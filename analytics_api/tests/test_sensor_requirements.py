import json
import pathlib
import re

import pytest

from app.services import micro_config, sensor_requirements, study_config

ANDROID = sensor_requirements.ANDROID
IOS = sensor_requirements.IOS


@pytest.fixture(autouse=True)
def _clear_caches():
    study_config.clear_cache()
    micro_config.clear_cache()
    yield
    study_config.clear_cache()
    micro_config.clear_cache()


@pytest.fixture(scope="session")
def micro_server_config_path(project_root) -> pathlib.Path:
    return project_root / "aware-micro-server" / "aware-config.json"


@pytest.fixture(scope="session")
def micro_server_config(micro_server_config_path) -> dict:
    if not micro_server_config_path.exists():
        pytest.skip("aware-config.json is only present after deployment")
    return json.loads(micro_server_config_path.read_text(encoding="utf-8"))


def requirement(result, sensor_key):
    return next(
        (item for item in result.sensors if item.sensor_key == sensor_key), None
    )


def required_keys(result) -> set[str]:
    return {item.sensor_key for item in result.sensors if item.required}


# --- the mapping tables ----------------------------------------------------


def _routed_keys(path: pathlib.Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r'@router\.get\(\s*"/([a-z0-9/_-]+)"', text)) - {"export"}


@pytest.mark.parametrize(
    "table,router",
    [
        (sensor_requirements.ANDROID_SETTING_STREAMS, "android.py"),
        (sensor_requirements.IOS_SETTING_STREAMS, "ios.py"),
    ],
)
def test_every_mapped_stream_is_a_real_endpoint(project_root, table, router):
    """A stream key the API cannot serve would show as permanently empty."""
    routed = _routed_keys(project_root / "analytics_api" / "app" / "routers" / router)
    mapped = {key for keys in table.values() for key in keys}

    assert mapped - routed == set()


def test_the_android_table_covers_the_deployed_config(deployed_study_config):
    settings = {
        entry["setting"]
        for entry in deployed_study_config["sensors"]
        if entry["setting"].startswith(sensor_requirements.STATUS_PREFIX)
    }

    assert settings - set(sensor_requirements.ANDROID_SETTING_STREAMS) == set()


def test_the_ios_table_covers_the_micro_config(micro_server_config):
    settings = {
        entry["setting"]
        for group in micro_server_config["sensors"] + micro_server_config["plugins"]
        for entry in group.get("settings", [])
        if entry["setting"].startswith(sensor_requirements.STATUS_PREFIX)
    }

    assert settings - set(sensor_requirements.IOS_SETTING_STREAMS) == set()


# --- deriving requirements -------------------------------------------------


def test_an_enabled_setting_makes_its_stream_required():
    result = sensor_requirements.requirements_for(
        ANDROID, {"status_wifi": True, "status_bluetooth": False}
    )

    assert requirement(result, "wifi").required is True
    assert requirement(result, "bluetooth").required is False
    assert result.required_sensor_count == 1
    assert result.available is True


def test_one_setting_can_require_several_streams():
    result = sensor_requirements.requirements_for(ANDROID, {"status_battery": True})

    assert required_keys(result) == {"battery", "battery-charges", "battery-discharges"}


def test_any_of_several_settings_can_require_one_stream():
    """Three location providers write to one table; one of them is enough."""
    result = sensor_requirements.requirements_for(
        ANDROID,
        {
            "status_location_gps": False,
            "status_location_network": True,
            "status_location_passive": False,
        },
    )
    locations = requirement(result, "locations")

    assert locations.required is True
    assert locations.settings == [
        "status_location_gps",
        "status_location_network",
        "status_location_passive",
    ]


def test_a_stream_reports_every_setting_that_governs_it():
    result = sensor_requirements.requirements_for(ANDROID, {"status_calls": True})

    assert requirement(result, "calls").settings == [
        "status_calls",
        "status_communication_events",
    ]


