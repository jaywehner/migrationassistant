from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    secret_key: str = Field(..., description="Secret key for signing tokens")
    allowed_origins: str = "http://localhost:8000"
    app_url: str = "http://localhost:8000"

    # Database
    database_url: str = "postgresql+asyncpg://appuser:changeme@db:5432/migration_platform"

    # Field encryption
    field_encryption_key: str = Field(..., description="Fernet key for field-level encryption")

    # SMTP
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    smtp_from_email: str = "noreply@migration-platform.local"
    smtp_from_name: str = "Migration Platform"

    # File uploads
    upload_dir: str = "/app/uploads"
    max_upload_size_mb: int = 25

    # ClamAV
    clamav_enabled: bool = False
    clamav_host: str = "clamav"
    clamav_port: int = 3310

    # Session
    session_expire_hours: int = 24

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
