"""report: add available_at, when a report becomes fillable by its writers"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("report", "available_at")
