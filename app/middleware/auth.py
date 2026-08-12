import uuid
from fastapi import Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_user_by_id


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    """Get the current user from session. Returns None if not authenticated."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None
    user = await get_user_by_id(db, uid)
    if user and user.is_active:
        return user
    return None


async def require_auth(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Dependency that requires authentication. Redirects to login if not authenticated."""
    user = await get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user
