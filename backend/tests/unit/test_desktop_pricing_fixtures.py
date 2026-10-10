r"""The server's own pricing answers, kept as files the desktop tests read.

D-UI-95 (2026-10-10): three document screens showed a line's total with tax
under *Taxable*. About 120 desktop tests passed while they did, because each
test's stand-in for the server was written from the same wrong idea as the
screen -- a ``net_amount`` before tax -- and nothing compared either with what
the server really sends.

So the stand-ins are no longer written by hand. Each case here is priced by
the real service and its answer is kept in
``desktop/test/fixtures/server_pricing``; the desktop tests load those files
and check the screen against them. This test fails when the service's answer
and the file differ, so the server cannot drift from what the desktop is
tested with. After a deliberate change, write the files again::

    $env:AGENCY_UPDATE_PRICING_FIXTURES = '1'
    uv run pytest tests/unit/test_desktop_pricing_fixtures.py -q
    Remove-Item Env:\\AGENCY_UPDATE_PRICING_FIXTURES

then run the desktop tests that read them
(``desktop/test/server_pricing_contract_test.dart``).

Every case carries a line discount, a discount on the whole document and,
where the document has one, a delivery charge, with GST at 18%: the parts a
screen leaves out when it works a line's taxable value out for itself.
"""

import json
import os
import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.quotation.schemas import QuotationCreate
from app.quotation.services.quotation_service import QuotationService
from app.sales_order.schemas import SalesOrderCreate
from app.sales_order.services.sales_order_service import SalesOrderService
from tests.unit.test_purchase_management import _vendor
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session
from tests.unit.test_sales_order_module import _tax_group

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "desktop"
    / "test"
    / "fixtures"
    / "server_pricing"
)
DAY = date(2026, 8, 4)
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_STAMPS = {"created_at", "updated_at"}


def _shop() -> _Firm:
    """Build a firm whose one product is 100.00 with GST at 18%."""
    setup = _Firm(_request_session())
    setup.product.selling_price = Decimal("100")
    setup.product.purchase_price = Decimal("60")
    setup.product.tax_profile_group_code = "GST_STANDARD"
    setup.session.commit()
    _tax_group(
        setup.session,
        firm_id=setup.firm.id,
        percent="18",
        starts=date(2026, 4, 1),
        ends=None,
    )
    return setup


def _line(setup: _Firm, **named: str) -> dict[str, object]:
    """Return five of the product at 100.00 less 10%, with what is named."""
    return {
        "product_id": str(setup.product.id),
        "unit_price": "100",
        "discount_percent": "10",
        **named,
    }


def _quotation() -> BaseModel:
    """Price a quotation under a 5% bill discount and a 40.00 delivery charge."""
    setup = _shop()
    payload = QuotationCreate.model_validate(
        {
            "customer_id": str(setup.customer.id),
            "branch_id": str(setup.branch.id),
            "warehouse_id": str(setup.warehouse.id),
            "quotation_date": DAY.isoformat(),
            "valid_until": date(2026, 9, 3).isoformat(),
            "bill_discount_percent": "5",
            "freight_amount": "40",
            "lines": [_line(setup, line_number="1", quantity="5")],
        }
    )
    return QuotationService(setup.session).preview_quotation(
        payload, firm_id=setup.firm.id, actor_id=uuid4()
    )


def _sales_order() -> BaseModel:
    """Price a sales order under the same discount and delivery charge."""
    setup = _shop()
    payload = SalesOrderCreate.model_validate(
        {
            "customer_id": str(setup.customer.id),
            "branch_id": str(setup.branch.id),
            "warehouse_id": str(setup.warehouse.id),
            "order_date": DAY.isoformat(),
            "bill_discount_percent": "5",
            "freight_amount": "40",
            "lines": [_line(setup, line_number="1", quantity="5")],
        }
    )
    return SalesOrderService(setup.session).preview_order(
        payload, firm_id=setup.firm.id, actor_id=uuid4()
    )


