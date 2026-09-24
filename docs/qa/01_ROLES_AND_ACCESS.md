# Roles and access

Part of the QA test suite in `docs/qa/`. What each job template may reach,
computed on 2026-09-25 from the application's own rules: the role seed
(`backend/app/identity/system_seed.py`) and the desktop's screen catalogue and
visibility filter. Regenerate rather than hand-edit.

**How to test a job.** Hire one user per job with *Administration → Users →
New*, naming the job in **Job template**. Sign in as each and check three
things, recording one result per job:

1. **The sidebar offers exactly the screens listed** for that job, no more and
   no fewer. A business profile can hide a whole module (for example batches
   on a profile that does not track them); note any such difference.
2. **Actions.** On each screen, write buttons appear only where the job holds
   a matching code. A screen marked *none beyond viewing* offers no New, Edit,
   Delete, Approve or Cancel, or offers them disabled with a reason.
3. **The server agrees.** Where a button is offered but the job lacks the code,
   the action is refused with *You do not have permission to perform this
   action.* A hidden button is not a control; a refused request is.

The *Codes held in this area* column lists the job's permission codes that
share the screen's area, other than viewing it. A code names one action, and
the area is broad: `SALES_INVOICE_CREATE` on the Quotations row means the job
may raise invoices, not quotations. Check each button against the code that
names it.

## Summary

| Job template | Roles | Screens offered |
| --- | --- | --- |
| Firm Administrator | FIRM_ADMIN | 87 |
| Firm Manager | FIRM_MANAGER | 81 |
| Counter Sales | CASHIER, BILLING_EXECUTIVE | 10 |
| Field Sales | SALES_EXECUTIVE | 17 |
| Sales Manager | SALES_MANAGER | 26 |
| Warehouse | INVENTORY_MANAGER | 14 |
| Purchasing | PURCHASE_EXECUTIVE | 9 |
| Purchase Manager | PURCHASE_MANAGER | 9 |
| Accounts | ACCOUNTANT | 21 |
| Customer Support | CUSTOMER_SUPPORT | 3 |
| Read Only | VIEWER | 76 |

## R01. Firm Administrator

