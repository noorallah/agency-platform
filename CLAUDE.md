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

As of 2026-09-02 `pytest` is **green (817: 784 unit + 33 integration)** and every test file also passes standalone — `tests/conftest.py` imports all model modules so `Base.metadata.create_all` sees the whole schema regardless of test order. Keep that list in step with `alembic/env.py`.

`tests/integration/` needs a real PostgreSQL server and **skips cleanly without one**. It covers what SQLite cannot express: platform tables being invisible to a firm schema, firm-scope resolution across deployment modes, two schemas holding independent rows, and ORM-vs-deployed-schema drift. Run it with `uv run pytest tests/integration -q`. Reach for it whenever a change touches tenancy, cross-schema foreign keys, triggers or concurrency — every defect in that class has been invisible to the unit suite.

**`app/` and `tests/` are clean under all four tools, and expected to stay that way.** `ruff check app`, `ruff check tests`, `black --check` and `mypy app` (370 files) all pass, so any finding in them is one you introduced. That was not true for most of this project's life -- this file claimed ~3,232 pre-existing findings and `mypy` failures outside `app/finance`, both of which stopped being true without the claim being updated, which is how a stale number talks people out of running the tools at all.

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
  - A 2026-08-10 survey split the 21 declared features: **12 have backing code** and are gateable (`EXPIRY_TRACKING`, `MANUFACTURING_DATE`, `SHELF_LIFE`, `WARRANTY`, `DRUG_LICENSE`, `VEHICLE_TRACKING`, `TERRITORY`, `BARCODE`, `QR_CODE`, `ATTACHMENTS`, `APPROVAL_WORKFLOW`, `MULTIPLE_WAREHOUSES`), and **7 had none in either application** — `IMEI`, `PRESCRIPTION_REQUIRED`, `RECIPE_MANAGEMENT`, `KITCHEN_MANAGEMENT`, `COMMISSION`, `SERVICE_CONTRACTS`, `PROJECT_MANAGEMENT`. Those seven are kept as roadmap and carry `business_features.is_implemented = false` (`20260810_0059`), which the service refuses to enable. **Six now: `COMMISSION` came off the list on 2026-09-03** (`20260903_0107`), because `app/commission` shipped on 2026-08-23 and the flag outlived the fact, so an administrator was refused a feature the platform had — **a flag recording what the codebase does has to be revisited when the codebase does it**, and nothing but a survey will find the next one; the same migration withdrew the 17 profile claims that advertised them, including PHARMACY's `PRESCRIPTION_REQUIRED` and RESTAURANT's `KITCHEN_MANAGEMENT`. `is_implemented` is a fact about the codebase and is deliberately **not** `is_active`, which is an administrator's choice. **The catalogue lives in every firm store, not in `platform`** — migrate each firm target, and remember a firm's assignment is only visible from its own store (querying `firm_shared` makes the two dedicated-store firms look unassigned). Features and modules are toggled from the desktop administration workspace, which calls `setBusinessProfileFeatures` / `setBusinessProfileModules` on save. `docs/BUSINESS_PROFILE_FRAMEWORK.md` is verified against the running backend on 2026-08-12.

- **Configurable custom fields** — a module gains industry-specific fields through `AttributeService` (`app/business/services/attribute_service.py`), never by adding columns. An `AttributeDefinition` targets an `entity_type` (`PRODUCT`, `CUSTOMER`, `VENDOR`, …) and is optionally scoped to one business profile, so a pharmacy firm carries fields a food firm does not.
  - **The catalogue is shared; value storage is per module.** Each module owns a small table extending `AttributeValueBase` — `product_attribute_values` is the reference — which keeps a real FK to the owning record and its own indexes. The service is parameterised by that model, so there is still one implementation, one set of tests, and one form renderer.
  - Values live in typed `value_text` / `value_number` / `value_date` / `value_boolean` columns so list filters and reports can index and query them. Never store custom fields as JSON: a `products.category_attribute_values` blob existed until 2026-08-09 and could not be filtered.
  - **To extend a new module:** add an `AttributeEntityType` member, a ~20-line table extending `AttributeValueBase` with `ENTITY_TYPE` / `OWNER_COLUMN` set, a migration, and calls to `replace_values` on save and `values_for` / `values_for_many` on read.
  - Read attributes for a list of records with `values_for_many`, never per row — `ProductService._products_matching_attribute` shows the pattern for filtering.
