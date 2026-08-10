# Module Review Checklist

A per-module review pass, in the shape that worked for the platform layer on
2026-08-09. That pass found twelve unseeded permission codes, a login timing
side-channel, a permanently-burned email address on user delete, missing refresh
token reuse detection, and three unbounded tables — none of which were visible
from reading a single file.

Two rules carried over from it:

- **Verify before you claim.** Two of the eight platform findings were wrong and
  were caught only by checking against the running system before acting. Reproduce
  a defect before fixing it, and re-check the fix against a real database.
- **Record the baseline first.** Capture the module's test/lint/type counts before
  changing anything, so your diff is measured against fact rather than assumption.

## The checklist

Run these against one module at a time. Items marked **(found a real bug)** are
ones that produced a defect during the platform pass.

### Business profile

- [ ] Behaviour that is industry-specific is gated on a **feature**, not hardcoded
      **(found a real bug — 18 of 21 features were unenforced)**. Use
      `require_feature` / `require_module` from `app/business/gating.py`.
- [ ] The feature exists in `business_features` and is enabled for the profiles
      that should have it; check `profile_features`, not just the code.
- [ ] Gates are on writes only; reads stay open so existing data remains visible.

### Authorization and tenancy

- [ ] Every code passed to `require_permission` exists in `PERMISSION_GROUPS`
      **(found a real bug — 12 codes)**. `tests/unit/test_identity_hardening.py`
      now guards this globally, but check that new codes reach a sensible role.
- [ ] Every firm-owned route resolves scope through `X-Firm-ID` **and** validates
      an active `UserFirm` membership — platform admins included.
- [ ] Firm-scoped queries filter on `firm_id`; nothing leaks across firms. Write a
      two-firm test that asserts the second firm sees nothing.
- [ ] Uniqueness checks filter `is_deleted` **(found a real bug — user email)**.
      A soft-deleted row must not permanently reserve a natural key. **The
      database constraint has to agree with the service check** — `firms` kept
      table-wide `UNIQUE` constraints while `_assert_unique` ignored deleted
      rows, so re-creating a deleted firm passed validation and then died on the
      constraint with a 500 **(found a real bug — firm code, GST and PAN)**.

### Persistence and migrations

- [ ] Entities extend `BaseEntity`; no bespoke id/timestamp/soft-delete columns.
- [ ] Constraint names follow `UQ_`/`IX_`/`FK_`/`PK_`.
- [ ] Migration matches the ORM exactly. Diff them rather than eyeballing:
      build one schema from `Base.metadata.create_all` and one from the
      migration's `upgrade()`, then compare columns table by table.
- [ ] Migration is **idempotent** — guard `add_column`/`create_table` with
      `sa.inspect(bind)` checks **(found a real bug — `20260808_0040`)**. Firm
      schemas are partly built by `create_all` in the sample-data scripts, so
      `alembic_version` understates what exists.
- [ ] Cross-schema foreign keys are conditional **(found a real bug — finance)**.
      `firms` exists only in `platform`; `customers`/`vendors` only in firm
      schemas. Declare the FK only when `has_table()` finds the target.
- [ ] Migration applied to **every** target, not just the default schema:
      `platform`, `firm_shared`, each dedicated schema, each dedicated database.
- [ ] `downgrade()` actually reverses `upgrade()`, verified by running it.

### Correctness and conventions

- [ ] Every mutation emits `record_audit` with before/after data.
- [ ] Responses use `ApiResponse` / `PaginatedResponse`; lists accept only the
      whitelisted `page`, `page_size`, `search`, `sort_by`, `sort_direction`.
- [ ] Date filters use `datetime.combine(date, time.min/max, UTC)` — not naive
      local dates **(found a real bug — audit filters)**.
- [ ] Money is `Numeric(18, 2)` quantized at the boundary, never float.
- [ ] No table grows without bound, or there is a documented purge path
      **(found a real bug — tokens and history)**.

### Tests

- [ ] A dedicated `tests/unit/test_<module>.py` exists.
- [ ] It passes **standalone**, not only inside the full suite.
- [ ] Covers: firm isolation, permission denial, validation failures, and the
      module's lifecycle transitions — not just the happy path.

### Desktop

- [ ] Endpoint paths live in `api_client.dart`, not inlined in pages via the
      untyped `api.request(...)` escape hatch.
