"""Goods types (backlog 89, steps 1 and 2).

A goods type says how a line of goods is tracked. The platform keeps a shared
catalogue and a firm adds its own; the firm says which it trades in; a
category carries one and a product takes it from there and stores it. A
product with no category, or under a category with no type, is General,
which is the absence of a type.
"""

# ruff: noqa: D103

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.business.api.router import (
    get_active_features,
    get_active_modules,
    list_attribute_definitions,
    list_features,
)
from app.business.models import BusinessFeature, BusinessModule, BusinessProfile
from app.business.schemas import FirmBusinessProfileAssign
from app.business.services.framework_service import BusinessProfileFrameworkService
from app.common.audit.models import AuditLog
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.identity.models import UserFirm
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.products.api.router import GoodsTypeManageScope, router
from app.products.goods_type_seed import SHARED_GOODS_TYPES, seed_goods_types
from app.products.models import Product, ProductCategory
from app.products.schemas import (
    ProductCategoryCreate,
    ProductCategoryUpdate,
    ProductUpdate,
)
from app.products.schemas.goods_type import (
    GoodsTypeCreate,
    GoodsTypeResponse,
    GoodsTypeUpdate,
    GoodsTypeUse,
)
from app.products.services import ProductService
from app.products.services.goods_types import GoodsTypeService
from app.tax.models import TaxProfile
from tests.unit.test_product_master import (
    _base_payload,
    _firm,
    _principal,
    _seed_profile,
    _session_factory,
)


def _store() -> Session:
    """Return a store holding the shared catalogue and a profile."""
    session = _session_factory()()
    seed_goods_types(session)
    _seed_profile(session)
    session.commit()
    return session


def _by_code(session: Session, firm_id: object, code: str) -> GoodsTypeResponse:
    """Return one goods type as the firm sees it."""
    return next(
        row
        for row in GoodsTypeService(session).list_types(firm_id)  # type: ignore[arg-type]
        if row.code == code
    )


def _use(session: Session, firm_id: object, code: str) -> GoodsTypeResponse:
    """Take a shared goods type into use for the firm."""
    return GoodsTypeService(session).set_use(
        _by_code(session, firm_id, code).id,
        GoodsTypeUse(in_use=True),
        firm_id=firm_id,  # type: ignore[arg-type]
        actor_id=uuid4(),
    )


def _category(
    session: Session,
    firm_id: object,
    code: str,
    *,
    goods_type_id: object = None,
    parent_id: object = None,
) -> object:
    """Create one category and return its id."""
    return (
        ProductService(session)
        .create_category(
            ProductCategoryCreate(
                code=code,
                name=code.title(),
                goods_type_id=goods_type_id,  # type: ignore[arg-type]
                parent_id=parent_id,  # type: ignore[arg-type]
            ),
            firm_id=firm_id,  # type: ignore[arg-type]
            actor_id=uuid4(),
        )
        .id
    )


def _product(session: Session, firm_id: object, code: str, **fields: object) -> Product:
    """Create one product."""
    payload = _base_payload(code).model_copy(update=fields)
    return ProductService(session).create_product(
        payload,
        firm_id=firm_id,  # type: ignore[arg-type]
        actor_id=uuid4(),
    )


def test_the_shared_catalogue_is_seeded_once_and_read_by_every_firm() -> None:
    session = _store()
    seed_goods_types(session)  # a replay adds nothing
    session.commit()
    first, second = _firm(session, "ONE"), _firm(session, "TWO")
    listed = GoodsTypeService(session).list_types(first.id)

    assert sorted(row.code for row in listed) == sorted(
        seed["code"] for seed in SHARED_GOODS_TYPES
    )
    assert all(row.firm_id is None and not row.in_use for row in listed)
    medicine = _by_code(session, second.id, "MEDICINE")
    assert (medicine.track_batch, medicine.track_expiry) == (True, True)
    assert (medicine.track_serial, medicine.track_warranty) == (False, False)
    paint = _by_code(session, second.id, "PAINT")
    assert (paint.track_batch, paint.track_expiry) == (True, False)


