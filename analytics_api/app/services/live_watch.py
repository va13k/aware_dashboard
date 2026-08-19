"""What arrived since a moment ago, watched once and told to everyone.

A minute-old count is an interim answer. The refresher keeps the caches honest on
its own schedule, and this closes the gap between a row landing and a tile moving.

**One loop, not one per connection.** Ten open dashboards must not mean ten times
the database work, so the watching happens here, once, and the result is handed to
whoever is listening. A subscriber is a queue, not a poller.

**It sleeps when nobody is watching.** With no subscribers the loop does nothing at
all — the study is not made more expensive by a feature nobody has open.

**Watermarks come from `MAX(_id)` per table.** The tempting shortcut is
`AUTO_INCREMENT` from `information_schema`, one query for every table at once. It
is wrong: that column is cached, and a scratch table showed it reporting 4 when the
table already held 5 rows, with the default expiry leaving it stale for up to a day.
A watcher built on it would look live and silently miss changes, so the tables are
asked directly — but in one statement rather than one round trip each, and only the
tables the rollup has ever seen data in.

**Which tables those are is read on a slower clock than the tick.** The list grows
only when the rollup first folds rows from a table it has never seen, and that
happens on the refresher's pass rather than this loop's. Asking every tick would
spend a statement per platform to be told the same thing thirty times over, so the
answer is kept for `TABLE_LIST_SECONDS` and a quiet tick costs one statement per
platform that has tables rather than two.

Deltas are per `(device, sensor)`: the count of rows that arrived in the tick. That
is what a tile shows, so a subscriber can apply the change without asking anything
further. A sensor spread over two tables sums, the same way every other reader
treats it.

**A tick that found rows folds them into the caches before saying so.** Every
number the dashboard shows is read from `record_counts` and `coverage_hourly`, which
move only when a refresh runs. Announcing an arrival while those still hold the old
totals would send every reader to refetch the very numbers they already have, and
the change would appear to have been imagined. The refresh is the same incremental
pass the scheduler runs, under the same lock, so a pass already in progress is
skipped rather than double-counted.
"""

import asyncio
import logging
import time
from collections import deque

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("aware.live")

#: How often the loop looks, while anyone is listening. Short enough that a tile
#: moves while the researcher is still looking at it, long enough that a quiet
#: study costs two statements per platform per tick.
TICK_SECONDS = 2.0

#: Sent when a tick found nothing, so a silent socket stays distinguishable from a
#: dead one. A subscriber that hears nothing for several of these has lost the
#: connection rather than the study going quiet.
HEARTBEAT_SECONDS = 20.0

#: How long the watched-table list is trusted before being read again. Matched to
#: the refresher's own interval, because that pass is the only thing that can add a
#: table to the list: a new sensor becomes watched within a minute of its first
#: rows being folded in, and the tick stops paying for the question in between.
TABLE_LIST_SECONDS = 60.0

#: Messages kept for a subscriber that reconnects and asks to carry on. Bounded:
#: a client further behind than this is told to refetch rather than replayed.
HISTORY = 200


class Subscriber:
    """One open dashboard. A queue, so a slow reader cannot stall the loop."""

    def __init__(self, seq: int) -> None:
        #: The newest sequence this subscriber has been given.
        self.seq = seq
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        #: Set when the queue overflowed: the subscriber is too far behind to be
        #: caught up incrementally and is told to refetch instead.
        self.overflowed = False

    def offer(self, message: dict) -> None:
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            self.overflowed = True


