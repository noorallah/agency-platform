# Users, roles, job templates and hiring

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-09-25 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## A firm administrator creating users

`FIRM_ADMIN` holds `USER_CREATE`, `USER_UPDATE`, `ROLE_ASSIGN` and `ROLE_VIEW`
— everything running a firm's people needs — and not `FIRM_VIEW`, a platform
code. The New-user gate used to demand it, so the one role whose job is
running a firm's people was refused New and Edit.

Where a person also works in another firm, their **profile** is a platform
administrator's to manage; a firm administrator still decides what they do in
their own firm, through **Roles by firm**.

### TC-USER-001 — New and Edit are a firm administrator's

- **Preconditions:** A firm administrator of QA01, and a QA01 user given two roles picked by hand.
- **Steps**
  1. Sign in as the prepared **Firm admin** → Administration → **Users**.
  2. Select **Manual Hire (qa)** — in QA01 only — → **Edit**.
- **Expect:** **New** and **Edit** offered; the edit form opens normally, writable.
### TC-USER-002 — Somebody who also works elsewhere opens read-only, and says why

- **Preconditions:** The platform administrator, a firm administrator of QA01, a user who is a member of QA01 and QA02, and a user in QA02 only.
- **Steps**
  1. As the prepared **Firm admin**, Users → select **Shared Member (qa)** → **Edit**.
  2. Double-click the row; then the context menu's **Edit**.
- **Expect:** all three open the record **read-only**, never silently: the subtitle reads "… also works in another firm, so their profile is managed by a platform administrator. Use Roles by firm to set what they do in yours." The refusal is about writing; the row is still one somebody meant to look at, so it opens.
### TC-USER-003 — New starts in the firm that is open

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. As the prepared **Firm admin**, Users → **New**. Look at **Firms** before typing anything; open its list.
  2. Name `In Firm qa`, email `qa.infirm@qa.test`, a 12-character password → Save.
- **Expect**
  - Step 1: **QA01 already ticked** — the firm open in the switcher — and the list offers the firms *you* belong to (`/api/v1/me/firms`; `/api/v1/firms` is platform-only and answers a firm admin 403). The form used to open empty and then silently remove the membership the save had just made.
  - Step 2: created, in QA01, in the grid at once.
### TC-USER-004 — Creating somebody in no firm

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. As the prepared **Firm admin**, Users → **New**: name `No Firm qa`, email `qa.nofirm@qa.test`, password; **clear** the Firms box; no job, no roles → Save.
  2. Users → **Add existing user** → type `qa.nofirm`.
  3. New again: `qa.nofirm2@qa.test`, Firms cleared, and this time pick a role under Roles in this firm → Save. Then look them up as in step 2.
- **Expect**
  - Step 1: created, in **no** firm — allowed and deliberate — and **not** in the grid.
  - Step 2: found, not marked as already a member.
  - Step 3: the form says "Somebody in no firm cannot be given roles here, because roles are held per firm. Save them without roles, then use Add existing user to bring them into this firm and set what they do." — **and no account was created**: the lookup finds no `qa.nofirm2`. Clear Roles and press Save; it saves. Fixed 2026-09-16; see defect **D-20-1**.
  - *Step 1 failed on 2026-09-15 ("User not found." with the user created anyway) and was fixed in #402. Driven on the API: a firm admin's create lands the user in QA01, clearing the firms leaves none, and the lookup then finds them with `already_a_member: false`. Step 3's order — create, clear firms, then refuse — is read from `saveAssignments`, not seen on screen.*
### TC-USER-005 — A platform administrator's New form

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps:** sign in as the prepared **Platform admin** → Administration → Users → **New**; look at Firms and open its list.
- **Expect:** Firms is **empty**, not prefilled — a platform administrator has no firm of their own, and quietly using whichever one the switcher shows would be a surprise. The list offers **every** firm (`/api/v1/firms`). Same field, a different source.
### TC-USER-006 — A firm outside your reach is refused by name

- **Preconditions:** The platform administrator, a firm administrator of QA01, a user who is a member of QA01 and QA02, and a user in QA02 only.
- **Steps (HTTP)** — as the prepared firm admin, `X-Firm-ID` QA01: `PUT /api/v1/users/{Shared Member's id}/firms` with `{"assignments": [{"firm_id": "11111111-1111-1111-1111-111111111111", "is_primary": false, "is_active": true}]}`.
- **Expect:** **422**, "You can only assign firms you administer." Refused, not silently dropped. Any id that is not QA01's gives it — the reach check runs before the firm-exists check.
### TC-USER-007 — A firm administrator's membership write merges

- **Preconditions:** The platform administrator, a firm administrator of QA01, a user who is a member of QA01 and QA02, and a user in QA02 only.
- **Steps**
  1. **(HTTP)** As the prepared firm admin: `PUT /api/v1/users/{Shared Member's id}/firms` naming **QA01 only**: `{"assignments": [{"firm_id": "<QA01 id>", "is_primary": false, "is_active": true}]}`.
  2. Sign in as the prepared **Platform admin** → Users → Shared Member (or `GET /api/v1/users/{id}/firms`).
- **Expect**
  - Step 1: **200** — naming only your own firm is legitimate.
  - Step 2: **both** memberships, QA02 still primary. The endpoint replaces for a platform caller and **merges** for a scoped one: memberships outside the caller's reach are carried through untouched, or a firm administrator correcting their own firm would silently remove that person from every other firm. The screen refuses this edit anyway (TC-USER-002); the merge protects the API from any other client.
### TC-USER-008 — A firm administrator does not move somebody's primary firm

