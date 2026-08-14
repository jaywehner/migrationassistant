from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager
import os

from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import init_db, engine, get_configured_database_url
    await init_db()

    # Make sure all models are imported so their metadata is registered before create_all
    import app.models.user
    import app.models.plan
    import app.models.tab
    import app.models.task
    import app.models.note
    import app.models.attachment
    import app.models.audit
    from app.database import Base

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
        secret_key=settings.secret_key or "temporary_secret_key_for_setup_only",
        session_cookie="session",
        max_age=settings.session_expire_hours * 3600,
        same_site="strict",
        https_only=False,  # Set True in production with TLS
    )

    # Static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    application.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Middleware: Setup redirect
    @application.middleware("http")
    async def enforce_setup(request: Request, call_next):
        if request.url.path.startswith("/setup") or request.url.path.startswith("/static"):
            return await call_next(request)
            
        from app.routers.setup import is_setup_complete
        if not await is_setup_complete():
            return RedirectResponse(url="/setup", status_code=303)
            
        return await call_next(request)

    # Register routers
    from app.routers import auth, plans, tabs, tasks, notes, attachments, admin, setup, analytics
    application.include_router(setup.router)
    application.include_router(auth.router)
    application.include_router(plans.router)
    application.include_router(tabs.router)
    application.include_router(tasks.router)
    application.include_router(notes.router)
    application.include_router(attachments.router)
    application.include_router(admin.router)
    application.include_router(analytics.router)

    # Invite acceptance (top-level route)
    from app.routers.invites import router as invites_router
    application.include_router(invites_router)

    # Root redirect
    @application.get("/")
    async def root():
        return RedirectResponse(url="/plans", status_code=303)

    return application


app = create_app()
