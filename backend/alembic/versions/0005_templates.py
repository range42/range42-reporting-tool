"""report template tables: report_template, template_section_def"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_template",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lineage_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("metadata", pg.JSONB(), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("lineage_id", "version", name="uq_template_lineage_version"),
    )
    op.create_index("idx_report_template_lineage", "report_template", ["lineage_id"])
    op.create_index("idx_report_template_status_type", "report_template", ["status", "report_type"])

    op.create_table(
        "template_section_def",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "template_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("report_template.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("field_type", sa.String(20), nullable=False),
        sa.Column("char_limit", sa.Integer(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("grade_mode", sa.String(20), nullable=False, server_default=sa.text("'not_graded'")),
        sa.Column("grade_min", sa.Float(), nullable=True),
        sa.Column("grade_max", sa.Float(), nullable=True),
        sa.Column("grade_weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("rubric_criteria", pg.JSONB(), nullable=True),
        sa.Column("evaluation_criteria", sa.Text(), nullable=True),
        sa.Column("choice_config", pg.JSONB(), nullable=True),
        sa.Column("mitre_attack_tags", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("capec_tags", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cwe_tags", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_template_section_template", "template_section_def", ["template_id", "position"])


def downgrade() -> None:
    op.drop_index("idx_template_section_template", table_name="template_section_def")
    op.drop_table("template_section_def")
    op.drop_index("idx_report_template_status_type", table_name="report_template")
    op.drop_index("idx_report_template_lineage", table_name="report_template")
    op.drop_table("report_template")
