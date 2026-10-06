"""What a price list promises, and where it sits in the precedence.

A product carries one `selling_price` and a customer can be put on one blanket
rate. A price list is the arrangement between those two: this customer, or
everyone on this round, on this product, from this date.

The ordering is the thing worth testing. A typed figure beats a table, because
a person deciding beats a rule; a list beats the blanket rate, because it is
the more specific arrangement; and the most specific list wins among lists.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Every model is registered by `tests/conftest.py`, which imports
# `all_models` -- so `create_all` below sees the whole schema without this
# file listing it.
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.core.utils.pricing import resolve_line_discount
from app.customers.models import Customer
from app.pricing.models import PriceList, PriceListItem
from app.pricing.schemas import PriceListWrite
from app.pricing.services.price_list_crud import PriceListService
from app.pricing.services.price_list_service import PriceListResolver
from app.products.models import Product

TODAY = date(2026, 8, 23)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _product(session: Session, firm_id: UUID, code: str = "SKU-1") -> Product:
    row = Product(
        firm_id=firm_id,
        code=code,
        name=f"Product {code}",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _customer(session: Session, firm_id: UUID) -> Customer:
    row = Customer(
        firm_id=firm_id,
        code="CUS-1",
        customer_type="RETAIL",
        name="Anand Agencies",
        display_name="Anand Agencies",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _list(
    session: Session,
    *,
    firm_id: UUID,
    code: str,
    product_id: UUID,
    percent: str,
    customer_id: UUID | None = None,
    territory_id: UUID | None = None,
    effective_from: date = date(2026, 1, 1),
    effective_to: date | None = None,
    status: str = "ACTIVE",
) -> PriceList:
    """Create one list holding one product's rate."""
    row = PriceList(
        firm_id=firm_id,
        code=code,
        name=code.title(),
        customer_id=customer_id,
        territory_id=territory_id,
        effective_from=effective_from,
        effective_to=effective_to,
        status=status,
    )
    session.add(row)
    session.flush()
    session.add(
        PriceListItem(
            price_list_id=row.id,
            firm_id=firm_id,
            product_id=product_id,
            discount_percent=Decimal(percent),
        )
    )
    session.commit()
    return row


def test_a_firm_wide_list_reaches_a_document_naming_nobody() -> None:
    """The standing arrangement applies even with no customer on the document."""
    session = _session()
    firm_id = uuid4()
    product = _product(session, firm_id)
    _list(session, firm_id=firm_id, code="STANDARD", product_id=product.id, percent="5")

    resolver = PriceListResolver(
        session, firm_id=firm_id, customer_id=None, territory_id=None, on=TODAY
    )

    assert resolver.rate_for(product.id) == Decimal("5")


def test_a_customer_list_beats_the_firm_wide_one() -> None:
    """The most specific arrangement wins."""
    session = _session()
    firm_id = uuid4()
    product = _product(session, firm_id)
    customer = _customer(session, firm_id)
    _list(session, firm_id=firm_id, code="STANDARD", product_id=product.id, percent="5")
    _list(
        session,
        firm_id=firm_id,
        code="ANAND",
        product_id=product.id,
        percent="12",
        customer_id=customer.id,
    )

    resolver = PriceListResolver(
        session, firm_id=firm_id, customer_id=customer.id, territory_id=None, on=TODAY
    )

    assert resolver.rate_for(product.id) == Decimal("12")


def test_a_customer_list_beats_a_territory_one() -> None:
    """Customer over route, route over firm — three rungs, tested at the top."""
    session = _session()
    firm_id = uuid4()
    territory_id = uuid4()
    product = _product(session, firm_id)
    customer = _customer(session, firm_id)
    _list(
        session,
        firm_id=firm_id,
        code="ROUTE",
        product_id=product.id,
        percent="8",
        territory_id=territory_id,
    )
    _list(
        session,
        firm_id=firm_id,
        code="ANAND",
        product_id=product.id,
        percent="12",
        customer_id=customer.id,
    )

    resolver = PriceListResolver(
        session,
        firm_id=firm_id,
        customer_id=customer.id,
        territory_id=territory_id,
        on=TODAY,
    )

    assert resolver.rate_for(product.id) == Decimal("12")


