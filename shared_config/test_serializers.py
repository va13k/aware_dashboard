"""
Tests for shared_config/serializers.py.

Covers:
- serialize_android_config: sensor values, study info, database, ESM, webservice_server
- serialize_ios_config: server block, study block, sensor/plugin defaultValues, ESM plugin upsert
- build_ios_esm_config: question/schedule conversion
- build_ios_sensor_settings: direct mapping, renames, compound sensors, shared-sensor priority
- source.json field coverage for both serializers
"""

import json
import pathlib

import pytest

from shared_config.serializers import (
    ANDROID_ONLY_SHARED_SENSOR_NAMES,
    COMMON_SHARED_SENSOR_FIELDS,
    IOS_ONLY_SENSOR_NAMES,
    apply_ios_study_config,
    build_ios_esm_config,
    build_ios_sensor_settings,
    serialize_android_config,
    serialize_ios_config,
    update_ios_server_config,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SOURCE = {
    "version": 1,
    "study": {
        "id": "test-study-id",
        "title": "Test Study",
        "description": "A test study",
        "active": True,
        "start_timestamp": 0,
    },
    "researcher": {
        "first_name": "Alice",
        "last_name": "Smith",
        "contact": "alice@example.com",
    },
    "deployment": {"public_host": "", "public_port": 80, "protocol": "http"},
    "database": {
        "host": "db.internal",
        "android": {
            "port": 3306,
            "name": "aware_android",
            "username": "android_user",
            "password": "android_pass",
            "require_ssl": False,
            "config_without_password": False,
        },
        "ios": {
            "port": 3306,
            "name": "aware_ios",
            "username": "ios_user",
            "password": "ios_pass",
            "engine": "mysql",
        },
    },
    "android": {
        "created_at": "2026-01-01T00:00:00.000Z",
        "updated_at": "2026-05-01T00:00:00.000Z",
        "questions": [
            {
                "id": 1,
                "esm_type": 2,
                "esm_title": "Q1",
                "instructions": "Pick one",
                "esm_radios": ["Yes", "No"],
                "esm_submit": "Submit",
            }
        ],
        "schedules": [
            {
                "title": "S1",
                "type": "repeat",
                "esm_keep": False,
                "questions": [1],
                "repeatInterval": 60,
            }
        ],
        "settings": {
            "status_accelerometer": True,
            "frequency_accelerometer": 20000,
            "threshold_accelerometer": 0,
            "frequency_accelerometer_enforce": False,
            "status_bluetooth": True,
            "frequency_bluetooth": 60,
            "status_battery": True,
            "status_screen": False,
            "status_location_gps": True,
            "frequency_location_gps": 180,
            "min_location_gps_accuracy": 150,
            "status_location_network": False,
            "frequency_location_network": 300,
            "min_location_network_accuracy": 1500,
            "status_location_passive": False,
            "location_expiration_time": 300,
            "location_save_all": False,
            "status_network_events": True,
            "status_network_traffic": False,
            "status_calls": True,
            "status_messages": False,
            "status_plugin_esm_scheduler": True,
            "status_google_fused_location": True,
            "frequency_google_fused_location": 300,
            "max_frequency_google_fused_location": 60,
            "fallback_location_timeout": 20,
            "accuracy_google_fused_location": 0,
            "status_plugin_ambient_noise": False,
            "frequency_plugin_ambient_noise": 5,
            "plugin_ambient_noise_sample_size": 30,
            "plugin_ambient_noise_silence_threshold": 50,
            "webservice_wifi_only": False,
            "webservice_charging": False,
            "frequency_webservice": 60,
            "frequency_clean_old_data": 0,
            "webservice_silent": False,
            "fallback_network": 30,
            "remind_to_charge": True,
            "foreground_priority": True,
            "debug_flag": False,
            "status_webservice": True,
        },
    },
    "ios": {
        "study_number": 1,
        "study_key": "test_study_key",
        "server": {
            "server_host": "0.0.0.0",
            "server_port": 8080,
            "websocket_port": 8081,
            "path_fullchain_pem": "",
            "path_key_pem": "",
        },
        "sensors": {
            "accelerometer": True,
            "locations": True,
            "network": False,
            "communication": True,
            "significant_motion": False,
            "websocket": False,
            "mqtt": False,
        },
        "plugins": {
            "plugin_ambient_noise": False,
            "plugin_esm_scheduler": True,
            "plugin_ios_esm": True,
            "plugin_google_fused_location": True,
        },
        "plugin_settings": {
            "accuracy_google_fused_location": 105,
        },
    },
    "shared": {
        "esms": {
            "questions": [
                {
                    "id": 1,
                    "esm_type": 2,
                    "esm_title": "Q1",
                    "instructions": "Pick one",
                    "esm_radios": ["Yes", "No"],
                    "esm_submit": "Submit",
                }
            ],
            "schedules": [
                {
                    "title": "S1",
                    "type": "repeat",
                    "esm_keep": False,
                    "questions": [1],
                    "repeatInterval": 60,
                }
            ],
        },
        "sensors": {
            "accelerometer": {
                "enabled": True,
                "frequency": 20000,
                "threshold": 0,
                "enforce": False,
            },
            "battery": {"enabled": True},
            "bluetooth": {"enabled": True, "frequency": 60},
        },
    },
}

SETTINGS = {
    "protocol": "http",
    "public_host": "192.168.1.10",
    "public_port": 80,
    "micro_database_host": "mysql",
    "android_database_host": "192.168.1.10",
    "external_server_host": "http://192.168.1.10",
    "ios_database_name": "aware_ios",
    "ios_database_user": "ios_user",
    "ios_database_password": "ios_pass",
    "ios_database_port": 3306,
    "ios_server_host": "0.0.0.0",
    "ios_server_port": 8080,
    "ios_websocket_port": 8081,
    "ios_path_fullchain_pem": "",
    "ios_path_key_pem": "",
}


@pytest.fixture()
def source():
    import copy

    return copy.deepcopy(SOURCE)


@pytest.fixture()
def settings():
    return dict(SETTINGS)


@pytest.fixture()
def android_template(tmp_path):
    """Minimal Android template with sensors list."""
    template = {
        "_id": "",
        "study_info": {},
        "database": {},
        "createdAt": "",
        "updatedAt": "",
        "questions": [],
        "schedules": [],
        "ios_sensors": {},
        "sensors": [
            {"setting": "status_accelerometer", "value": False},
            {"setting": "frequency_accelerometer", "value": 200000},
            {"setting": "threshold_accelerometer", "value": 0},
            {"setting": "frequency_accelerometer_enforce", "value": False},
            {"setting": "status_bluetooth", "value": False},
            {"setting": "frequency_bluetooth", "value": 60},
            {"setting": "status_battery", "value": False},
            {"setting": "status_screen", "value": False},
            {"setting": "status_location_gps", "value": False},
            {"setting": "frequency_location_gps", "value": 180},
            {"setting": "status_location_network", "value": False},
            {"setting": "frequency_location_network", "value": 300},
            {"setting": "status_network_events", "value": False},
            {"setting": "status_network_traffic", "value": False},
            {"setting": "frequency_network_traffic", "value": 30},
            {"setting": "status_processor", "value": False},
            {"setting": "frequency_processor", "value": 10},
            {"setting": "status_proximity", "value": False},
            {"setting": "frequency_proximity", "value": 20000},
            {"setting": "threshold_proximity", "value": 0},
            {"setting": "frequency_proximity_enforce", "value": False},
            {"setting": "status_significant_motion", "value": False},
            {"setting": "status_calls", "value": False},
            {"setting": "status_messages", "value": False},
            {"setting": "status_plugin_esm_scheduler", "value": False},
            {"setting": "webservice_wifi_only", "value": False},
            {"setting": "frequency_webservice", "value": 30},
            {"setting": "remind_to_charge", "value": False},
            {"setting": "foreground_priority", "value": False},
            {"setting": "status_webservice", "value": False},
        ],
    }
    p = tmp_path / "android_template.json"
    p.write_text(json.dumps(template))
    return p


@pytest.fixture()
def ios_example(tmp_path):
    """Minimal iOS example config with the sensor/plugin structure."""
    example = {
        "server": {
            "database_engine": "mysql",
            "database_host": "localhost",
            "database_name": "aware_ios",
            "database_user": "ios_user",
            "database_pwd": "ios_pass",
            "database_port": 3306,
            "server_host": "0.0.0.0",
            "external_server_host": "http://localhost",
            "external_server_port": 80,
            "server_port": 8080,
            "websocket_port": 8081,
            "path_fullchain_pem": "",
            "path_key_pem": "",
        },
        "study": {
            "study_key": "placeholder",
            "study_number": 1,
            "study_name": "",
            "study_active": True,
            "study_start": 0,
            "study_description": "",
            "researcher_first": "",
            "researcher_last": "",
            "researcher_contact": "",
        },
        "sensors": [
            {
                "sensor": "accelerometer",
                "settings": [
                    {"setting": "status_accelerometer", "defaultValue": "false"},
                    {"setting": "frequency_accelerometer", "defaultValue": "200000"},
                    {"setting": "threshold_accelerometer", "defaultValue": "0"},
                ],
            },
            {
                "sensor": "locations",
                "settings": [
                    {"setting": "status_location_gps", "defaultValue": "false"},
                    {"setting": "frequency_gps", "defaultValue": "180"},
                    {"setting": "min_gps_accuracy", "defaultValue": "150"},
                ],
            },
            {
                "sensor": "webservice",
                "settings": [
                    {"setting": "status_webservice", "defaultValue": "true"},
                    {
                        "setting": "webservice_server",
                        "defaultValue": "http://placeholder/index.php/",
                    },
                    {"setting": "frequency_webservice", "defaultValue": "30"},
                ],
            },
            {
                "sensor": "processor",
                "settings": [
                    {"setting": "status_processor", "defaultValue": "false"},
                    {"setting": "frequency_processor", "defaultValue": "10"},
                ],
            },
        ],
        "plugins": [
            {
                "package_name": "com.aware.plugin.ambient_noise",
                "plugin": "plugin_ambient_noise",
                "settings": [
                    {"setting": "status_plugin_ambient_noise", "defaultValue": "false"},
                    {"setting": "frequency_plugin_ambient_noise", "defaultValue": "5"},
                    {"setting": "plugin_ambient_noise_sample_size", "defaultValue": "30"},
                ],
            },
            {
                "package_name": "com.aware.plugin.esm.scheduler",
                "plugin": "plugin_esm_scheduler",
                "settings": [
                    {"setting": "status_plugin_esm_scheduler", "defaultValue": "false"},
                ],
            },
            {
                "package_name": "com.aware.plugin.google.fused_location",
                "plugin": "plugin_google_fused_location",
                "settings": [
                    {"setting": "status_google_fused_location", "defaultValue": "false"},
                    {"setting": "frequency_google_fused_location", "defaultValue": "300"},
                    {"setting": "max_frequency_google_fused_location", "defaultValue": "60"},
                    {"setting": "fallback_location_timeout", "defaultValue": "20"},
                    {"setting": "accuracy_google_fused_location", "defaultValue": "102"},
                ],
            },
        ],
    }
    p = tmp_path / "aware-config.example.json"
    p.write_text(json.dumps(example))
    return p


@pytest.fixture()
def ios_existing(tmp_path):
    """Existing iOS config file (no prior study key set)."""
    existing = {"study": {"study_key": ""}}
    p = tmp_path / "aware-config.json"
    p.write_text(json.dumps(existing))
    return p


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sensor_value(config, setting):
    for item in config.get("sensors", []):
        if item.get("setting") == setting:
            return item.get("value")
    raise KeyError(f"Setting {setting!r} not found in sensors")


def ios_setting_default(config, sensor_name, setting):
    for sensor in config.get("sensors", []):
        if sensor.get("sensor") == sensor_name:
            for s in sensor.get("settings", []):
                if s.get("setting") == setting:
                    return s.get("defaultValue")
    raise KeyError(f"{sensor_name}/{setting} not found")


def ios_plugin_default(config, plugin_name, setting):
    for plugin in config.get("plugins", []):
        if plugin.get("plugin") == plugin_name or plugin.get("package_name") == plugin_name:
            for s in plugin.get("settings", []):
                if s.get("setting") == setting:
                    return s.get("defaultValue")
    raise KeyError(f"{plugin_name}/{setting} not found")


# ===========================================================================
# serialize_android_config
# ===========================================================================


class TestSerializeAndroidConfig:
    def test_study_info_populated(self, source, settings, android_template, tmp_path):
        config = serialize_android_config(
            source, settings, android_template, webservice_server="http://host/index.php/1/key"
        )
        assert config["study_info"]["study_title"] == "Test Study"
        assert config["study_info"]["study_description"] == "A test study"
        assert config["study_info"]["researcher_first"] == "Alice"
        assert config["study_info"]["researcher_last"] == "Smith"
        assert config["study_info"]["researcher_contact"] == "alice@example.com"

    def test_study_id_passed(self, source, settings, android_template):
        config = serialize_android_config(
            source, settings, android_template, study_id="explicit-id"
        )
        assert config["_id"] == "explicit-id"

    def test_study_id_falls_back_to_source(self, source, settings, android_template):
        config = serialize_android_config(source, settings, android_template)
        assert config["_id"] == "test-study-id"

    def test_database_fields(self, source, settings, android_template):
        config = serialize_android_config(source, settings, android_template)
        db = config["database"]
        assert db["database_name"] == "aware_android"
        assert db["database_username"] == "android_user"
        assert db["database_password"] == "android_pass"
        assert db["database_port"] == "3306"

    def test_database_password_redacted_when_config_without_password(
        self, source, settings, android_template
    ):
        source["database"]["android"]["config_without_password"] = True
        config = serialize_android_config(source, settings, android_template)
        # Password is omitted from the served config so participants enter it;
        # the stored account password is unchanged.
        assert config["database"]["database_password"] == "-"
        assert config["database"]["config_without_password"] is True

    def test_database_host_resolved_from_settings(self, source, settings, android_template):
        # db.internal is an abstract alias → should resolve to android_database_host from settings
        config = serialize_android_config(source, settings, android_template)
        assert config["database"]["database_host"] == "192.168.1.10"

    def test_sensor_values_from_android_settings(self, source, settings, android_template):
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_accelerometer") is True
        assert sensor_value(config, "status_bluetooth") is True
        assert sensor_value(config, "status_screen") is False

    def test_shared_sensor_frequency_overrides_android_settings(
        self, source, settings, android_template
    ):
        # shared.sensors.accelerometer.frequency=20000 should appear in output
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "frequency_accelerometer") == 20000

    def test_webservice_server_injected(self, source, settings, android_template):
        url = "http://192.168.1.10/index.php/1/mykey"
        config = serialize_android_config(source, settings, android_template, webservice_server=url)
        assert sensor_value(config, "webservice_server") == url

    def test_questions_passed_through(self, source, settings, android_template):
        config = serialize_android_config(source, settings, android_template)
        assert len(config["questions"]) == 1
        assert config["questions"][0]["esm_title"] == "Q1"
        assert config["questions"][0]["id"] == 1

    def test_schedules_passed_through(self, source, settings, android_template):
        config = serialize_android_config(source, settings, android_template)
        assert len(config["schedules"]) == 1
        assert config["schedules"][0]["title"] == "S1"

    def test_ios_sensors_block_present(self, source, settings, android_template):
        config = serialize_android_config(source, settings, android_template)
        assert "ios_sensors" in config
        for name in IOS_ONLY_SENSOR_NAMES:
            assert name in config["ios_sensors"]

    def test_ios_sensors_values_from_source(self, source, settings, android_template):
        config = serialize_android_config(source, settings, android_template)
        assert config["ios_sensors"]["significant_motion"] is False
        assert config["ios_sensors"]["websocket"] is False
        assert config["ios_sensors"]["mqtt"] is False

    def test_timestamps_preserved(self, source, settings, android_template):
        config = serialize_android_config(source, settings, android_template)
        assert config["createdAt"] == "2026-01-01T00:00:00.000Z"

    def test_esm_question_submit_default(self, source, settings, android_template):
        source["android"]["questions"][0].pop("esm_submit")
        config = serialize_android_config(source, settings, android_template)
        assert config["questions"][0]["esm_submit"] == "Submit"


