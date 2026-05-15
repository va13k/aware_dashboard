import csv
import io
import re
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_android_db, get_ios_db
from app.routers.android import _EXPORT_MODELS as ANDROID_EXPORT_MODELS
from app.routers.ios import _EXPORT_MODELS as IOS_EXPORT_MODELS
from app.schemas import IosSchema

router = APIRouter(prefix="/export", tags=["export"])

_SAFE_PATH_PART = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_path_part(value: str) -> str:
    cleaned = _SAFE_PATH_PART.sub("_", value).strip("._")
    return cleaned or "unknown"


def _csv_response(records: list[dict]) -> str:
    buf = io.StringIO()
    fieldnames = list(dict.fromkeys(key for record in records for key in record))
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", restval="")
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue()


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


async def _android_records(
    db: AsyncSession,
    model,
    schema,
    device_id: str,
) -> list[dict]:
    try:
        result = await db.execute(
            select(model).where(model.device_id == device_id).order_by(model.timestamp.asc())
        )
    except (OperationalError, ProgrammingError, SQLAlchemyError):
        await _rollback_after_table_error(db)
        return []

    return [schema.model_validate(row).model_dump() for row in result.scalars().all()]


async def _ios_records(
    db: AsyncSession,
    models: tuple,
    device_id: str,
) -> list[dict]:
    records = []
    for model in models:
        try:
            result = await db.execute(
                select(model).where(model.device_id == device_id).order_by(model.timestamp.asc())
            )
        except (OperationalError, ProgrammingError, SQLAlchemyError):
            await _rollback_after_table_error(db)
            continue

        records.extend(
            IosSchema.model_validate(row).model_dump()
            for row in result.scalars().all()
        )
    return sorted(records, key=lambda record: record["timestamp"])


async def _android_records_for_sensor(
    db: AsyncSession,
    model,
    schema,
    device_id: str | None = None,
) -> list[dict]:
    try:
        q = select(model)
        if device_id is not None:
            q = q.where(model.device_id == device_id)
        result = await db.execute(q.order_by(model.device_id.asc(), model.timestamp.asc()))
    except (OperationalError, ProgrammingError, SQLAlchemyError):
        await _rollback_after_table_error(db)
        return []

    return [schema.model_validate(row).model_dump() for row in result.scalars().all()]


async def _ios_records_for_sensor(
    db: AsyncSession,
    models: tuple,
    device_id: str | None = None,
) -> list[dict]:
    records = []
    for model in models:
        try:
            q = select(model)
            if device_id is not None:
                q = q.where(model.device_id == device_id)
            result = await db.execute(q.order_by(model.device_id.asc(), model.timestamp.asc()))
        except (OperationalError, ProgrammingError, SQLAlchemyError):
            await _rollback_after_table_error(db)
            continue

        records.extend(
            IosSchema.model_validate(row).model_dump()
            for row in result.scalars().all()
        )
    return sorted(records, key=lambda record: (str(record["device_id"]), record["timestamp"]))


async def _sensor_stats(db: AsyncSession, models: tuple) -> dict:
    row_count = 0
    device_ids: set[str] = set()
    first_timestamp = None
    last_timestamp = None

    for model in models:
        try:
            stats = await db.execute(
                select(
                    func.count().label("row_count"),
                    func.min(model.timestamp).label("first_timestamp"),
                    func.max(model.timestamp).label("last_timestamp"),
                )
            )
            row = stats.one()
            row_count += int(row.row_count or 0)

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

            device_result = await db.execute(select(model.device_id).distinct())
            device_ids.update(
                str(item[0])
                for item in device_result.all()
                if item[0] not in (None, "")
            )
        except (OperationalError, ProgrammingError, SQLAlchemyError):
            await _rollback_after_table_error(db)

    return {
        "row_count": row_count,
        "devices_with_data": len(device_ids),
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
    }


async def _ios_fields(db: AsyncSession, models: tuple) -> list[str]:
    fields = ["id", "timestamp", "device_id"]
    for model in models:
        try:
            result = await db.execute(select(model))
        except (OperationalError, ProgrammingError, SQLAlchemyError):
            await _rollback_after_table_error(db)
            continue

        for row in result.scalars().all():
            record = IosSchema.model_validate(row).model_dump()
            fields.extend(record.keys())

    return list(dict.fromkeys(fields))


