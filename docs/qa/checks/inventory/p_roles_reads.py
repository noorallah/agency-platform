"""Probe: every inventory read endpoint by manager, store, sales and read-only accounts (403 exactly when the code is not held)."""
from _inv import *
from _roles import role_codes

c = Check("p_roles_reads")
ROLE = {"manager": "FIRM_MANAGER", "store": "INVENTORY_MANAGER", "sales": "SALES_MANAGER", "viewer": "VIEWER"}
codes = role_codes(client("platform"))
who = {name: client(name) for name in ROLE}
V = ("INVENTORY_VIEW",)
reads = [
    ("/api/v1/inventory", V), ("/api/v1/inventory/summary", V), ("/api/v1/inventory/summary/by-product", V),
    ("/api/v1/inventory/summary/by-warehouse", V), ("/api/v1/inventory/summary/by-branch", V), ("/api/v1/inventory/summary/by-firm", V),
    ("/api/v1/inventory/ledger", ("INVENTORY_LEDGER_VIEW",)), ("/api/v1/inventory/transactions", ("INVENTORY_TRANSACTION_VIEW",)),
    ("/api/v1/inventory/opening-stock", V), ("/api/v1/inventory/opening-stock/import-template", ("INVENTORY_IMPORT",)),
    ("/api/v1/inventory/adjustment-limits", V), ("/api/v1/inventory/adjustment-reasons", ("INVENTORY_VIEW", "INVENTORY_ADJUST", "INVENTORY_MANAGE_REASONS")),
    ("/api/v1/inventory/adjustment-requests", ("INVENTORY_ADJUST",)), ("/api/v1/inventory/repacks", V),
    ("/api/v1/inventory/stock-transfers", V), ("/api/v1/inventory/counts", V), ("/api/v1/inventory/count-plans", V),
    ("/api/v1/inventory/abc-classes", V), ("/api/v1/inventory/export", ("INVENTORY_EXPORT",)),
    ("/api/v1/inventory/alerts", ("INVENTORY_VIEW", "REPORT_VIEW")), ("/api/v1/inventory/reports/stock-valuation", ("INVENTORY_VIEW", "REPORT_VIEW")),
    ("/api/v1/inventory/reports/stock-ageing", ("INVENTORY_VIEW", "REPORT_VIEW")), ("/api/v1/inventory/reports/slow-moving", ("INVENTORY_VIEW", "REPORT_VIEW")),
    ("/api/v1/inventory/reports/dead-stock", ("INVENTORY_VIEW", "REPORT_VIEW")), ("/api/v1/inventory/reports/free-goods", ("INVENTORY_VIEW", "REPORT_VIEW")),
    ("/api/v1/inventory/reports/stock-statement?from_date=2026-04-01&to_date=2026-10-08", ("INVENTORY_VIEW", "REPORT_VIEW")),
    ("/api/v1/batch-serial/batches", ("BATCH_VIEW",)), ("/api/v1/batch-serial/batches/expiry-dashboard", ("BATCH_VIEW",)),
    ("/api/v1/batch-serial/batches/returns-due", ("BATCH_VIEW",)), ("/api/v1/batch-serial/lots", ("BATCH_VIEW",)),
    ("/api/v1/batch-serial/serials", ("SERIAL_VIEW",)), ("/api/v1/batch-serial/sale-settings", ()),
]
for path, need in reads:
    for name, api in who.items():
        st, b = api.get(path)
        allowed = (not need) or any(code in codes[ROLE[name]] for code in need)
        if need:
            if allowed:
                c.ok(st != 403, f"GET {path} by {name} is allowed ({ROLE[name]} holds one of {need})", (st, message(b)))
            else:
                c.eq(st, 403, f"GET {path} by {name} ({ROLE[name]} holds none of {need})")
        else:
            c.ok(st in (200, 403), f"GET {path} by {name} answers", st)
c.done()
