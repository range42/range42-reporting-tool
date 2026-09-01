import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class SectionGrade(Base, UUIDMixin, TimestampMixin):
    """Per-section grade + feedback from one evaluator (ARCHITECTURE §4.2).

    No row is ever created for a section whose source ``template_section_def.grade_mode``
    is ``not_graded`` — §7.2's finalize condition and §4.2's rollup rule both key off the
    row's absence.
    """

    # NOTE: no index=True — indexes are created explicitly in the migration (repo convention).
    __tablename__ = "section_grade"
    __table_args__ = (UniqueConstraint("evaluation_id", "report_section_id", name="uq_section_grade_eval_section"),)

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation.id", ondelete="CASCADE"), nullable=False
    )
    # CASCADE, not RESTRICT: report_section already cascades from report and so does evaluation —
    # a report delete must not be blocked by grade rows. Deviates from the "…_section_id → RESTRICT"
    # convention on purpose; called out in the W5-1 plan for review.
    report_section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_section.id", ondelete="CASCADE"), nullable=False
    )
    grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    pass_fail_result: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # none_as_null: a Python None must write SQL NULL, not JSONB 'null'. ck_section_grade_shape
    # reads "rubric_scores IS NULL", which a JSON null does not satisfy — switching a row from
    # rubric to pass_fail grading would otherwise trip the constraint.
    rubric_scores: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    graded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
