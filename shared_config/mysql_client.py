"""How setup reaches the study database, whichever placement the study runs.

Setup has to issue SQL before anything else works --- creating the Android schema,
settling the account passwords, and asking whether a row can be written at all ---
and where that SQL is issued from is not the same on both placements. A bundled
database has a container of this deployment's own with a client already inside it. A
database the researcher names has neither, so the client comes from a throwaway
container attached to the deployment's network.

The network matters more than the convenience. A host that resolves on the machine
running setup and not inside a container is a study that passes every check and then
collects nothing, so the question is asked from where the micro-server and the API
will ask it. Where the deployment has no network yet --- a first run, before anything
is up --- the client falls back to this machine's own resolution, and
:meth:`Client.on_network` says which of the two answered.
"""

import base64
import shlex
import subprocess

from shared_config import database, placement

#: The bundled database's container, which carries a client of its own.
BUNDLED_CONTAINER = "aware_mysql"

#: The image the compose file already runs, so a throwaway client is one that has
#: been pulled rather than one a deployment has to fetch to finish setting up.
CLIENT_IMAGE = "mysql:8.0"

#: The network this deployment's services reach the database on.
COMPOSE_NETWORK = "aware_dashboard_aware_network"

#: Long enough to cross a network to an institutional host, short enough that an
#: unreachable one is reported rather than waited on.
CONNECT_TIMEOUT_SECONDS = 10

#: Where an authority is planted for the client that has to check a certificate
#: against it. Inside the container that runs the query and gone with it, because
#: the study already holds the certificate and a copy on a disk somewhere is one
#: more thing that can go stale.
CA_PATH = "/tmp/aware-db-ca.pem"


class Client:
    """A MySQL client addressed at this study's database.

    ``host`` is the address as the deployment's own services resolve it: the compose
    name for a bundled database, and the declared host for one the researcher names.
    """

    def __init__(
        self,
        docker_base: list[str],
        host: str,
        port: int = 3306,
        network: str = COMPOSE_NETWORK,
        ssl_mode: str = "",
        ca_pem: str = "",
    ):
        self._base = docker_base
        self._host = host
        self._port = int(port)
        self._network = network
        self._bundled = database.is_internal(host)
        self._ssl_mode = str(ssl_mode or "").strip()
        self._ca_pem = str(ca_pem or "").strip()

    @classmethod
    def for_study(cls, docker_base: list[str], source: dict, platform: str = "android"):
        """The client this study's declared database is reached with.

        Left on the client's own default rather than asking for a mode, because this
        is the administrative connection: it creates the accounts that decide what
        every other connection may ask for, and a study being repaired is one whose
        declaration and whose server may not agree yet. ``PREFERRED`` encrypts
        wherever the server offers it and still reaches one that cannot.
        """
        databases = source.get("database") or {}
        return cls(
            docker_base,
            database.service_host(databases),
            database.platform_port(databases, platform),
        )

    def asking_for(self, ssl_mode: str, ca_pem: str = ""):
        """The same address, opened with a TLS mode this connection must get.

        A separate client rather than a setting on this one: the checks ask the same
        database several questions with different demands, and one that quietly
        changed what an earlier answer meant would be worse than no check at all.
        """
        return Client(
            self._base,
            self._host,
            self._port,
            self._network,
            ssl_mode=ssl_mode,
            ca_pem=ca_pem,
        )

    @property
    def bundled(self) -> bool:
        """Whether this addresses the database this deployment runs itself."""
        return self._bundled

    def _network_available(self) -> bool:
        probe = self._base + ["network", "inspect", self._network]
        return subprocess.run(probe, capture_output=True, text=True, check=False).returncode == 0

    def on_network(self) -> bool:
        """Whether a query is asked from the deployment's network or from this machine."""
        return self._bundled or self._network_available()

    def _client_argv(self, user: str, password: str, schema: str, batch: bool) -> list[str]:
        client = [
            "mysql",
            "--protocol=TCP",
            f"-h{'127.0.0.1' if self._bundled else self._host}",
            f"-P{self._port}",
            f"-u{user}",
            f"-p{password}",
            f"--connect-timeout={CONNECT_TIMEOUT_SECONDS}",
        ]
        if self._ssl_mode:
            client.append(f"--ssl-mode={self._ssl_mode}")
        if self._ca_pem:
            client.append(f"--ssl-ca={CA_PATH}")
        if batch:
            client += ["-B", "-N"]
        if schema:
            client.append(schema)
        return client

    def _with_authority(self, client: list[str]) -> list[str]:
        """The client run behind a line that plants the authority it has to check.

        The certificate travels base64-encoded and quoted, so a PEM's newlines and a
        bundle holding several certificates survive being handed to a shell. ``exec``
        rather than a second command, so the client still owns the standard input the
        SQL arrives on.
        """
        if not self._ca_pem:
            return client
        encoded = base64.b64encode(self._ca_pem.encode("utf-8")).decode("ascii")
        program = " ".join(shlex.quote(argument) for argument in client)
        return [
            "sh",
            "-c",
            f"printf %s {shlex.quote(encoded)} | base64 -d > {CA_PATH} && exec {program}",
        ]

    def _command(self, user: str, password: str, schema: str, batch: bool) -> list[str]:
        client = self._with_authority(self._client_argv(user, password, schema, batch))

        if self._bundled:
            return self._base + ["exec", "-i", BUNDLED_CONTAINER] + client
        network = ["--network", self._network] if self._network_available() else []
        return self._base + ["run", "--rm", "-i"] + network + [CLIENT_IMAGE] + client

    def run(
        self,
        user: str,
        password: str,
        sql: str = "",
        schema: str = "",
        batch: bool = False,
        stdin=None,
    ) -> subprocess.CompletedProcess:
        """Issue SQL, from stdin or from a file handle, and return what happened."""
        return subprocess.run(
            self._command(user, password, schema, batch),
            input=None if stdin is not None else sql,
            stdin=stdin,
            capture_output=True,
            text=True,
            check=False,
        )

    def scalar(self, user: str, password: str, sql: str, schema: str = "") -> str:
        """One value from a single-row query, or "" when the query returns nothing."""
        result = self.run(user, password, sql, schema, batch=True)
        if result.returncode != 0:
            raise RuntimeError(error_of(result) or "query failed")
        return result.stdout.strip()

    def describe(self) -> str:
        """Where this client asks its questions, for a report a researcher reads."""
        if self._bundled:
            return f"the bundled database at {self._host}:{self._port}"
        where = "the deployment's network" if self._network_available() else "this host"
        return f"{self._host}:{self._port}, from {where}"


def error_of(result: subprocess.CompletedProcess) -> str:
    """What MySQL said, with the client's own advisory left out."""
    lines = [
        line.strip()
        for line in (result.stderr or "").splitlines()
        if line.strip() and "Using a password on the command line" not in line
    ]
    return lines[-1] if lines else ""


def denied(result: subprocess.CompletedProcess) -> bool:
    """Whether a statement failed for want of a privilege rather than for anything else."""
    return "denied" in (result.stderr or "").lower()


def quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def quote_sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def waits_for_container(placement_choice: str) -> bool:
    """Whether setup has a database container of its own to wait for."""
    return placement.runs_bundled_mysql(placement_choice)