def test_a_firm_adds_its_own_type_and_no_other_firm_sees_it() -> None:
    session = _store()
    first, second = _firm(session, "ONE"), _firm(session, "TWO")
    service = GoodsTypeService(session)
    actor = uuid4()

    created = service.create(
        GoodsTypeCreate(
            code="seeds", name="Seeds", track_batch=True, track_expiry=True
        ),
        firm_id=first.id,
        actor_id=actor,
    )

    assert (created.code, created.firm_id, created.in_use) == ("SEEDS", first.id, True)
    assert "SEEDS" not in {row.code for row in service.list_types(second.id)}
    assert session.scalar(
        select(AuditLog.id).where(AuditLog.action == "goods_type.created")
    )
    # A shared code is taken for every firm; the firm's own only for itself.
    with pytest.raises(ConflictError, match="MEDICINE already exists"):
        service.create(
            GoodsTypeCreate(code="MEDICINE", name="Ours"),
            firm_id=first.id,
            actor_id=actor,
        )
    with pytest.raises(ConflictError, match="SEEDS already exists"):
        service.create(
            GoodsTypeCreate(code="SEEDS", name="Again"),
            firm_id=first.id,
            actor_id=actor,
        )
    service.create(
        GoodsTypeCreate(code="SEEDS", name="Theirs"), firm_id=second.id, actor_id=actor
    )


