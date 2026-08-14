"""Alembic environment for the application's SQLAlchemy metadata."""

import re
from logging.config import fileConfig

from sqlalchemy import text
from sqlalchemy.engine import Connection

# One list of model modules, shared with the tests and the seed
# scripts. A module missing from it is invisible to autogenerate, to
# `create_all` and to the sample-data reset alike.
import app.core.database.all_models  # noqa: F401
from alembic import context
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.database.engine import EngineFactory

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
_SAFE_SCHEMA = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def run_migrations_offline() -> None:
    """Run migrations without creating a database engine."""
    url = EngineFactory.database_config_from_settings(Settings()).url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations through a database connection."""
    connectable = EngineFactory.create_engine(
        EngineFactory.database_config_from_settings(Settings())
    )

    with connectable.connect() as connection:
        _configure_migrations(connection)

    connectable.dispose()


def _configure_migrations(connection: Connection) -> None:
    """Configure and execute migrations through an open connection."""
    settings = Settings()
    schema = settings.database_schema
    if schema and connection.dialect.name == "postgresql":
        if _SAFE_SCHEMA.fullmatch(schema) is None:
            raise ValueError(f"Invalid AGENCY_DATABASE_SCHEMA: {schema!r}")
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_schemas=True,
        version_table_schema=schema,
    )

    with context.begin_transaction():
        context.run_migrations()
    connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