class LiveWatch:
    """The shared loop, its subscribers, and the recent history they resume from."""

    def __init__(self, sessions: dict, tables_for, sensor_for, refresh) -> None:
        #: `{platform: async_sessionmaker}`.
        self._sessions = sessions
        #: Called per platform, returns the tables worth watching -- or `None`
        #: when it could not find out, which is not the same answer as "none".
        self._tables_for = tables_for
        #: Called per platform, returns `{table: sensor}`. Platform-specific: an
        #: iPhone stores `wifi` across two tables and `esm` across two more, where
        #: every Android sensor is one table.
        self._sensor_for = sensor_for
        #: Folds arrived rows into the caches every reader counts from. Injected
        #: rather than reached for, so the loop stays testable without a database.
        self._refresh = refresh
        self._subscribers: set[Subscriber] = set()
        self._history: deque = deque(maxlen=HISTORY)
        self._seq = 0
        #: `{(platform, table): highest _id folded in}`.
        self._watermarks: dict[tuple[str, str], int] = {}
        #: The watched list per platform, and the monotonic time each was read at.
        self._tables: dict[str, list[str]] = {}
        self._tables_read_at: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="live-watch")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None

    # -- subscribers -------------------------------------------------------

    def subscribe(self, since: int | None = None) -> tuple[Subscriber, list[dict], bool]:
        """Register a listener, with whatever it missed.

        Returns the subscriber, the backlog to send first, and whether the client
        should refetch instead — true when it asked to resume from further back
        than the history holds, so nothing is quietly skipped.
        """
        subscriber = Subscriber(self._seq)
        self._subscribers.add(subscriber)
        # The loop idles with no subscribers, so the first one has to wake it.
        self._wake.set()

        if since is None:
            return subscriber, [], False

        # A client naming a sequence ahead of this one has outlived a restart,
        # which put the count back to zero. Its number refers to a history that no
        # longer exists, so it cannot be told it is up to date.
        if since > self._seq:
            return subscriber, [], True

        backlog = [message for message in self._history if message["seq"] > since]
        # Either the history reaches back far enough to cover the gap, or it does
        # not and the client cannot be trusted to be up to date.
        oldest = self._history[0]["seq"] if self._history else self._seq + 1
        resumable = since >= oldest - 1
        return subscriber, backlog if resumable else [], not resumable

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)
        if not self._subscribers:
            # Nothing is listening; stop looking until something is.
            self._wake.clear()
            self._watermarks.clear()
            # Dropped with them: the study may gain a sensor while nobody watches,
            # and the next subscriber should not inherit a list from before that.
            self._tables.clear()
            self._tables_read_at.clear()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def sequence(self) -> int:
        return self._seq

    # -- the loop ----------------------------------------------------------

    async def _run(self) -> None:
        logger.info("live watch started")
        while True:
            # Nobody listening: wait rather than poll.
            await self._wake.wait()
            try:
                changes = await self._collect()
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - the loop must outlive a bad tick
                logger.warning("live watch tick failed: %s", error)
                changes = []

            if changes:
                await self._fold_in()
                self._publish({"type": "changes", "changes": changes})
            await asyncio.sleep(TICK_SECONDS)

    async def _fold_in(self) -> None:
        """Bring the caches up to the rows just seen, before anyone is told.

        A failure here costs the readers their prompt numbers, not the channel: the
        scheduled refresh folds the same rows in on its own pass, and the fallback
        poll is what picks them up.
        """
        try:
            await self._refresh()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - a stale cache outlives a bad pass
            logger.warning("live watch could not refresh the caches: %s", error)

    def _publish(self, message: dict) -> None:
        self._seq += 1
        message = {**message, "seq": self._seq, "at": int(time.time() * 1000)}
        self._history.append(message)
        for subscriber in self._subscribers:
            subscriber.offer(message)

    def publish_heartbeat(self) -> dict:
        """A message carrying no change, for a connection to prove itself with.

        Not put through `_publish`: it holds no news, so it must not take a
        sequence number a reconnecting client would then try to resume from.
        """
        return {"type": "heartbeat", "seq": self._seq, "at": int(time.time() * 1000)}

    # -- reading the databases --------------------------------------------

    async def _collect(self) -> list[dict]:
        changes: list[dict] = []
        for platform, factory in self._sessions.items():
            async with factory() as db:
                changes.extend(await self._collect_platform(db, platform))
        return changes

    async def _watched(self, db, platform: str) -> list[str]:
        """The tables worth asking about, remembered between ticks.

        A read that fails leaves the previous list in place rather than emptying
        it. The tables already known have not stopped existing, and a watcher that
        went blind on one bad query would stay blind until something subscribed
        again.
        """
        now = time.monotonic()
        read_at = self._tables_read_at.get(platform)
        if read_at is not None and now - read_at < TABLE_LIST_SECONDS:
            return self._tables[platform]

        tables = await self._tables_for(db, platform)
        if tables is None:
            return self._tables.get(platform, [])
        self._tables[platform] = tables
        self._tables_read_at[platform] = now
        return tables

    async def _collect_platform(self, db, platform: str) -> list[dict]:
        tables = await self._watched(db, platform)
        if not tables:
            return []

        current = await self._max_ids(db, tables)
        first_look = not any(
            (platform, table) in self._watermarks for table in tables
        )

        sensor_by_table = self._sensor_for(platform)
        # Summed per (device, sensor) rather than reported per table, because a
        # tile is a sensor. On an iPhone `wifi` arrives in two tables, and two
        # separate deltas naming tables would leave the interface to work out a
        # mapping that only the API holds.
        totals: dict[tuple[str, str], int] = {}
        for table, highest in current.items():
            key = (platform, table)
            previous = self._watermarks.get(key)
            self._watermarks[key] = highest
            # A first look establishes where the study is now. Reporting every row
            # ever stored as "just arrived" would be worse than saying nothing.
            if first_look or previous is None or highest <= previous:
                continue
            sensor = sensor_by_table.get(table)
            if sensor is None:
                continue
            for device_id, records in await self._new_rows(
                db, table, previous, highest
            ):
                totals[(device_id, sensor)] = totals.get((device_id, sensor), 0) + records

        return [
            {
                "platform": platform,
                "sensor": sensor,
                "device_id": device_id,
                "records": records,
            }
            for (device_id, sensor), records in sorted(totals.items())
        ]

    async def _max_ids(self, db, tables: list[str]) -> dict[str, int]:
        """The highest `_id` in each table, in one statement.

        One round trip rather than one per table: the subqueries are primary-key
        lookups, and the cost of asking is dominated by the trips, not the reads.
        """
        parts = [
            f"SELECT '{table}' AS table_name, COALESCE(MAX(`_id`), 0) AS highest "
            f"FROM `{table}`"
            for table in tables
        ]
        try:
            rows = (await db.execute(text(" UNION ALL ".join(parts)))).all()
        except SQLAlchemyError:
            try:
                await db.rollback()
            except SQLAlchemyError:
                pass
            return {}
        # Read through `_mapping` rather than as attributes: SQLAlchemy reserves
        # short names on Row for its own API — `Row.t` is the whole row as a tuple —
        # so a column aliased `t` comes back as the row itself and every watermark
        # lands under a nonsense key.
        return {
            str(row._mapping["table_name"]): int(row._mapping["highest"] or 0)
            for row in rows
        }

    async def _new_rows(self, db, table: str, low: int, high: int):
        """Which devices the rows between two watermarks belong to, and how many."""
        try:
            rows = (
                await db.execute(
                    text(
                        f"SELECT `device_id` AS device, COUNT(*) AS records "
                        f"FROM `{table}` "
                        "WHERE `_id` > :low AND `_id` <= :high GROUP BY `device_id`"
                    ),
                    {"low": low, "high": high},
                )
            ).all()
        except SQLAlchemyError:
            try:
                await db.rollback()
            except SQLAlchemyError:
                pass
            return []
        return [
            (str(row._mapping["device"]), int(row._mapping["records"]))
            for row in rows
            if row._mapping["device"] not in (None, "") and row._mapping["records"]
        ]
