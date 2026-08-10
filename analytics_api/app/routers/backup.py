"""Export and import of the AWARE databases.

Both run for long enough at study scale — a hundred phones over a couple of
months — that they are structured as jobs the backup page polls, rather than one
request held open until the work is done. Progress is measured in bytes: an
export against the dump's estimated size, an import against the compressed
file's, so the number moves smoothly and means something.

Neither direction stages the data on disk. The export compresses ``mysqldump``
output straight into the HTTP response, and the import decompresses into
``mysql`` as it reads, which is what keeps a hundred-gigabyte database viable
through a page. An import runs in one of two modes: ``replace`` restores the
dump as written, and ``merge`` folds its rows into what is already stored (see
services/dump_stream.py).
"""

import asyncio
import gzip
import io
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.database import AndroidSessionLocal, IosSessionLocal
from app.models import AndroidRecordCount, IosRecordCount
from app.routers.counts import ANDROID_SOURCES, IOS_SOURCES
from app.services import backup_jobs as jobs
from app.services import coverage, dump_stream, record_counts, watermarks

router = APIRouter(prefix="/backup", tags=["backup"])

DATABASES = ("aware_android", "aware_ios")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
MYSQL_USER = os.environ.get("MYSQL_BACKUP_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "")

#: Backups written by the scheduled dump, offered as import sources so a restore
#: does not have to travel through the browser. Anything ending in .sql.gz here
#: can be imported by name.
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backups"))

#: Ceiling on a browser upload. Files on BACKUP_DIR have no such limit — past a
#: few gigabytes an upload is the wrong transport regardless of the ceiling.
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 8 * 1024 * 1024 * 1024))

CHUNK = 1024 * 1024
#: Lines between job updates during an import. Each update takes a lock, and at
#: a million rows a second an update per line would cost more than the work.
PROGRESS_EVERY = 2000

_RETRIEVING = re.compile(r"Retrieving rows for table `?([^`.\s]+)`?", re.IGNORECASE)

#: Import tasks are held here for their lifetime; the event loop only keeps a
#: weak reference to a bare task and would be free to collect one mid-run.
_running: set[asyncio.Task] = set()


def _mysql_env() -> dict[str, str]:
    if not MYSQL_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MYSQL_ROOT_PASSWORD is not configured for backup operations",
        )
    env = os.environ.copy()
    env["MYSQL_PWD"] = MYSQL_PASSWORD
    return env


def _mysql_base_command(binary: str) -> list[str]:
    return [
        binary,
        f"--host={MYSQL_HOST}",
        f"--port={MYSQL_PORT}",
        f"--user={MYSQL_USER}",
    ]


async def _estimated_dump_bytes() -> int:
    """How much table data the dump will read, from the server's own statistics.

    InnoDB's DATA_LENGTH is an estimate, and the SQL text mysqldump writes is a
    different size again. It only has to be steady enough to make a percentage
    meaningful, and it is: both scale with the row count.
    """
    placeholders = ", ".join(f"'{name}'" for name in DATABASES)
    async with AndroidSessionLocal() as db:
        try:
            total = (
                await db.execute(
                    text(
                        "SELECT COALESCE(SUM(DATA_LENGTH), 0) FROM information_schema.TABLES "
                        f"WHERE TABLE_SCHEMA IN ({placeholders})"
                    )
                )
            ).scalar()
        except Exception:
            await db.rollback()
            return 0
    return int(total or 0)


def _session_for(database: str):
    return AndroidSessionLocal if database == "aware_android" else IosSessionLocal


async def _data_span() -> tuple[float | None, float | None]:
    """The oldest and newest timestamp across both platform databases."""
    oldest = newest = None
    for database in DATABASES:
        async with _session_for(database)() as db:
            tables = await coverage.timestamped_tables(db, database)
            low, high = await coverage.span(db, database, tables)
        if low is not None and (oldest is None or low < oldest):
            oldest = low
        if high is not None and (newest is None or high > newest):
            newest = high
    return oldest, newest


