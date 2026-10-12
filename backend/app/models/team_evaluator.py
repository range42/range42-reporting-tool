import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class TeamEvaluator(Base, UUIDMixin):
    """Which evaluator(s) watch a team, independent of any campaign.

    Resolved against ``CampaignEvaluator`` (intersection) at report-submission time to decide
    who actually gets assigned to grade a report — see ``_auto_assign_evaluators``.
    """

    __tablename__ = "team_evaluator"
    __table_args__ = (UniqueConstraint("team_id", "evaluator_id", name="uq_team_evaluator"),)

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team.id", ondelete="CASCADE"), nullable=False
    )
    evaluator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