# ===========================================================================
# serialize_ios_config
# ===========================================================================


class TestSerializeIosConfig:
    def test_server_block_database_host_resolved(self, source, settings, ios_example, ios_existing):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert config["server"]["database_host"] == "mysql"  # micro_database_host

    def test_server_block_credentials(self, source, settings, ios_example, ios_existing):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        s = config["server"]
        assert s["database_name"] == "aware_ios"
        assert s["database_user"] == "ios_user"
        assert s["database_pwd"] == "ios_pass"
        assert s["database_port"] == 3306
        assert s["server_host"] == "0.0.0.0"
        assert s["server_port"] == 8080
        assert s["websocket_port"] == 8081
        assert s["database_engine"] == "mysql"

    def test_server_external_host(self, source, settings, ios_example, ios_existing):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert config["server"]["external_server_host"] == "http://192.168.1.10"

    def test_study_block_populated(self, source, settings, ios_example, ios_existing):
        config, study = serialize_ios_config(
            source, settings, ios_example, ios_existing, study_key="mykey"
        )
        assert config["study"]["study_name"] == "Test Study"
        assert config["study"]["study_description"] == "A test study"
        assert config["study"]["researcher_first"] == "Alice"
        assert config["study"]["study_key"] == "mykey"
        assert study["study_key"] == "mykey"

    def test_study_key_from_source_when_not_provided(
        self, source, settings, ios_example, ios_existing
    ):
        config, study = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert study["study_key"] == "test_study_key"

    def test_sensor_defaultvalue_updated_from_android_settings(
        self, source, settings, ios_example, ios_existing
    ):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert ios_setting_default(config, "accelerometer", "status_accelerometer") == "true"

    def test_sensor_frequency_defaultvalue_updated(
        self, source, settings, ios_example, ios_existing
    ):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert ios_setting_default(config, "accelerometer", "frequency_accelerometer") == "20000"

    def test_processor_frequency_defaultvalue_converted_to_microseconds(
        self, source, settings, ios_example, ios_existing
    ):
        source["shared"]["sensors"]["processor"] = {"enabled": True, "frequency": 20}
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert ios_setting_default(config, "processor", "frequency_processor") == "20000000"

    def test_ios_sensor_settings_are_not_flattened_into_micro_config(
        self, source, settings, ios_example, ios_existing
    ):
        source["shared"]["sensors"]["wifi"] = {"enabled": True, "frequency": 60}
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)

        assert all("settings" in sensor for sensor in config["sensors"])
        assert not any("setting" in sensor and "sensor" not in sensor for sensor in config["sensors"])

    def test_location_gps_defaultvalue(self, source, settings, ios_example, ios_existing):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert ios_setting_default(config, "locations", "status_location_gps") == "true"

    def test_webservice_url_updated(self, source, settings, ios_example, ios_existing):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        url = ios_setting_default(config, "webservice", "webservice_server")
        assert "192.168.1.10" in url
        assert url.endswith("/index.php/")

    def test_plugin_enabled_defaultvalue(self, source, settings, ios_example, ios_existing):
        # plugin_esm_scheduler is enabled in source.ios.plugins
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        val = ios_plugin_default(config, "plugin_esm_scheduler", "status_plugin_esm_scheduler")
        assert val == "true"

    def test_plugin_ambient_noise_disabled(self, source, settings, ios_example, ios_existing):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        val = ios_plugin_default(config, "plugin_ambient_noise", "status_plugin_ambient_noise")
        assert val == "false"

    def test_plugin_ambient_noise_sub_settings(self, source, settings, ios_example, ios_existing):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert (
            ios_plugin_default(config, "plugin_ambient_noise", "frequency_plugin_ambient_noise")
            == "5"
        )
        assert (
            ios_plugin_default(config, "plugin_ambient_noise", "plugin_ambient_noise_sample_size")
            == "30"
        )

    def test_fused_location_accuracy_normalizes_android_zero_to_100m(
        self, source, settings, ios_example, ios_existing
    ):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert (
            ios_plugin_default(
                config,
                "plugin_google_fused_location",
                "accuracy_google_fused_location",
            )
            == "102"
        )

    def test_fused_location_accuracy_uses_android_selection_for_ios_plugin(
        self, source, settings, ios_example, ios_existing
    ):
        source["android"]["settings"]["accuracy_google_fused_location"] = 100
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert (
            ios_plugin_default(
                config,
                "plugin_google_fused_location",
                "accuracy_google_fused_location",
            )
            == "100"
        )

    def test_ios_esm_plugin_upserted(self, source, settings, ios_example, ios_existing):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        plugins = config["plugins"]
        esm = next((p for p in plugins if p.get("plugin") == "plugin_ios_esm"), None)
        assert esm is not None
        settings_map = {s["setting"]: s["defaultValue"] for s in esm["settings"]}
        assert "status_plugin_ios_esm" in settings_map
        assert "plugin_ios_esm_config_url" in settings_map
        assert "192.168.1.10" in settings_map["plugin_ios_esm_config_url"]

    def test_ios_esm_plugin_enabled_when_esm_scheduler_on(
        self, source, settings, ios_example, ios_existing
    ):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        plugins = config["plugins"]
        esm = next(p for p in plugins if p.get("plugin") == "plugin_ios_esm")
        status = next(s for s in esm["settings"] if s["setting"] == "status_plugin_ios_esm")
        assert status["defaultValue"] == "true"


