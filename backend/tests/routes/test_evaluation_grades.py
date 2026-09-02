from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import assign, evaluator, ga_headers
from tests.routes._helpers import client

pytestmark = pytest.mark.integration

# weight is required by section_invariant_error (WP3): each criterion needs max_score>0 AND weight>0.
RUBRIC = [{"name": "Clarity", "max_score": 5, "weight": 1}, {"name": "Depth", "max_score": 10, "weight": 1}]
NUMERIC = {"grade_mode": "numeric", "grade_min": 0, "grade_max": 10}
PASS_FAIL = {"grade_mode": "pass_fail"}
RUBRIC_SECTION = {"grade_mode": "rubric", "rubric_criteria": RUBRIC}


async def _report_with_section(c, ah, **section):
    """Published template with one section of the given grading shape -> submitted report."""
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    r = await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={"name": "S", "field_type": "rich_text", "is_required": True, **section},
        headers=ah,
    )
    assert r.status_code == 201, r.text
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
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
    await c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
        headers=ah,
    )
    await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    return ex, rid, sid


async def _arrange(migrated_db, c, ah, *, jti="ev1", **section):
    ex, rid, sid = await _report_with_section(c, ah, **section)
    h, uid = await evaluator(migrated_db, c, ah, ex, jti)
    evid = await assign(c, ah, ex, rid, uid)
    return ex, rid, sid, h, evid


def _grade_url(ex, rid, evid, sid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}"


def _grades_url(ex, rid, evid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades"


# --- numeric -----------------------------------------------------------------


async def test_put_numeric_grade_creates_section_grade_row(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **NUMERIC)
        r = await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "7.5"}, headers=h)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["grade"] == "7.50"
        assert d["report_section_id"] == sid


async def test_put_numeric_grade_is_idempotent_upsert_on_second_call(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **NUMERIC)
        first = (await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "5"}, headers=h)).json()["data"]
        second = (await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "9"}, headers=h)).json()["data"]
        assert first["id"] == second["id"]  # same row, updated
        assert second["grade"] == "9.00"
        rows = (await c.get(_grades_url(ex, rid, evid), headers=h)).json()["data"]
        assert len(rows) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"grade": "-1"},  # below grade_min
        {"grade": "11"},  # above grade_max
        {},  # no grade at all
        {"pass_fail_result": True},  # wrong channel for the mode
    ],
)
async def test_put_numeric_grade_rejects_bad_payloads(migrated_db: async_sessionmaker, payload: dict) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **NUMERIC)
        r = await c.put(_grade_url(ex, rid, evid, sid), json=payload, headers=h)
        assert r.status_code == 422, r.text


# --- pass_fail ---------------------------------------------------------------


@pytest.mark.parametrize(("result", "expected"), [(True, "1.00"), (False, "0.00")])
async def test_put_pass_fail_result_stores_zero_or_one(
    migrated_db: async_sessionmaker, result: bool, expected: str
) -> None:
    # A4 — store 0/1; W5-2's rollup applies the grade_max scaling.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **PASS_FAIL)
        d = (await c.put(_grade_url(ex, rid, evid, sid), json={"pass_fail_result": result}, headers=h)).json()["data"]
        assert d["pass_fail_result"] is result
        assert d["grade"] == expected


@pytest.mark.parametrize("payload", [{"pass_fail_result": True, "grade": "10"}, {}])
async def test_put_pass_fail_rejects_bad_payloads(migrated_db: async_sessionmaker, payload: dict) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **PASS_FAIL)
        assert (await c.put(_grade_url(ex, rid, evid, sid), json=payload, headers=h)).status_code == 422


# --- rubric ------------------------------------------------------------------


async def test_put_rubric_scores_persists_the_criteria_array(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **RUBRIC_SECTION)
        body = {"rubric_scores": [{"criterion": "Clarity", "score": "4"}, {"criterion": "Depth", "score": "8"}]}
        d = (await c.put(_grade_url(ex, rid, evid, sid), json=body, headers=h)).json()["data"]
        assert [e["criterion"] for e in d["rubric_scores"]] == ["Clarity", "Depth"]


async def test_put_rubric_persists_the_pre_rolled_grade_into_section_grade(migrated_db: async_sessionmaker) -> None:
    # M7 — flipped from W5-1's "leaves grade null"; Task 8 wired the pre-rollup in. The section
    # declares no range, so Clarity 4/5 = 80% lands on [0, 1].
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **RUBRIC_SECTION)
        body = {"rubric_scores": [{"criterion": "Clarity", "score": "4"}]}
        d = (await c.put(_grade_url(ex, rid, evid, sid), json=body, headers=h)).json()["data"]
        assert d["grade"] == "0.80"


