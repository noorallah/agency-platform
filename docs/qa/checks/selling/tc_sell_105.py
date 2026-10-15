"""TC-SELL-105: round every bill to the nearest rupee."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_105")
a = admin()
sc = Scene(a, stock="100")
item = sc.new_product("RR", "33.33", "100", "GST_18_LOCAL")
sc.product = item
cid = sc.customer["id"]
q2 = D("0.01")

with counter(a):
    one = sc.bill(qty="3")
    c.eq(D(one["grand_total"]).quantize(q2), D("117.99"), "step 1: 117.99 with its paise")
    c.eq(D(one["round_off"]), D(0), "step 1: no Round off")
    before = owed(a, cid)
    c.eq(before, D("117.99"), "step 1: owes 117.99")
with counter(a, round_bills_to_rupee=True):
    status, answer = a.post(f"{SI}/preview", sc.bill_body("3"))
    pre = data(answer)["invoice"] if status == 200 else None
    c.ok(pre is not None, "step 3: the preview answers", f"{status} {message(answer)}")
    if pre:
        c.eq((D(pre["round_off"]).quantize(q2), D(pre["grand_total"]).quantize(q2)), (D("0.01"), D("118.00")), "step 3: the preview shows Round off 0.01 and 118.00")
    bill = sc.bill(qty="3")
    c.eq((D(bill["round_off"]).quantize(q2), D(bill["grand_total"]).quantize(q2)), (D("0.01"), D("118.00")), "step 3: the saved bill reads 118.00 with Round off 0.01")
    je = journal(a, bill["invoice_number"])
    c.eq([D(e["total_debit"]) for e in je], [D("118.00")], "step 4: Trade Receivables debited 118.00")
    credits = sorted(D(l["credit_amount"]) for e in je for l in e["lines"] if D(l["credit_amount"]))
    c.ok(D("0.01") in credits, "step 4: Rounding credited 0.01", credits)
    c.eq(sum(credits, Decimal(0)), D("118.00"), "step 4: the credits add to 118.00")
    status, raw = a.raw(f"{SI}/{bill['id']}/print")
    text = pdf_text(raw)
    c.ok("round off" in text.lower() and "118.00" in text, "step 5: the print has a Round off line and 118.00")
    mid = owed(a, cid)
    c.eq(mid - before, D("118.00"), "the customer owes 118.00 more")
    got = must(a.post(SR, return_body(sc, bill, "3")), "return of everything")
    done = complete_return(a, got)
    c.eq(done[0], 200, f"step 6: the return completes ({message(done[1])})")
    r = data(done[1])
    c.eq((D(r["round_off"]).quantize(q2), D(r["credited_amount"]).quantize(q2)), (D("0.01"), D("118.00")), "step 6: it credits 118.00 with Round off 0.01")
    c.eq(owed(a, cid), before, "step 7: the bill and its return leave nothing owed for them")
    rid = [e for e in journal(a, r["return_number"]) if not e["reference_number"].endswith("-COST")]
    c.eq([D(e["total_credit"]) for e in rid], [D("118.00")], "step 7: the return's journal credits the customer 118.00")
with counter(a):
    back = sc.bill(qty="3")
    c.eq(D(back["grand_total"]).quantize(q2), D("117.99"), "step 8: off again, 117.99")
c.done()
