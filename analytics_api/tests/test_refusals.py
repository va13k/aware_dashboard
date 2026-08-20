"""Writes the micro-server turned away, and why they need a record at all.

Everything else the dashboard shows about a device is read from rows that device
wrote. A refused write stores nothing, so a phone turned away at ingest is one the
dashboard has no other way to notice — the enrolment badge learns about an
unrecognised device from its data, and a refused device leaves none.

So the record is the only trace, and these check what it reports: totals over both
reasons, the empty-device row counted as an attempt but never as a device, the most
recent refusal first, and a deployment whose micro-server has never refused
anything reading as zero rather than as an error.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import ProgrammingError

from app.models import AndroidRefusal
from app.services import refusals


def _row(device_id, reason, attempts, rows_refused, first_seen, last_seen, table="accelerometer"):
    return SimpleNamespace(
        device_id=device_id,
        reason=reason,
        attempts=attempts,
        rows_refused=rows_refused,
        last_table=table,
        first_seen=first_seen,
        last_seen=last_seen,
    )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Session:
    """Answers the read, in whatever order the query asked for."""

    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.rolled_back = False

    async def execute(self, statement):
        self.statements.append(str(statement))
        return _Result(self.rows)

    async def rollback(self):
        self.rolled_back = True


class _MissingTableSession:
    """A deployment whose micro-server has never written the table."""

    def __init__(self):
        self.rolled_back = False

    async def execute(self, statement):
        raise ProgrammingError("SELECT", {}, Exception("table does not exist"))

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_totals_count_every_attempt_and_row():
    session = _Session(
        [
            _row("stranger", "no_enrolment", attempts=3, rows_refused=6, first_seen=10, last_seen=90),
            _row("other", "no_enrolment", attempts=1, rows_refused=2, first_seen=20, last_seen=40),
        ]
    )

    summary = await refusals.summary(session, AndroidRefusal)

    assert summary["attempts"] == 4
    assert summary["rows_refused"] == 8
    assert summary["devices"] == 2


@pytest.mark.asyncio
async def test_a_request_naming_no_device_is_an_attempt_but_not_a_device():
    """It is one row standing for every id-less request, so counting it as a
    device would report a participant that does not exist."""
    session = _Session(
        [
            _row("", "no_device_id", attempts=5, rows_refused=5, first_seen=10, last_seen=90),
            _row("stranger", "no_enrolment", attempts=1, rows_refused=1, first_seen=10, last_seen=20),
        ]
    )

    summary = await refusals.summary(session, AndroidRefusal)

    assert summary["attempts"] == 6
    assert summary["devices"] == 1


@pytest.mark.asyncio
async def test_the_most_recent_refusal_is_read_first():
    """Ordering is the query's, so the read has to ask for it: a study with a long
    history should open on what is happening now."""
    session = _Session([])

    await refusals.by_device(session, AndroidRefusal)

    assert "ORDER BY refusals.last_seen DESC" in session.statements[0]


@pytest.mark.asyncio
async def test_each_refusal_carries_what_it_means():
    session = _Session(
        [_row("stranger", "no_enrolment", attempts=1, rows_refused=1, first_seen=10, last_seen=20)]
    )

    reported = await refusals.by_device(session, AndroidRefusal)

    assert reported[0]["explanation"] == refusals.REASONS["no_enrolment"]
    assert reported[0]["last_table"] == "accelerometer"
    # Both ends are reported, which is what tells one afternoon from a week of
    # retries.
    assert reported[0]["first_seen"] == 10
    assert reported[0]["last_seen"] == 20


@pytest.mark.asyncio
async def test_an_unrecognised_reason_is_reported_as_itself():
    """A reason the micro-server learns before the dashboard does should still
    reach the screen, rather than being dropped for being unfamiliar."""
    session = _Session(
        [_row("stranger", "after_study_end", attempts=1, rows_refused=1, first_seen=1, last_seen=2)]
    )

    reported = await refusals.by_device(session, AndroidRefusal)

    assert reported[0]["explanation"] == "after_study_end"


@pytest.mark.asyncio
async def test_a_deployment_that_never_refused_anything_reports_zero():
    """The table is written by the ingest path, so its absence means nothing has
    been turned away — not that the read failed."""
    session = _MissingTableSession()

    summary = await refusals.summary(session, AndroidRefusal)

    assert summary == {
        "attempts": 0,
        "rows_refused": 0,
        "devices": 0,
        "refusals": [],
    }
    assert session.rolled_back
