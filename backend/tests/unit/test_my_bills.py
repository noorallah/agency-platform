"""A collector's own list, and the role that holds only that (backlog 123, M5).

The bills handed to one person and still out, and beside each customer's the
other unpaid bills of that customer, marked apart. Nothing of anybody else's
bag and nothing of a customer he carries no bill of.
"""

import inspect
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.collections.api.router import list_my_bills
from app.collections.schemas import HandoverTakeBack, MyBillRow
from app.collections.services import BillHandoverService
from app.common.scope import ResolvedFirmScope
from app.identity.models import Role, UserTemplate, UserTemplateRole
from app.identity.system_seed import (
    FIRM_ROLE_CODES,
    PERMISSION_GROUPS,
    ROLE_PERMISSION_CODES,
    SYSTEM_USER_TEMPLATES,
    seed_system_rbac,
)
from app.sales_invoice.models import SalesInvoice
from tests.unit import test_sales_order_module as sales
from tests.unit.test_bill_handovers import TODAY, _give, _out
from tests.unit.test_collection_follow_up import (
    _actor,
    _bill,
    _counting,
    _customer,
    _member,
    _pay,
    _total,
    _world,
)
from tests.unit.test_sales_chain_synthesis import _Firm


def _mine(setup: _Firm, collector: UUID) -> list[MyBillRow]:
    """Read the collector's own list."""
    return BillHandoverService(setup.session).my_bills(
        setup.firm.id, collector_id=collector, today=TODAY
    )


def _ids(rows: list[MyBillRow], *, handed: bool) -> set[UUID]:
    """Return the bills of the list that are, or are not, in the bag."""
    return {row.invoice_id for row in rows if row.handed_to_me is handed}


# ---- the list -------------------------------------------------------------


def test_a_collector_sees_the_bills_handed_to_him_and_nobody_elses() -> None:
    """Two bags, two lists, and a bill in the office in neither."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    second, third = _customer(setup, "C-MINE-2"), _customer(setup, "C-MINE-3")
    with_ravi, with_sita = _bill(setup), _bill(setup, second)
    _bill(setup, third)
    _give(setup, ravi, with_ravi)
    _give(setup, sita, with_sita)

    ravis, sitas = _mine(setup, ravi), _mine(setup, sita)

    assert [row.invoice_id for row in ravis] == [with_ravi.id]
    assert [row.invoice_id for row in sitas] == [with_sita.id]
    row = ravis[0]
    assert row.handed_to_me is True
    assert row.handover_id == _out(setup)[with_ravi.id].id
    assert row.handed_on == TODAY
    assert row.outstanding == _total(with_ravi)
    assert row.days_overdue == (TODAY - date(2026, 8, 9)).days
    assert row.customer_code == setup.customer.code


def test_the_same_customers_other_unpaid_bills_are_listed_and_marked_apart() -> None:
    """The customer's Try for A14: both, marked apart."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    other_customer = _customer(setup, "C-MINE-4")
    handed, older, with_sita = _bill(setup), _bill(setup), _bill(setup)
    stranger = _bill(setup, other_customer)
    _give(setup, ravi, handed)
    _give(setup, sita, with_sita)

    rows = _mine(setup, ravi)

    assert _ids(rows, handed=True) == {handed.id}
    assert _ids(rows, handed=False) == {older.id, with_sita.id}
    assert stranger.id not in {row.invoice_id for row in rows}
    # In the bag first, then the customer's others.
    assert rows[0].invoice_id == handed.id
    # Whose bag another bill is in is not his to read.
    apart = [row for row in rows if not row.handed_to_me]
    assert all(row.handover_id is None and row.handed_on is None for row in apart)


def test_the_list_is_by_customer_with_the_bag_first() -> None:
    """Each customer's rows sit together, handed bills above the others."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    second = _customer(setup, "C-MINE-5")
    first_other, first_handed = _bill(setup), _bill(setup)
    second_handed = _bill(setup, second)
    _give(setup, ravi, first_handed, second_handed)

    rows = _mine(setup, ravi)

    assert {row.invoice_id for row in rows} == {
        first_handed.id,
        first_other.id,
        second_handed.id,
    }
    ours = [row for row in rows if row.customer_id == setup.customer.id]
    assert [row.invoice_id for row in ours] == [first_handed.id, first_other.id]
    names = [row.customer_name.casefold() for row in rows]
    assert names == sorted(names)


def test_a_bill_taken_back_leaves_the_list_with_its_neighbours() -> None:
    """Nothing in the bag, nothing on the list."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    handed = _bill(setup)
    _bill(setup)
    _give(setup, ravi, handed)
    assert len(_mine(setup, ravi)) == 2

    BillHandoverService(setup.session).take_back(
        HandoverTakeBack(handover_ids=[_out(setup)[handed.id].id]),
        firm_id=setup.firm.id,
        actor_id=_actor(setup),
    )

    assert _mine(setup, ravi) == []


