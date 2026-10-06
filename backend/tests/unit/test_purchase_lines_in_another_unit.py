"""A line bought by the box is counted, costed and returned as a box.

The buying twin of ``test_lines_in_another_unit.py``. A product kept in
pieces, 12 to a box, bought by the box at 720.00 -- 60.00 a piece. Every case
drives the real services on a request-shaped session (autoflush off): order,
approval, goods receipt, supplier bill, purchase return.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.services.control_accounts import ControlAccountPurpose
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptCreate
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.models import (
    InventoryTransaction,
    ProductValuation,
    StockLedgerEntry,
)
from app.pricing.models import PriceList, PriceListItem
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
)
from app.purchase.services import PurchaseService
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_invoice.services.gst_purchase_register import (
    GstPurchaseRegisterService,
)
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine
from app.purchase_return.schemas import PurchaseReturnCreate
from app.purchase_return.services.purchase_return_service import (
    PurchaseReturnService,
)
from app.uom.models import ConversionRule, Uom
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal
DAY = date(2026, 8, 4)
NO_RULE = (
    "SKU-BOX: no active conversion rule converts CARTON to PIECE. Add one "
    "under Units -> Conversion Rules, or enter the quantity in PIECE."
)


def _request_session() -> Session:
    """Open a session as a request does: one that does not flush on a read."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)()


