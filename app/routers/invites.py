from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templating import templates
from app.middleware.auth import get_current_user
from app.services.auth_service import verify_invite_token, get_user_by_email
from app.services.plan_service import get_invite_by_token, accept_invite, get_plan_by_id

router = APIRouter(tags=["invites"])


@router.get("/invite/{token}", response_class=HTMLResponse)
async def accept_invite_page(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request, db)

    # Verify the token signature
    data = verify_invite_token(token)
    if not data:
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "errors": ["This invitation link is invalid or has expired."],
            "csrf_token": "",
        })

    invite = await get_invite_by_token(db, token)
    if not invite:
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "errors": ["This invitation has already been used or is no longer valid."],
            "csrf_token": "",
        })

    # If user is not logged in, redirect to login/register with return URL
    if not user:
        request.session["invite_token"] = token
        return RedirectResponse(url="/auth/login", status_code=303)

    # Accept the invite
    plan = await get_plan_by_id(db, invite.plan_id)
    await accept_invite(db, invite, user)
    await db.commit()

    return RedirectResponse(url=f"/plans/{invite.plan_id}", status_code=303)