def test_an_update_leaves_alone_what_it_does_not_mention() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    service = GoodsTypeService(session)
    created = service.create(
        GoodsTypeCreate(
            code="SEEDS", name="Seeds", track_batch=True, default_hsn_sac="1209"
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    renamed = service.update(
        created.id,
        GoodsTypeUpdate(name="Seeds and bulbs"),
        firm_id=firm.id,
        actor_id=uuid4(),
        expected_version=created.version,
    )

    assert (renamed.name, renamed.track_batch) == ("Seeds and bulbs", True)
    assert renamed.default_hsn_sac == "1209"
    cleared = service.update(
        created.id,
        GoodsTypeUpdate(default_hsn_sac=None, track_batch=False),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    assert (cleared.default_hsn_sac, cleared.track_batch) == (None, False)
    with pytest.raises(ConflictError, match="changed since you loaded it"):
        service.update(
            created.id,
            GoodsTypeUpdate(name="Late"),
            firm_id=firm.id,
            actor_id=uuid4(),
            expected_version=created.version,
        )


def test_a_shared_type_is_read_only_to_a_firm_but_its_use_is_the_firms() -> None:
    session = _store()
    firm, other = _firm(session, "ONE"), _firm(session, "TWO")
    service = GoodsTypeService(session)
    medicine = _by_code(session, firm.id, "MEDICINE")

    with pytest.raises(ValidationError, match="shared goods type"):
        service.update(
            medicine.id, GoodsTypeUpdate(name="Mine"), firm_id=firm.id, actor_id=uuid4()
        )
    with pytest.raises(ValidationError, match="shared goods type"):
        service.delete(medicine.id, firm_id=firm.id, actor_id=uuid4())

    session.add(
        TaxProfile(
            firm_id=firm.id,
            code="GST_12_LOCAL",
            name="GST 12%",
            label="GST 12%",
            group_code="GST_12",
            status="ACTIVE",
            tax_system_id=uuid4(),
        )
    )
    session.commit()
    used = service.set_use(
        medicine.id,
        GoodsTypeUse(
            in_use=True, default_hsn_sac="3004", default_tax_profile_group_code="GST_12"
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    assert (used.in_use, used.default_hsn_sac) == (True, "3004")
    assert used.default_tax_profile_group_code == "GST_12"
    # The defaults are this firm's: the next firm sees the type unused.
    theirs = _by_code(session, other.id, "MEDICINE")
    assert (theirs.in_use, theirs.default_hsn_sac) == (False, None)
    # Re-saving use without naming a default leaves it alone.
    again = service.set_use(
        medicine.id, GoodsTypeUse(in_use=True), firm_id=firm.id, actor_id=uuid4()
    )
    assert again.default_hsn_sac == "3004"
    with pytest.raises(ValidationError, match="No active tax profile"):
        service.set_use(
            medicine.id,
            GoodsTypeUse(in_use=True, default_tax_profile_group_code="NOPE"),
            firm_id=firm.id,
            actor_id=uuid4(),
        )


def test_a_category_takes_only_a_type_the_firm_uses() -> None:
    session = _store()
    firm, other = _firm(session, "ONE"), _firm(session, "TWO")
    medicine = _by_code(session, firm.id, "MEDICINE")

    with pytest.raises(ValidationError, match="not among the goods types"):
        _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)
    _use(session, firm.id, "MEDICINE")
    _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)

    theirs = GoodsTypeService(session).create(
        GoodsTypeCreate(code="SEEDS", name="Seeds"), firm_id=other.id, actor_id=uuid4()
    )
    with pytest.raises(ValidationError, match="unavailable"):
        _category(session, firm.id, "SEEDS", goods_type_id=theirs.id)


def test_a_product_takes_its_categorys_type_and_none_is_general() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    medicine = _use(session, firm.id, "MEDICINE")
    paint = _use(session, firm.id, "PAINT")
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)
    # A sub-category with no type takes its parent's; one with its own wins.
    strips = _category(session, firm.id, "STRIPS", parent_id=tablets)
    tins = _category(
        session, firm.id, "TINS", parent_id=tablets, goods_type_id=paint.id
    )
    plain = _category(session, firm.id, "SUNDRIES")

    assert _product(session, firm.id, "P-1", category_id=tablets).goods_type_id == (
        medicine.id
    )
    under_strips = _product(
        session, firm.id, "P-2", category_id=tablets, sub_category_id=strips
    )
    assert under_strips.goods_type_id == medicine.id
    under_tins = _product(
        session, firm.id, "P-3", category_id=tablets, sub_category_id=tins
    )
    assert under_tins.goods_type_id == paint.id
    assert _product(session, firm.id, "P-4", category_id=plain).goods_type_id is None
    assert _product(session, firm.id, "P-5").goods_type_id is None
    # A product that takes no type is filled with nothing.
    assert _product(session, firm.id, "P-6", category_id=plain).track_batch is False


def test_a_category_changing_type_reaches_new_products_only() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    medicine = _use(session, firm.id, "MEDICINE")
    food = _use(session, firm.id, "FOOD")
    service = ProductService(session)
    syrups = _category(session, firm.id, "SYRUPS", goods_type_id=medicine.id)
    before = _product(session, firm.id, "P-1", category_id=syrups)

    def save(**fields: object) -> None:
        service.update_category(
            syrups,  # type: ignore[arg-type]
            ProductCategoryUpdate(code="SYRUPS", name="Syrups", **fields),  # type: ignore[arg-type]
            firm_scope=firm.id,
            actor_id=uuid4(),
        )

    save()  # a save that does not mention the type leaves it alone
    assert _product(session, firm.id, "P-2", category_id=syrups).goods_type_id == (
        medicine.id
    )
    save(goods_type_id=food.id)
    session.refresh(before)
    assert before.goods_type_id == medicine.id
    assert _product(session, firm.id, "P-3", category_id=syrups).goods_type_id == (
        food.id
    )
    save(goods_type_id=None)  # an explicit null makes the category General
    assert _product(session, firm.id, "P-4", category_id=syrups).goods_type_id is None


def test_moving_a_product_to_another_category_is_what_changes_its_type() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    medicine = _use(session, firm.id, "MEDICINE")
    paint = _use(session, firm.id, "PAINT")
    service = ProductService(session)
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)
    enamels = _category(session, firm.id, "ENAMELS", goods_type_id=paint.id)
    product = _product(session, firm.id, "P-1", category_id=tablets)

    def save(**fields: object) -> Product:
        return service.update_product(
            product.id,
            ProductUpdate.model_validate(
                {"code": "P-1", "name": "Renamed", "product_type": "STOCK_ITEM"}
                | fields
            ),
            firm_scope=firm.id,
            actor_id=uuid4(),
        )

    assert save().goods_type_id == medicine.id
    assert save(category_id=str(enamels)).goods_type_id == paint.id
    assert save(category_id=None).goods_type_id is None


def test_a_type_something_carries_is_neither_dropped_nor_deleted() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    service = GoodsTypeService(session)
    medicine = _use(session, firm.id, "MEDICINE")
    own = service.create(
        GoodsTypeCreate(code="SEEDS", name="Seeds"), firm_id=firm.id, actor_id=uuid4()
    )
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)
    packets = _category(session, firm.id, "PACKETS", goods_type_id=own.id)
    _product(session, firm.id, "P-1", category_id=packets)

    with pytest.raises(ConflictError, match="category Tablets"):
        service.set_use(
            medicine.id, GoodsTypeUse(in_use=False), firm_id=firm.id, actor_id=uuid4()
        )
    with pytest.raises(ConflictError, match="category Packets"):
        service.delete(own.id, firm_id=firm.id, actor_id=uuid4())

    products = ProductService(session)
    for category, code in ((tablets, "TABLETS"), (packets, "PACKETS")):
        products.update_category(
            category,  # type: ignore[arg-type]
            ProductCategoryUpdate(code=code, name=code.title(), goods_type_id=None),
            firm_scope=firm.id,
            actor_id=uuid4(),
        )
    dropped = service.set_use(
        medicine.id, GoodsTypeUse(in_use=False), firm_id=firm.id, actor_id=uuid4()
    )
    assert dropped.in_use is False
    # The product filed while the category carried the type still holds it.
    with pytest.raises(ConflictError, match="product P-1"):
        service.delete(own.id, firm_id=firm.id, actor_id=uuid4())
    with pytest.raises(ResourceNotFoundError):
        service.delete(uuid4(), firm_id=firm.id, actor_id=uuid4())


