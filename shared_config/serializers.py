import json
import pathlib
import secrets
from datetime import datetime, timezone

from shared_config.runtime import build_public_base_url
from shared_config.source_store import read_source

DEFAULT_ANDROID_TEMPLATE_PATH = (
    pathlib.Path(__file__).resolve().parent / "android_template.json"
)

COMMON_SHARED_SENSOR_FIELDS: dict[str, tuple[str, ...]] = {
    "accelerometer": ("enabled", "frequency", "threshold", "enforce"),
    "applications": ("enabled", "frequency"),
    "barometer": ("enabled", "frequency", "threshold", "enforce"),
    "battery": ("enabled",),
    "bluetooth": ("enabled", "frequency"),
    "esm": ("enabled",),
    "gravity": ("enabled", "frequency", "threshold", "enforce"),
    "gyroscope": ("enabled", "frequency", "threshold", "enforce"),
    "light": ("enabled", "frequency", "threshold", "enforce"),
    "linear_accelerometer": ("enabled", "frequency", "threshold", "enforce"),
    "magnetometer": ("enabled", "frequency", "threshold", "enforce"),
    "processor": ("enabled",),
    "proximity": ("enabled", "frequency", "threshold", "enforce"),
    "rotation": ("enabled", "frequency", "threshold", "enforce"),
    "screen": ("enabled",),
    "telephony": ("enabled",),
    "temperature": ("enabled", "frequency", "threshold", "enforce"),
    "timezone": ("enabled", "frequency"),
    "wifi": ("enabled", "frequency"),
}

IOS_ONLY_SENSOR_NAMES = ("significant_motion", "websocket", "mqtt")

IOS_ESM_CONFIG_FILENAME = "ios-esm-config.json"


def load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_android_template(path: pathlib.Path) -> dict:
    if path.exists():
        return load_json(path)
    return load_json(DEFAULT_ANDROID_TEMPLATE_PATH)


def load_existing_json(path: pathlib.Path) -> dict | None:
    if not path.exists():
        return None
    return load_json(path)


def to_bool_string(value: object) -> str:
    return "true" if bool(value) else "false"


def build_sensor_setting_name(sensor_name: str, field_name: str) -> str:
    if field_name == "enabled":
        return f"status_{sensor_name}"
    if field_name == "frequency":
        return f"frequency_{sensor_name}"
    if field_name == "threshold":
        return f"threshold_{sensor_name}"
    if field_name == "enforce":
        return f"frequency_{sensor_name}_enforce"
    raise ValueError(f"Unsupported sensor field '{field_name}'")


def build_shared_sensor_settings(source: dict) -> dict[str, object]:
    shared_sensors = source.get("shared", {}).get("sensors", {})
    android_settings = source.get("android", {}).get("settings", {})
    shared_settings: dict[str, object] = {}

    for sensor_name, field_names in COMMON_SHARED_SENSOR_FIELDS.items():
        sensor_source = shared_sensors.get(sensor_name, {})
        if isinstance(sensor_source, bool):
            sensor_source = {"enabled": sensor_source}
        if not isinstance(sensor_source, dict):
            sensor_source = {}

        for field_name in field_names:
            setting_name = build_sensor_setting_name(sensor_name, field_name)
            if field_name in sensor_source:
                shared_settings[setting_name] = sensor_source[field_name]
            elif setting_name in android_settings:
                shared_settings[setting_name] = android_settings[setting_name]

    return shared_settings


def get_shared_esm(source: dict) -> dict[str, list[dict]]:
    """Return the canonical editable ESM structure with legacy fallback."""
    shared_esm = source.get("shared", {}).get("esms")
    if not isinstance(shared_esm, dict):
        shared_esm = {}

    android = source.get("android", {})
    questions = shared_esm.get("questions")
    schedules = shared_esm.get("schedules")

    if not isinstance(questions, list):
        questions = android.get("questions", [])
    if not isinstance(schedules, list):
        schedules = android.get("schedules", [])

    return {
        "questions": questions if isinstance(questions, list) else [],
        "schedules": schedules if isinstance(schedules, list) else [],
    }


def normalize_esm_question(question: dict, index: int) -> dict:
    normalized = dict(question)
    normalized["id"] = normalized.get("id", index + 1)
    normalized["esm_submit"] = normalized.get("esm_submit") or "Submit"
    return normalized


