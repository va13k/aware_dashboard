"""Tests for writing a generated file, on a platform with modes and on one without.

Every file this deployment generates is written the same way: into a temporary
neighbour, given its mode, then moved onto the name atomically, so a reader is
handed one whole version or the other and never a half-written one.

Two halves of that are Unix's alone. A descriptor carries a mode there and nowhere
else, and a file being written can be removed there while it is still open. On
Windows the first raises and the second refuses, and the second refusing is what
turns a failure into a different failure: the temporary file could not be cleaned
up, reported in place of whatever went wrong first.
"""

import os
import pathlib
import sys

import pytest

PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from shared_config import runtime  # noqa: E402


@pytest.fixture
def without_descriptor_modes(monkeypatch):
    """The platform Windows presents: no `fchmod` for a descriptor to be given."""
    monkeypatch.delattr(os, "fchmod", raising=False)


def leftovers(directory: pathlib.Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.name.endswith(".tmp"))


def test_the_text_arrives_where_descriptors_carry_a_mode(tmp_path):
    target = tmp_path / "generated.json"

    runtime.atomic_write_text(target, '{"study": 1}\n', runtime.SHARED_MODE)

    assert target.read_text(encoding="utf-8") == '{"study": 1}\n'
    assert target.stat().st_mode & 0o777 == runtime.SHARED_MODE
    assert leftovers(tmp_path) == []


def test_the_text_arrives_where_they_do_not(tmp_path, without_descriptor_modes):
    """What every host script on Windows does before it does anything else."""
    target = tmp_path / "generated.json"

    runtime.atomic_write_text(target, '{"study": 1}\n', runtime.SECRET_MODE)

    assert target.read_text(encoding="utf-8") == '{"study": 1}\n'
    assert leftovers(tmp_path) == []


def test_a_mode_is_asked_of_a_descriptor_that_carries_one(tmp_path):
    target = tmp_path / "secret.env"

    runtime.atomic_write_text(target, "KEY=value\n", runtime.SECRET_MODE)

    assert target.stat().st_mode & 0o777 == runtime.SECRET_MODE


def test_stating_a_mode_asks_nothing_of_a_descriptor_without_one(
    tmp_path, without_descriptor_modes
):
    handle = os.open(tmp_path / "plain", os.O_CREAT | os.O_WRONLY)
    try:
        runtime.set_descriptor_mode(handle, runtime.SECRET_MODE)
    finally:
        os.close(handle)


def test_a_write_that_fails_leaves_no_temporary_behind(
    tmp_path, monkeypatch, without_descriptor_modes
):
    """The failure that used to be reported as a file it could not delete.

    The descriptor is closed before the cleanup runs, which is the only order under
    which Windows lets the temporary file go, so what surfaces is the original
    failure rather than a permission error standing in front of it.
    """
    def refuse(*_args, **_kwargs):
        raise OSError("the move did not happen")

    monkeypatch.setattr(runtime.os, "replace", refuse)
    target = tmp_path / "generated.json"

    with pytest.raises(OSError, match="the move did not happen"):
        runtime.atomic_write_text(target, "half a file", runtime.SHARED_MODE)

    assert not target.exists()
    assert leftovers(tmp_path) == []


def test_a_second_write_replaces_the_first(tmp_path):
    target = tmp_path / "generated.json"

    runtime.atomic_write_text(target, "first\n", runtime.SHARED_MODE)
    runtime.atomic_write_text(target, "second\n", runtime.SHARED_MODE)

    assert target.read_text(encoding="utf-8") == "second\n"
    assert leftovers(tmp_path) == []
