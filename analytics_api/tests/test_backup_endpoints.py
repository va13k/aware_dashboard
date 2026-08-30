"""Backup routes and the job record behind them.

No MySQL and no subprocess: these cover the wiring the page depends on — the
shapes it polls, the file listing it offers, and the guards that reject a
request before any database work starts.
"""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import backup_jobs as jobs


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MYSQL_ROOT_PASSWORD", "test-password")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))

    import importlib

    from app.routers import backup as backup_module

    backup = importlib.reload(backup_module)
    app = FastAPI()
    app.include_router(backup.router)
    yield TestClient(app), backup, tmp_path

    importlib.reload(backup_module)


def test_the_file_listing_offers_finished_archives_newest_first(client):
    http, _, directory = client
    (directory / "aware-db-20260101-000000.sql.gz").write_bytes(b"one")
    (directory / "aware-db-20260202-000000.sql.gz").write_bytes(b"two-two")

    body = http.get("/backup/files").json()
    names = [entry["name"] for entry in body["files"]]
    assert names == ["aware-db-20260202-000000.sql.gz", "aware-db-20260101-000000.sql.gz"]
    assert body["files"][0]["size"] == 7


def test_a_half_written_archive_is_not_offered(client):
    """The scheduled dump writes to `.sql.gz.tmp` and renames on success, so a
    run still in flight must not appear as something to import."""
    http, _, directory = client
    (directory / "aware-db-20260101-000000.sql.gz.tmp").write_bytes(b"partial")

    assert http.get("/backup/files").json()["files"] == []


def test_a_missing_backup_directory_lists_nothing(client, tmp_path):
    http, backup, _ = client
    backup.BACKUP_DIR = tmp_path / "absent"
    assert http.get("/backup/files").json()["files"] == []


def test_an_archive_on_the_server_can_be_taken_off_it(client):
    """The scheduled dump's own copies, handed over rather than only restorable.

    They are the only backups a study has that nobody had to ask for, and a
    researcher leaving this server needs them off it.
    """
    http, _, directory = client
    (directory / "aware-db-20260101-000000.sql.gz").write_bytes(b"archived")

    response = http.get("/backup/files/aware-db-20260101-000000.sql.gz/download")

    assert response.status_code == 200
    assert response.content == b"archived"
    assert response.headers["content-type"] == "application/gzip"
    assert "aware-db-20260101-000000.sql.gz" in response.headers["content-disposition"]


def test_downloading_a_name_outside_the_backup_directory_is_refused(client):
    """The same guard the import path has: a name picks a file in BACKUP_DIR and
    cannot be made to leave it."""
    http, _, _ = client
    assert http.get("/backup/files/..%2F..%2Fetc%2Fpasswd/download").status_code == 404
    assert http.get("/backup/files/absent.sql.gz/download").status_code == 404


def test_an_unknown_import_mode_is_refused(client):
    http, _, _ = client
    response = http.post("/backup/import", data={"mode": "sideways"})
    assert response.status_code == 400
    assert "sideways" in response.json()["detail"]


def test_an_import_without_a_source_is_refused(client):
    http, _, _ = client
    response = http.post("/backup/import", data={"mode": "merge"})
    assert response.status_code == 400


def test_a_filename_outside_the_backup_directory_is_refused(client):
    """The name picks a file inside BACKUP_DIR and cannot be made to leave it."""
    http, _, _ = client
    response = http.post(
        "/backup/import", data={"mode": "merge", "filename": "../../etc/passwd"}
    )
    assert response.status_code == 404


def test_an_unknown_job_is_a_404(client):
    http, _, _ = client
    assert http.get("/backup/jobs/nothing-here").status_code == 404


def test_downloading_an_unknown_export_is_a_404(client):
    http, _, _ = client
    assert http.get("/backup/export/nothing-here/download").status_code == 404


def test_export_without_a_configured_password_reports_it(client, monkeypatch):
    http, backup, _ = client
    monkeypatch.setattr(backup, "MYSQL_PASSWORD", "")
    response = http.post("/backup/export")
    assert response.status_code == 503


def test_a_job_reports_a_percentage_once_a_total_is_known():
    job = jobs.create("import")
    assert job.snapshot()["percent"] is None

    jobs.advance(job, total=1000, done=250)
    assert job.snapshot()["percent"] == 25.0


def test_row_tallies_accumulate_across_batches():
    job = jobs.create("import")
    jobs.count_rows(job, "accelerometer", added=10, skipped=4)
    jobs.count_rows(job, "accelerometer", added=5, skipped=1)
    jobs.count_rows(job, "battery", added=2)

    snapshot = job.snapshot()
    assert snapshot["tables"]["accelerometer"] == {"added": 15, "skipped": 5}
    assert snapshot["rows_added"] == 17
    assert snapshot["rows_skipped"] == 5


def test_finishing_completes_the_bar_and_keeps_earlier_detail():
    job = jobs.create("export")
    jobs.describe(job, filename="aware-db.sql.gz")
    jobs.advance(job, total=500, done=120)
    jobs.finish(job, {"bytes": 400})

    snapshot = job.snapshot()
    assert snapshot["state"] == jobs.DONE
    assert snapshot["percent"] == 100.0
    assert snapshot["result"] == {"filename": "aware-db.sql.gz", "bytes": 400}


def test_a_failed_job_carries_its_reason():
    job = jobs.create("import")
    jobs.fail(job, "mysql: table is full")

    snapshot = job.snapshot()
    assert snapshot["state"] == jobs.ERROR
    assert snapshot["error"] == "mysql: table is full"
