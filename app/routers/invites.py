from urllib.parse import quote

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templating import templates
from app.middleware.auth import get_current_user
from app.services.auth_service import verify_invite_token, get_user_by_email
from app.services.plan_service import get_invite_by_token, accept_invite

router = APIRouter(tags=["invites"])


@router.get("/invite/{token}", response_class=HTMLResponse)
async def accept_invite_page(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    # Verify the token signature
    data = verify_invite_token(token)
    if not data:
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "errors": ["This invitation link is invalid or has expired."],
            "csrf_token": "",
            "email": "",
        })

    invite = await get_invite_by_token(db, token)
    if not invite:
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "errors": ["This invitation has already been used or is no longer valid."],
            "csrf_token": "",
            "email": "",
        })

    invite_email = data["email"].lower().strip()
    current_user = await get_current_user(request, db)

    if current_user:
        if current_user.email.lower().strip() != invite_email:
            request.session["invite_token"] = token
            return RedirectResponse(
                url=f"/auth/login?email={quote(invite_email, safe='@.')}&error={quote('This invitation is for a different email address. Please sign in with the invited account.')}",
                status_code=303,
            )

        # Globally read-only users cannot accept invitations (state-changing action)
        if current_user.global_access_level.value == "read_only":
            return templates.TemplateResponse("auth/login.html", {
                "request": request,
                "errors": ["Read-only users cannot accept invitations."],
                "csrf_token": "",
                "email": invite_email,
            })

        # Accept the invite for the matching user
        await accept_invite(db, invite, current_user)
        await db.commit()
        return RedirectResponse(url=f"/plans/{invite.plan_id}", status_code=303)

    # Not logged in: route based on whether the email already has an account
    request.session["invite_token"] = token
    existing_user = await get_user_by_email(db, invite_email)
    if existing_user:
        return RedirectResponse(
            url=f"/auth/login?email={quote(invite_email, safe='@.')}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/auth/register?email={quote(invite_email, safe='@.')}",
        status_code=303,
    )
