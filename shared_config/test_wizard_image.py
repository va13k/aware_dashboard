"""Tests for what the setup wizard's image carries, against what it runs.

The image is built from a handful of named `COPY` lines rather than the directory,
and the two ways that list can be wrong fail differently. A script the wizard runs
and the image does not carry is a researcher shown a 500 at the moment they save,
which is the worst moment this deployment has. A script carried and never run is
dead weight that reads as though it works there, and one of them could not: a file
resolving the project to its own parent directory finds nothing to import inside the
image, where its parent is the root.

So the list is held to exactly the scripts the container executes, plus the one it is
started as.
"""

import ast
import pathlib
import re

PROJECT = pathlib.Path(__file__).resolve().parent.parent
SETUP = PROJECT / "setup"


def read(name: str) -> str:
    return (SETUP / name).read_text(encoding="utf-8")


def copied_into_the_image() -> set[str]:
    """Every Python file a `COPY` line puts in the image, by name."""
    return set(re.findall(r"^COPY\s+(\S+\.py)\s", read("Dockerfile"), re.MULTILINE))


def started_as() -> set[str]:
    """The script the container's own command runs."""
    command = re.search(r"^CMD\s+\[(.*)\]", read("Dockerfile"), re.MULTILINE)
    assert command, "the Dockerfile declares no CMD"
    return {
        pathlib.PurePosixPath(part).name
        for part in re.findall(r'"([^"]+)"', command.group(1))
        if part.endswith(".py")
    }


def run_by_the_server() -> set[str]:
    """Scripts `server.py` names, read as code so a comment cannot claim one."""
    tree = ast.parse(read("server.py"))
    return {
        pathlib.PurePosixPath(node.value).name
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith(".py")
    }


def run_by_the_cgi() -> set[str]:
    """Scripts the save endpoint runs, with its comments stripped first."""
    lines = [line.split("#", 1)[0] for line in read("deploy.sh").splitlines()]
    return set(re.findall(r"([A-Za-z0-9_]+\.py)", "\n".join(lines)))


def test_every_script_the_wizard_runs_is_in_its_image():
    missing = sorted((run_by_the_server() | run_by_the_cgi()) - copied_into_the_image())

    assert not missing, (
        f"the wizard runs {', '.join(missing)} and the image does not carry it, "
        "which is a 500 on the researcher's first save"
    )


def test_the_image_carries_nothing_it_does_not_run():
    spare = sorted(
        copied_into_the_image() - run_by_the_server() - run_by_the_cgi() - started_as()
    )

    assert not spare, (
        f"the image carries {', '.join(spare)} and nothing in it runs that: either "
        "run it there or leave it on the host"
    )


def test_the_command_the_container_starts_is_carried_too():
    assert started_as() <= copied_into_the_image()