Roles: `FIRM_ADMIN`. 164 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Administration | Users | `USER_CREATE`, `USER_DELETE`, `USER_UPDATE` | Not run | |
| Administration | Roles | `ROLE_ASSIGN`, `ROLE_CREATE`, `ROLE_DELETE`, `ROLE_UPDATE` | Not run | |
| Administration | Permissions | `PERMISSION_ASSIGN` | Not run | |
| Administration | User Templates | `ROLE_ASSIGN`, `ROLE_CREATE`, `ROLE_DELETE`, `ROLE_UPDATE` | Not run | |
| Administration | Numbering Series | `SETTINGS_UPDATE` | Not run | |
| Administration | Tax Configuration | `TAX_CREATE`, `TAX_DELETE`, `TAX_EXPORT`, `TAX_IMPORT`, `TAX_MANAGE_SETTINGS`, `TAX_RESTORE`, `TAX_RULE_CREATE`, `TAX_RULE_DELETE`, `TAX_RULE_RESTORE`, `TAX_RULE_UPDATE`, `TAX_SIMULATE`, `TAX_UPDATE` | Not run | |
| Administration | Tax Rules | `TAX_RULE_CREATE`, `TAX_RULE_DELETE`, `TAX_RULE_RESTORE`, `TAX_RULE_UPDATE` | Not run | |
| Administration | Rule Simulator | `TAX_SIMULATE` | Not run | |
| Administration | Execution Log | `TAX_RULE_CREATE`, `TAX_RULE_DELETE`, `TAX_RULE_RESTORE`, `TAX_RULE_UPDATE` | Not run | |
| Administration | Settings | `TAX_MANAGE_SETTINGS` | Not run | |
| Administration | Units of Measure | `UOM_EXPORT`, `UOM_IMPORT`, `UOM_MANAGE` | Not run | |
| Administration | UOM Groups | `UOM_EXPORT`, `UOM_IMPORT`, `UOM_MANAGE` | Not run | |
| Administration | Packaging Types | `PACKAGING_MANAGE` | Not run | |
| Administration | Packaging Levels | `PACKAGING_MANAGE` | Not run | |
| Administration | Conversion Rules | `CONVERSION_RULE_MANAGE` | Not run | |
| Administration | Industry Templates | `UOM_EXPORT`, `UOM_IMPORT`, `UOM_MANAGE` | Not run | |
| Masters | Customers | `CUSTOMER_CREATE`, `CUSTOMER_DELETE`, `CUSTOMER_EXPORT`, `CUSTOMER_IMPORT`, `CUSTOMER_MANAGE_SETTINGS`, `CUSTOMER_RESTORE`, `CUSTOMER_UPDATE` | Not run | |
| Masters | Statements | `CUSTOMER_CREATE`, `CUSTOMER_DELETE`, `CUSTOMER_EXPORT`, `CUSTOMER_IMPORT`, `CUSTOMER_MANAGE_SETTINGS`, `CUSTOMER_RESTORE`, `CUSTOMER_UPDATE` | Not run | |
| Masters | Loyalty | `LOYALTY_MANAGE`, `LOYALTY_MANAGE_SETTINGS` | Not run | |
| Masters | Products | `PRODUCT_ATTRIBUTE_MANAGE`, `PRODUCT_CREATE`, `PRODUCT_DELETE`, `PRODUCT_EXPORT`, `PRODUCT_IMPORT`, `PRODUCT_PRICING_MANAGE`, `PRODUCT_RESTORE`, `PRODUCT_TAX_MANAGE`, `PRODUCT_UPDATE`, `PRODUCT_VIEW_COST_PRICE` | Not run | |
| Masters | Vendors | `VENDOR_CREATE`, `VENDOR_DELETE`, `VENDOR_EXPORT`, `VENDOR_IMPORT`, `VENDOR_MANAGE_BANK_DETAILS`, `VENDOR_MANAGE_CATEGORIES`, `VENDOR_RESTORE`, `VENDOR_UPDATE`, `VENDOR_VIEW_FINANCIAL_DETAILS` | Not run | |
| Masters | Vendor Categories | `VENDOR_CREATE`, `VENDOR_DELETE`, `VENDOR_EXPORT`, `VENDOR_IMPORT`, `VENDOR_MANAGE_BANK_DETAILS`, `VENDOR_MANAGE_CATEGORIES`, `VENDOR_RESTORE`, `VENDOR_UPDATE`, `VENDOR_VIEW_FINANCIAL_DETAILS` | Not run | |
| Masters | Vendor Types | `VENDOR_CREATE`, `VENDOR_DELETE`, `VENDOR_EXPORT`, `VENDOR_IMPORT`, `VENDOR_MANAGE_BANK_DETAILS`, `VENDOR_MANAGE_CATEGORIES`, `VENDOR_RESTORE`, `VENDOR_UPDATE`, `VENDOR_VIEW_FINANCIAL_DETAILS` | Not run | |
| Masters | Branches | `BRANCH_CREATE`, `BRANCH_DELETE`, `BRANCH_RESTORE`, `BRANCH_UPDATE`, `BRANCH_WAREHOUSE_EXPORT`, `BRANCH_WAREHOUSE_IMPORT` | Not run | |
| Masters | Warehouses | `WAREHOUSE_CREATE`, `WAREHOUSE_DELETE`, `WAREHOUSE_RESTORE`, `WAREHOUSE_UPDATE` | Not run | |
| Masters | Storage Areas | `STORAGE_AREA_MANAGE` | Not run | |
| Masters | Warehouse Types | `WAREHOUSE_CREATE`, `WAREHOUSE_DELETE`, `WAREHOUSE_RESTORE`, `WAREHOUSE_UPDATE` | Not run | |
| Masters | Branch Types | `BRANCH_CREATE`, `BRANCH_DELETE`, `BRANCH_RESTORE`, `BRANCH_UPDATE`, `BRANCH_WAREHOUSE_EXPORT`, `BRANCH_WAREHOUSE_IMPORT` | Not run | |
| Masters | Settings | `BRANCH_CREATE`, `BRANCH_DELETE`, `BRANCH_RESTORE`, `BRANCH_UPDATE`, `BRANCH_WAREHOUSE_EXPORT`, `BRANCH_WAREHOUSE_IMPORT`, `WAREHOUSE_CREATE`, `WAREHOUSE_DELETE`, `WAREHOUSE_RESTORE`, `WAREHOUSE_UPDATE` | Not run | |
| Masters | Financial Years | `FINANCIAL_YEAR_CLOSE`, `FINANCIAL_YEAR_CREATE`, `FINANCIAL_YEAR_REOPEN` | Not run | |
| Sales | Geography | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Price Lists | `PRICE_LIST_MANAGE` | Not run | |
| Sales | Promotions | `PROMOTION_MANAGE` | Not run | |
| Sales | Commission | `COMMISSION_MANAGE`, `COMMISSION_PAY` | Not run | |
| Sales | Targets | `SALES_TARGET_MANAGE` | Not run | |
| Sales | Proforma | `PROFORMA_MANAGE` | Not run | |
| Sales | Credit Notes | `CREDIT_NOTE_APPROVE`, `CREDIT_NOTE_MANAGE` | Not run | |
| Sales | E-Invoice | `EINVOICE_MANAGE` | Not run | |
| Sales | GST Returns | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Sales | TCS | `TCS_MANAGE` | Not run | |
| Sales | Route Types | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Beat Plans | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Call Lists | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Coverage | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Route Builder | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Places | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Quotations | (the module itself) | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Sales Orders | (the module itself) | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Delivery Notes | Delivery Notes | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Sales Invoices | Sales Invoices | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Sales Returns | (the module itself) | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Purchases | Dashboard | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Purchase Orders | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Analytics | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Settings | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchase Invoices | (the module itself) | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchase Returns | (the module itself) | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Goods Receipts | Receipts | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Inventory | Inventory | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Transactions | none beyond viewing | Not run | |
| Inventory | Stock Ledger | none beyond viewing | Not run | |
| Inventory | Opening Stock | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Physical Count | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Stock Summary | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Stock Search | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Import | `INVENTORY_IMPORT` | Not run | |
| Inventory | Export | `INVENTORY_EXPORT` | Not run | |
| Inventory | Settings | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Batches | `BATCH_CREATE`, `BATCH_DELETE`, `BATCH_UPDATE` | Not run | |
| Inventory | Lots | `BATCH_CREATE`, `BATCH_DELETE`, `BATCH_UPDATE` | Not run | |
| Inventory | Serial Numbers | `SERIAL_CREATE`, `SERIAL_DELETE`, `SERIAL_UPDATE` | Not run | |
| Inventory | Expiry Monitor | `BATCH_CREATE`, `BATCH_DELETE`, `BATCH_UPDATE` | Not run | |
| Finance | Chart of Accounts | `ACCOUNT_MANAGE` | Not run | |
| Finance | Control Accounts | `ACCOUNT_MANAGE` | Not run | |
| Finance | Cost Centres | `ACCOUNT_MANAGE` | Not run | |
| Finance | Profit Centres | `ACCOUNT_MANAGE` | Not run | |
| Finance | Journal Entries | `JOURNAL_CREATE`, `JOURNAL_POST`, `JOURNAL_REVERSE` | Not run | |
| Finance | Receipts | `RECEIPT_CREATE` | Not run | |
| Finance | Payments | `PAYMENT_CREATE` | Not run | |
| Finance | Refunds | `ACCOUNT_MANAGE` | Not run | |
| Finance | Ledgers | none beyond viewing | Not run | |
| Finance | Trial Balance | none beyond viewing | Not run | |
| Finance | Profit & Loss | none beyond viewing | Not run | |
| Finance | Balance Sheet | none beyond viewing | Not run | |
| Reports | Operational Reports | `CREDIT_NOTE_APPROVE`, `CREDIT_NOTE_MANAGE`, `LOYALTY_MANAGE`, `LOYALTY_MANAGE_SETTINGS`, `PROFORMA_MANAGE`, `PROMOTION_MANAGE`, `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE`, `REPORT_EXPORT`, `REPORT_PRINT`, `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Reports | Financial Reports | `CREDIT_NOTE_APPROVE`, `CREDIT_NOTE_MANAGE`, `LOYALTY_MANAGE`, `LOYALTY_MANAGE_SETTINGS`, `PROFORMA_MANAGE`, `PROMOTION_MANAGE`, `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE`, `REPORT_EXPORT`, `REPORT_PRINT`, `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Settings | Audit Logs | none beyond viewing | Not run | |

