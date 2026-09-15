# Independent test cases

Pick any case, run it on its own, at any time, in any order. That is the
whole promise, and it is what `docs/MANUAL_UI_TEST_PLAN.md` could not make: its
rows were a chain. 20.1b needed the two-firm user 20.6 creates, 22.1 needed a
cashier nobody had made, 25.10 deletes the role 25.2 makes so 25.9 can never be
run twice, and 24.12 named an account whose password had changed. Picking a row
out of order met a failure that belonged to the plan, not to the product.

**Converted so far:** plan sections 25 (the pilot), 26 and 26a — see the
table of contents below. Other sections move here one at a time; until then
they stay in the plan.

---

## How a case works

### 1. Run its fixture

Every case names a **fixture**. From `backend`, with the backend running:

```powershell
.\.venv\Scripts\python.exe scripts\test_fixture.py role-holder
```

It builds exactly what the case needs **through the real API** — the same
rules you meet on screen apply to the setup — and prints what to use:

```
Fixture 'role-holder' ready
  Firm admin  : t0916xk2q.admin@fixtures.local / Fixture@2026pw
  Custom role : t0916xk2q-night-desk  (Night Desk t0916xk2q)
  It carries  : SALES_VIEW, CUSTOMER_VIEW, RECEIPT_VIEW, RECEIPT_CREATE
  Role holder : t0916xk2q.holder@fixtures.local / Fixture@2026pw
  Tables      : TEST01 in schema test_fixtures; identity rows in platform
  Suffix      : t0916xk2q  (everything this run made has it)
```

`scripts\test_fixture.py list` shows every fixture and the cases that use it.

### 2. Everything happens in TEST01 and TEST02

Fixtures work in two firms of their own, each in a schema of its own:

| Firm | Schema | For |
| --- | --- | --- |
| **TEST01** | `test_fixtures` | almost every case |
| **TEST02** | `test_fixtures_2` | cases needing somebody in two firms, or two firms kept apart |

The demo firms are never touched, and a table check against those schemas
shows only test data. The first fixture run builds both — create, provision,
open the books, GST template, head office, the Wholesale profile — through the
same endpoints plan section 27 tests; every later run finds them and moves on.
`scripts	est_fixture.py baseline` does only that.

**One setup step is not an API call, on purpose.** Nothing in the API grants
the platform-administrator designation — a `platform_admins` row is
deliberately unreachable from anything a role can do, which is what closed the
2026-09-05 escalation. The fixtures that need a platform administrator write
that one row directly, as the seeder does, and write no audit row for it.

### 3. Nothing is shared between runs

Each run makes **its own** users and roles under a fresh **suffix**
(`t` + month-day + four characters). A case that deletes a role, or signs
somebody out, only ever touches its own run's data — so running it breaks no
other case, and running it twice needs nothing but a second fixture.

**The one consequence to keep in mind:** TEST01 accumulates earlier runs' data.
A list will show other runs' roles and users beside yours. Cases therefore
**never count everything on a screen** — they count what the case itself is
about (e.g. *System* roles), and name your rows by their suffix.

### 4. What every case carries

| Part | What it holds |
| --- | --- |
| **Covers** | the old plan row(s) it replaces |
| **Fixture** | the command to run first |
| **Steps** | click by click, with the account to use |
| **Expect** | what passes, and what failure looks like |
| **Data** | table checks — see `docs/DATA_TRAIL_BY_OPERATION.md` for how to look |
| **Leaves** | what it writes that stays behind (always suffixed, never read by another case) |

Every expectation below was **driven against the running backend** before it
was written, and the sidebar lists were taken from the desktop's own
`ModuleVisibility` logic rather than inferred from permission codes.

### 5. Accounts

Fixture accounts sign in with **`Fixture@2026pw`** and are not asked to change
it. The script itself signs in as `master.ops@agency.local`; if that account's
password has changed, set `TEST_FIXTURE_ADMIN_EMAIL` and
`TEST_FIXTURE_ADMIN_PASSWORD`. It **stops on the first refused sign-in** rather
than retrying — repeated guesses lock an account.