- **Preconditions:** The platform administrator, a firm administrator of QA01, a user who is a member of QA01 and QA02, and a user in QA02 only. (Shared Member's primary is **QA02**, which QA01's admin cannot see.)
- **Steps**
  1. **(HTTP)** As the prepared firm admin: the `PUT` from TC-USER-007 with `"is_primary": true` on QA01.
  2. Re-read as the prepared platform admin.
- **Expect:** **200**, and the primary is **still QA02** — the flag was **ignored, not refused**. It is one flag across every firm somebody belongs to, held by `UQ_user_firms_active_primary`; a caller who can see only some of those firms would either collide with a primary they cannot see or quietly demote it. The exception is somebody with no primary at all, who gets one.
### TC-USER-009 — A Counter Sales hire gets the till and not the ledger

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. As the prepared **Firm admin**, Users → New: name, `qa.counter@qa.test`, password, **Job template** Counter Sales, Roles left alone → Save. (`docs/USER_ADMINISTRATION_GUIDE.md` §3 end to end.)
  2. Sign in as them and read the sidebar; open Finance.
- **Expect:** **Sales** and **Inventory** offered; **Finance** offered holding **exactly Receipts and Payments**; no Administration. None of Chart of Accounts, Control Accounts, Cost Centres, Profit Centres, Journal Entries, Ledgers, Trial Balance, Profit & Loss, Balance Sheet or Refunds.
  - **Two opposite failures:** no Finance at all means the module gate was reverted and the empty-sidebar bug is back; Finance *with the ledger in it* means the tabs lost their own codes and the module gate is doing the work alone.

## Hiring somebody who already has an account

`list_users` is scoped to the caller's own members, so a firm administrator
could not find — or learn the existence of — somebody who already works
elsewhere. `GET /api/v1/users/lookup` is a deliberate, narrow opening for that
one job, and **one route answers two callers differently**:

| | A firm administrator | A platform administrator |
| --- | --- | --- |
| Term | at least **3** characters | any, including none |
| Results | at most **10**, no paging | the ordinary paging |
| Members of the firm | listed, marked **Already in this firm** | **left out** — they are in the grid |
| Firms named | never | never |

### TC-LOOK-001 — Looking somebody up

- **Preconditions:** The platform administrator, a firm administrator of QA01, and a cashier who belongs to QA02 only. (Outsider works in QA02 alone.)
- **Steps**
  1. Sign in as the prepared **Firm admin** → Administration → Users → **Add existing user**, with no row selected.
  2. Type `t0`.
  3. Type `qa.outs`; then clear and type `Outsider (qa)`.
  4. Type `qa`.
  5. Type `zzqq-nobody`.
- **Expect**
  - Step 1: a search box. Offered with nothing selected — the person is not in the grid, which is the point.
  - Step 2: nothing searched: "Type at least 3 characters to look somebody up."
  - Step 3: Outsider, found by **email** and then by **name**. A result shows the name, the email, and **nothing else** — no firm is named anywhere on it.
  - Step 4: Outsider, and **Fixture Firm Admin (qa)** marked **Already in this firm** with Add disabled.
  - Step 5: "Nobody matches. They may not have an account yet — use New."
### TC-LOOK-002 — Adding them, with a job

- **Preconditions:** The platform administrator, a firm administrator of QA01, and a cashier who belongs to QA02 only.
- **Steps:** as the prepared **Firm admin**, Add existing user → `qa.outs` → pick Outsider → **Job template** Counter Sales → Add.
- **Expect:** "Outsider (qa) was added to this firm." They appear in QA01's grid. The Job template field's helper reads "Optional. You can set their roles afterwards."
### TC-LOOK-003 — Their profile is not yours; their roles here are

- **Preconditions:** As *outsider*, with the QA02 cashier already added to QA01 as *Counter Sales*. (Outsider is already in QA01 as Counter Sales.)
- **Steps**
  1. As the prepared **Firm admin**, select **Outsider (qa)** → **Edit**; double-click the row; the context menu's Edit.
  2. Select them → **Apply job template** → Warehouse → Apply. Then **Roles by firm**.
  3. Sign in as the prepared **Platform admin** → Users → Outsider → Edit.
- **Expect**
  - Step 1: all three open **read-only**, the subtitle saying they also work in another firm, so their profile is managed by a platform administrator, and Roles by firm is what to use.
  - Step 2: both work. Roles by firm shows **one section, QA01** — not QA02, though they work there: the dialog offers only firms you hold `USER_CREATE` in.
  - Step 3: **editable** — correct, not a hole. A platform administrator sees every firm, so nothing is hidden from them, and they are exactly who step 1's message points to.
### TC-LOOK-004 — Adding somebody tells you nothing about their other firms

- **Preconditions:** As *outsider*, with the QA02 cashier already added to QA01 as *Counter Sales*.
- **Steps (HTTP)**
  1. As the prepared firm admin (`X-Firm-ID` QA01): `GET /api/v1/users/{Outsider's id}/firms`.
  2. As the prepared platform admin: the same.
  3. As the platform admin: `GET /api/v1/users/{id}/firms/{QA02 id}/roles` and `.../{QA01 id}/roles`.
- **Expect**
  1. **Only QA01.** It returned every membership until 2026-09-06, on a route gated only by `ROLE_VIEW`.
  2. Both firms, QA02 primary.
  3. QA02 still exactly `CASHIER`; QA01 `BILLING_EXECUTIVE` and `CASHIER` from Counter Sales. Adding them to QA01 touched nothing in QA02.
