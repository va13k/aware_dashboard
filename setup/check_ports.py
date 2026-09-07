#!/usr/bin/env python3
"""The addresses this deployment publishes, asked about before anything is built.

Every port here is one a container binds on the host, and one already held by other
software is a container that never starts: nginx without port 80 serves nothing, and
a database that cannot publish its port ends the compose run. Asked first, the answer
is a sentence naming the port, what needs it and what holds it. Asked by Docker
partway through, it is an error about an address, minutes after the images began
building.

A port one of this deployment's own containers holds is what a redeploy looks like,
so those read as available.

Both entry scripts call this, so a researcher on either platform is told the same
thing about the same machine.
"""

import argparse
import errno
import os
import pathlib
import socket
import subprocess
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = pathlib.Path("/project")
if not PROJECT.exists():
    PROJECT = SCRIPT_DIR.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from detect_public_host import is_usable_address  # noqa: E402

ENV_PATH = PROJECT / ".env"

#: Written from the database placement and removed again, so its presence states
#: that the study names a database of its own and this deployment publishes none.
COMPOSE_OVERRIDE = PROJECT / "docker-compose.external-db.yml"

#: Every container in this deployment carries this prefix, which is what tells a
#: port held by the deployment apart from a port held by other software.
OWN_PREFIX = "aware_"

#: Bind addresses that mean every interface. A connection test aims at loopback
#: instead, which is an address this machine always answers on.
EVERY_INTERFACE = ("", "0.0.0.0", "*", "::", "[::]")
LOOPBACK = "127.0.0.1"

CONNECT_TIMEOUT_SECONDS = 1.0


def read_env() -> dict[str, str]:
    """`.env` as a mapping, and an empty one before the first wizard save."""
    env: dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    try:
        text = ENV_PATH.read_text(encoding="utf-8")
    except OSError:
        return env
    for line in text.splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def port_number(value: str, default: int) -> int:
    """A port from the environment, falling back to the compose file's own default."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if 1 <= number <= 65535 else default


def wanted(env: dict[str, str], include_wizard: bool = False) -> list[dict]:
    """Each address a container publishes on this host, and what needs it.

    The two nginx ports are written into the compose file and are the same for every
    deployment. The broker's address and the database's come from ``.env``, and the
    database appears only where this deployment runs one.
    """
    addresses = [
        {
            "host": "0.0.0.0",
            "port": 80,
            "needed_by": "nginx, which serves the dashboard, the Configurator and the study links",
        },
        {
            "host": "0.0.0.0",
            "port": 443,
            "needed_by": "nginx, for the same over HTTPS",
        },
        {
            "host": env.get("MQTT_BIND_ADDRESS") or "0.0.0.0",
            "port": port_number(env.get("MQTT_PUBLIC_PORT", ""), 1883),
            "needed_by": "the message broker, which carries what you send to a participant's phone",
        },
    ]
    if not COMPOSE_OVERRIDE.exists():
        addresses.append(
            {
                "host": env.get("MYSQL_BIND_ADDRESS") or LOOPBACK,
                "port": 3306,
                "needed_by": "the study database this deployment runs",
            }
        )
    if include_wizard:
        addresses.append(
            {
                "host": env.get("SETUP_BIND") or "0.0.0.0",
                "port": 9999,
                "needed_by": "the setup wizard",
            }
        )
    return addresses


def outbound_address() -> str:
    """The address this machine reaches the network from.

    Asked of the routing table by opening a UDP socket toward a documentation
    address and reading back which of its own addresses the kernel chose. Nothing
    is sent, so this touches no network.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 80))
            found = probe.getsockname()[0]
    except OSError:
        return ""
    return found if is_usable_address(found) else ""


def hostname_addresses() -> list[str]:
    """Every address this machine's own name resolves to."""
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    return [
        sockaddr[0]
        for *_rest, sockaddr in infos
        if is_usable_address(sockaddr[0])
    ]


def own_addresses() -> list[str]:
    """The addresses this machine answers on, as far as it can tell.

    A container publishing on every interface is refused by anything holding that
    port on any one of them, so each is asked rather than loopback alone: a server
    bound to this machine's network address and nothing else answers there and
    nowhere else.

    Only addresses this machine claims as its own are included. A name that resolves
    somewhere else would report another server's port as this deployment's conflict,
    which is a deployment stopped over somebody else's software.
    """
    found = [LOOPBACK]
    for address in [outbound_address(), *hostname_addresses()]:
        if address and address not in found:
            found.append(address)
    return found


