"""Decision A7 (with B5): a GSTIN or PAN may repeat across customers, warned.

One company is often several customer accounts: a branch per state shares its
PAN, a head office and its outlets may share a GSTIN. Both were unique among a
firm's live customers, which refused the second account (or, for a PAN filled
from a GSTIN, left it blank). Now only the code is unique; a save that repeats
a GSTIN or PAN is allowed and the response names the other account, and the
form can ask beforehand through ``GET /customers/identity-check``.
"""

from uuid import uuid4

import pytest
from fastapi import Response

from app.core.exceptions import ConflictError
from app.customers.api.router import (
    check_customer_identity,
    create_customer,
    update_customer,
)
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.customers.services import CustomerService
from app.identity.models import UserFirm
from tests.unit.test_customer_management import (
    _firm,
    _firm_scope,
    _principal,
    _session_factory,
)

PAN = "AAACP1234C"
GSTIN = f"29{PAN}1Z5"


def _data(code: str, **fields: object) -> CustomerCreate:
    """Build a business customer with no opening balance."""
    return CustomerCreate.model_validate(
        {
            "code": code,
            "customer_type": "BUSINESS",
            "name": f"Customer {code}",
            "currency_code": "INR",
            **fields,
        }
    )


def _scope() -> tuple[object, object]:
    """Return a session and a scope that may create, read and edit customers."""
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "A7")
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    setup.close()
    session = factory()
    principal = _principal(
        user_id, {"CUSTOMER_CREATE", "CUSTOMER_VIEW", "CUSTOMER_UPDATE"}
    )
    return session, _firm_scope(principal, session, firm.id)


def test_a_repeated_gstin_and_pan_are_saved_and_named() -> None:
    """The second account saves, and the response says who else holds them."""
    session, scope = _scope()
    first = create_customer(
        _data("HO", gst_number=GSTIN), scope, session  # type: ignore[arg-type]
    )
    assert first.message is None

    second = create_customer(
        _data("OUTLET", gst_number=GSTIN), scope, session  # type: ignore[arg-type]
    )

    assert second.data.gst_number == GSTIN
    assert second.data.pan_number == PAN
    assert second.message == (
        f"GSTIN {GSTIN} is also on HO Customer HO; PAN {PAN} is also on HO "
        "Customer HO."
    )


def test_the_form_can_ask_before_it_saves() -> None:
    """The check names the holders; the account being edited is left out."""
    session, scope = _scope()
    first = create_customer(
        _data("HO", gst_number=GSTIN), scope, session  # type: ignore[arg-type]
    )

    asked = check_customer_identity(
        scope, gst_number=None, pan_number=PAN.lower(), db=session  # type: ignore[arg-type]
    )
    assert [holder.code for holder in asked.data.holders] == ["HO"]
    assert asked.data.message == f"PAN {PAN} is also on HO Customer HO."

    itself = check_customer_identity(
        scope,  # type: ignore[arg-type]
        gst_number=GSTIN,
        pan_number=PAN,
        excluding_id=first.data.id,
        db=session,
    )
    assert itself.data.holders == []
    assert itself.data.message is None


def test_an_edit_that_takes_another_accounts_pan_is_named_too() -> None:
    """Update answers with the same warning as create."""
    session, scope = _scope()
    create_customer(_data("AA", pan_number=PAN), scope, session)  # type: ignore[arg-type]
    other = create_customer(_data("BB"), scope, session)  # type: ignore[arg-type]

    updated = update_customer(
        other.data.id,
        CustomerUpdate.model_validate(
            {
                "code": "BB",
                "customer_type": "BUSINESS",
                "name": "Customer BB",
                "currency_code": "INR",
                "pan_number": PAN,
            }
        ),
        scope,  # type: ignore[arg-type]
        Response(),
        session,  # type: ignore[arg-type]
    )

    assert updated.data.pan_number == PAN
    assert updated.message == f"PAN {PAN} is also on AA Customer AA."


def test_the_code_is_still_unique() -> None:
    """Only the GSTIN and PAN were relaxed; a repeated code is refused by name."""
    session, scope = _scope()
    create_customer(_data("SAME"), scope, session)  # type: ignore[arg-type]

    with pytest.raises(ConflictError, match="Customer code SAME already exists"):
        create_customer(_data("SAME"), scope, session)  # type: ignore[arg-type]


def test_a_deleted_account_comes_back_beside_one_sharing_its_pan() -> None:
    """Restore used to refuse a PAN now on a live account; only the code counts."""
    session, scope = _scope()
    firm_id = scope.firm_id  # type: ignore[attr-defined]
    service = CustomerService(session)  # type: ignore[arg-type]
    gone = service.create(
        _data("OLD", pan_number=PAN), firm_id=firm_id, actor_id=uuid4()
    )
    service.delete(gone.id, firm_scope=firm_id, actor_id=uuid4())
    service.create(_data("NEW", pan_number=PAN), firm_id=firm_id, actor_id=uuid4())

    back = service.restore(gone.id, firm_scope=firm_id, actor_id=uuid4())

    assert back.is_deleted is False
