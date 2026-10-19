from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templating import templates
from app.middleware.auth import require_auth
from app.models.user import User

router = APIRouter(prefix="/wiki", tags=["wiki"])


@router.get("", response_class=HTMLResponse)
async def wiki_index(
    request: Request,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    return templates.TemplateResponse("wiki/index.html", {
        "request": request,
        "current_user": user,
    })
