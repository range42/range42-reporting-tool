import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.integration
async def test_rbac_tables_exist_at_head(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        conn = await s.connection()
        names = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert {"role_definition", "exercise_role"} <= set(names)


@pytest.mark.integration
async def test_exercise_role_unique_constraint(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        user_id = (
            await s.execute(
                text(
                    'INSERT INTO "user" (external_id, email, display_name) '
                    "VALUES ('oidc:c3', 'c3@x', 'C3') RETURNING id"
                )
            )
        ).scalar_one()
        ex = "11111111-1111-1111-1111-111111111111"
        await s.execute(
            text("INSERT INTO exercise (id, name, created_by) VALUES (:e, 'Test Exercise', :u)"),
            {"e": ex, "u": user_id},
        )
        await s.execute(
            text("INSERT INTO exercise_role (exercise_id, user_id, role_key) VALUES (:e, :u, 'team_writer')"),
            {"e": ex, "u": user_id},
        )
        with pytest.raises(Exception):  # noqa: B017 -- unique violation surfaces as a DBAPI error
            await s.execute(
                text("INSERT INTO exercise_role (exercise_id, user_id, role_key) VALUES (:e, :u, 'team_writer')"),
                {"e": ex, "u": user_id},
            )
            await s.flush()