class _Buyer:
    """A firm buying a product kept in pieces, by the box of 12."""

    def __init__(self, *, default_box: bool = True) -> None:
        """Build the firm; ``default_box`` makes BOX the product's buying unit."""
        self.session = _request_session()
        self.firm = _Firm(self.session, "BOX")
        piece = Uom(code="PIECE", name="Piece", dimension="COUNT", status="ACTIVE")
        box = Uom(
            code="BOX",
            name="Box",
            dimension="COUNT",
            status="ACTIVE",
            is_decimal_allowed=False,
        )
        carton = Uom(code="CARTON", name="Carton", dimension="COUNT", status="ACTIVE")
        self.session.add_all([piece, box, carton])
        self.session.flush()
        self.piece, self.box, self.carton = piece.id, box.id, carton.id
        product = self.firm.product
        product.base_uom_id = piece.id
        product.inventory_uom_id = piece.id
        product.purchase_uom_id = box.id if default_box else None
        product.purchase_price = D("60")
        self.session.add(
            ConversionRule(
                firm_id=self.firm_id,
                product_id=product.id,
                from_uom_id=box.id,
                to_uom_id=piece.id,
                conversion_factor=D("12"),
                rounding_mode="HALF_UP",
                precision_scale=4,
                effective_from=date(2026, 4, 1),
                version_number=1,
            )
        )
        self.session.commit()

    @property
    def firm_id(self) -> UUID:
        """Return the firm."""
        return self.firm.firm.id

    @property
    def actor(self) -> UUID:
        """Return the user doing everything."""
        return self.firm.actor_id

    def order_payload(self, **line: object) -> dict[str, object]:
        """Describe an order of 2 at 720.00, with what the line names."""
        return {
            "branch_id": self.firm.branch.id,
            "warehouse_id": self.firm.warehouse.id,
            "vendor_id": self.firm.vendor.id,
            "purchase_date": DAY,
            "lines": [
                {
                    "product_id": self.firm.product.id,
                    "ordered_quantity": "2",
                    "unit_price": "720",
                    "warehouse_id": self.firm.warehouse.id,
                }
                | line
            ],
        }

    def order(self, *, approve: bool = True, **line: object) -> PurchaseOrder:
        """Raise an order of 2 at 720.00, with what the line names."""
        service = PurchaseService(self.session)
        order = service.create_order(
            PurchaseOrderCreate.model_validate(self.order_payload(**line)),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        if approve:
            service.submit_order(order.id, firm_scope=self.firm_id, actor_id=self.actor)
            service.approve_order(
                order.id, firm_scope=self.firm_id, actor_id=self.actor
            )
        return order

    def order_line(self, order: PurchaseOrder) -> PurchaseOrderLine:
        """Return the order's one line, as stored."""
        self.session.expire_all()
        return self.session.scalars(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == order.id
            )
        ).one()

    def receive(
        self, order: PurchaseOrder, quantity: str = "2", **line: object
    ) -> GoodsReceipt:
        """Receive the order's line on a completed goods receipt."""
        service = GoodsReceiptService(self.session)
        receipt = service.create_receipt(
            GoodsReceiptCreate.model_validate(
                {
                    "purchase_order_id": order.id,
                    "receipt_date": DAY,
                    "lines": [
                        {
                            "purchase_order_line_id": self.order_line(order).id,
                            "line_number": 1,
                            "current_receipt_quantity": quantity,
                            "warehouse_id": self.firm.warehouse.id,
                        }
                        | line
                    ],
                }
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        service.complete_receipt(
            receipt.id, firm_scope=self.firm_id, actor_id=self.actor
        )
        return receipt

    def receipt_line(self, receipt: GoodsReceipt) -> GoodsReceiptLine:
        """Return the receipt's one line, as stored."""
        self.session.expire_all()
        return self.session.scalars(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt.id
            )
        ).one()

    def bill(
        self, receipt: GoodsReceipt, quantity: str = "2", **line: object
    ) -> PurchaseInvoice:
        """Bill the receipt's line and approve the bill."""
        service = PurchaseInvoiceService(self.session)
        bill = service.create_invoice(
            PurchaseInvoiceCreate.model_validate(
                {
                    "supplier_invoice_number": f"S-{receipt.grn_number}-{quantity}",
                    "supplier_invoice_date": DAY,
                    "invoice_date": DAY,
                    "source_documents": [
                        {
                            "source_document_type": "GOODS_RECEIPT",
                            "source_document_id": receipt.id,
                        }
                    ],
                    "lines": [
                        {
                            "source_document_type": "GOODS_RECEIPT",
                            "source_document_id": receipt.id,
                            "source_document_line_id": self.receipt_line(receipt).id,
                            "line_number": 1,
                            "current_invoice_quantity": quantity,
                        }
                        | line
                    ],
                }
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        service.approve_invoice(bill.id, firm_scope=self.firm_id, actor_id=self.actor)
        return bill

    def bill_line(self, bill: PurchaseInvoice) -> PurchaseInvoiceLine:
        """Return the bill's one line, as stored."""
        self.session.expire_all()
        return self.session.scalars(
            select(PurchaseInvoiceLine).where(
                PurchaseInvoiceLine.purchase_invoice_id == bill.id
            )
        ).one()

    def send_back(
        self,
        source_type: str,
        source_id: UUID,
        source_line_id: UUID,
        quantity: str = "1",
        **line: object,
    ) -> PurchaseReturn:
        """Return some of a receipt or bill line, through to completion."""
        service = PurchaseReturnService(self.session)
        sent = service.create_return(
            PurchaseReturnCreate.model_validate(
                {
                    "return_date": DAY,
                    "warehouse_id": self.firm.warehouse.id,
                    "source_documents": [
                        {
                            "source_document_type": source_type,
                            "source_document_id": source_id,
                        }
                    ],
                    "lines": [
                        {
                            "source_document_type": source_type,
                            "source_document_id": source_id,
                            "source_document_line_id": source_line_id,
                            "line_number": 1,
                            "current_return_quantity": quantity,
                            "warehouse_id": self.firm.warehouse.id,
                        }
                        | line
                    ],
                }
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        service.approve_return(sent.id, firm_scope=self.firm_id, actor_id=self.actor)
        service.complete_return(sent.id, firm_scope=self.firm_id, actor_id=self.actor)
        return sent

    def return_line(self, sent: PurchaseReturn) -> PurchaseReturnLine:
        """Return the purchase return's one line, as stored."""
        self.session.expire_all()
        return self.session.scalars(
            select(PurchaseReturnLine).where(
                PurchaseReturnLine.purchase_return_id == sent.id
            )
        ).one()

    def stock(self) -> Decimal:
        """Return the pieces the warehouse holds."""
        self.session.expire_all()
        return D(str(self.firm.stock()))

    def valuation(self) -> tuple[Decimal, Decimal, Decimal]:
        """Return the pieces valued, their moving average and their value."""
        self.session.expire_all()
        row = self.session.scalars(
            select(ProductValuation).where(
                ProductValuation.product_id == self.firm.product.id
            )
        ).one()
        return (
            D(str(row.quantity_on_hand)),
            D(str(row.average_cost)),
            D(str(row.total_value)),
        )

    def movement(self, movement_id: UUID | None) -> tuple[Decimal, Decimal, Decimal]:
        """Return a movement's pieces, their unit cost and their value."""
        row = self.session.get(InventoryTransaction, movement_id)
        assert row is not None
        entry = self.session.scalars(
            select(StockLedgerEntry).where(
                StockLedgerEntry.transaction_id == movement_id
            )
        ).one()
        return (
            D(str(row.quantity)),
            D(str(entry.unit_cost)),
            D(str(entry.total_cost)),
        )

    def books(self) -> tuple[Decimal, Decimal, Decimal]:
        """Return the inventory, GRNI and payables balances (debit positive)."""
        return (
            self.firm.balance(ControlAccountPurpose.INVENTORY),
            self.firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED),
            self.firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE),
        )

    def named(self, case: str) -> dict[str, object]:
        """Return the units a line names for case (a), (b) or (c)."""
        return {
            "a": {"purchase_uom_id": self.box},
            "b": {},
            "c": {"purchase_uom_id": self.box, "inventory_uom_id": self.piece},
        }[case]


CASES = pytest.mark.parametrize("case", ["a", "b", "c"])


@CASES
def test_an_order_line_by_the_box_counts_24_however_it_names_its_units(
    case: str,
) -> None:
    """BOX alone, nothing at all, or both units: 2 BOX is 24 pieces."""
    buyer = _Buyer()

    line = buyer.order_line(buyer.order(approve=False, **buyer.named(case)))

    assert (line.purchase_uom_id, line.inventory_uom_id) == (buyer.box, buyer.piece)
    assert (line.conversion_factor, line.conversion_version) == (D("12"), 1)
    assert (line.ordered_quantity, line.base_quantity) == (D("2.0000"), D("24.0000"))
    assert (line.unit_price, line.gross_amount) == (D("720.0000"), D("1440.0000"))


@CASES
def test_a_blank_price_on_a_box_line_is_the_price_of_a_box(case: str) -> None:
    """60.00 a piece is 720.00 a box, whichever way the box was named."""
    buyer = _Buyer()

    line = buyer.order_line(
        buyer.order(approve=False, unit_price=None, **buyer.named(case))
    )

    assert (line.unit_price, line.gross_amount) == (D("720.0000"), D("1440.0000"))


@CASES
def test_a_box_received_lands_as_twelve_pieces_at_a_twelfth_of_its_cost(
    case: str,
) -> None:
    """2 BOX at 720.00 is 24 pieces at 60.00: 1,440.00 of stock and of GRNI."""
    buyer = _Buyer()

    receipt = buyer.receive(buyer.order(**buyer.named(case)))

    line = buyer.receipt_line(receipt)
    assert (line.purchase_uom_id, line.inventory_uom_id) == (buyer.box, buyer.piece)
    assert (line.conversion_factor, line.accepted_quantity) == (D("12"), D("2.0000"))
    assert buyer.movement(line.inventory_transaction_id) == (
        D("24.0000"),
        D("60.000000"),
        D("1440.0000"),
    )
    assert buyer.stock() == D("24.0000")
    assert buyer.valuation() == (D("24.0000"), D("60.000000"), D("1440.0000"))
    # Inventory debited and goods received not invoiced credited what was paid.
    assert buyer.books() == (D("1440.00"), D("-1440.00"), D("0"))


@CASES
def test_the_bill_of_a_box_receipt_clears_exactly_what_the_receipt_accrued(
    case: str,
) -> None:
    """The bill is 2 BOX at 720.00; GRNI goes to nothing, the payable to 1,440."""
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named(case)))

    bill = buyer.bill(receipt)

    line = buyer.bill_line(bill)
    assert (line.current_invoice_quantity, line.invoice_uom_id) == (
        D("2.0000"),
        buyer.box,
    )
    assert (line.unit_price, bill.grand_total) == (D("720.0000"), D("1440.0000"))
    assert buyer.books() == (D("1440.00"), D("0"), D("-1440.00"))
    assert buyer.valuation() == (D("24.0000"), D("60.000000"), D("1440.0000"))


@pytest.mark.parametrize("source", ["PURCHASE_INVOICE", "GOODS_RECEIPT"])
@CASES
def test_one_box_sent_back_takes_twelve_pieces_off_the_shelf(
    case: str, source: str
) -> None:
    """A return of 1 naming no unit is 1 BOX: 12 pieces leave, worth 720.00."""
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named(case)))
    if source == "PURCHASE_INVOICE":
        bill = buyer.bill(receipt)
        sent = buyer.send_back(source, bill.id, buyer.bill_line(bill).id)
    else:
        sent = buyer.send_back(source, receipt.id, buyer.receipt_line(receipt).id)

    line = buyer.return_line(sent)
    assert (line.current_return_quantity, line.purchase_uom_id) == (
        D("1.0000"),
        buyer.box,
    )
    assert line.gross_amount == D("720.0000")
    assert buyer.movement(line.inventory_transaction_id) == (
        D("12.0000"),
        D("60.000000"),
        D("720.0000"),
    )
    assert buyer.stock() == D("12.0000")
    assert buyer.valuation() == (D("12.0000"), D("60.000000"), D("720.0000"))
    inventory, grni, payable = buyer.books()
    assert inventory == D("720.00")
    # Off the bill the supplier owes 720.00 back; off an unbilled receipt
    # the accrual falls instead and nothing is owed either way.
    assert (grni, payable) == (
        (D("0"), D("-720.00"))
        if source == "PURCHASE_INVOICE"
        else (D("-720.00"), D("0"))
    )


