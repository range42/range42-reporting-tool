"""Task 3 — folding a rubric's criterion scores into one section grade (M7).

THE RULE (operator decision, 2026-09-01): each criterion is scored as a percentage of its OWN
maximum, those percentages are averaged using the criterion weights, and the result is
stretched onto the section's [grade_min, grade_max] range.

    normalized = Σ((score / max_score) · weight) / Σ(weight)
    grade      = grade_min + normalized · (grade_max - grade_min)

This deviates from #103's written formula, Σ(score·weight) / Σ(max_score·weight), which lets a
criterion with a larger max_score quietly carry more influence than its weight says. Under the
rule below, ``weight`` is the only thing that controls influence and ``max_score`` only sets
the scoring granularity. test_rubric_rollup_weight_not_max_score_controls_influence pins the
difference — it is the test that fails if anyone reverts to the other formula.
"""

from decimal import Decimal

from app.services.scoring.rollup import compute_rubric_rollup

CRITERIA = [
    {"name": "Clarity", "max_score": 5, "weight": 1},
    {"name": "Depth", "max_score": 10, "weight": 1},
]


def _roll(criteria, scores, *, grade_min="0", grade_max="10") -> Decimal | None:
    return compute_rubric_rollup(criteria, scores, grade_min=Decimal(grade_min), grade_max=Decimal(grade_max))


def test_rubric_rollup_normalizes_scores_onto_the_section_grade_scale() -> None:
    # Clarity 4/5 = 80%, Depth 8/10 = 80% -> 80% of 0..10
    scores = [{"criterion": "Clarity", "score": "4"}, {"criterion": "Depth", "score": "8"}]
    assert _roll(CRITERIA, scores) == Decimal("8")


def test_rubric_rollup_weight_not_max_score_controls_influence() -> None:
    # THE DECIDING CASE. Clarity 100%, Depth 0%, equal weights -> 50%.
    # The rejected points-based formula gives 5/15 = 33.3% -> 3.33 here.
    scores = [{"criterion": "Clarity", "score": "5"}, {"criterion": "Depth", "score": "0"}]
    assert _roll(CRITERIA, scores) == Decimal("5")


def test_rubric_rollup_all_max_scores_yields_grade_max() -> None:
    scores = [{"criterion": "Clarity", "score": "5"}, {"criterion": "Depth", "score": "10"}]
    assert _roll(CRITERIA, scores) == Decimal("10")


def test_rubric_rollup_all_zero_scores_yields_grade_min() -> None:
    scores = [{"criterion": "Clarity", "score": "0"}, {"criterion": "Depth", "score": "0"}]
    assert _roll(CRITERIA, scores) == Decimal("0")


def test_rubric_rollup_stretches_onto_a_non_zero_grade_min() -> None:
    scores = [{"criterion": "Clarity", "score": "5"}, {"criterion": "Depth", "score": "0"}]
    # 50% of the 4..10 band = 4 + 0.5*6
    assert _roll(CRITERIA, scores, grade_min="4", grade_max="10") == Decimal("7")


def test_rubric_rollup_honors_per_criterion_weights() -> None:
    # Clarity 100% at weight 3, Depth 0% at weight 1 -> 75%
    criteria = [
        {"name": "Clarity", "max_score": 5, "weight": 3},
        {"name": "Depth", "max_score": 10, "weight": 1},
    ]
    scores = [{"criterion": "Clarity", "score": "5"}, {"criterion": "Depth", "score": "0"}]
    assert _roll(criteria, scores) == Decimal("7.5")


def test_rubric_rollup_excludes_criteria_with_no_submitted_score() -> None:
    # Depth ungraded: the grade is Clarity's 80% alone, not 40%.
    assert _roll(CRITERIA, [{"criterion": "Clarity", "score": "4"}]) == Decimal("8")


def test_rubric_rollup_with_empty_criteria_returns_none() -> None:
    assert _roll([], [{"criterion": "Clarity", "score": "4"}]) is None
    assert _roll(None, [{"criterion": "Clarity", "score": "4"}]) is None


def test_rubric_rollup_with_no_scores_returns_none() -> None:
    assert _roll(CRITERIA, []) is None
    assert _roll(CRITERIA, None) is None


def test_rubric_rollup_with_zero_total_max_score_returns_none() -> None:
    # A zero max cannot yield a percentage; template validation forbids it, so this is a guard.
    criteria = [{"name": "Clarity", "max_score": 0, "weight": 1}]
    assert _roll(criteria, [{"criterion": "Clarity", "score": "0"}]) is None


def test_rubric_rollup_ignores_scores_for_unknown_criteria() -> None:
    # Defence in depth: a template edit must not break the rollup of an already-graded report.
    scores = [{"criterion": "Clarity", "score": "4"}, {"criterion": "Removed", "score": "9"}]
    assert _roll(CRITERIA, scores) == Decimal("8")


def test_rubric_rollup_defaults_missing_criterion_weight_to_one() -> None:
    # §4.2's rubric_criteria shape does not mark weight required.
    criteria = [{"name": "Clarity", "max_score": 5}, {"name": "Depth", "max_score": 10}]
    scores = [{"criterion": "Clarity", "score": "5"}, {"criterion": "Depth", "score": "0"}]
    assert _roll(criteria, scores) == Decimal("5")


def test_rubric_rollup_clamps_a_score_above_its_criterion_max() -> None:
    # Same stale-data class as unknown criteria: if a template edit LOWERS max_score, an older
    # score must not push the section above grade_max.
    scores = [{"criterion": "Clarity", "score": "9"}, {"criterion": "Depth", "score": "10"}]
    assert _roll(CRITERIA, scores) == Decimal("10")


def test_rubric_rollup_returns_decimal_not_float() -> None:
    scores = [{"criterion": "Clarity", "score": "4"}, {"criterion": "Depth", "score": "8"}]
    assert isinstance(_roll(CRITERIA, scores), Decimal)
