import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class ApprovalSectionRemark(Base, UUIDMixin):
    """One approver's remark on one report section, part of a single approve/reject decision.

    Append-only like its ``ApprovalRecord``: only ``created_at``, never updated.
    """

    __tablename__ = "approval_section_remark"
    __table_args__ = (UniqueConstraint("approval_record_id", "report_section_id", name="uq_approval_section_remark"),)

    approval_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_record.id", ondelete="CASCADE"), nullable=False
    )
    report_section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_section.id", ondelete="CASCADE"), nullable=False
    )
    remark: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
