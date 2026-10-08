# Table catalogue — every table, where it lives, what it holds

**334 tables**, of which **17** live only in the platform store.
Generated from the ORM metadata, not written by hand:

```powershell
uv run python scripts/dump_table_catalogue.py    # rewrites this file in place
```

Re-run it rather than editing the tables below. A hand-kept list of two hundred
rows is a list that rots, and `CLAUDE.md` carries the scars of several.

## The three stores, and why a table's home decides what a query can do

A firm's data lives in one of three arrangements, chosen when the firm is
created and never changed (see
[`TENANCY_AND_STORES.md`](TENANCY_AND_STORES.md)):

| Mode | Where the firm's tables are |
| --- | --- |
| `SHARED` | The shared database, schema `firm_shared`, alongside other shared firms |
| `SCHEMA` | Its own schema in the shared database |
| `DATABASE` | Its own database, possibly on another server |

**Two consequences run through every row below.**

*A platform table exists once.* `users`, `firms`, `user_firms` and the rest of
the platform list live **only** in the platform schema. A firm-owned service
that needs one opens the platform store deliberately, with `platform_reader()`
from `app/common/firm_metadata.py` -- a tenant session raises `UndefinedTable`
for them. `_PLATFORM_TABLES` in `app/core/tenancy/lifecycle.py` is the
authority on which they are, and "has no firm column" is **not** a test:
`geo_countries` has none and lives in every store.

*A firm table exists once per store.* Every firm-owned table is created in
`firm_shared` and in each dedicated schema or database, so the same table name
holds different rows in each. Nothing joins across them, which is why a
cross-firm view iterates stores rather than writing one query -- and why
`audit_logs` cannot answer "everything that happened" from one place.

## How to read the columns

- **Store** -- `platform` or `firm store`, as above.
- **Holds** -- the model's own docstring. Where it is blank, the model has no
  docstring; that is a gap in the code, not in this document.
- **Points at** -- the tables this one declares a foreign key to **in the
  ORM**. Read one line of it with care: nearly every firm-owned table points
  at `firms`, and `firms` lives only in the platform store. The column is
  real everywhere; the **constraint** is created only where the target table
  exists, because a migration declares such a reference only when
  `sa.inspect(op.get_bind()).has_table(...)` finds it (`_external_fk` in
  `20260809_0042`). So in `firm_shared` and in every dedicated store, `firm_id`
  is an unenforced reference by design -- the database cannot check it, and
  nothing may rely on it doing so.

¹ marks a table extending `BaseEntity`: UUID `id`, created/updated actor and
timestamp, `version` for optimistic concurrency, and `is_deleted` /
`deleted_at` soft delete. Repositories exclude soft-deleted rows unless asked.
`audit_logs` is the exception to everything -- append-only, enforced by a
trigger each schema owns its own copy of.


### `app/approvals`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `approval_decisions` | firm store ¹ | A sign-off or a rejection of one document at one level. |  |
| `approval_rules` | firm store ¹ | One role's sign-off at one level, for documents from an amount up. |  |

### `app/bank_reconciliation`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `bank_reconciliation_matches` | firm store ¹ | One posting on the bank account, accounted for by one statement line. | `bank_statement_lines`, `gl_postings` |
| `bank_statement_lines` | firm store ¹ | One line of a statement: money in or out of the account on a day. | `bank_statements` |
| `bank_statements` | firm store ¹ | One statement file imported against one bank account. | `ledger_accounts` |

### `app/batch_serial`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `batch_sale_settings` | firm store ¹ | One firm's rules for which batches go out on a sale (backlog 79 row 6). |  |
| `batches` | firm store ¹ | Track one batch/lot of a product across the warehouse. | `firms`, `products`, `warehouses`, `branches`, `vendors`, `warehouse_storage_nodes` |
| `document_line_serials` | firm store ¹ | Name one serialised unit a document line moves. | `serial_numbers` |
| `lots` | firm store ¹ | Track one production lot across manufacturing steps. | `firms`, `products`, `warehouses`, `branches` |
| `serial_numbers` | firm store ¹ | Track one serialized unit through its full lifecycle. | `firms`, `products`, `inventories`, `warehouses`, `branches`, `batches` |

### `app/bill_of_entry`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `bill_of_entry_allocations` | firm store ¹ | The share of a line's duty one receipt line carried into stock. | `bills_of_entry`, `bill_of_entry_lines`, `goods_receipts`, `goods_receipt_lines`, `inventory_transactions` |
| `bill_of_entry_documents` | firm store ¹ | A purchase invoice or goods receipt the Bill of Entry belongs to. | `bills_of_entry` |
| `bill_of_entry_lines` | firm store ¹ | One item on a Bill of Entry and the duty assessed on it. | `bills_of_entry`, `products` |
| `bills_of_entry` | firm store ¹ | One Bill of Entry: the duty customs assessed on imported goods. | `firms`, `vendors`, `branches`, `journal_entries` |

### `app/branches`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `branch_attribute_values` | firm store ¹ | Store one configurable attribute value for a branch. | `branches`, `firms`, `attribute_definitions` |
| `branch_types` | firm store ¹ | Persist reusable branch type masters per firm. | `firms` |
| `branches` | firm store ¹ | Represent one physical operational branch owned by a firm. | `firms`, `business_profiles`, `branch_types`, `users`, `geo_countries`, `geo_states`, `geo_districts`, `geo_cities`, `geo_postal_codes`, `geo_localities` |
| `user_work_defaults` | firm store ¹ | One person's usual branch and warehouse in one firm. | `branches`, `warehouses` |
| `warehouse_attribute_values` | firm store ¹ | Store one configurable attribute value for a warehouse. | `warehouses`, `firms`, `attribute_definitions` |
| `warehouse_storage_nodes` | firm store ¹ | Represent storage hierarchy nodes (area/rack/shelf/bin/receiving). | `warehouses` |
| `warehouse_types` | firm store ¹ | Persist reusable warehouse type masters per firm. | `firms` |
| `warehouses` | firm store ¹ | Represent one physical warehouse mapped to a branch. | `firms`, `branches`, `warehouse_types`, `users`, `business_profiles`, `geo_countries`, `geo_states`, `geo_districts`, `geo_cities`, `geo_postal_codes`, `geo_localities` |

### `app/branding`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `agency_branding` | platform ¹ | The agency that bought the product: its name, tagline and logo. |  |

