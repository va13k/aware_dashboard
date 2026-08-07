"""record_counts service over a stand-in session.

No MySQL runs: a fake session answers each query by inspecting the compiled SQL,
so these assert the read shapes and the refresh orchestration (watermark → scan
→ upsert → commit) without a database.
"""

import pytest

from app.models import AndroidAccelerometer, AndroidRecordCount
from app.services import record_counts


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _FakeSession:
    def __init__(self, watermark=0, scan_rows=None, read_rows=None):
        self.watermark = watermark
        self.scan_rows = scan_rows or []
        self.read_rows = read_rows or []
        self.upserts = []
        self.committed = False

    async def execute(self, query):
        sql = str(query).lower()
        if "insert into" in sql:
            self.upserts.append(query)
            return _Result()
        if "max(record_counts.last_id)" in sql:
            return _Result(scalar=self.watermark)
        if "group by" in sql and "accelerometer" in sql:
            return _Result(rows=self.scan_rows)
        # read paths (counts_for_device / sensor_totals)
        return _Result(rows=self.read_rows)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_counts_for_device_maps_rows():
    db = _FakeSession(read_rows=[("accelerometer", 10), ("battery", 3)])
    result = await record_counts.counts_for_device(db, AndroidRecordCount, "dev-1")
    assert result == {"accelerometer": 10, "battery": 3}


@pytest.mark.asyncio
async def test_sensor_totals_maps_rows():
    db = _FakeSession(read_rows=[("accelerometer", 500, 2), ("battery", 40, 1)])
    result = await record_counts.sensor_totals(db, AndroidRecordCount)
    assert result == {"accelerometer": (500, 2), "battery": (40, 1)}


@pytest.mark.asyncio
async def test_refresh_scans_since_watermark_and_upserts():
    # Two devices gained rows since the watermark; each becomes one upsert.
    db = _FakeSession(
        watermark=100,
        scan_rows=[("dev-1", 5, 130), ("dev-2", 2, 128)],
    )
    added = await record_counts.refresh(
        db, AndroidRecordCount, {"accelerometer": AndroidAccelerometer}
    )
    assert added == {"accelerometer": 7}
    assert len(db.upserts) == 2
    assert db.committed


@pytest.mark.asyncio
async def test_refresh_with_no_new_rows_adds_nothing():
    db = _FakeSession(watermark=200, scan_rows=[])
    added = await record_counts.refresh(
        db, AndroidRecordCount, {"accelerometer": AndroidAccelerometer}
    )
    assert added == {}
    assert db.upserts == []
