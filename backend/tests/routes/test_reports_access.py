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


async def test_writer_sees_only_own_team(migrated_db: async_sessionmaker) -> None:
    await _seed(migrated_db)
    ga, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {ga}"}
    writer_tok, writer_id = await make_user_token(migrated_db, jti="w", admin=False)
    async with client(migrated_db) as c:
        tid = await _published_template(c, ah)
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        t_alpha = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Alpha", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        t_beta = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Beta", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        await c.post(f"/api/v1/exercises/{ex}/teams/{t_alpha}/members", json={"user_id": writer_id}, headers=ah)
        await c.post(
            f"/api/v1/exercises/{ex}/roles", json={"user_id": writer_id, "role_key": "team_writer"}, headers=ah
        )
        await c.post(
            f"/api/v1/exercises/{ex}/reports",
            json={"template_id": tid, "team_id": t_alpha, "name": "Mine"},
            headers=ah,
        )
        await c.post(
            f"/api/v1/exercises/{ex}/reports",
            json={"template_id": tid, "team_id": t_beta, "name": "Theirs"},
            headers=ah,
        )

        wh = {"Authorization": f"Bearer {writer_tok}"}
        listed = (await c.get(f"/api/v1/exercises/{ex}/reports", headers=wh)).json()
        names = {row["name"] for row in listed["data"]}
        assert names == {"Mine"}


async def test_widened_status_filter_does_not_bypass_team_scoping(migrated_db: async_sessionmaker) -> None:
    # W5-1 Task 3 widened KNOWN_REPORT_STATUSES; the new values are AND-ed with the team
    # filter, so a writer cannot reach another team's report by filtering on one.
    await _seed(migrated_db)
    ga, _ = await make_user_token(migrated_db, jti="ga2", admin=True)
    ah = {"Authorization": f"Bearer {ga}"}
    writer_tok, writer_id = await make_user_token(migrated_db, jti="w2", admin=False)
    async with client(migrated_db) as c:
        tid = await _published_template(c, ah)
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        mine = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Alpha", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        theirs = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Beta", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        await c.post(f"/api/v1/exercises/{ex}/teams/{mine}/members", json={"user_id": writer_id}, headers=ah)
        await c.post(
            f"/api/v1/exercises/{ex}/roles", json={"user_id": writer_id, "role_key": "team_writer"}, headers=ah
        )
        await c.post(
            f"/api/v1/exercises/{ex}/reports",
            json={"template_id": tid, "team_id": theirs, "name": "Theirs"},
            headers=ah,
        )

        wh = {"Authorization": f"Bearer {writer_tok}"}
        for st in ("under_evaluation", "evaluated"):
            r = await c.get(f"/api/v1/exercises/{ex}/reports", params={"status": st}, headers=wh)
            assert r.status_code == 200, st
            assert r.json()["data"] == [], st
        # and the new values are accepted rather than 422'd
        assert (
            await c.get(f"/api/v1/exercises/{ex}/reports", params={"status": "nonsense"}, headers=wh)
        ).status_code == 422


async def test_detail_omits_evaluator_fields(migrated_db: async_sessionmaker) -> None:
    await _seed(migrated_db)
    ga, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {ga}"}
    async with client(migrated_db) as c:
        tid = await _published_template(c, ah)
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        team = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Alpha", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        rid = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports",
                json={"template_id": tid, "team_id": team, "name": "R"},
                headers=ah,
            )
        ).json()["data"]["id"]
        detail = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)).json()["data"]
        sec = detail["sections"][0]
        for leaked in (
            "evaluation_criteria",
            "grade_mode",
            "grade_min",
            "grade_max",
            "grade_weight",
            "rubric_criteria",
        ):
            assert leaked not in sec
