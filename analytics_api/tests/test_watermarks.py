"""Watermark construction, and what happens when the count cache cannot answer.

The merge import's whole duplicate test is the watermark, so a watermark that is
wrong in the low direction is not a slow path — it is silent duplication. The
case that matters is `record_counts.last_ts` reading 0, which it does for every
row written before that column was added.
"""

import pytest

from app.models import AndroidAccelerometer, AndroidRecordCount
from app.services import watermarks


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Answers each query by looking at the SQL it was handed."""

    def __init__(self, cached_rows, table_rows=None, live_rows=None):
        self.cached_rows = cached_rows
        self.table_rows = table_rows or []
        self.live_rows = live_rows or {}
        self.live_queries = []

    async def execute(self, query, params=None):
        sql = str(query).lower()
        if "record_counts" in sql:
            return _Result(self.cached_rows)
        if "information_schema" in sql:
            return _Result([(name,) for name in self.table_rows])
        if "group by device_id" in sql:
            table = sql.split("`")[3]
            self.live_queries.append(table)
            return _Result(self.live_rows.get(table, []))
        return _Result([])

    async def rollback(self):
        pass


SOURCES = {"accelerometer": AndroidAccelerometer}


@pytest.mark.asyncio
async def test_a_usable_cache_entry_becomes_the_watermark():
    session = _FakeSession(
        cached_rows=[("accelerometer", "phone-a", 5000.0)],
        table_rows=["accelerometer"],
    )
    built = await watermarks.build(session, "aware_android", AndroidRecordCount, SOURCES)

    assert built[("aware_android", "accelerometer")] == {"phone-a": 5000.0}
    assert session.live_queries == []


@pytest.mark.asyncio
async def test_a_zero_last_ts_sends_the_table_to_a_live_reading():
    """A row predating the `last_ts` column reads 0. Believing it would set the
    watermark to the epoch and admit every row the backup holds."""
    session = _FakeSession(
        cached_rows=[("accelerometer", "phone-a", 0.0)],
        table_rows=["accelerometer"],
        live_rows={"accelerometer": [("phone-a", 8000.0)]},
    )
    built = await watermarks.build(session, "aware_android", AndroidRecordCount, SOURCES)

    assert session.live_queries == ["accelerometer"]
    assert built[("aware_android", "accelerometer")] == {"phone-a": 8000.0}


@pytest.mark.asyncio
async def test_one_unusable_device_condemns_the_whole_table():
    """Filtering the devices with a good value while waving the rest through is
    the mixture that duplicates data, so the table is read live instead."""
    session = _FakeSession(
        cached_rows=[
            ("accelerometer", "phone-a", 5000.0),
            ("accelerometer", "phone-b", 0.0),
        ],
        table_rows=["accelerometer"],
        live_rows={"accelerometer": [("phone-a", 5000.0), ("phone-b", 9000.0)]},
    )
    built = await watermarks.build(session, "aware_android", AndroidRecordCount, SOURCES)

    assert session.live_queries == ["accelerometer"]
    assert built[("aware_android", "accelerometer")] == {
        "phone-a": 5000.0,
        "phone-b": 9000.0,
    }


@pytest.mark.asyncio
async def test_a_null_last_ts_is_treated_the_same_as_zero():
    session = _FakeSession(
        cached_rows=[("accelerometer", "phone-a", None)],
        table_rows=["accelerometer"],
        live_rows={"accelerometer": [("phone-a", 7000.0)]},
    )
    built = await watermarks.build(session, "aware_android", AndroidRecordCount, SOURCES)

    assert session.live_queries == ["accelerometer"]
    assert built[("aware_android", "accelerometer")] == {"phone-a": 7000.0}


@pytest.mark.asyncio
async def test_a_table_the_cache_never_covers_is_read_live():
    """aware_device is not a sensor stream, so no cache row ever describes it."""
    session = _FakeSession(
        cached_rows=[("accelerometer", "phone-a", 5000.0)],
        table_rows=["accelerometer", "aware_device"],
        live_rows={"aware_device": [("phone-a", 1234.0)]},
    )
    built = await watermarks.build(session, "aware_android", AndroidRecordCount, SOURCES)

    assert session.live_queries == ["aware_device"]
    assert built[("aware_android", "aware_device")] == {"phone-a": 1234.0}


@pytest.mark.asyncio
async def test_an_empty_table_contributes_no_watermark_at_all():
    """No stored rows means nothing to compare against, and the merge keeps
    everything the backup offers for it."""
    session = _FakeSession(
        cached_rows=[],
        table_rows=["aware_device"],
        live_rows={"aware_device": []},
    )
    built = await watermarks.build(session, "aware_android", AndroidRecordCount, SOURCES)

    assert ("aware_android", "aware_device") not in built
