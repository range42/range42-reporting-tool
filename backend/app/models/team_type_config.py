import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class TeamTypeConfig(Base, UUIDMixin):
    __tablename__ = "team_type_config"
    __table_args__ = (UniqueConstraint("exercise_id", "type_key", name="uq_team_type_per_exercise"),)

    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercise.id", ondelete="CASCADE"), nullable=False
    )
    type_key: Mapped[str] = mapped_column(String(50), nullable=False)
    display_label: Mapped[str] = mapped_column(String(100), nullable=False)
    default_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_visible_to_others: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
