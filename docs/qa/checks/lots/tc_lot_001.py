"""TC-LOT-001: the switch-over preview and its refusals (a firm still on Average)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_001")
platform = client("platform", "lots")
info = state("lots")["average_firm"]
admin = firm_admin(info)
if must(admin.get(f"{INV}/lot-settings"), "settings")["costing_method"] != "AVERAGE":
    # an earlier run switched this firm (one way): make another, once.
    info = new_average_firm(platform, "A")
    save_state({"average_firm": info}, "lots")
    admin = firm_admin(info)
PRE, SW = f"{INV}/lot-settings/switch-preview", f"{INV}/lot-settings/switch"
settings = must(admin.get(f"{INV}/lot-settings"), "settings")
c0.eq(settings["costing_method"], "AVERAGE", "(1) the firm shows Average")
base = must(admin.get(PRE), "preview")
c = Ctx(admin)
q = c.product("P", batch=False)
opening_stock(c, q, "10", "30")
neg = c.product("N", batch=False, allow_negative_stock=True)
try:
    pv = must(admin.get(f"{PRE}?on={today().isoformat()}"), "preview today")
    c0.eq(pv["refusals"], [], "(1) today's preview names no refusal")
    c0.eq((pv["items"] - base["items"], D(pv["quantity"]) - D(base["quantity"]), D(pv["stock_value"]) - D(base["stock_value"])),
          (1, D(10), D(300)), "(1) the preview lists the new item, its 10 units and 300.00 of stock value")
    c0.ok(pv["lots"] > base["lots"], "(1) and lots to be made", (base["lots"], pv["lots"]))
    # (2) a day after today; a day before the latest movement.
    for label, day, says in (("a day after today", today() + timedelta(days=1), "future"),
                             ("a day before the latest stock movement", today() - timedelta(days=1), "movement")):
        pv2 = must(admin.get(f"{PRE}?on={day.isoformat()}"), "preview")
        c0.ok(pv2["refusals"], f"(2) {label} is refused in the preview", pv2["refusals"])
        sw = admin.post(SW, {"on": day.isoformat()})
        c0.ok(sw[0] == 422, f"(2) {label}: the switch itself is refused", (sw[0], message(sw[1])[:200]))
    now = must(admin.get(f"{INV}/lot-settings"), "settings")
    c0.eq(now["costing_method"], "AVERAGE", "(2) nothing switched")
    # (3) an item below zero.
    sd = c.adjust(neg, "-3")
    c0.eq(sd[0], 201, f"a product that allows it goes below zero ({message(sd[1])[:120]})")
    pv3 = must(admin.get(f"{PRE}?on={today().isoformat()}"), "preview")
    c0.ok(any(neg["code"] in r or neg["name"] in r for r in pv3["refusals"]), "(3) the refusal names the item below zero",
          pv3["refusals"])
    sw = admin.post(SW, {"on": today().isoformat()}) if pv3["refusals"] else (0, "not tried: no refusal to stop it")
    c0.ok(sw[0] == 422 and (neg["code"] in message(sw[1]) or neg["name"] in message(sw[1])), "(3) the switch is refused naming it", (sw[0], message(sw[1])[:200]))
    # (4) a user without INVENTORY_MANAGE_SETTINGS.
    email = f"{info['code'].lower()}.store@fixtures.local"
    ensure_user(platform, email, "Lot avg store", info["id"], "INVENTORY_MANAGER")
    store = sign_in(email, PASSWORD, info["id"])
    c0.eq(store.get(PRE)[0], 403, "(4) the preview is 403 without the permission")
    c0.eq(store.post(SW, {"on": today().isoformat()})[0], 403, "(4) the switch is 403 without the permission")
    c0.eq(must(admin.get(f"{INV}/lot-settings"), "settings")["costing_method"], "AVERAGE", "(4) nothing changed")
    # cost value only to a holder of the cost permission (viewer of the same firm).
    viewer_email = f"{info['code'].lower()}.viewer@fixtures.local"
    ensure_user(platform, viewer_email, "Lot avg viewer", info["id"], "FIRM_MANAGER")
finally:
    # put the negative item back at zero so a re-run starts clean.
    admin.post(f"{INV}/adjustments", {"branch_id": c.branch["id"], "warehouse_id": c.warehouse["id"],
        "product_id": neg["id"], "quantity": "3", "transaction_date": today().isoformat()})
c0.done()
