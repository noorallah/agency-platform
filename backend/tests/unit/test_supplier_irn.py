"""The supplier's IRN on a bill, and the warning when it is missing (78.5)."""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.finance.services.opening_setup import seed_finance_setup
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceSupplierIrnWrite,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.tax.models import GstComplianceSettings
from app.tax.schemas.gst_compliance import GstComplianceSettingsWrite
from app.tax.services.gst_compliance import GstComplianceService
from app.vendors.models import Vendor
from tests.unit import test_purchase_invoice_module as bills

pytestmark = pytest.mark.typed_document_numbers

IRN = "a" * 40 + "0123456789abcdef01234567"
OTHER_IRN = "b" * 64


def _draft(
    *, e_invoicing: bool = True, irn: str | None = None, number: str = "S-1"
) -> tuple[Session, UUID, UUID, UUID, PurchaseInvoiceService]:
    """Return a session, firm, draft bill id, actor and service."""
    session = bills._session_factory()()
    actor_id = uuid4()
    firm = bills._firm(session)
    branch = bills._branch(session, firm_id=firm.id)
    warehouse = bills._warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = bills._vendor(session, firm_id=firm.id)
    vendor.issues_e_invoices = e_invoicing
    session.commit()
    order = bills._purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(bills.PurchaseOrderLine).where(
            bills.PurchaseOrderLine.purchase_order_id == order.id
        )
    )
    assert po_line is not None
    receipt, receipt_line = bills._received(session, po_line)
    payload = bills._bill_of(
        receipt, receipt_line, number=number, quantity="4", on=date(2026, 8, 2)
    )
    if irn is not None:
        payload = PurchaseInvoiceCreate.model_validate(
            {**payload.model_dump(), "supplier_irn": irn}
        )
    service = PurchaseInvoiceService(session)
    bill = service.create_invoice(payload, firm_id=firm.id, actor_id=actor_id)
    session.commit()
    return session, firm.id, bill.id, actor_id, service


def test_an_irn_is_64_hex_characters_stored_lower() -> None:
    assert PurchaseInvoiceSupplierIrnWrite(supplier_irn=IRN.upper()).supplier_irn == (
        IRN
    )
    assert PurchaseInvoiceSupplierIrnWrite(supplier_irn="  ").supplier_irn is None
    with pytest.raises(SchemaError, match="64 letters and digits"):
        PurchaseInvoiceSupplierIrnWrite(supplier_irn="IRN-123")


def test_an_e_invoicing_suppliers_bill_without_an_irn_is_warned() -> None:
    _, firm_id, bill_id, _, service = _draft()

    response = service.invoice_response(
        service.get_invoice(bill_id, firm_scope=firm_id)
    )

    assert response.irn_warning is not None
    assert "rule 48(4)" in response.irn_warning


def test_no_warning_once_the_irn_is_recorded_or_the_supplier_does_not() -> None:
    session, firm_id, bill_id, _, service = _draft(irn=IRN)
    response = service.invoice_response(
        service.get_invoice(bill_id, firm_scope=firm_id)
    )
    assert (response.supplier_irn, response.irn_warning) == (IRN, None)

    session, firm_id, bill_id, _, service = _draft(e_invoicing=False)
    response = service.invoice_response(
        service.get_invoice(bill_id, firm_scope=firm_id)
    )
    assert response.irn_warning is None


def test_the_firm_can_switch_the_check_off() -> None:
    session, firm_id, bill_id, _, service = _draft()
    session.add(GstComplianceSettings(firm_id=firm_id, supplier_irn_check="OFF"))
    session.commit()

    response = service.invoice_response(
        service.get_invoice(bill_id, firm_scope=firm_id)
    )

    assert response.irn_warning is None


