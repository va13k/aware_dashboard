"""Maintenance endpoints for the record-count cache (see services/record_counts.py).

The refresh is deliberately off the request path: a scheduler or cron hits
``POST /counts/refresh`` on an interval. It is idempotent and cheap when nothing
new arrived, so calling it often is fine.
"""

import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import android_engine, get_android_db, get_ios_db
from app.models import AndroidRecordCount, IosRecordCount
from app.routers.android import _EXPORT_MODELS as ANDROID_EXPORT_MODELS
from app.routers.ios import _EXPORT_MODELS as IOS_EXPORT_MODELS
from app.services import record_counts

router = APIRouter(prefix="/counts", tags=["counts"])

# sensor slug -> source model, reusing the export maps as the sensor registry.
# Android values are (model, schema); iOS values are a model or a tuple of
# models (multi-table sensors, e.g. wifi) — those are skipped, so they keep the
# live-count fallback rather than being split across cache rows.
ANDROID_SOURCES = {slug: entry[0] for slug, entry in ANDROID_EXPORT_MODELS.items()}
IOS_SOURCES = {
    slug: model
    for slug, model in IOS_EXPORT_MODELS.items()
    if not isinstance(model, tuple)
}


@router.post("/refresh")
async def refresh_counts(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """Fold in what has arrived, unless the scheduled refresher is mid-pass.

    It shares the refresh lock with the scheduler, so a researcher pressing this
    while a scheduled pass runs is answered rather than counted twice.
    """
    async with record_counts.single_writer(android_engine) as acquired:
        if not acquired:
            return {"status": "busy", "detail": "a refresh is already running"}
        android = await record_counts.refresh(
            android_db, AndroidRecordCount, ANDROID_SOURCES
        )
        ios = await record_counts.refresh(ios_db, IosRecordCount, IOS_SOURCES)
        return {"android": android, "ios": ios}


@router.post("/reset")
async def reset_counts(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """Clear the cache so the next refresh rebuilds it (use after purging rows)."""
    await record_counts.reset(android_db, AndroidRecordCount)
    await record_counts.reset(ios_db, IosRecordCount)
    return {"status": "cleared"}


#: Past this, the numbers on screen are old enough to say so. Three intervals of
#: the refresh container's default, so an ordinary late pass is not called stale.
STALE_AFTER_SECONDS = 180


async def _last_refreshed(db: AsyncSession) -> float | None:
    """When a refresh last wrote to this database, as epoch seconds.

    Both caches stamp `updated_at` on write, so the newer of the two is when the
    pass ran, whether or not the other had anything to add.
    """
    try:
        result = await db.execute(
            text(
                "SELECT UNIX_TIMESTAMP(MAX(updated_at)) FROM ("
                "  SELECT MAX(updated_at) AS updated_at FROM record_counts"
                "  UNION ALL"
                "  SELECT MAX(updated_at) FROM coverage_hourly"
                ") AS both_caches"
            )
        )
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        try:
            await db.rollback()
        except SQLAlchemyError:
            pass
        return None
    stamped = result.scalar()
    return float(stamped) if stamped is not None else None


@router.get("/status")
async def counts_status(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """When the counts were last refreshed, so the page can say how fresh it is.

    A dashboard whose refresher has died looks exactly like one whose study has
    gone quiet. This is what tells the two apart.

    Freshness is one figure across both platforms, not one each. A pass writes
    only what changed, so a platform receiving no data leaves its `updated_at`
    where it was and would read as stale while the refresher is perfectly
    healthy. One refresher does both databases in the same pass, so the newest
    write anywhere is when that pass ran.
    """
    now = time.time()
    platforms = {}
    for name, db in (("android", android_db), ("ios", ios_db)):
        refreshed = await _last_refreshed(db)
        platforms[name] = {
            "last_refreshed": refreshed,
            "age_seconds": (now - refreshed) if refreshed is not None else None,
        }

    stamps = [p["last_refreshed"] for p in platforms.values() if p["last_refreshed"]]
    newest = max(stamps) if stamps else None
    return {
        "stale_after_seconds": STALE_AFTER_SECONDS,
        "last_refreshed": newest,
        "age_seconds": (now - newest) if newest is not None else None,
        "stale": newest is None or (now - newest) > STALE_AFTER_SECONDS,
        "platforms": platforms,
    }
