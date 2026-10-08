"""Small helpers the goods-type checks share (not a check; run.py skips it)."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import Api, all_rows, data, message, suffix  # noqa: E402,F401


def uom(api: Api, code: str = "PIECE") -> str:
    """Return the id of a unit of measure by code."""
    return next(
        u["id"] for u in all_rows(api, "/api/v1/uom-framework/uoms") if u["code"] == code
    )


def product(api: Api, code: str, **extra: object) -> tuple[int, object]:
    """POST a product that names its switches explicitly; return the answer."""
    piece = uom(api)
    body: dict[str, object] = {
        "code": code,
        "name": f"GT {code}",
        "product_type": "STOCK_ITEM",
        "tax_profile_group_code": "GST_18_LOCAL",
        "selling_price": "100",
        "purchase_price": "60",
        "base_uom_id": piece,
        "inventory_uom_id": piece,
        "sales_uom_id": piece,
        "purchase_uom_id": piece,
    }
    body.update(extra)
    return api.post("/api/v1/products", body)


def one_in_stock(api: Api, product_id: str, tag: str, quantity: int = 1) -> str:
    """Put units of a product into a new warehouse; return the warehouse id.

    A serial number is added only for a unit the firm holds (D-STK-50), so a
    check that adds one by hand gives the product its stock first.
    """
    from datetime import UTC, datetime, timedelta

    tag = f"{tag}{suffix(3)}"
    branch = must(api.get("/api/v1/branches"), "branches")[0]["id"]
    warehouse = must(api.post("/api/v1/warehouses", {
        "code": f"GW{tag}"[:20], "name": f"GT stock {tag}", "branch_id": branch}),
        "warehouse")
    today = (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date()
    made = must(api.post("/api/v1/inventory/opening-stock", {
        "branch_id": branch, "warehouse_id": warehouse["id"],
        "reference_number": f"GO-{tag}", "posting_date": today.isoformat(),
        "lines": [{"product_id": product_id, "quantity": str(quantity),
                   "unit_cost": "60"}]}), "opening stock")
    must(api.post(f"/api/v1/inventory/opening-stock/{made['id']}/post", {}),
         "opening stock posted")
    return warehouse["id"]


def must(answer: tuple[int, object], what: str) -> dict:
    """Return the data of a 2xx answer or stop saying what was refused."""
    status, body = answer
    if status not in (200, 201):
        raise SystemExit(f"PRECONDITION {what}: {status} {message(body)}")
    return data(body)


def audit_actions(api: Api, firm_id: str, action: str) -> list[dict]:
    """Return the audit rows of one action in a firm's own trail."""
    return all_rows(api.inside(firm_id), f"/api/v1/audit-logs?action={action}")


def goods_types(api: Api) -> dict[str, dict]:
    """Return the firm's goods types by code, taking Medicine and Paint into use."""
    status, body = api.get("/api/v1/products/goods-types")
    held = {row["code"]: row for row in data(body)}
    for code in ("MEDICINE", "PAINT"):
        if code in held and not held[code]["in_use"]:
            api.put(f"/api/v1/products/goods-types/{held[code]['id']}/use",
                    {"in_use": True})
    return held


def field(api: Api, code: str, entity: str, **extra: object) -> dict:
    """Add a firm-own optional TEXT custom field and return it."""
    return must(api.post("/api/v1/business-framework/firm-custom-fields", {
        "code": code, "name": code.title(), "entity_type": entity,
        "data_type": "TEXT", "mandatory": False, **extra}), f"field {code}")


def rule(api: Api, field_id: str, **target: object) -> tuple[int, object]:
    """POST a firm field rule naming one thing."""
    return api.post("/api/v1/business-framework/firm-custom-field-rules",
                    {"attribute_definition_id": field_id, **target})


def customer_body(code: str, **extra: object) -> dict[str, object]:
    """Return the smallest customer a save accepts."""
    return {"code": code, "name": f"Cust {code}", "customer_type": "BUSINESS",
            "currency_code": "INR", **extra}


def vendor_body(code: str, **extra: object) -> dict[str, object]:
    """Return the smallest supplier a save accepts."""
    return {"code": code, "name": f"Supp {code}", **extra}


def clear_tracked_products(api: Api) -> int:
    """Delete every live product of an own-made firm that tracks anything.

    Only for the firms ``setup_firms.py`` made (nothing else lives there). Their
    batches and serial numbers go first. Returns how many products were removed.
    """
    removed = 0
    for row in all_rows(api, "/api/v1/products"):
        if not any(row.get(k) for k in ("track_batch", "track_expiry", "track_serial",
                                        "track_warranty", "track_manufacturing_date")):
            continue
        for kind in ("batches", "serials"):
            for item in all_rows(api, f"/api/v1/batch-serial/{kind}?product_id={row['id']}"):
                if item.get("product_id") == row["id"]:
                    api.delete(f"/api/v1/batch-serial/{kind}/{item['id']}")
        if api.delete(f"/api/v1/products/{row['id']}")[0] in (200, 204):
            removed += 1
    return removed
