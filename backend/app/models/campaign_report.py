import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class CampaignReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "campaign_report"
    __table_args__ = (UniqueConstraint("campaign_id", "report_id", name="uq_campaign_report"),)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
