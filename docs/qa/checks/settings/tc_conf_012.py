"""TC-CONF-012: Settings > Stock, Business profile and Pricing state, then saved."""

import datetime
import re

from _settings import (
    Check, count_of, data, grow, lead, limits_flow, message, shape, singleton, steps,
    suffix, who,
)

c = Check("tc_conf_012")
ready = who("ready_admin", "ready")
bare = who("bare_admin", "bare")
plat = who("platform")
held = __import__("common").state()
SAVED = lambda v: "Set for this firm"  # noqa: E731

# ---- Stock: no step is To do, row 1 says 8 built in -----------------------
got = shape(c, ready, "stock", "ready")
c.ok(got["adjustment-reasons"][1].startswith("8 built in"), "ready: 8 built in", got["adjustment-reasons"])
c.eq(got["costing-method"], ("OPTIONAL", "Average"), "ready: costing method Average")
for code, (st, _) in got.items():
    c.eq(st, "OPTIONAL", f"ready stock: {code} optional")
shape(c, bare, "stock", "bare")
grow(c, ready, "stock", "adjustment-reasons", "/api/v1/inventory/adjustment-reasons",
     {"code": f"S{suffix(5)}", "name": "Settings check reason"}, word="own")
limits_flow(c, bare, "stock", "adjustment-limits", "/api/v1/inventory/adjustment-limits",
            "INVENTORY_MANAGER", "max_value")
singleton(c, bare, "/api/v1/batch-serial/sale-settings", "stock", "batch-rules",
          flip=("near_expiry_below_floor", False), detail_for=SAVED)
# Costing method has no saved value of its own: the one setting (billing without
# stock) is refused while the firm is on Average, so the screen is read, not saved.
status, answer = bare.get("/api/v1/inventory/lot-settings")
c.eq(data(answer).get("costing_method") if status == 200 else status, "AVERAGE", "bare: costing method read")
c.refused(bare.put("/api/v1/inventory/lot-settings", {"allow_billing_without_stock": False}),
          422, "applies only to a firm that costs its stock by lot", "lot settings on Average")
c.eq(steps(bare, "stock")["costing-method"], ("OPTIONAL", "Average"), "costing method stays Average")

# ---- Business profile: all optional ----------------------------------------
got = shape(c, ready, "business-profile", "ready")
c.eq(got["profile-assignment"], ("OPTIONAL", "Wholesale Distribution"), "ready: profile named")
for code in ("feature-management", "module-configuration"):
    c.ok(re.fullmatch(r"\d+ of \d+ (features|modules) on", got[code][1]) is not None,
         f"ready: {code} reads 'N of M ... on'", got[code])
    c.eq(got[code][0], "OPTIONAL", f"ready: {code} optional")
for code, (st, _) in got.items():
    c.eq(st, "OPTIONAL", f"ready business-profile: {code} optional")
before_bare = shape(c, bare, "business-profile", "bare")

# Saved: a field of the firm's own, a rule on it, a unit set.
field = grow(c, ready, "business-profile", "attribute-definitions",
             "/api/v1/business-framework/firm-custom-fields",
             {"code": f"S{suffix(5)}", "name": "Settings check field", "data_type": "TEXT"}, word="own")
if field:
    grow(c, ready, "business-profile", "mandatory-attributes",
         "/api/v1/business-framework/firm-custom-field-rules",
         {"attribute_definition_id": field["id"], "is_mandatory": True, "category_code": "FXAMB"}, word="own")
status, answer = ready.get("/api/v1/uom-framework/uoms?page_size=5")
uoms = data(answer) if status == 200 else []
if c.ok(bool(uoms), "a unit exists to base a set on", f"{status} {message(answer)[:100]}"):
    grow(c, ready, "business-profile", "unit-sets", "/api/v1/uom-framework/unit-sets",
         {"name": f"Settings check set {suffix(4)}", "base_uom_id": uoms[0]["id"]}, word="own")

# Saved: assigning a profile to the bare firm moves step 1 from 'Not chosen' to its name.
status, answer = plat.get(f"/api/v1/business-framework/firms/{held['bare_id']}/profiles")
profiles = data(answer) if status == 200 else []
if before_bare["profile-assignment"][1].startswith("Not chosen") and c.ok(bool(profiles), "profiles listed"):
    pick = next((p for p in profiles if p["code"] == "AGENCY"), profiles[0])
    status, answer = plat.put(
        f"/api/v1/business-framework/firms/{held['bare_id']}/profile-assignment",
        {"business_profile_id": pick["id"], "is_active": True})
    if c.ok(status in (200, 201), "profile assignment saves", f"{status} {message(answer)[:200]}"):
        after = steps(bare, "business-profile")
        c.eq(after["profile-assignment"][1], pick["name"], "bare after assignment: profile named")
        c.eq(steps(bare, "firm")["firm-profile"][1], pick["name"], "Firm step 1 names it too")

# ---- Pricing: nothing is To do ----------------------------------------------
got = shape(c, ready, "pricing", "ready")
for code, (st, _) in got.items():
    c.eq(st, "OPTIONAL", f"ready pricing: {code} optional")
shape(c, bare, "pricing", "bare")
grow(c, ready, "pricing", "price-lists", "/api/v1/price-lists",
     {"code": f"S{suffix(5)}", "name": "Settings check list",
      "effective_from": datetime.date.today().isoformat()})
grow(c, ready, "pricing", "price-levels", "/api/v1/price-levels",
     {"code": f"S{suffix(5)}", "name": "Settings check level"})
singleton(c, bare, "/api/v1/loyalty/settings", "pricing", "loyalty",
          detail_for=lambda v: "None yet" if v.get("is_enabled") else "Scheme off: none yet")
c.done()
