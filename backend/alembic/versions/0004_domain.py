"""domain tables: exercise, team_type_config, team, team_member, scoring_config"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exercise",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("classification", sa.String(50), nullable=True),
        sa.Column("tlp", sa.String(20), nullable=True),
        sa.Column("classification_caveats", pg.ARRAY(sa.Text()), nullable=True),
        sa.Column("metadata", pg.JSONB(), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "team_type_config",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "exercise_id", pg.UUID(as_uuid=True), sa.ForeignKey("exercise.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("type_key", sa.String(50), nullable=False),
        sa.Column("display_label", sa.String(100), nullable=False),
        sa.Column("default_color", sa.String(7), nullable=True),
        sa.Column("is_visible_to_others", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("exercise_id", "type_key", name="uq_team_type_per_exercise"),
    )
    op.create_table(
        "team",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "exercise_id", pg.UUID(as_uuid=True), sa.ForeignKey("exercise.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("team_type", sa.String(50), nullable=False, server_default=sa.text("'blue'")),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("metadata", pg.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("exercise_id", "name", name="uq_team_name_per_exercise"),
    )
    op.create_table(
        "team_member",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("team_id", pg.UUID(as_uuid=True), sa.ForeignKey("team.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )
    op.create_table(
        "scoring_config",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "exercise_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("exercise.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("show_leaderboard", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("show_per_type_leaderboard", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("teams_see_own_scores", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_team_exercise", "team", ["exercise_id"])
    op.create_index("idx_team_member_team", "team_member", ["team_id"])
    op.create_index("idx_team_member_user", "team_member", ["user_id"])
    op.create_foreign_key(
        "fk_exercise_role_exercise", "exercise_role", "exercise", ["exercise_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("fk_exercise_role_exercise", "exercise_role", type_="foreignkey")
    op.drop_index("idx_team_member_user", table_name="team_member")
    op.drop_index("idx_team_member_team", table_name="team_member")
    op.drop_index("idx_team_exercise", table_name="team")
    op.drop_table("scoring_config")
    op.drop_table("team_member")
    op.drop_table("team")
    op.drop_table("team_type_config")
    op.drop_table("exercise")
