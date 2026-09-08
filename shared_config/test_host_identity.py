"""Tests for the user the Configurator writes a study as.

Editing a study writes files into the bind-mounted project directory --- the
configuration a phone reads, the ESM definitions, the study model --- and the
compose file runs that one service as `HOST_UID:HOST_GID` so what it writes stays
owned by whoever deployed. `setup.sh` fills both in from the deploying user's own
ids. Nothing on Windows can: there is no `id -u` to ask, and the compose default of
1000:1000 is then a user that owns nothing at all. Docker Desktop presents the mount
as root, the directories the deploy creates inside it keep the 0755 they were made
with, and the first Save lands in `studies/` as a PermissionError the researcher is
shown as a 500 --- with the study half written.

So the deploy settles it from the one thing true wherever it runs: who owns the
project directory as the containers see it.
"""

import pathlib
import sys

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import deploy_config  # noqa: E402


def owner_of(path: pathlib.Path) -> tuple[str, str]:
    stat = path.stat()
    return str(stat.st_uid), str(stat.st_gid)


def test_the_identity_is_the_project_directorys_own_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_config, "PROJECT", tmp_path)
    env: dict[str, str] = {}

    deploy_config.ensure_host_identity(env)

    assert (env["HOST_UID"], env["HOST_GID"]) == owner_of(tmp_path)


def test_what_the_shell_entrypoint_wrote_is_left_alone(tmp_path, monkeypatch):
    """`setup.sh` knows something this cannot: the real user behind a `sudo`."""
    monkeypatch.setattr(deploy_config, "PROJECT", tmp_path)
    env = {"HOST_UID": "1001", "HOST_GID": "1002"}

    deploy_config.ensure_host_identity(env)

    assert (env["HOST_UID"], env["HOST_GID"]) == ("1001", "1002")


def test_a_half_written_answer_is_completed_rather_than_kept(tmp_path, monkeypatch):
    """A uid with no gid beside it is a service compose cannot start at all."""
    monkeypatch.setattr(deploy_config, "PROJECT", tmp_path)
    env = {"HOST_UID": "1001", "HOST_GID": "  "}

    deploy_config.ensure_host_identity(env)

    assert env["HOST_UID"] == "1001"
    assert env["HOST_GID"] == owner_of(tmp_path)[1]


def test_a_project_directory_that_cannot_be_read_settles_nothing(tmp_path, monkeypatch):
    """Reported and carried past: compose still has its own default, and a deploy
    that stopped here would stop on something no researcher can act on."""
    monkeypatch.setattr(deploy_config, "PROJECT", tmp_path / "gone")
    env: dict[str, str] = {}

    deploy_config.ensure_host_identity(env)

    assert env == {}


def test_root_reaches_the_file_compose_reads_it_from(tmp_path, monkeypatch):
    """`0` is the answer on Docker Desktop, and the one an `if value:` drops."""
    monkeypatch.setattr(deploy_config, "ENV_PATH", tmp_path / ".env")

    deploy_config.persist_env({"DB_ADMIN_USER": "root", "HOST_UID": "0", "HOST_GID": "0"})

    written = (tmp_path / ".env").read_text(encoding="utf-8").splitlines()
    assert "HOST_UID=0" in written
    assert "HOST_GID=0" in written
