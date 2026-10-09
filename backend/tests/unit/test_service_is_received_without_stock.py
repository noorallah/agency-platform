"""A service bought is received and billed, and never held as stock.

D-BUY-74: selling leaves the stock half of a service line out (backlog 87
#3) and inventory's own writes refuse a service (D-STK-71), but a goods
receipt of one put it into the warehouse at its cost and the valuation
carried it. The receipt still completes and the order still counts it
received, so it can be billed; there is no movement, no accrual, and the bill
debits the service to purchases instead of clearing goods received not
invoiced.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.services.control_accounts import ControlAccountPurpose
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.services.goods_receipt_service import GoodsReceiptService
from app.inventory.models import InventoryRecord, StockLedgerEntry
from app.landed_costs.services import LandedCostService, LandedCostWrite
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from tests.unit.test_purchase_chain_synthesis import (
    _bill_receipt,
    _Firm,
    _order_with_free,
    _receive,
    _send_back,
)

D = Decimal
P = ControlAccountPurpose


@pytest.fixture
def firm() -> _Firm:
    """Build a firm that also buys an installation service."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="SVC")
    service = Product(
        firm_id=built.firm.id,
        code="INSTALL",
        name="Installation",
        product_type="SERVICE",
        status="ACTIVE",
        purchase_price=D("100"),
    )
    built.session.add(service)
    built.session.commit()
    built.service = service  # type: ignore[attr-defined]
    return built


def _service(firm: _Firm) -> Product:
    """Return the firm's service."""
    product = firm.session.scalar(
        select(Product).where(
            Product.firm_id == firm.firm.id, Product.product_type == "SERVICE"
        )
    )
    assert product is not None
    return product


def _ordered(firm: _Firm) -> tuple[PurchaseOrder, PurchaseOrderLine]:
    """Approve an order for ten of the service at 100.00."""
    order, (line,) = _order_with_free(
        firm,
        {
            "product_id": _service(firm).id,
            "ordered_quantity": "10",
            "unit_price": "100",
        },
    )
    return order, line


def _held(firm: _Firm, product: Product) -> tuple[int, int]:
    """Count the stock rows and ledger entries a product has."""
    rows = firm.session.scalar(
        select(func.count())
        .select_from(InventoryRecord)
        .where(InventoryRecord.product_id == product.id)
    )
    entries = firm.session.scalar(
        select(func.count())
        .select_from(StockLedgerEntry)
        .where(StockLedgerEntry.product_id == product.id)
    )
    return int(rows or 0), int(entries or 0)


def test_a_received_service_moves_the_order_and_no_stock(firm: _Firm) -> None:
    """The receipt completes and the order counts it; the shelf does not."""
    order, line = _ordered(firm)

    received = _receive(firm, order, line, "4")

    receipt = firm.session.get(GoodsReceipt, received.goods_receipt_id)
    assert receipt is not None
    assert receipt.status == "COMPLETED"
    assert received.inventory_transaction_id is None
    assert _held(firm, _service(firm)) == (0, 0)
    assert firm.balance(P.INVENTORY) == D("0")
    assert firm.balance(P.GOODS_RECEIVED_NOT_INVOICED) == D("0")
    firm.session.refresh(order)
    assert received.accepted_quantity == D("4")
    assert order.status == "PARTIALLY_RECEIVED"


def test_the_bill_of_a_service_debits_purchases(firm: _Firm) -> None:
    """Nothing was accrued, so the bill is an expense, not a variance."""
    order, line = _ordered(firm)
    received = _receive(firm, order, line, "4")

    bill = _bill_receipt(firm, received, "4")

    assert bill.status == "APPROVED"
    assert firm.balance(P.PURCHASE_EXPENSE) == D("400")
    assert firm.balance(P.ACCOUNTS_PAYABLE) == D("-400")
    assert firm.balance(P.PURCHASE_PRICE_VARIANCE) == D("0")
    assert firm.balance(P.GOODS_RECEIVED_NOT_INVOICED) == D("0")
    assert firm.balance(P.INVENTORY) == D("0")

    firm.bills().cancel_invoice(
        bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id, reason="Wrong bill"
    )
    assert firm.balance(P.PURCHASE_EXPENSE) == D("0")
    assert firm.balance(P.ACCOUNTS_PAYABLE) == D("0")


