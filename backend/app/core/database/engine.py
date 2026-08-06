"""SQLAlchemy engine construction and application-scoped database resources."""

from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.config import DatabaseConfig, database_config_from_settings
from app.core.database.session import SessionManager

if TYPE_CHECKING:
    from app.core.config.settings import Settings


class EngineFactory:
    """Build configured SQLAlchemy engines without exposing global session state."""

    @staticmethod
    def database_config_from_settings(settings: "Settings") -> DatabaseConfig:
        """Translate application settings into a dialect-specific configuration."""
        return database_config_from_settings(settings)

    @staticmethod
    def create_engine(config: DatabaseConfig) -> Engine:
        """Create a pooled engine for the configured backend."""
        return create_engine(
            config.url,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_pre_ping=True,
            pool_recycle=config.pool_recycle_seconds,
        )


class DatabaseManager:
    """Own an application's engine and create short-lived session managers."""

    def __init__(self, config: DatabaseConfig) -> None:
        """Create the pooled engine and its session factory."""
        self.config = config
        self.engine = EngineFactory.create_engine(config)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    @classmethod
    def from_settings(cls, settings: "Settings") -> "DatabaseManager":
        """Create a manager from the active application settings."""
        return cls(EngineFactory.database_config_from_settings(settings))

    def sessions(self, schema: str | None = None) -> SessionManager:
        """Create a session manager, optionally scoped to a future tenant schema."""
        return SessionManager(self.session_factory, schema=schema)

    def dispose(self) -> None:
        """Release all pooled connections during application shutdown."""
        self.engine.dispose()
