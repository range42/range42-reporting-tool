"""Lifecycle-event emit seam (ARCHITECTURE §11.3).

WP5 HAS NO WEBHOOKS. There is no ``webhook_config``, no HMAC signer and no delivery engine —
those are WP6 (#53/#54). What this module pins down is the CALL SITE that WP6 will
re-implement: today it builds the payload, writes one audit row and logs one line.

Route handlers must never build an event payload inline. If they do, WP6 becomes a
grep-and-pray refactor across every handler that ever transitioned a report, and any handler
missed silently stops emitting.

D1 EXTENDS TO MACHINES. The payload carries the report-level aggregate and per-SECTION values
only — never per-evaluator rows. A webhook shipping the breakdown would be a peer-visibility
hole with extra steps, and a durable one: the payload outlives the request in an outbox, a
delivery log, and someone else's HTTP endpoint.
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

#: The §11.3 action name. Audit-only in WP5; WP6's outbox reuses the same string.
REPORT_EVALUATED = "event.report_evaluated"

#: W5-4's supersession signal. NOT one of the four v1 events — it exists because a reopen
#: cannot retract an already-delivered ``report.evaluated``, so the only honest option is to
#: announce that a higher grade_version now supersedes it.
REPORT_EVALUATION_REOPENED = "event.report_evaluation_reopened"


def _grade_str(v: Decimal | None) -> str | None:
    """Two decimal places as a STRING, never a float.

    A JSONB float would hand consumers 7.699999999999999 for a grade the database stores as
    7.70, and the payload is the external contract (§12.3) — it does not get to be lossy.
    """
    return None if v is None else f"{v:.2f}"


def _report_identity(report: Report) -> dict[str, str]:
    """The three ids every event payload leads with.

    Shared so the two emitters cannot disagree about what identifies a report. WP6 (#54)
    re-implements this module against an outbox; one identity helper is one thing to port.
    """
    return {
        "exercise_id": str(report.exercise_id),
        "report_id": str(report.id),
        "team_id": str(report.team_id),
    }


async def build_report_evaluated_payload(db: AsyncSession, report: Report) -> dict[str, Any]:
    """The §11.3 ``report.evaluated`` body, plus ``grade_version``.

    ``grade_version`` is ADDITIVE to the documented shape and load-bearing (§9-A8): delivery is
    at-least-once and §11.3 defines no retraction event, so D3's monotonic version is a
    consumer's only way to tell a reopened-and-regraded report from a duplicate delivery of the
    original. Without it, supersession detection is impossible.

    Section values cover the CONTRIBUTING evaluations only — the same L7 set behind
    ``overall_grade`` — so the two halves of one payload cannot disagree.
    ``aggregate_section_grades`` applies that filter from each input's own ``contributes`` flag.
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
    emits nothing. At-least-once delivery tolerates a duplicate; a report that crossed once and
    announced twice is a different bug, and consumers cannot distinguish it from a regrade.

    Runs inside the CALLER'S transaction and never commits — a failure later in the request
    rolls the event back with the transition that caused it. An event announcing a transition
    that did not survive is worse than a missing one.

    WP6 (#54): replace the body with an outbox insert. The signature, the action name and the
    payload builder are the contract; keep all three and every call site keeps working.
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
    """Announce that a previously published grade has been superseded (W5-4).

    NOT a retraction. The contract defines no such event and delivery is at-least-once, so a
    consumer that already holds the original ``report.evaluated`` cannot be told to discard it.
    Carrying both versions lets it work out for itself that what it has is stale.

    THE ADMIN'S REASON IS DELIBERATELY ABSENT. A reopen reason may name a person's absence or
    the quality of their work, and this payload leaves the deployment — it lands in an outbox,
    a delivery log and someone else's HTTP endpoint. The reason stays on the evaluation's audit
    row, which does not travel.

    Per-evaluator rows are absent for the same reason they are absent from ``report.evaluated``:
    evaluator isolation extends to machines.

    Runs inside the CALLER'S transaction and never commits, so an event cannot outlive the
    reopen that caused it.
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
