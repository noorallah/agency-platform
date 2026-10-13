"""A product or a category may need several licences (backlog 152, row P3).

Every licence on the list is asked for, each judged by itself, so the finding
names the one that is missing or lapsed. A list of one behaves as the single
type did -- ``test_licence_checks.py`` still holds that, unchanged in what it
asserts.
"""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ConflictError, ValidationError
from app.products.models import (
    ProductCategoryLicenceRequirement,
    ProductLicenceRequirement,
)
from app.products.schemas import ProductCategoryUpdate
from app.products.services import ProductService
from app.trade_licences.models import TradeLicenceType
from app.trade_licences.schemas import (
    LicenceEnforcement,
    LicenceParty,
    LicenceShortfall,
)
from app.trade_licences.services import TradeLicenceService
from app.trade_licences.services.licence_check import LicenceLine
from app.vendors.models import Vendor
from tests.unit.test_licence_checks import ORDER_DATE, _Pharma


class _TwoLicences(_Pharma):
    """The pharma firm, its product needing two licences of its own."""

    def __init__(self) -> None:
        """Make the product need the wholesale and the Schedule X licence."""
        super().__init__()
        self.schedule_x: TradeLicenceType = self.types["DRUG_SCHEDULE_X"]
        self.product.required_licence_type_ids = [self.drug.id, self.schedule_x.id]
        self.session.commit()
        # The firm holds both, so only the buyer is in question.
        self.hold(branch=False)
        self.hold(branch=False, licence_type=self.schedule_x)


@pytest.fixture
def two() -> _TwoLicences:
    """Build a firm whose product needs two licences."""
    return _TwoLicences()


def test_a_shop_holding_one_of_two_is_told_which_is_missing(
    two: _TwoLicences,
) -> None:
    """The finding names the licence not held, and only that one."""
    two.hold(customer=True)
    two.policy(LicenceEnforcement.BLOCK)
    two.sale()
    assert [(f.party, f.licence_type_id, f.shortfall) for f in two.last.findings] == [
        (LicenceParty.CUSTOMER, two.schedule_x.id, LicenceShortfall.MISSING)
    ]
    assert two.last.would_block
    assert two.schedule_x.name in (two.last.message or "")
    assert two.drug.name not in (two.last.message or "")


def test_a_shop_holding_neither_gets_a_finding_for_each(two: _TwoLicences) -> None:
    """Each licence is judged by itself."""
    two.sale()
    assert {f.licence_type_id for f in two.last.findings} == {
        two.drug.id,
        two.schedule_x.id,
    }
    assert all(f.line_numbers == [1] for f in two.last.findings)


def test_a_shop_holding_both_passes(two: _TwoLicences) -> None:
    """Every licence on the list is held, so nothing is found."""
    two.hold(customer=True)
    two.hold(customer=True, licence_type=two.schedule_x)
    two.policy(LicenceEnforcement.BLOCK)
    two.sale()
    assert two.last.findings == []
    assert not two.last.would_block


def test_one_of_two_lapsed_on_the_document_s_date_is_named(
    two: _TwoLicences,
) -> None:
    """Each must be valid on the day: a lapsed one is found as lapsed."""
    two.hold(customer=True)
    two.hold(customer=True, licence_type=two.schedule_x, valid_to=date(2026, 6, 30))
    two.sale()
    assert [(f.licence_type_id, f.shortfall) for f in two.last.findings] == [
        (two.schedule_x.id, LicenceShortfall.EXPIRED)
    ]


def test_the_supplier_is_asked_for_every_one(two: _TwoLicences) -> None:
    """The buying check works the same way, for the supplier."""
    vendor = Vendor(
        firm_id=two.firm.id,
        code="VEN-2",
        name="Two Licence Supplies",
        display_name="Two Licence Supplies",
        status="ACTIVE",
    )
    two.session.add(vendor)
    two.session.commit()
    result = two.checks.check_purchase(
        firm_id=two.firm.id,
        vendor_id=vendor.id,
        on=ORDER_DATE,
        lines=[LicenceLine(1, two.product.id)],
    )
    assert [f.party for f in result.findings] == [LicenceParty.VENDOR] * 2
    assert {f.licence_type_id for f in result.findings} == {
        two.drug.id,
        two.schedule_x.id,
    }


def test_a_product_s_own_list_takes_the_place_of_its_category_s(
    two: _TwoLicences,
) -> None:
    """Own replaces the category's; an empty list takes the category's."""
    retail = two.types["DRUG_RETAIL"]
    two.category.required_licence_type_ids = [retail.id]
    two.session.commit()
    assert two.checks.required_types(two.firm.id, {two.product.id}) == {
        two.product.id: (two.drug.id, two.schedule_x.id)
    }
    two.product.required_licence_type_ids = []
    two.session.commit()
    assert two.checks.required_types(two.firm.id, {two.product.id}) == {
        two.product.id: (retail.id,)
    }


