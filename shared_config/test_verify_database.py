"""Tests for the question the database check asks about the connection itself.

The check runs before a study is deployed, and encryption is the one answer that
decides whether anything can write at all: the accounts are created requiring a TLS
session wherever the study asked for one, so a server that cannot offer it
authenticates and then refuses every insert. A deployment in that state comes up
healthy and collects nothing, which is exactly the failure this check exists to
turn into a message.

What is worth holding onto is the shape of the answers rather than the network. A
study that asked for plaintext gave an answer about a server it owns, and reporting
it as a failure would overrule a decision that is not this software's to make --- so
it is a warning the run carries on past. A study that asked for encryption and did
not get it is stopped, because everything after it would be measuring the wrong
server. And an authority a study publishes is checked here rather than first on a
participant's phone, where failing to verify is a device that keeps its data and
stops uploading.
"""

import pathlib
import subprocess
import sys

import pytest

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import verify_database  # noqa: E402


class _Client:
    """A MySQL client that answers from a script rather than from a server.

    ``answers`` is keyed by the TLS mode a connection was opened with, so a test says
    what the server does about encryption rather than what a query returns: "" is the
    plain client the check starts from, and the rest are what
    :meth:`shared_config.mysql_client.Client.asking_for` produces.
    """

    def __init__(self, answers: dict[str, tuple[int, str]]):
        self._answers = answers
        self.asked = []

    def asking_for(self, ssl_mode: str, ca_pem: str = ""):
        client = _Client(self._answers)
        client._mode = (ssl_mode, ca_pem)
        self.asked.append((ssl_mode, ca_pem))
        return client

    _mode = ("", "")

    def run(self, _user, _password, _sql="", _schema="", batch=False, stdin=None):
        code, out = self._answers.get(self._mode[0], (1, ""))
        return subprocess.CompletedProcess([], code, stdout=out, stderr="")


def _cipher(name="TLS_AES_256_GCM_SHA384"):
    return (0, f"Ssl_cipher\t{name}\n")


#: What MySQL returns for the cipher of a session that arrived in clear text: the
#: variable is there and its value is empty.
PLAINTEXT = (0, "Ssl_cipher\t\n")

#: A connection the server would not open at all.
REFUSED = (1, "")


class TestReadingTheSession:
    """session_cipher: what the connection actually negotiated.

    Asked of the session rather than of the server's configuration, because
    ``have_ssl`` --- the variable that used to answer it directly --- was removed in
    MySQL 8.4. Reading that would report every recent server as unable to encrypt.
    """

    def test_an_encrypted_session_reports_its_cipher(self):
        client = _Client({"": _cipher()})
        assert verify_database.session_cipher(client, "root", "pw") == (
            "TLS_AES_256_GCM_SHA384"
        )

    def test_a_clear_text_session_reports_nothing(self):
        assert verify_database.session_cipher(_Client({"": PLAINTEXT}), "root", "pw") == ""

    def test_a_connection_that_failed_reports_nothing(self):
        assert verify_database.session_cipher(_Client({"": REFUSED}), "root", "pw") == ""


class TestAStudyThatAskedForEncryption:
    def test_a_server_that_encrypts_passes(self):
        result = verify_database.check_tls(
            _Client({"": _cipher(), "REQUIRED": _cipher()}), "root", "pw", True
        )
        assert result["ok"]
        assert "TLS_AES_256_GCM_SHA384" in result["detail"]

    def test_a_server_that_will_not_encrypt_fails(self):
        # Not a warning: the accounts are granted on that condition, so a study
        # deployed here would authenticate and then refuse every insert.
        result = verify_database.check_tls(
            _Client({"": _cipher(), "REQUIRED": REFUSED}), "root", "pw", True
        )
        assert not result["ok"]
        assert not result["warning"]

    def test_an_encrypted_connection_says_what_it_does_not_prove(self):
        result = verify_database.check_tls(
            _Client({"": _cipher(), "REQUIRED": _cipher()}), "root", "pw", True
        )
        assert "not verified" in result["detail"]

    def test_an_authority_that_checks_out_is_reported_as_verified(self):
        client = _Client(
            {"": _cipher(), "REQUIRED": _cipher(), "VERIFY_CA": (0, "1\n")}
        )
        result = verify_database.check_tls(client, "root", "pw", True, "PEM")
        assert result["ok"]
        assert "verified" in result["detail"]
        assert ("VERIFY_CA", "PEM") in client.asked

    def test_an_authority_that_does_not_check_out_fails(self):
        # Devices are given the same authority and verify against it, so this is a
        # study whose phones would keep their data and stop uploading.
        client = _Client({"": _cipher(), "REQUIRED": _cipher(), "VERIFY_CA": REFUSED})
        result = verify_database.check_tls(client, "root", "pw", True, "PEM")
        assert not result["ok"]
        assert not result["warning"]


