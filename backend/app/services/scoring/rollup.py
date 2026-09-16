"""Scoring rollup: the grade arithmetic and the single write that publishes it.

SOLE-WRITER CONTRACT: this module is the *only* writer of ``report.overall_grade``. It honors
every grading mode — ``not_graded`` / ``manual`` / ``pass_fail`` / ``rubric`` /
``aggregated_weight`` — and returns the timeline shape so callers can render grade history.
No other code path may set ``overall_grade``.

STRUCTURE — a pure core wrapped in a thin persistence shell:

* The ``compute_*`` functions are pure: they take the ``*Input`` dataclasses below, touch no
  database and no ORM object, and hold all the grading arithmetic.
* ``recompute_report_grade`` is the shell: it loads rows, calls the pure core, and performs
  the single write, inside the caller's transaction.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.models import Evaluation, Report, ReportSection, ReportTemplate, SectionGrade, TemplateSectionDef
from app.services.scoring.aggregate import EvaluationFacts, aggregate_overall_grade, contributes_grade
from app.services.scoring.weighting import compute_weighted_average, quantize_grade

if TYPE_CHECKING:  # timeline imports rollup, so keep this one-directional at runtime
    from app.services.scoring.timeline import TimelineEntry

logger = structlog.get_logger(__name__)

_GRADE_MODES = frozenset({"numeric", "pass_fail", "rubric", "not_graded"})


@dataclass(frozen=True)
class SectionGradeInput:
    """One section's grading state, flattened from ``template_section_def`` + ``section_grade``.

    ``grade`` is whatever is stored on the row: the numeric grade, 0/1 for ``pass_fail``
    (scaled here, not at write time), or the pre-rolled rubric value. ``None`` means no grade
    has been recorded yet.
    """

    section_def_id: str
    name: str
    grade_mode: str
    grade: Decimal | None
    grade_min: Decimal | None
    grade_max: Decimal | None
    grade_weight: Decimal
    # Template ordering, echoed into the timeline so sections render in authoring order.
    position: int = 0


@dataclass(frozen=True)
class EvaluationInput:
    """One evaluator's contribution to a report: their sections plus their aggregation weight."""

    evaluation_id: str
    evaluator_id: str
    aggregated_weight: Decimal
    sections: tuple[SectionGradeInput, ...] = ()
    # Feeds the derived ``evaluated_at``; None while this evaluator is still working.
    completed_at: datetime | None = None
    # Whether this evaluation feeds the GRADE. A resolved boolean rather than
    # ``status``/``unassigned_at`` so the pure layer stays free of the predicate's rules. The
    # timeline needs both answers at once: section grades exclude non-contributors, while
    # ``evaluated_at`` and ``evaluator_count`` keep counting them.
    contributes: bool = True


def _dec(v: object) -> Decimal:
    """Coerce a JSONB scalar to Decimal via str, so a stored float never leaks binary error."""
    return Decimal(str(v))


def _resolve_bounds(grade_min: Decimal | None, grade_max: Decimal | None) -> tuple[Decimal, Decimal]:
    """The section's output range, defaulting to [0, 1] when the template declares none.

    Non-numeric sections on a mixed template should declare bounds — see
    ``section_invariant_error`` — or they under-score beside numeric siblings.
    """
    low = grade_min if grade_min is not None else Decimal(0)
    high = grade_max if grade_max is not None else Decimal(1)
    return low, high


def _criterion_weight(c: dict[str, Any]) -> Decimal:
    """The rubric_criteria shape does not mark ``weight`` required; absent means 1."""
    w = c.get("weight")
    return Decimal(1) if w is None else _dec(w)


def _criterion_max(c: dict[str, Any]) -> Decimal:
    m = c.get("max_score")
    return Decimal(0) if m is None else _dec(m)


