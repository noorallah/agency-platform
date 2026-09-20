"""The five seeded master duty codes are enforced by a route (D-MST-10).

``VENDOR_MANAGE_BANK_DETAILS``, ``VENDOR_VIEW_FINANCIAL_DETAILS``,
``PRODUCT_PRICING_MANAGE``, ``PRODUCT_TAX_MANAGE`` and
``PRODUCT_ATTRIBUTE_MANAGE`` were seeded and read by no route, so the account
a supplier is paid into was edited with ``VENDOR_UPDATE`` and shown to anybody
holding ``VENDOR_VIEW``, and a price, a tax group and the custom fields all
rode on ``PRODUCT_UPDATE``. Granting any of the five granted nothing.

Each duty is a projection of the principal over the fields it owns, the way
the cost price already was: a form resending what it was served saves as
before, and only a *change* to a duty's field is refused.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import AttributeDefinition, BusinessProfile
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.products.api.router import create_product, update_product
from app.products.models import Product
from app.products.schemas import ProductCreate, ProductResponse, ProductUpdate
from app.products.services import ProductService
from app.tax.models import TaxProfile, TaxSystem
from app.uom.models import Uom
from app.vendors.api.router import create_vendor, get_vendor, update_vendor
from app.vendors.models import Vendor
from app.vendors.schemas import VendorCreate, VendorUpdate
from app.vendors.services import VendorService

PRODUCT_DUTIES = {
    "PRODUCT_PRICING_MANAGE",
    "PRODUCT_TAX_MANAGE",
    "PRODUCT_ATTRIBUTE_MANAGE",
}


def _session() -> Session:
    """Open one in-memory database holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str) -> Firm:
    """Add a firm and the default profile a product needs."""
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
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
    session.commit()
    return firm


def _scope(session: Session, firm: Firm, codes: set[str]) -> ResolvedFirmScope:
    """Resolve a member of the firm holding exactly these codes."""
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()
    principal = Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(codes),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=sorted(codes),
        ),
    )
    return required_firm_scope(
        optional_firm_scope(principal=principal, db=session, x_firm_id=firm.id)
    )


# --- products ---------------------------------------------------------------


def _product_masters(session: Session, firm: Firm) -> tuple[Uom, AttributeDefinition]:
    """Seed the unit, the tax groups and the custom field the cases name."""
    unit = Uom(code="PIECE", name="Piece", symbol="pc")
    definition = AttributeDefinition(
        code="SHELF", name="Shelf", entity_type="PRODUCT", data_type="TEXT"
    )
    system = TaxSystem(firm_id=firm.id, code="GST", name="GST", display_name="GST")
    session.add(system)
    session.commit()
    session.add_all(
        [
            unit,
            definition,
            TaxProfile(
                firm_id=firm.id,
                tax_system_id=system.id,
                code="GST18",
                name="GST 18",
                label="GST 18",
                status="ACTIVE",
                group_code="GST18",
            ),
            TaxProfile(
                firm_id=firm.id,
                tax_system_id=system.id,
                code="GST5",
                name="GST 5",
                label="GST 5",
                status="ACTIVE",
                group_code="GST5",
            ),
        ]
    )
    session.commit()
    return unit, definition


def _product_body(
    unit: Uom, definition: AttributeDefinition, **more: object
) -> dict[str, object]:
    """Return the stored product, as the form would resend it."""
    return {
        "code": "DUTY-1",
        "name": "Dutiful product",
        "product_type": "STOCK_ITEM",
        "base_uom_id": unit.id,
        "sales_uom_id": unit.id,
        "purchase_price": "60",
        "selling_price": "100",
        "mrp": "120",
        "tax_profile_group_code": "GST18",
        "attributes": [{"attribute_definition_id": definition.id, "value": "A-12"}],
        **more,
    }


