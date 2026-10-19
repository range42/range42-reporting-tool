"""approval_section_remark: per-section remarks on one approve/reject decision"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approval_section_remark",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "approval_record_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("approval_record.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "report_section_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("report_section.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("approval_record_id", "report_section_id", name="uq_approval_section_remark"),
    )


def downgrade() -> None:
    op.drop_table("approval_section_remark")
