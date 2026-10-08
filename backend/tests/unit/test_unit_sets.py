"""Unit sets (backlog 89, step 3).

A unit set is a named template for a product's units and its pack size. The
platform keeps a shared catalogue and a firm adds its own. A set names the
goods types it suits, which only orders the product form's picker. Choosing
one on a new product copies it: the units land on the product and the factor
becomes the product's own conversion rule, in the one transaction.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.products.models import Product
from app.products.schemas import ProductCreate, ProductUpdate
from app.products.schemas.goods_type import GoodsTypeCreate
from app.products.services import ProductService
from app.products.services.goods_types import GoodsTypeService
from app.uom.api.router import router
from app.uom.models import ConversionRule, UnitSet, Uom
from app.uom.schemas import (
    ConversionRequest,
    UnitSetCreate,
    UnitSetResponse,
    UnitSetUpdate,
)
from app.uom.services import UnitSetService, UomService
from app.uom.system_seed import seed_uom_reference_data
from app.uom.unit_set_seed import SHARED_UNIT_SETS, seed_unit_sets
from tests.unit.test_goods_types import _category, _store, _use
from tests.unit.test_product_master import _base_payload, _firm

ACTOR = uuid4()


def _units_store() -> Session:
    """Return a store with the units, goods types and shared unit sets."""
    session = _store()
    seed_uom_reference_data(session)
    seed_unit_sets(session)
    session.commit()
    return session


def _unit(session: Session, code: str) -> UUID:
    """Return one seeded unit's id."""
    return session.scalars(select(Uom.id).where(Uom.code == code)).one()


def _named(session: Session, firm_id: UUID, name: str) -> UnitSetResponse:
    """Return one unit set as the firm sees it."""
    return next(
        row
        for row in UnitSetService(session).list_sets(firm_id, include_inactive=True)
        if row.name == name
    )


def _own_set(
    session: Session, firm_id: UUID, name: str = "Jar, case of 6", **fields: object
) -> UnitSetResponse:
    """Add one unit set of the firm's own: jars bought by the case of six."""
    payload: dict[str, object] = {
        "name": name,
        "base_uom_id": _unit(session, "JAR"),
        "inventory_uom_id": _unit(session, "JAR"),
        "purchase_uom_id": _unit(session, "CASE"),
        "sales_uom_id": _unit(session, "JAR"),
        "allow_decimal": False,
        "conversion_factor": "6",
    }
    payload.update(fields)
    return UnitSetService(session).create(
        UnitSetCreate.model_validate(payload), firm_id=firm_id, actor_id=ACTOR
    )


def _create(session: Session, firm_id: UUID, code: str, **fields: object) -> Product:
    """Create one product from a payload naming only ``fields``."""
    payload = ProductCreate.model_validate(
        {**_base_payload(code).model_dump(mode="json", exclude_unset=True), **fields}
    )
    return ProductService(session).create_product(
        payload, firm_id=firm_id, actor_id=ACTOR
    )


def _rules(session: Session, product_id: UUID) -> list[ConversionRule]:
    """Return a product's own live conversion rules."""
    return list(
        session.scalars(
            select(ConversionRule).where(
                ConversionRule.product_id == product_id,
                ConversionRule.is_deleted.is_(False),
            )
        )
    )


def _actions(session: Session, prefix: str) -> list[str]:
    """Return the audit actions written under one prefix, oldest first."""
    return [
        row.action
        for row in session.scalars(select(AuditLog).order_by(AuditLog.created_at))
        if row.action.startswith(prefix)
    ]


# -- the catalogue ----------------------------------------------------------


def test_the_shared_sets_are_seeded_once_and_read_by_every_firm() -> None:
    session = _units_store()
    seed_unit_sets(session)  # a replay adds nothing
    session.commit()
    one, two = _firm(session, "ONE"), _firm(session, "TWO")

    names = [row.name for row in UnitSetService(session).list_sets(one.id)]

    assert sorted(names) == sorted(seed["name"] for seed in SHARED_UNIT_SETS)
    assert names == sorted(names)
    assert [row.name for row in UnitSetService(session).list_sets(two.id)] == names
    strips = _named(session, one.id, "Strip, box of 10")
    assert strips.firm_id is None
    assert strips.base_uom_id == strips.sales_uom_id == _unit(session, "STRIP")
    assert strips.purchase_uom_id == _unit(session, "BOX")
    assert strips.conversion_factor == Decimal("10")


