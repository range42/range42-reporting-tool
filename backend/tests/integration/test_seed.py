import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.role_definition import RoleDefinition
from app.seed import seed_system_roles


@pytest.mark.integration
async def test_seed_is_idempotent_and_correct(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        n1 = await seed_system_roles(s)
        await s.commit()
        n2 = await seed_system_roles(s)
        await s.commit()
        rows = (await s.execute(select(RoleDefinition))).scalars().all()
    assert n1 == 5
    assert n2 == 5
    assert len(rows) == 5
    by = {r.role_key: r for r in rows}
    assert set(by) == {"team_admin", "team_writer", "team_approver", "evaluator", "observer"}
    assert all(r.is_system is True for r in rows)
    assert "reports:recall" in by["team_admin"].permissions
    assert "reports:read:all" in by["observer"].permissions
    assert "reports:write" not in by["observer"].permissions
