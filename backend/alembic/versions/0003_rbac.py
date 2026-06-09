"""rbac tables: role_definition, exercise_role"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role_definition",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("role_key", sa.String(100), nullable=False, unique=True),
        sa.Column("display_label", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("permissions", pg.JSONB(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "exercise_role",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # exercise_id FK to `exercise` is added in 0004 (Phase D) once the table exists.
        sa.Column("exercise_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_key", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("exercise_id", "user_id", "role_key", name="uq_exercise_role"),
    )
    op.create_index("idx_exercise_role_lookup", "exercise_role", ["exercise_id", "user_id"])


def downgrade() -> None:
    op.drop_index("idx_exercise_role_lookup", table_name="exercise_role")
    op.drop_table("exercise_role")
    op.drop_table("role_definition")
