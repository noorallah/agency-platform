# Data trail by operation — what each action writes, and where to look

A companion to `docs/MANUAL_UI_TEST_PLAN.md` for checking at the **table**
level. The plan says what the screen should show; this says which rows an
action inserts, updates or soft-deletes, which audit row it writes and in
which store, and gives a query to paste. Every claim was read off the service
code on 2026-09-15 (the writes in `identity_service.py`, `firm_service.py`,
`readiness.py`), not from memory; the audit action names are the literal
strings the code records.

**Pass 1 covers the identity, roles, templates, firm-setup and audit
operations — plan sections 16 to 27.** The trading sections (sales, purchase,
stock, finance, loyalty, TCS) are `docs/WHAT_HAPPENS_CHECKLIST.md` at the
screen level and will be extended here section by section before each is
re-tested; a dispatch touches eight tables across four subsystems and is not
worth writing from memory.

**Pass 2 began on 2026-09-18 with Buying (§9)**, the operations the
TC-BUY cases in `docs/INDEPENDENT_TEST_CASES.md` drive: order, approval,
receipt, cancellation, supplier invoice, return, payment and the purchasing
reports. It was read off the five purchasing services and everything they
call, then checked with read-only queries against the rows the fixtures left
in TEST01 and the history in WHOLE01; §9.15 says which claims a live row
confirmed and which it could not. **Stock followed the same day (§10)**: the
reads, transfers, write-offs, quarantine, physical counts, the stock side of
a dispatch, batches and serials, and the `_REVERSAL` twins, checked against
TEST01, WHOLE01 and the per-run pharmacy and electronics stores the fixtures
left behind (§10.12). **Selling followed on 2026-09-19 (§11)**: price
resolution, quotations, orders and their claims, credit limits, holds,
delivery notes, invoices, receipts and TCS, returns, credit notes, proformas,
loyalty and the shortened chain, checked against the selling fixture stores
and WHOLE01 (§11.22). **Finance followed the same day (§12)**: opening the
books, closing and reopening periods, the chart, hand journals and their
reversal, the journals each document posts, cost and profit centres, control
accounts, how ledger balances roll forward, the three statements, customer
statements and ageing, opening balances, the ledger side of money in and out,
and what `verify_sample_data.py` checks — against the `ready-firm` and
selling stores, TEST01 and WHOLE01 (§12.16). **Compliance followed the same
day (§13)**: tax configuration, the GST template, tax rules and their
versions, the engine and what every priced line writes, the tax a line gets,
GSTR-1 and GSTR-3B, e-invoice registration and withdrawal, e-way bills, and
TCS from settings to reversal — against the `compliance-firm` stores, one
built for the pass and driven, the selling stores, WHOLE01, the shared store
and ELEC01 (§13.13). **Configuration followed the same day (§14)**: business
profiles, features and what a firm resolves to, custom-field definitions,
rules and values, numbering series and what issuing a number writes, document
types and states, units, packaging and conversion rules, geography, the sales
stages, the credit policy, the loyalty scheme, the firm side of the Set up
panel, and preferences — against a `config-firm` store built for the pass and
driven, the fixture and selling stores, TEST01, WHOLE01 and the shared store
(§14.19). Tax configuration is §13. **Identity, firms and audit followed the
same day (§15)**: sign-in, refresh and sign-out, passwords, users,
memberships and the switcher, roles and the two grant tiers,
`authorization_version` and the platform narrowing, templates and clone, the
firm registry and where a firm lives, provisioning, the audit trail and its
merged read, and retention — pass 1's §2 to §7 re-read against the rows of
`platform`, every store's trigger and three fixture runs, with its errors
corrected in place (§15.13). **Masters closed the same day (§16)**: customers,
their segments, the standing discount and the credit limit, vendors and their
six child collections, categories and types, products, their categories,
prices, units and tracking flags, branches, warehouses and storage areas, and
what every delete, bulk action, import and export writes — read off the four
master services and checked against every store on the server, then driven on
six fixture runs (§16.21). What a document does to a master is §9 to §14 and is
not repeated there. **Territory, commission and targets followed the same day
(§17)**: the hierarchy, territories and routes, a round's customers and its
salespeople, beat plans and call lists, how a document gets its territory,
route and salesperson, commission rules and their ladders, the report, a
payout from accrual to approval, payment and cancellation with the journal
each posts, and sales targets and their achievement — read off `app/sales`,
`app/commission` and `app/sales_targets`, checked against every store on the
server, then driven on a `commission-firm` run (§17.18). **Reports, the
dashboard, global search and diagnostics closed the pass on 2026-09-23
(§18)**: the fifty-seven catalogued reports and what each reads, the Reports
workspace, the platform dashboard, Ctrl+K and its forty-one definitions, the
error reports and the health probes — read off twelve services and the
desktop, checked against WHOLE01, the shared store and `platform`, then
driven on TEST01 (§18.11).

---

## 1. How to look

### 1.1 Three places, not one

Firm-owned tables exist **once per store**. A query against the wrong schema
shows an empty table and looks like "nothing was written". This is the
single most common way a table-level check goes wrong here.

| What | Database | Schema | Holds |
| --- | --- | --- | --- |
| Platform | `agency_platform` | `platform` | identity, roles, permissions, templates, firm registry, `user_preferences`, its own `audit_logs` |
| MEDI01, FOOD01 | `agency_platform` | `firm_shared` | both firms' trading data, side by side, told apart by `firm_id` |
| TESTSH1, TESTSH2 | `agency_platform` | `firm_shared` | the two fixture firms built by `shared-pair`, beside MEDI01 and FOOD01 — filter on `firm_id` |
| WHOLE01 | `agency_platform` | `wholesale_hub` | that firm alone |
| **TEST01** | `agency_platform` | **`test_fixtures`** | the independent cases' firm: almost every fixture writes here, and it accumulates every run |
| TEST02 | `agency_platform` | `test_fixtures_2` | the second fixture firm, for cases needing two |
| LEARN01 | `agency_platform` | `firm_learn01` | that firm alone |
| SNTEST01 | `agency_platform` | `"SNTEST01"` | that firm alone — the name is upper case, so SQL must double-quote it: `"SNTEST01".audit_logs` |
| `<SUFFIX>-S`, `-T`, `-G`, … | `agency_platform` | `fx_<suffix>_<letter>` | one store per fixture run for the cases that change something firm-wide; the firm is soft-deleted when the run is cleared and the schema stays |
| ELEC01 | **`agency_electrolink`** | `electrolink_ops` | that firm alone — **a separate connection in DbVisualizer** |

Set up two DbVisualizer connections: one to `agency_platform`, one to
`agency_electrolink`. Every query below is schema-qualified, so no
`search_path` is needed. Section 1 of `backend/scripts/sql/check_backend_data.sql`
prints this map from the registry if it ever changes. The table above was read
from `platform.firm_storage_mappings` on 2026-09-18; TEST01, TEST02, TESTSH1,
TESTSH2, LEARN01 and SNTEST01 were missing from pass 1.

### 1.2 Columns every business row carries

All entities extend `BaseEntity` (`app/core/database/entity.py`):

| Column | Meaning |
| --- | --- |
| `id` | UUID |
| `created_at`, `created_by` / `updated_at`, `updated_by` | who and when; `*_by` is a user id |
| `version` | optimistic-concurrency counter, **+1 on every ORM update** — a row whose version moved was written, even if no visible column changed |
| `is_deleted`, `deleted_at`, `deleted_by` | **soft delete**. Nothing here is physically removed except by the reseed scripts. "Deleted" on screen means `is_deleted = true` |

`audit_logs` is the exception: append-only, and a trigger
(`TR_audit_logs_append_only`) refuses `UPDATE`/`DELETE` on it in every schema.
It carries the `version` and soft-delete columns like every other table, but
they never move — checked 2026-09-18: all 542 rows in `test_fixtures` read
`version = 1`, `is_deleted = false`.

### 1.3 The audit trail is per store, and one screen merges two

- User, role, template and firm administration writes to **`platform.audit_logs`**, carrying `firm_id` where the action was about a firm — **not always**: a membership change never carries one, and a platform administrator's user and role edits carry none, so neither reaches the firm's screen (§15.10, D-IDN-5).
- Everything a firm does to its own data writes to **that firm's** `audit_logs` (`wholesale_hub.audit_logs`, and so on).
- **Settings → Audit Logs** with a firm selected shows that firm's rows **merged with** the platform rows carrying its `firm_id`, in one time order. So a promotion you see in WHOLE01's screen is a `platform.audit_logs` row; querying `wholesale_hub.audit_logs` alone will not find it.

Columns: `created_at, action, entity_type, entity_id, actor_id, firm_id, before_data, after_data, ip_address, application_version`. `actor_id` and `entity_id` are UUIDs — the screen resolves them to names since #407/#409, the table does not.

### 1.4 The one query worth memorising

Before an operation, note the time. After it, this shows **everything the
operation wrote to that store's trail**:

```sql
select created_at, action, entity_type, entity_id, actor_id, firm_id,
       after_data
from   platform.audit_logs
where  created_at > now() - interval '2 minutes'
order  by created_at desc;
```

Swap `platform` for the firm's schema to see the firm-side rows. Two rows
for one click is normal: applying a template records both
`user_template.applied` and `user.roles_set`, because it goes through the
ordinary role-setting path.

### 1.5 Token revocation, which you cannot see in a table but will feel

Many identity writes end with `_revoke_user_tokens`, which does
`users.authorization_version += 1`. Every access token carries the version it
was minted with, and a request with a stale one is refused — so the person is
**signed out on their next click**, without being asked. Where a row below
says *revokes tokens*, that is the observable effect, and the column to check
is `users.authorization_version` before and after.

---

## 2. Signing in and out (plan sections 2, 16, 26a)

### Sign in — `POST /api/v1/auth/login`
- **Store:** platform
- **Inserts:** `login_history` — one row **per attempt, successful or not**: `attempted_email, outcome, client_ip, user_agent, failure_reason`. `refresh_tokens` — one row on success: `user_id, token_hash, expires_at, revoked_at (null)`.
- **Updates:** `users.last_login_at`; on a wrong password `users.failed_login_attempts += 1`, and at the threshold `users.locked_until` is set; on success both reset.
- **Audit:** `identity.login` (success only).
- **Check:**
  ```sql
  select created_at, attempted_email, outcome, failure_reason, client_ip
  from   platform.login_history
  order  by created_at desc limit 10;
  ```
  A lockout shows as several `outcome` failures then `locked_until` on the user; the refusal on screen names the state *before* the password is looked at, deliberately.

### Sign out — `POST /api/v1/auth/logout`
- **Updates:** `refresh_tokens.revoked_at` on the current token.
- **Audit:** `identity.logout`.

### Token refresh — automatic, once, after a 401
- **Inserts:** a new `refresh_tokens` row; the old one gets `revoked_at` and `replaced_by_id` pointing at the new one — a chain.
- **Audit:** `identity.refresh`. **Reusing a revoked token** records `identity.refresh_token_reuse_detected` and revokes **every** token the user holds (`authorization_version += 1`).

### Change own password — My profile → Change password
- **Inserts:** `password_history` (`user_id, password_hash`) — the old hash, so the last five cannot be reused.
- **Updates:** `users.password_hash`; `authorization_version += 1` (every session ends, including the one that changed it — the desktop returns to the login screen on purpose).
- **Audit:** `identity.password_changed`.

### Administrator resets somebody's password — user dialog footer, platform-only
- **Inserts:** `password_history` (the old hash, so the reset cannot be undone by changing back).
- **Updates:** `users.password_hash`, `force_password_change = true`, `locked_until = null`, `failed_login_attempts = 0`, `authorization_version += 1`.
- **Audit:** `user.password_reset`, `entity_id` = the user. Refused for the caller's own account.

---

## 3. Users (plan sections 20, 24, 26a)

### Create a user — Users → New (plan 20.2a, 22.0, 25.7)
- **Store:** platform
- **Inserts:** `users` (`email, full_name, password_hash, is_active, force_password_change`, the profile columns). For a **firm** caller, one `user_firms` row for the caller's own firm is written by `create_user` itself, then replaced by whatever the form's **Firms** box held (see *Set memberships* — this is why an empty Firms box used to remove the membership just created). Roles: see *Set roles* or *Apply job template*, which the form calls next.
- **Audit:** `user.created`, then `user.firms_set`, then either `user.roles_set` or (`user_template.applied` + `user.roles_set`). **Three or four rows for one Save.**
- **Check:**
  ```sql
  select u.email, u.is_active, u.force_password_change, u.authorization_version,
         uf.firm_id, uf.is_primary, uf.is_active as member_active, uf.is_deleted
  from   platform.users u
  left join platform.user_firms uf on uf.user_id = u.id
  where  u.email = 'plan22.test@agency.local';
  ```
- **Password policy:** minimum 12 characters, upper, lower, digit, symbol. The refusal on screen does not say which rule (BACKLOG 31.16); the server's `details` does.

### Update a user — Users → Edit (plan 20.1)
- **Updates:** `users` columns edited; `version += 1`; `authorization_version += 1` (revokes tokens — an edited person is signed out).
- **Audit:** `user.updated` with `before_data` / `after_data` holding the changed columns.
- **Refused** for a firm caller when the person also belongs to a firm the caller cannot see (`_assert_exclusive_firm_user`) — the desktop opens the view instead and says so in the subtitle.

### Delete a user — Users → Delete (plan 26/section on restore)
- **Updates:** `users.is_deleted = true, deleted_at, deleted_by`; `authorization_version += 1`.
- **Left in place, deliberately:** `user_firms`, `user_roles`, `user_preferences`, `refresh_tokens` rows — so a restore is one flag. The email is unique only among live accounts, so a new user may take it; restore is then refused by name.
- **Audit:** `user.deleted`.

### Restore a user — platform-only, from the Deleted filter
- **Updates:** `users.is_deleted = false, deleted_at = null`.
- **Audit:** `user.restored`.

### Set memberships — `PUT /users/{id}/firms`; Users → Edit → Firms; Add existing user; User-Firm Assignments (plan 20.5–20.7, 24.8, 24.19)
- **Soft-deletes:** `user_firms` rows for firms **not** in the request — for a **platform** caller that is every firm not named (replace); for a **firm** caller only firms within their reach, memberships elsewhere are carried through untouched (merge).
- **Inserts / updates:** a `user_firms` row per firm named (`is_primary, is_active`). A **scoped** caller never moves `is_primary`; only a person with no primary at all gets one.
- **Updates:** `users.authorization_version += 1`.
- **Audit:** `user.firms_set`.
- **Refused by name** when a firm caller names a firm they cannot staff — nothing written.
- **Check** (both rows survive after a scoped save, 20.6):
  ```sql
  select firm_id, is_primary, is_active, is_deleted, deleted_at, version
  from   platform.user_firms
  where  user_id = '<id>'
  order  by created_at;
  ```

### Set roles, global tier — Users → Edit → Roles (platform caller) or a firm caller's own firm (plan 20a)
- **Soft-deletes:** the user's existing `user_roles` rows in that tier (`firm_id is null` for the global tier; `firm_id = <firm>` for a firm caller — the server scopes it).
- **Inserts:** one `user_roles` row per role.
- **Updates:** `users.authorization_version += 1`.
- **Audit:** `user.roles_set`.

### Set roles in one firm — Roles by firm (plan 20a.4, 24.10)
- Same shape as above with `user_roles.firm_id = <firm>`.
- **Audit:** `user.firm_roles_set`.
- **Refused** for a firm the user is not a member of ("Add the user to this firm before giving them a role in it") and for a firm outside the caller's reach.

### Apply a job template — Users → Apply job template; Users → New with a job named (plan 23.4a, 25.7)
- **Writes exactly what *Set roles* writes**, through the same call — soft-delete the tier's `user_roles`, insert one per role in the template, `authorization_version += 1`.
- **Audit:** **two rows** — `user_template.applied` (`after_data`: `template_id`, `template_code`, `role_ids`, `role_codes`) and `user.roles_set`.
- **Nothing on the user records which template they came from** — deliberately. A user edited afterwards is no longer described by it.
- **Check:**
  ```sql
  select ur.firm_id, r.code, ur.is_deleted, ur.created_at
  from   platform.user_roles ur
  join   platform.roles r on r.id = ur.role_id
  where  ur.user_id = '<id>'
  order  by ur.created_at;
  ```

### Clone a user — Users → Hire like this person (plan section 18)
- **Inserts:** a new `users` row built from scratch (`force_password_change = true` always); `user_firms` copied from the source; `user_roles` copied within the caller's reach — **for a platform caller naming no firm, every role the source holds in any tier lands in the clone's global tier** (§15.7, D-IDN-3).
- **Not copied, deliberately:** mobile, employee code, joining date, photo, password, `password_history`, `login_history`, the source's audit rows, and never the `platform_admins` row.
- **Audit:** `user.cloned` with `source_user_id`, plus the `user.created` / `user.roles_set` rows the build makes. **No `user.firms_set`** — the copied memberships have no audit row (corrected 2026-09-19, §15.7).

### Choose own primary firm — user menu → Primary firm (plan 26a.3)
- **Updates:** `user_firms.is_primary` — the old primary cleared **and flushed** before the new one is set, because `UQ_user_firms_active_primary` is checked per statement.
- **Audit:** `user.primary_firm_set`.

### Preferences — appearance, last screen, last firm (plan 26a, and the sign-in noise)
- **Store:** platform, `user_preferences` (one row per user, created on first read): `preferred_theme, preferred_theme_mode, preferred_high_contrast, preferred_palette, default_firm_id, default_landing_page, rows_per_page, …`
- **Audit:** `user_preferences.updated` — written **on every save, with no `before_data` or `after_data`**, including saves that change nothing. The desktop saves at sign-in and on every firm switch, so the platform trail gains a contentless row per sign-in. **Open question for the owner**: narrow it to real changes, stop auditing preferences, or leave it. `user_preferences.reset` when reset.

---

## 4. Roles and permissions (plan sections 20a, 25)

### Create a role — Roles & Permissions → Roles → New (plan 25.2)
- **Store:** platform, `roles` (`code, name, description, is_active, is_system = false, firm_id` = the caller's firm for a firm caller, `null` for a platform caller).
- **Audit:** `role.created`.
- **Refused:** a code spelling `platform_admin` or any of the sixteen seeded codes, case-insensitively — "'<code>' is reserved. Choose a different role code." `RoleCreate.code` is `^[a-z0-9._-]+$`, which *permits* that spelling, so the refusal is the service's.
- **Check:** `select code, name, firm_id, is_system, is_deleted from platform.roles where code = 'night-desk';`

### Set a role's permissions — the Permissions section of the same form (plan 25.3)
- **Soft-deletes / inserts:** `role_permissions` (`role_id, permission_id`) replaced.
- **Updates:** **every holder's** `users.authorization_version += 1` (`_revoke_role_users`) — they are all signed out on their next click. This is 25.9.
- **Audit:** `role.permissions_set`.
- **Refused:** any code in `PLATFORM_PERMISSION_CODES` named by a firm caller — and `list_permissions` never offers those 22 to a firm caller in the first place, so the picker shows 167 of 189.
- **Check:**
  ```sql
  select p.code, rp.is_deleted
  from   platform.role_permissions rp
  join   platform.permissions p on p.id = rp.permission_id
  join   platform.roles r on r.id = rp.role_id
  where  r.code = 'night-desk' order by p.code;
  ```

### Edit a role's name / description (plan 25.9 is permissions, not this)
- **Audit:** `role.updated`; also revokes every holder's tokens.

### Delete a role — while people hold it (plan 25.10)
- **Updates:** `roles.is_deleted = true`; every holder's `authorization_version += 1`.
- **Left in place:** the `user_roles` rows pointing at it — the person's row still names a deleted role, and the token simply no longer carries its codes. **No refusal, no count of holders** — the only guard is `is_system`.
- **Audit:** `role.deleted`.
- **Check** who was holding it before you delete (the plan's advice):
  ```sql
  select u.email, ur.firm_id
  from   platform.user_roles ur join platform.users u on u.id = ur.user_id
  join   platform.roles r on r.id = ur.role_id
  where  r.code = 'night-desk' and ur.is_deleted = false;
  ```

### Permissions themselves
Seeded by migration; `permission.created/updated/deleted` exist for the platform administrator only. A firm never writes this table.

---

## 5. User templates (plan sections 17, 19, 25.6)

- **Store:** platform — `/api/v1/user-templates` is a platform path. Tables `user_templates` (`code, name, description, firm_id, is_active, is_system`) and `user_template_roles` (`template_id, role_id`).
- **`firm_id is null` means offered to every firm**; the eleven seeded ones are `is_system = true`. A firm caller's create gets their own `firm_id`; a platform caller's **Offered to** chip sets it, blank leaves it null. `code` is unique **per scope** (two partial indexes, because NULLs are distinct).
- **Create:** inserts both tables; audit `user_template.created`. Roles are validated against the *owning* firm at creation, not only at apply.
- **Update:** `user_template.updated`; **Delete:** `user_templates.is_deleted = true`, `user_template.deleted`. A firm caller changing a template with `firm_id is null` is refused (422, "offered to every firm, so only a platform administrator…").
- **Check:**
  ```sql
  select t.code, t.firm_id, t.is_system, t.is_active, t.is_deleted, r.code as role
  from   platform.user_templates t
  left join platform.user_template_roles tr on tr.template_id = t.id and tr.is_deleted = false
  left join platform.roles r on r.id = tr.role_id
  where  t.code in ('food-night','every-night','night-desk-job');
  ```
- **Observation, checked against the database on 2026-09-15, not yet acted on:** `user_templates` / `user_template_roles` are absent from `_PLATFORM_TABLES` in `app/core/tenancy/lifecycle.py`, so **provisioning does not prune them** from a store it builds — `SNTEST01`, provisioned through the app in section 27, carries a `user_templates`; `wholesale_hub`, built by the seeder, does not. Nothing reads the copy. If you see the table in a firm schema, it is not the real one; `platform.user_templates` is. **Corrected 2026-09-19:** the copies are not empty — each of the 55 firm schemas that has one holds the 11 seeded templates (§15.0, D-IDN-10).

---

## 6. Firms and setting one up (plan sections 19, 27)

All routes under `/api/v1/firms` are platform-only. The registry rows are in `platform`; the setup actions write into **the new firm's own store**, and their audit rows go to **the platform trail**.

### Create a firm — Administration → Firms → New (plan 27.3–27.9)
- **Inserts:** `firms` (`code` upper-cased, `name, country, currency_code, financial_year_start, status, is_active, gst_number, pan_number`) and `firm_storage_mappings` (`deployment_mode, database_name, schema_name, connection_profile, provisioned_at = null`).
- **Audit:** `firm.created`.
- **Refused:** duplicate `code`/`gst_number`/`pan_number` among **live** firms (409); an unknown `connection_profile` (422, at creation, not at first use); two firms on one database/schema pair.
- **Nothing is built yet** for `SCHEMA`/`DATABASE` modes — the schema does not exist until provisioning.

### Update / delete a firm
- `firm.updated` — any change to `deployment_mode`/`schema_name`/`database_name`/`connection_profile` is refused: routing is fixed at creation. `firm.deleted` soft-deletes; the data stays where it is.

### Provision storage — Set up → Provision storage (plan 27.11–27.13)
- **Creates** the database (DATABASE mode) and schema, runs `alembic upgrade head` against it in this process, prunes the platform tables from it.
- **Updates:** `firm_storage_mappings.provisioned_at` (or `provisioning_error` with the reason, on failure).
- **Audit:** `firm.storage_provisioned` (platform). Re-running is safe and is the repair action.
- **Check:** `select code, provisioned_at, provisioning_error from platform.firm_storage_mappings m join platform.firms f on f.id = m.firm_id;`
  and, in DbVisualizer, that the new schema now lists ~180 tables.

### Open the books — Set up → Open the books (plan 27.23c–d)
- **Store:** the **firm's** store. **Inserts:** `ledger_accounts` (24, the default chart), `financial_years` (1 — the year *today* falls in, aligned to the firm's year start), `accounting_periods` (12), `journal_types`, `voucher_types`, `firm_control_accounts` (24, one per posting purpose).
- **Audit:** `firm.books_opened` on the **platform** trail, **only when something was created** — a second press answers `already_open: true` and writes no row.
- **Check** (WHOLE01's schema shown; use the new firm's). On a freshly opened firm expect `24, 1, 12, 24`. On WHOLE01 itself, checked 2026-09-15, it reads **25, 3, 36, 24** — one account was added by hand in section 13 and the demo history spans three financial years, so those are not the template's numbers and not a fault:
  ```sql
  select (select count(*) from wholesale_hub.ledger_accounts        where is_deleted = false) as accounts,
         (select count(*) from wholesale_hub.financial_years        where is_deleted = false) as years,
         (select count(*) from wholesale_hub.accounting_periods     where is_deleted = false) as periods,
         (select count(*) from wholesale_hub.firm_control_accounts  where is_deleted = false) as mapped;
  ```

### Apply the GST template — Set up → Apply GST template (plan 27.23f)
- **Store:** the firm's. **Inserts:** `tax_systems` (1), `tax_components` (4: CGST, SGST, IGST, CESS), `tax_profiles` (8), `tax_rules` (6, with their conditions and actions), and `geo_countries` (India) **if the store has no country** — a dedicated store has no geography at all.
- **Audit:** `firm.tax_template_applied` (platform), only when something was created; idempotent on "already has a tax system".

### Create the default branch and warehouse — Set up → Create head office and main warehouse (plan 27.23i)
- **Store:** the firm's. **Inserts:** `branches` (`code = 'HO'`, `is_default = true`) and `warehouses` (`code = 'MAIN'`, `branch_id` = HO). Idempotent per half: a firm that already named a branch gets only the warehouse, under its default branch.
- **Audit:** `firm.default_branch_created` (platform), only when something was created.

### Assign a business profile — Set up → Business profile, or Profile Assignment (plan 27.18–27.20, 27.23g)
- **Store:** the **named firm's** store (the platform endpoint opens it with `firm_store_session`). **Inserts / updates:** `firm_business_profiles` (`firm_id, business_profile_id, is_active, effective_from`).
- **Audit:** `firm_business_profile.created` the first time, `firm_business_profile.updated` after — in the **firm's own** trail, not the platform's, with `firm_id` set and `after_data` = `business_profile_id` only. Corrected on 2026-09-19 (this line used to say no row was written); §14.2 has the detail.
- **Check:** `select business_profile_id, is_active, effective_from from wholesale_hub.firm_business_profiles where is_deleted = false;`
- **Trap this closed:** until 2026-08 the write went into the **caller's** store while reporting success; MEDI01 and FOOD01 hid it by sharing `firm_shared`.

### Readiness — Set up panel, `GET /firms/{id}/readiness`
- **Writes nothing.** Reads the counts above from the firm's store and answers seven steps; `scripts/check_firm_readiness.py` prints the same seven from the same implementation.

---

## 7. Reading the audit trail (plan section 23)

- **`GET /api/v1/audit-logs` with no `X-Firm-ID`** → `platform.audit_logs`, platform authority required.
- **With `X-Firm-ID`** → that firm's `audit_logs` **merged with** `platform.audit_logs where firm_id = <firm>`, exact merge: `page * page_size` from each store, sliced in one time order. Both stores get the same filters. A store is never merged with itself.
- **Filters are exact match** on `action` and `entity_type` (BACKLOG 31.17).
- **Query the merge by hand** (WHOLE01):
  ```sql
  select created_at, action, entity_type, entity_id, actor_id, 'firm' as store
  from   wholesale_hub.audit_logs where firm_id = '30c66274-60e9-4789-97d9-138a7a1fdc61'
  union all
  select created_at, action, entity_type, entity_id, actor_id, 'platform'
  from   platform.audit_logs      where firm_id = '30c66274-60e9-4789-97d9-138a7a1fdc61'
  order  by created_at desc limit 40;
  ```
  The `store` column is what 23.4b is checking: the two should interleave by time, not sit in two blocks.

---

## 8. Things that are *not* written, and are often looked for

| You might expect | What actually happens |
| --- | --- |
| A row saying which template a user came from | Nothing on `users`; only the `user_template.applied` audit row records it |
| Physical deletion anywhere | Never for a document, a master or a person; `is_deleted = true`. **The exception is a document's child rows** — attachments, notes, delivery schedules, dropped lines, and every child of a draft invoice or return — which are deleted and re-inserted on save, on the buying side (§9.14) and the selling side (§11.21) alike — and a customer's `OPENING_BALANCE` receivable row when the opening balance is revised (§12.11) |
| A firm's user rows in the firm's store | `users`, `user_firms`, `user_roles` are **platform-only**; the firm store has none |
| An audit row for a read | Reads write nothing, including readiness and the audit screen itself |
| A refused write leaving a partial row | A refusal is raised before commit; nothing lands — with one known exception, 20.2b before #402, where the user was created and the roles call then failed |
| A `user_preferences.updated` row meaning something changed | It fires on every save, with nothing on either side — see §3 |

---

## 9. Buying — order to payment (TC-BUY-001 to 008)

Read on 2026-09-18 off `purchase_service.py`, `goods_receipt_service.py`,
`purchase_invoice_service.py`, `purchase_return_service.py` and
`settlement_service.py`, and off what they call — `InventoryService`,
`DocumentPostingService`, `JournalEntryEngine`, `DocumentFrameworkService`.
Then checked, read-only, against the rows the TC-BUY fixtures left in TEST01
on 2026-09-16 (four orders, one approval withdrawn, seven receipts of which one
was cancelled, two supplier invoices, one return, one payment) and against
WHOLE01's history. A claim marked *(not seen in a live row)* was read off the
code only.

### 9.0 Before you look

- **Store:** every buying table is firm-owned. The fixtures buy in **TEST01**, so every query below reads `test_fixtures`. For WHOLE01 put `wholesale_hub`; for MEDI01 or FOOD01 put `firm_shared` and filter on `firm_id`.
- **Find your rows by the fixture's codes, never by counting.** The vendor is `<SUFFIX>-V` and the product `<SUFFIX>-B`, the suffix in capitals as the fixture prints it (`T0916XK2Q-V`). TEST01 keeps every earlier run's orders beside yours.
- **All buying audit rows go to the firm's own trail**, `test_fixtures.audit_logs`. None reaches `platform.audit_logs`.
- **Every document write also touches numbering and the timeline**, so the blocks below do not repeat it:
  - issuing a number (on create only) moves `document_number_sequences.next_sequence` and the rule's `document_numbering_rules.next_sequence` / `last_scope_signature`. Order and receipt numbers carry firm and branch — `PO-TEST01-HO-2026-2027-000001`, `GRN-TEST01-HO-2026-2027-000001`; invoice, return and payment numbers do not — `PI-2026-2027-…`, `PR-2026-2027-…`, `PY-2026-2027-…`;
  - one `document_lifecycle_events` row per create, edit and transition (`action` `CREATED`, `EDITED`, `SUBMITTED`, `APPROVED`, `COMPLETED`, `CANCELLED`, `CLOSED`; `source_module_code` `PURCHASE`, `GOODS_RECEIPT`, `PURCHASE_INVOICE`, `PURCHASE_RETURN`). **Payments write none;**
  - the first document of its kind in a firm also inserts `document_type_definitions`, `document_state_definitions` and `document_numbering_rules`, with audits `document_type.created`, `document_state.created`, `document_numbering_rule.created`. TEST01 already has all five buying types.
- **Two audit rows ride along with most steps.** Every stock movement writes `inventory.transaction.created`; every journal writes `finance.journal_entry.created` and `finance.journal_entry.posted`, and reversing one adds `finance.journal_entry.reversed` on the original. So completing a receipt that moves its order's status is five audit rows, not one.
- **One click, all its audit rows.** Every row carries its request id in `_meta`, and every row of one request has the **same `created_at`** — order within a click by `action`, not by time:
  ```sql
  select action, entity_type, entity_id, after_data
  from   test_fixtures.audit_logs
  where  after_data->'_meta'->>'request_id' = (
           select after_data->'_meta'->>'request_id'
           from   test_fixtures.audit_logs
           where  action = 'grn.cancelled'      -- the action you just took
           order  by created_at desc limit 1)
  order  by action;
  ```
- **What points at what.** Two links have no foreign key, and one is cleared by a cancellation:

  | From | Column | To |
  | --- | --- | --- |
  | `goods_receipts` | `purchase_order_id` (`purchase_order_number` copied) | `purchase_orders` |
  | `goods_receipt_lines` | `purchase_order_line_id` | `purchase_order_lines` |
  | `goods_receipt_lines`, `purchase_return_lines` | `inventory_transaction_id` | `inventory_transactions` — **set to null when the document is cancelled**; find the movement by `reference_number` afterwards |
  | `stock_ledger_entries` | `transaction_id` | `inventory_transactions`, one each |
  | `inventory_transactions` | `reference_number` = the document number; `reversal_of_transaction_id` on a reversal | — |
  | `journal_entries` | `source_module` + `source_id` = the document; `reference_number` = its number, `-REV` for the reversal; `reversal_of_id` on the reversal | — |
  | `purchase_invoice_lines`, `purchase_return_lines` | `source_document_id`, `source_document_line_id` | the receipt and its line — **no foreign key** |
  | `settlements` | `journal_entry_id` (never null), `reversal_journal_entry_id` | `journal_entries` |
  | `settlement_allocations` | `settlement_id`, `purchase_invoice_id` | `settlements`, `purchase_invoices` |

- **Do not count audit rows against documents in the seeded firms.** A reseed clears the documents and cannot clear an append-only trail: WHOLE01 holds 35 purchase orders and 2,720 `purchase.created` rows.

### 9.1 Raise a purchase order — Purchases → Purchase Orders → New (TC-BUY-001 step 1)

- **Store:** the firm's.
- **Inserts:** `purchase_orders` (`status` DRAFT, `po_number`, `subtotal` = after line discounts and before tax, `tax_total`, `grand_total`); `purchase_order_lines`, one per line (`line_number`, `ordered_quantity`, `unit_price`, `gross_amount`, `discount_amount`, `tax_amount`, `net_amount`, `base_quantity`, `conversion_factor` — and a line `status` that is always `ORDERED` and never follows the order); `purchase_delivery_schedules`, `purchase_attachments`, `purchase_notes` if the form carried any; `purchase_order_history` (`purchase.created`, → DRAFT); lifecycle `CREATED`.
- **Audit:** `purchase.created` (`after_data`: `po_number`, `status`).
- **Nothing else.** No stock, no journal, nothing on the vendor. The fixture's order reads 1000.00 + 180.00 = 1180.00.
- **Check** (the order and its lines):
  ```sql
  select o.po_number, o.status, o.grand_total, o.version,
         l.line_number, p.code as product, l.ordered_quantity, l.unit_price,
         l.tax_amount, l.net_amount, l.remarks
  from   test_fixtures.purchase_orders o
  join   test_fixtures.vendors v             on v.id = o.vendor_id
  join   test_fixtures.purchase_order_lines l on l.purchase_order_id = o.id
  join   test_fixtures.products p            on p.id = l.product_id
  where  v.code = '<SUFFIX>-V'
  order  by o.po_number, l.line_number;
  ```

### 9.2 Submit, then approve (TC-BUY-001 steps 2–3)

- **Updates:** `purchase_orders.status` DRAFT → SUBMITTED → APPROVED, `version` +1 each.
- **Inserts:** `purchase_order_history` `purchase.submitted`, then `purchase.approved`; lifecycle `SUBMITTED`, `APPROVED`.
- **Audit:** `purchase.submitted`, `purchase.approved`, each with the status before and after.
- **Not written, on purpose:** approving posts no journal, reserves nothing and moves no stock. It is a promise to buy.
- **Refused, nothing written:** approving a draft ("Only submitted purchase orders can be approved. Submit the order first."); submitting an order with no lines, or one that is not DRAFT. Submitting or approving an order already there returns it unchanged and writes nothing.
- **Create accepts a status — the approval can be skipped there.** `PurchaseOrderCreate` inherits a `status` field and `create_order` stores it, so a `POST /api/v1/purchases` carrying `"status": "APPROVED"` is born approved with no submit or approve row. The desktop never sends one, but the seeder does: `firm_shared` holds 64 `purchase.created` history rows with `to_status` APPROVED and no `purchase.submitted` at all. Listed as a defect in the PR, not fixed here.
- **Check** (history, used for §9.3 too):
  ```sql
  select o.po_number, h.created_at, h.action, h.from_status, h.to_status, h.details_json
  from   test_fixtures.purchase_order_history h
  join   test_fixtures.purchase_orders o on o.id = h.purchase_order_id
  join   test_fixtures.vendors v         on v.id = o.vendor_id
  where  v.code = '<SUFFIX>-V'
  order  by h.created_at, h.action;
  ```

### 9.3 Edit an approved order — the approval is withdrawn (TC-BUY-002)

- **Updates:** `purchase_orders` — every header column from the form, totals recomputed, `status` APPROVED → **DRAFT**. `purchase_order_lines` updated **in place by `line_number`**, so the line ids survive; a new line number is inserted and a dropped one is **physically deleted**.
- **Deleted physically and re-inserted, every save:** `purchase_delivery_schedules`, `purchase_attachments`, `purchase_notes`.
- **Inserts:** **two** `purchase_order_history` rows — `purchase.updated` (APPROVED → APPROVED) and `purchase.approval_withdrawn` (APPROVED → DRAFT, `details_json` "The order was edited after approval."); lifecycle `EDITED` (APPROVED → DRAFT).
- **Audit: `purchase.updated` only** (`before_data` status APPROVED; `after_data` status DRAFT and `grand_total`). **`purchase.approval_withdrawn` is a history row, not an audit row.** The view's **History** tab reads `purchase_order_history`, which is where TC-BUY-002 sees it; querying `audit_logs` for it finds nothing. Checked: TEST01's PO-TEST01-HO-2026-2027-000002 has the withdrawal in history and only `purchase.updated` in the trail.
- **The two history rows share one `created_at`** (one transaction), so time cannot order them; the §9.2 query lists the withdrawal first, and so does WHOLE01's own order. Read them as a pair.
- Submit and Approve again are §9.2.
- **Refused:** editing an order that is PARTIALLY_RECEIVED, RECEIVED, CANCELLED or CLOSED. Editing a DRAFT or SUBMITTED order leaves its status where it was.

### 9.4 Raise a goods receipt, as a draft (TC-BUY-003 step 1, Save Receipt)

- **Inserts:** `goods_receipts` (`status` DRAFT, `grn_number`, `purchase_order_id`, `purchase_order_number`, and vendor, branch and warehouse copied from the order; `total_*_quantity` totals); `goods_receipt_lines` (`purchase_order_line_id`, `ordered_quantity`, `previously_received_quantity` = what **completed** receipts already took, `current_receipt_quantity`, `accepted_quantity` = current − rejected − damaged, `unit_price` — the order's price when the form sends 0 or nothing, `tax_amount`, `net_amount`, `inventory_transaction_id` **null**); attachments and notes; lifecycle `CREATED`.
- **Audit:** `grn.created`.
- **Not written:** no stock, no journal; the order's status does not move.
- **Refused:** an order that is not APPROVED, PARTIALLY_RECEIVED or RECEIVED ("…goods can only be received against an approved order."); more than is left on the order line.
- **Editing a draft receipt:** `grn.updated`, lines matched on line number, attachments and notes deleted and re-inserted.

### 9.5 Complete a receipt — part, then the rest (TC-BUY-003)

The first step that moves anything.

- **Inserts, per line:**
  - `inventory_transactions` — `transaction_type` `GOODS_RECEIPT`, `reference_type` `GOODS_RECEIPT`, `reference_number` the GRN number, `quantity` and `current_quantity_delta` = accepted + free, `previous_current_quantity` → `new_current_quantity`;
  - `stock_ledger_entries` — the same figures plus `unit_cost` (the line's value before tax ÷ everything received, so free goods lower it), `total_cost`, `average_cost_after`;
  - `inventories` — the product × warehouse (× batch) row, **inserted the first time** the product lands there, otherwise updated: `current_quantity`, `available_quantity`, `version`;
  - `product_valuations` — inserted on first use, then `quantity_on_hand`, `total_value`, `average_cost` roll forward;
  - `batches` — only when the line names a batch number the register does not know (audit `CREATE`, entity `batch`). The fixture's product is not batch-tracked.
- **Inserts, once:** `journal_entries` (`source_module` `goods_receipt`, `source_id` the receipt, `reference_number` the GRN number, `journal_date` the receipt date, POSTED) with two `journal_lines` — **Dr 1200 Inventory / Cr 2300 Goods Received Not Invoiced**, at cost and without tax (400.00 for the fixture's 4, 600.00 for its 6); two `gl_postings`; `ledger_balances` inserted or moved for each account in that period, and each later period's row for the account carried forward. A receipt that brought in no value posts no journal.
- **Updates:** `goods_receipt_lines.inventory_transaction_id` (and `batch_id`); `goods_receipts.status` COMPLETED, `completed_at`; `purchase_orders.status` → PARTIALLY_RECEIVED or RECEIVED — **derived from the sum of completed receipts** each time, never counted up.
- **Audit:** `inventory.transaction.created` (per line), `finance.journal_entry.created`, `finance.journal_entry.posted`, `purchase.received_status_changed` (only when the order's status moved), `grn.completed`. Confirmed as one request on TEST01's GRN-TEST01-HO-2026-2027-000001.
- **Not written:** **no `purchase_order_history` row** when receiving moves the order — `purchase.received_status_changed` in the trail is the only record, so the order's History tab never shows PARTIALLY_RECEIVED or RECEIVED arriving. No payable: nobody is owed anything yet. `purchase_order_lines` hold no received quantity; "already received" is summed from the receipts every time it is shown.
- **Refused, and the whole completion rolls back:** a cancelled or closed receipt; over-receipt; a batch-required product with no batch; no open accounting period for the receipt date; a control account not mapped.
- **Check** — the receipts, the movements behind them, what is on the shelf, and the journals:
  ```sql
  select g.grn_number, g.status, g.completed_at, gl.current_receipt_quantity,
         gl.accepted_quantity, gl.unit_price, gl.inventory_transaction_id
  from   test_fixtures.goods_receipts g
  join   test_fixtures.goods_receipt_lines gl on gl.goods_receipt_id = g.id
  join   test_fixtures.vendors v              on v.id = g.vendor_id
  where  v.code = '<SUFFIX>-V'
  order  by g.grn_number;

  select t.created_at, t.reference_number, t.transaction_type, t.current_quantity_delta,
         t.new_current_quantity, t.reversal_of_transaction_id is not null as is_reversal,
         s.unit_cost, s.total_cost, s.average_cost_after
  from   test_fixtures.inventory_transactions t
  join   test_fixtures.stock_ledger_entries s on s.transaction_id = t.id
  join   test_fixtures.products p             on p.id = t.product_id
  where  p.code = '<SUFFIX>-B'
  order  by t.created_at;

  select w.code as warehouse, i.current_quantity, i.available_quantity,
         pv.average_cost, pv.total_value
  from   test_fixtures.inventories i
  join   test_fixtures.products p   on p.id = i.product_id
  join   test_fixtures.warehouses w on w.id = i.warehouse_id
  left join test_fixtures.product_valuations pv on pv.product_id = p.id and pv.is_deleted = false
  where  p.code = '<SUFFIX>-B';

  select je.reference_number, je.status, je.journal_date,
         je.reversal_of_id is not null as is_reversal,
         la.code, la.name, jl.debit_amount, jl.credit_amount
  from   test_fixtures.journal_entries je
  join   test_fixtures.journal_lines jl   on jl.journal_entry_id = je.id
  join   test_fixtures.ledger_accounts la on la.id = jl.ledger_account_id
  where  je.source_id in (select g.id
                          from   test_fixtures.goods_receipts g
                          join   test_fixtures.vendors v on v.id = g.vendor_id
                          where  v.code = '<SUFFIX>-V')
  order  by je.created_at, jl.line_number;
  ```
  After the receipt of 4: one movement +4, MAIN holds 4, the order PARTIALLY_RECEIVED, one journal of 400.00. After the 6: MAIN 10, RECEIVED, a second journal of 600.00.

### 9.6 Cancel a completed receipt (TC-BUY-004)

Refused first if it has been invoiced — §9.7.

- **Inserts:**
  - per line, `inventory_transactions` `GOODS_RECEIPT_REVERSAL` (`reference_number` the GRN, `quantity` −4, `reversal_of_transaction_id` = the original movement, `remarks` = the reason) and its `stock_ledger_entries` row, valued at **today's moving average**, not at the receipt's price;
  - `journal_entries` `<GRN number>-REV`, with `reversal_of_id` = the original and the same `source_module` and `source_id`: **Dr 2300 Goods Received Not Invoiced** with everything the receipt accrued / **Cr 1200 Inventory** with what the movement took out, any gap between them to **5400 Purchase Price Variance**. Lines, postings and balances as §9.5.
- **Updates:** the original journal POSTED → **REVERSED**; `inventories` and `product_valuations` back down; `goods_receipt_lines.inventory_transaction_id` → **null**; `goods_receipts.status` CANCELLED and `cancel_reason` (`completed_at` is left as it was); `purchase_orders.status` re-derived — RECEIVED → PARTIALLY_RECEIVED, or back to APPROVED when this was the only receipt.
- **Audit — six rows for one click** (confirmed on TEST01's GRN-TEST01-HO-2026-2027-000003): `inventory.transaction.created`, `finance.journal_entry.created`, `finance.journal_entry.posted`, `finance.journal_entry.reversed` (on the original; `after_data.reversal_entry_id`), `purchase.received_status_changed`, `grn.cancelled` (`after_data`: `reason`, `reversed_inventory_lines`).
- **The reversal is dated the first day of the original's accounting period, not today.** GRN-TEST01-HO-2026-2027-000003 was received on 2026-09-16 and its `-REV` is dated 2026-09-01; WHOLE01's two cancelled receipts and three reversed receipts (settlements) are the same. Journal Entries lists newest date first, so the reversal sits among the start of the month rather than at the top — search for it by reference. Listed in the PR as a finding.
- **Cancelling a draft receipt** writes only the status, lifecycle `CANCELLED` and `grn.cancelled`. It posted nothing, so nothing is reversed.
- **Check:** the §9.5 queries again. Expect the `GOODS_RECEIPT_REVERSAL` −4, MAIN at 6, the order PARTIALLY_RECEIVED, the original journal REVERSED and a `-REV` journal Dr 2300 400.00 / Cr 1200 400.00 (no variance line while the product has only ever been bought at 100).

### 9.7 A receipt that has been invoiced cannot be cancelled (TC-BUY-005)

- **The test the server makes:** a `purchase_invoice_lines` row whose `source_document_id` is the receipt, on an invoice that is neither deleted nor CANCELLED. A DRAFT invoice holds the receipt as firmly as an approved one.
- **Writes nothing** — the refusal comes before any row is touched, so there is no audit row either. `goods_receipts.version` does not move.
- **Check** — which live invoices hold the vendor's receipts:
  ```sql
  select pi.invoice_number, pi.status, g.grn_number, g.status as receipt_status
  from   test_fixtures.purchase_invoice_lines pil
  join   test_fixtures.purchase_invoices pi on pi.id = pil.purchase_invoice_id
  join   test_fixtures.goods_receipts g     on g.id = pil.source_document_id
  join   test_fixtures.vendors v            on v.id = g.vendor_id
  where  v.code = '<SUFFIX>-V'
    and  pil.is_deleted = false and pi.is_deleted = false;
  ```

### 9.8 Enter a supplier invoice (the `po-invoiced` fixture does this; no screen can — BACKLOG §31.9)

- **Inserts:** `purchase_invoices` (`status` DRAFT, `invoice_number`, `supplier_invoice_number`, `subtotal`, `tax_total`, `grand_total`); `purchase_invoice_sources`, one per source document; `purchase_invoice_lines` (`source_document_type` GOODS_RECEIPT, `source_document_id`, `source_document_line_id`, `received_quantity` = the receipt line's **accepted** quantity, `already_invoiced_quantity`, `current_invoice_quantity`, `unit_price`, `tax_amount`, `net_amount`); **`purchase_invoice_accounting_events` — three placeholder rows** (`PURCHASE_EXPENSE` debit, `INPUT_TAX` debit, `ACCOUNTS_PAYABLE` credit, narration "Placeholder accounting event for …"); attachments and notes; lifecycle `CREATED`.
- **The accounting events are not the ledger.** Nothing reads them into a journal; the journal is written at approval (§9.9).
- **Audit:** `purchase_invoice.created`.
- **Editing a draft invoice physically deletes every child row** — lines, sources, accounting events, attachments, notes — and inserts them again, with new line ids. Audit `purchase_invoice.updated`.
- **Refused:** more than the receipt line has left to bill (unless the invoice allows over-invoicing); a supplier invoice number the vendor has already used; sources from different vendors or branches.
- **Not checked by the server:** that the receipt was completed. A draft or cancelled receipt can be billed through the API — the desktop's picker is the only filter. Listed in the PR.

### 9.9 Approve a supplier invoice — the payable appears (`po-invoiced`; what TC-BUY-005 and 008 start from)

- **Inserts:** `journal_entries` (`source_module` `purchase_invoice`, reference the PI number, `journal_date` the invoice date) with **Dr 2300 Goods Received Not Invoiced** (what the receipts actually accrued: the `stock_ledger_entries.total_cost` behind the billed receipt lines) **+ Dr 1300 Input Tax / Cr 2100 Trade Payables** (the grand total), any gap between accrued and billed to **5400 Purchase Price Variance**. The fixture's reads 600.00 + 108.00 / 708.00. Lines, postings, balances as §9.5.
- **Updates:** `purchase_invoices.status` APPROVED, `approved_at`.
- **Audit:** `finance.journal_entry.created`, `finance.journal_entry.posted`, `purchase_invoice.approved` (no data beyond the request id).
- **Not written:** nothing on the vendor, the receipt or the order; no stock. What the bill still owes is never stored — §9.11.
- **Cancelling an approved invoice changes its status and nothing else** (`purchase_invoice.cancelled`): the approval's journal stays posted, and the receipt becomes cancellable again. *(Not seen in a live row.)* Listed in the PR.

### 9.10 Return goods to the supplier (TC-BUY-006)

Three steps; only Complete moves anything.

- **Create** — inserts `purchase_returns` (DRAFT, `return_number`), `purchase_return_sources`, `purchase_return_lines` (`received_quantity` = the receipt line's accepted quantity, `already_returned_quantity`, `current_return_quantity`, `rejected_quantity`, `is_damaged`, `is_scrap`, `is_expired`, `item_condition`, `unit_price`, `tax_amount`, `net_amount`), three placeholder `purchase_return_accounting_events` (`PURCHASE_RETURN`, `INPUT_TAX_REVERSAL`, `VENDOR_RECEIVABLE` — not the ledger), lifecycle `CREATED`. Audit `purchase_return.created`.
- **Approve** — `status` APPROVED, `approved_at`; lifecycle `APPROVED`; audit `purchase_return.approved`. Nothing else.
- **Complete:**
  - per line, `inventory_transactions` with `transaction_type` **`RETURN`**, `reference_type` `PURCHASE_RETURN`, `reference_number` the PR number, `quantity` 2, `current_quantity_delta` −2; its `stock_ledger_entries` row at the moving average; `inventories` and `product_valuations` down; `purchase_return_lines.inventory_transaction_id` set;
  - `journal_entries` (`source_module` `purchase_return`, reference the PR number): **Dr 2100 Trade Payables** (the return's grand total) / **Cr 1200 Inventory** (what the movement took out) / **Cr 1300 Input Tax** (the return's tax), any gap to 5400 Purchase Price Variance;
  - `purchase_returns.status` COMPLETED (the table has no completed-at column);
  - audit `inventory.transaction.created`, `finance.journal_entry.created`, `finance.journal_entry.posted`, `purchase_return.completed`.
- **The Damaged chip only sets `purchase_return_lines.is_damaged`.** The movement's damaged, blocked and quarantine deltas are always zero; the split survives only as text in `inventory_transactions.remarks` (`purchase_return buckets sellable=… damaged=…`), and `damaged=` there is the line's `rejected_quantity`, not the chip. The damaged-goods report reads the flag.
- **What passes for the case:** 2 back at 100 with 18% → the return's `grand_total` **236.00**; journal Dr 2100 236.00 / Cr 1200 200.00 / Cr 1300 36.00; MAIN at 8.
- **Check the price on the return line.** The server takes a missing `unit_price` as **0** rather than the receipt's price. The desktop sends the receipt line's price, but anything that omits it records a return worth nothing — payables debited 0.00 and the whole stock value charged to 5400. TEST01's PR-2026-2027-000001, raised on 2026-09-16 while the cases were being written, is one (grand total 0.00, journal Dr 5400 200.00 / Cr 1200 200.00 with a 0.00 Trade Payables line); so are the six returns the history seeder raised in WHOLE01 (the seventh, PR-2026-2027-000003, was raised by hand and reads 236.00) and all twelve in `firm_shared`, because the seeder sends no price. Listed in the PR.
- **Not written:** the bill's outstanding does not fall. The return debits Trade Payables in the ledger, but Record Payment still offers the invoice's full amount (§9.11). The receipt and the order are untouched.
- **Cancelling a completed return** posts `RETURN_REVERSAL` movements and a `<PR number>-REV` journal with `reversal_of_id`, marks the original REVERSED and writes `purchase_return.cancelled`. *(Not seen in a live row.)*
- **Check:**
  ```sql
  select r.return_number, r.status, r.grand_total, rl.source_document_number,
         rl.current_return_quantity, rl.rejected_quantity, rl.is_damaged,
         rl.unit_price, rl.tax_amount, rl.net_amount,
         t.transaction_type, t.current_quantity_delta, t.remarks
  from   test_fixtures.purchase_returns r
  join   test_fixtures.purchase_return_lines rl on rl.purchase_return_id = r.id
  join   test_fixtures.vendors v                on v.id = r.vendor_id
  left join test_fixtures.inventory_transactions t on t.id = rl.inventory_transaction_id
  where  v.code = '<SUFFIX>-V';
  ```
  and the journal with the §9.11 query, which covers invoices, returns and payments.

### 9.11 Pay the supplier — Finance → Payments → Record Payment (TC-BUY-008)

- **Inserts, in this order:** `journal_entries` (`source_module` `settlements`, `source_id` = the settlement's id, reference the `PY-…` number): **Dr 2100 Trade Payables / Cr 1010 Bank** (`1000 Cash` for method CASH), lines, postings, balances. Then `settlements` (`direction` PAYMENT, `vendor_id`, `customer_id` null, `settlement_number`, `amount`, `allocated_amount`, `unallocated_amount`, `method`, `ledger_account_id` = the bank or cash account, `status` POSTED, `journal_entry_id`), and one `settlement_allocations` row per bill (`purchase_invoice_id`, `amount`).
- **Audit:** `finance.journal_entry.created`, `finance.journal_entry.posted`, `settlement.payment.recorded` (`after_data`: `settlement_number`, `amount`, `allocated_amount`, `party` = the vendor's code).
- **Not written:** no lifecycle event; nothing on the invoice — `purchase_invoices.status` stays APPROVED, there is no PAID; nothing on the vendor. `vendor_ledgers` exists and nothing writes it.
- **What a bill still owes is derived every time:** its grand total to two decimals, less the allocations of **POSTED** settlements. At zero it drops out of Record Payment.
- **A payment with no allocation is accepted** — an advance, held in `unallocated_amount`. **It can never be applied to a bill afterwards:** the allocate endpoint is for receipts only ("Only a receipt can be applied to an invoice.").
- **Refused:** allocating more than a bill owes, to another vendor's bill or to a draft or cancelled one, or more in total than was paid; BANK or CASH not mapped to an account; no open period.
- **Check** — the payment and its allocations, what each bill still owes, and every journal the vendor's invoices, returns and payments raised:
  ```sql
  select s.settlement_number, s.status, s.amount, s.allocated_amount, s.unallocated_amount,
         s.method, la.code as paid_from, pi.invoice_number, a.amount as allocated
  from   test_fixtures.settlements s
  join   test_fixtures.vendors v         on v.id = s.vendor_id
  join   test_fixtures.ledger_accounts la on la.id = s.ledger_account_id
  left join test_fixtures.settlement_allocations a
         on a.settlement_id = s.id and a.is_deleted = false
  left join test_fixtures.purchase_invoices pi on pi.id = a.purchase_invoice_id
  where  s.direction = 'PAYMENT' and v.code = '<SUFFIX>-V';

  select pi.invoice_number, pi.status, round(pi.grand_total, 2) as total,
         coalesce(sum(a.amount) filter (where s.status = 'POSTED'), 0) as paid,
         round(pi.grand_total, 2)
           - coalesce(sum(a.amount) filter (where s.status = 'POSTED'), 0) as still_owed
  from   test_fixtures.purchase_invoices pi
  join   test_fixtures.vendors v on v.id = pi.vendor_id
  left join test_fixtures.settlement_allocations a
         on a.purchase_invoice_id = pi.id and a.is_deleted = false
  left join test_fixtures.settlements s on s.id = a.settlement_id
  where  v.code = '<SUFFIX>-V' and pi.is_deleted = false
  group  by pi.id, pi.invoice_number, pi.status, pi.grand_total;

  select je.reference_number, je.source_module, je.status, je.journal_date,
         la.code, la.name, jl.debit_amount, jl.credit_amount
  from   test_fixtures.journal_entries je
  join   test_fixtures.journal_lines jl   on jl.journal_entry_id = je.id
  join   test_fixtures.ledger_accounts la on la.id = jl.ledger_account_id
  where  je.source_id in (
           select id from test_fixtures.purchase_invoices where vendor_id = (select id from test_fixtures.vendors where code = '<SUFFIX>-V')
           union all
           select id from test_fixtures.purchase_returns  where vendor_id = (select id from test_fixtures.vendors where code = '<SUFFIX>-V')
           union all
           select id from test_fixtures.settlements       where vendor_id = (select id from test_fixtures.vendors where code = '<SUFFIX>-V'))
  order  by je.created_at, jl.line_number;
  ```
  For the case: PY paid 708.00 from 1010, allocated 708.00 to the bill, still owed 0.00; journal Dr 2100 708.00 / Cr 1010 708.00.

### 9.12 Reverse a payment — Finance → Payments → Reverse (not in the cases)

- **Inserts:** `journal_entries` `<PY number>-REV`, `reversal_of_id` = the payment's journal, the mirror (Dr 1010 Bank / Cr 2100 Trade Payables), dated the first day of the original's period as in §9.6.
- **Updates:** the original journal → REVERSED; `settlements.status` → REVERSED, with `reversal_journal_entry_id`, `reversed_at`, `reversed_by`, `reversal_reason`.
- **Left in place, deliberately:** the `settlement_allocations` rows, not even soft-deleted. They stop counting because the settlement is no longer POSTED, and the bill comes back to Record Payment.
- **Audit:** `finance.journal_entry.created`, `finance.journal_entry.posted`, `finance.journal_entry.reversed`, `settlement.payment.reversed`.
- **Refused:** a second reversal ("… has already been reversed.").
- Seen live on WHOLE01's three reversed **receipts**, which take the same path (allocations kept, `-REV` dated 2026-09-01). No reversed **payment** exists in any store today. *(The payment itself not seen in a live row.)*

### 9.13 The purchasing reports (TC-BUY-007) — read only

Each is computed from the tables every time it opens, and **writes nothing**, not even an audit row. None reads a receipt: "not yet received" follows the order's status.

| Report | Route | Reads | Empty for the fixture's order because |
| --- | --- | --- | --- |
| Purchase order register | `/api/v1/purchases/reports/register` | `purchase_orders`, every status, cancelled included, not deleted; `vendors.display_name` | — |
| Orders not yet received | `/api/v1/purchases/reports/pending` | `purchase_orders` that are APPROVED or PARTIALLY_RECEIVED | — |
| Overdue purchase orders | `/api/v1/purchases/reports/overdue` | the same, with `expected_delivery_date` before today (UTC) | the fixture sets no expected date, so it is never overdue |
| Orders by supplier | `/api/v1/purchases/reports/by-vendor` | `purchase_orders` not CANCELLED, `grand_total` summed per vendor; `vendors.display_name` | — |
| Orders by buyer | `/api/v1/purchases/reports/by-buyer` | `purchase_orders` not CANCELLED that name a `buyer_id`; names from **`platform.users`** | the fixture names no buyer |
| Purchases by product | `/api/v1/purchases/reports/by-product` | `purchase_order_lines` of orders not CANCELLED (`ordered_quantity`, `net_amount` with tax); `products` | — |
| Damaged goods returned (TC-BUY-006) | `/api/v1/purchase-returns/reports/damaged` | `purchase_return_lines` with `is_damaged`, on returns not CANCELLED — drafts included; `products` | — |

### 9.14 What buying does not write, and is often looked for

| You might expect | What actually happens |
| --- | --- |
| A balance on the vendor | None. `vendors` has no balance column and `vendor_ledgers` is never written. Payables are 2100 Trade Payables for all suppliers together, and per bill the allocations of §9.11 |
| A PAID status on a supplier invoice | It stays APPROVED; what it owes is derived |
| Received or invoiced quantities on the order line | Not stored; summed from completed receipts and live invoices each time |
| `purchase_invoice_accounting_events` or `purchase_return_accounting_events` being the journal | Placeholders written at create; the journal is `journal_entries` with `source_module` `purchase_invoice` or `purchase_return` |
| An audit row for `purchase.approval_withdrawn` | A history row only (§9.3) |
| A history row when receiving moves the order | An audit row only, `purchase.received_status_changed` (§9.5) |
| A reversal dated today | The first day of the original's period (§9.6) |
| A purchase return lowering what Record Payment offers | It does not (§9.10) |
| A journal for approving an order, or for a draft receipt, invoice or return | None; see each block |
| Soft-deleted child rows | Attachments, notes and delivery schedules on every save, dropped order and receipt lines, and every child of a draft invoice or return are **physically** deleted and re-inserted |

### 9.15 Checked against live rows, and not

- **Confirmed on TEST01**, the rows of the 2026-09-16 fixture runs: the DRAFT → SUBMITTED → APPROVED history and the withdrawn approval; PARTIALLY_RECEIVED, RECEIVED, and RECEIVED → PARTIALLY_RECEIVED after a cancel; the number formats; the five audit rows of a completion and the six of a cancellation, grouped by request id; `GOODS_RECEIPT`, `GOODS_RECEIPT_REVERSAL` and `RETURN` movements with their costs and `reversal_of_transaction_id`; the journals for receipt, reversal, invoice, return and payment on accounts 1200, 2300, 1300, 2100, 1010 and 5400; the `-REV` entry with `reversal_of_id` set and the original REVERSED; the cleared `inventory_transaction_id`; the placeholder accounting events; the allocation of 708.00 leaving 0.00 owed; lifecycle events for every document but the payment; `audit_logs` never versioned.
- **Confirmed on WHOLE01:** two cancelled receipts with `-REV` journals dated 2026-09-01; two withdrawn approvals ordered as in §9.3; three reversed receipts keeping their allocations; zero-priced seeded returns.
- **Not seen in a live row:** a cancelled supplier invoice; a cancelled purchase return; a reversed payment; a receipt carrying a new batch number; a draft invoice being edited; a price variance on a receipt cancellation (every TEST01 purchase was at 100, so the average never moved).
- **Where the buying rows are, 2026-09-18:** TEST01 4 orders, 7 receipts, 2 invoices, 1 return, 1 payment; WHOLE01 35, 35, 30, 7, 1; `firm_shared` (MEDI01 and FOOD01) 64, 60, 60, 12, none; ELEC01 32, 30, 30, 6, none. **TEST02 and LEARN01 hold none.**

---

## 10. Stock on its own (TC-STOCK-001 to 008)

Read on 2026-09-18 off `inventory_service.py`, `physical_count_service.py`,
`batch_serial_service.py`, the stock side of `delivery_note_service.py` and
`sales_order_service.py`, and `DocumentPostingService`. Then checked, read-only,
against TEST01's rows (the `stock-ready` run of 2026-09-16, `T0916NF7T`),
WHOLE01's history, and the per-run stores two `pharma-firm` runs and one
`electronics-firm` run left behind — one pharmacy run from before the D-8-1 fix
and one from after it, which is what let the batch claims be seen both ways.
§10.12 says which claims a live row confirmed and which it could not.

### 10.0 Before you look

- **Store:** every stock table is firm-owned. TC-STOCK-001 to 004 run in
  **TEST01**, so their queries read `test_fixtures`. TC-STOCK-005 to 007 run in
  the run's own **Pharmacy** firm, `<SUFFIX>-P`, whose schema is
  **`fx_<suffix>_p`** with the suffix in lower case (`fx_t0916f8m2_p`); TC-STOCK-008
  in the Electronics firm `<SUFFIX>-E`, schema `fx_<suffix>_e`. The fixture's
  **Tables** line prints the name. For WHOLE01 put `wholesale_hub`.
- **Find your rows by the fixture's codes.** `<SUFFIX>-P` is the product and
  `<SUFFIX>-W2` the second warehouse; `<SUFFIX>-TRF`, `-WO`, `-QH`, `-QR` are
  the references the case types, stored **upper-cased**; `<SUFFIX>-AMX` has
  batches `<SUFFIX>-B1`, `-B2`, `-B3`; `<SUFFIX>-SHT` is the short product;
  `<SUFFIX>-MIX-0001` to `-0005` are the serials.
- **Three tables per movement, one per balance.** `inventories` is the balance
  — **one row per product × branch × warehouse × storage locator, and per
  batch where the product is batch-tracked** (`batch_id` is part of the key;
  untracked stock sits on the row whose `batch_id` is null). `inventory_transactions`
  is one immutable row per movement, carrying every bucket's `previous_*` and
  `new_*`. `stock_ledger_entries` is one row per transaction (unique on
  `transaction_id`) with the same figures plus `unit_cost`, `total_cost` and
  `average_cost_after`. The Stock Ledger screen reads the third, the
  Transactions tab the second, the Inventory tab the first.
- **The balance is maintained, not summed.** Each movement rewrites the
  `inventories` row (`current_quantity`, `reserved_quantity`,
  `available_quantity` = current − reserved − blocked, `blocked_quantity`,
  `damaged_quantity`, `quarantine_quantity`, `in_transit_quantity`,
  `display_quantity` = current, `last_transaction_at` = the movement's
  `transaction_date`, `version` +1) and writes the before-and-after onto the
  movement. So the ledger's `new_current_quantity` on the latest row must equal
  the row's `current_quantity`, and the sum of `current_quantity_delta` over the
  row's movements must equal it too — the reconciliation in §10.1.
- **Valuation is one row per firm × product**, `product_valuations`
  (`quantity_on_hand`, `average_cost`, `total_value`, `costing_method`
  `WEIGHTED_AVERAGE`), inserted on first use. Stock arriving with a cost moves
  the average toward it; stock leaving is valued at the average. The ledger
  row's `unit_cost` and `total_cost` are what the movement was worth, and
  **every journal below reads `total_cost` off that ledger row** rather than
  computing it again. A movement that changes ownership of nothing — a hold, a
  release, a reservation — writes `unit_cost` and `total_cost` **null** and
  leaves the valuation alone.
- **The vocabulary is thirteen types plus a suffix.** `transaction_type` is a
  string; `InventoryTransactionType` (`app/inventory/schemas/inventory.py`)
  names what the service writes and `reverse_transaction` appends `_REVERSAL`
  to whatever it reverses:

  | `transaction_type` | `reference_type` | `reference_number` | Written by |
  | --- | --- | --- | --- |
  | `OPENING_STOCK` | `OPENING_STOCK` | the batch's reference | posting an opening-stock batch |
  | `GOODS_RECEIPT` | `GOODS_RECEIPT` | the GRN | §9.5 |
  | `RETURN` | `PURCHASE_RETURN` | the PR | §9.10 |
  | `SALES_RETURN` | `SALES_RETURN` | the SR | §11.16 |
  | `RESERVE` / `UNRESERVE` | `SALES_ORDER` | the **order** number | approving / cancelling an order; dispatching a note (§10.6) |
  | `DISPATCH` | `DELIVERY_NOTE` | the DN | dispatching a note (§10.6) |
  | `TRANSFER_OUT` / `TRANSFER_IN` | `TRANSFER` | typed | §10.2 |
  | `WRITE_OFF` | **the reason** — `DAMAGE`, `EXPIRY` or `LOSS` | typed | §10.3 |
  | `QUARANTINE_HOLD` / `QUARANTINE_RELEASE` | `QUARANTINE` | typed | §10.4 |
  | `ADJUSTMENT` | `PHYSICAL_COUNT` from a count; typed (default `ADJUSTMENT`) from `POST /inventory/adjustments` | the count number, or typed | §10.5 |
  | `<TYPE>_REVERSAL` | the original's | the original's | §10.10 |

  The Stock Ledger's type dropdown offers exactly these, by name, plus the
  three `_REVERSAL` twins that are ever written (`GOODS_RECEIPT_REVERSAL`,
  `RETURN_REVERSAL`, `SALES_RETURN_REVERSAL`);
  `test_stock_ledger_types_match_the_server.py` fails when the two drift.
  Before BL-31.13 it was typed by hand and offered eight types nothing
  writes.
- **The reference on a transfer, write-off or hold is typed, not issued**
  (BACKLOG §34). Nothing checks it is unique among movements; a write-off's
  reference also becomes its journal's `reference_number`, which *is* unique,
  so a repeated write-off reference is refused by the journal. Counts are the
  exception: `PC-2026-2027-000001` comes from the `PHYSICAL_COUNT` numbering
  rule, with no firm or branch in it.
- **Every movement writes `inventory.transaction.created`** (`after_data`:
  `inventory_id`, `transaction_type`, `reference_number`, `new_current_quantity`,
  `new_available_quantity`), and every journal `finance.journal_entry.created`
  and `.posted`, all in the firm's own trail. The §9.0 request-id query works
  here unchanged — put `inventory.stock_written_off` or
  `inventory.stock_transferred` as the action.
- **Who may:** `INVENTORY_ADJUST` for transfers, write-offs, quarantine,
  adjustments and counts; `OPENING_STOCK_CREATE` to post opening stock;
  `INVENTORY_VIEW`, `INVENTORY_LEDGER_VIEW`, `INVENTORY_TRANSACTION_VIEW` to
  read the three tables.
- **What points at what:**

  | From | Column | To |
  | --- | --- | --- |
  | `stock_ledger_entries` | `transaction_id` | `inventory_transactions`, one each |
  | `inventory_transactions` | `inventory_id`; `batch_id`; `reversal_of_transaction_id` | `inventories`; `batches`; the movement reversed |
  | `journal_entries` | `source_module` `inventory` + `source_id` = the **movement** (write-off, adjustment) or the **opening-stock batch**; `delivery_note` + the note (dispatch cost) | — |
  | `physical_count_lines` | `transaction_id` (no FK); `batch_id` (no FK); `storage_node_id` (no FK, null = ROOT) | the `ADJUSTMENT` it posted; `batches`; `warehouse_storage_nodes` |
  | `opening_stock_lines` | `transaction_id`, `batch_id` | the `OPENING_STOCK` movement; the batch it registered |
  | `delivery_note_lines` | `inventory_transaction_id`, `released_reservation_transaction_id`, `batch_id` | the first `DISPATCH` and `UNRESERVE` of the line, and the first batch drawn |
  | `serial_numbers` | `inventory_id`, `batch_id` (both optional, both null in the fixture) | `inventories`, `batches` — **and nothing points back**: no movement ever carries `serial_id` or `lot_id` |

### 10.1 The summary and the ledger — reads (TC-STOCK-001)

- **Inventory tab** — `GET /api/v1/inventory`: `inventories` rows joined to
  `products`, `branches`, `warehouses`, one row per location (and per batch).
  Current, Available, Reserved are the row's columns.
- **Stock Summary** — `GET /api/v1/inventory/summary`: the **whole firm's**
  `inventories` summed — row count, each bucket, and how many rows are at or
  below their reorder level, at zero, or negative. `/summary/by-firm`,
  `/by-branch`, `/by-warehouse` roll the same rows up; `/summary/by-product`
  exists on the API and no screen calls it.
- **Stock Ledger** — `GET /api/v1/inventory/ledger`: `stock_ledger_entries`,
  newest first with `id` as the tiebreaker (two rows of one dispatch share a
  timestamp). The balance after each row is `new_current_quantity`. The
  **Transactions** tab is `inventory_transactions`, the same figures without
  the cost. Both accept `transaction_type` as an **exact string** — the enum
  types nothing on the read side, so `RESERVATION` is accepted and matches
  nothing. The desktop no longer offers such a type (BL-31.13), and drops one
  remembered from before.
- **Writes nothing.** No audit row for any of these, nor for the exports.
- **Check** — the balance, the chain that produced it, and that the two agree:
  ```sql
  select w.code as warehouse, i.current_quantity, i.reserved_quantity,
         i.available_quantity, i.quarantine_quantity, i.last_transaction_at,
         i.version, pv.quantity_on_hand, pv.average_cost, pv.total_value
  from   test_fixtures.inventories i
  join   test_fixtures.products p   on p.id = i.product_id
  join   test_fixtures.warehouses w on w.id = i.warehouse_id
  left join test_fixtures.product_valuations pv
         on pv.product_id = p.id and pv.is_deleted = false
  where  p.code = '<SUFFIX>-B';

  select s.created_at, s.transaction_type, s.reference_type, s.reference_number,
         s.quantity, s.current_quantity_delta, s.previous_current_quantity,
         s.new_current_quantity, s.unit_cost, s.total_cost, s.average_cost_after
  from   test_fixtures.stock_ledger_entries s
  join   test_fixtures.products p on p.id = s.product_id
  where  p.code = '<SUFFIX>-B'
  order  by s.created_at, s.id;

  select i.current_quantity,
         (select sum(t.current_quantity_delta)
          from   test_fixtures.inventory_transactions t
          where  t.inventory_id = i.id)                     as summed_deltas,
         (select t.new_current_quantity
          from   test_fixtures.inventory_transactions t
          where  t.inventory_id = i.id
          order  by t.created_at desc, t.id desc limit 1)    as last_balance
  from   test_fixtures.inventories i
  join   test_fixtures.products p on p.id = i.product_id
  where  p.code = '<SUFFIX>-B';
  ```
  For the case: two `GOODS_RECEIPT` rows +4 and +6 naming their GRNs,
  `new_current_quantity` 4 then 10, `unit_cost` 100; the three figures in the
  last query all read 10.

### 10.2 Transfer between warehouses — Inventory → Transfer (TC-STOCK-002)

- **Inserts:** **two** `inventory_transactions`, in this order: `TRANSFER_OUT`
  on the source row (`quantity` 3, `current_quantity_delta` −3) and
  `TRANSFER_IN` on the destination (`current_quantity_delta` +3), both with the
  typed `reference_number` upper-cased, `reference_type` `TRANSFER`, the same
  `transaction_date` and remarks; two `stock_ledger_entries`, **both at the
  held average** (`unit_cost` 60, `total_cost` 180, `average_cost_after` 60 —
  the inbound leg is given the average explicitly so the move cannot revalue
  the product); the `inventories` row for `<SUFFIX>-W2` **inserted** the first
  time anything lands there (`current_quantity` 3, `display_uom_id` from the
  product); MAIN 50 → 47; `product_valuations` moved down by 180 and back up
  by 180, net nothing. The destination's `branch_id` is read off the
  destination warehouse, so a transfer may cross branches.
- **Audit — three rows, one request** (confirmed on TEST01):
  `inventory.transaction.created` ×2 and `inventory.stock_transferred`
  (`entity_id` = the **outbound** movement; `after_data`: `reference_number`,
  `quantity`, `from_warehouse_id`, `to_branch_id`, `to_warehouse_id`).
- **Not written, on purpose:** **no journal** — both legs read `has_journal`
  false in TEST01 and in WHOLE01's `TRF-0001`/`TRF-0002`. There is one
  inventory control account, so the entry would debit and credit 1200 for the
  same amount. No lifecycle event, no document number.
- **Refused, nothing written:** more than the source's `current − reserved`
  ("The source holds 47.0000 available, so 999 cannot be transferred out of
  it." — the desktop checks first and shows the same sentence; the server would
  say the same), the same warehouse and node ("A transfer must move stock
  somewhere else than where it is."), a destination outside the firm.
- **Check:**
  ```sql
  select t.created_at, t.transaction_type, w.code as warehouse, t.quantity,
         t.current_quantity_delta, t.previous_current_quantity, t.new_current_quantity,
         s.unit_cost, s.total_cost, s.average_cost_after,
         exists (select 1 from test_fixtures.journal_entries je
                 where  je.source_id = t.id) as has_journal
  from   test_fixtures.inventory_transactions t
  join   test_fixtures.stock_ledger_entries s on s.transaction_id = t.id
  join   test_fixtures.warehouses w           on w.id = t.warehouse_id
  where  t.reference_number = '<SUFFIX>-TRF'
  order  by t.created_at;
  ```
  Expect two rows, MAIN −3 → 47 and `<SUFFIX>-W2` +3 → 3, both costed 60 /
  180, `has_journal` false on both.

### 10.3 Write off — Inventory → Write off (TC-STOCK-003 step 1)

- **Inserts:** `inventory_transactions` `WRITE_OFF` with `reference_type` =
  **the reason** (`DAMAGE`), `quantity` 1, `current_quantity_delta` −1,
  `owned_quantity_delta` −1, `remarks` "Stock written off as damage" (or
  "Damage: <your remarks>" when you typed any); its `stock_ledger_entries` row
  at the average (`unit_cost` 60, `total_cost` 60); `journal_entries`
  (`source_module` `inventory`, `source_id` = **the movement's id**,
  `reference_number` = the typed reference, `description` "Stock adjustment
  <REF>", `journal_date` = the transaction date, POSTED) with **Dr 5500
  Inventory Adjustment / Cr 1200 Inventory** 60.00, both lines' `description`
  = the narration; `gl_postings`; `ledger_balances`. MAIN 47 → 46;
  `product_valuations` down 1 and 60.
- **Quarantined stock is condemned first:** the amount is taken from
  `quarantine_quantity` before `current_quantity`, and the limit is the two
  together. A write-off worth nothing (average cost 0) writes the movement and
  **no journal**.
- **Audit — four rows, one request** (confirmed): `inventory.transaction.created`,
  `finance.journal_entry.created`, `finance.journal_entry.posted`,
  `inventory.stock_written_off` (`after_data`: `reference_number`, `reason`,
  `quantity`).
- **Refused, nothing written:** more than `current + quarantine` ("This
  location holds 46.0000, so 999 cannot be written off from it."); a reference
  a journal already carries; no open period for the date; 1200 or 5500 not
  mapped in `firm_control_accounts`.
- **Check** — the movement and its journal, by reference:
  ```sql
  select t.transaction_type, t.reference_type, t.quantity, t.current_quantity_delta,
         t.quarantine_quantity_delta, t.owned_quantity_delta, t.remarks,
         s.unit_cost, s.total_cost,
         je.reference_number as journal, je.status, je.journal_date,
         la.code, la.name, jl.debit_amount, jl.credit_amount
  from   test_fixtures.inventory_transactions t
  join   test_fixtures.stock_ledger_entries s   on s.transaction_id = t.id
  left join test_fixtures.journal_entries je    on je.source_id = t.id
  left join test_fixtures.journal_lines jl      on jl.journal_entry_id = je.id
  left join test_fixtures.ledger_accounts la    on la.id = jl.ledger_account_id
  where  t.reference_number = '<SUFFIX>-WO'
  order  by jl.line_number;
  ```

### 10.4 Quarantine — hold back and release (TC-STOCK-003 steps 2–3)

- **Inserts:** `inventory_transactions` `QUARANTINE_HOLD` (`reference_type`
  `QUARANTINE`, `quantity` 2, `current_quantity_delta` **−2**,
  `quarantine_quantity_delta` **+2**) and its ledger row with `unit_cost` and
  `total_cost` **null** and `average_cost_after` unchanged — the movement is
  staged with `revalues=False`, so `product_valuations` is not touched. A
  release is the mirror: `QUARANTINE_RELEASE`, +2 current, −2 quarantine.
- **Which way the row moves — the question TC-STOCK-003 asks you to record:**
  holding 2 of 46 read `current_quantity` 46 → **44**, `available_quantity` 46
  → **44**, `quarantine_quantity` 0 → **2** (TEST01, confirmed). Current and
  Available both fall and Quarantine rises; what is physically on the premises
  is `current + quarantine`. The plan's expectation that Current stays put is
  not what the code does.
- **Audit — one row only:** `inventory.transaction.created`. There is no
  `inventory.stock_quarantined`; the hold and the release are told apart by
  `after_data.transaction_type`. Listed in the PR (D-STK-6).
- **Not written:** no journal (confirmed `has_journal` false on TEST01's
  `<SUFFIX>-QH` and WHOLE01's `4444`); nothing on `batches.status` — a
  quarantined *batch* is a separate, hand-set status on the batch row, which
  the Expiry Monitor counts and this movement does not set.
- **Refused, nothing written:** a hold beyond `current − reserved` ("There is
  44.0000 to hold, so 999 cannot be."); a release beyond `quarantine_quantity`
  ("There is 2.0000 to release, so 999 cannot be.").
- **Check** — both movements, and the row's buckets before and after each:
  ```sql
  select t.created_at, t.transaction_type, t.quantity,
         t.current_quantity_delta, t.quarantine_quantity_delta,
         t.previous_current_quantity, t.new_current_quantity,
         t.previous_available_quantity, t.new_available_quantity,
         t.previous_quarantine_quantity, t.new_quarantine_quantity,
         s.unit_cost, s.total_cost, s.average_cost_after
  from   test_fixtures.inventory_transactions t
  join   test_fixtures.stock_ledger_entries s on s.transaction_id = t.id
  where  t.reference_number in ('<SUFFIX>-QH', '<SUFFIX>-QR')
  order  by t.created_at;
  ```

### 10.5 Physical count — open, save progress, post (TC-STOCK-004)

A count is a document: `physical_counts` and `physical_count_lines`, numbered
from the document framework, with no lifecycle events (0 rows in every store).

- **Open Count** — `POST /api/v1/inventory/counts`. **Inserts** `physical_counts`
  (`count_number` `PC-2026-2027-000001`, `status` DRAFT, `branch_id`,
  `warehouse_id`, `count_date`, `remarks`) and **one `physical_count_lines`
  row per `inventories` row in the warehouse** — every product ever stocked
  there, other runs' too, rows at zero included, and one line per batch row
  (`batch_id`) **and per storage location** (`storage_node_id`, null for the
  warehouse's unlocated ROOT row — D-STK-13, fixed), in the order the rows
  were created; `expected_quantity` = what **that row** held **at that
  moment**, `counted_quantity` null. Lines named in the request may give a
  `storage_node_id` (absent = ROOT); one that is not a live node of the
  warehouse, or the same product, batch and location twice, is refused before
  a number is reserved. The **first
  count in a firm** also inserts the `PHYSICAL_COUNT` document type, its three
  states and its numbering rule (audits `document_type.created`,
  `document_state.created` ×3, `document_numbering_rule.created` — seen in the
  same request on TEST01). **Audit:** `inventory.physical_count.opened`
  (`after_data`: `count_number`, `line_count`).
- **Save progress** — `PUT /counts/{id}`. **Updates** `physical_count_lines.counted_quantity`
  and `remarks` on the lines named (matched on product, batch and storage
  location; unnamed lines are left alone, and a named line the sheet does not
  hold is refused rather than dropped), `version` +1 on each; `physical_counts.remarks`, `version`.
  **No audit row** (D-STK-6). Refused once the sheet is not DRAFT ("PC-… is
  posted, so it cannot be changed.").
- **Post count** — `POST /counts/{id}/post`. For each line whose
  `counted_quantity` is **not null**: `variance_quantity` = counted − **what the
  line's row holds now** — product, batch and storage location, never the
  warehouse summed (re-read, not `expected_quantity`, so a dispatch made
  while you counted is not undone); when the variance is not zero, one
  `ADJUSTMENT` movement (`reference_number` = **the count number**,
  `reference_type` `PHYSICAL_COUNT`, `quantity` 1, `current_quantity_delta` −1,
  `transaction_date` = the count date, `remarks` "Physical count PC-…: counted
  49.0000 against 50.0000" — the decimals as stored) on the counted row — its
  batch when the line names one (D-STK-1, fixed), and its storage location
  (`inventory_transactions.storage_node_id`; D-STK-13, fixed — a bin's
  shortage used to come off ROOT) — and its ledger row at the
  average (60 / 60); the line's `transaction_id` set. **Then one journal for
  the whole sheet** (D-STK-11, fixed; the owner chose one voucher per
  stock-take): `source_module` `physical_count`, `source_id` = the sheet,
  `reference_number` = the count number, `description` "Physical count PC-…",
  with **a pair of lines per difference** — a shortage **Dr 5500 Inventory
  Adjustment / Cr 1200 Inventory** at its value, a surplus the other way round,
  each line described with that difference's remarks. No journal when no
  difference moved any value. Then `physical_counts.status` POSTED,
  `posted_at`, `posted_by`. **Lines nobody counted are skipped**:
  `variance_quantity` stays null and nothing moves. The whole sheet is one
  transaction: a line that fails leaves nothing written and the sheet DRAFT
  (D-STK-3, fixed). **Audit:** per adjusted line
  `inventory.transaction.created`; then `finance.journal_entry.created` and
  `finance.journal_entry.posted` once; then `inventory.physical_count.posted`
  (`before_data` status DRAFT; `after_data` status POSTED, `adjusted_lines`).
- **Cancel** — status CANCELLED, audit `inventory.physical_count.cancelled`.
  Only a DRAFT can be posted or cancelled; a posted sheet cannot be reopened.
- **One thing to know before you rely on it:** a sheet with **nothing
  counted posts** with `adjusted_lines` 0 — WHOLE01's `PC-2026-2027-000005` is
  one (D-STK-5, open). D-STK-1 (the wrong row), D-STK-3 (a commit per line),
  D-STK-11 (a second difference refused on the journal reference) and
  D-STK-13 (a bin counted against the whole warehouse and corrected on ROOT)
  are fixed.
- **Not seen in a live row:** an adjusted line. WHOLE01's only posted sheet
  counted nothing and TEST01's is a draft; the block above is read off the
  code and off the plain adjustment path, which the two `CLEANUP-…`
  adjustments in TEST01 confirm (Dr 5500 / Cr 1200 at the average, `source_id`
  = the movement).
- **Check** — the sheet, its lines, and the movement and journal behind the
  counted one:
  ```sql
  select c.count_number, c.status, c.count_date, c.posted_at, c.version,
         l.line_number, p.code, l.batch_id is not null as batched,
         l.expected_quantity, l.counted_quantity, l.variance_quantity,
         t.transaction_type, t.reference_type, t.current_quantity_delta, t.remarks,
         je.reference_number as journal, la.code, jl.debit_amount, jl.credit_amount
  from   test_fixtures.physical_counts c
  join   test_fixtures.physical_count_lines l on l.physical_count_id = c.id
  join   test_fixtures.products p             on p.id = l.product_id
  left join test_fixtures.inventory_transactions t on t.id = l.transaction_id
  left join test_fixtures.journal_entries je       on je.source_id = c.id
  left join test_fixtures.journal_lines jl         on jl.journal_entry_id = je.id
  left join test_fixtures.ledger_accounts la       on la.id = jl.ledger_account_id
  where  c.count_number = 'PC-2026-2027-<your number>'
  order  by l.line_number, jl.line_number;
  ```
  Expect one line with `counted_quantity` 49, `variance_quantity` −1, an
  `ADJUSTMENT` of −1 referenced `PHYSICAL_COUNT`, Dr 5500 60.00 / Cr 1200
  60.00; every other line null throughout; MAIN at 49.

### 10.6 Dispatch — the stock side (TC-STOCK-005)

The delivery note itself is Selling; this is what it does to stock. Everything
below is in the pharmacy firm's schema, `fx_<suffix>_p`.

- **What the fixture leaves.** `pharma-firm` posts an opening-stock batch of
  four lines (§10.0's `OPENING_STOCK`): each batched line first **registers
  its batch** through `resolve_for_receipt` — `batches` row with
  `batch_number`, `product_id`, `warehouse_id`, `branch_id`, `expiry_date`,
  `status` AVAILABLE, `vendor_id` null; audit action **`CREATE`**, entity
  `batch`, no `after_data` — then lands the 10 in **that batch's own
  `inventories` row** (three rows for `<SUFFIX>-AMX`, one untracked row for
  `<SUFFIX>-SHT`), ledger rows at `unit_cost` 60, one journal for the batch
  (`source_module` `inventory`, `source_id` = the `opening_stock_batches` row,
  reference `<SUFFIX>-OS`): **Dr 1200 Inventory / Cr 3000 Opening Balance
  Equity** 1,980.00 (33 × 60); audits `opening_stock.created`,
  `opening_stock.posted`. `batches.status` **stays AVAILABLE when the date
  passes** — expiry is a fact about `expiry_date`, and nothing ever writes
  `EXPIRED`. Approving the order for 5 writes a `RESERVE` (§10.0) chosen
  earliest-expiry-first **among batches not expired on the order's date** —
  the same candidates dispatch draws from — so the hold sits on `<SUFFIX>-B2`.
  Before the D-STK-2 fix it sat on `<SUFFIX>-B1`, the expired one (both
  pharmacy stores of 2026-09-16). What no in-date batch covers is held on the
  untracked row as a back order, and when expired stock stands behind it that
  `RESERVE`'s remarks name it: "sales_order reserve line 1: 10 of this
  product's stock is past its expiry date (<SUFFIX>-B1 expired 2026-08-17)
  and cannot be reserved: write it off or quarantine it."
- **Batches screen:** a batch holds **no quantity**; Qty and Available are
  sums over the `inventories` rows carrying its id.
- **Dispatch inserts**, per note line: an **`UNRESERVE`** where the order
  held it (`reference_number` = the **order** number, dated the delivery date,
  remarks "delivery_note release line 1", `reserved_quantity_delta` −5,
  `batch_id` = B2 — B1 on a store built before D-STK-2 — no cost); then the allocation — batches in expiry order,
  **skipping any expired on the note's date** — and one **`DISPATCH`** per
  batch drawn (`reference_number` = the DN number, `reference_type`
  `DELIVERY_NOTE`, `current_quantity_delta` −5, `batch_id` = **B2**,
  `unit_cost` 60, `total_cost` 300); B2's `inventories` row 10 → 5;
  `product_valuations` for AMX 30 → 25, 1,800.00 → 1,500.00;
  `delivery_note_lines.inventory_transaction_id` and `.batch_id` (the first
  batch drawn) and `.released_reservation_transaction_id`; one journal for the
  note (`source_module` `delivery_note`, `source_id` = the note, reference the
  DN number with no suffix): **Dr 5200 Cost of Goods Sold / Cr 1200 Inventory**
  300.00 — the sum of the movements' `total_cost`, never the selling price.
  Then `delivery_notes.status` DISPATCHED, `dispatched_at`; lifecycle
  `DISPATCHED`; audits `delivery_note.dispatched` and, when the order's status
  moves, `sales_order.delivered_status_changed`.
- **Seen both ways.** The pharmacy store built at 02:31 on 2026-09-16, before
  the D-8-1 fix, dispatched from `B1`; the one built at 21:42, after it,
  dispatched from `B2` while its reservation still sat on `B1`.
- **Refused, and the whole dispatch rolls back:** not enough in-date stock —
  "Insufficient available stock to dispatch: short by 5. 10 of this product's
  stock is past its expiry date (<SUFFIX>-B1 expired 2026-08-17) and cannot be
  dispatched: write it off or quarantine it." Nothing is written, no audit row.
- **Expiry Monitor** — `GET /batch-serial/batches/expiry-dashboard` counts
  **`batches` rows**, not stock: expired = `expiry_date <= today` or status
  `EXPIRED`, never `DESTROYED`; "in 7 days" / "in 30 days" = `expiry_date`
  after today and within the window; Quarantine and Recalled by `status`. A
  batch with nothing left still counts, and **Expired Today and Total Expired
  are the same condition** (D-STK-8). The All Batches grid is `GET /batches`.
- **Check** (pharmacy schema):
  ```sql
  select b.batch_number, b.expiry_date, b.status,
         coalesce(sum(i.current_quantity), 0)   as on_hand,
         coalesce(sum(i.available_quantity), 0) as available,
         coalesce(sum(i.reserved_quantity), 0)  as reserved
  from   fx_<suffix>_p.batches b
  left join fx_<suffix>_p.inventories i on i.batch_id = b.id
  where  b.batch_number like '<SUFFIX>-B%'
  group  by b.batch_number, b.expiry_date, b.status
  order  by b.batch_number;

  select t.created_at, t.transaction_type, t.reference_number, t.transaction_date,
         b.batch_number, t.quantity, t.current_quantity_delta,
         t.reserved_quantity_delta, t.new_current_quantity, t.new_available_quantity,
         s.unit_cost, s.total_cost, t.remarks
  from   fx_<suffix>_p.inventory_transactions t
  join   fx_<suffix>_p.stock_ledger_entries s on s.transaction_id = t.id
  join   fx_<suffix>_p.products p             on p.id = t.product_id
  left join fx_<suffix>_p.batches b           on b.id = t.batch_id
  where  p.code = '<SUFFIX>-AMX'
  order  by t.created_at;

  select je.reference_number, je.source_module, je.status, je.journal_date,
         la.code, la.name, jl.debit_amount, jl.credit_amount
  from   fx_<suffix>_p.journal_entries je
  join   fx_<suffix>_p.journal_lines jl   on jl.journal_entry_id = je.id
  join   fx_<suffix>_p.ledger_accounts la on la.id = jl.ledger_account_id
  where  je.source_module in ('delivery_note', 'inventory')
  order  by je.created_at, jl.line_number;
  ```
  After the case: B1 10 / 10 / 0, **B2 5 / 5 / 0**, B3 10 / 10 / 0; three
  `OPENING_STOCK`, a `RESERVE` on B2, an `UNRESERVE` on B2, a `DISPATCH` on B2;
  the DN journal Dr 5200 300.00 / Cr 1200 300.00 beside the opening one.

### 10.7 A delivery short of stock (TC-STOCK-006)

- **What the fixture leaves:** `<SUFFIX>-SHT` on one untracked row with
  `current_quantity` 3, and an approved order for 10 — which wrote **two**
  `RESERVE` rows on that same row, 3 (what the row could cover) and 7 (the
  remainder, "no batch behind it"), so the row reads `reserved_quantity` 10
  and **`available_quantity` −7** (confirmed live). A reservation may drive
  available negative; that is the back order.
- **Save and Approve the note write no stock rows** — the note's own tables
  and lifecycle only. The "Short by 7 — there is not enough available stock to
  cover this line." line in the editor is computed on the client from the
  inventory rows it read.
- **Dispatch writes nothing.** The gate sums `available_quantity` across the
  product's rows in that bay (−7) against the line's 10 and raises
  "Insufficient available stock for dispatch line." **before** any movement is
  staged; the request rolls back whole — no `UNRESERVE`, no `DISPATCH`, no
  journal, no audit row, `delivery_notes.status` still APPROVED and its
  `version` unmoved.
- *(Not seen in a live row: neither pharmacy store holds a refused dispatch —
  the SHT note had not been raised in either. Read off the code, and the
  reservation rows above are live.)*
- **Check** (pharmacy schema) — the row, its reservations, and the absence of
  a `DISPATCH`:
  ```sql
  select i.current_quantity, i.reserved_quantity, i.available_quantity, i.version
  from   fx_<suffix>_p.inventories i
  join   fx_<suffix>_p.products p on p.id = i.product_id
  where  p.code = '<SUFFIX>-SHT';

  select t.transaction_type, t.reference_number, t.quantity,
         t.reserved_quantity_delta, t.new_reserved_quantity, t.new_available_quantity
  from   fx_<suffix>_p.inventory_transactions t
  join   fx_<suffix>_p.products p on p.id = t.product_id
  where  p.code = '<SUFFIX>-SHT'
  order  by t.created_at;
  ```

### 10.8 A remembered filter from another firm (TC-STOCK-007)

- **Not a table row.** The Inventory tab's filters are this **machine's**:
  `workspace_state.inventory_management` inside
  `%APPDATA%\.agency_platform\desktop_preferences.json` (keys `status`,
  `transaction_type`, `branch_id`, `warehouse_id`, `product_id`,
  `include_deleted`, `low_stock_only`, `out_of_stock_only`, `negative_only`,
  `default_post_after_save`, `default_export_format`). The server never sees
  it: `platform.user_preferences` carries none of these columns, and
  `_applyServerPreferences` cannot overwrite it at sign-in because it lives
  outside the server document.
- **What the case *does* write:** the firm switch saves the server
  preferences, so the platform trail gains a `user_preferences.updated` row
  with no before or after (§3), and `user_preferences.default_firm_id` moves.
  That is the only row.
- **The drop** happens in memory when the tab's lookups load: an id not among
  this firm's branches, warehouses or products is cleared, and the file is
  rewritten on the next Apply. Open the JSON file to see the stale id before
  and its absence after.

### 10.9 Serial numbers (TC-STOCK-008)

- **What the fixture leaves** (schema `fx_<suffix>_e`): 5 on one untracked
  `inventories` row from an opening-stock batch (`track_serial` is on the
  product; nothing in stock posting reads it), then five `POST
  /api/v1/batch-serial/serials`: one `serial_numbers` row each —
  `serial_number`, `product_id`, `warehouse_id`, `branch_id`, `status`
  `AVAILABLE`, `warranty_start` today, `warranty_end` a year on; `inventory_id`,
  `batch_id`, `manufactured_date`, `current_owner`, `asset_reference` null (the
  request may name the first two; the fixture does not). Audit action
  **`CREATE`**, entity `serial_number`, no `after_data`. Warranty dates are
  refused on a profile without the `WARRANTY` feature; Electronics has it.
- **The screen reads** `GET /batch-serial/serials` — search is `ilike` on
  `serial_number`, the Status filter exact on `status` (`AVAILABLE`,
  `RESERVED`, `SOLD`, `INSTALLED`, `RETURNED`, `REPAIRED`, `SCRAPPED`, `LOST`).
- **Not written, ever:** nothing outside `app/batch_serial` touches the
  table. No movement carries `serial_id` (or `lot_id`) — zero rows across every
  store — so receiving or dispatching a serialised product leaves every
  serial `AVAILABLE` (D-STK-4). Editing one writes `UPDATE` with the previous
  status and number in `before_data`; deleting soft-deletes with `DELETE`.
- **Check:**
  ```sql
  select s.serial_number, s.status, s.warranty_start, s.warranty_end,
         w.code as warehouse, s.inventory_id, s.batch_id, s.version
  from   fx_<suffix>_e.serial_numbers s
  join   fx_<suffix>_e.warehouses w on w.id = s.warehouse_id
  where  s.serial_number like '<SUFFIX>-MIX-%'
  order  by s.serial_number;
  ```

### 10.10 Reversals — the `_REVERSAL` twins

- **What `reverse_transaction` writes:** one movement typed
  `<original type>_REVERSAL` with `quantity` = **minus** the original's, every
  bucket delta negated (`owned_quantity_delta` too, so a return that owned two
  and shelved one is undone in full), the original's `reference_number` and
  `reference_type`, **the original's `transaction_date`**, `remarks` = the
  reason the caller passed, `reversal_of_transaction_id` = the original. Its
  ledger row is valued at **today's average** — stock leaving is always issued
  at the average — which is why the caller's journal books any gap to 5400 or
  leaves it in 5200 (§9.6, §9.10). It writes **no journal itself** and refuses
  a second reversal of the same row ("This inventory movement was already
  reversed."). Reversing a reversal is legal, and the type grows another suffix
  (cut at 40 characters).
- **Only three callers:** cancelling a completed goods receipt
  (`GOODS_RECEIPT_REVERSAL`, §9.6), a completed purchase return
  (`RETURN_REVERSAL`), a completed sales return (`SALES_RETURN_REVERSAL`).
  **Nothing reverses** a transfer, a write-off, a hold, an adjustment, a
  posted count, an opening-stock batch or a dispatch: no endpoint exists, and a
  delivery note refuses cancellation once DISPATCHED. Undoing one is a second
  movement the other way — a release for a hold, a transfer back, an adjustment
  up — which the ledger then shows as two facts rather than one undone.
- **The date is the original's, not today's.** WHOLE01's
  `SALES_RETURN_REVERSAL` for SR-2026-2027-000002 is dated 2026-08-19, the day
  the return completed, and `inventories.last_transaction_at` goes back with
  it; the journal the caller posts is dated the first of that period
  (D-BUY-4). Neither says when the cancel happened — `created_at` does.
- **Seen live:** `GOODS_RECEIPT_REVERSAL` (TEST01 ×2, WHOLE01 ×2),
  `SALES_RETURN_REVERSAL` (WHOLE01 ×2). *(`RETURN_REVERSAL` not seen in a live
  row.)*

### 10.11 What stock does not write, and is often looked for

| You might expect | What actually happens |
| --- | --- |
| A journal for a transfer | None, deliberately (§10.2) |
| A journal for a hold or release | None; the valuation is not touched either (§10.4) |
| A system number on a transfer, write-off or hold | Typed, upper-cased, checked for nothing (BACKLOG §34); only counts are numbered |
| A `PHYSICAL_COUNT` transaction type | `ADJUSTMENT` with `reference_type` `PHYSICAL_COUNT` and the count number as reference (§10.5) |
| A lifecycle event for a count | None, ever; the `PHYSICAL_COUNT` document type exists only to number it |
| An audit row for a hold, a release, or Save progress on a count | Only `inventory.transaction.created` for the first two; nothing for the third (D-STK-6) |
| A quantity on `batches` | None; summed from `inventories` rows by `batch_id` every time |
| `batches.status` becoming `EXPIRED` | Never written; expiry is judged on `expiry_date` |
| A serial's status moving when it ships | Never; no movement names a serial (§10.9) |
| `in_transit_quantity` moving on a transfer | Never written by anything — a transfer is out and in at once |
| `blocked_quantity` / `damaged_quantity` moving here | Only a goods receipt (rejected, damaged) and a sales return write them; write-offs and holds use `current` and `quarantine` |
| A reversal for a write-off, transfer, hold, adjustment or dispatch | None (§10.10) |
| A row on the server for the remembered filter | None; a JSON file on the machine (§10.8) |
| `inventories.status`, min / max / reorder levels changing with stock | Master edits only — `PUT /inventory/{id}`, audit `inventory.updated` |
| A batch or serial audit row named like the rest (`batch.created`) | Bare `CREATE` / `UPDATE` / `DELETE`, no `after_data` (D-STK-10) |

### 10.12 Checked against live rows, and not

- **Confirmed on TEST01** (the `T0916NF7T` run): the movement chain
  `OPENING_STOCK` 50 → `TRANSFER_OUT` 47 → `WRITE_OFF` 46 → `QUARANTINE_HOLD`
  44 with `previous_*`/`new_*` agreeing at every step; the `<SUFFIX>-W2` row
  inserted by the inbound leg; both transfer legs costed 60 / 180 with no
  journal; the write-off's journal Dr 5500 60.00 / Cr 1200 60.00 with
  `source_id` = the movement; the hold's null cost and untouched average; four
  audit rows for the write-off, three for the transfer, one for the hold, all
  grouped by request id; a first count bootstrapping its document type, states
  and numbering rule in the same request as `inventory.physical_count.opened`;
  a draft sheet drawn over ten lines of other runs' products.
- **Confirmed on WHOLE01:** `TRF-0001` / `TRF-0002` at 95.670659 both legs, no
  journal; write-off `33` Dr 5500 95.67 / Cr 1200; hold `4444`;
  `PC-2026-2027-000005` posted with nothing counted; two
  `SALES_RETURN_REVERSAL` rows dated their originals; `RESERVE` on the order
  date and `UNRESERVE` on cancel dated the day before it (D-STK-7);
  `inventory.updated` from master edits.
- **Confirmed on the pharmacy stores** (`fx_t0916ei35_p` before the D-8-1 fix,
  `fx_t0916f8m2_p` after): three `batches` rows per run inserted by opening
  stock with audit `CREATE`; the opening journal Dr 1200 / Cr 3000 1,980.00;
  the reservation on the expired `B1` in both; `DISPATCH` from `B1` before the
  fix and from `B2` after; the COGS journal Dr 5200 300.00 / Cr 1200; SHT's
  two reservations of 3 and 7 leaving available −7.
- **Confirmed on the electronics store:** five serials `AVAILABLE` with
  warranty a year on, `inventory_id` and `batch_id` null; no movement in any
  of the nineteen stores read carries `serial_id` or `lot_id`.
- **Not seen in a live row:** a count line that was adjusted; a quarantine
  release; a write-off taken from quarantine; a refused dispatch; a
  `RETURN_REVERSAL`; a transfer, write-off or hold entered in a unit other than
  the base one (`entered_uom_id` is null on every movement looked at); a count
  over a batch row; a batch or serial edited or deleted through the API in a
  fixture store.
- **Where the stock rows are, 2026-09-18:** TEST01 52 movements (12
  `GOODS_RECEIPT`, 12 `OPENING_STOCK`, 8 `RESERVE`, 5 `UNRESERVE`, 5
  `DISPATCH`, 2 `RETURN`, 2 `GOODS_RECEIPT_REVERSAL`, 2 `ADJUSTMENT`, one each
  of the transfer legs, `WRITE_OFF`, `QUARANTINE_HOLD`), one draft count, no
  batches or serials; WHOLE01 262 (68 `RESERVE`, 67 `UNRESERVE`, 62 `DISPATCH`,
  34 `GOODS_RECEIPT`, 11 `SALES_RETURN`, 7 `RETURN`, 3 `OPENING_STOCK`, two
  each of the transfer legs, `GOODS_RECEIPT_REVERSAL` and
  `SALES_RETURN_REVERSAL`, one `WRITE_OFF`, one `QUARANTINE_HOLD`), five counts
  (one posted, three draft, one cancelled), no batches or serials. Batches
  exist only in the two pharmacy stores (three each) and serials only in the
  electronics store (five). The seeded firms hold **no** batch or serial rows at
  all.

---

## 11. Selling — quotation to cash (TC-SELL-001 to 017)

Read on 2026-09-19 off `quotation_service.py`, `sales_order_service.py`,
`workflow_settings_service.py`, `delivery_note_service.py`,
`sales_invoice_service.py`, `sales_chain_service.py`, `sales_return_service.py`,
`credit_note_service.py`, `proforma_service.py`, `settlement_service.py`,
`tcs_service.py`, `loyalty_service.py`, `credit_control.py`,
`customer_service.py`, `app/core/utils/pricing.py`, the price-list resolver and
the promotion and redemption services, and off what they call —
`InventoryService` (§10 has the stock detail), `DocumentPostingService`,
`JournalEntryEngine`, `DocumentFrameworkService`,
`DocumentPrintTemplateService`. Then checked, read-only, against the four
selling fixture stores of 2026-09-16 and against WHOLE01. §11.22 says which
claims a live row confirmed and which it could not. A claim marked *(not seen
in a live row)* was read off the code only.

### 11.0 Before you look

- **Store: not TEST01.** Every `selling-*` fixture, `loyalty-points` and
  `policy-firm` builds a Wholesale firm of the run's own, `<SUFFIX>-S`, whose
  schema is **`fx_<suffix>_s`** with the suffix in lower case (`fx_t0916h2j3_s`).
  The fixture's **Tables** line prints the name. For WHOLE01 put
  `wholesale_hub`. TEST01 holds a few orders, notes and invoices from other
  fixtures and none of the TC-SELL cases.
- **Find your rows by the fixture's codes:** customers `<SUFFIX>-C01` (Vijaya)
  and `<SUFFIX>-C02` (Anand), product `<SUFFIX>-DET`. Every number restarts in
  each fixture store, so `SO-2026-2027-000001` is a different order in every
  run.
- **All selling audit rows go to the firm's own trail**, `fx_<suffix>_s.audit_logs`.
  None reaches `platform.audit_logs`.
- **Numbers.** Only the delivery note carries firm and branch:

  | Document | Number | Lifecycle `source_module_code` |
  | --- | --- | --- |
  | Quotation | `QT-2026-2027-000001` | `SALES_QUOTATION` |
  | Sales order | `SO-2026-2027-000001` | `SALES_ORDER` |
  | Delivery note | `DN-<SUFFIX>-S-HO-2026-2027-000001` | `DELIVERY_NOTE` |
  | Sales invoice | `SI-2026-2027-000001` | `SALES_INVOICE` |
  | Sales return | `SR-2026-2027-000001` | `SALES_RETURN` |
  | Credit note | `CN-2026-2027-000001` | `CREDIT_NOTE` — `CREATED` only (D-SELL-23) |
  | Proforma | `PI-2026-2027-000001` — the **same series letters as a purchase invoice** (D-SELL-17) | `PROFORMA_INVOICE`, actions `PROFORMA.CREATED` / `PROFORMA.ISSUED` / `PROFORMA.CANCELLED` |
  | Receipt | `RC-2026-2027-000001` (refund `RF-…`) | none — settlements write no lifecycle event |

  Every create accepts a typed number instead (`order_number`,
  `delivery_note_number`, `invoice_number`, …). Issuing a number moves
  `document_number_sequences` and the rule, as in §9.0, and the first document
  of its kind in a firm inserts its type, states and numbering rule.
- **Two log rows ride along with every priced save.** Each line's tax is
  worked out by `TaxRuleService.simulate`, which writes a
  `tax_rule_execution_logs` row and an audit row `tax.rule.simulated`
  (`after_data.transaction_type` `SALES_QUOTATION`, `SALES_ORDER`,
  `DELIVERY_NOTE`, `SALES_INVOICE` or `SALES_RETURN`). Each quotation or order
  save also stages one `promotion_execution_logs` row (the engine's input,
  trace and result), with no audit row.
- **The customer's balance moves only through `customer_receivable_transactions`.**
  One row per movement — `transaction_type` `INVOICE`, `RECEIPT`, `TCS`,
  `ADVANCE_APPLY`, `CREDIT_NOTE`, `LOYALTY`, `REFUND` or `REVERSAL`;
  `amount`; the split it made, `outstanding_delta` and `advance_delta`; the
  balance after it, `outstanding_after` and `advance_after`; and
  `reference_type` / `reference_id` / `reference_number`. The same request
  moves `customers.current_outstanding`, `customers.unapplied_advance_balance`
  and `customers.version`, and writes audit `customer.receivable_transaction_posted`
  (or `…_reversed`). This is the table that explains the Outstanding and
  Advance figures on the customer screen:
  ```sql
  select t.created_at, t.transaction_type, t.amount, t.outstanding_delta,
         t.advance_delta, t.outstanding_after, t.advance_after,
         t.reference_type, t.reference_number
  from   fx_<suffix>_s.customer_receivable_transactions t
  join   fx_<suffix>_s.customers c on c.id = t.customer_id
  where  c.code = '<SUFFIX>-C01'
  order  by t.created_at, t.id;
  ```
- **One click, all its audit rows** — the §9.0 request-id query works
  unchanged with `fx_<suffix>_s` as the schema and the action you took
  (`delivery_note.dispatched`, `sales_invoice.approved`,
  `settlement.receipt.reversed`).
- **What points at what.** None of the source links below has a foreign key:

  | From | Column | To |
  | --- | --- | --- |
  | `sales_orders` | `reference_number` (the QT number, after a convert) | `sales_quotations` |
  | `sales_quotations` | `converted_sales_order_id`, `converted_sales_order_number` | `sales_orders` |
  | `delivery_notes` | `sales_order_id`, `sales_order_reference` (copied) | `sales_orders` |
  | `delivery_note_lines` | `sales_order_line_id`; `inventory_transaction_id`, `released_reservation_transaction_id` | `sales_order_lines`; the `DISPATCH` and `UNRESERVE` (§10.6) |
  | `sales_invoice_lines`, `sales_return_lines` | `source_document_type`, `source_document_id`, `source_document_line_id` | the note (or invoice) and its line |
  | `credit_note_lines` | `sales_invoice_line_id` | `sales_invoice_lines` |
  | `proforma_invoice_lines` | `source_sales_order_line_id` | `sales_order_lines` |
  | `promotion_redemptions` | `document_type` `SALES_ORDER` + `document_id` | the order |
  | `settlement_allocations` | `settlement_id`, `sales_invoice_id` | `settlements`, `sales_invoices` |
  | `journal_entries` | `source_module` + `source_id`; `reference_number` the document number, `-REV` for a reversal | `delivery_note`, `sales_invoice`, `sales_return`, `credit_note`, `settlements`, `tcs`, `loyalty` |
  | `inventory_transactions` | `reference_number` = the **order** number (`RESERVE`/`UNRESERVE`), the DN (`DISPATCH`), the SR (`SALES_RETURN`) | — |

- **Where the selling rows are, 2026-09-19.** `fx_t0916h2j3_s` is a store
  somebody walked through TC-SELL-001 to 017 by API on 2026-09-16 (six
  quotations, five orders, two notes, two invoices, two receipts, a return, a
  credit note, a proforma) — most "confirmed" below means that store.
  `fx_t0916d751_s` is `selling-paid` plus a cancelled order carrying an issued
  proforma. `fx_t09164wau_s` is `loyalty-points` followed by `policy-firm`'s
  steps, including a bill raised through the automatic chain. `fx_t0916z0ph_s`
  is `policy-firm` untouched. WHOLE01 holds 34 quotations, 72 orders, 62 notes,
  53 invoices, 11 returns, 12 credit notes, 52 settlements and 18 proformas.

### 11.1 Price resolution — nothing is written until the document saves (TC-SELL-001 to 004, 006)

- **Reads, never writes:** `resolve_line_discount` (`app/core/utils/pricing.py`)
  takes, in order, a typed `discount_amount` → `discount_source` `amount`; a
  typed `discount_percent`, **0 included** → `percent`; what a promotion gave
  → `promotion`; the price list's break → `price_list`; the customer's
  `default_discount_percent` above 0 → `customer`; their segment's
  (`customer_groups.default_discount_percent`) above 0 → `customer_group`;
  otherwise `none`. The stored percentage is derived from the amount actually
  taken.
- **The price list** (`PriceListResolver`) reads `price_lists` (ACTIVE, not
  deleted, `effective_from` ≤ the document date ≤ `effective_to` or open) and
  `price_list_items`. A customer's own list outranks a territory's, which
  outranks the firm-wide one, and the more specific list **replaces** the
  ladder rather than amending it. Within a list, the highest `min_quantity` at
  or below the line's quantity wins.
- **Where the answer lands:** only `sales_quotation_lines.discount_source` and
  `sales_order_lines.discount_source` carry the source, beside
  `discount_percent` and `discount_amount`; `sales_orders.bill_discount_source`
  is `typed`, `promotion` or `none`; `customer_discount_percent` on both
  headers snapshots the standing rate. **Notes, invoices and returns store the
  percentage and amount they inherited and no source.**
- **Confirmed** in `fx_t0916h2j3_s`: QT-…-000001 (C01, 12) 2.0000 `price_list`,
  1,165.6512; QT-…-000002 (18) 6.7500 `price_list`; QT-…-000003 (C02, 18)
  9.2500 `price_list`; QT-…-000004 (C02, 30) 7.5000 `promotion`; QT-…-000005
  (typed 0) 0.0000 `percent`, 2,973.60. Orders: WELCOME10 and WELCOME10B 2.5000
  `promotion`, NOSUCHCODE 2.0000 `price_list`.
- **Check** — every line of the customer's quotations and orders, with its
  source:
  ```sql
  select 'QT' as doc, q.quotation_number as number, q.status, l.quantity,
         l.discount_percent, l.discount_source, q.grand_total
  from   fx_<suffix>_s.sales_quotations q
  join   fx_<suffix>_s.sales_quotation_lines l on l.sales_quotation_id = q.id
  join   fx_<suffix>_s.customers c             on c.id = q.customer_id
  where  c.code = '<SUFFIX>-C01'
  union all
  select 'SO', o.order_number, o.status, l.quantity,
         l.discount_percent, l.discount_source, o.grand_total
  from   fx_<suffix>_s.sales_orders o
  join   fx_<suffix>_s.sales_order_lines l on l.sales_order_id = o.id
  join   fx_<suffix>_s.customers c         on c.id = o.customer_id
  where  c.code = '<SUFFIX>-C01'
  order  by 1, 2;
  ```
  Put `-C02` for TC-SELL-003 and 004.

### 11.2 Quotation — create, revise, send, accept (TC-SELL-001 to 005)

- **Create** inserts `sales_quotations` (`status` DRAFT always — the create
  body has no status field and refuses one; `valid_until`, totals,
  `customer_discount_percent`, `bill_discount_*`, `freight_amount`),
  `sales_quotation_lines` (reconciled on `line_number`, with `discount_source`),
  attachments and notes; lifecycle `CREATED`. **Audit:** `quotation.created`
  (`after_data` `quotation_number`, `status`) and one `tax.rule.simulated`.
  No stock, no journal, and **no promotion claim** — a quotation stages none,
  and it has no coupon field at all (D-SELL-28).
- **Revise** (DRAFT or SENT only — "Only draft or sent quotations can be
  edited.") updates the lines in place by `line_number`, **physically
  deletes** dropped lines, attachments and notes and re-inserts the last two;
  lifecycle `UPDATED`; audit `quotation.updated` with `grand_total` and
  `valid_until` before and after. A revision prices every resolved line
  afresh, which is why TC-SELL-002 gets 6.75 after 12 → 18. *(Not seen in a
  fixture store; WHOLE01 has 16.)*
- **Mark as sent:** DRAFT → SENT, `sent_at`; lifecycle `SENT`; audit
  `quotation.sent`. **Customer accepted:** DRAFT or SENT → ACCEPTED,
  `decided_at`, the reason as lifecycle `remarks` and in `after_data.remarks`;
  audit `quotation.accepted`. Sending is not required before accepting.
  Declined: `decline_reason`, audit `quotation.declined`. Cancel: audit
  `quotation.cancelled`, refused only once converted. Delete (DRAFT only):
  soft delete, audit `quotation.deleted`, no lifecycle event.
- **Refused, nothing written:** sending or accepting after `valid_until`
  ("… expired on …").
- **Check** — the quotation's life:
  ```sql
  select e.created_at, e.document_number, e.action, e.from_state, e.to_state, e.remarks
  from   fx_<suffix>_s.document_lifecycle_events e
  where  e.source_module_code = 'SALES_QUOTATION'
  order  by e.created_at;
  ```

### 11.3 Convert an accepted quotation (TC-SELL-005)

- **Writes, in two commits:** first a whole sales order through the ordinary
  create (§11.4) — `sales_orders` DRAFT with `reference_number` = the QT
  number, its lines, lifecycle `CREATED`, audits `sales_order.created` and
  `tax.rule.simulated`, **committed**; then on the quotation `status`
  CONVERTED, `converted_sales_order_id`, `converted_sales_order_number`,
  `converted_at`, lifecycle `CONVERTED` with remarks "Became SO-…", audit
  `quotation.converted`. Because they are two commits, a failure between
  them leaves an order beside a quotation still ACCEPTED (D-SELL-14).
- **The order's lines arrive as typed discounts.** Each line is handed over
  with both the percentage and the amount, so the order reads
  `discount_source` **`amount`** and `bill_discount_source` **`typed`** — and
  a line priced by hand is skipped by the promotion engine, so a converted
  order **stages no claim and never counts against an offer's limit**
  (D-SELL-9). Confirmed: `fx_t0916h2j3_s` SO-…-000005 from QT-…-000006 reads
  9.2500 `amount` and `typed`; WHOLE01's three converted orders have no
  `promotion_redemptions` row.
- **Refused, nothing written:** a second convert ("Quotation QT-… already
  became SO-…."), one that is not ACCEPTED ("Only an accepted quotation can
  become an order."), an expired one.

### 11.4 Sales order — create and edit a draft; coupons (TC-SELL-006)

- **Inserts:** `sales_orders` (`status` **DRAFT always** — `SalesOrderCreate`
  has no status field, so unlike D-BUY-1 an order cannot be born approved;
  `coupon_code` stored upper-cased **whether or not anything recognises it**;
  `customer_discount_percent`; `credit_limit_snapshot`;
  `outstanding_balance_snapshot` — which is the customer's **opening** balance,
  not what they owe, so it reads 0.00 on every live order (D-SELL-25);
  `line_discount_total`, `subtotal`, `tax_total`, `grand_total`,
  `bill_discount_*`, `freight_amount`); `sales_order_lines` (`quantity`,
  `free_quantity`, `unit_price`, `discount_percent`, `discount_source`,
  `discount_amount`, `bill_discount_amount`, `freight_amount`, `gross_amount`,
  `tax_amount`, `net_amount`, `reservable_quantity`, `reserved_quantity` 0, and
  a snapshot of `available_stock` / `reserved_stock`); a gift the engine gave
  becomes its own line at price 0 ("Free with <code>"); attachments and notes;
  lifecycle `CREATED`.
- **The promotion claim is staged, not counted:** one
  `promotion_redemptions` row per applied offer (`promotion_id`, `coupon_id`,
  `customer_id`, `document_type` `SALES_ORDER`, `document_id`,
  `document_number`, `redeemed_on`, `benefit_amount`, `status` **PENDING**).
  A PENDING row counts against no limit.
- **Audit:** `sales_order.created` (`order_number`, `status`) and
  `tax.rule.simulated`. No stock, no journal, nothing on the customer.
- **Edit a draft** ("Only draft sales orders can be updated."): lines matched
  on `line_number`, dropped ones physically deleted; attachments and notes
  physically deleted and re-inserted; the order's PENDING claims
  **soft-deleted** and staged again, CLAIMED ones untouched; lifecycle
  `UPDATED`; audit `sales_order.updated`.
- **A coupon nobody recognises refuses nothing and claims nothing:** it is
  kept on `coupon_code` and simply matches no offer. Confirmed in
  `fx_t0916h2j3_s`: SO-…-000001 WELCOME10 and SO-…-000002 WELCOME10B each hold
  a PENDING WELCOME claim of 25.20; SO-…-000003 NOSUCHCODE holds none and is
  priced at the list's 2%.

### 11.5 Approve an order — the reservation and the claim (TC-SELL-007)

In this order, all in one request:

- **Credit** is judged first (§11.6). A block raises here and nothing below
  is written.
- **The claim:** PENDING → **CLAIMED** on each of the order's
  `promotion_redemptions` rows, under a row lock on the `promotions` row (and
  the `promotion_coupons` row when a coupon reached it). Refused, with
  nothing written, when an offer or coupon has reached its limit ("Promotion
  … has been claimed as often as it allows. Re-save the document to price it
  without."). **No audit row of its own** — it rides on `sales_order.approved`.
- **The reservation:** per line, one `RESERVE` movement (§10.0) per batch held,
  `reference_number` = the **order** number, `reference_type` `SALES_ORDER`,
  dated the order date, remarks "sales_order reserve line 1", no cost;
  `inventories.reserved_quantity` up and `available_quantity` down;
  `sales_order_lines.reserved_quantity` = `reservable_quantity`.
- **Then** `sales_orders.status` APPROVED, `approved_at`; lifecycle
  `APPROVED`.
- **Audit — two rows** (confirmed): `inventory.transaction.created` (the
  `RESERVE`) and `sales_order.approved`.
- **Not written:** no journal, nothing on the customer's balance.
- **Refused:** an order that is not DRAFT ("Only draft sales orders can be
  approved.").
- **Check** — the hold on the shelf and the claim:
  ```sql
  select w.code as warehouse, i.current_quantity, i.reserved_quantity, i.available_quantity
  from   fx_<suffix>_s.inventories i
  join   fx_<suffix>_s.products p   on p.id = i.product_id
  join   fx_<suffix>_s.warehouses w on w.id = i.warehouse_id
  where  p.code = '<SUFFIX>-DET';

  select r.document_number, r.status, r.benefit_amount, r.is_deleted,
         p.code as promotion, c.code as coupon, r.reversed_at
  from   fx_<suffix>_s.promotion_redemptions r
  join   fx_<suffix>_s.promotions p       on p.id = r.promotion_id
  left join fx_<suffix>_s.promotion_coupons c on c.id = r.coupon_id
  order  by r.created_at;
  ```
  For `selling-ordered`: MAIN 100 / 12 / 88; one WELCOME row, coupon
  WELCOME10, **CLAIMED**, 25.20.

### 11.6 Credit limit — warn, and block where the firm asks (TC-CUST-004, TC-FIN-008)

- **The policy** is `credit_control_settings` (`enforcement` OFF / WARN /
  BLOCK, `warn_at_percent`, `block_at_percent`), one row per firm. A firm with
  no row warns at 80% and never blocks; a limit of 0 means no limit. Writing
  it (`PUT /customers/credit-settings`, `CUSTOMER_MANAGE_SETTINGS`) records
  audit **`CREATE`** or **`UPDATE`** with `entity_type` `CreditControlSettings`
  (D-SELL-24).
- **Judged at** order approval and again at invoice approval (the invoice
  locks the customer row first). Exposure = outstanding − advance + the
  document's `grand_total`.
- **A warning writes nothing.** The approval goes through; the warning the
  desktop shows comes from `GET /customers/{id}/credit-status`. The order
  service computes the assessment and discards it (D-SELL-26).
- **A block writes nothing** — no status move, no reservation, no claim, no
  audit row. Confirmed: `fx_t09164wau_s` and `fx_t0916z0ph_s` each hold
  Anand's order for 1,799.03 against a 1,000.00 limit at DRAFT with
  `approved_at` null and only `sales_order.created` in the trail.
- **Check:**
  ```sql
  select s.enforcement, s.warn_at_percent, s.block_at_percent from fx_<suffix>_s.credit_control_settings s;

  select o.order_number, o.status, o.approved_at, o.grand_total, c.credit_limit,
         c.current_outstanding, c.unapplied_advance_balance
  from   fx_<suffix>_s.sales_orders o
  join   fx_<suffix>_s.customers c on c.id = o.customer_id
  where  c.code = '<SUFFIX>-C02';
  ```

### 11.7 Hold and release (TC-SELL-008)

- **Hold** updates `sales_orders` only: `is_on_hold` true, `hold_reason`,
  `held_at`, `held_by`, `released_at`/`released_by` cleared, `version` +1.
  **`status` does not move** — a hold is a flag. Lifecycle `HELD` with
  `from_state` = `to_state` = the status and the reason as remarks. Audit
  `sales_order.held` (`after_data` `status`, `is_on_hold` true, `hold_reason`).
- **The reservation stays.** No `UNRESERVE`, nothing on `inventories`.
- **The refused note writes nothing.** "SO-… is on hold and cannot be
  dispatched ("awaiting cheque"). Release it first." is raised by the note's
  **create** before any row exists.
- **A hold does not stop a note that already exists.** Only create checks the
  flag; editing, approving, dispatching or completing a note raised before the
  hold goes through, and the goods leave while the order reads "on hold"
  (D-SELL-5). *(Not seen in a live row.)*
- **Release:** `is_on_hold` false, `released_at`, `released_by`;
  **`hold_reason` is kept**. Lifecycle `RELEASED` (remarks = what was typed
  on release). Audit `sales_order.released` with `before_data`
  `{is_on_hold: true, hold_reason}`.
- Confirmed in `fx_t0916h2j3_s` on SO-…-000004: HELD "awaiting cheque",
  RELEASED "cheque cleared", both APPROVED → APPROVED; the hold reason still
  on the row after it was delivered.
- **Check:**
  ```sql
  select o.order_number, o.status, o.is_on_hold, o.hold_reason, o.held_at, o.released_at,
         l.reserved_quantity
  from   fx_<suffix>_s.sales_orders o
  join   fx_<suffix>_s.sales_order_lines l on l.sales_order_id = o.id;
  ```

### 11.8 Cancel or close an order (TC-SELL-017 step 2)

- **Cancel:** every line still holding stock is released — one `UNRESERVE`
  per batch, `reference_number` the order number, remarks "sales_order
  release line 1", **dated today (UTC)**, so it can read a day before the
  reservation (D-STK-7; confirmed on `fx_t0916d751_s` SO-…-000002, reserved
  2026-09-16 and released 2026-09-15); `sales_order_lines.reserved_quantity`
  0. Every PENDING or CLAIMED claim → **REVERSED** with `reversed_at` (the row
  kept). `status` CANCELLED, `cancel_reason`; lifecycle `CANCELLED`; audit
  `inventory.transaction.created` per release and `sales_order.cancelled`.
- **Cancel is refused only for an order already CANCELLED or CLOSED.** A
  DELIVERED or billed order can be cancelled: its claims are handed back
  while the discount stays on the invoice, and the order leaves every report
  of live orders (D-SELL-11). *(Not seen in a live row.)*
- **Close** releases what is held the same way and writes `closed_at`,
  `close_reason`, lifecycle `CLOSED`, audit `sales_order.closed` — but
  **leaves the claims alone**, and accepts a DRAFT, whose PENDING claims then
  stay forever (D-SELL-22).
- **Not written by either:** no journal. A proforma raised on the order is
  not touched (§11.18).

### 11.9 Delivery note — create and approve (TC-SELL-009)

- **Create** (the order must be APPROVED, PARTIALLY_DELIVERED, DELIVERED —
  or CLOSED, D-SELL-11 — and not on hold) inserts `delivery_notes` (DRAFT;
  `sales_order_id`, `sales_order_reference`, customer, branch, warehouse,
  salesman, route and territory copied from the order; totals) and
  `delivery_note_lines`: `sales_order_line_id`, `ordered_quantity`,
  `reserved_quantity` (a snapshot of the order line's),
  `previously_delivered_quantity` (what earlier **approved, dispatched,
  completed or closed** notes took), `current_delivery_quantity`,
  `free_quantity`, `delivered_quantity` (charged + free, in inventory units),
  `remaining_quantity`, `short_shipment_quantity`, and the **order line's**
  `unit_price` and discount rate where the form sent none (TC-SELL-010:
  84, 2.5000, `discount_amount` 10.50, net 483.21 — never re-read from the
  customer or a price list); `inventory_transaction_id` null. Lifecycle
  `CREATED`; audits `delivery_note.created` and `tax.rule.simulated`.
- **Approve:** `status` APPROVED, `approved_at`; lifecycle `APPROVED`; audit
  `delivery_note.approved` (no data beyond the request id). **Moves
  nothing** — TC-SELL-009's "an approved note moves nothing".
- **Refused:** more than the order line has left ("Delivery quantity exceeds
  allowed quantity for the order line.").
- **Cancel** (DRAFT or APPROVED only) writes the status, `cancel_reason`,
  lifecycle `CANCELLED`, audit `delivery_note.cancelled`. A DISPATCHED note
  cannot be cancelled and nothing reverses a dispatch (§10.10).
- **Close** refuses only a DRAFT. **An APPROVED note that never dispatched
  can be closed**, and a closed note counts as delivered for the order and is
  offered for billing (D-SELL-4). *(Not seen in a live row.)*

### 11.10 Dispatch — part deliveries move the order (TC-SELL-009, 010)

The stock side is §10.6; this is the whole request.

- **Inserts,** per line: an **`UNRESERVE`** of what the order held for it,
  where the order held it (`reference_number` the **order** number, dated the
  note's `delivery_date`, remarks "delivery_note release line 1"); then one
  **`DISPATCH`** per batch drawn (`reference_number` the DN, `reference_type`
  `DELIVERY_NOTE`, costed at the average); their `stock_ledger_entries`
  rows. Once per note: **`journal_entries`** (`source_module`
  `delivery_note`, `source_id` the note, reference the DN number) **Dr 5200
  Cost of Goods Sold / Cr 1200 Inventory** at the movements' `total_cost` —
  300.00 for 5 at 60, 420.00 for 7.
- **Updates:** `inventories`, `product_valuations`;
  `sales_order_lines.reserved_quantity` down by what was released;
  `delivery_note_lines.inventory_transaction_id`,
  `released_reservation_transaction_id`, `batch_id`; `delivery_notes.status`
  DISPATCHED, `dispatched_at`; lifecycle `DISPATCHED`; and the order's
  `status` **re-derived** from the sum of dispatched, completed and closed
  notes — PARTIALLY_DELIVERED, then DELIVERED.
- **Audit — six rows, one request** (confirmed twice in `fx_t0916h2j3_s`):
  `inventory.transaction.created` ×2 (the `UNRESERVE` and the `DISPATCH`),
  `finance.journal_entry.created`, `finance.journal_entry.posted`,
  `sales_order.delivered_status_changed` (`before_data`/`after_data`
  `status`, only when it moved), `delivery_note.dispatched`.
- **Not written:** no lifecycle event and no history row on the **order**
  when dispatch moves it — `sales_order.delivered_status_changed` in the trail
  is the only record. No revenue, nothing on the customer: goods leave here,
  and the sale is the invoice.
- **Refused, nothing written:** not enough available stock (§10.7), a
  reservation short of the quantity ("Reservation is insufficient for
  dispatch quantity."), a note that is not APPROVED.
- **Check** — the notes, and the movements and journals behind them:
  ```sql
  select d.delivery_note_number, d.status, d.dispatched_at, o.order_number, o.status as order_status,
         l.current_delivery_quantity, l.previously_delivered_quantity, l.remaining_quantity,
         l.unit_price, l.discount_percent, l.discount_amount, l.net_amount
  from   fx_<suffix>_s.delivery_notes d
  join   fx_<suffix>_s.delivery_note_lines l on l.delivery_note_id = d.id
  join   fx_<suffix>_s.sales_orders o        on o.id = d.sales_order_id
  order  by d.delivery_note_number;

  select t.created_at, t.transaction_type, t.reference_number, t.transaction_date,
         t.quantity, t.current_quantity_delta, t.reserved_quantity_delta,
         t.new_current_quantity, t.new_reserved_quantity, s.total_cost, t.remarks
  from   fx_<suffix>_s.inventory_transactions t
  join   fx_<suffix>_s.stock_ledger_entries s on s.transaction_id = t.id
  join   fx_<suffix>_s.products p             on p.id = t.product_id
  where  p.code = '<SUFFIX>-DET'
  order  by t.created_at, t.id;

  select je.reference_number, je.source_module, je.status, je.journal_date,
         je.reversal_of_id is not null as is_reversal,
         la.code, la.name, jl.debit_amount, jl.credit_amount
  from   fx_<suffix>_s.journal_entries je
  join   fx_<suffix>_s.journal_lines jl   on jl.journal_entry_id = je.id
  join   fx_<suffix>_s.ledger_accounts la on la.id = jl.ledger_account_id
  where  je.source_module <> 'inventory'
  order  by je.created_at, jl.line_number;
  ```
  The last query is every selling journal in the store — notes, invoices,
  receipts, TCS, returns, credit notes, loyalty — and is used again below.
  After TC-SELL-009: OPENING_STOCK +100, RESERVE 12, UNRESERVE 5, DISPATCH −5,
  UNRESERVE 7, DISPATCH −7; MAIN 88 / 0; two DN journals of 300.00 and
  420.00; the order DELIVERED.

### 11.11 Invoice from a note — the cap, the approval, its journal (TC-SELL-011)

- **Create** inserts `sales_invoices` (DRAFT; `due_date` from the customer's
  terms, `place_of_supply` from their billing address — both empty for the
  fixture's customers; `allow_direct_sales_order` true only when the firm's
  delivery-note stage is automatic); `sales_invoice_sources`, one per note;
  `sales_invoice_lines` (`source_document_type` DELIVERY_NOTE,
  `source_document_id`, `source_document_line_id`, `delivered_quantity` = the
  note line's **charged** quantity, `already_invoiced_quantity`,
  `current_invoice_quantity`, the note's `unit_price` and discount rate where
  the form sent none, `cost_amount` = that share of the dispatch's
  `total_cost`, `tax_amount`, `net_amount`, `accounting_event_reference`
  `SI-…:1`); **`sales_invoice_line_taxes`** — one row per component,
  CGST 9 and SGST 9 on 409.50, 36.855 each, which is where the split the
  printed bill shows lives; **`sales_invoice_accounting_events` — three
  placeholders** (`SALES_REVENUE`, `OUTPUT_TAX`, `ACCOUNTS_RECEIVABLE`,
  narration "Placeholder accounting event for …"), which are **not the
  ledger**; attachments and notes; lifecycle `CREATED`. Audits
  `sales_invoice.created` and `tax.rule.simulated`.
- **The cap:** billed + already billed by every invoice that is not CANCELLED
  (drafts included) ≤ the note line's charged quantity. Refused, nothing
  written: "Invoice quantity exceeds the available source quantity." — the
  desktop says "Only 5.0 left to bill." before sending.
- **Not checked by the server: that the note was dispatched.** A DRAFT,
  APPROVED or CANCELLED note can be billed through the API; only the
  desktop's picker filters (D-SELL-3). *(Every live invoice line sits on a
  DISPATCHED note.)*
- **Edit a draft** physically deletes every child — lines (their taxes by
  cascade), sources, accounting events, attachments, notes — and inserts them
  again; lifecycle `EDITED`; audit `sales_invoice.updated`.
- **Approve** (DRAFT only), after the credit check under a lock on the
  customer:
  - `customer_receivable_transactions` `INVOICE`, `reference_type`
    `SALES_INVOICE`, 483.21 — Outstanding up;
  - `journal_entries` (`source_module` `sales_invoice`, reference the SI
    number, dated the invoice date): **Dr 1100 Trade Receivables 483.21 /
    Cr 4000 Sales 409.50 / Cr 2200 Output Tax 73.71** — one tax line; the
    split is on the invoice;
  - `sales_invoices.status` APPROVED, `approved_at`; lifecycle `APPROVED`;
  - **audit — four rows** (confirmed): `customer.receivable_transaction_posted`,
    `finance.journal_entry.created`, `finance.journal_entry.posted`,
    `sales_invoice.approved`.
- **Loyalty points should follow and do not.** Approval commits, then stages
  the `EARNED` entry and its journal with nothing left to commit them — so no
  invoice approved through the API or the desktop earns a point (D-SELL-1,
  §11.19).
- **Not written:** no stock and no cost of goods — both were the note's
  (§11.10). Nothing on the note or the order.
- **Check:**
  ```sql
  select i.invoice_number, i.status, i.subtotal, i.tax_total, i.grand_total,
         l.source_document_number, l.delivered_quantity, l.already_invoiced_quantity,
         l.current_invoice_quantity, l.unit_price, l.discount_percent, l.cost_amount,
         t.component_code, t.percentage, t.base_amount, t.amount
  from   fx_<suffix>_s.sales_invoices i
  join   fx_<suffix>_s.sales_invoice_lines l      on l.sales_invoice_id = i.id
  left join fx_<suffix>_s.sales_invoice_line_taxes t on t.sales_invoice_line_id = l.id
  order  by i.invoice_number, l.line_number, t.sequence;
  ```
  and the §11.10 journal query and the §11.0 receivable query.

### 11.12 Cancel or close an invoice (not in the cases)

- **Cancel** is refused while anything rests on the bill — a POSTED receipt
  applied to it, a live credit note, a live return sourced on it, points
  spent on it, a registration with the tax portal ("SI-… cannot be cancelled
  while it has …. Reverse or cancel those first."). Otherwise an APPROVED
  invoice gets `SI-…-REV` (`reversal_of_id`, the original REVERSED, dated the
  first of the period — D-BUY-4) and a receivable row `CREDIT_NOTE`,
  `reference_type` `SALES_INVOICE`, dated today, remarks "Auto reversal for
  cancelled invoice …" (or the reason). Status CANCELLED, `cancel_reason`;
  lifecycle `CANCELLED`; audit `sales_invoice.cancelled`. Its quantity goes
  back on the notes, so they are offered for billing again. **The points it
  earned are not taken back** (D-SELL-2). Cancelling a DRAFT writes the status,
  the lifecycle event and the audit row only.
- **Close** refuses only an invoice already CLOSED — **a DRAFT or a CANCELLED
  invoice can be closed.** A closed draft never posts, yet keeps its quantity
  against the note, so those goods can never be billed; a cancelled one
  closed takes back the quantity its cancellation released (D-SELL-12).
  Closing writes `closed_at`, `close_reason`, lifecycle `CLOSED`, audit
  `sales_invoice.closed`, and no journal. *(Not seen in a live row.)*

### 11.13 Print settings and printing (TC-SELL-012)

- **Print settings** save one `document_print_templates` row per firm ×
  `document_type` (`SALES_INVOICE`): `title_text`, `accent_color`,
  `header_note`, `show_bank_details`, `bank_details`, `terms`, `declaration`,
  `jurisdiction`, `footer_note`, `signatory_text`, `show_discount_column`,
  `show_batch_column`, `show_expiry_column`, **`copy_labels`** (a JSON list —
  `["ORIGINAL FOR RECIPIENT", "DUPLICATE FOR TRANSPORTER"]`), `page_size`,
  `margin_mm`. Inserted on the first save, updated after. Audit
  `document_print_template.created` or `.updated`, `after_data` naming only
  the `document_type`. Needs `SETTINGS_UPDATE`. Confirmed on WHOLE01; no
  fixture store has one.
- **Printing writes nothing** — `GET /sales-invoices/{id}/print` renders the
  PDF from the invoice, its line taxes and the template, with no audit row.
- **Check:**
  ```sql
  select document_type, copy_labels, title_text, show_bank_details, version, updated_at
  from   fx_<suffix>_s.document_print_templates;
  ```

### 11.14 Record a receipt — allocation and TCS (TC-SELL-013)

- **Inserts, in order:** `journal_entries` (`source_module` `settlements`,
  `source_id` the settlement, reference the RC number) **Dr 1010 Bank**
  (`1000 Cash` for CASH) **/ Cr 1100 Trade Receivables** for the whole
  amount; `settlements` (`direction` RECEIPT, `customer_id`, `amount`,
  `allocated_amount`, `unallocated_amount`, `sales_order_id` when "Against
  order" was named, `method`, `ledger_account_id`, `status` POSTED,
  `journal_entry_id`); one `settlement_allocations` row per bill
  (`sales_invoice_id`, `amount`); a receivable row `RECEIPT`
  (`reference_type` `settlement`) that **stores the split** — whatever the
  customer owed comes off `outstanding_delta`, the excess goes to
  `advance_delta`.
- **Then TCS**, when the firm collects it and the receipt is above the
  threshold: `tcs_collections` (`consideration_amount`, `cumulative_before`
  — this year's earlier receipts, summed each time rather than held —
  `taxable_amount`, `rate_percent`, `without_pan`, `tcs_amount`, `status`
  COLLECTED, `journal_entry_id`, `receivable_transaction_id`); a journal
  `TCS-RC-…` (`source_module` `tcs`) **Dr 1100 / Cr 2500 TCS Payable**; a
  receivable row `TCS` (`reference_type` null, remarks "Tax collected at
  source under 206C(1H).") — the customer now owes the tax.
- **Audit — eight rows, one request** (confirmed):
  `customer.receivable_transaction_posted` ×2, `finance.journal_entry.created`
  ×2, `finance.journal_entry.posted` ×2, `settlement.receipt.recorded`
  (`settlement_number`, `amount`, `allocated_amount`, `party` = the customer's
  code), `tcs.collected`.
- **Not written:** no lifecycle event; nothing on `sales_invoices` — there is
  no PAID status, and what a bill still owes is its total less POSTED
  allocations and redeemed points, derived each time.
- **Refused, nothing written:** a draft or cancelled bill, another customer's,
  more than it owes, allocations beyond the amount.
- **Confirmed** on `fx_t0916d751_s` (the `selling-paid` rows): RC-…-000001
  241.60, RECEIPT −241.60 / 0 → 241.61, TCS 2.42 at 1% (`without_pan` true,
  `cumulative_before` 0) → **244.03**; RC-…-000002 341.61 with 241.61
  allocated and 100.00 unallocated, RECEIPT **−244.03 / +97.58** → 0.00 /
  97.58, TCS 3.42 (`cumulative_before` 241.60) → **3.42 / 97.58**.
- **Record Receipt keeps offering a bill's full remainder after a return or a
  credit note against it** — SI-…-000001 in `fx_t0916h2j3_s` is offered at
  241.60 though a 193.28 return and a 59.00 credit note stand against it
  (D-SELL-10).
- **Check:**
  ```sql
  select s.settlement_number, s.status, s.amount, s.allocated_amount, s.unallocated_amount,
         s.method, i.invoice_number, a.amount as applied,
         tc.tcs_amount, tc.rate_percent, tc.without_pan, tc.status as tcs_status
  from   fx_<suffix>_s.settlements s
  left join fx_<suffix>_s.settlement_allocations a on a.settlement_id = s.id and a.is_deleted = false
  left join fx_<suffix>_s.sales_invoices i         on i.id = a.sales_invoice_id
  left join fx_<suffix>_s.tcs_collections tc       on tc.settlement_id = s.id
  where  s.direction = 'RECEIPT'
  order  by s.settlement_number, i.invoice_number;
  ```
  with the §11.0 receivable query for the balance after each step.

### 11.15 Apply an advance; reverse a receipt (TC-SELL-014)

- **Apply to an invoice** inserts one `settlement_allocations` row and, only
  for the part that really comes out of the advance, a receivable row
  `ADVANCE_APPLY` (`reference_type` `settlement`). It updates
  `settlements.allocated_amount` / `unallocated_amount`. **No journal** — the
  money arrived when the receipt was recorded. Audits
  `customer.receivable_transaction_posted` and `settlement.receipt.allocated`
  (`settlement_number`, `invoice_number`, `amount`, `unallocated_amount`).
  Confirmed in `fx_t0916h2j3_s`: applying 97.58 of RC-…-000002 to
  SI-…-000002 wrote `ADVANCE_APPLY` **95.16** (−95.16 / −95.16 → **584.75 /
  2.42**) — the other 2.42 had already gone to RC-…-000001's TCS when the
  receipt split — and left RC-…-000002 allocated 339.19, unallocated 2.42.
  Refused beyond what is left: "RC-… has only 2.42 left unapplied."
- **Reverse:** `RC-…-REV` (the mirror, `reversal_of_id`, the original
  REVERSED, **dated the first of the period** — 2026-09-01 — D-BUY-4); a
  receivable row `REVERSAL` (`reference_type` `reversal`, the stored deltas
  negated, reference `RC-…-REV`, remarks the reason); and the TCS undone —
  `TCS-RC-…-REV` Dr 2500 / Cr 1100, a second `REVERSAL` row carrying
  reference `TCS-RC-…` with no `-REV` and no remarks (D-SELL-27),
  `tcs_collections.status` REVERSED. `settlements.status` REVERSED,
  `reversal_journal_entry_id`, `reversed_at`, `reversed_by`,
  `reversal_reason`. **The allocations stay**, not even soft-deleted; they
  stop counting because the receipt is no longer POSTED, so the bill comes
  back to Record Receipt.
- **Audit — ten rows, one request** (confirmed):
  `customer.receivable_transaction_reversed` ×2, `finance.journal_entry.created`
  ×2, `.posted` ×2, `.reversed` ×2, `settlement.receipt.reversed`
  (`before_data` POSTED; `after_data` `status`, `reversal_journal_entry_id`,
  `reason`), `tcs.reversed`.
- Confirmed in `fx_t0916h2j3_s` (RC-…-000001, "bounced"): +241.60 → 826.35,
  −2.42 → **823.93**, a net rise of **239.18**; GL 1100 still agrees with the
  customer's balance less their advance.
- **A receipt whose advance has been applied does not reverse cleanly.** The
  reversal looks up "the" receivable row for the settlement and there are now
  two (`RECEIPT` and `ADVANCE_APPLY`); whichever comes back is the one undone
  (D-SELL-8). RC-…-000002 in `fx_t0916h2j3_s` is in that state. *(Not driven —
  read-only.)*
- **Refused:** a second reversal ("RC-… has already been reversed."), one that
  would drive the balance below zero.

### 11.16 Sales return (TC-SELL-015)

- **Create** inserts `sales_returns` (DRAFT always), `sales_return_sources`,
  `sales_return_lines` (`source_document_type` SALES_INVOICE or
  DELIVERY_NOTE, `source_document_line_id`, `dispatched_quantity` — the
  source line's charged quantity — `already_returned_quantity`,
  `current_return_quantity`, `restock_quantity`, `damaged_quantity`,
  `scrap_quantity`, `unit_price`, `discount_percent`, `discount_amount`,
  `bill_discount_amount`, `tax_amount`, `net_amount`,
  `inventory_transaction_id` null), `sales_return_line_taxes` (CGST, SGST),
  attachments and notes; lifecycle `CREATED`; audits `sales_return.created`
  and `tax.rule.simulated`.
- **A missing price is not 0** — unlike the purchase return (D-BUY-3), the
  line takes the source line's `unit_price` and discount **rate**. Confirmed:
  84, 2.5000, 163.80 + 29.484 = 193.284.
- **The cap:** returned + already returned (every return not CANCELLED,
  drafts included, **on the same source line**) ≤ what the source line
  charged. Refused, nothing written: "Return quantity exceeds what was
  dispatched on the source document (5.0000 sent, 0.0000 already returned)."
  Because the count is per source line, goods returned against the note are
  not counted against the invoice that billed them (D-SELL-7), and the source
  document's **status is never checked** — a draft note or a cancelled
  invoice can be returned against (D-SELL-6).
- **The tax is worked out again** at the return date through the
  `SALES_RETURN` rules, not copied from what the invoice charged (D-SELL-21).
- **Edit a draft:** lines, sources, attachments and notes **physically
  deleted** and re-inserted (line taxes by cascade); lifecycle `UPDATED`;
  audit `sales_return.updated`.
- **Approve:** `status` APPROVED, `approved_at`; lifecycle `APPROVED`; audit
  `sales_return.approved`. Nothing moves.
- **Complete** (APPROVED only):
  - per line, `inventory_transactions` **`SALES_RETURN`** (`reference_type`
    `SALES_RETURN`, `reference_number` the SR number, +2, remarks
    "sales_return buckets restock=2.0000 damaged=0.0000 scrap=0.0000") and its
    ledger row at the average (120.00); `sales_return_lines.inventory_transaction_id`;
  - journal (`source_module` `sales_return`, reference the SR number):
    **Dr 4100 Sales Returns 163.80 / Dr 2200 Output Tax 29.48 / Cr 1100 Trade
    Receivables 193.28**;
  - a second journal **`SR-…-COST`: Dr 1200 Inventory / Cr 5200 Cost of Goods
    Sold 120.00**, at the movement's value;
  - receivable row `CREDIT_NOTE`, `reference_type` `SALES_RETURN`, 193.28 —
    Outstanding 823.93 → 630.65 in `fx_t0916h2j3_s`;
  - `sales_returns.status` COMPLETED, `completed_at`, `journal_entry_id`,
    `cost_journal_entry_id`; lifecycle `COMPLETED`;
  - **audit — seven rows, one request** (confirmed):
    `inventory.transaction.created`, `finance.journal_entry.created` ×2,
    `.posted` ×2, `customer.receivable_transaction_posted`,
    `sales_return.completed` (`after_data.stock_value` "120.0000").
- **Cancel a completed return:** a `SALES_RETURN_REVERSAL` per line (dated the
  original's date — D-STK-9), `SR-…-REV` and `SR-…-COST-REV` (both dated the
  first of the period — D-BUY-4), the originals REVERSED, a receivable
  `REVERSAL` by the stored deltas, `inventory_transaction_id`,
  `journal_entry_id` and `cost_journal_entry_id` cleared, `cancel_reason`;
  nine audit rows. Confirmed on WHOLE01 SR-2026-2027-000004.
- **Close** only from COMPLETED ("Only completed sales returns can be
  closed.") — the Buying defect does not recur here. Delete: DRAFT only, soft,
  audit `sales_return.deleted`.
- **Check:**
  ```sql
  select r.return_number, r.status, r.grand_total, l.source_document_type,
         l.source_document_number, l.dispatched_quantity, l.already_returned_quantity,
         l.current_return_quantity, l.unit_price, l.discount_percent, l.tax_amount,
         l.net_amount, t.transaction_type, t.current_quantity_delta, t.remarks
  from   fx_<suffix>_s.sales_returns r
  join   fx_<suffix>_s.sales_return_lines l on l.sales_return_id = r.id
  left join fx_<suffix>_s.inventory_transactions t on t.id = l.inventory_transaction_id;
  ```
  and the §11.10 journal query (the SR and SR-…-COST entries).

### 11.17 Credit note (TC-SELL-016)

- **Raise** (the invoice must be APPROVED or CLOSED) inserts `credit_notes`
  (DRAFT, `reason` — `RATE_DIFFERENCE`, `POST_SALE_DISCOUNT`,
  `DEFICIENCY_IN_SERVICE`, `OTHER` — `taxable_amount`, `tax_amount`,
  `total_amount`, `sales_invoice_id`) and `credit_note_lines`
  (`sales_invoice_line_id`, `quantity` 0 when none was sent,
  `taxable_amount`, `tax_amount`, `total_amount`, **`tax_rate_percent` = the
  rate that line was charged** — its tax ÷ its charged value, 18.0000).
  Lifecycle `CREATED`; audit `credit_note.created` (a full snapshot).
- **The cap**, read under a lock on the invoice line: credited + already
  credited by live credit notes ≤ what the line was charged. Refused, nothing
  written: "A credit note cannot credit more than the line was charged:
  409.5000 charged, 50.0000 already credited." Returns are not netted against
  it.
- **Approve:** journal (`source_module` `credit_note`, reference the CN
  number, dated the note's date) **Dr 4100 Sales Returns 50.00 / Dr 2200
  Output Tax 9.00 / Cr 1100 Trade Receivables 59.00**; receivable row
  `CREDIT_NOTE` 59.00 with **`reference_type` and `reference_id` null**
  (D-SELL-23); `status` APPROVED, `journal_entry_id`,
  `receivable_transaction_id`. **Audit — four rows** (confirmed):
  `finance.journal_entry.created`, `.posted`,
  `customer.receivable_transaction_posted`, `credit_note.approved`. **No
  lifecycle event** — the timeline stops at CREATED (D-SELL-23).
  Outstanding 630.65 → **571.65** in `fx_t0916h2j3_s`.
- **Not written:** no stock — a credit note is money only.
- **Edit a draft:** old lines **soft-deleted**, new ones inserted; audit
  `credit_note.updated`. **Cancel** (DRAFT or APPROVED): `CN-…-REV` dated the
  note's own date, the receivable reversed by its deltas, audit
  `credit_note.cancelled`. There is no close. *(Neither seen in a live row.)*
- **Check:**
  ```sql
  select n.credit_note_number, n.status, n.reason, n.taxable_amount, n.tax_amount,
         n.total_amount, l.tax_rate_percent, il.line_number as invoice_line,
         n.journal_entry_id is not null as posted
  from   fx_<suffix>_s.credit_notes n
  join   fx_<suffix>_s.credit_note_lines l  on l.credit_note_id = n.id and l.is_deleted = false
  join   fx_<suffix>_s.sales_invoice_lines il on il.id = l.sales_invoice_line_id;
  ```

### 11.18 Proforma — posts nothing and does not follow the order (TC-SELL-017)

- **Raise** (the order must be APPROVED, PARTIALLY_DELIVERED, DELIVERED or
  CLOSED) inserts `proforma_invoices` (DRAFT, `sales_order_id`, customer,
  branch and currency from the order, `payment_terms`, `delivery_terms`,
  `supersedes_id`) and `proforma_invoice_lines` **copied** from the order's
  lines (`source_sales_order_line_id`, quantity, price, `discount_percent`,
  `discount_amount`, `bill_discount_amount`, `gross_amount`, `tax_amount`,
  `net_amount`), totals summed from them. Lifecycle `PROFORMA.CREATED`; audit
  `proforma.created` (`proforma_number`, `status`, `sales_order_id`,
  `grand_total`).
- **Issue:** DRAFT → ISSUED, `issued_at`; lifecycle `PROFORMA.ISSUED`; audit
  `proforma.issued`. **Cancel:** `cancelled_at`, `cancel_reason`, audit
  `proforma.cancelled`.
- **Posts nothing, by design:** neither table has a `journal_entry_id` or a
  receivable link; no stock; the customer's balance does not move.
- **Snapshotted:** cancelling the order changes nothing on the proforma.
  Confirmed on `fx_t0916d751_s`: PI-2026-2027-000001 ISSUED at 291.4128 on
  SO-2026-2027-000002, which is CANCELLED; WHOLE01's PI-…-000004 and -000006
  the same.
- **Its totals leave out freight and the order's header charges** (D-SELL-16);
  the fixture's order has neither.
- **Check:**
  ```sql
  select p.proforma_number, p.status, p.issued_at, p.grand_total,
         o.order_number, o.status as order_status, o.grand_total as order_total
  from   fx_<suffix>_s.proforma_invoices p
  join   fx_<suffix>_s.sales_orders o on o.id = p.sales_order_id;
  ```
  No `journal_entries` row carries a proforma's id as `source_id`.

### 11.19 Loyalty — earn, spend, adjust, expire (TC-INCENT-005)

`loyalty_entries` is the whole scheme: `kind` `EARNED`, `REDEEMED`,
`EXPIRED`, `ADJUSTED` (and `REVERSED`, which nothing writes), signed
`points`, `amount`, `sales_invoice_id`, `earned_on`, `expires_on`,
`reverses_id`, `journal_entry_id`. **The balance is the sum of `points`**; no
column holds it. The settings are `loyalty_settings`, audit
`loyalty.settings_changed`.

- **Earn** — meant to happen at invoice approval: one `EARNED` row (points =
  grand total × `points_per_amount` / 100), a journal `LOY-SI-…`
  (`source_module` `loyalty`) **Dr 5700 Loyalty Expense / Cr 2600 Loyalty
  Payable**, audit `loyalty.earned`. **It is lost on every approval made
  through the API or the desktop** (D-SELL-1): no fixture store holds an
  `EARNED` row, and WHOLE01's invoices approved by hand on 2026-09-13
  (SI-…-000010 to 000013) have none while the 49 the seeder approved do. That
  is why TC-INCENT-005 reads exactly **200** — the invoice's 9.66 never
  arrived. Cancelling an invoice leaves any earned points and their journal
  standing (D-SELL-2; WHOLE01 SI-2026-2027-000008).
- **Adjust** (the fixture's 200): one `ADJUSTED` row, `amount` 0, `remarks`
  the reason; **posts nothing**; audit `loyalty.adjusted`. Adjusted points
  never expire.
- **Use points on an invoice** — the customer row locked: one `REDEEMED` row
  (negative points, `amount`, `sales_invoice_id`, `earned_on` = today UTC); a
  journal `LOY-RED-SI-…` **Dr 2600 Loyalty Payable / Cr 1100 Trade
  Receivables**, dated today UTC — 2026-09-15 for a 2026-09-16 invoice in
  `fx_t09164wau_s` (D-SELL-27); a receivable row `LOYALTY` (reference the SI
  number, remarks "100.0000 points spent on SI-…", no `reference_type`) —
  Outstanding 483.21 → **383.21**; audit `loyalty.redeemed`. The invoice's
  total and tax do not move: the bill is settled, not discounted, and what it
  still owes has the redeemed amount taken off. Spending goodwill points
  debits 2600 for value that was never accrued — `fx_t09164wau_s` reads
  **2600 at −100.00** (D-SELL-19) — and a second spend on the same bill is
  refused by the journal's unique reference (D-SELL-20).
- **Refused, nothing written:** "That customer holds 100.0000 points, not
  5000.0000."; under the minimum; more than the bill owes; a bill that is not
  approved.
- **Expire:** one `EXPIRED` row per lapsing batch for what is left of it,
  `reverses_id` the batch, journal `LOY-EXP-…` Dr 2600 / Cr 5700, audit
  `loyalty.expired`. Confirmed on WHOLE01 only.
- **Check:**
  ```sql
  select e.created_at, e.kind, e.points, e.amount, e.earned_on, e.expires_on,
         i.invoice_number, je.reference_number as journal, e.remarks
  from   fx_<suffix>_s.loyalty_entries e
  join   fx_<suffix>_s.customers c          on c.id = e.customer_id
  left join fx_<suffix>_s.sales_invoices i  on i.id = e.sales_invoice_id
  left join fx_<suffix>_s.journal_entries je on je.id = e.journal_entry_id
  where  c.code = '<SUFFIX>-C01'
  order  by e.created_at;

  select sum(points) as balance
  from   fx_<suffix>_s.loyalty_entries e
  join   fx_<suffix>_s.customers c on c.id = e.customer_id
  where  c.code = '<SUFFIX>-C01' and e.is_deleted = false;
  ```

### 11.20 The shortened chain — a stage switched to automatic (TC-FIN-009)

- **The setting** is one `sales_workflow_settings` row per firm
  (`quotation_stage`, `sales_order_stage`, `delivery_note_stage`,
  `default_branch_id`, `default_warehouse_id`); a firm with no row types
  every stage. Writing it needs `SALES_MANAGE_SETTINGS` and records audit
  **`CREATE`** / **`UPDATE`**, `entity_type` `SalesWorkflowSettings`, both
  sides in full (D-SELL-24).
- **Delivery-note stage off, bill the order:** the invoice's **create**
  raises, approves and dispatches the note itself, then bills it — all in the
  one request that saves the **draft** invoice. Confirmed on `fx_t09164wau_s`:
  one request at 03:34:30.913 wrote `delivery_note.created`,
  `delivery_note.approved`, `delivery_note.dispatched`, the `UNRESERVE` and
  `DISPATCH` of 4, the COGS journal of 240.00,
  `sales_order.delivered_status_changed` (APPROVED → DELIVERED),
  `sales_invoice.created` and two `tax.rule.simulated`; the invoice reads
  `allow_direct_sales_order` true. Approving it later is §11.11 unchanged.
- **So a draft bill has already moved the stock.** Cancelling that draft
  leaves the goods dispatched, their cost posted and the order DELIVERED, with
  no revenue behind them until the note is billed again (D-SELL-13).
- **Order and note stages both off, bare lines:** the create also raises and
  approves the order (credit check, reservation, claim) from the invoice's
  lines, at the firm's default branch and warehouse — refused if there is
  none ("This firm has no default branch, so a bill cannot decide where its
  goods ship from."). *(Not seen in a live row.)*
- **A firm on the whole chain** cannot bill an order directly ("This firm
  ships on a delivery note before it bills. Dispatch the order, or turn the
  delivery-note stage off.").
- **Check:**
  ```sql
  select quotation_stage, sales_order_stage, delivery_note_stage,
         default_branch_id, default_warehouse_id, updated_at
  from   fx_<suffix>_s.sales_workflow_settings;

  select i.invoice_number, i.status, i.allow_direct_sales_order, i.created_at,
         d.delivery_note_number, d.status as note_status, d.created_at as note_created
  from   fx_<suffix>_s.sales_invoices i
  join   fx_<suffix>_s.sales_invoice_sources s on s.sales_invoice_id = i.id
  join   fx_<suffix>_s.delivery_notes d        on d.id = s.source_document_id;
  ```
  The note and the invoice share a `created_at` to the microsecond.

### 11.21 What selling does not write, and is often looked for

| You might expect | What actually happens |
| --- | --- |
| A PAID status on a sales invoice | It stays APPROVED; what it owes is derived from POSTED allocations and redeemed points (§11.14) |
| A journal when an order is approved | None; a `RESERVE` and a CLAIMED row only (§11.5) |
| Revenue at dispatch, or cost of goods at invoice | The reverse: COGS at dispatch (§11.10), revenue at invoice approval (§11.11) |
| A lifecycle or history row when dispatch moves the order | Audit `sales_order.delivered_status_changed` only (§11.10) |
| An audit row for a promotion claim, or for a refused credit approval | None; the claim rides on `sales_order.approved`, and a block writes nothing (§11.5, §11.6) |
| The discount source on a note, invoice or return | Only quotation and order lines carry `discount_source` (§11.1) |
| `sales_invoice_accounting_events` being the journal | Placeholders written at create; the journal is `journal_entries` with `source_module` `sales_invoice` |
| The CGST/SGST split in the journal | One Output Tax line; the split is `sales_invoice_line_taxes` |
| A proforma journal or receivable | None, by design (§11.18) |
| Loyalty points from an approved invoice | Lost (D-SELL-1, §11.19) |
| A reversal dated the day of the cancel | Receipts, returns and invoices: the first of the period; credit notes: the note's date (D-BUY-4, D-SELL-27) |
| A credit note's APPROVED on its timeline | None; only CREATED (D-SELL-23) |
| Soft-deleted child rows | Order and note attachments and notes, dropped lines, every child of a draft invoice or return are **physically** deleted; a credit note's old lines are soft-deleted |

### 11.22 Checked against live rows, and not

- **Confirmed in `fx_t0916h2j3_s`** (TC-SELL-001 to 017 run by API on
  2026-09-16): every `discount_source` in §11.1; the quotation's CREATED → SENT
  → ACCEPTED → CONVERTED and the converted order reading `amount` / `typed`;
  PENDING claims for WELCOME10 and WELCOME10B and none for NOSUCHCODE; the
  CLAIMED row and the two-row approval; HELD and RELEASED with the reason
  kept; two dispatches of six audit rows each, the order PARTIALLY_DELIVERED
  then DELIVERED, COGS 300.00 and 420.00; the note line at 84 less 2.5%; the
  invoice's CGST/SGST rows, placeholders, receivable and journal Dr 1100 /
  Cr 4000 / Cr 2200; the receipts, TCS, the advance applied as 95.16 and the
  reversal's ten audit rows; the return's two journals and seven audit rows;
  the credit note at 18% with no APPROVED lifecycle and a null
  `reference_type`; an issued proforma; zero loyalty entries.
- **Confirmed in `fx_t0916d751_s`, `fx_t09164wau_s`, `fx_t0916z0ph_s`:** the
  `selling-paid` receipts and balances; the cancelled order's release dated
  the day before its reservation and its issued proforma unchanged; the
  goodwill adjustment, the 100-point spend dated UTC and 2600 at −100.00; the
  blocking policy with Anand's order left DRAFT and nothing else written; the
  automatic note raised and dispatched by a draft invoice's create; the
  `CREATE` audit rows for both settings tables.
- **Confirmed on WHOLE01:** a saved invoice print template with two copy
  labels; a completed return cancelled with its nine audit rows and two
  `-REV` journals on 2026-09-01; `EXPIRED` loyalty rows; earned points
  missing from the four invoices approved by hand and still standing on a
  cancelled one; proforma and purchase invoice numbers colliding; the
  REVERSED claims of a cancelled order; `outstanding_balance_snapshot` 0.00
  on orders whose customers owe thousands.
- **Not seen in a live row:** a quotation revision in a fixture store; a
  refused claim at its limit; a warned approval; a note dispatched while its
  order was held; a note closed without dispatch; an invoice from an
  undispatched note; an invoice closed from DRAFT or CANCELLED; a cancelled
  approved invoice with its receivable reversal in a fixture store; a
  delivered order cancelled; a cancelled credit note; a closed or edited
  return; a return against a note line already billed; a reversed receipt
  whose advance had been applied; a refund; a proforma on an order with
  freight; a bare-line bill with both stages off.
- **Where the selling rows are, 2026-09-19:** `fx_t0916h2j3_s` 6 quotations,
  5 orders, 2 notes, 2 invoices, 1 return, 1 credit note, 2 receipts, 1
  proforma; `fx_t0916d751_s` 2 orders, 2 notes, 2 invoices, 2 receipts, 1
  proforma; `fx_t09164wau_s` 7 orders, 3 notes, 2 invoices; `fx_t0916z0ph_s`
  2 orders; TEST01 9 orders, 7 notes, 9 invoices, 4 settlements from other
  fixtures; WHOLE01 as in §11.0.

---

## 12. Finance — the books themselves (TC-FIN-001 to 011)

Read on 2026-09-19 off `app/finance` — `finance_service.py` (years, periods,
groups, accounts, centres, journal and voucher types), `journal_engine.py`
(create, post, reverse, the ledger balances and their roll-forward),
`general_ledger_service.py` (trial balance, profit and loss, balance sheet,
ledger statement), `control_accounts.py`, `opening_setup.py`
(`seed_finance_setup`) and `document_posting.py` — and off the finance side of
`settlement_service.py`, `customer_service.py`, `statement_service.py`,
`app/firms/services/readiness.py` (`open_books`) and
`scripts/verify_sample_data.py`. Then checked, read-only, against every store
that holds a `journal_entries` table on the local server: the `ready-firm`
store TC-FIN-001, 003 and 007 were walked in (`fx_t0916hkkx_r`), the
`selling-paid` stores, TEST01 and WHOLE01. §12.16 says which claims a live row
confirmed and which it could not. A claim marked *(not seen in a live row)* was
read off the code only. The selling and buying money paths are §9.11–9.12 and
§11.14–11.15; this section does not repeat them.

### 12.0 Before you look

- **Stores.** The cases that change a firm's books run in a store of the
  run's own:

  | Case | Fixture | Schema |
  | --- | --- | --- |
  | TC-FIN-001, 003, 007 | `ready-firm` | **`fx_<suffix>_r`** — firm `<SUFFIX>-R`, "Ready <suffix>" |
  | TC-FIN-002, 004, 005 | `selling-paid` | `fx_<suffix>_s` |
  | TC-FIN-008, 009 | `policy-firm` | `fx_<suffix>_s` — §11.6 and §11.20 |
  | TC-FIN-006 | `product-master` | `test_fixtures` |
  | TC-FIN-010, 011 | `firm-admin`, `platform-admin` | `platform` |

  A `ready-firm` store starts with the default chart (24 accounts, 1000 Cash,
  5000 Purchases, no 9999), one financial year of 12 OPEN periods, the 24
  control-account mappings, a customer `FXCUST` and one receipt of 500.00
  cash (`RC-2026-2027-000001`, Dr 1000 / Cr 1100) that locks the Cash and
  Accounts receivable mappings. `fx_t0916hkkx_r` is the one TC-FIN-001, 003
  and 007 were walked in on 2026-09-16; its firm has since been soft-deleted
  by a clear and its schema stays.
- **All finance audit rows go to the firm's own trail.** No `finance.*` row
  exists in `platform.audit_logs` (checked 2026-09-19: zero). The one
  platform row is `firm.books_opened` (§12.1).
- **Three layers, and what reads which.**

  | Table | One row per | Written when | Read by |
  | --- | --- | --- | --- |
  | `journal_entries` | voucher | created (DRAFT); `status`, `posted_at` on post; `status` REVERSED when reversed | Journal Entries screen |
  | `journal_lines` | leg | with the entry, never edited | the entry's View; the ledger statement's narration |
  | `gl_postings` | leg, as posted | on post, one per line, `status` always POSTED | ledger statement; `verify_sample_data.py` |
  | `ledger_balances` | account × period | on post: inserted the first time an account moves in a period, then updated | trial balance, P&L, balance sheet, account summaries |

  **No report sums `journal_lines`.** A line that never posted (a draft) is
  on no report. `customer_ledgers` and `vendor_ledgers` exist and nothing
  writes either — zero rows in every store.
- **Money is two decimals** in every finance table. The engine rounds each
  leg to 0.01 before it checks the entry balances, so the stored legs are the
  ones that balance.
- **Journal and voucher type.** Every document posts under the firm's
  alphabetically first journal type and first voucher type — `GEN` / `JV` in
  every store — so the type says nothing about which module posted. The
  module is `journal_entries.source_module`; a hand-keyed entry has
  `source_module` and `source_id` null.
- **One click, all its audit rows** — the §9.0 request-id query works
  unchanged with the store's schema and the action you took
  (`finance.accounting_period.updated`, `finance.journal_entry.posted`).
- **What points at what:**

  | From | Column | To |
  | --- | --- | --- |
  | `accounting_periods` | `financial_year_id` | `financial_years` |
  | `ledger_accounts` | `account_group_id` | `account_groups` (`parent_group_id` on a group) |
  | `journal_entries` | `journal_type_id`, `voucher_type_id`, `accounting_period_id`; `reversal_of_id` on a reversal | — |
  | `journal_entries` | `source_module` + `source_id` — **no foreign key** | the document (§12.5) |
  | `journal_lines` | `ledger_account_id`, `cost_center_id`, `profit_center_id` | `ledger_accounts`, `cost_centers`, `profit_centers` |
  | `gl_postings` | `journal_entry_id`, `journal_line_id`, `ledger_account_id`, `accounting_period_id` | — |
  | `ledger_balances` | `ledger_account_id`, `accounting_period_id` (unique together) | — |
  | `firm_control_accounts` | `purpose` → `ledger_account_id` (unique per firm and purpose) | `ledger_accounts` |
  | `customer_receivable_transactions` | `journal_entry_id` — set **only** on `OPENING_BALANCE` rows | `journal_entries` |

### 12.1 Open the books — the year, its periods, the chart (Firms → Set up → Open the books)

`POST /api/v1/firms/{id}/open-books` is platform-only and runs
`seed_finance_setup` against the **firm's** store. §6 has the platform half;
this is the firm half.

- **Inserts** (store: the firm's), each only if missing — by code, or by
  year start and period number:
  - `account_groups` **5**: CA Current Assets (ASSET), CL Current Liabilities
    (LIABILITY), REV Revenue (INCOME), EXP Direct Expenses (EXPENSE), EQ Equity
    (EQUITY);
  - `ledger_accounts` **24**: 1000 Cash, 1010 Bank, 1100 Trade Receivables,
    1200 Inventory, 1300 Input Tax, 2100 Trade Payables, 2200 Output Tax,
    2300 Goods Received Not Invoiced, 2400 Commission Payable, 2500 TCS
    Payable, 2600 Loyalty Payable, 3000 Opening Balance Equity, 4000 Sales,
    4100 Sales Returns, 4200 Discount Received, 4900 Rounding, 5000 Purchases,
    5100 Purchase Returns, 5200 Cost of Goods Sold, 5300 Discount Allowed,
    5400 Purchase Price Variance, 5500 Inventory Adjustment, 5600 Commission
    Expense, 5700 Loyalty Expense. `is_profit_loss` follows the type (INCOME
    and EXPENSE true), `is_balance_sheet` its opposite;
  - `financial_years` **1**: the year today (UTC) falls in, aligned to
    `firms.financial_year_start` — code `FY2026`, name "Financial Year
    2026-2027", `is_active` true, `is_locked` false;
  - `accounting_periods` **12**: `period_number` 1–12, `code` `P01`…`P12`,
    `name` "April 2026"…"March 2027", calendar months, `status` OPEN;
  - `journal_types` `GEN` General and `voucher_types` `JV` Journal Voucher;
  - `firm_control_accounts` **24**, one per purpose (§12.7).
- **Audit, firm trail — 44 rows in one request:** `finance.account_group.created`
  ×5, `finance.ledger_account.created` ×24, `finance.financial_year.created`,
  `finance.accounting_period.created` ×12, `finance.journal_type.created`,
  `finance.voucher_type.created`. **The 24 mappings write no audit row** —
  `assign` records none (D-FIN-13).
- **Audit, platform trail:** `firm.books_opened`, `after_data` =
  `year_starts_on` and the counts (`groups` 5, `accounts` 24, `periods` 12,
  `types` 2, `mappings` 24). **Only when something was created**; a second
  press writes nothing and answers `already_open`.
- **Only the current year.** No screen creates a financial year or a period:
  the Financial Years page lists, closes and reopens. The next year is opened
  by pressing Open the books again on or after its first day, or by
  `POST /firms/{id}/open-books` with `year_starts_on` (platform-only), or by
  `POST /finance/financial-years` and twelve `POST /finance/accounting-periods`
  (`FINANCIAL_YEAR_CREATE`). A document dated in a year not yet opened is
  refused: "No open accounting period covers 2027-04-02. Open the period
  before approving documents dated in it."
- **Check** (fresh store: `5, 24, 1, 12, 1, 1, 24`):
  ```sql
  select (select count(*) from fx_<suffix>_r.account_groups        where is_deleted = false) as groups,
         (select count(*) from fx_<suffix>_r.ledger_accounts       where is_deleted = false) as accounts,
         (select count(*) from fx_<suffix>_r.financial_years       where is_deleted = false) as years,
         (select count(*) from fx_<suffix>_r.accounting_periods    where is_deleted = false) as periods,
         (select count(*) from fx_<suffix>_r.journal_types         where is_deleted = false) as journal_types,
         (select count(*) from fx_<suffix>_r.voucher_types         where is_deleted = false) as voucher_types,
         (select count(*) from fx_<suffix>_r.firm_control_accounts where is_deleted = false) as mapped;

  select y.code as year, y.is_locked, p.period_number, p.code, p.name,
         p.starts_on, p.ends_on, p.status, p.version
  from   fx_<suffix>_r.accounting_periods p
  join   fx_<suffix>_r.financial_years y on y.id = p.financial_year_id
  where  p.is_deleted = false
  order  by p.starts_on;
  ```

### 12.2 Close, reopen or lock a period (TC-FIN-003 steps 2, 4, 5)

Masters → Configuration → Financial Years → the year → a period → **Close** /
**Open**. Both are `PATCH /api/v1/finance/accounting-periods/{id}` with
`{"status": …}`, permission `FINANCIAL_YEAR_CLOSE`.

- **Updates:** `accounting_periods.status` OPEN → CLOSED (or back),
  `updated_by`, `version` +1. Nothing else moves: no journal, no balance, no
  change to the year.
- **Audit:** `finance.accounting_period.updated`, `before_data` and
  `after_data` = `status` and `name` only. Two rows for a close and a reopen,
  one request each. **The platform trail has none** (TC-FIN-003 step 5).
- **What a CLOSED or LOCKED period refuses:** a manual entry dated in it at
  **create** ("Accounting period P03 is closed and cannot accept postings.")
  and at **post** (the same sentence — the check is repeated, so a draft
  saved while June was open cannot be posted after June closed); every
  document approval, dispatch, receipt or return dated in it ("No open
  accounting period covers 2026-06-15. …"). A **reversal** of anything
  posted in a closed period goes into the period open on the day it happens
  (§12.4), so a cancellation is never refused for that reason alone.
- **What it does not stop:** a posting into an **earlier** open period still
  moves the closed period's stored opening and closing (§12.8), because
  periods can be closed in any order.
- **LOCKED** is an API-only status (the desktop offers Close and Open only).
  A locked period refuses every edit except being reopened — so a lock is a
  close that also freezes the name and dates, and `FINANCIAL_YEAR_CLOSE`
  undoes it.
- **A locked financial year locks nothing.** `financial_years.is_locked`
  (API only, `PATCH /finance/financial-years/{id}` with `is_locked`) is read
  only by the year's own edit and delete. Its periods can still be closed,
  reopened and posted into through the API; only the desktop hides Close and
  Open under a locked year. And once set it cannot be unset — the same PATCH
  refuses "A locked financial year cannot be modified." (D-FIN-3). No year is
  locked in any store.
- **Dates:** the same PATCH accepts `starts_on` / `ends_on` and checks only
  that the end follows the start — not that the period stays inside its year,
  does not overlap another, or still covers the entries already in it
  (D-FIN-6).
- **Check:**
  ```sql
  select p.code, p.name, p.status, p.version, p.updated_at
  from   fx_<suffix>_r.accounting_periods p
  where  p.name = 'June 2026';

  select created_at, action, before_data->>'status' as was, after_data->>'status' as now
  from   fx_<suffix>_r.audit_logs
  where  action = 'finance.accounting_period.updated'
  order  by created_at;
  ```
- **Confirmed** in `fx_t0916hkkx_r`: June 2026 closed at 22:03:07 UTC and
  reopened at 22:03:12, two audit rows (OPEN → CLOSED, CLOSED → OPEN);
  `MT-CLOSE-2`, created at 22:03:05 while June was open, posted at 22:03:14
  after the reopen. WHOLE01 holds the same pair for June 2026 (2026-09-14) and
  for April 2024. No period in any store is CLOSED today.

### 12.3 Create and edit a ledger account (TC-FIN-001)

Finance → Chart of Accounts → New / Edit. `POST` and
`PATCH /api/v1/finance/ledger-accounts`, permission `ACCOUNT_MANAGE`.

- **Create inserts** one `ledger_accounts` row: `account_group_id`, `code`
  (upper-case letters, digits, `_` and `-`, up to 20), `name`,
  `account_type`, `description`, `is_balance_sheet` / `is_profit_loss`
  (following the type unless sent), `requires_cost_center`,
  `requires_profit_center`, `is_active`. **Audit:**
  `finance.ledger_account.created` (`code`, `account_type`).
- **Refused, nothing written:** a group of another type ("A ledger account
  must share its group's account type." — the REV chip with type EXPENSE);
  a code the firm already has ("A ledger account with this code already
  exists."); a group that is not the firm's ("Account group not found.").
- **Edit updates** `name`, `description`, the two statement flags, the two
  "Requires a …" flags, `is_active`, and — through the API only — the group,
  provided the new group has the same type. **`code` and `account_type`
  cannot change**; the update schema does not carry them. `version` +1.
- **Audit:** `finance.ledger_account.updated`, **both sides `name` and
  `is_active` only** — ticking "Requires a cost centre" writes a row whose
  before and after read the same (D-FIN-13).
- **No delete.** There is no delete endpoint for an account, a group, a
  centre, a journal type or a voucher type; **Active** is the only way out.
  Deactivating an account mapped to a posting purpose is not refused, and
  every document of that purpose then fails at approval with "Ledger accounts
  are inactive: 1100." (D-FIN-8).
- **Account groups** (`POST` / `PATCH /finance/account-groups`) write
  `finance.account_group.created` / `.updated`. A new group with a parent
  must share the parent's type; an edit that changes the parent checks
  neither the type nor a cycle.
- **Check:**
  ```sql
  select a.code, a.name, a.account_type, g.code as grp, a.is_balance_sheet, a.is_profit_loss,
         a.requires_cost_center, a.requires_profit_center, a.is_active, a.version
  from   fx_<suffix>_r.ledger_accounts a
  join   fx_<suffix>_r.account_groups g on g.id = a.account_group_id
  where  a.code in ('9999', '5000')
  order  by a.code;
  ```
- **Confirmed** in `fx_t0916hkkx_r`: 9999 Manual test account, EXPENSE, group
  EXP, `is_profit_loss` true, version 1 — 25 accounts; 5000 at version 3
  after the flag was ticked and unticked, with two
  `finance.ledger_account.updated` rows reading `{"name": "Purchases",
  "is_active": true}` on both sides.

### 12.4 A manual journal — draft, post, reverse (TC-FIN-003 steps 1, 3, 4)

Finance → Journal Entries → **New Entry** → **Save Draft**, then **Post**; or
**Reverse** on a posted one.

- **Save Draft** — `POST /api/v1/finance/journal-entries`,
  `JOURNAL_CREATE`. **Inserts** `journal_entries` (`status` DRAFT,
  `journal_date`, `reference_number` as typed, `description`, `remarks`,
  `total_debit` = `total_credit`, `is_balanced` true, `source_module` and
  `source_id` null, `posted_at` null) and one `journal_lines` row per leg
  (`line_number` from 1, `debit_amount` or `credit_amount`, the centres, a
  narration). **Audit:** `finance.journal_entry.created`
  (`reference_number`, `total_debit`, `total_credit`). **No posting and no
  balance** — a draft is on no report.
- **Refused at save, nothing written:** fewer than two lines; a line with
  both sides or neither; debits ≠ credits ("Journal entry is not balanced:
  debit 100, credit 90."); a zero entry; a date outside the chosen period
  ("The journal date must fall inside the accounting period."); a period not
  OPEN; an account that is inactive ("Ledger accounts are inactive: 5000.")
  or not the firm's; a missing centre on an account that requires one
  (§12.6); a journal or voucher type not the firm's; a reference the firm
  already has ("A journal entry with this reference number already exists.").
  **References are unique across every journal the firm holds, documents'
  included** (D-FIN-9).
- **Not refused at save:** a line on an account a document keeps in step
  with something else — 1100 against the customers, 1200 against the stock,
  2300 against uninvoiced receipts. A hand Dr 1100 moves the receivable
  account with no customer owing it (D-FIN-11).
- **Post** — `POST /journal-entries/{id}/post`, `JOURNAL_POST`.
  **Updates** `journal_entries.status` → POSTED, `posted_at` = now (UTC),
  `version` +1. **Inserts** one `gl_postings` row per line (`posting_date` =
  the same instant, the entry's period, `status` POSTED, `posted_by`).
  **Inserts or updates** one `ledger_balances` row per account for the
  entry's period, and moves every **later** period's stored row for the same
  account (§12.8). **Audit:** `finance.journal_entry.posted` (DRAFT →
  POSTED). Refused: an entry not DRAFT ("Only draft entries can be posted;
  this entry is posted."); a period closed since the draft was saved.
- **Reverse** — `POST /journal-entries/{id}/reverse`, `JOURNAL_REVERSE`.
  **Inserts** a new entry — lines flipped, `reversal_of_id` = the original,
  **the original's `source_module` and `source_id` copied**, description
  "Reversal of MT-CLOSE-1" — and posts it at once (created and posted in one
  request, with its postings and balances). **Updates** the original's
  `status` → REVERSED. **Audit:** `finance.journal_entry.created`,
  `.posted`, and `.reversed` on the original (`reversal_entry_id`).
  - **Its date.** The desktop's Reverse sends the original's period and date,
    so a hand reversal lands **beside the original**, in its period — and is
    refused if that period is closed. Called without them, the engine uses
    **today in UTC**, in the period open on that day, or the original's own
    date if no period is open today. This is what every document cancellation
    does since D-BUY-4 (#442, 2026-09-18); rows written before it read the
    first day of the original's period, which is what §9.6, §9.12 and §11.15
    saw. **Today in UTC is the day before in India until 05:30**, so a bill
    dated and cancelled in those hours reverses the day before it was raised
    (D-FIN-5).
  - **Any posted entry can be reversed here, a document's included** — the
    desktop offers Reverse on every POSTED row. The document is left as it
    was, its receivable and its stock with it (D-FIN-2).
  - Refused: an entry not POSTED ("Only posted entries can be reversed.").
- **No edit, no delete, no reject** for a draft: `JournalEntryUpdate` is
  declared and no route uses it, and `REJECTED` is never written. A mistaken
  draft keeps its reference for good (D-FIN-15).
- **Check** — the entry, its lines, their postings, and what the accounts hold
  in its period:
  ```sql
  select je.reference_number, je.status, je.journal_date, p.code as period, p.status as period_status,
         je.posted_at, je.reversal_of_id, jl.line_number, la.code, jl.debit_amount, jl.credit_amount,
         cc.code as cost_centre, pc.code as profit_centre, g.posting_date
  from   fx_<suffix>_r.journal_entries je
  join   fx_<suffix>_r.accounting_periods p on p.id = je.accounting_period_id
  join   fx_<suffix>_r.journal_lines jl     on jl.journal_entry_id = je.id
  join   fx_<suffix>_r.ledger_accounts la   on la.id = jl.ledger_account_id
  left join fx_<suffix>_r.cost_centers cc   on cc.id = jl.cost_center_id
  left join fx_<suffix>_r.profit_centers pc on pc.id = jl.profit_center_id
  left join fx_<suffix>_r.gl_postings g     on g.journal_line_id = jl.id
  where  je.source_module is null
  order  by je.created_at, jl.line_number;
  ```
  A DRAFT row shows a null `posting_date`; a POSTED one, one posting per line.
- **Confirmed** in `fx_t0916hkkx_r`: `MT-CLOSE-1`, `MT-CC-1`, `MT-CLOSE-2`,
  each Dr 5000 / Cr 1000, `source_module` null, `GEN`/`JV`; the two June ones
  in P03. No hand reversal exists in any store.

### 12.5 Journals the documents post (TC-FIN-004)

Journal Entries lists every entry; the View dialog's first line is "POSTED ·
posted by <source_module> · <description>". The posting rules are
`docs/LEDGER_POSTING_RULES.md`; the per-document rows are §9 (buying), §10
(stock) and §11 (selling). This is the map from what you see to where it came
from, read off WHOLE01's and TEST01's live journals:

| `source_module` | Reference | Legs (default chart) | Written by |
| --- | --- | --- | --- |
| `goods_receipt` | `GRN-…` | Dr 1200 / Cr 2300 | completing a receipt (§9.5) |
| `purchase_invoice` | `PI-…` | Dr 2300 + 1300 (± 5400) / Cr 2100 (± 5400) | approving a supplier bill (§9.9) |
| `purchase_return` | `PR-…` | Dr 2100 / Cr 1200 + 1300 (± 5400) | completing a return (§9.10) |
| `delivery_note` | `DN-…` | Dr 5200 / Cr 1200 | dispatch (§11.10) |
| `sales_invoice` | `SI-…` | Dr 1100 / Cr 4000 + 2200 | approving a bill (§11.11) |
| `sales_return` | `SR-…`, `SR-…-COST` | Dr 4100 + 2200 / Cr 1100; Dr 1200 / Cr 5200 | completing a return (§11.16) |
| `credit_note` | `CN-…` | Dr 4100 + 2200 / Cr 1100 | approving a credit note (§11.17) |
| `settlements` | `RC-…`, `PY-…`, `RF-…` | Dr 1010 or 1000 / Cr 1100; Dr 2100 / Cr 1010 or 1000; Dr 1100 / Cr 1010 or 1000 | receipt, payment, refund (§12.12) |
| `tcs` | `TCS-RC-…` | Dr 1100 / Cr 2500 | a receipt past the threshold (§11.14) |
| `loyalty` | `LOY-SI-…`, `LOY-RED-SI-…`, `LOY-EXP-…` | Dr 5700 / Cr 2600; Dr 2600 / Cr 1100; Dr 2600 / Cr 5700 | earn, spend, expire (§11.19) |
| `commission` | `COMM-…`, `COMM-…-PAY` | Dr 5600 / Cr 2400; Dr 2400 / Cr 1000 or 1010 | approving and paying a payout |
| `inventory` | the movement's or batch's reference | Dr 5500 / Cr 1200 (or back); Dr 1200 / Cr 3000 for opening stock | write-off, adjustment, opening stock (§10.3, §12.11) |
| `physical_count` | the count number | Dr 5500 / Cr 1200 (or back) | posting a count (§10.5) |
| `customers` | `<code>-OB` | Dr 1100 / Cr 3000 (swapped for a credit balance) | a customer's opening balance (§12.11) |
| null | as typed | as typed | a hand entry (§12.4) |

- A reversal carries the **same** `source_module` and `source_id` as what it
  reverses, a reference ending `-REV`, and `reversal_of_id`; the original
  reads REVERSED. **Look a document's live journal up with
  `reversal_of_id is null`**, or you find its reversal too.
- **The search matches reference or description; there is no module filter**
  (BL-31.15).
- **Check** (the four TC-FIN-004 looks for, in the selling store):
  ```sql
  select je.reference_number, je.status, je.source_module, je.journal_date, je.description,
         je.total_debit, je.reversal_of_id
  from   fx_<suffix>_s.journal_entries je
  where  je.reference_number in ('SI-2026-2027-000001', 'RC-2026-2027-000001', 'TCS-RC-2026-2027-000001')
     or  je.reference_number like 'DN-%'
  order  by je.created_at;
  ```
- **Confirmed** in `fx_t0916d751_s` (`selling-paid`): `T0916D751-OS`
  (`inventory`), two `DN-` (`delivery_note`, 300.00 and 420.00),
  `SI-2026-2027-000001` / `-000002` (`sales_invoice`, 483.21 / 676.49),
  `RC-…-000001` / `-000002` (`settlements`, 241.60 / 341.61), `TCS-RC-…`
  (`tcs`, 2.42 / 3.42) — nine entries, all POSTED, all `GEN`/`JV`.

### 12.6 Cost and profit centres, and an account that demands one (TC-FIN-007)

- **New centre** — `POST /finance/cost-centers` or `/profit-centers`,
  `ACCOUNT_MANAGE`. **Inserts** `cost_centers` / `profit_centers` (`code`,
  `name`, `description`, `is_active`). **Audit:**
  `finance.cost_center.created` / `finance.profit_center.created` (`code`).
  A second SALES is refused with "A cost centre with this code already
  exists." and writes nothing.
- **Edit** updates `name`, `description`, `is_active`. **Audit:**
  `finance.cost_center.updated` / `.profit_center.updated`, `after_data`
  `name` and `is_active`, **no `before_data`**. No delete endpoint.
- **"Requires a cost centre"** is `ledger_accounts.requires_cost_center`
  (§12.3). It is enforced **when a journal is created** — a hand entry, and
  every document journal too: a document posting to an account that demands
  a centre is refused, since documents never name one — and not re-checked
  at post, so a draft saved before the flag was ticked still posts.
  Refused: "Ledger account 5000 requires a cost centre." (422, and nothing
  written).
- **A line's centre is checked for presence only** — not that it is the
  firm's, live or active. In the shared store another firm's centre is
  accepted; in a store of its own an unknown id fails the foreign key and is
  reported as "A journal entry with this reference number already exists."
  (D-FIN-12).
- **No report reads a centre.** `journal_lines.cost_center_id` /
  `profit_center_id` are written and shown on the entry; the trial balance,
  P&L and balance sheet ignore them.
- **Check:**
  ```sql
  select 'cost' as kind, code, name, is_active, version from fx_<suffix>_r.cost_centers
  union all
  select 'profit', code, name, is_active, version from fx_<suffix>_r.profit_centers;

  select je.reference_number, la.code, la.requires_cost_center, cc.code as cost_centre, pc.code as profit_centre
  from   fx_<suffix>_r.journal_lines jl
  join   fx_<suffix>_r.journal_entries je  on je.id = jl.journal_entry_id
  join   fx_<suffix>_r.ledger_accounts la  on la.id = jl.ledger_account_id
  left join fx_<suffix>_r.cost_centers cc   on cc.id = jl.cost_center_id
  left join fx_<suffix>_r.profit_centers pc on pc.id = jl.profit_center_id
  where  je.source_module is null;
  ```
- **Confirmed:** `fx_t0916hkkx_r` holds SALES (audit
  `finance.cost_center.created`) and no profit centre; `MT-CC-1` there was
  posted before the flag was ticked and carries none. WHOLE01's `MT-CC-1`
  carries SALES on its 5000 line; `JV-CENTRES-1` in WHOLE01 and in both
  shared-store firms carries SALES / NORTH on 5300, each firm's own.

### 12.7 Control accounts — which account a document posts to

Finance → Control Accounts. `GET /finance/control-accounts` lists all 24
purposes, mapped or not, with the account and `posted_lines` (POSTED lines
already on it). `PUT /finance/control-accounts/{purpose}` with
`ledger_account_id`, `ACCOUNT_MANAGE`.

- **Purposes:** ACCOUNTS_RECEIVABLE 1100, ACCOUNTS_PAYABLE 2100,
  SALES_REVENUE 4000, SALES_RETURNS 4100, PURCHASE_EXPENSE 5000,
  PURCHASE_RETURNS 5100, OUTPUT_TAX 2200, INPUT_TAX 1300, INVENTORY 1200,
  GOODS_RECEIVED_NOT_INVOICED 2300, COST_OF_GOODS_SOLD 5200,
  PURCHASE_PRICE_VARIANCE 5400, INVENTORY_ADJUSTMENT 5500,
  OPENING_BALANCE_EQUITY 3000, DISCOUNT_ALLOWED 5300, COMMISSION_EXPENSE 5600,
  COMMISSION_PAYABLE 2400, TCS_PAYABLE 2500, LOYALTY_EXPENSE 5700,
  LOYALTY_PAYABLE 2600, DISCOUNT_RECEIVED 4200, ROUNDING 4900, CASH 1000,
  BANK 1010 — as the default chart maps them.
- **Re-point** updates `firm_control_accounts.ledger_account_id` (or inserts
  the row for an unmapped purpose), `version` +1. **Audit:**
  `control_account.assigned`, `before_data.ledger_account_id` the old account,
  `after_data` the purpose and the new one.
- **Refused, nothing written:** an account not the firm's; the wrong type for
  the purpose ("SALES_REVENUE must post to a INCOME account, but 5000 is
  EXPENSE."); re-pointing a purpose whose current account already holds
  POSTED lines ("Accounts receivable has 1 posted line on 1100 Trade
  Receivables. Re-pointing it would …"). Choosing the same account again
  is accepted and still writes an audit row.
- **Not refused:** an **inactive** account (the docstring says it is;
  D-FIN-8); a **CONTROL**-type account for the receivable, payable, tax,
  GRNI, commission, TCS or loyalty purposes, which the balance sheet then
  leaves out (D-FIN-7).
- **A purpose with no mapping** refuses the document that needs it: "This
  firm has no ledger account configured for: ACCOUNTS_RECEIVABLE. Set the
  firm's control accounts before approving this document."
- **Check:**
  ```sql
  select c.purpose, la.code, la.name, la.account_type, la.is_active, c.version, c.updated_at,
         (select count(*) from fx_<suffix>_r.journal_lines jl
          join fx_<suffix>_r.journal_entries je on je.id = jl.journal_entry_id
          where jl.ledger_account_id = la.id and je.status = 'POSTED') as posted_lines
  from   fx_<suffix>_r.firm_control_accounts c
  join   fx_<suffix>_r.ledger_accounts la on la.id = c.ledger_account_id
  where  c.is_deleted = false
  order  by c.purpose;
  ```
- **Confirmed** on WHOLE01: two `control_account.assigned` rows on
  2026-09-08 moving PURCHASE_EXPENSE away and back. Every store maps all 24,
  none to an inactive account.

### 12.8 Ledger balances — how a posting rolls forward, and a back-dated one

`ledger_balances` is the stored figure every statement reads, one row per
account per period the account has **moved in**.

- **First posting to an account in a period inserts** the row with
  `opening_balance` = the closing of the account's latest earlier row (0 if
  none), then adds the line: `period_debit` / `period_credit` += the leg,
  `closing_balance` = opening + movement on the account's normal side (debit
  for ASSET and EXPENSE, credit for everything else, CONTROL included).
- **Every later period's row for that account moves too:** `opening_balance`
  and `closing_balance` += the line's movement; `period_debit` /
  `period_credit` stay as they were. A **back-dated** entry — a June journal
  posted in September, a bill dated last month cancelled today — therefore
  leaves every later month chained. Rows in CLOSED periods move as well.
- **A period an account did not move in has no row.** The trial balance and
  balance sheet supply it in memory from the latest earlier closing and never
  write it (§12.9).
- **Nothing is ever deleted or recomputed from scratch.** A reversal is a
  second posting in its own period, so the original's period keeps its
  movement and the reversal's period gains the opposite.
- **Balances run across years.** No year-end closing entry is written, so
  INCOME and EXPENSE accounts carry into the next year's first period; the
  P&L resets at the year by reading movement, and the balance sheet computes
  retained earnings (§12.9).
- **Check** — each row should open where the one before it closed:
  ```sql
  select a.code, p.code as period, p.name, b.opening_balance, b.period_debit, b.period_credit,
         b.closing_balance,
         lag(b.closing_balance) over (partition by b.ledger_account_id order by p.ends_on) as previous_close,
         b.version, b.updated_at
  from   fx_<suffix>_r.ledger_balances b
  join   fx_<suffix>_r.ledger_accounts a    on a.id = b.ledger_account_id
  join   fx_<suffix>_r.accounting_periods p on p.id = b.accounting_period_id
  order  by a.code, p.starts_on;
  ```
- **Confirmed** in `fx_t0916hkkx_r`: 1000 Cash's September row was inserted at
  19:27 UTC by the receipt (opening 0, Dr 500); the two June entries posted
  from 22:02 inserted a June row (Cr 200 → −200.00) and moved September's
  opening to **−200.00** and closing to **290.00** (version 5). 5000's
  September row opens at 200.00 — June's close. The chain holds in every
  store on the server (zero rows opening away from the previous close) and
  every period's postings balance.

### 12.9 Trial balance, profit and loss, balance sheet, ledger statement — reads (TC-FIN-002)

All four **write nothing**, not even an audit row. Each takes one
`accounting_period_id`.

| Report | Route (permission) | Reads |
| --- | --- | --- |
| Trial balance | `GET /finance/trial-balance` (`TRIAL_BALANCE_VIEW`) | the period's `ledger_balances` rows, plus every account whose latest earlier row closed non-zero (built in memory); `ledger_accounts` |
| Profit and loss | `GET /finance/profit-loss` (`PROFIT_LOSS_VIEW`) | `ledger_balances` of INCOME and EXPENSE accounts in the period's **financial year** up to and including the period — movement (`period_debit` / `period_credit`), never closings |
| Balance sheet | `GET /finance/balance-sheet` (`BALANCE_SHEET_VIEW`) | the trial balance's rows; ASSET, LIABILITY and EQUITY listed; INCOME and EXPENSE netted into earnings; MEMO and CONTROL left out; the P&L for the year's result |
| Ledger statement | `GET /finance/general-ledger/{account}` (`LEDGER_VIEW`) | the account's `ledger_balances` row (or the carried closing), and its `gl_postings` in the period joined to the entry and line, in journal-date order |

- **Trial balance.** One line per account: Opening, Debit, Credit, Closing —
  Debit and Credit are the **period's movement**. The Total row and the
  Balanced chip compare the **closing balances split by side** (a debit-side
  account's positive closing is a debit, and so on), **not** the sum of the
  Debit and Credit columns above them (D-FIN-18). Accounts with a zero
  carried balance and no movement are omitted.
- **Profit and loss.** Income and Expenses, each line with "This period"
  (movement in the period) and "Year to date"; an account with neither is
  omitted. Sections follow `account_type`, not `is_profit_loss`. 4100 Sales
  Returns is an INCOME account, so a return shows as a negative income line.
- **Another firm's period is not refused.** All four read the period by id
  without checking it is the firm's, so in the shared store one firm can ask
  for a report on the other's period and gets its own figures, dated by the
  other's calendar, instead of "not found" (D-FIN-14).
- **Balance sheet.** Total assets = liabilities + equity, where equity =
  the EQUITY accounts + **retained earnings brought forward** (every earlier
  year's net, computed) + **result for the year** (= the P&L's year-to-date
  net for the same period). Nothing is posted to make it balance.
- **Check** — the three statements from the stored rows (September 2026 in
  the selling store; any period code works):
  ```sql
  with p as (select id, starts_on, ends_on, financial_year_id
             from fx_<suffix>_s.accounting_periods where code = 'P06' and is_deleted = false),
  latest as (
    select distinct on (b.ledger_account_id) a.code, a.account_type, b.closing_balance
    from   fx_<suffix>_s.ledger_balances b
    join   fx_<suffix>_s.accounting_periods ap on ap.id = b.accounting_period_id
    join   fx_<suffix>_s.ledger_accounts a     on a.id = b.ledger_account_id, p
    where  ap.ends_on <= p.ends_on
    order  by b.ledger_account_id, ap.ends_on desc)
  select sum(case when account_type = 'ASSET'     then closing_balance else 0 end) as assets,
         sum(case when account_type = 'LIABILITY' then closing_balance else 0 end) as liabilities,
         sum(case when account_type = 'EQUITY'    then closing_balance else 0 end) as equity,
         sum(case when account_type = 'INCOME'  then closing_balance
                  when account_type = 'EXPENSE' then -closing_balance else 0 end)  as earnings_to_date,
         string_agg(code || ' ' || closing_balance, ', ' order by code)             as accounts
  from   latest;
  ```
  Assets should equal liabilities + equity + earnings to date.
- **Confirmed** in `fx_t0916d751_s` (`selling-paid`, untouched), September
  2026: trial balance 7,165.54 each side; assets 6,445.54 = liabilities
  182.74 + equity 6,000.00 + earnings 262.80; P&L 4000 982.80 less 5200
  720.00 = **262.80** this period and year to date, so result for the year
  262.80 and nothing brought forward. The Debit column of that trial balance
  sums to 8,468.75 — the month's postings — beside a Total of 7,165.54.
  WHOLE01 September: 496,202.07 = 458,173.01 + 0 + 38,029.06, with −4,194.86
  for the year to date and 42,223.92 brought forward from earlier years.
  TEST01: 46,738.00 = 7,198.00 + 42,000.00 − 2,460.00.

### 12.10 Customer statement and ageing — reads (TC-CUST-005)

Neither writes anything. Both read `customer_receivable_transactions`
(§11.0), never the journal.

- **Statement** — `GET /customers/{id}/statement?from_date=&to_date=`
  (`CUSTOMER_VIEW`). Opening = the sum of `outstanding_delta` on the
  customer's rows dated before `from_date`; lines = the rows dated in the
  range, ordered by `transaction_date`, then `created_at`, then `id`; the
  running balance is recomputed, never read off `outstanding_after`.
  `unapplied_advance` is the customer's current advance, beside it rather
  than netted. **A reversal row carries the date of what it reverses**, not
  the day it happened, while its journal carries the cancel date — so a
  statement for a month already sent changes when something in it is
  cancelled later (D-FIN-17).
- **Ageing** — `GET /customers/ageing[?customer_id=&as_of=]`. Per APPROVED or
  CLOSED invoice: `grand_total` to two decimals less the allocations of
  settlements not REVERSED; aged from `due_date`, or `invoice_date` when
  there is none, to `as_of` (default today in UTC); buckets 0–29, 30–59,
  60–89, 90+. Beside the bills: `account_balance` =
  `customers.current_outstanding`, and the gap named as
  `unapplied_credits` or `charges_not_billed`.
  - **Points spent on a bill are not subtracted** here, though Record Receipt
    subtracts them, so a bill part-settled by loyalty points ages at its full
    remainder and the gap is labelled "unapplied credits" (D-FIN-10).
  - **`as_of` moves only the day count.** Bills raised after it (age 0) and
    receipts after it are counted (D-FIN-10).
- **Check:**
  ```sql
  select t.transaction_date, t.created_at, t.transaction_type, t.reference_number,
         t.outstanding_delta,
         sum(t.outstanding_delta) over (order by t.transaction_date, t.created_at, t.id) as running
  from   test_fixtures.customer_receivable_transactions t
  join   test_fixtures.customers c on c.id = t.customer_id
  where  c.code = '<SUFFIX>-C' and t.is_deleted = false
  order  by t.transaction_date, t.created_at, t.id;

  select i.invoice_number, i.invoice_date, i.due_date, round(i.grand_total, 2) as total,
         coalesce(sum(a.amount) filter (where s.status <> 'REVERSED'), 0) as allocated,
         (select coalesce(sum(e.amount), 0) from test_fixtures.loyalty_entries e
          where e.sales_invoice_id = i.id and e.kind = 'REDEEMED' and e.is_deleted = false) as points_spent
  from   test_fixtures.sales_invoices i
  join   test_fixtures.customers c on c.id = i.customer_id
  left join test_fixtures.settlement_allocations a on a.sales_invoice_id = i.id and a.is_deleted = false
  left join test_fixtures.settlements s on s.id = a.settlement_id
  where  c.code = '<SUFFIX>-C' and i.status in ('APPROVED', 'CLOSED') and i.is_deleted = false
  group  by i.id;
  ```
  For TC-CUST-005: INVOICE 590.00 then RECEIPT −200.00, running 390.00;
  the invoice ages at 390.00 in 0–29 with nothing unexplained.
- **Confirmed:** TEST01's `invoiced-part-paid` customers carry exactly that
  trail (INVOICE 590.00, RECEIPT 200.00, 390.00 outstanding). WHOLE01's
  SI-2026-2027-000004 (3,698.95, nothing allocated, 100.00 of points spent)
  ages at 3,698.95 where Record Receipt offers 3,598.95.

### 12.11 Opening balances — customer, stock, vendor

- **A customer's opening balance** is `customers.opening_balance` on create
  (or an edit, while the customer has no other receivable row). **Inserts**
  a journal `<code>-OB` (`<code>-OB2`, … when the reference is taken),
  `source_module` `customers`, `source_id` the customer, dated **today in
  UTC** in the period open then: **Dr 1100 / Cr 3000**, swapped for a
  negative (credit) balance; and one `customer_receivable_transactions` row
  `OPENING_BALANCE` (`amount` the absolute value, the deltas splitting it into
  outstanding or advance, `reference_type` `CUSTOMER_MASTER`,
  `journal_entry_id` the journal). **Audit:** `finance.journal_entry.created`,
  `.posted`, `customer.created` (or `.updated`). Refused, with nothing
  written, when the firm has no chart or no period open today: "<code>
  cannot open with a balance: …".
- **Changing it** (only while no other receivable row exists) reverses every
  OB journal (`<ref>-REV`), **physically deletes** the old `OPENING_BALANCE`
  row, and posts the new figure.
- **Deleting the customer** reverses the OB journal and soft-deletes the
  customer — **with nothing else checked**. A customer who still owes, or
  holds an advance, leaves the receivable ledger with their balance still in
  1100 and no live customer owing it; **restoring** them brings the balance
  back without re-posting the opening journal (D-FIN-1).
- **Opening stock** is §10.0 and §10.6: posting a batch writes the
  `OPENING_STOCK` movements and one journal named by the batch reference,
  `source_module` `inventory`, **Dr 1200 / Cr 3000** at the movements' cost,
  dated the batch's `posting_date`; nothing when the value is zero. Audit
  `opening_stock.posted`.
- **A vendor has no opening balance.** `vendors` holds no balance column and
  nothing posts one; a supplier's day-one payable has to be a hand journal
  (Dr 3000 / Cr 2100) with no bill behind it.
- **Check:**
  ```sql
  select c.code, c.is_deleted, c.opening_balance, c.current_outstanding, c.unapplied_advance_balance,
         t.transaction_type, t.amount, t.outstanding_delta, t.advance_delta, je.reference_number, je.status
  from   test_fixtures.customers c
  left join test_fixtures.customer_receivable_transactions t
         on t.customer_id = c.id and t.transaction_type = 'OPENING_BALANCE'
  left join test_fixtures.journal_entries je on je.id = t.journal_entry_id
  where  c.opening_balance <> 0 or c.is_deleted;
  ```
- **Confirmed:** WHOLE01's OB-LIFE, OB-REV1 and OB-REV3 — deleted customers
  with a 25,000.00 opening balance, their OB rows gone and journals reversed.
  **TEST01's receivable account holds 3,040.00 while its live customers owe
  1,180.00:** five customers deleted on 2026-09-16 at 21:17 UTC still owe
  1,960.00 on four approved invoices and hold 100.00 of advance
  (`T09166ZCU-C`, `T0916RDX8-C`, `T0916KUGO-C`, `T0916LU5E-C`,
  `T09169VIQ-TILL`). No customer opening balance is live in any fixture store.

### 12.12 Money in and out — the ledger side of receipts, payments and refunds

The document side is §9.11–9.12 (payments) and §11.14–11.15 (receipts,
advances, TCS). What finance adds:

- **Every settlement posts before its row is written**, and
  `settlements.journal_entry_id` is NOT NULL. Receipt: Dr 1010 Bank (1000
  Cash for CASH) / Cr 1100. Payment: Dr 2100 / Cr 1010 or 1000. **Refund**
  (`POST /api/v1/refunds`, `PAYMENT_CREATE`, number `RF-2026-2027-…`): Dr 1100
  / Cr 1010 or 1000, a receivable row `REFUND` taking the advance down —
  refused beyond the advance held ("Refund amount exceeds unapplied
  advance."), and refused with allocations ("A refund returns money held on
  account, so it is not applied to an invoice."). **Audit:**
  `settlement.refund.recorded`. *(No refund exists in any store — not seen in
  a live row.)*
- **The bank or cash account is the CASH or BANK mapping** (§12.7); an
  unmapped one refuses the settlement by purpose.
- **A reversal** (`POST /receipts|payments|refunds/{id}/reverse`) posts
  `<number>-REV` through the engine with no date, so it is dated today (UTC)
  in the period open then (§12.4), and marks the settlement REVERSED; a
  receipt or refund also writes a receivable `REVERSAL` row dated the
  **original's** date (§12.10).
- **`POST /customers/{id}/receivables/transactions`** (`RECEIPT_CREATE`) is a
  second way to move a customer's balance. It refuses RECEIPT and
  ADVANCE_RECEIPT and posts a journal only for CREDIT_NOTE (Dr 4100 / Cr
  1100, reference as typed or `CN-<8 chars>`); **INVOICE, TCS, LOYALTY,
  ADVANCE_APPLY and REFUND move the balance with no journal**, no document
  and no allocation (D-FIN-4). No desktop screen calls it.
- **Check** — every settlement and its journals, and whether the two books
  agree:
  ```sql
  select s.settlement_number, s.direction, s.status, s.amount, la.code as money_account,
         je.reference_number, je.status as journal_status, je.journal_date,
         rv.reference_number as reversal, rv.journal_date as reversed_on
  from   fx_<suffix>_s.settlements s
  join   fx_<suffix>_s.ledger_accounts la on la.id = s.ledger_account_id
  join   fx_<suffix>_s.journal_entries je on je.id = s.journal_entry_id
  left join fx_<suffix>_s.journal_entries rv on rv.id = s.reversal_journal_entry_id
  order  by s.settlement_number;

  select (select coalesce(sum(p.debit_amount - p.credit_amount), 0)
          from fx_<suffix>_s.gl_postings p
          join fx_<suffix>_s.firm_control_accounts c
            on c.ledger_account_id = p.ledger_account_id and c.purpose = 'ACCOUNTS_RECEIVABLE') as ledger_1100,
         (select sum(current_outstanding) - sum(unapplied_advance_balance)
          from fx_<suffix>_s.customers where is_deleted = false)                             as customers_net;
  ```
  The two figures should be equal. They are in every store on the server
  except TEST01 (§12.11).

### 12.13 The other finance cases — what they write

- **TC-FIN-005, every report** — reads only. The finance reports are §12.9,
  the purchasing ones §9.13; none writes a row or an audit row.
- **TC-FIN-006, Ctrl+K** — `GET /api/v1/search?query=` reads the masters
  and documents the caller may see, in the firm in scope
  (`app/search/services/search_service.py`); it writes nothing. The only row a navigation can
  leave is the `user_preferences.updated` of the last screen (§3).
- **TC-FIN-008, a blocking credit policy** — §11.6: the refused approval
  writes nothing, the order stays DRAFT.
- **TC-FIN-009, the delivery-note stage off** — §11.20: the invoice's create
  raises, approves and dispatches the note in one request.
- **TC-FIN-010, Roles and Permissions** — reads only; the sidebar entry and
  the last-screen restore are `user_preferences` on the platform (§3, §4).
- **TC-FIN-011, a crash report** — one `platform.error_reports` row per
  report: `source` **CLIENT** for the desktop (the screen says Desktop) or
  SERVER, `error_type` `UnexpectedTermination`, `fingerprint`, `message`,
  `firm_id`, `user_id`, `breadcrumbs`, `occurred_at`, `received_at`; a server
  row also carries `request_id` and `stack_trace`. No audit row. The platform
  holds 263 CLIENT `UnexpectedTermination` rows (none with a request id or a
  stack trace) and 31 SERVER `ValidationError` rows (all with a stack trace, 3
  with a request id).
  ```sql
  select source, error_type, count(*), max(received_at),
         count(request_id) as with_request, count(stack_trace) as with_stack
  from   platform.error_reports
  group  by source, error_type
  order  by 3 desc;
  ```

### 12.14 `verify_sample_data.py` — what it checks, and what it does not

`uv run python scripts/verify_sample_data.py` reads every store in the
registry (SELECT only) and exits non-zero if any check fails:

| Check | Compares | Fails when |
| --- | --- | --- |
| Stock against the ledger | `product_valuations.total_value` against the INVENTORY account's postings | apart by more than 1.00 — and names un-mirrored receipt cancellations from before 2026-08-18 when the arithmetic says so |
| Every period balances | debits and credits of `gl_postings` per period | they differ |
| Balances are chained | each `ledger_balances.opening_balance` against the account's previous closing | any row opens elsewhere |
| Customers against the ledger | live customers' outstanding less advance, against the ACCOUNTS_RECEIVABLE postings | apart by more than 1.00 |
| Settlements reached the ledger | `settlements.journal_entry_id` | names no journal |
| Approved invoices posted | APPROVED, COMPLETED or CLOSED sales and purchase invoices | one has no journal with its `source_module` |

- **It does not separate firms in the shared store:** the stock, receivable
  and account sums carry no `firm_id`, so MEDI01's and FOOD01's differences
  are added together and can cancel (D-FIN-16).
- **It checks nothing about** payables against bills, GRNI against
  uninvoiced receipts, TCS payable against collections, loyalty payable
  against points, or cost and profit centres.
- **Run by hand on 2026-09-19** (the same queries, read-only): every period
  in every store balances and every balance is chained; stock agrees with
  1200 everywhere; customers agree with 1100 everywhere **except TEST01**,
  1,860.00 apart — the deleted customers of §12.11.

### 12.15 What finance does not write, and is often looked for

| You might expect | What actually happens |
| --- | --- |
| A row in `customer_ledgers` or `vendor_ledgers` | Never written; the customer side is `customer_receivable_transactions`, the vendor side does not exist |
| A trial balance row for every account every month | Rows only where an account moved; the rest are carried in memory by the report (§12.8) |
| A year-end closing entry | None; the balance sheet computes retained earnings (§12.9) |
| A journal type per module | Everything posts under the first journal and voucher type, `GEN` / `JV`; the module is `source_module` |
| A draft on a report | Drafts have no postings and no balances (§12.4) |
| An audit row for the 24 control-account mappings at Open the books | None (§12.1) |
| An audit row saying what changed on an account, a centre or a year | Name and active flag only (D-FIN-13) |
| A delete for an account, group, centre, journal type or period | None; deactivate (§12.3) |
| A finance row on the platform trail | Only `firm.books_opened` (§12.1) |
| A report using a cost or profit centre | None does (§12.6) |
| A vendor's opening balance | No mechanism (§12.11) |
| A crash report in the audit trail | `platform.error_reports` only (§12.13) |

### 12.16 Checked against live rows, and not

- **Confirmed in `fx_t0916hkkx_r`** (TC-FIN-001, 003 and 007 walked on
  2026-09-16): the 44 audit rows and the platform `firm.books_opened` of
  Open the books; account 9999; the two identical
  `finance.ledger_account.updated` rows; June closed and reopened with two
  audit rows; `MT-CLOSE-1`, `MT-CC-1`, `MT-CLOSE-2` with null
  `source_module`; the roll-forward of 1000 and 5000 into September;
  the SALES cost centre.
- **Confirmed in the selling stores:** the journal map of §12.5 in
  `fx_t0916d751_s`; its three statements agreeing; reversals dated the UTC
  day before the bills they cancel in `fx_t0919sosg_s` and `fx_t0919djcv_s`
  (SI-2026-2027-000001 and -000002, dated 2026-09-19, reversed 2026-09-18,
  and their receivable rows dated 2026-09-18 too); `SI-…-000002`'s
  cancellation in `fx_t0919djcv_s` leaving a 193.28 advance where a return
  had already credited the goods (D-SELL-7).
- **Confirmed on TEST01 and WHOLE01:** the journal map; the three statements
  agreeing; the deleted customers still owing in TEST01; the OB customers of
  WHOLE01; WHOLE01's control-account re-point and back; `JV-CENTRES-1` and
  `MT-CC-1` carrying centres; bills settled twice over by a full receipt plus
  points (SI-2026-2027-000009 4,586.76 allocated and 354.00 of points), all
  seeded on 2026-09-08, before Record Receipt began subtracting points on
  2026-09-13 — they stay until a reseed; 1000 Cash at −1,775.16 in WHOLE01's
  September.
- **Across every store on the server:** zero unbalanced periods, zero
  unchained balances, zero unbalanced entries, zero DRAFT journals, every line
  with one posting, `gl_postings.status` only POSTED, no CLOSED or LOCKED
  period, no locked year, no CONTROL or MEMO account, no overlapping periods,
  no mapping to an inactive account, no refund, no reversed payment, no
  cross-firm centre on a line.
- **Not seen in a live row:** a hand reversal; a refused post in a closed
  period (refusals write nothing); a locked period or year; a re-dated
  period; a customer opening balance still live; a customer restored after a
  delete; a refund; a receivable row posted through
  `/customers/{id}/receivables/transactions`; an account deactivated while
  mapped. ELEC01 (`agency_electrolink`) was not queried.

---

## 13. Compliance — tax engine, GST returns, e-invoices and TCS (TC-COMP-001 to 007, TC-CONF-005)

Read on 2026-09-19 off `app/tax` — `tax_framework_service.py` (systems,
components, profiles, country and migration mappings, settings, the profile
versions), `tax_rule_service.py` (rules, their versions, `simulate`, the
execution log), `gst_template.py`, `gst_buckets.py`, `retention.py` and the
router — off `app/gst_returns/services/gstr_service.py`, off
`app/einvoice` (`einvoice_service.py`, `payload.py`, `portal.py`) and off
`app/tcs/services/tcs_service.py`, with the parts of `sales_invoice_service.py`
and `settlement_service.py` that call them. `docs/MODULE_STATUS.md` files
nothing else under compliance; the "Ledger and tax filing" rules of
`docs/LEDGER_POSTING_RULES.md` these modules implement are the TCS, return,
sandbox and rounding ones. Then checked, read-only, against every store that
holds these tables — the `compliance-firm` stores of 2026-09-16
(`fx_t0916irn8_g`, `fx_t09167ru4_g`), one built for this pass
(`fx_t0919l8ca_g`), the selling stores, TEST01, WHOLE01, the shared store and
ELEC01 — and the defects were driven on `fx_t0919l8ca_g` against the running
backend. §13.13 says which claims a live row confirmed and which it could not.
A claim marked *(not seen in a live row)* was read off the code only.

### 13.0 Before you look

- **Stores.**

  | Case | Fixture | Schema |
  | --- | --- | --- |
  | TC-COMP-001 to 006 | `compliance-firm` | **`fx_<suffix>_g`** — firm `<SUFFIX>-G`, "Compliance <suffix>", GSTIN `33FXGST<4 digits>A1Z5` |
  | TC-COMP-007 | `selling-paid` | `fx_<suffix>_s` — §11.14 has the receipt side |
  | TC-CONF-005 | `firm-admin` | `test_fixtures` |

  The fixture's **Tables** line prints the schema. Find your rows by its
  codes: customers `<SUFFIX>-B2B` (GSTIN `33FXBUY…`) and `<SUFFIX>-B2C`
  (none), product `<SUFFIX>-P` at HSN 340220, invoices A, B and C as
  `SI-2026-2027-000001` to `000003`. For WHOLE01 put `wholesale_hub`; for
  MEDI01 or FOOD01 put `firm_shared` and filter on `firm_id`; ELEC01 is
  `electrolink_ops` in `agency_electrolink`.
- **All compliance audit rows go to the firm's own trail.** The only
  platform row is `firm.tax_template_applied` (§6, §13.2); no `tax.*`,
  `einvoice.*`, `eway_bill.*` or `tcs.*` row exists in `platform.audit_logs`
  (checked 2026-09-19: zero).
- **Four kinds of table, and one kind that does not exist.**

  | Tables | Written by | Holds |
  | --- | --- | --- |
  | `tax_systems`, `tax_components`, `tax_profiles`, `tax_profile_components`, `tax_profile_attribute_values`, `tax_country_mappings`, `tax_migration_mappings`, `tax_settings` | Tax Configuration, the GST template | what can be charged |
  | `tax_rules`, `tax_rule_conditions`, `tax_rule_actions` | Tax Configuration → Rules, the GST template | which profile a transaction gets |
  | `tax_rule_execution_logs` | **every priced document line**, and the Rule Simulator | the engine's input, trace and answer, one row per line |
  | `einvoice_registrations`, `eway_bills`, `tcs_settings`, `tcs_collections` | E-Invoice, TCS, and Record Receipt | what was registered, raised and collected |

  **There is no GST return table.** GSTR-1 and GSTR-3B are computed on every
  read from `sales_invoices`, `sales_invoice_lines`, `sales_invoice_line_taxes`,
  `credit_notes` and `credit_note_lines` (§13.6). Nothing records what was
  filed, or when.
- **The tax a line was charged lives on the line**, not in the engine's
  log: `sales_invoice_line_taxes` (and `sales_return_line_taxes`,
  `credit_note_lines.tax_rate_percent`, and each module's own) —
  `component_code`, `percentage`, `base_amount`, `amount` at four decimals.
  The return and the e-invoice both read those rows, through
  `split_components`, which buckets a code by whether it **contains**
  `CGST`, `SGST`, `IGST` or `CESS` and ignores anything else.
- **One click, all its audit rows** — the §9.0 request-id query works
  unchanged with the store's schema and the action you took
  (`einvoice.registered`, `eway_bill.cancelled`, `tcs.settings_changed`).
- **What points at what.**

  | From | Column | To |
  | --- | --- | --- |
  | `tax_profiles` | `tax_system_id`; `group_code` — **the name products use**, stable across versions | `tax_systems`; `products.tax_profile_group_code` (no foreign key) |
  | `tax_profile_components` | `tax_profile_id`, `tax_component_id` | `tax_profiles`, `tax_components` |
  | `tax_rules` | `version_group_id` (one per rule, all versions), `supersedes_rule_id` on a version | `tax_rules` |
  | `tax_rule_conditions`, `tax_rule_actions` | `tax_rule_id`; an action's `target_tax_profile_id` / `target_tax_component_id` | `tax_rules`; `tax_profiles`, `tax_components` |
  | `tax_rule_conditions` | `value_text` holding a **profile id as text** for the template's rules | `tax_profiles` (no foreign key) |
  | `tax_rule_execution_logs` | `matched_rule_id`, `tax_profile_id`, `applied_tax_profile_id` — **not** the document or line it priced | `tax_rules`, `tax_profiles` |
  | `sales_invoice_line_taxes` | `sales_invoice_line_id`, `tax_component_id` | the line; the component |
  | `einvoice_registrations`, `eway_bills` | `sales_invoice_id` (unique per firm, one row each for ever) | `sales_invoices` |
  | `tcs_collections` | `settlement_id` (unique), `customer_id`, `journal_entry_id`, `reversal_journal_entry_id`, `receivable_transaction_id` (no foreign key) | `settlements`, `customers`, `journal_entries`, `customer_receivable_transactions` |

- **Where the compliance rows are, 2026-09-19.** `fx_t0916irn8_g` is a
  `compliance-firm` run of 2026-09-16 (A and B registered, C not);
  `fx_t09167ru4_g` another, built before the fixture's product carried a tax
  profile, so its three invoices charge **no tax at all** and two are
  registered — plus an e-way bill raised and withdrawn on B (TC-COMP-006).
  Both firms have since been soft-deleted by a clear and their schemas stay.
  `fx_t0919l8ca_g` was built for this pass and then used to drive the
  defects in §13.13, so it is no longer a clean `compliance-firm`. WHOLE01
  holds 13 registrations, 7 e-way bills (one withdrawn), 39 TCS collections
  (three reversed) and 15,956 execution logs; the shared store 31, 15, 70 and
  25,722; ELEC01 17, 8, 39 and 16,769. Every registration and every e-way bill
  in every store is `SANDBOX` and every reference begins `SBX`.

### 13.1 Tax configuration — systems, components, profiles, mappings, settings

Administration → Configuration → Tax Configuration, all under
`/api/v1/tax-framework`, permissions `TAX_VIEW`, `TAX_CREATE`, `TAX_UPDATE`,
`TAX_DELETE`, `TAX_RESTORE`, `TAX_IMPORT`, `TAX_EXPORT`,
`TAX_MANAGE_SETTINGS`. **Each call commits on its own.**

- **Create and edit** insert or update one row and write an audit row:

  | Endpoint | Table | Audit |
  | --- | --- | --- |
  | `POST` / `PUT /systems` | `tax_systems` | `tax.system.created` / `.updated` |
  | `POST` / `PUT /components` | `tax_components` | `tax.component.created` / `.updated` |
  | `POST` / `PUT /profiles` | `tax_profiles` + `tax_profile_components` (+ `tax_profile_attribute_values`) | `tax.profile.created` / `.updated`, `after_data` = `code` only |
  | `POST /setup`, `PUT /setup/{id}` | a system, its components and profiles in one request | `tax.setup.created` / `.updated` |
  | `POST /country-mappings` | `tax_country_mappings` | `tax.country_mapping.created` |
  | `POST /migration-mappings`, `POST /legacy/import-csv` | `tax_migration_mappings` | `tax.migration_mapping.created`, no data |

- **Written with no audit row** (D-CMP-9): delete and restore of a system,
  component or profile (`is_deleted`, `deleted_at`, `version` +1); every
  `bulk-delete`, `bulk-restore` and `profiles/bulk-status`; edit and delete
  of a country or migration mapping; `PUT /settings` (`tax_settings`, labels
  and `additional_settings`). The **Tax History** screen
  (`GET /tax-framework/history`) reads only audit rows, so it cannot show
  any of them. `GET /settings` **inserts** the firm's `tax_settings` row and
  commits when there is none.
- **A rate change** is two writes: `PUT /profiles/{id}` ending the old
  version (`effective_to`, `tax.profile.updated`) and `POST /profiles` with
  the same `group_code` and a later `effective_from` (`tax.profile.created`).
  `TaxFrameworkService.supersede_profile`, which does both in one step, is
  called by nothing. A document picks the version in force on **its own
  date** (`resolve_active_profile`, latest `effective_from` first, NULLs
  last — explicit, so PostgreSQL and SQLite agree). Two ACTIVE versions of
  one group may not overlap — checked on create and update, **not** on
  `bulk-status` or restore.
- **Refused, nothing written:** deleting a system that still has live
  components or profiles; deleting a profile whose `group_code` a live
  product uses. **Not refused:** deleting a profile a rule's action targets
  (the interstate profiles have no products), or a component a profile
  still carries (D-CMP-9).
- **Check:**
  ```sql
  select p.code, p.group_code, p.status, p.effective_from, p.effective_to,
         p.is_historical, p.is_deleted, p.version,
         string_agg(c.code || ' ' || pc.percentage, ', ' order by pc.calculation_order) as components
  from   fx_<suffix>_g.tax_profiles p
  left join fx_<suffix>_g.tax_profile_components pc on pc.tax_profile_id = p.id
  left join fx_<suffix>_g.tax_components c on c.id = pc.tax_component_id
  group  by p.id
  order  by p.display_order, p.effective_from;

  select created_at, action, entity_type, entity_id
  from   fx_<suffix>_g.audit_logs
  where  entity_type like 'tax_%' and action <> 'tax.rule.simulated'
  order  by created_at desc;
  ```
- **Confirmed** in `fx_t0919l8ca_g`: `GST_0` set INACTIVE and back through
  `bulk-status`, `CESS` deleted and restored — `tax_profiles.version` and
  `tax_components.version` both read 3, and no audit row was written between
  06:26:49 and 06:26:59 IST.

### 13.2 The GST template — what a finished firm starts with

Firms → Set up → **Apply GST template**
(`POST /api/v1/firms/{id}/apply-tax-template`, platform-only). §6 has the
platform half.

- **Inserts** (firm's store), only when the firm has **no** live tax system:
  `tax_settings` updated (primary label "GST", `additional_settings.template`
  `IN_GST`); `tax_systems` 1 (`GST`); `tax_components` 4 — CGST, SGST, IGST,
  CESS (CESS not recoverable); `tax_country_mappings` 1 (India, default, from
  2017-07-01); `tax_profiles` 8 — `GST_0` (IGST 0), `GST_5_LOCAL`,
  `GST_12_LOCAL`, `GST_18_LOCAL` (CGST + SGST at half the rate each), their
  `_INTERSTATE` twins (IGST), `EXEMPT` (no components) — 10
  `tax_profile_components`; `tax_rules` 9 with 15 conditions and 13 actions (six before D-CMP-14);
  `geo_countries` India if the store has no country.
- **The nine rules:**

  | Code | Priority | When | Does |
  | --- | --- | --- | --- |
  | `EXPORT_ZERO` | 1 | `transaction_type` = `EXPORT` | apply `GST_0`, zero-rated |
  | `INTERSTATE_GST_5` / `_12` / `_18` | 10 / 11 / 12 | `transaction_type` = `SALES_INTERSTATE` **and** `tax_profile_id` = that slab's LOCAL profile id | apply the INTERSTATE twin |
  | `PURCHASE_INTERSTATE_GST_5` / `_12` / `_18` | 13 / 14 / 15 | `transaction_type` = `PURCHASE_INTERSTATE` **and** `tax_profile_id` = that slab's LOCAL profile id | apply the INTERSTATE twin, input credit allowed (D-CMP-14; `20260919_0148` adds them to firms templated earlier) |
  | `EXEMPT_PROFILE` | 20 | `tax_profile_id` = `EXEMPT`'s id | exempt |
  | `PURCHASE_INPUT_CREDIT` | 30 | `transaction_type` = `PURCHASE` | input credit allowed |

  **No document sends `SALES_INTERSTATE`, `EXPORT` or `PURCHASE`** — the
  modules send `SALES_INVOICE`, `PURCHASE_INVOICE`, `GOODS_RECEIPT` and their
  siblings — so on a real document only `EXEMPT_PROFILE` can ever match
  (D-CMP-1, D-CMP-13). The interstate rules name the LOCAL profile **by id**,
  so they would stop matching after a rate change supersedes it.
- **Audit, firm trail — 23 rows:** `tax.system.created`,
  `tax.component.created` ×4, `tax.country_mapping.created`,
  `tax.profile.created` ×8, `tax.rule.created` ×9. The settings change has
  none. **Audit, platform:** `firm.tax_template_applied`, `after_data`
  `template` `IN_GST` and the counts.
- **Not one transaction** — each record commits as it is made, so a failure
  half-way leaves a tax system that makes the next press answer "already has
  one" (D-CMP-8) *(not seen in a live row)*.
- **Check** (fresh store: `1, 4, 8, 10, 1, 1, 9, 15, 13`):
  ```sql
  select (select count(*) from fx_<suffix>_g.tax_systems)            as systems,
         (select count(*) from fx_<suffix>_g.tax_components)         as components,
         (select count(*) from fx_<suffix>_g.tax_profiles)           as profiles,
         (select count(*) from fx_<suffix>_g.tax_profile_components) as profile_components,
         (select count(*) from fx_<suffix>_g.tax_country_mappings)   as country_mappings,
         (select count(*) from fx_<suffix>_g.tax_settings)           as settings,
         (select count(*) from fx_<suffix>_g.tax_rules)              as rules,
         (select count(*) from fx_<suffix>_g.tax_rule_conditions)    as conditions,
         (select count(*) from fx_<suffix>_g.tax_rule_actions)       as actions;
  ```
- **Confirmed** in `fx_t0919l8ca_g`: those counts plus what the probes of
  §13.3 added (two rules, two conditions, one action), the 20 firm audit
  rows at 06:22:06–06:22:08 IST and the platform row at 06:22:06.

### 13.3 Tax rules — create, edit, delete, restore, import

Tax Configuration → Rules. `POST` / `PUT` / `DELETE /tax-framework/rules`,
`POST /rules/{id}/restore`, `POST /rules/import`; permissions
`TAX_RULE_CREATE`, `TAX_RULE_UPDATE`, `TAX_RULE_DELETE`, `TAX_RULE_RESTORE`,
`TAX_IMPORT`.

- **Create** inserts `tax_rules` (`version_group_id` new, `version_number`
  1, `status` as sent — DRAFT by default), its `tax_rule_conditions` and
  `tax_rule_actions`. Audit `tax.rule.created` (`code`, `version_number`).
  Refused: a code already used at that version ("Tax rule code already
  exists for this version.") or a profile or component that is not the
  firm's.
- **Edit a DRAFT** updates the row in place; the old conditions and actions
  are **soft-deleted** and new ones inserted. Audit `tax.rule.updated`
  (`code`, `priority`, `status`, `version_number` both sides). The status in
  the body is written — a draft is activated by editing it.
- **Edit an ACTIVE (or INACTIVE, ARCHIVED) rule** inserts a **new version**:
  a second `tax_rules` row with the same `code` and `version_group_id`,
  `version_number` +1, `supersedes_rule_id` = the old row, and whatever
  status the body carried. **The old row is not touched** — it stays ACTIVE
  and keeps being evaluated (§13.4). Audit `tax.rule.versioned`,
  `before_data.supersedes_rule_id`. Editing a rule to INACTIVE therefore
  leaves it in force (D-CMP-3).
- **Delete** soft-deletes the one row named (`tax.rule.deleted`); its other
  versions stand. **Restore** clears it (`tax.rule.restored`).
- **Import** is `create` in a loop, each committing: a batch refused at row
  *n* keeps rows 1 to *n*−1 and answers 409 (D-CMP-8).
- **Check:**
  ```sql
  select r.code, r.version_number, r.status, r.priority, r.effective_from, r.effective_to,
         r.supersedes_rule_id is not null as supersedes, r.is_deleted,
         (select string_agg(c.field_key || ' ' || c.operator || ' ' || coalesce(c.value_text, ''), ' and ')
          from fx_<suffix>_g.tax_rule_conditions c where c.tax_rule_id = r.id and c.is_deleted = false) as conditions,
         (select string_agg(a.action_type, ', ') from fx_<suffix>_g.tax_rule_actions a
          where a.tax_rule_id = r.id and a.is_deleted = false) as actions
  from   fx_<suffix>_g.tax_rules r
  order  by r.priority, r.code, r.version_number desc;
  ```
  Any `code` with two rows both ACTIVE and not deleted is D-CMP-3.
- **Confirmed** in `fx_t0919l8ca_g`: `INTERSTATE_GST_18` edited to INACTIVE
  at 06:26:41 IST — version 2 INACTIVE, version 1 still ACTIVE, one
  `tax.rule.versioned`; an import of two rules both coded `CMPIMP_A`
  answered 409 and left the first, DRAFT, with its `tax.rule.created`. No
  rule in any other store has a second version.

### 13.4 Simulate — the engine, and the Rule Simulator (TC-CONF-005)

Tax Configuration → **Rule Simulator** is `POST /tax-framework/simulate`
(`TAX_SIMULATE`). **The same function prices every document line** in nine
modules (§11.0), so what it writes rides along with every priced save.

- **How it decides:** every live ACTIVE rule of the firm, ordered
  `priority`, `code`, `version_number` desc, `created_at` — all columns
  NOT NULL, so the order is the same on both databases. The first rule whose
  scope, effective window (against the **document's** date) and every
  condition match wins, **and evaluation stops**: the trace lists the rules
  up to the winner and none after. Its actions apply in `sequence`; with no
  match the profile in context is used as configured. `total_tax_amount` is
  the additive components only; included-in-price and reverse-charge tax are
  reported beside it.
- **Inserts** one `tax_rule_execution_logs` row — `execution_mode`
  **always `SIMULATION`**, the document's lines included (D-CMP-13);
  `transaction_type`, `country_id`, `business_profile_id`, `tax_profile_id`,
  `matched_rule_id`, `applied_tax_profile_id`, and three JSON documents:
  `input_payload`, `evaluation_trace.decisions`, `result_payload`. **Audit:**
  `tax.rule.simulated` (`matched_rule_id`, empty when none, and
  `transaction_type`).
- **Commit:** the endpoint commits; the service never does — a document
  line's log and audit row are part of that document's own transaction and
  vanish with it if the save fails *(not seen in a live row)*.
- **Nothing links a log to its document.** The log carries no document id
  or line id; find a document's logs by time and `transaction_type`.
- **Retention:** nothing prunes the log until the retention service is run
  (`scripts/purge_retention.py`, default 365 days). The oldest log in WHOLE01
  and the shared store is from 2026-08-15.
- **Check:**
  ```sql
  select l.created_at, l.transaction_type, l.execution_mode, r.code as matched_rule,
         p.code as applied_profile,
         jsonb_array_length((l.evaluation_trace::jsonb)->'decisions') as rules_tried,
         (l.result_payload::jsonb)->>'total_tax_amount' as total_tax
  from   fx_<suffix>_g.tax_rule_execution_logs l
  left join fx_<suffix>_g.tax_rules r    on r.id = l.matched_rule_id
  left join fx_<suffix>_g.tax_profiles p on p.id = l.applied_tax_profile_id
  order  by l.created_at desc;
  ```
- **Confirmed** in `fx_t0919l8ca_g`: 14 logs — twelve from the fixture's and
  this pass's orders, notes and invoices (3 per sale, `SALES_ORDER`,
  `DELIVERY_NOTE`, `SALES_INVOICE`, each trying all six rules and matching
  none), one `SALES_RETURN`, and one simulator run of `SALES_INTERSTATE`
  that matched `INTERSTATE_GST_18` version 1 after four rules and answered
  IGST 180 — the TC-CONF-005 figure, reached through the version D-CMP-3
  should have retired.

### 13.5 The tax a document line gets — and where it is stored

- **Every sale is taxed as a sale within the state.** `SalesInvoiceService`
  asks the engine with `transaction_type` `SALES_INVOICE` whoever the buyer
  is, and the invoice's `place_of_supply` (the state name from the
  customer's address, copied at create) is read by nothing but the print.
  So a buyer registered in another state is charged **CGST + SGST**, the
  e-invoice then refuses the bill, and GSTR-1 files it under the buyer's
  state with central and state tax (D-CMP-1). **No line in any store on the
  server carries IGST.**
- **Stored per component** in `sales_invoice_line_taxes` at four decimals
  (18% on 409.50 is CGST 36.855 + SGST 36.855); the line's `tax_amount` and
  the invoice's `tax_total` are their sum. The **ledger** credits 2200 with
  that sum rounded once (73.71); **GSTR-1 and the e-invoice** round CGST and
  SGST separately (36.86 + 36.86 = 73.72). So a return and the books differ
  by a paisa on any bill whose halves end in a half-paisa (D-CMP-4).
- **Check** — the components, and what the ledger credited, per bill:
  ```sql
  select i.invoice_number, i.status, i.tax_total, t.component_code, t.percentage, t.amount,
         (select sum(jl.credit_amount) from fx_<suffix>_g.journal_entries e
          join fx_<suffix>_g.journal_lines jl on jl.journal_entry_id = e.id
          join fx_<suffix>_g.ledger_accounts a on a.id = jl.ledger_account_id
          where e.source_module = 'sales_invoice' and e.source_id = i.id
            and e.reversal_of_id is null and a.code = '2200') as credited_2200
  from   fx_<suffix>_g.sales_invoices i
  join   fx_<suffix>_g.sales_invoice_lines l      on l.sales_invoice_id = i.id and l.is_deleted = false
  join   fx_<suffix>_g.sales_invoice_line_taxes t on t.sales_invoice_line_id = l.id and t.is_deleted = false
  order  by i.invoice_number, l.line_number, t.sequence;
  ```
- **Confirmed:** `fx_t0919l8ca_g` SI-2026-2027-000004, to a buyer with
  GSTIN `29FXKAR0529C1Z1`, carries CGST 18.00 + SGST 18.00; the half-paisa
  split on 30 of WHOLE01's 52 live bills, 43 of the shared store's 90 and
  every `selling-paid` store's SI-2026-2027-000001.

### 13.6 GSTR-1 — reads only (TC-COMP-001, 002)

Sales → **GST Returns** → GSTR-1 is `GET /api/v1/gst-returns/gstr1?from_date=&to_date=`,
permission **`SALES_VIEW`**. **It writes nothing** — no row, no audit, no
log — and refuses a firm with no GSTIN ("This firm has no GST number, so it
has no return to file.").

- **Reads** invoices with `status` APPROVED or CLOSED and `invoice_date` in
  the period (drafts and cancelled bills are not supplies), their lines and
  `sales_invoice_line_taxes`, the customers' `gst_number`, the products'
  `hsn_sac`, and **credit notes** with `status` APPROVED and
  `credit_note_date` in the period. **Sales returns are not read** — a
  completed return reverses output tax in the ledger and appears in no
  section and in no deduction (D-CMP-2).
- **Sections:**

  | Section | What goes in | Place of supply |
  | --- | --- | --- |
  | `b2b` | every bill to a customer with a GSTIN, invoice by invoice, grouped by GSTIN | the buyer's GSTIN's first two digits |
  | `b2cl` | bills to an unregistered buyer charged IGST with `grand_total` above **2,50,000** (D-CMP-10) | — |
  | `b2cs` | every other unregistered bill, summed by place and rate, less unregistered buyers' credit notes | **read off the tax**: the seller's state when CGST/SGST was charged; blank when IGST was |
  | `cdnr` | credit notes to registered buyers, note by note, the note's one tax figure split by the tax its invoice charged | — |
  | `hsn` | every line by HSN and rate — a product with no HSN under a blank code, not dropped | — |
  | `docs` | the invoice series: first number, last number, **count of live bills** — cancelled ones are left out, not counted (D-CMP-10) | — |
  | `unplaced_invoices` | unregistered bills charged IGST, named rather than filed with a blank place | — |

- **Taxable value** is gross − line discount − bill discount + line charges
  + freight, per line; `additional_charges` and `round_off` on the header are
  outside it. Each figure is rounded to two decimals once, on the way out.
- **Derived on every read:** cancelling a bill takes it out of **its own
  month**, however long ago that month was filed (D-CMP-11).
- **Check** — what the B2B and B2CS sections are built from:
  ```sql
  select i.invoice_number, i.invoice_date, i.status, c.code, c.gst_number,
         left(coalesce(c.gst_number, ''), 2) as buyer_state, i.grand_total,
         sum(t.amount) filter (where t.component_code like '%CGST%') as cgst,
         sum(t.amount) filter (where t.component_code like '%SGST%') as sgst,
         sum(t.amount) filter (where t.component_code like '%IGST%') as igst
  from   fx_<suffix>_g.sales_invoices i
  join   fx_<suffix>_g.customers c on c.id = i.customer_id
  join   fx_<suffix>_g.sales_invoice_lines l on l.sales_invoice_id = i.id and l.is_deleted = false
  left join fx_<suffix>_g.sales_invoice_line_taxes t on t.sales_invoice_line_id = l.id and t.is_deleted = false
  where  i.is_deleted = false
    and  i.invoice_date between date_trunc('month', current_date)::date and current_date
  group  by i.id, c.id
  order  by i.invoice_number;
  ```
  The rows with `status` APPROVED or CLOSED are the ones filed.
- **Confirmed** in `fx_t0919l8ca_g` before the probes: B2B A 1,000.00 /
  90.00 / 90.00 and B 500.00 / 45.00 / 45.00 under `33FXBUY0529B1Z3`, place
  33; B2CS one row, place 33, 18%, 300.00 / 27.00 / 27.00; HSN 340220
  quantity 18, 1,800.00; CDNR empty; `docs` `SI-2026-2027-000001` to
  `000003`, count 3. After B was cancelled and a return booked against C: B2B
  lost B, the Karnataka bill appeared under place 29 with CGST 18.00 and
  SGST 18.00, B2CS still read 300.00 / 27.00 / 27.00, and `docs` read
  `000001` to `000004`, count 3.

### 13.7 GSTR-3B — reads only (TC-COMP-003)

`GET /api/v1/gst-returns/gstr3b?from_date=&to_date=`, `SALES_VIEW`. Writes
nothing.

- **3.1(a)** is summed from the same invoice lines GSTR-1 reads — **not**
  parsed out of GSTR-1 — less every credit note of the period, registered
  and unregistered. Nil-rated and exempt lines are inside 3.1(a) at 0%;
  there is no 3.1(b) or 3.1(c) (D-CMP-10). Credit notes' cess is not
  deducted. **Sales returns are not deducted** (D-CMP-2).
- **The inward half** reads "Not derived: the purchase side files this." —
  no input credit is computed anywhere.
- **Check** — 3.1(a)'s tax against what the ledger holds as output tax for
  the same days (they should agree, less rounding):
  ```sql
  select sum(p.credit_amount - p.debit_amount) as output_tax_2200
  from   fx_<suffix>_g.gl_postings p
  join   fx_<suffix>_g.ledger_accounts a on a.id = p.ledger_account_id
  where  a.code = '2200'
    and  p.posting_date::date between date_trunc('month', current_date)::date and current_date;
  ```
- **Confirmed** in `fx_t0919l8ca_g`: 3.1(a) 1,800.00 / 162.00 / 162.00
  before the probes, equal to GSTR-1's sum (TC-COMP-003); after them
  1,500.00 / 135.00 / 135.00 = 270.00 of tax with nothing deducted, while
  2200 holds **252.00** — the 18.00 of SR-2026-2027-000001.

### 13.8 Register an invoice with the portal (TC-COMP-004, 005)

Sales → **E-Invoice** → Register an invoice is
`POST /api/v1/einvoice/invoices/{id}/register`, permission
`EINVOICE_MANAGE`; the grid is `GET /einvoice/registrations`
(`EINVOICE_VIEW`).

- **Refused locally, nothing written** — not even an audit row — when the
  payload cannot be valid, the reasons joined: "This invoice cannot be
  registered yet: the firm has no GST number; the customer has no GST number;
  the invoice is not approved; the invoice has no lines; <product> has no HSN
  or SAC code." Also refused: a bill whose tax contradicts the two GSTINs'
  states — "This is an inter-state supply but the invoice charged CGST and
  SGST. Correct the tax before registering it." (every interstate bill,
  D-CMP-1) and the intra-state twin; and a bill already REGISTERED ("…is
  already registered as SBX…. Cancel that registration before raising
  another.", 409).
- **Inserts** one `einvoice_registrations` row: `firm_id`,
  `sales_invoice_id`, **`mode` SANDBOX** (NOT NULL, no default in the
  database), `status` REGISTERED, `irn` `SBX` + a 61-character hash of the
  payload, `acknowledgement_number` `SBX` + 12, `acknowledged_at` (UTC now),
  `signed_qr_code` `SANDBOX.…`, `signed_invoice`, `attempts` 1,
  `request_payload` — exactly what was sent (the seller's and buyer's GSTIN,
  state, `ItemList` with HSN, quantity, amounts, `GstRt` and the four tax
  buckets, and `ValDtls`). A portal refusal lands on the same row as
  `status` FAILED with `error_code` / `error_message`.
- **Audit:** `einvoice.registered` (or `einvoice.refused`), `after_data` =
  `sales_invoice_id`, `mode`, `status`, `irn`, `acknowledgement_number`,
  `attempts`, `error_code`, `error_message`.
- **What it stops:** a REGISTERED row blocks cancelling the invoice — "SI-…
  cannot be cancelled while it has … its registration with the tax
  authority. Reverse or cancel those first." (TC-COMP-002).
- **Not written:** nothing on `sales_invoices`; no journal; no lifecycle
  event. `LIVE` is never written — `portal_for("LIVE")` raises "Live
  registration needs this firm's GSP credentials…" and nothing is sent.
- **Check:**
  ```sql
  select i.invoice_number, i.status as invoice_status, c.gst_number,
         r.mode, r.status, r.irn, r.acknowledgement_number, r.acknowledged_at,
         r.attempts, r.error_code, r.error_message, r.cancelled_at, r.cancellation_reason, r.version
  from   fx_<suffix>_g.einvoice_registrations r
  join   fx_<suffix>_g.sales_invoices i on i.id = r.sales_invoice_id
  join   fx_<suffix>_g.customers c      on c.id = i.customer_id
  order  by i.invoice_number;
  ```
- **Confirmed** in `fx_t0919l8ca_g`, `fx_t0916irn8_g` and `fx_t09167ru4_g`:
  A and B registered by the fixture, one audit row each, `mode` SANDBOX and
  `SBX` references; C (no GSTIN) never registered; the Karnataka bill's
  refusal wrote nothing. In `fx_t09167ru4_g` the two registered bills carry
  **no tax at all** and were accepted at `GstRt` 0. No row in any store is
  LIVE or FAILED.

### 13.9 Withdraw a registration, and register again

E-Invoice → the row's **Withdraw** action is
`POST /api/v1/einvoice/invoices/{id}/cancel` with `{"reason": …}`,
`EINVOICE_MANAGE`. A row that is not REGISTERED — a withdrawn one included —
offers **Register** again, and **Register an invoice** lists it too.

- **Refused:** no REGISTERED row ("This invoice has no live
  registration."); an empty reason; more than 24 hours after
  `acknowledged_at`, judged in UTC ("A registration can only be withdrawn
  within 24 hours. Raise a credit note instead…").
- **Updates** the row: `status` CANCELLED, `cancelled_at`,
  `cancellation_reason` (up to 200), `version` +1. **Audit:**
  `einvoice.cancelled` (the same snapshot as §13.8).
- **Does not look at the e-way bill.** A registration is withdrawn while
  its e-way bill is GENERATED, and the invoice can then be cancelled with
  the bill still live (D-CMP-5).
- **Register again** reuses the **same row**: `status` REGISTERED,
  `attempts` +1, a new `acknowledged_at` — and the sandbox, hashing the same
  payload, mints the **same IRN** as the one withdrawn. `cancelled_at` and
  `cancellation_reason` are left on the REGISTERED row, and the withdrawn
  registration survives only in the audit trail (D-CMP-6).
- **Confirmed** in `fx_t0919l8ca_g`: A withdrawn at 06:26:34 and registered
  again — `attempts` 2, IRN `SBX85d3a853…` unchanged, `cancellation_reason`
  "cmp probe" on a REGISTERED row; B withdrawn at 06:26:06 with its e-way
  bill GENERATED, then cancelled as an invoice at 06:26:07.

### 13.10 E-way bill — raise and withdraw (TC-COMP-006)

Select a row → **Raise bill** is `POST /api/v1/einvoice/invoices/{id}/eway-bill`
(`distance_km` > 0, `transport_mode` ROAD / RAIL / AIR / SHIP,
`transporter_id`, `transporter_name`, `vehicle_number`); **Cancel bill** is
`POST …/eway-bill/cancel` with a reason. `EINVOICE_MANAGE`.

- **Refused, nothing written:** the invoice not REGISTERED ("Register the
  invoice before raising its e-way bill: the bill quotes the IRN…", 422 —
  TC-COMP-006 step 3); a GENERATED bill already standing (409); an unknown
  mode; ROAD with no vehicle ("Goods moving by road need a vehicle number on
  the e-way bill."). The invoice's own status is not checked.
- **Inserts** one `eway_bills` row (or rewrites the invoice's withdrawn one):
  `mode` = the registration's, `status` GENERATED, `eway_bill_number` `SBX` +
  up to 12 digits, `valid_until` = today (UTC) + one day per 200 km,
  `distance_km`, `transport_mode`, `transporter_id`, `transporter_name`,
  `vehicle_number` (upper-cased), `request_payload` (`Irn`, `TransDistance`,
  `TransMode`, `TransId`, `TransName`, `VehNo`). **Audit:**
  `eway_bill.generated` (`eway_bill_number`, `status`, `mode`).
- **Withdraw** updates `status` CANCELLED, `cancelled_at`,
  `cancellation_reason`, `version` +1; audit `eway_bill.cancelled` (`status`,
  `reason`). No time window is checked. The screen offers **Raise bill**
  only while the invoice has no bill row at all, so a withdrawn bill is
  raised again only through the API, which rewrites the same row.
- **Check:**
  ```sql
  select i.invoice_number, i.status as invoice_status, r.status as registration,
         e.mode, e.status, e.eway_bill_number, e.valid_until, e.distance_km,
         e.transport_mode, e.vehicle_number, e.cancelled_at, e.cancellation_reason, e.version
  from   fx_<suffix>_g.eway_bills e
  join   fx_<suffix>_g.sales_invoices i on i.id = e.sales_invoice_id
  left join fx_<suffix>_g.einvoice_registrations r on r.sales_invoice_id = i.id;
  ```
  An `invoice_status` CANCELLED beside a GENERATED bill is D-CMP-5.
- **Confirmed:** `fx_t09167ru4_g` B's bill `SBX621387159885`, 120 km by
  road, `TN01AB1234`, valid until 2026-09-16, withdrawn "probe" — two audit
  rows (TC-COMP-006 as walked); WHOLE01 one withdrawn bill on
  SI-2026-2027-000003 and six standing; `fx_t0919l8ca_g`
  `SBX359194143134` GENERATED on the **cancelled** SI-2026-2027-000002.

### 13.11 TCS — settings, preview, a collection, its reversal (TC-COMP-007)

Sales → **TCS**. `GET` / `PUT /api/v1/tcs/settings` (`TCS_VIEW` /
`TCS_MANAGE` — not granted to `SALES_MANAGER`), `GET /tcs/preview`,
`GET /tcs/collections`. **No endpoint collects**; a receipt does. Whether
section 206C(1H) is still levied at all is D-CMP-12.

- **Settings** — one `tcs_settings` row per firm, inserted on the first
  save: `section_code` `206C_1H`, `is_enabled` (false by default),
  `threshold_amount` (5,000,000), `rate_percent` (0.1),
  `rate_without_pan_percent` (1), `preceding_year_turnover` (0),
  `seller_turnover_threshold` (100,000,000). An omitted field is left alone.
  **Audit:** `tcs.settings_changed`, both sides all six figures. A firm with
  no row collects nothing and the screen shows these defaults.
- **Preview** reads only: the buyer's receipts **in the whole financial
  year** (from the firm's `financial_year_start`) less refunds, reversed ones
  excluded — including receipts dated **after** the date asked about
  (D-CMP-7) — and answers why nothing is due where nothing is.
- **Collected when Record Receipt posts** (§11.14 has the receipt itself),
  only if the firm is enabled, its stated turnover is above its threshold,
  and the part of this receipt above the buyer's threshold is positive:
  - `tcs_collections`: `customer_id`, `settlement_id`, `financial_year_start`,
    `collected_on` = the receipt's date, `consideration_amount` = the whole
    receipt, `cumulative_before`, `taxable_amount` = the part above the
    threshold, `rate_percent` (the without-PAN rate when `customers.pan_number`
    is blank, `without_pan` true), `tcs_amount` = taxable × rate rounded to
    the paisa, `status` COLLECTED, `journal_entry_id`,
    `receivable_transaction_id`;
  - journal `TCS-<receipt number>` (`source_module` `tcs`), **Dr 1100 / Cr
    2500 TCS Payable** — never 2200;
  - receivable row `TCS` for the amount, remarks "Tax collected at source
    under 206C(1H)." — the buyer now owes the tax;
  - **audit** `tcs.collected` (the figures), beside the receipt's own rows
    and two `finance.journal_entry.*` and a
    `customer.receivable_transaction_posted`.
- **Reversed when the receipt is reversed** (§11.15): `status` REVERSED,
  `reversal_journal_entry_id` = `TCS-…-REV` (Dr 2500 / Cr 1100), the TCS
  receivable row reversed by its stored deltas; **audit** `tcs.reversed`.
  The row stays, and later receipts' `cumulative_before` is not recomputed.
- **Check:**
  ```sql
  select s.settlement_number, s.settlement_date, s.status as receipt_status,
         c.code, c.pan_number, t.consideration_amount, t.cumulative_before,
         t.taxable_amount, t.rate_percent, t.without_pan, t.tcs_amount, t.status,
         j.reference_number, rj.reference_number as reversal
  from   fx_<suffix>_s.tcs_collections t
  join   fx_<suffix>_s.settlements s on s.id = t.settlement_id
  join   fx_<suffix>_s.customers c   on c.id = t.customer_id
  left join fx_<suffix>_s.journal_entries j  on j.id = t.journal_entry_id
  left join fx_<suffix>_s.journal_entries rj on rj.id = t.reversal_journal_entry_id
  order  by s.settlement_date, s.settlement_number;

  select (select sum(tcs_amount) from fx_<suffix>_s.tcs_collections where status = 'COLLECTED') as collected,
         (select sum(p.credit_amount - p.debit_amount) from fx_<suffix>_s.gl_postings p
          join fx_<suffix>_s.ledger_accounts a on a.id = p.ledger_account_id where a.code = '2500') as payable_2500;
  ```
  The two figures of the second query should agree.
- **Confirmed:** the `selling-paid` rows of §11.14 (2.42 and 3.42 at 1%, no
  PAN); WHOLE01's 39 collections, three REVERSED with their `-REV`
  journals, and 2500 at 648.24 = the 648.24 still collected;
  `fx_t0919l8ca_g` RC-2026-2027-000002 (1,500.00 today, 5.00 on the 500.00
  above a 1,000 threshold) and RC-2026-2027-000003 (100.00 dated
  2026-09-01, `cumulative_before` 1,500.00 — the later receipt — charged
  1.00, D-CMP-7). The shared store's RC-2025-2026-000014 (2026-02-12) counts
  RC-2025-2026-000013 (2026-02-21) the same way.

### 13.12 What compliance does not write, and is often looked for

| You might expect | What actually happens |
| --- | --- |
| A stored GSTR-1 or 3B, or a record of what was filed | Nothing; both are recomputed on every read (§13.6) |
| A sales return in GSTR-1 or 3B | Not read (D-CMP-2) |
| IGST on a bill to another state | CGST + SGST; nothing sends `SALES_INTERSTATE` (D-CMP-1) |
| A link from an execution log to its document | None; logs carry no document or line id (§13.4) |
| `execution_mode` other than SIMULATION | Never written (§13.4) |
| An audit row for a tax record deleted, restored or re-statused | None (D-CMP-9) |
| A second row for a re-registered invoice | The one row is rewritten (D-CMP-6) |
| A LIVE registration | Never; `portal_for("LIVE")` raises |
| A TCS collection written by the TCS screen | None; only a receipt writes one (§13.11) |
| TCS in 2200 Output Tax | 2500 TCS Payable |
| A GST return permission | Returns are gated on `SALES_VIEW` |
| A registration or e-way bill row on the platform | Firm store only |

### 13.13 Checked against live rows, and not

- **Confirmed in `fx_t0919l8ca_g`** (built 2026-09-19 00:51 UTC, then
  driven): the template's counts and 20 audit rows; the fixture's GSTR-1
  and 3B exactly as TC-COMP-001 and 003 expect; A and B registered, C not;
  every probe named in §13.1, 13.3, 13.4, 13.6–13.11. **What the probes
  left:** a customer `T0919L8CA-KA` with a Karnataka GSTIN and bill
  SI-2026-2027-000004 (CGST/SGST); B cancelled with its registration
  withdrawn and its e-way bill GENERATED; A registered twice;
  `INTERSTATE_GST_18` version 2 INACTIVE beside version 1 ACTIVE; a DRAFT
  rule `CMPIMP_A`; TCS switched on at a 1,000 threshold with two collections
  from `T0919L8CA-B2C`; SR-2026-2027-000001 completed against C.
- **Confirmed in `fx_t0916irn8_g` and `fx_t09167ru4_g`:** the fixture's
  registrations and TC-COMP-006's withdrawn bill; zero-tax bills registered.
- **Confirmed on WHOLE01, the shared store and ELEC01 (read only):** every
  registration and bill SANDBOX with `SBX` references; `mode` NOT NULL with
  no default in every store checked; 2500 agreeing with collections in
  WHOLE01; the half-paisa gap between GSTR-1's components and 2200;
  9 completed returns in WHOLE01 (2,853.09 of tax) and 14 in the shared store
  (2,341.44) reversing output tax that no return deducts; WHOLE01's
  SI-2026-2027-000008, dated 2026-08-12 and cancelled 2026-09-13, now
  missing from August; no IGST line and no interstate buyer anywhere.
- **Across every store:** no rule with two ACTIVE versions other than the
  probe's, no `execution_mode` but SIMULATION, no FAILED or LIVE
  registration.
- **Not seen in a live row:** a portal refusal (FAILED); a withdrawal refused
  after 24 hours; a B2CL bill; a registered buyer's credit note in CDNR in a
  compliance store; an unplaced invoice; a profile superseded by a rate
  change; a rule deleted or restored; an export; a TCS row under a
  preceding-year turnover below the threshold; the GST template failing
  half-way.

---

## 14. Configuration — how one firm differs from the next (TC-CONF-001 to 004 and 006, TC-FIELD-001 to 014, TC-FIRM-010 to 012, TC-CUST-003, TC-GRANT-005)

Read on 2026-09-19 off `app/business` (`framework_service.py`, `gating.py`,
`attribute_service.py` and the router), `app/document_framework`
(`document_framework_service.py`, `transactional_document_service.py`,
`print_template_service.py` and the router), `app/uom` (`uom_service.py` and
the router), the geography half of `app/sales` (`territory_service.py`), the
settings services — `workflow_settings_service.py`, `credit_control.py`,
`loyalty_service.py` — `app/firms/services/readiness.py` (the firm side),
`identity_service.py` (preferences), and the desktop's
`numbering_series_editor.dart`, `print_template.dart` and
`desktop_preferences_service.dart`. Tax configuration is §13 and is not
repeated; identity and roles are §15. `docs/MODULE_STATUS.md` files these
modules under "Configuration"; the rules they can break are the persistence,
tenancy and "a flag the caller sets" ones in `CLAUDE.md`. Then checked,
read-only, against every store on the local server that holds these tables,
and driven on a `config-firm` store built for the pass (`fx_t09193ugd_r`)
against the running backend. §14.19 says which claims a live row confirmed
and which it could not; a claim marked *(not seen in a live row)* was read off
the code only.

**The running backend was the build of 2026-09-19 before #500 (D-FIN-9)** and
it stopped at about 07:08 IST, before the pass had finished driving; it was not
restarted. Where #500 changes what a receipt does, the text says so.

### 14.0 Before you look

- **Stores.**

  | Case | Fixture | Schema |
  | --- | --- | --- |
  | TC-CONF-001 to 003 | `firm-admin`, `sales-executive` | `test_fixtures` — the numbering series are TEST01's own |
  | TC-CONF-004, 006 | `config-firm` | **`fx_<suffix>_r`** — firm `<SUFFIX>-R`, "Ready <suffix>" |
  | TC-FIELD-001 to 012 | `ready-firm` | `fx_<suffix>_r` |
  | TC-FIELD-013, 014 | `shared-pair` | **`firm_shared`** — filter on `firm_id` |
  | TC-FIRM-010, 012 | `unfinished-firm` | `fx_<suffix>_f` |
  | TC-CUST-003, TC-GRANT-005 | `customer-master`, `loyalty-viewer` | `test_fixtures` |

  The fixture's **Tables** line prints the schema. For WHOLE01 put
  `wholesale_hub`; for MEDI01, FOOD01, TESTSH1 or TESTSH2 put `firm_shared`.
- **Three kinds of configuration table, and only one carries a firm.**

  | Tables | `firm_id`? | So in `firm_shared` |
  | --- | --- | --- |
  | `business_profiles`, `business_features`, `business_modules`, `profile_features`, `profile_modules`, `attribute_definitions`, `category_attribute_rules`, `uoms`, `uom_groups`, `uom_group_units`, `packaging_types`, `uom_industry_templates`, `geo_countries` … `geo_localities` | **no** | one set for MEDI01, FOOD01, TESTSH1 and TESTSH2 together — an edit made "in" one of them is made in all four |
  | `firm_business_profiles`, `*_attribute_values`, `document_*`, `uom_conversion_rules`, `product_packaging_levels`, `business_profile_uom_defaults` (a firm's own row), `sales_workflow_settings`, `credit_control_settings`, `loyalty_settings`, `sales_hierarchy_configs` | yes | per firm |
  | `user_preferences` | per **user** | `platform` only |

  A dedicated store has its own copy of every catalogue, so "the WHOLESALE
  profile" is a different row, possibly with different features, in each
  store: WHOLE01's enables `SERIAL_NUMBER`, the fixture stores' does not.
- **Where the audit rows go, and one kind nobody can read.** Every write
  here audits into the store the request's session opened — the firm's own —
  except preferences (`platform`). But the business-framework catalogue
  (`attribute_definition.*`, `category_attribute_rule.*`, `business_profile.*`,
  `business_feature.*`, `business_module.*`) and geography
  (`sales_territory.geo.*`) record **`firm_id` null**, and Settings → Audit
  Logs filters a firm's trail on `firm_id`, so those rows are on no screen
  (D-CFG-13). Query them by action with no firm filter:
  ```sql
  select created_at, action, entity_type, entity_id, firm_id,
         before_data::jsonb - '_meta' as before, after_data::jsonb - '_meta' as after
  from   fx_<suffix>_r.audit_logs
  where  action ~ '^(business_|attribute_definition|category_attribute|firm_business_profile|document_|uom\.|sales_territory\.geo)'
     or  entity_type in ('SalesWorkflowSettings', 'CreditControlSettings', 'loyalty_settings')
  order  by created_at desc;
  ```
- **No ledger effect anywhere in this section.** Configuration writes no
  journal. What it changes is how later documents post — the numbers they
  carry (§14.7), the stock a conversion moves (§14.11), what a loyalty point
  is worth when spent (§14.15) — and those effects land on the documents'
  own journals.
- **What points at what.**

  | From | Column | To |
  | --- | --- | --- |
  | `firm_business_profiles` | `firm_id` (no foreign key — `firms` is platform), `business_profile_id` | `business_profiles` |
  | `profile_features`, `profile_modules` | `business_profile_id`, `feature_id` / `module_id` | the catalogue |
  | `attribute_definitions` | `applicable_business_profile_id` (NULL = every profile), `applicable_category` (NULL = every category) | `business_profiles` |
  | `category_attribute_rules` | `category_code` (text, not an id), `attribute_definition_id`, `business_profile_id` | — |
  | `<entity>_attribute_values` | `firm_id`, `attribute_definition_id`, the owner (`product_id`, `customer_id`, `vendor_id`, `branch_id`, `warehouse_id`, `uom_id`, `tax_profile_id`) | the definition and the record |
  | `document_numbering_rules` | `document_type_id` | `document_type_definitions` |
  | `document_number_sequences` | `numbering_rule_id`, `scope_signature` (year, branch and company, joined by bars) | the rule — **the counter documents actually use** |
  | `document_lifecycle_events` | `document_type_id`, `source_document_id` (no foreign key), `source_module_code` | the document |
  | `uom_conversion_rules` | `product_id` (NULL = firm-wide), `from_uom_id`, `to_uom_id`, `version_number` | `products`, `uoms` |
  | document lines | `conversion_version` (a **number**, not an id) | the rule with that version — re-read when stock moves (§14.11) |
  | `sales_workflow_settings` | `default_branch_id`, `default_warehouse_id` | `branches`, `warehouses` — unchecked (D-CFG-14) |

### 14.1 Business profiles, features and modules — the catalogue (TC-CONF-004)

Administration → Configuration → Business Profiles → **Profiles**, **Feature
Flags**, **Modules**. All under `/api/v1/business-framework`, **platform
administrator only**, written into the store the caller's `X-Firm-ID` opens.
Each call commits on its own.

- **Create / edit / delete** a profile, feature or module inserts, updates or
  soft-deletes one row of `business_profiles`, `business_features` or
  `business_modules`. Edits are partial (`exclude_unset`) and carry the row's
  `version` as an `ETag`. Audit `business_profile.created` / `.updated` /
  `.deleted` (a profile's `before_data` = `code` and `status`; `after_data` on
  create = `code`), and `business_feature.*` / `business_module.*` with **no
  data at all**.
- **Refused, nothing written:** a code already used; deleting a profile a
  live firm is assigned; deleting a feature or module a profile still
  enables; enabling a feature whose `is_implemented` is false — "These
  features are not implemented yet and cannot be enabled: IMEI." (the six:
  `IMEI`, `KITCHEN_MANAGEMENT`, `PRESCRIPTION_REQUIRED`, `PROJECT_MANAGEMENT`,
  `RECIPE_MANAGEMENT`, `SERVICE_CONTRACTS`). `is_implemented` is not on the
  write schema, so it cannot be switched through the API.
- **Which features a profile enables** — Profiles → edit → Enabled features,
  `PUT /profiles/{id}/features` with the whole list of ids. Existing
  `profile_features` rows are set `is_enabled` true or false in place; ids not
  yet mapped get a new row. `PUT /profiles/{id}/modules` does the same to
  `profile_modules`, `is_enabled` and `is_visible` together. Audit
  `business_profile.features.updated` / `.modules.updated`, **no data** — the
  trail cannot say which feature was switched (D-CFG-13).
- **Setting a profile's `is_default`** clears it on every other profile in
  the store first. Clearing it on the default leaves the store with none
  (D-CFG-19).
- **Check** — what each profile enables, the explicit rows and the
  catalogue's `default_enabled` for the rest:
  ```sql
  select p.code as profile, f.code as feature, f.is_implemented, f.default_enabled,
         pf.is_enabled as mapped, coalesce(pf.is_enabled, f.default_enabled) as resolves_to
  from   fx_<suffix>_r.business_profiles p
  cross  join fx_<suffix>_r.business_features f
  left   join fx_<suffix>_r.profile_features pf
         on pf.business_profile_id = p.id and pf.feature_id = f.id and pf.is_deleted = false
  where  p.code = 'WHOLESALE' and f.is_deleted = false and f.is_active = true
  order  by f.code;
  ```
- **Confirmed** in `fx_t09193ugd_r`: WHOLESALE's features re-saved unchanged at
  07:04:29 IST — one `business_profile.features.updated`, `firm_id` null,
  both sides empty. Every store carries 12 profiles with `GENERIC` the
  default, except WHOLE01, whose default is `WHOLESALE`.

### 14.2 Assign a profile to a firm (TC-FIRM-010, TC-FIRM-012)

Set up → Business profile, or Business Profiles → **Profile Assignment**.
`PUT /business-framework/firms/{id}/profile-assignment`, platform only, opened
on **the named firm's** store (`firm_store_session`), whatever firm the
caller has selected.

- **Inserts** `firm_business_profiles` the first time (`business_profile_id`,
  `is_active`, `effective_from` = now, `notes`) and **updates the same row in
  place** after: `business_profile_id`, `is_active`, `notes`. `effective_from`
  never moves, and the previous profile is not kept anywhere — the row says
  "RETAIL since the day it was first WHOLESALE" (D-CFG-13).
- **`notes` and `is_active` are written whether sent or not**; the Set up
  panel sends no notes, so choosing a profile there clears any the Profile
  Assignment screen had written (D-CFG-21).
- **Audit, firm trail:** `firm_business_profile.created` / `.updated`,
  `firm_id` set, `after_data` = `business_profile_id` only, never a
  `before_data`. **Nothing on the platform trail** — §6's "no row" was wrong,
  and is corrected there.
- **What it changes at once** — nothing stored; everything read. The gate
  and every form resolve the new profile on the next request: fields scoped
  to the old one stop being offered and keep their values (TC-FIELD-005),
  features the new one lacks are refused on the next write that fills them.
- **Profile Assignment's grid** (`GET /firm-profile-assignments`) opens every
  firm's store in turn and names a store it cannot read rather than blanking
  the row.
- **Check** (the firm's own store — MEDI01 and FOOD01 both read `firm_shared`):
  ```sql
  select a.firm_id, p.code, a.is_active, a.effective_from, a.notes, a.version, a.updated_at
  from   fx_<suffix>_f.firm_business_profiles a
  join   fx_<suffix>_f.business_profiles p on p.id = a.business_profile_id
  where  a.is_deleted = false;
  ```
- **Confirmed:** one `firm_business_profile.created` in each of 48 fixture
  stores; `pt0916ppotc` flipped WHOLESALE ↔ RETAIL six times in four minutes
  with `effective_from` still the first assignment and six `.updated` rows
  with no before side; TEST01 five `.updated` rows.

### 14.3 What a firm resolves to — the gate, `/active-features`, `/active-modules` (reads)

- **Writes nothing.** Three places answer "which profile is this firm on",
  and they do not share one implementation:

  | Where | Used by | No assignment and no default profile |
  | --- | --- | --- |
  | `resolve_profile` (`gating.py`) | `require_feature`, `assert_feature_fields`, tax, UOM, products, territory | nothing enforced |
  | `_resolved_profile_id` (`framework_service.py`) | `/active-features`, `/active-modules` — what the desktop renders | **any ACTIVE profile**, whichever the database returns first |
  | `_profile_id` (`attribute_service.py`) | the custom fields a form offers and a save demands | no profile-scoped field applies |

  Every store has a default today, so the three agree on the ground (D-CFG-19).
- **The gate is write-only and field-level.** `require_feature` stops a
  POST/PUT/DELETE on `batch-serial` endpoints (`BATCH_TRACKING`,
  `SERIAL_NUMBER`); `assert_feature_fields` refuses a write that *fills* a
  field of a feature the profile lacks (`EXPIRY_TRACKING`, `WARRANTY`,
  `BARCODE`, `DRUG_LICENSE`, `ATTACHMENTS`, `VEHICLE_TRACKING`, …) — "This
  firm's business profile does not enable WARRANTY, so warranty_end, warranty_start cannot
  be set." **`require_module` is applied to no route**, so a module's
  endpoints answer whatever the profile says; the desktop hiding the module
  is the only effect (`docs/BUSINESS_PROFILE_FRAMEWORK.md`, "Status").
- **`/active-features?firm_id=` reads the named firm's assignment in the
  caller's store**, not the named firm's. Asked from `fx_t09193ugd_r` for
  WHOLE01 it answered `ATTACHMENTS`, `BARCODE` — GENERIC, the fixture store's
  default — where WHOLE01's own store answers six features. The desktop never
  sends `firm_id` (D-CFG-19).

### 14.4 Custom fields — definitions and category rules (TC-FIELD-001 to 006, 011, 014)

Business Profiles → **Dynamic Attributes** and **Mandatory Attributes**.
`/business-framework/attribute-definitions` and
`/business-framework/category-attribute-rules`, platform only; one commit per
call; the rows land in the store `X-Firm-ID` opens, which in `firm_shared` is
all four firms' catalogue at once (TC-FIELD-014).

- **A definition** inserts one `attribute_definitions` row: `code`, `name`,
  `entity_type` (PRODUCT, CUSTOMER, VENDOR, BRANCH, WAREHOUSE, UOM,
  TAX_PROFILE), `data_type` (TEXT, NUMBER, DATE, BOOLEAN), `mandatory`,
  `validation_rule` (`allowed_values` for a TEXT list), `applicable_category`,
  `applicable_business_profile_id`, `is_active`. Edits are partial; delete is
  a soft delete with **no check for values** already stored. Audit
  `attribute_definition.created` / `.updated` / `.deleted`, `firm_id` null,
  **no data** (D-CFG-13).
- **A rule** inserts `category_attribute_rules`: `category_code` (the code as
  text), `attribute_definition_id`, `business_profile_id` (NULL = every
  profile), `is_mandatory`. Audit `category_attribute_rule.*`, the same empty
  shape.
- **Two ways a field becomes required, enforced differently.** The
  definition's `mandatory` refuses a missing field *and* an empty one
  ("Attribute CFG_LICENCE is required and cannot be empty."). A category
  rule's `is_mandatory` refuses only a *missing* one — the same field sent
  blank is stored as a row with every value column null (D-CFG-5). The
  desktop form refuses the blank; the API does not.
- **Changing a definition strands, it does not migrate:** a new `data_type`
  leaves the old value in the old typed column (TC-FIELD-006); a narrower
  profile or category takes values out of every read while they stay in the
  table; `docs/BACKLOG.md` §16 is the proposal.
- **Check:**
  ```sql
  select d.code, d.entity_type, d.data_type, d.mandatory, d.applicable_category,
         p.code as profile, d.is_active, d.is_deleted, d.version,
         (select string_agg(r.category_code || case when r.is_mandatory then ' (required)' else '' end, ', ')
          from fx_<suffix>_r.category_attribute_rules r
          where r.attribute_definition_id = d.id and r.is_deleted = false) as rules
  from   fx_<suffix>_r.attribute_definitions d
  left   join fx_<suffix>_r.business_profiles p on p.id = d.applicable_business_profile_id
  order  by d.entity_type, d.code;
  ```
- **Confirmed** in `fx_t09193ugd_r`: `CFG_COLD_ID` (PRODUCT, TEXT, not
  mandatory) with a required rule on `FXCHL`, and `CFG_LICENCE` (CUSTOMER,
  mandatory) — three audit rows at 07:03 IST, `firm_id` null, empty. Live
  catalogue sizes: 13 definitions and 7 rules in a fresh fixture store; 6 and
  3 in WHOLE01; 6 and 8 in `firm_shared`.

### 14.5 Custom-field values on a record (TC-FIELD-007 to 010, 013)

The **Custom fields** tab of a customer, vendor, branch or warehouse, the
product's **Attributes** tab, and `attributes` on the API write schemas of
all seven owners (UOMs and tax profiles are API-only).

- **Read first:** `GET /business-framework/attribute-definitions/applicable?entity_type=`
  — membership in the firm is the whole gate — answers `definitions` (what
  this firm's profile gets) and `mandatory_ids`.
- **A save carrying `attributes` replaces the record's whole set** in its
  value table (`product_attribute_values`, `customer_attribute_values`,
  `vendor_attribute_values`, `branch_attribute_values`,
  `warehouse_attribute_values`, `uom_attribute_values`,
  `tax_profile_attribute_values`): one row per definition, the value in
  exactly one of `value_text`, `value_number`, `value_date`, `value_boolean`,
  **never JSON**. A value that changed is **overwritten in place**
  (`version` +1); a definition no longer sent is **soft-deleted**; a new one
  is inserted with the calling firm's `firm_id`. **A save without
  `attributes` leaves them alone**; an empty list clears them.
- **Refused, nothing written:** a definition that does not apply ("One or
  more attributes do not apply to this record."); a required one missing
  ("Required attributes are missing.", ids in
  `details.missing_attribute_definition_ids`); a value of the wrong type or
  off the list ("Attribute STORAGE_TEMPERATURE must be one of: Ambient,
  Chilled, Frozen."). A value the record already holds is accepted even when
  its definition was deactivated, narrowed or had that choice withdrawn.
- **Audit:** none of its own. The owner's `customer.updated`,
  `product.created`, … carries no attributes, so **a changed licence number
  is on no trail** — the value row's `updated_at` and `updated_by` are the
  only record, and the old value is gone (D-CFG-13).
- **A unit is shared, its values are not:** in `firm_shared` a UOM is one row
  for every firm, and its values are keyed by `firm_id`, so TESTSH1's note on
  `BAG` is invisible to TESTSH2 (TC-FIELD-013).
- **Lists read them one record at a time.** Customers, vendors, products,
  warehouses and units build each row's `attributes` with its own query;
  `values_for_many` exists and nothing calls it (D-CFG-20).
- **Check:**
  ```sql
  select c.code, d.code as field, v.value_text, v.value_number, v.value_date, v.value_boolean,
         v.is_deleted, v.version, v.updated_at
  from   fx_<suffix>_r.customer_attribute_values v
  join   fx_<suffix>_r.customers c             on c.id = v.customer_id
  join   fx_<suffix>_r.attribute_definitions d on d.id = v.attribute_definition_id
  order  by c.code, d.code;
  ```
  Put `product_attribute_values` / `products` / `product_id` for a product.
- **Confirmed** in `fx_t09193ugd_r`: product `CFGCH1` saved in category
  `FXCHL` with `CFG_COLD_ID` sent as `""` — one value row, every column null;
  `CFGCH0` without it refused; a customer with `CFG_LICENCE` blank refused.

### 14.6 Numbering series — create, edit, retire, preview (TC-CONF-001 to 003)

Administration → Configuration → **Numbering Series**.
`/api/v1/document-framework/numbering-rules`: list and preview need only
membership; create, edit and **Retire** need `SETTINGS_UPDATE` (held by
`FIRM_ADMIN` alone). Each call commits.

- **Create** inserts `document_numbering_rules`: `document_type_id`, `code`,
  `name`, `prefix`, `suffix`, `separator`, `include_financial_year`,
  `include_branch_code`, `include_company_code`, `auto_reset` (restart each
  financial year), `manual_allowed`, `sequence_padding`, `next_sequence`
  (the desktop's "Start numbering at"), `format_pattern`, `is_default`,
  `is_active`. Audit `document_numbering_rule.created` (`code`,
  `document_type_id`). **No counter row yet** — that is written by the first
  document (§14.7).
- **Refused, nothing written:** a code the type already has; a yearly restart
  whose number does not show the year — "This rule restarts its numbering
  every financial year, so the number has to include the year …"
  (TC-CONF-002), judged on the rule as it will be; a prefix starting `JV-`,
  reserved for hand journals since #500.
- **Not refused:** a prefix or pattern that issues another type's numbers —
  a receipt series patterned `GRN-<firm>-HO-{financial_year}-{sequence}`
  previewed `GRN-T09193UGD-R-HO-2026-2027-000001`, the number a goods receipt
  already had, and every receipt was then refused "A journal entry with this
  reference number already exists." (D-CFG-8; since #500 a receipt steps
  over the taken number, every other document is still refused).
- **Edit** (`PUT`) is partial. `before_data` = `code`, `name`,
  `next_sequence`; **`after_data` is empty**, so the trail cannot say that
  the prefix or the restart changed (D-CFG-13). The desktop omits
  `next_sequence` for an existing series, but the API accepts it — and
  `last_scope_signature` and `document_type_id` — and the counter ignores
  it: `next_sequence` set to 3 on a series at 51 read 3 on the rule, the
  preview still said `…000051`, the next receipt took `…000051` and the rule
  went back to 52 (D-CFG-18).
- **"Use this series by default" and "Active" are stored and never read.**
  The series a document uses is the first live rule of its type the database
  returns (§14.7, D-CFG-6).
- **Turning the yearly restart off and on again restarts the series at
  000001.** Off, the counter continues under a year-less key and the yearly
  one is retired; on again, the yearly key finds nothing live and starts at 1
  — a number already issued — so every document of that type is refused
  "The request conflicts with existing data. Please retry.", and a retry is
  issued the same number (D-CFG-7).
- **Retire** soft-deletes the rule (audit `document_numbering_rule.deleted`,
  no data); its counters stay. The desktop warns that the firm "will not be
  able to raise one" without another series, and that is true in a sharper
  way than it says: the next document creates a fresh default series at 1 in
  the same request, collides, and rolls both back (D-CFG-7). The way out is
  **New series** with "Start numbering at" past the last number issued.
- **Preview** (`GET /numbering-rules/{id}/preview`) writes nothing and
  answers the next number from the live counter — the same both times
  (TC-CONF-003).
- **Check:**
  ```sql
  select t.code as type, r.code, r.prefix, r.format_pattern, r.auto_reset, r.include_financial_year,
         r.is_default, r.is_active, r.is_deleted, r.next_sequence as rule_says,
         s.scope_signature, s.next_sequence as counter_says, s.is_deleted as counter_retired
  from   test_fixtures.document_numbering_rules r
  join   test_fixtures.document_type_definitions t on t.id = r.document_type_id
  left   join test_fixtures.document_number_sequences s on s.numbering_rule_id = r.id
  order  by t.code, r.created_at, s.created_at;
  ```
  More than one live rule for a type is D-CFG-6; `rule_says` ≠ `counter_says`
  is a rule edited under its counter.
- **Confirmed** in `fx_t09193ugd_r` (RECEIPT and PURCHASE_ORDER):
  - `CFG_SECOND` (`RX`, not default, inactive) beside `RECEIPT_DEFAULT`: four
    receipts `RC-2026-2027-000002` to `000005`; then `CFG_SECOND` default and
    active, `RECEIPT_DEFAULT` neither — the next receipt was still
    `RC-2026-2027-000006`, from the inactive series;
  - `RECEIPT_DEFAULT` restart off → `RC-2026-2027-000007`, on → 409 twice;
    `PURCHASE_ORDER_DEFAULT` the same: `PO-T09193UGD-R-HO-2026-2027-000002`,
    then 409 twice. Its counters read `||` (live, 8) and `2026-2027||`
    (retired, 7);
  - both defaults retired → 409 on the next receipt and purchase order;
    `CFG_RECOVER` created at 50 → `RC-2026-2027-000050`;
  - no store other than WHOLE01 (three retired `PHYSICAL_COUNT` probes of
    2026-09-04) holds a second, retired, inactive or non-default rule.

### 14.7 Issuing a number — what every document create writes

Not a screen of its own: every numbered document (§9 to §12) goes through
`_ensure_document_setup` and `reserve_number` on its create.

- **The first document of its kind in a firm** inserts
  `document_type_definitions` (`code` e.g. `RECEIPT`, `configuration.module`),
  its `document_state_definitions` (one per state the module declares), and a
  `<TYPE>_DEFAULT` numbering rule — `include_financial_year` true,
  `auto_reset` true, the module's prefix, branch and company codes only where
  the module prints them. Audits `document_type.created`,
  `document_state.created` ×n, `document_numbering_rule.created`, in the
  document's own request.
- **Which rule:** the first live rule of the type, **with no ordering and no
  regard to `is_default` or `is_active`** (D-CFG-6). In practice the oldest
  wins while PostgreSQL keeps it in place.
- **Reserving** locks the rule, finds or creates the counter for the scope
  signature — `year|branch|company`, each part kept only when the rule counts
  on it — and moves `document_number_sequences.next_sequence` +1, then copies
  it to `document_numbering_rules.next_sequence` and
  `last_scope_signature`. A counter under an older key shape is carried over
  and retired, once.
- **A typed number bypasses all of it.** Every create takes one
  (`order_number`, `po_number`, `grn_number`, `invoice_number`,
  `delivery_note_number`, `return_number`, `credit_note_number`,
  `settlement_number`) and uses it as sent: `manual_allowed` — "Allow a
  number to be typed in", off by default — is read by no module. A number
  typed **ahead of the counter** is issued again by the series when it gets
  there, and that document is refused for good (D-CFG-2).
- **A failed create rolls its reservation back**, so the counter does not
  move and the retry is issued the same number. Since #500 a receipt or
  payment steps over up to 50 numbers a journal or settlement already holds;
  no other document does.
- **Lifecycle events** — `document_lifecycle_events`, one per create, edit
  and transition, `source_module_code` the module's type code — are written
  by the modules and carry no audit row of their own. The type and state rows
  are **not read** by any module: `allows_edit`, `is_terminal`,
  `allows_print`, `transition_rules` and the type's `is_active` change
  nothing (D-CFG-18).
- **Check** — one document's number, the counter that issued it, and its
  timeline:
  ```sql
  select po_number, created_at from fx_<suffix>_r.purchase_orders order by created_at;

  select e.occurred_at, e.action, e.from_state, e.to_state, e.document_number, e.source_module_code
  from   fx_<suffix>_r.document_lifecycle_events e
  where  e.document_number = 'PO-<SUFFIX>-R-HO-2026-2027-000001'
  order  by e.occurred_at;
  ```
- **Confirmed** in `fx_t09193ugd_r`: `CFG_PO_SERIES` created at 10 with
  `manual_allowed` false; `PO-T09193UGD-R-HO-2026-2027-000011` typed and
  accepted; the next order `…000010`; the two after it refused "Purchase
  order number already exists in this firm." Receipts the same on the
  running build: `RC-2026-2027-000062` typed, `…000061` issued, then 409
  "A journal entry with this reference number already exists." twice.

### 14.8 Document types, states and the timeline — platform administration

`/api/v1/document-framework/document-types`, `/document-states` and
`POST /documents/{id}/events` — platform administrator only.

- Create, edit (partial) and soft-delete one row each; audit
  `document_type.created` / `.updated` / `.deleted`, `document_state.*`
  (`before_data` code, name, sort order; no `after_data`). A hand-written
  timeline event inserts `document_lifecycle_events` with no audit row.
- **Deleting a type the modules use** makes the next document of it create a
  new type, new states and a new default series at 1 — the collision of
  §14.6 *(not seen in a live row)*.
- **Check:**
  ```sql
  select t.code, t.is_active, t.is_deleted, count(s.id) as states
  from   wholesale_hub.document_type_definitions t
  left   join wholesale_hub.document_state_definitions s on s.document_type_id = t.id and s.is_deleted = false
  group  by t.id order by t.code;
  ```

### 14.9 Print templates

§11.13 has the fields. One `document_print_templates` row per firm and
`document_type` (the path segment, upper-cased and **not checked** against
the document types), inserted on the first save and **replaced whole** after
— every field is written, sent or not. The desktop's Print settings omits
`header_note`, so each desktop save clears one written through the API
(D-CFG-18). Audit `document_print_template.created` / `.updated`, `after_data`
= `document_type` only: a change to **`bank_details`** — the account a
customer pays into — leaves no before or after (D-CFG-13). `SETTINGS_UPDATE`.
WHOLE01 holds the one live row.

### 14.10 Units, groups, packaging types, packaging levels, barcodes

Administration → Configuration → **UOM & Packaging**.
`/api/v1/uom-framework`: `UOM_MANAGE` for units, groups and industry
templates, `PACKAGING_MANAGE` for packaging types and levels,
`CONVERSION_RULE_MANAGE` for rules and default units (§14.11) — all held by
`FIRM_ADMIN` and `FIRM_MANAGER`. `UOM_IMPORT` and `UOM_EXPORT` are seeded and
enforced nowhere. One commit per call.

- **Units** — `POST` / `PUT` / `DELETE /uoms`: one `uoms` row (`code`,
  `name`, `dimension`, `is_decimal_allowed`, `status`, …), **no `firm_id`**.
  Edit is partial; delete is refused while a conversion rule, group, packaging
  level, a product's seven unit slots or a profile default names the unit —
  not while only a document line does (D-CFG-21). **No audit row** for any of
  them.
- **Groups** (`uom_groups`; `uom_group_units` has no endpoint), **packaging
  types** (`packaging_types`) and **industry templates**
  (`uom_industry_templates`, which nothing reads) — the same shape, shared,
  unaudited. In `firm_shared` any firm's administrator edits them for all
  four firms (D-CFG-9).
- **Whole-number units are not enforced.** `is_decimal_allowed` on a unit and
  a product's `allow_fraction` / `allow_decimal` are stored and read by no
  document: 1.5 BOX is accepted (D-CFG-11).
- **Packaging levels** — `POST` / `PUT` / `DELETE
  /products/{product_id}/packaging-levels`: one `product_packaging_levels`
  row with the caller's `firm_id` and the product **from the path, not
  checked** against the firm (D-CFG-9). No audit row.
- **Barcode lookup** (`GET /barcode-lookup?code=`) reads only: the firm's
  levels' `barcode`, `gtin`, `ean`, `upc`, `qr_code`, then products'
  `barcode`; two matches are refused by name.
- **Check** (units are the store's; levels are the firm's):
  ```sql
  select code, name, dimension, is_decimal_allowed, status, is_deleted, version, updated_by
  from   firm_shared.uoms order by code;

  select l.firm_id, p.code as product, p.firm_id as product_firm, l.level_name,
         l.conversion_to_base_factor, l.barcode, l.created_by
  from   firm_shared.product_packaging_levels l
  join   firm_shared.products p on p.id = l.product_id
  where  l.is_deleted = false;
  ```
  `firm_id` ≠ `product_firm` is D-CFG-9.
- **Confirmed:** 19 units in `firm_shared` and WHOLE01, 36 in TEST01 and the
  fixture stores (migration 0021 added 17, with near-duplicates such as
  KILOGRAM/KG); no unit deleted or inactive anywhere; five packaging levels
  written through the API and not one audit row for a unit, group, type or
  level in any store; no level on another firm's product.

### 14.11 Conversion rules and default units (TC-CONF-006)

UOM & Packaging → **Conversion Rules**, and Business Profiles → **Default
units**.

- **Create** inserts `uom_conversion_rules` (`firm_id`, `product_id` or NULL
  for firm-wide, `from_uom_id`, `to_uom_id`, `conversion_factor`,
  `rounding_mode`, `precision_scale`, `effective_from` / `effective_to`,
  `version_number`, `status`). Audit `uom.conversion.created`, **no data**.
  Two rules for one product, pair and version are refused by the unique key;
  two **firm-wide** ones are not — the key includes the nullable
  `product_id`, and PostgreSQL treats NULLs as distinct (D-CFG-10).
- **Which rule a line gets:** ACTIVE, live, in force on the document's date,
  the product's own before the firm-wide one — ranked explicitly, not by NULL
  order — then the highest `version_number`. The line stores the factor and
  the **version number** it used.
- **Edit changes the version in place.** `PUT` accepts the factor, the pair,
  the product, the dates and the version number of a published rule and keeps
  its `version_number`. When stock later moves for a document drafted under
  it, the inventory service re-reads the rule **by that version number** and
  multiplies by the factor it has now — so the receipt line says one thing and
  the stock another (D-CFG-1). Audit `uom.conversion.updated`, **no data**;
  delete is a soft delete, audit `uom.conversion.deleted` with `before_data`
  `status` and `version` (the version *number*).
- **Default units** — `PUT /profiles/{id}/defaults?apply_to=FIRM|PROFILE`:
  one `business_profile_uom_defaults` row, the firm's own (`firm_id` set,
  `CONVERSION_RULE_MANAGE`) or the profile's (`firm_id` NULL,
  `PLATFORM_SETTINGS` too). The profile-wide row reaches only firms in **the
  caller's store**, though the endpoint's docstring and
  `docs/UOM_FRAMEWORK.md` say every firm on the profile (D-CFG-21). Audit
  `uom.profile_default.created` / `.updated`, no data. They reach a product
  only by pre-filling its form.
- **Check:**
  ```sql
  select p.code as product, fu.code as from_uom, tu.code as to_uom, r.conversion_factor,
         r.version_number, r.status, r.effective_from, r.effective_to, r.is_deleted, r.version, r.updated_at
  from   fx_<suffix>_r.uom_conversion_rules r
  left   join fx_<suffix>_r.products p on p.id = r.product_id
  join   fx_<suffix>_r.uoms fu on fu.id = r.from_uom_id
  join   fx_<suffix>_r.uoms tu on tu.id = r.to_uom_id
  order  by fu.code, tu.code, r.product_id nulls last, r.version_number desc;

  select l.current_receipt_quantity, l.conversion_factor, l.conversion_version,
         t.quantity as stock_moved, t.entered_quantity
  from   fx_<suffix>_r.goods_receipt_lines l
  join   fx_<suffix>_r.goods_receipts g on g.id = l.goods_receipt_id
  join   fx_<suffix>_r.inventory_transactions t
         on t.reference_number = g.grn_number and t.transaction_type = 'GOODS_RECEIPT';
  ```
  `stock_moved` ≠ `current_receipt_quantity` × `conversion_factor` is D-CFG-1.
- **Confirmed** in `fx_t09193ugd_r`: `<SUFFIX>-DET`'s own PACK→KG rule at
  factor 1; a receipt drafted for 10 PACK (line factor 1, version 1), the rule
  edited to 2, the receipt completed — `inventory_transactions.quantity`
  **20**, `product_valuations` 20 at 2,000.00, journal Dr 1200 / Cr 2300
  **2,000.00** against an order worth 1,000.00; the line still reads factor 1;
  two `uom.conversion.updated` rows with nothing in them. WHOLE01 holds two
  firm-wide PACK→KG rules at version 1, one of them deleted.

### 14.12 Geography — countries to localities

Masters → Geography; `/api/v1/sales-territories/geo/countries`, `/states`,
`/districts`, `/cities`, `/postal-codes`, `/localities`. Reads need
`TERRITORY_VIEW`; **every write is platform-only** and lands in the store
`X-Firm-ID` opens. `docs/GEOGRAPHY_MASTERS.md` is the reference.

- **Create** inserts one `geo_*` row (no `firm_id` — one per store) and
  writes **no audit row**. **Edit** replaces the row from the write schema
  (an omitted `is_active` reactivates it; omitted codes clear); **delete** is
  a soft delete, refused while a child level, an address master, a branch, a
  warehouse or a route profile names the place — **not** a customer's or
  vendor's address, and not a tax row (D-CFG-12). Audits
  `sales_territory.geo.<kind>.updated` / `.deleted`, `after_data` = `name`,
  no before, **`firm_id` null** — on no screen (D-CFG-13).
- Migration `20260917_0137` seeds the 36 Indian states in every store; the GST
  template adds India to a store with no country (§13.2).
- **Check:**
  ```sql
  select 'country' as level, code, name, is_active, is_deleted from wholesale_hub.geo_countries
  union all select 'state', code, name, is_active, is_deleted from wholesale_hub.geo_states
  union all select 'city', code, name, is_active, is_deleted from wholesale_hub.geo_cities
  order  by 1, 2;

  select count(*) as customers_on_a_retired_state
  from   wholesale_hub.customer_addresses a
  join   wholesale_hub.geo_states s on s.id = a.state_id
  where  s.is_deleted and not a.is_deleted;
  ```
- **Confirmed:** countries/states/districts/cities/postcodes/localities —
  `firm_shared` 1/36/2/1/0/0, TEST01 1/38/2/2/0/0 (six places created through
  the API, no audit row), WHOLE01 3/37/1/1/1/1 with two countries and a state
  retired and six geo audit rows, all `firm_id` null; no customer, vendor or
  tax row on a retired place in any store.

### 14.13 Sales stages — `sales_workflow_settings` (TC-FIN-009)

Sales → Sales Orders → **Stages**. `GET` / `PUT
/api/v1/sales-orders/workflow-settings`; the read needs `SALES_VIEW`, the
write `SALES_MANAGE_SETTINGS` (`FIRM_ADMIN`, `FIRM_MANAGER`; not
`SALES_MANAGER`). §11.20 has what the stages do to a sale.

- **One row per firm**, inserted on the first save and **replaced whole**
  after: `quotation_stage`, `sales_order_stage`, `delivery_note_stage`,
  `default_branch_id`, `default_warehouse_id`. A firm with no row types every
  stage; the read does not insert one. Audit **`CREATE`** / **`UPDATE`**,
  `entity_type` `SalesWorkflowSettings`, all five on both sides (D-SELL-24).
- **An omitted default is written as null**, so a client that sends only the
  three switches clears both defaults; the desktop dialog, if its read
  fails, saves the whole chain with no defaults (D-CFG-14).
- **The defaults are not checked** — another firm's branch in `firm_shared`,
  a deleted one, a warehouse outside the branch — and deleting a branch or
  warehouse never looks here (D-CFG-14). `quotation_stage` is read by no
  backend code; only the desktop hides the module.
- **A draft bill made while the delivery-note stage is off treats any
  approved, undispatched note of the order as its own** — it dispatches it on
  approval and cancels it if the draft is cancelled (D-CFG-16) *(not seen in
  a live row)*.
- **Check:** §11.20's query, and:
  ```sql
  select w.*, b.code as branch, b.firm_id = w.firm_id as branch_is_the_firms, b.is_deleted as branch_deleted,
         wh.code as warehouse, wh.branch_id = w.default_branch_id as warehouse_in_branch
  from   wholesale_hub.sales_workflow_settings w
  left   join wholesale_hub.branches b    on b.id = w.default_branch_id
  left   join wholesale_hub.warehouses wh on wh.id = w.default_warehouse_id;
  ```
- **Confirmed:** seven rows in 51 stores (MEDI01, FOOD01, WHOLE01 and four
  fixture stores); none in TEST01. WHOLE01's `UPDATE` of 2026-09-02 22:52:33
  IST turned every stage back on **and cleared both defaults** that the one
  before it had set. Only `fx_t09197ev9_e` carries a default today (MAIN,
  with no branch).

### 14.14 Credit policy — `credit_control_settings` (TC-CUST-003, TC-FIN-008)

Customers → **Settings**. `GET` / `PUT /api/v1/customers/credit-settings`;
the read needs `CUSTOMER_VIEW` (so the dialog opens read-only for a seller),
the write `CUSTOMER_MANAGE_SETTINGS` (`ACCOUNTANT`, `FIRM_ADMIN`,
`FIRM_MANAGER`).

- **One row per firm**, full replace, every field required: `enforcement`
  (`OFF`, `WARN`, `BLOCK`), `warn_at_percent`, `block_at_percent` (warn ≤
  block). No row = WARN at 80, never block; the read does not insert. Audit
  `CREATE` / `UPDATE`, `entity_type` `CreditControlSettings`, the three
  figures both sides. §11.6 has what it does at approval.
- **The limit itself is on the customer**, and `CUSTOMER_UPDATE` —
  `SALES_MANAGER` holds it — edits it: raising a customer's limit, or setting
  it to 0 ("no limit"), lifts a BLOCK for that customer through the ordinary
  customer save (D-CFG-17).
- **Check:**
  ```sql
  select enforcement, warn_at_percent, block_at_percent, version, updated_at
  from   fx_<suffix>_s.credit_control_settings;
  ```
- **Confirmed:** six rows — BLOCK in MEDI01 and three `policy-firm` stores,
  WARN in FOOD01 and WHOLE01; ten audit rows. In the three BLOCK fixture
  stores a customer's limit moved 0 → 1,000 through `customer.updated`.

### 14.15 Loyalty scheme — `loyalty_settings` (TC-GRANT-005, TC-INCENT-005)

Masters → Loyalty → **Scheme settings**. `GET` / `PUT /api/v1/loyalty/settings`;
`LOYALTY_VIEW` / `LOYALTY_MANAGE_SETTINGS` (`FIRM_ADMIN`, `FIRM_MANAGER`).

- **One row per firm**, partial update: `is_enabled`, `points_per_amount`
  (per 100 billed), `amount_per_point`, `minimum_redemption_points`,
  `expiry_months`. No row = off; the read does not insert. Audit
  `loyalty.settings_changed`, the five figures both sides (none before on
  the first save).
- **What a change reaches.** `points_per_amount` and `expiry_months` reach
  only bills approved after it — an earned batch stores its points, its cost
  and its expiry. **`amount_per_point` reaches every point already held**:
  earning posts points × the rate then (Dr 5700 / Cr 2600), a lapse or a
  cancelled bill releases the batch's stored cost, but a redemption or an
  adjustment values points at the rate **now**. Raise the rate and 2600 is
  debited more than was ever credited; lower it and a residue never clears
  (D-CFG-3) *(not seen in a live row — no store has changed its rate)*.
- **Check:**
  ```sql
  select is_enabled, points_per_amount, amount_per_point, minimum_redemption_points, expiry_months, version, updated_at
  from   fx_<suffix>_s.loyalty_settings;

  select created_at, before_data->>'amount_per_point' as was, after_data->>'amount_per_point' as now
  from   fx_<suffix>_s.audit_logs
  where  action = 'loyalty.settings_changed'
  order  by created_at;
  ```
- **Confirmed:** 22 rows, every one 2 points per 100, 1.00 a point, minimum
  50, 24 months; 68 `loyalty.settings_changed` rows, 46 of them in
  `firm_shared` and WHOLE01 changing nothing — every seeder run re-saves the
  scheme.

### 14.16 Set up panel, the firm side — the default branch and readiness (TC-FIRM-011, 013)

§6 has the platform side and §12.1 Open the books.

- **Create head office and main warehouse**
  (`POST /firms/{id}/create-default-branch`, platform only) inserts, in the
  firm's store, `branches` `HO` (`is_default` **true**) and `warehouses`
  `MAIN` (`is_default` **false**), each only if the firm has none. Audits
  `branch.created` (`code`, `status`) and `warehouse.created` (`code`,
  `branch_id`) in the firm's trail, and `firm.default_branch_created` on the
  platform. Three commits.
- **MAIN is not a default warehouse**, so a firm finished from the panel
  that turns both the order and note stages off is refused every bare bill —
  "This branch has no default warehouse, so a bill cannot decide where its
  goods ship from." — while readiness reads the step as done (D-CFG-15).
- **Readiness** (`GET /firms/{id}/readiness`) writes nothing. Its profile step
  counts an assignment whether or not `is_active`; its people step counts
  active memberships of users who are themselves deleted (D-CFG-21).
- **Check:**
  ```sql
  select b.code as branch, b.is_default as branch_default, w.code as warehouse, w.is_default as warehouse_default
  from   fx_<suffix>_r.branches b
  left   join fx_<suffix>_r.warehouses w on w.branch_id = b.id and w.is_deleted = false
  where  b.is_deleted = false;
  ```
- **Confirmed:** `MAIN` with `is_default` false and no default warehouse in its
  branch in 49 stores — every fixture store, TEST01, TEST02, LEARN01,
  SNTEST01 and `pt0916ppotc`; 49 `firm.default_branch_created` rows on the
  platform.

### 14.17 Preferences — the server's and the desktop's

§3 has the columns.

- **Server:** `platform.user_preferences`, one row per user. **`GET
  /me/preferences` inserts it** on first read, with no audit row; `PATCH` is
  partial and writes `user_preferences.updated` with no before, no after and
  no `firm_id` — every screen change (`default_landing_page`), firm switch
  (`default_firm_id`) and appearance change (D-CFG-21). `POST
  /me/preferences/reset` writes `user_preferences.reset`, also empty.
- **Desktop:** `%APPDATA%\.agency_platform\desktop_preferences.json` on
  Windows (`AppStorage` elsewhere), per operating-system account, not per
  user: remembered and recent usernames, server URL and recent servers, the
  cached palette, mode and contrast, window state, last workspace, sidebar
  and grid density, `workspace_state` (global search, inventory and the
  inventory import wizard), and `server_preferences` — a cache that sign-in
  **replaces whole** from the server. Nothing in it reaches a table.
- **Check:**
  ```sql
  select action, count(*), count(firm_id) as with_firm,
         count(*) filter (where jsonb_typeof(after_data::jsonb) = 'object'
                          and (after_data::jsonb - '_meta') <> '{}'::jsonb) as with_after
  from   platform.audit_logs
  where  entity_type = 'user_preferences'
  group  by action;
  ```
- **Confirmed:** 14 preference rows, the busiest at `version` 334; 521
  `user_preferences.updated` rows, none with a before, an after or a firm.

### 14.18 What configuration does not write, and is often looked for

| You might expect | What actually happens |
| --- | --- |
| A catalogue change on the firm's Audit Logs screen | Written with `firm_id` null into the firm's store; on no screen (§14.0) |
| The old value of a changed custom field, bank detail, conversion factor or series setting | Overwritten; the audit row names the record and not the change (D-CFG-13) |
| The profile a firm ran on last month | Overwritten in place; `effective_from` still the first day (§14.2) |
| The default series deciding the number | The first live series the database returns (§14.7) |
| "Allow a number to be typed in" stopping a typed number | Read by nothing (§14.7) |
| A counter row when a series is created | Written by the first document (§14.6) |
| A module switched off refusing its endpoints | `require_module` is on no route (§14.3) |
| An audit row for a unit, group, packaging type, packaging level, geography place created | None (§14.10, §14.12) |
| A journal from any configuration change | None; its effects reach the next documents' journals (§14.0) |
| A lifecycle state stopping an edit or a print | State rows are read by nothing (§14.7) |
| A settings row when a firm has none | Defaults answered, nothing inserted — except preferences and the sales hierarchy, whose reads insert (§14.17) |

### 14.19 Checked against live rows, and not

- **Confirmed in `fx_t09193ugd_r`** (`config-firm`, built 2026-09-19 06:57
  IST, then driven until 07:08): the RECEIPT series chosen with its default
  and active flags off and another series' on; the restart toggled on
  RECEIPT and PURCHASE_ORDER and every document refused after; both defaults
  retired and refused; the recovery at 50; `next_sequence` written through
  the API and ignored; a receipt series shaped like goods receipts refused by
  the journal; a typed purchase order number and a typed receipt number
  blocking the series; the conversion factor edited under a draft receipt —
  20 KG and 2,000.00 for a line of 10 at factor 1; 50 received against an
  order for 10 and 80 billed against 50 (D-CFG-4); a category-mandatory field
  saved blank; the catalogue audit rows with `firm_id` null; WHOLE01's
  features answered as GENERIC's from another store. **What the probes left:**
  retired series `RECEIPT_DEFAULT`, `CFG_SECOND`, `CFG_RECOVER`,
  `CFG_GRN_LOOKALIKE` and `PURCHASE_ORDER_DEFAULT`; `CFG_RECOVER2` (receipts,
  blocked at `…000062`) and `CFG_PO_SERIES` (orders, blocked at `…000011`);
  stock of `<SUFFIX>-DET` at 70 KG; `PI-CFG-OVER-1` approved for 9,440.00.
- **Confirmed across every store on the server (read only):** 12 profiles and
  a default in each; one assignment per fixture firm; seven stage rows, six
  credit policies, 22 loyalty schemes, none with a changed rate; no second
  live numbering series for a type outside the probe store; `MAIN` never a
  default warehouse where the panel made it; geography and catalogue audit
  rows `firm_id` null in WHOLE01 (20 catalogue, 6 geography) and
  `firm_shared` (10 catalogue).
- **Not seen in a live row:** a loyalty rate change and a redemption after
  it (the backend stopped before it could be driven); a bare bill refused for
  want of a default warehouse; a draft bill adopting a hand-raised note; a
  document type deleted; a retired geography place under a customer; a unit
  deleted while a draft uses it; two live firm-wide conversion rules at one
  version; a packaging level on another firm's product; an
  `/active-features` answer from a store with no default profile; a sales
  manager lifting a BLOCK by raising a limit. ELEC01 (`agency_electrolink`)
  was not queried for this section.

---

## 15. Identity, firms and audit — who may act, where a firm lives, and what the trail keeps (TC-SESS-001 to 011, TC-TIER-001 to 003, TC-TMPL-001 to 015, TC-HIRE-001 to 004, TC-USER-001 to 009, TC-RTIER-001 to 008, TC-ROLE-001 to 009, TC-LOOK-001 to 007, TC-ME-001 to 008, TC-PLAT-001 to 005, TC-GRANT-001 to 008, TC-AUDIT-001 to 006, TC-FIRM-001 to 009 and 013 to 017, TC-ISO-004)

Read on 2026-09-19 off `app/identity` (`identity_service.py`, the router,
`system_seed.py`, `retention.py`), `app/core/security/authorization.py`,
`app/common/scope.py`, `app/common/firm_metadata.py` and the `/firm-members`
router, `app/firms` (`firm_service.py`, the router), `app/core/tenancy`
(`lifecycle.py`, `migrations.py`, `resolvers.py`) and `app/common/audit`
(`audit.py`, `reader.py`, the router). Sections 2 to 7 are pass 1 — written
off the same code on 2026-09-15 and never checked against a row; they stay
the per-screen quick reference, this section re-reads them against the
tables, adds what they left out, and says where they were wrong (§15.13).
Preferences are §14.17 and the firm side of the Set up panel §14.16; neither
is repeated. `docs/ACCESS_CONTROL_FRAMEWORK.md` and
`docs/TENANCY_AND_STORES.md` are the references; the rules these modules can
break are the Authorization, Tenancy and audit-trail ones in `CLAUDE.md`.

Checked read-only against `platform`, every schema of `agency_platform` that
holds an `audit_logs` table and `electrolink_ops` in `agency_electrolink`, then
driven against the running backend (identity code unchanged since #425 of
2026-09-17) on three fixture runs — `platform-operator` `t0919tkcy`,
`platform-admin` `t0919wwzu`, `two-firm-user` `t0919subq` — and one probe firm,
`IDNPROBE1`, created and deleted within a second and never provisioned. **Two
findings are privilege escalations and were deliberately not driven**
(D-IDN-1, D-IDN-2); they are described from the code, and TC-TIER-003 is the
case that would show the first. A claim marked *(not seen in a live row)* was
read off the code only.

### 15.0 Before you look

- **Stores.** Identity and the firm registry live in `platform` and nowhere
  else; a firm's own store holds none of it (`_PLATFORM_TABLES` in
  `app/core/tenancy/lifecycle.py` is what provisioning prunes). Checked: `users`,
  `user_firms`, `roles`, `firms` and `error_reports` exist in `platform` alone.
  **`user_templates` and `user_template_roles` are the exception** — not on
  that list, so every migrated store keeps a copy: 55 firm schemas, each
  holding the 11 seeded templates, and nothing reads them (D-IDN-10). The real
  ones are `platform.user_templates`.

  | What | Where | Why |
  | --- | --- | --- |
  | people, roles, grants, memberships, designations, tokens, sign-in history | `platform` | one person, many firms |
  | the firm registry and where each firm lives | `platform.firms`, `platform.firm_storage_mappings` | read before any firm is resolved |
  | the firm's business, and its own audit rows | the firm's schema (§1.1) | the trail is per store |
  | identity and firm administration's audit rows | `platform.audit_logs`, `firm_id` set only sometimes (§15.10) | written on the platform session |

- **What points at what.**

  | From | Column | To |
  | --- | --- | --- |
  | `user_firms` | `user_id`, `firm_id`, `is_primary`, `is_active` | a membership; one active primary per user (`UQ_user_firms_active_primary`) |
  | `user_roles` | `user_id`, `role_id`, **`firm_id`** | **NULL = the global tier** (applies in every firm the person belongs to); a firm = that firm only |
  | `roles` | `firm_id`, `is_system` | NULL + system = seeded; NULL + custom = a platform administrator's role; a firm = that firm's own role |
  | `role_permissions` | `role_id`, `permission_id` | the codes a role grants |
  | `platform_admins` | `user_id`, `scope` | the designation, `PLATFORM` or `ALL_FIRMS` — no endpoint writes it |
  | `refresh_tokens` | `user_id`, `token_hash`, `revoked_at`, `replaced_by_id` | a rotation chain |
  | `login_history` | `user_id` (NULL for an unknown address), `attempted_email`, `outcome`, `failure_reason` | every attempt |
  | `password_history` | `user_id`, `password_hash` | the reuse window |
  | `firm_storage_mappings` | `firm_id`, `deployment_mode`, `database_name`, `schema_name`, `connection_profile`, `provisioned_at` | where the firm's rows are |
  | `audit_logs` | `entity_id`, `actor_id`, `firm_id` — **no foreign keys** | whatever `entity_type` names, in whichever store |

- **How a grant reaches a request.** Nothing is re-read per request except
  the user's liveness and `authorization_version`; everything else is in the
  access token `_issue_tokens` minted at sign-in:

  | Claim | Built from |
  | --- | --- |
  | `platform_admin`, `platform_admin_scope` | a live `platform_admins` row |
  | `permissions` (global) | an `ALL_FIRMS` administrator: every code; a `PLATFORM` one: the 33 operator codes; anybody else: global-tier rows of **custom or platform** roles |
  | `firm_permissions[firm]` | per **active membership**: that firm's rows, plus global-tier rows of **seeded firm roles** — for a `PLATFORM` administrator too |
  | `authorization_version` | `users.authorization_version`; a token carrying another number is refused |
  | `password_change_required` | `users.force_password_change`; every permission check fails while it is set |

  Global-tier **custom** roles land in `permissions` and not in
  `firm_permissions`, although `docs/ACCESS_CONTROL_FRAMEWORK.md` Part 4 says
  both (D-IDN-10).
- **No ledger effect anywhere in this section**, and nothing here writes to a
  firm's store except the Set up actions (§6, §12.1, §13.2, §14.16).

### 15.1 Sign in, refresh, sign out (TC-SESS-001 to 003, 005)

§2 has the columns. Confirmed:

- **Sign in** inserts `login_history` per attempt and, on success, one
  `refresh_tokens` row, updates `users.last_login_at` and clears the counters,
  and audits `identity.login` with no firm and no data. The lockout is judged
  **before** the password and the account's state **after** it, so a wrong
  password never names a state (D-2-1). Outcomes across the platform:
  1,302 `success`, 103 `failed`/`invalid_credentials`, 31 `locked`/`account_locked`
  (refused while locked), 12 `locked`/`invalid_credentials` (the attempt that
  locked), 6 `failed`/`account_unavailable`.
- **Refresh** revokes the presented token with one guarded `UPDATE`
  (`revoked_at` null and unexpired, `rowcount` must be 1), inserts the next and
  points the old row's `replaced_by_id` at it; audit `identity.refresh`.
  Presenting a revoked token again revokes every token the person holds,
  bumps `authorization_version` and audits
  `identity.refresh_token_reuse_detected` (8 rows) — which also fires for a
  token revoked by sign-out or by an ordinary revocation, and for two refreshes
  racing (D-IDN-10) *(not seen in a live row)*. A refresh for an inactive or
  expired account is refused by name.
- **Sign out** sets `revoked_at` on the one refresh token and audits
  `identity.logout`. It does **not** bump `authorization_version`, so the access
  token already issued stays good for its 15 minutes.
- **Per request**, `get_current_principal` refuses a user who is deleted,
  inactive, past `expires_at` or on another `authorization_version`. Checked:
  no live refresh token belongs to a deleted or inactive user.
- **Check:**
  ```sql
  select l.created_at, l.attempted_email, l.outcome, l.failure_reason,
         u.failed_login_attempts, u.locked_until
  from   platform.login_history l
  left   join platform.users u on u.id = l.user_id
  where  l.attempted_email like '<suffix>.%'
  order  by l.created_at desc;

  select t.created_at, t.expires_at, t.revoked_at, t.replaced_by_id is not null as rotated
  from   platform.refresh_tokens t join platform.users u on u.id = t.user_id
  where  u.email = '<suffix>.target@fixtures.local'
  order  by t.created_at desc;
  ```
  Never select `token_hash` or `password_hash` into a note; count them.

### 15.2 Passwords — change, reset, history, a forced change (TC-SESS-006, 011, TC-ME-008)

- **Change own** (`POST /auth/change-password`, any signed-in user) inserts
  the **old** hash into `password_history`, writes the new one, clears
  `force_password_change`, revokes every token and bumps
  `authorization_version` — the session that changed it ends too. Audit
  `identity.password_changed`. Refused: a wrong current password; the policy
  (12 characters, upper, lower, digit, symbol); the current or any of the last
  five (`AGENCY_SECURITY_PASSWORD_HISTORY_COUNT`).
- **Reset somebody else's** (`POST /users/{id}/password`) is **any** platform
  administrator's — the route takes the designation and never looks at the
  target. It inserts the old hash, sets the new one, sets
  `force_password_change` as asked, clears the lock and the failed count,
  revokes everything and bumps the version. Audit `user.password_reset`,
  `after_data` `force_password_change`, no firm. Refused only for the caller's
  own account. **A `PLATFORM` operator may reset an `ALL_FIRMS`
  administrator's password — or rename, deactivate or expire them through
  `PATCH /users/{id}` — and sign in as them** (D-IDN-2) *(not driven)*.
- **A forced change** puts `password_change_required` on the token, and every
  `require_permission` and `require_platform_admin` check fails until it is
  done; only the routes that need no code — change-password, `/me`, `/me/firms`
  and preferences — answer.
- **Confirmed:** 16 `password_history` rows in all; 8 live users waiting on a
  forced change; 9 `identity.password_changed` and 7 `user.password_reset`
  rows, none carrying a firm. `USER_RESET_PASSWORD`, `USER_LOCK` and
  `USER_UNLOCK` are seeded and read by no route — reset is the designation's,
  unlock is `USER_UPDATE`'s (D-IDN-10).

### 15.3 Users — create, edit, deactivate, delete, restore (TC-SESS-004, 005, 007 to 010, TC-USER-001 to 005, 009)

§3 has the columns and the three-or-four audit rows one Save writes.

- **Which firm the rows name.** `create_user` audits `user.created` with the
  caller's firm scope — the firm for a firm administrator, **null for any
  platform administrator**, whichever firm the new person is then put in. The
  same holds for `user.updated` and `user.deleted`; `user.restored` and
  `user.password_reset` never carry one. So a person a platform administrator
  hires into TEST01 is on TEST01's Audit Logs screen only through their role
  grants in that firm (§15.10, D-IDN-5).
- **Edit** writes `before_data` `full_name` and `is_active` and **no
  `after_data`**; a changed mobile, expiry or unlock is not on the trail. Every
  edit bumps `authorization_version`, so an edited person is signed out even
  when only their mobile moved.
- **Deactivate** is `is_active = false` through the same edit; the next
  request fails authentication, the next refresh is refused "This account is
  inactive…". Checked: one live inactive user, and no live refresh token for
  any inactive or deleted one.
- **Delete** leaves `user_firms`, `user_roles`, `user_preferences` and the
  tokens (all revoked) in place; **Restore** is one flag, platform only,
  refused while a live account holds the address.
- **Email** is unique among live accounts: service check plus
  `UQ_users_email_active` (`WHERE is_deleted = false`), both present;
  addresses are case-folded before either sees them.
- **A firm administrator cannot edit or delete somebody who works elsewhere**
  (`_assert_exclusive_firm_user`) — but only an **active** membership
  elsewhere counts, so a person switched off in the other firm is editable and
  deletable platform-wide from this one (D-IDN-10) *(not seen in a live row —
  no inactive membership exists today)*.
- **Check:**
  ```sql
  select u.email, u.is_active, u.expires_at, u.is_deleted, u.force_password_change,
         u.authorization_version, u.version, u.updated_at
  from   platform.users u
  where  u.email like '<suffix>.%'
  order  by u.created_at;

  select a.created_at, a.action, a.firm_id,
         a.before_data::jsonb - '_meta' as before, a.after_data::jsonb - '_meta' as after
  from   platform.audit_logs a
  join   platform.users u on u.id = a.entity_id
  where  u.email = '<suffix>.target@fixtures.local'
  order  by a.created_at;
  ```
- **Confirmed:** 266 users before this pass, 143 of them deleted; 286
  `user.created` rows, 41 with a firm; 173 `user.deleted`, 1 with a firm; 28
  `user.restored` and 28 `user.updated`, the updates each with a before and
  none with an after.

### 15.4 Memberships, the primary firm and the switcher (TC-USER-006 to 008, TC-LOOK-001 to 007, TC-ME-002 to 004, 007, TC-PLAT-003, TC-TIER-002)

§3 *Set memberships* has the rows. What the tables show:

- **`user.firms_set` never carries a firm** and carries no data — which firms
  were added or removed is not recorded anywhere but in the rows' own
  timestamps. 1,121 such rows on the platform; **0** on TEST01's merged trail,
  although most of them staffed TEST01 (D-IDN-5).
- **A `PLATFORM` operator cannot staff a firm.** `_firms_the_caller_may_staff`
  reads the firms where the caller holds `USER_CREATE` in `firm_permissions`;
  an operator's token carries the two memberships with **0 codes** each, so
  `PUT /users/{id}/firms` answers 422 "You can only assign firms you
  administer." and `GET /users/{id}/firms` answers an empty list for a person
  in two firms — User-Firm Assignments is blank for them. `PUT
  /users/{id}/firms/{firm}/roles` is refused the same way. **Hire like this
  person** is not: with no firm named, it copies the source's memberships with
  no reach check at all (D-IDN-6).
- **Primary firm.** `PUT /me/primary-firm` clears the old flag, flushes, sets
  the new one; audit `user.primary_firm_set` with the firm (2 rows). A scoped
  administrator's membership save never moves it (TC-USER-008).
- **The switcher** (`GET /me/firms`) is active memberships in live, active
  firms, primary first — or every live, active firm for `ALL_FIRMS`, ranked
  with an explicit `case` rather than by NULL order. A `PLATFORM` operator gets
  their memberships only (TC-TIER-002).
- **`/firm-members`** (any member, platform session) lists active,
  undeleted memberships of undeleted users — **including a user switched off**
  (`User.is_active` is not filtered), who is then offered as a salesman
  (D-IDN-10). One such member exists today.
- **Check:**
  ```sql
  select f.code, uf.is_primary, uf.is_active, uf.is_deleted, uf.deleted_at, uf.version, uf.updated_by
  from   platform.user_firms uf
  join   platform.firms f on f.id = uf.firm_id
  join   platform.users u on u.id = uf.user_id
  where  u.email = '<suffix>.shared@fixtures.local'
  order  by uf.created_at;
  ```
- **Confirmed:** the `t0919tkcy` operator's token — `PLATFORM`, 33 global
  codes, TEST01 and TEST02 in `firm_permissions` with nothing in either; its
  `GET /users/{clone}/firms` answered `[]` and its re-save of the clone's two
  existing memberships 422.

### 15.5 Roles and permissions — custom roles, system roles, reserved codes (TC-ROLE-001 to 009)

§4 has the rows. Confirmed and added:

- **Create** inserts `roles` with `firm_id` = the caller's firm scope (null
  for a platform caller) and `is_system` false; audit `role.created`, no data.
  Refused: a reserved code, case-folded (`platform_admin` and the sixteen
  seeded codes, TC-ROLE-003), and **any code any role has ever used** — the
  check reads every role, deleted or not, in every firm, and
  `UQ_roles_code` is a plain unique index. A deleted role's code can never be
  reused, and the 409 tells one firm that another has a role by that name
  (D-IDN-9).
- **System roles** refuse edit, permission changes and delete through the
  API ("System roles cannot be modified."). `RoleUpdate` carries only name,
  description and `is_active`, so a code cannot be renamed into a reserved one.
- **Permissions** (`role.permissions_set`) replace `role_permissions` in place
  and bump every holder's version. A firm caller cannot name one of the 22
  `PLATFORM_PERMISSION_CODES`, and `list_permissions` never offers them.
- **The audit rows name the role and nothing else** — no code, no before, no
  after, and `role.permissions_set` does not say which codes moved; a role of
  a firm deleted by a platform administrator records **no firm** (D-IDN-5).
- **TC-ROLE-008, as the owner drove it:** `t0918nhew-night-desk` — the holder's
  `authorization_version` went 1 → 2 on `role.permissions_set` at 21:35:23 IST
  on 2026-09-18 (firm set), and the next click signed them out.
- **TC-ROLE-009, as the owner drove it:** deleting a held role is not refused;
  `roles.is_deleted` true, the holder's `user_roles` row left in place, the next
  token carries none of its codes and the sidebar is empty. Recorded in
  `docs/DEFECTS.md` as an open decision, not a defect. Today 3 live
  `user_roles` rows point at deleted roles (`t0916vgt6`, `t09169tk8`,
  `t09168etd`), each holder's version moved by the delete.
- **Check:**
  ```sql
  select r.code, r.firm_id, r.is_system, r.is_active, r.is_deleted, r.version,
         (select count(*) from platform.user_roles ur where ur.role_id = r.id and not ur.is_deleted) as holders,
         (select string_agg(p.code, ',' order by p.code) from platform.role_permissions rp
          join platform.permissions p on p.id = rp.permission_id
          where rp.role_id = r.id and not rp.is_deleted) as codes
  from   platform.roles r
  where  r.code like '<suffix>-%';
  ```

### 15.6 Grants in two tiers, `authorization_version`, and the platform narrowing (TC-RTIER-001 to 008, TC-TIER-001 to 003, TC-GRANT-001 to 008, TC-ISO-004)

- **Two tiers, two writers.** `PUT /users/{id}/roles` writes the tier the
  caller owns — global for a platform caller, their own firm for a firm
  caller — and `_replace_global_user_roles` / `_replace_scoped_user_roles`
  each touch only their own rows (TC-RTIER-002). `PUT
  /users/{id}/firms/{firm}/roles` writes one named firm, needs a membership
  there, and records `user.firm_roles_set` with that firm (166 rows, all with
  a firm).
- **What the global tier will take.** A firm caller is held to their firm's
  own roles and the seeded firm roles. **A platform caller is held to
  nothing**: the global path checks only that the ids exist, so another firm's
  own custom role, or a template belonging to one firm applied with no firm
  named, lands as a global row whose codes then apply in every firm the person
  belongs to (D-IDN-3) *(no such row today: all 5 rows of firm-owned roles are
  firm-scoped)*.
- **`authorization_version`** moves on: own password change, a reset, a user
  edit or delete, roles set in either tier, memberships set, a template
  applied, a role edited, deleted or its permissions set (every holder), a
  permission edited or deleted (every holder of every role carrying it), and
  refresh reuse. It does **not** move on restore (the tokens died at delete),
  primary-firm choice, a template's own edit, or a firm switched off or
  deleted — the membership check refuses an inactive or deleted firm on every
  request instead. Checked against the rules: no change that alters what a
  token grants is missing a bump.
- **The `PLATFORM` narrowing is in all three places** — `Principal.has_permission`
  and `optional_firm_scope` exempt `ALL_FIRMS` alone, and the stuffed claim is
  the 33 operator codes (the `t0919tkcy` token: 33). **But the operator holds
  `ROLE_ASSIGN` and the global tier is theirs to write, their own row
  included**: `firm_permissions` takes global-tier seeded firm roles for a
  `PLATFORM` administrator's memberships, so an operator who gives themselves
  `FIRM_ADMIN` holds it in every firm they are a member of on their next
  sign-in (D-IDN-1) *(not driven)*.
- **The identity routes take their firm from the raw header.** `_firm_scope`
  in the identity router is `principal.firm_id` — the `X-Firm-ID` a caller
  sent, checked against nothing. A firm administrator is still held back,
  because their codes are in `firm_permissions` for their own firm only; but
  anybody whose code is in the **global** claim — a global custom role, a
  platform role such as `SYSTEM_AUDITOR` — lists, creates people in, and
  assigns roles in any firm by naming it, with no membership (D-IDN-7) *(no
  such holder today: 0 global custom-role rows, 0 platform-role holders)*.
  Firm-owned routes do not have this hole: `app/common/scope.py` checks the
  membership (TC-ISO-004).
- **Seeded and enforced nowhere:** `FIRM_CREATE`, `FIRM_UPDATE`,
  `FIRM_DELETE`, `FIRM_ACTIVATE`, `FIRM_DEACTIVATE`, `PERMISSION_CREATE`,
  `PERMISSION_UPDATE`, `PERMISSION_DELETE`, `USER_RESET_PASSWORD`,
  `USER_LOCK`, `USER_UNLOCK` — their routes take the designation, so holding
  them grants nothing (D-IDN-10). Every code a route does enforce is seeded
  (`test_every_enforced_permission_code_is_seeded`).
- **TC-GRANT-001 to 008** are grants, not writes: `FIRM_ADMIN`'s
  `role_permissions` rows for the five groups `20260906_0130` added. What each
  screen then writes is §11.17 (credit notes), §11.18 (proforma), §13.8
  (e-invoice), §14.15 and §11.19 (loyalty), §13.11 (TCS).
- **Check** — who holds what, in which tier:
  ```sql
  select u.email, coalesce(f.code, '(every firm)') as tier, r.code as role, ur.is_deleted, ur.created_at
  from   platform.user_roles ur
  join   platform.users u on u.id = ur.user_id
  join   platform.roles r on r.id = ur.role_id
  left   join platform.firms f on f.id = ur.firm_id
  where  u.email like '<suffix>.%'
  order  by u.email, tier, r.code;

  select u.email, pa.scope, pa.is_deleted
  from   platform.platform_admins pa join platform.users u on u.id = pa.user_id
  where  u.email like '<suffix>.%';
  ```

### 15.7 Hiring — templates and "Hire like this person" (TC-TMPL-001 to 015, TC-HIRE-001 to 004)

§3 and §5 have the rows. Confirmed and added:

- **Apply a template** is `set_user_roles` plus `user_template.applied`
  (`template_id`, `template_code`, `role_ids`, `role_codes`); 34 rows, 24 with
  that data (the 10 without predate it), 29 with a firm.
- **A clone by a platform administrator widens the source's access.** With no
  firm named, `_roles_held_by` returns every role the source holds **in any
  tier**, and `set_user_roles` writes them all to the **global** tier; the
  memberships are copied separately. Driven on `t0919subq`: the source holds
  SALES_EXECUTIVE **in TEST01** and CUSTOMER_SUPPORT globally, in TEST01 and
  TEST02; the clone (`t0919subq.clone`, 11:50:39 IST) holds **both roles
  globally**, in both firms — a sales executive in TEST02, where the source is
  not (D-IDN-3).
- **A clone is three commits, not one.** `create_user` commits (11:50:39.660),
  `set_user_roles` commits (…39.846), the memberships and `user.cloned` commit
  (…39.943). A failure after the first leaves an account holding the address
  with no roles or firms, and the retry is refused 409 (D-IDN-8) *(the failure
  not seen in a live row)*.
- **The memberships a clone copies write no audit row at all** —
  `_copy_memberships` calls no `record_audit` — and a platform
  administrator's clone records `user.created`, `user.roles_set` and
  `user.cloned` with no firm, so none of the three is on TEST01's or TEST02's
  trail (D-IDN-5). §3 said the clone also wrote `user.firms_set`; it does not.
- **Check** — a clone beside its source:
  ```sql
  select u.email, coalesce(f.code, '(every firm)') as tier, r.code
  from   platform.user_roles ur
  join   platform.users u on u.id = ur.user_id
  join   platform.roles r on r.id = ur.role_id
  left   join platform.firms f on f.id = ur.firm_id
  where  u.email in ('<suffix>.twofirm@fixtures.local', '<suffix>.clone@fixtures.local')
    and  not ur.is_deleted
  order  by u.email, r.code;
  ```
  A role that reads `(every firm)` on the clone and a firm on the source is
  D-IDN-3.

### 15.8 Firms — create, edit, delete, and where a firm lives (TC-FIRM-001 to 005, 016, 017)

§6 has the columns. Every `/firms` route is `require_platform_admin()`, either
reach; all run on the platform session.

- **Create** inserts `firms` and `firm_storage_mappings` and audits
  `firm.created` (`after_data` `code`) with the firm's own id. Refused: a live
  firm with the code, GST or PAN (`UQ_firms_code_active` and its two
  siblings, partial on `is_deleted = false`); an unconfigured
  `connection_profile`; a database/schema pair **another firm's mapping**
  names, deleted firms included. **Not refused: a pair no mapping names but
  another store owns.** SHARED firms have no `schema_name`, and `platform` is
  no firm's mapping, so a SCHEMA or DATABASE firm may name `firm_shared`,
  `platform` or `public` in `agency_platform`. Provisioning such a firm
  migrates that schema and then **drops the platform tables from it**,
  `CASCADE` — on `platform`, the users, roles, memberships and the registry
  itself (D-IDN-4). Driven: `IDNPROBE1`, SCHEMA, `agency_platform/firm_shared`
  → **201** at 11:51:22 IST, `provisioned_at` null; deleted at 11:51:23, never
  provisioned. Its mapping stays and now reserves the pair.
- **Edit** (`PUT`, `If-Match` honoured) is a **full replacement**: every
  field is written, so an omitted GST or PAN is cleared, an omitted
  `is_active` is `true` (a switched-off firm comes back on) and an omitted
  `status` is `ACTIVE` — `status` is free text read by nothing. Routing fields
  must match the stored mapping exactly, or 422 "Firm storage routing cannot
  be changed after creation…". Audit `firm.updated`, before and after holding
  `name`, `code` and `is_active` only — a changed GST number or year start is
  not on the trail (D-IDN-5, D-IDN-10).
- **Delete** soft-deletes the firm and leaves the mapping, refused while a
  live user holds a live membership (TC-FIRM-017). Audit `firm.deleted`.
  **There is no restore**: nothing un-deletes a firm, and its code, GST and
  PAN are free for a new one the moment it goes.
- **Two firms never share a pair:** checked — no database/schema pair appears
  in two mappings.
- **Check:**
  ```sql
  select f.code, f.is_active, f.is_deleted, f.status, f.version,
         m.deployment_mode, m.database_name, m.schema_name, m.connection_profile,
         m.provisioned_at, m.provisioning_error
  from   platform.firms f
  join   platform.firm_storage_mappings m on m.firm_id = f.id
  order  by f.is_deleted, f.code;

  select m.database_name, m.schema_name, string_agg(f.code, ', ') as firms
  from   platform.firm_storage_mappings m join platform.firms f on f.id = m.firm_id
  where  m.schema_name is not null
  group  by 1, 2 having count(*) > 1
  union all
  select database_name, schema_name, code from platform.firm_storage_mappings m
  join   platform.firms f on f.id = m.firm_id
  where  m.schema_name in ('platform', 'firm_shared', 'public');
  ```
  The second query should answer nothing but `IDNPROBE1`, deleted.
- **Confirmed:** 42 live firms and 23 deleted before the probe; 4 SHARED
  (MEDI01, FOOD01, TESTSH1, TESTSH2), ELEC01 DATABASE on
  `agency_electrolink/electrolink_ops`, the rest SCHEMA in `agency_platform`;
  66 `firm.created`, 23 `firm.deleted`, 5 `firm.updated`, every one with the
  firm's id.

### 15.9 Provisioning and readiness, the platform side (TC-FIRM-004 to 007, 013, 014)

§6 has the rows, §14.16 the firm side, §12.1 Open the books, §13.2 the GST
template.

- **Provision** refuses a SHARED firm, returns at once for one already
  provisioned, and otherwise creates the database and schema
  (`_safe_identifier` — letters, digits, underscore — on both), migrates in
  this process through `upgrade_store`, prunes the platform tables, and sets
  `provisioned_at`; a failure is committed to `provisioning_error` before the
  error is raised. Audit `firm.storage_provisioned` (database, schema,
  profile). 57 such rows; no mapping carries an error today.
- **An unprovisioned dedicated firm serves nothing** —
  `FirmRegistryTenantResolver` refuses it — and `migrate-all` skips deleted
  firms, so the `IDNPROBE1` row reaches no store.
- **Readiness** writes nothing and reads the named firm's store through
  `firm_store_session`; `BLOCKED` for a store not built.
- **The trigger is in every store:** `TR_audit_logs_append_only` and its own
  `reject_audit_log_mutation()` in each of the 58 schemas of `agency_platform`
  that hold `audit_logs` (`platform` among them), and in `electrolink_ops`;
  pruning leaves both alone.

### 15.10 The audit trail — what writes where, and what the merged read shows (TC-AUDIT-001 to 006)

§1.3 and §7 have the read.

- **Where a row goes.** `record_audit` stages the row on whichever session
  the service holds: identity and firm administration on the platform
  session, so `platform.audit_logs`; a firm's own work in the firm's store.
  The row commits with the change — never one without the other.
- **Which rows carry a firm** — and so reach that firm's screen, since
  `list_events_with` filters the platform store on `firm_id`:

  | Action | `firm_id` |
  | --- | --- |
  | `firm.*`, `user.firm_roles_set`, `user.primary_firm_set` | always the firm |
  | `user.created`, `user.updated`, `user.deleted`, `user.roles_set`, `role.*` | the **caller's** firm — null for every platform administrator |
  | `user.cloned`, `user_template.created`, `user_template.applied` | the caller's firm, or the firm a platform administrator named; null when they named none |
  | `user.firms_set`, `user.restored`, `user.password_reset`, `identity.*`, `user_preferences.*`, `permission.*` | never |

  So a firm's screen shows what its own administrator did to its people and
  what anybody did to their roles in it — and **not** who was added to or
  removed from the firm by anybody, nor anything a platform administrator did
  to its people or its roles (D-IDN-5).
- **What the rows hold.** `before_data` / `after_data` carry `_meta`
  (correlation and request ids) and, beyond it: `user.created` the email;
  `user.updated` the old name and active flag, no after; `user.cloned` the
  source; `user_template.applied` the template and roles; `firm.*` the code
  (name and active flag on an edit or delete, what was built on a Set up
  action); `user.password_reset` the forced-change flag;
  `identity.refresh_token_reuse_detected` the replayed token's id. **Nothing
  else carries data** — `user.firms_set`, `user.roles_set`,
  `user.firm_roles_set`, `role.*`, `role.permissions_set` and `user.deleted`
  name the record and not the change.
- **Append-only** in every store (§15.9); `version` and `is_deleted` never
  move on an audit row.
- **The merged read** (`GET /audit-logs` with `X-Firm-ID`) takes `page ×
  page_size` from each store, sorts on `created_at` then id, and slices; the
  same filters reach both, exact-match (BL-31.17), and a store is never merged
  with itself. Both need `AUDIT_LOG_VIEW`; the platform trail (no header)
  needs the designation too, either reach; a firm's trail needs a membership,
  or `ALL_FIRMS`.
- **Check** — a firm's whole trail by hand, and what the platform store holds
  about it that the screen cannot show:
  ```sql
  select created_at, action, entity_type, entity_id, actor_id, 'firm' as store
  from   test_fixtures.audit_logs where firm_id = '<TEST01 id>'
  union  all
  select created_at, action, entity_type, entity_id, actor_id, 'platform'
  from   platform.audit_logs where firm_id = '<TEST01 id>'
  order  by created_at desc limit 50;

  select a.created_at, a.action, a.actor_id
  from   platform.audit_logs a
  where  a.firm_id is null
    and  a.entity_type = 'user'
    and  a.entity_id in (select user_id from platform.user_firms where firm_id = '<TEST01 id>')
  order  by a.created_at desc limit 50;
  ```
- **Confirmed** (the API, as `t0919wwzu` with `X-Firm-ID` TEST01, and the
  platform store): `user.firms_set` 0 on TEST01's screen against 1,121 on the
  platform; `user.created` 2 against 290; `user.roles_set` 9 against 884;
  the clone's three rows on the platform trail and none on TEST01's; five of
  the six `role.deleted` rows for TEST01's own night-desk roles — the fixture
  clear-up of 2026-09-17 05:23 IST, run by a platform administrator — carry no
  firm, while the one a TEST01 administrator made does.

### 15.11 Retention — tokens, sign-ins and password history

- **Nothing prunes until somebody runs it**: `agency-server purge-retention`
  (`scripts/purge_retention.py`, the opt-in `retention` compose service) runs
  `IdentityRetentionService.purge` — by default refresh tokens expired or
  revoked more than 7 days ago, `login_history` older than 365 days,
  `password_history` beyond the newest 10 per user (`created_at`, then id, so
  ties are fixed).
  It has not run here: 1,542 `refresh_tokens` since 2026-08-15, 593 live and
  627 past the grace; 1,454 `login_history` rows.
- **Not a defect** — opt-in by design (`CLAUDE.md`, "Nothing prunes…").

### 15.12 What identity, firms and audit do not write, and is often looked for

| You might expect | What actually happens |
| --- | --- |
| A row saying who was added to a firm, on that firm's screen | `user.firms_set` with no firm and no data, on the platform trail only (§15.4) |
| A platform administrator's hiring on the firm's screen | Only their role grants in that firm (§15.10) |
| Which codes a role gained, or which roles a person gained | Not recorded; the rows name the record (§15.10) |
| A membership row for a clone's firms in the audit trail | None (§15.7) |
| Sign-out ending the access token | It lives out its 15 minutes; only the refresh token is revoked (§15.1) |
| A deleted role's code free again | Never, in any firm (§15.5) |
| A firm restored | No endpoint (§15.8) |
| A firm's user rows in its own store | None; `user_templates` is the one stray copy (§15.0) |
| An audit row for a read, readiness or the audit screen | None |

### 15.13 Checked against live rows, and not

- **Confirmed by driving** (2026-09-19, 11:44–11:52 IST): the `PLATFORM`
  operator's token and its empty staffing reach (§15.4); a platform
  administrator's clone putting a firm-scoped role in the global tier and
  writing three commits and no membership audit (§15.7); a SCHEMA firm naming
  `firm_shared` accepted (§15.8); TEST01's merged trail missing every
  membership change (§15.10). **What the drives left:** users
  `t0919tkcy.operator`, `t0919wwzu.platform`, `t0919subq.twofirm`,
  `t0919subq.clone` (SALES_EXECUTIVE and CUSTOMER_SUPPORT globally, in TEST01
  and TEST02, forced to change password); deleted firm `IDNPROBE1` with its
  mapping on `agency_platform/firm_shared`, never provisioned.
- **Confirmed from the tables** (read only): the login outcomes, token and
  history counts; no live token for an unusable user; the partial unique
  indexes on email, firm code, GST, PAN and the active primary; the plain
  `UQ_roles_code`; the audit counts per action with and without a firm and
  data; the trigger in every store including `electrolink_ops`; no two firms on
  one pair; the stray `user_templates` copies; TC-ROLE-008's version move and
  TC-ROLE-009's rows.
- **Corrections to pass 1:** §1.3 said identity rows carry `firm_id` where
  the action was about a firm — only for the actions in §15.10's first row, or
  when a firm's own administrator acted. §3 *Clone a user* said roles are
  copied within the caller's reach and the build writes `user.firms_set` — a
  platform caller's clone copies every role into the global tier (D-IDN-3) and
  writes no membership row. §5 said a provisioned store's `user_templates` is
  empty — it holds the 11 seeded templates.
- **Not driven, deliberately:** a `PLATFORM` operator granting themselves
  `FIRM_ADMIN` (D-IDN-1) and resetting an `ALL_FIRMS` administrator's password
  (D-IDN-2) — both escalations, read off the code.
- **Not seen in a live row:** a global-tier row of a firm-owned role
  (D-IDN-3's second half); a global custom-role or platform-role holder
  reaching a firm by header (D-IDN-7); a clone failing half-way (D-IDN-8); a
  refresh-reuse revocation from a race; a person with an inactive membership
  elsewhere edited by a firm administrator; a firm provisioned onto a schema
  another store owns.

---

## 16. Masters — customers, vendors, products, branches and warehouses (TC-CUST-001 to 006, TC-MAST-001 to 008, TC-CONC-001 to 003, TC-ISO-001, TC-ISO-002)

Read on 2026-09-19 off `app/customers` (`customer_service.py`,
`customer_group_service.py`, the repository and the router), `app/vendors`
(`vendor_service.py`, the router), `app/products` (`product_service.py`, the
router), `app/branches` (`branch_warehouse_service.py`, the router) and what
they call — `AttributeService`, `DocumentPostingService`, the delete guards in
`app/settlements` and the pricing rule in `app/core/utils/pricing.py`. The 99
routes these four modules publish are counted in `docs/MODULE_STATUS.md`.

**Earlier sections carry the master data a document touches, and are not
repeated here**: what a purchase writes against a vendor is §9, stock against a
product and a warehouse §10, a sale against a customer §11 (the credit limit at
approval is §11.6), a customer's opening balance and what deleting one does to
the ledger §12.11, statements and ageing §12.10, the tax profile a product
names §13.5, and custom fields, units, packaging, barcodes and geography §14.4,
§14.5, §14.10 to §14.12. This section is the master records themselves: created,
edited, deleted, restored, imported, exported, grouped and categorised.

Checked read-only against every store on the local server that holds a
`customers` table (59 schemas in `agency_platform` plus `electrolink_ops` in
`agency_electrolink`), and driven against the running backend on six fixture
runs of this pass — `stock-ready` `t0919p81v`, `product-master` `t09199zi5`,
`customer-master` `t09193238`, `loyalty-viewer` `t09191qg3`, `shared-pair`
`t0919r8y3` and `po-received` `t091964t5`. **Nothing was written to the demo
firms** (WHOLE01, MEDI01, FOOD01, ELEC01); they were read only. §16.21 says
which claims a live row confirmed and which it could not; a claim marked *(not
seen in a live row)* was read off the code only.

### 16.0 Before you look

- **Stores.** Every table in this section is firm-owned, so it lives in the
  firm's own store and carries `firm_id`. For a fixture firm put the schema the
  fixture's **Tables** line prints; for TEST01 `test_fixtures`, TEST02
  `test_fixtures_2`, WHOLE01 `wholesale_hub`, MEDI01, FOOD01, TESTSH1 and
  TESTSH2 `firm_shared` (filter on `firm_id`), ELEC01 `electrolink_ops` in the
  `agency_electrolink` database.

  | Case | Fixture | Schema |
  | --- | --- | --- |
  | TC-CUST-001 to 004, 006, TC-CONC-001, TC-CONC-003 | `customer-master` | `test_fixtures` |
  | TC-CUST-005 | `invoiced-part-paid` | `test_fixtures` |
  | TC-MAST-001, 002 | `vendor-master` | `test_fixtures` |
  | TC-MAST-003, 008 | `product-master` | `test_fixtures` |
  | TC-MAST-004 to 007 | `branch-master` | **`test_fixtures_2`** — the branches and warehouses are TEST02's |
  | TC-ISO-001 | `shared-isolation-pair` | `firm_shared`, two firms in one table |
  | TC-ISO-002 | `isolation-pair` | `test_fixtures` and `test_fixtures_2` |

- **Four shapes of master table.**

  | Tables | Rows per |
  | --- | --- |
  | `customers`, `vendors`, `products`, `branches`, `warehouses` | the record itself, `firm_id` on every row |
  | `customer_addresses`, `customer_contacts`, `vendor_contacts`, `vendor_addresses`, `vendor_bank_accounts`, `vendor_tax_details`, `vendor_attachments`, `vendor_notes`, `product_media`, `warehouse_storage_nodes` | child rows, keyed to the parent and **replaced as a whole** by an edit that sends the collection |
  | `customer_groups`, `vendor_categories`, `vendor_types`, `product_categories`, `branch_types`, `warehouse_types` | the firm's own small masters |
  | `customer_attribute_values`, `vendor_attribute_values`, `product_attribute_values`, `branch_attribute_values`, `warehouse_attribute_values` | custom fields, typed columns, §14.5 |

  `customer_receivable_transactions` and `credit_control_settings` are
  §12.11 and §14.14. `vendors.business_attributes` is a **JSON blob on the
  vendor row** beside the typed custom fields — written by the API and by the
  demo seeder, read by nothing (D-MST-11).
- **The audit rows are the firm's own, and every one carries its firm.**
  Unlike the configuration catalogue (§14.0, D-CFG-13), every master write
  audits into the firm's store with `firm_id` set:
  `customer.created` / `.updated` / `.deleted` / `.restored`,
  `customer_group.created` / `.updated` / `.deleted`,
  `vendor.created` / `.updated` / `.deleted` / `.restored`,
  `product.created` / `.updated` / `.deleted` / `.restored` / `.duplicated`,
  `product.category.deleted`, `branch.*`, `warehouse.*` and
  `warehouse.storage_node.created`. **Nine master writes record nothing at
  all** — the four category and type screens, a vendor duplicate, a product
  category created or edited, and a storage node edited or deleted
  (D-MST-11). Query them:
  ```sql
  select created_at, action, entity_type, entity_id,
         before_data::jsonb - '_meta' as before, after_data::jsonb - '_meta' as after
  from   test_fixtures.audit_logs
  where  action ~ '^(customer|customer_group|vendor|product|branch|warehouse)'
  order  by created_at desc;
  ```
- **One master write reaches the ledger, and one delete used to.** A
  customer's opening balance posts `<code>-OB` (§12.11); nothing else here
  posts a journal. Deleting a customer no longer reverses anything (D-FIN-1),
  and deleting a vendor, product, branch or warehouse never did — which is why
  the guards in §16.3, §16.10, §16.14, §16.16 and §16.17 are the only thing between a delete
  and a balance nobody owns.
- **What points at what.**

  | From | Column | To |
  | --- | --- | --- |
  | `customers` | `customer_group_id` (FK, `ondelete="RESTRICT"`) | `customer_groups` — the only foreign key on a customer; `firm_id` has none, because `firms` is platform (§1.1) |
  | `vendors` | `category_id`, `type_id`, `business_profile_id` | `vendor_categories`, `vendor_types`, `business_profiles` |
  | `products` | `category_id`, `sub_category_id` | `product_categories` |
  | `products` | `base_uom_id`, `inventory_uom_id`, `purchase_uom_id`, `sales_uom_id`, `default_receiving_uom_id`, `default_dispatch_uom_id`, `minimum_sales_uom_id` | `uoms` (§14.10) |
  | `products` | `tax_profile_group_code` (**text, not an id**) | `tax_profiles.group_code` (§13.5) |
  | `branches` | `branch_type_id`, `business_profile_id`, `branch_manager_id` | `branch_types`, `business_profiles`, a **user** — which lives in `platform`, so the column is a bare id with no key |
  | `warehouses` | `branch_id`, `warehouse_type_id`, `warehouse_manager_id` | `branches`, `warehouse_types`, a user |
  | `warehouse_storage_nodes` | `warehouse_id`, `parent_id`, `path` | the warehouse and the node above; `path` is the codes joined by slashes |
  | `inventories`, and every document line | `product_id`, `warehouse_id`, `storage_node_id` | the masters — **with no foreign key from a document line**, which is what makes the delete guards the whole protection |
- **Every code is unique per firm and is never released.** `UQ_customers_firm_code`,
  `UQ_customers_firm_gst_number`, `UQ_customers_firm_pan_number`,
  `UQ_vendors_firm_code`, `UQ_vendors_firm_gstin`, `UQ_products_firm_code`,
  `UQ_branches_firm_code`, `UQ_warehouses_firm_code` and the six master-table
  keys are **plain** unique indexes covering deleted rows too — unlike
  `users.email` and `firms.code`, which are partial on `is_deleted` (§15.0).
  Only `UQ_products_firm_barcode_active`, `UQ_branches_default_active` and
  `UQ_warehouses_default_active` are partial. So a deleted customer's code can
  never be used again, and where the service's own check filters `is_deleted`
  the refusal arrives from the database as a bare 409 (D-MST-11).
- **Concurrency.** All four record endpoints publish the row's `version` as an
  `ETag` and as a field on the body, and take `If-Match`
  (`set_etag` / `assert_version` in each router); a save that changes nothing
  does not move it (TC-CONC-003). The small masters mostly do not: only
  customer segments carry a version and a precondition.

### 16.1 Create a customer — Masters → Customers → New (TC-CUST-002, TC-ISO-001, TC-ISO-002)

`POST /api/v1/customers`, `CUSTOMER_CREATE`, membership in `X-Firm-ID`. One
commit.

- **Inserts** one `customers` row (code, type, name, `display_name` =
  the name when none is sent, GST and PAN, contact details, `credit_limit`,
  `default_discount_percent`, `payment_terms_days`, `currency_code`, `status`,
  `customer_group_id`, `opening_balance`), one `customer_addresses` row per
  address and one `customer_contacts` row per contact, and one
  `customer_attribute_values` row per custom field sent (§14.5).
  `current_outstanding` and `unapplied_advance_balance` are derived from the
  opening balance, positive into the balance and negative into the advance.
- **The address's free text is derived from the place ids it names**
  (`_apply_place`): country takes `iso2`, the rest their name, and a rung that
  does not belong under the one above is refused — "That address names places
  that do not belong together." A row that sends no ids keeps its typed text,
  which is how a firm with no geography masters still records an address
  (§14.12).
- **A non-zero opening balance posts** (§12.11): journal `<code>-OB`,
  Dr 1100 / Cr 3000, plus one `customer_receivable_transactions`
  `OPENING_BALANCE` row. With no chart of accounts or no period open today the
  **whole create is refused** — "<code> cannot open with a balance: …".
- **Refused, nothing written:** a code, GSTIN or PAN another customer in the
  firm holds, **deleted ones included** — "Customer code, GST number, or PAN
  number already exists in this firm."; two default billing or shipping
  addresses, or two primary contacts; a custom field that does not apply or a
  required one missing (§14.5).
- **Not checked:** the segment. `customer_group_id` is written straight
  through, so another firm's segment in the shared store, or one deleted a
  second earlier, is accepted — and the discount it carries is then applied to
  that customer's orders (D-MST-3).
- **Check:**
  ```sql
  select c.code, c.name, c.status, c.credit_limit, c.default_discount_percent,
         c.payment_terms_days, c.opening_balance, c.current_outstanding,
         g.code as segment, g.firm_id = c.firm_id as segment_is_ours, g.is_deleted as segment_gone,
         (select count(*) from test_fixtures.customer_addresses a
          where a.customer_id = c.id and a.is_deleted = false) as addresses,
         (select count(*) from test_fixtures.customer_contacts t
          where t.customer_id = c.id and t.is_deleted = false) as contacts
  from   test_fixtures.customers c
  left   join test_fixtures.customer_groups g on g.id = c.customer_group_id
  where  c.code like '<SUFFIX>%';
  ```
- **Confirmed** in `test_fixtures`: `T09193238-CM` with one address, one
  contact, a 50,000 limit, 30 days and 7.5% standing; `T09193238-GRP` created
  into a segment deleted moments before; in `firm_shared`, `T0919R8Y3-X1`
  (TESTSH1) created into TESTSH2's segment.

### 16.2 Edit a customer — Masters → Customers → Edit (TC-CUST-001, TC-CONC-001, TC-CONC-003)

`PUT /api/v1/customers/{id}`, `CUSTOMER_UPDATE`, `If-Match` optional. One
commit.

- **Partial, and correct about it.** `_customer_values(..., partial=True)`
  dumps only what the caller sent, so **absent leaves the column alone and an
  explicit `null` still clears**. The two child collections are guarded on
  `model_fields_set`, so an omitted `addresses` or `contacts` is left exactly
  as it is and an empty list clears it; `attributes` the same (§14.5). The
  display name is only recomputed when `name` or `display_name` was sent.
  **Four fields are required by the schema whatever else is sent** — `code`,
  `customer_type`, `name` and `currency_code` — so the smallest honest edit
  carries five.
- **Addresses and contacts are reconciled by id**: a row whose id is sent is
  updated in place, one with no id is inserted, and one the payload leaves out
  is **soft-deleted**. An id the customer does not own is refused — "A customer
  address no longer exists."
- **The opening balance may only move while the account has never traded** —
  "Opening balance cannot be changed after receivable activity exists."; where
  it may, the old OB journal is reversed (`<ref>-REV`), the old
  `OPENING_BALANCE` row is physically deleted and the new figure is posted
  (§12.11).
- **The credit limit takes `CUSTOMER_MANAGE_SETTINGS`** (D-CFG-17): a save
  that moves it from somebody without the code is refused 403 — "Changing a
  customer's credit limit needs the manage customer settings permission
  (CUSTOMER_MANAGE_SETTINGS)." — while one that resends the stored figure goes
  through. **The standing discount takes nothing but `CUSTOMER_UPDATE`**, so
  the role the limit was taken from sets `default_discount_percent` to 100 and
  sells at nothing (D-MST-2).
- **`status` is writable here** — ACTIVE, INACTIVE or ON_HOLD — and no sales
  document reads it (§16.4, D-MST-6).
- **Audit:** one `customer.updated` with a before and an after side, each a
  fixed snapshot: firm, code, name, status, limit, opening balance, the two
  balances, the live address and contact counts, `is_deleted`. **A changed
  phone number, segment, standing discount or address is on no trail** — the
  snapshot does not carry them.
- **Check:** §16.1's query, plus the version and the trail:
  ```sql
  select created_at, action,
         before_data::jsonb - '_meta' as before, after_data::jsonb - '_meta' as after
  from   test_fixtures.audit_logs
  where  entity_type = 'customer' and entity_id = '<customer id>'
  order  by created_at;
  ```
- **Confirmed:** a PUT naming only the four required fields and the phone left
  the address, contact, limit, terms, standing discount and segment as they
  were, `version` 1 → 2 (TC-CUST-001, driven over HTTP); a `SALES_MANAGER`'s
  attempt to move a limit answered 403 and their 100% standing discount
  answered 200.

### 16.3 Delete and restore a customer — Masters → Customers → Delete (§12.11)

`DELETE /api/v1/customers/{id}` (`CUSTOMER_DELETE`) and
`POST /api/v1/customers/{id}/restore` (`CUSTOMER_RESTORE`).

- **Soft delete**: `is_deleted`, `deleted_at`, `deleted_by`, audit
  `customer.deleted` with the snapshot as `before_data`. Nothing else moves —
  the addresses, contacts, custom fields, receivable rows and journals all stay
  where they are, which is what makes a restore whole.
- **The guard is `_assert_account_is_square`** (D-FIN-1): what the customer
  owes, any advance they hold, and any APPROVED, CLOSED or DRAFT **sales
  invoice** stop the delete, by name — "<code> cannot be deleted: it owes …,
  has 2 open invoices (…). Settle, refund or cancel what is open first, or set
  the customer inactive to stop trading with them."
- **It stops at invoices.** A quotation, a sales order — approved, holding a
  reservation on stock — a delivery note, a proforma or a loyalty balance all
  go unlooked-at, so the customer goes and the documents stay (D-MST-4). The
  note the order needs is then refused, because every sales service loads the
  customer with `Customer.is_deleted.is_(False)`.
- **Restore** clears the three columns, re-posts an opening-balance journal a
  pre-D-FIN-1 delete had reversed, and audits `customer.restored`. There is no
  code check on the way back in, and there needs none: the code was never
  released (§16.0).
- **Check:**
  ```sql
  select c.code, c.is_deleted, c.deleted_at, c.current_outstanding,
         (select count(*) from test_fixtures.sales_orders o
          where o.customer_id = c.id and o.is_deleted = false
            and o.status in ('DRAFT', 'APPROVED', 'PARTIALLY_DELIVERED')) as open_orders,
         (select count(*) from test_fixtures.sales_invoices i
          where i.customer_id = c.id and i.is_deleted = false) as invoices
  from   test_fixtures.customers c
  where  c.is_deleted;
  ```
- **Confirmed:** `T09193238-CM` deleted 204 while SO-2026-2027-000012 stood
  APPROVED with one unit reserved, and `T09191QG3-SM` deleted 204 with a draft
  order; TEST01's five customers deleted on 2026-09-16 still carry 1,960.00
  (§12.11), which is the pre-fix shape.

### 16.4 A customer who is not to be traded with — `status`

- **Writes** nothing but `customers.status` (§16.2), audited inside
  `customer.updated`'s snapshot.
- **Read by:** the list filter and the summary counts (`GET /api/v1/customers?status=`,
  `/customers/summary`), the territory service's ACTIVE/not-ACTIVE split, and
  nothing else. **No sales document checks it**, so an INACTIVE or ON_HOLD
  customer is quoted, ordered, delivered and billed exactly as an active one
  (D-MST-6) — while the purchase side does check its counterparty
  (`_active_product` and the vendor check in
  `backend/app/purchase/services/purchase_service.py`).
- **Confirmed:** with `T09193238-CM` INACTIVE, SO-2026-2027-000012 was created
  and approved.

### 16.5 Segments — Customers → Groups (TC-CUST-006)

`/api/v1/customers/groups`; list and read need `CUSTOMER_VIEW`, write
`CUSTOMER_MANAGE_SETTINGS`. One commit each.

- **Create / edit / delete** writes one `customer_groups` row: `code`, `name`,
  `description`, `default_discount_percent`, `is_active`. Audit
  `customer_group.created` / `.updated` / `.deleted`; the update's two sides
  carry the name and the rate, which makes this the one master edit whose trail
  says what changed.
- **Delete is refused while anybody is in it** — "1 customer(s) are still in
  Wholesaler <suffix>. Move them first, …" — counting **live** customers only,
  so a deleted customer comes back into a segment that has gone. The row is
  soft-deleted without `deleted_at` or `deleted_by`.
- **The code is gone for good.** `_assert_free` looks only at live rows while
  `UQ_customer_groups_firm_code` covers every row, so re-using a retired code
  is refused by the database as "The request conflicts with existing data.
  Please retry." (D-MST-11).
- **What the rate does:** it is the last tier of the shared discount rule
  (§11.1) — below a typed amount, a percentage, a promotion, a price list and
  the customer's own standing rate. A sales order and a quotation resolve it
  through `_customer_group`, which reads the segment **by id, checking only
  `is_active`** — not the firm, not `is_deleted` (D-MST-3).
- **Check:**
  ```sql
  select g.code, g.name, g.default_discount_percent, g.is_active, g.is_deleted,
         count(c.id) filter (where c.is_deleted = false) as live_members
  from   test_fixtures.customer_groups g
  left   join test_fixtures.customers c on c.customer_group_id = g.id
  group  by g.id order by g.code;
  ```
- **Confirmed:** `T09193238-RET` (1.75%) and `-WHL` (3.25%) with their members;
  `T09193238-OLD` deleted and its code then refused 409; TESTSH2's
  `T0919R8Y3-TWO` at 50% pricing TESTSH1's order SO-2026-2027-000001 down to
  50.00 with `discount_source` `customer_group`.

### 16.6 Customer import and export — Customers → Import / Export

- **Import** — `POST /api/v1/customers/import`, `CUSTOMER_IMPORT`, JSON only
  (the desktop parses the file). Up to 1,000 records **staged and committed
  once**: every record goes through the same `_stage_create` a single create
  uses, so the audit rows, the uniqueness checks and the opening-balance
  postings are the same, and a batch whose fifth row clashes writes nothing.
- **Export** — `GET /api/v1/customers/export`, `CUSTOMER_EXPORT`, reads in
  pages of 1,000 and writes code, name, type, GST, PAN, email, phone and
  status through `csv.writer`, so a comma in a name is quoted. It writes
  nothing.
- **Confirmed:** no live import in a fixture store; the atomicity is the same
  shape as branches' (TC-MAST-006) *(not seen in a live row for customers)*.

### 16.7 Create and edit a vendor — Masters → Vendors (TC-MAST-001)

`POST` / `PUT /api/v1/vendors[/{id}]`, `VENDOR_CREATE` / `VENDOR_UPDATE`,
`If-Match` optional. One commit.

- **Inserts** one `vendors` row and the six child collections —
  `vendor_contacts`, `vendor_addresses`, `vendor_bank_accounts`,
  `vendor_tax_details`, `vendor_attachments`, `vendor_notes` — plus
  `vendor_attribute_values` for the custom fields. Audit `vendor.created` with
  the code, name, status and the four child counts.
- **`None` is not `[]` here.** Each collection is `list[...] | None` with no
  default, so an update that omits one leaves it alone and one that sends `[]`
  clears it; the header fields are dumped with `exclude_unset` for the same
  reason. **The one exception is `display_name`**, recomputed from `name` on
  every update, so a vendor whose display name differs loses it to any save
  that sends a name (D-MST-11).
- **A drug licence is gated on the field, not the vendor**: every
  `tax[].drug_license` sent is checked against the firm's `DRUG_LICENSE`
  feature (§14.3), and refused by name for a profile that does not enable it.
- **Refused, nothing written:** a code or GSTIN the firm already holds,
  deleted vendors included — "Vendor code or GSTIN already exists in this
  firm."; two primaries in one collection.
- **Not checked:** `category_id`, `type_id` and `business_profile_id` are
  written straight through, so another firm's category in the shared store is
  accepted (D-MST-3); the address's geography ids are stored without the
  parent-and-child check a customer address gets (§16.1).
- **Bank details are the firm's money, and two codes guard them.**
  `VENDOR_MANAGE_BANK_DETAILS` and `VENDOR_VIEW_FINANCIAL_DETAILS` were seeded
  and enforced on no route, so the account number a payment is sent to was
  edited with `VENDOR_UPDATE` and read with `VENDOR_VIEW`, which the seeded
  `VIEWER` role holds (D-MST-10, fixed). The router now serves
  `bank_accounts` empty without the read code, and the service refuses a
  create or an update that adds, changes or removes an account without the
  manage code; a caller shown no accounts has their resent empty list left
  unapplied rather than read as an instruction to clear them. `ACCOUNTANT`
  gained the read (`20260919_0150`) and deliberately not the write.
- **Check:**
  ```sql
  select v.code, v.name, v.display_name, v.status, v.gstin,
         c.code as category, c.firm_id = v.firm_id as category_is_ours,
         (select count(*) from test_fixtures.vendor_bank_accounts b
          where b.vendor_id = v.id and b.is_deleted = false) as banks,
         (select count(*) from test_fixtures.vendor_tax_details t
          where t.vendor_id = v.id and t.is_deleted = false) as tax_rows,
         v.business_attributes
  from   test_fixtures.vendors v
  left   join test_fixtures.vendor_categories c on c.id = v.category_id
  where  v.code like '<SUFFIX>%';
  ```
- **Confirmed:** TC-MAST-001's PUT with only code, name and phone left all six
  collections (driven); in `firm_shared`, `T0919R8Y3-V1` (TESTSH1) created in
  TESTSH2's category; six of the seven vendors in `firm_shared` carry a
  `business_attributes` blob nothing reads.

### 16.8 Vendor categories and types — Masters → Vendor Categories / Types (TC-MAST-002)

`/api/v1/vendors/categories` and `/api/v1/vendors/types`,
`VENDOR_MANAGE_CATEGORIES`. Declared above `/{vendor_id}` on purpose (§1 of
`docs/API_AND_PERSISTENCE_CONVENTIONS.md`).

- **Create / edit / delete** writes one `vendor_categories` or `vendor_types`
  row — `code`, `name`, `description`, `is_active`. **No audit row is written
  for any of the six operations**, and an edit reads the row *including*
  deleted ones and clears `is_deleted`, so a `PUT` on a retired category
  silently brings it back (D-MST-11).
- **Delete is refused while a live vendor names it** — "This category is used
  by 3 vendor(s) and cannot be deleted. Move them to another category first." —
  because `ondelete="RESTRICT"` guards nothing on a soft-deleted table.
- **No `ETag` and no `If-Match`**: two people editing one category is
  last-write-wins.
- **Check:**
  ```sql
  select c.code, c.name, c.is_active, c.is_deleted,
         count(v.id) filter (where v.is_deleted = false) as live_vendors
  from   test_fixtures.vendor_categories c
  left   join test_fixtures.vendors v on v.category_id = c.id
  group  by c.id order by c.code;
  ```
- **Confirmed:** no `vendor_category.*` or `vendor_type.*` action exists in any
  store's `audit_logs`.

### 16.9 Vendor bulk actions and duplicate — the Vendors toolbar

Five bulk endpoints (`/bulk-delete`, `/bulk-restore`, `/bulk-status`,
`/bulk-category`, `/bulk-profile`) and `POST /{id}/duplicate`.

- **The bulk endpoints audit each row** the way the single-row twin does —
  `vendor.deleted`, `.restored`, `.updated` with the code and the new status —
  and `bulk-delete` applies `_assert_account_is_square` per vendor **before
  anything is committed**, so a batch whose fifth vendor still owes leaves the
  first four alone. They commit once, at the end.
- **But they are still a second implementation**: `bulk-category` writes
  `category_id` with no check at all (another firm's category, a deleted one,
  or an id that exists nowhere — refused only if the database's foreign key
  catches it), and `bulk-profile` the same for `business_profile_id`. An id in
  the list that is already deleted answers 404 for the whole batch rather than
  being skipped.
- **Duplicate** copies the header and the contacts under `<code>-COPY`, clears
  the GSTIN, and **writes no audit row at all**; a second duplicate of the same
  vendor is refused 409, because the suffix does not count up the way the
  product's does.
- **Confirmed:** no `-COPY` vendor exists in any store *(not seen in a live
  row)*.

### 16.10 Delete and restore a vendor — Masters → Vendors → Delete

- **Soft delete with `_assert_account_is_square`** (the D-FIN-1 twin): what
  the firm owes on approved bills less what it has paid, any DRAFT purchase
  invoice, any posted payment not yet applied, and any supplier credit from a
  return not yet set against a bill (D-FIN-19) each refuse the delete by name.
- **It stops at bills.** A purchase order and a **completed goods receipt that
  has not been billed** are not looked at, so a supplier can be deleted while
  GRNI (2300) holds what the firm owes for goods it has taken in, and the bill
  that would clear it can no longer be raised from any screen (D-MST-4).
- **Restore** clears the flags and audits `vendor.restored`.
- **Check:**
  ```sql
  select v.code, v.is_deleted,
         (select coalesce(sum(l.credit_amount - l.debit_amount), 0)
          from test_fixtures.goods_receipts g
          join test_fixtures.journal_entries je on je.reference_number = g.grn_number
          join test_fixtures.journal_lines l on l.journal_entry_id = je.id
          join test_fixtures.ledger_accounts a on a.id = l.ledger_account_id and a.code = '2300'
          where g.vendor_id = v.id and g.status = 'COMPLETED') as grni_raised
  from   test_fixtures.vendors v where v.is_deleted;
  ```
- **Confirmed:** `T091964T5-V` deleted 204 with GRN-TEST01-HO-2026-2027-000027
  and -000028 completed and unbilled, GRNI holding 400.00 + 600.00; the
  Payments screen's outstanding list then answers `[]` for it.

### 16.11 Create a product — Masters → Products → New (TC-MAST-003)

`POST /api/v1/products`, `PRODUCT_CREATE`. One commit.

- **Inserts** one `products` row — code, barcode, QR, names, `product_type`,
  category and sub-category, the seven UOM slots (§14.10), `hsn_sac`,
  `tax_profile_group_code`, the three prices, the eleven tracking and
  permission flags, `status` — plus one `product_media` row per media entry and
  one `product_attribute_values` row per custom field (§14.5, TC-FIELD-007).
  Audit `product.created` carrying the code alone.
- **What is checked:** the code, unique among **live** products; the barcode,
  unique among live products; the category and the sub-category, which must
  belong to the firm, be live, and the sub-category must sit under the
  category; `tax_profile_group_code`, which must match a live ACTIVE tax
  profile of the firm (§13.1); every UOM id, which must exist and be live;
  and the three feature-gated fields — `barcode`, `qr_code`, `track_warranty`
  — against the firm's profile (§14.3).
- **What is not:** `selling_price` against `purchase_price` (only MRP is, and
  only against the selling price), and nothing ties the UOM slots to a
  conversion rule, so a sales unit with no path to the base unit is accepted
  and fails later on a document line (§14.11).
- **Cost price is a permission, on the way out only.** `purchase_price` is
  blanked in every response for a caller without `PRODUCT_VIEW_COST_PRICE`
  (`_response` in `backend/app/products/api/router.py`) — and is writable by
  anyone with `PRODUCT_UPDATE`, which is how the desktop's own edit dialog
  clears it (§16.12, D-MST-5).
- **Check:**
  ```sql
  select p.code, p.name, p.status, p.product_type, c.code as category,
         p.tax_profile_group_code, bu.code as base_unit, pu.code as purchase_unit,
         p.purchase_price, p.selling_price, p.mrp, p.barcode,
         p.track_batch, p.track_serial, p.track_expiry, p.version
  from   test_fixtures.products p
  left   join test_fixtures.product_categories c on c.id = p.category_id
  left   join test_fixtures.uoms bu on bu.id = p.base_uom_id
  left   join test_fixtures.uoms pu on pu.id = p.purchase_uom_id
  where  p.code like '<SUFFIX>%';
  ```
- **Confirmed:** `T09199ZI5-PM` with category `T09199ZI5-PC`, group
  `GST_18_LOCAL`, PIECE in three slots and BOX to buy in (TC-MAST-003).

### 16.12 Edit a product — Masters → Products → Edit (TC-CONC-002)

`PUT /api/v1/products/{id}`, `PRODUCT_UPDATE`, `If-Match` optional.

- **The write model is dumped whole** (`_product_values`, with no
  `exclude_unset`), so **every field the caller omits is written back at its
  schema default** — null for the category, the tax group, all seven units and
  the three prices, false for every tracking flag. `attributes` and `media` are
  not guarded on `model_fields_set` either, so an omitted `attributes` clears
  the custom fields and an omitted `media` soft-deletes every image. This is the
  shape the vendor and branch modules were fixed out of on 2026-09-16 and the
  product was not (D-MST-5).
- **The desktop sends every field**, which is why the screen looks right — and
  is exactly how the cost price goes: a caller without
  `PRODUCT_VIEW_COST_PRICE` is served `purchase_price: null`, the form shows an
  empty box, and the save sends that null back.
- **Nothing is refused because of stock.** The base and inventory units, the
  batch, lot, serial and expiry flags and `allow_negative_stock` can all change
  while the product has stock on hand, reservations and a valuation: the
  quantity in `inventories` is not converted and not re-checked, so 50 pieces
  read as 50 boxes the moment the base unit moves, and stock received without
  serials becomes unissuable the moment `require_serial_on_issue` goes on
  (D-MST-7, and D-STK-4 for what a serial pick then demands).
- **Audit:** `product.updated`, `before_data` the code and the category id,
  `after_data` the code and the status — so a price, a tax group, a unit or a
  tracking flag changes with nothing in the trail to say it did.
- **Check:** §16.11's query before and after, plus
  ```sql
  select i.current_quantity, i.reserved_quantity, w.code as warehouse,
         p.base_uom_id, v.quantity_on_hand, v.average_cost, v.total_value
  from   test_fixtures.inventories i
  join   test_fixtures.products p on p.id = i.product_id
  join   test_fixtures.warehouses w on w.id = i.warehouse_id
  left   join test_fixtures.product_valuations v on v.product_id = p.id
  where  p.code = '<SUFFIX>-P' and i.is_deleted = false;
  ```
- **Confirmed:** a PUT naming code, name and type left `T09199ZI5-PM` with no
  category, no tax group, no units and no selling price (100.00 before);
  `T09193238-P` moved from PIECE to BOX and gained `track_serial` with 50 on
  hand and one reserved.

### 16.13 Product categories — Masters → Products → Categories

`/api/v1/products/categories`, all three writes on `PRODUCT_UPDATE`.

- **Create / edit** writes one `product_categories` row with `parent_id`,
  `level` and `path` (the codes joined by slashes) derived from the parent, and
  **no audit row**. Only the delete writes one — `product.category.deleted`.
- **A category may be moved under its own child.** `update_category` checks
  nothing about the ancestry (the storage-node editor does), so the pair ends up
  in a cycle: the parent's path becomes `PC/PCC/PC` at level 2 while the child
  still reads `PC/PCC` at level 1, and **descendants are never repathed** on any
  move (D-MST-11).
- **Delete is refused while a live product names it** — "Categories used by
  products cannot be deleted." — but the check reads `category_id` only, so a
  category used as a **sub-category**, or one with live children, goes. The
  category-scoped custom-field rules key on the category's **code as text**
  (§14.4), so they are left pointing at a code nothing holds.
- **Check:**
  ```sql
  select c.code, c.name, c.level, c.path, c.is_active, c.is_deleted,
         par.code as parent,
         (select count(*) from test_fixtures.products p
          where p.category_id = c.id and p.is_deleted = false) as products,
         (select count(*) from test_fixtures.products p
          where p.sub_category_id = c.id and p.is_deleted = false) as as_sub
  from   test_fixtures.product_categories c
  left   join test_fixtures.product_categories par on par.id = c.parent_id
  order  by c.path;
  ```
- **Confirmed:** `T09199ZI5-PC` moved under its own child `T09199ZI5-PCC` and
  answered 200 with `path` `T09199ZI5-PC/T09199ZI5-PCC/T09199ZI5-PC` (put back
  by hand afterwards); no `product.category.created` or `.updated` action
  exists in any store.

### 16.14 Delete, restore, duplicate and the bulk actions — the Products toolbar

- **Delete** (`DELETE /api/v1/products/{id}`, `PRODUCT_DELETE`) sets the three
  soft-delete columns and audits `product.deleted` with the code. **There is no
  guard of any kind** — not stock on hand, not a reservation, not a batch, not
  an open order or an unbilled receipt (D-MST-1). The stock rows stay exactly
  as they are and the valuation with them, while
  `GET /api/v1/inventory/summary/by-product` filters deleted products out and
  every movement is refused — "Product does not belong to the active firm." —
  so the quantity can be neither seen nor moved until somebody restores the
  product.
- **Restore** clears the flags and audits `product.restored` (with no data),
  which is also the repair for the above.
- **Duplicate** (`POST /{id}/duplicate`, `PRODUCT_CREATE`) re-validates
  everything through `create_product` under `<code>-COPY`, `-COPY-1`, … and
  copies the attributes and media; it commits twice — once inside the create
  and once for the `product.duplicated` audit row.
- **Bulk delete and restore** audit each row like the single-row twin, commit
  once, and skip a row already in the target state — but **bulk delete carries
  no guard either**, and a hundred products leave in one request.
- **Check:**
  ```sql
  select p.code, p.deleted_at, w.code as warehouse, i.current_quantity, i.reserved_quantity,
         v.total_value
  from   test_fixtures.products p
  join   test_fixtures.inventories i on i.product_id = p.id and i.is_deleted = false
  join   test_fixtures.warehouses w on w.id = i.warehouse_id
  left   join test_fixtures.product_valuations v on v.product_id = p.id
  where  p.is_deleted and (i.current_quantity <> 0 or i.reserved_quantity <> 0)
  order  by p.deleted_at;
  ```
- **Confirmed:** `T0919P81V-P` deleted holding 45 in MAIN and 5 in a bin, with
  the adjustment that would write it off refused; **TEST01 already holds 13
  deleted products carrying 432 units and 27,160.00 of valuation**, deleted on
  2026-09-16, one of them with 2 units still reserved.

### 16.15 Product import, export and barcodes (TC-MAST-008)

- **Import** — `POST /api/v1/products/import`, `PRODUCT_IMPORT`, a multipart
  form: `format=json` with a `payload`, or `csv` / `xlsx` with a `file`. All
  three end in `import_products_json`, which **loops over `create_product`, and
  that commits per row** — so a file whose second row clashes answers 409 with
  the first row written and the retry then refused as a duplicate. Customers,
  vendors, branches and warehouses all stage and commit once; the product is the
  one that does not (D-MST-9).
- The CSV and XLSX readers take seven columns (Code, Name, Type, Brand, HSN,
  SellingPrice, Status) and fill **nothing else** — no category, no units, no
  tax group, no cost — so an imported product is a shell that a later edit must
  finish.
- **Export** — `GET /api/v1/products/export?format=csv|xlsx`,
  `PRODUCT_EXPORT`, the same seven columns, cost deliberately left out. The CSV
  is built by joining the values with commas rather than through `csv.writer`,
  so a product name containing a comma shifts every column after it
  (D-MST-11); the XLSX is written with `openpyxl` and is safe.
- **A barcode on the product row** is one thing and a **packaging level's**
  barcode another: the lookup TC-MAST-008 drives is `GET
  /api/v1/uom-framework/barcode-lookup` over `product_packaging_levels`
  (§14.10), and `products.barcode` is the loose single code, unique among live
  products by `UQ_products_firm_barcode_active`.
- **Confirmed:** a two-record JSON import whose second row reused
  `T09199ZI5-PM` answered 409 "Product code already exists in this firm." and
  left `T09199ZI5-IMP1` written.

### 16.16 Branches — Masters → Branches (TC-MAST-004)

`/api/v1/branches`, `BRANCH_CREATE` / `BRANCH_UPDATE` / `BRANCH_DELETE` /
`BRANCH_RESTORE`. One commit each.

- **Create** inserts one `branches` row (code, names, type, manager, the
  address and its six place ids, timezone, currency, `gst_registration`, PAN,
  licence, `working_hours` JSON, `is_default`, `status`) and its
  `branch_attribute_values`; audit `branch.created` with the code and status.
- **The default flag is maintained.** A branch saved as the default demotes
  every other live branch of the firm first, flushed before the promotion is
  written because `UQ_branches_default_active` is checked per statement. The
  demotion of the other rows **writes no audit row of its own**.
- **Update is partial** (`exclude_unset`), so a rename keeps the address, the
  city, the GST registration and the default flag — the defect TC-MAST-004
  exists for — and `is_default` is read with the row as its fallback
  (`values.get("is_default", row.is_default)`). `display_name` is the exception
  again: sending a name resets it.
- **Delete** is refused while the branch has a live warehouse — "This branch
  still has warehouses. Remove or reassign them first." — and while
  `sales_workflow_settings` names it as the default bills ship from (D-CFG-14).
  Nothing else is checked: documents carry `branch_id` with no foreign key, so
  a branch with open orders or receipts goes.
- **Check:**
  ```sql
  select b.code, b.name, b.display_name, b.is_default, b.status, b.is_deleted,
         b.address_line1, b.gst_registration, b.pan,
         (select count(*) from test_fixtures_2.warehouses w
          where w.branch_id = b.id and w.is_deleted = false) as warehouses
  from   test_fixtures_2.branches b order by b.code;
  ```
- **Confirmed:** TEST02 holds HO and the `branch-master` fixture's
  `<SUFFIX>-BR`, which is the default — a default branch created later demotes
  the one before it; 58 `branch.created` rows across 56 stores, every one with
  its firm.

### 16.17 Warehouses — Masters → Warehouses (TC-MAST-005)

`/api/v1/warehouses`, the `WAREHOUSE_*` codes.

- **Create** resolves the branch **by id or by code** (`_resolve_branch`, so an
  import file can name `branch_code`), refuses a code no branch in the firm
  holds by name, demotes the branch's other default warehouse, inserts the row
  and its `warehouse_attribute_values`, and audits `warehouse.created` with the
  code and the branch.
- **Update is partial**, keeps the branch when neither `branch_id` nor
  `branch_code` is sent, and keeps the capacity and the nine capability flags
  a rename does not mention (TC-MAST-005).
- **Delete is refused while the warehouse holds stock** — "This warehouse still
  holds stock. Move or write it off first." — judged on `inventories` rows with
  a non-zero current **or reserved** quantity, and while
  `sales_workflow_settings` names it (D-CFG-15). A warehouse with open
  documents but no stock goes; the documents then fail at the movement, because
  `_validate_references` in the inventory service refuses a deleted warehouse.
- **Check:**
  ```sql
  select w.code, w.name, w.is_default, w.status, w.capacity, w.capacity_unit,
         w.temperature_controlled, w.cold_storage, w.has_receiving_area,
         b.code as branch,
         coalesce(sum(i.current_quantity), 0) as on_hand
  from   test_fixtures_2.warehouses w
  join   test_fixtures_2.branches b on b.id = w.branch_id
  left   join test_fixtures_2.inventories i on i.warehouse_id = w.id and i.is_deleted = false
  group  by w.id, b.code order by w.code;
  ```
- **Confirmed:** 65 `warehouse.created` rows in 56 stores; TEST01's MAIN
  carries the stock every fixture works on and cannot be deleted.

### 16.18 Storage areas — Warehouses → Storage areas

`/api/v1/warehouses/storage-nodes` and
`GET /api/v1/warehouses/{id}/storage-nodes`, `STORAGE_AREA_MANAGE`.

- **Create** inserts one `warehouse_storage_nodes` row — `node_type`
  (STORAGE_AREA, RACK, SHELF, BIN, RECEIVING_AREA), code, name, `path`,
  `sort_order`, `is_active` — under a parent that must belong to the same
  warehouse. Audit `warehouse.storage_node.created`. The code is unique per
  warehouse and the name unique per parent.
- **Update** repaths every descendant, refuses a node as its own parent, and
  refuses a parent below itself — "Circular storage hierarchy is not allowed."
  — which is the check the product category is missing (§16.13). It writes **no
  audit row**.
- **Delete** refuses a node with live children and **nothing else**. Stock is
  held per node (`inventories.storage_node_id`, the grain a physical count
  works at since D-STK-13), so a bin holding stock is deleted with no refusal,
  and the stock in it can then not be moved — "Storage node does not belong to
  the selected warehouse." (D-MST-8). It writes no audit row either.
- **Check:**
  ```sql
  select n.code, n.node_type, n.path, n.is_active, n.is_deleted,
         w.code as warehouse, coalesce(sum(i.current_quantity), 0) as on_hand
  from   test_fixtures.warehouse_storage_nodes n
  join   test_fixtures.warehouses w on w.id = n.warehouse_id
  left   join test_fixtures.inventories i on i.storage_node_id = n.id and i.is_deleted = false
  group  by n.id, w.code order by w.code, n.path;
  ```
- **Confirmed:** `T0919P81V-BIN` deleted while holding 5, and the transfer back
  out refused. Storage areas are barely used: six live nodes in `firm_shared`,
  three in WHOLE01 and one in TEST01 (beside the deleted bin), against 93 and
  45 `warehouse.storage_node.created` audit rows — the seeders have built and
  cleared them many times over.

### 16.19 Branch and warehouse types, and the two imports and exports (TC-MAST-006, TC-MAST-007)

- **Types** — `/api/v1/branch-types` and `/api/v1/warehouse-types`,
  `BRANCH_UPDATE` / `WAREHOUSE_UPDATE`. One row each, **no audit row**, an edit
  un-deletes a retired row, and **no check that anything still names the type**
  on delete — the vendor module's `_assert_master_unused` has no twin here
  (D-MST-11).
- **Import** — `POST /api/v1/branches/import` and `/warehouses/import`,
  `BRANCH_WAREHOUSE_IMPORT`, JSON records the desktop builds from the CSV.
  Both **stage the whole batch and commit once**, so a file whose fifth row
  reuses a code writes nothing and can be corrected and re-imported
  (TC-MAST-006). The warehouse file names its branch by `branch_code`.
- **Export** — `GET /api/v1/branches/export` and `/warehouses/export`,
  `BRANCH_WAREHOUSE_EXPORT`, written through `csv.writer` in **exactly the
  columns the importer reads** (`BRANCH_EXPORT_COLUMNS`,
  `WAREHOUSE_EXPORT_COLUMNS`, held to the desktop's reader by
  `tests/unit/test_import_samples_match_the_server.py`), so an export can be
  edited and imported back (TC-MAST-007). Both write nothing.
- **Confirmed:** TC-MAST-006's clash file answered 409 and left none of its
  four clean rows behind, as the case records; the staging was re-read in the
  code here and not driven again.

### 16.20 What masters do not write, and is often looked for

| You might expect | What actually happens |
| --- | --- |
| A deleted code free for a new record | Never: every master key is a plain unique index covering deleted rows (§16.0) |
| The old value of a changed price, limit, discount, unit or address | Overwritten; the audit row names the record and, except for a segment's rate, not the change (§16.2, §16.12) |
| An audit row for a category, a type, a product category or a storage-node edit | None at all (§16.0) |
| A journal from a master change | Only a customer's opening balance (§12.11); nothing else here posts |
| A deleted customer's or vendor's documents cancelled | Nothing is touched; the documents stand and refuse to move (§16.3, §16.10) |
| A deleted product's stock cleared or written off | It stays, invisible to the stock summary and unmovable (§16.14) |
| An inactive customer refused a sale | Nothing reads the status on the sales side (§16.4) |
| A vendor's bank account behind its own permission | Fixed (D-MST-10): shown only with `VENDOR_VIEW_FINANCIAL_DETAILS`, changed only with `VENDOR_MANAGE_BANK_DETAILS` (§16.7) |
| A price, a tax group or the custom fields behind `PRODUCT_PRICING_MANAGE` / `PRODUCT_TAX_MANAGE` / `PRODUCT_ATTRIBUTE_MANAGE` | Fixed (D-MST-10): a *change* to the field is refused without the duty; resending what is stored saves as before (§16.12) |
| A customer's or vendor's custom fields on the record's own audit row | They are their own table and their own timestamps (§14.5) |
| A branch or warehouse manager resolved to a person | `branch_manager_id` is a bare id: `users` lives in `platform` (§16.0) |

### 16.21 Checked against live rows, and not

- **Confirmed by driving** (2026-09-19, 15:44–15:53 IST, six fixture runs):
  a product deleted while holding stock and the stock then unmovable
  (`stock-ready` `t0919p81v`); a storage bin deleted holding 5; a product PUT
  naming three fields clearing its category, tax group, units and price, and a
  product category moved under its own child (`product-master` `t09199zi5`);
  a `SALES_MANAGER` refused a credit-limit change and allowed a 100% standing
  discount, an order for the INACTIVE customer approved, a customer created
  into a segment deleted a second earlier, and a retired segment code refused
  with the bare 409 (`customer-master` `t09193238` with `loyalty-viewer`
  `t09191qg3`); another firm's segment, vendor category and branch type
  accepted in `firm_shared` and TESTSH2's 50% priced on to TESTSH1's order
  (`shared-pair` `t0919r8y3`); a vendor deleted with 1,000.00 of GRNI
  outstanding (`po-received` `t091964t5`); a customer deleted while an approved
  order held a reservation; a product import whose second row clashed leaving
  the first written. **What the drives left:** in `test_fixtures`, deleted
  product `T0919P81V-P` (45 in MAIN, 5 in a deleted bin), deleted customers
  `T09193238-CM` and `T09191QG3-SM` with their orders SO-2026-2027-000012
  (APPROVED, 1 reserved) and -000011 (DRAFT, total 0.00), deleted vendor
  `T091964T5-V`, product `T09199ZI5-PM` stripped to its name, product
  `T09199ZI5-IMP1`, product `T09193238-P` on BOX with serial tracking on,
  retired segment `T09193238-OLD` and customer `T09193238-GRP` inside it; in
  `firm_shared`, TESTSH1's `T0919R8Y3-X1`, `-V1`, `-B1`, `-W1`, `-XP` and its
  order SO-2026-2027-000001, and TESTSH2's `T0919R8Y3-TWO`, `-VC2`, `-BT2`.
- **Confirmed from the tables** (read only, 59 schemas plus `electrolink_ops`):
  every master audit action written anywhere, and that **every one of them
  carries its firm** and a data side (one `product.restored` row is empty on
  both, and it is the only one); no
  `vendor_category.*`, `vendor_type.*`, `branch_type.*`, `warehouse_type.*`,
  `product.category.created`/`.updated`, `warehouse.storage_node.updated` or
  `.deleted` action exists anywhere; the unique indexes on all eleven master
  tables, and the three that are partial; no firm-id foreign key in any firm
  schema; TEST01's 13 deleted products with 432 units and 27,160.00; TEST01's
  five customers deleted owing 1,960.00 (§12.11); six of seven `firm_shared`
  vendors carrying a `business_attributes` blob; no cross-firm segment or
  category in any store before this pass, and none in a dedicated store
  afterwards.
- **Not seen in a live row:** a customer or vendor import (both are atomic by
  the same code the branch import is); a vendor duplicate, and the 409 a second
  one gives; a bulk category or profile assignment naming another firm's id; a
  product barcode reused after a delete; a restore refused by the default
  partial index; a branch or warehouse type deleted while a record names it; an
  XLSX product import; a `working_hours` value anything reads.

---

## 17. Territory, commission and targets — who calls on whom, what a sale earns, and what was expected (TC-TERR-001 to 005, TC-INCENT-006 to 008, TC-CONC-006)

Read on 2026-09-19 off `app/sales` (`territory_service.py`,
`scope_resolution.py`, the router), `app/commission` (`commission_service.py`,
`payout_service.py`, the router), `app/sales_targets`
(`sales_target_service.py`, the router) and what they call —
`DocumentPostingService.post_commission_accrual` and
`post_commission_payment`, `JournalEntryEngine.reverse_entry`,
`FirmMetadataReader`, and the five sales services that call
`resolve_sales_scope`. `docs/TERRITORY_FRAMEWORK.md` and
`docs/COMMISSION_FRAMEWORK.md` are the references for *why*; this is *which
rows*.

**Earlier sections carry what is not repeated here**: the geography ladder
(countries to localities) and its platform-only writes are §14.12, the order,
note, invoice and receipt a commission is measured on are §11, the journals'
own tables and periods §12, and who may hold which role §15.6.

Checked read-only against every store on the local server that holds the
territory tables (59 schemas in `agency_platform` plus `electrolink_ops` in
`agency_electrolink`), and driven against the running backend on one
`commission-firm` fixture run of this pass, `t0919tkvs` — a firm of its own,
`T0919TKVS-T`, in schema `fx_t0919tkvs_t`. **Nothing was written to the demo
firms** (WHOLE01, MEDI01, FOOD01, ELEC01); they were read only. §17.18 says
which claims a live row confirmed and which it could not; a claim marked *(not
seen in a live row)* was read off the code only.

### 17.0 Before you look

- **Stores.** Every table here is firm-owned and lives in the firm's own
  store. `territory-firm` and `commission-firm` build **a firm of the run's
  own**, so put the schema the fixture's **Tables** line prints
  (`fx_<suffix>_t`); WHOLE01 is `wholesale_hub`, MEDI01 and FOOD01
  `firm_shared` (filter on `firm_id`), ELEC01 `electrolink_ops` in the
  `agency_electrolink` database. TEST01 holds no territory, rule, payout or
  target at all.

  | Case | Fixture | Schema |
  | --- | --- | --- |
  | TC-TERR-001 to 005 | `territory-firm` | `fx_<suffix>_t` |
  | TC-INCENT-006 to 008, TC-CONC-006 | `commission-firm` | `fx_<suffix>_t` |

- **The tables.**

  | Tables | Rows per |
  | --- | --- |
  | `sales_hierarchy_configs`, `sales_hierarchy_levels` | one config per firm and its named levels — Region / Territory / Route in every store here |
  | `sales_territories` | every node at every level: `parent_id`, `path` (the codes joined by slashes), `status` |
  | `territory_route_profiles`, `territory_working_days` | the one row that makes a node a **route** (`UQ_territory_route_profiles_territory`), its effective window, and one row per working weekday 1..7 |
  | `territory_customer_assignments` | shop ⇄ node: `is_primary`, `visit_sequence`, `is_potential` |
  | `territory_salesman_assignments` | person ⇄ node: `is_primary`, `include_children`; `user_id` is a **bare id**, `users` being platform |
  | `sales_route_types` | the firm's kinds of round |
  | `sales_beat_plans`, `sales_beat_plan_customer_stops` | when a route runs, and optionally the outlets of one day |
  | `commission_rules`, `commission_rule_slabs` | a rate, its scope and window, and its ladder |
  | `commission_payouts` | one period's commission for one person, DRAFT to PAID |
  | `sales_targets` | one expectation for one period, of a person, a node, or the firm |

  `address_masters` has no client and no live row anywhere. Call lists,
  coverage, the commission report and target achievement are **computed on
  every read and stored nowhere**.
- **No foreign key reaches a person.** `commission_rules.salesman_id`,
  `commission_payouts.salesman_id` and `sales_targets.salesman_id` are declared
  with a key to `users` in the ORM, and **no store carries it** — `users` is
  pruned from a firm store, so the constraint is never built. The only keys on
  these tables are to products, product categories, territories, ledger
  accounts and journal entries. What the service does not check, nothing
  checks -- so since #614 the rule and the target both check it themselves,
  through `FirmMetadataReader`, which reads the **platform** store
  (D-TER-15). `commission_payouts.salesman_id` still names whoever the
  accrual found, which is right: a payout is a record of what somebody
  earned while they were here.
- **The audit rows are the firm's own, every one carries its firm, and most
  say very little.** `sales_territory.created` / `.updated` / `.deleted` /
  `.restored` / `.moved` / `.status_changed` / `.customers_set` /
  `.salesmen_set`, `sales_territory.hierarchy.updated`,
  `sales_territory.route_type.*`, `sales_territory.beat_plan.*`,
  `commission.rule.created` / `.updated` / `.deleted`,
  `commission.payout.accrued` / `.updated` / `.approved` / `.paid` /
  `.cancelled`, `sales_target.created` / `.updated` / `.deleted`. The payout
  rows carry a full before and after; a rule row its whole shape **except
  `measure`**. Since #615 `customers_set` and `salesmen_set` carry the ids on
  both sides plus `added` and `removed`; `.deleted` and `.restored` carry the
  node; the hierarchy row carries the four settings and the levels; every
  `beat_plan.*` row carries the plan; and a target row carries the whole
  target (D-TER-16). `sales_territory.updated` still carries the code and path
  and nothing about the route profile. Query them:
  ```sql
  select created_at, action, entity_type, entity_id, actor_id,
         before_data::jsonb - '_meta' as before, after_data::jsonb - '_meta' as after
  from   fx_<suffix>_t.audit_logs
  where  action ~ '^(sales_territory|commission|sales_target)'
  order  by created_at desc;
  ```
- **Two writes reach the ledger, and one takes one off.** Approving a payout
  posts `COMM-<yyyymm>-<id8>` (Dr `COMMISSION_EXPENSE` 5600 / Cr
  `COMMISSION_PAYABLE` 2400), paying it posts `…-PAY` (Dr 2400 / Cr the account
  named), cancelling an approved one posts `…-REV`. All three carry
  `source_module = 'commission'` and the payout as `source_id`. Nothing in
  territory or targets posts anything.
- **What points at what.**

  | From | Column | To |
  | --- | --- | --- |
  | `sales_orders`, `sales_invoices`, `delivery_notes` | `territory_id`, `route_id`, `salesman_id` | a node, a **`territory_route_profiles.id`** (not a node id), a user |
  | `sales_quotations`, `sales_returns` | `territory_id`, `salesman_id` | the same, with no route column |
  | `sales_beat_plans` | `territory_id` | a node that must be a route when the plan is written, and is not looked at again |
  | `commission_rules` | `salesman_id`, `product_id`, `product_category_id` | NULL on all three is the firm-wide rule about the whole document |
  | `sales_targets` | `salesman_id`, `territory_id` | NULL on both is the firm's own number |
  | `commission_payouts` | `journal_entry_id`, `payment_journal_entry_id`, `money_account_id` | the accrual, the payment, and the account the money left |
- **The keys.** `UQ_territory_customer_assignments_pair_active`,
  `…_primary_active` and `…_sequence_active` are partial on live rows, and
  `UQ_commission_payouts_period_active` on live, un-cancelled rows.
  `UQ_sales_territories_firm_code`, `UQ_sales_beat_plans_firm_code` and
  `UQ_territory_salesman_assignments_territory_user` are **plain**, so a
  deleted territory or plan keeps its code for ever. The service's own check
  filtered `is_deleted` and the refusal then arrived as the bare 409; since
  #615 both checks look at retired rows too and name where the code went --
  "A deleted territory holds the code RT01. Restore it, or use another code."
  (D-TER-16).
  `UQ_sales_targets_scope_period` was plain over
  (`firm_id`, `salesman_id`, `territory_id`, `period_start`): since neither
  dialect equates two NULLs it held nothing for a target that left either
  scope blank — nearly all of them — it covered deleted rows, and it left
  `basis` out while the service allows one INVOICED and one COLLECTED target
  over the same days. `UQ_sales_targets_scope_period_active` replaces it
  (`20260924_0157`), partial on live rows, with both scopes `coalesce`d onto
  the nil UUID and `basis` in the key.
  `UQ_commission_rules_scope_start_active` is the same shape for a rule's
  scope and start date, partial on live ACTIVE rows, and is what the overlap
  read had nothing behind it (D-TER-16). Neither expresses an **overlapping**
  window, only a shared start; the service checks stay authoritative for that,
  as they do beside `UQ_commission_payouts_period_active`.
- **Concurrency.** Territories, route types, beat plans, commission rules,
  payouts and targets publish `version` as an `ETag` and on the body, and take
  `If-Match`. The two whole-list replaces — a round's customers and a node's
  salespeople — carry no version: the last save wins, and the proof that the
  list was read first is the desktop's (`docs/TERRITORY_FRAMEWORK.md`).

### 17.1 The hierarchy and route types — Sales → Geography, Route Types (TC-TERR-001)

`GET` and `PUT /api/v1/sales-territories/hierarchy-levels`; the read takes
`TERRITORY_VIEW`, the write is **platform-admin** by designation.
`/route-types` takes `TERRITORY_VIEW` / `_CREATE` / `_UPDATE` / `_DELETE`.

- **The first read of a new firm writes.** `_ensure_hierarchy_config` inserts
  one `sales_hierarchy_configs` row and three `sales_hierarchy_levels` rows
  (REGION, TERRITORY, ROUTE) and **commits them** (D-11-1), with no audit row.
- **A save** rewrites the four settings (`max_levels`,
  `allow_multi_route_per_salesman`, `allow_multi_salesman_per_route`,
  `enforce_customer_leaf_assignment`) and replaces the levels; audit
  `sales_territory.hierarchy.updated`, which was empty on both sides and
  since #615 carries the four settings and the levels by order, code and
  display name (D-TER-16).
- **A route type** is one `sales_route_types` row; delete is refused while a
  live route profile names it — "<n> route(s) still use this route type.
  Reassign them before deleting it."
- **Check:**
  ```sql
  select c.max_levels, c.allow_multi_route_per_salesman, c.allow_multi_salesman_per_route,
         c.enforce_customer_leaf_assignment, l.level_order, l.level_code, l.display_name, l.is_enabled
  from   fx_<suffix>_t.sales_hierarchy_configs c
  join   fx_<suffix>_t.sales_hierarchy_levels l on l.config_id = c.id and l.is_deleted = false
  order  by l.level_order;
  ```
- **Confirmed** in `fx_t0919tkvs_t`: one config, three levels, one
  `hierarchy.updated` and one `route_type.created` from the fixture.

### 17.2 Create a territory or a route — Geography → New (TC-TERR-001)

`POST /api/v1/sales-territories`, `TERRITORY_CREATE`. One commit.

- **Inserts** one `sales_territories` row (`path` = the parent's path, a
  slash, the code; `business_profile_id` from the firm's profile). With a
  `route_profile` in the body, one `territory_route_profiles` row and one
  `territory_working_days` row per weekday. Audit `sales_territory.created`
  with the code and name.
- **Refused, nothing written:** a code a live node holds; a name a live
  sibling holds; a level that is not exactly one below the parent's — "Territory
  level must be exactly one level below its parent."; a top-level node that is
  not level 1; `max_nodes_per_parent` reached.
- **Whose masters they are is checked since #614.** `_level` takes the firm
  wherever the id came off a request body, and `_upsert_route_profile` resolves
  `route_type_id` through `_route_type`, which is firm-scoped: both live in the
  shared store, where a key is satisfied by another firm's row (D-TER-15). A
  code a **deleted** node holds is refused by name since #615 (D-TER-16).
- **Check:**
  ```sql
  select t.path, t.status, t.is_deleted, l.display_name as level,
         p.id as route_profile_id, p.visit_frequency, p.effective_from, p.effective_to,
         p.is_deleted as profile_gone,
         (select string_agg(d.weekday::text, ',' order by d.weekday)
          from fx_<suffix>_t.territory_working_days d
          where d.route_profile_id = p.id and d.is_deleted = false) as days
  from   fx_<suffix>_t.sales_territories t
  join   fx_<suffix>_t.sales_hierarchy_levels l on l.id = t.hierarchy_level_id
  left   join fx_<suffix>_t.territory_route_profiles p on p.territory_id = t.id
  order  by t.path;
  ```
- **Confirmed:** the fixture's six nodes, three of them routes; `T0919TKVS-R-X`
  created with a profile and Monday.

### 17.3 Edit, move, deactivate, delete and restore a territory

`PUT /{id}` (`TERRITORY_UPDATE`, `If-Match` optional), `POST /bulk/status` and
`/bulk/move` (`TERRITORY_UPDATE`), `DELETE /{id}` (`TERRITORY_DELETE`),
`POST /{id}/restore` (`TERRITORY_RESTORE`).

- **The edit is a whole replace, and the route profile is part of it.**
  `TerritoryUpdate` *is* `TerritoryCreate`, every column is assigned from the
  body, and `_upsert_route_profile` is called with whatever `route_profile`
  holds — so a PUT that leaves it out **soft-deletes the profile** and the node
  stops being a route: its beat plans report "The route is not in force on this
  date.", a new plan is refused "… is not a route.", and documents stop being
  tagged with it (D-TER-7). Sending the profile again un-deletes the same row.
- **A changed code or parent repaths every descendant**
  (`_repath_descendants`). Audit `sales_territory.updated` with the code and
  path on both sides — and `before.code` is read **after** the row was
  assigned, so a rename records the new code twice (D-TER-16). A bulk move
  writes one `sales_territory.moved` per node with the two paths and commits
  once; a bulk status change one `sales_territory.status_changed` each.
- **`status` is a label.** Nothing in `resolve_sales_scope` or the call list
  reads `sales_territories.status`, so an INACTIVE round still tags a sale and
  is still called (D-TER-16).
- **Delete** is soft (`is_deleted`, `deleted_at`, `deleted_by`), audit
  `sales_territory.deleted` with nothing on either side, and is refused while
  the node has live children, customers or salespeople -- **and, since #612,
  while a live beat plan or a live sales target names it**, the refusal
  listing the plan codes or the target periods so the caller knows what to
  retire first (D-TER-14). The call list also skips a plan whose round is in
  the bin, for the rows retired before the guard existed. The route profile
  and its working days are left as they are.
- **A node in the bin refuses to be changed.** `update_territory`,
  `update_beat_plan`, `bulk_status_change` and `bulk_move` all load with
  `include_deleted=True` so that they can report a stale id honestly, and
  every one of them then wrote: a PUT renamed a territory that was in the bin
  and left it there (D-TER-14, #612). Restore is the endpoint for bringing one
  back; it clears the three columns, audits `sales_territory.restored`, and
  re-checks neither the code nor that the parent is still live.
- **Check:** §17.2's query, and the plans and targets a node still carries:
  ```sql
  select t.code, t.is_deleted,
         (select count(*) from fx_<suffix>_t.sales_beat_plans b
          where b.territory_id = t.id and b.is_deleted = false) as live_plans,
         (select count(*) from fx_<suffix>_t.sales_targets g
          where g.territory_id = t.id and g.is_deleted = false) as live_targets
  from   fx_<suffix>_t.sales_territories t order by t.path;
  ```
- **Confirmed:** a PUT of `T0919TKVS-R-N2` without `route_profile` answered 200
  with `route_profile: null`, its three plans then "not in force", and a second
  PUT brought the same profile row back at `version` 3; `T0919TKVS-R-X` deleted
  204 carrying one live plan and one live target, `GET /call-lists` for the
  Monday still answering `T0919TKVS-BP-X` `occurs: true`, and a PUT then
  renaming the deleted node to `-R-X2`.

### 17.4 A round's customers — Route Builder, the node's Customers tab (TC-TERR-004)

`PUT /api/v1/sales-territories/{id}/customers`, `TERRITORY_ASSIGN_CUSTOMERS`;
`POST /bulk/customers` the same for several nodes in **one commit**. The body
is either `customer_ids` (membership only) or `entries`
(`customer_id`, `visit_sequence`, `is_primary`, `is_potential`).

- **Replaces the whole list for this node only.** A shop the list leaves out
  is soft-deleted; a shop it adds is inserted, or its old row **un-deleted**;
  rows for the same shop on other rounds are not touched.
- **`visit_sequence` is position, and the swap is safe.** Every stop number
  about to be reassigned is set to NULL and flushed before the new ones are
  written, because `…_sequence_active` is checked per statement and a partial
  index cannot be deferred. Only the numbers actually moving are released: the
  `customer_ids` shape leaves every sequence where it was — including the gap a
  removed shop leaves behind.
- **`is_primary` omitted means leave alone.** A new row is primary only when
  the shop is primary on no other round. **An un-deleted row keeps the flag it
  was retired with**, so a shop that was primary here, left, and became primary
  elsewhere cannot be brought back from the picker: the save trips
  `…_primary_active` and answers the bare 409 "The operation violates
  uniqueness constraints." (D-TER-10).
- **Refused, nothing written:** a customer that is not this firm's, or is
  deleted — "One or more customers do not belong to the active firm."; two
  entries on one stop number (422, naming the numbers); a node that is not a
  leaf when `enforce_customer_leaf_assignment` is on.
- **Audit:** one `sales_territory.customers_set` on the **territory**. It
  carried `customer_count` and nothing else, so who joined or left a round was
  on no trail at all; since #615 it also carries the ids on both sides and the
  `added` / `removed` lists (D-TER-16). The call **order** is still not
  recorded.
- **Check:**
  ```sql
  select t.code as round, c.code as shop, a.visit_sequence, a.is_primary,
         a.is_potential, a.is_deleted, a.version
  from   fx_<suffix>_t.territory_customer_assignments a
  join   fx_<suffix>_t.sales_territories t on t.id = a.territory_id
  join   fx_<suffix>_t.customers c on c.id = a.customer_id
  order  by t.code, a.is_deleted, a.visit_sequence nulls last, c.code;
  ```
- **Confirmed:** `T0919TKVS-C1` taken off N1 (row deleted, `is_primary` still
  true), added to S1 (new row, primary), and the save putting it back on N1
  answered 409 with nothing written; C2 kept stop 2 with stop 1 empty.

### 17.5 A node's salespeople — the Salespeople tab, Coverage (TC-TERR-001)

`PUT /api/v1/sales-territories/{id}/salesmen`, `TERRITORY_ASSIGN_SALESMEN`;
`POST /bulk/salesmen` in one commit.

- **Replaces the whole list**: a person left out is soft-deleted, one added is
  inserted or un-deleted, and `include_children` and `is_primary` are written
  from the body every time — `is_primary` defaults to **false**, so a client
  that omits it demotes (the customer list's "leave alone" has no twin here).
  Deliberate, and said so on the schema since #615: a round may have several
  people and "primary" is the one a document is attributed to, so a save that
  said nothing about it cannot be read as "promote whoever is first in the
  list" (D-TER-16).
- **Checked through the platform store**: every `user_id` must be an active
  member of this firm (`FirmMetadataReader.active_member_count`) — "One or more
  salesmen are not active firm members." The two hierarchy settings are
  applied: "… may have only one salesperson." and "A salesperson here is
  already on …".
- **Leaving the firm takes them off its rounds since #618.** `PUT
  /users/{id}/firms` and `DELETE /users/{id}` open each departed firm's own
  store (`firm_store_session`) and retire the person's
  `territory_salesman_assignments` there, one
  `sales_territory.salesman_retired` audit row per round in that firm's trail.
  A membership switched off in place counts as much as one removed, because
  `active_member_count` filters both. Until then the rows stayed live: #575
  had fixed only the **read**, so a departed assignee was no longer derived on
  to new orders (§17.8, D-TER-11) but the round's Salespeople tab went on
  listing them (D-TER-17). The two writes are not one transaction and cannot
  be -- they are different databases -- so the platform fact is committed
  first and the firm stores follow it.
- **Audit:** `sales_territory.salesmen_set`. It carried `salesman_count`
  alone and since #615 also carries the ids on both sides and the `added` /
  `removed` lists (D-TER-16).
- **Check** (the platform join works where the firm's store is in
  `agency_platform`):
  ```sql
  select t.code as round, u.full_name, a.is_primary, a.include_children, a.is_deleted,
         u.is_deleted as person_gone,
         exists (select 1 from platform.user_firms f
                 where f.user_id = a.user_id and f.firm_id = t.firm_id
                   and f.is_active and f.is_deleted = false) as still_a_member
  from   fx_<suffix>_t.territory_salesman_assignments a
  join   fx_<suffix>_t.sales_territories t on t.id = a.territory_id
  left   join platform.users u on u.id = a.user_id
  order  by t.code;
  ```
- **Confirmed:** Asha live on N1 and S1 with `person_gone` true after the
  platform administrator deleted her.

### 17.6 Beat plans — Sales → Beat Plans (TC-TERR-002, TC-TERR-003)

`/api/v1/sales-territories/beat-plans`, `TERRITORY_CREATE` / `_UPDATE` /
`_DELETE`.

- **Create** inserts one `sales_beat_plans` row (`plan_type`, `weekday`,
  `week_of_month`, `starts_on`, `ends_on`, `is_active`) and one
  `sales_beat_plan_customer_stops` row per outlet named; the node must carry a
  live route profile — "… is not a route. Turn on 'This is a route' for it
  before scheduling a beat plan against it." — and every outlet must be this
  firm's.
- **The edit is a whole replace**, stops included: they are all soft-deleted
  and re-inserted from the body, so a PUT that leaves `customer_stops` out
  clears them (D-TER-7). It too loads with `include_deleted=True`.
- **Audit:** `sales_territory.beat_plan.created` / `.updated` / `.deleted`.
  `.updated` always carried both sides; since #615 `.created` and `.deleted`
  carry the plan too (D-TER-16).
- **Check:**
  ```sql
  select b.code, t.code as route, t.is_deleted as route_gone, b.plan_type, b.weekday,
         b.week_of_month, b.starts_on, b.ends_on, b.is_active, b.is_deleted,
         (select count(*) from fx_<suffix>_t.sales_beat_plan_customer_stops s
          where s.beat_plan_id = b.id and s.is_deleted = false) as own_stops
  from   fx_<suffix>_t.sales_beat_plans b
  join   fx_<suffix>_t.sales_territories t on t.id = b.territory_id
  order  by b.code;
  ```
- **Confirmed:** the fixture's nine plans, none with stops of its own — **no
  store anywhere holds a `sales_beat_plan_customer_stops` row**.

### 17.7 Call lists and coverage — Sales → Call Lists, Coverage (TC-TERR-002, TC-TERR-003)

`GET /call-lists?date=&salesman_id=`, `GET /beat-plans/{id}/call-list?date=`,
`GET /dashboard`, `GET /coverage/salesmen`; all `TERRITORY_VIEW`. **They write
nothing.**

- A plan occurs when its recurrence says so (`_occurs_on`), the route's
  effective window covers the date, and the route works that weekday; each
  refusal carries its reason. The date defaults to `utc_now().date()`.
- Stops are the plan's own outlets, else the node's live assignments ordered
  by `visit_sequence` with the unplaced last — ranked on an explicit `case`, so
  PostgreSQL and SQLite agree.
- The plan's salesperson is the node's primary assignment, read without
  looking at whether they are still a member.
- The territory is read **without** its `is_deleted` flag, which is how a
  deleted round goes on being called (§17.3).
- **Confirmed:** "1 of 9 plan(s) run" on Monday 2026-09-21 and the four on
  2027-01-12, as TC-TERR-002 and 003 record; `T0919TKVS-BP-COLL` "not in force"
  while N2's profile was gone.

### 17.8 How a document gets its territory, route and salesperson (TC-TERR-005)

`resolve_sales_scope` in `app/sales/services/scope_resolution.py`, called by
quotation and order on create and edit, and by invoice and return **only to
fill blanks** on a document with no source; a delivery note takes all three
from its order. It writes three columns on the document and nothing else.

- **Blank is derived, and derivation refuses to guess.** Territory: the shop's
  one primary assignment, or its only one. Salesperson: the node's one primary,
  or its only one, else the nearest ancestor whose person has
  `include_children`. Route: the profile on the node or its nearest ancestor
  **that was in force on the document's own date** — a closed round leaves
  `route_id` NULL and the territory still applies.
- **What the caller names is validated — except the route.** A territory must
  be this firm's and one the customer is on; a salesperson must cover it — "The
  selected salesperson is not assigned to this territory." A **`route_id` is
  kept as sent**: the order and invoice services check only that the profile
  exists, not that it is this firm's, the customer's, the territory's or in
  force, so an order is tagged to a round that ended in June, or to somebody
  else's (D-TER-9).
- **Membership is checked wherever the caller names a person.** Order,
  delivery note and invoice each ask `active_member_count` through the
  platform store in their own service — "Salesman is not an active member of
  this firm." — and since #614 `_validated_salesman` asks it too, before
  coverage and whether or not there is a territory, which is what closes
  quotation and sales return: they had no check of their own, so with no
  territory to check against any id at all was stored (D-TER-15). A
  **derived** person is never
  checked, so somebody who has left the firm is put on the order, the order
  approves and reserves stock, and the delivery note — which does check — is
  refused (D-TER-11).
- **Check:**
  ```sql
  select o.order_number, o.order_date, o.status, c.code as customer,
         t.code as territory, rt.code as route_is_on, p.effective_from, p.effective_to,
         o.salesman_id
  from   fx_<suffix>_t.sales_orders o
  join   fx_<suffix>_t.customers c on c.id = o.customer_id
  left   join fx_<suffix>_t.sales_territories t on t.id = o.territory_id
  left   join fx_<suffix>_t.territory_route_profiles p on p.id = o.route_id
  left   join fx_<suffix>_t.sales_territories rt on rt.id = p.territory_id
  order  by o.order_number;
  ```
- **Confirmed:** with S1's window closed at 2026-06-30, SO-2026-2027-000004
  (blank) took territory S1, Asha and **no route**; -000005 naming S1's closed
  profile and -000006 naming N2's were both saved as sent; QT-2026-2027-000001
  for the unrouted `T0919TKVS-SN` kept a random salesman id while the same id
  on an order answered 422; with Asha deleted, SO-2026-2027-000008 was created
  and approved in her name and its delivery note refused. Every demo order,
  note and invoice carries all three (WHOLE01 72 / 62 / 53, ELEC01 58 / 58 /
  49); the selling fixtures, which draw no rounds, carry none.

### 17.9 Territory bulk actions, copy, import and export

`POST /{id}/copy` (`TERRITORY_CREATE`), `POST /import` (`TERRITORY_IMPORT`),
`GET /export` (`TERRITORY_EXPORT`), and the four `/bulk/*` routes.

- **Import** stages every row through `create_territory(commit=False)` and
  `set_customers(commit=False)` and **commits once**; a row naming an unknown
  level refuses the file. **The four bulk routes** do the same.
- **Copy does not.** `copy_hierarchy` calls `create_territory`,
  `set_customers` and `set_salesmen` with their default `commit=True` for every
  node, so a copy refused partway — a salesperson policy, a node cap — leaves
  the nodes before it written. It also finds the subtree with
  `path.ilike('<source path>%')`, which takes a sibling whose code merely
  starts the same way, and treats `_` and `%` in a code as wildcards
  (D-TER-13) *(not seen in a live row)*.
- **Export** writes nothing; three CSVs and an XLSX, read off the same rows.
- **Audit:** one row per node as in §17.2 to §17.5; no row for the import or
  the copy as such.

### 17.10 Commission rules — Sales → Commission → Rules (TC-INCENT-006)

`/api/v1/commission/rules`; reads `COMMISSION_VIEW`, writes
`COMMISSION_MANAGE`. One commit each.

- **Create** inserts one `commission_rules` row and one `commission_rule_slabs`
  row per rung, numbered by `from_amount`. **Edit is partial**
  (`exclude_unset`): absent leaves a column alone, an explicit null clears
  `effective_to`, the cap, the floor, or moves the rule to the firm-wide scope;
  `slabs` omitted leaves the ladder, `[]` removes it. A ladder is **replaced**:
  every live rung is soft-deleted and the new ones inserted. Delete is soft.
- **`measure` is accepted and never stored.** Both write schemas declare it,
  neither `create_rule` nor `update_rule` assigns it, and `rule_response` does
  not pass it, so a MARGIN rule is saved — and read back — as VALUE and pays
  on the whole sale price. The only MARGIN rows anywhere were written by the
  demo seeder straight on to the column, and the seeder's own `create_rule`
  call for a fresh store loses it the same way (D-TER-1).
- **A rule with slabs ignores `percentage`** — the schema still requires one
  on create, and the fixtures send 0. The desktop labels the box "Rate
  (unused)" and the grid shows no single rate for a ladder or a per-unit rule.
- **Refused, nothing written:** a per-unit rate on the COLLECTED basis or with
  no product or category; a product *and* a category; a ladder that does not
  start at 0, has a gap or an overlap, or is open-ended below the top; a second
  ACTIVE rule over the same person, goods and days — "Another active rule
  already covers part of that period for the same scope (from …)." That last
  check was a read followed by an insert with no key behind it;
  `UQ_commission_rules_scope_start_active` (`20260924_0157`) is the backstop
  for two requests that both read before either commits (D-TER-16).
- **Who and what the rule names is checked since #614.** `salesman_id` must be
  an active member, read through the platform store — an unknown id used to be
  saved and listed as "Former member"; `product_id` and `product_category_id`
  must be **this firm's** live rows, answered as "not found" rather than as the
  bare 409 the foreign key gave (D-TER-15).
- **Audit:** `commission.rule.created` / `.updated` / `.deleted` with the whole
  rule and its ladder, `measure` excepted.
- **Check:**
  ```sql
  select r.status, r.salesman_id, r.effective_from, r.effective_to, r.basis, r.measure,
         r.rate_type, r.percentage, r.per_unit_amount, r.minimum_amount, r.bonus_percentage,
         r.max_commission_amount, r.slab_mode, p.code as product, g.name as category,
         (select string_agg(s.from_amount || '-' || coalesce(s.to_amount::text, '') || ' @' || s.percentage, ', '
                            order by s.from_amount)
          from fx_<suffix>_t.commission_rule_slabs s
          where s.commission_rule_id = r.id and s.is_deleted = false) as ladder
  from   fx_<suffix>_t.commission_rules r
  left   join fx_<suffix>_t.products p on p.id = r.product_id
  left   join fx_<suffix>_t.product_categories g on g.id = r.product_category_id
  where  r.is_deleted = false order by r.created_at;
  ```
- **Confirmed:** a PUT of `{"measure": "MARGIN"}` answered 200 with
  `measure: VALUE` and `version` 2, a POST of a MARGIN rule 201 with VALUE, and
  the column reads VALUE for both; an unknown salesman 201, an unknown product
  409. Every live rule in every store is COLLECTED and PERCENT: **no INVOICED
  rule, per-unit rate or cap exists in a live row**.

### 17.11 The commission report — Commission → Collected (TC-INCENT-006)

`GET /api/v1/commission/report?from_date=&to_date=&salesman_id=`,
`COMMISSION_VIEW`. **Writes nothing**; everything below is recomputed on every
read.

- **Collected** is `settlement_allocations` joined to a POSTED RECEIPT
  settlement dated in the window, per allocation; **invoiced** is
  `sales_invoices.grand_total` of APPROVED and CLOSED bills dated in the
  window. Attribution is the invoice's own `salesman_id`; money with none is
  the **Unassigned** row, which earns nothing and is never paid.
- **The governing rule is resolved per row on its own date** — the receipt's
  date for collected money, the bill's for invoiced — in six rungs (the
  person's product, category, unscoped rule, then the firm's three), and a rule
  pays only on its own basis. Each invoice's `grand_total` is apportioned over
  its lines so an unscoped rule measures exactly the document; each rule's
  subtotal is laddered **separately**, then floor, bonus and cap are applied in
  that order.
- **A margin line with no cost contributes nothing**
  (`sales_invoice_lines.cost_amount` NULL is not zero), and a sale below cost
  earns zero rather than a negative.
- **It is measured on the document total, tax and freight included** — an open
  question the owner has left as it is (`docs/COMMISSION_FRAMEWORK.md`).
- **Nothing is ever taken off.** A credit note, a sales return and a refund
  are read by neither sum, so a bill credited in full goes on counting as
  invoiced, as collected and as commission (D-TER-3). A **reversed** receipt
  does drop out.
- **An advance counts on the day it arrived, not the day it was applied.**
  `POST /receipts/{id}/allocate` adds the allocation to the original
  settlement and the report dates it by `settlement_date`, so money taken in
  August and set against a September bill is August's collection — a month
  whose payout may already be accrued, where it will never be paid (D-TER-6).
- **`target_met`** is the person's targets over the window **summed** against
  their achievements summed (§17.15); null where they have none.
- **Check** — what the report walks, per salesperson:
  ```sql
  select i.salesman_id, s.settlement_number, s.settlement_date, s.status,
         i.invoice_number, i.invoice_date, a.amount
  from   fx_<suffix>_t.settlement_allocations a
  join   fx_<suffix>_t.settlements s on s.id = a.settlement_id
  join   fx_<suffix>_t.sales_invoices i on i.id = a.sales_invoice_id
  where  a.is_deleted = false and s.direction = 'RECEIPT'
  order  by s.settlement_date, s.settlement_number;
  ```
- **Confirmed:** Asha 5,900.00 / 495.60 and Bala 4,720.00 / 94.40, as
  TC-INCENT-006 records; RC-2026-2027-000004 (118.00, 2026-08-15) applied to
  SI-2026-2027-000004 of 2026-09-19 and reported as **August's** 118.00 and
  4.72; CN-2026-2027-000001 for the whole of SI-2026-2027-000003, APPROVED, and
  Bala's row unchanged at 4,720.00 / 4,720.00 / 188.80.

### 17.12 Accrue a period — Commission → Payouts → Accrue period (TC-INCENT-007, TC-CONC-006)

`POST /api/v1/commission/payouts/accrue`, `COMMISSION_MANAGE`. One commit for
the whole run.

- **Reads the report once and stores what it said**: one DRAFT
  `commission_payouts` row per person who earned anything — `basis`,
  `measured_amount` (collected or invoiced, by basis), `earned_amount`,
  `payable_amount` equal to it, `adjustment_amount` 0, `accrued_on` = the date
  sent, else **`period_end`**. Nobody who earned nothing, and never the
  Unassigned row. Nothing downstream reads the report again. **No journal.**
- **One live payout per person per overlapping period**:
  `_assert_period_is_free` answers 409 "A commission payout already covers part
  of that period for this salesman (… to …)." and
  `UQ_commission_payouts_period_active` catches the race the read cannot, as
  "A commission payout for that period was created while this one was being
  worked out." A run for everybody is all-or-nothing, so one person's existing
  payout refuses the whole run; name a `salesman_id` to accrue the rest.
- **The period need not be over, and need not be a month.** Accruing
  September on the 19th is accepted, takes what has been collected so far, and
  **holds the period**: whatever is collected from the 20th is covered by a
  payout that no longer reads the report, and once that payout is PAID it
  cannot be cancelled. `accrued_on` is then a date that has not arrived
  (D-TER-6). `period_start` 2026-09-10 to `period_end` 2026-10-15 is accepted
  too.
- **Audit:** one `commission.payout.accrued` per row, with the snapshot.
- **Check:**
  ```sql
  select p.status, p.salesman_id, p.period_start, p.period_end, p.accrued_on, p.paid_on,
         p.basis, p.measured_amount, p.earned_amount, p.adjustment_amount, p.adjustment_reason,
         p.payable_amount, p.version,
         j.reference_number as accrual, j.journal_date as accrual_dated,
         pj.reference_number as payment, pj.journal_date as payment_dated,
         a.code as paid_from
  from   fx_<suffix>_t.commission_payouts p
  left   join fx_<suffix>_t.journal_entries j  on j.id  = p.journal_entry_id
  left   join fx_<suffix>_t.journal_entries pj on pj.id = p.payment_journal_entry_id
  left   join fx_<suffix>_t.ledger_accounts a  on a.id  = p.money_account_id
  where  p.is_deleted = false order by p.created_at;
  ```
- **Confirmed:** Bala 94.40 on 4,720.00 and Asha 495.60 on 5,900.00, both
  2026-09-01 to 2026-09-30 with `accrued_on` 2026-09-30, accrued on the 19th;
  the run for everybody refused 409 once Bala's existed; a second payout for
  Asha over 2026-09-10 to 2026-10-15 accepted after hers was cancelled, again
  495.60; a run for 2026-09-20 to 2026-09-25 answered "Nobody earned anything in
  that period." — nothing was collected in those days — and wrote nothing.

### 17.13 Adjust, approve and cancel a payout (TC-INCENT-007)

`PUT /payouts/{id}`, `POST /payouts/{id}/approve`, `POST /payouts/{id}/cancel`;
all `COMMISSION_MANAGE`, `If-Match` optional.

- **Adjust** — DRAFT only. Writes `adjustment_amount`, `adjustment_reason`,
  `notes`, and `payable_amount` = earned + adjustment; a non-zero adjustment
  needs a reason, and a negative total is refused. **`status` is not writable
  here** — the schema forbids the field (422). There is no ceiling on a
  positive adjustment. Audit `commission.payout.updated`, before and after.
- **Approve** — DRAFT only, and not a payout of nothing. Posts
  **`COMM-<yyyymm>-<first 8 of the id>`**: Dr `COMMISSION_EXPENSE` / Cr
  `COMMISSION_PAYABLE` for `payable_amount`, dated **`accrued_on`**, in the
  period open on that date — with none, or with either control account
  unmapped, the approval is refused and nothing is written. Sets
  `journal_entry_id`, status APPROVED.
  Audit `commission.payout.approved`.
- **Cancel** — DRAFT or APPROVED, never PAID ("Record a payment the other way
  rather than cancelling it."). An approved one is reversed with
  `reverse_entry`: a mirror entry **`…-REV`** dated `accrued_on`, the original
  marked REVERSED, the payout's `journal_entry_id` left pointing at it. Status
  CANCELLED, which releases the period. Audit `commission.payout.cancelled`.
- **Nobody is compared with anybody.** Approve and pay look at the status and
  at nothing else — not at who accrued it, who approved it, or **whose payout
  it is** — and the seeded `ACCOUNTANT` and `FIRM_ADMIN` hold `COMMISSION_MANAGE`
  and `COMMISSION_PAY` together, so one person states the debt, raises it and
  pays it, their own included (D-TER-4). The payout row keeps no approver or
  payer; the three audit rows' `actor_id` are the only record.
- **Check:** §17.12's query, and the journals:
  ```sql
  select j.reference_number, j.journal_date, j.status, j.reversal_of_id is not null as is_reversal,
         (select string_agg(a.code || ' ' || l.debit_amount || '/' || l.credit_amount, ', '
                            order by l.line_number)
          from fx_<suffix>_t.journal_lines l
          join fx_<suffix>_t.ledger_accounts a on a.id = l.ledger_account_id
          where l.journal_entry_id = j.id) as legs
  from   fx_<suffix>_t.journal_entries j
  where  j.source_module = 'commission' order by j.created_at;
  ```
- **Confirmed:** `COMM-202609-b238684f` 5600 495.60 / 2400 495.60 dated
  2026-09-30, REVERSED, and `COMM-202609-b238684f-REV` its mirror, the same
  date; a PUT of `{"status": "PAID"}` 422; and Bala — given `ACCOUNTANT` beside
  `SALES_EXECUTIVE` — accruing his own payout, adjusting it by +5,000.00 "because",
  approving it at 5,094.40 and paying it, five audit rows with his own id as
  actor.

### 17.14 Pay a payout (TC-INCENT-007, TC-INCENT-008)

`POST /payouts/{id}/pay` with `paid_on` and `money_account_id`;
**`COMMISSION_PAY`**, which `SALES_MANAGER` does not hold.

- APPROVED only — "Only an approved payout can be paid. Approve it first, which
  is what recognises the debt." Posts **`…-PAY`**: Dr `COMMISSION_PAYABLE` / Cr
  **the account named**, dated `paid_on`. Sets `payment_journal_entry_id`,
  `money_account_id`, `paid_on`, status PAID. The expense is not touched again.
  Audit `commission.payout.paid`.
- **Three references, because a journal reference is unique**: the accrual's,
  `-PAY` and `-REV`.
- **The account and the date are taken as sent.** The desktop offers cash and
  bank accounts only; the server checks that the id is a live account of this
  firm (`JournalEntryEngine._load_accounts`) and nothing more, so a payout is
  "paid" out of Trade Receivables, out of Sales, or out of Commission Payable
  itself — Dr 2400 / Cr 2400, which clears the debt on the payout and moves no
  money at all. `paid_on` may fall before `accrued_on`, leaving 2400 in debit
  between the two (D-TER-5).
- **A PAID payout is final**: no cancel, no reversal route, no edit.
- **Confirmed:** `COMM-202609-9b8f08c7-PAY` dated 2026-09-01 with legs
  `2400 5094.40/0.00, 2400 0.00/5094.40`, against an accrual dated 2026-09-30;
  in `fx_t0916zqbt_t` (TC-INCENT-007's own run) the payment is dated 2026-09-16
  and the debt it clears 2026-09-30. WHOLE01, MEDI01 and FOOD01 pay from 1000
  Cash on the accrual's own date. TC-INCENT-008 records the three 403s a
  `SALES_EXECUTIVE` gets; they were not driven again here.

### 17.15 Sales targets — Sales → Targets (TC-INCENT-006)

`/api/v1/sales-targets`; reads `SALES_TARGET_VIEW`, writes
`SALES_TARGET_MANAGE`. The service commits.

- **Create** inserts one `sales_targets` row: a person, a node, both or
  neither; the period's own dates; `period_type` a label; `basis` INVOICED or
  COLLECTED; `status` ACTIVE or INACTIVE. It was **free text** and only
  `ACTIVE` is ever reported, so `PAUSED` was accepted, stored, and vanished
  from the one screen a target exists for; it is an enum since `20260924_0157`
  (D-TER-16). The desktop's editor sends `ACTIVE` and nothing else.
- **The edit is a whole replace** with the create schema: every column is
  assigned from the body, so a PUT that leaves out `salesman_id` turns a
  person's target into **the firm's**, one that leaves out `basis` makes it
  INVOICED, and `notes` clears (D-TER-8). `If-Match` is honoured.
- **"One target per scope and period" compares `period_start` alone.** A
  quarterly target from the 1st is refused because the monthly one starts that
  day, while a second target from the 2nd — overlapping the first entirely — is
  accepted (D-TER-2).
- **Delete** fills `is_deleted`, `deleted_at` and `deleted_by` since #615; it
  used to set the first alone, so the row said it had gone and neither when
  nor at whose hand (D-TER-16).
- **Who and where the target is for is checked since #614.** `salesman_id` must
  be an active member, read through the platform store, and `territory_id` a
  live node of **this firm** -- `sales_territories` lives in the shared store,
  where a key is satisfied by another firm's node (D-TER-15). Both null is
  still the firm's own number and is checked against nothing. The update runs
  the check on the merged row, as the overlap check does.
- **Audit:** `sales_target.created`, `.updated` and `.deleted`. The first
  carried the start date and the amount and the last the amount alone, so
  neither said whose number it was or over what period; since #615 both carry
  every column the update may touch, rendered the way `.updated` renders them
  (D-TER-16).
- **Check:**
  ```sql
  select g.status, g.salesman_id, t.code as territory, g.period_start, g.period_end,
         g.period_type, g.basis, g.target_amount, g.is_deleted, g.deleted_at, g.version
  from   fx_<suffix>_t.sales_targets g
  left   join fx_<suffix>_t.sales_territories t on t.id = g.territory_id
  order  by g.period_start, g.created_at;
  ```
- **Confirmed:** a PUT of Asha's target naming only its dates and amount
  answered 200 with `salesman_id: null`, the achievement row read "Whole firm"
  at 10,620.00, and her `target_met` went from true to null; the same-day
  quarterly target 409 and the one from 2026-09-02 201; `PAUSED` 201.

### 17.16 Achievement, and what it decides — Targets → Achievement (TC-INCENT-006)

`GET /api/v1/sales-targets/achievement?from_date=&to_date=&salesman_id=`,
`SALES_TARGET_VIEW`. **Writes nothing.**

- Every ACTIVE target whose period **overlaps** the window is reported, each
  measured over **its own** dates and on its own basis: INVOICED sums
  `grand_total` of APPROVED and CLOSED bills dated in the period, COLLECTED the
  same allocation walk as §17.11. Credit notes and returns take nothing off
  either (D-TER-3).
- **A person is matched on `sales_invoices.salesman_id`, a node on
  `sales_invoices.territory_id` exactly.** A document is tagged with the node
  its customer is assigned to — the route — so a target set on a Territory or a
  Region **achieves nothing**, however much its routes sell; the row is also
  labelled "Whole firm", which is what a target with no person is called
  (D-TER-12).
- **The commission bonus reads this, summed.** `_targets_met` adds every
  target's amount and every target's achievement for a person and compares the
  totals. Two targets over the same days therefore count the same sales twice:
  4,720.00 sold against 8,000.00 is missed, and adding a second target of
  1,000.00 from the 2nd makes it 9,440.00 against 9,000.00 — **met**, and the
  2% bonus is paid (D-TER-2). A target naming only a node decides nobody's
  bonus.
- **Confirmed:** Asha 1,000.00 / 5,900.00 met and Bala 100,000.00 / 4,720.00
  missed, as TC-INCENT-006 records; the Region's 5,000.00 target at 0.00 with
  10,620.00 invoiced beneath it; Bala's report row 94.40 with his target at
  8,000.00 and **188.80** once the second target existed.

### 17.17 What these modules do not write, and is often looked for

| You might expect | What actually happens |
| --- | --- |
| A stored call list, visit or check-in | Computed on every read; visit execution is not built (`docs/TERRITORY_FRAMEWORK.md`) |
| A stored commission figure before accrual | The report is recomputed on every read; only `commission_payouts` remembers a number |
| A payout that follows a reversed receipt or a corrected rate | Never: it is a snapshot. Cancel it while it is DRAFT or APPROVED and accrue again |
| A credit note, return or refund taken off commission or a target | Neither reads them (§17.11, §17.16) |
| A margin rule | `measure` is dropped on the way in; only the demo seeder's direct write is MARGIN (§17.10) |
| Who approved and who paid, on the payout | Only on the three audit rows' `actor_id` |
| Who joined or left a round, and in what order | `customers_set` records a count (§17.4) |
| The route profile's old window | Overwritten; `sales_territory.updated` carries the code and path only |
| A document retagged when a shop changes round | Never: the three ids are written once, and a note or invoice inherits them |
| A salesperson taken off their rounds when they leave | Nothing touches the firm store (§17.5) |
| A foreign key from a rule, payout or target to a person | None in any store (§17.0) |
| A journal from a DRAFT or a cancelled-from-DRAFT payout | None: only approval posts |
| Commission net of tax or freight | Measured on `grand_total`; an open question, not a defect (`docs/COMMISSION_FRAMEWORK.md`) |

### 17.18 Checked against live rows, and not

- **Confirmed by driving** (2026-09-19, 20:55–21:05 IST, `commission-firm`
  `t0919tkvs`, schema `fx_t0919tkvs_t`): `measure` dropped on a PUT and a POST;
  an unknown salesman accepted on a rule, a target and a quotation, and refused
  on an order; a salesperson holding `ACCOUNTANT` accruing, adjusting by
  +5,000.00, approving and paying his own payout, from 2400 into 2400, dated 29
  days before the accrual; `status` refused on the payout update; an approved
  payout cancelled and its `-REV` posted; a period accrued before it ended and
  one running 10 September to 15 October; an August advance applied to a
  September bill counted in August; a second, overlapping target turning a
  missed target into a met one and 94.40 into 188.80; a credit note for a whole
  bill changing nothing in the report or the achievement; a territory PUT
  without `route_profile` deleting the profile, and a target PUT without
  `salesman_id` making it the firm's; an order keeping a closed route and
  another round's route as sent, and a blank one leaving the closed route off;
  a shop refused back on to a round it had been primary on; a Region target
  achieving 0.00; a deleted route still called, and renamed while deleted; a
  deleted salesperson derived on to an order whose delivery note was then
  refused. **What the drives left** in `fx_t0919tkvs_t`: payouts
  `COMM-202609-9b8f08c7` (PAID, 5,094.40) and `-b238684f` (CANCELLED) and a
  DRAFT for 2026-09-10 to 2026-10-15; an INACTIVE 9% rule and an ACTIVE 1% rule
  for nobody; six targets beyond the fixture's two; S1 closed at 2026-06-30;
  `T0919TKVS-C1` on S1 instead of N1; deleted node `T0919TKVS-R-X2` with plan
  `T0919TKVS-BP-X`; orders SO-2026-2027-000004 to -000008, QT-2026-2027-000001,
  RC-2026-2027-000004, SI-2026-2027-000004, CN-2026-2027-000001; and Asha's
  account deleted in `platform`.
- **Confirmed from the tables** (read only, 59 schemas plus
  `electrolink_ops`): every audit action these modules have written anywhere,
  and that **every one carries its firm** (the platform-only geography rows
  of §14.12 excepted); no salesman foreign key in any store; the unique
  indexes on all eight tables and which are partial; every live rule COLLECTED
  and PERCENT, and MARGIN only on the seeder's product rule (WHOLE01 one,
  `firm_shared` two, ELEC01 one), which `generate_transaction_history.py`
  corrects in place on the column rather than through the service; fifteen
  posted commission journals in the four stores that held any (WHOLE01,
  `firm_shared`, ELEC01, `fx_t0916zqbt_t`), accruals and `-PAY` entries with
  no `-REV` anywhere before this pass; WHOLE01's three CANCELLED payouts
  carrying no journal, having been cancelled as drafts; no order anywhere tagged
  to a route outside its territory or its window before this pass; no customer
  assigned to another firm's territory in `firm_shared`; no
  `sales_beat_plan_customer_stops` or `address_masters` row in any store; one
  windowed route profile in WHOLE01 and none elsewhere.
- **Not seen in a live row:** an INVOICED or per-unit rule, a cap, or a MIXED
  payout; a margin line with a NULL cost in a report (the unit suite holds it,
  `tests/unit/test_margin_commission.py`); the accrual race
  (`UQ_commission_payouts_period_active` is there; TC-CONC-006 drives the read
  that precedes it); an approval refused for want of an open period; a copy
  refused partway, or one that took a sibling's subtree; an import; a restore;
  a bulk move; a deleted target; the two hierarchy settings switched off; a
  plan with outlet stops of its own; another firm's level or route type on a
  node in `firm_shared`.

---

## 18. Reports, the dashboard, global search and diagnostics — what the firm reads about itself, and what the product reads about its own faults (TC-FIN-005, TC-FIN-006, TC-FIN-011, TC-ISO-003, TC-BUY-007)

Read on 2026-09-23 off the report methods of the twelve document services
(`quotation_service.py`, `sales_order_service.py`, `delivery_note_service.py`,
`sales_invoice_service.py`, `credit_note_service.py`, `sales_return_service.py`,
`proforma_service.py`, `goods_receipt_service.py`, `purchase_invoice_service.py`,
`purchase_return_service.py`, `loyalty_service.py`,
`promotions/services/report_service.py`), `app/api/routers/dashboard.py`,
`app/api/routers/health.py`, `app/search/services/search_service.py` and
`app/diagnostics`, and off the desktop's `reports_workspace.dart`,
`report_catalog.dart`, `dashboard_page.dart`, `global_search.dart` and
`diagnostics_page.dart`. The seven purchase-order reports are §9.13, the
finance statements §12.9, the customer statement and ageing §12.10 and the
commission report §17.11, and none is repeated here.

Checked read-only against WHOLE01, the shared store and `platform`, and driven
against the running backend on TEST01 (fixtures `accountant` `t0923zemi` and
`firm-admin` `t0923gcby`) and, read only, on WHOLE01, MEDI01 and FOOD01 as a
platform administrator. §18.11 says which claims a live row confirmed.

### 18.0 Before you look

- **Nothing in this section writes a row.** Not one report, the dashboard,
  a search or a health probe writes a business row *or an audit row*; the only
  table anything here inserts into is `platform.error_reports` (§18.7). The
  one row a report *can* leave is the `user_preferences.updated` of the last
  screen, on the platform (§3).
- **Every report is the whole history.** Fifty-seven catalogued report routes
  and **not one takes a date range or a page** — `loyalty/reports/expiring`
  takes `within_days` (1–730, default 90) and that is the only parameter
  anywhere. Each answers `ApiResponse[list[...]]` holding every matching row
  the firm has ever written, and the desktop's `DataTable` is not virtualised
  (D-RPT-18).
- **"Today" is `utc_now().date()`** everywhere a report needs one — the
  overdue lists, the proforma's `days_to_expiry`, the loyalty horizon. No
  report reads the server clock.
- **The gate on the screen is not the gate on the route.** The Reports module
  and workspace are offered on `REPORT_VIEW` (`module_catalog.dart`,
  `reports_workspace.dart:57`) — a seeded code that **no backend route
  enforces** (`grep -rn REPORT_VIEW app/` finds only the seed). Each route
  takes its module's own view code: `SALES_VIEW` for quotations, orders, notes,
  invoices and returns; `CREDIT_NOTE_VIEW`; `PROFORMA_VIEW`; `PURCHASE_VIEW`
  for receipts, supplier invoices and purchase returns; `LOYALTY_VIEW`;
  `PROMOTION_VIEW`. `ACCOUNTANT` holds the `report` group and none of the
  operational codes, so it is offered the screen and refused every operational
  entry on it (D-RPT-4).
- **Names.** The credit-note and proforma registers, every `by-*` report and
  the loyalty and promotion reports resolve names in one `IN (...)` read on
  the firm store. **The five other registers carry ids and no name at all**
  (D-RPT-17). The salesperson's name comes from `platform.users` through
  `platform_reader()` — one read for the set in the sales-order reports, and
  **one platform connection per person** in the delivery-note one (D-RPT-19).
  Two reports name the customer by `Customer.name`, the rest by
  `display_name` (D-RPT-19).
- **What a bill still owes is `settlement_allocations` (§9.11, §12.12), and
  four money reports never read it**: sales-invoice overdue and
  customer-outstanding's count, purchase-invoice overdue and vendor
  outstanding (D-RPT-2, D-RPT-3). A DRAFT is counted as given, returned or
  credited by the credit-note, sales-return and delivery `by-*` reports
  (D-RPT-8, D-RPT-9).
- **Where to query.** Every table a report reads is firm-owned and lives in
  the firm's store: TEST01 is `test_fixtures`, WHOLE01 `wholesale_hub`, MEDI01
  and FOOD01 `firm_shared` (filter on `firm_id`), ELEC01 `electrolink_ops`.
  The dashboard, search's `users` / `roles` / `permissions` / `firms`
  definitions and every error report read or write `platform`.

### 18.1 The Reports workspace — Reports → Operational Reports, Financial Reports (TC-FIN-005)

`reports_workspace.dart` is a picker and a grid. The catalogue
(`report_catalog.dart`, 57 entries, `ReportArea.operational` or `.financial`)
is data; choosing an entry calls `ApiClient.reportRows(path)`, a bare `GET` of
the entry's path with the `X-Firm-ID` header and **no query string**, and the
grid derives its columns from the first rows unless the entry names them
(three do, because their endpoints answer whole documents). The header says
`N row(s)`; an empty list reads "Nothing to report"; an `ApiException` — the
403 of D-RPT-4 included — is a banner. There is no filter, no export and no
paging on the screen, and nothing about opening a report is recorded anywhere.
`tests/unit/test_reports_have_a_screen.py` fails the build on a `/reports/`
route with no catalogue entry, and the reverse.

### 18.2 Quotations, orders and delivery notes (scope `SALES_VIEW`)

| Report | Route | Reads | Notes |
| --- | --- | --- | --- |
| Quotation register | `/api/v1/quotations/reports/register` | `sales_quotations`, every status, CANCELLED in; `quotation_date DESC` | `quotation_number, customer_id, quotation_date, valid_until, status, grand_total, converted_sales_order_number`. `customer_name` beside the id, in one read (D-RPT-17); `status` is the stored one, so a SENT quote past `valid_until` still reads SENT -- `is_expired` rides beside it, derived by the rule the document's own response uses (D-RPT-19) |
| Quotation conversion | `/api/v1/quotations/reports/conversion` | `sales_quotations` not CANCELLED, per customer; `customers.display_name` | `quoted_count` / `quoted_value` (every non-cancelled quote, DRAFT in), `converted_*` (CONVERTED), `declined_count` (DECLINED). **Nothing counts a lapsed quote** — a SENT quote past its date is "quoted" and nothing else, although the catalogue promises "how many lapsed" (D-RPT-12). Unordered |
| Sales order register | `/api/v1/sales-orders/reports/register` | `sales_orders`, every status; `order_date DESC, created_at DESC` | `order_number, order_date, customer_id, salesman_id, territory_id, branch_id, warehouse_id, status, grand_total` — each id with its name beside it, one read per table and the salespeople through `platform_reader()` (D-RPT-17) |
| Orders not yet delivered | `/api/v1/sales-orders/reports/pending` | `sales_orders` in **DRAFT or APPROVED** only | `pending_value` is the **whole `grand_total`**. A **PARTIALLY_DELIVERED** order — the one that most literally still owes stock — is left out, and a DRAFT nobody has approved is in; `is_on_hold` is not read (D-RPT-7) |
| Back orders | `/api/v1/sales-orders/reports/back-orders` | `sales_order_lines` joined to their order, **every status** — DELIVERED, CLOSED and CANCELLED in; one `select(SalesOrder)` per line | A line qualifies when `reservable_quantity − available_stock > 0`, and **`available_stock` is the snapshot written when the line was saved**, never refreshed: it says what was short the day the order was typed (D-RPT-8). No product name |
| Orders by customer | `/api/v1/sales-orders/reports/by-customer` | `sales_orders` not CANCELLED (DRAFT in); Σ `grand_total` and a count per customer; `customers.display_name` in one read (D-RPT-19) | sorted by name |
| Orders by salesman | `/api/v1/sales-orders/reports/by-salesman` | the same, every order; names from `platform.users` in one `platform_reader()` read | an order with nobody falls in an **Unassigned** bucket, as the note reports have always done, so the total reconciles against the register (D-RPT-19) |
| Orders by territory | `/api/v1/sales-orders/reports/by-territory` | the same, with an **Unassigned** bucket for an order on no territory; the nodes named in one read (D-RPT-19) | keyed on the **node** (`sales_orders.territory_id` is a node id, §17.0) — right; no roll-up to the parent |
| Delivery note register | `/api/v1/delivery-notes/reports/register` | `delivery_notes`, every status; `delivery_date DESC, created_at DESC` | `delivery_note_number, delivery_date, sales_order_id, sales_order_number` (the stored `sales_order_reference`), `customer_id, branch_id, warehouse_id, status, grand_total`. The customer, branch and warehouse are named, one read each (D-RPT-17) |
| Dispatches not yet completed | `/api/v1/delivery-notes/reports/pending` | `delivery_notes` in DRAFT or APPROVED | answers **whole `DeliveryNoteResponse` documents**, which is why the catalogue names its five columns (D-RPT-16). Unordered |
| Delivery progress by order | `/api/v1/delivery-notes/reports/partial` | **every** `sales_orders` row not CANCELLED (DELIVERED and CLOSED in); per order a `select(SalesOrderLine)`, per line a summed `delivery_note_lines` read | `ordered` = Σ `reservable_quantity` (base units, free goods in); `delivered` = Σ `delivered_quantity` on notes that are **APPROVED**, DISPATCHED, COMPLETED or CLOSED — so an approved note that has not left the warehouse counts as delivered and its order reads COMPLETED, unlike the service's own `_already_delivered_quantity`, which starts at DISPATCHED (D-RPT-9) |
| Deliveries by route / by salesman / by warehouse | `/api/v1/delivery-notes/reports/by-route`, `/by-salesman`, `/by-warehouse` | `delivery_notes` not CANCELLED — **DRAFT and APPROVED in**; keyed on `route_id` (a `territory_route_profiles.id`, named through the node — right per §17.0), `salesman_id` (**one platform connection per person**), `warehouse_id` -- every label in one read per dimension (D-RPT-19) | `dimension_id, dimension_name` (`None` → "Unassigned"), `note_count, delivered_quantity, total_value`; `delivered_quantity` is Σ `delivery_note_lines.delivered_quantity` of every non-cancelled note, one `select(DeliveryNoteLine)` per note — a draft's typed quantity is "delivered" (D-RPT-9) |

`grand_total` on every one of these is **with tax**, and a DRAFT order counts
in every `by-*` total.

### 18.3 Sales invoices, credit notes, sales returns and proformas

Scope `SALES_VIEW` for invoices and returns, `CREDIT_NOTE_VIEW`,
`PROFORMA_VIEW`. `/api/v1/sales-invoices/reports/summary` also exists: it is
the invoice screen's dashboard tile, not a catalogue report.

| Report | Route | Reads | Notes |
| --- | --- | --- | --- |
| Invoices not yet approved | `/api/v1/sales-invoices/reports/pending` | `sales_invoices` in DRAFT | whole `SalesInvoiceResponse` documents (D-RPT-16). Honest: "pending" means unapproved |
| Overdue invoices | `/api/v1/sales-invoices/reports/overdue` | `sales_invoices` with `due_date < today` and status **not CANCELLED and not CLOSED** | whole documents. **Status is the only test of "still owing"**, and a paid invoice stays APPROVED (§9.14's rule holds for sales too), so a **fully-collected invoice past its due date is listed as overdue**, and so is a DRAFT with a due date, which never posted — WHOLE01 lists 23, 5 of them paid in full (D-RPT-3). `due_date` is filled from `customers.payment_terms_days` when the caller sends none |
| Sales invoice register | `/api/v1/sales-invoices/reports/register` | `sales_invoices`, every status; `invoice_date DESC, created_at DESC` | `invoice_number, customer_invoice_number, customer_id, branch_id, invoice_date, due_date, grand_total, status`. `customer_name` and `branch_name` beside the ids (D-RPT-17); nothing about what is paid |
| Customer outstanding | `/api/v1/sales-invoices/reports/customer-outstanding` | `customers` of the firm with `current_outstanding > 0`; `invoice_count` = number of **APPROVED** invoices per customer, paid or not | `outstanding_amount` is **`customers.current_outstanding`**, the running balance `post_receivable_transaction` keeps — the statement's figure (§12.10), which credit notes, returns and opening balances move and allocations do not, so it legitimately differs from a sum over invoices (WHOLE01: 41,134.24 against 78,697.14 owed by invoices alone). `invoice_count` counts settled bills too, so "1 invoice, 1,200.00" may be one paid bill and an opening balance; a customer in advance (negative) is dropped (D-RPT-3) |
| Invoice reconciliation | `/api/v1/sales-invoices/reports/reconciliation` | `sales_invoice_lines` joined to their invoice, **every status** — DRAFT and CANCELLED in | one row **per invoice line**; `delivered_quantity, already_invoiced_quantity, current_invoice_quantity, pending_quantity` are the **snapshot stored on that line when written**, so a source line billed twice appears twice with the older row's `pending` stale, and a cancelled invoice's line still claims its quantity billed — WHOLE01 holds one (D-RPT-13). The product is named (D-RPT-17); the customer is not |
| Credit note register | `/api/v1/credit-notes/reports/register` | `credit_notes`, every status; `customers.display_name` and `sales_invoices.invoice_number` in one read each; `credit_note_date DESC, created_at DESC` | `credit_note_number, credit_note_date, customer_id, customer_name, sales_invoice_id, sales_invoice_number, reason, taxable_amount, tax_amount, total_amount, status` — the one register that names everything |
| Credits by customer / by reason | `/api/v1/credit-notes/reports/by-customer`, `/by-reason` | `_live_notes`: status **≠ CANCELLED** — **DRAFT in**; Σ `taxable_amount`, Σ `tax_amount` per customer (`quantize_ledger`, taxable desc) and Σ `total_amount` per `reason` | a draft credit — not given, posted nothing — is counted as credited (D-RPT-10) |
| Sales return register | `/api/v1/sales-returns/reports/register` | `sales_returns`, every status; `return_date DESC` | `return_number, customer_return_number, customer_id, branch_id, warehouse_id, return_date, grand_total, status`. The customer, branch and warehouse are named, one read each (D-RPT-17) |
| Returns by customer | `/api/v1/sales-returns/reports/by-customer` | `sales_returns` with status not in `_SPENT_STATUSES = (CANCELLED,)` — **DRAFT and APPROVED in**; Σ `grand_total`; `customers.display_name` | only COMPLETED moves stock and posts (§11.16); a draft return is counted as returned value (D-RPT-10) |
| Returns by product | `/api/v1/sales-returns/reports/by-product` | `_report_lines`: live lines of non-cancelled returns; Σ `current_return_quantity`, Σ **`restock_quantity`**, Σ `net_amount` (with tax) per product; `products` in one read | `restock_quantity` is summed off DRAFT lines whose stock has not come back (D-RPT-10) |
| Return reconciliation | `/api/v1/sales-returns/reports/reconciliation` | the same lines with their header; `products.name` in one read | `return_number, return_date, source_document_type/id/number, source_document_line_id/number, product_id, product_name, dispatched_quantity, already_returned_quantity, current_return_quantity, pending_quantity, restock_quantity, reason_code, is_damaged, is_expired` — the three quantities the line's own snapshot, one row per return line, drafts in (D-RPT-10) |
| Proforma register | `/api/v1/proforma-invoices/reports/register` | `proforma_invoices`, every status; `customers.display_name` and `sales_orders.order_number` in one read each; `proforma_date DESC, created_at DESC` | `proforma_number, proforma_date, valid_until, customer_id, customer_name, sales_order_id, sales_order_number, grand_total, status`. A superseded proforma still reads ISSUED — superseding writes `supersedes_id` on the new row and moves nothing on the old |
| Proformas awaiting payment | `/api/v1/proforma-invoices/reports/outstanding` | `proforma_invoices` in **ISSUED** whose id is no row's `supersedes_id`; `proforma_date ASC`; `days_to_expiry = valid_until − today`, negative once lapsed | **nothing outside `app/proforma` ever touches a proforma** (§11.18), so one stays ISSUED after its order is delivered, billed and paid: WHOLE01 lists 18, **16 on delivered or closed orders, 12 of them billed** (D-RPT-11) |

### 18.4 Goods receipts, supplier invoices and purchase returns (scope `PURCHASE_VIEW`)

Vendor, product and customer names come from the firm's own store in one
`IN (...)` read; none of these reads a platform table.

| Report | Route | Reads | Notes |
| --- | --- | --- | --- |
| Receipts awaiting completion | `/api/v1/goods-receipts/reports/pending` | `goods_receipts` in **DRAFT**; then per receipt its live lines, attachments, notes and a duplicate check | whole `GoodsReceiptResponse` documents — four extra queries per receipt, no ordering (D-RPT-16) |
| Receipts completed | `/api/v1/goods-receipts/reports/completed` | `goods_receipts` in **COMPLETED** only; the same per-row reads | **CLOSED receipts are left out**, although closing is the step after completing (`close_receipt`, COMPLETED → CLOSED): the report shrinks as the firm tidies up (D-RPT-15). No live store holds a CLOSED receipt yet |
| Rejected on receipt / Damaged on receipt | `/api/v1/goods-receipts/reports/rejected`, `/damaged` | `goods_receipt_lines` joined to `goods_receipts`, `rejected_quantity > 0` / `damaged_quantity > 0`, both not deleted | **no receipt status filter**: lines of DRAFT and CANCELLED receipts included, so a cancelled receipt's damage is reported as having happened (D-RPT-15). `GoodsReceiptLineResponse` with `product_code`, `product_name` and `warehouse_name` filled for the report (D-RPT-17); still no receipt number or date. No ordering |
| Orders part received | `/api/v1/goods-receipts/reports/partial` | every live `purchase_orders` row of the firm, **any status**; its live lines; per line a `SUM(current_receipt_quantity)` of `goods_receipt_lines` on receipts in **COMPLETED** only; a count of COMPLETED receipts | keeps an order when `0 < received < ordered` summed over the order; `status` is always the literal `PARTIAL`; the vendor, branch and warehouse are named (D-RPT-17). Counts COMPLETED receipts where the order's own derivation (`_received_quantities_for_po`) counts COMPLETED **and CLOSED** — close one receipt and the report says part received while the order reads RECEIVED; a CANCELLED or CLOSED order with a partial receipt is listed (D-RPT-14). One query per order plus one per line |
| Purchase invoice register | `/api/v1/purchase-invoices/reports/register` | `purchase_invoices`, every status; `invoice_date DESC, created_at DESC` | `invoice_number, supplier_invoice_number, vendor_id, branch_id, invoice_date, due_date, grand_total, status`. `vendor_name` and `branch_name` beside the ids (D-RPT-17) |
| Supplier invoices not yet approved | `/api/v1/purchase-invoices/reports/pending` | `purchase_invoices` in **DRAFT**; then per invoice its sources, lines, attachments, notes, accounting events and a duplicate check | whole documents; five extra queries per row; no ordering (D-RPT-16) |
| Overdue purchase invoices | `/api/v1/purchase-invoices/reports/overdue` | `purchase_invoices` with `due_date IS NOT NULL AND due_date < today`, status **not in (CANCELLED, CLOSED)** | so **DRAFT and APPROVED** are in. `due_date` is a request field, never derived from `payment_terms` — WHOLE01's 30 bills carry none, so none is ever overdue there. **Never reads `settlement_allocations`**: a bill paid in full stays overdue until somebody closes it (D-RPT-2). Whole documents |
| Vendor outstanding | `/api/v1/purchase-invoices/reports/outstanding` | `purchase_invoices` not deleted, status **≠ CANCELLED**; `vendors.display_name` | `SUM(grand_total)` and a count per vendor. **Nothing is subtracted**: not payments, not returns raised on the bill's lines, not CLOSED; DRAFT bills count as owed. `SettlementService.outstanding_invoices` already derives the real figure — total less POSTED allocations less returns, over `SETTLEABLE_INVOICE_STATES` — and this report ignores it: WHOLE01 reports 435,349.20 where 421,189.20 is owed (D-RPT-2) |
| Purchase invoice reconciliation | `/api/v1/purchase-invoices/reports/reconciliation` | `purchase_invoice_lines` joined to live `purchase_invoices`, **every status** | per line `received_quantity, already_invoiced_quantity, current_invoice_quantity` as **snapshotted at create**, `pending` floored at 0. A CANCELLED invoice's line still reports its quantity as billed (D-RPT-13). The product is named (D-RPT-17); the vendor and the invoice number are not — only the source document's type, id, number and line |
| Purchase return register | `/api/v1/purchase-returns/reports/register` | `purchase_returns`, every status; `return_date DESC, created_at DESC` | `return_number, supplier_return_number, vendor_id, branch_id, warehouse_id, return_date, grand_total, status`. The vendor, branch and warehouse are named, one read each (D-RPT-17) |
| Returns by vendor | `/api/v1/purchase-returns/reports/by-vendor` | `purchase_returns` not CANCELLED (DRAFT in); `vendors.display_name` | `SUM(grand_total)` (tax in) and count per vendor |
| Purchase returns by product | `/api/v1/purchase-returns/reports/by-product` | live `purchase_return_lines` of returns not CANCELLED; `products.code`, `.name` | `SUM(current_return_quantity)`, `SUM(net_amount)` (tax in) and a line count per product |
| Purchase return reconciliation / Expired stock returned | `/api/v1/purchase-returns/reports/reconciliation`, `/expired` | the same lines with their header (`_report_lines`, CANCELLED out, DRAFT in); `products.name`; `/expired` keeps `is_expired` lines only | per line the three snapshotted quantities, `pending` floored at 0, `reason_code, is_damaged, is_expired`, source type / id / number / line. `/damaged` (§9.13) is the `is_damaged` twin |

### 18.5 Loyalty and promotions (scope `LOYALTY_VIEW`, `PROMOTION_VIEW`)

The loyalty balance is a **sum over `loyalty_entries`**, never a column, and
what it is worth is walked batch by batch (`_allocate`, `_held_worth`) — the
allocation the expiry sweep itself uses (§11.19). All three promotion reports
key an offer by **`version_group_id`** and read every version, so a claim
naming a superseded row still counts against its campaign; a claim counts only
when `status == CLAIMED`, written at approval — PENDING while the document is a
draft, REVERSED on cancellation (§11.5).

| Report | Route | Reads | Notes |
| --- | --- | --- | --- |
| Loyalty balances | `/api/v1/loyalty/reports/balances` | every live `loyalty_entries` row of the firm in `earned_on, id` order; `loyalty_settings.amount_per_point`; `customers.display_name` | `SUM(points)` per customer, only customers **above zero**; `amount` = what the unspent batches are worth at each batch's own rate. Largest holding first |
| Loyalty movements | `/api/v1/loyalty/reports/movements` | every live entry, `earned_on DESC, id DESC`; `customers.display_name`; `sales_invoices.invoice_number` where named | one row per entry: `kind`, signed `points`, `amount`, `earned_on`, `expires_on`, `sales_invoice_number`, `remarks` |
| Points about to lapse | `/api/v1/loyalty/reports/expiring?within_days=90` | customers with an EARNED entry whose `expires_on <= today + within_days`; then `unspent_batches` per customer, one ledger read each | one row per batch still holding points: `points` = what is **left** of the batch, `amount` at its rate, `days_remaining`; sorted by `expires_on`, then name. A batch already past its date and not yet swept is **kept**, with `awaiting_sweep` true and a negative `days_remaining`: its points are still spendable and still in the balance, so the row is the notice that the sweep has not run (D-RPT-19) |
| Promotion performance | `/api/v1/promotions/reports/performance` | live `promotions` (every version); live `promotion_redemptions` | one row per group, the **latest version's** code / name / status / `max_redemptions`; `claimed_count, pending_count, reversed_count`, distinct `customer_count`, `benefit_amount` (CLAIMED only), `remaining_redemptions` = cap − claimed floored at 0, `None` when uncapped. Offers with no claim still appear. Costliest first |
| Promotion claims | `/api/v1/promotions/reports/redemptions` | live `promotion_redemptions`, `redeemed_on DESC, created_at DESC`; `promotions` for code and name; `promotion_coupons.code`; `customers.display_name` | every row **including PENDING and REVERSED**, labelled by `status`; `document_type, document_id, document_number, benefit_amount` |
| Coupon performance | `/api/v1/promotions/reports/coupons` | live `promotion_coupons`; `promotions`; live redemptions with a `coupon_id` and `status == CLAIMED` | per coupon `code, promotion_code, status, claimed_count, customer_count, benefit_amount, max_redemptions, remaining_redemptions`. Costliest first |

### 18.6 The dashboard — the first screen a platform administrator sees

`GET /api/v1/dashboard` (`app/api/routers/dashboard.py`) is a **platform
path**: `require_platform_admin()` by designation, always the platform session.
It answers four counts of live (`is_deleted = false`) rows — `firms` (inactive
firms included), `users`, `roles`, `permissions` — each `null` when the caller
lacks `FIRM_VIEW` / `USER_VIEW` / `ROLE_VIEW` / `PERMISSION_VIEW` in the token's
`permissions` claim. Nothing else: `DashboardSummary` forbids extra fields.
On 2026-09-23 the platform held 46 firms, 161 users, 20 roles and 189
permissions. The desktop page (`dashboard_page.dart`) shows the four cards,
each hidden without its code, and **two panels the server has never filled** —
"Recent Firms" reads `recent_firms` and "System Activity" `system_activity`,
neither of which any response carries, so both have always said "No recent …
activity available" (D-RPT-20). The module is offered on `requiresPlatformAdmin`,
not on the four codes; an `ACCOUNTANT` in a firm gets 403 from the route and
never sees the tab.

### 18.7 Global search — Ctrl+K (TC-FIN-006)

`GET /api/v1/search?query=…` takes `category` (`all`, `masters`, `inventory`,
`tax`, `organization`), `page`, `page_size` (1–100), `entity_types` (a
comma-separated subset) and `include_deleted`; `scope` is `OptionalFirmScope`,
so **a firm named in `X-Firm-ID` is checked for active membership before any
query runs**, and no header means the platform session. `query` may be empty,
which lists everything.

- **Forty-one definitions over thirty-eight models** (`_DEFINITIONS`), each
  naming its entity type, module and tab (the desktop's, guarded by
  `test_search_navigation_targets`), the permission it takes, its firm column,
  the columns matched (`ILIKE '%query%'` on each, cast to text) and the
  status column. `users`, `roles`, `permissions` and `firms` are flagged
  `platform_store` and read through one `platform_reader()` session opened
  once per search **only when the request is firm-scoped** — on the platform
  session the tables are in hand already; `test_search_reads_platform_tables_on_the_platform_store`
  compares the flag with `_PLATFORM_TABLES`.
- **The firm filter is the firm column.** A definition with one is narrowed to
  `firm_id = <scope> OR firm_id IS NULL` (a NULL firm is a platform row —
  roles are the case that matters), and to `IS NULL` alone with no firm. A
  definition with **none is not narrowed at all**, which is right for `uom`,
  `packaging`, `permissions` and the five geography ladders, which are
  firm-wide or platform-wide by design — and **wrong for two**: `users` has
  no firm column, so a firm caller holding `USER_VIEW` (every `FIRM_ADMIN`)
  reads **every user on the platform by name and email**, where
  `GET /api/v1/users` narrows them to their own members (§15.3, D-IDN-7) —
  TEST01's admin lists 37 people and searches 100 (D-RPT-1); and
  `storage_areas` is keyed by warehouse, not firm, so in a SHARED store a
  MEDI01 search returns FOOD01's shelves and the reverse — six hits for three
  (D-RPT-1). `firms` is safe by accident: `FIRM_VIEW` is a platform code no
  firm role holds.
- **`territories` and `routes` are two definitions over `SalesTerritoryNode`
  with the same filter**, so every node is listed twice, once under each label
  — WHOLE01's six nodes are twelve hits (D-RPT-6).
- **Pagination is over an in-memory list.** Each definition contributes at
  most `max(page_size, 20)` rows, newest `updated_at` first then `id DESC` (a
  tie-break, since every row one request wrote shares a timestamp); the hits
  are concatenated in definition order and sliced. `total` is therefore the
  size of that capped list, never the count of matches (D-RPT-20). `inventory`
  is matched on `storage_locator` alone and `opening_stock` on
  `reference_number`, so stock cannot be found by product.
- **The desktop dialog offers fourteen category chips and the server accepts
  five.** `_searchCategoryWire` sends `modules`, `customers`, `vendors`,
  `documents`, `transactions` and `reports` as typed, and the route's
  `SearchCategory` literal answers **422** "Input should be 'all', 'masters',
  'inventory', 'tax' or 'organization'" (D-RPT-5); `products` maps to
  `masters` and `warehouses` / `branches` to `organization`, which are wider
  than the chip promises.
- A search writes nothing; a result opened lands on the module and tab the
  definition names, and only the last-screen preference can follow (§3).

### 18.8 Diagnostics — crash and error reports (TC-FIN-011)

`platform.error_reports` is **not** a `BaseEntity` and is **not** per store:
no soft delete, no version, no actor columns, and every firm's reports in one
platform table, because a fault split across stores cannot be counted.
`/api/v1/diagnostics` is a platform path, so `X-Firm-ID` never changes the
session; the header's value is recorded as data.

| Action | Route / caller | Writes |
| --- | --- | --- |
| A desktop flushes its queue | `POST /api/v1/diagnostics/client-errors` — any **authenticated** caller, a batch of 1–50 | one row per report: `source = 'CLIENT'`, the client's own `fingerprint`, `error_type`, `message` (≤ 8,000), `stack_trace` (≤ 20,000), `app_version`, `build_number`, `platform_info`, `context_label`, `request_id`, `breadcrumbs` (≤ 300 lines of ≤ 500), `occurred_at`, `received_at = utc_now()`; **`firm_id` and `user_id` are taken from the caller**, never from the payload. One commit per report. No audit row |
| The server fails a request | `app/core/exceptions/handlers.py` → `record_server_error` | `source = 'SERVER'`, `fingerprint` = SHA-256 of the error type and the **last five application frames** (file and function, no line numbers), `error_type`, `message`, `stack_trace`, `request_id`, `context_label` = method and path; **no `firm_id` or `user_id`**. Wrapped so that its own failure is swallowed — a diagnostics write must never replace the 500 it is recording |
| Settings → Diagnostics | `GET /api/v1/diagnostics/errors` (`DIAGNOSTICS_VIEW`; `page`, `page_size ≤ 100`, `search` on message or type, `source`) | reads only: groups by `fingerprint`, newest `last_seen` first, `occurrences`, `first_seen`, up to ten distinct `app_versions` (one extra query per group) |
| Open a group | `GET /api/v1/diagnostics/errors/{fingerprint}` | reads only: up to 50 occurrences, newest first |
| Retention | `purge_retention.py` / the `retention` compose profile → `purge_before` | **physically deletes** rows older than the cutoff — the only delete in this section |

`DIAGNOSTICS_VIEW` is held by `PLATFORM_ADMIN`, `SUPPORT_ADMIN` and
`SYSTEM_AUDITOR` and deliberately **not** by `FIRM_ADMIN`. The desktop queues
`UnexpectedTermination` (the previous session ended without a clean exit, with
the last 100 log lines as breadcrumbs and no `occurred_at`) and each captured
error (with `occurred_at` in UTC) to disk, and sends the queue after the next
sign-in. Query the table:

```sql
select source, error_type, count(*), max(received_at),
       count(request_id) as with_request, count(stack_trace) as with_stack,
       count(firm_id) as with_firm, count(user_id) as with_user
from   platform.error_reports
group  by source, error_type
order  by 3 desc;
```

### 18.9 Health

`GET /health` (no authentication) answers `status`, `environment` and the
running build's `version` — the honest answer to "what is installed here",
since the client's own version is a JSON file beside the exe. `GET
/health/database` runs `SELECT 1` on the platform session and answers 503
"Database unavailable" if it fails. Neither writes anything.

### 18.10 What these do not write, and is often looked for

| You might expect | What actually happens |
| --- | --- |
| A row saying who ran which report, when | None — not an audit row, not a preference. The screen is a `GET` |
| A stored report, snapshot or export | None; every report is recomputed on the read and nothing can be exported |
| A report bounded to a period | None takes a date; the whole history every time (D-RPT-18) |
| An overdue or outstanding figure that a receipt or payment moves | Never on the invoice reports: they read `status` and `due_date`, or the customer's running balance; allocations are §9.11 and §12.12 (D-RPT-2, D-RPT-3) |
| A search that remembers what was typed | Recent and saved searches are the desktop's local preference file, not the server |
| An audit row for a crash report | None; `error_reports` is telemetry and carries its own actor columns |
| A firm-side copy of an error report | None; every report is in `platform` whatever store the firm lives in |
| A server fault carrying its firm or user | Never: only client reports carry `firm_id` and `user_id` |
| The dashboard's recent firms and activity | Never sent; the two panels have been empty since they were built (D-RPT-20) |
| `REPORT_VIEW` refusing a route | Nothing enforces it; it decides only whether the screen is offered (D-RPT-4) |

### 18.11 Checked against live rows, and not

- **Confirmed by driving** (2026-09-23, 15:55–17:10 IST, TEST01, fixtures
  `accountant` `t0923zemi`, `firm-admin` `t0923gcby`, `po-invoiced`
  `t0923vm0u`, `po-received` `t09233p7o`, `po-approved` `t092343ic` and
  `invoiced` `t092359jg`; WHOLE01, MEDI01 and FOOD01 read as `master.ops`):
  the accountant refused (403) on the sales order, sales invoice, purchase
  invoice, loyalty and credit-note reports and the dashboard, holding
  `REPORT_VIEW`; `category=customers` answering 422 naming the five values;
  TEST01's firm admin listing 37 users through `/api/v1/users` and 100 through
  `/api/v1/search?entity_types=users`, the WHOLE01 administrator among them by
  name, whom the users list does not know; WHOLE01's six territory nodes as
  twelve hits; MEDI01 and FOOD01 each searching six storage areas, three of
  them the other firm's (Cold Chain Distribution Center against Temperature
  Controlled Grocery Warehouse); PI-2026-2027-000013 (708.00) paid in full by
  PY-2026-2027-000003 and Vendor outstanding still 708.00, 1 invoice; a DRAFT
  bill due yesterday in the overdue list, then approved, cancelled, and still
  claiming its 4 billed with 0 pending in the reconciliation; GRN-…-000033
  closed, "Receipts completed" falling from 2 to 1 and "Orders part received"
  listing the order as 6 of 10 while the order read RECEIVED; GRN-…-000035
  with 1 damaged and 1 rejected in both reports while COMPLETED and after
  CANCEL; SI-2026-2027-000014 due 2026-09-22, approved, collected in full by
  RC-2026-2027-000004, still overdue, the customer's row saying 2 invoices,
  590.00; CN-2026-2027-000001 DRAFT credited 118.00 in both credit-note
  reports; SR-2026-2027-000001 DRAFT returning and restocking 2 in by-product;
  PF-2026-2027-000001 issued on a DELIVERED, billed, collected order and
  "awaiting payment"; SO-2026-2027-000016 for 45 against 40 on hand 5 short
  as a DRAFT and still after cancellation; DN-…-000010 for 4 raising the
  warehouse's delivered quantity while DRAFT, and reading 4 delivered, 6
  pending once approved and not dispatched; SO-2026-2027-000017
  PARTIALLY_DELIVERED and absent from "Orders not yet delivered"; the backend
  answering `/health` with `1.0.0`, `development`. **What the drives left** in
  `test_fixtures`: PY-2026-2027-000003; PI-2026-2027-000014 CANCELLED;
  GRN-…-000033 CLOSED; GRN-…-000035 CANCELLED; SI-2026-2027-000014 APPROVED
  and settled by RC-2026-2027-000004; CN-2026-2027-000001 and
  SR-2026-2027-000001 DRAFT; PF-2026-2027-000001 ISSUED; SO-2026-2027-000016
  CANCELLED; SO-2026-2027-000017 PARTIALLY_DELIVERED with DN-…-000010
  DISPATCHED. Nothing was written to a demo firm.
- **Confirmed from the tables** (read only, WHOLE01, `firm_shared`,
  `platform`): 23 sales invoices in WHOLE01's overdue list of which 5 are
  settled in full by POSTED allocations and none is a draft; vendor
  outstanding 435,349.20 against 421,189.20 owed once allocations are taken
  off; WHOLE01's 30 purchase invoices carrying no `due_date` and no CLOSED
  purchase invoice or goods receipt in any store before this pass;
  `customers.current_outstanding` summing to 41,134.24 against 78,697.14 owed
  by APPROVED invoices; five back-order rows of which one CLOSED, one
  CANCELLED, one DELIVERED and two DRAFT; one cancelled invoice's line in the
  reconciliation; 18 ISSUED proformas, 16 on delivered or closed orders, 12 of
  those billed; every WHOLE01 delivery note DISPATCHED, every credit note
  APPROVED, every sales return COMPLETED or CANCELLED — so D-RPT-9 and 10 have
  not yet bitten a demo store; no SENT quotation past its date (the write
  refuses one); 10 EARNED loyalty batches past `expires_on` and unswept; 62
  CLAIMED and 2 REVERSED redemptions; 294 error reports in 3 groups — 263
  CLIENT `UnexpectedTermination` (186 with a firm, all with a user, none with
  `occurred_at`) and 31 SERVER `ValidationError` (all with a stack, 3 with a
  request id, none with a firm), the largest server group still spanning four
  `context_label`s because its rows were fingerprinted before the frame rule
  changed; the dashboard's four counts.
- **Not seen in a live row:** a CLOSED supplier invoice; an expired SENT
  quotation (D-RPT-12 is read off the code alone); a search from a firm on
  another server; an error report purged by retention; a client report
  carrying a `request_id`; the `-REV` of anything, since nothing here posts.
