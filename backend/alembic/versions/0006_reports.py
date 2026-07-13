"""report + report_section

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "exercise_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("exercise.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", pg.UUID(as_uuid=True), sa.ForeignKey("team.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "template_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("report_template.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("template_version_at_creation", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("writer_notes", sa.Text(), nullable=True),
        sa.Column("assigned_writer_id", pg.UUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("metadata", pg.JSONB(), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_report_exercise_id", "report", ["exercise_id"])
    op.create_index("ix_report_team_id", "report", ["team_id"])
    op.create_index("ix_report_status", "report", ["status"])

    op.create_table(
        "report_section",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", pg.UUID(as_uuid=True), sa.ForeignKey("report.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "section_def_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("template_section_def.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_plain", sa.Text(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("choice_values", pg.ARRAY(sa.Text()), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("assigned_writer_id", pg.UUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_edited_by", pg.UUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("last_edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("report_id", "section_def_id", name="uq_report_section_def"),
    )
    op.execute(
        "ALTER TABLE report_section ADD CONSTRAINT ck_report_section_shape "
        "CHECK ( choice_values IS NULL OR (content IS NULL AND content_plain IS NULL AND char_count = 0) )"
    )


def downgrade() -> None:
    op.drop_table("report_section")
    op.drop_index("ix_report_status", table_name="report")
    op.drop_index("ix_report_team_id", table_name="report")
    op.drop_index("ix_report_exercise_id", table_name="report")
    op.drop_table("report")
