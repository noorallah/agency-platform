"""Every key the desktop sends for a purchase order is one the server takes.

Found in manual testing on 2026-09-12 (plan item 7.4): the desktop's update
payload carried ``po_number``, which ``PurchaseOrderCreate`` accepts and
``PurchaseOrderUpdate`` does not, and ``PurchaseSchema`` forbids unknown
fields -- so every edit of a saved order was refused, seven times that day.
Neither suite could see it: the desktop's fake accepts whatever it is given
and the backend's tests build their own requests. This is the cross-check
that closes that gap, the shape ``test_desktop_preference_payloads_are_accepted``
already has for preferences.

The keys are read out of the Dart source: ``toCreateJson`` writes them, and
``toUpdateJson`` is create minus whatever it ``remove``s.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.purchase.schemas.purchase import (
    PurchaseLineWrite,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
)

_MODEL = (
    Path(__file__).resolve().parents[3] / "desktop" / "lib" / "models" / "purchase.dart"
)


def _keys(block: str) -> set[str]:
    """Collect the JSON keys a Dart map literal writes."""
    return set(re.findall(r"'([a-z_]+)':", block))


def _order_create_keys() -> set[str]:
    # The order's toCreateJson is the one holding 'branch_id'; the lines'
    # toWriteJson holds 'product_id'.
    text = _MODEL.read_text(encoding="utf-8")
    start = text.index("  Json toCreateJson()")
    end = text.index("  Json toUpdateJson()", start)
    return _keys(text[start:end])


def _order_update_keys() -> set[str]:
    text = _MODEL.read_text(encoding="utf-8")
    start = text.index("  Json toUpdateJson()")
    end = text.index("\n}", start)
    removed = set(re.findall(r"body\.remove\('([a-z_]+)'\)", text[start:end]))
    return _order_create_keys() - removed


def _line_write_keys() -> set[str]:
    text = _MODEL.read_text(encoding="utf-8")
    start = text.index("'product_id': productId,")
    begin = text.rindex("  Json toWriteJson()", 0, start)
    end = text.index("\n}", begin)
    return _keys(text[begin:end])


def test_every_key_the_desktop_creates_with_is_a_create_field() -> None:
    """The create payload's keys are all fields of PurchaseOrderCreate."""
    unknown = _order_create_keys() - set(PurchaseOrderCreate.model_fields)
    assert not unknown, unknown


def test_every_key_the_desktop_updates_with_is_an_update_field() -> None:
    """The update payload's keys are all fields of PurchaseOrderUpdate.

    ``po_number`` is the one create takes and update does not; it must be
    removed on the way to an update, or every edit is refused.
    """
    unknown = _order_update_keys() - set(PurchaseOrderUpdate.model_fields)
    assert not unknown, unknown


def test_every_key_the_desktop_writes_on_a_line_is_a_line_field() -> None:
    """A purchase line's keys are all fields of PurchaseLineWrite."""
    unknown = _line_write_keys() - set(PurchaseLineWrite.model_fields)
    assert not unknown, unknown