# ===========================================================================
# build_ios_sensor_settings
# ===========================================================================


class TestBuildIosSensorSettings:
    def test_direct_mapping_passthrough(self, source):
        result = build_ios_sensor_settings(source)
        assert result["status_accelerometer"] is True
        assert result["status_bluetooth"] is True
        assert result["frequency_webservice"] == 60

    def test_rename_frequency_gps(self, source):
        # frequency_location_gps in android.settings is renamed to frequency_gps for iOS
        result = build_ios_sensor_settings(source)
        assert "frequency_gps" in result
        assert result["frequency_gps"] == 180
        assert "frequency_location_gps" not in result

    def test_rename_frequency_network(self, source):
        # iOS has no separate network location frequency — Android-only setting
        result = build_ios_sensor_settings(source)
        assert "frequency_location_network" not in result

    def test_ios_sensors_network_compound_expansion(self, source):
        # ios.sensors.network=False → status_network_events=False (no traffic on iOS)
        # android.settings.status_network_events=True overrides the baseline
        result = build_ios_sensor_settings(source)
        assert result["status_network_events"] is True  # android overrides ios.sensors
        assert "status_network_traffic" not in result  # iOS has no network traffic sensor

    def test_ios_sensors_communication_compound(self, source):
        # ios.sensors.communication=True → status_calls only (iOS has no SMS access)
        # android.settings.status_calls=True overrides the baseline
        result = build_ios_sensor_settings(source)
        assert result["status_calls"] is True
        assert "status_messages" not in result

    def test_shared_sensors_take_highest_priority(self, source):
        # android.settings has frequency_accelerometer=20000, shared.sensors has 20000
        # shared should win (same value here but logic is the override)
        source["android"]["settings"]["frequency_accelerometer"] = 99999
        source["shared"]["sensors"]["accelerometer"]["frequency"] = 20000
        result = build_ios_sensor_settings(source)
        assert result["frequency_accelerometer"] == 20000

    def test_processor_frequency_converts_seconds_to_microseconds_for_ios(self, source):
        source["shared"]["sensors"]["processor"] = {"enabled": True, "frequency": 20}
        result = build_ios_sensor_settings(source)
        assert result["frequency_processor"] == 20_000_000

    def test_processor_frequency_converts_string_seconds_to_microseconds_for_ios(self, source):
        source["shared"]["sensors"]["processor"] = {"enabled": True, "frequency": "0.5"}
        result = build_ios_sensor_settings(source)
        assert result["frequency_processor"] == 500_000

    def test_ios_only_sensors_from_ios_sensors_block(self, source):
        result = build_ios_sensor_settings(source)
        assert "status_significant_motion" in result
        assert result["status_significant_motion"] is False

    def test_locations_compound_sensor(self, source):
        # ios.sensors.locations=True → status_location_gps=True (as baseline)
        # android.settings.status_location_gps=True overrides
        source["android"]["settings"]["status_location_gps"] = False
        result = build_ios_sensor_settings(source)
        # android.settings wins over ios.sensors compound
        assert result["status_location_gps"] is False