def test_a_part_paid_bill_shows_what_it_still_owes_and_a_paid_one_goes() -> None:
    """What the list says is owed is what Record Receipt says."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    second = _customer(setup, "C-MINE-6")
    part, whole = _bill(setup), _bill(setup, second)
    _give(setup, ravi, part, whole)
    _pay(setup, part, Decimal("100.00"), date(2026, 8, 12))
    _pay(setup, whole, _total(whole), date(2026, 8, 12))

    rows = _mine(setup, ravi)

    assert [row.invoice_id for row in rows] == [part.id]
    assert rows[0].outstanding == _total(part) - Decimal("100.00")


def test_a_member_who_carries_nothing_reads_an_empty_list_cheaply() -> None:
    """No bag, no read of the firm's unpaid bills."""
    setup = _world()
    idle = _member(setup, "Idle Member")
    _bill(setup)

    with _counting(setup.session) as statements:
        rows = _mine(setup, idle)

    assert rows == []
    assert len(statements) == 1


def test_the_list_costs_the_same_however_many_bills_it_holds() -> None:
    """Built in bulk, not row by row."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")

    def cost() -> int:
        """Count the statements behind the list."""
        with _counting(setup.session) as statements:
            _mine(setup, ravi)
        return len(statements)

    _give(setup, ravi, _bill(setup))
    few = cost()
    more: list[SalesInvoice] = [_bill(setup) for _ in range(4)]
    _give(setup, ravi, *more[:2])

    assert cost() == few


def test_the_page_is_cut_from_the_same_list() -> None:
    """Page two of two holds the rest."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    _give(setup, ravi, _bill(setup), _bill(setup), _bill(setup))

    page, total = BillHandoverService(setup.session).my_bills_page(
        setup.firm.id, collector_id=ravi, page=2, page_size=2
    )

    assert (len(page), total) == (1, 3)


# ---- the route ------------------------------------------------------------


def test_the_route_reads_the_callers_bag_and_takes_no_name() -> None:
    """Whose bag it is comes from the token; no parameter names a person."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    with_ravi = _bill(setup)
    _give(setup, ravi, with_ravi)

    def read(actor: UUID) -> list[UUID]:
        """Call the route as ``actor``."""
        scope = ResolvedFirmScope(
            principal=sales._principal(actor, {"COLLECTION_OWN_VIEW"}),
            firm_id=setup.firm.id,
        )
        answer = list_my_bills(scope=scope, page=1, page_size=50, db=setup.session)
        return [row.invoice_id for row in answer.data]

    assert read(ravi) == [with_ravi.id]
    assert read(sita) == []
    asked = set(inspect.signature(list_my_bills).parameters)
    assert asked == {"scope", "page", "page_size", "db"}


# ---- the role -------------------------------------------------------------


def test_the_bill_collector_holds_his_own_list_and_nothing_else() -> None:
    """One code. Not the firm's bills, not its customers, not its money."""
    assert "COLLECTION_OWN_VIEW" in PERMISSION_GROUPS["accounting"]
    assert ROLE_PERMISSION_CODES["BILL_COLLECTOR"] == {"COLLECTION_OWN_VIEW"}
    assert "BILL_COLLECTOR" in FIRM_ROLE_CODES


def test_the_people_who_run_the_firm_may_carry_bills_too() -> None:
    """An owner who collects himself reads his own bag; a cashier does not."""
    for role in ("FIRM_ADMIN", "FIRM_MANAGER", "ACCOUNTANT"):
        assert "COLLECTION_OWN_VIEW" in ROLE_PERMISSION_CODES[role]
    assert "COLLECTION_OWN_VIEW" not in ROLE_PERMISSION_CODES["CASHIER"]
    assert "COLLECTION_OWN_VIEW" not in ROLE_PERMISSION_CODES["SALES_EXECUTIVE"]


def test_a_firm_hires_a_bill_collector_by_name() -> None:
    """The job template exists and is the one role."""
    bundles = {code: roles for code, _, _, roles in SYSTEM_USER_TEMPLATES}
    assert bundles["bill-collector"] == ("BILL_COLLECTOR",)
    setup = _world()
    seed_system_rbac(setup.session)
    setup.session.commit()

    template = setup.session.scalar(
        select(UserTemplate).where(UserTemplate.code == "bill-collector")
    )
    assert template is not None and template.firm_id is None
    held = setup.session.scalars(
        select(Role.code)
        .join(UserTemplateRole, UserTemplateRole.role_id == Role.id)
        .where(UserTemplateRole.template_id == template.id)
    ).all()
    assert held == ["BILL_COLLECTOR"]
