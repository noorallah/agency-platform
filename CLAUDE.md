# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository shape

Two independent applications, no shared build:

- `backend/` — FastAPI + SQLAlchemy 2.0 + Alembic, Python 3.13, managed with `uv`. Owns all business logic and the database.
- `desktop/` — Flutter Material 3 desktop client (Windows/Linux/macOS). Talks to the backend **only** over REST; it never touches the database.
- `docs/`, `backend/**/README.md`, `desktop/docs/` — the tracked, canonical documentation.

## Commands

### Backend (run from `backend/`)

```powershell
Copy-Item config\.env.example config\.env   # first time only
uv sync --group dev
uv run python -m alembic upgrade head
uv run uvicorn app.main:app --reload        # http://localhost:8000/docs

powershell -ExecutionPolicy Bypass -File scripts\start_backend.ps1  # sync + migrate + serve + log file
```

Validation:

```powershell
uv run ruff check .
uv run black --check .
uv run mypy app
uv run pytest -q
```

As of 2026-08-10 `pytest` is **green (248 unit + 24 integration)** and every test file also passes standalone — `tests/conftest.py` imports all model modules so `Base.metadata.create_all` sees the whole schema regardless of test order. Keep that list in step with `alembic/env.py`.

`tests/integration/` needs a real PostgreSQL server and **skips cleanly without one**. It covers what SQLite cannot express: platform tables being invisible to a firm schema, firm-scope resolution across deployment modes, two schemas holding independent rows, and ORM-vs-deployed-schema drift. Run it with `uv run pytest tests/integration -q`. Reach for it whenever a change touches tenancy, cross-schema foreign keys, triggers or concurrency — every defect in that class has been invisible to the unit suite.

**`app/` and `tests/` are clean under all four tools, and expected to stay that way.** `ruff check app`, `ruff check tests`, `black --check` and `mypy app` (320 files) all pass, so any finding in them is one you introduced. That was not true for most of this project's life -- this file claimed ~3,232 pre-existing findings and `mypy` failures outside `app/finance`, both of which stopped being true without the claim being updated, which is how a stale number talks people out of running the tools at all.

**`ruff check .` and `black --check .` are clean across the whole tree** as of 2026-08-14 -- `app/`, `tests/`, `scripts/` and `alembic/`. The 181 findings this file used to call permanent debt were 81 long lines, 49 missing docstrings and 32 missing annotations. Nothing about behaviour moved, and that was checked rather than assumed: every string literal and f-string in the seed scripts was compared by AST before and after, and every SQL statement in the six re-wrapped migrations is byte-identical once whitespace is normalised. A finding anywhere is now one you introduced.

Single test / single case:

```powershell
uv run pytest tests/unit/test_customer_management.py -q
uv run pytest -k "customer_scope" -q
```

If `uv run` fails on Windows with `uv trampoline failed to canonicalize script path`, that is a `uv` launcher bug — use `.\.venv\Scripts\python.exe -m pytest -q` (same for `mypy`, `black`, `ruff`).

Migrations and data:

```powershell
uv run python -m alembic current            # applied revision
uv run python -m alembic heads              # authoritative head (docs go stale — trust this)
uv run python scripts/generate_sample_data.py --yes   # see the warning below
uv run python scripts/verify_sample_data.py
uv run python scripts/seed_multi_firm_demo.py            # 4 firms + 2 years of trading
uv run python scripts/generate_transaction_history.py --firm WHOLE01 --years 2 --reset --yes
uv run python scripts/reset_tenancy_layout.py --yes   # destructive local rebuild of platform + firm_shared
```

**`app/core/database/all_models.py` is the one list of model modules.** `alembic/env.py`, `tests/conftest.py` and `scripts/generate_sample_data.py` all import it, so a new model module is added there and nowhere else; `tests/unit/test_schema_registry.py` fails the build if one is missing. Three hand-maintained copies used to exist and this file told you to keep two of them in step, which is how the sample-data reset fell 61 tables behind.

**`generate_sample_data.py --reset` derives its delete order** from `Base.metadata.sorted_tables` reversed, and clears each schema by name -- the seed session's `search_path` spans `platform` and `firm_shared`, so an unqualified delete hit whichever copy resolved first and left the other. `PRESERVED_TABLES` names the fourteen exceptions. It reaches **every firm store**, not just `platform` and `firm_shared`: the stores are read from the registry before the platform is cleared, because that registry is what says where they are. Their UOM reference data is re-seeded afterwards, since a store with no units cannot hold a product.

