import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _ga(migrated_db):
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def test_search_matches_display_name_or_email(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    await make_user_token(migrated_db, jti="alice", admin=False, display_name="Alice Admin", email="alice@x.com")
    await make_user_token(migrated_db, jti="bob", admin=False, display_name="Bob Builder", email="bob@x.com")
    async with client(migrated_db) as c:
        by_name = (await c.get("/api/v1/users?q=Alice", headers=ah)).json()["data"]
        assert {u["display_name"] for u in by_name} == {"Alice Admin"}

        by_email = (await c.get("/api/v1/users?q=bob@x.com", headers=ah)).json()["data"]
        assert {u["display_name"] for u in by_email} == {"Bob Builder"}


async def test_search_is_case_insensitive_and_paginated(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    for i in range(3):
        await make_user_token(
            migrated_db, jti=f"member{i}", admin=False, display_name=f"Member {i}", email=f"member{i}@x.com"
        )
    async with client(migrated_db) as c:
        r = await c.get("/api/v1/users?q=MEMBER&per_page=2", headers=ah)
        body = r.json()
        assert len(body["data"]) == 2
        assert body["meta"]["total"] == 3


async def test_search_without_q_returns_no_results(migrated_db: async_sessionmaker) -> None:
    # No open user directory browse — q is required to return anything.
    ah = await _ga(migrated_db)
    await make_user_token(migrated_db, jti="alice", admin=False, display_name="Alice", email="alice@x.com")
    async with client(migrated_db) as c:
        r = await c.get("/api/v1/users", headers=ah)
        assert r.status_code == 200
        assert r.json()["data"] == []


async def test_search_forbidden_for_non_admin(migrated_db: async_sessionmaker) -> None:
    tok, _ = await make_user_token(migrated_db, jti="rando", admin=False)
    async with client(migrated_db) as c:
        r = await c.get("/api/v1/users?q=a", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403
