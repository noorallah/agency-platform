"""TC-SELL-113: Standard against Trade layout on a full page, and the Preview."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("tc_sell_113")
a = admin()
sc = Scene(a, stock="50")
held = must(a.get(PRINT_TEMPLATE), "template")
base = {k: v for k, v in held.items() if k not in ("id", "document_type", "is_customised")}
c.eq(held["bill_layout"], "STANDARD", "step 1: Bill layout reads Standard")
with counter(a):
    bill = sc.bill()
    terms = f"Terms check {sc.tag}"
    status, raw = post_raw(a, f"{PRINT_TEMPLATE}/preview", {**base, "bill_layout": "TRADE", "terms": terms})
    c.eq((status, raw[:4]), (200, b"%PDF"), "step 2: the preview draws a PDF")
    t = pdf_text(raw)
    c.ok("SAMPLE - NOT A TAX INVOICE" in t, "step 2: headed SAMPLE - NOT A TAX INVOICE")
    c.ok(terms in t, "step 2: carries the line of terms just typed")
    for col in ("M.R.P", "D.Price", "P.T.R", "GST%", "Net Value", "Batch"):
        c.ok(col in t, f"step 2: the sample has the {col} column")
    c.eq(data(a.get(PRINT_TEMPLATE)[1])["bill_layout"], "STANDARD", "step 3: a preview saved nothing")
    std = pdf_text(printed(a, bill["id"]))
    c.ok("P.T.R" not in std and "Net Payable" not in std, "step 3: the bill still prints in the standard layout")
    with template(a, bill_layout="TRADE"):
        raw = printed(a, bill["id"])
        t = pdf_text(raw)
        c.ok("Net Payable" in t, "step 4: the boxed layout names Net Payable")
        c.ok("D.Price" in t and "M.R.P" in t, "step 4: it has D.Price and M.R.P")
        c.ok("118.00" in t, "step 4: Net Payable is the bill's 118.00")
        c.ok("118.000" in t, "step 4: D.Price is the rate with its GST (118.000)")
        c.ok("CGST" in t and "SGST" in t, "step 4: CGST and SGST are in the totals")
        c.ok(set(kinds(raw)) == {"A4"}, "step 4: full A4 pages", kinds(raw))
        with template(a, bill_layout="TRADE", page_size="HALF"):
            t = pdf_text(printed(a, bill["id"]))
            c.ok("D.Price" not in t, "step 5: on half pages the saved Trade layout is not used")
            c.eq(set(kinds(printed(a, bill["id"]))), {"HALF"}, "step 5: half pages")
    c.ok("Net Payable" not in pdf_text(printed(a, bill["id"])), "put back: Standard again")
# step 6: another document cannot take the layout
status, body = a.put("/api/v1/document-framework/print-templates/DELIVERY_NOTE", {**base, "bill_layout": "TRADE"})
c.eq(status, 422, "a delivery note cannot be saved as TRADE")
c.done()
