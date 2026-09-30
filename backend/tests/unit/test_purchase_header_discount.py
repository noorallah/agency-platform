"""A purchase order's whole-order discount reaches the lines and travels down.

D-BUY-19: ``header_discount_amount`` came off the order's grand total after
tax, so it lowered no taxable value and the input tax was overstated; and the
receipt and the bill never inherited it, so the stock was valued and the
supplier billed at the undiscounted price. It is now split across the order's
lines before tax (``bill_discount_amount``) and each receipt, bill and return
line inherits its share pro-rated by the quantity it covers.

The tax effect on the order itself is pinned in ``test_purchase_management``;
these follow the discount down the chain on a firm with no tax configured, so
every figure is the value alone.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.utils.pricing import inherited_share
from app.finance.services.control_accounts import ControlAccountPurpose
from app.goods_receipt.models import GoodsReceiptLine
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.purchase_invoice.models import PurchaseInvoiceLine
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from app.purchase_return.models import PurchaseReturnLine
from app.purchase_return.schemas import PurchaseReturnCreate
from app.purchase_return.services import PurchaseReturnService
from tests.unit.test_purchase_chain_synthesis import _Firm


@pytest.fixture
def firm() -> _Firm:
    """Build a firm on a fresh in-memory store, as the stage-switch tests do."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="HDISC")


def _order(firm: _Firm, *, lines: list[tuple[Product, str, str]]) -> PurchaseOrder:
    """Approve an order of ``(product, quantity, price)`` lines, 100 off it."""
    service = PurchaseService(firm.session)
    order = service.create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "vendor_id": firm.vendor.id,
                "purchase_date": "2026-08-02",
                "header_discount_amount": "100",
                "lines": [
                    {
                        "product_id": product.id,
                        "ordered_quantity": quantity,
                        "unit_price": price,
                    }
                    for product, quantity, price in lines
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.submit_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    return service.approve_order(
        order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )


def _order_lines(firm: _Firm, order: PurchaseOrder) -> list[PurchaseOrderLine]:
    """Read the order's lines in line-number order."""
    return list(
        firm.session.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == order.id)
            .order_by(PurchaseOrderLine.line_number)
        ).all()
    )


def _bill_of_order(
    firm: _Firm, order: PurchaseOrder, line: PurchaseOrderLine, quantity: str
) -> PurchaseInvoiceCreate:
    """Bill part of one order line, as a firm that types no receipts does."""
    return PurchaseInvoiceCreate.model_validate(
        {
            "invoice_date": "2026-08-10",
            "supplier_invoice_number": "S-44",
            "supplier_invoice_date": "2026-08-09",
            "lines": [
                {
                    "source_document_type": "PURCHASE_ORDER",
                    "source_document_id": order.id,
                    "source_document_line_id": line.id,
                    "line_number": 1,
                    "current_invoice_quantity": quantity,
                }
            ],
        }
    )


def test_the_share_is_pro_rated_and_never_exceeds_the_source() -> None:
    """Four of ten take four tenths; covering the whole takes all of it."""
    assert inherited_share(
        Decimal("100"), part=Decimal("4"), whole=Decimal("10")
    ) == Decimal("40.00")
    assert inherited_share(
        Decimal("100"), part=Decimal("12"), whole=Decimal("10")
    ) == Decimal("100.00")
    assert inherited_share(Decimal("0"), part=Decimal("4"), whole=Decimal("10")) == 0
    assert inherited_share(Decimal("100"), part=Decimal("4"), whole=Decimal("0")) == 0


def test_the_order_splits_its_discount_by_what_each_line_is_worth(
    firm: _Firm,
) -> None:
    """300 and 100 of lines share 100 off as 75 and 25, and the total holds."""
    second = Product(
        firm_id=firm.firm.id,
        code="SKU-TWO",
        name="Second",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        purchase_price=Decimal("10"),
    )
    firm.session.add(second)
    firm.session.commit()
    order = _order(firm, lines=[(firm.product, "3", "100"), (second, "10", "10")])
    lines = _order_lines(firm, order)
    assert [line.bill_discount_amount for line in lines] == [
        Decimal("75.0000"),
        Decimal("25.0000"),
    ]
    # Value before tax is net of the share, line by line.
    assert [line.net_amount - line.tax_amount for line in lines] == [
        Decimal("225.0000"),
        Decimal("75.0000"),
    ]
    assert order.subtotal == Decimal("400.0000")
    assert order.grand_total == Decimal("300.0000")


def test_a_bill_of_part_of_the_order_values_stock_and_payable_net(
    firm: _Firm,
) -> None:
    """Four of ten at 100, with 100 off the order: 40 off, 360 in stock and owed."""
    firm.stages(order=True, receipt=False)
    order = _order(firm, lines=[(firm.product, "10", "100")])
    (order_line,) = _order_lines(firm, order)
    assert order_line.bill_discount_amount == Decimal("100.0000")

    bills = firm.bills()
    bill = bills.create_invoice(
        _bill_of_order(firm, order, order_line, "4"),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)

    receipt_line = firm.session.scalar(
        select(GoodsReceiptLine).where(
            GoodsReceiptLine.purchase_order_line_id == order_line.id
        )
    )
    assert receipt_line is not None
    assert receipt_line.bill_discount_amount == Decimal("40.0000")
    bill_line = firm.session.scalar(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill.id
        )
    )
    assert bill_line is not None
    assert bill_line.bill_discount_amount == Decimal("40.0000")
    assert bill.grand_total == Decimal("360.0000")
    assert firm.stock() == Decimal("4")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == Decimal("360")
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-360")

    # Sending one back debits the supplier its share of the discount too:
    # one of the four received takes a quarter of the receipt line's 40.
    returned = PurchaseReturnService(firm.session).create_return(
        PurchaseReturnCreate.model_validate(
            {
                "warehouse_id": firm.warehouse.id,
                "return_date": "2026-08-12",
                "lines": [
                    {
                        "source_document_type": "GOODS_RECEIPT",
                        "source_document_id": receipt_line.goods_receipt_id,
                        "source_document_line_id": receipt_line.id,
                        "line_number": 1,
                        "current_return_quantity": "1",
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    return_line = firm.session.scalar(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == returned.id
        )
    )
    assert return_line is not None
    assert return_line.bill_discount_amount == Decimal("10.0000")
    assert returned.grand_total == Decimal("90.0000")
