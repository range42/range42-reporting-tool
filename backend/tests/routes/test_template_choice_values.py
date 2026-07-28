"""WP3 S4 (#79) — per-value deprecate/delete endpoints + choice-code immutability.

Published templates are frozen by policy (all section edits are draft-only), but
deprecating a choice value must remain possible without breaking reports that
already reference its code. Deleting a value is allowed only while nothing
references it (409 otherwise); a DB trigger backstops the invariant against
non-route writes.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog, TemplateSectionDef
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration

CFG = {
    "selection": "multiple",
    "values": [
        {"code": "a", "label": "A", "position": 0, "deprecated_at": None},
        {"code": "b", "label": "B", "position": 1, "deprecated_at": None},
        {"code": "c", "label": "C", "position": 2, "deprecated_at": None},
    ],
}


async def _ga(migrated_db):
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def _published_choice_template(c, ah):
    """A published template with one choice section (codes a/b/c); returns (tid, sid)."""
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
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    return tid, sid


async def _report_answering(c, ah, tid, codes):
    """A report on ``tid`` whose choice section answers ``codes``; returns (ex, rid, section_id)."""
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
    team = (await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)).json()[
        "data"
    ]["id"]
    detail = (
        await c.post(
            f"/api/v1/exercises/{ex}/reports",
            json={"template_id": tid, "team_id": team, "name": "R"},
            headers=ah,
        )
    ).json()["data"]
    rid, sid = detail["id"], detail["sections"][0]["id"]
    r = await c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "choice", "choice_values": codes}},
        headers=ah,
    )
    assert r.status_code == 200, r.text
    return ex, rid, sid


# --- deprecate ---------------------------------------------------------------


async def test_deprecate_on_published_sets_deprecated_at_and_audits(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _published_choice_template(c, ah)
        r = await c.post(f"/api/v1/templates/{tid}/sections/{sid}/choice-values/b/deprecate", headers=ah)
        assert r.status_code == 200, r.text
        values = {v["code"]: v for v in r.json()["data"]["choice_config"]["values"]}
        assert values["b"]["deprecated_at"] is not None
        assert values["a"]["deprecated_at"] is None
    async with migrated_db() as s:
        actions = set((await s.execute(select(AuditLog.action))).scalars().all())
    assert "template_section.choice_value.deprecate" in actions


async def test_deprecate_unknown_code_404(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _published_choice_template(c, ah)
        r = await c.post(f"/api/v1/templates/{tid}/sections/{sid}/choice-values/nope/deprecate", headers=ah)
        assert r.status_code == 404


async def test_deprecate_twice_409(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _published_choice_template(c, ah)
        await c.post(f"/api/v1/templates/{tid}/sections/{sid}/choice-values/b/deprecate", headers=ah)
        r = await c.post(f"/api/v1/templates/{tid}/sections/{sid}/choice-values/b/deprecate", headers=ah)
        assert r.status_code == 409


async def test_deprecate_non_choice_section_422(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
            "id"
        ]
        sid = (
            await c.post(f"/api/v1/templates/{tid}/sections", json={"name": "S", "field_type": "rich_text"}, headers=ah)
        ).json()["data"]["id"]
        r = await c.post(f"/api/v1/templates/{tid}/sections/{sid}/choice-values/a/deprecate", headers=ah)
        assert r.status_code == 422


async def test_deprecated_code_blocks_new_saves_keeps_existing_answers(migrated_db: async_sessionmaker) -> None:
    """Round-trip: deprecation hides the code from new saves but existing answers survive."""
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, tsid = await _published_choice_template(c, ah)
        ex, rid, rsid = await _report_answering(c, ah, tid, ["b"])
        await c.post(f"/api/v1/templates/{tid}/sections/{tsid}/choice-values/b/deprecate", headers=ah)
        # new save with the deprecated code is rejected
        r = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{rsid}",
            json={"version": 2, "body": {"kind": "choice", "choice_values": ["b"]}},
            headers=ah,
        )
        assert r.status_code == 422
        # the stored answer is untouched
        detail = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)).json()["data"]
        assert detail["sections"][0]["choice_values"] == ["b"]


# --- delete ------------------------------------------------------------------


async def test_delete_unreferenced_value_removes_and_renormalizes(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _published_choice_template(c, ah)
        r = await c.delete(f"/api/v1/templates/{tid}/sections/{sid}/choice-values/b", headers=ah)
        assert r.status_code == 200, r.text
        values = r.json()["data"]["choice_config"]["values"]
        assert [v["code"] for v in values] == ["a", "c"]
        assert [v["position"] for v in values] == [0, 1]
    async with migrated_db() as s:
        actions = set((await s.execute(select(AuditLog.action))).scalars().all())
    assert "template_section.choice_value.delete" in actions


async def test_delete_referenced_value_409(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _published_choice_template(c, ah)
        await _report_answering(c, ah, tid, ["b"])
        r = await c.delete(f"/api/v1/templates/{tid}/sections/{sid}/choice-values/b", headers=ah)
        assert r.status_code == 409
        # value is still there
        detail = (await c.get(f"/api/v1/templates/{tid}", headers=ah)).json()["data"]
        codes = [v["code"] for v in detail["sections"][0]["choice_config"]["values"]]
        assert "b" in codes


async def test_delete_unknown_code_404(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _published_choice_template(c, ah)
        r = await c.delete(f"/api/v1/templates/{tid}/sections/{sid}/choice-values/nope", headers=ah)
        assert r.status_code == 404


# --- DB trigger backstop ------------------------------------------------------


async def test_trigger_blocks_removing_referenced_code(migrated_db: async_sessionmaker) -> None:
    """Defense in depth: a direct DB write dropping a referenced code must fail."""
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _published_choice_template(c, ah)
        await _report_answering(c, ah, tid, ["b"])
    stripped = {**CFG, "values": [v for v in CFG["values"] if v["code"] != "b"]}
    async with migrated_db() as s:
        d = (await s.execute(select(TemplateSectionDef).where(TemplateSectionDef.id == sid))).scalar_one()
        d.choice_config = stripped
        with pytest.raises(DBAPIError):
            await s.commit()


async def test_trigger_allows_deprecation_and_unreferenced_removal(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        tid, sid = await _published_choice_template(c, ah)
        await _report_answering(c, ah, tid, ["b"])
    new_cfg = {
        "selection": "multiple",
        "values": [
            {"code": "a", "label": "A", "position": 0, "deprecated_at": None},
            {"code": "b", "label": "B", "position": 1, "deprecated_at": "2026-07-21T00:00:00+00:00"},
            # "c" removed — unreferenced, so the trigger lets it through
        ],
    }
    async with migrated_db() as s:
        d = (await s.execute(select(TemplateSectionDef).where(TemplateSectionDef.id == sid))).scalar_one()
        d.choice_config = new_cfg
        await s.commit()
    async with migrated_db() as s:
        d = (await s.execute(select(TemplateSectionDef).where(TemplateSectionDef.id == sid))).scalar_one()
        assert [v["code"] for v in d.choice_config["values"]] == ["a", "b"]
