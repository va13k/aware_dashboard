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

``tls``
    The connection is what the study asked of it. A database this deployment runs is
    always encrypted; one the researcher names answers to its owner, so the study
    declares what it needs and this is where the server is held to it --- including
    the certificate authority, checked here rather than first on a phone.

``schema``
    Both schemas this study's data lands in are there. Both, because a deployment
    serves both platforms: the dashboard is handed a URL into each.

``accounts``
    Every account this deployment opens the database with --- the one each Android
    dataflow puts on the ingest path, the iOS micro-server's, and the dashboard's
    own --- connects with the password this study holds.

``tables``
    The tables a phone's rows land in are there. An account holding every grant it
    needs on an empty schema collects nothing, and says so only on the device.

Nothing here writes to the database. The check reports what a deployment would find
and the deployment is what makes it so, which is the only arrangement where the
answer means anything: a check that created what it was asked about could only
report success, and would report it against a database the researcher has not agreed
to have changed yet. What is missing before the first deploy is therefore not a
failure but a line saying which side is going to create it --- setup, or whoever
administers a database that setup may not touch. For the second, the statements and
the tables are written out as a file to hand over.

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
import re
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

#: The cache and registry tables both schemas carry, which the deployment applies
#: alongside each platform's own and the setup file hands over with them.
DASHBOARD_TABLES_SQL = PROJECT / "db" / "dashboard-tables.sql"


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
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Report what is missing as somebody else's to create, not the deploy's.",
    )
    parser.add_argument(
        "--sql-out",
        help="Write the statements an administrator would run to this file, and stop.",
    )
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
    host = mysql_client.without_credentials(host)
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
        f"will reach it either.{unreachable_hint(message, port)}",
    )


def unreachable_hint(message: str, port: int) -> str:
    """What usually explains a database that resolves and then says nothing.

    The client reports the failure and not its cause, and the two causes want
    opposite fixes --- one is a field on the form, the other is a setting at the
    provider. A name that resolves rules out the third (a typo), so the answer is
    worth narrowing rather than leaving as "could not be reached".
    """
    lowered = message.lower()
    if "unknown mysql server host" in lowered:
        return (
            " That name does not resolve at all, so check it for a typo — it is the "
            "host on its own, without the scheme, the account or the database."
        )
    if "can't connect" not in lowered and "connection refused" not in lowered:
        return ""

    hint = (
        " The name resolves, so the address is right and nothing answered on that "
        "port."
    )
    if port == 3306:
        hint += (
            " Managed databases often listen somewhere else: Aiven and DigitalOcean "
            "give each service a port of its own, printed beside the host in their "
            "console. 3306 is the default here, not necessarily theirs."
        )
    return hint + (
        " If the port is right, the provider is likely refusing this machine: add "
        "its address to the allowed list (Aiven calls it Allowed IP addresses, "
        "DigitalOcean Trusted sources, Google Cloud SQL Authorized networks)."
    )


def session_cipher(client: mysql_client.Client, user: str, password: str) -> str:
    """The cipher this connection negotiated, or "" when it arrived in clear text.

    The session is asked rather than the server's configuration. ``have_ssl`` was the
    variable that answered the question directly and MySQL 8.4 removed it, so reading
    it would report every recent server as unable to encrypt --- while what a study
    actually depends on is whether a connection came up encrypted, which this is.
    """
    result = client.run(user, password, "SHOW STATUS LIKE 'Ssl_cipher';", batch=True)
    if result.returncode != 0:
        return ""
    parts = result.stdout.strip().split()
    return parts[-1] if len(parts) > 1 else ""


