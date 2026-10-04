"""A TDS challan: the deposit that pays the government what the firm deducted.

ACC-7 (backlog 53.1, decision A79). Tax deducted at source on a payment or an
expense sits in *TDS Payable* until the firm deposits it with challan ITNS 281,
by the seventh of the next month. The bank's counterfoil names the deposit by
three things together -- the branch's **BSR code** (seven digits), the **date**
it was tendered and the bank's **challan serial** (five digits) -- which is
the Challan Identification Number (CIN) the quarterly return files every
deduction under. A challan pays tax under **one section**, as ITNS 281 asks
for the nature of payment, so it gathers that section's deductions.

It posts on save, as a contra voucher does: the money has left by the time it
is recorded. Dr TDS Payable for the tax, Dr *Interest and Fees on TDS* for any
interest (section 201(1A)) and late fee (234E), Cr the bank. A mistake is
cancelled with a reason and a mirror journal, which frees its deductions for
the challan that should have carried them.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class TdsChallanStatus(StrEnum):
    """Posted on save; cancelled by a mirror journal."""

    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class TdsChallan(BaseEntity):
    """One deposit of TDS under one section."""

    __tablename__ = "tds_challans"
    __table_args__ = (
        UniqueConstraint("firm_id", "challan_number", name="UQ_tds_challans_number"),
        CheckConstraint("tax_amount > 0", name="CK_tds_challans_tax_positive"),
        CheckConstraint(
            "interest_amount >= 0 AND fee_amount >= 0",
            name="CK_tds_challans_charges_not_negative",
        ),
        # One live challan per CIN: the same counterfoil keyed twice would
        # file its deductions twice. A cancelled one frees the CIN.
        Index(
            "UQ_tds_challans_cin_live",
            "firm_id",
            "bsr_code",
            "deposited_on",
            "challan_serial",
            unique=True,
            postgresql_where=text("status = 'POSTED' AND is_deleted = false"),
            sqlite_where=text("status = 'POSTED' AND is_deleted = 0"),
        ),
        Index("IX_tds_challans_firm_date", "firm_id", "deposited_on"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: The firm's own voucher number, from its series.
    challan_number: Mapped[str] = mapped_column(String(60), nullable=False)
    #: The date the bank received it: the CIN's date and the ledger's.
    deposited_on: Mapped[date] = mapped_column(Date, nullable=False)
    bsr_code: Mapped[str] = mapped_column(String(7), nullable=False)
    challan_serial: Mapped[str] = mapped_column(String(5), nullable=False)
    #: The section every deduction on it was made under.
    section: Mapped[str] = mapped_column(String(10), nullable=False)
    #: The tax deposited: the sum of the deductions it carries.
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: Interest for depositing late (section 201(1A)).
    interest_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: Fee for filing the return late (section 234E), paid on the same challan.
    fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: The bank account the money left.
    paid_from_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    remarks: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TdsChallanStatus.POSTED.value,
        server_default=TdsChallanStatus.POSTED.value,
    )
    journal_entry_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancelled_by: Mapped[UUID | None] = mapped_column(UUIDType())
    cancel_reason: Mapped[str | None] = mapped_column(Text())


class TdsChallanItem(BaseEntity):
    """One deduction a challan paid: a payment's, an expense's or a bill's."""

    __tablename__ = "tds_challan_items"
    __table_args__ = (
        # Exactly one document: a payment, an expense or a bill (PG-5).
        CheckConstraint(
            "(CASE WHEN settlement_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN expense_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN purchase_invoice_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="CK_tds_challan_items_one_document",
        ),
        CheckConstraint("tds_amount > 0", name="CK_tds_challan_items_positive"),
        # A deduction is paid once. The key, not a read, holds it: two
        # challans saved together would both pass a check that counted first.
        Index(
            "UQ_tds_challan_items_settlement_live",
            "settlement_id",
            unique=True,
            postgresql_where=text("is_live = true AND settlement_id IS NOT NULL"),
            sqlite_where=text("is_live = 1 AND settlement_id IS NOT NULL"),
        ),
        Index(
            "UQ_tds_challan_items_expense_live",
            "expense_id",
            unique=True,
            postgresql_where=text("is_live = true AND expense_id IS NOT NULL"),
            sqlite_where=text("is_live = 1 AND expense_id IS NOT NULL"),
        ),
        Index(
            "UQ_tds_challan_items_purchase_invoice_live",
            "purchase_invoice_id",
            unique=True,
            postgresql_where=text("is_live = true AND purchase_invoice_id IS NOT NULL"),
            sqlite_where=text("is_live = 1 AND purchase_invoice_id IS NOT NULL"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    challan_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("tds_challans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    settlement_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("settlements.id", ondelete="RESTRICT")
    )
    expense_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("expenses.id", ondelete="RESTRICT")
    )
    #: A bill that bore the deduction at approval (PG-5, 194C and 194J).
    purchase_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("purchase_invoices.id", ondelete="RESTRICT")
    )
    tds_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: False once the challan is cancelled, which frees the deduction.
    is_live: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
