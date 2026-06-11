from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.core.permissions import PERMISSION_CATALOGUE
from app.models import RoleDefinition


def _validate_perms(perms: list[str]) -> list[str]:
    invalid = [p for p in perms if p not in PERMISSION_CATALOGUE]
    if invalid:
        raise ValueError(f"unknown permissions: {sorted(invalid)}")
    return perms


class RoleCreate(BaseModel):
    role_key: str
    display_label: str
    description: str | None = None
    permissions: list[str]

    @field_validator("permissions")
    @classmethod
    def _check(cls, v: list[str]) -> list[str]:
        return _validate_perms(v)


class RoleUpdate(BaseModel):
    display_label: str | None = None
    description: str | None = None
    permissions: list[str] | None = None

    @field_validator("permissions")
    @classmethod
    def _check(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _validate_perms(v)


class RoleOut(BaseModel):
    id: str
    role_key: str
    display_label: str
    description: str | None
    permissions: list[str]
    is_system: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, r: RoleDefinition) -> RoleOut:
        return cls(
            id=str(r.id),
            role_key=r.role_key,
            display_label=r.display_label,
            description=r.description,
            permissions=list(r.permissions),
            is_system=r.is_system,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
