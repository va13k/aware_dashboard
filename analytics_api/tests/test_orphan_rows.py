"""Rows belonging to no device, and the totals that used to disagree about them.

Android's data tables declare `device_id varchar(150) DEFAULT ''`, so an insert
that omits the device succeeds and lands under an empty string. The dashboard used
to count those rows and never export them, which let a manifest report more than
any download could produce — a discrepancy with nothing on screen explaining it.

Two things are checked. Public totals leave them out, while the count cache keeps
an internal row so an orphan-only batch can still advance the sensor watermark.
And their number is reported, because it is the figure that decides what to do
with them: a handful is an early test insert, a large block is data a phone really
collected.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Double, String
from sqlalchemy.orm import declarative_base

from app.models import AndroidRecordCount
from app.routers import export as export_router
from app.services import orphan_rows, record_counts

_Base = declarative_base()


class _SourceModel(_Base):
    """A stand-in source table for the refresh to read."""

    __tablename__ = "magnetometer"
    _id = Column(BigInteger, primary_key=True)
    device_id = Column(String(150), default="")
    timestamp = Column(Double, default=0)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar(self):
        return self._rows[0][0] if self._rows else 0

    def one(self):
        return self._rows[0]


class _Session:
    """Answers the grouped read, and records what it was asked to write."""

    def __init__(self, rows):
        self.rows = rows
        self.inserted = []
        self.statements = []

    async def execute(self, statement):
        text = str(statement)
        self.statements.append(text)
        if text.startswith("INSERT"):
            self.inserted.append(statement.compile().params)
            return _Result([])
        if "max(record_counts.last_id)" in text:
            return _Result([(0,)])
        return _Result(self.rows)

    async def commit(self):
        pass

    async def rollback(self):
        pass


class _Row:
    def __init__(self, device_id, count, last_id, timestamp):
        self._values = (device_id, count, last_id, timestamp)

    def __iter__(self):
        return iter(self._values)


class _StatsSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if "min(" in sql:
            return _Result(
                [SimpleNamespace(first_timestamp=100.0, last_timestamp=200.0)]
            )
        if "count(" in sql:
            return _Result([(7,)])
        return _Result([("phone-a",)])


@pytest.mark.asyncio
async def test_an_orphan_row_advances_the_internal_watermark():
    """Otherwise an orphan-only batch is scanned again on every refresh."""
    session = _Session([_Row("", 52, 900, 1.0), _Row("phone-a", 10, 950, 2.0)])

    await record_counts.refresh(
        session, AndroidRecordCount, {"magnetometer": _SourceModel}
    )

    cached = [entry["device_id"] for entry in session.inserted]
    assert cached == ["", "phone-a"]


@pytest.mark.asyncio
async def test_public_sensor_totals_filter_the_internal_orphan_row():
    session = _Session([])

    assert await record_counts.sensor_totals(session, AndroidRecordCount) == {}

    query = session.statements[0]
    assert "record_counts.device_id !=" in query


@pytest.mark.asyncio
async def test_a_cold_manifest_excludes_orphans_from_every_statistic():
    """The live-count fallback must agree with the warmed cache and exports."""
    session = _StatsSession()

    stats = await export_router._sensor_stats(session, (_SourceModel,))

    assert stats == {
        "row_count": 7,
        "devices_with_data": 1,
        "first_timestamp": 100.0,
        "last_timestamp": 200.0,
    }
    assert len(session.statements) == 3
    assert all("magnetometer.device_id IS NOT NULL" in sql for sql in session.statements)
    assert all("magnetometer.device_id !=" in sql for sql in session.statements)


@pytest.mark.asyncio
async def test_orphans_are_reported_per_table(monkeypatch):
    async def records_by_table(db, model, window, tables=None, device_id=None):
        assert device_id == orphan_rows.NO_DEVICE
        assert window == (None, None)
        return {"magnetometer": 52, "battery": 3}

    monkeypatch.setattr(
        orphan_rows.coverage_rollup, "records_by_table", records_by_table
    )

    summary = await orphan_rows.summary(None, None)

    assert summary["records"] == 55
    # Largest first, so the table worth a decision is named first.
    assert list(summary["tables"]) == ["magnetometer", "battery"]


@pytest.mark.asyncio
async def test_a_study_with_no_orphans_reports_zero_rather_than_nothing(monkeypatch):
    async def records_by_table(db, model, window, tables=None, device_id=None):
        return {}

    monkeypatch.setattr(
        orphan_rows.coverage_rollup, "records_by_table", records_by_table
    )

    summary = await orphan_rows.summary(None, None)

    assert summary == {"records": 0, "tables": {}}


@pytest.mark.asyncio
async def test_the_internal_orphan_row_never_arrives_as_a_device():
    """It carries a watermark, not a phone. Unfiltered it would put a device with
    an empty id in the list, which is the opposite of what the gate is for."""
    from app.routers import devices as devices_router

    session = _Session([])

    assert await devices_router._cached_last_seen_by_device(
        session, AndroidRecordCount
    ) == {}
    assert "record_counts.device_id !=" in session.statements[0]
