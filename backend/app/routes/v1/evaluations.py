"""Evaluation routes (WP5 W5-1).

D1 — EVALUATOR ISOLATION: every read and write path scopes on ``evaluator_id``. A Global
Admin bypasses; no other caller may reach an evaluation that is not theirs, at any
``evaluation.status`` or ``report.status``. There is deliberately no peer visibility.

Path shape (L3): nested under the report, not the flat ``/evaluations/{id}`` of §6.8, so the
exercise-scoped permission dependency has an ``exercise_id`` to resolve against. Matches the
attachments deviation already shipped in WP3.
"""

import uuid
from decimal import Decimal
from typing import Any

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
    EvaluationUpdate,
    GradableSectionOut,
    ManualGradeRequest,
    ReportGradeOut,
    SectionGradeOut,
    SectionGradeUpsert,
)
from app.services.scoring import grade_validation, rollup
from app.services.workflow import state_machine

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


async def _gradable_section(
    db: AsyncSession, report_id: uuid.UUID, section_id: uuid.UUID
) -> tuple[ReportSection, TemplateSectionDef]:
    """One section *of this report* with its template definition; 404 on a foreign section."""
    row = (
        await db.execute(
            select(ReportSection, TemplateSectionDef)
            .join(TemplateSectionDef, TemplateSectionDef.id == ReportSection.section_def_id)
            .where(ReportSection.id == section_id, ReportSection.report_id == report_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "section_not_found"})
    return row[0], row[1]


async def _upsert_grade(
    db: AsyncSession,
    ev: Evaluation,
    section: ReportSection,
    grade: Decimal | None,
    pass_fail: bool | None,
    rubric: list[dict[str, Any]] | None,
    feedback: str | None,
    actor_id: uuid.UUID,
) -> SectionGrade:
    """Create or update the caller's grade for one section.

    Keyed on UNIQUE(evaluation_id, report_section_id), which is per-evaluator: two evaluators
    grading the same section produce two rows, never a conflict.
    """
    sg = (
        await db.execute(
            select(SectionGrade).where(
                SectionGrade.evaluation_id == ev.id, SectionGrade.report_section_id == section.id
            )
        )
    ).scalar_one_or_none()
    if sg is None:
        sg = SectionGrade(evaluation_id=ev.id, report_section_id=section.id, graded_by=actor_id)
        db.add(sg)
    sg.grade = grade
    sg.pass_fail_result = pass_fail
    sg.rubric_scores = rubric
    sg.feedback = feedback
    sg.graded_by = actor_id
    await db.flush()
    return sg


async def _begin_evaluation(
    db: AsyncSession,
    ev: Evaluation,
    report: Report,
    *,
    actor_id: uuid.UUID,
    ip: str | None,
) -> None:
    """L5 — §7.2's 'assigned AND begins evaluation'. Idempotent: no-op when already begun,
    so no duplicate transition audit row is ever emitted.

    Assignment does not begin evaluation; the first evaluator write does. Task 8's grade
    upsert calls this same function, which is why it must stay idempotent.
    """
    if ev.status == "assigned":
        ev.status = "in_progress"
        await db.flush()
    if report.status == "submitted":
        await state_machine.transition(
            db,
            report,
            target_status="under_evaluation",
            actor_id=actor_id,
            action="report.under_evaluation",
            details={"evaluation_id": str(ev.id)},
            ip=ip,
        )


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


@router.patch(_BASE + "/{evid}")
async def update_evaluation(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    evid: uuid.UUID,
    body: EvaluationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(EVALUATIONS_WRITE)),
) -> DataEnvelope[EvaluationOut]:
    """Update the evaluation's overall feedback; the first write begins evaluation (L5).

    Authorize before mutating: the D1 gate runs ahead of every write and audit call, so a
    rejected caller leaves no trace behind (Task 11 pins that).

    A7 / D3 sole-writer guards: this handler never touches ``report.overall_grade``,
    ``evaluation.overall_grade`` or ``report.grade_version`` — the W5-2 rollup owns those.
    """
    report: Report = await _get_report(db, exercise_id, rid)
    ev = await _get_evaluation(db, report.id, evid)
    _assert_evaluation_access(ev, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(ev, field, value)
    await _begin_evaluation(db, ev, report, actor_id=user.id, ip=client_ip(request))
    await record_audit(
        db,
        user_id=user.id,
        action="evaluation.feedback_updated",
        resource_type="evaluation",
        resource_id=ev.id,
        details={"report_id": str(report.id)},
        ip=client_ip(request),
    )
    # server-side onupdate=now() expires updated_at on flush; reload before serializing.
    await db.refresh(ev)
    return DataEnvelope(data=await _evaluation_out(db, ev))


@router.put(_BASE + "/{evid}/grades/{section_id}")
async def upsert_section_grade(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    evid: uuid.UUID,
    section_id: uuid.UUID,
    body: SectionGradeUpsert,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(EVALUATIONS_WRITE)),
) -> DataEnvelope[SectionGradeOut]:
    """Create or replace the caller's grade for one section (L8).

    Every rejection — 403, 404, 409, 422 — is raised before the first mutation and before
    ``record_audit``, so a refused write leaves no row and no audit trail (Task 11 asserts it).
    """
    report: Report = await _get_report(db, exercise_id, rid)
    ev = await _get_evaluation(db, report.id, evid)
    _assert_evaluation_access(ev, user)
    if ev.status == "completed":
        raise HTTPException(status_code=409, detail={"error": "evaluation_completed"})
    section, defn = await _gradable_section(db, report.id, section_id)
    try:
        grade, pass_fail, rubric = grade_validation.validate_grade_payload(defn, body)
    except grade_validation.GradeValidationError as exc:
        raise HTTPException(status_code=422, detail={"error": exc.code, "mode": defn.grade_mode}) from None
    await _begin_evaluation(db, ev, report, actor_id=user.id, ip=client_ip(request))
    sg = await _upsert_grade(db, ev, section, grade, pass_fail, rubric, body.feedback, user.id)
    await record_audit(
        db,
        user_id=user.id,
        action="section_grade.saved",
        resource_type="section_grade",
        resource_id=sg.id,
        details={"evaluation_id": str(ev.id), "report_section_id": str(section.id), "grade_mode": defn.grade_mode},
        ip=client_ip(request),
    )
    # A7: rollup is the sole writer of report.overall_grade / evaluation.overall_grade /
    # grade_version, and runs inside THIS transaction so a grade write and its rollup are atomic.
    await rollup.recompute_report_grade(
        db, report, actor_id=user.id, trigger="section_grade.saved", ip=client_ip(request)
    )
    await db.refresh(sg)
    return DataEnvelope(data=SectionGradeOut.from_model(sg))


