"""Reads and redacts study configurations.

This module is the only place that handles a raw study config, and everything it
returns is redacted. Both sides of a config comparison carry credentials: the
deployed file holds the participant and root database passwords, and so does the
copy a phone reports back in `aware_studies.study_config` - verified against
real data, populated, despite the `config_without_password` flag being true.

Redaction therefore happens before anything else, including fingerprinting. That
ordering is deliberate: a fingerprint taken over unredacted content could not be
compared against a phone whose copy omits a secret field, and no caller can
accidentally hash - or return - the credentials by reaching for the wrong
function.
"""

import hashlib
import json
import pathlib
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Any

from app.services.config_file import JsonConfigFile

CONFIG_PATH_ENV = "CURRENT_STUDY_CONFIG_PATH"
DEFAULT_CONFIG_PATH = pathlib.Path("/app/studies/studyConfig.json")

SENSORS_KEY = "sensors"
IOS_SENSORS_KEY = "ios_sensors"
DATABASE_KEY = "database"

# Substring match against the lowercased key name. Deliberately not a bare
# "key": `status_keyboard` and `mask_keyboard` are ordinary settings, while
# `plugin_openweather_api_key` and `api_secret_plugin_fitbit` are not.
SECRET_KEY_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "api_key",
    "apikey",
    "username",
)

# Checked before the markers: both carry a marker substring in their name while
# being plain booleans a researcher has to be able to see.
PUBLIC_KEY_NAMES = frozenset({"config_without_password", "require_ssl"})

# The database block is allowlisted rather than filtered, because host, port and
# name describe deployment internals that are not part of what a researcher
# compares between a phone and the server.
DATABASE_PUBLIC_KEYS = PUBLIC_KEY_NAMES

# Left out of the fingerprint. Re-saving a config in the Configurator moves
# `updatedAt` without changing a single setting, and marking every phone stale
# for that would make the current/stale signal worthless. The readable version
# indicator is reported separately, from `updatedAt` itself.
VOLATILE_KEYS = frozenset({"createdAt", "updatedAt"})

_DROP = object()


@lru_cache(maxsize=4096)
def _is_secret_name(lowered: str) -> bool:
    if lowered in PUBLIC_KEY_NAMES:
        return False
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)


def is_secret_key(name: Any) -> bool:
    # Cached on the normalised name: redacting one config asks this a few hundred
    # times, over the same 150-odd names. `str()` first, because a malformed
    # config can put an unhashable value where a setting name belongs.
    return _is_secret_name(str(name).lower())


def _as_dict(value: Any) -> dict:
    """A section of a config that should be an object, or an empty one.

    Configs are files on disk and payloads from phones; a section that arrives as
    a list or a number must not take the endpoint down.
    """
    return value if isinstance(value, dict) else {}


def _is_setting_entry(value: dict) -> bool:
    """A `{"setting": name, "value": ...}` pair from a sensors list.

    These need the name inspected instead of the key, because the secret sits in
    the value of a key called "setting" - `mqtt_password`, for one.
    """
    return "setting" in value


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        if _is_setting_entry(value):
            if is_secret_key(value.get("setting")):
                return _DROP
            return {key: _redact(item) for key, item in value.items()}

        result = {}
        for key, item in value.items():
            if is_secret_key(key):
                continue
            if key == DATABASE_KEY and isinstance(item, dict):
                result[key] = {
                    name: item[name] for name in item if name in DATABASE_PUBLIC_KEYS
                }
                continue
            redacted_item = _redact(item)
            if redacted_item is not _DROP:
                result[key] = redacted_item
        return result

    if isinstance(value, list):
        items = (_redact(item) for item in value)
        return [item for item in items if item is not _DROP]

    return value


def redact(config: dict) -> dict:
    """Strip every credential from a config. Idempotent."""
    if not isinstance(config, dict):
        return {}
    return _redact(config)


def settings_map(config: dict) -> dict[str, Any]:
    """Flatten the Android `sensors` list into `{setting: value}`.

    Malformed entries are skipped rather than raising - a config the phone
    round-tripped is not something this process controls. A repeated setting
    keeps its last value, matching how the client reads the list.
    """
    settings: dict[str, Any] = {}
    for entry in redact(config).get(SENSORS_KEY) or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("setting")
        if not isinstance(name, str) or not name:
            continue
        settings[name] = entry.get("value")
    return settings


