"""Point the compliance checks at fixture firm T1016VSH1-S (and T1016SOTP-S as firm two).

    python docs/qa/checks/compliance/setup_vsh1.py

The older ``setup.py`` runs the ``compliance-firm`` fixture twice and builds new
firms. These two fixture firms have no GST number, so this gives each a
Tamil Nadu GSTIN, a product at HSN 340220, a registered buyer (``-B2B``), a
walk-in (``-B2C``) and invoices A (10, collected, registered), B (5, registered)
and C (3, unregistered buyer) -- the shape the checks read. Re-running finds
what exists. Writes ``.state/compliance.json``. The firms already trade, so a
check that counts the month's invoices sees more than A, B and C.
"""
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import (  # noqa: E402
    EINV, SI, Own, by_code, counter, data, must, rows_of, today,
)
from common import check_brand, client, save_state, state  # noqa: E402

ONE = ("selling", "admin", "t1016vsh1")
TWO = ("selling", "admin2", "t1016sotp")
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin(head: str) -> str:
    """Complete a 14-character head with its check character."""
    total = 0
    for i, ch in enumerate(head):
        p = ALPHABET.index(ch) * (1 if i % 2 == 0 else 2)
        total += p // 36 + p % 36
    return head + ALPHABET[(36 - total % 36) % 36]


def prepare(which: str, who: str, stem: str) -> dict:
    """Give one firm its GSTIN, product and customers; return its state entry."""
    firm_id = state("selling")["accounts"][who]["firm_id"]
    platform = client("platform", "selling")
    tag = stem.upper()
    row = must(platform.get(f"/api/v1/firms/{firm_id}"), "firm")
    mine = row.get("gst_number")
    if not mine:
        mine = gstin(f"33ABCDF{random.randint(1000, 9999)}A1Z")
        body = {k: row[k] for k in ("name", "code", "country", "currency_code", "financial_year_start")}
        must(platform.put(f"/api/v1/firms/{firm_id}", {**body, "gst_number": mine}), "firm gstin")
    a = client(who, "selling")
    buyer_g = gstin(f"33ABCDE{random.randint(1000, 9999)}B1Z")
    cust = {}
    for suffix, name, kind, extra in (
        ("B2B", "Registered Buyer", "BUSINESS", {"gst_number": buyer_g, "pan_number": buyer_g[2:12]}),
        ("B2C", "Walk-in Buyer", "INDIVIDUAL", {}),
    ):
        found = rows_of(a.get(f"/api/v1/customers?search={tag}-{suffix}"))
        cust[suffix] = next((c for c in found if c["code"] == f"{tag}-{suffix}"), None) or must(
            a.post("/api/v1/customers", {"code": f"{tag}-{suffix}", "name": f"{name} {stem}", "customer_type": kind, "currency_code": "INR", **extra}), "customer")
    buyer_gstin = cust["B2B"].get("gst_number") or buyer_g
    if not any(p["code"] == f"{tag}-P" for p in rows_of(a.get(f"/api/v1/products?search={tag}-P"))):
        piece = next(u["id"] for u in rows_of(a.get("/api/v1/uom-framework/uoms?page_size=100")) if u["code"] == "PIECE")
        made = must(a.post("/api/v1/products", {
            "code": f"{tag}-P", "name": f"Compliance product {stem}", "brand_id": check_brand(a),
            "hsn_sac": "340220", "product_type": "STOCK_ITEM", "tax_profile_group_code": "GST_18_LOCAL",
            "selling_price": "100", "purchase_price": "60", "base_uom_id": piece, "inventory_uom_id": piece,
            "sales_uom_id": piece, "purchase_uom_id": piece}), "product")
        branch, wh = by_code(a, "/api/v1/branches", "HO"), by_code(a, "/api/v1/warehouses", "MAIN")
        os_ = must(a.post("/api/v1/inventory/opening-stock", {
            "branch_id": branch["id"], "warehouse_id": wh["id"], "reference_number": f"{tag}-OS-{random.randint(100, 999)}",
            "posting_date": today().isoformat(),
            "lines": [{"product_id": made["id"], "quantity": "500", "unit_cost": "60"}]}), "opening stock")
        must(a.post(f"/api/v1/inventory/opening-stock/{os_['id']}/post", {}), "post opening stock")
    return {"email": state("selling")["accounts"][who]["email"], "firm_id": firm_id, "code": row["code"],
            "gstin": mine, "buyer_gstin": buyer_gstin, "suffix": stem, "invoices": {}, "_c": cust}


def main() -> None:
    """Build both entries, then the three bills in each."""
    sel = state("selling")["accounts"]
    entries = {k: prepare(*spec) for k, spec in (("one", ONE), ("two", TWO))}
    save_state({
        "accounts": {"platform": sel["platform"], "admin": sel["admin"], "admin2": sel["admin2"]},
        "one": {k: v for k, v in entries["one"].items() if k != "_c"},
        "two": {k: v for k, v in entries["two"].items() if k != "_c"},
    }, "compliance")
    for k in ("one", "two"):
        o = Own(k)
        cust = entries[k]["_c"]
        got = {}
        for key, who, qty, reg in (("A", "B2B", "10", True), ("B", "B2B", "5", True), ("C", "B2C", "3", False)):
            bill = o.bill(cust[who], qty)
            got[key] = bill["id"]
            if reg:
                o.register(bill)
        save_state({k: {**{kk: vv for kk, vv in entries[k].items() if kk != "_c"}, "invoices": got}}, "compliance")
    print("state written")


if __name__ == "__main__":
    main()