**Not offered:** Licensing. Check each is absent from the sidebar.

## R02. Firm Manager

Roles: `FIRM_MANAGER`. 150 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Administration | Tax Configuration | `TAX_CREATE`, `TAX_DELETE`, `TAX_EXPORT`, `TAX_IMPORT`, `TAX_MANAGE_SETTINGS`, `TAX_RESTORE`, `TAX_RULE_CREATE`, `TAX_RULE_DELETE`, `TAX_RULE_RESTORE`, `TAX_RULE_UPDATE`, `TAX_SIMULATE`, `TAX_UPDATE` | Not run | |
| Administration | Tax Rules | `TAX_RULE_CREATE`, `TAX_RULE_DELETE`, `TAX_RULE_RESTORE`, `TAX_RULE_UPDATE` | Not run | |
| Administration | Rule Simulator | `TAX_SIMULATE` | Not run | |
| Administration | Execution Log | `TAX_RULE_CREATE`, `TAX_RULE_DELETE`, `TAX_RULE_RESTORE`, `TAX_RULE_UPDATE` | Not run | |
| Administration | Settings | `TAX_MANAGE_SETTINGS` | Not run | |
| Administration | Units of Measure | `UOM_EXPORT`, `UOM_IMPORT`, `UOM_MANAGE` | Not run | |
| Administration | UOM Groups | `UOM_EXPORT`, `UOM_IMPORT`, `UOM_MANAGE` | Not run | |
| Administration | Packaging Types | `PACKAGING_MANAGE` | Not run | |
| Administration | Packaging Levels | `PACKAGING_MANAGE` | Not run | |
| Administration | Conversion Rules | `CONVERSION_RULE_MANAGE` | Not run | |
| Administration | Industry Templates | `UOM_EXPORT`, `UOM_IMPORT`, `UOM_MANAGE` | Not run | |
| Masters | Customers | `CUSTOMER_CREATE`, `CUSTOMER_DELETE`, `CUSTOMER_EXPORT`, `CUSTOMER_IMPORT`, `CUSTOMER_MANAGE_SETTINGS`, `CUSTOMER_RESTORE`, `CUSTOMER_UPDATE` | Not run | |
| Masters | Statements | `CUSTOMER_CREATE`, `CUSTOMER_DELETE`, `CUSTOMER_EXPORT`, `CUSTOMER_IMPORT`, `CUSTOMER_MANAGE_SETTINGS`, `CUSTOMER_RESTORE`, `CUSTOMER_UPDATE` | Not run | |
| Masters | Loyalty | `LOYALTY_MANAGE`, `LOYALTY_MANAGE_SETTINGS` | Not run | |
| Masters | Products | `PRODUCT_ATTRIBUTE_MANAGE`, `PRODUCT_CREATE`, `PRODUCT_DELETE`, `PRODUCT_EXPORT`, `PRODUCT_IMPORT`, `PRODUCT_PRICING_MANAGE`, `PRODUCT_RESTORE`, `PRODUCT_TAX_MANAGE`, `PRODUCT_UPDATE`, `PRODUCT_VIEW_COST_PRICE` | Not run | |
| Masters | Vendors | `VENDOR_CREATE`, `VENDOR_DELETE`, `VENDOR_EXPORT`, `VENDOR_IMPORT`, `VENDOR_MANAGE_BANK_DETAILS`, `VENDOR_MANAGE_CATEGORIES`, `VENDOR_RESTORE`, `VENDOR_UPDATE`, `VENDOR_VIEW_FINANCIAL_DETAILS` | Not run | |
| Masters | Vendor Categories | `VENDOR_CREATE`, `VENDOR_DELETE`, `VENDOR_EXPORT`, `VENDOR_IMPORT`, `VENDOR_MANAGE_BANK_DETAILS`, `VENDOR_MANAGE_CATEGORIES`, `VENDOR_RESTORE`, `VENDOR_UPDATE`, `VENDOR_VIEW_FINANCIAL_DETAILS` | Not run | |
| Masters | Vendor Types | `VENDOR_CREATE`, `VENDOR_DELETE`, `VENDOR_EXPORT`, `VENDOR_IMPORT`, `VENDOR_MANAGE_BANK_DETAILS`, `VENDOR_MANAGE_CATEGORIES`, `VENDOR_RESTORE`, `VENDOR_UPDATE`, `VENDOR_VIEW_FINANCIAL_DETAILS` | Not run | |
| Masters | Branches | `BRANCH_CREATE`, `BRANCH_DELETE`, `BRANCH_RESTORE`, `BRANCH_UPDATE`, `BRANCH_WAREHOUSE_EXPORT`, `BRANCH_WAREHOUSE_IMPORT` | Not run | |
| Masters | Warehouses | `WAREHOUSE_CREATE`, `WAREHOUSE_DELETE`, `WAREHOUSE_RESTORE`, `WAREHOUSE_UPDATE` | Not run | |
| Masters | Storage Areas | `STORAGE_AREA_MANAGE` | Not run | |
| Masters | Warehouse Types | `WAREHOUSE_CREATE`, `WAREHOUSE_DELETE`, `WAREHOUSE_RESTORE`, `WAREHOUSE_UPDATE` | Not run | |
| Masters | Branch Types | `BRANCH_CREATE`, `BRANCH_DELETE`, `BRANCH_RESTORE`, `BRANCH_UPDATE`, `BRANCH_WAREHOUSE_EXPORT`, `BRANCH_WAREHOUSE_IMPORT` | Not run | |
| Masters | Settings | `BRANCH_CREATE`, `BRANCH_DELETE`, `BRANCH_RESTORE`, `BRANCH_UPDATE`, `BRANCH_WAREHOUSE_EXPORT`, `BRANCH_WAREHOUSE_IMPORT`, `WAREHOUSE_CREATE`, `WAREHOUSE_DELETE`, `WAREHOUSE_RESTORE`, `WAREHOUSE_UPDATE` | Not run | |
| Masters | Financial Years | `FINANCIAL_YEAR_CLOSE`, `FINANCIAL_YEAR_CREATE`, `FINANCIAL_YEAR_REOPEN` | Not run | |
| Sales | Geography | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Price Lists | `PRICE_LIST_MANAGE` | Not run | |
| Sales | Promotions | `PROMOTION_MANAGE` | Not run | |
| Sales | Commission | `COMMISSION_MANAGE`, `COMMISSION_PAY` | Not run | |
| Sales | Targets | `SALES_TARGET_MANAGE` | Not run | |
| Sales | Proforma | `PROFORMA_MANAGE` | Not run | |
| Sales | Credit Notes | `CREDIT_NOTE_APPROVE`, `CREDIT_NOTE_MANAGE` | Not run | |
| Sales | E-Invoice | `EINVOICE_MANAGE` | Not run | |
| Sales | GST Returns | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Sales | TCS | `TCS_MANAGE` | Not run | |
| Sales | Route Types | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Beat Plans | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Call Lists | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Coverage | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Route Builder | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Sales | Places | `TERRITORY_ASSIGN_CUSTOMERS`, `TERRITORY_ASSIGN_SALESMEN`, `TERRITORY_CREATE`, `TERRITORY_DELETE`, `TERRITORY_EXPORT`, `TERRITORY_IMPORT`, `TERRITORY_RESTORE`, `TERRITORY_UPDATE` | Not run | |
| Quotations | (the module itself) | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Sales Orders | (the module itself) | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Delivery Notes | Delivery Notes | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Sales Invoices | Sales Invoices | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Sales Returns | (the module itself) | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Purchases | Dashboard | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Purchase Orders | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Analytics | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Settings | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchase Invoices | (the module itself) | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchase Returns | (the module itself) | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Goods Receipts | Receipts | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Inventory | Inventory | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Transactions | none beyond viewing | Not run | |
| Inventory | Stock Ledger | none beyond viewing | Not run | |
| Inventory | Opening Stock | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Physical Count | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Stock Summary | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Stock Search | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Import | `INVENTORY_IMPORT` | Not run | |
| Inventory | Export | `INVENTORY_EXPORT` | Not run | |
| Inventory | Settings | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Batches | `BATCH_CREATE`, `BATCH_DELETE`, `BATCH_UPDATE` | Not run | |
| Inventory | Lots | `BATCH_CREATE`, `BATCH_DELETE`, `BATCH_UPDATE` | Not run | |
| Inventory | Serial Numbers | `SERIAL_CREATE`, `SERIAL_DELETE`, `SERIAL_UPDATE` | Not run | |
| Inventory | Expiry Monitor | `BATCH_CREATE`, `BATCH_DELETE`, `BATCH_UPDATE` | Not run | |
| Finance | Chart of Accounts | `ACCOUNT_MANAGE` | Not run | |
| Finance | Control Accounts | `ACCOUNT_MANAGE` | Not run | |
| Finance | Cost Centres | `ACCOUNT_MANAGE` | Not run | |
| Finance | Profit Centres | `ACCOUNT_MANAGE` | Not run | |
| Finance | Journal Entries | `JOURNAL_CREATE`, `JOURNAL_POST`, `JOURNAL_REVERSE` | Not run | |
| Finance | Receipts | `RECEIPT_CREATE` | Not run | |
| Finance | Payments | `PAYMENT_CREATE` | Not run | |
| Finance | Refunds | `ACCOUNT_MANAGE` | Not run | |
| Finance | Ledgers | none beyond viewing | Not run | |
| Finance | Trial Balance | none beyond viewing | Not run | |
| Finance | Profit & Loss | none beyond viewing | Not run | |
| Finance | Balance Sheet | none beyond viewing | Not run | |
| Reports | Operational Reports | `CREDIT_NOTE_APPROVE`, `CREDIT_NOTE_MANAGE`, `LOYALTY_MANAGE`, `LOYALTY_MANAGE_SETTINGS`, `PROFORMA_MANAGE`, `PROMOTION_MANAGE`, `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE`, `REPORT_EXPORT`, `REPORT_PRINT`, `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |
| Reports | Financial Reports | `CREDIT_NOTE_APPROVE`, `CREDIT_NOTE_MANAGE`, `LOYALTY_MANAGE`, `LOYALTY_MANAGE_SETTINGS`, `PROFORMA_MANAGE`, `PROMOTION_MANAGE`, `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE`, `REPORT_EXPORT`, `REPORT_PRINT`, `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_MANAGE_SETTINGS`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_TARGET_MANAGE`, `SALES_UPDATE` | Not run | |

