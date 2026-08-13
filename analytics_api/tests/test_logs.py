"""Log endpoints over a stand-in session.

The SQL is not executed: a fake session returns canned ORM-ish rows and a canned
count, so these assert the response shape, filtering plumbing and CSV rendering
without MySQL.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import logs as logs_router
from app.schemas import AwareLogSchema


class _Row:
    """Enough of an AndroidAwareLog row for the schema to validate it."""

    def __init__(self, _id, timestamp, device_id, log_type, log_message):
        self._id = _id
        self.timestamp = timestamp
        self.device_id = device_id
        self.log_type = log_type
        self.log_message = log_message


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar(self):
        return len(self._rows)

    def all_tuples(self):
        return [(r,) for r in self._rows]


class _FakeSession:
    """Returns the canned rows for row queries and their count for COUNT()."""

    def __init__(self, rows, log_types):
        self._rows = rows
        self._log_types = log_types

    async def execute(self, query):
        text = str(query).lower()
        if "count(" in text:
            return _CountResult(len(self._rows))
        if "distinct" in text:
            return _TupleResult([(t,) for t in self._log_types])
        return _ScalarResult(self._rows)

    async def rollback(self):
        pass


class _CountResult:
    def __init__(self, n):
        self._n = n

    def scalar(self):
        return self._n


class _TupleResult:
    def __init__(self, tuples):
        self._tuples = tuples

    def all(self):
        return self._tuples


@pytest.fixture
def client():
    rows = [
        _Row(3, 3000.0, "dev-1", "sync", "STUDY-SYNC: installations"),
        _Row(2, 2000.0, "dev-1", "lifecycle", "Aware-starting"),
    ]

    async def session():
        yield _FakeSession(rows, ["diagnostics", "lifecycle", "sync"])

    app.dependency_overrides[logs_router.get_android_db] = session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_returns_total_and_rows(client):
    resp = client.get("/logs/android", params={"device_id": "dev-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert [r["log_type"] for r in body["rows"]] == ["sync", "lifecycle"]
    assert body["rows"][0]["log_message"] == "STUDY-SYNC: installations"


def test_log_types_lists_distinct_values(client):
    resp = client.get("/logs/android/log-types")
    assert resp.status_code == 200
    assert resp.json() == ["diagnostics", "lifecycle", "sync"]


def test_export_renders_csv_with_formatted_timestamp(client):
    resp = client.get("/logs/android/export", params={"device_id": "dev-1"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="android_logs_dev-1.csv"' in resp.headers["content-disposition"]
    text = resp.text
    assert "id,timestamp,device_id,log_type,log_message" in text
    assert "STUDY-SYNC: installations" in text
    # epoch-ms 3000 is tiny, so it is treated as seconds → 1970 UTC
    assert "1970-01-01" in text


def test_both_platforms_answer_with_the_same_fields():
    """The page renders one table for either platform, so the rows must match.

    An iPhone's log is a JSON blob and Android's is a set of columns; they only
    look alike because the iOS route projects through the same schema. Building
    that dictionary by hand once shipped `_id` where the page reads `id`, and the
    table crashed on its first row.
    """

    class Record:
        _id = 11
        timestamp = 1_700_000_000_000.0
        device_id = "phone-a"
        data = {"log_message": '{"class": "AWARECore", "event": "sync"}'}

    ios_row = logs_router._ios_row((Record(), "AWARECore"))
    android_row = AwareLogSchema.model_validate(
        {
            "_id": 11,
            "timestamp": 1_700_000_000_000.0,
            "device_id": "phone-a",
            "log_type": "sync",
            "log_message": "anything",
        }
    ).model_dump()

    assert ios_row.keys() == android_row.keys()
    assert ios_row["id"] == 11
    assert ios_row["log_type"] == "AWARECore"
    assert ios_row["log_message"] == '{"class": "AWARECore", "event": "sync"}'


def test_a_log_message_that_is_not_json_still_yields_its_text():
    class Record:
        _id = 3
        timestamp = 1.0
        device_id = "phone-a"
        data = {"log_message": "plain text, no braces"}

    row = logs_router._ios_row((Record(), None))

    assert row["log_message"] == "plain text, no braces"
    assert row["log_type"] == ""


def test_a_row_with_no_payload_does_not_break_the_page():
    class Record:
        _id = 4
        timestamp = 1.0
        device_id = "phone-a"
        data = None

    row = logs_router._ios_row((Record(), None))

    assert row["id"] == 4
    assert row["log_message"] == ""
