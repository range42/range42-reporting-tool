import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog, ExerciseRole
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _ga(migrated_db: async_sessionmaker) -> dict[str, str]:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def _grant(migrated_db: async_sessionmaker, *, user_id: str, exercise_id: str, role_key: str) -> None:
    async with migrated_db() as s:
        s.add(ExerciseRole(user_id=uuid.UUID(user_id), exercise_id=uuid.UUID(exercise_id), role_key=role_key))
        await s.commit()


async def _mk_pending_chain(c, ah, chain: list[dict]) -> tuple[str, str]:
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={"name": "S", "field_type": "rich_text", "is_required": True},
        headers=ah,
    )
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
    team = (await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)).json()[
        "data"
    ]["id"]
    detail = (
        await c.post(
            f"/api/v1/exercises/{ex}/reports",
            json={
                "template_id": tid,
                "team_id": team,
                "name": "R",
                "approval_required": True,
                "approval_chain": chain,
            },
            headers=ah,
        )
    ).json()["data"]
    rid, sid = detail["id"], detail["sections"][0]["id"]
    await c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "rich_text", "content": "<p>x</p>"}},
        headers=ah,
    )
    r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    assert r.json()["data"]["status"] == "pending_approval", r.text
    return ex, rid


async def _audit_count(migrated_db: async_sessionmaker, action: str) -> int:
    async with migrated_db() as s:
        return (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))
        ).scalar_one()


async def test_two_required_steps_finalize_on_last(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    chain = [{"role_key": "team_approver", "required": True}, {"role_key": "team_approver", "required": True}]
    async with client(migrated_db) as c:
        ex, rid = await _mk_pending_chain(c, ah, chain)
        r1 = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={}, headers=ah)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()["data"]
        assert d1["status"] == "pending_approval"  # first of two required steps
        assert len(d1["approval_records"]) == 1
        r2 = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={}, headers=ah)
        d2 = r2.json()["data"]
        assert d2["status"] == "submitted"  # last required step finalizes
        assert len(d2["approval_records"]) == 2
    assert await _audit_count(migrated_db, "report.approve") == 2


async def test_step_already_approved(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    chain = [{"role_key": "team_approver", "required": True}, {"role_key": "team_approver", "required": True}]
    async with client(migrated_db) as c:
        ex, rid = await _mk_pending_chain(c, ah, chain)
        await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={"step": 1}, headers=ah)
        dup = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={"step": 1}, headers=ah)
        assert dup.status_code == 409
        assert dup.json()["error"]["message"] == "step_already_approved"


async def test_optional_step_does_not_block(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    chain = [{"role_key": "team_approver", "required": True}, {"role_key": "team_approver", "required": False}]
    async with client(migrated_db) as c:
        ex, rid = await _mk_pending_chain(c, ah, chain)
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={}, headers=ah)
        assert r.json()["data"]["status"] == "submitted"  # only the required step gates


async def test_invalid_step(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _mk_pending_chain(c, ah, [{"role_key": "team_approver", "required": True}])
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={"step": 5}, headers=ah)
        assert r.status_code == 422
        assert r.json()["error"]["message"] == "invalid_step"


async def test_not_eligible_for_step(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        atok, auid = await make_user_token(migrated_db, jti="userA", admin=False)
        btok, buid = await make_user_token(migrated_db, jti="userB", admin=False)
        ex, rid = await _mk_pending_chain(c, ah, [{"user_id": auid, "required": True}])
        # both hold reports:approve (endpoint gate); only A is the step's designated user
        await _grant(migrated_db, user_id=auid, exercise_id=ex, role_key="team_approver")
        await _grant(migrated_db, user_id=buid, exercise_id=ex, role_key="team_approver")
        rb = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={}, headers={"Authorization": f"Bearer {btok}"}
        )
        assert rb.status_code == 403
        assert rb.json()["error"]["message"] == "not_eligible_for_step"
        ra = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={}, headers={"Authorization": f"Bearer {atok}"}
        )
        assert ra.status_code == 200
        assert ra.json()["data"]["status"] == "submitted"