def build_android_esm_questions(source: dict) -> list[dict]:
    shared_esm = get_shared_esm(source)
    return [
        normalize_esm_question(question, index)
        for index, question in enumerate(shared_esm["questions"])
        if isinstance(question, dict)
    ]


def build_android_esm_schedules(source: dict) -> list[dict]:
    return [
        dict(schedule)
        for schedule in get_shared_esm(source)["schedules"]
        if isinstance(schedule, dict)
    ]


def ios_esm_question_payload(question: dict, trigger: str) -> dict:
    payload = {}
    for key in ("esm_type", "esm_title"):
        if key in question:
            payload[key] = question[key]
    payload["esm_instructions"] = question.get(
        "esm_instructions", question.get("instructions", "")
    )
    payload["esm_submit"] = question.get("esm_submit") or "Submit"
    payload["esm_trigger"] = question.get("esm_trigger") or trigger

    for key, value in question.items():
        if not key.startswith("esm_"):
            continue
        if key in {"esm_instructions", "esm_submit", "esm_trigger"}:
            continue
        if key not in payload:
            payload[key] = value

    return payload


def ios_esm_schedule_hours(schedule: dict) -> list[int]:
    hours = schedule.get("hours")
    if isinstance(hours, list):
        return hours

    firsthour = schedule.get("firsthour")
    lasthour = schedule.get("lasthour")
    if isinstance(firsthour, str) and isinstance(lasthour, str):
        try:
            start = int(firsthour[:2])
            end = int(lasthour[:2])
        except ValueError:
            return list(range(24))
        if start <= end:
            return list(range(start, end + 1))
        return list(range(start, 24)) + list(range(0, end + 1))

    return list(range(24))


def build_ios_esm_config(source: dict) -> list[dict]:
    questions = build_android_esm_questions(source)
    schedules = build_android_esm_schedules(source)
    questions_by_id = {question.get("id"): question for question in questions}
    schedules_output = []

    for index, schedule in enumerate(schedules):
        schedule_output = {
            "schedule_id": schedule.get("schedule_id") or f"schedule_{index + 1}",
            "hours": ios_esm_schedule_hours(schedule),
            "notification_title": schedule.get("notification_title")
            or schedule.get("title")
            or f"Schedule {index + 1}",
            "notification_body": schedule.get("notification_body") or "Tap to answer",
            "esms": [],
        }

        for question_id in schedule.get("questions", []):
            question = questions_by_id.get(question_id)
            if not question:
                continue
            schedule_output["esms"].append(
                {
                    "esm": ios_esm_question_payload(
                        question,
                        f"q{question.get('id', len(schedule_output['esms']) + 1)}",
                    )
                }
            )

        schedules_output.append(schedule_output)

    return schedules_output


def build_ios_esm_config_url(settings: dict[str, str | int]) -> str:
    return (
        build_public_base_url(
            str(settings["protocol"]),
            str(settings["public_host"]),
            int(settings["public_port"]),
        )
        + f"/esm/{IOS_ESM_CONFIG_FILENAME}"
    )


def ios_esm_plugin_enabled(source: dict) -> bool:
    android_settings = source.get("android", {}).get("settings", {})
    if "status_plugin_esm_scheduler" in android_settings:
        return bool(android_settings["status_plugin_esm_scheduler"])

    ios_plugins = source.get("ios", {}).get("plugins", {})
    for plugin_name in ("plugin_ios_esm", "plugin_esm_scheduler"):
        if plugin_name in ios_plugins:
            return bool(ios_plugins[plugin_name])

    return bool(build_ios_esm_config(source))


