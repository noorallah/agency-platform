"""TDS on the purchase of goods, section 194Q, worked out (ACC-8, decision A78).

Off until the firm switches it on; 0.1% on purchases past fifty lakh from one
supplier in the April-March year, valued without GST; 5% without a PAN; what
the payments already deducted under 194Q is taken off; drafts and cancelled
bills and other years do not count.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.finance.services.tds_194q import Tds194QService, income_tax_year
from app.purchase_invoice.models import PurchaseInvoice
from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
from app.settlements.services import PaymentService
from tests.unit.test_settlements import WHEN, _Books, _session_factory


def _bill(
    books: _Books,
    number: str,
    taxable: str,
    *,
    on: date = WHEN,
    status: str = "APPROVED",
    tax: str = "0",
) -> PurchaseInvoice:
    row = PurchaseInvoice(
        firm_id=books.firm.id,
        vendor_id=books.vendor.id,
        branch_id=books.branch_id,
        invoice_number=number,
        invoice_date=on,
        supplier_invoice_number=f"S-{number}",
        supplier_invoice_date=on,
        status=status,
        subtotal=Decimal(taxable),
        tax_total=Decimal(tax),
        grand_total=Decimal(taxable) + Decimal(tax),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(row)
    books.session.commit()
    return row


def _switch_on(books: _Books, **over: object) -> None:
    values: dict[str, object] = {
        "is_enabled": True,
        "threshold_amount": Decimal("5000000"),
        "rate_percent": Decimal("0.1"),
        "rate_without_pan_percent": Decimal("5"),
    }
    values.update(over)
    Tds194QService(books.session).save_settings(
        books.firm.id, actor_id=books.actor_id, **values  # type: ignore[arg-type]
    )


def test_the_income_tax_year_is_april_to_march() -> None:
    assert income_tax_year(date(2026, 4, 1)) == (date(2026, 4, 1), date(2027, 3, 31))
    assert income_tax_year(date(2027, 3, 31)) == (date(2026, 4, 1), date(2027, 3, 31))


def test_nothing_is_due_until_the_firm_switches_it_on() -> None:
    books = _Books(_session_factory()())
    _bill(books, "PI-1", "6000000")
    position = Tds194QService(books.session).supplier(
        books.vendor.id, firm_id=books.firm.id, on=WHEN
    )
    assert position.purchases == Decimal("6000000.00")
    assert (position.due, position.applies) == (Decimal("0"), False)


def test_the_tax_is_on_the_excess_without_gst_at_the_threshold_edge() -> None:
    books = _Books(_session_factory()())
    books.vendor.pan = "AAACV1234A"
    books.session.commit()
    _switch_on(books)
    service = Tds194QService(books.session)

    _bill(books, "PI-1", "5000000", tax="900000")
    at_edge = service.supplier(books.vendor.id, firm_id=books.firm.id, on=WHEN)
    assert (at_edge.excess, at_edge.due, at_edge.applies) == (
        Decimal("0.00"),
        Decimal("0.00"),
        False,
    )

    _bill(books, "PI-2", "1000000", tax="180000")
    past = service.supplier(books.vendor.id, firm_id=books.firm.id, on=WHEN)
    assert past.purchases == Decimal("6000000.00")
    assert past.excess == Decimal("1000000.00")
    assert past.due == Decimal("1000.00")
    assert past.to_deduct == Decimal("1000.00")
    assert past.applies is True


def test_a_supplier_without_a_pan_is_deducted_at_five_percent() -> None:
    books = _Books(_session_factory()())
    books.vendor.pan = None
    books.session.commit()
    _switch_on(books)
    _bill(books, "PI-1", "5100000")
    position = Tds194QService(books.session).supplier(
        books.vendor.id, firm_id=books.firm.id, on=WHEN
    )
    assert position.rate_percent == Decimal("5")
    assert position.due == Decimal("5000.00")


def test_drafts_cancelled_bills_and_last_year_do_not_count() -> None:
    books = _Books(_session_factory()())
    books.vendor.pan = "AAACV1234A"
    books.session.commit()
    _switch_on(books)
    _bill(books, "PI-1", "5000000")
    _bill(books, "PI-2", "900000", status="DRAFT")
    _bill(books, "PI-3", "900000", status="CANCELLED")
    _bill(books, "PI-4", "900000", on=date(2026, 3, 31))
    position = Tds194QService(books.session).supplier(
        books.vendor.id, firm_id=books.firm.id, on=WHEN
    )
    assert position.purchases == Decimal("5000000.00")
    assert position.due == Decimal("0.00")


def test_what_payments_deducted_under_194q_is_taken_off() -> None:
    books = _Books(_session_factory()())
    books.vendor.pan = "AAACV1234A"
    books.session.commit()
    _switch_on(books)
    _bill(books, "PI-1", "7000000")
    PaymentService(books.session).create(
        SettlementCreate(
            party_id=books.vendor.id,
            settlement_date=WHEN,
            amount=Decimal("100000.00"),
            method=SettlementMethodEnum.BANK,
            tds_amount=Decimal("1500.00"),
            tds_section="194Q",
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    service = Tds194QService(books.session)
    position = service.supplier(books.vendor.id, firm_id=books.firm.id, on=WHEN)
    assert position.due == Decimal("2000.00")
    assert position.deducted == Decimal("1500.00")
    assert position.to_deduct == Decimal("500.00")

    [row] = service.register(firm_id=books.firm.id, on=WHEN)
    assert (row.vendor_code, row.to_deduct) == ("V1", Decimal("500.00"))


def test_settings_are_checked_and_an_unknown_supplier_refused() -> None:
    books = _Books(_session_factory()())
    with pytest.raises(ValidationError, match="at most 20"):
        _switch_on(books, rate_percent=Decimal("0"))
    with pytest.raises(ResourceNotFoundError):
        Tds194QService(books.session).supplier(uuid4(), firm_id=books.firm.id, on=WHEN)
    settings = Tds194QService(books.session).settings(books.firm.id)
    assert settings.is_enabled is False
    assert settings.threshold_amount == Decimal("5000000")
