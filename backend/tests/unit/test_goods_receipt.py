"""Goods receipt lifecycle, stock posting and firm-scope tests.

The 2026-08-09 review fixed three defects here and left no test behind, so
nothing pinned them: cancelling a completed receipt left the stock it had
posted on the books, the totals were computed twice by two different formulas,
and editing a receipt deleted and re-inserted its lines, which stranded the
``source_document_line_id`` references downstream documents keep as bare UUIDs.

These cases exist to keep all three fixed.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_models  # noqa: F401
from app.branches.models import Branch, Warehouse
from app.business.models import BusinessProfile
from app.common.audit.models import AuditLog
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import customer as _customer_models  # noqa: F401
from app.finance.models import (
    FirmControlAccount,
    GLPosting,
    JournalEntry,
    JournalStatus,
)
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptCreate
from app.goods_receipt.services import GoodsReceiptService
from app.identity.models import UserFirm
from app.inventory.models import (
    InventoryRecord,
    InventoryTransaction,
    ProductValuation,
)
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate, PurchaseOrderUpdate
from app.purchase.services import PurchaseService
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceSourceType,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.sales.models import territory as _sales_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import uom as _uom_models  # noqa: F401
from app.uom.schemas import ConversionRuleCreate, ConversionRuleUpdate, UomCreate
from app.uom.services import UomService
from app.vendors.models import Vendor

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


def _session_factory() -> sessionmaker[Session]:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    """Build a principal carrying the given permissions."""
    return Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=sorted(permissions),
        ),
    )


def _firm_scope(
    principal: Principal, session: Session, firm_id: UUID | None
) -> ResolvedFirmScope:
    """Resolve firm scope exactly as a request does, through the shared helper."""
    return required_firm_scope(
        optional_firm_scope(principal=principal, db=session, x_firm_id=firm_id)
    )


class _Fixture:
    """The firm, its masters and one approved purchase order to receive."""

    def __init__(self, session: Session, code: str) -> None:
        """Create everything a goods receipt needs, for one firm."""
        self.actor_id = uuid4()
        self.session = session
        self.firm = Firm(
            name=f"{code} Firm",
            code=code,
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.flush()
        # The profile is shared by every firm in the store, so a second
        # fixture in the same session reuses the one already seeded.
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
                    created_by=self.actor_id,
                    updated_by=self.actor_id,
                )
            )
            session.flush()
        self.branch = Branch(
            firm_id=self.firm.id,
            code=f"BR-{code}",
            name="Branch",
            display_name="Branch",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
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
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.vendor = Vendor(
            firm_id=self.firm.id,
            code=f"VEN-{code}",
            name="Vendor",
            display_name="Vendor",
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.product = Product(
            firm_id=self.firm.id,
            code=f"SKU-{code}",
            name="Product",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        session.add_all([self.warehouse, self.vendor, self.product])
        session.commit()
        # Completing a receipt posts to the general ledger, so the firm needs
        # its chart of accounts, an open period and its control accounts.
        seed_finance_setup(
            session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor_id,
        )
        self.order = self._purchase_order()

    def _purchase_order(self) -> PurchaseOrder:
        """Raise the order the receipts are taken against, and approve it.

        These fixtures used to leave the order at DRAFT and receive against it
        anyway, which is exactly the hole `_assert_order_receivable` closes --
        the suite could not have caught it because it depended on it.
        """
        service = PurchaseService(self.session)
        order = service.create_order(
            PurchaseOrderCreate.model_validate(
                {
                    "po_number": f"PO-{self.firm.code}",
                    "branch_id": self.branch.id,
                    "warehouse_id": self.warehouse.id,
                    "vendor_id": self.vendor.id,
                    "purchase_date": "2026-08-02",
                    "status": "DRAFT",
                    "lines": [
                        {
                            "product_id": self.product.id,
                            "ordered_quantity": "10",
                            "unit_price": "100",
                            "warehouse_id": self.warehouse.id,
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

    @property
    def order_line(self) -> PurchaseOrderLine:
        """Return the order's single line."""
        line = self.session.scalar(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == self.order.id
            )
        )
        assert line is not None
        return line

    def receipt_payload(
        self, quantity: str = "4", **over: object
    ) -> GoodsReceiptCreate:
        """Build a receipt payload for the order's line."""
        payload: dict[str, object] = {
            "purchase_order_id": self.order.id,
            "receipt_date": "2026-08-05",
            "lines": [
                {
                    "purchase_order_line_id": self.order_line.id,
                    "line_number": 1,
                    "current_receipt_quantity": quantity,
                    "unit_price": "100",
                    "warehouse_id": self.warehouse.id,
                }
            ],
        }
        payload.update(over)
        return GoodsReceiptCreate.model_validate(payload)


def _stock(session: Session, firm_id: UUID, product_id: UUID) -> Decimal:
    """Return the quantity the projection currently holds."""
    row = session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.firm_id == firm_id,
            InventoryRecord.product_id == product_id,
        )
    )
    return Decimal("0") if row is None else row.current_quantity


def test_completing_a_receipt_posts_the_stock_it_received() -> None:
    """A completed receipt puts what it received onto the shelf."""
    session = _session_factory()()
    fixture = _Fixture(session, "GRN1")
    service = GoodsReceiptService(session)

    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    assert _stock(session, fixture.firm.id, fixture.product.id) == Decimal("0")

    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )

    session.expire_all()
    assert _stock(session, fixture.firm.id, fixture.product.id) == Decimal("4")


