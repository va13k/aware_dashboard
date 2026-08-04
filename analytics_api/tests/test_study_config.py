import copy
import json
import os
import pathlib

import pytest

from app.services import study_config

# Distinctive values so an assertion that one of them leaked cannot pass or fail
# by accident on a common substring.
PARTICIPANT_PASSWORD = "participant-secret-9f2a"
ROOT_PASSWORD = "root-secret-4c81"
ROOT_USERNAME = "root-admin-a1"
PARTICIPANT_USERNAME = "participant-user-b2"
OPENWEATHER_KEY = "owm-key-7d3e"
MQTT_PASSWORD = "mqtt-secret-5b6f"
MQTT_USERNAME = "mqtt-user-c9"

CREDENTIALS = (
    PARTICIPANT_PASSWORD,
    ROOT_PASSWORD,
    ROOT_USERNAME,
    PARTICIPANT_USERNAME,
    OPENWEATHER_KEY,
    MQTT_PASSWORD,
    MQTT_USERNAME,
)


@pytest.fixture(autouse=True)
def _clear_config_cache():
    study_config.clear_cache()
    yield
    study_config.clear_cache()


@pytest.fixture
def config() -> dict:
    """Shaped like a real deployed config, including its credentials."""
    return {
        "_id": "config-id-1",
        "createdAt": "2026-01-01T00:00:00.000Z",
        "updatedAt": "2026-02-01T00:00:00.000Z",
        "study_info": {
            "study_title": "Test study",
            "researcher_contact": "researcher@example.test",
        },
        "database": {
            "database_host": "mysql",
            "database_port": "3306",
            "database_name": "aware_android",
            "database_username": PARTICIPANT_USERNAME,
            "database_password": PARTICIPANT_PASSWORD,
            "rootUsername": ROOT_USERNAME,
            "rootPassword": ROOT_PASSWORD,
            "config_without_password": True,
            "require_ssl": False,
        },
        "questions": [{"esm_title": "Question1", "id": 1}],
        "schedules": [{"title": "Schedule1", "questions": [1]}],
        "sensors": [
            {"setting": "enable_config_update", "value": False},
            {"setting": "status_accelerometer", "value": True},
            {"setting": "frequency_accelerometer", "value": 200000},
            {"setting": "status_wifi", "value": False},
            {"setting": "status_plugin_ambient_noise", "value": True},
            {"setting": "status_plugin_openweather", "value": False},
            {"setting": "plugin_openweather_api_key", "value": OPENWEATHER_KEY},
            {"setting": "mqtt_server", "value": "broker.example.test"},
            {"setting": "mqtt_username", "value": MQTT_USERNAME},
            {"setting": "mqtt_password", "value": MQTT_PASSWORD},
            # Both carry a "key" substring while being ordinary settings.
            {"setting": "status_keyboard", "value": True},
            {"setting": "mask_keyboard", "value": False},
        ],
        "ios_sensors": {"significant_motion": True, "mqtt": False},
    }


def _serialised(value) -> str:
    return json.dumps(value, default=str)


def assert_no_credentials(value, secrets=CREDENTIALS):
    serialised = _serialised(value)
    for secret in secrets:
        assert secret not in serialised, f"{secret} leaked"


# --- redaction -------------------------------------------------------------


def test_redaction_removes_every_credential(config):
    assert_no_credentials(study_config.redact(config))


def test_redaction_keeps_what_a_researcher_needs(config):
    safe = study_config.redact(config)
    settings = study_config.settings_map(config)

    assert safe["_id"] == "config-id-1"
    assert safe["updatedAt"] == "2026-02-01T00:00:00.000Z"
    assert safe["study_info"]["study_title"] == "Test study"
    assert safe["database"] == {"config_without_password": True, "require_ssl": False}
    assert safe["questions"] == config["questions"]
    assert settings["mqtt_server"] == "broker.example.test"
    # The marker list must not swallow settings that merely contain "key".
    assert settings["status_keyboard"] is True
    assert settings["mask_keyboard"] is False


def test_redaction_is_idempotent(config):
    once = study_config.redact(config)

    assert study_config.redact(once) == once


def test_redaction_does_not_mutate_its_input(config):
    original = copy.deepcopy(config)
    study_config.redact(config)

    assert config == original


def test_redaction_reaches_nested_structures():
    nested = {
        "level_one": {
            "level_two": [{"database_password": "leak-1"}, {"safe": "kept"}],
            "api_key_plugin_fitbit": "leak-2",
        }
    }
    safe = study_config.redact(nested)

    assert_no_credentials(safe, ("leak-1", "leak-2"))
    assert safe["level_one"]["level_two"] == [{}, {"safe": "kept"}]


@pytest.mark.parametrize(
    "name",
    [
        "database_password",
        "rootPassword",
        "rootUsername",
        "database_username",
        "mqtt_password",
        "plugin_openweather_api_key",
        "api_secret_plugin_fitbit",
        "access_token",
        "aws_credentials",
    ],
)
def test_secret_key_names_are_recognised(name):
    assert study_config.is_secret_key(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "status_keyboard",
        "mask_keyboard",
        "config_without_password",
        "require_ssl",
        "frequency_accelerometer",
        "mqtt_server",
    ],
)
def test_ordinary_settings_are_not_treated_as_secret(name):
    assert study_config.is_secret_key(name) is False


