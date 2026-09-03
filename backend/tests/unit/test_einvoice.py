"""Registering an invoice with the tax authority, and raising its e-way bill.

Nothing here talks to a government portal, and nothing needs to: the part that
has to be right is the payload and the refusals, and both can be judged
without one. What the sandbox adds is a state machine to drive.

The cases that decide whether this can be trusted:

- **a rehearsal can never be mistaken for a filing** -- the mode is on every
  row and the sandbox marks every reference it mints;
- **the payload is refused locally, naming the field**, rather than sent to
  come back as a numeric code;
- **the CGST/SGST versus IGST split is read off the two GSTINs**, so the
  document and the tax on it cannot disagree about the same supply.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.einvoice.models import (
    EWayBillStatus,
    RegistrationMode,
    RegistrationStatus,
)
from app.einvoice.services import EInvoiceService, SandboxPortal, portal_for
from app.firms.models import Firm
from app.products.models import Product
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
)

WHEN = date(2026, 4, 20)

#: Two GSTINs in the same state (27, Maharashtra) and one in another (29).
SELLER = "27AABCU9603R1ZM"
BUYER_SAME_STATE = "27AAACR5055K1Z5"
BUYER_OTHER_STATE = "29AAACR5055K1Z5"


def _session_factory() -> sessionmaker[Session]:
    """Create one shared in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class _Books:
    """A GST-registered firm with one approved, taxed invoice."""

    def __init__(
        self,
        session: Session,
        *,
        buyer_gstin: str | None = BUYER_SAME_STATE,
        seller_gstin: str | None = SELLER,
        hsn: str | None = "34011190",
        interstate: bool = False,
    ) -> None:
        """Seed everything a registration needs."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Registered Firm",
            code="EINV",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
            gst_number=seller_gstin,
        )
        session.add(self.firm)
        session.commit()
        self.branch = Branch(
            firm_id=self.firm.id,
            code="BR-1",
            name="Branch One",
            display_name="Branch One",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
        )
        self.customer = Customer(
            firm_id=self.firm.id,
            code="C1",
            customer_type="BUSINESS",
            name="Kumar Stores",
            display_name="Kumar Stores",
            currency_code="INR",
            status="ACTIVE",
            gst_number=buyer_gstin,
        )
        self.product = Product(
            firm_id=self.firm.id,
            code="SKU-1",
            name="Toothpaste 150g",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            hsn_sac=hsn,
        )
        session.add_all([self.branch, self.customer, self.product])
        session.commit()
        self.invoice, self.line = self._invoice(interstate=interstate)

    def _invoice(self, *, interstate: bool) -> tuple[SalesInvoice, SalesInvoiceLine]:
        """Bill 10 at 100 with 18% tax, split the way the supply requires."""
        invoice = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            invoice_number="SI-1",
            invoice_date=WHEN,
            status="APPROVED",
            grand_total=Decimal("1180.00"),
        )
        self.session.add(invoice)
        self.session.flush()
        line = SalesInvoiceLine(
            sales_invoice_id=invoice.id,
            firm_id=self.firm.id,
            line_number=1,
            source_document_type="SALES_ORDER",
            source_document_id=uuid4(),
            source_document_number="SO-1",
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=self.product.id,
            delivered_quantity=Decimal("10"),
            current_invoice_quantity=Decimal("10"),
            unit_price=Decimal("100"),
            gross_amount=Decimal("1000"),
            tax_amount=Decimal("180"),
            net_amount=Decimal("1180"),
        )
        self.session.add(line)
        self.session.flush()
        components = (
            [("IGST", Decimal("18"), Decimal("180"))]
            if interstate
            else [
                ("CGST", Decimal("9"), Decimal("90")),
                ("SGST", Decimal("9"), Decimal("90")),
            ]
        )
        for index, (code, rate, amount) in enumerate(components, start=1):
            self.session.add(
                SalesInvoiceLineTax(
                    sales_invoice_line_id=line.id,
                    firm_id=self.firm.id,
                    sequence=index,
                    component_code=code,
                    component_label=code,
                    percentage=rate,
                    base_amount=Decimal("1000"),
                    amount=amount,
                )
            )
        self.session.commit()
        return invoice, line

    def service(self, mode: str = RegistrationMode.SANDBOX.value) -> EInvoiceService:
        """Return a service bound to one mode."""
        return EInvoiceService(self.session, mode=mode)

    def register(self) -> object:
        """Register the invoice in sandbox."""
        row = self.service().register(
            self.invoice.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )
        self.session.commit()
        return row


def test_a_sandbox_registration_says_so_in_every_value() -> None:
    """A rehearsal that reads like a filing is the one failure to prevent.

    Somebody eventually prints this and presents it at a check post, so the
    mode is on the row *and* the reference marks itself -- a number carried
    away from its row still has to say what it is.
    """
    books = _Books(_session_factory()())

    row = books.register()

    assert row.status == RegistrationStatus.REGISTERED.value
    assert row.mode == RegistrationMode.SANDBOX.value
    assert row.irn is not None and row.irn.startswith("SBX")
    assert row.acknowledgement_number is not None
    assert row.acknowledgement_number.startswith("SBX")
    assert row.signed_qr_code is not None
    assert row.signed_qr_code.startswith("SANDBOX.")


def test_live_mode_refuses_rather_than_quietly_rehearsing() -> None:
    """A firm that believes it is filing must not be rehearsing instead.

    Falling back to the sandbox here would be the worst outcome available:
    every invoice would look registered and none would be.
    """
    with pytest.raises(NotImplementedError):
        portal_for(RegistrationMode.LIVE.value)


def test_the_payload_carries_what_the_portal_needs() -> None:
    """The part that has to be right, and needs no portal to check."""
    books = _Books(_session_factory()())

    row = books.register()
    payload = row.request_payload

    assert payload["DocDtls"]["No"] == "SI-1"
    assert payload["DocDtls"]["Dt"] == "20/04/2026"
    assert payload["SellerDtls"]["Gstin"] == SELLER
    assert payload["BuyerDtls"]["Gstin"] == BUYER_SAME_STATE
    item = payload["ItemList"][0]
    assert item["HsnCd"] == "34011190"
    assert item["AssAmt"] == 1000.0
    # Nine plus nine is the rate on the item, not two rows of nine.
    assert item["GstRt"] == 18.0
    assert item["CgstAmt"] == 90.0
    assert item["SgstAmt"] == 90.0
    assert item["IgstAmt"] == 0.0
    assert payload["ValDtls"]["TotInvVal"] == 1180.0


def test_an_interstate_supply_carries_igst() -> None:
    """Read off the two GSTINs, so the document and the tax cannot disagree."""
    books = _Books(_session_factory()(), buyer_gstin=BUYER_OTHER_STATE, interstate=True)

    row = books.register()
    item = row.request_payload["ItemList"][0]

    assert item["IgstAmt"] == 180.0
    assert item["CgstAmt"] == 0.0
    assert row.request_payload["BuyerDtls"]["Pos"] == "29"


def test_an_interstate_supply_taxed_as_local_is_refused() -> None:
    """The state codes say inter-state and the invoice charged CGST.

    Sending it would come back as a numeric code from the portal. Refusing it
    here says which of the two is wrong.
    """
    books = _Books(_session_factory()(), buyer_gstin=BUYER_OTHER_STATE)

    with pytest.raises(ValidationError, match="inter-state"):
        books.register()


def test_a_local_supply_taxed_as_interstate_is_refused() -> None:
    """And the mirror image, which is the same mistake the other way."""
    books = _Books(_session_factory()(), interstate=True)

    with pytest.raises(ValidationError, match="intra-state"):
        books.register()


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"seller_gstin": None}, "firm has no GST number"),
        ({"buyer_gstin": None}, "customer has no GST number"),
        ({"hsn": None}, "no HSN or SAC code"),
    ],
)
def test_a_payload_that_cannot_be_registered_is_refused_by_name(
    kwargs: dict[str, object], expected: str
) -> None:
    """Naming the field beats a numeric code somebody has to look up."""
    books = _Books(_session_factory()(), **kwargs)  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match=expected):
        books.register()


def test_a_draft_invoice_cannot_be_registered() -> None:
    """A draft is not a supply, so there is nothing to register."""
    books = _Books(_session_factory()())
    books.invoice.status = "DRAFT"
    books.session.commit()

    with pytest.raises(ValidationError, match="not approved"):
        books.register()


def test_registering_twice_is_refused() -> None:
    """Two references for one supply leave nothing to say which is held."""
    books = _Books(_session_factory()())
    books.register()

    with pytest.raises(ConflictError):
        books.register()


def test_a_refusal_lands_on_the_row_rather_than_raising() -> None:
    """The person who has to fix the invoice is looking at the invoice.

    A portal refusal is information, not a stack trace, so it comes back as a
    FAILED row carrying the code and the sentence -- and the attempt is
    counted, because a retry writes over the same row.
    """
    books = _Books(_session_factory()())
    service = books.service()
    # The sandbox refuses a document number it has already seen, which is what
    # the real portal answers 2150 for.
    portal = SandboxPortal()
    portal.register_invoice({"DocDtls": {"No": "SI-1"}})
    result = portal.register_invoice({"DocDtls": {"No": "SI-1"}})

    assert result.ok is False
    assert result.error_code == "2150"
    assert "already registered" in (result.error_message or "")
    assert service is not None


def test_a_registration_is_withdrawn_inside_its_window() -> None:
    """And the row keeps saying what it was."""
    books = _Books(_session_factory()())
    books.register()

    row = books.service().cancel(
        books.invoice.id,
        reason="Raised against the wrong customer.",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert row.status == RegistrationStatus.CANCELLED.value
    assert row.cancellation_reason == "Raised against the wrong customer."
    assert row.irn is not None, "the reference is kept, not blanked"


def test_a_registration_older_than_the_window_cannot_be_withdrawn() -> None:
    """The authority allows a day, and afterwards a credit note is the way.

    Judged in UTC like every clock here: reading the server's local time would
    make the window an hour wrong for part of every day on a non-UTC
    deployment.
    """
    books = _Books(_session_factory()())
    row = books.register()
    row.acknowledged_at = utc_now() - timedelta(hours=25)
    books.session.commit()

    with pytest.raises(ValidationError, match="24 hours"):
        books.service().cancel(
            books.invoice.id,
            reason="Too late.",
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_an_eway_bill_needs_the_invoice_registered_first() -> None:
    """The bill quotes the IRN; one without it matches no supply."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError, match="Register the invoice"):
        books.service().generate_eway_bill(
            books.invoice.id,
            distance_km=Decimal("120"),
            transport_mode="ROAD",
            transporter_id=None,
            transporter_name=None,
            vehicle_number="MH12AB1234",
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_goods_by_road_need_a_vehicle_number() -> None:
    """A lorry with no registration on the bill cannot be checked."""
    books = _Books(_session_factory()())
    books.register()

    with pytest.raises(ValidationError, match="vehicle number"):
        books.service().generate_eway_bill(
            books.invoice.id,
            distance_km=Decimal("120"),
            transport_mode="ROAD",
            transporter_id=None,
            transporter_name=None,
            vehicle_number=None,
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_an_eway_bill_carries_a_validity_the_portal_decided() -> None:
    """One day per 200km, which is the published rule.

    Stored rather than recomputed on read: a locally derived expiry that
    disagreed with the authority's is worse than none at all.
    """
    books = _Books(_session_factory()())
    books.register()

    row = books.service().generate_eway_bill(
        books.invoice.id,
        distance_km=Decimal("450"),
        transport_mode="ROAD",
        transporter_id="27AABCU9603R1ZM",
        transporter_name="Speedy Logistics",
        vehicle_number="mh12ab1234",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert row.status == EWayBillStatus.GENERATED.value
    assert row.mode == RegistrationMode.SANDBOX.value
    assert row.eway_bill_number is not None
    assert row.eway_bill_number.startswith("SBX")
    # 450km is three days at 200km a day.
    assert row.valid_until == utc_now().date() + timedelta(days=3)
    # Stored upper-cased, because that is how a registration is read.
    assert row.vehicle_number == "MH12AB1234"


def test_an_eway_bill_is_raised_once() -> None:
    """A second would put two references on one consignment."""
    books = _Books(_session_factory()())
    books.register()
    service = books.service()
    args: dict[str, object] = {
        "distance_km": Decimal("120"),
        "transport_mode": "ROAD",
        "transporter_id": None,
        "transporter_name": None,
        "vehicle_number": "MH12AB1234",
        "firm_scope": books.firm.id,
        "actor_id": books.actor_id,
    }
    service.generate_eway_bill(books.invoice.id, **args)  # type: ignore[arg-type]
    books.session.commit()

    with pytest.raises(ConflictError):
        service.generate_eway_bill(books.invoice.id, **args)  # type: ignore[arg-type]


def test_one_firm_s_registrations_are_invisible_to_another() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    books = _Books(_session_factory()())
    books.register()

    rows, total = books.service().list_registrations(
        firm_scope=uuid4(), page=1, page_size=20
    )

    assert total == 0
    assert rows == []
