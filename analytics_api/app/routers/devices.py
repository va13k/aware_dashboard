from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import ProgrammingError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_android_db, get_ios_db
from app.models import (
    AndroidAccelerometer,
    AndroidBattery,
    AndroidBluetooth,
    AndroidCalls,
    AndroidApplicationsForeground,
    AndroidDevice,
    AndroidGyroscope,
    AndroidLight,
    AndroidLocations,
    AndroidNetwork,
    AndroidScreen,
    AndroidWifi,
    IosAccelerometer,
    IosBattery,
    IosBluetooth,
    IosCalls,
    IosDevice,
    IosGyroscope,
    IosLocations,
    IosNetwork,
    IosPedometer,
    IosPluginActivityRecognition,
    IosScreen,
    IosWifi,
)

router = APIRouter(prefix="/devices", tags=["devices"])

ANDROID_STREAMS = {
    "accelerometer": AndroidAccelerometer,
    "battery": AndroidBattery,
    "bluetooth": AndroidBluetooth,
    "calls": AndroidCalls,
    "gyroscope": AndroidGyroscope,
    "light": AndroidLight,
    "locations": AndroidLocations,
    "network": AndroidNetwork,
    "screen": AndroidScreen,
    "wifi": AndroidWifi,
    "applications": AndroidApplicationsForeground,
}

IOS_STREAMS = {
    "accelerometer": IosAccelerometer,
    "activity": IosPluginActivityRecognition,
    "battery": IosBattery,
    "bluetooth": IosBluetooth,
    "calls": IosCalls,
    "gyroscope": IosGyroscope,
    "locations": IosLocations,
    "network": IosNetwork,
    "pedometer": IosPedometer,
    "screen": IosScreen,
    "wifi": IosWifi,
}


def _row_to_dict(row):
    if row is None:
        return None
    return {column.name.lstrip("_"): getattr(row, column.name) for column in row.__table__.columns}


async def _rollback_after_table_error(db: AsyncSession):
    await db.rollback()


async def _latest_row(db: AsyncSession, model, device_id: str):
    result = await db.execute(
        select(model).where(model.device_id == device_id).order_by(model.timestamp.desc()).limit(1)
    )
    return result.scalars().first()


async def _max_timestamps_by_device(db: AsyncSession, model):
    try:
        result = await db.execute(
            select(
                model.device_id,
                func.max(model.timestamp).label("last_seen"),
            ).group_by(model.device_id)
        )
    except (ProgrammingError, OperationalError):
        await _rollback_after_table_error(db)
        return {}

    return {
        str(row.device_id): row.last_seen
        for row in result.all()
        if row.device_id is not None and row.last_seen is not None
    }


async def _combined_last_seen_by_device(db: AsyncSession, models):
    last_seen_by_device = {}

    for model in models:
        timestamps = await _max_timestamps_by_device(db, model)
        for device_id, last_seen in timestamps.items():
            current = last_seen_by_device.get(device_id)
            if current is None or last_seen > current:
                last_seen_by_device[device_id] = last_seen

    return last_seen_by_device


async def _latest_android_metadata_by_device(db: AsyncSession):
    try:
        subq = (
            select(
                AndroidDevice.device_id,
                func.max(AndroidDevice.timestamp).label("max_ts"),
            )
            .group_by(AndroidDevice.device_id)
            .subquery()
        )
        result = await db.execute(
            select(
                AndroidDevice.device_id,
                AndroidDevice.manufacturer,
                AndroidDevice.model,
            )
            .join(
                subq,
                (AndroidDevice.device_id == subq.c.device_id)
                & (AndroidDevice.timestamp == subq.c.max_ts),
            )
        )
    except (ProgrammingError, OperationalError):
        await _rollback_after_table_error(db)
        return {}

    return {
        str(row.device_id): {
            "manufacturer": row.manufacturer,
            "model": row.model,
        }
        for row in result.all()
    }


async def _stream_summary(db: AsyncSession, key: str, model, device_id: str):
    count_result = await db.execute(
        select(func.count()).select_from(model).where(model.device_id == device_id)
    )
    count = int(count_result.scalar() or 0)
    latest = await _latest_row(db, model, device_id)
    return {
        "key": key,
        "count": count,
        "last_seen": getattr(latest, "timestamp", None) if latest else None,
        "latest": _row_to_dict(latest),
    }


async def _device_detail(platform: str, device_id: str, db: AsyncSession):
    device_model = AndroidDevice if platform == "android" else IosDevice
    streams = ANDROID_STREAMS if platform == "android" else IOS_STREAMS
    device = await _latest_row(db, device_model, device_id)
    stream_details = []

    for key, model in streams.items():
        try:
            stream_details.append(await _stream_summary(db, key, model, device_id))
        except (ProgrammingError, OperationalError):
            await _rollback_after_table_error(db)
            stream_details.append(
                {
                    "key": key,
                    "count": 0,
                    "last_seen": None,
                    "latest": None,
                }
            )

    return {
        "platform": platform,
        "device_id": device_id,
        "device": _row_to_dict(device),
        "streams": stream_details,
    }


@router.get("/android")
async def list_android_devices(db: AsyncSession = Depends(get_android_db)):
    last_seen_by_device = await _combined_last_seen_by_device(
        db,
        [AndroidDevice, *ANDROID_STREAMS.values()],
    )
    metadata_by_device = await _latest_android_metadata_by_device(db)

    devices = []
    for device_id, last_seen in last_seen_by_device.items():
        metadata = metadata_by_device.get(device_id, {})
        devices.append(
            {
                "device_id": device_id,
                "manufacturer": metadata.get("manufacturer"),
                "model": metadata.get("model"),
                "last_seen": last_seen,
                "platform": "android",
            }
        )

    return sorted(devices, key=lambda d: d["last_seen"], reverse=True)


@router.get("/ios")
async def list_ios_devices(db: AsyncSession = Depends(get_ios_db)):
    last_seen_by_device = await _combined_last_seen_by_device(
        db,
        [IosDevice, *IOS_STREAMS.values()],
    )

    devices = [
        {
            "device_id": device_id,
            "last_seen": last_seen,
            "platform": "ios",
        }
        for device_id, last_seen in last_seen_by_device.items()
    ]

    return sorted(devices, key=lambda d: d["last_seen"], reverse=True)


@router.get("")
async def list_all_devices(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    try:
        android = await list_android_devices(android_db)
    except (ProgrammingError, OperationalError):
        android = []
    try:
        ios = await list_ios_devices(ios_db)
    except (ProgrammingError, OperationalError):
        ios = []
    return {"android": android, "ios": ios}


@router.get("/{platform}/{device_id}")
async def get_device_detail(
    platform: str,
    device_id: str,
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    if platform not in {"android", "ios"}:
        raise HTTPException(status_code=404, detail="Unknown platform")

    db = android_db if platform == "android" else ios_db
    try:
        return await _device_detail(platform, device_id, db)
    except (ProgrammingError, OperationalError):
        raise HTTPException(status_code=404, detail="Device data is unavailable")