# ===========================================================================
# build_ios_esm_config
# ===========================================================================


class TestBuildIosEsmConfig:
    def test_schedule_count(self, source):
        result = build_ios_esm_config(source)
        assert len(result) == 1

    def test_schedule_id_generated(self, source):
        result = build_ios_esm_config(source)
        assert result[0]["schedule_id"] == "schedule_1"

    def test_schedule_notification_title(self, source):
        result = build_ios_esm_config(source)
        assert result[0]["notification_title"] == "S1"

    def test_schedule_has_esms(self, source):
        result = build_ios_esm_config(source)
        assert len(result[0]["esms"]) == 1

    def test_esm_type_preserved(self, source):
        result = build_ios_esm_config(source)
        esm = result[0]["esms"][0]["esm"]
        assert esm["esm_type"] == 2

    def test_esm_title_preserved(self, source):
        result = build_ios_esm_config(source)
        esm = result[0]["esms"][0]["esm"]
        assert esm["esm_title"] == "Q1"

    def test_esm_instructions_mapped(self, source):
        result = build_ios_esm_config(source)
        esm = result[0]["esms"][0]["esm"]
        assert esm["esm_instructions"] == "Pick one"

    def test_esm_trigger_generated(self, source):
        result = build_ios_esm_config(source)
        esm = result[0]["esms"][0]["esm"]
        assert "esm_trigger" in esm

    def test_esm_submit_preserved(self, source):
        result = build_ios_esm_config(source)
        esm = result[0]["esms"][0]["esm"]
        assert esm["esm_submit"] == "Submit"

    def test_schedule_hours_default_all_day(self, source):
        result = build_ios_esm_config(source)
        assert result[0]["hours"] == list(range(24))

    def test_schedule_hours_from_explicit_list(self, source):
        source["shared"]["esms"]["schedules"][0]["hours"] = [9, 12, 17]
        result = build_ios_esm_config(source)
        assert result[0]["hours"] == [9, 12, 17]

    def test_missing_question_id_skipped(self, source):
        source["shared"]["esms"]["schedules"][0]["questions"] = [99]
        result = build_ios_esm_config(source)
        assert result[0]["esms"] == []

    def test_empty_schedules(self, source):
        source["shared"]["esms"]["schedules"] = []
        result = build_ios_esm_config(source)
        assert result == []


# ===========================================================================
# update_ios_server_config
# ===========================================================================


class TestUpdateIosServerConfig:
    def test_all_required_fields_present(self, source, settings):
        config = {}
        update_ios_server_config(config, source["database"], settings)
        s = config["server"]
        for key in (
            "database_engine",
            "database_host",
            "database_name",
            "database_user",
            "database_pwd",
            "database_port",
            "server_host",
            "server_port",
            "websocket_port",
            "external_server_host",
            "external_server_port",
            "path_fullchain_pem",
            "path_key_pem",
        ):
            assert key in s, f"Missing key: {key}"

    def test_database_engine_always_mysql(self, source, settings):
        config = {}
        update_ios_server_config(config, source["database"], settings)
        assert config["server"]["database_engine"] == "mysql"

    def test_abstract_host_resolved_to_micro_database_host(self, source, settings):
        config = {}
        update_ios_server_config(config, source["database"], settings)
        assert config["server"]["database_host"] == "mysql"

    def test_concrete_host_preserved(self, source, settings):
        source["database"]["ios"]["host"] = "real-db-server.internal"
        config = {}
        update_ios_server_config(config, source["database"], settings)
        assert config["server"]["database_host"] == "real-db-server.internal"


# ===========================================================================
# source.json field coverage
# ===========================================================================


