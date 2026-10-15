"""TC-TMPL-008: after a template, somebody is an ordinary user."""
from _ur import *

c = Check("tc_tmpl_008"); sc = Scene()
try:
    a = sc.admin
    tt = sc.user("twotier")
    set_global_roles(sc, tt["id"], ["VIEWER", "CUSTOMER_SUPPORT"])
    set_firm_roles(sc, tt["id"], one(), ["ACCOUNTANT", "INVENTORY_MANAGER"])
    set_firm_roles(sc, tt["id"], one(), ["INVENTORY_MANAGER", "CASHIER"], by=a)
    c.eq(codes(sc, roles_of(a, tt["id"], one())), ["CASHIER", "INVENTORY_MANAGER"], "ACCOUNTANT removed, CASHIER added")
    c.eq(codes(sc, global_roles_of(a, tt["id"])), ["CUSTOMER_SUPPORT", "VIEWER"], "Also applies here shows the global tier")
    # a firm admin cannot write the global tier through the other route
    st, body = a.put(f"{U}/{tt['id']}/roles", {"ids": []})
    c.eq(codes(sc, global_roles_of(sc.platform, tt["id"])), ["CUSTOMER_SUPPORT", "VIEWER"], f"the global tier survives a firm admin role write ({st})")
finally:
    sc.cleanup()
c.done()
