"""campaign + campaign_report (WP3 S10)

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "exercise_id", pg.UUID(as_uuid=True), sa.ForeignKey("exercise.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("metadata", pg.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("exercise_id", "name", name="uq_campaign_name_per_exercise"),
    )
    op.create_index("ix_campaign_exercise_id", "campaign", ["exercise_id"])

    op.create_table(
        "campaign_report",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "campaign_id", pg.UUID(as_uuid=True), sa.ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("report_id", pg.UUID(as_uuid=True), sa.ForeignKey("report.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("campaign_id", "report_id", name="uq_campaign_report"),
    )
    op.create_index("ix_campaign_report_campaign_id", "campaign_report", ["campaign_id"])
    op.create_index("ix_campaign_report_report_id", "campaign_report", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_report_report_id", table_name="campaign_report")
    op.drop_index("ix_campaign_report_campaign_id", table_name="campaign_report")
    op.drop_table("campaign_report")
    op.drop_index("ix_campaign_exercise_id", table_name="campaign")
    op.drop_table("campaign")