@router.get(_BASE + "/{evid}/grades")
async def list_section_grades(
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    evid: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(EVALUATIONS_WRITE)),
) -> DataEnvelope[list[SectionGradeOut]]:
    """The evaluation's own grades, ordered by section position.

    No separate filter: "own grades" falls out of the D1 gate on "own evaluation". A Global
    Admin reads any evaluation's grades, one evaluation at a time.
    """
    report: Report = await _get_report(db, exercise_id, rid)
    ev = await _get_evaluation(db, report.id, evid)
    _assert_evaluation_access(ev, user)
    rows = (
        (
            await db.execute(
                select(SectionGrade)
                .join(ReportSection, ReportSection.id == SectionGrade.report_section_id)
                .where(SectionGrade.evaluation_id == ev.id)
                .order_by(ReportSection.position)
            )
        )
        .scalars()
        .all()
    )
    return DataEnvelope(data=[SectionGradeOut.from_model(g) for g in rows])


@router.delete(_BASE + "/{evid}/grades/{section_id}", status_code=204)
async def delete_section_grade(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    evid: uuid.UUID,
    section_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(EVALUATIONS_WRITE)),
) -> None:
    """Remove the caller's grade for one section and recompute (edge case 3).

    NOT IN §6.8 — see ambiguity B6. It exists because a grade has to be retractable and PUT
    cannot express it: L8's numeric branch REQUIRES ``grade``, so there is no payload meaning
    "un-grade this". Overloading PUT with null semantics would collide with the mode table, so
    the retraction gets its own verb.

    Deleting the last grade returns the report to an ungraded state — overall_grade goes back
    to NULL, not 0, and grade_version still advances because the published number changed.
    """
    report: Report = await _get_report(db, exercise_id, rid)
    ev = await _get_evaluation(db, report.id, evid)
    _assert_evaluation_access(ev, user)
    if ev.status == "completed":
        raise HTTPException(status_code=409, detail={"error": "evaluation_completed"})
    section, _defn = await _gradable_section(db, report.id, section_id)
    sg = (
        await db.execute(
            select(SectionGrade).where(
                SectionGrade.evaluation_id == ev.id, SectionGrade.report_section_id == section.id
            )
        )
    ).scalar_one_or_none()
    if sg is None:
        raise HTTPException(status_code=404, detail={"error": "grade_not_found"})
    await db.delete(sg)
    await db.flush()
    await record_audit(
        db,
        user_id=user.id,
        action="section_grade.deleted",
        resource_type="section_grade",
        resource_id=sg.id,
        details={"evaluation_id": str(ev.id), "report_section_id": str(section.id)},
        ip=client_ip(request),
    )
    await rollup.recompute_report_grade(
        db, report, actor_id=user.id, trigger="section_grade.deleted", ip=client_ip(request)
    )


# --- M9: manual overall-grade override ------------------------------------------------
#
# ROUTER HOME (locked): the path is report-scoped, so ``reports.py`` would be the obvious host,
# but the handler has to reach ``rollup`` and every grade-writing route belongs in ONE file so
# the sole-writer surface (M2) can be audited by reading a single module. Hence it lives here.


@router.put("/exercises/{exercise_id}/reports/{rid}/overall-grade")
async def set_overall_grade(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    body: ManualGradeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(EVALUATIONS_WRITE)),
) -> DataEnvelope[ReportGradeOut]:
    """Set ``report.overall_grade`` by hand, or clear the override (M9, §4.2).

    Authorization: Global Admin, or an evaluator ASSIGNED TO THIS REPORT. Holding
    ``evaluations:write`` in the exercise is not enough — D1 (E1) applies to the report-level
    number exactly as it does to a peer's evaluation, so an unassigned evaluator 403s. Every
    rejection precedes the first write, so a refused call leaves no row and no audit trail.

    ``overall_grade=None`` clears the flag and recomputes at once, so the report never sits on a
    stale hand-set number. Both branches go through ``rollup.set_manual_grade`` (M2) and both
    bump ``grade_version`` (D3) because either way a new number is published.
    """
    report: Report = await _get_report(db, exercise_id, rid)
    if not user.is_global_admin and await _existing_evaluation(db, report.id, user.id) is None:
        raise HTTPException(status_code=403, detail={"error": "not_assigned_to_report"})
    await rollup.set_manual_grade(
        db, report, body.overall_grade, actor_id=user.id, reason=body.reason, ip=client_ip(request)
    )
    return DataEnvelope(
        data=ReportGradeOut(
            report_id=str(report.id),
            overall_grade=report.overall_grade,
            overall_grade_is_manual=report.overall_grade_is_manual,
            grade_version=report.grade_version,
        )
    )
