# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository shape

Two independent applications, no shared build:

- `backend/` — FastAPI + SQLAlchemy 2.0 + Alembic, Python 3.13, managed with `uv`. Owns all business logic and the database.
- `desktop/` — Flutter Material 3 desktop client (Windows/Linux/macOS). Talks to the backend **only** over REST; it never touches the database.
- `docs/`, `backend/**/README.md`, `desktop/docs/` — the tracked, canonical documentation.

## Where the detail lives

This file is the **rules**. Every rule below was written from a defect that
actually happened, and the story beside it -- which defect, on what date, found
how -- is the half that says why the rule is the rule. Those stories moved into
`docs/` on 2026-09-15, when this file passed the 150k-character limit that keeps
it loadable in one context window. Nothing was cut; each group names its doc.

| Subject | Reference |
| --- | --- |
| Every table: where it lives, what it holds | `docs/TABLE_CATALOGUE.md` |
| Tenancy, stores, provisioning | `docs/TENANCY_AND_STORES.md` |
| Roles, permissions, memberships, hiring | `docs/ACCESS_CONTROL_FRAMEWORK.md` |
| Routers, schemas, pagination, concurrency, migrations | `docs/API_AND_PERSISTENCE_CONVENTIONS.md` |
| Discounts, price lists, promotions, loyalty, freight | `docs/PRICING_AND_PROMOTIONS.md` |
| What posts to the ledger, and at what value | `docs/LEDGER_POSTING_RULES.md` |
| The sales chain and what may be skipped | `docs/SALES_CHAIN_RULES.md` |
| Commission rules, ladders and payouts | `docs/COMMISSION_FRAMEWORK.md` |
| Demo and sample data | `docs/DEMO_DATA.md` |
| Custom fields / the attribute framework | `docs/CUSTOM_FIELDS_FRAMEWORK.md` |
| Geography masters | `docs/GEOGRAPHY_MASTERS.md` |
| Desktop shell, catalog, preferences | `desktop/docs/DESKTOP_FRAMEWORK.md` |
| Compiling, packaging and shipping a release | `docs/RELEASE_BUILD.md` |

Business profiles, purchasing, tax, UOM, territory and batch/serial each keep
the reference doc they already had; the narrative that was here was appended to
it.

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

As of 2026-09-13 `pytest` is **green (1,365 unit + 48 integration)** and every test file also passes standalone — `tests/conftest.py` imports all model modules so `Base.metadata.create_all` sees the whole schema regardless of test order. Keep that list in step with `alembic/env.py`.

`tests/integration/` needs a real PostgreSQL server and **skips cleanly without one**. It covers what SQLite cannot express: platform tables being invisible to a firm schema, firm-scope resolution across deployment modes, two schemas holding independent rows, and ORM-vs-deployed-schema drift. Run it with `uv run pytest tests/integration -q`. Reach for it whenever a change touches tenancy, cross-schema foreign keys, triggers or concurrency — every defect in that class has been invisible to the unit suite.

**`app/` and `tests/` are clean under all four tools, and expected to stay that way.** `ruff check app`, `ruff check tests`, `black --check` and `mypy app` (452 files) all pass, so any finding in them is one you introduced. That was not true for most of this project's life -- this file claimed ~3,232 pre-existing findings and `mypy` failures outside `app/finance`, both of which stopped being true without the claim being updated, which is how a stale number talks people out of running the tools at all.

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

**The script is a wrapper; the work is `upgrade_every_store` in
`app/core/tenancy/migrations.py`,** which firm provisioning and the shipped
binary both call. `scripts/` does not reach a customer — a released build is
compiled and has no interpreter to hand a `.py` to — so **anything an installed
copy has to do belongs in `app/` and is exposed as a subcommand of
`app/cli.py`** (`serve`, `create-database`, `migrate-all`, `purge-retention`,
`where`, `--version`). `tests/unit/test_cli_entry_point.py` fails the build when
a shipped `.ps1` reaches for `-m alembic`, `-m uvicorn` or a script by path
again; `docs/RELEASE_BUILD.md` is the reference.

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

`./start.sh` (Git Bash) wraps clean/get/run with `--no-clean`, `--linux`, `--macos`, `--release` flags. `desktop/build_android.ps1` is the separate mobile build: each run generates an Android APK into `desktop/dist/android/` named with the version, date and build type (ignored by git), starting at this PC's network address or `-ServerUrl` (changeable on the phone under Application Settings), and `-Install` pushes it over USB. It needs the Android SDK; the phone needs a backend started with `-BindHost 0.0.0.0` and port 8000 open. It exists to look at screens on a phone -- the layouts are still desktop layouts, so results there do not replace the desktop test plan. `AppStorage` (`desktop/lib/core/platform/app_storage.dart`) is the one place the app's file root is decided, because an Android process has no `APPDATA` or `HOME`. Native runner directories are generated, not authoritative — regenerate with `flutter create --platforms=windows,linux,macos .` if missing. Windows secure-storage builds need Developer Mode enabled for plugin symlinks.

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

Business services stay storage-agnostic: they receive a `Session` and never know the deployment mode. Default local layout is two schemas in one database — `platform` (identity, RBAC, firm registry) and `firm_shared` (firm-owned modules).

**`docs/TENANCY_AND_STORES.md` is the reference.** Four rules carry most of the weight:

