"""Requests for quotation and supplier quotations (PG-8, backlog 86 #1)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class Rfq(BaseEntity):
    """One request for quotation, sent to several suppliers.

    ``DRAFT`` while its lines and suppliers are typed, ``SENT`` while quotes
    come in and a supplier is chosen per line, ``CLOSED`` once the orders are
    raised (or the RFQ is closed with nothing chosen), ``CANCELLED`` if it is
    called off. The status moves only through the transition endpoints.
    """

    __tablename__ = "rfqs"
    __table_args__ = (
        UniqueConstraint("firm_id", "rfq_number", name="UQ_rfqs_firm_rfq_number"),
        Index("IX_rfqs_firm_status", "firm_id", "status"),
        Index("IX_rfqs_firm_date", "firm_id", "rfq_date"),
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
    rfq_number: Mapped[str] = mapped_column(String(60), nullable=False)
    rfq_date: Mapped[date] = mapped_column(Date, nullable=False)
    required_by: Mapped[date | None] = mapped_column(Date)
    #: ``DRAFT``, ``SENT``, ``CLOSED`` or ``CANCELLED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    notes: Mapped[str | None] = mapped_column(Text)
    #: The approved requisition this RFQ was started from, if any.
    source_requisition_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_requisitions.id", ondelete="SET NULL"),
        index=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_by: Mapped[UUID | None] = mapped_column(UUIDType())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class RfqLine(BaseEntity):
    """One product asked about, and the quote chosen for it."""

    __tablename__ = "rfq_lines"
    __table_args__ = (
        UniqueConstraint("rfq_id", "line_number", name="UQ_rfq_lines_rfq_line"),
        Index("IX_rfq_lines_rfq", "rfq_id"),
    )

    rfq_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    #: The supplier quotation line chosen for this line. A bare id: the
    #: quotation lines already reference this table.
    selected_quotation_line_id: Mapped[UUID | None] = mapped_column(UUIDType())
    #: Why a quote other than the lowest was chosen; required then.
    selection_reason: Mapped[str | None] = mapped_column(Text)


class RfqSupplier(BaseEntity):
    """A supplier invited to quote, and the order raised on them."""

    __tablename__ = "rfq_suppliers"
    __table_args__ = (
        UniqueConstraint("rfq_id", "vendor_id", name="UQ_rfq_suppliers_rfq_vendor"),
        Index("IX_rfq_suppliers_rfq", "rfq_id"),
    )

    rfq_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    #: The draft order raised on this supplier from the chosen quotes.
    purchase_order_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("purchase_orders.id", ondelete="SET NULL")
    )


class SupplierQuotation(BaseEntity):
    """One supplier's answer to an RFQ: one per RFQ and supplier."""

    __tablename__ = "supplier_quotations"
    __table_args__ = (
        UniqueConstraint(
            "rfq_id", "vendor_id", name="UQ_supplier_quotations_rfq_vendor"
        ),
        Index("IX_supplier_quotations_rfq", "rfq_id"),
    )

    rfq_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    quote_ref: Mapped[str | None] = mapped_column(String(80))
    quote_date: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class SupplierQuotationLine(BaseEntity):
    """The rate a supplier quoted for one RFQ line."""

    __tablename__ = "supplier_quotation_lines"
    __table_args__ = (
        UniqueConstraint(
            "quotation_id",
            "rfq_line_id",
            name="UQ_supplier_quotation_lines_quotation_rfq_line",
        ),
        Index("IX_supplier_quotation_lines_quotation", "quotation_id"),
    )

    quotation_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("supplier_quotations.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    rfq_line_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("rfq_lines.id", ondelete="CASCADE"), nullable=False
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
