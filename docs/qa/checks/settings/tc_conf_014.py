"""TC-CONF-014: Settings > Item lists and Locations state, then saved."""

import datetime
import re

from _settings import (
    Check, data, grow, lead, message, shape, steps, suffix, total, who,
)

c = Check("tc_conf_014")
ready = who("ready_admin", "ready")
bare = who("bare_admin", "bare")
plat = who("platform", "ready")  # store-wide lists: the platform administrator writes them

# ---- Item lists ------------------------------------------------------------
got = shape(c, ready, "item-lists", "ready")
units = total(ready, "/api/v1/uom-framework/uoms?status=ACTIVE")
c.eq(got["uoms"][0], "DONE", "ready: units done")
c.eq(lead(got["uoms"][1]), units, f"ready: units step counts the store's {units} active units")
for code in ("uom-groups", "conversion-rules", "packaging-types", "packaging-levels",
             "product-categories", "principals", "brands"):
    c.eq(got[code][0], "OPTIONAL", f"ready: {code} optional")
c.eq(lead(got["product-categories"][1]), total(ready, "/api/v1/products/categories"),
     "ready: product categories counted as the list holds them")
bare_got = shape(c, bare, "item-lists", "bare")

grow(c, plat, "item-lists", "uoms", "/api/v1/uom-framework/uoms",
     {"code": f"S{suffix(5)}", "name": "Settings check unit"})
grow(c, plat, "item-lists", "packaging-types", "/api/v1/uom-framework/packaging-types",
     {"code": f"S{suffix(5)}", "name": "Settings check packaging"})
grow(c, ready, "item-lists", "product-categories", "/api/v1/products/categories",
     {"code": f"S{suffix(5)}", "name": "Settings check category"})
principal = grow(c, ready, "item-lists", "principals", "/api/v1/products/principals",
                 {"code": f"S{suffix(5)}", "name": "Settings check company"})
if principal:
    grow(c, ready, "item-lists", "brands", "/api/v1/products/brands",
         {"name": "Settings check brand", "principal_id": principal["id"]})
status, answer = ready.get("/api/v1/uom-framework/uoms?page_size=50")
uoms = data(answer) if status == 200 else []
held_rules = lead(steps(ready, "item-lists")["conversion-rules"][1])
if c.ok(len(uoms) > held_rules + 1, "units enough to pair into a new rule"):
    grow(c, ready, "item-lists", "conversion-rules", "/api/v1/uom-framework/conversion-rules",
         {"from_uom_id": uoms[held_rules]["id"], "to_uom_id": uoms[held_rules + 1]["id"],
          "conversion_factor": "12", "effective_from": datetime.date.today().isoformat()})

# ---- Locations ---------------------------------------------------------------
got = shape(c, ready, "locations", "ready")
c.ok(re.fullmatch(r"\d+ countr(y|ies)(, \d+ states?)?(, \d+ districts?)?(, \d+ cit(y|ies))?", got["geography-masters"][1]) is not None,
     "ready: places read as counts of countries, states...", got["geography-masters"])
for code, (st, _) in got.items():
    c.eq(st, "OPTIONAL", f"ready locations: {code} optional")
bare_loc = shape(c, bare, "locations", "bare")
grow(c, ready, "locations", "branch-types", "/api/v1/branch-types", {"code": f"S{suffix(5)}", "name": "Settings check"})
grow(c, ready, "locations", "warehouse-types", "/api/v1/warehouse-types", {"code": f"S{suffix(5)}", "name": "Settings check"})

# Storage areas wait for a warehouse, then count the areas in it.
warehouses = total(bare, "/api/v1/warehouses")
st = steps(bare, "locations")["storage-areas"]
c.eq(st[1], "Needs a warehouse first" if not warehouses else st[1], f"storage areas with {warehouses} warehouses")
if warehouses:
    c.ok(st[1] != "Needs a warehouse first", "storage areas no longer ask for a warehouse", st)
status, answer = bare.get("/api/v1/branches?page_size=5")
branches = data(answer) if status == 200 else []
if not branches:  # a provisioned-only firm has no branch: the platform makes the head office
    held = __import__("common").state()
    who("platform").post(f"/api/v1/firms/{held['bare_id']}/create-default-branch", None)
    status, answer = bare.get("/api/v1/branches?page_size=5")
    branches = data(answer) if status == 200 else []
c.ok(bool(branches), "the firm has a branch to hold a warehouse", f"{status} {message(answer)[:100]}")
status, answer = bare.post("/api/v1/warehouses", {"branch_id": branches[0]["id"] if branches else None, "code": f"W{suffix(5)}", "name": f"Settings check store {suffix(4)}"})
if c.ok(status in (200, 201), "warehouse saves", f"{status} {message(answer)[:200]}"):
    wid = data(answer)["id"]
    c.eq(steps(bare, "locations")["storage-areas"][1].startswith("Needs"), False, "storage areas ask for no warehouse once one exists")
    before = steps(bare, "locations")["storage-areas"][1]
    status, answer = bare.post("/api/v1/warehouses/storage-nodes",
                               {"warehouse_id": wid, "node_type": "STORAGE_AREA",
                                "code": f"A{suffix(5)}", "name": f"Settings check area {suffix(4)}"})
    if c.ok(status in (200, 201), "storage area saves", f"{status} {message(answer)[:200]}"):
        after = steps(bare, "locations")["storage-areas"][1]
        c.eq(lead(after), lead(before) + 1, f"storage areas {before!r} -> {after!r}")
c.done()
