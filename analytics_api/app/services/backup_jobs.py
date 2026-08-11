"""Progress records for the long-running backup jobs.

A study-scale export or import runs for minutes to hours, so both report through
a job record that the backup page polls instead of holding one request open for
the whole run. Progress is expressed in bytes because that is the one unit both
sides can measure exactly and monotonically: an export knows how much of the
estimated dump it has streamed, an import knows how far into the compressed file
it has read.

The registry is per-process. A job is created, advanced and read by the same
worker, and a restart ends any run in flight, so there is nothing to share
between workers and nothing to persist. Finished jobs stay in memory briefly so
the page can collect the final state, then age out.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field

#: How long a finished job stays readable before it is swept, in seconds. The
#: page polls every second, so this is generous enough to survive a reload.
RETENTION_SECONDS = 15 * 60

RUNNING = "running"
DONE = "done"
ERROR = "error"
#: The reader went away — a cancelled download, a closed tab, a dropped
#: connection. Not a failure: nothing went wrong and there is nothing to report
#: beyond the fact that the work is no longer running.
CANCELLED = "cancelled"


@dataclass
class Job:
    """One export or import run, and how far along it is."""

    id: str
    kind: str
    state: str = RUNNING
    #: Short human-readable description of the current step.
    phase: str = "Starting"
    #: Bytes processed so far, and the best available estimate of the total.
    #: `total` of 0 means "not known yet" and the page shows an indeterminate bar.
    done: int = 0
    total: int = 0
    #: Bytes actually delivered, which an export reports alongside `done`: the
    #: percentage tracks the dump's progress through the data, while this is the
    #: compressed size the browser is receiving.
    bytes_out: int = 0
    #: Per-table row tallies, populated by an import: {table: [added, skipped]}.
    tables: dict = field(default_factory=dict)
    error: str = ""
    #: Set once the run finishes, for whatever the caller wants to hand back.
    result: dict = field(default_factory=dict)
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float = 0.0

    def snapshot(self) -> dict:
        """A plain dict for the status endpoint."""
        elapsed = (self.finished_at or time.monotonic()) - self.started_at
        percent = None
        if self.total > 0 and self.done <= self.total:
            percent = round(self.done * 100.0 / self.total, 1)
        elif self.state == DONE:
            percent = 100.0
        # Past the total the estimate has been overrun — a row count taken from
        # the count cache lags whatever has arrived since its last refresh. No
        # percentage is reported rather than one pinned at 100, which would claim
        # a download had finished while it was still being written.
        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "phase": self.phase,
            "done": self.done,
            "total": self.total,
            "bytes_out": self.bytes_out,
            "percent": percent,
            "tables": {
                name: {"added": added, "skipped": skipped}
                for name, (added, skipped) in self.tables.items()
            },
            "rows_added": sum(added for added, _ in self.tables.values()),
            "rows_skipped": sum(skipped for _, skipped in self.tables.values()),
            "elapsed": round(elapsed, 1),
            "error": self.error,
            "result": self.result,
        }


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def _sweep(now: float) -> None:
    """Drop jobs that finished long enough ago that nobody is watching."""
    stale = [
        job_id
        for job_id, job in _jobs.items()
        if job.finished_at and now - job.finished_at > RETENTION_SECONDS
    ]
    for job_id in stale:
        del _jobs[job_id]


def create(kind: str, job_id: str | None = None) -> Job:
    """Register a new running job. An explicit `job_id` lets the caller start
    polling before the work begins — the export download is a plain navigation,
    so the page has to know the id before it hands the URL to the browser."""
    job = Job(id=job_id or uuid.uuid4().hex, kind=kind)
    with _lock:
        _sweep(time.monotonic())
        _jobs[job.id] = job
    return job


def get(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def advance(job: Job, *, done: int | None = None, add: int = 0, phase: str | None = None,
            total: int | None = None, out: int = 0) -> None:
    """Move a job forward. Called from the streaming loops, so it stays cheap:
    a couple of assignments under the lock and no allocation."""
    with _lock:
        if done is not None:
            job.done = done
        if add:
            job.done += add
        if out:
            job.bytes_out += out
        if phase is not None:
            job.phase = phase
        if total is not None:
            job.total = total


def count_rows(job: Job, table: str, added: int = 0, skipped: int = 0) -> None:
    """Fold an import batch's outcome into the per-table tally."""
    with _lock:
        current_added, current_skipped = job.tables.get(table, (0, 0))
        job.tables[table] = (current_added + added, current_skipped + skipped)


def describe(job: Job, **values) -> None:
    """Attach detail the page shows once the job lands, such as the filename an
    export will download as."""
    with _lock:
        job.result.update(values)


def finish(job: Job, result: dict | None = None) -> None:
    with _lock:
        job.state = DONE
        job.phase = "Finished"
        job.finished_at = time.monotonic()
        if job.total:
            job.done = job.total
        if result:
            job.result.update(result)


def cancel(job: Job) -> None:
    """Mark a job whose reader disappeared.

    Closing a streaming response raises ``GeneratorExit``, which is a
    ``BaseException`` and so passes straight through ``except Exception``. Left
    alone the record would stay ``running`` until it aged out, and the page
    watching it would spin for a quarter of an hour over a download the user
    deliberately stopped.
    """
    with _lock:
        if job.state != RUNNING:
            return
        job.state = CANCELLED
        job.phase = "Cancelled"
        job.finished_at = time.monotonic()


def fail(job: Job, message: str) -> None:
    with _lock:
        job.state = ERROR
        job.phase = "Failed"
        job.error = message
        job.finished_at = time.monotonic()
