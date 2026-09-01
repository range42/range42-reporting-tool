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