def test_twelve_pieces_sent_back_off_a_box_line_are_one_box() -> None:
    """Typed as 12 PIECE, the return is stored as 1 BOX and 12 pieces leave."""
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named("c")))

    sent = buyer.send_back(
        "GOODS_RECEIPT",
        receipt.id,
        buyer.receipt_line(receipt).id,
        quantity="12",
        return_uom_id=buyer.piece,
    )

    line = buyer.return_line(sent)
    assert (line.current_return_quantity, line.gross_amount) == (
        D("1.0000"),
        D("720.0000"),
    )
    assert buyer.movement(line.inventory_transaction_id)[0] == D("12.0000")
    assert buyer.stock() == D("12.0000")
    # 36 pieces is three boxes, and two came in.
    with pytest.raises(ValidationError, match="can still send back 1 BOX bought"):
        buyer.send_back(
            "GOODS_RECEIPT",
            receipt.id,
            buyer.receipt_line(receipt).id,
            quantity="36",
            return_uom_id=buyer.piece,
        )


@pytest.mark.parametrize("default", [False, True])
@pytest.mark.parametrize("price", [None, "700"])
def test_a_buying_unit_no_rule_converts_is_refused_by_name(
    default: bool, price: str | None
) -> None:
    """A carton, named or the product's default, is never counted at 1."""
    buyer = _Buyer()
    named: dict[str, object] = {"unit_price": price}
    if default:
        buyer.firm.product.purchase_uom_id = buyer.carton
        buyer.session.commit()
    else:
        named["purchase_uom_id"] = buyer.carton

    with pytest.raises(ValidationError) as refused:
        buyer.order(approve=False, **named)

    assert str(refused.value.message) == NO_RULE


