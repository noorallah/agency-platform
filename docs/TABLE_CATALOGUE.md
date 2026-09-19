# Table catalogue — every table, where it lives, what it holds

**199 tables**, of which **14** live only in the platform store.
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


### `app/batch_serial`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `batches` | firm store ¹ | Track one batch/lot of a product across the warehouse. | `firms`, `products`, `warehouses`, `branches`, `vendors`, `warehouse_storage_nodes` |
| `document_line_serials` | firm store ¹ | Name one serialised unit a document line moves. | `serial_numbers` |
| `lots` | firm store ¹ | Track one production lot across manufacturing steps. | `firms`, `products`, `warehouses`, `branches` |
| `serial_numbers` | firm store ¹ | Track one serialized unit through its full lifecycle. | `firms`, `products`, `inventories`, `warehouses`, `branches`, `batches` |

### `app/branches`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `branch_attribute_values` | firm store ¹ | Store one configurable attribute value for a branch. | `branches`, `firms`, `attribute_definitions` |
| `branch_types` | firm store ¹ | Persist reusable branch type masters per firm. | `firms` |
| `branches` | firm store ¹ | Represent one physical operational branch owned by a firm. | `firms`, `business_profiles`, `branch_types`, `users`, `geo_countries`, `geo_states`, `geo_districts`, `geo_cities`, `geo_postal_codes`, `geo_localities` |
| `warehouse_attribute_values` | firm store ¹ | Store one configurable attribute value for a warehouse. | `warehouses`, `firms`, `attribute_definitions` |
| `warehouse_storage_nodes` | firm store ¹ | Represent storage hierarchy nodes (area/rack/shelf/bin/receiving). | `warehouses` |
| `warehouse_types` | firm store ¹ | Persist reusable warehouse type masters per firm. | `firms` |
| `warehouses` | firm store ¹ | Represent one physical warehouse mapped to a branch. | `firms`, `branches`, `warehouse_types`, `users`, `business_profiles`, `geo_countries`, `geo_states`, `geo_districts`, `geo_cities`, `geo_postal_codes`, `geo_localities` |

### `app/business`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `attribute_definitions` | firm store ¹ | Define one configurable field that extends a record for some industry. | `business_profiles` |
| `business_features` | firm store ¹ | Define one configurable framework feature flag. |  |
| `business_modules` | firm store ¹ | Define one configurable module in the ERP workspace. |  |
| `business_profiles` | firm store ¹ | Define one industry/business operating profile. |  |
| `category_attribute_rules` | firm store ¹ | Define category-scoped mandatory-attribute rules by business profile. | `business_profiles`, `attribute_definitions` |
| `firm_business_profiles` | firm store ¹ | Assign exactly one active business profile to a firm. | `firms`, `business_profiles` |
| `profile_features` | firm store ¹ | Store per-profile feature enablement and optional configuration. | `business_profiles`, `business_features` |
| `profile_modules` | firm store ¹ | Store per-profile module visibility and workflow configuration. | `business_profiles`, `business_modules` |

### `app/commission`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `commission_payouts` | firm store ¹ | One period's commission for one salesman, from accrual to payment. | `users`, `ledger_accounts`, `journal_entries` |
| `commission_rule_slabs` | firm store ¹ | One rung of a rule's ladder: a band of value, and its rate. | `commission_rules` |
| `commission_rules` | firm store ¹ | Store one flat commission percentage, scoped and effective-dated. | `users`, `products`, `product_categories` |

### `app/common`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `audit_logs` | firm store | Record a mutation without coupling auditing to a business domain. |  |

### `app/credit_note`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `credit_note_lines` | firm store ¹ | One invoice line being credited, in part or in whole. | `credit_notes`, `sales_invoice_lines`, `products` |
| `credit_notes` | firm store ¹ | One credit against one invoice, with the tax it reverses. | `customers`, `branches`, `sales_invoices`, `journal_entries` |

### `app/customers`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `credit_control_settings` | firm store ¹ | Store one firm's credit-limit policy. | `firms` |
| `customer_addresses` | firm store ¹ | Represent one reusable customer address. | `customers`, `geo_countries`, `geo_states`, `geo_districts`, `geo_cities`, `geo_postal_codes`, `geo_localities` |
| `customer_attribute_values` | firm store ¹ | Store one configurable attribute value for a customer. | `customers`, `firms`, `attribute_definitions` |
| `customer_contacts` | firm store ¹ | Represent one customer contact person. | `customers` |
| `customer_groups` | firm store ¹ | A commercial segment a firm sells to: Retailer, Wholesaler, Institution. | `firms` |
| `customer_receivable_transactions` | firm store ¹ | Represent one immutable receivable movement for a customer. | `firms`, `customers`, `journal_entries` |
| `customers` | firm store ¹ | Represent one customer master owned by a firm. | `firms`, `customer_groups` |