- **Document Lifecycle Framework** (`app/document_framework`) — configurable document types, states, numbering rules, and timeline events for transactional modules. Lifecycle states are configuration, not enums.
- **Purchasing end to end** (`app/purchase`, `app/goods_receipt`, `app/purchase_invoice`, `app/purchase_return`, `app/settlements`) -- `docs/PURCHASE_FRAMEWORK.md` is the reference: the four documents, their lifecycles, and which transitions reach outside their own module. Only four do -- completing a goods receipt posts stock, cancelling a completed one **reverses both the stock and the journal** as of 2026-08-18, and **the journal follows the stock** as of 2026-08-22 -- the reversal credits inventory with what the movement actually removed, at the moving average, and books the difference from the receipt price to `PURCHASE_PRICE_VARIANCE`. Mirroring the original entry instead credited inventory with a number no movement ever removed and put a seeded store 2,287.42 out in one cancellation -- it reversed only the stock until then, so the GL's inventory balance drifted above the warehouse by the value of every cancelled receipt. Two traps live in that reversal and are worth knowing before writing another one: `reverse_entry` copies the source module and id onto the mirror it posts, so a lookup filtering only on POSTED finds the mirror next time and reverses the reversal (match `reversal_of_id IS NULL`), and **a receipt that has been invoiced cannot be cancelled at all** because the invoice already cleared the accrual -- that is a purchase return. approving a purchase invoice posts the journal, and completing a purchase return takes stock back off -- **and cancelling that return takes its journal back off too, as of 2026-08-22**: until then it reversed the stock and left the payable, the input tax and the inventory credit standing, the same defect `goods_receipt` carried until 2026-08-18 and nobody thought to look for in its mirror; everything else is paperwork and status. `docs/PURCHASE_TO_PAYMENT_FLOW.md` traces order to payment end to end with the ledger lines each step raises, and `docs/SALES_TO_RECEIPT_FLOW.md` does the same for the sale -- quotation, order, delivery note, invoice, receipt -- both driven against a running backend rather than read off the code. Three things to know about an order's state, all of them repaired on 2026-08-18 after being driven against a running server. **Receiving moves the order**: `GoodsReceiptService._resync_order_status` writes `PARTIALLY_RECEIVED` and `RECEIVED` as receipts complete and walks it back as they are cancelled, derived by summing the completed receipts rather than incremented. `PARTIALLY_ORDERED` and `ORDERED` are still declared and still unwritten, and orders received before that date were not backfilled. **Approval cannot be skipped** -- `approve` on a draft is refused with "Submit the order first", and `_assert_order_receivable` now refuses a receipt against anything that is not APPROVED, PARTIALLY_RECEIVED or RECEIVED. It did not: a draft order could be received against and the receipt completed, which posts stock and posts to the ledger, so the approval step was bypassable by any client that did not filter its own picker -- the desktop did, which is why it went unseen, and the unit suite could not catch it because its own fixtures received against a draft. And **an edit no longer decides the status**: see the full-dump trap below. Editing an APPROVED order withdraws the approval and returns it to DRAFT, on the record as `purchase.approval_withdrawn`; editing a received one is refused outright, because its lines are what stock was posted at.
- **Tax framework / rule engine** (`app/tax`) — `docs/TAX_FRAMEWORK.md` is the reference: how systems, components and profiles relate, what a profile actually holds, effective-dated rates, and the rule evaluation order (ACTIVE rules ordered by `priority ASC, code ASC, version_number DESC`, **first match wins and evaluation stops**). Rules attach to the transaction, never to a product; the product contributes `tax_profile_group_code`, `product_category_id` and `product_type` to the matching context.
- **UOM & packaging** (`app/uom`) — `docs/UOM_FRAMEWORK.md` is the reference: the seven unit slots a product carries, effective-dated conversion rules, and the resolution order (the product's own rule before the firm-wide one, ranked explicitly rather than by NULL sort). All seven transactional modules call `convert_quantity` per line, taking a `factor = 1` short-circuit only when the units match.
- **Geography is one set of masters, and all four address-carrying modules name it.** `geo_countries` → `geo_states` → `geo_districts` → `geo_cities` → `geo_postal_codes` → `geo_localities`, per firm store. Customers, vendors, branches and warehouses each carry the six keys; `GeoAreaPicker` (`desktop/lib/ui/workspace/geo_area_picker.dart`) is the one control that fills them, so use it rather than a fifth copy of the cascade. **Customers are the odd one out and the reason there is a migration**: they had free text and no keys, where the other three had keys and no form. `20260816_0094` added the keys beside the text and backfilled only unambiguous matches. **The keys are the truth; the text is derived from them** by `CustomerService._apply_place`, because `city`, `state`, `country` and `postal_code` are NOT NULL and every report reads them -- a row whose `city` says one thing and whose `city_id` says another leaves nothing to say which a report should believe. An address naming no place keeps the text it was given. Two traps in the picker itself, both found by testing rather than by reading: a stored id that is not in the loaded list must stay as an item of its own, or `DropdownButtonFormField` asserts and the form saves as blank; and a rung must be loaded from the *new* selection rather than from `widget.value`, which the parent has not rebuilt yet in the frame the choice was made -- choosing a country loaded no states at all, and shipped that way because the first two screens' tests only ever chose one rung.
- **Territory, routes & beats** (`app/sales`) — `docs/TERRITORY_FRAMEWORK.md` is the reference: the firm-configurable hierarchy, what makes a node a route, the three keys on a customer assignment, how a beat plan becomes a call list, and how a sale gets filed against a round. Two rules to know before touching it. **A route's effective window is enforced** as of 2026-08-16 — it decides both whether a beat plan calls the round and whether a document may be tagged with it, judged on the document's own date. And **`PUT /{id}/customers` replaces the whole list**, with `visit_sequence` as position in it, so membership and order travel together; omitting `is_primary` means *leave it alone*, because sending it back would demote the round somebody chose and collide with the one-primary-per-shop key.
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

Backend tests are unit tests under `backend/tests/unit/`, one file per module. They build a **SQLite in-memory** engine with `Base.metadata.create_all` and a `StaticPool`, then call FastAPI route functions directly with hand-constructed `Principal`/scope objects — no running server or PostgreSQL required. Follow that pattern; new modules should keep their models SQLite-compatible for tests even though PostgreSQL is the deployment target. `backend/tests/integration/` is **not** empty -- it holds 33 tests and is described above; this line said it was empty long after it stopped being true.

Desktop tests are widget tests in `desktop/test/`, mostly per-module UX tests plus login and navigation-tree tests. `flutter test` is **green (931)** and `flutter analyze` is clean as of 2026-09-02.

## Repository conventions and traps

- **Most root-level `*.md` files are untracked, generated AI reports.** `.gitignore` excludes root `*_REPORT.md`, `*_ARCHITECTURE.md`, `*_SUMMARY.md`, `*_REVIEW.md`, `*_GUIDE.md`, `*_FRAMEWORK.md`, `DEVELOPMENT_*`, `PLATFORM_*`, etc. Only `README.md` and `SECURITY_ARCHITECTURE.md` are tracked at root. Treat the rest as scratch context, not as a spec, and put durable documentation in `docs/`, `backend/**/README.md`, or `desktop/docs/`.
- Migration docs cite stale heads (`alembic/README.md` says `20260802_0021`; the versions directory is well past that). Always confirm with `uv run python -m alembic heads`.
- **A firm-owned service reading a platform table opens the platform store**, with `platform_reader()` from `app/common/firm_metadata.py`. `users`, `firms` and `user_firms` exist **only** in the platform schema, so a tenant session cannot see them: territory search joined `users` for salesman names and answered 503 with `relation "wholesale_hub.users" does not exist` for every firm. Resolve the ids on the platform session, then match by id on the tenant one. **Fourth occurrence as of 2026-08-16**: global search ran every `SearchDefinition` on the request session, and four of them -- `users`, `roles`, `permissions`, `firms` -- are platform-owned, so one failing definition aborted the whole search and **every** Ctrl+K from inside a firm answered 503 for as long as the feature had existed. `SearchDefinition.platform_store` now marks them and they are read through `platform_reader()`. **Fifth, sixth and seventh on 2026-08-23**, all three on `salesman_id` and all latent because nothing ever sent one: the by-salesman reports read `users` for names, and then -- found the next day, after the reports were fixed -- `_validate_scope_references` in `sales_order` and `delivery_note` checked a caller's salesman with `select(User)` on the request session, so *raising* either document with a salesman named answered 503 for every firm outside the platform store. Reading a name and checking a name are different lines in different methods; fixing one did not fix the other -- and the seventh was `sales_invoice`'s own copy of the same check, missed again, which only surfaced when the demo seed first put a salesman on a round and every document began deriving one. **The seed is what makes this class of defect visible**: three of these lived through months of green suites because no seeded document exercised them. **`GET /api/v1/firm-members` is now the one list of a firm's people**, gated on membership of the firm and nothing else -- there were three copies behind `TERRITORY_ASSIGN_SALESMEN`, `COMMISSION_VIEW` and `USER_VIEW`, and the sales-order form could call none of them, so it offered no salesman field at all. A firm's own directory of names is not a privilege; *acting* on a person is what needs one, and those gates are unchanged. Validating a salesman now also asks whether they are a member of **this** firm, which the old `select(User)` did not -- one firm could tag another firm's people on its own documents. Note what the flag is *not*: "has no firm column" cannot decide this, because `geo_countries` and its siblings have no firm column either and live in every firm store. The authority is `_PLATFORM_TABLES` in `app/core/tenancy/lifecycle.py` -- the list provisioning drops from a firm store -- and a unit test compares the two. The defect itself is only visible in `tests/integration/`: the unit suite builds one SQLite schema holding every table, so `users` is always reachable there.
- **A route nothing calls is where whole features have gone missing.** Three have come off that list -- `category_attribute_rules`, the two vendor masters, and `product_packaging_levels` -- each unusable for months. `tests/unit/test_routes_have_a_caller.py` is the inverse of `test_desktop_calls_reach_a_route.py` and pins the four routes deliberately left without one, so a new orphan fails the build rather than waiting to be rediscovered by hand. It does not forbid them: adding one is a deliberate act with the reason recorded in `_ACCEPTED`.
- **A literal path must be declared before `/{id}` in the same router.** FastAPI matches in declaration order, so `sales_territories` had `/{territory_id}` above `/dashboard`, `/search`, `/beat-plans` and `/export` -- all four were read as a territory id and answered 422 "Input should be a valid UUID", so the Geography dashboard had never shown a number and beat plans could not be listed at all. **Nine more were found on 2026-08-22, in eight routers**: `vendors/categories` and `vendors/types` (which is why those two masters had no caller -- neither list had ever returned a row) and the `GET /export` of `branches`, `warehouses`, `sales-orders`, `delivery-notes`, `goods-receipts`, `purchase-invoices` and `purchase-returns`. Every one had been unreachable since the day it was written. `tests/unit/test_route_declaration_order.py` walks the built application and fails the build on the next one, so this is now a caught mistake rather than a remembered one.
- **A platform endpoint touching firm-owned data must open that firm's store**, with `firm_store_session(request, firm_id)` from `app/core/database/dependencies.py`. `get_db` routes on the caller's `X-Firm-ID`, which is right for a firm-scoped request and silently wrong for a platform screen administering another firm: the business-profile assignment endpoints read `none` for any firm in a different store and **wrote the assignment into the caller's store while returning success**, so the firm named in the URL kept its old profile. MEDI01 and FOOD01 hid it by sharing `firm_shared`. A list across firms iterates the stores -- `GET /business-framework/firm-profile-assignments` is the pattern -- and reports a store it could not read rather than blanking the row.
- **`firms` and `user_firms` exist only in the platform schema.** A tenant session runs `SET search_path TO "<firm schema>"` with no fallback, so resolving them on the request session raises `UndefinedTable` for every firm outside the platform store. Every firm-owned router did exactly that until 2026-08-09. Compose `app/common/scope.py`, which resolves through `get_platform_db`; never write a private firm-scope resolver.
- **Foreign key names are `FK_<table>_<column>`, keyed on the referring column.** Keying on the referred table collides whenever one table has two foreign keys to the same target, which SQLite ignores and PostgreSQL rejects — that made `Base.metadata.create_all` unusable on PostgreSQL, and the sample-data and tenancy-reset scripts build firm stores with it.
- **No model may declare its own `version` column** — that name is the concurrency counter below, and a business version under it gets incremented by every ORM update. `tax` and `uom` both call theirs `version_number`; `uom.ConversionRule` was renamed in `20260809_0055` after the ORM was found moving the version documents record in `conversion_version`.
- **A bare `ResolvedFirmScope` parameter is read by FastAPI as a request body field.** `ResolvedFirmScope` is a plain dataclass; the injectable form is `RequiredFirmScope` (`Annotated[..., Depends(required_firm_scope)]`) from `app/common/scope.py`. Nineteen handlers on the sales router took the bare class, so every geography write and `PUT /hierarchy-levels` answered 422 demanding `body.payload` and `body.scope` — uncallable since the day they were written, and invisible because nothing called them. Grep for `scope: ResolvedFirmScope,` before adding a platform-admin endpoint.
- **Declare `page` and `page_size` bounds on the query parameter, not by constructing `PaginationParams` inside the handler.** Swept across all 23 routers on 2026-08-21 and guarded by `tests/unit/test_pagination_conventions.py`, which fails the build on a handler that takes a bare `page: int = 1` or `page_size: int = 20`. `MAX_PAGE_SIZE` is 100 and the model enforces it — but constructing the model in the body of the function turns an over-cap request into a pydantic error *after* routing, which surfaces as a **500** rather than a 422 naming the limit. Two desktop screens shipped asking for `pageSize: 500` and were broken against every real backend while their tests, whose fakes ignore the value, stayed green. Client-side use `fetchAllPages` (`desktop/lib/ui/workspace/paged_fetch.dart`); server-side use `Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]`.
- **A partial unique index cannot be `DEFERRABLE`, so a swap must release before it reassigns.** `UQ_territory_customer_assignments_sequence_active` keeps two shops off one stop number, and PostgreSQL checks it per statement — so reassigning row by row collided the moment two rows exchanged values, which is exactly what dragging one stop above another does. `set_customers` clears the numbers it is about to hand out, flushes, then writes them, and clears **only** the ones actually moving so a re-save that says nothing about order leaves the sequence alone. Any "reorder within a set" that grows a uniqueness key needs the same shape.
- **A screen that replaces a whole list must prove it read that list first.** `PUT /{id}/customers` and the salesmen twin replace rather than merge, so the pane on screen *is* the record. Both territory screens clear the pane **before** the read rather than after it succeeds, and refuse to save until the pane provably holds the selected route — without that, a failed read left the previous route's shops on screen and one Save wrote them over a different round.
- **`ondelete="RESTRICT"` is not a guard on a soft-deleted table.** Every foreign key into the six geography tables is RESTRICT, which reads like protection; a soft delete never reaches the database's referential check, so a "deleted" city would stay wired to every branch naming it and simply vanish from the list. The refusal has to live in the service, and it has to look at the level below *and* at everything outside the module — addresses, branches, warehouses, route profiles.
- **An update that dumps its whole write model turns an omission into an instruction.** A write schema gives every optional field a default, so `model_dump()` returns a value for a field the caller never mentioned, and assigning all of them writes that default over live data. It has now shipped twice. `VendorUpdate`'s six child collections defaulted to `[]` and the API replaces rather than merges, so correcting a phone number destroyed a vendor's addresses, contacts, bank accounts, tax details, attachments and notes -- one seeded vendor had already lost its address. `BranchUpdate`/`WarehouseUpdate` did the scalar version: one rename cleared the branch's street lines, its city, its default flag and its GST registration, and a warehouse's ten capability flags, because the desktop form edits none of those and hardcoded `false` for the flags. Both now dump with `exclude_unset=True` on update only, so **absent means leave alone and an explicit `null` still clears** -- the distinction that makes a partial client safe without stopping a complete one clearing a field. Create is unchanged: there a default really is the value to store. Anything read from such a dump needs the row as its fallback (`values.get("is_default", row.is_default)`), or a promotion becomes a demotion. **A status field is the worst case of this shape, and `update_order` in `app/purchase` had it until 2026-08-18.** `PurchaseOrderUpdate` defaults `status` to DRAFT and the service assigned it straight onto the row, so a client that said nothing about the status silently reset an APPROVED order -- and a PARTIALLY_RECEIVED one, which nothing could then move back, because the receipt resync only touches an order already in the receiving part of its life. The desktop hid it by echoing back the status it last read, which produced the mirror-image fault: an approved order could be edited to any amount and stay approved. **A lifecycle status belongs to its transition endpoints and must never be writable through the update body**; the fix was to stop reading `data.status` at all, not to make the dump partial. **All eight remaining full-dump updates were made partial on 2026-08-21** -- `update_{attribute,category_rule,feature,module,profile}` in `app/business` and `update_{numbering_rule,state,type}` in `app/document_framework`. `update_profile` also reads `is_default` from the dumped values with the row as its fallback, because reading it off the model made an omission mean False: renaming the default profile demoted it and left the store with no default at all. Creates still dump in full, which is right -- there a default really is the value to store.
  **`app/customers` joined on 2026-08-23** and brought the child collections
  with it: `addresses` and `contacts` are replaced rather than merged, so
  reconciling one the caller never sent soft-deleted every row in it, and a
  full dump of the scalars reset `credit_limit`, `payment_terms_days` and the
  new `default_discount_percent` on any partial request. Both are now guarded
  on `model_fields_set`, and `opening_balance` is read out of the dumped values
  with the row as its fallback -- reading it off the model made an omission
  mean zero, which the balance-reset guard then acted on.
- **Bulk endpoints are a second implementation.** The six branch/warehouse bulk operations wrote no audit rows and skipped the delete guards their single-row twins enforced, so review both paths. The same module's two import endpoints looped over `create_branch`/`create_warehouse`, which commit, so a batch whose fifth row clashed returned 409 with the first four already written — and the corrected file then failed on those four as duplicates, making the import impossible to complete. Imports stage and commit once (`import_branches`/`import_warehouses`, the shape `CustomerService.import_customers` always had); the desktop dialog says so, because the user's first question after a failure is whether half of it went in. Exclusivity flags (`is_default`) are demoted in the service and backed by a partial unique index (`UQ_branches_default_active`, `UQ_warehouses_default_active`, `20260809_0056`); demotion must flush before the promoted row is written.
- **Never read the server's local clock.** Everything persisted here is UTC, so `date.today()` compares against a date the data does not use — on a non-UTC deployment it is already tomorrow, or still yesterday, for part of every day. It shipped three times (a UOM rule that was not yet effective, expiry buckets a day out, then the overdue reports and document numbering until 2026-08-10). Call `utc_now().date()`; `tests/unit/test_time_conventions.py` fails the build on any new occurrence. `func.now()` is fine — that is SQL the database evaluates.
- **Never let NULL ordering pick a row.** PostgreSQL sorts NULLs first in `DESC`, SQLite last, so `ORDER BY product_id DESC` made a firm-wide UOM conversion rule outrank a product's own factor in production while the unit suite saw the right answer. Rank on `case((col.is_(None), 1), else_=0)` and cover it in `tests/integration/`.
- **`BaseEntity.version` is the mapper's version id.** Every ORM update bumps it and checks it, so a stale write raises `StaleDataError` (mapped to 409). Bulk `query().update()` bypasses this by design. Update endpoints accept `If-Match` carrying the version the client last read, and **every response that returns one versioned record publishes that version as an `ETag`** through `set_etag` in `app/core/concurrency.py` — the `GET`/`PUT` pair for firms, purchase orders, sales orders, delivery notes, goods receipts and customers. Publish it on any new endpoint of that shape: five routers accepted the header for months while no response carried the version anywhere, so the only value a client could honestly send was `*`, which means no precondition. A client should echo the `ETag` it was given rather than compute the next version — an update can advance the counter by more than one. Sending nothing is still accepted, so the precondition is opt-in and existing clients keep working. **The version is also a field on those six response bodies**, which is not duplication: a header carries one value and a list carries many records, and the desktop opens its editors from list rows rather than re-reading the record, so an ETag alone could never reach the screen that needs it. The desktop sends `If-Match` for **every module that publishes a version** as of 2026-08-22 -- customers, vendors, products, branches, warehouses, quotations, UOM, tax, batch/serial, inventory, territories (including places and beat plans) and the business-profile catalogue, which the backend accepts even though no desktop screen edits it yet. Two shapes of wiring: a service that returns the row uses `set_etag`, and `app/sales`, which builds its response models in the service, uses `publish_version` with the number. **A save that changes nothing does not move the counter**, so a second save with the same `If-Match` is accepted -- correct, and worth knowing before writing a test that expects a 409 from re-sending an unchanged record. **UOM and tax joined on 2026-08-22**, which needed a name first: a conversion rule and a tax rule each publish a revision of their own, and `uom` exposed that as `version` — the one name the counter has to have. The revision is `version_number` everywhere now (the column's name, and how `tax` always spelled it) and `version` is the counter. The rename found a second copy of the rule resolver in `app/inventory` matching a line's stored revision against the *counter*, which agreed only until somebody edited a rule. Client-side the message differs by editor shape: a dialog that saves from inside keeps the user's typing on a refusal and says so, one that closes first does not — see `concurrencyMessage(noun, changesKept:)`. A record whose `version` is absent reads as zero client-side and saves with no precondition, so an older backend stays usable.
- **Document lines are reconciled on their line number, not deleted and re-inserted**, in `sales_order`, `purchase`, `goods_receipt` and `delivery_note`. Downstream documents record `source_document_line_id` as a bare UUID with **no foreign key**, so re-inserting lines silently left those references dangling. The three invoice modules still re-insert; their lines are terminal.
- **A ledger leg facing stock is valued from the movement; a leg facing a counterparty is valued from the document.** Every forward posting already did this -- receipt, dispatch, both returns, both adjustment paths all read `StockLedgerEntry`. All three *reversals* broke it, and all three were fixed on 2026-08-22: a cancelled goods receipt and a cancelled purchase return credit inventory with what the movement removed and book the gap to `PURCHASE_PRICE_VARIANCE`, and a cancelled sales return's cost entry posts both legs at the movement value so the gap stays in cost of goods sold. Goods arrive at one average and leave at another; mirroring an entry across that gap is what puts a store out.
- **No line editor may prefill a discount box.** `resolve_line_discount` ranks an explicit percentage above the price list, so filling the box turns an inherited arrangement into an override. The quotation editor filled it with the customer's standing rate -- and with a literal `0` where they had none, which the server reads as a refusal of every arrangement -- so **no price list could reach a quotation raised from the desktop at all**, from the day price lists shipped. Driven against a running backend: the same line resolved to a 15% list saying nothing and to nothing saying `discount_percent: "0"`. Both sales line editors now leave the box blank and *say* what blank takes; the reasoning behind the prefill (a salesman must see the rate) was right, and helper text is the honest version of it, because the form cannot resolve which arrangement is in force.
- **A line discount is resolved in one place**, `app/core/utils/pricing.py`, and
  every sales and purchase document calls it: an explicit amount beats an
  explicit percentage, which beats `customers.default_discount_percent`, which
  beats nothing. `docs/SALES_TO_RECEIPT_FLOW.md` is the reference. Three things
  to know before touching it. **`None` and `0` are different answers** -- saying
  nothing takes the customer's standing rate, sending zero refuses it for this
  line -- which is why the discount fields on the nine line-write schemas are
  `Decimal | None` with no default; giving them `Decimal("0")` back makes an
  omission indistinguishable from a refusal and switches the arrangement off
  for everybody. **The percentage was stored and never applied** by
  `sales_invoice`, `sales_return`, `purchase_invoice` and `purchase_return`
  until 2026-08-23: all four read the discount *amount* alone for both the tax
  base and the subtotal, so a ten percent order was invoiced at full price with
  `discount_percent = 10` sitting on the line as a lie, and the three documents
  upstream did apply it, so the order looked right and the bill did not match
  it. And **the recorded rate is derived from the amount applied**, not echoed
  from the request -- a line saying 10% and 50.00 against 1,000.00 is one
  nobody can reconcile. The discount reduces the taxable value, so it is
  applied before tax and revenue is booked net of it; a discount above the line
  or a rate above a hundred is refused, which only `goods_receipt` did before.
  An invoice **inherits from the line it bills** rather than re-reading the
  customer, so an edit to the master in August cannot rewrite a price agreed in
  March; a rate inherits as itself, an amount is pro-rated by the share billed.
