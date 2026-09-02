"""W5-3 Task 5 — the finalize gate (ARCHITECTURE §7.2).

Pure: a list of :class:`EvaluationFacts` plus a mode string. No database, no fixtures.

The gate answers one question — may this report move from ``under_evaluation`` to
``evaluated`` right now — and it answers it from the same L7 predicates the aggregate uses,
so a report can never be declared evaluated on a different set of evaluations than the one
its grade was computed from.
"""

from decimal import Decimal

from app.services.evaluation.finalize_gate import ALL_MUST_FINALIZE, ANY_CAN_FINALIZE, is_gate_open
from app.services.scoring.aggregate import EvaluationFacts


def _facts(
    *,
    status: str = "completed",
    grade: str | None = "8.00",
    unassigned: bool = False,
    evaluation_id: str = "e",
) -> EvaluationFacts:
    return EvaluationFacts(
        evaluation_id=evaluation_id,
        status=status,
        overall_grade=None if grade is None else Decimal(grade),
        aggregated_weight=Decimal("1.00"),
        is_unassigned=unassigned,
    )


# --- all_must_finalize ----------------------------------------------------------------


def test_all_must_finalize_gate_is_open_when_every_counted_evaluation_is_completed() -> None:
    # Arrange
    evaluations = [_facts(evaluation_id="a"), _facts(evaluation_id="b")]

    # Act
    result = is_gate_open(evaluations, ALL_MUST_FINALIZE)

    # Assert
    assert result is True


def test_all_must_finalize_gate_is_closed_when_one_counted_evaluation_is_in_progress() -> None:
    # Arrange
    evaluations = [_facts(evaluation_id="a"), _facts(status="in_progress", grade=None, evaluation_id="b")]

    # Act
    result = is_gate_open(evaluations, ALL_MUST_FINALIZE)

    # Assert
    assert result is False


def test_all_must_finalize_gate_ignores_unassigned_evaluations() -> None:
    """The mandated edge case: an evaluator removed mid-exercise must not block the report."""
    # Arrange: one finished evaluator, one unassigned who never started.
    evaluations = [
        _facts(evaluation_id="finished"),
        _facts(status="assigned", grade=None, unassigned=True, evaluation_id="removed"),
    ]

    # Act
    result = is_gate_open(evaluations, ALL_MUST_FINALIZE)

    # Assert
    assert result is True


# --- any_can_finalize -----------------------------------------------------------------


def test_any_can_finalize_gate_is_open_after_the_first_completed_evaluation() -> None:
    # Arrange
    evaluations = [_facts(evaluation_id="a"), _facts(status="in_progress", grade=None, evaluation_id="b")]

    # Act
    result = is_gate_open(evaluations, ANY_CAN_FINALIZE)

    # Assert
    assert result is True


def test_any_can_finalize_gate_is_closed_when_no_evaluation_is_completed() -> None:
    # Arrange
    evaluations = [
        _facts(status="in_progress", grade="7.00", evaluation_id="a"),
        _facts(status="assigned", grade=None, evaluation_id="b"),
    ]

    # Act
    result = is_gate_open(evaluations, ANY_CAN_FINALIZE)

    # Assert
    assert result is False


# --- degenerate sets ------------------------------------------------------------------


def test_gate_is_closed_when_no_evaluation_counts() -> None:
    """The empty counted set is CLOSED, not vacuously open.

    ``all(...)`` over nothing is True, which would let a report whose every evaluator was
    unassigned drift silently into ``evaluated`` with no grade behind it.
    """
    # Arrange
    evaluations = [
        _facts(unassigned=True, evaluation_id="a"),
        _facts(unassigned=True, evaluation_id="b"),
    ]

    # Act / Assert
    assert is_gate_open(evaluations, ALL_MUST_FINALIZE) is False
    assert is_gate_open(evaluations, ANY_CAN_FINALIZE) is False


def test_gate_is_closed_when_there_are_no_evaluations_at_all() -> None:
    # Arrange / Act / Assert
    assert is_gate_open([], ALL_MUST_FINALIZE) is False
    assert is_gate_open([], ANY_CAN_FINALIZE) is False


def test_gate_is_closed_when_a_counted_evaluation_has_no_grade() -> None:
    """``completed`` with no grade satisfies neither mode.

    §7.2 requires every gradeable section populated before an evaluation may complete; this is
    the backstop for a row that got there anyway.
    """
    # Arrange
    evaluations = [_facts(grade=None, evaluation_id="empty")]

    # Act / Assert
    assert is_gate_open(evaluations, ALL_MUST_FINALIZE) is False
    assert is_gate_open(evaluations, ANY_CAN_FINALIZE) is False


def test_gate_treats_an_unknown_mode_as_the_strict_default() -> None:
    # Arrange: a mode string outside the CHECK constraint must never be the permissive branch.
    evaluations = [_facts(evaluation_id="a"), _facts(status="in_progress", grade=None, evaluation_id="b")]

    # Act
    result = is_gate_open(evaluations, "something_else")

    # Assert
    assert result is False
