from app.schemas.report import KNOWN_REPORT_STATUSES
from app.services.workflow.state_machine import is_allowed


def test_is_allowed_legal_edges() -> None:
    assert is_allowed("draft", "pending_approval")
    assert is_allowed("draft", "submitted")
    assert is_allowed("pending_approval", "submitted")
    assert is_allowed("pending_approval", "draft")
    assert is_allowed("submitted", "draft")


def test_is_allowed_illegal_edges() -> None:
    assert not is_allowed("submitted", "submitted")
    assert not is_allowed("submitted", "pending_approval")
    assert not is_allowed("draft", "draft")
    assert not is_allowed("pending_approval", "pending_approval")
    assert not is_allowed("draft", "evaluated")
    assert not is_allowed("unknown", "submitted")


def test_submitted_to_under_evaluation_is_allowed() -> None:
    assert is_allowed("submitted", "under_evaluation")


def test_under_evaluation_to_evaluated_is_allowed() -> None:
    assert is_allowed("under_evaluation", "evaluated")


def test_evaluated_to_under_evaluation_is_allowed_for_admin_reopen() -> None:
    assert is_allowed("evaluated", "under_evaluation")


def test_under_evaluation_to_draft_is_rejected() -> None:
    assert not is_allowed("under_evaluation", "draft")


def test_evaluated_to_draft_is_rejected() -> None:
    assert not is_allowed("evaluated", "draft")


def test_under_evaluation_to_submitted_is_rejected() -> None:
    assert not is_allowed("under_evaluation", "submitted")


def test_known_report_statuses_covers_the_five_lifecycle_values() -> None:
    assert KNOWN_REPORT_STATUSES == (
        "draft",
        "pending_approval",
        "submitted",
        "under_evaluation",
        "evaluated",
    )
