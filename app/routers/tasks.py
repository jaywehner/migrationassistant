import uuid
from datetime import date
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templating import templates
from app.middleware.auth import require_auth
from app.middleware.csrf import generate_csrf_token, csrf_protect
from app.models.user import User
from app.models.task import TaskStatus, TaskPriority, VALID_TRANSITIONS
from app.services.plan_service import get_user_role_in_plan, get_plan_members, can_create_tasks
from app.services.task_service import (
    get_task_by_id,
    get_plan_id_for_task,
    create_task,
    change_task_status,
    assign_task,
    update_task,
    can_edit_task,
)

router = APIRouter(tags=["tasks"])


@router.post("/plans/{plan_id}/tabs/{tab_id}/tasks/new")
async def create_task_route(
    request: Request,
    plan_id: uuid.UUID,
    tab_id: uuid.UUID,
    title: str = Form(...),
    description: str = Form(""),
    assigned_to: str = Form(""),
    priority: str = Form(""),
    due_date: str = Form(""),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_create_tasks(role):
        raise HTTPException(status_code=403)

    assignee_id = uuid.UUID(assigned_to) if assigned_to else None
    parsed_due = None
    if due_date:
        try:
            parsed_due = date.fromisoformat(due_date)
        except ValueError:
            pass

    await create_task(
        db, tab_id, title.strip(), description.strip(),
        user.id, plan_id,
        assigned_to=assignee_id,
        priority=priority or None,
        due_date=parsed_due,
    )
    await db.commit()
    return RedirectResponse(url=f"/plans/{plan_id}", status_code=303)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail(
    request: Request,
    task_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    task = await get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404)

    plan_id = await get_plan_id_for_task(db, task_id)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role:
        raise HTTPException(status_code=404)

    # Direct browser navigation (non-HTMX) gets the full plan page instead of the bare fragment
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=f"/plans/{plan_id}", status_code=303)

    members = await get_plan_members(db, plan_id)
    csrf_token = generate_csrf_token(request)

    # Get valid next statuses for the state machine
    valid_next = VALID_TRANSITIONS.get(task.status, set())

    return templates.TemplateResponse("tasks/detail.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "task": task,
        "plan_id": plan_id,
        "role": role,
        "members": members,
        "can_edit": can_edit_task(role, task, user.id),
        "valid_statuses": valid_next,
        "all_statuses": TaskStatus,
        "all_priorities": TaskPriority,
    })


@router.post("/tasks/{task_id}/status")
async def change_status(
    request: Request,
    task_id: uuid.UUID,
    status: str = Form(...),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    task = await get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404)

    plan_id = await get_plan_id_for_task(db, task_id)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role:
        raise HTTPException(status_code=403)

    if not can_edit_task(role, task, user.id):
        raise HTTPException(status_code=403)

    try:
        new_status = TaskStatus(status)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid status")

    success, error = await change_task_status(db, task, new_status, user.id, plan_id, role)
    if not success:
        raise HTTPException(status_code=422, detail=error)

    await db.commit()

    # Return updated task detail for HTMX swap
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/tasks/{task_id}/assign")
async def assign_task_route(
    request: Request,
    task_id: uuid.UUID,
    assigned_to: str = Form(""),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    task = await get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404)

    plan_id = await get_plan_id_for_task(db, task_id)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_edit_task(role, task, user.id):
        raise HTTPException(status_code=403)

    assignee_id = uuid.UUID(assigned_to) if assigned_to else None
    await assign_task(db, task, assignee_id, user.id, plan_id)
    await db.commit()

    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/tasks/{task_id}/edit")
async def edit_task(
    request: Request,
    task_id: uuid.UUID,
    title: str = Form(...),
    description: str = Form(""),
    percent_complete: int = Form(0),
    priority: str = Form(""),
    due_date: str = Form(""),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    task = await get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404)

    plan_id = await get_plan_id_for_task(db, task_id)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_edit_task(role, task, user.id):
        raise HTTPException(status_code=403)

    parsed_due = None
    if due_date:
        try:
            parsed_due = date.fromisoformat(due_date)
        except ValueError:
            pass

    task_priority = None
    if priority:
        try:
            task_priority = TaskPriority(priority)
        except ValueError:
            pass

    await update_task(
        db, task, user.id, plan_id,
        title=title.strip(),
        description=description.strip(),
        percent_complete=max(0, min(100, percent_complete)),
        priority=task_priority,
        due_date=parsed_due,
    )
    await db.commit()

    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/tasks/{task_id}/delete")
async def delete_task(
    request: Request,
    task_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    task = await get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404)

    plan_id = await get_plan_id_for_task(db, task_id)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or role not in ("owner", "admin"):
        from app.models.plan import PlanRole
        if role not in (PlanRole.owner, PlanRole.admin):
            raise HTTPException(status_code=403)

    await db.delete(task)
    await db.commit()
    return RedirectResponse(url=f"/plans/{plan_id}", status_code=303)