**No attribute is mandatory for every firm.** `20260801_0011` seeded EXPIRY_DATE, BATCH_NUMBER, MANUFACTURER and IMEI with `mandatory = True` and no category or profile scope, which asked a pharmacy for an IMEI and an electronics distributor for an expiry date -- and `AttributeService` refuses the write, so it blocked product creation on any freshly-migrated database. `20260815_0087` clears it. Where an attribute really is required, say so in `category_attribute_rules`, scoped to a business profile and a category.

`alembic upgrade head --sql` intentionally fails at `20260728_0004`, which inspects a live schema. Use `upgrade 20260728_0003 --sql` for offline bootstrap DDL.

### Migrations are per-schema — this is the biggest operational trap

`alembic/env.py` migrates exactly **one** schema per run, chosen by `AGENCY_DATABASE_SCHEMA` (default `platform`). Firm-owned modules live in `firm_shared` and in each dedicated firm schema/database, so a bare `alembic upgrade head` advances only the platform schema and silently leaves firm data schemas behind. That drift is invisible until a query hits a missing column — it had already broken every product read in all three firm schemas before it was noticed on 2026-08-09.

**Use `scripts/migrate_all_stores.py`.** It enumerates the targets from the
registry rather than from a list someone maintains by hand — the platform
schema, `firm_shared`, and every distinct dedicated database/schema pair, each
reached through its own connection profile so a firm on another server is
upgraded on that server:

```powershell
uv run python scripts/migrate_all_stores.py --dry-run   # targets + current revision
uv run python scripts/migrate_all_stores.py --yes       # upgrade them all
```

`--dry-run` prints the revision each store is at, which is the quickest way to
see drift; it found three stores a revision behind the platform the first time
it ran. It reports every store rather than stopping at the first failure, and
exits non-zero if any failed.

The per-target form still works when you need one store on its own — set
`AGENCY_DATABASE_SCHEMA` (and `AGENCY_DATABASE_NAME` for a dedicated database)
and run `alembic upgrade head`, then `Remove-Item Env:\AGENCY_DATABASE_*`.

Two rules follow for any migration that touches firm-owned tables:

1. **Guard cross-schema foreign keys.** `firms` exists only in `platform`; `customers`/`vendors` only in firm schemas. No firm-owned table in `firm_shared` carries a `firm_id` FK. Declare such references only when `sa.inspect(op.get_bind()).has_table(...)` finds the target — see `_external_fk` in `20260809_0042`.
2. **Make migrations idempotent.** Firm schemas are partly built by `Base.metadata.create_all` from the sample-data and tenancy-reset scripts, so objects can exist even when `alembic_version` reads older. Check before `add_column`/`create_table`; `20260808_0040` had to be repaired for exactly this. Backfill `UPDATE`s should target only rows still at their defaults so they cannot overwrite live data on replay.

### Desktop (run from `desktop/`)

```powershell
flutter pub get
flutter run -d windows --dart-define=API_BASE_URL=http://localhost:8000
flutter analyze
flutter test
flutter test test/purchase_ux_test.dart      # single test file
```

`./start.sh` (Git Bash) wraps clean/get/run with `--no-clean`, `--linux`, `--macos`, `--release` flags. Native runner directories are generated, not authoritative — regenerate with `flutter create --platforms=windows,linux,macos .` if missing. Windows secure-storage builds need Developer Mode enabled for plugin symlinks.

## Backend architecture

### Module layout

Every business domain is a top-level package under `app/` with the same five layers:

```
app/<domain>/{api/router.py, schemas/, services/, repositories/, models/}
```

Routers are thin adapters (validate, resolve scope, delegate); services own transactions, business rules, and audit writes; repositories own soft-delete-aware queries. Each router is registered explicitly in `app/main.py:create_app`. `app/customers` is the reference master-data module; `app/purchase` is the reference transactional module.

`app/core/` is the transport- and domain-independent framework (responses, error codes/exceptions, validation, pagination/filtering/sorting, request context, middleware, security, database, tenancy, concurrency, openapi, utils). It must stay free of business entities. `app/common/` holds cross-domain services: `audit`, and `scope.py` — the firm-scope dependency every firm-owned router composes. It lives here rather than in `core` precisely because it must reference `Firm` and `UserFirm`.

