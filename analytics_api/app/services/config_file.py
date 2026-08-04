"""Reads a JSON config file that changes underneath a running process.

Both configs this API reads are rewritten while it runs, by the Configurator and
the setup script, so a value cached for the process lifetime would go stale. Both
are generated at deployment time and may be absent; `load` returns None then.
"""

import json
import logging
import os
import pathlib
from typing import Any, Callable

logger = logging.getLogger(__name__)


class JsonConfigFile:
    """A JSON file re-read only when it changes on disk.

    `build` turns the parsed object into the value to cache. It runs once per
    change, and nothing else keeps the raw content, so it is where redaction
    belongs.
    """

    def __init__(
        self,
        env_var: str,
        default_path: pathlib.Path,
        build: Callable[[dict], Any],
        description: str,
    ):
        self._env_var = env_var
        self._default_path = default_path
        self._build = build
        self._description = description
        self._cache_key: tuple | None = None
        self._cached: Any | None = None
        # Remembered separately so a broken file is not re-read and re-logged on
        # every request, only after it changes on disk.
        self._failed_key: tuple | None = None

    @property
    def env_var(self) -> str:
        return self._env_var

    @property
    def default_path(self) -> pathlib.Path:
        return self._default_path

    def path(self) -> pathlib.Path:
        configured = os.getenv(self._env_var, "").strip()
        return pathlib.Path(configured) if configured else self._default_path

    def clear_cache(self) -> None:
        self._cache_key = None
        self._cached = None
        self._failed_key = None

    def _forget(self) -> None:
        self._cache_key = None
        self._cached = None

    def load(self) -> Any | None:
        """The built value, or None when the file is absent or unusable."""
        path = self.path()
        try:
            stat = path.stat()
        except OSError:
            self._forget()
            return None

        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if self._cached is not None and self._cache_key == key:
            return self._cached
        if self._failed_key == key:
            return None

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            logger.warning("Could not read the %s at %s: %s", self._description, path, error)
            self._forget()
            self._failed_key = key
            return None

        if not isinstance(raw, dict):
            logger.warning("The %s at %s is not a JSON object", self._description, path)
            self._forget()
            self._failed_key = key
            return None

        built = self._build(raw)
        self._cache_key = key
        self._cached = built
        self._failed_key = None
        return built