def test_one_set_is_listed_under_two_goods_types_and_one_under_none() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    types = {row.code: row.id for row in GoodsTypeService(session).list_types(firm.id)}

    bottles = _named(session, firm.id, "Bottle, carton of 24")
    pieces = _named(session, firm.id, "Piece, loose")

    assert {types["MEDICINE"], types["FOOD"]} <= set(bottles.goods_type_ids)
    assert types["PAINT"] not in bottles.goods_type_ids
    assert pieces.goods_type_ids == []  # offered to every product


def test_a_firm_adds_its_own_set_and_no_other_firm_sees_it() -> None:
    session = _units_store()
    one, two = _firm(session, "ONE"), _firm(session, "TWO")
    food = _use(session, one.id, "FOOD")

    created = _own_set(session, one.id, goods_type_ids=[str(food.id)])

    assert created.firm_id == one.id
    assert created.goods_type_ids == [food.id]
    assert created.conversion_factor == Decimal("6")
    assert "Jar, case of 6" not in {
        row.name for row in UnitSetService(session).list_sets(two.id)
    }
    assert _actions(session, "unit_set.") == ["unit_set.created"]
    # The other firm may use the same name: a firm's names are its own.
    assert _own_set(session, two.id).firm_id == two.id


def test_a_name_the_firm_or_the_catalogue_has_is_refused() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    _own_set(session, firm.id)

    with pytest.raises(ConflictError, match="Jar, case of 6"):
        _own_set(session, firm.id)
    with pytest.raises(ConflictError, match="Strip, box of 10"):
        _own_set(session, firm.id, name="Strip, box of 10")


def test_a_set_is_refused_what_does_not_fit() -> None:
    session = _units_store()
    one, two = _firm(session, "ONE"), _firm(session, "TWO")
    theirs = GoodsTypeService(session).create(
        GoodsTypeCreate(code="HARDWARE", name="Hardware"),
        firm_id=two.id,
        actor_id=ACTOR,
    )

    with pytest.raises(ValidationError, match="units are unavailable"):
        _own_set(session, one.id, base_uom_id=str(uuid4()))
    with pytest.raises(ValidationError, match="differs from the stock unit"):
        _own_set(session, one.id, purchase_uom_id=str(_unit(session, "JAR")))
    with pytest.raises(ValidationError, match="differs from the stock unit"):
        _own_set(session, one.id, purchase_uom_id=None)
    with pytest.raises(ValidationError, match="goods types are unavailable"):
        _own_set(session, one.id, goods_type_ids=[str(theirs.id)])
    assert session.scalars(select(UnitSet).where(UnitSet.firm_id == one.id)).all() == []


def test_an_update_leaves_alone_what_it_does_not_mention() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    food = _use(session, firm.id, "FOOD")
    paint = _use(session, firm.id, "PAINT")
    created = _own_set(session, firm.id, goods_type_ids=[str(food.id)])
    service = UnitSetService(session)

    renamed = service.update(
        created.id,
        UnitSetUpdate(name="Jar, case of six"),
        firm_id=firm.id,
        actor_id=ACTOR,
        expected_version=created.version,
    )
    assert renamed.name == "Jar, case of six"
    assert renamed.conversion_factor == Decimal("6")
    assert renamed.goods_type_ids == [food.id]
    assert renamed.is_active is True

    retied = service.update(
        created.id,
        UnitSetUpdate(goods_type_ids=[paint.id], conversion_factor=Decimal("8")),
        firm_id=firm.id,
        actor_id=ACTOR,
    )
    assert retied.goods_type_ids == [paint.id]
    assert retied.conversion_factor == Decimal("8")
    assert retied.name == "Jar, case of six"
    assert _actions(session, "unit_set.") == [
        "unit_set.created",
        "unit_set.updated",
        "unit_set.updated",
        "unit_set.goods_types_changed",
    ]

    # The same values again are not an event.
    service.update(
        created.id,
        UnitSetUpdate(goods_type_ids=[paint.id], conversion_factor=Decimal("8")),
        firm_id=firm.id,
        actor_id=ACTOR,
    )
    assert len(_actions(session, "unit_set.")) == 4
    with pytest.raises(ConflictError):
        service.update(
            created.id,
            UnitSetUpdate(name="Late"),
            firm_id=firm.id,
            actor_id=ACTOR,
            expected_version=created.version,
        )
    with pytest.raises(ValueError, match="cannot be null"):
        UnitSetUpdate.model_validate({"name": None})
    # Taking the purchase unit away leaves a factor between no two units.
    with pytest.raises(ValidationError, match="differs from the stock unit"):
        service.update(
            created.id,
            UnitSetUpdate.model_validate({"purchase_uom_id": None}),
            firm_id=firm.id,
            actor_id=ACTOR,
        )


