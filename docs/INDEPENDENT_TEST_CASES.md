# Independent test cases

Pick any case, run it on its own, at any time, in any order. That is the
whole promise, and it is what `docs/MANUAL_UI_TEST_PLAN.md` could not make: its
rows were a chain. 20.1b needed the two-firm user 20.6 creates, 22.1 needed a
cashier nobody had made, 25.10 deletes the role 25.2 makes so 25.9 can never be
run twice, and 24.12 named an account whose password had changed. Picking a row
out of order met a failure that belonged to the plan, not to the product.

**Every numbered section of the plan, 2 to 27, is here.** The plan keeps each
section's heading with a pointer and an old-row → case map, and its Part 1
(bringing the environment up) and Part 4 (known gaps) are unchanged.

**Known defects found while writing the cases** are listed at the end of the
section they belong to — D-2-1, D-8-1, D-11-1, D-20-1 and D-27-1 to D-27-4.
None was fixed in this pass; each is for the owner.

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

### 2. Where a fixture's data lives

Fixtures work in firms of their own — never the four demo firms:

| Firm | Schema | For |
| --- | --- | --- |
| **TEST01** | `test_fixtures` | almost every case |
| **TEST02** | `test_fixtures_2` | cases needing somebody in two firms, or two firms kept apart |
| **TESTSH1**, **TESTSH2** | `firm_shared` | only the cases *about* the shared store; built the first time `shared-pair` runs |
| `<SUFFIX>-U`, `-F`, `-R` | `fx_<suffix>_u` … | the firm-setup and custom-field cases, which need a firm nobody has finished, or a store no other case reads |
| `<SUFFIX>-S`, `-T`, `-G`, `-P`, `-E` | `fx_<suffix>_s` … | selling and pricing, territory and commission, GST compliance, pharmacy batches, electronics serials: cases that change something firm-wide (a price list, a promotion, TCS, a credit policy, a profile) get a store of their own, built afresh each run — **a minute or two**, because it provisions a schema |

The fixture prints which firm and schema it used on its **Tables** line.
The demo firms are never touched, and a table check against those schemas
shows only test data. **TEST01 accumulates** every run's customers, products,
orders and users, so no case counts everything on a screen. The first fixture
run builds TEST01 and TEST02 — create, provision,
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

## Signing in, sessions, and the life of an account

A refusal about the **credential** says only "Invalid email or password." —
for a wrong password and for an unknown address alike, and at the same cost,
so nobody learns which addresses exist. A refusal about the **account's
state** — locked, inactive, expired — names the state and the remedy
(`docs/BACKLOG.md` 18.1, 18.2). Five wrong passwords lock an account for
fifteen minutes.

### TC-SESS-001 — Switching firms reloads every list

- **Covers:** plan 2.2
- **Fixture:** `isolation-pair` — a customer of this run's own in TEST01 and another in TEST02.
- **Steps**
  1. Sign in as the fixture's **Platform admin**; switch into **TEST01** → Masters → Customers; search `<SUFFIX>`.
  2. With the list open, switch to **TEST02**.
- **Expect:** step 1 shows `<SUFFIX>-ONE`; after the switch the list reloads by itself and shows `<SUFFIX>-TWO` — **no row from TEST01 survives**, not even for a moment.
- **Leaves:** unchanged.

### TC-SESS-002 — An idle session refreshes quietly, and a signed-out one leaves nothing behind

- **Covers:** plan 2.4, 2.5
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**; open Masters → Customers. Leave the application idle for **more than 15 minutes** (the access token's lifetime, `AGENCY_JWT_ACCESS_TOKEN_MINUTES`).
  2. Click **Refresh**.
  3. Sign out; press the mouse's Back button or Alt+Left.
- **Expect**
  - Step 2: the list reloads; you are **not** asked to sign in again — the client refreshes once on a 401 and repeats the request.
  - Step 3: the sign-in screen stays; no cached screen is reachable.
- **Leaves:** a firm admin user.

### TC-SESS-003 — Wrong passwords, a lockout, and a lock that counts down

- **Covers:** plan 2.6, 2.7
- **Fixture:** `lock-target`
- **Steps**
  1. On the sign-in screen, try `nobody.<suffix>@fixtures.local` / `Wrong@Password1`.
  2. Try the fixture's **Target** with `Wrong@Password1` **four** times.
  3. A fifth time.
  4. Now the **right** password, `Fixture@2026pw`.
  5. Watch the banner.
- **Expect**
  - Steps 1–2: "Invalid email or password." every time, the unknown address included, and each takes **about as long** as the others (~2 seconds on this machine, measured) — a wrong address and a wrong password must not feel different.
  - Step 3: "This account is locked after too many failed sign-in attempts. You can try again in 15:00." and the clock **counts down** a second at a time.
  - Step 4: refused the same way, with the time left. The lock is checked before the password is.
  - Step 5: at zero, "The lock on this account has lifted. You can sign in now." *(If you cannot wait, TC-SESS-004 lifts it.)*
- **Data (HTTP):** the fifth attempt's refusal is **401** with code `account_locked` and `details.retry_after_seconds` 900 and `locked_until`. Table check: `scripts/sql/check_identity_data.sql` §5 shows the fifth as `locked` and the sixth as `account_locked`.
- **Leaves:** a locked target (for 15 minutes).

### TC-SESS-004 — A firm administrator clears a lock

- **Covers:** plan 2.8, 2.9
- **Fixture:** `lock-target`
- **Steps**
  1. Lock the fixture's **Target** with five wrong passwords (TC-SESS-003 steps 2–3).
  2. Sign in as the fixture's **Firm admin** → Users → Edit **Lock Target (<suffix>)** → tick **Clear login lock (Account Lock)** → Save.
  3. Sign in as the target with `Fixture@2026pw`.
- **Expect:** step 3 signs in at once — the lock cleared and the failed count reset. *(2.9's other way, waiting fifteen minutes, ends the same; TC-SESS-003 step 5 shows it.)*
- **Data (HTTP):** the form sends `PATCH /api/v1/users/{id}` with `{"unlock": true}`.
- **Leaves:** an unlocked target.

### TC-SESS-005 — Inactive and expired accounts are told why

- **Covers:** plan 2.10
- **Fixture:** `lock-target`
- **Steps**
  1. As the fixture's **Firm admin**, Users → Edit the target → untick **Active** → Save. Sign in as the target with the right password; then with `Wrong@Password1`.
  2. Edit again: tick Active, set **Expires at** to yesterday → Save. Sign in with the right password; then a wrong one.
  3. Clear Expires at → Save; sign in.
- **Expect**
  - Step 1, right password: "This account is inactive. Ask an administrator to reactivate it." Login history says `account_unavailable`.
  - Step 2, right password: "This account has expired. Ask an administrator to extend it."
  - Step 3: signs in.
  - **With a wrong password, the plan expected "Invalid email or password."** The server answers the **state** message instead — driven on 2026-09-16 for both states. See defect **D-2-1**; record what you see.
- **Leaves:** the target active, no expiry.

### TC-SESS-006 — A password somebody else set must be changed

- **Covers:** plan 2.11
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Users → New: `<suffix>.newbie@fixtures.local`, password `Welcome@123456`, **Require password change** on, in TEST01 → Save.
  2. Sign in as them. On the change-password screen try new passwords `Short@1`, then `LongEnoughPassw0rd`, then `Newbie-Passw0rd!`.
- **Expect:** the change-password screen and nothing else reachable. `Short@1` refused ("Use at least 12 characters."); `LongEnoughPassw0rd` refused ("Include a symbol."); `Newbie-Passw0rd!` accepted and the app opens.
- **Leaves:** a TEST01 user with their own password.

### TC-SESS-007 — Deleting somebody releases their address; the new account is a new person

- **Covers:** plan 2.13
- **Fixture:** `lock-target`
- **Steps**
  1. As the fixture's **Platform admin**, Users → select the target → **Delete**.
  2. Users → New with the same email, any name and password, no firms or roles → Save.
- **Expect:** step 1 — gone from the grid; Settings → Audit Logs keeps the row. Step 2 — the address is accepted again (soft delete releases it) and the new account has **no** roles and **no** firms.
- **Leaves:** a deleted target and a new, empty account on the same address.

### TC-SESS-008 — Restoring a deleted person as they were

- **Covers:** plan 2.13b, 2.13c
- **Fixture:** `lock-target`
- **Steps**
  1. As the fixture's **Platform admin**, delete the target. Users → **Status** filter → **Deleted** → open them.
  2. **Restore** (dialog footer). Sign in as the target with `Fixture@2026pw`.
  3. Delete the target again; create a **new** account with the same address; Status → Deleted → open the old one → Restore.
- **Expect**
  - Step 1: status **Deleted**, Edit and Delete dead, View opens.
  - Step 2: back in the grid with TEST01 and SALES_EXECUTIVE; the old password works.
  - Step 3: refused — "Another live account now holds this email address. Delete that account first if this is the one to keep." Restore before re-onboarding, not after.
- **Leaves:** a deleted target and a live account on its address (after step 3).

### TC-SESS-009 — Deleted people are a platform administrator's; inactive ones anybody's

- **Covers:** plan 2.13d (both rows)
- **Fixture:** `lock-target`
- **Steps**
  1. As the fixture's **Firm admin**, Users → open the **Status** filter.
  2. **(HTTP)** As the firm admin, `GET /api/v1/users?deleted_only=true&search=<suffix>`.
  3. Edit the target: untick **Active** → Save. Status → **Inactive**.
  4. As the fixture's **Platform admin**: Status → **Inactive**; then also pick the firm **TEST01**.
- **Expect**
  - Step 1: Active and Inactive, **no Deleted**; and no **Restore** anywhere. A deleted person's memberships still place them in a firm, and a firm's grid must not list them.
  - Step 2: **live** rows only — the flag is ignored for a firm caller.
  - Step 3: the target, and nobody active.
  - Step 4: the switched-off people from every firm, the target among them and no deleted ones; with TEST01 as well, only TEST01's inactive people.
- **Leaves:** an inactive target.

### TC-SESS-010 — Who may not be deleted

- **Covers:** plan 2.14
- **Fixture:** `shared-member` (for the shared person) and `platform-admin-member` (for a platform administrator to aim at)
- **Steps**
  1. As the `shared-member` fixture's **Firm admin**, Users → select **Shared Member (<suffix>)** → Delete.
  2. **(HTTP)** As any platform administrator, `DELETE /api/v1/users/{id of the platform-admin-member fixture's admin}`.
- **Expect**
  - Step 1: refused — "This person also works in another firm, so their profile is managed by a platform administrator. You can still set their roles and job template in your own firm."
  - Step 2: **422**, "Platform administrator users cannot be deleted."
- **Leaves:** unchanged.

### TC-SESS-011 — Setting somebody else's password

- **Covers:** plan 2.15, 2.16, 2.17
- **Fixture:** `lock-target`
- **Steps**
  1. Lock the target (five wrong passwords).
  2. As the fixture's **Platform admin** → Users → open the target → **Reset password** (dialog footer) → `Temp-Passw0rd!!`, "Require a new password" on → Save. Sign in as the target with it.
  3. Reset again to `Handover-Passw0rd!` with "Require a new password" **off**; sign in with it.
  4. As the platform admin, open **your own** row → Reset password.
  5. As the fixture's **Firm admin**, open the target.
- **Expect**
  - Step 2: the lock is gone — they sign in at once and land on the change-password screen. Any other window of theirs is signed out.
  - Step 3: the app opens straight away: a handover, the password theirs to keep.
  - Step 4: refused — "Change your own password from My profile, where the current one is asked for."
  - Step 5: **no Reset password** in the footer. **(HTTP)** `POST /api/v1/users/{id}/password` as the firm admin → **403**.
- **Leaves:** the target on `Handover-Passw0rd!`.

### Known defects found while writing these cases

- **D-2-1 — An inactive or expired account names its state to a wrong password.** Driven: a wrong password on an inactive account answers "This account is inactive…", and on an expired one "This account has expired…", both with their state codes. Plan 2.10 expected "Invalid email or password." for a wrong password, which is what the locked refusal's reasoning and CLAUDE.md's "a refusal about the credential does not [name the state]" suggest. The unit tests pin the state messages with the **right** password only. Either the plan or the code is wrong; the owner's call, since the 18.1/18.2 decision was about the person holding the right password.

---

## Firm isolation — one firm never sees another's data

Three ways a firm's data can live: in the shared store beside other firms
(`SHARED`, schema `firm_shared`), in a schema of its own (`SCHEMA`), or in a
database of its own. The shared store is the one where isolation depends on
every query filtering by firm, so it is the one to check hardest.

### TC-ISO-001 — Two firms in one schema do not see each other's customers

- **Covers:** plan 3.1, 3.2 (shared half)
- **Fixture:** `shared-isolation-pair` — `<SUFFIX>-SHONE` in TESTSH1 and `<SUFFIX>-SHTWO` in TESTSH2, **both in `firm_shared`**.
- **Steps**
  1. Sign in as the fixture's **Platform admin** → switch into **TESTSH1** → Masters → Customers → search `<SUFFIX>`.
  2. Switch to **TESTSH2**; search again. Then **MEDI01** and **FOOD01**, which share the same schema; then **TEST01**.
- **Expect:** TESTSH1 shows only `-SHONE`; TESTSH2 only `-SHTWO`; MEDI01, FOOD01 and TEST01 show **neither**. **If a TESTSH1 customer appears in TESTSH2, stop and report it** — the two share one schema, so nothing but the firm filter keeps them apart.
- **Data**
  ```sql
  select c.code, f.code as firm from firm_shared.customers c
  join platform.firms f on f.id = c.firm_id
  where c.code like '<SUFFIX>-SH%';
  ```
  Two rows, one per firm, in one table.
- **Leaves:** a customer in each shared test firm.

### TC-ISO-002 — Two firms in their own schemas, and a name that cannot cross

- **Covers:** plan 3.2 (dedicated half), 3.3, 3.3b
- **Fixture:** `isolation-pair` — `<SUFFIX>-ONE` (Isolation One) in TEST01, `<SUFFIX>-TWO` (Isolation Two) in TEST02.
- **Steps**
  1. As the fixture's **Platform admin** in **TEST01**, Customers → search `Isolation One <suffix>`.
  2. Switch to **TEST02**; search the same name, then `<SUFFIX>`.
- **Expect**
  - Step 1: `<SUFFIX>-ONE`.
  - Step 2: the name finds **nothing**; `<SUFFIX>` finds only `<SUFFIX>-TWO`. A name from another firm's store cannot appear.
  - *Document numbers are the weaker check the plan's 3.3 started from: they **restart per firm**, so TEST02 may have an invoice with the same number as one of TEST01's — it must carry TEST02's own customer. The name is the real check.*
- **Leaves:** unchanged.

### TC-ISO-003 — Reports read the firm you are in

- **Covers:** plan 3.4
- **Fixture:** `invoiced` — a sale of this run's own in TEST01.
- **Steps**
  1. Sign in as the fixture's **Firm admin** (TEST01) → Reports → Operational Reports → **Sales order register**; find the fixture's order (customer **Fixture Buyer <suffix>**).
  2. Sign in as any platform administrator (e.g. `platform-admin` fixture) → switch into **TEST02** → the same report.
- **Expect:** step 1 lists the fixture's order; step 2 does **not** — TEST02's register holds only TEST02's orders, and reads "Nothing to report" if it has none.
- **Leaves:** unchanged.

### TC-ISO-004 — Naming a firm you do not belong to is refused, not answered empty

- **Covers:** plan 3.5, 3.6
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin** and look for any way to TEST02: the firm switcher, Ctrl+K, a report.
  2. **(HTTP)** As the firm admin, `GET /api/v1/customers` with `X-Firm-ID` of **TEST02**.
- **Expect**
  - Step 1: none. The switcher lists TEST01 alone.
  - Step 2: **403**, "You do not have permission to perform this action." — **not** an empty list, which would look like "no data" and hide the hole.
- **Leaves:** a firm admin user.

---

## Customers

A customer carries more than any one screen shows — addresses and contacts
that are replaced as a whole, a credit limit, payment terms, a standing
discount, a segment. **An update that dumps its whole write model turns an
omission into an instruction**, and it shipped twice here; these cases check
that an edit changes what it names and nothing else.

### TC-CUST-001 — Changing one field leaves everything else alone

- **Covers:** plan 4.1, 4.2
- **Fixture:** `customer-master` — `<SUFFIX>-CM`, Master Check: one billing address, one contact, credit limit 50,000, 30 days, 7.5% standing discount, segment `<SUFFIX>-RET`, phone +919800000100.
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Masters → Customers → open `<SUFFIX>-CM` → Edit.
  2. Change only the **phone** to `+919800000199` → Save → reopen.
- **Expect:** the phone is new; the address (12 Fixture Street, City <suffix>), the contact (Fixture Contact), **credit limit 50,000**, **payment terms 30**, **standing discount 7.5%** and the segment are all **unchanged**, and the outstanding balance is unchanged (0.00). Check each one.
- **Data**
  ```sql
  select phone, credit_limit, payment_terms_days, default_discount_percent,
         customer_group_id, current_outstanding, version
  from   test_fixtures.customers where code = '<SUFFIX>-CM';
  select count(*) from test_fixtures.customer_addresses a
  join   test_fixtures.customers c on c.id = a.customer_id
  where  c.code = '<SUFFIX>-CM' and a.is_deleted = false;
  ```
  One address, `version` up by one. *(Driven over HTTP: a PUT naming only the four required fields and the phone leaves all of these as they were.)*
- **Leaves:** the customer with a new phone number.

### TC-CUST-002 — The place picker loads each rung from the one above

- **Covers:** plan 4.3, 4.4
- **Fixture:** `customer-master` — TEST01's store holds India and, under it, this run's own **State <suffix> → District <suffix> → City <suffix>**.
- **Steps**
  1. As the fixture's **Firm admin**, Customers → New: code `<SUFFIX>-GEO`, name `Place Check <suffix>`, type Business, currency INR. In the address: country **India**, then **State <suffix>**, then **District <suffix>**, then **City <suffix>**; line 1 and PIN filled.
  2. Save; reopen.
- **Expect**
  - Step 1: each rung loads **immediately** after the one above is chosen — choosing the country fills the states at once, not after a second click. *(It shipped loading from the value the parent had not rebuilt yet.)*
  - Step 2: the place is still chosen, and the text fields agree with it: city `City <suffix>`, state `State <suffix>`, country `IN`. The ids are the truth; the text is derived from them.
- **Leaves:** a second customer.

### TC-CUST-003 — The credit policy: readable by whoever it warns, writable by one permission

- **Covers:** plan 4.5
- **Fixture:** `customer-master`
- **Steps**
  1. As the fixture's **Firm admin**, Customers → toolbar **Settings**.
  2. Sign in as the fixture's **Seller** (`SALES_EXECUTIVE`) → Customers → Settings.
  3. **(HTTP)** As the seller, `PUT /api/v1/customers/credit-settings` with `{"enforcement": "OFF", "warn_at_percent": "80", "block_at_percent": "100"}`.
- **Expect**
  - Step 1: **Credit policy** — "When a customer reaches their limit" **Warn**, warn at 80, block at 100 (TEST01 has no policy row, so the default applies), editable.
  - Step 2: the dialog **opens read-only**, with "Changing the policy needs the manage customer settings permission." *(The plan said the action is not offered to a salesperson; it is offered on `CUSTOMER_VIEW` on purpose — someone the policy warns should see the rule behind the warning.)*
  - Step 3: **403**.
- **Leaves:** unchanged.

### TC-CUST-004 — A credit limit warns and does not block

- **Covers:** plan 4.6
- **Fixture:** `customer-master`
- **Steps**
  1. As the fixture's **Firm admin**, edit `<SUFFIX>-CM`: credit limit `1` → Save.
  2. Sales Orders → New: customer `<SUFFIX>-CM`, one line `<SUFFIX>-P` quantity 2 at 100 → Create draft → **Approve**.
- **Expect:** a warning names the exposure — "Master Check <suffix> would be at …% of a 1.00 credit limit, leaving … available." — and the order **is approved**. TEST01 is in warn mode (no policy row), so nothing blocks.
- **Data (HTTP):** `GET /api/v1/customers/{id}/credit-status?amount=<order total>` → `status: WARNING`, `would_block: false`.
- **Leaves:** an approved order for 2, and a customer with a limit of 1.

### TC-CUST-005 — Statement and ageing agree with the account

- **Covers:** plan 4.7, 4.8
- **Fixture:** `invoiced-part-paid` — Fixture Buyer <suffix> owes 590 on one invoice and has paid 200 against it.
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Customers → `<SUFFIX>-C` → **Statement** for this financial year.
  2. **Ageing**.
- **Expect**
  - Step 1: opening 0.00; the invoice (debit 590, balance 590), then the receipt (credit 200, balance **390**); closing **390.00** — the customer's current balance. Lines are in date order and the running balance is recomputed, not read off the stored snapshot.
  - Step 2: total outstanding **390.00**, all of it in the 0–29 day bucket; the buckets sum to the total, and the reconciliation line has nothing to explain (no unapplied credits, no charges not billed).
- **Data (HTTP):** `GET /api/v1/customers/{id}/statement?from_date=2026-04-01&to_date=2027-03-31` and `GET /api/v1/customers/ageing`.
- **Leaves:** unchanged.

### TC-CUST-006 — Segments: assigning one, and refusing to delete one in use

- **Covers:** plan 4.9, 4.10
- **Fixture:** `customer-master`
- **Steps**
  1. As the fixture's **Firm admin**, edit `<SUFFIX>-CM` → segment `<SUFFIX>-WHL` (Wholesaler <suffix>) → Save → reopen.
  2. Customers toolbar → **Groups** → **Remove** on `<SUFFIX>-WHL`.
- **Expect**
  - Step 1: the segment holds.
  - Step 2: refused — "1 customer(s) are still in Wholesaler <suffix>. Move them first, or the group would vanish from every list while staying on their records." `ondelete="RESTRICT"` is no guard on a soft-deleted table, so the service refuses.
- **Leaves:** the customer in the Wholesaler segment.

---

## Vendors, products, branches and warehouses

The same rule as customers: an edit changes what it names. Vendors had six
child collections emptied by any edit that did not send them; a branch rename
cleared its street lines, city, default flag and GST registration, and a
warehouse rename its capability flags.

### TC-MAST-001 — A vendor edit keeps all six child collections

- **Covers:** plan 5.1
- **Fixture:** `vendor-master` — `<SUFFIX>-V`, Supply Check: one contact, address, bank account, tax record, attachment and note.
- **Steps:** as the fixture's **Firm admin**, Masters → Vendors → Edit `<SUFFIX>-V` → change only the phone → Save → reopen.
- **Expect:** the contact, address, bank account, tax record, attachment and note are **all still there**.
- **Data (HTTP):** `GET /api/v1/vendors/{id}` → `contacts`, `addresses`, `bank_accounts`, `tax_details`, `attachments`, `notes` one each. *(Driven: a PUT with only code, name and phone leaves all six.)*
- **Leaves:** the vendor with a new phone.

### TC-MAST-002 — Vendor categories and types

- **Covers:** plan 5.2, 5.3
- **Fixture:** `vendor-master`
- **Steps**
  1. As the fixture's **Firm admin**, Masters → **Vendor Categories**; then **Vendor Types**. Add one to each: `<SUFFIX>-CAT2` / `<SUFFIX>-TYP2`.
  2. Edit `<SUFFIX>-V`: category `<SUFFIX>-CAT`, type `<SUFFIX>-TYP` → Save → reopen.
- **Expect**
  - Step 1: both lists load — the fixture's `<SUFFIX>-CAT` and `<SUFFIX>-TYP` are in them — and both accept a new row. *(These returned nothing until the route order was fixed, and until 2026-09-11 the sidebar opened a "coming soon" placeholder — BACKLOG §26.)*
  - Step 2: both held, and the six child collections are still there.
- **Leaves:** a second category and type; the vendor categorised.

### TC-MAST-003 — A product's slots

- **Covers:** plan 5.4
- **Fixture:** `product-master` — `<SUFFIX>-PM`, Slot Check.
- **Steps:** as the fixture's **Firm admin**, Masters → Products → open `<SUFFIX>-PM`.
- **Expect:** category **Shelf <suffix>**; tax profile group **GST_18_LOCAL**; base, inventory and sales units **PIECE**, purchase unit **BOX** — each read as a name, not an id.
- **Leaves:** unchanged.

### TC-MAST-004 — A rename keeps a branch's address, city, GST registration and default flag

- **Covers:** plan 5.6
- **Fixture:** `branch-master` — in **TEST02**: `<SUFFIX>-BR`, Keep Branch, default, GST registered, 1 Keep Street / Keep Nagar, City <suffix>.
- **Steps:** sign in as the fixture's **TEST02 admin** → Masters → Branches → Edit `<SUFFIX>-BR` → rename to `Kept Branch renamed` → Save → reopen.
- **Expect:** both street lines, the city (and its state), **GST registration**, the PAN and **Default** are all unchanged.
- **Leaves:** the branch renamed.

### TC-MAST-005 — A rename keeps a warehouse's capacity and capability flags

- **Covers:** plan 5.7
- **Fixture:** `branch-master` — `<SUFFIX>-WH`, Keep Warehouse, 1000 SQFT, default; on: temperature controlled, cold storage, receiving area, dispatch area, inspection area, loading dock; off: hazardous, returns area, packing area.
- **Steps:** as the fixture's **TEST02 admin**, Masters → Warehouses → Edit `<SUFFIX>-WH` → rename → Save → reopen.
- **Expect:** capacity 1000 SQFT, Default, and **every flag exactly as listed** — the six on still on, the three off still off. *(Until 2026-09-11 a warehouse with no capacity could not be saved at all — BACKLOG §28.)*
- **Leaves:** the warehouse renamed.

### TC-MAST-006 — An import with one bad row imports nothing

- **Covers:** plan 5.8, 5.8b
- **Fixture:** `branch-master` — prints the paths of two files, **Import, clash** (five rows; the fifth reuses `<SUFFIX>-BR`) and **Import, clean** (the first four).
- **Steps**
  1. As the fixture's **TEST02 admin**, Masters → Branches → **Import** → the **clash** file.
  2. Select the refusal text with the mouse; press the copy icon beside it.
  3. Import the **clean** file.
- **Expect**
  - Step 1: **nothing** imported, and the dialog says so. The import stages and commits once.
  - Step 2: the message selects, and the copy icon puts the whole text on the clipboard.
  - Step 3: all four rows go in: `<SUFFIX>-I1` to `-I4`.
- **Data (HTTP):** `POST /api/v1/branches/import` with the clash rows → **409**, "Branch code already exists in this firm.", and a search for `<SUFFIX>-I` then finds none.
- **Leaves:** four imported branches in TEST02.

### TC-MAST-007 — Sample files and exports round-trip

- **Covers:** plan 5.8a, 5.9
- **Fixture:** `branch-master`
- **Steps**
  1. As the fixture's **TEST02 admin**, Branches → Import → **Sample file**; save it. Open it, change the example code `BR_NORTH` to `<SUFFIX>-NORTH` (otherwise a second run meets the first run's branch), save; import it.
  2. Warehouses → Import → Sample file; look at its branch column.
  3. Branches → **Export**; Warehouses → Export. Then Export again and dismiss the save dialog.
- **Expect**
  - Step 1: eleven column headings and one example row; previews as "1 rows ready" and imports. Reopen it: display name, both address lines and the currency are filled (multi-word headings were silently dropped until 2026-09-11 — BACKLOG §31.4).
  - Step 2: the example names a branch **by code**, prefilled with this firm's first branch.
  - Step 3: a save dialog suggesting `branches.csv` / `warehouses.csv`; the notice names the full path; the file holds the grid's rows in the **same columns the importer reads**. Dismissing says no file was saved.
- **Leaves:** one more branch in TEST02; two CSV files where you saved them.

### TC-MAST-008 — A carton barcode finds its product

- **Covers:** plan 5.10
- **Fixture:** `product-master` — `<SUFFIX>-PM` has a **Case** level of 12 pieces with the barcode the fixture printed.
- **Steps:** as the fixture's **Firm admin**, Administration → Configuration → UOM & Packaging → **Packaging Levels** (or Ctrl+K and the screen's name) → product `<SUFFIX>-PM` → type the barcode into "Scan or type a code" → **Look up**.
- **Expect:** resolves to **Slot Check <suffix>**, level **Case**, **12** base units. No scanner needed: a scanner only types the digits and presses Enter.
- **Data (HTTP):** `GET /api/v1/uom-framework/barcode-lookup?code=<barcode>` → `product_code`, `level_name: Case`, `base_quantity: 12`, `matched_field: barcode`.
- **Leaves:** unchanged.

