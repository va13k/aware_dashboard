"""Where "last upload" comes from.

Reading it from the sensor tables means a `MAX(timestamp)` over every one of
them — around eighty aggregate scans for a single device list, which took some
twenty seconds against a study-sized database. The record-count cache already
carries `last_ts` per sensor and device, so one grouped read of a small table
answers the same question.

The scan stays for the case the cache cannot answer: a deployment whose first
refresh has not run yet.
"""

import pytest

from app.models import AndroidRecordCount
from app.routers import devices as devices_router


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Row:
    def __init__(self, device_id, last_seen):
        self.device_id = device_id
        self.last_seen = last_seen


class _ContactRow:
    def __init__(self, device_id, last_contact):
        self.device_id = device_id
        self.last_contact = last_contact


class _Session:
    """Answers the cache query, and counts how often it was asked."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = 0

    async def execute(self, _query):
        self.queries += 1
        return _Result(self.rows)


@pytest.mark.asyncio
async def test_last_seen_comes_from_the_cache_in_one_query():
    session = _Session([_Row("phone-a", 1_700.0), _Row("phone-b", 2_500.0)])

    result = await devices_router._combined_last_seen_by_device(
        session, [object(), object(), object()], count_model=AndroidRecordCount
    )

    assert result == {"phone-a": 1_700.0, "phone-b": 2_500.0}
    assert session.queries == 1, "one grouped read, not one per sensor table"


@pytest.mark.asyncio
async def test_a_cold_cache_falls_back_to_the_tables(monkeypatch):
    """A cache that has never been refreshed answers for nobody."""
    session = _Session([])
    scanned = []

    async def scan(_db, model):
        scanned.append(model)
        return {"phone-a": 4_200.0}

    monkeypatch.setattr(devices_router, "_max_timestamps_by_device", scan)

    result = await devices_router._combined_last_seen_by_device(
        session, ["sensor-one", "sensor-two"], count_model=AndroidRecordCount
    )

    assert result == {"phone-a": 4_200.0}
    assert scanned == ["sensor-one", "sensor-two"]


@pytest.mark.asyncio
async def test_without_a_cache_model_the_tables_are_scanned(monkeypatch):
    async def scan(_db, model):
        return {"phone-a": 1.0} if model == "sensor-one" else {"phone-b": 9.0}

    monkeypatch.setattr(devices_router, "_max_timestamps_by_device", scan)

    result = await devices_router._combined_last_seen_by_device(
        _Session([]), ["sensor-one", "sensor-two"]
    )

    assert result == {"phone-a": 1.0, "phone-b": 9.0}


@pytest.mark.asyncio
async def test_the_newest_upload_wins_across_sensors(monkeypatch):
    async def scan(_db, model):
        return {"phone-a": 1.0} if model == "sensor-one" else {"phone-a": 8.0}

    monkeypatch.setattr(devices_router, "_max_timestamps_by_device", scan)

    result = await devices_router._combined_last_seen_by_device(
        _Session([]), ["sensor-one", "sensor-two"]
    )

    assert result == {"phone-a": 8.0}


@pytest.mark.asyncio
async def test_a_device_with_no_timestamp_is_left_out():
    session = _Session([_Row("phone-a", None), _Row("phone-b", 0), _Row("phone-c", 5.0)])

    result = await devices_router._combined_last_seen_by_device(
        session, [object()], count_model=AndroidRecordCount
    )

    assert result == {"phone-c": 5.0}


@pytest.mark.asyncio
async def test_last_contact_comes_from_the_server_contact_table():
    session = _Session(
        [_ContactRow("phone-a", 1_700), _ContactRow("phone-b", 2_500)]
    )

    result = await devices_router._last_contact_by_device(
        session, devices_router.AndroidDeviceContact
    )

    assert result == {"phone-a": 1_700, "phone-b": 2_500}
    assert session.queries == 1