def answering_on(host: str, port: int, probes: list[str] | None = None) -> str:
    """The address already holding this port, and an empty string when it is free.

    Two questions, because either alone leaves a gap. A connection that is accepted
    is a listener, and it is the question a user without privileges can ask about
    port 80 --- binding one below 1024 needs root, and the refusal that comes back
    describes the privilege rather than the port. A bind reaches the case a
    connection does not: an address held by something that accepts nothing still
    belongs to it, and Docker is refused the same way.

    What stays out of reach without privileges is the pair of those two: a socket
    bound to one specific address, on a port this user may not bind, that accepts
    nothing. Answering for that means asking the operating system for its listening
    sockets --- ``/proc/net/tcp`` on Linux, ``netstat`` output parsed per platform
    elsewhere --- or asking Docker to attempt the publish itself. Docker's own
    refusal names the port either way, so the deploy still stops; what this gives up
    is stopping it first.
    """
    for address in (probes or [LOOPBACK]) if host in EVERY_INTERFACE else [host]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connector:
            connector.settimeout(CONNECT_TIMEOUT_SECONDS)
            if connector.connect_ex((address, port)) == 0:
                return address

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as binder:
        # A port left in TIME_WAIT by a process that has already gone belongs to
        # nobody, and this is what lets it read that way.
        binder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            binder.bind(("" if host in EVERY_INTERFACE else host, port))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                return host
    return ""


def holders(docker_prefix: list[str]) -> dict[int, str]:
    """The container publishing each host port, for the containers running now."""
    command = [*docker_prefix, "docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}

    found: dict[int, str] = {}
    for line in result.stdout.splitlines():
        name, _, published = line.partition("\t")
        name = name.strip()
        for mapping in published.split(","):
            # "0.0.0.0:9999->9999/tcp" — the host port is what precedes the arrow.
            host_side, arrow, _ = mapping.strip().partition("->")
            if not arrow or ":" not in host_side:
                continue
            try:
                found.setdefault(int(host_side.rsplit(":", 1)[1]), name)
            except ValueError:
                continue
    return found


def find_command(port: int) -> str:
    """How to ask this operating system which program holds a port."""
    if os.name == "nt":
        return f"netstat -ano | findstr :{port}"
    return f"sudo lsof -i :{port}"


def conflicts(
    addresses: list[dict], running: dict[int, str], probes: list[str] | None = None
) -> list[dict]:
    """The addresses held by something other than this deployment."""
    reachable = probes if probes is not None else own_addresses()
    found = []
    for address in addresses:
        holder = running.get(address["port"], "")
        if holder.startswith(OWN_PREFIX):
            continue
        answering = answering_on(address["host"], address["port"], reachable)
        if answering:
            found.append({**address, "holder": holder, "answering_on": answering})
    return found


def report(found: list[dict]) -> None:
    print("")
    print("  These ports are already in use, and this deployment has to publish them:")
    print("")
    for address in found:
        print(f"    Port {address['port']} — needed by {address['needed_by']}.")
        if address.get("answering_on", LOOPBACK) != LOOPBACK:
            print(f"      Something is answering on {address['answering_on']}:{address['port']}.")
        if address["holder"]:
            print(f"      A Docker container named {address['holder']} is publishing it.")
            print(f"      Stop it with:  docker stop {address['holder']}")
        else:
            print("      No Docker container is publishing it, so another program on this")
            if address["port"] in (80, 443):
                print("      machine has it — a system Apache or Nginx is the usual one.")
            else:
                print("      machine has it.")
            print(f"      Find out which with:  {find_command(address['port'])}")
        print("")
    print("  Free each port, then run setup again. These addresses are written into")
    print("  the deployment, so the stack has no second port to fall back on.")
    print("")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--wizard",
        action="store_true",
        help="Also check the port the setup wizard is served on",
    )
    parser.add_argument(
        "--docker-prefix",
        action="append",
        default=[],
        help="Optional command prefix before docker, for example: --docker-prefix sudo",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    addresses = wanted(read_env(), include_wizard=args.wizard)
    found = conflicts(addresses, holders(list(args.docker_prefix)))

    if found:
        report(found)
        return 1

    checked = ", ".join(str(address["port"]) for address in addresses)
    print(f"  Ports available: {checked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
