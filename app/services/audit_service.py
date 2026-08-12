import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def log_action(
    db: AsyncSession,
    plan_id: uuid.UUID,
    actor_id: uuid.UUID,
    entity_type: str,
    entity_id: str,
    action: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        plan_id=plan_id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(entry)
    await db.flush()
    return entry
