import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Evaluation(Base, UUIDMixin, TimestampMixin):
    """One evaluator's assessment of one report (ARCHITECTURE §4.2).

    E1 — evaluator isolation: every read/write path scopes on ``evaluator_id``. There is
    deliberately no peer-visibility flag and no comment table; cross-evaluator discussion
    happens out-of-band.
    """

    # NOTE: no index=True here — indexes are created explicitly in the migration,
    # matching the repo convention (see the note at the top of app/models/report.py).
    __tablename__ = "evaluation"
    __table_args__ = (UniqueConstraint("report_id", "evaluator_id", name="uq_evaluation_report_evaluator"),)

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
    evaluator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="assigned", server_default=text("'assigned'")
    )
    overall_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-evaluator grade. WRITTEN ONLY BY app/services/scoring/rollup.py (A7 sole-writer).
    overall_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # W5-3 reads this for the multi-evaluator aggregate; a rollup input only.
    aggregated_weight: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("1.0"), server_default=text("1.0")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    assigned_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    # --- D2 / E2 deadlock exit (W5-3, migration 0012) -----------------------------------
    # finalized_by is who CLICKED; evaluator_id is who is CREDITED. They differ only on a
    # Global-Admin finalize-on-behalf-of, which also sets finalize_is_admin_override and
    # requires finalize_comment (enforced at the API layer, §9-A5).
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    finalize_is_admin_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    finalize_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Soft unassign (L8): the row stays so the evaluator's section_grade rows and the dispute
    # trail survive. `unassigned_at IS NULL` is the whole L7 "counted" predicate; status is
    # deliberately NOT changed (no 'unassigned' enum value, §9-A3).
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unassigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    unassign_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
