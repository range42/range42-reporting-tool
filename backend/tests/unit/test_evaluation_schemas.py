from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.evaluation import (
    EvaluationCreate,
    EvaluationUpdate,
    GradableSectionOut,
    RubricScoreEntry,
    SectionGradeOut,
    SectionGradeUpsert,
)
from app.schemas.report import ReportSectionOut

EVALUATOR_ONLY = {
    "grade_mode",
    "grade_min",
    "grade_max",
    "grade_weight",
    "rubric_criteria",
    "evaluation_criteria",
}


def test_evaluation_create_requires_evaluator_id() -> None:
    with pytest.raises(ValidationError):
        EvaluationCreate()


def test_evaluation_create_rejects_aggregated_weight_of_zero() -> None:
    with pytest.raises(ValidationError):
        EvaluationCreate(evaluator_id="u", aggregated_weight=Decimal("0"))


def test_evaluation_create_rejects_aggregated_weight_above_numeric_3_2_capacity() -> None:
    with pytest.raises(ValidationError):
        EvaluationCreate(evaluator_id="u", aggregated_weight=Decimal("10.00"))


def test_evaluation_create_defaults_aggregated_weight_to_one() -> None:
    assert EvaluationCreate(evaluator_id="u").aggregated_weight == Decimal("1.0")


def test_evaluation_update_rejects_explicit_null_overall_feedback() -> None:
    assert EvaluationUpdate().overall_feedback is None
    with pytest.raises(ValidationError):
        EvaluationUpdate(overall_feedback=None)


def test_section_grade_upsert_accepts_numeric_grade_only() -> None:
    body = SectionGradeUpsert(grade=Decimal("7.5"), feedback="ok")
    assert body.grade == Decimal("7.5")
    assert body.pass_fail_result is None
    assert body.rubric_scores is None


def test_section_grade_upsert_rejects_pass_fail_result_and_rubric_scores_together() -> None:
    with pytest.raises(ValidationError):
        SectionGradeUpsert(
            pass_fail_result=True,
            rubric_scores=[RubricScoreEntry(criterion="c", score=Decimal("1"))],
        )


def test_section_grade_upsert_rejects_empty_rubric_scores_list() -> None:
    with pytest.raises(ValidationError):
        SectionGradeUpsert(rubric_scores=[])


def test_rubric_score_entry_requires_criterion_and_score() -> None:
    with pytest.raises(ValidationError):
        RubricScoreEntry(score=Decimal("1"))
    with pytest.raises(ValidationError):
        RubricScoreEntry(criterion="c")
    with pytest.raises(ValidationError):
        RubricScoreEntry(criterion="", score=Decimal("1"))


def test_gradable_section_out_exposes_evaluator_only_template_fields() -> None:
    assert EVALUATOR_ONLY <= set(GradableSectionOut.model_fields)


def test_report_section_out_still_hides_evaluator_only_template_fields() -> None:
    assert EVALUATOR_ONLY.isdisjoint(set(ReportSectionOut.model_fields))


def test_section_grade_out_serializes_grade_as_a_two_decimal_string() -> None:
    now = datetime.now(UTC)
    out = SectionGradeOut(
        id="g",
        evaluation_id="e",
        report_section_id="s",
        grade=Decimal("8.5"),
        pass_fail_result=None,
        rubric_scores=None,
        feedback=None,
        created_at=now,
        updated_at=now,
    )
    assert out.model_dump(mode="json")["grade"] == "8.50"
    ungraded = out.model_copy(update={"grade": None})
    assert ungraded.model_dump(mode="json")["grade"] is None
