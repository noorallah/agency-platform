"""Round every bill to the nearest rupee, a firm setting (row F3, backlog 134).

Off, which is every firm until it switches it on, a sales bill and a credit
note are left as worked out and a typed round-off is kept. On, the server
works the round-off out itself, whatever was typed, posts it to the Rounding
account and a bill returned in full is cancelled to the rupee.

The fixture's goods sell at a whole 100.00 and the unit suite configures no
tax, so the paise come from the bill's additional charges.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils.money import rupee_round_off
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesWorkflowSettings
from app.sales_order.schemas import SalesWorkflowSettingsWrite
from app.sales_order.services.workflow_settings_service import SalesWorkflowService
from app.sales_return.models import SalesReturn
from app.sales_return.schemas import SalesReturnSourceType
from app.sales_return.services import SalesReturnService
from tests.unit.test_sales_return_module import (
    PRICE,
    _account_movement,
    _Dispatch,
    _session_factory,
)


def _setup(session: Session, *, rounds: bool) -> _Dispatch:
    """Dispatch four units, nothing billed yet, with the firm's switch set."""
    setup = _Dispatch(session, billed=Decimal("0"))
    if rounds:
        session.add(
            SalesWorkflowSettings(
                firm_id=setup.firm.id,
                round_bills_to_rupee=True,
                created_by=setup.actor_id,
                updated_by=setup.actor_id,
            )
        )
        session.commit()
    return setup


def _bill_payload(
    setup: _Dispatch, *, charges: str, round_off: str = "0"
) -> SalesInvoiceCreate:
    """Describe a bill of the four units with some paise of charges on it."""
    return SalesInvoiceCreate(
        invoice_date=date(2026, 8, 4),
        additional_charges=Decimal(charges),
        round_off=Decimal(round_off),
        lines=[
            SalesInvoiceLineWrite(
                source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                source_document_id=setup.note.id,
                source_document_line_id=setup.note_line.id,
                line_number=1,
                current_invoice_quantity=Decimal("4"),
                unit_price=PRICE,
            )
        ],
    )


