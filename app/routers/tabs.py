import uuid
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.templating import templates
from app.middleware.auth import require_auth
from app.middleware.csrf import generate_csrf_token, csrf_protect
from app.models.user import User
from app.models.tab import ProcessTab
from app.models.plan import PlanRole
from app.services.plan_service import get_user_role_in_plan, can_edit_plan

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
    if not role or not can_edit_plan(role):
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