### `app/business`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `attribute_definitions` | firm store ¹ | Define one configurable field that extends a record, shared or a firm's own. |  |
| `business_features` | firm store ¹ | Define one configurable framework feature flag. |  |
| `business_modules` | firm store ¹ | Define one configurable module in the ERP workspace. |  |
| `business_profiles` | firm store ¹ | Define one industry/business operating profile. |  |
| `category_attribute_rules` | firm store ¹ | Say which records a field belongs to, and where it is compulsory. | `goods_types`, `customer_groups`, `vendor_types`, `attribute_definitions` |
| `delivery_note_attribute_values` | firm store ¹ | Store one custom field value for a delivery note. | `delivery_notes`, `firms`, `attribute_definitions` |
| `firm_attribute_switches` | firm store ¹ | One firm's on or off for a field of the shared catalogue. | `attribute_definitions` |
| `firm_business_profiles` | firm store ¹ | Assign exactly one active business profile to a firm. | `firms`, `business_profiles` |
| `profile_features` | firm store ¹ | Store per-profile feature enablement and optional configuration. | `business_profiles`, `business_features` |
| `profile_modules` | firm store ¹ | Store per-profile module visibility and workflow configuration. | `business_profiles`, `business_modules` |
| `purchase_invoice_attribute_values` | firm store ¹ | Store one custom field value for a purchase invoice. | `purchase_invoices`, `firms`, `attribute_definitions` |
| `purchase_order_attribute_values` | firm store ¹ | Store one custom field value for a purchase order. | `purchase_orders`, `firms`, `attribute_definitions` |
| `quotation_attribute_values` | firm store ¹ | Store one custom field value for a quotation. | `sales_quotations`, `firms`, `attribute_definitions` |
| `sales_invoice_attribute_values` | firm store ¹ | Store one custom field value for a sales invoice. | `sales_invoices`, `firms`, `attribute_definitions` |
| `sales_order_attribute_values` | firm store ¹ | Store one custom field value for a sales order. | `sales_orders`, `firms`, `attribute_definitions` |

### `app/collections`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `payment_promises` | firm store ¹ | Store one promise to pay, against a bill or the customer's account. | `customers`, `sales_invoices` |

### `app/commission`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `commission_clawbacks` | firm store ¹ | What one payout recovered from one earlier, paid payout. | `commission_payouts` |
| `commission_payouts` | firm store ¹ | One period's commission for one salesman, from accrual to payment. | `users`, `ledger_accounts`, `journal_entries` |
| `commission_rule_slabs` | firm store ¹ | One rung of a rule's ladder: a band of value, and its rate. | `commission_rules` |
| `commission_rules` | firm store ¹ | Store one flat commission percentage, scoped and effective-dated. | `users`, `products`, `product_categories` |

### `app/common`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `audit_logs` | firm store | Record a mutation without coupling auditing to a business domain. |  |

### `app/contra`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `contra_vouchers` | firm store ¹ | One movement of money between two of the firm's own accounts. | `ledger_accounts`, `journal_entries` |

### `app/counter_shifts`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `counter_shifts` | firm store ¹ | Store one cashier's shift: the float, and the count it closed on. | `branches`, `ledger_accounts`, `journal_entries` |

### `app/credit_note`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `credit_note_lines` | firm store ¹ | One invoice line being credited, in part or in whole. | `credit_notes`, `sales_invoice_lines`, `products` |
| `credit_notes` | firm store ¹ | One credit against one invoice, with the tax it reverses. | `customers`, `branches`, `sales_invoices`, `journal_entries` |

### `app/customer_debit_note`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `customer_debit_note_lines` | firm store ¹ | One invoice line being charged more. | `customer_debit_notes`, `sales_invoice_lines`, `products` |
| `customer_debit_notes` | firm store ¹ | One charge against one invoice, with the tax it adds. | `customers`, `branches`, `sales_invoices`, `journal_entries` |

### `app/customer_rebates`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `customer_rebate_agreements` | firm store ¹ | One customer's, or one customer group's, rebate over one period. | `customers`, `customer_groups`, `journal_entries` |
| `customer_rebate_slabs` | firm store ¹ | One step: from this turnover, this rate on all of it. | `customer_rebate_agreements` |

### `app/customers`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `credit_control_settings` | firm store ¹ | Store one firm's credit-limit policy. | `firms` |
| `customer_addresses` | firm store ¹ | Represent one reusable customer address. | `customers`, `geo_countries`, `geo_states`, `geo_districts`, `geo_cities`, `geo_postal_codes`, `geo_localities` |
| `customer_attachments` | firm store ¹ | One file kept on file for a customer -- KYC, an agreement, a licence. | `firms`, `customers` |
| `customer_attribute_values` | firm store ¹ | Store one configurable attribute value for a customer. | `customers`, `firms`, `attribute_definitions` |
| `customer_bank_accounts` | firm store ¹ | One bank account a customer is paid into. | `firms`, `customers` |
| `customer_contacts` | firm store ¹ | Represent one customer contact person. | `customers` |
| `customer_groups` | firm store ¹ | A commercial segment a firm sells to: Retailer, Wholesaler, Institution. | `firms`, `price_levels` |
| `customer_opening_bills` | firm store ¹ | Store one bill a customer owed on the firm's first day here. | `customers`, `journal_entries` |
| `customer_receivable_transactions` | firm store ¹ | Represent one immutable receivable movement for a customer. | `firms`, `customers`, `journal_entries` |
| `customers` | firm store ¹ | Represent one customer master owned by a firm. | `firms`, `customer_groups`, `price_levels`, `vendors` |

### `app/debit_note`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `debit_note_lines` | firm store ¹ | One bill line being claimed against, in part or in whole. | `debit_notes`, `purchase_invoice_lines`, `products` |
| `debit_notes` | firm store ¹ | One claim against one supplier bill, with the input tax it reverses. | `vendors`, `branches`, `purchase_invoices`, `journal_entries` |

### `app/delivery_note`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `delivery_note_attachments` | firm store ¹ | Store delivery note attachments. | `delivery_notes`, `firms` |
| `delivery_note_line_batches` | firm store ¹ | Which batches one delivery line takes, as a person chose them (79). | `delivery_note_lines`, `batches` |
| `delivery_note_lines` | firm store ¹ | Store one delivery note line. | `delivery_notes`, `firms`, `sales_order_lines`, `products`, `uoms`, `packaging_types`, `tax_profiles`, `warehouses`, `warehouse_storage_nodes`, `batches` |
| `delivery_note_notes` | firm store ¹ | Store delivery note notes. | `delivery_notes`, `firms` |
| `delivery_notes` | firm store ¹ | Store one delivery note header. | `firms`, `sales_orders`, `customers`, `branches`, `warehouses`, `business_profiles`, `users`, `territory_route_profiles`, `sales_territories`, `transporters` |
| `transporters` | firm store ¹ | One carrier: who it is and what an e-way bill asks about it. |  |

