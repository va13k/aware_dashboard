"""The session the API asks for itself, rather than leaving it to nginx.

Nginx runs `auth_request` in front of every dashboard route, and for a request
that arrives through nginx that is the check. It is not the only way in: every
service on the compose network can reach this process directly, and a location
block written without the check reaches it from outside. So the application asks
as well, through one dependency declared on it rather than on each router.

Three things are worth holding onto. A route answers nothing without a session,
whichever direction the request came from. The paths that cannot have one --- the
login pages, and the container's own health probe --- still answer. And the
WebSocket is left to itself, because a handshake refused with a status is one the
browser cannot read a reason from.
"""

import time
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from app.main import app
from app.routers import auth

pytestmark = pytest.mark.no_session

USERNAME = "researcher"
PASSWORD = "a-deployment-password"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth, "_USERNAME", USERNAME)
    monkeypatch.setattr(auth, "_PASSWORD", PASSWORD)
    return TestClient(app)


def log_in(client) -> None:
    """A session obtained the way a researcher obtains one."""
    response = client.post(
        "/auth/login",
        data={"username": USERNAME, "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text


def test_a_route_answers_nothing_without_a_session(client):
    assert client.get("/devices").status_code == 401


def test_the_same_route_answers_a_request_that_carries_one(client):
    log_in(client)

    assert client.get("/devices").status_code != 401


def test_a_forged_cookie_is_refused(client):
    """The signature is what makes the cookie a session, so a value shaped like one
    and signed by nothing is not."""
    client.cookies.set(auth.SESSION_COOKIE, f"{USERNAME}:0:deadbeef")

    assert client.get("/devices").status_code == 401


def test_an_expired_session_is_refused(client):
    """The cookie carries when it was issued, and the age is checked as well as the
    signature: a session that outlived its window verifies and is still refused."""
    issued_long_ago = time.time() - (auth._MAX_AGE + 60)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(auth, "time", SimpleNamespace(time=lambda: issued_long_ago))
        aged = auth._make_token(USERNAME)

    client.cookies.set(auth.SESSION_COOKIE, aged)

    assert client.get("/devices").status_code == 401


def test_the_login_pages_answer_without_one(client):
    """They are how a session is obtained, so requiring one would leave nobody able
    to log in."""
    assert client.get("/auth/login").status_code == 200
    assert client.get("/auth/validate").status_code == 401


def test_the_health_probe_answers_without_one(client):
    """The container runs it against itself, ahead of nginx and holding no cookie,
    and a probe that cannot answer is a service compose reports as unhealthy."""
    assert client.get("/health").status_code == 200


def test_the_socket_is_left_to_check_itself():
    """`live` reads the same cookie and closes with a code that says why, which is
    the only refusal a browser can read from a handshake."""
    assert "/live" in auth.SOCKET_PATHS


def test_a_handshake_without_a_session_is_refused(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/live"):
            pass


def test_a_handshake_carrying_one_is_accepted(client):
    """The guard runs for a handshake as well as a request, so it has to be able to
    read one: `HTTPConnection` is the shape they share."""
    log_in(client)

    with client.websocket_connect("/live") as socket:
        assert socket.receive_json()["type"] == "hello"


def test_the_guard_is_declared_on_the_application():
    """Declared once rather than on each router, so a router added later is guarded
    by having been added and nothing has to remember."""
    declared = [
        dependency.dependency.__name__ for dependency in app.router.dependencies
    ]

    assert "require_session" in declared


def test_every_route_carries_it(client):
    """What the declaration buys, read off the routes themselves."""
    unguarded = [
        route.path
        for route in app.routes
        if getattr(route, "dependant", None) is not None
        and not any(
            dependency.call.__name__ == "require_session"
            for dependency in route.dependant.dependencies
        )
    ]

    assert unguarded == []
