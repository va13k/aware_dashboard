import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_ios_db
from app.models import (
    IosAccelerometer,
    IosBarometer,
    IosBattery,
    IosBatteryCharges,
    IosBatteryDischarges,
    IosBluetooth,
    IosCalls,
    IosCommunication,
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
    IosPushNotification,
    IosRotation,
    IosScreen,
    IosSignificantMotion,
    IosTimezone,
    IosWifi,
)
from app.schemas import IosSchema

router = APIRouter(prefix="/ios/{device_id}", tags=["ios"])


def _base_query(model, device_id, from_ts, to_ts, limit, offset):
    q = select(model).where(model.device_id == device_id)
    if from_ts is not None:
        q = q.where(model.timestamp >= from_ts)
    if to_ts is not None:
        q = q.where(model.timestamp <= to_ts)
    return q.order_by(model.timestamp.desc()).limit(limit).offset(offset)


@router.get("/accelerometer", response_model=list[IosSchema])
async def get_accelerometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosAccelerometer, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/activity", response_model=list[IosSchema])
async def get_activity(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginActivityRecognition, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/ambient-noise", response_model=list[IosSchema])
async def get_ambient_noise(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginAmbientNoise, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/barometer", response_model=list[IosSchema])
async def get_barometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosBarometer, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/battery", response_model=list[IosSchema])
async def get_battery(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosBattery, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/battery-charges", response_model=list[IosSchema])
async def get_battery_charges(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosBatteryCharges, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/battery-discharges", response_model=list[IosSchema])
async def get_battery_discharges(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosBatteryDischarges, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/ble-heartrate", response_model=list[IosSchema])
async def get_ble_heartrate(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginBleHeartrate, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/bluetooth", response_model=list[IosSchema])
async def get_bluetooth(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosBluetooth, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/calendar", response_model=list[IosSchema])
async def get_calendar(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginCalendar, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/calendar-esm-scheduler", response_model=list[IosSchema])
async def get_calendar_esm_scheduler(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginCalendarEsmScheduler, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/calls", response_model=list[IosSchema])
async def get_calls(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosCalls, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/communication", response_model=list[IosSchema])
async def get_communication(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosCommunication, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/contacts", response_model=list[IosSchema])
async def get_contacts(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginContacts, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/device-usage", response_model=list[IosSchema])
async def get_device_usage(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginDeviceUsage, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/esm", response_model=list[IosSchema])
async def get_esm(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosEsm, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/esm-scheduler", response_model=list[IosSchema])
async def get_esm_scheduler(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginIosEsm, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/fitbit", response_model=list[IosSchema])
async def get_fitbit(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginFitbit, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/fitbit-data", response_model=list[IosSchema])
async def get_fitbit_data(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosFitbitData, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/fitbit-device", response_model=list[IosSchema])
async def get_fitbit_device(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosFitbitDevice, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/fused-location", response_model=list[IosSchema])
async def get_fused_location(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosGoogleFusedLocation, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/gyroscope", response_model=list[IosSchema])
async def get_gyroscope(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosGyroscope, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/headphone-motion", response_model=list[IosSchema])
async def get_headphone_motion(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginHeadphoneMotion, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/health-kit", response_model=list[IosSchema])
async def get_health_kit(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosHealthKit, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/health-kit/category", response_model=list[IosSchema])
async def get_health_kit_category(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosHealthKitCategory, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/health-kit/quantity", response_model=list[IosSchema])
async def get_health_kit_quantity(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosHealthKitQuantity, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/health-kit/workout", response_model=list[IosSchema])
async def get_health_kit_workout(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosHealthKitWorkout, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/linear-accelerometer", response_model=list[IosSchema])
async def get_linear_accelerometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosLinearAccelerometer, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/location-visit", response_model=list[IosSchema])
async def get_location_visit(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosLocationVisit, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/locations", response_model=list[IosSchema])
async def get_locations(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosLocations, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/magnetometer", response_model=list[IosSchema])
async def get_magnetometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosMagnetometer, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/memory", response_model=list[IosSchema])
async def get_memory(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosMemory, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/network", response_model=list[IosSchema])
async def get_network(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosNetwork, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/ntptime", response_model=list[IosSchema])
async def get_ntptime(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginNtptime, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/openweather", response_model=list[IosSchema])
async def get_openweather(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginOpenweather, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/pedometer", response_model=list[IosSchema])
async def get_pedometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosPedometer, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/processor", response_model=list[IosSchema])
async def get_processor(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosProcessor, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/push-notification", response_model=list[IosSchema])
async def get_push_notification(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPushNotification, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/rotation", response_model=list[IosSchema])
async def get_rotation(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosRotation, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/screen", response_model=list[IosSchema])
async def get_screen(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosScreen, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/significant-motion", response_model=list[IosSchema])
async def get_significant_motion(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosSignificantMotion, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/studentlife-audio", response_model=list[IosSchema])
async def get_studentlife_audio(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginStudentlifeAudio, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/timezone", response_model=list[IosSchema])
async def get_timezone(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosTimezone, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/wifi", response_model=list[IosSchema])
async def get_wifi(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosWifi, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


# ---------------------------------------------------------------------------
# CSV export — all rows, no pagination limit
# ---------------------------------------------------------------------------

_EXPORT_MODELS: dict[str, object] = {
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
    "communication": IosCommunication,
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
    "push-notification": IosPushNotification,
    "rotation": IosRotation,
    "screen": IosScreen,
    "significant-motion": IosSignificantMotion,
    "studentlife-audio": IosPluginStudentlifeAudio,
    "timezone": IosTimezone,
    "wifi": IosWifi,
}


@router.get("/export")
async def export_csv(
    device_id: str,
    sensor: str = Query(..., description="Sensor slug, e.g. 'accelerometer'"),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    db: AsyncSession = Depends(get_ios_db),
):
    model = _EXPORT_MODELS.get(sensor)
    if not model:
        raise HTTPException(status_code=404, detail=f"Unknown sensor: {sensor}")

    q = select(model).where(model.device_id == device_id)
    if from_ts is not None:
        q = q.where(model.timestamp >= from_ts)
    if to_ts is not None:
        q = q.where(model.timestamp <= to_ts)
    q = q.order_by(model.timestamp.asc())

    result = await db.execute(q)
    rows = result.scalars().all()

    buf = io.StringIO()
    if rows:
        records = [IosSchema.model_validate(r).model_dump() for r in rows]
        # Union all keys so every row has the same columns
        all_keys: list[str] = list(dict.fromkeys(k for rec in records for k in rec))
        writer = csv.DictWriter(buf, fieldnames=all_keys, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(records)
    else:
        writer = csv.DictWriter(buf, fieldnames=["id", "timestamp", "device_id"])
        writer.writeheader()

    filename = f"{device_id}_{sensor.replace('/', '_')}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
