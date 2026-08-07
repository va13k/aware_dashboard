"""Populate / refresh the record-count cache off the request path.

The HTTP ``POST /counts/refresh`` endpoint sits behind researcher login, which
makes it awkward to drive from automation. This module does the same work
directly against the databases (using the analytics DB credentials), so it can
be run by hand or from cron without a session:

    python -m app.refresh_counts

The first run is a full ``GROUP BY device_id`` scan of every sensor table and
can take a while at scale; later runs only fold in rows added since each
sensor's ``_id`` watermark, so they are cheap. Safe to run often and safe to
overlap-guard with a simple cron interval.
"""

import asyncio

from app.database import (
    AndroidSessionLocal,
    IosSessionLocal,
    android_engine,
    ios_engine,
)
from app.models import AndroidRecordCount, IosRecordCount
from app.routers.counts import ANDROID_SOURCES, IOS_SOURCES
from app.services import record_counts


async def refresh_all() -> dict:
    try:
        async with AndroidSessionLocal() as db:
            android = await record_counts.refresh(
                db, AndroidRecordCount, ANDROID_SOURCES
            )
        async with IosSessionLocal() as db:
            ios = await record_counts.refresh(db, IosRecordCount, IOS_SOURCES)
        return {"android": android, "ios": ios}
    finally:
        # Dispose the pools inside the loop so aiomysql doesn't try to close
        # connections after asyncio.run() has already torn the loop down.
        await android_engine.dispose()
        await ios_engine.dispose()


def main() -> None:
    result = asyncio.run(refresh_all())
    android_total = sum(result["android"].values())
    ios_total = sum(result["ios"].values())
    print(f"android: +{android_total} rows across {len(result['android'])} sensors")
    print(f"ios:     +{ios_total} rows across {len(result['ios'])} sensors")


if __name__ == "__main__":
    main()
