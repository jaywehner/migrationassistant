import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_email(to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """Send an email via SMTP. Returns True on success, False on failure."""
    settings = get_settings()

    message = MIMEMultipart("alternative")
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = to_email
    message["Subject"] = subject

    if text_body:
        message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_use_tls,
        )
        logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


async def send_verification_email(to_email: str, token: str) -> bool:
    settings = get_settings()
    verify_url = f"{settings.app_url}/auth/verify-email/{token}"
    html = f"""
    <h2>Verify Your Email</h2>
    <p>Welcome to the Migration Collaboration Platform!</p>
    <p>Please click the link below to verify your email address:</p>
    <p><a href="{verify_url}">Verify Email</a></p>
    <p>This link expires in 24 hours.</p>
    <p>If you did not create an account, please ignore this email.</p>
    """
    return await send_email(to_email, "Verify Your Email - Migration Platform", html)


async def send_password_reset_email(to_email: str, token: str) -> bool:
    settings = get_settings()
    reset_url = f"{settings.app_url}/auth/reset-password/{token}"
    html = f"""
    <h2>Password Reset</h2>
    <p>You requested a password reset for your Migration Platform account.</p>
    <p>Click the link below to set a new password:</p>
    <p><a href="{reset_url}">Reset Password</a></p>
    <p>This link expires in 1 hour.</p>
    <p>If you did not request this, please ignore this email.</p>
    """
    return await send_email(to_email, "Password Reset - Migration Platform", html)


async def send_invite_email(to_email: str, plan_name: str, inviter_name: str, token: str) -> bool:
    settings = get_settings()
    invite_url = f"{settings.app_url}/invite/{token}"
    html = f"""
    <h2>You're Invited!</h2>
    <p>{inviter_name} has invited you to collaborate on the migration plan: <strong>{plan_name}</strong></p>
    <p>Click the link below to join:</p>
    <p><a href="{invite_url}">Accept Invitation</a></p>
    <p>This invitation expires in 7 days.</p>
    """
    return await send_email(to_email, f"Invitation to {plan_name} - Migration Platform", html)


async def send_new_account_email(to_email: str, password: str, display_name: str) -> bool:
    """Send account credentials to a user created by an admin."""
    settings = get_settings()
    login_url = f"{settings.app_url}/auth/login"
    html = f"""
    <h2>Your Account Has Been Created</h2>
    <p>Hi {display_name or to_email},</p>
    <p>An administrator has created an account for you on the Migration Collaboration Platform.</p>
    <p>Your login credentials:</p>
    <ul>
        <li><strong>Email:</strong> {to_email}</li>
        <li><strong>Password:</strong> {password}</li>
    </ul>
    <p><a href="{login_url}">Log In</a></p>
    <p>Please change your password after your first login.</p>
    """
    return await send_email(to_email, "Your Account Credentials - Migration Platform", html)
