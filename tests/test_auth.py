import pytest
import pytest_asyncio
from app.services.auth_service import (
    hash_password,
    verify_password,
    generate_email_verification_token,
    verify_email_token,
    generate_password_reset_token,
    verify_password_reset_token,
    generate_totp_secret,
    verify_totp,
    get_totp_uri,
    get_user_by_email,
    create_user,
    check_account_lockout,
    record_failed_login,
    reset_failed_logins,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "SecurePassword123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(hashed, password) is True

    def test_wrong_password(self):
        hashed = hash_password("correct-password")
        assert verify_password(hashed, "wrong-password") is False

    def test_different_hashes_for_same_password(self):
        p = "same-password"
        h1 = hash_password(p)
        h2 = hash_password(p)
        assert h1 != h2  # Argon2 uses random salts


class TestTokens:
    def test_email_verification_token(self):
        token = generate_email_verification_token("user-123")
        data = verify_email_token(token)
        assert data is not None
        assert data["user_id"] == "user-123"
        assert data["purpose"] == "email_verify"

    def test_email_token_wrong_purpose(self):
        token = generate_password_reset_token("user-123")
        # This token has purpose "password_reset", not "email_verify"
        data = verify_email_token(token)
        assert data is None

    def test_password_reset_token(self):
        token = generate_password_reset_token("user-456")
        data = verify_password_reset_token(token)
        assert data is not None
        assert data["user_id"] == "user-456"

    def test_invalid_token(self):
        assert verify_email_token("garbage-token") is None
        assert verify_password_reset_token("garbage-token") is None


class TestTOTP:
    def test_totp_secret_generation(self):
        secret = generate_totp_secret()
        assert len(secret) > 0

    def test_totp_uri(self):
        secret = generate_totp_secret()
        uri = get_totp_uri(secret, "test@example.com")
        assert "otpauth://totp/" in uri
        assert "Migration%20Platform" in uri

    def test_totp_verify_valid(self):
        import pyotp
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert verify_totp(secret, code) is True

    def test_totp_verify_invalid(self):
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False


class TestUserOperations:
    @pytest.mark.asyncio
    async def test_create_and_lookup(self, db_session):
        user = await create_user(db_session, "new@example.com", "Password123", "New User")
        await db_session.commit()

        found = await get_user_by_email(db_session, "new@example.com")
        assert found is not None
        assert found.display_name == "New User"
        assert found.email_verified is False

    @pytest.mark.asyncio
    async def test_case_insensitive_email_lookup(self, db_session):
        await create_user(db_session, "CamelCase@Example.COM", "Password123")
        await db_session.commit()

        found = await get_user_by_email(db_session, "camelcase@example.com")
        assert found is not None

    @pytest.mark.asyncio
    async def test_account_lockout(self, db_session):
        user = await create_user(db_session, "lockme@example.com", "Password123")
        await db_session.commit()

        # 4 failures: not locked
        for _ in range(4):
            await record_failed_login(db_session, user)
        assert user.is_locked is False

        # 5th failure: locked
        await record_failed_login(db_session, user)
        assert user.is_locked is True
        assert await check_account_lockout(user) is True

        # Reset
        await reset_failed_logins(db_session, user)
        assert user.is_locked is False
        assert await check_account_lockout(user) is False