Eleven docstring-only packages (`app/platform`, `app/tenant`, `app/infrastructure`, `app/common/{files,notifications,sequences,shared}` and others) were deleted on 2026-08-09. They advertised subsystems that do not exist — backup, licensing, scheduling, notifications, file storage — and `app/common/sequences` in particular looked like the home of document numbering while the real implementation lives in `app/document_framework`. **Do not recreate an empty package to reserve a name.**

### Multi-tenancy — the thing to understand first

Requests carry an `X-Firm-ID` header. `app/core/database/dependencies.py` decides the session:

- Paths under `/health`, `/api/v1/{auth,users,roles,permissions,firms,dashboard,me}` are **platform** paths and always use the platform schema (`get_platform_db` semantics).
- Everything else goes through `FirmRegistryTenantResolver` → `MultiTenantDatabaseProvider`, which resolves a firm to `SHARED` (shared DB + `firm_shared` schema), `SCHEMA` (dedicated schema), or `DATABASE` (dedicated database). PostgreSQL `search_path` is applied per session.

**A firm can live on a different server.** `firm_storage_mappings.connection_profile` names an entry in `AGENCY_TENANCY_CONNECTION_PROFILES` (host, port, username, password); `NULL` means the platform server, which is what every firm was before 2026-08-10 — until then the profiles were parsed and then discarded with `_ = connection_profiles` in both consumers, so a "dedicated database" firm was only ever a second database on the platform host. Both the request path (`FirmConnectionResolver`) and the provisioning path (`TenantStorageLifecycleService`) now build their connection through the single `app/core/tenancy/connections.py` helper. They must stay on it: if they disagree, provisioning builds tables on one host while every request looks for them on another, and nothing reports the difference. A profile's `database_type` must match the platform dialect — `Settings._ensure_platform_database_type` enforces that at startup.

**Dedicated storage is built by an explicit action, not at creation.** `POST /api/v1/firms/{id}/provision` (platform admin) creates the database, creates the schema, runs `alembic upgrade head` against it and prunes the platform tables; `FirmService.create` only records the intent. A remote server that is slow or unreachable must not fail the creation of the firm record. `FirmRegistryTenantResolver` refuses a dedicated firm whose `provisioned_at` is NULL, so a firm cannot serve requests before its tables exist, and `provisioning_error` keeps the reason a build failed on the record instead of only in logs. Re-running is safe — every step is create-if-missing and the migration stops at head — so the same endpoint is the repair action. Alembic runs in a **subprocess**: it used to run in-process with `AGENCY_DATABASE_URL`/`AGENCY_DATABASE_SCHEMA` set through `os.environ`, which is process-wide, so two concurrent provisions raced and any other request reading settings mid-provision could resolve the wrong database.

Business services stay storage-agnostic: they receive a `Session` and never know the deployment mode. Default local layout is two schemas in one database — `platform` (identity, RBAC, firm registry) and `firm_shared` (firm-owned modules).

### Authorization

**Any code you pass to `require_permission` must also exist in `PERMISSION_GROUPS` in `app/identity/system_seed.py`.** An unseeded code has no permission row, so it cannot be attached to any role, and the endpoint silently becomes platform-admin-only (their check short-circuits the lookup). Twelve codes were in this state until 2026-08-09. `tests/unit/test_identity_hardening.py::test_every_enforced_permission_code_is_seeded` now fails the build if it recurs; adding codes to the seed also needs a migration to insert them into existing databases (see `20260809_0044`).

`Principal` + `require_permission("CODE")` from `app.core.security.authorization`. Firm-owned routers compose a scope dependency that (a) checks the permission code and (b) validates active `UserFirm` membership for `X-Firm-ID` — platform admins are **not** exempt from supplying a firm context on firm-owned resources. See the `_permission()` / `CustomerViewScope` pattern in `app/customers/api/router.py` and copy it. Permission codes are `DOMAIN_ACTION` (`CUSTOMER_VIEW`, `TAX_RULE_SIMULATE`) and are seeded in `app/identity/system_seed.py`; system roles/permissions are immutable via the API.

### Entities and responses

