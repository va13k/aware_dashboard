import asyncio
import json
import logging
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import ProgrammingError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_android_db, get_ios_db, AndroidSessionLocal, IosSessionLocal

logger = logging.getLogger(__name__)

_CACHE_FILE = "/app/cache/devices_cache.json"


def _load_cache_from_disk() -> dict:
    try:
        with open(_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"android": [], "ios": []}


def _save_cache_to_disk(cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        logger.error(f"Failed to save devices cache to disk: {e}")


_devices_cache: dict = _load_cache_from_disk()


async def _refresh_cache() -> None:
    global _devices_cache
    android: list = []
    ios: list = []
    try:
        async with AndroidSessionLocal() as adb:
            android = await list_android_devices(adb)
    except Exception as e:
        logger.error(f"Devices cache (android) refresh failed: {e}")
        android = _devices_cache["android"]
    try:
        async with IosSessionLocal() as idb:
            ios = await list_ios_devices(idb)
    except Exception as e:
        logger.error(f"Devices cache (ios) refresh failed: {e}")
        ios = _devices_cache["ios"]
    _devices_cache = {"android": android, "ios": ios}
    _save_cache_to_disk(_devices_cache)
    logger.info(f"Devices cache updated: {len(android)} android, {len(ios)} ios")


async def background_refresh_loop() -> None:
    """Run forever, refreshing the devices cache every 5 minutes."""
    while True:
        await _refresh_cache()
        await asyncio.sleep(300)
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
    IosBarometer,
    IosBattery,
    IosBatteryCharges,
    IosBatteryDischarges,
    IosBluetooth,
    IosCalls,
    IosDevice,
    IosEsm,
    IosFitbitData,
    IosFitbitDevice,
    IosGoogleFusedLocation,
    IosGyroscope,
    IosHealthKit,
    IosHealthKitCategory,
    IosHealthKitQuantity,
    IosHealthKitWorkout,
    IosLinearAccelerometer,
    IosLocations,
    IosLocationVisit,
    IosMagnetometer,
    IosMemory,
    IosNetwork,
    IosPedometer,
    IosPluginActivityRecognition,
    IosPluginAmbientNoise,
    IosPluginBleHeartrate,
    IosPluginCalendar,
    IosPluginCalendarEsmScheduler,
    IosPluginContacts,
    IosPluginDeviceUsage,
    IosPluginFitbit,
    IosPluginHeadphoneMotion,
    IosPluginIosEsm,
    IosPluginNtptime,
    IosPluginOpenweather,
    IosPluginStudentlifeAudio,
    IosProcessor,
    IosProximity,
    IosPushNotification,
    IosRotation,
    IosScreen,
    IosSensorWifi,
    IosSignificantMotion,
    IosTimezone,
    IosWifi,
)

router = APIRouter(prefix="/devices", tags=["devices"])

DEVICE_METADATA_FIELDS = (
    "board",
    "brand",
    "device",
    "build_id",
    "hardware",
    "manufacturer",
    "model",
    "product",
    "serial",
    "release",
    "release_type",
    "sdk",
    "label",
)

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
    "ambient-noise": IosPluginAmbientNoise,
    "barometer": IosBarometer,
    "battery": IosBattery,
    "battery-charges": IosBatteryCharges,
    "battery-discharges": IosBatteryDischarges,
    "ble-heartrate": IosPluginBleHeartrate,
    "bluetooth": IosBluetooth,
    "calendar": IosPluginCalendar,
    "calendar-esm-scheduler": IosPluginCalendarEsmScheduler,
    "calls": IosCalls,
    "contacts": IosPluginContacts,
    "device-usage": IosPluginDeviceUsage,
    "esm": IosEsm,
    "esm-scheduler": IosPluginIosEsm,
    "fitbit": IosPluginFitbit,
    "fitbit-data": IosFitbitData,
    "fitbit-device": IosFitbitDevice,
    "fused-location": IosGoogleFusedLocation,
    "gyroscope": IosGyroscope,
    "headphone-motion": IosPluginHeadphoneMotion,
    "health-kit": IosHealthKit,
    "health-kit/category": IosHealthKitCategory,
    "health-kit/quantity": IosHealthKitQuantity,
    "health-kit/workout": IosHealthKitWorkout,
    "linear-accelerometer": IosLinearAccelerometer,
    "location-visit": IosLocationVisit,
    "locations": IosLocations,
    "magnetometer": IosMagnetometer,
    "memory": IosMemory,
    "network": IosNetwork,
    "ntptime": IosPluginNtptime,
    "openweather": IosPluginOpenweather,
    "pedometer": IosPedometer,
    "processor": IosProcessor,
    "proximity": IosProximity,
    "push-notification": IosPushNotification,
    "rotation": IosRotation,
    "screen": IosScreen,
    "sensor_wifi": IosSensorWifi,
    "significant-motion": IosSignificantMotion,
    "studentlife-audio": IosPluginStudentlifeAudio,
    "timezone": IosTimezone,
    "wifi": IosWifi,
}


