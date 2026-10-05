"""Requests for quotation and the quote comparison (PG-8, backlog 86 #1).

A buyer asks two suppliers for widgets and gadgets. Supplier one is cheaper
on widgets once its discount is taken, supplier two on nothing; the buyer
takes supplier two's widgets anyway, for its lead time, and says so, and
supplier one's gadgets at the lowest rate. Raising orders makes one draft
order per supplier at the quoted rate and discount and closes the RFQ.
"""

# ruff: noqa: D103

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.scope import ResolvedFirmScope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.products.models import Product
from app.purchase.models import PurchaseOrderLine
from app.purchase.schemas.requisition import PurchaseRequisitionWrite
from app.purchase.services.requisitions import PurchaseRequisitionService
from app.rfq.api.router import list_rfqs, router
from app.rfq.models import Rfq
from app.rfq.schemas import (
    RfqCreate,
    RfqSelectionsWrite,
    RfqUpdate,
    SupplierQuotationWrite,
)
from app.rfq.services import RfqService
from app.vendors.models import Vendor
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm with one branch, warehouse, supplier and product."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="RFQ01")


def _product(firm: _Firm, code: str) -> Product:
    row = Product(
        firm_id=firm.firm.id,
        code=code,
        name=code.title(),
        product_type="STOCK_ITEM",
        status="ACTIVE",
        purchase_price=D("40"),
    )
    firm.session.add(row)
    firm.session.commit()
    return row


def _vendor(firm: _Firm, code: str) -> Vendor:
    row = Vendor(
        firm_id=firm.firm.id,
        code=code,
        name=code.title(),
        display_name=code.title(),
        status="ACTIVE",
    )
    firm.session.add(row)
    firm.session.commit()
    return row


