"""Team CRUD routes (per exercise): create (type-validated), list, get (with members), update, delete."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.db import get_db
from app.core.permissions import TEAMS_READ
from app.core.rbac import require_global_admin, require_permission, require_team_membership
from app.models import Team, TeamMember, TeamTypeConfig, User
from app.schemas.common import DataEnvelope
from app.schemas.domain import TeamCreate, TeamMemberCreate, TeamMemberOut, TeamMemberRowOut, TeamOut, TeamUpdate

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
    request: Request,
    exercise_id: uuid.UUID,
    body: TeamCreate,
    actor: User = Depends(require_global_admin),
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
    await record_audit(
        db,
        user_id=actor.id,
        action="team.create",
        resource_type="team",
        resource_id=t.id,
        details={"name": t.name, "exercise_id": str(exercise_id)},
        ip=client_ip(request),
    )
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


@router.get("/exercises/{exercise_id}/teams/{team_id}/members")
async def list_team_members(
    exercise_id: uuid.UUID,
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_team_membership),
) -> DataEnvelope[list[TeamMemberOut]]:
    """Members of a team — powers the assigned-writer selector (L7)."""
    await _get_team(db, exercise_id, team_id)
    rows = (
        await db.execute(
            select(TeamMember, User).join(User, User.id == TeamMember.user_id).where(TeamMember.team_id == team_id)
        )
    ).all()
    return DataEnvelope(data=[TeamMemberOut.from_row(m, u) for m, u in rows])


@router.patch("/exercises/{exercise_id}/teams/{team_id}")
async def update_team(
    request: Request,
    exercise_id: uuid.UUID,
    team_id: uuid.UUID,
    body: TeamUpdate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TeamOut]:
    t = await _get_team(db, exercise_id, team_id)
    changed = sorted(body.model_dump(exclude_unset=True).keys())
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
    await record_audit(
        db,
        user_id=actor.id,
        action="team.update",
        resource_type="team",
        resource_id=t.id,
        details={"changed": changed},
        ip=client_ip(request),
    )
    return DataEnvelope(data=TeamOut.from_model(t))


@router.delete("/exercises/{exercise_id}/teams/{team_id}", status_code=204)
async def delete_team(
    request: Request,
    exercise_id: uuid.UUID,
    team_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    t = await _get_team(db, exercise_id, team_id)
    await db.delete(t)  # CASCADE removes team_member rows
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="team.delete",
        resource_type="team",
        resource_id=team_id,
        details=None,
        ip=client_ip(request),
    )


@router.post("/exercises/{exercise_id}/teams/{team_id}/members", status_code=201)
async def add_member(
    request: Request,
    exercise_id: uuid.UUID,
    team_id: uuid.UUID,
    body: TeamMemberCreate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[TeamMemberRowOut]:
    await _get_team(db, exercise_id, team_id)
    try:
        user_uuid = uuid.UUID(body.user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid user_id") from None
    user = (await db.execute(select(User).where(User.id == user_uuid))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    m = TeamMember(team_id=team_id, user_id=user.id)
    db.add(m)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="user already a member of this team") from None
    await record_audit(
        db,
        user_id=actor.id,
        action="team_member.add",
        resource_type="team_member",
        resource_id=m.id,
        details={"team_id": str(team_id), "user_id": str(user.id)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=TeamMemberRowOut.from_model(m))


@router.delete("/exercises/{exercise_id}/teams/{team_id}/members/{user_id}", status_code=204)
async def remove_member(
    request: Request,
    exercise_id: uuid.UUID,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_team(db, exercise_id, team_id)
    m = (
        await db.execute(select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id))
    ).scalar_one_or_none()
    if m is None:
        raise HTTPException(status_code=404, detail="membership not found")
    await db.delete(m)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="team_member.remove",
        resource_type="team_member",
        resource_id=m.id,
        details={"team_id": str(team_id), "user_id": str(user_id)},
        ip=client_ip(request),
    )
