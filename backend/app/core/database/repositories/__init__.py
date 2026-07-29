"""Generic repository abstractions for future persistence adapters."""

from app.core.database.repositories.base_repository import (
    BaseRepository,
    CRUDRepository,
    Repository,
)

__all__ = ["BaseRepository", "CRUDRepository", "Repository"]
