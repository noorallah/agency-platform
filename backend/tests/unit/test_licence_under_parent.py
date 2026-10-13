"""The licence check for a shop under a parent buyer (backlog 139, row F8).

A shop's own licence of the type a line needs comes first. Where it holds
none of that type, its parent's counts, judged on the document's date, and
the result says the parent's was used. A firm setting makes each shop hold
its own. A supplier's branch and its main office work the same way.
"""

from datetime import date
from uuid import UUID

import pytest

from app.customers.models import Customer
from app.sales_order.services import SalesOrderService
from app.trade_licences.models import TradeLicence
from app.trade_licences.schemas import (
    LicenceEnforcement,
    LicenceParty,
    LicenceShortfall,
    TradeLicenceSettingsWrite,
)
from app.trade_licences.services import TradeLicenceService
from app.trade_licences.services.licence_check import LicenceLine
from app.vendors.models import Vendor
from tests.unit.test_licence_checks import ORDER_DATE, _Pharma


class _Family(_Pharma):
    """The pharma firm, its customer made a shop of a parent buyer."""

    def __init__(self) -> None:
        """Put the customer under a parent; the firm itself is licensed."""
        super().__init__()
        self.parent = Customer(
            firm_id=self.firm.id,
            code="PAR-001",
            customer_type="RETAIL",
            name="Parent Stores",
            display_name="Parent Stores",
            currency_code="INR",
            status="ACTIVE",
        )
        self.session.add(self.parent)
        self.session.flush()
        self.customer.parent_customer_id = self.parent.id
        self.session.commit()
        # The seller is covered throughout: these cases are about the buyer.
        self.hold(branch=True)

    def parent_holds(
        self,
        *,
        number: str = "DL-P",
        valid_to: date | None = date(2027, 3, 31),
        customer_id: UUID | None = None,
    ) -> None:
        """Record a drug licence for the parent, or another customer."""
        self.session.add(
            TradeLicence(
                firm_id=self.firm.id,
                licence_type_id=self.drug.id,
                holder_type="CUSTOMER",
                customer_id=customer_id or self.parent.id,
                licence_number=number,
                valid_to=valid_to,
            )
        )
        self.session.commit()

    def strict(self, on: bool = True) -> None:
        """Switch *A shop must hold its own licence*."""
        self.checks.update_settings(
            TradeLicenceSettingsWrite(
                sale_enforcement=LicenceEnforcement.WARN,
                purchase_enforcement=LicenceEnforcement.WARN,
                shop_needs_own_licence=on,
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )


@pytest.fixture
def family() -> _Family:
    """Build a pharma firm whose customer is a shop under a parent."""
    return _Family()


def test_a_shop_with_none_is_covered_by_its_parent_s_and_is_told_so(
    family: _Family,
) -> None:
    """No finding; the cover names the parent, the number and the line."""
    family.parent_holds()
    family.sale()
    result = family.last
    assert result.findings == []
    assert not result.would_block
    assert result.message is None
    [cover] = result.covered_by_parent
    assert cover.party is LicenceParty.CUSTOMER
    assert cover.party_name == "Customer CUS-001"
    assert cover.parent_name == "Parent Stores"
    assert cover.licence_number == "DL-P"
    assert cover.line_numbers == [1]
    assert cover.message == (
        "Line 1 (Product SKU-001): Customer CUS-001 holds no Drug licence, "
        "wholesale; its parent Parent Stores's Drug licence, wholesale DL-P "
        "was used."
    )


def test_the_parent_s_expired_one_is_caught(family: _Family) -> None:
    """The parent's is judged on the document's date like any other."""
    family.parent_holds(valid_to=date(2026, 7, 31))
    family.sale()
    [finding] = family.last.findings
    assert finding.shortfall is LicenceShortfall.EXPIRED
    assert finding.parent_name == "Parent Stores"
    assert finding.licence_number == "DL-P"
    assert "its parent Parent Stores's" in finding.message
    assert "expired on 2026-07-31" in finding.message
    assert family.last.covered_by_parent == []
    # The day before it ran out, it covered the shop.
    family.sale(on=date(2026, 7, 31))
    assert family.last.findings == []
    assert len(family.last.covered_by_parent) == 1


def test_neither_holding_one_names_both(family: _Family) -> None:
    """Missing is said of the shop and of its parent."""
    family.sale()
    [finding] = family.last.findings
    assert finding.shortfall is LicenceShortfall.MISSING
    assert finding.message.endswith(
        "Customer CUS-001 holds no Drug licence, wholesale, and neither does "
        "its parent Parent Stores."
    )


def test_the_shop_s_own_outranks_the_parent_s(family: _Family) -> None:
    """A shop holding its own is judged on its own, valid or lapsed."""
    family.parent_holds()
    family.hold(customer=True)
    family.sale()
    assert family.last.findings == []
    assert family.last.covered_by_parent == []


def test_a_shop_whose_own_has_lapsed_is_not_rescued_by_its_parent(
    family: _Family,
) -> None:
    """Own first: the lapsed licence is the shop's to renew."""
    family.parent_holds()
    family.hold(customer=True, valid_to=date(2026, 7, 31))
    family.sale()
    [finding] = family.last.findings
    assert finding.shortfall is LicenceShortfall.EXPIRED
    assert finding.parent_name is None
    assert finding.licence_number == "DL-C"
    assert family.last.covered_by_parent == []


def test_with_the_setting_on_the_shop_is_refused(family: _Family) -> None:
    """Strict: the parent's valid licence no longer counts."""
    family.parent_holds()
    family.strict()
    assert family.checks.settings_response(family.firm.id).shop_needs_own_licence
    family.sale()
    [finding] = family.last.findings
    assert finding.shortfall is LicenceShortfall.MISSING
    assert finding.parent_name is None
    assert finding.message.endswith(
        "Customer CUS-001 holds no Drug licence, wholesale."
    )
    assert family.last.covered_by_parent == []


def test_a_write_without_the_switch_leaves_it_as_it_is(family: _Family) -> None:
    """Absent means leave alone; an explicit false switches it off."""
    family.strict()
    family.policy(LicenceEnforcement.BLOCK)
    stored = family.checks.settings_response(family.firm.id)
    assert stored.shop_needs_own_licence
    assert stored.sale_enforcement is LicenceEnforcement.BLOCK
    family.strict(on=False)
    assert not family.checks.settings_response(family.firm.id).shop_needs_own_licence


def test_a_firm_that_never_chose_starts_with_it_off(family: _Family) -> None:
    """The default policy covers a shop by its parent."""
    response = family.checks.settings_response(family.firm.id)
    assert not response.is_configured
    assert not response.shop_needs_own_licence


def test_goods_needing_no_licence_are_not_checked_at_all(family: _Family) -> None:
    """Neither a finding nor a cover for a line that needs nothing."""
    family.parent_holds()
    family.product.category_id = None
    family.session.commit()
    result = family.checks.check_sale(
        firm_id=family.firm.id,
        customer_id=family.customer.id,
        branch_id=family.branch.id,
        on=ORDER_DATE,
        lines=[LicenceLine(1, family.product.id)],
    )
    assert result.findings == []
    assert result.covered_by_parent == []


def test_a_customer_with_no_parent_is_judged_as_before(family: _Family) -> None:
    """Another customer's licence never stands in."""
    family.parent_holds()
    family.customer.parent_customer_id = None
    family.session.commit()
    family.sale()
    [finding] = family.last.findings
    assert finding.message.endswith(
        "Customer CUS-001 holds no Drug licence, wholesale."
    )


def test_approval_goes_ahead_and_the_timeline_says_whose_was_used(
    family: _Family,
) -> None:
    """Block is on and nothing is short; the cover is recorded all the same."""
    family.parent_holds()
    family.policy(LicenceEnforcement.BLOCK)
    order_id = family.order()
    SalesOrderService(family.session).approve_order(
        order_id, firm_scope=family.firm.id, actor_id=family.actor_id
    )
    event = family.approval_event(order_id)
    assert event.remarks is not None
    assert "its parent Parent Stores's" in event.remarks
    assert event.details_json is not None
    assert "licence_warning" not in event.details_json
    [cover] = event.details_json["licence_parent_cover"]["covers"]
    assert cover["licence_number"] == "DL-P"


def test_the_bill_prints_the_licence_that_was_used(family: _Family) -> None:
    """The parent's number prints for the shop; strict, or own held, it does not."""
    family.parent_holds()
    numbers = TradeLicenceService(family.session)

    def printed() -> list[tuple[str, str]]:
        """Return what the shop's bill would print."""
        return numbers.valid_numbers(
            firm_id=family.firm.id, on=ORDER_DATE, customer_id=family.customer.id
        )

    assert printed() == [("Drug licence, wholesale", "DL-P")]
    family.strict()
    assert printed() == []
    family.strict(on=False)
    # The shop's own, lapsed: neither prints, as the check found it short.
    family.hold(customer=True, valid_to=date(2026, 7, 31))
    assert printed() == []
    # The parent's own bill is not changed by having shops.
    assert numbers.valid_numbers(
        firm_id=family.firm.id, on=ORDER_DATE, customer_id=family.parent.id
    ) == [("Drug licence, wholesale", "DL-P")]


def test_a_supplier_s_branch_is_covered_by_its_main_office(family: _Family) -> None:
    """The buying check: own first, else the main office's, unless strict."""
    office = Vendor(
        firm_id=family.firm.id,
        code="VEN-HO",
        name="Pharma Supplies",
        display_name="Pharma Supplies",
        status="ACTIVE",
    )
    family.session.add(office)
    family.session.flush()
    branch = Vendor(
        firm_id=family.firm.id,
        code="VEN-BR",
        name="Pharma Supplies, Hubli",
        display_name="Pharma Supplies, Hubli",
        status="ACTIVE",
        parent_vendor_id=office.id,
    )
    family.session.add(branch)
    family.session.add(
        TradeLicence(
            firm_id=family.firm.id,
            licence_type_id=family.drug.id,
            holder_type="VENDOR",
            vendor_id=office.id,
            licence_number="DL-HO",
            valid_to=date(2027, 3, 31),
        )
    )
    family.session.commit()
    lines = [LicenceLine(1, family.product.id)]

    def judged() -> tuple[list[str], list[str]]:
        """Return the finding and the cover messages for the branch."""
        result = family.checks.check_purchase(
            firm_id=family.firm.id, vendor_id=branch.id, on=ORDER_DATE, lines=lines
        )
        return (
            [item.message for item in result.findings],
            [item.message for item in result.covered_by_parent],
        )

    findings, covers = judged()
    assert findings == []
    assert len(covers) == 1
    assert "its parent Pharma Supplies's Drug licence, wholesale DL-HO was used" in (
        covers[0]
    )
    family.strict()
    findings, covers = judged()
    assert covers == []
    assert len(findings) == 1
    assert findings[0].endswith(
        "Pharma Supplies, Hubli holds no Drug licence, wholesale."
    )
