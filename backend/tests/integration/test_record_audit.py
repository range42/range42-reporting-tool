import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.audit import record_audit
from app.models import AuditLog, User

pytestmark = pytest.mark.integration


async def _user(s: AsyncSession) -> User:
    u = User(external_id="oidc:a", email="a@x", display_name="A")
    s.add(u)
    await s.flush()
    return u


async def test_record_audit_writes_row(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        u = await _user(s)
        await record_audit(
            s,
            user_id=u.id,
            action="exercise.create",
            resource_type="exercise",
            resource_id=u.id,
            details={"name": "X"},
            ip="10.0.0.5",
        )
        await s.commit()
        row = (await s.execute(select(AuditLog).where(AuditLog.action == "exercise.create"))).scalar_one()
    assert row.resource_type == "exercise"
    assert row.details == {"name": "X"}
    assert str(row.ip_address) == "10.0.0.5"


async def test_record_audit_drops_bad_ip(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        u = await _user(s)
        await record_audit(s, user_id=u.id, action="x.y", resource_type="exercise", resource_id=u.id, ip="testclient")
        await s.commit()
        row = (await s.execute(select(AuditLog).where(AuditLog.action == "x.y"))).scalar_one()
    assert row.ip_address is None
