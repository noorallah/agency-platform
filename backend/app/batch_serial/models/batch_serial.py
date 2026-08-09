"""Enterprise batch, lot, and serial number persistence models."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class BatchRecord(BaseEntity):
    """Track one batch/lot of a product across the warehouse."""

    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint("firm_id", "batch_number", "product_id", name="UQ_batches_firm_batch_product"),
        Index("IX_batches_firm_product", "firm_id", "product_id"),
        Index("IX_batches_firm_status", "firm_id", "status"),
        Index("IX_batches_expiry_date", "firm_id", "expiry_date"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    product_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    warehouse_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True)
    branch_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    vendor_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), index=True)
    storage_node_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT"))
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_batch: Mapped[str | None] = mapped_column(String(100))
    internal_batch: Mapped[str | None] = mapped_column(String(100))
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    best_before_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="AVAILABLE", server_default="AVAILABLE")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    available_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    reserved_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    blocked_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    damaged_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    quarantine_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    shelf_life_days: Mapped[int | None] = mapped_column()
    remarks: Mapped[str | None] = mapped_column(Text)

    serials: Mapped[list["SerialNumber"]] = relationship(back_populates="batch", lazy="select")


class LotRecord(BaseEntity):
    """Track one production lot across manufacturing steps."""

    __tablename__ = "lots"
    __table_args__ = (
        UniqueConstraint("firm_id", "lot_number", "product_id", name="UQ_lots_firm_lot_product"),
        Index("IX_lots_firm_product", "firm_id", "product_id"),
        Index("IX_lots_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    product_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    warehouse_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True)
    branch_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    parent_lot_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("lots.id", ondelete="RESTRICT"), index=True)
    lot_number: Mapped[str] = mapped_column(String(100), nullable=False)
    lot_type: Mapped[str] = mapped_column(String(50), nullable=False, default="PRODUCTION", server_default="PRODUCTION")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE", server_default="ACTIVE")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    available_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    production_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    remarks: Mapped[str | None] = mapped_column(Text)


class SerialNumber(BaseEntity):
    """Track one serialized unit through its full lifecycle."""

    __tablename__ = "serial_numbers"
    __table_args__ = (
        UniqueConstraint("firm_id", "serial_number", "product_id", name="UQ_serial_numbers_firm_serial_product"),
        Index("IX_serial_numbers_firm_product", "firm_id", "product_id"),
        Index("IX_serial_numbers_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("firms.id"), nullable=False, index=True)
    product_id: Mapped[UUID] = mapped_column(UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    inventory_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("inventories.id", ondelete="RESTRICT"), index=True)
    warehouse_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True)
    branch_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), index=True)
    batch_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("batches.id", ondelete="RESTRICT"), index=True)
    serial_number: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="AVAILABLE", server_default="AVAILABLE")
    manufactured_date: Mapped[date | None] = mapped_column(Date)
    warranty_start: Mapped[date | None] = mapped_column(Date)
    warranty_end: Mapped[date | None] = mapped_column(Date)
    current_owner: Mapped[str | None] = mapped_column(String(200))
    asset_reference: Mapped[str | None] = mapped_column(String(200))
    remarks: Mapped[str | None] = mapped_column(Text)

    batch: Mapped["BatchRecord | None"] = relationship(back_populates="serials", foreign_keys=[batch_id])
