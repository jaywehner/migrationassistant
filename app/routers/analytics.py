from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templating import templates
from app.middleware.auth import require_auth
from app.models.user import User
from app.services.analytics_service import get_dashboard_analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_class=HTMLResponse)
async def analytics_dashboard(
    request: Request,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    stats = await get_dashboard_analytics(db, user.id)
    return templates.TemplateResponse("analytics/dashboard.html", {
        "request": request,
        "current_user": user,
        "stats": stats,
    })
