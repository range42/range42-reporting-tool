"""Regression: every endpoint that resolves a resource by ID returns 404 for unknown IDs."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


def _rand() -> str:
    return str(uuid.uuid4())


async def test_not_found_responses(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="nf-admin", admin=True)
    h = {"Authorization": f"Bearer {token}"}

    async with client(migrated_db) as c:
        # Create a real exercise and team to use as anchors for nested paths
        ex = (await c.post("/api/v1/exercises", json={"name": "NF-Test"}, headers=h)).json()["data"]["id"]
        tid = (
            await c.post(
                f"/api/v1/exercises/{ex}/teams",
                json={"name": "Alpha", "team_type": "blue"},
                headers=h,
            )
        ).json()["data"]["id"]

        rand = _rand()

        cases: list[tuple[str, str, dict | None, int]] = [
            # (method, path, json_body, expected_status)
            ("GET", f"/api/v1/exercises/{rand}", None, 404),
            ("PATCH", f"/api/v1/exercises/{rand}", {"name": "x"}, 404),
            ("DELETE", f"/api/v1/exercises/{rand}", None, 404),
            ("GET", f"/api/v1/exercises/{ex}/teams/{rand}", None, 404),
            ("PATCH", f"/api/v1/exercises/{ex}/teams/{rand}", {"name": "x"}, 404),
            ("DELETE", f"/api/v1/exercises/{ex}/teams/{rand}", None, 404),
            ("PATCH", f"/api/v1/exercises/{ex}/team-types/{rand}", {"display_label": "x"}, 404),
            ("DELETE", f"/api/v1/exercises/{ex}/team-types/{rand}", None, 404),
            ("DELETE", f"/api/v1/exercises/{ex}/teams/{tid}/members/{rand}", None, 404),
            ("DELETE", f"/api/v1/exercises/{ex}/roles/{rand}", None, 404),
            ("PATCH", f"/api/v1/roles/{rand}", {"display_label": "x"}, 404),
            ("DELETE", f"/api/v1/roles/{rand}", None, 404),
        ]

        for method, path, body, expected in cases:
            send = getattr(c, method.lower())
            if body is not None:
                r = await send(path, json=body, headers=h)
            else:
                r = await send(path, headers=h)
            assert r.status_code == expected, f"{method} {path} returned {r.status_code}, expected {expected}"
