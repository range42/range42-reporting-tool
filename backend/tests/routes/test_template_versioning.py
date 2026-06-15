import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _h(migrated_db: async_sessionmaker) -> dict[str, str]:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {token}"}


async def _draft_with_section(c, h) -> str:
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=h)).json()["data"]["id"]
    await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={"name": "S1", "field_type": "rich_text", "grade_mode": "not_graded"},
        headers=h,
    )
    return tid


async def test_publish_then_immutable(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        tid = await _draft_with_section(c, h)
        pub = await c.post(f"/api/v1/templates/{tid}/publish", headers=h)
        assert pub.status_code == 200 and pub.json()["data"]["status"] == "published"
        # immutable: patch + section write now 409
        assert (await c.patch(f"/api/v1/templates/{tid}", json={"name": "Y"}, headers=h)).status_code == 409
        assert (
            await c.post(f"/api/v1/templates/{tid}/sections", json={"name": "S2", "field_type": "rich_text"}, headers=h)
        ).status_code == 409


async def test_publish_requires_sections(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        r = await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=h)
        tid = r.json()["data"]["id"]
        assert (await c.post(f"/api/v1/templates/{tid}/publish", headers=h)).status_code == 409


async def test_clone_makes_next_version_in_lineage(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        tid = await _draft_with_section(c, h)
        await c.post(f"/api/v1/templates/{tid}/publish", headers=h)
        cloned = await c.post(f"/api/v1/templates/{tid}/clone", headers=h)
        assert cloned.status_code == 201
        cj = cloned.json()["data"]
        assert cj["version"] == 2 and cj["status"] == "draft" and len(cj["sections"]) == 1
        versions = (await c.get(f"/api/v1/templates/{tid}/versions", headers=h)).json()["data"]
        assert [v["version"] for v in versions] == [2, 1]


async def test_archive_only_published(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        tid = await _draft_with_section(c, h)
        assert (await c.post(f"/api/v1/templates/{tid}/archive", headers=h)).status_code == 409
        await c.post(f"/api/v1/templates/{tid}/publish", headers=h)
        assert (await c.post(f"/api/v1/templates/{tid}/archive", headers=h)).status_code == 200
