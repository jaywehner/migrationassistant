import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import ProcessNotificationSubscription


async def is_subscribed(
    db: AsyncSession,
    user_id: uuid.UUID,
    tab_id: uuid.UUID,
) -> bool:
    """Return True if the user is subscribed to notifications for a process tab."""
    result = await db.execute(
        select(ProcessNotificationSubscription)
        .where(
            ProcessNotificationSubscription.user_id == user_id,
            ProcessNotificationSubscription.tab_id == tab_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def toggle_subscription(
    db: AsyncSession,
    user_id: uuid.UUID,
    tab_id: uuid.UUID,
) -> bool:
    """Subscribe if not already subscribed, otherwise unsubscribe. Returns True if now subscribed."""
    existing = await db.execute(
        select(ProcessNotificationSubscription)
        .where(
            ProcessNotificationSubscription.user_id == user_id,
            ProcessNotificationSubscription.tab_id == tab_id,
        )
    )
    sub = existing.scalar_one_or_none()
    if sub:
        await db.delete(sub)
        return False

    db.add(ProcessNotificationSubscription(user_id=user_id, tab_id=tab_id))
    return True


async def get_user_subscriptions(
    db: AsyncSession,
    user_id: uuid.UUID,
):
    """Return all process-tab subscriptions for a user, loaded with tab and plan."""
    from sqlalchemy.orm import selectinload
    from app.models.tab import ProcessTab
    from app.models.plan import MigrationPlan

    result = await db.execute(
        select(ProcessNotificationSubscription)
        .where(ProcessNotificationSubscription.user_id == user_id)
        .options(
            selectinload(ProcessNotificationSubscription.tab).selectinload(ProcessTab.plan)
        )
        .order_by(ProcessNotificationSubscription.created_at.desc())
    )
    return result.scalars().all()


async def get_subscribed_user_ids(
    db: AsyncSession,
    tab_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Return all user IDs subscribed to a given process tab."""
    result = await db.execute(
        select(ProcessNotificationSubscription.user_id)
        .where(ProcessNotificationSubscription.tab_id == tab_id)
    )
    return [row[0] for row in result.all()]
