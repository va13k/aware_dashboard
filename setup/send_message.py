#!/usr/bin/env python3
"""Reach a participant's phone: ask it to sync, ask it a question, tell it something.

The three things a researcher could not do until now. Each is one publish to a topic
the AWARE client already subscribes to on connect, so nothing here asks anything of
the phone that the phone was not already built to do.

    python3 setup/send_message.py devices
    python3 setup/send_message.py sync --device <id>
    python3 setup/send_message.py update --device all
    python3 setup/send_message.py ask --device <id> --title "How are you?" \\
        --instructions "One touch answer" --answers Good,Fine,Bad
    python3 setup/send_message.py notice --device <id> --title "Thank you" \\
        --instructions "The study finishes on Friday."
    python3 setup/send_message.py history --device <id>

``--device all`` addresses every device the study log recorded joining.

**What arrived is read from the phone, not from the broker.** The client writes every
message it receives into its own ``mqtt_messages`` table, which uploads with the rest
of its data --- so ``history`` shows what was delivered on the phone's own account,
and what was answered from ``esms``. A message published and not yet in ``history``
is one the phone has not reported receiving, which on a quiet phone means it has not
synced since. That is why ``sync`` exists.
"""

import argparse
import json
import pathlib
import os
import subprocess
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = SCRIPT_DIR.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from shared_config import database, messaging, mysql_client
from shared_config.runtime import load_env
from shared_config.source_store import read_source

ENV_PATH = PROJECT / ".env"
BROKER_CONTAINER = "aware_mqtt"

#: A message the researcher composed rather than one the study config scheduled. The
#: client stores it against the ESM row, so it is what separates an answer to this
#: from an answer to the study's own schedule.
TRIGGER = "dashboard"