### TC-LOOK-005 — Reaching across firms is not reading your own people

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only). (and `firm-admin` (two runs, or any two))
- **Steps**
  1. Sign in as the `sales-executive` preparation's **Seller**; look for Administration → Users.
  2. **(HTTP)** As the seller with `X-Firm-ID` QA01: `GET /api/v1/users/lookup?q=fixtures`.
  3. **(HTTP)** As the `firm-admin` preparation's firm admin: `GET /api/v1/users/lookup?q=`, then `?q=qa.test&page=2&page_size=2`.
- **Expect**
  1. No Administration at all, so no Add existing user.
  2. **403** — the lookup needs `USER_CREATE`, deliberately not `USER_VIEW`.
  3. **422**, "Type at least 3 characters to look somebody up." — an empty term is the shortest of all. Page 2: **empty**, and a plain `?q=qa.test` returns **10** however many match: a firm caller gets "is this them?", not "who works here?".
### TC-LOOK-006 — A platform administrator gets the directory

- **Preconditions:** The platform administrator, a firm administrator of QA01, and a cashier who belongs to QA02 only.
- **Steps**
  1. Sign in as the prepared **Platform admin**, switch into **QA01** → Users → **Add existing user**.
  2. Type `e`; clear the box.
  3. Type `qa.outs`, pick Outsider, Add, close. Open Add existing user again and type `qa`.
  4. **(HTTP)** As the platform admin with `X-Firm-ID` QA01: `GET /api/v1/users/lookup?q=&page=1&page_size=2`.
- **Expect**
  - Step 1: the dialog **opens already listing** everyone with an account who is not in QA01, no typing. Helper: "Leave blank to list everyone not yet in this firm." QA01's own people are **not** listed, and no platform administrator is — the prepared firm admin and platform admin are both absent.
  - Step 2: filtered on one character; the three-character rule is a firm caller's. Clearing brings the full list back.
  - Step 3: Outsider is added, and **absent** the second time. A firm caller's lookup *flags* a member; a platform caller's directory *excludes* them.
  - Step 4: two rows and a `pagination` block whose `total_records` is everybody not in QA01.
### TC-LOOK-007 — User-Firm Assignments is a platform administrator's tab

- **Preconditions:** The platform administrator and a firm administrator of QA01. ((a firm admin and a platform admin))
- **Steps:** open Administration as the prepared **Firm admin**; then as its **Platform admin**, with no firm and then with QA01 selected.
- **Expect:** the firm admin sees Users, Roles & Permissions and User Templates — **no User-Firm Assignments**; Users → Edit → Firms and Add existing user are their ways to the same thing. The platform admin sees **User-Firm Assignments**, with the Firm filter, either way. A tab-level `requiresPlatformAdmin`, because a platform administrator passes code checks by designation.
---

## Hiring like an existing person

The other half of templates, and the more common one: an administrator usually
has a person in mind rather than a written-down job. **Hire like this person**
copies roles and firm memberships and nothing that belongs to the person.

The dialog checks only that the boxes are filled and the email has an `@`; the
**server** applies the password policy — twelve characters, upper, lower,
digit, symbol.

### TC-HIRE-001 — The dialog, and what it refuses

- **Preconditions:** A firm administrator of QA01, and a QA01 salesperson to hire somebody like.
- **Steps**
  1. Sign in as the prepared **Firm admin** → Administration → Users → select **Source Seller (qa)** → **Hire like this person**.
  2. Press **Create** with the form empty.
  3. Name `Clone Test`, email `not-an-email`, any password → Create.
  4. Email `qa.clone@qa.test`, password `short` → Create.
- **Expect**
  - Step 1: "Hire like this person": "The new user gets the same roles and firms as Source Seller (qa), and none of their personal details, password or history. You can edit their roles afterwards like any other user." Boxes **Full name**, **Email**, **Initial password** ("They must change it when they first sign in.").
  - Step 2: under each box — "Give the new person a name.", "An email is required.", "An initial password is required." Nothing created.
  - Step 3: "That is not an email." under Email.
  - Step 4: the **server** refuses, shown **on the dialog** in red: "Password does not meet the configured policy." with its reasons — must contain at least 12 characters, an uppercase letter, a digit, a symbol. Every box keeps what was typed.
### TC-HIRE-002 — A clone gets the access, not the person

- **Preconditions:** A firm administrator of QA01, and a QA01 salesperson to hire somebody like.
- **Steps**
  1. As the prepared **Firm admin**, Hire like this person on **Source Seller (qa)**: `Clone Test qa`, `qa.clone@qa.test`, `Welcome@12345` → Create.
  2. Open the new user.
  3. Sign out; sign in as `qa.clone@qa.test` / `Welcome@12345`. Set the new password to `CloneTest@2026x`.
- **Expect**
  - Step 1: "Clone Test qa was created with the same access as Source Seller (qa), and must change their password on first sign-in."
  - Step 2: `SALES_EXECUTIVE` in QA01 and QA01 as their firm (primary) — the same as the source. **Blank** mobile, employee code, department, joining date; **Also applies here** reads None.
  - Step 3: a **Set a new password** screen instead of the application — Current password, New password, Confirm new password, **Update password** — and nothing else opens until it is done. Afterwards: the source's access and no Administration. A password somebody else chose is not a password.
### TC-HIRE-003 — A clone is a starting point, not a link

- **Preconditions:** A firm administrator of QA01, and a QA01 salesperson to hire somebody like.
- **Steps**
  1. As the prepared **Firm admin**, Hire like this person on **Source Seller (qa)**: `Clone Test Two qa`, `qa.clone2@qa.test`, `Welcome@12345` → Create. A second clone, with its own address: TC-HIRE-002 has already taken `qa.clone@qa.test`.
  2. Edit the clone: add `CUSTOMER_SUPPORT` under Roles in this firm → Save & Close.
  3. Open **Source Seller (qa)**; close without saving.
