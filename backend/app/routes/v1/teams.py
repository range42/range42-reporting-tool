"""Team CRUD routes (per exercise): create (type-validated), list, get (with members), update, delete."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.permissions import TEAMS_READ
from app.core.rbac import require_global_admin, require_permission, require_team_membership
from app.models import Team, TeamMember, TeamTypeConfig, User
from app.schemas.common import DataEnvelope
from app.schemas.domain import TeamCreate, TeamMemberOut, TeamOut, TeamUpdate

router = APIRouter(tags=["teams"])


async def _get_team(db: AsyncSession, exercise_id: uuid.UUID, team_id: uuid.UUID) -> Team:
    t = (await db.execute(select(Team).where(Team.id == team_id, Team.exercise_id == exercise_id))).scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="team not found")
    return t


async def _assert_team_type(db: AsyncSession, exercise_id: uuid.UUID, type_key: str) -> None:
    exists = (
        await db.execute(
            select(TeamTypeConfig.id).where(
                TeamTypeConfig.exercise_id == exercise_id, TeamTypeConfig.type_key == type_key
            )
        )
    ).first()
    if exists is None:
        raise HTTPException(status_code=400, detail=f"unknown team_type '{type_key}' for this exercise")


@router.post("/exercises/{exercise_id}/teams", status_code=201)
async def create_team(
    exercise_id: uuid.UUID,
    body: TeamCreate,
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TeamOut]:
    await _assert_team_type(db, exercise_id, body.team_type)
    t = Team(
        exercise_id=exercise_id, name=body.name, team_type=body.team_type, color=body.color, metadata_=body.metadata
    )
    db.add(t)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="team name already exists in this exercise") from None
    return DataEnvelope(data=TeamOut.from_model(t))


@router.get("/exercises/{exercise_id}/teams")
async def list_teams(
    exercise_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(TEAMS_READ)),
) -> DataEnvelope[list[TeamOut]]:
    rows = (await db.execute(select(Team).where(Team.exercise_id == exercise_id).order_by(Team.name))).scalars().all()
    return DataEnvelope(data=[TeamOut.from_model(t) for t in rows])


@router.get("/exercises/{exercise_id}/teams/{team_id}")
async def get_team(
    exercise_id: uuid.UUID,
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_team_membership),
) -> DataEnvelope[TeamOut]:
    t = await _get_team(db, exercise_id, team_id)
    rows = (
        await db.execute(
            select(TeamMember, User).join(User, User.id == TeamMember.user_id).where(TeamMember.team_id == team_id)
        )
    ).all()
    members = [TeamMemberOut.from_row(m, u) for m, u in rows]
    return DataEnvelope(data=TeamOut.from_model(t, members=members))


@router.patch("/exercises/{exercise_id}/teams/{team_id}")
async def update_team(
    exercise_id: uuid.UUID,
    team_id: uuid.UUID,
    body: TeamUpdate,
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TeamOut]:
    t = await _get_team(db, exercise_id, team_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("team_type") is not None:
        await _assert_team_type(db, exercise_id, data["team_type"])
    if "metadata" in data:
        t.metadata_ = data.pop("metadata")
    for k, v in data.items():
        setattr(t, k, v)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="team name already exists in this exercise") from None
    await db.refresh(t)
    return DataEnvelope(data=TeamOut.from_model(t))


@router.delete("/exercises/{exercise_id}/teams/{team_id}", status_code=204)
async def delete_team(
    exercise_id: uuid.UUID,
    team_id: uuid.UUID,
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    t = await _get_team(db, exercise_id, team_id)
    await db.delete(t)  # CASCADE removes team_member rows
    await db.flush()
