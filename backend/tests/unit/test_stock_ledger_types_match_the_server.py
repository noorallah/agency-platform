"""The Stock Ledger's type picker offers exactly the types the server writes.

The ledger and transaction lists filter ``transaction_type`` on the exact
string and accept any, so a type nothing writes is offered, chosen, and
matches nothing -- silently. The desktop's list was typed by hand: it named
GOODS_ISSUE, PHYSICAL_COUNT, RESERVATION, RESERVATION_RELEASE, DAMAGE, EXPIRY,
QUARANTINE and CORRECTION, none of which is ever written, and left out
DISPATCH, WRITE_OFF, the quarantine pair, RESERVE, UNRESERVE, SALES_RETURN and
every reversal (BL-31.13). A suite on either side alone cannot see the drift,
the same gap ``test_import_samples_match_the_server.py`` closes for import
samples.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.inventory.schemas.inventory import REVERSAL_SUFFIX, InventoryTransactionType

_ROOT = Path(__file__).resolve().parents[3]
_PAGE = (
    _ROOT / "desktop" / "lib" / "ui" / "inventory" / "inventory_management_page.dart"
)
_APP = _ROOT / "backend" / "app"

#: The services that call ``reverse_transaction``, and the type each reverses.
#: A reversal is written as ``<original>_REVERSAL``, so these are the only
#: twins that can appear -- ``reverse_transaction`` has no endpoint of its own.
_REVERSED_BY = {
    "goods_receipt/services/goods_receipt_service.py": "GOODS_RECEIPT",
    "purchase_return/services/purchase_return_service.py": "RETURN",
    "sales_return/services/sales_return_service.py": "SALES_RETURN",
}


def _offered() -> list[str]:
    """Read the keys of ``_transactionTypeLabels`` in the inventory page."""
    text = _PAGE.read_text(encoding="utf-8")
    match = re.search(r"_transactionTypeLabels\s*=\s*\{(.*?)\};", text, re.DOTALL)
    assert match, f"{_PAGE.name} has no `_transactionTypeLabels` map"
    return re.findall(r"'([A-Z_]+)'\s*:", match.group(1))


def test_the_reversal_callers_are_the_ones_this_guard_knows() -> None:
    """A new caller of ``reverse_transaction`` writes a new ``_REVERSAL`` type.

    When this fails, add the caller and the type it reverses to
    ``_REVERSED_BY`` and the twin to the desktop's picker.
    """
    callers = {
        path.relative_to(_APP).as_posix()
        for path in _APP.rglob("*.py")
        if ".reverse_transaction(" in path.read_text(encoding="utf-8")
    }
    assert callers == set(_REVERSED_BY)


def test_the_picker_offers_exactly_the_types_the_server_writes() -> None:
    """Every written type is offered once, and nothing else is."""
    offered = _offered()
    written = {member.value for member in InventoryTransactionType} | {
        f"{original}{REVERSAL_SUFFIX}" for original in _REVERSED_BY.values()
    }
    assert len(offered) == len(set(offered)), "a type is offered twice"
    assert set(offered) - written == set(), "offered, never written"
    assert written - set(offered) == set(), "written, never offered"
