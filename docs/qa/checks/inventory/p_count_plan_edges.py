"""Probe (round 11): a count plan at its edges (STK-6).

What a plan accepts, a plan over nothing, two sheets drawn from one plan,
a plan removed or switched off while its sheet is open, and when it next
falls due.
"""
import uuid
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("p_count_plan_edges")
w = World()
PLANS = f"{INV}/count-plans"
COUNTS = f"{INV}/counts"
wh = w.warehouse()
empty = w.warehouse("E")
p = w.product()
w.stock_in(wh["id"], p["id"], 10, 10)


def plan_body(**change: object) -> dict:
    """A plan over the stocked warehouse, with what the case changes."""
    body = {"name": f"Edge {w.tag} {suffix(3)}", "branch_id": w.branch_id, "warehouse_id": wh["id"], "frequency_days": 7}
    body.update(change)
    return body


def listed(plan_id: str) -> dict | None:
    """The plan as the list shows it."""
    st, b = w.admin.get(PLANS)
    return next((row for row in data(b) if row["id"] == plan_id), None)


# 1. what a plan accepts
for label, change in (
    ("every 0 days", {"frequency_days": 0}),
    ("every -1 days", {"frequency_days": -1}),
    ("every 367 days", {"frequency_days": 367}),
    ("a frequency that is not a number", {"frequency_days": "often"}),
    ("a name of only spaces", {"name": "   "}),
    ("an empty name", {"name": ""}),
    ("class D", {"abc_class": "D"}),
    ("an unknown warehouse", {"warehouse_id": str(uuid.uuid4())}),
    ("an unknown bin", {"storage_node_id": str(uuid.uuid4())}),
    ("a field nobody declared", {"colour": "red"}),
):
    st, b = w.admin.post(PLANS, plan_body(**change))
    c.ok(st in (404, 422), f"a plan with {label} is refused", (st, message(b)))
    if st == 201:
        w.admin.delete(f"{PLANS}/{data(b)['id']}")

# 2. a plan over a warehouse holding nothing
st, b = w.admin.post(PLANS, plan_body(warehouse_id=empty["id"]))
if c.eq(st, 201, "a plan over an empty warehouse is saved (stock may arrive)"):
    hollow = data(b)
    c.eq(hollow["is_due"], True, "never counted, so it is due")
    st, b = w.admin.get(f"{COUNTS}?search={empty['code']}")
    before = b["pagination"]["total_records"]
    answer = w.admin.post(f"{PLANS}/{hollow['id']}/sheet", {})
    c.refused(answer, 422, "covers no stock", "its sheet is refused while there is nothing to count")
    st, b = w.admin.get(f"{COUNTS}?search={empty['code']}")
    c.eq(b["pagination"]["total_records"], before, "and no sheet is left behind")
    w.admin.delete(f"{PLANS}/{hollow['id']}")

# 3. two sheets from one plan
st, b = w.admin.post(PLANS, plan_body())
c.eq(st, 201, "a plan over the stocked warehouse is saved")
plan = data(b)
st, b = w.admin.post(f"{PLANS}/{plan['id']}/sheet?count_date=not-a-date", {})
c.eq(st, 422, "a count date that is not a date is refused")
st, b = w.admin.post(f"{PLANS}/{plan['id']}/sheet?count_date=2030-01-01", {})
c.eq(st, 422, "a sheet dated outside every open period is refused, as every stock write is")
st, b = w.admin.post(f"{PLANS}/{plan['id']}/sheet", {})
c.eq(st, 201, "the first sheet is drawn")
one = data(b)
st, b = w.admin.post(f"{PLANS}/{plan['id']}/sheet", {})
second_status = st
two = data(b) if st in (200, 201) else None
if two is not None:
    # Both open: counting 9 on each must leave 9, not 8.
    for sheet in (one, two):
        st, b = w.admin.put(f"{COUNTS}/{sheet['id']}", {"lines": [{"product_id": p["id"], "counted_quantity": "9"}]})
        c.eq(st, 200, "9 counted on a sheet")
    st, b = w.admin.post(f"{COUNTS}/{one['id']}/post", {})
    c.eq(st, 200, "the first sheet posts")
    st, b = w.admin.post(f"{COUNTS}/{two['id']}/post", {})
    c.ok(st in (200, 409, 422), "the second sheet posts or is refused by name", (st, message(b)))
    c.eq(w.qty(p["id"], wh["id"]), D(9), "9 were counted twice, so 9 are held")
    if st != 200:
        w.admin.post(f"{COUNTS}/{two['id']}/cancel", {})
