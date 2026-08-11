"""SQLAlchemy models for platform-level firm administration."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class Firm(BaseEntity):
    """Represent an organization available to one or more platform users."""

    __tablename__ = "firms"
    __table_args__ = tuple(
        # A firm's natural keys are reserved by live firms only. Table-wide
        # UNIQUE constraints kept them forever, so a soft-deleted firm burned
        # its code, GST and PAN: FirmService._assert_unique ignores deleted rows
        # and then INSERT failed on the constraint with a 500. This mirrors
        # UQ_users_email_active. MySQL ignores the predicate, so the service
        # check stays authoritative there.
        Index(
            f"UQ_firms_{column}_active",
            column,
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        )
        for column in ("code", "gst_number", "pan_number")
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    gst_number: Mapped[str | None] = mapped_column(String(32))
    pan_number: Mapped[str | None] = mapped_column(String(32))
    address_line1: Mapped[str | None] = mapped_column(String(250))
    address_line2: Mapped[str | None] = mapped_column(String(250))
    city: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(24))
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    state: Mapped[str | None] = mapped_column(String(100))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    financial_year_start: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    created_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    storage_mappings: Mapped[list["FirmStorageMapping"]] = relationship(
        back_populates="firm", cascade="all, delete-orphan"
    )

    @property
    def deployment_mode(self) -> str:
        """Return the firm deployment mode from its active storage mapping."""
        mapping = self._active_storage_mapping
        return mapping.deployment_mode if mapping is not None else "SHARED"

    @property
    def database_type(self) -> str:
        """Return the firm database engine from its active storage mapping."""
        mapping = self._active_storage_mapping
        return mapping.database_type if mapping is not None else "postgresql"

    @property
    def database_name(self) -> str | None:
        """Return the firm dedicated/shared database override, if configured."""
        mapping = self._active_storage_mapping
        return mapping.database_name if mapping is not None else None

    @property
    def schema_name(self) -> str | None:
        """Return the firm dedicated/shared schema override, if configured."""
        mapping = self._active_storage_mapping
        return mapping.schema_name if mapping is not None else None

    @property
    def connection_profile(self) -> str | None:
        """Return the configured connection profile naming this firm's server."""
        mapping = self._active_storage_mapping
        return mapping.connection_profile if mapping is not None else None

    @property
    def provisioned_at(self) -> datetime | None:
        """Return when this firm's dedicated storage was last built."""
        mapping = self._active_storage_mapping
        return mapping.provisioned_at if mapping is not None else None

    @property
    def _active_storage_mapping(self) -> "FirmStorageMapping | None":
        active = next(
            (
                mapping
                for mapping in self.storage_mappings
                if not mapping.is_deleted and mapping.is_active
            ),
            None,
        )
        if active is not None:
            return active
        return next(
            (mapping for mapping in self.storage_mappings if not mapping.is_deleted),
            None,
        )


class FirmStorageMapping(BaseEntity):
    """Persist tenant storage routing details for a firm."""

    __tablename__ = "firm_storage_mappings"
    __table_args__ = (
        Index("IX_firm_storage_mappings_firm_id", "firm_id"),
        UniqueConstraint("firm_id", name="UQ_firm_storage_mappings_firm_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    deployment_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SHARED", server_default="SHARED"
    )
    database_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="postgresql", server_default="postgresql"
    )
    database_name: Mapped[str | None] = mapped_column(String(128))
    schema_name: Mapped[str | None] = mapped_column(String(128))

    # Names an entry in AGENCY_TENANCY_CONNECTION_PROFILES. NULL means the
    # platform server, which is where every firm lived before a firm could be
    # pointed at a different one.
    connection_profile: Mapped[str | None] = mapped_column(String(64))

    # Dedicated storage is built by an explicit action rather than inline at
    # firm creation, so a firm exists before its tables do. Until this is
    # stamped the tenant resolver refuses to route requests to it.
    provisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provisioning_error: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    firm: Mapped[Firm] = relationship(back_populates="storage_mappings")
