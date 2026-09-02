"""Task 1 — the per-section value that feeds the rollup.

``None`` is the load-bearing return value: it means EXCLUDED FROM BOTH the numerator and the
weight denominator (§4.2), which is what M4 (``not_graded``) and M5 (gradable but ungraded)
both require. Returning 0 instead would silently drag every average down.
"""

from decimal import Decimal

import pytest

from app.services.scoring.rollup import SectionGradeInput, compute_section_value


def _section(**kw) -> SectionGradeInput:
    base = dict(
        section_def_id="s1",
        name="Executive Summary",
        grade_mode="numeric",
        grade=Decimal("8.5"),
        grade_min=Decimal("0"),
        grade_max=Decimal("10"),
        grade_weight=Decimal("1.0"),
    )
    return SectionGradeInput(**{**base, **kw})


def test_section_value_for_numeric_mode_returns_the_stored_grade() -> None:
    assert compute_section_value(_section(grade=Decimal("7.25"))) == Decimal("7.25")


def test_section_value_for_numeric_mode_with_null_grade_returns_none() -> None:
    # M5 — gradable but not yet graded: excluded from both sides, not scored zero.
    assert compute_section_value(_section(grade=None)) is None


def test_section_value_for_not_graded_mode_returns_none() -> None:
    # M4 — the section contributes nothing at all.
    assert compute_section_value(_section(grade_mode="not_graded", grade=None)) is None


def test_section_value_for_not_graded_mode_ignores_a_stray_stored_grade() -> None:
    # M4 belt-and-braces: no section_grade row should exist for a not_graded section, but if
    # one ever does, grade_mode wins over the stored value.
    assert compute_section_value(_section(grade_mode="not_graded", grade=Decimal("9"))) is None


def test_section_value_returns_decimal_not_float() -> None:
    # A float anywhere in this path defeats M11's exact ROUND_HALF_UP arithmetic.
    assert isinstance(compute_section_value(_section()), Decimal)


def test_section_value_for_unknown_grade_mode_raises_value_error() -> None:
    # A future grade_mode must fail loudly rather than silently score zero.
    with pytest.raises(ValueError, match="unknown grade_mode"):
        compute_section_value(_section(grade_mode="holographic"))


# --- pass_fail scaling (M6) --------------------------------------------------
#
# A pass_fail section MAY declare grade_min/grade_max (operator decision, 2026-09-01), which
# is what makes a pass worth full marks beside numeric siblings. Sections authored before that
# carry neither — test_pass_fail_without_template_bounds_* covers them, and they scale onto
# [0, 1] where a pass counts as 1.


def _pf(**kw) -> SectionGradeInput:
    base = dict(grade_mode="pass_fail", grade=Decimal("1"), grade_min=Decimal("0"), grade_max=Decimal("10"))
    return _section(**{**base, **kw})


def test_pass_fail_pass_scales_to_grade_max() -> None:
    assert compute_section_value(_pf(grade=Decimal("1"))) == Decimal("10")


def test_pass_fail_fail_scales_to_grade_min() -> None:
    assert compute_section_value(_pf(grade=Decimal("0"))) == Decimal("0")


def test_pass_fail_respects_non_zero_grade_min() -> None:
    # A grade_min>0 section stays comparable with its numeric siblings.
    assert compute_section_value(_pf(grade=Decimal("1"), grade_min=Decimal("4"))) == Decimal("10")
    assert compute_section_value(_pf(grade=Decimal("0"), grade_min=Decimal("4"))) == Decimal("4")


def test_pass_fail_with_null_grade_returns_none() -> None:
    assert compute_section_value(_pf(grade=None)) is None


def test_pass_fail_with_out_of_range_stored_grade_raises_value_error() -> None:
    # W5-1 guarantees 0/1, so a 5 in the column is corruption — fail loudly, never scale it.
    with pytest.raises(ValueError, match="pass_fail grade must be 0 or 1"):
        compute_section_value(_pf(grade=Decimal("5")))


def test_pass_fail_without_template_bounds_scales_to_zero_one() -> None:
    # Legacy shape: no bounds declared, so [0, 1] is the only scale available and a pass is
    # worth 1. Fixed by editing the template to declare a range.
    unbounded = _pf(grade_min=None, grade_max=None)
    assert compute_section_value(unbounded) == Decimal("1")
    assert compute_section_value(_pf(grade=Decimal("0"), grade_min=None, grade_max=None)) == Decimal("0")