async def test_rubric_grade_participates_in_the_report_rollup(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **RUBRIC_SECTION)
        body = {"rubric_scores": [{"criterion": "Clarity", "score": "4"}, {"criterion": "Depth", "score": "8"}]}
        await c.put(_grade_url(ex, rid, evid, sid), json=body, headers=h)
    async with migrated_db() as s:
        og = (
            await s.execute(text("SELECT overall_grade FROM report WHERE id = CAST(:i AS uuid)"), {"i": rid})
        ).scalar_one()
    assert og == Decimal("0.80")


@pytest.mark.parametrize(
    "scores",
    [
        [{"criterion": "Nonexistent", "score": "1"}],  # unknown criterion name
        [{"criterion": "Clarity", "score": "6"}],  # above that criterion's max_score
        [{"criterion": "Clarity", "score": "-1"}],  # negative
    ],
)
async def test_put_rubric_rejects_bad_scores(migrated_db: async_sessionmaker, scores: list) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **RUBRIC_SECTION)
        r = await c.put(_grade_url(ex, rid, evid, sid), json={"rubric_scores": scores}, headers=h)
        assert r.status_code == 422, r.text


async def test_put_rubric_without_scores_returns_422(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **RUBRIC_SECTION)
        assert (await c.put(_grade_url(ex, rid, evid, sid), json={}, headers=h)).status_code == 422


async def test_put_rubric_on_section_without_rubric_criteria_returns_422(migrated_db: async_sessionmaker) -> None:
    # Edge case 15 — a template misconfiguration WP3 does not forbid. 422, never a 500.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **RUBRIC_SECTION)
        async with migrated_db() as s:
            await s.execute(text("UPDATE template_section_def SET rubric_criteria = NULL"))
            await s.commit()
        r = await c.put(
            _grade_url(ex, rid, evid, sid),
            json={"rubric_scores": [{"criterion": "Clarity", "score": "1"}]},
            headers=h,
        )
        assert r.status_code == 422
        assert r.json()["error"]["message"] == "section_has_no_rubric_criteria"


# --- not_graded --------------------------------------------------------------


async def test_put_grade_on_not_graded_section_returns_422_and_creates_no_row(
    migrated_db: async_sessionmaker,
) -> None:
    # §7.2's finalize condition and §4.2's rollup rule both read the ABSENCE of the row.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)  # default grade_mode = not_graded
        r = await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "5"}, headers=h)
        assert r.status_code == 422
        assert r.json()["error"]["message"] == "section_not_graded"
    async with migrated_db() as s:
        assert (await s.execute(text("SELECT count(*) FROM section_grade"))).scalar_one() == 0


# --- lifecycle + isolation ---------------------------------------------------


async def test_first_grade_write_moves_report_to_under_evaluation(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **NUMERIC)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "5"}, headers=h)
    async with migrated_db() as s:
        st = (await s.execute(text("SELECT status FROM report WHERE id = CAST(:i AS uuid)"), {"i": rid})).scalar_one()
        assert st == "under_evaluation"


async def test_grade_write_recomputes_report_overall_grade(migrated_db: async_sessionmaker) -> None:
    # FLIPPED from W5-1, which asserted both stayed null/zero. Task 8 wired the A7 rollup into
    # this handler, so a grade save now publishes the report grade in the same transaction.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **NUMERIC)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "5"}, headers=h)
    async with migrated_db() as s:
        gv, og = (
            await s.execute(
                text("SELECT grade_version, overall_grade FROM report WHERE id = CAST(:i AS uuid)"), {"i": rid}
            )
        ).one()
        assert og == Decimal("5.00")
        assert gv == 1


async def test_grade_write_recomputes_the_callers_evaluation_overall_grade(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **NUMERIC)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "5"}, headers=h)
        d = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}", headers=h)).json()["data"]
    assert d["overall_grade"] == "5.00"


async def test_grade_write_increments_grade_version_on_each_change(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **NUMERIC)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "5"}, headers=h)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "7"}, headers=h)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "7"}, headers=h)  # no change
    async with migrated_db() as s:
        gv = (
            await s.execute(text("SELECT grade_version FROM report WHERE id = CAST(:i AS uuid)"), {"i": rid})
        ).scalar_one()
    assert gv == 2


async def test_second_evaluators_grade_changes_the_aggregate(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h1, evid1 = await _arrange(migrated_db, c, ah, jti="ev1", **NUMERIC)
        await c.put(_grade_url(ex, rid, evid1, sid), json={"grade": "9"}, headers=h1)
        h2, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        evid2 = await assign(c, ah, ex, rid, uid2)
        await c.put(_grade_url(ex, rid, evid2, sid), json={"grade": "5"}, headers=h2)
    async with migrated_db() as s:
        og = (
            await s.execute(text("SELECT overall_grade FROM report WHERE id = CAST(:i AS uuid)"), {"i": rid})
        ).scalar_one()
    assert og == Decimal("7.00")


async def test_grade_write_on_completed_evaluation_returns_409(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **NUMERIC)
        async with migrated_db() as s:
            await s.execute(text("UPDATE evaluation SET status = 'completed' WHERE id = CAST(:i AS uuid)"), {"i": evid})
            await s.commit()
        r = await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "5"}, headers=h)
        assert r.status_code == 409
        assert r.json()["error"]["message"] == "evaluation_completed"


