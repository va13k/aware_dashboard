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

from shared_config import database, dataflow, messaging, placement
from shared_config.certificates import read_certificate, valid_certificate
from shared_config.source_store import update_source
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
    IOS_ESM_CONFIG_FILENAME,
    build_android_micro_config,
    build_ios_esm_config,
    serialize_android_config,
    serialize_ios_config,
)
HTPASSWD_PATH = PROJECT / "nginx" / "auth" / ".htpasswd"
SOURCE_PATH = PROJECT / "source.json"
ENV_PATH = PROJECT / ".env"
REQUEST_ENV_PATH = pathlib.Path("/tmp/aware-dashboard-request.env")
CONFIG_PATH = PROJECT / "aware-micro-server" / "aware-config.json"
#: The Android instance's own configuration. One micro-server holds one study and
#: one database, and the two platforms share neither, so there is one of each.
ANDROID_CONFIG_PATH = PROJECT / "aware-micro-server" / "aware-config.android.json"
EXAMPLE_PATH = PROJECT / "aware-micro-server" / "aware-config.example.json"
ESM_CONFIG_PATH = PROJECT / "aware-micro-server" / "esm" / IOS_ESM_CONFIG_FILENAME
ANDROID_TEMPLATE_PATH = PROJECT / "AWARE-Configurator" / "reactapp" / "public" / "study-config.json"
STUDY_CONFIG_PATH = PROJECT / "studies" / "studyConfig.json"
#: Merged over the compose file when the study names a database of its own. Written
#: rather than checked in, because it exists only for the placement that needs it.
COMPOSE_OVERRIDE_PATH = PROJECT / "docker-compose.external-db.yml"
#: The broker's own files. Generated rather than checked in, because who may
#: publish and who may only receive is derived from the study, and its passwords
#: are this deployment's.
MOSQUITTO_DIR = PROJECT / "mosquitto"
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


def ensure_server_password(env: dict[str, str]) -> None:
    """Settle on the password the Android micro-server authenticates with.

    Its own secret, not the participants'. The participant password is published to
    every phone in the study on the direct dataflow, and the server's account may read
    the enrolment registry and keep the device-metadata row that a phone's account may
    not, so one password for both would hand every participant the wider account too.

    Nothing asks a researcher for this one: the server is the only holder, and the
    Configurator edits it on the dataflow where it is the credential in use. Kept
    rather than regenerated whenever one is already on record, so a change made there
    survives the next deploy.
    """
    password = str(env.get("ANDROID_SERVER_DB_PASSWORD", "")).strip()
    env["ANDROID_SERVER_DB_PASSWORD"] = (
        secrets.token_urlsafe(16) if password in PLACEHOLDER_SECRETS else password
    )


def requested_dataflow() -> str:
    """The dataflow the researcher chose in this wizard run, or "" for none.

    Read from the request env rather than the merged one. `.env` keeps the last
    value written, so a deploy nobody answered the question in — `setup.sh`
    offering "deploy with current config", or a rerun of this script — reads as
    no answer and leaves the study's own declaration standing.
    """
    if not RUNNING_IN_WIZARD:
        return ""
    return str(load_env(REQUEST_ENV_PATH).get("ANDROID_DATAFLOW", "")).strip().lower()


def requested_placement() -> dict[str, str]:
    """The database the researcher named in this wizard run, or {} for none.

    Read from the request env for the same reason the dataflow is: `.env` keeps the
    last value written, so a deploy nobody answered the question in leaves the
    study's own declaration standing rather than reapplying an old answer.
    """
    if not RUNNING_IN_WIZARD:
        return {}
    request = load_env(REQUEST_ENV_PATH)
    chosen = str(request.get("DB_PLACEMENT", "")).strip().lower()
    if chosen not in placement.CHOICES:
        return {}
    if chosen == placement.BUNDLED:
        return {"host": placement.DEFAULT_HOST}
    return {
        "host": str(request.get("DB_HOST", "")).strip(),
        "port": str(request.get("DB_PORT", "")).strip(),
    }


