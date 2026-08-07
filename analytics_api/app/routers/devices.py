from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.exc import ProgrammingError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_android_db, get_ios_db
from app.services import record_counts
from app.routers.android import _EXPORT_MODELS as _ANDROID_EXPORT_MODELS
from app.models import (
    AndroidRecordCount,
    IosRecordCount,
    AndroidDevice,
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
from app.models import AndroidAwareStudy
from app.schemas import (
    AndroidStudyEventSchema,
    AndroidStudyListSummarySchema,
    AndroidStudySummarySchema,
    ConfigDiffSchema,
    strip_ios_data_metadata,
)
from app.services import config_diff, study_state

router = APIRouter(prefix="/devices", tags=["devices"])

#: Events kept in the device detail response. The full history is paginated
#: through /devices/android/{device_id}/study-events.
DETAIL_EVENT_LIMIT = 50

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

# Every android sensor gets a stream summary (count + last_seen) so the device
# grid can build a tile per sensor from the detail response alone. Counts come
# from the record-count cache (see _stream_summary), so summarising them all is
# cheap. Derived from the export map — the canonical android sensor registry —
# to stay in sync with it automatically.
ANDROID_STREAMS = {slug: entry[0] for slug, entry in _ANDROID_EXPORT_MODELS.items()}

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
        return {**row_dict, **strip_ios_data_metadata(data)}

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


async def _android_study_rows(db: AsyncSession, device_id: str | None = None):
    query = select(AndroidAwareStudy).order_by(
        AndroidAwareStudy.timestamp, AndroidAwareStudy._id
    )
    if device_id is not None:
        query = query.where(AndroidAwareStudy.device_id == device_id)

    try:
        result = await db.execute(query)
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback_after_table_error(db)
        return []
    return result.scalars().all()


async def _android_study_states(db: AsyncSession, device_id: str | None = None):
    """Derived study state per device, keyed by device id."""
    rows_by_device = {}
    for row in await _android_study_rows(db, device_id):
        if row.device_id is None:
            continue
        rows_by_device.setdefault(str(row.device_id), []).append(row)

    return {
        device: study_state.derive_study_state(rows)
        for device, rows in rows_by_device.items()
    }


def _study_detail(state):
    """The study summary, the config comparison and the recent timeline."""
    diff = config_diff.compare_with_deployed(state.installed_config)
    events = state.events[:DETAIL_EVENT_LIMIT]
    return {
        "study": AndroidStudySummarySchema.model_validate(state.summary).model_dump(),
        "config_diff": ConfigDiffSchema.model_validate(diff).model_dump(),
        "study_events": [
            AndroidStudyEventSchema.model_validate(event).model_dump()
            for event in events
        ],
    }


def _study_list_summary(state):
    diff = config_diff.compare_with_deployed(state.installed_config)
    return AndroidStudyListSummarySchema(
        enrollment_status=state.summary.enrollment_status,
        last_study_event_at=state.summary.last_study_event_at,
        config_status=diff.config_status,
        diff_count=diff.diff_count,
    ).model_dump()


def _last_seen_sort_key(device):
    """Sort by most recent upload, with phones that never uploaded last."""
    last_seen = device.get("last_seen")
    return (last_seen is not None, last_seen or 0)


async def _stream_summary(
    db: AsyncSession, key: str, model, device_id: str, cached_count: int | None = None
):
    # Prefer the cached count; fall back to a live COUNT only on a cache miss
    # (a cold cache, or a sensor with zero rows the refresh never recorded).
    if cached_count is not None:
        count = cached_count
    else:
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

    # One lookup gives every cached per-sensor count for this device; sensors
    # missing from it fall back to a live COUNT inside `_stream_summary`.
    count_model = AndroidRecordCount if platform == "android" else IosRecordCount
    cached_counts = await record_counts.counts_for_device(db, count_model, device_id)

    for key, model in streams.items():
        try:
            stream_details.append(
                await _stream_summary(db, key, model, device_id, cached_counts.get(key))
            )
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

    detail = {
        "platform": platform,
        "device_id": device_id,
        "device": device_dict,
        "streams": stream_details,
    }

    if platform == "android":
        states = await _android_study_states(db, device_id)
        state = states.get(device_id) or study_state.derive_study_state([])
        detail.update(_study_detail(state))

    return detail


@router.get("/android")
async def list_android_devices(db: AsyncSession = Depends(get_android_db)):
    last_seen_by_device = await _combined_last_seen_by_device(
        db,
        [AndroidDevice, *ANDROID_STREAMS.values()],
    )
    metadata_by_device = await _device_metadata_by_device(db, AndroidDevice)
    study_states = await _android_study_states(db)

    devices = []
    # A phone that joined but has not uploaded yet exists only in aware_studies,
    # and still belongs in the list.
    for device_id in set(last_seen_by_device) | set(study_states):
        metadata = metadata_by_device.get(device_id, {})
        state = study_states.get(device_id)
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
                "last_seen": last_seen_by_device.get(device_id),
                "platform": "android",
                "study": _study_list_summary(state) if state else None,
            }
        )

    return sorted(devices, key=_last_seen_sort_key, reverse=True)


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

    return sorted(devices, key=_last_seen_sort_key, reverse=True)


@router.get("")
async def list_all_devices(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    try:
        android = await list_android_devices(android_db)
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        android = []
    try:
        ios = await list_ios_devices(ios_db)
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        ios = []
    return {"android": android, "ios": ios}


@router.get("/android/{device_id}/study-events", response_model=list[AndroidStudyEventSchema])
async def list_android_study_events(
    device_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_android_db),
):
    states = await _android_study_states(db, device_id)
    state = states.get(device_id)
    if state is None:
        return []
    return state.events[offset : offset + limit]


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
