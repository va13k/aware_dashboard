import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.exc import ProgrammingError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_android_db, get_ios_db
from app.services import record_counts
from app.routers.android import _EXPORT_MODELS as _ANDROID_EXPORT_MODELS
from app.models import (
    AndroidCoverageHourly,
    AndroidRecordCount,
    IosCoverageHourly,
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
from app.services import config_diff, enrolment, study_state

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
            )
            # The cache keeps an internal row under an empty `device_id` to carry
            # a sensor's watermark past an orphan-only batch. It stands for no
            # phone, so it must not arrive here as one.
            .where(count_model.device_id != record_counts.ORPHAN_DEVICE)
            .group_by(count_model.device_id)
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

    The coverage grids read the same rows to decide whether an empty bucket means
    anything was expected, so the reader lives in services/enrolment.py and the
    two cannot come to disagree about who was in the study when.
    """
    return await enrolment.stored_windows(db, AndroidDeviceEnrolment, device_id)


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


def _has_recorded_enrolment(windows: list | None) -> bool:
    """Whether something other than sensor data says this phone joined.

    The registry deliberately gives a data-only phone a `first_data` window so
    the coverage grid has a left edge. The existence of that inferred window is
    therefore not evidence of enrolment; its source is the distinction the badge
    needs to preserve.
    """
    return any(
        window.get("join_source") in {enrolment.STUDY_EVENT, enrolment.MANUAL}
        for window in windows or []
    )


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
    first_seen_by_device = await enrolment.first_record_by_device(
        db, AndroidCoverageHourly
    )

    devices = []
    # A phone that joined but has not uploaded yet exists only in aware_studies,
    # and still belongs in the list.
    for device_id in set(last_seen_by_device) | set(study_states) | set(enrolment_by_device):
        metadata = metadata_by_device.get(device_id, {})
        state = study_states.get(device_id)
        windows = enrolment_by_device.get(device_id)
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
                # When this device's first record arrived, to the hour. A phone
                # that appeared this week reads differently from one reporting
                # since the study opened, and that is the first thing worth
                # knowing about a device nobody recognises.
                "first_seen": first_seen_by_device.get(device_id),
                "last_seen": last_seen_by_device.get(device_id),
                "platform": "android",
                "study": _study_list_summary(state) if state else None,
                # A first-data window still appears here because coverage needs
                # its left edge; `recognised` below says whether a join was ever
                # actually recorded.
                "enrolment": _enrolment_summary(windows),
                # Whether the study has a record of this device joining. False is
                # the finding: data arrived from a phone that left no trace of
                # enrolling, which is what the device gate exists to surface.
                "recognised": _has_recorded_enrolment(windows),
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
    first_seen_by_device = await enrolment.first_record_by_device(db, IosCoverageHourly)

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
                "first_seen": first_seen_by_device.get(device_id),
                "last_seen": last_seen,
                "platform": "ios",
                # An iPhone keeps its study state in `NSUserDefaults` and never
                # uploads it, so the server holds nothing to recognise it by.
                # Unknown rather than false: an iPhone is not a suspect for
                # lacking a record it was never able to send.
                "recognised": None,
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


def _utc_text(milliseconds: int) -> str:
    """An instant a researcher can compare against, in UTC."""
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).strftime(
        "%d %b %Y %H:%M UTC"
    )


class WithdrawalRequest(BaseModel):
    """When the participant left."""

    #: The moment the participant acted, in epoch milliseconds. Absent means now,
    #: which is right when a researcher is told during the conversation and wrong
    #: whenever they are told later — so a caller who knows the date sends it.
    left_at: int | None = None


@router.post("/android/{device_id}/withdraw")
async def withdraw_device(
    device_id: str,
    body: WithdrawalRequest | None = None,
    db: AsyncSession = Depends(get_android_db),
):
    """Record that a participant has left, closing their enrolment window.

    The reliable path, because a researcher usually finds out by being told rather
    than by watching a phone go quiet. It takes effect on everything that reads the
    windows at once: the coverage grid stops expecting data from the moment they
    left, and the device reads as withdrawn rather than as merely gone silent.

    Closing the window is not deletion. What happens to the data already collected
    is a separate and deliberate action, because consent forms answer that question
    differently.

    Android only: an iPhone keeps its study state on the phone and the server holds
    no window to close.
    """
    request = body or WithdrawalRequest()
    left_at = int(request.left_at if request.left_at is not None else time.time() * 1000)

    stored = await enrolment.close_window(
        db, AndroidDeviceEnrolment, device_id, left_at
    )
    if stored is None:
        # Two different refusals, and saying which one it is matters: a date
        # before the device joined is a typo to correct, while no enrolment at all
        # is a finding about the device.
        # Through the router's own reader, which is what every other path here
        # uses to reach the windows.
        windows = (await _enrolment_windows(db, device_id)).get(device_id) or []
        if windows:
            earliest = min(window["joined_at"] for window in windows)
            raise HTTPException(
                status_code=422,
                detail=(
                    "That moment falls outside this device's enrolment: it joined "
                    f"at {_utc_text(earliest)}. Pick a time after it joined."
                ),
            )
        raise HTTPException(
            status_code=404,
            detail=(
                "The study has no record of this device joining, so there is no "
                "enrolment window to close."
            ),
        )

    return {"status": "withdrawn", "window": stored}


@router.post("/android/{device_id}/rejoin")
async def reopen_device_enrolment(
    device_id: str,
    db: AsyncSession = Depends(get_android_db),
):
    """Undo a withdrawal recorded by mistake.

    Clears this device's stored windows, then immediately derives them from the
    study log again, which is the phone's own account of when it joined and left.
    """
    if not await enrolment.reopen(db, AndroidDeviceEnrolment, device_id):
        raise HTTPException(status_code=500, detail="Could not clear the windows")
    await enrolment.refresh(
        db,
        AndroidDeviceEnrolment,
        AndroidCoverageHourly,
        AndroidAwareStudy,
    )
    return {"status": "reopened", "device_id": device_id}
