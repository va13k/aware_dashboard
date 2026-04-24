from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.database import get_android_db, get_ios_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    results = {}

    try:
        await android_db.execute(text("SELECT 1"))
        results["android"] = "ok"
    except Exception as e:
        results["android"] = str(e)

    try:
        await ios_db.execute(text("SELECT 1"))
        results["ios"] = "ok"
    except Exception as e:
        results["ios"] = str(e)

    status = "ok" if all(v == "ok" for v in results.values()) else "degraded"
    return {"status": status, "databases": results}
