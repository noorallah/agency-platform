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


def _target_url() -> str:
    """Return the database to migrate.

    `config.attributes` first, `Settings()` second. The attributes are how an
    in-process caller says which store it means without touching
    `os.environ`: those variables are process-wide, and two concurrent
    provisions once raced on them badly enough that the whole operation was
    pushed into a subprocess to get an environment of its own. Passing the
    target through the Config object instead gives each call its own values
    with no shared state, which is what lets it come back in-process -- and a
    frozen build has no interpreter to spawn.
    """
    override = config.attributes.get("database_url")
    if override:
        return str(override)
    return EngineFactory.database_config_from_settings(Settings()).url


def _target_schema() -> str | None:
    """Return the schema to migrate, by the same rule as `_target_url`."""
    override = config.attributes.get("schema_name")
    if override is not None:
        return str(override) or None
    return Settings().database_schema


def run_migrations_offline() -> None:
    """Run migrations without creating a database engine."""
    url = _target_url()
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
    settings = Settings()
    database = EngineFactory.database_config_from_settings(settings)
    override = config.attributes.get("database_url")
    if override:
        # DatabaseConfig is a frozen pydantic model: copy with the override
        # rather than mutating, and let `url` resolve from it as usual.
        database = database.model_copy(update={"url_override": str(override)})
    connectable = EngineFactory.create_engine(database)

    with connectable.connect() as connection:
        _configure_migrations(connection)

    connectable.dispose()


def _configure_migrations(connection: Connection) -> None:
    """Configure and execute migrations through an open connection."""
    schema = _target_schema()
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