- **Promotions stack; tax does not.** `app/promotions` copies `app/tax`'s shape
  -- rule, typed condition rows, action rows, execution log -- but where the tax
  engine breaks at the first match, the promotion engine applies every matching
  offer in `priority ASC, code ASC, version_number DESC, created_at ASC` order
  until one with `allow_stacking = false` is applied. Two consequences worth
  knowing before touching it. **Percentages compound on what is left**, so two
  stacked ten percent offers take nineteen percent -- which is the retail
  meaning and also the only basis on which stacked benefits cannot exceed the
  line, and `resolve_line_discount` refuses one that does. And **a stacking
  engine must collapse to one live version per `version_group_id`**: superseding
  leaves the predecessor ACTIVE and tax survives that only by stopping at the
  first match, so copying its query verbatim hands the customer the same offer
  twice -- 190.00 for one ten percent promotion, which is what the guard was run
  against before the collapse existed. The result feeds one new tier in
  `app/core/utils/pricing.py`, between what was typed and the price list, and
  `PromotionService.evaluate` never commits for the reason
  `TaxRuleService.simulate` never does. A line somebody priced by hand is
  skipped and the trace says so: a log that reports a benefit the line never
  received is a lie told to the person asking why the price is what it is.
- **A delivery note ships the deal the order struck.** It re-read the customer's
  *current* standing rate and the price lists instead of inheriting the order
  line it ships, so a rate agreed in March was replaced by whatever the master
  said in August -- the exact thing the invoice's own inheritance rule exists to
  prevent, one document earlier. Worse once promotions existed: an offer is
  applied when the order is priced, the note discarded the result, and the
  invoice inherits the *note*, so a customer promised a promoted price was
  billed the undiscounted one. Seeded data showed it plainly -- order lines at
  1, 5, 5.95, 7.5 and 8.425 percent, and 43 of 58 note lines at zero. Fixed
  2026-09-03: `_line_discount` inherits the source line, a rate as itself and an
  amount pro-rated by the share shipped, and the price list and standing rate
  are deliberately not consulted -- the order resolved both already, so a line
  that came out at nothing came out at nothing on purpose.
