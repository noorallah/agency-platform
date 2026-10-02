"""Customers come in from a file, with a template to fill in (backlog 46).

The file rules are the product import's, from ``app.common.file_import``: every
row checked before anything is written, all or nothing, update by code. What
these tests pin is what is particular to customers -- one address and one
contact per row, updated in place; an opening balance booked to the ledger and
read the way Tally writes it; a standing discount held to the settings code;
and a 10-digit phone number taken as Indian.

The sessions do not autoflush, because a request's do not.
"""

from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import UUID, uuid4

from openpyxl import load_workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.file_import import ImportReport, indian_phone
from app.core.database.base import Base
from app.customers.models import (
    Customer,
    CustomerAddress,
    CustomerContact,
    CustomerGroup,
    CustomerReceivableTransaction,
)
from app.customers.schemas import CustomerCreate
from app.customers.services import CustomerService
from app.customers.services.customer_import import (
    COLUMNS,
    CustomerFileImporter,
    template_csv,
    template_workbook,
)
from app.finance.models import JournalEntry, JournalLine, LedgerAccount
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm


def _factory() -> sessionmaker[Session]:
    """Build one in-memory database whose sessions do not autoflush."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def _firm(session: Session, *, books: bool = True) -> Firm:
    """Add a firm with one segment and, unless told not to, its books."""
    firm = Firm(
        name="Import Firm",
        code="IMPORT",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.flush()
    session.add(CustomerGroup(firm_id=firm.id, code="RETAIL", name="Retail shops"))
    session.commit()
    if books:
        seed_finance_setup(
            session,
            firm_id=firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=uuid4(),
        )
        session.commit()
    return firm


def _csv(*lines: str) -> bytes:
    """Join lines into a CSV file's bytes."""
    return ("\n".join(lines) + "\n").encode("utf-8")


def _run(
    session: Session,
    firm_id: UUID,
    content: bytes,
    *,
    apply: bool,
    existing: str = "refuse",
    file_format: str = "csv",
    may_manage_settings: bool = True,
) -> ImportReport[Customer]:
    """Check or apply one file as a single actor."""
    return CustomerFileImporter(
        session,
        CustomerService(session),
        may_manage_settings=may_manage_settings,
    ).run(
        content,
        file_format=file_format,  # type: ignore[arg-type]
        firm_id=firm_id,
        actor_id=uuid4(),
        existing=existing,  # type: ignore[arg-type]
        apply=apply,
    )


def _codes(factory: sessionmaker[Session]) -> list[str]:
    """Read what is durably stored, from a session of its own."""
    with factory() as fresh:
        return sorted(fresh.scalars(select(Customer.code)).all())