def test_a_line_in_the_stock_unit_is_bought_as_before() -> None:
    """24 PIECE named, and 24 of a product with no buying unit, convert nothing."""
    buyer = _Buyer(default_box=False)

    named = buyer.order_line(
        buyer.order(
            approve=False,
            ordered_quantity="24",
            unit_price="60",
            purchase_uom_id=buyer.piece,
        )
    )
    bare_order = buyer.order(ordered_quantity="24", unit_price="60")
    bare = buyer.order_line(bare_order)

    for line in (named, bare):
        assert (line.conversion_factor, line.base_quantity) == (D("1"), D("24.0000"))
        assert line.gross_amount == D("1440.0000")
    assert (bare.purchase_uom_id, bare.inventory_uom_id) == (None, buyer.piece)
    receipt = buyer.receive(bare_order, "24")
    assert buyer.movement(buyer.receipt_line(receipt).inventory_transaction_id) == (
        D("24.0000"),
        D("60.000000"),
        D("1440.0000"),
    )


def test_a_receipt_line_in_another_unit_than_its_order_is_refused() -> None:
    """24 PIECE ordered cannot be received as 2 BOX: the tallies are the order's."""
    buyer = _Buyer(default_box=False)
    order = buyer.order(
        ordered_quantity="24", unit_price="60", purchase_uom_id=buyer.piece
    )

    with pytest.raises(ValidationError) as refused:
        buyer.receive(order, purchase_uom_id=buyer.box)

    assert str(refused.value.message) == (
        f"Line 1 is received in BOX where {order.po_number} orders it in PIECE. "
        "Receive it in the order's unit."
    )
    assert buyer.stock() == D("0")


