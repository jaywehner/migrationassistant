import secrets
from fastapi import Request, HTTPException


CSRF_TOKEN_KEY = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def generate_csrf_token(request: Request) -> str:
    """Generate or retrieve CSRF token from session."""
    token = request.session.get(CSRF_TOKEN_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_TOKEN_KEY] = token
    return token


def validate_csrf_token(request: Request, token: str | None = None) -> bool:
    """Validate CSRF token from form data or header against session."""
    session_token = request.session.get(CSRF_TOKEN_KEY)
    if not session_token:
        return False
    return token == session_token


async def csrf_protect(request: Request) -> None:
    """Middleware-style dependency to validate CSRF on state-changing requests."""
    if request.method in SAFE_METHODS:
        return

    # Check header first (HTMX sends via hx-headers)
    token = request.headers.get(CSRF_HEADER)

    # Fall back to form field
    if not token:
        form = await request.form()
        token = form.get("csrf_token")

    if not validate_csrf_token(request, token):
        raise HTTPException(status_code=403, detail="CSRF token validation failed")
