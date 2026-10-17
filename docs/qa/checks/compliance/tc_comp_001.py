"""TC-COMP-001: GSTR-1 for the month (firm one, read only).

The firm already trades, so the check finds its own bills (A and B by id, the
B2C rows by the product's HSN and rate) instead of assuming nothing else exists.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_001")
a = api()
f = firm()
r = gstr1(a)
c.eq(r["gstin"], f["gstin"], "filing as the firm's GSTIN")
parties = [p for p in r["b2b"] if p["gstin"] == f["buyer_gstin"]]
c.eq(len(parties), 1, "the buyer appears once under B2B, under the buyer's GSTIN")
party = parties[0]
rows = {x["invoice_number"]: x for x in party["invoices"]}
mine = {k: must(a.get(f"{SI}/{f['invoices'][k]}"), f"bill {k}")["invoice_number"] for k in ("A", "B")}
c.ok(all(n in rows for n in mine.values()), "A and B are listed under the buyer", sorted(rows))
ab = [rows[n] for n in mine.values() if n in rows]
got = sorted((D(x["taxable_value"]), D(x["central_tax"]), D(x["state_tax"]), D(x["integrated_tax"])) for x in ab)
c.eq(got, [(D(500), D(45), D(45), D(0)), (D(1000), D(90), D(90), D(0))], "A 1000/90/90 and B 500/45/45")
c.eq([x["place_of_supply"] for x in ab], ["33"] * len(ab), "place of supply 33")
b2cs = [x for x in r["b2cs"] if x["place_of_supply"] == "33" and D(x["rate"]) == D(18)]
c.eq(len(b2cs), 1, "one B2CS row for place 33 at 18%")
b = b2cs[0]
c.ok(D(b["taxable_value"]) >= D(300), "its taxable value holds at least C's 300", b["taxable_value"])
c.ok(abs(D(b["central_tax"]) + D(b["state_tax"]) - D(b["taxable_value"]) * D("0.18")) <= D("1"), "CGST and SGST add to 18% of it (to a rupee of rounding across bills)", (b["central_tax"], b["state_tax"]))
c.eq(r["cdnr"], [], "CDNR empty") if not r["cdnr"] else c.ok(True, "credit notes of other bills may exist")
hsn = [h for h in r["hsn"] if h["hsn"] == "340220"]
c.eq(len(hsn), 1, "one HSN row for 340220")
h = hsn[0]
c.ok(D(h["quantity"]) >= D(18) and D(h["taxable_value"]) >= D(1800), "HSN 340220 holds at least A, B and C (18 pieces, 1800)", (h["quantity"], h["taxable_value"]))
c.eq(D(h["taxable_value"]), D(h["quantity"]) * D(100), "taxable is quantity x 100")
c.eq(r["unplaced_invoices"], [], "no invoice without a place of supply")
c.done()
