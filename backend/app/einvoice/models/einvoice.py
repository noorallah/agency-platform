"""What the government portal gave back for an invoice, and for its movement.

Two registrations, one module, because they share one portal, one set of
credentials and one failure story: an e-invoice is registered with the Invoice
Registration Portal and an e-way bill is raised from that same registration
for the goods it covers.

**Every registration records the mode it was made in.** A sandbox registration
is a rehearsal -- no return was filed, no IRN exists at the authority, and the
number on it means nothing outside this database. A row that could not say
which it was would be a document somebody eventually presents at a check post.
So `mode` is NOT NULL, there is no default that could quietly become LIVE, and
the reference the sandbox mints is prefixed so it cannot be mistaken even out
of context.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Date,
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
from app.core.database.types import UTCDateTime, UUIDType


class RegistrationMode(StrEnum):
    """Whether a registration was filed or rehearsed.

    There is no third value and no default. A firm switches to LIVE
    deliberately, with credentials, and every row written before that says so
    for ever after.
    """

    SANDBOX = "SANDBOX"
    LIVE = "LIVE"


class RegistrationStatus(StrEnum):
    """Where a registration got to.

    FAILED is a real state rather than an absence: the portal refused, it said
    why, and that answer is worth keeping. Retrying writes over the error on
    the same row, because one invoice has one registration.
    """

    PENDING = "PENDING"
    REGISTERED = "REGISTERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EInvoiceRegistration(BaseEntity):
    """One sales invoice, as the Invoice Registration Portal knows it."""

    __tablename__ = "einvoice_registrations"
    __table_args__ = (
        # One invoice, one registration. A second would leave two IRNs for one
        # supply and nothing to say which the customer holds.
        UniqueConstraint(
            "firm_id",
            "sales_invoice_id",
            name="UQ_einvoice_registrations_invoice",
        ),
        Index("IX_einvoice_registrations_firm_status", "firm_id", "status"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RegistrationStatus.PENDING.value,
        server_default=RegistrationStatus.PENDING.value,
    )
    #: The 64-character hash the portal returns. Sandbox mints one prefixed
    #: `SBX` so it is recognisable on its own, away from this row.
    irn: Mapped[str | None] = mapped_column(String(80))
    acknowledgement_number: Mapped[str | None] = mapped_column(String(40))
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    #: The signed QR the customer's copy has to carry. Held as text because it
    #: is a JWT, not a picture -- rendering is the printer's job.
    signed_qr_code: Mapped[str | None] = mapped_column(Text)
    signed_invoice: Mapped[str | None] = mapped_column(Text)
    #: What the portal said when it refused. Kept on the row rather than only
    #: in a log, because the person who has to fix the invoice is looking at
    #: the invoice.
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancellation_reason: Mapped[str | None] = mapped_column(String(200))
    #: Exactly what was sent, so a refusal can be argued with. The portal
    #: rejects on the payload it received, not on the document as it looks
    #: today.
    request_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)


class EWayBillStatus(StrEnum):
    """Where an e-way bill got to."""

    PENDING = "PENDING"
    GENERATED = "GENERATED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TransportMode(StrEnum):
    """How the goods are moving.

    The portal takes a code; these are the names a person uses. Road is the
    only one that requires a vehicle number, which is why the service asks for
    one only then.
    """

    ROAD = "ROAD"
    RAIL = "RAIL"
    AIR = "AIR"
    SHIP = "SHIP"


class EWayBill(BaseEntity):
    """One consignment's e-way bill, raised against an invoice."""

    __tablename__ = "eway_bills"
    __table_args__ = (
        UniqueConstraint("firm_id", "sales_invoice_id", name="UQ_eway_bills_invoice"),
        Index("IX_eway_bills_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EWayBillStatus.PENDING.value,
        server_default=EWayBillStatus.PENDING.value,
    )
    eway_bill_number: Mapped[str | None] = mapped_column(String(40))
    #: When the bill stops being valid. The portal decides it from the
    #: distance, so it is stored rather than computed -- a locally computed
    #: expiry that disagreed with the authority's is worse than none.
    valid_until: Mapped[date | None] = mapped_column(Date)
    distance_km: Mapped[Decimal] = mapped_column(
        Numeric(9, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    transport_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TransportMode.ROAD.value,
        server_default=TransportMode.ROAD.value,
    )
    transporter_id: Mapped[str | None] = mapped_column(String(40))
    transporter_name: Mapped[str | None] = mapped_column(String(200))
    vehicle_number: Mapped[str | None] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancellation_reason: Mapped[str | None] = mapped_column(String(200))
    request_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
