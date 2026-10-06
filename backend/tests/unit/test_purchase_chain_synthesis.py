"""A firm that switches buying stages off records only the supplier's bill.

Backlog §38, the buying twin of `test_sales_chain_synthesis.py`: the bill
raises the purchase order and the goods receipt behind it through the real
services. Nothing arrives while the bill is a draft; approving it completes
the receipt (stock in, goods received not invoiced credited) and posts the
bill (that accrual cleared), and cancelling a draft withdraws what it raised.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch, Warehouse
from app.business.models import BusinessProfile
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.models import FirmControlAccount, GLPosting
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptCreate
from app.goods_receipt.services.goods_receipt_service import GoodsReceiptService
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.inventory.models import InventoryRecord, ProductValuation
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate, PurchaseWorkflowSettingsWrite
from app.purchase.services import PurchaseService
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.models import PurchaseReturn
from app.purchase_return.schemas import PurchaseReturnCreate
from app.purchase_return.services import PurchaseReturnService
from app.vendors.models import Vendor


class _Firm:
    """A firm with one branch, warehouse, supplier and product, and its books."""

    def __init__(self, session: Session, code: str = "CHAIN") -> None:
        """Create the masters and seed the chart of accounts."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name=f"{code} Firm",
            code=code,
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.flush()
        if (
            session.scalar(
                select(BusinessProfile).where(BusinessProfile.code == "GENERIC")
            )
            is None
        ):
            session.add(
                BusinessProfile(
                    code="GENERIC",
                    name="Generic",
                    industry_type="GENERIC",
                    status="ACTIVE",
                    is_default=True,
                    default_settings={},
                )
            )
        self.branch = Branch(
            firm_id=self.firm.id,
            code=f"BR-{code}",
            name="Branch",
            display_name="Branch",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
            is_default=True,
        )
        session.add(self.branch)
        session.flush()
        self.warehouse = Warehouse(
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            code=f"WH-{code}",
            name="Warehouse",
            display_name="Warehouse",
            status="ACTIVE",
            is_default=True,
        )
        self.vendor = Vendor(
            firm_id=self.firm.id,
            code=f"VEN-{code}",
            name="Vendor",
            display_name="Vendor",
            status="ACTIVE",
        )
        self.product = Product(
            firm_id=self.firm.id,
            code=f"SKU-{code}",
            name="Product",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            purchase_price=Decimal("90"),
        )
        session.add_all([self.warehouse, self.vendor, self.product])
        session.commit()
        seed_finance_setup(
            session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor_id,
        )

    def stages(self, *, order: bool, receipt: bool) -> None:
        """Say which buying stages the firm types by hand."""
        PurchaseWorkflowService(self.session).update_settings(
            PurchaseWorkflowSettingsWrite(
                purchase_order_stage=order, goods_receipt_stage=receipt
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def product_bill(
        self, quantity: str = "10", price: str | None = "100", number: str = "S-1"
    ) -> PurchaseInvoiceCreate:
        """Build a supplier bill that names only products."""
        line: dict[str, object] = {
            "line_number": 1,
            "product_id": self.product.id,
            "current_invoice_quantity": quantity,
        }
        if price is not None:
            line["unit_price"] = price
        return PurchaseInvoiceCreate.model_validate(
            {
                "vendor_id": self.vendor.id,
                "invoice_date": "2026-08-10",
                "supplier_invoice_number": number,
                "supplier_invoice_date": "2026-08-09",
                "lines": [line],
            }
        )

    def approved_order(self) -> PurchaseOrder:
        """Raise and approve an order as a person would, for ten at 100."""
        service = PurchaseService(self.session)
        order = service.create_order(
            PurchaseOrderCreate.model_validate(
                {
                    "branch_id": self.branch.id,
                    "warehouse_id": self.warehouse.id,
                    "vendor_id": self.vendor.id,
                    "purchase_date": "2026-08-02",
                    "lines": [
                        {
                            "product_id": self.product.id,
                            "ordered_quantity": "10",
                            "unit_price": "100",
                        }
                    ],
                }
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        service.submit_order(order.id, firm_scope=self.firm.id, actor_id=self.actor_id)
        return service.approve_order(
            order.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )

    def bills(self) -> PurchaseInvoiceService:
        """Return the bill service on this session."""
        return PurchaseInvoiceService(self.session)

    def stock(self) -> Decimal:
        """Return what the warehouse holds of the product."""
        row = self.session.scalar(
            select(InventoryRecord).where(
                InventoryRecord.firm_id == self.firm.id,
                InventoryRecord.product_id == self.product.id,
            )
        )
        return Decimal("0") if row is None else row.current_quantity

    def balance(self, purpose: ControlAccountPurpose) -> Decimal:
        """Debit less credit on the firm's account for one purpose."""
        total = self.session.scalar(
            select(
                func.coalesce(
                    func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0
                )
            )
            .select_from(GLPosting)
            .join(
                FirmControlAccount,
                FirmControlAccount.ledger_account_id == GLPosting.ledger_account_id,
            )
            .where(
                FirmControlAccount.firm_id == self.firm.id,
                FirmControlAccount.purpose == purpose.value,
                FirmControlAccount.is_deleted.is_(False),
                GLPosting.is_deleted.is_(False),
            )
        )
        return Decimal(str(total or 0))

    def raised(self, bill: PurchaseInvoice) -> tuple[PurchaseOrder, GoodsReceipt]:
        """Return the live order and receipt a bill raised for itself."""
        receipt = self.session.scalar(
            select(GoodsReceipt).where(
                GoodsReceipt.raised_by_purchase_invoice_id == bill.id,
                GoodsReceipt.status != "CANCELLED",
            )
        )
        assert receipt is not None
        order = self.session.get(PurchaseOrder, receipt.purchase_order_id)
        assert order is not None
        return order, receipt


@pytest.fixture
def firm() -> _Firm:
    """Build a firm on a fresh in-memory store."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return _Firm(sessionmaker(bind=engine, expire_on_commit=False)())


def test_a_firm_on_the_whole_chain_still_bills_only_a_receipt(firm: _Firm) -> None:
    """No settings row means the chain as it always was: products are refused."""
    with pytest.raises(ValidationError, match="must name the goods receipt"):
        firm.bills().create_invoice(
            firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
        )


def test_receipts_cannot_be_typed_while_orders_are_not(firm: _Firm) -> None:
    """A receipt is raised against an order, so that combination is refused."""
    with pytest.raises(ValidationError, match="always raised against"):
        firm.stages(order=False, receipt=True)


def test_a_bill_of_products_raises_its_order_and_receipt_and_moves_nothing(
    firm: _Firm,
) -> None:
    """Saving the draft raises both documents; no stock and no journal yet."""
    firm.stages(order=False, receipt=False)
    bill = firm.bills().create_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    order, receipt = firm.raised(bill)
    assert order.status == "APPROVED"
    assert order.raised_by_purchase_invoice_id == bill.id
    assert receipt.status == "DRAFT"
    assert bill.grand_total == Decimal("1000.0000")
    assert firm.stock() == Decimal("0")
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0


def test_approving_the_bill_brings_the_goods_in_and_clears_the_accrual(
    firm: _Firm,
) -> None:
    """Receipt completed, stock on the shelf, the payable raised, GRNI at zero."""
    firm.stages(order=False, receipt=False)
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    order, receipt = firm.raised(bill)
    assert receipt.status == "COMPLETED"
    assert order.status == "RECEIVED"
    assert firm.stock() == Decimal("10")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == Decimal("1000")
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-1000")


def test_a_line_with_no_price_takes_the_products_purchase_price(
    firm: _Firm,
) -> None:
    """Silence on a product line is the product's standing purchase price."""
    firm.stages(order=False, receipt=False)
    bill = firm.bills().create_invoice(
        firm.product_bill(price=None), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert bill.grand_total == Decimal("900.0000")


def test_cancelling_a_draft_withdraws_what_it_raised(firm: _Firm) -> None:
    """The order and the receipt go with the bill; nothing was posted."""
    firm.stages(order=False, receipt=False)
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    order, receipt = firm.raised(bill)
    bills.cancel_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    firm.session.refresh(order)
    firm.session.refresh(receipt)
    assert receipt.status == "CANCELLED"
    assert order.status == "CANCELLED"
    assert firm.stock() == Decimal("0")


def test_editing_a_draft_raises_the_documents_again(firm: _Firm) -> None:
    """The old order and receipt are withdrawn; the new ones match the bill."""
    firm.stages(order=False, receipt=False)
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    first_order, first_receipt = firm.raised(bill)
    bills.update_invoice(
        bill.id,
        firm.product_bill(quantity="6"),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )
    firm.session.refresh(first_order)
    firm.session.refresh(first_receipt)
    assert first_receipt.status == "CANCELLED"
    assert first_order.status == "CANCELLED"
    order, _ = firm.raised(bill)
    assert order.id != first_order.id
    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    assert firm.stock() == Decimal("6")
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0


def test_with_only_receipts_off_the_bill_receives_the_order_it_names(
    firm: _Firm,
) -> None:
    """A person's order, billed directly: the bill raises just the receipt."""
    firm.stages(order=True, receipt=False)
    order = firm.approved_order()
    order_line = firm.session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert order_line is not None
    bills = firm.bills()
    bill = bills.create_invoice(
        PurchaseInvoiceCreate.model_validate(
            {
                "invoice_date": "2026-08-10",
                "supplier_invoice_number": "S-2",
                "supplier_invoice_date": "2026-08-09",
                "lines": [
                    {
                        "source_document_type": "PURCHASE_ORDER",
                        "source_document_id": order.id,
                        "source_document_line_id": order_line.id,
                        "line_number": 1,
                        "current_invoice_quantity": "4",
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    raised_order, receipt = firm.raised(bill)
    assert raised_order.id == order.id
    assert order.raised_by_purchase_invoice_id is None
    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    firm.session.refresh(order)
    firm.session.refresh(receipt)
    assert receipt.status == "COMPLETED"
    assert order.status == "PARTIALLY_RECEIVED"
    assert firm.stock() == Decimal("4")
    # Cancelling the bill's own draft never touches an order a person raised.
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0


def test_a_draft_receipt_is_billable_only_by_the_bill_that_raised_it(
    firm: _Firm,
) -> None:
    """Another bill naming the draft receipt is refused as it always was."""
    firm.stages(order=False, receipt=False)
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    _, receipt = firm.raised(bill)
    line = next(
        line
        for line in bills.invoice_response(bill).lines
        if line.source_document_id == receipt.id
    )
    with pytest.raises(ValidationError, match="Complete it first"):
        bills.create_invoice(
            PurchaseInvoiceCreate.model_validate(
                {
                    "invoice_date": "2026-08-10",
                    "supplier_invoice_number": "S-3",
                    "supplier_invoice_date": "2026-08-09",
                    "lines": [
                        {
                            "source_document_type": "GOODS_RECEIPT",
                            "source_document_id": receipt.id,
                            "source_document_line_id": line.source_document_line_id,
                            "line_number": 1,
                            "current_invoice_quantity": "1",
                        }
                    ],
                }
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_a_preview_of_a_bill_of_products_saves_nothing(firm: _Firm) -> None:
    """Priced through the chain, then rolled back: no order, receipt or bill."""
    firm.stages(order=False, receipt=False)
    preview = firm.bills().preview_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert Decimal(str(preview.invoice.grand_total)) == Decimal("1000")
    for model in (PurchaseOrder, GoodsReceipt, PurchaseInvoice):
        assert firm.session.scalar(select(func.count(model.id))) == 0


def test_the_default_branch_and_warehouse_must_be_the_firms(firm: _Firm) -> None:
    """A default outside the firm is refused when it is set, not at bill time."""
    with pytest.raises(ValidationError, match="not one of this firm's branches"):
        PurchaseWorkflowService(firm.session).update_settings(
            PurchaseWorkflowSettingsWrite(
                purchase_order_stage=False,
                goods_receipt_stage=False,
                default_branch_id=uuid4(),
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_only_a_firm_role_above_purchasing_may_switch_the_stages() -> None:
    """Turning receipts off is a control over the purchase roles, not theirs."""
    code = "PURCHASE_MANAGE_SETTINGS"
    assert code not in ROLE_PERMISSION_CODES["PURCHASE_MANAGER"]
    assert code not in ROLE_PERMISSION_CODES["PURCHASE_EXECUTIVE"]
    assert code in ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    assert code in ROLE_PERMISSION_CODES["FIRM_MANAGER"]


# --- D-PRC-90: a bill off an order in parts brings the free goods in once ---


def _order_with_free(
    firm: _Firm, *lines: dict[str, object]
) -> tuple[PurchaseOrder, list[PurchaseOrderLine]]:
    """Raise and approve an order: 24 at 60 with 2 free unless lines say."""
    service = PurchaseService(firm.session)
    order = service.create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "vendor_id": firm.vendor.id,
                "purchase_date": "2026-08-02",
                "lines": list(lines)
                or [
                    {
                        "product_id": firm.product.id,
                        "ordered_quantity": "24",
                        "free_quantity": "2",
                        "unit_price": "60",
                        "discount_amount": "144",
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.submit_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    service.approve_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    stored = list(
        firm.session.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == order.id)
            .order_by(PurchaseOrderLine.line_number)
        ).all()
    )
    return order, stored


def _part_bill(
    firm: _Firm,
    order: PurchaseOrder,
    *parts: tuple[PurchaseOrderLine, str, dict[str, object]],
    approve: bool = True,
) -> GoodsReceipt:
    """Bill parts of an order's lines with receipts off; return the receipt."""
    bills = firm.bills()
    bill = bills.create_invoice(
        PurchaseInvoiceCreate.model_validate(
            {
                "invoice_date": "2026-08-10",
                "supplier_invoice_number": f"S-{uuid4().hex[:8]}",
                "supplier_invoice_date": "2026-08-09",
                "lines": [
                    {
                        "source_document_type": "PURCHASE_ORDER",
                        "source_document_id": order.id,
                        "source_document_line_id": line.id,
                        "line_number": number,
                        "current_invoice_quantity": quantity,
                    }
                    | extra
                    for number, (line, quantity, extra) in enumerate(parts, start=1)
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    _, receipt = firm.raised(bill)
    if approve:
        bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    firm.session.refresh(receipt)
    return receipt


def _valuation(firm: _Firm) -> tuple[Decimal, Decimal, Decimal]:
    """Return the units valued, their moving average and their value."""
    firm.session.expire_all()
    row = firm.session.scalars(
        select(ProductValuation).where(ProductValuation.product_id == firm.product.id)
    ).one()
    return (
        Decimal(str(row.quantity_on_hand)),
        Decimal(str(row.average_cost)).quantize(Decimal("0.0001")),
        Decimal(str(row.total_value)).quantize(Decimal("0.01")),
    )


@pytest.mark.parametrize(
    ("parts", "free", "after"),
    [
        (
            ("12", "12"),
            ("1", "1"),
            ((Decimal("13"), Decimal("49.8462")), (Decimal("26"), Decimal("49.8462"))),
        ),
        (
            ("8", "16"),
            ("0", "2"),
            ((Decimal("8"), Decimal("54.0000")), (Decimal("26"), Decimal("49.8462"))),
        ),
        (
            ("16", "8"),
            ("1", "1"),
            ((Decimal("17"), Decimal("50.8235")), (Decimal("26"), Decimal("49.8462"))),
        ),
        (
            ("8", "8", "8"),
            ("0", "1", "1"),
            (
                (Decimal("8"), Decimal("54.0000")),
                (Decimal("17"), Decimal("50.8235")),
                (Decimal("26"), Decimal("49.8462")),
            ),
        ),
    ],
)
def test_part_bills_of_an_order_bring_its_free_goods_in_once(
    firm: _Firm,
    parts: tuple[str, ...],
    free: tuple[str, ...],
    after: tuple[tuple[Decimal, Decimal], ...],
) -> None:
    """24 + 2 free billed in parts: 26 on the shelf at 1,296.00, never 28."""
    firm.stages(order=True, receipt=False)
    order, (line,) = _order_with_free(firm)

    for quantity, expected, (stock, average) in zip(parts, free, after, strict=True):
        receipt = _part_bill(firm, order, (line, quantity, {}))
        assert receipt.total_free_quantity == Decimal(expected)
        assert firm.stock() == stock
        assert _valuation(firm)[:2] == (stock, average)

    assert _valuation(firm) == (Decimal("26"), Decimal("49.8462"), Decimal("1296.00"))
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0
    firm.session.refresh(order)
    assert order.status == "RECEIVED"


def test_a_bill_of_the_whole_order_line_still_brings_all_its_free_goods(
    firm: _Firm,
) -> None:
    """One bill of 24: both free units come with it."""
    firm.stages(order=True, receipt=False)
    order, (line,) = _order_with_free(firm)

    receipt = _part_bill(firm, order, (line, "24", {}))

    assert receipt.total_free_quantity == Decimal("2")
    assert _valuation(firm) == (Decimal("26"), Decimal("49.8462"), Decimal("1296.00"))


def test_free_goods_typed_on_a_part_bill_stand_and_the_rest_follow(
    firm: _Firm,
) -> None:
    """Both free units typed on the first part: the part that completes has 0."""
    firm.stages(order=True, receipt=False)
    order, (line,) = _order_with_free(firm)

    first = _part_bill(firm, order, (line, "12", {"free_quantity": "2"}))
    assert first.total_free_quantity == Decimal("2")
    assert firm.stock() == Decimal("14")

    second = _part_bill(firm, order, (line, "12", {}))
    assert second.total_free_quantity == Decimal("0")
    assert _valuation(firm) == (Decimal("26"), Decimal("49.8462"), Decimal("1296.00"))


def test_a_typed_zero_on_a_part_bill_leaves_the_free_goods_for_the_last(
    firm: _Firm,
) -> None:
    """A typed zero is an answer: nothing free came with this part."""
    firm.stages(order=True, receipt=False)
    order, (line,) = _order_with_free(firm)

    first = _part_bill(firm, order, (line, "12", {"free_quantity": "0"}))
    assert first.total_free_quantity == Decimal("0")
    second = _part_bill(firm, order, (line, "12", {}))
    assert second.total_free_quantity == Decimal("2")
    assert firm.stock() == Decimal("26")


def test_free_goods_typed_beyond_what_the_order_line_has_left_are_refused(
    firm: _Firm,
) -> None:
    """More than the order gives, or than its earlier parts left, by name."""
    firm.stages(order=True, receipt=False)
    order, (line,) = _order_with_free(firm)

    with pytest.raises(ValidationError, match="has 2 left to give"):
        _part_bill(firm, order, (line, "12", {"free_quantity": "3"}))
    firm.session.rollback()
    _part_bill(firm, order, (line, "12", {"free_quantity": "1"}))
    with pytest.raises(
        ValidationError,
        match="brings in 2 free.*has 1 left to give: 2 free on the order, "
        "1 already received",
    ):
        _part_bill(firm, order, (line, "12", {"free_quantity": "2"}))
    firm.session.rollback()
    assert firm.stock() == Decimal("13")


def test_two_draft_part_bills_share_the_free_goods_whichever_is_approved(
    firm: _Firm,
) -> None:
    """Drafts of 8 and 16 hold 0 and 2 between them before either arrives."""
    firm.stages(order=True, receipt=False)
    order, (line,) = _order_with_free(firm)

    first = _part_bill(firm, order, (line, "8", {}), approve=False)
    second = _part_bill(firm, order, (line, "16", {}), approve=False)

    assert first.total_free_quantity == Decimal("0")
    assert second.total_free_quantity == Decimal("2")


def test_a_cancelled_part_bill_gives_its_free_goods_back(firm: _Firm) -> None:
    """A draft part withdrawn is not counted against the next one."""
    firm.stages(order=True, receipt=False)
    order, (line,) = _order_with_free(firm)
    receipt = _part_bill(firm, order, (line, "24", {}), approve=False)
    assert receipt.total_free_quantity == Decimal("2")
    assert receipt.raised_by_purchase_invoice_id is not None
    firm.bills().cancel_invoice(
        receipt.raised_by_purchase_invoice_id,
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
        reason="typed twice",
    )

    again = _part_bill(firm, order, (line, "24", {}))

    assert again.total_free_quantity == Decimal("2")
    assert firm.stock() == Decimal("26")


def test_a_free_only_order_line_comes_in_whole_with_the_first_bill_naming_it(
    firm: _Firm,
) -> None:
    """Paid 0, free 3: the first bill naming the line brings all 3, once."""
    firm.stages(order=True, receipt=False)
    order, (paid, gift) = _order_with_free(
        firm,
        {"product_id": firm.product.id, "ordered_quantity": "24", "unit_price": "60"},
        {"product_id": firm.product.id, "ordered_quantity": "0", "free_quantity": "3"},
    )

    first = _part_bill(firm, order, (paid, "12", {}), (gift, "0", {}))
    assert first.total_free_quantity == Decimal("3")
    assert firm.stock() == Decimal("15")

    second = _part_bill(firm, order, (paid, "12", {}), (gift, "0", {}))
    assert second.total_free_quantity == Decimal("0")
    assert firm.stock() == Decimal("27")


# --- D-PRC-93: each buying document inherits the discount of the line it
# continues, a rate as itself and an amount by the share it covers ---

_TWENTY_FOUR = {"ordered_quantity": "24", "unit_price": "60"}


def _discounted_order(
    firm: _Firm, **discount: object
) -> tuple[PurchaseOrder, PurchaseOrderLine]:
    """Approve an order of 24 at 60.00 with the discount given on its line."""
    order, (line,) = _order_with_free(
        firm, {"product_id": firm.product.id} | _TWENTY_FOUR | discount
    )
    return order, line


def _receive(
    firm: _Firm,
    order: PurchaseOrder,
    line: PurchaseOrderLine,
    quantity: str,
    **typed: object,
) -> GoodsReceiptLine:
    """Receive part of an order line on a completed receipt a person typed."""
    service = GoodsReceiptService(firm.session)
    receipt = service.create_receipt(
        GoodsReceiptCreate.model_validate(
            {
                "purchase_order_id": order.id,
                "receipt_date": "2026-08-05",
                "lines": [
                    {
                        "purchase_order_line_id": line.id,
                        "line_number": 1,
                        "current_receipt_quantity": quantity,
                        "warehouse_id": firm.warehouse.id,
                    }
                    | typed
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    return firm.session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).one()


def _bill_receipt(
    firm: _Firm, receipt_line: GoodsReceiptLine, quantity: str, **typed: object
) -> PurchaseInvoice:
    """Bill part of a receipt line and approve the bill."""
    bills = firm.bills()
    bill = bills.create_invoice(
        PurchaseInvoiceCreate.model_validate(
            {
                "invoice_date": "2026-08-10",
                "supplier_invoice_number": f"S-{uuid4().hex[:8]}",
                "supplier_invoice_date": "2026-08-09",
                "lines": [
                    {
                        "source_document_type": "GOODS_RECEIPT",
                        "source_document_id": receipt_line.goods_receipt_id,
                        "source_document_line_id": receipt_line.id,
                        "line_number": 1,
                        "current_invoice_quantity": quantity,
                    }
                    | typed
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    return bills.approve_invoice(
        bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )


def _send_back(
    firm: _Firm, source_type: str, source_id: object, line_id: object, quantity: str
) -> PurchaseReturn:
    """Draft a return of some of a receipt or bill line, typing no figure."""
    return PurchaseReturnService(firm.session).create_return(
        PurchaseReturnCreate.model_validate(
            {
                "warehouse_id": firm.warehouse.id,
                "return_date": "2026-08-12",
                "lines": [
                    {
                        "source_document_type": source_type,
                        "source_document_id": source_id,
                        "source_document_line_id": line_id,
                        "line_number": 1,
                        "current_return_quantity": quantity,
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _settled(firm: _Firm) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Return stock value, the accrual left, payables and price variance."""
    return (
        firm.balance(ControlAccountPurpose.INVENTORY),
        firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED),
        firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE),
        firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE),
    )


def test_a_receipts_discount_typed_as_an_amount_reaches_its_bill(
    firm: _Firm,
) -> None:
    """The report's case: 72.00 off each receipt of 12 is 72.00 off its bill.

    Only a rate was inherited and the receipt keeps none for an amount, so
    the two bills came to 1,440.00 before tax where the order and the
    receipts said 1,296.00, and 144.00 went to purchase price variance.
    """
    order, line = _discounted_order(firm, discount_amount="144")

    bills = [
        _bill_receipt(
            firm, _receive(firm, order, line, "12", discount_amount="72"), "12"
        )
        for _ in range(2)
    ]

    assert [bill.grand_total for bill in bills] == [Decimal("648.0000")] * 2
    assert _settled(firm) == (Decimal("1296"), 0, Decimal("-1296"), 0)


def test_an_amount_off_a_receipt_is_split_over_its_part_bills_to_the_paisa(
    firm: _Firm,
) -> None:
    """100.00 off a receipt of 24, billed 8, 8 and 8: the bills take 100.00."""
    order, line = _discounted_order(firm)
    receipt_line = _receive(firm, order, line, "24", discount_amount="100")

    bills = [_bill_receipt(firm, receipt_line, "8") for _ in range(3)]

    taken = [
        firm.session.scalars(
            select(PurchaseInvoiceLine.discount_amount).where(
                PurchaseInvoiceLine.purchase_invoice_id == bill.id
            )
        ).one()
        for bill in bills
    ]
    assert taken == [Decimal("33.3300"), Decimal("33.3400"), Decimal("33.3300")]
    assert sum((bill.grand_total for bill in bills), Decimal("0")) == Decimal("1340")
    assert _settled(firm) == (Decimal("1340"), 0, Decimal("-1340"), 0)


@pytest.mark.parametrize(
    ("discount", "worth"),
    [
        ({"discount_percent": "10"}, Decimal("1296")),
        ({"discount_amount": "144"}, Decimal("1296")),
        ({"discount_amount": "100"}, Decimal("1340")),
    ],
)
def test_a_receipt_that_types_no_discount_takes_its_order_lines(
    firm: _Firm, discount: dict[str, object], worth: Decimal
) -> None:
    """Received 8, 8 and 8 saying nothing: stock and bills at the order's net.

    The receipt took no discount unless the client repeated it, so goods
    ordered at 1,296.00 were valued, and then billed, at 1,440.00.
    """
    order, line = _discounted_order(firm, **discount)

    received = [_receive(firm, order, line, "8") for _ in range(3)]

    assert sum((row.discount_amount for row in received), Decimal("0")) == (
        Decimal("1440") - worth
    )
    assert firm.balance(ControlAccountPurpose.INVENTORY) == worth
    bills = [_bill_receipt(firm, row, "8") for row in received]
    assert sum((bill.grand_total for bill in bills), Decimal("0")) == worth
    assert _settled(firm) == (worth, 0, -worth, 0)


def test_a_discount_typed_on_a_receipt_replaces_the_orders_a_zero_included(
    firm: _Firm,
) -> None:
    """A typed zero is a refusal, a typed rate or amount the receipt's own."""
    order, line = _discounted_order(firm, discount_percent="10")

    none = _receive(firm, order, line, "8", discount_percent="0")
    rate = _receive(firm, order, line, "8", discount_percent="5")
    amount = _receive(firm, order, line, "8", discount_amount="30")

    assert [row.discount_amount for row in (none, rate, amount)] == [
        Decimal("0.0000"),
        Decimal("24.0000"),
        Decimal("30.0000"),
    ]


def test_a_discount_typed_on_the_bill_replaces_the_receipts(firm: _Firm) -> None:
    """The bill's own figure stands over the amount it would have inherited."""
    order, line = _discounted_order(firm, discount_amount="144")
    receipt_line = _receive(firm, order, line, "24", discount_amount="144")

    typed = _bill_receipt(firm, receipt_line, "12", discount_amount="50")
    refused = _bill_receipt(firm, receipt_line, "12", discount_percent="0")

    assert typed.grand_total == Decimal("670.0000")
    assert refused.grand_total == Decimal("720.0000")


def test_part_bills_off_an_order_take_its_amount_between_them(firm: _Firm) -> None:
    """Receipt stage off, 100.00 off 24, billed 8, 8, 8: 1,340.00, no variance."""
    firm.stages(order=True, receipt=False)
    order, line = _discounted_order(firm, discount_amount="100")

    receipts = [_part_bill(firm, order, (line, "8", {})) for _ in range(3)]

    assert sum(
        (receipt.line_discount_total for receipt in receipts), Decimal("0")
    ) == Decimal("100")
    assert _settled(firm) == (Decimal("1340"), 0, Decimal("-1340"), 0)


def test_goods_go_back_at_the_amount_their_receipt_or_bill_took_off(
    firm: _Firm,
) -> None:
    """6 of 24 received at 144.00 off go back at 324.00, off either document."""
    order, line = _discounted_order(firm, discount_amount="144")
    receipt_line = _receive(firm, order, line, "24", discount_amount="144")

    unbilled = _send_back(
        firm, "GOODS_RECEIPT", receipt_line.goods_receipt_id, receipt_line.id, "6"
    )
    assert unbilled.subtotal == Decimal("324.0000")
    PurchaseReturnService(firm.session).cancel_return(
        unbilled.id, firm_scope=firm.firm.id, actor_id=firm.actor_id, reason="billed"
    )

    bill = _bill_receipt(firm, receipt_line, "24")
    bill_line = firm.session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill.id
        )
    ).one()
    billed = _send_back(firm, "PURCHASE_INVOICE", bill.id, bill_line.id, "6")
    assert billed.subtotal == Decimal("324.0000")


def test_an_orders_header_discount_reaches_three_part_receipts_and_bills(
    firm: _Firm,
) -> None:
    """100.00 off the whole order, received and billed 8, 8, 8: nothing left."""
    service = PurchaseService(firm.session)
    order = service.create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "vendor_id": firm.vendor.id,
                "purchase_date": "2026-08-02",
                "header_discount_amount": "100",
                "lines": [{"product_id": firm.product.id} | _TWENTY_FOUR],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.submit_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    service.approve_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    line = firm.session.scalars(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    ).one()

    for _ in range(3):
        _bill_receipt(firm, _receive(firm, order, line, "8"), "8")

    inventory, accrual, payable, variance = _settled(firm)
    assert (inventory, payable) == (Decimal("1340"), Decimal("-1340"))
    assert (accrual, variance) == (0, 0)