def test_cancelling_a_completed_receipt_takes_the_stock_back() -> None:
    """Cancelling used to leave the stock it had posted on the books.

    The receipt showed as cancelled while the quantity stayed on the shelf, so
    the projection and the document disagreed with nothing to reconcile them.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN2")
    service = GoodsReceiptService(session)

    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    session.expire_all()
    assert _stock(session, fixture.firm.id, fixture.product.id) == Decimal("4")

    service.cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="wrong delivery",
    )

    session.expire_all()
    assert _stock(session, fixture.firm.id, fixture.product.id) == Decimal("0")
    # The reversal is its own movement: the ledger keeps both halves.
    movements = session.scalars(
        select(InventoryTransaction).where(
            InventoryTransaction.firm_id == fixture.firm.id
        )
    ).all()
    assert len(movements) == 2
    assert sum(item.current_quantity_delta for item in movements) == Decimal("0")
    assert any(
        item.reversal_of_transaction_id is not None for item in movements
    ), "the reversal must be linked to what it reversed"


def test_cancelling_an_uncompleted_receipt_posts_nothing() -> None:
    """There is nothing to take back from a receipt that never posted."""
    session = _session_factory()()
    fixture = _Fixture(session, "GRN3")
    service = GoodsReceiptService(session)

    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="never arrived",
    )

    session.expire_all()
    assert _stock(session, fixture.firm.id, fixture.product.id) == Decimal("0")
    assert session.scalars(select(InventoryTransaction)).all() == []
    cancelled = session.scalar(
        select(AuditLog).where(AuditLog.action == "grn.cancelled")
    )
    assert cancelled is not None
    assert cancelled.firm_id == fixture.firm.id


def test_a_draft_receipt_cannot_be_closed() -> None:
    """Closing finishes a receipt's business; a draft never started it.

    `close_receipt` refused only a receipt already CLOSED, so a DRAFT that had
    posted no stock and accrued nothing went to CLOSED and read as finished for
    good (D-BUY-9, driven on TEST01 on 2026-09-18). A draft is cancelled, not
    closed; only a COMPLETED receipt can be closed.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-CLOSE")
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    with pytest.raises(ValidationError, match="Only completed goods receipts"):
        service.close_receipt(
            receipt.id,
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
            reason="tidying up",
        )
    session.expire_all()
    assert receipt.status == "DRAFT"

    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    closed = service.close_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="all in",
    )
    assert closed.status == "CLOSED"


def test_editing_a_receipt_keeps_its_line_identities() -> None:
    """Receipt line ids survive an edit.

    Purchase invoices record which receipt line they came from in
    source_document_line_id, a bare UUID with no foreign key. Re-inserting the
    lines on every save left those references pointing at rows that no longer
    existed.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN4")
    service = GoodsReceiptService(session)

    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    before = {
        line.line_number: line.id
        for line in session.scalars(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt.id,
                GoodsReceiptLine.is_deleted.is_(False),
            )
        )
    }

    service.update_receipt(
        receipt.id,
        fixture.receipt_payload("6"),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    session.expire_all()
    after = {
        line.line_number: (line.id, line.current_receipt_quantity)
        for line in session.scalars(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt.id,
                GoodsReceiptLine.is_deleted.is_(False),
            )
        )
    }
    assert set(after) == set(before)
    assert after[1][0] == before[1], "the line was re-inserted instead of updated"
    assert after[1][1] == Decimal("6")


def test_receipt_totals_are_computed_once() -> None:
    """The totals were computed twice, by two formulas that disagreed."""
    session = _session_factory()()
    fixture = _Fixture(session, "GRN5")
    service = GoodsReceiptService(session)

    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    session.expire_all()
    lines = session.scalars(
        select(GoodsReceiptLine).where(
            GoodsReceiptLine.goods_receipt_id == receipt.id,
            GoodsReceiptLine.is_deleted.is_(False),
        )
    ).all()
    stored = session.get(GoodsReceipt, receipt.id)
    assert stored is not None
    assert stored.subtotal == sum(line.net_amount for line in lines)
    assert stored.grand_total == stored.subtotal + stored.tax_total


def test_a_receipt_is_invisible_to_another_firm() -> None:
    """One firm's receipt cannot be fetched from another firm's scope."""
    session = _session_factory()()
    first = _Fixture(session, "GRNA")
    second = _Fixture(session, "GRNB")
    service = GoodsReceiptService(session)

    receipt = service.create_receipt(
        first.receipt_payload("4"),
        firm_id=first.firm.id,
        actor_id=first.actor_id,
    )

    assert service.get_receipt(receipt.id, firm_scope=first.firm.id).id == receipt.id
    with pytest.raises(ResourceNotFoundError):
        service.get_receipt(receipt.id, firm_scope=second.firm.id)


def test_receipt_scope_requires_membership_of_the_selected_firm() -> None:
    """A user outside the firm cannot resolve a scope for it."""
    factory = _session_factory()
    setup = factory()
    fixture = _Fixture(setup, "GRNC")
    member_id = uuid4()
    outsider_id = uuid4()
    setup.add(UserFirm(user_id=member_id, firm_id=fixture.firm.id, is_active=True))
    setup.commit()
    firm_id = fixture.firm.id
    setup.close()

    session = factory()
    scope = _firm_scope(_principal(member_id, {"GRN_VIEW"}), session, firm_id)
    assert scope.firm_id == firm_id

    with pytest.raises(AuthorizationError):
        _firm_scope(_principal(outsider_id, {"GRN_VIEW"}), session, firm_id)


def _order_status(session: Session, order_id: UUID) -> str:
    session.expire_all()
    row = session.get(PurchaseOrder, order_id)
    assert row is not None
    return str(row.status)


def _approve(fixture: "_Fixture") -> None:
    """Assert the order is where receiving begins.

    The fixture now approves on the way out, because receiving against an
    unapproved order is refused. This is kept as the statement of what these
    tests depend on rather than deleted.
    """
    assert _order_status(fixture.session, fixture.order.id) == "APPROVED"


def test_a_part_delivery_leaves_the_order_partially_received() -> None:
    """A half-delivered order says so.

    `PARTIALLY_RECEIVED` was declared from the first migration and never
    written, so an order that was half delivered still read APPROVED and every
    screen had to derive "how much is left?" from the receipts.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-PART")
    _approve(fixture)
    service = GoodsReceiptService(session)

    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    # A draft receipt moves nothing, including the order.
    assert _order_status(session, fixture.order.id) == "APPROVED"

    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )

    # Four of ten.
    assert _order_status(session, fixture.order.id) == "PARTIALLY_RECEIVED"


