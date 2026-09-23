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
from app.models.tab import ProcessTab
from sqlalchemy import select
from app.services.plan_service import get_user_role_in_plan, get_plan_members, can_create_tasks
from app.services.task_service import (
    get_task_by_id,
    get_plan_id_for_task,
    create_task,
    copy_task,
    change_task_status,
    assign_task,
    update_task,
    can_edit_task,
    create_step,
    get_step_by_id,
    delete_step,
    toggle_step,
    update_step,
    reorder_steps,
    reorder_tasks,
    sanitize_step_html,
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
    if assignee_id and not await get_user_role_in_plan(db, plan_id, assignee_id):
        raise HTTPException(status_code=422, detail="Assignee must be a member of this plan")

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
    return RedirectResponse(url=f"/plans/{plan_id}?tab={tab_id}", status_code=303)


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
    if assignee_id and not await get_user_role_in_plan(db, plan_id, assignee_id):
        raise HTTPException(status_code=422, detail="Assignee must be a member of this plan")

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
    if not role or not can_create_tasks(role):
        raise HTTPException(status_code=403)

    tab_id = task.tab_id
    await db.delete(task)
    await db.commit()
    return RedirectResponse(url=f"/plans/{plan_id}?tab={tab_id}", status_code=303)


@router.post("/tasks/{task_id}/copy")
async def copy_task_route(
    request: Request,
    task_id: uuid.UUID,
    target_tab_id: str = Form(...),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    task = await get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404)

    plan_id = await get_plan_id_for_task(db, task_id)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_create_tasks(role):
        raise HTTPException(status_code=403)

    try:
        target_tab_uuid = uuid.UUID(target_tab_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid target tab")

    tab_result = await db.execute(
        select(ProcessTab).where(ProcessTab.id == target_tab_uuid, ProcessTab.plan_id == plan_id)
    )
    target_tab = tab_result.scalar_one_or_none()
    if not target_tab:
        raise HTTPException(status_code=422, detail="Target tab must be in the same plan")

    await copy_task(db, task, target_tab_uuid, user.id, plan_id)
    await db.commit()
    return RedirectResponse(url=f"/plans/{plan_id}?tab={target_tab_uuid}&success=Task+copied", status_code=303)


@router.post("/tasks/{task_id}/steps/new")
async def create_step_route(
    request: Request,
    task_id: uuid.UUID,
    title: str = Form(...),
    code: str = Form(""),
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

    clean_title = sanitize_step_html(title)
    if not clean_title:
        raise HTTPException(status_code=422, detail="Step title is required")

    await create_step(db, task, clean_title, code, user.id, plan_id)
    await db.commit()
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/tasks/{task_id}/steps/{step_id}/delete")
async def delete_step_route(
    request: Request,
    task_id: uuid.UUID,
    step_id: uuid.UUID,
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

    step = await get_step_by_id(db, step_id)
    if not step or step.task_id != task_id:
        raise HTTPException(status_code=404)

    await delete_step(db, step, task, user.id, plan_id)
    await db.commit()
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/tasks/{task_id}/steps/{step_id}/toggle")
async def toggle_step_route(
    request: Request,
    task_id: uuid.UUID,
    step_id: uuid.UUID,
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

    step = await get_step_by_id(db, step_id)
    if not step or step.task_id != task_id:
        raise HTTPException(status_code=404)

    await toggle_step(db, step, task)
    await db.commit()
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/tasks/{task_id}/steps/{step_id}/edit")
async def edit_step_route(
    request: Request,
    task_id: uuid.UUID,
    step_id: uuid.UUID,
    title: str = Form(...),
    code: str = Form(""),
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

    step = await get_step_by_id(db, step_id)
    if not step or step.task_id != task_id:
        raise HTTPException(status_code=404)

    clean_title = sanitize_step_html(title)
    if not clean_title:
        raise HTTPException(status_code=422, detail="Step title is required")

    await update_step(db, step, task, clean_title, code, user.id, plan_id)
    await db.commit()
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/tasks/{task_id}/steps/reorder")
async def reorder_steps_route(
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
    if not role or not can_edit_task(role, task, user.id):
        raise HTTPException(status_code=403)

    body = await request.json()
    order = body.get("order", [])

    step_ids = []
    for sid in order:
        try:
            step_ids.append(uuid.UUID(sid))
        except ValueError:
            pass

    await reorder_steps(db, task, step_ids, user.id, plan_id)
    await db.commit()
    return {"status": "ok"}


@router.post("/plans/{plan_id}/tabs/{tab_id}/tasks/reorder")
async def reorder_tasks_route(
    request: Request,
    plan_id: uuid.UUID,
    tab_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_create_tasks(role):
        raise HTTPException(status_code=403)

    body = await request.json()
    order = body.get("order", [])

    task_ids = []
    for tid in order:
        try:
            task_ids.append(uuid.UUID(tid))
        except ValueError:
            pass

    await reorder_tasks(db, tab_id, task_ids, user.id, plan_id)
    await db.commit()
    return {"status": "ok"}
