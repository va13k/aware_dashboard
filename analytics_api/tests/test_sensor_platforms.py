"""Each sensor's declared platform matches the platform that can serve it.

The dashboard groups sensors into Shared / Android only / iPhone only from the
`platform` field in `config/sensors.ts`. A sensor labelled for one platform while
both collect it hides half the study; one labelled shared while only one platform
can answer shows a card that stays empty forever.

Ground truth is the schema: a sensor can only be served by a platform whose
database actually has its table. The API's export maps supply the key-to-table
mapping, since a sensor key and its table name often differ.
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

#: Sensors the dashboard shows for which no table exists on either platform, so
#: the card can only ever read zero. Recorded rather than hidden: each is either
#: a card to remove or a table to add.
UNSERVED = {
    "esms",           # android ESM lives in several tables, exported via /export
    "installations",
    "memory",         # no table in either schema; the iOS client does not register it
    "notes",
    "screentext",
    "telephony",
    "touch",
}


def declared() -> list[tuple[str, str]]:
    text = CONFIG.read_text(encoding="utf-8")
    return re.findall(r'key:\s*"([^"]+)"[\s\S]*?platform:\s*"(shared|android|ios)"', text)


def schema_tables(platform: str) -> set[str]:
    text = SCHEMA[platform].read_text(encoding="utf-8")
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS `([a-z_0-9]+)`", text))


def tables_for(key: str, export_map: dict) -> set[str]:
    entry = export_map.get(key)
    if entry is None:
        return set()
    models = entry if isinstance(entry, tuple) else (entry,)
    return {m.__tablename__ for m in models if hasattr(m, "__tablename__")}


def servable(key: str) -> str:
    on_android = bool(tables_for(key, ANDROID) & schema_tables("android"))
    on_ios = bool(tables_for(key, IOS) & schema_tables("ios"))
    if on_android and on_ios:
        return "shared"
    if on_android:
        return "android"
    if on_ios:
        return "ios"
    return "unserved"


def test_the_config_is_readable():
    """A parse that silently found nothing would make every test below pass."""
    assert len(declared()) > 40


@pytest.mark.parametrize("key, platform", declared())
def test_declared_platform_matches_what_can_serve_it(key, platform):
    actual = servable(key)
    if actual == "unserved":
        assert key in UNSERVED, (
            f"{key} is shown in the dashboard but no table on either platform holds it"
        )
        return
    assert platform == actual, (
        f"{key} is declared {platform!r} but the API serves it on {actual!r}"
    )


def test_the_sections_are_derived_rather_than_listed():
    """Two hand-kept lists are what let a sensor sit under the wrong heading."""
    text = CONFIG.read_text(encoding="utf-8")
    for name in ("SHARED_SENSOR_CONFIGS", "ANDROID_SENSOR_CONFIGS", "IOS_SENSOR_CONFIGS"):
        assert f"export const {name}: SensorConfig[] = ALL_SENSOR_CONFIGS.filter" in text, (
            f"{name} should be filtered from the single list, not maintained by hand"
        )


def test_ambient_noise_and_processor_are_shared():
    """Both tables exist in both databases; neither belongs to one platform."""
    platforms = dict(declared())
    assert platforms["plugin-ambient-noise"] == "shared"
    assert platforms["processor"] == "shared"


def test_proximity_is_android_until_ios_has_a_table():
    """The iOS model points at a table the schema does not create.

    The iPhone can collect proximity; this deployment does not store it, so an
    iPhone section for it would promise data that cannot arrive.
    """
    assert dict(declared())["proximity"] == "android"
    assert "proximity" not in schema_tables("ios")
