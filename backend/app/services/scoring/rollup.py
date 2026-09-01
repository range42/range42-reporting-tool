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

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.models import Evaluation, Report, ReportSection, ReportTemplate, SectionGrade, TemplateSectionDef

if TYPE_CHECKING:  # timeline imports rollup, so keep this one-directional at runtime
    from app.services.scoring.timeline import TimelineEntry

logger = structlog.get_logger(__name__)

_GRADE_MODES = frozenset({"numeric", "pass_fail", "rubric", "not_graded"})

_CENTS = Decimal("0.01")
# report.overall_grade and section_grade.grade are both NUMERIC(5,2).
_MAX_NUMERIC_5_2 = Decimal("999.99")


class RollupOverflow(Exception):
    """A computed grade exceeds NUMERIC(5,2). Indicates a template grade_max misconfiguration."""


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
    # Template ordering, echoed into the §6.10 timeline so sections render in authoring order.
    position: int = 0


@dataclass(frozen=True)
class EvaluationInput:
    """One evaluator's contribution to a report: their sections plus their aggregation weight."""

    evaluation_id: str
    evaluator_id: str
    aggregated_weight: Decimal
    sections: tuple[SectionGradeInput, ...] = ()
    # M16 — feeds the derived ``evaluated_at``; None while this evaluator is still working.
    completed_at: datetime | None = None


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
    grade_min: Decimal | None,
    grade_max: Decimal | None,
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
    low, high = _resolve_bounds(grade_min, grade_max)
    return low + normalized * (high - low)


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


def has_mixed_grade_max(sections: Sequence[SectionGradeInput]) -> bool:
    """Whether the contributing sections disagree about their upper bound.

    M12 keeps the RAW weighted average and does not normalize across scales, so a 0-100
    section averaged with a 0-10 one legitimately dominates. That is almost always a template
    mistake rather than an intent, hence the flag — the caller warns, the maths does not change.
    Sections that contribute nothing are ignored; their bounds never reach the average.
    """
    maxima = {s.grade_max for s in sections if s.grade_mode != "not_graded" and s.grade_max is not None}
    return len(maxima) > 1


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
    Shared with Task 5's report-level aggregation; there is deliberately one implementation.
    """
    total_weight = sum((w for _, w in pairs), Decimal(0))
    if total_weight == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 28
        return sum((v * w for v, w in pairs), Decimal(0)) / total_weight


def compute_evaluation_grade(ev: EvaluationInput) -> Decimal | None:
    """One evaluator's overall grade for a report.

    Sections contributing None — ``not_graded`` (M4) or ungraded (M5) — are excluded from BOTH
    the numerator and the weight denominator. A zero-weight section is excluded too: it would
    add nothing to either sum, and keeping it risks a 0/0.
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


def _contributing_evaluations(
    graded: Sequence[tuple[EvaluationInput, Decimal]],
) -> list[tuple[EvaluationInput, Decimal]]:
    """Which evaluations feed report.overall_grade.

    W5-2 (provisional): every evaluation with at least one graded section, so a grade is
    visible before anyone finalizes. W5-3 REPLACES THIS BODY with the
    scoring_config.finalize_policy branch (G-6: all_must_finalize -> only status='completed'
    contribute; any_can_finalize -> this rule stands). SINGLE SEAM — do not scatter the policy.

    Takes already-computed (evaluation, grade) pairs so ``compute_evaluation_grade`` runs once
    per evaluation; filtering raw inputs here would double every section's arithmetic.
    """
    return list(graded)


def compute_report_grade(evaluations: Sequence[EvaluationInput]) -> Decimal | None:
    """Σ(evaluation grade × aggregated_weight) / Σ aggregated_weight (§4.2).

    An evaluation with nothing graded yet contributes neither a value nor its weight, so an
    assigned-but-unstarted evaluator cannot drag the report down. None when nothing
    contributes — the caller persists that as SQL NULL, never 0.
    """
    graded = [(e, g) for e in evaluations if (g := compute_evaluation_grade(e)) is not None]
    pairs = [(g, e.aggregated_weight) for e, g in _contributing_evaluations(graded)]
    avg = compute_weighted_average(pairs)
    return None if avg is None else quantize_grade(avg)


