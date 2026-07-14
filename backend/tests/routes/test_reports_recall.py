import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog, ExerciseRole
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _ga(migrated_db: async_sessionmaker) -> tuple[dict[str, str], str]:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, uid = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}, uid


async def _grant_role(migrated_db: async_sessionmaker, *, user_id: str, exercise_id: str, role_key: str) -> None:
    async with migrated_db() as s:
        s.add(ExerciseRole(user_id=uuid.UUID(user_id), exercise_id=uuid.UUID(exercise_id), role_key=role_key))
        await s.commit()


async def _audit_count(migrated_db: async_sessionmaker, action: str) -> int:
    async with migrated_db() as s:
        return (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))
        ).scalar_one()


async def _mk_report(c, ah, *, submit: bool) -> tuple[str, str]:
    """Create a filled report; optionally submit it (no approval_required -> submitted)."""
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
            json={"template_id": tid, "team_id": team, "name": "R"},
            headers=ah,
        )
    ).json()["data"]
    rid, sid = detail["id"], detail["sections"][0]["id"]
    await c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
        headers=ah,
    )
    if submit:
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
        assert r.json()["data"]["status"] == "submitted", r.text
    return ex, rid


async def test_recall_submitted_to_draft(migrated_db: async_sessionmaker) -> None:
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _mk_report(c, ah, submit=True)
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/recall", json={"comment": "needs edits"}, headers=ah)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "draft"
        assert d["submitted_at"] is None
    assert await _audit_count(migrated_db, "report.recall") == 1


async def test_recall_rejects_non_submitted(migrated_db: async_sessionmaker) -> None:
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _mk_report(c, ah, submit=False)  # still draft
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/recall", json={}, headers=ah)
        assert r.status_code == 409
        assert r.json()["error"]["message"] == "invalid_state"
    assert await _audit_count(migrated_db, "report.recall") == 0


async def test_recall_forbidden_without_permission(migrated_db: async_sessionmaker) -> None:
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _mk_report(c, ah, submit=True)
        ptok, _puid = await make_user_token(migrated_db, jti="plain", admin=False)
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/recall",
            json={},
            headers={"Authorization": f"Bearer {ptok}"},
        )
        assert r.status_code == 403
    assert await _audit_count(migrated_db, "report.recall") == 0