- [ ] Backend capabilities have UI, or are explicitly `available: false` in
      `module_catalog.dart` rather than silently absent.
- [ ] Screens compose the shared workspace framework instead of bespoke shells.

### Gates

- [ ] `ruff`, `black`, `mypy` clean **for the module** (repo-wide is still red).
- [ ] Full suite no worse than the baseline you captured.

### Defects the 2026-08-09 pass added to this list

Each of these was invisible to the unit suite, and each cost a real defect.

- [ ] Permission codes are **upper snake case and seeded**. The guard test matched
      only `[A-Z0-9_]+`, so lowercase `sales_invoice:read` slipped past it and made
      an entire module platform-admin-only.
- [ ] Firm scope is resolved through `app/common/scope.py`, **never** on the
      request's tenant session — `firms`/`user_firms` live only in the platform
      schema **(found a real bug — every firm-owned router)**.
- [ ] A service that receives someone else's session **does not commit it**.
      `DocumentFrameworkService` committed in all 11 mutating methods, splitting
      every document write into several transactions. `TaxRuleService.simulate`
      did the same and was worse hidden: it reads like a preview, but all seven
      transactional modules call it once per line while building a document, so
      a commit there published a half-written invoice **(found a real bug
      twice — check every service another service calls)**.
- [ ] Cancelling a document **reverses whatever it posted**. Cancelling a completed
      goods receipt or purchase return left the stock movement in place.
- [ ] Sequence allocation **takes a row lock**, and a losing race returns 409, not 503.
- [ ] Rounding, financial-year labels and `subtotal` come from the shared helpers.
      Seven private copies disagreed three ways, including one using banker's rounding.
- [ ] **Generated values are asserted, not just their prefix.** Extracting the shared
      document base silently dropped the company code from purchase order numbers and
      nothing failed, because every test supplied its own number.
- [ ] Child rows are **reconciled on their natural key**, not deleted and re-inserted.
      Downstream documents reference line ids with no foreign key.
- [ ] Anything touching tenancy, cross-schema FKs, triggers or concurrency has an
      **integration test**; SQLite cannot express any of it.

### Defects the `firms` pass added to this list

- [ ] On a full-replacement `PUT`, an **optional field that is omitted inherits
      the stored value** — it does not fall back to the system default. Every
      tenancy field on `FirmUpdate` is optional, so renaming a firm rewrote its
      storage mapping to `SHARED` with a null schema and stranded everything the
      firm had written to its dedicated schema **(found a real bug)**.
- [ ] **Anything provisioned once is immutable afterwards.** Nothing migrates a
      firm's rows between stores and `provision_new_firm` runs only at creation,
      so accepting a routing change on update either abandons the data or aims
      the firm at a schema that was never built. Reject it in the service and
      mark the field `readOnlyWhenEditing` in the desktop form.
- [ ] **Two tenants can never be routed into one store.** The only uniqueness on
      `firm_storage_mappings` is one row per firm, so two firms could name the
      same schema and read each other's rows; soft-deleted firms count, because
      their data is still sitting in that schema.

### Defects the `tax` pass added to this list

- [ ] **A flag or action the engine records has to change an outcome.**
      `included_in_price` and the `REVERSE_CHARGE` action were both stored,
      returned in the response and read by nobody, so configuring either
      silently produced wrong money — an inclusive component was billed on top
      of the price it was already inside, and a reverse-charge sale still
      charged the customer the tax. Trace every declared flag to the line that
      acts on it, or the feature is decoration.
- [ ] **A scope filter must be satisfiable by the callers that actually exist.**
      Rules can be scoped by country and business profile, but no document sends
      a country and two of the seven send no profile, so country-scoped rules
      never fired and profile-scoped rules fired on five document types out of
      seven. Check what the real callers pass, not what the API accepts.
- [ ] **Grep for `quantize(` across the module.** An eighth private helper was
      still rounding tax half-to-even after the seven document copies were
      unified on `quantize_money`.

### Defects the `uom` pass added to this list

- [ ] **Never let NULL ordering decide which row wins.** Selecting the most
      specific conversion rule with `ORDER BY product_id DESC` relied on where
      the backend sorts NULLs: PostgreSQL puts them first, SQLite last, so the
      firm-wide fallback beat the product's own factor in production while the
      unit suite saw the right answer **(found a real bug)**. Rank on an
      explicit expression — `case((col.is_(None), 1), else_=0)` — and cover it
      with an integration test.