- **A claim on an offer is counted at approval, never while a document is
  priced.** `promotion_redemptions` records PENDING when the engine prices a
  document, CLAIMED when it is approved under a `with_for_update` lock on the
  promotion, and REVERSED when it is cancelled -- and **only CLAIMED counts
  against a limit**. A counter on the promotion would have to be written during
  pricing, which must never commit, so it would either publish a half-written
  order or count a draft edited five more times and never approved. Two
  behaviours follow and both are deliberate: an offer already exhausted is
  **not quoted at all**, so nobody is promised a price the approval would
  refuse; and two documents priced while it still had room race at approval,
  where the loser is **refused by name** rather than silently repriced --
  changing an agreed price underneath somebody is not the service's decision.
  A coupon is a way of reaching an offer, not a second kind of one: the
  benefit, the conditions and the stacking rule stay on the promotion, and
  `sales_orders.coupon_code` is on the order rather than the quotation because
  the order is what gets approved. An unrecognised code leaves the order
  saveable and simply gives nothing -- a typo in a field that gives money away
  must not refuse a sale.
- **`customer_type` is a legal classification, not a commercial one.** It holds
  INDIVIDUAL or BUSINESS, and hanging a price or an offer on it was never
  possible. `customer_groups` is the firm's own segmentation -- Retailer,
  Wholesaler, Institution -- added 2026-09-03 with `customers.customer_group_id`
  nullable and unassigned, so no existing document changed price. A flat list
  rather than a tree: `sales_territories` is already a hierarchy and a second
  one leaves two answers to "which group is this customer in". The segment's
  rate is the **last** tier of `resolve_line_discount`, below the customer's
  own standing rate, because a rate agreed with one shop is more specific than
  one agreed with a segment of them. Deleting a group somebody is in is refused
  **in the service**: `ondelete="RESTRICT"` is not a guard on a soft-deleted
  table, so a retired group would otherwise stay on every customer's record
  while vanishing from every list -- the same trap the geography masters have.
- **A price list holds a ladder, not a rate.** `price_list_items.min_quantity`
  is the quantity a rate starts at, and `PriceListResolver.rate_for(product,
  quantity)` takes the **highest break at or below** the line -- so 0, 50 and
  200 prices a line of 120 at the 50. Zero is the ordinary rate, which is what
  every existing row became, so no list changed what it promised. Two things to
  know: the unique key had to widen to `(list, product, min_quantity)` or a
  list could still hold only one row per product, which is the whole
  limitation; and a **more specific list replaces the ladder rather than
  merging into it** -- a customer's own arrangement is the arrangement, not an
  amendment to the firm-wide one, and merging would silently give them breaks
  nobody agreed with them.
- **A discount on the whole document reaches the lines, and therefore the tax.**
  `bill_discount_percent`/`bill_discount_amount` on a quotation, sales order,
  delivery note or sales invoice is resolved by `resolve_bill_discount` and
  split by `apportion` (`app/core/utils/pricing.py`) across the lines in
  proportion to what each is worth *after* its own discount, then stored on
  each line as `bill_discount_amount`. Three things follow. It comes off what
  the lines discounted to, **never off the gross** -- off the gross each
  discount is computed as though the other had not happened. The share has to
  be **stored and taxed**, not derived at print time: `header_discount_amount`
  on a purchase order is subtracted *after* tax, so it reduces no taxable value
  and the counterparty pays tax on money they were never charged -- that shape
  is deliberately not copied to sales. And the rounding residual goes to the
  **largest** line so the shares sum exactly to the figure they split; a
  document whose lines do not add up to its own total is one no reconciliation
  can accept. A conversion carries the *deal* and re-splits it, because copying
  each line's share agrees only while both documents hold the same lines; a
  sales return **inherits** its share pro-rata from the line it credits, since
  crediting the undiscounted figure hands back more than was charged. All four
  sales services price every line before taxing any of them for this reason --
  `sales_invoice` carries the intermediate state in `_PricedInvoiceLine`.
- **A bill can state what was given away.** `free_quantity` is goods supplied at
  nil value: outside the gross and outside the tax base, but real stock leaving
  the warehouse. It existed on quotation, sales order and delivery note lines
  and **not on the sales invoice** until 2026-08-23, so goods could be
  promised, ordered and dispatched free and then not appear on the document the
  customer reads. The invoice **inherits** it from the line it bills, pro-rated
  by the share being billed, and **refuses** more than the source line offered
  -- the goods left on somebody else's document, and a bill claiming free goods
  nobody dispatched is one the warehouse cannot reconcile. The desktop's
  quotation editor is the only screen that can give a line away; there was no
  field for it anywhere before, so the column was unreachable without the API.
- **What may be billed is what was charged, not what left the warehouse.** A
  delivery note line holds both figures and they are not interchangeable:
  `current_delivery_quantity` is what the customer is charged for, and
  `delivered_quantity` is that plus the free goods converted into inventory
  units, which is right for stock because all of it left. `sales_invoice`
  capped billing on the second until 2026-08-24 and was wrong three ways for
  it. It **let a bill charge for the gift** -- a seeded note dispatching 12
  with 1 free had all 12 billed and still offered a thirteenth unit, accepted
  at 195.00 plus tax. It pro-rated the inherited free goods by the wrong
  denominator, so a full bill carried 12/13 of a free unit and printed
  "12 + 0.923 free". And the units disagree -- `invoice_quantity` is converted
  into the source line's *sales* UOM, `delivered_quantity` is post-conversion
  inventory units -- so for any product whose two units differ the cap was
  inflated by the whole conversion factor. The siblings were checked and are
  right: `purchase_invoice` and `purchase_return` cap on `accepted_quantity`,
  which excludes free goods, and `sales_return` on
  `current_delivery_quantity`. **A quantity that has had free goods added to
  it or been converted into another unit is not a billing cap**; the only
  reason this survived was that every test billed from a sales order, where
  the field is plain `quantity`, so the delivery-note path had no coverage at
  all. Found by reading a rendered bill rather than the code.
