"""Regression: list /api/v1/exercises respects membership-based visibility for non-admin users."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_exercise_visibility_filter(migrated_db: async_sessionmaker) -> None:
    # Seed system roles (needed for exercise_role assignment)
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()

    # Create distinct users with unique jtis
    admin_token, _ = await make_user_token(migrated_db, jti="vis-admin", admin=True)
    no_member_token, no_member_id = await make_user_token(migrated_db, jti="vis-nomember", admin=False)
    member_token, member_id = await make_user_token(migrated_db, jti="vis-member", admin=False)
    role_only_token, role_only_id = await make_user_token(migrated_db, jti="vis-roleonly", admin=False)

    ah = {"Authorization": f"Bearer {admin_token}"}

    async with client(migrated_db) as c:
        # Admin creates an exercise and a team
        ex = (await c.post("/api/v1/exercises", json={"name": "Visibility-Test"}, headers=ah)).json()["data"]["id"]
        tid = (
            await c.post(
                f"/api/v1/exercises/{ex}/teams",
                json={"name": "Blue Team", "team_type": "blue"},
                headers=ah,
            )
        ).json()["data"]["id"]

        # --- Step 1: non-member sees nothing ---
        r_none = await c.get("/api/v1/exercises", headers={"Authorization": f"Bearer {no_member_token}"})
        assert r_none.status_code == 200
        body_none = r_none.json()
        assert body_none["meta"]["total"] == 0, f"Non-member should see 0 exercises, got {body_none['meta']['total']}"
        assert body_none["data"] == []

        # --- Step 2: add member to team → sees exercise ---
        await c.post(
            f"/api/v1/exercises/{ex}/teams/{tid}/members",
            json={"user_id": member_id},
            headers=ah,
        )
        r_member = await c.get("/api/v1/exercises", headers={"Authorization": f"Bearer {member_token}"})
        assert r_member.status_code == 200
        body_member = r_member.json()
        assert body_member["meta"]["total"] == 1, (
            f"Team member should see 1 exercise, got {body_member['meta']['total']}"
        )
        assert body_member["data"][0]["id"] == ex

        # --- Step 3: user with only exercise_role (no team membership) → sees exercise ---
        await c.post(
            f"/api/v1/exercises/{ex}/roles",
            json={"user_id": role_only_id, "role_key": "team_writer"},
            headers=ah,
        )
        r_role = await c.get("/api/v1/exercises", headers={"Authorization": f"Bearer {role_only_token}"})
        assert r_role.status_code == 200
        body_role = r_role.json()
        assert body_role["meta"]["total"] == 1, (
            f"Role-only user should see 1 exercise, got {body_role['meta']['total']}"
        )

        # --- Step 4: admin sees at least EX ---
        r_admin = await c.get("/api/v1/exercises", headers=ah)
        assert r_admin.status_code == 200
        assert r_admin.json()["meta"]["total"] >= 1
        ids = [e["id"] for e in r_admin.json()["data"]]
        assert ex in ids, "Admin should see the exercise in the list"
