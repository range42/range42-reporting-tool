import copy
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.core.rbac import require_global_admin
from app.models import ReportSection, ReportTemplate, TemplateSectionDef, User
from app.schemas.common import DataEnvelope, Page
from app.schemas.template import (
    ReorderBody,
    SectionCreate,
    SectionOut,
    SectionUpdate,
    TemplateBundle,
    TemplateCreate,
    TemplateDetailOut,
    TemplateOut,
    TemplateUpdate,
    TemplateVersionOut,
    section_invariant_error,
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


def _renormalize_choice_positions(choice_config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Rewrite values[].position to dense 0..n-1 by current position then array order."""
    if not choice_config or not choice_config.get("values"):
        return choice_config
    values = sorted(
        enumerate(choice_config["values"]),
        key=lambda iv: (iv[1].get("position", iv[0]), iv[0]),
    )
    renormed = [{**v, "position": i} for i, (_, v) in enumerate(values)]
    return {**choice_config, "values": renormed}


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


# ---------------------------------------------------------------------------
# Versioning: publish / clone / archive / versions
# ---------------------------------------------------------------------------


@router.post("/templates/{template_id}/publish")
async def publish_template(
    request: Request,
    template_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TemplateOut]:
    t = await _get_template(db, template_id)
    _require_draft(t)
    count = await _section_count(db, template_id)
    if count == 0:
        raise HTTPException(status_code=409, detail="cannot publish a template with no sections")
    t.status = "published"
    await db.flush()
    await db.refresh(t)
    await record_audit(
        db,
        user_id=actor.id,
        action="template.publish",
        resource_type="report_template",
        resource_id=t.id,
        details={"version": t.version},
        ip=client_ip(request),
    )
    return DataEnvelope(data=TemplateOut.from_model(t, count))


@router.post("/templates/{template_id}/clone", status_code=201)
async def clone_template(
    request: Request,
    template_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TemplateDetailOut]:
    src = await _get_template(db, template_id)
    max_v = (
        await db.execute(select(func.max(ReportTemplate.version)).where(ReportTemplate.lineage_id == src.lineage_id))
    ).scalar_one()
    clone = ReportTemplate(
        lineage_id=src.lineage_id,
        version=(max_v or 0) + 1,
        name=src.name,
        report_type=src.report_type,
        description=src.description,
        status="draft",
        created_by=actor.id,
    )
    clone.metadata_ = src.metadata_
    db.add(clone)
    await db.flush()
    for s in await _sections(db, template_id):
        db.add(
            TemplateSectionDef(
                template_id=clone.id,
                position=s.position,
                name=s.name,
                description=s.description,
                field_type=s.field_type,
                char_limit=s.char_limit,
                is_required=s.is_required,
                grade_mode=s.grade_mode,
                grade_min=s.grade_min,
                grade_max=s.grade_max,
                grade_weight=s.grade_weight,
                rubric_criteria=copy.deepcopy(s.rubric_criteria),
                evaluation_criteria=s.evaluation_criteria,
                choice_config=copy.deepcopy(s.choice_config),
                mitre_attack_tags=list(s.mitre_attack_tags),
                capec_tags=list(s.capec_tags),
                cwe_tags=list(s.cwe_tags),
            )
        )
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="template.clone",
        resource_type="report_template",
        resource_id=clone.id,
        details={"from": str(template_id), "version": clone.version},
        ip=client_ip(request),
    )
    return DataEnvelope(data=TemplateDetailOut.from_model(clone, await _sections(db, clone.id)))


@router.post("/templates/{template_id}/archive")
async def archive_template(
    request: Request,
    template_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TemplateOut]:
    t = await _get_template(db, template_id)
    if t.status != "published":
        raise HTTPException(status_code=409, detail="only published templates can be archived")
    t.status = "archived"
    await db.flush()
    await db.refresh(t)
    await record_audit(
        db,
        user_id=actor.id,
        action="template.archive",
        resource_type="report_template",
        resource_id=t.id,
        details=None,
        ip=client_ip(request),
    )
    return DataEnvelope(data=TemplateOut.from_model(t, await _section_count(db, template_id)))


@router.get("/templates/{template_id}/versions")
async def list_template_versions(
    template_id: uuid.UUID,
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[list[TemplateVersionOut]]:
    t = await _get_template(db, template_id)
    rows = list(
        (
            await db.execute(
                select(ReportTemplate)
                .where(ReportTemplate.lineage_id == t.lineage_id)
                .order_by(ReportTemplate.version.desc())
            )
        )
        .scalars()
        .all()
    )
    return DataEnvelope(data=[TemplateVersionOut.from_model(r) for r in rows])


# ---------------------------------------------------------------------------
# Section sub-resource (create / update / delete / reorder, draft-only)
# ---------------------------------------------------------------------------


async def _get_section(db: AsyncSession, template_id: uuid.UUID, section_id: uuid.UUID) -> TemplateSectionDef:
    s = (
        await db.execute(
            select(TemplateSectionDef).where(
                TemplateSectionDef.id == section_id, TemplateSectionDef.template_id == template_id
            )
        )
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail="section not found")
    return s


@router.post("/templates/{template_id}/sections", status_code=201)
async def create_section(
    request: Request,
    template_id: uuid.UUID,
    body: SectionCreate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[SectionOut]:
    t = await _get_template(db, template_id)
    _require_draft(t)
    count = await _section_count(db, template_id)
    s = TemplateSectionDef(
        template_id=template_id,
        position=count,
        name=body.name,
        description=body.description,
        field_type=body.field_type,
        char_limit=body.char_limit,
        is_required=body.is_required,
        grade_mode=body.grade_mode,
        grade_min=body.grade_min,
        grade_max=body.grade_max,
        grade_weight=body.grade_weight,
        rubric_criteria=body.rubric_criteria,
        evaluation_criteria=body.evaluation_criteria,
        choice_config=_renormalize_choice_positions(body.choice_config),
        mitre_attack_tags=body.mitre_attack_tags,
        capec_tags=body.capec_tags,
        cwe_tags=body.cwe_tags,
    )
    db.add(s)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="template_section.create",
        resource_type="template_section",
        resource_id=s.id,
        details={"template_id": str(template_id)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=SectionOut.from_model(s))


@router.patch("/templates/{template_id}/sections/{section_id}")
async def update_section(
    request: Request,
    template_id: uuid.UUID,
    section_id: uuid.UUID,
    body: SectionUpdate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[SectionOut]:
    t = await _get_template(db, template_id)
    _require_draft(t)
    s = await _get_section(db, template_id, section_id)
    data = body.model_dump(exclude_unset=True)
    changed = sorted(data.keys())
    for k, v in data.items():
        setattr(s, k, v)
    err = section_invariant_error(
        field_type=s.field_type,
        char_limit=s.char_limit,
        choice_config=s.choice_config,
        grade_mode=s.grade_mode,
        grade_min=s.grade_min,
        grade_max=s.grade_max,
        rubric_criteria=s.rubric_criteria,
        grade_weight=s.grade_weight,
    )
    if err:
        raise HTTPException(status_code=422, detail=err)
    if s.field_type == "choice":
        s.choice_config = _renormalize_choice_positions(s.choice_config)
    await db.flush()
    await db.refresh(s)
    await record_audit(
        db,
        user_id=actor.id,
        action="template_section.update",
        resource_type="template_section",
        resource_id=s.id,
        details={"changed": changed},
        ip=client_ip(request),
    )
    return DataEnvelope(data=SectionOut.from_model(s))


@router.delete("/templates/{template_id}/sections/{section_id}", status_code=204)
async def delete_section(
    request: Request,
    template_id: uuid.UUID,
    section_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    t = await _get_template(db, template_id)
    _require_draft(t)
    s = await _get_section(db, template_id, section_id)
    await db.delete(s)
    await db.flush()
    # reindex remaining positions to 0..n-1
    for i, rest in enumerate(await _sections(db, template_id)):
        rest.position = i
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="template_section.delete",
        resource_type="template_section",
        resource_id=section_id,
        details=None,
        ip=client_ip(request),
    )


@router.post("/templates/{template_id}/sections/reorder")
async def reorder_sections(
    request: Request,
    template_id: uuid.UUID,
    body: ReorderBody,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[list[SectionOut]]:
    t = await _get_template(db, template_id)
    _require_draft(t)
    sections = await _sections(db, template_id)
    by_id = {str(s.id): s for s in sections}
    if set(body.ordered_ids) != set(by_id.keys()) or len(body.ordered_ids) != len(by_id):
        raise HTTPException(status_code=422, detail="ordered_ids must match the template's sections exactly")
    for i, sid in enumerate(body.ordered_ids):
        by_id[sid].position = i
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="template_section.reorder",
        resource_type="template_section",
        resource_id=template_id,
        details={"order": body.ordered_ids},
        ip=client_ip(request),
    )
    return DataEnvelope(data=[SectionOut.from_model(s) for s in await _sections(db, template_id)])


# ---------------------------------------------------------------------------
# Choice-value sub-resource (WP3 S4, #79) — the sanctioned mutations on a
# published template's choice_config. Deprecation hides a code from new saves
# without touching existing answers; deletion is allowed only while no
# report_section references the code (409 otherwise). A DB trigger (0008)
# backstops the invariant against non-route writes.
# ---------------------------------------------------------------------------


def _choice_values(s: TemplateSectionDef) -> list[dict[str, Any]]:
    if s.field_type != "choice":
        raise HTTPException(status_code=422, detail="section is not a choice section")
    return list((s.choice_config or {}).get("values", []))


def _find_choice_value(values: list[dict[str, Any]], code: str) -> dict[str, Any]:
    for v in values:
        if v.get("code") == code:
            return v
    raise HTTPException(status_code=404, detail="choice value not found")


async def _choice_code_referenced(db: AsyncSession, section_def_id: uuid.UUID, code: str) -> bool:
    row = (
        await db.execute(
            select(ReportSection.id)
            .where(ReportSection.section_def_id == section_def_id, ReportSection.choice_values.contains([code]))
            .limit(1)
        )
    ).first()
    return row is not None


@router.post("/templates/{template_id}/sections/{section_id}/choice-values/{code}/deprecate")
async def deprecate_choice_value(
    request: Request,
    template_id: uuid.UUID,
    section_id: uuid.UUID,
    code: str,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[SectionOut]:
    await _get_template(db, template_id)
    s = await _get_section(db, template_id, section_id)
    values = _choice_values(s)
    value = _find_choice_value(values, code)
    if value.get("deprecated_at"):
        raise HTTPException(status_code=409, detail="choice value is already deprecated")
    s.choice_config = {
        **(s.choice_config or {}),
        "values": [
            {**v, "deprecated_at": datetime.now(UTC).isoformat()} if v.get("code") == code else v for v in values
        ],
    }
    await db.flush()
    await db.refresh(s)
    await record_audit(
        db,
        user_id=actor.id,
        action="template_section.choice_value.deprecate",
        resource_type="template_section",
        resource_id=s.id,
        details={"code": code},
        ip=client_ip(request),
    )
    return DataEnvelope(data=SectionOut.from_model(s))


@router.delete("/templates/{template_id}/sections/{section_id}/choice-values/{code}")
async def delete_choice_value(
    request: Request,
    template_id: uuid.UUID,
    section_id: uuid.UUID,
    code: str,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[SectionOut]:
    await _get_template(db, template_id)
    s = await _get_section(db, template_id, section_id)
    values = _choice_values(s)
    _find_choice_value(values, code)
    if len(values) == 1:
        raise HTTPException(status_code=422, detail="choice_config.values must be non-empty")
    if await _choice_code_referenced(db, s.id, code):
        raise HTTPException(status_code=409, detail={"error": "choice_code_referenced", "code": code})
    s.choice_config = _renormalize_choice_positions(
        {**(s.choice_config or {}), "values": [v for v in values if v.get("code") != code]}
    )
    await db.flush()
    await db.refresh(s)
    await record_audit(
        db,
        user_id=actor.id,
        action="template_section.choice_value.delete",
        resource_type="template_section",
        resource_id=s.id,
        details={"code": code},
        ip=client_ip(request),
    )
    return DataEnvelope(data=SectionOut.from_model(s))


# ---------------------------------------------------------------------------
# JSON export / import (portable, id-free bundle; import always starts a new lineage)
# ---------------------------------------------------------------------------


@router.get("/templates/{template_id}/export")
async def export_template(
    template_id: uuid.UUID,
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TemplateBundle]:
    t = await _get_template(db, template_id)
    return DataEnvelope(data=TemplateBundle.from_model(t, await _sections(db, template_id)))


@router.post("/templates/import", status_code=201)
async def import_template(
    request: Request,
    body: TemplateBundle,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TemplateDetailOut]:
    t = ReportTemplate(
        lineage_id=uuid.uuid4(),
        version=1,
        name=body.name,
        report_type=body.report_type,
        description=body.description,
        status="draft",
        created_by=actor.id,
    )
    db.add(t)
    await db.flush()
    for i, sec in enumerate(body.sections):
        db.add(
            TemplateSectionDef(
                template_id=t.id,
                position=i,
                name=sec.name,
                description=sec.description,
                field_type=sec.field_type,
                char_limit=sec.char_limit,
                is_required=sec.is_required,
                grade_mode=sec.grade_mode,
                grade_min=sec.grade_min,
                grade_max=sec.grade_max,
                grade_weight=sec.grade_weight,
                rubric_criteria=sec.rubric_criteria,
                evaluation_criteria=sec.evaluation_criteria,
                choice_config=sec.choice_config,
                mitre_attack_tags=sec.mitre_attack_tags,
                capec_tags=sec.capec_tags,
                cwe_tags=sec.cwe_tags,
            )
        )
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="template.import",
        resource_type="report_template",
        resource_id=t.id,
        details={"name": t.name, "sections": len(body.sections)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=TemplateDetailOut.from_model(t, await _sections(db, t.id)))
