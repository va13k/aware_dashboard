"""Integration tests for App01/participant_db.py against a real MySQL.

These run only when a MySQL server is reachable on 127.0.0.1:3306 (the port the
docker-compose stack exposes); otherwise the whole module is skipped, so the
unit suite stays hermetic. They operate on a throwaway account so the real
participant users are never touched.
"""
import os
import pathlib

import pymysql
import pytest

from App01.participant_db import ParticipantDbError, apply_account_credentials

HOST = "127.0.0.1"
PORT = 3306
TEST_USER = "aware_itest_participant"
HOST_PATTERN = "%"


def _root_password():
    if os.environ.get("MYSQL_ROOT_PASSWORD"):
        return os.environ["MYSQL_ROOT_PASSWORD"]
    env_file = pathlib.Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("MYSQL_ROOT_PASSWORD="):
                return line.split("=", 1)[1].strip()
    return "root"


@pytest.fixture(scope="module")
def admin():
    """Root connection params; skip the module if MySQL is unreachable."""
    password = _root_password()
    try:
        conn = pymysql.connect(
            host=HOST, port=PORT, user="root", password=password,
            connect_timeout=3, autocommit=True,
        )
        conn.close()
    except Exception as exc:  # server down / wrong creds -> not an integration env
        pytest.skip(f"MySQL not reachable on {HOST}:{PORT} ({exc})")
    return {"host": HOST, "port": PORT, "root_password": password}


def _root_conn(admin):
    return pymysql.connect(
        host=admin["host"], port=admin["port"], user="root",
        password=admin["root_password"], autocommit=True,
    )


@pytest.fixture
def test_user(admin):
    """Create a fresh throwaway participant account; drop it afterwards."""
    conn = _root_conn(admin)
    with conn.cursor() as cur:
        cur.execute(f"DROP USER IF EXISTS '{TEST_USER}'@'{HOST_PATTERN}'")
        cur.execute(f"CREATE USER '{TEST_USER}'@'{HOST_PATTERN}' IDENTIFIED BY 'initpw'")
    try:
        yield TEST_USER
    finally:
        with conn.cursor() as cur:
            cur.execute(f"DROP USER IF EXISTS '{TEST_USER}'@'{HOST_PATTERN}'")
        conn.close()


def _apply(admin, username, password, require_ssl):
    apply_account_credentials(
        host=admin["host"], port=admin["port"], root_password=admin["root_password"],
        username=username, password=password, require_ssl=require_ssl,
    )


def _login(password):
    """Authenticate as the test user (raises pymysql.err on failure)."""
    conn = pymysql.connect(
        host=HOST, port=PORT, user=TEST_USER, password=password, connect_timeout=3,
    )
    conn.close()


def _ssl_type(admin, username):
    conn = _root_conn(admin)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ssl_type FROM mysql.user WHERE user = %s AND host = %s",
            (username, HOST_PATTERN),
        )
        row = cur.fetchone()
    conn.close()
    return row[0]


# --------------------------------------------------------------------------

def test_password_change_takes_effect(admin, test_user):
    _apply(admin, test_user, password="newpw123", require_ssl=False)

    _login("newpw123")  # new password authenticates
    with pytest.raises(pymysql.err.OperationalError):
        _login("initpw")  # the old password no longer works


def test_passwordless_allows_empty_password(admin, test_user):
    _apply(admin, test_user, password="", require_ssl=False)
    _login("")  # empty password authenticates


def test_require_ssl_is_applied_and_cleared(admin, test_user):
    _apply(admin, test_user, password="x", require_ssl=True)
    assert _ssl_type(admin, test_user) == "ANY"

    _apply(admin, test_user, password="x", require_ssl=False)
    assert _ssl_type(admin, test_user) == ""


def test_missing_account_raises(admin):
    with pytest.raises(ParticipantDbError) as excinfo:
        _apply(admin, "aware_itest_absent_account", password="x", require_ssl=False)
    assert "does not exist" in str(excinfo.value)
