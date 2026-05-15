import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_android_db
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
)

router = APIRouter(prefix="/android/{device_id}", tags=["android"])


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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidWifi, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()


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


@router.get("/export")
async def export_csv(
    device_id: str,
    sensor: str = Query(..., description="Sensor slug, e.g. 'accelerometer'"),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    db: AsyncSession = Depends(get_android_db),
):
    entry = _EXPORT_MODELS.get(sensor)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown sensor: {sensor}")
    model, schema = entry

    q = select(model).where(model.device_id == device_id)
    if from_ts is not None:
        q = q.where(model.timestamp >= from_ts)
    if to_ts is not None:
        q = q.where(model.timestamp <= to_ts)
    q = q.order_by(model.timestamp.asc())

    result = await db.execute(q)
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for sensor: {sensor}",
        )

    buf = io.StringIO()
    records = [schema.model_validate(r).model_dump() for r in rows]
    for r in records:
        ts = r["timestamp"]
        r["timestamp"] = datetime.fromtimestamp(
            ts / 1000 if ts >= 1e11 else ts, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
        del r["device_id"]
    records.sort(key=lambda r: r["id"])
    writer = csv.DictWriter(buf, fieldnames=records[0].keys())
    writer.writeheader()
    writer.writerows(records)

    filename = f"{device_id}_{sensor}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
