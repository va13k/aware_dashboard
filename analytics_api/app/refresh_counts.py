"""Keeps the record-count cache current, once or on an interval.

Counts shown by the dashboard come from a cache table that only moves when a
refresh runs. This module is what runs it, holding the refresh lock so one
refresher works at a time (see services/record_counts.py):

    python -m app.refresh_counts                 one pass, then exit
    python -m app.refresh_counts --interval 60   a pass every 60 seconds

The interval form is what the scheduler container runs. Each pass folds in the
rows added since each sensor's ``_id`` watermark, so the first one is a full scan
and the rest cost what ingest cost. A pass that fails is logged and the loop
carries on: counts and watermarks move together in one transaction, so the rows a
failed pass missed are simply counted by the next one.

Every completed pass touches the heartbeat file, which is what tells a
healthcheck the loop is running rather than stuck on a query.
"""

import argparse
import asyncio
import logging
import os
import pathlib
import time

from app.database import (
    AndroidSessionLocal,
    IosSessionLocal,
    android_engine,
    ios_engine,
)
from app.models import AndroidRecordCount, IosRecordCount
from app.routers.counts import ANDROID_SOURCES, IOS_SOURCES
from app.services import record_counts

logger = logging.getLogger("aware.refresh_counts")

DEFAULT_INTERVAL_SECONDS = 60
HEARTBEAT_PATH_ENV = "COUNTS_REFRESH_HEARTBEAT"
INTERVAL_ENV = "COUNTS_REFRESH_INTERVAL_SECONDS"


def heartbeat_path() -> pathlib.Path | None:
    configured = os.environ.get(HEARTBEAT_PATH_ENV, "").strip()
    return pathlib.Path(configured) if configured else None


def touch_heartbeat() -> None:
    """Stamps the file a healthcheck reads to see that a pass completed."""
    path = heartbeat_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{time.time():.0f}\n")
    except OSError as error:
        logger.warning("could not write the heartbeat file %s: %s", path, error)


async def refresh_all() -> dict:
    """One pass over both platforms, for whichever refresher holds the lock.

    Returns the rows added per platform, or ``{"skipped": True}`` when another
    refresher is already working.
    """
    async with record_counts.single_writer(android_engine) as acquired:
        if not acquired:
            logger.info("another refresh is running; skipping this pass")
            return {"skipped": True}

        async with AndroidSessionLocal() as db:
            android = await record_counts.refresh(
                db, AndroidRecordCount, ANDROID_SOURCES
            )
        async with IosSessionLocal() as db:
            ios = await record_counts.refresh(db, IosRecordCount, IOS_SOURCES)
        return {"android": android, "ios": ios}


def _log_result(result: dict) -> None:
    if result.get("skipped"):
        return
    for platform in ("android", "ios"):
        counted = result[platform]
        logger.info(
            "%s: +%d rows across %d sensors",
            platform,
            sum(counted.values()),
            len(counted),
        )


async def run_once() -> dict:
    result = await refresh_all()
    _log_result(result)
    touch_heartbeat()
    return result


async def run_forever(interval_seconds: int) -> None:
    logger.info("refreshing record counts every %d seconds", interval_seconds)
    while True:
        started = time.monotonic()
        try:
            await run_once()
        except Exception:  # noqa: BLE001 - a failed pass is retried by the next
            logger.exception("refresh failed; retrying at the next interval")
        # Time the sleep from the start of the pass, so a slow pass shortens the
        # wait rather than adding to it and letting the schedule drift.
        await asyncio.sleep(max(0.0, interval_seconds - (time.monotonic() - started)))


async def _main(interval_seconds: int | None) -> None:
    try:
        if interval_seconds:
            await run_forever(interval_seconds)
        else:
            await run_once()
    finally:
        # Dispose the pools inside the loop so aiomysql closes its connections
        # while there is still a loop to close them on.
        await android_engine.dispose()
        await ios_engine.dispose()


def _configured_interval() -> int:
    raw = os.environ.get(INTERVAL_ENV, "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning(
            "%s=%r is not a number of seconds; running a single pass", INTERVAL_ENV, raw
        )
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        metavar="SECONDS",
        help=(
            f"repeat every SECONDS instead of running once "
            f"(default from {INTERVAL_ENV}, else a single pass)"
        ),
    )
    arguments = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    interval = arguments.interval
    if interval is None:
        interval = _configured_interval()
    if interval and interval < 0:
        interval = DEFAULT_INTERVAL_SECONDS

    try:
        asyncio.run(_main(interval))
    except KeyboardInterrupt:
        logger.info("stopped")


if __name__ == "__main__":
    main()