else:
    c.ok(second_status in (409, 422), "a second sheet while the first is open is refused by name", second_status)
    st, b = w.admin.put(f"{COUNTS}/{one['id']}", {"lines": [{"product_id": p["id"], "counted_quantity": "9"}]})
    st, b = w.admin.post(f"{COUNTS}/{one['id']}/post", {})
    c.eq(st, 200, "the one sheet posts")
    c.eq(w.qty(p["id"], wh["id"]), D(9), "9 are held")
row = listed(plan["id"])
c.eq(row and row["last_counted_on"], w.today, "the plan was counted today")
c.eq(row and row["next_due_on"], (date.fromisoformat(w.today) + timedelta(days=7)).isoformat(), "and is due in 7 days")
c.eq(row and row["is_due"], False, "so it is not due now")

# 4. a cancelled sheet is not a count
st, b = w.admin.post(PLANS, plan_body())
quiet = data(b)
st, b = w.admin.post(f"{PLANS}/{quiet['id']}/sheet", {})
c.eq(st, 201, "another plan draws its sheet")
dropped = data(b)
st, b = w.admin.post(f"{COUNTS}/{dropped['id']}/cancel", {})
c.eq(st, 200, "the sheet is cancelled")
row = listed(quiet["id"])
c.eq(row and row["last_counted_on"], None, "a cancelled sheet does not count as counted")
c.eq(row and row["is_due"], True, "the plan is still due")

# 5. switched off: not due, and it draws nothing
body = plan_body(name=quiet["name"], is_active=False)
st, b = w.admin.put(f"{PLANS}/{quiet['id']}", body)
c.eq(st, 200, "the plan is switched off")
row = listed(quiet["id"])
c.eq(row and row["is_due"], False, "a plan switched off is never due")
st, b = w.admin.post(f"{PLANS}/{quiet['id']}/sheet", {})
c.eq(st, 422, "a plan switched off draws no sheet")
if st in (200, 201):
    w.admin.post(f"{COUNTS}/{data(b)['id']}/cancel", {})

# 6. removed while its sheet is open
st, b = w.admin.post(PLANS, plan_body())
gone = data(b)
st, b = w.admin.post(f"{PLANS}/{gone['id']}/sheet", {})
c.eq(st, 201, "a third plan draws its sheet")
orphan = data(b)
st, b = w.admin.delete(f"{PLANS}/{gone['id']}")
c.eq(st, 200, "the plan is removed while its sheet is open")
c.eq(listed(gone["id"]), None, "it is no longer listed")
st, b = w.admin.post(f"{PLANS}/{gone['id']}/sheet", {})
c.eq(st, 404, "a removed plan draws nothing")
st, b = w.admin.put(f"{PLANS}/{gone['id']}", plan_body())
c.eq(st, 404, "and cannot be changed")
st, b = w.admin.delete(f"{PLANS}/{gone['id']}")
c.eq(st, 404, "or removed twice")
st, b = w.admin.get(f"{COUNTS}/{orphan['id']}")
c.eq(st, 200, "its sheet is still there")
st, b = w.admin.put(f"{COUNTS}/{orphan['id']}", {"lines": [{"product_id": p["id"], "counted_quantity": "8"}]})
c.eq(st, 200, "and still takes a count")
st, b = w.admin.post(f"{COUNTS}/{orphan['id']}/post", {})
c.eq(st, 200, "and still posts")
c.eq(w.qty(p["id"], wh["id"]), D(8), "8 are held")
st, b = w.admin.get(PLANS)
c.eq(st, 200, "the list of plans still reads")

# 7. a plan changed to a nonsense frequency keeps the old one
st, b = w.admin.put(f"{PLANS}/{plan['id']}", plan_body(name=plan["name"], frequency_days=0))
c.eq(st, 422, "changing a plan to every 0 days is refused")
row = listed(plan["id"])
c.eq(row and row["frequency_days"], 7, "it still says every 7 days")

for leftover in (plan, quiet):
    w.admin.delete(f"{PLANS}/{leftover['id']}")
c.done()
