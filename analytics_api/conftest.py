"""Shared test wiring for the analytics API.

Two things have to happen before any test module is imported.

`app` is a top-level package that lives inside `analytics_api/`, so it is not
importable when pytest is invoked from the repository root - the directory has
to go on `sys.path` first.

Importing anything from `app` also pulls in `app.database`, which builds both
async engines at import time from ANDROID_DATABASE_URL and IOS_DATABASE_URL.
Neither is set outside Docker, and `create_async_engine(None)` raises, so the
import fails before a single test runs. Placeholder URLs fix that: engines
connect lazily, so a URL that points nowhere is harmless for tests over pure
functions. `load_dotenv()` does not override variables that already exist, so a
real `.env` still wins when there is one.
"""

import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import pytest

API_ROOT = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = API_ROOT.parent

#: Production runs MySQL 8.0 (see docker-compose.yml). Anything older lacks
#: syntax the schema uses, so the tests decline to run rather than fail in ways
#: that say nothing about the deployed server. A newer server is allowed and
#: reported, because 8.0 is what the result actually speaks for.
MINIMUM_MYSQL = (8, 0)
DEPLOYED_MYSQL = "8.0"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
# The study's own vocabulary lives beside the API rather than inside it, and the
# container bind-mounts it in. Outside the container the repository root is where
# it is, so it goes on the path too.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def researcher_session(request):
    """Every test speaks to the API as a researcher who has logged in.

    One dependency on the application guards every route (app/routers/auth.py), so
    without this each test below would be exercising the 401 rather than the route
    it names. Lifted for a test marked `no_session`, which is how the guard itself
    is covered.
    """
    if "no_session" in request.keywords:
        yield
        return

    from app.main import app

    # Taken from what the application registered rather than imported here.
    # tests/test_auth.py reloads the auth module, which re-executes it into the
    # same namespace but produces new function objects, and an override keyed on a
    # freshly imported one would stop matching the guard the routes actually carry.
    guard = next(
        dependency.dependency
        for dependency in app.router.dependencies
        if dependency.dependency.__name__ == "require_session"
    )

    app.dependency_overrides[guard] = lambda: None
    try:
        yield
    finally:
        app.dependency_overrides.pop(guard, None)

os.environ.setdefault(
    "ANDROID_DATABASE_URL",
    "mysql+aiomysql://test:test@127.0.0.1:3306/aware_android",
)
os.environ.setdefault(
    "IOS_DATABASE_URL",
    "mysql+aiomysql://test:test@127.0.0.1:3306/aware_ios",
)


@pytest.fixture(scope="session")
def project_root() -> pathlib.Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def deployed_study_config_path() -> pathlib.Path:
    """Path to the deployed study config on the host.

    `studies/` is generated at deployment time and is gitignored, so this file
    is absent in a fresh checkout. Tests that need it skip rather than fail.
    """
    return PROJECT_ROOT / "studies" / "studyConfig.json"


@pytest.fixture(scope="session")
def deployed_study_config(deployed_study_config_path: pathlib.Path) -> dict:
    if not deployed_study_config_path.exists():
        pytest.skip("studies/studyConfig.json is only present after deployment")
    return json.loads(deployed_study_config_path.read_text(encoding="utf-8"))


def _mysqld_version(binary: str) -> tuple[int, ...] | None:
    """The (major, minor, patch) a `mysqld` reports, or None if it will not say."""
    try:
        spoken = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=15
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    found = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", spoken)
    return tuple(int(part) for part in found.groups()) if found else None


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


#: Given to the throwaway server's root account. The backup code declines to run
#: without a password, so the test server has one too and the real code path is
#: exercised rather than stepped around.
TEST_ROOT_PASSWORD = "aware-test-root"


class MySQLServer:
    """A MySQL that exists only for the tests, and only while they run."""

    def __init__(self, port: int, socket_path: str, version: tuple[int, ...]):
        self.port = port
        self.socket_path = socket_path
        self.version = version
        self.password = ""

    def url(self, database: str) -> str:
        secret = f":{self.password}" if self.password else ""
        return f"mysql+aiomysql://root{secret}@127.0.0.1:{self.port}/{database}"

    def run(self, sql: str, database: str = "") -> str:
        command = ["mysql", f"--socket={self.socket_path}", "-uroot", "-N", "-B"]
        if database:
            command.append(database)
        done = subprocess.run(
            command,
            input=sql,
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "MYSQL_PWD": self.password},
        )
        if done.returncode != 0:
            raise RuntimeError(done.stderr.strip())
        return done.stdout