- **A firm can live on a different server.** `firm_storage_mappings.connection_profile` names an entry in `AGENCY_TENANCY_CONNECTION_PROFILES`; `NULL` means the platform server. The request path (`FirmConnectionResolver`) and the provisioning path (`TenantStorageLifecycleService`) must both build through `app/core/tenancy/connections.py` — if they disagree, provisioning builds tables on one host while every request looks on another, and nothing reports the difference. **Both capture the profile map at `create_app`, so a profile added to `config/.env` is invisible until the backend restarts** — add it, restart, then create the firm, or the create is refused by name for a profile that is plainly in the file.
- **Dedicated storage is built by an explicit action, not at creation.** `POST /api/v1/firms/{id}/provision` creates the database and schema, migrates it and prunes the platform tables; `FirmService.create` only records the intent. Every step is create-if-missing, so the same endpoint is the repair action. Alembic runs **in this process**, through `upgrade_store` in `app/core/tenancy/migrations.py`, with the target passed on `Config.attributes` and a lock held for the run. It must never go back to `os.environ`: that is process-wide, and it is what made two concurrent provisions race before a subprocess was used to escape it. The subprocess had to go because `sys.executable -m alembic` cannot work in a compiled build.
- **A firm is finished from the Firms grid, not from scripts.** `GET /api/v1/firms/{id}/readiness` answers seven steps from **one implementation** in `app/firms/services/readiness.py` that `scripts/check_firm_readiness.py` also prints, so the screen and the shell cannot disagree. Open books, the GST template, control accounts and the default branch each have an endpoint and a row on the **Set up** panel (`firm_setup_dialog.dart`).
- **Storage routing is fixed at creation.** Nothing migrates a firm's rows between stores, so `FirmService.update` rejects any change to it, and two firms never share a database/schema pair — soft-deleted firms included.

### Authorization

`Principal` + `require_permission("CODE")` from `app.core.security.authorization`. Firm-owned routers compose a scope dependency that (a) checks the permission code and (b) validates active `UserFirm` membership for `X-Firm-ID` — platform admins are **not** exempt from supplying a firm context on firm-owned resources. See the `_permission()` / `CustomerViewScope` pattern in `app/customers/api/router.py` and copy it. Permission codes are `DOMAIN_ACTION` (`CUSTOMER_VIEW`, `TAX_RULE_UPDATE`) and are seeded in `app/identity/system_seed.py`; system roles/permissions are immutable via the API.

**`docs/ACCESS_CONTROL_FRAMEWORK.md` is the reference** — the two tiers of administrator, the sixteen seeded roles and why each withholding is what it is, how a role becomes a permission on a request, memberships and the firm switcher, hiring by template and by clone, and an appendix recording the defect behind each rule. The ones that bite:

- **Any code you pass to `require_permission` must also exist in `PERMISSION_GROUPS`** in `app/identity/system_seed.py`. An unseeded code has no permission row, so it can be attached to no role and the endpoint silently becomes platform-admin-only. Adding codes also needs a migration to insert them into existing databases (see `20260809_0044`). `tests/unit/test_identity_hardening.py::test_every_enforced_permission_code_is_seeded` fails the build if it recurs.
- **`require_platform_admin()` on a route makes every permission code on it grant nothing**, because the designation comes from a `platform_admins` row and no role can reach it. `tests/unit/test_platform_only_routes.py` pins the routes that are deliberately platform-only, with the reason per group, and fails both on a new one added by accident and on a pinned one that quietly stops being platform-only — which is the half that rots. **Count them there rather than trusting a number written here.**
- **A permission's blast radius is the set of endpoints enforcing it, not the group it is filed under.** `grep -rn CODE app/ --include=*.py` answers that in a second and is worth doing before adding any code to a role. `PLATFORM_PERMISSION_CODES` answers "what may a firm administrator not *grant*", which is a different question from what they may hold.
- **The platform designation is its own claim, and a role code must never be able to spell it.** `create_role` refuses the reserved codes case-insensitively, and a role row written by any other route still confers nothing.
- **A `PLATFORM` admin is narrowed in three places or in none** — the membership exemption in `app/common/scope.py`, the short-circuit in `Principal.has_permission`, and the stuffed `permissions` claim, which `has_permission` reads directly. Any two without the third is not a narrowing at all. A designation is a **ceiling, not a floor**: where they hold a real `UserFirm` row they act there as their roles make them.
- **A designation that exempts somebody from a check but leaves them unable to name a firm is not reach at all.** `GET /api/v1/me/firms` returns every active firm for `ALL_FIRMS`, and deliberately not for `PLATFORM`, who are refused firm-owned routes and would get a switcher full of 403s.
- **Moving a claim is not done until nothing reads the old place, and a grep for the *new* name will not tell you.** A fixture that supplies the old shape cannot see the break, so a suite going green after a claim moves proves less than it appears to.
- **A role can hold exactly the right codes and be offered no screen at all.** A tab naming no codes inherits its module's list. `tests/unit/test_every_role_can_open_something.py` asks it of every seeded firm role, and asks the same question one level down for tabs.
- **`_operational_permissions` is a hand-kept list** that groups drift out of. `tests/unit/test_firm_admin_holds_the_firms_own_modules.py` asks the derived question rather than pinning the names, so it catches the next one.
- **A firm's audit trail is its own store *plus* the platform rows that belong to it.** `AuditLogReader.list_events_with` merges on the **read** — exactly rather than per store, with the same filters on both, and never merging a store with itself, which the one-schema unit suite would otherwise do. Only `tests/integration/test_audit_trail_spans_two_stores.py` can see it.

### Entities and responses

