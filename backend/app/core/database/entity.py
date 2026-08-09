"""Standard base entity composed from the shared persistence mixins."""

from sqlalchemy.orm import declared_attr

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

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, object]:  # noqa: N805
        """Let SQLAlchemy maintain and check the optimistic-concurrency counter.

        The ``version`` column existed from the start and nothing ever read or
        incremented it. Declaring it as the mapper's version id makes every ORM
        update bump it and add ``WHERE version = :loaded`` to the statement, so a
        write against a row another transaction already changed fails instead of
        silently overwriting it.
        """
        return {"version_id_col": cls.__table__.c.version}