def apply_placement(source: dict) -> str:
    """Everything the chosen placement decides, settled in one place.

    Two things follow from it. Whether this deployment runs a database at all, which
    is a compose override rather than a setting: a service that must not start
    cannot simply be left unstarted while six others wait on its health check, so the
    override removes the service and the waits together. And whether the combination
    is honourable at all --- an external database with phones connecting directly
    would need that host open to every participant's network, which is the one
    combination refused.

    Refuses rather than half-applies, so a study is never left declaring a database
    this deployment would not actually use.
    """
    problems = placement.validate(source)
    if problems:
        raise SystemExit("This database placement cannot be applied. " + " ".join(problems))

    chosen = placement.declared(source)
    if placement.runs_bundled_mysql(chosen):
        COMPOSE_OVERRIDE_PATH.unlink(missing_ok=True)
    else:
        # Asked before anything is generated, because the alternative is a study
        # deployed against an address that answers to nobody: every config would name
        # it, every service would wait on it, and the first sign would be a coverage
        # grid that stays empty. The bundled database is checked after it is up
        # instead, since it does not exist to be asked yet.
        require_reachable_database(source)
        atomic_write_text(COMPOSE_OVERRIDE_PATH, build_compose_override(), SHARED_MODE)
    set_env_value(ENV_PATH, "DB_PLACEMENT", chosen)
    return chosen