- **`FREE_PRODUCT` gives something the document never mentioned, so the engine
  emits a line rather than setting a field.** `FREE_QUANTITY` gives more of
  what was bought and adjusts an existing line; there is no line to adjust for
  a different product. `PromotionEvaluationResponse.gifts` is what the engine
  answers with, and `SalesOrderService._gift_lines` appends them **before
  anything is priced**, so a gift flows through conversion, tax and totals on
  the same path a typed line does. The threshold is counted across the lines
  the offer **matched**, not per line -- ten bought as two lines of five is
  still ten. No threshold means give it once, because the condition is then on
  the document. A gift the caller already typed is not doubled. And the gift
  line sets `discount_percent` to an **explicit zero**: silence would let the
  customer's standing rate resolve, and the line stores the rate it resolved,
  so a bill for nothing would print a discount percentage. Making that true
  exposed a hole in `resolve_line_discount` -- on a zero-gross line the
  recorded rate came off `percent or price_list_percent or customer_default
  or ...`, which is falsy for an explicit zero, so a refusal recorded the
  customer's rate. It reads the branch actually taken now.
- **A downstream document inherits the price of the line it continues.** A
  delivery note ships at the order line's price and an invoice bills at the
  note line's, where the caller says nothing -- the same rule the discount and
  the free goods already followed, and for the same reason: re-deciding the
  price one document later is how an agreement gets quietly rewritten.
  `unit_price` on both line-write schemas is `Decimal | None` with **no
  default** for exactly the None-versus-zero reason everything else here is:
  silence means "whatever was agreed" and zero means goods given away. It used
  to default to `Decimal("0")`, so the two were the same value and a caller
  that named a source line and omitted the price got a note valued at nothing
  and a bill for nothing -- no refusal, and nothing on the document to say
  why. Nothing was broken in practice because the desktop and the seeder both
  passed it, which is also why it survived: **the fixtures repeated the price
  too, so every test proved the number it had just supplied**. Found by
  driving the chain with minimal payloads.
- **Free shipping waives the charge; it does not discount it.**
  `PromotionActionType.FREE_SHIPPING` sets the document's `freight_amount` to
  nothing, so nothing is charged for delivery and nothing is taxed on it -- a
  document showing a delivery charge beside a discount cancelling it says
  something different from one showing no charge. The action takes **no
  parameter**: a partial waiver is `BILL_DISCOUNT_AMOUNT`, which already
  exists. The engine is told the charge (`freight_amount` on the request) and
  answers `freight_waived`, because it cannot waive what it has not been told
  about, and an offer on a document with no delivery charge gives nothing
  rather than claiming to. Waived whole or not at all, so two offers cannot
  waive it twice -- and the waived amount counts towards `benefit_amount`,
  since a campaign that gave away shipping cost the firm exactly that.
- **A margin rule needs a cost the invoice remembers, and NULL is not zero.**
  `commission_rules.measure` is VALUE or MARGIN; MARGIN pays on the money less
  what the goods cost, which is a different arrangement rather than a
  different rate -- a firm selling at a thin markup pays far less on the same
  turnover. The cost was always recoverable from `stock_ledger_entries`, which
  records the moving average that actually left the warehouse, but reading it
  at report time answers about *today's* average, so a payout approved in
  March would disagree with the report beside it. It is **snapshotted onto
  `sales_invoice_lines.cost_amount`** when the bill is raised, the same reason
  a payout is snapshotted at accrual. The column is **nullable and NULL is not
  zero**: an invoice raised straight off an order has no dispatch behind it,
  so nothing moved and nothing was costed, and zero would say the goods were
  free -- which on a margin rule pays commission on the whole sale price. Such
  a line contributes nothing rather than being guessed at, and a sale below
  cost earns nothing rather than a negative, because clawing it back off other
  sales is an arrangement nobody asked for.
- **Freight is the bill discount's mirror image, and it has to reach the
  line.** `freight_amount` on the four sales documents is what the customer is
  charged for delivery, and it is **part of the taxable value**: a charge the
  seller makes for getting the goods to the buyer is part of the value of the
  supply. It is apportioned across the lines by the same `apportion`, on the
  same weights (what each line is worth after its own discount), with the
  residual to the largest line -- one lowers each line's taxable value and the
  other raises it. Being on the line is the whole point: a document-level
  figure that never touches a taxable value taxes nothing, which is what
  `header_discount_amount` does on a purchase order and is deliberately not
  copied. `additional_charges` stays **outside** the tax and is left alone --
  it is for additions that really are outside it, and re-taxing it would
  change every document that carries one. A line discounted to nothing carries
  no freight; freight and a bill discount both survive on the line rather than
  netting; and both `app/gst_returns` and the e-invoice payload put it inside
  the taxable value, since leaving it out declares less than the invoice
  charged tax on.
- **Applying money already received posts no journal, and only part of it
  moves the balance.** `settlements.sales_order_id` records which order a
  deposit came in against -- a note, not a ring-fence: cancelling the order
  does not make the deposit vanish. `POST /api/v1/receipts/{id}/allocate` is
  the other half, and it was missing entirely: `ADVANCE_APPLY` had been a
  declared receivable type since the settlements module shipped with
  **nothing able to reach it**. Two rules. **No journal** -- the receipt
  debited cash and credited receivables, the invoice debited receivables; the
  allocation only decides which invoice the credit belongs to, and a journal
  would count the money twice. And **only the part that became an advance
  moves the customer's balance**: a receipt splits when it is recorded,
  `min(amount, outstanding)` off the balance and the excess into advance, so
  posting `ADVANCE_APPLY` for the whole allocation double-counts. The first
  version did, and a deposit taken while the customer already owed something
  -- the ordinary case -- was refused outright with "exceeds unapplied
  advance". `_advance_part_of` reads the split off the receipt's own
  receivable row and subtracts what earlier allocations used, or the last of
  an advance is stranded for ever.
- **A hold on a sales order is a flag, not a status.** An order that is
  PARTIALLY_DELIVERED can be held, and releasing it has to put it back to
  PARTIALLY_DELIVERED -- writing HOLD into `status` would destroy the only
  record of how far the order had got and the release would have to guess.
  Nothing is overwritten, so nothing has to be restored; it is the same
  reasoning `update_order` was repaired on. **The stock stays reserved** --
  holding says "not yet", not "never", and releasing the goods would let
  another order take them while this one waits; cancelling is what gives stock
  back. The refusal lives in `DeliveryNoteService.stage_note` rather than
  `create_note`, so `SalesChainService` is covered by the same line, and it
  **names the reason** because whoever hits it is the one who has to get the
  hold lifted. A hold is an operational stop, **not a credit control** -- that
  is `credit_control_settings`, which acts at approval.
- **A dialog owns its own `TextEditingController`.** A caller that creates
  one, awaits `showDialog` and then disposes it, disposes it *mid-animation*,
  and the field rebuilding during the exit throws "A TextEditingController was
  used after being disposed". An `AlertDialog` also gives its content
  unbounded height, so a stretched `Column` with no width overflows by tens of
  thousands of pixels instead of laying out. Both were written twice in one
  afternoon before `askForReason` in
  `desktop/lib/ui/workspace/reason_prompt.dart` existed; use it rather than a
  third copy. It returns null for a dismissal **and** for an empty box, so a
  caller has one answer to check.
- **A proforma posts nothing, and the absence of anywhere to record that it
  did is the design.** `app/proforma` states what an approved sales order will
  be charged, for a buyer who needs the figure before the goods move -- a
  letter of credit, a payment approval, a customs entry. Neither table carries
  a `journal_entry_id` or a `receivable_transaction_id`; adding one is the
  first step towards a document that looks like a bill to the books as well as
  to the customer, and the unit suite counts journal and receivable rows after
  issuing rather than trusting the absence. **Its number comes from its own
  `PI` series, never the tax invoice's** -- GSTR-1's DOCS section declares the
  invoice series, so a proforma drawn from it would either leave a gap the
  return cannot explain or put a number in it that was never a supply. **Its
  lines are snapshotted**, not read live: an order can be edited afterwards,
  withdrawing its own approval as it goes, and a document somebody is
  arranging payment against must not change underneath them. Once ISSUED it
  cannot be edited -- a revision is a new document with `supersedes_id`
  pointing back -- and withdrawing keeps the row, because the customer holds a
  copy.
- **A statement's running balance is recomputed in date order, never read
  off `outstanding_after`.** That column on
  `customer_receivable_transactions` is a snapshot taken when the row was
  written, in the order things were *recorded*; a statement is read in the
  order things were *dated*. Money arriving against last month's bill is
  recorded after it and dated before it, so the stored figure shows a balance
  that never existed on any day. `CustomerStatementService` sums the opening
  balance from the deltas before the period -- the same arithmetic that
  produced the current balance -- rather than subtracting the period's
  movement from today's, which is right only while nothing is backdated.
  **And an ageing row reconciles against the account and says how**: the
  bills and the balance are not the same number, because a credit note or a
  sales return reduces the account and sits on no invoice while TCS raises it
  without being billed. One seeded customer's bills read 27,150.98 against an
  account of 21,230.48; `total_outstanding - unapplied_credits +
  charges_not_billed` is now the balance exactly, and the buckets always sum
  to `total_outstanding`. Two reports about one customer that disagree with
  nothing to explain the gap is a bug report waiting to be filed.