def upsert_ios_esm_plugin(config: dict, esm_url: str, enabled: bool) -> None:
    plugins = config.setdefault("plugins", [])
    target_plugin = None
    for plugin in plugins:
        if (
            plugin.get("plugin") == "plugin_ios_esm"
            or plugin.get("package_name") == "com.aware.plugin.ios_esm"
        ):
            target_plugin = plugin
            break

    if target_plugin is None:
        target_plugin = {
            "package_name": "com.aware.plugin.ios_esm",
            "plugin": "plugin_ios_esm",
            "settings": [],
        }
        plugins.append(target_plugin)

    target_plugin["package_name"] = "com.aware.plugin.ios_esm"
    target_plugin["plugin"] = "plugin_ios_esm"
    settings = target_plugin.setdefault("settings", [])
    settings_by_name = {setting.get("setting"): setting for setting in settings}

    status_setting = settings_by_name.get("status_plugin_ios_esm")
    if status_setting is None:
        status_setting = {
            "setting": "status_plugin_ios_esm",
            "title": "Active",
        }
        settings.append(status_setting)
    status_setting["defaultValue"] = to_bool_string(enabled)

    url_setting = settings_by_name.get("plugin_ios_esm_config_url")
    if url_setting is None:
        url_setting = {
            "setting": "plugin_ios_esm_config_url",
            "title": "iOS ESM Config URL",
        }
        settings.append(url_setting)
    url_setting["defaultValue"] = esm_url


def source_database_host(
    database: dict[str, object], platform_key: str | None = None
) -> str:
    platform_host = ""
    if platform_key:
        platform_db = database.get(platform_key, {})
        if isinstance(platform_db, dict):
            platform_host = str(platform_db.get("host", "")).strip()

    shared_host = str(database.get("host", "")).strip()
    return platform_host or shared_host or "db.internal"


def resolve_database_host(
    database: dict[str, object],
    fallback_host: str,
    platform_key: str | None = None,
) -> str:
    host = source_database_host(database, platform_key)
    if host in {"", "db.internal", "mysql", "localhost", "127.0.0.1", "0.0.0.0"}:
        return fallback_host
    return host


# Android setting keys that have the same name in the iOS config.
_ANDROID_TO_IOS_DIRECT = frozenset({
    # webservice / sync
    "webservice_wifi_only", "webservice_charging", "frequency_webservice",
    "frequency_clean_old_data", "webservice_silent", "fallback_network",
    "remind_to_charge", "foreground_priority",
    # debug
    "debug_flag",
    # applications
    "status_notifications", "status_crashes", "frequency_applications",
    "status_keyboard", "mask_keyboard", "status_installations",
    # screen
    "status_touch", "mask_touch_text",
    # locations (exact-match subset)
    "status_location_gps", "min_location_gps_accuracy",
    "status_location_network", "min_location_network_accuracy",
    "status_location_passive", "location_expiration_time", "location_save_all",
    # communication / network (granular)
    "status_calls", "status_messages",
    "status_network_events", "status_network_traffic",
    # plugin: ambient noise
    "status_plugin_ambient_noise",
    "frequency_plugin_ambient_noise", "plugin_ambient_noise_sample_size",
    "plugin_ambient_noise_silence_threshold", "plugin_ambient_noise_no_raw",
    # plugin: openweather
    "status_plugin_openweather", "plugin_openweather_frequency",
    # plugin: google activity recognition
    "status_plugin_google_activity_recognition",
    "frequency_plugin_google_activity_recognition",
    # plugin: sentimental
    "status_plugin_sentimental",
    # plugin: esm scheduler
    "status_plugin_esm_scheduler",
    # plugin: fitbit
    "status_plugin_fitbit", "units_plugin_fitbit",
    "fitbit_granularity", "fitbit_hr_granularity",
    "plugin_fitbit_frequency", "api_key_plugin_fitbit", "api_secret_plugin_fitbit",
    # plugin: sensortag
    "status_plugin_sensortag", "frequency_plugin_sensortag",
    # plugin: contacts list
    "status_plugin_contacts", "frequency_plugin_contacts",
    # plugin: google auth
    "status_plugin_google_login",
    # plugin: google fused location
    "status_google_fused_location", "frequency_google_fused_location",
    "max_frequency_google_fused_location", "fallback_location_timeout",
    "location_sensitivity", "accuracy_google_fused_location",
    # plugin: device usage
    "status_plugin_device_usage",
    # plugin: conversations
    "status_plugin_studentlife_audio", "plugin_conversations_delay",
    "plugin_conversations_off_duty", "plugin_conversations_length",
})

# Android setting keys that appear under a different name in the iOS config.
_ANDROID_TO_IOS_RENAME: dict[str, str] = {
    "frequency_gps": "frequency_location_gps",
    "frequency_network": "frequency_location_network",
    "plugin_openweather_api_key": "api_key_plugin_openweather",
    "plugin_openweather_measurement_units": "units_plugin_openweather",
}