def require_reachable_database(source: dict) -> None:
    """Refuse a study whose database cannot take its data.

    Reachability is not the question on its own --- a host that answers and refuses
    every insert collects exactly as much as one that does not answer --- so this
    runs the whole check and reports each part of it. Where a step failed for want of
    a privilege the check has already printed the SQL that settles it, so the message
    here points at that rather than repeating it.
    """
    checker = SCRIPT_DIR / "verify_database.py"
    result = subprocess.run(
        [sys.executable, str(checker), "--placement", placement.EXTERNAL],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return
    raise SystemExit(
        "The database this study names cannot take its data. No configuration a "
        "phone or a service reads has been generated, and the deployment still runs "
        "whatever it ran before.\n" + (result.stdout or result.stderr).strip()
    )


#: The services that wait on the bundled database's health check. A service kept out
#: of a deployment is still depended on, and compose starts a dependency whether or
#: not anyone asked for it, so the waits are cleared alongside the service itself.
WAITS_ON_BUNDLED_MYSQL = (
    "mysql-backup",
    "micro-server",
    "micro-server-android",
    "configurator",
    "dashboard-api",
    "counts-refresher",
)


def build_compose_override() -> str:
    """The compose file that takes the bundled database out of the deployment.

    `!reset` clears a value the base file sets rather than merging with it, which is
    what removing a service and its dependents' waits requires: an override can add
    to `depends_on` but cannot otherwise take anything out of it.
    """
    lines = [
        "# Generated by setup/deploy_config.py for a study that names its own database.",
        "# Merged over docker-compose.yml, and absent whenever the study runs the",
        "# bundled one. Edit the placement in setup rather than this file.",
        "services:",
        "  mysql: !reset null",
    ]
    for service in WAITS_ON_BUNDLED_MYSQL:
        lines.append(f"  {service}:")
        lines.append("    depends_on: !reset null")
    return "\n".join(lines) + "\n"


def seed_source_secrets(env: dict[str, str]) -> dict:
    """Align source.json with this deployment's credentials.

    update_source() creates source.json from source.example.json on first run.
    Each password is then taken from .env unconditionally, because .env is what
    MySQL's first-boot script applies to the accounts: copying any other value here
    would name a password the accounts do not have. That is safe to overwrite because
    the Configurator writes every password change back to .env, so .env already holds
    the researcher's own value.

    Android carries two accounts, one per dataflow, so it carries two passwords:
    the participant one phones open the database with, and the micro-server's own,
    which every webservice write authenticates as. Both are seeded whichever dataflow
    the study runs -- the instance is configured either way, and a study switching
    paths then finds the account on its new path already holding the password the
    generated configuration names.
    """
    participant_password = env["PARTICIPANT_DB_PASSWORD"]
    server_password = env["ANDROID_SERVER_DB_PASSWORD"]
    server_account = database.android_ingest_account(dataflow.WEBSERVICE)

    def mutate(source: dict) -> dict:
        for platform in ("android", "ios"):
            entry = source.get("database", {}).get(platform)
            if entry is None:
                continue
            entry["password"] = participant_password

        android = source.get("database", {}).get("android")
        if android is not None:
            android[server_account["password_key"]] = server_password
            # Named here so every reader of the study model finds the account, on a
            # study written before it carried one as much as on a new one.
            android.setdefault(
                server_account["name_key"], server_account["default_name"]
            )

        study = source.setdefault("study", {})
        if str(study.get("id", "")).strip() in PLACEHOLDER_SECRETS | {
            "00000000-0000-0000-0000-000000000000"
        }:
            study["id"] = env["STUDY_ID"]

        # The dataflow the study runs on, held here and derived from here, so every
        # generated file downstream comes from one answer -- a study half-configured
        # for two dataflows is a study that looks set up and collects nothing.
        #
        # An answer given in this wizard run wins, because it is the researcher
        # deciding. Otherwise the declaration already in the study model stands, and
        # `.env` seeds it only on a study that has never carried one -- the same rule
        # the study id above follows. That is what lets the Configurator change the
        # dataflow and have the change survive the next deploy.
        declared = source.setdefault("deployment", {}).setdefault("dataflow", {})
        chosen = requested_dataflow()
        if chosen:
            declared["android"] = chosen
        elif not str(declared.get("android", "")).strip():
            seeded = env.get("ANDROID_DATAFLOW", "").strip().lower()
            if seeded:
                declared["android"] = seeded
        declared.setdefault("ios", dataflow.WEBSERVICE)

        # Where the database runs, held as the host it runs on rather than as a
        # placement of its own: `database.host` is what every reader already
        # resolves, and a second field would be a second answer that could disagree
        # with it. An answer given in this run wins; otherwise the study's own
        # declaration stands, so the placement survives a deploy nobody was asked in.
        named = requested_placement()
        if named.get("host"):
            db = source.setdefault("database", {})
            db["host"] = named["host"]
            if named.get("port"):
                for platform in ("android", "ios"):
                    entry = db.get(platform)
                    if entry is not None:
                        entry["port"] = int(named["port"])
        source.setdefault("database", {}).setdefault("host", placement.DEFAULT_HOST)

        # The one path that reaches a phone, filled in rather than built: every one of
        # these keys has been in the study model all along and blank, and the client
        # subscribes on connect once they carry a server. The address is the public
        # host for the same reason the database's is on the direct path -- a
        # participant's phone resolves it from wherever the participant is.
        android_settings = source.setdefault("android", {}).setdefault("settings", {})
        android_settings.update(
            messaging.study_settings(
                # A study with no public host has no address to hand a phone, and a
                # block naming a broker that is not there is worse than one that is
                # off: the client would retry a connection it can never make. Absent
                # either half, the sensor stays off and says so.
                server=str(env.get("PUBLIC_HOST", "")).strip(),
                protocol=env.get("PROTOCOL", "http"),
                username=messaging.PARTICIPANT_USER,
                password=str(env.get("MQTT_PARTICIPANT_PASSWORD", "")).strip(),
            )
        )

        return source

    return update_source(mutate)



def resolve_database_readers(env: dict[str, str], source: dict) -> dict[str, str]:
    """Point every service inside the deployment at the declared database.

    The study model declares the database once. The phones' configs already derive
    from it; this is the other side of the boundary --- the API, its refresher and
    the backup job, which reached it by an address written down separately in the
    compose file and so could not follow a change.

    The analytics password is the deployment's own, not the study's, so it comes
    from the environment rather than the model. Its default matches the account the
    bootstrap SQL creates, which is what keeps an existing deployment working
    without being re-provisioned.
    """
    analytics_password = env.get("ANALYTICS_DB_PASSWORD", "analyticspass")
    resolved = database.resolved_env(source.get("database") or {}, analytics_password)
    for key, value in resolved.items():
        set_env_value(ENV_PATH, key, value)
    return resolved


def apply_dataflow(env: dict[str, str], source: dict) -> str:
    """Everything the chosen dataflow decides, settled in one place.

    The published config is handled by the serializers, which read the same
    declaration. What is left is the deployment's own half: whether MySQL is
    reachable from outside this machine at all. A phone on the direct path has to
    open it itself; on the webservice path only the micro-server does, and it
    reaches MySQL over the compose network, so the published port has no audience
    beyond this host.

    Refuses rather than half-applies: a dataflow this platform cannot honour is a
    configuration that would leave phones collecting and delivering nowhere.
    """
    problems = dataflow.validate(source)
    if problems:
        raise SystemExit(
            "This dataflow cannot be applied. " + " ".join(problems)
        )

    android = dataflow.declared(source, "android")
    # Read from the combination rather than from the dataflow alone. The dataflow
    # names who opens the database; where it runs names whether that crosses a
    # network, and the same webservice study is a hop inside one machine on a
    # bundled database and a hop across the internet on a named one.
    #
    # Loopback rather than removing the mapping: the mapping is what the compose
    # file declares, and narrowing the address is the part that decides who can
    # reach it. A study running no database of its own has nothing to bind, and the
    # value is written anyway so the compose file always has an answer -- the
    # service it belongs to is removed by the override in that case.
    where = placement.declared(source)
    bind = placement.connection(where, android)["bundled_bind"] or "127.0.0.1"
    set_env_value(ENV_PATH, "MYSQL_BIND_ADDRESS", bind)
    # Written back so `.env` mirrors the declaration rather than competing with it.
    # The setup wizard reads `.env` to fill its form, and a mirror is what lets it
    # open on the dataflow the study is running rather than on a default.
    set_env_value(ENV_PATH, "ANDROID_DATAFLOW", android)
    return bind


def ensure_broker_passwords(env: dict[str, str]) -> None:
    """A credential for each of the broker's two accounts, kept once generated.

    The participant one is served to every phone in the study config, so changing it
    silently would cut off every phone already carrying the old one until each picks
    up a new config. Both are therefore generated on the first deploy that needs them
    and left alone afterwards.
    """
    for key in ("MQTT_PARTICIPANT_PASSWORD", "MQTT_PUBLISHER_PASSWORD"):
        if not str(env.get(key, "")).strip():
            env[key] = secrets.token_urlsafe(18)


def apply_broker(env: dict[str, str], docker_prefix: list[str] | None = None) -> int:
    """The broker's configuration, its accounts and who may do what with them.

    Written whichever protocol the deployment serves, because the API publishes over
    the compose network either way and only the participants' port depends on it. The
    password file is built with the broker's own hashing tool, since mosquitto reads
    hashes rather than the passwords themselves.
    """
    protocol = str(env.get("PROTOCOL", "http")).strip().lower()
    port = messaging.port_for(protocol)

    MOSQUITTO_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        MOSQUITTO_DIR / "mosquitto.conf", messaging.broker_config(protocol), SHARED_MODE
    )
    atomic_write_text(MOSQUITTO_DIR / "acl", messaging.acl(), SHARED_MODE)
    write_broker_passwords(env, docker_prefix or [])

    set_env_value(ENV_PATH, "MQTT_PUBLIC_PORT", str(port))
    # Bound where participants are: the broker is what a phone reaches, so unlike the
    # database it is published whichever dataflow the study runs.
    set_env_value(ENV_PATH, "MQTT_BIND_ADDRESS", "0.0.0.0")
    set_env_value(ENV_PATH, "MQTT_PUBLISHER_USER", messaging.PUBLISHER_USER)
    set_env_value(ENV_PATH, "MQTT_PARTICIPANT_USER", messaging.PARTICIPANT_USER)
    for key in ("MQTT_PARTICIPANT_PASSWORD", "MQTT_PUBLISHER_PASSWORD"):
        set_env_value(ENV_PATH, key, env[key])
    return port


