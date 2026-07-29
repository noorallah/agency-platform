"""Database-portable SQLAlchemy column types."""

from collections.abc import Mapping
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import CHAR, JSON, DateTime, Numeric
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine

type JSONValue = (
    str | int | float | bool | None | list[JSONValue] | Mapping[str, JSONValue]
)


class UUIDType(TypeDecorator[UUID]):
    """Store UUIDs natively in PostgreSQL and as portable strings elsewhere."""

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[UUID]:
        """Choose the native UUID type only for PostgreSQL."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=True))
        return cast(TypeEngine[UUID], dialect.type_descriptor(CHAR(36)))

    def process_bind_param(
        self, value: UUID | None, dialect: Dialect
    ) -> UUID | str | None:
        """Convert UUID values to the representation accepted by the active dialect."""
        if value is None or dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(
        self, value: UUID | str | None, dialect: Dialect
    ) -> UUID | None:
        """Return UUID objects consistently across database backends."""
        if value is None or isinstance(value, UUID):
            return value
        return UUID(value)


JSONType = JSON
UTCDateTime = DateTime(timezone=True)


def decimal_type(precision: int = 18, scale: int = 2) -> Numeric[Decimal]:
    """Create a portable fixed-precision decimal type."""
    return Numeric(precision=precision, scale=scale, asdecimal=True)
