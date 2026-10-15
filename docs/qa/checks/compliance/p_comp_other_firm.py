"""Probe: another firm's returns, invoices and registrations are not readable (firm one admin against firm two)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("p_comp_other_firm")
a1 = api("admin")
one, two = firm("one"), firm("two")
f, t = month()
inv2 = two["invoices"]["B"]
c.eq(Api().get(f"{GST}/gstr1?from_date={f}&to_date={t}")[0], 401, "no token: 401")
b = a1.inside(two["firm_id"])
c.eq(b.get(f"{GST}/gstr1?from_date={f}&to_date={t}")[0], 403, "GSTR-1 under another firm's header: 403")
c.eq(b.get(f"{GST}/gstr3b?from_date={f}&to_date={t}")[0], 403, "GSTR-3B under another firm's header: 403")
c.eq(b.get(f"{EINV}/registrations")[0], 403, "e-invoice list under another firm's header: 403")
c.eq(b.get(f"{TCS}/collections")[0], 403, "TCS register under another firm's header: 403")
st, body = a1.get(f"{EINV}/invoices/{inv2}")
c.ok(st != 200 or data(body) is None, "firm two's invoice id reads no registration from firm one", (st, str(body)[:120]))
c.ok(a1.post(f"{EINV}/invoices/{inv2}/eway-bill/cancel", {"reason": "x"})[0] in (404, 422), "cannot withdraw firm two's e-way bill")
c.ok(a1.post(f"{EINV}/invoices/{inv2}/cancel", {"reason": "x"})[0] in (404, 422), "cannot cancel firm two's registration")
c.ok(a1.post(f"{SI}/{inv2}/cancel", {"reason": "x"})[0] in (404, 422), "cannot cancel firm two's invoice")
other = a1.get(f"{GST}/gstr1?from_date={f}&to_date={t}&gstin={two['gstin']}")
if other[0] == 200:
    c.eq(invoice_numbers(data(other[1])), [], "asking for firm two's GSTIN returns none of its invoices")
else:
    c.ok(other[0] in (404, 422), "firm two's GSTIN is refused", other[0])
c.eq(sorted(x["gstin"] for x in rows_of(a1.get(f"{GST}/registrations"))), [one["gstin"]], "registrations list only this firm's GSTIN")
c.done()
