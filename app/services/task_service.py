import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import Task, TaskStatus, TaskPriority, VALID_TRANSITIONS
from app.models.tab import ProcessTab
from app.models.plan import PlanRole
from app.services.audit_service import log_action


async def get_task_by_id(db: AsyncSession, task_id: uuid.UUID) -> Task | None:
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.assignee),
            selectinload(Task.creator),
            selectinload(Task.notes),
            selectinload(Task.attachments),
        )
    )
    return result.scalar_one_or_none()


async def get_plan_id_for_task(db: AsyncSession, task_id: uuid.UUID) -> uuid.UUID | None:
    """Resolve task -> tab -> plan_id."""
    result = await db.execute(
        select(ProcessTab.plan_id)
        .join(Task, Task.tab_id == ProcessTab.id)
        .where(Task.id == task_id)
    )
    return result.scalar_one_or_none()


async def create_task(
    db: AsyncSession,
    tab_id: uuid.UUID,
    title: str,
    description: str,
    created_by: uuid.UUID,
    plan_id: uuid.UUID,
    assigned_to: uuid.UUID | None = None,
    priority: str | None = None,
    due_date=None,
) -> Task:
    task_priority = None
    if priority:
        try:
            task_priority = TaskPriority(priority)
        except ValueError:
            pass

    task = Task(
        tab_id=tab_id,
        title=title,
        description=description,
        created_by=created_by,
        assigned_to=assigned_to,
        priority=task_priority,
        due_date=due_date,
    )
    db.add(task)
    await db.flush()

    await log_action(
        db, plan_id, created_by,
        "task", str(task.id), "created",
        new_value={"title": title, "status": TaskStatus.new.value},
    )
    return task


async def change_task_status(
    db: AsyncSession,
    task: Task,
    new_status: TaskStatus,
    actor_id: uuid.UUID,
    plan_id: uuid.UUID,
    role: PlanRole,
) -> tuple[bool, str]:
    """Change task status following the state machine. Returns (success, error_message)."""
    old_status = task.status

    # Check if transition is valid
    valid_next = VALID_TRANSITIONS.get(old_status, set())
    if new_status not in valid_next:
        return False, f"Cannot transition from '{old_status.value}' to '{new_status.value}'"

    # Reopening from closed states requires Admin/Owner
    if old_status in (TaskStatus.closed_complete, TaskStatus.closed_not_needed):
        if role not in (PlanRole.owner, PlanRole.admin):
            return False, "Only Admin or Owner can reopen closed tasks"

    task.status = new_status

    # Auto-adjust percent_complete for closed statuses
    if new_status == TaskStatus.closed_complete:
        task.percent_complete = 100
    elif new_status == TaskStatus.closed_not_needed:
        task.percent_complete = 0

    await log_action(
        db, plan_id, actor_id,
        "task", str(task.id), "status_change",
        old_value={"status": old_status.value},
        new_value={"status": new_status.value},
    )
    return True, ""


async def assign_task(
    db: AsyncSession,
    task: Task,
    assignee_id: uuid.UUID | None,
    actor_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> None:
    old_assignee = str(task.assigned_to) if task.assigned_to else None
    task.assigned_to = assignee_id

    await log_action(
        db, plan_id, actor_id,
        "task", str(task.id), "assigned",
        old_value={"assigned_to": old_assignee},
        new_value={"assigned_to": str(assignee_id) if assignee_id else None},
    )


async def update_task(
    db: AsyncSession,
    task: Task,
    actor_id: uuid.UUID,
    plan_id: uuid.UUID,
    **kwargs,
) -> None:
    changes_old = {}
    changes_new = {}

    for field, value in kwargs.items():
        if hasattr(task, field):
            old_val = getattr(task, field)
            if old_val != value:
                changes_old[field] = str(old_val) if old_val is not None else None
                changes_new[field] = str(value) if value is not None else None
                setattr(task, field, value)

    if changes_old:
        await log_action(
            db, plan_id, actor_id,
            "task", str(task.id), "updated",
            old_value=changes_old,
            new_value=changes_new,
        )


def can_edit_task(role: PlanRole, task: Task, user_id: uuid.UUID) -> bool:
    """Check if user can edit this task based on their role."""
    if role in (PlanRole.owner, PlanRole.admin):
        return True
    if role == PlanRole.contributor and task.assigned_to == user_id:
        return True
    return False