def test_a_territory_list_applies_when_the_customer_has_none() -> None:
    """The middle rung, which is the one an off-by-one would skip."""
    session = _session()
    firm_id = uuid4()
    territory_id = uuid4()
    product = _product(session, firm_id)
    customer = _customer(session, firm_id)
    _list(session, firm_id=firm_id, code="STANDARD", product_id=product.id, percent="5")
    _list(
        session,
        firm_id=firm_id,
        code="ROUTE",
        product_id=product.id,
        percent="8",
        territory_id=territory_id,
    )

    resolver = PriceListResolver(
        session,
        firm_id=firm_id,
        customer_id=customer.id,
        territory_id=territory_id,
        on=TODAY,
    )

    assert resolver.rate_for(product.id) == Decimal("8")


def test_a_list_outside_its_window_does_not_apply() -> None:
    """A rate agreed for last season must not price today's document."""
    session = _session()
    firm_id = uuid4()
    product = _product(session, firm_id)
    _list(
        session,
        firm_id=firm_id,
        code="DIWALI",
        product_id=product.id,
        percent="20",
        effective_from=date(2025, 10, 1),
        effective_to=date(2025, 11, 30),
    )

    resolver = PriceListResolver(
        session, firm_id=firm_id, customer_id=None, territory_id=None, on=TODAY
    )

    assert resolver.rate_for(product.id) is None


def test_an_inactive_list_does_not_apply() -> None:
    """Switched off is switched off, without having to be dated."""
    session = _session()
    firm_id = uuid4()
    product = _product(session, firm_id)
    _list(
        session,
        firm_id=firm_id,
        code="OLD",
        product_id=product.id,
        percent="20",
        status="INACTIVE",
    )

    resolver = PriceListResolver(
        session, firm_id=firm_id, customer_id=None, territory_id=None, on=TODAY
    )

    assert resolver.rate_for(product.id) is None


def test_a_product_no_list_mentions_gets_nothing_from_one() -> None:
    """None, not zero -- which is what lets the blanket rate still apply."""
    session = _session()
    firm_id = uuid4()
    listed = _product(session, firm_id, code="SKU-1")
    other = _product(session, firm_id, code="SKU-2")
    _list(session, firm_id=firm_id, code="STANDARD", product_id=listed.id, percent="5")

    resolver = PriceListResolver(
        session, firm_id=firm_id, customer_id=None, territory_id=None, on=TODAY
    )

    assert resolver.rate_for(other.id) is None


def test_a_list_stops_at_the_firm_boundary() -> None:
    """Another firm's arrangement is none of this one's business."""
    session = _session()
    mine = uuid4()
    theirs = uuid4()
    product = _product(session, theirs)
    _list(session, firm_id=theirs, code="STANDARD", product_id=product.id, percent="5")

    resolver = PriceListResolver(
        session, firm_id=mine, customer_id=None, territory_id=None, on=TODAY
    )

    assert resolver.rate_for(product.id) is None


# ---- where it sits in the precedence ---------------------------------------


def test_a_price_list_beats_the_customers_blanket_rate() -> None:
    """More specific wins. The list names the product; the blanket rate does not."""
    result = resolve_line_discount(
        gross=Decimal("1000"),
        price_list_percent=Decimal("12"),
        customer_default=Decimal("5"),
    )

    assert result.amount == Decimal("120.00")
    assert result.source == "price_list"


def test_a_typed_percentage_beats_the_price_list() -> None:
    """A person deciding beats a table."""
    result = resolve_line_discount(
        gross=Decimal("1000"),
        percent=Decimal("3"),
        price_list_percent=Decimal("12"),
        customer_default=Decimal("5"),
    )

    assert result.amount == Decimal("30.00")
    assert result.source == "percent"


def test_a_typed_zero_refuses_the_price_list_too() -> None:
    """Saying "not this time" outranks an arrangement as well as a blanket rate."""
    result = resolve_line_discount(
        gross=Decimal("1000"),
        percent=Decimal("0"),
        price_list_percent=Decimal("12"),
    )

    assert result.amount == Decimal("0.00")


def test_a_list_that_names_a_product_at_zero_blocks_the_blanket_rate() -> None:
    """The reason `rate_for` answers None rather than zero for silence.

    A firm that puts one product at nil on a customer's list means it: that
    product is excluded from the arrangement, and the blanket rate must not
    creep back in underneath.
    """
    result = resolve_line_discount(
        gross=Decimal("1000"),
        price_list_percent=Decimal("0"),
        customer_default=Decimal("5"),
    )

    assert result.amount == Decimal("0.00")
    assert result.source == "price_list"