def test_an_order_line_stored_before_the_fix_still_receives_24_at_60() -> None:
    """A row left at a factor of 1 is not rewritten; its receipt converts."""
    buyer = _Buyer()
    order = buyer.order(purchase_uom_id=buyer.box)
    stored = buyer.order_line(order)
    # As a line naming BOX alone was stored before: the product's units
    # beside a factor of 1 and a base quantity of 2.
    stored.conversion_factor = D("1")
    stored.conversion_version = None
    stored.base_quantity = D("2")
    buyer.session.commit()

    receipt = buyer.receive(order)

    assert buyer.movement(buyer.receipt_line(receipt).inventory_transaction_id) == (
        D("24.0000"),
        D("60.000000"),
        D("1440.0000"),
    )
    assert buyer.order_line(order).base_quantity == D("2.0000")


def test_saving_an_old_order_line_again_restates_it_in_pieces() -> None:
    """The next save of a draft left at a factor of 1 counts its 24."""
    buyer = _Buyer()
    order = buyer.order(approve=False, purchase_uom_id=buyer.box)
    stored = buyer.order_line(order)
    stored.conversion_factor = D("1")
    stored.conversion_version = None
    stored.base_quantity = D("2")
    buyer.session.commit()

    PurchaseService(buyer.session).update_order(
        order.id,
        PurchaseOrderUpdate.model_validate(
            buyer.order_payload(purchase_uom_id=buyer.box)
        ),
        firm_scope=buyer.firm_id,
        actor_id=buyer.actor,
    )

    line = buyer.order_line(order)
    assert (line.conversion_factor, line.base_quantity) == (D("12"), D("24.0000"))


def _direct_bill(buyer: _Buyer, **line: object) -> PurchaseInvoice:
    """Type a bill of 2 of the product with no order, and approve it."""
    service = PurchaseInvoiceService(buyer.session)
    bill = service.create_invoice(
        PurchaseInvoiceCreate.model_validate(
            {
                "vendor_id": buyer.firm.vendor.id,
                "invoice_date": DAY,
                "supplier_invoice_number": "S-DIRECT",
                "supplier_invoice_date": DAY,
                "lines": [
                    {
                        "line_number": 1,
                        "product_id": buyer.firm.product.id,
                        "current_invoice_quantity": "2",
                    }
                    | line
                ],
            }
        ),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )
    service.approve_invoice(bill.id, firm_scope=buyer.firm_id, actor_id=buyer.actor)
    return bill


@pytest.mark.parametrize("named", [False, True])
def test_a_bill_of_products_by_the_box_brings_in_24_pieces_at_60(
    named: bool,
) -> None:
    """Stages off, no price: 2 is 2 BOX at 720.00, and 24 pieces at 60.00."""
    buyer = _Buyer()
    buyer.firm.stages(order=False, receipt=False)

    bill = _direct_bill(buyer, **({"invoice_uom_id": buyer.box} if named else {}))

    line = buyer.bill_line(bill)
    assert (line.current_invoice_quantity, line.invoice_uom_id) == (
        D("2.0000"),
        buyer.box,
    )
    assert (line.unit_price, bill.grand_total) == (D("720.0000"), D("1440.0000"))
    hidden = buyer.session.scalars(select(PurchaseOrderLine)).one()
    assert (hidden.conversion_factor, hidden.base_quantity) == (D("12"), D("24.0000"))
    assert buyer.stock() == D("24.0000")
    assert buyer.valuation() == (D("24.0000"), D("60.000000"), D("1440.0000"))
    assert buyer.books() == (D("1440.00"), D("0"), D("-1440.00"))


def test_a_bill_of_products_in_a_unit_no_rule_converts_is_refused() -> None:
    """A carton typed straight onto a bill is refused in the same words."""
    buyer = _Buyer()
    buyer.firm.stages(order=False, receipt=False)

    with pytest.raises(ValidationError) as refused:
        _direct_bill(buyer, invoice_uom_id=buyer.carton)

    assert str(refused.value.message) == NO_RULE
    assert buyer.session.scalars(select(PurchaseOrder)).all() == []


def test_a_bill_in_pieces_bills_a_receipt_of_boxes_up_to_what_came_in() -> None:
    """24 PIECE bills the 2 BOX received; 25 is more than came in."""
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named("c")))

    with pytest.raises(ValidationError, match="exceeds the available source"):
        buyer.bill(receipt, "25", invoice_uom_id=buyer.piece)
    buyer.session.rollback()
    bill = buyer.bill(receipt, "24", invoice_uom_id=buyer.piece)

    line = buyer.bill_line(bill)
    # Stored in the receipt line's unit, at the receipt's price for it.
    assert (line.current_invoice_quantity, line.unit_price) == (
        D("2.0000"),
        D("720.0000"),
    )
    assert bill.grand_total == D("1440.0000")
    assert buyer.books() == (D("1440.00"), D("0"), D("-1440.00"))


