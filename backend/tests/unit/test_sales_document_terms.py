"""What a sale's documents say about delivery and payment (backlog 67 rows 3-6).

Row 3: the ship-to address is chosen on the order, inherited by the delivery
note and the invoice, validated as the customer's own, printed, and -- for an
unregistered buyer -- decides the place of supply. Row 4: payment terms are
agreed on the order and the bill inherits them. Row 5: the delivery note
records how the goods travel, for the challan and the e-way bill. Row 6: a
note is delivered only with a proof.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.core.utils.dates import as_utc
from app.customers.models import Customer, CustomerAddress
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import (
    DeliveryNoteCreate,
    DeliveryNoteLineWrite,
    DeliveryNoteListFilters,
    DeliveryProofAttachmentWrite,
    DeliveryProofWrite,
)
from app.delivery_note.services.challan_print_service import (
    DeliveryChallanPrintService,
)
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.sales_invoice.models import SalesInvoice, SalesInvoiceSource
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.sales_order_service import SalesOrderService
from app.tax.services.place_of_supply import SupplyPlaceResolver
from tests.unit.test_einvoice import _Books
from tests.unit.test_einvoice import _session_factory as _einvoice_factory
from tests.unit.test_sales_chain_synthesis import (
    _bill_of,
    _Firm,
    _persons_note,
    _session_factory,
)


def _address(
    session: Session,
    customer: Customer,
    *,
    line1: str,
    state: str = "Karnataka",
    kind: str = "SHIPPING",
    default_shipping: bool = False,
) -> CustomerAddress:
    """Give a customer one more address."""
    row = CustomerAddress(
        customer_id=customer.id,
        address_type=kind,
        address_line1=line1,
        city="City",
        state=state,
        country="IN",
        postal_code="560001",
        is_default_shipping=default_shipping,
    )
    session.add(row)
    session.commit()
    return row


def _order(setup: _Firm, **fields: object) -> SalesOrder:
    """Raise one draft order for four units."""
    return SalesOrderService(setup.session).create_order(
        SalesOrderCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
            **fields,  # type: ignore[arg-type]
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )


def _order_payload(
    setup: _Firm, order: SalesOrder, **fields: object
) -> SalesOrderCreate:
    """Describe an order's update as the editor sends it."""
    return SalesOrderCreate(
        customer_id=order.customer_id,
        branch_id=order.branch_id,
        warehouse_id=order.warehouse_id,
        order_date=order.order_date,
        lines=[
            SalesOrderLineWrite(
                line_number=1,
                product_id=setup.product.id,
                quantity=Decimal("4"),
                unit_price=Decimal("100"),
            )
        ],
        **fields,  # type: ignore[arg-type]
    )


# ---- row 3: ship-to per order ------------------------------------------


def test_an_order_ships_to_the_default_unless_another_address_is_named() -> None:
    """The default shipping address is preselected; another may be chosen."""
    session = _session_factory()()
    setup = _Firm(session)
    default = _address(session, setup.customer, line1="Main", default_shipping=True)
    other = _address(session, setup.customer, line1="Godown")

    assert _order(setup).shipping_address_id == default.id
    chosen = _order(setup, shipping_address_id=other.id)
    assert chosen.shipping_address_id == other.id


