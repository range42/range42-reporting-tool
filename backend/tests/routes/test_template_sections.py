import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _h(migrated_db: async_sessionmaker) -> dict[str, str]:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {token}"}


async def _tid(c, h) -> str:
    return (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=h)).json()["data"][
        "id"
    ]


async def test_section_crud_and_reorder(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        tid = await _tid(c, h)
        a = (
            await c.post(
                f"/api/v1/templates/{tid}/sections",
                json={"name": "A", "field_type": "rich_text", "char_limit": 500},
                headers=h,
            )
        ).json()["data"]
        b = (
            await c.post(
                f"/api/v1/templates/{tid}/sections",
                json={
                    "name": "B",
                    "field_type": "choice",
                    "choice_config": {
                        "selection": "single",
                        "values": [{"code": "x", "label": "X", "position": 0, "deprecated_at": None}],
                    },
                },
                headers=h,
            )
        ).json()["data"]
        assert a["position"] == 0 and b["position"] == 1

        # reorder B before A
        ro = await c.post(
            f"/api/v1/templates/{tid}/sections/reorder",
            json={"ordered_ids": [b["id"], a["id"]]},
            headers=h,
        )
        assert ro.status_code == 200
        positions = {s["id"]: s["position"] for s in ro.json()["data"]}
        assert positions[b["id"]] == 0 and positions[a["id"]] == 1

        # patch A name
        pa = await c.patch(f"/api/v1/templates/{tid}/sections/{a['id']}", json={"name": "A2"}, headers=h)
        assert pa.status_code == 200 and pa.json()["data"]["name"] == "A2"

        # delete B, A reindexes to 0
        assert (await c.delete(f"/api/v1/templates/{tid}/sections/{b['id']}", headers=h)).status_code == 204
        sections = (await c.get(f"/api/v1/templates/{tid}", headers=h)).json()["data"]["sections"]
        assert len(sections) == 1 and sections[0]["position"] == 0


async def test_invalid_section_422(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        tid = await _tid(c, h)
        r = await c.post(
            f"/api/v1/templates/{tid}/sections",
            json={
                "name": "N",
                "field_type": "rich_text",
                "grade_mode": "numeric",
                "grade_min": 5,
                "grade_max": 1,
            },
            headers=h,
        )
    assert r.status_code == 422


async def test_reorder_mismatch_422(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        tid = await _tid(c, h)
        a = (
            await c.post(
                f"/api/v1/templates/{tid}/sections",
                json={"name": "A", "field_type": "rich_text"},
                headers=h,
            )
        ).json()["data"]
        r = await c.post(
            f"/api/v1/templates/{tid}/sections/reorder",
            json={"ordered_ids": [a["id"], "00000000-0000-0000-0000-000000000000"]},
            headers=h,
        )
    assert r.status_code == 422


async def test_section_ops_blocked_on_published_template(migrated_db: async_sessionmaker) -> None:
    """Sections are draft-only: once published, create/patch/delete/reorder return 409."""
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        tid = await _tid(c, h)
        s = (
            await c.post(
                f"/api/v1/templates/{tid}/sections",
                json={"name": "A", "field_type": "rich_text"},
                headers=h,
            )
        ).json()["data"]
        assert (await c.post(f"/api/v1/templates/{tid}/publish", headers=h)).status_code == 200

        assert (
            await c.post(
                f"/api/v1/templates/{tid}/sections",
                json={"name": "B", "field_type": "rich_text"},
                headers=h,
            )
        ).status_code == 409
        assert (
            await c.patch(f"/api/v1/templates/{tid}/sections/{s['id']}", json={"name": "X"}, headers=h)
        ).status_code == 409
        assert (
            await c.post(
                f"/api/v1/templates/{tid}/sections/reorder",
                json={"ordered_ids": [s["id"]]},
                headers=h,
            )
        ).status_code == 409
        assert (await c.delete(f"/api/v1/templates/{tid}/sections/{s['id']}", headers=h)).status_code == 409


async def test_section_404_for_unknown_id(migrated_db: async_sessionmaker) -> None:
    h = await _h(migrated_db)
    async with client(migrated_db) as c:
        tid = await _tid(c, h)
        missing = "00000000-0000-0000-0000-000000000000"
        assert (
            await c.patch(f"/api/v1/templates/{tid}/sections/{missing}", json={"name": "X"}, headers=h)
        ).status_code == 404
        assert (await c.delete(f"/api/v1/templates/{tid}/sections/{missing}", headers=h)).status_code == 404
