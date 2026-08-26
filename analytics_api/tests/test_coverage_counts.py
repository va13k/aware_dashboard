"""What a period holds, as the export dialog asks it.

The rollup answers per table and the dialog asks per sensor, so the round trip
through that mapping is what these cover: a sensor stored in two tables has to
come back as one number, and a table no sensor claims must not be counted under
a guess. Both failures are silent — the dialog just shows a figure that does not
match what the download produces.

The rollup arithmetic underneath is covered against a real MySQL in
test_integration_export_window.py.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import coverage as coverage_router
from app.services import sensor_tables


class Counted(tuple):
    """``(holdings, asked)``, carrying the exclusion knobs beside them.

    A tuple so the counting tests keep unpacking two values, with the exclusion
    state reachable by name for the tests that set it.
    """

    #: Devices the researcher took out, per platform.
    excluded: dict
    #: What those devices hold, per platform and keyed by table.
    held_back: dict
    #: How many of them the rollup shows records for, per platform.
    held_back_devices: dict
    #: ``(platform, exclude, only)`` for each read, as the rollup received it.
    filtered: list


@pytest.fixture
def counted(monkeypatch):
    """Lets a test say what the rollup holds, per platform, keyed by table.

    `holdings` is what arrived. `held_back` is the part of it belonging to
    excluded devices, so a read that passes the exclusion set gets the remainder
    and a read that asks `only` about them gets that part — which is how the
    rollup itself answers, and what makes a router that forgets to narrow show
    up as a wrong total rather than as an unasserted argument.
    """
    holdings: dict[str, dict[str, int]] = {"android": {}, "ios": {}}
    asked: list[tuple] = []
    excluded: dict[str, set] = {"android": set(), "ios": set()}
    held_back: dict[str, dict[str, int]] = {"android": {}, "ios": {}}
    held_back_devices: dict[str, int] = {"android": 0, "ios": 0}
    filtered: list[tuple] = []

    def platform_of(model):
        return "ios" if "Ios" in model.__name__ else "android"

    def narrowed(held, tables):
        if tables is None:
            return dict(held)
        return {name: held[name] for name in tables if name in held}

    async def records_by_table(
        db, model, window, tables=None, device_id=None, exclude=None, only=None
    ):
        platform = platform_of(model)
        asked.append((platform, window, tuple(tables) if tables else None))
        filtered.append(
            (
                platform,
                frozenset(exclude or ()),
                None if only is None else frozenset(only),
            )
        )
        # `only` asks the opposite question of `exclude`: what the devices left
        # out of the analysis hold, rather than what remains without them.
        if only is not None:
            return narrowed(held_back[platform], tables)
        arrived = holdings[platform]
        if exclude:
            arrived = {
                table: count - held_back[platform].get(table, 0)
                for table, count in arrived.items()
            }
            arrived = {table: count for table, count in arrived.items() if count > 0}
        return narrowed(arrived, tables)

    async def devices_with_records(
        db, model, window, tables=None, device_id=None, only=None
    ):
        return held_back_devices[platform_of(model)] if only is not None else 0

    async def excluded_ids(db, model):
        return set(excluded["ios" if "Ios" in model.__name__ else "android"])

    async def bytes_per_row(db, database):
        # A stored byte per row for every table, so a count of N estimates to
        # N * CSV_ZIP_FACTOR bytes and the arithmetic is checkable by eye.
        return {table: 1.0 for held in holdings.values() for table in held}

    monkeypatch.setattr(
        coverage_router.coverage_rollup, "records_by_table", records_by_table
    )
    monkeypatch.setattr(
        coverage_router.coverage_rollup, "devices_with_records", devices_with_records
    )
    monkeypatch.setattr(coverage_router.exclusions, "excluded_ids", excluded_ids)
    monkeypatch.setattr(coverage_router.export_size, "bytes_per_row", bytes_per_row)

    state = Counted((holdings, asked))
    state.excluded = excluded
    state.held_back = held_back
    state.held_back_devices = held_back_devices
    state.filtered = filtered
    return state


@pytest.fixture
def client(counted):
    app = FastAPI()
    app.include_router(coverage_router.router)

    async def session():
        yield None

    app.dependency_overrides[coverage_router.get_android_db] = session
    app.dependency_overrides[coverage_router.get_ios_db] = session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def android_table(sensor: str) -> str:
    return sensor_tables.tables_for(coverage_router.ANDROID_EXPORT_MODELS, sensor)[0]


def test_a_period_reports_a_total_across_both_platforms(client, counted):
    holdings, _ = counted
    holdings["android"][android_table("accelerometer")] = 30
    holdings["ios"]["accelerometer"] = 12

    body = client.get("/coverage/counts?from_ts=1000&to_ts=2000").json()

    assert body["total"] == 42
    assert body["platforms"] == {"android": 30, "ios": 12}
    assert (body["from"], body["to"]) == (1000, 2000)


def test_the_window_reaches_the_rollup_as_given(client, counted):
    _, asked = counted
    client.get("/coverage/counts?from_ts=1000&to_ts=2000")

    assert all(window == (1000, 2000) for _, window, _ in asked)


def test_no_period_asks_about_everything_stored(client, counted):
    """`all time` is a choice the dialog offers explicitly, so it has to be
    answerable rather than rejected for want of bounds."""
    holdings, asked = counted
    holdings["android"][android_table("accelerometer")] = 5

    body = client.get("/coverage/counts").json()

    assert body["total"] == 5
    assert all(window == (None, None) for _, window, _ in asked)


def test_a_reversed_period_reads_as_the_range_it_means(client, counted):
    _, asked = counted
    client.get("/coverage/counts?from_ts=9000&to_ts=1000")

    assert all(window == (1000, 9000) for _, window, _ in asked)


def test_a_sensor_split_over_two_tables_comes_back_as_one_number(client, counted):
    """`esm` and `wifi` live in two tables each. Reporting them twice, or as the
    larger half, is the failure the table-keyed rollup exists to avoid."""
    holdings, _ = counted
    tables = sensor_tables.tables_for(coverage_router.IOS_EXPORT_MODELS, "esm")
    assert len(tables) >= 2, "this test needs a genuinely multi-table sensor"
    for index, table in enumerate(tables):
        holdings["ios"][table] = 10 * (index + 1)

    body = client.get("/coverage/counts?platform=ios&sensor=esm").json()

    assert body["sensors"]["ios"]["esm"] == sum(10 * (i + 1) for i in range(len(tables)))
    assert body["total"] == body["sensors"]["ios"]["esm"]


def test_a_table_no_sensor_claims_is_not_counted(client, counted):
    """The rollup covers every timestamped table, including ones the export does
    not serve. Folding those into a total makes the dialog promise rows the
    download will never contain."""
    holdings, _ = counted
    holdings["android"][android_table("accelerometer")] = 10
    holdings["android"]["some_table_the_api_does_not_serve"] = 999

    body = client.get("/coverage/counts?platform=android").json()

    assert body["total"] == 10


def test_asking_for_one_sensor_asks_the_rollup_for_only_its_tables(client, counted):
    """The point of passing the table list down is that the database narrows the
    read rather than the router filtering a full scan afterwards."""
    _, asked = counted
    client.get("/coverage/counts?platform=android&sensor=accelerometer")

    (_, _, tables), = asked
    assert tables == tuple(
        sensor_tables.tables_for(coverage_router.ANDROID_EXPORT_MODELS, "accelerometer")
    )


def test_an_unknown_sensor_holds_nothing_rather_than_everything(client, counted):
    holdings, _ = counted
    holdings["android"][android_table("accelerometer")] = 10

    body = client.get("/coverage/counts?sensor=not_a_sensor").json()

    assert body["total"] == 0
    assert body["available"] is False


def test_a_platform_filter_leaves_the_other_side_out(client, counted):
    holdings, _ = counted
    holdings["android"][android_table("accelerometer")] = 30
    holdings["ios"]["accelerometer"] = 12

    body = client.get("/coverage/counts?platform=android").json()

    assert body["platforms"] == {"android": 30}
    assert "ios" not in body["platforms"]


def test_an_unknown_platform_is_refused(client):
    assert client.get("/coverage/counts?platform=windows_phone").status_code == 404


def test_an_empty_period_is_reported_as_unavailable(client):
    """A dialog needs to know not to offer the download at all."""
    body = client.get("/coverage/counts?from_ts=1&to_ts=2").json()

    assert body["total"] == 0
    assert body["available"] is False


def test_the_answer_estimates_what_the_download_will_weigh(client, counted):
    """A record count does not say whether this is a few megabytes or a few
    gigabytes, which is the decision the researcher is actually making."""
    holdings, _ = counted
    holdings["android"][android_table("accelerometer")] = 1_000_000

    body = client.get("/coverage/counts?platform=android").json()

    assert body["estimated_bytes"] == int(
        1_000_000 * 1.0 * coverage_router.export_size.CSV_ZIP_FACTOR
    )


def test_an_empty_period_is_estimated_at_nothing(client):
    assert client.get("/coverage/counts?from_ts=1&to_ts=2").json()["estimated_bytes"] == 0


def test_the_answer_says_it_is_hour_granular(client, counted):
    """A caller comparing this with a row count needs to know why they differ,
    without having to read the rollup's source to find out."""
    holdings, _ = counted
    holdings["android"][android_table("accelerometer")] = 1

    assert client.get("/coverage/counts").json()["hour_granular"] is True


