"""Which batch a product leaves from (STK-11, §70 row 15, decision A63).

Earliest expiry first unless the product says otherwise: FIFO draws the batch
received first, and PICK refuses to draw at all until a person names the
batches on the line.
"""

# ruff: noqa: D103

from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.inventory.services import InventoryService
from app.products.schemas.product import IssueRule, ProductCreate
from tests.unit.test_counter_bill_batches import _Counter


def _received_late_first(shop: _Counter) -> None:
    """Make LATE the batch that arrived first."""
    early = shop.batches["EARLY"]
    shop.batches["LATE"].created_at = early.created_at - timedelta(days=30)
    shop.session.commit()


def _sell(shop: _Counter, picks: list[object] | None = None) -> None:
    draft = shop.bills.create_invoice(
        shop.bill(picks),  # type: ignore[arg-type]
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    shop.bills.approve_invoice(draft.id, firm_scope=shop.firm.id, actor_id=shop.actor)


def test_with_no_rule_the_earliest_expiry_leaves_first() -> None:
    shop = _Counter()
    _received_late_first(shop)

    _sell(shop)

    assert InventoryService(shop.session).issue_rule(shop.drug.id) == "FEFO"
    assert shop.drawn() == {"EARLY": Decimal("4.0000")}


def test_fifo_draws_the_batch_received_first() -> None:
    shop = _Counter()
    _received_late_first(shop)
    shop.drug.issue_rule = "FIFO"
    shop.session.commit()

    _sell(shop)

    assert shop.drawn() == {"LATE": Decimal("4.0000")}


def test_pick_refuses_to_choose_for_the_person() -> None:
    shop = _Counter()
    shop.drug.issue_rule = "PICK"
    shop.session.commit()

    with pytest.raises(ValidationError, match="issued by choosing the batch"):
        _sell(shop)


def test_pick_ships_the_batch_the_person_named() -> None:
    shop = _Counter()
    shop.drug.issue_rule = "PICK"
    shop.session.commit()

    _sell(shop, [shop.pick("LATE")])

    assert shop.drawn() == {"LATE": Decimal("4.0000")}


def test_the_product_form_takes_the_rule() -> None:
    data = ProductCreate(
        code="AMOX", name="Amoxicillin", product_type="STOCK_ITEM", issue_rule="PICK"
    )

    assert data.issue_rule is IssueRule.PICK
