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
from sqlalchemy import select

from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.purchase_invoice.models import PurchaseInvoiceLine
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from app.purchase_return.schemas import PurchaseReturnCreate
from app.purchase_return.services import PurchaseReturnService
from app.quotation.schemas import QuotationCreate
from app.quotation.services.quotation_service import QuotationService
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.schemas import SalesOrderCreate
from app.sales_order.services.sales_order_service import SalesOrderService
from app.sales_return.schemas import SalesReturnCreate
from app.sales_return.services import SalesReturnService
from tests.unit.test_purchase_chain_synthesis import _Firm as _BuyingFirm
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


def _counter_bill(setup: _Firm) -> SalesInvoiceCreate:
    """Describe a bill of products: discounts, a delivery charge, a charge."""
    return SalesInvoiceCreate.model_validate(
        {
            "customer_id": str(setup.customer.id),
            "invoice_date": DAY.isoformat(),
            "bill_discount_percent": "5",
            "freight_amount": "40",
            "lines": [
                _line(
                    setup,
                    line_number="1",
                    current_invoice_quantity="5",
                    charges_amount="20",
                )
            ],
        }
    )


def _sales_invoice() -> BaseModel:
    """Price a bill of products at a firm that types only the bill."""
    setup = _shop()
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    return SalesInvoiceService(setup.session).preview_invoice(
        _counter_bill(setup), firm_id=setup.firm.id, actor_id=uuid4()
    )


def _sales_return() -> BaseModel:
    """Price the return of two of the five that bill sold."""
    setup = _shop()
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    actor = uuid4()
    bills = SalesInvoiceService(setup.session)
    bill = bills.create_invoice(
        _counter_bill(setup), firm_id=setup.firm.id, actor_id=actor
    )
    if bill.status != "APPROVED":
        bills.approve_invoice(bill.id, firm_scope=setup.firm.id, actor_id=actor)
    setup.session.expire_all()
    billed = setup.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == bill.id)
    ).one()
    payload = SalesReturnCreate.model_validate(
        {
            "warehouse_id": str(setup.warehouse.id),
            "return_date": DAY.isoformat(),
            "lines": [
                {
                    "source_document_type": "SALES_INVOICE",
                    "source_document_id": str(bill.id),
                    "source_document_line_id": str(billed.id),
                    "line_number": 1,
                    "current_return_quantity": "2",
                }
            ],
        }
    )
    return SalesReturnService(setup.session).preview_return(
        payload, firm_id=setup.firm.id, actor_id=actor
    )


def _buyer() -> _BuyingFirm:
    """Build a firm that types only the supplier's bill, with GST at 18%."""
    firm = _BuyingFirm(_request_session())
    firm.product.tax_profile_group_code = "GST_STANDARD"
    firm.session.commit()
    _tax_group(
        firm.session,
        firm_id=firm.firm.id,
        percent="18",
        starts=date(2026, 4, 1),
        ends=None,
    )
    firm.stages(order=False, receipt=False)
    return firm


def _supplier_bill(firm: _BuyingFirm) -> PurchaseInvoiceCreate:
    """Describe a bill for ten at 100.00 less 10%, with a charge of 50.00."""
    return PurchaseInvoiceCreate.model_validate(
        {
            "vendor_id": str(firm.vendor.id),
            "invoice_date": DAY.isoformat(),
            "supplier_invoice_number": "S-1",
            "supplier_invoice_date": DAY.isoformat(),
            "lines": [
                {
                    "line_number": 1,
                    "product_id": str(firm.product.id),
                    "current_invoice_quantity": "10",
                    "unit_price": "100",
                    "discount_percent": "10",
                    "charges_amount": "50",
                }
            ],
        }
    )


def _purchase_invoice() -> BaseModel:
    """Price a supplier's bill of products."""
    firm = _buyer()
    return firm.bills().preview_invoice(
        _supplier_bill(firm), firm_id=firm.firm.id, actor_id=firm.actor_id
    )


def _purchase_return() -> BaseModel:
    """Price the return of four of the ten that bill bought."""
    firm = _buyer()
    bills = firm.bills()
    bill = bills.create_invoice(
        _supplier_bill(firm), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    if bill.status != "APPROVED":
        bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    firm.session.expire_all()
    billed = firm.session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill.id
        )
    ).one()
    payload = PurchaseReturnCreate.model_validate(
        {
            "return_date": DAY.isoformat(),
            "warehouse_id": str(firm.warehouse.id),
            "source_documents": [
                {
                    "source_document_type": "PURCHASE_INVOICE",
                    "source_document_id": str(bill.id),
                }
            ],
            "lines": [
                {
                    "source_document_type": "PURCHASE_INVOICE",
                    "source_document_id": str(bill.id),
                    "source_document_line_id": str(billed.id),
                    "line_number": 1,
                    "current_return_quantity": "4",
                    "warehouse_id": str(firm.warehouse.id),
                }
            ],
        }
    )
    return PurchaseReturnService(firm.session).preview_return(
        payload, firm_id=firm.firm.id, actor_id=firm.actor_id
    )


CASES: dict[str, Callable[[], BaseModel]] = {
    "quotation_preview": _quotation,
    "sales_order_preview": _sales_order,
    "purchase_order_preview": _purchase_order,
    "sales_invoice_preview": _sales_invoice,
    "sales_return_preview": _sales_return,
    "purchase_invoice_preview": _purchase_invoice,
    "purchase_return_preview": _purchase_return,
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
