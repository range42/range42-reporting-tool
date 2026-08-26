import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AuditLog, Report
from app.seed import seed_system_roles
from app.services.workflow.state_machine import InvalidTransition, transition
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _make_report(migrated_db: async_sessionmaker) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a draft report via the API; return (report_id, ga_user_id)."""
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, uid = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {tok}"}
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
        rid = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports",
                json={"template_id": tid, "team_id": team, "name": "R"},
                headers=ah,
            )
        ).json()["data"]["id"]
    return uuid.UUID(rid), uuid.UUID(uid)


async def _audit_count(s: AsyncSession) -> int:
    return (await s.execute(select(func.count()).select_from(AuditLog))).scalar_one()


async def test_transition_to_submitted_sets_timestamp_and_audits(migrated_db: async_sessionmaker) -> None:
    rid, uid = await _make_report(migrated_db)
    async with migrated_db() as s:
        report = (await s.execute(select(Report).where(Report.id == rid))).scalar_one()
        before = await _audit_count(s)
        await transition(s, report, target_status="submitted", actor_id=uid, action="report.submit")
        await s.commit()
        assert report.status == "submitted"
        assert report.submitted_at is not None
        assert await _audit_count(s) == before + 1


async def test_transition_to_draft_clears_submitted_at(migrated_db: async_sessionmaker) -> None:
    rid, uid = await _make_report(migrated_db)
    async with migrated_db() as s:
        report = (await s.execute(select(Report).where(Report.id == rid))).scalar_one()
        await transition(s, report, target_status="submitted", actor_id=uid, action="report.submit")
        await transition(s, report, target_status="draft", actor_id=uid, action="report.recall")
        await s.commit()
        assert report.status == "draft"
        assert report.submitted_at is None


async def test_illegal_transition_raises_and_is_inert(migrated_db: async_sessionmaker) -> None:
    rid, uid = await _make_report(migrated_db)
    async with migrated_db() as s:
        report = (await s.execute(select(Report).where(Report.id == rid))).scalar_one()
        before = await _audit_count(s)
        with pytest.raises(InvalidTransition):
            # draft -> draft is not a legal edge
            await transition(s, report, target_status="draft", actor_id=uid, action="report.recall")
        assert report.status == "draft"
        assert await _audit_count(s) == before


async def test_transition_to_under_evaluation_leaves_submitted_at_intact(migrated_db: async_sessionmaker) -> None:
    # W5-S2's timeline compares submitted_at against the deadline (§7.3); the evaluation
    # edges must neither set nor clear it.
    rid, uid = await _make_report(migrated_db)
    async with migrated_db() as s:
        report = (await s.execute(select(Report).where(Report.id == rid))).scalar_one()
        await transition(s, report, target_status="submitted", actor_id=uid, action="report.submit")
        submitted_at = report.submitted_at
        await transition(s, report, target_status="under_evaluation", actor_id=uid, action="report.under_evaluation")
        assert report.status == "under_evaluation"
        assert report.submitted_at == submitted_at
        # Not committed: 0011's downgrade restores the 3-value ck_report_status and would
        # fail on a surviving under_evaluation row, breaking migrated_db teardown.
        await s.rollback()
