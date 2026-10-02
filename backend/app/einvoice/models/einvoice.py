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
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
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


class EInvoiceProvider(StrEnum):
    """How a firm's documents reach the Invoice Registration Portal (A42).

    The provider decides the transport; the mode on each row still says
    whether a filing happened. SANDBOX rehearses (mode SANDBOX). OFFLINE is a
    real filing made by hand: the firm uploads the exported JSON on the
    portal and imports the result, so its rows are mode LIVE. NIC_DIRECT and
    GSP are the live API routes, added provider by provider.
    """

    SANDBOX = "SANDBOX"
    OFFLINE = "OFFLINE"
    NIC_DIRECT = "NIC_DIRECT"
    GSP = "GSP"


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
    """One document, as the Invoice Registration Portal knows it.

    A sales invoice, or since backlog 77 row 4 a credit note or a debit note
    to a customer, which the portal registers too (document types CRN and
    DBN), and since D-TAX-2 a sales return's credit note (CRN). Exactly one is
    named.
    """

    __tablename__ = "einvoice_registrations"
    __table_args__ = (
        # One document, one registration. A second would leave two IRNs for
        # one supply and nothing to say which the customer holds.
        UniqueConstraint(
            "firm_id",
            "sales_invoice_id",
            name="UQ_einvoice_registrations_invoice",
        ),
        UniqueConstraint(
            "firm_id",
            "credit_note_id",
            name="UQ_einvoice_registrations_credit_note",
        ),
        UniqueConstraint(
            "firm_id",
            "customer_debit_note_id",
            name="UQ_einvoice_registrations_debit_note",
        ),
        UniqueConstraint(
            "firm_id",
            "sales_return_id",
            name="UQ_einvoice_registrations_sales_return",
        ),
        CheckConstraint(
            "(CASE WHEN sales_invoice_id IS NULL THEN 0 ELSE 1 END)"
            " + (CASE WHEN credit_note_id IS NULL THEN 0 ELSE 1 END)"
            " + (CASE WHEN customer_debit_note_id IS NULL THEN 0 ELSE 1 END)"
            " + (CASE WHEN sales_return_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="CK_einvoice_registrations_one_document",
        ),
        Index("IX_einvoice_registrations_firm_status", "firm_id", "status"),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    sales_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_invoices.id", ondelete="RESTRICT")
    )
    #: A credit note registered as CRN (77 row 4).
    credit_note_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("credit_notes.id", ondelete="RESTRICT")
    )
    #: A debit note to a customer registered as DBN (77 row 4).
    customer_debit_note_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("customer_debit_notes.id", ondelete="RESTRICT")
    )
    #: A sales return's credit note, registered as CRN (D-TAX-2).
    sales_return_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_returns.id", ondelete="RESTRICT")
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The route it took (``EInvoiceProvider``); null on rows from before A42,
    #: which were all the sandbox.
    provider: Mapped[str | None] = mapped_column(String(20))
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
    """One consignment's e-way bill, raised against an invoice or a challan.

    An invoice, as before; or, where no invoice bills the goods yet, the
    delivery note that moves them (backlog 77 row 9). Exactly one is named.
    """

    __tablename__ = "eway_bills"
    __table_args__ = (
        UniqueConstraint("firm_id", "sales_invoice_id", name="UQ_eway_bills_invoice"),
        UniqueConstraint(
            "firm_id", "delivery_note_id", name="UQ_eway_bills_delivery_note"
        ),
        CheckConstraint(
            "(sales_invoice_id IS NULL) <> (delivery_note_id IS NULL)",
            name="CK_eway_bills_one_document",
        ),
        Index("IX_eway_bills_firm_status", "firm_id", "status"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    sales_invoice_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_invoices.id", ondelete="RESTRICT")
    )
    #: The challan it travels on, where no invoice bills the goods yet.
    delivery_note_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("delivery_notes.id", ondelete="RESTRICT")
    )
    #: Raised by hand on the e-way bill portal and its number recorded here
    #: (a firm filing offline, A42), rather than through this platform.
    entered_by_hand: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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


class EInvoiceSettings(BaseEntity):
    """How one firm registers its e-invoices (decision A42).

    One row per firm; a firm with none rehearses in the sandbox, so nothing is
    ever filed by default. The live API providers keep their credentials with
    the provider they belong to, encrypted, when they are built.
    """

    __tablename__ = "einvoice_settings"
    __table_args__ = (
        Index(
            "UQ_einvoice_settings_firm_active",
            "firm_id",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EInvoiceProvider.SANDBOX.value,
        server_default=EInvoiceProvider.SANDBOX.value,
    )
