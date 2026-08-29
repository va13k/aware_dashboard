#!/usr/bin/env python3
"""The study's database made ready: both schemas, every account, and the tables.

This is the only thing that creates anything. A database this deployment runs gets
its whole schema from ``db/init_all.sql``, which MySQL applies through ``--init-file``
on every start, before anything else is up to ask about it. A database the researcher
names has no such file and no such moment, so the same work is done here, over the
network, as the account the provider handed out.

The order is the whole of it. Each schema file grants the reads its own tables need
beside the table it has just created, so the accounts have to exist before any of
them runs, and the tables have to exist before anything is granted on them. A grant
issued against a table that is not there is `ERROR 1146`, and MySQL stops at it ---
which is how a deployment ends up holding a schema, its accounts, and none of the
tables a phone writes to.

Both platforms, always. The study model declares a schema for each and the dashboard
is handed a URL into each, so a deployment that provisioned one of them would leave a
service pointed at a database that does not exist.
"""
import argparse
import pathlib
import subprocess
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = SCRIPT_DIR.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from shared_config import database, mysql_client, placement
from shared_config.source_store import read_source
from shared_config.runtime import load_env


ENV_PATH = PROJECT / ".env"

#: Where each platform's tables are declared. Generated from the clients' own
#: providers by db/build_init_all.py, so the tables created here cannot drift from
#: the columns a phone actually sends.
PLATFORM_TABLE_FILES = {
    "android": PROJECT / "db" / "android-tables.sql",
    "ios": PROJECT / "db" / "ios-tables.sql",
}

#: The registry and cache tables both schemas carry. Self-contained: the file names
#: the schema each half belongs to, so it is applied without one.
DASHBOARD_TABLES_SQL_PATH = PROJECT / "db" / "dashboard-tables.sql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--docker-prefix",
        action="append",
        default=[],
        help="Optional command prefix before docker, for example: --docker-prefix sudo",
    )
    parser.add_argument("--timeout-seconds", type=int, default=90)
    return parser.parse_args()