- **Expect:** the clone holds `SALES_EXECUTIVE` and `CUSTOMER_SUPPORT`; the source still holds exactly `SALES_EXECUTIVE`.
### TC-HIRE-004 — Copying access is granting access

- **Preconditions:** A firm administrator of QA01, and a QA01 salesperson to hire somebody like.
- **Steps**
  1. Sign in as the prepared **Source** (a `SALES_EXECUTIVE`) and look for the users grid.
  2. **(HTTP)** As the source, with `X-Firm-ID` of QA01: `POST /api/v1/users/{their own id}/clone` with `{"email": "qa.x@qa.test", "full_name": "x", "password": "Welcome@12345"}`.
- **Expect**
  - Step 1: **Administration is not offered**, so there is no Hire like this person.
  - Step 2: **403**. The action needs `ROLE_ASSIGN` — somebody who may open accounts but not grant access must not be able to copy access instead.
---

## User templates — hiring by naming the job

A template is a named bundle of roles. Eleven are seeded and offered to every
firm; a firm may write its own and may not edit the platform's. Applying one is
an ordinary role write — nothing on the user records which template they came
from.

The eleven: Accounts (`ACCOUNTANT`), Counter Sales (`BILLING_EXECUTIVE`,
`CASHIER`), Customer Support, Field Sales (`SALES_EXECUTIVE`), Firm
Administrator, Firm Manager, Purchase Manager, Purchasing, Read Only
(`VIEWER`), Sales Manager and Warehouse (`INVENTORY_MANAGER`). QA01 also
lists templates earlier runs wrote, and any template a platform administrator
offered to every firm; cases count only the eleven.

### TC-TMPL-001 — The platform's templates are listed, and locked

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. Sign in as the prepared **Firm admin** → Administration → **User Templates**.
  2. Select **Counter Sales**; look at **Edit** and **Delete**; open it.
  3. **(HTTP)** `PATCH /api/v1/user-templates/{Counter Sales id}` with `{"name": "x"}`.
- **Expect**
  - Step 1: the **eleven** above with Origin **Platform**, each naming its roles — Counter Sales shows `BILLING_EXECUTIVE, CASHIER`.
  - Step 2: Edit and Delete **disabled**; the dialog subtitle reads "… · Provided by the platform". It is offered to every firm, so no one firm may change it.
  - Step 3: **422**, "Platform templates cannot be edited."
### TC-TMPL-002 — A firm's own template, and an edit that keeps its roles

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. As the prepared **Firm admin**, User Templates → **New**: Template code `qa-night-counter`, Job name `Night Counter`, Roles `CASHIER` and `BILLING_EXECUTIVE`, Offered on → Save.
  2. Edit it; change only the **name** to `Night Counter renamed` → Save; reopen.
- **Expect**
  - Step 1: created; Origin **This firm**; subtitle "… · This firm's own".
  - Step 2: still `BILLING_EXECUTIVE, CASHIER`. An edit that says nothing about the bundle must not empty it — `role_ids` replaces the bundle when sent, and the form does not send it unchanged.
### TC-TMPL-003 — Hiring into a job in one step

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. As the prepared **Firm admin**, Administration → Users → **New**: name `Job Hire qa`, email `qa.jobhire@qa.test`, a 12-character password, **Job template** Counter Sales. Save.
  2. New again: `Hand Hire qa`, `qa.handhire@qa.test`, Job template **blank**, Roles in this firm `CUSTOMER_SUPPORT` and `VIEWER`. Save.
- **Expect**
  - Step 1: created **and** holding `CASHIER` and `BILLING_EXECUTIVE` — one step, no second visit to the grid.
  - Step 2: exactly those two roles. The template field is optional.
### TC-TMPL-004 — When a job is named, the job decides

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. As the prepared **Firm admin**, Users → **New**. Pick `ACCOUNTANT` under Roles in this firm; then choose the **Read Only** job; then clear the job.
  2. Choose Read Only again and save (name, `qa.readonly@qa.test`, password).
  3. Edit that user.
- **Expect**
  - Step 1: the helper text under **Roles in this firm** ends "Ignored when a job template is named above." Choosing the job **clears** ACCOUNTANT and **locks** the chips; clearing it unlocks them, empty.
  - Step 2: the user holds only `VIEWER`.
  - Step 3: **no Job template field** — it is create-only. A template is where somebody starts, and Apply job template on the grid is how to re-apply one.
### TC-TMPL-005 — Applying a job replaces what somebody holds

- **Preconditions:** A firm administrator of QA01, and a QA01 user given two roles picked by hand.
- **Steps**
  1. As the prepared **Firm admin**, Users → select **Manual Hire (qa)** → **Apply job template**.
  2. Type `inventory` in **Search jobs**; clear it.
  3. Choose **Counter Sales** → Apply.
- **Expect**
  - Step 1: dialog "Apply a job template": "Whatever Manual Hire (qa) holds now is replaced by the job's roles. You can edit them afterwards like any other user." One line per active job with its roles beneath; **Apply disabled** until a job is chosen.
  - Step 2: only **Warehouse** remains (the search covers name, code, description and role). A filter that hides the chosen job clears the choice.
  - Step 3: their QA01 roles become exactly `BILLING_EXECUTIVE` and `CASHIER` — `SALES_EXECUTIVE` and `CUSTOMER_SUPPORT` are gone.
### TC-TMPL-006 — A firm administrator's template writes the firm tier only

- **Preconditions:** The platform administrator, a firm administrator of QA01, and a user holding one platform-wide role and one QA01 role.
- **Steps**
  1. As the prepared **Firm admin**, Users → **Two Tier Hire (qa)** → Apply job template → **Counter Sales** → Apply.
  2. Sign in as the prepared **Platform admin**, open the same user.
