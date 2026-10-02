"""Enterprise batch, lot, and serial number persistence models."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    and_,
    or_,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import ColumnElement

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class BatchRecord(BaseEntity):
    """Track one batch/lot of a product across the warehouse."""

    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "batch_number",
            "product_id",
            name="UQ_batches_firm_batch_product",
        ),
        Index("IX_batches_firm_product", "firm_id", "product_id"),
        Index("IX_batches_firm_status", "firm_id", "status"),
        Index("IX_batches_expiry_date", "firm_id", "expiry_date"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True
    )
    branch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), index=True
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), index=True
    )
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT")
    )
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_batch: Mapped[str | None] = mapped_column(String(100))
    internal_batch: Mapped[str | None] = mapped_column(String(100))
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    best_before_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="AVAILABLE", server_default="AVAILABLE"
    )
    shelf_life_days: Mapped[int | None] = mapped_column()
    remarks: Mapped[str | None] = mapped_column(Text)

    # A batch stores no quantities. It carries identity -- the number, who
    # supplied it, when it expires, whether it is blocked -- and how much of it
    # is on the shelf is a consequence of the movements that put it there.
    # `inventories` is keyed by batch, so the answer is a sum of the stock rows
    # carrying this id; `InventoryService.stock_by_batch` is where it lives.

    serials: Mapped[list["SerialNumber"]] = relationship(
        back_populates="batch", lazy="select"
    )

    @classmethod
    def expired_condition(cls, on_date: date) -> "ColumnElement[bool]":
        """Return the condition identifying batches that have expired.

        Expiry is a fact about the date, not a status: nothing ever set
        ``status = 'EXPIRED'`` -- there is no scheduler in the platform to do it
        -- so every count keyed on that status reported zero while expired
        stock sat on the shelf. A batch someone marked expired by hand still
        counts; a destroyed one never does.
        """
        return and_(
            cls.status != "DESTROYED",
            or_(
                cls.status == "EXPIRED",
                and_(cls.expiry_date.isnot(None), cls.expiry_date <= on_date),
            ),
        )


class LotRecord(BaseEntity):
    """Track one production lot across manufacturing steps."""

    __tablename__ = "lots"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "lot_number", "product_id", name="UQ_lots_firm_lot_product"
        ),
        Index("IX_lots_firm_product", "firm_id", "product_id"),
        Index("IX_lots_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True
    )
    branch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), index=True
    )
    parent_lot_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("lots.id", ondelete="RESTRICT"), index=True
    )
    lot_number: Mapped[str] = mapped_column(String(100), nullable=False)
    lot_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PRODUCTION", server_default="PRODUCTION"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    available_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )
    production_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    remarks: Mapped[str | None] = mapped_column(Text)


class SerialNumber(BaseEntity):
    """Track one serialized unit through its full lifecycle."""

    __tablename__ = "serial_numbers"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "serial_number",
            "product_id",
            name="UQ_serial_numbers_firm_serial_product",
        ),
        Index("IX_serial_numbers_firm_product", "firm_id", "product_id"),
        Index("IX_serial_numbers_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    inventory_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("inventories.id", ondelete="RESTRICT"), index=True
    )
    warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True
    )
    branch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), index=True
    )
    batch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("batches.id", ondelete="RESTRICT"), index=True
    )
    serial_number: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="AVAILABLE", server_default="AVAILABLE"
    )
    manufactured_date: Mapped[date | None] = mapped_column(Date)
    warranty_start: Mapped[date | None] = mapped_column(Date)
    warranty_end: Mapped[date | None] = mapped_column(Date)
    current_owner: Mapped[str | None] = mapped_column(String(200))
    asset_reference: Mapped[str | None] = mapped_column(String(200))
    remarks: Mapped[str | None] = mapped_column(Text)

    batch: Mapped["BatchRecord | None"] = relationship(
        back_populates="serials", foreign_keys=[batch_id]
    )


class DocumentLineSerial(BaseEntity):
    """Name one serialised unit a document line moves.

    A serial's status is a consequence of the documents that moved it, and
    nothing recorded which unit a movement carried: a delivery note dispatched
    two mixer grinders and every serial on the shelf stayed ``AVAILABLE``
    (D-STK-4). One row here says "this line moves this unit".

    The row is written when the line is saved -- the storekeeper picks the
    units while the note is still a draft -- and ``moved_at`` and
    ``inventory_transaction_id`` are filled when the stock actually moves. A
    pick with no ``moved_at`` has changed nothing yet.

    A movement is one row per batch drawn from rather than one per unit, so
    the link lives here: every unit names the movement that carried it, and
    ``inventory_transactions.serial_id`` is set only where a movement carried
    exactly one unit. The document and its line are bare ids, the convention
    every downstream document follows, because two modules write rows here.
    """

    __tablename__ = "document_line_serials"
    __table_args__ = (
        UniqueConstraint(
            "document_line_id",
            "serial_id",
            name="UQ_document_line_serials_line_serial",
        ),
        Index("IX_document_line_serials_firm_serial", "firm_id", "serial_id"),
        Index("IX_document_line_serials_firm_document", "firm_id", "document_id"),
        Index("IX_document_line_serials_firm_line", "firm_id", "document_line_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    serial_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("serial_numbers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: ``DELIVERY_NOTE`` (the unit leaves) or ``SALES_RETURN`` (it comes back).
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    document_line_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The movement that carried the unit, once it has moved.
    inventory_transaction_id: Mapped[UUID | None] = mapped_column(UUIDType())
    #: When the unit moved on this line; empty while it is only picked.
    moved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BatchSaleSettings(BaseEntity):
    """One firm's rules for which batches go out on a sale (backlog 79 row 6).

    The shape of ``price_floor_settings``: one row per firm, and a firm with
    no row shares the defaults -- near expiry is 30 days, a near-expiry batch
    and a FEFO skip are recorded but need no reason, and a near-expiry batch
    may be sold below the price floor (decision A2).
    """

    __tablename__ = "batch_sale_settings"
    __table_args__ = (
        Index(
            "UQ_batch_sale_settings_firm_active",
            "firm_id",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: A batch expiring within this many days of the document's date is near
    #: expiry: flagged in the picker, and judged by the two rules below.
    near_expiry_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    #: WARN records a near-expiry batch leaving; REASON refuses the dispatch
    #: until somebody says why.
    near_expiry_policy: Mapped[str] = mapped_column(
        String(10), nullable=False, default="WARN", server_default="WARN"
    )
    #: RECORD keeps both splits in the audit trail when a person draws a
    #: later batch ahead of an earlier one; REASON also needs a reason.
    fefo_skip_policy: Mapped[str] = mapped_column(
        String(10), nullable=False, default="RECORD", server_default="RECORD"
    )
    #: Whether a line drawn wholly from near-expiry batches may be sold below
    #: its price floor, the batches kept on the approval (decision A2).
    near_expiry_below_floor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: A batch chosen by hand with less shelf life left than the customer
    #: asks for: BLOCK refuses the dispatch, WARN records it. Earliest-expiry
    #: allocation passes over such a batch whatever this says.
    shelf_life_policy: Mapped[str] = mapped_column(
        String(10), nullable=False, default="BLOCK", server_default="BLOCK"
    )
