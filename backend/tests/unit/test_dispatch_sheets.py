"""The pick list and the loading sheet (SEL-13, decision A92).

Three approved notes for one product: 4 and 6 on van KA-01, 3 on no van. The
pick list sums 13 of the product, earliest expiry left to dispatch. The
loading sheet puts each note on its vehicle, ordered by the customer's place
on the round, and both PDFs render.
"""

# ruff: noqa: D103

from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.delivery_note.services.dispatch_sheets import (
    NO_VEHICLE,
    DispatchSheetService,
)
from app.sales.models.territory import TerritoryCustomerAssignment
from tests.unit.test_delivery_note_module import (
    _approved_note,
    _approved_order,
    _branch,
    _customer,
    _firm,
    _product,
    _session_factory,
    _stock,
    _warehouse,
)

D = Decimal


def test_the_sheets_sum_the_picks_and_order_the_drops() -> None:
    session = _session_factory()()
    actor = uuid4()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    first = _customer(session, firm_id=firm.id)
    second = Customer(
        firm_id=firm.id,
        code="CUS-ZED",
        customer_type="RETAIL",
        name="Aardvark Stores",
        display_name="Aardvark Stores",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(second)
    session.commit()
    product = _product(session, firm_id=firm.id)
    _stock(session, firm=firm, branch=branch, warehouse=warehouse, product=product)

    notes = []
    for customer, quantity, vehicle in (
        (first, D("4"), "KA-01"),
        (second, D("6"), "KA-01"),
        (first, D("3"), None),
    ):
        order, line = _approved_order(
            session,
            firm=firm,
            branch=branch,
            warehouse=warehouse,
            customer=customer,
            product=product,
            quantity=quantity,
            actor_id=actor,
        )
        note = _approved_note(
            session,
            firm=firm,
            order=order,
            order_line=line,
            quantity=quantity,
            actor_id=actor,
        )
        note.vehicle = vehicle
        notes.append(note)
    # The round visits the first customer before Aardvark, whatever the names.
    round_id = uuid4()
    for customer, place in ((first, 1), (second, 2)):
        session.add(
            TerritoryCustomerAssignment(
                territory_id=round_id,
                customer_id=customer.id,
                visit_sequence=place,
            )
        )
    for note in notes:
        note.territory_id = round_id
    session.commit()

    sheets = DispatchSheetService(session)
    ids = [note.id for note in notes]
    [pick] = sheets.pick_rows(firm.id, ids)
    assert pick.quantity == D("13")
    assert pick.batch == "Earliest expiry at dispatch"

    drops = sheets.drops(firm.id, ids)
    assert sorted(drops) == ["KA-01", NO_VEHICLE]
    van = [drop.customer_name for drop in drops["KA-01"]]
    assert van == [first.name, "Aardvark Stores"], "round order, not names"
    assert [drop.value > 0 for drop in drops["KA-01"]] == [True, True]

    assert sheets.pick_list_pdf(firm.id, ids).startswith(b"%PDF")
    assert sheets.loading_sheet_pdf(firm.id, ids).startswith(b"%PDF")

    with pytest.raises(ValidationError, match="at least one"):
        sheets.pick_rows(firm.id, [])
