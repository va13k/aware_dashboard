"""When each phone was in the study, as explicit windows.

The heatmap has to tell an empty cell that means "nothing was expected" from one
that means "expected and missing", and the device gate needs a reference for what
the study knows about. Both are the same question — was this device enrolled at
that moment — and neither can be answered from the data tables, which record only
what arrived.

Stored as one row per window rather than one per device, because a phone can quit
and come back: `aware_studies` reports a rejoin as its own event, and the client
keeps collecting nothing in between. A single window per device would span that
gap and report every hour of it as missing data, which is the exact reading this
table exists to prevent.

Windows are derived rather than authored. `aware_studies` is the phone's own
account of joining and leaving, which is the best source there is; a device that
has data but never reported a join gets a window opened at its first record
instead, so every device with data has a join time. `join_source` says which of
those happened, and that is what separates a device that never enrolled from one
that enrolled before anyone was recording it.

Android only. An iPhone's study state lives in `NSUserDefaults` and is never
uploaded, so there is nothing on the server to derive from and iOS devices are
left without windows rather than given an invented join time.

A window's start and end are taken from the client's own `double_join` and
`double_exit` when it reported them, falling back to when the row was logged.
Those two say when the participant *acted*, which is not when the message
arrived — a quit recorded on a phone with no signal reaches the server whenever
it next connects, and the window has to close on the day it actually closed.
"""

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import study_state

#: The phone said so, in `aware_studies`.
STUDY_EVENT = "study_event"
#: Inferred from when data first arrived, because the phone never said.
FIRST_DATA = "first_data"
#: A researcher entered it. Nothing writes this yet; the derivation already
#: leaves such a device alone so that the writer, when it arrives, does not have
#: to teach it to.
MANUAL = "manual"

#: Rows per insert statement. The table holds a few windows per device, so this
#: is one round trip for any study that fits on one server.
WRITE_CHUNK = 500


@dataclass(frozen=True)
class Window:
    """One stretch of time a device was in the study. `left_at` None means open."""

    device_id: str
    joined_at: int
    left_at: int | None = None
    join_source: str = STUDY_EVENT
    left_source: str | None = None

    def as_row(self) -> dict:
        return {
            "device_id": self.device_id,
            "joined_at": self.joined_at,
            "left_at": self.left_at,
            "join_source": self.join_source,
            "left_source": self.left_source,
        }


async def _rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except SQLAlchemyError:
        pass


def _moment(*candidates) -> int | None:
    """The first usable time among `candidates`.

    The client's numeric columns default to 0 rather than to NULL, so a zero
    means it reported nothing and the next candidate stands.
    """
    for value in candidates:
        if value is not None and value > 0:
            return int(value)
    return None


def _opened_at(event) -> int | None:
    """When a membership event put the phone in the study.

    The row's own `timestamp`, not its `double_join`. `double_join` names the
    enrolment the phone believes it is in and is carried on every row, so a
    rejoin after a quit repeats the *original* join time — which would reopen a
    window that already closed, and collide with it on the primary key.
    """
    return _moment(event.timestamp, event.joined_at)


def _closed_at(event) -> int | None:
    """When a quit took effect.

    `double_exit` is written on the leaving event itself, so unlike the join
    marker it does say when the participant acted — which is what makes a
    withdrawal made offline land on the day it happened.
    """
    return _moment(event.exited_at, event.timestamp)


def windows_for(
    device_id: str, events: list, first_data_at: int | None = None
) -> list[Window]:
    """The windows one device's study log describes, oldest first.

    `events` is a deduplicated, chronological event list from
    services/study_state.py. `first_data_at` is when this device's first record
    arrived, and is used for the two cases the log cannot answer on its own: a
    device that has data but never reported a join, and a log whose first
    decisive event is a quit.

    Real logs repeat themselves in both directions, and the windows have to come
    out disjoint and in order regardless: a phone re-reports a join it already
    made, and reports the same withdrawal several times over. So a window only
    opens while none is open and only after the last one closed, and a quit with
    nothing open is the client repeating itself rather than a new window.
    """
    windows: list[Window] = []
    open_at: int | None = None
    open_source = STUDY_EVENT
    closed_at: int | None = None
    left_the_study = False

    for event in events:
        if event.kind in study_state.MEMBERSHIP_KINDS:
            # Anything that says the phone was in the study when it happened
            # reopens a window, not only a join: after a quit, the next config
            # update or consent is the phone reporting itself back in.
            at = _opened_at(event)
            if at is None or open_at is not None:
                continue
            if closed_at is not None and at <= closed_at:
                continue
            open_at, open_source = at, STUDY_EVENT
            continue

        if event.kind != study_state.LEFT:
            continue

        at = _closed_at(event)
        if at is None:
            continue
        left_the_study = True

        if open_at is None:
            # Nothing is open. Either this log begins with a quit — in which
            # case the join predates what the phone reported, and its first
            # record is the earliest moment it can have been collecting — or a
            # window has already closed and this is the client repeating a
            # withdrawal it has already reported. Only the first is a window.
            if windows or first_data_at is None or first_data_at > at:
                continue
            open_at, open_source = first_data_at, FIRST_DATA

        if at >= open_at:
            windows.append(Window(device_id, open_at, at, open_source, STUDY_EVENT))
            open_at, closed_at = None, at

    if open_at is not None:
        windows.append(Window(device_id, open_at, None, open_source, None))

    if not windows and first_data_at is not None and not left_the_study:
        # Data arrived from a device that never said anything about joining. It
        # is in the study by the only evidence there is, and `first_data` says
        # the join time is inferred. A device whose log *did* say it left is not
        # covered here: opening a window from records it collected afterwards
        # would overwrite the withdrawal with the data that violated it.
        windows.append(Window(device_id, first_data_at, None, FIRST_DATA, None))

    return windows


