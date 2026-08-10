"""Environment-backed application settings."""

import json
import os
import re
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database.config import DatabaseDialect

_DEVELOPMENT_JWT_SECRET = "development-only-change-this-secret-key-before-production"
_DATABASE_SLOT_PATTERN = re.compile(
    r"^AGENCY_DATABASE(\d+)_(HOST|PORT|USERNAME|PASSWORD|TYPE)$"
)


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


class TenancySettings(BaseModel):
    """Expose installer-selected tenancy defaults for new firm provisioning."""

    model_config = ConfigDict(frozen=True)

    platform_database_type: DatabaseDialect
    shared_database_name: str
    shared_schema_name: str
    schema_prefix: str
    dedicated_schema_prefix: str
    dedicated_database_prefix: str
    connection_profiles: dict[str, "ConnectionProfileSettings"]


class ConnectionProfileSettings(BaseModel):
    """Resolve credentials and optional endpoint overrides for tenant connections."""

    model_config = ConfigDict(frozen=True)

    username: str
    password: SecretStr
    database_host: str | None = None
    database_port: int | None = Field(default=None, ge=1, le=65535)
    database_type: DatabaseDialect | None = None


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
    database_schema: str | None = Field(default="platform", min_length=1)
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
    tenancy_shared_database_name: str = ""
    tenancy_shared_schema_name: str = "firm_shared"
    tenancy_schema_prefix: str = ""
    tenancy_dedicated_schema_prefix: str = "firm_"
    tenancy_dedicated_database_prefix: str = "erp_"
    tenancy_connection_profiles: str | None = None

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
        if (
            self.environment in {Environment.STAGING, Environment.PRODUCTION}
            and self.database_password.get_secret_value() == "postgres"
        ):
            raise ValueError(
                "AGENCY_DATABASE_PASSWORD must be explicitly configured "
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

    @property
    def tenancy(self) -> TenancySettings:
        """Return grouped tenancy settings selected during installation."""
        profiles = self._parse_connection_profiles()
        self._ensure_platform_database_type(profiles)
        shared_database_name = (
            self.tenancy_shared_database_name.strip() or self.database_name
        )
        return TenancySettings(
            platform_database_type=self.database_dialect,
            shared_database_name=shared_database_name,
            shared_schema_name=self.tenancy_shared_schema_name,
            schema_prefix=self.tenancy_schema_prefix,
            dedicated_schema_prefix=self.tenancy_dedicated_schema_prefix,
            dedicated_database_prefix=self.tenancy_dedicated_database_prefix,
            connection_profiles=profiles,
        )

    def _parse_connection_profiles(self) -> dict[str, ConnectionProfileSettings]:
        slot_profiles = self._parse_database_slot_profiles()
        raw = self.tenancy_connection_profiles
        if raw is None or not raw.strip():
            return slot_profiles
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(
                "AGENCY_TENANCY_CONNECTION_PROFILES must be valid JSON."
            ) from error
        if not isinstance(parsed, dict):
            raise ValueError(
                "AGENCY_TENANCY_CONNECTION_PROFILES must be a JSON object."
            )
        profiles: dict[str, ConnectionProfileSettings] = {}
        for name, profile_data in parsed.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Connection profile names must be non-empty strings.")
            profiles[name.strip().upper()] = ConnectionProfileSettings.model_validate(
                profile_data
            )
        profiles.update(slot_profiles)
        return profiles

    def _parse_database_slot_profiles(self) -> dict[str, ConnectionProfileSettings]:
        slots: dict[str, dict[str, object]] = {}
        for key, raw_value in os.environ.items():
            match = _DATABASE_SLOT_PATTERN.match(key)
            if match is None:
                continue
            slot = f"DATABASE{match.group(1)}"
            field = match.group(2)
            value = raw_value.strip()
            bucket = slots.setdefault(slot, {})
            if field == "HOST":
                bucket["database_host"] = value
            elif field == "PORT":
                bucket["database_port"] = int(value)
            elif field == "USERNAME":
                bucket["username"] = value
            elif field == "PASSWORD":
                bucket["password"] = value
            elif field == "TYPE":
                bucket["database_type"] = value.lower()
        profiles: dict[str, ConnectionProfileSettings] = {}
        for slot, data in slots.items():
            if "username" not in data or "password" not in data:
                raise ValueError(
                    f"{slot} profile must define both username and password."
                )
            profiles[slot] = ConnectionProfileSettings.model_validate(data)
        return profiles

    def _ensure_platform_database_type(
        self, profiles: dict[str, ConnectionProfileSettings]
    ) -> None:
        for name, profile in profiles.items():
            if (
                profile.database_type is not None
                and profile.database_type is not self.database_dialect
            ):
                raise ValueError(
                    "Connection profile database_type must match "
                    f"AGENCY_DATABASE_DIALECT ({self.database_dialect.value}). "
                    f"Profile '{name}' uses '{profile.database_type.value}'."
                )