def _receivable_net(session: Session, firm_id: UUID) -> Decimal:
    """Return what the ledger says customers owe: the receivable's net debit."""
    rows = session.execute(
        select(JournalLine.debit_amount, JournalLine.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(LedgerAccount.firm_id == firm_id, LedgerAccount.code == "1100")
    ).all()
    return sum((Decimal(debit) - Decimal(credit) for debit, credit in rows), Decimal(0))


def test_a_check_reports_every_problem_by_row_and_writes_nothing() -> None:
    """One pass names them all, with the column each belongs to."""
    factory = _factory()
    session = factory()
    firm = _firm(session)
    _run(session, firm.id, _csv("Code,Name", "TAKEN,Already here"), apply=True)
    content = _csv(
        "Code,Name,Segment,Phone,Email,CreditLimit,Type,City,OpeningBalance",
        "GOOD-1,Good,Retail shops,9876543210,a@b.example,1000,,,",
        "BAD-SEG,Bad segment,WHOLESALE,,,,,,",
        "BAD-PHONE,Bad phone,,12345,,,,,",
        "BAD-MAIL,Bad email,,,not-an-email,,,,",
        "BAD-NUM,Bad number,,,,lots,,,",
        "BAD-TYPE,Bad type,,,,,COMPANY,,",
        "BAD-ADDR,Half an address,,,,,,Chennai,",
        "BAD-OPEN,Bad balance,,,,,,,twelve Dr",
        "TAKEN,Clash,,,,,,,",
        "GOOD-1,Twice,,,,,,,",
        "NO-NAME,,,,,,,,",
    )

    report = _run(session, firm.id, content, apply=True)

    found = {(issue.row, issue.column) for issue in report.issues}
    assert found == {
        (3, "Segment"),
        (4, "Phone"),
        (5, "Email"),
        (6, "CreditLimit"),
        (7, "Type"),
        (8, "Address1"),
        (8, "State"),
        (8, "PIN"),
        (9, "OpeningBalance"),
        (10, "Code"),
        (11, "Code"),
        (12, "Name"),
    }, [issue.describe() for issue in report.issues]
    assert not report.imported
    assert _codes(factory) == ["TAKEN"]


def test_a_clean_file_imports_whole_with_its_address_contact_and_balance() -> None:
    """Segment, address, contact and a Tally-style balance all land."""
    factory = _factory()
    session = factory()
    firm = _firm(session)
    content = _csv(
        "Party Code,Party Name,Customer Group,GSTIN/UIN,Mobile No,Credit Days,"
        "Opening Balance,Address,City,State,Pincode,Contact Person,Contact Mobile",
        'OWES,Owes Us,RETAIL,33AAAPL1234C1Z5,098765 43210,30,"1,200.50 Dr",'
        "12 Market Road,Chennai,Tamil Nadu,600001,R. Kumar,9123456789",
        "PAID,Paid Ahead,,,,,500 Cr,,,,,,",
        "PLAIN,Plain,,,,,,,,,,,",
    )

    report = _run(session, firm.id, content, apply=True)

    assert report.imported, [issue.describe() for issue in report.issues]
    assert (report.to_create, report.to_update) == (3, 0)
    with factory() as fresh:
        owes = fresh.scalars(select(Customer).where(Customer.code == "OWES")).one()
        assert owes.customer_group_id is not None
        assert owes.phone == "+919876543210"
        assert owes.currency_code == "INR"
        assert owes.customer_type == "BUSINESS"
        assert owes.payment_terms_days == 30
        assert owes.opening_balance == Decimal("1200.50")
        assert owes.current_outstanding == Decimal("1200.50")
        (address,) = owes.addresses
        assert (address.city, address.postal_code, address.country) == (
            "Chennai",
            "600001",
            "IN",
        )
        assert address.is_default_billing and address.is_default_shipping
        (contact,) = owes.contacts
        assert (contact.name, contact.mobile, contact.is_primary) == (
            "R. Kumar",
            "+919123456789",
            True,
        )
        paid = fresh.scalars(select(Customer).where(Customer.code == "PAID")).one()
        assert paid.opening_balance == Decimal("-500")
        assert paid.unapplied_advance_balance == Decimal("500")
        # Booked, not just recorded: the receivable carries the net of both.
        assert _receivable_net(fresh, firm.id) == Decimal("700.50")
        assert len(fresh.scalars(select(CustomerReceivableTransaction)).all()) == 2
        created = fresh.scalars(
            select(AuditLog).where(AuditLog.action == "customer.created")
        ).all()
        assert len(created) == 3
    assert _codes(factory) == ["OWES", "PAID", "PLAIN"]


def test_a_firm_without_books_is_told_per_row_and_nothing_is_written() -> None:
    """An opening balance has to be booked, so no chart means no balance."""
    factory = _factory()
    session = factory()
    firm = _firm(session, books=False)
    content = _csv("Code,Name,OpeningBalance", "NOBAL,No balance,", "BAL,Owes,100")

    report = _run(session, firm.id, content, apply=True)

    assert [(issue.row, issue.code) for issue in report.issues] == [(3, "BAL")]
    assert "chart of accounts" in report.issues[0].message
    assert _codes(factory) == []


def test_updating_by_code_changes_only_what_the_file_fills() -> None:
    """A blank cell keeps its field; the address changes in place."""
    factory = _factory()
    session = factory()
    firm = _firm(session)
    CustomerService(session).create(
        CustomerCreate.model_validate(
            {
                "code": "KEEP",
                "customer_type": "BUSINESS",
                "name": "Keep Me",
                "email": "keep@shop.example",
                "currency_code": "INR",
                "addresses": [
                    {
                        "address_type": "BILLING",
                        "address_line1": "1 Old Street",
                        "city": "Madurai",
                        "state": "Tamil Nadu",
                        "country": "IN",
                        "postal_code": "625001",
                        "is_default_billing": True,
                    },
                    {
                        "address_type": "SHIPPING",
                        "address_line1": "Godown 4",
                        "city": "Madurai",
                        "state": "Tamil Nadu",
                        "country": "IN",
                        "postal_code": "625002",
                        "is_default_shipping": True,
                    },
                ],
            }
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    content = _csv(
        "Code,Name,Email,Phone,City,PIN",
        "KEEP,,,9876543210,Chennai,600001",
        "NEW-1,Brand new,,,,",
    )

    refused = _run(session, firm.id, content, apply=True)
    assert [issue.row for issue in refused.issues] == [2]
    assert "update existing customers" in refused.issues[0].message

    report = _run(session, firm.id, content, apply=True, existing="update")

    assert report.imported, [issue.describe() for issue in report.issues]
    assert (report.to_create, report.to_update) == (1, 1)
    with factory() as fresh:
        kept = fresh.scalars(select(Customer).where(Customer.code == "KEEP")).one()
        assert (kept.name, kept.email, kept.phone) == (
            "Keep Me",
            "keep@shop.example",
            "+919876543210",
        )
        addresses = fresh.scalars(
            select(CustomerAddress)
            .where(CustomerAddress.customer_id == kept.id)
            .order_by(CustomerAddress.postal_code)
        ).all()
        assert [
            (a.address_line1, a.city, a.postal_code, a.is_deleted) for a in addresses
        ] == [
            ("1 Old Street", "Chennai", "600001", False),
            ("Godown 4", "Madurai", "625002", False),
        ]
        assert fresh.scalars(select(CustomerContact)).all() == []
    assert _codes(factory) == ["KEEP", "NEW-1"]


def test_a_standing_discount_needs_the_settings_permission() -> None:
    """A file is a second way to set a price, and answers to the same code."""
    factory = _factory()
    session = factory()
    firm = _firm(session)
    content = _csv("Code,Name,DiscountPercent", "DISC,Discounted,5", "NONE,Plain,")

    refused = _run(session, firm.id, content, apply=True, may_manage_settings=False)

    assert [(issue.row, issue.code) for issue in refused.issues] == [(2, "DISC")]
    assert "CUSTOMER_MANAGE_SETTINGS" in refused.issues[0].message
    assert _codes(factory) == []

    allowed = _run(session, firm.id, content, apply=True)
    assert allowed.imported
    assert _codes(factory) == ["DISC", "NONE"]


def test_one_gst_number_on_two_rows_imports_both() -> None:
    """A GSTIN may repeat across one company's accounts (decision A7)."""
    factory = _factory()
    session = factory()
    firm = _firm(session)
    content = _csv(
        "Code,Name,GSTIN",
        "FIRST,First,33AAAPL1234C1Z5",
        "SECOND,Second,33aaapl1234c1z5",
    )

    report = _run(session, firm.id, content, apply=True)

    assert report.issues == []
    assert sorted(_codes(factory)) == ["FIRST", "SECOND"]


def test_a_bare_indian_number_is_written_with_its_country_code() -> None:
    """Ten digits, a trunk 0 or a bare 91 all mean India; + is left alone."""
    assert indian_phone("98765 43210") == "+919876543210"
    assert indian_phone("09876543210") == "+919876543210"
    assert indian_phone("919876543210") == "+919876543210"
    assert indian_phone("+44 20 7946 0000") == "+442079460000"


def test_the_template_round_trips_and_lists_the_firms_segments() -> None:
    """The template's own example row imports, and its lists are this firm's."""
    factory = _factory()
    session = factory()
    firm = _firm(session)

    content = template_workbook(session, firm.id)

    workbook = load_workbook(BytesIO(content))
    assert workbook.sheetnames == ["Customers", "Notes", "Lists"]
    headings = [cell.value for cell in workbook["Customers"][1]]
    assert headings == [column.heading for column in COLUMNS]
    listed = {
        value
        for row in workbook["Lists"].iter_rows(values_only=True)
        for value in row
        if value
    }
    assert {"RETAIL", "Retail shops", "BUSINESS", "ON_HOLD"} <= listed
    assert template_csv().splitlines()[0].split(",")[0] == "Code"

    report = _run(session, firm.id, content, apply=True, file_format="xlsx")
    assert report.issues == [], [issue.describe() for issue in report.issues]
    assert _codes(factory) == ["SHOP-001"]