def ios_settings_map(config: dict) -> dict[str, Any]:
    """The iOS flags, which are a plain mapping rather than a settings list."""
    ios_settings = redact(config).get(IOS_SENSORS_KEY)
    if not isinstance(ios_settings, dict):
        return {}
    return dict(ios_settings)


def as_text(value: Any) -> str | None:
    """A config identifier as text, or None when it is not a scalar.

    `_id` and `updatedAt` come from a phone, so they can be any JSON type. A
    number is reported as text; a list or an object is reported as absent. Both
    the event signature and the response schemas need a hashable scalar here.
    """
    if isinstance(value, str):
        return value or None
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def is_enabled(value: Any) -> bool:
    """Truthiness of a config flag, tolerant of how it was serialised."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return False


def comparable(config: dict) -> dict:
    """The content two configs should be compared on: redacted and canonical.

    Both the fingerprint and the field-level diff are built from this, so
    "identical fingerprints" and "no differing fields" cannot disagree.
    """
    data = {
        key: value
        for key, value in redact(config).items()
        if key not in VOLATILE_KEYS
    }
    if isinstance(data.get(SENSORS_KEY), list):
        # As a mapping the content no longer depends on list order. Today the
        # client stores the list verbatim, but a reordering client must not make
        # every phone look stale.
        data[SENSORS_KEY] = settings_map(config)
    return data


def content_fingerprint(config: dict) -> str:
    """SHA-256 over the canonical, redacted, order-independent content."""
    payload = json.dumps(
        comparable(config),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def safe_summary(config: dict) -> dict[str, Any]:
    """The config facts that may be returned to a browser."""
    safe = redact(config)
    settings = settings_map(config)
    database = _as_dict(safe.get(DATABASE_KEY))
    study_info = _as_dict(safe.get("study_info"))

    status_settings = {
        name: value for name, value in settings.items() if name.startswith("status_")
    }
    plugin_settings = {
        name: value
        for name, value in status_settings.items()
        if name.startswith("status_plugin_")
    }

    return {
        "config_id": safe.get("_id") or None,
        "config_updated_at": safe.get("updatedAt") or None,
        "study_title": study_info.get("study_title") or None,
        "config_fingerprint": content_fingerprint(config),
        "require_ssl": is_enabled(database.get("require_ssl")),
        "config_without_password": is_enabled(database.get("config_without_password")),
        "config_update_enabled": is_enabled(settings.get("enable_config_update")),
        "enabled_sensor_count": sum(
            1
            for name, value in status_settings.items()
            if name not in plugin_settings and is_enabled(value)
        ),
        "enabled_plugin_count": sum(
            1 for value in plugin_settings.values() if is_enabled(value)
        ),
    }


@dataclass(frozen=True)
class DeployedStudyConfig:
    """The deployed config, already redacted. `config` holds no credentials."""

    path: pathlib.Path
    config: dict = field(repr=False)
    settings: dict = field(repr=False)
    ios_settings: dict = field(repr=False)
    fingerprint: str = ""
    summary: dict = field(default_factory=dict, repr=False)


def _build(raw: dict) -> DeployedStudyConfig:
    return DeployedStudyConfig(
        path=_file.path(),
        config=redact(raw),
        settings=settings_map(raw),
        ios_settings=ios_settings_map(raw),
        fingerprint=content_fingerprint(raw),
        summary=safe_summary(raw),
    )


_file = JsonConfigFile(
    env_var=CONFIG_PATH_ENV,
    default_path=DEFAULT_CONFIG_PATH,
    build=_build,
    description="deployed study config",
)


def config_path() -> pathlib.Path:
    return _file.path()


def clear_cache() -> None:
    _file.clear_cache()


def load_deployed_config() -> DeployedStudyConfig | None:
    """The deployed config, or None when it is absent or unreadable.

    Absent is a normal state, not an error: the file is generated at deployment
    time. Callers report an unknown config status instead of failing.
    """
    return _file.load()
