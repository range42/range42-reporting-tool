import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.permissions import PERMISSION_CATALOGUE
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_permissions_catalogue_returned_sorted(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    async with client(migrated_db) as c:
        r = await c.get("/api/v1/permissions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data == sorted(PERMISSION_CATALOGUE)
    assert len(data) == len(PERMISSION_CATALOGUE)


async def test_permissions_requires_global_admin(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="u", admin=False)
    async with client(migrated_db) as c:
        r = await c.get("/api/v1/permissions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


async def test_permissions_requires_auth(migrated_db: async_sessionmaker) -> None:
    async with client(migrated_db) as c:
        r = await c.get("/api/v1/permissions")
    assert r.status_code == 401
