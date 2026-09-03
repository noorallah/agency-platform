"""Sales quotation persistence models.

A quotation is an offer, and an offer commits nothing. It reserves no stock,
puts nothing on a customer's account and writes no journal -- which is the
whole difference between it and the sales order it may become. Everything the
firm actually promises happens at conversion, through
``SalesOrderService.create_order``, so the rules that govern an order are
applied when the order exists rather than months earlier when somebody quoted
a price.

The one thing a quotation owns that an order does not is an expiry: a price
offered in April is not a price offered in December, and ``valid_until`` is
what stops a stale quote being turned into an order at last year's rate.
"""

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


class SalesQuotation(BaseEntity):
    """Store one quotation header."""

    __tablename__ = "sales_quotations"
    __table_args__ = (
        UniqueConstraint(
            "firm_id",
            "quotation_number",
            name="UQ_sales_quotations_firm_quotation_number",
        ),
        Index("IX_sales_quotations_firm_status", "firm_id", "status"),
        Index("IX_sales_quotations_firm_date", "firm_id", "quotation_date"),
        Index("IX_sales_quotations_firm_customer", "firm_id", "customer_id"),
        Index("IX_sales_quotations_firm_valid_until", "firm_id", "valid_until"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    salesman_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="RESTRICT")
    )
    territory_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_territories.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    #: Carried so the order this becomes has one. A quotation reserves nothing
    #: from it -- naming the warehouse is a statement about where the goods
    #: would ship from, not a claim on them.
    warehouse_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    quotation_number: Mapped[str] = mapped_column(String(60), nullable=False)
    quotation_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: The last day the quoted prices stand. Past it a quotation can be read
    #: and reissued but not turned into an order.
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    customer_reference: Mapped[str | None] = mapped_column(String(80))
    reference_number: Mapped[str | None] = mapped_column(String(80))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    delivery_terms: Mapped[str | None] = mapped_column(String(200))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    remarks: Mapped[str | None] = mapped_column(Text)
    #: The customer's standing discount when this document was raised. The
    #: rate is a starting point and every line may override it, so this says
    #: what it would have been rather than what any line was charged.
    customer_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    #: A discount on the whole document, negotiated once rather than typed on
    #: every line. It comes off what the lines discounted to, and each line
    #: carries its share so the tax is charged on the discounted value.
    bill_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    bill_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: What the customer is charged for getting the goods to them.
    #:
    #: **Part of the taxable value, not an extra on the end.** Delivery charged
    #: by the seller is ancillary to the supply of the goods, so it is taxed at
    #: the goods' own rate -- which is what apportioning it across the lines
    #: achieves. `additional_charges` sits outside the tax and stays that way:
    #: it is for genuinely non-taxable additions, and silently re-taxing it
    #: would change the meaning of every document that carries one.
    #:
    #: The mirror image of `bill_discount_amount`, and it uses the same
    #: `apportion`: one reduces each line's taxable value and the other raises
    #: it, and both give the rounding residual to the largest line so the
    #: shares sum exactly to the header figure.
    freight_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    line_discount_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    additional_charges: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    round_off: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The order this quotation became. A bare id with no foreign key, the
    #: convention every cross-document reference here follows.
    converted_sales_order_id: Mapped[UUID | None] = mapped_column(UUIDType())
    converted_sales_order_number: Mapped[str | None] = mapped_column(String(60))
    #: Why the customer said no. Kept because the answer to "why are we losing
    #: quotes" is not in any total.
    decline_reason: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class SalesQuotationLine(BaseEntity):
    """Store one quotation line."""

    __tablename__ = "sales_quotation_lines"
    __table_args__ = (
        UniqueConstraint(
            "sales_quotation_id",
            "line_number",
            name="UQ_sales_quotation_lines_quotation_line",
        ),
        Index("IX_sales_quotation_lines_firm_product", "firm_id", "product_id"),
    )

    sales_quotation_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    free_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    sales_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    inventory_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    packaging_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("packaging_types.id", ondelete="RESTRICT")
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
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("tax_profiles.id", ondelete="RESTRICT")
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: This line's share of the document's bill discount. Stored rather than
    #: derived at print time, because it is what the tax was computed on.
    bill_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: This line's share of the document's freight, in proportion to what the
    #: line is worth after its own discounts. Stored rather than derived at
    #: print time, for the reason the bill discount's share is: the tax was
    #: charged on it, so the number has to survive.
    freight_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    remarks: Mapped[str | None] = mapped_column(Text)


class SalesQuotationAttachment(BaseEntity):
    """Store quotation attachments."""

    __tablename__ = "sales_quotation_attachments"

    sales_quotation_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    attachment_kind: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="QUOTATION_FILE",
        server_default="QUOTATION_FILE",
    )


class SalesQuotationNote(BaseEntity):
    """Store quotation notes."""

    __tablename__ = "sales_quotation_notes"

    sales_quotation_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    note_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="INTERNAL", server_default="INTERNAL"
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