- **Tax collected at source is charged on the money, not on the bill.**
  `app/tcs` implements 206C(1H), and the statute says "at the time of receipt
  of such amount" -- so the event that raises it is a **receipt**, never an
  invoice being approved, and `SettlementService.create` stages it. Putting it
  on the invoice collects on money that may never arrive and misses money that
  arrives against an older bill. Five rules follow. **Only the excess counts**
  -- the first fifty lakh a buyer pays in the year attracts nothing, so a
  receipt straddling the line pays on the part above it; charging the whole
  receipt over-collects by the entire remaining headroom. **The running total
  is summed from the receipts**, never a counter, net of refunds and excluding
  the receipt being charged -- counting that one would make the first receipt
  over the threshold pay on itself. **The financial year is the firm's own**,
  read off `financial_year_start`, because the threshold resets with it.
  **A seller below the turnover threshold collects nothing**, and that
  turnover is *stated* rather than derived: the preceding year may predate
  this system. And **the tax raises what the buyer owes** (`Dr Accounts
  Receivable / Cr TCS Payable`, account **2500** -- not 2200, which is Output
  Tax; TCS is filed on a different return on a different cycle). `is_enabled`
  defaults false so shipping it charged nobody, and `TCS_MANAGE` is not
  granted to `SALES_MANAGER` for the reason the credit policy is not.
  The direction check is `SettlementDirection.RECEIPT`, not `"IN"` -- the
  first version compared against a string the column never holds, so it
  collected nothing anywhere and only the tests said so.
- **A return is a view of the documents, and a supply is placed by the tax it
  was charged.** `app/gst_returns` stores nothing: GSTR-1 and the outward half
  of 3B are derived on every read, so a cancelled invoice drops out and a
  credit note lands in the month it was *issued*. Three rules, each of them a
  defect found by driving it. **The place of supply is read off the tax** --
  CGST with SGST is chargeable only within one state, IGST only between two,
  so the document settles it, and for an unregistered buyer nothing else can;
  the first version read a `state_code` field `customers` does not carry, so
  every B2CS row filed a **blank** place, which the portal rejects. Where the
  tax says a border was crossed and the buyer is unregistered, the invoice is
  named in `unplaced_invoices` rather than filed blank. **A credit note to an
  unregistered buyer is netted off its B2CS row**, not filed in CDNR and not
  dropped -- dropped, on the belief this system could not produce one, 3B
  deducted a credit GSTR-1 never declared and the two returns could not be
  reconciled. And **3B is aggregated from the documents, never parsed out of
  GSTR-1's own JSON**. `quantize_ledger` is the filing scale: documents carry
  four decimals, no portal takes them, and the rounding happens once on the
  way out or the HSN summary and the invoice detail drift apart a paisa at a
  time. `split_components` in `app/tax/services/gst_buckets.py` is the one
  place a component code becomes a bucket, shared with `app/einvoice`, so what
  is filed and what was registered cannot disagree.
- **A credit note's receivable is rounded the way its journal rounded it.**
  Third occurrence of the four-decimals-into-a-two-decimal-receivable defect
  -- `sales_invoice` hit it and fixed it privately, `sales_return` carried the
  identical bug untouched, and `app/credit_note` was the third: approving a
  note whose total ran past two decimals raised a pydantic error rather than
  posting, so the whole approval failed. Rounding the *sum* is not rounding
  the *parts*, so the receivable takes `quantize_ledger(taxable) +
  quantize_ledger(tax)` -- what the journal actually credited -- or the two
  books sit a paisa apart with nothing to say which is right. Invisible until
  a seeded credit note reached it, which is what the demo history is for.
- **A master field added later never reaches a store already seeded --
  third instance, and this one billed no tax for two years.** The batch flags
  were the first, the HSN code the second, and `tax_profile_group_code` the
  third: WHOLE01's toothpaste was seeded before its firm had a tax profile,
  kept a NULL, matched no tax rule, and **every sale of it was billed with no
  GST at all** -- 37,105 of supplies across two financial years, and nothing
  said so until a GST return reported a nil-rated row nobody had asked for.
  `seed_multi_firm_demo.py` now backfills it beside the other two, only where
  missing. Expect a fourth; the demo's masters are skipped on a re-run by
  design, so every new field on one needs a backfill written with it.
- **A sandbox registration must never read as a filing.** `app/einvoice`
  registers invoices and raises e-way bills, and `mode` is NOT NULL on both
  tables with **no server default** -- a default is one migration away from
  silently being LIVE. The sandbox marks every reference it mints (`SBX...`)
  so a number carried away from its row still says what it is, and the desktop
  shows the mode beside it everywhere. `portal_for("LIVE")` raises rather than
  falling back: a firm that believes it is filing must never be rehearsing.
  The payload is refused **locally, naming the field** (no GSTIN, no HSN)
  rather than sent to return a numeric code, and the CGST/SGST-versus-IGST
  split is read off the two GSTINs' **state codes**, so the document and its
  tax cannot disagree. One registration and one bill per invoice by unique
  key; a refusal lands on the row and a retry counts the attempt; withdrawal
  is inside 24 hours judged in UTC, and afterwards a credit note is the way.
  Live filing needs only GSP credentials and one implementation of
  `InvoiceRegistrationPortal`.
- **`as_utc()` in `app/core/utils/dates.py` reads a stored timestamp.**
  `UTCDateTime` is `DateTime(timezone=True)` and **SQLite ignores the
  timezone**, so what PostgreSQL returns aware the unit suite returns naive.
  Anything comparing a stored timestamp to `utc_now()` raises "can't subtract
  offset-naive and offset-aware datetimes" in the tests and works in
  production, or the reverse. Everything stored here is UTC, so a naive value
  is one that lost its label leaving the database -- say so once, there.
- **`FirmMetadataReader` carries the firm's name and GST number** as well as
  its code and financial year. `firms` is platform-only, so a firm-owned
  service reading it on the request session raises `relation
  "<firm schema>.firms" does not exist` -- the eighth occurrence, caught by
  `test_no_service_resolves_firms_on_a_tenant_session` rather than in
  production. Any new platform fact a firm-owned service needs goes on that
  reader, never on a fresh `select(Firm)`.
- **A master field added later never reaches a store already seeded.**
  `seed_multi_firm_demo.py` skips firms, customers and products that exist, so
  the firm's GSTIN, the customers' GSTINs and one product's HSN were all
  absent -- and **no invoice could be registered with the tax authority at
  all** until each was backfilled. All three are now backfilled *only where
  missing* and never overwritten, beside the batch flags which had the same
  problem first. Expect this every time a master gains a field the demo needs.
- **A credit note that states its lines reverses tax; the bare receivable
  adjustment does not.** `post_credit_note` posts two legs -- receivable and
  sales returns -- because a `customer_receivable_transactions` row carries one
  figure and no lines, so it has nothing to say what rate to take off. A firm
  correcting a rate after invoicing therefore kept declaring output tax on a
  price nobody paid. `app/credit_note` is the document that closes it:
  `post_credit_note_document` posts the third leg. It is **not** a sales
  return -- a return moves stock and this moves none -- and it always names
  the invoice **and the line**, because the rate is derived from what that
  line was actually charged rather than read off a tax profile that may since
  have been edited. The cap is the line's charged value less what other live
  credit notes took; **sales returns are deliberately not netted off**, since
  a return may have sourced from a delivery note that cannot be mapped back to
  an invoice line. Approving posts *and* moves the customer balance, or
  neither. `CREDIT_NOTE_APPROVE` is separate from `CREDIT_NOTE_MANAGE` and not
  granted to `SALES_MANAGER`: drafting is bookkeeping, approving reverses a
  declared tax.
- **A line whose whole content is a gift is not a line that has been billed.**
  Nothing charged, goods supplied free -- the shape a "buy ten of this, get
  two of that" offer needs. Such a line has a remaining quantity of zero from
  the moment it is written, and three separate places read that as *fully
  billed*: the note-level filter in `billable_documents` hid the whole note,
  `_billable_line` dropped the line, and `_invoice_free_quantity` pro-rated
  the gift by a charged share of zero and returned nothing. So the goods left
  the warehouse and the document the customer reads was silent about them --
  the same fault the ordinary case had until 2026-08-23, in the one shape
  nobody had tried. Fixed 2026-09-03. **A gift line is owed until an invoice
  line references it, counted in rows and never in quantity**: zero minus zero
  is zero however many times it has been stated, so the quantity test that
  stops an ordinary line being billed twice can never stop this one. Found by
  driving a nil-charge line through the chain by hand, which is also the only
  way to see it -- every fixture in the suite billed a line that charged for
  something.