**Not offered:** Licensing, Settings. Check each is absent from the sidebar.

## R03. Counter Sales

Roles: `CASHIER`, `BILLING_EXECUTIVE`. 6 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Sales | GST Returns | `SALES_INVOICE_CREATE` | Not run | |
| Quotations | (the module itself) | `SALES_INVOICE_CREATE` | Not run | |
| Sales Orders | (the module itself) | `SALES_INVOICE_CREATE` | Not run | |
| Delivery Notes | Delivery Notes | `SALES_INVOICE_CREATE` | Not run | |
| Sales Invoices | Sales Invoices | `SALES_INVOICE_CREATE` | Not run | |
| Sales Returns | (the module itself) | `SALES_INVOICE_CREATE` | Not run | |
| Finance | Receipts | `RECEIPT_CREATE` | Not run | |
| Finance | Payments | `PAYMENT_CREATE` | Not run | |
| Reports | Operational Reports | `SALES_INVOICE_CREATE` | Not run | |
| Reports | Financial Reports | `SALES_INVOICE_CREATE` | Not run | |

**Not offered:** Administration, Masters, Purchases, Purchase Invoices, Purchase Returns, Goods Receipts, Inventory, Licensing, Settings. Check each is absent from the sidebar.

## R04. Field Sales

Roles: `SALES_EXECUTIVE`. 6 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Masters | Customers | none beyond viewing | Not run | |
| Masters | Statements | none beyond viewing | Not run | |
| Sales | Geography | none beyond viewing | Not run | |
| Sales | GST Returns | `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE` | Not run | |
| Sales | Route Types | none beyond viewing | Not run | |
| Sales | Beat Plans | none beyond viewing | Not run | |
| Sales | Call Lists | none beyond viewing | Not run | |
| Sales | Coverage | none beyond viewing | Not run | |
| Sales | Route Builder | none beyond viewing | Not run | |
| Sales | Places | none beyond viewing | Not run | |
| Quotations | (the module itself) | `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE` | Not run | |
| Sales Orders | (the module itself) | `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE` | Not run | |
| Delivery Notes | Delivery Notes | `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE` | Not run | |
| Sales Invoices | Sales Invoices | `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE` | Not run | |
| Sales Returns | (the module itself) | `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE` | Not run | |
| Reports | Operational Reports | `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE` | Not run | |
| Reports | Financial Reports | `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE` | Not run | |

