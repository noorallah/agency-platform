"""The firm's own bank details, and the block bills print (ACC-4, decision A81).

Details hang off a bank ledger account and are saved whole and audited with
the number masked; one account per firm prints on documents; the full number
leaves the server only for whoever may change the details or pays from the
account; and a bill's bank block and UPI ID fill from the printed account
where the template leaves them empty.
"""

# ruff: noqa: D103

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.document_framework.models import DocumentPrintTemplate
from app.document_framework.services.print_support import load_template
from app.finance.api.router import (
    get_bank_details,
    list_bank_details,
    remove_bank_details,
    save_bank_details,
)
from app.finance.schemas.bank_details import BankAccountDetailsWrite
from app.finance.services.bank_details import BankDetailsService
from app.finance.services.control_accounts import ControlAccountPurpose
from app.sales_invoice.services.invoice_pdf import TemplateSettings
from tests.unit.test_settlements import _Books, _session_factory


def _details(**overrides: object) -> BankAccountDetailsWrite:
    values: dict[str, object] = {
        "bank_name": "HDFC Bank",
        "account_name": "Test Traders Pvt Ltd",
        "account_number": "5020 0012 3456 78",
        "ifsc": "hdfc0001234",
        "branch": "Andheri East",
        "account_kind": "CURRENT",
        "print_on_documents": True,
    }
    values.update(overrides)
    return BankAccountDetailsWrite.model_validate(values)


def _scope(books: _Books, *codes: str) -> ResolvedFirmScope:
    return ResolvedFirmScope(
        principal=Principal(
            subject=books.actor_id,
            roles=frozenset(),
            permissions=frozenset(codes),
            claims=TokenClaims(
                sub=str(books.actor_id),
                type=TokenType.ACCESS,
                iat=1,
                exp=4_102_444_800,
            ),
        ),
        firm_id=books.firm.id,
    )


def _second_bank(books: _Books) -> UUID:
    """Add another asset account under the bank's group."""
    from app.finance.models import LedgerAccount

    bank = books.session.get(LedgerAccount, books.account(ControlAccountPurpose.BANK))
    assert bank is not None
    other = LedgerAccount(
        id=uuid4(),
        firm_id=books.firm.id,
        account_group_id=bank.account_group_id,
        code="1215",
        name="ICICI Current Account",
        account_type="ASSET",
    )
    books.session.add(other)
    books.session.commit()
    return other.id


def test_the_number_and_ifsc_are_normalised_and_checked() -> None:
    row = _details()
    assert row.account_number == "50200012345678"
    assert row.ifsc == "HDFC0001234"
    with pytest.raises(SchemaError, match="11 characters"):
        _details(ifsc="HDFC1234")
    with pytest.raises(SchemaError, match="letters or digits"):
        _details(account_number="12/34")
    assert _details(ifsc=" ", branch=" ").ifsc is None


def test_details_are_saved_whole_and_audited_with_the_number_masked() -> None:
    books = _Books(_session_factory()())
    bank = books.account(ControlAccountPurpose.BANK)
    scope = _scope(books, "ACCOUNT_MANAGE")

    saved = save_bank_details(bank, _details(), scope, books.session).data
    assert saved is not None
    assert (saved.account_number, saved.masked) == ("50200012345678", False)

    trail = books.session.scalars(
        select(AuditLog).where(AuditLog.action == "bank_account_details.saved")
    ).all()
    assert trail[-1].after_data["account_number"] == "XXXXXXXXXX5678"

    again = save_bank_details(
        bank, _details(branch=None, ifsc=None), scope, books.session
    ).data
    assert again is not None
    assert (again.id, again.branch, again.ifsc) == (saved.id, None, None)


def test_the_full_number_is_only_for_who_may_change_it_or_pays() -> None:
    books = _Books(_session_factory()())
    bank = books.account(ControlAccountPurpose.BANK)
    save_bank_details(bank, _details(), _scope(books, "ACCOUNT_MANAGE"), books.session)

    viewer = list_bank_details(_scope(books, "ACCOUNT_VIEW"), books.session).data
    assert viewer is not None
    assert (viewer[0].account_number, viewer[0].masked) == ("XXXXXXXXXX5678", True)

    payer = get_bank_details(bank, _scope(books, "PAYMENT_CREATE"), books.session)
    assert payer.data is not None
    assert payer.data.account_number == "50200012345678"


