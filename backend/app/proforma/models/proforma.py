"""A bill that is not a bill: what an order will be charged, stated in advance.

A buyer needs a document before the goods move -- to open a letter of credit,
to get a payment approved, to clear customs, to release funds against an
advance. A quotation is an offer and a tax invoice is a demand; the thing in
between is a proforma, and this system had no way to produce one.

**It posts nothing, and the absence is the design.** There is no
`journal_entry_id` and no `receivable_transaction_id` on this table, because a
proforma raises no revenue, no output tax, no receivable and no stock movement.
Adding either column later would be the first step towards a document that
looks like a bill to the books as well as to the customer.

**It takes its number from its own series, never the tax invoice's.** GSTR-1's
DOCS section declares the invoice series a firm issued, so a proforma drawing
from that series would either leave a gap the return cannot explain or put a
number in it that was never a supply. `PROFORMA_INVOICE` is a document type of
its own, with its own prefix.

**Once issued it cannot be edited.** The customer may already be arranging
payment against the number on it, and a document that quietly changed under
them is worse than a second one that says it replaces the first. A revision is
a new proforma, with `supersedes_id` pointing back.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
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


class ProformaStatus(StrEnum):
    """Where a proforma stands.

    Short on purpose. A proforma has no approval of its own -- the order it
    states was already approved -- so the only questions are whether it has
    gone to the customer and whether it still stands.
    """

    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    CANCELLED = "CANCELLED"


class ProformaInvoice(BaseEntity):
    """One statement of what a sales order will be billed at."""

    __tablename__ = "proforma_invoices"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "proforma_number", name="UQ_proforma_invoices_number"
        ),
        CheckConstraint("grand_total >= 0", name="CK_proforma_invoices_total"),
        Index("IX_proforma_invoices_firm_customer", "firm_id", "customer_id"),
        Index("IX_proforma_invoices_firm_order", "firm_id", "sales_order_id"),
        Index("IX_proforma_invoices_firm_status", "firm_id", "status"),
    )

    #: No foreign key: `firms` lives only in the platform schema and this table
    #: lives in every firm store.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    #: Mandatory. A proforma states what a *particular* deal will be charged;
    #: one raised out of nothing is a quotation wearing the wrong name, and
    #: this module already has a quotation.
    sales_order_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    proforma_number: Mapped[str] = mapped_column(String(60), nullable=False)
    proforma_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: How long the stated prices stand. Nullable: a firm shipping against a
    #: standing arrangement has no deadline to give.
    valid_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ProformaStatus.DRAFT.value,
        server_default=ProformaStatus.DRAFT.value,
    )
    customer_reference: Mapped[str | None] = mapped_column(String(80))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    delivery_terms: Mapped[str | None] = mapped_column(String(200))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    remarks: Mapped[str | None] = mapped_column(Text)

    line_discount_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    bill_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )

    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    #: The proforma this one replaces. A revision is a new document rather
    #: than an edit, because the customer may already be arranging payment
    #: against the number on the old one.
    supersedes_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("proforma_invoices.id", ondelete="RESTRICT")
    )

    # Deliberately absent: `journal_entry_id` and `receivable_transaction_id`.
    # A proforma posts nothing, and there is nowhere here to record that it
    # did. Adding either is the first step towards a document that looks like
    # a bill to the books as well as to the customer.


class ProformaInvoiceLine(BaseEntity):
    """One line of a proforma, snapshotted from the order line it states.

    A snapshot rather than a reference. The order can be edited after the
    proforma goes out -- withdrawing its approval as it does -- and a document
    the customer is paying against must not change underneath them.
    """

    __tablename__ = "proforma_invoice_lines"
    __table_args__ = (
        UniqueConstraint(
            "proforma_invoice_id",
            "line_number",
            name="UQ_proforma_invoice_lines_number",
        ),
        CheckConstraint("quantity >= 0", name="CK_proforma_invoice_lines_quantity"),
        Index("IX_proforma_invoice_lines_firm", "firm_id"),
    )

    proforma_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("proforma_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500))
    #: A bare UUID with no foreign key, the way every downstream document in
    #: this repo records its source: the order's lines are reconciled on their
    #: line number and can be re-inserted.
    source_sales_order_line_id: Mapped[UUID | None] = mapped_column(UUIDType())
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    #: Goods stated at nil value. Outside the gross and outside the tax base,
    #: and a proforma that dropped them would understate what is being shipped.
    free_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    bill_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
