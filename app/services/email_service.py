import logging
from html import escape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)


def build_email_layout(title: str, body: str, button_label: str = "", button_url: str = "") -> str:
    button = ""
    if button_label and button_url:
        button = f"""
            <table role="presentation" cellspacing="0" cellpadding="0" style="margin:28px 0 24px;">
                <tr><td style="border-radius:999px;background:#c89b5e;">
                    <a href="{escape(button_url, quote=True)}" style="display:inline-block;padding:13px 24px;color:#0d1b2a;text-decoration:none;font-weight:700;">{escape(button_label)}</a>
                </td></tr>
            </table>
        """
    return f"""<!doctype html>
<html lang="en">
<body style="margin:0;padding:0;background:#f3f5f8;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#253247;">
    <div style="display:none;max-height:0;overflow:hidden;">{escape(title)} - Migration Assistant</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f5f8;padding:32px 16px;">
        <tr><td align="center">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#ffffff;border-radius:18px;overflow:hidden;box-shadow:0 14px 42px rgba(13,27,42,0.12);">
                <tr><td style="padding:28px 34px;background:linear-gradient(135deg,#0d1b2a 0%,#1e3a8a 60%,#0d1b2a 100%);color:#ffffff;">
                    <table role="presentation" cellspacing="0" cellpadding="0"><tr>
                        <td style="width:42px;height:42px;border:1px solid #c89b5e;border-radius:11px;text-align:center;color:#c89b5e;font-size:20px;font-weight:700;">M</td>
                        <td style="padding-left:13px;"><div style="font-size:17px;font-weight:700;">Migration Assistant</div><div style="margin-top:2px;color:#cbd5e1;font-size:12px;">Plan. Coordinate. Deliver.</div></td>
                    </tr></table>
                </td></tr>
                <tr><td style="padding:36px 34px;">
                    <h1 style="margin:0 0 18px;color:#0d1b2a;font-size:26px;line-height:1.25;">{escape(title)}</h1>
                    <div style="font-size:15px;line-height:1.7;color:#4b5563;">{body}</div>
                    {button}
                    <p style="margin:26px 0 0;padding-top:20px;border-top:1px solid #e5e7eb;color:#8b929c;font-size:12px;line-height:1.6;">This message was sent by Migration Assistant. If you were not expecting it, you can safely ignore this email.</p>
                </td></tr>
            </table>
        </td></tr>
    </table>
</body>
</html>"""


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
    html = build_email_layout(
        "Verify your email address",
        "<p style=\"margin:0 0 14px;\">Welcome to Migration Assistant. Confirm your email address to activate your account and start collaborating on migration plans.</p><p style=\"margin:0;color:#6b7280;\">This verification link expires in 24 hours.</p>",
        "Verify Email",
        verify_url,
    )
    return await send_email(to_email, "Verify Your Email - Migration Assistant", html)


async def send_password_reset_email(to_email: str, token: str) -> bool:
    settings = get_settings()
    reset_url = f"{settings.app_url}/auth/reset-password/{token}"
    html = build_email_layout(
        "Reset your password",
        "<p style=\"margin:0 0 14px;\">We received a request to reset the password for your Migration Assistant account.</p><p style=\"margin:0;color:#6b7280;\">This secure link expires in 1 hour.</p>",
        "Reset Password",
        reset_url,
    )
    return await send_email(to_email, "Password Reset - Migration Assistant", html)


async def send_invite_email(to_email: str, plan_name: str, inviter_name: str, token: str) -> bool:
    settings = get_settings()
    invite_url = f"{settings.app_url}/invite/{token}"
    safe_inviter = escape(inviter_name)
    safe_plan = escape(plan_name)
    html = build_email_layout(
        "You’re invited to collaborate",
        f"<p style=\"margin:0 0 14px;\"><strong style=\"color:#0d1b2a;\">{safe_inviter}</strong> invited you to collaborate on <strong style=\"color:#0d1b2a;\">{safe_plan}</strong>.</p><p style=\"margin:0;color:#6b7280;\">Open the plan to coordinate tasks, document technical steps, and track migration progress with the team. This invitation expires in 7 days.</p>",
        "Open Migration Plan",
        invite_url,
    )
    return await send_email(to_email, f"Invitation to {plan_name} - Migration Assistant", html)


async def send_new_account_email(to_email: str, password: str, display_name: str) -> bool:
    """Send account credentials to a user created by an admin."""
    settings = get_settings()
    login_url = f"{settings.app_url}/auth/login"
    safe_name = escape(display_name or to_email)
    safe_email = escape(to_email)
    safe_password = escape(password)
    html = build_email_layout(
        "Your account is ready",
        f"<p style=\"margin:0 0 14px;\">Hi {safe_name},</p><p style=\"margin:0 0 18px;\">An administrator created a Migration Assistant account for you.</p><div style=\"padding:16px 18px;border:1px solid #e5e7eb;border-radius:10px;background:#f8fafc;\"><div style=\"margin-bottom:8px;\"><strong>Email:</strong> {safe_email}</div><div><strong>Temporary password:</strong> <span style=\"font-family:Consolas,monospace;\">{safe_password}</span></div></div><p style=\"margin:16px 0 0;color:#6b7280;\">Sign in and change your password as soon as possible.</p>",
        "Sign In",
        login_url,
    )
    return await send_email(to_email, "Your Account Credentials - Migration Assistant", html)
