"""Backlog 125 (row M7): a parent buyer with shops; a GST number held once.

A chain is one parent customer with a customer per shop under it. The GST
number is typed on the parent; a shop that sends none takes it, as a copy the
server writes and marks, so every reader of ``gst_number`` bills the shop
under it. A number typed on a customer is on one live customer of the firm.
"""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.common.party_merge import PartyMergeService, PartyMergeWrite
from app.core.exceptions import ConflictError, ValidationError
from app.customers.api.router import (
    check_customer_identity,
    create_customer,
    customer_family,
    get_customer,
    list_customers,
    update_customer,
)
from app.customers.models import Customer
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.customers.services import CustomerService
from app.identity.models import UserFirm
from tests.unit.test_customer_import_file import _csv, _run
from tests.unit.test_customer_management import (
    _firm,
    _firm_scope,
    _principal,
    _session_factory,
)

PAN = "AAACD1234M"
GSTIN = f"36{PAN}1Z5"
OTHER_STATE = f"29{PAN}1Z3"


def _data(code: str, **fields: object) -> CustomerCreate:
    """Build a business customer with no opening balance."""
    return CustomerCreate.model_validate(
        {
            "code": code,
            "customer_type": "BUSINESS",
            "name": "DMart",
            "currency_code": "INR",
            **fields,
        }
    )


def _edit(code: str, **fields: object) -> CustomerUpdate:
    """Build an update that names only the required fields and ``fields``."""
    return CustomerUpdate.model_validate(
        {
            "code": code,
            "customer_type": "BUSINESS",
            "name": "DMart",
            "currency_code": "INR",
            **fields,
        }
    )


def _scope() -> tuple[Session, object]:
    """Return a session and a scope that may create, read and edit customers."""
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "M7")
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    setup.close()
    session = factory()
    principal = _principal(
        user_id, {"CUSTOMER_CREATE", "CUSTOMER_VIEW", "CUSTOMER_UPDATE"}
    )
    return session, _firm_scope(principal, session, firm.id)


def _create(session: Session, scope: object, code: str, **fields: object) -> UUID:
    """Create one customer through the route and return its id."""
    return create_customer(
        _data(code, **fields), scope, session  # type: ignore[arg-type]
    ).data.id


def _row(session: Session, customer_id: UUID) -> Customer:
    """Read one customer afresh."""
    session.expire_all()
    row = session.get(Customer, customer_id)
    assert row is not None
    return row


def test_a_parent_with_three_shops_and_no_second_holder_of_the_number() -> None:
    """The row's own trial: three shops take the number; a second parent cannot."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    shops = [
        create_customer(
            _data(code, parent_customer_id=parent),
            scope,  # type: ignore[arg-type]
            session,
        )
        for code in ("DM-KUK", "DM-MIY", "DM-GAC")
    ]

    for shop in shops:
        assert shop.data.gst_number == GSTIN
        assert shop.data.gst_number_from_parent is True
        assert shop.data.pan_number == PAN
        assert shop.data.parent_customer_id == parent
        assert shop.data.parent_code == "DMART"
        assert shop.data.parent_name == "DMart"
    read = get_customer(parent, scope, Response(), False, session)  # type: ignore[arg-type]
    assert read.data.shop_count == 3
    assert read.data.gst_number_from_parent is False

    with pytest.raises(ConflictError, match="held by DMART DMart") as refused:
        create_customer(
            _data("DMART2", gst_number=GSTIN), scope, session  # type: ignore[arg-type]
        )
    assert "Make this customer a shop of DMART" in str(refused.value)


def test_a_shop_in_another_state_keeps_its_own_number() -> None:
    """Its number is its own, and nobody else may take it."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    shop = create_customer(
        _data("DM-BLR", parent_customer_id=parent, gst_number=OTHER_STATE),
        scope,  # type: ignore[arg-type]
        session,
    )

    assert shop.data.gst_number == OTHER_STATE
    assert shop.data.gst_number_from_parent is False
    with pytest.raises(ConflictError, match="held by DM-BLR"):
        _create(session, scope, "ELSE", gst_number=OTHER_STATE)