def test_a_shared_set_is_read_only_and_another_firms_is_not_found() -> None:
    session = _units_store()
    one, two = _firm(session, "ONE"), _firm(session, "TWO")
    shared = _named(session, one.id, "Piece, loose")
    theirs = _own_set(session, two.id)
    service = UnitSetService(session)

    with pytest.raises(ValidationError, match="shared unit set"):
        service.update(
            shared.id, UnitSetUpdate(name="Mine"), firm_id=one.id, actor_id=ACTOR
        )
    with pytest.raises(ValidationError, match="shared unit set"):
        service.delete(shared.id, firm_id=one.id, actor_id=ACTOR)
    with pytest.raises(ResourceNotFoundError):
        service.update(
            theirs.id, UnitSetUpdate(name="Mine"), firm_id=one.id, actor_id=ACTOR
        )
    with pytest.raises(ResourceNotFoundError):
        service.delete(theirs.id, firm_id=one.id, actor_id=ACTOR)


def test_a_unit_a_set_names_cannot_be_deleted() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    _own_set(session, firm.id)

    with pytest.raises(ValidationError, match="in use"):
        UomService(session).delete_uom(_unit(session, "JAR"), actor_id=ACTOR)


def test_who_keeps_unit_sets_and_who_only_reads_them() -> None:
    def enforced(method: str, path: str) -> str:
        """Return the permission code one unit set route asks for."""
        route = next(
            item
            for item in router.routes
            if getattr(item, "path", "") == f"/api/v1/uom-framework{path}"
            and method in getattr(item, "methods", ())
        )
        codes = {
            getattr(dependency.call, "permission_code", None)
            for dependency in route.dependant.dependencies  # type: ignore[attr-defined]
        }
        return next(item for item in codes if item)

    assert enforced("GET", "/unit-sets") == "UOM_VIEW"
    for method, path in (
        ("POST", "/unit-sets"),
        ("PUT", "/unit-sets/{unit_set_id}"),
        ("DELETE", "/unit-sets/{unit_set_id}"),
    ):
        assert enforced(method, path) == "UOM_MANAGE"
    assert "UOM_MANAGE" in ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    assert "UOM_MANAGE" not in ROLE_PERMISSION_CODES["SALES_EXECUTIVE"]


# -- a product takes a set --------------------------------------------------


def test_a_product_takes_a_set_and_gets_its_units_and_its_own_rule() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    strips = _named(session, firm.id, "Strip, box of 10")

    product = _create(session, firm.id, "P-1", unit_set_id=str(strips.id))

    assert product.unit_set_id == strips.id
    assert product.base_uom_id == product.inventory_uom_id == _unit(session, "STRIP")
    assert product.purchase_uom_id == _unit(session, "BOX")
    assert product.sales_uom_id == _unit(session, "STRIP")
    assert product.allow_decimal is False
    [rule] = _rules(session, product.id)
    assert (rule.from_uom_id, rule.to_uom_id) == (
        _unit(session, "BOX"),
        _unit(session, "STRIP"),
    )
    assert rule.conversion_factor == Decimal("10")
    assert rule.firm_id == firm.id
    # A document dated before the product was typed in still converts.
    converted = UomService(session).convert_quantity(
        ConversionRequest(
            product_id=product.id,
            from_uom_id=_unit(session, "BOX"),
            to_uom_id=_unit(session, "STRIP"),
            quantity=Decimal("3"),
            conversion_date=date(2024, 4, 1),
        ),
        firm_scope=firm.id,
    )
    assert converted.converted_quantity == Decimal("30")
    assert "uom.conversion.created" in _actions(session, "uom.conversion.")