- **Expect:** **Roles in every firm** still `VIEWER`, `CUSTOMER_SUPPORT`; **Roles in specific firms** now `QA01: BILLING_EXECUTIVE · CASHIER` (was ACCOUNTANT, INVENTORY_MANAGER). A template overwrites the tier its caller writes and never touches the other.
### TC-TMPL-007 — A platform administrator's template writes the global tier only

- **Preconditions:** The platform administrator, a firm administrator of QA01, and a user holding one platform-wide role and one QA01 role.
- **Steps**
  1. As the prepared **Platform admin**, Users → **Two Tier Hire (qa)** → Apply job template → **Warehouse** → Apply.
  2. Reopen the user.
- **Expect:** **Roles in every firm** becomes exactly `INVENTORY_MANAGER` (Warehouse carries that one role) — VIEWER and CUSTOMER_SUPPORT are gone — while **Roles in specific firms** still reads `QA01: ACCOUNTANT · INVENTORY_MANAGER`, untouched. The desktop never names a firm on this call for a platform administrator. *(The plan said "four roles, a different four"; Warehouse has one role, so it is three.)*
### TC-TMPL-008 — After a template, somebody is an ordinary user

- **Preconditions:** The platform administrator, a firm administrator of QA01, and a user holding one platform-wide role and one QA01 role.
- **Steps**
  1. As the prepared **Firm admin**, edit **Two Tier Hire (qa)**: under **Roles in this firm** remove `ACCOUNTANT`, add `CASHIER` → Save & Close → reopen.
- **Expect:** `INVENTORY_MANAGER` and `CASHIER`. **Also applies here** (read-only, lower in the Security section) shows the global tier, `CUSTOMER_SUPPORT` and `VIEWER`, which a firm administrator cannot change. Nothing on the user records a template.
### TC-TMPL-009 — Somebody without role codes has no templates to see

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps:** sign in as the prepared **Seller**; look for Administration.
- **Expect:** **Administration is not offered at all**. `SALES_EXECUTIVE` holds `CUSTOMER_VIEW`, `SALES_VIEW`, `SALES_QUOTATION_CREATE`, `SALES_ORDER_CREATE`, `SALES_INVOICE_CREATE`, `TERRITORY_VIEW` — no `ROLE_VIEW`. **(HTTP)** `GET /api/v1/user-templates` with `X-Firm-ID` of QA01 → **403**.
### TC-TMPL-010 — Retiring a template is a decision about future hires

- **Preconditions:** A firm administrator of QA01, a QA01 job template of its own, and somebody hired into it.
- **Steps**
  1. As the prepared **Firm admin**, User Templates → select the prepared **Job template** → **Delete** (confirm).
  2. Users → open **Night Counter Hire (qa)**.
  3. Users → New → open the Job template list.
- **Expect**
  - Step 1: the row leaves the grid (a soft delete; there is no button called Retire).
  - Step 2: still `BILLING_EXECUTIVE` and `CASHIER`.
  - Step 3: the retired template is **not offered**.
### TC-TMPL-011 — A template cannot bundle a platform role

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps (HTTP)** — as the platform administrator, `GET /api/v1/roles?search=PLATFORM_ADMIN` to find its id (a firm admin's own role list never shows it). Then, as the prepared firm admin, with `X-Firm-ID` of QA01: `POST /api/v1/user-templates` `{"code": "qa-bad", "name": "Bad", "role_ids": ["<that id>"]}`.
- **Expect:** **422**, "A template cannot bundle platform or cross-firm roles." Nothing created. That role carries every permission code; a template able to name it would be a second door onto the same room.
---

## Templates from the platform side — which firms a job is offered to

A platform caller's scope resolves to no firm, and for a template no firm used
to mean **every** firm — so a job written while setting up one firm was
published to all of them. **Offered to** names the firm; blank still means
every firm, deliberately.
### TC-TMPL-012 — A platform administrator chooses who a job is offered to

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps:** sign in as the prepared **Platform admin** (on Platform) → Administration → **User Templates** → **New**.
- **Expect:** the tab opens with no firm selected — it carries `requiresFirm: false`, since a platform operator has no firm of their own. The General section has an **Offered to** picker: one chip per firm reading `CODE · Name`, helper "Leave blank to offer this job to every firm." A firm administrator's form has no such field. It is create-only.
### TC-TMPL-013 — A job offered to one firm is not offered to another

- **Preconditions:** The platform administrator and a firm administrator of QA01.
- **Steps**
  1. As the prepared **Platform admin**, User Templates → New: code `qa-t2-night`, name `T2 Night`, **Offered to** the `QA02 · …` chip, Roles `CASHIER` → Save.
  2. Sign in as the prepared **Firm admin** (QA01) → User Templates.
  3. As the platform admin again, delete `qa-t2-night`.
- **Expect**
  - Step 1: created. Origin reads **One firm**; the subtitle reads "`qa-t2-night — T2 Night` · Offered to one firm". **Every firm** would mean the firm never left the form; **This firm** is the wording #383 fixed — either means step 2 fails too.
  - Step 2: `qa-t2-night` is **not** listed.
### TC-TMPL-014 — A job offered to every firm is the platform's to change

- **Preconditions:** The platform administrator and a firm administrator of QA01.
- **Steps**
  1. As the prepared **Platform admin**, New: `qa-every-night`, `Every Night`, Roles `CASHIER`, **Offered to blank** → Save. Edit its name → Save.
  2. Sign in as the prepared **Firm admin** → User Templates → select `qa-every-night`.
  3. **(HTTP)** As the firm admin: `PATCH /api/v1/user-templates/{id}` `{"name": "y"}`, then `DELETE /api/v1/user-templates/{id}`.
  4. As the platform admin, **Delete** it.
- **Expect**
  - Step 1: Origin **Every firm**, and the platform admin may still edit it.
  - Step 2: listed, Origin **Every firm**, subtitle "… · Offered to every firm". **Edit** and **Delete** disabled.
  - Step 3: **422** on both, "This template is offered to every firm, so only a platform administrator can change or retire it."
  - Step 4: gone from every firm's list.
### TC-TMPL-015 — A firm administrator cannot write a template for another firm

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps (HTTP)** — as the prepared firm admin with `X-Firm-ID` of QA01: `POST /api/v1/user-templates` `{"code": "qa-x", "name": "X", "firm_id": "11111111-1111-1111-1111-111111111111", "role_ids": ["<CASHIER's id>"]}`.
- **Expect:** **422**, "You can only act within your own firm." Nothing created. Refused, not silently redirected.
  - The `firm_id` need not be a real firm: for a firm caller any firm but their own takes the same branch, and a firm administrator cannot read `/api/v1/firms` to find one anyway.
---

## Roles in two tiers — every firm, and one firm

A **global** role (`user_roles.firm_id IS NULL`) applies in every firm the
person belongs to; a **firm** role applies in that firm only. One writer per
tier: a platform administrator's user form writes the global set (**Roles in
every firm**); **Roles by firm** on the Users grid writes one firm's set, for
either administrator. A firm administrator's form writes their own firm's set
(**Roles in this firm**) and cannot remove a global grant.

