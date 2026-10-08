"""TC-MAST-031: goods type in the analyses, the stock reports and the product list.

Reads whatever TEST01 holds rather than building documents of its own: every
figure is checked against the same report asked another way, so the check
holds on any data and leaves nothing behind.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from decimal import Decimal

from common import Check, all_rows, client, data, message

c = Check("tc_mast_031")
admin, sales, store = client("admin"), client("sales"), client("store")
PERIOD = "from_date=2024-04-01&to_date=2026-12-31"
SALES = "/api/v1/sales-invoices/reports/analysis"
BUYS = "/api/v1/purchase-invoices/reports/analysis"

s, b = admin.get("/api/v1/products/goods-types")
names = {row["id"]: row["name"] for row in data(b)}
c.eq(s, 200, "the firm's goods types are read")


def net(cell: dict) -> Decimal:
    """Return a cell's net as a number."""
    return Decimal(str(cell["net"]))


def analysis(path: str, query: str) -> dict:
    """Return one analysis, or stop the case on a refusal."""
    status, body = admin.get(f"{path}?{PERIOD}&{query}")
    if status != 200:
        raise SystemExit(f"PRECONDITION {path} {query}: {status} {message(body)}")
    return data(body)


seen: set[str] = set()
for label, path, basis in (
    ("sales", SALES, "billed"),
    ("sales booked", SALES, "ordered"),
    ("purchases", BUYS, "billed"),
    ("purchases received", BUYS, "received"),
    ("purchases ordered", BUYS, "ordered"),
):
    by_type = analysis(path, f"rows=goods_type&basis={basis}")
    by_product = analysis(path, f"rows=product&basis={basis}")
    rows = {row["key"]: row["label"] for row in by_type["rows"]}
    # (a)/(d) every row is General or a goods type the firm can see, by name
    c.ok(all(rows[key] == ("General" if key == "" else names.get(key)) for key in rows),
         f"{label} (a) each row reads General or its type's name", rows)
    total = sum((net(by_type["row_totals"][key]) for key in rows), Decimal(0))
    c.eq(total, net(by_type["grand_total"]), f"{label} (a) the rows add up to the grand total")
    c.eq(net(by_type["grand_total"]), net(by_product["grand_total"]),
         f"{label} (a) the same grand total as by product")
    c.eq(by_type["grand_total"]["invoices"], by_product["grand_total"]["invoices"],
         f"{label} (a) the same count of documents as by product")
    seen |= set(rows)
    crossed = analysis(path, f"rows=goods_type&columns=month&basis={basis}")
    c.eq(sum((net(cell["figures"]) for cell in crossed["cells"]), Decimal(0)),
         net(crossed["grand_total"]), f"{label} (a) by month the cells add up")
    # (b) the filter narrows to exactly the row it names
    for key in [key for key in rows if key]:
        narrowed = analysis(path, f"rows=product&goods_type_id={key}&basis={basis}")
        c.eq(net(narrowed["grand_total"]), net(by_type["row_totals"][key]),
             f"{label} (b) filtered to {rows[key]}: the row's own total")
    typed = sum((net(by_type["row_totals"][key]) for key in rows if key), Decimal(0))
    c.eq(net(by_type["row_totals"].get("", {"net": 0})), net(by_type["grand_total"]) - typed,
         f"{label} (b) General is what no type claims")
    # (g) one dimension cannot sit on both axes
    c.refused(admin.get(f"{path}?{PERIOD}&rows=goods_type&columns=goods_type"), 422,
              "different dimension", f"{label} (g) goods type on both axes")

c.ok("" in seen, "(a) some document of the firm is of General goods", seen)
c.ok(seen - {""}, "(a) some document of the firm is of a goods type", seen)

# (c) the invoices behind a goods type's sales are that type's lines
by_type = analysis(SALES, "rows=goods_type")
for key in [row["key"] for row in by_type["rows"] if row["key"]]:
    s, b = admin.get(f"{SALES}/invoices?{PERIOD}&goods_type_id={key}")
    c.eq(s, 200, "(c) the invoices behind a goods type are listed")
    gross = analysis(SALES, f"rows=product&goods_type_id={key}&net_of_returns=false")
    notes = analysis(SALES, f"rows=product&goods_type_id={key}")
    c.ok(sum((Decimal(str(row["net"])) for row in data(b)), Decimal(0))
         <= net(gross["grand_total"]),
         "(c) the invoices sum to no more than the type's gross sales",
         (len(data(b)), str(net(gross["grand_total"])), str(net(notes["grand_total"]))))

# (e) the stock reports state each item's goods type
products = {row["code"]: row for row in all_rows(admin, "/api/v1/products")}


def expected(code: str) -> str:
    """Return the goods type name a report should show for a product code."""
    return names.get(products[code].get("goods_type_id") or "", "General")


for report in ("stock-valuation", "stock-ageing", "dead-stock?days=1"):
    joiner = "&" if "?" in report else "?"
    rows = all_rows(admin, f"/api/v1/inventory/reports/{report}{joiner}to_date=2026-12-31")
    items = [row for row in rows if row.get("row_type", "ITEM") == "ITEM"]
    known = [row for row in items if row["product_code"] in products
             and (products[row["product_code"]].get("goods_type_id") or "") in {"", *names}]
    wrong = [(row["product_code"], row["goods_type"]) for row in known
             if row["goods_type"] != expected(row["product_code"])]
    c.eq(wrong[:5], [], f"(e) {report}: every item reads its product's goods type")
    c.ok(known, f"(e) {report}: the report holds items to read", len(items))
    closing = [row["goods_type"] for row in rows if row.get("row_type", "ITEM") != "ITEM"]
    c.eq(set(closing) - {""}, set(), f"(e) {report}: a closing row carries no goods type")

# (f) the product list's filter, and its count
everything = len(products)
plain = all_rows(admin, "/api/v1/products?general_goods=true")
general = len(plain)
c.ok(all(not row.get("goods_type_id") for row in plain),
     "(f) General lists only products with no goods type")
s, b = admin.get("/api/v1/products?page_size=1&general_goods=true")
c.eq(b["pagination"]["total_records"], general, "(f) the count under the list matches it")
counted = general
# A product filed before D-MST-21 was fixed can hold a type since deleted,
# which the firm's list no longer shows: it is still found by its id.
on_products = {row["goods_type_id"] for row in products.values() if row.get("goods_type_id")}
for key in sorted(set(names) | on_products):
    held = all_rows(admin, f"/api/v1/products?goods_type_id={key}")
    counted += len(held)
    c.ok(all(row.get("goods_type_id") == key for row in held),
         f"(f) {names.get(key, key)} lists only its own products")
c.eq(counted, everything, "(f) General and the types together are every product")
c.ok(general < everything, "(f) the firm holds a product with a goods type", (general, everything))
c.refused(admin.get("/api/v1/products?goods_type_id=not-an-id"), 422, "",
          "(f) a goods type that is not an id")

# the roles that read the reports and the list are not refused the new parameters
c.eq(sales.get(f"{SALES}?{PERIOD}&rows=goods_type")[0], 200,
     "the sales user reads sales by goods type")
c.eq(store.get("/api/v1/products?page_size=1&general_goods=true")[0], 200,
     "the store user filters the product list by General")
c.done()
