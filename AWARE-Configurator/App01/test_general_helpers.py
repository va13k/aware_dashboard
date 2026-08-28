"""Tests for the save-path helpers in App01/general.py.

Covers the pure/near-pure pieces of the hybrid save:
- _ingest_credentials: which account the study's writes authenticate as, and
  collapsing config_without_password + password
- _merge_and_sync_credentials: MySQL is touched only when credentials change
- _mysql_admin_settings: env / .env resolution and defaults
- write_json: atomic round-trip with no leftover temp files
"""
import json

import pytest

from App01 import general


# --------------------------------------------------------------------------
# _ingest_credentials
# --------------------------------------------------------------------------

PARTICIPANT = "aware_android_participant"
SERVER = "aware_android_server"


@pytest.mark.parametrize(
    "android, expected",
    [
        (
            {"password": "pw", "config_without_password": False},
            (PARTICIPANT, "pw", True),
        ),
        # config_without_password never blanks the account password
        (
            {"password": "pw", "config_without_password": True},
            (PARTICIPANT, "pw", True),
        ),
        ({}, (PARTICIPANT, "", True)),
    ],
)
def test_ingest_credentials_on_the_direct_path(android, expected):
    """A study that declares nothing runs the direct path, where a phone writes."""
    source = {"database": {"android": android}}
    assert general._ingest_credentials(source) == expected


@pytest.mark.parametrize(
    "databases, encrypted",
    [
        # A database this deployment runs is administered at both ends, so its
        # accounts are granted on the one condition it can always meet.
        ({"host": "db.internal", "android": {"password": "pw"}}, True),
        ({"host": "db.example.edu", "android": {"password": "pw"}}, True),
        (
            {
                "host": "db.example.edu",
                "tls": {"require": False},
                "android": {"password": "pw"},
            },
            False,
        ),
    ],
)
def test_the_accounts_require_what_the_study_declares(databases, encrypted):
    """The REQUIRE clause follows the study's one answer about its connection."""
    assert general._ingest_credentials({"database": databases})[2] is encrypted


def test_ingest_credentials_missing_database():
    assert general._ingest_credentials({}) == (PARTICIPANT, "", True)


def test_ingest_credentials_on_the_webservice_path():
    """The server performs every write there, so its own account is the one in use."""
    source = {
        "deployment": {"dataflow": {"android": "webservice"}},
        "database": {
            "android": {
                "password": "phone-pw",
                "server_username": SERVER,
                "server_password": "server-pw",
            }
        },
    }
    assert general._ingest_credentials(source) == (SERVER, "server-pw", True)


def test_ingest_credentials_name_the_server_account_without_one_stored():
    """A study predating the field still names the account the deployment creates."""
    source = {"deployment": {"dataflow": {"android": "webservice"}}, "database": {"android": {}}}
    assert general._ingest_credentials(source)[0] == SERVER


def test_the_env_variable_follows_the_account():
    """Each account's password is recorded under its own variable, so a change to one
    never advertises itself as the other's."""
    direct = {"database": {"android": {}}}
    webservice = {"deployment": {"dataflow": {"android": "webservice"}}}

    assert general._ingest_account(direct)["env_key"] == "PARTICIPANT_DB_PASSWORD"
    assert (
        general._ingest_account(webservice)["env_key"] == "ANDROID_SERVER_DB_PASSWORD"
    )


# --------------------------------------------------------------------------
# _merge_and_sync_credentials: only sync on an effective change
# --------------------------------------------------------------------------

def _source(password="old", passwordless=False, require_ssl=True):
    return {
        "database": {
            "host": "db.example.edu",
            "tls": {"require": require_ssl},
            "android": {
                "password": password,
                "config_without_password": passwordless,
            },
        }
    }


def test_sync_called_when_password_changes(monkeypatch):
    synced = []

    def fake_update(source, content):
        source["database"]["android"]["password"] = "new"
        return source

    monkeypatch.setattr(general, "update_source_from_android_config", fake_update)
    monkeypatch.setattr(general, "_sync_ingest_credentials", synced.append)

    source = _source(password="old")
    result = general._merge_and_sync_credentials(source, {"any": "content"})

    assert result is source
    assert synced == [source]


def test_sync_skipped_when_toggling_config_without_password(monkeypatch):
    synced = []

    def fake_update(source, content):
        # config_without_password does not affect the account credentials
        source["database"]["android"]["config_without_password"] = True
        return source

    monkeypatch.setattr(general, "update_source_from_android_config", fake_update)
    monkeypatch.setattr(general, "_sync_ingest_credentials", synced.append)

    general._merge_and_sync_credentials(_source(password="secret"), {})
    assert synced == []