---

## Roles — a firm's own roles and templates

A permission is a capability, a **role** names a set of permissions, a
**template** names a set of roles — and a firm administrator may write their
own roles and templates without anybody writing code.

### TC-ROLE-001 — A firm admin sees the firm's roles and none of the platform's

- **Covers:** plan 25.1
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**. Select **TEST01** in the firm switcher if it is not already selected.
  2. Sidebar → **Administration** → **Roles & Permissions** → **Roles** tab.
- **Expect**
  - **Twelve rows subtitled *System role*:** `ACCOUNTANT`, `BILLING_EXECUTIVE`, `CASHIER`, `CUSTOMER_SUPPORT`, `FIRM_ADMIN`, `FIRM_MANAGER`, `INVENTORY_MANAGER`, `PURCHASE_EXECUTIVE`, `PURCHASE_MANAGER`, `SALES_EXECUTIVE`, `SALES_MANAGER`, `VIEWER`.
  - **None of the four platform roles:** `PLATFORM_ADMIN`, `SUPPORT_ADMIN`, `LICENSE_ADMIN`, `SYSTEM_AUDITOR`.
  - Rows subtitled *Custom role* may also appear — earlier fixture runs made them. **Do not count those.**
- **Data** — the same answer from the table:
  ```sql
  select code, is_system, firm_id from platform.roles
  where  is_deleted = false and (firm_id is null or firm_id = (select id from platform.firms where code = 'TEST01'))
  order  by is_system desc, code;
  ```
  The twelve have `is_system = true` and `firm_id` null; the four platform roles are in the table too, and are filtered out of a firm caller's list by the service rather than absent.
- **Leaves:** a firm admin user.

### TC-ROLE-002 — Creating a custom role; the platform's codes are never offered

