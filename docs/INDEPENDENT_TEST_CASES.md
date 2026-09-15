# Independent test cases

Pick any case, run it on its own, at any time, in any order. That is the
whole promise, and it is what `docs/MANUAL_UI_TEST_PLAN.md` could not make: its
rows were a chain. 20.1b needed the two-firm user 20.6 creates, 22.1 needed a
cashier nobody had made, 25.10 deletes the role 25.2 makes so 25.9 can never be
run twice, and 24.12 named an account whose password had changed. Picking a row
out of order met a failure that belonged to the plan, not to the product.

**Converted so far:** plan sections 16 to 19, 25 (the pilot), 26, 26a and 27 — see the
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
| **TESTSH1**, **TESTSH2** | `firm_shared` | only the cases *about* the shared store; built the first time `shared-pair` runs |
| `<SUFFIX>-U`, `-F`, `-R` | `fx_<suffix>_u` … | the firm-setup cases, which need a firm nobody has finished; a new one per run |

The demo firms are never touched, and a table check against those schemas
shows only test data. The first fixture run builds both — create, provision,
open the books, GST template, head office, the Wholesale profile — through the
same endpoints plan section 27 tests; every later run finds them and moves on.
`scripts\test_fixture.py baseline` does only that.

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

## User tiers — what a platform operator may and may not reach

Four kinds of user, not interchangeable:

| Tier | Who | Reaches |
| --- | --- | --- |
| 1 | Platform operator (`PLATFORM` scope) | Creates firms and their people, provisions storage, sets a firm up. **Refused a firm's books.** |
| 2 | All-firms administrator (`ALL_FIRMS` scope) | Everything, in every firm, with no membership needed — see TC-PLAT-001..004. |
| 3 | Firm administrator (`FIRM_ADMIN`) | Everything inside their own firm, including its people. |
| 4 | Firm staff | The modules their job needs. |

No seeded account is tier 1, and no screen sets a scope, which is why the plan
used to change `superadmin`'s scope by SQL and change it back. The
`platform-operator` fixture makes one of its own instead.

### TC-TIER-001 — A platform operator runs the platform

- **Covers:** plan 16.2
- **Fixture:** `platform-operator`
- **Steps**
  1. Sign in as the fixture's **Operator**. The header reads **Platform** — where every platform administrator lands.
  2. Open Dashboard; Administration → **Firms**, **Users**, **Roles & Permissions**, **User Templates**, **User-Firm Assignments**; Settings → **Audit Logs**, **Diagnostics**.
- **Expect:** every one offered, and each opens. Running the platform is their job.
- **Data**
  ```sql
  select pa.scope from platform.platform_admins pa
  join   platform.users u on u.id = pa.user_id
  where  u.email = '<suffix>.operator@fixtures.local';
  ```
  `PLATFORM`.
- **Leaves:** a platform operator.

### TC-TIER-002 — A platform operator is refused the books, even where they are a member

- **Covers:** plan 16.3
- **Fixture:** `platform-operator`
- **Steps**
  1. Sign in as the fixture's **Operator**. Look for Sales, Purchases, Finance, Inventory.
  2. Open the firm switcher.
  3. Switch into **TEST01** and read the sidebar.
- **Expect**
  - Step 1: **none** offered on Platform. Their token carries **33** codes — firm, user, role, permission, platform and system administration (`FIRM_*`, `USER_*`, `ROLE_*`, `PERMISSION_*`, `PLATFORM_VIEW`, `PLATFORM_SETTINGS`, `SETTINGS_VIEW`, `SETTINGS_UPDATE`, `AUDIT_LOG_VIEW`, `DIAGNOSTICS_VIEW`, `LICENSE_MANAGE`, `SYSTEM_BACKUP`, `SYSTEM_RESTORE`, `SYSTEM_CONFIGURATION`) and nothing operational.
  - Step 2: Platform, **TEST01** (primary) and **TEST02** — the two firms they are a member of, and **not** every firm. An `ALL_FIRMS` administrator is widened to every firm (TC-PLAT-003); a `PLATFORM` one is not, but memberships they genuinely hold still show.
  - Step 3: **no business modules**. A designation is a ceiling, not a floor, and they hold no role in TEST01.
- **Data (HTTP):** `GET /api/v1/me/firms` as the operator → exactly TEST01 (`is_primary: true`) and TEST02.
- **Leaves:** a platform operator.

### TC-TIER-003 — The server agrees: no firm's books, all of the platform

- **Covers:** plan 16.4
- **Fixture:** `platform-operator`
- **Steps (HTTP)** — sign in as the fixture's operator:
  1. With `X-Firm-ID` of TEST01: `GET /api/v1/customers`, `GET /api/v1/sales-orders`, `GET /api/v1/finance/journal-entries`.
  2. With no `X-Firm-ID`: `GET /api/v1/users`, `/api/v1/firms`, `/api/v1/roles`, `/api/v1/audit-logs`.
- **Expect**
  1. **403** on all three, "You do not have permission to perform this action." — although they are a member of TEST01. Not a rule of its own: a `PLATFORM` administrator is simply not exempt from the membership check, and meets it holding no role.
  2. **200** on all four.
- **Leaves:** a platform operator.

---

## User templates — hiring by naming the job

A template is a named bundle of roles. Eleven are seeded and offered to every
firm; a firm may write its own and may not edit the platform's. Applying one is
an ordinary role write — nothing on the user records which template they came
from.

The eleven: Accounts (`ACCOUNTANT`), Counter Sales (`BILLING_EXECUTIVE`,
`CASHIER`), Customer Support, Field Sales (`SALES_EXECUTIVE`), Firm
Administrator, Firm Manager, Purchase Manager, Purchasing, Read Only
(`VIEWER`), Sales Manager and Warehouse (`INVENTORY_MANAGER`). TEST01 also
lists templates earlier runs wrote, and any template a platform administrator
offered to every firm; cases count only the eleven.

### TC-TMPL-001 — The platform's templates are listed, and locked

- **Covers:** plan 17.1, 17.2
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Administration → **User Templates**.
  2. Select **Counter Sales**; look at **Edit** and **Delete**; open it.
  3. **(HTTP)** `PATCH /api/v1/user-templates/{Counter Sales id}` with `{"name": "x"}`.
- **Expect**
  - Step 1: the **eleven** above with Origin **Platform**, each naming its roles — Counter Sales shows `BILLING_EXECUTIVE, CASHIER`.
  - Step 2: Edit and Delete **disabled**; the dialog subtitle reads "… · Provided by the platform". It is offered to every firm, so no one firm may change it.
  - Step 3: **422**, "Platform templates cannot be edited."
- **Leaves:** a firm admin user.

### TC-TMPL-002 — A firm's own template, and an edit that keeps its roles

- **Covers:** plan 17.3, 17.4
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, User Templates → **New**: Template code `<suffix>-night-counter`, Job name `Night Counter`, Roles `CASHIER` and `BILLING_EXECUTIVE`, Offered on → Save.
  2. Edit it; change only the **name** to `Night Counter renamed` → Save; reopen.
- **Expect**
  - Step 1: created; Origin **This firm**; subtitle "… · This firm's own".
  - Step 2: still `BILLING_EXECUTIVE, CASHIER`. An edit that says nothing about the bundle must not empty it — `role_ids` replaces the bundle when sent, and the form does not send it unchanged.
- **Data**
  ```sql
  select t.code, t.name, t.firm_id, r.code as role
  from   platform.user_templates t
  join   platform.user_template_roles tr on tr.template_id = t.id
  join   platform.roles r on r.id = tr.role_id
  where  t.code = '<suffix>-night-counter';
  ```
  Two rows, `firm_id` = TEST01. Audit `user_template.created`, `user_template.updated`.
