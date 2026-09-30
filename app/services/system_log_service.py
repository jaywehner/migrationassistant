import json
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_log import SystemLog, LogLevel
from app.config import get_settings

logger = logging.getLogger(__name__)


LEVEL_RANK = {
    LogLevel.normal.value: 1,
    LogLevel.verbose.value: 2,
    LogLevel.debug.value: 3,
}


def _should_log(event_level: str, current_level: str) -> bool:
    return LEVEL_RANK.get(event_level, 1) <= LEVEL_RANK.get(current_level, 1)


async def log_system_event(
    db: AsyncSession,
    action: str,
    category: str = "system",
    level: str = LogLevel.normal.value,
    actor=None,
    details: dict | None = None,
    request=None,
):
    """Write a system log entry if the configured log level permits it.

    Passwords, tokens, and other sensitive field values must never be
    included in `details`.
    """
    settings = get_settings()
    if not _should_log(level, settings.log_level):
        return

    ip_address = None
    user_agent = None
    if request is not None:
        if hasattr(request, "client") and request.client:
            ip_address = request.client.host
        user_agent = request.headers.get("user-agent")

    actor_id = None
    actor_name = None
    if actor is not None:
        actor_id = getattr(actor, "id", None)
        actor_name = getattr(actor, "display_name", None)

    safe_details = {}
    if details:
        for key, value in details.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                safe_details[key] = value
            else:
                safe_details[key] = str(value)

    entry = SystemLog(
        level=level,
        category=category,
        action=action,
        actor_id=actor_id,
        actor_name=actor_name,
        details=json.dumps(safe_details) if safe_details else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)


async def get_system_logs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    category: str | None = None,
    level: str | None = None,
):
    query = select(SystemLog)
    count_query = select(func.count()).select_from(SystemLog)

    if category:
        query = query.where(SystemLog.category == category)
        count_query = count_query.where(SystemLog.category == category)
    if level:
        query = query.where(SystemLog.level == level)
        count_query = count_query.where(SystemLog.level == level)

    total = (await db.execute(count_query)).scalar()
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1

    result = await db.execute(
        query.order_by(SystemLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    entries = list(result.scalars().all())
    return entries, total, total_pages


async def prune_old_logs(db: AsyncSession) -> int:
    """Delete system logs older than the configured retention period."""
    settings = get_settings()
    days = max(1, settings.log_retention_days)
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        delete(SystemLog).where(SystemLog.created_at < cutoff)
    )
    return result.rowcount


def get_log_settings():
    settings = get_settings()
    return {
        "log_level": settings.log_level,
        "log_retention_days": settings.log_retention_days,
    }


def set_log_settings(log_level: str, log_retention_days: int):
    """Update the .env file with log settings and current environment."""
    import os
    log_level = log_level if log_level in (LogLevel.normal.value, LogLevel.verbose.value, LogLevel.debug.value) else LogLevel.normal.value
    days = max(1, int(log_retention_days))

    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    updates = {
        "LOG_LEVEL": log_level,
        "LOG_RETENTION_DAYS": str(days),
    }

    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()

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

    for key, value in updates.items():
        os.environ[key] = value
