import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import ExerciseRole, TeamMember
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _ga(migrated_db: async_sessionmaker) -> dict[str, str]:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def _grant_role(migrated_db: async_sessionmaker, *, user_id: str, exercise_id: str, role_key: str) -> None:
    async with migrated_db() as s:
        s.add(ExerciseRole(user_id=uuid.UUID(user_id), exercise_id=uuid.UUID(exercise_id), role_key=role_key))
        await s.commit()


async def _add_member(migrated_db: async_sessionmaker, *, user_id: str, team_id: str) -> None:
    async with migrated_db() as s:
        s.add(TeamMember(team_id=uuid.UUID(team_id), user_id=uuid.UUID(user_id)))
        await s.commit()


async def _grant_and_join(
    migrated_db: async_sessionmaker, *, user_id: str, exercise_id: str, team_id: str, role_key: str
) -> None:
    """Grant the exercise role (endpoint permission + eligibility) and join the report's team (read access)."""
    await _grant_role(migrated_db, user_id=user_id, exercise_id=exercise_id, role_key=role_key)
    await _add_member(migrated_db, user_id=user_id, team_id=team_id)


async def _mk_report(c, ah, chain: list[dict] | None) -> tuple[str, str, str]:
    """Create + fill + submit a report; returns (exercise_id, team_id, report_id).

    With a chain the report ends in pending_approval; with chain=None and no
    approval_required it goes straight to submitted.
    """
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
    payload: dict = {"template_id": tid, "team_id": team, "name": "R"}
    if chain is not None:
        payload["approval_required"] = True
        payload["approval_chain"] = chain
    detail = (await c.post(f"/api/v1/exercises/{ex}/reports", json=payload, headers=ah)).json()["data"]
    rid, sid = detail["id"], detail["sections"][0]["id"]
    await c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "rich_text", "content": "<p>x</p>"}},
        headers=ah,
    )
    await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    return ex, team, rid


async def _get_can_approve(c, ex: str, rid: str, headers: dict[str, str]) -> bool:
    r = await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["can_approve"]


async def test_can_approve_true_for_current_step_approver(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        atok, auid = await make_user_token(migrated_db, jti="appr", admin=False)
        ex, team, rid = await _mk_report(c, ah, [{"role_key": "team_approver", "required": True}])
        await _grant_and_join(migrated_db, user_id=auid, exercise_id=ex, team_id=team, role_key="team_approver")
        assert await _get_can_approve(c, ex, rid, {"Authorization": f"Bearer {atok}"}) is True


async def test_can_approve_false_for_non_approver(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        wtok, wuid = await make_user_token(migrated_db, jti="writer", admin=False)
        ex, team, rid = await _mk_report(c, ah, [{"role_key": "team_approver", "required": True}])
        # team_writer can read the report but holds no reports:approve
        await _grant_and_join(migrated_db, user_id=wuid, exercise_id=ex, team_id=team, role_key="team_writer")
        assert await _get_can_approve(c, ex, rid, {"Authorization": f"Bearer {wtok}"}) is False


async def test_can_approve_false_after_approving_own_step(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        atok, auid = await make_user_token(migrated_db, jti="userA", admin=False)
        btok, buid = await make_user_token(migrated_db, jti="userB", admin=False)
        ex, team, rid = await _mk_report(
            c, ah, [{"user_id": auid, "required": True}, {"user_id": buid, "required": True}]
        )
        for uid in (auid, buid):
            await _grant_and_join(migrated_db, user_id=uid, exercise_id=ex, team_id=team, role_key="team_approver")
        # before anyone approves: A (step 1) can, B (step 2) cannot yet
        assert await _get_can_approve(c, ex, rid, {"Authorization": f"Bearer {atok}"}) is True
        assert await _get_can_approve(c, ex, rid, {"Authorization": f"Bearer {btok}"}) is False
        # A approves step 1 -> current step is now 2 (B's); A can no longer approve
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={}, headers={"Authorization": f"Bearer {atok}"}
        )
        assert r.status_code == 200, r.text
        assert await _get_can_approve(c, ex, rid, {"Authorization": f"Bearer {atok}"}) is False
        assert await _get_can_approve(c, ex, rid, {"Authorization": f"Bearer {btok}"}) is True


async def test_can_approve_false_when_not_pending(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, _team, rid = await _mk_report(c, ah, None)  # no approval -> submitted
        assert await _get_can_approve(c, ex, rid, ah) is False


async def test_list_surfaces_can_approve(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        atok, auid = await make_user_token(migrated_db, jti="appr2", admin=False)
        ex, team, rid = await _mk_report(c, ah, [{"role_key": "team_approver", "required": True}])
        await _grant_and_join(migrated_db, user_id=auid, exercise_id=ex, team_id=team, role_key="team_approver")
        r = await c.get(
            f"/api/v1/exercises/{ex}/reports?status=pending_approval", headers={"Authorization": f"Bearer {atok}"}
        )
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        assert any(row["id"] == rid and row["can_approve"] is True for row in rows)
