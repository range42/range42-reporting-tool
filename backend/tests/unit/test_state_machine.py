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