- **Leaves:** a TEST01 template.

### TC-TMPL-003 — Hiring into a job in one step

- **Covers:** plan 17.4a, 17.4b
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Administration → Users → **New**: name `Job Hire <suffix>`, email `<suffix>.jobhire@fixtures.local`, a 12-character password, **Job template** Counter Sales. Save.
  2. New again: `Hand Hire <suffix>`, `<suffix>.handhire@fixtures.local`, Job template **blank**, Roles in this firm `CUSTOMER_SUPPORT` and `VIEWER`. Save.
- **Expect**
  - Step 1: created **and** holding `CASHIER` and `BILLING_EXECUTIVE` — one step, no second visit to the grid.
  - Step 2: exactly those two roles. The template field is optional.
- **Leaves:** two users in TEST01.

### TC-TMPL-004 — When a job is named, the job decides

- **Covers:** plan 17.4c, 17.4d
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Users → **New**. Pick `ACCOUNTANT` under Roles in this firm; then choose the **Read Only** job; then clear the job.
  2. Choose Read Only again and save (name, `<suffix>.readonly@fixtures.local`, password).
  3. Edit that user.
- **Expect**
  - Step 1: the helper text under **Roles in this firm** ends "Ignored when a job template is named above." Choosing the job **clears** ACCOUNTANT and **locks** the chips; clearing it unlocks them, empty.
  - Step 2: the user holds only `VIEWER`.
  - Step 3: **no Job template field** — it is create-only. A template is where somebody starts, and Apply job template on the grid is how to re-apply one.
- **Leaves:** a TEST01 user holding VIEWER.

### TC-TMPL-005 — Applying a job replaces what somebody holds

- **Covers:** plan 17.5, 17.6
- **Fixture:** `manual-hire`
- **Steps**
  1. As the fixture's **Firm admin**, Users → select **Manual Hire (<suffix>)** → **Apply job template**.
  2. Type `inventory` in **Search jobs**; clear it.
  3. Choose **Counter Sales** → Apply.
- **Expect**
  - Step 1: dialog "Apply a job template": "Whatever Manual Hire (<suffix>) holds now is replaced by the job's roles. You can edit them afterwards like any other user." One line per active job with its roles beneath; **Apply disabled** until a job is chosen.
  - Step 2: only **Warehouse** remains (the search covers name, code, description and role). A filter that hides the chosen job clears the choice.
  - Step 3: their TEST01 roles become exactly `BILLING_EXECUTIVE` and `CASHIER` — `SALES_EXECUTIVE` and `CUSTOMER_SUPPORT` are gone.
- **Data:** audit `user_template.applied` naming `template_code: counter-sales` and `role_codes`.
- **Leaves:** Manual Hire holding Counter Sales' roles.

### TC-TMPL-006 — A firm administrator's template writes the firm tier only

- **Covers:** plan 17.6a
- **Fixture:** `two-tier-hire`
- **Steps**
  1. As the fixture's **Firm admin**, Users → **Two Tier Hire (<suffix>)** → Apply job template → **Counter Sales** → Apply.
  2. Sign in as the fixture's **Platform admin**, open the same user.
- **Expect:** **Roles in every firm** still `VIEWER`, `CUSTOMER_SUPPORT`; **Roles in specific firms** now `TEST01: BILLING_EXECUTIVE · CASHIER` (was ACCOUNTANT, INVENTORY_MANAGER). A template overwrites the tier its caller writes and never touches the other.
- **Data (HTTP)**, as the platform admin: `GET /api/v1/users/{id}/roles` → the two global ids; `GET /api/v1/users/{id}/firms/{TEST01 id}/roles` → the two Counter Sales ids.
- **Leaves:** the user with a changed TEST01 tier.

### TC-TMPL-007 — A platform administrator's template writes the global tier only

- **Covers:** plan 17.6b
- **Fixture:** `two-tier-hire`
- **Steps**
  1. As the fixture's **Platform admin**, Users → **Two Tier Hire (<suffix>)** → Apply job template → **Warehouse** → Apply.
  2. Reopen the user.
- **Expect:** **Roles in every firm** becomes exactly `INVENTORY_MANAGER` (Warehouse carries that one role) — VIEWER and CUSTOMER_SUPPORT are gone — while **Roles in specific firms** still reads `TEST01: ACCOUNTANT · INVENTORY_MANAGER`, untouched. The desktop never names a firm on this call for a platform administrator. *(The plan said "four roles, a different four"; Warehouse has one role, so it is three.)*
- **Leaves:** the user with a changed global tier.

### TC-TMPL-008 — After a template, somebody is an ordinary user

- **Covers:** plan 17.7
- **Fixture:** `two-tier-hire`
- **Steps**
  1. As the fixture's **Firm admin**, edit **Two Tier Hire (<suffix>)**: under **Roles in this firm** remove `ACCOUNTANT`, add `CASHIER` → Save & Close → reopen.
- **Expect:** `INVENTORY_MANAGER` and `CASHIER`. **Also applies here** (read-only, lower in the Security section) shows the global tier, `CUSTOMER_SUPPORT` and `VIEWER`, which a firm administrator cannot change. Nothing on the user records a template.
- **Leaves:** the user with an edited TEST01 tier.

### TC-TMPL-009 — Somebody without role codes has no templates to see

- **Covers:** plan 17.9
- **Fixture:** `sales-executive`
- **Steps:** sign in as the fixture's **Seller**; look for Administration.
- **Expect:** **Administration is not offered at all**. `SALES_EXECUTIVE` holds `CUSTOMER_VIEW`, `SALES_VIEW`, `SALES_QUOTATION_CREATE`, `SALES_ORDER_CREATE`, `SALES_INVOICE_CREATE`, `TERRITORY_VIEW` — no `ROLE_VIEW`. **(HTTP)** `GET /api/v1/user-templates` with `X-Firm-ID` of TEST01 → **403**.
- **Leaves:** a seller.

### TC-TMPL-010 — Retiring a template is a decision about future hires

- **Covers:** plan 17.8
- **Fixture:** `firm-template-hire`
- **Steps**
  1. As the fixture's **Firm admin**, User Templates → select the fixture's **Job template** → **Delete** (confirm).
  2. Users → open **Night Counter Hire (<suffix>)**.
  3. Users → New → open the Job template list.
- **Expect**
  - Step 1: the row leaves the grid (a soft delete; there is no button called Retire).
  - Step 2: still `BILLING_EXECUTIVE` and `CASHIER`.
  - Step 3: the retired template is **not offered**.
- **Leaves:** a retired template and the user it hired.

### TC-TMPL-011 — A template cannot bundle a platform role

- **Covers:** plan 17.10
- **Fixture:** `firm-admin`
- **Steps (HTTP)** — find the `PLATFORM_ADMIN` role's id (`select id from platform.roles where code = 'PLATFORM_ADMIN'`; a firm admin's role list never shows it). As the fixture's firm admin, with `X-Firm-ID` of TEST01: `POST /api/v1/user-templates` `{"code": "<suffix>-bad", "name": "Bad", "role_ids": ["<that id>"]}`.
- **Expect:** **422**, "A template cannot bundle platform or cross-firm roles." Nothing created. That role carries every permission code; a template able to name it would be a second door onto the same room.
- **Leaves:** a firm admin user.

---

## Hiring like an existing person

The other half of templates, and the more common one: an administrator usually
has a person in mind rather than a written-down job. **Hire like this person**
copies roles and firm memberships and nothing that belongs to the person.

