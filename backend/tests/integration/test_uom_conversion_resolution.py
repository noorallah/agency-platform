"""Conversion-rule selection, which depends on how the backend sorts NULLs.

A product may carry its own conversion factor, overriding the firm-wide rule for
the same unit pair. The two candidates were separated by ``ORDER BY product_id
DESC``, and where NULLs land in that sort is backend-specific: PostgreSQL puts
them first, SQLite last. So on the deployment target the firm-wide fallback beat
the product's own rule and every quantity for that product converted with the
wrong factor -- while the SQLite unit suite saw the right answer.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.firms.models import Firm
from app.products.models import Product
from app.uom.models import ConversionRule, Uom
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService

_ACTOR = uuid4()


def _seed(session: Session) -> tuple[Firm, Product, Uom, Uom]:
    """Create a firm, a product and the unit pair to convert between."""
    firm = Firm(
        name="Conversion Firm",
        code="CONV01",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.flush()
    product = Product(
        firm_id=firm.id,
        code="SKU-CONV-1",
        name="Convertible",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        created_by=_ACTOR,
        updated_by=_ACTOR,
    )
    box = Uom(code="BOX", name="Box", dimension="COUNT", status="ACTIVE")
    piece = Uom(code="PIECE", name="Piece", dimension="COUNT", status="ACTIVE")
    session.add_all([product, box, piece])
    session.flush()
    return firm, product, box, piece


def _rule(
    session: Session,
    *,
    firm: Firm,
    product_id: object,
    box: Uom,
    piece: Uom,
    factor: str,
) -> None:
    """Add one active conversion rule effective from the start of 2026."""
    session.add(
        ConversionRule(
            firm_id=firm.id,
            product_id=product_id,
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_factor=Decimal(factor),
            effective_from=date(2026, 1, 1),
            version_number=1,
            status="ACTIVE",
            created_by=_ACTOR,
            updated_by=_ACTOR,
        )
    )
    session.flush()


def test_a_products_own_rule_beats_the_firm_wide_one(temp_session: Session) -> None:
    """The more specific rule wins, whatever the backend does with NULLs."""
    firm, product, box, piece = _seed(temp_session)
    _rule(temp_session, firm=firm, product_id=None, box=box, piece=piece, factor="12")
    _rule(
        temp_session,
        firm=firm,
        product_id=product.id,
        box=box,
        piece=piece,
        factor="24",
    )

    result = UomService(temp_session).convert_quantity(
        ConversionRequest(
            product_id=product.id,
            from_uom_id=box.id,
            to_uom_id=piece.id,
            quantity=Decimal("1"),
            conversion_date=date(2026, 6, 1),
        ),
        firm_scope=firm.id,
    )

    assert result.conversion_factor == Decimal("24.0000000000")
    assert result.converted_quantity == Decimal("24.0000")


def test_a_product_without_its_own_rule_falls_back_to_the_firm_rule(
    temp_session: Session,
) -> None:
    """The fallback still applies when the product has no rule of its own."""
    firm, product, box, piece = _seed(temp_session)
    _rule(temp_session, firm=firm, product_id=None, box=box, piece=piece, factor="12")

    result = UomService(temp_session).convert_quantity(
        ConversionRequest(
            product_id=product.id,
            from_uom_id=box.id,
            to_uom_id=piece.id,
            quantity=Decimal("1"),
            conversion_date=date(2026, 6, 1),
        ),
        firm_scope=firm.id,
    )

    assert result.conversion_factor == Decimal("12.0000000000")


def test_the_newest_version_of_a_rule_wins(temp_session: Session) -> None:
    """Two published versions of one rule resolve to the higher number."""
    firm, product, box, piece = _seed(temp_session)
    _rule(temp_session, firm=firm, product_id=None, box=box, piece=piece, factor="12")
    temp_session.add(
        ConversionRule(
            firm_id=firm.id,
            product_id=None,
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_factor=Decimal("15"),
            effective_from=date(2026, 1, 1),
            version_number=2,
            status="ACTIVE",
            created_by=_ACTOR,
            updated_by=_ACTOR,
        )
    )
    temp_session.flush()

    result = UomService(temp_session).convert_quantity(
        ConversionRequest(
            from_uom_id=box.id,
            to_uom_id=piece.id,
            quantity=Decimal("1"),
            conversion_date=date(2026, 6, 1),
        ),
        firm_scope=firm.id,
    )

    assert result.conversion_factor == Decimal("15.0000000000")
    assert result.version == 2
