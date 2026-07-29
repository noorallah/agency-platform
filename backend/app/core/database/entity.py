"""Standard base entity composed from the shared persistence mixins."""

from app.core.database.base import Base
from app.core.database.mixins import (
    AuditMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
    VersionMixin,
)


class BaseEntity(
    UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, VersionMixin, Base
):
    """Base for future business entities with standard persistence fields."""

    __abstract__ = True
