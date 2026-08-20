import csv
import io
import json
import re
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    AndroidSessionLocal,
    IosBase,
    IosSessionLocal,
    get_android_db,
    get_ios_db,
)
from app.models import (
    AndroidCoverageHourly,
    AndroidDeviceExclusion,
    AndroidRecordCount,
    IosCoverageHourly,
    IosDeviceExclusion,
    IosRecordCount,
)
from app.routers.android import _EXPORT_MODELS as ANDROID_EXPORT_MODELS
from app.routers.ios import _EXPORT_MODELS as IOS_EXPORT_MODELS
from app.schemas import IosSchema
from app.services import backup_jobs as jobs
from app.services import (
    coverage_rollup,
    exclusions,
    record_counts,
    sensor_tables,
    study_config,
)

router = APIRouter(prefix="/export", tags=["export"])

#: Both platforms' export entries, by platform name.
_EXPORT_MODELS_FOR = {"android": ANDROID_EXPORT_MODELS, "ios": IOS_EXPORT_MODELS}

#: The two entry shapes are read in services/sensor_tables.py, because anything
#: counting rows by sensor has to read them the same way this does.
_is_android_export_entry = sensor_tables.is_android_entry
_ios_models = sensor_tables.models_for

_SAFE_PATH_PART = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_path_part(value: str) -> str:
    cleaned = _SAFE_PATH_PART.sub("_", value).strip("._")
    return cleaned or "unknown"


#: Rows read per round trip while an archive is being produced. One batch and
#: its rendered CSV is the whole of what an export holds at a time, so this
#: bounds the memory a download costs no matter how many rows it covers.
EXPORT_BATCH = 5_000



class _Sink:
    """Catches what ``ZipFile`` writes so a generator can hand it onward.

    Deliberately offers neither ``tell`` nor ``seek``: ``ZipFile`` then treats
    the target as a stream and records each member's size in a trailing data
    descriptor instead of seeking back to patch its header. That is what makes an
    archive producible without holding it, which a study-scale export needs —
    assembling one in memory first costs a multiple of the data itself.
    """

    def __init__(self) -> None:
        self._parts: list[bytes] = []

    def write(self, data) -> int:
        self._parts.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        pass

    def drain(self) -> bytes:
        joined = b"".join(self._parts)
        self._parts.clear()
        return joined