def test_a_form_that_sends_back_the_number_it_was_shown_still_inherits() -> None:
    """A shop's form echoes the parent's number; that is not a number typed."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    typed = create_customer(
        _data("DM-KUK", parent_customer_id=parent, gst_number=GSTIN),
        scope,  # type: ignore[arg-type]
        session,
    )
    assert typed.data.gst_number_from_parent is True

    saved = update_customer(
        typed.data.id,
        _edit("DM-KUK", parent_customer_id=parent, gst_number=GSTIN, notes="x"),
        scope,  # type: ignore[arg-type]
        Response(),
        session,
    )

    assert saved.data.gst_number == GSTIN
    assert saved.data.gst_number_from_parent is True


def test_an_edit_that_names_neither_leaves_the_family_alone() -> None:
    """A phone number corrected on a shop does not take it out of its family."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    shop = _create(session, scope, "DM-KUK", parent_customer_id=parent)

    update_customer(
        shop,
        _edit("DM-KUK", notes="Open till ten"),
        scope,  # type: ignore[arg-type]
        Response(),
        session,
    )

    row = _row(session, shop)
    assert row.parent_customer_id == parent
    assert (row.gst_number, row.gst_number_from_parent) == (GSTIN, True)


def test_the_parents_new_number_reaches_the_shops_that_take_it() -> None:
    """The copies move with the number, each with its own audit row."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    taking = _create(session, scope, "DM-KUK", parent_customer_id=parent)
    own = _create(
        session, scope, "DM-BLR", parent_customer_id=parent, gst_number=OTHER_STATE
    )
    new_pan = "AAACD9999M"
    new_number = f"36{new_pan}1Z5"

    update_customer(
        parent,
        _edit("DMART", gst_number=new_number, pan_number=new_pan),
        scope,  # type: ignore[arg-type]
        Response(),
        session,
    )

    shop = _row(session, taking)
    assert (shop.gst_number, shop.pan_number) == (new_number, new_pan)
    assert shop.gst_number_from_parent is True
    assert _row(session, own).gst_number == OTHER_STATE
    trail = session.scalars(
        select(AuditLog).where(
            AuditLog.entity_id == str(taking), AuditLog.action == "customer.updated"
        )
    ).all()
    assert len(trail) == 1
    # The number the family gave up is free for somebody else.
    _create(session, scope, "NEWCO", gst_number=GSTIN)


def test_a_parent_that_clears_its_number_clears_the_copies() -> None:
    """A buyer that leaves GST takes its shops with it."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    shop = _create(session, scope, "DM-KUK", parent_customer_id=parent)

    update_customer(
        parent,
        _edit("DMART", gst_number=None),
        scope,  # type: ignore[arg-type]
        Response(),
        session,
    )

    row = _row(session, shop)
    assert row.gst_number is None
    assert row.gst_number_from_parent is True


def test_shops_sit_one_level_under_a_parent() -> None:
    """No shop of a shop, no parent under a parent, nobody its own parent."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    shop = _create(session, scope, "DM-KUK", parent_customer_id=parent)
    loner = _create(session, scope, "LONER")

    with pytest.raises(ValidationError, match="is itself a shop of DMART"):
        _create(session, scope, "DEEP", parent_customer_id=shop)
    with pytest.raises(ConflictError, match="parent of 1 shop"):
        update_customer(
            parent,
            _edit("DMART", parent_customer_id=loner),
            scope,  # type: ignore[arg-type]
            Response(),
            session,
        )
    with pytest.raises(ValidationError, match="its own parent"):
        update_customer(
            loner,
            _edit("LONER", parent_customer_id=loner),
            scope,  # type: ignore[arg-type]
            Response(),
            session,
        )
    with pytest.raises(ValidationError, match="not one of this firm"):
        _create(session, scope, "STRAY", parent_customer_id=uuid4())


def test_a_customer_taken_out_gives_the_number_back() -> None:
    """It does not keep a copy of its old parent's number as its own."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    shop = _create(session, scope, "DM-KUK", parent_customer_id=parent)

    saved = update_customer(
        shop,
        _edit("DM-KUK", parent_customer_id=None, gst_number=GSTIN),
        scope,  # type: ignore[arg-type]
        Response(),
        session,
    )

    assert saved.data.parent_customer_id is None
    assert saved.data.gst_number is None
    assert saved.data.gst_number_from_parent is False


