"""Every key the desktop's receipt and return editors send is one the server takes.

Found in manual testing on 2026-09-12 (plan item 7.9): every purchase return
raised from the desktop was refused with 422. The editor sent a
``description`` on each line -- seeded from the receipt line, so never empty
-- and ``PurchaseReturnLineWrite`` has no such field; ``PurchaseReturnSchema``
forbids unknown fields. The server derives the description itself from the
source line. Same class as the purchase order's ``po_number`` on update,
found the same morning, and the same reason neither suite saw it: the
desktop's fake accepts anything and the backend builds its own requests.

The keys are read out of the Dart source of each editor's payload block.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.delivery_note.schemas.delivery_note import (
    DeliveryNoteCreate,
    DeliveryNoteLineWrite,
)
from app.goods_receipt.schemas.goods_receipt import (
    GoodsReceiptCreate,
    GoodsReceiptLineWrite,
)
from app.purchase_invoice.schemas.purchase_invoice import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceSourceWrite,
)
from app.purchase_return.schemas.purchase_return import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceWrite,
)
from app.sales_return.schemas.sales_return import (
    SalesReturnCreate,
    SalesReturnLineWrite,
)

_UI = Path(__file__).resolve().parents[3] / "desktop" / "lib" / "ui"
_RETURN = _UI / "purchase_returns" / "purchase_return_editor_dialog.dart"
_RECEIPT = _UI / "goods_receipts" / "goods_receipt_editor_dialog.dart"
_INVOICE = _UI / "purchase_invoices" / "purchase_invoice_editor_dialog.dart"
_NOTE = _UI / "delivery_notes" / "delivery_note_editor_dialog.dart"
_SALES_RETURN = _UI / "sales_returns" / "sales_return_editor_dialog.dart"


def _keys_between(path: Path, first_key: str, stop: str) -> set[str]:
    """Collect the JSON keys of the map literal that starts at ``first_key``.

    ``stop`` is the text that ends the region: the literal's closing ``};``
    for a line, or the ``'lines': [`` that begins the nested list for a
    document.
    """
    text = path.read_text(encoding="utf-8")
    start = text.index(f"'{first_key}'")
    # Walk back to the opening brace of this literal so the first key counts.
    start = text.rindex("{", 0, start)
    end = text.index(stop, start)
    return set(re.findall(r"'([a-z_]+)':", text[start:end]))


def test_a_purchase_return_line_carries_only_line_fields() -> None:
    """The return line's keys are all fields of PurchaseReturnLineWrite."""
    sent = _keys_between(_RETURN, "source_document_line_id", "};")
    unknown = sent - set(PurchaseReturnLineWrite.model_fields)
    assert not unknown, unknown


def test_a_purchase_return_carries_only_document_fields() -> None:
    """The return's keys are fields of PurchaseReturnCreate or its source rows."""
    sent = _keys_between(_RETURN, "reference_grn_number", "'lines': [")
    allowed = set(PurchaseReturnCreate.model_fields) | set(
        PurchaseReturnSourceWrite.model_fields
    )
    unknown = sent - allowed
    assert not unknown, unknown


def test_a_goods_receipt_line_carries_only_line_fields() -> None:
    """The receipt line's keys are all fields of GoodsReceiptLineWrite."""
    sent = _keys_between(_RECEIPT, "purchase_order_line_id", "};")
    unknown = sent - set(GoodsReceiptLineWrite.model_fields)
    assert not unknown, unknown


def test_a_goods_receipt_carries_only_document_fields() -> None:
    """The receipt's keys are all fields of GoodsReceiptCreate."""
    sent = _keys_between(_RECEIPT, "receipt_date", "'lines': [")
    unknown = sent - set(GoodsReceiptCreate.model_fields)
    assert not unknown, unknown


def test_a_purchase_invoice_line_carries_only_line_fields() -> None:
    """The bill line's keys are all fields of PurchaseInvoiceLineWrite.

    The bill editor arrived on 2026-09-18 (BL-31.9), six days after the
    return editor's ``description`` refusal above; the same check on the
    day it is written is what keeps it from meeting the same refusal.
    """
    sent = _keys_between(_INVOICE, "source_document_line_id", "};")
    unknown = sent - set(PurchaseInvoiceLineWrite.model_fields)
    assert not unknown, unknown


def test_a_purchase_invoice_carries_only_document_fields() -> None:
    """The bill's keys are fields of PurchaseInvoiceCreate or its source rows."""
    sent = _keys_between(_INVOICE, "supplier_invoice_date", "'lines': [")
    allowed = set(PurchaseInvoiceCreate.model_fields) | set(
        PurchaseInvoiceSourceWrite.model_fields
    )
    unknown = sent - allowed
    assert not unknown, unknown


def test_the_bill_editor_never_sends_a_blank_price_as_zero() -> None:
    """A blank unit price stays out of the body rather than going as '0'.

    Absent means the server takes the receipt line's price; zero means the
    supplier charged nothing. The return editor sent ``'0'`` for a blank and
    every return was valued at nothing (D-BUY-3).
    """
    text = _INVOICE.read_text(encoding="utf-8")
    assert "'unit_price': '0'" not in text
    assert "isEmpty ? '0' : unitPrice" not in text


def test_a_delivery_note_line_carries_only_line_fields() -> None:
    """The note line's keys, ``serial_ids`` included, are DeliveryNoteLineWrite's.

    ``serial_ids`` arrived with the serial picker (D-STK-4, 2026-09-19): a
    line for a serial-tracked product names the units going out.
    """
    sent = _keys_between(_NOTE, "sales_order_line_id", "};")
    assert "serial_ids" in sent
    unknown = sent - set(DeliveryNoteLineWrite.model_fields)
    assert not unknown, unknown


def test_a_delivery_note_carries_only_document_fields() -> None:
    """The note's keys are all fields of DeliveryNoteCreate."""
    sent = _keys_between(_NOTE, "delivery_date", "'lines': [")
    unknown = sent - set(DeliveryNoteCreate.model_fields)
    assert not unknown, unknown


def test_a_sales_return_line_carries_only_line_fields() -> None:
    """The return line's keys, ``serial_ids`` included, are SalesReturnLineWrite's."""
    sent = _keys_between(_SALES_RETURN, "source_document_type", "]")
    assert "serial_ids" in sent
    unknown = sent - set(SalesReturnLineWrite.model_fields)
    assert not unknown, unknown


def test_a_sales_return_carries_only_document_fields() -> None:
    """The return's keys are all fields of SalesReturnCreate."""
    sent = _keys_between(_SALES_RETURN, "warehouse_id", "'lines': [")
    unknown = sent - set(SalesReturnCreate.model_fields)
    assert not unknown, unknown