---

## Configuration — numbering, profiles, tax and units

Most of these screens sit under **Administration → Configuration** (a parent
row only expands; the screens are its leaves). **Ctrl+K** opens any screen by
name.

### TC-CONF-001 — Numbering series: who may change one, and a counter nobody types

- **Covers:** plan 6.1, 6.2
- **Fixture:** `firm-admin` and `sales-executive`
- **Steps**
  1. Sign in as the `firm-admin` fixture's **Firm admin** → Administration → Configuration → **Numbering Series**.
  2. Select **SALES_INVOICE_DEFAULT** → Edit → scroll below the **Active** switch. Change the Name, save, reopen.
  3. Press **New series** and look at the same spot.
  4. Sign in as the `sales-executive` fixture's **Seller** and open the same screen.
- **Expect**
  - Step 1: **New series**, **Edit** and **Retire** offered.
  - Step 2: a locked row with a padlock, `Next number: N`, and the reason ("The counter belongs to the server, which advances it under a lock..."); no box to type in. After the rename the next number is unchanged.
  - Step 3: a **Start numbering at** box instead, helper "Usually 1...".
  - Step 4: the list loads, and **none** of the three buttons is offered.
- **Leaves:** a renamed sales invoice series in TEST01.

### TC-CONF-002 — A yearly restart without the year is refused

- **Covers:** plan 6.3
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Numbering Series → **New series**: document type Sales Invoice, code `<SUFFIX>-SI`, name `Check <suffix>`, **Restart numbering each financial year** on, **Include the financial year** off → Save.
  2. Switch Include the financial year on → Save.
- **Expect**
  - Step 1: a warning under the switches says the first document of April would repeat one from March; the save is refused with the server's sentence — "This rule restarts its numbering every financial year, so the number has to include the year -- without it the first document of each new year repeats a number the firm has already issued. …" — and nothing is created.
  - Step 2: created.
- **Leaves:** a second sales invoice series in TEST01 (not the default).

### TC-CONF-003 — Previewing the next number issues nothing

- **Covers:** plan 6.4
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, select **SALES_INVOICE_DEFAULT** → **Preview next**, twice.
- **Expect:** a number matching the pattern — `SI-2026-2027-00000N` — equal to the locked `Next number` and the **same both times**. A preview issues nothing.
- **Data (HTTP):** `GET /api/v1/document-framework/numbering-rules/{id}/preview`, twice → the same string.
- **Leaves:** unchanged.

### TC-CONF-004 — A roadmap feature cannot be switched on

- **Covers:** plan 6.5
- **Fixture:** `config-firm` — a store of the run's own, so a profile edit here reaches no other firm.
- **Steps**
  1. Sign in as the fixture's **Platform admin**, switch into the fixture's firm → Administration → Configuration → Business Profiles → **Profiles** → edit **WHOLESALE** → in **Enabled features** tick **IMEI** → Save.
  2. Untick IMEI; tick **BARCODE** (if it is not already) → Save.
- **Expect**
  - Step 1: refused in the summary at the top of the form, which scrolls into view: "These features are not implemented yet and cannot be enabled: IMEI." The dialog stays open and **nothing** is written — not the features, and not the profile's other fields (until 2026-09-12 they were — BACKLOG §31.6). The six roadmap features: `IMEI`, `KITCHEN_MANAGEMENT`, `PRESCRIPTION_REQUIRED`, `PROJECT_MANAGEMENT`, `RECIPE_MANAGEMENT`, `SERVICE_CONTRACTS`.
  - Step 2: saves. The **Feature Flags** leaf beside it is the catalogue, not where a profile's features are chosen.
- **Data (HTTP):** `PUT /api/v1/business-framework/profiles/{WHOLESALE id}/features` with the current ids plus IMEI's → **422**, the same sentence.
- **Leaves:** the fixture store's WHOLESALE profile, with BARCODE on.

### TC-CONF-005 — The tax simulator: CGST and SGST within a state, IGST across

