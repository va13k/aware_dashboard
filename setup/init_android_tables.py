#!/usr/bin/env python3
import argparse
import json
import pathlib
import subprocess
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = SCRIPT_DIR.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from shared_config import database, dataflow
from shared_config.source_store import read_source
from shared_config.runtime import load_env


ENV_PATH = PROJECT / ".env"
SOURCE_PATH = PROJECT / "source.json"
# Generated from the AWARE client's providers by db/build_init_all.py, so the
# tables created here cannot drift from the columns the client actually sends.
ANDROID_INIT_SQL_PATH = PROJECT / "db" / "android-tables.sql"
MYSQL_CONTAINER = "aware_mysql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--docker-prefix",
        action="append",
        default=[],
        help="Optional command prefix before docker, for example: --docker-prefix sudo",
    )
    parser.add_argument("--timeout-seconds", type=int, default=90)
    return parser.parse_args()


def run_command(
    command: list[str],
    *,
    stdin=None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        stdin=stdin,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def quote_sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def build_docker_base(prefix: list[str]) -> list[str]:
    return prefix + ["docker"]


def load_android_db_settings() -> tuple[str, str]:
    """The root password and the schema Android data lives in."""
    env = load_env(ENV_PATH)
    mysql_root_password = str(env.get("MYSQL_ROOT_PASSWORD", "")).strip()
    if not mysql_root_password:
        raise RuntimeError("MYSQL_ROOT_PASSWORD is missing from .env")

    return (
        mysql_root_password,
        str(read_source()["database"]["android"]["name"]).strip(),
    )


def load_database_accounts() -> list[dict]:
    """The accounts this deployment writes with, and the credentials it expects.

    source.json is authoritative: deploy_config seeds each password from .env, and
    the Configurator writes any later change back to both. Android holds two --- the
    participant account a phone opens the database with, and the micro-server's own,
    which performs every write on the webservice dataflow --- so both are listed and
    each carries its own password.

    ``require_ssl`` is applied to the account the study's dataflow puts on the ingest
    path and left as None elsewhere, which keeps an account's existing requirement.
    The requirement describes the connection ingest actually makes, so it lands on
    the account making it rather than on one nothing is opening.

    Each entry carries the platform whose schema it writes, so a caller provisioning
    one schema selects the accounts belonging to it.
    """
    source = read_source()
    databases = source["database"]
    on_path_name, _ = database.android_credentials(
        databases, dataflow.declared(source, "android")
    )
    server = database.android_ingest_account(dataflow.WEBSERVICE)

    def requirement(entry: dict, username: str):
        if username != on_path_name or "require_ssl" not in entry:
            return None
        return bool(entry["require_ssl"])

    accounts = []
    for platform, name_key, password_key in (
        ("android", "username", "password"),
        ("android", server["name_key"], server["password_key"]),
        ("ios", "username", "password"),
    ):
        entry = databases.get(platform)
        if not entry:
            continue
        username = str(entry.get(name_key, "")).strip()
        if not username:
            continue
        accounts.append(
            {
                "platform": platform,
                "username": username,
                "password": str(entry.get(password_key, "")).strip(),
                "require_ssl": requirement(entry, username),
            }
        )
    return accounts


def wait_for_mysql(docker_base: list[str], timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    inspect_command = docker_base + [
        "inspect",
        "-f",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
        MYSQL_CONTAINER,
    ]

    while time.time() < deadline:
        result = run_command(inspect_command)
        status = result.stdout.strip().lower()
        if result.returncode == 0 and status == "healthy":
            return
        time.sleep(2)

    stderr = result.stderr.strip() if "result" in locals() else ""
    raise RuntimeError(
        "Timed out waiting for MySQL container to become healthy."
        + (f" Last error: {stderr}" if stderr else "")
    )


def ensure_android_database(
    docker_base: list[str],
    mysql_root_password: str,
    database_name: str,
    writers: list[dict],
) -> None:
    """The Android schema and the accounts that insert into it.

    One statement list per account, so a deployment holds the participant account
    phones open the database with and the micro-server's own, each able to write the
    schema its dataflow sends data to. What each account reads back is granted where
    those tables are created.
    """
    statements = [
        f"CREATE DATABASE IF NOT EXISTS {quote_identifier(database_name)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
    ]
    for writer in writers:
        account = f"{quote_sql_string(writer['username'])}@'%'"
        statements.append(
            f"CREATE USER IF NOT EXISTS {account} "
            f"IDENTIFIED BY {quote_sql_string(writer['password'])};"
        )
        statements.append(
            f"GRANT INSERT ON {quote_identifier(database_name)}.* TO {account};"
        )
    statements.append("FLUSH PRIVILEGES;")
    sql = "\n".join(statements)
    command = docker_base + [
        "exec",
        "-i",
        MYSQL_CONTAINER,
        "mysql",
        "--protocol=TCP",
        "-h127.0.0.1",
        "-uroot",
        f"-p{mysql_root_password}",
    ]
    result = run_command(command, input_text=sql)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to ensure Android database exists")


def apply_account_passwords(
    docker_base: list[str],
    mysql_root_password: str,
    accounts: list[dict],
) -> None:
    """Force each account onto the password this deployment expects of it.

    db/zz-participant-password.sh only runs on an empty data directory, and
    init_all.sql creates the accounts with CREATE USER IF NOT EXISTS, so
    redeploying onto an existing MySQL volume would otherwise leave the
    accounts on whatever password they were first given while .env, the served
    study config and the micro-server's configuration advertise a newer one.

    Creating what is missing is part of it: this is what gives an existing
    deployment the micro-server's account with the password its generated
    configuration already names.
    """
    statements = []
    for account in accounts:
        user = f"{quote_sql_string(account['username'])}@'%'"
        password = quote_sql_string(account["password"])
        require = ""
        if account["require_ssl"] is not None:
            require = " REQUIRE SSL" if account["require_ssl"] else " REQUIRE NONE"
        statements.append(f"CREATE USER IF NOT EXISTS {user} IDENTIFIED BY {password};")
        statements.append(f"ALTER USER {user} IDENTIFIED BY {password}{require};")
    statements.append("FLUSH PRIVILEGES;")

    command = docker_base + [
        "exec",
        "-i",
        MYSQL_CONTAINER,
        "mysql",
        "--protocol=TCP",
        "-h127.0.0.1",
        "-uroot",
        f"-p{mysql_root_password}",
    ]
    result = run_command(command, input_text="\n".join(statements))
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "Failed to apply the database account passwords"
        )


def apply_android_tables(
    docker_base: list[str],
    mysql_root_password: str,
    database_name: str,
) -> None:
    command = docker_base + [
        "exec",
        "-i",
        MYSQL_CONTAINER,
        "mysql",
        "--protocol=TCP",
        "-h127.0.0.1",
        "-uroot",
        f"-p{mysql_root_password}",
        database_name,
    ]
    with ANDROID_INIT_SQL_PATH.open("r", encoding="utf-8") as sql_file:
        result = run_command(command, stdin=sql_file)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to initialize Android database tables")


def main() -> int:
    args = parse_args()
    docker_base = build_docker_base(args.docker_prefix)
    mysql_root_password, database_name = load_android_db_settings()
    accounts = load_database_accounts()

    wait_for_mysql(docker_base, args.timeout_seconds)
    ensure_android_database(
        docker_base,
        mysql_root_password,
        database_name,
        [a for a in accounts if a["platform"] == "android"],
    )
    apply_account_passwords(docker_base, mysql_root_password, accounts)
    # Runs after the accounts exist: this file grants the micro-server's account the
    # reads its device-metadata upsert makes, and a grant needs its grantee.
    apply_android_tables(docker_base, mysql_root_password, database_name)
    print("Android database tables are ready.")
    print("Database accounts are using the configured passwords.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
