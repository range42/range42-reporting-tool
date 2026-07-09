import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_team_mutations_are_audited(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    _, member_id = await make_user_token(migrated_db, jti="m", admin=False)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=h)).json()["data"]["id"]
        tid = (
            await c.post(
                f"/api/v1/exercises/{ex}/teams",
                json={"name": "A", "team_type": "blue"},
                headers=h,
            )
        ).json()["data"]["id"]
        await c.patch(f"/api/v1/exercises/{ex}/teams/{tid}", json={"name": "A2"}, headers=h)
        await c.post(f"/api/v1/exercises/{ex}/teams/{tid}/members", json={"user_id": member_id}, headers=h)
        await c.delete(f"/api/v1/exercises/{ex}/teams/{tid}/members/{member_id}", headers=h)
        await c.delete(f"/api/v1/exercises/{ex}/teams/{tid}", headers=h)
    async with migrated_db() as s:
        actions = set((await s.execute(select(AuditLog.action))).scalars().all())
        add_row = (await s.execute(select(AuditLog).where(AuditLog.action == "team_member.add"))).scalar_one()
    assert {"team.create", "team.update", "team_member.add", "team_member.remove", "team.delete"} <= actions
    assert add_row.user_id is not None
    assert add_row.details == {"team_id": tid, "user_id": member_id}


async def test_duplicate_member_conflict_emits_no_audit(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga2", admin=True)
    _, member_id = await make_user_token(migrated_db, jti="m2", admin=False)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=h)).json()["data"]["id"]
        tid = (
            await c.post(
                f"/api/v1/exercises/{ex}/teams",
                json={"name": "A", "team_type": "blue"},
                headers=h,
            )
        ).json()["data"]["id"]
        await c.post(f"/api/v1/exercises/{ex}/teams/{tid}/members", json={"user_id": member_id}, headers=h)
        dup = await c.post(f"/api/v1/exercises/{ex}/teams/{tid}/members", json={"user_id": member_id}, headers=h)
    assert dup.status_code == 409
    async with migrated_db() as s:
        n = (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "team_member.add"))
        ).scalar_one()
    assert n == 1  # only the first add, not the dup
