from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.approval_record import ApprovalRecord
from app.models.report import Report
from app.models.report_section import ReportSection
from app.models.template_section_def import TemplateSectionDef
from app.schemas.domain import _reject_null
from app.schemas.section_content import SectionBody

KNOWN_REPORT_STATUSES = ("draft", "pending_approval", "submitted", "under_evaluation", "evaluated")


class ApprovalChainEntry(BaseModel):
    """One ordered step of a multi-step approval chain (ARCHITECTURE §7).

    Exactly one of ``role_key``/``user_id`` identifies who may approve the step.
    ``required`` steps must all be approved before the report leaves
    ``pending_approval``; optional steps do not gate finalization.
    """

    role_key: str | None = None
    user_id: str | None = None
    required: bool = True

    @model_validator(mode="after")
    def _exactly_one_subject(self) -> ApprovalChainEntry:
        if (self.role_key is None) == (self.user_id is None):
            raise ValueError("exactly one of role_key or user_id must be set")
        return self


def _reject_empty_chain(v: list[ApprovalChainEntry] | None) -> list[ApprovalChainEntry] | None:
    if v is not None and len(v) == 0:
        raise ValueError("approval_chain must be a non-empty list or null")
    return v


class ReportCreate(BaseModel):
    template_id: str
    team_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    due_at: datetime | None = None
    approval_required: bool = False
    approval_chain: list[ApprovalChainEntry] | None = None
    assigned_writer_id: str | None = None

    _no_empty_chain = field_validator("approval_chain")(_reject_empty_chain)


class ReportUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    due_at: datetime | None = None
    approval_required: bool | None = None
    approval_chain: list[ApprovalChainEntry] | None = None
    assigned_writer_id: str | None = None

    @field_validator("name", "approval_required", mode="before")
    @classmethod
    def _nn(cls, v: object) -> object:
        return _reject_null(v)

    _no_empty_chain = field_validator("approval_chain")(_reject_empty_chain)


class ApproveRequest(BaseModel):
    # step/on_behalf_of drive multi-step chains (#38) and admin override (#39);
    # ignored on the single-step path.
    step: int | None = Field(default=None, ge=1)
    on_behalf_of: str | None = None
    comment: str | None = None


class RejectRequest(BaseModel):
    comment: str = Field(min_length=1)
    step: int | None = Field(default=None, ge=1)


class RecallRequest(BaseModel):
    comment: str | None = None


class ApprovalRecordOut(BaseModel):
    id: str
    report_id: str
    approver_id: str
    step: int
    action: str
    is_admin_override: bool
    comment: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, r: ApprovalRecord) -> ApprovalRecordOut:
        return cls(
            id=str(r.id),
            report_id=str(r.report_id),
            approver_id=str(r.approver_id),
            step=r.step,
            action=r.action,
            is_admin_override=r.is_admin_override,
            comment=r.comment,
            created_at=r.created_at,
        )


class SectionAnswerUpdate(BaseModel):
    version: int = Field(ge=1)
    body: SectionBody


class ReportSectionOut(BaseModel):
    # answer fields
    id: str
    report_id: str
    section_def_id: str
    content: str | None
    content_plain: str | None
    char_count: int
    choice_values: list[str] | None
    version: int
    last_edited_by: str | None
    last_edited_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # writer-facing def fields (evaluator fields deliberately excluded)
    name: str
    description: str | None
    field_type: str
    position: int
    char_limit: int | None
    is_required: bool
    choice_config: dict[str, Any] | None

    @classmethod
    def from_models(cls, s: ReportSection, d: TemplateSectionDef) -> ReportSectionOut:
        return cls(
            id=str(s.id),
            report_id=str(s.report_id),
            section_def_id=str(s.section_def_id),
            content=s.content,
            content_plain=s.content_plain,
            char_count=s.char_count,
            choice_values=s.choice_values,
            version=s.version,
            last_edited_by=str(s.last_edited_by) if s.last_edited_by else None,
            last_edited_at=s.last_edited_at,
            created_at=s.created_at,
            updated_at=s.updated_at,
            name=d.name,
            description=d.description,
            field_type=d.field_type,
            position=s.position,
            char_limit=d.char_limit,
            is_required=d.is_required,
            choice_config=_writer_choice_config(d.choice_config),
        )


def _writer_choice_config(cfg: dict[str, Any] | None) -> dict[str, Any] | None:
    """Active values only, sorted by (position, label) — never expose deprecated entries to writers."""
    if not cfg:
        return cfg
    values = [v for v in cfg.get("values", []) if not v.get("deprecated_at")]
    values.sort(key=lambda v: (v.get("position", 0), v.get("label", "")))
    return {**cfg, "values": values}


class ReportOut(BaseModel):
    id: str
    exercise_id: str
    team_id: str
    template_id: str
    template_version_at_creation: int
    name: str
    description: str | None
    status: str
    approval_required: bool
    due_at: datetime | None
    submitted_at: datetime | None
    assigned_writer_id: str | None
    approval_chain: list[dict[str, Any]] | None
    section_count: int
    can_approve: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, r: Report, section_count: int, *, can_approve: bool = False) -> ReportOut:
        return cls(
            id=str(r.id),
            exercise_id=str(r.exercise_id),
            team_id=str(r.team_id),
            template_id=str(r.template_id),
            template_version_at_creation=r.template_version_at_creation,
            name=r.name,
            description=r.description,
            status=r.status,
            approval_required=r.approval_required,
            due_at=r.due_at,
            submitted_at=r.submitted_at,
            assigned_writer_id=str(r.assigned_writer_id) if r.assigned_writer_id else None,
            approval_chain=r.approval_chain,
            section_count=section_count,
            can_approve=can_approve,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )


class ReportDetailOut(BaseModel):
    id: str
    exercise_id: str
    team_id: str
    template_id: str
    template_version_at_creation: int
    name: str
    description: str | None
    status: str
    approval_required: bool
    due_at: datetime | None
    submitted_at: datetime | None
    assigned_writer_id: str | None
    writer_notes: str | None
    approval_chain: list[dict[str, Any]] | None
    approval_records: list[ApprovalRecordOut]
    metadata: dict[str, Any] | None
    sections: list[ReportSectionOut]
    can_approve: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_models(
        cls,
        r: Report,
        pairs: list[tuple[ReportSection, TemplateSectionDef]],
        approval_records: list[ApprovalRecord] | None = None,
        *,
        can_approve: bool = False,
    ) -> ReportDetailOut:
        return cls(
            id=str(r.id),
            exercise_id=str(r.exercise_id),
            team_id=str(r.team_id),
            template_id=str(r.template_id),
            template_version_at_creation=r.template_version_at_creation,
            name=r.name,
            description=r.description,
            status=r.status,
            approval_required=r.approval_required,
            due_at=r.due_at,
            submitted_at=r.submitted_at,
            assigned_writer_id=str(r.assigned_writer_id) if r.assigned_writer_id else None,
            writer_notes=r.writer_notes,
            approval_chain=r.approval_chain,
            approval_records=[ApprovalRecordOut.from_model(a) for a in (approval_records or [])],
            metadata=r.metadata_,
            sections=[ReportSectionOut.from_models(s, d) for s, d in pairs],
            can_approve=can_approve,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