The defect behind the screen: the single Roles box wrote through a path that
replaced every row regardless of firm, so a platform administrator pressing
Save without changing anything collapsed each firm's separate roles into one
global grant.

### TC-RTIER-001 — The platform form writes the global set; Roles by firm writes one firm

- **Preconditions:** The platform administrator, a firm administrator of QA01, a user who is a member of QA01 and QA02, and a user in QA02 only. (Shared Member is in QA02 and QA01 with no roles.)
- **Steps**
  1. Sign in as the prepared **Platform admin** → Users → edit **Shared Member (qa)**. Read the roles field.
  2. Set it to `VIEWER` → Save & Close.
  3. Select the row → **Roles by firm**.
  4. Give QA01 `SALES_MANAGER` → that section's **Save**.
  5. Give QA02 `CASHIER` → its Save.
- **Expect**
  - Step 1: labelled **Roles in every firm**, saying it applies in every firm, including ones added later.
  - Step 3: a section per firm they belong to — QA01 and QA02, no others. `VIEWER` once at the top under **Applies in every firm**, greyed and unclickable. Each Save is enabled only once its own firm changed.
  - Step 5: QA02 saved; QA01 still shows `SALES_MANAGER` — one Save, one firm.
### TC-RTIER-002 — Saving the form unchanged keeps every firm's own roles

- **Preconditions:** As *shared-member*, with the QA01/QA02 member holding a role in each tier. (VIEWER everywhere, SALES_MANAGER in QA01, CASHIER in QA02.)
- **Steps**
  1. As the prepared **Platform admin**, edit **Shared Member (qa)** → **Save** without changing anything.
  2. **Roles by firm**.
- **Expect:** QA01 still SALES_MANAGER, QA02 still CASHIER, VIEWER still under Applies in every firm. **The regression case**: before the fix both firms ended up holding every role, globally. One writer per tier, so neither save can touch the other's rows.
### TC-RTIER-003 — Each administrator sees the tier they cannot write

- **Preconditions:** As *shared-member*, with the QA01/QA02 member holding a role in each tier.
- **Steps**
  1. As the prepared **Firm admin** (QA01), Users → open **Shared Member (qa)** (it opens read-only, TC-USER-002) and look under Security.
  2. As the prepared **Platform admin**, edit the same person.
  3. As the platform admin, Roles by firm → clear QA02's CASHIER → Save; reopen the form.
- **Expect**
  - Step 1: **Also applies here** shows `VIEWER`, read-only. A global grant applies in their firm, so hiding it made the form report less than the person could do.
  - Step 2: no Also applies here — the roles field already *is* the global set. Instead **Roles in specific firms**, read-only: `QA01: SALES_MANAGER · QA02: CASHIER`.
  - Step 3: only `QA01: SALES_MANAGER`. A firm holding nothing is left out rather than shown empty.
### TC-RTIER-004 — A firm administrator's Roles by firm is their firm only, and cannot clear a global grant

- **Preconditions:** As *shared-member*, with the QA01/QA02 member holding a role in each tier.
- **Steps**
  1. As the prepared **Firm admin**, Users → select **Shared Member (qa)** → **Roles by firm**.
  2. Remove `SALES_MANAGER` → Save.
- **Expect**
  - Step 1: **one section, QA01**, with chips that respond. QA02 is not listed — its Save would be refused by name. `VIEWER` shown greyed under Applies in every firm, not clearable. This dialog used to read the platform-only firm list, answer 403 and show a firm administrator no firm at all.
  - Step 2: removed in QA01; VIEWER survives. A firm administrator may not undo a platform grant.
### TC-RTIER-005 — A platform administrator's New writes the global tier only

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps**
  1. As the prepared **Platform admin**, Users → **New**; read the Security section.
  2. Create `qa.global1@qa.test`: Firms QA01 and QA02, Roles in every firm `CUSTOMER_SUPPORT` → Save. Select them → **Roles by firm**.
  3. Create `qa.global2@qa.test` in QA01 with **Job template** Read Only → Save → Roles by firm.
