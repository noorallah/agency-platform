"""TC-INCENT-006: commission blends rates per line, and a ladder's floor is a round number."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("tc_incent_006")
a = admin()
sc = Scene(a, stock="300")
day = today()
first, last = month_bounds(day)
prod_p = second_product(sc, "P")
asha = sc.salesman(f"Asha {sc.tag}")
bala = sc.salesman(f"Bala {sc.tag}")
past = first - timedelta(days=3)
rule(a, asha["id"], past, percentage="15", product_id=prod_p["id"])
rule(a, asha["id"], past, percentage="4")
rule(
    a, bala["id"], past, slab_mode="WHOLE_AMOUNT",
    slabs=[
        {"from_amount": "0", "to_amount": "1000", "percentage": "1"},
        {"from_amount": "1000", "to_amount": "5000", "percentage": "2"},
        {"from_amount": "5000", "percentage": "3"},
    ],
)
for who_, amount in ((asha, "1000"), (bala, "100000")):
    must(a.post("/api/v1/sales-targets", {
        "salesman_id": who_["id"], "period_start": first.isoformat(), "period_end": last.isoformat(),
        "target_amount": amount, "basis": "INVOICED"}), "target")

sell(sc, asha["id"], "20", "100", day, product=prod_p, collect=True)      # 2,360 on -P
sell(sc, asha["id"], "30", "100", day, collect=True)                       # 3,540 on the rest
sell(sc, bala["id"], "40", "100", day, collect=True)                       # 4,720

ra = report_row(a, asha["id"], first, last)
rb = report_row(a, bala["id"], first, last)
# Commission is earned on net sales (COMMISSION_FRAMEWORK, 2026-09-24): the amounts
# are on the net bases 5,000 and 4,000, not the tax-inclusive 5,900 and 4,720.
c.eq(D(ra.get("collected_amount")), Decimal("5900.00"), "Asha collected")
c.eq(D(ra.get("commission_amount")), Decimal("420.00"), "Asha commission (15% of 2,000 on -P plus 4% of 3,000, net of tax)")
c.eq(ra.get("target_met"), True, "Asha target Met")
c.eq(D(rb.get("collected_amount")), Decimal("4720.00"), "Bala collected")
c.eq(D(rb.get("commission_amount")), Decimal("80.00"), "Bala commission (exactly 2.00% of 4,000 net, the 1,000-5,000 band)")
c.eq(rb.get("target_met"), False, "Bala target Missed")

ach = must(a.get(f"/api/v1/sales-targets/achievement?from_date={first}&to_date={last}&salesman_id={bala['id']}"), "achievement")
ach = ach if isinstance(ach, list) else ach.get("rows", [])
if c.ok(bool(ach), "Bala has an achievement row"):
    c.eq(D(ach[0]["target_amount"]), Decimal("100000"), "Bala target 100,000")
    c.eq(D(ach[0]["achieved_amount"]), Decimal("4720"), "Bala invoiced 4,720")
    c.eq(D(ach[0]["achieved_percent"]), Decimal("4.72"), "Bala 4.72%")
    c.eq(D(ach[0]["shortfall_amount"]), Decimal("95280"), "Bala 95,280 short")
c.done()
