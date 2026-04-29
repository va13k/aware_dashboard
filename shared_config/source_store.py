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
_EXAMPLE_PATH = _project_root() / "source.example.json"


def _bootstrap_if_missing() -> None:
    if not SOURCE_PATH.exists() and _EXAMPLE_PATH.exists():
        import shutil
        shutil.copy2(_EXAMPLE_PATH, SOURCE_PATH)


@contextlib.contextmanager
def source_lock():
    import fcntl

    dir_fd = os.open(SOURCE_PATH.parent, os.O_RDONLY)
    try:
        fcntl.flock(dir_fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(dir_fd, fcntl.LOCK_UN)
    finally:
        os.close(dir_fd)


def _read_unlocked() -> dict[str, Any]:
    with SOURCE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_unlocked(data: dict[str, Any]) -> None:
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

    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def read_source() -> dict[str, Any]:
    _bootstrap_if_missing()
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
