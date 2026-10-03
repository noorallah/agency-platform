"""The register of gifts and incentives received from suppliers (BUY-2)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class SupplierGift(BaseEntity):
    """One gift from a supplier: not stock, not for sale (decision A112).

    Saving it posts one journal by who keeps it -- the business as an asset,
    the business using it up, or the owner -- always against supplier
    incentive income. No GST input credit is taken on a gift received free.
    """

    __tablename__ = "supplier_gifts"
    __table_args__ = (
        Index(
            "IX_supplier_gifts_firm_vendor_date", "firm_id", "vendor_id", "gift_date"
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    gift_number: Mapped[str] = mapped_column(String(60), nullable=False)
    gift_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    item: Mapped[str] = mapped_column(String(200), nullable=False)
    #: The supplier's declared value, or fair market value.
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    #: ``ASSET`` (kept by the business), ``EXPENSE`` (used up by it) or
    #: ``OWNER`` (taken by the owner, as drawings).
    kept_by: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The asset or expense account debited; null for the owner's drawings.
    debit_account_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("ledger_accounts.id", ondelete="RESTRICT")
    )
    #: The delivery it arrived with, where it did.
    goods_receipt_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("goods_receipts.id", ondelete="SET NULL")
    )
    scheme_name: Mapped[str | None] = mapped_column(String(120))
    #: Tax the supplier deducted under 194R, to match against Form 26AS.
    tds_194r_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    #: ``POSTED`` or ``CANCELLED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="POSTED")
    journal_entry_id: Mapped[UUID | None] = mapped_column(UUIDType())
    reversal_journal_entry_id: Mapped[UUID | None] = mapped_column(UUIDType())
    remarks: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