@router.get("/coverage")
async def export_coverage(
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
):
    """Which periods hold data, so the page only offers exports that yield rows.

    Windows ending at the newest stored row contain that row by construction, so
    they are known to be available without asking. The clock-anchored ones are
    the interesting case — on a quiet study they are empty, and that is what the
    page needs in order to grey them out.
    """
    now_ms = time.time() * 1000
    tables_by_database: dict[str, list[str]] = {}
    oldest = newest = None

    for database in DATABASES:
        async with _session_for(database)() as db:
            tables = await coverage.timestamped_tables(db, database)
            tables_by_database[database] = tables
            low, high = await coverage.span(db, database, tables)
        if low is not None and (oldest is None or low < oldest):
            oldest = low
        if high is not None and (newest is None or high > newest):
            newest = high

    async def available(start: float, end: float) -> bool:
        for database, tables in tables_by_database.items():
            async with _session_for(database)() as db:
                if await coverage.has_rows(db, database, tables, start, end):
                    return True
        return False

    offered = coverage.windows(newest, now_ms)
    for window in offered:
        if window["from"] is None:
            continue
        if window["anchor"] == coverage.DATA_ANCHOR:
            window["available"] = True
            continue
        window["available"] = await available(window["from"], window["to"])

    custom = None
    if from_ts is not None and to_ts is not None:
        start, end = (from_ts, to_ts) if from_ts <= to_ts else (to_ts, from_ts)
        custom = {"from": start, "to": end, "available": await available(start, end)}

    return {
        "now": now_ms,
        "oldest": oldest,
        "newest": newest,
        "total_bytes": await _estimated_dump_bytes(),
        "windows": offered,
        "custom": custom,
    }


def _watch_dump(stderr, job: jobs.Job) -> None:
    """Follow mysqldump's running commentary so the page can name the table."""
    for raw in iter(stderr.readline, b""):
        match = _RETRIEVING.search(raw.decode("utf-8", errors="replace"))
        if match:
            jobs.advance(job, phase=f"Exporting {match.group(1)}")


def _dump_command(start: float | None, end: float | None) -> list[str]:
    """The mysqldump invocation for a whole-database or a period export.

    Every AWARE data table carries `timestamp`, so one ``--where`` bounds them
    all. The count cache is the exception — it summarises rows rather than being
    one, and has no timestamp to filter on — so a period export leaves it out and
    the import's refresh rebuilds it from whatever arrives.
    """
    command = [
        *_mysql_base_command("mysqldump"),
        "--single-transaction",
        "--routines",
        "--triggers",
        "--verbose",
    ]
    if start is not None and end is not None:
        command.append(f"--where=timestamp >= {start:.0f} AND timestamp <= {end:.0f}")
        command += [
            f"--ignore-table={database}.{table}"
            for database in DATABASES
            for table in dump_stream.MERGE_SKIP_TABLES
        ]
    return [*command, "--databases", *DATABASES]


def _export_chunks(job: jobs.Job):
    """gzip-compressed dump bytes, produced as mysqldump writes them."""
    command = _dump_command(job.result.get("from_ts"), job.result.get("to_ts"))
    dump = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_mysql_env()
    )
    watcher = threading.Thread(target=_watch_dump, args=(dump.stderr, job), daemon=True)
    watcher.start()

    compressor = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
    try:
        while True:
            chunk = dump.stdout.read(CHUNK)
            if not chunk:
                break
            packed = compressor.compress(chunk)
            jobs.advance(job, add=len(chunk), out=len(packed))
            if packed:
                yield packed

        tail = compressor.flush()
        jobs.advance(job, out=len(tail))
        if tail:
            yield tail

        dump.stdout.close()
        watcher.join(timeout=5)
        if dump.wait() != 0:
            message = dump.stderr.read().decode("utf-8", errors="replace").strip()
            # The response is already streaming, so its status cannot change.
            # The job record is what the page is watching, and it carries this.
            jobs.fail(job, message or "Database export failed")
            return
        jobs.finish(job, {"bytes": job.bytes_out})
    except Exception as error:  # noqa: BLE001 - surfaced through the job record
        jobs.fail(job, str(error))
        raise
    finally:
        if dump.poll() is None:
            dump.kill()
        for pipe in (dump.stdout, dump.stderr):
            if pipe and not pipe.closed:
                pipe.close()


def _stamp(milliseconds: float) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).strftime("%Y%m%d")


