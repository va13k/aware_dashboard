from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_ios_db
from app.models import (
    IosAccelerometer,
    IosBattery,
    IosBluetooth,
    IosCalls,
    IosGyroscope,
    IosLocations,
    IosNetwork,
    IosScreen,
    IosWifi,
    IosHealthKit,
    IosHealthKitQuantity,
    IosPluginActivityRecognition,
    IosPedometer,
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


def _params(device_id: str, from_ts, to_ts, limit, offset, db):
    return device_id, from_ts, to_ts, limit, offset, db


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


@router.get("/accelerometer", response_model=list[IosSchema])
async def get_accelerometer(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosAccelerometer, device_id, from_ts, to_ts, limit, offset))
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


@router.get("/health-kit/quantity", response_model=list[IosSchema])
async def get_health_kit_quantity(
    device_id: str,
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    result = await db.execute(_base_query(IosHealthKitQuantity, device_id, from_ts, to_ts, limit, offset))
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
    result = await db.execute(_base_query(IosPluginActivityRecognition, device_id, from_ts, to_ts, limit, offset))
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
