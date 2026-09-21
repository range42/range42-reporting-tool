"""Campaigns — grouping of reports across teams/time for an exercise.

Writes are GA-only, like every authoring surface. Reads reuse the report visibility rules —
own team, ``reports:read:assigned`` (reports the caller evaluates), or ``reports:read:all`` —
resolved server-side on every query (default-deny). The timeline/compare endpoints feed the
evaluator two-pane / N-pane views.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.core.permissions import EVALUATIONS_WRITE, REPORTS_READ_ALL, REPORTS_READ_ASSIGNED, REPORTS_READ_OWN
from app.core.rbac import get_current_user, require_global_admin, require_permission_any
from app.models import Campaign, CampaignEvaluator, CampaignReport, Evaluation, Exercise, Report, Team, User
from app.routes.v1.reports import _auto_assign_evaluators, _caller_team_ids, _has_permission, _section_pairs
from app.schemas.campaign import (
    CampaignCreate,
    CampaignEvaluatorCreate,
    CampaignEvaluatorOut,
    CampaignOut,
    CampaignReportAdd,
    CampaignUpdate,
    TimelineEntryOut,
)
from app.schemas.common import DataEnvelope, Page
from app.schemas.report import ReportDetailOut

router = APIRouter(tags=["campaigns"])

COMPARE_MAX_REPORTS = 8


async def _get_exercise(db: AsyncSession, exercise_id: uuid.UUID) -> Exercise:
    e = (await db.execute(select(Exercise).where(Exercise.id == exercise_id))).scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    return e


async def _get_campaign(db: AsyncSession, exercise_id: uuid.UUID, cid: uuid.UUID) -> Campaign:
    c = (
        await db.execute(select(Campaign).where(Campaign.id == cid, Campaign.exercise_id == exercise_id))
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return c


async def _report_count(db: AsyncSession, campaign_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(CampaignReport).where(CampaignReport.campaign_id == campaign_id)
        )
    ).scalar_one()


async def _visible_report_ids(db: AsyncSession, exercise_id: uuid.UUID, user: User) -> set[uuid.UUID] | None:
    """The report ids the caller may read, or None for unrestricted (admin / read:all).

    Union of: reports belonging to the caller's own team(s), and — for an evaluator holding
    ``reports:read:assigned`` — reports they are actively assigned to evaluate (soft-unassigned
    rows don't count, same predicate as the finalize gate/rollup use).
    """
    if user.is_global_admin or await _has_permission(db, exercise_id, user, REPORTS_READ_ALL):
        return None
    visible: set[uuid.UUID] = set()
    team_ids = await _caller_team_ids(db, exercise_id, user)
    if team_ids:
        rows = (
            (await db.execute(select(Report.id).where(Report.exercise_id == exercise_id, Report.team_id.in_(team_ids))))
            .scalars()
            .all()
        )
        visible.update(rows)
    if await _has_permission(db, exercise_id, user, REPORTS_READ_ASSIGNED):
        rows = (
            (
                await db.execute(
                    select(Evaluation.report_id)
                    .join(Report, Report.id == Evaluation.report_id)
                    .where(
                        Report.exercise_id == exercise_id,
                        Evaluation.evaluator_id == user.id,
                        Evaluation.unassigned_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        visible.update(rows)
    return visible


# --- CRUD --------------------------------------------------------------------


@router.post("/exercises/{exercise_id}/campaigns", status_code=201)
async def create_campaign(
    request: Request,
    exercise_id: uuid.UUID,
    body: CampaignCreate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[CampaignOut]:
    await _get_exercise(db, exercise_id)
    dup = (
        await db.execute(select(Campaign.id).where(Campaign.exercise_id == exercise_id, Campaign.name == body.name))
    ).first()
    if dup is not None:
        raise HTTPException(status_code=409, detail="a campaign with this name already exists in the exercise")
    c = Campaign(exercise_id=exercise_id, name=body.name, description=body.description, created_by=actor.id)
    c.metadata_ = body.metadata
    db.add(c)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="campaign.create",
        resource_type="campaign",
        resource_id=c.id,
        details={"name": c.name},
        ip=client_ip(request),
    )
    return DataEnvelope(data=CampaignOut.from_model(c, 0))


@router.get("/exercises/{exercise_id}/campaigns")
async def list_campaigns(
    exercise_id: uuid.UUID,
    _: None = Depends(require_permission_any([REPORTS_READ_OWN, REPORTS_READ_ASSIGNED, REPORTS_READ_ALL])),
    db: AsyncSession = Depends(get_db),
    pp: PageParams = Depends(page_params),
) -> DataEnvelope[list[CampaignOut]]:
    base = select(Campaign).where(Campaign.exercise_id == exercise_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = list((await db.execute(base.order_by(Campaign.name).offset(pp.offset).limit(pp.limit))).scalars().all())
    counts = {
        cid: cnt
        for cid, cnt in (
            await db.execute(
                select(CampaignReport.campaign_id, func.count())
                .where(CampaignReport.campaign_id.in_([r.id for r in rows]))
                .group_by(CampaignReport.campaign_id)
            )
        ).all()
    }
    return DataEnvelope(
        data=[CampaignOut.from_model(r, counts.get(r.id, 0)) for r in rows],
        meta=Page(page=pp.page, per_page=pp.per_page, total=total),
    )


@router.get("/exercises/{exercise_id}/campaigns/{cid}")
async def get_campaign(
    exercise_id: uuid.UUID,
    cid: uuid.UUID,
    _: None = Depends(require_permission_any([REPORTS_READ_OWN, REPORTS_READ_ASSIGNED, REPORTS_READ_ALL])),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[CampaignOut]:
    c = await _get_campaign(db, exercise_id, cid)
    return DataEnvelope(data=CampaignOut.from_model(c, await _report_count(db, cid)))


@router.patch("/exercises/{exercise_id}/campaigns/{cid}")
async def update_campaign(
    request: Request,
    exercise_id: uuid.UUID,
    cid: uuid.UUID,
    body: CampaignUpdate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[CampaignOut]:
    c = await _get_campaign(db, exercise_id, cid)
    data = body.model_dump(exclude_unset=True)
    changed = sorted(data.keys())
    if "name" in data:
        dup = (
            await db.execute(
                select(Campaign.id).where(
                    Campaign.exercise_id == exercise_id, Campaign.name == data["name"], Campaign.id != cid
                )
            )
        ).first()
        if dup is not None:
            raise HTTPException(status_code=409, detail="a campaign with this name already exists in the exercise")
    if "metadata" in data:
        c.metadata_ = data.pop("metadata")
    for k, v in data.items():
        setattr(c, k, v)
    await db.flush()
    await db.refresh(c)
    await record_audit(
        db,
        user_id=actor.id,
        action="campaign.update",
        resource_type="campaign",
        resource_id=c.id,
        details={"changed": changed},
        ip=client_ip(request),
    )
    return DataEnvelope(data=CampaignOut.from_model(c, await _report_count(db, cid)))


@router.delete("/exercises/{exercise_id}/campaigns/{cid}", status_code=204)
async def delete_campaign(
    request: Request,
    exercise_id: uuid.UUID,
    cid: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    c = await _get_campaign(db, exercise_id, cid)
    await db.delete(c)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="campaign.delete",
        resource_type="campaign",
        resource_id=cid,
        details=None,
        ip=client_ip(request),
    )


# --- membership -----------------------------------------------------------------


@router.post("/exercises/{exercise_id}/campaigns/{cid}/reports", status_code=201)
async def add_campaign_report(
    request: Request,
    exercise_id: uuid.UUID,
    cid: uuid.UUID,
    body: CampaignReportAdd,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[CampaignOut]:
    c = await _get_campaign(db, exercise_id, cid)
    rid = uuid.UUID(body.report_id)
    report = (await db.execute(select(Report).where(Report.id == rid))).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    if report.exercise_id != exercise_id:
        raise HTTPException(status_code=422, detail="report does not belong to this exercise")
    dup = (
        await db.execute(
            select(CampaignReport.id).where(CampaignReport.campaign_id == cid, CampaignReport.report_id == rid)
        )
    ).first()
    if dup is not None:
        raise HTTPException(status_code=409, detail="report is already in this campaign")
    db.add(CampaignReport(campaign_id=cid, report_id=rid))
    await db.flush()
    # Campaign membership can arrive after submission (manual add, here) as well as before it
    # (the batch campaign-definition flow) — the submission-time hook alone would miss this case.
    if report.status in ("submitted", "under_evaluation", "evaluated"):
        await _auto_assign_evaluators(db, report, actor_id=actor.id)
    await record_audit(
        db,
        user_id=actor.id,
        action="campaign.report.add",
        resource_type="campaign",
        resource_id=cid,
        details={"report_id": str(rid)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=CampaignOut.from_model(c, await _report_count(db, cid)))


@router.delete("/exercises/{exercise_id}/campaigns/{cid}/reports/{rid}", status_code=204)
async def remove_campaign_report(
    request: Request,
    exercise_id: uuid.UUID,
    cid: uuid.UUID,
    rid: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_campaign(db, exercise_id, cid)
    link = (
        await db.execute(
            select(CampaignReport).where(CampaignReport.campaign_id == cid, CampaignReport.report_id == rid)
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="report is not in this campaign")
    await db.delete(link)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="campaign.report.remove",
        resource_type="campaign",
        resource_id=cid,
        details={"report_id": str(rid)},
        ip=client_ip(request),
    )


# --- campaign ↔ evaluator assignment ----------------------------------------------
# Independent of team; resolved against team_evaluator by intersection at report-submission
# time (reports.py::_auto_assign_evaluators).


@router.get("/exercises/{exercise_id}/campaigns/{cid}/evaluators")
async def list_campaign_evaluators(
    exercise_id: uuid.UUID,
    cid: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[list[CampaignEvaluatorOut]]:
    await _get_campaign(db, exercise_id, cid)
    rows = (
        await db.execute(
            select(CampaignEvaluator, User)
            .join(User, User.id == CampaignEvaluator.evaluator_id)
            .where(CampaignEvaluator.campaign_id == cid)
        )
    ).all()
    return DataEnvelope(data=[CampaignEvaluatorOut.from_row(ce, u) for ce, u in rows])


@router.post("/exercises/{exercise_id}/campaigns/{cid}/evaluators", status_code=201)
async def add_campaign_evaluator(
    request: Request,
    exercise_id: uuid.UUID,
    cid: uuid.UUID,
    body: CampaignEvaluatorCreate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[CampaignEvaluatorOut]:
    await _get_campaign(db, exercise_id, cid)
    try:
        evaluator_uuid = uuid.UUID(body.evaluator_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid evaluator_id") from None
    user = (await db.execute(select(User).where(User.id == evaluator_uuid))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if not await _has_permission(db, exercise_id, user, EVALUATIONS_WRITE):
        raise HTTPException(status_code=422, detail={"error": "user_is_not_an_evaluator"})
    ce = CampaignEvaluator(campaign_id=cid, evaluator_id=user.id)
    db.add(ce)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="already assigned") from None
    await record_audit(
        db,
        user_id=actor.id,
        action="campaign_evaluator.add",
        resource_type="campaign_evaluator",
        resource_id=ce.id,
        details={"campaign_id": str(cid), "evaluator_id": str(user.id)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=CampaignEvaluatorOut.from_row(ce, user))


@router.delete("/exercises/{exercise_id}/campaigns/{cid}/evaluators/{evaluator_id}", status_code=204)
async def remove_campaign_evaluator(
    request: Request,
    exercise_id: uuid.UUID,
    cid: uuid.UUID,
    evaluator_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_campaign(db, exercise_id, cid)
    ce = (
        await db.execute(
            select(CampaignEvaluator).where(
                CampaignEvaluator.campaign_id == cid, CampaignEvaluator.evaluator_id == evaluator_id
            )
        )
    ).scalar_one_or_none()
    if ce is None:
        raise HTTPException(status_code=404, detail="assignment not found")
    await db.delete(ce)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="campaign_evaluator.remove",
        resource_type="campaign_evaluator",
        resource_id=ce.id,
        details={"campaign_id": str(cid), "evaluator_id": str(evaluator_id)},
        ip=client_ip(request),
    )


# --- timeline + compare (evaluator feeds) -----------------------------------------


@router.get("/exercises/{exercise_id}/campaigns/{cid}/timeline")
async def campaign_timeline(
    exercise_id: uuid.UUID,
    cid: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission_any([REPORTS_READ_OWN, REPORTS_READ_ASSIGNED, REPORTS_READ_ALL])),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[list[TimelineEntryOut]]:
    await _get_campaign(db, exercise_id, cid)
    filt = [CampaignReport.campaign_id == cid]
    report_ids = await _visible_report_ids(db, exercise_id, user)
    if report_ids is not None:
        if not report_ids:
            return DataEnvelope(data=[])
        filt.append(Report.id.in_(report_ids))
    rows = (
        await db.execute(
            select(Report, Team.name)
            .join(CampaignReport, CampaignReport.report_id == Report.id)
            .join(Team, Team.id == Report.team_id)
            .where(*filt)
            .order_by(Report.submitted_at.asc().nulls_last(), Report.created_at.asc())
        )
    ).all()
    return DataEnvelope(data=[TimelineEntryOut.from_models(r, team_name) for r, team_name in rows])


@router.get("/exercises/{exercise_id}/campaigns/{cid}/compare")
async def campaign_compare(
    exercise_id: uuid.UUID,
    cid: uuid.UUID,
    report_ids: Annotated[list[uuid.UUID], Query(min_length=1, max_length=COMPARE_MAX_REPORTS)],
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission_any([REPORTS_READ_OWN, REPORTS_READ_ASSIGNED, REPORTS_READ_ALL])),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[list[ReportDetailOut]]:
    await _get_campaign(db, exercise_id, cid)
    member_ids = set(
        (await db.execute(select(CampaignReport.report_id).where(CampaignReport.campaign_id == cid))).scalars().all()
    )
    missing = [str(rid) for rid in report_ids if rid not in member_ids]
    if missing:
        raise HTTPException(status_code=404, detail={"error": "report_not_in_campaign", "report_ids": missing})

    visible_ids = await _visible_report_ids(db, exercise_id, user)
    reports = {r.id: r for r in (await db.execute(select(Report).where(Report.id.in_(report_ids)))).scalars().all()}
    if visible_ids is not None and any(rid not in visible_ids for rid in report_ids):
        raise HTTPException(status_code=403, detail="insufficient permissions")
    data = [ReportDetailOut.from_models(reports[rid], await _section_pairs(db, rid)) for rid in report_ids]
    return DataEnvelope(data=data)
