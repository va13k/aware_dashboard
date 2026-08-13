"""Maintenance endpoints for the record-count cache (see services/record_counts.py).

The refresh is deliberately off the request path: a scheduler or cron hits
``POST /counts/refresh`` on an interval. It is idempotent and cheap when nothing
new arrived, so calling it often is fine.
"""

from fastapi import APIRouter, Depends
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