def test_sync_called_when_require_ssl_changes(monkeypatch):
    synced = []

    def fake_update(source, content):
        source["database"]["tls"]["require"] = True
        return source

    monkeypatch.setattr(general, "update_source_from_android_config", fake_update)
    monkeypatch.setattr(general, "_sync_ingest_credentials", synced.append)

    general._merge_and_sync_credentials(
        _source(password="secret", require_ssl=False), {}
    )
    assert len(synced) == 1


def test_sync_called_when_the_dataflow_moves_the_account(monkeypatch):
    """A study that changes path writes with a different account, so the credentials
    it needs in MySQL are a different account's."""
    synced = []

    def fake_update(source, content):
        source["deployment"] = {"dataflow": {"android": "webservice"}}
        return source

    monkeypatch.setattr(general, "update_source_from_android_config", fake_update)
    monkeypatch.setattr(general, "_sync_ingest_credentials", synced.append)

    general._merge_and_sync_credentials(_source(password="secret"), {})
    assert len(synced) == 1


def test_sync_skipped_when_credentials_unchanged(monkeypatch):
    synced = []
    # update leaves the DB block exactly as-is
    monkeypatch.setattr(general, "update_source_from_android_config", lambda s, c: s)
    monkeypatch.setattr(general, "_sync_ingest_credentials", synced.append)

    general._merge_and_sync_credentials(_source(password="same"), {"questions": []})
    assert synced == []


# --------------------------------------------------------------------------
# _mysql_admin_settings
# --------------------------------------------------------------------------

def test_admin_settings_from_env_file(monkeypatch):
    monkeypatch.setattr(
        general,
        "load_env",
        lambda path: {"MYSQL_HOST": "dbhost", "MYSQL_PORT": "3307", "MYSQL_ROOT_PASSWORD": "rp"},
    )
    for key in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_ROOT_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    assert general._mysql_admin_settings() == {
        "host": "dbhost",
        "port": 3307,
        "root_password": "rp",
    }


def test_admin_settings_process_env_overrides_file(monkeypatch):
    monkeypatch.setattr(general, "load_env", lambda path: {"MYSQL_HOST": "filehost"})
    monkeypatch.setenv("MYSQL_HOST", "envhost")
    monkeypatch.delenv("MYSQL_PORT", raising=False)
    monkeypatch.delenv("MYSQL_ROOT_PASSWORD", raising=False)

    settings = general._mysql_admin_settings()
    assert settings["host"] == "envhost"
    assert settings["port"] == 3306  # default
    assert settings["root_password"] == ""  # default


def test_admin_settings_defaults(monkeypatch):
    monkeypatch.setattr(general, "load_env", lambda path: {})
    for key in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_ROOT_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    assert general._mysql_admin_settings() == {
        "host": "mysql",
        "port": 3306,
        "root_password": "",
    }


# --------------------------------------------------------------------------
# write_json
# --------------------------------------------------------------------------

