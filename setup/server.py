#!/usr/bin/env python3
import http.client
import json
import os
import secrets
import socket
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

# Containers that must pass their Docker healthcheck before the stack is ready.
_HEALTH_CHECKED = frozenset({
    "aware_mysql", "aware_micro", "aware_configurator",
    "aware_dashboard_api", "aware_dashboard",
})
# Containers without a healthcheck — just need to be running.
_RUNNING_ONLY = frozenset({"aware_nginx"})
_REQUIRED = _HEALTH_CHECKED | _RUNNING_ONLY


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
    statuses = {}
    for c in containers:
        name = (c.get("Names") or [""])[0].lstrip("/")
        if name in _REQUIRED:
            status_str = c.get("Status", "")
            if name in _HEALTH_CHECKED:
                statuses[name] = "(healthy)" in status_str
            else:
                statuses[name] = status_str.startswith("Up")
    return statuses

TOKEN = secrets.token_urlsafe(32)
WIZARD_DIR = os.path.dirname(os.path.abspath(__file__))
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
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_status(self):
        statuses = _service_statuses()
        if statuses is None:
            payload = {"ready": False, "services": {}, "socket_unavailable": True}
        else:
            ready = (
                all(n in statuses for n in _REQUIRED)
                and all(statuses.values())
            )
            payload = {"ready": ready, "services": {k: bool(v) for k, v in statuses.items()}}
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