def _csv_rows(fields: list[str], records: list[dict], header: bool = False) -> bytes:
    """One batch of rows as CSV bytes, ready to write into an archive member."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore", restval="")
    if header:
        writer.writeheader()
    writer.writerows(records)
    return buf.getvalue().encode("utf-8")


#: No period chosen, so the export covers whatever the table holds.
ALL_TIME = (None, None)


def _bounded(query, model, window):
    """The query, narrowed to the chosen period. Both ends are inclusive."""
    start, end = window
    if start is not None:
        query = query.where(model.timestamp >= start)
    if end is not None:
        query = query.where(model.timestamp <= end)
    return query


async def _paged(db: AsyncSession, model, device_id: str | None, render, window=ALL_TIME):
    """Walk a table in batches, yielding one rendered batch at a time.

    Paging on a key rather than ``OFFSET`` keeps each round trip an indexed seek,
    and means the rows a batch held can be released before the next one is read.

    *Which* key depends on the period. With none, ``_id`` — the primary key, and
    the order the archives have always been written in. With one, ``(timestamp,
    _id)``, because the two cannot both be indexed: the table carries ``PRIMARY
    KEY (_id)`` and ``KEY time_device (timestamp, device_id)``, so walking in
    ``_id`` order with a ``timestamp`` predicate reads the whole table and
    discards most of it. Ordering by ``timestamp`` makes the period an index
    range seek, so a day out of a year costs a day. ``_id`` breaks ties, so rows
    sharing a millisecond are neither repeated across batches nor skipped.
    """
    ranged = window != ALL_TIME
    last_ts, last_id = None, 0
    while True:
        query = select(model)
        if device_id is not None:
            query = query.where(model.device_id == device_id)

        if ranged:
            query = _bounded(query, model, window)
            if last_ts is not None:
                query = query.where(
                    or_(
                        model.timestamp > last_ts,
                        and_(model.timestamp == last_ts, model._id > last_id),
                    )
                )
            query = query.order_by(model.timestamp.asc(), model._id.asc())
        else:
            query = query.where(model._id > last_id).order_by(model._id.asc())

        try:
            result = await db.execute(query.limit(EXPORT_BATCH))
            rows = result.scalars().all()
        except (OperationalError, ProgrammingError, SQLAlchemyError):
            await _rollback_after_table_error(db)
            return
        if not rows:
            return
        yield [render(row) for row in rows]
        last_ts, last_id = rows[-1].timestamp, rows[-1]._id


async def _has_rows(
    db: AsyncSession, model, device_id: str | None = None, window=ALL_TIME
) -> bool:
    query = select(model._id)
    if device_id is not None:
        query = query.where(model.device_id == device_id)
    query = _bounded(query, model, window)
    try:
        return (await db.execute(query.limit(1))).first() is not None
    except (OperationalError, ProgrammingError, SQLAlchemyError):
        await _rollback_after_table_error(db)
        return False


async def _rollback_after_table_error(db: AsyncSession):
    try:
        await db.rollback()
    except SQLAlchemyError:
        pass


def _exclusion_model(model):
    """The exclusion list belonging to whichever platform this model is from.

    Taken from the model's own declarative base rather than from the session, so a
    caller cannot pair an iOS table with the Android exclusion list by holding the
    wrong session.
    """
    return IosDeviceExclusion if issubclass(model, IosBase) else AndroidDeviceExclusion


async def _device_ids_for_model(db: AsyncSession, model) -> set[str]:
    """The devices this table holds data for, minus the ones left out.

    Two filters, for two different reasons. An empty or null `device_id` belongs to
    no device and could never be attributed to one. An excluded device is a real
    participant a researcher deliberately took out of the analysis — the rows stay
    in the database and on screen, and this is where the decision takes effect,
    because an export is the analysis dataset leaving.
    """
    try:
        result = await db.execute(select(model.device_id).distinct())
    except (OperationalError, ProgrammingError, SQLAlchemyError):
        await _rollback_after_table_error(db)
        return set()

    found = {str(row[0]) for row in result.all() if row[0] not in (None, "")}
    return found - await exclusions.excluded_ids(db, _exclusion_model(model))


async def _platform_device_ids(db: AsyncSession, export_models: dict[str, object]) -> list[str]:
    device_ids: set[str] = set()
    for entry in export_models.values():
        for model in _ios_models(entry):
            device_ids.update(await _device_ids_for_model(db, model))
    return sorted(device_ids)


#: A sensor card spans both platforms, so its dialog offers one archive holding
#: whichever of them actually serve the sensor.
ALL_PLATFORMS = "all"


def _platform_exports(platform: str):
    if platform == "android":
        return ANDROID_EXPORT_MODELS
    if platform == "ios":
        return IOS_EXPORT_MODELS
    raise HTTPException(status_code=404, detail="Unknown platform")


def _requested_platforms(platform: str) -> tuple[str, ...]:
    """The platforms one scope covers, in the order their members are written."""
    if platform == ALL_PLATFORMS:
        return ("android", "ios")
    if platform in ("android", "ios"):
        return (platform,)
    raise HTTPException(status_code=404, detail="Unknown platform")


def _sensor_entries(platforms: tuple[str, ...], sensor: str) -> list[tuple[str, object]]:
    """`(platform, export entry)` for each platform that serves this sensor.

    A sensor one platform does not collect is left out rather than refused, so
    an all-platforms export of a shared sensor and of an Android-only one both
    produce an archive holding exactly what exists.
    """
    found = []
    for name in platforms:
        entry = _EXPORT_MODELS_FOR[name].get(sensor)
        if entry is not None:
            found.append((name, entry))
    return found


async def _sensor_members_across(entries, sensor: str, window=ALL_TIME):
    """One sensor's CSVs, one member per platform that serves it."""
    for name, entry in entries:
        async for member in _sensor_members(name, sensor, entry, window):
            yield member




