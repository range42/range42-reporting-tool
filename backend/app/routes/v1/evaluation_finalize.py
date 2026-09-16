"""Finalize, reopen, unassign, and the report-level finalize gate.

The dependency runs one way, this module -> ``evaluations``; the shared response builder lives
in ``app.services.evaluation`` so neither route module imports the other.

EVALUATOR ISOLATION: ``_assert_evaluation_access`` gates every path that is not Global-Admin-only.

LOCK ORDER — report, THEN evaluation, in every handler here. Acquiring these two locks in the
opposite order deadlocks in production.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.db import get_db
from app.core.permissions import EVALUATIONS_WRITE
from app.core.rbac import get_current_user, require_global_admin, require_permission
from app.models import Evaluation, Report, ReportSection, SectionGrade, TemplateSectionDef, User
from app.routes.v1.evaluations import (
    _BASE,
    _assert_evaluation_access,
    _get_evaluation,
)
from app.routes.v1.reports import _get_report
from app.schemas.common import DataEnvelope
from app.schemas.evaluation import (
    EvaluationBreakdownOut,
    FinalizeRequest,
    ReopenRequest,
    UnassignRequest,
)
from app.services.evaluation import breakdown, events
from app.services.evaluation.finalize_gate import is_gate_open, resolve_finalize_policy
from app.services.scoring import rollup
from app.services.workflow import state_machine

router = APIRouter(tags=["evaluations"])


# --- finalize -------------------------------------------------------------------------

# ``evaluated`` is finalizable too: under ``any_can_finalize`` the first finalize opens the gate
# while the other assigned evaluators are still grading, and they must not be stranded.
_FINALIZABLE_REPORT_STATUSES = frozenset({"under_evaluation", "evaluated"})


async def _get_report_for_update(db: AsyncSession, exercise_id: uuid.UUID, report_id: uuid.UUID) -> Report:
    """Fetch the report with its row locked, and with COMMITTED values.

    Serializes finalize / unassign / reopen against each other: all three read every sibling
    evaluation and then write the parent report. LOCK ORDER IS ALWAYS report-then-evaluation.

    ``populate_existing`` is load-bearing, not just the ``with_for_update``: the sessionmaker
    runs ``expire_on_commit=False``, so locking alone would leave the caller holding the
    snapshot it read before it began waiting. Lock and re-read must stay one operation.

    ``_get_report`` still runs first, for the 404 and the exercise scoping.
    """
    report = await _get_report(db, exercise_id, report_id)
    return (
        await db.execute(
            select(Report).where(Report.id == report.id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _ungraded_section_def_ids(db: AsyncSession, report_id: uuid.UUID, evaluation_id: uuid.UUID) -> list[str]:
    """Gradeable sections this evaluation has not scored.

    ``grade_mode='not_graded'`` sections are excluded — they can never block a finalize.
    """
    rows = (
        await db.execute(
            select(ReportSection.section_def_id)
            .join(TemplateSectionDef, TemplateSectionDef.id == ReportSection.section_def_id)
            .outerjoin(
                SectionGrade,
                (SectionGrade.report_section_id == ReportSection.id) & (SectionGrade.evaluation_id == evaluation_id),
            )
            .where(
                ReportSection.report_id == report_id,
                TemplateSectionDef.grade_mode != "not_graded",
                SectionGrade.id.is_(None),
            )
            .order_by(ReportSection.position)
        )
    ).scalars()
    return [str(sid) for sid in rows]


async def _assert_finalizable(db: AsyncSession, ev: Evaluation, report: Report, user: User) -> None:
    """Raise every rejection a finalize can produce, before the first mutation."""
    _assert_evaluation_access(ev, user)
    if ev.unassigned_at is not None:
        raise HTTPException(status_code=409, detail={"error": "evaluation_unassigned"})
    if ev.status == "completed":
        raise HTTPException(status_code=409, detail={"error": "already_finalized"})
    if report.status not in _FINALIZABLE_REPORT_STATUSES:
        raise HTTPException(status_code=409, detail={"error": "invalid_state", "status": report.status})
    missing = await _ungraded_section_def_ids(db, report.id, ev.id)
    if missing:
        raise HTTPException(status_code=409, detail={"error": "section_grade_missing", "section_def_ids": missing})


def _assert_reopenable(ev: Evaluation) -> None:
    """Raise every rejection a reopen can produce, before the first mutation.

    ORDER MATTERS: unassigned is checked FIRST, so a completed-then-unassigned evaluation is
    reported as unassigned rather than as ``not_finalized``.
    """
    if ev.unassigned_at is not None:
        raise HTTPException(status_code=409, detail={"error": "evaluation_unassigned"})
    if ev.status != "completed":
        raise HTTPException(status_code=409, detail={"error": "not_finalized", "status": ev.status})


async def _resolve_finalize_actor(
    db: AsyncSession, evaluation: Evaluation, body: FinalizeRequest, actor: User
) -> tuple[uuid.UUID, bool]:
    """Who is CREDITED with this finalize, and is it an admin override?

    An evaluation names exactly one evaluator, so ``on_behalf_of`` must name them.

    The returned id is the credited EVALUATOR. ``finalized_by`` is set to the actor at the call
    site, never to this value.
    """
    if body.on_behalf_of is None:
        return actor.id, False
    if not actor.is_global_admin:
        raise HTTPException(status_code=403, detail={"error": "not_global_admin"})
    if not (body.comment or "").strip():
        raise HTTPException(status_code=422, detail={"error": "comment_required"})
    try:
        target_id = uuid.UUID(body.on_behalf_of)
    except ValueError:
        raise HTTPException(status_code=422, detail={"error": "invalid_on_behalf_of"}) from None
    if (await db.execute(select(User.id).where(User.id == target_id))).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail={"error": "user_not_found", "user_id": body.on_behalf_of})
    if target_id != evaluation.evaluator_id:
        raise HTTPException(status_code=422, detail={"error": "on_behalf_of_mismatch"})
    return target_id, True


async def _settle_finalize_gate(
    db: AsyncSession,
    report: Report,
    *,
    exercise_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    actor_id: uuid.UUID,
    trigger: str,
    ip: str | None,
) -> tuple[bool, str]:
    """Ask the gate whether the report is finished, and transition it if so.

    Reads the facts through ``rollup.load_evaluation_facts`` — the SAME query the aggregate
    used — so the report is never declared evaluated over a different set of evaluations.

    ``trigger`` names the cause of the crossing: ``evaluation_finalized`` or
    ``evaluator_unassigned``.

    Returns ``(gate_satisfied, mode)``. Emits ``report.evaluated`` on the crossing.
    """
    mode = await resolve_finalize_policy(db, exercise_id)
    facts = await rollup.load_evaluation_facts(db, report.id)
    satisfied = is_gate_open(facts, mode)
    # Only an under_evaluation report has anywhere to go: ``evaluated -> evaluated`` is not a
    # legal edge.
    if satisfied and report.status == "under_evaluation":
        await state_machine.transition(
            db,
            report,
            target_status="evaluated",
            actor_id=actor_id,
            action="report.evaluated",
            details={"finalize_policy": mode, "evaluation_id": str(evaluation_id), "trigger": trigger},
            ip=ip,
        )
        # The emit seam, on the CROSSING only. Guarded by the same branch as the
        # transition so a later finalize on an already-evaluated report announces nothing.
        await events.emit_report_evaluated(db, report)
    return satisfied, mode


@router.post(_BASE + "/{evid}/finalize")
async def finalize_evaluation(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    evid: uuid.UUID,
    body: FinalizeRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(EVALUATIONS_WRITE)),
) -> DataEnvelope[EvaluationBreakdownOut]:
    """Mark this evaluator's work done, then settle the report-level gate.

    ORDER IS LOAD-BEARING: lock, guard, complete the evaluation, recompute the aggregate,
    THEN ask the gate — otherwise ``report.evaluated`` announces the previous grade.

    An evaluator finalizing their own work sends no body. A Global Admin may send
    ``on_behalf_of`` + ``comment`` to break a deadlock — see ``_resolve_finalize_actor``.
    """
    body = body or FinalizeRequest()
    report: Report = await _get_report_for_update(db, exercise_id, rid)
    ev = await _get_evaluation(db, report.id, evid)
    await _assert_finalizable(db, ev, report, user)
    credited_evaluator_id, is_override = await _resolve_finalize_actor(db, ev, body, user)

    ev.status = "completed"
    ev.completed_at = datetime.now(UTC)
    # ``finalized_by`` is the ACTOR, ``evaluator_id`` stays the credited evaluator.
    ev.finalized_by = user.id
    ev.finalize_is_admin_override = is_override
    ev.finalize_comment = body.comment if is_override else None
    await db.flush()

    # rollup stays the sole writer of overall_grade / grade_version.
    await rollup.recompute_report_grade(
        db, report, actor_id=user.id, trigger="evaluation.finalized", ip=client_ip(request)
    )
    satisfied, mode = await _settle_finalize_gate(
        db,
        report,
        exercise_id=exercise_id,
        evaluation_id=ev.id,
        actor_id=user.id,
        trigger="evaluation_finalized",
        ip=client_ip(request),
    )
    # One row per finalize, on the evaluation, whichever way the gate went — the override facts
    # must be recoverable even when the same request also emitted report.evaluated.
    await record_audit(
        db,
        user_id=user.id,
        action="evaluation.completed",
        resource_type="evaluation",
        resource_id=ev.id,
        details={
            "finalize_policy": mode,
            "finalize_gate_satisfied": satisfied,
            "is_admin_override": is_override,
            "credited_evaluator_id": str(credited_evaluator_id),
            "comment": ev.finalize_comment,
            "grade_version": report.grade_version,
        },
        ip=client_ip(request),
    )
    return DataEnvelope(data=await breakdown.build(db, report, user, exercise_id=exercise_id))


@router.post(_BASE + "/{evid}/unassign")
async def unassign_evaluator(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    evid: uuid.UUID,
    body: UnassignRequest,
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[EvaluationBreakdownOut]:
    """Global-Admin deadlock exit: drop an unavailable evaluator. Removes the seat entirely.

    SOFT, DELIBERATELY. Nothing is deleted and ``status`` is not rewritten: the evaluation and
    its section grades survive so a later dispute can still read them. ``unassigned_at IS NOT
    NULL`` alone takes the evaluator out of the counted set.

    ORDER IS LOAD-BEARING, as in finalize: lock, guard, mutate, recompute, THEN settle the gate.
    """
    report: Report = await _get_report_for_update(db, exercise_id, rid)  # report, then evaluation
    ev = await _get_evaluation(db, report.id, evid)
    if ev.unassigned_at is not None:
        # Not idempotent-by-silence: a second call must not re-run the recompute and bump
        # grade_version for a change that already happened.
        raise HTTPException(status_code=409, detail={"error": "already_unassigned"})
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail={"error": "reason_required"})

    ev.unassigned_at = datetime.now(UTC)
    ev.unassigned_by = user.id
    ev.unassign_reason = reason
    await db.flush()

    # rollup stays the sole writer of overall_grade / grade_version. Renormalization —
    # the dropped weight leaves the denominator, it does not rescale the survivors' grade.
    await rollup.recompute_report_grade(
        db, report, actor_id=user.id, trigger="evaluation.unassigned", ip=client_ip(request)
    )
    satisfied, mode = await _settle_finalize_gate(
        db,
        report,
        exercise_id=exercise_id,
        evaluation_id=ev.id,
        actor_id=user.id,
        trigger="evaluator_unassigned",
        ip=client_ip(request),
    )
    await record_audit(
        db,
        user_id=user.id,
        action="evaluation.unassigned",
        resource_type="evaluation",
        resource_id=ev.id,
        details={
            "evaluator_id": str(ev.evaluator_id),
            "reason": reason,
            # Redundant with the action name, but it keeps the audit-details shape
            # recognisable to a log consumer that greps for the flag.
            "is_admin_override": True,
            "finalize_gate_satisfied": satisfied,
            "overall_grade": f"{report.overall_grade:.2f}" if report.overall_grade is not None else None,
            "grade_version": report.grade_version,
        },
        ip=client_ip(request),
    )
    return DataEnvelope(data=await breakdown.build(db, report, user, exercise_id=exercise_id))


# --- reopen ---------------------------------------------------------------------------


@router.post(_BASE + "/{evid}/reopen")
async def reopen_evaluation(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    evid: uuid.UUID,
    body: ReopenRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(EVALUATIONS_WRITE)),
) -> DataEnvelope[EvaluationBreakdownOut]:
    """Return a finalized evaluation to grading. The assigned evaluator, or a Global Admin.

    THE ONLY un-finalize path, and still the only way back into grading: there is no
    edit-after-finalize. An evaluator revising work they already gave comes through here,
    with a reason, and finalizes again afterwards.

    A reopen produces a NEW grade version rather than an in-place edit — the original
    ``report.evaluated`` is not retractable, so supersession is the only mechanism available.

    LOCK ORDER — report, THEN evaluation, as finalize and unassign take it.

    The evaluator's WORK SURVIVES: section grades and overall feedback are untouched.

    A reopened evaluation still COUNTS towards the gate but no longer CONTRIBUTES a grade, so
    the aggregate falls back to the evaluations still completed, and to NULL when none remain.
    """
    body = body or ReopenRequest()
    report: Report = await _get_report_for_update(db, exercise_id, rid)  # report, then evaluation
    ev = await _get_evaluation(db, report.id, evid)
    _assert_evaluation_access(ev, user)
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail={"error": "reason_required"})
    _assert_reopenable(ev)

    # CAPTURED BEFORE the recompute below, which is the sole writer of grade_version.
    superseded_version = report.grade_version
    status_before = report.status

    ev.status = "in_progress"
    # Cleared, not preserved. A completion time on a non-complete row means two different
    # things depending on ``status``; the dispute trail lives in ``audit_log`` instead.
    ev.completed_at = None
    # The override fields belong to the finalize that just went away; left behind, they would
    # misattribute the NEXT finalize.
    ev.finalized_by = None
    ev.finalize_is_admin_override = False
    ev.finalize_comment = None
    ev.reopen_count += 1
    ev.reopened_at = datetime.now(UTC)
    ev.reopened_by = user.id
    await db.flush()

    # rollup stays the sole writer of overall_grade / grade_version.
    #
    # force_version_bump: a reopen is a publication even when the number does not move, so the
    # supersession event below cannot announce that version N supersedes version N.
    timeline = await rollup.recompute_report_grade(
        db,
        report,
        actor_id=user.id,
        trigger="evaluation.reopened",
        ip=client_ip(request),
        force_version_bump=True,
    )

    # Only a report that actually reached ``evaluated`` has anywhere to go; there is no
    # ``under_evaluation -> under_evaluation`` edge.
    if status_before == "evaluated":
        await state_machine.transition(
            db,
            report,
            target_status="under_evaluation",
            actor_id=user.id,
            action="report.reopened",
            details={
                "evaluation_id": str(ev.id),
                "superseded_grade_version": superseded_version,
            },
            ip=client_ip(request),
        )

    # One row per reopen, on the evaluation, whichever way the report went. This is where the
    # reason lives — it is deliberately kept off the event payload.
    await record_audit(
        db,
        user_id=user.id,
        action="evaluation.reopened",
        resource_type="evaluation",
        resource_id=ev.id,
        details={
            "evaluator_id": str(ev.evaluator_id),
            "reason": reason,
            # Distinguishes an evaluator revising their own work from an admin intervening.
            "is_self_reopen": user.id == ev.evaluator_id,
            "reopen_count": ev.reopen_count,
            "report_status_before": status_before,
            "superseded_grade_version": superseded_version,
            "grade_version": report.grade_version,
            "overall_grade": None if timeline.overall_grade is None else str(timeline.overall_grade),
        },
        ip=client_ip(request),
    )
    await events.emit_report_evaluation_reopened(db, report, superseded_grade_version=superseded_version)
    return DataEnvelope(data=await breakdown.build(db, report, user, exercise_id=exercise_id))
