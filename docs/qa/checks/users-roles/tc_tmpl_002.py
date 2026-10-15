"""TC-TMPL-002: a firm own template, and an edit that keeps its roles."""
from _ur import *

c = Check("tc_tmpl_002"); sc = Scene()
try:
    a = sc.admin
    ids = [sc.role_id("CASHIER"), sc.role_id("BILLING_EXECUTIVE")]
    row = sc.new_template(a, ids, code=f"qa-night-{sc.tag.lower()}", name=f"Night Counter {sc.tag}")
    c.eq((row["firm_id"], row["is_system"]), (one(), False), "Origin is this firm")
    st, body = a.call("PATCH", f"{T}/{row['id']}", {"name": "Night Counter renamed"})
    c.eq(st, 200, "rename")
    again = data(a.get(f"{T}/{row['id']}")[1])
    c.eq(again["name"], "Night Counter renamed", "renamed")
    c.eq(again["role_codes"], ["BILLING_EXECUTIVE", "CASHIER"], "an edit that says nothing about the bundle keeps it")
finally:
    sc.cleanup()
c.done()
