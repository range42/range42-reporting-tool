import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog, ExerciseRole
from app.seed import seed_system_roles
from tests.routes._evaluations import assign, evaluator, finalize, submitted_report
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _ga(migrated_db: async_sessionmaker) -> tuple[dict[str, str], str]:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, uid = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}, uid


async def _grant_role(migrated_db: async_sessionmaker, *, user_id: str, exercise_id: str, role_key: str) -> None:
    async with migrated_db() as s:
        s.add(ExerciseRole(user_id=uuid.UUID(user_id), exercise_id=uuid.UUID(exercise_id), role_key=role_key))
        await s.commit()


async def _audit_count(migrated_db: async_sessionmaker, action: str) -> int:
    async with migrated_db() as s:
        return (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))
        ).scalar_one()


async def _mk_report(c, ah, *, submit: bool) -> tuple[str, str]:
    """Create a filled report; optionally submit it (no approval_required -> submitted)."""
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
    if submit:
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
        assert r.json()["data"]["status"] == "submitted", r.text
    return ex, rid


async def test_recall_submitted_to_draft(migrated_db: async_sessionmaker) -> None:
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _mk_report(c, ah, submit=True)
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/recall", json={"comment": "needs edits"}, headers=ah)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "draft"
        assert d["submitted_at"] is None
    assert await _audit_count(migrated_db, "report.recall") == 1


async def test_recall_rejects_non_submitted(migrated_db: async_sessionmaker) -> None:
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _mk_report(c, ah, submit=False)  # still draft
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/recall", json={}, headers=ah)
        assert r.status_code == 409
        assert r.json()["error"]["message"] == "invalid_state"
    assert await _audit_count(migrated_db, "report.recall") == 0


async def test_recall_forbidden_without_permission(migrated_db: async_sessionmaker) -> None:
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _mk_report(c, ah, submit=True)
        ptok, _puid = await make_user_token(migrated_db, jti="plain", admin=False)
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/recall",
            json={},
            headers={"Authorization": f"Bearer {ptok}"},
        )
        assert r.status_code == 403
    assert await _audit_count(migrated_db, "report.recall") == 0


# --- W5-4: the recall guard against a live evaluation surface ------------------------
#
# ORDER TRAP. ``_require_status(report, "submitted")`` runs BEFORE the evaluation guard, and
# the first evaluator write moves the report to ``under_evaluation`` — so a report that has a
# graded evaluation fails the status check first and answers ``invalid_state``. A test that
# only asserted ``== 409`` would pass without the guard existing at all.
#
# These tests therefore force the report back to ``submitted`` while leaving the evaluation
# where it is, which is the only state in which the guard is the thing being tested, and they
# assert the error CODE rather than the status. The guard is defence in depth: it must hold
# even when a report's status says recall is otherwise permissible.


async def _force_report_status(migrated_db: async_sessionmaker, rid: str, status: str) -> None:
    async with migrated_db() as s:
        await s.execute(
            text("UPDATE report SET status = :st WHERE id = CAST(:i AS uuid)"),
            {"st": status, "i": rid},
        )
        await s.commit()


async def _recall(c, ah, ex: str, rid: str):
    return await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/recall", json={}, headers=ah)


async def _graded_world(migrated_db, c, ah):
    """Submitted report + one assigned evaluator + one gradable section.

    Returns (ex, rid, sid, evaluator_headers, evaluation_id). Nothing is graded yet, so the
    evaluation is ``assigned`` and the report is still ``submitted``.
    """
    ex, rid, sid = await submitted_report(c, ah)
    eh, uid = await evaluator(migrated_db, c, ah, ex, "ev-0")
    evid = await assign(c, ah, ex, rid, uid)
    return ex, rid, sid, eh, evid


