"""Inventory, transaction, ledger, and opening-stock persistence models."""

from datetime import date, datetime
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.clock import statement_now
from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class InventoryRecord(BaseEntity):
    """Persist one firm-scoped inventory projection per product location."""

    __tablename__ = "inventories"
    __table_args__ = (
        # Stock is held per batch where a product is batch-tracked, and once
        # per location where it is not. One unique constraint cannot express
        # that: a NULL batch is distinct from every other NULL in both
        # PostgreSQL and SQLite, so a single key over a nullable column would
        # let untracked stock duplicate freely. Two partial indexes say it
        # exactly -- one row per location for untracked stock, one row per
        # batch for tracked.
        Index(
            "UQ_inventories_location_product_untracked",
            "firm_id",
            "branch_id",
            "warehouse_id",
            "storage_locator",
            "product_id",
            unique=True,
            postgresql_where=text("batch_id IS NULL"),
            sqlite_where=text("batch_id IS NULL"),
        ),
        Index(
            "UQ_inventories_location_product_batch",
            "firm_id",
            "branch_id",
            "warehouse_id",
            "storage_locator",
            "product_id",
            "batch_id",
            unique=True,
            postgresql_where=text("batch_id IS NOT NULL"),
            sqlite_where=text("batch_id IS NOT NULL"),
        ),
        Index("IX_inventories_firm_product", "firm_id", "product_id"),
        Index("IX_inventories_firm_batch", "firm_id", "batch_id"),
        Index("IX_inventories_firm_status", "firm_id", "status"),
        Index("IX_inventories_firm_warehouse", "firm_id", "warehouse_id"),
        Index("IX_inventories_firm_branch", "firm_id", "branch_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    storage_locator: Mapped[str] = mapped_column(String(80), nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    #: The batch this stock belongs to, or NULL where the product is not
    #: batch-tracked. It is part of the row's identity, not a label: two
    #: batches of the same medicine in the same bay are different stock, and
    #: only one of them may be the one being recalled.
    batch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("batches.id", ondelete="RESTRICT")
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    current_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    available_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    blocked_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    damaged_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    quarantine_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    in_transit_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    display_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    display_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"), index=True
    )
    minimum_level: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    maximum_level: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    reorder_level: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    safety_stock: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    last_transaction_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    transactions: Mapped[list["InventoryTransaction"]] = relationship(
        back_populates="inventory",
        order_by="InventoryTransaction.created_at",
        lazy="selectin",
    )
    ledger_entries: Mapped[list["StockLedgerEntry"]] = relationship(
        back_populates="inventory",
        order_by="StockLedgerEntry.created_at",
        lazy="selectin",
    )


#: Movements are read as a chronology, so they need a clock that advances
#: within a request. ``BaseEntity.created_at`` uses ``func.now()``, which is the
#: transaction's start time -- identical for every row a request writes -- so
#: posting a delivery note gave its UNRESERVE and its DISPATCH the same instant
#: and the ledger could return them either way round. See
#: ``app/core/database/clock.py``.
def _movement_created_at() -> Mapped[datetime]:
    """Return a created_at that advances between statements."""
    return mapped_column(UTCDateTime, nullable=False, server_default=statement_now())


class InventoryTransaction(BaseEntity):
    """Persist one immutable inventory movement event."""

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        Index("IX_inventory_transactions_firm_date", "firm_id", "transaction_date"),
        Index("IX_inventory_transactions_firm_type", "firm_id", "transaction_type"),
        Index("IX_inventory_transactions_firm_product", "firm_id", "product_id"),
        Index("IX_inventory_transactions_firm_reference", "firm_id", "reference_type"),
    )

    inventory_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("inventories.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = _movement_created_at()
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    transaction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_number: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    current_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    reserved_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    blocked_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    damaged_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    quarantine_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    in_transit_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    #: How much the firm stopped or started owning, when that is not
    #: ``current_quantity_delta``. NULL means the two are the same, which is
    #: true of nearly every movement: stock arrives into the sellable bucket
    #: and leaves from it.
    #:
    #: It is persisted rather than derived because a reversal has to undo the
    #: valuation the original applied, and the buckets alone do not say what
    #: that was -- goods returned damaged are owned without being sellable,
    #: and quarantined goods stop being sellable without ceasing to be owned.
    owned_quantity_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    previous_current_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_current_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_available_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_available_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_blocked_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_blocked_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_damaged_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_damaged_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_quarantine_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_quarantine_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_in_transit_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_in_transit_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    entered_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    entered_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"), index=True
    )
    conversion_version: Mapped[int | None] = mapped_column()
    batch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("batches.id", ondelete="RESTRICT"), index=True
    )
    lot_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("lots.id", ondelete="RESTRICT"), index=True
    )
    serial_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("serial_numbers.id", ondelete="RESTRICT"), index=True
    )
    reversal_of_transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("inventory_transactions.id", ondelete="RESTRICT"),
        index=True,
    )

    inventory: Mapped[InventoryRecord] = relationship(back_populates="transactions")
    ledger_entries: Mapped[list["StockLedgerEntry"]] = relationship(
        back_populates="transaction",
        order_by="StockLedgerEntry.created_at",
        lazy="selectin",
    )