### `app/diagnostics`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `error_reports` | platform | One failure, reported by a desktop client or raised by this server. |  |

### `app/document_files`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `document_file_contents` | firm store | The bytes of one :class:`DocumentFile`, read only to download it. | `document_files` |
| `document_files` | firm store ¹ | One uploaded file kept with a purchase or a sales document. | `purchase_invoices`, `goods_receipts`, `sales_quotations`, `sales_orders`, `delivery_notes`, `sales_invoices`, `sales_returns` |

### `app/document_framework`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `document_headers` | firm store ¹ | Store a reusable enterprise document header. | `firms`, `document_type_definitions` |
| `document_lifecycle_events` | firm store ¹ | Record one append-only lifecycle event for a document instance. | `firms`, `document_type_definitions` |
| `document_lines` | firm store ¹ | Store one reusable document line. | `firms`, `document_headers` |
| `document_number_sequences` | firm store ¹ | Track the next number for one numbering rule in one scope. | `firms`, `document_numbering_rules` |
| `document_numbering_rules` | firm store ¹ | Define configurable numbering behavior for one document family. | `firms`, `document_type_definitions` |
| `document_print_templates` | firm store ¹ | Store what one firm prints around a document of one type. |  |
| `document_state_definitions` | firm store ¹ | Define configurable lifecycle states for one document family. | `firms`, `document_type_definitions` |
| `document_totals` | firm store ¹ | Store reusable totals for one document. | `firms`, `document_headers` |
| `document_type_definitions` | firm store ¹ | Define one reusable document family. | `firms` |

### `app/einvoice`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `einvoice_registrations` | firm store ¹ | One document, as the Invoice Registration Portal knows it. | `sales_invoices`, `credit_notes`, `customer_debit_notes`, `sales_returns` |
| `einvoice_settings` | firm store ¹ | How one firm registers its e-invoices (decision A42). |  |
| `eway_bills` | firm store ¹ | One consignment's e-way bill, raised against an invoice or a challan. | `sales_invoices`, `delivery_notes` |

### `app/enquiry`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `enquiries` | firm store ¹ | A buyer's enquiry before any quotation (decision A133). | `firms`, `branches`, `customers`, `sales_quotations` |
| `enquiry_follow_ups` | firm store ¹ | One contact with the buyer and what was agreed. | `enquiries` |
| `enquiry_lines` | firm store ¹ | One thing asked for: a product, or words until it is matched to one. | `enquiries`, `products` |

### `app/expenses`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `expenses` | firm store ¹ | Store one amount the firm spent, and the journal that records it. | `firms`, `ledger_accounts`, `journal_entries` |

### `app/finance`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `account_groups` | firm store ¹ | Group ledger accounts for classification and report rollups. | `firms` |
| `accounting_periods` | firm store ¹ | Represent one posting period inside a financial year. | `firms`, `financial_years` |
| `ageing_settings` | firm store ¹ | The ageing bands a firm reads what it is owed and owes in (ACC-6). |  |
| `bank_account_details` | firm store ¹ | One bank ledger account's bank, number and IFSC. | `firms`, `ledger_accounts` |
| `cost_centers` | firm store ¹ | Represent a cost centre used to attribute expenditure. | `firms` |
| `customer_ledgers` | firm store ¹ | Hold derived receivable totals for one customer and period. | `firms`, `customers`, `accounting_periods` |
| `financial_years` | firm store ¹ | Represent one fiscal year owned by a firm. | `firms` |
| `firm_control_accounts` | firm store ¹ | Map a document-posting purpose onto the account a firm posts it to. | `firms`, `ledger_accounts` |
| `gl_postings` | firm store ¹ | Record one journal line as it was posted to the general ledger. | `firms`, `journal_entries`, `journal_lines`, `ledger_accounts`, `accounting_periods` |
| `journal_entries` | firm store ¹ | Represent one balanced double-entry journal voucher. | `firms`, `journal_types`, `voucher_types`, `accounting_periods` |
| `journal_lines` | firm store ¹ | Represent one debit or credit leg of a journal entry. | `journal_entries`, `ledger_accounts`, `cost_centers`, `profit_centers` |
| `journal_types` | firm store ¹ | Classify journals such as sales, purchase, or general. | `firms` |
| `ledger_accounts` | firm store ¹ | Represent one general-ledger account in the chart of accounts. | `firms`, `account_groups` |
| `ledger_attachments` | firm store ¹ | One file backing a journal entry or a settlement -- never both. | `journal_entries`, `settlements` |
| `ledger_balances` | firm store ¹ | Hold the derived balance of one ledger account for one period. | `firms`, `ledger_accounts`, `accounting_periods` |
| `period_close_settings` | firm store ¹ | What a firm does when a month it closes still has work in it (ACC-5). |  |
| `profit_centers` | firm store ¹ | Represent a profit centre used to attribute revenue. | `firms` |
| `tally_ledger_mappings` | firm store ¹ | What one of our accounts is called in the CA's Tally, and its group. | `ledger_accounts` |
| `tds_194q_settings` | firm store ¹ | One firm's 194Q switch, threshold and rates. |  |
| `tds_challan_items` | firm store ¹ | One deduction a challan paid: a payment's, an expense's or a bill's. | `tds_challans`, `settlements`, `expenses`, `purchase_invoices` |
| `tds_challans` | firm store ¹ | One deposit of TDS under one section. | `ledger_accounts`, `journal_entries` |
| `tds_section_settings` | firm store ¹ | One firm's switch, thresholds and rates for 194C or 194J. |  |
| `vendor_ledgers` | firm store ¹ | Hold derived payable totals for one vendor and period. | `firms`, `vendors`, `accounting_periods` |
| `voucher_types` | firm store ¹ | Classify vouchers such as invoice, receipt, or payment. | `firms` |

### `app/firms`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `firm_storage_mappings` | platform ¹ | Persist tenant storage routing details for a firm. | `firms` |
| `firms` | platform ¹ | Represent an organization available to one or more platform users. |  |