def _bill(
    setup: _Dispatch, *, charges: str, round_off: str = "0", approve: bool = True
) -> SalesInvoice:
    """Raise the bill and, unless told not to, approve it."""
    service = SalesInvoiceService(setup.session)
    row = service.create_invoice(
        _bill_payload(setup, charges=charges, round_off=round_off),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    if approve:
        row = service.approve_invoice(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )
    return row


def _full_return(setup: _Dispatch, bill: SalesInvoice, *, charges: str) -> SalesReturn:
    """Complete a return of everything the bill charged, charges and all."""
    line = setup.session.scalar(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == bill.id)
    )
    assert line is not None
    payload = setup.payload(quantity=Decimal("4"))
    payload.additional_charges = Decimal(charges)
    payload.lines[0].source_document_type = SalesReturnSourceType.SALES_INVOICE
    payload.lines[0].source_document_id = bill.id
    payload.lines[0].source_document_line_id = line.id
    service = SalesReturnService(setup.session)
    row = service.create_return(payload, firm_id=setup.firm.id, actor_id=setup.actor_id)
    service.approve_return(row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    return service.complete_return(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )


def _owed(setup: _Dispatch) -> Decimal:
    """Return what the customer's account says they owe."""
    setup.session.refresh(setup.customer)
    return Decimal(str(setup.customer.current_outstanding))


@pytest.mark.parametrize(
    ("total", "round_off"),
    [
        ("9974.59", "0.41"),
        ("9974.49", "-0.49"),
        ("9974.50", "0.50"),
        ("9975.00", "0"),
        ("0.4999", "-0.4999"),
        ("0", "0"),
    ],
)
def test_the_round_off_takes_a_total_to_the_nearest_rupee(
    total: str, round_off: str
) -> None:
    """Half a rupee goes up, and the two always sum to a whole number."""
    answer = rupee_round_off(Decimal(total))

    assert answer == Decimal(round_off)
    assert (Decimal(total) + answer) % 1 == 0


def test_a_firm_that_has_not_switched_it_on_is_left_as_worked_out() -> None:
    """Off: no round-off is added, and the Rounding account is not touched."""
    with _session_factory()() as session:
        setup = _setup(session, rounds=False)

        bill = _bill(setup, charges="0.59")

        assert bill.round_off == Decimal("0")
        assert bill.grand_total == Decimal("400.59")
        assert _account_movement(session, setup.firm.id, "Rounding") == Decimal("0")


def test_a_typed_round_off_is_kept_where_the_switch_is_off() -> None:
    """Off: what somebody typed stands, and stays in revenue as it always has."""
    with _session_factory()() as session:
        setup = _setup(session, rounds=False)

        bill = _bill(setup, charges="0.59", round_off="0.41")

        assert bill.round_off == Decimal("0.41")
        assert bill.grand_total == Decimal("401")
        assert _account_movement(session, setup.firm.id, "Rounding") == Decimal("0")
        assert _account_movement(session, setup.firm.id, "Sales") == Decimal("-401")


def test_the_server_rounds_the_bill_up_and_posts_the_difference() -> None:
    """On: 400.59 is billed as 401.00 and the 0.41 is credited to Rounding."""
    with _session_factory()() as session:
        setup = _setup(session, rounds=True)

        bill = _bill(setup, charges="0.59")

        assert bill.round_off == Decimal("0.41")
        assert bill.grand_total == Decimal("401")
        assert _account_movement(session, setup.firm.id, "Rounding") == Decimal("-0.41")
        assert _account_movement(session, setup.firm.id, "Sales") == Decimal("-400.59")
        assert _account_movement(session, setup.firm.id, "Receivable") == Decimal("401")
        assert _owed(setup) == Decimal("401")


def test_the_server_rounds_the_bill_down_and_posts_the_difference() -> None:
    """On: 400.49 is billed as 400.00 and the 0.49 is debited to Rounding."""
    with _session_factory()() as session:
        setup = _setup(session, rounds=True)

        bill = _bill(setup, charges="0.49")

        assert bill.round_off == Decimal("-0.49")
        assert bill.grand_total == Decimal("400")
        assert _account_movement(session, setup.firm.id, "Rounding") == Decimal("0.49")
        assert _account_movement(session, setup.firm.id, "Receivable") == Decimal("400")


def test_nobody_types_the_round_off_where_the_switch_is_on() -> None:
    """On: a typed round-off is not kept, on the first save or on a later one."""
    with _session_factory()() as session:
        setup = _setup(session, rounds=True)
        service = SalesInvoiceService(session)

        bill = _bill(setup, charges="0.59", round_off="5", approve=False)
        assert bill.round_off == Decimal("0.41")

        bill = service.update_invoice(
            bill.id,
            _bill_payload(setup, charges="0.20", round_off="5"),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
        assert bill.round_off == Decimal("-0.20")
        assert bill.grand_total == Decimal("400")


def test_a_bill_already_whole_gets_no_round_off_and_no_rounding_leg() -> None:
    """On: a bill that needs none posts nothing to the Rounding account."""
    with _session_factory()() as session:
        setup = _setup(session, rounds=True)

        bill = _bill(setup, charges="0")

        assert bill.round_off == Decimal("0")
        assert bill.grand_total == Decimal("400")
        assert _account_movement(session, setup.firm.id, "Rounding") == Decimal("0")


def test_a_full_credit_note_cancels_a_rounded_bill_exactly() -> None:
    """On: the return of everything is rounded the same way, and nothing is owed."""
    with _session_factory()() as session:
        setup = _setup(session, rounds=True)
        bill = _bill(setup, charges="0.59")

        credit = _full_return(setup, bill, charges="0.59")

        assert credit.round_off == Decimal("0.41")
        assert credit.grand_total == Decimal("401")
        assert _account_movement(session, setup.firm.id, "Rounding") == Decimal("0")
        assert _account_movement(session, setup.firm.id, "Receivable") == Decimal("0")
        assert _account_movement(session, setup.firm.id, "Sales Returns") == Decimal(
            "400.59"
        )
        assert _owed(setup) == Decimal("0")


def test_a_credit_note_is_left_as_worked_out_where_the_switch_is_off() -> None:
    """Off: the credit note carries no round-off and posts none."""
    with _session_factory()() as session:
        setup = _setup(session, rounds=False)
        bill = _bill(setup, charges="0.59")

        credit = _full_return(setup, bill, charges="0.59")

        assert credit.round_off == Decimal("0")
        assert credit.grand_total == Decimal("400.59")
        assert _account_movement(session, setup.firm.id, "Rounding") == Decimal("0")
        assert _owed(setup) == Decimal("0")


def test_the_switch_is_off_until_a_firm_turns_it_on_and_an_omission_keeps_it() -> None:
    """The setting reads off for a firm with no row, and a write without it stays."""
    with _session_factory()() as session:
        setup = _setup(session, rounds=False)
        service = SalesWorkflowService(session)
        stages = {
            "quotation_stage": True,
            "sales_order_stage": True,
            "delivery_note_stage": True,
        }

        assert service.settings_response(setup.firm.id).round_bills_to_rupee is False
        assert service.rounds_bills(setup.firm.id) is False

        written = service.update_settings(
            SalesWorkflowSettingsWrite(**stages, round_bills_to_rupee=True),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
        assert written.round_bills_to_rupee is True
        assert service.rounds_bills(setup.firm.id) is True

        kept = service.update_settings(
            SalesWorkflowSettingsWrite(**stages),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
        assert kept.round_bills_to_rupee is True


def test_a_first_write_that_does_not_name_the_switch_leaves_it_off() -> None:
    """A firm that saves its stages without the switch is not made to round."""
    with _session_factory()() as session:
        setup = _setup(session, rounds=False)

        written = SalesWorkflowService(session).update_settings(
            SalesWorkflowSettingsWrite(
                quotation_stage=True,
                sales_order_stage=True,
                delivery_note_stage=True,
            ),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )

        assert written.round_bills_to_rupee is False