def build_ios_sensor_settings(source: dict) -> dict[str, object]:
    ios_sensors = source.get("ios", {}).get("sensors", {})
    android_settings = source.get("android", {}).get("settings", {})
    sensor_settings: dict[str, object] = {}

    # Step 1: ios.sensors toggles as baseline (covers iOS-only sensors like
    # significant_motion, websocket, mqtt that have no Android equivalent).
    for sensor_name, enabled in ios_sensors.items():
        if sensor_name == "network":
            sensor_settings["status_network_events"] = enabled
            sensor_settings["status_network_traffic"] = enabled
        elif sensor_name == "communication":
            sensor_settings["status_calls"] = enabled
            sensor_settings["status_messages"] = enabled
        elif sensor_name == "locations":
            sensor_settings["status_location_gps"] = enabled
        else:
            sensor_settings[f"status_{sensor_name}"] = enabled

    # Step 2: android.settings override with higher priority (more granular,
    # and represents the researcher's intent as set through the configurator).
    for key in _ANDROID_TO_IOS_DIRECT:
        if key in android_settings:
            sensor_settings[key] = android_settings[key]
    for android_key, ios_key in _ANDROID_TO_IOS_RENAME.items():
        if android_key in android_settings:
            sensor_settings[ios_key] = android_settings[android_key]

    # Step 3: shared sensor settings (frequency/threshold/enforce) take
    # highest priority as the authoritative cross-platform values.
    sensor_settings.update(build_shared_sensor_settings(source))
    return sensor_settings


def update_sensor_settings(sensor_items: list[dict], values: dict[str, object]) -> None:
    for item in sensor_items:
        setting = item.get("setting")
        if setting in values:
            item["value"] = values[setting]


def update_ios_sensor_defaults(sensor_items: list[dict], values: dict[str, object]) -> None:
    for sensor in sensor_items:
        for setting in sensor.get("settings", []):
            setting_name = setting.get("setting")
            if setting_name not in values:
                continue
            value = values[setting_name]
            if isinstance(value, bool):
                setting["defaultValue"] = to_bool_string(value)
            else:
                setting["defaultValue"] = str(value)


def update_ios_plugin_defaults(plugin_items: list[dict], values: dict[str, object]) -> None:
    for plugin in plugin_items:
        plugin_name = plugin.get("plugin") or plugin.get("package_name")
        if plugin_name not in values:
            continue
        enabled = values[plugin_name]
        for setting in plugin.get("settings", []):
            if setting.get("setting", "").startswith("status_"):
                setting["defaultValue"] = to_bool_string(enabled)
                break


def update_ios_plugin_settings(plugin_items: list[dict], values: dict[str, object]) -> None:
    """Apply android.settings sub-setting values to all iOS plugin settings."""
    for plugin in plugin_items:
        for setting in plugin.get("settings", []):
            setting_name = setting.get("setting")
            if setting_name in values:
                value = values[setting_name]
                if isinstance(value, bool):
                    setting["defaultValue"] = to_bool_string(value)
                else:
                    setting["defaultValue"] = str(value)


def serialize_android_config(
    source: dict,
    settings: dict[str, str | int],
    template_path: pathlib.Path,
    study_id: str = "",
) -> dict:
    config = load_android_template(template_path)
    study = source["study"]
    researcher = source["researcher"]
    android_db = source["database"]["android"]
    android = source["android"]
    android_settings = dict(android.get("settings", {}))
    android_settings.update(build_shared_sensor_settings(source))

    config["_id"] = study_id or study["id"]
    config["study_info"] = {
        "study_title": study["title"],
        "study_description": study["description"],
        "researcher_first": researcher["first_name"],
        "researcher_last": researcher["last_name"],
        "researcher_contact": researcher["contact"],
    }
    config["database"] = {
        "database_host": resolve_database_host(
            source["database"],
            str(settings["android_database_host"]),
            "android",
        ),
        "database_port": str(android_db["port"]),
        "database_name": android_db["name"],
        "database_username": android_db["username"],
        "database_password": android_db["password"],
        "rootUsername": "-",
        "rootPassword": "-",
        "config_without_password": android_db.get("config_without_password", False),
        "require_ssl": android_db.get("require_ssl", False),
    }
    config["createdAt"] = android.get("created_at", "")
    config["updatedAt"] = android.get("updated_at") or datetime.now(timezone.utc).isoformat()
    config["questions"] = build_android_esm_questions(source)
    config["schedules"] = build_android_esm_schedules(source)
    ios_sensors = source.get("ios", {}).get("sensors", {})
    config["ios_sensors"] = {
        sensor_name: bool(ios_sensors.get(sensor_name, False))
        for sensor_name in IOS_ONLY_SENSOR_NAMES
    }
    update_sensor_settings(config["sensors"], android_settings)
    return config


