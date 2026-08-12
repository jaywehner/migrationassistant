import uuid
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import pyotp
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.encryption import hash_email

ph = PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Migration Platform")


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def get_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key)


def generate_email_verification_token(user_id: str) -> str:
    s = get_serializer()
    return s.dumps({"user_id": user_id, "purpose": "email_verify"})


def verify_email_token(token: str, max_age: int = 86400) -> dict | None:
    """Verify email token. Returns payload or None if invalid/expired."""
    s = get_serializer()
    try:
        data = s.loads(token, max_age=max_age)
        if data.get("purpose") != "email_verify":
            return None
        return data
    except (SignatureExpired, BadSignature):
        return None


def generate_password_reset_token(user_id: str) -> str:
    s = get_serializer()
    return s.dumps({"user_id": user_id, "purpose": "password_reset"})


def verify_password_reset_token(token: str, max_age: int = 3600) -> dict | None:
    """Verify password reset token (1 hour expiry). Returns payload or None."""
    s = get_serializer()
    try:
        data = s.loads(token, max_age=max_age)
        if data.get("purpose") != "password_reset":
            return None
        return data
    except (SignatureExpired, BadSignature):
        return None


def generate_invite_token(plan_id: str, email: str, role: str) -> str:
    s = get_serializer()
    return s.dumps({"plan_id": plan_id, "email": email, "role": role, "purpose": "invite"})


def verify_invite_token(token: str, max_age: int = 604800) -> dict | None:
    """Verify invite token (7 day expiry). Returns payload or None."""
    s = get_serializer()
    try:
        data = s.loads(token, max_age=max_age)
        if data.get("purpose") != "invite":
            return None
        return data
    except (SignatureExpired, BadSignature):
        return None


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Look up user by email using the indexed email_hash."""
    eh = hash_email(email)
    result = await db.execute(select(User).where(User.email_hash == eh))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, email: str, password: str, display_name: str = "") -> User:
    user = User(
        email=email,
        email_hash=hash_email(email),
        password_hash=hash_password(password),
        display_name=display_name or email.split("@")[0],
    )
    db.add(user)
    await db.flush()
    return user


async def check_account_lockout(user: User) -> bool:
    """Returns True if account is currently locked."""
    if not user.is_locked:
        return False
    if user.locked_until and datetime.now(timezone.utc) > user.locked_until:
        # Lockout expired
        user.is_locked = False
        user.failed_login_count = 0
        user.locked_until = None
        return False
    return True


async def record_failed_login(db: AsyncSession, user: User) -> None:
    """Increment failed login count; lock account after 5 failures."""
    user.failed_login_count += 1
    if user.failed_login_count >= 5:
        user.is_locked = True
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    await db.flush()


async def reset_failed_logins(db: AsyncSession, user: User) -> None:
    user.failed_login_count = 0
    user.is_locked = False
    user.locked_until = None
    await db.flush()
