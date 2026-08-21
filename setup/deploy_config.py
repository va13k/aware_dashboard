import html
import json
import os
import pathlib
import secrets
import subprocess
import sys
import uuid

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = pathlib.Path("/project")
RUNNING_IN_WIZARD = False
if not PROJECT.exists():
    PROJECT = SCRIPT_DIR.parent
else:
    RUNNING_IN_WIZARD = True
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from shared_config import dataflow
from shared_config.source_store import update_source
from shared_config.runtime import (
    SECRET_MODE,
    SHARED_MODE,
    atomic_write_text,
    build_public_base_url,
    get_runtime_settings,
    load_env,
    normalize_public_env,
)
from shared_config.serializers import (
    IOS_ESM_CONFIG_FILENAME,
    build_ios_esm_config,
    serialize_android_config,
    serialize_ios_config,
)
HTPASSWD_PATH = PROJECT / "nginx" / "auth" / ".htpasswd"
SOURCE_PATH = PROJECT / "source.json"
ENV_PATH = PROJECT / ".env"
REQUEST_ENV_PATH = pathlib.Path("/tmp/aware-dashboard-request.env")
CONFIG_PATH = PROJECT / "aware-micro-server" / "aware-config.json"
EXAMPLE_PATH = PROJECT / "aware-micro-server" / "aware-config.example.json"
ESM_CONFIG_PATH = PROJECT / "aware-micro-server" / "esm" / IOS_ESM_CONFIG_FILENAME
ANDROID_TEMPLATE_PATH = PROJECT / "AWARE-Configurator" / "reactapp" / "public" / "study-config.json"
STUDY_CONFIG_PATH = PROJECT / "studies" / "studyConfig.json"
STUDIES_INDEX_PATH = PROJECT / "studies" / "index.html"
STUDIES_TEMPLATE_PATH = SCRIPT_DIR / "studies_index_template.html"

def load_merged_env() -> dict[str, str]:
    env = load_env(ENV_PATH)
    if RUNNING_IN_WIZARD:
        env.update(load_env(REQUEST_ENV_PATH))
    return env


PLACEHOLDER_SECRETS = {"", "CHANGE_ME"}


def ensure_participant_password(env: dict[str, str]) -> None:
    """Settle on the password devices use, preferring the researcher's own.

    The setup wizard writes the researcher's choice into the request env, which
    load_merged_env() layers over .env, so a typed password wins over a
    previously generated one. Only a deployment that has never been given a
    password gets a random one.
    """
    password = str(env.get("PARTICIPANT_DB_PASSWORD", "")).strip()
    env["PARTICIPANT_DB_PASSWORD"] = (
        secrets.token_urlsafe(16) if password in PLACEHOLDER_SECRETS else password
    )


def seed_source_secrets(env: dict[str, str]) -> dict:
    """Align source.json with this deployment's credentials.

    update_source() creates source.json from source.example.json on first run.
    The participant password is then taken from .env unconditionally, because
    .env is what MySQL's first-boot script applies to the accounts: copying any
    other value here would serve devices a password the accounts do not have.
    That is safe to overwrite because the Configurator writes every password
    change back to .env, so .env already holds the researcher's own value.
    """
    participant_password = env["PARTICIPANT_DB_PASSWORD"]

    def mutate(source: dict) -> dict:
        for platform in ("android", "ios"):
            database = source.get("database", {}).get(platform)
            if database is None:
                continue
            database["password"] = participant_password

        study = source.setdefault("study", {})
        if str(study.get("id", "")).strip() in PLACEHOLDER_SECRETS | {
            "00000000-0000-0000-0000-000000000000"
        }:
            study["id"] = env["STUDY_ID"]

        return source

    return update_source(mutate)


def ensure_django_secret_key(env: dict[str, str]) -> None:
    django_secret_key = str(env.get("DJANGO_SECRET_KEY", "")).strip()
    if not django_secret_key or django_secret_key == "CHANGE_ME":
        env["DJANGO_SECRET_KEY"] = secrets.token_urlsafe(50)


def ensure_session_secret(env: dict[str, str]) -> None:
    """The key the dashboard signs session cookies with.

    Generated once and kept in .env, so restarting the API does not invalidate
    every researcher's cookie (see analytics_api/app/routers/auth.py).
    """
    session_secret = str(env.get("DASHBOARD_SESSION_SECRET", "")).strip()
    if not session_secret or session_secret in PLACEHOLDER_SECRETS:
        env["DASHBOARD_SESSION_SECRET"] = secrets.token_urlsafe(50)


