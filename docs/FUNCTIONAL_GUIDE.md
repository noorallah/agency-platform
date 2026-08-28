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

## The order

| Phase | # | Module | Done |
| --- | ---: | --- | --- |
| **A — Stand the firm up** | 1 | Firm setup and access | ✅ |
| | 2 | Business profile: what the firm may operate | ☐ |
| | 3 | Document numbering and lifecycle | ☐ |
| | 4 | Financial year and chart of accounts | ☐ |
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

# Still to write

Modules 2–20 in the table above. Each gets the same six parts.