def test_only_one_account_prints_and_marking_another_moves_it() -> None:
    books = _Books(_session_factory()())
    bank = books.account(ControlAccountPurpose.BANK)
    other = _second_bank(books)
    scope = _scope(books, "ACCOUNT_MANAGE")
    save_bank_details(bank, _details(), scope, books.session)
    save_bank_details(
        other,
        _details(bank_name="ICICI Bank", account_number="000405001234", ifsc=None),
        scope,
        books.session,
    )

    rows = list_bank_details(scope, books.session).data
    assert rows is not None
    printed = [r.bank_name for r in rows if r.print_on_documents]
    assert printed == ["ICICI Bank"]
    assert rows[0].bank_name == "ICICI Bank"


def test_only_an_asset_account_carries_bank_details() -> None:
    books = _Books(_session_factory()())
    sales = books.account(ControlAccountPurpose.SALES_REVENUE)
    with pytest.raises(ValidationError, match="not an asset account"):
        BankDetailsService(books.session).save(
            sales, _details(), firm_id=books.firm.id, actor_id=books.actor_id
        )
    with pytest.raises(ResourceNotFoundError):
        BankDetailsService(books.session).save(
            uuid4(), _details(), firm_id=books.firm.id, actor_id=books.actor_id
        )


def test_removing_details_stops_the_bill_printing_them() -> None:
    books = _Books(_session_factory()())
    bank = books.account(ControlAccountPurpose.BANK)
    scope = _scope(books, "ACCOUNT_MANAGE")
    save_bank_details(bank, _details(), scope, books.session)
    remove_bank_details(bank, scope, books.session)

    assert BankDetailsService(books.session).printed(books.firm.id) is None
    with pytest.raises(ResourceNotFoundError):
        get_bank_details(bank, scope, books.session)


def test_a_bill_prints_the_marked_account_where_its_template_is_empty() -> None:
    books = _Books(_session_factory()())
    bank = books.account(ControlAccountPurpose.BANK)
    save_bank_details(
        bank,
        _details(upi_id="testtraders@hdfcbank"),
        _scope(books, "ACCOUNT_MANAGE"),
        books.session,
    )

    template = load_template(
        books.session, firm_scope=books.firm.id, document_type="SALES_INVOICE"
    )
    assert template.bank_details is not None
    assert template.bank_details.splitlines() == [
        "Bank: HDFC Bank, Andheri East",
        "A/c name: Test Traders Pvt Ltd",
        "A/c no.: 50200012345678",
        "IFSC: HDFC0001234",
    ]
    assert template.upi_id == "testtraders@hdfcbank"

    # An order or a challan charges nobody, and prints no bank block.
    quiet = load_template(
        books.session,
        firm_scope=books.firm.id,
        document_type="PURCHASE_ORDER",
        fallback=TemplateSettings(show_bank_details=False),
    )
    assert (quiet.bank_details, quiet.upi_id) == (None, None)


def test_text_typed_on_a_template_wins_over_the_account() -> None:
    books = _Books(_session_factory()())
    bank = books.account(ControlAccountPurpose.BANK)
    save_bank_details(
        bank,
        _details(upi_id="testtraders@hdfcbank"),
        _scope(books, "ACCOUNT_MANAGE"),
        books.session,
    )
    books.session.add(
        DocumentPrintTemplate(
            firm_id=books.firm.id,
            document_type="SALES_INVOICE",
            title_text="TAX INVOICE",
            accent_color="#0B3D6B",
            show_bank_details=True,
            bank_details="SBI, Fort branch\nA/c 1234",
        )
    )
    books.session.commit()

    template = load_template(
        books.session, firm_scope=books.firm.id, document_type="SALES_INVOICE"
    )
    assert template.bank_details == "SBI, Fort branch\nA/c 1234"
    assert template.upi_id == "testtraders@hdfcbank"
