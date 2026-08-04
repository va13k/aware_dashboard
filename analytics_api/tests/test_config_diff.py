import copy
import json

import pytest

from app.services import config_diff, study_config

PARTICIPANT_PASSWORD = "participant-secret-9f2a"
DEVICE_PARTICIPANT_PASSWORD = "participant-secret-other-3b7c"
OPENWEATHER_KEY = "owm-key-7d3e"
DEVICE_OPENWEATHER_KEY = "owm-key-different-2a91"


def make_config(
    password=PARTICIPANT_PASSWORD, api_key=OPENWEATHER_KEY, **overrides
) -> dict:
    config = {
        "_id": "config-id-1",
        "createdAt": "2026-01-01T00:00:00.000Z",
        "updatedAt": "2026-02-01T00:00:00.000Z",
        "study_info": {
            "study_title": "Test study",
            "researcher_contact": "researcher@example.test",
        },
        "database": {
            "database_host": "mysql",
            "database_username": "participant",
            "database_password": password,
            "rootPassword": password,
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
            {"setting": "plugin_openweather_api_key", "value": api_key},
        ],
        "ios_sensors": {"significant_motion": True, "mqtt": False},
    }
    config.update(overrides)
    return config


def with_setting(config: dict, setting: str, value) -> dict:
    updated = copy.deepcopy(config)
    for entry in updated["sensors"]:
        if entry["setting"] == setting:
            entry["value"] = value
            return updated
    updated["sensors"].append({"setting": setting, "value": value})
    return updated


def without_setting(config: dict, setting: str) -> dict:
    updated = copy.deepcopy(config)
    updated["sensors"] = [
        entry for entry in updated["sensors"] if entry["setting"] != setting
    ]
    return updated


def paths(diff: config_diff.ConfigDiff) -> list[str]:
    return [row.path for row in diff.rows]


# --- matching configs ------------------------------------------------------


def test_an_identical_config_is_current():
    config = make_config()
    diff = config_diff.compare(config, copy.deepcopy(config))

    assert diff.config_status == config_diff.CURRENT
    assert diff.status_reason is None
    assert diff.rows == []
    assert diff.diff_count == 0


def test_the_phone_reporting_the_config_verbatim_is_current():
    """What the real client does: same settings, same order, same types."""
    config = make_config()
    diff = config_diff.compare(config, json.loads(json.dumps(config)))

    assert diff.config_status == config_diff.CURRENT


def test_a_resave_that_changed_nothing_is_still_current():
    server = make_config(updatedAt="2026-03-01T00:00:00.000Z")
    device = make_config(updatedAt="2026-02-01T00:00:00.000Z")

    diff = config_diff.compare(server, device)

    assert diff.config_status == config_diff.CURRENT
    assert diff.rows == []
    assert diff.server_updated_at == "2026-03-01T00:00:00.000Z"
    assert diff.device_updated_at == "2026-02-01T00:00:00.000Z"


def test_a_reordered_settings_list_is_not_a_difference():
    server = make_config()
    device = copy.deepcopy(server)
    device["sensors"] = list(reversed(device["sensors"]))

    assert config_diff.compare(server, device).config_status == config_diff.CURRENT


# --- differing configs -----------------------------------------------------


def test_a_changed_sampling_frequency_is_reported():
    server = make_config()
    device = with_setting(server, "frequency_accelerometer", 100000)

    diff = config_diff.compare(server, device)
    row = diff.rows[0]

    assert diff.config_status == config_diff.STALE
    assert diff.diff_count == 1
    assert row.path == "sensors.frequency_accelerometer"
    assert row.kind == config_diff.CHANGED
    assert row.server_value == 200000
    assert row.device_value == 100000


def test_a_sensor_enabled_only_on_the_server_is_reported():
    server = with_setting(make_config(), "status_wifi", True)
    device = with_setting(server, "status_wifi", False)

    row = config_diff.compare(server, device).rows[0]

    assert row.path == "sensors.status_wifi"
    assert (row.server_value, row.device_value) == (True, False)


