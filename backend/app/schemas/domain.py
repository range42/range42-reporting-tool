from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models import Exercise, ExerciseRole, Team, TeamMember, TeamTypeConfig, User

ExerciseStatus = Literal["draft", "active", "archived"]


def _reject_null(v: object) -> object:
    if v is None:
        raise ValueError("field may not be null")
    return v


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    classification: str | None = None
    tlp: str | None = None
    classification_caveats: list[str] | None = None
    metadata: dict[str, Any] | None = None


class ExerciseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: ExerciseStatus | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    classification: str | None = None
    tlp: str | None = None
    classification_caveats: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("name", "status", mode="before")
    @classmethod
    def _nn(cls, v: object) -> object:
        return _reject_null(v)


class ExerciseOut(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    starts_at: datetime | None
    ends_at: datetime | None
    classification: str | None
    tlp: str | None
    classification_caveats: list[str] | None
    metadata: dict[str, Any] | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, ex: Exercise) -> ExerciseOut:
        return cls(
            id=str(ex.id),
            name=ex.name,
            description=ex.description,
            status=ex.status,
            starts_at=ex.starts_at,
            ends_at=ex.ends_at,
            classification=ex.classification,
            tlp=ex.tlp,
            classification_caveats=ex.classification_caveats,
            metadata=ex.metadata_,
            created_by=str(ex.created_by),
            created_at=ex.created_at,
            updated_at=ex.updated_at,
        )


class TeamTypeConfigCreate(BaseModel):
    type_key: str
    display_label: str
    default_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_visible_to_others: bool = True


class TeamTypeConfigUpdate(BaseModel):
    display_label: str | None = None
    default_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_visible_to_others: bool | None = None

    @field_validator("display_label", mode="before")
    @classmethod
    def _nn(cls, v: object) -> object:
        return _reject_null(v)


class TeamTypeConfigOut(BaseModel):
    id: str
    exercise_id: str
    type_key: str
    display_label: str
    default_color: str | None
    is_visible_to_others: bool

    @classmethod
    def from_model(cls, t: TeamTypeConfig) -> TeamTypeConfigOut:
        return cls(
            id=str(t.id),
            exercise_id=str(t.exercise_id),
            type_key=t.type_key,
            display_label=t.display_label,
            default_color=t.default_color,
            is_visible_to_others=t.is_visible_to_others,
        )


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    team_type: str
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    metadata: dict[str, Any] | None = None


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    team_type: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    metadata: dict[str, Any] | None = None

    @field_validator("name", "team_type", mode="before")
    @classmethod
    def _nn(cls, v: object) -> object:
        return _reject_null(v)


class TeamMemberOut(BaseModel):
    id: str
    user_id: str
    display_name: str
    email: str
    created_at: datetime

    @classmethod
    def from_row(cls, m: TeamMember, u: User) -> TeamMemberOut:
        return cls(
            id=str(m.id),
            user_id=str(u.id),
            display_name=u.display_name,
            email=u.email,
            created_at=m.created_at,
        )


class MeCapabilitiesOut(BaseModel):
    """The caller's own capabilities within an exercise — drives coarse FE route guards."""

    is_global_admin: bool
    capabilities: list[str]


class TeamOut(BaseModel):
    id: str
    exercise_id: str
    name: str
    team_type: str
    color: str | None
    metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    members: list[TeamMemberOut] | None = None

    @classmethod
    def from_model(cls, t: Team, members: list[TeamMemberOut] | None = None) -> TeamOut:
        return cls(
            id=str(t.id),
            exercise_id=str(t.exercise_id),
            name=t.name,
            team_type=t.team_type,
            color=t.color,
            metadata=t.metadata_,
            created_at=t.created_at,
            updated_at=t.updated_at,
            members=members,
        )


class TeamMemberCreate(BaseModel):
    user_id: str


class TeamMemberRowOut(BaseModel):
    id: str
    team_id: str
    user_id: str
    created_at: datetime

    @classmethod
    def from_model(cls, m: TeamMember) -> TeamMemberRowOut:
        return cls(id=str(m.id), team_id=str(m.team_id), user_id=str(m.user_id), created_at=m.created_at)


class ExerciseRoleCreate(BaseModel):
    user_id: str
    role_key: str


class ExerciseRoleOut(BaseModel):
    id: str
    exercise_id: str
    user_id: str
    role_key: str
    created_at: datetime

    @classmethod
    def from_model(cls, r: ExerciseRole) -> ExerciseRoleOut:
        return cls(
            id=str(r.id),
            exercise_id=str(r.exercise_id),
            user_id=str(r.user_id),
            role_key=r.role_key,
            created_at=r.created_at,
        )