**Not offered:** Administration, Purchases, Purchase Invoices, Purchase Returns, Goods Receipts, Inventory, Finance, Licensing, Settings. Check each is absent from the sidebar.

## R05. Sales Manager

Roles: `SALES_MANAGER`. 35 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Masters | Customers | `CUSTOMER_CREATE`, `CUSTOMER_DELETE`, `CUSTOMER_EXPORT`, `CUSTOMER_IMPORT`, `CUSTOMER_RESTORE`, `CUSTOMER_UPDATE` | Not run | |
| Masters | Statements | `CUSTOMER_CREATE`, `CUSTOMER_DELETE`, `CUSTOMER_EXPORT`, `CUSTOMER_IMPORT`, `CUSTOMER_RESTORE`, `CUSTOMER_UPDATE` | Not run | |
| Masters | Loyalty | `LOYALTY_MANAGE` | Not run | |
| Masters | Products | none beyond viewing | Not run | |
| Sales | Geography | `TERRITORY_ASSIGN_CUSTOMERS` | Not run | |
| Sales | Promotions | none beyond viewing | Not run | |
| Sales | Commission | none beyond viewing | Not run | |
| Sales | Targets | none beyond viewing | Not run | |
| Sales | Proforma | `PROFORMA_MANAGE` | Not run | |
| Sales | Credit Notes | `CREDIT_NOTE_MANAGE` | Not run | |
| Sales | E-Invoice | none beyond viewing | Not run | |
| Sales | GST Returns | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_UPDATE` | Not run | |
| Sales | TCS | none beyond viewing | Not run | |
| Sales | Route Types | `TERRITORY_ASSIGN_CUSTOMERS` | Not run | |
| Sales | Beat Plans | `TERRITORY_ASSIGN_CUSTOMERS` | Not run | |
| Sales | Call Lists | `TERRITORY_ASSIGN_CUSTOMERS` | Not run | |
| Sales | Coverage | `TERRITORY_ASSIGN_CUSTOMERS` | Not run | |
| Sales | Route Builder | `TERRITORY_ASSIGN_CUSTOMERS` | Not run | |
| Sales | Places | `TERRITORY_ASSIGN_CUSTOMERS` | Not run | |
| Quotations | (the module itself) | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_UPDATE` | Not run | |
| Sales Orders | (the module itself) | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_UPDATE` | Not run | |
| Delivery Notes | Delivery Notes | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_UPDATE` | Not run | |
| Sales Invoices | Sales Invoices | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_UPDATE` | Not run | |
| Sales Returns | (the module itself) | `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_UPDATE` | Not run | |
| Reports | Operational Reports | `CREDIT_NOTE_MANAGE`, `LOYALTY_MANAGE`, `PROFORMA_MANAGE`, `REPORT_EXPORT`, `REPORT_PRINT`, `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_UPDATE` | Not run | |
| Reports | Financial Reports | `CREDIT_NOTE_MANAGE`, `LOYALTY_MANAGE`, `PROFORMA_MANAGE`, `REPORT_EXPORT`, `REPORT_PRINT`, `SALES_APPROVE`, `SALES_CANCEL`, `SALES_CREATE`, `SALES_EXPORT`, `SALES_IMPORT`, `SALES_INVOICE_CREATE`, `SALES_ORDER_CREATE`, `SALES_QUOTATION_CREATE`, `SALES_RETURN`, `SALES_UPDATE` | Not run | |

**Not offered:** Administration, Purchases, Purchase Invoices, Purchase Returns, Goods Receipts, Inventory, Finance, Licensing, Settings. Check each is absent from the sidebar.

## R06. Warehouse

Roles: `INVENTORY_MANAGER`. 16 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Inventory | Inventory | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Transactions | none beyond viewing | Not run | |
| Inventory | Stock Ledger | none beyond viewing | Not run | |
| Inventory | Opening Stock | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Physical Count | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Stock Summary | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Stock Search | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Import | `INVENTORY_IMPORT` | Not run | |
| Inventory | Export | `INVENTORY_EXPORT` | Not run | |
| Inventory | Settings | `INVENTORY_ADJUST`, `INVENTORY_EXPORT`, `INVENTORY_IMPORT` | Not run | |
| Inventory | Batches | `BATCH_CREATE`, `BATCH_DELETE`, `BATCH_UPDATE` | Not run | |
| Inventory | Lots | `BATCH_CREATE`, `BATCH_DELETE`, `BATCH_UPDATE` | Not run | |
| Inventory | Serial Numbers | `SERIAL_CREATE`, `SERIAL_DELETE`, `SERIAL_UPDATE` | Not run | |
| Inventory | Expiry Monitor | `BATCH_CREATE`, `BATCH_DELETE`, `BATCH_UPDATE` | Not run | |

**Not offered:** Administration, Masters, Sales, Quotations, Sales Orders, Delivery Notes, Sales Invoices, Sales Returns, Purchases, Purchase Invoices, Purchase Returns, Goods Receipts, Finance, Reports, Licensing, Settings. Check each is absent from the sidebar.

## R07. Purchasing

Roles: `PURCHASE_EXECUTIVE`. 8 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Purchases | Dashboard | `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Purchase Orders | `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Analytics | `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Settings | `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchase Invoices | (the module itself) | `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchase Returns | (the module itself) | `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Goods Receipts | Receipts | `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Reports | Operational Reports | `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Reports | Financial Reports | `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |

