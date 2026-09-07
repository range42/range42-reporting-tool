"""W5-3 Task 3 — pure multi-evaluator aggregation and the L7 "counted" predicate.

DB-free on purpose: the finalize gate and the rollup must agree bit-for-bit on which
evaluations count, so the predicate has exactly one home and both import it.

The arithmetic is ``Decimal`` throughout. A float mean is the reproducibility bug that makes
two identically-graded exercises score differently.
"""

from decimal import Decimal

from app.services.scoring.aggregate import (
    EvaluationFacts,
    aggregate_overall_grade,
    contributes_grade,
    counts,
)


def _facts(
    grade: str | None,
    weight: str = "1.00",
    *,
    status: str = "completed",
    unassigned: bool = False,
    evaluation_id: str = "e",
) -> EvaluationFacts:
    return EvaluationFacts(
        evaluation_id=evaluation_id,
        status=status,
        overall_grade=None if grade is None else Decimal(grade),
        aggregated_weight=Decimal(weight),
        is_unassigned=unassigned,
    )


# --- the weighted mean ----------------------------------------------------------------


def test_single_completed_evaluation_aggregate_equals_its_own_grade() -> None:
    # Arrange
    evaluations = [_facts("7.50")]

    # Act
    result = aggregate_overall_grade(evaluations)

    # Assert
    assert result == Decimal("7.50")


def test_two_equal_weight_evaluations_aggregate_to_their_mean() -> None:
    # Arrange
    evaluations = [_facts("8.00", evaluation_id="a"), _facts("6.00", evaluation_id="b")]

    # Act
    result = aggregate_overall_grade(evaluations)

    # Assert
    assert result == Decimal("7.00")


def test_weighted_aggregate_uses_aggregated_weight_as_denominator() -> None:
    # Arrange: (8.00x1.00 + 6.00x1.50) / 2.50
    evaluations = [_facts("8.00", "1.00", evaluation_id="a"), _facts("6.00", "1.50", evaluation_id="b")]

    # Act
    result = aggregate_overall_grade(evaluations)

    # Assert
    assert result == Decimal("6.80")


# --- L7: what counts ------------------------------------------------------------------


def test_unassigned_evaluation_is_excluded_from_numerator_and_denominator() -> None:
    # Arrange: were the unassigned 2.00 counted, the mean would be 4.00, not 8.00.
    evaluations = [
        _facts("8.00", "1.00", evaluation_id="kept"),
        _facts("0.00", "1.00", unassigned=True, evaluation_id="gone"),
    ]

    # Act
    result = aggregate_overall_grade(evaluations)

    # Assert
    assert result == Decimal("8.00")


def test_unassign_evaluator_renormalizes_aggregated_weight() -> None:
    """The canonical L5 case: the denominator shrinks, the surviving grade is not rescaled."""
    # Arrange
    kept = _facts("8.00", "1.00", evaluation_id="kept")
    before = [kept, _facts("6.00", "1.50", evaluation_id="dropped")]
    after = [kept, _facts("6.00", "1.50", unassigned=True, evaluation_id="dropped")]

    # Act
    result_before = aggregate_overall_grade(before)
    result_after = aggregate_overall_grade(after)

    # Assert
    assert result_before == Decimal("6.80")
    assert result_after == Decimal("8.00")  # not 6.80, and not 6.80 x (1.00 / 2.50)


def test_incomplete_evaluation_is_excluded_from_numerator_but_counts_for_the_gate() -> None:
    # Arrange
    in_progress = _facts(None, "1.00", status="in_progress", evaluation_id="wip")
    evaluations = [_facts("8.00", "1.00", evaluation_id="done"), in_progress]

    # Act
    result = aggregate_overall_grade(evaluations)

    # Assert: it does not drag the mean toward zero, yet all_must_finalize still sees it.
    assert result == Decimal("8.00")
    assert counts(in_progress) is True
    assert contributes_grade(in_progress) is False


def test_evaluation_with_null_overall_grade_is_excluded_from_numerator() -> None:
    # Arrange
    evaluations = [_facts("8.00", evaluation_id="a"), _facts(None, evaluation_id="b")]

    # Act
    result = aggregate_overall_grade(evaluations)

    # Assert
    assert result == Decimal("8.00")


def test_counted_predicate_ignores_status_and_looks_only_at_unassigned_at() -> None:
    # Arrange
    statuses = ["pending", "in_progress", "completed"]

    # Act / Assert
    for status in statuses:
        assert counts(_facts("5.00", status=status)) is True
        assert counts(_facts("5.00", status=status, unassigned=True)) is False


# --- degenerate denominators ----------------------------------------------------------


def test_aggregate_is_none_when_no_evaluation_counts() -> None:
    # Arrange
    evaluations = [
        _facts("8.00", unassigned=True, evaluation_id="a"),
        _facts("6.00", unassigned=True, evaluation_id="b"),
    ]

    # Act
    result = aggregate_overall_grade(evaluations)

    # Assert: NULL, never 0.00, and never a ZeroDivisionError.
    assert result is None


def test_aggregate_is_none_when_total_weight_is_zero() -> None:
    # Arrange: DECIMAL(3,2) permits 0.00, and a Global Admin may set every weight to it.
    evaluations = [_facts("8.00", "0.00", evaluation_id="a"), _facts("6.00", "0.00", evaluation_id="b")]

    # Act
    result = aggregate_overall_grade(evaluations)

    # Assert
    assert result is None


def test_aggregate_is_empty_list_safe() -> None:
    # Arrange / Act
    result = aggregate_overall_grade([])

    # Assert
    assert result is None


# --- rounding -------------------------------------------------------------------------


def test_aggregate_rounds_half_up_to_two_decimals() -> None:
    # Arrange: (8.13 + 8.12) / 2 = 8.125, which HALF_UP resolves to 8.13, not 8.12.
    evaluations = [_facts("8.13", evaluation_id="a"), _facts("8.12", evaluation_id="b")]

    # Act
    result = aggregate_overall_grade(evaluations)

    # Assert
    assert result == Decimal("8.13")
    assert result.as_tuple().exponent == -2


def test_zero_grade_contributes_and_is_not_mistaken_for_missing() -> None:
    # Arrange: 0.00 is a real grade, not an absent one.
    evaluations = [_facts("0.00", evaluation_id="a"), _facts("8.00", evaluation_id="b")]

    # Act
    result = aggregate_overall_grade(evaluations)

    # Assert
    assert result == Decimal("4.00")
