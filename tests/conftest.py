import os
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from cryptography.fernet import Fernet

# Set test environment before importing app
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-1234567890"
os.environ["FIELD_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["SMTP_HOST"] = "localhost"
os.environ["SMTP_PORT"] = "1025"
os.environ["UPLOAD_DIR"] = "./test_uploads"

from app.database import Base, get_db
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def engine():
    """Create a test database engine using SQLite for speed."""
    test_engine = create_async_engine("sqlite+aiosqlite:///./test.db", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    if os.path.exists("./test.db"):
        os.remove("./test.db")


@pytest_asyncio.fixture
async def db_session(engine):
    """Create a test database session."""
    TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine):
    """Create a test HTTP client."""
    TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with TestSession() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create a verified test user."""
    from app.services.auth_service import create_user
    user = await create_user(db_session, "test@example.com", "TestPassword123", "Test User")
    user.email_verified = True
    await db_session.commit()
    return user