def test_no_list_falls_through_to_the_blanket_rate() -> None:
    """The arrangement is more specific, not a replacement."""
    result = resolve_line_discount(
        gross=Decimal("1000"),
        price_list_percent=None,
        customer_default=Decimal("5"),
    )

    assert result.amount == Decimal("50.00")
    assert result.source == "customer"


# ----------------------------------------------------------------------
# D-PRC-12: a price list says what clashed, before it writes
# ----------------------------------------------------------------------


def _request_session() -> Session:
    """Open a session as a request does: one that does not flush on a read."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)()


def _write(product_id: UUID, **changes: object) -> PriceListWrite:
    """Describe a list of one rate, with whatever a test changes."""
    return PriceListWrite.model_validate(
        {
            "code": "PL-1",
            "name": "Dealers",
            "effective_from": date(2026, 1, 1),
            "items": [{"product_id": product_id, "discount_percent": "5"}],
            **changes,
        }
    )


def test_a_price_list_names_what_clashed_before_it_writes() -> None:
    """D-PRC-12: each of these answered only that the request conflicted.

    A product or a customer of another firm, and one product twice at one
    quantity. The first two reached the foreign key -- and in a store two
    firms share they did not even fail -- and the third the unique key.
    """
    session = _request_session()
    firm_id, other_firm = uuid4(), uuid4()
    product = _product(session, firm_id)
    theirs = _product(session, other_firm, code="SKU-THEIRS")
    their_customer = _customer(session, other_firm)
    service = PriceListService(session)

    def create(**changes: object) -> PriceList:
        return service.create(
            _write(product.id, **changes), firm_scope=firm_id, actor_id=uuid4()
        )

    with pytest.raises(ValidationError) as refusal:
        create(
            items=[
                {"product_id": product.id, "discount_percent": "5"},
                {"product_id": theirs.id, "discount_percent": "5"},
            ]
        )
    assert str(refusal.value) == "Row 2: the product was not found in this firm."

    with pytest.raises(ValidationError) as refusal:
        create(customer_id=their_customer.id)
    assert str(refusal.value) == (
        "The customer this price list names was not found in this firm."
    )

    with pytest.raises(ValidationError) as refusal:
        create(
            items=[
                {"product_id": product.id, "min_quantity": "10", "rate": "75"},
                {"product_id": product.id, "min_quantity": "10.00", "rate": "70"},
            ]
        )
    assert str(refusal.value) == (
        "Row 2: SKU-1 already has a rate from a quantity of 10 on row 1. "
        "A product takes one rate at each quantity."
    )
    assert session.scalar(select(func.count()).select_from(PriceList)) == 0
    assert session.scalar(select(func.count()).select_from(PriceListItem)) == 0


def test_an_edit_to_a_price_list_is_checked_as_a_new_one_is() -> None:
    """The rows sent on an edit, and a party only where it is changing."""
    session = _request_session()
    firm_id, other_firm = uuid4(), uuid4()
    product = _product(session, firm_id)
    theirs = _product(session, other_firm, code="SKU-THEIRS")
    their_customer = _customer(session, other_firm)
    service = PriceListService(session)
    stored = service.create(_write(product.id), firm_scope=firm_id, actor_id=uuid4())

    with pytest.raises(ValidationError, match="Row 1: the product was not found"):
        service.update(
            stored.id,
            _write(theirs.id),
            firm_scope=firm_id,
            actor_id=uuid4(),
        )
    with pytest.raises(ValidationError, match="The customer this price list names"):
        service.update(
            stored.id,
            _write(product.id, customer_id=their_customer.id),
            firm_scope=firm_id,
            actor_id=uuid4(),
        )

    # Two breaks for one product are still a ladder, not a clash.
    service.update(
        stored.id,
        _write(
            product.id,
            items=[
                {"product_id": product.id, "min_quantity": "0", "rate": "80"},
                {"product_id": product.id, "min_quantity": "10", "rate": "75"},
            ],
        ),
        firm_scope=firm_id,
        actor_id=uuid4(),
    )
    assert len(service.response(stored).items) == 2