The dialog checks only that the boxes are filled and the email has an `@`; the
**server** applies the password policy — twelve characters, upper, lower,
digit, symbol.

### TC-HIRE-001 — The dialog, and what it refuses

- **Covers:** plan 18.1, 18.2, 18.3
- **Fixture:** `clone-source`
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Administration → Users → select **Source Seller (<suffix>)** → **Hire like this person**.
  2. Press **Create** with the form empty.
  3. Name `Clone Test`, email `not-an-email`, any password → Create.
  4. Email `<suffix>.clone@fixtures.local`, password `short` → Create.
- **Expect**
  - Step 1: "Hire like this person": "The new user gets the same roles and firms as Source Seller (<suffix>), and none of their personal details, password or history. You can edit their roles afterwards like any other user." Boxes **Full name**, **Email**, **Initial password** ("They must change it when they first sign in.").
  - Step 2: under each box — "Give the new person a name.", "An email is required.", "An initial password is required." Nothing created.
  - Step 3: "That is not an email." under Email.
  - Step 4: the **server** refuses, shown **on the dialog** in red: "Password does not meet the configured policy." with its reasons — must contain at least 12 characters, an uppercase letter, a digit, a symbol. Every box keeps what was typed.
- **Leaves:** a firm admin and a source seller; nothing cloned.

### TC-HIRE-002 — A clone gets the access, not the person

- **Covers:** plan 18.4, 18.5, 18.6
- **Fixture:** `clone-source`
- **Steps**
  1. As the fixture's **Firm admin**, Hire like this person on **Source Seller (<suffix>)**: `Clone Test <suffix>`, `<suffix>.clone@fixtures.local`, `Welcome@12345` → Create.
  2. Open the new user.
  3. Sign out; sign in as `<suffix>.clone@fixtures.local` / `Welcome@12345`. Set the new password to `CloneTest@2026x`.
- **Expect**
  - Step 1: "Clone Test <suffix> was created with the same access as Source Seller (<suffix>), and must change their password on first sign-in."
  - Step 2: `SALES_EXECUTIVE` in TEST01 and TEST01 as their firm (primary) — the same as the source. **Blank** mobile, employee code, department, joining date; **Also applies here** reads None.
  - Step 3: a **Set a new password** screen instead of the application — Current password, New password, Confirm new password, **Update password** — and nothing else opens until it is done. Afterwards: the source's access and no Administration. A password somebody else chose is not a password.
- **Data**
  ```sql
  select email, force_password_change, employee_code, joining_date, created_at
  from   platform.users where email = '<suffix>.clone@fixtures.local';
  ```
  `force_password_change` true until step 3, false after. Audit `user.cloned` carrying the source's id.
- **Leaves:** a clone in TEST01 with its own password.

### TC-HIRE-003 — A clone is a starting point, not a link

- **Covers:** plan 18.7
- **Fixture:** `clone-source`
- **Steps**
  1. As the fixture's **Firm admin**, make a clone of **Source Seller (<suffix>)** as in TC-HIRE-002 step 1.
  2. Edit the clone: add `CUSTOMER_SUPPORT` under Roles in this firm → Save & Close.
  3. Open **Source Seller (<suffix>)**; close without saving.
- **Expect:** the clone holds `SALES_EXECUTIVE` and `CUSTOMER_SUPPORT`; the source still holds exactly `SALES_EXECUTIVE`.
- **Leaves:** a clone with one extra role.

### TC-HIRE-004 — Copying access is granting access

- **Covers:** plan 18.8
- **Fixture:** `clone-source`
- **Steps**
  1. Sign in as the fixture's **Source** (a `SALES_EXECUTIVE`) and look for the users grid.
  2. **(HTTP)** As the source, with `X-Firm-ID` of TEST01: `POST /api/v1/users/{their own id}/clone` with `{"email": "<suffix>.x@fixtures.local", "full_name": "x", "password": "Welcome@12345"}`.
- **Expect**
  - Step 1: **Administration is not offered**, so there is no Hire like this person.
  - Step 2: **403**. The action needs `ROLE_ASSIGN` — somebody who may open accounts but not grant access must not be able to copy access instead.
- **Leaves:** nothing new.

---

## Templates from the platform side — which firms a job is offered to

A platform caller's scope resolves to no firm, and for a template no firm used
to mean **every** firm — so a job written while setting up one firm was
published to all of them. **Offered to** names the firm; blank still means
every firm, deliberately.

**These cases write platform-wide rows.** A template offered to every firm
appears in every firm's list, the demo firms included, until it is deleted —
each case ends by deleting what it made.

### TC-TMPL-012 — A platform administrator chooses who a job is offered to

- **Covers:** plan 19.1
- **Fixture:** `platform-admin`
- **Steps:** sign in as the fixture's **Platform admin** (on Platform) → Administration → **User Templates** → **New**.
- **Expect:** the tab opens with no firm selected — it carries `requiresFirm: false`, since a platform operator has no firm of their own. The General section has an **Offered to** picker: one chip per firm reading `CODE · Name`, helper "Leave blank to offer this job to every firm." A firm administrator's form has no such field. It is create-only.
- **Leaves:** nothing (cancel the form).

### TC-TMPL-013 — A job offered to one firm is not offered to another

- **Covers:** plan 19.2, 19.3
- **Fixture:** `template-offering`
- **Steps**
  1. As the fixture's **Platform admin**, User Templates → New: code `<suffix>-t2-night`, name `T2 Night`, **Offered to** the `TEST02 · …` chip, Roles `CASHIER` → Save.
  2. Sign in as the fixture's **Firm admin** (TEST01) → User Templates.
  3. As the platform admin again, delete `<suffix>-t2-night`.
- **Expect**
  - Step 1: created. Origin reads **One firm**; the subtitle reads "`<suffix>-t2-night — T2 Night` · Offered to one firm". **Every firm** would mean the firm never left the form; **This firm** is the wording #383 fixed — either means step 2 fails too.
  - Step 2: `<suffix>-t2-night` is **not** listed.
- **Data**
  ```sql
  select t.code, f.code as offered_to from platform.user_templates t
  left join platform.firms f on f.id = t.firm_id
  where t.code = '<suffix>-t2-night';
  ```
  `TEST02`.
- **Leaves:** nothing, once deleted.

### TC-TMPL-014 — A job offered to every firm is the platform's to change

- **Covers:** plan 19.4, 19.4a
- **Fixture:** `template-offering`
- **Steps**
  1. As the fixture's **Platform admin**, New: `<suffix>-every-night`, `Every Night`, Roles `CASHIER`, **Offered to blank** → Save. Edit its name → Save.
  2. Sign in as the fixture's **Firm admin** → User Templates → select `<suffix>-every-night`.
  3. **(HTTP)** As the firm admin: `PATCH /api/v1/user-templates/{id}` `{"name": "y"}`, then `DELETE /api/v1/user-templates/{id}`.
  4. As the platform admin, **Delete** it.
- **Expect**
  - Step 1: Origin **Every firm**, and the platform admin may still edit it.
  - Step 2: listed, Origin **Every firm**, subtitle "… · Offered to every firm". **Edit** and **Delete** disabled.
  - Step 3: **422** on both, "This template is offered to every firm, so only a platform administrator can change or retire it."
  - Step 4: gone from every firm's list.
- **Leaves:** nothing, once deleted.

### TC-TMPL-015 — A firm administrator cannot write a template for another firm

