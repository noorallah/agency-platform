"""Helpers the inventory checks share (not a check; run.py skips it)."""

from __future__ import annotations

import pathlib
import sys
from decimal import Decimal
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402,F401
    Api,
    Check,
    all_rows,
    client,
    data,
    message,
    state,
    suffix,
)

INV = "/api/v1/inventory"
TODAY_HINT = None


def D(value: Any) -> Decimal:
    """Decimal from anything the server returned."""
    return Decimal(str(value if value is not None else 0))


def must(answer: tuple[int, Any], what: str) -> Any:
    """Return the data of a 2xx answer or stop saying what was refused."""
    status, body = answer
    if status not in (200, 201):
        raise SystemExit(f"PRECONDITION {what}: {status} {message(body)}")
    return data(body)


def today(api: Api) -> str:
    """Return the firm's today (IST) from a harmless server read."""
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date().isoformat()


class World:
    """One check's own records inside the generic fixture firm."""

    def __init__(self) -> None:
        self.tag = suffix()
        self.admin = client("admin")
        self.firm_id = state()["firm_id"]
        self._uom: str | None = None
        self.branch_id = must(self.admin.get("/api/v1/branches"), "branches")[0]["id"]
        self.today = today(self.admin)

    # ----- masters -------------------------------------------------------
    @property
    def piece(self) -> str:
        """The PIECE unit id."""
        if self._uom is None:
            self._uom = next(
                u["id"]
                for u in all_rows(self.admin, "/api/v1/uom-framework/uoms")
                if u["code"] == "PIECE"
            )
        return self._uom

    def warehouse(self, label: str = "W") -> dict[str, Any]:
        """Create a warehouse under the head office."""
        code = f"{label}{self.tag}{suffix(3)}"[:20]
        return must(
            self.admin.post(
                "/api/v1/warehouses",
                {"code": code, "name": f"{label} {code}", "branch_id": self.branch_id},
            ),
            "warehouse",
        )

    def goods_type_category(self, goods_type: str) -> str:
        """Put a shared goods type in use and return a category carrying it."""
        held = getattr(self, "_cats", {})
        self._cats = held
        if goods_type in held:
            return held[goods_type]
        status, body = self.admin.get("/api/v1/products/goods-types")
        row = next(r for r in data(body) if r["code"] == goods_type)
        if not row["in_use"]:
            self.admin.put(f"/api/v1/products/goods-types/{row['id']}/use", {"in_use": True})
        made = must(
            self.admin.post(
                "/api/v1/products/categories",
                {"code": f"C{goods_type[:4]}{self.tag}{suffix(2)}", "name": f"{goods_type} {self.tag}", "goods_type_id": row["id"]},
            ),
            "category",
        )
        held[goods_type] = made["id"]
        return made["id"]

    def product(self, label: str = "P", goods_type: str | None = None, **extra: Any) -> dict[str, Any]:
        """Create a stock item; purchase price 60, selling 100 unless given.

        ``goods_type`` (MEDICINE, ELECTRONICS, ...) is carried by a category.
        """
        code = f"{label}{self.tag}{suffix(3)}"
        if goods_type:
            extra["category_id"] = self.goods_type_category(goods_type)
        body: dict[str, Any] = {
            "code": code,
            "name": f"INV {code}",
            "product_type": "STOCK_ITEM",
            "tax_profile_group_code": "GST_18_LOCAL",
            "selling_price": "100",
            "purchase_price": "60",
            "base_uom_id": self.piece,
            "inventory_uom_id": self.piece,
            "sales_uom_id": self.piece,
            "purchase_uom_id": self.piece,
        }
        body.update(extra)
        return must(self.admin.post("/api/v1/products", body), f"product {code}")

    UPDATE_FIELDS = (
        "allow_decimal", "allow_fraction", "allow_negative_stock", "barcode", "base_uom_id", "brand_id", "category_id",
        "code", "default_dispatch_uom_id", "default_receiving_uom_id", "description", "expiry_alert_days",
        "expiry_return_days", "expiry_stop_sale_days", "free_issue_only", "hsn_sac", "inspection_required",
        "inventory_uom_id", "issue_rule", "itc_eligibility", "minimum_sales_uom_id", "minimum_selling_price", "mrp",
        "name", "not_for_sale", "preferred_vendor_id", "product_type", "purchase_price", "purchase_uom_id",
        "require_batch_on_issue", "require_batch_on_receipt", "require_serial_on_issue", "require_serial_on_receipt",
        "sales_uom_id", "selling_price", "shelf_life_days", "short_name", "status", "sub_category_id",
        "tax_profile_group_code", "track_batch", "track_expiry", "track_lot", "track_manufacturing_date",
        "track_serial", "track_warranty",
    )

    def update_product(self, product: dict[str, Any], **changes: Any) -> tuple[int, Any]:
        """PUT the product as the editor does: every field it holds, plus the changes."""
        fresh = must(self.admin.get(f"/api/v1/products/{product['id']}"), "read product")
        body = {k: fresh[k] for k in self.UPDATE_FIELDS if k in fresh and fresh[k] is not None}
        body.update(changes)
        return self.admin.put(f"/api/v1/products/{product['id']}", body)

    # ----- stock in ------------------------------------------------------
    def opening(
        self,
        warehouse_id: str,
        lines: list[dict[str, Any]],
        *,
        post: bool = True,
        api: Api | None = None,
    ) -> dict[str, Any]:
        """Create (and post) an opening-stock batch."""
        api = api or self.admin
        made = must(
            api.post(
                f"{INV}/opening-stock",
                {
                    "branch_id": self.branch_id,
                    "warehouse_id": warehouse_id,
                    "reference_number": f"OS-{self.tag}-{suffix(3)}",
                    "posting_date": self.today,
                    "lines": lines,
                },
            ),
            "opening stock",
        )
        if post:
            made = must(api.post(f"{INV}/opening-stock/{made['id']}/post", {}), "post opening")
        return made

    def stock_in(self, warehouse_id: str, product_id: str, qty: Any, cost: Any = "60") -> None:
        """Put stock into a warehouse through a posted opening-stock batch."""
        self.opening(
            warehouse_id,
            [{"product_id": product_id, "quantity": str(qty), "unit_cost": str(cost)}],
        )

    # ----- reads ---------------------------------------------------------
    def rows(self, product_id: str, api: Api | None = None) -> list[dict[str, Any]]:
        """Inventory rows of a product."""
        return all_rows(api or self.admin, f"{INV}?product_id={product_id}&include_deleted=false")

    def qty(self, product_id: str, warehouse_id: str | None = None, field: str = "current_quantity") -> Decimal:
        """Sum a quantity field over the product's rows (optionally one warehouse)."""
        total = Decimal(0)
        for row in self.rows(product_id):
            if warehouse_id is None or row["warehouse_id"] == warehouse_id:
                total += D(row[field])
        return total

    def ledger(self, product_id: str, **filters: str) -> list[dict[str, Any]]:
        """Stock-ledger rows of a product, oldest first."""
        extra = "".join(f"&{k}={v}" for k, v in filters.items())
        rows = all_rows(self.admin, f"{INV}/ledger?product_id={product_id}{extra}&sort_by=created_at&sort_direction=asc")
        return rows

    def journal_lines_for(self, reference: str) -> list[dict[str, Any]]:
        """Journal entries whose reference or source mentions ``reference``."""
        status, body = self.admin.get(
            f"/api/v1/finance/journal-entries?search={reference}&page_size=50"
        )
        return data(body) if status == 200 else []

    def audit(self, **filters: str) -> list[dict[str, Any]]:
        """This firm's audit rows for the filters."""
        extra = "&".join(f"{k}={v}" for k, v in filters.items())
        return all_rows(self.admin, f"/api/v1/audit-logs?{extra}")

    def inventory_account(self) -> Decimal:
        """The Inventory control account's balance from the valuation report."""
        rows = self.valuation()
        for r in rows:
            if r["row_type"] == "BOOKS":
                return D(r["value"])
        return Decimal(0)

    def valuation(self, api: Api | None = None) -> list[dict[str, Any]]:
        """The stock-valuation report rows (every page)."""
        return all_rows(api or self.admin, f"{INV}/reports/stock-valuation?include_zero=true", size=100)


def journal_total(entries: list[dict[str, Any]]) -> Decimal:
    """Sum of debit of a list of journal entries (shape tolerant)."""
    total = Decimal(0)
    for entry in entries:
        total += D(entry.get("total_debit") or 0)
    return total