def test_write_json_roundtrip_creates_parents(tmp_path):
    target = tmp_path / "nested" / "config.json"
    general.write_json(target, {"a": 1, "b": [1, 2]})

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "b": [1, 2]}
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_write_json_overwrites_existing(tmp_path):
    target = tmp_path / "config.json"
    general.write_json(target, {"v": 1})
    general.write_json(target, {"v": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 2}


def test_write_json_leaves_no_temp_files(tmp_path):
    target = tmp_path / "config.json"
    general.write_json(target, {"v": 1})
    leftovers = sorted(p.name for p in tmp_path.iterdir() if p.name != "config.json")
    assert leftovers == []


# --------------------------------------------------------------------------
# get_participant_password
# --------------------------------------------------------------------------

class _Request:
    def __init__(self, method="GET"):
        self.method = method


def test_get_participant_password_returns_stored_value(monkeypatch):
    monkeypatch.setattr(
        general, "read_source", lambda: _source(password="join-me-2026")
    )
    response = general.get_participant_password(_Request())

    assert response.status_code == 200
    assert json.loads(response.content) == {"password": "join-me-2026"}


def test_get_participant_password_is_not_cacheable(monkeypatch):
    monkeypatch.setattr(general, "read_source", lambda: _source(password="secret"))
    response = general.get_participant_password(_Request())

    assert response["Cache-Control"] == "no-store"


def test_get_participant_password_ignores_config_without_password(monkeypatch):
    # The redaction only applies to the served config; the account keeps its
    # password, so the researcher must still be able to read it back.
    monkeypatch.setattr(
        general, "read_source", lambda: _source(password="secret", passwordless=True)
    )
    response = general.get_participant_password(_Request())

    assert json.loads(response.content) == {"password": "secret"}


def test_get_participant_password_without_source_block(monkeypatch):
    monkeypatch.setattr(general, "read_source", lambda: {})
    response = general.get_participant_password(_Request())

    assert json.loads(response.content) == {"password": ""}


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_get_participant_password_rejects_writes(monkeypatch, method):
    monkeypatch.setattr(general, "read_source", lambda: _source(password="secret"))
    response = general.get_participant_password(_Request(method))

    assert response.status_code == 405
    assert b"secret" not in response.content


# --------------------------------------------------------------------------
# update_source_from_android_config: what a submitted config may decide
# --------------------------------------------------------------------------


def _saveable(android_dataflow="webservice", host="db.internal", **android_db):
    """A study model shaped enough for the save path to merge into."""
    database = {
        "port": 3306,
        "name": "aware_android",
        "username": "aware_android_participant",
        "password": "stored",
        "config_without_password": True,
    }
    database.update(android_db)
    return {
        "deployment": {"dataflow": {"android": android_dataflow, "ios": "webservice"}},
        "database": {"host": host, "android": database, "ios": {}},
        "study": {"id": "s", "title": "t", "description": "d"},
        "researcher": {"first_name": "f", "last_name": "l", "contact": "c"},
        "android": {"settings": {}},
        "shared": {"sensors": {}, "esms": {"questions": [], "schedules": []}},
    }


def _submit(source, **database):
    """One save, carrying whatever a browser held in its database section."""
    content = {
        "_id": "s",
        "study_info": {},
        # The host the study already declares unless the case is about changing it,
        # because the placement is what decides whether the rest of this section is
        # the researcher's to set.
        "database": {"database_host": source["database"]["host"], **database},
    }
    if "dataflow" in database:
        content["dataflow"] = database.pop("dataflow")
        content["database"].pop("dataflow", None)
    return general.update_source_from_android_config(source, content)


class TestTheDataflowIsNotSubmittable:
    """The study address every enrolled phone joined at, held against the form.

    A browser keeps its own copy of the config this round-trips, so a stale one
    would otherwise re-address a running study on the next save. The published
    database port follows from the same choice and changes only when the
    deployment is brought up again, so this is reported here and set by setup.
    """

    def test_a_submitted_dataflow_does_not_change_the_study(self):
        source = _saveable("webservice")

        general.update_source_from_android_config(
            source, {"_id": "s", "study_info": {}, "dataflow": "direct", "database": {}}
        )

        assert source["deployment"]["dataflow"]["android"] == "webservice"

    def test_the_other_direction_is_held_too(self):
        source = _saveable("direct")

        general.update_source_from_android_config(
            source,
            {"_id": "s", "study_info": {}, "dataflow": "webservice", "database": {}},
        )

        assert source["deployment"]["dataflow"]["android"] == "direct"

    def test_a_study_carrying_none_reads_as_the_default(self):
        source = _saveable("webservice")
        del source["deployment"]["dataflow"]["android"]

        general.update_source_from_android_config(
            source, {"_id": "s", "study_info": {}, "database": {}}
        )

        assert source["deployment"]["dataflow"]["android"] == "direct"


class TestWhichDatabaseSettingsEachPathDecides:
    """What a submitted config may decide about the connection, and on which placement.

    Encryption is settled by where the database runs, not by the dataflow: a database
    this deployment runs is administered at both ends and always encrypted, and one
    the researcher named answers to its owner. So the setting is the researcher's on
    the second placement and nobody's on the first --- and a browser keeps its own
    copy of this section, so a value from the other placement arrives here either way.

    `config_without_password` governs the config a phone downloads, and the direct
    path is the one that publishes a password in it.
    """

    def test_a_named_database_can_be_told_it_cannot_encrypt(self):
        source = _saveable("webservice", host="db.example.edu")

        _submit(source, require_ssl=False)

        assert source["database"]["tls"]["require"] is False

    def test_the_same_holds_on_the_direct_path(self):
        source = _saveable("direct", host="db.example.edu")

        _submit(source, require_ssl=False)

        assert source["database"]["tls"]["require"] is False

    def test_encryption_can_be_asked_for_again(self):
        source = _saveable("webservice", host="db.example.edu")
        source["database"]["tls"] = {"require": False}

        _submit(source, require_ssl=True)

        assert source["database"]["tls"]["require"] is True

    def test_a_bundled_database_is_not_a_study_setting(self):
        # Refusing the value rather than storing it: a stale browser copy would
        # otherwise leave a study declaring plaintext against a server whose accounts
        # this deployment creates requiring TLS, and nothing could write.
        source = _saveable("webservice")

        _submit(source, require_ssl=False)

        assert "tls" not in source["database"]

    def test_config_without_password_is_held_on_the_webservice_path(self):
        source = _saveable("webservice", config_without_password=True)

        _submit(source, config_without_password=False)

        assert source["database"]["android"]["config_without_password"] is True

    def test_a_password_change_still_reaches_the_account(self):
        """The credential the micro-server authenticates with stays rotatable, under
        the key belonging to the account that holds it."""
        source = _saveable("webservice", password="stored")

        _submit(source, database_password="rotated")

        assert source["database"]["android"]["server_password"] == "rotated"
        # The participant account's password is left where it was.
        assert source["database"]["android"]["password"] == "stored"

def _webservice_source(password="phone-pw", server_password="server-pw"):
    return {
        "deployment": {"dataflow": {"android": "webservice"}},
        "database": {
            "android": {
                "password": password,
                "server_username": SERVER,
                "server_password": server_password,
            }
        },
    }


def test_get_participant_password_reveals_the_account_it_changes(monkeypatch):
    """On the webservice path the field governs the server's account, so revealing it
    has to show that account's password rather than the participants'."""
    monkeypatch.setattr(general, "read_source", _webservice_source)
    response = general.get_participant_password(_Request())

    assert json.loads(response.content) == {"password": "server-pw"}
    assert b"phone-pw" not in response.content


def test_a_submitted_password_is_stored_for_the_account_on_the_path():
    """One field in the form, and it governs the credential the study writes with."""
    source = _saveable("webservice", password="phone-pw", server_password="old-server-pw")

    _submit(source, database_password="new-server-pw")

    android = source["database"]["android"]
    assert android["server_password"] == "new-server-pw"
    # A field that governs one account is not a field that rotates both.
    assert android["password"] == "phone-pw"


def test_a_submitted_password_reaches_the_participant_account_on_the_direct_path():
    source = _saveable("direct", password="old-phone-pw", server_password="server-pw")

    _submit(source, database_password="new-phone-pw")

    android = source["database"]["android"]
    assert android["password"] == "new-phone-pw"
    assert android["server_password"] == "server-pw"


# --------------------------------------------------------------------------
# write_outputs: the Android instance's own configuration
# --------------------------------------------------------------------------

def test_saving_writes_the_servers_credential_into_its_own_configuration(
    monkeypatch, tmp_path
):
    """The micro-server authenticates with the account this field changes, and reads
    it from its own configuration file, so a save has to rewrite that file too --
    otherwise the account holds a password the server does not know."""
    import pathlib as _pathlib

    root = _pathlib.Path(general.PROJECT_ROOT)
    source = json.loads((root / "source.example.json").read_text(encoding="utf-8"))
    source["deployment"]["dataflow"]["android"] = "webservice"
    source["database"]["android"]["password"] = "phone-pw"
    source["database"]["android"]["server_password"] = "server-pw"

    monkeypatch.setattr(
        general, "load_env", lambda path: {"PUBLIC_HOST": "example.org", "PROTOCOL": "http"}
    )
    monkeypatch.setattr(general, "STUDY_CONFIG_PATH", tmp_path / "studyConfig.json")
    monkeypatch.setattr(general, "IOS_CONFIG_PATH", tmp_path / "aware-config.json")
    monkeypatch.setattr(general, "IOS_ESM_CONFIG_PATH", tmp_path / "esm.json")
    monkeypatch.setattr(
        general, "ANDROID_MICRO_CONFIG_PATH", tmp_path / "aware-config.android.json"
    )

    general.write_outputs(source)

    written = json.loads(
        (tmp_path / "aware-config.android.json").read_text(encoding="utf-8")
    )
    assert written["server"]["database_user"] == SERVER
    assert written["server"]["database_pwd"] == "server-pw"
    # The participant credential belongs to the path phones open the database on.
    assert "phone-pw" not in json.dumps(written)


def test_the_servers_credential_is_not_left_world_readable(monkeypatch, tmp_path):
    """It is a database password, kept as closely as the deploy that generates it
    keeps the same file."""
    import pathlib as _pathlib
    import stat

    root = _pathlib.Path(general.PROJECT_ROOT)
    source = json.loads((root / "source.example.json").read_text(encoding="utf-8"))

    monkeypatch.setattr(
        general, "load_env", lambda path: {"PUBLIC_HOST": "example.org", "PROTOCOL": "http"}
    )
    monkeypatch.setattr(general, "STUDY_CONFIG_PATH", tmp_path / "studyConfig.json")
    monkeypatch.setattr(general, "IOS_CONFIG_PATH", tmp_path / "aware-config.json")
    monkeypatch.setattr(general, "IOS_ESM_CONFIG_PATH", tmp_path / "esm.json")
    target = tmp_path / "aware-config.android.json"
    monkeypatch.setattr(general, "ANDROID_MICRO_CONFIG_PATH", target)

    general.write_outputs(source)

    assert not stat.S_IMODE(target.stat().st_mode) & (stat.S_IROTH | stat.S_IRGRP)
