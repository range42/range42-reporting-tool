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


async def _mk_pending(c, ah) -> tuple[str, str, str]:
    """Create a report with approval_required, fill it, submit -> pending_approval."""
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
            json={"template_id": tid, "team_id": team, "name": "R", "approval_required": True},
            headers=ah,
        )
    ).json()["data"]
    rid, sid = detail["id"], detail["sections"][0]["id"]
    await c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
        headers=ah,
    )
    r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    assert r.json()["data"]["status"] == "pending_approval"
    return ex, rid, team


async def _grant_role(migrated_db: async_sessionmaker, *, user_id: str, exercise_id: str, role_key: str) -> None:
    async with migrated_db() as s:
        s.add(ExerciseRole(user_id=uuid.UUID(user_id), exercise_id=uuid.UUID(exercise_id), role_key=role_key))
        await s.commit()


async def _audit_count(migrated_db: async_sessionmaker, action: str) -> int:
    async with migrated_db() as s:
        return (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))
        ).scalar_one()


async def test_approve_single_step_finalizes(migrated_db: async_sessionmaker) -> None:
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={"comment": "lgtm"}, headers=ah)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "submitted"
        assert d["submitted_at"] is not None
        assert len(d["approval_records"]) == 1
        rec = d["approval_records"][0]
        assert rec["action"] == "approved"
        assert rec["step"] == 1
        assert rec["is_admin_override"] is False
    assert await _audit_count(migrated_db, "report.approve") == 1


async def test_approve_by_team_approver(migrated_db: async_sessionmaker) -> None:
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        atok, auid = await make_user_token(migrated_db, jti="appr", admin=False)
        await _grant_role(migrated_db, user_id=auid, exercise_id=ex, role_key="team_approver")
        approver_ah = {"Authorization": f"Bearer {atok}"}
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={}, headers=approver_ah)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "submitted"


async def test_approve_requires_pending(migrated_db: async_sessionmaker) -> None:
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        # a fresh draft (not submitted) cannot be approved
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
        team = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        rid = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports",
                json={"template_id": tid, "team_id": team, "name": "R"},
                headers=ah,
            )
        ).json()["data"]["id"]
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={}, headers=ah)
        assert r.status_code == 409
        assert r.json()["error"]["message"] == "invalid_state"
    assert await _audit_count(migrated_db, "report.approve") == 0


async def test_approve_forbidden_without_permission(migrated_db: async_sessionmaker) -> None:
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        ptok, _puid = await make_user_token(migrated_db, jti="plain", admin=False)
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve",
            json={},
            headers={"Authorization": f"Bearer {ptok}"},
        )
        assert r.status_code == 403
    assert await _audit_count(migrated_db, "report.approve") == 0


# --- W4-8: admin override (#39) -------------------------------------------------


async def _mk_pending_chain(c, ah, chain: list[dict]) -> tuple[str, str]:
    """Like _mk_pending but with an explicit approval_chain."""
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


async def test_admin_override_records_on_behalf_and_finalizes(migrated_db: async_sessionmaker) -> None:
    """A global admin approves a step on behalf of its designated (absent) approver.

    Records is_admin_override=True with approver_id = the target user, and — being
    the only required step — finalizes the chain to submitted.
    """
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        atok, auid = await make_user_token(migrated_db, jti="absent", admin=False)
        ex, rid = await _mk_pending_chain(c, ah, [{"user_id": auid, "required": True}])
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve",
            json={"on_behalf_of": auid, "comment": "approver unreachable"},
            headers=ah,
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "submitted"
        assert len(d["approval_records"]) == 1
        rec = d["approval_records"][0]
        assert rec["is_admin_override"] is True
        assert rec["approver_id"] == auid
    assert await _audit_count(migrated_db, "report.approve") == 1


async def test_admin_override_forbidden_for_non_global_admin(migrated_db: async_sessionmaker) -> None:
    """on_behalf_of by a non-global-admin (even one holding reports:approve) -> 403."""
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        atok, auid = await make_user_token(migrated_db, jti="target", admin=False)
        etok, euid = await make_user_token(migrated_db, jti="editor", admin=False)
        ex, rid = await _mk_pending_chain(c, ah, [{"user_id": auid, "required": True}])
        # editor holds reports:approve (passes the endpoint gate) but is not a global admin
        await _grant_role(migrated_db, user_id=euid, exercise_id=ex, role_key="team_approver")
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve",
            json={"on_behalf_of": auid},
            headers={"Authorization": f"Bearer {etok}"},
        )
        assert r.status_code == 403
        assert r.json()["error"]["message"] == "not_global_admin"
    assert await _audit_count(migrated_db, "report.approve") == 0
