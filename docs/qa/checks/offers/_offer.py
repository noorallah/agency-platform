"""Helpers the offers-on-the-line checks share (not a check; run.py skips it).

Every check makes a scene of its own in the selling-firm fixture: one item at
100.00 (GST 12%), one customer on a standing rate of 2% with a price list
CITY at 4% of his own, and the offers the check asks for, each matched to
that item alone so no other check's offers reach it. The worked example of
``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`` section 1 is ``tea()``:
TEA-5 (5% off a line of 5 or more) and TEA-11 (buy 11 get 1 free, part share
allowed), both combining.
"""

from __future__ import annotations

import pathlib
import sys
from collections.abc import Iterator
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
    message,
    save_state,
    sign_in,
    state,
    suffix,
)

SO = "/api/v1/sales-orders"
SI = "/api/v1/sales-invoices"
QT = "/api/v1/quotations"
SETTINGS = f"{SO}/workflow-settings"
STAGES = ("quotation_stage", "sales_order_stage", "delivery_note_stage")


def D(value: object) -> Decimal:  # noqa: N802
    """Return a Decimal from whatever the server sent."""
    return Decimal(str(value if value is not None else 0))


def today() -> date:
    """Return the firm's business day (India), as the server judges it."""
    return (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date()


def must(answer: tuple[int, Any], what: str) -> Any:  # noqa: ANN401
    """Return the data of a 2xx answer or stop saying what was refused."""
    status, body = answer
    if status not in (200, 201):
        raise SystemExit(f"PRECONDITION {what}: {status} {message(body)}")
    return data(body)


def rows_of(answer: tuple[int, Any]) -> list[Any]:
    """Return the list of a list answer, or stop."""
    status, body = answer
    if status != 200:
        raise SystemExit(f"PRECONDITION list: {status} {message(body)}")
    got = data(body)
    return got if isinstance(got, list) else []


def by_code(api: Api, path: str, code: str) -> dict:
    """Return the row with this code from a list."""
    joiner = "&" if "?" in path else "?"
    for row in rows_of(api.get(f"{path}{joiner}search={code}&page_size=100")):
        if row.get("code") == code:
            return row
    raise SystemExit(f"PRECONDITION no {code} at {path}")


def admin() -> Api:
    """Return the selling firm's administrator."""
    return client("admin", "offers")


# ---------------------------------------------------------------- settings


@contextmanager
def mode(api: Api, wanted: str) -> Iterator[dict]:
    """Run a block under one ``promotion_mode`` and put the firm's back after.

    Yields the settings as they were. The stage switches are sent as read,
    because the write replaces all three.
    """
    held = must(api.get(SETTINGS), "workflow settings")
    body = {key: held[key] for key in STAGES}
    must(api.put(SETTINGS, {**body, "promotion_mode": wanted}), f"mode {wanted}")
    try:
        yield held
    finally:
        must(
            api.put(SETTINGS, {**body, "promotion_mode": held["promotion_mode"]}),
            "mode put back",
        )


@contextmanager
def counter_billing(api: Api) -> Iterator[None]:
    """Run a block with the order and note stages off, then put them back."""
    held = must(api.get(SETTINGS), "workflow settings")
    body = {key: held[key] for key in STAGES}
    must(
        api.put(
            SETTINGS, {**body, "sales_order_stage": False, "delivery_note_stage": False}
        ),
        "stages off",
    )
    try:
        yield
    finally:
        must(api.put(SETTINGS, body), "stages put back")


# ---------------------------------------------------------------- the scene


class Scene:
    """One item, one customer with a list and a standing rate, and offers."""

    def __init__(
        self,
        api: Api,
        stock: str | None = None,
        breaks: tuple[tuple[str, str], ...] = (("0", "4"),),
    ) -> None:
        """Make the item, the customer and his price list CITY.

        ``breaks`` are CITY's (minimum quantity, percent) rows; ``stock``
        puts that many pieces in MAIN through a posted opening stock.
        """
        self.api = api
        self.tag = suffix(5)
        self.branch = by_code(api, "/api/v1/branches", "HO")
        self.warehouse = by_code(api, "/api/v1/warehouses", "MAIN")
        units = rows_of(api.get("/api/v1/uom-framework/uoms?page_size=100"))
        piece = next(u["id"] for u in units if u["code"] == "PIECE")
        self.product = must(
            api.post(
                "/api/v1/products",
                {
                    "code": f"OF{self.tag}",
                    "name": f"Offer tea {self.tag}",
                    "brand_id": check_brand(api),
                    "product_type": "STOCK_ITEM",
                    "tax_profile_group_code": "GST_12_LOCAL",
                    "selling_price": "100",
                    "purchase_price": "60",
                    "base_uom_id": piece,
                    "inventory_uom_id": piece,
                    "sales_uom_id": piece,
                    "purchase_uom_id": piece,
                },
            ),
            "product",
        )
        self.customer = must(
            api.post(
                "/api/v1/customers",
                {
                    "code": f"OC{self.tag}",
                    "name": f"Offer buyer {self.tag}",
                    "customer_type": "BUSINESS",
                    "currency_code": "INR",
                    "default_discount_percent": "2",
                },
            ),
            "customer",
        )
        self.city = must(
            api.post(
                "/api/v1/price-lists",
                {
                    "code": f"CITY{self.tag}",
                    "name": f"City {self.tag}",
                    "customer_id": self.customer["id"],
                    "effective_from": "2000-01-01",
                    "items": [
                        {
                            "product_id": self.product["id"],
                            "min_quantity": low,
                            "discount_percent": rate,
                        }
                        for low, rate in breaks
                    ],
                },
            ),
            "price list CITY",
        )
        self.offers: dict[str, dict] = {}
        if stock:
            made = must(
                api.post(
                    "/api/v1/inventory/opening-stock",
                    {
                        "branch_id": self.branch["id"],
                        "warehouse_id": self.warehouse["id"],
                        "reference_number": f"OS-{self.tag}",
                        "posting_date": today().isoformat(),
                        "lines": [
                            {
                                "product_id": self.product["id"],
                                "quantity": stock,
                                "unit_cost": "60",
                            }
                        ],
                    },
                ),
                "opening stock",
            )
            must(
                api.post(f"/api/v1/inventory/opening-stock/{made['id']}/post", {}),
                "opening stock post",
            )

    def offer(
        self,
        name: str,
        action: dict,
        priority: int,
        minimum: str | None = None,
        **extra: object,
    ) -> dict:
        """Make an ACTIVE offer on this scene's item alone; keep it by name."""
        conditions: list[dict] = [
            {
                "field_key": "product_id",
                "operator": "EQUALS",
                "value_text": self.product["id"],
            }
        ]
        if minimum:
            conditions.append(
                {
                    "field_key": "line_quantity",
                    "operator": "GREATER_OR_EQUAL",
                    "value_number": minimum,
                    "sequence": 2,
                }
            )
        made = must(
            self.api.post(
                "/api/v1/promotions",
                {
                    "code": f"{name}-{self.tag}",
                    "name": f"{name} {self.tag}",
                    "priority": priority,
                    "status": "ACTIVE",
                    "effective_from": "2020-01-01",
                    "conditions": conditions,
                    "actions": [action],
                    **extra,
                },
            ),
            f"offer {name}",
        )
        self.offers[name] = made
        return made

    def tea(self, part_share: bool = True) -> Scene:
        """Make TEA-5 and TEA-11 of the worked example."""
        self.offer(
            "TEA5", {"action_type": "LINE_DISCOUNT_PERCENT", "percent": "5"}, 10, "5"
        )
        self.offer(
            "TEA11",
            {
                "action_type": "FREE_QUANTITY",
                "buy_quantity": "11",
                "free_quantity": "1",
            },
            20,
            allow_part_share=part_share,
        )
        return self

    def key(self, name: str) -> str:
        """Return an offer's candidate key: its version group id."""
        return str(self.offers[name]["version_group_id"])

    def code(self, name: str) -> str:
        """Return an offer's code."""
        return str(self.offers[name]["code"])

    # ------------------------------------------------------------ documents

    def line(self, qty: str, number: int = 1, **extra: object) -> dict:
        """Return one order or quotation line of this scene's item."""
        return {
            "line_number": number,
            "product_id": self.product["id"],
            "quantity": qty,
            **extra,
        }

    def order_body(self, lines: list[dict], **extra: object) -> dict:
        """Return an order of these lines for this scene's customer."""
        return {
            "customer_id": self.customer["id"],
            "order_date": today().isoformat(),
            "branch_id": self.branch["id"],
            "warehouse_id": self.warehouse["id"],
            "lines": lines,
            **extra,
        }

    def preview(self, lines: list[dict], api: Api | None = None) -> dict:
        """Preview an order of these lines; return its data."""
        return must(
            (api or self.api).post(f"{SO}/preview", self.order_body(lines)),
            "order preview",
        )

    def save(self, lines: list[dict], api: Api | None = None) -> tuple[int, Any]:
        """Save an order of these lines; return the raw answer."""
        return (api or self.api).post(SO, self.order_body(lines))

    def quote_body(self, lines: list[dict]) -> dict:
        """Return a quotation of these lines for this scene's customer."""
        return {
            "customer_id": self.customer["id"],
            "quotation_date": today().isoformat(),
            "valid_until": (today() + timedelta(days=15)).isoformat(),
            "branch_id": self.branch["id"],
            "warehouse_id": self.warehouse["id"],
            "lines": lines,
        }

    def bill_body(self, lines: list[dict]) -> dict:
        """Return a counter bill of bare product lines for this customer."""
        out = []
        for ln in lines:
            row = {
                "line_number": ln["line_number"],
                "product_id": self.product["id"],
                "current_invoice_quantity": ln["quantity"],
            }
            row.update(
                {
                    k: v
                    for k, v in ln.items()
                    if k not in ("line_number", "product_id", "quantity")
                }
            )
            out.append(row)
        return {
            "customer_id": self.customer["id"],
            "branch_id": self.branch["id"],
            "invoice_date": today().isoformat(),
            "lines": out,
        }


def orders_of(scene: Scene) -> list[dict]:
    """Return the orders saved for the scene's customer."""
    return rows_of(
        scene.api.get(f"{SO}?customer_id={scene.customer['id']}&page_size=50")
    )


def cands(preview: dict, number: int = 1) -> list[dict]:
    """Return the candidates of one previewed line."""
    for line in preview["lines"]:
        if line["line_number"] == number:
            return list(line.get("candidates") or [])
    return []


def cand(preview: dict, code_or_source: str, number: int = 1) -> dict | None:
    """Return one line's candidate by its code (offers) or its source."""
    for item in cands(preview, number):
        if item["code"] == code_or_source or item["source"] == code_or_source:
            return item
    return None


def refused_on(preview: dict, number: int = 1) -> str | None:
    """Return why the choice sent on a previewed line was not taken."""
    for line in preview["lines"]:
        if line["line_number"] == number:
            return line.get("choice_refused")
    return None


def doc_line(doc: dict, number: int = 1) -> dict:
    """Return the line of a document (or a preview's document) with this number."""
    for line in doc["lines"]:
        if line["line_number"] == number:
            return line
    raise SystemExit(f"PRECONDITION no line {number}")


def taxable(line: dict) -> Decimal:
    """Return a line's taxable value: gross less its discount and bill share."""
    return (
        D(line["gross_amount"])
        - D(line["discount_amount"])
        - D(line.get("bill_discount_amount"))
    )


def offer_rows(line: dict, wanted: str | None = None) -> list[tuple]:
    """Return a line's offer rows: (name, state, chosen, discount, free, part).

    ``name`` is the offer's code without the scene's tag (TEA5), or the
    source of a standing arrangement (price_list, customer).
    """
    out = []
    for row in line.get("offers") or []:
        if wanted and row["state"] != wanted:
            continue
        name = (
            row["code"].rsplit("-", 1)[0]
            if row["source"] == "promotion"
            else row["source"]
        )
        out.append(
            (
                name,
                row["state"],
                row["chosen"],
                D(row["discount_amount"]),
                D(row["free_quantity"]),
                bool(row.get("part_share")),
            )
        )
    return out


# ---------------------------------------------------------------- users


def ensure_user(
    platform: Api, email: str, title: str, firm_id: str, role_code: str
) -> None:
    """Find or make a user in one firm holding one role."""
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