All business entities extend `BaseEntity` (`app/core/database/entity.py`): UUID id, created/updated actor + timestamp, `version` for optimistic concurrency, `is_deleted`/`deleted_at` soft delete. Repositories exclude soft-deleted rows unless explicitly asked. Audit logs are the exception — append-only, enforced by the `TR_audit_logs_append_only` trigger; every mutation must emit one via `app.common.audit`. **Every schema owns its own copy of that trigger and of the `reject_audit_log_mutation()` function it calls** (`20260809_0043`), so anything that shapes a firm store must leave both alone: `prune_platform_objects` used to drop the function `CASCADE`, which took the firm's trigger with it and left every dedicated store with a rewritable trail. `tests/integration/test_audit_append_only.py` is the guard, and it only bites now that CI prunes `firm_shared` the way provisioning does.

**The audit trail is per store, not central.** Platform administration writes to `platform.audit_logs`; every firm-owned mutation writes to that firm's own store, because `record_audit` runs on whichever session `get_db` resolved. That is deliberate — a DATABASE-mode firm's history has to live inside its own database for the isolation and per-firm restore guarantees to hold. The consequence: **no single query can answer "everything that happened"**; a cross-firm view must iterate firm stores. `GET /api/v1/audit-logs` reads one trail, chosen by firm context — no `X-Firm-ID` plus platform authority gives the platform trail, `X-Firm-ID` gives that firm's. Date filters are inclusive UTC calendar days, matching the `created_from`/`created_to` convention in the customer and product list filters.

Responses always use `ApiResponse` / `PaginatedResponse` from `app/core/responses/models.py` (`success`, `data`, `message`, `timestamp`, `requestId`, plus `pagination.{page,page_size,total_records,total_pages}`). List endpoints accept only the whitelisted `page`, `page_size`, `search`, `sort_by`, `sort_direction`.

### Cross-cutting frameworks

Prefer extending these over adding module-specific machinery. Each has a reference doc; what is here is the rule that gets broken.

- **Business Profile Framework** (`app/business`) — `docs/BUSINESS_PROFILE_FRAMEWORK.md` is the reference: table map, resolution flow, what is actually enforced versus merely recorded, and how to extend it. Industry profiles decide which features and modules a firm operates. Never hardcode industry behaviour into entities; declare a feature and gate on it. `require_feature("CODE")` / `require_module("CODE")` from `app/business/gating.py` gate a whole **endpoint** and are **write-only** (safe methods always pass), which only suits a feature owning its own resource; most features are optional *fields* on a resource every firm uses, so call `assert_feature_fields(session, firm_id, feature=..., values={...})` from the service instead — it refuses the write only when it populates one of the named fields, and a firm with no resolvable profile is never gated, because a configuration gap is not a decision. `is_implemented` is a fact about the codebase and **has to be revisited when the codebase changes**; `COMMISSION` outlived its flag and an administrator was refused a feature the platform had. The desktop's `/active-modules` filtering is cosmetic and is **not** a security boundary.
- **Configurable custom fields** — `docs/CUSTOM_FIELDS_FRAMEWORK.md`. A module gains industry-specific fields through `AttributeService` (`app/business/services/attribute_service.py`), never by adding columns. Values live in typed `value_text` / `value_number` / `value_date` / `value_boolean` columns so list filters and reports can index them — **never as JSON**. Read a list's attributes with `values_for_many`, never per row. Copy the customer/vendor shape when extending a new module; a form sends `attributes` only once the definitions arrived, because absent means "leave them alone" and an empty list means "clear them".
- **Document Lifecycle Framework** (`app/document_framework`) — configurable document types, states, numbering rules, and timeline events for transactional modules. Lifecycle states are configuration, not enums.
- **Purchasing end to end** (`app/purchase`, `app/goods_receipt`, `app/purchase_invoice`, `app/purchase_return`, `app/settlements`) — `docs/PURCHASE_FRAMEWORK.md`, and `docs/PURCHASE_TO_PAYMENT_FLOW.md` traces order to payment with the ledger lines each step raises. Only four transitions reach outside their own module, and **each reversal takes the journal off with the stock**. Receiving moves the order, approval cannot be skipped, and an edit never decides the status.
- **Tax framework / rule engine** (`app/tax`) — `docs/TAX_FRAMEWORK.md`. ACTIVE rules ordered by `priority ASC, code ASC, version_number DESC`, **first match wins and evaluation stops**. Rules attach to the transaction, never to a product; the product contributes `tax_profile_group_code`, `product_category_id` and `product_type` to the matching context.
- **UOM & packaging** (`app/uom`) — `docs/UOM_FRAMEWORK.md`. The product's own rule outranks the firm-wide one, ranked explicitly rather than by NULL sort. Eight document modules call `convert_quantity` per line, plus `inventory`; `quotation` deliberately does not.
- **Geography** — `docs/GEOGRAPHY_MASTERS.md`. One set of masters named by all four address-carrying modules, and `GeoAreaPicker` (`desktop/lib/ui/workspace/geo_area_picker.dart`) is the one control that fills them rather than a fifth copy of the cascade.
- **Territory, routes & beats** (`app/sales`) — `docs/TERRITORY_FRAMEWORK.md`. A route's effective window is enforced, judged on the document's own date, and `PUT /{id}/customers` replaces the whole list with `visit_sequence` as position in it.
- **batch/serial/expiry** (`app/batch_serial`) — `docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md`.
- **Pricing, promotions and loyalty** — `docs/PRICING_AND_PROMOTIONS.md`. One resolver, `app/core/utils/pricing.py`, which every sales and purchase document calls.
- **Ledger posting** (`app/finance`, live at `/api/v1/finance`, migration `20260809_0042`) — `docs/LEDGER_POSTING_RULES.md`. Eleven modules post through `DocumentPostingService`, and `firm_control_accounts` carries 24 purposes per firm. It uses the seeded `accounting` / `financial_year` permission codes rather than a `FINANCE_*` namespace.

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

