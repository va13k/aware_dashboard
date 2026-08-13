"""The scheduler around the record-count refresh.

What matters here is the loop's behaviour rather than the counting, which
test_record_counts.py covers: a pass that fails must not stop the schedule, a
pass that runs long must not make the interval drift, a skipped pass must be
visible, and a completed pass must leave the heartbeat a healthcheck reads.
"""

import asyncio
import contextlib
import time

import pytest

from app import refresh_counts


class _Clock:
    """Collects what the loop would have slept, and stops it after N passes."""

    def __init__(self, stop_after: int):
        self.sleeps: list[float] = []
        self.stop_after = stop_after

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if len(self.sleeps) >= self.stop_after:
            raise asyncio.CancelledError


@pytest.fixture
def heartbeat(tmp_path, monkeypatch):
    path = tmp_path / "beats" / "heartbeat"
    monkeypatch.setenv(refresh_counts.HEARTBEAT_PATH_ENV, str(path))
    return path


def test_a_completed_pass_stamps_the_heartbeat(heartbeat, monkeypatch):
    async def passes(**_):
        return {"android": {}, "ios": {}}

    monkeypatch.setattr(refresh_counts, "refresh_all", passes)
    asyncio.run(refresh_counts.run_once())

    assert heartbeat.exists()
    assert float(heartbeat.read_text()) == pytest.approx(time.time(), abs=10)


def test_the_heartbeat_is_optional(monkeypatch):
    monkeypatch.delenv(refresh_counts.HEARTBEAT_PATH_ENV, raising=False)

    async def passes(**_):
        return {"android": {}, "ios": {}}

    monkeypatch.setattr(refresh_counts, "refresh_all", passes)
    assert asyncio.run(refresh_counts.run_once()) == {"android": {}, "ios": {}}


def test_a_failing_pass_does_not_stop_the_loop(monkeypatch, caplog):
    attempts = []

    async def fails_then_works():
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise RuntimeError("the database went away")
        return {"android": {}, "ios": {}}

    clock = _Clock(stop_after=3)
    monkeypatch.setattr(refresh_counts, "refresh_all", fails_then_works)
    monkeypatch.setattr(refresh_counts.asyncio, "sleep", clock.sleep)

    with caplog.at_level("INFO"), contextlib.suppress(asyncio.CancelledError):
        asyncio.run(refresh_counts.run_forever(60))

    assert len(attempts) == 3
    assert "the database went away" in caplog.text


@pytest.mark.parametrize(
    "work_seconds, expected_wait",
    [(40.0, 20.0), (300.0, 0.0), (0.0, 60.0)],
)
def test_the_wait_absorbs_how_long_the_pass_took(monkeypatch, work_seconds, expected_wait):
    """A pass is scheduled every interval, not every interval *plus* its own work.

    The event loop reads the same clock, so the fake advances only when the pass
    says it worked - a fixed sequence of readings would be consumed by asyncio
    itself.
    """
    now = 100.0

    async def works_for(*_):
        nonlocal now
        now += work_seconds
        return {"android": {}, "ios": {}}

    clock = _Clock(stop_after=1)
    monkeypatch.setattr(refresh_counts.time, "monotonic", lambda: now)
    monkeypatch.setattr(refresh_counts, "refresh_all", works_for)
    monkeypatch.setattr(refresh_counts.asyncio, "sleep", clock.sleep)

    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(refresh_counts.run_forever(60))

    assert clock.sleeps == [expected_wait]


def test_a_skipped_pass_is_reported_and_still_beats(heartbeat, monkeypatch, caplog):
    async def skipped():
        return {"skipped": True}

    monkeypatch.setattr(refresh_counts, "refresh_all", skipped)
    with caplog.at_level("INFO"):
        result = asyncio.run(refresh_counts.run_once())

    assert result == {"skipped": True}
    assert heartbeat.exists()


@pytest.mark.parametrize(
    "value, expected",
    [("60", 60), ("300", 300), ("0", 0), ("", 0), ("  90 ", 90), ("soon", 0)],
)
def test_the_interval_is_read_from_the_environment(monkeypatch, value, expected):
    monkeypatch.setenv(refresh_counts.INTERVAL_ENV, value)
    assert refresh_counts._configured_interval() == expected


def test_no_interval_means_a_single_pass(monkeypatch):
    monkeypatch.delenv(refresh_counts.INTERVAL_ENV, raising=False)
    assert refresh_counts._configured_interval() == 0