def test_a_supplier_lists_discount_break_counts_the_pieces_in_a_box() -> None:
    """2 BOX of 12 take the supplier's discount "from 20"; 1 BOX does not."""
    buyer = _Buyer()
    price_list = PriceList(
        firm_id=buyer.firm_id,
        code="SUP-BREAKS",
        name="Supplier breaks",
        vendor_id=buyer.firm.vendor.id,
        effective_from=date(2026, 4, 1),
    )
    buyer.session.add(price_list)
    buyer.session.flush()
    buyer.session.add_all(
        [
            PriceListItem(
                price_list_id=price_list.id,
                firm_id=buyer.firm_id,
                product_id=buyer.firm.product.id,
                min_quantity=D(quantity),
                discount_percent=D(percent),
            )
            for quantity, percent in (("0", "2"), ("20", "5"))
        ]
    )
    buyer.session.commit()

    two = buyer.order_line(buyer.order(approve=False, purchase_uom_id=buyer.box))
    one = buyer.order_line(
        buyer.order(approve=False, ordered_quantity="1", purchase_uom_id=buyer.box)
    )

    assert (two.discount_percent, two.discount_amount) == (D("5.0000"), D("72.0000"))
    assert (one.discount_percent, one.discount_amount) == (D("2.0000"), D("14.4000"))


def test_a_price_typed_on_a_bill_or_return_in_pieces_is_the_price_of_a_piece() -> None:
    """60.00 a piece on 24 PIECE is 720.00 a box on the 2 BOX it is stored as."""
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named("c")))

    bill = buyer.bill(receipt, "24", invoice_uom_id=buyer.piece, unit_price="60")

    line = buyer.bill_line(bill)
    assert (line.current_invoice_quantity, line.unit_price) == (
        D("2.0000"),
        D("720.0000"),
    )
    assert bill.grand_total == D("1440.0000")
    sent = buyer.send_back(
        "PURCHASE_INVOICE",
        bill.id,
        line.id,
        quantity="12",
        return_uom_id=buyer.piece,
        unit_price="60",
    )
    back = buyer.return_line(sent)
    assert (back.current_return_quantity, back.unit_price, back.gross_amount) == (
        D("1.0000"),
        D("720.0000"),
        D("720.0000"),
    )


# ---- pieces that are not whole boxes (D-PRC-37, D-PRC-38) -------------------
#
# The third live check (2026-10-06): against a receipt of 2 BOX at 720.00, a
# bill of 7 PIECE at 60.00 was stored as 0.5833 BOX at 720.0411 and cleared
# 419.98 of the accrual, 0.02 to purchase price variance; 17 PIECE with no
# price were 1,020.024. A return of 7 PIECE was saved as 0.5833 BOX, approved,
# and refused at completion: "BOX is counted in whole numbers, so 0.5833 BOX
# cannot be entered."


def _variance(buyer: _Buyer) -> Decimal:
    """Return what has gone to purchase price variance."""
    return buyer.firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE)


def test_loose_pieces_billed_off_a_box_receipt_cost_what_the_pieces_cost() -> None:
    """7 PIECE at 60.00 are 420.00 and 17 with no price 1,020.00: no variance."""
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named("c")))

    seven = buyer.bill(receipt, "7", invoice_uom_id=buyer.piece, unit_price="60")

    line = buyer.bill_line(seven)
    assert (line.entered_quantity, line.invoice_uom_id) == (D("7.0000"), buyer.piece)
    # The cap still counts in the receipt line's unit, at the receipt's price.
    assert (line.current_invoice_quantity, line.unit_price) == (
        D("0.5833"),
        D("720.0000"),
    )
    assert line.conversion_factor == D("0.0833333333")
    assert (line.gross_amount, seven.grand_total) == (D("420.0000"), D("420.0000"))
    # The accrual is cleared for seven pieces, and nothing is variance.
    assert buyer.books() == (D("1440.00"), D("-1020.00"), D("-420.00"))
    assert _variance(buyer) == D("0")

    rest = buyer.bill(receipt, "17", invoice_uom_id=buyer.piece)

    line = buyer.bill_line(rest)
    assert (line.entered_quantity, line.current_invoice_quantity) == (
        D("17.0000"),
        D("1.4167"),
    )
    assert (line.unit_price, line.gross_amount) == (D("720.0000"), D("1020.0000"))
    assert buyer.books() == (D("1440.00"), D("0"), D("-1440.00"))
    assert _variance(buyer) == D("0")