- **Covers:** plan 19.5
- **Fixture:** `firm-admin`
- **Steps (HTTP)** — as the fixture's firm admin with `X-Firm-ID` of TEST01: `POST /api/v1/user-templates` `{"code": "<suffix>-x", "name": "X", "firm_id": "11111111-1111-1111-1111-111111111111", "role_ids": ["<CASHIER's id>"]}`.
- **Expect:** **422**, "You can only act within your own firm." Nothing created. Refused, not silently redirected.
  - The `firm_id` need not be a real firm: for a firm caller any firm but their own takes the same branch, and a firm administrator cannot read `/api/v1/firms` to find one anyway.
  - `role_ids` must be non-empty and well formed, or validation refuses the body first and the case tests pydantic rather than the firm check. CASHIER's id: `select id from platform.roles where code = 'CASHIER'`.
- **Leaves:** a firm admin user.

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

## Firms — creating one and finishing it

A firm is created in one place and finished in several: storage, business
profile, books, tax, first branch and people are each a separate act.
**Administration → Firms** creates it, and **Set up** on that grid shows each
step and does four of them.

**These cases make firms of their own.** Creating a firm, provisioning it and
opening its books for the first time are the behaviours under test, so they
cannot run against TEST01, which was finished long ago. The fixtures build
firms whose code and schema carry the run's suffix — `T0916ABCD-F` in schema
`fx_t0916abcd_f` — so no two runs meet. A firm with no data costs nothing; a
dedicated one leaves its schema behind. Provisioning runs the migrations, so
`unfinished-firm` and `ready-firm` take a minute or two.

| Fixture | Builds |
| --- | --- |
| `unprovisioned-firm` | a platform admin, and a `SCHEMA` firm whose storage is **not** built |
| `unfinished-firm` | a platform admin, and a `SCHEMA` firm that is provisioned and **nothing else** — no profile, books, tax, branch or members |
| `ready-firm` | a platform admin, a **finished** `SCHEMA` firm (Wholesale), its firm admin, a `VIEWER`, two product categories, a customer, and a 500.00 cash receipt that has posted |

### TC-FIRM-001 — Firms is an Administration tab that needs no firm

- **Covers:** plan 27.1, 27.2
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. The header reads **Platform**.
  2. Open **Administration** → **Firms**.
  3. Select TEST01 and open it with **Open this firm**; look through **Masters**.
- **Expect**
  - Step 2: the list of every firm. This is the one Administration tab that works with no firm selected.
  - Step 3: **no Firms** under Masters. It moved to Administration on 2026-09-06 — as a Masters tab it needed a firm, so creating a firm was reachable only from inside another one.
- **Leaves:** a platform administrator.

### TC-FIRM-002 — Creating a shared firm, and reaching it at once

- **Covers:** plan 27.3, 27.4, 27.8, 27.10, 27.15, 27.16
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. Administration → **Firms** → **New**.
  2. Type only a name, e.g. `Created <suffix>`, and save.
  3. Fill the rest: code **`<suffix>-s` in lower case** (e.g. `t0916abcd-s`), country `IN`, currency `INR`, financial year start `2026-04-01`, deployment mode **SHARED**. Save.
  4. Select the new row.
  5. Press **Open this firm**, then open the firm switcher.
- **Expect**
  - Step 2: refused. The five required fields are `name`, `code`, `country` (2 letters), `currency_code` (3 letters) and `financial_year_start`; everything else is optional.
  - Step 3: saves. The code is stored **upper case** — `T0916ABCD-S` — as are country and currency. The follow-up message names the next step.
  - Step 4: **Open this firm** enabled — a shared firm is ready at once. **Provision storage** hidden; there is nothing to build.
  - Step 5: "Working in …" names the new firm, the header shows it, the sidebar grows. **The firm is in the switcher.** That is the half that was broken: the switcher was read once at sign-in, so a firm created minutes earlier was refused as "not assigned to this user".
- **Data**
  ```sql
  select code, deployment_mode, schema_name, provisioned_at, created_at
  from   platform.firms where code = '<SUFFIX>-S';
  ```
  `SHARED`, no schema of its own. Audit `firm.created` on the platform trail.
- **Leaves:** a platform administrator, and a firm `<SUFFIX>-S` in the shared store with nothing in it. Delete it from the Firms grid if you like.

### TC-FIRM-003 — What firm creation refuses

- **Covers:** plan 27.5, 27.6, 27.7, 27.9
- **Fixture:** `platform-admin`
- **Steps (HTTP)** — sign in as the fixture's platform admin and send `POST /api/v1/firms`, each time with `name`, `country: "IN"`, `currency_code: "INR"`, `financial_year_start: "2026-04-01"` and `deployment_mode: "SHARED"`, varying one thing:
  1. `code: "WHOLE01"`
  2. `code: "BAD CODE"`
  3. `code: "<SUFFIX>-Z"`, `country: "IND"`
  4. `code: "<SUFFIX>-Y"`, `deployment_mode: "DATABASE"`, `database_name: "fx_nope"`, `connection_profile: "NOPE"`
- **Expect**
  1. **409**, "Firm code, GST number, or PAN number already exists." Unique among *live* firms only — a deleted firm releases its code.
  2. **422**, the code "should match pattern `^[A-Z0-9_-]+$`" — no spaces, no dots.
  3. **422**, country "should have at most 2 characters".
  4. **422**, "Connection profile 'NOPE' is not configured. Configured profiles: REMOTE_A." Refused at creation, not at first use — otherwise the firm would provision nothing and fail far from the request that caused it.
- **Leaves:** nothing; every request was refused.

### TC-FIRM-004 — A dedicated firm cannot be opened until it is provisioned

- **Covers:** plan 27.11, 27.12, 27.13
- **Fixture:** `unprovisioned-firm`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. Administration → **Firms**; select the fixture's **New firm**.
  2. Press **Provision storage**. Wait — it runs the migrations. Refresh and select the row again.
  3. Press **Provision storage** again.
- **Expect**
  - Step 1: **Open this firm disabled** — its schema has no tables, so switching in would answer errors on every screen. **Provision storage** enabled.
  - Step 2: **Open this firm** now enabled; the row carries a provisioned date.
  - Step 3: succeeds and reports it was already provisioned. Every step is create-if-missing, so this is also the repair action after a server was unreachable.
- **Data**
  ```sql
  select provisioned_at, provisioning_error from platform.firms where code = '<SUFFIX>-U';
  select count(*) from information_schema.tables where table_schema = 'fx_<suffix>_u';
  ```
  `provisioned_at` set, no error, and the schema now holds the firm tables — none of the platform's (`users`, `firms`, `user_firms` are pruned). Audit `firm.storage_provisioned`.
- **Leaves:** the firm, now provisioned.

### TC-FIRM-005 — A firm's storage routing is fixed at creation

- **Covers:** plan 27.14
- **Fixture:** `unprovisioned-firm`
- **Steps (HTTP)** — as the fixture's platform admin, `GET /api/v1/firms/{id}` for the fixture's firm, then `PUT` it back with `name`, `code`, `country`, `currency_code`, `financial_year_start` as read and `deployment_mode: "SHARED"`.
- **Expect:** **422**, "Firm storage routing cannot be changed after creation (currently SCHEMA/fx_<suffix>_u). Migrate the firm's data first." Nothing moves a firm's rows between stores.
- **Leaves:** the firm, unchanged.

### TC-FIRM-006 — The setup panel on a firm whose storage is not built

- **Covers:** plan 27.23e
- **Fixture:** `unprovisioned-firm`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. Administration → Firms → select the fixture's firm → **Set up**.
  2. **(HTTP)** Before pressing anything, `POST /api/v1/firms/{id}/open-books`, `.../apply-tax-template` and `.../create-default-branch`.
  3. On the panel, press **Provision storage**.
