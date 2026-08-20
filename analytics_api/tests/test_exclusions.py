"""Taking a participant out of the analysis without taking them out of the study.

Withdrawal and exclusion answer different questions. Closing an enrolment window
stops new data arriving; this decides what happens to the data already collected,
which consent forms answer differently — so it is a separate action, defaulting to
keeping everything.

What these check is where the decision bites and where it deliberately does not.
An excluded device leaves the exports, because an export is the analysis dataset
leaving. It stays in the device list, marked, because a participant the dashboard
had quietly dropped would be indistinguishable from one who never took part.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Double, String
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import declarative_base

from app.database import AndroidBase, IosBase
from app.models import AndroidDeviceExclusion, IosDeviceExclusion
from app.routers import export as export_router
from app.services import exclusions

_Base = declarative_base()


class _AndroidSource(AndroidBase):
    __tablename__ = "test_exclusion_android_source"
    _id = Column(BigInteger, primary_key=True)
    device_id = Column(String(150), default="")
    timestamp = Column(Double, default=0)


class _IosSource(IosBase):
    __tablename__ = "test_exclusion_ios_source"
    _id = Column(BigInteger, primary_key=True)
    device_id = Column(String(150), default="")
    timestamp = Column(Double, default=0)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def desc(self):
        return self


class _Session:
    """Answers the distinct-device read with whatever the table holds."""

    def __init__(self, rows):
        self.rows = rows

    async def execute(self, statement):
        return _Result([(value,) for value in self.rows])

    async def rollback(self):
        pass


class _MissingTableSession:
    async def execute(self, statement):
        raise ProgrammingError("SELECT", {}, Exception("table does not exist"))

    async def rollback(self):
        pass


def test_the_exclusion_list_follows_the_model_not_the_session():
    """A caller holding the wrong session must not pair an iOS table with the
    Android exclusion list, so the platform comes from the model itself."""
    assert export_router._exclusion_model(_AndroidSource) is AndroidDeviceExclusion
    assert export_router._exclusion_model(_IosSource) is IosDeviceExclusion


@pytest.mark.asyncio
async def test_an_excluded_device_leaves_the_export(monkeypatch):
    async def excluded_ids(db, model):
        return {"phone-b"}

    monkeypatch.setattr(exclusions, "excluded_ids", excluded_ids)

    found = await export_router._device_ids_for_model(
        _Session(["phone-a", "phone-b", "phone-c"]), _AndroidSource
    )

    assert found == {"phone-a", "phone-c"}


@pytest.mark.asyncio
async def test_orphan_rows_are_still_dropped_alongside(monkeypatch):
    """Two filters for two reasons: a row with no device could never be
    attributed, while an excluded device is a real participant left out."""

    async def excluded_ids(db, model):
        return {"phone-b"}

    monkeypatch.setattr(exclusions, "excluded_ids", excluded_ids)

    found = await export_router._device_ids_for_model(
        _Session(["phone-a", "phone-b", "", None]), _AndroidSource
    )

    assert found == {"phone-a"}


@pytest.mark.asyncio
async def test_nothing_excluded_exports_exactly_as_before(monkeypatch):
    async def excluded_ids(db, model):
        return set()

    monkeypatch.setattr(exclusions, "excluded_ids", excluded_ids)

    found = await export_router._device_ids_for_model(
        _Session(["phone-a", "phone-b"]), _AndroidSource
    )

    assert found == {"phone-a", "phone-b"}


@pytest.mark.asyncio
async def test_a_deployment_without_the_table_excludes_nobody():
    """The table arrived after the exports did, so its absence has to read as
    nothing excluded rather than as an error that empties an archive."""
    assert await exclusions.excluded_ids(
        _MissingTableSession(), AndroidDeviceExclusion
    ) == set()


@pytest.mark.asyncio
async def test_undoing_an_exclusion_removes_the_row():
    """No row is the default state, so there is nothing to record about a device
    nobody excluded — an `undone` marker would be a second way to say included."""
    deleted = []

    class _DeletingSession:
        async def execute(self, statement):
            deleted.append(str(statement))
            return _Result([])

        async def commit(self):
            pass

        async def rollback(self):
            pass

    assert await exclusions.include(
        _DeletingSession(), AndroidDeviceExclusion, "phone-a"
    )
    assert deleted and deleted[0].startswith("DELETE FROM device_exclusions")


@pytest.mark.asyncio
async def test_an_absent_exclusion_table_reports_nothing_rather_than_failing():
    assert await exclusions.exclusions(
        _MissingTableSession(), AndroidDeviceExclusion
    ) == {}


@pytest.mark.asyncio
async def test_excluding_a_device_twice_is_the_same_state_as_once():
    """A researcher correcting the reason should not be told it is already
    excluded, so the write is idempotent and revises the note."""
    stored = SimpleNamespace(device_id="phone-a", excluded_at=100, note="first")
    added = []

    class _ExistingSession:
        async def get(self, model, key):
            return stored

        def add(self, row):
            added.append(row)

        async def commit(self):
            pass

        async def rollback(self):
            pass

    result = await exclusions.exclude(
        _ExistingSession(), AndroidDeviceExclusion, "phone-a", 200, "revised"
    )

    assert added == []
    assert stored.note == "revised"
    # The original moment stands: the decision was taken then, and revising the
    # reason is not a new decision.
    assert result["excluded_at"] == 100