class TestAStudyThatAskedForPlaintext:
    def test_it_is_reported_and_not_failed(self):
        result = verify_database.check_tls(
            _Client({"": PLAINTEXT}), "root", "pw", False
        )
        assert result["warning"]
        assert not result["ok"]

    def test_what_it_costs_is_carried_into_the_line(self):
        result = verify_database.check_tls(
            _Client({"": PLAINTEXT}), "root", "pw", False, exposure="Anyone can read it."
        )
        assert "Anyone can read it." in result["detail"]

    def test_a_server_that_could_have_encrypted_is_named(self):
        # Worth going back for: this is a study in clear text by its own setting
        # rather than by the server's limits.
        result = verify_database.check_tls(
            _Client({"": _cipher()}), "root", "pw", False
        )
        assert "does offer encryption" in result["detail"]

    def test_nothing_is_asked_of_a_connection_nobody_encrypts(self):
        client = _Client({"": PLAINTEXT})
        verify_database.check_tls(client, "root", "pw", False, "PEM")
        assert client.asked == []


class TestWhatTheRestOfTheCheckDependsOn:
    """verify: which failures stop the run, and which are carried past."""

    @pytest.fixture(autouse=True)
    def _stub(self, monkeypatch):
        monkeypatch.setattr(
            verify_database.mysql_client, "Client", lambda *a, **k: _Client({})
        )
        monkeypatch.setattr(
            verify_database,
            "check_reachable",
            lambda *a, **k: verify_database.check("reachable", True, "answered"),
        )
        for name, answer in (
            ("check_schemas", "schema"),
            ("check_profiles", "accounts"),
            ("check_tables", "tables"),
        ):
            monkeypatch.setattr(
                verify_database,
                name,
                lambda *a, _n=answer, **k: verify_database.check(_n, True, "fine"),
            )

    def test_a_demand_the_server_cannot_meet_stops_everything(self, monkeypatch):
        monkeypatch.setattr(
            verify_database,
            "check_tls",
            lambda *a, **k: verify_database.check("tls", False, "no"),
        )
        checks = verify_database.verify([], "h", 3306, "root", "pw", {"android": "s"}, [])
        assert [c["name"] for c in checks if c["ok"]] == ["reachable"]

    def test_a_study_in_clear_text_is_checked_the_rest_of_the_way(self, monkeypatch):
        # It declared a connection it can actually make, so what its accounts can
        # open is still the question worth answering.
        monkeypatch.setattr(
            verify_database,
            "check_tls",
            lambda *a, **k: verify_database.check("tls", False, "warned", warning=True),
        )
        checks = verify_database.verify([], "h", 3306, "root", "pw", {"android": "s"}, [])
        assert [c["name"] for c in checks if c["ok"]] == [
            "reachable",
            "schema",
            "accounts",
            "tables",
        ]


class _Server:
    """A MySQL that answers from what it holds, and remembers what it was asked.

    Keyed by the account a query arrives on, because what each account can do is the
    whole subject: a fake that answered the same thing to everyone could not tell an
    account that opens the database from one that does not exist, which is the
    distinction the check reports.
    """

    def __init__(self, schemas=(), accounts=None, tables=None):
        self.schemas = set(schemas)
        self.accounts = dict(accounts or {})
        self.tables = {name: set(held) for name, held in (tables or {}).items()}
        self.asked = []

    def asking_for(self, _ssl_mode, _ca_pem=""):
        return self

    def on_network(self):
        return True

    def run(self, user, password, sql="", schema="", batch=False, stdin=None, keep_going=False):
        self.asked.append(sql)
        if self.accounts.get(user) != password:
            return subprocess.CompletedProcess(
                [], 1, stdout="", stderr=f"ERROR 1045 (28000): Access denied for user '{user}'"
            )
        if sql.startswith("SHOW STATUS"):
            return _answer("Ssl_cipher\t\n")
        if sql.startswith("SHOW GRANTS"):
            return _answer(f'GRANT USAGE ON *.* TO "{user}"@"%"\n')
        if "information_schema.SCHEMATA" in sql:
            name = _subject(sql)
            return _answer(f"{name}\n" if name in self.schemas else "")
        if "mysql.user" in sql:
            return _answer("1\n" if _subject(sql) in self.accounts else "")
        if "information_schema.TABLES" in sql:
            held = self.tables.get(_subject(sql), ())
            return _answer("".join(f"{name}\n" for name in sorted(held)))
        return _answer("1\n")


def _answer(text):
    return subprocess.CompletedProcess([], 0, stdout=text, stderr="")


def _subject(sql):
    """The value a check's query compares against, which is its last quoted string."""
    return sql.rsplit("'", 2)[-2] if sql.count("'") >= 2 else ""


