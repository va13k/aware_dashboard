import html
import json
import pathlib
import secrets
import subprocess
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = pathlib.Path("/project")
RUNNING_IN_WIZARD = False
if not PROJECT.exists():
    PROJECT = SCRIPT_DIR.parent
else:
    RUNNING_IN_WIZARD = True
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from shared_config.source_store import read_source
from shared_config.runtime import (
    build_public_base_url,
    get_runtime_settings,
    load_env,
    normalize_public_env,
)
from shared_config.serializers import serialize_android_config, serialize_ios_config
HTPASSWD_PATH = PROJECT / "nginx" / "auth" / ".htpasswd"
SOURCE_PATH = PROJECT / "source.json"
ENV_PATH = PROJECT / ".env"
REQUEST_ENV_PATH = pathlib.Path("/tmp/aware-dashboard-request.env")
CONFIG_PATH = PROJECT / "aware-micro-server" / "aware-config.json"
EXAMPLE_PATH = PROJECT / "aware-micro-server" / "aware-config.example.json"
ESM_CONFIG_PATH = PROJECT / "aware-micro-server" / "esm" / "ios-esm-config.json"
ANDROID_TEMPLATE_PATH = PROJECT / "AWARE-Configurator" / "reactapp" / "public" / "study-config.json"
STUDY_CONFIG_PATH = PROJECT / "studies" / "studyConfig.json"
STUDIES_INDEX_PATH = PROJECT / "studies" / "index.html"
STUDIES_TEMPLATE_PATH = SCRIPT_DIR / "studies_index_template.html"

def load_merged_env() -> dict[str, str]:
    env = load_env(ENV_PATH)
    if RUNNING_IN_WIZARD:
        env.update(load_env(REQUEST_ENV_PATH))
    return env


def load_source_config() -> dict:
    return read_source()


def ensure_django_secret_key(env: dict[str, str]) -> None:
    django_secret_key = str(env.get("DJANGO_SECRET_KEY", "")).strip()
    if not django_secret_key or django_secret_key == "CHANGE_ME":
        env["DJANGO_SECRET_KEY"] = secrets.token_urlsafe(50)


def ensure_analytics_api_key(env: dict[str, str]) -> None:
    api_key = str(env.get("ANALYTICS_API_KEY", "")).strip()
    if not api_key or api_key == "CHANGE_ME":
        env["ANALYTICS_API_KEY"] = secrets.token_hex(32)


def ensure_researcher_credentials(env: dict[str, str]) -> None:
    if not env.get("RESEARCHER_USERNAME", "").strip():
        env["RESEARCHER_USERNAME"] = "researcher"
    if not env.get("RESEARCHER_PASSWORD", "").strip():
        env["RESEARCHER_PASSWORD"] = secrets.token_urlsafe(16)


def generate_htpasswd(username: str, password: str) -> None:
    result = subprocess.run(
        ["openssl", "passwd", "-apr1", password],
        capture_output=True,
        text=True,
        check=True,
    )
    hashed = result.stdout.strip()
    HTPASSWD_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTPASSWD_PATH.write_text(f"{username}:{hashed}\n", encoding="utf-8")


def persist_env(env: dict[str, str]) -> None:
    ordered_keys = [
        "MYSQL_ROOT_PASSWORD",
        "DJANGO_SECRET_KEY",
        "ANALYTICS_API_KEY",
        "RESEARCHER_USERNAME",
        "RESEARCHER_PASSWORD",
        "PUBLIC_HOST",
        "PUBLIC_PORT",
        "PROTOCOL",
        "MICRO_DATABASE_HOST",
        "SSL_CERTIFICATE_PATH",
        "SSL_CERTIFICATE_KEY_PATH",
    ]

    env_lines = []
    for key in ordered_keys:
        value = env.get(key)
        if value:
            env_lines.append(f"{key}={value}")

    for key, value in env.items():
        if key not in ordered_keys and value:
            env_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

def write_micro_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def write_ios_esm_config(schedules: list) -> None:
    ESM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ESM_CONFIG_PATH.write_text(json.dumps(schedules, indent=2) + "\n", encoding="utf-8")


def write_android_config(config: dict) -> None:
    STUDY_CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def build_study_join_urls(
    protocol: str, public_host: str, public_port: int, study: dict
) -> tuple[str, str, str]:
    base_url = build_public_base_url(protocol, public_host, public_port)
    study_join_path = f"/{study['study_number']}/{study['study_key']}"
    study_join_url = f"{base_url}{study_join_path}"
    return base_url, study_join_path, study_join_url


def render_android_study_link() -> str:
    if not STUDY_CONFIG_PATH.exists():
        return '<p class="note">The Android study config has not been generated yet.</p>'

    public_path = f"/studies/files/{STUDY_CONFIG_PATH.name}"
    return (
        '<a class="study-link dynamic-link" data-path="{path}" href="{path}">'
        "<span>{name}</span>"
        "<code>{path}</code>"
        "</a>"
    ).format(
        path=html.escape(public_path),
        name="android-study",
    )


def build_studies_index(
    base_url: str, study_join_path: str, study_join_url: str
) -> str:
    template = STUDIES_TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{STUDY_JOIN_URL}}", html.escape(study_join_url))
        .replace("{{STUDY_JOIN_PATH}}", html.escape(study_join_path))
        .replace("{{ANDROID_STUDY_LINK}}", render_android_study_link())
    )


def write_studies_index(base_url: str, study_join_path: str, study_join_url: str) -> None:
    STUDIES_INDEX_PATH.write_text(
        build_studies_index(base_url, study_join_path, study_join_url),
        encoding="utf-8",
    )


def main() -> None:
    env = load_merged_env()
    ensure_django_secret_key(env)
    ensure_analytics_api_key(env)
    ensure_researcher_credentials(env)
    env = normalize_public_env(env)

    generate_htpasswd(
        env["RESEARCHER_USERNAME"],
        env["RESEARCHER_PASSWORD"],
    )

    persist_env(env)

    source = load_source_config()
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

    android_config = serialize_android_config(source, settings, ANDROID_TEMPLATE_PATH)
    write_android_config(android_config)

    config, study, esm_schedules = serialize_ios_config(source, settings, EXAMPLE_PATH, CONFIG_PATH)
    write_micro_config(config)
    write_ios_esm_config(esm_schedules)

    base_url, study_join_path, study_join_url = build_study_join_urls(
        str(settings["protocol"]),
        str(settings["public_host"]),
        int(settings["public_port"]),
        study,
    )
    write_studies_index(base_url, study_join_path, study_join_url)


if __name__ == "__main__":
    main()
