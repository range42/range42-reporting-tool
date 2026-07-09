import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_template_mutations_are_audited(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=h)).json()["data"][
            "id"
        ]
        await c.post(f"/api/v1/templates/{tid}/sections", json={"name": "S", "field_type": "rich_text"}, headers=h)
        await c.post(f"/api/v1/templates/{tid}/publish", headers=h)
    async with migrated_db() as s:
        actions = set((await s.execute(select(AuditLog.action))).scalars().all())
    assert {"template.create", "template_section.create", "template.publish"} <= actions


async def test_import_is_audited(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        await c.post(
            "/api/v1/templates/import",
            json={"schema_version": 1, "name": "Imp", "report_type": "spot", "sections": []},
            headers=h,
        )
    async with migrated_db() as s:
        n = (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "template.import"))
        ).scalar_one()
    assert n == 1


async def test_failed_publish_emits_no_audit(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=h)).json()["data"][
            "id"
        ]
        await c.post(f"/api/v1/templates/{tid}/publish", headers=h)  # 409: no sections
    async with migrated_db() as s:
        n = (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "template.publish"))
        ).scalar_one()
    assert n == 0
