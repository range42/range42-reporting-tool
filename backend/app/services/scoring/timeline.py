"""The ARCHITECTURE §6.10 timeline shape (WP5 W5-2, M15/M16).

DELIBERATELY ORM-FREE. Nothing here imports a model or a session, so W5-S2 (#49) can build the
same entry shape for historical reports without dragging in the rollup's persistence
dependencies. Inputs are the plain dataclasses from ``rollup``.

M16 — ``evaluated_at`` PROVENANCE. There is no ``report.evaluated_at`` column (B5), so it is
derived: the latest ``completed_at`` across the report's evaluations, and NULL while any
evaluation is still outstanding. "Evaluated" therefore means every assigned evaluator has
finished, not merely that a grade exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.services.scoring.rollup import (
    EvaluationInput,
    SectionGradeInput,
    compute_section_value,
    has_mixed_grade_max,
)
from app.services.scoring.weighting import compute_weighted_average, quantize_grade


@dataclass(frozen=True)
class ReportMeta:
    """The report-level facts the timeline entry echoes back, free of ORM types."""

    report_id: str
    report_name: str
    report_type: str
    template_id: str
    due_at: datetime | None = None
    submitted_at: datetime | None = None


@dataclass(frozen=True)
class SectionGradeEntry:
    section_def_id: str
    name: str
    grade: Decimal | None
    weight: Decimal


@dataclass(frozen=True)
class TimelineEntry:
    """One evaluated report, in the ARCHITECTURE §6.10 timeline shape.

    Fields beyond §6.10 (grade_version, is_manual, mixed_scale, evaluator_count) are
    additive — the documented §6.10 field set is present and unchanged, so W5-S2's
    endpoints can serialize this directly. W5-S2 suppresses the additive ones for non-GA
    callers; they are exposed here because the rollup knows them and a second query would not.
    """

    report_id: str
    report_name: str
    report_type: str
    template_id: str
    due_at: datetime | None
    submitted_at: datetime | None
    evaluated_at: datetime | None
    overall_grade: Decimal | None
    section_grades: list[SectionGradeEntry]
    # additive
    grade_version: int
    is_manual: bool
    mixed_scale: bool
    evaluator_count: int


def compute_evaluated_at(evaluations: Sequence[EvaluationInput]) -> datetime | None:
    """M16 — the latest completion across evaluations, or None while any is outstanding.

    An empty evaluation set is also None: an unassigned report has not been evaluated.
    """
    if not evaluations:
        return None
    completions = [e.completed_at for e in evaluations]
    if any(c is None for c in completions):
        return None
    return max(c for c in completions if c is not None)


def aggregate_section_grades(evaluations: Sequence[EvaluationInput]) -> list[SectionGradeEntry]:
    """Per-section grades, aggregated across evaluators by ``aggregated_weight``.

    ``not_graded`` sections are omitted entirely — they are not part of the grading surface.
    A gradable section nobody has marked yet is listed with a null grade, so a client can
    render the row and show it as outstanding rather than silently dropping it.

    Values are the SCALED contributions (pass/fail already stretched onto its range, rubric
    pre-rolled), never the raw stored 0/1.
    """
    definitions: dict[str, SectionGradeInput] = {}
    contributions: dict[str, list[tuple[Decimal, Decimal]]] = {}
    for ev in evaluations:
        for s in ev.sections:
            if s.grade_mode == "not_graded":
                continue
            definitions.setdefault(s.section_def_id, s)
            value = compute_section_value(s)
            if value is not None:
                contributions.setdefault(s.section_def_id, []).append((value, ev.aggregated_weight))
    entries = []
    for section_def_id, defn in definitions.items():
        average = compute_weighted_average(contributions.get(section_def_id, []))
        entries.append(
            SectionGradeEntry(
                section_def_id=section_def_id,
                name=defn.name,
                grade=None if average is None else quantize_grade(average),
                weight=defn.grade_weight,
            )
        )
    order = {sid: defn.position for sid, defn in definitions.items()}
    return sorted(entries, key=lambda e: order[e.section_def_id])


def build_timeline_entry(
    report: ReportMeta,
    evaluations: Sequence[EvaluationInput],
    *,
    overall_grade: Decimal | None,
    grade_version: int,
    is_manual: bool,
) -> TimelineEntry:
    """Assemble one §6.10 entry from the report's facts and its evaluations.

    ``overall_grade`` is passed in rather than recomputed: the caller has already run the
    rollup, and a manual override (M9) must survive into the entry untouched.
    """
    all_sections = [s for ev in evaluations for s in ev.sections]
    return TimelineEntry(
        report_id=report.report_id,
        report_name=report.report_name,
        report_type=report.report_type,
        template_id=report.template_id,
        due_at=report.due_at,
        submitted_at=report.submitted_at,
        evaluated_at=compute_evaluated_at(evaluations),
        overall_grade=overall_grade,
        section_grades=aggregate_section_grades(evaluations),
        grade_version=grade_version,
        is_manual=is_manual,
        mixed_scale=has_mixed_grade_max(all_sections),
        evaluator_count=len(evaluations),
    )
