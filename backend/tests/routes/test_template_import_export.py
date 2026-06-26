import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _h(migrated_db: async_sessionmaker) -> dict[str, str]:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {token}"}


async def test_export_then_import_roundtrip(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        tid = (await c.post("/api/v1/templates", json={"name": "Spot", "report_type": "spot"}, headers=h)).json()[
            "data"
        ]["id"]
        await c.post(
            f"/api/v1/templates/{tid}/sections",
            json={
                "name": "Svc",
                "field_type": "choice",
                "choice_config": {
                    "selection": "single",
                    "values": [{"code": "p", "label": "Portal", "position": 0, "deprecated_at": None}],
                },
            },
            headers=h,
        )
        bundle = (await c.get(f"/api/v1/templates/{tid}/export", headers=h)).json()["data"]
        assert bundle["schema_version"] == 1 and len(bundle["sections"]) == 1
        assert "id" not in bundle

        imported = await c.post("/api/v1/templates/import", json=bundle, headers=h)
        assert imported.status_code == 201
        ij = imported.json()["data"]
        assert ij["version"] == 1 and ij["status"] == "draft" and len(ij["sections"]) == 1
        assert ij["lineage_id"] != tid  # new lineage


async def test_import_bad_schema_version_422(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        r = await c.post(
            "/api/v1/templates/import",
            json={"schema_version": 2, "name": "T", "report_type": "spot", "sections": []},
            headers=h,
        )
    assert r.status_code == 422


async def test_import_invalid_section_422(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        r = await c.post(
            "/api/v1/templates/import",
            json={
                "schema_version": 1,
                "name": "T",
                "report_type": "spot",
                "sections": [{"name": "X", "field_type": "choice", "choice_config": None}],
            },
            headers=h,
        )
    assert r.status_code == 422
