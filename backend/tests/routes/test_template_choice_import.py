"""WP3 S12 (#82) — CSV import of choice values (G-4 resolution).

CSV is the only v1 path for populating a choice field from a catalog:
``choice_config.catalog_binding`` stays opaque metadata — preserved, never
interpreted. Import merges: new codes are appended in file order, existing
codes keep their position and ``deprecated_at`` and only refresh their label.
Nothing is ever removed, so the S4 immutability rules hold even on published
templates with referenced codes.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration

BINDING = {"source": "service_catalog", "ref": "core-services"}  # opaque in v1 (G-4)

CFG = {
    "selection": "multiple",
    "catalog_binding": BINDING,
    "values": [
        {"code": "a", "label": "A", "position": 0, "deprecated_at": None},
        {"code": "b", "label": "B", "position": 1, "deprecated_at": "2026-07-01T00:00:00+00:00"},
    ],
}

CSV_OK = b"code,label\nb,Bravo (renamed)\nc,Charlie\nd,Delta\n"


async def _ga(migrated_db):
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def _choice_template(c, ah, *, publish=False):
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    sid = (
        await c.post(
            f"/api/v1/templates/{tid}/sections",
            json={"name": "S", "field_type": "choice", "choice_config": CFG},
            headers=ah,
        )
    ).json()["data"]["id"]
    if publish:
        await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    return tid, sid


def _import_url(tid, sid):
    return f"/api/v1/templates/{tid}/sections/{sid}/choice-values/import"


async def _upload_csv(c, ah, tid, sid, data=CSV_OK):
    return await c.post(_import_url(tid, sid), files={"file": ("values.csv", data, "text/csv")}, headers=ah)


async def test_csv_roundtrip_merges_values(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _choice_template(c, ah)
        r = await _upload_csv(c, ah, tid, sid)
        assert r.status_code == 200, r.text
        values = r.json()["data"]["choice_config"]["values"]
        by_code = {v["code"]: v for v in values}

        # existing codes: position kept, label refreshed, deprecation untouched
        assert [v["code"] for v in values] == ["a", "b", "c", "d"]
        assert by_code["a"]["label"] == "A"  # not in CSV — untouched
        assert by_code["b"]["label"] == "Bravo (renamed)"
        assert by_code["b"]["deprecated_at"] is not None  # import never un-deprecates
        # new codes appended in file order with normalized positions
        assert by_code["c"]["label"] == "Charlie"
        assert [v["position"] for v in values] == [0, 1, 2, 3]


async def test_catalog_binding_preserved_but_inert(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _choice_template(c, ah)
        r = await _upload_csv(c, ah, tid, sid)
        cfg = r.json()["data"]["choice_config"]
        assert cfg["catalog_binding"] == BINDING
        assert cfg["selection"] == "multiple"


@pytest.mark.parametrize(
    "data",
    [
        b"name,value\nx,y\n",  # wrong header
        b"code,label\n",  # no data rows
        b"code,label\na,X\na,Y\n",  # duplicate codes
        b"\xff\xfe\x00bad",  # not UTF-8
    ],
)
async def test_malformed_csv_rejected_422(migrated_db: async_sessionmaker, data: bytes) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _choice_template(c, ah)
        r = await _upload_csv(c, ah, tid, sid, data=data)
        assert r.status_code == 422, r.text


async def test_rich_text_section_rejected_422(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
            "id"
        ]
        sid = (
            await c.post(f"/api/v1/templates/{tid}/sections", json={"name": "S", "field_type": "rich_text"}, headers=ah)
        ).json()["data"]["id"]
        r = await _upload_csv(c, ah, tid, sid)
        assert r.status_code == 422


async def test_non_admin_rejected_403(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _choice_template(c, ah)
        tok, _ = await make_user_token(migrated_db, jti="pleb")
        r = await _upload_csv(c, {"Authorization": f"Bearer {tok}"}, tid, sid)
        assert r.status_code == 403


async def test_import_on_published_template_with_referenced_codes(migrated_db: async_sessionmaker) -> None:
    """Additive import must survive the S4 immutability trigger on a published, answered template."""
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _choice_template(c, ah, publish=True)
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        team = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        detail = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports", json={"template_id": tid, "team_id": team, "name": "R"}, headers=ah
            )
        ).json()["data"]
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{detail['id']}/sections/{detail['sections'][0]['id']}",
            json={"version": 1, "body": {"kind": "choice", "choice_values": ["a"]}},
            headers=ah,
        )
        r = await _upload_csv(c, ah, tid, sid)
        assert r.status_code == 200, r.text
        assert "a" in {v["code"] for v in r.json()["data"]["choice_config"]["values"]}


async def test_import_writes_audit_row_with_counts(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _choice_template(c, ah)
        await _upload_csv(c, ah, tid, sid)
    async with migrated_db() as s:
        row = (
            await s.execute(select(AuditLog).where(AuditLog.action == "template_section.choice_value.import"))
        ).scalar_one()
    assert row.details["added"] == 2
    assert row.details["updated"] == 1
