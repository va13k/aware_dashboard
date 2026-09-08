"""Tests for the two lists of tables a backup leaves out, which differ on purpose.

A study is archived two ways, and they do not carry the same thing. The scheduled
job dumps whole databases and leaves out the three tables the API rebuilds from what
it restores. The backup page leaves out those three and two more, because one list
serves both a whole export and one narrowed to a period, and a period is applied as
a single condition on `timestamp` that none of these tables has a column for.

The two extra are `refusals` and `device_exclusions`, and they are the reason this
is worth a test rather than a comment. Both hold something no dump rebuilds: an
exclusion is a researcher's decision about a participant. The scheduled archive is
therefore where that decision survives, and a change to either list that closed the
gap silently would take it away.

The shell comment beside one of these lists claimed for a while that it mirrored the
other. It held three of the other's five.
"""

import pathlib
import re

PROJECT = pathlib.Path(__file__).resolve().parent.parent

#: Left out of a page export on top of the three the API rebuilds. Named here so a
#: change to either list has to say what it means to do about them.
DECISIONS_THE_ARCHIVE_KEEPS = {"refusals", "device_exclusions"}


def skipped_by_the_scheduled_dump() -> set[str]:
    text = (PROJECT / "setup" / "mysql-backup" / "backup.sh").read_text(encoding="utf-8")
    default = re.search(r"BACKUP_SKIP_TABLES=\"\$\{BACKUP_SKIP_TABLES:-([^}]*)\}\"", text)
    assert default, "backup.sh no longer declares BACKUP_SKIP_TABLES with a default"
    return set(default.group(1).split())


def skipped_by_a_page_export() -> set[str]:
    text = (PROJECT / "analytics_api" / "app" / "services" / "dump_stream.py").read_text(
        encoding="utf-8"
    )
    block = re.search(r"CACHE_TABLES = frozenset\(\s*\{(.*?)\}\s*\)", text, re.S)
    assert block, "dump_stream.py no longer declares CACHE_TABLES as a set literal"
    return set(re.findall(r'"([^"]+)"', block.group(1)))


def columns_of(table: str) -> list[str]:
    """The columns the deployed schema gives a table."""
    schema = (PROJECT / "db" / "init_all.sql").read_text(encoding="utf-8")
    body = re.search(
        rf"CREATE TABLE IF NOT EXISTS `{table}`\s*\((.*?)\n\)", schema, re.S
    )
    assert body, f"{table} is not declared in the deployed schema"
    return re.findall(r"^\s*`([^`]+)`", body.group(1), re.MULTILINE)


def test_the_archive_leaves_out_nothing_the_page_export_keeps():
    """A table in the nightly archive's list has to be one the page drops as well.

    The other way round is the deliberate difference; this way round would be a
    table the archive quietly lacks and a researcher would expect to find in it.
    """
    scheduled = skipped_by_the_scheduled_dump()
    page = skipped_by_a_page_export()

    assert scheduled <= page, f"only the scheduled dump skips {sorted(scheduled - page)}"


def test_the_page_export_leaves_out_the_two_decisions_as_well():
    difference = skipped_by_a_page_export() - skipped_by_the_scheduled_dump()

    assert difference == DECISIONS_THE_ARCHIVE_KEEPS, (
        f"the two lists differ by {sorted(difference)}, and the difference this "
        f"deployment means is {sorted(DECISIONS_THE_ARCHIVE_KEEPS)}"
    )


def test_none_of_them_carries_the_column_a_period_filters_on():
    """Why one list covers both a whole export and one narrowed to a period."""
    for table in sorted(skipped_by_a_page_export()):
        assert "timestamp" not in columns_of(table), (
            f"{table} carries a timestamp, so a ranged export could filter it and "
            "would not have to leave it out"
        )
