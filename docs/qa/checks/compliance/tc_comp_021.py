"""TC-COMP-021: GST checks before filing (firm two, own bills). HSN, IRN and credit-note findings are skipped."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_021")
o = Own("two")
a = o.api
bad = o.bill(o.customer(o.gstin(valid=False)))
good = o.bill(o.customer(o.gstin()))
f, t = month()
r = data(a.get(f"{GST}/checks?from_date={f}&to_date={t}")[1])
rows = {(x["check"], x["document_number"]): x for x in r["rows"]}
x = rows.get(("GSTIN_INVALID", bad["invoice_number"]))
c.ok(x is not None, "an invoice to a buyer whose GSTIN fails its check character is flagged GSTIN_INVALID", list(rows)[:6])
if x:
    c.eq((x["severity"], x["document_type"]), ("ERROR", "SALES_INVOICE"), "as an error on a sales invoice")
    c.ok(x["party_name"] and x["document_date"], "naming party and date")
c.ok(("GSTIN_INVALID", good["invoice_number"]) not in rows, "an invoice to a buyer with a correct GSTIN is not flagged")
c.eq(r["counts"].get("GSTIN_INVALID"), sum(1 for k in rows if k[0] == "GSTIN_INVALID"), "counts agree with the rows")
c.ok(not [k for k in rows if k[0] == "HSN_MISSING"], "the product has an HSN, so no HSN_MISSING")
c.eq(r["required_hsn_digits"], 4, "four HSN digits while the firm does not e-invoice")
c.ok(bad["invoice_number"] in set(invoice_numbers(gstr1(a))), "the flagged invoice is one GSTR-1 declares")
c.done()
