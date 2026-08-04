"""Reads the sensor settings iPhones are configured from.

`studies/studyConfig.json` is the Android config; its `ios_sensors` block holds
only the three iOS-only flags. The settings an iPhone receives come from the
micro-server config, which has a different shape: sensor and plugin groups, each
with its own settings list, and values serialised as strings (`"false"`,
`"20000"`).

Only the settings are read. The file's `server` block holds the database user and
password and its `study` block holds researcher contact details; neither is
extracted, so neither can be cached or served here. Settings with a secret name
are dropped using the same denylist as the study config.
"""

import pathlib
from dataclasses import dataclass, field
from typing import Any

from app.services import study_config
from app.services.config_file import JsonConfigFile

CONFIG_PATH_ENV = "MICRO_SERVER_CONFIG_PATH"
DEFAULT_CONFIG_PATH = pathlib.Path("/app/aware-config.json")

SENSORS_KEY = "sensors"
PLUGINS_KEY = "plugins"
SETTINGS_KEY = "settings"


def settings_map(config: dict) -> dict[str, Any]:
    """Flatten every sensor and plugin settings list into `{setting: value}`."""
    settings: dict[str, Any] = {}
    if not isinstance(config, dict):
        return settings

    for section in (SENSORS_KEY, PLUGINS_KEY):
        for group in config.get(section) or []:
            if not isinstance(group, dict):
                continue
            for entry in group.get(SETTINGS_KEY) or []:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("setting")
                if not isinstance(name, str) or not name:
                    continue
                if study_config.is_secret_key(name):
                    continue
                settings[name] = entry.get("value")
    return settings


@dataclass(frozen=True)
class MicroServerConfig:
    """The iOS-facing settings, without the server and study blocks."""

    path: pathlib.Path
    settings: dict = field(default_factory=dict, repr=False)


def _build(raw: dict) -> MicroServerConfig:
    return MicroServerConfig(path=_file.path(), settings=settings_map(raw))


_file = JsonConfigFile(
    env_var=CONFIG_PATH_ENV,
    default_path=DEFAULT_CONFIG_PATH,
    build=_build,
    description="micro-server config",
)


def config_path() -> pathlib.Path:
    return _file.path()


def clear_cache() -> None:
    _file.clear_cache()


def load_micro_config() -> MicroServerConfig | None:
    """The iOS settings, or None when the config is absent or unreadable."""
    return _file.load()