class StockLedgerEntry(BaseEntity):
    """Persist one immutable stock-ledger row per inventory transaction."""

    __tablename__ = "stock_ledger_entries"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id", name="UQ_stock_ledger_entries_transaction_id"
        ),
        Index("IX_stock_ledger_entries_firm_date", "firm_id", "transaction_date"),
        Index("IX_stock_ledger_entries_firm_product", "firm_id", "product_id"),
        Index("IX_stock_ledger_entries_firm_warehouse", "firm_id", "warehouse_id"),
        Index("IX_stock_ledger_entries_firm_type", "firm_id", "transaction_type"),
        Index("IX_stock_ledger_entries_firm_batch", "firm_id", "batch_id"),
    )

    transaction_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("inventory_transactions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    inventory_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("inventories.id", ondelete="RESTRICT"), nullable=False
    )
    #: The batch that moved. The ledger is where "what did batch B-2405 cost"
    #: and "where did it go" are answered, and it could answer neither.
    batch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("batches.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = _movement_created_at()
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    transaction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_number: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    current_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    reserved_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    blocked_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    damaged_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    quarantine_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    in_transit_quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default="0"
    )
    previous_current_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_current_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_available_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_available_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_blocked_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_blocked_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_damaged_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_damaged_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_quarantine_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_quarantine_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    previous_in_transit_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    new_in_transit_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    original_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    original_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"), index=True
    )
    base_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    average_cost_after: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))

    transaction: Mapped[InventoryTransaction] = relationship(
        back_populates="ledger_entries"
    )
    inventory: Mapped[InventoryRecord] = relationship(back_populates="ledger_entries")


class ProductValuation(BaseEntity):
    """Track the moving weighted-average cost of a product for a firm.

    The stock ledger recorded quantity buckets and no cost of any kind, so stock
    could not be valued and cost of goods sold did not exist. This is the running
    state the average is computed from.

    The grain is deliberately ``(firm, product)`` rather than per location: a
    per-warehouse average turns every stock transfer into a cost-movement
    problem, and a per-bin average is noise. The costing method is stored so a
    firm can move to FIFO later without this table changing shape.
    """

    __tablename__ = "product_valuations"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "product_id", name="UQ_product_valuations_firm_product"
        ),
        Index("IX_product_valuations_firm_product", "firm_id", "product_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    costing_method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="WEIGHTED_AVERAGE",
        server_default="WEIGHTED_AVERAGE",
    )
    quantity_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    average_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )


class OpeningStockBatch(BaseEntity):
    """Persist a draft or posted opening-stock document."""

    __tablename__ = "opening_stock_batches"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "reference_number", name="UQ_opening_stock_batches_reference"
        ),
        Index("IX_opening_stock_batches_firm_date", "firm_id", "posting_date"),
        Index("IX_opening_stock_batches_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    reference_number: Mapped[str] = mapped_column(String(80), nullable=False)
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_format: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MANUAL", server_default="MANUAL"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[date | None] = mapped_column(Date)

    lines: Mapped[list["OpeningStockLine"]] = relationship(
        back_populates="batch",
        order_by="OpeningStockLine.line_number",
        lazy="selectin",
        cascade="save-update, merge",
    )


class OpeningStockLine(BaseEntity):
    """Persist one opening-stock line before or after posting."""

    __tablename__ = "opening_stock_lines"
    __table_args__ = (
        UniqueConstraint(
            "opening_stock_batch_id",
            "line_number",
            name="UQ_opening_stock_lines_batch_line",
        ),
        # The batch is part of the key. Day-one stock of one product in one
        # bay is routinely two deliveries expiring months apart, and keying
        # without the batch made that impossible to record on one document.
        UniqueConstraint(
            "opening_stock_batch_id",
            "product_id",
            "storage_locator",
            "batch_number",
            name="UQ_opening_stock_lines_batch_product_location",
        ),
    )

    opening_stock_batch_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("opening_stock_batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    storage_locator: Mapped[str] = mapped_column(String(80), nullable=False)
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    #: What the day-one stock was worth per unit. Without it opening stock
    #: entered at zero value: the firm's whole starting inventory was worth
    #: nothing in the valuation and nothing in the ledger, which agreed with
    #: each other and with nothing real.
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    entered_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    entered_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"), index=True
    )
    conversion_version: Mapped[int | None] = mapped_column()
    #: What was written on the day-one paperwork, and what it resolved to.
    #: Opening stock is stock arriving, so it registers an unknown batch the
    #: way a goods receipt does rather than refusing it.
    batch_number: Mapped[str | None] = mapped_column(String(120))
    batch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("batches.id", ondelete="RESTRICT"), index=True
    )
    expiry_date: Mapped[date | None] = mapped_column(Date)
    minimum_level: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    maximum_level: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    reorder_level: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    safety_stock: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    remarks: Mapped[str | None] = mapped_column(Text)
    transaction_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("inventory_transactions.id", ondelete="RESTRICT"),
        nullable=True,
    )

    batch: Mapped[OpeningStockBatch] = relationship(back_populates="lines")
