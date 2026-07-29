"""Reusable persistence infrastructure shared by all future modules."""

from app.core.database.base import Base
from app.core.database.engine import DatabaseManager, EngineFactory
from app.core.database.entity import BaseEntity
from app.core.database.repositories import BaseRepository
from app.core.database.unit_of_work import SQLAlchemyUnitOfWork, UnitOfWork

__all__ = [
    "Base",
    "BaseEntity",
    "BaseRepository",
    "DatabaseManager",
    "EngineFactory",
    "SQLAlchemyUnitOfWork",
    "UnitOfWork",
]
