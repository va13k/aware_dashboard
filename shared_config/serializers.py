import json
import pathlib
import secrets
from datetime import datetime, timezone


def load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_existing_json(path: pathlib.Path) -> dict | None:
    if not path.exists():
        return None
    return load_json(path)


def to_bool_string(value: object) -> str:
    return "true" if bool(value) else "false"


def update_sensor_settings(sensor_items: list[dict], values: dict[str, object]) -> None:
    for item in sensor_items:
        setting = item.get("setting")
        if setting in values:
            item["value"] = values[setting]


def update_ios_sensor_defaults(sensor_items: list[dict], values: dict[str, object]) -> None:
    for sensor in sensor_items:
        sensor_name = sensor.get("sensor")
        if sensor_name in values:
            enabled = values[sensor_name]
            for setting in sensor.get("settings", []):
                if setting.get("setting") == f"status_{sensor_name}":
                    setting["defaultValue"] = to_bool_string(enabled)


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
    config = load_json(template_path)
    study = source["study"]
    researcher = source["researcher"]
    android_db = source["database"]["android"]
    android = source["android"]

    config["_id"] = study["id"]
    config["study_info"] = {
        "study_title": study["title"],
        "study_description": study["description"],
        "researcher_first": researcher["first_name"],
        "researcher_last": researcher["last_name"],
        "researcher_contact": researcher["contact"],
    }
    config["database"] = {
        "database_host": android_db["host"] or str(settings["database_host"]),
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
    update_sensor_settings(config["sensors"], android.get("settings", {}))
    return config


def update_ios_server_config(config: dict, settings: dict[str, str | int]) -> None:
    server = config.setdefault("server", {})
    server["database_engine"] = "mysql"
    server["database_host"] = settings["database_host"]
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
    webservice_url = f"{settings['protocol']}://{settings['public_host']}"
    if not (
        (settings["protocol"] == "http" and settings["public_port"] == 80)
        or (settings["protocol"] == "https" and settings["public_port"] == 443)
    ):
        webservice_url += f":{settings['public_port']}"
    webservice_url += "/index.php/"

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
    update_ios_server_config(config, settings)
    study = apply_ios_study_config(config, source, existing_config)
    update_ios_sensor_defaults(config.get("sensors", []), source["ios"].get("sensors", {}))
    update_ios_plugin_defaults(config.get("plugins", []), source["ios"].get("plugins", {}))
    update_ios_webservice_url(config, settings)
    return config, study
