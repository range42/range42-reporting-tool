"""template_section_def: add default_content, a template-authored starting value for rich_text sections"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("template_section_def", sa.Column("default_content", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("template_section_def", "default_content")
