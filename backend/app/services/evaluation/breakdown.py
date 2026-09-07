"""The per-evaluator breakdown response (WP5 W5-3 Task 10).

THE SINGLE RESPONSE BUILDER used by ``GET …/evaluations``, ``POST …/finalize`` and
``POST …/unassign``. Three hand-rolled builders would be three chances to leak; there is one,
and D1 scoping lives inside it.

It sits in the service layer rather than in either route module because both
``routes/v1/evaluations.py`` and ``routes/v1/evaluation_finalize.py`` need it, and importing it
from either one into the other would close an import cycle.

D1 — the rows are FILTERED BEFORE the Pydantic model is constructed, never excluded during
serialization. A scoping rule expressed as a serializer exclusion is one ``model_dump()`` away
from leaking, and the leak would be silent.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Evaluation, Report, User
from app.schemas.evaluation import BreakdownAggregate, EvaluationBreakdownOut, EvaluationBreakdownRow
from app.services.evaluation.finalize_gate import is_gate_open, resolve_finalize_policy
from app.services.scoring.aggregate import contributes_grade, counts
from app.services.scoring.rollup import evaluation_facts


async def _rows_for(db: AsyncSession, report_id: uuid.UUID) -> list[Evaluation]:
    """Every evaluation of the report, unfiltered and deterministically ordered.

    Unfiltered is deliberate — the admin breakdown must show soft-unassigned rows (L8), and the
    aggregate's denominator is decided by the L7 predicate, not by the SQL.
    """
    return list(
        (await db.execute(select(Evaluation).where(Evaluation.report_id == report_id).order_by(Evaluation.created_at)))
        .scalars()
        .all()
    )


async def _display_names(db: AsyncSession, rows: list[Evaluation]) -> dict[uuid.UUID, str]:
    """Evaluator id -> display name. ADMIN PATH ONLY — never called for an evaluator caller.

    Kept as a separate query rather than a join on ``_rows_for`` so the evaluator path does not
    touch ``user`` at all: there is then no relationship for a later eager-load or a stray
    ``selectinload`` to walk into a peer's name.
    """
    if not rows:
        return {}
    ids = {ev.evaluator_id for ev in rows}
    found = (await db.execute(select(User.id, User.display_name).where(User.id.in_(ids)))).all()
    return {uid: name for uid, name in found}


def _row_out(ev: Evaluation, display_name: str | None) -> EvaluationBreakdownRow:
    return EvaluationBreakdownRow(
        id=str(ev.id),
        evaluator_id=str(ev.evaluator_id),
        evaluator_display_name=display_name,
        status=ev.status,
        overall_grade=ev.overall_grade,
        aggregated_weight=ev.aggregated_weight,
        completed_at=ev.completed_at,
        finalized_by=str(ev.finalized_by) if ev.finalized_by is not None else None,
        finalize_is_admin_override=ev.finalize_is_admin_override,
        unassigned_at=ev.unassigned_at,
        unassign_reason=ev.unassign_reason,
        reopen_count=ev.reopen_count,
    )


def caller_owns_a_row(rows: list[Evaluation], caller: User) -> bool:
    """Whether ``caller`` may see this report's breakdown at all.

    ROW EXISTENCE, NOT THE L7 COUNTED PREDICATE. A soft-unassigned evaluator keeps their row
    (L8) precisely so the dispute trail outlives their removal — gating on ``counts()`` would
    lock them out of the record W5-3 Task 9 preserved for them, at the exact moment a dispute
    needs it. Global Admin bypasses.
    """
    return caller.is_global_admin or any(ev.evaluator_id == caller.id for ev in rows)


async def build(
    db: AsyncSession,
    report: Report,
    caller: User,
    *,
    exercise_id: uuid.UUID,
) -> EvaluationBreakdownOut:
    """Build the D1-scoped breakdown. Caller access is the route's to check, not this builder's.

    The aggregate is computed over EVERY row (the L7 predicate decides what counts), then the
    rows themselves are narrowed to the caller. That order is what lets an evaluator read an
    honest aggregate over N evaluators while seeing only their own line.
    """
    rows = await _rows_for(db, report.id)
    facts = [evaluation_facts(ev) for ev in rows]
    counted = [f for f in facts if counts(f)]

    mode = await resolve_finalize_policy(db, exercise_id)
    aggregate = BreakdownAggregate(
        overall_grade=report.overall_grade,
        grade_version=report.grade_version,
        counted_evaluator_count=len(counted),
        completed_evaluator_count=sum(1 for f in counted if contributes_grade(f)),
        aggregated_weight_total=sum((f.aggregated_weight for f in counted), Decimal("0")),
    )

    visible = rows if caller.is_global_admin else [ev for ev in rows if ev.evaluator_id == caller.id]
    names = await _display_names(db, visible) if caller.is_global_admin else {}
    return EvaluationBreakdownOut(
        report_id=str(report.id),
        report_status=report.status,
        finalize_policy=mode,
        finalize_gate_satisfied=is_gate_open(facts, mode),
        aggregate=aggregate,
        evaluations=[_row_out(ev, names.get(ev.evaluator_id)) for ev in visible],
    )
