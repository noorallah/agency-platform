"""A vendor edit must not erase what the caller did not send.

`update_vendor` replaces its six child collections rather than merging them,
and every one of them defaulted to an empty list -- so a client that did not
manage a collection wiped it by omission. The desktop vendor dialog sent all
six empty on every save, which destroyed the vendor's addresses, contacts, bank
accounts, tax details, attachments and notes each time somebody corrected a
phone number. One seeded vendor had already lost its address that way.

`None` now means "leave them alone" and `[]` still means "remove them all",
which is the distinction that makes a partial client safe without taking the
ability to clear a collection away from a complete one.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.firms.models import Firm
from app.vendors.schemas import (
    VendorAddressInput,
    VendorContactInput,
    VendorCreate,
    VendorUpdate,
)
from app.vendors.services import VendorService


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
        name="Vendor Firm",
        code="VEN01",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _create(service: VendorService, firm_id: UUID, actor: UUID) -> UUID:
    vendor = service.create(
        VendorCreate(
            code="V001",
            name="Supplier One",
            addresses=[
                VendorAddressInput(
                    address_type="BILLING",
                    address_line1="11 Supplier Street",
                    is_primary=True,
                )
            ],
            contacts=[
                VendorContactInput(name="Asha", is_primary=True),
            ],
        ),
        firm_id=firm_id,
        actor_id=actor,
    )
    return vendor.id


def _live(rows: list[object]) -> int:
    return sum(0 if getattr(row, "is_deleted", False) else 1 for row in rows)


def test_an_edit_that_mentions_no_collections_keeps_them_all() -> None:
    """The defect: the desktop sent six empty lists on every save."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = VendorService(session)
    vendor_id = _create(service, firm.id, actor)

    updated = service.update(
        vendor_id,
        VendorUpdate(code="V001", name="Supplier One Renamed"),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert updated.name == "Supplier One Renamed"
    assert _live(list(updated.addresses)) == 1
    assert _live(list(updated.contacts)) == 1


def test_an_explicit_empty_list_still_clears_a_collection() -> None:
    """Absent and empty must stay different, or nothing could ever be cleared."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = VendorService(session)
    vendor_id = _create(service, firm.id, actor)

    updated = service.update(
        vendor_id,
        VendorUpdate(code="V001", name="Supplier One", addresses=[]),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert _live(list(updated.addresses)) == 0
    # The collection that was not mentioned is untouched.
    assert _live(list(updated.contacts)) == 1


def test_a_collection_that_is_sent_is_still_reconciled() -> None:
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = VendorService(session)
    vendor_id = _create(service, firm.id, actor)

    updated = service.update(
        vendor_id,
        VendorUpdate(
            code="V001",
            name="Supplier One",
            addresses=[
                VendorAddressInput(
                    address_type="SHIPPING",
                    address_line1="99 New Road",
                    is_primary=True,
                )
            ],
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )

    live = [row for row in updated.addresses if not row.is_deleted]
    assert [row.address_line1 for row in live] == ["99 New Road"]


def test_a_vendor_address_can_name_its_city() -> None:
    """The question this branch started from.

    `vendor_addresses` has no text city or postal code at all -- the only way
    to say where an address is, is through the geography masters. The API has
    always accepted those ids; nothing sent them.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = VendorService(session)
    city = uuid4()

    vendor = service.create(
        VendorCreate(
            code="V002",
            name="Supplier Two",
            addresses=[
                VendorAddressInput(
                    address_type="BILLING",
                    address_line1="1 Big Street",
                    city_id=city,
                    is_primary=True,
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor,
    )

    assert [row.city_id for row in vendor.addresses] == [city]
