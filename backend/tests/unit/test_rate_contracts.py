"""Rate contracts with a supplier and the orders drawn on them (PG-9).

The firm agrees 100 widgets at 70 less 2% with its supplier for August and
September, above the supplier's price list at 80 less 10%. An order in August
takes the contract's terms and draws on it once approved; an order in October
takes the list again; cancelling an order gives its quantity back.
"""

# ruff: noqa: D103

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

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
from app.core.utils.dates import utc_now
from app.core.utils.pricing import LinePrice, resolve_supplier_unit_price
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.pricing.models import PriceList, PriceListItem
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.rate_contracts.api.router import list_rate_contracts, router
from app.rate_contracts.models import RateContract
from app.rate_contracts.schemas import RateContractCreate, RateContractUpdate
from app.rate_contracts.services import RateContractService
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal
TODAY = utc_now().date()
#: Dates relative to today, so a contract is in force or has expired however
#: long after it was written the suite runs.
START = TODAY - timedelta(days=10)
END = TODAY + timedelta(days=50)


@pytest.fixture
def firm() -> _Firm:
    """Build a firm with a supplier price list for its product."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="RC01")
    price_list = PriceList(
        firm_id=built.firm.id,
        code="SUP-LIST",
        name="Supplier list",
        vendor_id=built.vendor.id,
        effective_from=TODAY - timedelta(days=400),
    )
    built.session.add(price_list)
    built.session.flush()
    built.session.add(
        PriceListItem(
            price_list_id=price_list.id,
            firm_id=built.firm.id,
            product_id=built.product.id,
            discount_percent=D("10"),
            rate=D("80"),
        )
    )
    built.session.commit()
    return built


def _contract(
    firm: _Firm,
    *,
    valid_from: date = START,
    valid_to: date = END,
    quantity: str | None = "100",
    approve: bool = True,
) -> RateContract:
    service = RateContractService(firm.session)
    line: dict[str, object] = {
        "product_id": firm.product.id,
        "rate": "70",
        "discount_percent": "2",
    }
    if quantity is not None:
        line["contracted_quantity"] = quantity
    row = service.create(
        RateContractCreate.model_validate(
            {
                "vendor_id": firm.vendor.id,
                "valid_from": valid_from.isoformat(),
                "valid_to": valid_to.isoformat(),
                "reference": "SUP-AGREEMENT-7",
                "lines": [line],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    if approve:
        row = service.approve(row.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    return row


def _order(
    firm: _Firm,
    quantity: str = "40",
    *,
    on: date = TODAY,
    unit_price: str | None = None,
) -> PurchaseOrder:
    line: dict[str, object] = {
        "product_id": firm.product.id,
        "ordered_quantity": quantity,
    }
    if unit_price is not None:
        line["unit_price"] = unit_price
    return PurchaseService(firm.session).create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "vendor_id": firm.vendor.id,
                "purchase_date": on.isoformat(),
                "lines": [line],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _line(firm: _Firm, order: PurchaseOrder) -> PurchaseOrderLine:
    return firm.session.scalars(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    ).one()


def _approve(firm: _Firm, order: PurchaseOrder) -> PurchaseOrder:
    service = PurchaseService(firm.session)
    service.submit_order(order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    return service.approve_order(
        order.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )


def _drawn(firm: _Firm, contract: RateContract) -> tuple[Decimal, Decimal | None]:
    service = RateContractService(firm.session)
    (response,) = service.responses([service.get(contract.id, firm_id=firm.firm.id)])
    (line,) = response.lines
    return line.drawn_quantity, line.remaining_quantity


def test_the_contract_rate_is_taken_over_the_suppliers_price_list(
    firm: _Firm,
) -> None:
    contract = _contract(firm)
    # Its own prefix, not the customer receipt's RC (D-BUY-57).
    assert contract.contract_number.startswith("RTC-")
    line = _line(firm, _order(firm))
    assert (line.unit_price, line.discount_percent) == (D("70"), D("2"))
    assert line.rate_source == "RATE_CONTRACT"
    (contract_line,) = RateContractService(firm.session).responses([contract])[0].lines
    assert line.rate_contract_line_id == contract_line.id
    response = PurchaseService(firm.session).order_response(
        firm.session.get(PurchaseOrder, line.purchase_order_id)  # type: ignore[arg-type]
    )
    assert response.lines[0].rate_source == "RATE_CONTRACT"
    assert response.lines[0].rate_contract_line_id == contract_line.id


def test_without_a_contract_the_price_list_still_prices_the_line(
    firm: _Firm,
) -> None:
    _contract(firm, approve=False)  # a draft prices nothing
    line = _line(firm, _order(firm))
    assert (line.unit_price, line.discount_percent) == (D("80"), D("10"))
    assert line.rate_source == "PRICE_LIST"
    assert line.rate_contract_line_id is None


def test_a_contract_past_its_end_is_not_taken(firm: _Firm) -> None:
    contract = _contract(firm)
    # An order dated after the contract ends takes the list again.
    line = _line(firm, _order(firm, on=END + timedelta(days=1)))
    assert line.unit_price == D("80")
    assert line.rate_contract_line_id is None
    # A contract whose period has passed reads as expired, though nobody set it.
    contract.valid_to = TODAY - timedelta(days=1)
    firm.session.commit()
    service = RateContractService(firm.session)
    assert service.responses([contract])[0].status == "EXPIRED"
    assert contract.status == "ACTIVE"
    rows, total = service.page(
        firm.firm.id,
        vendor_id=firm.vendor.id,
        status="EXPIRED",
        search=None,
        page=1,
        page_size=20,
    )
    assert total == 1 and rows[0].id == contract.id
    assert _line(firm, _order(firm)).rate_source == "PRICE_LIST"


def test_drawn_quantity_is_derived_and_a_cancelled_release_gives_it_back(
    firm: _Firm,
) -> None:
    contract = _contract(firm)
    draft = _order(firm, "40")
    # A draft draws nothing.
    assert _drawn(firm, contract) == (D("0"), D("100"))
    _approve(firm, draft)
    assert _drawn(firm, contract) == (D("40"), D("60"))
    second = _approve(firm, _order(firm, "25"))
    assert _drawn(firm, contract) == (D("65"), D("35"))
    releases = RateContractService(firm.session).releases(
        contract.id, firm_id=firm.firm.id
    )
    assert [r.ordered_quantity for r in releases] == [D("40"), D("25")]
    assert all(r.counts_as_drawn for r in releases)

    PurchaseService(firm.session).cancel_order(
        second.id,
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
        reason="Supplier short",
    )
    assert _drawn(firm, contract) == (D("40"), D("60"))
    releases = RateContractService(firm.session).releases(
        contract.id, firm_id=firm.firm.id
    )
    assert [r.counts_as_drawn for r in releases] == [True, False]


def test_drawing_past_the_contracted_quantity_warns_and_does_not_refuse(
    firm: _Firm,
) -> None:
    contract = _contract(firm, quantity="50")
    _approve(firm, _order(firm, "40"))
    over = _order(firm, "30")
    service = PurchaseService(firm.session)
    # The draft already says so, counting itself.
    warning = service.order_response(over).rate_contract_warning
    assert warning is not None
    assert contract.contract_number in warning
    assert "70 drawn of 50 contracted" in warning
    approved = _approve(firm, over)
    assert approved.status == "APPROVED"
    after = service.order_response(approved).rate_contract_warning or ""
    assert "70 drawn of 50" in after
    assert _drawn(firm, contract) == (D("70"), D("0"))


def test_a_contract_with_no_quantity_never_warns(firm: _Firm) -> None:
    _contract(firm, quantity=None)
    order = _approve(firm, _order(firm, "5000"))
    response = PurchaseService(firm.session).order_response(order)
    assert response.rate_contract_warning is None


def test_an_overlapping_activation_is_refused(firm: _Firm) -> None:
    first = _contract(firm)
    second = _contract(
        firm,
        valid_from=END - timedelta(days=5),
        valid_to=END + timedelta(days=30),
        approve=False,
    )
    service = RateContractService(firm.session)
    with pytest.raises(ValidationError, match=first.contract_number):
        service.approve(second.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    firm.session.rollback()
    # Once the first ends, the next can start.
    service.close(first.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    assert (
        service.approve(second.id, firm_id=firm.firm.id, actor_id=firm.actor_id).status
        == "ACTIVE"
    )


def test_a_typed_rate_still_wins_and_an_echo_keeps_the_contract(
    firm: _Firm,
) -> None:
    _contract(firm)
    typed = _line(firm, _order(firm, unit_price="65"))
    assert typed.unit_price == D("65")
    assert typed.rate_source == "TYPED"
    assert typed.rate_contract_line_id is None
    # A client re-saving the rate it was shown stays on the contract.
    echoed = _line(firm, _order(firm, unit_price="70.0000"))
    assert echoed.rate_source == "RATE_CONTRACT"
    assert echoed.rate_contract_line_id is not None


def test_a_contract_line_needs_a_rate_above_nothing(firm: _Firm) -> None:
    """D-BUY-53: a contract at 0 approved and priced order lines at 0.0000."""
    body = {
        "vendor_id": str(firm.vendor.id),
        "valid_from": START.isoformat(),
        "valid_to": END.isoformat(),
        "lines": [{"product_id": str(firm.product.id), "rate": "0"}],
    }
    with pytest.raises(PydanticValidationError) as refusal:
        RateContractCreate.model_validate(body)
    assert "A rate contract line needs a rate above 0" in str(refusal.value)
    body["lines"] = [{"product_id": str(firm.product.id), "rate": "0.01"}]
    assert RateContractCreate.model_validate(body).lines[0].rate == D("0.01")


def test_the_supplier_ranking_lives_in_the_pricing_module() -> None:
    def fallback() -> LinePrice:
        return LinePrice(price=D("40"), source="PRODUCT")

    assert resolve_supplier_unit_price(
        typed=None, contract_rate=D("70"), list_rate=D("80"), fallback=fallback
    ) == LinePrice(price=D("70"), source="RATE_CONTRACT")
    assert resolve_supplier_unit_price(
        typed=None, list_rate=D("80"), catalogue_rate=D("75"), fallback=fallback
    ) == LinePrice(price=D("80"), source="PRICE_LIST")
    assert resolve_supplier_unit_price(
        typed=None, catalogue_rate=D("75"), fallback=fallback
    ) == LinePrice(price=D("75"), source="CATALOGUE")
    assert resolve_supplier_unit_price(typed=None, fallback=fallback) == LinePrice(
        price=D("40"), source="PRODUCT"
    )
    assert resolve_supplier_unit_price(
        typed=D("0"), contract_rate=D("70"), fallback=fallback
    ) == LinePrice(price=D("0"), source="TYPED")


def test_only_a_draft_is_changed_and_status_moves_only_by_transition(
    firm: _Firm,
) -> None:
    service = RateContractService(firm.session)
    draft = _contract(firm, approve=False)
    with pytest.raises(Exception, match="extra"):
        RateContractUpdate.model_validate({"status": "ACTIVE"})
    changed = service.update(
        draft.id,
        RateContractUpdate(notes="Renegotiated"),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert changed.notes == "Renegotiated"
    assert changed.reference == "SUP-AGREEMENT-7"  # left out, left alone
    with pytest.raises(ValidationError, match="before valid_from"):
        service.update(
            draft.id,
            RateContractUpdate(valid_to=START - timedelta(days=1)),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()
    service.approve(draft.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    with pytest.raises(ValidationError, match="Only a draft"):
        service.update(
            draft.id,
            RateContractUpdate(notes="x"),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()
    cancelled = service.cancel(
        draft.id, "Supplier withdrew", firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert cancelled.status == "CANCELLED"
    with pytest.raises(ValidationError, match="cannot be cancelled"):
        service.cancel(draft.id, "again", firm_id=firm.firm.id, actor_id=firm.actor_id)


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
    base = "/api/v1/rate-contracts"
    assert routes[("GET", base)] == {"RATE_CONTRACT_VIEW"}
    assert routes[("GET", base + "/{contract_id}")] == {"RATE_CONTRACT_VIEW"}
    assert routes[("GET", base + "/{contract_id}/releases")] == {"RATE_CONTRACT_VIEW"}
    assert routes[("POST", base)] == {"RATE_CONTRACT_MANAGE"}
    assert routes[("PUT", base + "/{contract_id}")] == {"RATE_CONTRACT_MANAGE"}
    assert routes[("DELETE", base + "/{contract_id}")] == {"RATE_CONTRACT_MANAGE"}
    assert routes[("POST", base + "/{contract_id}/close")] == {"RATE_CONTRACT_MANAGE"}
    assert routes[("POST", base + "/{contract_id}/cancel")] == {"RATE_CONTRACT_MANAGE"}
    assert routes[("POST", base + "/{contract_id}/approve")] == {"PURCHASE_APPROVE"}
    for role in ("PURCHASE_EXECUTIVE", "PURCHASE_MANAGER", "FIRM_ADMIN"):
        assert {"RATE_CONTRACT_VIEW", "RATE_CONTRACT_MANAGE"} <= (
            ROLE_PERMISSION_CODES[role]
        ), role
    for role in ("ACCOUNTANT", "SALES_MANAGER"):
        assert "RATE_CONTRACT_MANAGE" not in ROLE_PERMISSION_CODES[role], role


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
    for _ in range(extra):
        _contract(firm, approve=False)
    firm.session.expunge_all()
    with _counting(firm.session) as seen:
        page = list_rate_contracts(
            scope=_scope(firm.firm.id),
            page=1,
            page_size=50,
            search=None,
            status_filter=None,
            vendor_id=None,
            db=firm.session,
        )
    assert page.data
    return len(seen)


def test_the_list_costs_the_same_at_any_length(firm: _Firm) -> None:
    small = _page_statements(firm, 3)
    large = _page_statements(firm, 9)
    assert large <= small, f"{small} statements at 3 rows, {large} at 12"
