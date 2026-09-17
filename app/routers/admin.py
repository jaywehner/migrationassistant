import uuid
from fastapi import APIRouter, Request, Depends, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.templating import templates
from app.middleware.auth import require_auth, require_global_admin
from app.middleware.csrf import generate_csrf_token, csrf_protect
from app.models.user import User, GlobalAccessLevel
from app.models.audit import AuditLog
from app.models.plan import PlanRole, MigrationPlan
from app.services.plan_service import get_user_role_in_plan, get_plan_by_id
from app.services.auth_service import create_user as create_new_user, get_user_by_id, get_user_by_email, hash_password, validate_email_address
from app.services.email_service import send_new_account_email
from app.services.email_service import send_email

router = APIRouter(tags=["admin"])

PAGE_SIZE = 25


@router.get("/plans/{plan_id}/audit", response_class=HTMLResponse)
async def audit_log(
    request: Request,
    plan_id: uuid.UUID,
    page: int = Query(1, ge=1),
    entity_type: str = Query("", alias="type"),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or role not in (PlanRole.owner, PlanRole.admin, PlanRole.contributor):
        raise HTTPException(status_code=403)

    plan = await get_plan_by_id(db, plan_id)

    # Build query
    query = select(AuditLog).where(AuditLog.plan_id == plan_id)
    count_query = select(func.count()).select_from(AuditLog).where(AuditLog.plan_id == plan_id)

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
        count_query = count_query.where(AuditLog.entity_type == entity_type)

    # Total count
    total = (await db.execute(count_query)).scalar()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    # Paginate
    query = (
        query.options(selectinload(AuditLog.actor))
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    )
    result = await db.execute(query)
    entries = list(result.scalars().all())

    csrf_token = generate_csrf_token(request)

    return templates.TemplateResponse("admin/audit_log.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "plan": plan,
        "entries": entries,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "entity_type": entity_type,
        "entity_types": ["task", "note", "attachment", "member", "plan", "tab"],
    })


# ---------------------------------------------------------------------------
# Global Admin Area
# ---------------------------------------------------------------------------

@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    csrf_token = generate_csrf_token(request)
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar()
    plan_count = (await db.execute(select(func.count()).select_from(MigrationPlan))).scalar()

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "user_count": user_count,
        "plan_count": plan_count,
    })


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = list(result.scalars().all())
    csrf_token = generate_csrf_token(request)

    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "users": users,
        "access_levels": [e.value for e in GlobalAccessLevel],
    })


