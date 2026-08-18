"""The shared watcher behind the live channel.

Four things here are the ones that would be wrong silently.

A first look must report nothing. The watcher learns where each table stands before
it can say what arrived, and announcing every row ever stored as "just now" would
move every tile on the first tick.

The loop must idle with nobody listening, or a feature nobody has open costs the
study two statements a second forever.

Resume must be honest. A client naming a sequence the history still covers gets the
gap; one naming an older sequence is told to refetch, because a skipped message
would leave a tile wrong with nothing to correct it.

And a heartbeat must not consume a sequence number: it carries no news, so a client
resuming from it would claim to have seen a change it never received.
"""

import asyncio

import pytest

from app.services import live_watch


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Row:
    """Stands in for a SQLAlchemy Row, read the way the watcher reads one.

    Only `_mapping` is exposed. Attribute access is deliberately absent: the first
    version of this test let `row.t` work, while against a real Row `.t` is
    SQLAlchemy's own tuple accessor and returned the whole row — so every watermark
    was stored under a nonsense key and no change was ever reported. A double that
    allows what the library forbids cannot catch that.
    """

    def __init__(self, **fields):
        self._mapping = dict(fields)

    def __getitem__(self, index):
        return list(self._mapping.values())[index]


class _Session:
    """Answers the two statements the watcher makes, from a scripted study."""

    def __init__(self, state):
        self.state = state
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "UNION ALL" in sql or "MAX(`_id`)" in sql:
            return _Result(
                [
                    _Row(table_name=table, highest=highest)
                    for table, highest in self.state["max_ids"].items()
                ]
            )
        return _Result(
            [
                _Row(device=device, records=count)
                for device, count in self.state["new_rows"].items()
            ]
        )

    async def rollback(self):
        pass


def watcher_for(state, tables=("battery",), sensors=None):
    def factory():
        return _Session(state)

    async def tables_for(db, platform):
        return list(tables)

    async def refresh():
        # Counts how many times a tick brought the caches up to what it saw.
        state["refreshes"] = state.get("refreshes", 0) + 1

    # Android's tables map one-to-one onto sensors; an iPhone's `wifi` and `esm`
    # each span two, which is what the summing exists for.
    mapping = sensors or {table: table for table in tables}

    def sensor_for(platform):
        return mapping

    return live_watch.LiveWatch(
        sessions={"android": factory},
        tables_for=tables_for,
        sensor_for=sensor_for,
        refresh=refresh,
    )


@pytest.mark.asyncio
async def test_a_first_look_reports_nothing():
    """It establishes where the study stands. Reporting the whole history as new
    would move every tile the moment a dashboard opened."""
    state = {"max_ids": {"battery": 500}, "new_rows": {"phone-a": 500}}
    watch = watcher_for(state)

    assert await watch._collect() == []


@pytest.mark.asyncio
async def test_rows_arriving_after_the_first_look_are_reported():
    state = {"max_ids": {"battery": 500}, "new_rows": {}}
    watch = watcher_for(state)
    await watch._collect()

    state["max_ids"]["battery"] = 512
    state["new_rows"] = {"phone-a": 12}

    assert await watch._collect() == [
        {
            "platform": "android",
            "sensor": "battery",
            "device_id": "phone-a",
            "records": 12,
        }
    ]


@pytest.mark.asyncio
async def test_a_tick_with_no_new_rows_reports_nothing():
    state = {"max_ids": {"battery": 500}, "new_rows": {}}
    watch = watcher_for(state)
    await watch._collect()

    assert await watch._collect() == []


@pytest.mark.asyncio
async def test_a_row_belonging_to_no_device_is_not_reported():
    """The same rule every other reader follows: it belongs to no participant, so
    there is no tile for it to move."""
    state = {"max_ids": {"battery": 500}, "new_rows": {}}
    watch = watcher_for(state)
    await watch._collect()

    state["max_ids"]["battery"] = 505
    state["new_rows"] = {"": 5}

    assert await watch._collect() == []


@pytest.mark.asyncio
async def test_watermarks_are_asked_for_in_one_statement():
    """One round trip rather than one per table. The subqueries are primary-key
    lookups; the trips are what cost."""
    state = {
        "max_ids": {"battery": 1, "screen": 2, "wifi": 3},
        "new_rows": {},
    }
    session = _Session(state)

    watch = watcher_for(state, tables=("battery", "screen", "wifi"))
    await watch._max_ids(session, ["battery", "screen", "wifi"])

    assert len(session.statements) == 1
    assert session.statements[0].count("UNION ALL") == 2


