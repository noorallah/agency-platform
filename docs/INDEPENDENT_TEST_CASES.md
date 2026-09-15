# Independent test cases

Pick any case, run it on its own, at any time, in any order. That is the
whole promise, and it is what `docs/MANUAL_UI_TEST_PLAN.md` could not make: its
rows were a chain. 20.1b needed the two-firm user 20.6 creates, 22.1 needed a
cashier nobody had made, 25.10 deletes the role 25.2 makes so 25.9 can never be
run twice, and 24.12 named an account whose password had changed. Picking a row
out of order met a failure that belonged to the plan, not to the product.

**Pilot: plan section 25 (a firm's own roles and templates), converted
2026-09-16.** Other sections move here one at a time; until then they stay in
the plan.

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
  Firm        : TEST01  (select it in the firm switcher)
  Firm admin  : t0916xk2q.admin@fixtures.local / Fixture@2026pw
  Custom role : t0916xk2q-night-desk  (Night Desk t0916xk2q)
  It carries  : SALES_VIEW, CUSTOMER_VIEW, RECEIPT_VIEW, RECEIPT_CREATE
  Role holder : t0916xk2q.holder@fixtures.local / Fixture@2026pw
  Tables      : schema test_fixtures; identity rows in platform
  Suffix      : t0916xk2q  (everything this run made has it)
```

`scripts\test_fixture.py list` shows every fixture and the cases that use it.

### 2. Everything happens in TEST01

Fixtures work in one firm, **TEST01**, stored in a schema of its own,
**`test_fixtures`**. The four demo firms are never touched, and a table check
against `test_fixtures` shows only test data. The first fixture run builds
TEST01 — create, provision, open the books, GST template, head office, the
Wholesale profile — and every later run finds it and moves on.

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
- **Also try** `FIRM_ADMIN` or `Cashier` as a code — the same refusal: the designation and all sixteen seeded codes are reserved, case-insensitively.
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

## Adding the next section

1. List what each row needs to exist before it starts — that is the fixture.
2. Add the fixture to `backend/scripts/test_fixture.py`, built from the API, composing the existing blocks where it can.
3. **Run the fixture and drive every expectation against the backend** before writing it down; take sidebar and tab lists from `ModuleVisibility`, not from the permission table.
4. Give each case a stable `TC-AREA-NNN` id and the six parts above. IDs do not change when cases are added, which plan section numbers did.
5. Replace the section in `MANUAL_UI_TEST_PLAN.md` with a pointer and a row → case map, so there is one version and not two.