#: One touch, so a notice costs a participant a tap rather than an essay.
QUICK_ANSWER = 5
FREE_TEXT = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--docker-prefix", action="append", default=[])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="Every device this study recorded joining")

    for name, help_text in (
        ("sync", "Ask a phone to upload what it is holding"),
        ("update", "Ask a phone to re-read the study configuration"),
        ("ask", "Put a question on a phone now"),
        ("notice", "Tell a participant something, with one button to dismiss it"),
        ("history", "What was sent, what arrived, and what came back"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--device", required=True, help="A device id, or 'all'")
        if name in ("ask", "notice"):
            p.add_argument("--title", required=True)
            p.add_argument("--instructions", default="")
            p.add_argument(
                "--answers",
                default="",
                help="Comma-separated quick answers. Omit for a free-text question.",
            )
            p.add_argument("--expires", type=int, default=3600, help="Seconds before it lapses")
    return parser.parse_args()


def client(docker_prefix: list[str]) -> mysql_client.Client:
    return mysql_client.Client.for_study(docker_prefix + ["docker"], read_source())


def enrolled_devices(sql: mysql_client.Client, root_password: str, schema: str) -> list[str]:
    """Every device the study log recorded joining, newest window first."""
    rows = sql.run(
        "root",
        root_password,
        "SELECT device_id FROM device_enrolment GROUP BY device_id "
        "ORDER BY MAX(joined_at) DESC;",
        schema,
        batch=True,
    )
    if rows.returncode != 0:
        raise SystemExit(mysql_client.error_of(rows) or "could not read the enrolment registry")
    return [line.strip() for line in rows.stdout.splitlines() if line.strip()]


def esm_payload(args: argparse.Namespace) -> str:
    """One ESM, in the shape the client's own queue parses.

    The array-of-``{"esm": …}`` wrapper and every key inside it are the client's, read
    from its documented examples rather than invented, so what is published is a
    question the phone already knows how to display.
    """
    answers = [a.strip() for a in (args.answers or "").split(",") if a.strip()]
    esm: dict = {
        "esm_type": QUICK_ANSWER if answers else FREE_TEXT,
        "esm_title": args.title,
        "esm_instructions": args.instructions,
        "esm_expiration_threshold": args.expires,
        "esm_trigger": TRIGGER,
    }
    if answers:
        esm["esm_quick_answers"] = answers
    else:
        esm["esm_submit"] = "Send"
    return json.dumps([{"esm": esm}])


def publish(docker_prefix: list[str], env: dict, topic: str, message: str) -> bool:
    """One message onto the broker, as the account that never leaves the server.

    Published from inside the deployment on the plaintext listener, because that is
    where the API sits: the port participants use is a different question and is
    settled by the study's protocol.
    """
    command = docker_prefix + [
        "docker",
        "exec",
        BROKER_CONTAINER,
        "mosquitto_pub",
        "-h",
        "127.0.0.1",
        "-p",
        str(messaging.PLAIN_PORT),
        "-u",
        env.get("MQTT_PUBLISHER_USER", messaging.PUBLISHER_USER),
        "-P",
        env.get("MQTT_PUBLISHER_PASSWORD", ""),
        "-t",
        topic,
        "-m",
        message,
        "-q",
        "1",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"  could not publish to {topic}: {result.stderr.strip()}")
        return False
    return True


def sent_recently(sql, root_password: str, schema: str, device: str, kind: str) -> int:
    """How many of this kind have gone to this device inside the limit's window."""
    since = int(time.time() * 1000) - messaging.LIMIT_WINDOW_SECONDS * 1000
    rows = sql.run(
        "root",
        root_password,
        f"SELECT COUNT(*) FROM {mysql_client.quote_identifier(messaging.SENT_TABLE)} "
        f"WHERE device_id = {mysql_client.quote_sql_string(device)} "
        f"AND kind = {mysql_client.quote_sql_string(kind)} AND sent_at >= {since};",
        schema,
        batch=True,
    )
    return int(rows.stdout.strip() or 0) if rows.returncode == 0 else 0


def record_sent(
    sql, root_password: str, schema: str, device: str, channel: str, kind: str,
    title: str, body: str,
) -> None:
    """What was asked of this phone, kept so the asking is answerable.

    Written after the publish rather than before, so the record is of what left
    rather than of what was intended. A prompt that failed to publish leaves nothing,
    which is what keeps the rate limit counting real messages.
    """
    result = sql.run(
        "root",
        root_password,
        f"INSERT INTO {mysql_client.quote_identifier(messaging.SENT_TABLE)} "
        "(device_id, channel, kind, title, body, sent_at, sent_by) VALUES ("
        f"{mysql_client.quote_sql_string(device)}, "
        f"{mysql_client.quote_sql_string(channel)}, "
        f"{mysql_client.quote_sql_string(kind)}, "
        f"{mysql_client.quote_sql_string(title)}, "
        f"{mysql_client.quote_sql_string(body)}, "
        f"{int(time.time() * 1000)}, "
        f"{mysql_client.quote_sql_string(os.environ.get('USER', 'setup'))});",
        schema,
    )
    if result.returncode != 0:
        print(f"  warning: the send was not recorded: {mysql_client.error_of(result)}")


def show_history(sql: mysql_client.Client, root_password: str, schema: str, device: str) -> None:
    """What the phone says it received, and what it sent back.

    Both are the phone's own rows rather than the broker's opinion, so a message
    listed here reached a participant's device and one that is absent did not --- or
    has not been uploaded yet, which is the same silence and a different cause.
    """
    scope = "" if device == "all" else f" WHERE device_id = '{device}'"
    received = sql.run(
        "root",
        root_password,
        "SELECT FROM_UNIXTIME(timestamp/1000), device_id, topic, LEFT(message, 60) "
        f"FROM mqtt_messages{scope} ORDER BY timestamp DESC LIMIT 15;",
        schema,
        batch=True,
    )
    answered_where = "WHERE esm_status = 2" + (
        "" if device == "all" else f" AND device_id = '{device}'"
    )
    answered = sql.run(
        "root",
        root_password,
        "SELECT FROM_UNIXTIME(double_esm_user_answer_timestamp/1000), device_id, "
        f"LEFT(esm_title, 30), LEFT(esm_user_answer, 40) FROM esms {answered_where} "
        "ORDER BY double_esm_user_answer_timestamp DESC LIMIT 15;",
        schema,
        batch=True,
    )

    asked = sql.run(
        "root",
        root_password,
        "SELECT FROM_UNIXTIME(sent_at/1000), device_id, kind, LEFT(title, 40) FROM "
        f"{mysql_client.quote_identifier(messaging.SENT_TABLE)}"
        + ("" if device == "all" else f" WHERE device_id = '{device}'")
        + " ORDER BY sent_at DESC LIMIT 15;",
        schema,
        batch=True,
    )
    print("\n  Sent — what was asked of the phone")
    print("  " + "─" * 60)
    lines = [l for l in asked.stdout.splitlines() if l.strip()] if asked.returncode == 0 else []
    for line in lines or ["  (nothing sent yet)"]:
        print("  " + line)

    print("\n  Delivered — what the phone recorded receiving")
    print("  " + "─" * 60)
    lines = [l for l in received.stdout.splitlines() if l.strip()] if received.returncode == 0 else []
    for line in lines or ["  (nothing yet — the phone reports these on its next sync)"]:
        print("  " + line)

    print("\n  Answered — what came back")
    print("  " + "─" * 60)
    lines = [l for l in answered.stdout.splitlines() if l.strip()] if answered.returncode == 0 else []
    for line in lines or ["  (nothing yet)"]:
        print("  " + line)
    print("")


def main() -> int:
    args = parse_args()
    env = load_env(ENV_PATH)
    source = read_source()
    schema = database.platform_schema(source.get("database") or {}, "android")
    root_password = database.admin_password(env)
    sql = client(args.docker_prefix)

    if args.command == "devices":
        print("")
        for device in enrolled_devices(sql, root_password, schema):
            print(f"  {device}")
        print("")
        return 0

    targets = (
        enrolled_devices(sql, root_password, schema)
        if args.device == "all"
        else [args.device]
    )

    if args.command == "history":
        show_history(sql, root_password, schema, args.device)
        return 0

    if args.command in ("sync", "update"):
        channel = messaging.SYNC
        message = messaging.action_for(
            messaging.SYNC_REQUEST if args.command == "sync" else messaging.UPDATE_REQUEST
        )
        described = (
            "a sync request" if args.command == "sync" else "a configuration update request"
        )
    else:
        channel, message = messaging.ESM, esm_payload(args)
        described = f"{'a notice' if args.command == 'notice' else 'a question'}: {args.title!r}"

    kind = {
        "sync": messaging.SYNC_REQUEST,
        "update": messaging.UPDATE_REQUEST,
        "notice": messaging.NOTICE,
    }.get(args.command, messaging.QUESTION)
    title = getattr(args, "title", "")

    print(f"\n  Sending {described} to {len(targets)} device(s)\n")
    sent = 0
    for device in targets:
        # Asked before publishing, so a device at its limit is not sent the message
        # and then told about it.
        refusal = messaging.over_limit(
            kind, sent_recently(sql, root_password, schema, device, kind)
        )
        if refusal:
            print(f"  held  {device}: {refusal}")
            continue
        topic = messaging.topic(device, channel)
        if publish(args.docker_prefix, env, topic, message):
            record_sent(sql, root_password, schema, device, channel, kind, title, message)
            print(f"  sent  {topic}")
            sent += 1
    print(f"\n  {sent} of {len(targets)} published.")
    print("  A phone that is connected acts on it now. One that is not picks it up when")
    print("  it reconnects. Read what arrived with:")
    print(f"      python3 setup/send_message.py history --device {args.device}\n")
    return 0 if sent == len(targets) else 1


if __name__ == "__main__":
    sys.exit(main())
