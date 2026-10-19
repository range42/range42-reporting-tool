"""Per-section remarks attached to an approve/reject decision."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApprovalRecord, ApprovalSectionRemark, ReportSection
from app.schemas.report import ApprovalWithRemarks, SectionRemarkIn


class SectionRemarkError(Exception):
    """A remark payload that cannot be stored; ``code`` is the client-facing error key."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def check_section_remarks(db: AsyncSession, report_id: uuid.UUID, remarks: Sequence[SectionRemarkIn]) -> None:
    """Raise :class:`SectionRemarkError` unless every remark targets a distinct section of the report."""
    if not remarks:
        return
    seen: set[uuid.UUID] = set()
    for item in remarks:
        if item.report_section_id in seen:
            raise SectionRemarkError("duplicate_section_remark")
        seen.add(item.report_section_id)
    owned = set(
        (
            await db.execute(
                select(ReportSection.id).where(ReportSection.report_id == report_id, ReportSection.id.in_(seen))
            )
        )
        .scalars()
        .all()
    )
    if owned != seen:
        raise SectionRemarkError("section_not_found")


def add_section_remarks(db: AsyncSession, record: ApprovalRecord, remarks: Sequence[SectionRemarkIn]) -> None:
    """Stage one row per remark against an already-flushed ``record``. Call after :func:`check_section_remarks`."""
    db.add_all(
        ApprovalSectionRemark(
            approval_record_id=record.id, report_section_id=item.report_section_id, remark=item.remark
        )
        for item in remarks
    )


async def with_remarks(db: AsyncSession, records: Sequence[ApprovalRecord]) -> list[ApprovalWithRemarks]:
    """Pair each record with its remarks, in one query, keeping the records' order."""
    if not records:
        return []
    rows = (
        (
            await db.execute(
                select(ApprovalSectionRemark)
                .where(ApprovalSectionRemark.approval_record_id.in_([r.id for r in records]))
                .order_by(ApprovalSectionRemark.created_at, ApprovalSectionRemark.id)
            )
        )
        .scalars()
        .all()
    )
    by_record: dict[uuid.UUID, list[ApprovalSectionRemark]] = {}
    for row in rows:
        by_record.setdefault(row.approval_record_id, []).append(row)
    return [(r, tuple(by_record.get(r.id, ()))) for r in records]