def update_ios_server_config(
    config: dict,
    source_database: dict[str, object],
    settings: dict[str, str | int],
) -> None:
    server = config.setdefault("server", {})
    server["database_engine"] = "mysql"
    server["database_host"] = resolve_database_host(
        source_database,
        str(settings["micro_database_host"]),
        "ios",
    )
    server["database_name"] = settings["ios_database_name"]
    server["database_user"] = settings["ios_database_user"]
    server["database_pwd"] = settings["ios_database_password"]
    server["database_port"] = settings["ios_database_port"]
    server["server_host"] = settings["ios_server_host"]
    server["server_port"] = settings["ios_server_port"]
    server["websocket_port"] = settings["ios_websocket_port"]
    server["external_server_host"] = settings["external_server_host"]
    server["external_server_port"] = settings["public_port"]
    server["path_fullchain_pem"] = settings["ios_path_fullchain_pem"]
    server["path_key_pem"] = settings["ios_path_key_pem"]


def apply_ios_study_config(config: dict, source: dict, existing_config: dict | None, study_key: str = "") -> dict:
    study_source = source["study"]
    researcher = source["researcher"]
    ios_source = source["ios"]
    study = config.setdefault("study", {})
    study["study_number"] = ios_source.get("study_number", 1)
    study["study_name"] = study_source["title"]
    study["study_active"] = study_source.get("active", True)
    study["study_start"] = study_source.get("start_timestamp", 0)
    study["study_description"] = study_source["description"]
    study["researcher_first"] = researcher["first_name"]
    study["researcher_last"] = researcher["last_name"]
    study["researcher_contact"] = researcher["contact"]
    if not study_key or study_key in {"your_study_key", "CHANGE_ME"}:
        study_key = str(ios_source.get("study_key", "")).strip()
        if existing_config:
            existing_study = existing_config.get("study", {})
            existing_study_key = str(existing_study.get("study_key", "")).strip()
            if study_key in {"", "your_study_key", "CHANGE_ME"} and existing_study_key:
                study_key = existing_study_key
        if not study_key or study_key in {"your_study_key", "CHANGE_ME"}:
            study_key = secrets.token_hex(6)
    study["study_key"] = study_key
    return study


def update_ios_webservice_url(config: dict, settings: dict[str, str | int]) -> None:
    webservice_url = (
        build_public_base_url(
            str(settings["protocol"]),
            str(settings["public_host"]),
            int(settings["public_port"]),
        )
        + "/index.php/"
    )

    for sensor in config.get("sensors", []):
        if sensor.get("sensor") == "webservice":
            for setting in sensor.get("settings", []):
                if setting.get("setting") == "webservice_server":
                    setting["defaultValue"] = webservice_url
                    return


def serialize_ios_config(
    source: dict,
    settings: dict[str, str | int],
    example_path: pathlib.Path,
    existing_config_path: pathlib.Path,
    study_key: str = "",
) -> tuple[dict, dict]:
    existing_config = load_existing_json(existing_config_path)
    config = load_json(example_path)
    update_ios_server_config(config, source["database"], settings)
    study = apply_ios_study_config(config, source, existing_config, study_key)
    ios_sensor_settings = build_ios_sensor_settings(source)
    update_ios_sensor_defaults(config.get("sensors", []), ios_sensor_settings)
    update_ios_plugin_defaults(config.get("plugins", []), source["ios"].get("plugins", {}))
    update_ios_plugin_settings(config.get("plugins", []), ios_sensor_settings)
    update_ios_webservice_url(config, settings)
    upsert_ios_esm_plugin(
        config,
        build_ios_esm_config_url(settings),
        ios_esm_plugin_enabled(source),
    )
    return config, study