- **A firm chooses which stages of a sale its people type**, per stage, in
  `sales_workflow_settings` -- `quotation_stage`, `sales_order_stage`,
  `delivery_note_stage`, the invoice always typed. A firm with no row types all
  four, so nothing changed for any existing firm. `SalesChainService`
  (`app/sales_invoice/services/sales_chain_service.py`) raises whatever is
  switched off by driving the same services a person would, so **the documents
  are real**: stock still leaves at dispatch and cost of goods sold still
  belongs to the delivery note. Making the invoice move stock itself was
  rejected deliberately -- it needs a second inventory path in a module that has
  never touched stock, and strands `_already_invoiced_quantity` and
  `sales_return`'s cap on `current_delivery_quantity`, both keyed off the chain.
  A column per stage rather than a mode, because a firm grows: an enum needs a
  new value for every combination on that path. The switch governs **new**
  documents only, so turning a stage on never strands work in flight.
- **A chain of committing services is not a transaction, and `begin_nested` does
  not make it one.** In SQLAlchemy 2.0 `Session.commit()` commits the outermost
  transaction and closes the savepoint, so wrapping does nothing -- verified
  against this repo's own version rather than assumed. Every step of the sales
  chain used to commit, so a failure at invoice approval left an approved order
  and a **DISPATCHED** delivery note written: goods gone from the warehouse with
  nothing owed for them. The seven methods are now split into `stage_*`
  internals that flush and public wrappers that commit -- the shape
  `CustomerService.import_customers` has always had. **Compose the `stage_*`
  methods and commit once**; the public ones are for a caller that owns nothing
  else. That split also made `import_orders`, `import_notes` and
  `import_invoices` genuinely atomic: all three said "atomically" in their
  docstrings while looping over a committing create.
- **A flag the caller sets to permit itself is not a control.**
  `allow_direct_sales_order` was a boolean on the invoice body that let a bill
  be raised against a sales order with no delivery note -- and since the invoice
  posts no stock and no cost, that reachable state produced revenue with no cost
  of goods sold, stock that never left, and a reservation open for ever. It is
  now the firm's `delivery_note_stage`, and the column records how a bill was
  raised rather than authorising it. Of 147 invoices in the seeded stores, none
  carried the flag and all were billed off delivery notes, so nothing needed
  migrating.
- **A sales order's status follows its deliveries as of 2026-08-23**, the way a
  purchase order has followed its receipts since 2026-08-18.
  `DeliveryNoteService._resync_order_status` writes `PARTIALLY_DELIVERED` and
  `DELIVERED` on dispatch, **derived by summing the notes that have left the
  warehouse** rather than incremented -- an incrementing counter and a reversal
  are two chances to disagree. Only an order already in the delivering part of
  its life is moved. Two traps came with it. The gate on raising a delivery
  note compared a **sales order's** status against `DeliveryNoteStatus`
  members, which agreed only because both enums spell APPROVED and CLOSED the
  same; writing the new status would have made it refuse every second delivery,
  so a part-shipped order could never be completed. And the service still lets
  a DELIVERED order be cancelled -- true before and invisible, because such an
  order read APPROVED -- so the desktop gate lists the new statuses rather than
  disabling a button the API accepts. Orders predating the change are not
  backfilled, as on the purchase side.
- **`app/settlements` is money in and money out**, and it is one document for both directions: a receipt from a customer and a payment to a vendor differ only in signs. It posts to the general ledger through `DocumentPostingService.post_settlement`, and `settlements.journal_entry_id` is NOT NULL because the defect it exists to close is a settlement that never reached the ledger. ****A customer's opening balance posts** `Dr Accounts Receivable / Cr Opening Balance Equity` as of 2026-08-15, and is refused outright when the firm has no chart of accounts or open period -- a balance nobody can book is one the firm should not be told it has recorded. Revising one or deleting the customer mirrors the entry, traced through `customer_receivable_transactions.journal_entry_id`. `CustomerService.post_receivable_transaction` still moves a customer balance without writing a journal** -- it is the older, lower-level path and the two books drift by every rupee recorded through it, so record money through `/api/v1/receipts` and `/api/v1/payments` instead. What an invoice still owes is derived from `settlement_allocations`, never stored on the invoice. A settlement is reversed rather than edited or deleted: a mirror journal cancels it, the allocations stop clearing invoices but still record what they had cleared, and `CustomerService.reverse_receivable_transaction` puts the customer's balances back by the **deltas stored on the original row** -- never recomputed, because a receipt of 500 against an outstanding 300 splits into 300 of balance and 200 of advance and only that row remembers the split.
- `app/finance/` was rewritten on 2026-08-09 and is live at `/api/v1/finance` (migration `20260809_0042`). It uses the seeded `accounting` / `financial_year` permission codes rather than a `FINANCE_*` namespace. Automatic GL posting from invoices is **not** built: it needs a per-firm control-account mapping design. The prior `accounting_event_consumer.py`, which guessed accounts by name, was removed — see git history if you want its posting rules.
- Config is `pydantic-settings` reading `backend/config/.env` with the `AGENCY_` prefix; env vars override the file. `config/.env` is never committed. Staging/production refuse to start with the development JWT key or without an explicit bootstrap admin password.
- PostgreSQL 17 is the primary target; MySQL is supported by the connection layer but some constraints (the `UQ_user_firms_active_primary` and `UQ_users_email_active` partial indexes) are PostgreSQL-only — the matching service-level checks stay authoritative.
- `users.email` is unique **only among live accounts**, so soft-deleting a user releases their address for re-onboarding. Filter `is_deleted` in any email lookup. `firms.code`, `gst_number` and `pan_number` work the same way since `20260809_0054` — partial indexes named `UQ_firms_<column>_active`.
- **Demo data has a history.** `scripts/seed_multi_firm_demo.py` seeds the four demo firms and then drives two financial years of trading through the real services, so stock moves, receivables build and the ledger balances the way they would in use; `--no-history` restores the old masters-only behaviour. `scripts/generate_transaction_history.py` does one firm on its own and is what the seeder calls. Both go through the services rather than the tables, which makes them a blunt integration test — building history is what surfaced the accounting-period, receivable-scale and document-numbering defects fixed on 2026-08-10. `scripts/sql/check_backend_data.sql` holds the queries for checking the result by hand; read its header first, because firm-owned tables exist once per store. **The history exercises the pricing rules too, as of 2026-08-23** -- one customer per firm on a standing 7.5% discount, a bill-level discount every fourth month and a free unit every third -- so the apportionment is driven across all three tenancy modes rather than only in SQLite. Before that none of the three pricing features appeared anywhere in the demo. **It collects money and names a salesman as of 2026-08-23 too**, and both were bigger holes than they look. Every store had **zero** rows in `territory_salesman_assignments` while every customer sat on a round, and `_validated_salesman` refuses anybody who does not cover the customer's territory -- so naming a salesman was refused on every customer of every firm, `_derived_salesman` had nobody to derive, and no document anywhere carried a `salesman_id`. That is why three separate `select(User)` calls on the tenant session survived for months. And every store had **zero** settlements: two financial years, 49 invoices a firm, and not one rupee collected, so receivables only ever grew, `app/settlements` was exercised by nothing, and commission -- earned on money collected -- could only report zero. The seeder now puts two salespeople per firm on the rounds, collects three invoices in four (one of those in part), and declares a firm-wide rate plus one person on a better one, so the precedence is visible rather than described. **It raises quotations and both kinds of return as of 2026-08-24**, which were the last three document types holding zero rows anywhere -- and each turned up something. Completing a sales return passed a four-decimal document total into a receivable amount capped at two, so it raised a pydantic error rather than posting: `sales_invoice` had hit and fixed that exact bug in a *private* helper its sibling never saw, and `quantize_ledger` in `app/core/utils/money.py` is now the shared one. Completing a purchase return refused any line that did not name a warehouse, where `sales_return` falls back to the header's -- and the header's is mandatory -- so such a return could be raised and approved and then never completed. And an offer cannot be sent, accepted or converted once `valid_until` has passed, judged against today and rightly so, which means a backdated history can only convert quotations inside the current window; the rest are declined or left to lapse, which is the ordinary fate of an offer anyway.
- **The demo seeds the incentives as of 2026-09-03**, and each firm carries
  four commission arrangements rather than one: the firm-wide default, one
  person's own flat rate, a **product-scoped** rate for that same person, and
  a **ladder** with a floor and a target bonus for the other. One target is
  met and one missed, and one payout of two is paid. Before this every store
  held zero targets and zero payouts, which is the state that has hidden every
  defect in this repo worth finding. Three things it taught on the first run.
  **`promotion_redemptions` and `promotion_coupons` were missing from
  `RESET_ORDER`**, so `--reset` failed outright on any firm whose documents
  had claimed an offer. **`seed_multi_firm_demo.py` printed the tally and
  threw `tally.skipped` away**, so a firm seeding differently from its
  siblings was invisible from the entry point everybody uses -- it prints the
  notes now, and the very next run reported two firms seeding a different set
  of rules. And **who gets which arrangement is chosen from the rules that
  exist, never positionally**: reading the salesmen in id order put the ladder
  on somebody who already had a flat rate in two firms of four, the overlap
  guard refused it, and those stores seeded with no slabs at all. The scoped
  rule names a **product** rather than a category because these firms carry a
  single category, where a category rule would cover every line and show
  nothing.
