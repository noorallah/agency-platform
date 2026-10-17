"""RCM GTA round 1: drive both bills, the journals, 3B, the GST payment and a debit note on RCM01.

Run ``setup.py`` .. ``setup6.py`` first (they make the firm, rules, item, transporters).
Prints PASS/FAIL per check. A bill is found by its supplier number if it exists.
"""

import json
import sys
from datetime import date
from decimal import Decimal as D

sys.path.insert(0, ".")
from _rcm import sign_in  # noqa: E402

st = json.load(open("state.json"))
a = sign_in()
a.firm = st["firm_id"]
BR = "38bf5aff-cdc3-457a-ab79-c5363bf726ae"
today = date.today().isoformat()
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""))


accounts = {
    x["id"]: f'{x["code"]} {x["name"]}'
    for x in a.ok("GET", "/api/v1/finance/ledger-accounts?page_size=100")
}


def find_bill(num):
    for b in a.ok("GET", f"/api/v1/purchase-invoices?search={num}&page_size=10"):
        if b["supplier_invoice_number"] == num:
            return b
    return None


def make_bill(num, vendor):
    b = find_bill(num)
    if b is None:
        body = {
            "vendor_id": vendor,
            "branch_id": BR,
            "invoice_date": today,
            "supplier_invoice_number": num,
            "supplier_invoice_date": today,
            "lines": [
                {
                    "line_number": 1,
                    "product_id": st["product"],
                    "current_invoice_quantity": "1",
                    "unit_price": "10000",
                }
            ],
        }
        b = a.ok("POST", "/api/v1/purchase-invoices", body)
    if b["status"] == "DRAFT":
        b = a.ok("POST", f"/api/v1/purchase-invoices/{b['id']}/approve", {})
    return a.ok("GET", f"/api/v1/purchase-invoices/{b['id']}")


def journal_of(source_module, source_id):
    for j in a.ok("GET", "/api/v1/finance/journal-entries?page_size=100"):
        if (
            j["source_module"] == source_module
            and j["source_id"] == source_id
            and j.get("reversal_of_id") is None
        ):
            return a.ok("GET", f"/api/v1/finance/journal-entries/{j['id']}")
    return None


def legs(j):
    return [
        (accounts[x["ledger_account_id"]], D(x["debit_amount"]), D(x["credit_amount"]))
        for x in j["lines"]
    ]


cases = {
    "LOCAL": ("LR-LOCAL-001", st["vendor_local"], {"CGST": 250, "SGST": 250}),
    "INTER": ("LR-INTER-001", st["vendor_inter"], {"IGST": 500}),
}
bills = {}
for case, (num, vendor, heads) in cases.items():
    b = make_bill(num, vendor)
    bills[case] = b
    print(f"--- {case} bill {b['invoice_number']} ({num})")
    check(f"{case} bill approved", b["status"] == "APPROVED", b["status"])
    check(
        f"{case} no tax payable to transporter (tax_total 0, grand_total = owed = 10000)",
        D(b["tax_total"]) == 0
        and D(b["grand_total"]) == 10000
        and D(b["amount_owed"]) == 10000,
        f'tax_total={b["tax_total"]} grand_total={b["grand_total"]} owed={b["amount_owed"]}',
    )
    taxes = {
        t["component_code"]: (D(t["amount"]), t["reverse_charge"])
        for ln in b["lines"]
        for t in ln["taxes"]
    }
    check(
        f"{case} self-assessed heads {heads}",
        {k: D(v) for k, v in heads.items()} == {k: v[0] for k, v in taxes.items()}
        and all(v[1] for v in taxes.values())
        and D(b["reverse_charge_tax_total"]) == 500,
        str({k: str(v[0]) for k, v in taxes.items()}),
    )
    check(
        f"{case} RSI- self-invoice number",
        (b.get("self_invoice_number") or "").startswith("RSI-"),
        str(b.get("self_invoice_number")),
    )
    j = journal_of("purchase_invoice", b["id"])
    L = legs(j)
    for x in L:
        print("   ", x[0], "Dr", x[1], "Cr", x[2])
    dr = {n: d for n, d, c in L if d}
    cr = {n: c for n, d, c in L if c}
    check(f"{case} journal balanced", j["total_debit"] == j["total_credit"], j["total_debit"])
    tenk = [n for n in dr if dr[n] == 10000]
    check(
        f"{case} Dr 10000 to one account that is not stock",
        len(tenk) == 1 and not any(w in tenk[0].lower() for w in ("inventory", "stock")),
        str(tenk),
    )
    inp = {n for n in dr if "input" in n.lower()}
    check(f"{case} Dr input tax total 500", sum(dr[n] for n in inp) == 500, str({n: str(dr[n]) for n in inp}))
    check(f"{case} Cr transporter payable 10000", any(cr[n] == 10000 for n in cr), str({n: str(v) for n, v in cr.items()}))
    rc = {n: cr[n] for n in cr if cr[n] != 10000}
    check(f"{case} Cr RCM payable total 500", sum(rc.values()) == 500, str({n: str(v) for n, v in rc.items()}))