def check_tls(
    client: mysql_client.Client,
    user: str,
    password: str,
    required: bool,
    authority: str = "",
    exposure: str = "",
) -> dict:
    """Whether the connection is what this study asked of it, and how far it is trusted.

    Asked because the answer decides whether anything can write at all: the accounts
    are created requiring an encrypted session wherever the study asked for one, so a
    server that cannot offer TLS to a study that demands it authenticates and then
    refuses every insert. Finding that out here is the difference between a failed
    check and a deployment that comes up healthy and collects nothing.

    A study that asked for plaintext is reported rather than failed. That is the
    answer a researcher gave about a server they own, and this check's job is to say
    what it costs --- including whether the server would have encrypted anyway, since
    a study running in clear text against a database that could have done better is
    worth going back for.

    Verification is reported apart from encryption, because they fail for different
    reasons. A database this deployment runs signs its own certificate with no
    subject alternative name, so nothing can check who answered; that is a limit to
    state. A database the researcher names may present a real one, and an authority
    supplied for it is checked here rather than first on a participant's phone --- a
    certificate that does not chain to it is a study whose devices keep their data and
    stop uploading.
    """
    if not required:
        cipher = session_cipher(client, user, password)
        offered = (
            " The server does offer encryption --- the connection this check made came "
            "up encrypted --- so this study is in clear text by its own setting rather "
            "than by the server's limits."
            if cipher
            else " The server did not offer encryption either."
        )
        return check(
            "tls",
            False,
            "This study asked for an unencrypted connection to its database."
            + (f" {exposure}" if exposure else "")
            + offered,
            warning=True,
        )

    cipher = session_cipher(client.asking_for("REQUIRED"), user, password)
    if not cipher:
        return check(
            "tls",
            False,
            "This server would not open an encrypted connection, and this study "
            "requires one --- every account it creates is granted on that condition, so "
            "nothing would be able to write. Enable TLS on the server, use a database "
            "that offers it, or say in setup that this study connects without "
            "encryption.",
        )

    if not authority:
        return check(
            "tls",
            True,
            f"Encrypted ({cipher}). The certificate is not verified: nothing here names "
            "the authority that signed it, so the traffic cannot be read but a server "
            "on the same network could impersonate this one. Supplying a certificate "
            "authority is what closes that.",
        )

    verified = client.asking_for("VERIFY_CA", authority).run(
        user, password, "SELECT 1;", batch=True
    )
    if verified.returncode == 0:
        return check(
            "tls",
            True,
            f"Encrypted ({cipher}) and verified against the certificate authority this "
            "study supplies.",
        )
    return check(
        "tls",
        False,
        "This server's certificate does not check out against the authority this study "
        f"supplies: {mysql_client.error_of(verified)} Devices are given that authority "
        "and verify against it, so they would treat this database as one they cannot "
        "reach and stop uploading. Supply the authority that signed this server's "
        "certificate, or clear it to connect encrypted without verifying.",
    )



