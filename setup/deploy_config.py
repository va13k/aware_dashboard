import html
import json
import pathlib
import secrets


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = pathlib.Path("/project")
ENV_PATH = PROJECT / ".env"
REQUEST_ENV_PATH = pathlib.Path("/tmp/aware-dashboard-request.env")
CONFIG_PATH = PROJECT / "aware-micro-server" / "aware-config.json"
EXAMPLE_PATH = PROJECT / "aware-micro-server" / "aware-config.example.json"
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


def ensure_django_secret_key(env: dict[str, str]) -> None:
    django_secret_key = str(env.get("DJANGO_SECRET_KEY", "")).strip()
    if not django_secret_key or django_secret_key == "CHANGE_ME":
        env["DJANGO_SECRET_KEY"] = secrets.token_urlsafe(50)


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


def load_micro_config() -> dict:
    source_path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH
    return json.loads(source_path.read_text(encoding="utf-8"))


def update_server_config(config: dict, settings: dict[str, str | int]) -> None:
    server = config.setdefault("server", {})
    server["database_engine"] = "mysql"
    server["database_host"] = settings["database_host"]
    server["database_name"] = "aware_ios"
    server["database_user"] = "aware_ios_participant"
    server["database_pwd"] = "participantpass"
    server["database_port"] = 3306
    server["server_host"] = "0.0.0.0"
    server["server_port"] = 8080
    server["websocket_port"] = 8081
    server["external_server_host"] = settings["external_server_host"]
    server["external_server_port"] = settings["public_port"]
    server["path_fullchain_pem"] = ""
    server["path_key_pem"] = ""


def ensure_study_defaults(config: dict) -> dict:
    study = config.setdefault("study", {})
    study["study_number"] = study.get("study_number", 1)
    study_key = str(study.get("study_key", "")).strip()
    if not study_key or study_key in {"your_study_key", "CHANGE_ME"}:
        study["study_key"] = secrets.token_hex(6)
    return study


def write_micro_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def build_study_join_urls(
    protocol: str, public_host: str, public_port: int, study: dict
) -> tuple[str, str]:
    is_default_port = (protocol == "http" and public_port == 80) or (
        protocol == "https" and public_port == 443
    )
    base_url = f"{protocol}://{public_host}"
    if not is_default_port:
        base_url += f":{public_port}"

    study_join_path = f"/{study['study_number']}/{study['study_key']}"
    study_join_url = f"{base_url}{study_join_path}"
    return study_join_path, study_join_url


def build_studies_index(study_join_path: str, study_join_url: str) -> str:
    template = STUDIES_TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{STUDY_JOIN_URL}}", html.escape(study_join_url))
        .replace("{{STUDY_JOIN_PATH}}", html.escape(study_join_path))
    )


def write_studies_index(study_join_path: str, study_join_url: str) -> None:
    STUDIES_INDEX_PATH.write_text(
        build_studies_index(study_join_path, study_join_url),
        encoding="utf-8",
    )


def main() -> None:
    env = load_merged_env()
    ensure_django_secret_key(env)
    persist_env(env)

    settings = get_runtime_settings(env)
    config = load_micro_config()
    update_server_config(config, settings)
    study = ensure_study_defaults(config)
    write_micro_config(config)

    study_join_path, study_join_url = build_study_join_urls(
        str(settings["protocol"]),
        str(settings["public_host"]),
        int(settings["public_port"]),
        study,
    )
    write_studies_index(study_join_path, study_join_url)


if __name__ == "__main__":
    main()
