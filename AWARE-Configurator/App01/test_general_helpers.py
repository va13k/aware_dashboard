"""Tests for the save-path helpers in App01/general.py.

Covers the pure/near-pure pieces of the hybrid save:
- _participant_credentials: collapsing config_without_password + password
- _merge_and_sync_credentials: MySQL is touched only when credentials change
- _mysql_admin_settings: env / .env resolution and defaults
- write_json: atomic round-trip with no leftover temp files
"""
import json

import pytest

from App01 import general


# --------------------------------------------------------------------------
# _participant_credentials
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "android, expected",
    [
        ({"password": "pw", "config_without_password": False, "require_ssl": False}, ("pw", False)),
        # config_without_password never blanks the account password
        ({"password": "pw", "config_without_password": True, "require_ssl": False}, ("pw", False)),
        ({"password": "pw", "config_without_password": False, "require_ssl": True}, ("pw", True)),
        ({"password": "pw", "config_without_password": True, "require_ssl": True}, ("pw", True)),
        ({}, ("", False)),
    ],
)
def test_participant_credentials(android, expected):
    source = {"database": {"android": android}}
    assert general._participant_credentials(source) == expected


def test_participant_credentials_missing_database():
    assert general._participant_credentials({}) == ("", False)


# --------------------------------------------------------------------------
# _merge_and_sync_credentials: only sync on an effective change
# --------------------------------------------------------------------------

def _source(password="old", passwordless=False, require_ssl=False):
    return {
        "database": {
            "android": {
                "password": password,
                "config_without_password": passwordless,
                "require_ssl": require_ssl,
            }
        }
    }


def test_sync_called_when_password_changes(monkeypatch):
    synced = []

    def fake_update(source, content):
        source["database"]["android"]["password"] = "new"
        return source

    monkeypatch.setattr(general, "update_source_from_android_config", fake_update)
    monkeypatch.setattr(general, "_sync_participant_credentials", synced.append)

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
    monkeypatch.setattr(general, "_sync_participant_credentials", synced.append)

    general._merge_and_sync_credentials(_source(password="secret"), {})
    assert synced == []


def test_sync_called_when_require_ssl_changes(monkeypatch):
    synced = []

    def fake_update(source, content):
        source["database"]["android"]["require_ssl"] = True
        return source

    monkeypatch.setattr(general, "update_source_from_android_config", fake_update)
    monkeypatch.setattr(general, "_sync_participant_credentials", synced.append)

    general._merge_and_sync_credentials(
        _source(password="secret", require_ssl=False), {}
    )
    assert len(synced) == 1


def test_sync_skipped_when_credentials_unchanged(monkeypatch):
    synced = []
    # update leaves the DB block exactly as-is
    monkeypatch.setattr(general, "update_source_from_android_config", lambda s, c: s)
    monkeypatch.setattr(general, "_sync_participant_credentials", synced.append)

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


def _saveable(android_dataflow="webservice", **android_db):
    """A study model shaped enough for the save path to merge into."""
    database = {
        "port": 3306,
        "name": "aware_android",
        "username": "aware_android_participant",
        "password": "stored",
        "require_ssl": False,
        "config_without_password": True,
    }
    database.update(android_db)
    return {
        "deployment": {"dataflow": {"android": android_dataflow, "ios": "webservice"}},
        "database": {"host": "db.internal", "android": database, "ios": {}},
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
        "database": {"database_host": "db.internal", **database},
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


class TestDirectPathSettingsAreHeldOnWebservice:
    """`require_ssl` and `config_without_password` describe a phone opening the
    database itself, so a study whose phones never do must not receive them.

    `require_ssl` is the one that bites: it is applied to the database account,
    and on the webservice path the holder of that account is the micro-server,
    whose client is refused every connection once TLS is demanded of it. The form
    no longer offers either control there, but a browser keeps its own copy of
    that section, so the value still arrives and is stopped here.
    """

    def test_require_ssl_is_ignored_on_the_webservice_path(self):
        source = _saveable("webservice", require_ssl=False)

        _submit(source, require_ssl=True)

        assert source["database"]["android"]["require_ssl"] is False

    def test_require_ssl_is_honoured_on_the_direct_path(self):
        source = _saveable("direct", require_ssl=False)

        _submit(source, require_ssl=True)

        assert source["database"]["android"]["require_ssl"] is True

    def test_config_without_password_is_held_on_the_webservice_path(self):
        source = _saveable("webservice", config_without_password=True)

        _submit(source, config_without_password=False)

        assert source["database"]["android"]["config_without_password"] is True

    def test_a_password_change_still_reaches_the_account(self):
        """The credential the micro-server authenticates with stays rotatable."""
        source = _saveable("webservice", password="stored")

        _submit(source, database_password="rotated")

        assert source["database"]["android"]["password"] == "rotated"