- **Expect**
  - Step 1: **Cannot post documents yet.** Storage is **missing** with a **Provision storage** button. Business profile, Books, Tax, Geography and Branches read "Cannot be checked until the firm's storage is provisioned." with no button and no hint. People reads "Nobody belongs to this firm yet. Only a platform administrator can open it."
  - Step 2: three **422**s — "Provision the firm's storage before opening its books.", "… before applying a tax template.", "… before creating its first branch."
  - Step 3: the list re-reads; Storage is done and Books now offers **Open the books**.
- **Leaves:** the firm, provisioned.

### TC-FIRM-007 — The setup panel says what an unfinished firm still needs

- **Covers:** plan 27.23, 27.23a, 27.23b
- **Fixture:** `unfinished-firm`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. Administration → Firms → select the fixture's firm → **Set up**.
  2. **(HTTP)** `GET /api/v1/firms/{id}/readiness`.
  3. From `backend`: `.\.venv\Scripts\python.exe scripts\check_firm_readiness.py <SUFFIX>-F`
- **Expect**
  - Step 1: titled `Set up <SUFFIX>-F`; **Cannot post documents yet.** Seven rows — Storage and Books **Required**, the rest **Recommended**:

    | Row | Reads | Offers |
    | --- | --- | --- |
    | Storage | SCHEMA storage provisioned. | done |
    | Business profile | None assigned. The firm runs as GENERIC … | a profile dropdown and **Assign** |
    | Books | No chart of accounts. Nothing can post until the books are opened. | **Open the books** |
    | Tax | No tax profiles or rules. … | **Apply GST template** |
    | Geography | No country in the store. … | a hint: Territories → Geography Masters; the GST template adds the country |
    | Branches and warehouses | … 0 branches, 0 warehouses so far. | **Create head office and main warehouse** |
    | People | Nobody belongs to this firm yet. … | a hint: Users → Add existing user, or User-Firm Assignments |
  - Step 2: **200**, `can_post: false`, `ready: false`, the same seven `steps` with `status` DONE / MISSING and `required`.
  - Step 3: the same seven rows from the same implementation, and that it **cannot post** because the books are not open.
- **Leaves:** the firm, unchanged.

### TC-FIRM-008 — Opening the books, once

- **Covers:** plan 27.23c, 27.23d
- **Fixture:** `unfinished-firm`
- **Steps**
  1. Sign in as the fixture's **Platform admin** → Firms → the fixture's firm → **Set up** → **Open the books**.
  2. Press **Refresh**. Then **(HTTP)** `POST /api/v1/firms/{id}/open-books` again.
  3. Settings → **Audit Logs**, on Platform.
- **Expect**
  - Step 1: the notice names the year: "Books opened for the year starting 2026-04-01" — the year *today* falls in, aligned to the firm's year start. Books re-reads as done: "24 accounts, 1 financial year, 12 periods, all 24 control accounts mapped, and a period open today." The button is gone, and the verdict reads **Can post documents. The recommended steps are still open.**
  - Step 2: nothing changes. The response: "The books were already open; nothing was created.", `already_open: true`, every count 0.
  - Step 3: **one** `firm.books_opened` row for this firm, with the counts (5 groups, 24 accounts, 12 periods, 2 types, 24 mappings) — not two. An audit row saying books were opened with every count at zero would be a lie, so the second call writes none.
- **Data**
  ```sql
  select count(*) from fx_<suffix>_f.ledger_accounts;          -- 24
  select count(*) from fx_<suffix>_f.accounting_periods;       -- 12
  select count(*) from fx_<suffix>_f.firm_control_accounts;    -- 24
  select action, created_at from platform.audit_logs
  where  entity_id = '<firm id>' order by created_at;
  ```
- **Leaves:** the firm with its books open.

### TC-FIRM-009 — The GST template, once

- **Covers:** plan 27.23f, 27.23h
- **Fixture:** `unfinished-firm`
- **Steps**
  1. As the fixture's **Platform admin**, open **Set up** on the fixture's firm → Tax row → **Apply GST template**.
  2. **(HTTP)** `POST /api/v1/firms/{id}/apply-tax-template` again; then once more with `{"template": "US"}`.
  3. Open this firm → Administration → Configuration → **Tax Configuration**.
- **Expect**
  - Step 1: "GST set up: 8 tax profiles and 6 rules." Tax re-reads as "1 tax system, 8 profiles, 6 rules", and **Geography flips to done** ("1 country in the store") — the template adds India to a store that has no country.
  - Step 2: "The firm already has a tax system; nothing was created.", `already_configured: true`. With `US`: **422**, only `IN_GST` exists. One `firm.tax_template_applied` audit row, not two.
  - Step 3: the system, four components and eight profiles, editable.
- **Leaves:** the firm with GST set up.

### TC-FIRM-010 — Assigning the business profile from the panel

- **Covers:** plan 27.23g
- **Fixture:** `unfinished-firm`
- **Steps**
  1. As the fixture's **Platform admin**, stay on **Platform** (no firm open) and open **Set up** on the fixture's firm.
  2. Business profile row: look at **Assign** before choosing; choose **Wholesale**; press **Assign**.
- **Expect**
  - Assign is dead until a profile is chosen. The dropdown lists the **firm's own** catalogue (`GET /api/v1/business-framework/firms/{id}/profiles`), which is why this works with no firm open.
  - "Business profile set to Wholesale." The row re-reads "Assigned: WHOLESALE." and the picker is gone.
- **Leaves:** the firm on the Wholesale profile.

### TC-FIRM-011 — Head office and main warehouse, once

- **Covers:** plan 27.23i
- **Fixture:** `unfinished-firm`
- **Steps**
  1. As the fixture's **Platform admin**, **Set up** on the fixture's firm → Branches and warehouses → **Create head office and main warehouse**.
  2. **(HTTP)** `POST /api/v1/firms/{id}/create-default-branch` again.
  3. Open this firm → Masters → **Branches**, then **Warehouses**.
- **Expect**
  - Step 1: "Created branch HO and warehouse MAIN. Rename them on their own screens." The row reads "1 branch, 1 warehouse". The verdict stays **Cannot post documents yet.** — the books are still shut in this run; that is TC-FIRM-008's step, not this one's.
  - Step 2: "The firm already has a branch and a warehouse; nothing was created.", `already_present: true`.
  - Step 3: `HO` Head Office, default; `MAIN` under it.
- **Leaves:** the firm with a branch and a warehouse.

### TC-FIRM-012 — Profile Assignment, the other way to set a profile

- **Covers:** plan 27.18, 27.19, 27.20
- **Fixture:** `unfinished-firm`
- **Steps**
  1. As the fixture's **Platform admin**, switch into **TEST01** (the screen needs *some* firm open).
  2. Administration → Configuration → Business Profiles → **Profile Assignment**.
  3. Select the fixture's firm, open it, choose **Retail**, save. Re-open the row.
- **Expect**
  - Step 2: a grid of **every** firm, not only TEST01 — the screen names the firm in the URL rather than reading `X-Firm-ID`.
  - Step 3: saved against the fixture's firm, not TEST01; re-opening shows Retail. The **Business profile** dropdown is populated — empty, or "The database is temporarily unavailable", means no firm is open.
- **Data**
  ```sql
  select p.code from fx_<suffix>_f.firm_business_profiles a
  join   fx_<suffix>_f.business_profiles p on p.id = a.business_profile_id
  where  a.is_deleted = false;
  ```
  `RETAIL`, in the fixture firm's own store. TEST01's own assignment is still `WHOLESALE`.
- **Leaves:** the firm on the Retail profile.

### TC-FIRM-013 — Masters need no books; posting does

