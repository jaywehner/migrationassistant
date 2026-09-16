import uuid
import os
import re
import secrets
from urllib.parse import urlparse
from cryptography.fernet import Fernet
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import get_db, init_db, engine, get_configured_database_url
from app.templating import templates
from app.config import get_settings, clear_settings_cache
from app.services.auth_service import create_user
from app.models.user import GlobalAccessLevel, User

router = APIRouter(tags=["setup"])


_setup_complete = False

async def is_setup_complete() -> bool:
    """Returns True if the application is fully configured."""
    global _setup_complete
    if _setup_complete:
        return True

    # Check if `.setup_complete` file exists
    if os.path.exists(".setup_complete"):
        _setup_complete = True
        return True

    settings = get_settings()
    if not settings.database_url or not settings.secret_key or not settings.field_encryption_key:
        return False

    # Check if database is initialized and has at least one global admin
    try:
        if not engine:
            await init_db()
        if not engine:
            return False
            
        from app.database import AsyncSessionLocal
        if not AsyncSessionLocal:
            return False

        async with AsyncSessionLocal() as session:
            count = (await session.execute(select(func.count()).select_from(User).where(User.is_global_admin == True))).scalar()
            if count and count > 0:
                # Setup is complete! Mark it.
                with open(".setup_complete", "w") as f:
                    f.write("done")
                _setup_complete = True
                return True
    except Exception:
        return False

    return False


async def is_db_initialized() -> bool:
    """Return True if the database is reachable and the users table exists."""
    global engine
    if not engine:
        await init_db()
    if not engine:
        return False
    db_url = get_configured_database_url()
    try:
        async with engine.connect() as conn:
            if db_url.startswith("sqlite"):
                result = await conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                )
                return result.scalar() is not None
            else:
                result = await conn.execute(text("SELECT to_regclass('users')"))
                return result.scalar() is not None
    except Exception:
        return False


def parse_database_url(db_url: str) -> dict:
    """Parse a SQLAlchemy database URL into setup-form fields."""
    defaults = {
        "host": "localhost",
        "port": 5432,
        "username": "postgresmigration",
        "dbname": "migration_platform",
        "password": "",
    }
    if not db_url:
        return defaults

    try:
        # Normalize the asyncpg scheme so urlparse can handle it
        url = db_url.replace("postgresql+asyncpg", "postgresql", 1)
        parsed = urlparse(url)
        if parsed.hostname:
            defaults["host"] = parsed.hostname
        if parsed.port:
            defaults["port"] = parsed.port
        if parsed.username:
            defaults["username"] = parsed.username
        if parsed.password is not None:
            defaults["password"] = parsed.password
        path = parsed.path.strip("/") if parsed.path else ""
        if path:
            defaults["dbname"] = path
    except Exception:
        pass
    return defaults


@router.get("/setup", response_class=HTMLResponse)
async def setup_index(request: Request):
    if await is_setup_complete():
        return RedirectResponse(url="/auth/login", status_code=303)

    settings = get_settings()
    if not settings.database_url or not await is_db_initialized():
        return RedirectResponse(url="/setup/database", status_code=303)

    return RedirectResponse(url="/setup/smtp", status_code=303)


@router.get("/setup/database", response_class=HTMLResponse)
async def setup_database_get(request: Request):
    if await is_setup_complete():
        return RedirectResponse(url="/auth/login", status_code=303)

    settings = get_settings()
    db_params = parse_database_url(settings.database_url)

    return templates.TemplateResponse("setup/database.html", {
        "request": request,
        "host": db_params["host"],
        "port": db_params["port"],
        "username": db_params["username"],
        "password": db_params["password"],
        "dbname": db_params["dbname"],
    })


@router.post("/setup/database", response_class=HTMLResponse)
async def setup_database_post(
    request: Request,
    host: str = Form("localhost"),
    port: int = Form(5432),
    username: str = Form("postgresmigration"),
    password: str = Form(""),
    dbname: str = Form("migration_platform")
):
    if await is_setup_complete():
        return RedirectResponse(url="/auth/login", status_code=303)

    db_url = f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{dbname}"
    
    test_engine = create_async_engine(db_url, echo=False)
    try:
        async with test_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        error_msg = str(e)
        sql_hint = ""
        if "does not exist" in error_msg.lower() and dbname in error_msg:
            sql_hint = f"CREATE DATABASE {dbname};"
            
        return templates.TemplateResponse("setup/database.html", {
            "request": request,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "dbname": dbname,
            "error": "Failed to connect to PostgreSQL. Please check your credentials.",
            "detail": error_msg,
            "sql_hint": sql_hint
        })
    finally:
        await test_engine.dispose()

    # Connection succeeded! Generate keys and save to .env
    env_path = ".env"
    
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
            
    updates = {
        "DATABASE_URL": db_url,
    }
    
    # Generate keys if missing
    settings = get_settings()
    if not settings.secret_key:
        updates["SECRET_KEY"] = secrets.token_urlsafe(48)
    if not settings.field_encryption_key:
        updates["FIELD_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
        
    new_lines = []
    seen = set()
    for line in lines:
        key = line.split("=")[0].strip() if "=" in line else ""
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            seen.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)
        
    # Update environment and clear cache so get_settings() returns new values
    for k, v in updates.items():
        os.environ[k] = v
        
    clear_settings_cache()
    
    # Init DB and run Alembic migrations programmatically
    await init_db(force_reinit=True)
    
    import alembic.config
    import alembic.command
    alembic_cfg = alembic.config.Config("alembic.ini")
    
    # We must run migrations asynchronously using our current engine
    # Alembic handles async engines using the env.py we updated earlier
    try:
        # Run in a thread to avoid blocking the event loop since alembic.command is sync
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, alembic.command.upgrade, alembic_cfg, "head")
    except Exception as e:
        return templates.TemplateResponse("setup/database.html", {
            "request": request,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "dbname": dbname,
            "error": "Database connection successful, but migrations failed.",
            "detail": str(e)
        })

    return RedirectResponse(url="/setup/smtp", status_code=303)


