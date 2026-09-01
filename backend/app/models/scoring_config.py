import uuid

from sqlalchemy import Boolean, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ScoringConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scoring_config"

    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercise.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    show_leaderboard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    show_per_type_leaderboard: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    teams_see_own_scores: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # G-6: the all_must_finalize / any_can_finalize field ARCHITECTURE §4.2's aggregation rule
    # references but never declares. Created + defaulted in W5-1; CONSUMED BY W5-3.
    finalize_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="all_must_finalize", server_default=text("'all_must_finalize'")
    )
