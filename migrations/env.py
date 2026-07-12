"""Alembic environment configuration."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.db.models import Base
from app.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
# Only set default URL if not already configured (e.g., by test scripts)
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations inside a connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
        await connection.commit()
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    For SQLite (our only DB), use a sync engine to avoid async
    transaction-commit issues that prevent schema persistence.
    For other databases, the async path would be used.
    """
    url = config.get_main_option("sqlalchemy.url")
    if url.startswith("sqlite"):
        # SQLite: use sync engine for reliable schema persistence.
        # Convert aiosqlite URL to plain sqlite sync URL.
        sync_url = url.replace("sqlite+aiosqlite://", "sqlite://")
        connectable = create_engine(sync_url, poolclass=pool.NullPool)
        with connectable.connect() as connection:
            do_run_migrations(connection)
            connection.commit()
        connectable.dispose()
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
