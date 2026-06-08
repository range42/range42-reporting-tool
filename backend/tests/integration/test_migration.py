import pytest
from alembic.config import Config

from alembic import command


@pytest.mark.integration
def test_upgrade_then_downgrade(pg_url: str, alembic_cfg: Config) -> None:
    alembic_cfg.set_main_option("sqlalchemy.url", pg_url)
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")