**`desktop/docs/DESKTOP_FRAMEWORK.md` is the reference**, with `DESIGN_SYSTEM.md`, `UX_GUIDELINES.md` and `COMPONENT_LIBRARY.md` beside it; its appendix carries the story behind each rule here.

- **A tab's body goes in the workspace of the module that declares it.** Each multi-tab workspace renders by `switch (tabId)` and falls back to a placeholder for an id it does not name, so a tab declared in one module and dispatched in another opens the placeholder while its own widget test passes. `desktop/test/workspace_tab_bodies_test.dart` fails the build on the next one.
- **A field the desktop sends must be one the server declares**, and a suite on either side cannot see when it is not: `ApiSchema` forbids unknown fields, so one stray key fails the whole request, and the desktop's fake accepts anything while the backend's tests build their own payloads. `tests/unit/test_desktop_preference_payloads_are_accepted.py` reads the keys the client sends and asks the two schemas.
- **There is one tab filter, `ModuleVisibility.tabsFor`.** There were eight byte-identical copies; they drifted the moment `requiresFirm` was added, so the sidebar hid tabs each workspace's own strip went on offering. `module_visibility_test.dart` greps the shell for a ninth.
- **A dialog owns its own `TextEditingController`**, and an `AlertDialog` gives its content unbounded height. Use `askForReason` (`desktop/lib/ui/workspace/reason_prompt.dart`) rather than a third copy; it returns null for a dismissal *and* an empty box, so a caller has one answer to check.
- **A toolbar action that is not about the selected row must say so.** `ResourceAction.needsSelection` defaults to true because almost every one is; an action whose subject is not in the grid reads as a broken button without it. A guard for this needs a real `BuildContext` from a `testWidgets`, or it loops over an empty list and passes with the fix reverted.
- **Where a screen lives is a decision about who can reach it.** `requiresFirm` and `requiresPlatformAdmin` exist on `ModuleDefinition` *and* on `ModuleTabDefinition`, and a flag is the right instrument rather than a permission code — a platform administrator passes permission checks by designation rather than by holding codes. A tab may also name a `group`, which renders grouped tabs as one sidebar entry with a strip inside while each tab keeps its own id as its address.
- **Preferences are three separate stores and sign-in only replaces one.** Server preferences are replaced wholesale by `_applyServerPreferences`, so workspace state lives in `DesktopPreferences.workspaceState`; the last screen is per user via `default_landing_page`, because the local file is per Windows account rather than per user. `desktop/test/workspace_state_persistence_test.dart` pins both.

## Keeping this file true

**Every claim here was re-derived on 2026-09-05, and six were wrong.** The
test counts (817 against 1,127), the `mypy` file count (370 against 452),
the integration count (33 against 37), the desktop count (931 against
1,074), `TAX_RULE_SIMULATE` offered as an example permission code that has
never existed, and "11 of 21" business features when there are 22. A
seventh -- automatic GL posting described as unbuilt while eleven modules
were posting -- was corrected the same week.

None of them was ever wrong when written. Each stopped being true and
nobody re-derived it, which is exactly the failure this file warns about
in its own words: *a stale number talks people out of running the tools at
all*.

A second pass over the 142 behavioural claims on the same day found two more: this file named **six** routers publishing an `ETag` when 24 do, and stated the foreign-key convention as though it had no exceptions when 15 keys deviate harmlessly. Both are the same failure as the counts -- an enumeration that was exhaustive when written and quietly stopped being so. **Prefer a command that counts to a list that rots.**

Twenty of the twenty-two structural claims checked mechanically held, and the two that appeared not to were the checker's fault rather than the file's: three `date.today()` hits were in comments warning against it (the real guard uses an AST, not a grep), and the foreign-key exceptions turned out not to collide.

`tests/unit/test_claude_md_names_real_things.py` now fails the build when
this file names a path, a migration or an identifier that does not exist.
It deliberately does **not** guard the counts: a test that fails every
time somebody adds a test file becomes a test somebody deletes. Counts
carry the date they were taken, and the honest way to treat one is to
re-run the command beside it rather than trust the number.

**This file was 184,455 characters on 2026-09-15, and a file nobody can
load is as useless as one nobody believes.** Claude Code's limit is
150,000; past it the whole file competes with the work for one context
window, and the first thing to go is the reader's willingness to consult
it at all -- the same failure as a stale number, arrived at from the other
direction. The narrative half of each rule moved to the docs named in
**Where the detail lives** and the imperative half stayed here, which is
the shape the rest of this repository already uses: `docs/` holds the
reference, this file holds what you must not do. Nothing was deleted, and
the split was checked rather than assumed -- every sentence of the old
file was matched against the new tree before the old one was overwritten.
**The guard travelled with the prose**: the test above reads the moved
docs as well as this file, so a path that rots in one of them still fails
the build. Keep the ratio -- a rule that grows a second paragraph of
history here belongs in its doc.

## Module reviews

`docs/MODULE_REVIEW_CHECKLIST.md` holds the per-module review checklist, a debt
inventory (endpoints, ruff/mypy counts, test and desktop coverage per module), the
review order, and a progress table. The checklist items are derived from defects
that actually occurred, not generic advice. Update the progress table as modules
are completed.

