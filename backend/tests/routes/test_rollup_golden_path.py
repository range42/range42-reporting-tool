"""Task 12 — the plan's worked example, end to end through the real API.

The unit-level golden paths (Tasks 4 and 5) use a constructed fixture. This one reproduces the
W5-2 plan's worked example verbatim, driving every grading mode through the HTTP routes so the
whole slice — validation, rubric pre-rollup, pass_fail scaling, not_graded exclusion,
multi-evaluator aggregation, persistence, M17 visibility — is exercised in one pass.

    Template: S1 numeric 0-10 w1.0 · S2 pass_fail 0-10 w1.5 · S3 rubric 0-10 w2.0 {A w1 max5, B w1 max5}
              S4 choice, not_graded, w1.0

    Evaluator X (aggregated_weight 1.00):
        S1 = 8.00 ; S2 pass -> 10.00 ; S3 A=4, B=3 -> 0.70 -> 7.00 ; S4 no row
        (8.00·1.0 + 10.00·1.5 + 7.00·2.0) / (1.0 + 1.5 + 2.0) = 37.00 / 4.50 = 8.222… -> 8.22

    Evaluator Y (aggregated_weight 2.00) computes to 7.00.

    report.overall_grade = (8.22·1.00 + 7.00·2.00) / 3.00 = 22.22 / 3.00 = 7.406… -> 7.41
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import assign, evaluator, ga_headers
from tests.routes._helpers import client

pytestmark = pytest.mark.integration

_RUBRIC = [{"name": "A", "weight": 1, "max_score": 5}, {"name": "B", "weight": 1, "max_score": 5}]
_CHOICE = {"selection": "single", "values": [{"code": "y", "label": "Yes", "position": 0}]}
_SECTIONS = [
    {"name": "S1", "field_type": "rich_text", "grade_mode": "numeric", "grade_min": 0, "grade_max": 10},
    {
        "name": "S2",
        "field_type": "rich_text",
        "grade_mode": "pass_fail",
        "grade_min": 0,
        "grade_max": 10,
        "grade_weight": 1.5,
    },
    {
        "name": "S3",
        "field_type": "rich_text",
        "grade_mode": "rubric",
        "grade_min": 0,
        "grade_max": 10,
        "grade_weight": 2.0,
        "rubric_criteria": _RUBRIC,
    },
    {"name": "S4", "field_type": "choice", "grade_mode": "not_graded", "choice_config": _CHOICE},
]


async def _worked_example_report(c, ah):
    tid = (await c.post("/api/v1/templates", json={"name": "Golden", "report_type": "sitrep"}, headers=ah)).json()[
        "data"
    ]["id"]
    for section in _SECTIONS:
        r = await c.post(f"/api/v1/templates/{tid}/sections", json={"is_required": False, **section}, headers=ah)
        assert r.status_code == 201, r.text
    assert (await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)).status_code == 200
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
    team = (await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)).json()[
        "data"
    ]["id"]
    detail = (
        await c.post(
            f"/api/v1/exercises/{ex}/reports", json={"template_id": tid, "team_id": team, "name": "R"}, headers=ah
        )
    ).json()["data"]
    rid = detail["id"]
    sids = {s["name"]: s["id"] for s in detail["sections"]}
    r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    assert r.json()["data"]["status"] == "submitted", r.text
    return ex, rid, sids


async def _put_grade(c, ex, rid, evid, sid, body, headers):
    r = await c.put(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _evaluation_grade(c, ex, rid, evid, headers):
    r = await c.get(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["overall_grade"]


async def _report_grade(c, ex, rid, ah):
    r = await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    return d["overall_grade"], d["overall_grade_is_manual"], d["grade_version"]


async def test_worked_example_lands_on_8_22_and_7_41(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids = await _worked_example_report(c, ah)
        hx, uid_x = await evaluator(migrated_db, c, ah, ex, "x")
        hy, uid_y = await evaluator(migrated_db, c, ah, ex, "y")
        evid_x = await assign(c, ah, ex, rid, uid_x, aggregated_weight="1.00")
        evid_y = await assign(c, ah, ex, rid, uid_y, aggregated_weight="2.00")

        # Evaluator X — every graded mode; S4 (not_graded) is left alone.
        await _put_grade(c, ex, rid, evid_x, sids["S1"], {"grade": "8"}, hx)
        await _put_grade(c, ex, rid, evid_x, sids["S2"], {"pass_fail_result": True}, hx)
        scores = [{"criterion": "A", "score": "4"}, {"criterion": "B", "score": "3"}]
        s3 = await _put_grade(c, ex, rid, evid_x, sids["S3"], {"rubric_scores": scores}, hx)
        assert s3["grade"] == "7.00"  # M7 pre-rollup: 0.70 stretched onto 0-10
        assert await _evaluation_grade(c, ex, rid, evid_x, hx) == "8.22"
        # Only X has graded — Y contributes neither a value nor its weight yet.
        assert await _report_grade(c, ex, rid, ah) == ("8.22", False, 3)

        # Evaluator Y computes to 7.00.
        await _put_grade(c, ex, rid, evid_y, sids["S1"], {"grade": "7"}, hy)
        assert await _evaluation_grade(c, ex, rid, evid_y, hy) == "7.00"

        # D3: one bump per published number — 8.00, 9.20 (S2 joins), 8.22 (S3 joins), 7.41 (Y joins).
        assert await _report_grade(c, ex, rid, ah) == ("7.41", False, 4)
        listed = (await c.get(f"/api/v1/exercises/{ex}/reports", headers=ah)).json()["data"][0]
    assert (listed["overall_grade"], listed["grade_version"]) == ("7.41", 4)