def test_receiving_the_rest_marks_the_order_received() -> None:
    """Four then six against an order of ten finishes it."""
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-FULL")
    _approve(fixture)
    service = GoodsReceiptService(session)

    for quantity in ("4", "6"):
        receipt = service.create_receipt(
            fixture.receipt_payload(quantity),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )
        service.complete_receipt(
            receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
        )

    assert _order_status(session, fixture.order.id) == "RECEIVED"


def test_cancelling_the_receipt_walks_the_order_back() -> None:
    """Cancelling the only receipt makes the order receivable again.

    The status is derived from the completed receipts every time, so the order
    comes back down without a second, subtractive path to get wrong.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-BACK")
    _approve(fixture)
    service = GoodsReceiptService(session)

    receipt = service.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    assert _order_status(session, fixture.order.id) == "RECEIVED"

    service.cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="wrong goods",
    )

    # Every receipt against it is cancelled, so it is receivable again.
    assert _order_status(session, fixture.order.id) == "APPROVED"


def test_a_cancelled_order_is_never_revived_by_a_receipt() -> None:
    """Only an order already in the receiving part of its life is moved.

    Receiving against a cancelled order is a different problem; quietly
    reviving one here would hide it.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-DEAD")
    _approve(fixture)
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    PurchaseService(session).cancel_order(
        fixture.order.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="no longer needed",
    )

    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )

    assert _order_status(session, fixture.order.id) == "CANCELLED"


def test_an_unapproved_order_cannot_be_received_against() -> None:
    """Nothing checked this, and completing a receipt posts stock.

    A draft purchase order could be received against and the receipt completed,
    which posts stock and posts to the ledger, so the approval step was
    bypassable by any client that did not filter its own picker. The order then
    stayed DRAFT for good, because the resync only moves an order already in
    the receiving part of its life.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-DRAFT")
    PurchaseService(session).update_order(
        fixture.order.id,
        PurchaseOrderUpdate.model_validate(
            {
                "branch_id": fixture.branch.id,
                "warehouse_id": fixture.warehouse.id,
                "vendor_id": fixture.vendor.id,
                "purchase_date": "2026-08-02",
                "lines": [
                    {
                        "product_id": fixture.product.id,
                        "ordered_quantity": "10",
                        "unit_price": "100",
                        "warehouse_id": fixture.warehouse.id,
                    }
                ],
            }
        ),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    assert _order_status(session, fixture.order.id) == "DRAFT"

    with pytest.raises(ValidationError, match="only be received against an approved"):
        GoodsReceiptService(session).create_receipt(
            fixture.receipt_payload("4"),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )


def test_a_cancelled_order_cannot_be_received_against() -> None:
    """The same guard, from the other terminal state."""
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-CANC")
    PurchaseService(session).cancel_order(
        fixture.order.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="no longer needed",
    )

    with pytest.raises(ValidationError, match="only be received against an approved"):
        GoodsReceiptService(session).create_receipt(
            fixture.receipt_payload("4"),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )


def test_a_received_order_refuses_an_edit() -> None:
    """Its lines are what stock was posted at.

    Editing them leaves the receipt describing a document that no longer says
    what it said.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-EDIT")
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload("4"), firm_id=fixture.firm.id, actor_id=fixture.actor_id
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    assert _order_status(session, fixture.order.id) == "PARTIALLY_RECEIVED"

    with pytest.raises(ValidationError, match="Goods have been received"):
        PurchaseService(session).update_order(
            fixture.order.id,
            PurchaseOrderUpdate.model_validate(
                {
                    "branch_id": fixture.branch.id,
                    "warehouse_id": fixture.warehouse.id,
                    "vendor_id": fixture.vendor.id,
                    "purchase_date": "2026-08-02",
                    "lines": [
                        {
                            "product_id": fixture.product.id,
                            "ordered_quantity": "999",
                            "unit_price": "1",
                            "warehouse_id": fixture.warehouse.id,
                        }
                    ],
                }
            ),
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
        )

    assert _order_status(session, fixture.order.id) == "PARTIALLY_RECEIVED"


def _receipt_journals(session: Session, receipt_id: UUID) -> list[JournalEntry]:
    """Every journal entry raised against one goods receipt, oldest first."""
    return list(
        session.scalars(
            select(JournalEntry)
            .where(
                JournalEntry.source_module == "goods_receipt",
                JournalEntry.source_id == receipt_id,
                JournalEntry.is_deleted.is_(False),
            )
            .order_by(JournalEntry.created_at)
        ).all()
    )