`docs/MODULE_STATUS.md` is the shorter companion: every module grouped by what
it is for, with route and report counts, whether it is built, and what is still
open -- and the open work sorted by what is actually blocking it rather than by
module. **Its counts are compiled from the running application, so re-derive
them rather than trusting them after a few months.** The category worth reading
first is "built, but nothing exercises it": 42 of 182 tables hold no live row
in any store, and asking that question found four defects in one day on
2026-09-04.

## Testing

**Never run `pytest tests/unit` or `flutter test` without arguments on your
own initiative. Ask, every time, and wait for an answer** -- including before
a merge, which is not an exemption. If a full run looks warranted, say why in
one line and let the owner decide.

This is a prohibition on the command rather than a preference about scope, and
it is phrased that way deliberately: it was a preference first, and a
preference is something to rationalise around -- "this change is broad", "it
has been a while", "better to be sure" -- which is how one session came to
spend most of its wall-clock time watching suites nobody had asked for. Six
minutes for the backend and two for the desktop, per run, mostly re-proving
what a targeted run had already shown.

**And leave a gap.** Do not start a full sweep while one is running, and do
not start another straight after one has passed unless the code has changed
since -- consecutive sweeps over the same tree prove nothing twice. Targeted
runs need no permission and should be constant; say which files you ran.

**Run what the change can break, not everything.** The full backend suite is
1,365 unit tests and the desktop suite is 1,408 (2026-09-13). On an **idle** machine they
take **7:19** and **2:26** (measured 2026-09-06); with the dev server and the
built desktop client running, the same backend suite took **23 minutes** the
same day and had to be run in quarters to fit inside a ten-minute tool
timeout, while the desktop suite took four. That is a **three-fold** spread on
one machine on one day, so budget for the machine you are on, not for the
number. Running both after a one-line fix is most of the cost of the fix.
While iterating, run the module's own test file plus any guard that reads the
thing you touched -- a router edit wants that module's tests and
`test_identity_hardening.py`; a change to `module_catalog.dart` wants
`test_search_navigation_targets.py`, `business_module_gating_test.dart` and
`configuration_screens_test.dart`, all three of which parse it; a widget edit
wants `flutter analyze` on the changed files and that screen's test. Seconds,
not minutes.

**The full suites and tree-wide `ruff` / `black` / `mypy` run on two
occasions, not per edit: once a day, and before a commit is merged.** Per-file
linting is instant and is what to use in between. A documentation-only change
needs neither suite.

The daily run is the safety net for the days when several small changes each
looked safely targeted; the merge run is the gate. To know whether today's has
happened, ask git rather than memory -- `git log -1 --format=%cd --date=short`
on the last merge to `main` is the day the suites last had to pass. If that
date is not today and you are about to start a batch of work, run them first,
so a failure belongs to yesterday's change rather than to yours.

**Say which one you ran.** "Identity tests and the document-framework tests
pass" is honest; "tests pass" after running two files implies coverage that was
not taken. The full desktop suite has earned its place at merge time -- it
caught a toolbar overflow that only appears at the 800x600 test window, in no
file a reasonable person would have called impacted -- so a targeted run is a
speed choice while iterating, never a claim that the narrow set was sufficient.

Backend tests are unit tests under `backend/tests/unit/`, one file per module. They build a **SQLite in-memory** engine with `Base.metadata.create_all` and a `StaticPool`, then call FastAPI route functions directly with hand-constructed `Principal`/scope objects — no running server or PostgreSQL required. Follow that pattern; new modules should keep their models SQLite-compatible for tests even though PostgreSQL is the deployment target. `backend/tests/integration/` is **not** empty -- it holds 48 tests and is described above; this line said it was empty long after it stopped being true.

Desktop tests are widget tests in `desktop/test/`, mostly per-module UX tests plus login and navigation-tree tests. `flutter test` is **green (1,408)** and `flutter analyze` is clean as of 2026-09-13.

## Repository conventions and traps

What follows is the imperative half of each rule. **The story beside it — which
defect, on what date, found how — lives in the doc each group names**, and it is
the half that says why the rule is the rule. Read it before arguing with one, and
add the next defect there rather than here.

### Repository

- **Most root-level `*.md` files are untracked, generated AI reports.** `.gitignore` excludes root `*_REPORT.md`, `*_ARCHITECTURE.md`, `*_SUMMARY.md`, `*_REVIEW.md`, `*_GUIDE.md`, `*_FRAMEWORK.md`, `DEVELOPMENT_*`, `PLATFORM_*`, etc. Only `README.md` and `SECURITY_ARCHITECTURE.md` are tracked at root. Treat the rest as scratch context, not as a spec, and put durable documentation in `docs/`, `backend/**/README.md`, or `desktop/docs/`.
- Migration docs cite stale heads (`alembic/README.md` says `20260802_0021`; the versions directory is well past that). Always confirm with `uv run python -m alembic heads`.
- Config is `pydantic-settings` reading `backend/config/.env` with the `AGENCY_` prefix; env vars override the file. `config/.env` is never committed. Staging/production refuse to start with the development JWT key or without an explicit bootstrap admin password.

### Tenancy — `docs/TENANCY_AND_STORES.md`

