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
from app.core.rbac import get_current_user, require_global_admin, require_permission
from app.models import Evaluation, Report, ReportSection, SectionGrade, TemplateSectionDef, User
from app.routes.v1.reports import _get_report, _has_permission
from app.schemas.common import DataEnvelope
from app.schemas.evaluation import (
    EvaluationCreate,
    EvaluationDetailOut,
    EvaluationOut,
    GradableSectionOut,
)

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


async def _get_evaluation(db: AsyncSession, report_id: uuid.UUID, evid: uuid.UUID) -> Evaluation:
    """Fetch one evaluation *of this report*. Wrong parent report is a 404, not a 403 — the
    caller must not learn that the id exists elsewhere."""
    ev = (
        await db.execute(select(Evaluation).where(Evaluation.id == evid, Evaluation.report_id == report_id))
    ).scalar_one_or_none()
    if ev is None:
        raise HTTPException(status_code=404, detail={"error": "evaluation_not_found"})
    return ev


def _assert_evaluation_access(ev: Evaluation, user: User) -> None:
    """D1 (final): evaluators are isolated. Global Admin bypasses; every other caller must
    BE the assigned evaluator. No peer visibility at any evaluation.status or report.status.
    Relaxing this is a D1 violation — reject in review."""
    if user.is_global_admin:
        return
    if ev.evaluator_id != user.id:
        raise HTTPException(status_code=403, detail={"error": "not_your_evaluation"})


async def _gradable_sections(
    db: AsyncSession, report_id: uuid.UUID, evaluation_id: uuid.UUID
) -> list[GradableSectionOut]:
    """Every section of the report with its template definition and *this* evaluation's grade.

    One query, LEFT OUTER on ``section_grade`` keyed on ``evaluation_id`` so an evaluator can
    never see a peer's grade. Ordered by ``report_section.position``. Task 8 reuses this — a
    per-section query here would multiply into an N+1 there.
    """
    rows = (
        await db.execute(
            select(ReportSection, TemplateSectionDef, SectionGrade)
            .join(TemplateSectionDef, TemplateSectionDef.id == ReportSection.section_def_id)
            .outerjoin(
                SectionGrade,
                (SectionGrade.report_section_id == ReportSection.id) & (SectionGrade.evaluation_id == evaluation_id),
            )
            .where(ReportSection.report_id == report_id)
            .order_by(ReportSection.position)
        )
    ).all()
    return [GradableSectionOut.from_models(s, d, g) for s, d, g in rows]


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


@router.get(_BASE)
async def list_evaluations(
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(EVALUATIONS_WRITE)),
) -> DataEnvelope[list[EvaluationOut]]:
    """List the report's evaluations, D1-scoped.

    Scoping here is a *filter*, not a gate: an evaluator holding EVALUATIONS_WRITE in the
    exercise but assigned to no evaluation on this report gets ``200 []``, not a 403. The
    detail route below is the gate. The asymmetry is deliberate — see #95's error contract.
    """
    report: Report = await _get_report(db, exercise_id, rid)
    q = select(Evaluation).where(Evaluation.report_id == report.id)
    if not user.is_global_admin:
        q = q.where(Evaluation.evaluator_id == user.id)
    rows = (await db.execute(q.order_by(Evaluation.created_at))).scalars().all()
    return DataEnvelope(data=[await _evaluation_out(db, ev) for ev in rows])


@router.get(_BASE + "/{evid}")
async def get_evaluation(
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    evid: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(EVALUATIONS_WRITE)),
) -> DataEnvelope[EvaluationDetailOut]:
    """One evaluation with the sections to grade (D1-gated).

    L12: ``GradableSectionOut`` is the only place the evaluator-only template fields
    (grade_mode/min/max, weight, rubric and evaluation criteria) are exposed. They must never
    migrate onto ``ReportSectionOut``.
    """
    report: Report = await _get_report(db, exercise_id, rid)
    ev = await _get_evaluation(db, report.id, evid)
    _assert_evaluation_access(ev, user)
    base = await _evaluation_out(db, ev)
    return DataEnvelope(
        data=EvaluationDetailOut(
            **base.model_dump(),
            report_name=report.name,
            report_status=report.status,
            grade_version=report.grade_version,
            sections=await _gradable_sections(db, report.id, ev.id),
        )
    )
