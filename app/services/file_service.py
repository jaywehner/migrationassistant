import os
import uuid
from pathlib import Path

from app.config import get_settings

# Allowed extensions (lowercase)
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".log", ".md",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp",
    ".zip", ".7z", ".tar", ".gz",
    ".json", ".xml", ".yaml", ".yml",
}

# Blocked extensions
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".sh", ".ps1", ".cmd", ".msi", ".dll",
    ".com", ".vbs", ".js", ".wsh", ".wsf", ".scr", ".pif",
}


def validate_file_extension(filename: str) -> tuple[bool, str]:
    """Validate file extension. Returns (is_valid, error_message)."""
    ext = Path(filename).suffix.lower()
    if ext in BLOCKED_EXTENSIONS:
        return False, f"File type '{ext}' is not allowed."
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"File type '{ext}' is not in the allowed list."
    return True, ""


def validate_file_size(size_bytes: int) -> tuple[bool, str]:
    settings = get_settings()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        return False, f"File exceeds maximum size of {settings.max_upload_size_mb} MB."
    return True, ""


def generate_storage_key() -> str:
    return str(uuid.uuid4())


def get_storage_path(storage_key: str) -> str:
    settings = get_settings()
    return os.path.join(settings.upload_dir, storage_key)


async def save_file(storage_key: str, data: bytes) -> str:
    """Save file data to storage. Returns the full path."""
    path = get_storage_path(storage_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def delete_file(storage_key: str) -> bool:
    """Delete a file from storage."""
    path = get_storage_path(storage_key)
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


def get_mime_type(filename: str) -> str:
    """Guess MIME type from filename."""
    import mimetypes
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"
