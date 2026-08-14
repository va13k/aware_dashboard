"""The period offer both the export dialogs and the backup page read.

Availability used to be settled by probing the data tables for a single row per
window, and a data-anchored window was assumed available without asking. Now
every window is answered from the rollup, which means the offer carries a record
count and one code path serves both pages.

What is worth pinning down is that the two cannot drift, that a period with no
anchor stays unavailable rather than counting everything, and that a window is
offered as the absolute pair it resolves to.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import coverage as coverage_router
from app.services import coverage

NEWEST = 1_754_000_000_000.0


@pytest.fixture
def rollup(monkeypatch):
    """Lets a test say what each asked-for window holds, per platform."""
    holdings = {"android": 0, "ios": 0}
    asked: list[tuple] = []

    async def records_for_windows(db, model, windows, tables=None):
        platform = "ios" if "Ios" in model.__name__ else "android"
        asked.append((platform, tuple(windows)))
        return [holdings[platform]] * len(windows)

    async def newest_timestamp(db, model):
        return NEWEST

    monkeypatch.setattr(
        coverage_router.coverage_rollup, "records_for_windows", records_for_windows
    )
    monkeypatch.setattr(
        coverage_router.record_counts, "newest_timestamp", newest_timestamp
    )
    return holdings, asked


@pytest.fixture
def client(rollup):
    app = FastAPI()
    app.include_router(coverage_router.router)

    async def session():
        yield None

    app.dependency_overrides[coverage_router.get_android_db] = session
    app.dependency_overrides[coverage_router.get_ios_db] = session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def window(body, anchor, period):
    return next(
        entry
        for entry in body["windows"]
        if entry["anchor"] == anchor and entry["period"] == period
    )


def test_every_period_is_offered_against_both_anchors(client):
    body = client.get("/coverage/windows").json()

    assert len(body["windows"]) == len(coverage.PERIODS) * 2
    assert {entry["anchor"] for entry in body["windows"]} == {"data", "now"}


def test_a_relative_period_is_offered_as_the_instants_it_resolves_to(client):
    """A choice whose starting point is invisible cannot be reproduced later."""
    body = client.get("/coverage/windows").json()
    hour = window(body, "data", "hour")

    assert hour["to"] == NEWEST
    assert hour["from"] == NEWEST - coverage.HOUR_MS


def test_a_window_carries_what_it_holds(client, rollup):
    holdings, _ = rollup
    holdings["android"], holdings["ios"] = 30, 12

    hour = window(client.get("/coverage/windows").json(), "data", "hour")

    assert hour["records"] == 42
    assert hour["platforms"] == {"android": 30, "ios": 12}
    assert hour["available"] is True


def test_an_empty_period_is_offered_as_unavailable(client, rollup):
    """The page greys it out, which is the case the old table probe was slowest
    at: it walked every table before concluding nothing was there."""
    holdings, _ = rollup
    holdings["android"] = holdings["ios"] = 0

    assert window(client.get("/coverage/windows").json(), "now", "hour")["available"] is False


def test_every_bounded_window_is_asked_in_one_read_per_platform(client, rollup):
    """Ten periods asked one at a time is ten aggregates per platform."""
    _, asked = rollup
    client.get("/coverage/windows")

    assert len(asked) == 2
    assert {platform for platform, _ in asked} == {"android", "ios"}
    assert all(len(windows) == len(coverage.PERIODS) * 2 for _, windows in asked)


def test_a_period_with_no_anchor_is_unavailable_rather_than_everything(monkeypatch):
    """With nothing stored there is no newest row to count back from. Such a
    window has no bounds, and a boundless window read as `all time` would
    report the whole study as available on an empty database."""

    async def nothing_stored(db, model):
        return None

    async def records_for_windows(db, model, windows, tables=None):
        # The clock-anchored periods still have bounds and are fair to ask
        # about. A boundless one reaching the rollup would count everything.
        assert all(
            start is not None and end is not None for start, end in windows
        ), windows
        return [0] * len(windows)

    monkeypatch.setattr(coverage_router.record_counts, "newest_timestamp", nothing_stored)
    monkeypatch.setattr(
        coverage_router.coverage_rollup, "records_for_windows", records_for_windows
    )

    app = FastAPI()
    app.include_router(coverage_router.router)

    async def session():
        yield None

    app.dependency_overrides[coverage_router.get_android_db] = session
    app.dependency_overrides[coverage_router.get_ios_db] = session

    with TestClient(app) as test_client:
        body = test_client.get("/coverage/windows").json()

    data_anchored = [e for e in body["windows"] if e["anchor"] == "data"]
    assert data_anchored
    assert all(entry["from"] is None for entry in data_anchored)
    assert all(entry["available"] is False for entry in data_anchored)
    assert all(entry["records"] == 0 for entry in data_anchored)


def test_the_offer_says_it_is_hour_granular(client):
    assert client.get("/coverage/windows").json()["hour_granular"] is True