async def test_evaluator_grading_a_peer_evaluation_returns_403(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h1, _ = await _arrange(migrated_db, c, ah, jti="ev1", **NUMERIC)
        _, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        evid2 = await assign(c, ah, ex, rid, uid2)
        r = await c.put(_grade_url(ex, rid, evid2, sid), json={"grade": "5"}, headers=h1)
        assert r.status_code == 403


async def test_evaluator_grading_a_section_of_another_report_returns_404(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, h, evid = await _arrange(migrated_db, c, ah, **NUMERIC)
        _, _, other_sid = await _report_with_section(c, ah, **NUMERIC)
        r = await c.put(_grade_url(ex, rid, evid, other_sid), json={"grade": "5"}, headers=h)
        assert r.status_code == 404


async def test_get_grades_returns_only_the_callers_own_grades(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h1, evid1 = await _arrange(migrated_db, c, ah, jti="ev1", **NUMERIC)
        h2, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        evid2 = await assign(c, ah, ex, rid, uid2)
        await c.put(_grade_url(ex, rid, evid1, sid), json={"grade": "4"}, headers=h1)
        await c.put(_grade_url(ex, rid, evid2, sid), json={"grade": "9"}, headers=h2)
        rows = (await c.get(_grades_url(ex, rid, evid1), headers=h1)).json()["data"]
        assert [r["grade"] for r in rows] == ["4.00"]


async def test_get_grades_as_global_admin_returns_every_evaluators_grades(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h1, evid1 = await _arrange(migrated_db, c, ah, jti="ev1", **NUMERIC)
        h2, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        evid2 = await assign(c, ah, ex, rid, uid2)
        await c.put(_grade_url(ex, rid, evid1, sid), json={"grade": "4"}, headers=h1)
        await c.put(_grade_url(ex, rid, evid2, sid), json={"grade": "9"}, headers=h2)
        # Admin bypasses D1 and can read each evaluation's grades, one evaluation at a time.
        a = (await c.get(_grades_url(ex, rid, evid1), headers=ah)).json()["data"]
        b = (await c.get(_grades_url(ex, rid, evid2), headers=ah)).json()["data"]
        assert [r["grade"] for r in a] == ["4.00"]
        assert [r["grade"] for r in b] == ["9.00"]


async def test_two_evaluators_grade_the_same_section_independently(migrated_db: async_sessionmaker) -> None:
    # UNIQUE(evaluation_id, report_section_id) is per-evaluator, not per-section.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h1, evid1 = await _arrange(migrated_db, c, ah, jti="ev1", **NUMERIC)
        h2, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        evid2 = await assign(c, ah, ex, rid, uid2)
        assert (await c.put(_grade_url(ex, rid, evid1, sid), json={"grade": "4"}, headers=h1)).status_code == 200
        assert (await c.put(_grade_url(ex, rid, evid2, sid), json={"grade": "9"}, headers=h2)).status_code == 200
    async with migrated_db() as s:
        assert (await s.execute(text("SELECT count(*) FROM section_grade"))).scalar_one() == 2


async def test_grade_round_trips_as_decimal_not_float(migrated_db: async_sessionmaker) -> None:
    # A float anywhere in this path will bite W5-2's arithmetic.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **NUMERIC)
        d = (await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "0.1"}, headers=h)).json()["data"]
        assert d["grade"] == "0.10"
    async with migrated_db() as s:
        v = (await s.execute(text("SELECT grade FROM section_grade LIMIT 1"))).scalar_one()
        assert isinstance(v, Decimal)


# --- pass_fail sections that declare what a pass is worth ---------------------

BOUNDED_PASS_FAIL = {"grade_mode": "pass_fail", "grade_min": 0, "grade_max": 10}


async def test_pass_fail_section_may_declare_grade_bounds(migrated_db: async_sessionmaker) -> None:
    """A pass_fail section can carry grade_min/grade_max so a pass is worth full marks beside
    numeric siblings. The stored grade stays 0/1 — rollup.py scales it, not the write path."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        # _report_with_section asserts 201 on the section POST, which is the half that used to fail.
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, **BOUNDED_PASS_FAIL)
        d = (await c.put(_grade_url(ex, rid, evid, sid), json={"pass_fail_result": True}, headers=h)).json()["data"]
        assert d["pass_fail_result"] is True
        assert d["grade"] == "1.00"
