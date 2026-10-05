"""The transporter master and the carrier on a delivery note (§87 #5, SG-5).

A firm keeps its carriers once; a note that picks one copies the name, the id
an e-way bill asks for and the usual mode into its own columns, so the challan
and the e-way bill read the note and a later edit of the master rewrites
nothing already raised.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select

from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.delivery_note.models import DeliveryNote
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.delivery_note.services.transporters import (
    TransporterService,
    TransporterWrite,
)
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

GSTIN = "29AAACR5055K1Z5"
TRANSIN = "29AABCT1332L1ZU"


def _order_line(setup: _Firm) -> tuple[UUID, UUID]:
    """Approve an order for four units; return its id and its line's."""
    actor = uuid4()
    orders = SalesOrderService(setup.session)
    order = orders.stage_order(
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
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    orders.stage_approval(order.id, firm_scope=setup.firm.id, actor_id=actor)
    line_id = setup.session.scalar(
        select(SalesOrderLine.id).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line_id is not None
    setup.session.commit()
    return order.id, line_id


def _payload(order_id: UUID, line_id: UUID, **fields: object) -> DeliveryNoteCreate:
    """Describe a note for one unit of the order, with the transport given."""
    return DeliveryNoteCreate.model_validate(
        {
            "sales_order_id": order_id,
            "delivery_date": date(2026, 8, 3),
            "lines": [
                DeliveryNoteLineWrite(
                    sales_order_line_id=line_id,
                    line_number=1,
                    current_delivery_quantity=Decimal("1"),
                )
            ],
            **fields,
        }
    )


def _carrier(setup: _Firm, **fields: object) -> UUID:
    """Add a transporter and return its id."""
    data = TransporterWrite.model_validate(
        {"name": "Speedy Logistics", "gstin": GSTIN, "default_mode": "ROAD", **fields}
    )
    return (
        TransporterService(setup.session)
        .save(data, firm_id=setup.firm.id, actor_id=uuid4())
        .id
    )


def _note(setup: _Firm, data: DeliveryNoteCreate) -> DeliveryNote:
    """Raise a draft note."""
    note = DeliveryNoteService(setup.session).stage_note(
        data, firm_id=setup.firm.id, actor_id=uuid4()
    )
    setup.session.commit()
    return note


def test_a_transporter_is_kept_once_by_name() -> None:
    """The list is by name; a second of the same name is refused."""
    setup = _Firm(_session_factory()())
    service = TransporterService(setup.session)
    _carrier(setup, name="Zed Carriers", gstin=None)
    first = _carrier(setup)

    assert [row.name for row in service.transporters(setup.firm.id)] == [
        "Speedy Logistics",
        "Zed Carriers",
    ]
    with pytest.raises(ConflictError, match="already a transporter"):
        _carrier(setup)
    renamed = service.save(
        TransporterWrite(name="Speedy Logistics", phone=" 98450 ", is_active=False),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
        transporter_id=first,
    )
    assert (renamed.phone, renamed.is_active) == ("98450", False)
    assert [
        row.name for row in service.transporters(setup.firm.id, active_only=True)
    ] == ["Zed Carriers"]


def test_an_id_that_is_not_the_shape_of_a_gstin_is_refused() -> None:
    """The e-way bill portal would refuse it later, with the goods waiting."""
    with pytest.raises((SchemaError, ValidationError)):
        TransporterWrite(name="Bad Id", gstin="NOT-A-GSTIN")


def test_a_deleted_transporter_is_gone_and_its_name_is_free() -> None:
    """Removing one releases the name; another firm cannot reach it."""
    setup = _Firm(_session_factory()())
    service = TransporterService(setup.session)
    carrier = _carrier(setup)

    with pytest.raises(ResourceNotFoundError):
        service.get(carrier, uuid4())
    service.delete(carrier, firm_id=setup.firm.id, actor_id=uuid4())

    assert service.transporters(setup.firm.id) == []
    assert _carrier(setup) != carrier


def test_a_note_inherits_the_transporter_it_names() -> None:
    """Name, id and mode are copied; the freight terms are the note's own."""
    setup = _Firm(_session_factory()())
    order_id, line_id = _order_line(setup)
    carrier = _carrier(setup)

    note = _note(
        setup,
        _payload(order_id, line_id, transporter_id=carrier, freight_terms="TO_PAY"),
    )

    assert (
        note.transporter_id,
        note.transporter_name,
        note.transporter_gstin,
        note.transport_mode,
        note.freight_terms,
    ) == (carrier, "Speedy Logistics", GSTIN, "ROAD", "TO_PAY")
    response = DeliveryNoteService(setup.session).note_response(note)
    assert (response.transporter_id, response.freight_terms) == (carrier, "TO_PAY")


def test_an_unregistered_transporter_gives_its_transin_to_the_e_way_bill() -> None:
    """The id the e-way bill reads off the note is the TRANSIN, with no GSTIN."""
    setup = _Firm(_session_factory()())
    order_id, line_id = _order_line(setup)
    carrier = _carrier(setup, gstin=None, transporter_ref=TRANSIN)

    note = _note(setup, _payload(order_id, line_id, transporter_id=carrier))

    assert note.transporter_gstin == TRANSIN


def test_what_is_typed_on_the_note_wins_over_the_master() -> None:
    """A one-off mode or name for this dispatch is kept as typed."""
    setup = _Firm(_session_factory()())
    order_id, line_id = _order_line(setup)
    carrier = _carrier(setup)

    note = _note(
        setup,
        _payload(
            order_id,
            line_id,
            transporter_id=carrier,
            transport_mode="RAIL",
            transporter_name="Speedy (rail desk)",
        ),
    )

    assert (note.transporter_name, note.transport_mode) == (
        "Speedy (rail desk)",
        "RAIL",
    )
    assert note.transporter_gstin == GSTIN


def test_editing_the_master_leaves_a_note_already_raised_alone() -> None:
    """The note owns what it copied."""
    setup = _Firm(_session_factory()())
    order_id, line_id = _order_line(setup)
    carrier = _carrier(setup)
    note = _note(setup, _payload(order_id, line_id, transporter_id=carrier))

    TransporterService(setup.session).save(
        TransporterWrite(name="Speedy Cargo", default_mode="AIR"),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
        transporter_id=carrier,
    )
    setup.session.refresh(note)

    assert (note.transporter_name, note.transporter_gstin, note.transport_mode) == (
        "Speedy Logistics",
        GSTIN,
        "ROAD",
    )


def test_an_edit_that_does_not_mention_the_carrier_keeps_it() -> None:
    """Absent leaves alone; naming another carrier takes its details."""
    setup = _Firm(_session_factory()())
    order_id, line_id = _order_line(setup)
    carrier = _carrier(setup)
    other = _carrier(setup, name="Zed Carriers", gstin=None, default_mode="AIR")
    notes = DeliveryNoteService(setup.session)
    note = _note(
        setup,
        _payload(order_id, line_id, transporter_id=carrier, freight_terms="PAID"),
    )

    kept = notes.update_note(
        note.id, _payload(order_id, line_id), firm_scope=setup.firm.id, actor_id=uuid4()
    )
    assert (kept.transporter_id, kept.transporter_name, kept.freight_terms) == (
        carrier,
        "Speedy Logistics",
        "PAID",
    )

    moved = notes.update_note(
        note.id,
        _payload(order_id, line_id, transporter_id=other, freight_terms="TO_BE_BILLED"),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )
    assert (
        moved.transporter_id,
        moved.transporter_name,
        moved.transport_mode,
        moved.freight_terms,
    ) == (other, "Zed Carriers", "AIR", "TO_BE_BILLED")


def test_an_inactive_or_unknown_transporter_is_refused() -> None:
    """A carrier no longer used is not picked by accident."""
    setup = _Firm(_session_factory()())
    order_id, line_id = _order_line(setup)
    carrier = _carrier(setup, is_active=False)

    with pytest.raises(ValidationError, match="marked inactive"):
        _note(setup, _payload(order_id, line_id, transporter_id=carrier))
    setup.session.rollback()
    with pytest.raises(ResourceNotFoundError):
        _note(setup, _payload(order_id, line_id, transporter_id=uuid4()))


def test_only_the_three_freight_terms_are_taken() -> None:
    """Paid, to pay or to be billed."""
    with pytest.raises(SchemaError):
        _payload(uuid4(), uuid4(), freight_terms="FREE")