def schema_present(
    client: mysql_client.Client, user: str, password: str, schema: str
) -> bool:
    """Whether the server already holds this schema."""
    result = client.run(
        user,
        password,
        "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = "
        f"{mysql_client.quote_sql_string(schema)};",
        batch=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def check_schemas(
    client: mysql_client.Client,
    user: str,
    password: str,
    schemas: list[str],
    create: bool = True,
) -> dict:
    """Every schema this study's data lands in.

    Both of them, because a deployment serves both platforms whichever one a
    participant carries: the dashboard is handed a URL into each schema and the iOS
    micro-server writes its own, so one missing schema is a service that connects to
    nothing rather than a platform quietly left out.
    """
    missing = [name for name in schemas if not schema_present(client, user, password, name)]
    named = ", ".join(schemas)
    if not missing:
        return check("schema", True, f"{named} are present.")
    absent = ", ".join(missing)
    if create:
        return check(
            "schema",
            False,
            f"{absent} will be created when this study deploys.",
            warning=True,
        )
    return check(
        "schema",
        False,
        f"{absent} is absent, and this study asked to have its database made by hand. "
        "Run the setup file against this database, then check again.",
    )


def account_exists(
    client: mysql_client.Client, admin_user: str, admin_password: str, username: str
) -> bool:
    """Whether MySQL already knows this account, asked without creating it."""
    result = client.run(
        admin_user,
        admin_password,
        "SELECT 1 FROM mysql.user WHERE user = "
        f"{mysql_client.quote_sql_string(username)} LIMIT 1;",
        batch=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def profile_grants(client: mysql_client.Client, profile: dict) -> list[str]:
    """What the server says this account holds, asked as the account itself.

    Read from the connection the account opened rather than from ``mysql.user`` as
    an administrator, because the account is what a phone and a service authenticate
    as: an answer given to somebody else could be right about the grants and wrong
    about the connection that carries them.
    """
    result = client.run(
        profile["username"], profile["password"], "SHOW GRANTS FOR CURRENT_USER;", batch=True
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_profiles(
    client: mysql_client.Client,
    admin_user: str,
    admin_password: str,
    profiles: list[dict],
    create: bool = True,
) -> dict:
    """Every account this deployment opens the database with, asked to open it.

    The question is the one each service will ask: the account connects with the
    password this study holds, over the connection this study declared. Nothing is
    granted and nothing is created --- an account refused for a password it does not
    have and an account refused for a schema that does not exist are the same
    message otherwise, and only one of them is a credential to fix.

    An account that does not exist yet is not a failure before the first deploy,
    which is what creates it. It is a failure on a database made by hand, where
    nothing else will.
    """
    opened, absent, refused = [], [], []
    for profile in profiles:
        result = client.run(profile["username"], profile["password"], "SELECT 1;", batch=True)
        if result.returncode == 0:
            opened.append(profile["username"])
        elif not account_exists(client, admin_user, admin_password, profile["username"]):
            absent.append(profile["username"])
        else:
            refused.append(f"{profile['username']} ({mysql_client.error_of(result)})")

    parts = []
    if opened:
        parts.append(f"{', '.join(opened)} opened the database.")
    if absent:
        parts.append(
            f"{', '.join(absent)} " + (
                "will be created when this study deploys."
                if create
                else "do not exist, and this study asked to have its database made by hand."
            )
        )
    if refused:
        parts.append(
            f"{', '.join(refused)} exist and would not open it, so the password this "
            "study holds is not the one the account has."
        )

    if refused or (absent and not create):
        return check("accounts", False, " ".join(parts))
    if absent:
        return check("accounts", False, " ".join(parts), warning=True)
    return check("accounts", True, " ".join(parts))


#: Where each platform's tables are declared. The check reads the same files the
#: deploy applies, so what it expects to find cannot drift from what was created.
PLATFORM_TABLE_FILES = {
    "android": PROJECT / "db" / "android-tables.sql",
    "ios": PROJECT / "db" / "ios-tables.sql",
}


def declared_tables(path: pathlib.Path) -> list[str]:
    """The tables a schema file creates, in the order it creates them."""
    if not path.exists():
        return []
    return re.findall(
        r"CREATE TABLE IF NOT EXISTS\s+`(\w+)`", path.read_text(encoding="utf-8")
    )


def present_tables(
    client: mysql_client.Client, user: str, password: str, schema: str
) -> set[str]:
    """What the server holds in this schema."""
    result = client.run(
        user,
        password,
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = "
        f"{mysql_client.quote_sql_string(schema)};",
        batch=True,
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def check_tables(
    client: mysql_client.Client,
    user: str,
    password: str,
    schemas: dict[str, str],
    create: bool = True,
) -> dict:
    """The tables a phone's rows actually land in.

    Asked because an account holding every grant it needs on a schema with no tables
    in it collects nothing, and says so only on the device: the client inserts into
    `accelerometer` and the server answers that no such table exists. A schema that
    is present is not a schema that is ready, and this is the difference.
    """
    reported, short = [], []
    for platform, schema in schemas.items():
        wanted = declared_tables(PLATFORM_TABLE_FILES.get(platform, pathlib.Path()))
        if not wanted:
            continue
        held = present_tables(client, user, password, schema)
        missing = [name for name in wanted if name not in held]
        if missing:
            short.append(
                f"{schema} is missing {len(missing)} of the {len(wanted)} tables this "
                "study writes"
            )
        else:
            reported.append(f"{schema} holds all {len(wanted)} tables this study writes")

    if not short:
        return check("tables", True, "; ".join(reported) + ".")
    detail = "; ".join(short) + "."
    if create:
        return check(
            "tables",
            False,
            detail + " They are created when this study deploys.",
            warning=True,
        )
    return check(
        "tables",
        False,
        detail + " Run the setup file against this database, then check again.",
    )


def verify(
    docker_base: list[str],
    host: str,
    port: int,
    admin_user: str,
    admin_password: str,
    schemas: dict[str, str],
    profiles: list[dict],
    tls_required: bool = True,
    authority: str = "",
    exposure: str = "",
    create: bool = True,
) -> list[dict]:
    """The five questions, in the order a later one depends on an earlier.

    Nothing here writes to the database. The check answers what a deployment would
    find, and the deployment is what makes it so --- a check that created the thing
    it was asked about could only ever report success, and would report it against a
    database the researcher had not agreed to have changed yet.

    ``create`` is whether this study asked the deployment to make its database ready.
    It decides how what is missing reads --- something the next deploy will create,
    or something waiting on whoever administers the server --- and nothing else.
    """
    client = mysql_client.Client(docker_base, host, port)

    reachable = check_reachable(client, admin_user, admin_password, host, port)
    if not reachable["ok"]:
        return [
            reachable,
            check("tls", False, "Not attempted: the database did not answer."),
            check("schema", False, "Not attempted: the database did not answer."),
            check("accounts", False, "Not attempted: the database did not answer."),
            check("tables", False, "Not attempted: the database did not answer."),
        ]

    tls_check = check_tls(
        client, admin_user, admin_password, tls_required, authority, exposure
    )
    # A study that asked for plaintext leaves this failed and warning, which is a
    # connection to carry on checking over. Only a demand the server could not meet
    # stops the rest: every account this study opens the database with is granted on
    # that condition, so what they can do says nothing about what the study would.
    if not tls_check["ok"] and not tls_check["warning"]:
        return [
            reachable,
            tls_check,
            check("schema", False, "Not attempted: this study cannot use an unencrypted server."),
            check("accounts", False, "Not attempted: this study cannot use an unencrypted server."),
            check("tables", False, "Not attempted: this study cannot use an unencrypted server."),
        ]

    schema_check = check_schemas(
        client, admin_user, admin_password, list(schemas.values()), create
    )
    profiles_check = check_profiles(client, admin_user, admin_password, profiles, create)
    tables_check = check_tables(client, admin_user, admin_password, schemas, create)

    statements = account_statements(list(schemas.values()), profiles)
    for entry in (schema_check, profiles_check):
        if not entry["ok"] and not create:
            entry["sql"] = statements

    return [reachable, tls_check, schema_check, profiles_check, tables_check]


LABELS = {
    "reachable": "Reachable",
    "tls": "Encrypted",
    "schema": "Schemas",
    "accounts": "Study accounts",
    "tables": "Tables",
}


def report(result: dict) -> None:
    print("")
    printable_host = mysql_client.without_credentials(result["host"])
    print(f"  Database check ({result['placement']} — {printable_host}:{result['port']})")
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
        print(f"  [{mark:>4}] {LABELS.get(entry['name'], entry['name'])}")
        print(f"         {entry['detail']}")
    print("")

    outstanding = [entry for entry in result["checks"] if not entry["ok"] and entry.get("sql")]
    if outstanding:
        print("  Hand these to whoever administers the database, then run this again.")
        print("  They carry this study's account passwords, so send them the way you would")
        print("  send a credential. The tables come with them, in the file setup offers:")
        print("")
        for line in outstanding[0]["sql"].splitlines():
            print(f"      {line}")
        print("")

    # What is missing before the first deploy is the deploy's to create, so the
    # verdict says which of the two this is rather than reading as ready either way.
    pending = [
        entry
        for entry in result["checks"]
        if entry.get("warning") and entry["name"] in ("schema", "accounts", "tables")
    ]
    if not result["ok"]:
        print("  This study cannot collect against that database yet.")
    elif pending:
        print("  This database can take this study. What is missing is created when it deploys.")
    else:
        print("  The database is ready for this study.")
    print("")


def account_statements(schemas: list[str], profiles: list[dict]) -> str:
    """The schemas and the accounts, as an administrator would create them.

    Schema-level grants only. What each account reads back is granted table by
    table, beside the tables it names, in the files that create them --- stating it
    here as well is what makes a grant run before the table exists.
    """
    lines = []
    for schema in schemas:
        lines.append(
            f"CREATE DATABASE IF NOT EXISTS {mysql_client.quote_identifier(schema)} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
        )
    lines.append("")
    for profile in profiles:
        user = mysql_client.quote_sql_string(profile["username"]) + "@'%'"
        lines.append(
            f"CREATE USER IF NOT EXISTS {user} IDENTIFIED BY "
            f"{mysql_client.quote_sql_string(profile['password'])};"
        )
        privilege = "INSERT" if profile["writes"] else "SELECT"
        for schema in profile["schemas"]:
            lines.append(
                f"GRANT {privilege} ON {mysql_client.quote_identifier(schema)}.* TO {user};"
            )
        lines.append("")
    lines.append("FLUSH PRIVILEGES;")
    return "\n".join(lines)


def setup_sql(schemas: dict[str, str], profiles: list[dict]) -> str:
    """Everything an administrator would run to make this study's database ready.

    The accounts and then the tables, which is the whole of it: a schema and a set of
    accounts with nothing to write into is a database that passes every question
    about privileges and refuses every insert a phone makes. The table files are the
    same ones the deployment applies, so a database made by hand and one made by
    setup end up the same shape.

    Order is not arrangement. Each file grants the reads its own tables need beside
    the table it just created, so the accounts have to exist before any of them runs.
    """
    lines = [
        "-- Generated by the AWARE Dashboard setup wizard.",
        "-- Run as an administrator against the database this study names:",
        "--   mysql -h <host> -P <port> -u <admin> -p < aware-setup.sql",
        "--",
        "-- It creates the schemas, the accounts this study opens them with, and the",
        "-- tables its data lands in. The passwords below are this deployment's own, so",
        "-- treat this file as a credential.",
        "",
        account_statements(list(schemas.values()), profiles),
        "",
    ]
    for platform, schema in schemas.items():
        path = PLATFORM_TABLE_FILES.get(platform)
        if not path or not path.exists():
            continue
        lines.append(f"USE {mysql_client.quote_identifier(schema)};")
        lines.append("")
        lines.append(path.read_text(encoding="utf-8").strip())
        lines.append("")
    if DASHBOARD_TABLES_SQL.exists():
        lines.append(DASHBOARD_TABLES_SQL.read_text(encoding="utf-8").strip())
        lines.append("")
    return "\n".join(lines)


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
    schemas = {
        "android": args.schema or database.platform_schema(databases, "android"),
        "ios": database.platform_schema(databases, "ios"),
    }
    # Whatever the request settled, so running this by hand after a failed deploy
    # asks as the same account the deployment did.
    admin_user = args.admin_user or str(env.get("DB_ADMIN_USER", "")).strip() or "root"
    admin_password = args.admin_password or str(env.get("MYSQL_ROOT_PASSWORD", "")).strip()
    # A study whose database is made by hand is waiting on somebody; one setup
    # deploys is waiting on the deploy. The questions asked are the same either way.
    create = not (args.verify_only or str(env.get("DB_INIT", "")).strip().lower() == "manual")

    profiles = database.profiles(databases, database.analytics_password(env))

    # Asked for on its own, before anything is opened: the file is what somebody
    # hands to an administrator, and needing it is the usual reason the check
    # cannot pass yet.
    if args.sql_out:
        pathlib.Path(args.sql_out).write_text(setup_sql(schemas, profiles), encoding="utf-8")
        if not args.quiet:
            print(f"Wrote {args.sql_out}")
        return 0

    result = {
        "placement": chosen,
        "host": host,
        "port": port,
        "schema": schemas["android"],
        "schemas": schemas,
        # What was asked of the connection, so a reader of the file knows which
        # question the encryption line answers.
        "tls_required": database.tls_required(databases),
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
            docker_base,
            host,
            port,
            admin_user,
            admin_password,
            schemas,
            profiles,
            database.tls_required(databases),
            database.tls_authority(databases),
            placement.unencrypted_warning(chosen, dataflow.declared(source, "android")) or "",
            create,
        )

    result["ok"] = all(entry["ok"] or entry.get("warning") for entry in result["checks"])
    atomic_write_text(pathlib.Path(args.json_out), json.dumps(result, indent=2) + "\n", SECRET_MODE)
    if not args.quiet:
        report(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
