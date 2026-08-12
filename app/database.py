import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings


class Base(DeclarativeBase):
    pass


# URL chosen at runtime. Defaults come from DATABASE_URL env var; if Postgres is
# unavailable we transparently fall back to SQLite.
_current_database_url: str | None = None


def get_configured_database_url() -> str:
    settings = get_settings()
    return settings.database_url or os.environ.get("DATABASE_URL", "")


async def resolve_database_url() -> str:
    """Return the configured DATABASE_URL, falling back to local SQLite if Postgres is unreachable."""
    global _current_database_url
    if _current_database_url is not None:
        return _current_database_url

    url = get_configured_database_url()
    if not url:
        url = "sqlite+aiosqlite:///./migration_platform.db"

    if url.startswith("postgresql"):
        test_engine = create_async_engine(url, echo=False)
        try:
            async with test_engine.connect() as conn:
                await conn.execute("SELECT 1")
            _current_database_url = url
            return url
        except Exception:
            # Postgres is unavailable: use a local SQLite fallback
            url = "sqlite+aiosqlite:///./migration_platform.db"
        finally:
            await test_engine.dispose()

    _current_database_url = url
    os.environ["DATABASE_URL"] = url
    return url


def get_engine():
    if _current_database_url is None:
        raise RuntimeError("Database URL has not been resolved. Call init_db() first.")
    kwargs = {"echo": False}
    if _current_database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_pre_ping"] = True
    return create_async_engine(_current_database_url, **kwargs)


engine = None
AsyncSessionLocal = None


async def init_db():
    global engine, AsyncSessionLocal
    await resolve_database_url()
    engine = get_engine()
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    if AsyncSessionLocal is None:
        await init_db()
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
