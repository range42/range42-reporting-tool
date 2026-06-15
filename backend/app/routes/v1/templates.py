import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.core.rbac import require_global_admin
from app.models import ReportTemplate, TemplateSectionDef, User
from app.schemas.common import DataEnvelope, Page
from app.schemas.template import (
    TemplateCreate,
    TemplateDetailOut,
    TemplateOut,
    TemplateUpdate,
)

router = APIRouter(tags=["templates"])


async def _get_template(db: AsyncSession, template_id: uuid.UUID) -> ReportTemplate:
    t = (await db.execute(select(ReportTemplate).where(ReportTemplate.id == template_id))).scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="template not found")
    return t


def _require_draft(t: ReportTemplate) -> None:
    if t.status != "draft":
        raise HTTPException(status_code=409, detail="template is not a draft")


async def _section_count(db: AsyncSession, template_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(TemplateSectionDef).where(TemplateSectionDef.template_id == template_id)
        )
    ).scalar_one()


async def _sections(db: AsyncSession, template_id: uuid.UUID) -> list[TemplateSectionDef]:
    return list(
        (
            await db.execute(
                select(TemplateSectionDef)
                .where(TemplateSectionDef.template_id == template_id)
                .order_by(TemplateSectionDef.position)
            )
        )
        .scalars()
        .all()
    )


@router.post("/templates", status_code=201)
async def create_template(
    request: Request,
    body: TemplateCreate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TemplateOut]:
    t = ReportTemplate(
        lineage_id=uuid.uuid4(),
        version=1,
        name=body.name,
        report_type=body.report_type,
        description=body.description,
        status="draft",
        created_by=actor.id,
    )
    t.metadata_ = body.metadata
    db.add(t)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="template.create",
        resource_type="report_template",
        resource_id=t.id,
        details={"name": t.name},
        ip=client_ip(request),
    )
    return DataEnvelope(data=TemplateOut.from_model(t, 0))


@router.get("/templates")
async def list_templates(
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
    pp: PageParams = Depends(page_params),
    status: str | None = None,
    report_type: str | None = None,
) -> DataEnvelope[list[TemplateOut]]:
    # one row per lineage = the highest-version row remaining after filters.
    filt = []
    if status is not None:
        filt.append(ReportTemplate.status == status)
    else:
        filt.append(ReportTemplate.status != "archived")
    if report_type is not None:
        filt.append(ReportTemplate.report_type == report_type)

    maxv = (
        select(ReportTemplate.lineage_id, func.max(ReportTemplate.version).label("mv"))
        .where(*filt)
        .group_by(ReportTemplate.lineage_id)
        .subquery()
    )
    base = (
        select(ReportTemplate)
        .join(
            maxv,
            (ReportTemplate.lineage_id == maxv.c.lineage_id) & (ReportTemplate.version == maxv.c.mv),
        )
        .where(*filt)
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = list(
        (await db.execute(base.order_by(ReportTemplate.name).offset(pp.offset).limit(pp.limit))).scalars().all()
    )
    counts = {
        tid: cnt
        for tid, cnt in (
            await db.execute(
                select(TemplateSectionDef.template_id, func.count())
                .where(TemplateSectionDef.template_id.in_([r.id for r in rows]))
                .group_by(TemplateSectionDef.template_id)
            )
        ).all()
    }
    return DataEnvelope(
        data=[TemplateOut.from_model(r, counts.get(r.id, 0)) for r in rows],
        meta=Page(page=pp.page, per_page=pp.per_page, total=total),
    )


@router.get("/templates/{template_id}")
async def get_template(
    template_id: uuid.UUID,
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TemplateDetailOut]:
    t = await _get_template(db, template_id)
    return DataEnvelope(data=TemplateDetailOut.from_model(t, await _sections(db, template_id)))


@router.patch("/templates/{template_id}")
async def update_template(
    request: Request,
    template_id: uuid.UUID,
    body: TemplateUpdate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TemplateOut]:
    t = await _get_template(db, template_id)
    _require_draft(t)
    data = body.model_dump(exclude_unset=True)
    changed = sorted(data.keys())
    if "metadata" in data:
        t.metadata_ = data.pop("metadata")
    for k, v in data.items():
        setattr(t, k, v)
    await db.flush()
    await db.refresh(t)
    await record_audit(
        db,
        user_id=actor.id,
        action="template.update",
        resource_type="report_template",
        resource_id=t.id,
        details={"changed": changed},
        ip=client_ip(request),
    )
    return DataEnvelope(data=TemplateOut.from_model(t, await _section_count(db, template_id)))


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    request: Request,
    template_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    t = await _get_template(db, template_id)
    _require_draft(t)
    await db.delete(t)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="template.delete",
        resource_type="report_template",
        resource_id=template_id,
        details=None,
        ip=client_ip(request),
    )
