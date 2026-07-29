"""Database connection configuration independent of the active dialect."""

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.engine import URL, make_url

if TYPE_CHECKING:
    from app.core.config.settings import Settings


class DatabaseDialect(StrEnum):
    """Supported relational database backends."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"


class DatabaseConfig(BaseModel):
    """Represent the complete connection configuration for one database."""

    model_config = ConfigDict(frozen=True)

    dialect: DatabaseDialect
    host: str
    port: int
    database: str
    username: str
    password: SecretStr
    pool_size: int = Field(ge=1)
    max_overflow: int = Field(ge=0)
    pool_recycle_seconds: int = Field(ge=0)
    default_schema: str | None = None
    url_override: str | None = None

    @property
    def drivername(self) -> str:
        """Return the SQLAlchemy dialect and supported DBAPI driver."""
        return {
            DatabaseDialect.POSTGRESQL: "postgresql+psycopg",
            DatabaseDialect.MYSQL: "mysql+pymysql",
        }[self.dialect]

    @property
    def url(self) -> str:
        """Build an unmasked database URL unless an explicit URL is configured."""
        if self.url_override is not None:
            return self.url_override
        return URL.create(
            drivername=self.drivername,
            username=self.username,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.database,
        ).render_as_string(hide_password=False)


class PostgreSQLConfig(DatabaseConfig):
    """PostgreSQL-specific defaults while retaining the common interface."""

    dialect: DatabaseDialect = DatabaseDialect.POSTGRESQL
    port: int = 5432


class MySQLConfig(DatabaseConfig):
    """MySQL-specific defaults while retaining the common interface."""

    dialect: DatabaseDialect = DatabaseDialect.MYSQL
    port: int = 3306


def database_config_from_settings(settings: "Settings") -> DatabaseConfig:
    """Create the selected database configuration from application settings."""
    config_class = (
        PostgreSQLConfig
        if settings.database_dialect is DatabaseDialect.POSTGRESQL
        else MySQLConfig
    )
    url_override = settings.database_url
    if url_override is not None:
        configured_dialect = make_url(url_override).get_backend_name()
        if configured_dialect != settings.database_dialect.value:
            message = (
                "AGENCY_DATABASE_URL dialect must match AGENCY_DATABASE_DIALECT "
                f"({settings.database_dialect.value})."
            )
            raise ValueError(message)

    return config_class(
        host=settings.database_host,
        port=settings.database_port
        or (5432 if settings.database_dialect is DatabaseDialect.POSTGRESQL else 3306),
        database=settings.database_name,
        username=settings.database_username,
        password=settings.database_password,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle_seconds=settings.database_pool_recycle_seconds,
        default_schema=settings.database_schema,
        url_override=url_override,
    )
