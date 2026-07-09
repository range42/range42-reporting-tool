import pytest
from pydantic import ValidationError

from app.schemas.report import ReportCreate, SectionAnswerUpdate


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
