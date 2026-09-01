import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, MetadataMixin, TimestampMixin, UUIDMixin


class Report(Base, UUIDMixin, TimestampMixin, MetadataMixin):
    __tablename__ = "report"

    # NOTE: no index=True here — indexes are created explicitly in the migration (Task 3),
    # matching the repo convention (ReportTemplate/TemplateSectionDef). index=True would make
    # Alembic autogenerate a second, conflicting index.
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercise.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_template.id", ondelete="RESTRICT"), nullable=False
    )
    template_version_at_creation: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default=text("'draft'"))
    approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Ordered multi-step chain: [{role_key|user_id, required: bool}, ...].
    # NULL or single-entry = single-step default (WP4 / ARCHITECTURE §7).
    approval_chain: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    writer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A7 sole-writer: app/services/scoring/rollup.py. No other code path may set these two.
    overall_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    overall_grade_is_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # E3: monotonic publish counter, incremented by rollup.py in the grade-save transaction.
    # Never decreases; NOT incremented while overall_grade_is_manual suppresses recomputation.
    grade_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    assigned_writer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
