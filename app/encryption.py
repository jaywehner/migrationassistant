import hashlib
from cryptography.fernet import Fernet
from sqlalchemy import String, TypeDecorator
from app.config import get_settings


_fernet = None


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        settings = get_settings()
        _fernet = Fernet(settings.field_encryption_key.encode())
    return _fernet


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string value using Fernet (AES-128-CBC + HMAC)."""
    if not plaintext:
        return plaintext
    f = get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    if not ciphertext:
        return ciphertext
    f = get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


def hash_email(email: str) -> str:
    """Create a SHA-256 hash of a normalized email for indexed lookups."""
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


class EncryptedString(TypeDecorator):
    """SQLAlchemy TypeDecorator that transparently encrypts/decrypts string columns."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return encrypt_field(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return decrypt_field(value)
        return value