### `app/fixed_assets`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `asset_classes` | firm store ¹ | A kind of asset and how it is depreciated in each book. | `firms`, `ledger_accounts` |
| `depreciation_run_lines` | firm store ¹ | What one run charged one asset, and over which days. | `depreciation_runs`, `fixed_assets`, `asset_classes` |
| `depreciation_runs` | firm store ¹ | One posting of Companies Act depreciation for a period. | `firms`, `journal_entries` |
| `fixed_assets` | firm store ¹ | One asset on the register. | `firms`, `asset_classes`, `vendors`, `branches`, `journal_entries` |

### `app/goods_receipt`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `goods_receipt_attachments` | firm store ¹ | Store goods receipt attachments. | `goods_receipts`, `firms` |
| `goods_receipt_line_serials` | firm store ¹ | One serial number typed on a receipt line (PG-10). | `goods_receipts`, `goods_receipt_lines` |
| `goods_receipt_lines` | firm store ¹ | Store one goods receipt line. | `goods_receipts`, `firms`, `purchase_order_lines`, `products`, `tax_profiles`, `packaging_types`, `uoms`, `warehouses`, `warehouse_storage_nodes`, `batches`, `inventory_transactions` |
| `goods_receipt_notes` | firm store ¹ | Store goods receipt notes. | `goods_receipts`, `firms` |
| `goods_receipts` | firm store ¹ | Store one goods receipt note header. | `firms`, `purchase_orders`, `vendors`, `branches`, `warehouses`, `users` |

### `app/gst_returns`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `gst_cash_deposits` | firm store ¹ | One PMT-06 challan paid for month 1 or 2 of a quarter. | `ledger_accounts`, `journal_entries` |
| `gst_payments` | firm store ¹ | A month's GST liability, the credit set off, the cash paid by challan. | `ledger_accounts`, `journal_entries` |
| `gst_return_filings` | firm store ¹ | One return, for one month, filed on the portal. |  |
| `gst_return_snapshots` | firm store ¹ | The GSTR-1 a filing reported, as it stood when marked filed (GST-6). | `gst_return_filings` |
| `gstr2b_documents` | firm store ¹ | One supplier document in a month's GSTR-2B, and what it matched. | `gstr2b_imports` |
| `gstr2b_imports` | firm store ¹ | One month's GSTR-2B, imported once; a re-import replaces it. |  |
| `itc_common_reversals` | firm store ¹ | One rule 42 reversal: a period's, or a year's true-up. | `journal_entries` |
| `itc_reversals` | firm store ¹ | One reversal of a bill's credit, or one reclaim of it. | `purchase_invoices`, `journal_entries` |

### `app/identity`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `login_history` | platform ¹ | Audit successful, failed, and locked login attempts. | `users` |
| `password_history` | platform ¹ | Retain prior password hashes for future password-reuse checks. | `users` |
| `permissions` | platform ¹ | Represent one configurable capability granted through roles. |  |
| `platform_admins` | platform ¹ | Designate a user as a platform-level administrator without a role name. | `users` |
| `refresh_tokens` | platform ¹ | Store a hashed, revocable refresh-token secret. | `users` |
| `role_permissions` | platform ¹ | Associate a role with a configurable permission. | `roles`, `permissions` |
| `roles` | platform ¹ | Represent a configurable collection of permissions. | `firms` |
| `user_firms` | platform ¹ | Associate a user with a firm and designate its primary active firm. | `users`, `firms` |
| `user_preferences` | platform ¹ | Persist versioned, user-owned desktop and workspace preferences. | `users`, `firms` |
| `user_roles` | platform ¹ | Associate a user with a configurable role. | `users`, `roles`, `firms` |
| `user_template_roles` | platform ¹ | One role in a template's bundle. | `user_templates`, `roles` |
| `user_templates` | platform ¹ | A named bundle of roles for one job, so a firm hires by naming the job. | `firms` |
| `users` | platform ¹ | Represent an interactive platform user. |  |

### `app/imports`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `import_mappings` | firm store ¹ | How one firm reads one kind of file from one source, by name. |  |

### `app/inventory`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `count_plans` | firm store ¹ | What to count, where, and how often (STK-6, decision A117). | `firms` |
| `inventories` | firm store ¹ | Persist one firm-scoped inventory projection per product location. | `firms`, `branches`, `warehouses`, `warehouse_storage_nodes`, `products`, `batches`, `business_profiles`, `uoms` |
| `inventory_transactions` | firm store ¹ | Persist one immutable inventory movement event. | `inventories`, `firms`, `branches`, `warehouses`, `warehouse_storage_nodes`, `products`, `business_profiles`, `uoms`, `batches`, `lots`, `serial_numbers` |
| `opening_stock_batches` | firm store ¹ | Persist a draft or posted opening-stock document. | `firms`, `branches`, `warehouses` |
| `opening_stock_lines` | firm store ¹ | Persist one opening-stock line before or after posting. | `opening_stock_batches`, `products`, `warehouse_storage_nodes`, `business_profiles`, `uoms`, `batches`, `inventory_transactions` |
| `physical_count_lines` | firm store ¹ | Store one stock row's count on one sheet. | `firms`, `physical_counts` |
| `physical_counts` | firm store ¹ | Store one count sheet for one warehouse. | `firms` |
| `product_valuations` | firm store ¹ | Track the moving weighted-average cost of a product for a firm. | `firms`, `products` |
| `repack_lines` | firm store ¹ | One product consumed or produced, and the movement that did it. | `repacks`, `products`, `batches`, `inventory_transactions` |
| `repacks` | firm store ¹ | Goods consumed and goods produced in one warehouse (decision A114). | `firms`, `branches`, `warehouses` |
| `role_stock_adjustment_limits` | firm store ¹ | The largest stock adjustment one role may post, in one firm (A108). |  |
| `stock_adjustment_reasons` | firm store ¹ | One reason stock left, or was corrected, tied to the account it costs. | `firms`, `ledger_accounts` |
| `stock_adjustment_requests` | firm store ¹ | An adjustment or write-off above its author's limit, waiting (A108). | `firms`, `products`, `warehouses`, `inventory_transactions` |
| `stock_attachments` | firm store ¹ | Store one file backing a movement or a count sheet -- never both. | `firms`, `inventory_transactions`, `physical_counts` |
| `stock_ledger_entries` | firm store ¹ | Persist one immutable stock-ledger row per inventory transaction. | `inventory_transactions`, `inventories`, `batches`, `firms`, `branches`, `warehouses`, `warehouse_storage_nodes`, `products`, `business_profiles`, `uoms` |
| `stock_transfer_lines` | firm store ¹ | One product sent, and what became of it at the other end. | `stock_transfers`, `products`, `batches`, `inventory_transactions` |
| `stock_transfers` | firm store ¹ | Goods sent from one warehouse to another, in two steps (decision A126). | `firms`, `branches`, `warehouses` |

