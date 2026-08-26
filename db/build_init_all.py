#!/usr/bin/env python3
"""Generate db/init_all.sql, and check the Android schema against the client.

init_all.sql is a build product. MySQL's --init-file is read server-side and
cannot SOURCE other files, so the deployed schema has to be one concatenated
file; keeping it hand-edited alongside a second copy is what let the two drift
apart for two months and let `bluetooth` lose rows to a missing `bt_status`.

Sources, all hand-written:
    00-bootstrap.sql    databases, accounts, grants
    android-tables.sql  the Android schema
    ios-tables.sql      the iOS schema

Usage:
    build_init_all.py                 regenerate init_all.sql
    build_init_all.py --check         fail if init_all.sql is stale (CI)
    build_init_all.py --check-client PATH_TO_AWARE_CLIENT
                                      also fail if the Android schema is missing
                                      a table or column the client declares
"""
import argparse
import pathlib
import re
import sys

DB = pathlib.Path(__file__).resolve().parent
GENERATED = DB / "init_all.sql"
BANNER = (
    "-- GENERATED FILE - DO NOT EDIT.\n"
    "-- Built by db/build_init_all.py from 00-bootstrap.sql, android-tables.sql\n"
    "-- and ios-tables.sql. Edit those and re-run the script.\n\n"
)


def render() -> str:
    boot = (DB / "00-bootstrap.sql").read_text(encoding="utf-8").rstrip()
    android = (DB / "android-tables.sql").read_text(encoding="utf-8").strip()
    ios = (DB / "ios-tables.sql").read_text(encoding="utf-8").strip()
    # Self-contained (carries its own USE statements), appended last.
    dashboard = (DB / "dashboard-tables.sql").read_text(encoding="utf-8").strip()
    return (
        BANNER
        + boot
        + "\n\nUSE `aware_android`;\n\n"
        + android
        + "\n\nUSE `aware_ios`;\n\n"
        + ios
        + "\n\n"
        + dashboard
        + "\n"
    )


def sql_tables(text: str) -> dict:
    """table -> column list, from CREATE TABLE statements."""
    out = {}
    for m in re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+`(\w+)`\s*\((.*?)\n\)\s*ENGINE", text, re.S
    ):
        out[m.group(1)] = re.findall(r"^\s*`(\w+)`", m.group(2), re.M)
    return out


def client_tables(client_root: pathlib.Path) -> dict:
    """table -> column list, as the Android client's providers declare them.

    This is the authority: Jdbc builds its INSERT column list from
    TABLES_FIELDS, so a column the server lacks fails every insert for that
    table, silently, on the device.
    """
    sys.path.insert(0, str(DB))
    import client_schema  # noqa: E402  (kept beside this script)

    return client_schema.extract(client_root)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--check-client", metavar="AWARE_CLIENT_PATH")
    args = ap.parse_args()

    rendered = render()
    failed = False

    if args.check:
        current = GENERATED.read_text(encoding="utf-8") if GENERATED.exists() else ""
        if current != rendered:
            print("init_all.sql is stale - run db/build_init_all.py", file=sys.stderr)
            failed = True
    else:
        GENERATED.write_text(rendered, encoding="utf-8")
        print(f"wrote {GENERATED.relative_to(DB.parent)}")

    if args.check_client:
        client = client_tables(pathlib.Path(args.check_client))
        server = sql_tables((DB / "android-tables.sql").read_text(encoding="utf-8"))
        # Local-only bookkeeping the client never uploads. aware_settings is
        # excluded deliberately and permanently: it holds the participant's
        # database password.
        local_only = {"aware_settings", "aware_plugins", "aware_sync_markers"}
        for table in sorted(set(client) - set(server) - local_only):
            print(f"MISSING TABLE: client writes `{table}`, schema lacks it", file=sys.stderr)
            failed = True
        # `_id` is the server's own identity column, which some providers declare
        # and others leave to the database.
        server_owned = {"_id"}
        for table in sorted(set(client) & set(server)):
            gap = [c for c in client[table] if c not in server[table]]
            if gap:
                print(f"MISSING COLUMNS: `{table}` lacks {gap}", file=sys.stderr)
                failed = True
            # A column the client stopped declaring stays behind holding a default
            # per row, on tables that carry the most rows in the deployment. The
            # check runs both ways so a column's removal travels as far as its
            # addition does.
            stale = [
                c for c in server[table]
                if c not in client[table] and c not in server_owned
            ]
            if stale:
                print(
                    f"STALE COLUMNS: `{table}` declares {stale}, the client does not",
                    file=sys.stderr,
                )
                failed = True
        if not failed:
            print("Android schema matches the client's declared tables and columns.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
