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
from app.goods_receipt.models import GoodsReceipt
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.inventory.models import InventoryRecord
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate, PurchaseWorkflowSettingsWrite
from app.purchase.services import PurchaseService
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from app.purchase_invoice.services import PurchaseInvoiceService
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
        """A supplier bill that names only products."""
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
        """An order a person raised and approved, for ten at 100."""
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
        """The bill service on this session."""
        return PurchaseInvoiceService(self.session)

    def stock(self) -> Decimal:
        """What the warehouse holds of the product."""
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
        """The live order and receipt a bill raised for itself."""
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
    """A firm on a fresh in-memory store."""
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