def test_cancelling_a_completed_receipt_reverses_its_journal() -> None:
    """The stock came back; the ledger did not.

    `_reverse_inventory` put the stock back and nothing put the ledger back --
    `post_goods_receipt` had one caller, on the complete path, and
    `reverse_entry` was never called for a receipt. The general ledger's
    inventory balance drifted above the warehouse by the value of every
    cancelled receipt, and goods received not invoiced kept a liability for
    goods that had gone back.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-REV")
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    posted = _receipt_journals(session, receipt.id)
    assert len(posted) == 1
    assert posted[0].status == JournalStatus.POSTED.value
    original_debit = posted[0].total_debit

    service.cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="sent back",
    )

    entries = _receipt_journals(session, receipt.id)
    assert len(entries) == 2, "cancelling must raise a mirror entry"
    original, mirror = entries
    assert original.status == JournalStatus.REVERSED.value
    assert mirror.reversal_of_id == original.id
    assert mirror.total_debit == original_debit
    # Every account nets to nothing once the pair is taken together, which is
    # the only way the stock ledger and the GL can still be reconciled.
    net: dict[UUID, Decimal] = {}
    for entry in entries:
        for line in entry.lines:
            net[line.ledger_account_id] = (
                net.get(line.ledger_account_id, Decimal("0"))
                + line.debit_amount
                - line.credit_amount
            )
    assert set(net.values()) == {Decimal("0")}, net


def test_cancelling_twice_does_not_reverse_the_reversal() -> None:
    """`reverse_entry` copies the source ids onto the mirror it posts.

    So a lookup that only filtered on POSTED would find that mirror on a second
    pass and reverse the reversal, putting the original back on the books.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-TWICE")
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    for _ in range(3):
        service.cancel_receipt(
            receipt.id,
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
            reason="again",
        )

    entries = _receipt_journals(session, receipt.id)
    assert len(entries) == 2
    assert [entry.status for entry in entries] == [
        JournalStatus.REVERSED.value,
        JournalStatus.POSTED.value,
    ]


def test_an_uncompleted_receipt_cancels_without_a_journal() -> None:
    """Nothing was posted, so there is nothing to take back."""
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-NOJRNL")
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    service.cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="never arrived",
    )

    assert _receipt_journals(session, receipt.id) == []


def _bill_the_receipt(
    session: Session, fixture: "_Fixture", receipt: GoodsReceipt, *, status: str
) -> None:
    """Put a purchase invoice against the receipt, at the given status.

    Written straight to the tables rather than through `PurchaseInvoiceService`
    because the guard under test is a question about data state -- is anything
    billing this receipt? -- and building a real invoice would test the invoice
    module instead.
    """
    invoice = PurchaseInvoice(
        firm_id=fixture.firm.id,
        vendor_id=fixture.vendor.id,
        branch_id=fixture.branch.id,
        invoice_number=f"PI-{status}-{receipt.grn_number}",
        invoice_date=date(2026, 8, 2),
        supplier_invoice_number=f"SUP-{status}",
        supplier_invoice_date=date(2026, 8, 2),
        status=status,
        created_by=fixture.actor_id,
        updated_by=fixture.actor_id,
    )
    session.add(invoice)
    session.flush()
    line = session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).first()
    assert line is not None
    session.add(
        PurchaseInvoiceLine(
            purchase_invoice_id=invoice.id,
            firm_id=fixture.firm.id,
            line_number=1,
            source_document_type="GOODS_RECEIPT",
            source_document_id=receipt.id,
            source_document_number=receipt.grn_number,
            source_document_line_id=line.id,
            source_document_line_number=line.line_number,
            product_id=fixture.product.id,
            received_quantity=Decimal("10"),
            current_invoice_quantity=Decimal("10"),
            unit_price=Decimal("100"),
            created_by=fixture.actor_id,
            updated_by=fixture.actor_id,
        )
    )
    session.flush()