- [ ] **No model may declare a column named `version`.** That name is
      `BaseEntity`'s optimistic-concurrency counter and the mapper's
      `version_id_col`. `ConversionRule` used it for the rule's published
      version, so the ORM incremented the number documents record to identify
      the factor they converted with, and every edit invented a version that
      never existed **(found a real bug)**. Business versions are
      `version_number`.
- [ ] **Deleting shared reference data needs a usage guard.** The UOM catalogue
      has no `firm_id`, so in a SHARED deployment every firm in the store reads
      the same rows and an unguarded delete took a unit out from under another
      firm's products and rules. Check usage across the store, not just the
      caller's firm.
- [ ] A recorded setting that changes nothing recurred here: `rounding_mode` was
      stored per rule and the conversion always rounded half up.

### Defects the `search` pass added to this list

- [ ] **A platform admin is not exempt from the firm filter.** Global search
      skipped it for them entirely, so in a SHARED deployment -- one schema
      holding every firm's rows -- an admin with no firm selected got two
      firms' customers in a single list **(found a real bug)**. Where a firm
      column is nullable, null means the row belongs to the platform, not that
      the filter should be dropped.

### Defects the `batch_serial` pass added to this list

- [ ] **A status nobody transitions is not a state.** Expiry counts filtered on
      `status = 'EXPIRED'`, which nothing ever set -- the platform has no
      scheduler -- so the summary reported zero expired batches while the
      expiry card, reading the date, listed them, and the guard blocking
      purchases of expired stock never fired **(found a real bug)**. Derive the
      state from the fact that decides it.
- [ ] **Two numbers describing the same rows must be computed the same way.**
      One dashboard held both, disagreeing.

### Defects the `inventory` pass added to this list

- [ ] **A response builder is not reusable just because the rows look alike.**
      `ledger_response` passed a `StockLedgerEntry` to the builder for
      `InventoryTransaction`; the ledger names its as-entered columns
      `original_quantity`/`original_uom_id` and has no `conversion_version`, so
      the endpoint raised AttributeError as soon as one movement existed
      **(found a real bug)**. mypy had been reporting it the whole time.
- [ ] **Read every endpoint back at least once in a test.** The write path was
      correct and covered; nothing had ever listed the rows it wrote.
- [ ] **Fixtures must use the module's whole vocabulary.** Repairing the ledger
      response uncovered a second failure underneath it only when the app was
      run against seeded data: the response validated `transaction_type`
      against a closed enum while the service writes RESERVE, UNRESERVE and
      DISPATCH, and `reverse_transaction` writes `"<TYPE>_REVERSAL"`, which no
      enum can enumerate. An adjustment-only fixture passed throughout
      **(found a real bug, by running the app)**. An immutable historical
      record carries the vocabulary it was written with; keep the enum for
      filters, where a closed set is what a caller should be held to.

### Defects the `branches` pass added to this list

- [ ] **Bulk endpoints audit every row they touch.** All six of them wrote
      nothing, so deleting fifty branches from the toolbar left a trail showing
      none of it while deleting one from the row menu was recorded
      **(found a real bug)**. Check the bulk path separately: it is usually a
      second implementation of the single-row one, and it drifts.
- [ ] **A bulk endpoint enforces the same rules as its single-row twin.** The
      guards, not just the audit, have to be in both.
- [ ] **Deleting a parent checks its children.** A branch could be soft deleted
      with live warehouses still trading under it, and a warehouse with stock
      still in it, while the module already refused to delete a storage node
      with children **(found a real bug)**.
- [ ] **An exclusivity flag needs an owner.** `is_default` was accepted on write
      and maintained by nothing, so every branch in a firm could claim it. Demote
      the incumbent in the service and back it with a partial unique index, as
      `UQ_user_firms_active_primary` does. Flush the demotion before writing the
      promoted row or the index rejects the statement.

## Module inventory

Endpoint counts and debt measured 2026-08-09. `ruff`/`mypy` are current error
counts for that package — they are the size of the cleanup, not a pass/fail.

