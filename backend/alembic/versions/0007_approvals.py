"""approval_record + report.approval_chain + status backstop

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report", sa.Column("approval_chain", pg.JSONB(), nullable=True))

    op.create_table(
        "approval_record",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", pg.UUID(as_uuid=True), sa.ForeignKey("report.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approver_id", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("is_admin_override", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        "ALTER TABLE approval_record ADD CONSTRAINT ck_approval_record_action CHECK (action IN ('approved','rejected'))"
    )
    op.create_index("ix_approval_record_report_id", "approval_record", ["report_id"])
    # At most one approval per (report, step) — concurrency/double-approve guard.
    op.execute(
        "CREATE UNIQUE INDEX uq_approval_record_report_step_approved "
        "ON approval_record (report_id, step) WHERE action = 'approved'"
    )
    # Backstop: the state machine is the sole writer of report.status; this keeps a
    # stray value out of the column even if that invariant is ever violated.
    op.execute(
        "ALTER TABLE report ADD CONSTRAINT ck_report_status CHECK (status IN ('draft','pending_approval','submitted'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE report DROP CONSTRAINT ck_report_status")
    op.execute("DROP INDEX IF EXISTS uq_approval_record_report_step_approved")
    op.drop_index("ix_approval_record_report_id", table_name="approval_record")
    op.drop_table("approval_record")
    op.drop_column("report", "approval_chain")
