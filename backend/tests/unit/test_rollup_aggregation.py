"""Task 5 — several evaluators' grades folded into the report's single grade (M8).

Each evaluation carries an ``aggregated_weight``, so a lead evaluator can count for more than
a shadow one. The report grade is the weighted average of the per-evaluator grades.

This exercises the COMPOSITION — sections to an evaluator grade to a report grade — through
``compute_evaluation_grade`` and W5-3's ``aggregate_overall_grade``. W5-2's
``compute_report_grade`` is gone; ``test_scoring_aggregate.py`` covers the aggregate in
isolation, and what is pinned here is that the two halves still meet on the plan's numbers.
"""

from decimal import Decimal

from app.services.scoring.aggregate import EvaluationFacts, aggregate_overall_grade
from app.services.scoring.rollup import (
    EvaluationInput,
    SectionGradeInput,
    compute_evaluation_grade,
)


def _s(grade: str | None, weight: str = "1", **kw) -> SectionGradeInput:
    base = dict(
        section_def_id="s",
        name="Section",
        grade_mode="numeric",
        grade=None if grade is None else Decimal(grade),
        grade_min=Decimal("0"),
        grade_max=Decimal("10"),
        grade_weight=Decimal(weight),
    )
    return SectionGradeInput(**{**base, **kw})


def _ev(*sections: SectionGradeInput, weight: str = "1", eid: str = "e") -> EvaluationInput:
    return EvaluationInput(
        evaluation_id=eid, evaluator_id=f"u-{eid}", aggregated_weight=Decimal(weight), sections=sections
    )


def _facts(ev: EvaluationInput, *, status: str = "completed", unassigned: bool = False) -> EvaluationFacts:
    """One evaluation's aggregation facts, with its sections already folded into a grade."""
    return EvaluationFacts(
        evaluation_id=ev.evaluation_id,
        status=status,
        overall_grade=compute_evaluation_grade(ev),
        aggregated_weight=ev.aggregated_weight,
        is_unassigned=unassigned,
    )


def _report_grade(*evaluations: EvaluationInput, **kw: object) -> Decimal | None:
    return aggregate_overall_grade([_facts(e, **kw) for e in evaluations])  # type: ignore[arg-type]


def test_single_evaluator_report_grade_equals_that_evaluators_grade() -> None:
    assert _report_grade(_ev(_s("8"), _s("6"))) == Decimal("7.00")


def test_report_grade_is_weighted_average_of_evaluator_grades() -> None:
    # Equal aggregated_weight -> plain mean of 8 and 6.
    assert _report_grade(_ev(_s("8"), eid="a"), _ev(_s("6"), eid="b")) == Decimal("7.00")


def test_report_grade_honors_unequal_aggregated_weights() -> None:
    # (9*3 + 5*1) / 4 = 8
    evaluations = [_ev(_s("9"), weight="3", eid="lead"), _ev(_s("5"), weight="1", eid="shadow")]
    assert _report_grade(*evaluations) == Decimal("8.00")


def test_report_grade_excludes_evaluations_with_no_grades() -> None:
    # An assigned-but-unstarted evaluator must not pull the report toward zero, and their
    # weight must leave the denominator too: this is 8, not 4.
    evaluations = [_ev(_s("8"), eid="done"), _ev(_s(None), weight="5", eid="unstarted")]
    assert _report_grade(*evaluations) == Decimal("8.00")


def test_report_grade_returns_none_when_no_evaluation_has_grades() -> None:
    assert _report_grade(_ev(_s(None), eid="a"), _ev(_s(None), eid="b")) is None


def test_report_grade_returns_none_when_report_has_no_evaluations() -> None:
    assert _report_grade() is None


def test_report_grade_ignores_zero_weight_evaluations() -> None:
    evaluations = [_ev(_s("8"), eid="counts"), _ev(_s("2"), weight="0", eid="ignored")]
    assert _report_grade(*evaluations) == Decimal("8.00")


def test_report_grade_excludes_an_in_progress_evaluation() -> None:
    """The W5-2 behaviour this replaces: an in-progress evaluation used to contribute.

    W5-2's provisional M8 policy let any evaluation with a graded section count, so a grade was
    visible before anyone finalized. L7 narrows the numerator to completed evaluations, which is
    why the same input now yields None.
    """
    in_progress = _ev(_s("8"), eid="still-grading")
    assert _report_grade(in_progress, status="in_progress") is None


def test_report_grade_excludes_an_unassigned_evaluation() -> None:
    # L5 renormalization: the survivor's grade stands unscaled, the removed weight simply goes.
    kept = _ev(_s("8"), eid="kept")
    dropped = _ev(_s("2"), weight="4", eid="dropped")
    assert aggregate_overall_grade([_facts(kept), _facts(dropped, unassigned=True)]) == Decimal("8.00")


def test_report_grade_quantizes_after_aggregating_not_before() -> None:
    # Per-evaluator grades are already 2dp (they are persisted values); the aggregate rounds
    # once at the end. 7.33 and 7.34 average to exactly 7.335 -> HALF_UP -> 7.34.
    evaluations = [_ev(_s("7.33"), eid="a"), _ev(_s("7.34"), eid="b")]
    assert _report_grade(*evaluations) == Decimal("7.34")


def test_golden_path_two_evaluators_weighted_report_grade_is_7_41() -> None:
    """Two evaluators at unequal weight — lands on 7.41.

    Constructed here rather than copied: the plan's worked example lives in the gitignored
    docs/superpowers tree. Evaluator A is Task 4's golden-path evaluation, reused so the two
    tests chain, and the arithmetic is spelled out so it can be re-derived.

        A  lead    8.22 (Task 4's golden path)   aggregated_weight 2 -> 16.44
        B  shadow  (5.58 + 6.00) / 2 = 5.79      aggregated_weight 1 ->  5.79

        22.23 / 3 = 7.41
    """
    lead = _ev(
        _s("8.5", weight="2", section_def_id="exec"),
        _s("7.8", section_def_id="timeline"),
        _s("1", section_def_id="soc", grade_mode="pass_fail"),
        _s("6.3", section_def_id="quality", grade_mode="rubric"),
        _s(None, section_def_id="status", grade_mode="not_graded"),
        _s(None, weight="3", section_def_id="lessons"),
        weight="2",
        eid="lead",
    )
    shadow = _ev(_s("5.58"), _s("6.00"), weight="1", eid="shadow")
    assert _report_grade(lead, shadow) == Decimal("7.41")
