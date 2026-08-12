import io
import pyotp
import qrcode
import qrcode.image.svg
from base64 import b64encode
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templating import templates
from app.middleware.auth import get_current_user, require_auth
from app.middleware.csrf import generate_csrf_token, csrf_protect
from app.services.auth_service import (
    get_user_by_email,
    create_user,
    verify_password,
    hash_password,
    check_account_lockout,
    record_failed_login,
    reset_failed_logins,
    generate_email_verification_token,
    verify_email_token,
    generate_password_reset_token,
    verify_password_reset_token,
    generate_totp_secret,
    get_totp_uri,
    verify_totp,
)
from app.services.email_service import send_verification_email, send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    csrf_token = generate_csrf_token(request)
    return templates.TemplateResponse("auth/register.html", {
        "request": request,
        "csrf_token": csrf_token,
    })


@router.post("/register")
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    display_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    errors = []

    if password != confirm_password:
        errors.append("Passwords do not match.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")

    existing = await get_user_by_email(db, email)
    if existing:
        errors.append("An account with this email already exists.")

    if errors:
        csrf_token = generate_csrf_token(request)
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "csrf_token": csrf_token,
            "errors": errors,
            "email": email,
            "display_name": display_name,
        })

    user = await create_user(db, email, password, display_name)
    token = generate_email_verification_token(str(user.id))
    await send_verification_email(email, token)
    await db.commit()

    return templates.TemplateResponse("auth/verify_email_sent.html", {
        "request": request,
        "email": email,
    })


@router.get("/verify-email/{token}", response_class=HTMLResponse)
async def verify_email(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    data = verify_email_token(token)
    if not data:
        return templates.TemplateResponse("auth/verify_email.html", {
            "request": request,
            "success": False,
            "error": "Invalid or expired verification link.",
        })

    from app.services.auth_service import get_user_by_id
    import uuid
    user = await get_user_by_id(db, uuid.UUID(data["user_id"]))
    if not user:
        return templates.TemplateResponse("auth/verify_email.html", {
            "request": request,
            "success": False,
            "error": "User not found.",
        })

    user.email_verified = True
    await db.commit()

    return templates.TemplateResponse("auth/verify_email.html", {
        "request": request,
        "success": True,
    })


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    csrf_token = generate_csrf_token(request)
    return templates.TemplateResponse("auth/login.html", {
        "request": request,
        "csrf_token": csrf_token,
    })


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    csrf_token = generate_csrf_token(request)

    user = await get_user_by_email(db, email)
    if not user:
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "csrf_token": csrf_token,
            "errors": ["Invalid email or password."],
            "email": email,
        })

    # Check lockout
    if await check_account_lockout(user):
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "csrf_token": csrf_token,
            "errors": ["Account is temporarily locked. Please try again in 15 minutes."],
            "email": email,
        })

    # Verify password
    if not verify_password(user.password_hash, password):
        await record_failed_login(db, user)
        await db.commit()
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "csrf_token": csrf_token,
            "errors": ["Invalid email or password."],
            "email": email,
        })

    # Check email verification
    if not user.email_verified:
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "csrf_token": csrf_token,
            "errors": ["Please verify your email before logging in."],
            "email": email,
        })

    # Check MFA
    if user.mfa_enabled:
        request.session["mfa_user_id"] = str(user.id)
        return RedirectResponse(url="/auth/mfa-verify", status_code=303)

    # Success — create session
    await reset_failed_logins(db, user)
    request.session["user_id"] = str(user.id)
    await db.commit()

    return RedirectResponse(url="/plans", status_code=303)


@router.get("/mfa-verify", response_class=HTMLResponse)
async def mfa_verify_page(request: Request):
    if "mfa_user_id" not in request.session:
        return RedirectResponse(url="/auth/login", status_code=303)
    csrf_token = generate_csrf_token(request)
    return templates.TemplateResponse("auth/mfa_verify.html", {
        "request": request,
        "csrf_token": csrf_token,
    })


