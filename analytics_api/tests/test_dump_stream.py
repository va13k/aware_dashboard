"""DumpRewriter over hand-written mysqldump fragments.

No MySQL runs: the rewriter is a pure byte-in/byte-out transform, so these feed
it the statements mysqldump actually emits and assert on what comes back. The
cases that matter are the ones where a naive rewrite loses or duplicates rows —
values containing the tuple delimiters, and the `_id` column that means nothing
across two deployments.
"""

from app.services import dump_stream
from app.services.dump_stream import MERGE, REPLACE, DumpRewriter

CREATE = [
    b"CREATE TABLE `locations` (\n",
    b"  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,\n",
    b"  `timestamp` double DEFAULT '0',\n",
    b"  `device_id` varchar(150) DEFAULT '',\n",
    b"  `double_latitude` double DEFAULT '0',\n",
    b"  `label` text,\n",
    b"  PRIMARY KEY (`_id`),\n",
    b"  KEY `time_device` (`timestamp`,`device_id`)\n",
    b") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n",
]


def run(rewriter, lines):
    return b"".join(rewriter.feed(line) for line in lines)


def prepared(watermarks=None):
    """A rewriter that has already read the locations definition."""
    rewriter = DumpRewriter(MERGE, watermarks or {})
    run(rewriter, [b"USE `aware_android`;\n", *CREATE])
    return rewriter


def test_replace_mode_passes_every_line_through():
    rewriter = DumpRewriter(REPLACE)
    lines = [b"DROP TABLE IF EXISTS `locations`;\n", *CREATE]
    assert run(rewriter, lines) == b"".join(lines)


def test_merge_keeps_the_stored_table_and_creates_a_missing_one():
    rewriter = DumpRewriter(MERGE)
    output = run(rewriter, [b"DROP TABLE IF EXISTS `locations`;\n", *CREATE])
    assert b"DROP TABLE" not in output
    assert b"CREATE TABLE IF NOT EXISTS `locations`" in output


def test_merge_drops_the_id_column_so_rows_take_fresh_identity():
    rewriter = prepared()
    insert = b"INSERT INTO `locations` VALUES (1,100,'phone-a',0.5,NULL);\n"
    output = rewriter.feed(insert)
    assert output == (
        b"INSERT INTO `locations` "
        b"(`timestamp`,`device_id`,`double_latitude`,`label`) "
        b"VALUES (100,'phone-a',0.5,NULL);\n"
    )


def test_merge_admits_only_rows_newer_than_the_device_watermark():
    rewriter = prepared({("aware_android", "locations"): {"phone-a": 200.0}})
    insert = (
        b"INSERT INTO `locations` VALUES "
        b"(1,100,'phone-a',0.5,NULL),"
        b"(2,200,'phone-a',0.6,NULL),"
        b"(3,300,'phone-a',0.7,NULL);\n"
    )
    output = rewriter.feed(insert)
    assert b"(300,'phone-a',0.7,NULL)" in output
    assert b"'phone-a',0.5" not in output
    assert b"'phone-a',0.6" not in output


def test_a_device_with_nothing_stored_keeps_all_of_its_rows():
    rewriter = prepared({("aware_android", "locations"): {"phone-a": 200.0}})
    insert = (
        b"INSERT INTO `locations` VALUES "
        b"(1,100,'phone-b',0.5,NULL),"
        b"(2,150,'phone-b',0.6,NULL);\n"
    )
    output = rewriter.feed(insert)
    assert b"(100,'phone-b',0.5,NULL)" in output
    assert b"(150,'phone-b',0.6,NULL)" in output


def test_a_fully_stored_statement_contributes_nothing():
    rewriter = prepared({("aware_android", "locations"): {"phone-a": 500.0}})
    insert = b"INSERT INTO `locations` VALUES (1,100,'phone-a',0.5,NULL);\n"
    assert rewriter.feed(insert) == b""