def test_a_firms_first_profile_hands_it_the_starting_types_once() -> None:
    session = _store()
    firm = _firm(session, "MED")
    pharmacy = BusinessProfile(
        code="PHARMACY",
        name="Pharma Distribution",
        industry_type="PHARMACY",
        status="ACTIVE",
        default_settings={},
    )
    session.add(pharmacy)
    session.commit()
    framework = BusinessProfileFrameworkService(session)
    generic = session.scalar(
        select(BusinessProfile).where(BusinessProfile.code == "GENERIC")
    )
    assert generic is not None

    framework.assign_profile_to_firm(
        firm.id, FirmBusinessProfileAssign(business_profile_id=pharmacy.id), uuid4()
    )
    session.commit()
    assert [
        row.code for row in GoodsTypeService(session).list_types(firm.id) if row.in_use
    ] == ["MEDICINE"]
    handed = session.scalars(
        select(AuditLog).where(AuditLog.action == "goods_type.starting_set")
    ).all()
    assert [(row.entity_id, row.after_data) for row in handed] == [
        (firm.id, {"profile": "PHARMACY", "goods_types": ["MEDICINE"]})
    ]

    # Dropped by the firm, then the profile changed and changed back: the
    # profile is a starter kit and has no say after the first day.
    medicine = _by_code(session, firm.id, "MEDICINE")
    GoodsTypeService(session).set_use(
        medicine.id, GoodsTypeUse(in_use=False), firm_id=firm.id, actor_id=uuid4()
    )
    for profile in (generic, pharmacy):
        framework.assign_profile_to_firm(
            firm.id, FirmBusinessProfileAssign(business_profile_id=profile.id), uuid4()
        )
        session.commit()
    assert not [
        row for row in GoodsTypeService(session).list_types(firm.id) if row.in_use
    ]
    # ... and a hand-over that gave nothing wrote nothing to the trail.
    assert (
        len(
            session.scalars(
                select(AuditLog).where(AuditLog.action == "goods_type.starting_set")
            ).all()
        )
        == 1
    )


