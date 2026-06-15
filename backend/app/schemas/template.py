from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.report_template import ReportTemplate
from app.models.template_section_def import TemplateSectionDef
from app.schemas.domain import _reject_null

KNOWN_REPORT_TYPES = ("sitrep", "cti", "incident", "spot", "custom")
FIELD_TYPES = ("rich_text", "choice")
GRADE_MODES = ("numeric", "pass_fail", "rubric", "not_graded")


def section_invariant_error(
    *,
    field_type: str,
    char_limit: int | None,
    choice_config: dict[str, Any] | None,
    grade_mode: str,
    grade_min: float | None,
    grade_max: float | None,
    rubric_criteria: list[dict[str, Any]] | None,
    grade_weight: float,
) -> str | None:
    """Cross-field section validity. Returns an error message, or None when valid."""
    if field_type not in FIELD_TYPES:
        return f"field_type must be one of {FIELD_TYPES}"
    if grade_mode not in GRADE_MODES:
        return f"grade_mode must be one of {GRADE_MODES}"
    if grade_weight <= 0:
        return "grade_weight must be > 0"
    if field_type == "rich_text":
        if choice_config is not None:
            return "rich_text sections must not have choice_config"
        if char_limit is not None and char_limit < 1:
            return "char_limit must be >= 1"
    else:  # choice
        if char_limit is not None:
            return "choice sections must not have a char_limit"
        if not choice_config:
            return "choice sections require choice_config"
        if choice_config.get("selection") not in ("single", "multiple"):
            return "choice_config.selection must be 'single' or 'multiple'"
        values = choice_config.get("values") or []
        if not values:
            return "choice_config.values must be non-empty"
        codes = [v.get("code") for v in values]
        if any(not c for c in codes):
            return "every choice value needs a code"
        if len(codes) != len(set(codes)):
            return "choice value codes must be unique"
    if grade_mode == "numeric":
        if grade_min is None or grade_max is None or grade_min >= grade_max:
            return "numeric grading requires grade_min < grade_max"
    if grade_mode == "rubric":
        if not rubric_criteria:
            return "rubric grading requires rubric_criteria"
        for c in rubric_criteria:
            if float(c.get("max_score", 0)) <= 0 or float(c.get("weight", 0)) <= 0:
                return "each rubric criterion needs max_score>0 and weight>0"
    if grade_mode in ("pass_fail", "not_graded") and (grade_min is not None or grade_max is not None):
        return f"{grade_mode} grading must not set grade_min/grade_max"
    return None


class SectionBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    field_type: str = "rich_text"
    char_limit: int | None = None
    is_required: bool = True
    grade_mode: str = "not_graded"
    grade_min: float | None = None
    grade_max: float | None = None
    grade_weight: float = 1.0
    rubric_criteria: list[dict[str, Any]] | None = None
    evaluation_criteria: str | None = None
    choice_config: dict[str, Any] | None = None
    mitre_attack_tags: list[str] = Field(default_factory=list)
    capec_tags: list[str] = Field(default_factory=list)
    cwe_tags: list[str] = Field(default_factory=list)


class SectionCreate(SectionBase):
    @model_validator(mode="after")
    def _check(self) -> SectionCreate:
        err = section_invariant_error(
            field_type=self.field_type,
            char_limit=self.char_limit,
            choice_config=self.choice_config,
            grade_mode=self.grade_mode,
            grade_min=self.grade_min,
            grade_max=self.grade_max,
            rubric_criteria=self.rubric_criteria,
            grade_weight=self.grade_weight,
        )
        if err:
            raise ValueError(err)
        return self


class SectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    field_type: str | None = None
    char_limit: int | None = None
    is_required: bool | None = None
    grade_mode: str | None = None
    grade_min: float | None = None
    grade_max: float | None = None
    grade_weight: float | None = None
    rubric_criteria: list[dict[str, Any]] | None = None
    evaluation_criteria: str | None = None
    choice_config: dict[str, Any] | None = None
    mitre_attack_tags: list[str] | None = None
    capec_tags: list[str] | None = None
    cwe_tags: list[str] | None = None

    @field_validator(
        "name",
        "field_type",
        "is_required",
        "grade_mode",
        "grade_weight",
        "mitre_attack_tags",
        "capec_tags",
        "cwe_tags",
        mode="before",
    )
    @classmethod
    def _nn(cls, v: object) -> object:
        return _reject_null(v)