All business entities extend `BaseEntity` (`app/core/database/entity.py`): UUID id, created/updated actor + timestamp, `version` for optimistic concurrency, `is_deleted`/`deleted_at` soft delete. Repositories exclude soft-deleted rows unless explicitly asked. Audit logs are the exception — append-only, enforced by the `TR_audit_logs_append_only` trigger; every mutation must emit one via `app.common.audit`. **Every schema owns its own copy of that trigger and of the `reject_audit_log_mutation()` function it calls** (`20260809_0043`), so anything that shapes a firm store must leave both alone: `prune_platform_objects` used to drop the function `CASCADE`, which took the firm's trigger with it and left every dedicated store with a rewritable trail. `tests/integration/test_audit_append_only.py` is the guard, and it only bites now that CI prunes `firm_shared` the way provisioning does.

**The audit trail is per store, not central.** Platform administration writes to `platform.audit_logs`; every firm-owned mutation writes to that firm's own store, because `record_audit` runs on whichever session `get_db` resolved. That is deliberate — a DATABASE-mode firm's history has to live inside its own database for the isolation and per-firm restore guarantees to hold. The consequence: **no single query can answer "everything that happened"**; a cross-firm view must iterate firm stores. `GET /api/v1/audit-logs` reads one trail, chosen by firm context — no `X-Firm-ID` plus platform authority gives the platform trail, `X-Firm-ID` gives that firm's. Date filters are inclusive UTC calendar days, matching the `created_from`/`created_to` convention in the customer and product list filters.

Responses always use `ApiResponse` / `PaginatedResponse` from `app/core/responses/models.py` (`success`, `data`, `message`, `timestamp`, `requestId`, plus `pagination.{page,page_size,total_records,total_pages}`). List endpoints accept only the whitelisted `page`, `page_size`, `search`, `sort_by`, `sort_direction`.

### Cross-cutting frameworks

Prefer extending these over adding module-specific machinery:

- **Business Profile Framework** (`app/business`) — industry profiles decide which features and modules a firm operates. `docs/BUSINESS_PROFILE_FRAMEWORK.md` is the reference: table map, resolution flow, what is actually enforced versus merely recorded, and how to extend it. Never hardcode industry behaviour into entities; declare a feature and gate on it.
  - Enforce server-side with `require_feature("CODE")` / `require_module("CODE")` from `app/business/gating.py`, used exactly like `require_permission`. They are **write-only**: safe methods always pass, so enabling a gate can never hide data a firm already has. A firm with no profile resolves to the platform default (GENERIC). Those gate a whole **endpoint**, which only suits a feature that owns its own resource. Most features are optional *fields* on a resource every firm uses, so gating the endpoint would stop a firm creating products because it does not scan barcodes: for those call `assert_feature_fields(session, firm_id, feature=..., values={...})` from the service, which refuses the write only when it populates one of the named fields. Blank and unchanged always pass, and a firm with no resolvable profile is never gated — a configuration gap is not a decision. **Enforced as of 2026-08-12 — 11 of 21:** `BATCH_TRACKING` and `SERIAL_NUMBER` (endpoints), plus `EXPIRY_TRACKING`, `MANUFACTURING_DATE`, `SHELF_LIFE`, `WARRANTY`, `BARCODE`, `QR_CODE`, `DRUG_LICENSE`, `ATTACHMENTS` (all seven transactional modules) and `VEHICLE_TRACKING` (`delivery_note`, `goods_receipt`) (fields). Gating makes the seeded profile assignments load-bearing: if a profile omits a feature its firms were using, they lose that field. **`TERRITORY` is deliberately still ungated** — only AGENCY and WHOLESALE enable it, so enforcing it would take territory and route management away from the other nine profiles including PHARMACY, FOOD and RETAIL, all of which plausibly sell by territory on a distribution platform. The seed assignment is the thing that looks wrong, not the code; deferred on 2026-08-10 pending a decision about which profiles should have it, or whether territory is core and should not be a switch at all. `APPROVAL_WORKFLOW` and `MULTIPLE_WAREHOUSES` are ungated for the same reason: each needs a product decision first.
  - The desktop's `/active-modules` filtering is cosmetic and is *not* a security boundary — it only hides menu entries.
  - A 2026-08-10 survey split the 21 declared features: **12 have backing code** and are gateable (`EXPIRY_TRACKING`, `MANUFACTURING_DATE`, `SHELF_LIFE`, `WARRANTY`, `DRUG_LICENSE`, `VEHICLE_TRACKING`, `TERRITORY`, `BARCODE`, `QR_CODE`, `ATTACHMENTS`, `APPROVAL_WORKFLOW`, `MULTIPLE_WAREHOUSES`), and **7 had none in either application** — `IMEI`, `PRESCRIPTION_REQUIRED`, `RECIPE_MANAGEMENT`, `KITCHEN_MANAGEMENT`, `COMMISSION`, `SERVICE_CONTRACTS`, `PROJECT_MANAGEMENT`. Those seven are kept as roadmap and carry `business_features.is_implemented = false` (`20260810_0059`), which the service refuses to enable; the same migration withdrew the 17 profile claims that advertised them, including PHARMACY's `PRESCRIPTION_REQUIRED` and RESTAURANT's `KITCHEN_MANAGEMENT`. `is_implemented` is a fact about the codebase and is deliberately **not** `is_active`, which is an administrator's choice. **The catalogue lives in every firm store, not in `platform`** — migrate each firm target, and remember a firm's assignment is only visible from its own store (querying `firm_shared` makes the two dedicated-store firms look unassigned). Features and modules are toggled from the desktop administration workspace, which calls `setBusinessProfileFeatures` / `setBusinessProfileModules` on save. `docs/BUSINESS_PROFILE_FRAMEWORK.md` is verified against the running backend on 2026-08-12.

