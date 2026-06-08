import os

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.models.base import Base

target_metadata = Base.metadata
config = context.config


def _resolve_url() -> str:
    # Prefer an explicit ini override (used by the integration test, which calls
    # set_main_option). Otherwise read DATABASE_URL from the environment so the
    # migrate container / CLI invocation gets the connection string from .env.
    return config.get_main_option("sqlalchemy.url") or os.environ.get("DATABASE_URL", "")


def run_migrations_offline() -> None:
    context.configure(url=_resolve_url(), target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    # Alembic runs sync; coerce asyncpg URL to psycopg (v3) for the migration runner.
    url = _resolve_url()
    section["sqlalchemy.url"] = url.replace("+asyncpg", "+psycopg")
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