| Module | Endpoints | ruff | mypy | Unit test | Desktop |
| --- | ---: | ---: | ---: | --- | --- |
| `finance` | 30 | 0 | 0 | `test_finance_module` | **none** |
| `common` (audit) | 1 | 0 | 0 | `test_audit_trail_api` | **none** |
| `identity` | 29 | 0 | 2 | `test_identity_service`, `test_identity_hardening` | typed |
| `firms` | 5 | 0 | 0 | `test_firms_module` | typed |
| `document_framework` | 15 | 0 | 0 | `test_document_framework` | widgets only |
| `business` | 28 | 0 | 0 | `test_business_profile_framework` | typed |
| `sales` (territory) | 44 | 0 | 0 | `test_sales_territory_route_management` | typed |
| `customers` | 14 | 0 | 0 | `test_customer_management` | typed |
| `products` | 17 | 0 | 0 | `test_product_master` | typed |
| `search` | 1 | 0 | 0 | `test_global_search` | typed |
| `vendors` | 23 | 0 | 0 | `test_vendor_management` | typed |
| `purchase` | 12 | 0 | 0 | `test_purchase_management` | typed |
| `batch_serial` | 17 | 0 | 0 | `test_batch_serial_expiry` | typed |
| `goods_receipt` | 16 | 0 | 0 | `test_goods_receipt` | typed |
| `inventory` | 19 | 0 | 0 | `test_inventory_foundation` | typed |
| `branches` | 39 | 0 | 0 | `test_branch_warehouse_management` | typed |
| `uom` | 29 | 0 | 0 | `test_uom_packaging_framework` | typed |
| `sales_order` | 17 | 170 | 1 | `test_sales_order_module` | typed |
| `sales_invoice` | 16 | 185 | 34 | `test_sales_invoice_module` | typed |
| `purchase_invoice` | 16 | 208 | 15 | `test_purchase_invoice_module` | typed |
| `delivery_note` | 19 | 210 | 6 | `test_delivery_note_module` | typed |
| `purchase_return` | 18 | 212 | 22 | `test_purchase_return_module` | typed |
| `tax` | 52 | 0 | 0 | `test_tax_framework` | typed |

As of 2026-08-10 no page holds an endpoint path: `grep -rn "'/api/v1/" lib/`
matches only `api_client.dart`. The five document workspaces share
`documentSummary`/`documentPage`/`documentHistory`/`documentAction`, and the tax
screens use the typed client that already existed — they had simply never been
wired to it.

## Suggested order

**1. `sales_invoice`** — worst combination on the board: no test at all, 34 mypy
errors, 185 ruff, and an untyped desktop client. Highest chance of a real defect.

**2. `goods_receipt` and `firms`** — the other two modules with no dedicated test.
`goods_receipt` posts to inventory, so silent breakage there corrupts stock.

**3. The transaction chain** — `purchase_invoice`, `purchase_return`,
`delivery_note`, `sales_order`. Similar shape, so reviewing them together lets one
set of fixes apply four times, including lifting their endpoints into
`api_client.dart`.

**4. `tax`** — the largest single module (52 endpoints, 268 ruff) and a dependency
of every transaction module, so defects here surface as wrong money elsewhere.

**5. `uom`, `branches`, `inventory`, `batch_serial`** — high lint debt but tested
and typed; mostly cleanup.

**6. The rest** — `customers`, `products`, `vendors`, `purchase`, `search`,
`business`, `sales` are in reasonable shape and can be quick passes.

## Progress