@pytest.fixture(scope="session")
def mysql_server(project_root: pathlib.Path):
    """A throwaway MySQL carrying the deployed schema.

    A server of its own rather than a spare database inside an existing one: the
    data directory is a temporary folder and the port is whatever was free, so
    nothing these tests do can reach a real deployment even if a statement is
    catastrophically wrong. It is shut down and deleted when the session ends.

    Absent or too-old MySQL skips rather than fails, so a checkout without one
    still reports green — the same bargain `deployed_study_config` makes.
    """
    binary = shutil.which("mysqld")
    if binary is None:
        pytest.skip(
            "integration tests need a local MySQL server: `mysqld` is not on PATH. "
            "Install MySQL "
            f"{DEPLOYED_MYSQL} (macOS: `brew install mysql`) or start the Docker "
            "stack and run them there. See analytics_api/README.md."
        )

    version = _mysqld_version(binary)
    if version is None:
        pytest.skip(f"could not read a version from `{binary} --version`")
    if version[:2] < MINIMUM_MYSQL:
        pytest.skip(
            f"found MySQL {'.'.join(map(str, version))}, but these tests need "
            f"{'.'.join(map(str, MINIMUM_MYSQL))} or newer — the deployed server is "
            f"{DEPLOYED_MYSQL} and the schema uses syntax older servers reject."
        )

    base = pathlib.Path(binary).resolve().parent.parent
    root = pathlib.Path(tempfile.mkdtemp(prefix="aware-test-mysql-"))
    data, sock = root / "data", root / "mysql.sock"
    port = _free_port()

    subprocess.run(
        [binary, "--initialize-insecure", f"--datadir={data}", f"--basedir={base}"],
        capture_output=True,
        timeout=300,
        check=True,
    )
    process = subprocess.Popen(
        [
            binary,
            f"--datadir={data}",
            f"--basedir={base}",
            f"--port={port}",
            f"--socket={sock}",
            f"--pid-file={root / 'mysqld.pid'}",
            "--mysqlx=OFF",
            # Deployment runs MySQL 8.0, where GTIDs are off by default. Later
            # servers turn them on, and mysqldump then writes a GTID_PURGED
            # statement that no dump from the real server carries — and that a
            # restore onto the same instance rejects outright. Off here keeps the
            # dumps these tests read the same shape as the deployed ones.
            "--gtid-mode=OFF",
            "--enforce-gtid-consistency=OFF",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    server = MySQLServer(port, str(sock), version)
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    process.stderr.read().decode("utf-8", errors="replace")[-2000:]
                )
            try:
                server.run("SELECT 1")
                break
            except RuntimeError:
                time.sleep(0.5)
        else:
            raise RuntimeError("the test MySQL did not accept connections in time")

        server.run(
            f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{TEST_ROOT_PASSWORD}'"
        )
        server.password = TEST_ROOT_PASSWORD

        schema = (project_root / "db" / "init_all.sql").read_text(encoding="utf-8")
        server.run(schema)
        yield server
    finally:
        subprocess.run(
            ["mysqladmin", f"--socket={sock}", "-uroot", "shutdown"],
            capture_output=True,
            timeout=60,
            env={**os.environ, "MYSQL_PWD": server.password},
        )
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def clean_databases(mysql_server: MySQLServer):
    """Empties the study tables so each test starts from a known state."""
    for database in ("aware_android", "aware_ios"):
        tables = mysql_server.run(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            f"WHERE TABLE_SCHEMA = '{database}' AND TABLE_TYPE = 'BASE TABLE'"
        ).split()
        if tables:
            statements = "".join(f"TRUNCATE TABLE `{name}`;" for name in tables)
            mysql_server.run(f"SET FOREIGN_KEY_CHECKS=0;{statements}", database)
    return mysql_server
