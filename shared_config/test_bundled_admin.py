"""Tests for bootstrapping the administrator of a database this deployment runs.

MySQL creates one account of its own, `root`, and bakes its password into the data
directory the first time the server starts --- the variable is read once and
ignored ever after. So a deployment brought up again over a volume that outlived
it holds a root password the server has never had.

Root is here to do one thing: create the account the researcher named, with the
privileges to administer the study. Everything the deploy does afterwards runs as
that account. Which is why a root that will not authenticate is only fatal while
the account it would have created is missing --- once that account is on the
server and opens it, the bootstrap is behind us and root's password decides
nothing.
"""

import pathlib
import subprocess
import sys

import pytest

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import init_study_tables as init  # noqa: E402

from shared_config import database  # noqa: E402

ADMIN = "admin"
ADMIN_PASSWORD = "the-one-the-researcher-typed"
ENV = {"MYSQL_ROOT_PASSWORD": "the-one-.env-holds"}


class FakeClient:
    """A database that accepts some accounts and refuses others."""

    def __init__(self, accepts):
        self.accepts = accepts
        self.calls = []

    def run(self, user, password, sql="", schema="", batch=False, stdin=None):
        self.calls.append((user, sql))
        ok = self.accepts.get(user) == password
        return subprocess.CompletedProcess(
            args=[],
            returncode=0 if ok else 1,
            stdout="",
            stderr="" if ok else "ERROR 1045 (28000): Access denied",
        )


def test_root_creates_the_account_the_researcher_named():
    client = FakeClient({"root": ENV["MYSQL_ROOT_PASSWORD"]})

    assert init.ensure_bundled_admin(client, ADMIN, ADMIN_PASSWORD, ENV) is True
    statements = client.calls[0][1]
    assert "CREATE USER IF NOT EXISTS 'admin'@'%'" in statements
    assert "GRANT ALL PRIVILEGES ON *.* TO 'admin'@'%' WITH GRANT OPTION;" in statements


def test_a_stale_root_password_is_not_fatal_once_the_account_exists():
    """The volume outlived the deployment, so the server's root password is the old
    one --- and the administrator on it is the account the deploy goes on to use."""
    client = FakeClient({ADMIN: ADMIN_PASSWORD})

    assert init.ensure_bundled_admin(client, ADMIN, ADMIN_PASSWORD, ENV) is False
    assert [user for user, _ in client.calls] == ["root", ADMIN]


def test_a_stale_root_password_is_fatal_while_the_account_is_missing():
    """Nothing else can create it, so this is a deployment to stop rather than one
    to carry on with."""
    client = FakeClient({})

    with pytest.raises(RuntimeError) as refused:
        init.ensure_bundled_admin(client, ADMIN, ADMIN_PASSWORD, ENV)

    message = str(refused.value)
    assert "would not create 'admin'" in message
    assert database.ADMIN_PASSWORD_ENV in message


def test_a_deployment_administered_as_root_has_nothing_to_bootstrap():
    client = FakeClient({})

    assert init.ensure_bundled_admin(client, "root", "whatever", ENV) is False
    assert client.calls == []


def test_a_missing_root_password_is_reported_as_the_one_it_is():
    with pytest.raises(RuntimeError) as refused:
        init.ensure_bundled_admin(FakeClient({}), ADMIN, ADMIN_PASSWORD, {})

    assert "MYSQL_ROOT_PASSWORD is missing" in str(refused.value)