def test_an_invoiced_receipt_cannot_be_cancelled() -> None:
    """Reversing it would leave the accrual and the payable disagreeing.

    Receiving posted `Dr Inventory / Cr goods received not invoiced`; approving
    the invoice cleared that accrual and raised a payable. Reversing the
    receipt now debits the accrual a second time and leaves it with a balance
    nobody can explain, while the payable stays exactly where it was. Handing
    goods back after they have been billed is a purchase return.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-BILLED")
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    _bill_the_receipt(session, fixture, receipt, status="APPROVED")

    with pytest.raises(ValidationError, match="has been invoiced"):
        service.cancel_receipt(
            receipt.id,
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
            reason="sent back",
        )

    session.expire_all()
    assert _order_status(session, fixture.order.id) == "RECEIVED"
    assert len(_receipt_journals(session, receipt.id)) == 1


def test_a_cancelled_invoice_does_not_hold_the_receipt() -> None:
    """The refusal is about a live bill, not any bill that ever existed."""
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-UNBILLED")
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    _bill_the_receipt(session, fixture, receipt, status="CANCELLED")

    service.cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="sent back",
    )

    assert len(_receipt_journals(session, receipt.id)) == 2


def _inventory_account_balance(session: Session, firm_id: UUID) -> Decimal:
    """Return what the inventory control account currently holds."""
    total = session.scalar(
        select(
            func.coalesce(func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0)
        )
        .select_from(GLPosting)
        .join(
            FirmControlAccount,
            FirmControlAccount.ledger_account_id == GLPosting.ledger_account_id,
        )
        .where(
            FirmControlAccount.firm_id == firm_id,
            FirmControlAccount.purpose == ControlAccountPurpose.INVENTORY.value,
            FirmControlAccount.is_deleted.is_(False),
            GLPosting.is_deleted.is_(False),
        )
    )
    return Decimal(str(total or 0))


def _stock_value(session: Session, firm_id: UUID) -> Decimal:
    """Return what the warehouse says its stock is worth."""
    total = session.scalar(
        select(func.coalesce(func.sum(ProductValuation.total_value), 0)).where(
            ProductValuation.firm_id == firm_id,
            ProductValuation.is_deleted.is_(False),
        )
    )
    return Decimal(str(total or 0))


def test_cancelling_a_receipt_credits_what_the_stock_actually_gave_back() -> None:
    """Mirroring the original entry breaks the books once the average moves.

    A receipt brings stock in at the price on the receipt. Cancelling it takes
    the stock back out at the moving average the warehouse carries it at, and
    those are the same number only until something else is received at another
    price. `_reverse_receipt_journal` mirrored the original entry regardless,
    so inventory was credited with a figure no movement ever removed.

    Found on 2026-08-22 by cancelling one receipt on a seeded store: 8,040.00
    mirrored out of the inventory account against 5,752.60 of stock removed,
    leaving the store 2,287.42 out in a single request -- the same invariant
    `scripts/verify_sample_data.py` checks first.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-AVG")
    service = GoodsReceiptService(session)

    dear = service.create_receipt(
        fixture.receipt_payload("5"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        dear.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )

    # A second receipt at a quarter of the price drags the average down, which
    # is all it takes for the two figures to part company.
    cheap_payload = fixture.receipt_payload("5")
    cheap_payload.lines[0].unit_price = Decimal("25")
    cheap = service.create_receipt(
        cheap_payload, firm_id=fixture.firm.id, actor_id=fixture.actor_id
    )
    service.complete_receipt(
        cheap.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )

    session.expire_all()
    assert _stock_value(session, fixture.firm.id) == _inventory_account_balance(
        session, fixture.firm.id
    ), "the two books start in step"

    service.cancel_receipt(
        dear.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="sent back",
    )
    session.expire_all()

    # The invariant the whole thing exists for: what the warehouse holds and
    # what the ledger says it holds are the same number.
    assert _stock_value(session, fixture.firm.id) == _inventory_account_balance(
        session, fixture.firm.id
    )

    entries = _receipt_journals(session, dear.id)
    original, reversal = entries
    assert original.status == JournalStatus.REVERSED.value
    assert reversal.reversal_of_id == original.id
    assert reversal.total_debit == reversal.total_credit, "and it balances"
    # The accrual goes back in full -- the firm owes nobody for goods it handed
    # back -- while inventory is credited only with what left the shelf.
    accrual = sum(line.debit_amount for line in reversal.lines if line.debit_amount > 0)
    assert accrual == original.total_debit


def _approved_bill(fixture: "_Fixture", receipt: GoodsReceipt) -> PurchaseInvoice:
    """Raise and approve a real supplier invoice for the whole receipt."""
    from app.purchase_invoice.schemas import (
        PurchaseInvoiceCreate,
        PurchaseInvoiceLineWrite,
        PurchaseInvoiceSourceType,
    )
    from app.purchase_invoice.services import PurchaseInvoiceService

    line = fixture.session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).first()
    assert line is not None
    service = PurchaseInvoiceService(fixture.session)
    invoice = service.create_invoice(
        PurchaseInvoiceCreate(
            supplier_invoice_number=f"SUP-{receipt.grn_number}",
            supplier_invoice_date=date(2026, 8, 6),
            invoice_date=date(2026, 8, 6),
            source_documents=[
                {
                    "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[
                PurchaseInvoiceLineWrite(
                    source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    source_document_id=receipt.id,
                    source_document_line_id=line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("10"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    return service.approve_invoice(
        invoice.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )


def _journals_for(session: Session, *source_ids: UUID) -> list[JournalEntry]:
    """Every journal entry raised against the given documents."""
    return list(
        session.scalars(
            select(JournalEntry).where(
                JournalEntry.source_id.in_(source_ids),
                JournalEntry.is_deleted.is_(False),
            )
        ).all()
    )


def test_cancelling_an_approved_bill_takes_its_journal_back() -> None:
    """D-BUY-2: the bill's journal stayed posted after it was cancelled.

    Cancelling changed the status and left Dr accrual / Dr input tax / Cr
    payable in the ledger, and the receipt -- no longer invoiced -- could then
    be cancelled too, clearing the accrual a second time. Driven on TEST01 on
    2026-09-18: 2300 was left debited 600 on its own. With both cancelled,
    every account the two documents touched must net to nothing.
    """
    from app.purchase_invoice.services import PurchaseInvoiceService

    session = _session_factory()()
    fixture = _Fixture(session, "BILL-REV")
    receipts = GoodsReceiptService(session)
    receipt = receipts.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    receipts.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    bill = _approved_bill(fixture, receipt)

    PurchaseInvoiceService(session).cancel_invoice(
        bill.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    bill_entries = [
        e
        for e in _journals_for(session, bill.id)
        if e.source_module == "purchase_invoice"
    ]
    assert len(bill_entries) == 2, "cancelling must raise a mirror of the bill"
    assert {e.status for e in bill_entries} == {
        JournalStatus.REVERSED.value,
        JournalStatus.POSTED.value,
    }

    receipts.cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="sent back after the bill was cancelled",
    )
    net: dict[UUID, Decimal] = {}
    for entry in _journals_for(session, bill.id, receipt.id):
        for line in entry.lines:
            net[line.ledger_account_id] = (
                net.get(line.ledger_account_id, Decimal("0"))
                + line.debit_amount
                - line.credit_amount
            )
    assert set(net.values()) == {Decimal("0")}, net


def test_a_paid_bill_cannot_be_cancelled() -> None:
    """A payment applied to a bill is undone first, by reversing the payment."""
    from app.purchase_invoice.services import PurchaseInvoiceService
    from app.settlements.schemas import SettlementCreate
    from app.settlements.services import PaymentService

    session = _session_factory()()
    fixture = _Fixture(session, "BILL-PAID")
    receipts = GoodsReceiptService(session)
    receipt = receipts.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    receipts.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    bill = _approved_bill(fixture, receipt)
    payment = PaymentService(session).create(
        SettlementCreate.model_validate(
            {
                "party_id": fixture.vendor.id,
                "settlement_date": "2026-08-07",
                "amount": "100",
                "method": "BANK",
                "allocations": [{"invoice_id": bill.id, "amount": "100"}],
            }
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    with pytest.raises(ValidationError, match=payment.settlement_number):
        PurchaseInvoiceService(session).cancel_invoice(
            bill.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
        )
    session.expire_all()
    still = session.get(PurchaseInvoice, bill.id)
    assert still is not None and still.status == "APPROVED"


@pytest.mark.parametrize("state", ["DRAFT", "CANCELLED"])
def test_only_a_completed_receipt_can_be_billed_or_returned(state: str) -> None:
    """D-BUY-5: a bill or a return named a receipt whose stock never posted.

    Driven on TEST01 on 2026-09-18: a DRAFT receipt was billed, the bill was
    approved -- a payable for goods nobody received -- and returned against.
    """
    from app.purchase_invoice.schemas import (
        PurchaseInvoiceCreate,
        PurchaseInvoiceLineWrite,
        PurchaseInvoiceSourceType,
    )
    from app.purchase_invoice.services import PurchaseInvoiceService
    from app.purchase_return.schemas import (
        PurchaseReturnCreate,
        PurchaseReturnLineWrite,
        PurchaseReturnSourceType,
    )
    from app.purchase_return.services import PurchaseReturnService

    session = _session_factory()()
    fixture = _Fixture(session, f"GRN-{state}")
    receipts = GoodsReceiptService(session)
    receipt = receipts.create_receipt(
        fixture.receipt_payload("5"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    if state == "CANCELLED":
        receipts.cancel_receipt(
            receipt.id,
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
            reason="never arrived",
        )
    line = session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).first()
    assert line is not None

    with pytest.raises(ValidationError, match="only a completed goods receipt"):
        PurchaseInvoiceService(session).create_invoice(
            PurchaseInvoiceCreate(
                supplier_invoice_number="SUP-EARLY",
                supplier_invoice_date=date(2026, 8, 6),
                invoice_date=date(2026, 8, 6),
                source_documents=[
                    {
                        "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
                        "source_document_id": receipt.id,
                    }
                ],
                lines=[
                    PurchaseInvoiceLineWrite(
                        source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                        source_document_id=receipt.id,
                        source_document_line_id=line.id,
                        line_number=1,
                        current_invoice_quantity=Decimal("5"),
                    )
                ],
            ),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )
    with pytest.raises(ValidationError, match="only a completed goods receipt"):
        PurchaseReturnService(session).create_return(
            PurchaseReturnCreate(
                supplier_return_number="SUP-EARLY-RET",
                supplier_return_date=date(2026, 8, 6),
                return_date=date(2026, 8, 6),
                warehouse_id=fixture.warehouse.id,
                source_documents=[
                    {
                        "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
                        "source_document_id": receipt.id,
                    }
                ],
                lines=[
                    PurchaseReturnLineWrite(
                        source_document_type=PurchaseReturnSourceType.GOODS_RECEIPT,
                        source_document_id=receipt.id,
                        source_document_line_id=line.id,
                        line_number=1,
                        current_return_quantity=Decimal("2"),
                        warehouse_id=fixture.warehouse.id,
                    )
                ],
            ),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )


def _control_balance(session: Session, firm_id: UUID, purpose: str) -> Decimal:
    """Return the debit-less-credit balance of one control account."""
    total = session.scalar(
        select(
            func.coalesce(func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0)
        )
        .select_from(GLPosting)
        .join(
            FirmControlAccount,
            FirmControlAccount.ledger_account_id == GLPosting.ledger_account_id,
        )
        .where(
            FirmControlAccount.firm_id == firm_id,
            FirmControlAccount.purpose == purpose,
            FirmControlAccount.is_deleted.is_(False),
            GLPosting.is_deleted.is_(False),
        )
    )
    return Decimal(str(total or 0))


def _bill(
    session: Session,
    fixture: "_Fixture",
    receipt: GoodsReceipt,
    *,
    quantity: str,
    unit_price: str,
    supplier_number: str,
) -> PurchaseInvoice:
    """Raise and approve a supplier bill for part of the receipt's line."""
    line = session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).first()
    assert line is not None
    service = PurchaseInvoiceService(session)
    invoice = service.create_invoice(
        PurchaseInvoiceCreate(
            vendor_id=fixture.vendor.id,
            branch_id=fixture.branch.id,
            supplier_invoice_number=supplier_number,
            supplier_invoice_date=date(2026, 8, 6),
            invoice_date=date(2026, 8, 6),
            source_documents=[
                {
                    "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[
                PurchaseInvoiceLineWrite(
                    source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    source_document_id=receipt.id,
                    source_document_line_id=line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal(quantity),
                    unit_price=Decimal(unit_price),
                )
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    return service.approve_invoice(
        invoice.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )


def _accrual_cleared_by(session: Session, invoice: PurchaseInvoice) -> Decimal:
    """Return what the bill's journal debited to goods received not invoiced."""
    entry = session.scalar(
        select(JournalEntry).where(
            JournalEntry.source_module == "purchase_invoice",
            JournalEntry.source_id == invoice.id,
            JournalEntry.is_deleted.is_(False),
        )
    )
    assert entry is not None
    accrual_account = session.scalar(
        select(FirmControlAccount.ledger_account_id).where(
            FirmControlAccount.firm_id == invoice.firm_id,
            FirmControlAccount.purpose
            == ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED.value,
        )
    )
    return sum(
        (
            line.debit_amount
            for line in entry.lines
            if line.ledger_account_id == accrual_account
        ),
        Decimal("0"),
    )


def test_billing_part_of_a_receipt_clears_only_its_share_of_the_accrual() -> None:
    """Bill 4 of a received 10 and the accrual for the other 6 must stand.

    `_accrued_cost` cleared the whole receipt line's accrual whatever share of
    it the bill covered: the bill for 4 debited goods received not invoiced
    the full 1000, booked 600 of nothing as a favourable price variance, and
    the bill for the 6 then debited another 1000 (D-BUY-7, driven on TEST01
    on 2026-09-18 as PI-2026-2027-000006 and -000007).
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-PART")
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    accrual = ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED.value
    variance = ControlAccountPurpose.PURCHASE_PRICE_VARIANCE.value
    assert _control_balance(session, fixture.firm.id, accrual) == Decimal("-1000.00")

    first = _bill(
        session, fixture, receipt, quantity="4", unit_price="100", supplier_number="A"
    )
    session.expire_all()
    assert _accrual_cleared_by(session, first) == Decimal("400.00")
    assert _control_balance(session, fixture.firm.id, accrual) == Decimal("-600.00")
    assert _control_balance(session, fixture.firm.id, variance) == Decimal("0")

    second = _bill(
        session, fixture, receipt, quantity="6", unit_price="100", supplier_number="B"
    )
    session.expire_all()
    assert _accrual_cleared_by(session, second) == Decimal("600.00")
    assert _control_balance(session, fixture.firm.id, accrual) == Decimal("0")
    assert _control_balance(session, fixture.firm.id, variance) == Decimal("0")


def test_the_bill_that_completes_a_receipt_takes_the_rounding_residual() -> None:
    """Three bills for a third each must clear exactly what the receipt posted.

    A cost that does not divide leaves a paisa somewhere: rounding each share
    and summing them is not the same as rounding the sum the receipt posted.
    The bill that completes the receipt takes whatever the earlier ones left,
    so the accrual nets to zero rather than to a residual nobody can clear.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-THIRD")
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload(
            "3",
            lines=[
                {
                    "purchase_order_line_id": fixture.order_line.id,
                    "line_number": 1,
                    "current_receipt_quantity": "3",
                    "unit_price": "33.3333",
                    "warehouse_id": fixture.warehouse.id,
                }
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    accrual = ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED.value
    posted = -_control_balance(session, fixture.firm.id, accrual)
    assert posted == Decimal("100.00"), "99.9999 of cost, posted at the ledger's scale"

    cleared = [
        _accrual_cleared_by(
            session,
            _bill(
                session,
                fixture,
                receipt,
                quantity="1",
                unit_price="33.3333",
                supplier_number=number,
            ),
        )
        for number in ("A", "B", "C")
    ]
    session.expire_all()
    assert cleared == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert _control_balance(session, fixture.firm.id, accrual) == Decimal("0")


def test_a_rule_edited_under_a_draft_receipt_leaves_its_stock_alone() -> None:
    """A receipt's stock moves at the factor its line was written with.

    D-CFG-1: a line stored factor 1 and the rule's version number, and when
    the receipt was completed stock re-read the rule by that number. Edited to
    2 in the meantime, the line said 10 PACK at 1 and 20 KG went onto the
    shelf, valued and journalled at double the order; renumbered, the draft
    matched no rule and could not be completed at all.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-CONV")
    units = UomService(session)
    kg = units.create_uom(
        UomCreate(code="KGCONV", name="Kilogram"), actor_id=fixture.actor_id
    )
    pack = units.create_uom(
        UomCreate(code="PACKCONV", name="Pack"), actor_id=fixture.actor_id
    )
    fixture.product.base_uom_id = kg.id
    fixture.product.inventory_uom_id = kg.id
    session.commit()
    rule = units.create_conversion_rule(
        ConversionRuleCreate(
            product_id=fixture.product.id,
            from_uom_id=pack.id,
            to_uom_id=kg.id,
            conversion_factor=Decimal("1"),
            effective_from=date(2026, 1, 1),
            version_number=1,
        ),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    purchases = PurchaseService(session)
    order = purchases.create_order(
        PurchaseOrderCreate.model_validate(
            {
                "po_number": "PO-GRN-CONV-PACK",
                "branch_id": fixture.branch.id,
                "warehouse_id": fixture.warehouse.id,
                "vendor_id": fixture.vendor.id,
                "purchase_date": "2026-08-02",
                "lines": [
                    {
                        "product_id": fixture.product.id,
                        "ordered_quantity": "10",
                        "unit_price": "100",
                        "purchase_uom_id": pack.id,
                        "inventory_uom_id": kg.id,
                        "warehouse_id": fixture.warehouse.id,
                    }
                ],
            }
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    purchases.submit_order(
        order.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    purchases.approve_order(
        order.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    order_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert order_line is not None
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload(
            purchase_order_id=order.id,
            lines=[
                {
                    "purchase_order_line_id": order_line.id,
                    "line_number": 1,
                    "current_receipt_quantity": "10",
                    "unit_price": "100",
                    "warehouse_id": fixture.warehouse.id,
                }
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    line = session.scalar(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    )
    assert line is not None
    assert line.conversion_factor == Decimal("1")

    # The factor doubled and the revision renumbered while the receipt waits.
    units.update_conversion_rule(
        rule.id,
        ConversionRuleUpdate(conversion_factor=Decimal("2"), version_number=7),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )

    session.expire_all()
    assert _stock(session, fixture.firm.id, fixture.product.id) == Decimal("10")
    assert _stock_value(session, fixture.firm.id) == Decimal("1000.00")
    line = session.get(GoodsReceiptLine, line.id)
    assert line is not None
    assert line.conversion_factor == Decimal("1"), "the line is never rewritten"


def test_a_receipt_cannot_lift_its_own_cap() -> None:
    """D-BUY-16: the request body used to carry a switch for the cap.

    Driven 2026-09-19 on TEST01 (fixture ``po-received``, suffix t0919hv0b):
    PO-TEST01-HO-2026-2027-000012 for ten, already received in full, took
    GRN-TEST01-HO-2026-2027-000022 for 20 more with ``allow_over_receipt``
    true and ``over_receipt_percent`` 1000 -- completed, 30 in against 10
    ordered. Neither field is on the write schema any more, and the cap is
    the order line, less what came in before, for every receipt.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-OVER")
    service = GoodsReceiptService(session)
    body = fixture.receipt_payload("20").model_dump(mode="json")

    for field, value in (("allow_over_receipt", True), ("over_receipt_percent", 1000)):
        with pytest.raises(PydanticValidationError, match=field):
            GoodsReceiptCreate.model_validate({**body, field: value})

    first = service.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        first.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    with pytest.raises(ValidationError, match="exceeds allowed quantity"):
        service.create_receipt(
            fixture.receipt_payload("1"),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )


def test_a_closed_receipt_still_counts_as_received() -> None:
    """D-BUY-16, second way past the cap: closing freed a receipt's quantity.

    What an order line had taken in was summed over COMPLETED receipts only,
    so closing one -- which says its business is finished, not that its goods
    left -- let the same quantity be received again. Driven 2026-09-19 on
    TEST01: GRN-TEST01-HO-2026-2027-000019 (4) closed, then a receipt of 4
    more completed against an order of ten already received in full.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-CLOSED")
    service = GoodsReceiptService(session)
    receipt = service.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    service.close_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="finished",
    )

    with pytest.raises(ValidationError, match="exceeds allowed quantity"):
        service.create_receipt(
            fixture.receipt_payload("4"),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )
    assert _order_status(session, fixture.order.id) == "RECEIVED"


def test_the_receipt_reports_follow_the_receipts_life() -> None:
    """Closing keeps a receipt completed; a cancelled receipt's damage did not happen.

    "Receipts completed" kept COMPLETED alone, so closing -- the step after
    completing -- removed a receipt from it: TEST01's dropped from 2 to 1.
    "Damaged on receipt" and "Rejected on receipt" filtered the line and never
    the receipt, so a DRAFT's damage was reported before the goods were booked
    in and a CANCELLED receipt's stayed after its stock was taken back out
    (GRN-TEST01-HO-2026-2027-000035; D-RPT-15).
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN9")
    service = GoodsReceiptService(session)
    payload = fixture.receipt_payload("4")
    payload.lines[0].damaged_quantity = Decimal("1")
    payload.lines[0].rejected_quantity = Decimal("1")

    def seen() -> tuple[int, int, int]:
        return (
            len(service.completed_receipts(firm_scope=fixture.firm.id)),
            len(service.damaged_items(firm_scope=fixture.firm.id)),
            len(service.rejected_items(firm_scope=fixture.firm.id)),
        )

    draft = service.create_receipt(
        payload, firm_id=fixture.firm.id, actor_id=fixture.actor_id
    )
    assert seen() == (0, 0, 0), "a draft has booked nothing in"

    service.complete_receipt(
        draft.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    assert seen() == (1, 1, 1)

    service.close_receipt(
        draft.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id, reason="done"
    )
    assert seen() == (1, 1, 1), "closing takes nothing back out"

    again = fixture.receipt_payload("2")
    again.lines[0].damaged_quantity = Decimal("1")
    again.lines[0].rejected_quantity = Decimal("1")
    second = service.create_receipt(
        again, firm_id=fixture.firm.id, actor_id=fixture.actor_id
    )
    service.complete_receipt(
        second.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    assert seen() == (2, 2, 2)
    service.cancel_receipt(
        second.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="wrong delivery",
    )
    assert seen() == (1, 1, 1), "a cancelled receipt's damage did not happen"


def test_orders_part_received_agree_with_the_order() -> None:
    """The report and the order derive "received" the same way.

    The report walked orders of every status and counted COMPLETED receipts
    alone, where the order's own status counts COMPLETED and CLOSED: closing
    the receipt of 4 made the report say 6 of 10 received while
    `GET /purchases/{id}` read RECEIVED (PO-TEST01-HO-2026-2027-000018,
    D-RPT-14). It now reads the orders the receiving side has moved to
    PARTIALLY_RECEIVED, through `_received_quantities_for_po`.
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-RPT14")
    _approve(fixture)
    service = GoodsReceiptService(session)

    def report() -> list[tuple[str, Decimal, Decimal, int]]:
        return [
            (
                row.purchase_order_number,
                row.received_quantity,
                row.pending_quantity,
                row.receipt_count,
            )
            for row in service.partially_received_purchase_orders(
                firm_scope=fixture.firm.id
            )
        ]

    assert report() == [], "nothing received yet"
    first = service.create_receipt(
        fixture.receipt_payload("4"), firm_id=fixture.firm.id, actor_id=fixture.actor_id
    )
    service.complete_receipt(
        first.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    [(number, received, pending, count)] = report()
    assert (received, pending, count) == (Decimal("4"), Decimal("6"), 1)
    assert number == fixture.order.po_number
    assert _order_status(session, fixture.order.id) == "PARTIALLY_RECEIVED"

    service.close_receipt(
        first.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id, reason="done"
    )
    assert report()[0][1:] == (Decimal("4"), Decimal("6"), 1), "closing changes nothing"

    second = service.create_receipt(
        fixture.receipt_payload("6"), firm_id=fixture.firm.id, actor_id=fixture.actor_id
    )
    service.complete_receipt(
        second.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    assert _order_status(session, fixture.order.id) == "RECEIVED"
    assert report() == [], "fully received is not part received"


def test_a_receipt_row_carries_what_the_screen_shows() -> None:
    """The flat receipt row names the vendor and carries the header's totals.

    The pending and completed reports answered whole documents (D-RPT-16).
    """
    session = _session_factory()()
    fixture = _Fixture(session, "GRN-ROWS")
    service = GoodsReceiptService(session)
    payload = fixture.receipt_payload("4")
    payload.lines[0].damaged_quantity = Decimal("1")
    receipt = service.create_receipt(
        payload, firm_id=fixture.firm.id, actor_id=fixture.actor_id
    )

    [row] = service.register_rows(service.pending_receipts(firm_scope=fixture.firm.id))
    assert row.grn_number == receipt.grn_number
    assert row.vendor_name == fixture.vendor.display_name
    assert row.purchase_order_number == fixture.order.po_number
    assert (row.total_current_receipt_quantity, row.total_damaged_quantity) == (
        Decimal("4"),
        Decimal("1"),
    )
    assert row.status == "DRAFT"
    assert service.register_rows([]) == []
    assert row.receipt_id == receipt.id