def ensure_study_key(env: dict[str, str]) -> None:
    study_key = str(env.get("STUDY_KEY", "")).strip()
    if not study_key or study_key in {"CHANGE_ME", "your_study_key"}:
        env["STUDY_KEY"] = secrets.token_urlsafe(9)


def ensure_study_id(env: dict[str, str]) -> None:
    study_id = str(env.get("STUDY_ID", "")).strip()
    if not study_id or study_id in {"CHANGE_ME", "aware-default-study"}:
        env["STUDY_ID"] = str(uuid.uuid4())


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
    atomic_write_text(HTPASSWD_PATH, f"{username}:{hashed}\n", SECRET_MODE)


def persist_env(env: dict[str, str]) -> None:
    ordered_keys = [
        "MYSQL_ROOT_PASSWORD",
        "DJANGO_SECRET_KEY",
        "DASHBOARD_SESSION_SECRET",
        "STUDY_KEY",
        "STUDY_ID",
        "RESEARCHER_USERNAME",
        "RESEARCHER_PASSWORD",
        "PARTICIPANT_DB_PASSWORD",
        "PUBLIC_HOST",
        "PUBLIC_PORT",
        "PROTOCOL",
        "MYSQL_BACKUP_HOST_DIR",
        "MYSQL_BACKUP_INTERVAL_SECONDS",
        "MYSQL_BACKUP_RETENTION_DAYS",
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

    atomic_write_text(ENV_PATH, "\n".join(env_lines) + "\n", SECRET_MODE)

def write_micro_config(config: dict) -> None:
    # Bind-mounted into the micro-server, which runs as appuser.
    atomic_write_text(CONFIG_PATH, json.dumps(config, indent=2) + "\n", SHARED_MODE)


def write_ios_esm_config(config: list[dict]) -> None:
    # Served to iOS devices by nginx at /esm/.
    atomic_write_text(ESM_CONFIG_PATH, json.dumps(config, indent=2) + "\n", SHARED_MODE)


def write_android_config(config: dict) -> None:
    # Served to Android devices by nginx at /studies/files/.
    atomic_write_text(STUDY_CONFIG_PATH, json.dumps(config, indent=2) + "\n", SHARED_MODE)


def build_study_join_urls(
    protocol: str, public_host: str, public_port: int, study: dict
) -> tuple[str, str, str]:
    base_url = build_public_base_url(protocol, public_host, public_port)
    study_join_path = f"/{study['study_number']}/{study['study_key']}"
    study_join_url = f"{base_url}{study_join_path}"
    return base_url, study_join_path, study_join_url


def build_deployment_urls(base_url: str, study_join_url: str, android_join_url: str) -> dict[str, str]:
    return {
        "app_url": base_url,
        "dashboard_url": f"{base_url}/dashboard/",
        "configurator_url": f"{base_url}/configurator/",
        "studies_url": f"{base_url}/studies/",
        "android_join_url": android_join_url,
        "ios_join_url": study_join_url,
    }


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
    base_url: str, study_join_path: str, study_join_url: str, android_join_url: str = ""
) -> str:
    template = STUDIES_TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{STUDY_JOIN_URL}}", html.escape(study_join_url))
        .replace("{{STUDY_JOIN_PATH}}", html.escape(study_join_path))
        .replace("{{ANDROID_STUDY_LINK}}", render_android_study_link())
        .replace("{{ANDROID_JOIN_URL}}", html.escape(android_join_url))
    )


def write_studies_index(
    base_url: str, study_join_path: str, study_join_url: str, android_join_url: str = ""
) -> None:
    atomic_write_text(
        STUDIES_INDEX_PATH,
        build_studies_index(base_url, study_join_path, study_join_url, android_join_url),
        SHARED_MODE,
    )


def write_deployment_urls(urls: dict[str, str]) -> None:
    # Read back by setup.sh/setup.bat as the host user, which may differ from
    # the wizard container's UID that writes it.
    atomic_write_text(
        PROJECT / "deployment-urls.json",
        json.dumps(urls, indent=2) + "\n",
        SHARED_MODE,
    )


