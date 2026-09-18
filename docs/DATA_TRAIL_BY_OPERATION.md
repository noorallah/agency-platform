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
left behind (§10.12). Selling, finance, loyalty and TCS follow.

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

- User, role, template and firm administration writes to **`platform.audit_logs`**, carrying `firm_id` where the action was about a firm.
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
- **Inserts:** a new `users` row built from scratch (`force_password_change = true` always); `user_firms` copied from the source; `user_roles` copied within the caller's reach.
- **Not copied, deliberately:** mobile, employee code, joining date, photo, password, `password_history`, `login_history`, the source's audit rows, and never the `platform_admins` row.
- **Audit:** `user.cloned` with `source_user_id`, plus the `user.created` / `user.firms_set` / `user.roles_set` rows the build makes.

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
- **Observation, checked against the database on 2026-09-15, not yet acted on:** `user_templates` / `user_template_roles` are absent from `_PLATFORM_TABLES` in `app/core/tenancy/lifecycle.py`, so **provisioning does not prune them** from a store it builds — `SNTEST01`, provisioned through the app in section 27, carries an empty `user_templates`; `wholesale_hub`, built by the seeder, does not. Nothing reads the copy. If you see the table in a firm schema, it is empty and not the real one; `platform.user_templates` is.

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
- **Audit:** no `*.assigned` action appears in the code's action list for this write — verify on screen rather than in `audit_logs`. If you find a row, tell me and I will correct this line.
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
| Physical deletion anywhere | Never for a document, a master or a person; `is_deleted = true`. **The exception is a purchase document's child rows** — attachments, notes, delivery schedules, dropped lines, and every child of a draft invoice or return — which are deleted and re-inserted on save (§9.14) |
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
  | `SALES_RETURN` | `SALES_RETURN` | the SR | Selling |
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
  | `physical_count_lines` | `transaction_id` (no FK); `batch_id` (no FK) | the `ADJUSTMENT` it posted; `batches` |
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
  (`batch_id`), in the order the rows were created; `expected_quantity` = what
  the warehouse held **at that moment**, `counted_quantity` null. The **first
  count in a firm** also inserts the `PHYSICAL_COUNT` document type, its three
  states and its numbering rule (audits `document_type.created`,
  `document_state.created` ×3, `document_numbering_rule.created` — seen in the
  same request on TEST01). **Audit:** `inventory.physical_count.opened`
  (`after_data`: `count_number`, `line_count`).
- **Save progress** — `PUT /counts/{id}`. **Updates** `physical_count_lines.counted_quantity`
  and `remarks` on the lines named (matched on product and batch; unnamed lines
  are left alone), `version` +1 on each; `physical_counts.remarks`, `version`.
  **No audit row** (D-STK-6). Refused once the sheet is not DRAFT ("PC-… is
  posted, so it cannot be changed.").
- **Post count** — `POST /counts/{id}/post`. For each line whose
  `counted_quantity` is **not null**: `variance_quantity` = counted − **what the
  warehouse holds now** (re-read, not `expected_quantity`, so a dispatch made
  while you counted is not undone); when the variance is not zero, one
  `ADJUSTMENT` movement (`reference_number` = **the count number**,
  `reference_type` `PHYSICAL_COUNT`, `quantity` 1, `current_quantity_delta` −1,
  `transaction_date` = the count date, `remarks` "Physical count PC-…: counted
  49.0000 against 50.0000" — the decimals as stored), its ledger row at the
  average (60 / 60), and a journal (`source_module` `inventory`, `source_id` =
  the movement, `reference_number` = the count number, `description` "Stock
  adjustment PC-…") of **Dr 5500 Inventory Adjustment / Cr 1200 Inventory**
  60.00 — the other way round when the count found more; the line's
  `transaction_id` set. Then `physical_counts.status` POSTED, `posted_at`,
  `posted_by`. **Lines nobody counted are skipped**: `variance_quantity` stays
  null and nothing moves. **Audit:** per adjusted line
  `inventory.transaction.created`, `finance.journal_entry.created`,
  `finance.journal_entry.posted`; then `inventory.physical_count.posted`
  (`before_data` status DRAFT; `after_data` status POSTED, `adjusted_lines`).
- **Cancel** — status CANCELLED, audit `inventory.physical_count.cancelled`.
  Only a DRAFT can be posted or cancelled; a posted sheet cannot be reopened.
- **Three things to know before you rely on it** (all listed in the PR):
  the adjustment is posted **without the line's batch** — a count line for a
  batch row measures its variance against that batch and moves the product's
  *untracked* row instead, creating one if there is none (D-STK-1; TEST01's
  Wholesale profile has no batches, so the case will not meet it); **each
  adjusted line is committed on its own** before the sheet's status is written
  (D-STK-3); and a sheet with **nothing counted posts** with `adjusted_lines`
  0 — WHOLE01's `PC-2026-2027-000005` is one (D-STK-5).
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
  left join test_fixtures.journal_entries je       on je.source_id = t.id
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
