import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.requests import HTTPConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

SESSION_SECRET_ENV = "DASHBOARD_SESSION_SECRET"


def _load_secret() -> bytes:
    """The key sessions are signed with, from the deployment rather than the run.

    A key minted per process makes every restart a logout: cookies issued before
    it no longer verify, so a deploy signs everyone out mid-session. It also caps
    the API at one worker, since two processes would reject each other's cookies.
    Reading it from the environment - written once at deployment, alongside the
    other credentials - fixes both, and makes signing everyone out a deliberate
    rotation instead of a side effect of restarting.

    Falling back to a random key keeps a deployment that has not set one working,
    at the cost of the behaviour above; it is logged so it is not a surprise.
    """
    configured = os.environ.get(SESSION_SECRET_ENV, "").strip()
    if configured:
        return configured.encode()
    logger.warning(
        "%s is not set: signing sessions with a key generated for this process, "
        "so restarting the API will log every researcher out and only one worker "
        "can serve requests.",
        SESSION_SECRET_ENV,
    )
    return secrets.token_bytes(32)


_SECRET = _load_secret()
_COOKIE = "aware_session"

#: What the deployment was configured to serve, used when a request carries no
#: answer of its own. Read once, because it describes the deployment rather than
#: any particular request.
_CONFIGURED_PROTOCOL = os.getenv("PROTOCOL", "http").strip().lower()


def _secure_cookie(request: Request) -> bool:
    """Whether this request's session cookie may only travel over TLS.

    Decided per request rather than at startup. Nginx terminates TLS and forwards
    the scheme it answered on, so this follows what the browser actually used --- a
    deployment reachable on both gets the right answer for each, and one that
    switches protocol does not keep handing out the old flag until its containers
    are recreated.

    Neither answer can be assumed. Without the flag an HTTPS deployment's cookie is
    sent over plain HTTP as well, and whoever reads it is logged in without a
    password. With it, an HTTP deployment never receives the cookie back at all, so
    nobody can log in.

    The configured protocol answers when nothing forwarded a scheme, which is the
    case for a request that reached the API without passing the proxy.
    """
    forwarded = request.headers.get("x-forwarded-proto", "")
    scheme = forwarded.split(",")[0].strip().lower() or _CONFIGURED_PROTOCOL
    return scheme == "https"
#: How long a session lasts. Enforced twice: the browser drops the cookie, and
#: `_verify_token` rejects a token this much older than the time it carries.
_MAX_AGE = 8 * 3600

_USERNAME = os.environ.get("RESEARCHER_USERNAME", "")
_PASSWORD = os.environ.get("RESEARCHER_PASSWORD", "")


def _check_credentials(username: str, password: str) -> bool:
    if not _USERNAME or not _PASSWORD:
        return False
    return hmac.compare_digest(username, _USERNAME) and hmac.compare_digest(password, _PASSWORD)


def verify_researcher_credentials(username: str, password: str) -> bool:
    return _check_credentials(username, password)


def _make_token(username: str) -> str:
    ts = str(int(time.time()))
    msg = f"{username}:{ts}"
    sig = hmac.new(_SECRET, msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}:{sig}"


def _verify_token(token: str) -> bool:
    try:
        last = token.rfind(":")
        if last == -1:
            return False
        msg, sig = token[:last], token[last + 1 :]
        expected = hmac.new(_SECRET, msg.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        _, ts = msg.rsplit(":", 1)
        return time.time() - int(ts) <= _MAX_AGE
    except Exception:
        return False


#: The cookie a browser presents, named for callers outside this module.
SESSION_COOKIE = _COOKIE


def session_is_valid(cookies) -> bool:
    """Whether a request's cookies carry a live researcher session.

    Nginx's `auth_request` guards the HTTP request that opens a WebSocket and
    nothing that travels over it afterwards, so the socket has to check for
    itself. Exposed here rather than reached into, so both checks read the same
    token the same way.
    """
    return _verify_token(cookies.get(_COOKIE, ""))


#: Answered without a session. The login pages are how one is obtained, and the
#: health probe is the container asking whether this process is up: it runs inside
#: the container, ahead of nginx, and reports nothing about the study.
OPEN_PREFIXES = ("/auth/",)
OPEN_PATHS = frozenset({"/health"})

#: Checked by the route instead of here. A WebSocket handshake refused with a status
#: is one the browser cannot read a reason from, so `live` reads the same cookie
#: itself and closes with a code that says why.
SOCKET_PATHS = frozenset({"/live"})


async def require_session(connection: HTTPConnection) -> None:
    """The session every route is held to, asked once for the whole application.

    Nginx runs `auth_request` in front of this, and that was the only thing asking:
    nothing here read the cookie, so a caller arriving by any other route --- another
    service on the compose network, a location block written without the check ---
    was answered in full. A boundary that holds from one direction only is one
    editing mistake away from holding from none.

    Declared on the application rather than on each router, so a router added later
    is guarded by having been added.

    `HTTPConnection` is the shape an ordinary request and a WebSocket handshake
    share, and this runs for both.
    """
    path = connection.url.path
    if path in OPEN_PATHS or path in SOCKET_PATHS or path.startswith(OPEN_PREFIXES):
        return
    if not session_is_valid(connection.cookies):
        raise HTTPException(status_code=401, detail="Not authenticated")


def _safe_next(url: str) -> str:
    if url and url.startswith("/") and not url.startswith("//") and not url.startswith("/api/"):
        return url
    return "/dashboard/"


@router.get("/validate")
async def validate(request: Request):
    if _verify_token(request.cookies.get(_COOKIE, "")):
        return Response(status_code=200)
    return Response(status_code=401)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/configurator/"):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next_url": next, "error": False, "not_configured": not _USERNAME or not _PASSWORD},
    )


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/configurator/"),
):
    next_url = _safe_next(next)
    if _check_credentials(username, password):
        token = _make_token(username)
        resp = RedirectResponse(url=next_url, status_code=302)
        resp.set_cookie(
            _COOKIE,
            token,
            max_age=_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=_secure_cookie(request),
        )
        return resp
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next_url": next_url, "error": True, "not_configured": False},
        status_code=401,
    )


@router.get("/logout")
async def logout(request: Request):
    resp = RedirectResponse(url="/auth/login", status_code=302)
    # Cleared with the attributes it was set with, or a browser keeps a cookie it
    # was asked to drop.
    resp.delete_cookie(
        _COOKIE, httponly=True, samesite="lax", secure=_secure_cookie(request)
    )
    return resp
