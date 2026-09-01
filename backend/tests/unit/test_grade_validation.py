"""Unit tests for the L8 grade-mode table — one case per row, plus the boundaries."""

from decimal import Decimal

import pytest

from app.models.template_section_def import TemplateSectionDef
from app.schemas.evaluation import SectionGradeUpsert
from app.services.scoring.grade_validation import (
    INVALID_FOR_MODE,
    NO_RUBRIC_CRITERIA,
    NOT_GRADED,
    GradeValidationError,
    validate_grade_payload,
)

RUBRIC_CRITERIA = [
    {"name": "Clarity", "max_score": 5, "weight": 1},
    {"name": "Depth", "max_score": 10, "weight": 1},
]


def _defn(**kw) -> TemplateSectionDef:
    """A section definition, unpersisted — the validator never touches the DB."""
    return TemplateSectionDef(name="S", field_type="rich_text", **kw)


def _body(**kw) -> SectionGradeUpsert:
    return SectionGradeUpsert(**kw)


def _code(defn, body) -> str:
    with pytest.raises(GradeValidationError) as exc:
        validate_grade_payload(defn, body)
    return exc.value.code


# --- numeric -----------------------------------------------------------------


def test_numeric_returns_the_grade_and_no_other_channel() -> None:
    defn = _defn(grade_mode="numeric", grade_min=0, grade_max=10)
    assert validate_grade_payload(defn, _body(grade=Decimal("7.5"))) == (Decimal("7.5"), None, None)


@pytest.mark.parametrize("value", ["0", "10"])
def test_numeric_bounds_are_inclusive(value: str) -> None:
    defn = _defn(grade_mode="numeric", grade_min=0, grade_max=10)
    grade, _, _ = validate_grade_payload(defn, _body(grade=Decimal(value)))
    assert grade == Decimal(value)


@pytest.mark.parametrize("value", ["-0.01", "10.01"])
def test_numeric_rejects_out_of_range(value: str) -> None:
    defn = _defn(grade_mode="numeric", grade_min=0, grade_max=10)
    assert _code(defn, _body(grade=Decimal(value))) == INVALID_FOR_MODE


def test_numeric_requires_a_grade() -> None:
    defn = _defn(grade_mode="numeric", grade_min=0, grade_max=10)
    assert _code(defn, _body()) == INVALID_FOR_MODE


@pytest.mark.parametrize(
    "extra",
    [{"pass_fail_result": True}, {"rubric_scores": [{"criterion": "Clarity", "score": Decimal("1")}]}],
)
def test_numeric_rejects_other_channels(extra: dict) -> None:
    defn = _defn(grade_mode="numeric", grade_min=0, grade_max=10)
    assert _code(defn, _body(grade=Decimal("5"), **extra)) == INVALID_FOR_MODE


# --- pass_fail ---------------------------------------------------------------


@pytest.mark.parametrize(("result", "stored"), [(True, Decimal("1")), (False, Decimal("0"))])
def test_pass_fail_stores_one_or_zero(result: bool, stored: Decimal) -> None:
    # A4 — 0/1 now; W5-2's rollup applies the grade_max scaling.
    assert validate_grade_payload(_defn(grade_mode="pass_fail"), _body(pass_fail_result=result)) == (
        stored,
        result,
        None,
    )


def test_pass_fail_requires_a_result() -> None:
    assert _code(_defn(grade_mode="pass_fail"), _body()) == INVALID_FOR_MODE


def test_pass_fail_rejects_an_explicit_grade() -> None:
    defn = _defn(grade_mode="pass_fail")
    assert _code(defn, _body(pass_fail_result=True, grade=Decimal("10"))) == INVALID_FOR_MODE


# --- rubric ------------------------------------------------------------------


def test_rubric_returns_scores_and_leaves_grade_null() -> None:
    defn = _defn(grade_mode="rubric", rubric_criteria=RUBRIC_CRITERIA)
    body = _body(rubric_scores=[{"criterion": "Clarity", "score": Decimal("4"), "note": "clear"}])
    grade, pass_fail, scores = validate_grade_payload(defn, body)
    assert grade is None
    assert pass_fail is None
    assert scores == [{"criterion": "Clarity", "score": "4", "note": "clear"}]


def test_rubric_score_equal_to_max_score_is_accepted() -> None:
    defn = _defn(grade_mode="rubric", rubric_criteria=RUBRIC_CRITERIA)
    _, _, scores = validate_grade_payload(defn, _body(rubric_scores=[{"criterion": "Clarity", "score": Decimal("5")}]))
    assert scores == [{"criterion": "Clarity", "score": "5", "note": None}]


@pytest.mark.parametrize(
    "entry",
    [
        {"criterion": "Nonexistent", "score": Decimal("1")},
        {"criterion": "Clarity", "score": Decimal("5.01")},
        {"criterion": "Clarity", "score": Decimal("-1")},
    ],
)
def test_rubric_rejects_unknown_criteria_and_out_of_range_scores(entry: dict) -> None:
    defn = _defn(grade_mode="rubric", rubric_criteria=RUBRIC_CRITERIA)
    assert _code(defn, _body(rubric_scores=[entry])) == INVALID_FOR_MODE


def test_rubric_requires_scores() -> None:
    defn = _defn(grade_mode="rubric", rubric_criteria=RUBRIC_CRITERIA)
    assert _code(defn, _body()) == INVALID_FOR_MODE


def test_rubric_without_criteria_on_the_definition_is_its_own_error() -> None:
    # Edge case 15 — distinguishable from a bad payload so the operator knows the template is wrong.
    defn = _defn(grade_mode="rubric", rubric_criteria=None)
    body = _body(rubric_scores=[{"criterion": "Clarity", "score": Decimal("1")}])
    assert _code(defn, body) == NO_RUBRIC_CRITERIA


def test_rubric_rejects_a_numeric_grade_alongside_scores() -> None:
    defn = _defn(grade_mode="rubric", rubric_criteria=RUBRIC_CRITERIA)
    body = _body(rubric_scores=[{"criterion": "Clarity", "score": Decimal("1")}], grade=Decimal("3"))
    assert _code(defn, body) == INVALID_FOR_MODE


# --- not_graded + unknown ----------------------------------------------------


@pytest.mark.parametrize("body_kw", [{}, {"grade": Decimal("5")}, {"pass_fail_result": True}])
def test_not_graded_never_yields_a_row(body_kw: dict) -> None:
    assert _code(_defn(grade_mode="not_graded"), _body(**body_kw)) == NOT_GRADED


def test_unrecognised_mode_is_rejected_rather_than_crashing() -> None:
    assert _code(_defn(grade_mode="wat"), _body(grade=Decimal("1"))) == INVALID_FOR_MODE


def test_feedback_alone_does_not_satisfy_any_mode() -> None:
    defn = _defn(grade_mode="numeric", grade_min=0, grade_max=10)
    assert _code(defn, _body(feedback="nice")) == INVALID_FOR_MODE
