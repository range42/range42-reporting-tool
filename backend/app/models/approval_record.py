import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class ApprovalRecord(Base, UUIDMixin):
    """One approval/rejection decision on a report (append-only fact).

    Only ``created_at`` — no ``TimestampMixin``/``MetadataMixin`` (a decision is
    never updated). ``step`` is 1-based (``approval_chain[step-1]``); ``step=1`` is
    the single-step default. ``is_admin_override`` marks a Global-Admin approval
    made on behalf of an unavailable approver (WP4 deadlock resolution).
    """

    __tablename__ = "approval_record"
    __table_args__ = (CheckConstraint("action IN ('approved','rejected')", name="ck_approval_record_action"),)

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    is_admin_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