# --- fingerprint -----------------------------------------------------------


def test_fingerprint_ignores_key_order_and_formatting(config):
    reordered = json.loads(
        json.dumps(dict(reversed(list(config.items()))), indent=4)
    )
    reordered["sensors"] = list(reversed(reordered["sensors"]))

    assert study_config.content_fingerprint(reordered) == (
        study_config.content_fingerprint(config)
    )


def test_fingerprint_ignores_a_resave_that_changed_nothing(config):
    resaved = copy.deepcopy(config)
    resaved["updatedAt"] = "2026-03-01T00:00:00.000Z"
    resaved["createdAt"] = "2026-02-28T00:00:00.000Z"

    assert study_config.content_fingerprint(resaved) == (
        study_config.content_fingerprint(config)
    )


def test_fingerprint_matches_a_copy_that_omits_credentials(config):
    """The comparability property that forces redaction to come first."""
    without_secrets = copy.deepcopy(config)
    without_secrets["database"] = {
        "config_without_password": True,
        "require_ssl": False,
    }
    without_secrets["sensors"] = [
        entry
        for entry in without_secrets["sensors"]
        if entry["setting"]
        not in {"plugin_openweather_api_key", "mqtt_username", "mqtt_password"}
    ]

    assert study_config.content_fingerprint(without_secrets) == (
        study_config.content_fingerprint(config)
    )


@pytest.mark.parametrize(
    "setting,value",
    [
        ("status_accelerometer", False),
        ("frequency_accelerometer", 100000),
        ("enable_config_update", True),
    ],
)
def test_fingerprint_changes_when_a_setting_changes(config, setting, value):
    changed = copy.deepcopy(config)
    for entry in changed["sensors"]:
        if entry["setting"] == setting:
            entry["value"] = value

    assert study_config.content_fingerprint(changed) != (
        study_config.content_fingerprint(config)
    )


def test_fingerprint_changes_when_a_question_changes(config):
    changed = copy.deepcopy(config)
    changed["questions"][0]["esm_title"] = "Question2"

    assert study_config.content_fingerprint(changed) != (
        study_config.content_fingerprint(config)
    )


# --- settings and flags ----------------------------------------------------


def test_settings_map_skips_malformed_entries(config):
    config["sensors"].extend(
        ["not-a-dict", {"value": "no setting name"}, {"setting": "", "value": 1}]
    )
    settings = study_config.settings_map(config)

    assert "" not in settings
    assert settings["status_accelerometer"] is True


def test_settings_map_keeps_the_last_value_of_a_repeated_setting(config):
    config["sensors"].append({"setting": "status_wifi", "value": True})

    assert study_config.settings_map(config)["status_wifi"] is True


def test_settings_map_omits_secret_settings(config):
    settings = study_config.settings_map(config)

    assert "plugin_openweather_api_key" not in settings
    assert "mqtt_password" not in settings


def test_ios_settings_map(config):
    assert study_config.ios_settings_map(config) == {
        "significant_motion": True,
        "mqtt": False,
    }


def test_ios_settings_map_tolerates_a_missing_section():
    assert study_config.ios_settings_map({}) == {}


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        (1, True),
        (2.5, True),
        (False, False),
        ("false", False),
        ("", False),
        (0, False),
        (None, False),
        ([], False),
    ],
)
def test_is_enabled(value, expected):
    assert study_config.is_enabled(value) is expected


# --- summary ---------------------------------------------------------------


def test_safe_summary_reports_the_version_and_counts(config):
    summary = study_config.safe_summary(config)

    assert summary["config_id"] == "config-id-1"
    assert summary["config_updated_at"] == "2026-02-01T00:00:00.000Z"
    assert summary["study_title"] == "Test study"
    assert summary["config_fingerprint"] == study_config.content_fingerprint(config)
    assert summary["require_ssl"] is False
    assert summary["config_without_password"] is True
    assert summary["config_update_enabled"] is False
    # status_accelerometer and status_keyboard, not the two plugin flags.
    assert summary["enabled_sensor_count"] == 2
    assert summary["enabled_plugin_count"] == 1


def test_safe_summary_never_carries_a_credential(config):
    assert_no_credentials(study_config.safe_summary(config))


def test_safe_summary_tolerates_an_empty_config():
    summary = study_config.safe_summary({})

    assert summary["config_id"] is None
    assert summary["study_title"] is None
    assert summary["enabled_sensor_count"] == 0


# --- loader ----------------------------------------------------------------


def _write_config(path: pathlib.Path, config: dict, mtime_ns: int) -> None:
    path.write_text(json.dumps(config), encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))


def test_config_path_prefers_the_environment(monkeypatch):
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, "/somewhere/studyConfig.json")

    assert study_config.config_path() == pathlib.Path("/somewhere/studyConfig.json")


def test_config_path_falls_back_to_the_container_path(monkeypatch):
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, "   ")

    assert study_config.config_path() == study_config.DEFAULT_CONFIG_PATH


