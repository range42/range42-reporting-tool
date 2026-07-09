import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_exercise_mutations_are_audited(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    _, member_id = await make_user_token(migrated_db, jti="u", admin=False)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=h)).json()["data"]["id"]
        await c.post(f"/api/v1/exercises/{ex}/team-types", json={"type_key": "k", "display_label": "K"}, headers=h)
        await c.post(f"/api/v1/exercises/{ex}/roles", json={"user_id": member_id, "role_key": "team_writer"}, headers=h)
        await c.patch(f"/api/v1/exercises/{ex}", json={"name": "E2"}, headers=h)
        await c.delete(f"/api/v1/exercises/{ex}", headers=h)
    async with migrated_db() as s:
        actions = set((await s.execute(select(AuditLog.action))).scalars().all())
        create_row = (await s.execute(select(AuditLog).where(AuditLog.action == "exercise.create"))).scalar_one()
    expected = {"exercise.create", "team_type.create", "exercise_role.assign", "exercise.update", "exercise.archive"}
    assert expected <= actions
    assert create_row.user_id is not None
    assert create_row.details == {"name": "E"}


async def test_conflict_emits_no_audit_row(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga2", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=h)).json()["data"]["id"]
        # "blue" is a seeded default team-type → this POST 409s
        dup = await c.post(
            f"/api/v1/exercises/{ex}/team-types",
            json={"type_key": "blue", "display_label": "x"},
            headers=h,
        )
    assert dup.status_code == 409
    async with migrated_db() as s:
        n = (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "team_type.create"))
        ).scalar_one()
    assert n == 0  # the 409 rolled back; no orphan audit row
