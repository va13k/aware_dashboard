from __future__ import annotations

import contextlib
import json
import os
import pathlib
import tempfile
from typing import Any, Callable

def _project_root() -> pathlib.Path:
    container_path = pathlib.Path("/project")
    if container_path.is_dir():
        return container_path
    return pathlib.Path(__file__).resolve().parent.parent


SOURCE_PATH = _project_root() / "source.json"
LOCK_PATH = SOURCE_PATH.with_suffix(SOURCE_PATH.suffix + ".lock")


@contextlib.contextmanager
def source_lock():
    import fcntl

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

def _read_unlocked() -> dict[str, Any]:
    with SOURCE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_unlocked(data: dict[str, Any]) -> None:
    SOURCE_PATH.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=SOURCE_PATH.name + ".",
        suffix=".tmp",
        dir=str(SOURCE_PATH.parent),
    )
    tmp_path = pathlib.Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=2)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())

        os.replace(tmp_path, SOURCE_PATH)

        dir_fd = os.open(SOURCE_PATH.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def read_source() -> dict[str, Any]:
    with source_lock():
        return _read_unlocked()


def write_source(data: dict[str, Any]) -> None:
    with source_lock():
        _atomic_write_unlocked(data)


def update_source(mutator: Callable[[dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any]:
    with source_lock():
        current = _read_unlocked()
        updated = mutator(current)
        if updated is None:
            updated = current
        _atomic_write_unlocked(updated)
        return updated