"""TC-ROLE-001: a firm admin sees the firm roles and none of the platform ones."""
from _ur import *

SYSTEM = {"ACCOUNTANT", "BILLING_EXECUTIVE", "CASHIER", "CUSTOMER_SUPPORT", "FIRM_ADMIN", "FIRM_MANAGER",
          "INVENTORY_MANAGER", "PURCHASE_EXECUTIVE", "PURCHASE_MANAGER", "SALES_EXECUTIVE", "SALES_MANAGER", "VIEWER"}
PLATFORM = {"PLATFORM_ADMIN", "SUPPORT_ADMIN", "LICENSE_ADMIN", "SYSTEM_AUDITOR"}
VISIBLE_TO_PLATFORM = PLATFORM - {"SUPPORT_ADMIN"}  # SUPPORT_ADMIN is a hidden system role
c = Check("tc_role_001"); sc = Scene()
try:
    rows = all_rows(sc.admin, R)
    system = {r["code"] for r in rows if r["is_system"]}
    c.ok(SYSTEM <= system, "the twelve documented system roles are listed", sorted(SYSTEM - system))
    c.eq(sorted(system & PLATFORM), [], "none of the four platform roles")
    seen_platform = {r["code"] for r in rows} & PLATFORM
    c.eq(sorted(seen_platform), [], "not even as custom rows")
    for code in PLATFORM:
        c.eq(len([r for r in all_rows(sc.admin, f"{R}?search={code}") if r["code"] == code]), 0, f"searching for {code} finds nothing")
    pl = {r["code"] for r in all_rows(sc.platform, R)}
    c.ok(VISIBLE_TO_PLATFORM <= pl, "the platform admin does see the platform roles", sorted(VISIBLE_TO_PLATFORM - pl))
    c.ok("SUPPORT_ADMIN" not in pl, "SUPPORT_ADMIN is hidden from every list")
    pid = next(r["id"] for r in all_rows(sc.platform, f"{R}?search=PLATFORM_ADMIN") if r["code"] == "PLATFORM_ADMIN")
    c.ok(sc.admin.get(f"{R}/{pid}")[0] in (403, 404), "and a firm admin cannot open one by id")
finally:
    sc.cleanup()
c.done()
