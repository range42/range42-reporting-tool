"""Custom role-definition CRUD (global). System roles are read-only (PATCH/DELETE → 409)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.core.rbac import require_global_admin
from app.models import ExerciseRole, RoleDefinition, User
from app.schemas.common import DataEnvelope, Page
from app.schemas.role import RoleCreate, RoleOut, RoleUpdate

router = APIRouter(tags=["roles"])


async def _get_role(db: AsyncSession, role_id: uuid.UUID) -> RoleDefinition:
    r = (await db.execute(select(RoleDefinition).where(RoleDefinition.id == role_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="role not found")
    return r


@router.post("/roles", status_code=201)
async def create_role(
    request: Request,
    body: RoleCreate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[RoleOut]:
    r = RoleDefinition(
        role_key=body.role_key,
        display_label=body.display_label,
        description=body.description,
        permissions=sorted(body.permissions),
        is_system=False,
    )
    db.add(r)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="role_key already exists") from None
    await record_audit(
        db,
        user_id=actor.id,
        action="role.create",
        resource_type="role",
        resource_id=r.id,
        details={"role_key": r.role_key},
        ip=client_ip(request),
    )
    return DataEnvelope(data=RoleOut.from_model(r))


@router.get("/roles")
async def list_roles(
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
    pp: PageParams = Depends(page_params),
) -> DataEnvelope[list[RoleOut]]:
    total = (await db.execute(select(func.count()).select_from(RoleDefinition))).scalar_one()
    rows = (
        (
            await db.execute(
                select(RoleDefinition)
                .order_by(RoleDefinition.is_system.desc(), RoleDefinition.role_key)
                .offset(pp.offset)
                .limit(pp.limit)
            )
        )
        .scalars()
        .all()
    )
    return DataEnvelope(
        data=[RoleOut.from_model(r) for r in rows], meta=Page(page=pp.page, per_page=pp.per_page, total=total)
    )


@router.patch("/roles/{role_id}")
async def update_role(
    request: Request,
    role_id: uuid.UUID,
    body: RoleUpdate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[RoleOut]:
    r = await _get_role(db, role_id)
    if r.is_system:
        raise HTTPException(status_code=409, detail="cannot modify a system role")
    changed = sorted(body.model_dump(exclude_unset=True).keys())
    data = body.model_dump(exclude_unset=True)
    if data.get("permissions") is not None:
        data["permissions"] = sorted(data["permissions"])
    for k, v in data.items():
        setattr(r, k, v)
    await db.flush()
    await db.refresh(r)
    await record_audit(
        db,
        user_id=actor.id,
        action="role.update",
        resource_type="role",
        resource_id=r.id,
        details={"changed": changed},
        ip=client_ip(request),
    )
    return DataEnvelope(data=RoleOut.from_model(r))


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    request: Request,
    role_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    r = await _get_role(db, role_id)
    if r.is_system:
        raise HTTPException(status_code=409, detail="cannot delete a system role")
    assigned = (await db.execute(select(ExerciseRole.id).where(ExerciseRole.role_key == r.role_key).limit(1))).first()
    if assigned is not None:
        raise HTTPException(status_code=409, detail="role has active assignments")
    await db.delete(r)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="role.delete",
        resource_type="role",
        resource_id=role_id,
        details=None,
        ip=client_ip(request),
    )
