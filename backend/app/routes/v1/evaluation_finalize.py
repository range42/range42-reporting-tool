"""Finalize, gate settling and the D2 deadlock exit (WP5 W5-3).

Split out of ``evaluations.py``, which owns the W5-1 CRUD surface. The cut is by SLICE, not by
verb: everything here exists because a report has SEVERAL evaluators, and it shares one idea —
an evaluation stops being editable and the report-level gate is re-asked. W5-4's reopen lands
here too, on the same ``_settle_finalize_gate``.

The dependency runs one way, this module -> ``evaluations``, and must stay that way. The
response builder both modules need lives in ``app.services.evaluation`` rather than in either
route module, so neither has to import the other to build a payload.

D1 — EVALUATOR ISOLATION applies here exactly as in ``evaluations.py``: ``_assert_evaluation_access``
gates every path that is not already Global-Admin-only.
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
    _evaluation_out,
    _get_evaluation,
)
from app.routes.v1.reports import _get_report
from app.schemas.common import DataEnvelope
from app.schemas.evaluation import EvaluationFinalizeOut, FinalizeRequest, UnassignRequest
from app.services.evaluation.finalize_gate import is_gate_open, resolve_finalize_policy
from app.services.scoring import rollup
from app.services.workflow import state_machine

router = APIRouter(tags=["evaluations"])


# --- W5-3: finalize -------------------------------------------------------------------

# An evaluator may finalize their own work while the report is under evaluation OR already
# evaluated. The second case is ``any_can_finalize``: the first finalize opens the gate and the
# report becomes ``evaluated`` immediately, but the other assigned evaluators are still
# mid-grading. Refusing them would strand their evaluations permanently — un-finalizable
# through no fault of theirs, and invisible in the breakdown — so the gate opening must not
# double as a deadline. Their later finalize still joins the aggregate and publishes a new
# grade_version, which is how a consumer notices the number was refined.
_FINALIZABLE_REPORT_STATUSES = frozenset({"under_evaluation", "evaluated"})


async def _lock_report(db: AsyncSession, report_id: uuid.UUID) -> None:
    """Serialize concurrent finalizes of the same report, BEFORE the guards run.

    Two evaluators pressing Finalize at the same moment would otherwise both read a gate that
    is still closed and neither would transition the report. Locking first means the second
    waits, re-reads the first one's committed ``completed`` row, and settles the gate.
    """
    await db.execute(select(Report.id).where(Report.id == report_id).with_for_update())


async def _ungraded_section_def_ids(db: AsyncSession, report_id: uuid.UUID, evaluation_id: uuid.UUID) -> list[str]:
    """Gradeable sections this evaluation has not scored (§7.2).

    ``grade_mode='not_graded'`` sections are excluded — they are not gradeable, so they can
    never block a finalize.
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
    """Every rejection a finalize can raise, before the first mutation.

    Extracted so W5-4's re-finalize path reuses it verbatim rather than restating the guards
    and drifting from them.
    """
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


