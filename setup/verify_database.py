#!/usr/bin/env python3
"""Ask the database the questions this deployment will ask it, before it is committed to.

A study can be configured against a database nobody can reach, or one that answers
and refuses every write, and either way the deployment comes up looking healthy and
collects nothing. The same four questions are asked whichever placement the study
runs, because the answer matters equally for both --- a bundled container that
failed to initialise its schema is as silent as an institutional host behind a
firewall:

``reachable``
    The address answers on its port and the credential authenticates.

``schema``
    The study's schema is there, or this account can create it.

``write``
    The account that will carry the study's rows can insert one, and it can be read
    back afterwards. Reachability and writability are different questions, and the
    second is the one a study depends on.

``accounts``
    The account each dataflow puts on the ingest path exists with the grants its
    work needs, or can be created.

Privileges are found out rather than assumed. A researcher handed a database by
their institution rarely holds ``CREATE USER``, so where a step is refused for want
of a privilege the exact SQL is printed for whoever does hold it, and the check can
be run again afterwards. That is the difference between a deployment that cannot
proceed and one that needs a colleague to run four statements.

The client runs on the deployment's own network rather than on this machine, so the
question asked is the one the micro-server and the API will ask: a host that
resolves here and not in a container is a study that fails after setup has said it
is fine.

Run from the host::

    python3 setup/verify_database.py --docker-prefix sudo
    python3 setup/verify_database.py --host db.example.edu --port 3306 \\
        --admin-user aware_admin --admin-password ... --placement external
"""

import argparse
import json
import pathlib
import secrets
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = pathlib.Path("/project") if pathlib.Path("/project/shared_config").is_dir() else SCRIPT_DIR.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from shared_config import database, dataflow, mysql_client, placement
from shared_config.runtime import SECRET_MODE, atomic_write_text, load_env
from shared_config.source_store import read_source

ENV_PATH = PROJECT / ".env"
RESULT_PATH = PROJECT / "setup" / ".database-check.json"

#: Written and read back to prove the account can carry the study's rows. It holds
#: no `timestamp` column, which is what keeps it out of the coverage rollup: the
#: builder walks every timestamped table it finds, and a scratch table with one
#: would arrive on the grid as a sensor nobody configured.
PROBE_TABLE = "_aware_write_check"

