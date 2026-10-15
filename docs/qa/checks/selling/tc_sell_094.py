"""TC-SELL-094: a return of goods never billed credits nothing, and the reports say so."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_094")
a = admin()
sc = Scene(a, stock="100")
cust = sc.customer["id"]
oa = new_order(sc, "10", approve=True)
na = new_note(sc, oa, "10", dispatch=True)
ba = bill_note(sc, na, "10")
ob = new_order(sc, "4", approve=True)
nb = new_note(sc, ob, "4", dispatch=True)
bb = bill_note(sc, nb, "3")
oc = new_order(sc, "5", approve=True)
nc = new_note(sc, oc, "5", dispatch=True)
c.eq((D(ba["grand_total"]), D(bb["grand_total"])), (D(1180), D(354)), "bills of 1,180 and 354")
owe0 = owed(a, cust)


def summary() -> dict:
    """Read the returns summary."""
    return must(a.get(f"{SR}/summary"), "summary")


def register(rid: str) -> dict:
    """Read one return's row of the register."""
    rows = rows_of(a.get(f"{SR}/reports/register?page_size=100&from_date={today().isoformat()}"))
    found = [r for r in rows if r["return_id"] == rid]
    return found[0] if found else {}


s0 = summary()
r1 = complete_return(a, must(a.post(SR, return_body(sc, ba, "2")), "r1"))
c.eq(D(data(r1[1])["credited_amount"]).quantize(D("0.01")), D("236.00"), "(1) credited 236.00")
ents = journal(a, data(r1[1])["return_number"])
c.eq(sorted(D(e["total_debit"]) for e in ents), [D("120"), D("236")], "(1) a credit entry of 236.00 and the cost entry of 120.00")
r2 = complete_return(a, must(a.post(SR, return_body(sc, nb, "2", kind="DELIVERY_NOTE")), "r2"))
g2 = data(r2[1])
c.eq(r2[0], 200, "(2) completes")
c.eq(D(g2["lines"][0]["unbilled_quantity"]), D(1), "(2) unbilled quantity 1")
c.eq(D(g2["credited_amount"]).quantize(D("0.01")), D("118.00"), "(2) credited 118.00")
r3 = must(a.post(SR, return_body(sc, nc, "5", kind="DELIVERY_NOTE")), "r3")
mid = summary()
c.eq(D(mid["pending_return_value"]) - D(s0["pending_return_value"]), D("590"), "(3) draft adds 590 to pending")
c.eq(D(mid["total_return_value"]) - D(s0["total_return_value"]), D("354"), "(3) total return value so far 354 (236 + 118)")
r3 = complete_return(a, r3)
g3 = data(r3[1])
c.eq(D(g3["credited_amount"]), D(0), "(3) credited 0.00")
c.eq(D(g3["lines"][0]["unbilled_quantity"]), D(5), "(3) unbilled 5")
c.eq([e for e in journal(a, g3["return_number"]) if not e["reference_number"].endswith("-COST")], [], "(3) no credit journal")
end = summary()
c.eq(D(end["total_return_value"]) - D(s0["total_return_value"]), D("354"), "total return value 354")
c.eq(D(end["pending_return_value"]), D(s0["pending_return_value"]), "completed leaves pending")
c.eq(owe0 - owed(a, cust), D("354"), "the customer's outstanding fell by 354 only")
reg = [register(data(r[1])["id"]) for r in (r1, r2, r3)]
c.eq([D(r.get("credited_amount", -1)).quantize(D("0.01")) for r in reg], [D("236"), D("118"), D("0")], "register credited amounts")
c.eq([D(r.get("unbilled_quantity", -1)) for r in reg], [D(0), D(1), D(5)], "register unbilled quantities")
day = today().isoformat()
gst = all_rows(a, f"{SI}/reports/gst-register?from_date={day}&to_date={day}")
mine = {r["document_number"]: r for r in gst if r["document_number"] in {data(x[1])["return_number"] for x in (r1, r2, r3)}}
c.eq(D(mine.get(data(r1[1])["return_number"], {}).get("taxable_value", 0)), D(-200), "GST register: return 1 at -200.00")
c.eq(D(mine.get(g2["return_number"], {}).get("taxable_value", 0)), D(-100), "GST register: return 2 at -100.00")
c.eq(mine.get(g2["return_number"], {}).get("against_invoice_number"), bb["invoice_number"], "return 2 names bill B under Against invoice")
c.ok(g3["return_number"] not in mine, "GST register: no row for return 3")
nc_after = must(a.get(f"{DN}/{nc['id']}"), "note C")
c.ok(bool(nc_after), "note C readable")
c.done()
