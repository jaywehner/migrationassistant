import uuid
from collections import Counter
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.plan import MigrationPlan, PlanMember
from app.models.tab import ProcessTab
from app.models.task import Task, TaskStatus, TaskPriority

CLOSED_STATUSES = {TaskStatus.closed_complete, TaskStatus.closed_not_needed}


async def get_dashboard_analytics(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Aggregate analytics across every plan the user is a member of."""
    result = await db.execute(
        select(MigrationPlan)
        .join(PlanMember, PlanMember.plan_id == MigrationPlan.id)
        .where(PlanMember.user_id == user_id)
        .options(
            selectinload(MigrationPlan.tabs).selectinload(ProcessTab.tasks).selectinload(Task.assignee),
            selectinload(MigrationPlan.members).selectinload(PlanMember.user),
        )
    )
    plans = list(result.scalars().unique().all())

    all_tasks: list[Task] = []
    for plan in plans:
        for tab in plan.tabs:
            all_tasks.extend(tab.tasks)

    total_tasks = len(all_tasks)
    completed_tasks = sum(1 for t in all_tasks if t.status == TaskStatus.closed_complete)
    open_tasks = total_tasks - sum(1 for t in all_tasks if t.status in CLOSED_STATUSES)

    # Status breakdown (fixed order matching the workflow)
    status_order = list(TaskStatus)
    status_counts = Counter(t.status for t in all_tasks)
    status_breakdown = {s.value: status_counts.get(s, 0) for s in status_order}

    # Priority breakdown
    priority_order = list(TaskPriority)
    priority_counts = Counter(t.priority for t in all_tasks if t.priority)
    priority_breakdown = {p.value: priority_counts.get(p, 0) for p in priority_order}
    priority_breakdown["Unset"] = sum(1 for t in all_tasks if not t.priority)

    # Overdue tasks (due date passed, not closed)
    today = date.today()
    overdue_tasks = [
        t for t in all_tasks
        if t.due_date and t.due_date < today and t.status not in CLOSED_STATUSES
    ]

    # Due soon (next 7 days, not closed)
    due_soon_tasks = [
        t for t in all_tasks
        if t.due_date and today <= t.due_date <= today.fromordinal(today.toordinal() + 7)
        and t.status not in CLOSED_STATUSES
    ]

    # Per-plan progress: % of tasks closed_complete
    plan_progress = []
    for plan in plans:
        plan_tasks = [t for tab in plan.tabs for t in tab.tasks]
        p_total = len(plan_tasks)
        p_done = sum(1 for t in plan_tasks if t.status == TaskStatus.closed_complete)
        pct = round((p_done / p_total) * 100) if p_total else 0
        plan_progress.append({
            "id": str(plan.id),
            "name": plan.name,
            "total": p_total,
            "done": p_done,
            "percent": pct,
        })
    plan_progress.sort(key=lambda p: p["percent"])

    # Workload per assignee (open tasks only)
    assignee_counts: Counter[str] = Counter()
    for t in all_tasks:
        if t.status not in CLOSED_STATUSES and t.assignee:
            assignee_counts[t.assignee.display_name] += 1
    workload = dict(sorted(assignee_counts.items(), key=lambda kv: kv[1], reverse=True)[:10])

    # Tasks created per week over the last 8 weeks (activity trend), bucketed by ISO week
    buckets: dict[str, int] = {}
    for t in all_tasks:
        created = t.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        iso_year, iso_week, _ = created.isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        buckets[key] = buckets.get(key, 0) + 1
    sorted_weeks = sorted(buckets.items())[-8:]
    activity_labels = [w for w, _ in sorted_weeks]
    activity_counts = [c for _, c in sorted_weeks]

    return {
        "total_plans": len(plans),
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "open_tasks": open_tasks,
        "completion_rate": round((completed_tasks / total_tasks) * 100) if total_tasks else 0,
        "overdue_count": len(overdue_tasks),
        "due_soon_count": len(due_soon_tasks),
        "status_breakdown": status_breakdown,
        "priority_breakdown": priority_breakdown,
        "plan_progress": plan_progress,
        "workload": workload,
        "activity_labels": activity_labels,
        "activity_counts": activity_counts,
        "overdue_tasks": sorted(overdue_tasks, key=lambda t: t.due_date)[:10],
        "total_members": len({m.user_id for plan in plans for m in plan.members}),
    }