def test_a_device_narrows_the_count_to_that_phone(client, counted, monkeypatch):
    """A device export covers one phone, so the dialog beside it must not report
    what the whole study holds — the figure would be wildly larger than the
    archive the button produces."""
    holdings, _ = counted
    holdings["android"][android_table("accelerometer")] = 500
    asked_for: list = []

    async def records_by_table(
        db, model, window, tables=None, device_id=None, exclude=None, only=None
    ):
        asked_for.append(device_id)
        return {} if device_id else dict(holdings["android"])

    monkeypatch.setattr(
        coverage_router.coverage_rollup, "records_by_table", records_by_table
    )

    body = client.get("/coverage/counts?platform=android&device=phone-a").json()

    assert asked_for == ["phone-a"]
    assert body["total"] == 0


def test_no_device_asks_about_every_phone(client, counted):
    holdings, _ = counted
    holdings["android"][android_table("accelerometer")] = 500

    assert client.get("/coverage/counts?platform=android").json()["total"] == 500


class TestExclusion:
    """A period reports the dataset the download writes, and accounts for the rest.

    The dialog's figure and the archive it starts come from two different reads,
    so nothing but a test keeps them saying the same thing. An excluded
    participant holding most of a study is the case where the two diverge most
    visibly: the researcher is shown a number several times larger than the file
    they receive.
    """

    def test_the_total_leaves_excluded_devices_out(self, client, counted):
        """930 rows arrived and 900 of them belong to an excluded phone, so the
        download is 30 and that is the figure the dialog has to show."""
        holdings, _ = counted
        holdings["android"][android_table("accelerometer")] = 930
        counted.excluded["android"] = {"phone-out"}
        counted.held_back["android"][android_table("accelerometer")] = 900

        body = client.get("/coverage/counts?platform=android").json()

        assert body["total"] == 30
        assert body["platforms"]["android"] == 30

    def test_the_exclusion_reaches_the_rollup_rather_than_being_filtered_after(
        self, client, counted
    ):
        """The database narrows the read: a router summing everything and
        subtracting afterwards would need every excluded device's rows first."""
        holdings, _ = counted
        holdings["android"][android_table("accelerometer")] = 30
        counted.excluded["android"] = {"phone-out"}

        client.get("/coverage/counts?platform=android")

        analysis_reads = [
            exclude for _, exclude, only in counted.filtered if only is None
        ]
        assert analysis_reads == [frozenset({"phone-out"})]

    def test_the_answer_says_what_the_exclusion_holds_back(self, client, counted):
        holdings, _ = counted
        holdings["android"][android_table("accelerometer")] = 930
        counted.excluded["android"] = {"phone-out"}
        counted.held_back["android"][android_table("accelerometer")] = 900
        counted.held_back_devices["android"] = 1

        body = client.get("/coverage/counts?platform=android").json()

        assert body["excluded"] == {"devices": 1, "records": 900}

    def test_the_held_back_figure_is_asked_of_the_same_scope(self, client, counted):
        """A sensor dialog accounts for that sensor: the two figures beside each
        other have to be answers to the same question."""
        holdings, _ = counted
        holdings["android"][android_table("accelerometer")] = 30
        counted.excluded["android"] = {"phone-out"}

        client.get("/coverage/counts?platform=android&sensor=accelerometer")

        wanted = tuple(
            sensor_tables.tables_for(
                coverage_router.ANDROID_EXPORT_MODELS, "accelerometer"
            )
        )
        assert all(tables == wanted for _, _, tables in counted[1])

    def test_nothing_excluded_holds_nothing_back(self, client, counted):
        holdings, _ = counted
        holdings["android"][android_table("accelerometer")] = 30

        body = client.get("/coverage/counts?platform=android").json()

        assert body["excluded"] == {"devices": 0, "records": 0}
        assert all(only is None for _, _, only in counted.filtered)

    def test_a_period_holding_only_excluded_data_is_not_offered(
        self, client, counted
    ):
        """The archive would be empty, so the button should not be pressable."""
        holdings, _ = counted
        holdings["android"][android_table("accelerometer")] = 900
        counted.excluded["android"] = {"phone-out"}
        counted.held_back["android"][android_table("accelerometer")] = 900
        counted.held_back_devices["android"] = 1

        body = client.get("/coverage/counts?platform=android").json()

        assert body["total"] == 0
        assert body["available"] is False
        assert body["excluded"]["records"] == 900

    def test_the_size_estimate_follows_the_analysis_dataset(self, client, counted):
        """A magnitude for the file that arrives, not for the rows behind it."""
        holdings, _ = counted
        holdings["android"][android_table("accelerometer")] = 1_001_000
        counted.excluded["android"] = {"phone-out"}
        counted.held_back["android"][android_table("accelerometer")] = 1_000_000

        body = client.get("/coverage/counts?platform=android").json()

        assert body["estimated_bytes"] == int(
            1_000 * 1.0 * coverage_router.export_size.CSV_ZIP_FACTOR
        )

    def test_a_device_scope_reports_that_phones_own_rows(self, client, counted):
        """A device export writes the phone it names, excluded or not, so the
        figure beside it counts that phone rather than the analysis dataset."""
        holdings, _ = counted
        holdings["android"][android_table("accelerometer")] = 930
        counted.excluded["android"] = {"phone-out"}
        counted.held_back["android"][android_table("accelerometer")] = 900

        body = client.get(
            "/coverage/counts?platform=android&device=phone-out"
        ).json()

        assert body["total"] == 930
        assert body["excluded"] == {"devices": 0, "records": 0}
        assert all(exclude == frozenset() for _, exclude, _ in counted.filtered)
