"""TC-TMPL-001: the platform templates are listed, and locked."""
from _ur import *

ELEVEN = {
    "accounts": ["ACCOUNTANT"], "counter-sales": ["BILLING_EXECUTIVE", "CASHIER"],
    "customer-support": ["CUSTOMER_SUPPORT"], "field-sales": ["SALES_EXECUTIVE"],
    "firm-administrator": ["FIRM_ADMIN"], "firm-manager": ["FIRM_MANAGER"],
    "purchase-manager": ["PURCHASE_MANAGER"], "purchasing": ["PURCHASE_EXECUTIVE"],
    "read-only": ["VIEWER"], "sales-manager": ["SALES_MANAGER"], "warehouse": ["INVENTORY_MANAGER"],
}
c = Check("tc_tmpl_001"); sc = Scene()
try:
    a = sc.admin
    rows = {r["code"]: r for r in all_rows(a, T)}
    for code, role_codes in ELEVEN.items():
        row = rows.get(code)
        c.ok(row is not None, f"template {code} is listed")
        if row:
            c.eq(row["role_codes"], role_codes, f"{code} bundles its roles")
            c.eq((row["is_system"], row["firm_id"]), (True, None), f"{code} is a platform template")
    cs = rows["counter-sales"]["id"]
    c.refused(a.call("PATCH", f"{T}/{cs}", {"name": "x"}), 422, "Platform templates cannot be edited", "edit a platform template")
    st, body = a.delete(f"{T}/{cs}")
    c.ok(st == 422, "delete a platform template is refused", (st, message(body)))
    c.eq(data(a.get(f"{T}/{cs}")[1])["name"], rows["counter-sales"]["name"], "the template is unchanged")
finally:
    sc.cleanup()
c.done()
