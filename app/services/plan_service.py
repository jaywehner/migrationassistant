import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.plan import MigrationPlan, PlanMember, PlanInvite, PlanRole
from app.models.user import User
from app.services.auth_service import generate_invite_token


async def get_user_plans(db: AsyncSession, user_id: uuid.UUID) -> list[MigrationPlan]:
    """Get all plans where user is a member."""
    result = await db.execute(
        select(MigrationPlan)
        .join(PlanMember, PlanMember.plan_id == MigrationPlan.id)
        .where(PlanMember.user_id == user_id)
        .options(selectinload(MigrationPlan.members))
    )
    return list(result.scalars().unique().all())


async def get_plan_by_id(db: AsyncSession, plan_id: uuid.UUID) -> MigrationPlan | None:
    result = await db.execute(
        select(MigrationPlan)
        .where(MigrationPlan.id == plan_id)
        .options(
            selectinload(MigrationPlan.members).selectinload(PlanMember.user),
            selectinload(MigrationPlan.tabs),
        )
    )
    return result.scalar_one_or_none()


async def create_plan(db: AsyncSession, name: str, description: str, owner: User) -> MigrationPlan:
    plan = MigrationPlan(name=name, description=description, owner_id=owner.id)
    db.add(plan)
    await db.flush()

    # Add owner as member with owner role
    member = PlanMember(plan_id=plan.id, user_id=owner.id, role=PlanRole.owner)
    db.add(member)
    await db.flush()
    return plan


async def get_user_role_in_plan(db: AsyncSession, plan_id: uuid.UUID, user_id: uuid.UUID) -> PlanRole | None:
    result = await db.execute(
        select(PlanMember.role)
        .where(PlanMember.plan_id == plan_id, PlanMember.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_plan_members(db: AsyncSession, plan_id: uuid.UUID) -> list[PlanMember]:
    result = await db.execute(
        select(PlanMember)
        .where(PlanMember.plan_id == plan_id)
        .options(selectinload(PlanMember.user))
    )
    return list(result.scalars().all())


async def create_invite(
    db: AsyncSession,
    plan_id: uuid.UUID,
    email: str,
    role: PlanRole,
    invited_by: uuid.UUID,
) -> PlanInvite:
    token = generate_invite_token(str(plan_id), email, role.value)
    invite = PlanInvite(
        plan_id=plan_id,
        email=email,
        token=token,
        role=role,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    await db.flush()
    return invite


async def get_invite_by_token(db: AsyncSession, token: str) -> PlanInvite | None:
    result = await db.execute(
        select(PlanInvite)
        .where(PlanInvite.token == token, PlanInvite.accepted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def accept_invite(db: AsyncSession, invite: PlanInvite, user: User) -> PlanMember:
    invite.accepted_at = datetime.now(timezone.utc)
    member = PlanMember(
        plan_id=invite.plan_id,
        user_id=user.id,
        role=invite.role,
    )
    db.add(member)
    await db.flush()
    return member


async def remove_member(db: AsyncSession, plan_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(PlanMember)
        .where(PlanMember.plan_id == plan_id, PlanMember.user_id == user_id)
    )
    member = result.scalar_one_or_none()
    if member and member.role != PlanRole.owner:
        await db.delete(member)
        return True
    return False


async def change_member_role(db: AsyncSession, plan_id: uuid.UUID, user_id: uuid.UUID, new_role: PlanRole) -> bool:
    result = await db.execute(
        select(PlanMember)
        .where(PlanMember.plan_id == plan_id, PlanMember.user_id == user_id)
    )
    member = result.scalar_one_or_none()
    if member and member.role != PlanRole.owner:
        member.role = new_role
        return True
    return False


def can_manage_members(role: PlanRole) -> bool:
    return role in (PlanRole.owner, PlanRole.admin)


def can_edit_plan(role: PlanRole) -> bool:
    return role in (PlanRole.owner, PlanRole.admin)


def can_create_tasks(role: PlanRole) -> bool:
    return role in (PlanRole.owner, PlanRole.admin, PlanRole.contributor)


def can_view_plan(role: PlanRole) -> bool:
    return role is not None
