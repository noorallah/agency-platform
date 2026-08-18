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
from sqlalchemy import create_engine, select
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
from app.core.exceptions import AuthorizationError, ResourceNotFoundError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import customer as _customer_models  # noqa: F401
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptCreate
from app.goods_receipt.services import GoodsReceiptService
from app.identity.models import UserFirm
from app.inventory.models import InventoryRecord, InventoryTransaction
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.sales.models import territory as _sales_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import uom as _uom_models  # noqa: F401
from app.vendors.models import Vendor


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
        """Raise the order the receipts are taken against."""
        return PurchaseService(self.session).create_order(
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
    """Walk the order to APPROVED, which is where receiving begins."""
    service = PurchaseService(fixture.session)
    service.submit_order(
        fixture.order.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    service.approve_order(
        fixture.order.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )


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
