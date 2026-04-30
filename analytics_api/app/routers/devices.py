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
    return {
        column.name.lstrip("_"): getattr(row, column.name)
        for column in row.__table__.columns
    }


async def _latest_row(db: AsyncSession, model, device_id: str):
    result = await db.execute(
        select(model)
        .where(model.device_id == device_id)
        .order_by(model.timestamp.desc())
        .limit(1)
    )
    return result.scalars().first()


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
            stream_details.append({
                "key": key,
                "count": 0,
                "last_seen": None,
                "latest": None,
            })

    return {
        "platform": platform,
        "device_id": device_id,
        "device": _row_to_dict(device),
        "streams": stream_details,
    }


@router.get("/android")
async def list_android_devices(db: AsyncSession = Depends(get_android_db)):
    result = await db.execute(
        select(
            AndroidDevice.device_id,
            AndroidDevice.manufacturer,
            AndroidDevice.model,
            func.max(AndroidDevice.timestamp).label("last_seen"),
        ).group_by(AndroidDevice.device_id, AndroidDevice.manufacturer, AndroidDevice.model)
        .order_by(func.max(AndroidDevice.timestamp).desc())
    )
    rows = result.all()
    return [
        {
            "device_id": r.device_id,
            "manufacturer": r.manufacturer,
            "model": r.model,
            "last_seen": r.last_seen,
            "platform": "android",
        }
        for r in rows
    ]


@router.get("/ios")
async def list_ios_devices(db: AsyncSession = Depends(get_ios_db)):
    try:
        result = await db.execute(
            select(
                IosDevice.device_id,
                func.max(IosDevice.timestamp).label("last_seen"),
            ).group_by(IosDevice.device_id)
            .order_by(func.max(IosDevice.timestamp).desc())
        )
        rows = result.all()
        if not rows:
            result = await db.execute(
                select(
                    IosBattery.device_id,
                    func.max(IosBattery.timestamp).label("last_seen"),
                ).group_by(IosBattery.device_id)
                .order_by(func.max(IosBattery.timestamp).desc())
            )
            rows = result.all()
        return [
            {
                "device_id": r.device_id,
                "last_seen": r.last_seen,
                "platform": "ios",
            }
            for r in rows
        ]
    except (ProgrammingError, OperationalError):
        return []


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