def test_the_firms_administrator_keeps_goods_types_and_the_manager_does_not() -> None:
    code = GoodsTypeManageScope.__metadata__[0].dependency.permission_code
    assert code == "CUSTOM_FIELD_MANAGE"
    assert code in ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    assert code not in ROLE_PERMISSION_CODES["FIRM_MANAGER"]

    def enforced(method: str, path: str) -> str:
        """Return the permission code one goods type route asks for."""
        route = next(
            item
            for item in router.routes
            if getattr(item, "path", "") == f"/api/v1/products{path}"
            and method in getattr(item, "methods", ())
        )
        codes = {
            getattr(dependency.call, "permission_code", None)
            for dependency in route.dependant.dependencies  # type: ignore[attr-defined]
        }
        return next(item for item in codes if item)

    assert enforced("GET", "/goods-types") == "PRODUCT_VIEW"
    for method, path in (
        ("POST", "/goods-types"),
        ("PUT", "/goods-types/{goods_type_id}"),
        ("PUT", "/goods-types/{goods_type_id}/use"),
        ("DELETE", "/goods-types/{goods_type_id}"),
    ):
        assert enforced(method, path) == "CUSTOM_FIELD_MANAGE"


def _tax_group(session: Session, firm_id: object, group_code: str) -> TaxProfile:
    """Give the firm one live tax profile in a group."""
    row = TaxProfile(
        firm_id=firm_id,
        tax_system_id=uuid4(),
        code=group_code,
        name=group_code,
        group_code=group_code,
        label=group_code,
        status="ACTIVE",
        created_by=uuid4(),
        updated_by=uuid4(),
    )
    session.add(row)
    session.commit()
    return row


def _defaults(session: Session, firm_id: object, code: str) -> GoodsTypeResponse:
    """Take a shared type into use with an HSN code and a tax group."""
    return GoodsTypeService(session).set_use(
        _by_code(session, firm_id, code).id,
        GoodsTypeUse(
            in_use=True, default_hsn_sac="3004", default_tax_profile_group_code="GST12"
        ),
        firm_id=firm_id,  # type: ignore[arg-type]
        actor_id=uuid4(),
    )


_REQUIRE = (
    "require_batch_on_receipt",
    "require_batch_on_issue",
    "require_serial_on_receipt",
    "require_serial_on_issue",
)


def test_the_type_fills_a_new_products_switches() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    medicine = _use(session, firm.id, "MEDICINE")
    electronics = _use(session, firm.id, "ELECTRONICS")
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)
    phones = _category(session, firm.id, "PHONES", goods_type_id=electronics.id)

    tablet = _product(session, firm.id, "P-1", category_id=tablets)
    phone = _product(session, firm.id, "P-2", category_id=phones)

    assert (tablet.track_batch, tablet.track_expiry) == (True, True)
    assert tablet.track_manufacturing_date is True
    assert (tablet.track_serial, tablet.track_warranty) == (False, False)
    # Tracked by batch means its goods neither arrive nor leave without one.
    assert [getattr(tablet, name) for name in _REQUIRE] == [True, True, False, False]
    assert (phone.track_serial, phone.track_warranty) == (True, True)
    assert (phone.track_batch, phone.track_expiry) == (False, False)
    assert [getattr(phone, name) for name in _REQUIRE] == [False, False, True, True]
    # Not a switch the type holds, so never one it fills.
    assert tablet.track_lot is False


def test_a_switch_the_caller_names_is_theirs_on_or_off() -> None:
    """One product may differ from its line; ``False`` sent is not silence."""
    session = _store()
    firm = _firm(session, "ONE")
    medicine = _use(session, firm.id, "MEDICINE")
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)

    loose = _product(session, firm.id, "P-1", category_id=tablets, track_batch=False)
    # Its expiry was not mentioned, so that still follows the type; and with
    # batch tracking off it is not left demanding a batch on a receipt.
    assert (loose.track_batch, loose.track_expiry) == (False, True)
    assert (loose.require_batch_on_receipt, loose.require_batch_on_issue) == (
        False,
        False,
    )

    lenient = _product(
        session, firm.id, "P-2", category_id=tablets, require_batch_on_issue=False
    )
    assert (lenient.track_batch, lenient.require_batch_on_receipt) == (True, True)
    assert lenient.require_batch_on_issue is False

    serialled = _product(
        session, firm.id, "P-3", category_id=tablets, track_serial=True
    )
    # Medicine is not a serial line, so naming the switch brings no rule.
    assert serialled.track_serial is True
    assert serialled.require_serial_on_receipt is False


