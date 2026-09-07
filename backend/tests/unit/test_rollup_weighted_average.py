"""Task 4 — the heart of A7: sections folded into one evaluator's grade.

The exclusion rule is what most of this file defends. A section contributing ``None`` — either
``not_graded`` (M4) or gradable-but-ungraded (M5) — leaves BOTH the numerator and the weight
denominator. Counting it as zero, or keeping its weight in the denominator, silently punishes
a team for work an evaluator simply has not marked yet.
"""

from decimal import Decimal

import pytest

from app.services.scoring.rollup import (
    EvaluationInput,
    SectionGradeInput,
    compute_evaluation_grade,
    compute_rubric_rollup,
    has_mixed_grade_max,
)
from app.services.scoring.weighting import RollupOverflow, compute_weighted_average, quantize_grade


def _s(**kw) -> SectionGradeInput:
    base = dict(
        section_def_id="s",
        name="Section",
        grade_mode="numeric",
        grade=Decimal("8"),
        grade_min=Decimal("0"),
        grade_max=Decimal("10"),
        grade_weight=Decimal("1"),
    )
    return SectionGradeInput(**{**base, **kw})


def _ev(*sections: SectionGradeInput) -> EvaluationInput:
    return EvaluationInput(evaluation_id="e1", evaluator_id="u1", aggregated_weight=Decimal("1"), sections=sections)


# --- the weighted average itself ---------------------------------------------


def test_rollup_computes_weighted_average_of_graded_sections() -> None:
    # (9*2 + 6*1) / 3 = 8
    ev = _ev(_s(grade=Decimal("9"), grade_weight=Decimal("2")), _s(grade=Decimal("6")))
    assert compute_evaluation_grade(ev) == Decimal("8.00")


def test_rollup_treats_equal_weights_as_a_plain_mean() -> None:
    ev = _ev(_s(grade=Decimal("7")), _s(grade=Decimal("8")), _s(grade=Decimal("9")))
    assert compute_evaluation_grade(ev) == Decimal("8.00")


def test_rollup_with_a_single_section_returns_that_sections_value() -> None:
    assert compute_evaluation_grade(_ev(_s(grade=Decimal("6.5")))) == Decimal("6.50")


# --- M4 / M5 exclusion --------------------------------------------------------


def test_rollup_excludes_not_graded_sections_from_denominator() -> None:
    # Without the exclusion this would be 8/2 = 4.
    ev = _ev(_s(grade=Decimal("8")), _s(grade_mode="not_graded", grade=None))
    assert compute_evaluation_grade(ev) == Decimal("8.00")


def test_rollup_excludes_not_graded_sections_from_numerator() -> None:
    # A stray stored grade on a not_graded section must not reach the numerator either.
    ev = _ev(_s(grade=Decimal("8")), _s(grade_mode="not_graded", grade=Decimal("2")))
    assert compute_evaluation_grade(ev) == Decimal("8.00")


def test_rollup_excludes_ungraded_sections_from_denominator() -> None:
    # M5 — a heavy ungraded section must not drag the grade down before it is marked.
    ev = _ev(_s(grade=Decimal("8")), _s(grade=None, grade_weight=Decimal("9")))
    assert compute_evaluation_grade(ev) == Decimal("8.00")


def test_rollup_excludes_zero_weight_sections() -> None:
    ev = _ev(_s(grade=Decimal("8")), _s(grade=Decimal("2"), grade_weight=Decimal("0")))
    assert compute_evaluation_grade(ev) == Decimal("8.00")


# --- None, never zero ---------------------------------------------------------


def test_rollup_returns_none_when_no_section_has_a_grade() -> None:
    assert compute_evaluation_grade(_ev(_s(grade=None), _s(grade=None))) is None


def test_rollup_returns_none_when_every_section_is_not_graded() -> None:
    ev = _ev(_s(grade_mode="not_graded", grade=None), _s(grade_mode="not_graded", grade=None))
    assert compute_evaluation_grade(ev) is None


def test_rollup_returns_none_when_total_weight_is_zero() -> None:
    assert compute_weighted_average([(Decimal("8"), Decimal("0"))]) is None
    assert compute_weighted_average([]) is None


def test_rollup_returns_none_for_an_evaluation_with_no_sections() -> None:
    assert compute_evaluation_grade(_ev()) is None


# --- M11 arithmetic -----------------------------------------------------------


def test_rollup_quantizes_to_two_decimal_places() -> None:
    ev = _ev(_s(grade=Decimal("8")), _s(grade=Decimal("7")), _s(grade=Decimal("8")))
    assert compute_evaluation_grade(ev) == Decimal("7.67")  # 23/3 = 7.666...


