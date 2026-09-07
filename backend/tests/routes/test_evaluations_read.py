import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import assign, evaluator, ga_headers, role_holder, submitted_report
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


def _list_url(ex, rid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations"


def _detail_url(ex, rid, evid):
    return f"{_list_url(ex, rid)}/{evid}"


async def _two_evaluators(migrated_db, c, ah, ex, rid):
    """Assign ev1 and ev2 to the same report. Returns (h1, evid1, h2, evid2)."""
    h1, uid1 = await evaluator(migrated_db, c, ah, ex, "ev1")
    h2, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
    return h1, await assign(c, ah, ex, rid, uid1), h2, await assign(c, ah, ex, rid, uid2)


async def test_global_admin_lists_all_evaluations_for_a_report(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        await _two_evaluators(migrated_db, c, ah, ex, rid)
        rows = (await c.get(_list_url(ex, rid), headers=ah)).json()["data"]["evaluations"]
        assert len(rows) == 2


async def test_evaluator_list_returns_only_their_own_evaluation(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        h1, evid1, _, _ = await _two_evaluators(migrated_db, c, ah, ex, rid)
        rows = (await c.get(_list_url(ex, rid), headers=h1)).json()["data"]["evaluations"]
        assert [r["id"] for r in rows] == [evid1]


async def test_evaluator_list_omits_peer_evaluations_even_when_report_is_evaluated(
    migrated_db: async_sessionmaker,
) -> None:
    # D1: no peer visibility at ANY evaluation.status or report.status.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        h1, evid1, _, _ = await _two_evaluators(migrated_db, c, ah, ex, rid)
        async with migrated_db() as s:
            await s.execute(text("UPDATE report SET status = 'evaluated' WHERE id = CAST(:i AS uuid)"), {"i": rid})
            await s.execute(
                text("UPDATE evaluation SET status = 'completed' WHERE report_id = CAST(:i AS uuid)"), {"i": rid}
            )
            await s.commit()
        rows = (await c.get(_list_url(ex, rid), headers=h1)).json()["data"]["evaluations"]
        assert [r["id"] for r in rows] == [evid1]


async def test_evaluator_not_assigned_to_this_report_is_refused(migrated_db: async_sessionmaker) -> None:
    """403, NOT the ``200 []`` W5-1 shipped — the route gates now (W5-3 Task 10, #122).

    The response carries the report's aggregate, so an empty ``evaluations[]`` would still hand
    a non-participant the grade, the grade_version and the evaluator headcount. #95's "scoping
    is a filter, not a gate" held only while the body was nothing but the caller's own rows.
    """
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        await _two_evaluators(migrated_db, c, ah, ex, rid)
        hc, _ = await evaluator(migrated_db, c, ah, ex, "evc")
        r = await c.get(_list_url(ex, rid), headers=hc)
        assert r.status_code == 403


async def test_evaluator_gets_own_evaluation_detail(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        h1, evid1, _, _ = await _two_evaluators(migrated_db, c, ah, ex, rid)
        r = await c.get(_detail_url(ex, rid, evid1), headers=h1)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["id"] == evid1


async def test_evaluator_getting_a_peer_evaluation_returns_403(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        h1, _, _, evid2 = await _two_evaluators(migrated_db, c, ah, ex, rid)
        r = await c.get(_detail_url(ex, rid, evid2), headers=h1)
        assert r.status_code == 403
        assert r.json()["error"]["message"] == "not_your_evaluation"


async def test_detail_includes_evaluator_only_template_fields(migrated_db: async_sessionmaker) -> None:
    # L12 — these fields are excluded from every ReportSectionOut and surface here for the first time.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        h1, evid1, _, _ = await _two_evaluators(migrated_db, c, ah, ex, rid)
        sec = (await c.get(_detail_url(ex, rid, evid1), headers=h1)).json()["data"]["sections"][0]
        assert sec["grade_mode"] == "numeric"
        assert float(sec["grade_min"]) == 0
        assert float(sec["grade_max"]) == 10
        assert "grade_weight" in sec
        assert "rubric_criteria" in sec
        assert "evaluation_criteria" in sec


async def test_detail_includes_section_content_for_grading(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        h1, evid1, _, _ = await _two_evaluators(migrated_db, c, ah, ex, rid)
        sec = (await c.get(_detail_url(ex, rid, evid1), headers=h1)).json()["data"]["sections"][0]
        assert sec["content_plain"] == "done"
        assert sec["grade"] is None


async def test_detail_orders_sections_by_position(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
            "id"
        ]
        for name in ("first", "second", "third"):
            await c.post(
                f"/api/v1/templates/{tid}/sections",
                json={"name": name, "field_type": "rich_text", "is_required": False},
                headers=ah,
            )
        await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        team = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        rid = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports",
                json={"template_id": tid, "team_id": team, "name": "R"},
                headers=ah,
            )
        ).json()["data"]["id"]
        await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
        h1, uid1 = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid1 = await assign(c, ah, ex, rid, uid1)
        secs = (await c.get(_detail_url(ex, rid, evid1), headers=h1)).json()["data"]["sections"]
        assert [s["position"] for s in secs] == sorted(s["position"] for s in secs)
        assert [s["name"] for s in secs] == ["first", "second", "third"]


async def test_detail_reports_grade_version_zero_before_any_rollup(migrated_db: async_sessionmaker) -> None:
    # D3 — rollup.py owns the increment; nothing in W5-1 touches it.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        h1, evid1, _, _ = await _two_evaluators(migrated_db, c, ah, ex, rid)
        assert (await c.get(_detail_url(ex, rid, evid1), headers=h1)).json()["data"]["grade_version"] == 0


async def test_detail_for_unknown_evaluation_returns_404(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        r = await c.get(_detail_url(ex, rid, "00000000-0000-0000-0000-000000000000"), headers=ah)
        assert r.status_code == 404


async def test_detail_for_evaluation_of_another_report_returns_404(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid_a, _ = await submitted_report(c, ah)
        _, rid_b, _ = await submitted_report(c, ah)
        _, uid1 = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid_a = await assign(c, ah, ex, rid_a, uid1)
        # Right evaluation id, wrong parent report -> 404, not 403.
        r = await c.get(_detail_url(ex, rid_b, evid_a), headers=ah)
        assert r.status_code == 404


@pytest.mark.parametrize("role_key", ["team_writer", "team_admin", "team_approver", "observer"])
async def test_non_evaluator_roles_are_denied_both_reads(migrated_db: async_sessionmaker, role_key: str) -> None:
    # L13 — EVALUATIONS_READ_OWN holders get 403 on every W5-1 evaluation route.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid1 = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid1 = await assign(c, ah, ex, rid, uid1)
        hr, _ = await role_holder(migrated_db, c, ah, ex, f"r-{role_key}", role_key)
        assert (await c.get(_list_url(ex, rid), headers=hr)).status_code == 403
        assert (await c.get(_detail_url(ex, rid, evid1), headers=hr)).status_code == 403
