import uuid
from fastapi import APIRouter, Request, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_auth
from app.middleware.csrf import csrf_protect
from app.models.user import User
from app.models.attachment import Attachment
from app.services.task_service import get_task_by_id, get_plan_id_for_task
from app.services.plan_service import get_user_role_in_plan
from app.services.file_service import (
    validate_file_extension,
    validate_file_size,
    generate_storage_key,
    save_file,
    delete_file,
    get_storage_path,
    get_mime_type,
)
from app.services.audit_service import log_action

router = APIRouter(tags=["attachments"])


@router.post("/tasks/{task_id}/attachments/upload")
async def upload_attachment(
    request: Request,
    task_id: uuid.UUID,
    file: UploadFile = File(...),
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

    # Validate extension
    valid, error = validate_file_extension(file.filename)
    if not valid:
        raise HTTPException(status_code=422, detail=error)

    # Read file data
    data = await file.read()

    # Validate size
    valid, error = validate_file_size(len(data))
    if not valid:
        raise HTTPException(status_code=422, detail=error)

    # Save to storage
    storage_key = generate_storage_key()
    await save_file(storage_key, data)

    # Create DB record
    attachment = Attachment(
        task_id=task_id,
        uploader_id=user.id,
        storage_key=storage_key,
        original_filename=file.filename,
        mime_type=get_mime_type(file.filename),
        size_bytes=len(data),
    )
    db.add(attachment)
    await db.flush()

    await log_action(
        db, plan_id, user.id,
        "attachment", str(attachment.id), "uploaded",
        new_value={"filename": file.filename, "size_bytes": len(data)},
    )
    await db.commit()

    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.get("/attachments/{storage_key}/download")
async def download_attachment(
    request: Request,
    storage_key: str,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Attachment).where(Attachment.storage_key == storage_key)
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404)

    # Verify user has access to the plan
    if attachment.task_id:
        plan_id = await get_plan_id_for_task(db, attachment.task_id)
        role = await get_user_role_in_plan(db, plan_id, user.id)
        if not role:
            raise HTTPException(status_code=403)

    path = get_storage_path(storage_key)
    return FileResponse(
        path,
        media_type=attachment.mime_type,
        filename=attachment.original_filename,
        headers={"Content-Disposition": f'attachment; filename="{attachment.original_filename}"'},
    )


@router.post("/attachments/{attachment_id}/delete")
async def delete_attachment_route(
    request: Request,
    attachment_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await csrf_protect(request)

    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404)

    # Check permission: uploader or admin/owner
    if attachment.task_id:
        plan_id = await get_plan_id_for_task(db, attachment.task_id)
        role = await get_user_role_in_plan(db, plan_id, user.id)
        from app.models.plan import PlanRole
        if attachment.uploader_id != user.id and role not in (PlanRole.owner, PlanRole.admin):
            raise HTTPException(status_code=403)

    delete_file(attachment.storage_key)
    await db.delete(attachment)
    await db.commit()

    task_id = attachment.task_id
    if task_id:
        return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)
    return RedirectResponse(url="/plans", status_code=303)