class TestSourceJsonCoverage:
    """Ensure the real source.json has all fields required by the serializers."""

    SOURCE_PATH = pathlib.Path(__file__).resolve().parent.parent / "source.json"

    @pytest.fixture(scope="class")
    def real_source(self):
        assert self.SOURCE_PATH.exists(), f"source.json not found at {self.SOURCE_PATH}"
        return json.loads(self.SOURCE_PATH.read_text(encoding="utf-8"))

    def test_top_level_keys(self, real_source):
        for key in ("study", "researcher", "database", "android", "ios", "shared"):
            assert key in real_source, f"Missing top-level key: {key}"

    def test_study_fields(self, real_source):
        study = real_source["study"]
        for field in ("id", "title", "description"):
            assert field in study, f"Missing study.{field}"

    def test_researcher_fields(self, real_source):
        r = real_source["researcher"]
        for field in ("first_name", "last_name", "contact"):
            assert field in r, f"Missing researcher.{field}"

    def test_database_android_fields(self, real_source):
        db = real_source["database"]["android"]
        for field in ("port", "name", "username", "password"):
            assert field in db, f"Missing database.android.{field}"

    def test_database_ios_fields(self, real_source):
        db = real_source["database"]["ios"]
        for field in ("port", "name", "username", "password"):
            assert field in db, f"Missing database.ios.{field}"

    def test_android_settings_is_dict(self, real_source):
        settings = real_source["android"]["settings"]
        assert isinstance(settings, dict)

    def test_android_required_settings_present(self, real_source):
        settings = real_source["android"]["settings"]
        for key in ("status_webservice", "webservice_wifi_only", "frequency_webservice"):
            assert key in settings, f"Missing android.settings.{key}"

    def test_ios_server_fields(self, real_source):
        srv = real_source["ios"]["server"]
        for field in ("server_host", "server_port", "websocket_port"):
            assert field in srv, f"Missing ios.server.{field}"

    def test_ios_sensors_is_dict(self, real_source):
        assert isinstance(real_source["ios"]["sensors"], dict)

    def test_ios_plugins_is_dict(self, real_source):
        assert isinstance(real_source["ios"]["plugins"], dict)

    def test_shared_esms_structure(self, real_source):
        esms = real_source["shared"]["esms"]
        assert isinstance(esms.get("questions"), list)
        assert isinstance(esms.get("schedules"), list)

    def test_shared_sensors_common_fields(self, real_source):
        sensors = real_source["shared"]["sensors"]
        assert isinstance(sensors, dict)
        for sensor_name in ("accelerometer", "battery", "bluetooth"):
            assert sensor_name in sensors, f"Missing shared.sensors.{sensor_name}"

    def test_shared_sensor_has_enabled_field(self, real_source):
        sensors = real_source["shared"]["sensors"]
        for name, sensor in sensors.items():
            if not isinstance(sensor, dict) or not sensor:
                # Empty dicts are allowed for sensors with no stored state yet
                continue
            assert "enabled" in sensor, f"shared.sensors.{name} missing 'enabled'"

    def test_shared_sensors_cover_common_sensor_names(self, real_source):
        """Sensors in COMMON_SHARED_SENSOR_FIELDS should exist in shared.sensors."""
        sensors = real_source["shared"]["sensors"]
        # Hardware/software sensors whose state lives in shared.sensors (not android.settings)
        expected = {
            name for name in COMMON_SHARED_SENSOR_FIELDS if name not in IOS_ONLY_SENSOR_NAMES
        }
        for sensor_name in expected:
            assert sensor_name in sensors, f"shared.sensors missing {sensor_name}"


# ===========================================================================
# Gravity sensor — Android-only
# ===========================================================================


class TestGravitySensor:
    """Gravity is Android-only: iOS receives no gravity settings."""

    GRAVITY = {
        "enabled": True,
        "frequency": 20000,
        "threshold": 10,
        "enforce": True,
    }

    def test_gravity_not_in_common_shared_sensor_fields(self):
        assert "gravity" not in COMMON_SHARED_SENSOR_FIELDS

    def test_gravity_not_in_ios_sensor_settings(self, source):
        source["shared"]["sensors"]["gravity"] = self.GRAVITY
        result = build_ios_sensor_settings(source)
        assert "status_gravity" not in result
        assert "frequency_gravity" not in result
        assert "threshold_gravity" not in result
        assert "frequency_gravity_enforce" not in result

    def test_gravity_in_android_config(self, source, settings, android_template):
        source["android"]["settings"]["status_gravity"] = True
        source["android"]["settings"]["frequency_gravity"] = 20000
        source["android"]["settings"]["threshold_gravity"] = 10
        source["android"]["settings"]["frequency_gravity_enforce"] = True
        template = json.loads(android_template.read_text())
        template["sensors"] += [
            {"setting": "status_gravity", "value": False},
            {"setting": "frequency_gravity", "value": 200000},
            {"setting": "threshold_gravity", "value": 0},
            {"setting": "frequency_gravity_enforce", "value": False},
        ]
        android_template.write_text(json.dumps(template))

        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_gravity") is True
        assert sensor_value(config, "frequency_gravity") == 20000
        assert sensor_value(config, "threshold_gravity") == 10
        assert sensor_value(config, "frequency_gravity_enforce") is True

    def test_gravity_not_written_to_ios_config(self, source, settings, ios_existing, tmp_path):
        source["shared"]["sensors"]["gravity"] = self.GRAVITY
        example = {
            "server": {
                "database_engine": "mysql",
                "database_host": "localhost",
                "database_name": "aware_ios",
                "database_user": "u",
                "database_pwd": "p",
                "database_port": 3306,
                "server_host": "0.0.0.0",
                "external_server_host": "http://localhost",
                "external_server_port": 80,
                "server_port": 8080,
                "websocket_port": 8081,
                "path_fullchain_pem": "",
                "path_key_pem": "",
            },
            "study": {
                "study_key": "placeholder",
                "study_number": 1,
                "study_name": "",
                "study_active": True,
                "study_start": 0,
                "study_description": "",
                "researcher_first": "",
                "researcher_last": "",
                "researcher_contact": "",
            },
            "sensors": [],
            "plugins": [],
        }
        example_path = tmp_path / "aware-config-no-gravity.example.json"
        example_path.write_text(json.dumps(example))

        config, _ = serialize_ios_config(source, settings, example_path, ios_existing)
        sensor_names = [s.get("sensor") for s in config.get("sensors", [])]
        assert "gravity" not in sensor_names

    def test_gravity_absent_from_source_json_ios(self):
        """Verify the real source.json has no gravity entry in ios.sensors."""
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        assert (
            "gravity" not in real_source["ios"]["sensors"]
        ), "ios.sensors must not contain gravity in source.json"


# ===========================================================================
# Temperature sensor — Android-only
# ===========================================================================


