import json
import logging
import os
import pathlib
import sys
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt

from aware_light_config_Django import settings

# settings.py already resolves PROJECT_ROOT (Docker's /project mount or the
# repo root locally) and adds it to sys.path, so shared_config is importable.
PROJECT_ROOT = settings.PROJECT_ROOT

from shared_config import database as database_model
from shared_config import dataflow, placement
from shared_config.certificates import read_certificate
from shared_config.database import android_credentials, android_ingest_account
from shared_config.source_store import read_source, update_source
from shared_config.runtime import (
    SECRET_MODE,
    SHARED_MODE,
    atomic_write_text,
    build_public_base_url,
    get_runtime_settings,
    load_env,
    normalize_public_env,
    set_env_value,
)
from shared_config.serializers import (
    ANDROID_ONLY_SHARED_SENSOR_NAMES,
    COMMON_SHARED_SENSOR_FIELDS,
    IOS_ESM_CONFIG_FILENAME,
    IOS_ONLY_SENSOR_NAMES,
    build_android_micro_config,
    build_ios_esm_config,
    build_ios_plugin_settings,
    build_sensor_setting_name,
    serialize_android_config,
    serialize_ios_config,
    update_ios_plugin_settings,
)
from App01.participant_db import ParticipantDbError, apply_account_credentials

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
#: The Android micro-server's own configuration, which carries the account it
#: authenticates with. Rewritten alongside the study configs so a credential change
#: reaches the server that uses it.
ANDROID_MICRO_CONFIG_PATH = (
    PROJECT_ROOT / "aware-micro-server" / "aware-config.android.json"
)
IOS_ESM_CONFIG_PATH = PROJECT_ROOT / "aware-micro-server" / "esm" / IOS_ESM_CONFIG_FILENAME
STUDY_CONFIG_PATH = pathlib.Path(storage_path) / STUDY_CONFIG_FILE_NAME
ABSTRACT_DATABASE_HOST = "db.internal"


@ensure_csrf_cookie
def get_token(request):
    return HttpResponse("success")


def deployment_facts(request):
    """What the study is running on, for the form that describes it.

    The dataflow is read from the study model rather than from the browser, so the
    Configurator shows the study's own answer instead of whatever a form last
    defaulted to. It is reported rather than offered: changing it re-addresses the
    study, so every enrolled participant has to join again, and it takes effect
    only when the deployment is brought up again -- neither of which a page inside
    a container can do.

    `protocol` and `mysql_reachable_externally` are the two facts the webservice
    path is judged on: whether the hop a phone makes is encrypted, and whether the
    database the server writes to is reachable beyond this host.

    `android_ingest_account` is the MySQL account the study's writes authenticate as,
    which is what the form's password field changes.
    """
    if request.method != "GET":
        return HttpResponse(
            json.dumps({"success": False, "msg": "Invalid request method"}),
            status=405,
            content_type="application/json",
        )

    source = read_source()
    env = load_env(ENV_PATH)
    bind = str(env.get("MYSQL_BIND_ADDRESS", "0.0.0.0")).strip()
    return HttpResponse(
        json.dumps(
            {
                "android_dataflow": dataflow.declared(source, "android"),
                # Where the database runs. The page needs it to say who supplies the
                # certificate authority: a bundled database publishes its own, a
                # named one has an authority only its administrator holds.
                "database_placement": placement.declared(source),
                "ios_dataflow": dataflow.declared(source, "ios"),
                # Named so the password field says which account it changes. The
                # dataflow decides the holder, and a field that reads as the
                # participants' while it changes the server's invites a researcher
                # to rotate the wrong credential.
                "android_ingest_account": android_credentials(
                    source.get("database", {}), dataflow.declared(source, "android")
                )[0],
                # What a phone verifies the database against, so the page can state
                # the connection it actually has rather than warn about one it might.
                # `generated` is the authority a bundled MySQL signs with, which the
                # deploy reads out of the container and publishes; `supplied` is one
                # the researcher pasted; `none` leaves the connection encrypted and
                # unverified, which only an external database can end up in.
                "database_authority": (
                    "supplied"
                    if database_model.tls_authority(source.get("database", {}))
                    else (
                        "generated"
                        if placement.declared(source) == placement.BUNDLED
                        else "none"
                    )
                ),
                # Whether this study's database connection is encrypted at all. A
                # database this deployment runs always is; one the researcher named
                # answers to its owner, so the page states the study's own answer
                # rather than a promise it cannot keep for a server it does not run.
                "database_require_tls": database_model.tls_required(
                    source.get("database", {})
                ),
                # Where the broker this deployment runs actually is. The dashboard
                # publishes there, so a study pointing phones elsewhere would listen
                # where nothing is sent -- the address is stated, not offered.
                "mqtt_server": str(
                    (source.get("android", {}).get("settings") or {}).get("mqtt_server")
                    or ""
                ),
                "mqtt_port": (source.get("android", {}).get("settings") or {}).get(
                    "mqtt_port"
                ),
                "protocol": str(env.get("PROTOCOL", "http")).strip().lower(),
                # A published port narrowed to loopback is reachable only from the
                # host itself, which is where the micro-server's own hop starts.
                "mysql_reachable_externally": bind not in ("127.0.0.1", "::1", "localhost"),
            }
        ),
        content_type="application/json",
    )