def test_parts_in_pieces_that_round_up_as_boxes_still_bill_the_whole_receipt() -> None:
    """5, 5 and 14 PIECE are 0.4167 + 0.4167 + 1.1667 boxes: the third is taken.

    Each rounded on its own they come to 2.0001 BOX, and the bill that
    completes the receipt was refused as more than came in. It is stored as
    what was left.
    """
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named("c")))

    buyer.bill(receipt, "5", invoice_uom_id=buyer.piece)
    buyer.bill(receipt, "5.0", invoice_uom_id=buyer.piece)
    last = buyer.bill(receipt, "14", invoice_uom_id=buyer.piece)

    line = buyer.bill_line(last)
    assert (line.entered_quantity, line.current_invoice_quantity) == (
        D("14.0000"),
        D("1.1666"),
    )
    assert line.gross_amount == D("840.0000")
    assert buyer.books() == (D("1440.00"), D("0"), D("-1440.00"))
    assert _variance(buyer) == D("0")
    with pytest.raises(ValidationError, match="exceeds the available source"):
        buyer.bill(receipt, "1", invoice_uom_id=buyer.piece)
    buyer.session.rollback()


def test_the_bill_that_completes_a_receipt_takes_what_the_others_left() -> None:
    """A box at 1,000.00 billed 4 + 4 + 4 pieces is 333.33 + 333.33 + 333.34."""
    buyer = _Buyer()
    receipt = buyer.receive(
        buyer.order(ordered_quantity="1", unit_price="1000", **buyer.named("c")),
        "1",
    )

    bills = [
        buyer.bill(receipt, quantity, invoice_uom_id=buyer.piece)
        for quantity in ("4", "4.0", "4.00")
    ]

    assert [buyer.bill_line(bill).gross_amount for bill in bills] == [
        D("333.3333"),
        D("333.3333"),
        D("333.3400"),
    ]
    assert buyer.books() == (D("1000.00"), D("0"), D("-1000.00"))
    assert _variance(buyer) == D("0")


def test_seven_pieces_sent_back_off_a_box_line_leave_as_seven_pieces() -> None:
    """D-PRC-38: saved, approved and completed; 7 pieces leave at 60.00."""
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named("c")))
    buyer.bill(receipt)
    assert buyer.stock() == D("24.0000")

    sent = buyer.send_back(
        "GOODS_RECEIPT",
        receipt.id,
        buyer.receipt_line(receipt).id,
        quantity="7",
        return_uom_id=buyer.piece,
    )

    line = buyer.return_line(sent)
    assert (line.entered_quantity, line.return_uom_id) == (D("7.0000"), buyer.piece)
    assert (line.current_return_quantity, line.unit_price) == (
        D("0.5833"),
        D("720.0000"),
    )
    assert line.gross_amount == D("420.0000")
    buyer.session.expire_all()
    assert buyer.session.get(PurchaseReturn, sent.id).status == "COMPLETED"
    assert buyer.stock() == D("17.0000")
    moved, cost, value = buyer.movement(line.inventory_transaction_id)
    assert (abs(moved), cost, abs(value)) == (D("7.0000"), D("60.000000"), D("420.00"))
    # The other 17 go back too, and the line is then all gone.
    rest = buyer.send_back(
        "GOODS_RECEIPT",
        receipt.id,
        buyer.receipt_line(receipt).id,
        quantity="17",
        return_uom_id=buyer.piece,
    )
    assert buyer.return_line(rest).current_return_quantity == D("1.4167")
    assert buyer.stock() == D("0.0000")
    assert buyer.books()[0] == D("0.00")


