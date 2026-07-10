import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_choice_positions_renormalized_on_create(migrated_db: async_sessionmaker) -> None:
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {tok}"}
    async with client(migrated_db) as c:
        tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
            "id"
        ]
        cfg = {
            "selection": "single",
            "values": [
                {"code": "a", "label": "A", "position": 5, "deprecated_at": None},
                {"code": "b", "label": "B", "position": 9, "deprecated_at": None},
            ],
        }
        sec = (
            await c.post(
                f"/api/v1/templates/{tid}/sections",
                json={"name": "S", "field_type": "choice", "choice_config": cfg},
                headers=ah,
            )
        ).json()["data"]
        positions = [v["position"] for v in sec["choice_config"]["values"]]
        assert positions == [0, 1]


async def test_choice_positions_renormalized_on_update(migrated_db: async_sessionmaker) -> None:
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {tok}"}
    async with client(migrated_db) as c:
        tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
            "id"
        ]
        cfg = {
            "selection": "single",
            "values": [
                {"code": "a", "label": "A", "position": 0, "deprecated_at": None},
                {"code": "b", "label": "B", "position": 1, "deprecated_at": None},
            ],
        }
        sid = (
            await c.post(
                f"/api/v1/templates/{tid}/sections",
                json={"name": "S", "field_type": "choice", "choice_config": cfg},
                headers=ah,
            )
        ).json()["data"]["id"]
        # PATCH with reversed/sparse positions -> dense 0..n-1 by given position then order
        reordered = {
            "selection": "single",
            "values": [
                {"code": "a", "label": "A", "position": 7, "deprecated_at": None},
                {"code": "b", "label": "B", "position": 2, "deprecated_at": None},
            ],
        }
        sec = (
            await c.patch(
                f"/api/v1/templates/{tid}/sections/{sid}",
                json={"choice_config": reordered},
                headers=ah,
            )
        ).json()["data"]
        values = sec["choice_config"]["values"]
        by_code = {v["code"]: v["position"] for v in values}
        assert by_code == {"b": 0, "a": 1}