async def _sensor_stats(db: AsyncSession, models: tuple, cached=None) -> dict:
    """Per-sensor manifest stats.

    ``cached`` is the ``(row_count, devices_with_data)`` from the record-count
    cache when available; it replaces the O(rows) ``COUNT`` + ``DISTINCT
    device_id`` scans. First/last timestamps stay live — ``MIN``/``MAX`` on the
    indexed ``timestamp`` is cheap — and a cache miss falls back to live counts.
    """
    row_count = 0
    device_ids: set[str] = set()
    first_timestamp = None
    last_timestamp = None

    for model in models:
        try:
            exportable = (model.device_id.is_not(None), model.device_id != "")
            stats = await db.execute(
                select(
                    func.min(model.timestamp).label("first_timestamp"),
                    func.max(model.timestamp).label("last_timestamp"),
                ).where(*exportable)
            )
            row = stats.one()
            if row.first_timestamp is not None:
                first_timestamp = (
                    row.first_timestamp
                    if first_timestamp is None
                    else min(first_timestamp, row.first_timestamp)
                )
            if row.last_timestamp is not None:
                last_timestamp = (
                    row.last_timestamp
                    if last_timestamp is None
                    else max(last_timestamp, row.last_timestamp)
                )

            if cached is None:
                count_row = await db.execute(
                    select(func.count()).select_from(model).where(*exportable)
                )
                row_count += int(count_row.scalar() or 0)
                device_result = await db.execute(
                    select(model.device_id).where(*exportable).distinct()
                )
                device_ids.update(
                    str(item[0])
                    for item in device_result.all()
                    if item[0] not in (None, "")
                )
        except (OperationalError, ProgrammingError, SQLAlchemyError):
            await _rollback_after_table_error(db)

    if cached is not None:
        row_count, devices_with_data = cached
    else:
        devices_with_data = len(device_ids)

    return {
        "row_count": row_count,
        "devices_with_data": devices_with_data,
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
    }



def _android_fields(schema) -> list[str]:
    """CSV columns for an android sensor, from the schema rather than from a row,
    so the header can be written before anything has been read."""
    return list(schema.model_fields)


async def _ios_field_union(db: AsyncSession, models: tuple) -> list[str]:
    """Every key iOS rows carry for this sensor.

    iOS payloads are JSON, so the columns are only known once the rows have been
    looked at — but they are looked at a batch at a time and only the key names
    are kept, so the pass costs a scan rather than the table.
    """
    fields = ["id", "timestamp", "device_id"]
    for model in models:
        async for batch in _paged(db, model, None, lambda row: IosSchema.model_validate(row).model_dump()):
            for record in batch:
                fields.extend(record.keys())
            fields = list(dict.fromkeys(fields))
    return list(dict.fromkeys(fields))


def _member(archive: zipfile.ZipFile, name: str):
    """A new archive member, sized by a trailing descriptor.

    ``force_zip64`` because a member's length is not known when its header is
    written and a single sensor's CSV can pass the 4 GiB the classic format holds.
    """
    info = zipfile.ZipInfo(name, date_time=datetime.now(timezone.utc).timetuple()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    return archive.open(info, "w", force_zip64=True)


async def _stream_archive(members, job=None, manifest=None):
    """Produce a ZIP as it is read.

    `members` is an async iterable of ``(name, fields, batches)``, where
    `batches` yields lists of rendered rows. Nothing larger than one batch and
    the compressor's own buffers is held at a time.

    `manifest` is written first, before any data, so an archive says what it is
    even when the download was interrupted part-way through.
    """
    sink = _Sink()
    try:
        with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if manifest is not None:
                with _member(archive, MANIFEST_MEMBER) as member:
                    member.write(json.dumps(manifest, indent=2).encode("utf-8"))
                if chunk := sink.drain():
                    yield chunk

            async for name, fields, batches in members:
                if job is not None:
                    jobs.advance(job, phase=f"Writing {name.rsplit('/', 1)[-1]}")
                with _member(archive, name) as member:
                    member.write(_csv_rows(fields, [], header=True))
                    async for batch in batches:
                        member.write(_csv_rows(fields, batch))
                        if job is not None:
                            jobs.advance(job, add=len(batch))
                        if chunk := sink.drain():
                            yield chunk
                if chunk := sink.drain():
                    yield chunk
        if chunk := sink.drain():
            yield chunk
        if job is not None:
            jobs.finish(job)
    except Exception as error:  # noqa: BLE001 - the response has already begun
        if job is not None:
            jobs.fail(job, str(error))
        raise
    finally:
        # A cancelled download closes this generator, which arrives as
        # GeneratorExit — a BaseException, so it misses the handler above. Left
        # unresolved the job would read as running until it aged out.
        if job is not None:
            jobs.cancel(job)


def _progress_job(job_id: str | None, scope: str):
    """The job this download may report into, or nothing.

    The id arrives in the query string, so it is whatever the caller put there.
    One belonging to something else must not be advanced or finished here: the
    page watching it would be told the wrong thing about work still running.
    """
    if not job_id:
        return None
    job = jobs.get(job_id)
    if job is None or job.kind != "export-zip":
        return None
    if job.result.get("scope") != scope:
        return None
    return job


async def _start_zip_job(scope: str, filename: str, total: int):
    job = jobs.create("export-zip")
    jobs.advance(job, total=total, phase="Starting export")
    jobs.describe(job, filename=filename, scope=scope, unit="rows")
    return {"id": job.id, "filename": filename, "rows": total}


#: Written first into every archive, so the file explains itself once it has
#: left the dashboard and is sitting in someone's downloads folder.
MANIFEST_MEMBER = "manifest.json"


def _study_name() -> str:
    """The study this deployment is running, for naming what it produces.

    A deployment with no config yet is normal rather than an error — the file is
    written at deployment time — so an archive still gets a name.
    """
    deployed = study_config.load_deployed_config()
    title = (deployed.summary.get("study_title") if deployed else None) or "aware"
    return _safe_path_part(str(title).strip()) or "aware"


def _stamp(milliseconds: float) -> str:
    """A window bound in a filename: UTC, sortable, minute precision."""
    moment = datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
    return moment.strftime("%Y%m%d-%H%M")


def _utc(milliseconds: float | None) -> str | None:
    if milliseconds is None:
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).isoformat()


