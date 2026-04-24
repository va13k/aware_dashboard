from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os

load_dotenv()

ANDROID_DB_URL = os.getenv("ANDROID_DATABASE_URL")
IOS_DB_URL = os.getenv("IOS_DATABASE_URL")

android_engine = create_async_engine(ANDROID_DB_URL, echo=True)
ios_engine = create_async_engine(IOS_DB_URL, echo=True)

AndroidSessionLocal = sessionmaker(android_engine, class_=AsyncSession, expire_on_commit=False)
IosSessionLocal = sessionmaker(ios_engine, class_=AsyncSession, expire_on_commit=False)

class AndroidBase(DeclarativeBase):
    pass

class IosBase(DeclarativeBase):
    pass

async def get_android_db():
    async with AndroidSessionLocal() as session:
        yield session

async def get_ios_db():
    async with IosSessionLocal() as session:
        yield session