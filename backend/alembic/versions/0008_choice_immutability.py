"""choice-code immutability trigger (WP3 S4 backstop)

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backstop for the app-layer 409-if-referenced guard: a choice code that any
    # report_section answer references must stay present in choice_config.values
    # (deprecation keeps the code; only removal/rename is blocked). Section-def
    # DELETEs are already blocked by the report_section FK (ondelete=RESTRICT).
    op.execute(
        """
        CREATE FUNCTION choice_code_immutability() RETURNS trigger AS $$
        DECLARE
          missing text;
        BEGIN
          SELECT refs.code INTO missing
          FROM (
            SELECT DISTINCT unnest(rs.choice_values) AS code
            FROM report_section rs
            WHERE rs.section_def_id = NEW.id
          ) refs
          WHERE refs.code NOT IN (
            SELECT jsonb_array_elements(COALESCE(NEW.choice_config -> 'values', '[]'::jsonb)) ->> 'code'
          )
          LIMIT 1;
          IF missing IS NOT NULL THEN
            RAISE EXCEPTION 'choice code "%" is referenced by existing report sections', missing
              USING ERRCODE = '23503';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS template_section_def_choice_immutability ON template_section_def")
    op.execute(
        """
        CREATE TRIGGER template_section_def_choice_immutability
        AFTER UPDATE OF choice_config ON template_section_def
        FOR EACH ROW EXECUTE FUNCTION choice_code_immutability();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS template_section_def_choice_immutability ON template_section_def")
    op.execute("DROP FUNCTION IF EXISTS choice_code_immutability")
