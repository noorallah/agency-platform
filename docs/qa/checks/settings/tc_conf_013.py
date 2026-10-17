"""TC-CONF-013: Settings > Territories, Account structure and Party lists, then saved."""

import re

from _settings import (
    Check, data, grow, lead, message, shape, singleton, steps, suffix, total, who,
)

c = Check("tc_conf_013")
ready = who("ready_admin", "ready")
bare = who("bare_admin", "bare")
SAVED = lambda v: "Set for this firm"  # noqa: E731

# ---- Territories & routes: all four optional ---------------------------------
got = shape(c, ready, "territories", "ready")
for code, (st, _) in got.items():
    c.eq(st, "OPTIONAL", f"ready territories: {code} optional")
shape(c, bare, "territories", "bare")
status, answer = ready.get("/api/v1/sales-territories/hierarchy-levels")
levels = data(answer)["levels"] if status == 200 else []
if c.ok(bool(levels), "a hierarchy level exists", f"{status} {message(answer)[:100]}"):
    grow(c, ready, "territories", "territories", "/api/v1/sales-territories",
         {"code": f"S{suffix(5)}", "name": "Settings check area",
          "hierarchy_level_id": levels[0]["id"]})
grow(c, ready, "territories", "route-types", "/api/v1/sales-territories/route-types",
     {"code": f"S{suffix(5)}", "name": "Settings check route type"})
grow(c, ready, "territories", "transporters", "/api/v1/delivery-notes/transporters",
     {"name": f"Settings check carrier {suffix(4)}"})

# ---- Account structure -----------------------------------------------------
got = shape(c, ready, "account-structure", "ready")
c.eq(got["control-accounts"], ("DONE", "All 64 mapped"), "ready: all 64 mapped")
c.eq(got["cost-centers"][0], "OPTIONAL", "ready: cost centres optional")
c.eq(got["profit-centers"][0], "OPTIONAL", "ready: profit centres optional")

status, answer = bare.get("/api/v1/finance/control-accounts")
rows = data(answer)
unmapped = sum(1 for r in rows if not r["ledger_account_id"])
got = shape(c, bare, "account-structure", "bare")
c.eq(got["control-accounts"][0], "TODO" if unmapped else "DONE", f"bare: control accounts with {unmapped} unmapped")
c.eq(got["control-accounts"][1], f"{unmapped} of {len(rows)} unmapped" if unmapped
     else f"All {len(rows)} mapped", "bare: control accounts detail")
c.eq(len(rows), 64, "64 purposes per firm")

# Saved: remap one purpose to another account and back; the count stays 'all mapped'.
status, answer = bare.get("/api/v1/finance/ledger-accounts?page_size=50")
accounts = data(answer) if status == 200 else []
purpose = next((r for r in rows if r["ledger_account_id"] and not r["posted_lines"]), None)
other = next((a for a in accounts if purpose and a["id"] != purpose["ledger_account_id"]
              and a["account_type"] in (purpose.get("expected_types") or [a["account_type"]])), None)
if purpose and other:
    for target in (other["id"], purpose["ledger_account_id"]):
        status, answer = bare.put(f"/api/v1/finance/control-accounts/{purpose['purpose']}",
                                  {"ledger_account_id": target})
        c.ok(status == 200, "control account remap saves", f"{status} {message(answer)[:160]}")
        c.eq(steps(bare, "account-structure")["control-accounts"], ("DONE", "All 64 mapped"),
             "control accounts stay done after a remap")

# Saved: a live account requiring a centre makes the step To do until a centre exists.
acct = accounts[0] if accounts else None
if acct:
    centres = total(bare, "/api/v1/finance/cost-centers")
    status, answer = bare.call("PATCH", f"/api/v1/finance/ledger-accounts/{acct['id']}",
                               {"requires_cost_center": True})
    if c.ok(status == 200, "ledger account takes requires_cost_center", f"{status} {message(answer)[:200]}"):
        st = steps(bare, "account-structure")["cost-centers"]
        c.eq(st[0], "OPTIONAL" if centres else "TODO", f"cost centres with {centres} centres and an account needing one")
        if not centres:
            c.ok(re.search(r"None yet: \d+ accounts? needs? one|None yet: \d+ accounts? need one", st[1]) is not None,
                 "cost centres To do line", st)
        status, answer = bare.post("/api/v1/finance/cost-centers",
                                   {"code": f"S{suffix(5)}", "name": "Settings check centre"})
        c.ok(status in (200, 201), "cost centre saves", f"{status} {message(answer)[:160]}")
        after = steps(bare, "account-structure")["cost-centers"]
        c.eq(after[0], "OPTIONAL", "cost centres optional once one exists")
        c.eq(lead(after[1]), centres + 1, f"cost centres count {after[1]!r}")
        status, answer = bare.call("PATCH", f"/api/v1/finance/ledger-accounts/{acct['id']}",
                                   {"requires_cost_center": False})
        c.eq(status, 200, "requires_cost_center put back")
grow(c, ready, "account-structure", "profit-centers", "/api/v1/finance/profit-centers",
     {"code": f"S{suffix(5)}", "name": "Settings check profit centre"})

# ---- Party lists: all optional ---------------------------------------------
got = shape(c, ready, "party-lists", "ready")
for code, (st, _) in got.items():
    c.eq(st, "OPTIONAL", f"ready party-lists: {code} optional")
c.eq(got["licence-check-settings"][1], "Left as it comes", "ready: licence check default")
shape(c, bare, "party-lists", "bare")
for step, path in (("customer-groups", "/api/v1/customers/groups"),
                   ("vendor-categories", "/api/v1/vendors/categories"),
                   ("vendor-types", "/api/v1/vendors/types"),
                   ("licence-types", "/api/v1/trade-licences/types")):
    grow(c, ready, "party-lists", step, path, {"code": f"S{suffix(5)}", "name": "Settings check"})
singleton(c, bare, "/api/v1/trade-licences/settings", "party-lists", "licence-check-settings",
          flip=("shop_needs_own_licence", True), detail_for=SAVED)
c.done()