@router.get("/setup/smtp", response_class=HTMLResponse)
async def setup_smtp_get(request: Request):
    if await is_setup_complete():
        return RedirectResponse(url="/auth/login", status_code=303)

    settings = get_settings()
    if not settings.database_url or not await is_db_initialized():
        return RedirectResponse(url="/setup/database", status_code=303)

    return templates.TemplateResponse("setup/smtp.html", {
        "request": request,
        "app_url": settings.app_url,
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_user": settings.smtp_user,
        "smtp_password": settings.smtp_password,
        "smtp_use_tls": settings.smtp_use_tls,
        "smtp_from_email": settings.smtp_from_email,
        "smtp_from_name": settings.smtp_from_name,
    })


@router.post("/setup/smtp", response_class=HTMLResponse)
async def setup_smtp_post(
    request: Request,
    app_url: str = Form("http://localhost:8000"),
    smtp_host: str = Form("localhost"),
    smtp_port: int = Form(1025),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    smtp_use_tls: str = Form("false"),
    smtp_from_email: str = Form("noreply@migration-platform.local"),
    smtp_from_name: str = Form("Migration Platform"),
):
    if await is_setup_complete():
        return RedirectResponse(url="/auth/login", status_code=303)

    settings = get_settings()
    if not settings.database_url:
        return RedirectResponse(url="/setup/database", status_code=303)

    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()

    updates = {
        "APP_URL": app_url.strip().rstrip("/"),
        "SMTP_HOST": smtp_host,
        "SMTP_PORT": str(smtp_port),
        "SMTP_USER": smtp_user,
        "SMTP_PASSWORD": smtp_password,
        "SMTP_USE_TLS": smtp_use_tls.lower(),
        "SMTP_FROM_EMAIL": smtp_from_email,
        "SMTP_FROM_NAME": smtp_from_name,
    }

    new_lines = []
    seen = set()
    for line in lines:
        key = line.split("=")[0].strip() if "=" in line else ""
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            seen.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)

    for k, v in updates.items():
        os.environ[k] = v

    clear_settings_cache()

    return RedirectResponse(url="/setup/admin", status_code=303)


@router.get("/setup/admin", response_class=HTMLResponse)
async def setup_admin_get(request: Request):
    if await is_setup_complete():
        return RedirectResponse(url="/auth/login", status_code=303)

    settings = get_settings()
    if not settings.database_url or not await is_db_initialized():
        return RedirectResponse(url="/setup/database", status_code=303)
        
    return templates.TemplateResponse("setup/admin.html", {
        "request": request
    })


@router.post("/setup/admin", response_class=HTMLResponse)
async def setup_admin_post(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    if await is_setup_complete():
        return RedirectResponse(url="/auth/login", status_code=303)

    if password != confirm_password:
        return templates.TemplateResponse("setup/admin.html", {
            "request": request,
            "email": email,
            "display_name": display_name,
            "error": "Passwords do not match."
        })
        
    if len(password) < 8:
        return templates.TemplateResponse("setup/admin.html", {
            "request": request,
            "email": email,
            "display_name": display_name,
            "error": "Password must be at least 8 characters."
        })

    from app.database import AsyncSessionLocal
    if not AsyncSessionLocal:
        await init_db()

    async with AsyncSessionLocal() as session:
        # Double check if an admin already exists (race condition)
        count = (await session.execute(select(func.count()).select_from(User).where(User.is_global_admin == True))).scalar()
        if count and count > 0:
            with open(".setup_complete", "w") as f:
                f.write("done")
            global _setup_complete
            _setup_complete = True
            return RedirectResponse(url="/auth/login", status_code=303)

        # Create the first global admin
        user = await create_user(session, email, password, display_name)
        user.email_verified = True
        user.global_access_level = GlobalAccessLevel.admin
        user.is_global_admin = True
        user.is_first_admin = True
        await session.commit()
        
    # Mark setup as complete
    with open(".setup_complete", "w") as f:
        f.write("done")
    _setup_complete = True
    
    return RedirectResponse(url="/auth/login", status_code=303)