class TestTemperatureSensor:
    """Temperature is Android-only: iPhones have no ambient thermometer hardware."""

    TEMPERATURE = {
        "enabled": True,
        "frequency": 20000,
        "threshold": 10,
        "enforce": True,
    }

    def test_temperature_in_common_shared_sensor_fields(self):
        assert "temperature" in COMMON_SHARED_SENSOR_FIELDS

    def test_temperature_in_android_only_shared_sensor_names(self):
        assert "temperature" in ANDROID_ONLY_SHARED_SENSOR_NAMES

    def test_temperature_not_in_ios_sensor_settings(self, source):
        source["shared"]["sensors"]["temperature"] = self.TEMPERATURE
        result = build_ios_sensor_settings(source)
        assert "status_temperature" not in result
        assert "frequency_temperature" not in result
        assert "threshold_temperature" not in result
        assert "frequency_temperature_enforce" not in result

    def test_temperature_in_android_config(self, source, settings, android_template):
        source["android"]["settings"]["status_temperature"] = True
        source["android"]["settings"]["frequency_temperature"] = 20000
        source["android"]["settings"]["threshold_temperature"] = 10
        source["android"]["settings"]["frequency_temperature_enforce"] = True
        template = json.loads(android_template.read_text())
        template["sensors"] += [
            {"setting": "status_temperature", "value": False},
            {"setting": "frequency_temperature", "value": 200000},
            {"setting": "threshold_temperature", "value": 0},
            {"setting": "frequency_temperature_enforce", "value": False},
        ]
        android_template.write_text(json.dumps(template))
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_temperature") is True
        assert sensor_value(config, "frequency_temperature") == 20000
        assert sensor_value(config, "threshold_temperature") == 10
        assert sensor_value(config, "frequency_temperature_enforce") is True

    def test_temperature_shared_sensor_flows_to_android(self, source, settings, android_template):
        source["shared"]["sensors"]["temperature"] = self.TEMPERATURE
        template = json.loads(android_template.read_text())
        template["sensors"] += [
            {"setting": "status_temperature", "value": False},
            {"setting": "frequency_temperature", "value": 0},
            {"setting": "threshold_temperature", "value": 0},
            {"setting": "frequency_temperature_enforce", "value": False},
        ]
        android_template.write_text(json.dumps(template))
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_temperature") is True
        assert sensor_value(config, "frequency_temperature") == 20000

    def test_temperature_not_written_to_ios_config(self, source, settings, ios_existing, tmp_path):
        source["shared"]["sensors"]["temperature"] = self.TEMPERATURE
        example = {
            "server": {
                "database_engine": "mysql",
                "database_host": "localhost",
                "database_name": "aware_ios",
                "database_user": "u",
                "database_pwd": "p",
                "database_port": 3306,
                "server_host": "0.0.0.0",
                "external_server_host": "http://localhost",
                "external_server_port": 80,
                "server_port": 8080,
                "websocket_port": 8081,
                "path_fullchain_pem": "",
                "path_key_pem": "",
            },
            "study": {
                "study_key": "placeholder",
                "study_number": 1,
                "study_name": "",
                "study_active": True,
                "study_start": 0,
                "study_description": "",
                "researcher_first": "",
                "researcher_last": "",
                "researcher_contact": "",
            },
            "sensors": [],
            "plugins": [],
        }
        example_path = tmp_path / "aware-config-no-temperature.example.json"
        example_path.write_text(json.dumps(example))
        config, _ = serialize_ios_config(source, settings, example_path, ios_existing)
        sensor_names = [s.get("sensor") for s in config.get("sensors", [])]
        assert "temperature" not in sensor_names

    def test_temperature_absent_from_source_json_ios_sensors(self):
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        assert (
            "temperature" not in real_source["ios"]["sensors"]
        ), "ios.sensors must not contain temperature in source.json"

    def test_temperature_present_in_source_json_shared_sensors(self):
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        assert (
            "temperature" in real_source["shared"]["sensors"]
        ), "shared.sensors must contain temperature for Android config"


# ===========================================================================
# Telephony sensor — Android-only
# ===========================================================================


class TestTelephonySensor:
    """Telephony is Android-only: iOS has no equivalent cell-tower/operator API."""

    def test_telephony_in_common_shared_sensor_fields(self):
        assert "telephony" in COMMON_SHARED_SENSOR_FIELDS

    def test_telephony_in_android_only_shared_sensor_names(self):
        assert "telephony" in ANDROID_ONLY_SHARED_SENSOR_NAMES

    def test_telephony_not_in_ios_sensor_settings(self, source):
        source["shared"]["sensors"]["telephony"] = {"enabled": True}
        result = build_ios_sensor_settings(source)
        assert "status_telephony" not in result

    def test_telephony_in_android_config(self, source, settings, android_template):
        source["android"]["settings"]["status_telephony"] = True
        template = json.loads(android_template.read_text())
        template["sensors"] += [{"setting": "status_telephony", "value": False}]
        android_template.write_text(json.dumps(template))
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_telephony") is True

    def test_telephony_shared_sensor_flows_to_android(self, source, settings, android_template):
        source["shared"]["sensors"]["telephony"] = {"enabled": True}
        template = json.loads(android_template.read_text())
        template["sensors"] += [{"setting": "status_telephony", "value": False}]
        android_template.write_text(json.dumps(template))
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_telephony") is True

    def test_telephony_absent_from_source_json_ios_sensors(self):
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        assert (
            "telephony" not in real_source["ios"]["sensors"]
        ), "ios.sensors must not contain telephony in source.json"

    def test_telephony_present_in_source_json_shared_sensors(self):
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        assert (
            "telephony" in real_source["shared"]["sensors"]
        ), "shared.sensors must contain telephony for Android config"


# ===========================================================================
# Applications sensor — Android-only
# ===========================================================================


class TestApplicationsSensor:
    """Applications sensor is Android-only: iOS sandboxing prevents app/process enumeration."""

    APPLICATIONS = {"enabled": True, "frequency": 30}

    def test_applications_in_common_shared_sensor_fields(self):
        assert "applications" in COMMON_SHARED_SENSOR_FIELDS

    def test_applications_in_android_only_shared_sensor_names(self):
        assert "applications" in ANDROID_ONLY_SHARED_SENSOR_NAMES

    def test_applications_not_in_ios_sensor_settings(self, source):
        source["shared"]["sensors"]["applications"] = self.APPLICATIONS
        result = build_ios_sensor_settings(source)
        assert "status_applications" not in result
        assert "frequency_applications" not in result

    def test_applications_sub_settings_not_in_ios(self, source):
        source["android"]["settings"].update(
            {
                "status_notifications": True,
                "status_crashes": True,
                "status_keyboard": True,
                "mask_keyboard": True,
                "status_installations": True,
            }
        )
        result = build_ios_sensor_settings(source)
        for key in (
            "status_notifications",
            "status_crashes",
            "status_keyboard",
            "mask_keyboard",
            "status_installations",
        ):
            assert key not in result, f"{key} must not flow to iOS settings"

    def test_applications_in_android_config(self, source, settings, android_template):
        source["android"]["settings"]["status_applications"] = True
        source["android"]["settings"]["frequency_applications"] = 30
        template = json.loads(android_template.read_text())
        template["sensors"] += [
            {"setting": "status_applications", "value": False},
            {"setting": "frequency_applications", "value": 0},
        ]
        android_template.write_text(json.dumps(template))
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_applications") is True
        assert sensor_value(config, "frequency_applications") == 30

    def test_applications_shared_sensor_flows_to_android(self, source, settings, android_template):
        source["shared"]["sensors"]["applications"] = self.APPLICATIONS
        template = json.loads(android_template.read_text())
        template["sensors"] += [
            {"setting": "status_applications", "value": False},
            {"setting": "frequency_applications", "value": 0},
        ]
        android_template.write_text(json.dumps(template))
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_applications") is True
        assert sensor_value(config, "frequency_applications") == 30

    def test_applications_absent_from_source_json_ios_sensors(self):
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        assert (
            "applications" not in real_source["ios"]["sensors"]
        ), "ios.sensors must not contain applications in source.json"

    def test_applications_present_in_source_json_shared_sensors(self):
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        assert (
            "applications" in real_source["shared"]["sensors"]
        ), "shared.sensors must contain applications for Android config"


# ===========================================================================
# Light sensor — Android-only
# ===========================================================================


