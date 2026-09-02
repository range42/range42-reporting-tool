import pytest
from pydantic import ValidationError

from app.schemas.template import SectionCreate, TemplateBundle, section_invariant_error


def _rich(**kw: object) -> dict[str, object]:
    base = {"name": "S", "field_type": "rich_text", "grade_mode": "not_graded"}
    base.update(kw)
    return base


def test_rich_text_section_ok() -> None:
    s = SectionCreate(**_rich(char_limit=1500))
    assert s.field_type == "rich_text"


def test_choice_requires_config() -> None:
    with pytest.raises(ValidationError):
        SectionCreate(**_rich(field_type="choice", choice_config=None))


def test_numeric_requires_min_lt_max() -> None:
    assert (
        section_invariant_error(
            field_type="rich_text",
            char_limit=None,
            choice_config=None,
            grade_mode="numeric",
            grade_min=5.0,
            grade_max=3.0,
            rubric_criteria=None,
            grade_weight=1.0,
        )
        is not None
    )


def test_choice_rejects_char_limit() -> None:
    choice_cfg = {
        "selection": "single",
        "values": [{"code": "a", "label": "A", "position": 0, "deprecated_at": None}],
    }
    err = section_invariant_error(
        field_type="choice",
        char_limit=10,
        choice_config=choice_cfg,
        grade_mode="not_graded",
        grade_min=None,
        grade_max=None,
        rubric_criteria=None,
        grade_weight=1.0,
    )
    assert err is not None


def test_choice_duplicate_codes_rejected() -> None:
    err = section_invariant_error(
        field_type="choice",
        char_limit=None,
        choice_config={
            "selection": "single",
            "values": [
                {"code": "a", "label": "A", "position": 0, "deprecated_at": None},
                {"code": "a", "label": "B", "position": 1, "deprecated_at": None},
            ],
        },
        grade_mode="not_graded",
        grade_min=None,
        grade_max=None,
        rubric_criteria=None,
        grade_weight=1.0,
    )
    assert err is not None


def test_valid_choice_returns_none() -> None:
    assert (
        section_invariant_error(
            field_type="choice",
            char_limit=None,
            choice_config={
                "selection": "multiple",
                "values": [{"code": "a", "label": "A", "position": 0, "deprecated_at": None}],
            },
            grade_mode="not_graded",
            grade_min=None,
            grade_max=None,
            rubric_criteria=None,
            grade_weight=1.0,
        )
        is None
    )


def test_rubric_criterion_bounds_rejected() -> None:
    assert (
        section_invariant_error(
            field_type="rich_text",
            char_limit=None,
            choice_config=None,
            grade_mode="rubric",
            grade_min=None,
            grade_max=None,
            rubric_criteria=[{"name": "C", "weight": 1.0, "max_score": 0}],
            grade_weight=1.0,
        )
        is not None
    )


def _pass_fail(**kw) -> str | None:
    base = dict(
        field_type="rich_text",
        char_limit=None,
        choice_config=None,
        grade_mode="pass_fail",
        grade_min=None,
        grade_max=None,
        rubric_criteria=None,
        grade_weight=1.0,
    )
    return section_invariant_error(**{**base, **kw})


def test_pass_fail_without_bounds_is_valid() -> None:
    # Sections authored before bounds were allowed carry neither; they stay valid and scale
    # onto [0, 1] at rollup.
    assert _pass_fail() is None


def test_pass_fail_with_both_bounds_is_valid() -> None:
    # Declares what a pass is worth, so it can sit on a mixed template beside numeric sections.
    assert _pass_fail(grade_min=0.0, grade_max=10.0) is None


def test_pass_fail_with_only_grade_min_rejected() -> None:
    assert _pass_fail(grade_min=0.0) is not None


def test_pass_fail_with_only_grade_max_rejected() -> None:
    assert _pass_fail(grade_max=10.0) is not None


def test_pass_fail_with_inverted_bounds_rejected() -> None:
    assert _pass_fail(grade_min=10.0, grade_max=0.0) is not None


def test_pass_fail_with_equal_bounds_rejected() -> None:
    assert _pass_fail(grade_min=5.0, grade_max=5.0) is not None


def test_pass_fail_with_rubric_criteria_rejected() -> None:
    assert _pass_fail(rubric_criteria=[{"name": "C", "weight": 1.0, "max_score": 5}]) is not None


def test_not_graded_with_rubric_rejected() -> None:
    assert (
        section_invariant_error(
            field_type="rich_text",
            char_limit=None,
            choice_config=None,
            grade_mode="not_graded",
            grade_min=None,
            grade_max=None,
            rubric_criteria=[{"name": "C", "weight": 1.0, "max_score": 10}],
            grade_weight=1.0,
        )
        is not None
    )


def test_bundle_schema_version() -> None:
    b = TemplateBundle(schema_version=1, name="T", report_type="spot", description=None, sections=[])
    assert b.schema_version == 1
    with pytest.raises(ValidationError):
        TemplateBundle(schema_version=2, name="T", report_type="spot", description=None, sections=[])
