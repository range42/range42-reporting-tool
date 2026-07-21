import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, MetadataMixin, TimestampMixin, UUIDMixin


class Campaign(Base, UUIDMixin, TimestampMixin, MetadataMixin):
    """A grouping of reports across teams/time within an exercise (WP3 S10).

    Membership lives in ``campaign_report`` (M2M) — a report may appear in
    several campaigns and campaign membership never mutates the report row.
    """

    __tablename__ = "campaign"
    __table_args__ = (UniqueConstraint("exercise_id", "name", name="uq_campaign_name_per_exercise"),)

    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercise.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
