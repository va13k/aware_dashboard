import csv
import io
import re
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AndroidSessionLocal, IosSessionLocal, get_android_db, get_ios_db
from app.models import AndroidRecordCount, IosRecordCount
from app.routers.android import _EXPORT_MODELS as ANDROID_EXPORT_MODELS
from app.routers.ios import _EXPORT_MODELS as IOS_EXPORT_MODELS
from app.schemas import IosSchema
from app.services import backup_jobs as jobs
from app.services import record_counts

router = APIRouter(prefix="/export", tags=["export"])

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


async def _paged(db: AsyncSession, model, device_id: str | None, render):
    """Walk a table in ``_id`` order, yielding one rendered batch at a time.

    Paging on the primary key rather than ``OFFSET`` keeps each round trip an
    indexed seek, and means the rows a batch held can be released before the next
    one is read.
    """
    last_id = 0
    while True:
        query = select(model).where(model._id > last_id)
        if device_id is not None:
            query = query.where(model.device_id == device_id)
        try:
            result = await db.execute(query.order_by(model._id.asc()).limit(EXPORT_BATCH))
            rows = result.scalars().all()
        except (OperationalError, ProgrammingError, SQLAlchemyError):
            await _rollback_after_table_error(db)
            return
        if not rows:
            return
        yield [render(row) for row in rows]
        last_id = rows[-1]._id


async def _has_rows(db: AsyncSession, model, device_id: str | None = None) -> bool:
    query = select(model._id)
    if device_id is not None:
        query = query.where(model.device_id == device_id)
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


async def _device_ids_for_model(db: AsyncSession, model) -> set[str]:
    try:
        result = await db.execute(select(model.device_id).distinct())
    except (OperationalError, ProgrammingError, SQLAlchemyError):
        await _rollback_after_table_error(db)
        return set()

    return {str(row[0]) for row in result.all() if row[0] not in (None, "")}


async def _platform_device_ids(db: AsyncSession, export_models: dict[str, object]) -> list[str]:
    device_ids: set[str] = set()
    for entry in export_models.values():
        models = (entry[0],) if _is_android_export_entry(entry) else (
            entry if isinstance(entry, tuple) else (entry,)
        )
        for model in models:
            device_ids.update(await _device_ids_for_model(db, model))
    return sorted(device_ids)


def _is_android_export_entry(entry: object) -> bool:
    return isinstance(entry, tuple) and len(entry) == 2 and hasattr(entry[1], "model_fields")


def _platform_exports(platform: str):
    if platform == "android":
        return ANDROID_EXPORT_MODELS
    if platform == "ios":
        return IOS_EXPORT_MODELS
    raise HTTPException(status_code=404, detail="Unknown platform")


def _ios_models(model_entry: object) -> tuple:
    return model_entry if isinstance(model_entry, tuple) else (model_entry,)






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
            stats = await db.execute(
                select(
                    func.min(model.timestamp).label("first_timestamp"),
                    func.max(model.timestamp).label("last_timestamp"),
                )
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
                    select(func.count()).select_from(model)
                )
                row_count += int(count_row.scalar() or 0)
                device_result = await db.execute(select(model.device_id).distinct())
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


async def _stream_archive(members, job=None):
    """Produce a ZIP as it is read.

    `members` is an async iterable of ``(name, fields, batches)``, where
    `batches` yields lists of rendered rows. Nothing larger than one batch and
    the compressor's own buffers is held at a time.
    """
    sink = _Sink()
    try:
        with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
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


async def _sensor_row_total(db: AsyncSession, count_model, sensor: str) -> int:
    totals = await record_counts.sensor_totals(db, count_model)
    return int(totals.get(sensor, (0, 0))[0])


async def _device_row_total(db: AsyncSession, count_model, device_id: str) -> int:
    cached = await record_counts.counts_for_device(db, count_model, device_id)
    return sum(entry["count"] for entry in cached.values())


async def _platform_row_total(db: AsyncSession, count_model) -> int:
    totals = await record_counts.sensor_totals(db, count_model)
    return sum(count for count, _ in totals.values())


def _zip_streaming_response(members, filename: str, job=None) -> StreamingResponse:
    return StreamingResponse(
        _stream_archive(members, job),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Produced as it is sent, so no intermediary should collect it first.
            "X-Accel-Buffering": "no",
        },
    )


async def _chained(db: AsyncSession, models: tuple, device_ids: list[str], render):
    """Every device's rows for one sensor, in turn, as batches.

    Walking device by device keeps the CSV grouped the way it has always been —
    all of one phone's rows together — while still only holding a batch at a time.
    """
    for model in models:
        for device_id in device_ids:
            async for batch in _paged(db, model, device_id, render):
                yield batch


async def _sensor_members(platform: str, sensor: str, model_entry):
    """One sensor across every phone, as a single CSV inside the archive."""
    name = f"{platform}_{_safe_path_part(sensor)}.csv"
    session = AndroidSessionLocal if platform == "android" else IosSessionLocal
    async with session() as db:
        if _is_android_export_entry(model_entry):
            model, schema = model_entry
            devices = sorted(await _device_ids_for_model(db, model))
            yield (
                name,
                _android_fields(schema),
                _chained(db, (model,), devices, lambda row: schema.model_validate(row).model_dump()),
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
            ),
        )


