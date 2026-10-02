"""A customer's bank accounts and files on record (MST-4, decision A68).

Accounts replace as a list, only for ``CUSTOMER_MANAGE_BANK_DETAILS``, and read
masked to the last four digits for anybody else -- in the trail too. Files are
added and removed one at a time, and a removal is remembered.
"""

# ruff: noqa: D103

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.schemas.records import (
    CustomerAttachmentWrite,
    CustomerBankAccountInput,
)
from app.customers.services import CustomerService
from app.customers.services.customer_records import (
    CustomerRecordsService,
    mask_account_number,
)
from app.identity.system_seed import PERMISSION_GROUPS, ROLE_PERMISSION_CODES
from tests.unit.test_customer_management import (
    _firm,
    _session_factory,
    _settled_customer_data,
)


def _customer() -> tuple[object, object, object]:
    session = _session_factory()()
    firm = _firm(session, "MST4")
    customer = CustomerService(session).create(
        _settled_customer_data(), firm_id=firm.id, actor_id=uuid4()
    )
    return session, firm, customer


def _account(number: str, primary: bool = False) -> CustomerBankAccountInput:
    return CustomerBankAccountInput(
        bank_name="State Bank",
        account_name="Acme Customer",
        account_number=number,
        ifsc="sbin0001234",
        is_primary=primary,
    )


def test_the_number_shows_only_its_last_four() -> None:
    assert mask_account_number("123456789012") == "XXXXXXXX9012"
    assert mask_account_number("1234") == "1234"


def test_accounts_replace_as_a_list_and_read_masked_to_others() -> None:
    session, firm, customer = _customer()
    service = CustomerRecordsService(session)  # type: ignore[arg-type]
    actor = uuid4()

    saved = service.replace_bank_accounts(
        customer.id,  # type: ignore[attr-defined]
        [_account("1234 5678 9012")],
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=actor,
    )
    # A lone account is the primary one; spaces dropped, IFSC upper-cased.
    assert [(a.account_number, a.is_primary, a.ifsc) for a in saved] == [
        ("123456789012", True, "SBIN0001234")
    ]

    service.replace_bank_accounts(
        customer.id,  # type: ignore[attr-defined]
        [_account("111122223333"), _account("444455556666", primary=True)],
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=actor,
    )
    masked = service.bank_accounts(
        customer.id, firm_id=firm.id, unmasked=False  # type: ignore[attr-defined]
    )
    assert [(a.account_number, a.masked) for a in masked] == [
        ("XXXXXXXX6666", True),
        ("XXXXXXXX3333", True),
    ]

    trail = session.scalars(  # type: ignore[attr-defined]
        select(AuditLog).where(AuditLog.action == "customer.bank_accounts.replaced")
    ).all()
    assert len(trail) == 2
    assert "444455556666" not in str(trail[-1].after_data)
    assert "XXXXXXXX6666" in str(trail[-1].after_data)

    assert (
        service.replace_bank_accounts(
            customer.id,  # type: ignore[attr-defined]
            [],
            firm_id=firm.id,  # type: ignore[attr-defined]
            actor_id=actor,
        )
        == []
    )


def test_two_primaries_or_a_repeated_number_are_refused() -> None:
    session, firm, customer = _customer()
    service = CustomerRecordsService(session)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="Only one"):
        service.replace_bank_accounts(
            customer.id,  # type: ignore[attr-defined]
            [_account("11112222", True), _account("33334444", True)],
            firm_id=firm.id,  # type: ignore[attr-defined]
            actor_id=uuid4(),
        )
    with pytest.raises(ValidationError, match="twice"):
        service.replace_bank_accounts(
            customer.id,  # type: ignore[attr-defined]
            [_account("11112222"), _account("1111 2222")],
            firm_id=firm.id,  # type: ignore[attr-defined]
            actor_id=uuid4(),
        )
    with pytest.raises(ResourceNotFoundError):
        service.bank_accounts(uuid4(), firm_id=firm.id, unmasked=True)  # type: ignore[attr-defined]


def test_files_are_kept_and_a_removal_is_remembered() -> None:
    session, firm, customer = _customer()
    service = CustomerRecordsService(session)  # type: ignore[arg-type]
    actor = uuid4()
    [kept] = service.attach(
        customer.id,  # type: ignore[attr-defined]
        [
            CustomerAttachmentWrite(
                file_name="gst.pdf",
                file_path=r"\\server\kyc\gst.pdf",
                caption="GST certificate",
            )
        ],
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=actor,
    )
    assert [row.id for row in service.attachments(customer.id, firm_id=firm.id)] == [  # type: ignore[attr-defined]
        kept.id
    ]
    service.remove_attachment(
        customer.id, kept.id, firm_id=firm.id, actor_id=actor  # type: ignore[attr-defined]
    )
    assert service.attachments(customer.id, firm_id=firm.id) == []  # type: ignore[attr-defined]
    actions = session.scalars(  # type: ignore[attr-defined]
        select(AuditLog.action).where(AuditLog.action.like("customer.attachment.%"))
    ).all()
    assert sorted(actions) == [
        "customer.attachment.added",
        "customer.attachment.removed",
    ]
    with pytest.raises(ResourceNotFoundError):
        service.remove_attachment(
            customer.id, kept.id, firm_id=firm.id, actor_id=actor  # type: ignore[attr-defined]
        )
    with pytest.raises(ValidationError, match="at least one"):
        service.attach(customer.id, [], firm_id=firm.id, actor_id=actor)  # type: ignore[attr-defined]


def test_changing_where_a_refund_goes_is_a_separate_duty() -> None:
    assert "CUSTOMER_MANAGE_BANK_DETAILS" in PERMISSION_GROUPS["customer"]
    assert "CUSTOMER_MANAGE_BANK_DETAILS" not in ROLE_PERMISSION_CODES["SALES_MANAGER"]
    assert "CUSTOMER_MANAGE_BANK_DETAILS" not in ROLE_PERMISSION_CODES["ACCOUNTANT"]
