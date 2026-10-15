"""Helpers the compliance checks share (not a check; run.py skips it).

Firm ``one`` and firm ``two`` are the GST-registered Wholesale firms the
``compliance-firm`` fixture built (GSTIN state 33, buyers QA-B2B and QA-B2C,
product at HSN 340220, invoices A, B, C). Checks that only read use firm one;
a check that changes anything makes its own customers and bills in firm two
and compares before with after, so it runs alone and runs twice.
"""

from __future__ import annotations

import pathlib
import random
from contextlib import contextmanager
import sys
from decimal import Decimal
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "collections"))

from _col import (  # noqa: E402,F401
    D, Api, by_code, counter, data, message, must, rows_of, today, suffix,
)
from common import Check, all_rows, client, state  # noqa: E402,F401

MODULE = "compliance"
GST = "/api/v1/gst-returns"
EINV = "/api/v1/einvoice"
TCS = "/api/v1/tcs"
SI = "/api/v1/sales-invoices"
CU = "/api/v1/customers"


def api(which: str = "admin") -> Api:
    """Return a signed-in account of the compliance state."""
    return client(which, MODULE)


def firm(which: str = "one") -> dict:
    """Return the state of firm one or two."""
    return state(MODULE)[which]


def month() -> tuple[str, str]:
    """Return the first of the firm's current month and its today."""
    t = today()
    return t.replace(day=1).isoformat(), t.isoformat()


@contextmanager
def gst_settings(api: Api, **changes: object):  # noqa: ANN201
    """Run a block with the firm's GST document policy changed, then put it back."""
    path = "/api/v1/tax-framework/gst-compliance-settings"
    held = must(api.get(path), "gst compliance settings")
    base = {k: v for k, v in held.items() if k != "is_configured"}
    must(api.put(path, {**base, **changes}), "gst settings changed")
    try:
        yield held
    finally:
        must(api.put(path, base), "gst settings put back")


def last_month() -> tuple[str, str, str]:
    """Return (first day, last day, YYYY-MM) of the month before this one."""
    from datetime import timedelta

    end = today().replace(day=1) - timedelta(days=1)
    return end.replace(day=1).isoformat(), end.isoformat(), end.strftime("%Y-%m")


def gstr1(a: Api, frm: str | None = None, to: str | None = None, gstin: str | None = None) -> dict:
    """Read GSTR-1 for the month so far."""
    f, t = month()
    extra = f"&gstin={gstin}" if gstin else ""
    return must(a.get(f"{GST}/gstr1?from_date={frm or f}&to_date={to or t}{extra}"), "gstr1")


def gstr3b(a: Api, frm: str | None = None, to: str | None = None) -> dict:
    """Read GSTR-3B for the month so far."""
    f, t = month()
    return must(a.get(f"{GST}/gstr3b?from_date={frm or f}&to_date={to or t}"), "gstr3b")


def gstr1_totals(r: dict) -> dict[str, Decimal]:
    """Add GSTR-1's B2B, B2CL, B2CS and exports into taxable and tax totals."""
    out = {"taxable": Decimal(0), "cgst": Decimal(0), "sgst": Decimal(0), "igst": Decimal(0)}

    def add(row: dict) -> None:
        out["taxable"] += D(row["taxable_value"])
        out["cgst"] += D(row["central_tax"])
        out["sgst"] += D(row["state_tax"])
        out["igst"] += D(row["integrated_tax"])

    for party in r["b2b"]:
        for inv in party["invoices"]:
            add(inv)
    for key in ("b2cs",):
        for row in r[key]:
            add(row)
    for key in ("b2cl", "exp"):
        for row in r[key]:
            for inv in row.get("invoices", [row]):
                add(inv)
    return out


def invoice_numbers(r: dict) -> list[str]:
    """Every invoice number GSTR-1 lists under B2B."""
    return [inv["invoice_number"] for p in r["b2b"] for inv in p["invoices"]]


class Own:
    """Make this check's own customers and bills in a fixture firm."""

    def __init__(self, which: str = "two") -> None:
        self.which = which
        self.f = firm(which)
        self.api = api("admin2" if which == "two" else "admin")
        tag = self.f["suffix"].upper()
        self.product = by_code(self.api, "/api/v1/products", f"{tag}-P")
        self.branch = by_code(self.api, "/api/v1/branches", "HO")
        self.warehouse = by_code(self.api, "/api/v1/warehouses", "MAIN")
        self.tag = suffix(4)

    def customer(self, gstin: str | None = None, **extra: object) -> dict:
        """Make a customer, registered when a GSTIN is given."""
        n = suffix(4)
        body: dict[str, Any] = {
            "code": f"K{self.tag}{n}",
            "name": f"Compliance buyer {self.tag}{n}",
            "customer_type": "BUSINESS" if gstin else "INDIVIDUAL",
            "currency_code": "INR",
            **extra,
        }
        if gstin:
            body["gst_number"] = gstin
            body["pan_number"] = gstin[2:12]
        return must(self.api.post(CU, body), "customer")

    def gstin(self, state_code: str = "33", valid: bool = True) -> str:
        """Return a fresh GSTIN for a state; with a correct check character unless ``valid`` is off."""
        head = f"{state_code}FXBUY{random.randint(1000, 9999)}B1Z"
        if not valid:
            return f"{head}3"
        alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        total = 0
        for i, ch in enumerate(head):
            product = alphabet.index(ch) * (1 if i % 2 == 0 else 2)
            total += product // 36 + product % 36
        return head + alphabet[(36 - total % 36) % 36]

    def bill(self, customer: dict, qty: str = "1", approve: bool = True, on: str | None = None) -> dict:
        """Type and approve a bill of ``qty`` pieces at 100.00 + 18%."""
        with counter(self.api):
            made = self._type(customer, qty, on)
        if approve:
            status, body = self.api.post(f"{SI}/{made['id']}/approve", {})
            if status == 422 and "Insufficient" in message(body):
                self.stock(str(int(Decimal(qty)) * 2 + 200))
                status, body = self.api.post(f"{SI}/{made['id']}/approve", {})
            made = must((status, body), "bill approve")
        return made

    def stock(self, qty: str) -> None:
        """Add stock of the firm's product by an adjustment (the fixture stocks only a few)."""
        must(
            self.api.post(
                "/api/v1/inventory/adjustments",
                {
                    "branch_id": self.branch["id"],
                    "warehouse_id": self.warehouse["id"],
                    "product_id": self.product["id"],
                    "quantity": qty,
                    "transaction_date": today().isoformat(),
                    "remarks": "compliance check stock",
                },
            ),
            "stock adjustment",
        )

    def _type(self, customer: dict, qty: str, on: str | None = None) -> dict:
        """Type one bill with the order and note stages switched off (put back after)."""
        return must(
            self.api.post(
                SI,
                {
                    "customer_id": customer["id"],
                    "branch_id": self.branch["id"],
                    "invoice_date": on or today().isoformat(),
                    "lines": [
                        {
                            "line_number": 1,
                            "product_id": self.product["id"],
                            "current_invoice_quantity": qty,
                            "warehouse_id": self.warehouse["id"],
                        }
                    ],
                },
            ),
            "bill",
        )

    def register(self, bill: dict) -> dict:
        """Register a bill with the sandbox portal."""
        return must(self.api.post(f"{EINV}/invoices/{bill['id']}/register", {}), "register")
