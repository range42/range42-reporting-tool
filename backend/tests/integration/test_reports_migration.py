import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def test_report_tables_exist_with_check(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        conn = await s.connection()
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        assert {"report", "report_section"} <= tables
        # backstop CHECK present
        n = (
            await s.execute(
                text(
                    "select count(*) from information_schema.check_constraints "
                    "where constraint_name = 'ck_report_section_shape'"
                )
            )
        ).scalar_one()
        assert n == 1
