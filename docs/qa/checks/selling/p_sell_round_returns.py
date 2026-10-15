"""Probe (e): rounded to the rupee, a return or credit note of a bill credits what was billed: no paisa drift."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("p_sell_round_returns")
a = admin()
q2 = D("0.01")


def receivable_net(ids: list[str]) -> Decimal:
    """Net debit on the receivable account across the journals these documents raised."""
    status, body = a.get("/api/v1/finance/journal-entries?page_size=100&sort_by=created_at&sort_direction=desc")
    mine = [e for e in data(body) if e.get("source_id") in ids and not e["reference_number"].endswith("-COST")]
    billed = next((e for e in mine if e["source_id"] == ids[0]), None)
    if billed is None:
        return Decimal(-1)
    account = billed["lines"][0]["ledger_account_id"]     # the bill debits the receivable first
    return sum((D(l["debit_amount"]) - D(l["credit_amount"]) for e in mine for l in e["lines"] if l["ledger_account_id"] == account), Decimal(0))


for price, qty in (("33.35", "3"), ("12.34", "7")):
    sc = Scene(a, stock="100")
    sc.product = sc.new_product("RD", price, "100", "GST_18_LOCAL")
    cid = sc.customer["id"]
    with counter(a, round_bills_to_rupee=True):
        bill = sc.bill(qty=qty)
        billed = D(bill["grand_total"]).quantize(q2)
        c.eq(billed % 1, D(0), f"{price}x{qty}: the bill is a whole rupee ({billed})")
        c.eq(owed(a, cid), billed, f"{price}x{qty}: the customer owes what was billed")
        refs = [bill["id"]]
        credited = Decimal(0)
        for unit in range(int(qty)):          # take it back one piece at a time
            r = complete_return(a, must(a.post(SR, return_body(sc, bill, "1")), "return"))
            if r[0] != 200:
                c.ok(False, f"{price}x{qty}: return {unit + 1} completes", f"{r[0]} {message(r[1])}")
                break
            got = data(r[1])
            credited += D(got["credited_amount"]).quantize(q2)
            refs.append(got["id"])
        else:
            c.eq(credited, billed, f"{price}x{qty}: the returns, piece by piece, credit exactly what was billed")
            c.eq(owed(a, cid), D(0), f"{price}x{qty}: the customer owes nothing")
            c.eq(receivable_net(refs), D(0), f"{price}x{qty}: the ledger receivable nets to nothing")
    # a credit note on a fresh bill: the credit is what it states, with tax, and the books agree
    with counter(a, round_bills_to_rupee=True):
        bill = sc.bill(qty=qty)
        line = must(a.get(f"{SI}/{bill['id']}"), "bill")["lines"][0]
        before = owed(a, cid)
        note = must(a.post(CN, {"sales_invoice_id": bill["id"], "credit_note_date": today().isoformat(),
            "reason": "RATE_DIFFERENCE",
            "lines": [{"sales_invoice_line_id": line["id"], "line_number": 1, "taxable_amount": "10"}]}), "credit note")
        done = must(a.post(f"{CN}/{note['id']}/approve", {}), "approve")
        fell = before - owed(a, cid)
        c.eq(fell, D(done["total_amount"]).quantize(q2), f"{price}x{qty}: the receivable falls by the credit note's total")
        c.ok(fell in (D("11.80"), D("12.00")), f"{price}x{qty}: 10 + 18% is 11.80, or 12.00 if rounded", fell)
c.done()