@router.post("/admin/users/new")
async def admin_create_user(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(""),
    password: str = Form(...),
    confirm_password: str = Form(...),
    access_level: str = Form("user"),
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    email_error = validate_email_address(email)
    if email_error:
        raise HTTPException(status_code=422, detail=email_error)

    if password != confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match")

    try:
        level = GlobalAccessLevel(access_level)
    except ValueError:
        level = GlobalAccessLevel.user

    existing = await get_user_by_email(db, email)
    if existing:
        raise HTTPException(status_code=409, detail="A user with that email already exists")

    new_user = await create_new_user(db, email.strip(), password, display_name.strip())
    new_user.global_access_level = level
    new_user.is_global_admin = level == GlobalAccessLevel.admin
    new_user.email_verified = True  # Admin-created users are pre-verified
    await send_new_account_email(email.strip(), password, display_name.strip())
    await db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{target_user_id}/update")
async def admin_update_user(
    request: Request,
    target_user_id: uuid.UUID,
    display_name: str = Form(""),
    access_level: str = Form("user"),
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    target = await get_user_by_id(db, target_user_id)
    if not target:
        raise HTTPException(status_code=404)

    if target.is_first_admin and user.id != target.id:
        raise HTTPException(status_code=403, detail="The first admin account cannot be modified by another admin")

    try:
        level = GlobalAccessLevel(access_level)
    except ValueError:
        level = GlobalAccessLevel.user

    target.display_name = display_name.strip() or target.display_name
    target.global_access_level = level
    target.is_global_admin = level == GlobalAccessLevel.admin
    await db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{target_user_id}/reset-password")
async def admin_reset_password(
    request: Request,
    target_user_id: uuid.UUID,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    target = await get_user_by_id(db, target_user_id)
    if not target:
        raise HTTPException(status_code=404)

    if target.is_first_admin and user.id != target.id:
        raise HTTPException(status_code=403, detail="The first admin password cannot be changed by another admin")

    if new_password != confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match")

    if len(new_password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    target.password_hash = hash_password(new_password)
    await db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{target_user_id}/delete")
async def admin_delete_user(
    request: Request,
    target_user_id: uuid.UUID,
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    target = await get_user_by_id(db, target_user_id)
    if not target:
        raise HTTPException(status_code=404)

    if target.is_first_admin:
        raise HTTPException(status_code=403, detail="The first admin account cannot be deleted")

    if target.id == user.id:
        raise HTTPException(status_code=403, detail="You cannot delete your own account from here")

    await db.delete(target)
    await db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(
    request: Request,
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    csrf_token = generate_csrf_token(request)
    from app.config import get_settings
    settings = get_settings()

    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_user": settings.smtp_user,
        "smtp_password": settings.smtp_password,
        "smtp_use_tls": settings.smtp_use_tls,
        "smtp_from_email": settings.smtp_from_email,
        "smtp_from_name": settings.smtp_from_name,
        "max_upload_size_mb": settings.max_upload_size_mb,
        "session_expire_hours": settings.session_expire_hours,
        "app_url": settings.app_url,
    })


@router.post("/admin/settings")
async def admin_settings_update(
    request: Request,
    smtp_host: str = Form(""),
    smtp_port: int = Form(1025),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    smtp_use_tls: str = Form("false"),
    smtp_from_email: str = Form(""),
    smtp_from_name: str = Form(""),
    max_upload_size_mb: int = Form(25),
    session_expire_hours: int = Form(24),
    app_url: str = Form(""),
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    # Settings are read-only at runtime; update the .env file for persistence
    import os
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    if os.path.exists(env_path):
        lines = []
        with open(env_path, "r") as f:
            lines = f.readlines()

        updates = {
            "SMTP_HOST": smtp_host,
            "SMTP_PORT": str(smtp_port),
            "SMTP_USER": smtp_user,
            "SMTP_PASSWORD": smtp_password,
            "SMTP_USE_TLS": smtp_use_tls.lower(),
            "SMTP_FROM_EMAIL": smtp_from_email,
            "SMTP_FROM_NAME": smtp_from_name,
            "MAX_UPLOAD_SIZE_MB": str(max_upload_size_mb),
            "SESSION_EXPIRE_HOURS": str(session_expire_hours),
            "APP_URL": app_url.strip().rstrip("/"),
        }

        new_lines = []
        seen = set()
        for line in lines:
            key = line.split("=")[0] if "=" in line else ""
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
        
        # Update environment variables for immediate effect
        for key, value in updates.items():
            os.environ[key] = value

    return RedirectResponse(url="/admin/settings", status_code=303)


@router.post("/admin/settings/test")
async def admin_settings_test_email(
    request: Request,
    smtp_host: str = Form(""),
    smtp_port: int = Form(1025),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    smtp_use_tls: str = Form("false"),
    smtp_from_email: str = Form(""),
    smtp_from_name: str = Form(""),
    test_email_to: str = Form(""),
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    
    # Validate test email
    if not test_email_to:
        return JSONResponse(content={"status": "error", "detail": "Please provide an email address to send the test to"}, status_code=400)
    
    # Test with the provided settings
    import aiosmtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    message = MIMEMultipart("alternative")
    message["From"] = f"{smtp_from_name} <{smtp_from_email}>"
    message["To"] = test_email_to
    message["Subject"] = "Email Configuration Test"
    
    html = f"""
    <h2>Email Configuration Test</h2>
    <p>This is a test email to verify your SMTP settings are working correctly.</p>
    <p>If you received this email, your configuration is valid!</p>
    <p>Settings used:</p>
    <ul>
        <li>Host: {smtp_host}</li>
        <li>Port: {smtp_port}</li>
        <li>TLS: {smtp_use_tls}</li>
        <li>From: {smtp_from_email}</li>
    </ul>
    """
    message.attach(MIMEText(html, "html"))
    
    try:
        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user or None,
            password=smtp_password or None,
            use_tls=smtp_use_tls.lower() == "true",
        )
        return JSONResponse(content={"status": "success", "message": "Test email sent successfully"})
    except Exception as e:
        return JSONResponse(content={"status": "error", "detail": str(e)}, status_code=400)
