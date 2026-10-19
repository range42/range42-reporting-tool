"""Reports sitting in ``under_evaluation``, ordered so the most stalled surface first."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Evaluation, Report, SectionGrade, Team
from app.schemas.evaluation import StalledReportRow, StalledReportsOut
from app.services.evaluation.finalize_gate import resolve_finalize_policy
from app.services.scoring.aggregate import COMPLETED, contributes_grade, counts
from app.services.scoring.rollup import evaluation_facts

UNDER_EVALUATION = "under_evaluation"
#: Audit actions that move a report into ``under_evaluation``.
_ENTRY_ACTIONS = ("report.under_evaluation", "report.reopened")
_EPOCH = datetime.min.replace(tzinfo=UTC)

_EvaluationActivity = tuple[Evaluation, datetime]


async def _under_evaluation_since(db: AsyncSession, report_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    rows = await db.execute(
        select(AuditLog.resource_id, func.max(AuditLog.created_at))
        .where(
            AuditLog.resource_type == "report",
            AuditLog.resource_id.in_(report_ids),
            AuditLog.action.in_(_ENTRY_ACTIONS),
        )
        .group_by(AuditLog.resource_id)
    )
    return {rid: at for rid, at in rows.all()}


async def _evaluations_by_report(
    db: AsyncSession, report_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[_EvaluationActivity]]:
    """Every evaluation of the reports, each with its last activity: its own or its newest grade's update."""
    rows = await db.execute(
        select(Evaluation, func.max(SectionGrade.updated_at))
        .outerjoin(SectionGrade, SectionGrade.evaluation_id == Evaluation.id)
        .where(Evaluation.report_id.in_(report_ids))
        .group_by(Evaluation.id)
    )
    out: dict[uuid.UUID, list[_EvaluationActivity]] = {}
    for ev, newest_grade in rows.all():
        last = max(ev.updated_at, newest_grade) if newest_grade is not None else ev.updated_at
        out.setdefault(ev.report_id, []).append((ev, last))
    return out


def _row(
    report: Report, team_name: str, since: datetime | None, evaluations: Sequence[_EvaluationActivity]
) -> StalledReportRow:
    with_facts = [(evaluation_facts(ev), last) for ev, last in evaluations]
    counted = [(facts, last) for facts, last in with_facts if counts(facts)]
    pending = [last for facts, last in counted if facts.status != COMPLETED]
    return StalledReportRow(
        report_id=str(report.id),
        report_name=report.name,
        team_id=str(report.team_id),
        team_name=team_name,
        under_evaluation_since=since,
        counted_evaluator_count=len(counted),
        completed_evaluator_count=sum(1 for facts, _ in counted if contributes_grade(facts)),
        oldest_pending_activity_at=min(pending, default=None),
    )


def _staleness(row: StalledReportRow) -> tuple[bool, datetime, datetime]:
    """No pending evaluator first (nobody can move it), then oldest pending activity, then longest waiting."""
    return (
        row.oldest_pending_activity_at is not None,
        row.oldest_pending_activity_at or _EPOCH,
        row.under_evaluation_since or _EPOCH,
    )


async def stalled_reports(db: AsyncSession, exercise_id: uuid.UUID) -> StalledReportsOut:
    """Every ``under_evaluation`` report of the exercise, most stalled first. Access is the route's to check."""
    found = (
        await db.execute(
            select(Report, Team.name)
            .join(Team, Team.id == Report.team_id)
            .where(Report.exercise_id == exercise_id, Report.status == UNDER_EVALUATION)
        )
    ).all()
    policy = await resolve_finalize_policy(db, exercise_id)
    if not found:
        return StalledReportsOut(finalize_policy=policy, reports=[])
    ids = [report.id for report, _ in found]
    since = await _under_evaluation_since(db, ids)
    evaluations = await _evaluations_by_report(db, ids)
    rows = [
        _row(report, team_name, since.get(report.id), evaluations.get(report.id, [])) for report, team_name in found
    ]
    return StalledReportsOut(finalize_policy=policy, reports=sorted(rows, key=_staleness))