- **A firm-owned service reading a platform table opens the platform store**, with `platform_reader()` from `app/common/firm_metadata.py`. `users`, `firms` and `user_firms` exist **only** in the platform schema, so a tenant session raises `UndefinedTable` for every firm outside it. Eight occurrences so far — reading a name and checking a name are different lines in different methods, and fixing one has never fixed the other. `_PLATFORM_TABLES` in `app/core/tenancy/lifecycle.py` is the authority on which tables those are ("has no firm column" is not: `geo_countries` has none and lives in every store). Only `tests/integration/` can see the defect, because the unit suite builds one SQLite schema holding every table.
- **A platform endpoint touching firm-owned data must open that firm's store**, with `firm_store_session(request, firm_id)` from `app/core/database/dependencies.py`. `get_db` routes on the caller's `X-Firm-ID`, which is right for a firm-scoped request and silently wrong for a platform screen administering another firm — the business-profile assignment endpoints wrote into the caller's store and returned success. A list across firms iterates the stores and **reports a store it could not read rather than blanking the row**.
- **Never write a private firm-scope resolver** — compose `app/common/scope.py`, which resolves through `get_platform_db`.
- **Any new platform fact a firm-owned service needs goes on `FirmMetadataReader`**, never a fresh `select(Firm)`. `test_no_service_resolves_firms_on_a_tenant_session` in `tests/unit/test_global_search.py` guards it.
- **`GET /api/v1/firm-members` is the one list of a firm's people**, gated on membership and nothing else. A firm's own directory of names is not a privilege; *acting* on a person is what needs one.
- **A firm's storage routing is fixed at creation**, and two firms never share a database/schema pair — soft-deleted firms included, because their data is still there. An unknown `connection_profile` is refused at create rather than at first use.
- `users.email` is unique **only among live accounts**, so soft-deleting a user releases the address; `firms.code`, `gst_number` and `pan_number` work the same way (`UQ_firms_<column>_active`). Filter `is_deleted` in any such lookup.
- PostgreSQL 17 is the primary target; MySQL is supported by the connection layer but the `UQ_user_firms_active_primary` and `UQ_users_email_active` partial indexes are PostgreSQL-only, so the matching service-level checks stay authoritative.

### Routers, schemas and persistence — `docs/API_AND_PERSISTENCE_CONVENTIONS.md`

- **A literal path must be declared before `/{id}` in the same router.** FastAPI matches in declaration order, so ten routes across nine routers were read as an id and answered 422 from the day they were written. `tests/unit/test_route_declaration_order.py` fails the build on the next one.
- **A bare `ResolvedFirmScope` parameter is read by FastAPI as a request body field** — it is a plain dataclass, and the injectable form is `RequiredFirmScope` from `app/common/scope.py`. Nineteen handlers were uncallable this way. Grep for `scope: ResolvedFirmScope,` before adding a platform-admin endpoint.
- **Declare `page` and `page_size` bounds on the query parameter**, `Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]`, never by constructing `PaginationParams` in the handler — that turns an over-cap request into a **500** instead of a 422 naming the limit. `tests/unit/test_pagination_conventions.py` guards it; client-side use `fetchAllPages` (`desktop/lib/ui/workspace/paged_fetch.dart`).
- **An update that dumps its whole write model turns an omission into an instruction.** Dump with `exclude_unset=True` on update only, so **absent means leave alone and an explicit `null` still clears**; guard child collections on `model_fields_set`; and read anything out of the dumped values with the row as its fallback (`values.get("is_default", row.is_default)`), or a promotion becomes a demotion. Create is unchanged — there a default really is the value to store. **A lifecycle status belongs to its transition endpoints and must never be writable through the update body.** This has shipped at least a dozen times.
- **Bulk and import endpoints are a second implementation.** Review both paths for the audit writes and the delete guards the single-row twin enforces, and **stage then commit once** so a batch whose fifth row clashes cannot leave the first four written.
- **`BaseEntity.version` is the mapper's version id.** Every ORM update bumps and checks it, so a stale write raises `StaleDataError` (409); bulk `query().update()` bypasses this by design. Publish it as an `ETag` — `set_etag` from `app/core/concurrency.py`, or `publish_version` where the service builds the response model — on any endpoint returning one versioned record, **and** as a field on the body, because a list carries many records and the desktop opens its editors from list rows. Count the routers that do with `grep -rl 'set_etag\|publish_version' app/*/api/router.py` rather than trusting a list. A client echoes the `ETag` it was given rather than computing the next number; sending nothing is accepted, so the precondition stays opt-in. A save that changes nothing does not move the counter.
- **No model may declare its own `version` column** — that name is the concurrency counter, and a business version under it gets incremented by every ORM update. Call a business revision `version_number`.
- **Optimistic concurrency protects a decision about a *row*, and nothing about a decision about a *set* of rows.** A guard that reads a row and updates it is safe. A guard that reads a **sum or a count and then inserts** is not — no row is updated, so no version can conflict. Guarding a **key** takes a partial unique index; guarding a **sum** takes `with_for_update` on the thing being consumed, held per row so unrelated work does not queue. One mechanism everywhere is wrong more often than not.
- **A partial unique index cannot be `DEFERRABLE`**, and PostgreSQL checks it per statement — so a reorder that swaps values must clear the ones it is about to hand out, flush, then write them, and clear **only** the ones actually moving. Declare `sqlite_where` beside `postgresql_where`, or the index is not partial under the unit suite and is stricter than intended.
- **`ondelete="RESTRICT"` is not a guard on a soft-deleted table** — a soft delete never reaches the database's referential check, so the refusal has to live in the service, and it has to look at the level below *and* at everything outside the module.
- **A foreign key's name must be unique within its table**, which keying on the referring column (`FK_<table>_<column>`) guarantees. Keying on the referred table collides when one table has two keys to the same target, which SQLite ignores and PostgreSQL rejects — and `Base.metadata.create_all` is how the seed and tenancy-reset scripts build firm stores. `tests/unit/test_schema_registry.py` fails on two keys sharing a name; **the collision is the thing to guard, not the spelling**.
- **Never read the server's local clock.** Everything persisted here is UTC, so `date.today()` compares against a date the data does not use. Call `utc_now().date()`; `tests/unit/test_time_conventions.py` fails the build on a new occurrence, using an AST rather than a grep. `func.now()` is fine. **`as_utc()` (`app/core/utils/dates.py`) reads a stored timestamp**, because SQLite ignores the timezone and returns naive what PostgreSQL returns aware.
- **Never let NULL ordering pick a row.** PostgreSQL sorts NULLs first in `DESC` and SQLite last, so an ordering that works in the unit suite can pick the wrong row in production. Rank on `case((col.is_(None), 1), else_=0)` and cover it in `tests/integration/`.
- **A hand-written `op.create_table` must spell out `server_default=sa.text("CURRENT_TIMESTAMP")` for the timestamps**, or the column is NOT NULL with no default and the **first** write raises `NotNullViolation`. The unit suite builds its schema from the ORM, so it can never see this. `tests/integration/test_multi_schema_tenancy.py::test_every_deployed_table_can_be_inserted_into` is the guard.
- **`TaxRuleService.simulate` is the tax calculation, not a preview.** Nine modules call it once per line on their own session, so **it must never commit** — the `/simulate` endpoint owns that. It derives `country_id` and `business_profile_id` itself, because no document sends either. `total_tax_amount` is only what the counterparty is billed; inclusive and reverse-charge tax are reported separately and must not be added to a document total.
- **Nothing prunes `refresh_tokens`, `login_history`, `password_history` or `tax_rule_execution_logs` until somebody enables it.** `scripts/purge_retention.py` enumerates every firm store from the registry and applies both retention services, which is why it cannot miss a store the way the single-purpose scripts do; the `retention` compose service runs it on a loop and is **opt-in** (`docker compose --profile retention up -d`).
- **A screen that replaces a whole list must prove it read that list first** — clear the pane **before** the read rather than after it succeeds, and refuse to save until it provably holds the selected record.
- **A route nothing calls is where whole features have gone missing** — and **a call in `api_client.dart` counts as a caller, which is the hole.** `tests/unit/test_routes_have_a_caller.py` pins the routes deliberately left without one; `desktop/test/reachable_features_test.dart` pins the controls themselves, because the day a feature merges is the only day anybody remembers it is unreachable. **A report needs its own entry in `report_catalog.dart`** — the orphan-route guard matches path *shapes*, so a sibling's entry makes an unlisted report look reachable; `tests/unit/test_reports_have_a_screen.py` asks it both ways.

