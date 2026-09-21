from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.campaign import Campaign
from app.models.campaign_evaluator import CampaignEvaluator
from app.models.report import Report
from app.models.user import User
from app.schemas.domain import _reject_null


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    metadata: dict[str, Any] | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _nn(cls, v: object) -> object:
        return _reject_null(v)


class CampaignReportAdd(BaseModel):
    report_id: str


class CampaignEvaluatorCreate(BaseModel):
    evaluator_id: str


class CampaignEvaluatorOut(BaseModel):
    id: str
    campaign_id: str
    evaluator_id: str
    display_name: str
    email: str
    created_at: datetime

    @classmethod
    def from_row(cls, ce: CampaignEvaluator, u: User) -> CampaignEvaluatorOut:
        return cls(
            id=str(ce.id),
            campaign_id=str(ce.campaign_id),
            evaluator_id=str(u.id),
            display_name=u.display_name,
            email=u.email,
            created_at=ce.created_at,
        )


class CampaignOut(BaseModel):
    id: str
    exercise_id: str
    name: str
    description: str | None
    report_count: int
    created_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, c: Campaign, report_count: int) -> CampaignOut:
        return cls(
            id=str(c.id),
            exercise_id=str(c.exercise_id),
            name=c.name,
            description=c.description,
            report_count=report_count,
            created_by=str(c.created_by),
            created_at=c.created_at,
            updated_at=c.updated_at,
        )


class TimelineEntryOut(BaseModel):
    """One campaign report on the evaluator timeline (two-pane/N-pane feed)."""

    report_id: str
    name: str
    status: str
    team_id: str
    team_name: str
    submitted_at: datetime | None
    due_at: datetime | None
    created_at: datetime

    @classmethod
    def from_models(cls, r: Report, team_name: str) -> TimelineEntryOut:
        return cls(
            report_id=str(r.id),
            name=r.name,
            status=r.status,
            team_id=str(r.team_id),
            team_name=team_name,
            submitted_at=r.submitted_at,
            due_at=r.due_at,
            created_at=r.created_at,
        )
