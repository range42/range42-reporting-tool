import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _admin(migrated_db: async_sessionmaker) -> dict[str, str]:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {token}"}


async def test_create_list_get_patch_delete(migrated_db: async_sessionmaker) -> None:
    h = await _admin(migrated_db)
    async with client(migrated_db) as c:
        created = await c.post("/api/v1/templates", json={"name": "Spot", "report_type": "spot"}, headers=h)
        assert created.status_code == 201
        t = created.json()["data"]
        assert t["version"] == 1 and t["status"] == "draft" and t["section_count"] == 0
        tid = t["id"]

        got = await c.get(f"/api/v1/templates/{tid}", headers=h)
        assert got.status_code == 200 and got.json()["data"]["sections"] == []

        patched = await c.patch(f"/api/v1/templates/{tid}", json={"name": "Spot Report"}, headers=h)
        assert patched.status_code == 200 and patched.json()["data"]["name"] == "Spot Report"

        listed = await c.get("/api/v1/templates", headers=h)
        assert listed.status_code == 200 and listed.json()["meta"]["total"] == 1

        deleted = await c.delete(f"/api/v1/templates/{tid}", headers=h)
        assert deleted.status_code == 204
        assert (await c.get(f"/api/v1/templates/{tid}", headers=h)).status_code == 404


async def test_patch_rejects_explicit_null_name(migrated_db: async_sessionmaker) -> None:
    h = await _admin(migrated_db)
    async with client(migrated_db) as c:
        resp = await c.post("/api/v1/templates", json={"name": "X", "report_type": "spot"}, headers=h)
        tid = resp.json()["data"]["id"]
        r = await c.patch(f"/api/v1/templates/{tid}", json={"name": None}, headers=h)
    assert r.status_code == 422


async def test_non_admin_403_and_unauth_401(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="u", admin=False)
    async with client(migrated_db) as c:
        assert (await c.get("/api/v1/templates")).status_code == 401
        r = await c.get("/api/v1/templates", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