### `app/delivery_note`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `delivery_note_attachments` | firm store ¹ | Store delivery note attachments. | `delivery_notes`, `firms` |
| `delivery_note_lines` | firm store ¹ | Store one delivery note line. | `delivery_notes`, `firms`, `sales_order_lines`, `products`, `uoms`, `packaging_types`, `tax_profiles`, `warehouses`, `warehouse_storage_nodes`, `batches` |
| `delivery_note_notes` | firm store ¹ | Store delivery note notes. | `delivery_notes`, `firms` |
| `delivery_notes` | firm store ¹ | Store one delivery note header. | `firms`, `sales_orders`, `customers`, `branches`, `warehouses`, `business_profiles`, `users`, `territory_route_profiles`, `sales_territories` |

### `app/diagnostics`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `error_reports` | platform | One failure, reported by a desktop client or raised by this server. |  |

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
| `einvoice_registrations` | firm store ¹ | One sales invoice, as the Invoice Registration Portal knows it. | `sales_invoices` |
| `eway_bills` | firm store ¹ | One consignment's e-way bill, raised against an invoice. | `sales_invoices` |

### `app/finance`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `account_groups` | firm store ¹ | Group ledger accounts for classification and report rollups. | `firms` |
| `accounting_periods` | firm store ¹ | Represent one posting period inside a financial year. | `firms`, `financial_years` |
| `cost_centers` | firm store ¹ | Represent a cost centre used to attribute expenditure. | `firms` |
| `customer_ledgers` | firm store ¹ | Hold derived receivable totals for one customer and period. | `firms`, `customers`, `accounting_periods` |
| `financial_years` | firm store ¹ | Represent one fiscal year owned by a firm. | `firms` |
| `firm_control_accounts` | firm store ¹ | Map a document-posting purpose onto the account a firm posts it to. | `firms`, `ledger_accounts` |
| `gl_postings` | firm store ¹ | Record one journal line as it was posted to the general ledger. | `firms`, `journal_entries`, `journal_lines`, `ledger_accounts`, `accounting_periods` |
| `journal_entries` | firm store ¹ | Represent one balanced double-entry journal voucher. | `firms`, `journal_types`, `voucher_types`, `accounting_periods` |
| `journal_lines` | firm store ¹ | Represent one debit or credit leg of a journal entry. | `journal_entries`, `ledger_accounts`, `cost_centers`, `profit_centers` |
| `journal_types` | firm store ¹ | Classify journals such as sales, purchase, or general. | `firms` |
| `ledger_accounts` | firm store ¹ | Represent one general-ledger account in the chart of accounts. | `firms`, `account_groups` |
| `ledger_balances` | firm store ¹ | Hold the derived balance of one ledger account for one period. | `firms`, `ledger_accounts`, `accounting_periods` |
| `profit_centers` | firm store ¹ | Represent a profit centre used to attribute revenue. | `firms` |
| `vendor_ledgers` | firm store ¹ | Hold derived payable totals for one vendor and period. | `firms`, `vendors`, `accounting_periods` |
| `voucher_types` | firm store ¹ | Classify vouchers such as invoice, receipt, or payment. | `firms` |

### `app/firms`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `firm_storage_mappings` | platform ¹ | Persist tenant storage routing details for a firm. | `firms` |
| `firms` | platform ¹ | Represent an organization available to one or more platform users. |  |

### `app/goods_receipt`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `goods_receipt_attachments` | firm store ¹ | Store goods receipt attachments. | `goods_receipts`, `firms` |
| `goods_receipt_lines` | firm store ¹ | Store one goods receipt line. | `goods_receipts`, `firms`, `purchase_order_lines`, `products`, `tax_profiles`, `packaging_types`, `uoms`, `warehouses`, `warehouse_storage_nodes`, `batches`, `inventory_transactions` |
| `goods_receipt_notes` | firm store ¹ | Store goods receipt notes. | `goods_receipts`, `firms` |
| `goods_receipts` | firm store ¹ | Store one goods receipt note header. | `firms`, `purchase_orders`, `vendors`, `branches`, `warehouses`, `users` |

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
| `user_template_roles` | firm store ¹ | One role in a template's bundle. | `user_templates`, `roles` |
| `user_templates` | firm store ¹ | A named bundle of roles for one job, so a firm hires by naming the job. | `firms` |
| `users` | platform ¹ | Represent an interactive platform user. |  |

