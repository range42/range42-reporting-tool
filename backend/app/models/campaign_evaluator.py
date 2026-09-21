import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class CampaignEvaluator(Base, UUIDMixin):
    """Which evaluator(s) cover a campaign, independent of team.

    Resolved against ``TeamEvaluator`` (intersection) at report-submission time to decide who
    actually gets assigned to grade a report — see ``_auto_assign_evaluators``.
    """

    __tablename__ = "campaign_evaluator"
    __table_args__ = (UniqueConstraint("campaign_id", "evaluator_id", name="uq_campaign_evaluator"),)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
    )
    evaluator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
