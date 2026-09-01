"""Report workflow state machine (WP4).

SOLE-WRITER CONTRACT: this module is the *only* writer of ``report.status`` and
the *only* place that emits an ``audit_log`` row per status transition. Every
transition (draft -> pending_approval -> submitted, plus reject/recall -> draft)
flows through ``transition`` so it is validated and audited atomically. No other
code path may mutate ``report.status`` directly.

G-5: the ``approved`` enum value is intentionally NOT a ``report.status`` — it
lives only in ``approval_record.action``. A multi-step chain stays in
``pending_approval`` until all required steps are approved, then goes straight to
``submitted``.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.models.report import Report

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"pending_approval", "submitted"}),
    "pending_approval": frozenset({"submitted", "draft"}),
    "submitted": frozenset({"draft", "under_evaluation"}),
    # WP5: evaluation lifecycle. under_evaluation/evaluated never return to draft — a
    # graded report is reworked by reopening the evaluation (W5-4), not by un-submitting.
    "under_evaluation": frozenset({"evaluated"}),
    # §6.8 POST /evaluations/{id}/reopen (Global Admin only, W5-4). Not in §7.2's table — see A3.
    "evaluated": frozenset({"under_evaluation"}),
}


class InvalidTransition(Exception):
    """Raised when ``current -> target`` is not an allowed status transition."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid transition {current!r} -> {target!r}")


def is_allowed(current: str, target: str) -> bool:
    """Whether ``current -> target`` is a legal report-status transition (pure)."""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


async def transition(
    db: AsyncSession,
    report: Report,
    *,
    target_status: str,
    actor_id: uuid.UUID,
    action: str,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Apply a validated status transition and emit exactly one audit row.

    Raises :class:`InvalidTransition` *before* any mutation, so a rejected
    transition leaves ``report`` untouched and writes no audit row. Sets
    ``submitted_at`` to now on ``->submitted`` and clears it on ``->draft``
    (reject/recall return the report to a clean draft).
    """
    if not is_allowed(report.status, target_status):
        raise InvalidTransition(report.status, target_status)
    report.status = target_status
    if target_status == "submitted":
        report.submitted_at = datetime.now(UTC)
    elif target_status == "draft":
        report.submitted_at = None
    await db.flush()
    await record_audit(
        db,
        user_id=actor_id,
        action=action,
        resource_type="report",
        resource_id=report.id,
        details=details,
        ip=ip,
    )
