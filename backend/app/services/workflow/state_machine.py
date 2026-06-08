"""Report workflow state machine (shape reservation — no impl yet).

SOLE-WRITER CONTRACT: this module is the *only* writer of ``report.status`` and
the *only* writer of the ``audit_log``. Every status transition (e.g. draft ->
submitted -> under_review -> graded) flows through here so that each transition
is validated and an audit_log entry is emitted atomically. No other code path may
mutate ``report.status`` directly. Implementation lands in WP4.
"""


def transition(report_id: str, target_status: str, actor_id: str) -> None:
    """Validate and apply a status transition, writing the audit_log entry.

    Sole writer of ``report.status`` + ``audit_log``. Unimplemented until WP4.
    """
    raise NotImplementedError("workflow state machine lands in WP4")