class SectionOut(SectionBase):
    id: str
    template_id: str
    position: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, s: TemplateSectionDef) -> SectionOut:
        return cls(
            id=str(s.id),
            template_id=str(s.template_id),
            position=s.position,
            name=s.name,
            description=s.description,
            field_type=s.field_type,
            char_limit=s.char_limit,
            is_required=s.is_required,
            grade_mode=s.grade_mode,
            grade_min=s.grade_min,
            grade_max=s.grade_max,
            grade_weight=s.grade_weight,
            rubric_criteria=s.rubric_criteria,
            evaluation_criteria=s.evaluation_criteria,
            choice_config=s.choice_config,
            mitre_attack_tags=s.mitre_attack_tags,
            capec_tags=s.capec_tags,
            cwe_tags=s.cwe_tags,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    report_type: str = Field(min_length=1, max_length=50)
    description: str | None = None
    metadata: dict[str, Any] | None = None


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    report_type: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("name", "report_type", mode="before")
    @classmethod
    def _nn(cls, v: object) -> object:
        return _reject_null(v)


class TemplateOut(BaseModel):
    id: str
    lineage_id: str
    version: int
    name: str
    report_type: str
    description: str | None
    status: str
    section_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, t: ReportTemplate, section_count: int) -> TemplateOut:
        return cls(
            id=str(t.id),
            lineage_id=str(t.lineage_id),
            version=t.version,
            name=t.name,
            report_type=t.report_type,
            description=t.description,
            status=t.status,
            section_count=section_count,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )


class TemplateDetailOut(BaseModel):
    id: str
    lineage_id: str
    version: int
    name: str
    report_type: str
    description: str | None
    status: str
    metadata: dict[str, Any] | None
    sections: list[SectionOut]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, t: ReportTemplate, sections: list[TemplateSectionDef]) -> TemplateDetailOut:
        return cls(
            id=str(t.id),
            lineage_id=str(t.lineage_id),
            version=t.version,
            name=t.name,
            report_type=t.report_type,
            description=t.description,
            status=t.status,
            metadata=t.metadata_,
            sections=[SectionOut.from_model(s) for s in sections],
            created_at=t.created_at,
            updated_at=t.updated_at,
        )


class TemplateVersionOut(BaseModel):
    id: str
    version: int
    status: str
    created_at: datetime

    @classmethod
    def from_model(cls, t: ReportTemplate) -> TemplateVersionOut:
        return cls(id=str(t.id), version=t.version, status=t.status, created_at=t.created_at)


class TemplateBundle(BaseModel):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=255)
    report_type: str = Field(min_length=1, max_length=50)
    description: str | None = None
    sections: list[SectionCreate]

    @classmethod
    def from_model(cls, t: ReportTemplate, sections: list[TemplateSectionDef]) -> TemplateBundle:
        return cls(
            schema_version=1,
            name=t.name,
            report_type=t.report_type,
            description=t.description,
            sections=[
                SectionCreate(
                    name=s.name,
                    description=s.description,
                    field_type=s.field_type,
                    char_limit=s.char_limit,
                    is_required=s.is_required,
                    grade_mode=s.grade_mode,
                    grade_min=s.grade_min,
                    grade_max=s.grade_max,
                    grade_weight=s.grade_weight,
                    rubric_criteria=s.rubric_criteria,
                    evaluation_criteria=s.evaluation_criteria,
                    choice_config=s.choice_config,
                    mitre_attack_tags=s.mitre_attack_tags,
                    capec_tags=s.capec_tags,
                    cwe_tags=s.cwe_tags,
                )
                for s in sections
            ],
        )


class ReorderBody(BaseModel):
    ordered_ids: list[str]
