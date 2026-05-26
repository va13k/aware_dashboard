import asyncio
import json
import logging
import os
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AndroidSessionLocal, IosSessionLocal
from app.models import (
    AndroidAccelerometer,
    AndroidApplicationsCrashes,
    AndroidApplicationsForeground,
    AndroidApplicationsHistory,
    AndroidApplicationsNotifications,
    AndroidBarometer,
    AndroidBattery,
    AndroidBatteryCharges,
    AndroidBatteryDischarges,
    AndroidBluetooth,
    AndroidCalls,
    AndroidEsms,
    AndroidGravity,
    AndroidGyroscope,
    AndroidInstallations,
    AndroidKeyboard,
    AndroidLight,
    AndroidLinearAccelerometer,
    AndroidLocations,
    AndroidMagnetometer,
    AndroidMessages,
    AndroidNetwork,
    AndroidNetworkTraffic,
    AndroidNotes,
    AndroidPluginAmbientNoise,
    AndroidPluginOpenweather,
    AndroidProximity,
    AndroidRotation,
    AndroidScreen,
    AndroidScreentext,
    AndroidSignificant,
    AndroidTelephony,
    AndroidTemperature,
    AndroidTimezone,
    AndroidTouch,
    AndroidWifi,
    IosAccelerometer,
    IosBarometer,
    IosBattery,
    IosBatteryCharges,
    IosBatteryDischarges,
    IosBluetooth,
    IosCalls,
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

router = APIRouter(prefix="/overview", tags=["overview"])
logger = logging.getLogger(__name__)

_CACHE_FILE = "/app/cache/overview_cache.json"


def _load_overview_from_disk() -> dict | None:
    try:
        with open(_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _save_overview_to_disk(cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        logger.error(f"Failed to save overview cache to disk: {e}")


_overview_cache: dict | None = _load_overview_from_disk()

ANDROID_SENSOR_MAP: dict[str, object] = {
    "accelerometer": AndroidAccelerometer,
    "applications": AndroidApplicationsForeground,
    "applications-crashes": AndroidApplicationsCrashes,
    "applications-history": AndroidApplicationsHistory,
    "applications-notifications": AndroidApplicationsNotifications,
    "barometer": AndroidBarometer,
    "battery": AndroidBattery,
    "battery-charges": AndroidBatteryCharges,
    "battery-discharges": AndroidBatteryDischarges,
    "bluetooth": AndroidBluetooth,
    "calls": AndroidCalls,
    "esms": AndroidEsms,
    "gravity": AndroidGravity,
    "gyroscope": AndroidGyroscope,
    "installations": AndroidInstallations,
    "keyboard": AndroidKeyboard,
    "light": AndroidLight,
    "linear-accelerometer": AndroidLinearAccelerometer,
    "locations": AndroidLocations,
    "magnetometer": AndroidMagnetometer,
    "messages": AndroidMessages,
    "network": AndroidNetwork,
    "network-traffic": AndroidNetworkTraffic,
    "notes": AndroidNotes,
    "plugin-ambient-noise": AndroidPluginAmbientNoise,
    "plugin-openweather": AndroidPluginOpenweather,
    "proximity": AndroidProximity,
    "rotation": AndroidRotation,
    "screen": AndroidScreen,
    "screentext": AndroidScreentext,
    "significant-motion": AndroidSignificant,
    "telephony": AndroidTelephony,
    "temperature": AndroidTemperature,
    "timezone": AndroidTimezone,
    "touch": AndroidTouch,
    "wifi": AndroidWifi,
}

# wifi uses two tables — listed as a tuple; we sum counts and take the latest ts
IOS_SENSOR_MAP: dict[str, object] = {
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
    "significant-motion": IosSignificantMotion,
    "studentlife-audio": IosPluginStudentlifeAudio,
    "timezone": IosTimezone,
    "wifi": (IosSensorWifi, IosWifi),
}


async def _row_counts(db: AsyncSession, db_name: str) -> dict[str, int]:
    """Single INFORMATION_SCHEMA query — returns approximate counts for all tables instantly."""
    try:
        result = await db.execute(
            text(
                "SELECT TABLE_NAME, TABLE_ROWS "
                "FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = :db"
            ),
            {"db": db_name},
        )
        return {row[0]: int(row[1] or 0) for row in result.all()}
    except Exception:
        return {}


async def _table_last_ts(db: AsyncSession, table_name: str) -> float | None:
    """Get the most recent timestamp using the primary key — O(log n), no full scan."""
    try:
        result = await db.execute(
            text(f"SELECT timestamp FROM `{table_name}` ORDER BY _id DESC LIMIT 1")
        )
        row = result.one_or_none()
        return float(row[0]) if row and row[0] is not None else None
    except (OperationalError, ProgrammingError):
        await db.rollback()
        return None


async def _sensor_stats(
    db: AsyncSession, entry, counts: dict[str, int]
) -> dict | None:
    if isinstance(entry, tuple):
        parts = []
        for model in entry:
            name = model.__tablename__
            last_ts = await _table_last_ts(db, name)
            if last_ts is not None:
                parts.append({"count": counts.get(name, 0), "last_ts": last_ts})
        if not parts:
            return None
        return {
            "count": sum(p["count"] for p in parts),
            "last_ts": max(p["last_ts"] for p in parts),
        }
    name = entry.__tablename__
    last_ts = await _table_last_ts(db, name)
    if last_ts is None:
        return None
    return {"count": counts.get(name, 0), "last_ts": last_ts}


async def _platform_stats(db: AsyncSession, sensor_map: dict, db_name: str) -> dict:
    counts = await _row_counts(db, db_name)
    results = {}
    for key, entry in sensor_map.items():
        results[key] = await _sensor_stats(db, entry, counts)
    return results


async def _refresh_overview_cache() -> None:
    global _overview_cache
    try:
        async with AndroidSessionLocal() as adb:
            async with IosSessionLocal() as idb:
                android_result, ios_result = await asyncio.gather(
                    _platform_stats(adb, ANDROID_SENSOR_MAP, "aware_android"),
                    _platform_stats(idb, IOS_SENSOR_MAP, "aware_ios"),
                )
        _overview_cache = {"android": android_result, "ios": ios_result}
        _save_overview_to_disk(_overview_cache)
        logger.info("Overview cache updated")
    except Exception as e:
        logger.error(f"Overview cache refresh failed: {e}")


async def background_overview_refresh_loop() -> None:
    while True:
        await _refresh_overview_cache()
        await asyncio.sleep(300)


@router.get("")
async def get_overview():
    if _overview_cache is not None:
        return _overview_cache
    return {"android": {}, "ios": {}}