def _archive_name(scope: str, window: tuple) -> str:
    """What the download is called: study, what it covers, and when.

    Named after the study rather than ``all.zip``, because a researcher ends up
    with several of these from several studies in one folder. The window is in
    the name for the same reason the dialog shows resolved bounds: a relative
    period whose instants are invisible cannot be reproduced later.
    """
    start, end = window
    if start is None and end is None:
        span = "all-time"
    elif start is None:
        span = f"to-{_stamp(end)}"
    elif end is None:
        span = f"from-{_stamp(start)}"
    else:
        span = f"{_stamp(start)}-to-{_stamp(end)}"
    return f"{_study_name()}-{scope}-{span}.zip"


def _export_manifest(scope: str, window: tuple) -> dict:
    """What this archive holds, written into it as its first member.

    Deliberately carries no expected row count. The only figure available
    without re-reading the data is the rollup's, which is hour-granular at a
    window's edges — and an approximate expectation sitting beside exact CSVs
    reads as missing data rather than as a rounding. The rows in the archive are
    the answer; the estimate belongs to the progress bar, where it is invisible.
    """
    start, end = window
    return {
        "study": _study_name(),
        "scope": scope,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": {
            "all_time": window == ALL_TIME,
            "from": start,
            "to": end,
            "from_utc": _utc(start),
            "to_utc": _utc(end),
            # Both ends are inclusive, which decides whether a boundary row
            # belongs to this archive or the next one.
            "bounds": "inclusive",
        },
    }


def _window(from_ts: float | None, to_ts: float | None) -> tuple:
    """The chosen period, or ALL_TIME when neither end was given.

    A reversed pair is read as the period the researcher meant rather than
    refused, since the two ends are a range and not an order.
    """
    if from_ts is None and to_ts is None:
        return ALL_TIME
    if from_ts is not None and to_ts is not None and from_ts > to_ts:
        return (to_ts, from_ts)
    return (from_ts, to_ts)


def _rollup_model(platform: str):
    return AndroidCoverageHourly if platform == "android" else IosCoverageHourly


def _sensor_tables(platform: str, sensor: str) -> list[str]:
    """The tables one sensor's rows live in.

    Taken from the export models rather than the count cache's source map: a
    sensor spread across two tables is missing from that map entirely, and
    counting it is the reason the rollup is keyed by table.
    """
    return sensor_tables.tables_for(_EXPORT_MODELS_FOR[platform], sensor)


# The totals below are what a progress bar is measured against. Without a period
# they come from the count cache, which holds exactly the rows an export writes.
# With one they come from the rollup, whose buckets are whole hours — so a window
# landing mid-hour reads slightly high. The bar is completed when the job
# finishes rather than by reaching its denominator, so the difference is not
# visible; what would be visible is measuring a windowed export against the whole
# table, which is what these replace.


