"""TC-MAST-026: the Inventory menu (goods_tracking of active-modules) follows the goods."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, message, state, suffix
from _lib import clear_tracked_products, must, product

c = Check("tc_mast_026")
tag = suffix()
admin, manager, cashier = client("generic_admin"), client("generic_manager"), client("generic_cashier")
test02 = client("test02_admin")
generic = state()["own_firms"]["generic"]["id"]
AM = "/api/v1/business-framework/active-modules"


def tracking(api) -> object:
    """The INVENTORY row's goods_tracking, and the other rows' (all null)."""
    s, b = api.get(AM)
    rows = data(b)
    inv = [r for r in rows if r["code"] == "INVENTORY"]
    others = {r["code"]: r["goods_tracking"] for r in rows if r["code"] != "INVENTORY"}
    return (s, sorted(inv[0]["goods_tracking"]) if inv and inv[0]["goods_tracking"] is not None
            else (inv[0]["goods_tracking"] if inv else "no INVENTORY row"), others)


def use(code: str, on: bool) -> tuple[int, object]:
    """Take a shared goods type into use or drop it."""
    s, b = admin.get("/api/v1/products/goods-types")
    row = next(r for r in data(b) if r["code"] == code)
    return admin.put(f"/api/v1/products/goods-types/{row['id']}/use", {"in_use": on})


def types() -> dict[str, dict]:
    """The firm's goods types by code."""
    s, b = admin.get("/api/v1/products/goods-types")
    return {r["code"]: r for r in data(b)}


def clear_categories() -> None:
    """Take every goods type off every category, then stop using every type."""
    s, b = admin.get("/api/v1/products/categories?page_size=100")
    for row in data(b):
        if row.get("goods_type_id"):
            admin.put(f"/api/v1/products/categories/{row['id']}", {
                "code": row["code"], "name": row["name"], "goods_type_id": None})
    for code, row in types().items():
        if row["in_use"]:
            use(code, False)


# the firm is this suite's own: remove tracked products an earlier check (029) left
clear_tracked_products(admin)
clear_categories()
# (a) nothing in use, nothing on the menu
s, inv, others = tracking(admin)
c.eq((s, inv), (200, []), "(a) a firm with no goods type and no tracked product: empty list")
c.eq(set(others.values()), {None} if others else set(), "(a) every other row carries null")

# (b) Paint in use, a category under it
c.eq(use("PAINT", True)[0], 200, "(b) Paint taken into use")
cat = must(admin.post("/api/v1/products/categories", {
    "code": f"ENAM{tag}", "name": f"Enamels {tag}", "goods_type_id": types()["PAINT"]["id"]}), "category")
c.eq(tracking(admin)[1], ["BATCH"], "(b) Paint in use: BATCH")

# a type still carried by a category cannot be dropped
c.refused(use("PAINT", False), 409, "", "(b) dropping Paint while a category carries it")
# (c) Electronics
c.eq(use("ELECTRONICS", True)[0], 200, "(c) Electronics taken into use")
c.eq(tracking(admin)[1], ["BATCH", "SERIAL"], "(c) Paint and Electronics: BATCH and SERIAL, no EXPIRY")
# Medicine adds expiry
c.eq(use("MEDICINE", True)[0], 200, "Medicine taken into use")
c.eq(tracking(admin)[1], ["BATCH", "EXPIRY", "SERIAL"], "Medicine adds EXPIRY")
use("MEDICINE", False)

# (e) the user without BATCH_VIEW, Paint (and Electronics) still in use
s, inv, others = tracking(cashier)
c.eq(inv, ["BATCH", "SERIAL"], "(e) the cashier is told the same goods tracking")
c.eq(cashier.get("/api/v1/batch-serial/batches")[0], 403, "(e) but may not open Batches (no BATCH_VIEW)")
c.eq(cashier.get("/api/v1/batch-serial/serials")[0], 403, "(e) nor Serial Numbers (no SERIAL_VIEW)")
c.eq(tracking(manager)[1], ["BATCH", "SERIAL"], "the firm manager is told the same")

# (h) no X-Firm-ID header: answered, and no row says anything about tracking
s, b = admin.inside(None).get(AM)
c.eq((s, [r for r in data(b) if r["goods_tracking"] is not None] if s == 200 else None), (200, []),
     "(h) with no X-Firm-ID the call is answered and no row carries tracking")
# platform admin inside the firm sees the same as the firm's admin
c.eq(tracking(client("generic_platform"))[1], ["BATCH", "SERIAL"], "(h) the platform admin inside the firm")

# (d) clear and stop using both
clear_categories()
c.eq(tracking(admin)[1], [], "(d) all types dropped: empty again")

# (f) a firm with no goods type but a live product that tracks batch
sku = must(product(test02, f"TRK-{tag}", track_batch=True), "product in TEST02")
s, inv, others = tracking(test02)
c.ok("BATCH" in (inv or []), "(f) a live product with Track batch on adds BATCH although no type is used", inv)
c.done()
