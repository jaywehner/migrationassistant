import uuid
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templating import templates
from app.middleware.auth import require_auth
from app.middleware.csrf import generate_csrf_token, csrf_protect
from app.models.user import User
from urllib.parse import quote
from app.models.plan import PlanRole, PlanMember
from app.services.plan_service import (
    get_user_plans,
    get_plan_by_id,
    create_plan,
    get_user_role_in_plan,
    get_plan_members,
    create_invite,
    get_invite_by_token,
    accept_invite,
    remove_member,
    change_member_role,
    can_manage_members,
    can_edit_plan,
)
from app.services.auth_service import get_user_by_email, verify_invite_token, validate_email_address
from app.services.email_service import send_invite_email

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("", response_class=HTMLResponse)
async def plans_list(
    request: Request,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    plans = await get_user_plans(db, user.id)
    csrf_token = generate_csrf_token(request)
    return templates.TemplateResponse("plans/list.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "plans": plans,
    })


@router.get("/new", response_class=HTMLResponse)
async def new_plan_page(request: Request, user: User = Depends(require_auth)):
    csrf_token = generate_csrf_token(request)
    return templates.TemplateResponse("plans/new.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
    })


@router.post("/new")
async def create_plan_submit(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    if not name.strip():
        csrf_token = generate_csrf_token(request)
        return templates.TemplateResponse("plans/new.html", {
            "request": request,
            "current_user": user,
            "csrf_token": csrf_token,
            "errors": ["Plan name is required."],
        })

    plan = await create_plan(db, name.strip(), description.strip(), user)
    await db.commit()
    return RedirectResponse(url=f"/plans/{plan.id}", status_code=303)


@router.get("/{plan_id}", response_class=HTMLResponse)
async def plan_detail(
    request: Request,
    plan_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role:
        raise HTTPException(status_code=404)

    plan = await get_plan_by_id(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404)

    csrf_token = generate_csrf_token(request)
    # Sort tabs by sort_order
    tabs = sorted(plan.tabs, key=lambda t: t.sort_order)
    copy_targets = []
    for target_plan in await get_user_plans(db, user.id):
        if target_plan.id != plan_id:
            target_role = await get_user_role_in_plan(db, target_plan.id, user.id)
            if target_role and can_edit_plan(target_role):
                copy_targets.append(target_plan)
    return templates.TemplateResponse("plans/detail.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "plan": plan,
        "tabs": tabs,
        "role": role,
        "copy_targets": copy_targets,
    })


@router.post("/{plan_id}/edit")
async def edit_plan(
    request: Request,
    plan_id: uuid.UUID,
    name: str = Form(...),
    description: str = Form(""),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_edit_plan(role):
        raise HTTPException(status_code=403)

    plan = await get_plan_by_id(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404)

    name = name.strip()
    if not name:
        return RedirectResponse(
            url=f"/plans/{plan_id}?error={quote('Plan name is required.')}",
            status_code=303,
        )

    plan.name = name
    plan.description = description.strip()
    await db.commit()
    return RedirectResponse(
        url=f"/plans/{plan_id}?success={quote('Plan details updated.')}",
        status_code=303,
    )


@router.get("/{plan_id}/members", response_class=HTMLResponse)
async def plan_members_page(
    request: Request,
    plan_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role:
        raise HTTPException(status_code=404)

    plan = await get_plan_by_id(db, plan_id)
    members = await get_plan_members(db, plan_id)
    csrf_token = generate_csrf_token(request)

    return templates.TemplateResponse("plans/members.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "plan": plan,
        "members": members,
        "role": role,
        "can_manage": can_manage_members(role),
        "roles": [r.value for r in PlanRole if r != PlanRole.owner],
    })


@router.post("/{plan_id}/invite")
async def invite_member(
    request: Request,
    plan_id: uuid.UUID,
    email: str = Form(...),
    invite_role: str = Form("contributor"),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_manage_members(role):
        raise HTTPException(status_code=403)

    email = email.strip()

    email_error = validate_email_address(email)
    if email_error:
        return RedirectResponse(
            url=f"/plans/{plan_id}/members?error={quote(email_error)}",
            status_code=303,
        )

    plan = await get_plan_by_id(db, plan_id)
    try:
        target_role = PlanRole(invite_role)
    except ValueError:
        target_role = PlanRole.contributor

    invite = await create_invite(db, plan_id, email, target_role, user.id)
    await db.commit()
    email_sent = await send_invite_email(email, plan.name, user.display_name, invite.token)
    if email_sent:
        return RedirectResponse(
            url=f"/plans/{plan_id}/members?success={quote(f'Invitation sent to {email}.')}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/plans/{plan_id}/members?error={quote('Invitation was saved, but the email could not be sent. Please check the SMTP settings.')}",
        status_code=303,
    )


@router.post("/{plan_id}/members/add-existing")
async def add_existing_member(
    request: Request,
    plan_id: uuid.UUID,
    email: str = Form(...),
    member_role: str = Form("contributor"),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_manage_members(role):
        raise HTTPException(status_code=403)

    email = email.strip()

    email_error = validate_email_address(email)
    if email_error:
        return RedirectResponse(
            url=f"/plans/{plan_id}/members?error={quote(email_error)}",
            status_code=303,
        )

    target_user = await get_user_by_email(db, email)
    if not target_user:
        return RedirectResponse(
            url=f"/plans/{plan_id}/members?error={quote('No user with that email address was found.')}",
            status_code=303,
        )

    existing_role = await get_user_role_in_plan(db, plan_id, target_user.id)
    if existing_role:
        return RedirectResponse(
            url=f"/plans/{plan_id}/members?error={quote('That user is already a member of this plan.')}",
            status_code=303,
        )

    try:
        target_role = PlanRole(member_role)
    except ValueError:
        target_role = PlanRole.contributor

    db.add(PlanMember(plan_id=plan_id, user_id=target_user.id, role=target_role, invited_by=user.id))
    await db.commit()

    return RedirectResponse(
        url=f"/plans/{plan_id}/members?success={quote(f'{target_user.display_name or email} was added to the plan.')}",
        status_code=303,
    )


@router.post("/{plan_id}/members/{member_id}/remove")
async def remove_plan_member(
    request: Request,
    plan_id: uuid.UUID,
    member_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_manage_members(role):
        raise HTTPException(status_code=403)

    await remove_member(db, plan_id, member_id)
    await db.commit()
    return RedirectResponse(url=f"/plans/{plan_id}/members", status_code=303)


@router.post("/{plan_id}/members/{member_user_id}/role")
async def change_role(
    request: Request,
    plan_id: uuid.UUID,
    member_user_id: uuid.UUID,
    new_role: str = Form(...),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or not can_manage_members(role):
        raise HTTPException(status_code=403)

    try:
        target_role = PlanRole(new_role)
    except ValueError:
        raise HTTPException(status_code=422)

    await change_member_role(db, plan_id, member_user_id, target_role)
    await db.commit()
    return RedirectResponse(url=f"/plans/{plan_id}/members", status_code=303)


@router.post("/{plan_id}/delete")
async def delete_plan(
    request: Request,
    plan_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if role != PlanRole.owner:
        raise HTTPException(status_code=403)

    plan = await get_plan_by_id(db, plan_id)
    if plan:
        await db.delete(plan)
        await db.commit()
    return RedirectResponse(url="/plans", status_code=303)
