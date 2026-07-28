"""L7 assignment-based write-locking on section saves (WP4 #27 Task L7).

When a report has an ``assigned_writer_id``, only the assigned writer, a team
admin (holder of ``reports:recall``), or a global admin may edit its sections.
Unassigned reports keep the team-scoped policy.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _seed(migrated_db):
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()


async def _published_template(c, ah) -> str:
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={"name": "S", "field_type": "rich_text", "is_required": True},
        headers=ah,
    )
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    return tid


async def _team_user(c, ah, migrated_db, *, jti: str, ex: str, team: str, role_key: str) -> tuple[dict, str]:
    """Create a user, add them to the team with an exercise role; return (auth headers, user id)."""
    tok, uid = await make_user_token(migrated_db, jti=jti, admin=False)
    await c.post(f"/api/v1/exercises/{ex}/teams/{team}/members", json={"user_id": uid}, headers=ah)
    await c.post(f"/api/v1/exercises/{ex}/roles", json={"user_id": uid, "role_key": role_key}, headers=ah)
    return {"Authorization": f"Bearer {tok}"}, uid


async def _exercise_team(c, ah) -> tuple[str, str]:
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
    team = (
        await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Alpha", "team_type": "blue"}, headers=ah)
    ).json()["data"]["id"]
    return ex, team


async def _report(c, ah, *, tid: str, ex: str, team: str, assigned_writer_id: str | None) -> tuple[str, str]:
    """Instantiate a report; return (report id, first section id)."""
    body: dict = {"template_id": tid, "team_id": team, "name": "R"}
    if assigned_writer_id is not None:
        body["assigned_writer_id"] = assigned_writer_id
    detail = (await c.post(f"/api/v1/exercises/{ex}/reports", json=body, headers=ah)).json()["data"]
    return detail["id"], detail["sections"][0]["id"]


def _save(c, ex: str, rid: str, sid: str, headers: dict):
    return c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "rich_text", "content": "<p>x</p>"}},
        headers=headers,
    )


async def test_assigned_writer_can_edit(migrated_db: async_sessionmaker) -> None:
    await _seed(migrated_db)
    ga, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {ga}"}
    async with client(migrated_db) as c:
        tid = await _published_template(c, ah)
        ex, team = await _exercise_team(c, ah)
        wh, wid = await _team_user(c, ah, migrated_db, jti="w1", ex=ex, team=team, role_key="team_writer")
        rid, sid = await _report(c, ah, tid=tid, ex=ex, team=team, assigned_writer_id=wid)
        r = await _save(c, ex, rid, sid, wh)
        assert r.status_code == 200


async def test_other_team_writer_locked_out(migrated_db: async_sessionmaker) -> None:
    await _seed(migrated_db)
    ga, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {ga}"}
    async with client(migrated_db) as c:
        tid = await _published_template(c, ah)
        ex, team = await _exercise_team(c, ah)
        _, wid = await _team_user(c, ah, migrated_db, jti="w1", ex=ex, team=team, role_key="team_writer")
        other_h, _ = await _team_user(c, ah, migrated_db, jti="w2", ex=ex, team=team, role_key="team_writer")
        rid, sid = await _report(c, ah, tid=tid, ex=ex, team=team, assigned_writer_id=wid)
        r = await _save(c, ex, rid, sid, other_h)
        assert r.status_code == 403


async def test_team_admin_can_edit_assigned(migrated_db: async_sessionmaker) -> None:
    await _seed(migrated_db)
    ga, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {ga}"}
    async with client(migrated_db) as c:
        tid = await _published_template(c, ah)
        ex, team = await _exercise_team(c, ah)
        _, wid = await _team_user(c, ah, migrated_db, jti="w1", ex=ex, team=team, role_key="team_writer")
        admin_h, _ = await _team_user(c, ah, migrated_db, jti="ta", ex=ex, team=team, role_key="team_admin")
        rid, sid = await _report(c, ah, tid=tid, ex=ex, team=team, assigned_writer_id=wid)
        r = await _save(c, ex, rid, sid, admin_h)
        assert r.status_code == 200


async def test_global_admin_can_edit_assigned(migrated_db: async_sessionmaker) -> None:
    await _seed(migrated_db)
    ga, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {ga}"}
    async with client(migrated_db) as c:
        tid = await _published_template(c, ah)
        ex, team = await _exercise_team(c, ah)
        _, wid = await _team_user(c, ah, migrated_db, jti="w1", ex=ex, team=team, role_key="team_writer")
        rid, sid = await _report(c, ah, tid=tid, ex=ex, team=team, assigned_writer_id=wid)
        r = await _save(c, ex, rid, sid, ah)
        assert r.status_code == 200


async def test_unassigned_keeps_team_policy(migrated_db: async_sessionmaker) -> None:
    await _seed(migrated_db)
    ga, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {ga}"}
    async with client(migrated_db) as c:
        tid = await _published_template(c, ah)
        ex, team = await _exercise_team(c, ah)
        wh, _ = await _team_user(c, ah, migrated_db, jti="w1", ex=ex, team=team, role_key="team_writer")
        rid, sid = await _report(c, ah, tid=tid, ex=ex, team=team, assigned_writer_id=None)
        r = await _save(c, ex, rid, sid, wh)
        assert r.status_code == 200
