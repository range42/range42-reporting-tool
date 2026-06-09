"""Idempotent seed of the built-in system roles (``just seed``).

Upserts the five §5.2 ``role_definition`` rows by ``role_key`` (safe to re-run).
Invoked by ``just seed`` (``python -m app.seed``) and reused by tests.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import build_engine, get_sessionmaker
from app.core.permissions import SYSTEM_ROLES
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
