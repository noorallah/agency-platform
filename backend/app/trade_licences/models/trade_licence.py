"""The licences a firm, its customers and its vendors trade under (backlog 54).

Some goods may only be bought and sold under a licence: medicines under a drug
licence, packaged food under FSSAI, pesticides, fertilisers and seeds under
their own. The seller needs one to sell them and, for most, the buyer needs one
to buy them. Before this there was one free-text number on a branch and a
vendor and nothing on a customer, with no type, no validity and nothing that
read them.

**Types are a master, not code** (the convention of Marg, BUSY pharma and the
Tally add-ons): a firm is seeded the usual ones and adds its own, because the
list differs by trade and state.

**One register for every holder.** A licence belongs to the firm (optionally
to one branch, since a drug licence is issued per premises), to a customer or
to a vendor, and a holder may hold several. An expired licence is kept, never
deleted: it is the record of what was valid when a past sale was made.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class TradeLicenceType(BaseEntity):
    """One kind of licence, such as a wholesale drug licence or FSSAI."""

    __tablename__ = "trade_licence_types"
    __table_args__ = (
        Index(
            "UQ_trade_licence_types_firm_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: The statutory forms it covers, for reading -- "20B / 21B".
    form_numbers: Mapped[str | None] = mapped_column(String(120))
    #: Whether a licence of this type runs out. Where it does, a valid-to date
    #: is required when one is recorded, because an expiry nobody wrote down
    #: is an expiry nobody is warned about.
    expires: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    description: Mapped[str | None] = mapped_column(Text)


class TradeLicence(BaseEntity):
    """One licence held by the firm, a customer or a vendor."""

    __tablename__ = "trade_licences"
    __table_args__ = (
        CheckConstraint(
            "holder_type IN ('FIRM', 'CUSTOMER', 'VENDOR')",
            name="CK_trade_licences_holder_type",
        ),
        # Exactly the holder the type names, and nobody else's column set: a
        # row naming a customer and a vendor would answer "whose is it" twice.
        CheckConstraint(
            "(holder_type = 'FIRM' AND customer_id IS NULL AND vendor_id IS NULL)"
            " OR (holder_type = 'CUSTOMER' AND customer_id IS NOT NULL"
            " AND vendor_id IS NULL AND branch_id IS NULL)"
            " OR (holder_type = 'VENDOR' AND vendor_id IS NOT NULL"
            " AND customer_id IS NULL AND branch_id IS NULL)",
            name="CK_trade_licences_holder",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="CK_trade_licences_validity",
        ),
        Index("IX_trade_licences_firm_valid_to", "firm_id", "valid_to"),
        Index("IX_trade_licences_firm_holder", "firm_id", "holder_type"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    licence_type_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("trade_licence_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: FIRM, CUSTOMER or VENDOR.
    holder_type: Mapped[str] = mapped_column(String(20), nullable=False)
    #: For the firm's own licence, the premises it was issued for; null means
    #: the firm as a whole.
    branch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT"), index=True
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("vendors.id", ondelete="RESTRICT"), index=True
    )
    licence_number: Mapped[str] = mapped_column(String(80), nullable=False)
    issued_by: Mapped[str | None] = mapped_column(String(200))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    #: The address the licence covers, as printed on it.
    premises: Mapped[str | None] = mapped_column(String(250))
    remarks: Mapped[str | None] = mapped_column(Text)
