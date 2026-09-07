"""W5-3 Task 6 — the evaluation transitions, as behaviour rather than table lookups.

``tests/unit/test_state_machine.py`` already asserts which edges ``is_allowed`` permits. What
was missing is what ``transition()`` *does* on the two evaluation targets: it must leave
``submitted_at`` alone, and it must emit exactly one audit row.

Pure by design. ``transition()`` only calls ``add()`` and ``flush()`` on its session, so a stub
stands in for the database and the grading rules stay testable without one.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.models import AuditLog
from app.models.report import Report
from app.services.workflow.state_machine import ALLOWED_TRANSITIONS, InvalidTransition, transition

SUBMITTED_AT = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _StubSession:
    """The narrow slice of AsyncSession that ``transition`` and ``record_audit`` touch."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushes = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1

    @property
    def audit_rows(self) -> list[AuditLog]:
        return [o for o in self.added if isinstance(o, AuditLog)]


def _report(status: str) -> Report:
    return Report(
        id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        name="R",
        status=status,
        submitted_at=SUBMITTED_AT,
    )


async def _transition(report: Report, target: str, action: str) -> _StubSession:
    session = _StubSession()
    await transition(session, report, target_status=target, actor_id=uuid.uuid4(), action=action)  # type: ignore[arg-type]
    return session


async def test_transition_to_under_evaluation_does_not_clear_submitted_at() -> None:
    """Only ``-> draft`` clears it. Losing it here would erase when the team actually delivered."""
    # Arrange
    report = _report("submitted")

    # Act
    await _transition(report, "under_evaluation", "report.evaluation_started")

    # Assert
    assert report.status == "under_evaluation"
    assert report.submitted_at == SUBMITTED_AT


async def test_transition_to_evaluated_does_not_clear_submitted_at() -> None:
    # Arrange
    report = _report("under_evaluation")

    # Act
    await _transition(report, "evaluated", "report.evaluated")

    # Assert
    assert report.status == "evaluated"
    assert report.submitted_at == SUBMITTED_AT


async def test_transition_to_evaluated_records_exactly_one_audit_row() -> None:
    # Arrange
    report = _report("under_evaluation")

    # Act
    session = await _transition(report, "evaluated", "report.evaluated")

    # Assert
    assert len(session.audit_rows) == 1
    assert session.audit_rows[0].action == "report.evaluated"
    assert session.audit_rows[0].resource_id == report.id


async def test_rejected_transition_mutates_nothing_and_writes_no_audit_row() -> None:
    # Arrange: recall after evaluation began is blocked by §7.2.
    report = _report("under_evaluation")
    session = _StubSession()

    # Act / Assert
    with pytest.raises(InvalidTransition):
        await transition(
            session,  # type: ignore[arg-type]
            report,
            target_status="draft",
            actor_id=uuid.uuid4(),
            action="report.recalled",
        )
    assert report.status == "under_evaluation"
    assert report.submitted_at == SUBMITTED_AT
    assert session.added == []


def test_evaluated_only_opens_the_reopen_edge() -> None:
    """W5-1 opened ``evaluated -> under_evaluation`` early for W5-4's reopen.

    Task 6's plan text expected ``evaluated`` to still be closed here and asked for the closure
    to be asserted. It is not closed, deliberately (see the table's own comment), so what is
    pinned instead is that reopen is the ONLY edge out — nothing may reach ``draft`` or
    ``submitted`` from a graded report.
    """
    # Arrange / Act / Assert
    assert ALLOWED_TRANSITIONS["evaluated"] == frozenset({"under_evaluation"})
