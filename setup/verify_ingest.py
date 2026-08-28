#!/usr/bin/env python3
"""Ask the deployment the question a participant's phone will ask, before anyone enrols.

A study can be deployed, healthy and serving, and still deliver nothing: the phones
reach the ingest endpoint from a participant's network rather than from the compose
network, over the public address and whatever certificate that address presents, and
nothing inside the deployment exercises that path. This walks it end to end and says
what happened, in the order a phone meets it:

``endpoint``
    Reachable at the address the study hands out, answering with the study
    configuration a joining phone reads.

``certificate``
    Presented by that address and verified against the system trust store, with the
    name it was issued to and the day it expires.

``record``
    A row posted the way the client posts one, admitted by the ingest path, found in
    the study database afterwards, and taken back out again.

Both dataflows are covered, because the choice decides what a phone has to reach: the
webservice path is HTTPS to the micro-server, the direct path is MySQL's own port at
the public address, opened with the participant account a phone is given.

The probe device is synthetic and named per run, and everything it touches is keyed on
that name --- its row, its enrolment window, and its entries in the two caches, which
are keyed by device so a probe leaves them exactly as it found them. Cleanup runs
whatever the outcome, and reports itself as part of the result.

Run from the host once the stack is healthy::

    python3 setup/verify_ingest.py --docker-prefix sudo
"""

import argparse
import json
import pathlib
import secrets
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = SCRIPT_DIR.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from shared_config import database, dataflow
from shared_config.runtime import (
    SHARED_MODE,
    atomic_write_text,
    build_public_base_url,
    load_env,
    strip_ipv6_brackets,
)
from shared_config.source_store import read_source

ENV_PATH = PROJECT / ".env"
MYSQL_CONTAINER = "aware_mysql"

#: Read by the setup wizard's status endpoint, so the browser shows the same result
#: the terminal does. Written last, whole, so a reader sees a finished run or none.
RESULT_PATH = SCRIPT_DIR / ".ingest-check.json"

#: The table the probe writes. A phone fills this in as soon as it has joined, the
#: micro-server keeps one row per device here, and a row is addressed by its device,
#: so a probe row is removed by naming the device that wrote it.
PROBE_TABLE = "aware_device"

#: How the probe's enrolment window records itself. The gate admits a device whose
#: window came from the study log or from a researcher, and setup entering one on the
#: researcher's behalf is the second of those, so the probe is admitted for the same
#: reason a real device is rather than for a reason invented for it.
PROBE_JOIN_SOURCE = "manual"

#: What a probe reaches besides the table it writes, all of it keyed by device, which
#: is what lets a probe be taken back out exactly. The two caches hold the figures the
#: dashboard reads; `refusals` holds the record a turned-away probe leaves, which is
#: shown beside the client logs and belongs to the probe rather than to the study.
DERIVED_TABLES = ("record_counts", "coverage_hourly", "refusals")

HTTP_TIMEOUT_SECONDS = 15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--docker-prefix",
        action="append",
        default=[],
        help="Optional command prefix before docker, for example: --docker-prefix sudo",
    )
    parser.add_argument(
        "--json-out",
        default=str(RESULT_PATH),
        help="Where to write the machine-readable result",
    )
    parser.add_argument("--timeout-seconds", type=int, default=60)
    return parser.parse_args()


def run_command(command: list[str], input_text: str | None = None):
    return subprocess.run(
        command, input=input_text, capture_output=True, text=True, check=False
    )


def quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def quote_sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


class Mysql:
    """Statements run against the study database as root, through the container.

    Root because the probe verifies and then removes what it wrote, and the accounts
    on the ingest path are granted to write rather than to read back or to clean up.
    Which account performs the *write* is the thing under test, and that is chosen by
    the path the row travels, not here.
    """

    def __init__(self, docker_base: list[str], root_password: str, schema: str):
        self._base = docker_base
        self._root_password = root_password
        self._schema = schema

    def _command(self, extra: list[str]) -> list[str]:
        return self._base + [
            "exec",
            "-i",
            MYSQL_CONTAINER,
            "mysql",
            "--protocol=TCP",
            "-h127.0.0.1",
            "-uroot",
            f"-p{self._root_password}",
            *extra,
        ]

    def execute(self, sql: str) -> subprocess.CompletedProcess:
        return run_command(self._command([self._schema]), input_text=sql)

    def scalar(self, sql: str) -> str:
        """One value from a single-row query, or "" when the query returns nothing."""
        result = run_command(
            self._command(["-B", "-N", self._schema]), input_text=sql
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "query failed")
        return result.stdout.strip()


