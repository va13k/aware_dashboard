from __future__ import annotations

import contextlib
import json
import os
import pathlib
from typing import Any, Callable

from shared_config.runtime import SECRET_MODE, atomic_write_text


def _project_root() -> pathlib.Path:
    container_path = pathlib.Path("/project")
    if container_path.is_dir():
        return container_path
    return pathlib.Path(__file__).resolve().parent.parent


SOURCE_PATH = _project_root() / "source.json"

# source.json is a runtime file, not source code: it holds this deployment's
# study configuration and participant credentials, so it is gitignored and
# materialized from the committed template on first use.
TEMPLATE_PATH = _project_root() / "source.example.json"


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


def _ensure_unlocked() -> None:
    """Create source.json from the template when it does not exist yet.

    Never overwrites an existing file: the Configurator persists researcher
    edits into source.json, so re-running deployment must leave them intact.
    """
    if SOURCE_PATH.exists():
        return

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Neither {SOURCE_PATH.name} nor its template {TEMPLATE_PATH.name} exists; "
            "cannot initialize the study configuration."
        )

    with TEMPLATE_PATH.open("r", encoding="utf-8") as f:
        template = json.load(f)

    _atomic_write_unlocked(template)


def _read_unlocked() -> dict[str, Any]:
    with SOURCE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_unlocked(data: dict[str, Any]) -> None:
    # source.json holds participant credentials and is only ever read by the
    # Configurator, which runs as the deploying user.
    atomic_write_text(SOURCE_PATH, json.dumps(data, indent=2) + "\n", SECRET_MODE)


def ensure_source() -> None:
    """Materialize source.json from the template if it is missing."""
    with source_lock():
        _ensure_unlocked()


def read_source() -> dict[str, Any]:
    with source_lock():
        _ensure_unlocked()
        return _read_unlocked()


def write_source(data: dict[str, Any]) -> None:
    with source_lock():
        _atomic_write_unlocked(data)


def update_source(mutator: Callable[[dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any]:
    with source_lock():
        _ensure_unlocked()
        current = _read_unlocked()
        updated = mutator(current)
        if updated is None:
            updated = current
        _atomic_write_unlocked(updated)
        return updated
