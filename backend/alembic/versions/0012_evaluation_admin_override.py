"""evaluation admin-override/unassign columns

Adds only the deadlock-exit columns, mirroring approval_record's is_admin_override/comment
pattern. ``scoring_config.finalize_policy`` and ``report.grade_version`` are created by 0011.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation",
        sa.Column("finalized_by", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column(
        "evaluation",
        sa.Column("finalize_is_admin_override", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("evaluation", sa.Column("finalize_comment", sa.Text(), nullable=True))
    op.add_column("evaluation", sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "evaluation",
        sa.Column("unassigned_by", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column("evaluation", sa.Column("unassign_reason", sa.Text(), nullable=True))
    # Every gate and aggregate query filters on exactly this shape — partial, not plain.
    op.create_index(
        "ix_evaluation_report_active",
        "evaluation",
        ["report_id"],
        postgresql_where=sa.text("unassigned_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_report_active", table_name="evaluation")
    op.drop_column("evaluation", "unassign_reason")
    op.drop_column("evaluation", "unassigned_by")
    op.drop_column("evaluation", "unassigned_at")
    op.drop_column("evaluation", "finalize_comment")
    op.drop_column("evaluation", "finalize_is_admin_override")
    op.drop_column("evaluation", "finalized_by")
