"""Backlog 84: a new firm's purchase documents number like the order and receipt.

The purchase bill, the purchase return and the supplier debit note print the
firm code and the branch code (and so run a number per branch), as the order
and the goods receipt do. The sales invoice stays within the 16 characters GST
allows, and a firm that already has a series is left alone.
"""

from __future__ import annotations

import ast
import importlib
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import pytest

from app.debit_note.services.debit_note_service import DebitNoteService
from app.document_framework.services.transactional_document_service import (
    DocumentTypeSpec,
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


# -- one default prefix, one document (D-BUY-46, D-BUY-57, D-BUY-58) ---------

_APP = Path(__file__).resolve().parents[2] / "app"

#: Series numbered by hand rather than through a ``DocumentTypeSpec``: the
#: file, and the text that issues the number. Pinned so they stand in the
#: comparison below, and so a renamed one fails here rather than vanishing.
_HAND_NUMBERED = {
    "FA": ("fixed_assets/services/fixed_asset_service.py", 'f"FA-{'),
    "DEP": ("fixed_assets/services/fixed_asset_service.py", 'f"DEP-{'),
}


def _declaring_modules() -> list[str]:
    """Return every module under ``app`` that builds a ``DocumentTypeSpec``."""
    found = []
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "DocumentTypeSpec"
            for node in ast.walk(tree)
        ):
            parts = path.relative_to(_APP.parent).with_suffix("").parts
            found.append(".".join(part for part in parts if part != "__init__"))
    return found


def _specs_in(value: object, depth: int = 0) -> list[DocumentTypeSpec]:
    """Return the specs a module-level or class-level value holds."""
    if isinstance(value, DocumentTypeSpec):
        return [value]
    if depth < 2 and isinstance(value, dict):
        value = list(value.values())
    if depth < 2 and isinstance(value, list | tuple | set | frozenset):
        return [spec for item in value for spec in _specs_in(item, depth + 1)]
    return []


def _default_prefixes() -> dict[str, set[str]]:
    """Return each default prefix with the document types numbered under it.

    However a module declares its series -- a ``DOCUMENT`` on the service, a
    second spec beside it (the self-invoice), three on one module
    (settlements), a table of them (stock movements, master codes) -- the
    spec is found by reading what the module and its classes hold.
    """
    by_prefix: dict[str, set[str]] = defaultdict(set)
    for name in _declaring_modules():
        module = importlib.import_module(name)
        held = list(vars(module).values())
        for value in list(held):
            if isinstance(value, type) and value.__module__ == name:
                held.extend(vars(value).values())
        specs = [spec for value in held for spec in _specs_in(value)]
        assert specs, f"{name} builds a DocumentTypeSpec this test cannot find"
        for spec in specs:
            by_prefix[spec.prefix.upper()].add(spec.code)
    for prefix, (file, text) in _HAND_NUMBERED.items():
        assert text in (_APP / file).read_text(encoding="utf-8"), (file, text)
        by_prefix[prefix].add(f"hand-numbered in {file}")
    return by_prefix


def test_no_two_document_types_share_a_default_prefix() -> None:
    """A shared prefix is two documents under one number.

    A number is issued by stepping over numbers of the same document type
    and over journal references, so two types under one prefix collide the
    moment one of them posts no journal under its number: a requisition and
    a purchase return (``PR``, D-BUY-46), a rate contract and a customer
    receipt (``RC``, D-BUY-57), a reverse-charge self-invoice and a sales
    invoice (``SI``, D-BUY-58 -- two GST documents under one serial number).
    Give a new document type a prefix of its own.
    """
    by_prefix = _default_prefixes()
    # Enough were found to know the search works: 42 series on 2026-10-05.
    assert len(by_prefix) >= 40, sorted(by_prefix)
    shared = {
        prefix: sorted(codes) for prefix, codes in by_prefix.items() if len(codes) > 1
    }
    assert shared == {}, f"document types sharing a default prefix: {shared}"
    assert by_prefix["RSI"] == {"RCM_SELF_INVOICE"}
    assert by_prefix["RTC"] == {"RATE_CONTRACT"}
    assert by_prefix["SI"] == {"SALES_INVOICE"}
    assert by_prefix["RC"] == {"RECEIPT"}