def test_the_type_fills_hsn_and_tax_group_only_where_the_product_has_none() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    _tax_group(session, firm.id, "GST12")
    _tax_group(session, firm.id, "GST5")
    medicine = _defaults(session, firm.id, "MEDICINE")
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)

    filled = _product(session, firm.id, "P-1", category_id=tablets)
    own = _product(
        session,
        firm.id,
        "P-2",
        category_id=tablets,
        hsn_sac="3003",
        tax_profile_group_code="GST5",
    )
    general = _product(session, firm.id, "P-3")

    assert (filled.hsn_sac, filled.tax_profile_group_code) == ("3004", "GST12")
    assert (own.hsn_sac, own.tax_profile_group_code) == ("3003", "GST5")
    assert (general.hsn_sac, general.tax_profile_group_code) == (None, None)


def test_a_default_tax_group_the_firm_no_longer_has_is_passed_over() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    profile = _tax_group(session, firm.id, "GST12")
    medicine = _defaults(session, firm.id, "MEDICINE")
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)
    profile.status = "INACTIVE"
    session.commit()

    product = _product(session, firm.id, "P-1", category_id=tablets)
    offered = ProductService(session).metadata(
        firm_scope=firm.id,
        category_id=tablets,  # type: ignore[arg-type]
    )

    # Saved without a tax group rather than refused for a default it did not
    # choose, and the form is not offered a group its list does not hold.
    assert (product.hsn_sac, product.tax_profile_group_code) == ("3004", None)
    option = next(row for row in offered.goods_types if row.code == "MEDICINE")
    assert (option.default_hsn_sac, option.default_tax_profile_group_code) == (
        "3004",
        None,
    )


