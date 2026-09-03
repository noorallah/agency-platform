# Functional guide, module by module

What each module is **for**, what you **configure** before using it, the
**workflow** it runs, **how to drive it** from the desktop, and the **tables**
it writes. No code walkthroughs — the file that maps a workflow onto a
permission and a table, so somebody can operate the platform or specify a
change to it.

Filled in one module at a time. The order below is the order a firm actually
does things in, which is **not** the code-dependency order in
[`LEARNING_PATH.md`](LEARNING_PATH.md): you cannot raise an invoice before
there is a tax rate, and you cannot set a tax rate before there is a firm.

## Every section has the same six parts

| Part | Answers |
| --- | --- |
| **What it does** | The business job, in a paragraph |
| **Configure first** | What must exist before the module works, and what breaks if it doesn't |
| **Workflow** | The steps: who does it, what it changes, what status it lands in |
| **How to use it** | The desktop path and the actions on each screen |
| **Tables** | What is stored where, and which columns carry the meaning |
| **Rules that bite** | The refusals and defaults that surprise people |

Permission codes appear in the workflow tables. Endpoint tables are generated,
never typed: `uv run python scripts/dump_route_permissions.py --markdown <module>`.

**In a hurry?** [Runbook — a new firm, from nothing to trading](#runbook--a-new-firm-from-nothing-to-trading)
is the five steps that take an empty installation to a firm that can raise and
settle a document, and it names the one step that has no screen.

## The order

| Phase | # | Module | Done |
| --- | ---: | --- | --- |
| **A — Stand the firm up** | 1 | Firm setup and access | ✅ |
| | 2 | Business profile: what the firm may operate | ✅ |
| | 3 | Document numbering and lifecycle | ✅ |
| | 4 | Financial year and chart of accounts | ✅ |
| **B — Masters** | 5 | Branches and warehouses | ☐ |
| | 6 | Geography | ☐ |
| | 7 | Units and packaging | ☐ |
| | 8 | Tax setup | ☐ |
| | 9 | Products, attributes, batch and serial | ☐ |
| | 10 | Customers and credit policy | ☐ |
| | 11 | Vendors | ☐ |
| | 12 | Territory, routes and beats | ☐ |
| | 13 | Price lists and discounts | ☐ |
| **C — Buying** | 14 | Purchase order → receipt → invoice → return | ☐ |
| **D — Selling** | 15 | Quotation → order → delivery → invoice → return | ☐ |
| **E — Money** | 16 | Receipts, payments and refunds | ☐ |
| | 17 | Commission | ☐ |
| | 18 | Journals, ledgers and financial reports | ☐ |
| **F — Running it** | 19 | Inventory operations | ☐ |
| | 20 | Reports, search, audit and diagnostics | ☐ |

---

# 1. Firm setup and access

## What it does

The platform serves many firms from one installation. A **firm** is a trading
entity with its own customers, stock, documents and books; a **user** is a
person; a **membership** joins the two. Nothing else in the platform works
until all three exist, because every firm-owned screen is authorized twice —
once on what the user may do, once on which firm they may do it to.

Where a firm's data physically lives is also decided here, and **only** here:
a firm can share the common store, take a schema of its own, or take a whole
database of its own on another server. That choice is made when the firm is
created and cannot be changed afterwards, because nothing migrates rows
between stores.

## Configure first

Server-side, in `backend/config/.env` (prefix `AGENCY_`, environment variables
override the file). These decide what a new firm gets by default:

| Setting | Default | What it decides |
| --- | --- | --- |
| `AGENCY_TENANCY_SHARED_DATABASE_NAME` | `agency_platform` | The database shared-mode firms live in |
| `AGENCY_TENANCY_SHARED_SCHEMA_NAME` | `firm_shared` | The schema they share |
| `AGENCY_TENANCY_DEDICATED_SCHEMA_PREFIX` | `firm_` | Prefix for a schema-mode firm's own schema |
| `AGENCY_TENANCY_DEDICATED_DATABASE_PREFIX` | `erp_` | Prefix for a database-mode firm's own database |
| `AGENCY_TENANCY_CONNECTION_PROFILES` | *(empty)* | Named remote servers, as JSON: host, port, username, password. A firm naming one is built and served **on that server** |
| `AGENCY_JWT_ACCESS_TOKEN_MINUTES` | `15` | How long a session token lasts before the client silently refreshes |
| `AGENCY_JWT_REFRESH_TOKEN_DAYS` | `7` | How long "stay signed in" lasts |
| `AGENCY_SECURITY_MAX_LOGIN_ATTEMPTS` | `5` | Failed logins before the account locks |
| `AGENCY_SECURITY_LOCKOUT_MINUTES` | `15` | How long the lock holds |
| `AGENCY_SECURITY_PASSWORD_HISTORY_COUNT` | `5` | How many old passwords cannot be reused |
| `AGENCY_BOOTSTRAP_ADMIN_PASSWORD` | — | The first platform admin's password. Staging and production **refuse to start** without it, or with the development JWT key |

An unknown `connection_profile` on a firm is refused when the firm is created,
not at first use — a typo would otherwise produce a firm that provisions
nothing and fails far from the request that caused it.

## Workflow

### A. Bring a firm into service

| # | Step | Who | Permission | Result |
| --- | --- | --- | --- | --- |
| 1 | Record the firm — name, code, GST, PAN, currency, financial-year start, and the storage choice | Platform admin | `PLATFORM-ADMIN` | Row in `firms` + intent in `firm_storage_mappings`. **Nothing is built yet** |
| 2 | Provision its storage (dedicated firms only) | Platform admin | `PLATFORM-ADMIN` | Database and/or schema created, migrations run, platform tables pruned, `provisioned_at` stamped |
| 3 | Assign a business profile | Platform admin | `PLATFORM_VIEW` + `FIRM_VIEW` | Decides which features and modules the firm operates (module 2) |

Step 1 records intent only, so a remote server that is slow or unreachable
cannot fail the creation of the firm record. Until step 2 succeeds the firm is
refused by name — *"Firm storage for 'X' has not been provisioned yet"* — and
the reason a build failed is kept on the record, not only in the logs.
**Re-running step 2 is the repair action**; every step is create-if-missing.

Shared-mode firms skip step 2 entirely, and asking for it is refused.

### B. Give somebody access

Three separate grants, held by different people on purpose:

| # | Step | Who | Permission | Grants |
| --- | --- | --- | --- | --- |
| 1 | Create the user account | User admin | `USER_CREATE` | Nothing yet — an account with no membership can sign in and open nothing |
| 2 | Assign roles | Role admin | `ROLE_ASSIGN` | *What* they may do — the permission codes behind those roles |
| 3 | Assign firms | Platform admin | `PLATFORM-ADMIN` | *Whose data* they may do it to, and which firm opens by default (`is_primary`) |

### C. Sign in and pick a firm

| # | Step | Permission | Notes |
| --- | --- | --- | --- |
| 1 | Log in | *(open)* | Writes `login_history`; too many failures lock the account for the configured window |
| 2 | Choose a firm | authenticated | The client's firm switcher; every later request carries that firm's id |
| 3 | Work | per-screen code + membership | Both are checked. **A platform admin still has to pick a firm** to open firm-owned screens |
| 4 | Change password | authenticated | A user flagged to change their password fails **every** permission check until they do — so a forced reset locks the whole application, not just one screen |

## How to use it

| Task | Where |
| --- | --- |
| Create, edit, provision firms | **Masters › Firms** (`FIRM_VIEW`) |
| A firm's own details and preferences | **Masters › Firm Settings** (`FIRM_VIEW`) |
| Create users, reset passwords | **Administration › Users** (`USER_VIEW`) |
| Define roles | **Administration › Roles** (`ROLE_VIEW`) |
| See the permission catalogue | **Administration › Permissions** (`PERMISSION_VIEW`) |
| Attach people to firms | **Administration › User-Firm Assignments** (`USER_VIEW` + `USER_UPDATE` + `FIRM_VIEW`) |
| Read who changed what | **Settings › Audit Log** (`AUDIT_LOG_VIEW`) |

The firm switcher lives in the shell header and lists only firms the signed-in
user is an active member of.

## Tables

All of these live in the **platform** schema only — no firm store holds a copy,
which is why a firm-owned screen cannot resolve a user's name without asking
the platform store for it.

| Table | Holds | Columns that carry the meaning |
| --- | --- | --- |
| `firms` | The trading entity | `code`, `gst_number`, `pan_number` (unique among live rows only), `currency_code`, `financial_year_start`, `status`, `is_active` |
| `firm_storage_mappings` | Where that firm's data lives | `deployment_mode` (`SHARED`/`SCHEMA`/`DATABASE`), `database_name`, `schema_name`, `connection_profile`, `provisioned_at`, `provisioning_error` |
| `users` | People | `email` (unique among live accounts only), lock and password-change flags |
| `platform_admins` | Who is a platform administrator | — |
| `roles` | Named bundles of permission | system roles are immutable through the API |
| `permissions` | The permission catalogue | `code` — `DOMAIN_ACTION`, e.g. `CUSTOMER_VIEW` |
| `user_roles` | Which roles a person holds | — |
| `role_permissions` | Which codes a role grants | — |
| `user_firms` | **Membership** — whose data a person may touch | `is_primary` (the firm that opens by default), `is_active` |
| `user_preferences` | Per-user client settings | — |
| `refresh_tokens` | Live sessions | Pruned only by the retention job |
| `login_history` | Sign-in attempts | Pruned only by the retention job |
| `password_history` | Old passwords, to stop reuse | Pruned only by the retention job |

**The audit trail is per store, not central.** Firm administration writes to
`platform.audit_logs`; a firm's own work writes to that firm's store. No single
query can answer "everything that happened" across firms.

## Rules that bite

- **Storage routing is immutable.** An edit that changes deployment mode,
  schema, database or connection profile is refused. Omitting those fields
  means *keep what is stored*, not *reset to shared*.
- **Two firms may never share one database/schema pair** — soft-deleted firms
  included, because their data is still sitting there.
- **Soft delete releases the natural keys.** A deleted firm's `code`, GST and
  PAN become available again, and a deleted user's email can be re-onboarded.
- **A firm with users assigned cannot be deleted.** Remove the memberships
  first.
- **A permission code that is enforced but not seeded silently becomes
  platform-admin-only**, because the admin check short-circuits the lookup. If
  a role "has" a permission and the screen still refuses, this is why.
- **Three retention tables grow forever** unless `scripts/purge_retention.py`
  is scheduled (`docker compose --profile retention up -d`).

## Four permission rows worth questioning

Found by generating the endpoint table and reading the guard column against the
neighbouring rows. None has been driven against a running server, so each is a
question for whoever owns the module rather than a reported defect.

| Endpoint | Guard today | Why it looks wrong |
| --- | --- | --- |
| `POST /api/v1/permissions` | `PERMISSION_VIEW` | A **read** code on a write endpoint. `PERMISSION_CREATE` is seeded, and the alias binding it is declared in the router and used nowhere; the update and delete aliases are dead the same way |
| `GET /api/v1/roles/{id}/permissions` | `PERMISSION_ASSIGN` | Reading what a role holds needs the code for *granting* permissions, while reading the role itself needs only `ROLE_VIEW` |
| `GET /api/v1/users/{id}/firms` | `ROLE_VIEW` | A membership question answered behind a role code. The sibling `/users/{id}/roles` correctly takes `USER_VIEW or ROLE_VIEW` |
| `GET /api/v1/roles` | `PLATFORM-ADMIN` | The list is stricter than the `GET /roles/{id}` it lists |

Severity turns on who actually holds `PERMISSION_VIEW`: the seeded `VIEWER`
role explicitly excludes it, so the likely answer is "administrators only",
which makes the first row untidy rather than dangerous. Worth confirming rather
than assuming.

---

# Runbook — a new firm, from nothing to trading

Five steps. **Step 4 is the one that catches people**, because there is no
screen for it and nothing tells you it is missing until a document refuses to
post.

## 1. Record the firm

**Masters › Firms › New** (platform admin), or `POST /api/v1/firms`.

Required: `name`, `code` (uppercase `A-Z0-9_-`, 2–50 characters), `country`
(2 letters), `currency_code` (3 letters), `financial_year_start`. GST, PAN,
address and contacts are optional. The desktop form pre-fills `IN` / `INR` and
the current financial-year start as **defaults, not decisions** — all three stay
editable.

The one choice that can never be changed afterwards is where the data lives:

| Mode | What the firm gets | Names derived as |
| --- | --- | --- |
| `SHARED` (the form's default) | The common store — nothing to build | `agency_platform` / `firm_shared` |
| `SCHEMA` | Its own schema in the shared database | `firm_<code>` |
| `DATABASE` | Its own database, optionally **on another server** | `erp_<code>` + schema `firm_<code>` |

The prefixes come from the `AGENCY_TENANCY_*` settings in module 1. Naming a
`connection_profile` puts the firm on that server; an unknown profile name is
refused **here**, not at first use, so a typo cannot produce a firm that
provisions nothing and fails far from the request that caused it.
`database_type` must match the platform dialect.

All five storage fields appear on the form under **Storage Mapping**, editable
while creating and read-only once the firm exists — which is exactly what the
service enforces.

Two refusals to expect: a duplicate `code`, GST or PAN among live firms; and a
database + schema pair another firm already claims, **soft-deleted firms
included**, because their data is still sitting there.

**Nothing has been built yet.** That is deliberate — a slow or unreachable
target server must not fail the creation of a firm record.

## 2. Provision the storage — dedicated firms only

**Masters › Firms › Provision** (the action appears for any firm that is not
SHARED, and stays enabled until its storage is ready), or
`POST /api/v1/firms/{id}/provision`.

It creates the database and/or schema, runs `alembic upgrade head` against it in
a subprocess, prunes the platform-only tables, and stamps `provisioned_at`.
Until that succeeds every request for the firm is refused by name — *"Firm
storage for 'X' has not been provisioned yet"* — and a failure is kept in
`provisioning_error` on the record rather than only in the log.

**Re-running is the repair action**, not a risk: every step is create-if-missing
and Alembic stops at head.

What the new store holds afterwards comes from the migrations themselves — the
business-profile catalogue, features and modules, units of measure, tax systems,
geography masters. There is no application-level seeding step; the provisioning
service's seed hook has no handler wired to it.

## 3. Assign a business profile

**Administration › Profile Assignment** (module 2). Decides the firm's features,
modules and custom fields.

Skip it and the firm falls back to the store's default profile (GENERIC); if the
store has no default either, **nothing is enforced at all**.

## 4. Seed the finance setup — no screen exists for this

```powershell
uv run python scripts/seed_finance_defaults.py --yes
```

It walks every active firm **in its own store**, resolved through the tenancy
provider, so it works across all three deployment modes. It creates the account
groups, the chart of accounts, twelve monthly periods from the financial-year
start, the journal and voucher types, and the **control-account mapping**.
Idempotent — re-running reports zeros. There is deliberately no `--dry-run`,
because `FinanceService` commits inside each mutating method and a preview would
write the chart and then claim it had not.

**Why this step is load-bearing.** `firm_control_accounts` is what tells posting
which ledger account is Inventory, Trade Receivables or Output Tax, and it has
**no endpoint among the 33 finance routes and no desktop screen**. Financial
years, periods, account groups and ledger accounts can all be created through
the API; the mapping cannot. And a failed posting is allowed to fail the
document action that triggered it, on purpose — stock that moved with no
accounting entry behind it is the gap that rule closes.

So a firm that skips step 4 can enter masters and raise drafts, and then:

| Action | What happens |
| --- | --- |
| Dispatch a delivery note | Fails — no Cost of Goods Sold / Inventory accounts |
| Approve a sales invoice | Fails — no Receivables / Sales / Output Tax |
| Record a receipt | Fails — `settlements.journal_entry_id` is NOT NULL |
| Record a customer's opening balance | Refused outright — a balance nobody can book is one the firm should not be told it has recorded |

## 5. Give people access

Three grants, deliberately held by different people (module 1):

| Step | Where | Permission |
| --- | --- | --- |
| Create the account | **Administration › Users** | `USER_CREATE` |
| Assign roles — *what* they may do | **Administration › Roles** | `ROLE_ASSIGN` |
| Assign the firm — *whose data* | **Administration › User-Firm Assignments** | platform admin |

Mark one membership `is_primary`: that is the firm that opens by default. A
platform admin still has to pick a firm to open firm-owned screens.

## Then the masters, in this order

Each depends on the one before it:

1. **Branches**, then **warehouses** under them
2. **Units of measure** — check the profile defaults before products
3. **Tax** — the profile and its rates, before anything is priced
4. **Products**
5. **Customers** and **vendors** (credit policy with them)
6. **Territories and routes**, if the firm sells by round
7. **Price lists**

**Document numbering needs no setup.** Each module creates its document type,
states and numbering rule lazily on the first save, and the series can be edited
afterwards in **Settings › Numbering Series**.

## Checking it worked

| Check | Expect |
| --- | --- |
| The firm's storage is ready | `provisioned_at` set, `provisioning_error` empty |
| Its capabilities resolve | `GET /api/v1/business-framework/active-features` returns the profile's list, not an empty one |
| Finance is set up | `GET /api/v1/finance/ledger-accounts` returns the chart, and an accounting period covers today |
| A person can actually work | They can sign in, the firm appears in their switcher, and a firm-owned screen opens |

The end-to-end proof is raising one small sale — quotation to receipt — and
watching the receivable return to zero. `docs/SALES_TO_RECEIPT_FLOW.md` traces
exactly that, with the ledger lines each step raises.

## What this runbook says about the product

Two gaps are worth stating plainly rather than working around silently:

- **Finance setup has no UI path.** A firm created entirely through the desktop
  is not able to post anything until somebody with shell access runs a script.
  Either the control-account mapping needs an endpoint and a screen, or
  provisioning should seed it.
- **Nothing tells a firm it is missing.** The refusal arrives at the first
  dispatch or invoice approval, far from the setup step that was skipped. A
  readiness check on the firm record — chart present, period open, mapping
  complete — would move the message to where the decision was made.

---

# 2. Business profile: what the firm may operate

## What it does

One installation serves a pharmacy, an electronics distributor and a food
wholesaler. They need different fields, different rules and different menus —
and none of that is hardcoded per industry. A **business profile** is a named
industry (PHARMACY, ELECTRONICS, WHOLESALE …) that switches on:

- **features** — optional capabilities such as expiry tracking, serial numbers,
  barcodes, warranty, drug licence;
- **modules** — which workspaces the firm operates and in what menu order;
- **custom fields** — extra fields on products, customers, vendors and other
  masters, and which of them are mandatory for a given product category.

A firm is assigned exactly one profile. Change the profile and the firm's
fields, menus and refusals change with it — no code change, no migration.

## Configure first

| Needs | Why |
| --- | --- |
| The firm exists and is provisioned (module 1) | The catalogue is read from the firm's own store |
| A **default profile** exists in that store | A firm with no assignment falls back to it. With no default either, **nothing is enforced at all** |
| The catalogue is migrated into **every** store | `business_profiles`, `business_features` and the rest are firm-owned tables, not platform ones |

**This is the trap that costs the most time.** The catalogue lives once per
firm store, so a query against `firm_shared` shows the two dedicated-store
firms as unassigned even when they are not, and a migration run only against
the platform schema leaves those stores without the catalogue entirely. Use
`scripts/migrate_all_stores.py`.

## Workflow

### A. Decide what an industry means

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Create or pick a profile | `PLATFORM-ADMIN` | Row in `business_profiles`; one is flagged the default |
| 2 | Switch its features on or off | `PLATFORM-ADMIN` | Rows in `profile_features`. A feature marked `is_implemented = false` is **refused** |
| 3 | Switch its modules on or off, set menu order | `PLATFORM-ADMIN` | Rows in `profile_modules` — two booleans: `is_enabled` (may use) and `is_visible` (appears in the menu) |

### B. Give a firm its industry

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Assign the profile to the firm | `PLATFORM-ADMIN` | Row in `firm_business_profiles`, written **into that firm's own store** |
| 2 | The firm's users sign in | — | `/active-features` and `/active-modules` answer what they may use |

### C. What the firm then experiences

| Situation | What happens |
| --- | --- |
| Reads anything | Always allowed. **The gates are write-only**, so switching a feature on can never hide data a firm already has |
| Writes to a feature-owned endpoint | Refused outright if the feature is off — e.g. batches and serials |
| Writes a feature-owned **field** on a shared resource | The write is refused only if it *populates* that field. Blank and unchanged always pass |
| Has no profile at all | Falls back to the platform default (GENERIC). A configuration gap is not treated as a decision |

The distinction in the middle two rows is the design: gating the whole endpoint
suits a feature that owns its resource, but most features are optional *fields*
on a resource every firm uses — gating the endpoint would stop a firm creating
products because it does not scan barcodes.

### D. Custom fields

| # | Step | Permission | Result |
| --- | --- | --- | --- |
| 1 | Define an attribute — name, data type, entity type, optionally scoped to one profile | `PLATFORM-ADMIN` | Row in `attribute_definitions` |
| 2 | Make it mandatory for a profile + product category | `PLATFORM-ADMIN` | Row in `category_attribute_rules` |
| 3 | Users fill it on the record | the module's own code | Value stored in that module's `*_attribute_values` table, in a typed column |

**Mandatory is stated per profile and category, never globally.** Four
attributes were once globally mandatory, which asked a pharmacy for an IMEI and
an electronics distributor for an expiry date — and blocked product creation on
any freshly migrated database.

## How to use it

All under **Administration**, each needing `PLATFORM_VIEW`:

| Task | Where |
| --- | --- |
| Create industries, set what each enables | **Business Profiles** |
| The feature catalogue | **Feature Management** |
| The module catalogue, menu order and visibility | **Module Configuration** |
| Define custom fields | **Attribute Definitions** |
| Make a field mandatory for a category | **Mandatory Attributes** |
| Point a firm at an industry | **Profile Assignment** (`FIRM_VIEW` + `PLATFORM_VIEW`) |

## What each profile enables today

Read live from `profile_features`:

| Profile | Features |
| --- | --- |
| PHARMACY | ATTACHMENTS, BARCODE, BATCH_TRACKING, DRUG_LICENSE, EXPIRY_TRACKING, MANUFACTURING_DATE, SHELF_LIFE |
| FOOD | ATTACHMENTS, BARCODE, BATCH_TRACKING, EXPIRY_TRACKING, MANUFACTURING_DATE, SHELF_LIFE |
| MANUFACTURING | APPROVAL_WORKFLOW, ATTACHMENTS, BARCODE, BATCH_TRACKING, MANUFACTURING_DATE, MULTIPLE_WAREHOUSES |
| WHOLESALE | ATTACHMENTS, BARCODE, BATCH_TRACKING, MULTIPLE_WAREHOUSES, TERRITORY |
| AGENCY | ATTACHMENTS, BARCODE, MULTIPLE_WAREHOUSES, TERRITORY |
| ELECTRONICS | ATTACHMENTS, BARCODE, SERIAL_NUMBER, WARRANTY |
| RETAIL | ATTACHMENTS, BARCODE, EXPIRY_TRACKING, QR_CODE |
| GARMENTS | ATTACHMENTS, BARCODE, QR_CODE |
| RESTAURANT | ATTACHMENTS, EXPIRY_TRACKING, SHELF_LIFE |
| GENERIC | ATTACHMENTS, BARCODE |
| SERVICE | APPROVAL_WORKFLOW, ATTACHMENTS |
| CUSTOM | *(none — configured per deployment)* |

Modules run 10–12 per profile: RESTAURANT and SERVICE add kitchen/recipes and
projects/contracts, ELECTRONICS and MANUFACTURING get 11, everyone else the ten
core workspaces.

**Eleven of twenty-one features are actually enforced.** `BATCH_TRACKING` and
`SERIAL_NUMBER` gate whole endpoints; `EXPIRY_TRACKING`, `MANUFACTURING_DATE`,
`SHELF_LIFE`, `WARRANTY`, `BARCODE`, `QR_CODE`, `DRUG_LICENSE`, `ATTACHMENTS`
and `VEHICLE_TRACKING` gate fields. `TERRITORY`, `APPROVAL_WORKFLOW` and
`MULTIPLE_WAREHOUSES` have working code and are deliberately ungated pending a
product decision — enforcing `TERRITORY` today would take routes away from
PHARMACY, FOOD and RETAIL, which plausibly sell by territory. Six of the
remaining codes have no backing code and stay `is_implemented = false`:
`IMEI`, `PRESCRIPTION_REQUIRED`, `RECIPE_MANAGEMENT`, `KITCHEN_MANAGEMENT`,
`SERVICE_CONTRACTS` and `PROJECT_MANAGEMENT`.

## Tables

Every one is **firm-owned** — it exists once per store.

| Table | Holds | Columns that carry the meaning |
| --- | --- | --- |
| `business_profiles` | The industries | `code`, `is_default` (the fallback for unassigned firms) |
| `business_features` | The capability catalogue | `code`, `default_enabled`, `is_implemented` |
| `business_modules` | The workspace catalogue | `code`, `default_enabled` |
| `profile_features` | Which features an industry enables | `is_enabled` (overrides `default_enabled`), `configuration` |
| `profile_modules` | Which modules an industry enables | `is_enabled`, `is_visible`, `display_order` |
| `firm_business_profiles` | **The assignment** — firm → industry | `is_active` |
| `attribute_definitions` | Custom field definitions | `entity_type` (`PRODUCT`, `CUSTOMER`, `VENDOR`…), optional profile scope, data type |
| `category_attribute_rules` | Which fields are mandatory | `business_profile_id` (**NULL = every profile**), `category_code`, `is_mandatory` |
| `business_profile_uom_defaults` | Default units per industry | `firm_id` **NULL = the profile-wide default**; a firm's own row wins |
| `<module>_attribute_values` | The values themselves | Typed columns — `value_text`, `value_number`, `value_date`, `value_boolean`, never JSON |

**How a capability is resolved:** firm → its assignment → else the default
profile → else enforce nothing. Then per catalogue entry: an explicit
`profile_features` / `profile_modules` row wins, otherwise the catalogue's
`default_enabled`.

## Rules that bite

- **The gates are write-only.** Safe methods always pass, so turning a feature
  on can never hide data.
- **A firm with no resolvable profile is never gated.** A configuration gap is
  not a decision.
- **`is_implemented = false` refuses enabling**, and it is deliberately *not*
  `is_active`: one is a fact about the codebase, the other an administrator's
  choice. Conflating them lets someone switch on a feature that does nothing.
- **Deleting a feature or module a profile still enables revokes the capability
  for every firm on that profile** — writes those firms made yesterday start
  being rejected.
- **The desktop's menu filtering is cosmetic, not a security boundary.** It
  hides entries; the server's `require_feature` / `require_module` is the
  boundary.
- **Mandatory attributes must be scoped.** A global `mandatory` flag asks every
  industry for every field.
- **Renaming the default profile once demoted it**, leaving the store with no
  default and therefore no gating at all for unassigned firms. Fixed, but it is
  the shape to watch when editing a profile.

### ~~One inconsistency worth fixing~~ — closed by #168

Kept because the shape recurs. `20260810_0059` cleared `is_implemented` for
seven codes with no backing code. That was true of `COMMISSION` when it was
written and stopped being true on 2026-08-23, when `app/commission` shipped
with effective-dated rates, a collection-based report, seeded permissions and a
desktop screen — and the flag outlived the fact, so `_reject_unimplemented`
went on refusing an administrator a feature the platform had.
`20260903_0107` flipped it.

**`is_implemented` is a claim about the codebase, so it goes stale the moment
the codebase moves and nothing re-checks it.** Six codes still carry
`false`; each is one shipped module away from repeating this. Whatever
implements one of them has to flip its flag in the same change, the way #168
had to be a separate repair.

---

# 3. Document numbering and lifecycle

## What it does

Every transactional document needs two things a firm cares about: a **number**
somebody can quote down the phone, and a **status** that decides what may still
be done to it. Both are configuration held per firm, not code — so one firm can
run `INV-000001` and another `SI/2026-2027/000001`, and neither needs a release.

The same module keeps the **timeline** — an append-only record of every state a
document passed through and who moved it — and the **print template** that
decides what the printed copy says.

## Configure first

**Nothing.** This is the one module that needs no setup: the first time a firm
saves a document of a given kind, its document type, its states and its default
numbering rule are created on the spot.

The one input it does read is the firm's `financial_year_start` (module 1),
which decides the financial-year label a number carries and when the sequence
resets.

## Workflow

### A. First save of a document kind, in a firm

| # | What happens | Result |
| --- | --- | --- |
| 1 | The module bootstraps its own document type | Row in `document_type_definitions` — one per firm per kind |
| 2 | It creates that type's states | Rows in `document_state_definitions`, one flagged the default |
| 3 | It creates a default numbering rule | Row in `document_numbering_rules` with the module's prefix |

Thirteen kinds bootstrap this way, each with its own prefix:

| Prefix | Document | Prefix | Document |
| --- | --- | --- | --- |
| `QT` | Quotation | `PO` | Purchase order |
| `SO` | Sales order | `GRN` | Goods receipt |
| `DN` | Delivery note | `PI` | Purchase invoice |
| `SI` | Sales invoice | `PR` | Purchase return |
| `SR` | Sales return | `PC` | Physical count |
| `RC` | Receipt | `PY` | Payment |
| `RF` | Refund | | |

### B. How a number is built

Either from a `format_pattern` if the rule has one, or by joining these parts
with the rule's `separator` (default `-`), skipping any that is switched off:

```
prefix  [company_code]  [branch_code]  [financial_year]  sequence  [suffix]
  SI                                       2026-2027      000010
                     →  SI-2026-2027-000010
```

`sequence_padding` decides the zeros (default 6). `include_company_code`,
`include_branch_code` and `include_financial_year` are the switches.

### C. How the sequence resets

The counter is kept per **scope signature** — `financial year | branch |
company` — so with `auto_reset` on, a new financial year starts again at 1 while
last year's numbers stay untouched. A firm numbering per branch gets an
independent run per branch, which is what a branch that files its own returns
needs.

### D. Manual numbers

Only if the rule sets `manual_allowed`. Then a caller may supply its own number
and the sequence is not consumed — for entering historical documents that
already have numbers on paper.

### E. Every move is recorded

Each transition appends to `document_lifecycle_events`: which document, from
which state to which, by whom, when. **Append-only** — the timeline is what the
document's history *is*, and `GET /documents/{id}/timeline` is what a screen
shows.

Worth knowing what this costs: sending a quotation, accepting it, approving a
delivery note and approving a sales return each write **nothing but** a
lifecycle event and an audit row. That is the difference between paperwork and a
movement.

### F. Printing

A firm can restyle what its documents say — the banner text (`TAX INVOICE` or
`BILL OF SUPPLY`, both real documents), an accent colour, a header note, whether
bank details appear. One template per firm per document type.

Five documents render today: purchase order, tax invoice, delivery challan,
quotation and credit note.

## How to use it

| Task | Where | Permission |
| --- | --- | --- |
| Change a prefix, padding, or what a number includes | **Settings › Numbering Series** | `SETTINGS_VIEW` to see; platform admin to change |
| See what the next number will look like before saving | `GET /numbering-rules/{id}/preview` | firm membership |
| Read a document's history | The document's timeline panel | firm membership |
| Restyle the printed copy | Print template per document type | firm membership |

**Reading is firm membership alone; changing is platform admin.** Numbering and
lifecycle shape every document a firm will ever raise, so the module is
deliberately readable by everyone in the firm and writable by nobody in it.

## Tables

| Table | Holds | Columns that carry the meaning |
| --- | --- | --- |
| `document_type_definitions` | One row per firm per document kind | `code`, unique per firm |
| `document_state_definitions` | The states that kind can be in | `is_default`, `is_terminal`, `allows_edit`, `allows_print`, `allows_email`, `allows_export_pdf`, `sort_order`, `transition_rules` |
| `document_numbering_rules` | How the number is composed | `prefix`, `suffix`, `separator`, `sequence_padding`, `include_financial_year` / `_branch_code` / `_company_code`, `auto_reset`, `manual_allowed`, `format_pattern`, `is_default` |
| `document_number_sequences` | The live counter | `scope_signature` (`year\|branch\|company`), `next_sequence` |
| `document_lifecycle_events` | The timeline, append-only | from-state, to-state, actor, timestamp |
| `document_print_templates` | Per-firm print styling | `document_type`, `title_text`, `accent_color`, `header_note`, `show_bank_details`; one live row per firm per type |

## Rules that bite

- **A state is configuration; the transitions are not.** The states, their names
  and their edit/print flags live in the database, but which transition a
  service will actually perform is written in that service. Renaming a state in
  the table does not teach `approve` about it.
- **Nothing sweeps the tables.** A quotation's `EXPIRED` is derived from
  `valid_until` on read, never stored, precisely because a job that had not run
  yet would let a stale quote through.
- **The counter is per scope, so changing what a number includes changes which
  counter it uses.** Switching `include_branch_code` on mid-year starts a fresh
  run per branch rather than continuing the firm-wide one.
- **A number is reserved when the document is saved, not when it is approved.**
  A cancelled draft has consumed its number, which is normal for a
  numbering series but surprises people expecting no gaps.
- **Timeline events are append-only** and cannot be edited away, like the audit
  trail they sit beside.

### Two settings that do not do what they say

Both surfaced from the obvious question — *what can we configure this to
ignore?* The answer is: most of it, and then two things that look configurable
and are not.

**`auto_reset` is written and never read.** Its only reference outside the
model and schemas is the bootstrap setting it to `True`. The yearly reset is
not driven by that flag at all — it is driven by the scope signature, which is
built as `financial_year | branch | company` and **always** includes the year
label, whatever `include_financial_year` says:

```python
financial_year_label or str(document_date.year)
```

So setting `auto_reset = false` changes nothing, and a firm that wants one
continuous run — `SI-000001` through `SI-004312` across five years — cannot
have it.

**And the two settings interact badly.** Switch `include_financial_year` off
while the counter still resets per year, and the second year reissues the
first year's numbers: `SI-000001` in 2025-26 and `SI-000001` again in 2026-27.
**No document number column carries a unique constraint anywhere** — not
`invoice_number`, not `order_number`, not any sibling — so nothing rejects the
duplicate. Two invoices, same firm, same number, no error.

That combination is a defect rather than a gap: the configuration is offered,
it is reachable from **Settings › Numbering Series**, and taking it silently
corrupts the series.

**`manual_allowed` is unreachable.** The plumbing is complete — `reserve_number`
accepts a `manual_number` and correctly returns it without consuming the
sequence — but **no document module passes one**. The flag can be set and has no
path to a caller. The only client-supplied number anywhere is
`settlements.settlement_number`, which has its own handling and bypasses the
numbering rule. That matters for the case people want it for: entering
historical documents that already carry numbers on paper.

### What *can* be configured away, and does work

`include_financial_year`, `include_branch_code`, `include_company_code`,
`prefix`, `suffix` (all nullable), `separator` (any string, including empty),
`sequence_padding` (`1` gives `SI-1`), and `format_pattern`, which bypasses
composition entirely with `{prefix}`, `{sequence}`, `{financial_year}`,
`{branch_code}`, `{company_code}` and `{document_date}`. `INV/1`,
`2026-2027-000001` and a bare `000001` are all reachable today.

### Three tables nothing writes

`document_headers`, `document_lines` and `document_totals` are declared, exported
from the model package, and referenced by **no service, router, script or test**
— every concrete module keeps its own header and line tables instead. They are a
generic document store that was designed and then not used.

They cost nothing at runtime, and they mislead: somebody reasonably reads the
schema, finds a "documents" table, and looks there for a sales order that will
never be in it. Either wire them up or drop them; leaving three empty tables
named after the module's central concept is the expensive option.

---

# 4. Financial year and chart of accounts

## What it does

Holds the books. A **financial year** divided into **accounting periods** says
when a document may be posted; a **chart of accounts** says where the money
lands; and the **control-account mapping** translates "this is a sales invoice"
into "debit 1100, credit 4000 and 2200".

Nothing here is optional decoration. Documents post through one service that
**refuses rather than guesses**, and a refused posting fails the document action
that triggered it — so an unfinished setup here does not produce wrong books, it
stops the firm trading.

## Configure first

| Needs | Why |
| --- | --- |
| The firm, provisioned (module 1) | The books live in the firm's own store |
| Its `financial_year_start` | The year and its twelve periods are built from that date |

Then four things must exist before **any** document can post:

1. a **journal type**,
2. a **voucher type**,
3. an **open accounting period covering the document's date**,
4. a **control account for every purpose that posting touches**.

Each missing one produces a message naming it — *"No open accounting period
covers 2026-08-28"*, *"This firm has no ledger account configured for:
INVENTORY, COST_OF_GOODS_SOLD"*. Gaps in the mapping are reported **all at
once** rather than one refusal at a time.

**The whole set is created by `scripts/seed_finance_defaults.py --yes`** — see
the runbook. The mapping in particular has no endpoint and no screen.

## Workflow

### A. Open the year

| # | Step | Endpoint | Permission |
| --- | --- | --- | --- |
| 1 | Create the financial year | `POST /finance/financial-years` | `FINANCIAL_YEAR_CREATE` |
| 2 | Create its periods (twelve monthly, by convention) | `POST /finance/accounting-periods` | `FINANCIAL_YEAR_CREATE` |
| 3 | Close or reopen a period | `PATCH /finance/accounting-periods/{id}` | `FINANCIAL_YEAR_CLOSE` |

A period is `OPEN`, `CLOSED` or `LOCKED`. Only `OPEN` accepts postings.
**A locked period accepts exactly one edit: being reopened.**

Periods are numbered and coded **within their year**, not within the firm — the
seeder writes `P01`…`P12` every year, so scoping the code to the firm would have
stopped a firm ever holding a second year, and with it year-end, comparatives
and prior-year reporting.

### B. Build the chart

| # | Step | Endpoint | Permission |
| --- | --- | --- | --- |
| 1 | Account groups | `POST /finance/account-groups` | `ACCOUNT_MANAGE` |
| 2 | Ledger accounts | `POST /finance/ledger-accounts` | `ACCOUNT_MANAGE` |
| 3 | Cost and profit centres (optional) | `POST /finance/cost-centers`, `/profit-centers` | `ACCOUNT_MANAGE` |
| 4 | Journal and voucher types | `POST /finance/journal-types`, `/voucher-types` | `ACCOUNT_MANAGE` |
| 5 | **Map the control accounts** | *(script only)* | — |

The seeded chart is a conventional distribution chart, not a claim about any
firm's conventions. A firm that wants a different one builds it through the API
and remaps its control accounts — changing a code or a name is an edit to seed
data, not a migration.

### C. Post by hand

| # | Step | Endpoint | Permission |
| --- | --- | --- | --- |
| 1 | Draft a journal entry | `POST /finance/journal-entries` | `JOURNAL_CREATE` |
| 2 | Post it | `POST /finance/journal-entries/{id}/post` | `JOURNAL_POST` |
| 3 | Reverse it | `POST /finance/journal-entries/{id}/reverse` | `JOURNAL_REVERSE` |

**A posted entry is reversed, never edited or deleted.** The reversal is a
mirror entry linked to the original, so both stay on the record.

### D. Read the books

| Report | Endpoint | Permission |
| --- | --- | --- |
| Trial balance | `GET /finance/trial-balance` | `TRIAL_BALANCE_VIEW` |
| General ledger for one account | `GET /finance/general-ledger/{id}` | `LEDGER_VIEW` |
| Profit and loss | `GET /finance/profit-loss` | `PROFIT_LOSS_VIEW` |
| Balance sheet | `GET /finance/balance-sheet` | `BALANCE_SHEET_VIEW` |
| Account summaries | `GET /finance/account-summaries` | `LEDGER_VIEW` |

## The default chart

Nineteen accounts in five groups. The **Purpose** column is what document
posting actually looks up — an account with no purpose mapped is invisible to it.

| Code | Account | Type | Purpose |
| --- | --- | --- | --- |
| 1000 | Cash | Asset | `CASH` |
| 1010 | Bank | Asset | `BANK` |
| 1100 | Trade Receivables | Asset | `ACCOUNTS_RECEIVABLE` |
| 1200 | Inventory | Asset | `INVENTORY` |
| 1300 | Input Tax | Asset | `INPUT_TAX` |
| 2100 | Trade Payables | Liability | `ACCOUNTS_PAYABLE` |
| 2200 | Output Tax | Liability | `OUTPUT_TAX` |
| 2300 | Goods Received Not Invoiced | Liability | `GOODS_RECEIVED_NOT_INVOICED` |
| 3000 | Opening Balance Equity | Equity | `OPENING_BALANCE_EQUITY` |
| 4000 | Sales | Income | `SALES_REVENUE` |
| 4100 | Sales Returns | Income | `SALES_RETURNS` |
| 4200 | Discount Received | Income | `DISCOUNT_RECEIVED` |
| 4900 | Rounding | Income | `ROUNDING` |
| 5000 | Purchases | Expense | `PURCHASE_EXPENSE` |
| 5100 | Purchase Returns | Expense | `PURCHASE_RETURNS` |
| 5200 | Cost of Goods Sold | Expense | `COST_OF_GOODS_SOLD` |
| 5300 | Discount Allowed | Expense | `DISCOUNT_ALLOWED` |
| 5400 | Purchase Price Variance | Expense | `PURCHASE_PRICE_VARIANCE` |
| 5500 | Inventory Adjustment | Expense | `INVENTORY_ADJUSTMENT` |

Groups: `CA` Current Assets, `CL` Current Liabilities, `REV` Revenue, `EXP`
Direct Expenses, `EQ` Equity.

**`2300` and `5400` are the two people ask about.** *Goods Received Not
Invoiced* holds the accrual between a receipt and the bill for it. *Purchase
Price Variance* takes the difference when goods leave stock at a different
average from what a document said they cost — which is what stops a reversal
putting the ledger out against the warehouse.

A purpose must resolve to an account of the right classification: mapping
revenue onto an expense account is refused at mapping time rather than
discovered in a report.

## How to use it

| Task | Where |
| --- | --- |
| Open and close years and periods | **Masters › Financial Years** |
| Post and reverse journal entries | **Finance › Journal Entries** |
| Trial balance, P&L, balance sheet, ledger statement | **Finance** workspace |
| Map control accounts | **Nowhere — script only** |

## Tables

All firm-owned, in the firm's own store.

| Table | Holds | Columns that carry the meaning |
| --- | --- | --- |
| `financial_years` | The year | `starts_on`, `ends_on`, `is_active`, `is_locked` |
| `accounting_periods` | Its periods | `period_number` and `code` unique **per year**, `status` (`OPEN`/`CLOSED`/`LOCKED`) |
| `account_groups` | Classification for rollups | `code`, `account_type` |
| `ledger_accounts` | The chart | `code`, `account_type`, group |
| `firm_control_accounts` | **Purpose → account** | `purpose`, `ledger_account_id`. No API, no screen |
| `journal_types`, `voucher_types` | Required references for any posting | `code` |
| `journal_entries` | The entry | date, status, `reversal_of_id` |
| `journal_lines` | Its legs | account, debit, credit, narration |
| `gl_postings` | The ledger itself | what reports read |
| `ledger_balances` | Running balances | — |
| `customer_ledgers`, `vendor_ledgers` | Party sub-ledgers | — |

## Rules that bite

- **A posting failure fails the document.** Dispatch, invoice approval, receipts
  and returns all refuse rather than proceed unposted. That is deliberate: stock
  that moved with no accounting entry behind it is the gap the rule closes.
- **A date with no open period stops everything dated in it** — including
  backdated documents, which is what a firm building history hits first.
- **A posted entry is reversed, never edited.** Reversals are linked, and a
  lookup that filters only on POSTED will find the mirror and reverse the
  reversal; the reversal chain must be excluded explicitly.
- **The balance check and the stored lines must round the same way.** Checking
  a document balanced at four decimals while storing legs at two once allowed
  lines a cent apart with `is_balanced` true — and `gl_postings` copies line
  amounts straight through.
- **A ledger statement is dated by the journal date, not by when it was
  posted.** It was ordered by the wall clock at posting once, which puts a
  backdated entry in the wrong place.
- **Twelve periods is a convention, not a rule.** The seeder writes twelve
  monthly ones; the API will create any periods you ask for.

### The gap, stated once

`firm_control_accounts` is the only table in this module with no endpoint and no
screen, and it is the one without which nothing posts. Financial years, periods,
groups, accounts, journal and voucher types are all creatable through the API,
so a firm can be fully set up in every visible respect and still be unable to
approve an invoice. Either the mapping needs a screen, or provisioning should
seed it — and a readiness check on the firm would say which of the four
preconditions is missing before somebody discovers it at dispatch.

---

# Still to write

Modules 5–20 in the table above. Each gets the same six parts.
