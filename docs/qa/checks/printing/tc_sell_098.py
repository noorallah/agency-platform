"""TC-SELL-098 (print half): the firm's valid licence numbers print under its name, the buyer's under Billed to."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from datetime import timedelta

from _prt import *

c = Check("tc_sell_098")
a = admin()
sc = Scene(a, stock="50")
tag = sc.tag


def licence_type(code: str) -> dict:
    """Find or make a licence type of the firm."""
    for row in rows_of(a.get(f"{LIC}/types")):
        if row["code"] == code:
            return row
    return must(a.post(f"{LIC}/types", {"code": code, "name": code}), f"type {code}")


dgl = licence_type("DGL")
fssai = licence_type("FSSAI")
day = today()
nxt = (day + timedelta(days=365)).isoformat()
old = (day - timedelta(days=1)).isoformat()
start = (day - timedelta(days=700)).isoformat()


def own(type_row: dict, number: str, to: str, **extra: object) -> dict:
    """Record a licence."""
    return must(a.post(LIC, {"licence_type_id": type_row["id"], "licence_number": number,
                             "valid_from": start, "valid_to": to, **extra}), f"licence {number}")


firm_dgl = f"DGL-F-{tag}"
firm_fssai = f"FSSAI-F-{tag}"
lapsed = f"DGL-OLD-{tag}"
buyer_dgl = f"DGL-B-{tag}"
own(dgl, firm_dgl, nxt, holder_type="FIRM")
own(fssai, firm_fssai, nxt, holder_type="FIRM")
own(dgl, lapsed, old, holder_type="FIRM")
own(dgl, buyer_dgl, nxt, holder_type="CUSTOMER", customer_id=sc.customer["id"])
with counter(a):
    bill = sc.bill()
    other = sc.bill(customer=sc.new_customer())
text = pdf_text(printed(a, bill["id"]))
c.ok(firm_dgl in text, "step 10: the firm's valid DGL number is on the bill")
c.ok(firm_fssai in text, "step 10: the firm's FSSAI number is on the bill")
c.ok(lapsed not in text, "step 10: the DGL that ended yesterday is not on the bill")
c.ok(buyer_dgl in text, "step 10: the buyer's DGL number is on the bill")
if buyer_dgl in text and firm_dgl in text:
    billed = text.find("BILLED TO")
    c.ok(text.find(firm_dgl) < billed, "the firm's number is above Billed to", (text.find(firm_dgl), billed))
    c.ok(text.find(buyer_dgl) > billed, "the buyer's number is under Billed to", (text.find(buyer_dgl), billed))
c.ok(buyer_dgl not in pdf_text(printed(a, other["id"])), "another buyer's bill does not carry this buyer's licence")
for size in ("HALF", "A4"):
    with template(a, page_size=size, bill_layout="STANDARD"):
        t = pdf_text(printed(a, bill["id"]))
        c.ok(firm_dgl in t and buyer_dgl in t and lapsed not in t, f"{size}: the same numbers print")
with template(a, bill_layout="TRADE"):
    t = pdf_text(printed(a, bill["id"]))
    c.ok(firm_dgl in t and buyer_dgl in t and lapsed not in t, "trade layout: the same numbers print")
c.done()
