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


def load_android_db_settings() -> tuple[str, str, str, str]:
    env = load_env(ENV_PATH)
    mysql_root_password = str(env.get("MYSQL_ROOT_PASSWORD", "")).strip()
    if not mysql_root_password:
        raise RuntimeError("MYSQL_ROOT_PASSWORD is missing from .env")

    source = read_source()
    android_db = source["database"]["android"]
    return (
        mysql_root_password,
        str(android_db["name"]).strip(),
        str(android_db["username"]).strip(),
        str(android_db["password"]).strip(),
    )


def load_participant_accounts() -> list[dict]:
    """The participant accounts and the credentials this deployment expects.

    source.json is authoritative: deploy_config seeds it from
    PARTICIPANT_DB_PASSWORD in .env, and the Configurator writes any later
    change back to both. ``require_ssl`` is None when the platform does not
    configure one, which leaves the account's existing requirement alone.
    """
    databases = read_source()["database"]
    accounts = []
    for platform in ("android", "ios"):
        database = databases.get(platform)
        if not database:
            continue
        username = str(database.get("username", "")).strip()
        if not username:
            continue
        accounts.append(
            {
                "username": username,
                "password": str(database.get("password", "")).strip(),
                "require_ssl": (
                    bool(database["require_ssl"])
                    if "require_ssl" in database
                    else None
                ),
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
    insert_username: str,
    insert_password: str,
) -> None:
    sql = "\n".join(
        [
            f"CREATE DATABASE IF NOT EXISTS {quote_identifier(database_name)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
            (
                "CREATE USER IF NOT EXISTS "
                f"{quote_sql_string(insert_username)}@'%' IDENTIFIED BY {quote_sql_string(insert_password)};"
            ),
            (
                "GRANT INSERT ON "
                f"{quote_identifier(database_name)}.* TO {quote_sql_string(insert_username)}@'%';"
            ),
            "FLUSH PRIVILEGES;",
        ]
    )
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


def apply_participant_passwords(
    docker_base: list[str],
    mysql_root_password: str,
    accounts: list[dict],
) -> None:
    """Force the participant accounts onto this deployment's password.

    db/zz-participant-password.sh only runs on an empty data directory, and
    init_all.sql creates the accounts with CREATE USER IF NOT EXISTS, so
    redeploying onto an existing MySQL volume would otherwise leave the
    accounts on whatever password they were first given while .env and the
    served study config advertise a newer one.
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
            result.stderr.strip() or "Failed to apply the participant account password"
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
    (
        mysql_root_password,
        database_name,
        insert_username,
        insert_password,
    ) = load_android_db_settings()

    wait_for_mysql(docker_base, args.timeout_seconds)
    ensure_android_database(
        docker_base,
        mysql_root_password,
        database_name,
        insert_username,
        insert_password,
    )
    apply_participant_passwords(
        docker_base,
        mysql_root_password,
        load_participant_accounts(),
    )
    apply_android_tables(docker_base, mysql_root_password, database_name)
    print("Android database tables are ready.")
    print("Participant accounts are using the configured password.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
