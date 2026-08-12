from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager
import os

from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import init_db, engine, _current_database_url, Base
    await init_db()

    # For SQLite fallback, create tables automatically. For PostgreSQL, rely on Alembic.
    if _current_database_url and _current_database_url.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    settings = get_settings()
    os.makedirs(settings.upload_dir, exist_ok=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Migration Collaboration Platform",
        description="Multi-user migration planning and task tracking",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Session middleware
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="session",
        max_age=settings.session_expire_hours * 3600,
        same_site="strict",
        https_only=False,  # Set True in production with TLS
    )

    # Static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    application.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Register routers
    from app.routers import auth, plans, tabs, tasks, notes, attachments, admin
    application.include_router(auth.router)
    application.include_router(plans.router)
    application.include_router(tabs.router)
    application.include_router(tasks.router)
    application.include_router(notes.router)
    application.include_router(attachments.router)
    application.include_router(admin.router)

    # Invite acceptance (top-level route)
    from app.routers.invites import router as invites_router
    application.include_router(invites_router)

    # Root redirect
    @application.get("/")
    async def root():
        return RedirectResponse(url="/plans", status_code=303)

    return application


app = create_app()
