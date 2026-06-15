import uuid
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class TemplateSectionDef(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "template_section_def"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_template.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    char_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    grade_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_graded", server_default=text("'not_graded'")
    )
    grade_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default=text("1.0"))
    rubric_criteria: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    evaluation_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    choice_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    mitre_attack_tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    capec_tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    cwe_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
