"""FastAPI dependencies that provide request-scoped database sessions."""

from collections.abc import Generator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.database.engine import DatabaseManager


def get_db(request: Request) -> Generator[Session]:
    """Yield a request-scoped session without committing application work."""
    database = cast(DatabaseManager, request.app.state.database)
    with database.sessions().session() as session:
        yield session