def _draft(firm: _Firm, products: list[Product], vendors: list[Vendor]) -> Rfq:
    return RfqService(firm.session).create(
        RfqCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "rfq_date": "2026-08-02",
                "required_by": "2026-08-20",
                "lines": [
                    {"product_id": p.id, "quantity": str(10 * (i + 1))}
                    for i, p in enumerate(products)
                ],
                "vendor_ids": [v.id for v in vendors],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _quote(
    firm: _Firm, rfq: Rfq, vendor: Vendor, rates: list[tuple[str, str, int]]
) -> None:
    service = RfqService(firm.session)
    (response,) = service.responses([service.get(rfq.id, firm_id=firm.firm.id)])
    service.save_quotation(
        rfq.id,
        vendor.id,
        SupplierQuotationWrite.model_validate(
            {
                "quote_ref": f"Q-{vendor.code}",
                "quote_date": "2026-08-04",
                "valid_until": "2026-09-04",
                "lines": [
                    {
                        "rfq_line_id": line.id,
                        "rate": rate,
                        "discount_percent": discount,
                        "lead_time_days": lead,
                    }
                    for line, (rate, discount, lead) in zip(
                        response.lines, rates, strict=True
                    )
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _sent_with_quotes(firm: _Firm) -> tuple[Rfq, Vendor, Vendor, Product]:
    """Send an RFQ for widgets and gadgets to two suppliers, who quote."""
    gadget = _product(firm, "GADGET")
    one = firm.vendor
    two = _vendor(firm, "SUP-TWO")
    rfq = _draft(firm, [firm.product, gadget], [one])
    service = RfqService(firm.session)
    service.update(
        rfq.id,
        RfqUpdate(vendor_ids=[one.id, two.id]),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.send(rfq.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    # Widget: 100 less 10% = 90 from one, 95 from two (faster).
    # Gadget: 40 less 10% = 36 from one, 38 from two.
    _quote(firm, rfq, one, [("100", "10", 10), ("40", "10", 7)])
    _quote(firm, rfq, two, [("95", "0", 2), ("38", "0", 3)])
    return rfq, one, two, gadget


def test_the_whole_flow_raises_one_order_per_chosen_supplier(firm: _Firm) -> None:
    rfq, one, two, gadget = _sent_with_quotes(firm)
    service = RfqService(firm.session)
    assert rfq.rfq_number.startswith("RFQ")

    comparison = service.comparison(rfq.id, firm_id=firm.firm.id)
    widget_line, gadget_line = comparison.lines
    assert [q.vendor_id for q in widget_line.quotes] == [one.id, two.id]
    assert widget_line.quotes[0].landed_rate == D("90.0000")
    assert widget_line.quotes[0].is_lowest
    assert not widget_line.quotes[1].is_lowest
    assert (
        widget_line.lowest_quotation_line_id == widget_line.quotes[0].quotation_line_id
    )
    assert gadget_line.quotes[0].vendor_id == one.id
    assert gadget_line.quotes[0].landed_rate == D("36.0000")

    widget_from_two = widget_line.quotes[1].quotation_line_id
    gadget_from_one = gadget_line.quotes[0].quotation_line_id
    with pytest.raises(ValidationError, match="Line 1: say why"):
        service.set_selections(
            rfq.id,
            RfqSelectionsWrite.model_validate(
                {
                    "selections": [
                        {
                            "rfq_line_id": widget_line.rfq_line_id,
                            "quotation_line_id": widget_from_two,
                        }
                    ]
                }
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()
    service.set_selections(
        rfq.id,
        RfqSelectionsWrite.model_validate(
            {
                "selections": [
                    {
                        "rfq_line_id": widget_line.rfq_line_id,
                        "quotation_line_id": widget_from_two,
                        "reason": "Delivers in two days",
                    },
                    {
                        "rfq_line_id": gadget_line.rfq_line_id,
                        "quotation_line_id": gadget_from_one,
                    },
                ]
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    chosen = service.comparison(rfq.id, firm_id=firm.firm.id)
    assert chosen.lines[0].selected_quotation_line_id == widget_from_two
    assert chosen.lines[0].selection_reason == "Delivers in two days"
    assert chosen.lines[1].selection_reason is None

    orders = service.raise_orders(rfq.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    assert sorted(o.vendor_id for o in orders) == sorted([one.id, two.id])
    assert all(o.status == "DRAFT" for o in orders)
    assert all(o.reference_number == rfq.rfq_number for o in orders)
    by_vendor = {o.vendor_id: o for o in orders}
    lines = {
        line.purchase_order_id: line
        for line in firm.session.scalars(select(PurchaseOrderLine)).all()
    }
    widget_order_line = lines[by_vendor[two.id].id]
    assert widget_order_line.product_id == firm.product.id
    assert widget_order_line.unit_price == D("95")
    assert widget_order_line.discount_percent == D("0")
    gadget_order_line = lines[by_vendor[one.id].id]
    assert gadget_order_line.product_id == gadget.id
    assert gadget_order_line.unit_price == D("40")
    assert gadget_order_line.discount_percent == D("10")
    assert by_vendor[one.id].external_reference == f"Q-{one.code}"

    (response,) = service.responses([service.get(rfq.id, firm_id=firm.firm.id)])
    assert response.status == "CLOSED"
    assert {s.vendor_id: s.purchase_order_id for s in response.suppliers} == {
        one.id: by_vendor[one.id].id,
        two.id: by_vendor[two.id].id,
    }
    # A closed RFQ takes no more quotations.
    with pytest.raises(ValidationError, match="closed RFQ takes no quotations"):
        _quote(firm, rfq, one, [("1", "0", 1), ("1", "0", 1)])


def test_lines_and_suppliers_are_fixed_once_sent(firm: _Firm) -> None:
    rfq = _draft(firm, [firm.product], [firm.vendor])
    service = RfqService(firm.session)
    with pytest.raises(ValidationError, match="Only a sent RFQ"):
        service.close(rfq.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    service.update(
        rfq.id,
        RfqUpdate(notes="Urgent"),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    (response,) = service.responses([service.get(rfq.id, firm_id=firm.firm.id)])
    # A field left out is left alone.
    assert response.notes == "Urgent"
    assert len(response.lines) == 1
    assert len(response.suppliers) == 1
    service.send(rfq.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    with pytest.raises(ValidationError, match="Only a draft RFQ can be changed"):
        service.update(
            rfq.id,
            RfqUpdate(vendor_ids=[]),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_a_quote_from_a_supplier_not_invited_is_refused(firm: _Firm) -> None:
    rfq = _draft(firm, [firm.product], [firm.vendor])
    stranger = _vendor(firm, "STRANGER")
    with pytest.raises(ValidationError, match="draft RFQ takes no quotations"):
        _quote(firm, rfq, firm.vendor, [("10", "0", 1)])
    RfqService(firm.session).send(rfq.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    with pytest.raises(ValidationError, match="was not invited"):
        _quote(firm, rfq, stranger, [("10", "0", 1)])


def test_nothing_chosen_raises_nothing(firm: _Firm) -> None:
    rfq, *_ = _sent_with_quotes(firm)
    with pytest.raises(ValidationError, match="Choose a quote"):
        RfqService(firm.session).raise_orders(
            rfq.id, firm_id=firm.firm.id, actor_id=firm.actor_id
        )


def test_an_rfq_starts_from_an_approved_requisition(firm: _Firm) -> None:
    firm.product.preferred_vendor_id = firm.vendor.id
    firm.session.commit()
    requisitions = PurchaseRequisitionService(firm.session)
    requisition = requisitions.create(
        PurchaseRequisitionWrite.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "requisition_date": "2026-08-02",
                "lines": [{"product_id": firm.product.id, "quantity": "7"}],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service = RfqService(firm.session)
    with pytest.raises(ValidationError, match="approved requisition"):
        service.create_from_requisition(
            requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id
        )
    requisitions.submit(requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    requisitions.approve(requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    rfq = service.create_from_requisition(
        requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    (response,) = service.responses([rfq])
    assert response.source_requisition_id == requisition.id
    assert response.lines[0].quantity == D("7.0000")
    assert [s.vendor_id for s in response.suppliers] == [firm.vendor.id]
    with pytest.raises(ValidationError, match="already started"):
        service.create_from_requisition(
            requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id
        )


def _codes(route: APIRoute) -> set[str]:
    """Return every permission code a route's dependencies enforce."""
    found: set[str] = set()
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        code = getattr(dependency.call, "permission_code", None)
        if code:
            found.add(code)
        pending.extend(dependency.dependencies)
    return found


def test_permissions() -> None:
    routes = {
        (method, route.path): _codes(route)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    assert routes[("GET", "/api/v1/rfqs")] == {"RFQ_VIEW"}
    assert routes[("GET", "/api/v1/rfqs/{rfq_id}/comparison")] == {"RFQ_VIEW"}
    assert routes[("POST", "/api/v1/rfqs")] == {"RFQ_MANAGE"}
    assert routes[("PUT", "/api/v1/rfqs/{rfq_id}/selections")] == {"RFQ_MANAGE"}
    assert routes[("POST", "/api/v1/rfqs/{rfq_id}/raise-orders")] == {
        "RFQ_MANAGE",
        "PURCHASE_CREATE",
    }
    assert all(codes for codes in routes.values())
    for role in ("PURCHASE_EXECUTIVE", "PURCHASE_MANAGER", "FIRM_ADMIN"):
        assert {"RFQ_VIEW", "RFQ_MANAGE", "PURCHASE_CREATE"} <= ROLE_PERMISSION_CODES[
            role
        ], role
    for role in ("ACCOUNTANT", "INVENTORY_MANAGER", "SALES_MANAGER"):
        assert "RFQ_MANAGE" not in ROLE_PERMISSION_CODES[role], role


def _scope(firm_id: UUID) -> ResolvedFirmScope:
    user_id = uuid.uuid4()
    principal = Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(),
        claims=TokenClaims(
            sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
    )
    return ResolvedFirmScope(principal=principal, firm_id=firm_id)


@contextmanager
def _counting(session: Session) -> Iterator[list[str]]:
    seen: list[str] = []

    def record(*args: Any) -> None:  # noqa: ANN401
        seen.append(args[2])

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _page_statements(firm: _Firm, extra: int) -> int:
    gadget = firm.session.scalar(select(Product).where(Product.code == "GADGET"))
    for _ in range(extra):
        _draft(firm, [firm.product, gadget], [firm.vendor])  # type: ignore[list-item]
    firm.session.expunge_all()
    with _counting(firm.session) as seen:
        page = list_rfqs(
            scope=_scope(firm.firm.id),
            page=1,
            page_size=50,
            search=None,
            status_filter=None,
            db=firm.session,
        )
    assert page.data
    return len(seen)


def test_the_list_costs_the_same_at_any_length(firm: _Firm) -> None:
    _product(firm, "GADGET")
    small = _page_statements(firm, 3)
    large = _page_statements(firm, 9)
    assert large <= small, f"{small} statements at 3 rows, {large} at 12"


def test_a_quote_needs_a_rate_above_nothing() -> None:
    """D-BUY-53: a quote at 0 was accepted, and would win every comparison."""
    body = {
        "quote_date": "2026-08-04",
        "lines": [{"rfq_line_id": str(uuid4()), "rate": "0"}],
    }
    with pytest.raises(PydanticValidationError) as refusal:
        SupplierQuotationWrite.model_validate(body)
    assert "A quoted rate is above 0" in str(refusal.value)
    body["lines"][0]["rate"] = "12.50"  # type: ignore[index]
    assert SupplierQuotationWrite.model_validate(body).lines[0].rate == Decimal("12.50")
