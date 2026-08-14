"""What an archive is called, and what it says about itself.

An export leaves the dashboard and becomes a file in somebody's downloads
folder, next to several others from several studies. From that point on the only
things that can say what it holds are its name and what is inside it — so the
window is in both, resolved to absolute instants rather than left as the relative
period that was clicked.
"""

import json
import zipfile

import pytest

from app.routers import export as export_router

HOUR = 60 * 60 * 1000
NOON = 1_786_708_800_000  # 2026-08-14 12:00:00 UTC, hour-aligned


@pytest.fixture(autouse=True)
def study(monkeypatch):
    """A deployment whose study has a name."""

    class _Deployed:
        summary = {"study_title": "Sleep and Mood 2026"}

    monkeypatch.setattr(
        export_router.study_config, "load_deployed_config", lambda: _Deployed()
    )


def test_the_archive_is_named_after_the_study(study):
    name = export_router._archive_name("all", export_router.ALL_TIME)

    assert name.startswith("Sleep_and_Mood_2026-")
    assert name.endswith(".zip")


def test_a_window_appears_in_the_name_as_absolute_instants():
    """`last 24 hours` means nothing once the file is a month old."""
    name = export_router._archive_name("all", (NOON - 24 * HOUR, NOON))

    assert "20260813-1200-to-20260814-1200" in name


def test_all_time_says_so_rather_than_carrying_no_window():
    assert export_router._archive_name("all", export_router.ALL_TIME).endswith(
        "-all-time.zip"
    )


@pytest.mark.parametrize(
    "window, expected",
    [
        ((None, NOON), "to-20260814-1200"),
        ((NOON, None), "from-20260814-1200"),
    ],
)
def test_a_half_open_window_names_the_end_it_has(window, expected):
    assert expected in export_router._archive_name("all", window)


def test_the_scope_stays_in_the_name():
    """A sensor export and a device export of the same period would otherwise
    land in the folder under the same name."""
    window = (NOON - HOUR, NOON)
    sensor = export_router._archive_name("android-accelerometer", window)
    device = export_router._archive_name("android-phone_a", window)

    assert sensor != device
    assert "accelerometer" in sensor and "phone_a" in device


def test_a_deployment_with_no_config_still_names_its_archive(monkeypatch):
    """The config is written at deployment time, so its absence is a normal
    state rather than a reason to fail a download."""
    monkeypatch.setattr(
        export_router.study_config, "load_deployed_config", lambda: None
    )

    assert export_router._archive_name("all", export_router.ALL_TIME).startswith("aware-")


def test_a_study_name_cannot_escape_the_filename(monkeypatch):
    """The title comes from a deployed config file, and a name is a path."""

    class _Deployed:
        summary = {"study_title": "../../etc/passwd"}

    monkeypatch.setattr(
        export_router.study_config, "load_deployed_config", lambda: _Deployed()
    )
    name = export_router._archive_name("all", export_router.ALL_TIME)

    assert "/" not in name and ".." not in name


def test_the_manifest_records_the_window_it_was_taken_for():
    manifest = export_router._export_manifest("all", (NOON - HOUR, NOON))

    assert manifest["study"] == "Sleep_and_Mood_2026"
    assert manifest["scope"] == "all"
    assert manifest["window"]["from"] == NOON - HOUR
    assert manifest["window"]["from_utc"].startswith("2026-08-14T11:00")
    assert manifest["window"]["all_time"] is False
    assert manifest["window"]["bounds"] == "inclusive"


def test_an_all_time_manifest_says_so():
    manifest = export_router._export_manifest("all", export_router.ALL_TIME)

    assert manifest["window"]["all_time"] is True
    assert manifest["window"]["from"] is None
    assert manifest["window"]["from_utc"] is None


def test_the_manifest_carries_a_generation_time():
    assert export_router._export_manifest("all", export_router.ALL_TIME)["generated_at"]


def test_the_manifest_promises_no_row_count():
    """An hour-granular estimate beside exact CSVs reads as missing data. The
    rows in the archive are the answer."""
    assert "rows_expected" not in export_router._export_manifest("all", export_router.ALL_TIME)


@pytest.mark.asyncio
async def test_the_manifest_is_the_first_member_of_the_archive():
    """An interrupted download still leaves a file that says what it was."""

    async def members():
        yield ("android_accelerometer.csv", ["timestamp"], _batches())

    async def _batches():
        yield [{"timestamp": 1}]

    manifest = export_router._export_manifest("all", (NOON - HOUR, NOON))
    body = b"".join(
        [chunk async for chunk in export_router._stream_archive(members(), None, manifest)]
    )

    import io

    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        assert names[0] == export_router.MANIFEST_MEMBER
        written = json.loads(archive.read(export_router.MANIFEST_MEMBER))

    assert written["window"]["from"] == NOON - HOUR
    assert "android_accelerometer.csv" in names


@pytest.mark.asyncio
async def test_an_archive_without_a_manifest_is_unchanged():
    """Nothing else writes one, and the parameter is optional so the existing
    members stay exactly where they were."""

    async def members():
        yield ("a.csv", ["x"], _batches())

    async def _batches():
        yield [{"x": 1}]

    body = b"".join([chunk async for chunk in export_router._stream_archive(members())])

    import io

    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert archive.namelist() == ["a.csv"]