def test_the_loop_idles_until_something_subscribes():
    watch = watcher_for({"max_ids": {}, "new_rows": {}})

    assert not watch._wake.is_set()
    subscriber, _, _ = watch.subscribe()
    assert watch._wake.is_set()

    watch.unsubscribe(subscriber)
    assert not watch._wake.is_set()


def test_a_departing_subscriber_leaves_no_watermarks_behind():
    """The next subscriber gets a fresh first look, so it is told what arrives from
    the moment it started watching rather than everything since the last one left."""
    watch = watcher_for({"max_ids": {}, "new_rows": {}})
    watch._watermarks[("android", "battery")] = 10

    subscriber, _, _ = watch.subscribe()
    watch.unsubscribe(subscriber)

    assert watch._watermarks == {}


def test_two_subscribers_share_one_loop():
    watch = watcher_for({"max_ids": {}, "new_rows": {}})
    first, _, _ = watch.subscribe()
    second, _, _ = watch.subscribe()

    assert watch.subscriber_count == 2

    watch._publish({"type": "changes", "changes": [{"records": 1}]})

    assert first.queue.qsize() == 1
    assert second.queue.qsize() == 1


def test_a_resuming_subscriber_receives_only_the_gap():
    watch = watcher_for({"max_ids": {}, "new_rows": {}})
    opener, _, _ = watch.subscribe()
    for _ in range(4):
        watch._publish({"type": "changes", "changes": []})
    watch.unsubscribe(opener)

    _, backlog, refetch = watch.subscribe(since=2)

    assert refetch is False
    assert [message["seq"] for message in backlog] == [3, 4]


def test_resuming_from_further_back_than_the_history_asks_for_a_refetch():
    """A gap silently skipped leaves a tile wrong with nothing to correct it."""
    watch = watcher_for({"max_ids": {}, "new_rows": {}})
    opener, _, _ = watch.subscribe()
    for _ in range(live_watch.HISTORY + 10):
        watch._publish({"type": "changes", "changes": []})
    watch.unsubscribe(opener)

    _, backlog, refetch = watch.subscribe(since=1)

    assert refetch is True
    assert backlog == []


def test_a_fresh_subscriber_gets_no_backlog():
    watch = watcher_for({"max_ids": {}, "new_rows": {}})
    opener, _, _ = watch.subscribe()
    watch._publish({"type": "changes", "changes": []})
    watch.unsubscribe(opener)

    _, backlog, refetch = watch.subscribe()

    assert backlog == []
    assert refetch is False


def test_a_heartbeat_does_not_consume_a_sequence_number():
    """It carries no news. Numbering it would let a client resume from a point it
    never actually received a change for."""
    watch = watcher_for({"max_ids": {}, "new_rows": {}})
    watch.subscribe()
    watch._publish({"type": "changes", "changes": []})

    before = watch.sequence
    beat = watch.publish_heartbeat()

    assert beat["type"] == "heartbeat"
    assert beat["seq"] == before
    assert watch.sequence == before


def test_a_subscriber_too_far_behind_is_flagged_rather_than_stalling_the_loop():
    """A slow reader must not hold up every other dashboard."""
    watch = watcher_for({"max_ids": {}, "new_rows": {}})
    subscriber, _, _ = watch.subscribe()

    for _ in range(subscriber.queue.maxsize + 5):
        watch._publish({"type": "changes", "changes": []})

    assert subscriber.overflowed is True
    assert subscriber.queue.full()


@pytest.mark.asyncio
async def test_a_failing_tick_does_not_kill_the_loop():
    """A database blip must cost a tick, not the channel."""

    class _Broken:
        def __call__(self):
            return self

        async def __aenter__(self):
            raise RuntimeError("database down")

        async def __aexit__(self, *_):
            return False

    async def tables_for(db, platform):
        return ["battery"]

    async def refresh():
        pass

    watch = live_watch.LiveWatch(
        sessions={"android": _Broken()},
        tables_for=tables_for,
        sensor_for=lambda platform: {"battery": "battery"},
        refresh=refresh,
    )
    watch.subscribe()
    watch.start()
    await asyncio.sleep(0.05)

    assert watch._task is not None and not watch._task.done()
    await watch.stop()


