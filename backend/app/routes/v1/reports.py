import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.core.permissions import REPORTS_READ_ALL, REPORTS_READ_OWN
from app.core.rbac import get_current_user, require_global_admin, require_permission_any
from app.models import Report, ReportSection, ReportTemplate, Team, TeamMember, TemplateSectionDef, User
from app.models.exercise_role import ExerciseRole
from app.models.role_definition import RoleDefinition
from app.schemas.common import DataEnvelope, Page
from app.schemas.report import ReportCreate, ReportDetailOut, ReportOut

router = APIRouter(tags=["reports"])


# --- shared helpers (reused by all report endpoints) -----------------------


async def _get_report(db: AsyncSession, exercise_id: uuid.UUID, rid: uuid.UUID) -> Report:
    r = (
        await db.execute(select(Report).where(Report.id == rid, Report.exercise_id == exercise_id))
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="report not found")
    return r


async def _section_pairs(db: AsyncSession, report_id: uuid.UUID) -> list[tuple[ReportSection, TemplateSectionDef]]:
    rows = (
        await db.execute(
            select(ReportSection, TemplateSectionDef)
            .join(TemplateSectionDef, TemplateSectionDef.id == ReportSection.section_def_id)
            .where(ReportSection.report_id == report_id)
            .order_by(ReportSection.position)
        )
    ).all()
    return [(s, d) for s, d in rows]


async def _section_count(db: AsyncSession, report_id: uuid.UUID) -> int:
    return (
        await db.execute(select(func.count()).select_from(ReportSection).where(ReportSection.report_id == report_id))
    ).scalar_one()


async def _caller_team_ids(db: AsyncSession, exercise_id: uuid.UUID, user: User) -> set[uuid.UUID]:
    rows = (
        (
            await db.execute(
                select(TeamMember.team_id)
                .join(Team, Team.id == TeamMember.team_id)
                .where(Team.exercise_id == exercise_id, TeamMember.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


async def _has_permission(db: AsyncSession, exercise_id: uuid.UUID, user: User, perm: str) -> bool:
    """Inline permission probe (mirrors require_permission's resolver) for list-filtering decisions."""
    if user.is_global_admin:
        return True
    keys = (
        (
            await db.execute(
                select(ExerciseRole.role_key).where(
                    ExerciseRole.exercise_id == exercise_id, ExerciseRole.user_id == user.id
                )
            )
        )
        .scalars()
        .all()
    )
    if not keys:
        return False
    granted = (
        (await db.execute(select(RoleDefinition.permissions).where(RoleDefinition.role_key.in_(keys)))).scalars().all()
    )
    return any(perm in perms for perms in granted)


async def _assert_report_access(
    db: AsyncSession, exercise_id: uuid.UUID, report: Report, user: User, *, write: bool
) -> None:
    if user.is_global_admin:
        return
    team_ids = await _caller_team_ids(db, exercise_id, user)
    if report.team_id in team_ids:
        return
    if not write and await _has_permission(db, exercise_id, user, REPORTS_READ_ALL):
        return
    raise HTTPException(status_code=403, detail="insufficient permissions")


def _require_draft(r: Report) -> None:
    if r.status != "draft":
        raise HTTPException(status_code=409, detail="report is not a draft")


# --- instantiate -----------------------------------------------------------


@router.post("/exercises/{exercise_id}/reports", status_code=201)
async def create_report(
    request: Request,
    exercise_id: uuid.UUID,
    body: ReportCreate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ReportDetailOut]:
    team = (await db.execute(select(Team).where(Team.id == uuid.UUID(body.team_id)))).scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    if team.exercise_id != exercise_id:
        raise HTTPException(status_code=422, detail="team does not belong to this exercise")

    template = (
        await db.execute(select(ReportTemplate).where(ReportTemplate.id == uuid.UUID(body.template_id)))
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    if template.status != "published":
        raise HTTPException(status_code=409, detail="template is not published")

    if body.assigned_writer_id is not None:
        member = (
            await db.execute(
                select(TeamMember.id).where(
                    TeamMember.team_id == team.id, TeamMember.user_id == uuid.UUID(body.assigned_writer_id)
                )
            )
        ).first()
        if member is None:
            raise HTTPException(status_code=422, detail="assigned writer is not a member of the team")

    report = Report(
        exercise_id=exercise_id,
        team_id=team.id,
        template_id=template.id,
        template_version_at_creation=template.version,
        name=body.name,
        description=body.description,
        status="draft",
        approval_required=body.approval_required,
        due_at=body.due_at,
        assigned_writer_id=uuid.UUID(body.assigned_writer_id) if body.assigned_writer_id else None,
        created_by=actor.id,
    )
    db.add(report)
    await db.flush()

    defs = (
        (
            await db.execute(
                select(TemplateSectionDef)
                .where(TemplateSectionDef.template_id == template.id)
                .order_by(TemplateSectionDef.position)
            )
        )
        .scalars()
        .all()
    )
    for d in defs:
        db.add(ReportSection(report_id=report.id, section_def_id=d.id, position=d.position, version=1, char_count=0))
    await db.flush()

    await record_audit(
        db,
        user_id=actor.id,
        action="report.create",
        resource_type="report",
        resource_id=report.id,
        details={"template_id": str(template.id), "team_id": str(team.id), "sections": len(defs)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=ReportDetailOut.from_models(report, await _section_pairs(db, report.id)))


# --- list + detail ---------------------------------------------------------


@router.get("/exercises/{exercise_id}/reports")
async def list_reports(
    exercise_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission_any([REPORTS_READ_OWN, REPORTS_READ_ALL])),
    db: AsyncSession = Depends(get_db),
    pp: PageParams = Depends(page_params),
    team_id: uuid.UUID | None = None,
    status: str | None = None,
) -> DataEnvelope[list[ReportOut]]:
    filt = [Report.exercise_id == exercise_id]
    if team_id is not None:
        filt.append(Report.team_id == team_id)
    if status is not None:
        filt.append(Report.status == status)
    # team scoping unless caller can read all (or is admin)
    if not (user.is_global_admin or await _has_permission(db, exercise_id, user, REPORTS_READ_ALL)):
        team_ids = await _caller_team_ids(db, exercise_id, user)
        if not team_ids:
            return DataEnvelope(data=[], meta=Page(page=pp.page, per_page=pp.per_page, total=0))
        filt.append(Report.team_id.in_(team_ids))

    base = select(Report).where(*filt)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(Report.created_at.desc()).offset(pp.offset).limit(pp.limit))).scalars().all()
    counts = {
        rid: cnt
        for rid, cnt in (
            await db.execute(
                select(ReportSection.report_id, func.count())
                .where(ReportSection.report_id.in_([r.id for r in rows]))
                .group_by(ReportSection.report_id)
            )
        ).all()
    }
    return DataEnvelope(
        data=[ReportOut.from_model(r, counts.get(r.id, 0)) for r in rows],
        meta=Page(page=pp.page, per_page=pp.per_page, total=total),
    )


@router.get("/exercises/{exercise_id}/reports/{rid}")
async def get_report(
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission_any([REPORTS_READ_OWN, REPORTS_READ_ALL])),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ReportDetailOut]:
    report = await _get_report(db, exercise_id, rid)
    await _assert_report_access(db, exercise_id, report, user, write=False)
    return DataEnvelope(data=ReportDetailOut.from_models(report, await _section_pairs(db, rid)))