- **A hand-written `op.create_table` must spell out the timestamp defaults,
  or the table cannot be inserted into at all.** `TimestampMixin` declares
  `created_at`/`updated_at` with `server_default=func.now()`, so
  `Base.metadata.create_all` builds them with a default and SQLAlchemy leaves
  the column out of every INSERT. A migration that writes the two columns
  without `server_default=sa.text("CURRENT_TIMESTAMP")` builds a NOT NULL
  column with no default, and the **first** write raises `NotNullViolation`.
  The unit suite cannot see it -- it builds its schema from the ORM, so the
  default the migration forgot is always there in the tests. Found by driving
  a real firm; `20260903_0114` set the default on every undefaulted column in
  every store, which turned out to include all **twelve `tax` tables**, live
  since they were written and usable only because `TaxFrameworkService` passes
  `created_at=now` by hand on every insert.
  `tests/integration/test_multi_schema_tenancy.py::test_every_deployed_table_can_be_inserted_into`
  is the guard.
- **A commission rule has a floor and a target bonus, and both are fields on
  the rule.** `minimum_amount` earns **nothing at all** below it and pays on
  **all** of it above -- deliberately not a zero-percent bottom slab, which
  pays from the first rupee once the ladder is climbed and is a different
  deal. `bonus_percentage` is an extra percentage on the same value, paid only
  when the salesman's targets over the period were met, and added **before**
  the cap so a firm's ceiling still holds. A field rather than a second rule
  because two live rules over one person's days are refused, and weakening
  that guard to allow a bonus rule would reopen the defect it exists to close.
  **Targets over a window are judged taken together** (the achievements summed
  against the targets summed), because requiring every month makes an annual
  bonus unearnable and requiring one makes it unmissable. **Somebody with no
  target reports `target_met: null`, not false**, and earns no bonus: nobody
  set them a number, so there is nothing they failed. **Margin-based
  commission landed on 2026-09-03**: `sales_invoice_lines.cost_amount`
  snapshots what the goods cost when the bill was raised, off the stock
  ledger's own moving average.
- **A commission rule can be about goods, and the report resolves per line.**
  `product_id`/`product_category_id` on `commission_rules` make a rule a
  statement about lines rather than about the document, resolved in **six
  rungs of specificity** -- the person's own product rule, their category
  rule, their unscoped rule, then the same three firm-wide. Whose rule it is
  outranks what it is about, or a firm-wide rule naming a product would
  override a rate somebody negotiated. **An unscoped rule must keep measuring
  exactly the document**: the report apportions each invoice's own
  `grand_total` across its lines with `apportion` (the bill-discount helper),
  so the shares sum to the invoice -- deriving a share from the line's own
  `net_amount` instead drifts by whatever the header carries and silently
  changes what every existing rule pays, which has a test. On the COLLECTED
  basis a scoped rule takes its share of **each receipt** in the same
  proportion, because a payment clears a share of every line it settles. An
  invoice with no readable lines contributes as a single unscoped line, so
  money that exists is still measured by a rule about the document.
  `rate_type` PER_UNIT multiplies **quantity** and ignores value and slabs
  entirely; it is refused on the COLLECTED basis (money has no cases) and
  refused without a product or category (it would add cases of biscuits to
  litres of oil). Commission is measured on the document total, which
  **includes tax** -- whether that is right is an open question for the owner
  and deliberately not changed, because changing it moves every payout.
- **A commission payout is snapshotted, and it posts.** `commission_payouts`
  goes DRAFT → APPROVED → PAID, or CANCELLED. **The report is read once, at
  accrual, and never again** -- it walks live documents, so re-reading it would
  answer differently after a settlement is reversed or a rate corrected, and
  the journal posted at approval would then disagree with the record beside
  it. One live payout per person per overlapping period, or the same
  collections are paid twice; a CANCELLED one holds no claim, which is what
  makes a period accrued at the wrong rate correctable. Approval posts
  `Dr COMMISSION_EXPENSE / Cr COMMISSION_PAYABLE` and payment
  `Dr COMMISSION_PAYABLE / Cr` the money account -- two purposes, because an
  approved payout is a liability that outlives the month it was earned in.
  Both are nominated per firm in `firm_control_accounts`, and the seeded chart
  carries `5600` and `2400` (**not** 2200, which is Output Tax). Adjustments
  need a reason and only work on a draft. `COMMISSION_PAY` is separate from
  `COMMISSION_MANAGE` and **not** granted to `SALES_MANAGER`: whoever states a
  debt must not be the one who moves the cash. Two traps found by driving it:
  a journal reference is unique, so the accrual, the payment and the reversal
  need distinct ones (`...`, `...-PAY`, `...-REV`) or an approved payout can
  never be paid; and `JournalEntryEngine._load_accounts` already scopes
  accounts to the firm, so a second check in the calling service changes no
  outcome and was removed.
- **Commission is a ladder, a basis and a ceiling, not one rate.**
  `commission_rules` still holds a flat `percentage`, and a rule with no slabs
  still pays it -- but a rule with `commission_rule_slabs` ignores that column
  entirely, so never show it beside a ladder. `slab_mode` decides whether the
  bands read MARGINAL (each portion at its own rate) or WHOLE_AMOUNT (all of it
  at the band reached); they pay very differently on the same numbers, so it is
  declared rather than inferred. `basis` is COLLECTED or INVOICED and **a rule
  pays on one of them** -- the overlap guard refuses a second live rule over
  one person's days whatever its basis, which is what stops a firm changing
  over from paying twice for one sale. `max_commission_amount` is applied
  **after** the ladder, so it caps what was earned rather than what was sold.
  A ladder must start at zero, meet exactly and be open-ended only at the top.
  And the governing rule is resolved per row on its own date, then each rule's
  subtotal is laddered separately -- pooling a person's whole period would
  carry one arrangement's volume into another's thresholds.
- **Credit limits warn, and block only if a firm asks.** `customers.credit_limit` constrained nothing until `20260810_0057`. `CreditControlService` compares it against exposure — `current_outstanding - unapplied_advance + the document being saved` — at sales order and sales invoice approval, the two points where credit is committed. Policy is per firm in `credit_control_settings` (`OFF` / `WARN` / `BLOCK`, with warn and block percentages); a firm with no row warns at 80% and never blocks, and a `credit_limit` of zero means unset rather than no credit, so shipping this stopped nobody trading. `GET /api/v1/customers/{id}/credit-status?amount=` answers the question before a document is saved rather than reporting the breach after, and `GET`/`PUT /api/v1/customers/credit-settings` carries the policy. Writing the policy needs `CUSTOMER_MANAGE_SETTINGS`, deliberately **not** granted to `SALES_MANAGER`: the role the limit constrains must not be able to switch it off. The desktop **warns and never blocks**: `warnOnCreditExposure` (`desktop/lib/ui/sales/credit_notice.dart`) runs on Approve for sales orders and sales invoices, before the action so the document is not counted twice, and stays silent when `would_block` is true because the server's refusal already carries the same sentence. A client that blocked on its own would enforce a rule the firm may not have chosen and could be bypassed by any other client. The policy itself is edited from the Settings action on the customers workspace (`credit_settings_dialog.dart`), which is readable with `CUSTOMER_VIEW` — someone the policy warns should see the rule behind the warning — and writable only with `CUSTOMER_MANAGE_SETTINGS`.
- **A firm's storage routing is fixed at creation.** Nothing migrates a firm's rows between stores, so `FirmService.update` rejects any change to `deployment_mode`/`schema_name`/`database_name`/`connection_profile`, and omitted tenancy fields inherit the stored mapping instead of defaulting to `SHARED`. Two firms are never allowed to share one database/schema pair — soft-deleted firms included, because their data is still there. An unknown `connection_profile` is refused at create rather than at first use: a typo would otherwise produce a firm that provisions and serves nothing, failing far from the request that caused it.
- `refresh_tokens`, `login_history` and `password_history` have no automatic cleanup of their own, and neither does `tax_rule_execution_logs`. **`scripts/purge_retention.py` is the one to run**: it enumerates every firm store from the registry — dedicated schemas and dedicated databases included — and applies both retention services, so it cannot miss a store the way running the two single-purpose scripts by hand does. `--dry-run` reports, `--yes` applies. The `retention` service in `docker-compose.yml` runs it on a loop, and is **opt-in**: `docker compose --profile retention up -d`, because bringing the stack up should not start deleting rows on its own. Until someone enables it nothing prunes these tables, which is how they grew unbounded to begin with. `AGENCY_RETENTION_INTERVAL_SECONDS` sets the period (default daily) and `AGENCY_RETENTION_MODE=--dry-run` makes it report instead of delete. `scripts/purge_identity_history.py` and `scripts/purge_tax_execution_logs.py` remain for pruning one store on its own. `tax_rule_execution_logs` is the same shape and grows fastest — one row holding three JSON documents per document line — and is pruned per firm store by `scripts/purge_retention.py` (every store at once) or `scripts/purge_tax_execution_logs.py` (one store, selected with `AGENCY_DATABASE_SCHEMA` the way a migration does).
- **`TaxRuleService.simulate` is the tax calculation, not a preview.** All seven transactional modules call it once per line while building a document, on their own session, so it must never commit — the `/simulate` endpoint owns that. It also derives `country_id` from the applied profile's tax system and `business_profile_id` from the firm's assignment, because no document sends either and rules scoped that way otherwise never match. `total_tax_amount` is only what the counterparty is billed: tax `included_in_price` and tax under `REVERSE_CHARGE` are reported in `inclusive_tax_amount` / `reverse_charge_tax_amount` and must not be added to a document total.