async def _grade(c, ex, rid, evid, sid, value, headers) -> None:
    r = await c.put(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
        json={"grade": value},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def test_recall_is_allowed_when_evaluations_are_only_assigned(
    migrated_db: async_sessionmaker,
) -> None:
    """Assignment is not the start of work. The pre-WP5 permissiveness must not regress."""
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _sid, _eh, _evid = await _graded_world(migrated_db, c, ah)

        # Act
        r = await _recall(c, ah, ex, rid)

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "draft"


async def test_recall_is_blocked_once_an_evaluation_is_in_progress(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, eh, evid = await _graded_world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, 7, eh)
        await _force_report_status(migrated_db, rid, "submitted")

        # Act
        r = await _recall(c, ah, ex, rid)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "evaluation_in_progress"


async def test_recall_is_blocked_once_an_evaluation_is_completed(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, eh, evid = await _graded_world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, 7, eh)
        await finalize(c, eh, ex, rid, evid)
        await _force_report_status(migrated_db, rid, "submitted")

        # Act
        r = await _recall(c, ah, ex, rid)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "evaluation_in_progress"


async def test_recall_is_blocked_when_a_reopened_evaluation_is_in_progress(
    migrated_db: async_sessionmaker,
) -> None:
    """A reopen is not a back door to recall.

    The report was evaluated, an admin reopened one evaluation, and the report is now under
    evaluation again with an ``in_progress`` row. Recall must still refuse — and refuse for
    THIS reason, which is why the error code is asserted rather than the bare status.
    """
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, eh, evid = await _graded_world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, 7, eh)
        await finalize(c, eh, ex, rid, evid)
        rr = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/reopen",
            json={"reason": "recount"},
            headers=ah,
        )
        assert rr.status_code == 200, rr.text
        await _force_report_status(migrated_db, rid, "submitted")

        # Act
        r = await _recall(c, ah, ex, rid)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "evaluation_in_progress"


async def test_recall_is_blocked_when_only_an_unassigned_evaluation_is_completed(
    migrated_db: async_sessionmaker,
) -> None:
    """Unassignment does not un-assess a report — so recall stays blocked.

    A DELIBERATE ASYMMETRY with the grade aggregate, which DOES exclude unassigned rows. The
    aggregate is asking "whose grade counts toward the number"; this guard is asking "has
    anyone looked at this content yet". An unassigned evaluator's completed grades answer yes,
    and returning the report to draft would let the team rewrite content already assessed.
    """
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, eh, evid = await _graded_world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, 7, eh)
        await finalize(c, eh, ex, rid, evid)
        ur = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/unassign",
            json={"reason": "left the exercise"},
            headers=ah,
        )
        assert ur.status_code == 200, ur.text
        await _force_report_status(migrated_db, rid, "submitted")

        # Act
        r = await _recall(c, ah, ex, rid)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "evaluation_in_progress"


async def test_the_recall_guard_is_scoped_to_the_report(migrated_db: async_sessionmaker) -> None:
    """One missing report_id predicate and every recall in the exercise breaks.

    Two reports in the SAME exercise: the second is being graded, the first has no evaluations
    at all. Recalling the first must succeed.
    """
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, graded_rid, sid, eh, evid = await _graded_world(migrated_db, c, ah)
        template_id = (await c.get(f"/api/v1/exercises/{ex}/reports/{graded_rid}", headers=ah)).json()["data"][
            "template_id"
        ]
        team_id = (await c.get(f"/api/v1/exercises/{ex}/teams", headers=ah)).json()["data"][0]["id"]
        detail = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports",
                json={"template_id": template_id, "team_id": team_id, "name": "R2"},
                headers=ah,
            )
        ).json()["data"]
        clean_rid, clean_sid = detail["id"], detail["sections"][0]["id"]
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{clean_rid}/sections/{clean_sid}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
            headers=ah,
        )
        sr = await c.post(f"/api/v1/exercises/{ex}/reports/{clean_rid}/submit", headers=ah)
        assert sr.json()["data"]["status"] == "submitted", sr.text
        # The OTHER report is the one under evaluation.
        await _grade(c, ex, graded_rid, evid, sid, 7, eh)

        # Act
        r = await _recall(c, ah, ex, clean_rid)

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "draft"