def test_goods_beside_a_service_come_in_alone(firm: _Firm) -> None:
    """One receipt of both stocks and accrues the goods only."""
    order, (goods, work) = _order_with_free(
        firm,
        {"product_id": firm.product.id, "ordered_quantity": "5", "unit_price": "60"},
        {
            "product_id": _service(firm).id,
            "ordered_quantity": "1",
            "unit_price": "250",
        },
    )
    receipts = GoodsReceiptService(firm.session)
    receipt = receipts.create_receipt(
        receipts_payload(firm, order, [(goods, "5"), (work, "1")]),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    receipts.complete_receipt(
        receipt.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )

    assert firm.stock() == D("5")
    assert _held(firm, _service(firm)) == (0, 0)
    assert firm.balance(P.INVENTORY) == D("300")
    assert firm.balance(P.GOODS_RECEIVED_NOT_INVOICED) == D("-300")
    firm.session.refresh(order)
    assert order.status == "RECEIVED"

    # Cancelling takes back the goods and their accrual; the service had
    # neither to give back.
    receipts.cancel_receipt(
        receipt.id, firm_scope=firm.firm.id, actor_id=firm.actor_id, reason="Wrong"
    )
    assert firm.stock() == D("0")
    assert firm.balance(P.INVENTORY) == D("0")
    assert firm.balance(P.GOODS_RECEIVED_NOT_INVOICED) == D("0")
    assert _held(firm, _service(firm)) == (0, 0)


def receipts_payload(
    firm: _Firm, order: PurchaseOrder, lines: list[tuple[PurchaseOrderLine, str]]
) -> object:
    """Build a receipt of several order lines into the firm's warehouse."""
    from app.goods_receipt.schemas import GoodsReceiptCreate

    return GoodsReceiptCreate.model_validate(
        {
            "purchase_order_id": order.id,
            "receipt_date": "2026-08-05",
            "lines": [
                {
                    "purchase_order_line_id": line.id,
                    "line_number": number,
                    "current_receipt_quantity": quantity,
                    "warehouse_id": firm.warehouse.id,
                }
                for number, (line, quantity) in enumerate(lines, start=1)
            ],
        }
    )


def test_a_bill_that_raises_its_own_receipt_holds_no_service(firm: _Firm) -> None:
    """A firm typing only bills buys a service straight to purchases."""
    firm.stages(order=False, receipt=False)
    firm.product = _service(firm)
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill("3", "100"), firm_id=firm.firm.id, actor_id=firm.actor_id
    )

    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)

    _, receipt = firm.raised(bill)
    assert receipt.status == "COMPLETED"
    assert _held(firm, _service(firm)) == (0, 0)
    assert firm.balance(P.PURCHASE_EXPENSE) == D("300")
    assert firm.balance(P.ACCOUNTS_PAYABLE) == D("-300")
    assert firm.balance(P.PURCHASE_PRICE_VARIANCE) == D("0")
    assert firm.balance(P.INVENTORY) == D("0")


def test_a_service_is_not_sent_back_and_carries_no_landed_cost(firm: _Firm) -> None:
    """There is no stock for a return to take out or a cost to land on."""
    order, line = _ordered(firm)
    received = _receive(firm, order, line, "4")

    with pytest.raises(ValidationError, match="is a service"):
        _send_back(firm, "GOODS_RECEIPT", received.goods_receipt_id, received.id, "1")
    firm.session.rollback()

    with pytest.raises(ValidationError, match="brought in no stock"):
        LandedCostService(firm.session).post(
            LandedCostWrite.model_validate(
                {
                    "voucher_date": date(2026, 8, 20),
                    "basis": "VALUE",
                    "goods_receipt_ids": [received.goods_receipt_id],
                    "charges": [
                        {
                            "description": "Freight",
                            "amount": "50",
                            "vendor_id": firm.vendor.id,
                            "bill_reference": "TR-1",
                        }
                    ],
                }
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()
    assert (
        firm.session.scalars(
            select(GoodsReceiptLine.inventory_transaction_id).where(
                GoodsReceiptLine.id == received.id
            )
        ).one()
        is None
    )