async def _resolve_finalize_actor(
    db: AsyncSession, evaluation: Evaluation, body: FinalizeRequest, actor: User
) -> tuple[uuid.UUID, bool]:
    """Who is CREDITED with this finalize, and is it an admin override?

    Mirrors ``reports.py::_resolve_on_behalf_of`` (§4.2 deadlock resolution) with one extra
    check the approval chain cannot make: an approval step names a *role*, which many users may
    satisfy, but an evaluation names exactly one evaluator — so ``on_behalf_of`` must name them.
    The stricter check is available here, so it is taken.

    The returned id is the credited EVALUATOR. ``finalized_by`` is set to the actor at the call
    site, never to this value: conflating them is how the dispute trail starts lying about who
    pressed the button.
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

    Reads the facts back through ``rollup.load_evaluation_facts`` — the SAME query the
    aggregate used — so the report can never be declared evaluated over a different set of
    evaluations than the one its grade was computed from.

    ``trigger`` names the cause of the crossing — ``evaluation_finalized`` when the last
    evaluator pressed the button, ``evaluator_unassigned`` when an admin removed the one who
    never would. Same edge, opposite stories, and a dispute needs to tell them apart.

    Returns ``(gate_satisfied, mode)``. The report.evaluated event seam (L11) is Task 11's.
    """
    mode = await resolve_finalize_policy(db, exercise_id)
    facts = await rollup.load_evaluation_facts(db, report.id)
    satisfied = is_gate_open(facts, mode)
    # Only an under_evaluation report has anywhere to go: ``evaluated -> evaluated`` is not a
    # legal edge, and attempting it on a later finalize would raise InvalidTransition and emit
    # a second report.evaluated row for one crossing.
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
) -> DataEnvelope[EvaluationFinalizeOut]:
    """Mark this evaluator's work done, then settle the report-level gate (§7.2).

    ORDER IS LOAD-BEARING: lock, guard, complete the evaluation, recompute the aggregate,
    THEN ask the gate. A gate settled before the recompute would fire ``report.evaluated``
    carrying the previous grade — announcing a number that the same request then changes.

    An evaluator finalizing their own work sends no body. A Global Admin may send
    ``on_behalf_of`` + ``comment`` to break a deadlock (D2) — see ``_resolve_finalize_actor``.
    """
    body = body or FinalizeRequest()
    report: Report = await _get_report(db, exercise_id, rid)
    await _lock_report(db, report.id)
    ev = await _get_evaluation(db, report.id, evid)
    await _assert_finalizable(db, ev, report, user)
    credited_evaluator_id, is_override = await _resolve_finalize_actor(db, ev, body, user)

    ev.status = "completed"
    ev.completed_at = datetime.now(UTC)
    # ``finalized_by`` is the ACTOR, ``evaluator_id`` stays the credited evaluator (D2).
    ev.finalized_by = user.id
    ev.finalize_is_admin_override = is_override
    ev.finalize_comment = body.comment if is_override else None
    await db.flush()

    # A7: rollup stays the sole writer of overall_grade / grade_version.
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
    return DataEnvelope(
        data=EvaluationFinalizeOut(
            evaluation=await _evaluation_out(db, ev),
            report_status=report.status,
            finalize_gate_satisfied=satisfied,
            finalize_policy=mode,
            overall_grade=report.overall_grade,
            grade_version=report.grade_version,
        )
    )


@router.post(_BASE + "/{evid}/unassign")
async def unassign_evaluator(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    evid: uuid.UUID,
    body: UnassignRequest,
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[EvaluationFinalizeOut]:
    """Global-Admin deadlock exit (D2, half two): drop an unavailable evaluator.

    Half one finalizes IN the absent evaluator's name; this half removes the seat entirely,
    for when there is no grade to publish on their behalf. Mirrors the ARCHITECTURE §4.2
    approval-chain override pattern.

    SOFT, DELIBERATELY (L8). Nothing is deleted and ``status`` is not rewritten: the evaluation
    and its section grades survive so a later dispute can still read what the removed evaluator
    had done. ``unassigned_at IS NOT NULL`` alone takes them out of the L7 counted set.

    ORDER IS LOAD-BEARING, exactly as in finalize: lock, guard, mutate, recompute, THEN settle
    the gate — a gate settled first would announce a grade the same request goes on to change.
    """
    report: Report = await _get_report(db, exercise_id, rid)
    await _lock_report(db, report.id)  # lock order: report, then evaluation
    ev = await _get_evaluation(db, report.id, evid)
    if ev.unassigned_at is not None:
        # Not idempotent-by-silence: a second call must not re-run the recompute and bump
        # grade_version (L9) for a change that already happened.
        raise HTTPException(status_code=409, detail={"error": "already_unassigned"})
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail={"error": "reason_required"})

    ev.unassigned_at = datetime.now(UTC)
    ev.unassigned_by = user.id
    ev.unassign_reason = reason
    await db.flush()

    # A7: rollup stays the sole writer of overall_grade / grade_version. L5 renormalization —
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
            # Redundant with the action name, but it keeps the WP4 audit-details shape
            # recognisable to a log consumer that greps for the flag.
            "is_admin_override": True,
            "finalize_gate_satisfied": satisfied,
            "overall_grade": f"{report.overall_grade:.2f}" if report.overall_grade is not None else None,
            "grade_version": report.grade_version,
        },
        ip=client_ip(request),
    )
    return DataEnvelope(
        data=EvaluationFinalizeOut(
            evaluation=await _evaluation_out(db, ev),
            report_status=report.status,
            finalize_gate_satisfied=satisfied,
            finalize_policy=mode,
            overall_grade=report.overall_grade,
            grade_version=report.grade_version,
        )
    )