def test_what_the_caller_names_beside_a_set_is_theirs() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    strips = _named(session, firm.id, "Strip, box of 10")

    changed = _create(
        session,
        firm.id,
        "P-1",
        unit_set_id=str(strips.id),
        purchase_uom_id=str(_unit(session, "CARTON")),
        unit_conversion_factor="120",
        allow_decimal=True,
    )
    assert changed.purchase_uom_id == _unit(session, "CARTON")
    assert changed.base_uom_id == _unit(session, "STRIP")  # still the set's
    assert changed.allow_decimal is True
    [rule] = _rules(session, changed.id)
    assert rule.from_uom_id == _unit(session, "CARTON")
    assert rule.conversion_factor == Decimal("120")

    # A factor named blank is no rule, whatever the set holds.
    blank = _create(
        session, firm.id, "P-2", unit_set_id=str(strips.id), unit_conversion_factor=None
    )
    assert blank.purchase_uom_id == _unit(session, "BOX")
    assert _rules(session, blank.id) == []

    # The units changed to one and the same: the set's factor has nothing to
    # convert and is dropped without a refusal.
    same = _create(
        session,
        firm.id,
        "P-3",
        unit_set_id=str(strips.id),
        purchase_uom_id=str(_unit(session, "STRIP")),
    )
    assert _rules(session, same.id) == []


def test_two_products_of_one_category_take_different_sets() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    medicine = _use(session, firm.id, "MEDICINE")
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)
    ten = _named(session, firm.id, "Strip, box of 10")
    fifteen = _named(session, firm.id, "Strip, box of 15")

    first = _create(
        session, firm.id, "P-1", category_id=str(tablets), unit_set_id=str(ten.id)
    )
    second = _create(
        session, firm.id, "P-2", category_id=str(tablets), unit_set_id=str(fifteen.id)
    )

    assert first.goods_type_id == second.goods_type_id == medicine.id
    assert _rules(session, first.id)[0].conversion_factor == Decimal("10")
    assert _rules(session, second.id)[0].conversion_factor == Decimal("15")


def test_a_set_of_another_goods_type_is_never_refused() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    paint = _use(session, firm.id, "PAINT")
    emulsions = _category(session, firm.id, "EMULSIONS", goods_type_id=paint.id)
    strips = _named(session, firm.id, "Strip, box of 10")  # Medicine's
    assert paint.id not in strips.goods_type_ids

    product = _create(
        session, firm.id, "P-1", category_id=str(emulsions), unit_set_id=str(strips.id)
    )

    assert product.goods_type_id == paint.id
    assert product.unit_set_id == strips.id
    assert product.purchase_uom_id == _unit(session, "BOX")


def test_a_product_with_no_set_is_typed_by_hand_and_nothing_is_filled() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")

    bare = _create(session, firm.id, "P-1")
    assert bare.unit_set_id is None
    assert bare.base_uom_id is None and bare.purchase_uom_id is None
    assert _rules(session, bare.id) == []

    # Units and a factor typed by hand make the product's own rule all the same.
    typed = _create(
        session,
        firm.id,
        "P-2",
        base_uom_id=str(_unit(session, "PIECE")),
        purchase_uom_id=str(_unit(session, "BOX")),
        unit_conversion_factor="12",
    )
    assert typed.unit_set_id is None
    [rule] = _rules(session, typed.id)
    assert rule.to_uom_id == _unit(session, "PIECE")
    assert rule.conversion_factor == Decimal("12")


def test_a_factor_between_no_two_units_and_a_set_not_offered_are_refused() -> None:
    session = _units_store()
    one, two = _firm(session, "ONE"), _firm(session, "TWO")
    theirs = _own_set(session, two.id)
    retired = _own_set(session, one.id, name="Old jars", is_active=False)

    with pytest.raises(ValidationError, match="differs from the stock unit"):
        _create(session, one.id, "P-1", unit_conversion_factor="10")
    session.rollback()
    for unit_set_id in (theirs.id, retired.id, uuid4()):
        with pytest.raises(ValidationError, match="unit set is unavailable"):
            _create(session, one.id, "P-1", unit_set_id=str(unit_set_id))
        session.rollback()
    assert session.scalars(select(Product)).all() == []
    assert session.scalars(select(ConversionRule)).all() == []
    with pytest.raises(ValueError, match="greater than 0"):
        ProductCreate.model_validate(
            {
                **_base_payload("P-1").model_dump(mode="json"),
                "unit_conversion_factor": 0,
            }
        )


