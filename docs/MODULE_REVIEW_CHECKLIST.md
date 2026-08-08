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
      A soft-deleted row must not permanently reserve a natural key.

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

## Module inventory

Endpoint counts and debt measured 2026-08-09. `ruff`/`mypy` are current error
counts for that package — they are the size of the cleanup, not a pass/fail.

| Module | Endpoints | ruff | mypy | Unit test | Desktop |
| --- | ---: | ---: | ---: | --- | --- |
| `finance` | 30 | 0 | 0 | `test_finance_module` | **none** |
| `common` (audit) | 1 | 0 | 0 | `test_audit_trail_api` | **none** |
| `identity` | 29 | 0 | 2 | `test_identity_service`, `test_identity_hardening` | typed |
| `firms` | 5 | 0 | 1 | **none** | typed |
| `document_framework` | 15 | 0 | 1 | `test_document_framework` | widgets only |
| `business` | 28 | 2 | 3 | `test_business_profile_framework` | typed |
| `sales` (territory) | 44 | 2 | 0 | `test_sales_territory_route_management` | typed |
| `customers` | 14 | 15 | 6 | `test_customer_management` | typed |
| `products` | 17 | 23 | 4 | `test_product_master` | typed |
| `search` | 1 | 55 | 1 | `test_global_search` | typed |
| `vendors` | 23 | 82 | 6 | `test_vendor_management` | typed |
| `purchase` | 12 | 105 | 5 | `test_purchase_management` | typed |
| `batch_serial` | 17 | 121 | 2 | `test_batch_serial_expiry` | typed |
| `goods_receipt` | 16 | 134 | 1 | **none** | typed |
| `inventory` | 19 | 145 | 6 | `test_inventory_foundation` | typed |
| `branches` | 39 | 149 | 2 | `test_branch_warehouse_management` | typed |
| `uom` | 29 | 161 | 20 | `test_uom_packaging_framework` | typed |
| `sales_order` | 17 | 170 | 1 | `test_sales_order_module` | **untyped** |
| `sales_invoice` | 16 | 185 | 34 | **none** | **untyped** |
| `purchase_invoice` | 16 | 208 | 15 | `test_purchase_invoice_module` | **untyped** |
| `delivery_note` | 19 | 210 | 6 | `test_delivery_note_module` | **untyped** |
| `purchase_return` | 18 | 212 | 22 | `test_purchase_return_module` | **untyped** |
| `tax` | 52 | 268 | 14 | `test_tax_framework` | typed + untyped |

"untyped" means the desktop reaches those endpoints through
`api.request('GET', '/api/v1/...')` inside page widgets rather than through
`api_client.dart`, which the desktop README says is the only place paths belong.

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
| 1 | `sales_invoice` | | | |
| 2 | `goods_receipt` | | | |
| 3 | `firms` | | | |
| 4 | `purchase_invoice` | | | |
| 5 | `purchase_return` | | | |
| 6 | `delivery_note` | | | |
| 7 | `sales_order` | | | |
| 8 | `tax` | | | |
| 9 | `uom` | | | |
| 10 | `branches` | | | |
| 11 | `inventory` | | | |
| 12 | `batch_serial` | | | |
| 13 | `customers` | | | |
| 14 | `products` | | | |
| 15 | `vendors` | | | |
| 16 | `purchase` | | | |
| 17 | `business` | | | |
| 18 | `sales` (territory) | | | |
| 19 | `search` | | | |
| 20 | `document_framework` | | | |
