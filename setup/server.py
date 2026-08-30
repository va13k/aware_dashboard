#!/usr/bin/env python3
import http.client
import json
import os
import secrets
import socket
import subprocess
import tempfile
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

# Containers that must pass their Docker healthcheck before the stack is ready.
_HEALTH_CHECKED = frozenset({
    "aware_micro", "aware_configurator", "aware_dashboard_api", "aware_dashboard",
})
# Containers without a healthcheck — just need to be running.
_RUNNING_ONLY = frozenset({"aware_nginx"})

# The two a deployment has only because it runs the database itself. A study that
# names its own server has neither, so waiting for them is waiting forever --- the
# browser sits on "Starting services" while the deployment behind it is finished.
# deploy_config.py writes the compose override for that placement and removes it
# again, so its presence is the placement, which is the same thing setup.sh reads.
_BUNDLED_HEALTH_CHECKED = frozenset({"aware_mysql"})
_BUNDLED_RUNNING_ONLY = frozenset({"aware_mysql_backup"})
_COMPOSE_OVERRIDE = "/project/docker-compose.external-db.yml"


def _runs_its_own_database():
    return not os.path.exists(_COMPOSE_OVERRIDE)


def _expected_services():
    """The containers this deployment has, and how each says it is ready."""
    health_checked = set(_HEALTH_CHECKED)
    running_only = set(_RUNNING_ONLY)
    if _runs_its_own_database():
        health_checked |= _BUNDLED_HEALTH_CHECKED
        running_only |= _BUNDLED_RUNNING_ONLY
    return health_checked, running_only

# Written by setup/verify_ingest.py on the host once the stack is healthy. The
# wizard reports it rather than running it: the check has to reach the deployment
# at its public address and read the study database, and this container is on
# neither path.
_INGEST_RESULT = "/project/setup/.ingest-check.json"


def _ingest_result():
    """This run's ingest self-test, or None while it has not finished.

    A half-written file reads as not finished, which is the same answer as no file
    and leaves the page waiting rather than showing a partial result.
    """
    try:
        with open(_INGEST_RESULT, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


class _UnixHTTP(http.client.HTTPConnection):
    """HTTPConnection that talks over a Unix domain socket."""
    def __init__(self, sock_path):
        super().__init__("localhost")
        self._sock_path = sock_path

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self._sock_path)
        self.sock = s


def _docker_containers():
    try:
        conn = _UnixHTTP("/var/run/docker.sock")
        conn.request("GET", "/containers/json?all=1")
        r = conn.getresponse()
        return json.loads(r.read()), True
    except Exception:
        return [], False


def _service_statuses():
    containers, socket_ok = _docker_containers()
    if not socket_ok:
        return None  # socket unavailable
    health_checked, running_only = _expected_services()
    required = health_checked | running_only
    statuses = {name: False for name in required}
    for c in containers:
        name = (c.get("Names") or [""])[0].lstrip("/")
        if name in required:
            status_str = c.get("Status", "")
            if name in health_checked:
                statuses[name] = "(healthy)" in status_str
            else:
                statuses[name] = status_str.startswith("Up")
    return statuses

TOKEN = secrets.token_urlsafe(32)
WIZARD_DIR = os.path.dirname(os.path.abspath(__file__))
#: The scripts run on the wizard's behalf live beside it in the image, and
#: beside this file in a checkout.
SETUP_DIR = WIZARD_DIR
PREFIX = f"/{TOKEN}"
URL_FILE = "/project/setup/.wizard_url"

# Write token path to bind-mounted project dir; setup.sh builds the full URL
try:
    with open(URL_FILE, "w") as f:
        f.write(PREFIX + "/\n")
except Exception:
    pass  # non-fatal if project dir isn't mounted

