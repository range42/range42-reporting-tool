"""Attach persona roles to users that have already logged in, matched by email.

Run INSIDE the backend container, AFTER each persona's first SSO login::

    docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml \
        exec -T backend uv run --no-sync python -m app.seed_grants

Why this is a separate step from ``app.seed_demo``: a Dex subject is a base64
protobuf of ``{userID, connectorID}`` and is not knowable from the IdP config,
so a role cannot be pre-assigned to a subject that has never logged in. Email is
the join key instead — it is also IdP-agnostic, so pointing this at a production
IdP later needs no change here.

Matching happens on ``User.email`` for *seeding only*. The login path
(``upsert_user``) must keep linking on ``{provider}:{subject}``: email is a
mutable claim, and matching on it there would turn control of an email at any
configured IdP into account takeover.

Idempotent, and safe to re-run as more personas log in — a persona who has not
logged in yet is reported as skipped, not an error.
"""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import build_engine, get_sessionmaker
from app.models.exercise import Exercise
from app.models.exercise_role import ExerciseRole
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.user import User
from app.seed_demo import BLUE_TEAM_NAME, EXERCISE_NAME, RED_TEAM_NAME


@dataclass(frozen=True)
class _Grant:
    email: str
    role_key: str
    team_name: str | None
    is_global_admin: bool = False


# Emails must stay in step with staticPasswords in deploy/dex/config.yaml;
# tests/integration/test_seed_grants.py asserts the two lists match.
GRANTS: tuple[_Grant, ...] = (
    _Grant("admin@range42.local", "team_admin", None, is_global_admin=True),
    _Grant("alice@range42.local", "team_writer", BLUE_TEAM_NAME),
    _Grant("bob@range42.local", "team_approver", BLUE_TEAM_NAME),
    _Grant("carol@range42.local", "evaluator", None),
    _Grant("dave@range42.local", "observer", RED_TEAM_NAME),
)


async def _ensure_team_member(session: AsyncSession, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    exists = (
        await session.execute(select(TeamMember.id).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id))
    ).first()
    if exists is None:
        session.add(TeamMember(team_id=team_id, user_id=user_id))


async def _ensure_exercise_role(
    session: AsyncSession, *, exercise_id: uuid.UUID, user_id: uuid.UUID, role_key: str
) -> None:
    exists = (
        await session.execute(
            select(ExerciseRole.id).where(
                ExerciseRole.exercise_id == exercise_id,
                ExerciseRole.user_id == user_id,
                ExerciseRole.role_key == role_key,
            )
        )
    ).first()
    if exists is None:
        session.add(ExerciseRole(exercise_id=exercise_id, user_id=user_id, role_key=role_key))


async def seed_grants(session: AsyncSession) -> dict[str, Any]:
    """Grant roles + team membership to logged-in personas. Returns a summary."""
    exercise = (await session.execute(select(Exercise).where(Exercise.name == EXERCISE_NAME))).scalar_one_or_none()
    if exercise is None:
        raise RuntimeError(f"demo exercise {EXERCISE_NAME!r} not found — run the demo seed first")

    teams = {
        t.name: t for t in (await session.execute(select(Team).where(Team.exercise_id == exercise.id))).scalars().all()
    }

    granted: list[str] = []
    skipped: list[str] = []
    promoted: list[str] = []
    for grant in GRANTS:
        user = (await session.execute(select(User).where(User.email == grant.email))).scalar_one_or_none()
        if user is None:
            skipped.append(grant.email)
            continue

        await _ensure_exercise_role(session, exercise_id=exercise.id, user_id=user.id, role_key=grant.role_key)
        if grant.team_name is not None:
            team = teams.get(grant.team_name)
            if team is None:
                raise RuntimeError(f"team {grant.team_name!r} missing from {exercise.name!r} — re-run the demo seed")
            await _ensure_team_member(session, team_id=team.id, user_id=user.id)

        # Reconcile on update, never clear: the row already exists by the time
        # this runs, and neither upsert_user() nor the demo seed's insert-only
        # branch will ever set this flag for a persona who logged in first.
        if grant.is_global_admin and not user.is_global_admin:
            user.is_global_admin = True
            promoted.append(grant.email)

        granted.append(grant.email)
    await session.flush()

    return {
        "exercise": exercise.name,
        "granted": len(granted),
        "granted_emails": granted,
        "skipped": len(skipped),
        "skipped_emails": skipped,
        "promoted_to_global_admin": promoted,
    }


async def _main() -> None:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    sm = get_sessionmaker(engine)
    try:
        async with sm() as session:
            summary = await seed_grants(session)
            await session.commit()
    finally:
        await engine.dispose()
    print(f"grants: {summary}")
    if summary["skipped"]:
        print(f"not yet logged in (re-run after they do): {', '.join(summary['skipped_emails'])}")


if __name__ == "__main__":
    asyncio.run(_main())
