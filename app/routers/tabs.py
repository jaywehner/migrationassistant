import uuid
from urllib.parse import quote

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.templating import templates
from app.middleware.auth import require_auth
from app.middleware.csrf import generate_csrf_token, csrf_protect
from app.models.user import User
from app.models.tab import ProcessTab
from app.models.task import Task
from app.models.step import TaskStep
from app.models.plan import PlanMember
from app.services.plan_service import get_user_role_in_plan, can_edit_plan, can_create_tasks

router = APIRouter(tags=["tabs"])


@router.post("/plans/{plan_id}/tabs/new")
async def create_tab(
    request: Request,
    plan_id: uuid.UUID,
    name: str = Form(...),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_create_tasks(role):
        raise HTTPException(status_code=403)

    # Get max sort_order
    result = await db.execute(
        select(ProcessTab.sort_order)
        .where(ProcessTab.plan_id == plan_id)
        .order_by(ProcessTab.sort_order.desc())
        .limit(1)
    )
    max_order = result.scalar_one_or_none() or 0

    tab = ProcessTab(plan_id=plan_id, name=name.strip(), sort_order=max_order + 1)
    db.add(tab)
    await db.commit()

    return RedirectResponse(url=f"/plans/{plan_id}", status_code=303)


@router.post("/plans/{plan_id}/tabs/{tab_id}/copy")
async def copy_tab(
    request: Request,
    plan_id: uuid.UUID,
    tab_id: uuid.UUID,
    target_plan_id: uuid.UUID = Form(...),
    conflict_action: str = Form("rename"),
    new_name: str = Form(""),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    source_role = await get_user_role_in_plan(db, plan_id, user.id)
    target_role = await get_user_role_in_plan(db, target_plan_id, user.id)
    if not source_role or not can_edit_plan(source_role):
        raise HTTPException(status_code=403)
    if not target_role or not can_edit_plan(target_role) or target_plan_id == plan_id:
        raise HTTPException(status_code=403)

    result = await db.execute(
        select(ProcessTab)
        .where(ProcessTab.id == tab_id, ProcessTab.plan_id == plan_id)
        .options(selectinload(ProcessTab.tasks).selectinload(Task.steps))
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404)

    result = await db.execute(
        select(ProcessTab).where(
            ProcessTab.plan_id == target_plan_id,
            func.lower(ProcessTab.name) == source.name.lower(),
        )
    )
    existing = result.scalars().first()
    copied_name = source.name
    if existing:
        if conflict_action == "replace":
            await db.delete(existing)
            await db.flush()
        elif conflict_action == "rename" and new_name.strip():
            copied_name = new_name.strip()
            duplicate = await db.execute(
                select(ProcessTab.id).where(
                    ProcessTab.plan_id == target_plan_id,
                    func.lower(ProcessTab.name) == copied_name.lower(),
                )
            )
            if duplicate.scalar_one_or_none():
                return RedirectResponse(
                    url=f"/plans/{plan_id}?tab={tab_id}&error={quote('A process with the new name already exists in the target plan.')}",
                    status_code=303,
                )
        else:
            return RedirectResponse(
                url=f"/plans/{plan_id}?tab={tab_id}&error={quote('Choose Replace or provide a new process name.')}",
                status_code=303,
            )

    max_order = (await db.execute(
        select(ProcessTab.sort_order)
        .where(ProcessTab.plan_id == target_plan_id)
        .order_by(ProcessTab.sort_order.desc())
        .limit(1)
    )).scalar_one_or_none() or 0
    copied_tab = ProcessTab(plan_id=target_plan_id, name=copied_name, sort_order=max_order + 1)
    db.add(copied_tab)
    await db.flush()

    target_member_ids = set((await db.execute(
        select(PlanMember.user_id).where(PlanMember.plan_id == target_plan_id)
    )).scalars().all())
    for source_task in source.tasks:
        copied_task = Task(
            tab_id=copied_tab.id,
            title=source_task.title,
            description=source_task.description,
            status=source_task.status,
            percent_complete=source_task.percent_complete,
            priority=source_task.priority,
            due_date=source_task.due_date,
            position=source_task.position,
            assigned_to=source_task.assigned_to if source_task.assigned_to in target_member_ids else None,
            created_by=user.id,
        )
        db.add(copied_task)
        await db.flush()
        for source_step in source_task.steps:
            db.add(TaskStep(
                task_id=copied_task.id,
                title=source_step.title,
                code=source_step.code,
                position=source_step.position,
                is_done=source_step.is_done,
            ))

    await db.commit()
    return RedirectResponse(
        url=f"/plans/{target_plan_id}?tab={copied_tab.id}&success={quote('Process copied successfully.')}",
        status_code=303,
    )


@router.post("/plans/{plan_id}/tabs/{tab_id}/rename")
async def rename_tab(
    request: Request,
    plan_id: uuid.UUID,
    tab_id: uuid.UUID,
    name: str = Form(...),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_edit_plan(role):
        raise HTTPException(status_code=403)

    result = await db.execute(select(ProcessTab).where(ProcessTab.id == tab_id, ProcessTab.plan_id == plan_id))
    tab = result.scalar_one_or_none()
    if not tab:
        raise HTTPException(status_code=404)

    tab.name = name.strip()
    await db.commit()
    return RedirectResponse(url=f"/plans/{plan_id}", status_code=303)


@router.post("/plans/{plan_id}/tabs/{tab_id}/delete")
async def delete_tab(
    request: Request,
    plan_id: uuid.UUID,
    tab_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_edit_plan(role):
        raise HTTPException(status_code=403)

    result = await db.execute(select(ProcessTab).where(ProcessTab.id == tab_id, ProcessTab.plan_id == plan_id))
    tab = result.scalar_one_or_none()
    if tab:
        await db.delete(tab)
        await db.commit()
    return RedirectResponse(url=f"/plans/{plan_id}", status_code=303)


@router.post("/plans/{plan_id}/tabs/reorder")
async def reorder_tabs(
    request: Request,
    plan_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_edit_plan(role):
        raise HTTPException(status_code=403)

    body = await request.json()
    order = body.get("order", [])

    for idx, tab_id in enumerate(order):
        await db.execute(
            update(ProcessTab)
            .where(ProcessTab.id == uuid.UUID(tab_id), ProcessTab.plan_id == plan_id)
            .values(sort_order=idx)
        )
    await db.commit()
    return {"ok": True}


@router.get("/plans/{plan_id}/tabs/{tab_id}/tasks", response_class=HTMLResponse)
async def tab_tasks(
    request: Request,
    plan_id: uuid.UUID,
    tab_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Return the task list partial for a specific tab (loaded via HTMX)."""
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role:
        raise HTTPException(status_code=404)

    result = await db.execute(
        select(ProcessTab)
        .where(ProcessTab.id == tab_id, ProcessTab.plan_id == plan_id)
        .options(selectinload(ProcessTab.tasks))
    )
    tab = result.scalar_one_or_none()
    if not tab:
        raise HTTPException(status_code=404)

    from app.services.plan_service import can_create_tasks, get_plan_members
    members = await get_plan_members(db, plan_id)
    csrf_token = generate_csrf_token(request)

    return templates.TemplateResponse("tasks/list.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "plan_id": plan_id,
        "tab": tab,
        "tasks": tab.tasks,
        "role": role,
        "can_create": can_create_tasks(role),
        "members": members,
    })
