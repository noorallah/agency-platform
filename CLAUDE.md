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

As of 2026-08-10 `pytest` is **green (233 unit + 24 integration)** and every test file also passes standalone — `tests/conftest.py` imports all model modules so `Base.metadata.create_all` sees the whole schema regardless of test order. Keep that list in step with `alembic/env.py`.

`tests/integration/` needs a real PostgreSQL server and **skips cleanly without one**. It covers what SQLite cannot express: platform tables being invisible to a firm schema, firm-scope resolution across deployment modes, two schemas holding independent rows, and ORM-vs-deployed-schema drift. Run it with `uv run pytest tests/integration -q`. Reach for it whenever a change touches tenancy, cross-schema foreign keys, triggers or concurrency — every defect in that class has been invisible to the unit suite.

`ruff check .` still reports ~3,232 pre-existing findings across older modules (mostly `E501` and missing docstrings), so it is **not** a usable pass/fail gate repo-wide. Lint the files you touched instead, e.g. `uv run ruff check app/<module> tests/unit/test_<module>.py`. `mypy app` likewise has pre-existing failures outside `app/finance`. New and rewritten code is expected to be clean under all four tools.

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
uv run python scripts/generate_sample_data.py --yes
uv run python scripts/verify_sample_data.py
uv run python scripts/reset_tenancy_layout.py --yes   # destructive local rebuild of platform + firm_shared
```

`alembic upgrade head --sql` intentionally fails at `20260728_0004`, which inspects a live schema. Use `upgrade 20260728_0003 --sql` for offline bootstrap DDL.

### Migrations are per-schema — this is the biggest operational trap

`alembic/env.py` migrates exactly **one** schema per run, chosen by `AGENCY_DATABASE_SCHEMA` (default `platform`). Firm-owned modules live in `firm_shared` and in each dedicated firm schema/database, so a bare `alembic upgrade head` advances only the platform schema and silently leaves firm data schemas behind. That drift is invisible until a query hits a missing column — it had already broken every product read in all three firm schemas before it was noticed on 2026-08-09.

Upgrade every target, not just the default:

```powershell
uv run python -m alembic upgrade head                                   # platform
$env:AGENCY_DATABASE_SCHEMA="firm_shared";   uv run python -m alembic upgrade head
$env:AGENCY_DATABASE_SCHEMA="wholesale_hub"; uv run python -m alembic upgrade head
$env:AGENCY_DATABASE_NAME="agency_electrolink"; $env:AGENCY_DATABASE_SCHEMA="electrolink_ops"
uv run python -m alembic upgrade head
```

Enumerate the real targets rather than trusting this list — query `firms` plus `firm_storage_mappings`, and remember `Remove-Item Env:\AGENCY_DATABASE_*` afterwards.

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
- Everything else goes through `FirmRegistryTenantResolver` → `MultiTenantDatabaseProvider`, which resolves a firm to `SHARED` (shared DB + `firm_shared` schema), `SCHEMA` (dedicated schema), or `DATABASE` (dedicated database, credentials from `AGENCY_TENANCY_CONNECTION_PROFILES`). PostgreSQL `search_path` is applied per session.

Business services stay storage-agnostic: they receive a `Session` and never know the deployment mode. Default local layout is two schemas in one database — `platform` (identity, RBAC, firm registry) and `firm_shared` (firm-owned modules).

### Authorization

**Any code you pass to `require_permission` must also exist in `PERMISSION_GROUPS` in `app/identity/system_seed.py`.** An unseeded code has no permission row, so it cannot be attached to any role, and the endpoint silently becomes platform-admin-only (their check short-circuits the lookup). Twelve codes were in this state until 2026-08-09. `tests/unit/test_identity_hardening.py::test_every_enforced_permission_code_is_seeded` now fails the build if it recurs; adding codes to the seed also needs a migration to insert them into existing databases (see `20260809_0044`).

`Principal` + `require_permission("CODE")` from `app.core.security.authorization`. Firm-owned routers compose a scope dependency that (a) checks the permission code and (b) validates active `UserFirm` membership for `X-Firm-ID` — platform admins are **not** exempt from supplying a firm context on firm-owned resources. See the `_permission()` / `CustomerViewScope` pattern in `app/customers/api/router.py` and copy it. Permission codes are `DOMAIN_ACTION` (`CUSTOMER_VIEW`, `TAX_RULE_SIMULATE`) and are seeded in `app/identity/system_seed.py`; system roles/permissions are immutable via the API.

### Entities and responses

All business entities extend `BaseEntity` (`app/core/database/entity.py`): UUID id, created/updated actor + timestamp, `version` for optimistic concurrency, `is_deleted`/`deleted_at` soft delete. Repositories exclude soft-deleted rows unless explicitly asked. Audit logs are the exception — append-only, enforced by the `TR_audit_logs_append_only` trigger; every mutation must emit one via `app.common.audit`.

**The audit trail is per store, not central.** Platform administration writes to `platform.audit_logs`; every firm-owned mutation writes to that firm's own store, because `record_audit` runs on whichever session `get_db` resolved. That is deliberate — a DATABASE-mode firm's history has to live inside its own database for the isolation and per-firm restore guarantees to hold. The consequence: **no single query can answer "everything that happened"**; a cross-firm view must iterate firm stores. `GET /api/v1/audit-logs` reads one trail, chosen by firm context — no `X-Firm-ID` plus platform authority gives the platform trail, `X-Firm-ID` gives that firm's. Date filters are inclusive UTC calendar days, matching the `created_from`/`created_to` convention in the customer and product list filters.

Responses always use `ApiResponse` / `PaginatedResponse` from `app/core/responses/models.py` (`success`, `data`, `message`, `timestamp`, `requestId`, plus `pagination.{page,page_size,total_records,total_pages}`). List endpoints accept only the whitelisted `page`, `page_size`, `search`, `sort_by`, `sort_direction`.

### Cross-cutting frameworks

Prefer extending these over adding module-specific machinery:

- **Business Profile Framework** (`app/business`) — industry profiles decide which features and modules a firm operates. `docs/BUSINESS_PROFILE_FRAMEWORK.md` is the reference: table map, resolution flow, what is actually enforced versus merely recorded, and how to extend it. Never hardcode industry behaviour into entities; declare a feature and gate on it.
  - Enforce server-side with `require_feature("CODE")` / `require_module("CODE")` from `app/business/gating.py`, used exactly like `require_permission`. They are **write-only**: safe methods always pass, so enabling a gate can never hide data a firm already has. A firm with no profile resolves to the platform default (GENERIC).
  - The desktop's `/active-modules` filtering is cosmetic and is *not* a security boundary — it only hides menu entries.
  - As of 2026-08-09 only `batch_serial` is gated (`BATCH_TRACKING`, `SERIAL_NUMBER`) as the reference implementation. 18 of 21 declared features still have no enforcement anywhere; adding it is per-module work, and each one needs a product decision about what the feature actually means.

- **Configurable custom fields** — a module gains industry-specific fields through `AttributeService` (`app/business/services/attribute_service.py`), never by adding columns. An `AttributeDefinition` targets an `entity_type` (`PRODUCT`, `CUSTOMER`, `VENDOR`, …) and is optionally scoped to one business profile, so a pharmacy firm carries fields a food firm does not.
  - **The catalogue is shared; value storage is per module.** Each module owns a small table extending `AttributeValueBase` — `product_attribute_values` is the reference — which keeps a real FK to the owning record and its own indexes. The service is parameterised by that model, so there is still one implementation, one set of tests, and one form renderer.
  - Values live in typed `value_text` / `value_number` / `value_date` / `value_boolean` columns so list filters and reports can index and query them. Never store custom fields as JSON: a `products.category_attribute_values` blob existed until 2026-08-09 and could not be filtered.
  - **To extend a new module:** add an `AttributeEntityType` member, a ~20-line table extending `AttributeValueBase` with `ENTITY_TYPE` / `OWNER_COLUMN` set, a migration, and calls to `replace_values` on save and `values_for` / `values_for_many` on read.
  - Read attributes for a list of records with `values_for_many`, never per row — `ProductService._products_matching_attribute` shows the pattern for filtering.
- **Document Lifecycle Framework** (`app/document_framework`) — configurable document types, states, numbering rules, and timeline events for transactional modules. Lifecycle states are configuration, not enums.
- **Tax framework / rule engine** (`app/tax`), **UOM & packaging** (`app/uom`), **batch/serial/expiry** (`app/batch_serial`).

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
- **Bulk endpoints are a second implementation.** The six branch/warehouse bulk operations wrote no audit rows and skipped the delete guards their single-row twins enforced, so review both paths. Exclusivity flags (`is_default`) are demoted in the service and backed by a partial unique index (`UQ_branches_default_active`, `UQ_warehouses_default_active`, `20260809_0056`); demotion must flush before the promoted row is written.
- **Never let NULL ordering pick a row.** PostgreSQL sorts NULLs first in `DESC`, SQLite last, so `ORDER BY product_id DESC` made a firm-wide UOM conversion rule outrank a product's own factor in production while the unit suite saw the right answer. Rank on `case((col.is_(None), 1), else_=0)` and cover it in `tests/integration/`.
- **`BaseEntity.version` is the mapper's version id.** Every ORM update bumps it and checks it, so a stale write raises `StaleDataError` (mapped to 409). Bulk `query().update()` bypasses this by design. Update endpoints accept `If-Match` carrying the version the client last read.
- **Document lines are reconciled on their line number, not deleted and re-inserted**, in `sales_order`, `purchase`, `goods_receipt` and `delivery_note`. Downstream documents record `source_document_line_id` as a bare UUID with **no foreign key**, so re-inserting lines silently left those references dangling. The three invoice modules still re-insert; their lines are terminal.
- `app/finance/` was rewritten on 2026-08-09 and is live at `/api/v1/finance` (migration `20260809_0042`). It uses the seeded `accounting` / `financial_year` permission codes rather than a `FINANCE_*` namespace. Automatic GL posting from invoices is **not** built: it needs a per-firm control-account mapping design. The prior `accounting_event_consumer.py`, which guessed accounts by name, was removed — see git history if you want its posting rules.
- Config is `pydantic-settings` reading `backend/config/.env` with the `AGENCY_` prefix; env vars override the file. `config/.env` is never committed. Staging/production refuse to start with the development JWT key or without an explicit bootstrap admin password.
- PostgreSQL 17 is the primary target; MySQL is supported by the connection layer but some constraints (the `UQ_user_firms_active_primary` and `UQ_users_email_active` partial indexes) are PostgreSQL-only — the matching service-level checks stay authoritative.
- `users.email` is unique **only among live accounts**, so soft-deleting a user releases their address for re-onboarding. Filter `is_deleted` in any email lookup. `firms.code`, `gst_number` and `pan_number` work the same way since `20260809_0054` — partial indexes named `UQ_firms_<column>_active`.
- **A firm's storage routing is fixed at creation.** `provision_new_firm` runs only on create and nothing migrates a firm's rows between stores, so `FirmService.update` rejects any change to `deployment_mode`/`schema_name`/`database_name`, and omitted tenancy fields inherit the stored mapping instead of defaulting to `SHARED`. Two firms are never allowed to share one database/schema pair — soft-deleted firms included, because their data is still there.
- `refresh_tokens`, `login_history` and `password_history` have no automatic cleanup of their own, and neither does `tax_rule_execution_logs`. **`scripts/purge_retention.py` is the one to run**: it enumerates every firm store from the registry — dedicated schemas and dedicated databases included — and applies both retention services, so it cannot miss a store the way running the two single-purpose scripts by hand does. `--dry-run` reports, `--yes` applies. The `retention` service in `docker-compose.yml` runs it on a loop (`AGENCY_RETENTION_INTERVAL_SECONDS`, default daily); set `AGENCY_RETENTION_MODE=--dry-run` to watch it first. `scripts/purge_identity_history.py` and `scripts/purge_tax_execution_logs.py` remain for pruning one store on its own. `tax_rule_execution_logs` is the same shape and grows fastest — one row holding three JSON documents per document line — and is pruned per firm store by `scripts/purge_retention.py` (every store at once) or `scripts/purge_tax_execution_logs.py` (one store, selected with `AGENCY_DATABASE_SCHEMA` the way a migration does).
- **`TaxRuleService.simulate` is the tax calculation, not a preview.** All seven transactional modules call it once per line while building a document, on their own session, so it must never commit — the `/simulate` endpoint owns that. It also derives `country_id` from the applied profile's tax system and `business_profile_id` from the firm's assignment, because no document sends either and rules scoped that way otherwise never match. `total_tax_amount` is only what the counterparty is billed: tax `included_in_price` and tax under `REVERSE_CHARGE` are reported in `inclusive_tax_amount` / `reverse_charge_tax_amount` and must not be added to a document total.
