import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def _check_constraint_count(s: AsyncSession, name: str) -> int:
    return (
        await s.execute(
            text("select count(*) from information_schema.check_constraints where constraint_name = :n"),
            {"n": name},
        )
    ).scalar_one()


async def test_report_tables_exist_with_check(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        conn = await s.connection()
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        assert {"report", "report_section"} <= tables
        # backstop CHECK present
        assert await _check_constraint_count(s, "ck_report_section_shape") == 1


async def test_approval_tables_and_checks(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        conn = await s.connection()
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        assert "approval_record" in tables
        cols = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("report")})
        assert "approval_chain" in cols
        assert await _check_constraint_count(s, "ck_approval_record_action") == 1
        assert await _check_constraint_count(s, "ck_report_status") == 1