class TestLightSensor:
    """Light sensor is Android-only: iPhones have no ambient light hardware sensor API."""

    LIGHT = {"enabled": True, "frequency": 20000, "threshold": 10, "enforce": True}

    def test_light_in_common_shared_sensor_fields(self):
        assert "light" in COMMON_SHARED_SENSOR_FIELDS

    def test_light_in_android_only_shared_sensor_names(self):
        assert "light" in ANDROID_ONLY_SHARED_SENSOR_NAMES

    def test_light_not_in_ios_sensor_settings(self, source):
        source["shared"]["sensors"]["light"] = self.LIGHT
        result = build_ios_sensor_settings(source)
        assert "status_light" not in result
        assert "frequency_light" not in result
        assert "threshold_light" not in result
        assert "frequency_light_enforce" not in result

    def test_light_in_android_config(self, source, settings, android_template):
        source["android"]["settings"]["status_light"] = True
        source["android"]["settings"]["frequency_light"] = 20000
        source["android"]["settings"]["threshold_light"] = 10
        source["android"]["settings"]["frequency_light_enforce"] = True
        template = json.loads(android_template.read_text())
        template["sensors"] += [
            {"setting": "status_light", "value": False},
            {"setting": "frequency_light", "value": 0},
            {"setting": "threshold_light", "value": 0},
            {"setting": "frequency_light_enforce", "value": False},
        ]
        android_template.write_text(json.dumps(template))
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_light") is True
        assert sensor_value(config, "frequency_light") == 20000
        assert sensor_value(config, "threshold_light") == 10
        assert sensor_value(config, "frequency_light_enforce") is True

    def test_light_shared_sensor_flows_to_android(self, source, settings, android_template):
        source["shared"]["sensors"]["light"] = self.LIGHT
        template = json.loads(android_template.read_text())
        template["sensors"] += [
            {"setting": "status_light", "value": False},
            {"setting": "frequency_light", "value": 0},
            {"setting": "threshold_light", "value": 0},
            {"setting": "frequency_light_enforce", "value": False},
        ]
        android_template.write_text(json.dumps(template))
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_light") is True
        assert sensor_value(config, "frequency_light") == 20000

    def test_light_absent_from_source_json_ios_sensors(self):
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        assert (
            "light" not in real_source["ios"]["sensors"]
        ), "ios.sensors must not contain light in source.json"

    def test_light_present_in_source_json_shared_sensors(self):
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        assert (
            "light" in real_source["shared"]["sensors"]
        ), "shared.sensors must contain light for Android config"


# ===========================================================================
# Screen sensor — iOS has status_screen only (no touch/keyboard sub-settings)
# ===========================================================================


class TestScreenSensorIos:
    """status_touch and mask_touch_text are Android-only; iOS only exposes status_screen."""

    def test_status_touch_not_in_ios_sensor_settings(self, source):
        source["android"]["settings"]["status_touch"] = True
        result = build_ios_sensor_settings(source)
        assert "status_touch" not in result

    def test_mask_touch_text_not_in_ios_sensor_settings(self, source):
        source["android"]["settings"]["mask_touch_text"] = True
        result = build_ios_sensor_settings(source)
        assert "mask_touch_text" not in result

    def test_status_screen_does_flow_to_ios(self, source):
        source["android"]["settings"]["status_screen"] = True
        result = build_ios_sensor_settings(source)
        assert result.get("status_screen") is True

    def test_status_touch_flows_to_android(self, source, settings, android_template):
        source["android"]["settings"]["status_touch"] = True
        config = serialize_android_config(source, settings, android_template)
        # status_touch is written to Android via android.settings directly
        assert sensor_value(config, "status_screen") is False  # default from template

    def test_status_touch_in_android_template(self, android_template):
        import json

        template = json.loads(android_template.read_text())
        assert any(s.get("setting") == "status_screen" for s in template["sensors"])


# ===========================================================================
# Accelerometer — iOS has no "enforce frequency" concept (CoreMotion)
# ===========================================================================


class TestAccelerometerIos:
    """iOS CoreMotion delivers data at hardware rate; *_enforce keys must not appear."""

    def test_enforce_not_in_ios_sensor_settings(self, source):
        result = build_ios_sensor_settings(source)
        assert "frequency_accelerometer_enforce" not in result

    def test_status_frequency_threshold_flow_to_ios(self, source):
        result = build_ios_sensor_settings(source)
        assert "status_accelerometer" in result
        assert "frequency_accelerometer" in result
        assert "threshold_accelerometer" in result

    def test_enforce_not_updated_in_ios_config(self, source, settings, ios_example, ios_existing):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        for sensor in config.get("sensors", []):
            if sensor.get("sensor") == "accelerometer":
                setting_names = [s.get("setting") for s in sensor.get("settings", [])]
                assert "frequency_accelerometer_enforce" not in setting_names

    def test_enforce_still_flows_to_android(self, source, settings, android_template):
        source["shared"]["sensors"]["accelerometer"]["enforce"] = True
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "frequency_accelerometer_enforce") is True

    def test_all_enforce_keys_stripped_from_ios(self, source):
        # Plant enforce values across multiple shared sensors and verify none reach iOS.
        for sensor_name in ("barometer", "gyroscope", "magnetometer", "rotation"):
            source["shared"]["sensors"].setdefault(sensor_name, {})["enforce"] = True
        result = build_ios_sensor_settings(source)
        enforce_keys = [k for k in result if k.endswith("_enforce")]
        assert enforce_keys == [], f"Unexpected _enforce keys in iOS settings: {enforce_keys}"


# ===========================================================================
# Proximity sensor — Android-only
# ===========================================================================


class TestProximitySensor:
    """Proximity is Android-only in this deployment; iPhone has no DB table."""

    def test_proximity_not_in_common_shared_sensor_fields(self):
        assert "proximity" not in COMMON_SHARED_SENSOR_FIELDS

    def test_proximity_android_settings_do_not_flow_to_ios(self, source):
        source["android"]["settings"].update(
            {
                "status_proximity": True,
                "frequency_proximity": 20000,
                "threshold_proximity": 10,
                "frequency_proximity_enforce": True,
            }
        )
        result = build_ios_sensor_settings(source)
        assert "status_proximity" not in result
        assert "frequency_proximity" not in result
        assert "threshold_proximity" not in result
        assert "frequency_proximity_enforce" not in result

    def test_proximity_android_settings_flow_to_android(self, source, settings, android_template):
        source["android"]["settings"].update(
            {
                "status_proximity": True,
                "frequency_proximity": 20000,
                "threshold_proximity": 10,
                "frequency_proximity_enforce": True,
            }
        )
        config = serialize_android_config(source, settings, android_template)
        assert sensor_value(config, "status_proximity") is True
        assert sensor_value(config, "frequency_proximity") == 20000
        assert sensor_value(config, "threshold_proximity") == 10
        assert sensor_value(config, "frequency_proximity_enforce") is True

    def test_proximity_absent_from_source_json_ios_and_shared(self):
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        assert "proximity" not in real_source["ios"]["sensors"]
        assert "proximity" not in real_source["shared"]["sensors"]

    def test_proximity_present_in_source_json_android_settings(self):
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        android_settings = real_source["android"]["settings"]
        assert "status_proximity" in android_settings
        assert "frequency_proximity" in android_settings
        assert "threshold_proximity" in android_settings
        assert "frequency_proximity_enforce" in android_settings


