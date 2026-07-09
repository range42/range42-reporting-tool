import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ReportSection(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_section"
    __table_args__ = (UniqueConstraint("report_id", "section_def_id", name="uq_report_section_def"),)

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
    section_def_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("template_section_def.id", ondelete="RESTRICT"), nullable=False
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_plain: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    choice_values: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_writer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    last_edited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    last_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
