"""Tests for the addresses a deployment publishes, asked about before it is built.

The check exists to turn one failure into a sentence: a port another program holds
is a container that never starts, and Docker reports that as an error about an
address, partway through a build. Three things decide whether the sentence is the
right one.

Which ports are asked about follows the deployment — the broker's address and the
database's come from `.env`, and a study on a database it named publishes none of
its own. Who holds a port decides whether it is a conflict at all, because a port
held by this deployment's own container is what every redeploy looks like. And a
port below 1024 cannot be bound by the user running setup, so the question has to be
asked in a way that answers for port 80 rather than describing a privilege.

A container publishing on every interface is refused by anything holding that port
on any one of them, so a wildcard publish is asked about at each address this
machine claims as its own. Which addresses those are is the other half of it: a name
resolving somewhere else would report another server's port as this deployment's
conflict.
"""

import pathlib
import socket
import subprocess
import sys

import pytest

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import check_ports  # noqa: E402


@pytest.fixture
def bundled(monkeypatch, tmp_path):
    """A deployment that runs its own database, which the override's absence states."""
    monkeypatch.setattr(check_ports, "COMPOSE_OVERRIDE", tmp_path / "absent.yml")


@pytest.fixture
def external(monkeypatch, tmp_path):
    """A study on a database it named, so this deployment publishes no database port."""
    override = tmp_path / "docker-compose.external-db.yml"
    override.write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(check_ports, "COMPOSE_OVERRIDE", override)


def ports_of(addresses):
    return [address["port"] for address in addresses]


def test_nginx_and_the_broker_and_the_bundled_database_are_asked_about(bundled):
    assert sorted(ports_of(check_ports.wanted({}))) == [80, 443, 1883, 3306]


def test_a_study_on_its_own_database_publishes_no_database_port(external):
    assert 3306 not in ports_of(check_ports.wanted({}))


def test_the_wizard_port_is_asked_about_only_when_it_is_wanted(bundled):
    assert 9999 not in ports_of(check_ports.wanted({}))
    assert 9999 in ports_of(check_ports.wanted({}, include_wizard=True))


def test_the_broker_port_comes_from_the_deployment(bundled):
    addresses = check_ports.wanted({"MQTT_PUBLIC_PORT": "8883", "MQTT_BIND_ADDRESS": "127.0.0.1"})
    broker = [a for a in addresses if a["port"] == 8883]

    assert broker and broker[0]["host"] == "127.0.0.1"
    assert 1883 not in ports_of(addresses)


def test_the_wizard_bound_to_loopback_is_asked_about_there(bundled):
    addresses = check_ports.wanted({"SETUP_BIND": "127.0.0.1"}, include_wizard=True)
    wizard = [a for a in addresses if a["port"] == 9999]

    assert wizard and wizard[0]["host"] == "127.0.0.1"


@pytest.mark.parametrize("value", ["", "   ", "not-a-port", "0", "70000", None])
def test_a_port_that_is_not_one_falls_back_to_the_compose_default(value):
    assert check_ports.port_number(value, 1883) == 1883


def test_an_address_with_a_listener_names_itself():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind((check_ports.LOOPBACK, 0))
        held.listen(128)
        port = held.getsockname()[1]

        assert check_ports.answering_on(check_ports.LOOPBACK, port) == check_ports.LOOPBACK

    assert check_ports.answering_on(check_ports.LOOPBACK, port) == ""


def test_loopback_is_always_among_the_addresses_asked():
    assert check_ports.own_addresses()[0] == check_ports.LOOPBACK


def test_each_address_is_asked_about_once():
    assert len(check_ports.own_addresses()) == len(set(check_ports.own_addresses()))


def test_an_address_this_machine_does_not_claim_is_never_asked_about(monkeypatch):
    """A name resolving elsewhere would report another server's port as ours."""
    monkeypatch.setattr(check_ports, "outbound_address", lambda: "")
    monkeypatch.setattr(
        check_ports.socket,
        "getaddrinfo",
        lambda *a, **k: [
            (check_ports.socket.AF_INET, 0, 0, "", ("127.0.0.1", 0)),
            (check_ports.socket.AF_INET, 0, 0, "", ("169.254.1.1", 0)),
            (check_ports.socket.AF_INET, 0, 0, "", ("10.1.2.3", 0)),
        ],
    )

    # Loopback is there once as itself, the link-local address is not usable, and
    # what remains is the address the machine really carries.
    assert check_ports.own_addresses() == [check_ports.LOOPBACK, "10.1.2.3"]


@pytest.fixture
def own_network_address():
    """An address this machine carries besides loopback, when it has one."""
    addresses = [a for a in check_ports.own_addresses() if a != check_ports.LOOPBACK]
    if not addresses:
        pytest.skip("this machine reports no address of its own beyond loopback")
    return addresses[0]