def compute_rubric_rollup(
    criteria: list[dict[str, Any]] | None,
    scores: list[dict[str, Any]] | None,
    *,
    grade_min: Decimal | None,
    grade_max: Decimal | None,
) -> Decimal | None:
    """Pre-roll rubric criteria into one section grade.

    Each criterion is scored as a fraction of its OWN maximum; those fractions are averaged by
    criterion weight and stretched onto the section's range:

        normalized = Σ((score / max_score) · weight) / Σ(weight)
        grade      = grade_min + normalized · (grade_max - grade_min)

    ``weight`` alone controls influence; ``max_score`` only sets granularity. Changing this
    formula silently re-grades every rubric section ever scored — treat it as a data migration.

    Criteria with no submitted score are excluded from BOTH sums. Scores naming a criterion
    that no longer exists on the template are ignored, and a score above its criterion's
    maximum is clamped, so a template edit cannot break or inflate an already-graded report.
    Returns None when nothing can be computed.
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
    low, high = _resolve_bounds(grade_min, grade_max)
    return low + normalized * (high - low)


def _scale_pass_fail(s: SectionGradeInput) -> Decimal:
    """Scale a stored pass/fail 0/1 onto the section's range: a pass is worth grade_max.

    Scaling happens here rather than at write time, so re-ranging a template re-scores old
    reports instead of freezing the number. A section with no declared bounds scales onto
    [0, 1], where a pass counts as 1.
    """
    if s.grade not in (Decimal(0), Decimal(1)):
        raise ValueError(f"pass_fail grade must be 0 or 1, got {s.grade}")
    low, high = _resolve_bounds(s.grade_min, s.grade_max)
    return low + s.grade * (high - low)


def compute_section_value(s: SectionGradeInput) -> Decimal | None:
    """The scaled value this section contributes, or None when it contributes nothing.

    None means EXCLUDED FROM BOTH the numerator and the weight denominator — the section is
    either ``not_graded`` or gradable but ungraded so far. Returning 0 would depress the
    average instead.
    """
    if s.grade_mode not in _GRADE_MODES:
        raise ValueError(f"unknown grade_mode {s.grade_mode!r}")
    if s.grade_mode == "not_graded":
        return None
    if s.grade is None:
        return None
    if s.grade_mode == "pass_fail":
        return _scale_pass_fail(s)
    return s.grade  # numeric, and rubric (pre-rolled)


def has_mixed_grade_max(sections: Sequence[SectionGradeInput]) -> bool:
    """Whether the contributing sections disagree about their upper bound.

    The rollup keeps the RAW weighted average and does not normalize across scales, so a 0-100
    section averaged with a 0-10 one dominates. This flag lets the caller warn; the maths does
    not change. Sections that contribute nothing are ignored.
    """
    maxima = {s.grade_max for s in sections if s.grade_mode != "not_graded" and s.grade_max is not None}
    return len(maxima) > 1


def compute_evaluation_grade(ev: EvaluationInput) -> Decimal | None:
    """One evaluator's overall grade for a report.

    Sections contributing None — ``not_graded`` or ungraded — are excluded from BOTH the
    numerator and the weight denominator. A zero-weight section is excluded too, to avoid 0/0.
    """
    pairs: list[tuple[Decimal, Decimal]] = []
    for s in ev.sections:
        if s.grade_weight < 0:
            raise ValueError(f"negative grade_weight on section {s.section_def_id}")
        value = compute_section_value(s)
        if value is not None and s.grade_weight != 0:
            pairs.append((value, s.grade_weight))
    if has_mixed_grade_max(ev.sections):
        logger.warning(
            "rollup_mixed_grade_max",
            evaluation_id=ev.evaluation_id,
            detail="sections disagree on grade_max; the raw weighted average is used (M12)",
        )
    avg = compute_weighted_average(pairs)
    return None if avg is None else quantize_grade(avg)


# The report-level aggregate lives in ``aggregate.aggregate_overall_grade``, which reads the
# status and ``unassigned_at`` that ``EvaluationInput`` deliberately never carries.


@dataclass(frozen=True)
class GradeTimeline:
    """What ``recompute_report_grade`` hands back: the persisted grade plus its timeline entry.

    ``entry`` carries the full timeline shape so a caller can render grade history without a
    second query. It is None only when the report has no evaluations to describe.
    """

    report_id: str
    overall_grade: Decimal | None = None
    grade_version: int = 0
    entry: TimelineEntry | None = None


# ``recompute_report_grade`` below is the entry point; it takes the caller's session so the
# write honours the caller's transaction.


# --- persistence shell --------------------------------------------------------
#
# Everything above is pure. Everything below touches the database, and only through the
# caller's session — it never commits.


def _bump_grade_version(report: Report) -> None:
    """THE ONLY PLACE ``grade_version`` IS INCREMENTED.

    Monotonic by construction: +1, never a recomputed or reset value, so a version is never
    reused for a different grade. Every caller must funnel through here; the sole-writer guard
    test asserts this function is unique.
    """
    report.grade_version = report.grade_version + 1


async def _lock_report_row(db: AsyncSession, report_id: uuid.UUID) -> None:
    """Serialize concurrent recomputes of the same report.

    SELECT ... FOR UPDATE, so two evaluators saving a grade at the same moment cannot both
    write version+1 and publish two different grades under one version.
    """
    await db.execute(select(Report.id).where(Report.id == report_id).with_for_update())


async def _load_evaluation_inputs(db: AsyncSession, report: Report) -> list[tuple[EvaluationInput, Evaluation]]:
    """Every evaluation of ``report`` as a pure input, paired with its ORM row.

    THE ONLY ORM-TOUCHING LOAD in this module. Three queries regardless of how many evaluators
    or sections exist — evaluations, section definitions, then all grades at once. A
    per-evaluation or per-section query here becomes an N+1 on every grade save.
    """
    evaluations = (
        (await db.execute(select(Evaluation).where(Evaluation.report_id == report.id).order_by(Evaluation.created_at)))
        .scalars()
        .all()
    )
    sections = (
        await db.execute(
            select(ReportSection, TemplateSectionDef)
            .join(TemplateSectionDef, TemplateSectionDef.id == ReportSection.section_def_id)
            .where(ReportSection.report_id == report.id)
            .order_by(ReportSection.position)
        )
    ).all()
    if not evaluations:
        return []
    grades = (
        (await db.execute(select(SectionGrade).where(SectionGrade.evaluation_id.in_([e.id for e in evaluations]))))
        .scalars()
        .all()
    )
    by_evaluation: dict[uuid.UUID, dict[uuid.UUID, SectionGrade]] = {}
    for g in grades:
        by_evaluation.setdefault(g.evaluation_id, {})[g.report_section_id] = g

    paired: list[tuple[EvaluationInput, Evaluation]] = []
    for ev in evaluations:
        own = by_evaluation.get(ev.id, {})
        inputs = tuple(
            SectionGradeInput(
                section_def_id=str(defn.id),
                name=defn.name,
                grade_mode=defn.grade_mode,
                grade=own[section.id].grade if section.id in own else None,
                grade_min=_dec(defn.grade_min) if defn.grade_min is not None else None,
                grade_max=_dec(defn.grade_max) if defn.grade_max is not None else None,
                grade_weight=_dec(defn.grade_weight),
                position=section.position,
            )
            for section, defn in sections
        )
        paired.append(
            (
                EvaluationInput(
                    evaluation_id=str(ev.id),
                    evaluator_id=str(ev.evaluator_id),
                    aggregated_weight=ev.aggregated_weight,
                    sections=inputs,
                    completed_at=ev.completed_at,
                    contributes=contributes_grade(evaluation_facts(ev)),
                ),
                ev,
            )
        )
    return paired


def evaluation_facts(ev: Evaluation) -> EvaluationFacts:
    """Project one ORM row onto the narrow shape aggregation and the gate agree on.

    The single mapping site: ``unassigned_at IS NULL`` is translated to ``is_unassigned`` here
    and nowhere else, so the numerator and the gate can never disagree about who counts.
    """
    return EvaluationFacts(
        evaluation_id=str(ev.id),
        status=ev.status,
        overall_grade=ev.overall_grade,
        aggregated_weight=ev.aggregated_weight,
        is_unassigned=ev.unassigned_at is not None,
    )


async def load_evaluation_facts(db: AsyncSession, report_id: uuid.UUID) -> list[EvaluationFacts]:
    """Every evaluation of ``report_id`` as aggregation facts. One SELECT, shared with the gate.

    Filters NOTHING: the counted predicate decides what counts, not the SQL, so an admin-facing
    breakdown can still show the unassigned rows this same query returns. Ordered by
    ``created_at`` so two callers see the same sequence.
    """
    rows = (
        (await db.execute(select(Evaluation).where(Evaluation.report_id == report_id).order_by(Evaluation.created_at)))
        .scalars()
        .all()
    )
    return [evaluation_facts(ev) for ev in rows]


async def _timeline_for(
    db: AsyncSession,
    report: Report,
    evaluations: Sequence[tuple[EvaluationInput, Evaluation]],
    *,
    is_manual: bool,
) -> GradeTimeline:
    """Wrap the persisted state in the timeline shape. Imported here, not at module scope,
    because ``timeline`` imports this module."""
    from app.services.scoring.timeline import ReportMeta, build_timeline_entry

    report_type = (
        await db.execute(select(ReportTemplate.report_type).where(ReportTemplate.id == report.template_id))
    ).scalar_one_or_none()
    entry = build_timeline_entry(
        ReportMeta(
            report_id=str(report.id),
            report_name=report.name,
            report_type=report_type or "",
            template_id=str(report.template_id),
            due_at=report.due_at,
            submitted_at=report.submitted_at,
        ),
        [i for i, _ in evaluations],
        overall_grade=report.overall_grade,
        grade_version=report.grade_version,
        is_manual=is_manual,
    )
    return GradeTimeline(
        report_id=str(report.id),
        overall_grade=report.overall_grade,
        grade_version=report.grade_version,
        entry=entry,
    )


async def load_evaluation_inputs(db: AsyncSession, report: Report) -> list[EvaluationInput]:
    """Every evaluation of ``report`` as a pure input, ORM rows dropped.

    Unfiltered on purpose: each input carries its own ``contributes`` verdict, so a consumer
    keeps the non-contributors it still needs to count. ``aggregate_section_grades`` honours
    the flag.
    """
    return [inp for inp, _row in await _load_evaluation_inputs(db, report)]


async def recompute_report_grade(
    db: AsyncSession,
    report: Report,
    *,
    actor_id: uuid.UUID | None = None,
    trigger: str = "section_grade.saved",
    ip: str | None = None,
    force_version_bump: bool = False,
) -> GradeTimeline:
    """Recompute and persist grades for ``report``, returning its timeline entry.

    SOLE WRITER of ``report.overall_grade``, ``evaluation.overall_grade`` and
    ``report.grade_version``. Runs inside the CALLER'S transaction and never commits.

    Per-evaluator grades are always recomputed. The report-level grade is skipped when
    ``report.overall_grade_is_manual`` is true, and ``grade_version`` is then NOT incremented
    because nothing new was published.

    ``force_version_bump`` publishes a new version even when the number is unchanged. The
    default (off) is right for a grade save; a reopen needs it, because the report left
    ``evaluated`` and its grade now rests on fewer evaluations. The caller supplies the intent,
    never the increment.
    """
    await _lock_report_row(db, report.id)
    evaluations = await _load_evaluation_inputs(db, report)
    for ev_input, ev_row in evaluations:
        ev_row.overall_grade = compute_evaluation_grade(ev_input)

    if report.overall_grade_is_manual:
        await db.flush()
        return await _timeline_for(db, report, evaluations, is_manual=True)

    # Built from the ORM rows just written above, so the aggregate sees this save's per-evaluator
    # grades rather than the values the row held on load.
    new_grade = aggregate_overall_grade([evaluation_facts(row) for _, row in evaluations])
    # Numeric comparison, never str(): NUMERIC(5,2) round-trips as Decimal("8.00") while the
    # fresh computation gives Decimal("8"). Those are ==; their str() forms are not.
    if new_grade != report.overall_grade or force_version_bump:
        previous = report.overall_grade
        report.overall_grade = new_grade
        _bump_grade_version(report)
        await db.flush()
        await record_audit(
            db,
            user_id=actor_id,
            action="report.grade_recomputed",
            resource_type="report",
            resource_id=report.id,
            details={
                "overall_grade": str(new_grade) if new_grade is not None else None,
                "previous": str(previous) if previous is not None else None,
                "grade_version": report.grade_version,
                "trigger": trigger,
            },
            ip=ip,
        )
    else:
        await db.flush()
    return await _timeline_for(db, report, evaluations, is_manual=False)


async def set_manual_grade(
    db: AsyncSession,
    report: Report,
    value: Decimal | None,
    *,
    actor_id: uuid.UUID | None,
    reason: str,
    ip: str | None = None,
) -> GradeTimeline:
    """Override ``report.overall_grade`` by hand, or clear the override.

    Lives in this module so the sole-writer contract holds literally. ``value=None`` clears the
    override and recomputes immediately, so the report never sits on a stale manual number.
    """
    if value is None:
        report.overall_grade_is_manual = False
        await db.flush()
        await record_audit(
            db,
            user_id=actor_id,
            action="report.grade_set_manually",
            resource_type="report",
            resource_id=report.id,
            details={"overall_grade": None, "cleared": True, "reason": reason},
            ip=ip,
        )
        return await recompute_report_grade(db, report, actor_id=actor_id, trigger="manual_override_cleared", ip=ip)

    await _lock_report_row(db, report.id)
    report.overall_grade = quantize_grade(value)
    report.overall_grade_is_manual = True
    _bump_grade_version(report)
    await db.flush()
    await record_audit(
        db,
        user_id=actor_id,
        action="report.grade_set_manually",
        resource_type="report",
        resource_id=report.id,
        details={
            "overall_grade": str(report.overall_grade),
            "grade_version": report.grade_version,
            "reason": reason,
        },
        ip=ip,
    )
    evaluations = await _load_evaluation_inputs(db, report)
    return await _timeline_for(db, report, evaluations, is_manual=True)