def test_a_setting_the_phone_never_received_is_reported():
    server = make_config()
    device = without_setting(server, "status_accelerometer")

    row = config_diff.compare(server, device).rows[0]

    assert row.path == "sensors.status_accelerometer"
    assert row.kind == config_diff.ONLY_ON_SERVER
    assert row.server_value is True
    assert row.device_value is None


def test_a_setting_only_the_phone_has_is_reported():
    server = make_config()
    device = with_setting(server, "status_from_a_newer_client", True)

    row = config_diff.compare(server, device).rows[0]

    assert row.path == "sensors.status_from_a_newer_client"
    assert row.kind == config_diff.ONLY_ON_DEVICE
    assert row.device_value is True


def test_a_changed_study_title_is_reported_by_path():
    server = make_config()
    device = copy.deepcopy(server)
    device["study_info"]["study_title"] = "An older title"

    row = config_diff.compare(server, device).rows[0]

    assert row.path == "study_info.study_title"
    assert row.server_value == "Test study"
    assert row.device_value == "An older title"


def test_a_changed_question_is_reported_by_index():
    server = make_config()
    device = copy.deepcopy(server)
    device["questions"][0]["esm_title"] = "An older question"

    row = config_diff.compare(server, device).rows[0]

    assert row.path == "questions[0].esm_title"


def test_an_added_question_is_reported_as_server_only():
    server = make_config()
    server["questions"].append({"esm_title": "Question2", "id": 2})
    device = make_config()

    row = config_diff.compare(server, device).rows[0]

    assert row.path == "questions[1]"
    assert row.kind == config_diff.ONLY_ON_SERVER
    assert row.server_value == {"esm_title": "Question2", "id": 2}


def test_a_changed_ios_flag_is_reported():
    server = make_config()
    device = copy.deepcopy(server)
    device["ios_sensors"]["significant_motion"] = False

    row = config_diff.compare(server, device).rows[0]

    assert row.path == "ios_sensors.significant_motion"


def test_a_field_whose_shape_changed_is_reported_as_changed():
    server = make_config()
    device = copy.deepcopy(server)
    device["study_info"] = "a plain string"

    row = config_diff.compare(server, device).rows[0]

    assert row.path == "study_info"
    assert row.kind == config_diff.CHANGED
    assert row.device_value == "a plain string"


def test_every_difference_is_reported_not_just_the_first():
    server = make_config()
    device = with_setting(
        with_setting(server, "status_wifi", True), "status_accelerometer", False
    )
    device["study_info"]["study_title"] = "An older title"

    diff = config_diff.compare(server, device)

    assert diff.diff_count == 3
    assert set(paths(diff)) == {
        "sensors.status_wifi",
        "sensors.status_accelerometer",
        "study_info.study_title",
    }


def test_row_order_is_stable():
    """The UI renders these as a table; the order must not shuffle per request."""
    server = make_config()
    device = with_setting(
        with_setting(server, "status_wifi", True), "status_accelerometer", False
    )

    first = paths(config_diff.compare(server, device))
    second = paths(config_diff.compare(server, device))

    assert first == second
    assert first == sorted(first)


# --- credentials -----------------------------------------------------------


def test_credentials_differing_on_both_sides_produce_no_row():
    server = make_config()
    device = make_config(
        password=DEVICE_PARTICIPANT_PASSWORD, api_key=DEVICE_OPENWEATHER_KEY
    )

    diff = config_diff.compare(server, device)

    assert diff.config_status == config_diff.CURRENT
    assert diff.rows == []


def test_no_credential_reaches_a_diff_row():
    server = make_config()
    device = make_config(
        password=DEVICE_PARTICIPANT_PASSWORD, api_key=DEVICE_OPENWEATHER_KEY
    )
    device["study_info"]["study_title"] = "An older title"

    serialised = json.dumps(config_diff.compare(server, device), default=vars)

    for secret in (
        PARTICIPANT_PASSWORD,
        DEVICE_PARTICIPANT_PASSWORD,
        OPENWEATHER_KEY,
        DEVICE_OPENWEATHER_KEY,
    ):
        assert secret not in serialised


