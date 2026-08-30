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
from shared_config.certificates import (
    decode_certificate,
    read_certificate,
    valid_certificate,
)
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
#: The one-time copy from the database this deployment used to run into the one the
#: study now names. Written only where the study asked for it, so a move that leaves
#: the rows behind leaves nothing to run either.
COPY_SCRIPT_PATH = PROJECT / "copy-study-data.sh"
#: The broker's own files. Generated rather than checked in, because who may
#: publish and who may only receive is derived from the study, and its passwords
#: are this deployment's.
MOSQUITTO_DIR = PROJECT / "mosquitto"
STUDIES_INDEX_PATH = PROJECT / "studies" / "index.html"
STUDIES_TEMPLATE_PATH = SCRIPT_DIR / "studies_index_template.html"
#: The study key as nginx reads it. Generated rather than checked in, because it is
#: this deployment's credential and the two protocol configurations beside it are
#: the same file for every study.
NGINX_STUDY_KEY_PATH = PROJECT / "nginx" / "study-key.conf"

def load_merged_env() -> dict[str, str]:
    env = load_env(ENV_PATH)
    if RUNNING_IN_WIZARD:
        env.update(load_env(REQUEST_ENV_PATH))
    return env


PLACEHOLDER_SECRETS = {"", "CHANGE_ME"}

#: The variable a deploy is asked through to mint a credential again.
ROTATE_ENV = "ROTATE"

#: What can be asked for, and the values each one replaces.
#:
#: Both are credentials every participant's phone holds a copy of, which is why a
#: new one is asked for rather than produced by a redeploy: the study key is the
#: address a phone uploads to, and the broker password is what every phone in the
#: study connects with. A phone carrying the old one is a phone that has stopped
#: reporting until it reads its configuration again.
ROTATABLE = {
    "study-key": ("STUDY_KEY",),
    "broker": ("MQTT_PARTICIPANT_PASSWORD", "MQTT_PUBLISHER_PASSWORD"),
}


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


def ensure_bundled_root_password(env: dict[str, str]) -> None:
    """Settle the password the bundled database's own `root` is created with.

    Generated here and then left alone. MySQL bakes it into the data directory the
    first time the container starts and ignores the variable ever after, so a value
    that changes is a value that stops matching the server --- which is what happened
    while this key also carried the administrator of whichever database the study
    named: pointing a study at a managed server overwrote it, and moving back
    authenticated to the bundled server with somebody else's password.

    Nobody types this one. The account a researcher names lives in
    database.ADMIN_PASSWORD_ENV, and on the bundled placement
    setup/init_study_tables.py creates it with the privileges to administer the study.
    """
    password = str(env.get("MYSQL_ROOT_PASSWORD", "")).strip()
    if not password or password in PLACEHOLDER_SECRETS:
        env["MYSQL_ROOT_PASSWORD"] = secrets.token_urlsafe(16)


def ensure_analytics_password(env: dict[str, str]) -> None:
    """Settle on the password the dashboard reads the study with.

    The deployment's own account rather than the study's, so nothing asks a
    researcher for it and it is generated here like every other secret. The seed the
    bootstrap SQL creates the account with counts as no password at all: it is the
    same word in every deployment of this software, and the account holds SELECT over
    both schemas --- on a database the researcher named, that is every row of every
    participant's data, readable by anyone who can reach the server.

    Applied to the account by setup/init_study_tables.py, which reads the same value.
    """
    password = str(env.get(database.ANALYTICS_PASSWORD_ENV, "")).strip()
    if password in PLACEHOLDER_SECRETS | {database.ANALYTICS_SEED_PASSWORD}:
        password = secrets.token_urlsafe(16)
    env[database.ANALYTICS_PASSWORD_ENV] = password


def ensure_backup_password(env: dict[str, str]) -> None:
    """Settle on the password the dashboard dumps and restores the study with.

    The deployment's own account rather than the administrator's, so nothing asks a
    researcher for it and it is generated here like every other secret. A restore
    feeds an archive into a database client and everything the archive contains
    runs; as the administrator that is the whole server, and an archive that arrived
    through an upload form is not something this deployment wrote.

    Applied to the account by setup/init_study_tables.py, which reads the same value
    on every deploy --- which is what reaches a database whose data directory already
    exists, where db/*.sql never runs again.
    """
    password = str(env.get(database.BACKUP_PASSWORD_ENV, "")).strip()
    if password in PLACEHOLDER_SECRETS:
        password = secrets.token_urlsafe(16)
    env[database.BACKUP_PASSWORD_ENV] = password


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


