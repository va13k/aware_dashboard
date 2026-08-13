"""A sensor is one capability, and it names the table serving it on each platform.

The dashboard groups sensors into Shared / Android only / iPhone only from those
names alone, so a table named on a platform whose schema lacks it would move a
sensor under the wrong heading, and a capability stored under different names on
the two platforms would otherwise appear twice, each half looking exclusive.

These check the names against the schemas, which is where the answer actually
lives, and against the API, which has to serve what the card offers.
"""

import pathlib
import re

import pytest

from app.routers.android import _EXPORT_MODELS as ANDROID
from app.routers.ios import _EXPORT_MODELS as IOS

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / "dashboard" / "src" / "config" / "sensors.ts"
SCHEMA = {
    "android": ROOT / "db" / "android-tables.sql",
    "ios": ROOT / "db" / "ios-tables.sql",
}

#: Capabilities both platforms collect under different table names. Listed so a
#: split back into two platform-specific cards fails rather than passing quietly.
SHARED_UNDER_DIFFERENT_NAMES = {
    "esm": ("esms", "plugin_ios_esm"),
    "esm-scheduler": ("scheduler", "plugin_calendar_esm_scheduler"),
    "significant-motion": ("significant", "significant_motion"),
}


def declared() -> dict[str, dict[str, str]]:
    """Each sensor key and the table it names per platform."""
    text = CONFIG.read_text(encoding="utf-8")
    found = {}
    for key, tables in re.findall(
        r'key:\s*"([^"]+)"[\s\S]*?tables:\s*\{([^}]*)\}', text
    ):
        found[key] = dict(re.findall(r'(android|ios):\s*"([a-z_0-9]+)"', tables))
    return found


def schema_tables(platform: str) -> set[str]:
    text = SCHEMA[platform].read_text(encoding="utf-8")
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS `([a-z_0-9]+)`", text))


def api_tables(key: str, export_map: dict) -> set[str]:
    entry = export_map.get(key)
    if entry is None:
        return set()
    models = entry if isinstance(entry, tuple) else (entry,)
    return {m.__tablename__ for m in models if hasattr(m, "__tablename__")}


def test_the_config_is_readable():
    """A parse that silently found nothing would make every test below pass."""
    assert len(declared()) > 40


def test_every_sensor_names_at_least_one_table():
    """A sensor serving neither platform is a card that can only read zero."""
    empty = sorted(key for key, tables in declared().items() if not tables)
    assert not empty, f"{empty} name no table on either platform"


@pytest.mark.parametrize("key, tables", sorted(declared().items()))
def test_named_tables_exist_in_that_schema(key, tables):
    for platform, table in tables.items():
        assert table in schema_tables(platform), (
            f"{key} names {table!r} on {platform}, which that schema does not create"
        )


@pytest.mark.parametrize("key, tables", sorted(declared().items()))
def test_the_api_serves_every_platform_the_card_offers(key, tables):
    """A card offering a platform the API cannot answer is a dead download."""
    for platform, table in tables.items():
        served = api_tables(key, ANDROID if platform == "android" else IOS)
        assert table in served, (
            f"{key} offers {platform}, but the API serves {served or 'nothing'} "
            f"for that key rather than {table!r}"
        )


@pytest.mark.parametrize("key, expected", sorted(SHARED_UNDER_DIFFERENT_NAMES.items()))
def test_capabilities_stored_under_different_names_stay_one_card(key, expected):
    android_table, ios_table = expected
    tables = declared()[key]
    assert tables.get("android") == android_table
    assert tables.get("ios") == ios_table


def test_no_capability_is_offered_twice():
    """Two keys reading one table is the duplicate this model exists to prevent."""
    seen: dict[tuple[str, str], str] = {}
    for key, tables in declared().items():
        for platform, table in tables.items():
            previous = seen.get((platform, table))
            assert previous is None, (
                f"{key} and {previous} both read {table} on {platform}"
            )
            seen[(platform, table)] = key


def test_the_sections_are_derived_rather_than_declared():
    text = CONFIG.read_text(encoding="utf-8")
    assert "export function sensorPlatform(" in text
    for name in ("SHARED", "ANDROID", "IOS"):
        assert (
            f"{name}_SENSOR_CONFIGS: SensorConfig[] = ALL_SENSOR_CONFIGS.filter" in text
        )