def _server(schemas=(), accounts=None, tables=None):
    known = {"root": "pw"}
    known.update(accounts or {})
    return _Server(schemas=schemas, accounts=known, tables=tables)


#: A study's own account, as the check receives it from the study model.
SERVER_PROFILE = {
    "username": "aware_android_server",
    "password": "s3cret",
    "schemas": ["aware_android"],
    "writes": True,
}


class TestTheSchemasAStudyNeeds:
    """check_schemas: both of them, and who is going to create what is missing."""

    def test_both_platforms_are_asked_about(self):
        """A deployment hands the dashboard a URL into each schema, so provisioning
        one of them leaves a service pointed at a database that does not exist."""
        result = verify_database.check_schemas(
            _server(schemas={"aware_android"}), "root", "pw", ["aware_android", "aware_ios"]
        )
        assert not result["ok"]
        assert "aware_ios" in result["detail"]

    def test_what_the_deploy_will_create_is_not_a_failure(self):
        # Nothing here creates the schema, so a database that has never been
        # deployed to could otherwise never pass the check that precedes deploying.
        result = verify_database.check_schemas(
            _server(), "root", "pw", ["aware_android", "aware_ios"]
        )
        assert result["warning"] and not result["ok"]

    def test_a_database_made_by_hand_fails_on_it(self):
        """Nothing else is going to create it, so there is nothing to wait for."""
        result = verify_database.check_schemas(
            _server(), "root", "pw", ["aware_android"], create=False
        )
        assert not result["ok"] and not result["warning"]


class TestTheAccountsAStudyOpensItWith:
    """check_profiles: each account asked to open the database, as itself."""

    def test_an_account_that_opens_the_database_passes(self):
        server = _server(accounts={"aware_android_server": "s3cret"})
        result = verify_database.check_profiles(server, "root", "pw", [SERVER_PROFILE])
        assert result["ok"]
        assert "aware_android_server" in result["detail"]

    def test_an_account_that_does_not_exist_yet_is_the_deploys_to_create(self):
        result = verify_database.check_profiles(_server(), "root", "pw", [SERVER_PROFILE])
        assert result["warning"] and not result["ok"]

    def test_an_account_that_will_not_take_this_studys_password_fails(self):
        """The account is there and the credential this study publishes is not its
        own, which no deploy fixes by creating anything."""
        server = _server(accounts={"aware_android_server": "something else"})
        result = verify_database.check_profiles(server, "root", "pw", [SERVER_PROFILE])
        assert not result["ok"] and not result["warning"]


#: The Android tables as db/android-tables.sql declares them, which is the same file
#: the deployment applies.
ANDROID_TABLES = verify_database.declared_tables(
    verify_database.PLATFORM_TABLE_FILES["android"]
)


class TestTheTablesRowsLandIn:
    """check_tables: a schema that is present is not a schema that is ready.

    An account can hold every grant its work needs on a schema with nothing in it,
    and the study then collects nothing while every other question answers well. The
    client says so only on the device, by inserting into `accelerometer` and being
    told there is no such table.
    """

    def test_a_schema_holding_none_of_them_is_reported(self):
        result = verify_database.check_tables(
            _server(tables={"aware_android": set()}), "root", "pw", {"android": "aware_android"}
        )
        assert not result["ok"]
        assert f"missing {len(ANDROID_TABLES)} of" in result["detail"]

    def test_a_schema_holding_them_all_passes(self):
        result = verify_database.check_tables(
            _server(tables={"aware_android": ANDROID_TABLES}),
            "root",
            "pw",
            {"android": "aware_android"},
        )
        assert result["ok"]


class TestTheCheckChangesNothing:
    """verify: the database is reported on, not provisioned.

    The check used to create the schema and the accounts it was asked about, and
    granted each account the reads its work makes --- table by table, before the
    tables existed. MySQL refuses a grant on a table that is not there and stops at
    it, which left the accounts made, the tables uncreated and the run reporting
    that the study could write.
    """

    def test_no_statement_it_issues_writes_to_the_database(self, monkeypatch):
        server = _server(
            schemas={"aware_android", "aware_ios"},
            accounts={"aware_android_server": "s3cret"},
            tables={"aware_android": ANDROID_TABLES},
        )
        monkeypatch.setattr(verify_database.mysql_client, "Client", lambda *a, **k: server)
        verify_database.verify(
            [],
            "h",
            3306,
            "root",
            "pw",
            {"android": "aware_android", "ios": "aware_ios"},
            [SERVER_PROFILE],
            tls_required=False,
        )
        assert not [
            sql
            for sql in server.asked
            if sql.strip().upper().startswith(
                ("CREATE", "GRANT", "ALTER", "INSERT", "DROP", "FLUSH", "SET")
            )
        ]