async def stored_windows(
    db: AsyncSession, model, device_id: str | None = None
) -> dict[str, list[dict]]:
    """The windows the table holds, per device, oldest first.

    Read from the table rather than re-derived: the study log needs parsing and
    deduplicating per device, and this is on the path of both the device list and
    every coverage grid. The refresher keeps the table in step.
    """
    query = select(model).order_by(model.device_id, model.joined_at)
    if device_id is not None:
        query = query.where(model.device_id == device_id)

    try:
        result = await db.execute(query)
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}

    windows: dict[str, list[dict]] = {}
    for row in result.scalars().all():
        windows.setdefault(str(row.device_id), []).append(
            {
                "joined_at": int(row.joined_at),
                "left_at": int(row.left_at) if row.left_at is not None else None,
                "join_source": row.join_source,
                "left_source": row.left_source,
            }
        )
    return windows


async def close_window(
    db: AsyncSession, model, device_id: str, left_at: int
) -> dict | None:
    """Record that a device left the study, at the moment it left.

    `left_at` is when the participant *acted*, which is not always when anyone
    found out: a withdrawal reported days later still has to land on the day it
    happened, or every bucket in between reads as expected-and-missing on a grid
    the participant had already left. So the caller supplies the moment and this
    stores it.

    The window closed is the one covering `left_at`, or the latest still open
    before it. Marked `manual`, which is what makes the derivation leave this
    device alone afterwards rather than reopening the window from the study log.

    Returns the window as stored, or None when the device has none to close.
    """
    windows = (await stored_windows(db, model, device_id)).get(device_id) or []

    target = None
    for index, window in enumerate(windows):
        if window["joined_at"] > left_at:
            continue
        # A changed withdrawal date may be later than the date stored before.
        # Partition by the next join instead of the old end, so editing a manual
        # correction can extend or shorten it without ever crossing a rejoin.
        next_join = (
            windows[index + 1]["joined_at"] if index + 1 < len(windows) else None
        )
        if next_join is None or left_at < next_join:
            target = window
    if target is None:
        return None

    try:
        await db.execute(
            model.__table__.update()
            .where(model.device_id == device_id)
            .where(model.joined_at == target["joined_at"])
            .values(left_at=int(left_at), left_source=MANUAL)
        )
        await db.commit()
    except SQLAlchemyError:
        await _rollback(db)
        return None

    return {
        "device_id": device_id,
        "joined_at": target["joined_at"],
        "left_at": int(left_at),
        "join_source": target["join_source"],
        "left_source": MANUAL,
    }


async def reopen(db: AsyncSession, model, device_id: str) -> bool:
    """Undo a withdrawal recorded by mistake, handing the device back to the log.

    Clears the manual marks so the next derivation rebuilds this device's windows
    from `aware_studies` — the phone's own account — rather than leaving it frozen
    at a researcher's correction.
    """
    try:
        await db.execute(
            model.__table__.delete().where(model.device_id == device_id)
        )
        await db.commit()
    except SQLAlchemyError:
        await _rollback(db)
        return False
    return True


