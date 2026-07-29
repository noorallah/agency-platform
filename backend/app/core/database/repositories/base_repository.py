"""Database-agnostic repository contract and SQLAlchemy base implementation."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database.entity import BaseEntity

EntityT = TypeVar("EntityT", bound=BaseEntity)
ReadEntityT = TypeVar("ReadEntityT", bound=BaseEntity, covariant=True)


class Repository(Protocol[ReadEntityT]):
    """Define the read operations expected from a persistence repository."""

    def get(
        self, entity_id: UUID, *, include_deleted: bool = False
    ) -> ReadEntityT | None:
        """Return one entity by identifier when it is visible."""

    def list(
        self, *, offset: int = 0, limit: int = 100, include_deleted: bool = False
    ) -> Sequence[ReadEntityT]:
        """Return a bounded collection of visible entities."""


class CRUDRepository(Repository[EntityT], Protocol[EntityT]):
    """Extend repository reads with lifecycle operations."""

    def add(self, entity: EntityT) -> EntityT:
        """Stage an entity for persistence."""

    def delete(self, entity: EntityT) -> None:
        """Logically delete an entity."""


class BaseRepository[EntityT: BaseEntity]:
    """Provide reusable SQLAlchemy CRUD primitives for one entity type."""

    def __init__(self, session: Session, model: type[EntityT]) -> None:
        """Bind this repository to an entity model and unit-of-work session."""
        self.session = session
        self.model = model

    def get(self, entity_id: UUID, *, include_deleted: bool = False) -> EntityT | None:
        """Return an entity by UUID, respecting soft-deletion by default."""
        statement = select(self.model).where(self.model.id == entity_id)
        if not include_deleted:
            statement = statement.where(self.model.is_deleted.is_(False))
        return self.session.scalar(statement)

    def find_by_id(
        self, entity_id: UUID, *, include_deleted: bool = False
    ) -> EntityT | None:
        """Return an entity by identifier using the standard repository name."""
        return self.get(entity_id, include_deleted=include_deleted)

    def list(
        self, *, offset: int = 0, limit: int = 100, include_deleted: bool = False
    ) -> Sequence[EntityT]:
        """Return a page of entities, excluding soft-deleted rows by default."""
        statement = select(self.model).offset(offset).limit(limit)
        if not include_deleted:
            statement = statement.where(self.model.is_deleted.is_(False))
        return self.session.scalars(statement).all()

    def find_all(
        self, *, offset: int = 0, limit: int = 100, include_deleted: bool = False
    ) -> Sequence[EntityT]:
        """Return a bounded page of visible entities."""
        return self.list(offset=offset, limit=limit, include_deleted=include_deleted)

    def add(self, entity: EntityT) -> EntityT:
        """Stage an entity for insertion or update in the current unit of work."""
        self.session.add(entity)
        return entity

    def create(self, entity: EntityT) -> EntityT:
        """Stage a new entity for insertion."""
        return self.add(entity)

    def update(self, entity: EntityT) -> EntityT:
        """Stage modifications to an existing entity."""
        self.session.add(entity)
        return entity

    def delete(self, entity: EntityT) -> None:
        """Logically delete an entity instead of issuing a physical delete."""
        entity.is_deleted = True
        entity.deleted_at = datetime.now(UTC)

    def exists(self, entity_id: UUID, *, include_deleted: bool = False) -> bool:
        """Return whether an entity is visible by identifier."""
        return self.find_by_id(entity_id, include_deleted=include_deleted) is not None

    def count(self, *, include_deleted: bool = False) -> int:
        """Return the number of visible entities."""
        statement = select(func.count()).select_from(self.model)
        if not include_deleted:
            statement = statement.where(self.model.is_deleted.is_(False))
        return int(self.session.scalar(statement) or 0)
