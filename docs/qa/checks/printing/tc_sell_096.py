"""TC-SELL-096: print several bills (and challans) as one PDF."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("tc_sell_096")
a = admin()
v = admin("viewer")
sc = Scene(a, stock="200")
with counter(a):
    bills = [sc.bill(qty=str(n)) for n in (1, 2, 3)]
ids = [b["id"] for b in bills]
singles = [printed(a, i) for i in ids]
status, run = post_raw(a, f"{SI}/bulk-print", {"invoice_ids": ids})
c.eq(status, 200, "(a) the run prints")
c.eq(run[:4], b"%PDF", "(a) it is a PDF")
c.eq(len(kinds(run)), 9, "(a) three bills of three copies are nine pages")
text = pdf_text(run)
spots = [text.find(b["invoice_number"]) for b in bills]
c.ok(all(s >= 0 for s in spots) and spots == sorted(spots), "(a) the bills are in the order of the list", spots)
c.eq(sum(len(kinds(s)) for s in singles), len(kinds(run)), "(a) the same pages as three printed singly")
for label in ("ORIGINAL FOR RECIPIENT", "DUPLICATE FOR TRANSPORTER", "TRIPLICATE FOR SUPPLIER"):
    c.eq(text.count(label), 3, f"(a) {label} three times")
status, rev = post_raw(a, f"{SI}/bulk-print", {"invoice_ids": ids[::-1]})
t = pdf_text(rev)
spots = [t.find(b["invoice_number"]) for b in bills[::-1]]
c.ok(spots[0] >= 0 and spots == sorted(spots), "reversed ids print in the reversed order", spots)
status, one = post_raw(a, f"{SI}/bulk-print", {"invoice_ids": [ids[0]]})
c.eq(status, 200, "(e) one id is accepted by the server")
status, dup = post_raw(a, f"{SI}/bulk-print", {"invoice_ids": [ids[0], ids[0]]})
c.eq(len(kinds(dup)), 3, "an id named twice prints once")
status, vrun = post_raw(v, f"{SI}/bulk-print", {"invoice_ids": ids})
c.eq(status, 200, "(c) a Viewer prints the run")
c.eq(len(kinds(vrun)), 9, "(c) the same nine pages")
with template(a, page_size="THERMAL80"):
    status, raw = post_raw(a, f"{SI}/bulk-print", {"invoice_ids": ids})
    c.eq(status, 422, "(d) a thermal roll is refused")
    c.ok("thermal roll" in refusal_of(raw) and "one at a time" in refusal_of(raw), "(d) the words name the roll and one at a time", refusal_of(raw))
# delivery challans
order, bill = sc.staged_bill("1")
notes = [n for n in all_rows(a, DN) if n.get("sales_order_id") == order["id"]]
c.ok(len(notes) >= 1, "the staged sale made a delivery note")
if notes:
    status, raw = post_raw(a, f"{DN}/bulk-print", {"note_ids": [notes[0]["id"]]})
    c.eq((status, raw[:4]), (200, b"%PDF"), "(b) a challan run prints")
    status, raw = post_raw(a, f"{DN}/bulk-print", {"note_ids": [notes[0]["id"], "00000000-0000-4000-8000-000000000000"]})
    c.eq(status, 404, "(b) a challan id that is not the firm's is refused")
c.done()
