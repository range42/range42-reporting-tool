"""Exercise CRUD routes: create (seeds defaults), list (membership-filtered), get, update, archive."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, nulls_last, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.core.permissions import EXERCISES_READ, TEAMS_READ
from app.core.rbac import get_current_user, require_global_admin, require_permission
from app.models import Exercise, ExerciseRole, RoleDefinition, Team, TeamMember, TeamTypeConfig, User
from app.schemas.common import DataEnvelope, Page
from app.schemas.domain import (
    ExerciseCreate,
    ExerciseOut,
    ExerciseRoleCreate,
    ExerciseRoleOut,
    ExerciseUpdate,
    TeamTypeConfigCreate,
    TeamTypeConfigOut,
    TeamTypeConfigUpdate,
)
from app.seed import seed_exercise_defaults

router = APIRouter(tags=["exercises"])


async def _get_exercise(db: AsyncSession, exercise_id: uuid.UUID) -> Exercise:
    ex = (await db.execute(select(Exercise).where(Exercise.id == exercise_id))).scalar_one_or_none()
    if ex is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    return ex


@router.post("/exercises", status_code=201)
async def create_exercise(
    request: Request,
    body: ExerciseCreate,
    admin: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ExerciseOut]:
    ex = Exercise(
        name=body.name,
        description=body.description,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        classification=body.classification,
        tlp=body.tlp,
        classification_caveats=body.classification_caveats,
        metadata_=body.metadata,
        created_by=admin.id,
    )
    db.add(ex)
    await db.flush()
    await seed_exercise_defaults(db, ex.id)
    await record_audit(
        db,
        user_id=admin.id,
        action="exercise.create",
        resource_type="exercise",
        resource_id=ex.id,
        details={"name": ex.name},
        ip=client_ip(request),
    )
    return DataEnvelope(data=ExerciseOut.from_model(ex))


@router.get("/exercises")
async def list_exercises(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pp: PageParams = Depends(page_params),
) -> DataEnvelope[list[ExerciseOut]]:
    base = select(Exercise)
    count_q = select(func.count()).select_from(Exercise)
    if not user.is_global_admin:
        role_ex = select(ExerciseRole.exercise_id).where(ExerciseRole.user_id == user.id)
        team_ex = (
            select(Team.exercise_id)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == user.id)
        )
        visible = role_ex.union(team_ex).subquery()
        base = base.where(Exercise.id.in_(select(visible.c.exercise_id)))
        count_q = count_q.where(Exercise.id.in_(select(visible.c.exercise_id)))
    total = (await db.execute(count_q)).scalar_one()
    rows = (
        (await db.execute(base.order_by(nulls_last(Exercise.starts_at.desc())).offset(pp.offset).limit(pp.limit)))
        .scalars()
        .all()
    )
    return DataEnvelope(
        data=[ExerciseOut.from_model(e) for e in rows], meta=Page(page=pp.page, per_page=pp.per_page, total=total)
    )


@router.get("/exercises/{exercise_id}")
async def get_exercise(
    exercise_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(EXERCISES_READ)),
) -> DataEnvelope[ExerciseOut]:
    return DataEnvelope(data=ExerciseOut.from_model(await _get_exercise(db, exercise_id)))


@router.patch("/exercises/{exercise_id}")
async def update_exercise(
    request: Request,
    exercise_id: uuid.UUID,
    body: ExerciseUpdate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ExerciseOut]:
    ex = await _get_exercise(db, exercise_id)
    data = body.model_dump(exclude_unset=True)
    changed = sorted(data.keys())
    if "metadata" in data:
        ex.metadata_ = data.pop("metadata")
    for k, v in data.items():
        setattr(ex, k, v)
    await db.flush()
    await db.refresh(ex)
    await record_audit(
        db,
        user_id=actor.id,
        action="exercise.update",
        resource_type="exercise",
        resource_id=ex.id,
        details={"changed": changed},
        ip=client_ip(request),
    )
    return DataEnvelope(data=ExerciseOut.from_model(ex))


@router.delete("/exercises/{exercise_id}")
async def archive_exercise(
    request: Request,
    exercise_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ExerciseOut]:
    ex = await _get_exercise(db, exercise_id)
    ex.status = "archived"
    await db.flush()
    await db.refresh(ex)
    await record_audit(
        db,
        user_id=actor.id,
        action="exercise.archive",
        resource_type="exercise",
        resource_id=ex.id,
        details=None,
        ip=client_ip(request),
    )
    return DataEnvelope(data=ExerciseOut.from_model(ex))


@router.get("/exercises/{exercise_id}/team-types")
async def list_team_types(
    exercise_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(TEAMS_READ)),
) -> DataEnvelope[list[TeamTypeConfigOut]]:
    rows = (
        (
            await db.execute(
                select(TeamTypeConfig)
                .where(TeamTypeConfig.exercise_id == exercise_id)
                .order_by(TeamTypeConfig.type_key)
            )
        )
        .scalars()
        .all()
    )
    return DataEnvelope(data=[TeamTypeConfigOut.from_model(t) for t in rows])


@router.post("/exercises/{exercise_id}/team-types", status_code=201)
async def create_team_type(
    request: Request,
    exercise_id: uuid.UUID,
    body: TeamTypeConfigCreate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TeamTypeConfigOut]:
    await _get_exercise(db, exercise_id)
    t = TeamTypeConfig(
        exercise_id=exercise_id,
        type_key=body.type_key,
        display_label=body.display_label,
        default_color=body.default_color,
        is_visible_to_others=body.is_visible_to_others,
    )
    db.add(t)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="team type already exists") from None
    await record_audit(
        db,
        user_id=actor.id,
        action="team_type.create",
        resource_type="team_type",
        resource_id=t.id,
        details={"type_key": t.type_key, "exercise_id": str(exercise_id)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=TeamTypeConfigOut.from_model(t))


async def _get_team_type(db: AsyncSession, exercise_id: uuid.UUID, type_id: uuid.UUID) -> TeamTypeConfig:
    t = (
        await db.execute(
            select(TeamTypeConfig).where(TeamTypeConfig.id == type_id, TeamTypeConfig.exercise_id == exercise_id)
        )
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="team type not found")
    return t


@router.patch("/exercises/{exercise_id}/team-types/{type_id}")
async def update_team_type(
    request: Request,
    exercise_id: uuid.UUID,
    type_id: uuid.UUID,
    body: TeamTypeConfigUpdate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TeamTypeConfigOut]:
    t = await _get_team_type(db, exercise_id, type_id)
    changed = sorted(body.model_dump(exclude_unset=True).keys())
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="team_type.update",
        resource_type="team_type",
        resource_id=t.id,
        details={"changed": changed},
        ip=client_ip(request),
    )
    return DataEnvelope(data=TeamTypeConfigOut.from_model(t))


@router.delete("/exercises/{exercise_id}/team-types/{type_id}", status_code=204)
async def delete_team_type(
    request: Request,
    exercise_id: uuid.UUID,
    type_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    t = await _get_team_type(db, exercise_id, type_id)
    in_use = (
        await db.execute(select(Team.id).where(Team.exercise_id == exercise_id, Team.team_type == t.type_key).limit(1))
    ).first()
    if in_use is not None:
        raise HTTPException(status_code=409, detail="team type is in use by a team")
    await db.delete(t)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="team_type.delete",
        resource_type="team_type",
        resource_id=type_id,
        details=None,
        ip=client_ip(request),
    )


@router.post("/exercises/{exercise_id}/roles", status_code=201)
async def assign_role(
    request: Request,
    exercise_id: uuid.UUID,
    body: ExerciseRoleCreate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ExerciseRoleOut]:
    await _get_exercise(db, exercise_id)
    try:
        user_uuid = uuid.UUID(body.user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid user_id") from None
    user = (await db.execute(select(User).where(User.id == user_uuid))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    role = (
        await db.execute(select(RoleDefinition.role_key).where(RoleDefinition.role_key == body.role_key))
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=400, detail=f"unknown role '{body.role_key}'")
    r = ExerciseRole(exercise_id=exercise_id, user_id=user.id, role_key=body.role_key)
    db.add(r)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="user already holds this role in the exercise") from None
    await record_audit(
        db,
        user_id=actor.id,
        action="exercise_role.assign",
        resource_type="exercise_role",
        resource_id=r.id,
        details={"user_id": str(user.id), "role_key": body.role_key, "exercise_id": str(exercise_id)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=ExerciseRoleOut.from_model(r))


@router.get("/exercises/{exercise_id}/roles")
async def list_role_assignments(
    exercise_id: uuid.UUID,
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[list[ExerciseRoleOut]]:
    rows = (await db.execute(select(ExerciseRole).where(ExerciseRole.exercise_id == exercise_id))).scalars().all()
    return DataEnvelope(data=[ExerciseRoleOut.from_model(r) for r in rows])


@router.delete("/exercises/{exercise_id}/roles/{assignment_id}", status_code=204)
async def remove_role_assignment(
    request: Request,
    exercise_id: uuid.UUID,
    assignment_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    r = (
        await db.execute(
            select(ExerciseRole).where(ExerciseRole.id == assignment_id, ExerciseRole.exercise_id == exercise_id)
        )
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="assignment not found")
    await db.delete(r)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="exercise_role.revoke",
        resource_type="exercise_role",
        resource_id=assignment_id,
        details=None,
        ip=client_ip(request),
    )
