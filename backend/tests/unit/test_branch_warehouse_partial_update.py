"""A branch or warehouse edit must not erase what the caller did not send.

Every field on ``BranchWrite`` and ``WarehouseWrite`` carries a default, and
the update path dumped the whole model and assigned every key -- so an omitted
field was written as ``None`` (or ``False``) rather than left alone. The
desktop form edits neither the address nor the geography keys and hardcoded
``is_default: false`` and ``gst_registration: false``, so one rename cleared
the branch's street lines, its city, its default flag and its GST
registration, and a warehouse rename cleared all ten capability flags.

``None`` on an update now means "leave it alone" and an explicit ``null``
still clears, which is the distinction that makes a partial client safe
without taking the ability to clear a field away from a complete one. Create
is unchanged: there, a default really is the value to store.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.schemas import (
    BranchCreate,
    BranchUpdate,
    WarehouseCreate,
    WarehouseUpdate,
)
from app.branches.services import BranchWarehouseService
from app.core.database.base import Base
from app.firms.models import Firm


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session) -> Firm:
    row = Firm(
        name="Branch Firm",
        code="BR01",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _branch(
    service: BranchWarehouseService, firm_id: UUID, actor: UUID, city: UUID
) -> UUID:
    branch = service.create_branch(
        BranchCreate(
            code="HO",
            name="Head Office",
            address_line1="9 Mount Road",
            address_line2="Near Spencer Plaza",
            city_id=city,
            gst_registration=True,
            is_default=True,
        ),
        firm_id=firm_id,
        actor_id=actor,
    )
    return branch.id


def test_a_rename_keeps_the_address_the_form_cannot_show() -> None:
    """The defect: the desktop form sends neither address nor place."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    city = uuid4()
    service = BranchWarehouseService(session)
    branch_id = _branch(service, firm.id, actor, city)

    updated = service.update_branch(
        branch_id,
        BranchUpdate(code="HO", name="Head Office Renamed"),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert updated.name == "Head Office Renamed"
    assert updated.address_line1 == "9 Mount Road"
    assert updated.address_line2 == "Near Spencer Plaza"
    assert updated.city_id == city
    assert updated.gst_registration is True
    assert updated.is_default is True


def test_an_explicit_null_still_clears_an_address() -> None:
    """Absent and explicit must stay different, or nothing could be cleared."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    city = uuid4()
    service = BranchWarehouseService(session)
    branch_id = _branch(service, firm.id, actor, city)

    updated = service.update_branch(
        branch_id,
        BranchUpdate(code="HO", name="Head Office", address_line1=None, city_id=None),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert updated.address_line1 is None
    assert updated.city_id is None
    # The line that was not mentioned is untouched.
    assert updated.address_line2 == "Near Spencer Plaza"


def test_a_field_that_is_sent_is_still_applied() -> None:
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    city = uuid4()
    moved = uuid4()
    service = BranchWarehouseService(session)
    branch_id = _branch(service, firm.id, actor, city)

    updated = service.update_branch(
        branch_id,
        BranchUpdate(code="HO", name="Head Office", city_id=moved),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert updated.city_id == moved


def test_a_branch_that_is_not_default_can_still_be_promoted() -> None:
    """`is_default` is read from the row when absent, not assumed false."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = BranchWarehouseService(session)
    first = _branch(service, firm.id, actor, uuid4())
    second = service.create_branch(
        BranchCreate(code="BR2", name="Second"),
        firm_id=firm.id,
        actor_id=actor,
    )

    service.update_branch(
        second.id,
        BranchUpdate(code="BR2", name="Second", is_default=True),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert service.get_branch(second.id, firm_scope=firm.id).is_default is True
    # Promoting one demotes the other, as it always did.
    assert service.get_branch(first, firm_scope=firm.id).is_default is False


def test_a_warehouse_rename_keeps_its_capability_flags() -> None:
    """Ten booleans the desktop hardcoded to false on every save."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    city = uuid4()
    service = BranchWarehouseService(session)
    branch_id = _branch(service, firm.id, actor, city)
    warehouse = service.create_warehouse(
        WarehouseCreate(
            branch_id=branch_id,
            code="WH1",
            name="Main Store",
            address_line1="12 Dock Road",
            city_id=city,
            capacity=Decimal("500"),
            capacity_unit="KG",
            cold_storage=True,
            hazardous_storage=True,
            has_loading_dock=True,
        ),
        firm_id=firm.id,
        actor_id=actor,
    )

    updated = service.update_warehouse(
        warehouse.id,
        WarehouseUpdate(branch_id=branch_id, code="WH1", name="Main Store 2"),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert updated.name == "Main Store 2"
    assert updated.address_line1 == "12 Dock Road"
    assert updated.city_id == city
    assert updated.cold_storage is True
    assert updated.hazardous_storage is True
    assert updated.has_loading_dock is True
    assert updated.capacity == Decimal("500")