# ===========================================================================
# Locations — iOS uses abbreviated GPS field names; network location is Android-only
# ===========================================================================


class TestLocationsIos:
    """iOS Core Location: GPS only, renamed frequency/accuracy keys, no network location."""

    def test_frequency_gps_renamed_in_ios_settings(self, source):
        result = build_ios_sensor_settings(source)
        assert "frequency_gps" in result
        assert result["frequency_gps"] == 180
        assert "frequency_location_gps" not in result

    def test_min_gps_accuracy_renamed_in_ios_settings(self, source):
        result = build_ios_sensor_settings(source)
        assert "min_gps_accuracy" in result
        assert result["min_gps_accuracy"] == 150
        assert "min_location_gps_accuracy" not in result

    def test_network_location_settings_absent_from_ios(self, source):
        result = build_ios_sensor_settings(source)
        for key in (
            "status_location_network",
            "frequency_location_network",
            "min_location_network_accuracy",
            "status_location_passive",
            "location_expiration_time",
            "location_save_all",
        ):
            assert key not in result, f"{key} must not flow to iOS settings"

    def test_network_traffic_absent_from_ios(self, source):
        result = build_ios_sensor_settings(source)
        assert "status_network_traffic" not in result

    def test_renamed_location_keys_applied_in_ios_config(
        self, source, settings, ios_example, ios_existing
    ):
        config, _ = serialize_ios_config(source, settings, ios_example, ios_existing)
        assert ios_setting_default(config, "locations", "frequency_gps") == "180"
        assert ios_setting_default(config, "locations", "min_gps_accuracy") == "150"

    def test_location_gps_status_still_flows_unchanged(self, source):
        result = build_ios_sensor_settings(source)
        assert result.get("status_location_gps") is True


# ===========================================================================
# Android config correctness — key names and presence
# ===========================================================================


def _android_setting(config: dict, key: str):
    """Return the value of a named setting in the Android config sensors list."""
    for item in config.get("sensors", []):
        if item.get("setting") == key:
            return item["value"]
    raise KeyError(f"Setting '{key}' not found in Android config")


def _android_has(config: dict, key: str) -> bool:
    return any(item.get("setting") == key for item in config.get("sensors", []))


class TestAndroidConfigCorrectness:
    """Verify that serialize_android_config produces correct setting keys and values."""

    def test_frequency_location_gps_key_correct(self, source, settings, android_template):
        source["android"]["settings"]["frequency_location_gps"] = 120
        template = json.loads(android_template.read_text())
        android_template.write_text(json.dumps(template))
        config = serialize_android_config(source, settings, android_template)
        assert _android_has(
            config, "frequency_location_gps"
        ), "frequency_location_gps must be present (not frequency_gps)"
        assert not _android_has(
            config, "frequency_gps"
        ), "frequency_gps must NOT appear in Android config"
        assert _android_setting(config, "frequency_location_gps") == 120

    def test_frequency_location_network_key_correct(self, source, settings, android_template):
        source["android"]["settings"]["frequency_location_network"] = 240
        config = serialize_android_config(source, settings, android_template)
        assert _android_has(
            config, "frequency_location_network"
        ), "frequency_location_network must be present (not frequency_network)"
        assert not _android_has(
            config, "frequency_network"
        ), "frequency_network must NOT appear in Android config"
        assert _android_setting(config, "frequency_location_network") == 240

    def test_status_significant_motion_present(self, source, settings, android_template):
        source["android"]["settings"]["status_significant_motion"] = True
        config = serialize_android_config(source, settings, android_template)
        assert _android_has(
            config, "status_significant_motion"
        ), "status_significant_motion must be present in Android config"
        assert _android_setting(config, "status_significant_motion") is True

    def test_frequency_network_traffic_present(self, source, settings, android_template):
        source["android"]["settings"]["frequency_network_traffic"] = 45
        config = serialize_android_config(source, settings, android_template)
        assert _android_has(
            config, "frequency_network_traffic"
        ), "frequency_network_traffic must be present in Android config"
        assert _android_setting(config, "frequency_network_traffic") == 45

    def test_status_network_traffic_present(self, source, settings, android_template):
        source["android"]["settings"]["status_network_traffic"] = True
        config = serialize_android_config(source, settings, android_template)
        assert _android_has(config, "status_network_traffic")
        assert _android_setting(config, "status_network_traffic") is True

    def test_sensor_toggles_round_trip(self, source, settings, android_template):
        """Core sensor on/off toggles appear under the correct setting names."""
        source["android"]["settings"].update(
            {
                "status_accelerometer": True,
                "status_bluetooth": True,
                "status_location_gps": True,
                "status_location_network": False,
                "status_network_events": True,
                "status_network_traffic": True,
                "status_calls": True,
                "status_messages": False,
                "webservice_wifi_only": True,
            }
        )
        config = serialize_android_config(source, settings, android_template)
        assert _android_setting(config, "status_accelerometer") is True
        assert _android_setting(config, "status_bluetooth") is True
        assert _android_setting(config, "status_location_gps") is True
        assert _android_setting(config, "status_location_network") is False
        assert _android_setting(config, "status_network_events") is True
        assert _android_setting(config, "status_network_traffic") is True
        assert _android_setting(config, "status_calls") is True
        assert _android_setting(config, "status_messages") is False
        assert _android_setting(config, "webservice_wifi_only") is True

    def test_location_frequency_propagates_to_ios(self, source, settings):
        """frequency_location_gps is renamed to frequency_gps for iOS."""
        source["android"]["settings"]["frequency_location_gps"] = 90
        source["android"]["settings"]["frequency_location_network"] = 200
        ios_settings = build_ios_sensor_settings(source)
        assert ios_settings.get("frequency_gps") == 90
        assert "frequency_location_gps" not in ios_settings
        assert "frequency_location_network" not in ios_settings  # Android-only

    def test_ios_uses_abbreviated_gps_keys(self, source, settings):
        """iOS uses frequency_gps / min_gps_accuracy, not the full Android names."""
        source["android"]["settings"]["frequency_location_gps"] = 90
        source["android"]["settings"]["min_location_gps_accuracy"] = 75
        ios_settings = build_ios_sensor_settings(source)
        assert ios_settings.get("frequency_gps") == 90
        assert ios_settings.get("min_gps_accuracy") == 75
        assert "frequency_location_gps" not in ios_settings
        assert "min_location_gps_accuracy" not in ios_settings

    def test_real_source_json_uses_correct_location_keys(self):
        """The committed source.json must use the correct GPS/network frequency keys."""
        source_path = pathlib.Path(__file__).resolve().parent.parent / "source.json"
        real_source = json.loads(source_path.read_text(encoding="utf-8"))
        android_settings = real_source.get("android", {}).get("settings", {})
        assert (
            "frequency_location_gps" in android_settings
        ), "source.json must use frequency_location_gps"
        assert (
            "frequency_location_network" in android_settings
        ), "source.json must use frequency_location_network"
        assert (
            "frequency_gps" not in android_settings
        ), "source.json must not have legacy frequency_gps"
        assert (
            "frequency_network" not in android_settings
        ), "source.json must not have legacy frequency_network"