def get_participant_password(request):
    """Return the ingest account's password for the study form.

    Whichever account the study's dataflow puts on the ingest path, so the field
    reveals the password it also changes.

    serialize_android_config redacts the password to "-" when
    config_without_password is on, and that config is served from the public
    /studies/files/ path devices download, so the Configurator cannot read the
    real value back from it and the form field would always load empty. On the
    webservice path the served config carries no database block at all, which
    leaves the field with nothing to load either. This route lives under
    /configurator/, which nginx gates behind the researcher login, so the password
    is only handed to an authenticated researcher.
    """
    if request.method != "GET":
        return HttpResponse(
            json.dumps({"success": False, "msg": "Invalid request method"}),
            status=405,
            content_type="application/json",
        )

    source = read_source()
    _, password = android_credentials(
        source.get("database", {}), dataflow.declared(source, "android")
    )
    response = HttpResponse(
        json.dumps({"password": password}),
        content_type="application/json",
    )
    # Never let a secret settle in a browser or proxy cache.
    response["Cache-Control"] = "no-store"
    return response


@csrf_exempt
def save_json_file(request):
    if request.method != "POST":
        return HttpResponse(
            json.dumps({"success": False, "msg": "Invalid request method"}),
            status=405,
            content_type="application/json",
        )

    json_str = request.body
    json_dict = json.loads(json_str)
    raw_text = json_dict.get("text", None)
    try:
        content = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError):
        content = raw_text

    try:
        file_name = save(content)
    except ValueError as exc:
        # write_outputs refuses a dataflow this deployment cannot honour, before
        # anything is generated. The reason names what is missing, so it is worth
        # showing rather than collapsing into a server error.
        logger.error("Save refused: %s", exc)
        return HttpResponse(
            json.dumps({"success": False, "msg": str(exc)}),
            status=400,
            content_type="application/json",
        )
    except ParticipantDbError as exc:
        # The credential change was rejected, so nothing was written: the served
        # config and the database stay on their previous, consistent values.
        logger.error("Save aborted: %s", exc)
        return HttpResponse(
            json.dumps({"success": False, "msg": str(exc)}),
            status=502,
            content_type="application/json",
        )

    return HttpResponse(
        json.dumps(
            {
                "success": True,
                "file_name": file_name,
                "url": f"/studies/files/{file_name}",
            }
        ),
        content_type="application/json",
    )


def save(content):
    folder = os.path.exists(storage_path)
    if not folder:
        os.makedirs(storage_path)

    # Merge the submitted study config into the shared source and, when the
    # participant credentials change, apply them to MySQL within the same
    # locked update. If the database rejects the change the update raises and
    # source.json is left untouched, so the served config below is only
    # regenerated once the new credentials are actually in effect.
    source = update_source(lambda s: _merge_and_sync_credentials(s, content))
    write_outputs(source)

    return STUDY_CONFIG_FILE_NAME


def _merge_and_sync_credentials(source, content):
    previous_credentials = _ingest_credentials(source)
    update_source_from_android_config(source, content)
    new_credentials = _ingest_credentials(source)

    # Only talk to MySQL when the ingest credentials actually change, so
    # routine edits (questions, schedules, sensors) never depend on the
    # database being reachable.
    if new_credentials != previous_credentials:
        _sync_ingest_credentials(source)

    return source


def _ingest_account(source):
    """Where the account this study's Android ingest authenticates as is kept.

    The dataflow decides the holder: a phone opens the database itself on the direct
    path, and the micro-server performs every write on the webservice one. So the one
    password field in the form governs one account at a time, and this is the answer
    every reader of that field starts from.
    """
    return android_ingest_account(dataflow.declared(source, "android"))


