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
    return s.grade  # numeric, and rubric (pre-rolled per M7); pass_fail scaling lands in Task 2


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
