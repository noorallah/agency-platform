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

from app.goods_receipt.schemas.goods_receipt import (
    GoodsReceiptCreate,
    GoodsReceiptLineWrite,
)
from app.purchase_return.schemas.purchase_return import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceWrite,
)

_UI = Path(__file__).resolve().parents[3] / "desktop" / "lib" / "ui"
_RETURN = _UI / "purchase_returns" / "purchase_return_editor_dialog.dart"
_RECEIPT = _UI / "goods_receipts" / "goods_receipt_editor_dialog.dart"


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