def run_command(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def build_docker_base(prefix: list[str]) -> list[str]:
    return prefix + ["docker"]


def made_by_hand() -> bool:
    """Whether this study said its database is somebody else's to make ready.

    Then nothing here runs. The account such a study hands over may only write, so
    every statement below would be refused --- and the file setup offers, which
    carries the same schemas, accounts and tables, is what the administrator ran
    instead.
    """
    return str(load_env(ENV_PATH).get("DB_INIT", "")).strip().lower() == "manual"


def load_admin(databases: dict) -> tuple[str, str]:
    """The administrator this runs as, and its password.

    Root for a database this deployment brings up, since that is what it creates.
    A database somebody else runs names its own administrator --- `avnadmin`,
    `doadmin`, whatever the provider chose --- and running as root there fails in a
    way that reads like a wrong password.

    Named by the request where there is one, then by what the host says about its
    provider, and only then by MySQL's own default. A deployment upgraded in place
    has an `.env` written before the question existed, and would otherwise
    authenticate as an account its managed database has never had.
    """
    env = load_env(ENV_PATH)
    password = str(env.get("MYSQL_ROOT_PASSWORD", "")).strip()
    if not password:
        raise RuntimeError("MYSQL_ROOT_PASSWORD is missing from .env")
    admin_user = database.admin_user(
        database.declared_host(databases), env.get("DB_ADMIN_USER", "")
    )
    return admin_user, password


def study_schemas(databases: dict) -> dict[str, str]:
    """The schema each platform's data lands in, by platform."""
    return {
        platform: database.platform_schema(databases, platform)
        for platform in PLATFORM_TABLE_FILES
    }


def wait_for_mysql(
    admin_user: str,
    client: mysql_client.Client,
    docker_base: list[str],
    admin_password: str,
    timeout_seconds: int,
) -> None:
    """Wait until the study's database answers, by whatever means it can be asked.

    A bundled database has a container whose health check is the cheaper and more
    precise signal. A database the researcher names has none, so the question is put
    to the database itself --- which is also the only thing that could answer it.
    """
    deadline = time.time() + timeout_seconds
    inspect_command = docker_base + [
        "inspect",
        "-f",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
        mysql_client.BUNDLED_CONTAINER,
    ]

    last = ""
    while time.time() < deadline:
        if client.bundled:
            result = run_command(inspect_command)
            if result.returncode == 0 and result.stdout.strip().lower() == "healthy":
                return
            last = result.stderr.strip()
        else:
            result = client.run(admin_user, admin_password, "SELECT 1;", batch=True)
            if result.returncode == 0:
                return
            last = mysql_client.error_of(result)
        time.sleep(2)

    raise RuntimeError(
        f"Timed out waiting for {client.describe()} to answer."
        + (f" Last error: {last}" if last else "")
    )


def ensure_schemas(
    admin_user: str,
    client: mysql_client.Client,
    admin_password: str,
    schemas: list[str],
) -> None:
    """Every schema this study's data lands in."""
    statements = [
        f"CREATE DATABASE IF NOT EXISTS {mysql_client.quote_identifier(schema)} "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
        for schema in schemas
    ]
    result = client.run(admin_user, admin_password, "\n".join(statements))
    if result.returncode != 0:
        raise RuntimeError(
            mysql_client.error_of(result) or "Failed to create the study's schemas"
        )


def ensure_accounts(
    admin_user: str,
    client: mysql_client.Client,
    admin_password: str,
    profiles: list[dict],
    require_ssl: bool,
) -> None:
    """Every account this deployment opens the database with, on the password it holds.

    Created and settled in one pass. The accounts a bundled database seeds from
    `db/init_all.sql` carry a first-boot password, `CREATE USER IF NOT EXISTS` leaves
    an existing account's alone, and a deployment redeployed onto an existing volume
    would otherwise advertise a password its accounts never took. So the password is
    stated rather than assumed, for accounts that are new here and for accounts that
    are not.

    Encryption is stated in both directions. An `ALTER USER` with no `REQUIRE` leaves
    the clause the account already carries, so a study moved onto a server that
    cannot encrypt would keep accounts refusing every connection it can make, and the
    deployment would look configured.

    Grants here are schema-level and nothing else: the rows an account reads back are
    granted table by table in the files that create those tables, which is what keeps
    a grant from running before its table exists.
    """
    require = " REQUIRE SSL" if require_ssl else " REQUIRE NONE"
    statements = []
    for profile in profiles:
        user = f"{mysql_client.quote_sql_string(profile['username'])}@'%'"
        password = mysql_client.quote_sql_string(profile["password"])
        statements.append(f"CREATE USER IF NOT EXISTS {user} IDENTIFIED BY {password};")
        statements.append(f"ALTER USER {user} IDENTIFIED BY {password}{require};")
        privilege = "INSERT" if profile["writes"] else "SELECT"
        for schema in profile["schemas"]:
            statements.append(
                f"GRANT {privilege} ON {mysql_client.quote_identifier(schema)}.* TO {user};"
            )
    statements.append("FLUSH PRIVILEGES;")

    result = client.run(admin_user, admin_password, "\n".join(statements))
    if result.returncode != 0:
        raise RuntimeError(
            mysql_client.error_of(result) or "Failed to create the study's database accounts"
        )


def apply_sql_file(
    admin_user: str,
    client: mysql_client.Client,
    admin_password: str,
    path: pathlib.Path,
    schema: str = "",
) -> None:
    """One schema file, applied whole.

    Stopping at the first failed statement is deliberate. Everything in these files
    is idempotent, so a run that reports an error has found a real one --- and a run
    that carried on past it would leave the tables after it uncreated while saying
    the database was ready.
    """
    with path.open("r", encoding="utf-8") as sql_file:
        result = client.run(admin_user, admin_password, schema=schema, stdin=sql_file)
    if result.returncode != 0:
        raise RuntimeError(
            mysql_client.error_of(result) or f"Failed to apply {path.name}"
        )


def main() -> int:
    args = parse_args()
    docker_base = build_docker_base(args.docker_prefix)
    if made_by_hand():
        print(
            "database: made by hand — nothing created here. "
            "setup/verify_database.py reports what the administrator's run left."
        )
        return 0
    source = read_source()
    databases = source.get("database") or {}
    admin_user, admin_password = load_admin(databases)
    schemas = study_schemas(databases)
    profiles = database.profiles(databases, database.analytics_password(load_env(ENV_PATH)))
    client = mysql_client.Client.for_study(docker_base, source)
    print(f"database: {placement.declared(source)} — {client.describe()}")

    wait_for_mysql(admin_user, client, docker_base, admin_password, args.timeout_seconds)
    ensure_schemas(admin_user, client, admin_password, list(schemas.values()))
    ensure_accounts(
        admin_user,
        client,
        admin_password,
        profiles,
        database.tls_required(databases),
    )
    for platform, schema in schemas.items():
        apply_sql_file(
            admin_user, client, admin_password, PLATFORM_TABLE_FILES[platform], schema
        )
    apply_sql_file(admin_user, client, admin_password, DASHBOARD_TABLES_SQL_PATH)

    print(f"Schemas ready: {', '.join(schemas.values())}.")
    print(f"Accounts on their configured passwords: {', '.join(p['username'] for p in profiles)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
