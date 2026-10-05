"""Imports and capital goods through order, receipt and bill (D-BUY-39, 40).

A firm on the whole chain -- it types the order, the receipt and the bill --
buys abroad and buys machines like any other firm.

**An import.** The order carries the currency and the rate; its lines are
priced as the supplier bills. The receipt values the stock in rupees at the
order's rate. The bill is in the order's currency: at the same rate it clears
the accrual to the paisa, at another rate only the rate difference goes to
price variance, and a bill in any other currency is refused by name.

**A machine.** The order line (or the receipt line) is marked capital goods,
so the receipt brings it in without a stock movement or an accrual, and the
bill capitalises it exactly as a bill typed alone does. A line already taken
into stock is still refused as capital goods at the bill.

Sessions are shaped like a request's (no autoflush), as in the chain tests.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.models import JournalEntry, JournalLine
from app.finance.services.control_accounts import ControlAccountPurpose
from app.fixed_assets.models import AssetClass, FixedAsset
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptCreate
from app.goods_receipt.services import GoodsReceiptService
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import (
    PurchaseOrderAmend,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
)
from app.purchase.services import PurchaseService
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from tests.unit.test_purchase_chain_synthesis import _Firm

pytestmark = pytest.mark.typed_document_numbers

D = Decimal
ORDERED = date(2026, 8, 2)
RECEIVED = date(2026, 8, 5)
BILLED = date(2026, 8, 10)


def _firm() -> _Firm:
    """Build a firm on the whole chain, on a request-shaped session."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return _Firm(sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)())


def _order(
    firm: _Firm,
    *,
    quantity: str = "10",
    price: str = "100",
    capital: bool | None = None,
    **header: object,
) -> PurchaseOrder:
    """Raise and approve an order for the firm's product."""
    line: dict[str, object] = {
        "product_id": firm.product.id,
        "ordered_quantity": quantity,
        "unit_price": price,
    }
    if capital is not None:
        line["is_capital_goods"] = capital
    service = PurchaseService(firm.session)
    order = service.create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "vendor_id": firm.vendor.id,
                "purchase_date": ORDERED.isoformat(),
                "lines": [line],
                **header,
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.submit_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    return service.approve_order(
        order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )


