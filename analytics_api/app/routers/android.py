import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AndroidSessionLocal, get_android_db
from app.services import backup_jobs as jobs
from app.services.series import (
    DEFAULT_BUCKETS,
    MAX_BUCKETS,
    bucketed_series,
    clamp_window,
)
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
)
from app.schemas import (
    AndroidAccelerometerSchema,
    AndroidApplicationsCrashesSchema,
    AndroidApplicationsForegroundSchema,
    AndroidApplicationsHistorySchema,
    AndroidApplicationsNotificationsSchema,
    AndroidBarometerSchema,
    AndroidBatterySchema,
    AndroidBatteryChargesSchema,
    AndroidBatteryDischargesSchema,
    AndroidBluetoothSchema,
    AndroidCallsSchema,
    AndroidEsmsSchema,
    AndroidGravitySchema,
    AndroidGyroscopeSchema,
    AndroidInstallationsSchema,
    AndroidKeyboardSchema,
    AndroidLightSchema,
    AndroidLinearAccelerometerSchema,
    AndroidLocationsSchema,
    AndroidMagnetometerSchema,
    AndroidMessagesSchema,
    AndroidNetworkSchema,
    AndroidNetworkTrafficSchema,
    AndroidNotesSchema,
    AndroidPluginAmbientNoiseSchema,
    AndroidPluginOpenweatherSchema,
    AndroidProximitySchema,
    AndroidRotationSchema,
    AndroidScreenSchema,
    AndroidScreentextSchema,
    AndroidSignificantSchema,
    AndroidTelephonySchema,
    AndroidTemperatureSchema,
    AndroidTimezoneSchema,
    AndroidTouchSchema,
    AndroidWifiSchema,
    SeriesBucketSchema,
)

router = APIRouter(prefix="/android/{device_id}", tags=["android"])

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


