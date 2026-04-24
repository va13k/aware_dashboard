from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_android_db
from app.models import (
    AndroidAccelerometer,
    AndroidBattery,
    AndroidBluetooth,
    AndroidCalls,
    AndroidApplicationsForeground,
    AndroidGyroscope,
    AndroidLight,
    AndroidLocations,
    AndroidNetwork,
    AndroidScreen,
    AndroidWifi,
)
from app.schemas import (
    AndroidAccelerometerSchema,
    AndroidBatterySchema,
    AndroidBluetoothSchema,
    AndroidCallsSchema,
    AndroidApplicationsForegroundSchema,
    AndroidGyroscopeSchema,
    AndroidLightSchema,
    AndroidLocationsSchema,
    AndroidNetworkSchema,
    AndroidScreenSchema,
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
    result = await db.execute(_base_query(AndroidAccelerometer, device_id, from_ts, to_ts, limit, offset))
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
    result = await db.execute(_base_query(AndroidGyroscope, device_id, from_ts, to_ts, limit, offset))
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


@router.get("/locations", response_model=list[AndroidLocationsSchema])
async def get_locations(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidLocations, device_id, from_ts, to_ts, limit, offset))
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


@router.get("/bluetooth", response_model=list[AndroidBluetoothSchema])
async def get_bluetooth(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidBluetooth, device_id, from_ts, to_ts, limit, offset))
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


@router.get("/applications", response_model=list[AndroidApplicationsForegroundSchema])
async def get_applications(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    result = await db.execute(_base_query(AndroidApplicationsForeground, device_id, from_ts, to_ts, limit, offset))
    return result.scalars().all()