### `app/landed_costs`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `landed_cost_allocations` | firm store ¹ | The share of a voucher one receipt line carried. | `landed_cost_vouchers`, `goods_receipts`, `goods_receipt_lines`, `products`, `inventory_transactions` |
| `landed_cost_charges` | firm store ¹ | One charge on a voucher: what it was for and whose bill it was. | `landed_cost_vouchers`, `vendors` |
| `landed_cost_vouchers` | firm store ¹ | Freight, loading or clearing spread over completed receipts (A129). | `firms`, `journal_entries` |

### `app/loyalty`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `loyalty_entries` | firm store ¹ | One movement of a customer's credit. | `customers`, `sales_invoices`, `journal_entries` |
| `loyalty_settings` | firm store ¹ | One firm's scheme. |  |

### `app/messaging`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `messaging_channel_configs` | firm store ¹ | One firm's account with one provider, for one channel. |  |
| `messaging_event_configs` | firm store ¹ | Whether one event goes out on one channel, and with which template. |  |
| `messaging_outbox` | firm store ¹ | One message: asked for, queued, sent, failed or skipped. |  |
| `messaging_settings` | firm store ¹ | One firm's master switch and reminder schedule. |  |

### `app/notifications`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `notification_reads` | firm store ¹ | One person's mark that they have seen one notification. |  |

### `app/party_adjustments`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `party_adjustment_allocations` | firm store ¹ | How much of one adjustment came off one bill. | `party_adjustments`, `sales_invoices`, `purchase_invoices`, `customer_opening_bills`, `vendor_opening_bills` |
| `party_adjustment_settings` | firm store ¹ | A firm's limits on adjusting balances. A firm with no row has defaults. |  |
| `party_adjustments` | firm store ¹ | One balance moved without money: write-off, write-back or set-off. | `customers`, `vendors`, `journal_entries`, `supplier_rebate_agreements`, `principal_claims`, `customer_rebate_agreements` |

### `app/pricing`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `price_levels` | firm store ¹ | One named level a firm prices by. |  |
| `price_list_items` | firm store ¹ | One product's rate on one list. | `price_lists`, `products` |
| `price_lists` | firm store ¹ | One named arrangement, scoped to who it applies to and when. | `customers`, `sales_territories`, `vendors` |
| `product_price_levels` | firm store ¹ | One product's price at one level. | `products`, `price_levels` |

### `app/principal_claims`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `principal_claim_lines` | firm store ¹ | One thing claimed: a redemption, free goods, a write-off or a return line. | `principal_claims`, `products` |
| `principal_claim_receipts` | firm store ¹ | Money the principal paid against a claim. | `principal_claims`, `ledger_accounts`, `journal_entries` |
| `principal_claims` | firm store ¹ | What one principal owes the firm for one period (decision A128). | `firms`, `principals`, `vendors`, `journal_entries` |

### `app/products`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `brands` | firm store ¹ | A brand the firm sells, under the principal that owns it. | `firms`, `principals` |
| `firm_goods_types` | firm store ¹ | One goods type a firm trades in, with its defaults for a new product. | `goods_types` |
| `goods_types` | firm store ¹ | One line of goods and the tracking its products start with. |  |
| `principals` | firm store ¹ | The company whose agency the firm holds -- a distributor's principal. | `firms`, `vendors` |
| `product_attribute_values` | firm store ¹ | Store one configurable attribute value for a product. | `products`, `firms`, `attribute_definitions` |
| `product_categories` | firm store ¹ | Represent a hierarchical firm category tree for products. | `firms`, `trade_licence_types`, `goods_types` |
| `product_kit_components` | firm store ¹ | One component of a kit, and how many go into one kit (decision A134). | `firms`, `products` |
| `product_media` | firm store ¹ | Store product images, attachments, and reference documents. | `firms`, `products` |
| `product_price_revisions` | firm store ¹ | New rates for a product from a date, kept with every earlier one. | `firms`, `products` |
| `products` | firm store ¹ | Represent one configurable product core master row. | `firms`, `product_categories`, `goods_types`, `unit_sets`, `trade_licence_types`, `brands`, `uoms`, `vendors` |

### `app/proforma`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `proforma_invoice_lines` | firm store ¹ | One line of a proforma, snapshotted from the order line it states. | `proforma_invoices`, `products` |
| `proforma_invoices` | firm store ¹ | One statement of what a sales order will be billed at. | `customers`, `branches`, `sales_orders` |

### `app/promotions`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `promotion_actions` | firm store ¹ | Store one benefit a promotion gives when it matches. | `promotions` |
| `promotion_conditions` | firm store ¹ | Store one condition a promotion is matched on. | `promotions` |
| `promotion_coupons` | firm store ¹ | A code a customer presents to claim an offer. | `promotions` |
| `promotion_execution_logs` | firm store ¹ | Store what the engine was asked, what it considered, and what it gave. |  |
| `promotion_redemptions` | firm store ¹ | One claim on an offer, and what it was worth. | `promotions`, `promotion_coupons` |
| `promotions` | firm store ¹ | Store one versioned promotion evaluated while a document is priced. | `principals` |

### `app/purchase`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `purchase_attachments` | firm store ¹ | Store purchase document attachments. | `purchase_orders`, `firms` |
| `purchase_budgets` | firm store ¹ | What a firm means to spend on buying in one month (BUY-14, A106). | `firms`, `branches`, `product_categories` |
| `purchase_delivery_schedules` | firm store ¹ | Store delivery schedules per order line. | `purchase_order_lines`, `firms` |
| `purchase_notes` | firm store ¹ | Store notes linked to purchase documents. | `purchase_orders`, `firms` |
| `purchase_order_history` | firm store ¹ | Store immutable history events for purchase orders. | `purchase_orders`, `firms` |
| `purchase_order_lines` | firm store ¹ | Store one purchase order line item. | `purchase_orders`, `firms`, `products`, `uoms`, `tax_profiles`, `warehouses`, `warehouse_storage_nodes` |
| `purchase_order_revisions` | firm store ¹ | One earlier version of an amended purchase order (BUY-8, A102). | `firms`, `purchase_orders` |
| `purchase_orders` | firm store ¹ | Store one enterprise purchase order header. | `firms`, `branches`, `warehouses`, `vendors`, `users`, `tax_profiles` |
| `purchase_requisition_lines` | firm store ¹ | One product asked for, and the order it went onto. | `purchase_requisitions`, `products`, `vendors`, `purchase_orders` |
| `purchase_requisitions` | firm store ¹ | A branch or storeman asking for goods (decision A109). | `firms`, `branches`, `warehouses` |
| `purchase_workflow_settings` | firm store ¹ | Store which buying stages one firm fills in by hand. | `firms`, `branches`, `warehouses` |
| `reorder_planning_settings` | firm store ¹ | How one firm decides what to reorder (backlog 69 row 12, decision A39). |  |
| `role_purchase_approval_limits` | firm store ¹ | The largest purchase order one role may approve, in one firm. |  |

