"""A supplier's GST number follows the customers' rule (backlog 136, row F5).

The number is typed once among the firm's live suppliers. A branch that sends
none takes its main office's, as a marked copy on its own row; a branch in
another state types its own. A second holder is refused naming the first, and
a number removed is free again. These are the cases of
``test_customer_parent_and_shops.py``, asked of suppliers.
"""

# ruff: noqa: D103

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.exceptions import ConflictError
from app.vendors.api.router import _responses
from app.vendors.models import Vendor
from app.vendors.schemas import VendorCreate, VendorUpdate
from app.vendors.services import VendorService
from tests.unit.test_goods_receipt import _Fixture, _principal, _session_factory

pytestmark = pytest.mark.typed_document_numbers

PAN = "AAACD1234K"
GSTIN = f"36{PAN}1Z5"
OTHER_STATE = f"29{PAN}1Z5"


def _fixture(code: str = "F5") -> _Fixture:
    return _Fixture(_session_factory()(), code)


def _supplier(
    fixture: _Fixture, code: str, parent: UUID | None = None, **fields: object
) -> Vendor:
    return VendorService(fixture.session).create(
        VendorCreate.model_validate(
            {"code": code, "name": f"Supplier {code}", "parent_vendor_id": parent}
            | fields
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _edit(fixture: _Fixture, vendor: Vendor, **fields: object) -> Vendor:
    return VendorService(fixture.session).update(
        vendor.id,
        VendorUpdate.model_validate(
            {"code": vendor.code, "name": vendor.name} | fields
        ),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _held(vendor: Vendor) -> tuple[str | None, bool]:
    return vendor.gstin, vendor.gstin_from_parent


def test_a_main_office_with_three_branches_and_no_second_holder() -> None:
    """Three branches take the number; a second supplier cannot type it."""
    fixture = _fixture()
    main = _supplier(fixture, "HUL", gstin=GSTIN, gst_registration=True)
    branches = [
        _supplier(fixture, code, main.id) for code in ("HUL-KKP", "HUL-MYP", "HUL-GAC")
    ]

    for branch in branches:
        assert _held(branch) == (GSTIN, True)
        assert branch.pan == PAN
        assert branch.gst_registration is True
        assert branch.parent_vendor_id == main.id
    assert _held(main) == (GSTIN, False)
    scope = ResolvedFirmScope(
        principal=_principal(fixture.actor_id, {"VENDOR_VIEW"}),
        firm_id=fixture.firm.id,
    )
    rows = _responses([main, *branches], fixture.session, scope)
    assert [row.gstin_from_parent for row in rows] == [False, True, True, True]

    with pytest.raises(ConflictError, match="held by HUL Supplier HUL") as refused:
        _supplier(fixture, "HUL2", gstin=GSTIN)
    assert "Make this supplier a branch of HUL" in str(refused.value)


def test_a_branch_in_another_state_keeps_its_own_number() -> None:
    """Its number is its own, and nobody else may take it."""
    fixture = _fixture()
    main = _supplier(fixture, "HUL", gstin=GSTIN)
    branch = _supplier(fixture, "HUL-BLR", main.id, gstin=OTHER_STATE)

    assert _held(branch) == (OTHER_STATE, False)
    with pytest.raises(ConflictError, match="held by HUL-BLR"):
        _supplier(fixture, "ELSE", gstin=OTHER_STATE)
    with pytest.raises(ConflictError, match="held by HUL-BLR"):
        _supplier(fixture, "HUL-DUP", main.id, gstin=OTHER_STATE)


def test_a_form_that_sends_back_the_number_it_was_shown_still_inherits() -> None:
    """A branch's form echoes the main office's number; that is not typed."""
    fixture = _fixture()
    main = _supplier(fixture, "HUL", gstin=GSTIN)
    branch = _supplier(fixture, "HUL-KKP", main.id, gstin=GSTIN)
    assert _held(branch) == (GSTIN, True)

    branch = _edit(fixture, branch, parent_vendor_id=main.id, gstin=GSTIN, remarks="x")

    assert _held(branch) == (GSTIN, True)


def test_an_edit_that_names_neither_leaves_the_company_alone() -> None:
    """A phone number corrected on a branch does not take it out."""
    fixture = _fixture()
    main = _supplier(fixture, "HUL", gstin=GSTIN)
    branch = _supplier(fixture, "HUL-KKP", main.id)

    branch = _edit(fixture, branch, phone="+919000000001")

    assert branch.parent_vendor_id == main.id
    assert _held(branch) == (GSTIN, True)


def test_the_main_offices_new_number_reaches_the_branches_that_take_it() -> None:
    """The copies move with the number, each with its own audit row."""
    fixture = _fixture()
    main = _supplier(fixture, "HUL", gstin=GSTIN)
    taking = _supplier(fixture, "HUL-KKP", main.id)
    own = _supplier(fixture, "HUL-BLR", main.id, gstin=OTHER_STATE)
    new_pan = "AAACD9999M"
    new_number = f"36{new_pan}1Z5"

    _edit(fixture, main, gstin=new_number, pan=new_pan)

    fixture.session.refresh(taking)
    assert (taking.gstin, taking.pan) == (new_number, new_pan)
    assert taking.gstin_from_parent is True
    fixture.session.refresh(own)
    assert own.gstin == OTHER_STATE
    trail = fixture.session.scalars(
        select(AuditLog).where(
            AuditLog.entity_id == str(taking.id), AuditLog.action == "vendor.updated"
        )
    ).all()
    assert len(trail) == 1
    # The number the company gave up is free for somebody else.
    _supplier(fixture, "NEWCO", gstin=GSTIN)


def test_a_main_office_that_clears_its_number_clears_the_copies() -> None:
    """A supplier that leaves GST takes its branches with it."""
    fixture = _fixture()
    main = _supplier(fixture, "HUL", gstin=GSTIN, gst_registration=True)
    branch = _supplier(fixture, "HUL-KKP", main.id)

    _edit(fixture, main, gstin=None, gst_registration=False)

    fixture.session.refresh(branch)
    assert _held(branch) == (None, True)
    assert branch.gst_registration is False


def test_a_branch_taken_out_gives_the_number_back() -> None:
    """It does not keep a copy of its old main office's number as its own."""
    fixture = _fixture()
    main = _supplier(fixture, "HUL", gstin=GSTIN, gst_registration_type="REGULAR")
    branch = _supplier(fixture, "HUL-KKP", main.id)
    assert branch.gst_registration_type == "REGULAR"

    branch = _edit(fixture, branch, parent_vendor_id=None, gstin=GSTIN)

    assert branch.parent_vendor_id is None
    assert _held(branch) == (None, False)
    assert branch.gst_registration_type is None


def test_an_existing_supplier_is_put_under_a_main_office() -> None:
    """A branch entered before its main office joins it and takes the number."""
    fixture = _fixture()
    branch = _supplier(fixture, "HUL-KKP")
    main = _supplier(fixture, "HUL", gstin=GSTIN)

    branch = _edit(fixture, branch, parent_vendor_id=main.id)

    assert _held(branch) == (GSTIN, True)


def test_a_branch_types_its_own_number_and_stops_taking_one() -> None:
    """A branch that registers in its state holds that number as its own."""
    fixture = _fixture()
    main = _supplier(fixture, "HUL", gstin=GSTIN)
    branch = _supplier(fixture, "HUL-BLR", main.id)

    branch = _edit(fixture, branch, gstin=OTHER_STATE)

    assert _held(branch) == (OTHER_STATE, False)
    # And blank again takes the main office's.
    branch = _edit(fixture, branch, gstin=None)
    assert _held(branch) == (GSTIN, True)
    # The number it gave up is free.
    _supplier(fixture, "ELSE", gstin=OTHER_STATE)


def test_a_number_removed_is_free_again() -> None:
    """Cleared from its holder, or its holder deleted, it may be typed anew."""
    fixture = _fixture()
    service = VendorService(fixture.session)
    first = _supplier(fixture, "FIRST", gstin=GSTIN)
    with pytest.raises(ConflictError, match="held by FIRST"):
        _supplier(fixture, "SECOND", gstin=GSTIN)

    _edit(fixture, first, gstin=None)
    second = _supplier(fixture, "SECOND", gstin=GSTIN)

    service.delete(second.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id)
    _supplier(fixture, "THIRD", gstin=GSTIN)


def test_a_restore_does_not_walk_into_a_number_that_moved_on() -> None:
    """A deleted holder does not get its number back from a live one."""
    fixture = _fixture()
    service = VendorService(fixture.session)
    main = _supplier(fixture, "HUL", gstin=GSTIN)
    branch = _supplier(fixture, "HUL-KKP", main.id)
    service.delete(branch.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id)
    service.delete(main.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id)

    with pytest.raises(ConflictError, match="Restore the main office first"):
        service.restore(
            branch.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
        )

    _supplier(fixture, "NEWCO", gstin=GSTIN)
    with pytest.raises(ConflictError, match="cannot be restored: GST number"):
        service.restore(main.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id)


def test_a_restored_branch_takes_the_number_its_main_office_holds_now() -> None:
    """The copy on a deleted branch is not trusted; it is read again."""
    fixture = _fixture()
    service = VendorService(fixture.session)
    main = _supplier(fixture, "HUL", gstin=GSTIN)
    branch = _supplier(fixture, "HUL-KKP", main.id)
    service.delete(branch.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id)
    _edit(fixture, main, gstin=OTHER_STATE)

    restored = service.restore(
        branch.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )

    assert _held(restored) == (OTHER_STATE, True)


def test_the_company_read_says_whose_number_each_office_holds() -> None:
    """The family names the copies, so a screen can say "main office's"."""
    fixture = _fixture()
    main = _supplier(fixture, "HUL", gstin=GSTIN)
    _supplier(fixture, "HUL-BLR", main.id, gstin=OTHER_STATE)
    _supplier(fixture, "HUL-KKP", main.id)

    family = VendorService(fixture.session).family(main.id, firm_scope=fixture.firm.id)

    assert [(row.code, row.gstin, row.gstin_from_parent) for row in family.members] == [
        ("HUL", GSTIN, False),
        ("HUL-BLR", OTHER_STATE, False),
        ("HUL-KKP", GSTIN, True),
    ]


def test_a_supplier_with_no_main_office_and_no_number_holds_none() -> None:
    """Blank means blank where there is nobody to take a number from."""
    fixture = _fixture()
    plain = _supplier(fixture, "PLAIN")

    assert _held(plain) == (None, False)
    plain = _edit(fixture, plain, gstin=None)
    assert _held(plain) == (None, False)


def test_the_key_holds_one_typed_number_to_one_live_supplier() -> None:
    """The index is the guard; the service check is only the message."""
    fixture = _fixture()
    main = _supplier(fixture, "HUL", gstin=GSTIN)
    _supplier(fixture, "HUL-KKP", main.id)

    fixture.session.add(
        Vendor(
            firm_id=fixture.firm.id,
            code="RACE",
            name="Race",
            display_name="Race",
            gstin=GSTIN,
            created_by=fixture.actor_id,
            updated_by=fixture.actor_id,
        )
    )
    with pytest.raises(IntegrityError):
        fixture.session.flush()
    fixture.session.rollback()