inv = a.ok("GET", "/api/v1/inventory/transactions?page_size=50")
check("no stock movement for either freight bill", len(inv) == 0, f"{len(inv)} rows")
check("two different RSI numbers", bills["LOCAL"]["self_invoice_number"] != bills["INTER"]["self_invoice_number"])

print("--- GSTR-3B Oct 2026")
g = a.ok("GET", "/api/v1/gst-returns/gstr3b?from_date=2026-10-01&to_date=2026-10-31")
ir, ic = g["inward_reverse_charge"], g["itc_reverse_charge"]
print(ir, ic)
check("3.1(d) taxable 20000, CGST 250 SGST 250 IGST 500", (ir["taxable_value"], ir["central_tax"], ir["state_tax"], ir["integrated_tax"]) == (20000, 250, 250, 500), str(ir))
check("4(A)(3) CGST 250 SGST 250 IGST 500", (ic["central_tax"], ic["state_tax"], ic["integrated_tax"]) == (250, 250, 500), str(ic))
check("not double-counted in 4(A)(5)", g["eligible_itc"]["central_tax"] == 0 and g["eligible_itc"]["integrated_tax"] == 0, str(g["eligible_itc"]))

print("--- GST payment")
pv = a.ok("GET", "/api/v1/gst-returns/payments/preview?return_period=2026-10")
print(json.dumps({k: pv[k] for k in ("cash_total", "heads")})[:900])
check("preview: cash = 1000 (RCM, cash only)", D(pv["cash_total"]) == 1000, pv["cash_total"])
cash = next(m for m in a.ok("GET", "/api/v1/contra-vouchers/money-accounts") if m["kind"] == "CASH" and m["code"] == "1000")
s, p = a.call("POST", "/api/v1/gst-returns/payments", {"return_period": "2026-10", "payment_date": today, "money_account_id": cash["id"], "narration": "RCM GTA round 1"})
check("GST payment recorded", s < 300, str(p)[:300] if s >= 300 else "")
if s < 300:
    pj = a.ok("GET", f"/api/v1/finance/journal-entries/{p['data']['journal_entry_id']}")
    PL = legs(pj)
    for x in PL:
        print("   ", x[0], "Dr", x[1], "Cr", x[2])
    check("payment journal credits Cash 1000", sum(c for n, d, c in PL if n.endswith("Cash")) == 1000, str([(n, str(c)) for n, d, c in PL if c]))
    check("payment journal debits RCM payable 1000", sum(d for n, d, c in PL if "rcm" in n.lower() or "reverse" in n.lower()) == 1000, str([(n, str(d)) for n, d, c in PL if d]))
    st["payment_id"] = p["data"]["id"]

print("--- debit note off the LOCAL bill, taxable 4000")
lb = bills["LOCAL"]
line = lb["lines"][0]
s, n = a.call("POST", "/api/v1/debit-notes", {"purchase_invoice_id": lb["id"], "debit_note_date": today, "supplier_credit_note_number": "CN-LR-1", "supplier_credit_note_date": today, "lines": [{"purchase_invoice_line_id": line["id"], "line_number": 1, "taxable_amount": "4000"}]})
print(s, str(n)[:500])
if s < 300:
    nd = n["data"]
    check("debit note carries no tax of its own", D(str(nd.get("tax_total", "0"))) == 0, str(nd.get("tax_total")))
    s2, ap = a.call("POST", f"/api/v1/debit-notes/{nd['id']}/approve", {})
    check("debit note approved", s2 < 300, str(ap)[:300] if s2 >= 300 else "")
    if s2 < 300:
        nj = journal_of("debit_note", nd["id"])
        if nj:
            for x in legs(nj):
                print("   ", x[0], "Dr", x[1], "Cr", x[2])
        g2 = a.ok("GET", "/api/v1/gst-returns/gstr3b?from_date=2026-10-01&to_date=2026-10-31")
        ir, ic = g2["inward_reverse_charge"], g2["itc_reverse_charge"]
        check("3.1(d) now taxable 16000, CGST 150 SGST 150 IGST 500", (ir["taxable_value"], ir["central_tax"], ir["state_tax"], ir["integrated_tax"]) == (16000, 150, 150, 500), str(ir))
        check("4(A)(3) now CGST 150 SGST 150 IGST 500", (ic["central_tax"], ic["state_tax"], ic["integrated_tax"]) == (150, 150, 500), str(ic))
        pv2 = a.ok("GET", "/api/v1/gst-returns/payments/preview?return_period=2026-10")
        print("preview after note:", pv2["cash_total"])
        st["note_id"] = nd["id"]
json.dump(st, open("state.json", "w"))
print(f"\n{sum(results)}/{len(results)} passed")