def _row_to_dict(row):
    if row is None:
        return None
    return {column.name.lstrip("_"): getattr(row, column.name) for column in row.__table__.columns}


def _flatten_device_row(row):
    row_dict = _row_to_dict(row)
    if row_dict is None:
        return None

    data = row_dict.pop("data", None)
    if isinstance(data, dict):
        return {**row_dict, **data}

    return row_dict


def _metadata_score(row_dict):
    if not row_dict:
        return 0
    return sum(1 for field in DEVICE_METADATA_FIELDS if row_dict.get(field) not in (None, ""))


def _timestamp_score(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0
    return 0


async def _rollback_after_table_error(db: AsyncSession):
    try:
        await db.rollback()
    except SQLAlchemyError:
        pass


async def _latest_row(db: AsyncSession, model, device_id: str):
    result = await db.execute(
        select(model).where(model.device_id == device_id).order_by(model.timestamp.desc()).limit(1)
    )
    return result.scalars().first()


async def _best_device_row(db: AsyncSession, model, device_id: str):
    result = await db.execute(
        select(model).where(model.device_id == device_id).order_by(model.timestamp.desc())
    )
    rows = result.scalars().all()
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            _metadata_score(_flatten_device_row(row)),
            _timestamp_score(_flatten_device_row(row).get("timestamp")),
        ),
    )


async def _max_timestamps_by_device(db: AsyncSession, model):
    try:
        result = await db.execute(
            select(
                model.device_id,
                func.max(model.timestamp).label("last_seen"),
            ).group_by(model.device_id)
        )
    except (ProgrammingError, OperationalError, SQLAlchemyError):
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


async def _device_metadata_by_device(db: AsyncSession, model):
    try:
        result = await db.execute(select(model).order_by(model.timestamp.desc()))
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback_after_table_error(db)
        return {}

    metadata_by_device = {}
    for row in result.scalars().all():
        row_dict = _flatten_device_row(row)
        if not row_dict:
            continue

        device_id = row_dict.get("device_id")
        if device_id is None:
            continue

        device_id = str(device_id)
        current = metadata_by_device.get(device_id)
        if current is None or (
            _metadata_score(row_dict),
            _timestamp_score(row_dict.get("timestamp")),
        ) > (
            _metadata_score(current),
            _timestamp_score(current.get("timestamp")),
        ):
            metadata_by_device[device_id] = row_dict

    return metadata_by_device


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
    device = await _best_device_row(db, device_model, device_id)
    device_dict = _flatten_device_row(device)
    stream_details = []

    for key, model in streams.items():
        try:
            stream_details.append(await _stream_summary(db, key, model, device_id))
        except (ProgrammingError, OperationalError, SQLAlchemyError):
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
        "device": device_dict,
        "streams": stream_details,
    }


@router.get("/android")
async def list_android_devices(db: AsyncSession = Depends(get_android_db)):
    last_seen_by_device = await _combined_last_seen_by_device(
        db,
        [AndroidDevice, *ANDROID_STREAMS.values()],
    )
    metadata_by_device = await _device_metadata_by_device(db, AndroidDevice)

    devices = []
    for device_id, last_seen in last_seen_by_device.items():
        metadata = metadata_by_device.get(device_id, {})
        devices.append(
            {
                "device_id": device_id,
                **{
                    field: metadata.get(field)
                    for field in DEVICE_METADATA_FIELDS
                    if metadata.get(field) not in (None, "")
                },
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

    metadata_by_device = await _device_metadata_by_device(db, IosDevice)

    devices = []
    for device_id, last_seen in last_seen_by_device.items():
        metadata = metadata_by_device.get(device_id, {})
        devices.append(
            {
                "device_id": device_id,
                **{
                    field: metadata.get(field)
                    for field in DEVICE_METADATA_FIELDS
                    if metadata.get(field) not in (None, "")
                },
                "last_seen": last_seen,
                "platform": "ios",
            }
        )

    return sorted(devices, key=lambda d: d["last_seen"], reverse=True)


@router.get("")
async def list_all_devices():
    return _devices_cache


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
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        raise HTTPException(status_code=404, detail="Device data is unavailable")