def _mysql_as(
    docker_base: list[str],
    host: str,
    port: int,
    username: str,
    password: str,
    schema: str,
    ssl_mode: str | None,
    sql: str,
) -> subprocess.CompletedProcess:
    extra = ["--protocol=TCP", f"-h{host}", f"-P{port}", f"-u{username}", f"-p{password}"]
    if ssl_mode:
        extra.append(f"--ssl-mode={ssl_mode}")
    command = docker_base + ["exec", "-i", MYSQL_CONTAINER, "mysql", *extra, schema]
    return run_command(command, input_text=sql)


def check(name: str, ok: bool, detail: str, skipped: bool = False) -> dict:
    return {"name": name, "ok": bool(ok), "skipped": bool(skipped), "detail": detail}


def probe_device_id() -> str:
    """A name no participant can hold and no run repeats.

    Random per run so a row left behind by a killed run is still addressable, and
    never confusable with a device a study is collecting from.
    """
    return f"setup-self-test-{secrets.token_hex(8)}"


def fetch_study_config(url: str) -> tuple[bool, str]:
    """The configuration a joining phone reads, fetched the way the phone fetches it."""
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "aware-setup-self-test"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status = response.status
            body = response.read(2_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return False, f"{url} answered {error.code} {error.reason}."
    except urllib.error.URLError as error:
        return False, f"{url} could not be reached: {error.reason}."
    except (TimeoutError, socket.timeout):
        return False, f"{url} did not answer within {HTTP_TIMEOUT_SECONDS} seconds."
    except OSError as error:
        return False, f"{url} could not be reached: {error}."

    if status != 200:
        return False, f"{url} answered {status}."
    try:
        config = json.loads(body)
    except json.JSONDecodeError:
        return False, (
            f"{url} answered 200 but not with a study configuration. "
            "A joining phone reads this as JSON and refuses what it cannot parse."
        )
    if not isinstance(config, dict) or not (config.get("sensors") or config.get("study")):
        return False, f"{url} answered with JSON carrying no study or sensor block."

    sensors = config.get("sensors")
    described = f"{len(sensors)} settings" if isinstance(sensors, list) else "a study block"
    return True, f"{url} served the study configuration ({described})."


def inspect_certificate(host: str, port: int) -> tuple[bool, str]:
    """The certificate the public address presents, verified against the system store.

    Verified rather than merely read, because a phone verifies: a certificate that
    fails here is one every client refuses, and it fails on the day of setup instead
    of in the coverage grid a month later.
    """
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=HTTP_TIMEOUT_SECONDS) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                certificate = tls.getpeercert()
                protocol = tls.version()
    except ssl.SSLCertVerificationError as error:
        return False, (
            f"The certificate {host}:{port} presents did not verify: {error.verify_message or error}. "
            "A phone refuses this connection for the same reason."
        )
    except (OSError, ssl.SSLError) as error:
        return False, f"No TLS session could be opened to {host}:{port}: {error}."

    subject = ""
    for part in certificate.get("subject", ()):
        for key, value in part:
            if key == "commonName":
                subject = value
    names = [value for key, value in certificate.get("subjectAltName", ()) if key == "DNS"]
    expires = certificate.get("notAfter", "")
    remaining = ""
    try:
        expiry = datetime.strptime(expires, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        remaining = f", {(expiry - datetime.now(timezone.utc)).days} days from now"
    except ValueError:
        pass

    issued_to = subject or (names[0] if names else host)
    return True, f"{protocol} to {issued_to}, valid until {expires}{remaining}."


def post_probe_row(insert_url: str, device_id: str, timestamp_ms: int) -> tuple[bool, str]:
    """A row posted as the client posts one, and the ingest path's own answer to it.

    The form encoding and the two field names are the client's, so the request under
    test is the request a phone makes. The status carries what became of the batch:
    the row is stored, the rule turned it away, or the database could not take it.
    """
    payload = [
        {
            "timestamp": timestamp_ms,
            "device_id": device_id,
            "label": "setup self-test",
            "manufacturer": "AWARE",
            "model": "setup-self-test",
        }
    ]
    body = urllib.parse.urlencode(
        {"device_id": device_id, "data": json.dumps(payload)}
    ).encode()
    request = urllib.request.Request(
        insert_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "aware-setup-self-test",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status = response.status
            response.read(4096)
    except urllib.error.HTTPError as error:
        reason = error.read(4096).decode("utf-8", "replace").strip()
        if error.code == 403:
            return False, (
                "The ingest path refused the row: the enrolment gate found no window "
                "for the probe device. The path is reachable and reads the registry."
            )
        if error.code == 503:
            return False, (
                "The ingest path accepted the request and the study database could not "
                f"take the row. {reason}"
            )
        return False, f"{insert_url} answered {error.code} {error.reason}. {reason}".strip()
    except urllib.error.URLError as error:
        return False, f"{insert_url} could not be reached: {error.reason}."
    except OSError as error:
        return False, f"{insert_url} could not be reached: {error}."

    if status != 200:
        return False, f"{insert_url} answered {status}."
    return True, "The ingest path reported the row stored."


def open_probe_window(sql: Mysql, device_id: str, joined_at_ms: int) -> None:
    """An enrolment window for the probe, so the gate admits its row.

    The gate asks whether the study log ever recorded this device joining, and a probe
    has no phone to join with, so the window is entered on its behalf and removed with
    everything else the probe leaves.
    """
    result = sql.execute(
        "INSERT INTO `device_enrolment` (`device_id`, `joined_at`, `join_source`) "
        f"VALUES ({quote_sql_string(device_id)}, {int(joined_at_ms)}, "
        f"{quote_sql_string(PROBE_JOIN_SOURCE)}) "
        "ON DUPLICATE KEY UPDATE `join_source` = VALUES(`join_source`);"
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "could not record the probe's enrolment window")


def clear_probe(sql: Mysql, device_id: str) -> tuple[bool, str]:
    """Everything the probe put in the database, taken back out and checked for.

    The caches are keyed by device, so removing the probe's entries restores the
    figures on screen to what they were and lets the next refresh recount from a
    watermark that no longer stands on a row that has gone.
    """
    quoted = quote_sql_string(device_id)
    statements = [
        f"DELETE FROM {quote_identifier(PROBE_TABLE)} WHERE `device_id` = {quoted};",
        f"DELETE FROM `device_enrolment` WHERE `device_id` = {quoted};",
    ]
    statements += [
        f"DELETE FROM {quote_identifier(table)} WHERE `device_id` = {quoted};"
        for table in DERIVED_TABLES
    ]
    result = sql.execute("\n".join(statements))
    if result.returncode != 0:
        return False, (
            "The probe's rows could not be removed: "
            + (result.stderr.strip() or "the delete failed")
            + f" Remove them by hand with device_id = {device_id!r}."
        )

    counted = " + ".join(
        f"(SELECT COUNT(*) FROM {quote_identifier(table)} WHERE `device_id` = {quoted})"
        for table in (PROBE_TABLE, "device_enrolment", *DERIVED_TABLES)
    )
    try:
        remaining = sql.scalar(f"SELECT {counted};")
    except RuntimeError as error:
        return False, f"The probe's rows were deleted and could not be checked for: {error}"

    if remaining not in {"0", ""}:
        return False, (
            f"{remaining} probe rows are still in the database. "
            f"Remove them by hand with device_id = {device_id!r}."
        )
    return True, "The probe left nothing behind."


def verify_webservice(
    sql: Mysql, base_url: str, study_key: str, host: str, port: int, protocol: str
) -> list[dict]:
    """The path a phone takes when the micro-server performs the write."""
    checks = []
    join_url = f"{base_url}/{dataflow.ANDROID_STUDY_NUMBER}/{study_key}"
    insert_url = f"{join_url}/{PROBE_TABLE}/insert"

    reachable, detail = fetch_study_config(join_url)
    checks.append(check("endpoint", reachable, detail))

    if protocol == "https":
        checks.append(check("certificate", *inspect_certificate(host, port)))
    else:
        checks.append(
            check(
                "certificate",
                True,
                "This study is served over HTTP, so no certificate is presented. "
                "A participant's data travels in clear text and many mobile networks "
                "allow only 443, so HTTPS is what a study off this machine wants.",
                skipped=True,
            )
        )

    if not reachable:
        checks.append(
            check(
                "record",
                False,
                "Not attempted: a row cannot be posted to an endpoint that does not answer.",
            )
        )
        return checks

    device_id = probe_device_id()
    now_ms = int(time.time() * 1000)
    try:
        open_probe_window(sql, device_id, now_ms)
    except RuntimeError as error:
        checks.append(check("record", False, str(error)))
        return checks

    try:
        stored, detail = post_probe_row(insert_url, device_id, now_ms)
        if stored:
            try:
                found = sql.scalar(
                    f"SELECT COUNT(*) FROM {quote_identifier(PROBE_TABLE)} "
                    f"WHERE `device_id` = {quote_sql_string(device_id)};"
                )
            except RuntimeError as error:
                stored, detail = False, f"The row was accepted and could not be read back: {error}"
            else:
                if found == "1":
                    detail = f"A row posted to {insert_url} was found in the study database."
                else:
                    stored = False
                    detail = (
                        "The ingest path reported the row stored and the study database "
                        "does not hold it."
                    )
        checks.append(check("record", stored, detail))
    finally:
        checks.append(check("cleanup", *clear_probe(sql, device_id)))
    return checks


def verify_direct(
    docker_base: list[str],
    sql: Mysql,
    host: str,
    port: int,
    schema: str,
    username: str,
    password: str,
    require_ssl: bool,
) -> list[dict]:
    """The path a phone takes when it opens the database itself."""
    checks = []
    try:
        with socket.create_connection((host, port), timeout=HTTP_TIMEOUT_SECONDS):
            reachable, detail = True, f"{host}:{port} accepted a connection."
    except OSError as error:
        reachable, detail = False, (
            f"{host}:{port} could not be reached: {error}. On this dataflow every "
            "participant's phone opens that port from whatever network it is on."
        )
    checks.append(check("endpoint", reachable, detail))

    ssl_mode = "REQUIRED" if require_ssl else None
    if not require_ssl:
        checks.append(
            check(
                "certificate",
                True,
                "This study declares an unencrypted connection to its database, so "
                "phones open it in clear text. The declaration is `database.tls` in "
                "the study model, and only a database the researcher names may carry "
                "it.",
                skipped=True,
            )
        )

    if not reachable:
        checks.append(check("record", False, "Not attempted: the database port did not answer."))
        return checks

    device_id = probe_device_id()
    now_ms = int(time.time() * 1000)
    insert = (
        f"INSERT INTO {quote_identifier(PROBE_TABLE)} "
        "(`timestamp`, `device_id`, `label`, `manufacturer`, `model`) VALUES "
        f"({now_ms}, {quote_sql_string(device_id)}, 'setup self-test', 'AWARE', 'setup-self-test');"
    )
    try:
        written = _mysql_as(
            docker_base, host, port, username, password, schema, ssl_mode, insert
        )
        if written.returncode != 0:
            checks.append(
                check(
                    "record",
                    False,
                    f"{username} could not write to {host}:{port}: "
                    + (written.stderr.strip() or "the insert failed"),
                )
            )
            if require_ssl:
                checks.append(
                    check(
                        "certificate",
                        False,
                        "The encrypted session the account requires was not established.",
                    )
                )
            return checks

        if require_ssl:
            cipher = _mysql_as(
                docker_base,
                host,
                port,
                username,
                password,
                schema,
                ssl_mode,
                "SHOW STATUS LIKE 'Ssl_cipher';",
            )
            negotiated = cipher.stdout.strip().splitlines()[-1:] or [""]
            checks.append(
                check(
                    "certificate",
                    cipher.returncode == 0,
                    f"The account connected over TLS ({negotiated[0].strip()}).",
                )
            )

        try:
            found = sql.scalar(
                f"SELECT COUNT(*) FROM {quote_identifier(PROBE_TABLE)} "
                f"WHERE `device_id` = {quote_sql_string(device_id)};"
            )
        except RuntimeError as error:
            checks.append(check("record", False, f"The row was written and could not be read back: {error}"))
            return checks

        checks.append(
            check(
                "record",
                found == "1",
                f"A row written by {username} over {host}:{port} was found in the study database."
                if found == "1"
                else "The insert reported success and the study database does not hold the row.",
            )
        )
    finally:
        checks.append(check("cleanup", *clear_probe(sql, device_id)))
    return checks


def wait_for_ingest(docker_base: list[str], container: str, timeout_seconds: int) -> bool:
    """Whether the container that performs the write is up and reporting healthy."""
    deadline = time.time() + timeout_seconds
    inspect = docker_base + [
        "inspect",
        "-f",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
        container,
    ]
    while time.time() < deadline:
        result = run_command(inspect)
        if result.returncode == 0 and result.stdout.strip().lower() in {"healthy", "running"}:
            return True
        time.sleep(2)
    return False


def report(result: dict) -> None:
    labels = {
        "endpoint": "Endpoint reachable",
        "certificate": "Certificate",
        "record": "Test record lands",
        "cleanup": "Probe removed",
    }
    print("")
    print(f"  Ingest self-test ({result['dataflow']} dataflow)")
    print("  " + "─" * 44)
    for entry in result["checks"]:
        mark = "skip" if entry["skipped"] else ("ok" if entry["ok"] else "FAIL")
        print(f"  [{mark:>4}] {labels.get(entry['name'], entry['name'])}")
        print(f"         {entry['detail']}")
    print("")
    if result["ok"]:
        print("  The ingest path works from outside the deployment. Enrolment can begin.")
    else:
        print("  The ingest path is not ready. Phones enrolled now would collect data")
        print("  and never deliver it. Fix the failures above, then rerun:")
        print("      python3 setup/verify_ingest.py")
    print("")


def main() -> int:
    args = parse_args()
    docker_base = args.docker_prefix + ["docker"]

    env = load_env(ENV_PATH)
    source = read_source()
    databases = source.get("database") or {}
    android = dataflow.declared(source, "android")

    protocol = str(env.get("PROTOCOL", "http")).strip().lower() or "http"
    host = strip_ipv6_brackets(str(env.get("PUBLIC_HOST", "localhost")).strip() or "localhost")
    public_port = int(env.get("PUBLIC_PORT", "443" if protocol == "https" else "80"))
    base_url = build_public_base_url(protocol, host, public_port)

    root_password = str(env.get("MYSQL_ROOT_PASSWORD", "")).strip()
    schema = database.platform_schema(databases, "android")
    sql = Mysql(docker_base, root_password, schema)

    result = {
        "dataflow": android,
        "base_url": base_url,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": [],
        "ok": False,
    }

    if not root_password:
        result["checks"] = [
            check("record", False, "MYSQL_ROOT_PASSWORD is missing from .env, so nothing can be verified.")
        ]
    elif android == dataflow.WEBSERVICE:
        container = "aware_micro_android"
        if not wait_for_ingest(docker_base, container, args.timeout_seconds):
            result["checks"] = [
                check("endpoint", False, f"{container} did not become healthy within {args.timeout_seconds} seconds.")
            ]
        else:
            result["checks"] = verify_webservice(
                sql, base_url, str(env.get("STUDY_KEY", "")).strip(), host, public_port, protocol
            )
    else:
        username, password = database.android_credentials(databases, android)
        result["checks"] = verify_direct(
            docker_base,
            sql,
            host,
            database.platform_port(databases, "android"),
            schema,
            username,
            password,
            database.tls_required(databases),
        )

    result["ok"] = all(entry["ok"] for entry in result["checks"])
    atomic_write_text(
        pathlib.Path(args.json_out), json.dumps(result, indent=2) + "\n", SHARED_MODE
    )
    report(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
