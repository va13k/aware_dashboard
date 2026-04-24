from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_android_db, get_ios_db
from app.models import AndroidDevice, IosDevice

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/android")
async def list_android_devices(db: AsyncSession = Depends(get_android_db)):
    result = await db.execute(
        select(
            AndroidDevice.device_id,
            AndroidDevice.manufacturer,
            AndroidDevice.model,
            func.max(AndroidDevice.timestamp).label("last_seen"),
        ).group_by(AndroidDevice.device_id, AndroidDevice.manufacturer, AndroidDevice.model)
        .order_by(func.max(AndroidDevice.timestamp).desc())
    )
    rows = result.all()
    return [
        {
            "device_id": r.device_id,
            "manufacturer": r.manufacturer,
            "model": r.model,
            "last_seen": r.last_seen,
            "platform": "android",
        }
        for r in rows
    ]


@router.get("/ios")
async def list_ios_devices(db: AsyncSession = Depends(get_ios_db)):
    result = await db.execute(
        select(
            IosDevice.device_id,
            func.max(IosDevice.timestamp).label("last_seen"),
        ).group_by(IosDevice.device_id)
        .order_by(func.max(IosDevice.timestamp).desc())
    )
    rows = result.all()
    return [
        {
            "device_id": r.device_id,
            "last_seen": r.last_seen,
            "platform": "ios",
        }
        for r in rows
    ]


@router.get("")
async def list_all_devices(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    android = await list_android_devices(android_db)
    ios = await list_ios_devices(ios_db)
    return {"android": android, "ios": ios}