@dataclass(frozen=True)
class GradeTimeline:
    """What ``recompute_report_grade`` hands back: the persisted grade plus its §6.10 entry.

    ``entry`` carries the full timeline shape so a caller can render grade history without a
    second query. It is None only when the report has no evaluations to describe.
    """

    report_id: str
    overall_grade: Decimal | None = None
    grade_version: int = 0
    entry: TimelineEntry | None = None


# The WP1 shape reservation ``rollup(report_id)`` is gone: ``recompute_report_grade`` below is
# the real entry point, and it needs the caller's session to honour the transaction contract
# that a module-level function could not.


# --- persistence shell (M3) ---------------------------------------------------
#
# Everything above is pure. Everything below touches the database, and only through the
# caller's session — it never commits. Keeping the boundary here is what lets the grading
# rules be tested without a database at all.


def _bump_grade_version(report: Report) -> None:
    """D3 — THE ONLY PLACE ``grade_version`` IS INCREMENTED.

    Monotonic by construction: +1, never a recomputed or reset value, so a version can never
    be reused for a different grade. Every caller must funnel through here — a second
    increment site is how the counter starts lying to consumers who use it to detect stale
    published grades. Task 10's sole-writer guard asserts this function is unique.
    """
    report.grade_version = report.grade_version + 1


async def _lock_report_row(db: AsyncSession, report_id: uuid.UUID) -> None:
    """Serialize concurrent recomputes of the same report (B9).

    Two evaluators saving a grade at the same moment would otherwise read the same
    ``grade_version``, both write version+1, and publish two different grades under one
    version. SELECT ... FOR UPDATE makes the second wait for the first to commit, so the
    versions stay strictly monotonic. Contention is per-report and the section is short.
    """
    await db.execute(select(Report.id).where(Report.id == report_id).with_for_update())


async def _load_evaluation_inputs(db: AsyncSession, report: Report) -> list[tuple[EvaluationInput, Evaluation]]:
    """Every evaluation of ``report`` as a pure input, paired with its ORM row.

    THE ONLY ORM-TOUCHING LOAD in this module. Three queries regardless of how many
    evaluators or sections exist — evaluations, section definitions, then all grades at once.
    A per-evaluation or per-section query here becomes an N+1 on every grade save.
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
                ),
                ev,
            )
        )
    return paired


async def _timeline_for(
    db: AsyncSession,
    report: Report,
    evaluations: Sequence[tuple[EvaluationInput, Evaluation]],
    *,
    is_manual: bool,
) -> GradeTimeline:
    """Wrap the persisted state in the §6.10 shape. Imported here, not at module scope,
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


async def recompute_report_grade(
    db: AsyncSession,
    report: Report,
    *,
    actor_id: uuid.UUID | None = None,
    trigger: str = "section_grade.saved",
    ip: str | None = None,
) -> GradeTimeline:
    """Recompute and persist grades for ``report``, returning its §6.10 timeline.

    A7 SOLE WRITER of ``report.overall_grade``, ``evaluation.overall_grade`` and (D3)
    ``report.grade_version``. Runs inside the CALLER'S transaction — never commits, so a
    failure later in the request rolls the grade back with everything else.

    Per-evaluator grades are always recomputed. The report-level grade is skipped when
    ``report.overall_grade_is_manual`` is true (M9), and ``grade_version`` is then NOT
    incremented (D3) because nothing new was published.
    """
    await _lock_report_row(db, report.id)
    evaluations = await _load_evaluation_inputs(db, report)
    for ev_input, ev_row in evaluations:
        ev_row.overall_grade = compute_evaluation_grade(ev_input)

    if report.overall_grade_is_manual:
        await db.flush()
        return await _timeline_for(db, report, evaluations, is_manual=True)

    new_grade = compute_report_grade([i for i, _ in evaluations])
    # Numeric comparison, never str(): NUMERIC(5,2) round-trips as Decimal("8.00") while the
    # fresh computation gives Decimal("8"). Those are ==; their str() forms are not, and
    # comparing strings would bump grade_version on every single save.
    if new_grade != report.overall_grade:
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
    """Override ``report.overall_grade`` by hand, or clear the override (M9).

    Lives in this module so M2 holds literally: every write to ``overall_grade`` goes through
    ``rollup``. ``value=None`` clears the override and hands control back to the computation,
    recomputing immediately so the report never sits on a stale manual number.
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
