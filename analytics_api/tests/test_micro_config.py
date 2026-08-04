import json
import os
import pathlib

import pytest

from app.services import micro_config

DATABASE_PASSWORD = "micro-db-secret-4f81"
DATABASE_USER = "micro-db-user-9c2"
MQTT_PASSWORD = "mqtt-secret-7b3d"
FITBIT_KEY = "fitbit-key-1a5e"

CREDENTIALS = (DATABASE_PASSWORD, DATABASE_USER, MQTT_PASSWORD, FITBIT_KEY)


@pytest.fixture(autouse=True)
def _clear_cache():
    micro_config.clear_cache()
    yield
    micro_config.clear_cache()


@pytest.fixture
def config() -> dict:
    """Shaped like aware-config.json: grouped settings with string values."""
    return {
        "server": {
            "database_host": "mysql",
            "database_name": "aware_ios",
            "database_user": DATABASE_USER,
            "database_pwd": DATABASE_PASSWORD,
            "server_port": "8080",
        },
        "study": {
            "study_key": 1,
            "study_name": "Test study",
            "researcher_contact": "researcher@example.test",
        },
        "sensors": [
            {
                "sensor": "accelerometer",
                "title": "Accelerometer",
                "settings": [
                    {"setting": "status_accelerometer", "value": "true"},
                    {"setting": "frequency_accelerometer", "value": "20000"},
                ],
            },
            {
                "sensor": "communication",
                "settings": [{"setting": "status_calls", "value": "false"}],
            },
            {
                "sensor": "webservice",
                "settings": [{"setting": "mqtt_password", "value": MQTT_PASSWORD}],
            },
        ],
        "plugins": [
            {
                "plugin": "plugin_fitbit",
                "settings": [
                    {"setting": "status_plugin_fitbit", "value": "true"},
                    {"setting": "api_key_plugin_fitbit", "value": FITBIT_KEY},
                ],
            }
        ],
    }


def write_config(path: pathlib.Path, config: dict, mtime_ns: int) -> None:
    path.write_text(json.dumps(config), encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))


def assert_no_credentials(value):
    serialised = json.dumps(value, default=str)
    for secret in CREDENTIALS:
        assert secret not in serialised, f"{secret} leaked"


# --- reading the settings --------------------------------------------------


def test_sensor_and_plugin_settings_are_flattened_together(config):
    settings = micro_config.settings_map(config)

    assert settings["status_accelerometer"] == "true"
    assert settings["frequency_accelerometer"] == "20000"
    assert settings["status_calls"] == "false"
    assert settings["status_plugin_fitbit"] == "true"


def test_the_server_and_study_blocks_are_not_read(config):
    settings = micro_config.settings_map(config)

    assert_no_credentials(settings)
    assert "database_host" not in settings
    assert "study_name" not in settings
    assert "researcher_contact" not in settings


def test_secret_settings_are_dropped(config):
    settings = micro_config.settings_map(config)

    assert "mqtt_password" not in settings
    assert "api_key_plugin_fitbit" not in settings


@pytest.mark.parametrize(
    "broken",
    [
        {},
        {"sensors": None, "plugins": None},
        {"sensors": ["not a group"], "plugins": [{"settings": "not a list"}]},
        {"sensors": [{"settings": [{"value": "no name"}, {"setting": ""}]}]},
    ],
)
def test_malformed_sections_are_skipped(broken):
    assert micro_config.settings_map(broken) == {}


# --- the loader ------------------------------------------------------------


def test_the_path_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv(micro_config.CONFIG_PATH_ENV, "/somewhere/aware-config.json")

    assert micro_config.config_path() == pathlib.Path("/somewhere/aware-config.json")


def test_load_returns_none_when_the_config_is_absent(monkeypatch, tmp_path):
    monkeypatch.setenv(
        micro_config.CONFIG_PATH_ENV, str(tmp_path / "aware-config.json")
    )

    assert micro_config.load_micro_config() is None


def test_load_returns_none_for_an_unparseable_config(monkeypatch, tmp_path):
    path = tmp_path / "aware-config.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(micro_config.CONFIG_PATH_ENV, str(path))

    assert micro_config.load_micro_config() is None


def test_load_hands_out_settings_without_credentials(monkeypatch, tmp_path, config):
    path = tmp_path / "aware-config.json"
    write_config(path, config, 1_000_000_000_000_000_000)
    monkeypatch.setenv(micro_config.CONFIG_PATH_ENV, str(path))

    loaded = micro_config.load_micro_config()

    assert loaded is not None
    assert loaded.settings["status_accelerometer"] == "true"
    assert_no_credentials(loaded)


def test_load_picks_up_a_rewritten_config(monkeypatch, tmp_path, config):
    path = tmp_path / "aware-config.json"
    write_config(path, config, 1_000_000_000_000_000_000)
    monkeypatch.setenv(micro_config.CONFIG_PATH_ENV, str(path))
    before = micro_config.load_micro_config()

    config["sensors"][1]["settings"][0]["value"] = "true"
    write_config(path, config, 2_000_000_000_000_000_000)
    after = micro_config.load_micro_config()

    assert before.settings["status_calls"] == "false"
    assert after.settings["status_calls"] == "true"


def test_load_is_cached_between_calls(monkeypatch, tmp_path, config):
    path = tmp_path / "aware-config.json"
    write_config(path, config, 1_000_000_000_000_000_000)
    monkeypatch.setenv(micro_config.CONFIG_PATH_ENV, str(path))

    assert micro_config.load_micro_config() is micro_config.load_micro_config()


# --- the real config -------------------------------------------------------


def test_the_deployed_micro_config_reads_without_leaking(monkeypatch, project_root):
    path = project_root / "aware-micro-server" / "aware-config.json"
    if not path.exists():
        pytest.skip("aware-config.json is only present after deployment")

    raw = json.loads(path.read_text(encoding="utf-8"))
    real_secrets = [
        str(value)
        for key, value in (raw.get("server") or {}).items()
        if ("pwd" in key or "user" in key) and str(value)
    ]

    monkeypatch.setenv(micro_config.CONFIG_PATH_ENV, str(path))
    loaded = micro_config.load_micro_config()

    assert loaded is not None
    assert loaded.settings
    serialised = json.dumps(loaded.settings, default=str)
    for secret in real_secrets:
        assert secret not in serialised
