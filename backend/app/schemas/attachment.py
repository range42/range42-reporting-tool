from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.attachment import Attachment


class AttachmentOut(BaseModel):
    id: str
    report_id: str
    section_id: str
    filename: str
    content_type: str
    size_bytes: int
    classification: str | None
    uploaded_by: str
    created_at: datetime

    @classmethod
    def from_model(cls, a: Attachment) -> AttachmentOut:
        return cls(
            id=str(a.id),
            report_id=str(a.report_id),
            section_id=str(a.section_id),
            filename=a.filename,
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            classification=a.classification,
            uploaded_by=str(a.uploaded_by),
            created_at=a.created_at,
        )