def test_an_address_not_the_customers_own_and_live_is_refused() -> None:
    """Another customer's address, or a deleted one, is never a ship-to."""
    session = _session_factory()()
    setup = _Firm(session)
    stranger = Customer(
        firm_id=setup.firm.id,
        code="CUS-002",
        customer_type="RETAIL",
        name="Someone Else",
        display_name="Someone Else",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(stranger)
    session.commit()
    theirs = _address(session, stranger, line1="Theirs")
    gone = _address(session, setup.customer, line1="Old")
    gone.is_deleted = True
    session.commit()

    for address in (theirs, gone):
        with pytest.raises(ValidationError, match="ship-to"):
            _order(setup, shipping_address_id=address.id)


def test_an_update_that_leaves_the_ship_to_out_keeps_it() -> None:
    """Absent means leave alone; naming one moves it."""
    session = _session_factory()()
    setup = _Firm(session)
    _address(session, setup.customer, line1="Main", default_shipping=True)
    other = _address(session, setup.customer, line1="Godown")
    third = _address(session, setup.customer, line1="Shop")
    order = _order(setup, shipping_address_id=other.id)
    service = SalesOrderService(session)

    kept = service.update_order(
        order.id,
        _order_payload(setup, order),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )
    assert kept.shipping_address_id == other.id
    moved = service.update_order(
        order.id,
        _order_payload(setup, order, shipping_address_id=third.id),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )
    assert moved.shipping_address_id == third.id


def test_the_note_and_the_bill_inherit_the_orders_ship_to() -> None:
    """A note continues its order, and a bill the notes it bills."""
    session = _session_factory()()
    setup = _Firm(session)
    default = _address(session, setup.customer, line1="Main", default_shipping=True)
    other = _address(session, setup.customer, line1="Godown")
    note = _persons_note(setup)
    order = session.get(SalesOrder, note.sales_order_id)
    assert order is not None
    assert order.shipping_address_id == default.id
    assert note.shipping_address_id == order.shipping_address_id
    service = DeliveryNoteService(session)
    service.dispatch_note(note.id, firm_scope=setup.firm.id, actor_id=uuid4())

    invoice = SalesInvoiceService(session).create_invoice(
        _bill_of(setup, note), firm_id=setup.firm.id, actor_id=uuid4()
    )
    assert invoice.shipping_address_id == note.shipping_address_id

    named = SalesInvoiceService(session).update_invoice(
        invoice.id,
        _bill_of(setup, note).model_copy(update={"shipping_address_id": other.id}),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    assert named.shipping_address_id == other.id


def test_a_counter_bill_passes_its_ship_to_down_the_chain_it_raises() -> None:
    """The order and note a bare bill raises ship where the bill says."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    _address(session, setup.customer, line1="Main", default_shipping=True)
    other = _address(session, setup.customer, line1="Godown")

    invoice = SalesInvoiceService(session).create_invoice(
        setup.bare_bill().model_copy(update={"shipping_address_id": other.id}),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    note = session.query(DeliveryNote).one()
    order = session.query(SalesOrder).one()
    assert order.shipping_address_id == other.id
    assert note.shipping_address_id == other.id
    assert invoice.shipping_address_id == other.id


def test_the_challan_prints_the_address_the_note_names() -> None:
    """The ship-to block is the note's own address, not the first on file."""
    session = _session_factory()()
    setup = _Firm(session)
    _address(session, setup.customer, line1="Main Road", default_shipping=True)
    other = _address(session, setup.customer, line1="Godown Lane")
    note = _persons_note(setup)
    note.shipping_address_id = other.id
    session.commit()

    document = DeliveryChallanPrintService(session)._document(
        note, firm_scope=setup.firm.id
    )
    assert document.ship_to is not None
    assert "Godown Lane" in document.ship_to.address_lines


# ---- row 3: place of supply --------------------------------------------


def _buyers(setup: _Firm) -> tuple[Customer, Customer, UUID]:
    """Return an unregistered and a registered buyer and a Tamil Nadu ship-to.

    Both bill from Karnataka; each has a ship-to in Tamil Nadu.
    """
    session = setup.session
    setup.firm.gst_number = "29ABCDE1234F1Z5"
    session.commit()
    walk_in = setup.customer
    _address(session, walk_in, line1="Bill", kind="BILLING", state="Karnataka")
    there = _address(session, walk_in, line1="Ship", state="Tamil Nadu")
    registered = Customer(
        firm_id=setup.firm.id,
        code="CUS-REG",
        customer_type="BUSINESS",
        name="Registered",
        display_name="Registered",
        currency_code="INR",
        status="ACTIVE",
        gst_number="29AAAAA0000A1Z5",
        gst_registration_type="REGULAR",
    )
    session.add(registered)
    session.commit()
    return walk_in, registered, there.id


def test_an_unregistered_buyer_is_supplied_where_the_goods_are_delivered() -> None:
    """IGST Act s.10(1)(a): no GSTIN, so the ship-to's state decides."""
    session = _session_factory()()
    setup = _Firm(session)
    walk_in, _, there = _buyers(setup)
    resolver = SupplyPlaceResolver(session)

    assert resolver.buyer_state(walk_in.id) == "29"
    assert resolver.buyer_state(walk_in.id, shipping_address_id=there) == "33"
    assert resolver.is_interstate(
        firm_id=setup.firm.id,
        branch_id=None,
        customer_id=walk_in.id,
        shipping_address_id=there,
    )
    assert resolver.place_of_supply(walk_in.id, shipping_address_id=there) == (
        "Tamil Nadu (33)"
    )


def test_a_registered_buyer_keeps_its_gstins_state_whatever_the_ship_to() -> None:
    """IGST Act s.10(1)(b): bill-to-ship-to is supplied to the bill-to person."""
    session = _session_factory()()
    setup = _Firm(session)
    _, registered, _ = _buyers(setup)
    elsewhere = _address(session, registered, line1="Depot", state="Tamil Nadu")
    resolver = SupplyPlaceResolver(session)

    assert resolver.buyer_state(registered.id, shipping_address_id=elsewhere.id) == (
        "29"
    )
    assert not resolver.is_interstate(
        firm_id=setup.firm.id,
        branch_id=None,
        customer_id=registered.id,
        shipping_address_id=elsewhere.id,
    )


def test_the_bill_stamps_the_place_of_supply_its_ship_to_decides() -> None:
    """The printed place of supply follows the same answer as the tax."""
    session = _session_factory()()
    setup = _Firm(session)
    _, _, there = _buyers(setup)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)

    invoice = SalesInvoiceService(session).create_invoice(
        setup.bare_bill().model_copy(update={"shipping_address_id": there}),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    stamped = session.get(SalesInvoice, invoice.id)
    assert stamped is not None
    assert stamped.place_of_supply == "Tamil Nadu (33)"


# ---- row 4: payment terms on the order ---------------------------------


def test_an_order_takes_the_customers_credit_days_unless_it_names_its_own() -> None:
    """None takes the customer's days; a typed figure, zero included, stands."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.customer.payment_terms_days = 30
    session.commit()

    assert _order(setup).payment_terms_days == 30
    agreed = _order(setup, payment_terms="7 days net", payment_terms_days=7)
    assert (agreed.payment_terms, agreed.payment_terms_days) == ("7 days net", 7)
    assert _order(setup, payment_terms_days=0).payment_terms_days == 0


def test_an_update_that_leaves_the_terms_out_keeps_them() -> None:
    """Absent means leave alone, as for every field an older editor omits."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.customer.payment_terms_days = 30
    session.commit()
    order = _order(setup, payment_terms="7 days net", payment_terms_days=7)

    kept = SalesOrderService(session).update_order(
        order.id,
        _order_payload(setup, order),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )
    assert (kept.payment_terms, kept.payment_terms_days) == ("7 days net", 7)


def test_the_bill_falls_due_on_the_orders_terms_not_the_customers() -> None:
    """The deal was struck on the order; re-reading the customer rewrites it."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.customer.payment_terms_days = 30
    session.commit()
    note = _persons_note(setup)
    order = session.get(SalesOrder, note.sales_order_id)
    assert order is not None
    order.payment_terms = "7 days net"
    order.payment_terms_days = 7
    session.commit()
    DeliveryNoteService(session).dispatch_note(
        note.id, firm_scope=setup.firm.id, actor_id=uuid4()
    )

    invoice = SalesInvoiceService(session).create_invoice(
        _bill_of(setup, note), firm_id=setup.firm.id, actor_id=uuid4()
    )
    assert invoice.due_date == date(2026, 8, 11)
    assert invoice.payment_terms == "7 days net"

    typed = SalesInvoiceService(session).update_invoice(
        invoice.id,
        _bill_of(setup, note).model_copy(update={"due_date": date(2026, 9, 1)}),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    assert typed.due_date == date(2026, 9, 1), "a typed date always wins"


def test_a_counter_bill_still_falls_due_on_the_customers_terms() -> None:
    """The order the chain raises takes the customer's days, as the bill did."""
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    setup.customer.payment_terms_days = 30
    session.commit()

    invoice = SalesInvoiceService(session).create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
    )
    assert invoice.due_date == date(2026, 9, 3)


# ---- row 5: transport details on the delivery note ---------------------

_TRANSPORT = {
    "transporter_name": "Speedy Logistics",
    "transporter_gstin": "27aabcu9603r1zm",
    "transport_mode": "road",
    "lr_number": "LR-778",
    "lr_date": date(2026, 8, 3),
    "distance_km": 450,
}


def _note_payload(note: DeliveryNote, **fields: object) -> DeliveryNoteCreate:
    """Describe a note's update as the editor sends it."""
    session = Session.object_session(note)
    assert session is not None
    line = session.query(DeliveryNoteLine).filter_by(delivery_note_id=note.id).one()
    return DeliveryNoteCreate(
        sales_order_id=note.sales_order_id,
        delivery_date=note.delivery_date,
        lines=[
            DeliveryNoteLineWrite(
                sales_order_line_id=line.sales_order_line_id,
                line_number=1,
                current_delivery_quantity=line.current_delivery_quantity,
            )
        ],
        **fields,  # type: ignore[arg-type]
    )


def test_a_note_records_how_the_goods_travel_and_an_edit_keeps_it() -> None:
    """Stored as typed, normalised; absent on an update means leave alone."""
    session = _session_factory()()
    setup = _Firm(session)
    note = _persons_note(setup)
    service = DeliveryNoteService(session)
    note.status = "DRAFT"
    session.commit()

    saved = service.update_note(
        note.id,
        _note_payload(note, **_TRANSPORT),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )
    assert saved.transporter_gstin == "27AABCU9603R1ZM"
    assert saved.transport_mode == "ROAD"
    assert (saved.lr_number, saved.lr_date, saved.distance_km) == (
        "LR-778",
        date(2026, 8, 3),
        450,
    )
    kept = service.update_note(
        note.id, _note_payload(note), firm_scope=setup.firm.id, actor_id=uuid4()
    )
    assert kept.transporter_name == "Speedy Logistics"
    assert kept.distance_km == 450


@pytest.mark.parametrize(
    "fields",
    [
        {"transporter_gstin": "27AABCU9603R1Z"},
        {"transporter_gstin": "ABCDEFGHIJKLMNO"},
        {"transport_mode": "CAMEL"},
        {"distance_km": 5000},
    ],
)
def test_a_malformed_transport_detail_is_refused(fields: dict[str, object]) -> None:
    """A GSTIN of the wrong shape, an unknown mode, an impossible distance."""
    with pytest.raises(PydanticValidationError):
        DeliveryNoteCreate(
            sales_order_id=uuid4(),
            delivery_date=date(2026, 8, 3),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=uuid4(),
                    line_number=1,
                    current_delivery_quantity=Decimal("1"),
                )
            ],
            **fields,  # type: ignore[arg-type]
        )