- **Expect**
  - Step 1: **Job template**, **Roles in every firm**, and nothing that names a firm. **Apply roles to** is gone.
  - Step 2: both firm sections **empty**; CUSTOMER_SUPPORT under **Applies in every firm**.
  - Step 3: VIEWER under Applies in every firm — the job's roles land in the same tier the Roles field writes.
### TC-RTIER-006 — The firm switcher has no say in where a role lands

- **Preconditions:** As *shared-member*, with the QA01/QA02 member holding a role in each tier.
- **Steps**
  1. As the prepared **Platform admin**, switch into **QA01**. Users → edit **Shared Member (qa)**.
  2. Add `CUSTOMER_SUPPORT` to the roles field → Save → Roles by firm.
- **Expect**
  - Step 1: **one** roles field, **Roles in every firm**, plus the read-only **Roles in specific firms** listing both firms — QA01 included. No second column. The helper says a role in one firm only is set under Roles by firm.
  - Step 2: CUSTOMER_SUPPORT under **Applies in every firm**; no firm section changed.
### TC-RTIER-007 — A firm administrator's form

- **Preconditions:** The platform administrator, a firm administrator of QA01, and a user holding one platform-wide role and one QA01 role. (global VIEWER and CUSTOMER_SUPPORT; QA01 ACCOUNTANT and INVENTORY_MANAGER.)
- **Steps**
  1. As the prepared **Firm admin**, Users → edit **Two Tier Hire (qa)**.
  2. Press **Roles by firm** in the dialog footer; close it. Close the form, open it in **view**, press it again.
- **Expect**
  - Step 1: the roles field labelled **Roles in this firm** (ACCOUNTANT, INVENTORY_MANAGER) and **Also applies here** showing CUSTOMER_SUPPORT and VIEWER read-only. Nothing names a firm.
  - Step 2: the per-firm editor opens without closing the form, from edit and from view.
### TC-RTIER-008 — The server holds a firm administrator to their firm, and a role to a membership

- **Preconditions:** The platform administrator, a firm administrator of QA01, a user who is a member of QA01 and QA02, and a user in QA02 only.
- **Steps (HTTP)**
  1. As the prepared firm admin (`X-Firm-ID` QA01): `PUT /api/v1/users/{Shared Member}/firms/{QA02 id}/roles` `{"ids": ["<CASHIER id>"]}`.
  2. `GET /api/v1/users/{Shared Member}/firms/{QA02 id}/roles`, then the same for QA01.
  3. As the prepared platform admin: `PUT /api/v1/users/{QA02 Only}/firms/{QA01 id}/roles` `{"ids": ["<CASHIER id>"]}`.
  4. As the firm admin: `GET /api/v1/users/{QA02 Only}/firms`.
