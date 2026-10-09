"""TC-MAST-022: a unit set fills a new product's units and its own conversion rule."""
import datetime
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("tc_mast_022")
tag = suffix()
admin = client("admin")
units = uom_ids(admin)
med = ensure_use(admin, "MEDICINE")
paint = ensure_use(admin, "PAINT")
tablets = cat(admin, tag, "TABLETS", goods_type_id=med["id"])
emulsions = cat(admin, tag, "EMULSIONS", goods_type_id=paint["id"])
sundries = cat(admin, tag, "SUNDRIES")

status, body = admin.get(SETS)
sets = {r["name"]: r for r in data(body)}
shared = {n: r for n, r in sets.items() if r["firm_id"] is None}
c.eq(len(shared), 8, "eight shared unit sets")
types_by_id = {r["id"]: r["code"] for r in data(admin.get(GT)[1])}
bottle = shared.get("Bottle, carton of 24", {})
c.eq(sorted(types_by_id.get(i) for i in bottle.get("goods_type_ids", [])), ["COSMETICS", "FOOD", "MEDICINE"],
     "Bottle, carton of 24 is tied to Medicine, Food and Cosmetics")
c.eq(shared.get("Piece, loose", {}).get("goods_type_ids"), [], "Piece, loose is tied to no type (All goods)")
strip10 = shared.get("Strip, box of 10", {})
c.refused(admin.put(f"{SETS}/{strip10['id']}", {"name": "Edited"}), 422, "shared unit set", "edit a shared set")
c.refused(admin.delete(f"{SETS}/{strip10['id']}"), 422, "shared unit set", "delete a shared set")

# The firm's own set (tied to a goods type of the firm's own, so no shared type is touched).
status, body = admin.post(GT, {"code": f"{tag}-JARS", "name": f"Jars {tag}"})
jar_type = data(body)
jar_name = f"Jar, case of 6 {tag}"
jar_body = {"name": jar_name, "base_uom_id": units["JAR"], "inventory_uom_id": units["JAR"],
            "sales_uom_id": units["JAR"], "purchase_uom_id": units["CASE"], "conversion_factor": "6",
            "goods_type_ids": [jar_type["id"]]}
status, body = admin.post(SETS, jar_body)
c.eq(status, 201, f"own unit set saved ({message(body)})")
jar = data(body) if status == 201 else {}
c.refused(admin.post(SETS, jar_body), 409, "already exists", "repeated set name")
c.refused(admin.post(SETS, {**jar_body, "name": f"Same unit {tag}", "purchase_uom_id": units["JAR"]}), 422,
          "purchase unit that differs", "factor between one and the same unit")

meta = data(admin.get(f"{PRODUCTS}/metadata?category_id={tablets['id']}")[1])
offered = {o["name"]: o for o in meta["unit_sets"]}
c.ok(strip10.get("name") in offered and jar_name in offered, "metadata offers shared and own sets")


def rule_of(product_id):
    rows = data(admin.get(f"/api/v1/uom-framework/conversion-rules?product_id={product_id}&page_size=50")[1])
    return [(r["from_uom_id"], r["to_uom_id"], float(r["conversion_factor"])) for r in rows]


def make(name, **kw):
    status, body = prod(admin, tag, name, **kw)
    c.eq(status, 201, f"{name} created ({message(body)})")
    return get_product(admin, data(body)["id"]) if status == 201 else {}


us1 = make("US1", category_id=tablets["id"], unit_set_id=strip10["id"])
c.eq((us1.get("base_uom_id"), us1.get("purchase_uom_id"), us1.get("inventory_uom_id")),
     (units["STRIP"], units["BOX"], units["STRIP"]), "US-1 takes Strip/Box/Strip")
c.eq(rule_of(us1["id"]), [(units["BOX"], units["STRIP"], 10.0)], "US-1 own rule 1 Box = 10 Strip")
c.eq(us1.get("unit_set_id"), strip10["id"], "US-1 remembers its set")

us2 = make("US2", category_id=tablets["id"], unit_set_id=shared["Strip, box of 15"]["id"])
c.eq(rule_of(us2["id"]), [(units["BOX"], units["STRIP"], 15.0)], "US-2 rule is 15")

us3 = make("US3", category_id=tablets["id"], unit_set_id=strip10["id"], purchase_uom_id=units["CARTON"],
           unit_conversion_factor="120")
c.eq(rule_of(us3["id"]), [(units["CARTON"], units["STRIP"], 120.0)], "US-3 Carton = 120 Strip")
c.eq(us3.get("base_uom_id"), units["STRIP"], "US-3 base unit still Strip")

