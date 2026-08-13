import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_ios_db
from app.services.series import (
    DEFAULT_BUCKETS,
    MAX_BUCKETS,
    bucketed_series,
    clamp_window,
)
from app.models import (
    IosAccelerometer,
    IosAwareLog,
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
from app.schemas import IosSchema, SeriesBucketSchema

router = APIRouter(prefix="/ios/{device_id}", tags=["ios"])

# The largest window a single data request may pull. The dashboard asks for at
# most 1500 points per chart; this ceiling leaves headroom for direct API use
# while keeping a single-device range scan bounded. Full-history dumps go
# through the CSV export endpoints, not these JSON routes.
MAX_RECORD_LIMIT = 5000


def _base_query(model, device_id, from_ts, to_ts, limit, offset):
    q = select(model).where(model.device_id == device_id)
    if from_ts is not None:
        q = q.where(model.timestamp >= from_ts)
    if to_ts is not None:
        q = q.where(model.timestamp <= to_ts)
    return q.order_by(model.timestamp.desc()).limit(limit).offset(offset)


async def _sensor_rows(db: AsyncSession, models, device_id, from_ts, to_ts, limit, offset):
    rows = []
    for model in models:
        try:
            result = await db.execute(_base_query(model, device_id, from_ts, to_ts, limit, offset))
            rows.extend(
                IosSchema.model_validate(row).model_dump()
                for row in result.scalars().all()
            )
        except (OperationalError, ProgrammingError):
            await db.rollback()
    return sorted(rows, key=lambda row: row["timestamp"], reverse=True)[:limit]


@router.get("/accelerometer", response_model=list[IosSchema])
async def get_accelerometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginAmbientNoise, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/plugin-ambient-noise", response_model=list[IosSchema])
async def get_plugin_ambient_noise(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosCalls, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/contacts", response_model=list[IosSchema])
async def get_contacts(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    """The questionnaires this device was shown, from both tables that hold them."""
    return await _sensor_rows(
        db, (IosPluginIosEsm, IosEsm), device_id, from_ts, to_ts, limit, offset
    )


@router.get("/esm-scheduler", response_model=list[IosSchema])
async def get_esm_scheduler(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosProcessor, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/proximity", response_model=list[IosSchema])
async def get_proximity(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosProximity, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/push-notification", response_model=list[IosSchema])
async def get_push_notification(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(
        _base_query(IosPluginStudentlifeAudio, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/device", response_model=list[IosSchema])
async def get_device(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    """What the phone reports about itself: make, hardware, OS."""
    result = await db.execute(_base_query(IosDevice, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/aware-log", response_model=list[IosSchema])
async def get_aware_log(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosAwareLog, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/timezone", response_model=list[IosSchema])
async def get_timezone(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
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
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    return await _sensor_rows(
        db, (IosSensorWifi, IosWifi), device_id, from_ts, to_ts, limit, offset
    )


# ---------------------------------------------------------------------------
# Bucketed series — consistent point density for any window
# ---------------------------------------------------------------------------
#
# iOS keeps every reading in an opaque ``data`` JSON blob (see models.py), so
# the value column is extracted at query time with ``data[key].as_float()``
# (MySQL ``JSON_EXTRACT`` + a null-safe numeric cast). The candidate-key lists
# mirror the dashboard's ``firstNumber``/``vectorMagnitude`` fallbacks in
# ``config/sensors.ts`` so a plotted series matches the raw-record view: iOS may
# store vector components as ``double_values_N`` or ``x/y/z`` (rotation also
# roll/pitch/yaw, headphone-motion also acceleration_*), hence the COALESCE.


def _num(model, *keys):
    """First present numeric JSON key — mirrors the FE ``firstNumber`` fallback."""
    exprs = [model.data[key].as_float() for key in keys]
    return exprs[0] if len(exprs) == 1 else func.coalesce(*exprs)


def _magnitude(model, *components):
    """√(Σ cᵢ²) where each component is the first present of its candidate keys."""
    squares = []
    for keys in components:
        component = _num(model, *keys)
        squares.append(component * component)
    return func.sqrt(sum(squares))


_XYZ = (
    ("double_values_0", "x"),
    ("double_values_1", "y"),
    ("double_values_2", "z"),
)


# sensor slug -> (model, value expression). Only numeric *continuous* sensors
# belong here; event/tabular sensors keep the raw-record + logs view. Slugs with
# a "/" (health-kit/quantity, …) are intentionally absent: the `{sensor}` path
# param cannot capture a slash.
_SERIES_TARGETS: dict[str, tuple] = {
    "accelerometer": (IosAccelerometer, _magnitude(IosAccelerometer, *_XYZ)),
    "gyroscope": (IosGyroscope, _magnitude(IosGyroscope, *_XYZ)),
    "linear-accelerometer": (
        IosLinearAccelerometer,
        _magnitude(IosLinearAccelerometer, *_XYZ),
    ),
    "magnetometer": (IosMagnetometer, _magnitude(IosMagnetometer, *_XYZ)),
    "rotation": (
        IosRotation,
        _magnitude(
            IosRotation,
            ("double_values_0", "x", "roll"),
            ("double_values_1", "y", "pitch"),
            ("double_values_2", "z", "yaw"),
        ),
    ),
    "headphone-motion": (
        IosPluginHeadphoneMotion,
        _magnitude(
            IosPluginHeadphoneMotion,
            ("double_values_0", "x", "acceleration_x"),
            ("double_values_1", "y", "acceleration_y"),
            ("double_values_2", "z", "acceleration_z"),
        ),
    ),
    "barometer": (IosBarometer, _num(IosBarometer, "pressure", "double_values_0")),
    "battery": (IosBattery, _num(IosBattery, "battery_level", "level", "batteryLevel")),
    "bluetooth": (IosBluetooth, _num(IosBluetooth, "bt_rssi", "rssi")),
    "locations": (
        IosLocations,
        _num(IosLocations, "double_speed", "speed", "horizontal_accuracy"),
    ),
    "fused-location": (
        IosGoogleFusedLocation,
        _num(IosGoogleFusedLocation, "accuracy", "horizontal_accuracy", "speed"),
    ),
    "ambient-noise": (
        IosPluginAmbientNoise,
        _num(IosPluginAmbientNoise, "double_decibels", "decibels"),
    ),
    "plugin-ambient-noise": (
        IosPluginAmbientNoise,
        _num(IosPluginAmbientNoise, "double_decibels", "decibels"),
    ),
    "processor": (
        IosProcessor,
        _num(
            IosProcessor,
            "double_last_user",
            "double_user_load",
            "double_last_system",
            "double_system_load",
            "load",
            "processor_load",
            "usage",
            "value",
        ),
    ),
    "ble-heartrate": (
        IosPluginBleHeartrate,
        _num(IosPluginBleHeartrate, "heart_rate", "heartrate", "bpm", "value"),
    ),
    "memory": (IosMemory, _num(IosMemory, "used", "free", "total", "value")),
    "ntptime": (
        IosPluginNtptime,
        _num(IosPluginNtptime, "offset", "delay", "latency", "value"),
    ),
    "pedometer": (
        IosPedometer,
        _num(IosPedometer, "step_count", "steps", "number_of_steps", "distance"),
    ),
    "openweather": (
        IosPluginOpenweather,
        _num(IosPluginOpenweather, "temperature", "temp", "value"),
    ),
    "health-kit": (IosHealthKit, _num(IosHealthKit, "value", "quantity")),
}


@router.get("/{sensor}/series", response_model=list[SeriesBucketSchema])
async def get_series(
    sensor: str,
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    buckets: int = Query(DEFAULT_BUCKETS, ge=1, le=MAX_BUCKETS),
    db: AsyncSession = Depends(get_ios_db),
):
    target = _SERIES_TARGETS.get(sensor)
    if target is None:
        raise HTTPException(
            status_code=404, detail=f"No plottable series for sensor '{sensor}'"
        )
    model, value_expr = target
    return await bucketed_series(
        db, model, value_expr, device_id, from_ts, to_ts, buckets
    )


# ---------------------------------------------------------------------------
# CSV export — all rows, no pagination limit
# ---------------------------------------------------------------------------

_EXPORT_MODELS: dict[str, object] = {
    "accelerometer": IosAccelerometer,
    "activity": IosPluginActivityRecognition,
    "ambient-noise": IosPluginAmbientNoise,
    "plugin-ambient-noise": IosPluginAmbientNoise,
    "barometer": IosBarometer,
    "battery": IosBattery,
    "battery-charges": IosBatteryCharges,
    "battery-discharges": IosBatteryDischarges,
    "ble-heartrate": IosPluginBleHeartrate,
    "bluetooth": IosBluetooth,
    "calendar": IosPluginCalendar,
    "esm-scheduler": IosPluginCalendarEsmScheduler,
    "calls": IosCalls,
    "contacts": IosPluginContacts,
    "device-usage": IosPluginDeviceUsage,
    "esm": (IosPluginIosEsm, IosEsm),
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
    "aware-log": IosAwareLog,
    "device": IosDevice,
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

    models = model if isinstance(model, tuple) else (model,)
    # Always bound the scan: an open export would range-scan the whole table for
    # a high-rate sensor. The full selected period is still exported; only a
    # literal "all time" request is capped (to the most recent year).
    from_ts, to_ts = clamp_window(from_ts, to_ts)
    rows = []
    for m in models:
        try:
            q = (
                select(m)
                .where(m.device_id == device_id)
                .where(m.timestamp >= from_ts)
                .where(m.timestamp <= to_ts)
                .order_by(m.timestamp.asc())
            )
            result = await db.execute(q)
            rows.extend(
                IosSchema.model_validate(row).model_dump()
                for row in result.scalars().all()
            )
        except (OperationalError, ProgrammingError):
            await db.rollback()
    rows = sorted(rows, key=lambda row: row["id"])
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for sensor: {sensor}",
        )

    buf = io.StringIO()
    records = rows
    for r in records:
        ts = r["timestamp"]
        r["timestamp"] = datetime.fromtimestamp(
            ts / 1000 if ts >= 1e11 else ts, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
        r.pop("device_id", None)
    # Union all keys so every row has the same columns
    all_keys: list[str] = list(dict.fromkeys(k for rec in records for k in rec))
    writer = csv.DictWriter(buf, fieldnames=all_keys, extrasaction="ignore", restval="")
    writer.writeheader()
    writer.writerows(records)

    filename = f"{device_id}_{sensor.replace('/', '_')}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