async def _period_estimate(whole: int, start: float, end: float) -> int:
    """The whole-database estimate, scaled to the share of the span requested.

    Ingest is not perfectly even, so this is an approximation — enough to make a
    bar move at the right sort of pace, and the bar is capped at 100% for when
    it under-shoots.
    """
    oldest, newest = await _data_span()
    if oldest is None or newest is None or newest <= oldest:
        return whole
    overlap = min(end, newest) - max(start, oldest)
    if overlap <= 0:
        return 0
    return int(whole * min(1.0, overlap / (newest - oldest)))


@router.post("/export")
async def start_export(
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
):
    """Register the export, so the page can poll it while the file downloads.

    A period is applied when both bounds are given; otherwise the whole of both
    databases is exported, as before.
    """
    _mysql_env()
    ranged = from_ts is not None and to_ts is not None
    if ranged and to_ts < from_ts:
        from_ts, to_ts = to_ts, from_ts

    job = jobs.create("export")
    estimate = await _estimated_dump_bytes()
    if ranged:
        estimate = await _period_estimate(estimate, from_ts, to_ts)
        filename = f"aware-db-{_stamp(from_ts)}-to-{_stamp(to_ts)}.sql.gz"
    else:
        filename = f"aware-db-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.sql.gz"

    jobs.advance(job, total=estimate, phase="Starting export")
    jobs.describe(
        job,
        filename=filename,
        from_ts=from_ts if ranged else None,
        to_ts=to_ts if ranged else None,
    )
    return {"id": job.id, "filename": filename}


