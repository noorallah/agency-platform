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
#: What a development server encrypts messaging credentials under when
#: ``AGENCY_MESSAGING_KEY`` is unset. Never accepted outside development.
DEVELOPMENT_MESSAGING_KEY = "development-only-messaging-key-change-before-production"
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
    retention_days: int = 30
    error_retention_days: int = 90
    max_total_mb: int = 1024


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
    #: The platform store, which no dedicated firm may be routed to (D-IDN-4).
    #: Defaulted so a caller building this by hand keeps working.
    platform_database_name: str = ""
    platform_schema_name: str = "platform"


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
    app_version: str = "1.1.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: str = "INFO"
    log_directory: Path = Path("logs")
    #: Retired: the server writes `server/server-YYYY-MM-DD.log` now. Still
    #: accepted so an existing `.env` that names it keeps loading.
    log_file_name: str = "application.log"
    #: The size at which a day's log file is rolled over within the day.
    log_max_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    #: Retired: log files are kept by age (`log_retention_days`) now.
    log_backup_count: int = Field(default=5, ge=0)
    log_file_enabled: bool = True
    log_retention_days: int = Field(default=30, ge=1)
    log_error_retention_days: int = Field(default=90, ge=1)
    log_max_total_mb: int = Field(default=1024, ge=1)
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
    #: The key a firm's messaging credentials (SMTP password, WhatsApp access
    #: token, SMS auth key) are encrypted under, held here rather than in the
    #: database (backlog 51, decision 2). Unset in development reads a fixed
    #: development key; unset in staging or production means no credential
    #: can be saved at all -- the server still starts, because messaging is a
    #: feature a firm turns on and most never will.
    messaging_key: SecretStr | None = None
    #: Run the messaging outbox in a background thread of the server process.
    #: Off for a process that only serves a test client or a second worker.
    messaging_worker_enabled: bool = True
    #: Seconds between outbox passes.
    messaging_worker_interval_seconds: int = Field(default=60, ge=5)
    #: Where `Back up now` writes (`manual/<stamp>`) and where the backups
    #: screen looks for the nightly (`daily/`) and pre-upgrade ones. Setup
    #: points it at `<data root>/backups` through the service definition.
    backup_directory: Path = Path("backups")
    #: How many manual backups are kept; the oldest beyond this are deleted.
    backup_keep_manual: int = Field(default=10, ge=1)
    #: The folder holding `pg_dump` and `pg_restore`. Unset, the server looks
    #: beside itself (`<install>/pgsql/bin`), then on PATH.
    backup_pg_bin: Path | None = None
    #: Whether the nightly task prunes old login records, refresh tokens,
    #: password history and tax-rule logs after its backup (PLT-6). On by
    #: default; a platform that must keep them longer sets it false.
    retention_auto_purge: bool = True

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

    def messaging_secret(self) -> str | None:
        """Return the key messaging credentials are encrypted under, if any.

        The shape of the JWT key: development (and testing) fall back to a
        fixed, published key; staging and production have no fallback, so a
        firm there cannot store credentials until the operator sets
        ``AGENCY_MESSAGING_KEY``. A value equal to the development key is
        refused outside development for the same reason.
        """
        configured = (
            None
            if self.messaging_key is None
            else self.messaging_key.get_secret_value()
        )
        if self.environment in {Environment.STAGING, Environment.PRODUCTION}:
            if not configured or configured == DEVELOPMENT_MESSAGING_KEY:
                return None
            return configured
        return configured or DEVELOPMENT_MESSAGING_KEY

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
            retention_days=self.log_retention_days,
            error_retention_days=self.log_error_retention_days,
            max_total_mb=self.log_max_total_mb,
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
            platform_database_name=self.database_name,
            platform_schema_name=self.database_schema or "platform",
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