**Not offered:** Administration, Masters, Sales, Quotations, Sales Orders, Delivery Notes, Sales Invoices, Sales Returns, Inventory, Finance, Licensing, Settings. Check each is absent from the sidebar.

## R08. Purchase Manager

Roles: `PURCHASE_MANAGER`. 9 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Purchases | Dashboard | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Purchase Orders | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Analytics | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchases | Settings | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchase Invoices | (the module itself) | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Purchase Returns | (the module itself) | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Goods Receipts | Receipts | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Reports | Operational Reports | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |
| Reports | Financial Reports | `PURCHASE_APPROVE`, `PURCHASE_CANCEL`, `PURCHASE_CREATE`, `PURCHASE_DELETE`, `PURCHASE_EXPORT`, `PURCHASE_IMPORT`, `PURCHASE_RESTORE`, `PURCHASE_UPDATE` | Not run | |

**Not offered:** Administration, Masters, Sales, Quotations, Sales Orders, Delivery Notes, Sales Invoices, Sales Returns, Inventory, Finance, Licensing, Settings. Check each is absent from the sidebar.

## R09. Accounts

Roles: `ACCOUNTANT`. 25 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Masters | Customers | `CUSTOMER_MANAGE_SETTINGS` | Not run | |
| Masters | Statements | `CUSTOMER_MANAGE_SETTINGS` | Not run | |
| Masters | Products | none beyond viewing | Not run | |
| Masters | Vendors | `VENDOR_VIEW_FINANCIAL_DETAILS` | Not run | |
| Masters | Vendor Categories | `VENDOR_VIEW_FINANCIAL_DETAILS` | Not run | |
| Masters | Vendor Types | `VENDOR_VIEW_FINANCIAL_DETAILS` | Not run | |
| Sales | Commission | `COMMISSION_MANAGE`, `COMMISSION_PAY` | Not run | |
| Finance | Chart of Accounts | `ACCOUNT_MANAGE` | Not run | |
| Finance | Control Accounts | `ACCOUNT_MANAGE` | Not run | |
| Finance | Cost Centres | `ACCOUNT_MANAGE` | Not run | |
| Finance | Profit Centres | `ACCOUNT_MANAGE` | Not run | |
| Finance | Journal Entries | `JOURNAL_CREATE`, `JOURNAL_POST`, `JOURNAL_REVERSE` | Not run | |
| Finance | Receipts | `RECEIPT_CREATE` | Not run | |
| Finance | Payments | `PAYMENT_CREATE` | Not run | |
| Finance | Refunds | `ACCOUNT_MANAGE` | Not run | |
| Finance | Ledgers | none beyond viewing | Not run | |
| Finance | Trial Balance | none beyond viewing | Not run | |
| Finance | Profit & Loss | none beyond viewing | Not run | |
| Finance | Balance Sheet | none beyond viewing | Not run | |
| Reports | Operational Reports | `REPORT_EXPORT`, `REPORT_PRINT` | Not run | |
| Reports | Financial Reports | `REPORT_EXPORT`, `REPORT_PRINT` | Not run | |