### `app/inventory`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `inventories` | firm store ¹ | Persist one firm-scoped inventory projection per product location. | `firms`, `branches`, `warehouses`, `warehouse_storage_nodes`, `products`, `batches`, `business_profiles`, `uoms` |
| `inventory_transactions` | firm store ¹ | Persist one immutable inventory movement event. | `inventories`, `firms`, `branches`, `warehouses`, `warehouse_storage_nodes`, `products`, `business_profiles`, `uoms`, `batches`, `lots`, `serial_numbers` |
| `opening_stock_batches` | firm store ¹ | Persist a draft or posted opening-stock document. | `firms`, `branches`, `warehouses` |
| `opening_stock_lines` | firm store ¹ | Persist one opening-stock line before or after posting. | `opening_stock_batches`, `products`, `warehouse_storage_nodes`, `business_profiles`, `uoms`, `batches`, `inventory_transactions` |
| `physical_count_lines` | firm store ¹ | Store one stock row's count on one sheet. | `firms`, `physical_counts` |
| `physical_counts` | firm store ¹ | Store one count sheet for one warehouse. | `firms` |
| `product_valuations` | firm store ¹ | Track the moving weighted-average cost of a product for a firm. | `firms`, `products` |
| `stock_ledger_entries` | firm store ¹ | Persist one immutable stock-ledger row per inventory transaction. | `inventory_transactions`, `inventories`, `batches`, `firms`, `branches`, `warehouses`, `warehouse_storage_nodes`, `products`, `business_profiles`, `uoms` |

### `app/loyalty`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `loyalty_entries` | firm store ¹ | One movement of a customer's credit. | `customers`, `sales_invoices`, `journal_entries` |
| `loyalty_settings` | firm store ¹ | One firm's scheme. |  |

### `app/pricing`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `price_list_items` | firm store ¹ | One product's rate on one list. | `price_lists`, `products` |
| `price_lists` | firm store ¹ | One named arrangement, scoped to who it applies to and when. | `customers`, `sales_territories` |

### `app/products`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `product_attribute_values` | firm store ¹ | Store one configurable attribute value for a product. | `products`, `firms`, `attribute_definitions` |
| `product_categories` | firm store ¹ | Represent a hierarchical firm category tree for products. | `firms` |
| `product_media` | firm store ¹ | Store product images, attachments, and reference documents. | `firms`, `products` |
| `products` | firm store ¹ | Represent one configurable product core master row. | `firms`, `product_categories`, `uoms` |

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
| `promotions` | firm store ¹ | Store one versioned promotion evaluated while a document is priced. |  |

### `app/purchase`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `purchase_attachments` | firm store ¹ | Store purchase document attachments. | `purchase_orders`, `firms` |
| `purchase_delivery_schedules` | firm store ¹ | Store delivery schedules per order line. | `purchase_order_lines`, `firms` |
| `purchase_notes` | firm store ¹ | Store notes linked to purchase documents. | `purchase_orders`, `firms` |
| `purchase_order_history` | firm store ¹ | Store immutable history events for purchase orders. | `purchase_orders`, `firms` |
| `purchase_order_lines` | firm store ¹ | Store one purchase order line item. | `purchase_orders`, `firms`, `products`, `uoms`, `tax_profiles`, `warehouses`, `warehouse_storage_nodes` |
| `purchase_orders` | firm store ¹ | Store one enterprise purchase order header. | `firms`, `branches`, `warehouses`, `vendors`, `users`, `tax_profiles` |

### `app/purchase_invoice`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `purchase_invoice_accounting_events` | firm store ¹ | Store reusable accounting placeholder events. | `purchase_invoices`, `firms` |
| `purchase_invoice_attachments` | firm store ¹ | Store purchase invoice attachments. | `purchase_invoices`, `firms` |
| `purchase_invoice_lines` | firm store ¹ | Store one purchase invoice line. | `purchase_invoices`, `firms`, `products`, `tax_profiles`, `packaging_types`, `uoms`, `warehouses`, `warehouse_storage_nodes` |
| `purchase_invoice_notes` | firm store ¹ | Store purchase invoice notes. | `purchase_invoices`, `firms` |
| `purchase_invoice_sources` | firm store ¹ | Store supplier invoice source document references. | `purchase_invoices`, `firms`, `vendors`, `branches` |
| `purchase_invoices` | firm store ¹ | Store one supplier invoice header. | `firms`, `vendors`, `branches`, `business_profiles` |

