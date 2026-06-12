import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, MetadataMixin, TimestampMixin, UUIDMixin


class Team(Base, UUIDMixin, TimestampMixin, MetadataMixin):
    __tablename__ = "team"
    __table_args__ = (UniqueConstraint("exercise_id", "name", name="uq_team_name_per_exercise"),)

    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercise.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # team_type: soft reference to team_type_config.type_key — no DB FK because
    # team_type_config uniqueness is composite (exercise_id, type_key); a single-
    # column FK can't express it. Validated at the service layer (route handlers).
    team_type: Mapped[str] = mapped_column(String(50), nullable=False, default="blue", server_default=text("'blue'"))
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
