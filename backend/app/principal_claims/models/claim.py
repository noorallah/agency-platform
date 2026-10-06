"""Claims raised on a principal and how they were settled (SEL-11)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class PrincipalClaim(BaseEntity):
    """What one principal owes the firm for one period (decision A128).

    Raised from the schemes the principal funds, the firm's expiry
    write-offs of its products and the broken goods customers returned;
    settled by the principal's credit note or by its payment. A rate
    difference claim is for one price cut rather than a period: both ends of
    its period are the day the new rates took effect.
    """

    __tablename__ = "principal_claims"
    __table_args__ = (
        Index("IX_principal_claims_firm_principal", "firm_id", "principal_id"),
        Index(
            "UQ_principal_claims_number_active",
            "firm_id",
            "claim_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    claim_number: Mapped[str] = mapped_column(String(60), nullable=False)
    claim_date: Mapped[date] = mapped_column(Date, nullable=False)
    principal_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("principals.id", ondelete="RESTRICT"), nullable=False
    )
    #: The supplier the principal is, when it is one: a credit note from it
    #: settles the claim against its bills.
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT")
    )
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    scheme_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    expiry_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    breakage_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    #: Free goods somebody typed on a bill line of the principal's products,
    #: at what the dispatch cost. An offer's free goods are in
    #: ``scheme_amount``, with the rest of what its schemes gave.
    free_goods_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    #: The principal's price cut on the stock in hand when it took effect:
    #: old rate less new rate, times what stood at the close of the day before.
    rate_difference_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, server_default="0"
    )
    #: ``RAISED`` or ``CANCELLED``; how far it is settled is derived.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RAISED")
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class PrincipalClaimLine(BaseEntity):
    """One thing claimed: a redemption, free goods, a write-off or a return line.

    Or, for a rate difference, the stock a price cut found on the shelf.

    A source is claimed once: a live line holds it, and cancelling the claim
    soft-deletes its lines so the source can be claimed again.
    """

    __tablename__ = "principal_claim_lines"
    __table_args__ = (
        Index("IX_principal_claim_lines_claim", "claim_id"),
        Index(
            "UQ_principal_claim_lines_source_active",
            "kind",
            "source_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    claim_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("principal_claims.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: ``SCHEME``, ``FREE_GOODS``, ``EXPIRY``, ``BREAKAGE`` or
    #: ``RATE_DIFFERENCE``.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The redemption, delivery note line, stock movement or sales return
    #: line claimed. No foreign key: four tables, named by ``kind`` -- a
    #: scheme's line is a redemption for its money and a delivery note line
    #: for its free goods. A rate difference has no row to name: its source
    #: is a key made of the principal, the product, the batch and the day the
    #: cut took effect (``rate_difference_source``), so the same stock is
    #: claimed once for one cut.
    source_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_number: Mapped[str] = mapped_column(String(80), nullable=False)
    source_date: Mapped[date] = mapped_column(Date, nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("products.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    #: Rate difference only. The batch the stock was in, where the product is
    #: kept by batch; a bare id, as ``source_id`` is. The rates are the
    #: purchase rate per stock unit before tax, before and after the cut, as
    #: the claim stated them: the principal's circular is the authority, so
    #: they are kept here rather than re-read from the price revisions.
    batch_id: Mapped[UUID | None] = mapped_column(UUIDType())
    old_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    new_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)


class PrincipalClaimReceipt(BaseEntity):
    """Money the principal paid against a claim."""

    __tablename__ = "principal_claim_receipts"
    __table_args__ = (Index("IX_principal_claim_receipts_claim", "claim_id"),)

    claim_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("principal_claims.id", ondelete="CASCADE"),
        nullable=False,
    )
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    money_account_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reference: Mapped[str | None] = mapped_column(String(100))
    #: ``POSTED`` or ``REVERSED``.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="POSTED")
    journal_entry_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