def write_broker_passwords(env: dict[str, str], docker_prefix: list[str]) -> None:
    """The broker's password file, hashed the way the broker hashes.

    Built by running the broker's own image, so the hash is whatever that version of
    mosquitto produces rather than a format reimplemented here. A deployment that
    cannot run it keeps the file it has, which is what lets a redeploy on a machine
    without the image pulled leave a working broker working.
    """
    target = MOSQUITTO_DIR / "passwords"
    accounts = (
        (messaging.PARTICIPANT_USER, env["MQTT_PARTICIPANT_PASSWORD"]),
        (messaging.PUBLISHER_USER, env["MQTT_PUBLISHER_PASSWORD"]),
    )
    # Each mosquitto_passwd run announces itself, and the file is read from this
    # command's own output, so only the cat is allowed to reach it.
    script = " && ".join(
        ["touch /tmp/passwords"]
        + [
            f"mosquitto_passwd -b /tmp/passwords {user} '{password}' >/dev/null 2>&1"
            for user, password in accounts
        ]
        + ["cat /tmp/passwords"]
    )
    result = subprocess.run(
        (docker_prefix or []) + ["docker", "run", "--rm", "--entrypoint", "sh",
                                 "eclipse-mosquitto:2", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        atomic_write_text(target, result.stdout, SHARED_MODE)
        return
    if target.exists():
        print("broker: keeping the password file already in place")
        return
    raise SystemExit(
        "The broker's password file could not be built: "
        + (result.stderr.strip() or "mosquitto_passwd did not run")
    )


#: Where a bundled MySQL keeps the authority it signed its own certificate with.
#: Generated by the server on its first start, and readable, so a study running its
#: own database needs nobody to supply one.
BUNDLED_CA_PATH = "/var/lib/mysql/ca.pem"


def ensure_database_authority(source: dict, docker_prefix: list[str] | None = None) -> str:
    """Publish the authority a phone can verify the study database against.

    A database this deployment runs signs its own certificate, and the authority it
    used is on disk in the container --- so on that placement nobody has to supply
    anything, and a phone opening the database gets a connection it can check rather
    than one it can only encrypt. A database the researcher names has an authority
    only they can provide, and its absence leaves the connection encrypted and
    unverified, which is stated where the choice is made.

    An answer already in the study model wins: a researcher who pasted an authority
    meant it, and it may well be the right one for a certificate that was replaced.

    What is read from the container is deliberately not written back to the study
    model. It is re-read on every deploy instead, so a database that regenerates its
    certificate --- a fresh volume, a restored backup --- publishes the authority it
    is actually using rather than one this study remembered from before.
    """
    databases = source.get("database") or {}
    android = databases.get("android")
    if android is None:
        return "supplied"

    existing = str(android.get("ca_certificate") or "").strip()
    if existing:
        if not valid_certificate(existing):
            raise SystemExit(
                "The database certificate authority in this study is not a "
                "certificate this deployment can read. Publishing it would stop every "
                "phone uploading, because the client treats an unreadable authority "
                "as a database it cannot reach. Correct it, or clear it to run "
                "encrypted without verifying the server."
            )
        return "supplied"

    if placement.declared(source) != placement.BUNDLED:
        return "none"

    read = subprocess.run(
        (docker_prefix or []) + ["docker", "exec", "aware_mysql", "cat", BUNDLED_CA_PATH],
        capture_output=True,
        text=True,
        check=False,
    )
    pem = read_certificate(read.stdout)
    if read.returncode != 0 or not pem:
        # A first deploy has no database running yet, and there is nothing to read.
        # The connection is encrypted either way; only the verification waits for the
        # next deploy, once the server has generated what it signs with.
        return "none"

    android["ca_certificate"] = pem
    return "generated"


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
        "ANDROID_SERVER_DB_PASSWORD",
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


def check_placement_applied(source: dict) -> None:
    """The compose override read back against the placement that decided it.

    The override is what takes the bundled database out of a deployment, so a study
    declaring an external database while the file is absent brings up a database
    nobody reads and waits on its health check. Reading it back turns that into a
    failure at deploy time rather than a container that is running for nobody.
    """
    chosen = placement.declared(source)
    present = COMPOSE_OVERRIDE_PATH.exists()
    if placement.runs_bundled_mysql(chosen) == present:
        raise SystemExit(
            f"The deployment does not match the declared database placement "
            f"({chosen!r}). {COMPOSE_OVERRIDE_PATH.name} is "
            + ("present" if present else "absent")
            + ", and that placement requires it to be "
            + ("absent." if present else "present.")
        )


def check_dataflow_applied(source: dict, bind: str, android_study_url: str) -> None:
    """Every artefact the dataflow decides, checked against the declaration.

    The declaration is one line; what follows from it is a bind address, a join
    URL and whether the published config carries database coordinates. Each is
    written by a different function, and a study half-configured for two
    dataflows still starts, serves and looks deployed -- the phones simply
    deliver nowhere. Reading them back is what turns that into a failure at
    deploy time.

    Raises SystemExit naming every disagreement, so one run reports all of them.
    """
    android = dataflow.declared(source, "android")
    expected_bind = "0.0.0.0" if android == dataflow.DIRECT else "127.0.0.1"
    carries = dataflow.carries_database_credentials("android", android)

    published = {}
    if STUDY_CONFIG_PATH.exists():
        try:
            published = json.loads(STUDY_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            published = {}

    problems = []
    if bind != expected_bind:
        problems.append(
            f"MySQL is bound to {bind}, but {android!r} implies {expected_bind}."
        )
    if ("database" in published) != carries:
        held = "carries" if "database" in published else "omits"
        wanted = "carry" if carries else "omit"
        problems.append(
            f"The published Android config {held} database coordinates, "
            f"but {android!r} requires it to {wanted} them."
        )
    for name, url in (
        ("deployment-urls.json", _stored_join_url()),
        ("the generated config", android_study_url),
    ):
        if url and url != android_study_url:
            problems.append(f"The join URL in {name} is {url}, not {android_study_url}.")

    if problems:
        raise SystemExit(
            f"The deployment does not match the declared Android dataflow "
            f"({android!r}). " + " ".join(problems)
        )


def _stored_join_url() -> str:
    """The Android join URL the last deploy published, or "" when there is none."""
    path = PROJECT / "deployment-urls.json"
    if not path.exists():
        return ""
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("android_join_url", ""))
    except (OSError, json.JSONDecodeError):
        return ""


def main() -> None:
    env = load_merged_env()
    ensure_django_secret_key(env)
    ensure_session_secret(env)
    ensure_study_key(env)
    ensure_study_id(env)
    ensure_researcher_credentials(env)
    ensure_participant_password(env)
    ensure_server_password(env)
    ensure_broker_passwords(env)
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
    # The same resolver the Configurator uses, so the two write one answer into
    # one setting.
    # Applied before anything is generated: a refusal here means no half-written
    # study, and the bind address is settled alongside the config that depends on it.
    bind = apply_dataflow(env, source)
    # After the dataflow, because the combination is what is refused: an external
    # database is offered with HTTP/S ingest and not with phones connecting directly.
    where = apply_placement(source)
    authority = ensure_database_authority(source)
    broker_port = apply_broker(env)
    resolve_database_readers(env, source)
    print(f"dataflow: android={dataflow.declared(source, 'android')} "
          f"ios={dataflow.declared(source, 'ios')} mysql_bind={bind}")
    print(f"database: {where} at {database.declared_host(source.get('database') or {})} "
          f"(tls verified by: {authority})")
    print(f"broker: {messaging.PARTICIPANT_USER} on port {broker_port} "
          f"({'TLS' if messaging.uses_tls(env.get('PROTOCOL', 'http')) else 'plaintext'})")

    android_study_url = dataflow.android_study_url(
        dataflow.declared(source, "android"),
        base_url,
        env["STUDY_KEY"],
        STUDY_CONFIG_PATH.name,
    )
    android_config = serialize_android_config(source, settings, ANDROID_TEMPLATE_PATH, env["STUDY_ID"], android_study_url)
    write_android_config(android_config)

    # The Android micro-server's own configuration. Written whichever dataflow is
    # chosen: an instance that is running and unused costs nothing, and generating
    # it only on the webservice path would mean a switch needed a re-deploy rather
    # than a restart.
    android_micro = build_android_micro_config(
        source,
        settings,
        env["STUDY_KEY"],
        dataflow.ANDROID_STUDY_NUMBER,
        join_url=android_study_url,
    )
    atomic_write_text(
        ANDROID_CONFIG_PATH, json.dumps(android_micro, indent=2) + "\n", SECRET_MODE
    )

    config, study = serialize_ios_config(source, settings, EXAMPLE_PATH, CONFIG_PATH, env["STUDY_KEY"])
    write_micro_config(config)
    write_ios_esm_config(build_ios_esm_config(source))
    study_join_path = f"/{study['study_number']}/{study['study_key']}"
    study_join_url = f"{base_url}{study_join_path}"
    write_studies_index(base_url, study_join_path, study_join_url, android_study_url)
    write_deployment_urls(build_deployment_urls(base_url, study_join_url, android_study_url))

    # Read back after everything is written: the check is worth only as much as
    # the files it inspects, and those are the files a phone will be served.
    check_dataflow_applied(source, bind, android_study_url)
    check_placement_applied(source)

    chown_generated_paths(env)


if __name__ == "__main__":
    main()