**Not offered:** Administration, Quotations, Sales Orders, Delivery Notes, Sales Invoices, Sales Returns, Purchases, Purchase Invoices, Purchase Returns, Goods Receipts, Inventory, Licensing, Settings. Check each is absent from the sidebar.

## R10. Customer Support

Roles: `CUSTOMER_SUPPORT`. 3 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Masters | Customers | `CUSTOMER_UPDATE` | Not run | |
| Masters | Statements | `CUSTOMER_UPDATE` | Not run | |
| Masters | Products | none beyond viewing | Not run | |

**Not offered:** Administration, Sales, Quotations, Sales Orders, Delivery Notes, Sales Invoices, Sales Returns, Purchases, Purchase Invoices, Purchase Returns, Goods Receipts, Inventory, Finance, Reports, Licensing, Settings. Check each is absent from the sidebar.

## R11. Read Only

Roles: `VIEWER`. 37 permission codes.

| Module | Screen | Codes held in this area | Result | Notes |
| --- | --- | --- | --- | --- |
| Administration | Firms | none beyond viewing | Not run | |
| Administration | Tax Configuration | none beyond viewing | Not run | |
| Administration | Tax Rules | none beyond viewing | Not run | |
| Administration | Execution Log | none beyond viewing | Not run | |
| Administration | Units of Measure | none beyond viewing | Not run | |
| Administration | UOM Groups | none beyond viewing | Not run | |
| Administration | Industry Templates | none beyond viewing | Not run | |
| Masters | Customers | none beyond viewing | Not run | |
| Masters | Statements | none beyond viewing | Not run | |
| Masters | Loyalty | none beyond viewing | Not run | |
| Masters | Products | none beyond viewing | Not run | |
| Masters | Vendors | none beyond viewing | Not run | |
| Masters | Vendor Categories | none beyond viewing | Not run | |
| Masters | Vendor Types | none beyond viewing | Not run | |
| Masters | Branches | none beyond viewing | Not run | |
| Masters | Warehouses | none beyond viewing | Not run | |
| Masters | Warehouse Types | none beyond viewing | Not run | |
| Masters | Branch Types | none beyond viewing | Not run | |
| Masters | Settings | none beyond viewing | Not run | |
| Masters | Financial Years | none beyond viewing | Not run | |
| Masters | Firm Settings | none beyond viewing | Not run | |
| Sales | Geography | none beyond viewing | Not run | |
| Sales | Price Lists | none beyond viewing | Not run | |
| Sales | Promotions | none beyond viewing | Not run | |
| Sales | Commission | none beyond viewing | Not run | |
| Sales | Targets | none beyond viewing | Not run | |
| Sales | Proforma | none beyond viewing | Not run | |
| Sales | Credit Notes | none beyond viewing | Not run | |
| Sales | E-Invoice | none beyond viewing | Not run | |
| Sales | GST Returns | none beyond viewing | Not run | |
| Sales | TCS | none beyond viewing | Not run | |
| Sales | Route Types | none beyond viewing | Not run | |
| Sales | Beat Plans | none beyond viewing | Not run | |
| Sales | Call Lists | none beyond viewing | Not run | |
| Sales | Coverage | none beyond viewing | Not run | |
| Sales | Route Builder | none beyond viewing | Not run | |
| Sales | Places | none beyond viewing | Not run | |
| Quotations | (the module itself) | none beyond viewing | Not run | |
| Sales Orders | (the module itself) | none beyond viewing | Not run | |
| Delivery Notes | Delivery Notes | none beyond viewing | Not run | |
| Sales Invoices | Sales Invoices | none beyond viewing | Not run | |
| Sales Returns | (the module itself) | none beyond viewing | Not run | |
| Purchases | Dashboard | none beyond viewing | Not run | |
| Purchases | Purchase Orders | none beyond viewing | Not run | |
| Purchases | Analytics | none beyond viewing | Not run | |
| Purchases | Settings | none beyond viewing | Not run | |
| Purchase Invoices | (the module itself) | none beyond viewing | Not run | |
| Purchase Returns | (the module itself) | none beyond viewing | Not run | |
| Goods Receipts | Receipts | none beyond viewing | Not run | |
| Inventory | Inventory | none beyond viewing | Not run | |
| Inventory | Transactions | none beyond viewing | Not run | |
| Inventory | Stock Ledger | none beyond viewing | Not run | |
| Inventory | Opening Stock | none beyond viewing | Not run | |
| Inventory | Physical Count | none beyond viewing | Not run | |
| Inventory | Stock Summary | none beyond viewing | Not run | |
| Inventory | Stock Search | none beyond viewing | Not run | |
| Inventory | Settings | none beyond viewing | Not run | |
| Inventory | Batches | none beyond viewing | Not run | |
| Inventory | Lots | none beyond viewing | Not run | |
| Inventory | Serial Numbers | none beyond viewing | Not run | |
| Inventory | Expiry Monitor | none beyond viewing | Not run | |
| Finance | Chart of Accounts | none beyond viewing | Not run | |
| Finance | Control Accounts | none beyond viewing | Not run | |
| Finance | Cost Centres | none beyond viewing | Not run | |
| Finance | Profit Centres | none beyond viewing | Not run | |
| Finance | Journal Entries | none beyond viewing | Not run | |
| Finance | Receipts | none beyond viewing | Not run | |
| Finance | Payments | none beyond viewing | Not run | |
| Finance | Refunds | none beyond viewing | Not run | |
| Finance | Ledgers | none beyond viewing | Not run | |
| Finance | Trial Balance | none beyond viewing | Not run | |
| Finance | Profit & Loss | none beyond viewing | Not run | |
| Finance | Balance Sheet | none beyond viewing | Not run | |
| Reports | Operational Reports | none beyond viewing | Not run | |
| Reports | Financial Reports | none beyond viewing | Not run | |
| Settings | Diagnostics | none beyond viewing | Not run | |

**Not offered:** Licensing. Check each is absent from the sidebar.

## The platform administrator

`platform-admin@agency.local` starts on **Platform** every time, with
Dashboard, Administration (including Firms, Business Profiles, Feature
Management, Module Configuration, Attribute Definitions, Mandatory
Attributes, Profile Assignment and User-Firm Assignments, which no firm role
reaches), Settings and Licensing. Choosing a firm in the switcher opens that
firm's modules. Test cases for this account are in
`02_SIGN_IN_AND_ACCOUNTS.md` and `04_FIRMS_AND_CONFIGURATION.md`.
