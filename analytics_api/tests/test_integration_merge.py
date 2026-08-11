"""The merge import, against a real MySQL.

The rest of the suite hands the code a stand-in session that answers from
whatever the test wrote into it. That is fast and it covers logic, but it can
only ever confirm what the author already imagined — which is how a deduplication
bug reached the server: every stand-in returned a sensible `last_ts`, and the
deployed table held 0 in all 77 rows.

These run against a MySQL of their own (see the `mysql_server` fixture), so the
answers come from the database rather than from the test. They are slow enough
to be opt-in: `pytest -m integration`.
"""

import gzip
import os
import subprocess

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import AndroidRecordCount
from app.routers import backup as backup_router
from app.routers.counts import ANDROID_SOURCES
from app.services import backup_jobs, dump_stream, watermarks

pytestmark = pytest.mark.integration

DEVICE = "phone-a"


@pytest_asyncio.fixture
async def android_session(clean_databases):
    """A session pointed at the throwaway server's android database."""
    engine = create_async_engine(clean_databases.url("aware_android"))
    yield (
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
        clean_databases,
    )
    await engine.dispose()


def seed_accelerometer(server, rows):
    values = ",".join(f"({ts},'{DEVICE}',{x})" for ts, x in rows)
    server.run(
        "INSERT INTO accelerometer (timestamp, device_id, double_values_0) "
        f"VALUES {values}",
        "aware_android",
    )


def count(server, table="accelerometer") -> int:
    return int(server.run(f"SELECT COUNT(*) FROM `{table}`", "aware_android").strip())


@pytest.mark.asyncio
async def test_a_zero_last_ts_does_not_switch_deduplication_off(android_session):
    """The bug that reached the server.

    `last_ts` joined `record_counts` after the table already existed, and the
    incremental refresh only rewrites a row when new data arrives for that phone,
    so a phone that stopped uploading keeps 0 forever. Read as a watermark, 0
    means "skip nothing", and a merge silently duplicates everything.
    """
    sessionmaker_, server = android_session
    seed_accelerometer(server, [(100, 1.0), (200, 2.0)])
    server.run(
        "INSERT INTO record_counts (sensor, device_id, count, last_id, last_ts) "
        f"VALUES ('accelerometer','{DEVICE}',2,2,0)",
        "aware_android",
    )

    async with sessionmaker_() as db:
        marks = await watermarks.build(
            db, "aware_android", AndroidRecordCount, ANDROID_SOURCES
        )

    # The cache says 0. The table says 200. The table wins.
    assert marks[("aware_android", "accelerometer")] == {DEVICE: 200.0}


@pytest.mark.asyncio
async def test_a_usable_cache_entry_is_still_trusted(android_session):
    """The fallback must not swallow the fast path it exists to protect."""
    sessionmaker_, server = android_session
    seed_accelerometer(server, [(100, 1.0), (200, 2.0)])
    server.run(
        "INSERT INTO record_counts (sensor, device_id, count, last_id, last_ts) "
        f"VALUES ('accelerometer','{DEVICE}',2,2,150)",
        "aware_android",
    )

    async with sessionmaker_() as db:
        marks = await watermarks.build(
            db, "aware_android", AndroidRecordCount, ANDROID_SOURCES
        )

    assert marks[("aware_android", "accelerometer")] == {DEVICE: 150.0}


@pytest.mark.asyncio
async def test_an_empty_table_yields_no_watermark_so_everything_is_admitted(
    android_session,
):
    sessionmaker_, _ = android_session
    async with sessionmaker_() as db:
        marks = await watermarks.build(
            db, "aware_android", AndroidRecordCount, ANDROID_SOURCES
        )
    assert ("aware_android", "accelerometer") not in marks