def test_an_existing_customer_is_put_under_a_parent() -> None:
    """A shop entered before its parent joins it and takes the number."""
    session, scope = _scope()
    shop = _create(session, scope, "DM-KUK")
    parent = _create(session, scope, "DMART", gst_number=GSTIN)

    saved = update_customer(
        shop,
        _edit("DM-KUK", parent_customer_id=parent),
        scope,  # type: ignore[arg-type]
        Response(),
        session,
    )

    assert saved.data.gst_number == GSTIN
    assert saved.data.gst_number_from_parent is True
    assert saved.data.pan_number == PAN


def test_a_parent_with_shops_is_not_deleted_or_merged_away() -> None:
    """A soft delete never reaches the foreign key, so the service refuses."""
    session, scope = _scope()
    firm_id = scope.firm_id  # type: ignore[attr-defined]
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    shop = _create(session, scope, "DM-KUK", parent_customer_id=parent)
    other = _create(session, scope, "OTHER")
    service = CustomerService(session)

    with pytest.raises(ConflictError, match="parent of 1 shop"):
        service.delete(parent, firm_scope=firm_id, actor_id=uuid4())
    with pytest.raises(ValidationError, match="parent of 1 shop"):
        PartyMergeService(session).merge(
            "CUSTOMER",
            other,
            PartyMergeWrite(duplicate_id=parent, reason="Typed twice"),
            firm_id=firm_id,
            actor_id=uuid4(),
        )

    service.delete(shop, firm_scope=firm_id, actor_id=uuid4())
    service.delete(parent, firm_scope=firm_id, actor_id=uuid4())
    assert _row(session, parent).is_deleted is True


def test_a_restore_does_not_walk_into_a_family_that_moved_on() -> None:
    """A deleted shop does not hold its parent, nor a deleted holder its number."""
    session, scope = _scope()
    firm_id = scope.firm_id  # type: ignore[attr-defined]
    service = CustomerService(session)
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    shop = _create(session, scope, "DM-KUK", parent_customer_id=parent)
    service.delete(shop, firm_scope=firm_id, actor_id=uuid4())
    service.delete(parent, firm_scope=firm_id, actor_id=uuid4())

    with pytest.raises(ConflictError, match="its parent DMART is deleted"):
        service.restore(shop, firm_scope=firm_id, actor_id=uuid4())

    _create(session, scope, "NEWCO", gst_number=GSTIN)
    with pytest.raises(ConflictError, match="cannot be restored: GST number"):
        service.restore(parent, firm_scope=firm_id, actor_id=uuid4())