def _stored_product(
    session: Session, firm: Firm
) -> tuple[Product, Uom, AttributeDefinition]:
    """Create the product through a trusted service call."""
    unit, definition = _product_masters(session, firm)
    product = ProductService(session).create_product(
        ProductCreate.model_validate(_product_body(unit, definition)),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    return product, unit, definition


def test_a_price_a_tax_group_and_the_custom_fields_each_need_their_own_code() -> None:
    """A change to a duty's field is refused without the duty, by name."""
    session = _session()
    firm = _firm(session, "DUT1")
    product, unit, definition = _stored_product(session, firm)
    editor = {"PRODUCT_VIEW", "PRODUCT_UPDATE", "PRODUCT_VIEW_COST_PRICE"}
    # What the form was served, carried forward as each save lands.
    current = _product_body(unit, definition)

    def save(codes: set[str], **fields: object) -> Product:
        """Save the stored product back with these fields changed."""
        body = ProductUpdate.model_validate({**current, **fields})
        update_product(
            product.id, body, _scope(session, firm, codes), Response(), session, None
        )
        current.update(fields)
        session.refresh(product)
        return product

    # Resending exactly what is stored is not a change and saves as before.
    assert save(editor, name="Renamed").name == "Renamed"

    changed_attributes = [{"attribute_definition_id": definition.id, "value": "B-1"}]
    for duty, field in (
        ("PRODUCT_PRICING_MANAGE", {"selling_price": "110"}),
        ("PRODUCT_PRICING_MANAGE", {"mrp": "130"}),
        ("PRODUCT_TAX_MANAGE", {"tax_profile_group_code": "GST5"}),
        ("PRODUCT_ATTRIBUTE_MANAGE", {"attributes": changed_attributes}),
        ("PRODUCT_ATTRIBUTE_MANAGE", {"attributes": []}),
    ):
        with pytest.raises(AuthorizationError, match=duty):
            save(editor, **field)
        # Every other duty held still leaves this one wanting.
        with pytest.raises(AuthorizationError, match=duty):
            save(editor | (PRODUCT_DUTIES - {duty}), **field)
        save(editor | {duty}, **field)

    session.refresh(product)
    assert product.selling_price == Decimal("110")
    assert product.mrp == Decimal("130")
    assert product.tax_profile_group_code == "GST5"
    assert ProductService(session).attribute_responses(product) == []


def test_a_new_product_carrying_a_duty_field_needs_the_duty() -> None:
    """The create is one place for the form and all three import formats."""
    session = _session()
    firm = _firm(session, "DUT2")
    unit, definition = _product_masters(session, firm)
    creator = {"PRODUCT_VIEW", "PRODUCT_CREATE"}
    no_prices: dict[str, object] = {
        "purchase_price": None,
        "selling_price": None,
        "mrp": None,
    }

    def create(codes: set[str], **fields: object) -> ProductResponse:
        """Create a product through the route with these fields."""
        body = ProductCreate.model_validate(_product_body(unit, definition, **fields))
        return create_product(body, _scope(session, firm, codes), session).data

    with pytest.raises(AuthorizationError, match="PRODUCT_PRICING_MANAGE"):
        create(creator, tax_profile_group_code=None, attributes=[])
    with pytest.raises(AuthorizationError, match="PRODUCT_TAX_MANAGE"):
        create(creator, attributes=[], **no_prices)
    with pytest.raises(AuthorizationError, match="PRODUCT_ATTRIBUTE_MANAGE"):
        create(creator, tax_profile_group_code=None, **no_prices)
    # A bare product needs none of the three, and the full one needs all three.
    bare = create(creator, tax_profile_group_code=None, attributes=[], **no_prices)
    assert bare.code == "DUTY-1"
    full = create(creator | PRODUCT_DUTIES, code="DUTY-2")
    assert full.selling_price == Decimal("100")


def test_a_number_resent_as_a_form_types_it_is_not_a_change() -> None:
    """A stored ``10.00`` custom field resent as ``10`` is the same value."""
    session = _session()
    firm = _firm(session, "DUT3")
    unit, _ = _product_masters(session, firm)
    number = AttributeDefinition(
        code="WEIGHT", name="Weight", entity_type="PRODUCT", data_type="NUMBER"
    )
    session.add(number)
    session.commit()
    product = ProductService(session).create_product(
        ProductCreate.model_validate(
            _product_body(
                unit,
                number,
                attributes=[{"attribute_definition_id": number.id, "value": "10.00"}],
            )
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    body = ProductUpdate.model_validate(
        _product_body(
            unit,
            number,
            name="Weighed",
            attributes=[{"attribute_definition_id": number.id, "value": 10}],
        )
    )
    editor = {"PRODUCT_VIEW", "PRODUCT_UPDATE", "PRODUCT_VIEW_COST_PRICE"}
    update_product(
        product.id, body, _scope(session, firm, editor), Response(), session, None
    )
    session.refresh(product)
    assert product.name == "Weighed"


# --- vendors ----------------------------------------------------------------


def _bank(number: str) -> dict[str, object]:
    """Return one bank account input with this account number."""
    return {
        "bank_name": "State Bank",
        "account_name": "Supplier One",
        "account_number": number,
        "ifsc": "SBIN0000001",
        "is_primary": True,
    }


def _stored_vendor(session: Session, firm: Firm) -> Vendor:
    """Create a vendor with one bank account through a trusted call."""
    return VendorService(session).create(
        VendorCreate.model_validate(
            {"code": "V001", "name": "Supplier One", "banking": [_bank("1111")]}
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )


def _live_accounts(session: Session, vendor: Vendor) -> list[str]:
    """Return the account numbers the vendor still holds."""
    session.refresh(vendor)
    return sorted(
        row.account_number for row in vendor.bank_accounts if not row.is_deleted
    )


def test_a_vendors_bank_accounts_are_shown_only_with_the_financial_code() -> None:
    """``VENDOR_VIEW`` alone -- the seeded VIEWER -- is served no accounts."""
    session = _session()
    firm = _firm(session, "DUT4")
    vendor = _stored_vendor(session, firm)

    def shown(codes: set[str]) -> list[str]:
        """Read the vendor through the route and list the accounts served."""
        payload = get_vendor(
            vendor.id, _scope(session, firm, codes), Response(), False, session
        ).data
        return [row.account_number for row in payload.bank_accounts]

    assert shown({"VENDOR_VIEW"}) == []
    assert shown({"VENDOR_VIEW", "VENDOR_VIEW_FINANCIAL_DETAILS"}) == ["1111"]


def test_where_a_supplier_is_paid_changes_only_with_the_bank_details_code() -> None:
    """Every way of writing the account is held to the one duty."""
    session = _session()
    firm = _firm(session, "DUT5")
    vendor = _stored_vendor(session, firm)
    editor = {"VENDOR_VIEW", "VENDOR_UPDATE"}
    sighted = editor | {"VENDOR_VIEW_FINANCIAL_DETAILS"}

    def save(codes: set[str], **fields: object) -> None:
        """Rename the vendor through the route, with these fields."""
        body = VendorUpdate.model_validate(
            {"code": "V001", "name": "Supplier Renamed", **fields}
        )
        update_vendor(
            vendor.id, body, _scope(session, firm, codes), Response(), session, None
        )

    # A caller shown no accounts sends the empty list back; it is not an
    # instruction, so the account survives the rename.
    save(editor, banking=[])
    assert _live_accounts(session, vendor) == ["1111"]
    # One who can see them may resend them; changing them is refused by name.
    save(sighted, banking=[_bank("1111")])
    assert _live_accounts(session, vendor) == ["1111"]
    with pytest.raises(AuthorizationError, match="VENDOR_MANAGE_BANK_DETAILS"):
        save(sighted, banking=[_bank("2222")])
    with pytest.raises(AuthorizationError, match="VENDOR_MANAGE_BANK_DETAILS"):
        save(sighted, banking=[])
    assert _live_accounts(session, vendor) == ["1111"]
    save(sighted | {"VENDOR_MANAGE_BANK_DETAILS"}, banking=[_bank("2222")])
    assert _live_accounts(session, vendor) == ["2222"]

    # A new vendor carrying an account is held to the same duty.
    creator = {"VENDOR_VIEW", "VENDOR_CREATE"}
    body = VendorCreate.model_validate(
        {"code": "V002", "name": "Supplier Two", "banking": [_bank("3333")]}
    )
    with pytest.raises(AuthorizationError, match="VENDOR_MANAGE_BANK_DETAILS"):
        create_vendor(body, _scope(session, firm, creator), session)
    created = create_vendor(
        body, _scope(session, firm, creator | {"VENDOR_MANAGE_BANK_DETAILS"}), session
    ).data
    # The creator can write the account but, without the read, is not shown it.
    assert [row.account_number for row in created.bank_accounts] == []
    stored = session.get(Vendor, created.id)
    assert stored is not None
    assert _live_accounts(session, stored) == ["3333"]
