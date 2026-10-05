"""Initial system roles, permissions, and role-permission mappings."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils.dates import utc_now
from app.identity.models import (
    Permission,
    Role,
    RolePermission,
    UserTemplate,
    UserTemplateRole,
)

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
        "CUSTOMER_MANAGE_SETTINGS",
        # Changing where a customer's refunds are paid (MST-4), a duty of its
        # own like the supplier twin.
        "CUSTOMER_MANAGE_BANK_DETAILS",
        # Letting a new outlet a salesman added be billed (SEL-15).
        "CUSTOMER_APPROVE",
    ),
    "vendor": (
        "VENDOR_CREATE",
        "VENDOR_VIEW",
        "VENDOR_UPDATE",
        "VENDOR_DELETE",
        "VENDOR_RESTORE",
        "VENDOR_IMPORT",
        "VENDOR_EXPORT",
        "VENDOR_MANAGE_CATEGORIES",
        "VENDOR_VIEW_FINANCIAL_DETAILS",
        "VENDOR_MANAGE_BANK_DETAILS",
    ),
    "branch_warehouse": (
        "BRANCH_VIEW",
        "BRANCH_CREATE",
        "BRANCH_UPDATE",
        "BRANCH_DELETE",
        "BRANCH_RESTORE",
        "WAREHOUSE_VIEW",
        "WAREHOUSE_CREATE",
        "WAREHOUSE_UPDATE",
        "WAREHOUSE_DELETE",
        "WAREHOUSE_RESTORE",
        "STORAGE_AREA_MANAGE",
        "BRANCH_WAREHOUSE_IMPORT",
        "BRANCH_WAREHOUSE_EXPORT",
    ),
    "tax_framework": (
        "TAX_VIEW",
        "TAX_CREATE",
        "TAX_UPDATE",
        "TAX_DELETE",
        "TAX_RESTORE",
        "TAX_IMPORT",
        "TAX_EXPORT",
        "TAX_MANAGE_SETTINGS",
        "TAX_RULE_VIEW",
        "TAX_RULE_CREATE",
        "TAX_RULE_UPDATE",
        "TAX_RULE_DELETE",
        "TAX_RULE_RESTORE",
        "TAX_SIMULATE",
    ),
    "product": (
        "PRODUCT_CREATE",
        "PRODUCT_VIEW",
        "PRODUCT_UPDATE",
        "PRODUCT_DELETE",
        "PRODUCT_RESTORE",
        "PRODUCT_IMPORT",
        "PRODUCT_EXPORT",
        "PRODUCT_VIEW_COST_PRICE",
        "PRODUCT_ATTRIBUTE_MANAGE",
        "PRODUCT_PRICING_MANAGE",
        "PRODUCT_TAX_MANAGE",
    ),
    "territory": (
        "TERRITORY_CREATE",
        "TERRITORY_VIEW",
        "TERRITORY_UPDATE",
        "TERRITORY_DELETE",
        "TERRITORY_RESTORE",
        "TERRITORY_ASSIGN_CUSTOMERS",
        "TERRITORY_ASSIGN_SALESMEN",
        "TERRITORY_IMPORT",
        "TERRITORY_EXPORT",
    ),
    "sales": (
        "SALES_QUOTATION_CREATE",
        "SALES_ORDER_CREATE",
        "SALES_INVOICE_CREATE",
        "SALES_RETURN",
        "SALES_CANCEL",
        "SALES_APPROVE",
        "SALES_VIEW",
        # Enforced by the delivery-note router; without these no non-platform
        # user can be granted delivery-note create/update/import/export.
        "SALES_CREATE",
        "SALES_UPDATE",
        "SALES_IMPORT",
        "SALES_EXPORT",
        # Which of quotation, sales order and delivery note this firm raises by
        # hand. Subtracted from `SALES_MANAGER` below, beside the credit block
        # and for the same reason.
        "SALES_MANAGE_SETTINGS",
        # Approve a sale below cost or below a product's minimum price when
        # the firm's policy refuses it, with a reason the document keeps
        # (backlog 64 row 2). A control over the people who sell, so it is
        # subtracted from `SALES_MANAGER` with the settings code.
        "SALES_PRICE_OVERRIDE",
    ),
    "einvoice": (
        "EINVOICE_VIEW",
        # Registering files a document with the tax authority. Even in sandbox
        # it is the action that will file one the day a firm switches to LIVE,
        # so it is its own code rather than riding on a sales permission.
        "EINVOICE_MANAGE",
    ),
    "proforma": (
        "PROFORMA_VIEW",
        # A proforma posts nothing, so raising one moves no money and needs no
        # separate approval of its own -- the order it states was approved
        # already. Two codes rather than three for exactly that reason.
        "PROFORMA_MANAGE",
    ),
    "credit_note": (
        "CREDIT_NOTE_VIEW",
        "CREDIT_NOTE_MANAGE",
        # Approving reduces what a customer owes **and reverses tax the firm
        # has declared to the authority**. Drafting one is bookkeeping;
        # approving it changes a return. Separate for the same reason
        # `COMMISSION_PAY` is separate from `COMMISSION_MANAGE`.
        "CREDIT_NOTE_APPROVE",
    ),
    "customer_debit_note": (
        "CUSTOMER_DEBIT_NOTE_VIEW",
        "CUSTOMER_DEBIT_NOTE_MANAGE",
        # Approving raises what a customer owes **and the output tax the firm
        # declares**. The twin of `CREDIT_NOTE_APPROVE`, held back from the
        # role that drafts one for the same reason (backlog 77 row 5).
        "CUSTOMER_DEBIT_NOTE_APPROVE",
    ),
    "debit_note": (
        "DEBIT_NOTE_VIEW",
        "DEBIT_NOTE_MANAGE",
        # Approving reduces what the firm owes a supplier **and reverses input
        # tax it has claimed**. The purchasing twin of `CREDIT_NOTE_APPROVE`,
        # held back from the role that drafts one for the same reason.
        "DEBIT_NOTE_APPROVE",
    ),
    "party_adjustment": (
        "PARTY_ADJUSTMENT_VIEW",
        # Drafting a write-off, write-back or set-off, and approving one at
        # or below the firm's threshold (backlog 74 row 2).
        "PARTY_ADJUSTMENT_MANAGE",
        # Approving or cancelling one above the threshold, as somebody other
        # than its maker, and setting the threshold itself. A rupee written
        # off is profit given away; the role that clears balances must not
        # be the one that decides how much it may clear alone.
        "PARTY_ADJUSTMENT_APPROVE",
    ),
    "batch_serial": (
        "BATCH_VIEW",
        "BATCH_CREATE",
        "BATCH_UPDATE",
        "BATCH_DELETE",
        "SERIAL_VIEW",
        "SERIAL_CREATE",
        "SERIAL_UPDATE",
        "SERIAL_DELETE",
    ),
    "purchase": (
        "PURCHASE_CREATE",
        "PURCHASE_VIEW",
        "PURCHASE_UPDATE",
        "PURCHASE_DELETE",
        "PURCHASE_RESTORE",
        "PURCHASE_CANCEL",
        "PURCHASE_APPROVE",
        # Approving a supplier bill priced past the firm's tolerance over its
        # order (BUY-10): the purchase manager's call, not the executive's.
        "PURCHASE_APPROVE_OVER_TOLERANCE",
        # Passing or rejecting received goods held for inspection (BUY-9):
        # not the executive who counted them in; the inventory manager too.
        "PURCHASE_INSPECT",
        # Approving an order past a purchase budget where the firm requires
        # it (BUY-14): the purchase manager's call, not the executive's.
        "PURCHASE_APPROVE_OVER_BUDGET",
        # Receiving goods against an order (D-ROLE-3): raising, editing and
        # completing a goods receipt, which puts the stock on the shelf. The
        # job of whoever counts the goods in -- Purchasing and Warehouse --
        # rather than of whoever approves the order or the bill, the split
        # ERPNext draws with Stock User and Zoho with *Purchase Receives*.
        "PURCHASE_RECEIVE",
        # Raising a purchase requisition (BUY-7): asking for goods, which a
        # storeman does without being able to order them.
        "PURCHASE_REQUISITION_CREATE",
        # Requests for quotation (PG-8): reading them and the comparison, and
        # raising, sending, quoting and choosing on them. Raising the orders
        # from the chosen quotes also takes `PURCHASE_CREATE`.
        "RFQ_VIEW",
        "RFQ_MANAGE",
        # Rate contracts with suppliers (PG-9): reading them and what has been
        # drawn against them, and typing, closing and cancelling them.
        # Activating one takes `PURCHASE_APPROVE`, as approving an order does.
        "RATE_CONTRACT_VIEW",
        "RATE_CONTRACT_MANAGE",
        # Bills of Entry on imports (PG-12 part B): reading them, and typing,
        # changing and deleting drafts. Posting one, and cancelling it, takes
        # `PURCHASE_APPROVE`, as approving a bill does.
        "BILL_OF_ENTRY_VIEW",
        "BILL_OF_ENTRY_MANAGE",
        # Supplier free-goods schemes on an item (PG-11): reading them, and
        # setting them up, changing and removing them. An order priced
        # afterwards takes the scheme's free goods by itself.
        "SUPPLIER_SCHEME_VIEW",
        "SUPPLIER_SCHEME_MANAGE",
        "PURCHASE_IMPORT",
        "PURCHASE_EXPORT",
        # Which of purchase order and goods receipt this firm raises by hand.
        # Subtracted from both purchase roles below: turning the receipt stage
        # off means goods are confirmed by the bill rather than by whoever
        # counts them in, a control over those roles rather than theirs.
        "PURCHASE_MANAGE_SETTINGS",
    ),
    "inventory": (
        "INVENTORY_VIEW",
        "OPENING_STOCK_CREATE",
        "OPENING_STOCK_UPDATE",
        "INVENTORY_LEDGER_VIEW",
        "INVENTORY_EXPORT",
        "INVENTORY_IMPORT",
        "INVENTORY_TRANSACTION_VIEW",
        "INVENTORY_ADJUST",
        # The firm's list of adjustment reasons and the account each costs
        # (STK-7): where a write-off lands is a control, not an adjustment.
        "INVENTORY_MANAGE_REASONS",
        # The value limits on stock adjustments (STK-8). Withheld from the
        # inventory manager: the role a limit constrains must not lift it.
        "INVENTORY_MANAGE_SETTINGS",
    ),
    "uom_framework": (
        "UOM_VIEW",
        "UOM_MANAGE",
        "PACKAGING_MANAGE",
        "CONVERSION_RULE_MANAGE",
        "UOM_IMPORT",
        "UOM_EXPORT",
    ),
    "pricing": (
        "PRICE_LIST_VIEW",
        "PRICE_LIST_MANAGE",
    ),
    "sales_targets": (
        "SALES_TARGET_VIEW",
        "SALES_TARGET_MANAGE",
    ),
    "trade_licences": (
        # Drug, FSSAI, insecticide, fertiliser and seed licences of the firm,
        # its customers and its vendors (backlog 54). Not `LICENSE_*`, which
        # is the product's own licence to run.
        "TRADE_LICENCE_VIEW",
        "TRADE_LICENCE_MANAGE",
        # Whether a sale without the licence warns or is refused. A control
        # over the people who sell, so no sales role holds it.
        "TRADE_LICENCE_MANAGE_SETTINGS",
        # Approve a sale the licence check refuses, with a reason that is
        # recorded on the document. Not a sales role's either, for the same
        # reason.
        "TRADE_LICENCE_OVERRIDE",
    ),
    "promotions": (
        "PROMOTION_VIEW",
        # `SALES_MANAGER` is granted `PROMOTION_VIEW` alone, below: a promotion
        # is a discount the firm gives away, and the role measured on what it
        # sells does not set it.
        "PROMOTION_MANAGE",
    ),
    "loyalty": (
        "LOYALTY_VIEW",
        # Spending a customer's credit settles a bill with money the firm owes
        # them, so it is its own authority rather than part of reading a
        # balance.
        "LOYALTY_MANAGE",
        # The conversion rate decides what every customer's credit is worth.
        # Deliberately not granted to `SALES_MANAGER`, on the same reasoning
        # as the credit policy: whoever the scheme constrains must not be able
        # to rewrite what a point is worth.
        "LOYALTY_MANAGE_SETTINGS",
    ),
    "tcs": (
        "TCS_VIEW",
        # The policy decides what every buyer is charged on every receipt, so
        # writing it is separate from reading it -- and deliberately not
        # granted to `SALES_MANAGER`, on the same reasoning as the credit
        # policy: the role a rule constrains must not be able to switch it off.
        "TCS_MANAGE",
    ),
    "commission": (
        "COMMISSION_VIEW",
        "COMMISSION_MANAGE",
        # Money leaving the firm is a separate authority from agreeing what is
        # owed. Whoever accrues and approves a payout is stating a debt;
        # whoever pays it is moving cash, and one person holding both is the
        # segregation of duties this split exists to keep. Deliberately not
        # granted to `SALES_MANAGER`, who would otherwise be able to pay their
        # own team -- and, on a rule with no salesman, themselves.
        "COMMISSION_PAY",
    ),
    "accounting": (
        "ACCOUNT_VIEW",
        "ACCOUNT_MANAGE",
        "JOURNAL_VIEW",
        "JOURNAL_CREATE",
        "JOURNAL_POST",
        "JOURNAL_REVERSE",
        "PAYMENT_CREATE",
        "PAYMENT_VIEW",
        # Approving a payment run books every payment in it (BUY-11): the
        # accountant's call, not the cashier's who records single payments.
        "PAYMENT_RUN_APPROVE",
        # Recording or taking back a supplier's gift (BUY-2): it posts a
        # journal, so it sits with the books.
        "SUPPLIER_GIFT_MANAGE",
        "RECEIPT_CREATE",
        "RECEIPT_VIEW",
        "LEDGER_VIEW",
        "TRIAL_BALANCE_VIEW",
        "PROFIT_LOSS_VIEW",
        "BALANCE_SHEET_VIEW",
        # The fixed asset register (PG-13): reading it and its reports, and
        # keeping classes and assets. A depreciation run, cancelling one and
        # a disposal post journals, so they also need `JOURNAL_POST`.
        "FIXED_ASSET_VIEW",
        "FIXED_ASSET_MANAGE",
    ),
    "expenses": (
        "EXPENSE_VIEW",
        # Recording an expense writes and posts its journal, so a manager can
        # book rent or fuel without `JOURNAL_POST` -- which would let them
        # post anything to any account. The journal it writes is always Dr an
        # expense account, Cr a money account, and nothing else.
        "EXPENSE_CREATE",
        # Taking one back is separate from recording it, as reversing a
        # journal is separate from posting one.
        "EXPENSE_CANCEL",
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
    "messaging": (
        # Send or resend a document to a customer by email, WhatsApp or SMS
        # (backlog 51, decision 5). Not a `*_VIEW`: printing shows what the
        # screen shows, sending acts for the firm towards somebody outside it.
        # The firm's messaging *settings* are `SETTINGS_UPDATE`, like its
        # numbering series and print templates.
        "DOCUMENT_SEND",
    ),
    # A firm's own audit trail (decision B1, 2026-10-02): readable with a firm
    # selected and nowhere else, so a firm administrator may grant it to their
    # own roles -- which `AUDIT_LOG_VIEW`, a platform code, they cannot.
    "firm_audit": ("FIRM_AUDIT_LOG_VIEW",),
    #: A firm's own custom fields (MST-8): firm administration, so the firm
    #: administrator holds them and the firm manager does not.
    "custom_fields": (
        "CUSTOM_FIELD_VIEW",
        "CUSTOM_FIELD_MANAGE",
    ),
    "system_administration": (
        "AUDIT_LOG_VIEW",
        "DIAGNOSTICS_VIEW",
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
#: Codes that name an act only the platform designation performs, so no role
#: may hold them (D-IDN-10). Each is seeded and read by no route: the firm
#: routes and the permission catalogue's writes are `require_platform_admin()`,
#: which makes any code on them grant nothing; setting somebody else's
#: password is the designation's for the reason `test_platform_only_routes.py`
#: records; and a lockout lifts itself after `AGENCY_SECURITY_LOCKOUT_MINUTES`
#: while switching an account off is `USER_UPDATE`. Granting one to a role
#: therefore promised a power it did not confer.
#:
#: Decided by Claude, industry standard: tenant lifecycle and the capability
#: catalogue are operator (superuser) actions, not grantable permissions. The
#: codes stay in the catalogue because the designation's `permissions` claim
#: carries them and the desktop gates the Firms and Permissions buttons on
#: them; they are stripped from every role (`20260924_0161`) and refused by
#: `set_role_permissions`, and a firm is not shown them.
DESIGNATION_ONLY_PERMISSION_CODES = frozenset(
    {
        "FIRM_CREATE",
        "FIRM_UPDATE",
        "FIRM_DELETE",
        "FIRM_ACTIVATE",
        "FIRM_DEACTIVATE",
        "PERMISSION_CREATE",
        "PERMISSION_UPDATE",
        "PERMISSION_DELETE",
        "USER_RESET_PASSWORD",
        "USER_LOCK",
        "USER_UNLOCK",
    }
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
#: What a `PLATFORM`-scoped administrator holds: run the platform, and set a
#: firm up until it works. Deliberately **not** `PLATFORM_PERMISSION_CODES`,
#: which is a different question -- that set is what a firm administrator may
#: not *grant*, and it is wrong here in both directions. It omits `user`,
#: `role` and `permission`, which are the operator's whole job; and it includes
#: `high_risk`, which is `VOID_INVOICE` and `EDIT_POSTED_TRANSACTION` on a
#: firm's posted books -- the one thing this tier exists not to touch.
PLATFORM_OPERATOR_PERMISSION_CODES = frozenset(
    code
    for group in (
        "platform",
        "firm",
        "system_administration",
        "user",
        "role",
        "permission",
    )
    for code in PERMISSION_GROUPS[group]
)


def _codes(*groups: str) -> frozenset[str]:
    """Combine named permission groups into an immutable permission set."""
    return frozenset(code for group in groups for code in PERMISSION_GROUPS[group])


_all_permissions = frozenset(SYSTEM_PERMISSION_CODES)
_platform_administration = _codes("platform", "system_administration")
_firm_administration = _codes("user", "role", "permission", "custom_fields")
#: Running a firm's business, as opposed to administering its people. Held by
#: `FIRM_ADMIN` and -- minus the administration codes -- by `FIRM_MANAGER`.
#:
#: **A group added to `PERMISSION_GROUPS` is not added here**, and five slipped
#: through: `credit_note`, `proforma`, `einvoice`, `loyalty` and `tcs` all
#: shipped with a module, a screen and a seeded gate, and none of them reached
#: the role whose description is running the firm and every module. A firm
#: administrator could not open Credit Notes, Proforma, E-Invoice, Loyalty or
#: TCS at all; `SALES_MANAGER` names most of them individually, so the screens
#: were reachable by somebody, which is why nobody noticed. Corrected
#: 2026-09-06 (`20260906_0130` grants them in databases that already exist).
#:
#: The check that finds the next one is in
#: `tests/unit/test_firm_admin_holds_the_firms_own_modules.py`: it asks which
#: groups are operational -- neither platform nor firm administration -- and
#: fails if this list omits one. A list somebody has to remember to update is
#: a list that drifts.
_operational_permissions = _codes(
    "customer",
    "vendor",
    "branch_warehouse",
    "tax_framework",
    "product",
    "territory",
    "sales",
    "purchase",
    "inventory",
    "batch_serial",
    "uom_framework",
    "pricing",
    "promotions",
    "sales_targets",
    "trade_licences",
    "commission",
    "credit_note",
    "customer_debit_note",
    "debit_note",
    "party_adjustment",
    "proforma",
    "einvoice",
    "loyalty",
    "tcs",
    "accounting",
    "expenses",
    "report",
    "financial_year",
    "messaging",
)
_all_read_permissions = frozenset(
    code for code in SYSTEM_PERMISSION_CODES if code.endswith("_VIEW")
)

#: The masters a purchase document is typed from (D-ROLE-1). The buying
#: editors read these lists to fill their pickers -- `GET /vendors`
#: (`VENDOR_VIEW`), `/products` (`PRODUCT_VIEW`), `/branches` (`BRANCH_VIEW`),
#: `/warehouses` and their storage nodes (`WAREHOUSE_VIEW`),
#: `/tax-framework/profiles` (`TAX_VIEW`) and `/uom-framework/uoms`
#: (`UOM_VIEW`). Without them the Purchasing job opened a purchase order and
#: was told it had no vendor and no product to order. A supplier's bank
#: accounts (`VENDOR_VIEW_FINANCIAL_DETAILS`) and a product's cost
#: (`PRODUCT_VIEW_COST_PRICE`) stay out: neither is needed to raise the order.
_purchase_document_masters = frozenset(
    {
        "VENDOR_VIEW",
        "PRODUCT_VIEW",
        "BRANCH_VIEW",
        "WAREHOUSE_VIEW",
        "TAX_VIEW",
        "UOM_VIEW",
    }
)

_SEEDED_ROLE_PERMISSION_CODES = {
    "PLATFORM_ADMIN": _all_permissions,
    "SUPPORT_ADMIN": _all_permissions,
    "LICENSE_ADMIN": frozenset({"LICENSE_MANAGE", "FIRM_VIEW", "REPORT_VIEW"}),
    "SYSTEM_AUDITOR": frozenset(
        {"FIRM_VIEW", "USER_VIEW", "REPORT_VIEW", "AUDIT_LOG_VIEW", "DIAGNOSTICS_VIEW"}
    ),
    "FIRM_ADMIN": _operational_permissions | _firm_administration
    # Granted directly rather than through a group. All three are in
    # `PLATFORM_PERMISSION_CODES`, which answers "what may a firm
    # administrator not *grant*" -- a different question from what they may
    # hold, and the reason `SETTINGS_VIEW` has always been here.
    #
    # `AUDIT_LOG_VIEW` joined them on 2026-09-06. The Settings module is
    # offered on any of `SETTINGS_VIEW`, `AUDIT_LOG_VIEW` or
    # `DIAGNOSTICS_VIEW` and both its tabs demand one of the latter two, so a
    # firm administrator was offered the module and refused every tab in it:
    # it opened empty. `audit_scope` reads one trail chosen by firm context,
    # so with `X-Firm-ID` they get **their own firm's** and nothing else.
    #
    # `DIAGNOSTICS_VIEW` deliberately stays out: error reports are
    # operational telemetry for whoever maintains the product, kept in one
    # place rather than per firm, and `firm_id` on them is data rather than
    # routing.
    | frozenset({"SETTINGS_VIEW", "SETTINGS_UPDATE", "AUDIT_LOG_VIEW"})
    | _codes("firm_audit"),
    "FIRM_MANAGER": _operational_permissions
    - _firm_administration
    - frozenset({"LICENSE_MANAGE"}),
    "ACCOUNTANT": _codes("accounting", "commission", "expenses", "report")
    | frozenset(
        {
            "CUSTOMER_VIEW",
            "VENDOR_VIEW",
            # Whoever pays a supplier has to read the account the money goes
            # to. `VENDOR_VIEW` served it to everybody until the code was
            # enforced (D-MST-10), so this keeps what the accountant already
            # read; changing the account stays with `VENDOR_MANAGE_BANK_DETAILS`,
            # which this role deliberately does not hold -- whoever sends the
            # money must not be the one who says where it goes.
            "VENDOR_VIEW_FINANCIAL_DETAILS",
            "PRODUCT_VIEW",
            # Credit policy governs receivables, so it belongs to the role that
            # owns them rather than to the role it constrains.
            "CUSTOMER_MANAGE_SETTINGS",
            # Chasing what is owed: resending a bill or a reminder.
            "DOCUMENT_SEND",
            # Clears small balances -- a few rupees short, a set-off -- and
            # drafts larger write-offs for somebody else to approve. Approving
            # above the threshold is held back: the role that books a
            # write-off is not the one that agrees to it (backlog 74 row 2).
            "PARTY_ADJUSTMENT_VIEW",
            "PARTY_ADJUSTMENT_MANAGE",
        }
    ),
    "SALES_MANAGER": (
        _codes("customer", "sales", "report")
        # A sales manager must not be able to switch off the credit block that
        # limits their own sales, nor the delivery-note stage: turning that off
        # means dispatch is confirmed by the sale itself rather than by whoever
        # watches the goods leave. Both are controls over the role, so neither
        # belongs to it.
        - frozenset(
            {
                "CUSTOMER_MANAGE_SETTINGS",
                # Where a refund is paid is a payment instruction, not sales
                # work -- the classic redirection fraud (MST-4).
                "CUSTOMER_MANAGE_BANK_DETAILS",
                "SALES_MANAGE_SETTINGS",
                "SALES_PRICE_OVERRIDE",
            }
        )
    )
    | frozenset(
        {
            "PRODUCT_VIEW",
            # D-ROLE-1: a quotation, an order, a delivery note and a return
            # name a branch and a warehouse, and a delivery note's lines a tax
            # profile and a unit -- `/branches`, `/warehouses`,
            # `/tax-framework/profiles`, `/uom-framework/uoms`.
            "BRANCH_VIEW",
            "WAREHOUSE_VIEW",
            "TAX_VIEW",
            "UOM_VIEW",
            "TERRITORY_VIEW",
            "TERRITORY_ASSIGN_CUSTOMERS",
            # Reads the offers their team sells under. Setting them is not
            # theirs, for the reason the commission rate below is not: a
            # discount the firm gives away is a control over the role, and
            # `PROMOTION_MANAGE` is deliberately absent here.
            "PROMOTION_VIEW",
            # Reads the number their team is measured on. Setting it is the
            # firm's decision, not the role the target constrains.
            "SALES_TARGET_VIEW",
            # A customer's licence is customer master data, which this role
            # owns; whether a sale without one is refused is the firm's.
            "TRADE_LICENCE_VIEW",
            "TRADE_LICENCE_MANAGE",
            # A sales manager reads what their team earned; setting the rate
            # they are paid on is not theirs, the way the credit policy that
            # limits their own sales is not theirs to switch off.
            "COMMISSION_VIEW",
            # A sales manager may draft a credit note; approving one reverses
            # declared tax and is not theirs, the same split as commission.
            "CREDIT_NOTE_VIEW",
            "CREDIT_NOTE_MANAGE",
            # And a debit note, the same split: drafting is the desk's,
            # approving adds declared tax and is not.
            "CUSTOMER_DEBIT_NOTE_VIEW",
            "CUSTOMER_DEBIT_NOTE_MANAGE",
            # A proforma states what an approved order will be charged and
            # posts nothing, so raising one is ordinary sales-desk work.
            "PROFORMA_VIEW",
            "PROFORMA_MANAGE",
            # Reading what was registered is part of running a sales desk;
            # filing with the authority is not, the same split as approving a
            # credit note.
            "EINVOICE_VIEW",
            # A sales manager sees what a buyer will be charged before asking
            # for the money -- it is part of quoting a collection. Setting the
            # rate is the firm's, like the credit policy above.
            "TCS_VIEW",
            # Reading a customer's credit and spending it are both part of
            # running a sales desk; deciding what a point is worth is not.
            "LOYALTY_VIEW",
            "LOYALTY_MANAGE",
            # Sending a customer their bill is sales-desk work.
            "DOCUMENT_SEND",
        }
    ),
    "SALES_EXECUTIVE": frozenset(
        {
            "CUSTOMER_VIEW",
            # D-SELL-57: the salesman adds the shop he finds on his beat, and
            # deliberately does **not** hold `CUSTOMER_APPROVE` -- so where the
            # firm switches on `new_outlets_need_approval` his outlet starts
            # PENDING and the office approves it (SEL-15). No seeded role
            # held the one without the other, so the setting could not be
            # reached with the jobs a firm starts with. The code is enforced
            # on `POST /customers` alone.
            "CUSTOMER_CREATE",
            "TERRITORY_VIEW",
            "SALES_QUOTATION_CREATE",
            "SALES_ORDER_CREATE",
            "SALES_INVOICE_CREATE",
            "SALES_VIEW",
            # Sees why a line needing a licence is flagged on a customer.
            "TRADE_LICENCE_VIEW",
            # D-ROLE-1: a quotation and an order are typed from the product
            # list and name a branch and a warehouse -- `/products`,
            # `/branches`, `/warehouses`.
            "PRODUCT_VIEW",
            "BRANCH_VIEW",
            "WAREHOUSE_VIEW",
            # D-ROLE-4: the order and invoice views name each line's tax
            # profile and unit (`/tax-framework/profiles`,
            # `/uom-framework/uoms`), and showed their ids without these.
            "TAX_VIEW",
            "UOM_VIEW",
        }
    ),
    # A vendor's licence is vendor master data, which the purchase manager
    # owns; the executive reads it to know a supplier may supply the goods.
    "PURCHASE_MANAGER": (_codes("purchase") - frozenset({"PURCHASE_MANAGE_SETTINGS"}))
    | frozenset(
        {
            "TRADE_LICENCE_VIEW",
            "TRADE_LICENCE_MANAGE",
            # A purchase manager may draft a debit note; approving one reverses
            # claimed input tax and is not theirs -- the split the sales
            # manager has on credit notes.
            "DEBIT_NOTE_VIEW",
            "DEBIT_NOTE_MANAGE",
        }
    )
    | _purchase_document_masters
    # D-ROLE-1: the job template says this role "owns the vendor masters", and
    # it held no vendor code at all. It keeps them now the way `SALES_MANAGER`
    # keeps customers -- everything but where the money goes. Changing a
    # supplier's bank account is a payment instruction (MST-4), and reading it
    # is for whoever pays (`ACCOUNTANT`), so both stay out.
    | (
        _codes("vendor")
        - frozenset({"VENDOR_MANAGE_BANK_DETAILS", "VENDOR_VIEW_FINANCIAL_DETAILS"})
    ),
    "PURCHASE_EXECUTIVE": (
        _codes("purchase")
        - frozenset(
            {
                "PURCHASE_APPROVE",
                "PURCHASE_APPROVE_OVER_TOLERANCE",
                "PURCHASE_INSPECT",
                "PURCHASE_APPROVE_OVER_BUDGET",
                "PURCHASE_MANAGE_SETTINGS",
            }
        )
    )
    | frozenset({"TRADE_LICENCE_VIEW"})
    # D-ROLE-1: the masters every buying editor picks from.
    | _purchase_document_masters,
    "INVENTORY_MANAGER": (
        _codes("inventory", "batch_serial") - frozenset({"INVENTORY_MANAGE_SETTINGS"})
    )
    | frozenset(
        {
            "PURCHASE_INSPECT",
            "PURCHASE_REQUISITION_CREATE",
            # D-ROLE-3: Warehouse "receives, stores, picks and dispatches
            # stock", so it raises and completes the goods receipt. It reads
            # the receipts and the orders it receives against through this
            # code, not through `PURCHASE_VIEW`, so the bills and returns stay
            # out of its reach -- and `PURCHASE_CREATE` stays out: ordering is
            # not the storeman's. The receipt editor's lines name a tax
            # profile and a unit (`/tax-framework/profiles`,
            # `/uom-framework/uoms`).
            "PURCHASE_RECEIVE",
            "TAX_VIEW",
            "UOM_VIEW",
            # D-ROLE-1: an adjustment, a transfer, a count, a repack and a
            # requisition are typed from `/products`, `/branches` and
            # `/warehouses`; a requisition loads `/vendors` with them, and
            # writing stock off as a free gift must name the customer it went
            # to (`/customers`).
            "PRODUCT_VIEW",
            "BRANCH_VIEW",
            "WAREHOUSE_VIEW",
            "VENDOR_VIEW",
            "CUSTOMER_VIEW",
        }
    ),
    "CASHIER": frozenset(
        # A cashier who can record money and not look at what they recorded
        # cannot do the job; the view codes went in with the receipts and
        # payments module that first enforced them.
        {"PAYMENT_CREATE", "PAYMENT_VIEW", "RECEIPT_CREATE", "RECEIPT_VIEW"}
    ),
    # Whoever raises the bill can send it to the customer (backlog 51).
    "BILLING_EXECUTIVE": frozenset(
        {
            "SALES_INVOICE_CREATE",
            "SALES_VIEW",
            "DOCUMENT_SEND",
            # D-ROLE-1: the invoice editor reads `/customers` and `/products`.
            "CUSTOMER_VIEW",
            "PRODUCT_VIEW",
            # D-ROLE-4: the invoice view names the branch, warehouse, tax
            # profile and unit, and showed their ids without these.
            "BRANCH_VIEW",
            "WAREHOUSE_VIEW",
            "TAX_VIEW",
            "UOM_VIEW",
        }
    ),
    "CUSTOMER_SUPPORT": frozenset({"CUSTOMER_VIEW", "CUSTOMER_UPDATE", "PRODUCT_VIEW"}),
    "VIEWER": _all_read_permissions
    - frozenset(
        {
            "PLATFORM_VIEW",
            "USER_VIEW",
            "ROLE_VIEW",
            "PERMISSION_VIEW",
            "AUDIT_LOG_VIEW",
            # Who did what is not a read-only screen for everybody (B1).
            "FIRM_AUDIT_LOG_VIEW",
            "SETTINGS_VIEW",
        }
    ),
}

#: What each seeded role grants: the table above, less the designation-only
#: codes, which no role holds.
ROLE_PERMISSION_CODES = {
    role: codes - DESIGNATION_ONLY_PERMISSION_CODES
    for role, codes in _SEEDED_ROLE_PERMISSION_CODES.items()
}


#: Platform-provided job templates: a name a firm already uses, and the roles
#: that job needs. `firm_id` is NULL, so every firm is offered them.
#:
#: These exist because a firm administrator hiring a counter clerk should not
#: have to reassemble a permission set from twelve roles and remember which. A
#: template is where they **start** -- what the new user holds afterwards is an
#: ordinary role set they are free to edit.
#:
#: Most jobs are one role, and that is not a redundancy: the value is the name.
#: "Counter Sales" is a job a firm has; `CASHIER` plus `BILLING_EXECUTIVE` is a
#: permission decision somebody has to make correctly, once, rather than on
#: every hire.
SYSTEM_USER_TEMPLATES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "firm-administrator",
        "Firm Administrator",
        "Runs the firm: its people, their access, and every module.",
        ("FIRM_ADMIN",),
    ),
    (
        "firm-manager",
        "Firm Manager",
        "Every operational module, without administering the firm's users.",
        ("FIRM_MANAGER",),
    ),
    (
        "counter-sales",
        "Counter Sales",
        "Takes payment and raises the bill at the counter.",
        ("CASHIER", "BILLING_EXECUTIVE"),
    ),
    (
        "field-sales",
        "Field Sales",
        "Works a beat: customers, quotations and orders on their round.",
        ("SALES_EXECUTIVE",),
    ),
    (
        "sales-manager",
        "Sales Manager",
        "Owns the sales team, its territories and its customers.",
        ("SALES_MANAGER",),
    ),
    (
        "warehouse",
        "Warehouse",
        "Receives, stores, picks and dispatches stock.",
        ("INVENTORY_MANAGER",),
    ),
    (
        "purchasing",
        "Purchasing",
        "Raises orders on vendors and receives against them.",
        ("PURCHASE_EXECUTIVE",),
    ),
    (
        "purchase-manager",
        "Purchase Manager",
        "Approves purchasing and owns the vendor masters.",
        ("PURCHASE_MANAGER",),
    ),
    (
        "accounts",
        "Accounts",
        "Keeps the books: the ledger, the periods and the reports.",
        ("ACCOUNTANT",),
    ),
    (
        "customer-support",
        "Customer Support",
        "Answers for customers: their orders, their bills, their balances.",
        ("CUSTOMER_SUPPORT",),
    ),
    (
        "read-only",
        "Read Only",
        "Sees everything the firm does and changes none of it.",
        ("VIEWER",),
    ),
)


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
    # No role holds a designation-only code, custom roles included; a row
    # written before the rule is retired rather than left promising a power.
    designation_only = {
        permissions[code].id for code in DESIGNATION_ONLY_PERMISSION_CODES
    }
    for (_, permission_id), assignment in assignments.items():
        if permission_id in designation_only and not assignment.is_deleted:
            assignment.is_deleted = True
            assignment.deleted_at = utc_now()
    _seed_user_templates(session, roles)


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


def _seed_user_templates(session: Session, roles: dict[str, Role]) -> None:
    """Create the platform job templates, and restore any that were retired.

    Idempotent and additive, like the rest of this seeder. An existing
    template's **bundle** is reconciled but its name and description are left
    alone: those are what a firm reads, and a platform upgrade quietly renaming
    a template somebody has been using for a year is worse than a stale name.
    """
    existing = {
        template.code: template
        for template in session.scalars(
            select(UserTemplate).where(UserTemplate.firm_id.is_(None))
        )
    }
    for code, name, description, role_codes in SYSTEM_USER_TEMPLATES:
        template = existing.get(code)
        if template is None:
            template = UserTemplate(
                code=code,
                name=name,
                description=description,
                firm_id=None,
                is_active=True,
                is_system=True,
            )
            session.add(template)
            session.flush()
        elif template.is_deleted:
            template.is_deleted = False
            template.deleted_at = None
            template.deleted_by = None
        wanted = {roles[role_code].id for role_code in role_codes}
        held = {row.role_id: row for row in template.template_roles}
        for role_id, row in held.items():
            if role_id in wanted and row.is_deleted:
                row.is_deleted, row.deleted_at, row.deleted_by = False, None, None
        for role_id in wanted - set(held):
            session.add(UserTemplateRole(template_id=template.id, role_id=role_id))