### The sales chain — `docs/SALES_CHAIN_RULES.md`

- **A chain of committing services is not a transaction, and `begin_nested` does not make it one.** In SQLAlchemy 2.0 `Session.commit()` commits the outermost transaction and closes the savepoint. Split into `stage_*` internals that flush and public wrappers that commit; **compose the `stage_*` methods and commit once.** Three import endpoints said "atomically" in their docstrings while looping over a committing create.
- **Document lines are reconciled on their line number**, not deleted and re-inserted — downstream documents record `source_document_line_id` as a bare UUID with no foreign key, so re-inserting silently dangles them. The three invoice modules re-insert because their lines are terminal.
- **A lifecycle status is derived by summing what happened, never incremented**, and only an order already in that part of its life is moved. An incrementing counter and a reversal are two chances to disagree.
- **A flag the caller sets to permit itself is not a control.** Which stages of a sale a firm's people type is `sales_workflow_settings`, per stage; `SalesChainService` raises what is switched off by driving the same services a person would, so the documents are real and stock still leaves at dispatch.
- **A hold is a flag, not a status.** Writing it into `status` would destroy the record of how far the order had got. The stock stays reserved — holding says "not yet", not "never" — and cancelling is what gives it back. A hold is an operational stop, not credit control.
- **A gift line is owed until an invoice line references it**, counted in rows and never in quantity: zero minus zero is zero however many times it has been stated.
- **Credit limits warn, and block only if a firm asks** (`credit_control_settings`; a firm with no row warns at 80% and never blocks, and a limit of zero means unset). The desktop **warns and never blocks** — a client that blocked would enforce a rule the firm may not have chosen and could be bypassed by any other client. Writing the policy needs `CUSTOMER_MANAGE_SETTINGS`, deliberately **not** granted to `SALES_MANAGER`: the role the limit constrains must not switch it off.

### Pricing, promotions and loyalty — `docs/PRICING_AND_PROMOTIONS.md`