- **Covers:** plan 25.2, 25.3, 25.4
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**, TEST01 selected.
  2. Administration → Roles & Permissions → Roles → **New**.
  3. **Role code:** `<suffix>-my-role` (your fixture's suffix — codes must be unique in the firm). **Name:** anything.
  4. Scroll to the **Permissions** section **on the same form** — it is not a separate screen.
  5. Search the picker for `FIRM_CREATE`, then `PLATFORM_SETTINGS`, `VOID_INVOICE`, `AUDIT_LOG_VIEW`.
  6. Tick `SALES_VIEW` and `CUSTOMER_VIEW`. **Save.**
- **Expect**
  - Step 5: **none of those four codes is in the list.** The picker offers **167** codes; the 22 platform codes are filtered out of a firm caller's read, not merely refused on save.
  - Step 6: the role is created, subtitled **Custom role**, and offers **Edit** (the System roles do not).
- **Data**
  ```sql
  select r.code, r.firm_id, p.code as permission
  from   platform.roles r
  join   platform.role_permissions rp on rp.role_id = r.id and rp.is_deleted = false
  join   platform.permissions p on p.id = rp.permission_id
  where  r.code = '<suffix>-my-role';
  ```
  Two rows; `firm_id` is TEST01's. Audit: `role.created` then `role.permissions_set` in `platform.audit_logs`.
- **Leaves:** a custom role.

### TC-ROLE-003 — No role may be named `platform_admin`

- **Covers:** plan 25.5
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**, TEST01 selected.
  2. Roles → **New** → **Role code** `platform_admin`, any name → **Save**.
- **Expect:** refused on the form — **"'platform_admin' is reserved. Choose a different role code."** Nothing is created. The code pattern `^[a-z0-9._-]+$` *permits* that spelling, so the refusal is the service's. Before 2026-09-05 this went through, and a firm administrator who assigned it to themselves signed in as a platform administrator.
- **Also try** `firm_admin`, `cashier` or `system_auditor` — the same named refusal: the designation and all sixteen seeded codes are reserved. **Type them in lower case.** `FIRM_ADMIN` or `Cashier` is refused *earlier*, by the code pattern, with a generic "The request validation failed" — a different refusal for a different reason, and not what this case is checking. (The service's check is case-insensitive as defence in depth, for a role row written by some other route; through this form the pattern means only lower case can reach it.) *(Corrected 2026-09-16 after driving it: the first version of this case said `FIRM_ADMIN` gave the same refusal.)*
- **Data:** `select count(*) from platform.roles where lower(code) = 'platform_admin';` → **0**.
- **Leaves:** a firm admin user.

### TC-ROLE-004 — A firm admin *holds* `AUDIT_LOG_VIEW` and cannot *grant* it

- **Covers:** plan 25.4a
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**, TEST01 selected.
  2. Sidebar → **Settings** → **Audit Logs**.
  3. Administration → Roles & Permissions → Roles → **New** → Permissions → search `AUDIT_LOG_VIEW`. Cancel.
- **Expect**
  - Step 2: **opens**, on TEST01's trail.
  - Step 3: **not offered**.
  - That is not a contradiction. `PLATFORM_PERMISSION_CODES` answers "what may a firm administrator not *grant*", a different question from what they may hold. `AUDIT_LOG_VIEW` was granted to `FIRM_ADMIN` directly on 2026-09-06. Confusing the two sets is how a permission's reach gets misjudged.
- **Leaves:** a firm admin user.

### TC-ROLE-005 — A template can bundle the firm's own custom role

- **Covers:** plan 25.6
- **Fixture:** `custom-role`
- **Steps**
  1. Sign in as the fixture's **Firm admin**, TEST01 selected.
  2. Administration → **User Templates** → **New**.
  3. **Template code** `<suffix>-my-job`, **Job name** anything.
  4. **Roles** → tick the fixture's **Custom role** (`Night Desk <suffix>`). **Save.**
- **Expect:** created, **Origin: This firm**. This is the first place the screen *says* the custom role belongs to TEST01 — the roles grid only says "Custom role".
- **Data**
  ```sql
  select t.code, t.firm_id, t.is_system, r.code as role
  from   platform.user_templates t
  join   platform.user_template_roles tr on tr.template_id = t.id and tr.is_deleted = false
  join   platform.roles r on r.id = tr.role_id
  where  t.code = '<suffix>-my-job';
  ```
  One row, `firm_id` TEST01's, `is_system` false. Audit `user_template.created`.
- **Leaves:** a custom role and a template.

### TC-ROLE-006 — Hiring into a template grants exactly its roles

- **Covers:** plan 25.7
- **Fixture:** `custom-template`
- **Steps**
  1. Sign in as the fixture's **Firm admin**, TEST01 selected.
  2. Administration → **Users** → **New**.
  3. Full name anything; email `<suffix>.hire@fixtures.local`; **Initial password** `Fixture@2026pw` (twelve or more characters — the form does not say which rule it refused on if shorter).
  4. **Job template** → the fixture's **Job template**. Leave **Roles** empty. Firms as prefilled. **Save.**
  5. Select the new row → **Roles by firm**.
- **Expect:** one section, TEST01, holding **only** `Night Desk <suffix>`.
- **Data**
  ```sql
  select r.code, ur.firm_id, ur.is_deleted
  from   platform.user_roles ur
  join   platform.roles r on r.id = ur.role_id
  join   platform.users u on u.id = ur.user_id
  where  u.email = '<suffix>.hire@fixtures.local';
  ```
  Audit: `user.created`, `user.firms_set`, `user_template.applied` (with `template_code` and `role_codes`) and `user.roles_set` — four rows for one Save.
- **Leaves:** a custom role, a template, a user.

### TC-ROLE-007 — A custom role's codes become exactly those screens

- **Covers:** plan 25.8
- **Fixture:** `role-holder`
- **Steps**
  1. Sign in as the fixture's **Role holder** (no password change is asked for). TEST01 is their only firm.
  2. Read the sidebar, and open each module to see its tabs.
- **Expect** — exactly these, taken from the desktop's own visibility logic:

  | Sidebar | Tabs inside |
  | --- | --- |
  | **Masters** | Customers, Statements |
  | **Sales** | GST Returns |
  | **Quotations** | — |
  | **Sales Orders** | — |
  | **Delivery Notes** | Delivery Notes |
  | **Sales Invoices** | Sales Invoices |
  | **Sales Returns** | — |
  | **Finance** | **Receipts only**, with **Record Receipt** offered |

  **No** Dashboard, Purchases, Inventory, Reports, Settings or Administration. Four codes — `SALES_VIEW`, `CUSTOMER_VIEW`, `RECEIPT_VIEW`, `RECEIPT_CREATE` — rendered as screens.
- **Why Finance holds Receipts at all:** the role carries `RECEIPT_VIEW` beside `RECEIPT_CREATE`. With the create code alone there is no Receipts screen to record on — Finance opens on the view code — which is the mistake plan row 25.3 used to make.
- **Leaves:** a custom role and a holder.

### TC-ROLE-008 — Editing a role signs out everyone holding it

- **Covers:** plan 25.9
- **Fixture:** `role-holder`
- **Steps** — two windows:
  1. **Window A:** sign in as the fixture's **Role holder**. Open Finance → Receipts. **Record Receipt** is there.
  2. **Window B:** sign in as the fixture's **Firm admin**, TEST01 selected. Roles → the fixture's **Custom role** → **Edit** → untick **`RECEIPT_CREATE`** → **Save**.
  3. **Window A:** click anything.
  4. Sign back in as the holder. Finance → Receipts.
- **Expect**
  - Step 3: **signed out on that click** — nobody asked them to. Editing a role revokes every holder's tokens.
  - Step 4: the **sidebar is unchanged** (the table in TC-ROLE-007), and on Receipts **Record Receipt is gone**. `RECEIPT_CREATE` gates the button, not the screen.
  - A role is not versioned: editing it changes everybody holding it, immediately.
- **Data**
  ```sql
  select email, authorization_version from platform.users
  where  email = '<suffix>.holder@fixtures.local';
  ```
  Run before and after step 2: **`authorization_version` goes up by one**. That column is the sign-out. Audit `role.permissions_set`.
- **Leaves:** a custom role with three codes, and a holder.

### TC-ROLE-009 — Deleting a role somebody holds just goes through

- **Covers:** plan 25.10, 25.10a
- **Fixture:** `role-holder`
- **Steps** — two windows:
  1. **Window A:** sign in as the fixture's **Role holder**.
  2. **Window B:** sign in as the fixture's **Firm admin**, TEST01 selected. Roles → the fixture's **Custom role** → **Delete**.
  3. **Window A:** click anything. Then sign back in as the holder.
- **Expect**
  - Step 2: **it deletes.** No refusal, no warning, no count of who holds it. The only guard in `delete_role` is against System roles.
  - Step 3: **signed out** on the click; signed back in, an **empty sidebar** — no module at all — and nothing on screen says why.
  - Recorded as the behaviour, **not a defect**. Whether deleting a held role should refuse, or warn with the count, is an open decision for the owner.
- **Data**
  ```sql
  select r.code, r.is_deleted, ur.is_deleted as holder_row_deleted
  from   platform.roles r
  join   platform.user_roles ur on ur.role_id = r.id
  where  r.code = '<suffix>-night-desk';
  ```
  `roles.is_deleted` is **true**; the holder's `user_roles` row is **left in place** — it names a deleted role, and the token simply stops carrying its codes. Audit `role.deleted`.
- **Leaves:** a deleted custom role, and a holder with nothing.

---

## Platform mode — the switcher and what a platform administrator starts on

A platform administrator with reach over every firm, and a member of none, used
to get a token carrying every code — so the sidebar offered Sales and
Inventory — and an empty firm switcher, so every one of those screens refused
its first request. The firm switcher is now the mode switch: **Platform** is
one of its entries.

**Firm counts vary.** The switcher lists every active firm on the platform:
the four demo firms, TEST01 and TEST02, and any firm created while testing
section 27. Cases name the firms that must be there, never how many.

### TC-PLAT-001 — A platform administrator starts on Platform, every time

- **Covers:** plan 26.1, 26.8
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**.
  2. Read the firm control in the header, and the status bar.
  3. Switch into **TEST01** (see TC-PLAT-003), then sign out and sign back in.
- **Expect**
  - Steps 2 and 3: the header firm control reads **Platform**, and so does the status bar — **including after having been in TEST01**.
  - That is deliberate: somebody with reach over every firm's books must not land silently in one of them on a screen that looks like their own. `SessionController.resolveLandingFirm` returns no firm for any platform administrator, whatever their last firm or primary.
- **Data:** switching firms writes `platform.user_preferences.default_firm_id` (and a `user_preferences.updated` audit row) — for a platform administrator that preference is **ignored** at sign-in, which is the rule this case checks.
- **Leaves:** a platform administrator.

### TC-PLAT-002 — Platform mode offers the platform, and nothing that needs a firm

- **Covers:** plan 26.2, 26.3
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. The header reads **Platform**.
  2. Read the sidebar. Open **Administration** and **Settings** and read their tabs.
- **Expect** — taken from the desktop's own visibility logic:

  | Sidebar | Tabs inside |
  | --- | --- |
  | **Dashboard** | — |
  | **Administration** | Firms · Users · Roles & Permissions (Roles, Permissions) · User Templates · User-Firm Assignments |
  | **Licensing** | — |
  | **Settings** | Audit Logs · Diagnostics |

  **No** Masters, Sales, Quotations, Sales Orders, Delivery Notes, Sales Invoices, Sales Returns, Purchases, Inventory, Finance or Reports. **No** Numbering Series, Business Profiles, Tax, UOM or Industry Templates tabs — those live in a firm's own store.
- **Why:** `requiresFirm` on a module *and* on a tab hides what needs a firm when none is selected. A platform administrator's token carries every code, so permissions alone would offer everything.
- **Leaves:** a platform administrator.

### TC-PLAT-003 — The switcher lists every firm, and choosing one grows the workspace

- **Covers:** plan 26.4, 26.5, 26.6, 26.7
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**.
  2. Open the firm control.
  3. Pick **TEST01**.
  4. Open **Sales Orders**.
  5. Open the firm control again and pick **Platform**.
- **Expect**
  - Step 2: a **Platform** entry at the top with a tick beside it, then **every active firm** — TEST01, TEST02, WHOLE01, ELEC01, MEDI01, FOOD01 among them — **although this account is a member of none**.
  - Step 3: a notification names TEST01. The sidebar grows **Masters, Sales, Quotations, Sales Orders, Delivery Notes, Sales Invoices, Sales Returns, Purchases, Purchase Invoices, Purchase Returns, Goods Receipts, Inventory, Finance, Reports**. Administration gains its configuration tabs (Numbering Series through Industry Templates). **Licensing goes away** — it is a platform screen.
  - Step 4: the screen **loads** — an empty list, since TEST01 has no orders — with no error. Before the fix this module was offered and this screen failed.
  - Step 5: **"Working on the platform. No firm is selected."** The firm-owned modules go away again.
- **Data (HTTP)** — the switcher's source:
  ```
  GET /api/v1/me/firms          (as the fixture's platform admin)
  ```
  Every active firm, each with `is_primary: false` — there is no membership row, so nobody's primary. The same call as a firm user returns only their own firms.
- **Leaves:** a platform administrator.

### TC-PLAT-004 — Being a member of firms does not change where a platform administrator lands

- **Covers:** plan 26.9
- **Fixture:** `platform-admin-member`
- **Steps**
  1. Sign in as the fixture's **Platform admin** — this one *is* a member of TEST01 (primary) and TEST02.
  2. Read the header; open the firm control.
- **Expect:** still starts on **Platform**. The switcher looks as in TC-PLAT-003, with TEST01 marked **primary**. Membership is not what decides the landing; the designation is.
- **Leaves:** a platform administrator with two memberships.

### TC-PLAT-005 — A firm user never sees Platform

- **Covers:** plan 26.10
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**.
  2. Read the header; open the firm control.
- **Expect:** **no Platform entry** anywhere; TEST01 selected and the only firm; lands in it. For an ordinary user a null firm is an empty application rather than a mode, so the switcher refuses to offer it.
- **Leaves:** a firm admin user.

---

## The user menu — who you are, and where you start

`GET /api/v1/me` names the signed-in person; `PUT /api/v1/me/primary-firm`
and `POST /api/v1/auth/change-password` are theirs to call. All three need
being signed in and nothing else.

### TC-ME-001 — The menu names you, including after a restored session

- **Covers:** plan 26a.1, 26a.2
- **Fixture:** `two-firm-user`
- **Steps**
  1. Sign in as the fixture's **Two-firm user** with **Remember me** ticked.
  2. Open the account menu (top right); read the status bar.
  3. Close the application and start it again.
- **Expect**
  - Step 2: the first row is the **full name** — `Two Firm User (<suffix>)` — with the **email** under it. Not the address typed at sign-in, and not the word "User". The status bar shows the same name.
  - Step 3: still the name. It used to read "User", because a restored session never passes through the login form and the token carries no name.
- **Leaves:** a two-firm user.

### TC-ME-002 — Choosing your own primary firm

- **Covers:** plan 26a.3, 26a.4
- **Fixture:** `two-firm-user`
- **Steps**
  1. Sign in as the fixture's **Two-firm user**.
  2. Account menu → **Primary firm**.
  3. Choose **TEST02** → **Save**.
  4. Open the firm switcher.
- **Expect**
  - Step 2: a dialog listing TEST01 and TEST02, **TEST01 selected**, and **Save dead** until something else is chosen.
  - Step 3: a notice says which firm you will start in next time. **Nothing on screen switches** — the primary is for next time, not for now.
  - Step 4: **TEST02** is labelled `primary` beside its code.
- **Data**
  ```sql
  select f.code, uf.is_primary, uf.updated_at
  from   platform.user_firms uf
  join   platform.firms f on f.id = uf.firm_id
  join   platform.users u on u.id = uf.user_id
  where  u.email = '<suffix>.twofirm@fixtures.local' and uf.is_deleted = false;
  ```
  TEST02 `true`, TEST01 `false`. Audit `user.primary_firm_set`. The old primary is cleared and flushed before the new one is set, because `UQ_user_firms_active_primary` is checked per statement.
- **Leaves:** a two-firm user whose primary is TEST02.

### TC-ME-003 — Signing in lands in the primary firm, not the last one used

- **Covers:** plan 26a.5
- **Fixture:** `two-firm-user`
- **Steps**
  1. Sign in as the fixture's **Two-firm user** (primary: TEST01).
  2. Switch to **TEST02** and open any screen there.
  3. Sign out, sign back in.
- **Expect:** you land in **TEST01**, the primary — not TEST02, where you were last. Switching is for the session; the primary is for next time. Until 2026-09-08 it was the reverse, so the flag meant nothing to anybody who had ever switched.
- **Leaves:** a two-firm user.

### TC-ME-004 — Nobody can make a firm they do not belong to their primary

- **Covers:** plan 26a.7
- **Fixture:** `two-firm-user`
- **Steps (HTTP)** — sign in as the fixture's user and send:
  ```
  PUT /api/v1/me/primary-firm
  { "firm_id": "<WHOLE01's id>" }
  ```
  WHOLE01's id is in `GET /api/v1/firms` as a platform administrator, or in `platform.firms`.
- **Expect:** **422**, "You can only make a firm you belong to your primary firm." Nothing changes.
- **Leaves:** a two-firm user.

### TC-ME-005 — My profile, for somebody who cannot read the user list

- **Covers:** plan 26a.8, 26a.10
- **Fixture:** `two-firm-user` — holds `SALES_EXECUTIVE` and `CUSTOMER_SUPPORT`, neither of which carries `USER_VIEW`.
- **Steps**
  1. Sign in as the fixture's **Two-firm user**.
  2. Account menu → **My profile**.
- **Expect**
  - Opens. Name and email at the top; sections **Work**, **Contact**, **Firms**, **Access** and **Sign-in**; every unset field reads **Not set**.
  - **Firms:** TEST01 marked **Primary**, and TEST02.
  - **Access:** roles grouped as **In every firm** (Customer Support) and **In TEST01** (Sales Executive).
  - No boxes to type in, and the line: *"These details are held by your administrator. Ask them to change anything here; your appearance, primary firm and password are yours to set."*
- **Data (HTTP):** `GET /api/v1/me` as this user → **200** with `profile` and `roles` (each role carrying `firm_code`, null for the every-firm tier). `GET /api/v1/users/{their own id}` → **403**: reading yourself is not reading the user list.
- **Leaves:** a two-firm user.

### TC-ME-006 — A platform administrator's menu

- **Covers:** plan 26a.6 (platform half), 26a.9
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**.
  2. Open the account menu; open **My profile**.
- **Expect:** **no Primary firm entry** — a platform administrator always starts on Platform, so there is nothing to choose. My profile shows a **Platform administrator** chip under the name.
- **Leaves:** a platform administrator.

### TC-ME-007 — Somebody in one firm has no primary to choose

- **Covers:** plan 26a.6 (one-firm half)
- **Fixture:** `firm-admin`
- **Steps:** sign in as the fixture's **Firm admin** and open the account menu.
- **Expect:** **no Primary firm entry**. The menu offers it only to somebody with more than one firm who is not a platform administrator.
- **Leaves:** a firm admin user.

### TC-ME-008 — Changing your own password

- **Covers:** plan 26a.11, 26a.12, 26a.13
- **Fixture:** `two-firm-user`
- **Steps**
  1. Sign in as the fixture's **Two-firm user** — in **two windows** if you want to see the second one signed out.
  2. Account menu → **My profile** → **Change password**.
  3. New password `Short@1` (under twelve characters).
  4. New password `LongEnoughPassw0rd` (no symbol).
  5. Current password `Wrong@Password1`, new password `Str0ng-Passw0rd!` twice.
  6. Current password `Fixture@2026pw`, new password `Str0ng-Passw0rd!` twice.
- **Expect**
  - Step 3: refused beside the box, **"Use at least 12 characters."** — nothing sent.
  - Step 4: **"Include a symbol."** — nothing sent. (The desktop checks the same rules the server enforces: twelve characters, upper, lower, digit, symbol.)
  - Step 5: the server's refusal in the dialog — **"Current password is incorrect."** — and the dialog **stays open** for another try.
  - Step 6: both dialogs close and you land on the login screen with **"Password changed. Sign in with your new password."** The other window is signed out on its next click. Sign in with `Str0ng-Passw0rd!`.
  - No need to set it back: the account is this run's own.
- **Data**
  ```sql
  select authorization_version, force_password_change, updated_at
  from   platform.users where email = '<suffix>.twofirm@fixtures.local';
  select count(*) from platform.password_history ph
  join   platform.users u on u.id = ph.user_id
  where  u.email = '<suffix>.twofirm@fixtures.local';
  ```
  `authorization_version` up by one (every session ends, including this one); one `password_history` row holding the old hash. Audit `identity.password_changed`. The server also refuses any of the last five passwords.
- **Leaves:** a two-firm user whose password is `Str0ng-Passw0rd!`.

---

## Adding the next section

1. List what each row needs to exist before it starts — that is the fixture.
2. Add the fixture to `backend/scripts/test_fixture.py`, built from the API, composing the existing blocks where it can.
3. **Run the fixture and drive every expectation against the backend** before writing it down; take sidebar and tab lists from `ModuleVisibility`, not from the permission table.
4. Give each case a stable `TC-AREA-NNN` id and the six parts above. IDs do not change when cases are added, which plan section numbers did.
5. Replace the section in `MANUAL_UI_TEST_PLAN.md` with a pointer and a row → case map, so there is one version and not two.
