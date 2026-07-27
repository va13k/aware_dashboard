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
        # passwordless => empty effective password, stored value ignored
        ({"password": "pw", "config_without_password": True, "require_ssl": False}, ("", False)),
        ({"password": "pw", "config_without_password": False, "require_ssl": True}, ("pw", True)),
        ({"password": "pw", "config_without_password": True, "require_ssl": True}, ("", True)),
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


def test_sync_called_when_toggling_passwordless(monkeypatch):
    synced = []

    def fake_update(source, content):
        source["database"]["android"]["config_without_password"] = True
        return source

    monkeypatch.setattr(general, "update_source_from_android_config", fake_update)
    monkeypatch.setattr(general, "_sync_participant_credentials", synced.append)

    # Password unchanged, but flipping passwordless changes the effective creds.
    general._merge_and_sync_credentials(_source(password="secret"), {})
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
