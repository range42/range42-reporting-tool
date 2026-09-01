"""Scoring rollup (WP5 W5-2 — A7, the math).

SOLE-WRITER CONTRACT: this module is the *only* writer of ``report.overall_grade``.
It honors every grading mode — ``not_graded`` / ``manual`` / ``pass_fail`` /
``rubric`` / ``aggregated_weight`` — and returns the §6.10 timeline shape so
callers can render grade history. No other code path may set ``overall_grade``.

STRUCTURE (M3) — a pure core wrapped in a thin persistence shell:

* The ``compute_*`` functions are pure. They take the ``*Input`` dataclasses below, touch no
  database and no ORM object, and are exhaustively unit-tested without a session. All grading
  arithmetic lives here.
* ``recompute_report_grade`` (Task 7) is the shell: it loads rows, calls the pure core, and
  performs the single write, inside the caller's transaction.

Keeping the split means the scoring rules can be reasoned about — and re-derived by hand from
a failing report — without standing up a database.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

_GRADE_MODES = frozenset({"numeric", "pass_fail", "rubric", "not_graded"})


@dataclass(frozen=True)
class SectionGradeInput:
    """One section's grading state, flattened from ``template_section_def`` + ``section_grade``.

    ``grade`` is whatever is stored on the row: the numeric grade, 0/1 for ``pass_fail`` (M6
    scales it here, not at write time), or the pre-rolled rubric value (M7). ``None`` means no
    grade has been recorded yet.
    """

    section_def_id: str
    name: str
    grade_mode: str
    grade: Decimal | None
    grade_min: Decimal | None
    grade_max: Decimal | None
    grade_weight: Decimal


@dataclass(frozen=True)
class EvaluationInput:
    """One evaluator's contribution to a report: their sections plus their aggregation weight."""

    evaluation_id: str
    evaluator_id: str
    aggregated_weight: Decimal
    sections: tuple[SectionGradeInput, ...] = ()


def _dec(v: object) -> Decimal:
    """Coerce a JSONB scalar to Decimal via str, so a stored float never leaks binary error."""
    return Decimal(str(v))


def _resolve_bounds(grade_min: Decimal | None, grade_max: Decimal | None) -> tuple[Decimal, Decimal]:
    """The section's output range, defaulting to [0, 1] when the template declares none.

    A section that never declared a range has no scale to stretch onto, so a normalized 0..1
    fraction is the honest answer. Non-numeric sections on a mixed template should declare
    bounds — see ``section_invariant_error`` — or they under-score beside numeric siblings.
    """
    low = grade_min if grade_min is not None else Decimal(0)
    high = grade_max if grade_max is not None else Decimal(1)
    return low, high


def _criterion_weight(c: dict[str, Any]) -> Decimal:
    """§4.2's rubric_criteria shape does not mark ``weight`` required; absent means 1."""
    w = c.get("weight")
    return Decimal(1) if w is None else _dec(w)


def _criterion_max(c: dict[str, Any]) -> Decimal:
    m = c.get("max_score")
    return Decimal(0) if m is None else _dec(m)


def compute_rubric_rollup(
    criteria: list[dict[str, Any]] | None,
    scores: list[dict[str, Any]] | None,
    *,
    grade_min: Decimal,
    grade_max: Decimal,
) -> Decimal | None:
    """Pre-roll rubric criteria into one section grade (§4.2).

    Each criterion is scored as a fraction of its OWN maximum; those fractions are averaged by
    criterion weight and stretched onto the section's range:

        normalized = Σ((score / max_score) · weight) / Σ(weight)
        grade      = grade_min + normalized · (grade_max - grade_min)

    OPERATOR DECISION (2026-09-01) — this replaces the plan's Σ(score·w)/Σ(max_score·w). Under
    that formula a criterion with a larger ``max_score`` carries more influence than its
    ``weight`` declares, so the two fields fight over the same job. Here ``weight`` alone
    controls influence and ``max_score`` only sets granularity. Changing this back silently
    re-grades every rubric section ever scored, so treat it as a data migration, not a tweak.

    Criteria with no submitted score are excluded from BOTH sums. Scores naming a criterion
    that no longer exists on the template are ignored, and a score above its criterion's
    maximum is clamped — a template edit must not break, or inflate, the rollup of an
    already-graded report. Returns None when nothing can be computed.
    """
    if not criteria or not scores:
        return None
    by_name = {str(c.get("name")): c for c in criteria}
    weighted_total = Decimal(0)
    weight_total = Decimal(0)
    for entry in scores:
        criterion = by_name.get(str(entry.get("criterion")))
        if criterion is None:  # stale name from a template edit
            continue
        ceiling = _criterion_max(criterion)
        weight = _criterion_weight(criterion)
        if ceiling <= 0 or weight <= 0:
            continue
        fraction = min(_dec(entry.get("score", 0)) / ceiling, Decimal(1))
        weighted_total += fraction * weight
        weight_total += weight
    if weight_total == 0:
        return None
    normalized = weighted_total / weight_total
    return grade_min + normalized * (grade_max - grade_min)


def _scale_pass_fail(s: SectionGradeInput) -> Decimal:
    """§4.2: '1.0=pass, 0.0=fail scaled to grade_max'. The stored value is 0/1 (W5-1 L8) and is
    scaled here, so re-ranging a template re-scores old reports instead of freezing the number.

    A template MAY declare grade_min/grade_max on a pass_fail section (operator decision,
    2026-09-01) — a pass is then worth grade_max, keeping it comparable with numeric siblings
    on a mixed template. Sections authored before that carry no bounds and scale onto [0, 1],
    where a pass counts as 1; they need a template edit to score fairly.
    """
    if s.grade not in (Decimal(0), Decimal(1)):
        raise ValueError(f"pass_fail grade must be 0 or 1, got {s.grade}")
    low, high = _resolve_bounds(s.grade_min, s.grade_max)
    return low + s.grade * (high - low)


def compute_section_value(s: SectionGradeInput) -> Decimal | None:
    """The scaled value this section contributes, or None when it contributes nothing.

    None means EXCLUDED FROM BOTH numerator and weight denominator (§4.2 rollup rule) —
    either the section is ``not_graded`` (M4), or it is gradable but ungraded so far (M5).
    Returning 0 for either case would silently depress the average instead.
    """
    if s.grade_mode not in _GRADE_MODES:
        raise ValueError(f"unknown grade_mode {s.grade_mode!r}")
    if s.grade_mode == "not_graded":
        return None
    if s.grade is None:
        return None
    if s.grade_mode == "pass_fail":
        return _scale_pass_fail(s)
    return s.grade  # numeric, and rubric (pre-rolled per M7)


@dataclass(frozen=True)
class GradeTimeline:
    """The §6.10 timeline shape returned by a rollup.

    Reserved shape only; fields firm up in WP5.
    """

    report_id: str
    overall_grade: str | None = None
    entries: list[dict[str, object]] = field(default_factory=list)


def rollup(report_id: str) -> GradeTimeline:
    """Recompute and persist ``report.overall_grade``, returning its timeline.

    Sole writer of ``report.overall_grade``. Unimplemented until WP5.
    """
    raise NotImplementedError("scoring rollup lands in WP5")