@router.post("/mfa-verify")
async def mfa_verify_submit(
    request: Request,
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    user_id = request.session.get("mfa_user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    from app.services.auth_service import get_user_by_id
    import uuid
    user = await get_user_by_id(db, uuid.UUID(user_id))
    if not user or not user.mfa_secret:
        return RedirectResponse(url="/auth/login", status_code=303)

    if not verify_totp(user.mfa_secret, code):
        csrf_token = generate_csrf_token(request)
        return templates.TemplateResponse("auth/mfa_verify.html", {
            "request": request,
            "csrf_token": csrf_token,
            "errors": ["Invalid code. Please try again."],
        })

    # MFA verified — create session
    await reset_failed_logins(db, user)
    request.session.pop("mfa_user_id", None)
    request.session["user_id"] = str(user.id)
    await db.commit()

    return RedirectResponse(url="/plans", status_code=303)


@router.get("/mfa-setup", response_class=HTMLResponse)
async def mfa_setup_page(request: Request, user: "User" = Depends(require_auth)):
    secret = generate_totp_secret()
    request.session["mfa_setup_secret"] = secret
    uri = get_totp_uri(secret, user.email)

    # Generate QR code as base64 SVG
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgImage)
    buffer = io.BytesIO()
    img.save(buffer)
    qr_svg = buffer.getvalue().decode()

    csrf_token = generate_csrf_token(request)
    return templates.TemplateResponse("auth/mfa_setup.html", {
        "request": request,
        "csrf_token": csrf_token,
        "qr_svg": qr_svg,
        "secret": secret,
    })


@router.post("/mfa-setup")
async def mfa_setup_submit(
    request: Request,
    code: str = Form(...),
    user: "User" = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    secret = request.session.get("mfa_setup_secret")
    if not secret:
        return RedirectResponse(url="/auth/mfa-setup", status_code=303)

    if not verify_totp(secret, code):
        csrf_token = generate_csrf_token(request)
        return templates.TemplateResponse("auth/mfa_setup.html", {
            "request": request,
            "csrf_token": csrf_token,
            "errors": ["Invalid code. Please try again."],
            "secret": secret,
            "qr_svg": "",
        })

    user.mfa_secret = secret
    user.mfa_enabled = True
    request.session.pop("mfa_setup_secret", None)
    await db.commit()

    return RedirectResponse(url="/plans", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=303)


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    csrf_token = generate_csrf_token(request)
    return templates.TemplateResponse("auth/forgot_password.html", {
        "request": request,
        "csrf_token": csrf_token,
    })


@router.post("/forgot-password")
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    # Always show success to prevent email enumeration
    user = await get_user_by_email(db, email)
    if user:
        token = generate_password_reset_token(str(user.id))
        await send_password_reset_email(email, token)

    return templates.TemplateResponse("auth/forgot_password.html", {
        "request": request,
        "csrf_token": generate_csrf_token(request),
        "success": True,
    })


@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str):
    data = verify_password_reset_token(token)
    if not data:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "error": "Invalid or expired reset link.",
        })
    csrf_token = generate_csrf_token(request)
    return templates.TemplateResponse("auth/reset_password.html", {
        "request": request,
        "csrf_token": csrf_token,
        "token": token,
    })


@router.post("/reset-password/{token}")
async def reset_password_submit(
    request: Request,
    token: str,
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    data = verify_password_reset_token(token)
    if not data:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "error": "Invalid or expired reset link.",
        })

    if password != confirm_password:
        csrf_token = generate_csrf_token(request)
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "csrf_token": csrf_token,
            "token": token,
            "errors": ["Passwords do not match."],
        })

    if len(password) < 8:
        csrf_token = generate_csrf_token(request)
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "csrf_token": csrf_token,
            "token": token,
            "errors": ["Password must be at least 8 characters."],
        })

    from app.services.auth_service import get_user_by_id
    import uuid
    user = await get_user_by_id(db, uuid.UUID(data["user_id"]))
    if not user:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "error": "User not found.",
        })

    user.password_hash = hash_password(password)
    await reset_failed_logins(db, user)
    await db.commit()

    return RedirectResponse(url="/auth/login", status_code=303)


@router.post("/preferences")
async def update_preferences(
    request: Request,
    theme: str = Form("light"),
    user: "User" = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    if theme in ("light", "dark"):
        user.theme_preference = theme
        await db.commit()
    return HTMLResponse("")
