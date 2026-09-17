"""Demo-data seed for manual exploration of the app.

Run INSIDE the backend container (where ``deploy/.env`` is already loaded and the
``postgres`` hostname resolves on the compose network)::

    docker compose -f deploy/docker-compose.yml exec -T backend \
        uv run --no-sync python -m app.seed_demo

Seeds the *world* only. Persona users are deliberately absent: their rows are created by their
first SSO login, and ``app.seed_grants`` attaches roles and team membership afterwards.

Idempotent: every entity is looked up by its natural key before insert. It seeds:

* the 5 built-in system roles (reuses ``app.seed.seed_system_roles``);
* a global-admin user matching the emergency-login subject (``emergency:admin``),
  which also owns the seeded data as ``created_by``;
* one active exercise with the default team-type set + scoring config
  (reuses ``app.seed.seed_exercise_defaults``);
* two teams (Blue, Red), without members;
* the default report templates (reuses ``app.seed_default_templates.seed_default_templates``).

Log in through the emergency admin using the password whose bcrypt hash is in
``EMERGENCY_ADMIN_PASSWORD_HASH`` (``deploy/.env``), or through the IdP and then
run ``app.seed_grants``.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import build_engine, get_sessionmaker
from app.models.exercise import Exercise
from app.models.team import Team
from app.models.user import User
from app.seed import seed_exercise_defaults, seed_system_roles
from app.seed_default_templates import seed_default_templates

# --- the emergency admin (external_id is namespaced "{provider}:{subject}") ---
# Must mirror emergency_claims() (provider="emergency", subject="admin") so
# start_session()'s upsert on emergency-login reuses this row. Needs no exercise role.
ADMIN_EXTERNAL_ID = "emergency:admin"


@dataclass(frozen=True)
class _Persona:
    external_id: str
    email: str
    display_name: str
    is_global_admin: bool


ADMIN = _Persona(ADMIN_EXTERNAL_ID, "admin@localhost", "Emergency Admin", True)

EXERCISE_NAME = "Autumn Cyber Range 2026"
BLUE_TEAM_NAME = "Blue Team Alpha"
RED_TEAM_NAME = "Red Team Bravo"


async def _get_or_create_user(session: AsyncSession, p: _Persona) -> User:
    user = (await session.execute(select(User).where(User.external_id == p.external_id))).scalar_one_or_none()
    if user is None:
        user = User(
            external_id=p.external_id,
            email=p.email,
            display_name=p.display_name,
            is_global_admin=p.is_global_admin,
        )
        session.add(user)
        await session.flush()
    return user


async def _get_or_create_exercise(session: AsyncSession, *, created_by: uuid.UUID) -> Exercise:
    exercise = (await session.execute(select(Exercise).where(Exercise.name == EXERCISE_NAME))).scalar_one_or_none()
    if exercise is None:
        now = datetime.now(UTC)
        exercise = Exercise(
            name=EXERCISE_NAME,
            description="Seeded demo exercise for manual walkthroughs.",
            status="active",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=6),
            classification="UNCLASSIFIED",
            tlp="CLEAR",
            created_by=created_by,
        )
        session.add(exercise)
        await session.flush()
    return exercise


async def _get_or_create_team(
    session: AsyncSession, *, exercise_id: uuid.UUID, name: str, team_type: str, color: str
) -> Team:
    team = (
        await session.execute(select(Team).where(Team.exercise_id == exercise_id, Team.name == name))
    ).scalar_one_or_none()
    if team is None:
        team = Team(exercise_id=exercise_id, name=name, team_type=team_type, color=color)
        session.add(team)
        await session.flush()
    return team


async def seed_demo(session: AsyncSession) -> dict[str, Any]:
    """Seed the full demo dataset. Returns a summary dict for logging."""
    await seed_system_roles(session)

    admin = await _get_or_create_user(session, ADMIN)

    exercise = await _get_or_create_exercise(session, created_by=admin.id)
    await seed_exercise_defaults(session, exercise.id)

    blue = await _get_or_create_team(
        session, exercise_id=exercise.id, name=BLUE_TEAM_NAME, team_type="blue", color="#3B82F6"
    )
    red = await _get_or_create_team(
        session, exercise_id=exercise.id, name=RED_TEAM_NAME, team_type="red", color="#EF4444"
    )

    templates = await seed_default_templates(session, created_by=admin.id)

    return {
        "users": 1,
        "exercise": exercise.name,
        "teams": [blue.name, red.name],
        "templates": templates,
        "admin_external_id": ADMIN_EXTERNAL_ID,
    }


async def _main() -> None:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    sm = get_sessionmaker(engine)
    try:
        async with sm() as session:
            summary = await seed_demo(session)
            await session.commit()
    finally:
        await engine.dispose()

    print("demo seed complete:")
    print(f"  users            : {summary['users']} (emergency admin only)")
    print(f"  exercise         : {summary['exercise']} (+ default team-types & scoring)")
    print(f"  teams            : {', '.join(summary['teams'])} (no members yet)")
    for name, created in summary["templates"]:
        print(f"  template         : {name} ({'created' if created else 'already present'})")
    print("  log in as        : emergency admin (POST /api/v1/auth/emergency-login)")
    print("  next             : persona SSO logins, then `just seed-grants`")


if __name__ == "__main__":
    asyncio.run(_main())