def test_the_list_keeps_its_order_and_a_type_named_twice_is_held_once(
    two: _TwoLicences,
) -> None:
    """Reordering and dropping in one write leaves exactly the list sent."""
    retail = two.types["DRUG_RETAIL"]
    two.product.required_licence_type_ids = [
        two.schedule_x.id,
        retail.id,
        two.schedule_x.id,
    ]
    two.session.commit()
    two.session.expire_all()
    assert two.product.required_licence_type_ids == [two.schedule_x.id, retail.id]
    held = two.session.scalar(
        select(func.count(ProductLicenceRequirement.id)).where(
            ProductLicenceRequirement.product_id == two.product.id
        )
    )
    assert held == 2


def test_a_change_to_the_list_alone_moves_the_record_s_version(
    two: _TwoLicences,
) -> None:
    """A second editor is told; a write of the same list moves nothing."""
    before = two.product.version
    two.product.required_licence_type_ids = [two.drug.id, two.schedule_x.id]
    two.session.commit()
    assert two.product.version == before
    two.product.required_licence_type_ids = [two.drug.id]
    two.session.commit()
    assert two.product.version == before + 1


def test_a_category_takes_a_list_and_an_edit_that_omits_it_keeps_it(
    two: _TwoLicences,
) -> None:
    """Absent leaves the list alone; an empty list clears it."""
    service = ProductService(two.session)
    retail = two.types["DRUG_RETAIL"]
    service.update_category(
        two.category.id,
        ProductCategoryUpdate(
            code="SCHED-H",
            name="Schedule H",
            required_licence_type_ids=[two.drug.id, retail.id],
        ),
        firm_scope=two.firm.id,
        actor_id=two.actor_id,
    )
    assert two.category.required_licence_type_ids == [two.drug.id, retail.id]
    service.update_category(
        two.category.id,
        ProductCategoryUpdate(code="SCHED-H", name="Schedule H drugs"),
        firm_scope=two.firm.id,
        actor_id=two.actor_id,
    )
    assert two.category.required_licence_type_ids == [two.drug.id, retail.id]
    service.update_category(
        two.category.id,
        ProductCategoryUpdate(
            code="SCHED-H", name="Schedule H", required_licence_type_ids=[]
        ),
        firm_scope=two.firm.id,
        actor_id=two.actor_id,
    )
    assert two.category.required_licence_type_ids == []
    left = two.session.scalar(
        select(func.count(ProductCategoryLicenceRequirement.id)).where(
            ProductCategoryLicenceRequirement.category_id == two.category.id
        )
    )
    assert left == 0


def test_a_type_switched_off_stays_on_a_list_but_cannot_be_added(
    two: _TwoLicences,
) -> None:
    """Only what is being added is asked about."""
    service = ProductService(two.session)
    retail = two.types["DRUG_RETAIL"]
    two.category.required_licence_type_ids = [two.drug.id]
    two.drug.is_active = False
    two.session.commit()
    service.update_category(
        two.category.id,
        ProductCategoryUpdate(
            code="SCHED-H",
            name="Schedule H",
            required_licence_type_ids=[two.drug.id, retail.id],
        ),
        firm_scope=two.firm.id,
        actor_id=two.actor_id,
    )
    assert two.category.required_licence_type_ids == [two.drug.id, retail.id]
    two.category.required_licence_type_ids = [retail.id]
    two.session.commit()
    with pytest.raises(ValidationError, match="Licence type not found"):
        service.update_category(
            two.category.id,
            ProductCategoryUpdate(
                code="SCHED-H",
                name="Schedule H",
                required_licence_type_ids=[retail.id, two.drug.id],
            ),
            firm_scope=two.firm.id,
            actor_id=two.actor_id,
        )


def test_a_type_on_a_product_s_list_cannot_be_deleted(two: _TwoLicences) -> None:
    """The soft delete never reaches the key, so the service counts."""
    narcotic = next(
        row
        for code, row in two.types.items()
        if code not in {"DRUG_WHOLESALE", "DRUG_SCHEDULE_X", "DRUG_RETAIL"}
    )
    two.product.required_licence_type_ids = [two.drug.id, narcotic.id]
    two.session.commit()
    with pytest.raises(ConflictError, match="need a"):
        TradeLicenceService(two.session).delete_type(
            narcotic.id, firm_id=two.firm.id, actor_id=two.actor_id
        )