def _purchase_order() -> BaseModel:
    """Price a purchase order under a discount of 100.00 on the whole order."""
    setup = _shop()
    actor_id = uuid4()
    vendor = _vendor(setup.session, firm_id=setup.firm.id, actor_id=actor_id)
    payload = PurchaseOrderCreate.model_validate(
        {
            "vendor_id": str(vendor.id),
            "branch_id": str(setup.branch.id),
            "warehouse_id": str(setup.warehouse.id),
            "purchase_date": DAY.isoformat(),
            "header_discount_amount": "100",
            "lines": [
                {
                    "product_id": str(setup.product.id),
                    "ordered_quantity": "10",
                    "unit_price": "60",
                }
            ],
        }
    )
    return PurchaseService(setup.session).preview_order(
        payload, firm_id=setup.firm.id, actor_id=actor_id
    )


CASES: dict[str, Callable[[], BaseModel]] = {
    "quotation_preview": _quotation,
    "sales_order_preview": _sales_order,
    "purchase_order_preview": _purchase_order,
}


def _steady(answer: BaseModel) -> dict[str, Any]:
    """Return the answer with its ids and timestamps made the same every run."""
    names: dict[str, str] = {}

    def walk(value: object, key: str = "") -> object:
        if isinstance(value, dict):
            return {name: walk(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [walk(item, key) for item in value]
        if key in _STAMPS and value is not None:
            return "2026-08-04T00:00:00Z"
        if isinstance(value, str) and _UUID.match(value):
            return names.setdefault(value, f"id-{len(names) + 1}")
        return value

    steady = walk(answer.model_dump(mode="json"))
    assert isinstance(steady, dict)
    return steady


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_desktop_is_tested_with_what_the_server_sends(name: str) -> None:
    """Each kept answer is what the service answers today."""
    priced = json.dumps(_steady(CASES[name]()), indent=2, sort_keys=True) + "\n"
    kept = FIXTURES / f"{name}.json"
    if os.environ.get("AGENCY_UPDATE_PRICING_FIXTURES"):
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_text(priced, encoding="utf-8", newline="\n")
    assert kept.exists(), f"{kept} is missing; see this module's docstring."
    assert kept.read_text(encoding="utf-8") == priced, (
        f"{kept.name} is not what the service answers now. If the change is "
        "meant, write the files again (this module's docstring) and run the "
        "desktop tests that read them."
    )


@pytest.mark.parametrize("name", ["quotation_preview", "sales_order_preview"])
def test_a_sales_lines_amount_is_its_taxable_value_and_its_tax(name: str) -> None:
    """The rule the screens rely on: amount less tax is what was taxed.

    And it is not gross less the line's own discount: the bill discount's
    share comes off and the delivery charge's share goes on.
    """
    answer = _steady(CASES[name]())
    document = answer["quotation" if name.startswith("quotation") else "order"]
    line = document["lines"][0]
    net, tax = Decimal(line["net_amount"]), Decimal(line["tax_amount"])
    taxable = net - tax

    # 500.00 less 10% is 450.00; less 5% of that is 427.50; plus 40.00.
    assert taxable == Decimal("467.5000")
    assert tax == Decimal("84.1500")
    assert Decimal(document["tax_total"]) == tax
    assert Decimal(document["grand_total"]) == net
    own = Decimal(line["gross_amount"]) - Decimal(line["discount_amount"])
    assert own == Decimal("450.0000") != taxable


def test_a_purchase_lines_amount_is_its_taxable_value_and_its_tax() -> None:
    """An order discount comes off the line before it is taxed (D-UI-96)."""
    line = _steady(_purchase_order())["order"]["lines"][0]
    net, tax = Decimal(line["net_amount"]), Decimal(line["tax_amount"])

    # Ten at 60.00 is 600.00; the order's 100.00 comes off; 18% of 500.00.
    assert net - tax == Decimal("500.0000")
    assert tax == Decimal("90.0000")
    own = Decimal(line["gross_amount"]) - Decimal(line["discount_amount"])
    assert own == Decimal("600.0000")