@router.get("/export/{job_id}/download")
async def download_export(job_id: str):
    job = jobs.get(job_id)
    if job is None or job.kind != "export":
        raise HTTPException(status_code=404, detail="Unknown export job")

    filename = job.result.get("filename", "aware-db-backup.sql.gz")
    return StreamingResponse(
        _export_chunks(job),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # The archive is produced as it is sent, so no intermediary should
            # collect it first.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/files")
async def list_backup_files():
    """Backups already on the server, newest first."""
    if not BACKUP_DIR.is_dir():
        return {"directory": str(BACKUP_DIR), "files": []}

    files = []
    for entry in BACKUP_DIR.iterdir():
        if not entry.is_file() or not entry.name.endswith(".sql.gz"):
            continue
        stat = entry.stat()
        files.append(
            {
                "name": entry.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
        )
    files.sort(key=lambda item: item["modified"], reverse=True)
    return {"directory": str(BACKUP_DIR), "files": files}


def _resolve_backup_file(name: str) -> Path:
    """A named file inside BACKUP_DIR, with the name kept to that directory."""
    candidate = (BACKUP_DIR / name).resolve()
    if not candidate.is_relative_to(BACKUP_DIR.resolve()) or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Unknown backup file")
    return candidate


def _feed_mysql(job: jobs.Job, path: Path, mode: str, marks: dict) -> None:
    """Stream the archive into mysql, rewriting statements when merging.

    Runs off the event loop: the reads, the decompression and the client are all
    blocking, and the job record is what carries progress back.
    """
    total = path.stat().st_size
    jobs.advance(
        job,
        total=total,
        done=0,
        phase="Merging into the databases" if mode == dump_stream.MERGE else "Restoring",
    )

    mysql = subprocess.Popen(
        _mysql_base_command("mysql"),
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_mysql_env(),
    )
    rewriter = dump_stream.DumpRewriter(
        mode,
        marks,
        on_rows=lambda table, added, skipped: jobs.count_rows(job, table, added, skipped),
    )

    try:
        with path.open("rb") as raw:
            stream = io.BufferedReader(gzip.GzipFile(fileobj=raw), buffer_size=CHUNK)
            seen = 0
            for line in stream:
                statement = rewriter.feed(line)
                if statement:
                    mysql.stdin.write(statement)
                seen += 1
                if seen % PROGRESS_EVERY == 0:
                    jobs.advance(job, done=min(raw.tell(), total))
        mysql.stdin.close()
    except BrokenPipeError:
        # The client exited early; its stderr below says why.
        pass
    except BaseException as error:
        # Anything else leaves a client mid-statement, so end it here rather
        # than leaving the process attached to a half-fed pipe.
        mysql.kill()
        mysql.wait()
        if isinstance(error, OSError):
            raise RuntimeError(f"Could not read the backup archive: {error}") from error
        raise
    finally:
        if mysql.stdin and not mysql.stdin.closed:
            mysql.stdin.close()

    message = mysql.stderr.read().decode("utf-8", errors="replace").strip()
    if mysql.wait() != 0:
        raise RuntimeError(message or "Database import failed")

    jobs.advance(job, done=total)


async def _refresh_counts(mode: str) -> None:
    """Bring the count cache back in line with what the databases now hold.

    Merged rows carry fresh ``_id`` values above every sensor's watermark, so the
    ordinary incremental refresh folds them in.

    A replace is different: it drops and rebuilds the tables the cache
    summarises, leaving every tally and ``_id`` watermark describing rows that no
    longer exist. The refresh is incremental and cannot notice, so the cache is
    cleared first and rebuilt from what actually arrived — which is what
    ``reset`` is for.
    """
    for session, model, sources in (
        (AndroidSessionLocal, AndroidRecordCount, ANDROID_SOURCES),
        (IosSessionLocal, IosRecordCount, IOS_SOURCES),
    ):
        async with session() as db:
            if mode == dump_stream.REPLACE:
                await record_counts.reset(db, model)
            await record_counts.refresh(db, model, sources)


async def _build_watermarks(job: jobs.Job) -> dict:
    marks: dict = {}
    progress = lambda phase: jobs.advance(job, phase=phase)  # noqa: E731
    async with AndroidSessionLocal() as db:
        marks |= await watermarks.build(
            db, "aware_android", AndroidRecordCount, ANDROID_SOURCES, progress
        )
    async with IosSessionLocal() as db:
        marks |= await watermarks.build(
            db, "aware_ios", IosRecordCount, IOS_SOURCES, progress
        )
    return marks


async def _run_import(job: jobs.Job, path: Path, mode: str, temporary: bool) -> None:
    try:
        marks: dict = {}
        if mode == dump_stream.MERGE:
            jobs.advance(job, phase="Reading what is already stored")
            marks = await _build_watermarks(job)

        await asyncio.get_running_loop().run_in_executor(
            None, _feed_mysql, job, path, mode, marks
        )

        jobs.advance(job, phase="Refreshing record counts")
        await _refresh_counts(mode)
        jobs.finish(job, {"mode": mode, "source": path.name})
    except Exception as error:  # noqa: BLE001 - surfaced through the job record
        jobs.fail(job, str(error))
    finally:
        if temporary:
            shutil.rmtree(path.parent, ignore_errors=True)


@router.post("/import")
async def start_import(
    mode: str = Form(dump_stream.REPLACE),
    filename: str | None = Form(None),
    backup: UploadFile | None = File(None),
):
    """Begin an import and hand back the job to watch.

    The archive arrives either as an upload or by name from BACKUP_DIR. An
    upload is received here — that is the phase the browser reports itself — and
    everything after it is the job's.
    """
    if mode not in (dump_stream.REPLACE, dump_stream.MERGE):
        raise HTTPException(status_code=400, detail=f"Unknown import mode: {mode}")
    _mysql_env()

    temporary = False
    if filename:
        path = _resolve_backup_file(filename)
    elif backup is not None:
        if backup.size and backup.size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Backup file is too large to upload; copy it to the server's "
                "backup directory and import it by name instead",
            )
        staging = Path(tempfile.mkdtemp(prefix="aware-restore-"))
        path = staging / "restore.sql.gz"
        with path.open("wb") as target:
            shutil.copyfileobj(backup.file, target, CHUNK)
        temporary = True
    else:
        raise HTTPException(status_code=400, detail="Choose a backup file to import")

    job = jobs.create("import")
    jobs.advance(job, phase="Preparing", total=path.stat().st_size)
    task = asyncio.create_task(_run_import(job, path, mode, temporary))
    _running.add(task)
    task.add_done_callback(_running.discard)
    return {"id": job.id, "mode": mode, "source": path.name}


@router.get("/jobs/{job_id}")
async def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return job.snapshot()