def test_load_returns_none_when_the_config_was_never_deployed(monkeypatch, tmp_path):
    monkeypatch.setenv(
        study_config.CONFIG_PATH_ENV, str(tmp_path / "studyConfig.json")
    )

    assert study_config.load_deployed_config() is None


def test_load_returns_none_for_an_unparseable_config(monkeypatch, tmp_path):
    path = tmp_path / "studyConfig.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(path))

    assert study_config.load_deployed_config() is None


def test_load_returns_none_when_the_config_is_not_an_object(monkeypatch, tmp_path):
    path = tmp_path / "studyConfig.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(path))

    assert study_config.load_deployed_config() is None


def test_load_hands_out_a_redacted_config(monkeypatch, tmp_path, config):
    path = tmp_path / "studyConfig.json"
    _write_config(path, config, 1_000_000_000_000_000_000)
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(path))

    deployed = study_config.load_deployed_config()

    assert deployed is not None
    assert_no_credentials(deployed.config)
    assert_no_credentials(deployed.settings)
    assert_no_credentials(deployed.summary)
    assert deployed.fingerprint == study_config.content_fingerprint(config)
    assert deployed.settings["status_accelerometer"] is True
    assert deployed.ios_settings == {"significant_motion": True, "mqtt": False}


def test_load_is_cached_between_calls(monkeypatch, tmp_path, config):
    path = tmp_path / "studyConfig.json"
    _write_config(path, config, 1_000_000_000_000_000_000)
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(path))

    first = study_config.load_deployed_config()
    second = study_config.load_deployed_config()

    assert first is second


def test_load_picks_up_a_rewritten_config(monkeypatch, tmp_path, config):
    path = tmp_path / "studyConfig.json"
    _write_config(path, config, 1_000_000_000_000_000_000)
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(path))
    before = study_config.load_deployed_config()

    changed = copy.deepcopy(config)
    for entry in changed["sensors"]:
        if entry["setting"] == "status_wifi":
            entry["value"] = True
    _write_config(path, changed, 2_000_000_000_000_000_000)
    after = study_config.load_deployed_config()

    assert before is not None and after is not None
    assert after.fingerprint != before.fingerprint
    assert after.settings["status_wifi"] is True


def test_load_recovers_after_the_config_is_repaired(monkeypatch, tmp_path, config):
    path = tmp_path / "studyConfig.json"
    path.write_text("{broken", encoding="utf-8")
    os.utime(path, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(path))

    assert study_config.load_deployed_config() is None

    _write_config(path, config, 2_000_000_000_000_000_000)

    assert study_config.load_deployed_config() is not None


# --- the real deployed config ---------------------------------------------


def _secret_key_names(value) -> set[str]:
    """Every secret-named key or setting anywhere in a config."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if study_config.is_secret_key(key):
                found.add(str(key))
            if key == "setting" and study_config.is_secret_key(item):
                found.add(str(item))
            found |= _secret_key_names(item)
    elif isinstance(value, list):
        for item in value:
            found |= _secret_key_names(item)
    return found


def _secret_values(value) -> set[str]:
    """Secret values worth searching a response for.

    Short values are skipped: this deployment writes "-" into the password
    fields because the client fetches credentials separately, and a one-character
    needle matches any hyphen in a UUID. The key-name check below is what covers
    those fields; this one covers the credentials that are really there.
    """
    return {
        str(item)
        for name, item in _secret_pairs(value)
        if isinstance(item, (str, int, float)) and len(str(item)) >= 8
    }


def _secret_pairs(value):
    if isinstance(value, dict):
        if "setting" in value:
            if study_config.is_secret_key(value.get("setting")):
                yield str(value.get("setting")), value.get("value")
            return
        for key, item in value.items():
            if study_config.is_secret_key(key):
                yield str(key), item
            else:
                yield from _secret_pairs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _secret_pairs(item)


def test_the_deployed_config_carries_secrets_worth_redacting(deployed_study_config):
    """Guards the test below from passing because it had nothing to find."""
    assert _secret_key_names(deployed_study_config)
    assert _secret_values(deployed_study_config)


def test_the_deployed_config_summarises_without_leaking(
    monkeypatch, deployed_study_config_path, deployed_study_config
):
    real_secrets = tuple(_secret_values(deployed_study_config))

    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(deployed_study_config_path))
    deployed = study_config.load_deployed_config()

    assert deployed is not None
    for value in (deployed.config, deployed.settings, deployed.summary):
        assert_no_credentials(value, real_secrets)
        # Placeholder-valued credentials leave no searchable string behind, so
        # the field itself has to be gone.
        assert _secret_key_names(value) == set()

    assert deployed.summary["config_id"]
    assert deployed.summary["config_updated_at"]
    assert deployed.summary["enabled_sensor_count"] > 0
    assert len(deployed.fingerprint) == 64


def test_redaction_leaves_no_secret_field_behind(config):
    assert _secret_key_names(study_config.redact(config)) == set()
    assert _secret_key_names(study_config.safe_summary(config)) == set()
    assert _secret_key_names(config), "the fixture should carry secrets"