def requested_placement() -> dict[str, object]:
    """The database the researcher named in this wizard run, or {} for none.

    Read from the request env for the same reason the dataflow is: `.env` keeps the
    last value written, so a deploy nobody answered the question in leaves the
    study's own declaration standing rather than reapplying an old answer.

    What the connection to it has to be carries the same way, and only for a database
    the researcher named: on the bundled placement encryption is settled and the
    authority is read out of the container, so there is no answer to carry.
    """
    if not RUNNING_IN_WIZARD:
        return {}
    request = load_env(REQUEST_ENV_PATH)
    chosen = str(request.get("DB_PLACEMENT", "")).strip().lower()
    if chosen not in placement.CHOICES:
        return {}
    if chosen == placement.BUNDLED:
        return {"host": placement.DEFAULT_HOST}
    named = {
        "host": str(request.get("DB_HOST", "")).strip(),
        "port": str(request.get("DB_PORT", "")).strip(),
    }
    declared = str(request.get("DB_REQUIRE_TLS", "")).strip()
    if declared:
        named["require_tls"] = declared not in {"0", "false", "no", "off"}
    # Carried encoded because a PEM is several lines and the request is a `.env` file,
    # whose every line is one setting. Absent rather than empty when none was pasted,
    # so a run nobody typed a certificate in leaves the one this study already
    # publishes standing --- clearing an authority is done where the current one can
    # be seen, which is the Configurator and not this form.
    pasted = read_certificate(decode_certificate(request.get("DB_CA_CERTIFICATE_B64", "")))
    if pasted:
        named["ca_certificate"] = pasted
    return named


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
        atomic_write_text(
            COMPOSE_OVERRIDE_PATH,
            build_compose_override(backup_connection(source) if keeps_backups() else None),
            SHARED_MODE,
        )
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
    # The account that creates the schema is the study's answer, not root by
    # assumption: a managed database calls its administrator something of its own,
    # and authenticating as a name that does not exist reads exactly like a wrong
    # password.
    # Named by this wizard run where there is one, then by what a deployment already
    # on record settled, then by what the host says about its provider. The request
    # lives in /tmp and a deploy re-run after a reboot has none, which would
    # otherwise send every managed database a login as root.
    request = load_env(REQUEST_ENV_PATH)
    admin_user = database.admin_user(
        str((source.get("database") or {}).get("host") or ""),
        str(request.get("DB_ADMIN_USER", "")).strip()
        or str(load_env(ENV_PATH).get("DB_ADMIN_USER", "")).strip(),
    )
    # Where the study said its schema is created by hand, the deployment checks and
    # creates nothing: the account it was given may only write.
    verify_only = str(request.get("DB_INIT", "")).strip().lower() == "manual"
    result = subprocess.run(
        [
            sys.executable,
            str(checker),
            "--placement",
            placement.EXTERNAL,
            "--admin-user",
            admin_user,
        ]
        + (["--verify-only"] if verify_only else []),
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


#: The service a deployment has only because it runs the database itself. Nothing
#: replaces it when the study names its own: the address in `.env` is what every
#: other service opens.
BUNDLED_DATABASE_SERVICE = "mysql"

#: The scheduled dump. It goes wherever the database goes only if the study asked
#: for it: the job was written for the database this deployment runs, and a server
#: somebody else administers usually keeps its own snapshots. Left behind, it is
#: removed rather than kept failing against a host it cannot reach.
BACKUP_SERVICE = "mysql-backup"

#: The services that wait on the bundled database's health check. A service kept out
#: of a deployment is still depended on, and compose starts a dependency whether or
#: not anyone asked for it, so the waits are cleared alongside the service itself.
WAITS_ON_BUNDLED_MYSQL = (
    "micro-server",
    "micro-server-android",
    "configurator",
    "dashboard-api",
    "counts-refresher",
)


def build_compose_override(backup: dict[str, str] | None = None) -> str:
    """The compose file that takes the bundled database out of the deployment.

    `!reset` clears a value the base file sets rather than merging with it, which is
    what removing a service and its dependents' waits requires: an override can add
    to `depends_on` but cannot otherwise take anything out of it.

    `backup` is the connection the dump job is kept on when the study asked to go on
    taking copies of the server it named, and None when it did not --- then the job
    is removed like the database it was written for. The password is left as a
    reference for compose to resolve from `.env`, so a generated file carries none.
    """
    lines = [
        "# Generated by setup/deploy_config.py for a study that names its own database.",
        "# Merged over docker-compose.yml, and absent whenever the study runs the",
        "# bundled one. Edit the placement in setup rather than this file.",
        "services:",
        f"  {BUNDLED_DATABASE_SERVICE}: !reset null",
    ]
    waiting = list(WAITS_ON_BUNDLED_MYSQL)
    if backup is None:
        lines.append(f"  {BACKUP_SERVICE}: !reset null")
    else:
        waiting.append(BACKUP_SERVICE)
    for service in waiting:
        lines.append(f"  {service}:")
        lines.append("    depends_on: !reset null")
        if service == BACKUP_SERVICE:
            lines.append("    environment:")
            for key, value in backup.items():
                lines.append(f"      {key}: {value}")
    return "\n".join(lines) + "\n"


def keeps_backups(env: dict[str, str] | None = None) -> bool:
    """Whether the deployment goes on dumping a database it does not run.

    Off unless the study said otherwise, because carrying the job across is a
    decision about somebody else's server rather than a detail of the move. Read from
    this wizard run first and from the deployment on record after it, so a redeploy
    that never opens the wizard keeps the answer already given.
    """
    answer = str(load_env(REQUEST_ENV_PATH).get("DB_KEEP_BACKUPS", "")).strip()
    if not answer:
        source = env if env is not None else load_env(ENV_PATH)
        answer = str(source.get("DB_KEEP_BACKUPS", "")).strip()
    return answer == "1"


def backup_connection(source: dict) -> dict[str, str]:
    """How the dump job opens a database this deployment does not run.

    As `aware_analytics` rather than as the administrator: the job runs for the whole
    study, and reading every row is all a dump needs. `--no-tablespaces` in the job
    itself is what lets an account without PROCESS take one, and the schemas hold no
    routines, triggers or views for the rest of the dump to need more.
    """
    databases = source.get("database") or {}
    return {
        "MYSQL_PORT": str(database.platform_port(databases, "android")),
        "MYSQL_USER": database.ANALYTICS_USER,
        "MYSQL_PASSWORD": "${ANALYTICS_DB_PASSWORD}",
        "MYSQL_SSL_MODE": "REQUIRED" if database.tls_required(databases) else "PREFERRED",
    }


#: The copy script is run by the researcher rather than read by a service.
EXECUTABLE_MODE = 0o755

#: The container the bundled database keeps running in after a study has moved off
#: it. Compose is not asked to remove orphans, so it is still there to be dumped.
BUNDLED_CONTAINER = "aware_mysql"

#: Tables the copy leaves behind. Both are the dashboard's own arithmetic over the
#: rows that arrive, and the API rebuilds them on the server it lands on; carrying
#: them would describe the deployment that counted rather than the study. The
#: decisions --- enrolment, refusals, exclusions --- do travel, because a copy into
#: an empty server has no second deployment's answers to reconcile with.
COPY_SKIP_TABLES = ("record_counts", "coverage_hourly")


def carries_collected_rows() -> bool:
    """Whether this run was asked to carry the rows already collected across.

    Off unless the study said otherwise. A move switches which database the study
    writes to; what was written before stays where it was written, and copying
    gigabytes into a server somebody else pays for is a decision rather than a step.
    """
    return str(load_env(REQUEST_ENV_PATH).get("DB_CARRY_DATA", "")).strip() == "1"


def build_copy_script(source: dict) -> str:
    """The commands that carry the collected rows into the database the study names.

    Written out rather than run here: the deploy answers a browser that is waiting on
    it, and 4 GB of sensor data is not something to move behind a request with no
    progress and no second attempt. As a file it can be read before it is trusted,
    watched while it runs, and run again --- every insert is an INSERT IGNORE, so a
    connection that drops halfway costs the time and nothing else.

    No password is written into it. The bundled server's own is read from the
    container that still holds it, and the named server's from `.env`, which by then
    describes the database this study writes to.
    """
    databases = source.get("database") or {}
    host = database.declared_host(databases)
    port = database.platform_port(databases, "android")
    admin_user = database.admin_user(host, str(load_env(ENV_PATH).get("DB_ADMIN_USER", "")).strip())
    ssl_mode = "REQUIRED" if database.tls_required(databases) else "PREFERRED"
    android_schema = database.platform_schema(databases, "android")
    schemas = " ".join(
        database.platform_schema(databases, platform) for platform in ("android", "ios")
    )
    skipped = " ".join(COPY_SKIP_TABLES)
    admin_password_env = database.ADMIN_PASSWORD_ENV
    return f"""#!/bin/sh
# Generated by setup/deploy_config.py for a study that moved to a database it names.
#
# Carries the rows collected before the move from the database this deployment used
# to run into {host}. Run it from the project folder, once, after
# the deploy that switched the study over:
#
#   sudo ./copy-study-data.sh
#
# It reads both passwords where they already live --- the old server's from the
# container still holding it, this study's from .env --- so nothing here is a
# credential. Set DOCKER=docker if your user may talk to the daemon without sudo.
set -eu

DOCKER="${{DOCKER:-sudo docker}}"
SOURCE_CONTAINER='{BUNDLED_CONTAINER}'
TARGET_HOST='{host}'
TARGET_PORT='{port}'
TARGET_USER='{admin_user}'
TARGET_SSL_MODE='{ssl_mode}'
SCHEMAS='{schemas}'
SKIP_TABLES='{skipped}'

cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "No .env here. Run this from the project folder." >&2
    exit 1
fi

TARGET_PASSWORD="$(sed -n 's/^{admin_password_env}=//p' .env | head -n 1)"
if [ -z "$TARGET_PASSWORD" ]; then
    echo "{admin_password_env} is not in .env, so there is no account to write with." >&2
    exit 1
fi

if [ "$($DOCKER inspect -f '{{{{.State.Running}}}}' "$SOURCE_CONTAINER" 2>/dev/null)" != "true" ]; then
    echo "$SOURCE_CONTAINER is not running, so the rows it holds cannot be read." >&2
    echo "Start it with: $DOCKER start $SOURCE_CONTAINER" >&2
    exit 1
fi

# Refused rather than merged. Every insert here is an INSERT IGNORE keyed on the
# `_id` the old server assigned, so rows a phone has already written to the new one
# would collide by number and be dropped without a word. A server that has begun
# collecting is merged through the dashboard's backup page, which reconciles by
# watermark instead.
echo "Checking that the new database is still empty..."
COLLECTED="$($DOCKER exec -i \\
    -e MYSQL_PWD="$TARGET_PASSWORD" "$SOURCE_CONTAINER" \\
    mysql --host="$TARGET_HOST" --port="$TARGET_PORT" --user="$TARGET_USER" \\
    --ssl-mode="$TARGET_SSL_MODE" -B -N \\
    -e 'SELECT COUNT(*) FROM aware_device' {android_schema} 2>/dev/null || echo 0)"
if [ "${{COLLECTED:-0}}" != "0" ]; then
    echo "The database this study now writes to already holds $COLLECTED devices." >&2
    echo "Import through the dashboard's backup page instead: it folds rows in above" >&2
    echo "the watermark, where this copy would drop them as duplicate ids." >&2
    exit 1
fi

IGNORE=""
for schema in $SCHEMAS; do
    for table in $SKIP_TABLES; do
        IGNORE="$IGNORE --ignore-table=$schema.$table"
    done
done

echo "Copying $SCHEMAS to $TARGET_HOST. This runs as long as the data is large."

# Intentional word splitting: SCHEMAS is a space-separated list and IGNORE one
# option per table left behind.
#
# --no-create-info because the deploy has already created every table on the far
# side, --insert-ignore so a second run adds only what the first did not, and
# --set-gtid-purged=OFF because a managed server has GTIDs on and reading their
# position needs a privilege a study's account has no reason to hold.
$DOCKER exec -i \\
    -e TARGET_PASSWORD="$TARGET_PASSWORD" \\
    -e TARGET_HOST="$TARGET_HOST" \\
    -e TARGET_PORT="$TARGET_PORT" \\
    -e TARGET_USER="$TARGET_USER" \\
    -e TARGET_SSL_MODE="$TARGET_SSL_MODE" \\
    -e SCHEMAS="$SCHEMAS" \\
    -e IGNORE="$IGNORE" \\
    "$SOURCE_CONTAINER" sh -c '
set -eu
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump \\
    --single-transaction --no-tablespaces --set-gtid-purged=OFF \\
    --no-create-info --insert-ignore --complete-insert \\
    $IGNORE --databases $SCHEMAS \\
| MYSQL_PWD="$TARGET_PASSWORD" mysql \\
    --host="$TARGET_HOST" --port="$TARGET_PORT" --user="$TARGET_USER" \\
    --ssl-mode="$TARGET_SSL_MODE"
'

BEFORE="$($DOCKER exec -i "$SOURCE_CONTAINER" sh -c \\
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -B -N -e "SELECT COUNT(*) FROM aware_device" {android_schema}')"
AFTER="$($DOCKER exec -i -e MYSQL_PWD="$TARGET_PASSWORD" "$SOURCE_CONTAINER" \\
    mysql --host="$TARGET_HOST" --port="$TARGET_PORT" --user="$TARGET_USER" \\
    --ssl-mode="$TARGET_SSL_MODE" -B -N \\
    -e 'SELECT COUNT(*) FROM aware_device' {android_schema})"

echo
echo "Devices on the old server: $BEFORE"
echo "Devices on {host}: $AFTER"
echo
echo "The dashboard's counts are its own arithmetic over these rows, and the first"
echo "refresh after this rebuilds them."
"""


def apply_data_copy(source: dict) -> bool:
    """Write, or take away, the script that carries the collected rows across.

    Present only where a study asked for the copy, so the file's existence is the
    answer --- the same way the compose override's existence is the placement.
    """
    if placement.runs_bundled_mysql(placement.declared(source)) or not carries_collected_rows():
        COPY_SCRIPT_PATH.unlink(missing_ok=True)
        return False
    atomic_write_text(COPY_SCRIPT_PATH, build_copy_script(source), EXECUTABLE_MODE)
    return True


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
            # Beside the host, because it describes the same server and only the
            # researcher naming one has an answer to give. A run that named the
            # bundled database clears nothing: switching back settles encryption by
            # placement, and the authority pasted for the old server is re-read from
            # the container it now runs in.
            if "require_tls" in named or "ca_certificate" in named:
                database.declare_tls(
                    db, named.get("require_tls"), named.get("ca_certificate")
                )
        source.setdefault("database", {}).setdefault("host", placement.DEFAULT_HOST)

        # The one path that reaches a phone, filled in rather than built: every one of
        # these keys has been in the study model all along and blank, and the client
        # subscribes on connect once they carry a server. The address is the public
        # host for the same reason the database's is on the direct path -- a
        # participant's phone resolves it from wherever the participant is.
        android_settings = source.setdefault("android", {}).setdefault("settings", {})
        android_settings.update(
            messaging.apply_deployment_settings(
                android_settings,
                messaging.study_settings(
                    # A study with no public host has no address to hand a phone, and
                    # a block naming a broker that is not there is worse than one that
                    # is off: the client would retry a connection it can never make.
                    # Absent either half, the sensor stays off and says so.
                    server=str(env.get("PUBLIC_HOST", "")).strip(),
                    protocol=env.get("PROTOCOL", "http"),
                    username=messaging.PARTICIPANT_USER,
                    password=str(env.get("MQTT_PARTICIPANT_PASSWORD", "")).strip(),
                ),
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
    resolved = database.resolved_env(
        source.get("database") or {}, database.analytics_password(env)
    )
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


def clear_database_authority(model: dict) -> dict:
    """Take the certificate authority out of the study model."""
    database.declare_tls(model.setdefault("database", {}), ca_certificate="")
    return model


def ensure_database_authority(source: dict, docker_prefix: list[str] | None = None) -> str:
    """Publish the authority a phone can verify the study database against.

    A database this deployment runs signs its own certificate, and the authority it
    used is on disk in the container --- so on that placement nobody has to supply
    anything, and a phone opening the database gets a connection it can check rather
    than one it can only encrypt. A database the researcher names has an authority
    only they can provide, and its absence leaves the connection encrypted and
    unverified, which is stated where the choice is made.

    An answer already in the study model wins for the placement it was given for: a
    researcher who pasted an authority meant it, and it may well be the right one for
    a certificate that was replaced. It does not survive a move onto the bundled
    database, whose certificate it did not sign.

    What is read from the container is deliberately not written back to the study
    model. It is re-read on every deploy instead, so a database that regenerates its
    certificate --- a fresh volume, a restored backup --- publishes the authority it
    is actually using rather than one this study remembered from before.

    A study that declared an unencrypted connection has nothing to verify, and
    publishing an authority for a connection no client will check is a promise the
    interfaces would then have to un-make.
    """
    databases = source.get("database") or {}
    android = databases.get("android")
    if android is None:
        return "supplied"

    if not database.tls_required(databases):
        return "unencrypted"

    bundled = placement.declared(source) == placement.BUNDLED
    existing = database.tls_authority(databases)
    if existing and not bundled:
        if not valid_certificate(existing):
            raise SystemExit(
                "The database certificate authority in this study is not a "
                "certificate this deployment can read. Publishing it would stop every "
                "phone uploading, because the client treats an unreadable authority "
                "as a database it cannot reach. Correct it, or clear it to run "
                "encrypted without verifying the server."
            )
        return "supplied"

    if not bundled:
        return "none"

    # An authority belongs to the server that presented the certificate it signed,
    # not to the study, so one supplied for a database this study has moved off is
    # cleared rather than carried. Kept, it is published to every phone and checked
    # against a certificate it never signed, which reads as a database they cannot
    # reach --- and the deployment's own check refuses before that reaches anyone.
    #
    # Written through to the study model, unlike the authority read below: every
    # other reader opens source.json rather than this run's copy, and one left
    # holding the old server's certificate reports a database it cannot verify long
    # after the deploy that moved off it.
    if existing:
        update_source(clear_database_authority)
        database.declare_tls(databases, ca_certificate="")

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

    database.declare_tls(databases, ca_certificate=pem)
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


def apply_rotation_request(env: dict[str, str]) -> list[str]:
    """Empty the credentials this deploy was asked to mint again.

    Emptied rather than replaced here, so each value still has exactly one
    generator: every ``ensure_`` below reads a blank as a deployment that has none
    yet, which is the path a first deploy already takes.

    The request itself is cleared, so a rotation happens on the deploy that asked
    for it. Left in place it would mint a new key on every subsequent run, and a
    study whose address moves each time it is redeployed collects nothing.

    A name nothing recognises stops the run. Ignored, it would report a rotation
    that did not happen, and the value it was meant to replace is the one somebody
    has already been told is gone.
    """
    asked = str(env.get(ROTATE_ENV, "")).replace(",", " ").split()
    names = [name.strip().lower() for name in asked]
    unknown = sorted({name for name in names if name not in ROTATABLE})
    if unknown:
        raise SystemExit(
            f"{ROTATE_ENV}: this deployment does not mint {', '.join(unknown)}. "
            f"Choose from {', '.join(sorted(ROTATABLE))}."
        )

    env[ROTATE_ENV] = ""
    for name in names:
        for key in ROTATABLE[name]:
            env[key] = ""
    return sorted(set(names))


def report_rotation(rotated: list[str]) -> None:
    """What a rotation costs the study, said where the researcher is standing.

    Both credentials live on phones that are out in the field, so the deploy that
    replaces one leaves participants to act before their data resumes.
    """
    if not rotated:
        return
    print(f"minted again: {', '.join(rotated)}")
    if "study-key" in rotated:
        print("  every phone holds the old address: a participant rejoins by "
              "scanning the study's QR code again")
    if "broker" in rotated:
        print("  every phone holds the old broker password: prompts reach one "
              "again once it has read its configuration")


def generate_htpasswd(username: str, password: str) -> None:
    result = subprocess.run(
        ["openssl", "passwd", "-apr1", password],
        capture_output=True,
        text=True,
        check=True,
    )
    hashed = result.stdout.strip()
    atomic_write_text(HTPASSWD_PATH, f"{username}:{hashed}\n", SECRET_MODE)


#: Answers that belong to one wizard run rather than to the deployment. The request
#: env is merged over `.env` so a run's answers reach the code that applies them, and
#: this is what keeps the ones that were only ever in transit --- a certificate the
#: study model now holds --- from being written back as deployment settings.
#: `DB_CARRY_DATA` is one of them: copying what was already collected is something a
#: researcher does once, and a deployment that remembered it would offer to do it
#: again on every redeploy.
REQUEST_ONLY_KEYS = frozenset({"DB_CA_CERTIFICATE_B64", "DB_CARRY_DATA"})


def declared_database_host() -> str:
    """The host the study model names, for settling what the request left out."""
    try:
        return database.declared_host((read_source().get("database") or {}))
    except Exception:
        return ""


def persist_env(env: dict[str, str]) -> None:
    # Written whether or not the request carried it: a deployment upgraded in place
    # has an .env from before the question existed, and every script that opens the
    # database reads this file rather than asking again.
    env = dict(env)
    if not str(env.get("DB_ADMIN_USER", "")).strip():
        env["DB_ADMIN_USER"] = database.admin_user(
            str(env.get("DB_HOST", "")).strip() or declared_database_host(), ""
        )

    ordered_keys = [
        "DB_ADMIN_USER",
        database.ADMIN_PASSWORD_ENV,
        "MYSQL_ROOT_PASSWORD",
        "DJANGO_SECRET_KEY",
        "DASHBOARD_SESSION_SECRET",
        "STUDY_KEY",
        "STUDY_ID",
        "RESEARCHER_USERNAME",
        "RESEARCHER_PASSWORD",
        "PARTICIPANT_DB_PASSWORD",
        "ANDROID_SERVER_DB_PASSWORD",
        "ANALYTICS_DB_PASSWORD",
        database.BACKUP_PASSWORD_ENV,
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
        if key not in ordered_keys and key not in REQUEST_ONLY_KEYS and value:
            env_lines.append(f"{key}={value}")

    atomic_write_text(ENV_PATH, "\n".join(env_lines) + "\n", SECRET_MODE)

def write_micro_config(config: dict) -> None:
    # Bind-mounted into the micro-server, which runs as appuser.
    atomic_write_text(CONFIG_PATH, json.dumps(config, indent=2) + "\n", SHARED_MODE)


def write_android_micro_config(config: dict) -> None:
    # Bind-mounted into micro-server-android, which runs as appuser. The mode is
    # fixed here rather than left to the caller: a raw atomic_write_text at the
    # call site had it passing SECRET_MODE (0600, deploying user only), which left
    # appuser unable to read its own configuration and the container unhealthy —
    # this file is exactly as sensitive as CONFIG_PATH above, so it gets the same
    # helper shape.
    atomic_write_text(ANDROID_CONFIG_PATH, json.dumps(config, indent=2) + "\n", SHARED_MODE)


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


def write_nginx_study_key(study_key: str) -> None:
    """The key nginx compares a request against before serving a study config.

    A phone's configuration carries the broker credential it connects with, and on
    the direct dataflow the database account it opens as well, so the paths that
    serve it ask for the key first. Written as a map in its own file so the key
    reaches nginx without being written into a configuration that is checked in.

    Absent, nginx refuses to start on the unknown variable, which is what a
    deployment wants from a missing credential.
    """
    atomic_write_text(
        NGINX_STUDY_KEY_PATH,
        "# Generated from the study by setup/deploy_config.py. Edit the study, not this file.\n"
        "#\n"
        "# The key a phone presents to read its configuration, compared in\n"
        "# nginx/http.conf and nginx/https.conf before either serves the file.\n"
        f'map $host $study_key {{\n    default "{study_key}";\n}}\n',
        SHARED_MODE,
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
        ANDROID_CONFIG_PATH,
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


#: Files a container reads under a uid that never matches the host user's — nginx's
#: worker user for the two served over an alias, appuser inside each micro-server
#: for its own config. `chown_generated_paths` still runs first (it fixes ownership
#: for the host tools that touch the same paths, e.g. the Configurator), but a
#: container-readable file must work even when that chown is skipped (Windows,
#: `os.chown` missing) or when ownership and mode disagree, so what is checked here
#: is the "other" bit specifically rather than who owns the file.
CONTAINER_READABLE_PATHS = (CONFIG_PATH, ANDROID_CONFIG_PATH, ESM_CONFIG_PATH, STUDY_CONFIG_PATH)


def check_config_permissions() -> None:
    """Catch a config a container cannot read at deploy time, not weeks later.

    `aware-config.android.json` once reached production as SECRET_MODE (0600):
    every write into this file its own micro-server bind-mounts still went out
    with the right mode, so it never showed up in review, and it only surfaced
    as a 502 on the Android QR code once the container tried to boot from it.
    Checked after chown_generated_paths, and by the "other" bit rather than the
    owner, so the failure mode is a loud SystemExit here rather than a container
    stuck unhealthy in the field.
    """
    unreadable = [
        path for path in CONTAINER_READABLE_PATHS
        if path.exists() and not (path.stat().st_mode & 0o004)
    ]
    if unreadable:
        named = ", ".join(str(path) for path in unreadable)
        raise SystemExit(
            f"Not world-readable, so the container that bind-mounts it cannot "
            f"open it: {named}. Whatever wrote it must use SHARED_MODE, not "
            f"SECRET_MODE."
        )


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
    # Asked of the same function that decided it, because the dataflow does not decide
    # it alone. A study that names its own database runs no bundled one, so there is no
    # address of this deployment's for a phone to be pointed at and none to disagree
    # with --- and the value written for the compose file is a placeholder for a
    # service the override removes.
    expected_bind = placement.connection(placement.declared(source), android)["bundled_bind"]
    carries = dataflow.carries_database_credentials("android", android)

    published = {}
    if STUDY_CONFIG_PATH.exists():
        try:
            published = json.loads(STUDY_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            published = {}

    problems = []
    if expected_bind is not None and bind != expected_bind:
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
    rotated = apply_rotation_request(env)
    ensure_django_secret_key(env)
    ensure_session_secret(env)
    ensure_study_key(env)
    ensure_study_id(env)
    ensure_researcher_credentials(env)
    ensure_participant_password(env)
    ensure_server_password(env)
    ensure_bundled_root_password(env)
    ensure_analytics_password(env)
    ensure_backup_password(env)
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
    # After the placement, because it is the placement that decides there is anywhere
    # to copy from: a study staying on the bundled database has one server, not two.
    copying = apply_data_copy(source)
    authority = ensure_database_authority(source)
    broker_port = apply_broker(env)
    resolve_database_readers(env, source)
    print(f"dataflow: android={dataflow.declared(source, 'android')} "
          f"ios={dataflow.declared(source, 'ios')} mysql_bind={bind}")
    databases = source.get("database") or {}
    print(
        f"database: {where} at {database.declared_host(databases)} "
        + (
            f"(encrypted, verified by: {authority})"
            if database.tls_required(databases)
            else "(unencrypted, as this study declares)"
        )
    )
    if where != placement.BUNDLED:
        print(
            "backups: "
            + (
                f"kept, dumped as {database.ANALYTICS_USER}"
                if keeps_backups(env)
                else "left with the database this deployment used to run"
            )
        )
    if copying:
        print(f"rows already collected: run ./{COPY_SCRIPT_PATH.name} to carry them across")
    print(f"broker: {messaging.PARTICIPANT_USER} on port {broker_port} "
          f"({'TLS' if messaging.uses_tls(env.get('PROTOCOL', 'http')) else 'plaintext'})")
    report_rotation(rotated)

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
    write_android_micro_config(android_micro)

    config, study = serialize_ios_config(source, settings, EXAMPLE_PATH, CONFIG_PATH, env["STUDY_KEY"])
    write_micro_config(config)
    write_ios_esm_config(build_ios_esm_config(source))
    study_join_path = f"/{study['study_number']}/{study['study_key']}"
    study_join_url = f"{base_url}{study_join_path}"
    write_studies_index(base_url, study_join_path, study_join_url, android_study_url)
    write_deployment_urls(build_deployment_urls(base_url, study_join_url, android_study_url))
    write_nginx_study_key(env["STUDY_KEY"])

    # Read back after everything is written: the check is worth only as much as
    # the files it inspects, and those are the files a phone will be served.
    check_dataflow_applied(source, bind, android_study_url)
    check_placement_applied(source)

    chown_generated_paths(env)
    check_config_permissions()


if __name__ == "__main__":
    main()
