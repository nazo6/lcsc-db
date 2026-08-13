"""Alembic migration environment for lcsc-db."""

from alembic import context
from sqlmodel import SQLModel

# Importing the module registers all table models with ``SQLModel.metadata``.
import lcsc_db.schema  # noqa: F401

config = context.config
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live connection."""
    from sqlalchemy import create_engine

    database_url = config.get_main_option("sqlalchemy.url")
    if database_url is None:
        raise RuntimeError("sqlalchemy.url is not set in alembic configuration")
    connectable = create_engine(database_url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