print("", flush=True)
print("=" * 64, flush=True)
print("  AWARE Dashboard — Setup Wizard", flush=True)
print("", flush=True)
print(f"  Token path: {PREFIX}/", flush=True)
print("  (setup.sh will print the full URL)", flush=True)
print("=" * 64, flush=True)
print("", flush=True)
sys.stdout.flush()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def _forbidden(self):
        self.send_response(403)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Forbidden: invalid or missing setup token")

    def _check_token(self):
        if not self.path.startswith(PREFIX):
            self._forbidden()
            return False
        return True

    def _inner_path(self):
        path = self.path[len(PREFIX):]
        return path.split("?")[0] or "/"

    def do_GET(self):
        if not self._check_token():
            return
        p = self._inner_path()
        if p in ("/", ""):
            self._serve_file("index.html", "text/html; charset=utf-8")
        elif p == "/script.js":
            self._serve_file("script.js", "application/javascript; charset=utf-8")
        elif p == "/style.css":
            self._serve_file("style.css", "text/css; charset=utf-8")
        elif p == "/cgi-bin/deploy":
            self._run_cgi("GET", b"")
        elif p == "/status":
            self._serve_status()
        elif p == "/database.sql":
            self._serve_setup_sql()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self._check_token():
            return
        p = self._inner_path()
        if p == "/cgi-bin/deploy":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            self._run_cgi("POST", body)
        elif p == "/check-database":
            length = int(self.headers.get("Content-Length", 0))
            self._check_database(self.rfile.read(length))
        else:
            self.send_response(404)
            self.end_headers()

    def _check_database(self, body):
        """Ask the database the deploy's own questions, before deploying.

        The same script the deployment runs, so what passes here passes there —
        and a database that cannot be reached is a field to correct rather than a
        deployment that stops half way through.
        """
        try:
            asked = json.loads(body or b"{}")
        except ValueError:
            asked = {}

        command = [sys.executable, os.path.join(SETUP_DIR, "verify_database.py"), "--quiet"]
        for flag, key in (
            ("--host", "host"),
            ("--port", "port"),
            ("--admin-user", "admin_user"),
            ("--admin-password", "admin_password"),
            ("--placement", "placement"),
        ):
            value = str(asked.get(key) or "").strip()
            if value:
                command += [flag, value]
        # A study whose schema is created by hand is asked about, not acted on:
        # the test must not leave behind what the deployment would have made.
        if str(asked.get("init") or "").strip().lower() == "manual":
            command.append("--verify-only")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out:
            result_path = out.name
        command += ["--json-out", result_path]

        run = subprocess.run(command, capture_output=True, text=True)
        try:
            with open(result_path, encoding="utf-8") as handle:
                report = json.load(handle)
        except (OSError, ValueError):
            report = {
                "ok": False,
                "checks": [
                    {
                        "name": "reachable",
                        "ok": False,
                        "skipped": False,
                        "detail": (run.stderr or run.stdout or "").strip()
                        or "The check did not run.",
                    }
                ],
            }
        finally:
            try:
                os.unlink(result_path)
            except OSError:
                pass

        self._send_json(report)

    def _serve_setup_sql(self):
        """The statements an administrator would run, as a file to hand over."""
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as out:
            sql_path = out.name
        subprocess.run(
            [
                sys.executable,
                os.path.join(SETUP_DIR, "verify_database.py"),
                "--sql-out",
                sql_path,
                "--quiet",
            ],
            capture_output=True,
        )
        try:
            with open(sql_path, "rb") as handle:
                data = handle.read()
        except OSError:
            data = b"-- The setup script could not be built.\n"
        finally:
            try:
                os.unlink(sql_path)
            except OSError:
                pass

        self.send_response(200)
        self.send_header("Content-Type", "application/sql; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="aware-setup.sql"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_status(self):
        statuses = _service_statuses()
        if statuses is None:
            payload = {"ready": False, "services": {}, "socket_unavailable": True}
        else:
            # Every expected service is in the mapping whether or not its container
            # exists, so one that has not been created yet reads as not ready rather
            # than as nothing to wait for.
            ready = bool(statuses) and all(statuses.values())
            payload = {"ready": ready, "services": {k: bool(v) for k, v in statuses.items()}}
        payload["ingest"] = _ingest_result()
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filename, content_type):
        filepath = os.path.join(WIZARD_DIR, filename)
        try:
            with open(filepath, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _run_cgi(self, method, body):
        env = os.environ.copy()
        env["REQUEST_METHOD"] = method
        env["CONTENT_LENGTH"] = str(len(body))
        env["CONTENT_TYPE"] = self.headers.get("Content-Type", "")

        result = subprocess.run(
            ["/wizard/cgi-bin/deploy"],
            input=body,
            capture_output=True,
            env=env,
        )

        output = result.stdout
        sep = b"\r\n\r\n" if b"\r\n\r\n" in output else b"\n\n"
        if sep in output:
            header_bytes, body_bytes = output.split(sep, 1)
        else:
            header_bytes, body_bytes = b"Content-Type: application/json", output

        self.send_response(200)
        for line in header_bytes.replace(b"\r\n", b"\n").split(b"\n"):
            if b":" in line:
                name, _, value = line.partition(b":")
                self.send_header(name.decode().strip(), value.decode().strip())
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)


if __name__ == "__main__":
    httpd = HTTPServer(("0.0.0.0", 9999), Handler)
    httpd.serve_forever()