def _ingest_credentials(source):
    """Credentials that account should have: (username, password, require_ssl).

    The username rides along because the account is part of what has to be in
    effect: a study whose dataflow names a different holder needs that holder's
    credentials applied, not the previous one's.

    config_without_password does NOT change the account — it only controls
    whether the served study config embeds the password or omits it so the
    participant enters it when joining. The account always keeps its password.
    """
    username, password = android_credentials(
        source.get("database", {}), dataflow.declared(source, "android")
    )
    return (username, password, database_model.tls_required(source.get("database", {})))


def _mysql_admin_settings(source=None):
    """Where the account changes are applied, resolved the way every service does.

    The study's own declaration is the fallback rather than the compose name, so a
    study whose database is a host the researcher named has its accounts altered on
    that host. Naming the bundled service unconditionally would send the change to a
    container that is not running on that placement, and the save would fail on a
    study whose database is perfectly reachable.
    """
    env = load_env(ENV_PATH)

    def pick(key, default=""):
        return os.environ.get(key) or str(env.get(key, "")).strip() or default

    databases = (source or {}).get("database") or {}
    return {
        "host": pick("MYSQL_HOST", database_model.service_host(databases)),
        "port": int(pick("MYSQL_PORT", str(database_model.platform_port(databases, "android")))),
        "root_password": pick("MYSQL_ROOT_PASSWORD"),
    }


def _sync_ingest_credentials(source):
    """Apply the study's ingest credentials to the account that holds them.

    One account per dataflow, so the change lands on the one the study writes with:
    the participant account on the direct path, the micro-server's on the webservice
    path. Each keeps its own password, so changing one leaves the other as it was.
    """
    username, password, require_ssl = _ingest_credentials(source)
    admin = _mysql_admin_settings(source)
    apply_account_credentials(
        host=admin["host"],
        port=admin["port"],
        root_password=admin["root_password"],
        username=username,
        password=password,
        require_ssl=require_ssl,
    )

    # .env is the single source of truth for these passwords: the deployment step
    # seeds source.json from it and MySQL's first-boot script applies it. Recording
    # the new password under this account's own variable keeps all three in
    # agreement, so re-running the wizard cannot hand the study a stale password.
    # Only after MySQL accepted the change, otherwise .env would advertise a
    # password the account does not have.
    set_env_value(ENV_PATH, _ingest_account(source)["env_key"], password)


