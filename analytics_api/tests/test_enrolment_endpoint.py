"""What the device endpoints report about enrolment.

The windows are read from the table rather than re-derived per request, so what
matters here is the reading: one query for a whole device list, the span a row
shows, and the state a researcher has to be able to see — a device that wrote
data the study never recorded a join for.

The derivation that fills the table is test_enrolment.py's subject.
"""

import pytest

from app.routers import devices as devices_router
from app.services import enrolment

DEVICE = "ca14d3f3-0000-4000-8000-000000000001"
OTHER_DEVICE = "ca14d3f3-0000-4000-8000-000000000002"


class _Row:
    def __init__(self, device_id, joined_at, left_at=None, join_source=None, left_source=None):
        self.device_id = device_id
        self.joined_at = joined_at
        self.left_at = left_at
        self.join_source = join_source or enrolment.STUDY_EVENT
        self.left_source = left_source


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _Session:
    """Answers the window query, and counts how often it was asked."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = 0

    async def execute(self, _query):
        self.queries += 1
        return _Result(self.rows)


@pytest.mark.asyncio
async def test_a_whole_device_list_costs_one_query():
    """The alternative is re-parsing the study log per device on every request,
    which is what storing the windows is for."""
    session = _Session(
        [
            _Row(DEVICE, 1_000, 5_000),
            _Row(DEVICE, 9_000),
            _Row(OTHER_DEVICE, 2_000),
        ]
    )

    windows = await devices_router._enrolment_windows(session)

    assert session.queries == 1
    assert list(windows) == [DEVICE, OTHER_DEVICE]
    assert len(windows[DEVICE]) == 2


@pytest.mark.asyncio
async def test_a_window_carries_how_its_start_was_established():
    session = _Session([_Row(DEVICE, 4_000, join_source=enrolment.FIRST_DATA)])

    (window,) = (await devices_router._enrolment_windows(session))[DEVICE]

    assert window == {
        "joined_at": 4_000,
        "left_at": None,
        "join_source": enrolment.FIRST_DATA,
        "left_source": None,
    }


@pytest.mark.asyncio
async def test_a_missing_table_reports_no_windows_rather_than_failing():
    """A deployment whose schema has not caught up still serves its device list."""

    class _Failing:
        async def execute(self, _query):
            raise devices_router.ProgrammingError("select", {}, Exception("no table"))

        async def rollback(self):
            return None

    assert await devices_router._enrolment_windows(_Failing()) == {}


def test_the_summary_spans_from_the_first_join_to_the_last_exit():
    """A phone that quit and came back is enrolled since it first joined and is
    still in the study. The gap lives in the windows, which the heatmap reads."""
    summary = devices_router._enrolment_summary(
        [
            {"joined_at": 1_000, "left_at": 5_000, "join_source": "study_event", "left_source": "study_event"},
            {"joined_at": 9_000, "left_at": None, "join_source": "study_event", "left_source": None},
        ]
    )

    assert summary["joined_at"] == 1_000
    assert summary["left_at"] is None
    assert summary["window_count"] == 2


def test_a_device_with_no_window_reports_none():
    """It wrote data the study never recorded a join for, and that is the state
    a researcher has to be able to pick out of the list."""
    assert devices_router._enrolment_summary([]) is None
    assert devices_router._enrolment_summary(None) is None
