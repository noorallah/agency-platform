"""Initial system roles, permissions, and role-permission mappings."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity.models import Permission, Role, RolePermission

SYSTEM_ROLE_CODES = (
    "PLATFORM_ADMIN",
    "SUPPORT_ADMIN",
    "LICENSE_ADMIN",
    "SYSTEM_AUDITOR",
    "FIRM_ADMIN",
    "FIRM_MANAGER",
    "ACCOUNTANT",
    "SALES_MANAGER",
    "SALES_EXECUTIVE",
    "PURCHASE_MANAGER",
    "PURCHASE_EXECUTIVE",
    "INVENTORY_MANAGER",
    "CASHIER",
    "BILLING_EXECUTIVE",
    "CUSTOMER_SUPPORT",
    "VIEWER",
)
HIDDEN_SYSTEM_ROLE_CODES = frozenset({"SUPPORT_ADMIN"})

PERMISSION_GROUPS = {
    "platform": (
        "PLATFORM_VIEW",
        "PLATFORM_SETTINGS",
        "SYSTEM_CONFIGURATION",
        "SYSTEM_BACKUP",
        "SYSTEM_RESTORE",
        "LICENSE_MANAGE",
    ),
    "firm": (
        "FIRM_CREATE",
        "FIRM_VIEW",
        "FIRM_UPDATE",
        "FIRM_DELETE",
        "FIRM_ACTIVATE",
        "FIRM_DEACTIVATE",
    ),
    "user": (
        "USER_CREATE",
        "USER_VIEW",
        "USER_UPDATE",
        "USER_DELETE",
        "USER_LOCK",
        "USER_UNLOCK",
        "USER_RESET_PASSWORD",
    ),
    "role": (
        "ROLE_CREATE",
        "ROLE_VIEW",
        "ROLE_UPDATE",
        "ROLE_DELETE",
        "ROLE_ASSIGN",
    ),
    "permission": (
        "PERMISSION_CREATE",
        "PERMISSION_VIEW",
        "PERMISSION_UPDATE",
        "PERMISSION_DELETE",
        "PERMISSION_ASSIGN",
    ),
    "customer": (
        "CUSTOMER_CREATE",
        "CUSTOMER_VIEW",
        "CUSTOMER_UPDATE",
        "CUSTOMER_DELETE",
        "CUSTOMER_RESTORE",
        "CUSTOMER_IMPORT",
        "CUSTOMER_EXPORT",
    ),
    "vendor": (
        "VENDOR_CREATE",
        "VENDOR_VIEW",
        "VENDOR_UPDATE",
        "VENDOR_DELETE",
    ),
    "product": (
        "PRODUCT_CREATE",
        "PRODUCT_VIEW",
        "PRODUCT_UPDATE",
        "PRODUCT_DELETE",
        "PRODUCT_PRICE_UPDATE",
    ),
    "sales": (
        "SALES_QUOTATION_CREATE",
        "SALES_ORDER_CREATE",
        "SALES_INVOICE_CREATE",
        "SALES_RETURN",
        "SALES_CANCEL",
        "SALES_APPROVE",
        "SALES_VIEW",
    ),
    "purchase": (
        "PURCHASE_CREATE",
        "PURCHASE_VIEW",
        "PURCHASE_UPDATE",
        "PURCHASE_CANCEL",
        "PURCHASE_APPROVE",
    ),
    "inventory": (
        "STOCK_VIEW",
        "STOCK_ADJUST",
        "STOCK_TRANSFER",
        "STOCK_AUDIT",
    ),
    "accounting": (
        "ACCOUNT_VIEW",
        "JOURNAL_CREATE",
        "PAYMENT_CREATE",
        "RECEIPT_CREATE",
        "LEDGER_VIEW",
        "TRIAL_BALANCE_VIEW",
        "PROFIT_LOSS_VIEW",
        "BALANCE_SHEET_VIEW",
    ),
    "report": (
        "REPORT_VIEW",
        "REPORT_EXPORT",
        "REPORT_PRINT",
    ),
    "financial_year": (
        "FINANCIAL_YEAR_CREATE",
        "FINANCIAL_YEAR_CLOSE",
        "FINANCIAL_YEAR_REOPEN",
        "FINANCIAL_YEAR_VIEW",
    ),
    "system_administration": (
        "AUDIT_LOG_VIEW",
        "SETTINGS_VIEW",
        "SETTINGS_UPDATE",
    ),
    "high_risk": (
        "DELETE_TRANSACTION",
        "VOID_INVOICE",
        "EDIT_POSTED_TRANSACTION",
        "CHANGE_FINANCIAL_YEAR",
        "RESTORE_BACKUP",
        "DATABASE_MAINTENANCE",
    ),
}

SYSTEM_PERMISSION_CODES = tuple(
    code for codes in PERMISSION_GROUPS.values() for code in codes
)
PLATFORM_ROLE_CODES = frozenset(
    {"PLATFORM_ADMIN", "SUPPORT_ADMIN", "LICENSE_ADMIN", "SYSTEM_AUDITOR"}
)
FIRM_ROLE_CODES = frozenset(SYSTEM_ROLE_CODES) - PLATFORM_ROLE_CODES
PLATFORM_PERMISSION_CODES = frozenset(
    code
    for group in ("platform", "firm", "system_administration", "high_risk")
    for code in PERMISSION_GROUPS[group]
)


def _codes(*groups: str) -> frozenset[str]:
    """Combine named permission groups into an immutable permission set."""
    return frozenset(code for group in groups for code in PERMISSION_GROUPS[group])


_all_permissions = frozenset(SYSTEM_PERMISSION_CODES)
_platform_administration = _codes("platform", "system_administration")
_firm_administration = _codes("user", "role", "permission")
_operational_permissions = _codes(
    "customer",
    "vendor",
    "product",
    "sales",
    "purchase",
    "inventory",
    "accounting",
    "report",
    "financial_year",
)
_all_read_permissions = frozenset(
    code for code in SYSTEM_PERMISSION_CODES if code.endswith("_VIEW")
)

ROLE_PERMISSION_CODES = {
    "PLATFORM_ADMIN": _all_permissions,
    "SUPPORT_ADMIN": _all_permissions,
    "LICENSE_ADMIN": frozenset({"LICENSE_MANAGE", "FIRM_VIEW", "REPORT_VIEW"}),
    "SYSTEM_AUDITOR": frozenset(
        {"FIRM_VIEW", "USER_VIEW", "REPORT_VIEW", "AUDIT_LOG_VIEW"}
    ),
    "FIRM_ADMIN": _operational_permissions
    | _firm_administration
    | frozenset({"SETTINGS_VIEW", "SETTINGS_UPDATE"}),
    "FIRM_MANAGER": _operational_permissions
    - _firm_administration
    - frozenset({"LICENSE_MANAGE"}),
    "ACCOUNTANT": _codes("accounting", "report")
    | frozenset({"CUSTOMER_VIEW", "VENDOR_VIEW", "PRODUCT_VIEW"}),
    "SALES_MANAGER": _codes("customer", "sales", "report")
    | frozenset({"PRODUCT_VIEW"}),
    "SALES_EXECUTIVE": frozenset(
        {
            "CUSTOMER_VIEW",
            "SALES_QUOTATION_CREATE",
            "SALES_ORDER_CREATE",
            "SALES_INVOICE_CREATE",
            "SALES_VIEW",
        }
    ),
    "PURCHASE_MANAGER": _codes("purchase"),
    "PURCHASE_EXECUTIVE": _codes("purchase") - frozenset({"PURCHASE_APPROVE"}),
    "INVENTORY_MANAGER": _codes("inventory"),
    "CASHIER": frozenset({"PAYMENT_CREATE", "RECEIPT_CREATE"}),
    "BILLING_EXECUTIVE": frozenset({"SALES_INVOICE_CREATE", "SALES_VIEW"}),
    "CUSTOMER_SUPPORT": frozenset({"CUSTOMER_VIEW", "CUSTOMER_UPDATE", "PRODUCT_VIEW"}),
    "VIEWER": _all_read_permissions
    - frozenset(
        {
            "PLATFORM_VIEW",
            "USER_VIEW",
            "ROLE_VIEW",
            "PERMISSION_VIEW",
            "AUDIT_LOG_VIEW",
            "SETTINGS_VIEW",
        }
    ),
}


def seed_system_rbac(session: Session) -> None:
    """Create or restore initial system RBAC records without altering custom data."""
    roles = _seed_roles(session)
    permissions = _seed_permissions(session)
    session.flush()

    assignments = {
        (assignment.role_id, assignment.permission_id): assignment
        for assignment in session.scalars(select(RolePermission))
    }
    for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
        role = roles[role_code]
        for permission_code in permission_codes:
            permission = permissions[permission_code]
            assignment = assignments.get((role.id, permission.id))
            if assignment is None:
                session.add(
                    RolePermission(role_id=role.id, permission_id=permission.id)
                )
            elif assignment.is_deleted:
                assignment.is_deleted = False
                assignment.deleted_at = None
                assignment.deleted_by = None


def _seed_roles(session: Session) -> dict[str, Role]:
    """Create the reserved role records and restore soft-deleted seed rows."""
    existing = {role.code: role for role in session.scalars(select(Role))}
    seeded: dict[str, Role] = {}
    for code in SYSTEM_ROLE_CODES:
        role = existing.get(code)
        if role is None:
            role = Role(
                code=code,
                name=_display_name(code),
                description="System-defined role.",
                is_system=True,
            )
            session.add(role)
        else:
            role.is_system = True
            role.is_deleted = False
            role.deleted_at = None
            role.deleted_by = None
        seeded[code] = role
    return seeded


def _seed_permissions(session: Session) -> dict[str, Permission]:
    """Create the reserved permission records and restore soft-deleted seed rows."""
    existing = {
        permission.code: permission
        for permission in session.scalars(select(Permission))
    }
    seeded: dict[str, Permission] = {}
    for code in SYSTEM_PERMISSION_CODES:
        permission = existing.get(code)
        if permission is None:
            permission = Permission(
                code=code,
                name=_display_name(code),
                description="System-defined permission.",
                is_system=True,
            )
            session.add(permission)
        else:
            permission.is_system = True
            permission.is_deleted = False
            permission.deleted_at = None
            permission.deleted_by = None
        seeded[code] = permission
    return seeded


def _display_name(code: str) -> str:
    """Convert a system code into a readable initial display name."""
    return code.replace("_", " ").title()
