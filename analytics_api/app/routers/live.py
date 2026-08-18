"""The channel a dashboard listens on, so a tile moves without a refresh.

WebSockets rather than a one-way stream, because commands will eventually travel
the other way — a researcher acting on a device rather than only watching it — and
replacing the transport later would be the more expensive order to do it in.

That choice puts two things here that a one-way stream would have got for free.
Nginx's `auth_request` guards the HTTP request that opens the socket and nothing
that flows over it afterwards, so the session is checked here as well. And a
browser reconnects an `EventSource` on its own, but not a socket, so the client
resumes by naming the last sequence it saw and this replies with the gap — or tells
it to refetch when the gap is longer than the history kept.

Between the browser and this API only. Reaching a *phone* is a separate leg with a
separate transport, and belongs to the client's own work.
"""

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import AndroidSessionLocal, IosSessionLocal
from app.routers import auth
from app.routers.android import _EXPORT_MODELS as ANDROID_EXPORT_MODELS
from app.routers.ios import _EXPORT_MODELS as IOS_EXPORT_MODELS
from app.refresh_counts import refresh_all
from app.services import coverage_rollup, live_watch, sensor_tables

logger = logging.getLogger("aware.live")

router = APIRouter(tags=["live"])

#: Closed with this when the handshake carries no live session. 1008 is the
#: protocol's "policy violation", which is what an unauthenticated socket is.
UNAUTHORISED = 1008


#: Which sensor each table belongs to, per platform. Read once: the export maps
#: are the registry every other reader uses, so a table they do not claim is not
#: something the interface can show.
_SENSOR_BY_TABLE = {
    "android": sensor_tables.sensor_by_table(ANDROID_EXPORT_MODELS),
    "ios": sensor_tables.sensor_by_table(IOS_EXPORT_MODELS),
}


def _sensor_for(platform: str) -> dict:
    return _SENSOR_BY_TABLE.get(platform, {})


async def _watched_tables(db, platform: str) -> list[str]:
    """The tables worth asking about: those the rollup has seen data in, and that
    a sensor claims.

    Twenty of the fifty-nine have never held a row on this deployment, and an
    empty table cannot have gained one since the last tick. Taken from the rollup
    rather than the schema so the list follows the study rather than the framework,
    and narrowed to what a tile could show, so no tick spends a query on a table
    with nowhere to report to.
    """
    try:
        rows = (
            await db.execute(text("SELECT DISTINCT `table_name` FROM `coverage_hourly`"))
        ).all()
    except SQLAlchemyError:
        try:
            await db.rollback()
        except SQLAlchemyError:
            pass
        return []
    claimed = _sensor_for(platform)
    return [
        str(row[0])
        for row in rows
        if row[0]
        and str(row[0]) not in coverage_rollup.SKIP_TABLES
        and str(row[0]) in claimed
    ]


watcher = live_watch.LiveWatch(
    sessions={"android": AndroidSessionLocal, "ios": IosSessionLocal},
    tables_for=_watched_tables,
    sensor_for=_sensor_for,
    # The same pass the scheduler runs, under the same lock. A tick that saw rows
    # brings the caches to them, so a reader that refetches on the news finds it.
    refresh=refresh_all,
)


@router.websocket("/live")
async def live(websocket: WebSocket, since: int | None = Query(None)):
    """Stream what arrives, to a dashboard that is already open.

    `since` is the last sequence this client saw. Given one, it receives the
    messages after it; given one older than the history holds, it is told to
    refetch, because a gap silently skipped is worse than a reload.
    """
    if not auth.session_is_valid(websocket.cookies):
        await websocket.close(code=UNAUTHORISED)
        return

    await websocket.accept()
    subscriber, backlog, must_refetch = watcher.subscribe(since)

    try:
        await websocket.send_json(
            {
                "type": "hello",
                "seq": watcher.sequence,
                "tick_seconds": live_watch.TICK_SECONDS,
                "heartbeat_seconds": live_watch.HEARTBEAT_SECONDS,
                # The client reloads rather than trusting an incremental update it
                # cannot have received.
                "refetch": must_refetch,
            }
        )
        for message in backlog:
            await websocket.send_json(message)

        while True:
            try:
                message = await asyncio.wait_for(
                    subscriber.queue.get(), timeout=live_watch.HEARTBEAT_SECONDS
                )
            except asyncio.TimeoutError:
                # Nothing arrived. Say so, so the client can tell a quiet study
                # from a broken connection.
                await websocket.send_json(watcher.publish_heartbeat())
                continue

            if subscriber.overflowed:
                # Too far behind to catch up a message at a time.
                await websocket.send_json({"type": "refetch", "seq": watcher.sequence})
                subscriber.overflowed = False
                continue

            await websocket.send_json(message)
            subscriber.seq = message["seq"]
    except WebSocketDisconnect:
        pass
    except Exception as error:  # noqa: BLE001 - one bad socket must not take the loop
        logger.info("live socket closed: %s", error)
    finally:
        watcher.unsubscribe(subscriber)
