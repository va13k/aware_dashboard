"""Series endpoint wiring over a stand-in session.

The SQL is not executed: a fake session returns canned grouped rows, so these
assert the bucket-index -> timestamp math and the response shape without MySQL.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import android as android_router
from app.services.series import MAX_WINDOW_MS, clamp_window


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]


class _FakeRow:
    def __init__(self, mapping):
        self._mapping = mapping


class _FakeSession:
    """Yields the same grouped rows for the aggregation query."""

    def __init__(self, mappings):
        self._mappings = mappings

    async def execute(self, _query):
        return _FakeResult([_FakeRow(m) for m in self._mappings])

    async def rollback(self):
        pass


@pytest.fixture
def client_with_rows():
    def make(mappings):
        async def session():
            yield _FakeSession(mappings)

        app.dependency_overrides[android_router.get_android_db] = session
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


def test_series_maps_buckets_to_evenly_spaced_timestamps(client_with_rows):
    # width = (2500 - 1000) / 3 = 500; t = from_ts + bucket * width
    rows = [
        {"bucket": 0, "n": 3, "avg": 1.5, "lo": 1.0, "hi": 2.0},
        {"bucket": 2, "n": 5, "avg": 3.0, "lo": 2.5, "hi": 3.5},
    ]
    client = client_with_rows(rows)

    resp = client.get(
        "/android/dev-1/accelerometer/series",
        params={"from_ts": 1000, "to_ts": 2500, "buckets": 3},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert [b["t"] for b in data] == [1000.0, 2000.0]
    assert data[0] == {"t": 1000.0, "avg": 1.5, "lo": 1.0, "hi": 2.0, "n": 3}
    assert data[1]["n"] == 5


def test_series_404_for_non_series_sensor(client_with_rows):
    # `calls` is an event sensor with no plottable value column.
    client = client_with_rows([])
    resp = client.get("/android/dev-1/calls/series", params={"from_ts": 0, "to_ts": 10})
    assert resp.status_code == 404


# --- clamp_window: the step-1 bounded-scan guarantee ---------------------------

NOW = 1_700_000_000_000  # fixed "now" in epoch-ms so the tests are deterministic


def test_clamp_window_keeps_a_bounded_pair_untouched():
    frm, to = clamp_window(1000, 2500, now_ms=NOW)
    assert (frm, to) == (1000.0, 2500.0)


def test_clamp_window_missing_from_defaults_to_one_year_before_to():
    frm, to = clamp_window(None, NOW, now_ms=NOW)
    assert to == float(NOW)
    assert frm == float(NOW) - MAX_WINDOW_MS


def test_clamp_window_missing_to_anchors_to_now():
    frm, to = clamp_window(None, None, now_ms=NOW)
    assert to == float(NOW)
    assert frm == float(NOW) - MAX_WINDOW_MS


def test_clamp_window_all_time_span_is_trimmed_to_one_year():
    # A device whose data spans three years must not scan all three.
    three_years = 3 * MAX_WINDOW_MS
    frm, to = clamp_window(NOW - three_years, NOW, now_ms=NOW)
    assert to - frm == MAX_WINDOW_MS
    assert to == float(NOW)


def test_clamp_window_swaps_reversed_bounds():
    frm, to = clamp_window(2500, 1000, now_ms=NOW)
    assert (frm, to) == (1000.0, 2500.0)
