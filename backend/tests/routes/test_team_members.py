import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _exercise_and_team(c, h) -> tuple[str, str]:
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=h)).json()["data"]["id"]
    resp = await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=h)
    tid = resp.json()["data"]["id"]
    return ex, tid


async def test_add_remove_member(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    _, member_id = await make_user_token(migrated_db, jti="member", admin=False)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex, tid = await _exercise_and_team(c, h)
        added = await c.post(f"/api/v1/exercises/{ex}/teams/{tid}/members", json={"user_id": member_id}, headers=h)
        dup = await c.post(f"/api/v1/exercises/{ex}/teams/{tid}/members", json={"user_id": member_id}, headers=h)
        removed = await c.delete(f"/api/v1/exercises/{ex}/teams/{tid}/members/{member_id}", headers=h)
    assert added.status_code == 201
    assert dup.status_code == 409
    assert removed.status_code == 204


async def test_add_member_unknown_user_404(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga2", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex, tid = await _exercise_and_team(c, h)
        r = await c.post(
            f"/api/v1/exercises/{ex}/teams/{tid}/members",
            json={"user_id": "00000000-0000-0000-0000-000000000000"},
            headers=h,
        )
    assert r.status_code == 404


async def test_membership_guards_get_team(migrated_db: async_sessionmaker) -> None:
    # Exercises the real require_team_membership branch (admin bypass NOT used here).
    admin_token, _ = await make_user_token(migrated_db, jti="ga3", admin=True)
    member_token, member_id = await make_user_token(migrated_db, jti="m", admin=False)
    outsider_token, _ = await make_user_token(migrated_db, jti="out", admin=False)
    ah = {"Authorization": f"Bearer {admin_token}"}
    async with client(migrated_db) as c:
        ex, tid = await _exercise_and_team(c, ah)
        await c.post(f"/api/v1/exercises/{ex}/teams/{tid}/members", json={"user_id": member_id}, headers=ah)
        mh = {"Authorization": f"Bearer {member_token}"}
        oh = {"Authorization": f"Bearer {outsider_token}"}
        member_resp = await c.get(f"/api/v1/exercises/{ex}/teams/{tid}", headers=mh)
        outsider_resp = await c.get(f"/api/v1/exercises/{ex}/teams/{tid}", headers=oh)
    assert member_resp.status_code == 200
    assert len(member_resp.json()["data"]["members"]) == 1
    assert outsider_resp.status_code == 403


async def test_list_members(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga4", admin=True)
    _, alice = await make_user_token(migrated_db, jti="alice", admin=False)
    _, bob = await make_user_token(migrated_db, jti="bob", admin=False)
    _, carol = await make_user_token(migrated_db, jti="carol", admin=False)  # created but not added
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex, tid = await _exercise_and_team(c, h)
        await c.post(f"/api/v1/exercises/{ex}/teams/{tid}/members", json={"user_id": alice}, headers=h)
        await c.post(f"/api/v1/exercises/{ex}/teams/{tid}/members", json={"user_id": bob}, headers=h)
        r = await c.get(f"/api/v1/exercises/{ex}/teams/{tid}/members", headers=h)
    assert r.status_code == 200, r.text
    by_uid = {m["user_id"]: m for m in r.json()["data"]}
    assert set(by_uid) == {alice, bob}  # carol excluded
    assert carol not in by_uid
    for m in by_uid.values():
        assert m["id"] and m["display_name"] and m["email"]


async def test_list_members_forbidden_for_non_member(migrated_db: async_sessionmaker) -> None:
    admin_token, _ = await make_user_token(migrated_db, jti="ga5", admin=True)
    outsider_token, _ = await make_user_token(migrated_db, jti="out2", admin=False)
    ah = {"Authorization": f"Bearer {admin_token}"}
    async with client(migrated_db) as c:
        ex, tid = await _exercise_and_team(c, ah)
        r = await c.get(
            f"/api/v1/exercises/{ex}/teams/{tid}/members",
            headers={"Authorization": f"Bearer {outsider_token}"},
        )
    assert r.status_code == 403