def test_the_public_database_flags_are_still_compared():
    server = make_config()
    device = copy.deepcopy(server)
    device["database"]["require_ssl"] = True

    row = config_diff.compare(server, device).rows[0]

    assert row.path == "database.require_ssl"
    assert (row.server_value, row.device_value) == (False, True)


# --- unknown states --------------------------------------------------------


@pytest.mark.parametrize("device", [None, {}, "not a config", []])
def test_a_phone_that_reported_no_config_is_unknown(device):
    diff = config_diff.compare(make_config(), device)

    assert diff.config_status == config_diff.UNKNOWN
    assert diff.status_reason == config_diff.NO_DEVICE_CONFIG
    assert diff.rows == []
    assert diff.diff_count == 0


@pytest.mark.parametrize("server", [None, {}, "not a config"])
def test_an_undeployed_config_is_unknown(server):
    diff = config_diff.compare(server, make_config())

    assert diff.config_status == config_diff.UNKNOWN
    assert diff.status_reason == config_diff.NO_SERVER_CONFIG
    assert diff.rows == []


def test_an_unknown_state_still_reports_what_it_knows():
    diff = config_diff.compare(None, make_config())

    assert diff.device_updated_at == "2026-02-01T00:00:00.000Z"
    assert diff.server_updated_at is None
    assert diff.device_config_update_enabled is False


# --- the update flag -------------------------------------------------------


def test_the_update_flag_is_read_from_each_side():
    server = with_setting(make_config(), "enable_config_update", True)
    device = make_config()

    diff = config_diff.compare(server, device)

    assert diff.config_update_enabled is True
    assert diff.device_config_update_enabled is False
    # A phone that has not caught up with the flag is itself a difference.
    assert "sensors.enable_config_update" in paths(diff)


@pytest.mark.parametrize("value,expected", [(True, True), ("true", True), (False, False)])
def test_the_update_flag_tolerates_how_it_was_serialised(value, expected):
    server = with_setting(make_config(), "enable_config_update", value)

    assert config_diff.compare(server, make_config()).config_update_enabled is expected


# --- the invariant that keeps the UI honest --------------------------------


@pytest.mark.parametrize(
    "device_factory",
    [
        lambda server: copy.deepcopy(server),
        lambda server: with_setting(server, "status_wifi", True),
        lambda server: without_setting(server, "status_wifi"),
        lambda server: make_config(updatedAt="2020-01-01T00:00:00.000Z"),
        lambda server: make_config(password="another-secret-1234"),
    ],
)
def test_current_means_no_rows_and_stale_means_some(device_factory):
    server = make_config()
    diff = config_diff.compare(server, device_factory(server))

    if diff.config_status == config_diff.CURRENT:
        assert diff.rows == []
    else:
        assert diff.config_status == config_diff.STALE
        assert diff.rows


def test_the_status_agrees_with_the_fingerprint():
    server = make_config()
    device = with_setting(server, "status_wifi", True)

    same = study_config.content_fingerprint(server) == study_config.content_fingerprint(
        device
    )

    assert same is False
    assert config_diff.compare(server, device).config_status == config_diff.STALE


# --- against the deployed config -------------------------------------------


def test_compare_with_deployed_reads_the_deployed_file(
    monkeypatch, tmp_path, deployed_study_config
):
    path = tmp_path / "studyConfig.json"
    path.write_text(json.dumps(deployed_study_config), encoding="utf-8")
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(path))
    study_config.clear_cache()

    diff = config_diff.compare_with_deployed(copy.deepcopy(deployed_study_config))

    assert diff.config_status == config_diff.CURRENT
    assert diff.rows == []
    study_config.clear_cache()


def test_compare_with_deployed_without_a_deployed_config(monkeypatch, tmp_path):
    monkeypatch.setenv(
        study_config.CONFIG_PATH_ENV, str(tmp_path / "studyConfig.json")
    )
    study_config.clear_cache()

    diff = config_diff.compare_with_deployed(make_config())

    assert diff.status_reason == config_diff.NO_SERVER_CONFIG
    study_config.clear_cache()
