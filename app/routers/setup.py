import uuid
import os
import secrets
from cryptography.fernet import Fernet
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import get_db, init_db, engine
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


@router.get("/setup", response_class=HTMLResponse)
async def setup_index(request: Request):
    if await is_setup_complete():
        return RedirectResponse(url="/auth/login", status_code=303)
        
    settings = get_settings()
    if not settings.database_url:
        return RedirectResponse(url="/setup/database", status_code=303)
        
    return RedirectResponse(url="/setup/admin", status_code=303)


@router.get("/setup/database", response_class=HTMLResponse)
async def setup_database_get(request: Request):
    if await is_setup_complete():
        return RedirectResponse(url="/auth/login", status_code=303)
        
    return templates.TemplateResponse("setup/database.html", {
        "request": request,
        "host": "localhost",
        "port": 5432,
        "username": "postgres",
        "dbname": "migration_platform"
    })


@router.post("/setup/database", response_class=HTMLResponse)
async def setup_database_post(
    request: Request,
    host: str = Form("localhost"),
    port: int = Form(5432),
    username: str = Form("postgres"),
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
            "dbname": dbname,
            "error": "Database connection successful, but migrations failed.",
            "detail": str(e)
        })

    return RedirectResponse(url="/setup/admin", status_code=303)


@router.get("/setup/admin", response_class=HTMLResponse)
async def setup_admin_get(request: Request):
    if await is_setup_complete():
        return RedirectResponse(url="/auth/login", status_code=303)
        
    settings = get_settings()
    if not settings.database_url:
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
