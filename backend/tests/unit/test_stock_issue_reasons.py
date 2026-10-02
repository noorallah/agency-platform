"""Stock issued for internal use, to staff, or for display (STK-3, decision A61).

Stock taken for the office, given to staff or put out as a sample is not lost:
it is an expense with a name. Each of the three reasons posts the value to its
own expense -- *Stock Used in Business*, *Staff Welfare*, *Samples and Display*
-- while damage, expiry and loss stay on the inventory adjustment account.
"""

# ruff: noqa: D103

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.finance.models import FirmControlAccount, JournalEntry, JournalLine
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.opening_setup import INDIRECT_EXPENSE_ACCOUNTS
from app.inventory.models import InventoryRecord
from app.inventory.schemas import StockWriteOffCreate
from app.inventory.services import InventoryService
from app.products.models import Product
from tests.unit.test_opening_stock_import_file import _ON
from tests.unit.test_stock_valuation import _stocked

pytestmark = pytest.mark.typed_document_numbers


def _issue(reason: str) -> tuple[object, dict[str, Decimal]]:
    """Write one bag of rice off for a reason; return each account's debit."""
    session, firm = _stocked()
    rice = session.scalar(
        select(Product).where(Product.firm_id == firm.id, Product.code == "RICE")
    )
    assert rice is not None
    record = session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.firm_id == firm.id, InventoryRecord.product_id == rice.id
        )
    )
    assert record is not None
    movement = InventoryService(session).write_off_stock(
        StockWriteOffCreate(
            branch_id=record.branch_id,
            warehouse_id=record.warehouse_id,
            product_id=rice.id,
            reason=reason,  # type: ignore[arg-type]
            quantity=Decimal("1"),
            transaction_date=_ON + timedelta(days=2),
        ),
        firm_scope=firm.id,
        actor_id=firm.id,
    )
    session.commit()
    purposes = {
        row.ledger_account_id: row.purpose
        for row in session.scalars(
            select(FirmControlAccount).where(FirmControlAccount.firm_id == firm.id)
        )
    }
    entry = session.scalar(
        select(JournalEntry).where(JournalEntry.source_id == movement.id)
    )
    assert entry is not None
    debits = {
        purposes.get(line.ledger_account_id, "?"): line.debit_amount
        for line in session.scalars(
            select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
        )
        if line.debit_amount > 0
    }
    return movement, debits


@pytest.mark.parametrize(
    ("reason", "purpose"),
    [
        ("INTERNAL_USE", ControlAccountPurpose.INTERNAL_USE),
        ("STAFF", ControlAccountPurpose.STAFF_WELFARE),
        ("DISPLAY", ControlAccountPurpose.SAMPLES_AND_DISPLAY),
    ],
)
def test_stock_issued_is_booked_to_its_own_expense(
    reason: str, purpose: ControlAccountPurpose
) -> None:
    movement, debits = _issue(reason)

    # One bag at the opening cost of 50.
    assert debits == {purpose.value: Decimal("50.00")}
    assert movement.reference_type == reason  # type: ignore[attr-defined]


def test_damage_still_lands_on_the_adjustment_account() -> None:
    _, debits = _issue("DAMAGE")

    assert debits == {
        ControlAccountPurpose.INVENTORY_ADJUSTMENT.value: Decimal("50.00")
    }


def test_a_new_firms_chart_carries_the_three_expenses() -> None:
    seeded = {account.purpose for account in INDIRECT_EXPENSE_ACCOUNTS}

    assert {
        ControlAccountPurpose.INTERNAL_USE,
        ControlAccountPurpose.STAFF_WELFARE,
        ControlAccountPurpose.SAMPLES_AND_DISPLAY,
    } <= seeded
