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


def build_ios_sensor_settings(source: dict) -> dict[str, object]:
    ios_sensors = source.get("ios", {}).get("sensors", {})
    sensor_settings: dict[str, object] = {}
    for sensor_name, enabled in ios_sensors.items():
        if sensor_name == "network":
            # aware-config.json splits network into two separate settings
            sensor_settings["status_network_events"] = enabled
            sensor_settings["status_network_traffic"] = enabled
        elif sensor_name == "communication":
            # aware-config.json splits communication into calls and messages
            sensor_settings["status_calls"] = enabled
            sensor_settings["status_messages"] = enabled
        elif sensor_name == "locations":
            # aware-config.json uses status_location_gps as the primary location toggle
            sensor_settings["status_location_gps"] = enabled
        else:
            sensor_settings[f"status_{sensor_name}"] = enabled

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


def serialize_android_config(
    source: dict,
    settings: dict[str, str | int],
    template_path: pathlib.Path,
) -> dict:
    config = load_android_template(template_path)
    study = source["study"]
    researcher = source["researcher"]
    android_db = source["database"]["android"]
    android = source["android"]
    android_settings = dict(android.get("settings", {}))
    android_settings.update(build_shared_sensor_settings(source))

    config["_id"] = study["id"]
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
    config["questions"] = [
        {**question, "id": question.get("id", index + 1)}
        for index, question in enumerate(android.get("questions", []))
    ]
    config["schedules"] = android.get("schedules", [])
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


def apply_ios_study_config(config: dict, source: dict, existing_config: dict | None) -> dict:
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
) -> tuple[dict, dict]:
    existing_config = load_existing_json(existing_config_path)
    config = load_json(example_path)
    update_ios_server_config(config, source["database"], settings)
    study = apply_ios_study_config(config, source, existing_config)
    update_ios_sensor_defaults(config.get("sensors", []), build_ios_sensor_settings(source))
    update_ios_plugin_defaults(config.get("plugins", []), source["ios"].get("plugins", {}))
    update_ios_webservice_url(config, settings)
    return config, study
