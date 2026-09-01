"""Arrange helpers shared by the W5-1 evaluation route tests (Tasks 5-11)."""

from app.seed import seed_system_roles
from tests.routes._helpers import make_user_token


async def ga_headers(migrated_db, *, jti: str = "ga"):
    """Seed the system roles and return (Global-Admin auth headers, user_id)."""
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, uid = await make_user_token(migrated_db, jti=jti, admin=True)
    return {"Authorization": f"Bearer {tok}"}, uid


async def submitted_report(c, ah):
    """Template (one required, numeric-graded section) -> exercise -> team -> report -> submitted.

    Returns (exercise_id, report_id, section_id). grade_mode is 'numeric' so
    gradable_section_count is 1 — Tasks 6-8 grade this section.
    """
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={
            "name": "S",
            "field_type": "rich_text",
            "is_required": True,
            "grade_mode": "numeric",
            "grade_min": 0,
            "grade_max": 10,
        },
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
    r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    assert r.json()["data"]["status"] == "submitted", r.text
    return ex, rid, sid


async def role_holder(migrated_db, c, ah, exercise_id, jti, role_key):
    """Create a user, grant them ``role_key`` in the exercise. Returns (headers, user_id)."""
    tok, uid = await make_user_token(migrated_db, jti=jti)
    r = await c.post(
        f"/api/v1/exercises/{exercise_id}/roles",
        json={"user_id": uid, "role_key": role_key},
        headers=ah,
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {tok}"}, uid


async def evaluator(migrated_db, c, ah, exercise_id, jti):
    """Create a user and grant them the 'evaluator' system role in the exercise."""
    return await role_holder(migrated_db, c, ah, exercise_id, jti, "evaluator")


async def assign(c, ah, ex, rid, uid, **body):
    """POST an assignment; return the created evaluation's id."""
    r = await c.post(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations",
        json={"evaluator_id": uid, **body},
        headers=ah,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]
