"""Shared SQLAlchemy declarative base and deterministic metadata."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "IX_%(table_name)s_%(column_0_name)s",
    "uq": "UQ_%(table_name)s_%(column_0_name)s",
    "ck": "CK_%(table_name)s_%(constraint_name)s",
    # Keyed on the referring column, not the referred table: two foreign keys
    # from one table to the same target (products.category_id and
    # products.sub_category_id both reference product_categories) generated the
    # same name, which SQLite ignores but PostgreSQL rejects as a duplicate
    # constraint. That made Base.metadata.create_all unusable on PostgreSQL,
    # and the sample-data and tenancy-reset scripts build firm schemas with it.
    "fk": "FK_%(table_name)s_%(column_0_name)s",
    "pk": "PK_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class that every ORM entity must inherit."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
