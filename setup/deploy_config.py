import html
import json
import pathlib
import secrets
import sys


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = pathlib.Path("/project")
if not PROJECT.exists():
    PROJECT = SCRIPT_DIR.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from shared_config.serializers import serialize_android_config, serialize_ios_config
SOURCE_PATH = PROJECT / "source.json"
ENV_PATH = PROJECT / ".env"
REQUEST_ENV_PATH = pathlib.Path("/tmp/aware-dashboard-request.env")
CONFIG_PATH = PROJECT / "aware-micro-server" / "aware-config.json"
EXAMPLE_PATH = PROJECT / "aware-micro-server" / "aware-config.example.json"
ANDROID_TEMPLATE_PATH = PROJECT / "AWARE-Configurator" / "reactapp" / "public" / "study-config.json"
STUDY_CONFIG_PATH = PROJECT / "studies" / "studyConfig.json"
STUDIES_INDEX_PATH = PROJECT / "studies" / "index.html"
STUDIES_TEMPLATE_PATH = SCRIPT_DIR / "studies_index_template.html"


def load_env(path: pathlib.Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def load_merged_env() -> dict[str, str]:
    env = load_env(ENV_PATH)
    env.update(load_env(REQUEST_ENV_PATH))
    return env


def load_source_config() -> dict:
    return json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


def ensure_django_secret_key(env: dict[str, str]) -> None:
    django_secret_key = str(env.get("DJANGO_SECRET_KEY", "")).strip()
    if not django_secret_key or django_secret_key == "CHANGE_ME":
        env["DJANGO_SECRET_KEY"] = secrets.token_urlsafe(50)


def normalize_public_env(env: dict[str, str]) -> None:
    public_host = str(env.get("PUBLIC_HOST", "")).strip()
    protocol = str(env.get("PROTOCOL", "")).strip().lower()
    public_port = str(env.get("PUBLIC_PORT", "")).strip()
    cert_path = str(env.get("SSL_CERTIFICATE_PATH", "")).strip()
    cert_key_path = str(env.get("SSL_CERTIFICATE_KEY_PATH", "")).strip()

    if not public_host or public_host in {"example.test", "CHANGE_ME"}:
        public_host = "localhost"

    if protocol not in {"http", "https"}:
        protocol = "http"

    if protocol == "https" and (not cert_path or not cert_key_path):
        protocol = "http"
        public_port = "80"
        env.pop("SSL_CERTIFICATE_PATH", None)
        env.pop("SSL_CERTIFICATE_KEY_PATH", None)

    if not public_port:
        public_port = "443" if protocol == "https" else "80"

    if protocol == "http" and public_port == "443":
        public_port = "80"
    if protocol == "https" and public_port == "80":
        public_port = "443"

    env["PUBLIC_HOST"] = public_host
    env["PROTOCOL"] = protocol
    env["PUBLIC_PORT"] = public_port


def persist_env(env: dict[str, str]) -> None:
    ordered_keys = [
        "MYSQL_ROOT_PASSWORD",
        "DJANGO_SECRET_KEY",
        "PUBLIC_HOST",
        "PUBLIC_PORT",
        "PROTOCOL",
        "MICRO_DATABASE_HOST",
        "MICRO_EXTERNAL_HOST",
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


def get_runtime_settings(env: dict[str, str]) -> dict[str, str | int]:
    protocol = env.get("PROTOCOL", "http")
    public_host = env.get("PUBLIC_HOST", "localhost")
    public_port = int(env.get("PUBLIC_PORT", "443" if protocol == "https" else "80"))
    database_host = str(env.get("MICRO_DATABASE_HOST", public_host)).strip() or public_host
    external_server_host = str(
        env.get("MICRO_EXTERNAL_HOST", f"{protocol}://{public_host}")
    ).strip() or f"{protocol}://{public_host}"

    return {
        "protocol": protocol,
        "public_host": public_host,
        "public_port": public_port,
        "database_host": database_host,
        "external_server_host": external_server_host,
    }

def write_micro_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def write_android_config(config: dict) -> None:
    STUDY_CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def build_study_join_urls(
    protocol: str, public_host: str, public_port: int, study: dict
) -> tuple[str, str, str]:
    is_default_port = (protocol == "http" and public_port == 80) or (
        protocol == "https" and public_port == 443
    )
    base_url = f"{protocol}://{public_host}"
    if not is_default_port:
        base_url += f":{public_port}"

    study_join_path = f"/{study['study_number']}/{study['study_key']}"
    study_join_url = f"{base_url}{study_join_path}"
    return base_url, study_join_path, study_join_url


def render_android_study_link(base_url: str) -> str:
    if not STUDY_CONFIG_PATH.exists():
        return '<p class="note">The Android study config has not been generated yet.</p>'

    public_path = f"/studies/files/{STUDY_CONFIG_PATH.name}"
    public_url = f"{base_url}{public_path}"
    return (
        '<a class="study-link" href="{path}">'
        "<span>{name}</span>"
        "<code>{url}</code>"
        "</a>"
    ).format(
        path=html.escape(public_path),
        name="android-study",
        url=html.escape(public_url),
    )


def build_studies_index(
    base_url: str, study_join_path: str, study_join_url: str
) -> str:
    template = STUDIES_TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{STUDY_JOIN_URL}}", html.escape(study_join_url))
        .replace("{{STUDY_JOIN_PATH}}", html.escape(study_join_path))
        .replace("{{ANDROID_STUDY_LINK}}", render_android_study_link(base_url))
    )


def write_studies_index(base_url: str, study_join_path: str, study_join_url: str) -> None:
    STUDIES_INDEX_PATH.write_text(
        build_studies_index(base_url, study_join_path, study_join_url),
        encoding="utf-8",
    )


def main() -> None:
    env = load_merged_env()
    ensure_django_secret_key(env)
    normalize_public_env(env)
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

    config, study = serialize_ios_config(source, settings, EXAMPLE_PATH, CONFIG_PATH)
    write_micro_config(config)

    base_url, study_join_path, study_join_url = build_study_join_urls(
        str(settings["protocol"]),
        str(settings["public_host"]),
        int(settings["public_port"]),
        study,
    )
    write_studies_index(base_url, study_join_path, study_join_url)


if __name__ == "__main__":
    main()
