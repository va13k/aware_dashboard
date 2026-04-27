import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/auth", tags=["auth"])

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

_SECRET = secrets.token_bytes(32)
_COOKIE = "aware_session"
_MAX_AGE = 8 * 3600

_USERNAME = os.environ.get("RESEARCHER_USERNAME", "")
_PASSWORD = os.environ.get("RESEARCHER_PASSWORD", "")


def _check_credentials(username: str, password: str) -> bool:
    if not _USERNAME or not _PASSWORD:
        return False
    return (
        hmac.compare_digest(username, _USERNAME)
        and hmac.compare_digest(password, _PASSWORD)
    )


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
        msg, sig = token[:last], token[last + 1:]
        expected = hmac.new(_SECRET, msg.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        _, ts = msg.rsplit(":", 1)
        return time.time() - int(ts) <= _MAX_AGE
    except Exception:
        return False


def _safe_next(url: str) -> str:
    if url and url.startswith("/") and not url.startswith("//"):
        return url
    return "/configurator/"


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
        resp.set_cookie(_COOKIE, token, max_age=_MAX_AGE, httponly=True, samesite="lax")
        return resp
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next_url": next_url, "error": True, "not_configured": False},
        status_code=401,
    )


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/auth/login", status_code=302)
    resp.delete_cookie(_COOKIE)
    return resp
