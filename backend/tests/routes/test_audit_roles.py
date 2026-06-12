import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_role_mutations_are_audited(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        resp = await c.post(
            "/api/v1/roles",
            json={"role_key": "ciso", "display_label": "CISO", "permissions": ["exercises:read"]},
            headers=h,
        )
        rid = resp.json()["data"]["id"]
        await c.patch(f"/api/v1/roles/{rid}", json={"display_label": "Chief"}, headers=h)
        await c.delete(f"/api/v1/roles/{rid}", headers=h)
    async with migrated_db() as s:
        actions = set((await s.execute(select(AuditLog.action))).scalars().all())
        create_row = (await s.execute(select(AuditLog).where(AuditLog.action == "role.create"))).scalar_one()
    assert {"role.create", "role.update", "role.delete"} <= actions
    assert create_row.user_id is not None
    assert create_row.details == {"role_key": "ciso"}


async def test_system_role_patch_409_emits_no_audit(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    token, _ = await make_user_token(migrated_db, jti="ga2", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        listed = (await c.get("/api/v1/roles", headers=h)).json()["data"]
        sys_id = next(r["id"] for r in listed if r["is_system"])
        patch_sys = await c.patch(f"/api/v1/roles/{sys_id}", json={"display_label": "nope"}, headers=h)
    assert patch_sys.status_code == 409
    async with migrated_db() as s:
        n = (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "role.update"))
        ).scalar_one()
    assert n == 0