async def _device_members(platform: str, device_id: str):
    """Every sensor this phone has data for, one archive member each."""
    safe_device = _safe_path_part(device_id)
    session = AndroidSessionLocal if platform == "android" else IosSessionLocal
    async with session() as db:
        if platform == "android":
            for sensor, (model, schema) in ANDROID_EXPORT_MODELS.items():
                if not await _has_rows(db, model, device_id):
                    continue
                yield (
                    f"android/{safe_device}/{_safe_path_part(sensor)}.csv",
                    _android_fields(schema),
                    _paged(db, model, device_id, lambda row, s=schema: s.model_validate(row).model_dump()),
                )
            return

        for sensor, model_entry in IOS_EXPORT_MODELS.items():
            models = _ios_models(model_entry)
            if not any([await _has_rows(db, model, device_id) for model in models]):
                continue
            fields = await _ios_field_union(db, models)
            for model in models:
                yield (
                    f"ios/{safe_device}/{_safe_path_part(sensor)}.csv",
                    fields,
                    _paged(db, model, device_id, lambda row: IosSchema.model_validate(row).model_dump()),
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


async def _any_sensor_has_rows(db: AsyncSession, platform: str, device_id: str) -> bool:
    """Whether this phone wrote anything at all.

    Settled before the response begins: once a streaming body is under way its
    status can no longer become a 404.
    """
    exports = _platform_exports(platform)
    for entry in exports.values():
        models = (entry[0],) if _is_android_export_entry(entry) else _ios_models(entry)
        for model in models:
            if await _has_rows(db, model, device_id):
                return True
    return False


@router.post("/device/{platform}/{device_id}.zip")
async def start_device_csv_zip(
    platform: str,
    device_id: str,
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """Register the export so the page can show progress while it downloads."""
    _platform_exports(platform)
    db = android_db if platform == "android" else ios_db
    if not await _any_sensor_has_rows(db, platform, device_id):
        raise HTTPException(
            status_code=404,
            detail=f"No sensor data found for {platform} device: {device_id}",
        )
    model = AndroidRecordCount if platform == "android" else IosRecordCount
    return await _start_zip_job(
        f"device:{platform}:{device_id}",
        f"{platform}_{_safe_path_part(device_id)}.zip",
        await _device_row_total(db, model, device_id),
    )


@router.get("/device/{platform}/{device_id}.zip")
async def export_device_csv_zip(
    platform: str,
    device_id: str,
    job: str | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    _platform_exports(platform)
    db = android_db if platform == "android" else ios_db

    if not await _any_sensor_has_rows(db, platform, device_id):
        raise HTTPException(
            status_code=404,
            detail=f"No sensor data found for {platform} device: {device_id}",
        )

    return _zip_streaming_response(
        _device_members(platform, device_id),
        f"{platform}_{_safe_path_part(device_id)}.zip",
        _progress_job(job, f"device:{platform}:{device_id}"),
    )


@router.post("/sensor/{platform}/{sensor:path}.zip")
async def start_sensor_csv_zip(
    platform: str,
    sensor: str,
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """Register the export so the page can show progress while it downloads."""
    export_models = _platform_exports(platform)
    model_entry = export_models.get(sensor)
    if not model_entry:
        raise HTTPException(status_code=404, detail=f"Unknown sensor: {sensor}")
    db = android_db if platform == "android" else ios_db
    models = (model_entry[0],) if _is_android_export_entry(model_entry) else _ios_models(model_entry)
    if not any([await _has_rows(db, model) for model in models]):
        raise HTTPException(
            status_code=404, detail=f"No data found for {platform} sensor: {sensor}"
        )
    count_model = AndroidRecordCount if platform == "android" else IosRecordCount
    return await _start_zip_job(
        f"sensor:{platform}:{sensor}",
        f"{platform}_{_safe_path_part(sensor)}.zip",
        await _sensor_row_total(db, count_model, sensor),
    )


@router.get("/sensor/{platform}/{sensor:path}.zip")
async def export_sensor_csv_zip(
    platform: str,
    sensor: str,
    job: str | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    export_models = _platform_exports(platform)
    model_entry = export_models.get(sensor)
    if not model_entry:
        raise HTTPException(status_code=404, detail=f"Unknown sensor: {sensor}")

    db = android_db if platform == "android" else ios_db
    models = (model_entry[0],) if _is_android_export_entry(model_entry) else _ios_models(model_entry)

    if not any([await _has_rows(db, model) for model in models]):
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {platform} sensor: {sensor}",
        )

    safe_sensor = _safe_path_part(sensor)
    return _zip_streaming_response(
        _sensor_members(platform, sensor, model_entry),
        f"{platform}_{safe_sensor}.zip",
        _progress_job(job, f"sensor:{platform}:{sensor}"),
    )


async def _all_members():
    """Every sensor of every phone on both platforms."""
    for platform in ("android", "ios"):
        session = AndroidSessionLocal if platform == "android" else IosSessionLocal
        exports = ANDROID_EXPORT_MODELS if platform == "android" else IOS_EXPORT_MODELS
        async with session() as db:
            for device_id in await _platform_device_ids(db, exports):
                async for entry in _device_members(platform, device_id):
                    yield entry


@router.post("/all.zip")
async def start_all_csv_zip(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """Register the export so the page can show progress while it downloads."""
    android = await _platform_device_ids(android_db, ANDROID_EXPORT_MODELS)
    ios = await _platform_device_ids(ios_db, IOS_EXPORT_MODELS)
    if not android and not ios:
        raise HTTPException(status_code=404, detail="No sensor data found to export")

    total = await _platform_row_total(android_db, AndroidRecordCount)
    total += await _platform_row_total(ios_db, IosRecordCount)
    return await _start_zip_job("all", "all.zip", total)


@router.get("/all.zip")
async def export_all_csv_zip(
    job: str | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    android = await _platform_device_ids(android_db, ANDROID_EXPORT_MODELS)
    ios = await _platform_device_ids(ios_db, IOS_EXPORT_MODELS)
    if not android and not ios:
        raise HTTPException(status_code=404, detail="No sensor data found to export")

    return _zip_streaming_response(_all_members(), "all.zip", _progress_job(job, "all"))
