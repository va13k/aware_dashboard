"""Recording that a participant has left.

Withdrawal is two halves enforced in different places: the phone stops
collecting, and the server stops expecting. This covers the server's half — the
enrolment window closing — which is what the coverage grid, the exports and the
counts all read.

The case that decides the design is a withdrawal reported late. A researcher is
usually told after the fact, so the moment recorded has to be when the participant
*acted*, not when anyone found out. Stamp it on arrival instead and every bucket in
between reads as expected-and-missing on a grid the participant had already left.

A rejoin after quitting is why the window to close has to be chosen rather than
assumed: a device with three windows has two already shut, and the one covering the
withdrawal is the only one that may move.
"""

import pytest
from sqlalchemy import BigInteger, Column, String
from sqlalchemy.orm import declarative_base

from app.services import enrolment

_Base = declarative_base()


class _Model(_Base):
    """A stand-in for AndroidDeviceEnrolment.

    `close_window` builds an update against the table, and the real model
    carries a whole platform's schema with it.
    """

    __tablename__ = "device_enrolment"
    device_id = Column(String(150), primary_key=True)
    joined_at = Column(BigInteger, primary_key=True)
    left_at = Column(BigInteger, nullable=True)
    join_source = Column(String(16))
    left_source = Column(String(16), nullable=True)

DEVICE = "phone-a"
HOUR = 3_600_000
DAY = 24 * HOUR
#: 1 August 2026, UTC.
JOINED = 1_785_542_400_000


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
    """Answers the window read, and records the update it is asked to perform."""

    def __init__(self, rows, fail=False):
        self.rows = rows
        self.updates = []
        self.deletes = 0
        self.committed = 0
        self.fail = fail

    async def execute(self, statement):
        if self.fail:
            from sqlalchemy.exc import SQLAlchemyError

            raise SQLAlchemyError("write refused")
        text = str(statement)
        if text.startswith("UPDATE"):
            self.updates.append(statement.compile().params)
        elif text.startswith("DELETE"):
            self.deletes += 1
        return _Result(self.rows)

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_a_withdrawal_closes_the_open_window():
    session = _Session([_Row(DEVICE, JOINED)])

    stored = await enrolment.close_window(
        session, _Model, DEVICE, JOINED + 5 * DAY
    )

    assert stored["left_at"] == JOINED + 5 * DAY
    assert stored["joined_at"] == JOINED
    assert session.committed == 1


@pytest.mark.asyncio
async def test_a_late_notice_lands_on_the_day_the_participant_acted():
    """The whole reason the moment is supplied rather than stamped on arrival."""
    session = _Session([_Row(DEVICE, JOINED)])
    acted = JOINED + 2 * DAY

    stored = await enrolment.close_window(session, _Model, DEVICE, acted)

    assert stored["left_at"] == acted
    assert session.updates[0]["left_at"] == acted


@pytest.mark.asyncio
async def test_the_window_covering_the_withdrawal_is_the_one_that_closes():
    """A device that quit and came back has windows already shut behind it, and
    only the one the withdrawal falls in may move."""
    session = _Session(
        [
            _Row(DEVICE, JOINED, JOINED + DAY),
            _Row(DEVICE, JOINED + 2 * DAY, JOINED + 3 * DAY),
            _Row(DEVICE, JOINED + 4 * DAY),
        ]
    )

    stored = await enrolment.close_window(
        session, _Model, DEVICE, JOINED + 6 * DAY
    )

    assert stored["joined_at"] == JOINED + 4 * DAY


@pytest.mark.asyncio
async def test_a_withdrawal_backdated_into_a_closed_window_closes_that_one():
    """A researcher told weeks later that somebody left in the first spell."""
    session = _Session(
        [
            _Row(DEVICE, JOINED, JOINED + 3 * DAY),
            _Row(DEVICE, JOINED + 5 * DAY),
        ]
    )

    stored = await enrolment.close_window(session, _Model, DEVICE, JOINED + DAY)

    assert stored["joined_at"] == JOINED
    assert stored["left_at"] == JOINED + DAY


@pytest.mark.asyncio
async def test_a_withdrawal_before_the_device_ever_joined_closes_nothing():
    session = _Session([_Row(DEVICE, JOINED)])

    assert await enrolment.close_window(session, _Model, DEVICE, JOINED - DAY) is None
    assert session.updates == []


@pytest.mark.asyncio
async def test_a_device_with_no_window_has_nothing_to_withdraw_from():
    session = _Session([])

    assert await enrolment.close_window(session, _Model, DEVICE, JOINED) is None


@pytest.mark.asyncio
async def test_a_closed_window_is_marked_manual_so_the_derivation_leaves_it():
    """Otherwise the next refresh rebuilds the window from the study log and
    reopens what a researcher just closed."""
    session = _Session([_Row(DEVICE, JOINED)])

    stored = await enrolment.close_window(session, _Model, DEVICE, JOINED + DAY)

    assert stored["left_source"] == enrolment.MANUAL
    # Recording a withdrawal must not rewrite how the join was established.
    assert stored["join_source"] == enrolment.STUDY_EVENT
    assert session.updates[0]["left_source"] == enrolment.MANUAL


@pytest.mark.asyncio
async def test_a_manual_withdrawal_date_can_be_moved_later():
    """The device page calls this "Change the date", so both directions work."""
    session = _Session(
        [
            _Row(
                DEVICE,
                JOINED,
                JOINED + DAY,
                enrolment.STUDY_EVENT,
                enrolment.MANUAL,
            )
        ]
    )

    stored = await enrolment.close_window(session, _Model, DEVICE, JOINED + 2 * DAY)

    assert stored["left_at"] == JOINED + 2 * DAY


@pytest.mark.asyncio
async def test_a_failed_write_reports_failure_rather_than_claiming_success():
    session = _Session([_Row(DEVICE, JOINED)], fail=True)

    assert await enrolment.close_window(session, _Model, DEVICE, JOINED + DAY) is None


@pytest.mark.asyncio
async def test_reopening_hands_the_device_back_to_the_study_log():
    """Undoing a mistake clears the manual marks, so the derivation rebuilds the
    windows from the phone's own account instead of leaving them frozen."""
    session = _Session([_Row(DEVICE, JOINED, JOINED + DAY, enrolment.MANUAL, enrolment.MANUAL)])

    assert await enrolment.reopen(session, _Model, DEVICE) is True
    assert session.deletes == 1
    assert session.committed == 1