### `app/purchase_invoice`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `purchase_invoice_accounting_events` | firm store ¹ | Store reusable accounting placeholder events. | `purchase_invoices`, `firms` |
| `purchase_invoice_attachments` | firm store ¹ | Store purchase invoice attachments. | `purchase_invoices`, `firms` |
| `purchase_invoice_line_taxes` | firm store ¹ | Store the tax components one bill line was actually charged. | `purchase_invoice_lines` |
| `purchase_invoice_lines` | firm store ¹ | Store one purchase invoice line. | `purchase_invoices`, `firms`, `products`, `tax_profiles`, `packaging_types`, `uoms`, `warehouses`, `warehouse_storage_nodes`, `asset_classes` |
| `purchase_invoice_notes` | firm store ¹ | Store purchase invoice notes. | `purchase_invoices`, `firms` |
| `purchase_invoice_sources` | firm store ¹ | Store supplier invoice source document references. | `purchase_invoices`, `firms`, `vendors`, `branches` |
| `purchase_invoices` | firm store ¹ | Store one supplier invoice header. | `firms`, `vendors`, `branches`, `business_profiles` |

### `app/purchase_return`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `purchase_return_accounting_events` | firm store ¹ | Store reusable accounting placeholder events. | `purchase_returns`, `firms` |
| `purchase_return_attachments` | firm store ¹ | Store purchase return attachments. | `purchase_returns`, `firms` |
| `purchase_return_bill_placements` | firm store ¹ | Record which supplier bill line a completed return line came off. | `purchase_returns`, `purchase_return_lines`, `firms`, `purchase_invoice_lines` |
| `purchase_return_lines` | firm store ¹ | Store one purchase return line. | `purchase_returns`, `firms`, `products`, `tax_profiles`, `packaging_types`, `uoms`, `warehouses`, `warehouse_storage_nodes`, `batches`, `inventory_transactions` |
| `purchase_return_notes` | firm store ¹ | Store purchase return notes. | `purchase_returns`, `firms` |
| `purchase_return_sources` | firm store ¹ | Store supplier return source document references. | `purchase_returns`, `firms`, `vendors`, `branches` |
| `purchase_returns` | firm store ¹ | Store one supplier return header. | `firms`, `vendors`, `branches`, `warehouses`, `business_profiles` |

### `app/quotation`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `sales_quotation_attachments` | firm store ¹ | Store quotation attachments. | `sales_quotations`, `firms` |
| `sales_quotation_lines` | firm store ¹ | Store one quotation line. | `sales_quotations`, `firms`, `products`, `uoms`, `packaging_types`, `tax_profiles`, `warehouses` |
| `sales_quotation_notes` | firm store ¹ | Store quotation notes. | `sales_quotations`, `firms` |
| `sales_quotations` | firm store ¹ | Store one quotation header. | `firms`, `customers`, `users`, `sales_territories`, `branches`, `warehouses`, `business_profiles` |

### `app/rate_contracts`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `rate_contract_lines` | firm store ¹ | One product on a contract, its agreed rate and how much was agreed. | `rate_contracts`, `products`, `uoms` |
| `rate_contracts` | firm store ¹ | An agreement with one supplier: these items, at these rates, for a period. | `firms`, `vendors` |

### `app/report_layouts`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `report_layouts` | firm store ¹ | One named layout of one report, kept by one person in one firm. |  |

### `app/rfq`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `rfq_lines` | firm store ¹ | One product asked about, and the quote chosen for it. | `rfqs`, `products`, `uoms` |
| `rfq_suppliers` | firm store ¹ | A supplier invited to quote, and the order raised on them. | `rfqs`, `vendors`, `purchase_orders` |
| `rfqs` | firm store ¹ | One request for quotation, sent to several suppliers. | `firms`, `branches`, `warehouses`, `purchase_requisitions` |
| `supplier_quotation_lines` | firm store ¹ | The rate a supplier quoted for one RFQ line. | `supplier_quotations`, `rfq_lines` |
| `supplier_quotations` | firm store ¹ | One supplier's answer to an RFQ: one per RFQ and supplier. | `rfqs`, `vendors` |

### `app/sales`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `address_masters` | firm store ¹ | Reusable multi-address storage for firm-owned entities. | `firms`, `geo_countries`, `geo_states`, `geo_districts`, `geo_cities`, `geo_postal_codes`, `geo_localities` |
| `geo_cities` | firm store ¹ | Reusable geographical master for cities. | `geo_districts` |
| `geo_countries` | firm store ¹ | Reusable geographical master for countries. |  |
| `geo_districts` | firm store ¹ | Reusable geographical master for districts. | `geo_states` |
| `geo_localities` | firm store ¹ | Reusable geographical master for areas/localities. | `geo_postal_codes` |
| `geo_postal_codes` | firm store ¹ | Reusable geographical master for postal codes. | `geo_cities` |
| `geo_states` | firm store ¹ | Reusable geographical master for states/provinces. | `geo_countries` |
| `sales_beat_plan_customer_stops` | firm store ¹ | Store one ordered outlet belonging to a beat plan. | `sales_beat_plans`, `customers` |
| `sales_beat_plans` | firm store ¹ | Store beat-planning templates without visit execution data. | `firms`, `business_profiles`, `sales_territories` |
| `sales_hierarchy_configs` | firm store ¹ | Store configurable hierarchy behavior for one firm. | `firms`, `business_profiles` |
| `sales_hierarchy_levels` | firm store ¹ | Store one configurable hierarchy level. | `sales_hierarchy_configs` |
| `sales_route_types` | firm store ¹ | Reusable route-type master for territory route profiles. | `firms` |
| `sales_territories` | firm store ¹ | Store one node in the configurable sales hierarchy tree. | `firms`, `business_profiles`, `sales_hierarchy_levels` |
| `territory_customer_assignments` | firm store ¹ | Assign one customer to one territory node. | `sales_territories`, `customers` |
| `territory_route_profiles` | firm store ¹ | Route-specific extension fields for territory nodes. | `sales_territories`, `sales_route_types`, `geo_cities`, `geo_postal_codes`, `geo_localities` |
| `territory_salesman_assignments` | firm store ¹ | Assign one salesperson user to one territory node. | `sales_territories`, `users` |
| `territory_working_days` | firm store ¹ | Working weekdays assigned to one route profile. | `territory_route_profiles` |