def write_json(path, content, mode=SHARED_MODE):
    # These configs are read back by other containers (micro-server's appuser,
    # nginx) and by devices, so they default to SHARED_MODE rather than the
    # 0600 an atomic swap would otherwise leave behind.
    atomic_write_text(path, json.dumps(content, indent=2) + "\n", mode)


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

    # The dataflow the study already declares, kept as it is. It travels in the
    # config this round-trips, and a browser holds its own copy of that config, so
    # taking the submitted value would let a stale form re-address a running study
    # -- every enrolled phone joined at an address this decides. It is also half a
    # deployment setting: the published database port follows from it, and only
    # bringing the deployment up again applies that. So it is reported here and
    # changed by running setup.
    declared = source.setdefault("deployment", {}).setdefault("dataflow", {})
    declared.setdefault("android", dataflow.DEFAULTS["android"])
    declared.setdefault("ios", dataflow.WEBSERVICE)
    android_dataflow = dataflow.declared(source, "android")

    source["study"]["id"] = content.get("_id", source["study"]["id"])
    source["study"]["title"] = study_info.get("study_title", source["study"]["title"])
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
        android_db["username"] = database.get("database_username", android_db["username"])
        # config_without_password redacts the served password to "-"; never let
        # that sentinel (or a blank) overwrite the real stored password, so the
        # account and the source of truth keep the working password.
        #
        # Stored under the key belonging to the account this study's dataflow puts on
        # the ingest path, which is the account the save then applies it to: one field
        # in the form, and it governs the credential the study actually writes with.
        incoming_password = database.get("database_password")
        if incoming_password and incoming_password != "-":
            android_db[_ingest_account(source)["password_key"]] = incoming_password
        # What this study asks of the connection, held beside the host it describes.
        # Only a database the researcher named carries an answer: one this deployment
        # runs is administered at both ends and always encrypted, so a value arriving
        # for it is a browser's copy of a control the page never showed.
        if placement.declared(source) == placement.EXTERNAL:
            if "require_ssl" in database:
                database_model.declare_tls(
                    source["database"], require=bool(database.get("require_ssl"))
                )
            # The authority a phone verifies the database against. Kept only when it
            # is a certificate that can actually be read: devices treat an unreadable
            # one as a database they cannot reach and stop uploading, so storing a bad
            # paste would halt the study rather than merely fail to protect it. A
            # blank field clears it, which is how a researcher goes back to
            # encrypted-but-unverified.
            if "ca_certificate" in database:
                supplied = str(database.get("ca_certificate") or "").strip()
                if supplied:
                    cleaned = read_certificate(supplied)
                    if not cleaned:
                        raise ValueError(
                            "That is not a certificate this deployment can read. Paste "
                            "the whole file, from -----BEGIN CERTIFICATE----- to "
                            "-----END CERTIFICATE-----, or leave the field empty to run "
                            "encrypted without verifying the server."
                        )
                else:
                    cleaned = ""
                database_model.declare_tls(source["database"], ca_certificate=cleaned)
        # Whether the published config carries the password. The direct path is the
        # one that publishes it, so it is the path that governs the setting; a
        # browser keeps its own copy of this section, and a value left in it from
        # the other path reaches this boundary either way.
        if android_dataflow == dataflow.DIRECT:
            android_db["config_without_password"] = database.get(
                "config_without_password",
                android_db.get("config_without_password", False),
            )

    source["android"]["created_at"] = content.get(
        "createdAt", source["android"].get("created_at", "")
    )
    source["android"]["updated_at"] = content.get(
        "updatedAt", source["android"].get("updated_at", "")
    )
    questions = content.get("questions", [])
    schedules = content.get("schedules", [])
    sync_shared_esms_from_config(source, questions, schedules)
    # ESM data is stored once in shared.esms — do not duplicate into android.questions/schedules.
    source["android"].pop("questions", None)
    source["android"].pop("schedules", None)
    android_settings = {
        item["setting"]: item.get("value")
        for item in content.get("sensors", [])
        if item.get("setting")
    }
    sync_shared_sensors_from_android_settings(source, android_settings)
    sync_ios_plugin_settings_from_android_settings(source, android_settings)
    source["android"]["settings"] = android_settings
    sync_ios_only_sensors_from_config(source, content.get("ios_sensors", {}))
    sync_ios_plugins_from_config(source, content.get("ios_plugins", {}))
    sync_ios_plugin_settings_from_config(source, content.get("ios_plugin_settings", {}))
    return source


def sync_ios_plugins_from_config(source, ios_plugins):
    if not isinstance(ios_plugins, dict):
        return
    plugins = source.setdefault("ios", {}).setdefault("plugins", {})
    for plugin_name, enabled in ios_plugins.items():
        plugins[plugin_name] = bool(enabled)


def sync_ios_plugin_settings_from_config(source, ios_plugin_settings):
    if not isinstance(ios_plugin_settings, dict):
        return
    plugin_settings = source.setdefault("ios", {}).setdefault("plugin_settings", {})
    plugin_settings.update(ios_plugin_settings)


def sync_ios_plugin_settings_from_android_settings(source, android_settings):
    plugin_settings = source.setdefault("ios", {}).setdefault("plugin_settings", {})
    synced_settings = build_ios_plugin_settings(
        {"android": {"settings": android_settings}, "ios": {"plugin_settings": plugin_settings}}
    )
    plugin_settings.update(synced_settings)


def sync_ios_only_sensors_from_config(source, ios_sensor_settings):
    if not isinstance(ios_sensor_settings, dict):
        return

    ios_sensors = source.setdefault("ios", {}).setdefault("sensors", {})
    for sensor_name in IOS_ONLY_SENSOR_NAMES:
        if sensor_name in ios_sensor_settings:
            ios_sensors[sensor_name] = bool(ios_sensor_settings[sensor_name])


def sync_shared_esms_from_config(source, questions, schedules):
    shared = source.setdefault("shared", {})
    shared["esms"] = {
        "questions": questions if isinstance(questions, list) else [],
        "schedules": schedules if isinstance(schedules, list) else [],
    }


