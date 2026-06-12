import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_custom_role_lifecycle_and_system_guard(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        created = await c.post(
            "/api/v1/roles",
            json={"role_key": "ciso", "display_label": "CISO", "permissions": ["exercises:read", "scoring:read:all"]},
            headers=h,
        )
        dup = await c.post(
            "/api/v1/roles",
            json={"role_key": "ciso", "display_label": "x", "permissions": []},
            headers=h,
        )
        bad_perm = await c.post(
            "/api/v1/roles", json={"role_key": "z", "display_label": "Z", "permissions": ["bogus"]}, headers=h
        )
        listed = await c.get("/api/v1/roles", headers=h)
        rid = created.json()["data"]["id"]
        sys_id = next(r["id"] for r in listed.json()["data"] if r["is_system"])
        patch_sys = await c.patch(f"/api/v1/roles/{sys_id}", json={"display_label": "nope"}, headers=h)
        del_sys = await c.delete(f"/api/v1/roles/{sys_id}", headers=h)
        patch_ok = await c.patch(f"/api/v1/roles/{rid}", json={"display_label": "Chief"}, headers=h)
        del_ok = await c.delete(f"/api/v1/roles/{rid}", headers=h)
    assert created.status_code == 201
    assert created.json()["data"]["is_system"] is False
    assert dup.status_code == 409
    assert bad_perm.status_code == 422
    assert patch_sys.status_code == 409
    assert del_sys.status_code == 409
    assert patch_ok.status_code == 200
    assert patch_ok.json()["data"]["display_label"] == "Chief"
    assert del_ok.status_code == 204


async def test_delete_role_with_assignments_409(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    token, _ = await make_user_token(migrated_db, jti="ga2", admin=True)
    _, member_id = await make_user_token(migrated_db, jti="u2", admin=False)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        resp = await c.post(
            "/api/v1/roles",
            json={"role_key": "lead", "display_label": "Lead", "permissions": ["exercises:read"]},
            headers=h,
        )
        rid = resp.json()["data"]["id"]
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=h)).json()["data"]["id"]
        await c.post(f"/api/v1/exercises/{ex}/roles", json={"user_id": member_id, "role_key": "lead"}, headers=h)
        blocked = await c.delete(f"/api/v1/roles/{rid}", headers=h)
    assert blocked.status_code == 409
