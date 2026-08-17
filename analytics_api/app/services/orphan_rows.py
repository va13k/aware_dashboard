"""Rows that belong to no device, counted rather than discarded.

Every iOS table declares `device_id VARCHAR(128) NOT NULL`; the Android tables
declare `device_id varchar(150) DEFAULT ''`. So an Android insert that omits the
device succeeds and lands as an empty string — a row nobody wrote, with no error
raised at the time.

The dashboard used to treat those rows two ways at once. They were counted, since
the count cache grouped by `device_id` and skipped only `NULL`. They could never be
exported, since every CSV and ZIP walks a device list that drops both `NULL` and
`''`. That let the manifest report more rows than any download could produce, with
nothing on screen explaining the gap.

Counting comes before deleting. One read says whether this is a handful of rows
from an early test insert or a month of a client bug, and the answer changes what
to do with them: a few are noise, a large block is data somebody's phone really
collected and may be attributable by timestamp before anything is discarded. So
this reports the figure, and the count cache stops including it — the totals and
the downloads agree, and the difference is on screen rather than implied.

Read from the hourly rollup, which already holds one row per
`(table, device, hour)` and keys the orphans under an empty `device_id`. That makes
the answer a grouped read of a small table instead of a `COUNT(*)` per orphan
candidate across sixty large ones.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import coverage_rollup

#: What an Android insert leaves behind when it omits the device.
NO_DEVICE = ""

#: Unbounded: the question is what the study holds in total, not in a period.
ALL_TIME = (None, None)


async def by_table(db: AsyncSession, rollup_model) -> dict[str, int]:
    """How many orphan records each table holds, largest first.

    A table with none is absent rather than zero, so the answer names only what
    actually needs a decision.
    """
    counted = await coverage_rollup.records_by_table(
        db, rollup_model, ALL_TIME, None, NO_DEVICE
    )
    return dict(
        sorted(counted.items(), key=lambda entry: entry[1], reverse=True)
    )


async def summary(db: AsyncSession, rollup_model) -> dict:
    """One platform's orphans: the total, and which tables hold them."""
    tables = await by_table(db, rollup_model)
    return {
        "records": sum(tables.values()),
        "tables": tables,
    }