def test_the_family_adds_up_and_reads_the_same_from_a_shop() -> None:
    """One total for the buyer, asked of the parent or of any shop."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    first = _create(session, scope, "DM-KUK", parent_customer_id=parent)
    second = _create(session, scope, "DM-MIY", parent_customer_id=parent)
    for customer_id, owed in ((parent, "100.00"), (first, "250.50"), (second, "0")):
        row = session.get(Customer, customer_id)
        assert row is not None
        row.current_outstanding = Decimal(owed)
    session.commit()

    of_parent = customer_family(parent, scope, session).data  # type: ignore[arg-type]
    of_shop = customer_family(second, scope, session).data  # type: ignore[arg-type]

    assert [member.code for member in of_parent.members] == [
        "DMART",
        "DM-KUK",
        "DM-MIY",
    ]
    assert [member.is_parent for member in of_parent.members] == [True, False, False]
    assert str(of_parent.total_outstanding) == "350.50"
    assert of_shop == of_parent

    alone = _create(session, scope, "LONER")
    family = customer_family(alone, scope, session).data  # type: ignore[arg-type]
    assert [member.code for member in family.members] == ["LONER"]


def test_a_list_row_names_its_parent_and_counts_its_shops() -> None:
    """Read once for the page, not per row."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    _create(session, scope, "DM-KUK", parent_customer_id=parent)
    _create(session, scope, "DM-MIY", parent_customer_id=parent)

    page = list_customers(
        scope,  # type: ignore[arg-type]
        page=1,
        page_size=20,
        search=None,
        sort_by="code",
        sort_direction="asc",
        status_value=None,
        customer_type=None,
        firm_id=None,
        city=None,
        state_value=None,
        created_from=None,
        created_to=None,
        include_deleted=False,
        db=session,
    ).data

    assert [(row.code, row.parent_code, row.shop_count) for row in page] == [
        ("DM-KUK", "DMART", 0),
        ("DM-MIY", "DMART", 0),
        ("DMART", None, 2),
    ]


def test_the_form_is_told_whose_number_it_is_before_it_saves() -> None:
    """The check names the holder, never a shop that only takes the number."""
    session, scope = _scope()
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    _create(session, scope, "DM-KUK", parent_customer_id=parent)

    asked = check_customer_identity(
        scope, gst_number=GSTIN, pan_number=None, db=session  # type: ignore[arg-type]
    ).data

    assert [holder.code for holder in asked.holders] == ["DMART"]
    assert asked.message == (
        f"GSTIN {GSTIN} is held by DMART DMart: make this customer a shop of "
        "it and leave the GST number blank."
    )


def test_the_key_holds_one_typed_number_to_one_live_customer() -> None:
    """The index is the guard; the service check is only the message."""
    session, scope = _scope()
    firm_id = scope.firm_id  # type: ignore[attr-defined]
    parent = _create(session, scope, "DMART", gst_number=GSTIN)
    _create(session, scope, "DM-KUK", parent_customer_id=parent)

    session.add(
        Customer(
            firm_id=firm_id,
            code="RACE",
            customer_type="BUSINESS",
            name="Race",
            display_name="Race",
            currency_code="INR",
            status="ACTIVE",
            gst_number=GSTIN,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_a_file_puts_shops_under_a_parent_on_an_earlier_row() -> None:
    """ParentCode names a stored customer or one the same file brings."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session, "M7F")
    content = _csv(
        "Code,Name,GSTIN,ParentCode",
        f"DMART,DMart,{GSTIN},",
        "DM-KUK,DMart,,dmart",
        f"DM-BLR,DMart,{OTHER_STATE},DMART",
    )

    report = _run(session, firm.id, content, apply=True)

    assert report.issues == []
    rows = {
        row.code: row
        for row in factory().scalars(
            select(Customer).where(Customer.firm_id == firm.id)
        )
    }
    assert rows["DM-KUK"].parent_customer_id == rows["DMART"].id
    assert (rows["DM-KUK"].gst_number, rows["DM-KUK"].gst_number_from_parent) == (
        GSTIN,
        True,
    )
    assert rows["DM-BLR"].gst_number_from_parent is False

    again = _run(
        session,
        firm.id,
        _csv("Code,Name,GSTIN,ParentCode", "LOST,Lost,,NOBODY"),
        apply=False,
    )
    assert [(issue.column, issue.message) for issue in again.issues] == [
        (
            "ParentCode",
            "'NOBODY' is not a customer of the firm, nor on an earlier row of "
            "this file.",
        )
    ]