| # | Module | Reviewed | Findings | Fixed |
| --- | --- | --- | --- | --- |
| 0 | platform (`identity`, `firms`, security, RBAC) | 2026-08-09 | 6 real, 2 retracted | yes |
| 0b | `business` (profile framework) | 2026-08-09 | gating was client-side only; 18/21 features unenforced; profile data empty for every industry but GENERIC | mechanism + seed done; per-module gating outstanding |
| 0c | **all firm-owned routers** (tenancy) | 2026-08-09 | every one resolved `firms`/`user_firms` on the tenant session, so all firm-owned endpoints failed on PostgreSQL outside the platform schema | yes — shared `app/common/scope.py` |
| 0d | **persistence conventions** | 2026-08-09 | FK naming collided on two FKs to one target, so `create_all` could not build the schema on PostgreSQL; `BaseEntity.version` never read or incremented | yes |
| 1 | `sales_invoice` | 2026-08-09 | permission codes unseeded (whole API admin-only); every handler mis-called its service; the six tables never matched the ORM | yes — module now has a test |
| 2 | `goods_receipt` | 2026-08-09 | cancel left stock posted; totals computed twice with different formulas; lines re-inserted on edit | yes — `test_goods_receipt` added 2026-08-10 to pin the fixes |
| 3 | `firms` | 2026-08-09 | soft delete burned the code, GST and PAN forever; a `PUT` omitting the optional tenancy fields re-pointed a dedicated firm at the shared schema; two firms could be routed into one schema; update carried no `after_data` and no `If-Match` | yes — module now has a test |
| 4 | `purchase_invoice` | 2026-08-09 | `subtotal` folded in line charges; committed mid-write; `_flush_or_conflict` left the session unusable | yes |
| 5 | `purchase_return` | 2026-08-09 | cancel left stock posted and its movements were unlinkable; `subtotal` folded in line charges | yes |
| 6 | `delivery_note` | 2026-08-09 | lines re-inserted on edit, dangling downstream references | yes |
| 7 | `sales_order` | 2026-08-09 | lines re-inserted on edit, resetting `reserved_quantity` while the RESERVE movement stayed in the ledger | yes |
| 8 | `tax` | 2026-08-09 | `simulate` committed the caller's session while every document computed tax line by line; an eighth private rounding helper still used banker's rounding; country-scoped rules never matched a document and profile-scoped ones matched five of seven; `included_in_price` was billed on top of the price; `REVERSE_CHARGE` changed nothing; the execution log had no purge path | yes — desktop endpoints still inlined |
| 9 | `uom` | 2026-08-09 | a product's own conversion factor lost to the firm-wide one on PostgreSQL only; the rule's published version was the same column as the concurrency counter, so any edit moved it; the configured `rounding_mode` was ignored; a unit in use could be deleted out from under other firms | yes — module is now clean under ruff, black and mypy |
| 10 | `branches` | 2026-08-10 | the six bulk endpoints wrote no audit entries at all; a branch could be deleted with live warehouses under it and a warehouse deleted with stock in it; `is_default` was maintained by nothing, so every branch could be the firm default | yes — module is now clean under ruff, black and mypy |
| 11 | `inventory` | 2026-08-10 | `GET /inventory/ledger` raised AttributeError for every firm that had ever moved stock, because the ledger row was fed to the transaction response builder | yes — module is now clean under ruff, black and mypy |
| 12 | `batch_serial` | 2026-08-10 | expiry counts keyed on a `status` nothing ever sets, so the summary reported zero expired batches while the expiry card listed them; the guard blocking purchases of expired stock never fired for the same reason; expiry windows used the server's local date | yes — module is now clean under ruff, black and mypy |
| 13 | `customers` | 2026-08-10 | none in the review itself — receivable arithmetic, address/contact reconciliation and firm scoping all hold. The recorded-but-unenforced `credit_limit` was resolved separately: warn by default, block if the firm configures it (`20260810_0057`) | gates cleared; credit control shipped |
| 14 | `products` | 2026-08-10 | bulk delete and restore wrote no audit entries, the same gap found in `branches`; deleting a category was unaudited too | yes |
| 15 | `vendors` | 2026-08-10 | all five bulk endpoints wrote no audit entries — the third module with this gap | yes — module is now clean under ruff, black and mypy |
| 16 | `purchase` | 2026-08-10 | a purchase order with goods receipts against it could be deleted, though cancelling the same order was refused; a CSV import helper closed over its loop variable | yes — module is now clean under ruff, black and mypy |
| 17 | `business` | 2026-08-10 | deleting a feature or module a profile still enabled silently revoked the capability for every firm on that profile, so `require_feature` began rejecting writes those firms made the day before | yes |
| 18 | `sales` (territory) | 2026-08-10 | bulk status changes and moves wrote one summary audit row keyed on the first id, so the trail recorded that N territories changed without naming any of them | yes |
| 19 | `search` | 2026-08-10 | the firm filter was skipped entirely for platform admins, so an admin with no firm selected saw every firm's rows in one result list — in a SHARED store that is one schema holding all of them | yes |
| 20 | `document_framework` | 2026-08-10 | none — the commit-per-method defect was fixed in the 2026-08-09 pass and lifecycle, numbering and timeline events all hold | gates only |
