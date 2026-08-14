"""The streamed CSV export: its columns, its rows, and the job it reports through.

The export used to load every row, validate them all, render one string and send
it — four copies of the same data in memory, which on a multi-million-row sensor
is measured in gigabytes. It now walks the table in `_id`-ordered batches. What
matters is that the file did not change while the memory profile did, so these
pin the header, the per-row shape and the paging predicate.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import android as android_router
from app.schemas import AndroidAccelerometerSchema
from app.services import backup_jobs

DEVICE = "phone-a"


def sensor_row(_id, timestamp, **values):
    from types import SimpleNamespace

    return SimpleNamespace(
        _id=_id,
        timestamp=timestamp,
        device_id=DEVICE,
        double_values_0=values.get("x", 0.0),
        double_values_1=values.get("y", 0.0),
        double_values_2=values.get("z", 0.0),
        accuracy=values.get("accuracy", 0),
        label=values.get("label"),
    )


def test_the_header_comes_from_the_schema_not_the_first_row():
    """It has to be written before any row is read, so it cannot be derived from
    one. device_id is left out because the file is already per-device."""
    fields = android_router._export_fields(AndroidAccelerometerSchema)
    assert fields[0] == "id"
    assert fields[1] == "timestamp"
    assert "device_id" not in fields
    assert fields == [
        "id",
        "timestamp",
        "double_values_0",
        "double_values_1",
        "double_values_2",
        "accuracy",
        "label",
    ]


def test_a_row_is_rendered_with_a_readable_timestamp_and_no_device():
    row = sensor_row(7, 1_785_929_738_186, x=1.5, label="here")
    record = android_router._export_row(row, AndroidAccelerometerSchema)

    assert record["id"] == 7
    assert record["timestamp"] == "2026-08-05 11:35:38 UTC"
    assert "device_id" not in record
    assert record["double_values_0"] == 1.5
    assert record["label"] == "here"


def test_a_seconds_timestamp_is_read_as_seconds():
    """Sensor tables have historically held seconds as well as milliseconds."""
    record = android_router._export_row(
        sensor_row(1, 1_785_929_738), AndroidAccelerometerSchema
    )
    assert record["timestamp"] == "2026-08-05 11:35:38 UTC"


def test_an_unknown_sensor_is_refused_before_any_query():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as raised:
        android_router._export_window("not-a-sensor", None, None)
    assert raised.value.status_code == 404


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else 0


class _BatchSession:
    """Answers each batch from a scripted list, recording the paging predicate."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.statements = []

    async def execute(self, query):
        self.statements.append(str(query))
        return _Result(self.batches.pop(0) if self.batches else [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


@pytest.mark.asyncio
async def test_the_stream_pages_by_id_and_renders_every_batch(monkeypatch):
    first = [sensor_row(1, 1_785_929_738_186, x=1.0), sensor_row(2, 1_785_929_738_206, x=2.0)]
    second = [sensor_row(9, 1_785_929_738_226, x=3.0)]
    session = _BatchSession([first, second, []])
    monkeypatch.setattr(android_router, "AndroidSessionLocal", lambda: session)

    model, schema, from_ts, to_ts = android_router._export_window("accelerometer", None, None)
    chunks = [
        chunk
        async for chunk in android_router._stream_export(
            DEVICE, "accelerometer", model, schema, from_ts, to_ts, None
        )
    ]
    csv_text = "".join(chunks)

    assert csv_text.startswith("id,timestamp,double_values_0")
    assert csv_text.count("\r\n") == 4  # header plus three rows
    assert "1.0" in csv_text and "2.0" in csv_text and "3.0" in csv_text
    # The second batch must resume past the last id of the first, not re-read it.
    assert "_id > " in session.statements[1] or ">" in session.statements[1]


@pytest.mark.asyncio
async def test_the_stream_reports_rows_into_its_job(monkeypatch):
    session = _BatchSession([[sensor_row(1, 1_785_929_738_186)] * 3, []])
    monkeypatch.setattr(android_router, "AndroidSessionLocal", lambda: session)
    job = backup_jobs.create("export-csv")
    backup_jobs.advance(job, total=3)

    model, schema, from_ts, to_ts = android_router._export_window("accelerometer", None, None)
    async for _ in android_router._stream_export(
        DEVICE, "accelerometer", model, schema, from_ts, to_ts, job
    ):
        pass

    snapshot = job.snapshot()
    assert snapshot["state"] == backup_jobs.DONE
    assert snapshot["percent"] == 100.0


@pytest.mark.asyncio
async def test_a_failure_mid_stream_lands_on_the_job(monkeypatch):
    """Once the body has begun the status code is fixed, so the job carries it."""

    class _Broken(_BatchSession):
        async def execute(self, query):
            raise RuntimeError("connection lost")

    monkeypatch.setattr(android_router, "AndroidSessionLocal", lambda: _Broken([]))
    job = backup_jobs.create("export-csv")

    model, schema, from_ts, to_ts = android_router._export_window("accelerometer", None, None)
    with pytest.raises(RuntimeError):
        async for _ in android_router._stream_export(
            DEVICE, "accelerometer", model, schema, from_ts, to_ts, job
        ):
            pass

    assert job.snapshot()["state"] == backup_jobs.ERROR
    assert "connection lost" in job.snapshot()["error"]


def test_a_download_will_not_report_into_someone_elses_job():
    """The job id comes from the query string, so it is whatever the caller put
    there. Advancing a backup import from a CSV download would tell the backup
    page that an import had finished while it was still running."""
    import_job = backup_jobs.create("import")
    backup_jobs.advance(import_job, total=1000, done=100, phase="Merging into the databases")

    assert android_router._progress_job(import_job.id, "accelerometer") is None
    assert import_job.state == backup_jobs.RUNNING
    assert import_job.phase == "Merging into the databases"


def test_a_download_reports_into_its_own_job():
    job = backup_jobs.create("export-csv")
    backup_jobs.describe(job, sensor="accelerometer")
    assert android_router._progress_job(job.id, "accelerometer") is job


def test_a_job_for_a_different_sensor_is_not_accepted():
    job = backup_jobs.create("export-csv")
    backup_jobs.describe(job, sensor="accelerometer")
    assert android_router._progress_job(job.id, "gyroscope") is None


def test_an_unknown_or_absent_job_id_simply_means_no_reporting():
    assert android_router._progress_job("deadbeef", "accelerometer") is None
    assert android_router._progress_job(None, "accelerometer") is None


def test_progress_stops_claiming_a_percentage_once_the_estimate_is_passed():
    """The total is a row count from the record-count cache, which lags whatever
    arrived since its last refresh. Pinning the bar at 100% would tell a
    researcher the download had finished while it was still being written."""
    job = backup_jobs.create("export-zip")
    backup_jobs.advance(job, total=1000, done=500)
    assert job.snapshot()["percent"] == 50.0

    backup_jobs.advance(job, done=1500)
    assert job.snapshot()["percent"] is None
    assert job.snapshot()["done"] == 1500  # still moving, still reported


def test_a_finished_job_reads_as_complete_even_after_overrunning():
    job = backup_jobs.create("export-zip")
    backup_jobs.advance(job, total=1000, done=1500)
    assert job.snapshot()["percent"] is None

    backup_jobs.finish(job)
    assert job.snapshot()["percent"] == 100.0
    assert job.snapshot()["state"] == backup_jobs.DONE


@pytest.mark.asyncio
async def test_abandoning_a_download_marks_its_job_cancelled(monkeypatch):
    """Closing a streaming response raises GeneratorExit, which is a
    BaseException and so slips past `except Exception`. Without the finally the
    record would read as running until it aged out, and the page watching it
    would spin for a quarter of an hour over a download the user stopped."""
    session = _BatchSession([[sensor_row(i, 1_785_929_738_186)] for i in range(1, 20)])
    monkeypatch.setattr(android_router, "AndroidSessionLocal", lambda: session)
    job = backup_jobs.create("export-csv")
    backup_jobs.advance(job, total=1000)

    model, schema, from_ts, to_ts = android_router._export_window("accelerometer", None, None)
    stream = android_router._stream_export(
        DEVICE, "accelerometer", model, schema, from_ts, to_ts, job
    )
    await stream.__anext__()  # header
    await stream.__anext__()  # one batch
    await stream.aclose()     # the reader goes away

    assert job.snapshot()["state"] == backup_jobs.CANCELLED
    assert job.snapshot()["phase"] == "Cancelled"


def test_cancelling_leaves_an_already_finished_job_alone():
    job = backup_jobs.create("export-csv")
    backup_jobs.advance(job, total=10, done=10)
    backup_jobs.finish(job)

    backup_jobs.cancel(job)
    assert job.snapshot()["state"] == backup_jobs.DONE


def test_cancelling_leaves_a_failed_job_alone():
    job = backup_jobs.create("export-csv")
    backup_jobs.fail(job, "table is full")

    backup_jobs.cancel(job)
    assert job.snapshot()["state"] == backup_jobs.ERROR
    assert job.snapshot()["error"] == "table is full"


def test_an_unknown_job_is_a_404():
    with TestClient(app) as client:
        assert client.get("/jobs/does-not-exist").status_code == 404


def test_a_known_job_reports_its_snapshot():
    job = backup_jobs.create("export-csv")
    backup_jobs.advance(job, total=200, done=50, phase="Exporting accelerometer")
    with TestClient(app) as client:
        body = client.get(f"/jobs/{job.id}").json()
    assert body["percent"] == 25.0
    assert body["phase"] == "Exporting accelerometer"


@pytest.mark.asyncio
async def test_the_archive_is_produced_before_its_last_member_is_read():
    """The regression this guards against is silent and expensive.

    Nothing about a buffered archive looks wrong from the outside — the file is
    identical either way. It only shows up at study scale, as a request that
    holds a multi-gigabyte ZIP in memory before sending a single byte, which is
    the whole reason `_Sink` refuses to offer `seek`.

    So this asserts on timing rather than content: bytes must reach the caller
    while members are still being produced, not after the last one.
    """
    from app.routers import export as export_router

    produced: list[str] = []

    async def batches(name):
        for index in range(3):
            yield [{"timestamp": index}]

    async def members():
        for name in ("a.csv", "b.csv", "c.csv"):
            produced.append(name)
            yield (name, ["timestamp"], batches(name))

    seen_after: list[int] = []
    async for chunk in export_router._stream_archive(members()):
        if chunk:
            seen_after.append(len(produced))

    assert seen_after, "the archive yielded nothing at all"
    # The first bytes arrived while members were still being made.
    assert seen_after[0] < len(produced)


@pytest.mark.asyncio
async def test_a_manifest_reaches_the_caller_before_the_data_is_read():
    """A window changes which rows are read, not how the archive is assembled.

    The manifest is written first precisely so an interrupted download still
    says what it was, which only holds if it is *sent* before the rows are
    fetched rather than merely written first into a buffer.
    """
    from app.routers import export as export_router

    read_batches = 0

    async def batches():
        nonlocal read_batches
        for index in range(3):
            read_batches += 1
            yield [{"timestamp": index}]

    async def members():
        yield ("android_accelerometer.csv", ["timestamp"], batches())

    batches_when_first_chunk_arrived = None
    async for chunk in export_router._stream_archive(
        members(), None, export_router._export_manifest("all", (1000, 2000))
    ):
        if chunk and batches_when_first_chunk_arrived is None:
            batches_when_first_chunk_arrived = read_batches

    assert batches_when_first_chunk_arrived == 0
