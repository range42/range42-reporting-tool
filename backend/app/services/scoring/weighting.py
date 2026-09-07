"""The Decimal primitives every scoring path shares: rounding and the weighted mean.

They live below ``rollup`` and ``aggregate`` so both can import them without a cycle. There is
deliberately ONE implementation of each — two evaluators grading the same report must not be
able to reach different numbers because two modules rounded differently.
"""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal, localcontext

_CENTS = Decimal("0.01")
# report.overall_grade and section_grade.grade are both NUMERIC(5,2).
_MAX_NUMERIC_5_2 = Decimal("999.99")


class RollupOverflow(Exception):
    """A computed grade exceeds NUMERIC(5,2). Indicates a template grade_max misconfiguration."""


def quantize_grade(value: Decimal) -> Decimal:
    """Round to the column's 2 decimal places, HALF_UP (M11). Only called on persist.

    HALF_UP, not Python's default banker's rounding: 8.125 becomes 8.13, not 8.12. Repeatedly
    rounding half-to-even would bias a long run of grades downward, and it surprises anyone
    checking the arithmetic by hand.
    """
    if value > _MAX_NUMERIC_5_2 or value < -_MAX_NUMERIC_5_2:
        raise RollupOverflow(f"grade {value} exceeds NUMERIC(5,2)")
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def compute_weighted_average(pairs: Sequence[tuple[Decimal, Decimal]]) -> Decimal | None:
    """Σ(value × weight) / Σ weight (§4.2).

    None when the denominator is zero — callers must persist that as SQL NULL, never as 0.
    Shared by section rollup, report rollup and multi-evaluator aggregation.
    """
    total_weight = sum((w for _, w in pairs), Decimal(0))
    if total_weight == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 28
        return sum((v * w for v, w in pairs), Decimal(0)) / total_weight
