"""Lifecycle-event emit seam.

THERE ARE NO WEBHOOKS YET: no ``webhook_config``, no HMAC signer, no delivery engine. This
module is the call site a delivery implementation will replace; today it builds the payload,
writes one audit row and logs one line.

Route handlers must never build an event payload inline, or a handler that is missed later
silently stops emitting.

EVALUATOR ISOLATION EXTENDS TO MACHINES. The payload carries the report-level aggregate and
per-SECTION values only — never per-evaluator rows. The payload outlives the request in an
outbox, a delivery log, and someone else's HTTP endpoint.
"""

from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.models import Report
from app.services.scoring.rollup import load_evaluation_inputs
from app.services.scoring.timeline import aggregate_section_grades

logger = structlog.get_logger(__name__)

#: The action name. Audit-only today; a delivery outbox reuses the same string.
REPORT_EVALUATED = "event.report_evaluated"

#: Supersession signal: a reopen cannot retract an already-delivered ``report.evaluated``, so
#: it announces that a higher grade_version now supersedes it.
REPORT_EVALUATION_REOPENED = "event.report_evaluation_reopened"


def _grade_str(v: Decimal | None) -> str | None:
    """Two decimal places as a STRING, never a float.

    A JSONB float would hand consumers 7.699999999999999 for a stored 7.70, and the payload is
    an external contract.
    """
    return None if v is None else f"{v:.2f}"


def _report_identity(report: Report) -> dict[str, str]:
    """The three ids every event payload leads with.

    Shared so the two emitters cannot disagree about what identifies a report.
    """
    return {
        "exercise_id": str(report.exercise_id),
        "report_id": str(report.id),
        "team_id": str(report.team_id),
    }


async def build_report_evaluated_payload(db: AsyncSession, report: Report) -> dict[str, Any]:
    """The ``report.evaluated`` body, plus ``grade_version``.

    ``grade_version`` is additive to the documented shape and load-bearing: delivery is
    at-least-once and there is no retraction event, so the monotonic version is a consumer's
    only way to tell a reopened-and-regraded report from a duplicate delivery.

    Section values cover the CONTRIBUTING evaluations only — the same set behind
    ``overall_grade`` — so the two halves of one payload cannot disagree.
    """
    inputs = await load_evaluation_inputs(db, report)
    return {
        **_report_identity(report),
        "overall_grade": _grade_str(report.overall_grade),
        "grade_version": report.grade_version,
        "section_grades": [
            {
                "section_def_id": s.section_def_id,
                "name": s.name,
                "grade": _grade_str(s.grade),
                "weight": _grade_str(s.weight),
            }
            for s in aggregate_section_grades(inputs)
        ],
    }


async def emit_report_evaluated(db: AsyncSession, report: Report) -> dict[str, Any]:
    """Emit ``report.evaluated`` for a report that has just become ``evaluated``.

    ONE CALLER, ONE CROSSING: ``_settle_finalize_gate`` invokes this only on the
    ``under_evaluation -> evaluated`` edge, so a second finalize on an already-evaluated report
    emits nothing.

    Runs inside the CALLER'S transaction and never commits, so an event cannot announce a
    transition that did not survive.

    A delivery implementation replaces the body with an outbox insert; the signature, the
    action name and the payload builder are the contract.
    """
    payload = await build_report_evaluated_payload(db, report)
    await record_audit(
        db,
        user_id=None,  # a system event: the actor is on the transition's own audit row
        action=REPORT_EVALUATED,
        resource_type="report",
        resource_id=report.id,
        details=payload,
        ip=None,
    )
    logger.info(REPORT_EVALUATED, report_id=str(report.id), grade_version=report.grade_version)
    return payload


async def emit_report_evaluation_reopened(
    db: AsyncSession, report: Report, *, superseded_grade_version: int
) -> dict[str, Any]:
    """Announce that a previously published grade has been superseded.

    NOT a retraction: the contract defines no such event and delivery is at-least-once, so
    carrying both versions is how a consumer works out that what it holds is stale.

    THE ADMIN'S REASON IS DELIBERATELY ABSENT. A reopen reason may name a person's absence or
    the quality of their work, and this payload leaves the deployment. The reason stays on the
    evaluation's audit row, which does not travel.

    Per-evaluator rows are absent for the same reason they are absent from ``report.evaluated``:
    evaluator isolation extends to machines.

    Runs inside the CALLER'S transaction and never commits.
    """
    payload = {
        **_report_identity(report),
        "grade_version": report.grade_version,
        "superseded_grade_version": superseded_grade_version,
    }
    await record_audit(
        db,
        user_id=None,  # a system event: the actor is on the reopen's own audit row
        action=REPORT_EVALUATION_REOPENED,
        resource_type="report",
        resource_id=report.id,
        details=payload,
        ip=None,
    )
    logger.info(REPORT_EVALUATION_REOPENED, **payload)
    return payload