async def first_record_by_device(db: AsyncSession, coverage_model) -> dict[str, int]:
    """When each device's first record arrived, to the hour.

    Read from the hourly rollup rather than the data tables: the rollup already
    holds one row per hour a device wrote in, so the earliest is an aggregate
    over a small table instead of a `MIN(timestamp)` across sixty large ones.
    The hour it lands on is finer than any window this feeds.
    """
    try:
        rows = (
            await db.execute(
                select(
                    coverage_model.device_id,
                    func.min(coverage_model.hour_start).label("first_hour"),
                ).group_by(coverage_model.device_id)
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}

    return {
        str(row.device_id): int(row.first_hour)
        for row in rows
        if row.device_id and row.first_hour is not None
    }


async def _researcher_marks(db: AsyncSession, model) -> dict[str, int]:
    """Per device, the moment a researcher's own answer stops applying.

    Scoped in time rather than per device. A researcher saying when somebody left
    settles the history up to that moment, and nothing about what the participant
    does afterwards — so a rejoin the phone reports later has to be honoured, or
    marking one person as having quit would bar them from the study permanently.

    The moment returned is the newest instant a researcher entered for that device.
    Windows at or before it are theirs; study events after it are derived as usual.
    """
    try:
        rows = (
            await db.execute(
                select(
                    model.device_id,
                    func.max(func.coalesce(model.left_at, model.joined_at)),
                )
                .where((model.join_source == MANUAL) | (model.left_source == MANUAL))
                .group_by(model.device_id)
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}
    return {
        str(device_id): int(marked)
        for device_id, marked in rows
        if device_id and marked is not None
    }


async def _study_events_by_device(db: AsyncSession, study_model) -> dict[str, list]:
    """Each device's deduplicated study log, oldest first.

    `derive_study_state` returns its events newest first, which is the order the
    device page renders them in. Windows are read forwards, so they are turned
    back here rather than at each use.
    """
    try:
        result = await db.execute(
            select(study_model).order_by(study_model.timestamp, study_model._id)
        )
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}

    by_device: dict[str, list] = {}
    for row in result.scalars().all():
        if row.device_id:
            by_device.setdefault(str(row.device_id), []).append(row)

    return {
        device: list(reversed(study_state.derive_study_state(device_rows).events))
        for device, device_rows in by_device.items()
    }


def derive(
    events_by_device: dict[str, list], first_record: dict[str, int]
) -> list[Window]:
    """Every window both sources describe, for every device either one names.

    A device with a study log and no data still gets its windows: it joined and
    has yet to upload, which is a state the device list already shows.

    `(device, joined_at)` is the primary key, so two windows sharing one would
    fail the insert and take every other device's windows down with them. The
    derivation is written not to produce that; this makes a log shape it did not
    anticipate cost one window rather than the whole pass.
    """
    windows: list[Window] = []
    seen: set[tuple[str, int]] = set()
    for device_id in sorted(set(events_by_device) | set(first_record)):
        for window in windows_for(
            device_id,
            events_by_device.get(device_id, []),
            first_record.get(device_id),
        ):
            key = (window.device_id, window.joined_at)
            if key in seen:
                continue
            seen.add(key)
            windows.append(window)
    return windows


async def refresh(
    db: AsyncSession, model, coverage_model, study_model
) -> dict[str, int]:
    """Rebuild the derived windows. Returns the counts a caller can log.

    Rebuilt whole rather than incrementally: `aware_studies` holds a handful of
    rows per phone, so re-reading it costs less than tracking what changed, and a
    correction to an earlier event is picked up for free.

    A researcher's own answer is kept, and only for the stretch it speaks to: their
    windows stay, and anything the phone reports after the moment they entered is
    derived on top. That is what lets a participant marked as having quit rejoin
    whenever they choose.
    """
    marks = await _researcher_marks(db, model)
    events_by_device = await _study_events_by_device(db, study_model)
    first_record = await first_record_by_device(db, coverage_model)

    windows = [
        window
        for window in derive(events_by_device, first_record)
        if window.joined_at > marks.get(window.device_id, -1)
    ]

    discard = delete(model)
    for device_id, marked in marks.items():
        # Keep this device's researcher-entered windows, drop the derived ones so
        # they are rebuilt from the log.
        discard = discard.where(
            ~((model.device_id == device_id) & (model.joined_at <= marked))
        )

    try:
        await db.execute(discard)
        for start in range(0, len(windows), WRITE_CHUNK):
            chunk = windows[start : start + WRITE_CHUNK]
            await db.execute(
                model.__table__.insert().values([window.as_row() for window in chunk])
            )
        await db.commit()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}

    return {
        "devices": len({window.device_id for window in windows}),
        "windows": len(windows),
        "researcher_owned": len(marks),
    }


async def reset(db: AsyncSession, model) -> None:
    """Empty the table so the next pass rebuilds it, researcher rows included."""
    try:
        await db.execute(delete(model))
        await db.commit()
    except SQLAlchemyError:
        await _rollback(db)
