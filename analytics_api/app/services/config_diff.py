"""Compares the config a phone carries against the deployed one.

Both sides are reduced to `study_config.comparable` first, which redacts them and
drops the version metadata. Two consequences worth knowing:

A credential can never reach a diff row, because the redaction happens before the
comparison rather than being filtered out of the result afterwards.

`config_status` and the diff rows are derived from the same content, so a phone
cannot read `current` while showing differing fields, and it cannot read `stale`
with nothing to show. `createdAt` and `updatedAt` are excluded from that content -
re-saving a config moves them without changing a setting - so they are reported
as plain version indicators instead of as differences.
"""

from dataclasses import dataclass, field
from typing import Any

from app.services import study_config

CURRENT = "current"
STALE = "stale"
UNKNOWN = "unknown"

CHANGED = "changed"
ONLY_ON_SERVER = "only_on_server"
ONLY_ON_DEVICE = "only_on_device"

NO_DEVICE_CONFIG = "no_device_config"
NO_SERVER_CONFIG = "no_server_config"

ENABLE_CONFIG_UPDATE = "enable_config_update"

_MISSING = object()


@dataclass(frozen=True)
class ConfigDiffRow:
    #: Dotted path into the config, e.g. `sensors.status_wifi`.
    path: str
    kind: str
    server_value: Any = None
    device_value: Any = None


@dataclass(frozen=True)
class ConfigDiff:
    config_status: str = UNKNOWN
    #: Why the status is unknown, so the UI can say which side is missing.
    status_reason: str | None = None
    #: Whether the deployed config lets a phone update its own config.
    config_update_enabled: bool = False
    #: The same flag as the phone currently has it, which can lag the server.
    device_config_update_enabled: bool = False
    server_updated_at: str | None = None
    device_updated_at: str | None = None
    diff_count: int = 0
    rows: list[ConfigDiffRow] = field(default_factory=list)


def _updated_at(config: dict | None) -> str | None:
    if not isinstance(config, dict):
        return None
    return study_config.as_text(config.get("updatedAt"))


def _update_flag(config: dict | None) -> bool:
    if not isinstance(config, dict):
        return False
    return study_config.is_enabled(
        study_config.settings_map(config).get(ENABLE_CONFIG_UPDATE)
    )


def _join(prefix: str, key: Any) -> str:
    return f"{prefix}.{key}" if prefix else str(key)


def _walk(path: str, server: Any, device: Any, rows: list[ConfigDiffRow]) -> None:
    if server is _MISSING:
        rows.append(ConfigDiffRow(path=path, kind=ONLY_ON_DEVICE, device_value=device))
        return
    if device is _MISSING:
        rows.append(ConfigDiffRow(path=path, kind=ONLY_ON_SERVER, server_value=server))
        return

    if isinstance(server, dict) and isinstance(device, dict):
        for key in sorted(set(server) | set(device), key=str):
            _walk(
                _join(path, key),
                server.get(key, _MISSING),
                device.get(key, _MISSING),
                rows,
            )
        return

    if isinstance(server, list) and isinstance(device, list):
        for index in range(max(len(server), len(device))):
            _walk(
                f"{path}[{index}]",
                server[index] if index < len(server) else _MISSING,
                device[index] if index < len(device) else _MISSING,
                rows,
            )
        return

    if server != device:
        rows.append(
            ConfigDiffRow(
                path=path,
                kind=CHANGED,
                server_value=server,
                device_value=device,
            )
        )


def compare(server: dict | None, device: dict | None) -> ConfigDiff:
    """Field-level differences between the deployed and the installed config.

    A missing config on either side is a normal state, not an error: the file is
    generated at deployment time, and a phone only reports a config on its update
    events. Either way the status is unknown and no differences are claimed.
    """
    server_updated_at = _updated_at(server)
    device_updated_at = _updated_at(device)
    flags = {
        "config_update_enabled": _update_flag(server),
        "device_config_update_enabled": _update_flag(device),
        "server_updated_at": server_updated_at,
        "device_updated_at": device_updated_at,
    }

    if not isinstance(server, dict) or not server:
        return ConfigDiff(status_reason=NO_SERVER_CONFIG, **flags)
    if not isinstance(device, dict) or not device:
        return ConfigDiff(status_reason=NO_DEVICE_CONFIG, **flags)

    rows: list[ConfigDiffRow] = []
    _walk("", study_config.comparable(server), study_config.comparable(device), rows)

    return ConfigDiff(
        config_status=CURRENT if not rows else STALE,
        diff_count=len(rows),
        rows=rows,
        **flags,
    )


def compare_with_deployed(device: dict | None) -> ConfigDiff:
    """The same comparison, against whatever config is currently deployed."""
    deployed = study_config.load_deployed_config()
    return compare(deployed.config if deployed else None, device)
