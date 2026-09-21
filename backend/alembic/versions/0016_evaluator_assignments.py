"""team_evaluator + campaign_evaluator: two independent M2M assignments resolved by
intersection at report-submission time (see reports.py::_auto_assign_evaluators)"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_evaluator",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("team_id", pg.UUID(as_uuid=True), sa.ForeignKey("team.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "evaluator_id", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("team_id", "evaluator_id", name="uq_team_evaluator"),
    )
    op.create_index("ix_team_evaluator_team_id", "team_evaluator", ["team_id"])

    op.create_table(
        "campaign_evaluator",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "campaign_id", pg.UUID(as_uuid=True), sa.ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "evaluator_id", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("campaign_id", "evaluator_id", name="uq_campaign_evaluator"),
    )
    op.create_index("ix_campaign_evaluator_campaign_id", "campaign_evaluator", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_evaluator_campaign_id", table_name="campaign_evaluator")
    op.drop_table("campaign_evaluator")
    op.drop_index("ix_team_evaluator_team_id", table_name="team_evaluator")
    op.drop_table("team_evaluator")
