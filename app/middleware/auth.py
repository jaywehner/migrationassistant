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
    """Dependency that requires authentication. Redirects to login if not authenticated.
    Globally read-only users are blocked from state-changing requests.
    """
    user = await get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    if request.method not in ("GET", "HEAD", "OPTIONS") and user.global_access_level.value == "read_only":
        raise HTTPException(status_code=403, detail="Read-only users cannot modify data")
    return user


async def require_global_admin(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Dependency that requires global admin access."""
    user = await require_auth(request, db)
    if not user.is_global_admin or user.global_access_level.value != "admin":
        raise HTTPException(status_code=403)
    return user


def require_global_write_access(request: Request) -> None:
    """Rejects state-changing requests from globally read-only users."""
    user = request.scope.get("user")
    if user and user.global_access_level.value == "read_only" and request.method not in ("GET", "HEAD", "OPTIONS"):
        raise HTTPException(status_code=403, detail="Read-only users cannot modify data")


async def load_current_user_into_scope(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Dependency that attaches the current user to request.scope['user'].
    Use this on routes where require_global_write_access needs the user object.
    """
    user = await get_current_user(request, db)
    request.scope["user"] = user
    return user