### `app/sales_invoice`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `sales_invoice_accounting_events` | firm store ¹ | Store accounting events generated by sales invoice lifecycle. | `sales_invoices`, `firms` |
| `sales_invoice_attachments` | firm store ¹ | Store sales invoice attachments. | `sales_invoices`, `firms` |
| `sales_invoice_charges` | firm store ¹ | One charge on a bill taxed at a rate of its own (backlog 87 #4, SG-4). | `sales_invoices`, `tax_profiles` |
| `sales_invoice_line_taxes` | firm store ¹ | Store the tax components one invoice line was actually charged. | `sales_invoice_lines` |
| `sales_invoice_lines` | firm store ¹ | Store one sales invoice line. | `sales_invoices`, `firms`, `products`, `tax_profiles`, `packaging_types`, `uoms`, `warehouses`, `warehouse_storage_nodes` |
| `sales_invoice_notes` | firm store ¹ | Store sales invoice notes. | `sales_invoices`, `firms` |
| `sales_invoice_sources` | firm store ¹ | Store customer invoice source document references. | `sales_invoices`, `firms`, `customers`, `branches` |
| `sales_invoice_tenders` | firm store ¹ | One way a counter bill was paid: cash, UPI or card (SEL-12, A90). | `sales_invoices` |
| `sales_invoices` | firm store ¹ | Store one customer invoice header. | `firms`, `customers`, `users`, `sales_territories`, `territory_route_profiles`, `branches`, `business_profiles`, `counter_shifts` |

### `app/sales_order`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `price_floor_settings` | firm store ¹ | One firm's policy on selling below cost or below a minimum price. |  |
| `role_discount_limits` | firm store ¹ | The largest discount one role may give on its own, in one firm. |  |
| `sales_order_attachments` | firm store ¹ | Store sales order attachments. | `sales_orders`, `firms` |
| `sales_order_lines` | firm store ¹ | Store one sales order line. | `sales_orders`, `firms`, `products`, `uoms`, `packaging_types`, `tax_profiles`, `warehouses`, `warehouse_storage_nodes`, `batches` |
| `sales_order_notes` | firm store ¹ | Store sales order notes. | `sales_orders`, `firms` |
| `sales_orders` | firm store ¹ | Store one sales order header. | `firms`, `customers`, `users`, `sales_territories`, `territory_route_profiles`, `branches`, `warehouses`, `business_profiles` |
| `sales_workflow_settings` | firm store ¹ | Store which sales stages one firm fills in by hand. | `firms`, `branches`, `warehouses` |

### `app/sales_return`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `sales_return_attachments` | firm store ¹ | Store sales return attachments. | `sales_returns`, `firms` |
| `sales_return_bill_placements` | firm store ¹ | Store which bill line a completed return line off a note took units from. | `sales_returns`, `sales_return_lines` |
| `sales_return_line_taxes` | firm store ¹ | Store the tax components one return line actually credited. | `sales_return_lines` |
| `sales_return_lines` | firm store ¹ | Store one customer return line. | `sales_returns`, `firms`, `products`, `tax_profiles`, `packaging_types`, `uoms`, `warehouses`, `warehouse_storage_nodes`, `batches`, `inventory_transactions` |
| `sales_return_notes` | firm store ¹ | Store sales return notes. | `sales_returns`, `firms` |
| `sales_return_sources` | firm store ¹ | Store the documents one return was raised against. | `sales_returns`, `firms`, `customers`, `branches` |
| `sales_returns` | firm store ¹ | Store one customer return header. | `firms`, `customers`, `branches`, `warehouses`, `users`, `sales_territories`, `business_profiles`, `journal_entries` |

### `app/sales_targets`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `sales_targets` | firm store ¹ | One expectation, for one period, of one salesman or round. | `users`, `sales_territories` |

### `app/settlements`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `cheque_layouts` | firm store ¹ | One bank account's printing offsets and A/c Payee choice. | `firms`, `ledger_accounts` |
| `customer_credit_applications` | firm store ¹ | Store how much of one return's or credit note's credit went where. | `customers` |
| `payment_run_lines` | firm store ¹ | One bill in a run, and the payment that settled it. | `payment_runs`, `vendors`, `settlements` |
| `payment_runs` | firm store ¹ | The bills chosen to be paid on one date (decision A110). | `firms` |
| `post_dated_cheques` | firm store ¹ | Store one cheque dated ahead, from a customer or to a supplier. | `customers`, `vendors`, `settlements`, `journal_entries` |
| `settlement_allocations` | firm store ¹ | Store how much of one settlement cleared one invoice. | `firms`, `settlements`, `sales_invoices`, `purchase_invoices`, `vendor_opening_bills`, `customer_opening_bills` |
| `settlements` | firm store ¹ | Store one receipt from a customer or payment to a vendor. | `firms`, `customers`, `vendors`, `ledger_accounts`, `sales_orders`, `journal_entries` |
| `supplier_credit_applications` | firm store ¹ | Store how much of one purchase return's supplier credit cleared one bill. | `vendors`, `purchase_returns`, `debit_notes`, `purchase_invoices`, `vendor_opening_bills` |
| `supplier_credit_refunds` | firm store ¹ | Money a supplier paid back against one return's credit (69 row 7). | `vendors`, `purchase_returns`, `debit_notes`, `ledger_accounts`, `journal_entries` |

### `app/supplier_rebates`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `supplier_rebate_agreements` | firm store ¹ | One supplier's rebate over one period. | `vendors`, `journal_entries` |
| `supplier_rebate_slabs` | firm store ¹ | One step: from this volume, this rate on all of it. | `supplier_rebate_agreements` |

### `app/supplier_schemes`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `supplier_schemes` | firm store ¹ | Buy ``buy_quantity`` of a product, get ``free_quantity`` free. | `firms`, `vendors`, `products` |

### `app/tax`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `gst_compliance_settings` | firm store ¹ | One firm's GST document policy (backlog 77 rows 1-2, decision A35). |  |
| `tax_components` | firm store ¹ | Store one configurable tax component for a tax system. | `firms`, `tax_systems` |
| `tax_country_mappings` | firm store ¹ | Store default tax system mapping per country and profile context. | `firms`, `geo_countries`, `business_profiles`, `tax_systems` |
| `tax_migration_mappings` | firm store ¹ | Store migration mapping from legacy tax definitions. | `firms`, `tax_profiles` |
| `tax_profile_attribute_values` | firm store ¹ | Store one configurable attribute value for a tax profile. | `tax_profiles`, `firms`, `attribute_definitions` |
| `tax_profile_components` | firm store ¹ | Store component composition and percentages for one tax profile. | `firms`, `tax_profiles`, `tax_components` |
| `tax_profiles` | firm store ¹ | Store one reusable tax profile applied by products. | `firms`, `tax_systems`, `business_profiles` |
| `tax_rule_actions` | firm store ¹ | Store one action performed when a tax rule matches. | `firms`, `tax_rules`, `tax_profiles`, `tax_components` |
| `tax_rule_conditions` | firm store ¹ | Store one configurable condition attached to a tax rule. | `firms`, `tax_rules` |
| `tax_rule_execution_logs` | firm store ¹ | Persist simulation and preview runs with immutable explanations. | `firms`, `geo_countries`, `business_profiles`, `tax_profiles`, `tax_rules` |
| `tax_rules` | firm store ¹ | Store versioned tax rule masters evaluated by the tax engine. | `firms`, `geo_countries`, `business_profiles`, `tax_profiles` |
| `tax_settings` | firm store ¹ | Store configurable enterprise tax labels and behavior per firm. | `firms` |
| `tax_systems` | firm store ¹ | Store one configurable tax system per firm and country. | `firms`, `geo_countries`, `business_profiles` |

### `app/tcs`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `tcs_collections` | firm store ¹ | One receipt's worth of tax collected at source. | `customers`, `settlements`, `journal_entries` |
| `tcs_settings` | firm store ¹ | One firm's 206C(1H) parameters. |  |

### `app/trade_licences`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `trade_licence_settings` | firm store ¹ | One firm's policy on selling and buying goods without a licence. |  |
| `trade_licence_types` | firm store ¹ | One kind of licence, such as a wholesale drug licence or FSSAI. |  |
| `trade_licences` | firm store ¹ | One licence held by the firm, a customer or a vendor. | `trade_licence_types`, `branches`, `customers`, `vendors` |

### `app/uom`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `packaging_types` | firm store ¹ | Define one packaging type token (box/carton/pallet/etc.). |  |
| `product_packaging_levels` | firm store ¹ | Store unlimited product packaging hierarchy levels. | `firms`, `products`, `packaging_types`, `uoms` |
| `unit_set_goods_types` | firm store ¹ | One goods type a unit set suits; the pair is the whole row. | `unit_sets`, `goods_types` |
| `unit_sets` | firm store ¹ | One template for a product's units and its pack size. | `uoms` |
| `uom_attribute_values` | firm store ¹ | Store one configurable attribute value for a unit of measure. | `uoms`, `firms`, `attribute_definitions` |
| `uom_conversion_rules` | firm store ¹ | Versioned UOM conversion rule with historical effectivity. | `firms`, `business_profiles`, `products`, `uoms` |
| `uom_group_units` | firm store ¹ | Map UOMs into UOM groups with base-unit selection. | `uom_groups`, `uoms` |
| `uom_groups` | firm store ¹ | Group related UOMs for conversions and product assignment. |  |
| `uoms` | firm store ¹ | Define one reusable unit of measure. |  |

### `app/vendors`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `supplier_gifts` | firm store ¹ | One gift from a supplier: not stock, not for sale (decision A112). | `firms`, `vendors`, `ledger_accounts`, `goods_receipts` |
| `supplier_products` | firm store ¹ | One dated catalogue row: a supplier's name, code and terms for a product. | `firms`, `vendors`, `products` |
| `vendor_addresses` | firm store ¹ | Represent one vendor address referencing geo masters. | `vendors`, `geo_countries`, `geo_states`, `geo_districts`, `geo_cities`, `geo_postal_codes`, `geo_localities` |
| `vendor_attachments` | firm store ¹ | Represent one vendor attachment metadata row. | `vendors` |
| `vendor_attribute_values` | firm store ¹ | Store one configurable attribute value for a vendor. | `vendors`, `firms`, `attribute_definitions` |
| `vendor_bank_accounts` | firm store ¹ | Represent one vendor bank account. | `vendors` |
| `vendor_categories` | firm store ¹ | Persist a reusable vendor category per firm. | `firms` |
| `vendor_contacts` | firm store ¹ | Represent one vendor contact person. | `vendors` |
| `vendor_notes` | firm store ¹ | Represent one vendor note/history item. | `vendors` |
| `vendor_opening_bills` | firm store ¹ | Store one bill a supplier was owed on the firm's first day here. | `vendors`, `journal_entries` |
| `vendor_ratings` | firm store ¹ | One person's scores for one supplier. | `firms`, `vendors` |
| `vendor_tax_details` | firm store ¹ | Represent one vendor tax detail set. | `vendors` |
| `vendor_types` | firm store ¹ | Persist a reusable vendor type per firm. | `firms` |
| `vendors` | firm store ¹ | Represent one vendor master owned by a firm. | `firms`, `vendor_categories`, `vendor_types`, `business_profiles` |

---

## What this catalogue cannot tell you

- **Which tables hold live rows.** 42 of them held none in any store when
  `docs/MODULE_STATUS.md` last asked, and asking that question found four
  defects in one day. Built is not the same as used.
- **What an action writes.** [`DATA_TRAIL_BY_OPERATION.md`](DATA_TRAIL_BY_OPERATION.md)
  answers that per operation, with a query to paste.
- **How the rows behave.** The module's section in
  [`FUNCTIONAL_GUIDE.md`](FUNCTIONAL_GUIDE.md) is the workflow;
  [`DATA_MODEL_IDENTITY_AND_FIRMS.md`](DATA_MODEL_IDENTITY_AND_FIRMS.md) and
  [`FIRM_DOMAIN_MODEL.md`](FIRM_DOMAIN_MODEL.md) are the two domains drawn as
  diagrams rather than listed.

