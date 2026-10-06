"""Sales invoice persistence models."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class SalesInvoice(BaseEntity):
    """Store one customer invoice header."""

    __tablename__ = "sales_invoices"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "invoice_number", name="UQ_sales_invoices_firm_invoice_number"
        ),
        Index("IX_sales_invoices_firm_status", "firm_id", "status"),
        Index("IX_sales_invoices_firm_date", "firm_id", "invoice_date"),
        Index("IX_sales_invoices_firm_customer", "firm_id", "customer_id"),
        Index("IX_sales_invoices_firm_branch", "firm_id", "branch_id"),
        Index("IX_sales_invoices_firm_due_date", "firm_id", "due_date"),
        # Backlog 56 C: the list's default sort, newest first.
        Index("IX_sales_invoices_firm_created", "firm_id", "created_at"),
        # A shift's summary reads its bills (SG-7).
        Index("IX_sales_invoices_counter_shift", "counter_shift_id"),
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
    route_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("territory_route_profiles.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id", ondelete="RESTRICT")
    )
    invoice_number: Mapped[str] = mapped_column(String(60), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_invoice_number: Mapped[str | None] = mapped_column(String(120))
    #: Where the goods go: one of the customer's own addresses (backlog 67
    #: row 3). A bare id, validated by ``app/customers/services/ship_to.py``
    #: when it is set, so a document still prints the address it named after
    #: the address is deleted. NULL only for a customer with no shipping
    #: address, which ships to the billing address as before.
    shipping_address_id: Mapped[UUID | None] = mapped_column(UUIDType())
    #: The state the supply was made in, copied from the customer's billing
    #: address when the invoice is raised. It decides CGST + SGST against IGST,
    #: and it is stored rather than derived because a customer who moves must
    #: not silently change the tax treatment of an invoice already issued.
    place_of_supply: Mapped[str | None] = mapped_column(String(120))
    #: The buyer's GST registration type when the bill was raised (backlog 75
    #: row 2): REGULAR, SEZ_WITHOUT_PAYMENT and so on. Stamped with the place
    #: of supply, because it decides the return table and the e-invoice supply
    #: type; NULL on bills raised before it, which read the customer instead.
    buyer_gst_registration_type: Mapped[str | None] = mapped_column(String(30))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    reference_number: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    allow_direct_sales_order: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Retired (D-SELL-30): a bill may never charge for more than was
    # delivered or ordered, and no request can say otherwise. The columns
    # stay so no migration is needed; nothing reads or writes them.
    allow_over_invoice: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    over_invoice_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    total_source_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_already_invoiced_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_current_invoice_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: A discount on the whole document, negotiated once rather than typed on
    #: every line. It comes off what the lines discounted to, and each line
    #: carries its share so the tax is charged on the discounted value.
    #: How much was supplied free across the document. A statement, not a
    #: movement: the delivery note moved the goods.
    total_free_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    bill_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    bill_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: Where `bill_discount_amount` came from: ``typed`` when the bill itself
    #: stated it, ``inherited`` when it is the share of the discount agreed on
    #: the documents the bill continues, NULL when there is none. Only a typed
    #: one is judged against the approver's discount limit and carried across
    #: an edit that leaves it out (D-PRC-1).
    bill_discount_source: Mapped[str | None] = mapped_column(String(20))
    #: How the bill discount was last stated on the bill: ``amount`` or
    #: ``percent``; NULL where the bill never stated one. The header keeps
    #: both figures and they look the same either way, but they are not the
    #: same instruction: somebody who typed 25.00 off means 25.00 on whatever
    #: the lines come to, and a four-place rate carried across an edit gave
    #: them 25.0001 (D-PRC-35). An edit that leaves the discount out carries
    #: it as this says; NULL carries the rate, as every bill did before.
    bill_discount_typed_as: Mapped[str | None] = mapped_column(String(10))
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
    #: Money taken at the counter as the bill is made (backlog 64 row 5):
    #: approving the bill records a receipt for it against this invoice, in
    #: the same transaction, so a counter sale is settled the moment it is.
    received_now_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: CASH or BANK, as a receipt's method.
    received_now_method: Mapped[str | None] = mapped_column(String(10))
    received_now_reference: Mapped[str | None] = mapped_column(String(120))
    #: Who a walk-in bill was made out to (backlog 87 #2): typed at the
    #: counter and printed in place of the *Cash sale* customer's own name.
    #: Null on a bill to a customer with a record.
    buyer_name: Mapped[str | None] = mapped_column(String(200))
    buyer_phone: Mapped[str | None] = mapped_column(String(30))
    #: The receipt approval recorded; set once, never re-recorded.
    received_now_settlement_id: Mapped[UUID | None] = mapped_column(UUIDType())
    #: Whether the rates typed on this bill include GST (backlog 64 row 4). A
    #: typed rate is then stored as its pre-tax equivalent in each line's
    #: ``unit_price`` and kept as typed in ``entered_rate``; a line continuing
    #: an order or a delivery note keeps the price it inherited.
    rate_includes_tax: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: A counter bill parked while the next customer is served (backlog 87
    #: #7, SG-7). **A flag, not a status**: the bill is still the draft it
    #: was, and recalling it puts nothing back. A held bill is never approved.
    is_held: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: What the cashier typed to know the bill again: "lady in red, back in
    #: five minutes".
    held_note: Mapped[str | None] = mapped_column(String(200))
    #: The cashier's shift the bill's counter money was taken in (SG-7):
    #: stamped at approval when whoever approves has a shift open, NULL for a
    #: firm that opens none.
    counter_shift_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "counter_shifts.id",
            ondelete="RESTRICT",
            name="FK_sales_invoices_counter_shift_id",
        ),
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When it was cancelled, so an ageing as of an earlier day still
    #: counts what was owed then (D-FIN-21).
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    close_reason: Mapped[str | None] = mapped_column(Text)


class SalesInvoiceSource(BaseEntity):
    """Store customer invoice source document references."""

    __tablename__ = "sales_invoice_sources"
    __table_args__ = (
        UniqueConstraint(
            "sales_invoice_id",
            "source_document_type",
            "source_document_id",
            name="UQ_sales_invoice_sources_document",
        ),
        Index("IX_sales_invoice_sources_invoice", "sales_invoice_id"),
    )

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    source_document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_number: Mapped[str] = mapped_column(String(80), nullable=False)
    source_document_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )


class SalesInvoiceLine(BaseEntity):
    """Store one sales invoice line."""

    __tablename__ = "sales_invoice_lines"
    __table_args__ = (
        UniqueConstraint(
            "sales_invoice_id",
            "line_number",
            name="UQ_sales_invoice_lines_invoice_line",
        ),
        Index("IX_sales_invoice_lines_invoice", "sales_invoice_id"),
        Index(
            "IX_sales_invoice_lines_firm_source", "firm_id", "source_document_line_id"
        ),
        Index("IX_sales_invoice_lines_firm_product", "firm_id", "product_id"),
    )

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_number: Mapped[str] = mapped_column(String(80), nullable=False)
    source_document_line_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_document_line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    #: The HSN or SAC code the line was billed under (D-CMP-22). Stamped from
    #: the product when the line is written, so correcting a product's code
    #: later does not rewrite the HSN summary of a month already filed or
    #: reprint an old bill with a code it was not issued with.
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(String(500))
    delivered_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    already_invoiced_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    current_invoice_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The rate as typed, GST included, where the bill's ``rate_includes_tax``
    #: read it so (backlog 64 row 4); ``unit_price`` is the pre-tax rate it
    #: derived to, which is what every posting and return reads. Null on a
    #: line whose rate was not typed inclusive.
    entered_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: ``percent`` or ``amount`` when the bill itself said so, ``inherited``
    #: when it took the order's or the note's, ``none`` when nothing applied.
    #: Only a typed discount is judged against the approver's limit (backlog
    #: 64 row 3): an inherited one was judged when its order was approved.
    #: NULL on lines written before it existed.
    discount_source: Mapped[str | None] = mapped_column(String(20))
    charges_amount: Mapped[Decimal] = mapped_column(
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
    #: Supplied free with this line. Excluded from `gross_amount` and from
    #: the tax base -- nothing is charged for it -- but stated on the bill,
    #: because a customer who receives eleven and is billed for ten asks why.
    free_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
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
    #: What these goods cost the firm, snapshotted when the bill was raised.
    #:
    #: **Nullable, and NULL is not zero.** NULL means no cost could be traced
    #: -- an invoice raised straight off an order has no dispatch behind it,
    #: so nothing moved and nothing was costed. Zero would mean the goods were
    #: free, and a margin rule reading one as the other pays commission on the
    #: whole sale price as though the firm had bought the goods for nothing.
    #:
    #: Snapshotted rather than derived on demand because the moving average
    #: moves: re-reading it in September would answer about September, and a
    #: payout approved in March would then disagree with the report beside it.
    #: That is the same reason a payout is snapshotted at accrual.
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    packaging_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("packaging_types.id", ondelete="RESTRICT")
    )
    order_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    invoice_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT")
    )
    #: What was typed, in ``invoice_uom_id``, where that is another unit than the
    #: line this one continues: 7 for seven pieces of a line delivered by the
    #: box. ``current_invoice_quantity`` beside it is the same goods in the
    #: source line's unit at four places (0.5833), which is what the caps
    #: count; the line is priced, moved and printed from this one, because
    #: 0.5833 of a box is not seven pieces (D-PRC-37). Null on a line typed
    #: in its source line's own unit, and on every line written before it.
    entered_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    conversion_factor: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), nullable=False, default=Decimal("1"), server_default="1"
    )
    conversion_version: Mapped[int | None] = mapped_column(Integer)
    warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    storage_node_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouse_storage_nodes.id", ondelete="RESTRICT")
    )
    batch_number: Mapped[str | None] = mapped_column(String(120))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    remarks: Mapped[str | None] = mapped_column(Text)
    accounting_event_reference: Mapped[str | None] = mapped_column(String(120))
    #: The tax rule that decided the line, by code and version_number; null
    #: when the profile alone did (GST-8). Kept here because the execution
    #: log that also says so is purged.
    tax_rule_code: Mapped[str | None] = mapped_column(String(50))
    tax_rule_version: Mapped[int | None] = mapped_column(Integer)


class SalesInvoiceLineTax(BaseEntity):
    """Store the tax components one invoice line was actually charged.

    A line has always carried a single `tax_amount`, which is what the customer
    pays and is useless on a printed bill: a tax invoice has to state each
    component -- CGST 9% 90.00, SGST 9% 90.00 -- and the rate it was charged at.
    That breakup was computed by the rule engine at save time and then thrown
    away, surviving only in `tax_rule_execution_logs`, which the retention job
    prunes. Rules are effective-dated, so re-deriving it at print time can
    disagree with what the customer was billed; the only honest answer is to
    keep what was charged, on the document that charged it.

    `tax_component_id` carries no foreign key on purpose. It says which
    catalogue row produced this line at the time, and the catalogue moves on --
    a RESTRICT would stop a firm ever retiring a component, and a CASCADE would
    erase the evidence. The code, label and percentage beside it are the record.
    """

    __tablename__ = "sales_invoice_line_taxes"
    __table_args__ = (
        Index("IX_sales_invoice_line_taxes_line", "sales_invoice_line_id"),
        Index("IX_sales_invoice_line_taxes_firm", "firm_id"),
    )

    sales_invoice_line_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoice_lines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tax_component_id: Mapped[UUID | None] = mapped_column(UUIDType())
    component_code: Mapped[str] = mapped_column(String(40), nullable=False)
    component_label: Mapped[str] = mapped_column(String(120), nullable=False)
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    base_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: Tax already inside the price, which the bill shows but does not add.
    included_in_price: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Whether the buyer may claim it as input credit.
    recoverable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class SalesInvoiceTender(BaseEntity):
    """One way a counter bill was paid: cash, UPI or card (SEL-12, A90).

    A counter bill is often paid partly in cash and partly by UPI. Each tender
    becomes its own receipt when the bill is approved -- cash to the cash
    account, UPI or card to the bank -- so the cash book and the bank book each
    read only what reached them. Replaced whole while the bill is a draft.
    """

    __tablename__ = "sales_invoice_tenders"
    __table_args__ = (Index("IX_sales_invoice_tenders_invoice", "sales_invoice_id"),)

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    #: CASH, UPI, CARD or BANK_TRANSFER.
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    #: The receipt approval recorded for this tender.
    settlement_id: Mapped[UUID | None] = mapped_column(UUIDType())


class SalesInvoiceCharge(BaseEntity):
    """One charge on a bill taxed at a rate of its own (backlog 87 #4, SG-4).

    Packing, handling, insurance: named, priced before tax and taxed by the
    profile it names, where freight is split across the goods and taxed at
    their rates and ``additional_charges`` carries no tax at all. The tax is
    kept by GST head, as charged, so the posting, the print and the returns
    read what the customer was billed rather than re-deriving it. Replaced
    whole while the bill is a draft.
    """

    __tablename__ = "sales_invoice_charges"
    __table_args__ = (Index("IX_sales_invoice_charges_invoice", "sales_invoice_id"),)

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey(
            "sales_invoices.id",
            ondelete="CASCADE",
            name="FK_sales_invoice_charges_sales_invoice_id",
        ),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: The SAC the charge is declared under in the HSN summary.
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    #: What is charged, before tax.
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: NULL is a charge outside GST; a profile that charges nothing is exempt.
    tax_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(),
        ForeignKey(
            "tax_profiles.id",
            ondelete="RESTRICT",
            name="FK_sales_invoice_charges_tax_profile_id",
        ),
    )
    #: The GST rate charged, cess apart: nine plus nine is eighteen.
    tax_rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    cgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    sgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    cess_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )


class SalesInvoiceAttachment(BaseEntity):
    """Store sales invoice attachments."""

    __tablename__ = "sales_invoice_attachments"
    __table_args__ = (
        Index("IX_sales_invoice_attachments_invoice", "sales_invoice_id"),
    )

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
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
        default="SALES_INVOICE_FILE",
        server_default="SALES_INVOICE_FILE",
    )


class SalesInvoiceNote(BaseEntity):
    """Store sales invoice notes."""

    __tablename__ = "sales_invoice_notes"
    __table_args__ = (Index("IX_sales_invoice_notes_invoice", "sales_invoice_id"),)

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
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


class SalesInvoiceAccountingEvent(BaseEntity):
    """Store accounting events generated by sales invoice lifecycle."""

    __tablename__ = "sales_invoice_accounting_events"
    __table_args__ = (
        Index("IX_sales_invoice_accounting_events_invoice", "sales_invoice_id"),
        Index("IX_sales_invoice_accounting_events_type", "firm_id", "event_type"),
    )

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)
    direction: Mapped[str] = mapped_column(String(12), nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    narration: Mapped[str | None] = mapped_column(Text)
    source_line_id: Mapped[UUID | None] = mapped_column(UUIDType())
