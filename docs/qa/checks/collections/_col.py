"""Helpers the collections checks share (not a check; run.py skips it).

Firm ``one`` is a finished Wholesale firm with its Firm admin, a Viewer, a
Cashier, a Firm Manager and two Bill Collectors; firm ``two`` is a second such
firm. Each check makes its own customers, product and bills under a fresh tag.
Money is compared as exact decimals.
"""

from __future__ import annotations

import pathlib
import sys
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402,F401
    PASSWORD,
    Api,
    Check,
    all_rows,
    check_brand,
    client,
    data,
    fetch,
    message,
    save_state,
    sign_in,
    state,
    suffix,
)

SO = "/api/v1/sales-orders"
SI = "/api/v1/sales-invoices"
RC = "/api/v1/receipts"
RF = "/api/v1/refunds"
CU = "/api/v1/customers"
COL = "/api/v1/collections"
PDC = "/api/v1/post-dated-cheques"
PA = "/api/v1/party-adjustments"
SETTINGS = f"{SO}/workflow-settings"


def today() -> date:
    """Return the firm's business day (India), as the server judges it."""
    return (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date()


def D(value: object) -> Decimal:  # noqa: N802
    """Return a Decimal from whatever the server sent."""
    return Decimal(str(value if value is not None else 0))


def must(answer: tuple[int, Any], what: str) -> Any:  # noqa: ANN401
    """Return the data of a 2xx answer or stop saying what was refused."""
    status, body = answer
    if status not in (200, 201):
        raise SystemExit(f"PRECONDITION {what}: {status} {message(body)}")
    return data(body)


def rows_of(answer: tuple[int, Any]) -> list[Any]:
    """Return the list of a list answer, or stop."""
    got = must(answer, "list")
    return got if isinstance(got, list) else []


def by_code(api: Api, path: str, code: str) -> dict:
    """Return the row with this code from a list."""
    joiner = "&" if "?" in path else "?"
    for row in rows_of(api.get(f"{path}{joiner}search={code}&page_size=100")):
        if row.get("code") == code:
            return row
    raise SystemExit(f"PRECONDITION no {code} at {path}")


def admin(which: str = "admin") -> Api:
    """Return a signed-in account of the module's state."""
    return client(which, "collections")


@contextmanager
def settings(api: Api, **wanted: object):  # noqa: ANN201
    """Run a block with the selling workflow settings changed, then put them back."""
    held = must(api.get(SETTINGS), "workflow settings")
    keys = (
        "quotation_stage", "sales_order_stage", "delivery_note_stage",
        "default_branch_id", "default_warehouse_id", "promotion_mode",
        "max_line_discount_percent", "rate_includes_tax",
        "new_outlets_need_approval", "reservation_lapse_days",
        "sales_order_approval", "delivery_note_approval",
        "sales_invoice_approval", "round_bills_to_rupee", "salesman_required",
        "box_and_piece_entry",
    )
    base = {k: held[k] for k in keys if k in held}
    must(api.put(SETTINGS, {**base, **wanted}), "settings changed")
    try:
        yield held
    finally:
        must(api.put(SETTINGS, base), "settings put back")


def counter(api: Api, **extra: object):  # noqa: ANN201
    """Settings with the order and note stages off, so a bill is typed alone."""
    return settings(api, sales_order_stage=False, delivery_note_stage=False, **extra)


class Scene:
    """One stocked 100.00 item (18% GST: a bill of 1 is 118.00) and helpers."""

    def __init__(self, api: Api, stock: str = "500", price: str = "100") -> None:
        """Make the item with stock in MAIN."""
        self.api = api
        self.tag = suffix(5)
        self.branch = by_code(api, "/api/v1/branches", "HO")
        self.warehouse = by_code(api, "/api/v1/warehouses", "MAIN")
        self.piece = next(
            u["id"]
            for u in rows_of(api.get("/api/v1/uom-framework/uoms?page_size=100"))
            if u["code"] == "PIECE"
        )
        self.product = self._product(price, stock)

    def _product(self, price: str, stock: str) -> dict:
        api = self.api
        made = must(
            api.post(
                "/api/v1/products",
                {
                    "code": f"C{self.tag}",
                    "name": f"Collections check item {self.tag}",
                    "brand_id": check_brand(api),
                    "product_type": "STOCK_ITEM",
                    "tax_profile_group_code": "GST_18_LOCAL",
                    "selling_price": price,
                    "purchase_price": "60",
                    "base_uom_id": self.piece,
                    "inventory_uom_id": self.piece,
                    "sales_uom_id": self.piece,
                    "purchase_uom_id": self.piece,
                },
            ),
            "product",
        )
        stocked = must(
            api.post(
                "/api/v1/inventory/opening-stock",
                {
                    "branch_id": self.branch["id"],
                    "warehouse_id": self.warehouse["id"],
                    "reference_number": f"OS-C{self.tag}",
                    "posting_date": today().isoformat(),
                    "lines": [
                        {"product_id": made["id"], "quantity": stock, "unit_cost": "60"}
                    ],
                },
            ),
            "opening stock",
        )
        must(
            api.post(f"/api/v1/inventory/opening-stock/{stocked['id']}/post", {}),
            "post opening stock",
        )
        return made

    def customer(self, **extra: object) -> dict:
        """Make a customer of this scene's tag."""
        n = suffix(4)
        return must(
            self.api.post(
                CU,
                {
                    "code": f"CL{self.tag}{n}",
                    "name": f"Collect buyer {self.tag}{n}",
                    "customer_type": "BUSINESS",
                    "currency_code": "INR",
                    **extra,
                },
            ),
            "customer",
        )

    def bill(self, customer: dict, qty: str = "1", approve: bool = True) -> dict:
        """Type and approve a counter bill (the caller holds ``counter``).

        One piece is 100.00 plus 18% tax: 118.00.
        """
        made = must(
            self.api.post(
                SI,
                {
                    "customer_id": customer["id"],
                    "branch_id": self.branch["id"],
                    "invoice_date": today().isoformat(),
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
        if approve:
            made = must(self.api.post(f"{SI}/{made['id']}/approve", {}), "bill approve")
        return made


def receipt(
    api: Api,
    customer: dict,
    amount: str,
    bills: list[tuple[dict, str]] | None = None,
    method: str = "BANK",
    **extra: object,
) -> tuple[int, Any]:
    """Record a receipt from a customer, set against the given (bill, amount)."""
    body: dict[str, Any] = {
        "party_id": customer["id"],
        "settlement_date": today().isoformat(),
        "amount": amount,
        "method": method,
        "allocations": [
            {"invoice_id": b["id"], "amount": a} for b, a in (bills or [])
        ],
        **extra,
    }
    return api.post(RC, body)


def position(api: Api, customer: dict) -> tuple[Decimal, Decimal]:
    """Return (outstanding, unapplied advance) of a customer from its summary."""
    got = must(api.get(f"{CU}/{customer['id']}/receivables/summary"), "summary")
    return D(got["outstanding"]), D(got["unapplied_advance"])


def closing(api: Api, customer: dict) -> Decimal:
    """Return the customer's statement closing balance for today."""
    day = today().isoformat()
    got = must(
        api.get(f"{CU}/{customer['id']}/statement?from_date={day}&to_date={day}"),
        "statement",
    )
    return D(got["closing_balance"])


def owing(api: Api, customer: dict, bill: dict) -> Decimal:
    """Return what a bill still owes, from the receipt screen's outstanding list."""
    rows = rows_of(
        api.get(f"{RC}/outstanding?customer_id={customer['id']}&with_shops=true")
    )
    for row in rows:
        if row["invoice_id"] == bill["id"]:
            return D(row["outstanding_amount"])
    return Decimal(0)


def journal(api: Api, reference: str) -> list[dict]:
    """Return the journal entries whose reference matches a document number."""
    status, body = api.get(
        f"/api/v1/finance/journal-entries?search={reference}&page_size=50"
    )
    rows = data(body) if status == 200 else []
    return [e for e in rows if reference in str(e.get("reference_number"))]


def entry_by_id(api: Api, entry_id: str) -> dict:
    """Read one journal entry."""
    return must(api.get(f"/api/v1/finance/journal-entries/{entry_id}"), "entry")


def balanced(entry: dict) -> bool:
    """True when an entry's debits equal its credits to the paisa."""
    dr = sum((D(line["debit_amount"]) for line in entry["lines"]), Decimal(0))
    cr = sum((D(line["credit_amount"]) for line in entry["lines"]), Decimal(0))
    return dr == cr and dr > 0


def entry_net(api: Api, entry: dict) -> dict[str, Decimal]:
    """Net debit (+) / credit (-) per control purpose (or account id) of an entry."""
    accounts = {
        r["ledger_account_id"]: r["purpose"]
        for r in rows_of(api.get("/api/v1/finance/control-accounts"))
        if r.get("ledger_account_id")
    }
    net: dict[str, Decimal] = {}
    for line in entry["lines"]:
        key = accounts.get(line["ledger_account_id"], line["ledger_account_id"][:8])
        net[key] = (
            net.get(key, Decimal(0)) + D(line["debit_amount"]) - D(line["credit_amount"])
        )
    return net


def ensure_user(
    platform: Api, email: str, title: str, firm_id: str, role_code: str
) -> str:
    """Find or make a user in one firm holding one role; return the user id."""
    found = [
        r
        for r in rows_of(platform.get(f"/api/v1/users?search={email}&page_size=10"))
        if r.get("email") == email
    ]
    if found:
        user_id = found[0]["id"]
    else:
        user_id = must(
            platform.post(
                "/api/v1/users",
                {
                    "email": email,
                    "full_name": title,
                    "password": PASSWORD,
                    "is_active": True,
                    "force_password_change": False,
                },
            ),
            f"user {email}",
        )["id"]
        must(
            platform.put(
                f"/api/v1/users/{user_id}/firms",
                {
                    "assignments": [
                        {"firm_id": firm_id, "is_primary": True, "is_active": True}
                    ]
                },
            ),
            "membership",
        )
    inside = platform.inside(firm_id)
    roles = rows_of(inside.get(f"/api/v1/roles?search={role_code}&page_size=50"))
    role = next(r for r in roles if r["code"] == role_code)
    must(
        platform.put(
            f"/api/v1/users/{user_id}/firms/{firm_id}/roles", {"ids": [role["id"]]}
        ),
        f"role {role_code}",
    )
    return str(user_id)


def collector_ids() -> tuple[str, str]:
    """Return the user ids of the two Bill Collectors."""
    held = state("collections")
    return held["collector1_id"], held["collector2_id"]


def hand(api: Api, invoice_ids: list[str], collector_id: str) -> tuple[int, Any]:
    """Hand bills to a collector."""
    return api.post(
        f"{COL}/handovers",
        {
            "collector_id": collector_id,
            "handed_on": today().isoformat(),
            "invoice_ids": invoice_ids,
        },
    )


def journal_count(api: Api) -> int:
    """Return how many journal entries the firm holds."""
    status, body = api.get("/api/v1/finance/journal-entries?page_size=1")
    if status != 200:
        raise SystemExit(f"PRECONDITION journal count: {status} {message(body)}")
    return int((body.get("pagination") or {}).get("total_records", 0))


def day_range() -> str:
    """Return the query string of today's statement."""
    day = today().isoformat()
    return f"from_date={day}&to_date={day}"


def trial_totals(api: Api) -> tuple[Decimal, Decimal, Decimal]:
    """Return (closing debit total, closing credit total, receivables closing)."""
    day = today().isoformat()
    period = next(
        p
        for p in rows_of(api.get("/api/v1/finance/accounting-periods?page_size=100"))
        if p["starts_on"] <= day <= p["ends_on"]
    )
    got = must(
        api.get(f"/api/v1/finance/trial-balance?accounting_period_id={period['id']}"),
        "trial balance",
    )
    receivable = next(
        (D(x["closing_balance"]) for x in got["lines"] if x["account_name"] == "Trade Receivables"),
        Decimal(0),
    )
    return D(got["total_closing_debit"]), D(got["total_closing_credit"]), receivable


def address(area: str, city: str = "Mysuru") -> list[dict]:
    """Return a one-address list for a customer in an area."""
    return [
        {
            "address_type": "BILLING", "address_line1": "1 Check Street", "area": area,
            "city": city, "state": "Karnataka", "country": "IN", "postal_code": "570001",
            "is_default_billing": True,
        }
    ]


def account_balance(api: Api, name: str) -> Decimal:
    """Return a ledger account's closing balance (its own side) for today's period."""
    day = today().isoformat()
    period = next(
        p
        for p in rows_of(api.get("/api/v1/finance/accounting-periods?page_size=100"))
        if p["starts_on"] <= day <= p["ends_on"]
    )
    got = must(
        api.get(f"/api/v1/finance/trial-balance?accounting_period_id={period['id']}"),
        "trial balance",
    )
    return next(
        (D(x["closing_balance"]) for x in got["lines"] if x["account_name"] == name),
        Decimal(0),
    )
