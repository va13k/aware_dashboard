"""Status for any long-running job, whichever router started it.

Jobs began with the backup export and import, and the CSV exports now report the
same way, so the record they share is read from one place rather than from a
path that names whoever happens to own it. The registry itself lives in
services/backup_jobs.py.
"""

from fastapi import APIRouter, HTTPException

from app.services import backup_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def job_status(job_id: str):
    job = backup_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return job.snapshot()
