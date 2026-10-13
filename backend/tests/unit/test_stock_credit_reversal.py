"""Input credit given up on stock given away or written off (D-CMP-24).

The bill is the one `test_input_credit_eligibility` builds: 4 x 100 at 18%
local GST, CGST 9% + SGST 9%, dated 2 August 2026. Ten of the product are then
held at a cost of 100 each, so one unit leaving under a reason that reverses
gives up 9 + 9.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Warehouse
from app.finance.models import FirmControlAccount, JournalEntry, JournalLine
from app.gst_returns.models import ItcReversal
from app.gst_returns.services.gstr_service import GstReturnService
from app.gst_returns.services.rule37 import Rule37Service
from app.inventory.models import InventoryTransaction
from app.inventory.models.adjustment_reason import StockAdjustmentReason
from app.inventory.schemas import InventoryAdjustmentCreate, StockWriteOffCreate
from app.inventory.services import InventoryService
from app.inventory.services.adjustment_reasons import (
    REVERSING_REASONS,
    AdjustmentReasonService,
    AdjustmentReasonWrite,
)
from app.purchase_invoice.models import PurchaseInvoice
from tests.unit.test_input_credit_eligibility import _bill

pytestmark = pytest.mark.typed_document_numbers

D = Decimal
ON = date(2026, 8, 5)


class _Held:
    """A firm holding ten of the billed product at a cost of 100."""

    def __init__(self, **bill: str) -> None:
        """Build the bill, then the stock."""
        session, firm_id, bill_id, actor_id, line = _bill(**bill)  # type: ignore[arg-type]
        self.session: Session = session
        self.firm_id: UUID = firm_id
        self.bill_id: UUID = bill_id
        self.actor_id: UUID = actor_id
        self.product_id: UUID = line.product_id
        purchase = session.get(PurchaseInvoice, bill_id)
        assert purchase is not None
        self.branch_id: UUID = purchase.branch_id
        self.warehouse_id: UUID = session.scalars(
            select(Warehouse.id).where(Warehouse.firm_id == firm_id)
        ).one()
        self._number = 0
        inventory = InventoryService(session)
        valuation = inventory.valuation_for(
            firm_scope=firm_id, product_id=self.product_id
        )
        valuation.average_cost = D("100")
        session.commit()
        self.adjust("10")

    def _reference(self) -> str:
        """Return the next reference of the test's own."""
        self._number += 1
        return f"G1-{self._number}"

    def adjust(self, quantity: str, reason: str | None = None) -> InventoryTransaction:
        """Correct the stock by a signed quantity, under a reason or none."""
        movement = InventoryService(self.session).create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=self.branch_id,
                warehouse_id=self.warehouse_id,
                product_id=self.product_id,
                quantity=D(quantity),
                reference_number=self._reference(),
                reason_code=reason,
                transaction_date=ON,
            ),
            firm_scope=self.firm_id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return movement

    def write_off(self, reason: str, quantity: str) -> InventoryTransaction:
        """Take stock off the books under a reason."""
        movement = InventoryService(self.session).write_off_stock(
            StockWriteOffCreate(
                branch_id=self.branch_id,
                warehouse_id=self.warehouse_id,
                product_id=self.product_id,
                reason=reason,
                quantity=D(quantity),
                reference_number=self._reference(),
                transaction_date=ON,
            ),
            firm_scope=self.firm_id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return movement

    def rows(self) -> list[ItcReversal]:
        """Return every credit movement of the firm, oldest first."""
        return list(
            self.session.scalars(
                select(ItcReversal)
                .where(ItcReversal.firm_id == self.firm_id)
                .order_by(ItcReversal.created_at, ItcReversal.id)
            )
        )

    def table4(self) -> dict[str, object]:
        """Return GSTR-3B for the day the stock moved."""
        return GstReturnService(self.session).gstr3b(
            firm_scope=self.firm_id, from_date=ON, to_date=ON
        )

    def switch(self, code: str, on: bool) -> None:
        """Set whether one of the firm's reasons reverses."""
        AdjustmentReasonService(self.session).ensure_seeded(self.firm_id)
        reason = self.session.scalars(
            select(StockAdjustmentReason).where(
                StockAdjustmentReason.firm_id == self.firm_id,
                StockAdjustmentReason.code == code,
            )
        ).one()
        reason.reverses_input_credit = on
        self.session.commit()


def _heads(block: object) -> tuple[float, float, float, float]:
    assert isinstance(block, dict)
    return (
        block["integrated_tax"],
        block["central_tax"],
        block["state_tax"],
        block["cess"],
    )


def test_a_sample_gives_up_the_credit_at_the_cost_it_left_at() -> None:
    held = _Held()

    movement = held.write_off("SAMPLE", "2")

    (row,) = held.rows()
    assert (row.basis, row.movement, row.reason_code) == ("STOCK", "REVERSAL", "SAMPLE")
    assert row.inventory_transaction_id == movement.id
    assert row.purchase_invoice_id == held.bill_id
    assert (row.stock_value, row.movement_date) == (D("200.00"), ON)
    assert (row.igst, row.cgst, row.sgst, row.cess) == (
        D("0"),
        D("18.00"),
        D("18.00"),
        D("0"),
    )


def test_the_reversal_moves_the_credit_to_input_tax_not_claimable() -> None:
    held = _Held()

    held.write_off("SAMPLE", "2")

    (row,) = held.rows()
    purposes = {
        account.ledger_account_id: account.purpose
        for account in held.session.scalars(
            select(FirmControlAccount).where(FirmControlAccount.firm_id == held.firm_id)
        )
    }
    entry = held.session.get(JournalEntry, row.journal_entry_id)
    assert entry is not None
    assert (entry.source_module, entry.source_id) == ("itc_stock", row.id)
    assert entry.journal_date == ON
    legs = sorted(
        (
            purposes.get(line.ledger_account_id, "?"),
            line.debit_amount,
            line.credit_amount,
        )
        for line in held.session.scalars(
            select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
        )
    )
    assert legs == [
        ("INELIGIBLE_INPUT_TAX", D("36.00"), D("0")),
        ("INPUT_TAX_CGST", D("0"), D("18.00")),
        ("INPUT_TAX_SGST", D("0"), D("18.00")),
    ]


def test_gstr3b_shows_it_in_4b1_and_takes_it_off_the_net_credit() -> None:
    held = _Held()
    before = held.table4()

    held.write_off("SAMPLE", "2")

    after = held.table4()
    assert _heads(before["itc_reversed_stock"]) == (0.0, 0.0, 0.0, 0.0)
    assert _heads(after["itc_reversed_stock"]) == (0.0, 18.0, 18.0, 0.0)
    assert _heads(after["itc_reclaimed_stock"]) == (0.0, 0.0, 0.0, 0.0)
    net_before, net_after = _heads(before["net_itc"]), _heads(after["net_itc"])
    assert (net_before[1] - net_after[1], net_before[2] - net_after[2]) == (18.0, 18.0)
    # The other lines of table 4 are where they were.
    for key in ("eligible_itc", "itc_reversed_blocked", "itc_reversed"):
        assert _heads(after[key]) == _heads(before[key])


def test_a_loss_taken_off_by_an_adjustment_reverses_as_a_write_off_does() -> None:
    held = _Held()

    held.adjust("-1", "LOSS")

    (row,) = held.rows()
    assert (row.movement, row.reason_code) == ("REVERSAL", "LOSS")
    assert (row.cgst, row.sgst) == (D("9.00"), D("9.00"))


@pytest.mark.parametrize("reason", sorted(REVERSING_REASONS - {"FREE_TO_CUSTOMER"}))
def test_each_reason_the_section_names_reverses(reason: str) -> None:
    held = _Held()

    held.write_off(reason, "1")

    assert [(row.reason_code, row.cgst) for row in held.rows()] == [(reason, D("9.00"))]


def test_a_count_correction_with_no_reason_reverses_nothing() -> None:
    held = _Held()

    held.adjust("-1")

    assert held.rows() == []


@pytest.mark.parametrize("reason", ["INTERNAL_USE", "STAFF", "DISPLAY"])
def test_stock_used_in_the_business_reverses_nothing(reason: str) -> None:
    held = _Held()

    held.write_off(reason, "1")

    assert held.rows() == []


def test_a_firm_that_switches_a_reason_off_gets_none_for_it() -> None:
    held = _Held()
    held.switch("SAMPLE", on=False)

    held.write_off("SAMPLE", "2")

    assert held.rows() == []
    assert _heads(held.table4()["itc_reversed_stock"]) == (0.0, 0.0, 0.0, 0.0)


def test_a_firm_can_switch_a_reason_of_its_own_on() -> None:
    held = _Held()
    held.switch("DISPLAY", on=True)

    held.write_off("DISPLAY", "1")

    assert [(row.reason_code, row.sgst) for row in held.rows()] == [
        ("DISPLAY", D("9.00"))
    ]


def test_a_sample_that_comes_back_claims_the_credit_again() -> None:
    held = _Held()
    held.write_off("SAMPLE", "2")

    movement = held.adjust("1", "SAMPLE")

    reversal, reclaim = held.rows()
    assert (reclaim.movement, reclaim.inventory_transaction_id) == (
        "RECLAIM",
        movement.id,
    )
    assert (reclaim.cgst, reclaim.sgst) == (D("9.00"), D("9.00"))
    assert reclaim.journal_entry_id not in (None, reversal.journal_entry_id)
    table = held.table4()
    assert _heads(table["itc_reversed_stock"]) == (0.0, 18.0, 18.0, 0.0)
    assert _heads(table["itc_reclaimed_stock"]) == (0.0, 9.0, 9.0, 0.0)


def test_no_more_is_claimed_back_than_stands_reversed() -> None:
    held = _Held()
    held.write_off("SAMPLE", "1")

    held.adjust("3", "SAMPLE")

    reversal, reclaim = held.rows()
    assert (reversal.cgst, reclaim.cgst, reclaim.sgst) == (
        D("9.00"),
        D("9.00"),
        D("9.00"),
    )


def test_stock_in_under_a_reason_claims_nothing_when_nothing_was_reversed() -> None:
    held = _Held()

    held.adjust("1", "SAMPLE")

    assert held.rows() == []


def test_goods_whose_credit_was_blocked_give_none_back() -> None:
    held = _Held(product_says="BLOCKED")

    held.write_off("SAMPLE", "2")

    assert held.rows() == []


def test_rule_37_does_not_read_the_stock_rows() -> None:
    held = _Held()
    held.write_off("SAMPLE", "2")
    rule37 = Rule37Service(held.session)

    reversed_, reclaimed = rule37.movements_between(
        firm_id=held.firm_id, from_date=ON, to_date=ON
    )
    (due,) = rule37.rows(firm_id=held.firm_id, as_of=date(2027, 2, 10))

    assert (reversed_.cgst, reclaimed.cgst) == (D("0"), D("0"))
    # The whole of the bill's credit is still the unpaid bill's to reverse.
    assert (due.move["cgst"], due.move["sgst"]) == (D("36.00"), D("36.00"))
    assert _heads(held.table4()["itc_reversed_rule37"]) == (0.0, 0.0, 0.0, 0.0)


def test_the_system_reasons_start_as_the_section_names_them() -> None:
    held = _Held()

    listed = {
        reason.code: reason.reverses_input_credit
        for reason in AdjustmentReasonService(held.session).list_reasons(held.firm_id)
    }

    assert listed == {
        "DAMAGE": True,
        "EXPIRY": True,
        "LOSS": True,
        "INTERNAL_USE": False,
        "STAFF": False,
        "DISPLAY": False,
        "FREE_TO_CUSTOMER": True,
        "SAMPLE": True,
    }


def test_a_reason_of_the_firms_own_is_off_until_it_says_otherwise() -> None:
    held = _Held()
    service = AdjustmentReasonService(held.session)

    plain = service.create(
        AdjustmentReasonWrite(code="THEFT", name="Stolen"),
        firm_id=held.firm_id,
        actor_id=held.actor_id,
    )
    switched = service.update(
        plain.id,
        AdjustmentReasonWrite(code="THEFT", name="Stolen", reverses_input_credit=True),
        firm_id=held.firm_id,
        actor_id=held.actor_id,
    )
    renamed = service.update(
        plain.id,
        AdjustmentReasonWrite(code="THEFT", name="Stolen goods"),
        firm_id=held.firm_id,
        actor_id=held.actor_id,
    )

    assert plain.reverses_input_credit is False
    assert switched.reverses_input_credit is True
    # A save that does not mention the switch leaves it as it was.
    assert (renamed.name, renamed.reverses_input_credit) == ("Stolen goods", True)
