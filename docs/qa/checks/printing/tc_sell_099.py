"""TC-SELL-099: a short bill on half a page, a long one on a full page, a customer's own paper."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("tc_sell_099")
a = admin()
sc = Scene(a, stock="200")
cust_b = sc.new_customer()
cust_c = sc.new_customer()
with counter(a):
    with template(a, page_size="HALF"):
        short_a = sc.bill()
        long_a = sc.bill(lines=60)
        raw = printed(a, short_a["id"])
        c.eq(kinds(raw), ["HALF"] * 3, "step 2: a short bill is three half pages (three copies)")
        t = pdf_text(raw)
        for word in ("Product Details", "Batch", "Customer signature", "Net payable"):
            c.ok(word.lower() in t.lower(), f"step 2: half page carries {word}")
        c.ok("GST" in t, "step 2: half page carries a GST summary")
        long_raw = printed(a, long_a["id"])
        long_kinds = kinds(long_raw)
        c.ok(set(long_kinds) == {"A4"} and len(long_kinds) > 3, "step 3: sixty lines print on full A4 pages, more than one per copy", long_kinds)
        c.ok("HSN / SAC" in pdf_text(long_raw), "step 3: the full page has the HSN summary")
        sc.set_paper(cust_b, "A4")
        bill_b = sc.bill(customer=cust_b)
        b_kinds = kinds(printed(a, bill_b["id"]))
        c.eq(set(b_kinds), {"A4"}, "step 4: customer B on A4 prints full pages on a half-page firm")
        status, run = post_raw(a, f"{SI}/bulk-print", {"invoice_ids": [short_a["id"], long_a["id"], bill_b["id"]]})
        c.eq(status, 200, "step 5: bulk print answers")
        c.eq(kinds(run), kinds(raw) + long_kinds + b_kinds, "step 5: one file, each bill on its own paper, in the order of the list")
        sc.set_paper(cust_c, "HALF")
        bill_c = sc.bill(customer=cust_c)
        c.eq(set(kinds(printed(a, bill_c["id"]))), {"HALF"}, "customer C on half prints half on a half-page firm")
        sc.set_paper(cust_c, None)
        c.eq(set(kinds(printed(a, bill_c["id"]))), {"HALF"}, "C back on the firm's setting: half")
    with template(a, page_size="A4"):
        c.eq(set(kinds(printed(a, short_a["id"]))), {"A4"}, "step 6: firm back on A4, the short bill is full pages")
        c.eq(set(kinds(printed(a, bill_c["id"]))), {"A4"}, "step 8: on an A4 firm, customer C on the firm's setting is full pages")
        sc.set_paper(cust_c, "HALF")
        c.eq(set(kinds(printed(a, bill_c["id"]))), {"A4"}, "step 7: an A4 firm does not read the customer's half-page paper")
        sc.set_paper(cust_c, None)
c.done()
