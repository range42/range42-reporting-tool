"""Exercise CRUD routes: create (seeds defaults), list (membership-filtered), get, update, archive."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.core.permissions import EXERCISES_READ
from app.core.rbac import get_current_user, require_global_admin, require_permission
from app.models import Exercise, ExerciseRole, Team, TeamMember, User
from app.schemas.common import DataEnvelope, Page
from app.schemas.domain import ExerciseCreate, ExerciseOut, ExerciseUpdate
from app.seed import seed_exercise_defaults

router = APIRouter(tags=["exercises"])


async def _get_exercise(db: AsyncSession, exercise_id: uuid.UUID) -> Exercise:
    ex = (await db.execute(select(Exercise).where(Exercise.id == exercise_id))).scalar_one_or_none()
    if ex is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    return ex


@router.post("/exercises", status_code=201)
async def create_exercise(
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
    exercise_id: uuid.UUID,
    body: ExerciseUpdate,
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ExerciseOut]:
    ex = await _get_exercise(db, exercise_id)
    data = body.model_dump(exclude_unset=True)
    if "metadata" in data:
        ex.metadata_ = data.pop("metadata")
    for k, v in data.items():
        setattr(ex, k, v)
    await db.flush()
    await db.refresh(ex)
    return DataEnvelope(data=ExerciseOut.from_model(ex))


@router.delete("/exercises/{exercise_id}")
async def archive_exercise(
    exercise_id: uuid.UUID,
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ExerciseOut]:
    ex = await _get_exercise(db, exercise_id)
    ex.status = "archived"
    await db.flush()
    await db.refresh(ex)
    return DataEnvelope(data=ExerciseOut.from_model(ex))
