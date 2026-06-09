import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.integration
async def test_identity_tables_exist(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        rows = (
            (await s.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")))
            .scalars()
            .all()
        )
    assert {"user", "user_session", "audit_log"} <= set(rows)


@pytest.mark.integration
async def test_audit_log_insert_ok_but_update_delete_blocked(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    rid = str(uuid.uuid4())
    async with migrated_db() as s:
        await s.execute(
            text(
                "INSERT INTO audit_log (id, action, resource_type, resource_id) "
                "VALUES (gen_random_uuid(), 'test.action', 'report', :rid)"
            ),
            {"rid": rid},
        )
        await s.commit()

    # INSERT is allowed.
    async with migrated_db() as s:
        count = (
            await s.execute(text("SELECT count(*) FROM audit_log WHERE resource_id=:rid"), {"rid": rid})
        ).scalar_one()
        assert count == 1

    # UPDATE is blocked.
    async with migrated_db() as s:
        with pytest.raises(DBAPIError):
            await s.execute(text("UPDATE audit_log SET action='changed' WHERE resource_id=:rid"), {"rid": rid})
            await s.commit()

    # DELETE is blocked.
    async with migrated_db() as s:
        with pytest.raises(DBAPIError):
            await s.execute(text("DELETE FROM audit_log WHERE resource_id=:rid"), {"rid": rid})
            await s.commit()

    # Row is unchanged after the blocked mutations.
    async with migrated_db() as s:
        action = (
            await s.execute(text("SELECT action FROM audit_log WHERE resource_id=:rid"), {"rid": rid})
        ).scalar_one()
        assert action == "test.action"


@pytest.mark.integration
async def test_audit_log_truncate_blocked(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        with pytest.raises(DBAPIError):
            await s.execute(text("TRUNCATE audit_log"))
            await s.commit()