async def _sensor_row_total(
    db: AsyncSession, platform: str, count_model, sensor: str, window=ALL_TIME
) -> int:
    if window == ALL_TIME:
        totals = await record_counts.sensor_totals(db, count_model)
        return int(totals.get(sensor, (0, 0))[0])
    return await coverage_rollup.records_in(
        db, _rollup_model(platform), window, _sensor_tables(platform, sensor)
    )


async def _device_row_total(
    db: AsyncSession, platform: str, count_model, device_id: str, window=ALL_TIME
) -> int:
    if window == ALL_TIME:
        cached = await record_counts.counts_for_device(db, count_model, device_id)
        return sum(entry["count"] for entry in cached.values())
    return await coverage_rollup.records_in(
        db, _rollup_model(platform), window, device_id=device_id
    )


async def _platform_row_total(
    db: AsyncSession, platform: str, count_model, window=ALL_TIME
) -> int:
    if window == ALL_TIME:
        totals = await record_counts.sensor_totals(db, count_model)
        return sum(count for count, _ in totals.values())
    return await coverage_rollup.records_in(db, _rollup_model(platform), window)


def _zip_streaming_response(
    members, filename: str, job=None, manifest=None
) -> StreamingResponse:
    return StreamingResponse(
        _stream_archive(members, job, manifest),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Produced as it is sent, so no intermediary should collect it first.
            "X-Accel-Buffering": "no",
        },
    )


async def _chained(
    db: AsyncSession, models: tuple, device_ids: list[str], render, window=ALL_TIME
):
    """Every device's rows for one sensor, in turn, as batches.

    Walking device by device keeps the CSV grouped the way it has always been —
    all of one phone's rows together — while still only holding a batch at a time.
    """
    for model in models:
        for device_id in device_ids:
            async for batch in _paged(db, model, device_id, render, window):
                yield batch


async def _sensor_members(platform: str, sensor: str, model_entry, window=ALL_TIME):
    """One sensor across every phone, as a single CSV inside the archive.

    A platform holding nothing inside the period contributes no member at all,
    rather than a CSV of headers. That matters for an all-platforms export of a
    sensor only one side collected: the archive then says what it has, and does
    not imply the other side was asked and answered.
    """
    name = f"{platform}_{_safe_path_part(sensor)}.csv"
    session = AndroidSessionLocal if platform == "android" else IosSessionLocal
    async with session() as db:
        if not any([
            await _has_rows(db, model, None, window)
            for model in _ios_models(model_entry)
        ]):
            return

        if _is_android_export_entry(model_entry):
            model, schema = model_entry
            devices = sorted(await _device_ids_for_model(db, model))
            yield (
                name,
                _android_fields(schema),
                _chained(
                    db,
                    (model,),
                    devices,
                    lambda row: schema.model_validate(row).model_dump(),
                    window,
                ),
            )
            return

        models = _ios_models(model_entry)
        devices: set[str] = set()
        for model in models:
            devices |= await _device_ids_for_model(db, model)
        yield (
            name,
            await _ios_field_union(db, models),
            _chained(
                db,
                models,
                sorted(devices),
                lambda row: IosSchema.model_validate(row).model_dump(),
                window,
            ),
        )


async def _device_members(platform: str, device_id: str, window=ALL_TIME):
    """Every sensor this phone has data for, one archive member each.

    A sensor with nothing inside the period is left out rather than written as a
    header-only member, so the archive says which sensors the period actually
    covers.
    """
    safe_device = _safe_path_part(device_id)
    session = AndroidSessionLocal if platform == "android" else IosSessionLocal
    async with session() as db:
        if platform == "android":
            for sensor, (model, schema) in ANDROID_EXPORT_MODELS.items():
                if not await _has_rows(db, model, device_id, window):
                    continue
                yield (
                    f"android/{safe_device}/{_safe_path_part(sensor)}.csv",
                    _android_fields(schema),
                    _paged(
                        db,
                        model,
                        device_id,
                        lambda row, s=schema: s.model_validate(row).model_dump(),
                        window,
                    ),
                )
            return

        for sensor, model_entry in IOS_EXPORT_MODELS.items():
            models = _ios_models(model_entry)
            if not any(
                [await _has_rows(db, model, device_id, window) for model in models]
            ):
                continue
            fields = await _ios_field_union(db, models)
            for model in models:
                yield (
                    f"ios/{safe_device}/{_safe_path_part(sensor)}.csv",
                    fields,
                    _paged(
                        db,
                        model,
                        device_id,
                        lambda row: IosSchema.model_validate(row).model_dump(),
                        window,
                    ),
                )


