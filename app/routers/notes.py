import uuid
import markdown
import bleach
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_auth
from app.middleware.csrf import csrf_protect
from app.models.user import User
from app.models.note import TaskNote
from app.services.task_service import get_task_by_id, get_plan_id_for_task
from app.services.plan_service import get_user_role_in_plan
from app.services.audit_service import log_action

router = APIRouter(tags=["notes"])

# Bleach allowlist for sanitized Markdown HTML
ALLOWED_TAGS = [
    "p", "br", "strong", "em", "b", "i", "u", "s",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "a", "code", "pre", "blockquote",
    "table", "thead", "tbody", "tr", "th", "td",
    "img", "hr",
]
ALLOWED_ATTRS = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
}


def render_markdown(text: str) -> str:
    """Render Markdown to sanitized HTML."""
    raw_html = markdown.markdown(text, extensions=["tables", "fenced_code"])
    return bleach.clean(raw_html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)


@router.post("/tasks/{task_id}/notes/new")
async def add_note(
    request: Request,
    task_id: uuid.UUID,
    body: str = Form(...),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)
    task = await get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404)

    plan_id = await get_plan_id_for_task(db, task_id)
    role = await get_user_role_in_plan(db, plan_id, user.id)
    if not role:
        raise HTTPException(status_code=403)

    # All plan members can add notes (even viewers can add notes per spec)
    note = TaskNote(
        task_id=task_id,
        author_id=user.id,
        body=body.strip(),
    )
    db.add(note)
    await db.flush()

    await log_action(
        db, plan_id, user.id,
        "note", str(note.id), "created",
        new_value={"task_id": str(task_id), "body_preview": body[:100]},
    )
    await db.commit()

    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)
