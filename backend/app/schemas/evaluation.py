from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from app.models.evaluation import Evaluation
from app.models.report_section import ReportSection
from app.models.section_grade import SectionGrade
from app.models.template_section_def import TemplateSectionDef
from app.schemas.domain import _reject_null

KNOWN_EVALUATION_STATUSES = ("assigned", "in_progress", "completed")


def _dec(v: float | Decimal | None) -> Decimal | None:
    """Float column -> Decimal without binary-float artefacts (grade_* are Float in the DB)."""
    return None if v is None else Decimal(str(v))


class EvaluationCreate(BaseModel):
    evaluator_id: str
    # NUMERIC(3,2) tops out at 9.99; the DB CHECK also requires > 0.
    aggregated_weight: Decimal = Field(default=Decimal("1.0"), gt=0, le=Decimal("9.99"))


class EvaluationUpdate(BaseModel):
    overall_feedback: str | None = None

    _no_null = field_validator("overall_feedback")(_reject_null)


class RubricScoreEntry(BaseModel):
    criterion: str = Field(min_length=1)
    score: Decimal
    note: str | None = None


class SectionGradeUpsert(BaseModel):
    """One grading channel per row (§4.2).

    WHICH channel is legal depends on the source section's ``grade_mode``; that check needs
    the DB and therefore lives at the route layer (L8). Here we only forbid the combination
    the DB backstop ``ck_section_grade_shape`` also refuses.
    """

    grade: Decimal | None = None
    pass_fail_result: bool | None = None
    rubric_scores: list[RubricScoreEntry] | None = None
    feedback: str | None = None

    @field_validator("rubric_scores")
    @classmethod
    def _no_empty_rubric(cls, v: list[RubricScoreEntry] | None) -> list[RubricScoreEntry] | None:
        if v is not None and len(v) == 0:
            raise ValueError("rubric_scores must be a non-empty list or null")
        return v

    @model_validator(mode="after")
    def _at_most_one_non_numeric_channel(self) -> SectionGradeUpsert:
        if self.pass_fail_result is not None and self.rubric_scores is not None:
            raise ValueError("pass_fail_result and rubric_scores are mutually exclusive")
        return self


class SectionGradeOut(BaseModel):
    id: str
    evaluation_id: str
    report_section_id: str
    grade: Decimal | None
    pass_fail_result: bool | None
    rubric_scores: list[dict[str, Any]] | None
    feedback: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("grade")
    def _two_dp(self, v: Decimal | None) -> str | None:
        """Pin NUMERIC(5,2) to one wire form so W5-2 and the frontend agree."""
        return None if v is None else f"{v:.2f}"

    @classmethod
    def from_model(cls, g: SectionGrade) -> SectionGradeOut:
        return cls(
            id=str(g.id),
            evaluation_id=str(g.evaluation_id),
            report_section_id=str(g.report_section_id),
            grade=g.grade,
            pass_fail_result=g.pass_fail_result,
            rubric_scores=g.rubric_scores,
            feedback=g.feedback,
            created_at=g.created_at,
            updated_at=g.updated_at,
        )


class GradableSectionOut(BaseModel):
    """Evaluator-facing section view — the ONLY place the evaluator-only template fields are
    exposed (L12). Never merge these into ``ReportSectionOut``."""

    report_section_id: str
    section_def_id: str
    name: str
    description: str | None
    position: int
    field_type: str
    content: str | None
    content_plain: str | None
    choice_values: list[str] | None
    grade_mode: str
    # Nullable in the DB: template_section_def.grade_min/grade_max are Float NULL-able and are
    # unset for not_graded / pass_fail sections.
    grade_min: Decimal | None
    grade_max: Decimal | None
    grade_weight: Decimal
    rubric_criteria: list[dict[str, Any]] | None
    # Free text in the DB (Text column), not structured JSON.
    evaluation_criteria: str | None
    grade: SectionGradeOut | None

    @classmethod
    def from_models(
        cls,
        s: ReportSection,
        d: TemplateSectionDef,
        grade: SectionGrade | None = None,
    ) -> GradableSectionOut:
        weight = _dec(d.grade_weight)
        return cls(
            report_section_id=str(s.id),
            section_def_id=str(s.section_def_id),
            name=d.name,
            description=d.description,
            position=s.position,
            field_type=d.field_type,
            content=s.content,
            content_plain=s.content_plain,
            choice_values=s.choice_values,
            grade_mode=d.grade_mode,
            grade_min=_dec(d.grade_min),
            grade_max=_dec(d.grade_max),
            grade_weight=weight if weight is not None else Decimal("1.0"),
            rubric_criteria=d.rubric_criteria,
            evaluation_criteria=d.evaluation_criteria,
            grade=SectionGradeOut.from_model(grade) if grade is not None else None,
        )


class EvaluationOut(BaseModel):
    id: str
    report_id: str
    evaluator_id: str
    status: str
    overall_feedback: str | None
    # A7 sole-writer: rollup.py computes this; no route sets it directly.
    overall_grade: Decimal | None
    completed_at: datetime | None
    reopen_count: int
    graded_section_count: int
    gradable_section_count: int
    created_at: datetime
    updated_at: datetime

    # aggregated_weight is deliberately absent (L11): admin-only, surfaced by W5-3's breakdown.

    @classmethod
    def from_model(cls, e: Evaluation, *, graded: int, gradable: int) -> EvaluationOut:
        return cls(
            id=str(e.id),
            report_id=str(e.report_id),
            evaluator_id=str(e.evaluator_id),
            status=e.status,
            overall_feedback=e.overall_feedback,
            overall_grade=e.overall_grade,
            completed_at=e.completed_at,
            reopen_count=e.reopen_count,
            graded_section_count=graded,
            gradable_section_count=gradable,
            created_at=e.created_at,
            updated_at=e.updated_at,
        )


class EvaluationDetailOut(EvaluationOut):
    report_name: str
    report_status: str
    # E3 — exposed so a client can detect that a reopen invalidated published numbers.
    grade_version: int
    sections: list[GradableSectionOut]


class ManualGradeRequest(BaseModel):
    """Body of ``PUT .../reports/{rid}/overall-grade`` (M9).

    ``overall_grade=None`` clears the override and hands the number back to the rollup.
    ``reason`` is mandatory and lands in the audit row — the §6.8 reopen precedent.
    The bounds mirror ``report.overall_grade``'s NUMERIC(5,2): anything the column could not
    store is refused here, with the caller's own digits, instead of surfacing as a DB error.
    """

    overall_grade: Decimal | None = Field(default=None, ge=0, max_digits=5, decimal_places=2)
    reason: str = Field(min_length=1)


class ReportGradeOut(BaseModel):
    """The report-level grade state after a manual set/clear — what the M9 route returns."""

    report_id: str
    overall_grade: Decimal | None
    overall_grade_is_manual: bool
    grade_version: int

    @field_serializer("overall_grade")
    def _two_dp(self, v: Decimal | None) -> str | None:
        return None if v is None else f"{v:.2f}"