- **Covers:** plan 27.24, 27.25
- **Fixture:** `unfinished-firm`
- **Steps**
  1. As the fixture's **Platform admin**, open the fixture's firm. Masters → **Customers** → New: code `C1`, name `Before books`, type Business, currency INR. Save.
  2. **(HTTP)** `POST /api/v1/receipts` with `X-Firm-ID` of the fixture's firm: `{"party_id": "<C1's id>", "settlement_date": "<today>", "amount": "100.00", "method": "CASH"}`.
- **Expect**
  - Step 1: saves. Masters do not need the books.
  - Step 2: **422**, "No ledger account is configured for CASH. Set the firm's control accounts before posting this document." The posting service refuses rather than guesses — the design working, not a broken firm.
- **Leaves:** a customer `C1` in the fixture's firm; no receipt.

### TC-FIRM-014 — What "finished" looks like

- **Covers:** plan 27.26
- **Fixture:** `ready-firm`
- **Steps:** sign in as the fixture's **Platform admin** → Administration → Firms → the fixture's firm → **Set up**.
- **Expect:** **Finished. Every step is done.** — "24 accounts, 1 financial year, 12 periods, all 24 control accounts mapped, and a period open today"; Assigned: WHOLESALE; 1 tax system, 8 profiles, 6 rules; 1 country; 1 branch, 1 warehouse; **2 members**. No buttons. The contrast with TC-FIRM-007 is the point.
- **Leaves:** the firm, unchanged.

### TC-FIRM-015 — Control accounts: held once something has posted

- **Covers:** plan 27.23j
- **Fixture:** `ready-firm`
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Finance → **Control Accounts**.
  2. Hover the lock on **Accounts receivable**.
  3. On **Rounding**, press **Change**. Open the account picker; look at **Save** before choosing. Choose `4000 Sales`, Save. Then change it back to `4900 Rounding`.
  4. **(HTTP)** `PUT /api/v1/finance/control-accounts/ACCOUNTS_RECEIVABLE` with `{"ledger_account_id": "<any other ASSET account>"}`.
  5. Sign in as the fixture's **Viewer** → Finance → Control Accounts.
- **Expect**
  - Step 1: 24 rows, one per posting purpose, each with the account it posts to and the classifications it may use. **Accounts receivable** and **Cash** show a lock and **1 posted** with no Change — the fixture's receipt posted one line to each. Every other row offers **Change**.
  - Step 2: "1 posted line on this account. Re-pointing it would leave two accounts each holding part of one story; post a transfer entry and map a new account from the next period instead."
  - Step 3: the picker lists only **INCOME and EXPENSE** accounts — what Rounding may post to. Save is dead until a *different* account is chosen. The notice reads "Rounding posts to 4000 Sales.", then "Rounding posts to 4900 Rounding."
  - Step 4: **422**, "Accounts receivable has 1 posted line on 1100 Trade Receivables. Re-pointing it would leave two accounts each holding part of one story; post a transfer entry and map the new account from the next period instead."
  - Step 5: the tab is there and read-only — **no Change, no Map**. The server agrees: a `PUT` as the viewer is **403**.
- **Data**
  ```sql
  select purpose, ledger_account_id, updated_at from fx_<suffix>_r.firm_control_accounts
  where  purpose in ('ACCOUNTS_RECEIVABLE', 'CASH', 'ROUNDING');
  ```
- **Leaves:** the firm, with Rounding back where it was.

### TC-FIRM-016 — A firm administrator cannot reach firms at all

- **Covers:** plan 27.21, 27.22, 27.23a (the 403 half), 27.26a
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin** → **Administration**.
  2. **(HTTP)** As that user: `GET /api/v1/firms`, `POST /api/v1/firms` (any body), `GET /api/v1/firms/{TEST01's id}/readiness`, `POST /api/v1/firms/{TEST01's id}/open-books`.
- **Expect**
  - Step 1: **no Firms** tab and **no Business Profiles** group, so no setup panel. `FIRM_VIEW` and `PLATFORM_VIEW` are platform codes no firm role can hold.
  - Step 2: **403** for all four. No permission code can grant them. What they would show, a firm administrator reads as their own Finance → Chart of Accounts and Financial Years.
- **Leaves:** a firm admin user.

---

## Custom fields — how a profile reaches a record

A definition applies to a record when it targets the record's entity type
**and** is either unscoped or scoped to the firm's business profile. **NULL
means every profile, not none.** `docs/BUSINESS_PROFILE_FRAMEWORK.md`, "How a
firm resolves its attributes", is the reference.

**Only a platform administrator writes definitions and rules** — a firm
administrator is refused `/business-framework/attribute-definitions` with 403
— and both screens live in a firm's store, so they need a firm open. Cases
here define as the fixture's **Platform admin** inside the fixture's firm, and
enter records as whichever account the case names.

**Every case runs in `ready-firm`'s own store**, because they make fields
mandatory and change the firm's profile. In TEST01 that would break every
other case that saves a customer or a product.

> **The product form is not the customer form.** A customer, vendor, branch or
> warehouse form offers every field that *applies*. The product form offers
> only fields a **Mandatory Attributes** rule names for the product's
> category — mandatory or not — and no Attributes tab at all when there is
> none. So a product field needs a rule before it can be seen. Three plan rows
> assumed otherwise; see *Known defects* at the end of this section.

### TC-FIELD-001 — Unscoped applies everywhere; scoped to another profile, nowhere here

- **Covers:** plan 27.27, 27.28, 27.29, 27.30
- **Fixture:** `ready-firm`
- **Steps**
  1. Sign in as the fixture's **Platform admin**; switch into the fixture's firm. Administration → Configuration → Business Profiles → **Dynamic Attributes**.
  2. **New**: code `SHELF_NOTE`, name `Shelf note`, TEXT, entity type `PRODUCT`, business profile **blank**. Save.
  3. **New**: code `PHARMA_NOTE`, name `Pharma note`, TEXT, entity type `PRODUCT`, business profile **Pharmacy**. Save.
  4. **(HTTP)** `GET /api/v1/business-framework/attribute-definitions/applicable?entity_type=PRODUCT` with the fixture firm's `X-Firm-ID`.
  5. Mandatory Attributes → **New**: category `FXAMB`, attribute `Shelf note`, mandatory **off**, profile blank. Save. Then Masters → **Products** → New → category **Fixture Ambient** → **Attributes** tab.
- **Expect**
  - Step 1: the definitions in *this firm's* store — the seeded ones (Batch Number, Expiry Date, IMEI …) — each showing its entity type and the profile it is narrowed to.
  - Steps 2–3: both save.
  - Step 4: `definitions` includes **SHELF_NOTE** and **not** PHARMA_NOTE. Scoping is what stops one industry's field appearing everywhere.
  - Step 5: an **Attributes** tab with a **Shelf note** box. Before the rule, a product in that category had no Attributes tab at all.
- **Leaves:** two definitions and one optional rule in the fixture firm.

### TC-FIELD-002 — A mandatory definition reaches every category

- **Covers:** plan 27.31
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: `BIN_CODE`, `Bin code`, TEXT, `PRODUCT`, profile blank, **mandatory on**. Save.
  2. **(HTTP)** `POST /api/v1/products` with `X-Firm-ID`: `{"code": "NOBIN", "name": "No bin", "product_type": "STOCK_ITEM", "category_id": "<FXAMB's id>"}`.
  3. The same with `"attributes": [{"attribute_definition_id": "<BIN_CODE's id>", "value": "A-1"}]` and code `BIN1`.
- **Expect**
  - Step 2: **422**, "Required attributes are missing.", naming BIN_CODE's id in `missing_attribute_definition_ids`. The flag on the definition applies to **every** category it reaches — blunt, and the one with a history.
  - Step 3: saves.
  - On the desktop this cannot be done at all: see defect **D-27-2**.