async def _write_platform_device_csvs(
    archive: zipfile.ZipFile,
    platform: str,
    db: AsyncSession,
    device_id: str,
) -> int:
    files_written = 0
    safe_device_id = _safe_path_part(device_id)

    if platform == "android":
        for sensor, (model, schema) in ANDROID_EXPORT_MODELS.items():
            records = await _android_records(db, model, schema, device_id)
            if not records:
                continue
            archive.writestr(
                f"android/{safe_device_id}/{_safe_path_part(sensor)}.csv",
                _csv_response(records),
            )
            files_written += 1
        return files_written

    for sensor, model_entry in IOS_EXPORT_MODELS.items():
        records = await _ios_records(db, _ios_models(model_entry), device_id)
        if not records:
            continue
        archive.writestr(
            f"ios/{safe_device_id}/{_safe_path_part(sensor)}.csv",
            _csv_response(records),
        )
        files_written += 1

    return files_written


def _zip_response(zip_buf: io.BytesIO, filename: str) -> Response:
    zip_buf.seek(0)
    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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

    for sensor, (model, schema) in ANDROID_EXPORT_MODELS.items():
        platforms["android"]["sensors"][sensor] = {
            **await _sensor_stats(android_db, (model,)),
            "fields": list(dict.fromkeys(schema.model_fields.keys())),
        }

    for sensor, model_entry in IOS_EXPORT_MODELS.items():
        models = _ios_models(model_entry)
        platforms["ios"]["sensors"][sensor] = {
            **await _sensor_stats(ios_db, models),
            "fields": await _ios_fields(ios_db, models),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platforms": platforms,
    }


@router.get("/device/{platform}/{device_id}.zip")
async def export_device_csv_zip(
    platform: str,
    device_id: str,
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    _platform_exports(platform)
    db = android_db if platform == "android" else ios_db
    zip_buf = io.BytesIO()

    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        files_written = await _write_platform_device_csvs(archive, platform, db, device_id)

    if files_written == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No sensor data found for {platform} device: {device_id}",
        )

    return _zip_response(zip_buf, f"{platform}_{_safe_path_part(device_id)}.zip")


@router.get("/sensor/{platform}/{sensor:path}.zip")
async def export_sensor_csv_zip(
    platform: str,
    sensor: str,
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    export_models = _platform_exports(platform)
    model_entry = export_models.get(sensor)
    if not model_entry:
        raise HTTPException(status_code=404, detail=f"Unknown sensor: {sensor}")

    db = android_db if platform == "android" else ios_db

    if platform == "android":
        model, schema = model_entry
        records = await _android_records_for_sensor(db, model, schema)
    else:
        records = await _ios_records_for_sensor(db, _ios_models(model_entry))

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {platform} sensor: {sensor}",
        )

    safe_sensor = _safe_path_part(sensor)
    csv_name = f"{platform}_{safe_sensor}.csv"
    zip_buf = io.BytesIO()

    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(csv_name, _csv_response(records))

    return _zip_response(zip_buf, f"{platform}_{safe_sensor}.zip")


@router.get("/all.zip")
async def export_all_csv_zip(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    zip_buf = io.BytesIO()
    files_written = 0

    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        android_device_ids = await _platform_device_ids(android_db, ANDROID_EXPORT_MODELS)
        for device_id in android_device_ids:
            safe_device_id = _safe_path_part(device_id)
            for sensor, (model, schema) in ANDROID_EXPORT_MODELS.items():
                records = await _android_records(android_db, model, schema, device_id)
                if not records:
                    continue
                archive.writestr(
                    f"android/{safe_device_id}/{_safe_path_part(sensor)}.csv",
                    _csv_response(records),
                )
                files_written += 1

        ios_device_ids = await _platform_device_ids(ios_db, IOS_EXPORT_MODELS)
        for device_id in ios_device_ids:
            safe_device_id = _safe_path_part(device_id)
            for sensor, model_entry in IOS_EXPORT_MODELS.items():
                models = model_entry if isinstance(model_entry, tuple) else (model_entry,)
                records = await _ios_records(ios_db, models, device_id)
                if not records:
                    continue
                archive.writestr(
                    f"ios/{safe_device_id}/{_safe_path_part(sensor)}.csv",
                    _csv_response(records),
                )
                files_written += 1

    if files_written == 0:
        raise HTTPException(status_code=404, detail="No sensor data found to export")

    zip_buf.seek(0)
    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="all.zip"'},
    )
