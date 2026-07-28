"""Section attachments + inline images (WP3 S9, #80).

Uploads are draft-only and follow the section write-lock; the stored
``content_type`` comes from magic-byte sniffing (the client claim is never
trusted — spoofed types get 415); size is capped by ``ATTACHMENT_MAX_BYTES``
(413). Downloads reuse the report read-scoping rules (default-deny) and are
served with ``X-Content-Type-Options: nosniff``; only image types render
inline (they back the TipTap ``<img>`` flow), everything else downloads as an
attachment. Blobs live behind the StorageBackend Protocol (guardrail #2).
"""

import posixpath
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.filesniff import IMAGE_TYPES, sniff
from app.core.permissions import REPORTS_READ_ALL, REPORTS_READ_OWN, REPORTS_WRITE
from app.core.rbac import get_current_user, require_permission, require_permission_any
from app.models import Attachment, Exercise, User
from app.routes.v1.reports import (
    _assert_report_access,
    _assert_section_write_access,
    _get_report,
    _get_report_section,
    _require_draft,
)
from app.schemas.attachment import AttachmentOut
from app.schemas.common import DataEnvelope
from app.storage import StorageBackend, get_storage

router = APIRouter(tags=["attachments"])


async def _get_attachment(db: AsyncSession, report_id: uuid.UUID, aid: uuid.UUID) -> Attachment:
    a = (
        await db.execute(select(Attachment).where(Attachment.id == aid, Attachment.report_id == report_id))
    ).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    return a


@router.post("/exercises/{exercise_id}/reports/{rid}/sections/{sid}/attachments", status_code=201)
async def upload_attachment(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    sid: uuid.UUID,
    file: UploadFile,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission(REPORTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    s: Settings = Depends(get_settings),
) -> DataEnvelope[AttachmentOut]:
    report = await _get_report(db, exercise_id, rid)
    _require_draft(report)
    await _assert_report_access(db, exercise_id, report, user, write=True)
    await _assert_section_write_access(db, exercise_id, report, user)
    section = await _get_report_section(db, rid, sid)

    # Read one byte past the cap so an oversize upload is detected without
    # buffering arbitrarily more than the configured limit.
    data = await file.read(s.attachment_max_bytes + 1)
    if len(data) > s.attachment_max_bytes:
        raise HTTPException(status_code=413, detail="attachment exceeds size limit")

    content_type = sniff(data)
    if content_type is None:
        raise HTTPException(status_code=415, detail="unsupported or spoofed content type")

    exercise = (await db.execute(select(Exercise).where(Exercise.id == exercise_id))).scalar_one()
    attachment = Attachment(
        report_id=report.id,
        section_id=section.id,
        uploaded_by=user.id,
        filename=posixpath.basename(file.filename or "") or "upload",
        content_type=content_type,
        size_bytes=len(data),
        storage_key=f"{exercise_id}/{rid}/{uuid.uuid4().hex}",
        classification=exercise.classification,
    )
    await storage.put(attachment.storage_key, data)
    db.add(attachment)
    await db.flush()
    await db.refresh(attachment)
    await record_audit(
        db,
        user_id=user.id,
        action="attachment.create",
        resource_type="attachment",
        resource_id=attachment.id,
        details={"report_id": str(rid), "filename": attachment.filename, "size_bytes": attachment.size_bytes},
        ip=client_ip(request),
    )
    return DataEnvelope(data=AttachmentOut.from_model(attachment))


@router.get("/exercises/{exercise_id}/reports/{rid}/attachments")
async def list_attachments(
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission_any([REPORTS_READ_OWN, REPORTS_READ_ALL])),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[list[AttachmentOut]]:
    report = await _get_report(db, exercise_id, rid)
    await _assert_report_access(db, exercise_id, report, user, write=False)
    rows = (
        (await db.execute(select(Attachment).where(Attachment.report_id == rid).order_by(Attachment.created_at)))
        .scalars()
        .all()
    )
    return DataEnvelope(data=[AttachmentOut.from_model(a) for a in rows])


@router.get("/exercises/{exercise_id}/reports/{rid}/attachments/{aid}/download")
async def download_attachment(
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    aid: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission_any([REPORTS_READ_OWN, REPORTS_READ_ALL])),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> Response:
    report = await _get_report(db, exercise_id, rid)
    await _assert_report_access(db, exercise_id, report, user, write=False)
    attachment = await _get_attachment(db, rid, aid)
    data = await storage.get(attachment.storage_key)
    disposition = "inline" if attachment.content_type in IMAGE_TYPES else "attachment"
    # The plain filename fallback is forced to ASCII; exotic names survive in the DB.
    ascii_name = attachment.filename.encode("ascii", "replace").decode()
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{ascii_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/exercises/{exercise_id}/reports/{rid}/attachments/{aid}", status_code=204)
async def delete_attachment(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    aid: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission(REPORTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> Response:
    report = await _get_report(db, exercise_id, rid)
    _require_draft(report)
    await _assert_report_access(db, exercise_id, report, user, write=True)
    await _assert_section_write_access(db, exercise_id, report, user)
    attachment = await _get_attachment(db, rid, aid)
    await storage.delete(attachment.storage_key)
    await db.delete(attachment)
    await db.flush()
    await record_audit(
        db,
        user_id=user.id,
        action="attachment.delete",
        resource_type="attachment",
        resource_id=aid,
        details={"report_id": str(rid), "filename": attachment.filename},
        ip=client_ip(request),
    )
    return Response(status_code=204)
