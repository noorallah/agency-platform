"""TC-INCENT-013: a commission slab pays a fixed amount or a percentage."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("tc_incent_013")
a = admin()
sc = Scene(a, stock="200")
this_first, _ = month_bounds(today())
last_end = this_first - timedelta(days=1)
last_first = last_end.replace(day=1)
tenth = last_first.replace(day=10)
SLABS = [
    {"from_amount": "0", "to_amount": "1000", "fixed_amount": "50"},
    {"from_amount": "1000", "to_amount": "5000", "fixed_amount": "300"},
    {"from_amount": "5000", "percentage": "5"},
]
reached = sc.salesman(f"Reached {sc.tag}")
each = sc.salesman(f"Each {sc.tag}")
rules = {}
for name, person, mode in (("reached", reached, "WHOLE_AMOUNT"), ("each", each, "MARGINAL")):
    rules[name] = rule(a, person["id"], last_first, effective_to=last_end.isoformat(),
                       basis="INVOICED", slab_mode=mode, slabs=SLABS)
    got = rules[name]["slabs"]
    c.eq([str(s.get("fixed_amount")) if s.get("fixed_amount") is not None else None for s in got],
         ["50.00", "300.00", None], f"{name}: fixed_amount on each slab, null on a percentage slab") or None

# A slab with both, or neither, is refused.
bad = {"salesman_id": reached["id"], "effective_from": last_first.isoformat(), "basis": "INVOICED"}
c.refused(a.post(f"{COMM}/rules", {**bad, "slabs": [{"from_amount": "0", "percentage": "5", "fixed_amount": "50"}]}),
          422, "a percentage or a fixed amount, not both", "slab with both")
status, body = a.post(f"{COMM}/rules", {**bad, "slabs": [{"from_amount": "0"}]})
c.ok(status == 422, "a slab with neither is refused", f"{status} {message(body)[:150]}")

sell(sc, reached["id"], "20", "100", tenth)
sell(sc, each["id"], "20", "100", tenth)
rr = report_row(a, reached["id"], last_first, last_end)
re_ = report_row(a, each["id"], last_first, last_end)
c.eq(D(rr.get("invoiced_amount")), Decimal("2360"), "invoiced 2,360")
c.eq(D(rr.get("commission_amount")), Decimal("300.00"), "band reached pays 300 (the second slab, nothing of the first)")
c.eq(D(re_.get("commission_amount")), Decimal("350.00"), "each band pays 350 (50 + 300)")
for name, person, want in (("reached", reached, "300.00"), ("each", each, "350.00")):
    status, body = a.post(f"{COMM}/payouts/accrue", {"period_start": last_first.isoformat(),
                          "period_end": last_end.isoformat(), "salesman_id": person["id"]})
    if c.eq(status, 201, f"{name}: accrue ({message(body)[:150]})"):
        p = data(body)[0]
        c.eq(D(p["earned_amount"]), Decimal(want), f"{name}: the draft earns {want}")
        c.eq(D(p["payable_amount"]), Decimal(want), f"{name}: the draft owes {want}")

# Editing the first slab back to percent clears its amount.
edited = [{"from_amount": "0", "to_amount": "1000", "percentage": "1"}] + SLABS[1:]
status, body = a.put(f"{COMM}/rules/{rules['reached']['id']}", {"slabs": edited})
if c.eq(status, 200, f"edit the first slab to percent ({message(body)[:150]})"):
    first = data(body)["slabs"][0]
    c.eq(first.get("fixed_amount"), None, "the first slab's amount is cleared")
    c.eq(D(first.get("percentage")), Decimal("1"), "and it reads its percentage")
c.done()