### `app/purchase_return`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `purchase_return_accounting_events` | firm store ¹ | Store reusable accounting placeholder events. | `purchase_returns`, `firms` |
| `purchase_return_attachments` | firm store ¹ | Store purchase return attachments. | `purchase_returns`, `firms` |
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
| `sales_invoice_line_taxes` | firm store ¹ | Store the tax components one invoice line was actually charged. | `sales_invoice_lines` |
| `sales_invoice_lines` | firm store ¹ | Store one sales invoice line. | `sales_invoices`, `firms`, `products`, `tax_profiles`, `packaging_types`, `uoms`, `warehouses`, `warehouse_storage_nodes` |
| `sales_invoice_notes` | firm store ¹ | Store sales invoice notes. | `sales_invoices`, `firms` |
| `sales_invoice_sources` | firm store ¹ | Store customer invoice source document references. | `sales_invoices`, `firms`, `customers`, `branches` |
| `sales_invoices` | firm store ¹ | Store one customer invoice header. | `firms`, `customers`, `users`, `sales_territories`, `territory_route_profiles`, `branches`, `business_profiles` |

### `app/sales_order`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `sales_order_attachments` | firm store ¹ | Store sales order attachments. | `sales_orders`, `firms` |
| `sales_order_lines` | firm store ¹ | Store one sales order line. | `sales_orders`, `firms`, `products`, `uoms`, `packaging_types`, `tax_profiles`, `warehouses`, `warehouse_storage_nodes` |
| `sales_order_notes` | firm store ¹ | Store sales order notes. | `sales_orders`, `firms` |
| `sales_orders` | firm store ¹ | Store one sales order header. | `firms`, `customers`, `users`, `sales_territories`, `territory_route_profiles`, `branches`, `warehouses`, `business_profiles` |
| `sales_workflow_settings` | firm store ¹ | Store which sales stages one firm fills in by hand. | `firms`, `branches`, `warehouses` |

### `app/sales_return`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `sales_return_attachments` | firm store ¹ | Store sales return attachments. | `sales_returns`, `firms` |
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
| `settlement_allocations` | firm store ¹ | Store how much of one settlement cleared one invoice. | `firms`, `settlements`, `sales_invoices`, `purchase_invoices` |
| `settlements` | firm store ¹ | Store one receipt from a customer or payment to a vendor. | `firms`, `customers`, `vendors`, `ledger_accounts`, `sales_orders`, `journal_entries` |
| `supplier_credit_applications` | firm store ¹ | Store how much of one purchase return's supplier credit cleared one bill. | `vendors`, `purchase_returns`, `purchase_invoices` |

### `app/tax`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
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

### `app/uom`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `business_profile_uom_defaults` | firm store ¹ | Default UOM behavior by business profile (and optional firm override). | `firms`, `business_profiles`, `uoms` |
| `packaging_types` | firm store ¹ | Define one packaging type token (box/carton/pallet/etc.). |  |
| `product_packaging_levels` | firm store ¹ | Store unlimited product packaging hierarchy levels. | `firms`, `products`, `packaging_types`, `uoms` |
| `uom_attribute_values` | firm store ¹ | Store one configurable attribute value for a unit of measure. | `uoms`, `firms`, `attribute_definitions` |
| `uom_conversion_rules` | firm store ¹ | Versioned UOM conversion rule with historical effectivity. | `firms`, `business_profiles`, `products`, `uoms` |
| `uom_group_units` | firm store ¹ | Map UOMs into UOM groups with base-unit selection. | `uom_groups`, `uoms` |
| `uom_groups` | firm store ¹ | Group related UOMs for conversions and product assignment. |  |
| `uom_industry_templates` | firm store ¹ | Store reusable industry UOM/packaging templates. |  |
| `uoms` | firm store ¹ | Define one reusable unit of measure. |  |

### `app/vendors`

| Table | Store | Holds | Points at |
| --- | --- | --- | --- |
| `vendor_addresses` | firm store ¹ | Represent one vendor address referencing geo masters. | `vendors`, `geo_countries`, `geo_states`, `geo_districts`, `geo_cities`, `geo_postal_codes`, `geo_localities` |
| `vendor_attachments` | firm store ¹ | Represent one vendor attachment metadata row. | `vendors` |
| `vendor_attribute_values` | firm store ¹ | Store one configurable attribute value for a vendor. | `vendors`, `firms`, `attribute_definitions` |
| `vendor_bank_accounts` | firm store ¹ | Represent one vendor bank account. | `vendors` |
| `vendor_categories` | firm store ¹ | Persist a reusable vendor category per firm. | `firms` |
| `vendor_contacts` | firm store ¹ | Represent one vendor contact person. | `vendors` |
| `vendor_notes` | firm store ¹ | Represent one vendor note/history item. | `vendors` |
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