us4 = make("US4", category_id=emulsions["id"], unit_set_id=strip10["id"])
c.eq(us4.get("base_uom_id"), units["STRIP"], "US-4 (another type's set) saves with the set's units")

us5 = make("US5", category_id=sundries["id"])
c.eq((us5.get("base_uom_id"), us5.get("purchase_uom_id"), rule_of(us5["id"])), (None, None, []), "US-5 no units, no rule")

us6 = make("US6", base_uom_id=units["PIECE"], purchase_uom_id=units["BOX"], unit_conversion_factor="12")
c.eq(rule_of(us6["id"]), [(units["BOX"], units["PIECE"], 12.0)], "US-6 own rule 1 Box = 12 Piece")

# Back-dated order of 2 Box of US-1 converts to 20 Strip.
warehouse = next(w for w in data(admin.get("/api/v1/warehouses?search=MAIN&page_size=50")[1]) if w["code"] == "MAIN")
branch = next(b for b in data(admin.get("/api/v1/branches?page_size=50")[1]) if b["code"] == "HO")
vendor = data(admin.post("/api/v1/vendors", {"code": f"{tag}-V", "name": f"Supplier {tag}"})[1])
today = datetime.date.today()
last_year = today.replace(year=today.year - 1, day=min(today.day, 28)).isoformat()
status, body = admin.post("/api/v1/purchases", {
    "branch_id": branch["id"], "warehouse_id": warehouse["id"], "vendor_id": vendor["id"], "purchase_date": last_year,
    "lines": [{"product_id": us1["id"], "ordered_quantity": "2", "unit_price": "100",
               "purchase_uom_id": units["BOX"], "inventory_uom_id": units["STRIP"]}]})
c.eq(status, 201, f"back-dated order saved ({message(body)})")
if status == 201:
    pl = data(admin.get(f"/api/v1/purchases/{data(body)['id']}")[1])["lines"][0]
    c.eq(float(pl["base_quantity"]), 20.0, "2 Box converts to 20 Strip on a back-dated order")

# US-7 / US-8: a set edited and deleted does not move a product made from it.
us7 = make("US7", unit_set_id=jar["id"])
c.eq(rule_of(us7["id"]), [(units["CASE"], units["JAR"], 6.0)], "US-7 rule Case = 6 Jar")
status, body = admin.put(f"{SETS}/{jar['id']}", {"conversion_factor": "12"})
c.eq(status, 200, f"set edited to 12 ({message(body)})")
us8 = make("US8", unit_set_id=jar["id"])
c.eq(rule_of(us8["id"]), [(units["CASE"], units["JAR"], 12.0)], "US-8 took 12")
c.eq(rule_of(us7["id"]), [(units["CASE"], units["JAR"], 6.0)], "US-7 keeps 6 after the edit")
status, _ = admin.delete(f"{SETS}/{jar['id']}")
c.eq(status, 204, "own set deleted")
us7b = get_product(admin, us7["id"])
c.eq((us7b.get("purchase_uom_id"), us7b.get("unit_set_id")), (units["CASE"], jar["id"]),
     "US-7 keeps Case and its set reference after delete")
c.eq(rule_of(us7["id"]), [(units["CASE"], units["JAR"], 6.0)], "US-7 rule survives the delete")
c.refused(prod(admin, tag, "US9", unit_set_id=jar["id"]), 422, "unit set is unavailable", "a deleted set is not offered")

# A unit_set_id on PUT is not accepted.
status, body = admin.put(f"{PRODUCTS}/{us1['id']}", {"code": us1["code"], "name": us1["name"],
                                                      "product_type": "STOCK_ITEM", "unit_set_id": strip10["id"]})
c.eq(status, 422, f"unit_set_id on PUT is refused ({message(body)})")

# Sales manager: reads, cannot add.
sales = client("sales")
c.eq(sales.get(SETS)[0], 200, "sales manager reads the unit sets")
c.eq(sales.post(SETS, {**jar_body, "name": f"Sales set {tag}"})[0], 403, "sales manager cannot add a set")

# The second firm sees the shared sets and not the first firm's own.
status, body = admin.post(SETS, {**jar_body, "name": f"Second view {tag}"})
other = client("platform").inside(firm_ids()["TEST02"])
status, body = other.get(SETS)
if status == 200:
    names = [r["name"] for r in data(body)]
    c.ok("Strip, box of 10" in names, "the second firm sees the shared sets")
    c.ok(f"Second view {tag}" not in names, "the second firm does not see the first firm's own set")
else:
    c.ok(False, "the second firm's read could not be driven: no account in TEST02", (status, message(body)))
c.done()
