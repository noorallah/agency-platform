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

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.firms.models import Firm
from app.vendors.schemas import (
    VendorAddressInput,
    VendorCategoryWrite,
    VendorContactInput,
    VendorCreate,
    VendorTypeWrite,
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


def test_an_edit_does_not_clear_the_header_fields_it_does_not_mention() -> None:
    """The collections' rule, arrived at for the header a year later.

    `_vendor_values` dumped the whole write model, defaults included, so a
    `PUT` naming only a phone number also set `gstin`, `pan`, `website` and
    the rest back to null. The two halves of one request disagreed about what
    silence means -- the collections left alone what was absent while the
    header read the same absence as an instruction to clear.

    The same shape wiped a product's tax group and units on 2026-09-15, which
    is how this one came to be looked for.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = VendorService(session)
    vendor_id = service.create(
        VendorCreate(
            code="V900",
            name="Full Supplier",
            gstin="29ABCDE1234F1Z5",
            pan="ABCDE1234F",
            website="https://supplier.example",
            phone="+918011111111",
        ),
        firm_id=firm.id,
        actor_id=actor,
    ).id

    updated = service.update(
        vendor_id,
        VendorUpdate(code="V900", name="Full Supplier", phone="+918022222222"),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert updated.phone == "+918022222222", "what was sent is written"
    assert updated.gstin == "29ABCDE1234F1Z5"
    assert updated.pan == "ABCDE1234F"
    assert updated.website == "https://supplier.example"


def test_an_explicit_null_still_clears_a_header_field() -> None:
    """Absent and null must stay different, or nothing could ever be cleared."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = VendorService(session)
    vendor_id = service.create(
        VendorCreate(code="V901", name="Supplier", gstin="29ABCDE1234F1Z5"),
        firm_id=firm.id,
        actor_id=actor,
    ).id

    updated = service.update(
        vendor_id,
        VendorUpdate(code="V901", name="Supplier", gstin=None),
        firm_scope=firm.id,
        actor_id=actor,
    )

    assert updated.gstin is None, "the caller set it, so it is an instruction"


def test_a_category_a_vendor_still_names_cannot_be_retired() -> None:
    """`ondelete="RESTRICT"` reads like protection on a soft-deleted table.

    It is not: a soft delete never reaches the database's referential check,
    so the category simply vanished from every picker while the vendor went on
    naming it. Products have refused this since they were written; vendors did
    not, and the inconsistency was found writing the functional guide.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = VendorService(session)
    category = service.create_category(
        VendorCategoryWrite(code="RAW", name="Raw materials"),
        firm_id=firm.id,
        actor_id=actor,
    )
    vendor = service.create(
        VendorCreate(code="V902", name="Held Supplier", category_id=category.id),
        firm_id=firm.id,
        actor_id=actor,
    )

    with pytest.raises(ValidationError, match="used by 1 vendor"):
        service.delete_category(category.id, firm_id=firm.id, actor_id=actor)

    # Moved off it, the category goes.
    service.update(
        vendor.id,
        VendorUpdate(code="V902", name="Held Supplier", category_id=None),
        firm_scope=firm.id,
        actor_id=actor,
    )
    service.delete_category(category.id, firm_id=firm.id, actor_id=actor)


def test_a_type_a_vendor_still_names_cannot_be_retired() -> None:
    """The same guard, the other master -- one helper serves both."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = VendorService(session)
    vendor_type = service.create_type(
        VendorTypeWrite(code="MFR", name="Manufacturer"),
        firm_id=firm.id,
        actor_id=actor,
    )
    service.create(
        VendorCreate(code="V903", name="Maker", type_id=vendor_type.id),
        firm_id=firm.id,
        actor_id=actor,
    )

    with pytest.raises(ValidationError, match="used by 1 vendor"):
        service.delete_type(vendor_type.id, firm_id=firm.id, actor_id=actor)


def test_a_deleted_vendor_does_not_hold_its_category_open() -> None:
    """The guard counts live vendors: a retired one is not somebody's problem."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = VendorService(session)
    category = service.create_category(
        VendorCategoryWrite(code="OLD", name="Old"), firm_id=firm.id, actor_id=actor
    )
    vendor = service.create(
        VendorCreate(code="V904", name="Gone", category_id=category.id),
        firm_id=firm.id,
        actor_id=actor,
    )
    service.delete(vendor.id, firm_scope=firm.id, actor_id=actor)

    service.delete_category(category.id, firm_id=firm.id, actor_id=actor)
