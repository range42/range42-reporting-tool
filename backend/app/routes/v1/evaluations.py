"""Evaluation routes (WP5 W5-1).

D1 — EVALUATOR ISOLATION: every read and write path scopes on ``evaluator_id``. A Global
Admin bypasses; no other caller may reach an evaluation that is not theirs, at any
``evaluation.status`` or ``report.status``. There is deliberately no peer visibility.

Path shape (L3): nested under the report, not the flat ``/evaluations/{id}`` of §6.8, so the
exercise-scoped permission dependency has an ``exercise_id`` to resolve against. Matches the
attachments deviation already shipped in WP3.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.db import get_db
from app.core.permissions import EVALUATIONS_WRITE
from app.core.rbac import require_global_admin
from app.models import Evaluation, Report, ReportSection, SectionGrade, TemplateSectionDef, User
from app.routes.v1.reports import _get_report, _has_permission
from app.schemas.common import DataEnvelope
from app.schemas.evaluation import EvaluationCreate, EvaluationOut

router = APIRouter(tags=["evaluations"])

_BASE = "/exercises/{exercise_id}/reports/{rid}/evaluations"

# L4 — an evaluator is assignable while the report is awaiting or under evaluation. A second
# evaluator may join a report already being graded (multi-evaluator, W5-3).
_ASSIGNABLE_STATUSES = ("submitted", "under_evaluation")


async def _get_user(db: AsyncSession, raw_id: str) -> User:
    """Resolve ``raw_id`` to a user; 404 on a malformed uuid as well as on a missing row.

    ``EvaluationCreate.evaluator_id`` is typed ``str`` precisely so this handler owns the
    response: a malformed id is a missing resource, not a schema violation.
    """
    try:
        uid = uuid.UUID(raw_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="user not found") from None
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


async def _existing_evaluation(db: AsyncSession, report_id: uuid.UUID, evaluator_id: uuid.UUID) -> Evaluation | None:
    return (
        await db.execute(
            select(Evaluation).where(Evaluation.report_id == report_id, Evaluation.evaluator_id == evaluator_id)
        )
    ).scalar_one_or_none()


async def _grade_counts(db: AsyncSession, report_id: uuid.UUID, evaluation_id: uuid.UUID) -> tuple[int, int]:
    """``(graded, gradable)`` for one evaluation, in a single query.

    gradable = sections whose source ``template_section_def.grade_mode`` is not ``not_graded``.
    graded   = those that carry a ``section_grade`` row for *this* evaluation.
    """
    graded, gradable = (
        await db.execute(
            select(func.count(SectionGrade.id), func.count(ReportSection.id))
            .select_from(ReportSection)
            .join(TemplateSectionDef, TemplateSectionDef.id == ReportSection.section_def_id)
            .outerjoin(
                SectionGrade,
                (SectionGrade.report_section_id == ReportSection.id) & (SectionGrade.evaluation_id == evaluation_id),
            )
            .where(ReportSection.report_id == report_id, TemplateSectionDef.grade_mode != "not_graded")
        )
    ).one()
    return int(graded), int(gradable)


async def _evaluation_out(db: AsyncSession, ev: Evaluation) -> EvaluationOut:
    """Serialize one evaluation with its grading progress. Reused by Tasks 6-8."""
    graded, gradable = await _grade_counts(db, ev.report_id, ev.id)
    return EvaluationOut.from_model(ev, graded=graded, gradable=gradable)


@router.post(_BASE, status_code=201)
async def assign_evaluator(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    body: EvaluationCreate,
    user: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[EvaluationOut]:
    """Assign an evaluator to a submitted report (Global Admin only).

    L5: assignment does NOT begin evaluation — ``report.status`` is untouched here. The
    ``submitted -> under_evaluation`` transition fires on the evaluator's first write (Task 7).
    """
    report: Report = await _get_report(db, exercise_id, rid)
    if report.status not in _ASSIGNABLE_STATUSES:
        raise HTTPException(status_code=409, detail={"error": "report_not_submitted"})
    target = await _get_user(db, body.evaluator_id)
    if not await _has_permission(db, exercise_id, target, EVALUATIONS_WRITE):
        raise HTTPException(status_code=422, detail={"error": "user_is_not_an_evaluator"})
    if await _existing_evaluation(db, report.id, target.id) is not None:
        raise HTTPException(status_code=409, detail={"error": "evaluator_already_assigned"})
    ev = Evaluation(
        report_id=report.id,
        evaluator_id=target.id,
        assigned_by=user.id,
        aggregated_weight=body.aggregated_weight,
    )
    db.add(ev)
    try:
        await db.flush()
    except IntegrityError:
        # Race backstop only — the pre-check above is the normal path. Roll back first so the
        # audit write below can never run on a poisoned session.
        await db.rollback()
        raise HTTPException(status_code=409, detail={"error": "evaluator_already_assigned"}) from None
    await record_audit(
        db,
        user_id=user.id,
        action="evaluation.assigned",
        resource_type="evaluation",
        resource_id=ev.id,
        details={"report_id": str(report.id), "evaluator_id": str(target.id)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=await _evaluation_out(db, ev))
