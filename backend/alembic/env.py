"""Alembic environment for the application's SQLAlchemy metadata."""

import re
from logging.config import fileConfig

from sqlalchemy import text
from sqlalchemy.engine import Connection

from alembic import context
from app.batch_serial.models import batch_serial  # noqa: F401
from app.branches.models import branch_warehouse  # noqa: F401
from app.business.models import framework  # noqa: F401
from app.common.audit.models import audit_log  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.database.engine import EngineFactory
from app.customers.models import customer  # noqa: F401
from app.delivery_note.models import delivery_note  # noqa: F401
from app.diagnostics.models import error_report  # noqa: F401
from app.document_framework.models import document_framework  # noqa: F401
from app.finance.models import finance  # noqa: F401
from app.firms.models import firm  # noqa: F401
from app.goods_receipt.models import goods_receipt  # noqa: F401
from app.identity.models import identity  # noqa: F401
from app.inventory.models import inventory  # noqa: F401
from app.products.models import product  # noqa: F401
from app.purchase.models import purchase  # noqa: F401
from app.purchase_invoice.models import purchase_invoice  # noqa: F401
from app.purchase_return.models import purchase_return  # noqa: F401
from app.sales.models import territory  # noqa: F401
from app.sales_invoice.models import sales_invoice  # noqa: F401
from app.sales_order.models import sales_order  # noqa: F401
from app.settlements.models import settlement  # noqa: F401
from app.tax.models import tax_framework  # noqa: F401
from app.uom.models import uom  # noqa: F401
from app.vendors.models import vendor  # noqa: F401

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