def test_rollup_rounds_half_up_not_bankers() -> None:
    # Python's default would give 8.12 for both; HALF_UP gives 8.13 / 8.14.
    assert quantize_grade(Decimal("8.125")) == Decimal("8.13")
    assert quantize_grade(Decimal("8.135")) == Decimal("8.14")


def test_rollup_uses_no_floating_point_arithmetic() -> None:
    # 0.1 + 0.2 in binary float is 0.30000000000000004; Decimal keeps it exact.
    ev = _ev(_s(grade=Decimal("0.1")), _s(grade=Decimal("0.2")))
    result = compute_evaluation_grade(ev)
    assert isinstance(result, Decimal)
    assert result == Decimal("0.15")


def test_rollup_raises_on_value_exceeding_numeric_5_2() -> None:
    with pytest.raises(RollupOverflow):
        quantize_grade(Decimal("1000"))
    ev = _ev(_s(grade=Decimal("1000"), grade_max=Decimal("1000")))
    with pytest.raises(RollupOverflow):
        compute_evaluation_grade(ev)


def test_rollup_raises_on_negative_grade_weight() -> None:
    # A negative weight would silently invert the average rather than fail.
    with pytest.raises(ValueError, match="negative grade_weight"):
        compute_evaluation_grade(_ev(_s(grade_weight=Decimal("-1"))))


def test_rollup_handles_degenerate_grade_scale() -> None:
    # grade_min == grade_max: zero-width scale, so every result is that constant. Must not
    # divide by zero. Template validation forbids this for numeric/pass_fail, not for rubric.
    got = compute_rubric_rollup(
        [{"name": "C", "max_score": 5, "weight": 1}],
        [{"criterion": "C", "score": "3"}],
        grade_min=Decimal("5"),
        grade_max=Decimal("5"),
    )
    assert got == Decimal("5")


# --- M12: raw weighted average, no cross-section normalization ----------------


def test_rollup_flags_mixed_grade_max_across_sections() -> None:
    # Averaging a 0-10 section with a 0-100 one is arithmetically valid but almost never
    # intended, so the caller can warn. M12 keeps the raw average rather than normalizing.
    assert has_mixed_grade_max([_s(grade_max=Decimal("10")), _s(grade_max=Decimal("100"))]) is True
    assert has_mixed_grade_max([_s(grade_max=Decimal("10")), _s(grade_max=Decimal("10"))]) is False


def test_mixed_grade_max_ignores_sections_that_contribute_nothing() -> None:
    # A not_graded section's grade_max is irrelevant — it never reaches the average.
    sections = [_s(grade_max=Decimal("10")), _s(grade_mode="not_graded", grade=None, grade_max=Decimal("100"))]
    assert has_mixed_grade_max(sections) is False


def test_rollup_does_not_normalize_across_mixed_scales() -> None:
    # M12 — the raw weighted average, even when the scales differ. (80 + 8) / 2 = 44.
    ev = _ev(_s(grade=Decimal("80"), grade_max=Decimal("100")), _s(grade=Decimal("8")))
    assert compute_evaluation_grade(ev) == Decimal("44.00")


# --- golden path --------------------------------------------------------------


def test_golden_path_single_evaluator_overall_grade_is_8_22() -> None:
    """One evaluator, every grading mode, both exclusion rules — lands on 8.22.

    Constructed here rather than copied: the plan's worked example lives in the gitignored
    docs/superpowers tree. The arithmetic is spelled out so a future reader can re-derive it.

        Executive Summary   numeric    8.5            weight 2 -> 17.0
        Detection Timeline  numeric    7.8            weight 1 ->  7.8
        SOC notified        pass_fail  pass on 0-10   weight 1 -> 10.0
        Report quality      rubric     6.3 pre-rolled weight 1 ->  6.3
        Service status      not_graded                weight 1 -> excluded (M4)
        Lessons learned     numeric    ungraded       weight 3 -> excluded (M5)

        41.1 / 5 = 8.22
    """
    ev = _ev(
        _s(section_def_id="exec", grade=Decimal("8.5"), grade_weight=Decimal("2")),
        _s(section_def_id="timeline", grade=Decimal("7.8")),
        _s(section_def_id="soc", grade_mode="pass_fail", grade=Decimal("1")),
        _s(section_def_id="quality", grade_mode="rubric", grade=Decimal("6.3")),
        _s(section_def_id="status", grade_mode="not_graded", grade=None),
        _s(section_def_id="lessons", grade=None, grade_weight=Decimal("3")),
    )
    assert compute_evaluation_grade(ev) == Decimal("8.22")