def test_an_update_and_a_copy_leave_the_products_switches_alone() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    medicine = _use(session, firm.id, "MEDICINE")
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)
    plain = _category(session, firm.id, "SUNDRIES")
    service = ProductService(session)
    sundry = _product(session, firm.id, "P-1", category_id=plain)
    differing = _product(
        session, firm.id, "P-2", category_id=tablets, track_expiry=False
    )

    # Moved under Medicine: it takes the type, and keeps its own switches.
    moved = service.update_product(
        sundry.id,
        ProductUpdate.model_validate(
            {
                "code": "P-1",
                "name": sundry.name,
                "product_type": "STOCK_ITEM",
                "category_id": str(tablets),
            }
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    assert moved.goods_type_id == medicine.id
    assert (moved.track_batch, moved.require_batch_on_receipt) == (False, False)

    copied = service.duplicate_product(
        differing.id, firm_scope=firm.id, actor_id=uuid4()
    )
    assert copied.goods_type_id == medicine.id
    assert (copied.track_batch, copied.track_expiry) == (True, False)


def test_the_product_metadata_carries_the_goods_types_in_its_one_call() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    medicine = _use(session, firm.id, "MEDICINE")
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)
    strips = _category(session, firm.id, "STRIPS", parent_id=tablets)
    plain = _category(session, firm.id, "SUNDRIES")
    service = ProductService(session)

    under_strips = service.metadata(
        firm_scope=firm.id,
        category_id=strips,  # type: ignore[arg-type]
    )
    under_plain = service.metadata(
        firm_scope=firm.id,
        category_id=plain,  # type: ignore[arg-type]
    )
    unasked = service.metadata(firm_scope=firm.id)

    # The parent's type, resolved by the server so the form walks no tree.
    assert under_strips.goods_type_id == medicine.id
    assert under_plain.goods_type_id is None
    assert unasked.goods_type_id is None
    assert sorted(row.code for row in unasked.goods_types) == sorted(
        str(seed["code"]) for seed in SHARED_GOODS_TYPES
    )
    option = next(row for row in unasked.goods_types if row.code == "MEDICINE")
    assert option.switches == {
        "track_batch": True,
        "track_expiry": True,
        "track_manufacturing_date": True,
        "track_serial": False,
        "track_warranty": False,
        "require_batch_on_receipt": True,
        "require_batch_on_issue": True,
        "require_serial_on_receipt": False,
        "require_serial_on_issue": False,
    }
    # What the form is told is what a save with nothing named does.
    created = _product(session, firm.id, "P-1", category_id=tablets)
    assert {name: getattr(created, name) for name in option.switches} == (
        option.switches
    )


def test_the_menus_follow_the_goods_a_firm_trades_in() -> None:
    session = _store()
    firm = _firm(session, "MIX")
    other = _firm(session, "OTH")
    service = GoodsTypeService(session)
    framework = BusinessProfileFrameworkService(session)

    # A firm trading in nothing tracked needs none of the three screens.
    assert service.tracking_in_use(firm.id) == []

    # A type taken into use is enough: no product has to exist yet.
    paint = _use(session, firm.id, "PAINT")
    assert service.tracking_in_use(firm.id) == ["BATCH"]
    _use(session, firm.id, "ELECTRONICS")
    assert service.tracking_in_use(firm.id) == ["BATCH", "SERIAL"]
    assert service.tracking_in_use(other.id) == []

    # A product keeps its own switches: one filed before goods types
    # existed, or differing from its line, still needs its screen.
    _product(session, other.id, "OLD-1", track_batch=True, track_expiry=True)
    assert service.tracking_in_use(other.id) == ["BATCH", "EXPIRY"]

    # A type dropped stops asking, unless a product still does.
    service.set_use(
        paint.id, GoodsTypeUse(in_use=False), firm_id=firm.id, actor_id=uuid4()
    )
    assert service.tracking_in_use(firm.id) == ["SERIAL"]

    # It rides on the answer the shell already reads, and no firm says nothing.
    assert framework.goods_tracking(firm.id) == ["SERIAL"]
    assert framework.goods_tracking(None) is None


def test_the_active_modules_route_says_which_tracking_screens_a_firm_needs() -> None:
    session = _store()
    firm = _firm(session, "RTE")
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    for code in ("INVENTORY", "SALES"):
        session.add(
            BusinessModule(
                code=code,
                name=code.title(),
                default_enabled=True,
                is_active=True,
                created_by=user_id,
                updated_by=user_id,
            )
        )
    session.commit()
    _use(session, firm.id, "ELECTRONICS")
    principal = _principal(user_id, set())
    request = Request({"type": "http"})

    answer = get_active_modules(
        principal, request, db=session, platform_db=session, x_firm_id=firm.id
    )
    by_code = {row.code: row.goods_tracking for row in answer.data}
    # Only the inventory row carries it; every other module says nothing.
    assert by_code == {"INVENTORY": ["SERIAL"], "SALES": None}

    # With no firm named there is nothing to hide, so nothing is said.
    nobody = get_active_modules(
        principal, request, db=session, platform_db=session, x_firm_id=None
    )
    assert {row.goods_tracking for row in nobody.data} == {None}

    # Somebody who does not belong to the firm is not told about it.
    with pytest.raises(AuthorizationError):
        get_active_modules(
            _principal(uuid4(), set()),
            request,
            db=session,
            platform_db=session,
            x_firm_id=firm.id,
        )


def test_a_deleted_category_hands_the_form_no_goods_type() -> None:
    """D-MST-18: the metadata named the type of a category that was gone."""
    session = _store()
    firm = _firm(session, "ONE")
    medicine = _use(session, firm.id, "MEDICINE")
    tablets = _category(session, firm.id, "TABLETS", goods_type_id=medicine.id)
    service = ProductService(session)
    assert (
        service.metadata(firm_scope=firm.id, category_id=tablets).goods_type_id  # type: ignore[arg-type]
        == medicine.id
    )

    row = session.get(ProductCategory, tablets)
    assert row is not None
    row.is_deleted = True
    session.commit()

    assert (
        service.metadata(firm_scope=firm.id, category_id=tablets).goods_type_id  # type: ignore[arg-type]
        is None
    )


def test_a_type_a_deleted_product_holds_is_not_deleted() -> None:
    """D-MST-19: a removed product can come back, and must find its type."""
    session = _store()
    firm = _firm(session, "ONE")
    service = GoodsTypeService(session)
    products = ProductService(session)
    own = service.create(
        GoodsTypeCreate(code="SEEDS", name="Seeds"), firm_id=firm.id, actor_id=uuid4()
    )
    packets = _category(session, firm.id, "PACKETS", goods_type_id=own.id)
    product = _product(session, firm.id, "P-1", category_id=packets)
    products.delete_product(product.id, firm_scope=firm.id, actor_id=uuid4())
    products.update_category(
        packets,  # type: ignore[arg-type]
        ProductCategoryUpdate(code="PACKETS", name="Packets", goods_type_id=None),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )

    with pytest.raises(ConflictError, match="deleted product P-1"):
        service.delete(own.id, firm_id=firm.id, actor_id=uuid4())

    restored = products.restore_product(
        product.id, firm_scope=firm.id, actor_id=uuid4()
    )
    assert restored.goods_type_id == own.id
    assert _by_code(session, firm.id, "SEEDS").id == own.id


def test_a_types_defaults_outlive_a_drop_and_come_back_with_it() -> None:
    """D-MST-21: stop using forgot the firm's HSN and tax group for the type."""
    session = _store()
    firm = _firm(session, "ONE")
    _tax_group(session, firm.id, "GST12")
    service = GoodsTypeService(session)
    medicine = _defaults(session, firm.id, "MEDICINE")

    def use(**fields: object) -> GoodsTypeResponse:
        return service.set_use(
            medicine.id,
            GoodsTypeUse(**fields),  # type: ignore[arg-type]
            firm_id=firm.id,
            actor_id=uuid4(),
        )

    assert use(in_use=False).in_use is False
    back = use(in_use=True)
    assert (back.default_hsn_sac, back.default_tax_profile_group_code) == (
        "3004",
        "GST12",
    )

    # A default sent with the drop is read: checked, and kept for next time.
    with pytest.raises(ValidationError, match="tax profile"):
        use(in_use=False, default_tax_profile_group_code="NOWHERE")
    assert _by_code(session, firm.id, "MEDICINE").in_use is True
    use(in_use=False, default_hsn_sac="3003")
    again = use(in_use=True)
    assert (again.default_hsn_sac, again.default_tax_profile_group_code) == (
        "3003",
        "GST12",
    )
    # One row for the firm and the type throughout, live again.
    assert list(service._uses(firm.id)) == [medicine.id]


def test_a_store_with_no_catalogue_answers_nothing_when_no_firm_is_named() -> None:
    """D-CFG-26: the platform store holds none of these tables, and said 503."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    bare = Session(engine)
    principal = _principal(uuid4(), set())
    request = Request({"type": "http"})

    modules = get_active_modules(
        principal, request, db=bare, platform_db=bare, x_firm_id=None
    )
    features = get_active_features(
        principal, request, db=bare, platform_db=bare, x_firm_id=None
    )
    catalogue = list_features(principal, db=bare)
    fields = list_attribute_definitions(principal, db=bare)

    assert modules.data == [] and features.data == []
    assert catalogue.data == [] and catalogue.pagination.total_records == 0
    assert fields.data == [] and fields.pagination.total_records == 0

    # A store that does hold the catalogue answers as it always did.
    session = _store()
    assert list_features(principal, db=session).pagination.total_records == len(
        session.scalars(select(BusinessFeature.id)).all()
    )
