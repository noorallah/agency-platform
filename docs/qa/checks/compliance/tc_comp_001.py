"""TC-COMP-001: GSTR-1 for the month (firm one, read only)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_001")
a = api()
f = firm()
r = gstr1(a)
c.eq(r["gstin"], f["gstin"], "filing as the firm's GSTIN")
c.eq(len(r["b2b"]), 1, "one buyer under B2B")
party = r["b2b"][0]
c.eq(party["gstin"], f["buyer_gstin"], "under the buyer's GSTIN")
rows = {x["invoice_number"]: x for x in party["invoices"]}
c.eq(len(rows), 2, "two B2B invoices (A and B)")
got = sorted((D(x["taxable_value"]), D(x["central_tax"]), D(x["state_tax"]), D(x["integrated_tax"])) for x in rows.values())
c.eq(got, [(D(500), D(45), D(45), D(0)), (D(1000), D(90), D(90), D(0))], "A 1000/90/90 and B 500/45/45")
c.eq([x["place_of_supply"] for x in rows.values()], ["33", "33"], "place of supply 33")
c.eq(len(r["b2cs"]), 1, "one B2CS row")
b = r["b2cs"][0]
c.eq((b["place_of_supply"], D(b["rate"]), D(b["taxable_value"]), D(b["central_tax"]), D(b["state_tax"])), ("33", D(18), D(300), D(27), D(27)), "B2CS 33 / 18% / 300 / 27 / 27")
c.eq(r["cdnr"], [], "CDNR empty")
c.eq(len(r["hsn"]), 1, "one HSN row")
h = r["hsn"][0]
c.eq((h["hsn"], D(h["quantity"]), D(h["taxable_value"])), ("340220", D(18), D(1800)), "HSN 340220 qty 18 taxable 1800")
c.eq(r["unplaced_invoices"], [], "no invoice without a place of supply")
c.done()
