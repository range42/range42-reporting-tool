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
# NOTE on the fixtures below: a pass_fail section can never carry grade_min/grade_max in real
# data — section_invariant_error (app/schemas/template.py:64) rejects that at template
# authoring time. The first three tests exercise M6's formula on explicit bounds because that
# is what the spec defines; test_pass_fail_without_template_bounds_* covers what the database
# actually holds. See the module note in rollup.py.


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
    # The real-data shape: WP3 forbids grade_min/grade_max on pass_fail, so both are NULL and
    # [0, 1] is the only scale available. Comparability with numeric siblings is B3's problem.
    unbounded = _pf(grade_min=None, grade_max=None)
    assert compute_section_value(unbounded) == Decimal("1")
    assert compute_section_value(_pf(grade=Decimal("0"), grade_min=None, grade_max=None)) == Decimal("0")