def _receive(
    firm: _Firm, order: PurchaseOrder, **line: object
) -> tuple[GoodsReceipt, GoodsReceiptLine]:
    """Receive the whole order as a person would, and complete the receipt."""
    ordered = firm.session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert ordered is not None
    receipts = GoodsReceiptService(firm.session)
    receipt = receipts.create_receipt(
        GoodsReceiptCreate.model_validate(
            {
                "purchase_order_id": order.id,
                "receipt_date": RECEIVED.isoformat(),
                "lines": [
                    {
                        "purchase_order_line_id": ordered.id,
                        "line_number": 1,
                        "current_receipt_quantity": str(ordered.ordered_quantity),
                        **line,
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    receipts.complete_receipt(
        receipt.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    received = firm.session.scalar(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    )
    assert received is not None
    return receipt, received


def _bill_data(
    receipt: GoodsReceipt,
    received: GoodsReceiptLine,
    *,
    price: str = "100",
    line: dict[str, object] | None = None,
    **header: object,
) -> PurchaseInvoiceCreate:
    """Build a bill of the whole received line."""
    return PurchaseInvoiceCreate.model_validate(
        {
            "invoice_date": BILLED.isoformat(),
            "supplier_invoice_number": "S-1",
            "supplier_invoice_date": BILLED.isoformat(),
            "lines": [
                {
                    "source_document_type": "GOODS_RECEIPT",
                    "source_document_id": receipt.id,
                    "source_document_line_id": received.id,
                    "line_number": 1,
                    "current_invoice_quantity": str(received.accepted_quantity),
                    "unit_price": price,
                    **(line or {}),
                }
            ],
            **header,
        }
    )


def _billed(
    firm: _Firm, data: PurchaseInvoiceCreate, *, approve: bool = True
) -> PurchaseInvoice:
    """Save a bill and, unless told not to, approve it."""
    bills = firm.bills()
    bill = bills.create_invoice(data, firm_id=firm.firm.id, actor_id=firm.actor_id)
    if not approve:
        return bill
    return bills.approve_invoice(
        bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )


def _balanced(firm: _Firm) -> bool:
    """Say whether every journal the firm posted balances."""
    for entry_id in firm.session.scalars(
        select(JournalEntry.id).where(JournalEntry.firm_id == firm.firm.id)
    ).all():
        lines = firm.session.execute(
            select(JournalLine.debit_amount, JournalLine.credit_amount).where(
                JournalLine.journal_entry_id == entry_id
            )
        ).all()
        if sum(D(debit) for debit, _ in lines) != sum(D(credit) for _, credit in lines):
            return False
    return True


def _plant(firm: _Firm) -> AssetClass:
    """Return the firm's seeded Plant and Machinery class."""
    row = firm.session.scalar(
        select(AssetClass).where(
            AssetClass.firm_id == firm.firm.id, AssetClass.code == "PLANT"
        )
    )
    assert row is not None
    return row


def _assets(firm: _Firm) -> list[FixedAsset]:
    """Return the firm's live fixed assets."""
    return list(
        firm.session.scalars(
            select(FixedAsset).where(
                FixedAsset.firm_id == firm.firm.id, FixedAsset.is_deleted.is_(False)
            )
        ).all()
    )


# -- D-BUY-39: an import through the chain -----------------------------------


def test_a_usd_order_is_received_in_rupees_at_the_orders_rate() -> None:
    """Ten at 100 USD ordered at 83 lands 83,000 of stock and of accrual."""
    firm = _firm()
    order = _order(firm, currency_code="usd", exchange_rate="83")

    _receive(firm, order)

    assert (order.currency_code, order.exchange_rate) == ("USD", D("83"))
    assert firm.stock() == D("10")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("83000")
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == D(
        "-83000"
    )


def test_a_bill_at_the_orders_rate_clears_the_accrual_with_no_variance() -> None:
    """Order, receipt and bill in USD at 83: nothing is left over."""
    firm = _firm()
    receipt, received = _receive(
        firm, _order(firm, currency_code="USD", exchange_rate="83")
    )

    bill = _billed(
        firm, _bill_data(receipt, received, currency_code="USD", exchange_rate="83")
    )

    assert bill.base_grand_total == D("83000.00")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == D("-83000")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("83000")
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == 0
    assert _balanced(firm)


def test_a_bill_at_another_rate_posts_only_the_rate_difference() -> None:
    """Received at 83, billed at 84.50: 1,500 of variance, not 84,500."""
    firm = _firm()
    receipt, received = _receive(
        firm, _order(firm, currency_code="USD", exchange_rate="83")
    )

    _billed(
        firm,
        _bill_data(receipt, received, currency_code="USD", exchange_rate="84.5"),
    )

    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == D("-84500")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("83000")
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == D("1500")
    assert _balanced(firm)


def test_a_bill_naming_no_currency_takes_its_orders_currency_and_rate() -> None:
    """Silence on the bill is the order's currency, not rupees."""
    firm = _firm()
    receipt, received = _receive(
        firm, _order(firm, currency_code="USD", exchange_rate="83")
    )

    bill = _billed(firm, _bill_data(receipt, received))

    assert (bill.currency_code, bill.exchange_rate) == ("USD", D("83"))
    assert bill.base_grand_total == D("83000.00")
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == 0


def test_a_rupee_bill_against_a_usd_order_is_refused_by_name() -> None:
    """1,000 rupees against 83,000 of stock would be 82,000 of variance."""
    firm = _firm()
    order = _order(firm, currency_code="USD", exchange_rate="83")
    receipt, received = _receive(firm, order)

    with pytest.raises(ValidationError, match=f"{order.po_number} is in USD"):
        _billed(firm, _bill_data(receipt, received, currency_code="INR"), approve=False)


def test_a_foreign_bill_against_a_rupee_order_is_refused_by_name() -> None:
    """The defect as found: a USD bill off a receipt valued in rupees."""
    firm = _firm()
    order = _order(firm)
    receipt, received = _receive(firm, order)

    with pytest.raises(ValidationError, match=f"{order.po_number} is in rupees"):
        _billed(
            firm,
            _bill_data(receipt, received, currency_code="USD", exchange_rate="83"),
            approve=False,
        )
    firm.session.rollback()
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == 0


def test_an_order_in_another_currency_needs_its_rate() -> None:
    """Refused where it is typed, not at the dock when the goods arrive."""
    firm = _firm()
    # In an order's words, not a bill's.
    with pytest.raises(
        ValidationError, match="A purchase order in USD needs its exchange rate"
    ):
        _order(firm, currency_code="USD")


def test_a_rupee_order_is_received_and_billed_exactly_as_before() -> None:
    """No currency anywhere: 1,000 of stock, 1,000 owed, nothing else."""
    firm = _firm()
    order = _order(firm)
    receipt, received = _receive(firm, order)

    bill = _billed(firm, _bill_data(receipt, received))

    assert (order.currency_code, order.exchange_rate) == (None, None)
    assert (bill.currency_code, bill.base_grand_total) == (None, None)
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("1000")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == D("-1000")
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == 0


def test_a_rupee_order_outranks_the_suppliers_own_currency() -> None:
    """A supplier kept in USD, ordered from in rupees, is billed in rupees."""
    firm = _firm()
    firm.vendor.currency_code = "USD"
    firm.session.commit()
    receipt, received = _receive(firm, _order(firm))

    bill = _billed(firm, _bill_data(receipt, received))

    assert bill.currency_code is None
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == D("-1000")
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == 0


def _order_edit(firm: _Firm, **fields: object) -> dict[str, object]:
    """Return an edit of the firm's one-line order with the fields given."""
    return {
        "branch_id": firm.branch.id,
        "warehouse_id": firm.warehouse.id,
        "vendor_id": firm.vendor.id,
        "purchase_date": ORDERED.isoformat(),
        "lines": [
            {
                "product_id": firm.product.id,
                "ordered_quantity": "10",
                "unit_price": "100",
            }
        ],
        **fields,
    }


def test_an_edit_that_names_no_currency_keeps_the_orders() -> None:
    """Absent means leave alone; an explicit null makes it a rupee order."""
    firm = _firm()
    service = PurchaseService(firm.session)
    order = service.create_order(
        PurchaseOrderCreate.model_validate(
            _order_edit(firm, currency_code="USD", exchange_rate="83")
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )

    service.update_order(
        order.id,
        PurchaseOrderUpdate.model_validate(_order_edit(firm, remarks="by sea")),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert (order.currency_code, order.exchange_rate) == ("USD", D("83"))

    service.update_order(
        order.id,
        PurchaseOrderUpdate.model_validate(
            _order_edit(firm, currency_code=None, exchange_rate=None)
        ),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert (order.currency_code, order.exchange_rate) == (None, None)


def test_the_rate_cannot_change_once_goods_were_received_at_it() -> None:
    """The stock is valued; a new rate belongs on the supplier's bill."""
    firm = _firm()
    order = _order(firm, quantity="10", currency_code="USD", exchange_rate="83")
    receipt, _ = _receive(firm, order)

    with pytest.raises(ValidationError, match=f"{receipt.grn_number} has already"):
        PurchaseService(firm.session).amend_order(
            order.id,
            PurchaseOrderAmend.model_validate(
                _order_edit(
                    firm,
                    currency_code="USD",
                    exchange_rate="85",
                    reason="rate moved",
                )
            ),
            firm_scope=firm.firm.id,
            actor_id=firm.actor_id,
            may_approve=True,
        )


# -- D-BUY-40: capital goods through the chain -------------------------------


def _capital_line(firm: _Firm) -> dict[str, object]:
    """Return the bill-line fields that capitalise a line as plant."""
    return {"is_capital_goods": True, "asset_class_id": str(_plant(firm).id)}


def test_a_machine_ordered_as_capital_goods_is_received_without_stock() -> None:
    """The receipt completes; nothing enters stock and nothing is accrued."""
    firm = _firm()
    order = _order(firm, quantity="1", price="100000", capital=True)

    receipt, received = _receive(firm, order)

    assert receipt.status == "COMPLETED"
    assert received.is_capital_goods is True
    assert received.inventory_transaction_id is None
    firm.session.refresh(order)
    assert order.status == "RECEIVED"
    assert firm.stock() == D("0")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == 0
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0


def test_the_bill_capitalises_what_the_receipt_brought_in() -> None:
    """Order, receipt, bill: FA-00001 at cost, no stock, the books balanced."""
    firm = _firm()
    receipt, received = _receive(
        firm, _order(firm, quantity="1", price="100000", capital=True)
    )

    bill = _billed(
        firm,
        _bill_data(receipt, received, price="100000", line=_capital_line(firm)),
    )

    (asset,) = _assets(firm)
    assert asset.purchase_invoice_id == bill.id
    assert asset.cost == D("100000.00")
    assert firm.stock() == D("0")
    assert firm.balance(ControlAccountPurpose.FIXED_ASSET_COST) == D("100000")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == D("-100000")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == 0
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == 0
    assert _balanced(firm)


def test_a_bill_line_takes_capital_goods_from_its_receipt_line() -> None:
    """Billed without the tick, it is still capital goods: it needs a class."""
    firm = _firm()
    receipt, received = _receive(
        firm, _order(firm, quantity="1", price="100000", capital=True)
    )

    with pytest.raises(ValidationError, match="choose its asset class"):
        _billed(firm, _bill_data(receipt, received, price="100000"), approve=False)
    firm.session.rollback()

    with pytest.raises(ValidationError, match="was received as capital goods"):
        _billed(
            firm,
            _bill_data(
                receipt, received, price="100000", line={"is_capital_goods": False}
            ),
            approve=False,
        )


def test_the_receiver_may_mark_a_line_capital_goods_on_the_receipt() -> None:
    """An order typed without the mark is put right at the dock."""
    firm = _firm()
    order = _order(firm, quantity="1", price="100000")

    _, received = _receive(firm, order, is_capital_goods=True)

    assert received.is_capital_goods is True
    assert firm.stock() == D("0")
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0


def test_a_line_already_in_stock_is_still_refused_as_capital_goods() -> None:
    """Taking it out again is a stock issue; the message says what to do."""
    firm = _firm()
    receipt, received = _receive(firm, _order(firm, quantity="1", price="100000"))
    assert firm.stock() == D("1")
    bill = _billed(
        firm,
        _bill_data(receipt, received, price="100000", line=_capital_line(firm)),
        approve=False,
    )

    with pytest.raises(ValidationError, match="mark the line capital goods on"):
        firm.bills().approve_invoice(
            bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
        )


def test_cancelling_the_capital_receipt_moves_no_stock() -> None:
    """Nothing came in, so nothing goes out and nothing is reversed."""
    firm = _firm()
    order = _order(firm, quantity="1", price="100000", capital=True)
    receipt, _ = _receive(firm, order)

    GoodsReceiptService(firm.session).cancel_receipt(
        receipt.id, firm_scope=firm.firm.id, actor_id=firm.actor_id, reason="wrong"
    )

    firm.session.refresh(receipt)
    assert receipt.status == "CANCELLED"
    assert firm.stock() == D("0")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == 0
    assert _balanced(firm)


def test_a_receipt_says_what_currency_its_order_is_in() -> None:
    """The bill editor reads it off the receipt it already has (D-BUY-42)."""
    firm = _firm()
    receipts = GoodsReceiptService(firm.session)

    usd, _ = _receive(firm, _order(firm, currency_code="USD", exchange_rate="83"))
    rupees, _ = _receive(firm, _order(firm))

    in_usd, in_rupees = receipts.receipt_responses([usd, rupees])
    assert (in_usd.currency_code, in_usd.exchange_rate) == ("USD", D("83"))
    assert (in_rupees.currency_code, in_rupees.exchange_rate) == (None, None)
