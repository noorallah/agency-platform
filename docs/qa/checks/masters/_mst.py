"""Helpers the masters checks share (not a check; run.py skips it).

Firm ``one`` is TEST01 (Firm admin, Seller, a Sales Manager, an Accountant and
the described customer ``<SFX>-CM``); firm ``two`` is TEST02 (admin, a branch
and warehouse with every field set, two import files). Each check makes its
own records under a fresh tag, so it runs alone and runs twice.
"""

from __future__ import annotations

import pathlib
import sys
from decimal import Decimal
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "collections"))
sys.path.insert(0, str(HERE.parent / "selling"))

from _col import D, Api, by_code, counter, data, message, must, rows_of, today, suffix  # noqa: E402,F401
from common import Check, all_rows, check_brand, client, fetch, state  # noqa: E402,F401

MODULE = "masters"
CU = "/api/v1/customers"
VE = "/api/v1/vendors"
PR = "/api/v1/products"


def api(which: str = "admin") -> Api:
    """Return a signed-in account of the masters state."""
    return client(which, MODULE)


def one() -> dict:
    """Return the state of firm one (TEST01)."""
    return state(MODULE)["one"]


def two() -> dict:
    """Return the state of firm two (TEST02)."""
    return state(MODULE)["two"]


def tag(n: int = 5) -> str:
    """Return a fresh upper-case tag."""
    return suffix(n)


def customer(a: Api, **extra: Any) -> dict:
    """Make a customer with a fresh code and return the response data."""
    t = tag()
    body = {"code": f"M{t}", "name": f"Masters check {t}", "customer_type": "BUSINESS",
            "currency_code": "INR", **extra}
    return must(a.post(CU, body), "customer")


def vendor(a: Api, **extra: Any) -> dict:
    """Make a vendor with a fresh code."""
    t = tag()
    body = {"code": f"V{t}", "name": f"Masters vendor {t}", **extra}
    return must(a.post(VE, body), "vendor")


def piece(a: Api) -> str:
    """Return the id of the PIECE unit."""
    for u in rows_of(a.get("/api/v1/uom-framework/uoms?page_size=100")):
        if u["code"] == "PIECE":
            return str(u["id"])
    raise SystemExit("PRECONDITION no PIECE unit")


def product(a: Api, **extra: Any) -> dict:
    """Make a stock product with a fresh code."""
    t = tag()
    p = piece(a)
    body = {
        "code": f"P{t}", "name": f"Masters item {t}", "brand_id": check_brand(a),
        "product_type": "STOCK_ITEM", "tax_profile_group_code": "GST_18_LOCAL",
        "selling_price": "100", "base_uom_id": p, "inventory_uom_id": p,
        "sales_uom_id": p, "purchase_uom_id": p, **extra,
    }
    return must(a.post(PR, body), "product")

import json  # noqa: E402

from _sell import (  # noqa: E402,F401
    DN, SI, SO, Scene, bill_note, counter, credit_policy, new_note, new_order, owed,
)

RC = "/api/v1/receipts"
BR = "/api/v1/branches"
WH = "/api/v1/warehouses"


def described(a: Api, **extra: Any) -> dict:
    """Make a customer like the fixture's QA-CM: address, contact, terms, segment.

    Copies the fixture customer's segment and place ids, so the clone is
    described exactly as the case says (limit 50,000, 30 days, 7.5%).
    """
    src = by_code(a, CU, one()["customer_code"])
    full = must(a.get(f"{CU}/{src['id']}"), "fixture customer")
    t = tag()
    addr = {k: v for k, v in full["addresses"][0].items() if k not in ("id", "created_at", "updated_at")}
    contact = {k: v for k, v in full["contacts"][0].items() if k not in ("id", "created_at", "updated_at")}
    body = {
        "code": f"D{t}", "name": f"Described {t}", "customer_type": "BUSINESS",
        "currency_code": "INR", "phone": "+919800000100", "credit_limit": "50000",
        "payment_terms_days": 30, "default_discount_percent": "7.5",
        "customer_group_id": full["customer_group_id"], "addresses": [addr],
        "contacts": [contact], **extra,
    }
    return must(a.post(CU, body), "described customer")


_SCHEMAS: dict[str, Any] = {}


def schema_fields(name: str) -> set[str]:
    """Return the property names the server declares for a request schema."""
    if not _SCHEMAS:
        status, raw = fetch("GET", "/openapi.json", None, {})
        _SCHEMAS.update(json.loads(raw)["components"]["schemas"])
    return set(_SCHEMAS[name].get("properties", {}))


def echo(schema: str, row: dict, children: dict[str, str] | None = None, **changes: Any) -> dict:
    """Build an update body from a response: its write fields, with changes.

    ``children`` maps a list field to the schema of its rows, so a child is
    sent back without the response-only keys the server forbids.
    """
    body = {k: v for k, v in row.items() if k in schema_fields(schema)}
    for field, child in (children or {}).items():
        if field in body:
            keep = schema_fields(child)
            body[field] = [{k: v for k, v in r.items() if k in keep} for r in body[field]]
    body.update(changes)
    return body


def put_with(a: Api, path: str, body: dict, version: int | None = None, **headers: str) -> tuple[int, Any]:
    """PUT JSON with an If-Match header, which Api.put cannot send."""
    head = {"Content-Type": "application/json", "Authorization": f"Bearer {a.token}",
            "X-Firm-ID": a.firm_id or ""}
    if version is not None:
        head["If-Match"] = f'"{version}"' if headers.get("quoted") else str(version)
    status, raw = fetch("PUT", path, json.dumps(body).encode(), head)
    try:
        return status, json.loads(raw.decode()) if raw else None
    except ValueError:
        return status, raw


def gstin(state_code: str = "33") -> str:
    """Return a fresh GSTIN (valid check character) for a state code."""
    import random

    head = f"{state_code}FXBUY{random.randint(1000, 9999)}B1Z"
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total = 0
    for i, ch in enumerate(head):
        product = alphabet.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return head + alphabet[(36 - total % 36) % 36]


def gstin_of(pan: str, state_code: str = "33") -> str:
    """Return a GSTIN of a given PAN in a state, with a valid check character."""
    head = f"{state_code}{pan}1Z"
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total = 0
    for i, ch in enumerate(head):
        product = alphabet.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return head + alphabet[(36 - total % 36) % 36]


def csv_bytes(rows: list[list[str]]) -> bytes:
    """Encode rows as a CSV file."""
    import csv
    import io

    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return out.getvalue().encode("utf-8")
