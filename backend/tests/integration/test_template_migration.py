import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.integration
async def test_template_tables_exist(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        rows = (
            (await s.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")))
            .scalars()
            .all()
        )
    assert {"report_template", "template_section_def"} <= set(rows)


@pytest.mark.integration
async def test_lineage_version_unique(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    from sqlalchemy.exc import IntegrityError

    async with migrated_db() as s:
        uid = (
            await s.execute(
                text(
                    'INSERT INTO "user" (id, external_id, email, display_name) '
                    "VALUES (gen_random_uuid(), 'oidc:t', 't@x', 'T') RETURNING id"
                )
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO report_template (id, lineage_id, version, name, report_type, status, created_by) "
                "VALUES (gen_random_uuid(), '11111111-1111-1111-1111-111111111111', 1, 'A', 'sitrep', 'draft', :u)"
            ),
            {"u": uid},
        )
        await s.commit()
    async with migrated_db() as s:
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO report_template (id, lineage_id, version, name, report_type, status, created_by) "
                    "VALUES (gen_random_uuid(), '11111111-1111-1111-1111-111111111111', 1, 'B', 'sitrep', 'draft', "
                    '(SELECT id FROM "user" LIMIT 1))'
                )
            )
            await s.commit()