@pytest.mark.asyncio
async def test_a_sensor_stored_in_two_tables_arrives_as_one_delta():
    """An iPhone keeps `wifi` in `sensor_wifi` and `wifi`. A tile is a sensor, so
    two tables gaining rows is one change of the sum -- not two changes naming
    tables the interface has never heard of."""
    state = {"max_ids": {"sensor_wifi": 100, "wifi": 200}, "new_rows": {}}
    watch = watcher_for(
        state,
        tables=("sensor_wifi", "wifi"),
        sensors={"sensor_wifi": "wifi", "wifi": "wifi"},
    )
    await watch._collect()

    # Both tables advance by the same batch, three rows each.
    state["max_ids"] = {"sensor_wifi": 103, "wifi": 203}
    state["new_rows"] = {"phone-a": 3}

    assert await watch._collect() == [
        {"platform": "android", "sensor": "wifi", "device_id": "phone-a", "records": 6}
    ]


@pytest.mark.asyncio
async def test_a_table_no_sensor_claims_reports_nothing():
    """Android's `sensor_wifi` is claimed by no export entry, so a tile for it does
    not exist. Reporting it would name a sensor the interface cannot show."""
    state = {"max_ids": {"battery": 10, "sensor_wifi": 10}, "new_rows": {}}
    watch = watcher_for(
        state, tables=("battery", "sensor_wifi"), sensors={"battery": "battery"}
    )
    await watch._collect()

    state["max_ids"] = {"battery": 10, "sensor_wifi": 15}
    state["new_rows"] = {"phone-a": 5}

    assert await watch._collect() == []


@pytest.mark.asyncio
async def test_an_unclaimed_table_still_advances_its_watermark():
    """Otherwise every tick rescans the same rows it has already decided to ignore."""
    state = {"max_ids": {"sensor_wifi": 10}, "new_rows": {}}
    watch = watcher_for(state, tables=("sensor_wifi",), sensors={})
    await watch._collect()

    state["max_ids"] = {"sensor_wifi": 40}
    await watch._collect()

    assert watch._watermarks[("android", "sensor_wifi")] == 40


def test_a_client_ahead_of_the_server_is_told_to_refetch():
    """The API restarting puts the sequence back to zero while an open tab still
    remembers a high number. Told it was up to date, that tab would sit on tiles
    frozen at the restart with nothing ever correcting them."""
    watch = watcher_for({"max_ids": {}, "new_rows": {}})
    opener, _, _ = watch.subscribe()
    watch._publish({"type": "changes", "changes": []})
    watch.unsubscribe(opener)

    _, backlog, refetch = watch.subscribe(since=99999)

    assert refetch is True
    assert backlog == []


def test_a_client_exactly_up_to_date_is_left_alone():
    """The common reconnect: nothing happened while it was away."""
    watch = watcher_for({"max_ids": {}, "new_rows": {}})
    opener, _, _ = watch.subscribe()
    watch._publish({"type": "changes", "changes": []})
    watch.unsubscribe(opener)

    _, backlog, refetch = watch.subscribe(since=watch.sequence)

    assert refetch is False
    assert backlog == []


@pytest.mark.asyncio
async def test_a_tick_that_found_rows_refreshes_the_caches_before_announcing():
    """Every number a reader shows is read from the caches, which move only when a
    refresh runs. Announcing first would send every reader to refetch the totals it
    already has, and the arrival would look like it never happened."""
    state = {"max_ids": {"battery": 10}, "new_rows": {}}
    watch = watcher_for(state)
    watch.subscribe()
    await watch._collect()

    state["max_ids"]["battery"] = 14
    state["new_rows"] = {"phone-a": 4}
    changes = await watch._collect()
    assert changes
    await watch._fold_in()

    assert state["refreshes"] == 1


@pytest.mark.asyncio
async def test_a_refresh_that_fails_leaves_the_channel_running():
    """A stale cache is worth less than a dead channel: the scheduled pass folds the
    same rows in, and the fallback poll is what picks them up."""

    async def refresh():
        raise RuntimeError("lock wait timeout")

    async def tables_for(db, platform):
        return ["battery"]

    watch = live_watch.LiveWatch(
        sessions={},
        tables_for=tables_for,
        sensor_for=lambda platform: {"battery": "battery"},
        refresh=refresh,
    )

    await watch._fold_in()
