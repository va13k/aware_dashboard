"""Tests for App01/participant_db.py.

The MySQL connection is mocked, so these exercise the logic around it:
input guards, account-existence check, the exact ALTER USER statement issued,
error wrapping, and that the connection is always closed.
"""
from unittest import mock

import pytest

from App01 import participant_db
from App01.participant_db import ParticipantDbError, apply_account_credentials

VALID = dict(
    host="mysql",
    port=3306,
    admin_user="root", admin_password="rootpw",
    username="aware_android_participant",
)


def _mock_connection(fetchone=(1,), execute_side_effect=None):
    """Build a MagicMock connection whose cursor is a context manager."""
    connection = mock.MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = fetchone
    if execute_side_effect is not None:
        cursor.execute.side_effect = execute_side_effect
    return connection, cursor


# --------------------------------------------------------------------------
# Input guards (must not even open a connection)
# --------------------------------------------------------------------------

def test_missing_username_raises_without_connecting():
    with mock.patch.object(participant_db.pymysql, "connect") as connect:
        with pytest.raises(ParticipantDbError):
            apply_account_credentials(
                host="mysql", port=3306, admin_user="root", admin_password="rootpw",
                username="", password="x", require_ssl=False,
            )
    connect.assert_not_called()


def test_missing_admin_password_raises_without_connecting():
    with mock.patch.object(participant_db.pymysql, "connect") as connect:
        with pytest.raises(ParticipantDbError):
            apply_account_credentials(
                host="mysql", port=3306, admin_user="root", admin_password="",
                username="aware_android_participant", password="x", require_ssl=False,
            )
    connect.assert_not_called()


# --------------------------------------------------------------------------
# Connection / existence failures
# --------------------------------------------------------------------------

def test_connect_failure_is_wrapped():
    boom = OSError("connection refused")
    with mock.patch.object(participant_db.pymysql, "connect", side_effect=boom):
        with pytest.raises(ParticipantDbError) as excinfo:
            apply_account_credentials(password="x", require_ssl=False, **VALID)
    assert "reach the database" in str(excinfo.value)
    assert excinfo.value.__cause__ is boom


def test_missing_account_raises_and_does_not_alter():
    connection, cursor = _mock_connection(fetchone=None)
    with mock.patch.object(participant_db.pymysql, "connect", return_value=connection):
        with pytest.raises(ParticipantDbError) as excinfo:
            apply_account_credentials(password="x", require_ssl=False, **VALID)

    assert "does not exist" in str(excinfo.value)
    # Only the existence SELECT ran; no ALTER USER was attempted.
    assert cursor.execute.call_count == 1
    assert "SELECT" in cursor.execute.call_args_list[0].args[0]
    connection.close.assert_called_once()


# --------------------------------------------------------------------------
# Happy paths: the exact statement issued
# --------------------------------------------------------------------------

def test_sets_password_with_require_none():
    connection, cursor = _mock_connection()
    with mock.patch.object(participant_db.pymysql, "connect", return_value=connection):
        apply_account_credentials(password="s3cret", require_ssl=False, **VALID)

    select_sql, select_params = cursor.execute.call_args_list[0].args
    assert "SELECT" in select_sql
    assert select_params == (VALID["username"], "%")

    alter_sql, alter_params = cursor.execute.call_args_list[1].args
    assert alter_sql.startswith("ALTER USER %s@%s IDENTIFIED BY %s")
    assert alter_sql.endswith("REQUIRE NONE")
    assert alter_params == (VALID["username"], "%", "s3cret")
    connection.close.assert_called_once()


def test_passwordless_with_require_ssl():
    connection, cursor = _mock_connection()
    with mock.patch.object(participant_db.pymysql, "connect", return_value=connection):
        apply_account_credentials(password="", require_ssl=True, **VALID)

    alter_sql, alter_params = cursor.execute.call_args_list[1].args
    assert alter_sql.endswith("REQUIRE SSL")
    # Passwordless => empty password bound as the parameter.
    assert alter_params == (VALID["username"], "%", "")
    connection.close.assert_called_once()


# --------------------------------------------------------------------------
# DDL failure still closes the connection and is wrapped
# --------------------------------------------------------------------------

def test_alter_failure_is_wrapped_and_closes_connection():
    # First execute (SELECT) succeeds; second (ALTER) raises.
    connection, cursor = _mock_connection(
        execute_side_effect=[None, RuntimeError("access denied")]
    )
    with mock.patch.object(participant_db.pymysql, "connect", return_value=connection):
        with pytest.raises(ParticipantDbError) as excinfo:
            apply_account_credentials(password="x", require_ssl=False, **VALID)

    assert "rejected" in str(excinfo.value)
    connection.close.assert_called_once()
