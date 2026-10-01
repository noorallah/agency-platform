"""Backlog 78 row 2: what a supplier is under GST, and what it charges.

A composition dealer, an unregistered shop and a supplier abroad charge no GST
on their own bill, but the firm's rules taxed a purchase from them like any
other and claimed the credit. A supplier now carries a GST type; one declared
COMPOSITION, UNREGISTERED or OVERSEAS is billed no tax and gives no credit,
unless a rule makes the supply reverse charge. A supplier never declared is
taxed as before (decision A37), and the type reaches the rules as
``vendor_type``.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.purchase_invoice.services import PurchaseInvoiceService
from app.vendors.gst_registration import assert_consistent, effective_type
from tests.unit.test_input_credit_eligibility import _bill, _table4
from tests.unit.test_output_tax_by_head import _net

D = Decimal
GSTIN = "33AABCU9603R1ZM"


def test_a_regular_supplier_is_taxed_and_credited_as_before() -> None:
    """Declared or read off the GSTIN, a regular supplier changes nothing."""
    session, firm_id, bill_id, _, _ = _bill(
        supplier_type="REGULAR", supplier_gstin=GSTIN
    )
    bill = PurchaseInvoiceService(session).get_invoice(bill_id, firm_scope=firm_id)
    assert bill.tax_total == D("72.0000")
    assert _net(session, firm_id, "1320") == D("36.00")


def test_a_supplier_never_declared_is_still_taxed_by_the_rules() -> None:
    """No GSTIN typed in does not make a supplier unregistered (A37)."""
    session, firm_id, bill_id, _, _ = _bill()
    bill = PurchaseInvoiceService(session).get_invoice(bill_id, firm_scope=firm_id)
    assert bill.tax_total == D("72.0000")


@pytest.mark.parametrize(
    ("supplier_type", "gstin"),
    [("COMPOSITION", GSTIN), ("UNREGISTERED", None), ("OVERSEAS", None)],
)
def test_a_supplier_who_charges_no_gst_is_billed_none(
    supplier_type: str, gstin: str | None
) -> None:
    """Bill of supply, unregistered or abroad: no tax, no credit, 3B untouched."""
    session, firm_id, bill_id, _, _ = _bill(
        supplier_type=supplier_type, supplier_gstin=gstin
    )
    bill = PurchaseInvoiceService(session).get_invoice(bill_id, firm_scope=firm_id)
    assert bill.tax_total == D("0")
    assert bill.grand_total == D("400.0000")
    assert _net(session, firm_id, "1320") == D("0.00")
    assert _net(session, firm_id, "2100") == D("-400.00")
    assert _table4(session, firm_id)["4A5"] == 0.0


def test_reverse_charge_still_stands_for_an_unregistered_supplier() -> None:
    """A rule's reverse charge makes the firm owe the tax whoever the supplier is."""
    session, firm_id, bill_id, _, _ = _bill(
        supplier_type="UNREGISTERED", reverse_charge=True
    )
    bill = PurchaseInvoiceService(session).get_invoice(bill_id, firm_scope=firm_id)
    assert bill.tax_total == D("0")
    assert bill.reverse_charge_tax_total == D("72.0000")
    assert _net(session, firm_id, "2270") == D("-36.00")


def test_the_type_must_agree_with_the_gstin() -> None:
    """A registered type needs a GSTIN; unregistered and overseas cannot hold one."""
    assert effective_type(None, GSTIN) == "REGULAR"
    assert effective_type(None, "  ") == "UNREGISTERED"
    assert effective_type("COMPOSITION", GSTIN) == "COMPOSITION"
    with pytest.raises(ValidationError, match="must have a GST number"):
        assert_consistent("COMPOSITION", None)
    with pytest.raises(ValidationError, match="cannot have a GST number"):
        assert_consistent("OVERSEAS", GSTIN)
    assert_consistent(None, None)
    assert_consistent("SEZ", GSTIN)


def test_the_vendor_write_refuses_a_contradiction() -> None:
    """The supplier form and the import end in the same check."""
    from app.vendors.schemas import VendorCreate
    from app.vendors.services.vendor_service import VendorService
    from tests.unit.test_settlements import _Books, _session_factory

    books = _Books(_session_factory()())
    service = VendorService(books.session)
    with pytest.raises(ValidationError, match="must have a GST number"):
        service.create(
            VendorCreate(
                code="COMP-1",
                name="Corner Shop",
                gst_registration_type="COMPOSITION",
            ),
            firm_id=books.firm.id,
            actor_id=uuid4(),
        )
    books.session.rollback()
    saved = service.create(
        VendorCreate(
            code="COMP-2",
            name="Corner Shop Two",
            gstin=GSTIN,
            gst_registration_type="COMPOSITION",
        ),
        firm_id=books.firm.id,
        actor_id=uuid4(),
    )
    assert saved.gst_registration_type == "COMPOSITION"
