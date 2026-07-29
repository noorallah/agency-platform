"""Alembic environment for the application's SQLAlchemy metadata."""

from logging.config import fileConfig

from sqlalchemy.engine import Connection

from alembic import context
from app.common.audit.models import audit_log  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.database.engine import EngineFactory
from app.firms.models import firm  # noqa: F401
from app.identity.models import identity  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


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
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