def dump(server, tmp_path, ranged=False):
    """A real mysqldump of the throwaway server, gzipped as the page produces it."""
    command = [
        "mysqldump",
        f"--socket={server.socket_path}",
        "-uroot",
        "--single-transaction",
    ]
    env = {**os.environ, "MYSQL_PWD": server.password}
    if ranged:
        command.append("--where=timestamp >= 0 AND timestamp <= 9999")
        command += [
            f"--ignore-table={db}.record_counts" for db in ("aware_android", "aware_ios")
        ]
    command += ["--databases", "aware_android", "aware_ios"]
    produced = subprocess.run(command, capture_output=True, timeout=300, env=env)
    assert produced.returncode == 0, produced.stderr.decode()[-500:]
    path = tmp_path / "backup.sql.gz"
    path.write_bytes(gzip.compress(produced.stdout))
    return path


@pytest.mark.asyncio
async def test_merging_a_backup_of_the_same_rows_adds_nothing(
    android_session, tmp_path, monkeypatch
):
    """Re-reading a backup must be a no-op, or a mistaken second import doubles
    the study's data with no way back short of a restore."""
    sessionmaker_, server = android_session
    seed_accelerometer(server, [(100, 1.0), (200, 2.0), (300, 3.0)])
    archive = dump(server, tmp_path)

    monkeypatch.setattr(backup_router, "MYSQL_HOST", "127.0.0.1")
    monkeypatch.setattr(backup_router, "MYSQL_PORT", str(server.port))
    monkeypatch.setattr(backup_router, "MYSQL_USER", "root")
    monkeypatch.setattr(backup_router, "MYSQL_PASSWORD", server.password)

    async with sessionmaker_() as db:
        marks = await watermarks.build(
            db, "aware_android", AndroidRecordCount, ANDROID_SOURCES
        )

    job = backup_jobs.create("import")
    backup_router._feed_mysql(job, archive, dump_stream.MERGE, marks)

    assert count(server) == 3
    assert job.snapshot()["rows_added"] == 0
    assert job.snapshot()["rows_skipped"] >= 3


@pytest.mark.asyncio
async def test_a_merge_adds_newer_rows_and_leaves_stored_ones_alone(
    android_session, tmp_path, monkeypatch
):
    sessionmaker_, server = android_session
    seed_accelerometer(server, [(100, 1.0), (200, 2.0), (300, 3.0)])
    archive = dump(server, tmp_path)

    # The target now holds only the older part of what the backup carries.
    server.run("DELETE FROM accelerometer WHERE timestamp > 100", "aware_android")
    assert count(server) == 1

    monkeypatch.setattr(backup_router, "MYSQL_HOST", "127.0.0.1")
    monkeypatch.setattr(backup_router, "MYSQL_PORT", str(server.port))
    monkeypatch.setattr(backup_router, "MYSQL_USER", "root")
    monkeypatch.setattr(backup_router, "MYSQL_PASSWORD", server.password)

    async with sessionmaker_() as db:
        marks = await watermarks.build(
            db, "aware_android", AndroidRecordCount, ANDROID_SOURCES
        )

    job = backup_jobs.create("import")
    backup_router._feed_mysql(job, archive, dump_stream.MERGE, marks)

    assert count(server) == 3
    stored = server.run(
        "SELECT timestamp FROM accelerometer ORDER BY timestamp", "aware_android"
    ).split()
    assert [float(value) for value in stored] == [100.0, 200.0, 300.0]


def test_a_period_export_fails_unless_the_count_cache_is_left_out(
    clean_databases, tmp_path
):
    """`record_counts` has no `timestamp`, so a global --where cannot apply to it.
    The --ignore-table flags are load-bearing, not defensive."""
    seed_accelerometer(clean_databases, [(100, 1.0)])

    without = subprocess.run(
        [
            "mysqldump",
            f"--socket={clean_databases.socket_path}",
            "-uroot",
            "--single-transaction",
            "--where=timestamp >= 0 AND timestamp <= 9999",
            "--databases",
            "aware_android",
        ],
        capture_output=True,
        timeout=300,
        env={**os.environ, "MYSQL_PWD": clean_databases.password},
    )
    assert without.returncode != 0
    assert b"Unknown column 'timestamp'" in without.stderr

    # And it succeeds once the cache is excluded, which is what the router does.
    dump(clean_databases, tmp_path, ranged=True)