@router.get("/accelerometer", response_model=list[AndroidAccelerometerSchema])
async def get_accelerometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidAccelerometer, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/applications", response_model=list[AndroidApplicationsForegroundSchema])
async def get_applications(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidApplicationsForeground, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/applications-crashes", response_model=list[AndroidApplicationsCrashesSchema])
async def get_applications_crashes(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidApplicationsCrashes, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/applications-history", response_model=list[AndroidApplicationsHistorySchema])
async def get_applications_history(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidApplicationsHistory, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get(
    "/applications-notifications", response_model=list[AndroidApplicationsNotificationsSchema]
)
async def get_applications_notifications(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidApplicationsNotifications, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/barometer", response_model=list[AndroidBarometerSchema])
async def get_barometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidBarometer, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/battery", response_model=list[AndroidBatterySchema])
async def get_battery(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidBattery, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/battery-charges", response_model=list[AndroidBatteryChargesSchema])
async def get_battery_charges(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidBatteryCharges, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/battery-discharges", response_model=list[AndroidBatteryDischargesSchema])
async def get_battery_discharges(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidBatteryDischarges, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/bluetooth", response_model=list[AndroidBluetoothSchema])
async def get_bluetooth(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidBluetooth, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/calls", response_model=list[AndroidCallsSchema])
async def get_calls(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidCalls, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/esms", response_model=list[AndroidEsmsSchema])
async def get_esms(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidEsms, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/gravity", response_model=list[AndroidGravitySchema])
async def get_gravity(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidGravity, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/gyroscope", response_model=list[AndroidGyroscopeSchema])
async def get_gyroscope(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidGyroscope, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/installations", response_model=list[AndroidInstallationsSchema])
async def get_installations(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidInstallations, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/keyboard", response_model=list[AndroidKeyboardSchema])
async def get_keyboard(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidKeyboard, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/light", response_model=list[AndroidLightSchema])
async def get_light(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidLight, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/linear-accelerometer", response_model=list[AndroidLinearAccelerometerSchema])
async def get_linear_accelerometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidLinearAccelerometer, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/locations", response_model=list[AndroidLocationsSchema])
async def get_locations(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidLocations, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/magnetometer", response_model=list[AndroidMagnetometerSchema])
async def get_magnetometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidMagnetometer, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/messages", response_model=list[AndroidMessagesSchema])
async def get_messages(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidMessages, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/network", response_model=list[AndroidNetworkSchema])
async def get_network(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidNetwork, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/network-traffic", response_model=list[AndroidNetworkTrafficSchema])
async def get_network_traffic(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidNetworkTraffic, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/notes", response_model=list[AndroidNotesSchema])
async def get_notes(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidNotes, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/plugin-ambient-noise", response_model=list[AndroidPluginAmbientNoiseSchema])
async def get_plugin_ambient_noise(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidPluginAmbientNoise, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/plugin-openweather", response_model=list[AndroidPluginOpenweatherSchema])
async def get_plugin_openweather(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidPluginOpenweather, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/proximity", response_model=list[AndroidProximitySchema])
async def get_proximity(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidProximity, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/rotation", response_model=list[AndroidRotationSchema])
async def get_rotation(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidRotation, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/screen", response_model=list[AndroidScreenSchema])
async def get_screen(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidScreen, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/screentext", response_model=list[AndroidScreentextSchema])
async def get_screentext(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidScreentext, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/significant-motion", response_model=list[AndroidSignificantSchema])
async def get_significant_motion(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidSignificant, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/telephony", response_model=list[AndroidTelephonySchema])
async def get_telephony(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidTelephony, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/temperature", response_model=list[AndroidTemperatureSchema])
async def get_temperature(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidTemperature, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/timezone", response_model=list[AndroidTimezoneSchema])
async def get_timezone(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(
        _base_query(AndroidTimezone, device_id, from_ts, to_ts, limit, offset)
    )
    return result.scalars().all()


@router.get("/touch", response_model=list[AndroidTouchSchema])
async def get_touch(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidTouch, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


@router.get("/wifi", response_model=list[AndroidWifiSchema])
async def get_wifi(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=MAX_RECORD_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidWifi, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Bucketed series — consistent point density for any window
# ---------------------------------------------------------------------------


def _magnitude(*columns):
    """√(x²+y²+z²) over a vector sensor's component columns."""
    return func.sqrt(sum(column * column for column in columns))


# sensor key -> (model, value expression). Keyed by the same hyphenated keys the
# dashboard uses. Only numeric *continuous* sensors belong here; event sensors
# (calls, screen, timezone, …) and enum sensors (significant-motion) keep the
# raw-record view. Vector sensors aggregate their magnitude.
_SERIES_TARGETS: dict[str, tuple] = {
    "accelerometer": (
        AndroidAccelerometer,
        _magnitude(
            AndroidAccelerometer.double_values_0,
            AndroidAccelerometer.double_values_1,
            AndroidAccelerometer.double_values_2,
        ),
    ),
    "gyroscope": (
        AndroidGyroscope,
        _magnitude(
            AndroidGyroscope.double_values_0,
            AndroidGyroscope.double_values_1,
            AndroidGyroscope.double_values_2,
        ),
    ),
    "linear-accelerometer": (
        AndroidLinearAccelerometer,
        _magnitude(
            AndroidLinearAccelerometer.double_values_0,
            AndroidLinearAccelerometer.double_values_1,
            AndroidLinearAccelerometer.double_values_2,
        ),
    ),
    "magnetometer": (
        AndroidMagnetometer,
        _magnitude(
            AndroidMagnetometer.double_values_0,
            AndroidMagnetometer.double_values_1,
            AndroidMagnetometer.double_values_2,
        ),
    ),
    "gravity": (
        AndroidGravity,
        _magnitude(
            AndroidGravity.double_values_0,
            AndroidGravity.double_values_1,
            AndroidGravity.double_values_2,
        ),
    ),
    "rotation": (
        AndroidRotation,
        _magnitude(
            AndroidRotation.double_values_0,
            AndroidRotation.double_values_1,
            AndroidRotation.double_values_2,
        ),
    ),
    "barometer": (AndroidBarometer, AndroidBarometer.double_values_0),
    "light": (AndroidLight, AndroidLight.double_light_lux),
    "temperature": (AndroidTemperature, AndroidTemperature.temperature_celsius),
    "plugin-ambient-noise": (
        AndroidPluginAmbientNoise,
        AndroidPluginAmbientNoise.double_decibels,
    ),
    "network-traffic": (
        AndroidNetworkTraffic,
        AndroidNetworkTraffic.double_sent_bytes,
    ),
}


@router.get("/{sensor}/series", response_model=list[SeriesBucketSchema])
async def get_series(
    sensor: str,
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    buckets: int = Query(DEFAULT_BUCKETS, ge=1, le=MAX_BUCKETS),
    db: AsyncSession = Depends(get_android_db),
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

_EXPORT_MODELS: dict[str, tuple] = {
    "accelerometer": (AndroidAccelerometer, AndroidAccelerometerSchema),
    "applications": (AndroidApplicationsForeground, AndroidApplicationsForegroundSchema),
    "applications-crashes": (AndroidApplicationsCrashes, AndroidApplicationsCrashesSchema),
    "applications-history": (AndroidApplicationsHistory, AndroidApplicationsHistorySchema),
    "applications-notifications": (
        AndroidApplicationsNotifications,
        AndroidApplicationsNotificationsSchema,
    ),
    "barometer": (AndroidBarometer, AndroidBarometerSchema),
    "battery": (AndroidBattery, AndroidBatterySchema),
    "battery-charges": (AndroidBatteryCharges, AndroidBatteryChargesSchema),
    "battery-discharges": (AndroidBatteryDischarges, AndroidBatteryDischargesSchema),
    "bluetooth": (AndroidBluetooth, AndroidBluetoothSchema),
    "calls": (AndroidCalls, AndroidCallsSchema),
    "esms": (AndroidEsms, AndroidEsmsSchema),
    "gravity": (AndroidGravity, AndroidGravitySchema),
    "gyroscope": (AndroidGyroscope, AndroidGyroscopeSchema),
    "installations": (AndroidInstallations, AndroidInstallationsSchema),
    "keyboard": (AndroidKeyboard, AndroidKeyboardSchema),
    "light": (AndroidLight, AndroidLightSchema),
    "linear-accelerometer": (AndroidLinearAccelerometer, AndroidLinearAccelerometerSchema),
    "locations": (AndroidLocations, AndroidLocationsSchema),
    "magnetometer": (AndroidMagnetometer, AndroidMagnetometerSchema),
    "messages": (AndroidMessages, AndroidMessagesSchema),
    "network": (AndroidNetwork, AndroidNetworkSchema),
    "network-traffic": (AndroidNetworkTraffic, AndroidNetworkTrafficSchema),
    "notes": (AndroidNotes, AndroidNotesSchema),
    "plugin-ambient-noise": (AndroidPluginAmbientNoise, AndroidPluginAmbientNoiseSchema),
    "plugin-openweather": (AndroidPluginOpenweather, AndroidPluginOpenweatherSchema),
    "proximity": (AndroidProximity, AndroidProximitySchema),
    "rotation": (AndroidRotation, AndroidRotationSchema),
    "screen": (AndroidScreen, AndroidScreenSchema),
    "screentext": (AndroidScreentext, AndroidScreentextSchema),
    "significant-motion": (AndroidSignificant, AndroidSignificantSchema),
    "telephony": (AndroidTelephony, AndroidTelephonySchema),
    "temperature": (AndroidTemperature, AndroidTemperatureSchema),
    "timezone": (AndroidTimezone, AndroidTimezoneSchema),
    "touch": (AndroidTouch, AndroidTouchSchema),
    "wifi": (AndroidWifi, AndroidWifiSchema),
}


# Rows fetched per round trip while streaming an export. Large enough that the
# query count stays small on a multi-million-row sensor, small enough that a
# batch and its rendered CSV are a bounded amount of memory.
EXPORT_BATCH = 5_000


def _export_window(sensor: str, from_ts: float | None, to_ts: float | None):
    entry = _EXPORT_MODELS.get(sensor)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown sensor: {sensor}")
    # Always bound the scan: an open export would range-scan the whole table
    # for a high-rate sensor. The full selected period is still exported; only a
    # literal "all time" request is capped (to the most recent year).
    return (*entry, *clamp_window(from_ts, to_ts))


def _export_fields(schema) -> list[str]:
    """CSV columns, in the order the schema declares them.

    Taken from the schema rather than from the first row, so the header can be
    written before any row has been read. ``device_id`` is left out because the
    file is already per-device.
    """
    return [name for name in schema.model_fields if name != "device_id"]


def _export_row(row, schema) -> dict:
    record = schema.model_validate(row).model_dump()
    stamp = record["timestamp"]
    record["timestamp"] = datetime.fromtimestamp(
        stamp / 1000 if stamp >= 1e11 else stamp, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")
    del record["device_id"]
    return record


async def _stream_export(device_id, sensor, model, schema, from_ts, to_ts, job):
    """Yield the CSV a batch at a time, never holding the whole result.

    Rows are walked in ``_id`` order and paged by the last id seen, so each round
    trip is an indexed seek rather than a growing OFFSET, and the file comes out
    in the same order as before. The session is opened here rather than injected:
    a streaming response outlives the request that returned it, and a
    dependency-scoped session would already be closed by the first batch.
    """
    fields = _export_fields(schema)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    yield buffer.getvalue()

    last_id = 0
    try:
        async with AndroidSessionLocal() as db:
            while True:
                result = await db.execute(
                    select(model)
                    .where(model.device_id == device_id)
                    .where(model.timestamp >= from_ts)
                    .where(model.timestamp <= to_ts)
                    .where(model._id > last_id)
                    .order_by(model._id.asc())
                    .limit(EXPORT_BATCH)
                )
                rows = result.scalars().all()
                if not rows:
                    break

                buffer = io.StringIO()
                writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
                writer.writerows(_export_row(row, schema) for row in rows)
                yield buffer.getvalue()

                last_id = rows[-1]._id
                if job is not None:
                    jobs.advance(job, add=len(rows), phase=f"Exporting {sensor}")
        if job is not None:
            jobs.finish(job, {"sensor": sensor})
    except Exception as error:  # noqa: BLE001 - the response has already begun
        if job is not None:
            jobs.fail(job, str(error))
        raise
    finally:
        # A cancelled download closes this generator, which arrives as
        # GeneratorExit — a BaseException, so it misses the handler above. Left
        # unresolved the job would read as running until it aged out.
        if job is not None:
            jobs.cancel(job)


def _progress_job(job_id: str | None, sensor: str):
    """The job this download may report into, or nothing.

    The id arrives in the query string, so it is whatever the caller put there.
    An id belonging to something else — a backup import, say — must never be
    advanced or finished by a CSV download: the page watching that job would be
    told an import had completed while it was still running. A mismatch simply
    yields no reporting; the download itself is unaffected either way.
    """
    if not job_id:
        return None
    job = jobs.get(job_id)
    if job is None or job.kind != "export-csv":
        return None
    if job.result.get("sensor") != sensor:
        return None
    return job


async def _export_total(db, model, device_id, from_ts, to_ts) -> int:
    """Rows the export will produce, counted from the index alone."""
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(model)
                .where(model.device_id == device_id)
                .where(model.timestamp >= from_ts)
                .where(model.timestamp <= to_ts)
            )
        ).scalar()
        or 0
    )


@router.post("/export")
async def start_export_csv(
    device_id: str,
    sensor: str = Query(..., description="Sensor slug, e.g. 'accelerometer'"),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    db: AsyncSession = Depends(get_android_db),
):
    """Register an export so the page can show progress while it downloads.

    The row count is settled here rather than mid-stream, so the bar has a real
    denominator from the first chunk. The GET below streams with or without a
    job; this only attaches the reporting.
    """
    model, schema, from_ts, to_ts = _export_window(sensor, from_ts, to_ts)
    total = await _export_total(db, model, device_id, from_ts, to_ts)
    if not total:
        raise HTTPException(status_code=404, detail=f"No data found for sensor: {sensor}")

    job = jobs.create("export-csv")
    filename = f"{device_id}_{sensor}.csv"
    jobs.advance(job, total=total, phase=f"Exporting {sensor}")
    jobs.describe(job, filename=filename, sensor=sensor, unit="rows")
    return {"id": job.id, "filename": filename, "rows": total}


@router.get("/export")
async def export_csv(
    device_id: str,
    sensor: str = Query(..., description="Sensor slug, e.g. 'accelerometer'"),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    job: str | None = Query(None, description="Job id from POST, to report progress"),
    db: AsyncSession = Depends(get_android_db),
):
    model, schema, from_ts, to_ts = _export_window(sensor, from_ts, to_ts)

    # Settle emptiness before the response starts: once a streaming body is
    # under way its status can no longer become a 404.
    exists = (
        await db.execute(
            select(model._id)
            .where(model.device_id == device_id)
            .where(model.timestamp >= from_ts)
            .where(model.timestamp <= to_ts)
            .limit(1)
        )
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"No data found for sensor: {sensor}")

    filename = f"{device_id}_{sensor}.csv"
    return StreamingResponse(
        _stream_export(
            device_id, sensor, model, schema, from_ts, to_ts, _progress_job(job, sensor)
        ),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Produced as it is sent, so no intermediary should collect it first.
            "X-Accel-Buffering": "no",
        },
    )
