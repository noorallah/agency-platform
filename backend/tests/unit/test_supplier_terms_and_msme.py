"""Supplier payment terms and MSME payment deadlines (backlog 68 rows 1-2).

The supplier bill dated 2026-08-10, supplier's own date 2026-08-09, from the
purchase-chain firm. The MSME period runs from the earlier of the two dates.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.document_framework.models import DocumentLifecycleEvent
from app.purchase_invoice.services.msme import (
    default_due_date,
    msme_pay_by,
    msme_warning,
)
from app.vendors.schemas.vendor import VendorCreate
from tests.unit.test_purchase_chain_synthesis import _Firm


@pytest.fixture
def firm() -> _Firm:
    """Build the purchase-chain firm on a fresh store, bills typed directly."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)())
    built.stages(order=False, receipt=False)
    return built


def _supplier(**fields: object) -> SimpleNamespace:
    """Build a stand-in supplier carrying only what the rules read."""
    return SimpleNamespace(**fields)


def test_the_due_date_defaults_from_the_supplier_s_terms() -> None:
    """Typed wins; else bill date plus terms; no terms leaves it empty."""
    on = date(2026, 8, 10)
    assert default_due_date(
        _supplier(payment_terms_days=30), typed=None, invoice_date=on
    ) == date(2026, 9, 9)
    assert default_due_date(
        _supplier(payment_terms_days=30), typed=date(2026, 8, 20), invoice_date=on
    ) == date(2026, 8, 20)
    assert (
        default_due_date(_supplier(payment_terms_days=0), typed=None, invoice_date=on)
        is None
    )


@pytest.mark.parametrize(
    ("category", "agreement", "expected"),
    [
        ("MICRO", True, date(2026, 9, 23)),
        ("SMALL", False, date(2026, 8, 24)),
        ("MEDIUM", True, None),
        (None, True, None),
    ],
)
def test_the_legal_date_is_45_days_agreed_15_not_from_the_earlier_date(
    category: str | None, agreement: bool, expected: date | None
) -> None:
    """Micro and small only; from the supplier's own date when it is earlier."""
    supplier = _supplier(msme_category=category, msme_written_agreement=agreement)
    assert (
        msme_pay_by(
            supplier,
            invoice_date=date(2026, 8, 10),
            supplier_invoice_date=date(2026, 8, 9),
        )
        == expected
    )


def test_a_due_date_past_the_legal_one_is_warned() -> None:
    """Within it, nothing; past it or with none, the warning names the date."""
    pay_by = date(2026, 8, 24)
    assert (
        msme_warning(pay_by=pay_by, due_date=date(2026, 8, 20), vendor_name="X") is None
    )
    warning = msme_warning(pay_by=pay_by, due_date=date(2026, 9, 9), vendor_name="Ace")
    assert warning is not None
    assert "Ace" in warning and "2026-08-24" in warning and "43B(h)" in warning
    assert "no due date" in (
        msme_warning(pay_by=pay_by, due_date=None, vendor_name="Ace") or ""
    )


def test_a_udyam_number_must_have_its_shape() -> None:
    """UDYAM-XX-00-0000000, upper-cased; anything else is refused by name."""
    base = {"code": "SUP-9", "name": "Ace Traders"}
    assert (
        VendorCreate(**base, udyam_number="udyam-tn-01-1234567").udyam_number
        == "UDYAM-TN-01-1234567"
    )
    with pytest.raises(ValueError, match="UDYAM-XX-00-0000000"):
        VendorCreate(**base, udyam_number="UDYAM-123")


def test_a_bill_to_a_small_supplier_is_stamped_warned_and_listed(
    firm: _Firm,
) -> None:
    """Terms give the due date, the law the pay-by; approval warns; listed."""
    firm.vendor.payment_terms_days = 30
    firm.vendor.msme_category = "SMALL"
    firm.vendor.udyam_number = "UDYAM-TN-01-1234567"
    firm.session.commit()
    bills = firm.bills()

    bill = bills.create_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert bill.due_date == date(2026, 9, 9)
    assert bill.msme_pay_by == date(2026, 8, 24)

    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    event = firm.session.scalar(
        select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.source_document_id == bill.id,
            DocumentLifecycleEvent.action == "APPROVED",
        )
    )
    assert event is not None and event.remarks is not None
    assert "must be paid by 2026-08-24" in event.remarks

    (row,) = bills.msme_dues_report(firm_scope=firm.firm.id, as_of=date(2026, 8, 20))
    assert row.invoice_id == bill.id
    assert row.state == "DUE_SOON" and row.days_left == 4
    assert row.outstanding_amount == Decimal("1000.00")
    (late,) = bills.msme_dues_report(firm_scope=firm.firm.id, as_of=date(2026, 8, 30))
    assert late.state == "OVERDUE"


def test_a_supplier_outside_the_rule_is_never_listed(firm: _Firm) -> None:
    """No category, no pay-by, nothing on the list."""
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)

    assert bill.msme_pay_by is None
    assert bills.msme_dues_report(firm_scope=firm.firm.id) == []
