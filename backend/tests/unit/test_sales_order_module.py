"""Sales order backend lifecycle and reservation tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.branches.models import Branch, Warehouse
from app.business.models import framework as _business_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.concurrency import parse_if_match
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ConflictError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import Customer
from app.document_framework.models import DocumentTypeDefinition
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import InventoryTransaction
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import Product
from app.sales.models import GeoCountry
from app.sales.models import territory as _sales_models  # noqa: F401
from app.sales_order.api.router import update_sales_order
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import (
    SalesOrderCreate,
    SalesOrderLineWrite,
    SalesOrderStatus,
)
from app.sales_order.services import SalesOrderService
from app.tax.models import TaxComponent, TaxProfile, TaxProfileComponent, TaxSystem
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import uom as _uom_models  # noqa: F401


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    """Build a principal holding the given permissions."""
    return Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
    )


def _firm(session: Session) -> Firm:
    row = Firm(
        name="Sales Firm",
        code="SAL-FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _branch(session: Session, *, firm_id: UUID) -> Branch:
    row = Branch(
        firm_id=firm_id,
        code="BR-001",
        name="Branch BR-001",
        display_name="Branch BR-001",
        currency_code="INR",
        working_hours={"start": "09:00", "end": "18:00"},
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _warehouse(session: Session, *, firm_id: UUID, branch_id: UUID) -> Warehouse:
    row = Warehouse(
        firm_id=firm_id,
        branch_id=branch_id,
        code="WH-001",
        name="Warehouse WH-001",
        display_name="Warehouse WH-001",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _customer(session: Session, *, firm_id: UUID) -> Customer:
    row = Customer(
        firm_id=firm_id,
        code="CUS-001",
        customer_type="RETAIL",
        name="Customer CUS-001",
        display_name="Customer CUS-001",
        currency_code="INR",
        status="ACTIVE",
        credit_limit=Decimal("50000"),
        opening_balance=Decimal("1000"),
    )
    session.add(row)
    session.commit()
    return row


def _product(session: Session, *, firm_id: UUID) -> Product:
    row = Product(
        firm_id=firm_id,
        code="SKU-001",
        name="Product SKU-001",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def test_sales_order_creates_lifecycle_and_reservation() -> None:
    """Approving an order reserves the stock it promised.

    Stock that is promised twice is stock that gets dispatched once and
    apologised for once.
    """
    session_factory = _session_factory()
    session = session_factory()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)

    service = SalesOrderService(session)
    row = service.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    response = service.order_response(row)
    assert response.status == SalesOrderStatus.DRAFT
    assert response.order_number.startswith("SO")
    assert response.grand_total == Decimal("400.0000")
    assert (
        session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.firm_id == firm.id,
                DocumentTypeDefinition.code == "SALES_ORDER",
            )
        )
        is not None
    )
    assert session.scalar(select(SalesOrder).where(SalesOrder.id == row.id)) is not None

    approved = service.approve_order(row.id, firm_scope=firm.id, actor_id=uuid4())
    assert approved.status == SalesOrderStatus.APPROVED.value
    reservation = session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.reference_type == "SALES_ORDER",
            InventoryTransaction.reference_number == approved.order_number,
            InventoryTransaction.transaction_type == "RESERVE",
        )
    )
    assert reservation is not None
    assert reservation.reserved_quantity_delta == Decimal("4.0000")
    assert service.summary(firm_scope=firm.id).total == 1
    assert session.scalar(select(AuditLog.id)) is not None


def _tax_group(
    session: Session, *, firm_id: UUID, percent: str, starts: date, ends: date | None
) -> TaxProfile:
    """Create one version of a GST_STANDARD rate, snapshotting its percentage."""
    country = session.scalar(select(GeoCountry).where(GeoCountry.code == "IN"))
    if country is None:
        country = GeoCountry(
            code="IN", name="India", iso2="IN", iso3="IND", phone_code="+91"
        )
        session.add(country)
        session.flush()
    system = session.scalar(select(TaxSystem).where(TaxSystem.firm_id == firm_id))
    if system is None:
        system = TaxSystem(
            firm_id=firm_id,
            country_id=country.id,
            code="GST",
            name="GST",
            display_name="GST",
            status="ACTIVE",
        )
        session.add(system)
        session.flush()
    component = TaxComponent(
        firm_id=firm_id,
        tax_system_id=system.id,
        code=f"GST_{percent}",
        name=f"GST {percent}",
        label=f"GST {percent}",
        percentage=Decimal(percent),
        calculation_order=1,
        status="ACTIVE",
    )
    session.add(component)
    session.flush()
    profile = TaxProfile(
        firm_id=firm_id,
        tax_system_id=system.id,
        code=f"GST_{percent}",
        name=f"GST {percent}",
        label=f"GST {percent}",
        status="ACTIVE",
        group_code="GST_STANDARD",
        effective_from=starts,
        effective_to=ends,
    )
    profile.components = [
        TaxProfileComponent(
            firm_id=firm_id,
            tax_component_id=component.id,
            label=f"GST {percent}",
            percentage=Decimal(percent),
            calculation_order=1,
            included_in_price=False,
            recoverable=False,
        )
    ]
    session.add(profile)
    session.commit()
    return profile


def test_a_sales_order_takes_the_rate_in_force_on_its_own_date() -> None:
    """A line without an explicit profile resolves the rate from the order date.

    The product names a tax group, not a version, so a back-dated order keeps the
    rate that applied when it was placed and a rate change needs no product edit.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    product.tax_profile_group_code = "GST_STANDARD"
    session.commit()

    _tax_group(
        session,
        firm_id=firm.id,
        percent="5",
        starts=date(2020, 1, 1),
        ends=date(2026, 3, 31),
    )
    _tax_group(
        session, firm_id=firm.id, percent="8", starts=date(2026, 4, 1), ends=None
    )

    service = SalesOrderService(session)

    def _total(order_date: date) -> Decimal:
        row = service.create_order(
            SalesOrderCreate(
                customer_id=customer.id,
                branch_id=branch.id,
                warehouse_id=warehouse.id,
                order_date=order_date,
                lines=[
                    SalesOrderLineWrite(
                        line_number=1,
                        product_id=product.id,
                        quantity=Decimal("1"),
                        unit_price=Decimal("100"),
                    )
                ],
            ),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
        return service.order_response(row).tax_total

    assert _total(date(2026, 3, 1)) == Decimal("5.0000"), "the old rate still applies"
    assert _total(date(2026, 6, 1)) == Decimal("8.0000"), "the new rate takes over"


def test_editing_a_sales_order_keeps_its_line_identities() -> None:
    """Line ids survive an edit, and dropped lines are removed.

    Lines used to be deleted and re-inserted on every save, minting a new UUID
    each time. Delivery notes and sales invoices record source_document_line_id
    as a bare UUID with no foreign key, so every downstream reference to an
    edited order silently pointed at a row that no longer existed.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    first = _product(session, firm_id=firm.id)
    second = Product(
        firm_id=firm.id,
        code="SKU-002",
        name="Product SKU-002",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(second)
    session.commit()

    service = SalesOrderService(session)

    def _payload(quantity: str, include_second: bool) -> SalesOrderCreate:
        lines = [
            SalesOrderLineWrite(
                line_number=1,
                product_id=first.id,
                quantity=Decimal(quantity),
                unit_price=Decimal("100"),
            )
        ]
        if include_second:
            lines.append(
                SalesOrderLineWrite(
                    line_number=2,
                    product_id=second.id,
                    quantity=Decimal("2"),
                    unit_price=Decimal("50"),
                )
            )
        return SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=lines,
        )

    order = service.create_order(
        _payload("4", include_second=True), firm_id=firm.id, actor_id=uuid4()
    )
    before = {
        line.line_number: line.id
        for line in session.scalars(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
        ).all()
    }
    assert len(before) == 2

    service.update_order(
        order.id,
        _payload("9", include_second=True),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    after = {
        line.line_number: (line.id, line.quantity)
        for line in session.scalars(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
        ).all()
    }
    assert after[1][0] == before[1], "line 1 must keep its identity across an edit"
    assert after[2][0] == before[2], "line 2 must keep its identity across an edit"
    assert after[1][1] == Decimal("9.0000"), "the edit must still apply"

    # Dropping a line removes it rather than leaving an orphan.
    service.update_order(
        order.id,
        _payload("9", include_second=False),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    remaining = session.scalars(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    ).all()
    assert [line.line_number for line in remaining] == [1]
    assert remaining[0].id == before[1]


def test_update_rejects_a_stale_if_match_version() -> None:
    """An edit aimed at a superseded version is refused, not silently applied.

    BaseEntity carried a version column from the start that nothing incremented
    or checked, so concurrent edits were last-writer-wins — and because an update
    rebuilt the whole line collection, the loser lost every line they entered.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    scope = ResolvedFirmScope(
        principal=_principal(uuid4(), {"SALES_VIEW", "SALES_UPDATE"}),
        firm_id=firm.id,
    )

    def _payload(quantity: str) -> SalesOrderCreate:
        return SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal(quantity),
                    unit_price=Decimal("100"),
                )
            ],
        )

    service = SalesOrderService(session)
    order = service.create_order(_payload("4"), firm_id=firm.id, actor_id=uuid4())
    loaded_version = order.version

    # No precondition: accepted, so existing clients keep working.
    update_sales_order(order_id=order.id, data=_payload("5"), scope=scope, db=session)
    bumped = service.get_order(order.id, firm_scope=firm.id).version
    assert bumped > loaded_version, "an update must advance the version"

    # The version we first read is now stale.
    with pytest.raises(ConflictError):
        update_sales_order(
            order_id=order.id,
            data=_payload("6"),
            scope=scope,
            db=session,
            expected_version=loaded_version,
        )

    # The current version is accepted.
    update_sales_order(
        order_id=order.id,
        data=_payload("7"),
        scope=scope,
        db=session,
        expected_version=bumped,
    )
    final = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert final is not None
    assert final.quantity == Decimal("7.0000")


def test_if_match_header_parsing() -> None:
    """A quoted ETag, a bare version, and * are all understood."""
    assert parse_if_match(None) is None
    assert parse_if_match("*") is None
    assert parse_if_match("3") == 3
    assert parse_if_match('"7"') == 7
    with pytest.raises(ValidationError):
        parse_if_match("not-a-version")
