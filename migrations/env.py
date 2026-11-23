"""
migrations/env.py - Alembic runs this file for every `alembic ...` command.

WHAT ALEMBIC IS FOR:
    models.py describes what the tables SHOULD look like. The real MySQL tables don't
    change by themselves when you edit a model. Alembic keeps them in sync with
    small, versioned "migration" scripts (migrations/versions/*.py), each with an
    upgrade() and a downgrade(). Git tracks them, so every developer / server can
    bring their database to exactly the same schema.

DAILY COMMANDS (run in the project folder):
    uv run alembic revision --autogenerate -m "add bio to users"
        -> compares models.py with the live DB and WRITES a migration file.
           Always open and read it before applying!
    uv run alembic upgrade head      -> apply all pending migrations
    uv run alembic downgrade -1      -> undo the last migration
    uv run alembic current           -> which migration the DB is at
    uv run alembic history           -> list all migrations

HOW IT KNOWS THE DB VERSION:
    Alembic stores the current revision id in a one-row table called `alembic_version`.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Importing models REGISTERS every table on Base.metadata - without this import,
# autogenerate would think there are no tables and propose dropping them all!
import models  # noqa: F401  (imported for its side effect)
from config import settings
from database import Base

# The Alembic Config object (gives access to alembic.ini).
config = context.config

# Use the SAME database URL as the app (from .env via config.py) instead of
# hard-coding it in alembic.ini. ("%" must be doubled for the ini parser.)
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

# Set up Python logging from the [loggers] section of alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# What `--autogenerate` compares the database against: all our models' tables.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """'Offline' mode: `alembic upgrade head --sql` prints the SQL instead of running
    it - handy to review changes or hand them to a DBA. No DB connection needed."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # also detect column TYPE changes (e.g. String(50) -> String(80))
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """'Online' mode with our ASYNC driver (aiomysql).

    Migrations themselves are written as normal sync code, so we open an async
    connection and use run_sync() to run them inside it.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # one-off command: no need for a connection pool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
