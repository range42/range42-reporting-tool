import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.integration
async def test_domain_tables_exist(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        rows = (
            (await s.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")))
            .scalars()
            .all()
        )
    assert {"exercise", "team", "team_type_config", "team_member", "scoring_config"} <= set(rows)


@pytest.mark.integration
async def test_exercise_role_fk_enforced(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    # exercise_role.exercise_id now references exercise(id); an orphan insert must fail
    # at execute() time (asyncpg sends the statement immediately).
    async with migrated_db() as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text(
                    "INSERT INTO exercise_role (id, exercise_id, user_id, role_key) "
                    "VALUES (gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), 'team_writer')"
                )
            )
