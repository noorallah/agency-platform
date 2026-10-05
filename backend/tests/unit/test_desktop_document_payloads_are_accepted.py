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
    DeliveryNoteBatchPick,
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


def test_a_bill_of_products_line_carries_only_line_fields() -> None:
    """A line typed directly (backlog §38) sends only PurchaseInvoiceLineWrite keys.

    It names a product rather than a receipt line -- the server raises the
    order and the receipt -- so its keys are a different set from the
    receipt-line body above, and need their own check.
    """
    sent = _keys_between(_INVOICE, "product_id", "};")
    assert {"product_id", "current_invoice_quantity", "expiry_date"} <= sent
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
    # The line's own keys run up to its nested list of batch picks, which
    # are asked about against their own schema (backlog 79).
    sent = _keys_between(_NOTE, "sales_order_line_id", "'batches': [") | {"batches"}
    assert "serial_ids" in sent
    unknown = sent - set(DeliveryNoteLineWrite.model_fields)
    assert not unknown, unknown
    text = _NOTE.read_text(encoding="utf-8")
    picks_start = text.index("'batches': [")
    picks = set(
        re.findall(
            r"'([a-z_]+)':", text[picks_start + 1 : text.index("};", picks_start)]
        )
    ) - {"batches"}
    assert picks == {"batch_id", "quantity"}, picks
    assert not picks - set(DeliveryNoteBatchPick.model_fields)


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


# ---- The phase 2 editors and the sales side (PLT-9, §31.11) -----------------
#
# The phase 2 editors are ``part of`` the dialog files above and mostly share
# their payload builders, which is why reading the dialogs covered them. Two
# gaps remained: the phase 2 sales return builds its own body, and nothing on
# the sales side -- quotation, order, both kinds of bill, credit and debit
# note -- was read at all. These read each body between markers inside its
# own function, so a key appearing elsewhere in the file cannot stand in.

from app.credit_note.schemas.credit_note import (  # noqa: E402
    CreditNoteCreate,
    CreditNoteLineWrite,
)
from app.customer_debit_note.schemas.customer_debit_note import (  # noqa: E402
    CustomerDebitNoteCreate,
    CustomerDebitNoteLineWrite,
)
from app.quotation.schemas.quotation import (  # noqa: E402
    QuotationCreate,
    QuotationLineWrite,
)
from app.sales_invoice.schemas.sales_invoice import (  # noqa: E402
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
)
from app.sales_order.schemas.sales_order import (  # noqa: E402
    SalesOrderCreate,
    SalesOrderLineWrite,
)

_SALES = _UI / "sales"
_QUOTATION = _UI / "quotations" / "quotation_editor_dialog.dart"
_ORDER = _SALES / "sales_order_editor_dialog.dart"
_BILL = _SALES / "sales_invoice_editor_dialog.dart"
_CREDIT = _SALES / "credit_note_editor_phase2.dart"
_DEBIT = _SALES / "customer_debit_note_editor_phase2.dart"
_RETURN_PHASE2 = _UI / "sales_returns" / "sales_return_editor_phase2.dart"


def _keys_in(path: Path, function: str, start: str, stop: str) -> set[str]:
    """Collect the keys between ``start`` and ``stop`` inside ``function``.

    Both markers are searched from the function's own signature onwards, so
    the region is the body that function builds and nothing earlier.
    """
    # The Dart sources are CRLF on Windows checkouts and LF in CI.
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    body = text.index(function)
    begin = text.index(start, body)
    end = text.index(stop, begin + len(start))
    return set(re.findall(r"'([a-z_]+)':", text[begin + len(start) : end]))


def _assert_known(sent: set[str], *schemas: type) -> None:
    """Fail naming every key no schema declares."""
    allowed: set[str] = set()
    for schema in schemas:
        allowed |= set(schema.model_fields)  # type: ignore[attr-defined]
    unknown = sent - allowed
    assert not unknown, unknown


def test_a_quotation_carries_only_quotation_fields() -> None:
    """The phase 2 quotation shares this builder."""
    head = _keys_in(_QUOTATION, "Json? _buildPayload()", "return <String", "'lines': [")
    _assert_known(head, QuotationCreate)
    line = _keys_in(_QUOTATION, "Json? _buildPayload()", "'lines': [", "],\n    };")
    _assert_known(line, QuotationLineWrite)


def test_a_sales_order_carries_only_order_fields() -> None:
    """The phase 2 order shares this builder."""
    head = _keys_in(
        _ORDER, "Json? _buildPayload()", "return <String", "'lines': <Json>["
    )
    _assert_known(head, SalesOrderCreate)
    line = _keys_in(_ORDER, "Json? _buildPayload()", "'lines': <Json>[", "],\n    };")
    _assert_known(line, SalesOrderLineWrite)


def test_both_kinds_of_bill_carry_only_invoice_fields() -> None:
    """A bill of notes and a bill of products both post SalesInvoiceCreate."""
    for function in ("Json? _payload()", "Json? _directPayload()"):
        line = _keys_in(_BILL, function, "lines.add(<String", "});")
        _assert_known(line, SalesInvoiceLineWrite)
        head = _keys_in(_BILL, function, "return <String", "'lines': lines")
        _assert_known(head, SalesInvoiceCreate)
    received = _keys_in(_BILL, "_receivedFields()", "{", "}\n")
    _assert_known(received, SalesInvoiceCreate)
    # A product added to a saved counter bill is built on its own (D-SELL-59),
    # and so is a saved line restated as a product for the preview.
    for function in ("Json? _productLine(", "Json _asProductLine("):
        line = _keys_in(_BILL, function, "return <String", "};")
        assert "product_id" in line, function
        _assert_known(line, SalesInvoiceLineWrite)


def test_credit_and_debit_notes_carry_only_their_fields() -> None:
    """The two phase 2 notes against a bill."""
    for path, document, line_schema in (
        (_CREDIT, CreditNoteCreate, CreditNoteLineWrite),
        (_DEBIT, CustomerDebitNoteCreate, CustomerDebitNoteLineWrite),
    ):
        head = _keys_in(path, "Json? _phase2Payload()", "return <String", "'lines': [")
        _assert_known(head, document)
        line = _keys_in(path, "Json? _phase2Payload()", "'lines': [", "],\n    };")
        _assert_known(line, line_schema)


def test_the_phase2_sales_return_carries_only_return_fields() -> None:
    """The phase 2 return builds its own body rather than the dialog's."""
    head = _keys_in(
        _RETURN_PHASE2, "Json? _phase2Payload(", "return <String", "'lines': ["
    )
    _assert_known(head, SalesReturnCreate)
    line = _keys_in(_RETURN_PHASE2, "Json? _phase2Payload(", "'lines': [", "],\n    };")
    _assert_known(line, SalesReturnLineWrite)
