"""TC-CONF-011: Settings > Firm, Selling and Buying state, then saved."""

import datetime

from _settings import (
    Check, data, grow, lead, limits_flow, message, shape, singleton, steps, suffix,
    total, who,
)

c = Check("tc_conf_011")
ready = who("ready_admin", "ready")
bare = who("bare_admin", "bare")
plat = who("platform")
held = __import__("common").state()

# ---- Firm: a finished firm ------------------------------------------------
got = shape(c, ready, "firm", "ready")
c.eq(got["firm-profile"], ("OPTIONAL", "Wholesale Distribution"), "ready: profile named")
c.eq(got["financial-years"][0], "DONE", "ready: a year is open")
c.ok(got["financial-years"][1].endswith("open"), "ready: the open year is named", got["financial-years"])
c.eq(got["numbering-series"][0], "OPTIONAL", "ready: numbering optional")
c.eq(got["messaging"], ("OPTIONAL", "Off"), "ready: messaging off")
for step in ("goods-types", "custom-fields", "custom-field-rules", "approval-levels"):
    c.eq(got[step][0], "OPTIONAL", f"ready: {step} optional")

# Step 6: Financial years To do exactly while no year is open.
status, years = bare.get("/api/v1/finance/financial-years")
open_years = [y for y in data(years) if y.get("is_active", True) and not y.get("is_locked")]
got = shape(c, bare, "firm", "bare")
c.eq(got["financial-years"][0], "DONE" if open_years else "TODO",
     f"bare: financial years follow the {len(open_years)} open years")
if not open_years:
    c.eq(got["financial-years"][1], "None open: nothing can be posted", "bare: the To do line")
    c.ok(got["firm-profile"][1].startswith("Not chosen"), "bare: no profile chosen", got["firm-profile"])
    status, answer = plat.post(f"/api/v1/firms/{held['bare_id']}/open-books", {})
    if c.ok(status in (200, 201), "open-books saves", f"{status} {message(answer)[:200]}"):
        after = steps(bare, "firm")["financial-years"]
        c.eq(after[0], "DONE", "bare after open-books: financial years done")
        c.ok(after[1].endswith("open"), "bare after open-books: a year is named", after)

# Saved: records of the Firm steps, through their own endpoints.
grow(c, ready, "firm", "goods-types", "/api/v1/products/goods-types",
     {"code": f"S{suffix(5)}", "name": "Settings check goods type"})
grow(c, ready, "firm", "custom-fields", "/api/v1/business-framework/firm-custom-fields",
     {"code": f"S{suffix(5)}", "name": "Settings check field", "data_type": "TEXT"})
singleton(c, bare, "/api/v1/messaging/settings", "firm", "messaging",
          detail_for=lambda v: "On" if v.get("is_enabled") else "Off")

# ---- Selling --------------------------------------------------------------
got = shape(c, ready, "selling", "ready")
c.ok(got["credit-control"] in (("OPTIONAL", "Left as it comes: warns at 80%"), ("OPTIONAL", "Set for this firm")),
     "ready: credit control default or already set", str(got["credit-control"]))
for step in ("sales-stages", "salesmen", "price-floor", "discount-limits", "loyalty-scheme", "tcs"):
    c.eq(got[step][0], "OPTIONAL", f"ready: {step} optional")

shape(c, bare, "selling", "bare")
SAVED = lambda v: "Set for this firm"  # noqa: E731
onoff = lambda v: "On" if v.get("is_enabled") else "Off"  # noqa: E731
singleton(c, bare, "/api/v1/sales-orders/price-floor-settings", "selling", "price-floor", detail_for=SAVED)
singleton(c, bare, "/api/v1/customers/credit-settings", "selling", "credit-control",
          flip=("collector_records_receipt", True), detail_for=SAVED)
singleton(c, bare, "/api/v1/loyalty/settings", "selling", "loyalty-scheme", detail_for=onoff)
singleton(c, bare, "/api/v1/tcs/settings", "selling", "tcs", detail_for=onoff)
limits_flow(c, bare, "selling", "discount-limits", "/api/v1/sales-orders/discount-limits",
            "SALES_EXECUTIVE", "max_discount_percent")

# Step 4: Salesmen is To do when, and only when, a bill must name one and none exists.
salesmen = total(bare, "/api/v1/salesmen?is_active=true")
singleton(c, bare, "/api/v1/sales-orders/workflow-settings", "selling", "sales-stages",
          flip=("salesman_required", True), detail_for=SAVED)
status, answer = bare.put("/api/v1/sales-orders/workflow-settings", {
    "quotation_stage": True, "sales_order_stage": True, "delivery_note_stage": True,
    "salesman_required": True})
if c.eq(status, 200, f"PUT salesman_required {message(answer)[:150]}"):
    salesmen = total(bare, "/api/v1/salesmen")
    st = steps(bare, "selling")["salesmen"]
    c.eq(st[0], "DONE" if salesmen else "TODO", f"salesmen state with required and {salesmen} salesmen")
    if not salesmen:
        c.eq(st[1], "None yet: every bill must name one", "salesmen To do line")
        grow(c, bare, "selling", "salesmen", "/api/v1/salesmen", {"name": f"Settings check {suffix(4)}"})
        c.eq(steps(bare, "selling")["salesmen"][0], "DONE", "salesmen done once one exists")
    status, answer = bare.put("/api/v1/sales-orders/workflow-settings", {
        "quotation_stage": True, "sales_order_stage": True, "delivery_note_stage": True,
        "salesman_required": False})
    c.eq(status, 200, "salesman_required put back")
    c.eq(steps(bare, "selling")["salesmen"][0], "OPTIONAL", "salesmen optional again when not required")

# ---- Buying ---------------------------------------------------------------
got = shape(c, ready, "buying", "ready")
for step in ("purchase-settings", "approval-limits", "purchase-budgets"):
    c.eq(got[step][0], "OPTIONAL", f"ready: {step} optional")
shape(c, bare, "buying", "bare")
singleton(c, bare, "/api/v1/purchases/workflow-settings", "buying", "purchase-settings",
          flip=("box_and_piece_entry", True), detail_for=SAVED)
limits_flow(c, bare, "buying", "approval-limits", "/api/v1/purchases/approval-limits",
            "PURCHASE_EXECUTIVE", "max_order_amount")
month = f"{2100 + int(suffix(1), 36) % 5}-{1 + int(suffix(1), 36) % 12:02d}-01"
grow(c, ready, "buying", "purchase-budgets", "/api/v1/purchases/budgets",
     {"budget_month": month, "amount": "1000"})
c.done()
