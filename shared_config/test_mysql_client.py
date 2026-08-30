"""Tests for how setup hands a database password to the client that uses it.

A command line is public on the machine that runs it. `ps` lists every process's
arguments to every user on the host, and the same holds inside a container, so a
password written into the command that opens the database is readable by anyone with
a shell there for as long as the query runs. The account this deployment issues SQL
as is the one that administers the study's database, which makes it the worst of the
passwords to leave lying about.

So these check the one property the module has to keep: the password reaches the
client through a file docker reads and appears in nobody's arguments --- on either
placement, since one runs the client inside the bundled container and the other in a
throwaway one, and both go through docker. A file rather than an inherited variable
because setup reaches docker through sudo, which resets the environment.
"""

import pathlib
import subprocess

import pytest

from shared_config import mysql_client

PASSWORD = "a-password-nobody-should-see"


def _client(host: str) -> mysql_client.Client:
    return mysql_client.Client(["docker"], host, 3306)


class TestThePasswordIsNotAnArgument:
    """Client.run: handed over in a file, on both placements."""

    def _issued(self, monkeypatch, host):
        """What one query put on the command line, and what the file beside it held."""
        seen = {}

        def record(command, **kwargs):
            # A client addressed at a named database asks docker whether the
            # deployment's network exists before it runs anything on it.
            if "--env-file" not in command:
                return subprocess.CompletedProcess(command, 0, "", "")
            seen["command"] = command
            path = command[command.index("--env-file") + 1]
            seen["file"] = pathlib.Path(path).read_text(encoding="utf-8")
            seen["mode"] = pathlib.Path(path).stat().st_mode & 0o777
            seen["path"] = path
            return subprocess.CompletedProcess(command, 0, "", "")

        monkeypatch.setattr(mysql_client.subprocess, "run", record)
        _client(host).run("root", PASSWORD, "SELECT 1;", "aware_android")
        return seen

    def test_the_bundled_query_does_not_carry_it(self, monkeypatch):
        seen = self._issued(monkeypatch, "mysql")
        assert PASSWORD not in " ".join(seen["command"])
        assert "exec" in seen["command"]

    def test_the_external_query_does_not_carry_it(self, monkeypatch):
        seen = self._issued(monkeypatch, "db.example.edu")
        assert PASSWORD not in " ".join(seen["command"])
        assert "run" in seen["command"]

    def test_the_file_docker_reads_holds_it(self, monkeypatch):
        seen = self._issued(monkeypatch, "mysql")
        assert seen["file"] == f"{mysql_client.PASSWORD_ENV}={PASSWORD}\n"

    def test_only_its_owner_can_read_that_file(self, monkeypatch):
        assert self._issued(monkeypatch, "mysql")["mode"] == 0o600

    def test_the_file_does_not_outlive_the_query(self, monkeypatch):
        seen = self._issued(monkeypatch, "mysql")
        assert not pathlib.Path(seen["path"]).exists()

    def test_it_is_gone_even_when_the_query_raises(self, monkeypatch):
        seen = {}

        def explode(command, **kwargs):
            seen["path"] = command[command.index("--env-file") + 1]
            raise OSError("docker is not there")

        monkeypatch.setattr(mysql_client.subprocess, "run", explode)
        with pytest.raises(OSError):
            _client("mysql").run("root", PASSWORD, "SELECT 1;")
        assert not pathlib.Path(seen["path"]).exists()

    def test_a_certificate_does_not_put_it_back(self, monkeypatch):
        # The authority is planted by a shell line the client is exec'd behind, and
        # a password quoted into that line would be a password in its arguments.
        seen = {}

        def record(command, **kwargs):
            seen["command"] = command
            return subprocess.CompletedProcess(command, 0, "", "")

        monkeypatch.setattr(mysql_client.subprocess, "run", record)
        mysql_client.Client(
            ["docker"], "db.example.edu", 3306, ca_pem="-----BEGIN CERTIFICATE-----\nx\n"
        ).run("root", PASSWORD, "SELECT 1;")
        assert PASSWORD not in " ".join(seen["command"])

    def test_it_does_not_depend_on_the_environment_surviving_sudo(self, monkeypatch):
        """setup reaches docker through sudo, which resets the environment.

        A password handed over as an inherited variable arrives empty there, and
        MySQL answers with a refusal that reads as a login with no password at all.
        """
        seen = self._issued(monkeypatch, "db.example.edu")
        assert "-e" not in seen["command"]
        assert mysql_client.PASSWORD_ENV not in " ".join(seen["command"])
