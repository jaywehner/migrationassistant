import uuid
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.templating import templates
from app.middleware.auth import require_auth
from app.middleware.csrf import generate_csrf_token
from app.models.user import User
from app.models.audit import AuditLog
from app.models.plan import PlanRole
from app.services.plan_service import get_user_role_in_plan, get_plan_by_id

router = APIRouter(tags=["admin"])

PAGE_SIZE = 25


@router.get("/plans/{plan_id}/audit", response_class=HTMLResponse)
async def audit_log(
    request: Request,
    plan_id: uuid.UUID,
    page: int = Query(1, ge=1),
    entity_type: str = Query("", alias="type"),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role or role not in (PlanRole.owner, PlanRole.admin):
        raise HTTPException(status_code=403)

    plan = await get_plan_by_id(db, plan_id)

    # Build query
    query = select(AuditLog).where(AuditLog.plan_id == plan_id)
    count_query = select(func.count()).select_from(AuditLog).where(AuditLog.plan_id == plan_id)

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
        count_query = count_query.where(AuditLog.entity_type == entity_type)

    # Total count
    total = (await db.execute(count_query)).scalar()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    # Paginate
    query = (
        query.options(selectinload(AuditLog.actor))
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    )
    result = await db.execute(query)
    entries = list(result.scalars().all())

    csrf_token = generate_csrf_token(request)

    return templates.TemplateResponse("admin/audit_log.html", {
        "request": request,
        "current_user": user,
        "csrf_token": csrf_token,
        "plan": plan,
        "entries": entries,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "entity_type": entity_type,
        "entity_types": ["task", "note", "attachment", "member", "plan", "tab"],
    })
