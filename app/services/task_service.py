import uuid
import bleach
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import Task, TaskStatus, TaskPriority, VALID_TRANSITIONS
from app.models.step import TaskStep
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
            selectinload(Task.steps),
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

    result = await db.execute(
        select(func.max(Task.position)).where(Task.tab_id == tab_id)
    )
    next_position = (result.scalar() or 0) + 1

    task = Task(
        tab_id=tab_id,
        title=title,
        description=description,
        created_by=created_by,
        assigned_to=assigned_to,
        priority=task_priority,
        due_date=due_date,
        position=next_position,
    )
    db.add(task)
    await db.flush()

    await log_action(
        db, plan_id, created_by,
        "task", str(task.id), "created",
        new_value={"title": title, "status": TaskStatus.new.value},
    )
    return task


async def copy_task(
    db: AsyncSession,
    task: Task,
    target_tab_id: uuid.UUID,
    actor_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> Task:
    """Create a duplicate of a task (including its steps) in a target tab."""
    result = await db.execute(
        select(func.max(Task.position)).where(Task.tab_id == target_tab_id)
    )
    next_position = (result.scalar() or 0) + 1

    new_task = Task(
        tab_id=target_tab_id,
        title=task.title,
        description=task.description,
        status=task.status,
        percent_complete=task.percent_complete,
        priority=task.priority,
        due_date=task.due_date,
        assigned_to=task.assigned_to,
        created_by=actor_id,
        position=next_position,
    )
    db.add(new_task)
    await db.flush()

    for step in sorted(task.steps, key=lambda s: s.position):
        new_step = TaskStep(
            task_id=new_task.id,
            title=step.title,
            code=step.code,
            is_done=step.is_done,
            position=step.position,
        )
        db.add(new_step)

    await log_action(
        db, plan_id, actor_id,
        "task", str(new_task.id), "copied",
        new_value={
            "source_task_id": str(task.id),
            "source_tab_id": str(task.tab_id),
            "target_tab_id": str(target_tab_id),
        },
    )
    return new_task


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
    return role in (PlanRole.owner, PlanRole.admin, PlanRole.contributor)


STEP_ALLOWED_TAGS = [
    "b", "strong", "i", "em", "s", "strike", "del", "u",
    "ul", "ol", "li", "a", "br", "p", "div", "span", "code", "pre",
]
STEP_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def _step_attr_filter(tag, name, value):
    if tag == "a":
        return name in ("href", "target", "rel")
    if name == "class" and tag in ("ol", "ul"):
        return value == "list-alpha"
    return False


def sanitize_step_html(html: str) -> str:
    """Sanitize rich-text step content, keeping only basic formatting markup."""
    return bleach.clean(
        html,
        tags=STEP_ALLOWED_TAGS,
        attributes=_step_attr_filter,
        protocols=STEP_ALLOWED_PROTOCOLS,
        strip=True,
    ).strip()


async def create_step(
    db: AsyncSession,
    task: Task,
    title: str,
    code: str,
    actor_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> TaskStep:
    next_position = max((s.position for s in task.steps), default=0) + 1
    step = TaskStep(task_id=task.id, title=title, code=code, position=next_position)
    db.add(step)
    await db.flush()

    await log_action(
        db, plan_id, actor_id,
        "task", str(task.id), "step_added",
        new_value={"title": title, "position": next_position},
    )
    return step


async def get_step_by_id(db: AsyncSession, step_id: uuid.UUID) -> TaskStep | None:
    result = await db.execute(select(TaskStep).where(TaskStep.id == step_id))
    return result.scalar_one_or_none()


async def delete_step(
    db: AsyncSession,
    step: TaskStep,
    task: Task,
    actor_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> None:
    await log_action(
        db, plan_id, actor_id,
        "task", str(task.id), "step_removed",
        old_value={"title": step.title, "position": step.position},
    )
    await db.delete(step)
    await db.flush()

    # Renumber remaining steps
    remaining = sorted((s for s in task.steps if s.id != step.id), key=lambda s: s.position)
    for i, s in enumerate(remaining, start=1):
        s.position = i


async def toggle_step(
    db: AsyncSession,
    step: TaskStep,
    task: Task,
) -> None:
    step.is_done = not step.is_done


async def update_step(
    db: AsyncSession,
    step: TaskStep,
    task: Task,
    title: str,
    code: str,
    actor_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> None:
    await log_action(
        db, plan_id, actor_id,
        "task", str(task.id), "step_updated",
        old_value={"title": step.title, "code": step.code},
        new_value={"title": title, "code": code},
    )
    step.title = title
    step.code = code


async def reorder_steps(
    db: AsyncSession,
    task: Task,
    step_ids: list[uuid.UUID],
    actor_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> None:
    """Reassign positions based on the given order of step IDs."""
    step_map = {s.id: s for s in task.steps}
    position = 1
    for sid in step_ids:
        if sid in step_map:
            step_map[sid].position = position
            position += 1

    await log_action(
        db, plan_id, actor_id,
        "task", str(task.id), "steps_reordered",
        new_value={"order": [str(s) for s in step_ids]},
    )


async def reorder_tasks(
    db: AsyncSession,
    tab_id: uuid.UUID,
    task_ids: list[uuid.UUID],
    actor_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> None:
    """Reassign task positions within a tab based on the given order of task IDs."""
    result = await db.execute(select(Task).where(Task.tab_id == tab_id))
    task_map = {t.id: t for t in result.scalars().all()}

    position = 1
    for tid in task_ids:
        if tid in task_map:
            task_map[tid].position = position
            position += 1

    await log_action(
        db, plan_id, actor_id,
        "tab", str(tab_id), "tasks_reordered",
        new_value={"order": [str(t) for t in task_ids]},
    )