- **Expect**
  1. **422**, "You can only set roles in firms you administer."
  2. **422**, "You can only read roles in firms you administer." — the read used to answer for any firm. QA01: **200**.
  3. **422**, "Add the user to this firm before giving them a role in it." A role there would sit in the table and stay out of the token.
  4. **200** and an **empty** list — a firm administrator learns nothing about which firms somebody outside theirs belongs to. *(Plan 20a.8k's screen message, "This person belongs to no firm you administer.", needs the Roles by firm dialog open on such a person, and a QA02-only person is not in QA01's grid to open it from; this is the server's half of the same rule.)*
---

## Roles — a firm's own roles and templates

A permission is a capability, a **role** names a set of permissions, a
**template** names a set of roles — and a firm administrator may write their
own roles and templates without anybody writing code.

### TC-ROLE-001 — A firm admin sees the firm's roles and none of the platform's

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. Sign in as the prepared **Firm admin**. Select **QA01** in the firm switcher if it is not already selected.
  2. Sidebar → **Administration** → **Roles & Permissions** → **Roles** tab.
- **Expect**
  - **Twelve rows subtitled *System role*:** `ACCOUNTANT`, `BILLING_EXECUTIVE`, `CASHIER`, `CUSTOMER_SUPPORT`, `FIRM_ADMIN`, `FIRM_MANAGER`, `INVENTORY_MANAGER`, `PURCHASE_EXECUTIVE`, `PURCHASE_MANAGER`, `SALES_EXECUTIVE`, `SALES_MANAGER`, `VIEWER`.
  - **None of the four platform roles:** `PLATFORM_ADMIN`, `SUPPORT_ADMIN`, `LICENSE_ADMIN`, `SYSTEM_AUDITOR`.
  - Rows subtitled *Custom role* may also appear — earlier preparation runs made them. **Do not count those.**
### TC-ROLE-002 — Creating a custom role; the platform's codes are never offered

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. Sign in as the prepared **Firm admin**, QA01 selected.
  2. Administration → Roles & Permissions → Roles → **New**.
  3. **Role code:** `qa-my-role` (your preparation's suffix — codes must be unique in the firm). **Name:** anything.
  4. Scroll to the **Permissions** section **on the same form** — it is not a separate screen.
  5. Search the picker for `FIRM_CREATE`, then `PLATFORM_SETTINGS`, `VOID_INVOICE`, `AUDIT_LOG_VIEW`.
  6. Tick `SALES_VIEW` and `CUSTOMER_VIEW`. **Save.**
- **Expect**
  - Step 5: **none of those four codes is in the list.** The picker offers **167** codes; the 22 platform codes are filtered out of a firm caller's read, not merely refused on save.
  - Step 6: the role is created, subtitled **Custom role**, and offers **Edit** (the System roles do not).
### TC-ROLE-003 — No role may be named `platform_admin`

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. Sign in as the prepared **Firm admin**, QA01 selected.
  2. Roles → **New** → **Role code** `platform_admin`, any name → **Save**.
- **Expect:** refused on the form — **"'platform_admin' is reserved. Choose a different role code."** Nothing is created. The code pattern `^[a-z0-9._-]+$` *permits* that spelling, so the refusal is the service's. Before 2026-09-05 this went through, and a firm administrator who assigned it to themselves signed in as a platform administrator.
- **Also try** `firm_admin`, `cashier` or `system_auditor` — the same named refusal: the designation and all sixteen seeded codes are reserved. **Type them in lower case.** `FIRM_ADMIN` or `Cashier` is refused *earlier*, by the code pattern, with a generic "The request validation failed" — a different refusal for a different reason, and not what this case is checking. (The service's check is case-insensitive as defence in depth, for a role row written by some other route; through this form the pattern means only lower case can reach it.) *(Corrected 2026-09-16 after driving it: the first version of this case said `FIRM_ADMIN` gave the same refusal.)*
### TC-ROLE-004 — A firm admin *holds* `AUDIT_LOG_VIEW` and cannot *grant* it

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps**
  1. Sign in as the prepared **Firm admin**, QA01 selected.
  2. Sidebar → **Settings** → **Audit Logs**.
  3. Administration → Roles & Permissions → Roles → **New** → Permissions → search `AUDIT_LOG_VIEW`. Cancel.
- **Expect**
  - Step 2: **opens**, on QA01's trail.
  - Step 3: **not offered**.
  - That is not a contradiction. `PLATFORM_PERMISSION_CODES` answers "what may a firm administrator not *grant*", a different question from what they may hold. `AUDIT_LOG_VIEW` was granted to `FIRM_ADMIN` directly on 2026-09-06. Confusing the two sets is how a permission's reach gets misjudged.
### TC-ROLE-005 — A template can bundle the firm's own custom role

- **Preconditions:** A firm administrator of QA01, and a custom role *Night Desk* holding exactly SALES_VIEW, CUSTOMER_VIEW, RECEIPT_VIEW and RECEIPT_CREATE.
- **Steps**
  1. Sign in as the prepared **Firm admin**, QA01 selected.
  2. Administration → **User Templates** → **New**.
  3. **Template code** `qa-my-job`, **Job name** anything.
  4. **Roles** → tick the prepared **Custom role** (`Night Desk qa`). **Save.**
- **Expect:** created, **Origin: This firm**. This is the first place the screen *says* the custom role belongs to QA01 — the roles grid only says "Custom role".
### TC-ROLE-006 — Hiring into a template grants exactly its roles

- **Preconditions:** The *Night Desk* custom role, and a QA01 job template that bundles it.
- **Steps**
  1. Sign in as the prepared **Firm admin**, QA01 selected.
  2. Administration → **Users** → **New**.
  3. Full name anything; email `qa.hire@qa.test`; **Initial password** the prepared password (twelve or more characters — the form does not say which rule it refused on if shorter).
  4. **Job template** → the prepared **Job template**. Leave **Roles** empty. Firms as prefilled. **Save.**
  5. Select the new row → **Roles by firm**.
- **Expect:** one section, QA01, holding **only** `Night Desk qa`.
### TC-ROLE-007 — A custom role's codes become exactly those screens

- **Preconditions:** The *Night Desk* custom role, and a QA01 user holding that role and nothing else.
- **Steps**
  1. Sign in as the prepared **Role holder** (no password change is asked for). QA01 is their only firm.
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
### TC-ROLE-008 — Editing a role signs out everyone holding it

- **Preconditions:** The *Night Desk* custom role, and a QA01 user holding that role and nothing else.
- **Steps** — two windows:
  1. **Window A:** sign in as the prepared **Role holder**. Open Finance → Receipts. **Record Receipt** is there.
  2. **Window B:** sign in as the prepared **Firm admin**, QA01 selected. Roles → the prepared **Custom role** → **Edit** → untick **`RECEIPT_CREATE`** → **Save**.
  3. **Window A:** click anything.
  4. Sign back in as the holder. Finance → Receipts.
- **Expect**
  - Step 3: **signed out on that click** — nobody asked them to. Editing a role revokes every holder's tokens.
  - Step 4: the **sidebar is unchanged** (the table in TC-ROLE-007), and on Receipts **Record Receipt is gone**. `RECEIPT_CREATE` gates the button, not the screen.
  - A role is not versioned: editing it changes everybody holding it, immediately.
### TC-ROLE-009 — Deleting a role somebody holds just goes through

- **Preconditions:** The *Night Desk* custom role, and a QA01 user holding that role and nothing else.
- **Steps** — two windows:
  1. **Window A:** sign in as the prepared **Role holder**.
  2. **Window B:** sign in as the prepared **Firm admin**, QA01 selected. Roles → the prepared **Custom role** → **Delete**.
  3. **Window A:** click anything. Then sign back in as the holder.
- **Expect**
  - Step 2: **it deletes.** No refusal, no warning, no count of who holds it. The only guard in `delete_role` is against System roles.
  - Step 3: **signed out** on the click; signed back in, an **empty sidebar** — no module at all — and nothing on screen says why.
  - Recorded as the behaviour, **not a defect**. Whether deleting a held role should refuse, or warn with the count, is an open decision for the owner.
---

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 03-S01 | **Administration → Users** | Offered to any role holding `USER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 03-S02 | **Administration → Roles** | Offered to any role holding `ROLE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 03-S03 | **Administration → Permissions** | Offered to any role holding `PERMISSION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 03-S04 | **Administration → User Templates** | Offered to any role holding `ROLE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 03-S05 | **Administration → User-Firm Assignments** | Offered to the platform administrator only. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
