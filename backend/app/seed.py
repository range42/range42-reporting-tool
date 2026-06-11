"""Idempotent seed of the built-in system roles (``just seed``).

Upserts the five §5.2 ``role_definition`` rows by ``role_key`` (safe to re-run).
Invoked by ``just seed`` (``python -m app.seed``) and reused by tests.
"""

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import build_engine, get_sessionmaker
from app.core.permissions import SYSTEM_ROLES
from app.models import ScoringConfig, TeamTypeConfig
from app.models.role_definition import RoleDefinition


async def seed_system_roles(session: AsyncSession) -> int:
    """Upsert the built-in system roles by ``role_key``. Returns the count processed."""
    for role in SYSTEM_ROLES:
        existing = (
            await session.execute(select(RoleDefinition).where(RoleDefinition.role_key == role.role_key))
        ).scalar_one_or_none()
        perms = sorted(role.permissions)
        if existing is None:
            session.add(
                RoleDefinition(
                    role_key=role.role_key,
                    display_label=role.display_label,
                    description=role.description,
                    permissions=perms,
                    is_system=True,
                )
            )
        else:
            existing.display_label = role.display_label
            existing.description = role.description
            existing.permissions = perms
            existing.is_system = True
    await session.flush()
    return len(SYSTEM_ROLES)


@dataclass(frozen=True)
class _TeamTypeDefault:
    type_key: str
    display_label: str
    default_color: str
    is_visible_to_others: bool


DEFAULT_TEAM_TYPES: tuple[_TeamTypeDefault, ...] = (
    _TeamTypeDefault("blue", "Blue Team", "#3B82F6", True),
    _TeamTypeDefault("red", "Red Team", "#EF4444", True),
    _TeamTypeDefault("purple", "Purple Team", "#A855F7", True),
    _TeamTypeDefault("green", "Green Team", "#22C55E", True),
    _TeamTypeDefault("white", "White Cell", "#6B7280", False),
    _TeamTypeDefault("observer", "Observer", "#94A3B8", False),
)


async def seed_exercise_defaults(session: AsyncSession, exercise_id: uuid.UUID) -> None:
    """Idempotently seed the default team-type set + a scoring_config row for ``exercise_id``.

    Called inside the exercise-create transaction (the handler flushes the Exercise
    first to obtain its id, then calls this). Re-running is a no-op (select-by-key).
    """
    existing_types = {
        row
        for row in (
            await session.execute(select(TeamTypeConfig.type_key).where(TeamTypeConfig.exercise_id == exercise_id))
        ).scalars()
    }
    for d in DEFAULT_TEAM_TYPES:
        if d.type_key in existing_types:
            continue
        session.add(
            TeamTypeConfig(
                exercise_id=exercise_id,
                type_key=d.type_key,
                display_label=d.display_label,
                default_color=d.default_color,
                is_visible_to_others=d.is_visible_to_others,
            )
        )
    has_scoring = (
        await session.execute(select(ScoringConfig.id).where(ScoringConfig.exercise_id == exercise_id))
    ).first()
    if has_scoring is None:
        session.add(ScoringConfig(exercise_id=exercise_id))
    await session.flush()


async def _main() -> None:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    sm = get_sessionmaker(engine)
    try:
        async with sm() as session:
            count = await seed_system_roles(session)
            await session.commit()
            print(f"seeded {count} system roles")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
