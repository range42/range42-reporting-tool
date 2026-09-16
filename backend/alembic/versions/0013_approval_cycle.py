"""submission cycle for approvals (recall/reject invalidation)

``report.approval_cycle`` counts submissions; ``approval_record.cycle`` stamps the one an
approval belonged to, so a recalled and resubmitted report can be approved again. Existing rows
backfill to 1.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report", sa.Column("approval_cycle", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column("approval_record", sa.Column("cycle", sa.Integer(), nullable=False, server_default=sa.text("1")))
    # Every approved-steps lookup is (report, cycle) filtered on action — index that shape.
    op.create_index("ix_approval_record_report_cycle", "approval_record", ["report_id", "cycle"])
    # The double-approve guard must block a double approval WITHIN one submission only, so the
    # unique index is cut per cycle rather than on (report, step) for all time.
    op.execute("DROP INDEX IF EXISTS uq_approval_record_report_step_approved")
    op.execute(
        "CREATE UNIQUE INDEX uq_approval_record_report_cycle_step_approved "
        "ON approval_record (report_id, cycle, step) WHERE action = 'approved'"
    )


def downgrade() -> None:
    # LOSSY, UNAVOIDABLY: rows from any cycle other than the report's current one are dropped,
    # or the index below cannot be rebuilt. Take a dump before downgrading a database that has
    # seen a recall.
    op.execute("DELETE FROM approval_record a USING report r WHERE a.report_id = r.id AND a.cycle <> r.approval_cycle")
    op.execute("DROP INDEX IF EXISTS uq_approval_record_report_cycle_step_approved")
    op.execute(
        "CREATE UNIQUE INDEX uq_approval_record_report_step_approved "
        "ON approval_record (report_id, step) WHERE action = 'approved'"
    )
    op.drop_index("ix_approval_record_report_cycle", table_name="approval_record")
    op.drop_column("approval_record", "cycle")
    op.drop_column("report", "approval_cycle")
