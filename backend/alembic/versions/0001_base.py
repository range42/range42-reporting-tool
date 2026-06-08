"""base schema_meta table"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schema_meta",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.String(length=255), nullable=False),
    )
    op.execute("INSERT INTO schema_meta (key, value) VALUES ('skeleton', 'ok')")


def downgrade() -> None:
    op.drop_table("schema_meta")
