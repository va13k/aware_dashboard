"""Session tokens survive a restart, and still expire on time.

The bug these guard: the signing key used to be generated per process, so every
API restart invalidated every cookie and signed all researchers out mid-session -
and two workers would have rejected each other's cookies. The key now comes from
the environment, which is what makes a restart survivable.

A restart is simulated by reloading the module: that re-runs the key lookup
exactly as a fresh process would, so a token minted before the reload is verified
by what is, as far as the code is concerned, a different run.
"""

import importlib
import time

import pytest

from app.routers import auth as auth_module


def _reload(monkeypatch, secret: str | None):
    """The auth router as a freshly started process would have it.

    `importlib.reload` re-executes the module in place and returns the *same*
    object, so anything a test wants to compare across a restart has to be copied
    out of it first - a held reference would only ever see the current value.
    """
    if secret is None:
        monkeypatch.delenv(auth_module.SESSION_SECRET_ENV, raising=False)
    else:
        monkeypatch.setenv(auth_module.SESSION_SECRET_ENV, secret)
    return importlib.reload(auth_module)


@pytest.fixture(autouse=True)
def restore_module():
    """Leave the imported module as the rest of the suite expects to find it."""
    yield
    importlib.reload(auth_module)


def test_token_verifies_in_the_process_that_made_it(monkeypatch):
    auth = _reload(monkeypatch, "a-configured-secret")
    assert auth._verify_token(auth._make_token("researcher")) is True


def test_token_survives_a_restart_when_the_secret_is_configured(monkeypatch):
    before = _reload(monkeypatch, "a-configured-secret")
    token = before._make_token("researcher")
    secret_before = before._SECRET

    after = _reload(monkeypatch, "a-configured-secret")
    assert after._SECRET == secret_before
    assert after._verify_token(token) is True


def test_token_dies_on_restart_when_no_secret_is_configured(monkeypatch):
    """The old behaviour, still the fallback - and the reason for the warning."""
    before = _reload(monkeypatch, None)
    token = before._make_token("researcher")
    secret_before = before._SECRET

    after = _reload(monkeypatch, None)
    assert after._SECRET != secret_before
    assert after._verify_token(token) is False


def test_rotating_the_secret_signs_everyone_out(monkeypatch):
    before = _reload(monkeypatch, "the-old-secret")
    token = before._make_token("researcher")

    after = _reload(monkeypatch, "the-new-secret")
    assert after._verify_token(token) is False


def test_blank_secret_is_treated_as_unset(monkeypatch):
    auth = _reload(monkeypatch, "   ")
    assert auth._verify_token(auth._make_token("researcher")) is True
    assert auth._SECRET != b"   "


def test_expiry_is_unchanged_by_the_fix(monkeypatch):
    """Eight hours is deliberate; only the restart behaviour was the bug."""
    auth = _reload(monkeypatch, "a-configured-secret")
    assert auth._MAX_AGE == 8 * 3600

    issued = int(time.time()) - auth._MAX_AGE - 1
    message = f"researcher:{issued}"
    import hashlib
    import hmac

    signature = hmac.new(auth._SECRET, message.encode(), hashlib.sha256).hexdigest()
    assert auth._verify_token(f"{message}:{signature}") is False

    fresh = int(time.time()) - auth._MAX_AGE + 60
    message = f"researcher:{fresh}"
    signature = hmac.new(auth._SECRET, message.encode(), hashlib.sha256).hexdigest()
    assert auth._verify_token(f"{message}:{signature}") is True


def test_a_tampered_token_is_refused(monkeypatch):
    auth = _reload(monkeypatch, "a-configured-secret")
    token = auth._make_token("researcher")
    message, signature = token.rsplit(":", 1)

    # Flip the last character to one it certainly is not, so the tampered
    # signature never happens to equal the original.
    flipped = signature[:-1] + ("a" if signature[-1] != "a" else "b")

    assert auth._verify_token(f"{message}x:{signature}") is False
    assert auth._verify_token(f"{message}:{flipped}") is False
    assert auth._verify_token("") is False
    assert auth._verify_token("not-a-token") is False


def test_warns_only_when_the_secret_is_missing(monkeypatch, caplog):
    with caplog.at_level("WARNING"):
        _reload(monkeypatch, "a-configured-secret")
    assert auth_module.SESSION_SECRET_ENV not in caplog.text

    caplog.clear()
    with caplog.at_level("WARNING"):
        _reload(monkeypatch, None)
    assert auth_module.SESSION_SECRET_ENV in caplog.text