def test_settings_are_read_as_the_config_serialises_them():
    """The micro-server config stores its values as strings."""
    result = sensor_requirements.requirements_for(
        IOS, {"status_wifi": "true", "status_bluetooth": "false"}
    )

    assert required_keys(result) == {"wifi"}


def test_a_setting_the_config_omits_is_not_required():
    result = sensor_requirements.requirements_for(ANDROID, {"status_wifi": True})

    assert requirement(result, "bluetooth").required is False


# --- what has no stream ----------------------------------------------------


def test_an_enabled_setting_with_no_stream_is_reported():
    result = sensor_requirements.requirements_for(
        ANDROID, {"status_mqtt": True, "status_plugin_fitbit": True}
    )

    assert result.required_without_stream == [
        "status_mqtt",
        "status_plugin_fitbit",
    ]
    assert requirement(result, "mqtt") is None


def test_a_disabled_setting_with_no_stream_is_not_reported():
    result = sensor_requirements.requirements_for(ANDROID, {"status_processor": False})

    assert result.required_without_stream == []


def test_an_unknown_setting_is_reported_rather_than_dropped():
    result = sensor_requirements.requirements_for(
        ANDROID, {"status_from_a_newer_client": True, "frequency_wifi": 300}
    )

    assert result.unmapped_settings == ["status_from_a_newer_client"]


def test_a_stream_with_no_governing_setting_is_absent_from_the_response():
    result = sensor_requirements.requirements_for(ANDROID, {"status_wifi": True})

    assert requirement(result, "aware_log") is None
    assert requirement(result, "fused-location") is None


# --- platforms -------------------------------------------------------------


def test_the_two_platforms_have_different_streams():
    """The same setting can reach a stream on one platform and none on the other."""
    android = sensor_requirements.requirements_for(
        ANDROID, {"status_keyboard": True, "status_plugin_contacts": True}
    )
    ios = sensor_requirements.requirements_for(
        IOS, {"status_keyboard": True, "status_plugin_contacts": True}
    )

    assert required_keys(android) == {"keyboard"}
    assert required_keys(ios) == {"contacts"}


def test_a_setting_both_platforms_serve_is_required_on_both():
    """Processor has a table and a route on each side."""
    for platform in (ANDROID, IOS):
        result = sensor_requirements.requirements_for(
            platform, {"status_processor": True}
        )
        assert required_keys(result) == {"processor"}


def test_screenshots_are_required_when_the_study_asks_for_them():
    result = sensor_requirements.requirements_for(ANDROID, {"status_screenshot": True})
    assert required_keys(result) == {"screenshot"}
    assert result.required_without_stream == []


def test_an_absent_config_reports_nothing_rather_than_no_requirements():
    result = sensor_requirements.requirements_for(ANDROID, None)

    assert result.available is False
    assert result.sensors == []
    assert result.required_sensor_count == 0


def test_an_unknown_platform_is_a_programming_error():
    with pytest.raises(ValueError):
        sensor_requirements.requirements_for("windows-phone", {})


# --- both configs together -------------------------------------------------


def test_study_requirements_reads_both_configs(
    monkeypatch, deployed_study_config_path, micro_server_config_path
):
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(deployed_study_config_path))
    monkeypatch.setenv(micro_config.CONFIG_PATH_ENV, str(micro_server_config_path))
    if not deployed_study_config_path.exists() or not micro_server_config_path.exists():
        pytest.skip("both configs are only present after deployment")

    result = sensor_requirements.study_requirements()

    assert result[ANDROID].available is True
    assert result[IOS].available is True
    assert result[ANDROID].required_sensor_count > 0
    assert result[ANDROID].unmapped_settings == []
    assert result[IOS].unmapped_settings == []


def test_study_requirements_without_either_config(monkeypatch, tmp_path):
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(tmp_path / "study.json"))
    monkeypatch.setenv(micro_config.CONFIG_PATH_ENV, str(tmp_path / "micro.json"))

    result = sensor_requirements.study_requirements()

    assert result[ANDROID].available is False
    assert result[IOS].available is False
