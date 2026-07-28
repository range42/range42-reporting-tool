import pytest
from pydantic import ValidationError

from app.schemas.report import ApprovalChainEntry, ReportCreate, SectionAnswerUpdate


def test_report_create_requires_template_team_name() -> None:
    with pytest.raises(ValidationError):
        ReportCreate(name="x")  # missing template_id/team_id


def test_section_answer_update_discriminates_rich_text() -> None:
    m = SectionAnswerUpdate(version=3, body={"kind": "rich_text", "content": "<p>hi</p>"})
    assert m.body.kind == "rich_text"
    assert m.version == 3


def test_section_answer_update_discriminates_choice() -> None:
    m = SectionAnswerUpdate(version=1, body={"kind": "choice", "choice_values": ["a", "b"]})
    assert m.body.kind == "choice"
    assert m.body.choice_values == ["a", "b"]


def test_section_answer_update_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        SectionAnswerUpdate(version=1, body={"kind": "nope"})


def test_approval_chain_entry_requires_exactly_one_subject() -> None:
    with pytest.raises(ValidationError):
        ApprovalChainEntry(role_key="team_approver", user_id="u1")  # both
    with pytest.raises(ValidationError):
        ApprovalChainEntry()  # neither
    assert ApprovalChainEntry(role_key="team_approver").required is True
    assert ApprovalChainEntry(user_id="u1", required=False).required is False


def test_report_create_rejects_empty_chain() -> None:
    with pytest.raises(ValidationError):
        ReportCreate(template_id="t", team_id="tm", name="R", approval_chain=[])


def test_report_create_accepts_valid_chain() -> None:
    m = ReportCreate(
        template_id="t",
        team_id="tm",
        name="R",
        approval_chain=[{"role_key": "team_approver"}, {"user_id": "u1", "required": False}],
    )
    assert m.approval_chain is not None
    assert len(m.approval_chain) == 2