- **Configurable custom fields** — a module gains industry-specific fields through `AttributeService` (`app/business/services/attribute_service.py`), never by adding columns. An `AttributeDefinition` targets an `entity_type` (`PRODUCT`, `CUSTOMER`, `VENDOR`, …) and is optionally scoped to one business profile, so a pharmacy firm carries fields a food firm does not.
  - **The catalogue is shared; value storage is per module.** Each module owns a small table extending `AttributeValueBase` — `product_attribute_values` is the reference — which keeps a real FK to the owning record and its own indexes. The service is parameterised by that model, so there is still one implementation, one set of tests, and one form renderer.
  - Values live in typed `value_text` / `value_number` / `value_date` / `value_boolean` columns so list filters and reports can index and query them. Never store custom fields as JSON: a `products.category_attribute_values` blob existed until 2026-08-09 and could not be filtered.
  - **To extend a new module:** add an `AttributeEntityType` member, a ~20-line table extending `AttributeValueBase` with `ENTITY_TYPE` / `OWNER_COLUMN` set, a migration, and calls to `replace_values` on save and `values_for` / `values_for_many` on read.
  - Read attributes for a list of records with `values_for_many`, never per row — `ProductService._products_matching_attribute` shows the pattern for filtering.
- **Document Lifecycle Framework** (`app/document_framework`) — configurable document types, states, numbering rules, and timeline events for transactional modules. Lifecycle states are configuration, not enums.
- **Tax framework / rule engine** (`app/tax`) — `docs/TAX_FRAMEWORK.md` is the reference: how systems, components and profiles relate, what a profile actually holds, effective-dated rates, and the rule evaluation order (ACTIVE rules ordered by `priority ASC, code ASC, version_number DESC`, **first match wins and evaluation stops**). Rules attach to the transaction, never to a product; the product contributes `tax_profile_group_code`, `product_category_id` and `product_type` to the matching context.
- **UOM & packaging** (`app/uom`) — `docs/UOM_FRAMEWORK.md` is the reference: the seven unit slots a product carries, effective-dated conversion rules, and the resolution order (the product's own rule before the firm-wide one, ranked explicitly rather than by NULL sort). All seven transactional modules call `convert_quantity` per line, taking a `factor = 1` short-circuit only when the units match.
- **batch/serial/expiry** (`app/batch_serial`).

### Style enforced by tooling

ruff selects `E,F,I,N,UP,B,SIM,ANN,D` and mypy runs `strict` on `app` — every function needs full type annotations and a docstring, including nested helpers and test fixtures where ruff applies. Line length 88 (black).

## Desktop architecture

`main.dart` → `app.dart` → `ui/desktop_shell.dart` (the single shell). Modules are declared as data in `ui/workspace/module_catalog.dart` (`ModuleDefinition` with id, icon, workspace template, tabs, and `requiredPermissions`); the shell filters them by permission **and** by business-profile active modules. Adding a module means adding a catalog entry plus a workspace page — not new navigation code.

All UI composes the shared framework barrel:

```dart
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
```

which provides `WorkspaceLayout`, `ModuleWorkspaceFrame`, `ManagementWorkspaceLayout`, `WorkspaceDialog`/`CrudWorkspaceDialog`, `WorkspaceToolbar`, `SearchFilterPanel`, `EnterpriseDataGrid`, `StatusBadge`, `LoadingOverlay`, `StandardEmptyState`, `WorkspaceShortcuts`, and the context-menu/global-search helpers. Simple REST resources should be expressed as a `ResourceDefinition<T>` passed to `ResourceManagementPage<T>` — metadata and API callbacks only, no bespoke shell. Complex documents still use `WorkspaceDialog` with module-owned tab bodies. Feature modules must not define themes or hardcode colors; use `core/design/design_tokens.dart` and `ThemeManager`. Every screen must stay overflow-free from 1366x768 up.

`lib/core/api/api_client.dart` is the **only** place endpoint paths live; it also owns the `X-Firm-ID` header, the single automatic refresh-retry after a `401`, and the HTTPS-except-loopback rule. Only the refresh token is persisted, in the OS credential vault via `flutter_secure_storage`; passwords are never stored. Runtime branding comes from the external `config/branding.json` beside the executable.

Detailed contracts live in `desktop/docs/DESKTOP_FRAMEWORK.md`, `DESIGN_SYSTEM.md`, `UX_GUIDELINES.md`, and `COMPONENT_LIBRARY.md`.

## Module reviews

`docs/MODULE_REVIEW_CHECKLIST.md` holds the per-module review checklist, a debt
inventory (endpoints, ruff/mypy counts, test and desktop coverage per module), the
review order, and a progress table. The checklist items are derived from defects
that actually occurred, not generic advice. Update the progress table as modules
are completed.

## Testing

Backend tests are unit tests under `backend/tests/unit/`, one file per module. They build a **SQLite in-memory** engine with `Base.metadata.create_all` and a `StaticPool`, then call FastAPI route functions directly with hand-constructed `Principal`/scope objects — no running server or PostgreSQL required. Follow that pattern; new modules should keep their models SQLite-compatible for tests even though PostgreSQL is the deployment target. `backend/tests/integration/` exists but is empty.

Desktop tests are widget tests in `desktop/test/`, mostly per-module UX tests plus login and navigation-tree tests.

## Repository conventions and traps

- **Most root-level `*.md` files are untracked, generated AI reports.** `.gitignore` excludes root `*_REPORT.md`, `*_ARCHITECTURE.md`, `*_SUMMARY.md`, `*_REVIEW.md`, `*_GUIDE.md`, `*_FRAMEWORK.md`, `DEVELOPMENT_*`, `PLATFORM_*`, etc. Only `README.md` and `SECURITY_ARCHITECTURE.md` are tracked at root. Treat the rest as scratch context, not as a spec, and put durable documentation in `docs/`, `backend/**/README.md`, or `desktop/docs/`.
- Migration docs cite stale heads (`alembic/README.md` says `20260802_0021`; the versions directory is well past that). Always confirm with `uv run python -m alembic heads`.
- **`firms` and `user_firms` exist only in the platform schema.** A tenant session runs `SET search_path TO "<firm schema>"` with no fallback, so resolving them on the request session raises `UndefinedTable` for every firm outside the platform store. Every firm-owned router did exactly that until 2026-08-09. Compose `app/common/scope.py`, which resolves through `get_platform_db`; never write a private firm-scope resolver.
- **Foreign key names are `FK_<table>_<column>`, keyed on the referring column.** Keying on the referred table collides whenever one table has two foreign keys to the same target, which SQLite ignores and PostgreSQL rejects — that made `Base.metadata.create_all` unusable on PostgreSQL, and the sample-data and tenancy-reset scripts build firm stores with it.
- **No model may declare its own `version` column** — that name is the concurrency counter below, and a business version under it gets incremented by every ORM update. `tax` and `uom` both call theirs `version_number`; `uom.ConversionRule` was renamed in `20260809_0055` after the ORM was found moving the version documents record in `conversion_version`.
- **Bulk endpoints are a second implementation.** The six branch/warehouse bulk operations wrote no audit rows and skipped the delete guards their single-row twins enforced, so review both paths. The same module's two import endpoints looped over `create_branch`/`create_warehouse`, which commit, so a batch whose fifth row clashed returned 409 with the first four already written — and the corrected file then failed on those four as duplicates, making the import impossible to complete. Imports stage and commit once (`import_branches`/`import_warehouses`, the shape `CustomerService.import_customers` always had); the desktop dialog says so, because the user's first question after a failure is whether half of it went in. Exclusivity flags (`is_default`) are demoted in the service and backed by a partial unique index (`UQ_branches_default_active`, `UQ_warehouses_default_active`, `20260809_0056`); demotion must flush before the promoted row is written.
- **Never read the server's local clock.** Everything persisted here is UTC, so `date.today()` compares against a date the data does not use — on a non-UTC deployment it is already tomorrow, or still yesterday, for part of every day. It shipped three times (a UOM rule that was not yet effective, expiry buckets a day out, then the overdue reports and document numbering until 2026-08-10). Call `utc_now().date()`; `tests/unit/test_time_conventions.py` fails the build on any new occurrence. `func.now()` is fine — that is SQL the database evaluates.
- **Never let NULL ordering pick a row.** PostgreSQL sorts NULLs first in `DESC`, SQLite last, so `ORDER BY product_id DESC` made a firm-wide UOM conversion rule outrank a product's own factor in production while the unit suite saw the right answer. Rank on `case((col.is_(None), 1), else_=0)` and cover it in `tests/integration/`.
- **`BaseEntity.version` is the mapper's version id.** Every ORM update bumps it and checks it, so a stale write raises `StaleDataError` (mapped to 409). Bulk `query().update()` bypasses this by design. Update endpoints accept `If-Match` carrying the version the client last read.
- **Document lines are reconciled on their line number, not deleted and re-inserted**, in `sales_order`, `purchase`, `goods_receipt` and `delivery_note`. Downstream documents record `source_document_line_id` as a bare UUID with **no foreign key**, so re-inserting lines silently left those references dangling. The three invoice modules still re-insert; their lines are terminal.
- **`app/settlements` is money in and money out**, and it is one document for both directions: a receipt from a customer and a payment to a vendor differ only in signs. It posts to the general ledger through `DocumentPostingService.post_settlement`, and `settlements.journal_entry_id` is NOT NULL because the defect it exists to close is a settlement that never reached the ledger. ****A customer's opening balance posts** `Dr Accounts Receivable / Cr Opening Balance Equity` as of 2026-08-15, and is refused outright when the firm has no chart of accounts or open period -- a balance nobody can book is one the firm should not be told it has recorded. Revising one or deleting the customer mirrors the entry, traced through `customer_receivable_transactions.journal_entry_id`. `CustomerService.post_receivable_transaction` still moves a customer balance without writing a journal** -- it is the older, lower-level path and the two books drift by every rupee recorded through it, so record money through `/api/v1/receipts` and `/api/v1/payments` instead. What an invoice still owes is derived from `settlement_allocations`, never stored on the invoice. A settlement is reversed rather than edited or deleted: a mirror journal cancels it, the allocations stop clearing invoices but still record what they had cleared, and `CustomerService.reverse_receivable_transaction` puts the customer's balances back by the **deltas stored on the original row** -- never recomputed, because a receipt of 500 against an outstanding 300 splits into 300 of balance and 200 of advance and only that row remembers the split.
- `app/finance/` was rewritten on 2026-08-09 and is live at `/api/v1/finance` (migration `20260809_0042`). It uses the seeded `accounting` / `financial_year` permission codes rather than a `FINANCE_*` namespace. Automatic GL posting from invoices is **not** built: it needs a per-firm control-account mapping design. The prior `accounting_event_consumer.py`, which guessed accounts by name, was removed — see git history if you want its posting rules.
- Config is `pydantic-settings` reading `backend/config/.env` with the `AGENCY_` prefix; env vars override the file. `config/.env` is never committed. Staging/production refuse to start with the development JWT key or without an explicit bootstrap admin password.
- PostgreSQL 17 is the primary target; MySQL is supported by the connection layer but some constraints (the `UQ_user_firms_active_primary` and `UQ_users_email_active` partial indexes) are PostgreSQL-only — the matching service-level checks stay authoritative.
- `users.email` is unique **only among live accounts**, so soft-deleting a user releases their address for re-onboarding. Filter `is_deleted` in any email lookup. `firms.code`, `gst_number` and `pan_number` work the same way since `20260809_0054` — partial indexes named `UQ_firms_<column>_active`.
- **Demo data has a history.** `scripts/seed_multi_firm_demo.py` seeds the four demo firms and then drives two financial years of trading through the real services, so stock moves, receivables build and the ledger balances the way they would in use; `--no-history` restores the old masters-only behaviour. `scripts/generate_transaction_history.py` does one firm on its own and is what the seeder calls. Both go through the services rather than the tables, which makes them a blunt integration test — building history is what surfaced the accounting-period, receivable-scale and document-numbering defects fixed on 2026-08-10. `scripts/sql/check_backend_data.sql` holds the queries for checking the result by hand; read its header first, because firm-owned tables exist once per store.
- **Credit limits warn, and block only if a firm asks.** `customers.credit_limit` constrained nothing until `20260810_0057`. `CreditControlService` compares it against exposure — `current_outstanding - unapplied_advance + the document being saved` — at sales order and sales invoice approval, the two points where credit is committed. Policy is per firm in `credit_control_settings` (`OFF` / `WARN` / `BLOCK`, with warn and block percentages); a firm with no row warns at 80% and never blocks, and a `credit_limit` of zero means unset rather than no credit, so shipping this stopped nobody trading. `GET /api/v1/customers/{id}/credit-status?amount=` answers the question before a document is saved rather than reporting the breach after, and `GET`/`PUT /api/v1/customers/credit-settings` carries the policy. Writing the policy needs `CUSTOMER_MANAGE_SETTINGS`, deliberately **not** granted to `SALES_MANAGER`: the role the limit constrains must not be able to switch it off. The desktop **warns and never blocks**: `warnOnCreditExposure` (`desktop/lib/ui/sales/credit_notice.dart`) runs on Approve for sales orders and sales invoices, before the action so the document is not counted twice, and stays silent when `would_block` is true because the server's refusal already carries the same sentence. A client that blocked on its own would enforce a rule the firm may not have chosen and could be bypassed by any other client. The policy itself is edited from the Settings action on the customers workspace (`credit_settings_dialog.dart`), which is readable with `CUSTOMER_VIEW` — someone the policy warns should see the rule behind the warning — and writable only with `CUSTOMER_MANAGE_SETTINGS`.
- **A firm's storage routing is fixed at creation.** Nothing migrates a firm's rows between stores, so `FirmService.update` rejects any change to `deployment_mode`/`schema_name`/`database_name`/`connection_profile`, and omitted tenancy fields inherit the stored mapping instead of defaulting to `SHARED`. Two firms are never allowed to share one database/schema pair — soft-deleted firms included, because their data is still there. An unknown `connection_profile` is refused at create rather than at first use: a typo would otherwise produce a firm that provisions and serves nothing, failing far from the request that caused it.
- `refresh_tokens`, `login_history` and `password_history` have no automatic cleanup of their own, and neither does `tax_rule_execution_logs`. **`scripts/purge_retention.py` is the one to run**: it enumerates every firm store from the registry — dedicated schemas and dedicated databases included — and applies both retention services, so it cannot miss a store the way running the two single-purpose scripts by hand does. `--dry-run` reports, `--yes` applies. The `retention` service in `docker-compose.yml` runs it on a loop, and is **opt-in**: `docker compose --profile retention up -d`, because bringing the stack up should not start deleting rows on its own. Until someone enables it nothing prunes these tables, which is how they grew unbounded to begin with. `AGENCY_RETENTION_INTERVAL_SECONDS` sets the period (default daily) and `AGENCY_RETENTION_MODE=--dry-run` makes it report instead of delete. `scripts/purge_identity_history.py` and `scripts/purge_tax_execution_logs.py` remain for pruning one store on its own. `tax_rule_execution_logs` is the same shape and grows fastest — one row holding three JSON documents per document line — and is pruned per firm store by `scripts/purge_retention.py` (every store at once) or `scripts/purge_tax_execution_logs.py` (one store, selected with `AGENCY_DATABASE_SCHEMA` the way a migration does).
- **`TaxRuleService.simulate` is the tax calculation, not a preview.** All seven transactional modules call it once per line while building a document, on their own session, so it must never commit — the `/simulate` endpoint owns that. It also derives `country_id` from the applied profile's tax system and `business_profile_id` from the firm's assignment, because no document sends either and rules scoped that way otherwise never match. `total_tax_amount` is only what the counterparty is billed: tax `included_in_price` and tax under `REVERSE_CHARGE` are reported in `inclusive_tax_amount` / `reverse_charge_tax_amount` and must not be added to a document total.
