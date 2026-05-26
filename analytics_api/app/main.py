import asyncio
import logging
from contextlib import asynccontextmanager
from sqlalchemy import text
from fastapi import FastAPI
from app.database import android_engine, ios_engine
from app.routers import health, devices, android, ios, auth, backup, export, overview


class _SuppressChromeProbe(logging.Filter):
    def filter(self, record):
        return "com.chrome.devtools" not in record.getMessage()


logging.basicConfig(level=logging.INFO)
logging.getLogger("uvicorn.access").addFilter(_SuppressChromeProbe())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    for name, engine in (("Android", android_engine), ("iOS", ios_engine)):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info(f"{name} DB connected successfully")
        except Exception as e:
            logger.error(f"{name} DB connection failed: {e}")
    task = asyncio.create_task(devices.background_refresh_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(devices.router)
app.include_router(android.router)
app.include_router(ios.router)
app.include_router(backup.router)
app.include_router(export.router)
app.include_router(overview.router)


@app.get("/")
async def root():
    return {"message": "AWARE Dashboard API"}