def test_the_setting_round_trips_and_absent_keeps_it() -> None:
    session, firm_id, _, actor_id, _ = _draft()
    settings = GstComplianceService(session)
    assert settings.settings_response(firm_id).supplier_irn_check == "WARN"
    base = {
        "einvoice_applicable_from": None,
        "thirty_day_rule_from": None,
        "dispatch_without_invoice": "WARN",
        "route_sale_needs_invoice": False,
    }
    settings.update_settings(
        GstComplianceSettingsWrite(**base, supplier_irn_check="OFF"),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    kept = settings.update_settings(
        GstComplianceSettingsWrite(**base), firm_id=firm_id, actor_id=actor_id
    )
    assert kept.supplier_irn_check == "OFF"


def test_an_edit_that_omits_the_irn_keeps_it_and_null_clears_it() -> None:
    session, firm_id, bill_id, actor_id, service = _draft(irn=IRN)
    bill = service.invoice_response(service.get_invoice(bill_id, firm_scope=firm_id))
    edit = {
        "invoice_date": bill.invoice_date,
        "supplier_invoice_number": bill.supplier_invoice_number,
        "supplier_invoice_date": bill.supplier_invoice_date,
        "lines": [
            {
                "line_number": line.line_number,
                "source_document_type": line.source_document_type,
                "source_document_id": line.source_document_id,
                "source_document_line_id": line.source_document_line_id,
                "current_invoice_quantity": line.current_invoice_quantity,
            }
            for line in bill.lines
        ],
    }

    row = service.update_invoice(
        bill_id,
        PurchaseInvoiceCreate.model_validate(edit),
        firm_scope=firm_id,
        actor_id=actor_id,
    )
    assert row.supplier_irn == IRN

    row = service.update_invoice(
        bill_id,
        PurchaseInvoiceCreate.model_validate({**edit, "supplier_irn": None}),
        firm_scope=firm_id,
        actor_id=actor_id,
    )
    assert row.supplier_irn is None


def test_the_irn_can_be_recorded_on_an_approved_bill_and_is_audited() -> None:
    session, firm_id, bill_id, actor_id, service = _draft()
    seed_finance_setup(
        session, firm_id=firm_id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    session.commit()
    service.approve_invoice(bill_id, firm_scope=firm_id, actor_id=actor_id)
    session.commit()

    row = service.set_supplier_irn(bill_id, IRN, firm_scope=firm_id, actor_id=actor_id)

    assert row.supplier_irn == IRN
    assert service.invoice_response(row).irn_warning is None
    assert session.scalar(
        select(AuditLog).where(
            AuditLog.action == "purchase_invoice.supplier_irn_set",
            AuditLog.entity_id == bill_id,
        )
    )


def test_a_cancelled_bill_keeps_its_irn() -> None:
    session, firm_id, bill_id, actor_id, service = _draft()
    service.cancel_invoice(bill_id, firm_scope=firm_id, actor_id=actor_id)
    session.commit()

    with pytest.raises(ValidationError, match="cancelled"):
        service.set_supplier_irn(bill_id, IRN, firm_scope=firm_id, actor_id=actor_id)


def test_two_bills_carrying_one_irn_are_warned() -> None:
    session, firm_id, bill_id, actor_id, service = _draft(irn=IRN)
    first = service.get_invoice(bill_id, firm_scope=firm_id)
    second = service.create_invoice(
        PurchaseInvoiceCreate.model_validate(
            {
                "invoice_date": first.invoice_date,
                "supplier_invoice_number": "S-2",
                "supplier_invoice_date": first.supplier_invoice_date,
                "supplier_irn": IRN,
                "lines": [
                    {
                        "line_number": line.line_number,
                        "source_document_type": line.source_document_type,
                        "source_document_id": line.source_document_id,
                        "source_document_line_id": line.source_document_line_id,
                        "current_invoice_quantity": "1",
                    }
                    for line in service.invoice_response(first).lines
                ],
            }
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    session.commit()

    response = service.invoice_response(second)

    assert response.irn_warning is not None
    assert first.invoice_number in response.irn_warning


def test_the_supplier_flag_is_on_the_supplier() -> None:
    session, _, _, _, _ = _draft()
    assert session.scalars(select(Vendor.issues_e_invoices)).all() == [True]
