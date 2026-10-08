"""TC-MAST-030: copying a product keeps its pack size."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("tc_mast_030")
tag = suffix()
admin = client("admin")
units = uom_ids(admin)
med = ensure_use(admin, "MEDICINE")
tablets = cat(admin, tag, "TABLETS", goods_type_id=med["id"])
strip10 = next(r for r in data(admin.get(SETS)[1]) if r["firm_id"] is None and r["name"] == "Strip, box of 10")


def rule_of(product_id):
    rows = data(admin.get(f"/api/v1/uom-framework/conversion-rules?product_id={product_id}&page_size=50")[1])
    return [(r["from_uom_id"], r["to_uom_id"], float(r["conversion_factor"])) for r in rows]


def make(name, **kw):
    status, body = prod(admin, tag, name, **kw)
    c.eq(status, 201, f"{name} created ({message(body)})")
    return get_product(admin, data(body)["id"]) if status == 201 else {}


def copy(src):
    status, body = admin.post(f"{PRODUCTS}/{src['id']}/duplicate")
    c.eq(status, 201, f"copy of {src['code']} ({message(body)})")
    return get_product(admin, data(body)["id"]) if status == 201 else {}


UNITS = ("base_uom_id", "inventory_uom_id", "purchase_uom_id", "sales_uom_id")
cp_set = make("CP-SET", category_id=tablets["id"], unit_set_id=strip10["id"], unit_conversion_factor="12")
c.eq(rule_of(cp_set["id"]), [(units["BOX"], units["STRIP"], 12.0)], "source CP-SET has its own rule of 12")
cp_hand = make("CP-HAND", category_id=tablets["id"], base_uom_id=units["PIECE"], inventory_uom_id=units["PIECE"],
               purchase_uom_id=units["BOX"], sales_uom_id=units["PIECE"], unit_conversion_factor="6")
cp_plain = make("CP-PLAIN", category_id=tablets["id"], base_uom_id=units["PIECE"], inventory_uom_id=units["PIECE"],
                purchase_uom_id=units["PIECE"], sales_uom_id=units["PIECE"])

c2 = copy(cp_set)
if c2:
    c.eq(c2.get("unit_set_id"), strip10["id"], "CP-SET copy still shows its unit set")
    c.eq(rule_of(c2["id"]), [(units["BOX"], units["STRIP"], 12.0)], "CP-SET copy has the source's 12, not the set's 10")
    c.eq({k: c2.get(k) for k in UNITS}, {k: cp_set.get(k) for k in UNITS}, "CP-SET copy has the source's units")
h2 = copy(cp_hand)
if h2:
    c.eq(h2.get("unit_set_id"), None, "CP-HAND copy has no unit set")
    c.eq({k: h2.get(k) for k in UNITS}, {k: cp_hand.get(k) for k in UNITS}, "CP-HAND copy has the source's units")
    c.eq(rule_of(h2["id"]), [(units["BOX"], units["PIECE"], 6.0)], "CP-HAND copy has the source's rule")
p2 = copy(cp_plain)
if p2:
    c.eq(rule_of(p2["id"]), [], "a source with no rule gives a copy with none")

# A set that is no longer offered: the copy keeps the units and the rule, not the set.
own_name = f"Own strip {tag}"
status, body = admin.post(SETS, {"name": own_name, "base_uom_id": units["STRIP"], "inventory_uom_id": units["STRIP"],
                                 "purchase_uom_id": units["BOX"], "sales_uom_id": units["STRIP"],
                                 "conversion_factor": "10"})
c.eq(status, 201, f"own set made ({message(body)})")
own = data(body)
src = make("CP-OWN", category_id=tablets["id"], unit_set_id=own["id"])
status, body = admin.put(f"{SETS}/{own['id']}", {"is_active": False})
c.eq(status, 200, f"set deactivated ({message(body)})")
c3 = copy(src)
if c3:
    c.eq(c3.get("unit_set_id"), None, "copy drops the set that is no longer offered")
    c.eq({k: c3.get(k) for k in UNITS}, {k: src.get(k) for k in UNITS}, "copy keeps the units")
    c.eq(rule_of(c3["id"]), [(units["BOX"], units["STRIP"], 10.0)], "copy keeps the conversion")

# The sources are unchanged.
again = get_product(admin, cp_set["id"])
c.eq((again.get("version"), again.get("unit_set_id")), (cp_set.get("version"), strip10["id"]), "the source product is unchanged")
c.eq(rule_of(cp_set["id"]), [(units["BOX"], units["STRIP"], 12.0)], "the source rule is unchanged")

# A user without PRODUCT_CREATE.
before = data(admin.get(f"{PRODUCTS}?search={tag}&page_size=100")[1])
sales = client("sales")
c.eq(sales.post(f"{PRODUCTS}/{cp_set['id']}/duplicate")[0], 403, "sales manager cannot duplicate")
after = data(admin.get(f"{PRODUCTS}?search={tag}&page_size=100")[1])
c.eq(len(after), len(before), "no product was written by the refused copy")
c.done()