- **Leaves:** a mandatory definition and one product in the fixture firm. Any later product in this firm needs a bin code.

### TC-FIELD-003 — A rule makes a field mandatory for one category only

- **Covers:** plan 27.32
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: `COLD_CHAIN_ID`, `Cold chain id`, TEXT, `PRODUCT`, profile blank, mandatory **off**.
  2. Mandatory Attributes → **New**: profile **Wholesale**, category `FXCHL`, attribute `Cold chain id`, **mandatory on**.
  3. Products → New, category **Fixture Chilled**, code `CH1`, leave Cold chain id empty, Save. Fill it, Save.
  4. Products → New, category **Fixture Ambient**, code `AM1`, Save.
- **Expect**
  - Step 3: the Attributes tab shows **Cold chain id** as required; empty is refused on the form ("Required business attributes are missing."); filled, it saves.
  - Step 4: saves — no Attributes tab, nothing asked. Other categories are untouched.
- **Data**
  ```sql
  select r.category_code, d.code, r.is_mandatory
  from   fx_<suffix>_r.category_attribute_rules r
  join   fx_<suffix>_r.attribute_definitions d on d.id = r.attribute_definition_id
  where  r.is_deleted = false;
  ```
- **Leaves:** a definition, a rule and two products in the fixture firm.

### TC-FIELD-004 — A rule naming a field this firm cannot see enforces nothing on the server

- **Covers:** plan 27.33
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: `RX_CLASS`, `Rx class`, TEXT, `PRODUCT`, profile **Pharmacy**.
  2. Mandatory Attributes → New: profile **Wholesale**, category `FXAMB`, attribute `Rx class`, mandatory **on**. Save.
  3. **(HTTP)** `POST /api/v1/products`: code `RX0`, category FXAMB, no attributes.
  4. **(HTTP)** `GET /api/v1/products/metadata?category_id=<FXAMB's id>`.
- **Expect**
  - Step 2: accepted — not an error.
  - Step 3: **saves**. The server intersects the rules with what applies to this firm, and a Pharmacy field does not.
  - Step 4: **fails today** — `required_attribute_definition_ids` lists RX_CLASS. The form reads that list, so on the desktop no FXAMB product can be saved in this firm: see defect **D-27-3**.
- **Leaves:** a definition, a rule and one product in the fixture firm. Retire the rule to make FXAMB usable on the desktop again.

### TC-FIELD-005 — Changing the firm's profile hides a field and keeps its value

- **Covers:** plan 27.34, 27.35
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm: Dynamic Attributes → New `WS_GRADE`, `Wholesale grade`, TEXT, `PRODUCT`, profile **Wholesale**. Mandatory Attributes → New: profile **Wholesale**, category `FXAMB`, `Wholesale grade`, mandatory **off**.
  2. Products → New, category Fixture Ambient, code `GR1`, Wholesale grade `A`. Save.
  3. Set Up on the firm (from Platform) or Profile Assignment: change the firm to **Retail**. Open `GR1` again.
  4. Change the firm back to **Wholesale**. Open `GR1` again.
- **Expect**
  - Step 3: the **Attributes tab is gone** and nothing warned you. The value is still stored (below). This is `docs/BACKLOG.md` §16.
  - Step 4: the field and its value `A` are back. Nothing was lost; it stopped being *read*.
- **Data**
  ```sql
  select d.code, v.value_text from fx_<suffix>_r.product_attribute_values v
  join   fx_<suffix>_r.attribute_definitions d on d.id = v.attribute_definition_id
  join   fx_<suffix>_r.products p on p.id = v.product_id
  where  p.code = 'GR1';
  ```
  `WS_GRADE | A` under both profiles.
- **Leaves:** the fixture firm back on Wholesale, with one more product.

### TC-FIELD-006 — Changing a definition's data type strands its values

- **Covers:** plan 27.36
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, create `LOT_NOTE`, TEXT, `PRODUCT`, profile blank, and an optional rule for it on `FXAMB`. Create product `LN1` in Fixture Ambient with Lot note `abc`.
  2. Edit `LOT_NOTE` and change its data type to **NUMBER**. Save.
- **Expect:** accepted, **with no warning**. The stored value stays where it was: `value_text = 'abc'`, `value_number` empty, beside a definition that now says NUMBER. Record this as expected-but-wrong — it is §16's first lifecycle guard. *(Driven: `GET /api/v1/products/{id}` still returns the row with `value_text: "abc"`. What the product form shows for it was not checked.)*
- **Data:** the query from TC-FIELD-005 with `p.code = 'LN1'`, plus `value_number`.
- **Leaves:** a definition now NUMBER, with a text value stranded.

### TC-FIELD-007 — A customer carries a custom field, and an edit leaves it alone

- **Covers:** plan 27.36a, 27.36b
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: entity type `CUSTOMER`, code `DRUG_LICENCE_NO`, name `Drug licence no`, TEXT, mandatory **off**.
  2. Sign in as the fixture's **Firm admin** → Masters → Customers → New.
  3. Fill the General tab (code `DLC`, name `Licence Holder`), then **Custom fields**: `DL-4471`. Save. Reopen.
  4. Edit the phone on the General tab (`+919800000001`), Save, reopen Custom fields.
- **Expect**
  - Step 2: a **Custom fields** tab with one box, **Drug licence no**.
  - Step 3: the value is there. **(HTTP)** `GET /api/v1/customers/{id}`: `attributes` carries one row with `value_text: "DL-4471"`.
  - Step 4: the licence is still there. A form sends `attributes` only once it has read the definitions, and an update that omits them leaves them alone.
- **Data**
  ```sql
  select v.value_text, v.updated_at from fx_<suffix>_r.customer_attribute_values v
  join   fx_<suffix>_r.customers c on c.id = v.customer_id where c.code = 'DLC';
  ```
- **Leaves:** a definition and a customer in the fixture firm.

### TC-FIELD-008 — A mandatory customer field is refused on the form and on the server

- **Covers:** plan 27.36c
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, create `DRUG_LICENCE_NO` for `CUSTOMER` as in TC-FIELD-007, with **mandatory on**.
  2. As the fixture's **Firm admin**: Customers → New, fill General, leave the licence empty, Save.
  3. **(HTTP)** `POST /api/v1/customers` with `code`, `name`, `customer_type: "BUSINESS"`, `currency_code: "INR"` and no attributes.
- **Expect**
  - Step 2: refused on the form, **"Drug licence no is required."** Nothing sent.
  - Step 3: **422**, "Required attributes are missing."
- **Leaves:** a mandatory customer definition in the fixture firm. Every later customer there needs a licence.

### TC-FIELD-009 — A vendor field belongs to vendors only

- **Covers:** plan 27.36d
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: entity type `VENDOR`, `SUPPLIER_TIER`, `Supplier tier`, NUMBER.
  2. As the fixture's **Firm admin**: Masters → Vendors → New (or Edit one) → **Custom fields**: `2`. Save, reopen.
  3. Customers → New: look at Custom fields.
  4. **(HTTP)** `POST /api/v1/customers` carrying `"attributes": [{"attribute_definition_id": "<SUPPLIER_TIER's id>", "value": "2"}]`.
- **Expect**
  - Step 2: one numeric box, Supplier tier; `2` after reopening.
  - Step 3: not offered.
  - Step 4: **422**, "One or more attributes do not apply to this record."
- **Leaves:** a vendor definition and a vendor in the fixture firm.

### TC-FIELD-010 — Branches and warehouses carry their own fields

