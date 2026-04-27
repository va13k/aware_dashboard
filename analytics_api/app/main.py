import os
import logging
from contextlib import asynccontextmanager
from sqlalchemy import text
from fastapi import FastAPI, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.database import android_engine, ios_engine
from app.routers import health, devices, android, ios, auth

class _SuppressChromeProbe(logging.Filter):
    def filter(self, record):
        return "com.chrome.devtools" not in record.getMessage()

logging.basicConfig(level=logging.INFO)
logging.getLogger("uvicorn.access").addFilter(_SuppressChromeProbe())
logger = logging.getLogger(__name__)

_API_KEY = os.environ.get("ANALYTICS_API_KEY", "")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def _verify_api_key(key: str = Security(_api_key_header)):
    if _API_KEY and key != _API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or missing API key")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not _API_KEY:
        logger.warning("ANALYTICS_API_KEY is not set — API is unprotected")
    for name, engine in (("Android", android_engine), ("iOS", ios_engine)):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info(f"{name} DB connected successfully")
        except Exception as e:
            logger.error(f"{name} DB connection failed: {e}")
    yield

app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(devices.router,  dependencies=[Security(_verify_api_key)])
app.include_router(android.router,  dependencies=[Security(_verify_api_key)])
app.include_router(ios.router,      dependencies=[Security(_verify_api_key)])

@app.get("/")
async def root():
    return {"message": "AWARE Dashboard API"}
