"""Regression: non-admin token must receive 403 on every mutating endpoint guarded by require_global_admin."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helpers to set up a real exercise/team/member so path look-ups are valid.
# require_global_admin fires *before* any body/path resolution, so 403 is
# expected even with legitimately existing IDs.
# ---------------------------------------------------------------------------

_FAKE_UUID = str(uuid.uuid4())


async def _setup(migrated_db: async_sessionmaker) -> tuple[str, str, str, str, str, str, str]:
    """Seed roles, create admin + non-admin users, exercise, team, and member.

    Returns (non_admin_token, non_admin_id, admin_token, ex_id, team_type_id, tid, assignment_id).
    """
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()

    admin_token, admin_id = await make_user_token(migrated_db, jti="rbac-admin", admin=True)
    non_admin_token, non_admin_id = await make_user_token(migrated_db, jti="rbac-user", admin=False)
    ah = {"Authorization": f"Bearer {admin_token}"}

    async with client(migrated_db) as c:
        ex_id = (await c.post("/api/v1/exercises", json={"name": "RBAC-Test"}, headers=ah)).json()["data"]["id"]

        # Grab a seeded team-type id for use in path parameters
        types = (await c.get(f"/api/v1/exercises/{ex_id}/team-types", headers=ah)).json()["data"]
        team_type_id = types[0]["id"]

        # Create a team and add the non-admin as a member
        tid = (
            await c.post(
                f"/api/v1/exercises/{ex_id}/teams",
                json={"name": "Alpha", "team_type": "blue"},
                headers=ah,
            )
        ).json()["data"]["id"]
        await c.post(
            f"/api/v1/exercises/{ex_id}/teams/{tid}/members",
            json={"user_id": non_admin_id},
            headers=ah,
        )

        # Assign a role so we have a real assignment_id
        role_resp = await c.post(
            f"/api/v1/exercises/{ex_id}/roles",
            json={"user_id": non_admin_id, "role_key": "team_writer"},
            headers=ah,
        )
        assignment_id = role_resp.json()["data"]["id"]

    return non_admin_token, non_admin_id, admin_token, ex_id, team_type_id, tid, assignment_id


@pytest.mark.parametrize(
    "method,path_tpl,body",
    [
        ("POST", "/api/v1/exercises", {"name": "x"}),
        ("PATCH", "/api/v1/exercises/{ex}", {"name": "x"}),
        ("DELETE", "/api/v1/exercises/{ex}", None),
        ("POST", "/api/v1/exercises/{ex}/team-types", {"type_key": "gold", "display_label": "Gold"}),
        ("PATCH", "/api/v1/exercises/{ex}/team-types/{type_id}", {"display_label": "x"}),
        ("DELETE", "/api/v1/exercises/{ex}/team-types/{type_id}", None),
        ("POST", "/api/v1/exercises/{ex}/teams", {"name": "Beta", "team_type": "blue"}),
        ("PATCH", "/api/v1/exercises/{ex}/teams/{tid}", {"name": "x"}),
        ("DELETE", "/api/v1/exercises/{ex}/teams/{tid}", None),
        ("POST", "/api/v1/exercises/{ex}/teams/{tid}/members", {"user_id": _FAKE_UUID}),
        ("DELETE", "/api/v1/exercises/{ex}/teams/{tid}/members/{member_id}", None),
        ("POST", "/api/v1/exercises/{ex}/roles", {"user_id": _FAKE_UUID, "role_key": "team_writer"}),
        ("DELETE", "/api/v1/exercises/{ex}/roles/{assignment_id}", None),
        ("POST", "/api/v1/roles", {"role_key": "x", "display_label": "X", "permissions": []}),
        ("PATCH", "/api/v1/roles/{role_id}", {"display_label": "x"}),
        ("DELETE", "/api/v1/roles/{role_id}", None),
    ],
)
async def test_non_admin_gets_403(
    migrated_db: async_sessionmaker,
    method: str,
    path_tpl: str,
    body: dict | None,
) -> None:
    (
        non_admin_token,
        non_admin_id,
        _admin_token,
        ex_id,
        team_type_id,
        tid,
        assignment_id,
    ) = await _setup(migrated_db)

    # Build a placeholder role_id (not a real custom role, but 403 fires before the DB look-up)
    role_id = str(uuid.uuid4())

    path = path_tpl.format(
        ex=ex_id,
        type_id=team_type_id,
        tid=tid,
        member_id=non_admin_id,
        assignment_id=assignment_id,
        role_id=role_id,
    )

    h = {"Authorization": f"Bearer {non_admin_token}"}

    async with client(migrated_db) as c:
        send = getattr(c, method.lower())
        if body is not None:
            r = await send(path, json=body, headers=h)
        else:
            r = await send(path, headers=h)

    assert r.status_code == 403, f"{method} {path} returned {r.status_code}, expected 403 for non-admin token"