- **Covers:** plan 27.36d2
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: entity type `BRANCH`, `FSSAI_LICENCE`, TEXT. And another: entity type `WAREHOUSE`, `DOCK_COUNT`, NUMBER.
  2. As the fixture's **Firm admin**: Masters → Branches → Edit `HO`; Masters → Warehouses → Edit `MAIN`.
- **Expect:** a **Custom fields** heading at the foot of each dialog with **its own** box only — FSSAI licence on the branch, Dock count on the warehouse. Type a value, Save, reopen: it is there. The branch is **still the default** — saving the dialog does not clear what it does not show.
- **Data:** `fx_<suffix>_r.branch_attribute_values`, `fx_<suffix>_r.warehouse_attribute_values`.
- **Leaves:** two definitions and two values in the fixture firm.

### TC-FIELD-011 — A field with fixed choices

- **Covers:** plan 27.36d3
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: `PRODUCT`, `STORAGE_TEMPERATURE`, `Storage temperature`, TEXT, **Allowed values** `Ambient, Chilled, Frozen`. Then Mandatory Attributes → New: category `FXAMB`, Storage temperature, mandatory **off**.
  2. Products → New, category Fixture Ambient, code `PEAS`, Attributes → Storage temperature.
  3. Choose **Frozen**, Save, reopen.
  4. **(HTTP)** `PUT /api/v1/products/{PEAS id}` with `code`, `name`, `product_type`, `category_id` and `"attributes": [{"attribute_definition_id": "<id>", "value": "Cold"}]`.
  5. Edit the definition: remove `Frozen`. Reopen `PEAS`; then change its name and Save.
  6. Edit the definition: set the data type to NUMBER with the values still filled. Save.
- **Expect**
  - Step 2: a **dropdown** of the three, not a text box.
  - Step 3: Frozen is selected.
  - Step 4: **422**, "Attribute STORAGE_TEMPERATURE must be one of: Ambient, Chilled, Frozen."
  - Step 5: Frozen still shows, selectable. **The save fails today**: the server refuses the unchanged value with "must be one of: Ambient, Chilled" — see defect **D-27-4**. The plan expected it to save unchanged.
  - Step 6: **422**, "Only a TEXT attribute can carry allowed values."
- **Leaves:** a definition, a rule and a product in the fixture firm.

### TC-FIELD-012 — Reading a firm's fields needs the firm, and nothing else

- **Covers:** plan 27.36e
- **Fixture:** `ready-firm`
- **Steps (HTTP)** — as the fixture's **Firm admin**:
  1. `GET /api/v1/business-framework/attribute-definitions/applicable?entity_type=CUSTOMER` with `X-Firm-ID` of the fixture's firm.
  2. The same without `X-Firm-ID`.
  3. `POST /api/v1/business-framework/attribute-definitions` with any body, with `X-Firm-ID`.
- **Expect**
  1. **200**: `entity_type`, `definitions` (what this firm's profile allows) and `mandatory_ids`. Membership is the whole gate — the forms of anybody who can open a customer need it.
  2. **403**, "Select a firm to read its custom fields."
  3. **403**. Reading the fields a form offers is not writing the catalogue.
- **Leaves:** nothing.

### TC-FIELD-013 — A unit is shared by the store; its custom-field values are per firm

- **Covers:** plan 27.36d4
- **Fixture:** `shared-pair`
- **Touches the shared store.** A UOM is one row for every firm in `firm_shared`, MEDI01 and FOOD01 included. The case writes a *value* (per firm, TESTSH1's own) and one definition, which every firm in the store will see — delete it at the end.
- **Steps**
  1. Sign in as the fixture's **Platform admin**, switch into **TESTSH1**, Dynamic Attributes → New: entity type `UOM`, code `<SUFFIX>_PACK_NOTE` (upper case), TEXT.
  2. **(HTTP)** As the fixture's **TESTSH1 admin**, `GET /api/v1/uom-framework/uoms?page_size=100` and pick a unit, e.g. `BAG`. `PUT /api/v1/uom-framework/uoms/{id}` with only `{"attributes": [{"attribute_definition_id": "<id>", "value": "TESTSH1 note"}]}`.
  3. **(HTTP)** As the fixture's **TESTSH2 admin**, list the units and find the same id.
  4. Delete the definition (Dynamic Attributes, as the platform admin).
- **Expect**
  - Step 2: **200**; the unit's `attributes` carries "TESTSH1 note". The update is partial — nothing else about the unit changes.
  - Step 3: the **same unit**, with `attributes` **empty**. The unit is one row; the values are per firm.
  - No desktop form shows UOM custom fields yet.
- **Data**
  ```sql
  select firm_id, uom_id, value_text from firm_shared.uom_attribute_values
  where  value_text = 'TESTSH1 note';
  ```
  One row, carrying TESTSH1's firm id.
- **Leaves:** one stored value for TESTSH1 (harmless once the definition is gone).

### TC-FIELD-014 — The shared store has one custom-field catalogue

- **Covers:** plan 27.37
- **Fixture:** `shared-pair`
- **Touches the shared store**, deliberately — it is the case. Delete the definition at the end.
- **Steps**
  1. Sign in as the fixture's **Platform admin**, switch into **TESTSH1**, Dynamic Attributes → New: `CUSTOMER`, code `<SUFFIX>_SHARED_CHECK`, TEXT.
  2. Switch into **TESTSH2** → Dynamic Attributes.
  3. Delete it.
- **Expect:** step 2 — **it is there.** `attribute_definitions` carries no `firm_id`, so every firm in `firm_shared` — TESTSH1, TESTSH2, MEDI01 and FOOD01 — edits one set. A firm in its own schema, like `ready-firm`'s, does not have this. It is the reason `docs/BACKLOG.md` §16 exists.
- **Leaves:** nothing, once deleted.

### Known defects found while writing these cases

Recorded for the owner, **not fixed** — this pass changes documents only.

- **D-27-1 — The product form never offers a field that merely applies.** `ProductService._category_attribute_ids` builds the form's field list from `category_attribute_rules` alone; customers, vendors, branches and warehouses use `/attribute-definitions/applicable`. An unscoped PRODUCT definition with no rule is offered on no product. Plan 27.30 expected it to appear.
- **D-27-2 — A mandatory PRODUCT definition blocks every product on the desktop.** The server refuses a product without it ("Required attributes are missing.") while the form, per D-27-1, has no box to fill. Plan 27.31.
- **D-27-3 — An "inert" rule is not inert on the desktop.** `mandatory_ids` in `AttributeService` intersects rules with what applies; `_category_attribute_ids` does not, so `/products/metadata` lists a rule naming another profile's field as *required*. The form then refuses an empty box, and a filled one is refused by the server as "do not apply" — no product in that category can be saved from the desktop. Plan 27.33 said this is not an error. Two implementations of one question; they disagree.
- **D-27-4 — A value removed from a field's allowed list cannot be saved back.** `_coerce` validates every value sent, changed or not, so editing anything else on a product that still holds a retired choice is refused — if the form resends it, which it appears to. Plan 27.36d3 expected it to save unchanged.

---

## Adding the next section

1. List what each row needs to exist before it starts — that is the fixture.
2. Add the fixture to `backend/scripts/test_fixture.py`, built from the API, composing the existing blocks where it can.
3. **Run the fixture and drive every expectation against the backend** before writing it down; take sidebar and tab lists from `ModuleVisibility`, not from the permission table.
4. Give each case a stable `TC-AREA-NNN` id and the six parts above. IDs do not change when cases are added, which plan section numbers did.
5. Replace the section in `MANUAL_UI_TEST_PLAN.md` with a pointer and a row → case map, so there is one version and not two.
