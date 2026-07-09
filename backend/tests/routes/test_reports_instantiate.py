import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _published_template(c, ah) -> str:
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={"name": "Summary", "field_type": "rich_text", "is_required": True},
        headers=ah,
    )
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    return tid


async def _exercise_team(c, ah) -> tuple[str, str]:
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
    team = (
        await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Alpha", "team_type": "blue"}, headers=ah)
    ).json()["data"]["id"]
    return ex, team


async def test_instantiate_snapshots_sections(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        tid = await _published_template(c, ah)
        ex, team = await _exercise_team(c, ah)
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports", json={"template_id": tid, "team_id": team, "name": "R1"}, headers=ah
        )
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        assert data["status"] == "draft"
        assert data["template_version_at_creation"] == 1
        assert len(data["sections"]) == 1
        assert data["sections"][0]["field_type"] == "rich_text"
        assert data["sections"][0]["version"] == 1


async def test_instantiate_rejects_unpublished(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
            "id"
        ]  # draft, not published
        ex, team = await _exercise_team(c, ah)
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports", json={"template_id": tid, "team_id": team, "name": "R1"}, headers=ah
        )
        assert r.status_code == 409


async def test_instantiate_team_must_belong_to_exercise(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        tid = await _published_template(c, ah)
        ex1, _ = await _exercise_team(c, ah)
        _, team2 = await _exercise_team(c, ah)  # team in a different exercise
        r = await c.post(
            f"/api/v1/exercises/{ex1}/reports", json={"template_id": tid, "team_id": team2, "name": "R1"}, headers=ah
        )
        assert r.status_code == 422
