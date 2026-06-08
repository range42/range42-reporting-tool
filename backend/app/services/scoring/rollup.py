"""Scoring rollup (shape reservation — no impl yet).

SOLE-WRITER CONTRACT: this module is the *only* writer of ``report.overall_grade``.
It honors every grading mode — ``not_graded`` / ``manual`` / ``pass_fail`` /
``rubric`` / ``aggregated_weight`` — and returns the §6.10 timeline shape so
callers can render grade history. No other code path may set ``overall_grade``.
Implementation lands in WP5.
"""

from dataclasses import dataclass, field


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
