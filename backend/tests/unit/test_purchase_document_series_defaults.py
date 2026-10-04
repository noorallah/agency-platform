"""Backlog 84: a new firm's purchase documents number like the order and receipt.

The purchase bill, the purchase return and the supplier debit note print the
firm code and the branch code (and so run a number per branch), as the order
and the goods receipt do. The sales invoice stays within the 16 characters GST
allows, and a firm that already has a series is left alone.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.debit_note.services.debit_note_service import DebitNoteService
from app.document_framework.services.transactional_document_service import (
    TransactionalDocumentService,
)
from app.goods_receipt.services.goods_receipt_service import GoodsReceiptService
from app.purchase.services.purchase_service import PurchaseService
from app.purchase_invoice.services.purchase_invoice_service import (
    PurchaseInvoiceService,
)
from app.purchase_return.services.purchase_return_service import (
    PurchaseReturnService,
)
from app.sales_invoice.services.sales_invoice_service import SalesInvoiceService
from tests.unit.test_document_framework import _firm, _session_factory

_PURCHASE_CHAIN = (
    PurchaseService,
    GoodsReceiptService,
    PurchaseInvoiceService,
    PurchaseReturnService,
    DebitNoteService,
)


@pytest.mark.parametrize("service_class", _PURCHASE_CHAIN)
def test_every_purchase_document_prints_firm_and_branch(
    service_class: type[TransactionalDocumentService],
) -> None:
    """A new firm's purchase series carries the firm and the branch code."""
    session = _session_factory()()
    firm = _firm(session)
    service = service_class(session)
    _, rule = service._ensure_document_setup(firm_id=firm.id, actor_id=uuid4())
    assert rule.include_company_code is True
    assert rule.include_branch_code is True
    assert rule.include_financial_year is True


def test_an_existing_series_is_not_rewritten() -> None:
    """A firm that already holds a series keeps it exactly as it was."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    service = PurchaseInvoiceService(session)
    _, rule = service._ensure_document_setup(firm_id=firm.id, actor_id=actor)
    rule.include_branch_code = False
    rule.include_company_code = False
    session.commit()
    _, again = service._ensure_document_setup(firm_id=firm.id, actor_id=actor)
    assert again.id == rule.id
    assert again.include_branch_code is False
    assert again.include_company_code is False


def test_the_sales_invoice_series_stays_within_gst_length() -> None:
    """The tax invoice does not print firm or branch (rule 46(b), D-TAX-3)."""
    session = _session_factory()()
    firm = _firm(session)
    service = SalesInvoiceService(session)
    _, rule = service._ensure_document_setup(firm_id=firm.id, actor_id=uuid4())
    assert rule.include_company_code is False
    assert rule.include_branch_code is False
    assert rule.short_financial_year is True
