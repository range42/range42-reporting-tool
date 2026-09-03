"""Multi-evaluator aggregation (W5-3, ARCHITECTURE §4.2 "Multi-evaluator aggregation rule").

Pure and DB-free on purpose: the finalize gate and the rollup must agree bit-for-bit on what
"counts", so the predicate lives here exactly once (L7) and both import it. Nothing else may
re-derive it from ``unassigned_at`` — a second copy is how the two drift apart.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.services.scoring.weighting import compute_weighted_average, quantize_grade

COMPLETED = "completed"


@dataclass(frozen=True)
class EvaluationFacts:
    """The only fields of an ``evaluation`` row that aggregation or the gate may read.

    Deliberately narrow: taking the ORM object here would let the maths reach for a lazy
    relationship and turn a pure function into a query.
    """

    evaluation_id: object
    status: str
    overall_grade: Decimal | None
    aggregated_weight: Decimal
    is_unassigned: bool


def counts(e: EvaluationFacts) -> bool:
    """L7: an evaluation participates in the gate and the denominator iff it is not unassigned.

    Status is irrelevant here. An ``in_progress`` evaluation still blocks ``all_must_finalize``;
    only unassignment removes an evaluator from the reckoning.
    """
    return not e.is_unassigned


def contributes_grade(e: EvaluationFacts) -> bool:
    """L7: it participates in the numerator iff it is also completed with a grade.

    Narrower than :func:`counts` — an assigned evaluator who has not finished must not drag the
    aggregate toward zero while their evaluation is still pending.
    """
    return counts(e) and e.status == COMPLETED and e.overall_grade is not None


def aggregate_overall_grade(evaluations: Sequence[EvaluationFacts]) -> Decimal | None:
    """Weighted mean over grade-contributing evaluations, renormalized (L5).

    Unassigning an evaluator drops their weight from the denominator rather than rescaling the
    surviving grade: two evaluators at 1.00/8.00 and 1.50/6.00 average 6.80, and unassigning the
    second yields 8.00 — not 6.80, and not 6.80 × (1.00 / 2.50).

    Returns ``None`` when nothing contributes or the counted weight is zero, so the caller
    stores NULL rather than a misleading 0.00.
    """
    # ``contributes_grade`` already rejects a None grade; the walrus re-states it for the
    # type checker. An explicit ``is not None`` — a grade of 0.00 is real and must count.
    pairs = [
        (g, e.aggregated_weight) for e in evaluations if contributes_grade(e) if (g := e.overall_grade) is not None
    ]
    average = compute_weighted_average(pairs)
    return None if average is None else quantize_grade(average)
