import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import evaluator, ga_headers, submitted_report
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _draft_report(c, ah):
    """Same shape as _submitted_report, stopping before submit."""
    tid = (await c.post("/api/v1/templates", json={"name": "T2", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={"name": "S", "field_type": "rich_text", "is_required": True},
        headers=ah,
    )
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    ex = (await c.post("/api/v1/exercises", json={"name": "E2"}, headers=ah)).json()["data"]["id"]
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
    return ex, detail["id"], detail["sections"][0]["id"]


def _url(ex, rid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations"


async def _set_report_status(migrated_db, rid, status):
    """Drive report.status directly — no route reaches these states until W5-3/W5-4."""
    async with migrated_db() as s:
        await s.execute(text("UPDATE report SET status = :st WHERE id = CAST(:i AS uuid)"), {"st": status, "i": rid})
        await s.commit()


async def test_global_admin_assigns_evaluator_to_submitted_report(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        r = await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)
        assert r.status_code == 201, r.text


async def test_assign_returns_data_envelope_with_evaluation_id(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        d = (await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)).json()["data"]
        assert d["id"]
        assert d["report_id"] == rid
        assert d["evaluator_id"] == uid
        assert d["gradable_section_count"] == 1
        assert d["graded_section_count"] == 0
        assert "aggregated_weight" not in d  # L11 — admin-only, surfaced by W5-3


async def test_assign_sets_evaluation_status_to_assigned(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        d = (await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)).json()["data"]
        assert d["status"] == "assigned"
        assert d["completed_at"] is None
        assert d["reopen_count"] == 0


async def test_assign_records_assigned_by_as_the_calling_admin(migrated_db: async_sessionmaker) -> None:
    ah, ga_uid = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid = (await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)).json()["data"]["id"]
    async with migrated_db() as s:
        row = (
            await s.execute(text("SELECT assigned_by FROM evaluation WHERE id = CAST(:i AS uuid)"), {"i": evid})
        ).scalar_one()
        assert str(row) == ga_uid


async def test_assign_leaves_report_status_submitted(migrated_db: async_sessionmaker) -> None:
    # L5 — assignment alone does not begin evaluation; only a grade/feedback write does (Task 7).
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)
        got = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)).json()["data"]
        assert got["status"] == "submitted"


async def test_assign_to_draft_report_returns_409(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _draft_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        r = await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)
        assert r.status_code == 409
        assert r.json()["error"]["message"] == "report_not_submitted"


async def test_assign_to_pending_approval_report_returns_409(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
            "id"
        ]
        await c.post(
            f"/api/v1/templates/{tid}/sections",
            json={"name": "S", "field_type": "rich_text", "is_required": True},
            headers=ah,
        )
        await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        team = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        detail = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports",
                json={"template_id": tid, "team_id": team, "name": "R", "approval_required": True},
                headers=ah,
            )
        ).json()["data"]
        rid, sid = detail["id"], detail["sections"][0]["id"]
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
            headers=ah,
        )
        submitted = (await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)).json()["data"]
        assert submitted["status"] == "pending_approval"
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        r = await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)
        assert r.status_code == 409
        assert r.json()["error"]["message"] == "report_not_submitted"


async def test_assign_to_evaluated_report_returns_409(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        # No finalize endpoint until W5-3; drive the terminal state directly.
        await _set_report_status(migrated_db, rid, "evaluated")
        r = await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)
        assert r.status_code == 409
        assert r.json()["error"]["message"] == "report_not_submitted"


async def test_assign_second_evaluator_to_under_evaluation_report_succeeds(migrated_db: async_sessionmaker) -> None:
    # A second evaluator may join once grading has begun (multi-evaluator, W5-3).
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid1 = await evaluator(migrated_db, c, ah, ex, "ev1")
        await c.post(_url(ex, rid), json={"evaluator_id": uid1}, headers=ah)
        await _set_report_status(migrated_db, rid, "under_evaluation")
        _, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        r = await c.post(_url(ex, rid), json={"evaluator_id": uid2}, headers=ah)
        assert r.status_code == 201, r.text


async def test_assign_same_evaluator_twice_returns_409_duplicate(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        assert (await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)).status_code == 201
        r = await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)
        assert r.status_code == 409
        assert r.json()["error"]["message"] == "evaluator_already_assigned"


async def test_assign_user_without_evaluator_role_in_exercise_returns_422(migrated_db: async_sessionmaker) -> None:
    # Guards that the target actually holds evaluations:write *in this exercise*.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await make_user_token(migrated_db, jti="nobody")
        r = await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=ah)
        assert r.status_code == 422
        assert r.json()["error"]["message"] == "user_is_not_an_evaluator"


async def test_assign_unknown_user_returns_404(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        r = await c.post(_url(ex, rid), json={"evaluator_id": "00000000-0000-0000-0000-000000000000"}, headers=ah)
        assert r.status_code == 404


async def test_assign_malformed_user_id_returns_404(migrated_db: async_sessionmaker) -> None:
    # evaluator_id is typed str so this handler owns the response — not a Pydantic 422.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        r = await c.post(_url(ex, rid), json={"evaluator_id": "not-a-uuid"}, headers=ah)
        assert r.status_code == 404


async def test_assign_by_non_admin_evaluator_returns_403(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        eh, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        r = await c.post(_url(ex, rid), json={"evaluator_id": uid}, headers=eh)
        assert r.status_code == 403


async def test_assign_with_aggregated_weight_persists_the_weight(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid = (await c.post(_url(ex, rid), json={"evaluator_id": uid, "aggregated_weight": "2.5"}, headers=ah)).json()[
            "data"
        ]["id"]
    async with migrated_db() as s:
        w = (
            await s.execute(text("SELECT aggregated_weight FROM evaluation WHERE id = CAST(:i AS uuid)"), {"i": evid})
        ).scalar_one()
        assert float(w) == 2.5
