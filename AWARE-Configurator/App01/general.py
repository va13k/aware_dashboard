import json
import logging
import os
import pathlib
import sys
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt

from aware_light_config_Django import settings

PROJECT_ROOT = pathlib.Path("/project")
if PROJECT_ROOT.exists() and str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared_config.runtime import get_runtime_settings, load_env, normalize_public_env
from shared_config.serializers import (
    COMMON_SHARED_SENSOR_FIELDS,
    build_sensor_setting_name,
    serialize_android_config,
    serialize_ios_config,
)

logger = logging.getLogger(__name__)
storage_path = settings.STORAGE_DIR
STUDY_CONFIG_FILE_NAME = "studyConfig.json"
SOURCE_PATH = PROJECT_ROOT / "source.json"
ENV_PATH = PROJECT_ROOT / ".env"
ANDROID_TEMPLATE_PATH = (
    PROJECT_ROOT / "AWARE-Configurator" / "reactapp" / "public" / "study-config.json"
)
IOS_EXAMPLE_PATH = PROJECT_ROOT / "aware-micro-server" / "aware-config.example.json"
IOS_CONFIG_PATH = PROJECT_ROOT / "aware-micro-server" / "aware-config.json"
STUDY_CONFIG_PATH = pathlib.Path(storage_path) / STUDY_CONFIG_FILE_NAME
ABSTRACT_DATABASE_HOST = "db.internal"


@ensure_csrf_cookie
def get_token(request):
    return HttpResponse("success")


@csrf_exempt
def save_json_file(request):
    if request.method == "POST":
        json_str = request.body
        json_dict = json.loads(json_str)
        raw_text = json_dict.get('text', None)
        try:
            content = json.loads(raw_text)
        except (TypeError, json.JSONDecodeError):
            content = raw_text

        file_name = save(content)
        return HttpResponse(
            json.dumps({
                "success": True,
                "file_name": file_name,
                "url": f"/studies/files/{file_name}",
            }),
            content_type="application/json",
        )

    return HttpResponse(
        json.dumps({"success": False, "message": "Invalid request method"}),
        status=405,
        content_type="application/json",
    )


def save(content):
    folder = os.path.exists(storage_path)
    if not folder:
        os.makedirs(storage_path)

    source = load_source()
    source = update_source_from_android_config(source, content)
    write_json(SOURCE_PATH, source)
    write_outputs(source)

    return STUDY_CONFIG_FILE_NAME


def load_source():
    with open(SOURCE_PATH, 'r', encoding='utf-8') as file:
        return json.load(file)


def write_json(path, content):
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(content, file, indent=2)
        file.write("\n")


def runtime_database_host() -> str:
    env = normalize_public_env(load_env(ENV_PATH))
    settings = get_runtime_settings(env)
    return str(settings["android_database_host"]).strip()


def normalize_database_host_for_source(raw_host: object) -> str:
    host = str(raw_host or "").strip()
    if not host:
        return ABSTRACT_DATABASE_HOST

    if host in {
        ABSTRACT_DATABASE_HOST,
        "mysql",
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        runtime_database_host(),
    }:
        return ABSTRACT_DATABASE_HOST

    return host


def sync_database_host(source: dict, raw_host: object) -> None:
    normalized_host = normalize_database_host_for_source(raw_host)
    database = source.setdefault("database", {})
    database["host"] = normalized_host

    for platform_name in ("android", "ios"):
        platform_db = database.setdefault(platform_name, {})
        if isinstance(platform_db, dict):
            platform_db.pop("host", None)


def update_source_from_android_config(source, content):
    study_info = content.get("study_info", {})
    database = content.get("database", {})

    source["study"]["id"] = content.get("_id", source["study"]["id"])
    source["study"]["title"] = study_info.get(
        "study_title", source["study"]["title"]
    )
    source["study"]["description"] = study_info.get(
        "study_description", source["study"]["description"]
    )
    source["researcher"]["first_name"] = study_info.get(
        "researcher_first", source["researcher"]["first_name"]
    )
    source["researcher"]["last_name"] = study_info.get(
        "researcher_last", source["researcher"]["last_name"]
    )
    source["researcher"]["contact"] = study_info.get(
        "researcher_contact", source["researcher"]["contact"]
    )

    if database:
        android_db = source["database"]["android"]
        sync_database_host(
            source,
            database.get("database_host", source.get("database", {}).get("host", "")),
        )
        android_db["port"] = int(database.get("database_port", android_db["port"]))
        android_db["name"] = database.get("database_name", android_db["name"])
        android_db["username"] = database.get(
            "database_username", android_db["username"]
        )
        android_db["password"] = database.get(
            "database_password", android_db["password"]
        )
        android_db["config_without_password"] = database.get(
            "config_without_password", android_db.get("config_without_password", False)
        )
        android_db["require_ssl"] = database.get(
            "require_ssl", android_db.get("require_ssl", False)
        )

    source["android"]["created_at"] = content.get(
        "createdAt", source["android"].get("created_at", "")
    )
    source["android"]["updated_at"] = content.get(
        "updatedAt", source["android"].get("updated_at", "")
    )
    source["android"]["questions"] = content.get("questions", [])
    source["android"]["schedules"] = content.get("schedules", [])
    android_settings = {
        item["setting"]: item.get("value")
        for item in content.get("sensors", [])
        if item.get("setting")
    }
    sync_shared_sensors_from_android_settings(source, android_settings)
    source["android"]["settings"] = android_settings
    return source


def sync_shared_sensors_from_android_settings(source, android_settings):
    shared_sensors = source.setdefault("shared", {}).setdefault("sensors", {})
    for sensor_name, field_names in COMMON_SHARED_SENSOR_FIELDS.items():
        sensor_shared = shared_sensors.setdefault(sensor_name, {})
        if isinstance(sensor_shared, bool):
            sensor_shared = {"enabled": sensor_shared}
            shared_sensors[sensor_name] = sensor_shared
        for field_name in field_names:
            setting_name = build_sensor_setting_name(sensor_name, field_name)
            if setting_name in android_settings:
                sensor_shared[field_name] = android_settings.pop(setting_name)


def build_ios_settings(source):
    env = normalize_public_env(load_env(ENV_PATH))
    settings = get_runtime_settings(env)
    ios_db = source["database"]["ios"]
    ios_server = source["ios"]["server"]
    settings.update(
        {
            "ios_database_name": ios_db["name"],
            "ios_database_user": ios_db["username"],
            "ios_database_password": ios_db["password"],
            "ios_database_port": ios_db["port"],
            "ios_server_host": ios_server["server_host"],
            "ios_server_port": ios_server["server_port"],
            "ios_websocket_port": ios_server["websocket_port"],
            "ios_path_fullchain_pem": ios_server.get("path_fullchain_pem", ""),
            "ios_path_key_pem": ios_server.get("path_key_pem", ""),
        }
    )
    return settings


def write_outputs(source):
    settings = build_ios_settings(source)
    android_config = serialize_android_config(source, settings, ANDROID_TEMPLATE_PATH)
    ios_config, _study = serialize_ios_config(
        source,
        settings,
        IOS_EXAMPLE_PATH,
        IOS_CONFIG_PATH,
    )
    write_json(STUDY_CONFIG_PATH, android_config)
    write_json(IOS_CONFIG_PATH, ios_config)