- **A line discount is resolved in one place**, `app/core/utils/pricing.py`, and every sales and purchase document calls it: an explicit amount beats an explicit percentage, beats a promotion, beats the price list, beats the customer's standing rate, beats their group's. **`None` and `0` are different answers** — silence takes the standing rate, zero refuses it — so the discount and `unit_price` fields on the line-write schemas are `Decimal | None` **with no default**; giving them `Decimal("0")` makes an omission indistinguishable from a refusal. **The recorded rate is derived from the branch actually taken**, never echoed from the request.
- **No line editor may prefill a discount box**, or an inherited arrangement becomes an override — and a literal `0` refuses every arrangement. Say what blank takes in helper text instead.
- **A downstream document inherits the price, the discount and the free goods of the line it continues** — a rate as itself, an amount pro-rated by the share billed or shipped. Re-reading the master one document later is how an agreement gets quietly rewritten.
- **A document-level discount or freight charge must reach the line, and therefore the tax.** `resolve_bill_discount` and `apportion` split it across the lines in proportion to what each is worth *after* its own discount, store it on the line, and put the rounding residual on the largest line so the shares sum exactly. A header figure that never touches a taxable value taxes nothing — `header_discount_amount` on a purchase order does that and is deliberately not copied to sales.
- **A promotion's identity is its `version_group_id`; the row is only the version that is current.** Anything identifying an offer by row id breaks the moment somebody edits it, and editing is the routine act. **Promotions stack and tax does not**, so a stacking engine must collapse to one live version per group — copying the tax engine's query verbatim hands the customer the same offer twice.
- **A claim on an offer is counted at approval under a lock, never while a document is priced** — pricing must not commit, so a counter written there would publish a half-written order or count a draft. An exhausted offer is not quoted at all; two documents that race at approval have the loser refused by name rather than silently repriced.
- **Loyalty redemption settles a bill rather than discounting it**, so the supply is worth what it is worth and the full tax stands. Points cost the firm when **earned**, not when spent; the balance is a sum over the ledger and never a column; and points expire out of what is **left** of a batch, with their cost reversed.
- **What may be billed is what was charged, not what left the warehouse.** A quantity that has had free goods added to it, or been converted into another unit, is not a billing cap.

### Ledger and tax filing — `docs/LEDGER_POSTING_RULES.md`

- **A ledger leg facing stock is valued from the movement; a leg facing a counterparty is valued from the document.** Goods arrive at one average and leave at another, so mirroring an entry across that gap puts a store out — all three reversals did it. `reverse_entry` copies the source module and id onto the mirror it posts, so a lookup must match `reversal_of_id IS NULL` or it reverses the reversal.
- **Record money through `/api/v1/receipts` and `/api/v1/payments`.** `CustomerService.post_receivable_transaction` moves a customer balance **without** writing a journal, so the two books drift by every rupee recorded through it. What an invoice still owes is derived from `settlement_allocations`, never stored on the invoice.
- **A settlement is reversed, never edited or deleted**, and the balances go back by the **deltas stored on the original row** — a receipt of 500 against an outstanding 300 splits into balance and advance, and only that row remembers the split. Applying an advance posts **no journal** and moves only the part that became one.
- **Rounding the sum is not rounding the parts.** A receivable capped at two decimals takes `quantize_ledger(taxable) + quantize_ledger(tax)` — what the journal actually credited — or the two books sit a paisa apart. This shipped three times in three modules; `quantize_ledger` (`app/core/utils/money.py`) is the shared one.
- **A statement's running balance is recomputed in date order**, never read off `outstanding_after`, which is a snapshot in the order things were *recorded*. An ageing row must reconcile against the account and say how.
- **Tax collected at source is charged on the money, not on the bill** — the event is a **receipt**, only the excess over the threshold counts, the running total is summed from the receipts rather than held in a counter, and the financial year is the firm's own.
- **A return is a view of the documents.** GSTR-1 and the outward half of 3B are derived on every read and store nothing, 3B is aggregated from the documents rather than parsed out of GSTR-1's JSON, and **a supply is placed by the tax it was charged** — the document settles the place of supply, and for an unregistered buyer nothing else can.
- **A sandbox registration must never read as a filing.** `mode` is NOT NULL with **no server default**, the sandbox marks every reference it mints, and `portal_for("LIVE")` raises rather than falling back.
- **A proforma posts nothing**, and having nowhere to record that it did is the design — neither table carries a `journal_entry_id` or a `receivable_transaction_id`, and its number comes from its own series, never the tax invoice's.
- **When a taxable base moves, grep the fields.** `_charged_taxable` was correct when written and wrong once freight moved inside the base — nothing about it changed, another module's arithmetic changed underneath it.

### Commission — `docs/COMMISSION_FRAMEWORK.md`

- **A payout is snapshotted at accrual and never re-read**, or the journal posted at approval disagrees with the record beside it. One live payout per person per overlapping period, held by `UQ_commission_payouts_period_active` rather than by a read; the service check stays for the message and for *overlap*, which no key can express.
- **A rule with slabs ignores its flat `percentage`** entirely, so never show the two together. The governing rule is resolved per row on its own date and each rule's subtotal laddered separately.
- **`COMMISSION_PAY` is separate from `COMMISSION_MANAGE`** and not granted to `SALES_MANAGER`: whoever states a debt must not be the one who moves the cash.
- **A journal reference is unique**, so the accrual, the payment and the reversal need distinct ones, or an approved payout can never be paid.
- **NULL cost is not zero cost** — a margin line with no dispatch behind it contributes nothing rather than paying commission on the whole sale price.

### Demo and sample data — `docs/DEMO_DATA.md`

- **A master field added later never reaches a store already seeded.** The seeders skip masters that exist, so every new field one needs must be backfilled beside it, **only where missing and never overwriting**. Four instances so far; one of them billed no tax for two years.
- **A new table that RESTRICTs a table in `RESET_ORDER` must join that list**, or the whole reseed fails partway. `ondelete="CASCADE"` needs no entry, which is the distinction that keeps the check precise. `_assert_nothing_holds_the_history_down` asks the metadata the inverse question.
- **Build the history, not just the masters.** Both seeders drive the real services, which makes them a blunt integration test — most of the defects recorded here were found that way and were invisible to the unit suite for months, because nothing seeded exercised them.
- **Ask which columns no live row populates** whenever a feature lands. That sweep found four defects in one day, and a blanket promotion that had silently switched off every pricing tier beneath it.
- **Print what was skipped.** A seeder that reports only its tally hides a firm seeding differently from its siblings from everybody who uses the entry point.