@pytest.mark.parametrize("named", [True, False])
def test_half_a_box_typed_as_a_box_is_refused_where_it_is_saved(named: bool) -> None:
    """0.5 BOX, named or as the line's own unit, never reaches approval."""
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named("c")))
    unit = {"return_uom_id": buyer.box} if named else {}

    with pytest.raises(ValidationError) as refused:
        buyer.send_back(
            "GOODS_RECEIPT",
            receipt.id,
            buyer.receipt_line(receipt).id,
            quantity="0.5",
            **unit,
        )
    buyer.session.rollback()

    assert str(refused.value.message) == (
        "BOX is counted in whole numbers, so 0.5 BOX cannot be entered."
    )
    assert buyer.session.scalars(select(PurchaseReturn)).all() == []
    with pytest.raises(ValidationError, match="so 0.5 BOX cannot be entered"):
        buyer.bill(receipt, "0.5", **({"invoice_uom_id": buyer.box} if named else {}))
    buyer.session.rollback()


def test_the_hsn_summary_counts_what_was_typed_in_the_unit_it_names() -> None:
    """D-PRC-50: 7 PIECE billed and 5 PIECE sent back read 7 and 2 PIECE.

    The row is filed under the typed unit, and counted the stored part of a
    box beside it: "0.5833 PIECE" bought, and 0.1666 after the return.
    """
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named("c")))
    bill = buyer.bill(receipt, "7", invoice_uom_id=buyer.piece)
    register = GstPurchaseRegisterService(buyer.session)

    [bought] = register.hsn_summary(buyer.firm_id)
    assert (bought.unit, bought.quantity) == ("PIECE", D("7.0000"))
    assert bought.taxable_value == D("420.00")

    buyer.send_back(
        "PURCHASE_INVOICE",
        bill.id,
        buyer.bill_line(bill).id,
        quantity="5",
        return_uom_id=buyer.piece,
    )

    [left] = register.hsn_summary(buyer.firm_id)
    assert (left.unit, left.quantity) == ("PIECE", D("2.0000"))
    assert left.taxable_value == D("120.00")


def test_loose_pieces_sent_back_before_the_bill_clear_what_the_pieces_cost() -> None:
    """D-PRC-54: 7 PIECE back off an unbilled receipt of 2 BOX take off 420.00.

    The accrual's share was worked from 0.5833 of 2 boxes -- 419.98 -- so two
    paise went to price variance, and came back when the other 17 were billed.
    """
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named("c")))

    buyer.send_back(
        "GOODS_RECEIPT",
        receipt.id,
        buyer.receipt_line(receipt).id,
        quantity="7",
        return_uom_id=buyer.piece,
    )

    assert buyer.books() == (D("1020.00"), D("-1020.00"), D("0"))
    assert _variance(buyer) == D("0")

    buyer.bill(receipt, "17", invoice_uom_id=buyer.piece)

    assert buyer.books() == (D("1020.00"), D("0"), D("-1020.00"))
    assert _variance(buyer) == D("0")


def test_the_return_that_finishes_a_receipt_billed_in_pieces_leaves_no_paisa() -> None:
    """7 PIECE billed, then the other 17 sent back unbilled: nothing is left."""
    buyer = _Buyer()
    receipt = buyer.receive(buyer.order(**buyer.named("c")))
    buyer.bill(receipt, "7", invoice_uom_id=buyer.piece)

    buyer.send_back(
        "GOODS_RECEIPT",
        receipt.id,
        buyer.receipt_line(receipt).id,
        quantity="17",
        return_uom_id=buyer.piece,
    )

    assert buyer.books() == (D("420.00"), D("0"), D("-420.00"))
    assert _variance(buyer) == D("0")


def test_a_receipt_refused_for_its_quantity_or_its_unit_says_which_unit() -> None:
    """D-PRC-57: 7 PIECE of 2 BOX are in the wrong unit; 3 are 3 BOX of 2 BOX.

    Seven loose pieces were told only that they "exceed allowed quantity",
    being seven against two, and three boxes were told the same with no unit
    and no figure.
    """
    buyer = _Buyer()
    order = buyer.order(**buyer.named("c"))

    with pytest.raises(ValidationError) as pieces:
        buyer.receive(order, "7", purchase_uom_id=buyer.piece)
    buyer.session.rollback()
    with pytest.raises(ValidationError) as boxes:
        buyer.receive(order, "3")
    buyer.session.rollback()

    assert str(pieces.value.message) == (
        f"Line 1 is received in PIECE where {order.po_number} orders it in BOX. "
        "Receive it in the order's unit."
    )
    assert str(boxes.value.message) == (
        "Goods receipt exceeds allowed quantity for PO line 1: 2 BOX ordered, "
        "0 BOX already received, and this line receives 3 BOX."
    )