@router.get("/manifest")
async def export_manifest(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    platforms = {
        "android": {
            "device_count": len(await _platform_device_ids(android_db, ANDROID_EXPORT_MODELS)),
            "sensors": {},
        },
        "ios": {
            "device_count": len(await _platform_device_ids(ios_db, IOS_EXPORT_MODELS)),
            "sensors": {},
        },
    }

    # Exact counts come from the cache in one lookup per platform; the manifest
    # only adds cheap MIN/MAX timestamps on top (see _sensor_stats).
    android_totals = await record_counts.sensor_totals(android_db, AndroidRecordCount)
    ios_totals = await record_counts.sensor_totals(ios_db, IosRecordCount)

    for sensor, (model, schema) in ANDROID_EXPORT_MODELS.items():
        platforms["android"]["sensors"][sensor] = {
            **await _sensor_stats(android_db, (model,), android_totals.get(sensor)),
            "fields": list(dict.fromkeys(schema.model_fields.keys())),
        }

    for sensor, model_entry in IOS_EXPORT_MODELS.items():
        models = _ios_models(model_entry)
        platforms["ios"]["sensors"][sensor] = {
            **await _sensor_stats(ios_db, models, ios_totals.get(sensor)),
            "fields": await _ios_field_union(ios_db, models),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platforms": platforms,
    }


async def _any_sensor_has_rows(
    db: AsyncSession, platform: str, device_id: str, window=ALL_TIME
) -> bool:
    """Whether this phone wrote anything inside the chosen period.

    Settled before the response begins: once a streaming body is under way its
    status can no longer become a 404. With a period that makes an empty window
    a refusal rather than an archive of empty CSVs.
    """
    exports = _platform_exports(platform)
    for entry in exports.values():
        models = (entry[0],) if _is_android_export_entry(entry) else _ios_models(entry)
        for model in models:
            if await _has_rows(db, model, device_id, window):
                return True
    return False


@router.post("/device/{platform}/{device_id}.zip")
async def start_device_csv_zip(
    platform: str,
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """Register the export so the page can show progress while it downloads."""
    _platform_exports(platform)
    db = android_db if platform == "android" else ios_db
    window = _window(from_ts, to_ts)
    if not await _any_sensor_has_rows(db, platform, device_id, window):
        raise HTTPException(
            status_code=404,
            detail=f"No sensor data found for {platform} device: {device_id}",
        )
    model = AndroidRecordCount if platform == "android" else IosRecordCount
    return await _start_zip_job(
        f"device:{platform}:{device_id}",
        _archive_name(f"{platform}-{_safe_path_part(device_id)}", window),
        await _device_row_total(db, platform, model, device_id, window),
    )


@router.get("/device/{platform}/{device_id}.zip")
async def export_device_csv_zip(
    platform: str,
    device_id: str,
    job: str | None = Query(None),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),

    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    _platform_exports(platform)
    db = android_db if platform == "android" else ios_db

    window = _window(from_ts, to_ts)
    if not await _any_sensor_has_rows(db, platform, device_id, window):
        raise HTTPException(
            status_code=404,
            detail=f"No sensor data found for {platform} device: {device_id}",
        )

    scope = f"device:{platform}:{device_id}"
    return _zip_streaming_response(
        _device_members(platform, device_id, window),
        _archive_name(f"{platform}-{_safe_path_part(device_id)}", window),
        _progress_job(job, scope),
        _export_manifest(scope, window),
    )


@router.post("/sensor/{platform}/{sensor:path}.zip")
async def start_sensor_csv_zip(
    platform: str,
    sensor: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """Register the export so the page can show progress while it downloads."""
    entries = _sensor_entries(_requested_platforms(platform), sensor)
    if not entries:
        raise HTTPException(status_code=404, detail=f"Unknown sensor: {sensor}")

    window = _window(from_ts, to_ts)
    sessions = {"android": android_db, "ios": ios_db}
    counts = {"android": AndroidRecordCount, "ios": IosRecordCount}

    total = 0
    holds_rows = False
    for name, entry in entries:
        db = sessions[name]
        if any([await _has_rows(db, model, None, window) for model in _ios_models(entry)]):
            holds_rows = True
        total += await _sensor_row_total(db, name, counts[name], sensor, window)

    if not holds_rows:
        raise HTTPException(
            status_code=404, detail=f"No data found for {platform} sensor: {sensor}"
        )

    return await _start_zip_job(
        f"sensor:{platform}:{sensor}",
        _archive_name(f"{platform}-{_safe_path_part(sensor)}", window),
        total,
    )


@router.get("/sensor/{platform}/{sensor:path}.zip")
async def export_sensor_csv_zip(
    platform: str,
    sensor: str,
    job: str | None = Query(None),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),

    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    entries = _sensor_entries(_requested_platforms(platform), sensor)
    if not entries:
        raise HTTPException(status_code=404, detail=f"Unknown sensor: {sensor}")

    window = _window(from_ts, to_ts)
    sessions = {"android": android_db, "ios": ios_db}

    # Settled before the response begins: once a streaming body is under way its
    # status can no longer become a 404.
    holds_rows = False
    for name, entry in entries:
        if any([
            await _has_rows(sessions[name], model, None, window)
            for model in _ios_models(entry)
        ]):
            holds_rows = True
            break

    if not holds_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {platform} sensor: {sensor}",
        )

    scope = f"sensor:{platform}:{sensor}"
    return _zip_streaming_response(
        _sensor_members_across(entries, sensor, window),
        _archive_name(f"{platform}-{_safe_path_part(sensor)}", window),
        _progress_job(job, scope),
        _export_manifest(scope, window),
    )


def _all_scope_name(platform: str) -> str:
    """What a study-wide archive is called for this platform choice.

    Both platforms stays plain `all`, so the name a researcher has been getting
    does not change under them; one platform says which, because an archive
    holding half the study should not be indistinguishable from one holding it.
    """
    return "all" if platform == ALL_PLATFORMS else f"all-{platform}"


async def _all_members(window=ALL_TIME, platforms=("android", "ios")):
    """Every sensor of every phone, on each platform asked for."""
    for platform in platforms:
        session = AndroidSessionLocal if platform == "android" else IosSessionLocal
        exports = _EXPORT_MODELS_FOR[platform]
        async with session() as db:
            for device_id in await _platform_device_ids(db, exports):
                async for entry in _device_members(platform, device_id, window):
                    yield entry


@router.post("/all.zip")
async def start_all_csv_zip(
    platform: str = Query(ALL_PLATFORMS),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """Register the export so the page can show progress while it downloads."""
    platforms = _requested_platforms(platform)
    sessions = {"android": android_db, "ios": ios_db}
    counts = {"android": AndroidRecordCount, "ios": IosRecordCount}
    window = _window(from_ts, to_ts)

    holds_rows = False
    total = 0
    for name in platforms:
        if await _platform_device_ids(sessions[name], _EXPORT_MODELS_FOR[name]):
            holds_rows = True
        total += await _platform_row_total(sessions[name], name, counts[name], window)

    if not holds_rows:
        raise HTTPException(status_code=404, detail="No sensor data found to export")

    return await _start_zip_job(
        f"all:{platform}",
        _archive_name(_all_scope_name(platform), window),
        total,
    )


@router.get("/all.zip")
async def export_all_csv_zip(
    job: str | None = Query(None),
    platform: str = Query(ALL_PLATFORMS),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    platforms = _requested_platforms(platform)
    sessions = {"android": android_db, "ios": ios_db}

    holds_rows = False
    for name in platforms:
        if await _platform_device_ids(sessions[name], _EXPORT_MODELS_FOR[name]):
            holds_rows = True
            break

    if not holds_rows:
        raise HTTPException(status_code=404, detail="No sensor data found to export")

    window = _window(from_ts, to_ts)
    scope = f"all:{platform}"
    return _zip_streaming_response(
        _all_members(window, platforms),
        _archive_name(_all_scope_name(platform), window),
        _progress_job(job, scope),
        _export_manifest(scope, window),
    )