def test_values_containing_the_tuple_delimiters_survive_intact():
    """A label of `),(` is the shape that breaks splitting on punctuation."""
    rewriter = prepared()
    insert = (
        b"INSERT INTO `locations` VALUES "
        b"(1,100,'phone-a',0.5,'end),(start'),"
        b"(2,200,'phone-a',0.6,'quote \\' and comma, here');\n"
    )
    output = rewriter.feed(insert)
    assert b"(100,'phone-a',0.5,'end),(start')" in output
    assert b"(200,'phone-a',0.6,'quote \\' and comma, here')" in output


def test_an_escaped_backslash_before_a_quote_ends_the_string():
    rewriter = prepared()
    insert = (
        b"INSERT INTO `locations` VALUES "
        b"(1,100,'phone-a',0.5,'trailing slash\\\\'),"
        b"(2,200,'phone-a',0.6,'next');\n"
    )
    output = rewriter.feed(insert)
    assert b"(100,'phone-a',0.5,'trailing slash\\\\')" in output
    assert b"(200,'phone-a',0.6,'next')" in output


def test_row_tallies_report_what_was_added_and_skipped():
    seen = []
    rewriter = DumpRewriter(
        MERGE,
        {("aware_android", "locations"): {"phone-a": 200.0}},
        on_rows=lambda table, added, skipped: seen.append((table, added, skipped)),
    )
    run(rewriter, [b"USE `aware_android`;\n", *CREATE])
    rewriter.feed(
        b"INSERT INTO `locations` VALUES "
        b"(1,100,'phone-a',0.5,NULL),"
        b"(2,300,'phone-a',0.7,NULL);\n"
    )
    assert seen == [("locations", 1, 1)]


def test_the_count_cache_is_left_out_of_a_merge():
    """record_counts describes one deployment's tables, so a foreign copy of it
    is bookkeeping to discard rather than data to merge."""
    rewriter = DumpRewriter(MERGE)
    lines = [
        b"USE `aware_android`;\n",
        b"CREATE TABLE `record_counts` (\n",
        b"  `sensor` varchar(64) NOT NULL,\n",
        b"  `device_id` varchar(150) NOT NULL,\n",
        b") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n",
        b"INSERT INTO `record_counts` VALUES ('locations','phone-a',5,9,100);\n",
    ]
    output = run(rewriter, lines)
    assert b"record_counts" not in output


def test_watermarks_are_scoped_to_the_database_in_use():
    """Both platform databases have a `locations`, so the table name alone
    cannot pick the right watermark."""
    marks = {
        ("aware_android", "locations"): {"phone-a": 500.0},
        ("aware_ios", "locations"): {"phone-a": 10.0},
    }
    rewriter = DumpRewriter(MERGE, marks)
    run(rewriter, [b"USE `aware_ios`;\n", *CREATE])
    output = rewriter.feed(
        b"INSERT INTO `locations` VALUES (1,100,'phone-a',0.5,NULL);\n"
    )
    assert b"(100,'phone-a',0.5,NULL)" in output


def test_a_table_without_an_id_column_is_left_alone():
    rewriter = DumpRewriter(MERGE)
    lines = [
        b"USE `aware_android`;\n",
        b"CREATE TABLE `settings` (\n",
        b"  `name` varchar(64) NOT NULL,\n",
        b"  `value` text,\n",
        b") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n",
    ]
    run(rewriter, lines)
    insert = b"INSERT INTO `settings` VALUES ('a','b');\n"
    assert rewriter.feed(insert) == insert


def test_an_explicit_column_list_on_the_insert_is_respected():
    rewriter = DumpRewriter(MERGE, {("aware_android", "locations"): {"phone-a": 50.0}})
    rewriter.feed(b"USE `aware_android`;\n")
    insert = (
        b"INSERT INTO `locations` (`_id`,`timestamp`,`device_id`) "
        b"VALUES (1,100,'phone-a');\n"
    )
    output = rewriter.feed(insert)
    assert output == (
        b"INSERT INTO `locations` (`timestamp`,`device_id`) "
        b"VALUES (100,'phone-a');\n"
    )


def test_tuple_end_reports_the_byte_after_the_closing_paren():
    line = b"(1,'a'),(2,'b')"
    assert dump_stream._tuple_end(line, 0) == 7
    assert line[:7] == b"(1,'a')"