_ANDROID_STATUS_TO_IOS_PLUGIN = {
    "status_plugin_ambient_noise": "plugin_ambient_noise",
    "status_plugin_google_activity_recognition": "plugin_google_activity_recognition",
    "status_plugin_openweather": "plugin_openweather",
    "status_plugin_fitbit": "plugin_fitbit",
    "status_plugin_contacts": "plugin_contacts_list",
    "status_plugin_google_login": "plugin_google_auth",
    "status_google_fused_location": "plugin_google_fused_location",
    "status_plugin_device_usage": "plugin_device_usage",
    "status_plugin_studentlife_audio": "plugin_conversations",
}


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

    # Sync compound Android settings back to their iOS sensor equivalents.
    # build_ios_sensor_settings expands these in the forward direction;
    # here we do the reverse so iOS tracks whatever Android has enabled.
    ios_sensors = source.setdefault("ios", {}).setdefault("sensors", {})
    _sync_ios_compound_sensor(
        ios_sensors,
        android_settings,
        "network",
        ["status_network_events", "status_network_traffic"],
    )
    _sync_ios_compound_sensor(
        ios_sensors,
        android_settings,
        "communication",
        ["communication", "status_calls", "status_messages"],
    )
    _sync_ios_compound_sensor(ios_sensors, android_settings, "locations", ["status_location_gps"])

    # Mirror shared sensor enabled states to ios.sensors so source.json stays
    # consistent. Android-only sensors (applications, light, etc.) are skipped.
    for sensor_name in COMMON_SHARED_SENSOR_FIELDS:
        if sensor_name in ANDROID_ONLY_SHARED_SENSOR_NAMES:
            continue
        sensor_shared = shared_sensors.get(sensor_name, {})
        if isinstance(sensor_shared, bool):
            ios_sensors[sensor_name] = sensor_shared
        elif isinstance(sensor_shared, dict) and "enabled" in sensor_shared:
            ios_sensors[sensor_name] = bool(sensor_shared["enabled"])

    # Sync plugin enable/disable from android.settings to ios.plugins.
    ios_plugins = source.setdefault("ios", {}).setdefault("plugins", {})
    for android_key, ios_plugin_name in _ANDROID_STATUS_TO_IOS_PLUGIN.items():
        if android_key in android_settings:
            ios_plugins[ios_plugin_name] = bool(android_settings[android_key])
    if "status_plugin_esm_scheduler" in android_settings:
        ios_plugins["plugin_ios_esm"] = bool(android_settings["status_plugin_esm_scheduler"])


def _sync_ios_compound_sensor(ios_sensors, android_settings, ios_name, android_keys):
    values = [android_settings[k] for k in android_keys if k in android_settings]
    if values:
        ios_sensors[ios_name] = any(values)


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
    ios_config, study = serialize_ios_config(
        source,
        settings,
        IOS_EXAMPLE_PATH,
        IOS_CONFIG_PATH,
    )
    ios_plugin_settings = source.get("ios", {}).get("plugin_settings", {})
    if ios_plugin_settings:
        update_ios_plugin_settings(ios_config.get("plugins", []), ios_plugin_settings)
    base_url = build_public_base_url(
        str(settings["protocol"]),
        str(settings["public_host"]),
        int(settings["public_port"]),
    )
    # Refused before anything is written. A study half-applied for two dataflows
    # is the failure this check exists to prevent, and the reason names the piece
    # that is missing rather than leaving a researcher hunting for a setting.
    problems = dataflow.validate(source)
    if problems:
        raise ValueError("This dataflow cannot be applied. " + " ".join(problems))

    android_webservice_url = dataflow.android_study_url(
        dataflow.declared(source, "android"),
        base_url,
        study["study_key"],
        STUDY_CONFIG_FILE_NAME,
    )
    android_config = serialize_android_config(
        source, settings, ANDROID_TEMPLATE_PATH, webservice_server=android_webservice_url
    )
    # The Android instance's own configuration, carrying the account it authenticates
    # as. Written here so a credential change reaches the server that uses it, and
    # written on either dataflow for the same reason the deploy writes it on either:
    # the instance runs regardless, and a switch is then a restart rather than a
    # re-deploy. It takes effect when the container next starts.
    android_micro = build_android_micro_config(
        source,
        settings,
        study["study_key"],
        dataflow.ANDROID_STUDY_NUMBER,
        join_url=android_webservice_url,
    )
    ios_esm_config = build_ios_esm_config(source)
    write_json(STUDY_CONFIG_PATH, android_config)
    write_json(IOS_CONFIG_PATH, ios_config)
    write_json(IOS_ESM_CONFIG_PATH, ios_esm_config)
    # The credential inside is the server's own, so it is kept as closely as the
    # deploy that generates it keeps it.
    write_json(ANDROID_MICRO_CONFIG_PATH, android_micro, SECRET_MODE)