def test_the_challan_prints_the_transport_details() -> None:
    """What a checkpost asks for travels on the paper with the goods."""
    session = _session_factory()()
    setup = _Firm(session)
    note = _persons_note(setup)
    for name, value in _TRANSPORT.items():
        setattr(note, name, value.upper() if isinstance(value, str) else value)
    session.commit()

    references = dict(
        DeliveryChallanPrintService(session)
        ._document(note, firm_scope=setup.firm.id)
        .references
    )
    assert references["Transporter"] == "SPEEDY LOGISTICS"
    assert references["Transporter GSTIN"] == "27AABCU9603R1ZM"
    assert references["Mode"] == "Road"
    assert references["LR / docket"] == "LR-778 dt 03 Aug 2026"
    assert references["Distance"] == "450 km"


def test_an_eway_bill_reads_what_the_note_recorded_when_left_blank() -> None:
    """Distance, mode, transporter, vehicle and LR come from the note."""
    books = _Books(_einvoice_factory()())
    session = books.session
    note = DeliveryNote(
        firm_id=books.firm.id,
        sales_order_id=uuid4(),
        customer_id=books.customer.id,
        branch_id=books.branch.id,
        warehouse_id=uuid4(),
        delivery_note_number="DN-1",
        delivery_date=date(2026, 8, 3),
        sales_order_reference="SO-1",
        vehicle="MH12AB1234",
        status="DISPATCHED",
        **{
            **_TRANSPORT,
            "transporter_gstin": "27AABCU9603R1ZM",
            "transport_mode": "ROAD",
        },
    )
    session.add(note)
    session.flush()
    session.add(
        SalesInvoiceSource(
            sales_invoice_id=books.invoice.id,
            firm_id=books.firm.id,
            source_document_type="DELIVERY_NOTE",
            source_document_id=note.id,
            source_document_number="DN-1",
            source_document_date=date(2026, 8, 3),
            customer_id=books.customer.id,
            branch_id=books.branch.id,
        )
    )
    session.commit()
    books.register()

    row = books.service().generate_eway_bill(
        books.invoice.id,
        distance_km=None,
        transport_mode=None,
        transporter_id=None,
        transporter_name=None,
        vehicle_number=None,
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    assert row.distance_km == Decimal("450")
    assert (row.transport_mode, row.transporter_id, row.transporter_name) == (
        "ROAD",
        "27AABCU9603R1ZM",
        "Speedy Logistics",
    )
    assert row.vehicle_number == "MH12AB1234"
    assert row.request_payload is not None
    assert row.request_payload["TransDocNo"] == "LR-778"
    assert row.request_payload["TransDocDt"] == "03/08/2026"


# ---- row 6: proof of delivery ------------------------------------------


def _proof(**fields: object) -> DeliveryProofWrite:
    """Describe a proof: received the day after dispatch, with a photo."""
    values: dict[str, object] = {
        "delivered_at": datetime(2026, 8, 4, 15, 30, tzinfo=UTC),
        "received_by": "  R. Kumar ",
        "remarks": "Two cartons, seal intact",
        "attachment": DeliveryProofAttachmentWrite(
            file_name="pod.jpg", mime_type="image/jpeg", file_path="pod/dn-1.jpg"
        ),
    }
    values.update(fields)
    return DeliveryProofWrite(**values)  # type: ignore[arg-type]


def _dispatched(setup: _Firm) -> DeliveryNote:
    """Raise, approve and dispatch one note."""
    note = _persons_note(setup)
    DeliveryNoteService(setup.session).dispatch_note(
        note.id, firm_scope=setup.firm.id, actor_id=uuid4()
    )
    return note


def test_a_proof_marks_the_note_delivered_and_completes_it() -> None:
    """Delivered only with a proof; the photo is kept with the attachments."""
    session = _session_factory()()
    setup = _Firm(session)
    note = _dispatched(setup)
    service = DeliveryNoteService(session)
    assert service.note_response(note).is_delivered is False

    row = service.record_delivery_proof(
        note.id, _proof(), firm_scope=setup.firm.id, actor_id=uuid4()
    )

    response = service.note_response(row)
    assert response.is_delivered is True
    assert response.status == "COMPLETED"
    assert response.delivery_received_by == "R. Kumar"
    assert response.delivered_at is not None
    assert as_utc(response.delivered_at) == datetime(2026, 8, 4, 15, 30, tzinfo=UTC)
    assert [item.attachment_kind for item in response.attachments] == [
        "PROOF_OF_DELIVERY"
    ]
    audit = session.query(AuditLog).filter_by(action="delivery_note.delivered")
    assert audit.count() == 1


def test_no_proof_for_goods_that_have_not_left() -> None:
    """An approved note is still in the warehouse; nothing was delivered."""
    session = _session_factory()()
    setup = _Firm(session)
    note = _persons_note(setup)

    with pytest.raises(ValidationError, match="dispatch it first"):
        DeliveryNoteService(session).record_delivery_proof(
            note.id, _proof(), firm_scope=setup.firm.id, actor_id=uuid4()
        )


@pytest.mark.parametrize(
    ("when", "message"),
    [
        (datetime(2026, 8, 1, 10, 0, tzinfo=UTC), "before the note"),
        (datetime(2999, 1, 1, tzinfo=UTC), "future"),
    ],
)
def test_a_proof_dated_before_the_note_or_in_the_future_is_refused(
    when: datetime, message: str
) -> None:
    """Received before it was sent, or not yet: neither is a delivery."""
    session = _session_factory()()
    setup = _Firm(session)
    note = _dispatched(setup)

    with pytest.raises(ValidationError, match=message):
        DeliveryNoteService(session).record_delivery_proof(
            note.id,
            _proof(delivered_at=when),
            firm_scope=setup.firm.id,
            actor_id=uuid4(),
        )


def test_the_list_finds_notes_dispatched_but_not_yet_proven_delivered() -> None:
    """The filter and the summary count agree, and a proof takes a note off."""
    session = _session_factory()()
    setup = _Firm(session)
    note = _dispatched(setup)
    service = DeliveryNoteService(session)

    def awaiting() -> list[UUID]:
        rows, _ = service.list_notes(
            firm_scope=setup.firm.id,
            filters=DeliveryNoteListFilters(awaiting_delivery_proof=True),
            page=1,
            page_size=20,
            search=None,
            sort_by="created_at",
            descending=True,
        )
        return [row.id for row in rows]

    assert awaiting() == [note.id]
    assert service.summary(firm_scope=setup.firm.id).awaiting_delivery_proof == 1
    service.record_delivery_proof(
        note.id, _proof(attachment=None), firm_scope=setup.firm.id, actor_id=uuid4()
    )
    assert awaiting() == []
    assert service.summary(firm_scope=setup.firm.id).awaiting_delivery_proof == 0
