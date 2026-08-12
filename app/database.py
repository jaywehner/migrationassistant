import os
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# Active database connection config. Set by get_engine() or init_db().
_current_database_url: str | None = None

def get_configured_database_url() -> str:
    settings = get_settings()
    return settings.database_url or os.environ.get("DATABASE_URL", "")


def get_engine():
    global _current_database_url
    url = get_configured_database_url()
    _current_database_url = url
    
    if not url:
        return None
        
    kwargs = {"echo": False}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_pre_ping"] = True
    return create_async_engine(url, **kwargs)


engine = None
AsyncSessionLocal = None


async def init_db(force_reinit: bool = False):
    global engine, AsyncSessionLocal
    if engine and not force_reinit:
        return
        
    engine = get_engine()
    if engine:
        AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialized")
        
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
