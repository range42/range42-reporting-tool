"""evaluation + section_grade + grade rollup columns (WP5 W5-1)

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- evaluation -------------------------------------------------------
    op.create_table(
        "evaluation",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", pg.UUID(as_uuid=True), sa.ForeignKey("report.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evaluator_id", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'assigned'")),
        sa.Column("overall_feedback", sa.Text(), nullable=True),
        sa.Column("overall_grade", sa.Numeric(5, 2), nullable=True),
        sa.Column("aggregated_weight", sa.Numeric(3, 2), nullable=False, server_default=sa.text("1.0")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopen_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("assigned_by", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("report_id", "evaluator_id", name="uq_evaluation_report_evaluator"),
    )
    op.create_index("ix_evaluation_report_id", "evaluation", ["report_id"])
    op.create_index("ix_evaluation_evaluator_id", "evaluation", ["evaluator_id"])
    op.execute(
        "ALTER TABLE evaluation ADD CONSTRAINT ck_evaluation_status "
        "CHECK (status IN ('assigned','in_progress','completed'))"
    )
    op.execute("ALTER TABLE evaluation ADD CONSTRAINT ck_evaluation_aggregated_weight CHECK (aggregated_weight > 0)")

    # --- section_grade ----------------------------------------------------
    op.create_table(
        "section_grade",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "evaluation_id", pg.UUID(as_uuid=True), sa.ForeignKey("evaluation.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "report_section_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("report_section.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("grade", sa.Numeric(5, 2), nullable=True),
        sa.Column("pass_fail_result", sa.Boolean(), nullable=True),
        sa.Column("rubric_scores", pg.JSONB(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("graded_by", pg.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("evaluation_id", "report_section_id", name="uq_section_grade_eval_section"),
    )
    op.create_index("ix_section_grade_evaluation_id", "section_grade", ["evaluation_id"])
    op.create_index("ix_section_grade_report_section_id", "section_grade", ["report_section_id"])
    # Backstop: at most one non-numeric grading channel populated per row
    # (mirrors ck_report_section_shape's "forbid the likely accident" approach).
    op.execute(
        "ALTER TABLE section_grade ADD CONSTRAINT ck_section_grade_shape "
        "CHECK (pass_fail_result IS NULL OR rubric_scores IS NULL)"
    )

    # --- report: A7 rollup targets + E3 grade_version ---------------------
    op.add_column("report", sa.Column("overall_feedback", sa.Text(), nullable=True))
    op.add_column("report", sa.Column("overall_grade", sa.Numeric(5, 2), nullable=True))
    op.add_column(
        "report",
        sa.Column("overall_grade_is_manual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("report", sa.Column("grade_version", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.execute("ALTER TABLE report ADD CONSTRAINT ck_report_grade_version CHECK (grade_version >= 0)")

    # --- report status backstop: two new lifecycle values (0007 created this) ---
    op.execute("ALTER TABLE report DROP CONSTRAINT ck_report_status")
    op.execute(
        "ALTER TABLE report ADD CONSTRAINT ck_report_status CHECK (status IN "
        "('draft','pending_approval','submitted','under_evaluation','evaluated'))"
    )

    # --- G-6: scoring_config.finalize_policy ------------------------------
    op.add_column(
        "scoring_config",
        sa.Column("finalize_policy", sa.String(20), nullable=False, server_default=sa.text("'all_must_finalize'")),
    )
    op.execute(
        "ALTER TABLE scoring_config ADD CONSTRAINT ck_scoring_config_finalize_policy "
        "CHECK (finalize_policy IN ('all_must_finalize','any_can_finalize'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scoring_config DROP CONSTRAINT ck_scoring_config_finalize_policy")
    op.drop_column("scoring_config", "finalize_policy")
    # The pre-WP5 constraint has no room for the evaluation statuses, so any row still holding
    # one must be normalized before it is re-added. Downgrade is dev/test-only (ARCHITECTURE
    # §9.7) and this step is lossy by design: 'submitted' is the state those rows came from.
    # Without it the integration fixture's per-test `downgrade base` fails as soon as any test
    # drives a report into under_evaluation/evaluated.
    op.execute("UPDATE report SET status = 'submitted' WHERE status IN ('under_evaluation','evaluated')")
    op.execute("ALTER TABLE report DROP CONSTRAINT ck_report_status")
    op.execute(
        "ALTER TABLE report ADD CONSTRAINT ck_report_status CHECK (status IN ('draft','pending_approval','submitted'))"
    )
    op.execute("ALTER TABLE report DROP CONSTRAINT ck_report_grade_version")
    op.drop_column("report", "grade_version")
    op.drop_column("report", "overall_grade_is_manual")
    op.drop_column("report", "overall_grade")
    op.drop_column("report", "overall_feedback")
    op.drop_index("ix_section_grade_report_section_id", table_name="section_grade")
    op.drop_index("ix_section_grade_evaluation_id", table_name="section_grade")
    op.drop_table("section_grade")
    op.drop_index("ix_evaluation_evaluator_id", table_name="evaluation")
    op.drop_index("ix_evaluation_report_id", table_name="evaluation")
    op.drop_table("evaluation")
