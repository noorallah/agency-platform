"""Firm-scoped branch, warehouse, and storage structure persistence models."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    and_,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class BranchType(BaseEntity):
    """Persist reusable branch type masters per firm."""

    __tablename__ = "branch_types"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_branch_types_firm_code"),
        UniqueConstraint("firm_id", "name", name="UQ_branch_types_firm_name"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class Branch(BaseEntity):
    """Represent one physical operational branch owned by a firm."""

    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_branches_firm_code"),
        Index("IX_branches_firm_name", "firm_id", "name"),
        Index("IX_branches_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    branch_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branch_types.id", ondelete="RESTRICT")
    )
    branch_manager_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="RESTRICT")
    )
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(20))
    mobile: Mapped[str | None] = mapped_column(String(20))
    country_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_countries.id", ondelete="RESTRICT")
    )
    state_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_states.id", ondelete="RESTRICT")
    )
    district_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_districts.id", ondelete="RESTRICT")
    )
    city_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_cities.id", ondelete="RESTRICT")
    )
    postal_code_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_postal_codes.id", ondelete="RESTRICT")
    )
    locality_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_localities.id", ondelete="RESTRICT")
    )
    address_line1: Mapped[str | None] = mapped_column(String(250))
    address_line2: Mapped[str | None] = mapped_column(String(250))
    timezone: Mapped[str | None] = mapped_column(String(100))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    gst_registration: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    pan: Mapped[str | None] = mapped_column(String(32))
    license_number: Mapped[str | None] = mapped_column(String(64))
    working_hours: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    warehouses: Mapped[list["Warehouse"]] = relationship(
        back_populates="branch",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Branch.id == Warehouse.branch_id,
            Warehouse.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="Warehouse.created_at",
    )


class WarehouseType(BaseEntity):
    """Persist reusable warehouse type masters per firm."""

    __tablename__ = "warehouse_types"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_warehouse_types_firm_code"),
        UniqueConstraint("firm_id", "name", name="UQ_warehouse_types_firm_name"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class Warehouse(BaseEntity):
    """Represent one physical warehouse mapped to a branch."""

    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_warehouses_firm_code"),
        Index("IX_warehouses_firm_name", "firm_id", "name"),
        Index("IX_warehouses_branch_status", "branch_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    warehouse_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouse_types.id", ondelete="RESTRICT")
    )
    warehouse_manager_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="RESTRICT")
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    country_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_countries.id", ondelete="RESTRICT")
    )
    state_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_states.id", ondelete="RESTRICT")
    )
    district_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_districts.id", ondelete="RESTRICT")
    )
    city_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_cities.id", ondelete="RESTRICT")
    )
    postal_code_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_postal_codes.id", ondelete="RESTRICT")
    )
    locality_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_localities.id", ondelete="RESTRICT")
    )
    address_line1: Mapped[str | None] = mapped_column(String(250))
    address_line2: Mapped[str | None] = mapped_column(String(250))
    capacity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    capacity_unit: Mapped[str | None] = mapped_column(String(20))
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    temperature_controlled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    cold_storage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    hazardous_storage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    has_receiving_area: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    has_dispatch_area: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    has_returns_area: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    has_inspection_area: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    has_packing_area: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    has_loading_dock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    branch: Mapped[Branch] = relationship(back_populates="warehouses")
    storage_nodes: Mapped[list["WarehouseStorageNode"]] = relationship(
        back_populates="warehouse",
        cascade="save-update, merge",
        primaryjoin=lambda: and_(
            Warehouse.id == WarehouseStorageNode.warehouse_id,
            WarehouseStorageNode.is_deleted.is_(False),
        ),
        lazy="selectin",
        order_by="WarehouseStorageNode.created_at",
    )


class WarehouseStorageNode(BaseEntity):
    """Represent storage hierarchy nodes (area/rack/shelf/bin/receiving)."""

    __tablename__ = "warehouse_storage_nodes"
    __table_args__ = (
        UniqueConstraint(
            "warehouse_id",
            "code",
            name="UQ_warehouse_storage_nodes_warehouse_code",
        ),
        UniqueConstraint(
            "warehouse_id",
            "name",
            "parent_id",
            name="UQ_warehouse_storage_nodes_warehouse_name_parent",
        ),
        Index("IX_warehouse_storage_nodes_warehouse_parent", "warehouse_id", "parent_id"),
        Index("IX_warehouse_storage_nodes_warehouse_type", "warehouse_id", "node_type"),
    )

    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT"),
    )
    node_type: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    warehouse: Mapped[Warehouse] = relationship(back_populates="storage_nodes")
