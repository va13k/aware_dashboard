"""Rewrites a mysqldump stream on its way into MySQL.

A dump produced by ``mysqldump --databases`` recreates what it restores: every
table is dropped, created and refilled, so a restore replaces the server's
contents. Merging a dump into a live database instead means editing the stream
as it goes past — keep the schema statements harmless, and admit only the rows
the target does not already hold.

Two properties of the AWARE schema decide how the merge works:

* ``_id`` is a per-instance ``AUTO_INCREMENT`` primary key, so the same ``_id``
  names unrelated records in two deployments. Merged rows therefore leave their
  ``_id`` behind and take fresh values from the target, which also places them
  above the ``record_counts`` watermark so the incremental refresh picks them up.
* No table carries a unique key over the data itself, so "already have this row"
  has to be answered from outside the schema. It is answered per
  ``(table, device_id)`` by the newest timestamp already stored, which
  ``record_counts.last_ts`` maintains — an in-memory lookup per row, with no
  staging copy on disk and no probe into the target table.

mysqldump escapes newlines inside string literals, so a statement never spans a
line break and the whole stream can be handled a line at a time.
"""

import re

REPLACE = "replace"
MERGE = "merge"

#: The dashboard's own caches are per-deployment bookkeeping, not study data.
#: They are rebuilt from the merged rows afterwards, so a merge skips them rather
#: than folding a foreign deployment's tallies into them. A period export leaves
#: them out for a second reason: neither carries a `timestamp` column, and the
#: single `--where` a ranged dump applies to every table would fail on them.
MERGE_SKIP_TABLES = frozenset({"record_counts", "coverage_hourly"})

_QUOTE = ord("'")
_BACKSLASH = ord("\\")

# Inside a string literal a backslash escapes the next byte and a quote ends it.
_IN_STRING = re.compile(rb"['\\]")
# Outside one, a quote opens a string and a close paren ends the row tuple.
_OUT_STRING = re.compile(rb"[')]")

_USE = re.compile(rb"^USE\s+`([^`]+)`", re.IGNORECASE)
_CREATE_DATABASE = re.compile(rb"^CREATE\s+DATABASE\s", re.IGNORECASE)
_DROP_TABLE = re.compile(rb"^DROP\s+TABLE\s", re.IGNORECASE)
_CREATE_TABLE = re.compile(rb"^CREATE\s+TABLE\s+`([^`]+)`", re.IGNORECASE)
_INSERT = re.compile(
    rb"^INSERT\s+(?:IGNORE\s+)?INTO\s+`([^`]+)`\s*(\(([^)]*)\))?\s*VALUES\s*",
    re.IGNORECASE,
)
# A column definition inside CREATE TABLE: indented, and the backtick-quoted
# name comes first. Key and constraint lines lead with their keyword instead.
_COLUMN = re.compile(rb"^\s+`([^`]+)`\s+\S")


def _tuple_end(line: bytes, open_at: int) -> int:
    """Index just past the ``)`` that closes the row tuple opening at `open_at`.

    Row values are literals, so the only parenthesis worth tracking is the
    closing one, and the only thing that can hide it is a quoted string.
    """
    i = open_at + 1
    in_string = False
    while True:
        pattern = _IN_STRING if in_string else _OUT_STRING
        match = pattern.search(line, i)
        if match is None:
            return -1
        at = match.start()
        char = line[at]
        if in_string:
            if char == _BACKSLASH:
                i = at + 2
            else:
                in_string = False
                i = at + 1
        elif char == _QUOTE:
            in_string = True
            i = at + 1
        else:
            return at + 1


def _row_tuples(line: bytes, start: int):
    """Yield each ``( ... )`` row tuple in the VALUES list, verbatim."""
    at = line.find(b"(", start)
    while at != -1:
        end = _tuple_end(line, at)
        if end == -1:
            return
        yield line[at:end]
        at = line.find(b"(", end)


def _next_field(body: bytes, start: int) -> tuple[bytes, int]:
    """The literal beginning at `start` and the index just past its comma."""
    if start < len(body) and body[start] == _QUOTE:
        i = start + 1
        while i < len(body):
            match = _IN_STRING.search(body, i)
            if match is None:
                return body[start:], len(body)
            if body[match.start()] == _BACKSLASH:
                i = match.start() + 2
                continue
            end = match.start() + 1
            return body[start:end], end + 1
        return body[start:], len(body)

    comma = body.find(b",", start)
    if comma == -1:
        return body[start:], len(body)
    return body[start:comma], comma + 1


