"""
Route-level 422 validation tests.

Ensures that explicit-null on required PATCH fields returns 422 (not 500),
and that nullable fields continue to accept null.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _create_exercise(c, token: str, name: str = "ValidationTestEx") -> str:
    r = await c.post("/api/v1/exercises", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


async def test_patch_exercise_explicit_null_name_returns_422(migrated_db: async_sessionmaker) -> None:
    """PATCH /exercises/{id} with {"name": null} must return 422, not 500."""
    token, _ = await make_user_token(migrated_db, jti="val1", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex_id = await _create_exercise(c, token)
        r = await c.patch(f"/api/v1/exercises/{ex_id}", json={"name": None}, headers=h)
    assert r.status_code == 422, f"expected 422 but got {r.status_code}: {r.text}"


async def test_patch_exercise_explicit_null_description_returns_200(migrated_db: async_sessionmaker) -> None:
    """PATCH /exercises/{id} with {"description": null} must return 200 (nullable column)."""
    token, _ = await make_user_token(migrated_db, jti="val2", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex_id = await _create_exercise(c, token)
        r = await c.patch(f"/api/v1/exercises/{ex_id}", json={"description": None}, headers=h)
    assert r.status_code == 200, f"expected 200 but got {r.status_code}: {r.text}"
    assert r.json()["data"]["description"] is None
