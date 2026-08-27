from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os
import ssl

load_dotenv()

ANDROID_DB_URL = os.getenv("ANDROID_DATABASE_URL")
IOS_DB_URL = os.getenv("IOS_DATABASE_URL")

#: Echoes every statement SQLAlchemy runs to the log. Set SQL_ECHO=1 to read the
#: queries a request or a refresh actually makes.
SQL_ECHO = os.getenv("SQL_ECHO", "").strip().lower() in {"1", "true", "yes", "on"}

#: The connection to the study database is encrypted, always.
#:
#: Not a preference, and not something the study model decides any more. Without it
#: MySQL 8 still protects the password --- `caching_sha2_password` refuses to send one
#: in clear --- and then carries every row of every participant's data over the same
#: socket unencrypted. The password was never the part worth protecting most.
#:
#: The certificate is not verified here. A bundled MySQL generates its own, which
#: carries no subject alternative name and therefore cannot pass an identity check;
#: an external one may present a real certificate, and verifying it needs its
#: authority, which nothing in this deployment has a place to put yet. So this
#: closes eavesdropping and leaves impersonation open, which is the honest half and
#: is stated as such wherever a researcher reads about it.
def _encrypted(url: str) -> dict:
    """Connect arguments that encrypt the session, for a driver that takes a context."""
    if not url or "aiomysql" not in url:
        return {}
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return {"ssl": context}


android_engine = create_async_engine(
    ANDROID_DB_URL,
    echo=SQL_ECHO,
    pool_recycle=3600,
    connect_args=_encrypted(ANDROID_DB_URL),
)
ios_engine = create_async_engine(
    IOS_DB_URL,
    echo=SQL_ECHO,
    pool_recycle=3600,
    connect_args=_encrypted(IOS_DB_URL),
)

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