def _unquote(value: bytes) -> str:
    if len(value) >= 2 and value[0] == _QUOTE:
        value = value[1:-1]
    return value.decode("utf-8", errors="replace")


class DumpRewriter:
    """Turns dump lines into the statements that should actually run.

    `watermarks` maps ``(database, table)`` to ``{device_id: newest timestamp}``.
    A table missing from it, or a device missing from its map, has nothing
    stored locally and so keeps every row offered.

    `on_rows` is called as ``(table, added, skipped)`` per statement, letting the
    caller tally progress without the rewriter knowing about jobs.
    """

    def __init__(self, mode: str, watermarks: dict | None = None, on_rows=None):
        self.mode = mode
        self.watermarks = watermarks or {}
        self.on_rows = on_rows
        self.database = ""
        self.columns: dict[tuple[str, str], list[bytes]] = {}
        self._creating: str | None = None
        self._create_columns: list[bytes] = []

    def feed(self, line: bytes) -> bytes:
        """The bytes this input line should contribute to the MySQL stream."""
        if self.mode == REPLACE:
            return line

        if self._creating is not None:
            return self._continue_create(line)

        stripped = line.lstrip()

        match = _USE.match(stripped)
        if match:
            self.database = match.group(1).decode()
            return line

        if _CREATE_DATABASE.match(stripped):
            return line

        # The target keeps the rows it already has, so the dump's teardown of
        # each table is left out of the stream.
        if _DROP_TABLE.match(stripped):
            return b""

        match = _CREATE_TABLE.match(stripped)
        if match:
            table = match.group(1).decode()
            if table in MERGE_SKIP_TABLES:
                self._creating = ""
                self._create_columns = []
                return b""
            self._creating = table
            self._create_columns = []
            # Tables the target is missing are still worth creating; ones it has
            # keep their existing definition.
            return stripped.replace(b"CREATE TABLE", b"CREATE TABLE IF NOT EXISTS", 1)

        match = _INSERT.match(stripped)
        if match:
            return self._rewrite_insert(stripped, match)

        return line

    def _continue_create(self, line: bytes) -> bytes:
        """Collect column names until the CREATE TABLE body closes."""
        skipping = self._creating == ""
        if line.lstrip().startswith(b")"):
            if not skipping:
                self.columns[(self.database, self._creating)] = self._create_columns
            self._creating = None
            return b"" if skipping else line

        match = _COLUMN.match(line)
        if match and not skipping:
            self._create_columns.append(match.group(1))
        return b"" if skipping else line

    def _rewrite_insert(self, line: bytes, match: re.Match) -> bytes:
        table = match.group(1).decode()
        if table in MERGE_SKIP_TABLES:
            return b""

        columns = self.columns.get((self.database, table), [])
        if match.group(3):
            columns = [name.strip().strip(b"`") for name in match.group(3).split(b",")]

        # Without a leading `_id` there is nothing to strip and no identity to
        # reassign, so the statement is left as the dump wrote it.
        if not columns or columns[0] != b"_id":
            return line

        try:
            device_at = columns.index(b"device_id")
            time_at = columns.index(b"timestamp")
        except ValueError:
            device_at = time_at = -1

        watermark = self.watermarks.get((self.database, table), {})
        kept: list[bytes] = []
        skipped = 0

        for row in _row_tuples(line, match.end()):
            body = row[1:-1]
            _, after_id = _next_field(body, 0)

            if device_at > 0 and time_at > 0 and watermark:
                if self._is_stored(body, after_id, columns, device_at, time_at, watermark):
                    skipped += 1
                    continue

            kept.append(b"(" + body[after_id:] + b")")

        if self.on_rows:
            self.on_rows(table, len(kept), skipped)
        if not kept:
            return b""

        names = b",".join(b"`" + name + b"`" for name in columns[1:])
        return b"INSERT INTO `" + table.encode() + b"` (" + names + b") VALUES " + b",".join(kept) + b";\n"

    def _is_stored(self, body, after_id, columns, device_at, time_at, watermark) -> bool:
        """Whether the target already holds this row's period for its device."""
        cursor = after_id
        timestamp = None
        device = None
        for index in range(1, max(device_at, time_at) + 1):
            value, cursor = _next_field(body, cursor)
            if index == time_at:
                try:
                    timestamp = float(value)
                except ValueError:
                    return False
            elif index == device_at:
                device = _unquote(value)

        if device is None or timestamp is None:
            return False
        newest = watermark.get(device)
        return newest is not None and timestamp <= newest
