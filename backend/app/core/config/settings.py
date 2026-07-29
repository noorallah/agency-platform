"""Environment-backed application settings."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database.config import DatabaseDialect

_DEVELOPMENT_JWT_SECRET = "development-only-change-this-secret-key-before-production"


class Environment(StrEnum):
    """Identify an application deployment environment."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class ApplicationSettings(BaseModel):
    """Expose application metadata as a cohesive configuration group."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    environment: Environment
    debug: bool


class JwtSettings(BaseModel):
    """Expose token settings without leaking the signing secret."""

    model_config = ConfigDict(frozen=True)

    secret_key: SecretStr
    algorithm: str
    access_token_minutes: int
    refresh_token_days: int


class LoggingSettings(BaseModel):
    """Expose logging settings as a cohesive configuration group."""

    model_config = ConfigDict(frozen=True)

    level: str
    directory: Path
    file_name: str
    max_bytes: int
    backup_count: int
    file_enabled: bool


class SecuritySettings(BaseModel):
    """Expose generic security policy settings."""

    model_config = ConfigDict(frozen=True)

    max_login_attempts: int
    lockout_minutes: int
    password_history_count: int


class LicenseSettings(BaseModel):
    """Reserve license infrastructure configuration for a future module."""

    model_config = ConfigDict(frozen=True)

    enabled: bool
    validation_url: str | None


class Settings(BaseSettings):
    """Provide typed, validated settings loaded from the environment.

    Environment variables use the ``AGENCY_`` prefix. Values in
    ``config/.env`` are a local-development convenience and remain optional.
    """

    app_name: str = "Agency Platform Backend"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: str = "INFO"
    log_directory: Path = Path("logs")
    log_file_name: str = "application.log"
    log_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    log_backup_count: int = Field(default=5, ge=0)
    log_file_enabled: bool = True
    database_url: str | None = Field(default=None)
    database_dialect: DatabaseDialect = DatabaseDialect.POSTGRESQL
    database_host: str = "localhost"
    database_port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str = "agency_platform"
    database_username: str = "postgres"
    database_password: SecretStr = SecretStr("postgres")
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_recycle_seconds: int = Field(default=1800, ge=0)
    database_schema: str | None = Field(default=None, min_length=1)
    jwt_secret_key: SecretStr = SecretStr(_DEVELOPMENT_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = Field(default=15, ge=1)
    jwt_refresh_token_days: int = Field(default=7, ge=1)
    security_max_login_attempts: int = Field(default=5, ge=1)
    security_lockout_minutes: int = Field(default=15, ge=1)
    security_password_history_count: int = Field(default=5, ge=1, le=24)
    bootstrap_admin_password: SecretStr | None = None
    license_enabled: bool = False
    license_validation_url: str | None = None

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file="config/.env",
        env_file_encoding="utf-8",
        env_prefix="AGENCY_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_bootstrap_password(self) -> "Settings":
        """Reject known development secrets outside local development."""
        if (
            self.environment in {Environment.STAGING, Environment.PRODUCTION}
            and self.jwt_secret_key.get_secret_value() == _DEVELOPMENT_JWT_SECRET
        ):
            raise ValueError(
                "AGENCY_JWT_SECRET_KEY must be explicitly configured "
                "outside development."
            )
        if self.bootstrap_admin_password is None:
            if self.environment is Environment.DEVELOPMENT:
                self.bootstrap_admin_password = SecretStr("Local-Development-Only1!")
            else:
                raise ValueError(
                    "AGENCY_BOOTSTRAP_ADMIN_PASSWORD is required outside development."
                )
        return self

    @property
    def app(self) -> ApplicationSettings:
        """Return grouped application metadata."""
        return ApplicationSettings(
            name=self.app_name,
            version=self.app_version,
            environment=self.environment,
            debug=self.debug,
        )

    @property
    def jwt(self) -> JwtSettings:
        """Return grouped JWT settings."""
        return JwtSettings(
            secret_key=self.jwt_secret_key,
            algorithm=self.jwt_algorithm,
            access_token_minutes=self.jwt_access_token_minutes,
            refresh_token_days=self.jwt_refresh_token_days,
        )

    @property
    def logging(self) -> LoggingSettings:
        """Return grouped logging settings."""
        return LoggingSettings(
            level=self.log_level,
            directory=self.log_directory,
            file_name=self.log_file_name,
            max_bytes=self.log_max_bytes,
            backup_count=self.log_backup_count,
            file_enabled=self.log_file_enabled,
        )

    @property
    def security(self) -> SecuritySettings:
        """Return grouped security settings."""
        return SecuritySettings(
            max_login_attempts=self.security_max_login_attempts,
            lockout_minutes=self.security_lockout_minutes,
            password_history_count=self.security_password_history_count,
        )

    @property
    def license(self) -> LicenseSettings:
        """Return grouped licensing settings."""
        return LicenseSettings(
            enabled=self.license_enabled,
            validation_url=self.license_validation_url,
        )