def test_a_set_edited_or_deleted_afterwards_leaves_the_product_as_it_was() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    jars = _own_set(session, firm.id)
    product = _create(session, firm.id, "P-1", unit_set_id=str(jars.id))
    service = UnitSetService(session)

    service.update(
        jars.id,
        UnitSetUpdate(
            conversion_factor=Decimal("12"), purchase_uom_id=_unit(session, "CARTON")
        ),
        firm_id=firm.id,
        actor_id=ACTOR,
    )
    session.refresh(product)
    assert product.purchase_uom_id == _unit(session, "CASE")
    assert _rules(session, product.id)[0].conversion_factor == Decimal("6")
    later = _create(session, firm.id, "P-2", unit_set_id=str(jars.id))
    assert later.purchase_uom_id == _unit(session, "CARTON")
    assert _rules(session, later.id)[0].conversion_factor == Decimal("12")

    service.delete(jars.id, firm_id=firm.id, actor_id=ACTOR)
    session.refresh(product)
    assert product.unit_set_id == jars.id  # where its units came from
    assert product.base_uom_id == _unit(session, "JAR")
    assert len(_rules(session, product.id)) == 1
    assert _actions(session, "unit_set.")[-1] == "unit_set.deleted"


def test_an_update_cannot_name_a_set_or_a_factor() -> None:
    for key, value in (("unit_set_id", str(uuid4())), ("unit_conversion_factor", "5")):
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            ProductUpdate.model_validate(
                {**_base_payload("P-1").model_dump(mode="json"), key: value}
            )


def test_the_product_metadata_carries_the_unit_sets_in_its_one_call() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    _own_set(session, firm.id)
    _own_set(session, firm.id, name="Old jars", is_active=False)

    metadata = ProductService(session).metadata(firm_scope=firm.id)

    names = [row.name for row in metadata.unit_sets]
    assert names == sorted(
        [*(seed["name"] for seed in SHARED_UNIT_SETS), "Jar, case of 6"]
    )
    option = next(row for row in metadata.unit_sets if row.name == "Strip, box of 10")
    types = {row.code: row.id for row in metadata.goods_types}
    assert option.goods_type_ids == [types["MEDICINE"]]
    assert option.conversion_factor == Decimal("10")
    # What the form is told is what a save naming only the set does.
    created = _create(session, firm.id, "P-1", unit_set_id=str(option.id))
    assert created.purchase_uom_id == option.purchase_uom_id
    assert created.inventory_uom_id == option.inventory_uom_id


def test_a_copy_converts_as_its_source_does_and_keeps_the_sets_name() -> None:
    session = _units_store()
    firm = _firm(session, "ONE")
    jars = _own_set(session, firm.id)
    # The source overrode the set: a case of eight, not six.
    source = _create(
        session,
        firm.id,
        "P-1",
        unit_set_id=str(jars.id),
        unit_conversion_factor="8",
    )
    products = ProductService(session)

    copy = products.duplicate_product(source.id, firm_scope=firm.id, actor_id=ACTOR)

    assert copy.unit_set_id == jars.id
    assert copy.purchase_uom_id == _unit(session, "CASE")
    [rule] = _rules(session, copy.id)
    assert rule.conversion_factor == Decimal("8")

    # A product typed by hand, with one unit throughout, copies with no rule.
    plain = _create(session, firm.id, "P-2")
    plain_copy = products.duplicate_product(
        plain.id, firm_scope=firm.id, actor_id=ACTOR
    )
    assert plain_copy.unit_set_id is None and not _rules(session, plain_copy.id)

    # The set is gone: the copy still converts, and names no set.
    UnitSetService(session).delete(jars.id, firm_id=firm.id, actor_id=ACTOR)
    late = products.duplicate_product(source.id, firm_scope=firm.id, actor_id=ACTOR)
    assert late.unit_set_id is None
    assert late.purchase_uom_id == _unit(session, "CASE")
    assert _rules(session, late.id)[0].conversion_factor == Decimal("8")
