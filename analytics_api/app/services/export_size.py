"""Roughly how large an export will be, before producing it.

A researcher choosing a period is deciding whether to start a download, and the
record count alone does not answer that — a million rows of one sensor and a
million of another are not the same file. This turns a per-table record count
into a size, well enough to tell a few megabytes from a few gigabytes.

It is an estimate twice over and says so. `TABLE_ROWS` is InnoDB's own estimate
rather than a count, and the ratio between a stored row and the compressed CSV
it becomes depends on how repetitive the data is. Measured against a live study:
`bluetooth` came out at 0.10 of its stored size, `magnetometer` at 0.18 — a
sensor whose columns are three constantly-changing floats compresses far worse
than one repeating device names. `CSV_ZIP_FACTOR` sits between them, so the
figure is a magnitude rather than a promise, and the interface should present it
as one.

The alternative — producing the archive to find out how big it is — is the thing
the estimate exists to avoid.
"""

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

#: Compressed CSV bytes per byte the table occupies. See the module docstring
#: for where this came from and how far it can be out.
CSV_ZIP_FACTOR = 0.15


async def bytes_per_row(db: AsyncSession, database: str) -> dict[str, float]:
    """Each table's average stored bytes per row, from the server's statistics.

    One read of `information_schema`, not a scan: the figures are already kept.
    A table InnoDB reports as empty is absent rather than zero, so a caller
    cannot divide by it.
    """
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT TABLE_NAME, DATA_LENGTH / TABLE_ROWS AS per_row "
                    "FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = :database AND TABLE_ROWS > 0 "
                    "AND DATA_LENGTH > 0"
                ),
                {"database": database},
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        try:
            await db.rollback()
        except SQLAlchemyError:
            pass
        return {}

    return {str(name): float(per_row) for name, per_row in rows if per_row}


def estimate(records: dict[str, int], per_row: dict[str, float]) -> int:
    """Compressed bytes an export of `records` would come to.

    `records` is `{table: rows}` for whatever the export covers. A table with no
    statistics contributes nothing rather than a guessed row size — under-stating
    a total is better than inventing the part that is unknown.
    """
    total = 0.0
    for table, count in records.items():
        size = per_row.get(table)
        if size:
            total += count * size * CSV_ZIP_FACTOR
    return int(total)
