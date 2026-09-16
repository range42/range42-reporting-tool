"""Approvals belong to a SUBMISSION, not to the report forever.

``approval_record`` carries a cycle counter so an approval names the submission it approved: a
recall followed by a resubmission reopens every step instead of leaving the report stuck in
``pending_approval`` with ``step_already_approved``.

Rejection carries the same rule: content changes after a rejection, so earlier steps must sign
off again rather than being silently skipped.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import ExerciseRole, Report
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _ga(migrated_db: async_sessionmaker) -> dict[str, str]:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def _grant(migrated_db: async_sessionmaker, *, user_id: str, exercise_id: str, role_key: str) -> None:
    async with migrated_db() as s:
        s.add(ExerciseRole(user_id=uuid.UUID(user_id), exercise_id=uuid.UUID(exercise_id), role_key=role_key))
        await s.commit()


async def _mk_pending(c, ah, chain: list[dict] | None = None) -> tuple[str, str, str]:
    """Template -> exercise -> team -> report (approval required) -> submitted, awaiting approval."""
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
    body: dict = {"template_id": tid, "team_id": team, "name": "R", "approval_required": True}
    if chain is not None:
        body["approval_chain"] = chain
    detail = (await c.post(f"/api/v1/exercises/{ex}/reports", json=body, headers=ah)).json()["data"]
    rid, sid = detail["id"], detail["sections"][0]["id"]
    await c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "rich_text", "content": "<p>x</p>"}},
        headers=ah,
    )
    r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    assert r.json()["data"]["status"] == "pending_approval", r.text
    return ex, rid, sid


async def _resubmit(c, ah, ex: str, rid: str) -> None:
    r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    assert r.json()["data"]["status"] == "pending_approval", r.text


async def _cycle(migrated_db: async_sessionmaker, rid: str) -> int:
    async with migrated_db() as s:
        report = (await s.execute(select(Report).where(Report.id == uuid.UUID(rid)))).scalar_one()
        return report.approval_cycle


async def test_a_recalled_report_can_be_approved_again(migrated_db: async_sessionmaker) -> None:
    """Recall -> resubmit -> approve must succeed, not dead-end."""
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        assert (await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", headers=ah)).status_code == 200
        assert (await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/recall", headers=ah)).status_code == 200
        await _resubmit(c, ah, ex, rid)
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", headers=ah)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "submitted"


async def test_recall_advances_the_submission_cycle(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        assert await _cycle(migrated_db, rid) == 1
        await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", headers=ah)
        await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/recall", headers=ah)
        assert await _cycle(migrated_db, rid) == 2


async def test_the_earlier_approval_survives_for_the_audit_trail(migrated_db: async_sessionmaker) -> None:
    """Superseding is not erasing: both approvals stay readable on the report."""
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", headers=ah)
        await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/recall", headers=ah)
        await _resubmit(c, ah, ex, rid)
        await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", headers=ah)
        detail = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)).json()["data"]
        approved = [a for a in detail["approval_records"] if a["action"] == "approved"]
        assert len(approved) == 2, detail["approval_records"]
        assert sorted(a["cycle"] for a in approved) == [1, 2]


async def test_approving_the_same_step_twice_in_one_cycle_is_still_refused(migrated_db: async_sessionmaker) -> None:
    """The cycle must not weaken the original guard within a single submission.

    Two steps, so the report is still pending_approval after the first: on a single-step chain
    the first approval finalizes it and a second call would be refused for the state, not the
    step, which would not exercise this guard at all.
    """
    ah = await _ga(migrated_db)
    chain = [{"role_key": "team_approver", "required": True}, {"role_key": "team_approver", "required": True}]
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah, chain)
        assert (
            await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={"step": 1}, headers=ah)
        ).status_code == 200
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={"step": 1}, headers=ah)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["message"] == "step_already_approved"


async def test_rejection_invalidates_an_earlier_step_approval(migrated_db: async_sessionmaker) -> None:
    """The content changed, so step 1 signs off again rather than being skipped."""
    ah = await _ga(migrated_db)
    chain = [{"role_key": "team_approver", "required": True}, {"role_key": "team_approver", "required": True}]
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah, chain)
        assert (
            await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={"step": 1}, headers=ah)
        ).status_code == 200
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/reject", json={"step": 2, "comment": "needs work"}, headers=ah
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "draft"
        await _resubmit(c, ah, ex, rid)
        # Step 1 is open again: approving it must succeed and must NOT finalize on its own.
        again = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={"step": 1}, headers=ah)
        assert again.status_code == 200, again.text
        assert again.json()["data"]["status"] == "pending_approval"
        last = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={"step": 2}, headers=ah)
        assert last.json()["data"]["status"] == "submitted", last.text