PROBE_TABLE_SQL = f"""CREATE TABLE IF NOT EXISTS `{PROBE_TABLE}` (
  `_id`        bigint unsigned NOT NULL AUTO_INCREMENT,
  `checked_at` varchar(64)     NOT NULL DEFAULT '',
  `note`       varchar(128)    NOT NULL DEFAULT '',
  PRIMARY KEY (`_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--docker-prefix", action="append", default=[])
    parser.add_argument(
        "--placement",
        choices=placement.CHOICES,
        help="Which placement to check. Read from the study model when omitted.",
    )
    parser.add_argument("--host", help="Database host. Read from the study model when omitted.")
    parser.add_argument("--port", type=int, help="Database port")
    parser.add_argument("--admin-user", help="The account that creates the schema")
    parser.add_argument("--admin-password", help="Its password")
    parser.add_argument("--schema", help="The schema the study's Android data lives in")
    parser.add_argument("--json-out", default=str(RESULT_PATH))
    parser.add_argument("--quiet", action="store_true", help="Write the result without printing it")
    return parser.parse_args()


def check(
    name: str, ok: bool, detail: str, sql: str = "", skipped: bool = False, warning: bool = False
) -> dict:
    """One question and its answer, with the SQL that would settle it where there is any.

    A warning is a question answered badly that does not stop a study collecting, so
    it is reported and does not fail the check.
    """
    return {
        "name": name,
        "ok": bool(ok),
        "skipped": bool(skipped),
        "warning": bool(warning),
        "detail": detail,
        "sql": sql,
    }


def check_reachable(client: mysql_client.Client, user: str, password: str, host: str, port: int) -> dict:
    result = client.run(user, password, "SELECT 1;")
    if result.returncode == 0:
        where = "the deployment's network" if client.on_network() else "this host"
        return check("reachable", True, f"{host}:{port} answered and {user} authenticated, from {where}.")
    message = mysql_client.error_of(result)
    if "access denied" in message.lower():
        return check("reachable", False, f"{host}:{port} answered and refused {user}: {message}")
    return check(
        "reachable",
        False,
        f"{host}:{port} could not be reached: {message} Nothing this deployment runs "
        "will reach it either.",
    )


def check_schema(client: mysql_client.Client, user: str, password: str, schema: str) -> dict:
    present = client.run(
        user,
        password,
        "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = "
        f"{mysql_client.quote_sql_string(schema)};",
        batch=True,
    )
    if present.returncode == 0 and present.stdout.strip():
        return check("schema", True, f"{schema} is present.")

    created = client.run(
        user,
        password,
        f"CREATE DATABASE IF NOT EXISTS {mysql_client.quote_identifier(schema)} "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
    )
    if created.returncode == 0:
        return check("schema", True, f"{schema} was created.")
    return check(
        "schema",
        False,
        f"{schema} is absent and {user} may not create it: {mysql_client.error_of(created)}",
        sql=f"CREATE DATABASE {mysql_client.quote_identifier(schema)} "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
        f"GRANT ALL ON {mysql_client.quote_identifier(schema)}.* TO {mysql_client.quote_sql_string(user)}@'%';",
    )


def check_accounts(
    client: mysql_client.Client, admin_user: str, admin_password: str, schema: str, accounts: list[dict]
) -> dict:
    """The accounts this study's dataflows write with, present with the grants they need.

    The grants named here are the ones each account's own work requires: a phone
    delivers rows and reads nothing back, and the micro-server additionally reads the
    enrolment registry before a write, keeps the refusal counters and rewrites the
    device row.
    """
    statements = []
    for account in accounts:
        user = mysql_client.quote_sql_string(account["username"]) + "@'%'"
        statements.append(
            f"CREATE USER IF NOT EXISTS {user} IDENTIFIED BY {mysql_client.quote_sql_string(account['password'])};"
        )
        statements.append(f"GRANT INSERT ON {mysql_client.quote_identifier(schema)}.* TO {user};")
        for table, grant in account.get("extra_grants", {}).items():
            statements.append(
                f"GRANT {grant} ON {mysql_client.quote_identifier(schema)}.{mysql_client.quote_identifier(table)} TO {user};"
            )
    statements.append("FLUSH PRIVILEGES;")
    sql = "\n".join(statements)

    result = client.run(admin_user, admin_password, sql)
    named = ", ".join(account["username"] for account in accounts)
    if result.returncode == 0:
        return check("accounts", True, f"{named} exist with the grants their work needs.")
    return check(
        "accounts",
        False,
        f"{admin_user} may not create or grant to {named}: {mysql_client.error_of(result)}",
        sql=sql,
    )


def check_write(
    client: mysql_client.Client, admin_user: str, admin_password: str, schema: str, writer: dict
) -> dict:
    """A row carried by the account that will carry the study's, and read back.

    The scratch table is made by the administrator and written by the writer, which
    is the split the deployment runs on: the account on the ingest path is granted to
    insert and nothing else, so it neither creates what it writes into nor clears up
    after itself.
    """
    note = secrets.token_hex(8)
    made = client.run(admin_user, admin_password, PROBE_TABLE_SQL, schema)
    if made.returncode != 0:
        return check(
            "write",
            False,
            f"A table to write into could not be created in {schema}: {mysql_client.error_of(made)}",
            sql=PROBE_TABLE_SQL,
        )

    try:
        written = client.run(
            writer["username"],
            writer["password"],
            f"INSERT INTO {mysql_client.quote_identifier(PROBE_TABLE)} (`checked_at`, `note`) VALUES "
            f"({mysql_client.quote_sql_string(datetime.now(timezone.utc).isoformat(timespec='seconds'))}, "
            f"{mysql_client.quote_sql_string(note)});",
            schema,
        )
        if written.returncode != 0:
            hint = ""
            if mysql_client.denied(written):
                hint = (
                    f" Every row this study collects is written by {writer['username']}, "
                    "so nothing would arrive."
                )
            return check(
                "write",
                False,
                f"{writer['username']} could not write to {schema}: {mysql_client.error_of(written)}{hint}",
                sql=f"GRANT INSERT ON {mysql_client.quote_identifier(schema)}.* TO "
                f"{mysql_client.quote_sql_string(writer['username'])}@'%';",
            )

        read_back = client.run(
            admin_user,
            admin_password,
            f"SELECT COUNT(*) FROM {mysql_client.quote_identifier(PROBE_TABLE)} WHERE `note` = "
            f"{mysql_client.quote_sql_string(note)};",
            schema,
            batch=True,
        )
        if read_back.returncode != 0 or read_back.stdout.strip() != "1":
            return check(
                "write",
                False,
                f"{writer['username']} reported the row written and {schema} does not hold it.",
            )
        return check(
            "write",
            True,
            f"A row written by {writer['username']} was read back from {schema}.",
        )
    finally:
        client.run(
            admin_user,
            admin_password,
            f"DROP TABLE IF EXISTS {mysql_client.quote_identifier(PROBE_TABLE)};",
            schema,
        )


def ingest_accounts(source: dict) -> tuple[list[dict], dict]:
    """Every account a dataflow puts on the ingest path, and the one this study uses.

    Both are provisioned whichever dataflow the study runs, so a study switching
    paths finds the account on its new one already holding the password its
    generated configuration names. Only the one on the current path is what a failed
    write would stop.
    """
    databases = source.get("database") or {}
    entry = databases.get("android") or {}
    accounts = []
    for choice in (dataflow.DIRECT, dataflow.WEBSERVICE):
        username, password = database.android_credentials(databases, choice)
        if not username:
            continue
        account = {"username": username, "password": password, "dataflow": choice}
        if choice == dataflow.WEBSERVICE:
            account["extra_grants"] = {
                "device_enrolment": "SELECT",
                "refusals": "SELECT, INSERT, UPDATE",
                "aware_device": "SELECT, UPDATE",
            }
        accounts.append(account)

    on_path = dataflow.declared(source, "android")
    current = next((a for a in accounts if a["dataflow"] == on_path), accounts[0] if accounts else {})
    return accounts, current


def verify(
    docker_base: list[str],
    host: str,
    port: int,
    admin_user: str,
    admin_password: str,
    schema: str,
    accounts: list[dict],
    writer: dict,
) -> list[dict]:
    """The four questions, in the order a later one depends on an earlier."""
    client = mysql_client.Client(docker_base, host, port)

    reachable = check_reachable(client, admin_user, admin_password, host, port)
    if not reachable["ok"]:
        return [
            reachable,
            check("schema", False, "Not attempted: the database did not answer."),
            check("accounts", False, "Not attempted: the database did not answer."),
            check("write", False, "Not attempted: the database did not answer."),
        ]

    schema_check = check_schema(client, admin_user, admin_password, schema)
    if not schema_check["ok"]:
        return [
            reachable,
            schema_check,
            check("accounts", False, "Not attempted: the schema is not there to grant on."),
            check("write", False, "Not attempted: the schema is not there to write into."),
        ]

    accounts_check = check_accounts(client, admin_user, admin_password, schema, accounts)
    write_check = check_write(client, admin_user, admin_password, schema, writer)

    if not accounts_check["ok"] and write_check["ok"]:
        accounts_check["warning"] = True
        accounts_check["detail"] += (
            f" The account this study writes with, {writer['username']}, is already there "
            "and works, so the study collects. Apply the grants below before switching "
            "the study to the other dataflow, whose account may not be."
        )

    return [reachable, schema_check, accounts_check, write_check]


def report(result: dict) -> None:
    labels = {
        "reachable": "Reachable",
        "schema": "Schema",
        "accounts": "Ingest accounts",
        "write": "A row can be written",
    }
    print("")
    print(f"  Database check ({result['placement']} — {result['host']}:{result['port']})")
    print("  " + "─" * 52)
    for entry in result["checks"]:
        if entry["skipped"]:
            mark = "skip"
        elif entry["ok"]:
            mark = "ok"
        elif entry.get("warning"):
            mark = "warn"
        else:
            mark = "FAIL"
        print(f"  [{mark:>4}] {labels.get(entry['name'], entry['name'])}")
        print(f"         {entry['detail']}")
    print("")

    outstanding = [entry for entry in result["checks"] if not entry["ok"] and entry.get("sql")]
    if outstanding:
        print("  Hand these to whoever administers the database, then run this again.")
        print("  They carry this study's account passwords, so send them the way you would")
        print("  send a credential:")
        print("")
        for entry in outstanding:
            for line in entry["sql"].splitlines():
                print(f"      {line}")
        print("")

    if result["ok"]:
        print("  The database is reachable and this study can write to it.")
    else:
        print("  This study cannot collect against that database yet.")
    print("")


def main() -> int:
    args = parse_args()
    docker_base = args.docker_prefix + ["docker"]

    env = load_env(ENV_PATH)
    source = read_source()
    databases = source.get("database") or {}

    host = args.host or database.declared_host(databases)
    chosen = args.placement or placement.declared_for_host(host)
    # A bundled database is reached by its compose name whatever the model declares,
    # which is the same resolution every service inside the deployment uses.
    if chosen == placement.BUNDLED:
        host = database.COMPOSE_HOST
    port = args.port or database.platform_port(databases, "android")
    schema = args.schema or database.platform_schema(databases, "android")
    admin_user = args.admin_user or "root"
    admin_password = args.admin_password or str(env.get("MYSQL_ROOT_PASSWORD", "")).strip()

    accounts, writer = ingest_accounts(source)

    result = {
        "placement": chosen,
        "host": host,
        "port": port,
        "schema": schema,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": [],
        "ok": False,
    }

    refusal = placement.unsupported_reason(chosen, dataflow.declared(source, "android"))
    if refusal:
        result["checks"] = [check("reachable", False, refusal)]
    elif not admin_password:
        result["checks"] = [
            check("reachable", False, "No administrator password was given, so nothing can be checked.")
        ]
    else:
        result["checks"] = verify(
            docker_base, host, port, admin_user, admin_password, schema, accounts, writer
        )

    result["ok"] = all(entry["ok"] or entry.get("warning") for entry in result["checks"])
    atomic_write_text(pathlib.Path(args.json_out), json.dumps(result, indent=2) + "\n", SECRET_MODE)
    if not args.quiet:
        report(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
