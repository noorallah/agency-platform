"""Settlement persistence models: money arriving, and money going out.

A settlement is one movement of money against a party -- a receipt from a
customer or a payment to a vendor -- together with the invoices it clears.

Both directions are one table because they are the same document with the
signs reversed. Splitting them would double every rule that matters (the
allocation cannot exceed the amount, the amount must reach the ledger, an
invoice cannot be over-cleared) and the two copies would drift, which is what
happened to the seven transactional document modules before they were given a
shared base.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class SettlementDirection(StrEnum):
    """Which way the money went."""

    RECEIPT = "RECEIPT"
    PAYMENT = "PAYMENT"
    #: Money back to a customer. It is money out like a payment and
    #: about a customer like a receipt, which is why it is neither of
    #: them: refunding a customer reduces what they have paid in
    #: advance rather than settling anything the firm owes a supplier.
    REFUND = "REFUND"


class SettlementMethod(StrEnum):
    """How the money moved, which decides the account it lands in."""

    CASH = "CASH"
    BANK = "BANK"


class SettlementStatus(StrEnum):
    """The lifecycle of a settlement.

    Two states, and no approval between them: a settlement is recorded after
    the money has moved, so there is nothing to decide. A mistake is taken back
    rather than edited -- the original stays, a mirror journal cancels it, and
    both are visible. Money that was recorded and then unrecorded is a fact
    about the day, not something to erase.
    """

    POSTED = "POSTED"
    REVERSED = "REVERSED"


class Settlement(BaseEntity):
    """Store one receipt from a customer or payment to a vendor."""

    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "settlement_number", name="UQ_settlements_firm_number"
        ),
        # Exactly one party, and it is the one the direction implies. A receipt
        # from a vendor is not a thing this document records.
        CheckConstraint(
            "(direction IN ('RECEIPT', 'REFUND') AND customer_id IS "
            "NOT NULL AND vendor_id IS NULL) OR (direction = 'PAYMENT' "
            "AND vendor_id IS NOT NULL AND customer_id IS NULL)",
            name="CK_settlements_party_matches_direction",
        ),
        CheckConstraint("amount > 0", name="CK_settlements_amount_positive"),
        Index("IX_settlements_firm_direction", "firm_id", "direction"),
        Index("IX_settlements_firm_date", "firm_id", "settlement_date"),
        Index("IX_settlements_firm_customer", "firm_id", "customer_id"),
        Index("IX_settlements_firm_vendor", "firm_id", "vendor_id"),
        Index("IX_settlements_firm_order", "firm_id", "sales_order_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT")
    )
    settlement_number: Mapped[str] = mapped_column(String(60), nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: What was allocated to invoices, and what was not. The remainder is an
    #: advance: money held against nothing in particular, which is a normal
    #: thing for a customer to send and has to be visible rather than inferred.
    allocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    unallocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    #: Tax deducted at source out of ``amount`` (backlog 53.1): the part of
    #: what settles the party that never moved as money. On a payment the firm
    #: deducted it and owes it to the government (TDS Payable); on a receipt
    #: the customer deducted it and the firm claims it (TDS Receivable). The
    #: cash or bank leg is ``amount - tds_amount``; the party is settled for
    #: the whole ``amount``, as Tally's voucher does.
    tds_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    #: The section it is filed under (``app.finance.tds.TDS_SECTIONS``).
    tds_section: Mapped[str | None] = mapped_column(String(10))
    #: The rest of ``amount`` that settled the bills without moving as money
    #: (backlog 74 row 2), each posted to its own account: a receipt a few
    #: rupees short or a payment rounded off (``ROUNDING``), what a customer's
    #: bank took on the way (``BANK_CHARGES``, receipts only), and a discount
    #: allowed on a receipt or received on a payment. The cash or bank leg is
    #: ``amount - tds_amount`` less these three; the party is settled for the
    #: whole ``amount``, exactly as with TDS. None of them touches tax -- a
    #: reduction in the value of a supply is a credit or debit note.
    rounding_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    bank_charges_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The cash or bank account the money actually moved through, resolved from
    #: the firm's control accounts at the time and then stored. Re-deriving it
    #: later would rewrite history if the mapping is ever changed.
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: The order this money came in against, where it came in against one.
    #:
    #: A note about *why* the money arrived, not a ring-fence around it. The
    #: cash is the customer's balance either way: if the order is cancelled the
    #: deposit does not vanish, it stays on account. Recording the order is
    #: what makes "what has this customer paid us for order X" answerable, and
    #: what lets the bill for that order find the deposit when it is raised.
    sales_order_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_orders.id", ondelete="RESTRICT")
    )
    instrument_reference: Mapped[str | None] = mapped_column(String(120))
    #: How the money moved within its method (backlog ACC-3): CASH, CHEQUE,
    #: UPI, BANK_TRANSFER, CARD, DEMAND_DRAFT or OTHER. NULL on a bank
    #: settlement recorded before the mode was asked for.
    payment_mode: Mapped[str | None] = mapped_column(String(20))
    #: The cheque's or draft's own date, which is not the day it was recorded.
    instrument_date: Mapped[date | None] = mapped_column(Date)
    narration: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SettlementStatus.POSTED.value
    )
    #: The mirror journal that cancelled this one, and why. Set together with
    #: the status so a reversed settlement can always show what undid it.
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reversed_by: Mapped[UUID | None] = mapped_column(UUIDType())
    reversal_reason: Mapped[str | None] = mapped_column(Text())
    #: The journal this wrote. A settlement that did not reach the ledger is
    #: the defect this module exists to fix, so the link is not optional.
    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )


class SettlementAllocation(BaseEntity):
    """Store how much of one settlement cleared one invoice."""

    __tablename__ = "settlement_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="CK_settlement_allocations_positive"),
        # One row per settlement per invoice: two lines against the same
        # invoice are one allocation, and keeping them apart would make the
        # outstanding arithmetic depend on how somebody typed it.
        UniqueConstraint(
            "settlement_id",
            "sales_invoice_id",
            name="UQ_settlement_allocations_sales_invoice",
        ),
        UniqueConstraint(
            "settlement_id",
            "purchase_invoice_id",
            name="UQ_settlement_allocations_purchase_invoice",
        ),
        Index("IX_settlement_allocations_sales", "firm_id", "sales_invoice_id"),
        Index("IX_settlement_allocations_purchase", "firm_id", "purchase_invoice_id"),
        UniqueConstraint(
            "settlement_id",
            "vendor_opening_bill_id",
            name="UQ_settlement_allocations_opening_bill",
        ),
        Index(
            "IX_settlement_allocations_opening_bill",
            "firm_id",
            "vendor_opening_bill_id",
        ),
        UniqueConstraint(
            "settlement_id",
            "customer_opening_bill_id",
            name="UQ_settlement_allocations_customer_opening_bill",
        ),
        Index(
            "IX_settlement_allocations_customer_opening_bill",
            "firm_id",
            "customer_opening_bill_id",
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    settlement_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("settlements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sales_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_invoices.id", ondelete="RESTRICT")
    )
    purchase_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("purchase_invoices.id", ondelete="RESTRICT")
    )
    #: A payment against what a supplier was owed before the firm started
    #: here. It is a bill to the payment screen, but not a purchase invoice --
    #: see `VendorOpeningBill` for why it cannot be one.
    vendor_opening_bill_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendor_opening_bills.id", ondelete="RESTRICT")
    )
    #: A receipt against what a customer owed before the firm started here --
    #: the receivable twin of the column above; see `CustomerOpeningBill`.
    customer_opening_bill_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customer_opening_bills.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: The day the money met the bill. For an allocation made with the
    #: settlement it is the settlement's own date; for an advance applied to a
    #: bill raised since (`allocate`) it is the day the bill existed to be
    #: settled, which is later. Commission and sales targets count a
    #: collection in the period of this date, not the settlement's: an
    #: advance taken in August and applied to a September bill is September's
    #: collection (D-TER-6). Nullable because rows written before the column
    #: existed carry nothing; readers fall back to the settlement date, which
    #: is what the backfill wrote.
    allocated_on: Mapped[date | None] = mapped_column(Date)


class SupplierCreditApplication(BaseEntity):
    """Store how much of one purchase return's supplier credit cleared one bill.

    A completed purchase return debits accounts payable with its whole total.
    Where its lines name the supplier's bill, that bill owes less (D-BUY-6).
    Where they name the goods receipt instead, the debit is a credit the
    supplier owes the firm, standing on the vendor's account until it is set
    against a bill -- the payable twin of a customer's advance (D-FIN-19).

    What a return has left to give is derived: its total, less what its
    bill-sourced lines already took off their bills, less its live rows here.
    Applying posts nothing, exactly as applying a customer's advance posts
    nothing: the return already debited payables and the bill already credited
    them, and this row only says which bill the debit belongs to. A row is
    withdrawn (soft-deleted) when either the return or the bill is cancelled.
    """

    __tablename__ = "supplier_credit_applications"
    __table_args__ = (
        CheckConstraint("amount > 0", name="CK_supplier_credit_applications_positive"),
        CheckConstraint(
            "(purchase_return_id IS NULL) <> (debit_note_id IS NULL)",
            name="CK_supplier_credit_applications_one_source",
        ),
        Index(
            "IX_supplier_credit_applications_return", "firm_id", "purchase_return_id"
        ),
        Index("IX_supplier_credit_applications_debit_note", "firm_id", "debit_note_id"),
        Index(
            "IX_supplier_credit_applications_invoice", "firm_id", "purchase_invoice_id"
        ),
        Index("IX_supplier_credit_applications_vendor", "firm_id", "vendor_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    #: The source of the credit: a purchase return, or (A4) a debit note.
    #: Exactly one of the two is set.
    purchase_return_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("purchase_returns.id", ondelete="RESTRICT")
    )
    debit_note_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("debit_notes.id", ondelete="RESTRICT")
    )
    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    applied_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)


class SupplierCreditRefund(BaseEntity):
    """Money a supplier paid back against one return's credit (69 row 7).

    A purchase return whose outcome is a refund leaves its credit on the
    supplier's account until the money arrives. Receiving it posts ``Dr cash or
    bank / Cr accounts payable`` -- the payable the return debited comes back
    to nil -- and uses that much of the return's credit, exactly as setting it
    against a bill does. Reversing posts the mirror and frees the credit.
    """

    __tablename__ = "supplier_credit_refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="CK_supplier_credit_refunds_positive"),
        CheckConstraint(
            "(purchase_return_id IS NULL) <> (debit_note_id IS NULL)",
            name="CK_supplier_credit_refunds_one_source",
        ),
        Index("IX_supplier_credit_refunds_return", "firm_id", "purchase_return_id"),
        Index("IX_supplier_credit_refunds_debit_note", "firm_id", "debit_note_id"),
        Index("IX_supplier_credit_refunds_vendor", "firm_id", "vendor_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    #: The source of the credit, as on an application: exactly one is set.
    purchase_return_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("purchase_returns.id", ondelete="RESTRICT")
    )
    debit_note_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("debit_notes.id", ondelete="RESTRICT")
    )
    refunded_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: ``CASH`` or ``BANK``, which decides the account the money landed in.
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    ledger_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: The cheque, UTR or note the supplier's money came with.
    reference: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    #: ``POSTED`` or ``REVERSED``.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="POSTED", server_default="POSTED"
    )
    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reversal_reason: Mapped[str | None] = mapped_column(Text)
