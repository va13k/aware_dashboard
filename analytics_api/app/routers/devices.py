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
    AndroidDeviceEnrolment,
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
# from the record-count cache (see services/record_counts.py), so summarising
# them all is cheap. Derived from the export map — the canonical android registry —
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


async def _cached_last_seen_by_device(db: AsyncSession, count_model):
    """The newest timestamp per device, from the record-count cache.

    The cache carries `last_ts` per sensor and device, so the answer is one
    grouped read of a small table. Scanning the sensor tables for it means a
    `MAX(timestamp)` over every one of them, which costs seconds per request at
    study scale. The figure trails the refresh interval, which a "last seen"
    reading can afford.
    """
    try:
        result = await db.execute(
            select(
                count_model.device_id,
                func.max(count_model.last_ts).label("last_seen"),
            ).group_by(count_model.device_id)
        )
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback_after_table_error(db)
        return {}

    return {
        str(row.device_id): row.last_seen
        for row in result.all()
        if row.device_id is not None and row.last_seen
    }


async def _combined_last_seen_by_device(db: AsyncSession, models, count_model=None):
    """Newest upload per device: from the cache, falling back to the tables.

    A cache that has never been refreshed answers for no device, so the scan
    remains for a deployment whose first refresh has not run.
    """
    if count_model is not None:
        cached = await _cached_last_seen_by_device(db, count_model)
        if cached:
            return cached

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


async def _enrolment_windows(db: AsyncSession, device_id: str | None = None):
    """The stored enrolment windows per device, oldest first.

    Read from the table rather than re-derived from the study log: the log needs
    parsing and deduplicating per device, and this is on the path of every device
    list. The refresher keeps the table in step (services/enrolment.py).
    """
    query = select(AndroidDeviceEnrolment).order_by(
        AndroidDeviceEnrolment.device_id, AndroidDeviceEnrolment.joined_at
    )
    if device_id is not None:
        query = query.where(AndroidDeviceEnrolment.device_id == device_id)

    try:
        result = await db.execute(query)
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback_after_table_error(db)
        return {}

    windows: dict[str, list] = {}
    for row in result.scalars().all():
        windows.setdefault(str(row.device_id), []).append(
            {
                "joined_at": int(row.joined_at),
                "left_at": int(row.left_at) if row.left_at is not None else None,
                "join_source": row.join_source,
                "left_source": row.left_source,
            }
        )
    return windows


def _enrolment_summary(windows: list | None) -> dict | None:
    """What a device row shows about enrolment: the span, and how it is known.

    `joined_at` is the first window's start and `left_at` the last one's end, so
    a device that quit and came back reads as enrolled since it first joined and
    still in the study. The windows themselves carry the gap, and the heatmap
    reads those rather than this.

    A device with no window at all returns None. That is the state worth seeing:
    it wrote data without the study ever recording that it joined.
    """
    if not windows:
        return None
    return {
        "joined_at": windows[0]["joined_at"],
        "left_at": windows[-1]["left_at"],
        "join_source": windows[0]["join_source"],
        "window_count": len(windows),
    }


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


async def _latest_payload_by_id(db: AsyncSession, model, last_id: int):
    """The newest row for a stream, fetched by primary key — an O(1) point
    lookup instead of an `ORDER BY timestamp` scan."""
    try:
        result = await db.execute(select(model).where(model._id == last_id).limit(1))
        return _row_to_dict(result.scalars().first())
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback_after_table_error(db)
        return None


async def _device_detail(platform: str, device_id: str, db: AsyncSession):
    device_model = AndroidDevice if platform == "android" else IosDevice
    streams = ANDROID_STREAMS if platform == "android" else IOS_STREAMS
    device = await _best_device_row(db, device_model, device_id)
    device_dict = _flatten_device_row(device)
    stream_details = []

    # One lookup gives every cached (count, last_seen, last_id) for this device.
    # A sensor absent from the cache has no rows for this device — the refresh
    # records every sensor/device that does — so a miss is zero with *no* query.
    # That keeps the page O(1) no matter how many sensors a device lacks (a live
    # "latest row" probe on a table the device never wrote would scan the whole
    # timestamp index). A cold cache simply reads zero until the refresh runs.
    count_model = AndroidRecordCount if platform == "android" else IosRecordCount
    cached = await record_counts.counts_for_device(db, count_model, device_id)

    for key in streams:
        entry = cached.get(key)
        stream_details.append(
            {
                "key": key,
                "count": entry["count"] if entry else 0,
                "last_seen": (entry["last_ts"] or None) if entry else None,
                "latest": None,
            }
        )

    # The "latest payload" panel shows one stream, so fetch only the most-recent
    # cached stream's newest row (by primary key) rather than one per sensor.
    newest = max(
        (
            (key, entry)
            for key, entry in cached.items()
            if entry["last_id"] and entry["last_ts"] and key in streams
        ),
        key=lambda item: item[1]["last_ts"],
        default=None,
    )
    if newest is not None:
        key, entry = newest
        latest = await _latest_payload_by_id(db, streams[key], entry["last_id"])
        if latest is not None:
            for summary in stream_details:
                if summary["key"] == key:
                    summary["latest"] = latest
                    break

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

        windows = (await _enrolment_windows(db, device_id)).get(device_id, [])
        detail["enrolment"] = _enrolment_summary(windows)
        # The windows themselves, because the gap between two of them is time
        # this device was expected to send nothing.
        detail["enrolment_windows"] = windows

    return detail


@router.get("/android")
async def list_android_devices(db: AsyncSession = Depends(get_android_db)):
    last_seen_by_device = await _combined_last_seen_by_device(
        db,
        [AndroidDevice, *ANDROID_STREAMS.values()],
        AndroidRecordCount,
    )
    metadata_by_device = await _device_metadata_by_device(db, AndroidDevice)
    study_states = await _android_study_states(db)
    enrolment_by_device = await _enrolment_windows(db)

    devices = []
    # A phone that joined but has not uploaded yet exists only in aware_studies,
    # and still belongs in the list.
    for device_id in set(last_seen_by_device) | set(study_states) | set(enrolment_by_device):
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
                # None for a device that wrote data the study never recorded a
                # join for — the case worth being able to see.
                "enrolment": _enrolment_summary(enrolment_by_device.get(device_id)),
            }
        )

    return sorted(devices, key=_last_seen_sort_key, reverse=True)


@router.get("/ios")
async def list_ios_devices(db: AsyncSession = Depends(get_ios_db)):
    last_seen_by_device = await _combined_last_seen_by_device(
        db,
        [IosDevice, *IOS_STREAMS.values()],
        IosRecordCount,
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