def test_a_listener_on_one_interface_is_found_for_a_publish_on_every_interface(
    own_network_address,
):
    """The case loopback alone answers nothing about.

    Asserted in the positive direction only. Whether the bind that follows the
    connections also reports the address is the platform's own answer --- SO_REUSEADDR
    on a wildcard bind over a held specific address reads differently across
    them --- and the connections are what this has to get right on all of them.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind((own_network_address, 0))
        held.listen(128)
        port = held.getsockname()[1]

        found = check_ports.answering_on("0.0.0.0", port, check_ports.own_addresses())

    assert found == own_network_address


def test_a_port_this_deployments_own_container_holds_is_available(monkeypatch):
    """What every redeploy looks like: nginx already answering on the port it needs."""
    monkeypatch.setattr(check_ports, "answering_on", lambda host, port, probes=None: host)
    addresses = [{"host": "0.0.0.0", "port": 80, "needed_by": "nginx"}]

    assert check_ports.conflicts(addresses, {80: "aware_nginx"}) == []


def test_a_port_another_container_holds_is_a_conflict_naming_it(monkeypatch):
    monkeypatch.setattr(check_ports, "answering_on", lambda host, port, probes=None: host)
    addresses = [{"host": "0.0.0.0", "port": 80, "needed_by": "nginx"}]

    found = check_ports.conflicts(addresses, {80: "someone_elses_proxy"})

    assert [entry["holder"] for entry in found] == ["someone_elses_proxy"]


def test_a_port_held_by_no_container_is_a_conflict_with_no_holder(monkeypatch):
    monkeypatch.setattr(check_ports, "answering_on", lambda host, port, probes=None: host)
    addresses = [{"host": "0.0.0.0", "port": 80, "needed_by": "nginx"}]

    found = check_ports.conflicts(addresses, {})

    assert [entry["holder"] for entry in found] == [""]


def test_a_free_port_is_no_conflict(monkeypatch):
    monkeypatch.setattr(check_ports, "answering_on", lambda host, port, probes=None: "")
    addresses = [{"host": "0.0.0.0", "port": 80, "needed_by": "nginx"}]

    assert check_ports.conflicts(addresses, {}) == []


def _docker_ps(output: str, returncode: int = 0):
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, returncode, output, "")

    return run


def test_the_container_publishing_each_port_is_read_from_docker(monkeypatch):
    monkeypatch.setattr(
        check_ports.subprocess,
        "run",
        _docker_ps(
            "aware_nginx\t0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp\n"
            "aware_mysql\t127.0.0.1:3306->3306/tcp\n"
            "other_app\t0.0.0.0:8080->8080/tcp\n"
        ),
    )

    assert check_ports.holders([]) == {
        80: "aware_nginx",
        443: "aware_nginx",
        3306: "aware_mysql",
        8080: "other_app",
    }


def test_a_container_publishing_nothing_names_no_port(monkeypatch):
    monkeypatch.setattr(
        check_ports.subprocess, "run", _docker_ps("aware_micro\t8080/tcp\n")
    )

    assert check_ports.holders([]) == {}


def test_a_docker_that_does_not_answer_leaves_the_holder_unknown(monkeypatch):
    """The conflict is still reported; what holds it is what goes unnamed."""
    def refuse(command, **kwargs):
        raise OSError("docker daemon is not running")

    monkeypatch.setattr(check_ports.subprocess, "run", refuse)

    assert check_ports.holders([]) == {}


def test_the_docker_prefix_reaches_the_command(monkeypatch):
    seen = {}

    def record(command, **kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(check_ports.subprocess, "run", record)
    check_ports.holders(["sudo"])

    assert seen["command"][:3] == ["sudo", "docker", "ps"]


def test_the_command_offered_suits_the_operating_system(monkeypatch):
    monkeypatch.setattr(check_ports.os, "name", "posix")
    assert check_ports.find_command(80) == "sudo lsof -i :80"

    monkeypatch.setattr(check_ports.os, "name", "nt")
    assert check_ports.find_command(80) == "netstat -ano | findstr :80"


def test_the_report_names_the_interface_it_answered_on(capsys):
    check_ports.report(
        [{"port": 1883, "needed_by": "the broker", "holder": "", "answering_on": "192.168.0.19"}]
    )

    assert "answering on 192.168.0.19:1883" in capsys.readouterr().out


def test_the_report_keeps_the_interface_to_itself_for_loopback(capsys):
    """One address, and the line naming it would repeat what follows."""
    check_ports.report(
        [{"port": 1883, "needed_by": "the broker", "holder": "", "answering_on": check_ports.LOOPBACK}]
    )

    assert "answering on" not in capsys.readouterr().out


def test_the_report_offers_the_command_that_frees_a_container(capsys):
    check_ports.report(
        [{"port": 80, "needed_by": "nginx", "holder": "other_proxy", "answering_on": check_ports.LOOPBACK}]
    )

    assert "docker stop other_proxy" in capsys.readouterr().out


def test_the_report_offers_the_command_that_finds_a_program(capsys, monkeypatch):
    monkeypatch.setattr(check_ports.os, "name", "posix")
    check_ports.report(
        [{"port": 80, "needed_by": "nginx", "holder": "", "answering_on": check_ports.LOOPBACK}]
    )

    assert "sudo lsof -i :80" in capsys.readouterr().out