- **Covers:** plan 6.7
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, Administration → Configuration → Tax Configuration → **Rule Simulator**. Transaction type `SALES_INVOICE`, tax profile `GST_18_LOCAL`, invoice value `1000` → Run Simulation. Then transaction type `SALES_INTERSTATE` → Run.
- **Expect:** local — no rule matched, CGST 9% = 90 and SGST 9% = 90, total **180**. Interstate — matched rule **`INTERSTATE_GST_18`**, one component IGST 18% = 180, total **180**, and the trace shows the rule matched. (TEST01's rules come from the GST template, the same six the demo firms carry.)
- **Data (HTTP):** `POST /api/v1/tax-framework/simulate` with the same values → `total_tax_amount` 180 both times; `matched_rule_id` null, then INTERSTATE_GST_18's id.
- **Leaves:** unchanged.

### TC-CONF-006 — A product's own conversion outranks the firm-wide one

- **Covers:** plan 6.8
- **Fixture:** `config-firm` — `<SUFFIX>-DET` is bought in PACK and stocked in KG, with its own PACK→KG rule at factor **1**.
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm (or its **Firm admin**), Administration → Configuration → UOM & Packaging → **Conversion Rules** → **Add**: Product *Firm-wide*, From `PACK`, To `KG`, Factor `2` → Save.
  2. Purchases → Purchase Orders → New: vendor `<SUFFIX>-V`, product `<SUFFIX>-DET`, quantity **10**, Purchase UOM `PACK — Pack` → Save; open the order.
- **Expect**
  - Step 1: the firm-wide rule appears beside the product's own.
  - Step 2: the line shows **Base Qty 10**, not 20 — the product's factor of 1 outranks the firm-wide 2. (Ranked explicitly rather than by NULL sort, which PostgreSQL and SQLite order oppositely.)
- **Data (HTTP):** the order's line carries `conversion_factor` 1 and `base_quantity` 10. *(Driven with two firm-wide PACK→KG rules at 2 in place: still 10.)*
- **Leaves:** a firm-wide rule and a draft order in the fixture's store.

---

## Buying — order to payment

Four documents: a purchase order, goods receipts against it, a supplier
invoice against a receipt, and a purchase return. **Completing a receipt
posts stock; cancelling a completed one reverses the stock and the journal;
approving an invoice posts the payable; completing a return takes stock back
off.** Everything else is paperwork.

Each stage has a fixture, so any step can be taken on its own. They all buy
**this run's own product**, which starts with **nothing on hand** — every
stock figure below is absolute, not "up by N from where you started".

| Fixture | Starts you with |
| --- | --- |
| `buy-ready` | a vendor `<SUFFIX>-V` and a product `<SUFFIX>-B`, 0 on hand |
| `po-approved` | … and an **approved** purchase order for 10 at 100 |
| `po-received` | … and receipts of **4** and **6**, both completed — 10 on hand |
| `po-invoiced` | … and an **approved** supplier invoice for the receipt of 6 (708.00 with GST) |

Purchase orders are **Purchases → Purchase Orders**; receipts, invoices and
returns have their own sidebar modules; payments are **Finance → Payments**;
stock is **Inventory → Inventory** and **Inventory → Stock Ledger**. Every
screen reads once when opened: **Refresh** after acting elsewhere.

### TC-BUY-001 — Raising a purchase order, and the approval that cannot be skipped

- **Covers:** plan 7.1, 7.2, 7.3
- **Fixture:** `buy-ready`
- **Steps**
  1. As the fixture's **Firm admin**, Purchases → Purchase Orders → **New**: vendor `<SUFFIX>-V`, branch `HO`, warehouse `MAIN`, today; **Add Line**: product `<SUFFIX>-B`, quantity **10**, unit price **100** (the units fill from the product, PIECE) → **Save**. Open it.
  2. Select the draft: look at the toolbar and inside the view.
  3. **Submit**, then **Approve**.
- **Expect**
  - Step 1: status **DRAFT**, number `PO-TEST01-HO-2026-2027-…`; the Line Items table names the product as `<SUFFIX>-B — Bought Item <suffix>` and the unit `PIECE`; the Approval banner reads "Submit this draft to send it for approval."
  - Step 2: **Approve is not offered** on a draft — only Submit. **(HTTP)** `POST /api/v1/purchases/{id}/approve` on a draft → **422**, "Only submitted purchase orders can be approved. Submit the order first."
  - Step 3: toasts "… submitted for approval." and "… approved."; status **APPROVED**, the grid updating without the dialog closing.
- **Leaves:** an approved order.

### TC-BUY-002 — Editing an approved order withdraws the approval

- **Covers:** plan 7.4
- **Fixture:** `po-approved`
- **Steps:** as the fixture's **Firm admin**, select the fixture's order → **Edit** → dialog **Editing withdraws the approval** → **Edit anyway**. Type a line remark and change the order remarks → **Save**. Then **Submit** and **Approve** again.
- **Expect:** saved as **DRAFT**; the remark survives reopening; the view's **History** shows the approval withdrawn (audit `purchase.approval_withdrawn`). An edit no longer decides the status — the update body cannot write one. After Submit and Approve: APPROVED again.
- **Leaves:** the order, re-approved.

### TC-BUY-003 — Receiving part of an order, then the rest

- **Covers:** plan 7.5, 7.6
- **Fixture:** `po-approved`
- **Steps**
  1. As the fixture's **Firm admin**, Goods Receipts → **New** → **Purchase Order** picker (approved orders only) → the fixture's order. Set Accepted to **4**, warehouse `MAIN` → **Save Receipt** → select the draft → **Complete**.
  2. Purchases → the order. Inventory → Inventory and Stock Ledger, filtered to `<SUFFIX>-B`.
  3. Goods Receipts → New against the same order → Accepted defaults to **6** → Save, Complete.
- **Expect**
  - Step 1: the line arrives with Accepted 10 and "Ordered 10 · already received 0"; after save, "Goods receipt GRN-… created as a draft. Complete it to post the stock."; after Complete, status **COMPLETED**.
  - Step 2: the order reads **PARTIALLY_RECEIVED**; `<SUFFIX>-B` in MAIN holds **4**; the Stock Ledger shows `GOODS_RECEIPT` +4 referencing the GRN.
  - Step 3: the line says "already received 4"; after Complete the order reads **RECEIVED**, MAIN holds **10**, and a second `GOODS_RECEIPT` entry appears.
- **Leaves:** a fully received order.

### TC-BUY-004 — Cancelling a completed receipt undoes its stock and its journal

- **Covers:** plan 7.7
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, Goods Receipts → select the **receipt of 4** → **Cancel**. Then the order, the Inventory row and the Stock Ledger for `<SUFFIX>-B`; Finance → Journal Entries.
- **Expect:** status **CANCELLED**; the ledger shows `GOODS_RECEIPT_REVERSAL` **−4** against that GRN; MAIN holds **6**; the order drops back to **PARTIALLY_RECEIVED**; the journal shows the reversal, crediting inventory with what the movement removed.
- **Leaves:** 6 on hand; one cancelled receipt.

### TC-BUY-005 — A receipt that has been invoiced cannot be cancelled

- **Covers:** plan 7.8
- **Fixture:** `po-invoiced`
- **Steps:** as the fixture's **Firm admin**, Goods Receipts → select the **receipt of 6** (the one the fixture invoiced) → **Cancel**.
- **Expect:** refused — "Goods receipt GRN-… has been invoiced, so cancelling it would leave the accrual and the payable disagreeing. Cancel the purchase invoice first, or raise a purchase return." Nothing changes. *(A purchase invoice cannot be raised from the desktop — BACKLOG §31.9 — which is why the fixture raises it.)*
- **Leaves:** unchanged.

### TC-BUY-006 — Returning damaged goods to the supplier

- **Covers:** plan 7.9
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, Purchase Returns → **New** → **Goods Receipt** picker (completed receipts only) → the **receipt of 6**. On its line set **Returning** **2**, click the **Damaged** chip → **Save Return** → select the draft → **Approve** → **Complete**. Then Inventory, Stock Ledger, Journal Entries, and Reports → Operational Reports → **Damaged goods returned**.
- **Expect:** after save, "Purchase return PR-2026-2027-… created as a draft. Approving and completing it is what takes the stock off."; after Complete, **COMPLETED**. MAIN holds **8**. The Stock Ledger shows the return of 2 referencing the PR (the API reads `transaction_type: RETURN`). The journal shows the return's entry; the damaged-goods report lists the line. Open the return: product and unit read as code and name, not ids.
- **Leaves:** 8 on hand; a completed return.

### TC-BUY-007 — The purchasing reports have rows

- **Covers:** plan 7.10
- **Fixture:** `po-approved`
- **Steps:** as the fixture's **Firm admin**, Reports → **Operational Reports**: Purchase order register, Orders not yet received, Overdue purchase orders, Orders by supplier, Orders by buyer, Purchases by product.
- **Expect:** each opens with a row count in the header. The register and "not yet received" include the fixture's order; by supplier names `Fixture Supplier <suffix>`; by product names `Bought Item <suffix>`. Overdue and by buyer may be empty in TEST01 — an empty report reads "Nothing to report", never a blank grid.
- **Leaves:** unchanged.

### TC-BUY-008 — Paying the supplier

- **Covers:** plan 7.11
- **Fixture:** `po-invoiced`
- **Steps:** as the fixture's **Firm admin**, Finance → **Payments → Record Payment**: **Paid to** `<SUFFIX>-V`; **Amount** the bill's Outstanding (708.00); **Method** Bank; **Oldest first** → **Record payment**. Open Record Payment again for the same vendor.
- **Expect:** toast "PY-… recorded and posted to the ledger." *(The plan said `PAY-`; the series prefix is `PY`.)* The second time, the bill is gone from the list. Journal Entries shows the payment: Dr Accounts Payable / Cr Bank.
- **Data (HTTP):** `GET /api/v1/payments/parties?search=<SUFFIX>` lists the vendor by code and name.
- **Leaves:** a paid supplier invoice.

---

## Stock

Everything here lives under **Inventory**, in two groups that must be clicked
open: **Stock** (Inventory, Opening Stock, Physical Count, Stock Ledger,
Transactions, Stock Summary, Stock Search) and **Batch & Serial** (Batches,
Lots, Serial Numbers, Expiry Monitor). Transfer, Write off and Quarantine are
toolbar buttons on the Inventory tab and act on the selected row.

Batches with expiry dates and serial numbers need a business profile that
enables them, and TEST01's Wholesale profile does not — so those cases run in
a firm of the run's own on the **Pharmacy** or **Electronics** profile, which
the fixture builds (a minute or two).

### TC-STOCK-001 — The summary and the rows agree; the ledger explains the balance

- **Covers:** plan 8.1, 8.2
- **Fixture:** `po-received` — `<SUFFIX>-B` received 4 then 6 into MAIN: 10 on hand.
- **Steps**
  1. As the fixture's **Firm admin**, Inventory → Stock → **Inventory**, filter Product `<SUFFIX>-B` → Apply. Then **Stock Summary**.
  2. Inventory → Stock → **Stock Ledger**, filter Product `<SUFFIX>-B` → Apply; open one row's detail (eye icon). Then Transaction type `GOODS_RECEIPT` → Apply.
- **Expect**
  - Step 1: one row, MAIN, Current **10**, Available 10, Reserved 0; the summary's figure for the product agrees.
  - Step 2: two `GOODS_RECEIPT` rows, +4 and +6, each naming its GRN, with the balance after each; the last equals Current. The detail dialog is titled "Ledger details". Filtering by type leaves the two. *(Known: the type list offers values the server never writes and lacks some it does — BACKLOG §31.13.)*
- **Leaves:** unchanged.

### TC-STOCK-002 — Moving stock between warehouses posts no journal

- **Covers:** plan 8.3
- **Fixture:** `stock-ready` — 50 of `<SUFFIX>-P` in MAIN; an empty warehouse `<SUFFIX>-W2` under HO.
- **Steps**
  1. As the fixture's **Firm admin**, Inventory → Stock → Inventory → select the `<SUFFIX>-P` / MAIN row → **Transfer**: quantity **3**, **Move it to** `<SUFFIX>-W2 - Overflow <suffix>`, reference `<SUFFIX>-TRF` → **Transfer**.
  2. Refresh; Stock Ledger for the product; Finance → Journal Entries.
  3. Transfer again with quantity **999**.
- **Expect**
  - Step 1: the dialog "Transfer stock" says how much is available; toast "Stock transferred."
  - Step 2: MAIN **47**, `<SUFFIX>-W2` **3** (a row appears), the product's total unchanged at 50. Ledger: `TRANSFER_OUT` 3 at MAIN and `TRANSFER_IN` 3 at W2, both `<SUFFIX>-TRF`. Journal: **no** entry — the footnote says why.
  - Step 3: refused in the dialog, in a red banner with the error icon: "The source holds 47.0000 available, so 999 cannot be transferred out of it." — before anything is sent.
- **Leaves:** 47 in MAIN, 3 in W2.

### TC-STOCK-003 — Writing off, and holding stock back

- **Covers:** plan 8.3a, 8.3b
- **Fixture:** `stock-ready`
- **Steps**
  1. As the fixture's **Firm admin**, select `<SUFFIX>-P` / MAIN → **Write off**: quantity **1**, reason Damage, reference `<SUFFIX>-WO` → Write off. Check the ledger and Journal Entries.
  2. **Quarantine** → **Hold back**, quantity **2**, reference `<SUFFIX>-QH` → Hold back. Then Quarantine → **Release**, quantity 2, reference `<SUFFIX>-QR` → Release.
  3. Quarantine → Hold back with quantity **999**.
- **Expect**
  - Step 1: "Stock written off."; MAIN **49**; ledger `WRITE_OFF` 1 `<SUFFIX>-WO`; the journal shows it (Dr Inventory Adjustment / Cr Inventory).
  - Step 2: "Quarantine updated."; ledger `QUARANTINE_HOLD`, then `QUARANTINE_RELEASE`; **no** journal for either. Note what the row shows between hold and release — **(HTTP)** the inventory row read `current_quantity` 47, `available_quantity` 47, `quarantine_quantity` 2 after holding 2 of 49 (driven); the plan expected Current to stay put while Available fell, so record which way the screen shows it.
  - Step 3: refused by name: "There is … to hold, so 999 cannot be."
- **Leaves:** 49 in MAIN, nothing held.

### TC-STOCK-004 — A physical count posts only what was counted

- **Covers:** plan 8.4
- **Fixture:** `stock-ready`
- **Steps:** as the fixture's **Firm admin**, Inventory → Stock → **Physical Count** → **Open Count**: branch HO, warehouse MAIN, today → Open. On the sheet find `<SUFFIX>-P - Fixture Product <suffix>` (code and name, never an id); type **49** in Counted (Expected is 50); leave every other line blank. **Save progress**, close, reopen from the list → **Post count** → confirm.
- **Expect:** "PC-… opened over N lines." (N is every product in MAIN — other runs' too). Difference reads `-1` while typing. The list reads "1 of N lines counted", then "N lines · posted". After posting: MAIN **49**; ledger `ADJUSTMENT` −1 referencing the count; Journal Entries shows the adjustment; the uncounted lines moved nothing. The posted sheet is read-only: "Posted. The differences are in the ledger."
- **Leaves:** 49 in MAIN; a posted count.

### TC-STOCK-005 — Dispatch draws the earliest-expiring batch first

- **Covers:** plan 8.5, 8.6
- **Fixture:** `pharma-firm` — `<SUFFIX>-AMX` in three batches of 10: `-B1` **expired 30 days ago**, `-B2` expiring in 20 days, `-B3` in 400; an approved order for **5**.
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Inventory → **Batch & Serial** → **Batches**, search `<SUFFIX>-B`.
  2. Delivery Notes → **New** → the fixture's order for 5 → read "Expected to ship from — earliest expiry first, decided at dispatch" → **Save** → **Approve** → **Dispatch**.
  3. Batches again; Stock Ledger for `<SUFFIX>-AMX`.
  4. Inventory → Batch & Serial → **Expiry Monitor**.
- **Expect**
  - Step 1: three batches, 10 available each, with their expiry dates.
  - Step 2–3: status DISPATCHED; ledger `DISPATCH` −5 referencing the note. **Which batch lost 5 is the question.** Driven on 2026-09-16, it was **`-B1`, the expired one** — see defect **D-8-1**. Record which batch the preview named and which lost stock.
  - Step 4: the six cards — Expired Today, Expire in 7 Days, Expire in 30 Days, Total Expired, Quarantine, Recalled — with `-B1` counted as expired and `-B2` inside 30 days; then the **All Batches** grid (Batch #, Product, Status, Qty, Available, Expiry Date, Warehouse).
- **Leaves:** a dispatched note.

### TC-STOCK-006 — A delivery short of stock saves but will not dispatch

- **Covers:** plan 8.7
- **Fixture:** `pharma-firm` — `<SUFFIX>-SHT` has **3** on hand and an approved order for **10**.
- **Steps:** as the fixture's **Firm admin**, Delivery Notes → **New** → the order for 10 → read the preview → Save → Approve → **Dispatch**.
- **Expect:** the preview ends "Short by … — there is not enough available stock to cover this line." Saving is allowed; **Dispatch is refused** with the server's sentence, "Insufficient available stock for dispatch line."; the note stays **APPROVED** and the ledger shows no DISPATCH.
- **Leaves:** an approved, undispatched note.

### TC-STOCK-007 — A remembered filter from another firm is dropped

- **Covers:** plan 8.6a
- **Fixture:** `pharma-firm` — its platform admin can open both TEST01 and the fixture's firm.
- **Steps:** sign in as the fixture's **Platform admin**; switch into **TEST01** → Inventory → Stock → Inventory → filter by any product → Apply. Switch into the fixture's firm → the same tab.
- **Expect:** the tab renders; the remembered TEST01 filter is dropped (the panel reads "Filters" with none active) and choosing the firm's own warehouse works. *(A remembered id from another firm used to take the section down with "This section failed to render".)*
- **Leaves:** unchanged.

### TC-STOCK-008 — Serial numbers carry their warranty

- **Covers:** plan 8.8
- **Fixture:** `electronics-firm` — `<SUFFIX>-MIX`, 5 on hand, serials `<SUFFIX>-MIX-0001` to `-0005`.
- **Steps:** as the fixture's **Firm admin**, Inventory → Batch & Serial → **Serial Numbers**; search `<SUFFIX>-MIX-`; open one row's detail; filter Status AVAILABLE.
- **Expect:** five rows, status AVAILABLE, Warranty End a year from today, warehouse MAIN. The detail is titled "Serial: <SUFFIX>-MIX-0001" with warranty start and end and the warehouse. The Status filter keeps all five.
- **Leaves:** unchanged.

### Known defects found while writing these cases

- **D-8-1 — Dispatch drew an expired batch.** In a Pharmacy firm with batches expired 30 days ago, expiring in 20 days and in 400 days, dispatching 5 took them from the **expired** batch — its status still AVAILABLE. "Earliest expiry first" read literally does that; for a pharmacy it ships expired medicine. Whether an expired batch should be skipped, refused or warned about is the owner's call.

---

## Selling — quotation to cash

A firm of the run's own, priced the way WHOLE01 is. Its fixtures build it
from nothing — a minute or two — and then carry one sale to a stage:

| Fixture | Starts you with |
| --- | --- |
| `selling-firm` | customers **`<SUFFIX>-C01` Vijaya** (7.5% standing discount, Retailer segment, **no PAN**) and **`<SUFFIX>-C02` Anand** (Wholesaler, PAN, its own `NEGOTIATED` list at 9.25%); **`<SUFFIX>-DET`** at 84, GST 18 local, 100 in MAIN; the firm-wide **`STANDING`** list on DET with breaks 0 → 2%, 15 → 4.25%, 18 → 6.75%; promotions **BULK5** (7.5% on a line of 25+), **BIGORDER** (200 off a bill of 4,500+, ends the stack), **CLEARANCE** (1% on a line of 40+), **WELCOME** (2.5%, coupon only: `WELCOME10`, `WELCOME10B`); **TCS on** with a threshold of 0 (0.1%, 1% without a PAN); loyalty 2 points per 100 |
| `selling-ordered` | … and Vijaya's order for **12** with coupon `WELCOME10`, approved |
| `selling-delivered` | … and notes for **5** and **7**, both dispatched |
| `selling-invoiced` | … and the note for 5 **billed and approved: 483.21** |
| `selling-paid` | … and receipts of **241.60** and **341.61** (241.61 applied), and the note for 7 billed and approved (676.49) |

Sign in as the fixture's **Firm admin** unless a case says otherwise.
Quotations, Sales Orders, Delivery Notes, Sales Invoices and Sales Returns are
sidebar entries of their own; Credit Notes and Proforma are under **Sales**.
A resolved rate is not printed on a saved document: reopen the editor
(**Revise** on a quotation, **Edit** on a draft order) and read the helper
under the blank Discount % box — "Last priced at N% by the price list" (or a
promotion, or the customer's standing rate).

### TC-SELL-001 — The price list's first break outranks a standing discount

- **Covers:** plan 9.1
- **Fixture:** `selling-firm`
- **Steps:** Quotations → **New Quotation**: customer `<SUFFIX>-C01`; **Add line** `<SUFFIX>-DET` quantity **12**, Discount % empty (helper: "Blank takes this customer's 7.5%, or a price list where one applies.") → **Create draft** → **Revise**.
- **Expect:** "QT-… drafted, good until … Nothing is reserved by it." Under the blank box: "Last priced at **2**% by the price list." — STANDING's first break beats Vijaya's 7.5% standing rate.
- **Data (HTTP):** the quotation's line carries `discount_percent` 2.0000, `discount_source` `price_list`; grand total 1,165.65.
- **Leaves:** a draft quotation.

### TC-SELL-002 — A ladder takes the highest break at or below the quantity

- **Covers:** plan 9.2
- **Fixture:** `selling-firm`
- **Steps:** a quotation for `<SUFFIX>-C01`, DET quantity **18**, Discount % empty → Create draft → Revise.
- **Expect:** "Last priced at **6.75**% by the price list" — the break at 18, not the first one above zero. Revising 12 → 18 on one quotation and saving gives the same, because a revision prices resolved lines afresh.
- **Leaves:** a draft quotation.

### TC-SELL-003 — A customer's own list replaces the firm-wide ladder

- **Covers:** plan 9.3
- **Fixture:** `selling-firm`
- **Steps:** a quotation for `<SUFFIX>-C02` (Anand), DET quantity **18** → Create draft → Revise.
- **Expect:** "Last priced at **9.25**% by the price list" — Anand's `NEGOTIATED` list replaces STANDING rather than amending it.
- **Leaves:** a draft quotation.

### TC-SELL-004 — A promotion outranks both lists; a typed zero refuses them all

- **Covers:** plan 9.4, 9.5
- **Fixture:** `selling-firm`
- **Steps**
  1. A quotation for `<SUFFIX>-C02`, DET quantity **30** → Create draft → Revise.
  2. Revise: type **0** in Discount % → Save revision → Revise.
- **Expect**
  - Step 1: "Last priced at **7.5**% by a promotion" — BULK5 applies at 25+ and a promotion outranks either list.
  - Step 2: the box itself reads **0** (a typed rate is kept) and the line total is the full 30 × 84 = 2,520 before tax. Zero is a refusal of every arrangement, not a silence.
- **Data (HTTP):** step 1 `discount_source` `promotion`, 7.5; step 2 `discount_source` `percent`, 0, grand total 2,973.60.
- **Leaves:** a draft quotation.

### TC-SELL-005 — An accepted quotation converts once

- **Covers:** plan 9.6
- **Fixture:** `selling-firm`
- **Steps:** a quotation for `<SUFFIX>-C02`, DET 12 → Create draft → **Mark as sent** → **Customer accepted** (give a reason) → **Convert to order**. Then look for Convert again.
- **Expect:** toasts "QT-… marked as sent…", "QT-… accepted. Converting it is what creates the order.", "QT-… became SO-…. The order reserves the stock when it is approved." Afterwards **no Convert to order**. **(HTTP)** `POST /api/v1/quotations/{id}/convert` with `{"order_date": "<today>"}` → **422**, "Quotation QT-… already became SO-….".
- **Leaves:** a converted quotation and a draft order.

### TC-SELL-006 — A coupon reaches its offer; a code nobody recognises gives nothing and refuses nothing

- **Covers:** plan 9.7, 9.8
- **Fixture:** `selling-firm`
- **Steps**
  1. Sales Orders → **New Order**: `<SUFFIX>-C01`, ships from MAIN, DET **12**, Discount % blank, **Coupon** `WELCOME10` → **Create draft** → **Edit**.
  2. Replace the coupon with `WELCOME10B` → Save order → Edit.
  3. Coupon `NOSUCHCODE` → Save order → Edit.
- **Expect**
  - Step 1: "Order drafted. Approve it to commit the stock and the credit."; "Last priced at **2.5**% by a promotion" — the coupon's offer **replaces** the list's 2%, it does not compound onto it.
  - Step 2: still **2.5** — a second code on the same offer.
  - Step 3: "Order updated."; the helper falls back to "Last priced at **2**% by the price list". The Coupon helper says "Unrecognised codes are ignored".
- **Leaves:** a draft order.

### TC-SELL-007 — Approving reserves the stock and claims the offer

- **Covers:** plan 9.9
- **Fixture:** `selling-ordered`
- **Steps:** Inventory → Stock → Inventory, filtered to `<SUFFIX>-DET`. Then Reports → Operational Reports → **Promotion claims**.
- **Expect:** MAIN: Current **100**, Reserved **12**, Available **88**. The claims report lists `WELCOME`, coupon `WELCOME10`, Vijaya, the order, **CLAIMED** (it was PENDING while a draft; only a claim at approval counts against a limit).
- **Leaves:** unchanged.

### TC-SELL-008 — A hold stops a delivery; releasing restores the status it had

- **Covers:** plan 9.10, 9.11
- **Fixture:** `selling-ordered`
- **Steps**
  1. Select the fixture's order → **Hold**, reason `awaiting cheque` → Hold. Then Delivery Notes → **New** → that order → **Save Delivery Note**.
  2. Select the order → **Release**.
- **Expect**
  - Step 1: "SO-… is on hold."; Status **APPROVED (on hold)**. The note is refused **on save**: "SO-… is on hold and cannot be dispatched ("awaiting cheque"). Release it first." Reserved stays **12** — a hold says "not yet", not "never".
  - Step 2: "SO-… released."; Status plain **APPROVED** — the status it had, not a reset.
- **Leaves:** the order released.

### TC-SELL-009 — Part deliveries move the order's status

- **Covers:** plan 9.12, 9.14
- **Fixture:** `selling-ordered`
- **Steps**
  1. Delivery Notes → **New** → the order; Delivering **5**, warehouse MAIN → Save → **Approve** → **Dispatch** (an approved note moves nothing). Refresh.
  2. New again: Delivering defaults to the remaining **7** → Save, Approve, Dispatch, Refresh.
- **Expect**
  - Step 1: "Delivery note DN-… created as a draft. Dispatching it is what moves the stock."; the note **DISPATCHED**; the order **PARTIALLY_DELIVERED**; MAIN on hand **95**, Reserved **7**; ledger `DISPATCH` −5; Journal Entries has the note's cost-of-goods entry.
  - Step 2: the order **DELIVERED** (only once both notes are dispatched); ledger `DISPATCH` −7; Reserved **0**, on hand **88**.
- **Leaves:** a delivered order.

### TC-SELL-010 — A delivery ships the deal the order struck

- **Covers:** plan 9.13
- **Fixture:** `selling-delivered`
- **Steps:** open the note for 5 and read its line's Unit Price and discount; open the order and compare.
- **Expect:** **identical** — 84 less 2.5%, from the coupon on the order. The note does not re-read the customer's current rate or price list.
- **Data (HTTP):** the note's line: `unit_price` 84, `discount_percent` 2.5, `net_amount` 483.21.
- **Leaves:** unchanged.

### TC-SELL-011 — Billing a note: the cap, the approval and its journal

- **Covers:** plan 9.15, 9.16
- **Fixture:** `selling-delivered`
- **Steps**
  1. Sales Invoices → **New Invoice** → **Bill this delivery note** → the note for **5** (it reads "dispatched 5 · at 84 less 2.5%"). Type **6** into Bill.
  2. Set Bill back to **5** → **Create draft** → select it → **Approve**.
  3. Finance → Journal Entries → the invoice's `SI-…` entry → **View**. Masters → Customers → `<SUFFIX>-C01`.
- **Expect**
  - Step 1: refused before sending: "Only 5.0 left to bill." (an API client gets "Invoice quantity exceeds the available source quantity.").
  - Step 2: "Invoice created as a draft. Approve it to post the journal."; **APPROVED**.
  - Step 3: Dr **1100 Trade Receivables 483.21**, Cr **Sales 409.50**, Cr **Output Tax 73.71** — one tax line; the CGST/SGST split is on the invoice. Vijaya's Outstanding **483.21**.
- **Leaves:** an approved invoice.

### TC-SELL-012 — Print settings and a printed bill

- **Covers:** plan 9.17
- **Fixture:** `selling-invoiced`
- **Steps:** select the invoice → **Print settings** icon → How many copies **2**, Copy 1 label / Copy 2 label (they prefill ORIGINAL FOR RECIPIENT / DUPLICATE FOR TRANSPORTER) → save → **Print**.
- **Expect:** the PDF carries the CGST/SGST split, an HSN column, the HSN-wise summary, "AMOUNT CHARGEABLE, IN WORDS", and two labelled copies. Saving print settings needs `SETTINGS_UPDATE`, which the firm admin holds. *(The fixture's firm and customer carry no GSTIN and the product no HSN, so those cells print empty; WHOLE01's did.)*
- **Leaves:** the firm's print settings for invoices.

### TC-SELL-013 — Receipts charge TCS; an excess with nothing else owed becomes an advance

- **Covers:** plan 9.18, 9.19
- **Fixture:** `selling-invoiced`
- **Steps**
  1. Finance → Receipts → **Record Receipt**: `<SUFFIX>-C01`, Amount **241.60**, Bank; under **Apply to invoices** type 241.60 into the invoice's **Apply** box → Record receipt. Customers → C01.
  2. Record Receipt again: Amount **341.61**, type **241.61** into Apply → Record receipt. Customers → C01.
- **Expect**
  - Step 1: the TCS notice (small text under **Against order (optional)**) charges **1%** — Vijaya has no PAN — **2.42** on 241.60. "RC-… recorded and posted to the ledger."; the row reads "Cleared SI-…". Outstanding **244.03** (483.21 − 241.60 + 2.42).
  - Step 2: TCS **3.42**; the running line says 100.00 left over before saving. The invoice drops out of the outstanding list. Customers: Outstanding **3.42** (this receipt's TCS) and Advance **97.58** — the excess over everything owed. *(WHOLE01's Vijaya owed on older bills, so there the excess came off the account instead; this firm has none.)*
- **Data (HTTP):** `GET /api/v1/customers/{id}` → `current_outstanding`, `unapplied_advance_balance`.
- **Leaves:** two receipts.

### TC-SELL-014 — Applying an advance posts nothing; reversing a receipt puts everything back

- **Covers:** plan 9.20, 9.21
- **Fixture:** `selling-paid` — the second receipt has 100.00 unallocated; Vijaya: Outstanding 679.91, Advance 97.58.
- **Steps**
  1. Finance → Receipts → on the **341.61** receipt, **Apply to an invoice** → the invoice for 7 → Amount **97.58** → Apply. Then try to apply **5** more.
  2. On the **241.60** receipt → **Reverse**, give a reason → Reverse. Then Reverse it again.
- **Expect**
  - Step 1: "RC-… applied to SI-…"; the dialog says "Nothing moves in the ledger. The money arrived when the receipt was recorded." — Journal Entries has **no** new entry. Customers: Outstanding **584.75**, Advance **2.42** (the net owed is unchanged). Applying 5 more is refused: "RC-… has only 2.42 left unapplied."
  - Step 2: "RC-… reversed."; badge **Reversed**; Journal Entries shows `RC-…-REV` and the receipt's TCS reversed. Outstanding rises by **239.18** — the 241.60 less the 2.42 TCS that is also undone. Reversing again: "RC-… has already been reversed."
- **Leaves:** one receipt reversed, one applied.

### TC-SELL-015 — A sales return is capped at what was dispatched

- **Covers:** plan 9.22
- **Fixture:** `selling-invoiced`
- **Steps:** Sales Returns → **New Return** → Returned against the invoice (entries read "SI-… · date · Vijaya Stores <suffix>") → Line 1 → Taken back into MAIN → Quantity returned **9** → Create draft. Then **2** → Create draft → **Approve** → **Complete**.
- **Expect:** 9 is refused: "Only 5.0 went out on this line." (server: "Return quantity exceeds what was dispatched on the source document (5.0000 sent, 0.0000 already returned)."). With 2: "SR-… created as a draft…", "SR-… approved. Nothing has moved yet…", "SR-… completed: 2 back on the shelf and 193.28 credited to the customer." Ledger `SALES_RETURN` +2; Outstanding down **193.28** (2 × 84 less 2.5% plus 18%).
- **Leaves:** a completed return.

### TC-SELL-016 — A credit note reverses the tax the line was charged, and no more than the line

- **Covers:** plan 9.23, 9.24
- **Fixture:** `selling-invoiced`
- **Steps**
  1. Sales → Credit Notes → **Raise credit note**: the invoice, Line 1, Reason Rate difference, **Credit, before tax** **50** → Raise → row's **Approve**.
  2. Raise again on the same line with **400**.
- **Expect**
  - Step 1: the row reads `59.00 (tax 9.00)` — 18%, the rate that line was charged. "CN-… — approved. The credit and the tax are on the ledger." Outstanding down **59**.
  - Step 2: refused: "A credit note cannot credit more than the line was charged: 409.5000 charged, 50.0000 already credited."
- **Leaves:** an approved credit note.

### TC-SELL-017 — A proforma posts nothing and does not follow the order afterwards

- **Covers:** plan 9.25, 9.26
- **Fixture:** `selling-ordered`
- **Steps**
  1. Sales → Proforma → **New** → the fixture's order ("SO-… — Vijaya Stores <suffix> — total") → Raise → **Issue**. Journal Entries; Customers → C01.
  2. Sales Orders → the order → **Cancel**. Proforma → Refresh → reopen the proforma.
- **Expect**
  - Step 1: "PI-… raised. Issue it when the customer needs it." then "PI-… issued."; a `PI` series number; **nothing** posted; Outstanding unchanged; the pane says "Not a tax invoice — no input tax credit is available against this document."
  - Step 2: the proforma's lines and totals are unchanged — snapshotted when it was raised.
- **Leaves:** an issued proforma and a cancelled order.

---

## Pricing, promotions and incentives

Price Lists, Promotions, Commission and Targets are under **Sales**; Loyalty
under **Masters**; the promotion and loyalty reports under **Reports**.
Pricing and loyalty cases use the selling fixtures (see *Selling*, above);
commission uses `commission-firm`:

| Fixture | Starts you with |
| --- | --- |
| `loyalty-points` | `selling-invoiced` — Vijaya's invoice for 483.21 — plus **200 points** credited to Vijaya by adjustment |
| `commission-firm` | `territory-firm` plus: firm-wide **4%** of money collected; **Asha 15%** on `<SUFFIX>-P` only; **Bala** a ladder (2% to 50,000 then 4%, nothing below 1,000, 2% bonus when his target is met). Asha sold 20 `-P` (2,360.00) and 30 `-Q` (3,540.00); Bala 40 `-Q` (4,720.00); **all collected** today. This month's targets: Asha 1,000 (met), Bala 100,000 (missed) |

### TC-INCENT-001 — A price list is a ladder, and a promotion still outranks it

- **Covers:** plan 10.1, 10.2
- **Fixture:** `selling-firm`
- **Steps**
  1. As the fixture's **Firm admin**, Sales → **Price Lists** → select `STANDING` (do not open it).
  2. Double-click `STANDING` → **Add product**: `<SUFFIX>-DET`, From qty **25**, Discount % **8** → Save.
  3. Quotations → New for `<SUFFIX>-C01`, DET qty **30** → Create draft → Revise.
- **Expect**
  - Step 1: the pane reads `STANDING · applies to Everyone`, "In force from 2000-01-01", and three rates for DET: `2%`, `from 15: 4.25%`, `from 18: 6.75%`. Products column 3 (it counts rate rows).
  - Step 2: "Price list saved."; a fourth line `from 25: 8%`.
  - Step 3: "Last priced at **7.5**% by a promotion" — BULK5 outranks the list at 25+.
- **Leaves:** STANDING with a 25 break, in the fixture's store only.

### TC-INCENT-002 — Editing an active promotion makes a new revision

- **Covers:** plan 10.3
- **Fixture:** `selling-firm`
- **Steps:** Sales → **Promotions** → select `BULK5` → Edit → change only the Description → Save. Read the list and the selected row's pane.
- **Expect:** "Promotion BULK5 saved as a new revision; the one you opened is now inactive."; a second BULK5 row appears. The pane reads "BULK5 · revision 2 · applies at 10" and "Applies when: line_quantity GREATER_OR_EQUAL 25.0000". An active offer is superseded, never rewritten — and its claims and limits follow the version group, not the row.
- **Leaves:** BULK5 at revision 2.

### TC-INCENT-003 — Promotion reports count a claim once, at approval

- **Covers:** plan 10.4, 10.5, 10.6
- **Fixture:** `selling-ordered` — one approved order used coupon `WELCOME10`.
- **Steps:** Reports → Operational Reports → **Promotion performance**, **Coupon performance**, **Promotion claims**.
- **Expect**
  - Performance: `WELCOME` with 1 claim; BULK5, BIGORDER and CLEARANCE listed with 0.
  - Coupons: `WELCOME10` with 1 claim; `WELCOME10B` listed at **0** — a code nobody presented is still listed.
  - Claims: one row — WELCOME, coupon WELCOME10, Vijaya Stores <suffix>, SALES_ORDER, the order's number, benefit 25.20, **CLAIMED**.
- **Leaves:** unchanged.

### TC-INCENT-004 — An offer that does not stack ends the stack

- **Covers:** plan 10.7
- **Fixture:** `selling-firm`
- **Steps:** Sales Orders → New for `<SUFFIX>-C01`: DET **60** at 84 (gross 5,040) → Create draft → Edit. Then Save order unchanged → Edit again.
- **Expect:** under the line's blank box "Last priced at **7.5**% by a promotion" (BULK5); the **Discount on the whole order** box blank with "Last taken off: 200 by a promotion." (BIGORDER). CLEARANCE (1% at 40+, priority 30) did **not** apply: BIGORDER (priority 20) ends the stack. Both survive the unchanged save.
- **Data (HTTP):** the order: `line_discount_total` 378.00, `bill_discount_amount` 200.00 (`bill_discount_source` promotion), grand total 5,265.16.
- **Leaves:** a draft order.

### TC-INCENT-005 — Loyalty: the scheme, a balance, and spending points settles a bill

- **Covers:** plan 10.8, 10.9, 10.10, 10.11
- **Fixture:** `loyalty-points`
- **Steps**
  1. Masters → **Loyalty**. Reports → Financial Reports → **Loyalty balances**.
  2. Sales Invoices → select Vijaya's approved invoice → **Use points** → 100 → **Use them**.
  3. Journal Entries → the top `LOY-RED-SI-…` → View. Customers → C01.
  4. Use points again, 5000.
  5. Reports → Operational Reports → **Points about to lapse**.
- **Expect**
  - Step 1: the banner "2 points per 100, worth 1 each and expire after 24 months. At least 50 before any can be spent."; the balances report lists Vijaya with **200** points worth 200.00.
  - Step 2: "100 points used on SI-…".
  - Step 3: Dr **2600 Loyalty Payable 100.00** / Cr **1100 Trade Receivables 100.00**. Outstanding **383.21** — 100 lower; the invoice's total and tax unchanged: the bill is **settled**, not discounted.
  - Step 4: refused outright: "That customer holds 100.0000 points, not 5000.0000." No journal.
  - Step 5: **empty** — nothing in this store is within 90 days of lapsing. *(WHOLE01's aged batches, and the oldest-first spending they showed, need points two years old; a fixture cannot age them.)*
- **Leaves:** 100 points spent.

### TC-INCENT-006 — Commission blends rates per line, and a ladder's floor is a round number

- **Covers:** plan 10.12, 10.13
- **Fixture:** `commission-firm`
- **Steps:** as the fixture's **Firm admin**, Sales → **Commission** → **Collected** view, from `2026-04-01` to the end of this month → **Show**. Then Sales → **Targets** → **Achievement** for this month.
- **Expect**
  - **Asha**: collected **5,900.00**, commission **495.60** — 15% of 2,360 on `-P` plus 4% of 3,540 on everything else: **8.4%**, neither of the two rates that govern her. Target **Met**.
  - **Bala**: collected **4,720.00**, commission **94.40** — exactly **2.00%**, the bottom band; above the 1,000 floor; target **Missed**, so no bonus.
  - Achievement: Asha 1,000 target achieved; Bala 100,000 wanted, 4,720 invoiced (4.72%), 95,280 short.
- **Data (HTTP):** `GET /api/v1/commission/report?from_date=2026-04-01&to_date=<month end>`; `GET /api/v1/sales-targets/achievement?from_date=…&to_date=…`.
- **Leaves:** unchanged.

### TC-INCENT-007 — Payouts: accrue, approve, pay, cancel

- **Covers:** plan 10.14
- **Fixture:** `commission-firm`
- **Steps**
  1. Commission → **Payouts** → **Accrue period** for this month → Accrue.
  2. On Bala's DRAFT look for Pay; **Approve**; then **Pay** (paid on today, from `1000 Cash`).
  3. **Cancel** Asha's draft.
  4. Accrue the same period again.
- **Expect**
  - Step 1: "2 payout(s) accrued." — Asha **495.60**, Bala **94.40**, both DRAFT.
  - Step 2: no Pay on a draft (**(HTTP)** paying it: 422, "Only an approved payout can be paid. Approve it first, which is what recognises the debt."). Approve: "… approved. The cost and the debt are on the ledger."; Pay: "… paid." Journal Entries: `COMM-YYYYMM-<id>` (Dr Commission Expense / Cr Commission Payable) and `COMM-YYYYMM-<id>-PAY` (Dr Commission Payable / Cr Cash).
  - Step 3: "… cancelled. The period is free to accrue again." — nothing posted, because a draft had no journal.
  - Step 4: refused — "A commission payout already covers part of that period for this salesman (…)." Bala's paid payout still holds it; accruing for Asha alone would succeed.
- **Leaves:** Bala paid, Asha cancelled.

### TC-INCENT-008 — Whoever states a debt must not move the cash

- **Covers:** plan 10.15
- **Fixture:** `commission-firm`
- **Steps:** sign in as the fixture's **Asha** (`SALES_EXECUTIVE`), expand Sales. **(HTTP)** as Asha: `GET /api/v1/commission/payouts`; `POST /api/v1/commission/payouts/{any id}/approve` and `/pay`.
- **Expect:** no Commission, Targets, Price Lists or Promotions under Sales. All three calls **403**.
- **Leaves:** unchanged.

---

## Territory, routes and beats

A firm of the run's own with WHOLE01's territory shape, from the
`territory-firm` fixture (a minute or two). Geography, Route Types, Beat
Plans, Call Lists, Coverage and Route Builder are under **Sales**.

| | Route | Frequency, days | Salesperson | Round, in order |
| --- | --- | --- | --- | --- |
| North Zone | `<SUFFIX>-R-N1` North Sales Beat | weekly, Mon Wed Fri | Asha | `<SUFFIX>-C1` Revise Check, `<SUFFIX>-C2` Classic Stores |
| North Zone | `<SUFFIX>-R-N2` North Collections | fortnightly, Tue Thu | Bala | `<SUFFIX>-C3` Vijaya Stores |
| South Zone | `<SUFFIX>-R-S1` South Sales Beat | weekly, Tue Thu | Asha | `<SUFFIX>-C4` Anand Agencies |

Beat plans: one weekly plan per working day per route (`-BP-R1-MON`, `-R1-WED`,
`-R1-FRI`, `-R2-TUE`, `-R2-THU`, `-R3-TUE`, `-R3-THU`), **`-BP-COLL`**
fortnightly on Tuesdays from 2026-04-07 (N2), and **`-BP-MTH`** on the second
Tuesday (S1). `<SUFFIX>-SN` is on no route. Sign in as the fixture's **Firm
admin**.

### TC-TERR-001 — The territory tree

- **Covers:** plan 11.1, 11.2
- **Fixture:** `territory-firm`
- **Steps**
  1. Sales → **Geography**; select any row; the right-hand **Territory tree** → **Expand all**. Click the icon beside its title ("Open the tree in a larger window"); try Collapse all / Expand all; Close.
  2. Double-click `<SUFFIX>-R-N1` → **Details**; then **Customers** and **Salespeople**.
- **Expect**
  - Step 1: Chennai Region (Region) → North Zone and South Zone (Territory) → North Sales Beat and North Collections under North, South Sales Beat under South (Route), each node with its code and full path; the grid's Hierarchy column carries the path.
  - Step 2: **Route** section: Route type **Sales Route**, Visit frequency **Weekly**, Working days **Mon, Wed, Fri**, Runs from **Always**, Runs until **No end**. 2 customers, both active; Salespeople 1. Customers: Revise Check, Classic Stores. Salespeople: Asha Sales.
- **Leaves:** unchanged.

### TC-TERR-002 — A call list for a Monday, with reasons for every plan that does not run

- **Covers:** plan 11.3
- **Fixture:** `territory-firm`
- **Steps:** Sales → **Call Lists**. Move to **Monday 2026-09-21** (› Next day or the date button), Salesperson Everyone. Then **Back to today**.
- **Expect:** the date button reads "Monday 2026-09-21"; the status bar "1 of 9 plan(s) run on Monday 2026-09-21". `-BP-R1-MON` is badged **Runs on Monday** and calls Revise Check then Classic Stores (the route's round, in order). Every other plan is **Not on Monday** with its reason — e.g. `-BP-R1-FRI` "Runs on Fridays; this is a Monday."
- **Data (HTTP):** `GET /api/v1/sales-territories/call-lists?date=2026-09-21` → nine `entries`, one with `occurs: true`.
- **Leaves:** unchanged.

### TC-TERR-003 — Fortnightly and monthly plans, and why they skip a week

- **Covers:** plan 11.4
- **Fixture:** `territory-firm`
- **Steps:** Call Lists: date **2027-01-12**, then **2026-10-13**, then **2026-10-20**.
- **Expect**
  - 2027-01-12 (a second Tuesday and an even fortnight from 2026-04-07): "4 of 9 plan(s) run" — `-R2-TUE` and `-COLL` (both Vijaya), `-R3-TUE` and `-MTH` (both Anand).
  - 2026-10-13 (second Tuesday, off fortnight): `-COLL` **Not on Tuesday**, "Runs every other Tuesday counted from 2026-04-07; this is the week between."; `-MTH` runs.
  - 2026-10-20 (third Tuesday): `-COLL` runs; `-MTH` "Runs on the second Tuesday of the month; this is the third."
- **Leaves:** unchanged.

### TC-TERR-004 — Building a round, and saving one unchanged

- **Covers:** plan 11.5, 11.6
- **Fixture:** `territory-firm`
- **Steps**
  1. Sales → **Route Builder** → Route being built `<SUFFIX>-R-N1` (right: 1. Revise Check, 2. Classic Stores). Tick **On no route yet** → **Find** → double-click `<SUFFIX>-SN` (stop 3) → drag it by ≡ above the first stop → **Save round and order**. Choose the route again.
  2. **Remove from round** on SN → Save. Then choose N1 again, change nothing → Save.
- **Expect**
  - Step 1: "3 outlet(s) on North Sales Beat, in order."; reopened: 1. SN, 2. Revise Check, 3. Classic Stores — the stops moved without a collision.
  - Step 2: "2 outlet(s) on North Sales Beat, in order." both times; the same two stops in the same order. The status bar says "Saving replaces the whole round with the list on the right." — which is why the screen refuses to save a round it could not read.
- **Leaves:** N1's round as the fixture made it.

### TC-TERR-005 — A salesperson must cover the customer's route

- **Covers:** plan 11.7
- **Fixture:** `territory-firm`
- **Steps:** Sales Orders → **New Order** for `<SUFFIX>-C4` (Anand, on S1, covered by Asha): ships from MAIN, **Salesman Bala**, one line `<SUFFIX>-P` qty 1 → Create draft. Then Asha → Create draft. Then Salesman blank → Create draft → reopen.
- **Expect:** Bala is refused in the editor's banner: "The selected salesperson is not assigned to this territory." — nothing saved. Asha saves. Blank saves and, reopened, the salesman is **Asha**, supplied by the customer's route.
- **Leaves:** two draft orders.

### Known defects found while writing these cases

- **D-11-1 — A new firm's territory hierarchy is not saved until somebody saves it, and reading it invents ids.** `GET /api/v1/sales-territories/hierarchy-levels` on a fresh store answers REGION / TERRITORY / ROUTE with a **different config id and level ids on every read** — defaults built and never committed. Creating a territory against one of those ids is refused: "Configured hierarchy level is not active." Saving the hierarchy (the same levels, unchanged) makes them real; the fixture does that. Whether the desktop's Geography screen saves first was not checked — if it does not, a new firm cannot create its first territory.

---

## Compliance — GST returns, e-invoices and TCS

A GST return is **derived on every read**, never stored: cancel an invoice and
it drops out. E-invoices and e-way bills go to a **sandbox** that marks every
reference it mints `SBX…`. E-Invoice, GST Returns and TCS are under **Sales**.

| Fixture | Starts you with |
| --- | --- |
| `compliance-firm` | a firm with GSTIN `33…` (Tamil Nadu); **`<SUFFIX>-B2B`** Registered Buyer with a GSTIN; **`<SUFFIX>-B2C`** Walk-in Buyer with none; `<SUFFIX>-P` at HSN **340220**, GST 18 local. This month: **Invoice A** — B2B, 10 × 100 (1,180.00), **collected and e-registered**; **Invoice B** — B2B, 5 × 100 (590.00), unpaid, **e-registered, no e-way bill**; **Invoice C** — B2C, 3 × 100 (354.00), unpaid, not registered |
| `selling-paid` | (see *Selling*) two receipts from Vijaya, who has no PAN, each charged TCS at 1% |

### TC-COMP-001 — GSTR-1 for the month

- **Covers:** plan 12.1
- **Fixture:** `compliance-firm`
- **Steps:** as the fixture's **Firm admin**, Sales → **GST Returns** → this month (the From/To boxes are chosen, not typed) → **GSTR-1**.
- **Expect:** "Filing as <the firm's GSTIN>". **B2B**: Invoice A — taxable 1,000.00, CGST 90.00, SGST 90.00 — and Invoice B — 500.00, 45.00, 45.00 — under the buyer's GSTIN. **B2CS**: one row, Place **33**, 18%, taxable 300.00, CGST 27.00, SGST 27.00 — never a blank place. **CDNR**: nothing. **HSN**: 340220, quantity 18, taxable 1,800.00. **Invoices without a place of supply**: "Nothing in this section." The status bar: "Derived from the documents on every read, never stored."
- **Data (HTTP):** `GET /api/v1/gst-returns/gstr1?from_date=<first>&to_date=<last>`.
- **Leaves:** unchanged.

### TC-COMP-002 — What rests on a bill stops it being cancelled; a return follows what is left

- **Covers:** plan 12.2
- **Fixture:** `compliance-firm`
- **Steps**
  1. Sales Invoices → **Invoice A** → **Cancel**.
  2. **Invoice C** → **Cancel** (give a reason). GST Returns → Refresh.
- **Expect**
  - Step 1: refused, naming what rests on it: "SI-… cannot be cancelled while it has money applied from RC-…; its registration with the tax authority. Reverse or cancel those first."
  - Step 2: C cancels. The **B2CS row is gone** and HSN falls to quantity 15, taxable 1,500.00. *(The plan's second refusal — by a sales return — is TC-SELL-015's return in reverse; this fixture has none.)*
- **Leaves:** Invoice C cancelled.

### TC-COMP-003 — GSTR-3B agrees with GSTR-1

- **Covers:** plan 12.3
- **Fixture:** `compliance-firm`
- **Steps:** GST Returns → **GSTR-3B**, same month. Add GSTR-1's B2B, B2CS and CDNR taxable values by hand.
- **Expect:** **3.1(a)** taxable **1,800.00**, CGST 162.00, SGST 162.00 — equal to GSTR-1's sum; credit notes deducted 0; the inward side reads "Not derived: the purchase side files this." 3B is aggregated from the documents, not parsed out of GSTR-1.
- **Leaves:** unchanged.

### TC-COMP-004 — The e-invoice screen says it is a rehearsal

- **Covers:** plan 12.4
- **Fixture:** `compliance-firm`
- **Steps:** Sales → **E-Invoice**.
- **Expect:** a banner, "References marked sandbox are a rehearsal: nothing was filed with the tax authority..."; columns Invoice, Customer, Reference, E-way bill; **two** rows (A and B), each Reference an `SBX…` value (hover for `SBX… (sandbox — nothing filed)`), E-way bill —. If anything reads LIVE, stop.
- **Leaves:** unchanged.

### TC-COMP-005 — An invoice to a buyer with no GSTIN is refused locally

- **Covers:** plan 12.5
- **Fixture:** `compliance-firm`
- **Steps:** E-Invoice → **Register an invoice** → **Invoice C** (items read `SI-… — Walk-in Buyer <suffix> — 354.00`) → Register.
- **Expect:** refused **locally**, in an error toast: "This invoice cannot be registered yet: the customer has no GST number." No row added, no portal code.
- **Leaves:** unchanged.

### TC-COMP-006 — Raising and withdrawing an e-way bill

- **Covers:** plan 12.6
- **Fixture:** `compliance-firm`
- **Steps**
  1. Select **Invoice B**'s row → **Raise bill**: Distance 120, Moving by Road, vehicle blank → Raise. Then vehicle `TN01AB1234` → Raise.
  2. With the row selected → **Cancel bill**, give a reason.
  3. **(HTTP)** `POST /api/v1/einvoice/invoices/{Invoice C id}/eway-bill` with `{"distance_km": "120", "transport_mode": "ROAD", "vehicle_number": "TN01AB1234"}`.
- **Expect**
  - Step 1: blank vehicle refused before sending: "Goods moving by road need a vehicle number on the bill."; then "E-way bill raised." and the cell fills with `SBX…`.
  - Step 2: "E-way bill withdrawn."
  - Step 3: **422**, "Register the invoice before raising its e-way bill: the bill quotes the IRN, and one without it cannot be matched to a supply." The screen does not offer it.
- **Leaves:** a withdrawn e-way bill on B.

### TC-COMP-007 — TCS: the register, the settings, and a journal of its own

- **Covers:** plan 12.7, 12.8
- **Fixture:** `selling-paid`
- **Steps:** as the fixture's **Firm admin**, Sales → **TCS**; open **Settings** (close without saving). Finance → Journal Entries → search `TCS-RC` → View one.
- **Expect**
  - The banner reads "Collecting under section 206C(1H) • (the threshold, 0) per buyer per year, then 0.100% (1.000% without a PAN)"; the register lists the two receipts from Vijaya — **2.42** and **3.42**, rate **1.000%** (no PAN), **COLLECTED**.
  - Settings: **Collect under section 206C(1H)** on; preceding year turnover 150,000,000; threshold 0; rate 0.1; without a PAN 1.0.
  - Journal: `TCS-RC-…` entries separate from the receipts' own; View reads **Dr 1100 Trade Receivables / Cr 2500 TCS Payable** — 2500, not Output Tax.
- **Data (HTTP):** `GET /api/v1/tcs/collections` → `tcs_amount`, `rate_percent`, `without_pan: true`.
- **Leaves:** unchanged.

---

## Finance, reports and the rest of the platform

Finance is a flat list of tabs; Reports has **Operational Reports** and
**Financial Reports**; accounting periods live under **Masters →
Configuration → Financial Years**. Trial Balance, Profit & Loss and Balance
Sheet each take an **Accounting period**: pick the same one on all three.

The cases that change a firm's books — a new account, a closed period, a cost
centre, an account that demands one — use `ready-firm`, a store of the run's
own with a fresh chart (1000 Cash, 5000 Purchases, and no 9999).

### TC-FIN-001 — A new ledger account, and what cannot change afterwards

- **Covers:** plan 13.1
- **Fixture:** `ready-firm`
- **Steps:** as the fixture's **Firm admin**, Finance → **Chart of Accounts** → **New**: group chip **REV** first, code `9999`, name `Manual test account`, type EXPENSE → Save. Then group **EXP · Direct Expenses** → Save. Select it → **Edit**.
- **Expect:** with REV: "A ledger account must share its group's account type." With EXP: the row appears (Code, Account, Type, Status). No Delete on the toolbar. On Edit, group, type and code are fixed; only Name, Description, the two "Requires a …" boxes and **Active** change.
- **Leaves:** account 9999 in the fixture's store.

### TC-FIN-002 — The three statements balance and agree

- **Covers:** plan 13.2, 13.3
- **Fixture:** `selling-paid`
- **Steps:** as the fixture's **Firm admin**, Finance → **Trial Balance**, this month's period; then **Profit & Loss** and **Balance Sheet**, the same period.
- **Expect:** the trial balance has Code, Account, Type, Opening, Debit, Credit, Closing, a Total row and a **Balanced** chip — 1100 Trade Receivables among the rows. P&L: Income and Expenses with a Net profit or loss row (This period, Year to date). Balance Sheet: Assets, Liabilities, Equity with Retained earnings brought forward and Result for the year, chip **Balanced**. They agree: Total assets = Liabilities and equity; the sheet's Result for the year = the P&L's year-to-date net; total debit = total credit. *(The figures are this fixture's own; the relationships are the test.)*
- **Leaves:** unchanged.

### TC-FIN-003 — A closed period refuses a posting; its trail says who closed it

- **Covers:** plan 13.5, 13.8
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Firm admin**, Journal Entries → **New Entry**: period June 2026, any journal and voucher type, date 2026-06-15, reference `MT-CLOSE-1`, lines `5000 Purchases` Dr 100 and `1000 Cash` Cr 100 → **Save Draft**.
  2. Masters → Configuration → **Financial Years** → the year → **June 2026** → **Close**.
  3. Journal Entries → the draft → **Post**.
  4. Reopen June (**Open**) → Post again.
  5. Settings → Audit Logs → Action `finance.accounting_period.updated` (in full) → Search. Then sign in as the fixture's **Platform admin**, stay on Platform, and run the same search.
- **Expect**
  - Step 2: "June 2026 is closed. Nothing further can be booked into it."
  - Step 3: refused: "Accounting period P03 is closed and cannot accept postings." (June is P03 in an April year.)
  - Step 4: "Journal entry MT-CLOSE-1 posted." The trial balance for a later month still reads **Balanced**.
  - Step 5: in the firm, the caption "The trail for Ready <suffix>…" and **two** rows (closed, reopened); `finance` alone would find nothing (exact match). On Platform the same search finds **nothing** — finance events stay in the firm's trail.
- **Leaves:** a posted June entry.

### TC-FIN-004 — Journal entries say which module posted them

- **Covers:** plan 13.4
- **Fixture:** `selling-paid`
- **Steps:** Finance → Journal Entries; search each: `SI-2026-2027-000001`, `DN-`, `RC-2026-2027-000001`, `TCS-RC-2026-2027-000001`; open each with **View**.
- **Expect:** each row's subtitle is the entry's description; the View dialog's first line reads "POSTED · posted by <module> · <description>" — sales_invoice, delivery_note, settlements, tcs. The search matches reference or description; there is no source-module filter (BACKLOG §31.15).
- **Leaves:** unchanged.

### TC-FIN-005 — Every report opens, and an empty one says so

- **Covers:** plan 13.6
- **Fixture:** `selling-paid`
- **Steps:** Reports → **Operational Reports** and **Financial Reports**: open every entry.
- **Expect:** each renders with `N row(s)` in the header, or — when empty — "Nothing to report / This firm has nothing matching it yet." rather than a blank grid. The sales order register, delivery note register and invoice reports hold the fixture's documents; the purchase reports are empty (this store bought nothing).
- **Leaves:** unchanged.

### TC-FIN-006 — Ctrl+K finds a product and lands on its screen

- **Covers:** plan 13.7
- **Fixture:** `product-master`
- **Steps:** as the fixture's **Firm admin**, type in any search box, move to another screen, press **Ctrl+K**, type `<SUFFIX>-PM` → Search; select the result → **Open Details**.
- **Expect:** the dialog opens wherever focus is; one result, **Slot Check <suffix>** (a product), "1 result found."; Open Details closes the search and lands on **Masters → Products**. **(HTTP)** `GET /api/v1/search?query=<SUFFIX>-PM` → 200 (the parameter is `query`; `q` answers 422).
- **Leaves:** unchanged.

### TC-FIN-007 — Cost and profit centres, and an account that demands one

- **Covers:** plan 13.9d, 13.9e
- **Fixture:** `ready-firm`
- **Steps**
  1. Finance → **Cost Centres** → New `SALES`, `Sales` → Save; New `SALES` again. Finance → **Profit Centres** → New `NORTH`, `North` → Save.
  2. Chart of Accounts → Edit `5000 Purchases` → tick **Requires a cost centre** → Save. Journal Entries → New Entry → choose 5000 on a line.
  3. **(HTTP)** `POST /api/v1/finance/journal-entries` with a 5000 line and no `cost_center_id`.
  4. Untick the flag.
- **Expect**
  - Step 1: the rows appear; the second SALES: "A cost centre with this code already exists." No Delete on either grid — deactivate with Active.
  - Step 2: a **Cost centre \*** dropdown on that line and no other; with SALES chosen the entry saves.
  - Step 3: **422**, "Ledger account 5000 requires a cost centre."
- **Leaves:** centres SALES and NORTH.

### TC-FIN-008 — A blocking credit policy refuses the approval

- **Covers:** plan 13.9c3 (credit half)
- **Fixture:** `policy-firm` — BLOCK at 100%; Anand's limit 1,000; a draft order for 20 detergent.
- **Steps:** as the fixture's **Firm admin**, Customers → toolbar **Settings**; Cancel. Sales Orders → the fixture's draft → **Approve**.
- **Expect:** the policy reads **Warn, then block**, warn 80, block 100. Approve is refused: "Anand Agencies <suffix> would be at 179.9% of a 1000.00 credit limit. Collect payment or raise the limit before continuing." The order stays DRAFT.
- **Leaves:** unchanged.

### TC-FIN-009 — A firm that does not type delivery notes

- **Covers:** plan 13.9c3 (stages half)
- **Fixture:** `policy-firm` — delivery-note stage off; Vijaya's order for 4, approved.
- **Steps:** as the fixture's **Firm admin**, Sales Invoices → **Sales stages** icon. Look for Delivery Notes in the sidebar. Then Sales Invoices → New → bill the fixture's **order** (4) → Create draft → Approve. Reports → Operational → **Delivery note register**.
- **Expect:** Sales stages shows **Delivery note** switched off, and **Delivery Notes is not in the sidebar** — a stage the firm does not type is hidden. The invoice approves straight off the order; the service raises and dispatches the note itself (the order reads **DELIVERED**), and the register lists that note. *(Whether a hidden screen should hide notes that exist is an open product question, not a defect.)*
- **Leaves:** a billed, delivered order.

### TC-FIN-010 — Roles and Permissions are one sidebar entry with two addresses

- **Covers:** plan 13.9, 13.9b, 13.9c
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, look at the Administration sidebar; open **Roles & Permissions**; switch the strip to Permissions. Ctrl+K a permission code (e.g. `CUSTOMER_VIEW`) → open it. Sign out and in.
- **Expect:** **one** entry, Roles & Permissions, with a Roles / Permissions strip; switching keeps the entry highlighted and the heading. Ctrl+K lands on **Permissions** directly; after signing in again the last screen restores to the same half. (Creating and editing roles is TC-ROLE-001 and TC-ROLE-002.)
- **Leaves:** a firm admin user.

### TC-FIN-011 — A crash report reaches Diagnostics

- **Covers:** plan 13.10
- **Fixture:** `platform-admin`
- **Steps:** sign in on the desktop, end **agency_desktop** in Task Manager, start it again and sign in as the fixture's **Platform admin** (the queued report is sent then). Settings → **Diagnostics** → Source **Desktop** → Search; open the **UnexpectedTermination** group's first occurrence. Then Source **Server**, any group's first occurrence.
- **Expect:** Desktop: the UnexpectedTermination count one higher than before; occurrences / first seen / last seen / versions chips; the newest occurrence shows Firm, User and "Leading up to it" breadcrumbs ("Previous session started at … ended without a clean exit…") — no Request and no stack trace. Server: **Request <request_id>** and the stack trace.
- **Leaves:** one more crash report.

---

## Concurrency — two people, one record

Run these with **two clients** on one server (or two windows of one client),
**A** and **B**, both signed in as the same fixture's firm admin. An editor that
saves from **inside** its dialog — customer, sales order, sales invoice,
product, price list, promotion, coupon, customer group, target, payout
adjustment — says on a lost race, keeping the dialog open with the typing in
it: *"Somebody else saved this <thing> while you were editing it. Your changes
are still here and have not been sent. Copy anything you need, then close and
reopen to see theirs."* An editor that closes first — branch, warehouse,
quotation, batch, lot, serial number, beat plan, place, territory, tax
component — says in a red toast: *"Somebody else saved this <thing> while you
were editing it. Your changes were not saved. Open it again to see theirs and
redo yours."*

### TC-CONC-001 — Two people editing one customer

- **Covers:** plan 14.1
- **Fixture:** `customer-master`
- **Steps:** on **A** and **B**: Masters → Customers → double-click `<SUFFIX>-CM`. On A change the phone → **Save**. On B change the phone to something else → **Save**.
- **Expect:** A saves ("Customer updated."). B is refused **inside the editor** with the sentence naming `customer`; the dialog stays open with B's typed phone still in the box. Cancel B; reopen: A's phone.
- **Leaves:** the customer with A's phone.

### TC-CONC-002 — The same race on an order, a product and a price list

- **Covers:** plan 14.2
- **Fixture:** `selling-firm`
- **Steps:** create a draft Sales Order for `<SUFFIX>-C01` first (any line). Then, on A and B: open that draft → **Edit**, change **Remarks** on both, Save A then B. Repeat on Masters → Products → `<SUFFIX>-DET` (Description) and Sales → Price Lists → `STANDING` (the **Name** — the dialog has no Description).
- **Expect:** B is refused each time with the sentence naming `sales order`, `product`, `price list`; typing kept, dialog open.
- **Leaves:** three records with A's edits.

### TC-CONC-003 — Saving unchanged does not move the version

- **Covers:** plan 14.3
- **Fixture:** `customer-master`
- **Steps:** on A alone, double-click `<SUFFIX>-CM`, change nothing → Save; do it again. **(HTTP)** `GET /api/v1/customers/{id}` before and after; compare the `ETag`.
- **Expect:** accepted both times; the `ETag` and the body's `version` are **the same before and after** — so a client re-sending the same `If-Match` is still accepted. *(Driven: `"2"` before and after an unchanged PUT.)*
- **Leaves:** unchanged.

### TC-CONC-004 — Two approvals of one order

- **Covers:** plan 14.4
- **Fixture:** `selling-firm`
- **Steps:** create a draft order for `<SUFFIX>-C01`. On A and B select it in the grid. **Approve** on A; then **Approve** on B, whose grid still says DRAFT.
- **Expect:** A: the row reads APPROVED. B: a red toast — "Only draft sales orders can be approved." (A finished first) or the conflict sentence (both in flight) — never a silent no-op, never a 500. Refresh B: APPROVED once.
- **Leaves:** an approved order.

### TC-CONC-005 — The last use of a coupon goes to one order

- **Covers:** plan 14.5
- **Fixture:** `selling-firm`
- **Steps**
  1. Sales → Promotions → **Coupons** → `WELCOME10B` → Edit → **Total claims allowed** `1` → Save.
  2. Raise two draft orders for `<SUFFIX>-C01` with **Coupon** `WELCOME10B`, one on each client. Approve both.
- **Expect:** the first approves; the second is refused **by name**: "Coupon WELCOME10B has been used as often as it allows. Re-save the document to price it without." — not silently repriced. A claim counts only at approval, under a lock on the promotion. (`test_the_refusal_is_for_the_race_two_orders_priced_before_either_approved` covers the true race.)
- **Leaves:** one approved order with the coupon, one draft; the coupon exhausted in the fixture's store.

### TC-CONC-006 — Two accruals of one payout period

- **Covers:** plan 14.6
- **Fixture:** `commission-firm`
- **Steps:** on A and B: Sales → Commission → **Payouts** → **Accrue period**, this month on both; **Accrue** on A, then on B.
- **Expect:** A: "2 payout(s) accrued." B: "A commission payout already covers part of that period for this salesman (…)." — a **409** by name, never a 500. The database holds the rule (`UQ_commission_payouts_period_active`); the service supplies the sentence.
- **Leaves:** two draft payouts.

---

## Permissions — the server refuses, not only the button

`SALES_EXECUTIVE` holds `CUSTOMER_VIEW`, `TERRITORY_VIEW`, `SALES_VIEW` and the
three `SALES_*_CREATE` codes, nothing else. A hidden button is not a control:
each case below checks the screen **and** the route behind it.

### TC-PERM-001 — What a salesperson is not offered

- **Covers:** plan 15.1, 15.3, 15.4, 15.5
- **Fixture:** `sales-executive`
- **Steps:** sign in as the fixture's **Seller**. Look for Administration; expand **Sales** and look for Commission, Credit Notes and TCS.
- **Expect:** **no Administration** at all. Under Sales, the territory screens (on `TERRITORY_VIEW`) and none of **Commission**, **Credit Notes**, **TCS** — nor Price Lists, Promotions, Targets, Proforma, E-Invoice or GST Returns, each hidden on its own view code. That is expected, not a fault.
- **Leaves:** a seller.

### TC-PERM-002 — The credit policy opens read-only

- **Covers:** plan 15.2
- **Fixture:** `sales-executive`
- **Steps:** as the fixture's **Seller**, Masters → Customers → toolbar **Settings**.
- **Expect:** the dialog **opens read-only** — the policy's fields shown but disabled, Save greyed, only Close works — with "Changing the policy needs the manage customer settings permission."
- **Leaves:** a seller.

### TC-PERM-003 — Six writes, six refusals; two reads allowed

- **Covers:** plan 15.1, 15.2, 15.3, 15.4, 15.5, 15.6 (the HTTP halves)
- **Fixture:** `sales-executive`
- **Steps (HTTP)** — sign in as the fixture's seller (`POST /api/v1/auth/login`) and send, with `X-Firm-ID` of TEST01:
  1. `GET /api/v1/document-framework/numbering-rules`, then `PUT /api/v1/document-framework/numbering-rules/{any listed id}` `{"name": "x"}`.
  2. `GET /api/v1/customers/credit-settings`, then `PUT` it `{"enforcement": "OFF"}`.
  3. `POST /api/v1/commission/payouts/{any id}/approve` and `/pay`.
  4. `POST /api/v1/credit-notes/{any id}/approve`.
  5. `PUT /api/v1/tcs/settings` `{"is_enabled": true}`.
- **Expect:** both **reads answer 200** — any member may read how documents are numbered and the credit rule that warns them. **All six writes answer 403**, body `{"success": false, "error": {"code": "authorization_denied", …}}`. The id need not exist: the permission is checked before the record is looked up.
- **Leaves:** nothing.

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

## A firm administrator creating users

`FIRM_ADMIN` holds `USER_CREATE`, `USER_UPDATE`, `ROLE_ASSIGN` and `ROLE_VIEW`
— everything running a firm's people needs — and not `FIRM_VIEW`, a platform
code. The New-user gate used to demand it, so the one role whose job is
running a firm's people was refused New and Edit.

Where a person also works in another firm, their **profile** is a platform
administrator's to manage; a firm administrator still decides what they do in
their own firm, through **Roles by firm**.

### TC-USER-001 — New and Edit are a firm administrator's

- **Covers:** plan 20.1, 20.1a
- **Fixture:** `manual-hire`
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Administration → **Users**.
  2. Select **Manual Hire (<suffix>)** — in TEST01 only — → **Edit**.
- **Expect:** **New** and **Edit** offered; the edit form opens normally, writable.
- **Leaves:** unchanged.

### TC-USER-002 — Somebody who also works elsewhere opens read-only, and says why

- **Covers:** plan 20.1b
- **Fixture:** `shared-member`
- **Steps**
  1. As the fixture's **Firm admin**, Users → select **Shared Member (<suffix>)** → **Edit**.
  2. Double-click the row; then the context menu's **Edit**.
- **Expect:** all three open the record **read-only**, never silently: the subtitle reads "… also works in another firm, so their profile is managed by a platform administrator. Use Roles by firm to set what they do in yours." The refusal is about writing; the row is still one somebody meant to look at, so it opens.
- **Data (HTTP):** in `GET /api/v1/users?search=<suffix>.shared` as the firm admin, the row carries `belongs_to_other_firms: true`.
- **Leaves:** unchanged.

### TC-USER-003 — New starts in the firm that is open

- **Covers:** plan 20.2, 20.2a, 20.3
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Users → **New**. Look at **Firms** before typing anything; open its list.
  2. Name `In Firm <suffix>`, email `<suffix>.infirm@fixtures.local`, a 12-character password → Save.
- **Expect**
  - Step 1: **TEST01 already ticked** — the firm open in the switcher — and the list offers the firms *you* belong to (`/api/v1/me/firms`; `/api/v1/firms` is platform-only and answers a firm admin 403). The form used to open empty and then silently remove the membership the save had just made.
  - Step 2: created, in TEST01, in the grid at once.
- **Leaves:** a TEST01 user.

### TC-USER-004 — Creating somebody in no firm

- **Covers:** plan 20.2b
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Users → **New**: name `No Firm <suffix>`, email `<suffix>.nofirm@fixtures.local`, password; **clear** the Firms box; no job, no roles → Save.
  2. Users → **Add existing user** → type `<suffix>.nofirm`.
  3. New again: `<suffix>.nofirm2@fixtures.local`, Firms cleared, and this time pick a role under Roles in this firm → Save. Then look them up as in step 2.
- **Expect**
  - Step 1: created, in **no** firm — allowed and deliberate — and **not** in the grid.
  - Step 2: found, not marked as already a member.
  - Step 3: the form says "Somebody in no firm cannot be given roles here, because roles are held per firm. Save them without roles, then use Add existing user to bring them into this firm and set what they do." — **and the account already exists**, in no firm with no roles: the lookup finds `<suffix>.nofirm2`. Do not press Save again; a second create answers 409 on the email. See defect **D-20-1**.
  - *Step 1 failed on 2026-09-15 ("User not found." with the user created anyway) and was fixed in #402. Driven on the API: a firm admin's create lands the user in TEST01, clearing the firms leaves none, and the lookup then finds them with `already_a_member: false`. Step 3's order — create, clear firms, then refuse — is read from `saveAssignments`, not seen on screen.*
- **Leaves:** two users in no firm.

### TC-USER-005 — A platform administrator's New form

- **Covers:** plan 20.2c, 20.4
- **Fixture:** `platform-admin`
- **Steps:** sign in as the fixture's **Platform admin** → Administration → Users → **New**; look at Firms and open its list.
- **Expect:** Firms is **empty**, not prefilled — a platform administrator has no firm of their own, and quietly using whichever one the switcher shows would be a surprise. The list offers **every** firm (`/api/v1/firms`). Same field, a different source.
- **Leaves:** nothing (cancel).

### TC-USER-006 — A firm outside your reach is refused by name

- **Covers:** plan 20.5
- **Fixture:** `shared-member`
- **Steps (HTTP)** — as the fixture's firm admin, `X-Firm-ID` TEST01: `PUT /api/v1/users/{Shared Member's id}/firms` with `{"assignments": [{"firm_id": "11111111-1111-1111-1111-111111111111", "is_primary": false, "is_active": true}]}`.
- **Expect:** **422**, "You can only assign firms you administer." Refused, not silently dropped. Any id that is not TEST01's gives it — the reach check runs before the firm-exists check.
- **Leaves:** unchanged.

### TC-USER-007 — A firm administrator's membership write merges

- **Covers:** plan 20.6
- **Fixture:** `shared-member`
- **Steps**
  1. **(HTTP)** As the fixture's firm admin: `PUT /api/v1/users/{Shared Member's id}/firms` naming **TEST01 only**: `{"assignments": [{"firm_id": "<TEST01 id>", "is_primary": false, "is_active": true}]}`.
  2. Sign in as the fixture's **Platform admin** → Users → Shared Member (or `GET /api/v1/users/{id}/firms`).
- **Expect**
  - Step 1: **200** — naming only your own firm is legitimate.
  - Step 2: **both** memberships, TEST02 still primary. The endpoint replaces for a platform caller and **merges** for a scoped one: memberships outside the caller's reach are carried through untouched, or a firm administrator correcting their own firm would silently remove that person from every other firm. The screen refuses this edit anyway (TC-USER-002); the merge protects the API from any other client.
- **Leaves:** unchanged.

### TC-USER-008 — A firm administrator does not move somebody's primary firm

- **Covers:** plan 20.7
- **Fixture:** `shared-member` — Shared Member's primary is **TEST02**, which TEST01's admin cannot see.
- **Steps**
  1. **(HTTP)** As the fixture's firm admin: the `PUT` from TC-USER-007 with `"is_primary": true` on TEST01.
  2. Re-read as the fixture's platform admin.
- **Expect:** **200**, and the primary is **still TEST02** — the flag was **ignored, not refused**. It is one flag across every firm somebody belongs to, held by `UQ_user_firms_active_primary`; a caller who can see only some of those firms would either collide with a primary they cannot see or quietly demote it. The exception is somebody with no primary at all, who gets one.
- **Data**
  ```sql
  select f.code, uf.is_primary from platform.user_firms uf
  join platform.firms f on f.id = uf.firm_id
  join platform.users u on u.id = uf.user_id
  where u.email = '<suffix>.shared@fixtures.local' and uf.is_deleted = false;
  ```
- **Leaves:** unchanged.

### TC-USER-009 — A Counter Sales hire gets the till and not the ledger

- **Covers:** plan 20.8
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Users → New: name, `<suffix>.counter@fixtures.local`, password, **Job template** Counter Sales, Roles left alone → Save. (`docs/USER_ADMINISTRATION_GUIDE.md` §3 end to end.)
  2. Sign in as them and read the sidebar; open Finance.
- **Expect:** **Sales** and **Inventory** offered; **Finance** offered holding **exactly Receipts and Payments**; no Administration. None of Chart of Accounts, Control Accounts, Cost Centres, Profit Centres, Journal Entries, Ledgers, Trial Balance, Profit & Loss, Balance Sheet or Refunds.
  - **Two opposite failures:** no Finance at all means the module gate was reverted and the empty-sidebar bug is back; Finance *with the ledger in it* means the tabs lost their own codes and the module gate is doing the work alone.
- **Leaves:** a Counter Sales user in TEST01.

### Known defects found while writing these cases

- **D-20-1 — Asking for roles on somebody in no firm refuses after the account is made.** `saveAssignments` runs after the create and after the membership write, so the refusal "Save them without roles, then use Add existing user…" arrives when the user already exists in no firm. The message reads as if nothing was saved; pressing Save again answers 409. Checking before the create, in the form's own validation, would make the message true.

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

- **Covers:** plan 20a.1, 20a.2, 20a.3, 20a.4, 20a.5
- **Fixture:** `shared-member` — Shared Member is in TEST02 and TEST01 with no roles.
- **Steps**
  1. Sign in as the fixture's **Platform admin** → Users → edit **Shared Member (<suffix>)**. Read the roles field.
  2. Set it to `VIEWER` → Save & Close.
  3. Select the row → **Roles by firm**.
  4. Give TEST01 `SALES_MANAGER` → that section's **Save**.
  5. Give TEST02 `CASHIER` → its Save.
- **Expect**
  - Step 1: labelled **Roles in every firm**, saying it applies in every firm, including ones added later.
  - Step 3: a section per firm they belong to — TEST01 and TEST02, no others. `VIEWER` once at the top under **Applies in every firm**, greyed and unclickable. Each Save is enabled only once its own firm changed.
  - Step 5: TEST02 saved; TEST01 still shows `SALES_MANAGER` — one Save, one firm.
- **Data (HTTP)** as the platform admin: `GET /api/v1/users/{id}/roles` → VIEWER; `.../firms/{TEST01 id}/roles` → SALES_MANAGER; `.../firms/{TEST02 id}/roles` → CASHIER.
- **Leaves:** Shared Member with a role in each tier.

### TC-RTIER-002 — Saving the form unchanged keeps every firm's own roles

- **Covers:** plan 20a.6, 20a.8d
- **Fixture:** `shared-member-roles` — VIEWER everywhere, SALES_MANAGER in TEST01, CASHIER in TEST02.
- **Steps**
  1. As the fixture's **Platform admin**, edit **Shared Member (<suffix>)** → **Save** without changing anything.
  2. **Roles by firm**.
- **Expect:** TEST01 still SALES_MANAGER, TEST02 still CASHIER, VIEWER still under Applies in every firm. **The regression case**: before the fix both firms ended up holding every role, globally. One writer per tier, so neither save can touch the other's rows.
- **Leaves:** unchanged.

### TC-RTIER-003 — Each administrator sees the tier they cannot write

- **Covers:** plan 20a.6b, 20a.6c, 20a.6d
- **Fixture:** `shared-member-roles`
- **Steps**
  1. As the fixture's **Firm admin** (TEST01), Users → open **Shared Member (<suffix>)** (it opens read-only, TC-USER-002) and look under Security.
  2. As the fixture's **Platform admin**, edit the same person.
  3. As the platform admin, Roles by firm → clear TEST02's CASHIER → Save; reopen the form.
- **Expect**
  - Step 1: **Also applies here** shows `VIEWER`, read-only. A global grant applies in their firm, so hiding it made the form report less than the person could do.
  - Step 2: no Also applies here — the roles field already *is* the global set. Instead **Roles in specific firms**, read-only: `TEST01: SALES_MANAGER · TEST02: CASHIER`.
  - Step 3: only `TEST01: SALES_MANAGER`. A firm holding nothing is left out rather than shown empty.
- **Leaves:** Shared Member without the TEST02 role.

### TC-RTIER-004 — A firm administrator's Roles by firm is their firm only, and cannot clear a global grant

- **Covers:** plan 20a.7, 20a.8, 20a.8j
- **Fixture:** `shared-member-roles`
- **Steps**
  1. As the fixture's **Firm admin**, Users → select **Shared Member (<suffix>)** → **Roles by firm**.
  2. Remove `SALES_MANAGER` → Save.
- **Expect**
  - Step 1: **one section, TEST01**, with chips that respond. TEST02 is not listed — its Save would be refused by name. `VIEWER` shown greyed under Applies in every firm, not clearable. This dialog used to read the platform-only firm list, answer 403 and show a firm administrator no firm at all.
  - Step 2: removed in TEST01; VIEWER survives. A firm administrator may not undo a platform grant.
- **Leaves:** Shared Member with no TEST01 role.

### TC-RTIER-005 — A platform administrator's New writes the global tier only

- **Covers:** plan 20a.8b, 20a.8c, 20a.8e
- **Fixture:** `platform-admin`
- **Steps**
  1. As the fixture's **Platform admin**, Users → **New**; read the Security section.
  2. Create `<suffix>.global1@fixtures.local`: Firms TEST01 and TEST02, Roles in every firm `CUSTOMER_SUPPORT` → Save. Select them → **Roles by firm**.
  3. Create `<suffix>.global2@fixtures.local` in TEST01 with **Job template** Read Only → Save → Roles by firm.
- **Expect**
  - Step 1: **Job template**, **Roles in every firm**, and nothing that names a firm. **Apply roles to** is gone.
  - Step 2: both firm sections **empty**; CUSTOMER_SUPPORT under **Applies in every firm**.
  - Step 3: VIEWER under Applies in every firm — the job's roles land in the same tier the Roles field writes.
- **Leaves:** two users.

### TC-RTIER-006 — The firm switcher has no say in where a role lands

- **Covers:** plan 20a.8f, 20a.8g
- **Fixture:** `shared-member-roles`
- **Steps**
  1. As the fixture's **Platform admin**, switch into **TEST01**. Users → edit **Shared Member (<suffix>)**.
  2. Add `CUSTOMER_SUPPORT` to the roles field → Save → Roles by firm.
- **Expect**
  - Step 1: **one** roles field, **Roles in every firm**, plus the read-only **Roles in specific firms** listing both firms — TEST01 included. No second column. The helper says a role in one firm only is set under Roles by firm.
  - Step 2: CUSTOMER_SUPPORT under **Applies in every firm**; no firm section changed.
- **Leaves:** Shared Member with a second global role.

### TC-RTIER-007 — A firm administrator's form

- **Covers:** plan 20a.8h, 20a.8i
- **Fixture:** `two-tier-hire` — global VIEWER and CUSTOMER_SUPPORT; TEST01 ACCOUNTANT and INVENTORY_MANAGER.
- **Steps**
  1. As the fixture's **Firm admin**, Users → edit **Two Tier Hire (<suffix>)**.
  2. Press **Roles by firm** in the dialog footer; close it. Close the form, open it in **view**, press it again.
- **Expect**
  - Step 1: the roles field labelled **Roles in this firm** (ACCOUNTANT, INVENTORY_MANAGER) and **Also applies here** showing CUSTOMER_SUPPORT and VIEWER read-only. Nothing names a firm.
  - Step 2: the per-firm editor opens without closing the form, from edit and from view.
- **Leaves:** unchanged.

### TC-RTIER-008 — The server holds a firm administrator to their firm, and a role to a membership

- **Covers:** plan 20a.9, 20a.9b, 20a.10 (and the refusal 20a.8k shows)
- **Fixture:** `shared-member`
- **Steps (HTTP)**
  1. As the fixture's firm admin (`X-Firm-ID` TEST01): `PUT /api/v1/users/{Shared Member}/firms/{TEST02 id}/roles` `{"ids": ["<CASHIER id>"]}`.
  2. `GET /api/v1/users/{Shared Member}/firms/{TEST02 id}/roles`, then the same for TEST01.
  3. As the fixture's platform admin: `PUT /api/v1/users/{TEST02 Only}/firms/{TEST01 id}/roles` `{"ids": ["<CASHIER id>"]}`.
  4. As the firm admin: `GET /api/v1/users/{TEST02 Only}/firms`.
- **Expect**
  1. **422**, "You can only set roles in firms you administer."
  2. **422**, "You can only read roles in firms you administer." — the read used to answer for any firm. TEST01: **200**.
  3. **422**, "Add the user to this firm before giving them a role in it." A role there would sit in the table and stay out of the token.
  4. **200** and an **empty** list — a firm administrator learns nothing about which firms somebody outside theirs belongs to. *(Plan 20a.8k's screen message, "This person belongs to no firm you administer.", needs the Roles by firm dialog open on such a person, and a TEST02-only person is not in TEST01's grid to open it from; this is the server's half of the same rule.)*
- **Leaves:** unchanged.

---

## The five modules a firm administrator could not open

`FIRM_ADMIN` is built from `_operational_permissions`, a hand-kept list, and
five permission groups had never been added to it: `credit_note`, `proforma`,
`einvoice`, `loyalty` and `tcs`. Each shipped with a module, a screen and a
seeded gate that the role running the firm could not open. Granted in
`20260906_0130`.

**A token carries the claims it was minted with** — a session from before a
grant changes shows the old screens. Fixture accounts are always new, so this
only matters for accounts you already had open.

### TC-GRANT-001 — Credit notes: raise one against an approved invoice

- **Covers:** plan 21.1, 21.1a
- **Fixture:** `invoiced` — a sale of this run's own in TEST01: one invoice for 5 **APPROVED**, one **CANCELLED**.
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Sales → **Credit Notes** → **Raise credit note**.
  2. Open the **Invoice** picker and look for the fixture's two invoice numbers and its delivery note number.
  3. Pick the approved invoice; open **Line**.
  4. Enter an amount below what the line was charged (it was charged 590.00: 5 × 100 plus 18% GST) → **Raise**.
- **Expect**
  - Step 1: the dialog is titled **Raise a credit note**, its button reads **Raise** — this screen is hand-built, so nothing is called New or Save.
  - Step 2: the **approved** invoice is offered; the **cancelled** one is not, and no `DN-…` number is. Approved sales invoices with lines, and nothing else.
  - Step 3: the line names its product — **Fixture Product <suffix>** — not `Line 1`.
  - Step 4: a draft is listed. **Approve** and **Cancel** are **row actions** on the right, not toolbar buttons; Approve being there *is* the approve gate this case checks. Leave it a draft — approving posts the credit and reverses declared output tax.
- **Data (HTTP):** `GET /api/v1/credit-notes` with `X-Firm-ID` TEST01 lists the draft against the fixture's invoice.
- **Leaves:** a draft credit note in TEST01.

### TC-GRANT-002 — Proforma opens

- **Covers:** plan 21.2
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, Sales → **Proforma**.
- **Expect:** offered, and a real screen — a grid or a proper empty state, never a "coming soon" placeholder. A proforma states what an approved order **will** be charged and **posts nothing**; its number comes from its own `PI` series, not the tax invoice's.
- **Leaves:** a firm admin user.

### TC-GRANT-003 — E-Invoice opens, and never says LIVE

- **Covers:** plan 21.3
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, Sales → **E-Invoice**.
- **Expect:** offered and opens. Wherever a mode is shown it reads **`SANDBOX`**; if it reads LIVE anywhere, stop — that is not cosmetic. `mode` is NOT NULL with no server default on both e-invoice tables, and the sandbox marks every reference it mints `SBX…`. *(TEST01 has registered nothing, so the grid may be empty and show no mode at all; that passes.)*
- **Leaves:** a firm admin user.

### TC-GRANT-004 — Loyalty: the banner states the scheme, and a firm can change it

- **Covers:** plan 21.4, 21.4a
- **Fixture:** `firm-admin`
- **TEST01's scheme is shared by every run.** It starts **off**; switch it back off at the end.
- **Steps**
  1. As the fixture's **Firm admin**, Masters → **Loyalty**. Read the banner.
  2. **Scheme settings** → switch **Scheme is running** on; **Minimum to redeem** `50`; **Points expire** off → Save.
  3. Scheme settings → switch **Scheme is running** off → Save.
- **Expect**
  - Step 1: "No scheme is running: nobody is earning anything."
  - Step 2: the dialog saves and the banner re-reads: "1 points per 100, worth 1 each and never expire. At least 50 before any can be spent."
  - Step 3: back to "No scheme is running…".
  - *Until #399 there was no editor at all: the settings route, the code and the grant existed, and the desktop carried only the read.*
- **Data (HTTP):** `GET /api/v1/loyalty/settings` with `X-Firm-ID` TEST01 after each save.
- **Leaves:** TEST01's scheme off, minimum 50.

### TC-GRANT-005 — Loyalty settings are readable by somebody who cannot change them

- **Covers:** plan 21.4b
- **Fixture:** `loyalty-viewer` — `SALES_MANAGER`, which holds `LOYALTY_VIEW` and not `LOYALTY_MANAGE_SETTINGS`.
- **Steps**
  1. Sign in as the fixture's **Loyalty viewer** → Masters → Loyalty → **Scheme settings**.
  2. **(HTTP)** As them, `PUT /api/v1/loyalty/settings` with the body `GET` returned.
- **Expect**
  - Step 1: it **opens**, read-only, saying "Changing the scheme needs the manage loyalty settings permission." Offered rather than hidden on purpose: whoever is asked why a balance is what it is should reach the rule behind it.
  - Step 2: **403**. Whoever a scheme constrains must not rewrite what it is worth.
- **Leaves:** a sales manager.

### TC-GRANT-006 — TCS settings open, and TCS is off

- **Covers:** plan 21.5
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, Sales → **TCS** → **Settings**; save without changing anything.
- **Expect:** offered, opens and saves. **Collect under section 206C(1H)** is off — it defaults false so shipping the feature charged nobody. Leave it off: on, every receipt in TEST01 collects TCS, and other cases record receipts there.
- **Leaves:** a firm admin user.

### TC-GRANT-007 — The fix was a grant, not a wider gate

- **Covers:** plan 21.6
- **Fixture:** `sales-executive`
- **Steps:** sign in as the fixture's **Seller**; open **Sales**, then **Masters**.
- **Expect:** Sales is offered — `SALES_VIEW` is one of their six codes — with **no** Credit Notes, Proforma, E-Invoice or TCS; Masters has **no** Loyalty. Any of the five appearing means a tab lost its own code and its module gate is carrying it alone.
- **Leaves:** a seller.

### TC-GRANT-008 — The server grants all five

- **Covers:** plan 21.8
- **Fixture:** `firm-admin`
- **Steps (HTTP)** — as the fixture's firm admin with `X-Firm-ID` TEST01: `GET /api/v1/credit-notes`, `/api/v1/proforma-invoices`, `/api/v1/einvoice/registrations`, `/api/v1/loyalty/settings`, `/api/v1/tcs/settings`.
- **Expect:** **200** on all five. They answered 403 before `20260906_0130`. The screens being offered is the desktop honouring the claims; these are the claims being there.
- **Leaves:** a firm admin user.

---

## A cashier can see the till

`CASHIER` holds exactly `RECEIPT_CREATE`, `RECEIPT_VIEW`, `PAYMENT_CREATE` and
`PAYMENT_VIEW`, and was offered **no module at all**: Receipts and Payments are
Finance tabs, Finance was gated on `ACCOUNT_VIEW`, and a tab naming no codes
inherits its module's. Finance now takes any of `ACCOUNT_VIEW`, `RECEIPT_VIEW`,
`PAYMENT_VIEW`, **and every tab names its own code** — both halves are
load-bearing.

Finance's twelve tabs: Chart of Accounts, Control Accounts, Cost Centres,
Profit Centres, Journal Entries, Receipts, Payments, Refunds, Ledgers, Trial
Balance, Profit & Loss, Balance Sheet.

### TC-CASH-001 — A cashier gets Finance, holding Receipts and Payments only

- **Covers:** plan 22.0, 22.1, 22.2, 22.3
- **Fixture:** `cashier` — `CASHIER` alone, no job template. That combination is the whole setup: the seeded Counter Sales template pairs CASHIER with BILLING_EXECUTIVE, which is what hid the bug.
- **Steps:** sign in as the fixture's **Cashier**; read the sidebar; open Finance.
- **Expect:** **Finance** is in the sidebar (before the fix the sidebar was empty), with exactly **Receipts** and **Payments**. **None** of Chart of Accounts, Control Accounts, Cost Centres, Profit Centres, Journal Entries, Ledgers, Trial Balance, Profit & Loss, Balance Sheet, Refunds. Widening the module without gating its tabs would have handed a cashier the ledger.
- **Data (HTTP):** as the cashier with `X-Firm-ID` TEST01, `GET /api/v1/finance/ledger-accounts` → **403**.
- **Leaves:** a cashier.

### TC-CASH-002 — Recording a receipt, with a searchable party picker

- **Covers:** plan 22.4, 22.4a
- **Fixture:** `cashier`
- **Steps**
  1. As the fixture's **Cashier**, Finance → Receipts → **Record Receipt**.
  2. In the party picker, type part of the fixture's customer code (`<SUFFIX>-TI`); clear it; type part of its name (`Till Customer`); then type `zzzz-nobody`.
  3. Choose **<SUFFIX>-TILL**, amount `100`, method Cash → save.
- **Expect**
  - Step 1: the dialog opens with the picker filled. **This failed until 2026-09-15** with "You do not have permission to perform this action." — the picker read `GET /api/v1/customers`, which needs `CUSTOMER_VIEW`, so the role was blocked one step short of the only thing it exists to do. The money screens read `GET /api/v1/receipts/parties` now (#403).
  - Step 2: both narrow the list, each option reading `CODE  Name` on one line; a search matching nobody says so under the field rather than showing an empty sheet.
  - Step 3: the receipt is recorded and listed.
- **Data (HTTP):** as the cashier, `GET /api/v1/customers` → **403**, while `GET /api/v1/receipts/parties?search=<SUFFIX>` → **200** with `id`, `code` and `name` only.
- **Leaves:** a receipt of 100 from the fixture's customer in TEST01.

### TC-CASH-003 — An accountant keeps all twelve

- **Covers:** plan 22.5
- **Fixture:** `accountant` — `ACCOUNTANT` alone. No accountant is seeded in any demo firm.
- **Steps:** sign in as the fixture's **Accountant** → Finance.
- **Expect:** **all twelve** tabs. `ACCOUNTANT` carries `ACCOUNT_VIEW`, `JOURNAL_VIEW`, `RECEIPT_VIEW`, `PAYMENT_VIEW`, `LEDGER_VIEW`, `TRIAL_BALANCE_VIEW`, `PROFIT_LOSS_VIEW` and `BALANCE_SHEET_VIEW`; every code now on a tab is one whoever held `ACCOUNT_VIEW` already had, so nobody lost one.
- **Leaves:** an accountant.

### TC-CASH-004 — A firm administrator keeps all twelve

- **Covers:** plan 22.6
- **Fixture:** `firm-admin`
- **Steps:** sign in as the fixture's **Firm admin** → Finance.
- **Expect:** all twelve tabs.
- **Leaves:** a firm admin user.

---

## The audit trail

`GET /api/v1/audit-logs` reads **one** trail chosen by firm context: no
`X-Firm-ID` plus platform authority gives the platform trail; `X-Firm-ID`
gives that firm's. A firm's trail is **its own store plus the platform rows
that carry its id** — hiring, role edits, promotions — merged by time on the
read. The unit suite cannot see that merge (it builds one schema holding every
table), so these cases are where it is checked.

Settings is offered on any of `SETTINGS_VIEW`, `AUDIT_LOG_VIEW`,
`DIAGNOSTICS_VIEW`; Audit Logs needs `AUDIT_LOG_VIEW` and no firm; Diagnostics
needs `DIAGNOSTICS_VIEW`, which `FIRM_ADMIN` does not hold.

### TC-AUDIT-001 — A platform administrator reads the platform trail

- **Covers:** plan 23.1
- **Fixture:** `platform-admin`
- **Steps:** sign in as the fixture's **Platform admin**, no firm selected → Settings → **Audit Logs**.
- **Expect:** the **platform** trail — user, role and firm administration: `identity.login`, `user.created`, `user.firm_roles_set` and the like, including the fixture's own setup a moment ago. Each row names who did it. *(Answered 403 between 2026-09-05 and 09-06: the designation had moved claims and the check had not.)*
- **Leaves:** a platform administrator.

### TC-AUDIT-002 — Selecting a firm switches to that firm's trail

- **Covers:** plan 23.2
- **Fixture:** `platform-admin`
- **Steps:** as the fixture's **Platform admin**, switch into **TEST01** (the header changes from Platform, the sidebar grows) → Settings → Audit Logs.
- **Expect:** **TEST01's** trail — firm-owned work such as `customer.created`, `sales_invoice.created`, `settlement.receipt.recorded` from fixtures that sold or took money in TEST01 — with platform rows carrying TEST01's id interleaved. Not the platform trail of TC-AUDIT-001: selecting a firm is what sets `X-Firm-ID`.
- **Leaves:** a platform administrator.

### TC-AUDIT-003 — A firm administrator reads their own firm's history, naming people

- **Covers:** plan 23.3, 23.4, 23.5
- **Fixture:** `firm-admin`
- **Steps:** sign in as the fixture's **Firm admin** → **Settings**; read Audit Logs; look for Diagnostics.
- **Expect**
  - Settings opens with **Audit Logs** in it. It used to open empty — offered on `SETTINGS_VIEW` with both tabs demanding codes the role lacked.
  - TEST01's history and nothing else. **Every row names the person who did it** and, where the subject is a person, who it was done to (#407, #409).
  - **No Diagnostics.** Error reports are telemetry for whoever maintains the product, not something a firm owns.
- **Leaves:** a firm admin user.

### TC-AUDIT-004 — A promotion lands in the firm's trail, in time order, and a filter reaches both stores

- **Covers:** plan 23.4a, 23.4b, 23.4c
- **Fixture:** `manual-hire`
- **Steps**
  1. As the fixture's **Firm admin**: Masters → Customers → New `<SUFFIX>-A`, name `Audit Before <suffix>` → Save.
  2. Administration → Users → **Manual Hire (<suffix>)** → **Apply job template** → Counter Sales → Apply.
  3. Customers → New `<SUFFIX>-B`, name `Audit After <suffix>` → Save.
  4. Settings → **Audit Logs**. Read the top rows.
  5. Filter by action `user_template.applied` — **typed in full**.
- **Expect**
  - Step 4: from the top, `customer.created` (Audit After), `user_template.applied` and `user.roles_set` (both naming Manual Hire), `customer.created` (Audit Before) — **strictly descending timestamps straight through**. The promotion is written to the *platform* store (user administration is a platform path) and the customers to TEST01's; nothing marks which came from where. A block of user-administration rows at one end and customers in another means the stores were concatenated, not merged. The promotion names the template **and the role codes it granted** — `role_codes` beside `role_ids`, `template_code` beside `template_id`.
  - Step 5: the promotion is found. A filter that reached one store and not the other would answer a half-truth that reads as correct because something came back. *(Exact match: `user` finds nothing — BACKLOG 31.17.)*
- **Data (HTTP)**, as the firm admin with `X-Firm-ID` TEST01: `GET /api/v1/audit-logs?page_size=10` shows the order; `?action=user_template.applied` returns the row with `after_data.role_codes: ["BILLING_EXECUTIVE", "CASHIER"]`.
- **Leaves:** two customers in TEST01 and Manual Hire on Counter Sales.

### TC-AUDIT-005 — The platform trail needs platform authority

- **Covers:** plan 23.6
- **Fixture:** `firm-admin`
- **Steps (HTTP):** `GET /api/v1/audit-logs` as the fixture's firm admin with **no** `X-Firm-ID`.
- **Expect:** **403**.
- **Leaves:** a firm admin user.

### TC-AUDIT-006 — Somebody with none of the three codes has no Settings at all

- **Covers:** plan 23.7
- **Fixture:** `sales-executive`
- **Steps:** sign in as the fixture's **Seller**; read the sidebar.
- **Expect:** **no Settings** — the module absent, not an empty Settings. A module that opens and does nothing reads as broken rather than withheld.
- **Leaves:** a seller.

---

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

- **Covers:** plan 24.1 – 24.7
- **Fixture:** `outsider` — Outsider works in TEST02 alone.
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Administration → Users → **Add existing user**, with no row selected.
  2. Type `t0`.
  3. Type `<suffix>.outs`; then clear and type `Outsider (<suffix>)`.
  4. Type `<suffix>`.
  5. Type `zzqq-nobody`.
- **Expect**
  - Step 1: a search box. Offered with nothing selected — the person is not in the grid, which is the point.
  - Step 2: nothing searched: "Type at least 3 characters to look somebody up."
  - Step 3: Outsider, found by **email** and then by **name**. A result shows the name, the email, and **nothing else** — no firm is named anywhere on it.
  - Step 4: Outsider, and **Fixture Firm Admin (<suffix>)** marked **Already in this firm** with Add disabled.
  - Step 5: "Nobody matches. They may not have an account yet — use New."
- **Data (HTTP):** as the firm admin, `GET /api/v1/users/lookup?q=<suffix>` → each row `{id, full_name, email, already_a_member}` and nothing more.
- **Leaves:** unchanged.

### TC-LOOK-002 — Adding them, with a job

- **Covers:** plan 24.8
- **Fixture:** `outsider`
- **Steps:** as the fixture's **Firm admin**, Add existing user → `<suffix>.outs` → pick Outsider → **Job template** Counter Sales → Add.
- **Expect:** "Outsider (<suffix>) was added to this firm." They appear in TEST01's grid. The Job template field's helper reads "Optional. You can set their roles afterwards."
- **Data**
  ```sql
  select f.code, uf.is_primary from platform.user_firms uf
  join platform.firms f on f.id = uf.firm_id
  join platform.users u on u.id = uf.user_id
  where u.email = '<suffix>.outsider@fixtures.local' and uf.is_deleted = false;
  ```
  TEST02 (primary) and TEST01 — adding merged, it did not replace.
- **Leaves:** Outsider in TEST01 as Counter Sales.

### TC-LOOK-003 — Their profile is not yours; their roles here are

- **Covers:** plan 24.9, 24.9a, 24.10
- **Fixture:** `outsider-added` — Outsider is already in TEST01 as Counter Sales.
- **Steps**
  1. As the fixture's **Firm admin**, select **Outsider (<suffix>)** → **Edit**; double-click the row; the context menu's Edit.
  2. Select them → **Apply job template** → Warehouse → Apply. Then **Roles by firm**.
  3. Sign in as the fixture's **Platform admin** → Users → Outsider → Edit.
- **Expect**
  - Step 1: all three open **read-only**, the subtitle saying they also work in another firm, so their profile is managed by a platform administrator, and Roles by firm is what to use.
  - Step 2: both work. Roles by firm shows **one section, TEST01** — not TEST02, though they work there: the dialog offers only firms you hold `USER_CREATE` in.
  - Step 3: **editable** — correct, not a hole. A platform administrator sees every firm, so nothing is hidden from them, and they are exactly who step 1's message points to.
- **Leaves:** Outsider on Warehouse in TEST01.

### TC-LOOK-004 — Adding somebody tells you nothing about their other firms

- **Covers:** plan 24.11, 24.12, 24.13
- **Fixture:** `outsider-added`
- **Steps (HTTP)**
  1. As the fixture's firm admin (`X-Firm-ID` TEST01): `GET /api/v1/users/{Outsider's id}/firms`.
  2. As the fixture's platform admin: the same.
  3. As the platform admin: `GET /api/v1/users/{id}/firms/{TEST02 id}/roles` and `.../{TEST01 id}/roles`.
- **Expect**
  1. **Only TEST01.** It returned every membership until 2026-09-06, on a route gated only by `ROLE_VIEW`.
  2. Both firms, TEST02 primary.
  3. TEST02 still exactly `CASHIER`; TEST01 `BILLING_EXECUTIVE` and `CASHIER` from Counter Sales. Adding them to TEST01 touched nothing in TEST02.
- **Leaves:** unchanged.

### TC-LOOK-005 — Reaching across firms is not reading your own people

- **Covers:** plan 24.14, 24.15, 24.16
- **Fixture:** `sales-executive` and `firm-admin` (two runs, or any two)
- **Steps**
  1. Sign in as the `sales-executive` fixture's **Seller**; look for Administration → Users.
  2. **(HTTP)** As the seller with `X-Firm-ID` TEST01: `GET /api/v1/users/lookup?q=fixtures`.
  3. **(HTTP)** As the `firm-admin` fixture's firm admin: `GET /api/v1/users/lookup?q=`, then `?q=fixtures.local&page=2&page_size=2`.
- **Expect**
  1. No Administration at all, so no Add existing user.
  2. **403** — the lookup needs `USER_CREATE`, deliberately not `USER_VIEW`.
  3. **422**, "Type at least 3 characters to look somebody up." — an empty term is the shortest of all. Page 2: **empty**, and a plain `?q=fixtures.local` returns **10** however many match: a firm caller gets "is this them?", not "who works here?".
- **Leaves:** unchanged.

### TC-LOOK-006 — A platform administrator gets the directory

- **Covers:** plan 24.17, 24.18, 24.19, 24.20
- **Fixture:** `outsider`
- **Steps**
  1. Sign in as the fixture's **Platform admin**, switch into **TEST01** → Users → **Add existing user**.
  2. Type `e`; clear the box.
  3. Type `<suffix>.outs`, pick Outsider, Add, close. Open Add existing user again and type `<suffix>`.
  4. **(HTTP)** As the platform admin with `X-Firm-ID` TEST01: `GET /api/v1/users/lookup?q=&page=1&page_size=2`.
- **Expect**
  - Step 1: the dialog **opens already listing** everyone with an account who is not in TEST01, no typing. Helper: "Leave blank to list everyone not yet in this firm." TEST01's own people are **not** listed, and no platform administrator is — the fixture's firm admin and platform admin are both absent.
  - Step 2: filtered on one character; the three-character rule is a firm caller's. Clearing brings the full list back.
  - Step 3: Outsider is added, and **absent** the second time. A firm caller's lookup *flags* a member; a platform caller's directory *excludes* them.
  - Step 4: two rows and a `pagination` block whose `total_records` is everybody not in TEST01.
- **Leaves:** Outsider in TEST01 with no roles there.

### TC-LOOK-007 — User-Firm Assignments is a platform administrator's tab

- **Covers:** plan 24.21, 24.22
- **Fixture:** `template-offering` (a firm admin and a platform admin)
- **Steps:** open Administration as the fixture's **Firm admin**; then as its **Platform admin**, with no firm and then with TEST01 selected.
- **Expect:** the firm admin sees Users, Roles & Permissions and User Templates — **no User-Firm Assignments**; Users → Edit → Firms and Add existing user are their ways to the same thing. The platform admin sees **User-Firm Assignments**, with the Firm filter, either way. A tab-level `requiresPlatformAdmin`, because a platform administrator passes code checks by designation.
- **Leaves:** unchanged.

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
  - Step 4: the screen **loads** with no error — whatever orders fixtures have raised in TEST01, or none. Before the fix this module was offered and this screen failed.
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

## Adding a case

Every section is here now, so what follows is for a **new** case — a new
feature, or a defect worth guarding against by hand.


1. List what each row needs to exist before it starts — that is the fixture.
2. Add the fixture to `backend/scripts/test_fixture.py`, built from the API, composing the existing blocks where it can.
3. **Run the fixture and drive every expectation against the backend** before writing it down; take sidebar and tab lists from `ModuleVisibility`, not from the permission table.
4. Give each case a stable `TC-AREA-NNN` id and the six parts above. IDs do not change when cases are added, which plan section numbers did.
5. Write it here, at the end of the section it belongs to. Do not add rows to `MANUAL_UI_TEST_PLAN.md` — that file is pointers now, so there is one version and not two.
6. Use `by_code` for a firm's HO and MAIN, never a list's first row, and set a product's fields at creation: a product `PUT` replaces every editable field.
