"""Every table an iPhone writes has somewhere to land and something to read it.

The micro-server inserts with a plain `INSERT INTO`; it never creates a table, so
a table the schema does not declare means the batch is rejected and the data is
gone. These tests hold the three pieces together — what the client sends, what
`db/ios-tables.sql` creates, and what the API can read — so a table cannot be
added to one and forgotten in the others.

The client-side list is written down here rather than parsed out of the iOS
project, which lives in a separate repository: this file is the record of what
that inspection found.
"""

import pathlib
import re

import pytest

from app.routers.ios import _EXPORT_MODELS

SCHEMA = pathlib.Path(__file__).resolve().parents[2] / "db" / "ios-tables.sql"

#: Tables the AWARE iOS client writes, from the sensors its manager registers
#: plus the framework core. Sensors it registers but that are absent from the
#: study config still appear: enabling one must not start dropping data.
CLIENT_TABLES = {
    "accelerometer", "aware_device", "barometer", "basic_settings", "battery",
    "battery_charges", "battery_discharges", "bluetooth", "calls", "fitbit_data",
    "fitbit_device", "google_fused_location", "gyroscope", "health_kit",
    "ios_aware_log", "ios_location_visit", "ios_status_monitor",
    "linear_accelerometer", "locations", "magnetometer", "network",
    "plugin_ambient_noise", "plugin_ble_heartrate", "plugin_calendar",
    "plugin_calendar_esm_scheduler", "plugin_contacts", "plugin_device_usage",
    "plugin_fitbit", "plugin_headphone_motion", "plugin_ios_activity_recognition",
    "plugin_ios_esm", "plugin_ios_pedometer", "plugin_ntptime",
    "plugin_openweather", "plugin_studentlife_audio", "processor",
    "push_notification", "rotation", "screen", "sensor_wifi",
    "significant_motion", "timezone", "wifi",
}

#: Written by sensors the client registers but the study config leaves out, and
#: not yet given a table. Enabling either one starts dropping its batches.
KNOWN_UNCOVERED = {"gravity", "proximity"}


def schema_tables() -> set[str]:
    text = SCHEMA.read_text(encoding="utf-8")
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS `([a-z_0-9]+)`", text))


def api_tables() -> set[str]:
    tables = set()
    for entry in _EXPORT_MODELS.values():
        for model in entry if isinstance(entry, tuple) else (entry,):
            tables.add(model.__tablename__)
    return tables


def test_every_table_the_client_writes_exists_in_the_schema():
    missing = sorted(CLIENT_TABLES - schema_tables() - KNOWN_UNCOVERED)
    assert not missing, (
        f"the client writes {missing} and the schema declares no such table, so "
        "the micro-server's insert fails and the batch is discarded"
    )


def test_the_event_log_is_readable_through_the_api():
    """The point of collecting it is being able to look at it."""
    assert "ios_aware_log" in api_tables(), "nothing can read the client's event log"


def test_the_status_monitor_is_stored_without_being_offered():
    """It records how the device is doing rather than what the study measures.

    The table keeps receiving, so the data is there for a question that needs it;
    the dashboard does not carry a card nobody reads.
    """
    assert "ios_status_monitor" in schema_tables()
    assert "ios_status_monitor" not in api_tables()


def test_both_wifi_tables_are_covered():
    """`wifi` is the access point in use, `sensor_wifi` the ones in range."""
    for table in ("wifi", "sensor_wifi"):
        assert table in schema_tables()
        assert table in api_tables()


@pytest.mark.parametrize("table", sorted(KNOWN_UNCOVERED))
def test_uncovered_tables_stay_recorded(table):
    """Records the gap that is knowingly left open, so closing it is deliberate.

    If a table here gains a schema entry, it has been covered and belongs in
    CLIENT_TABLES instead.
    """
    assert table not in schema_tables(), (
        f"{table} now has a table; move it out of KNOWN_UNCOVERED"
    )