def chown_generated_paths(env: dict[str, str]) -> None:
    """Align on-disk ownership with the deploying user.

    The setup wizard runs this script as root inside its container (it also
    reads /var/run/docker.sock to poll service health, which needs root or
    the docker group, so it can't drop to HOST_UID:HOST_GID the way the
    Configurator does). Left alone, every file below would stay root-owned,
    and the Configurator — which does run as HOST_UID:HOST_GID — would get a
    PermissionError, surfaced to the researcher as a 500, the moment they hit
    Save. Re-running this as a normal, non-root user (setup.sh's redeploy
    path) is a harmless no-op: chowning a path to its own uid/gid always
    succeeds without extra privilege.

    Windows has no Unix uid/gid concept — os.chown doesn't exist there — and
    setup.bat never writes HOST_UID/HOST_GID to .env, since Docker Desktop's
    bind mounts don't enforce host-side ownership the way a native Linux bind
    mount does. Bail out before touching os.getuid/os.chown, both of which
    would raise AttributeError on that platform.

    Every path this touches holds a secret or credentials (.env, the
    htpasswd, source.json's database passwords), so the target uid:gid is
    not trusted blindly: it must match the project directory's own owner,
    which was established out-of-band at `git clone` time and is not
    reachable from any web request (write_request_env.py's fixed key
    allowlist already excludes HOST_UID/HOST_GID, so the wizard's HTTP body
    cannot inject one either — this is defense in depth for a future code
    path or a hand-edited .env, not a plugged hole).
    """
    if not hasattr(os, "chown"):
        return

    try:
        uid = int(env.get("HOST_UID", os.getuid()))
        gid = int(env.get("HOST_GID", os.getgid()))
    except (TypeError, ValueError):
        return

    try:
        anchor = PROJECT.stat()
    except OSError as exc:
        print(f"deploy_config: could not stat {PROJECT}: {exc}", file=sys.stderr)
        return

    if (uid, gid) != (anchor.st_uid, anchor.st_gid):
        print(
            f"deploy_config: refusing to chown generated files to {uid}:{gid} — "
            f"it does not match the project directory's owner "
            f"{anchor.st_uid}:{anchor.st_gid}. Check HOST_UID/HOST_GID in .env.",
            file=sys.stderr,
        )
        return

    paths = [
        ENV_PATH,
        HTPASSWD_PATH,
        HTPASSWD_PATH.parent,
        SOURCE_PATH,
        CONFIG_PATH,
        CONFIG_PATH.parent,
        CONFIG_PATH.parent / "cache",
        ESM_CONFIG_PATH,
        ESM_CONFIG_PATH.parent,
        STUDY_CONFIG_PATH,
        STUDY_CONFIG_PATH.parent,
        STUDIES_INDEX_PATH,
        PROJECT / "deployment-urls.json",
    ]
    for path in paths:
        try:
            if path.exists():
                os.chown(path, uid, gid)
        except OSError as exc:
            print(f"deploy_config: could not chown {path}: {exc}", file=sys.stderr)


def main() -> None:
    env = load_merged_env()
    ensure_django_secret_key(env)
    ensure_session_secret(env)
    ensure_study_key(env)
    ensure_study_id(env)
    ensure_researcher_credentials(env)
    ensure_participant_password(env)
    env = normalize_public_env(env)

    generate_htpasswd(
        env["RESEARCHER_USERNAME"],
        env["RESEARCHER_PASSWORD"],
    )

    persist_env(env)

    # Creates source.json from source.example.json when absent, then fills in
    # this deployment's generated credentials before anything is serialized.
    source = seed_source_secrets(env)
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

    base_url = build_public_base_url(
        str(settings["protocol"]),
        str(settings["public_host"]),
        int(settings["public_port"]),
    )
    # The same resolver the Configurator uses, so the two cannot write different
    # answers into one setting again. The identifiers come from the env and the
    # source rather than from the iOS config's study block, which is not built
    # until below.
    android_study_url = dataflow.webservice_server(
        dataflow.declared(source, "android"),
        study_url=(
            f"{base_url}/{source.get('ios', {}).get('study_number', 1)}"
            f"/{env['STUDY_KEY']}"
        ),
        config_url=f"{base_url}/studies/files/{STUDY_CONFIG_PATH.name}",
    )
    android_config = serialize_android_config(source, settings, ANDROID_TEMPLATE_PATH, env["STUDY_ID"], android_study_url)
    write_android_config(android_config)

    config, study = serialize_ios_config(source, settings, EXAMPLE_PATH, CONFIG_PATH, env["STUDY_KEY"])
    write_micro_config(config)
    write_ios_esm_config(build_ios_esm_config(source))
    study_join_path = f"/{study['study_number']}/{study['study_key']}"
    study_join_url = f"{base_url}{study_join_path}"
    write_studies_index(base_url, study_join_path, study_join_url, android_study_url)
    write_deployment_urls(build_deployment_urls(base_url, study_join_url, android_study_url))

    chown_generated_paths(env)


if __name__ == "__main__":
    main()
