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
None was fixed while the cases were being written; **all eight were fixed on
2026-09-16**, each with a test that fails when the fix is reverted. Every note
now opens with what changed, and the case steps expect the fixed behaviour —
a case that used to say "fails today" has been corrected.

A ninth, **D-27-5**, was found later the same day while clearing the runs'
leftover firms rather than while writing a case, and was fixed the same way.
TC-FIRM-017 is the case for it.

**Brought up to release 1.3.0 on 2026-10-04.** Every menu path in a case is the
1.3.0 menu (the light menu and the Settings page, built in `desktop/lib/phase2/menu_layout.dart`):
`Sell > Quotations` is the **Sell** drop-down on the menu bar; a screen that is not
daily work is `Sell > All Sell screens > Documents > Proforma`; the short list
is `Sell > Returns & notes > Credit Notes`; and the gear at the right of the bar
opens **Settings**, whose parts are Settings (Firm, Selling, Buying, Stock, Tax,
Business profile, This PC and me), **Set up** (Pricing, Territories & routes,
Account structure, Party lists, Item lists, Locations) and **Platform** (People,
Firms, Agency, System): `Settings > Set up > Pricing > Price Lists`,
`Settings > Platform > System > Audit Logs`. The **Admin** area is gone from the
bar. Case ids are unchanged. Release 1.3.0 includes 1.2.0, which was never shipped.

**Brought up to the fixes of 2026-10-05 and 06 on 2026-10-06.** The buying and
selling cases were corrected to what the application does after the fixes found
by driving it over HTTP (the check files `docs/qa/*_API_CHECK_*`), and nineteen
cases were added: **TC-BUY-093 to 098** (returns to the supplier: free goods,
the same goods going back once, the batch, the import, and the self-invoice
number), **TC-SELL-088 to 095** (a saved counter bill changed before approval,
quantity 0 and a bill of 0.00, a limited coupon, a bill that is not a whole
paisa, returns never billed, reservations by batch), **TC-CUST-007 to 010**
(who may set a customer's money terms, and the opening balance as a bill) and
**TC-CONF-009** ("today" is the firm's own day). Their expectations were driven
over HTTP; their screens have not been walked. Existing ids are unchanged.

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
was written, and the menu lists were taken from the desktop's own
`ModuleVisibility` and `MenuLayout` logic (release 1.3.0, the light menu)
rather than inferred from permission codes.
**Exception:** the cases added on 2026-10-02 and 2026-10-03 say in their own
text that they were written from the code and not yet driven. The 2026-10-03
cases cover the backlog items built in Waves 1 to 3 (`docs/BACKLOG_BUILD_PLAN.md`);
each names its backlog id and decision number under **Covers**. Nineteen cases
that had been added to `docs/qa/` by hand on 2026-10-02 (TC-MAST-009 and 010,
TC-BUY-017 and 018, TC-SELL-022 to 026, TC-TERR-006 and TC-COMP-009 to 019) were
brought back into this file on 2026-10-03, in the wording of the QA suite
(a *Preconditions* line instead of a *Fixture* line), so that regenerating the
suite no longer drops them.

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
  1. Sign in as the fixture's **Platform admin**; switch into **TEST01** → Masters > Customers; search `<SUFFIX>`.
  2. With the list open, switch to **TEST02**.
- **Expect:** step 1 shows `<SUFFIX>-ONE`; after the switch the list reloads by itself and shows `<SUFFIX>-TWO` — **no row from TEST01 survives**, not even for a moment.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 and §14.17 — the switch writes only `platform.user_preferences.default_firm_id` (and an empty `user_preferences.updated`); each list then reads the other firm's store.
- **Leaves:** unchanged.

### TC-SESS-002 — An idle session refreshes quietly, and a signed-out one leaves nothing behind

- **Covers:** plan 2.4, 2.5
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**; open Masters > Customers. Leave the application idle for **more than 15 minutes** (the access token's lifetime, `AGENCY_JWT_ACCESS_TOKEN_MINUTES`).
  2. Click **Refresh**.
  3. Sign out; press the mouse's Back button or Alt+Left.
- **Expect**
  - Step 2: the list reloads; you are **not** asked to sign in again — the client refreshes once on a 401 and repeats the request.
  - Step 3: the sign-in screen stays; no cached screen is reachable.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.1 — the quiet refresh revokes the old `refresh_tokens` row and inserts the next with `replaced_by_id` pointing at it (audit `identity.refresh`); sign-out sets `revoked_at` on one row (audit `identity.logout`) and leaves the access token good for its 15 minutes (D-IDN-10).
- **Leaves:** a firm admin user.

### TC-SESS-003 — Wrong passwords, a lockout, and a lock that counts down

- **Covers:** plan 2.6, 2.7
- **Fixture:** `lock-target`
- **Steps**
  1. On the sign-in screen, try `nobody.<suffix>@fixtures.local` / `Wrong@Password1`.
  2. Try the fixture's **Target** with `Wrong@Password1` **four** times.
  3. A fifth time.
  4. Now the fixture's password (the right one).
  5. Watch the banner.
- **Expect**
  - Steps 1–2: "Invalid email or password." every time, the unknown address included, and each takes **about as long** as the others (~2 seconds on this machine, measured) — a wrong address and a wrong password must not feel different.
  - Step 3: "This account is locked after too many failed sign-in attempts. You can try again in 15:00." and the clock **counts down** a second at a time.
  - Step 4: refused the same way, with the time left. The lock is checked before the password is.
  - Step 5: at zero, "The lock on this account has lifted. You can sign in now." *(If you cannot wait, TC-SESS-004 lifts it.)*
- **Data (HTTP):** the fifth attempt's refusal is **401** with code `account_locked` and `details.retry_after_seconds` 900 and `locked_until`. Table check: `scripts/sql/check_identity_data.sql` §5 shows the fifth as `locked` and the sixth as `account_locked`.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.1 — each attempt is one `login_history` row (`user_id` null for the unknown address); the fifth sets `users.locked_until` and `failed_login_attempts` 5.
- **Leaves:** a locked target (for 15 minutes).

### TC-SESS-004 — A firm administrator clears a lock

- **Covers:** plan 2.8, 2.9
- **Fixture:** `lock-target`
- **Steps**
  1. Lock the fixture's **Target** with five wrong passwords (TC-SESS-003 steps 2–3).
  2. Sign in as the fixture's **Firm admin** → Settings > Platform > People > Users → Edit **Lock Target (<suffix>)** → tick **Clear login lock (Account Lock)** → Save.
  3. Sign in as the target with the fixture's password.
- **Expect:** step 3 signs in at once — the lock cleared and the failed count reset. *(2.9's other way, waiting fifteen minutes, ends the same; TC-SESS-003 step 5 shows it.)*
- **Data (HTTP):** the form sends `PATCH /api/v1/users/{id}` with `{"unlock": true}`.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.3 — `users.locked_until` null, `failed_login_attempts` 0, `authorization_version` +1; audit `user.updated` with TEST01 — a before (name, active flag) and no after, so the unlock itself is not named.
- **Leaves:** an unlocked target.

### TC-SESS-005 — Inactive and expired accounts are told why

- **Covers:** plan 2.10
- **Fixture:** `lock-target`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → Edit the target → untick **Active** → Save. Sign in as the target with the right password; then with `Wrong@Password1`.
  2. Edit again: tick Active, set **Expires at** to yesterday → Save. Sign in with the right password; then a wrong one.
  3. Clear Expires at → Save; sign in.
- **Expect**
  - Step 1, right password: "This account is inactive. Ask an administrator to reactivate it." Login history says `account_unavailable`.
  - Step 2, right password: "This account has expired. Ask an administrator to extend it."
  - Step 3: signs in.
  - **With a wrong password, all three answer "Invalid email or password."** — the state is named only to somebody who typed the right one. Fixed 2026-09-16; see defect **D-2-1**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.1 and §15.3 — each Save is `user.updated` and moves `authorization_version`; the right password on an inactive or expired account writes `login_history` `failed` / `account_unavailable`, a wrong one `invalid_credentials`.
- **Leaves:** the target active, no expiry.

### TC-SESS-006 — A password somebody else set must be changed

- **Covers:** plan 2.11
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → New: `<suffix>.newbie@fixtures.local`, password `Welcome@123456`, **Require password change** on, in TEST01 → Save.
  2. Sign in as them. On the change-password screen try new passwords `Short@1`, then `LongEnoughPassw0rd`, then `Newbie-Passw0rd!`.
- **Expect:** the change-password screen and nothing else reachable. `Short@1` refused ("Use at least 12 characters."); `LongEnoughPassw0rd` refused ("Include a symbol."); `Newbie-Passw0rd!` accepted and the app opens.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.2 in `platform` — the accepted change inserts one `password_history` row (the old hash), clears `force_password_change`, bumps `authorization_version` and writes `identity.password_changed`; the refused tries write nothing.
- **Leaves:** a TEST01 user with their own password.

### TC-SESS-007 — Deleting somebody releases their address; the new account is a new person

- **Covers:** plan 2.13
- **Fixture:** `lock-target`
- **Steps**
  1. As the fixture's **Platform admin**, Settings > Platform > People > Users → select the target → **Delete**.
  2. Settings > Platform > People > Users → New with the same email, any name and password, no firms or roles → Save.
- **Expect:** step 1 — gone from the grid; Settings > Platform > System > Audit Logs keeps the row. Step 2 — the address is accepted again (soft delete releases it) and the new account has **no** roles and **no** firms.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.3 in `platform` — step 1 sets `users.is_deleted` and bumps the version (audit `user.deleted`, no firm from a platform administrator); step 2 is a second `users` row on the same address, which `UQ_users_email_active` allows because it is partial on `is_deleted = false`.
- **Leaves:** a deleted target and a new, empty account on the same address.

### TC-SESS-008 — Restoring a deleted person as they were

- **Covers:** plan 2.13b, 2.13c
- **Fixture:** `lock-target`
- **Steps**
  1. As the fixture's **Platform admin**, delete the target. Settings > Platform > People > Users → **Status** filter → **Deleted** → open them.
  2. **Restore** (dialog footer). Sign in as the target with the fixture's password.
  3. Delete the target again; create a **new** account with the same address; Status → Deleted → open the old one → Restore.
- **Expect**
  - Step 1: status **Deleted**, Edit and Delete dead, View opens.
  - Step 2: back in the grid with TEST01 and SALES_EXECUTIVE; the old password works.
  - Step 3: refused — "Another live account now holds this email address. Delete that account first if this is the one to keep." Restore before re-onboarding, not after.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.3 in `platform` — Restore clears `is_deleted` and writes `user.restored` with no firm; the `user_firms` and `user_roles` rows were never touched, which is why they come back; the refusal writes nothing.
- **Leaves:** a deleted target and a live account on its address (after step 3).

### TC-SESS-009 — Deleted people are a platform administrator's; inactive ones anybody's

- **Covers:** plan 2.13d (both rows)
- **Fixture:** `lock-target`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → open the **Status** filter.
  2. **(HTTP)** As the firm admin, `GET /api/v1/users?deleted_only=true&search=<suffix>`.
  3. Edit the target: untick **Active** → Save. Status → **Inactive**.
  4. As the fixture's **Platform admin**: Status → **Inactive**; then also pick the firm **TEST01**.
- **Expect**
  - Step 1: Active and Inactive, **no Deleted**; and no **Restore** anywhere. A deleted person's memberships still place them in a firm, and a firm's grid must not list them.
  - Step 2: **live** rows only — the flag is ignored for a firm caller.
  - Step 3: the target, and nobody active.
  - Step 4: the switched-off people from every firm, the target among them and no deleted ones; with TEST01 as well, only TEST01's inactive people.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.3 — reads only, except step 3's `user.updated`.
- **Leaves:** an inactive target.

### TC-SESS-010 — Who may not be deleted

- **Covers:** plan 2.14
- **Fixture:** `shared-member` (for the shared person) and `platform-admin-member` (for a platform administrator to aim at)
- **Steps**
  1. As the `shared-member` fixture's **Firm admin**, Settings > Platform > People > Users → select **Shared Member (<suffix>)** → Delete.
  2. **(HTTP)** As any platform administrator, `DELETE /api/v1/users/{id of the platform-admin-member fixture's admin}`.
- **Expect**
  - Step 1: refused — "This person also works in another firm, so their profile is managed by a platform administrator. You can still set their roles and job template in your own firm."
  - Step 2: **422**, "Platform administrator users cannot be deleted."
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.3 — both refusals write nothing.
- **Leaves:** unchanged.

### TC-SESS-011 — Setting somebody else's password

- **Covers:** plan 2.15, 2.16, 2.17
- **Fixture:** `lock-target`
- **Steps**
  1. Lock the target (five wrong passwords).
  2. As the fixture's **Platform admin** → Settings > Platform > People > Users → open the target → **Reset password** (dialog footer) → `Temp-Passw0rd!!`, "Require a new password" on → Save. Sign in as the target with it.
  3. Reset again to `Handover-Passw0rd!` with "Require a new password" **off**; sign in with it.
  4. As the platform admin, open **your own** row → Reset password.
  5. As the fixture's **Firm admin**, open the target.
- **Expect**
  - Step 2: the lock is gone — they sign in at once and land on the change-password screen. Any other window of theirs is signed out.
  - Step 3: the app opens straight away: a handover, the password theirs to keep.
  - Step 4: refused — "Change your own password from My profile, where the current one is asked for."
  - Step 5: **no Reset password** in the footer. **(HTTP)** `POST /api/v1/users/{id}/password` as the firm admin → **403**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.2 in `platform` — each reset inserts the old hash into `password_history`, sets `force_password_change` as chosen, clears the lock and bumps `authorization_version`; audit `user.password_reset` with `force_password_change`, no firm. The route takes the designation of either reach and never looks at the target's (D-IDN-2).
- **Leaves:** the target on `Handover-Passw0rd!`.

### Known defects found while writing these cases

- **D-2-1 — An inactive or expired account named its state to a wrong password. Fixed 2026-09-16.** Driven: a wrong password on an inactive account answered "This account is inactive…", and on an expired one "This account has expired…", both with their state codes. That tells a stranger the address exists, belongs to somebody real and — for an expired one — may be worth trying again later, which is the enumeration oracle the throwaway-hash verification exists to close, given away by the message instead of by the clock. `IdentityService.login` now settles the state before the password and acts on it **after**, so a wrong password gets the same refusal every other wrong password gets while the right one still says plainly what is wrong (the 18.1/18.2 decision was about the person holding the right password). The lockout deliberately stays **in front** of the password: a locked account must cost the same whatever was typed. `test_a_wrong_password_never_names_the_state` in `tests/unit/test_identity_hardening.py`.

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
  1. Sign in as the fixture's **Platform admin** → switch into **TESTSH1** → Masters > Customers → search `<SUFFIX>`.
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
  1. As the fixture's **Platform admin** in **TEST01**, Masters > Customers → search `Isolation One <suffix>`.
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
  1. Sign in as the fixture's **Firm admin** (TEST01) → Reports > Operational → **Sales order register**; find the fixture's order (customer **Fixture Buyer <suffix>**).
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — the refusal writes nothing. Firm-owned routes check the membership in `app/common/scope.py`; the identity routes take `X-Firm-ID` unchecked, which a holder of a global code could use (D-IDN-7).
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
  1. Sign in as the fixture's **Firm admin** → Masters > Customers → open `<SUFFIX>-CM` → Edit.
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
  One address, `version` up by one. *(Driven over HTTP: a PUT naming only the four required fields and the phone leaves all of these as they were.)* `docs/DATA_TRAIL_BY_OPERATION.md` §16.2 has what the edit writes: the partial dump, the two collections guarded on `model_fields_set`, and the one `customer.updated` snapshot that does **not** say which field moved.
- **Leaves:** the customer with a new phone number.

### TC-CUST-002 — The place picker loads each rung from the one above

- **Covers:** plan 4.3, 4.4
- **Fixture:** `customer-master` — TEST01's store holds India and, under it, this run's own **State <suffix> → District <suffix> → City <suffix>**.
- **Steps**
  1. As the fixture's **Firm admin**, Masters > Customers → New: code `<SUFFIX>-GEO`, name `Place Check <suffix>`, type Business, currency INR. In the address: country **India**, then **State <suffix>**, then **District <suffix>**, then **City <suffix>**; line 1 and PIN filled.
  2. Save; reopen.
- **Expect**
  - Step 1: each rung loads **immediately** after the one above is chosen — choosing the country fills the states at once, not after a second click. *(It shipped loading from the value the parent had not rebuilt yet.)*
  - Step 2: the place is still chosen, and the text fields agree with it: city `City <suffix>`, state `State <suffix>`, country `IN`. The ids are the truth; the text is derived from them.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §16.1 in `test_fixtures` — the create writes one `customers` row, one `customer_addresses` row whose free text is derived from the ids by `_apply_place`, and `customer.created`; a rung that does not belong under the one above is refused with nothing written.
- **Leaves:** a second customer.

### TC-CUST-003 — The credit policy: readable by whoever it warns, writable by one permission

- **Covers:** plan 4.5
- **Fixture:** `customer-master`
- **Steps**
  1. As the fixture's **Firm admin**, Masters > Customers → toolbar **Settings**.
  2. Sign in as the fixture's **Seller** (`SALES_EXECUTIVE`) → Masters > Customers → Settings.
  3. **(HTTP)** As the seller, `PUT /api/v1/customers/credit-settings` with `{"enforcement": "OFF", "warn_at_percent": "80", "block_at_percent": "100"}`.
- **Expect**
  - Step 1: **Credit policy** — "When a customer reaches their limit" **Warn**, warn at 80, block at 100 (TEST01 has no policy row, so the default applies), editable.
  - Step 2: the dialog **opens read-only**, with "Changing the policy needs the manage customer settings permission." *(The plan said the action is not offered to a salesperson; it is offered on `CUSTOMER_VIEW` on purpose — someone the policy warns should see the rule behind the warning.)*
  - Step 3: **403**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.14 in `test_fixtures` — both reads write nothing (TEST01 has no `credit_control_settings` row, so the defaults answer), and the refused PUT writes nothing either. A permitted save writes one row and an audit `CREATE` (`entity_type` `CreditControlSettings`). The limit itself is §16.2: moving it now takes `CUSTOMER_MANAGE_SETTINGS` too (D-CFG-17, fixed), and so do the customer's standing discount, opening balance, payment terms and cash-discount terms, on create and on edit (D-SELL-76; TC-CUST-007).
- **Leaves:** unchanged.

### TC-CUST-004 — A credit limit warns and does not block

- **Covers:** plan 4.6
- **Fixture:** `customer-master`
- **Steps**
  1. As the fixture's **Firm admin**, edit `<SUFFIX>-CM`: credit limit `1` → Save.
  2. Sell > Sales Orders → New: customer `<SUFFIX>-CM`, one line `<SUFFIX>-P` quantity 2 at 100 → Create draft → **Approve**.
- **Expect:** a warning names the exposure — "Master Check <suffix> would be at …% of a 1.00 credit limit, leaving … available." — and the order **is approved**. TEST01 is in warn mode (no policy row), so nothing blocks.
- **Data (HTTP):** `GET /api/v1/customers/{id}/credit-status?amount=<order total>` → `status: WARNING`, `would_block: false`. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §16.2 for the limit (the save needs `CUSTOMER_MANAGE_SETTINGS`) and §11.6 for what approval does with it; the status check writes nothing.
- **Leaves:** an approved order for 2, and a customer with a limit of 1.

### TC-CUST-005 — Statement and ageing agree with the account

- **Covers:** plan 4.7, 4.8
- **Fixture:** `invoiced-part-paid` — Fixture Buyer <suffix> owes 590 on one invoice and has paid 200 against it.
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Masters > Customers → `<SUFFIX>-C` → **Statement** for this financial year.
  2. **Ageing**.
- **Expect**
  - Step 1: opening 0.00; the invoice (debit 590, balance 590), then the receipt (credit 200, balance **390**); closing **390.00** — the customer's current balance. Lines are in date order and the running balance is recomputed, not read off the stored snapshot.
  - Step 2: total outstanding **390.00**, all of it in the 0–29 day bucket; the buckets sum to the total, and the reconciliation line has nothing to explain (no unapplied credits, no charges not billed).
- **Data (HTTP):** `GET /api/v1/customers/{id}/statement?from_date=2026-04-01&to_date=2027-03-31` and `GET /api/v1/customers/ageing`. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §12.10 — both read `customer_receivable_transactions` (the ageing, the allocations too) and write nothing; its query recomputes the running balance.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §16.5 in `test_fixtures` — the assignment is one column on `customers` and one `customer.updated`; the refused delete writes nothing; a segment that *is* retired keeps its code for ever and is still accepted on a new customer, another firm's included (D-MST-3, D-MST-11).
- **Leaves:** the customer in the Wholesaler segment.

**Money terms and the opening balance (added 2026-10-06).** A customer's credit limit, standing discount, opening balance, payment terms and cash-discount terms are *money terms*: setting or changing one needs the manage customer settings permission (`CUSTOMER_MANAGE_SETTINGS`), which the **Firm Administrator**, **Firm Manager** and **Accounts** jobs hold and **Field Sales**, **Sales Manager** and **Customer Support** do not. Any case that creates or edits a customer with those figures signs in as the firm administrator or a Firm Manager.

### TC-CUST-007 — A customer's money terms need the settings permission

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-SELL-76, #1204 (D-CFG-17 widened to every money term)
- **Fixture:** `customer-master`
- **Also needs:** a **Sales Manager** and a **Firm Manager** user in the firm, beside the fixture's Firm admin and Seller (Field Sales). The fixture's customer `<SUFFIX>-CM` carries credit limit 50,000, payment terms 30 days and standing discount 7.5%.
- **Steps**
  1. As the fixture's **Seller**: Masters > Customers → **New**. Look at **Credit limit**, **Default discount %**, **Opening balance**, **Payment terms (days)**, **Cash discount (days)** and **Cash discount %**. Type a code and a name only → Save.
  2. **(HTTP)** As the seller, `POST /api/v1/customers` five times, each with one of `credit_limit` 50000, `opening_balance` 1500, `payment_terms_days` 30, `cash_discount_percent` 2 with `cash_discount_days` 10, `default_discount_percent` 12.5. Then once with every one of them sent as 0.
  3. As the **Sales Manager**: Masters > Customers → `<SUFFIX>-CM` → **Edit**. Look at the same six boxes. Change only the name → Save.
  4. **(HTTP)** As the Sales Manager, `PUT /api/v1/customers/{id}` with the whole record and one figure changed: payment terms 30 to 45; then the credit limit; then the standing discount; then each set to 0.
  5. As the Sales Manager: Masters > Customers → **Import**, a file that names `<SUFFIX>-CM` with *update existing* chosen and a changed credit limit, credit days, opening balance or discount; then a file that changes only its name.
  6. As the **Firm Manager**, then the **Firm admin**: edit `<SUFFIX>-CM` and change payment terms to 45 → Save.
- **Expect**
  - Step 1: the six boxes are locked, with "Set by somebody with the manage customer settings permission." beneath; the customer saves with none of them.
  - Step 2: each of the five is refused with **403** and nothing is created: "<code>: giving a customer a credit limit needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS). Leave it at zero, or ask somebody who holds it.", and the same sentence for "an opening balance", "credit days", "cash-discount terms" and "a standing discount". Every term sent as zero is not a term: 201.
  - Step 3: the six boxes are locked on an edit too; the name saves and the terms are as they were.
  - Step 4: each is refused with **403**, "Changing a customer's credit days needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)." (and "…credit limit…", "…standing discount…"); setting one to zero is a change and is refused the same way. After every refusal the customer is unchanged.
  - Step 5: the import reports the problem on the row in the same words and updates nothing; the file that changes only the name updates the name. The batch import (`POST /api/v1/customers/import`) answers the same way.
  - Step 6: the Firm Manager's and the administrator's changes save.
- **Data:** a refusal writes nothing: the customer's `version`, the journal count and the opening-bill count do not move. `grep -rn CUSTOMER_MANAGE_SETTINGS backend/app --include=*.py` lists every place that asks for the code.
- **Leaves:** one more customer; `<SUFFIX>-CM` with payment terms 45.

### TC-CUST-008 — An opening balance typed on the customer is collected as a bill

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-MST-13 (#1205)
- **Fixture:** `customer-master`
- **Also needs:** nothing beyond the fixture's Firm admin; the case makes its own customers.
- **Steps**
  1. As the fixture's **Firm admin**: Masters > Customers → **New**: code `<SUFFIX>-OB1`, a name, **Opening balance** `1500`, **Payment terms (days)** `30` → Save. Open it again and read **Opening bills**. Accounts > Journal Entries.
  2. Sell > Receipts → **Record Receipt** → `<SUFFIX>-OB1`: read the bills offered. Sell > All Sell screens > Money > **Collection Sheet**. Masters > **Statements** → the customer's ageing and statement.
  3. Record Receipt: Amount `2000`, applied to the row → Save. Then Amount `600`, Cash, applied to the row → Save. Read the three lists and the customer again.
  4. Masters > Customers → `<SUFFIX>-OB1` → Opening bills → **Cancel** on the row, with a reason.
  5. In **Opening bills** press **Add opening bill**: any reference, 250 → Save.
  6. New customer `<SUFFIX>-OB2` with **Opening balance** `-300` → Save; read its Opening bills.
- **Expect**
  - Step 1: Outstanding **1,500.00**. Opening bills holds **one** row, 1,500.00, standing for the figure typed. One journal, reference `<code>-OB`: Dr 1100 Trade Receivables 1,500.00 / Cr 3000 Opening Balance Equity 1,500.00.
  - Step 2: Record Receipt lists one row **Opening balance**, 1,500.00, due the day it was entered plus 30 days; the collection sheet and the ageing list the same row, and the statement shows the opening balance once, not twice.
  - Step 3: 2,000 is refused: "Invoice Opening balance has 1500.00 outstanding, so 2000.00 cannot be allocated to it." The 600 is taken (Dr 1000 Cash 600.00 / Cr 1100 Trade Receivables 600.00) and the row reads **900.00** on Record Receipt, the collection sheet and the ageing, and the customer's Outstanding is 900.00. Paid in full, the row leaves all three.
  - Step 4: refused: "OBC-… is the opening balance entered on the customer, not a bill of its own. Set the customer's opening balance to 0 to take it back; reverse any receipt taken against it first."
  - Step 5: refused: "… carries an opening balance of 1500.00. Enter the opening balance either as one figure on the customer or bill by bill, not both…"
  - Step 6: a negative opening balance (money the firm owes the customer) makes no bill.
- **Data:** `GET /api/v1/customers/{id}/opening-bills` returns the row with `covers_master_balance` true; `GET /api/v1/receipts/outstanding?customer_id=` marks it `is_opening_bill`. The due date is fixed when the figure is entered: changing the payment terms afterwards does not move it.
- **Leaves:** two customers, one owing 900.00 on its opening balance, and a receipt of 600.00.

### TC-CUST-009 — Correcting an opening balance: after a reversed receipt, and after a cancelled invoice

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.*** The cancelled-invoice half (D-MST-16) is unit-tested and **has not been driven on a running server**.

- **Covers:** D-MST-15, D-MST-16 (#1227)
- **Fixture:** `customer-master`
- **Also needs:** a customer `<SUFFIX>-OB3` created by the Firm admin with **Opening balance** `1500`, and a receipt of `600` applied to its *Opening balance* row (as TC-CUST-008 steps 1 and 3). A second customer `<SUFFIX>-OB4` with **Opening balance** `1500` and nothing received.
- **Steps**
  1. As the fixture's **Firm admin**: Masters > Customers → `<SUFFIX>-OB3` → Edit → **Opening balance** `400` → Save. Try `0`, then `2000`.
  2. Sell > Receipts → select the receipt of 600 → **Reverse** with a reason. Edit the customer again: **Opening balance** `400` → Save. Read Opening bills, Record Receipt and Journal Entries.
  3. Edit once more: **Opening balance** `0` → Save. Then **Delete** the customer.
  4. For `<SUFFIX>-OB4`: sell it 1 of the fixture's product `<SUFFIX>-P` and take the sale to an **approved** invoice. Edit the customer: **Opening balance** `400` → Save.
  5. **Cancel** that invoice with a reason. Edit the customer: **Opening balance** `400` → Save.
- **Expect**
  - Step 1: each is refused and the figure stays 1,500: "Opening balance cannot be changed while other entries stand on <code>'s account: receipt RC-… of 600.00. Reverse or cancel them first. Where the customer has really traded, leave the opening balance and correct what is owed with a credit note or an adjustment."
  - Step 2: with the receipt reversed the change saves. Opening bills shows the bill of 1,500.00 **Cancelled** ("The customer's opening balance was revised.") and **one** standing bill of **400.00**; Record Receipt lists one row of 400.00. Two journals: `<code>-OB-REV` mirrors the first, and `<code>-OB2` posts Dr 1100 Trade Receivables 400.00 / Cr 3000 Opening Balance Equity 400.00.
  - Step 3: at 0 no bill stands, the lists are empty and one more journal takes the 400.00 back; the customer can then be deleted.
  - Step 4: refused in the same words, naming the invoice: "…: invoice SI-… of …. Reverse or cancel them first. …"
  - Step 5: once the invoice is cancelled it no longer holds the figure, and the change to 400 saves as in step 2.
- **Leaves:** a deleted customer; a customer with an opening balance of 400.00; a reversed receipt and a cancelled invoice.

### TC-CUST-010 — Recording, cancelling and importing opening bills needs the settings permission

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-MST-14
- **Fixture:** `customer-master`
- **Also needs:** a **Sales Manager** and a **Firm Manager** user in the firm; a customer `<SUFFIX>-OB5` with one opening bill of `5000` the Firm admin entered (Masters > Customers → the customer → Opening bills → **Add opening bill**), and a customer `<SUFFIX>-OB6` with none.
- **Steps**
  1. As the **Sales Manager**: Masters > Customers → `<SUFFIX>-OB5` → **Opening bills**. Look for **Add opening bill** and for **Cancel** on the row; look for **Import opening bills** on the Customers toolbar.
  2. **(HTTP)** As the Sales Manager: `POST /api/v1/customers/{id}/opening-bills` for `<SUFFIX>-OB6` with 900; `POST /api/v1/customers/opening-bills/{bill_id}/cancel` on the bill of 5,000; `POST /api/v1/customers/opening-bills/import`; `POST /api/v1/customers/opening-bills/import-file` with `apply=false`, then `apply=true`.
  3. As the **Firm Manager**: on `<SUFFIX>-OB6` → Opening bills → **Add opening bill**: reference `OLD-7`, amount `900`, **dated today** → Save. Add another dated **tomorrow**. Then **Cancel** the bill of 900 with a reason. As the **Firm admin**: Customers toolbar → **Import opening bills** with a file of one bill: Check, then Apply.
- **Expect**
  - Step 1: the list of opening bills opens and reads the 5,000.00; **Add opening bill**, **Cancel** and **Import opening bills** are not offered.
  - Step 2: each is refused with **403**: "Recording a customer's opening bill needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)."; "Cancelling a customer's opening bill needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)."; and for the import, the file check and the file apply, "Importing customers' opening bills needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)." After each the customer owes what it owed (0.00 and 5,000.00) and no journal is written. A Customer Support user is refused the two import routes earlier, with "You do not have permission to perform this action.", because the job cannot import customers at all.
  - Step 3: the bill dated today saves and posts (Dr 1100 Trade Receivables 900.00); the one dated tomorrow is refused: "An opening bill is one raised before the books here start, so its date cannot be after <today>.", where today is the firm's own day. The cancel reverses the journal. The file check reports one bill to create and writes nothing; Apply posts it. The same date rule holds for a supplier's opening bill.
- **Leaves:** a cancelled opening bill, and one imported.

---


## Vendors, products, branches and warehouses

The same rule as customers: an edit changes what it names. Vendors had six
child collections emptied by any edit that did not send them; a branch rename
cleared its street lines, city, default flag and GST registration, and a
warehouse rename its capability flags.

### TC-MAST-001 — A vendor edit keeps all six child collections

- **Covers:** plan 5.1
- **Fixture:** `vendor-master` — `<SUFFIX>-V`, Supply Check: one contact, address, bank account, tax record, attachment and note.
- **Steps:** as the fixture's **Firm admin**, Masters > Vendors → Edit `<SUFFIX>-V` → change only the phone → Save → reopen.
- **Expect:** the contact, address, bank account, tax record, attachment and note are **all still there**.
- **Data (HTTP):** `GET /api/v1/vendors/{id}` → `contacts`, `addresses`, `bank_accounts`, `tax_details`, `attachments`, `notes` one each. *(Driven: a PUT with only code, name and phone leaves all six.)* Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §16.7 — `None` leaves a collection alone and `[]` clears it, the header is dumped with `exclude_unset`, and one `vendor.updated` carries the four child counts. The bank account is edited on `VENDOR_UPDATE`: `VENDOR_MANAGE_BANK_DETAILS` is enforced nowhere (D-MST-10).
- **Leaves:** the vendor with a new phone.

### TC-MAST-002 — Vendor categories and types

- **Covers:** plan 5.2, 5.3
- **Fixture:** `vendor-master`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Set up > Party lists > **Vendor Categories**; then **Vendor Types**. Add one to each: `<SUFFIX>-CAT2` / `<SUFFIX>-TYP2`.
  2. Edit `<SUFFIX>-V`: category `<SUFFIX>-CAT`, type `<SUFFIX>-TYP` → Save → reopen.
- **Expect**
  - Step 1: both lists load — the fixture's `<SUFFIX>-CAT` and `<SUFFIX>-TYP` are in them — and both accept a new row. *(These returned nothing until the route order was fixed, and until 2026-09-11 the sidebar opened a "coming soon" placeholder — BACKLOG §26.)*
  - Step 2: both held, and the six child collections are still there.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §16.8 in `test_fixtures` — one `vendor_categories` / `vendor_types` row each and **no audit row at all**; a delete is refused while a live vendor names it; a retired code can never be used again, and a `PUT` on a retired row silently brings it back (D-MST-11).
- **Leaves:** a second category and type; the vendor categorised.

### TC-MAST-003 — A product's slots

- **Covers:** plan 5.4
- **Fixture:** `product-master` — `<SUFFIX>-PM`, Slot Check.
- **Steps:** as the fixture's **Firm admin**, Masters > Products → open `<SUFFIX>-PM`.
- **Expect:** category **Shelf <suffix>**; tax profile group **GST_18_LOCAL**; base, inventory and sales units **PIECE**, purchase unit **BOX** — each read as a name, not an id.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §16.11 in `test_fixtures` — the query there reads all seven slots at once. Open the product and save it from a client that does not send every field and they all clear: the update dumps its whole write model (D-MST-5), which is the one thing not to do while checking this case.
- **Leaves:** unchanged.

### TC-MAST-004 — A rename keeps a branch's address, city, GST registration and default flag

- **Covers:** plan 5.6
- **Fixture:** `branch-master` — in **TEST02**: `<SUFFIX>-BR`, Keep Branch, default, GST registered, 1 Keep Street / Keep Nagar, City <suffix>.
- **Steps:** sign in as the fixture's **TEST02 admin** → Masters > Branches → Edit `<SUFFIX>-BR` → rename to `Kept Branch renamed` → Save → reopen. **(HTTP)** `GET /api/v1/branches/{id}` to check the PAN — the desktop branch form has no PAN field, so the screen cannot show it survived.
- **Expect:** both street lines, the city (and its state), **GST registration** and **Default** are all unchanged on screen; the HTTP call shows the PAN unchanged too.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §16.16 in `test_fixtures_2` — the update is partial and reads `is_default` with the row as its fallback, so the flag survives a rename; `display_name` is the one field recomputed from the name (D-MST-11); audit `branch.updated` with the code and status.
- **Leaves:** the branch renamed.

### TC-MAST-005 — A rename keeps a warehouse's capacity and capability flags

- **Covers:** plan 5.7
- **Fixture:** `branch-master` — `<SUFFIX>-WH`, Keep Warehouse, 1000 SQFT, default; on: temperature controlled, cold storage, receiving area, dispatch area, inspection area, loading dock; off: hazardous, returns area, packing area.
- **Steps:** as the fixture's **TEST02 admin**, Masters > Warehouses → Edit `<SUFFIX>-WH` → rename → Save → reopen.
- **Expect:** capacity 1000 SQFT, Default, and **every flag exactly as listed** — the six on still on, the three off still off. *(Until 2026-09-11 a warehouse with no capacity could not be saved at all — BACKLOG §28.)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §16.17 in `test_fixtures_2` — the update keeps the branch when neither `branch_id` nor `branch_code` is sent, and the query there shows the flags beside the stock the delete guard counts.
- **Leaves:** the warehouse renamed.

### TC-MAST-006 — An import with one bad row imports nothing

- **Covers:** plan 5.8, 5.8b
- **Fixture:** `branch-master` — prints the paths of two files, **Import, clash** (five rows; the fifth reuses `<SUFFIX>-BR`) and **Import, clean** (the first four).
- **Steps**
  1. As the fixture's **TEST02 admin**, Masters > Branches → **Import** → the **clash** file.
  2. Select the refusal text with the mouse; press the copy icon beside it.
  3. Import the **clean** file.
- **Expect**
  - Step 1: **nothing** imported, and the dialog says so. The import stages and commits once.
  - Step 2: the message selects, and the copy icon puts the whole text on the clipboard.
  - Step 3: all four rows go in: `<SUFFIX>-I1` to `-I4`.
- **Data (HTTP):** `POST /api/v1/branches/import` with the clash rows → **409**, "Branch code already exists in this firm.", and a search for `<SUFFIX>-I` then finds none. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §16.19 in `test_fixtures_2` — the batch is staged and committed once, so nothing is written and the corrected file imports. The **product** import is the one that still commits per row (D-MST-9), which is worth contrasting here.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §16.19 — `BRANCH_EXPORT_COLUMNS` and `WAREHOUSE_EXPORT_COLUMNS` are the two lists, written through `csv.writer` and held to the desktop's reader by `tests/unit/test_import_samples_match_the_server.py`; an export writes nothing.
- **Leaves:** one more branch in TEST02; two CSV files where you saved them.

### TC-MAST-008 — A carton barcode finds its product

- **Covers:** plan 5.10
- **Fixture:** `product-master` — `<SUFFIX>-PM` has a **Case** level of 12 pieces with the barcode the fixture printed.
- **Steps:** as the fixture's **Firm admin**, Settings > Set up > Item lists > **Packaging Levels** (or Ctrl+K and the screen's name) → product `<SUFFIX>-PM` → type the barcode into "Scan or type a code" → **Look up**.
- **Expect:** resolves to **Slot Check <suffix>**, level **Case**, **12** base units. No scanner needed: a scanner only types the digits and presses Enter.
- **Data (HTTP):** `GET /api/v1/uom-framework/barcode-lookup?code=<barcode>` → `product_code`, `level_name: Case`, `base_quantity: 12`, `matched_field: barcode`. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §14.10 for the packaging level the code hangs on, and §16.15 for the difference between that and `products.barcode`, the loose single code; the lookup writes nothing.
- **Leaves:** unchanged.

### TC-MAST-009 — One company, two customer accounts

*Added 2026-10-02 (decision A7).*

- **Preconditions:** a customer `QA-HO` with GSTIN `29AAACP1234C1Z5`.
- **Steps:** Masters > Customers → **New**: code `QA-KA2`, GSTIN `29AAACP1234C1Z5` → Save; on the question, **Cancel**; then Save again → **Save anyway**. New again: code `QA-TN`, GSTIN `33AAACP1234C1Z9` → Save → Save anyway. Then New with code `QA-HO` again.
- **Expect:** the first save asks "Same GSTIN or PAN on another customer", naming **QA-HO** for both the GSTIN and the PAN; Cancel keeps everything typed and saves nothing; Save anyway saves. `QA-TN` is asked about the PAN only, and its PAN box holds `AAACP1234C` (filled from the GSTIN, no longer left blank). A second `QA-HO` is refused: "Customer code QA-HO already exists in this firm."

### TC-MAST-010 — Mapping another software's export on import

*Added 2026-10-02 (decision B3).*

- **Preconditions:** a CSV with the headings `Account No`, `Ledger Name`, `GSTIN/UIN`, `Remarks` and two customer rows (as a Tally ledger export might be).
- **Steps:** Masters > Customers → "..." → **Import** → choose the file. Look at the mapping table. Leave `Account No` as *Not imported* and press **Check**. Then map `Account No` → **Code**, `Remarks` → *Not imported* → **Save mapping as...** "Tally ledgers" → **Check** → **Import**. Close, open Import again with the same file, choose *Saved mappings* → "Tally ledgers".
- **Expect:** the table shows each heading with sample values; `Ledger Name` is already mapped to **Name** and `GSTIN/UIN` to **GSTIN**; `Account No` starts *Not imported*. With Code unmapped, Check is held back with a warning that the required **Code** column is not mapped. Mapped, the check is clean and the import creates both customers. The saved mapping fills the table the same way on the second open.
---

### TC-MAST-011 — Principals and brands, and a price revision with an effective date

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog MST-1 (A118), MST-2 (A119)
- **Fixture:** `product-master`
- **Steps:** as the fixture's **Firm admin**: Settings > Set up > Item lists > **Principals** → New *Acme Foods*; **Brands** → New *Acme Gold* under it. Masters > Products → `<SUFFIX>-PM` → pick the brand → Save. Sell > All Sell screens > Insight > **Sales Analysis** → group by Brand, then by Principal; filter by one. Back on the product open **Price history** → add a revision with a price **dated next week** and another dated yesterday; import revisions from a file (one bad row). Quote the product today and with next week's date.
- **Expect:** principals and brands are masters with their own screens; the product carries a brand (text brands that existed are carried over); sales analysis offers Brand and Principal as dimensions and filters. A price revision is the price **in force on the document's date**: today's quote takes yesterday's revision, a quote dated next week takes the later one; the unit-price resolver and a blank price on a purchase order read it. The import checks every row and writes nothing if one is bad.
- **Leaves:** a principal, a brand, revisions.

### TC-MAST-012 — A duplicate warning, and merging two customers

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog MST-3, A136
- **Fixture:** `customer-master`
- **Also needs:** a second customer *Master Check Stores* (same name once trade words are set aside) with the same GSTIN or the same last ten digits of phone, carrying an approved invoice and a receipt; the same for two vendors; a user holding CUSTOMER_DELETE and VENDOR_DELETE.
- **Steps:** as the fixture's **Firm admin**: Masters > **Customers** → New, type the name *M/s Master Check Traders* and the same phone → before Save read the warning. Open the list, select the **duplicate** → **Merge into...** → pick `QA-CM` (the survivor) → confirm. Open the survivor's statement and balances. Repeat for vendors. Then try to merge a duplicate that has an invoice dated in a **closed financial year**.
- **Expect:** the warning (not a block) names customers sharing a GSTIN, the last ten digits of a phone, or the same name once punctuation and words like stores, traders, pvt, ltd and M/s are set aside. The merge re-points every document and ledger row that named the duplicate in **one transaction**; where a unique key would collide the survivor's row is kept (per-period ledger amounts are added); stored balances are summed; the duplicate is soft-deleted and records which customer it was merged into. A duplicate with an invoice or settlement in a locked financial year is refused. Without CUSTOMER_DELETE (VENDOR_DELETE) the merge is refused.
- **Leaves:** a merged customer, a merged vendor.

### TC-MAST-013 — A customer's bank accounts and files

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog MST-4, A68
- **Fixture:** `customer-master`
- **Also needs:** a sales manager and an accountant; a PDF.
- **Steps:** as the fixture's **Firm admin**: Masters > Customers → `QA-CM` → **Bank accounts** → add an account (name, number `1234567890123456`, IFSC) → Save. Open **Files** → add the PDF; delete it. Sign in as the **Sales manager** and open the same tabs. Look at the customer's audit trail.
- **Expect:** the list of accounts is replaced as a whole on save. The administrator sees the number whole; the sales manager and accountant, who do not hold CUSTOMER_MANAGE_BANK_DETAILS, see only the last four digits; the audit trail shows it masked. Files are references (name, type, path, caption); a delete is soft and audited.
- **Leaves:** a bank account, a file reference.

### TC-MAST-014 — A customer who is also a supplier

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog ACC-11, A86
- **Fixture:** `customer-master`
- **Also needs:** a vendor with the **same PAN** as the customer, and another vendor with a different PAN; an approved sales invoice to the customer and a supplier bill from the vendor.
- **Steps:** as the fixture's **Firm admin**: Masters > Customers → `QA-CM` → **Also a supplier** → pick the same-PAN vendor → Save; try the different-PAN vendor and a vendor already linked to another customer. Open **Combined statement**. On the vendor open **Also a customer**. Accounts > All Accounts screens > Books > **Party Adjustments** → set-off.
- **Expect:** a link is accepted only for the firm's own live, unclaimed vendor with the same PAN; the others are refused by name. The combined statement merges the customer and supplier statements in date order with a running **net**; it needs CUSTOMER_VIEW plus VENDOR_VIEW. The supplier editor shows the link back. The set-off dialog preselects the linked party.
- **Leaves:** a party link.

### TC-MAST-015 — Codes issued from a series

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog MST-5, A67
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**: Masters > Customers → New and look at the Code box; leave it blank and save. Do the same for a vendor and a product. Then create a customer typing the code `CUS-00009` and another with a blank code.
- **Expect:** the editor says *Blank: issued on save*. The saved codes come from the series — **CUS**, **SUP**, **PRD** — five digits, with no financial year in them and no yearly reset. A typed code stands and the counter steps over it, so the next blank one does not collide with it.
- **Leaves:** a customer, a vendor, a product.

### TC-MAST-016 — Customer and supplier PAN reports

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog PLT-11, A53
- **Fixture:** `customer-master`
- **Also needs:** one customer with no PAN and one with a malformed PAN (import it through the customer import); a vendor with the same two faults.
- **Steps:** as the fixture's **Firm admin**: Reports > Financial → **Customer PAN check**; then **Supplier PAN check**. As a role without CUSTOMER_VIEW open the first.
- **Expect:** each report lists the live parties whose PAN is missing or fails the format, with six columns; a party with a good PAN is not listed. The customer report needs CUSTOMER_VIEW and the supplier report VENDOR_VIEW.
- **Leaves:** unchanged.

### TC-MAST-017 — A goods type, a category that carries it, and a product that takes it

*Added 2026-10-08 from the code (backlog 89, step 1); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`). What the type fills on the product is TC-MAST-020.*

- **Covers:** backlog 89 test group 1 (goods type)
- **Fixture:** `product-master`
- **Steps:** as the fixture's **Firm admin**: Settings > Firm > **Goods Types**. Read the list. On *Medicine* choose **Use in this firm**; then **Set defaults** → HSN `3004` and one of the firm's tax groups → Save. Add a type of the firm's own: code `<SUFFIX>-SEED`, name *Seeds*, Batches and Expiry date on → Save. Try to add another with code `MEDICINE`. Settings > Set up > Item lists > **Product Categories** → New *Tablets* → Goods type **Medicine** → Save; New *Sundries* leaving the type at *General (no tracking)*; New *Strips* under *Tablets* with no type of its own. Masters > Products → New in *Tablets*; another in *Tablets* > *Strips*; another in *Sundries*; another with no category. Read each product back over the API (`GET /api/v1/products/{id}`).
- **Expect:** the list shows five shared types (Medicine, Food, Cosmetics and personal care, Paint, Electronics) marked *Shared*, none in use on a firm whose profile starts with none, and what each tracks. A shared row offers *Use in this firm* and *Set defaults* and neither Edit nor Delete; over the API a change to one is refused *is a shared goods type and cannot be changed here*. The firm's own type is saved, is in use at once and is listed *Own*; the code `MEDICINE` is refused *already exists*. The category picker offers only types the firm uses, plus General. The products in *Tablets* and in *Strips* carry Medicine's `goods_type_id`; the ones in *Sundries* and with no category carry null. A default tax group the firm does not have is refused.
- **Leaves:** a goods type in use, a goods type of the firm's own, three categories, four products.

### TC-MAST-018 — A category changes type, a product changes category, and a type in use cannot go

*Added 2026-10-08 from the code (backlog 89, step 1); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89 test group 4 (a category changes type)
- **Fixture:** `product-master`
- **Also needs:** Medicine, Food and Paint in use; a category *Syrups* carrying Medicine with one product in it; a category *Enamels* carrying Paint.
- **Steps:** as the fixture's **Firm admin**: Product Categories → *Syrups* → rename it only → Save, and read its type. Change its goods type to **Food** → Save. Read the product that was already in it; create a second product in it. Move the first product to *Enamels*; then clear its category. Goods Types → on *Food* choose **Stop using**. Give *Syrups* the type *General*, then **Stop using** Food again. Add a type of the firm's own, file a category and a product under it, then delete the type; clear the category's type and delete again.
- **Expect:** a rename leaves the category's type alone. After the change to Food the product already filed keeps Medicine and the new one takes Food. Moving the first product to *Enamels* gives it Paint; clearing its category makes it General (null). *Stop using* is refused while a category carries the type -- *is still the goods type of category Syrups* -- and accepted once none does; products that hold the type keep it. Deleting the firm's own type is refused while a category carries it and, after that is cleared, while the product still does (*is still the goods type of product ...; deactivate it instead*).
- **Leaves:** categories and products with changed types; a goods type no longer in use.

### TC-MAST-019 — Who keeps goods types, and what a new firm starts with

*Added 2026-10-08 from the code (backlog 89, step 1); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89 test groups 7 (what a new firm starts with) and 8 (roles)
- **Fixture:** `firm-admin`
- **Also needs:** on the same firm a **Firm manager** and a **Sales manager**; a second, new firm given the profile *Pharma Distribution* as its **first** profile, and a third given *General Agency Distribution*.
- **Steps:** as the **Firm manager**: open Goods Types and Product Categories; over the API `POST /api/v1/products/goods-types` and `PUT /api/v1/products/goods-types/{id}/use`. As the **Sales manager**: `GET /api/v1/products/goods-types`. As the **Firm admin**: the same two writes. As the platform administrator: read the goods types of the two new firms; on the pharmacy firm **Stop using** Medicine, change its profile to another and back, and read again.
- **Expect:** adding, changing, deleting and using a goods type need `CUSTOM_FIELD_MANAGE`: the firm administrator holds it and the writes succeed; the firm manager and the sales manager are refused 403 on the writes and can read the list (`PRODUCT_VIEW`). The pharmacy firm starts with Medicine in use and the agency firm with none. After Medicine is dropped and the profile is changed and changed back, Medicine is still not in use: a profile hands out its goods types once.
- **Leaves:** two firms with their profiles.

### TC-MAST-020 — A new product starts with its goods type's switches, HSN code and tax group

*Added 2026-10-08 from the code (backlog 89, step 2); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`): passes, with the receipt refused at completion.*

- **Covers:** backlog 89 test groups 1 (what a new product starts with), 3 (override and its limit) and 7 (what the profile no longer refuses)
- **Fixture:** `product-master`
- **Also needs:** Medicine in use with defaults HSN `3004` and one of the firm's tax groups; Electronics in use with no defaults; categories *Tablets* (Medicine), *Phones* (Electronics) and *Sundries* (General); a warehouse to receive into.
- **Steps:** as the fixture's **Firm admin**, over the API: `POST /api/v1/products` in *Tablets* naming no switch, no HSN and no tax group (P1); in *Tablets* with `"track_batch": false` (P2); in *Tablets* with `"hsn_sac": "3003"` and another of the firm's tax groups (P3); in *Phones* naming no switch (P4); in *Sundries* naming no switch (P5); in *Sundries* with a `barcode`, a `qr_code`, `"track_warranty": true` and `"shelf_life_days": 365` (P6). Read each back. `GET /api/v1/products/metadata?category_id=<Tablets>`. `PUT` P5 moving it to *Tablets* and read it. `POST /api/v1/products/{P1}/duplicate`. Receive P1 on a goods receipt with no batch number and **complete** it, then with one; then `PUT` P1 with `"track_batch": false`.
- **Expect:** P1 has `track_batch`, `track_expiry`, `track_manufacturing_date`, `require_batch_on_receipt` and `require_batch_on_issue` true, serial and warranty false, `hsn_sac` `3004` and the default tax group. P2 has `track_batch` false, **both `require_batch_*` false**, and `track_expiry` still true. P3 keeps `3003` and its own tax group. P4 has `track_serial`, `track_warranty` and both `require_serial_*` true and no batch switch. P5 has every tracking switch false and no HSN. P6 is saved on any profile -- none of the four fields is refused with *does not enable*. The metadata names Medicine in `goods_type_id` and lists each type's nine `switches`. Moved to *Tablets*, P5 carries Medicine's `goods_type_id` and **its switches are unchanged**. The copy of P1 carries P1's switches. The receipt of P1 with no batch is saved as a draft and refused when it is **completed** (*must be received with a batch number*), and one with a batch completes; switching P1's batch tracking off is then refused because it holds stock.
- **Leaves:** six products and a copy, one with stock in a batch.

### TC-MAST-021 — The product form shows its goods type's properties and no others

*Added 2026-10-08 from the code (backlog 89, step 2); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89 test group 5 (the product form)
- **Fixture:** `product-master`
- **Also needs:** the goods types, defaults and categories of TC-MAST-020; a **Sales manager** on the same firm.
- **Steps:** as the **Firm admin**: Masters > Products > New. Read the form before choosing a category. Choose *Tablets*; read the goods type line, the tracking section, HSN and tax group. Switch **Show all tracking options** on, then off. Switch *Track expiry* off and on; switch *Track batch* off and on. Change the category to *Phones*, then to *Sundries*. Type HSN `9999`, choose *Tablets* again. Type a barcode. Save. Open the saved product; open **Duplicate** on it. As the **Sales manager**: open the same product.
- **Expect:** with no category the line reads *Goods type: General*, the tracking section reads *No tracking for this goods type.* and offers only *Show all tracking options*. On *Tablets*: *Goods type: Medicine* (not a control), *Track batch*, *Track expiry* and *Track manufacturing date* on, *Require batch on receipt* and *on issue* on, no serial or warranty switch, HSN `3004` and the default tax group filled. *Show all* adds lot, serial and warranty and hides them again while they are off. *Track expiry* off hides shelf life and the three expiry rule boxes; *Track batch* off hides the issue rule and both *Require batch* switches, and they come back **off**. *Phones* shows serial and warranty and clears the HSN the type had filled; *Sundries* shows the hint. The typed `9999` survives the change back to *Tablets*. The barcode box accepts typing on any profile. The saved product reopens with the switches it was saved with and its stored goods type; the duplicate opens with the same switches. The sales manager sees the form read-only, as before. Opening a new product makes no server call of its own and each category picked makes one (`/products/metadata`); nothing calls `/products/goods-types`.
- **Leaves:** one product.

### TC-MAST-022 — A unit set fills a new product's units and its own conversion rule

*Added 2026-10-08 from the code (backlog 89, step 3); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89 test group 11 (unit sets)
- **Fixture:** `product-master`
- **Also needs:** the goods types and categories of TC-MAST-020 (*Tablets* is Medicine, *Emulsions* is Paint, *Sundries* has no type); a **Sales manager** and a second firm in the same store.
- **Steps:** as the **Firm admin**: Set up > Unit Sets; read the list. Try to edit *Strip, box of 10*. Add *Jar, case of 6* (stock and sales unit Jar, purchase unit Case, factor 6, goods type Food). Add a second set with the same name; add one with a factor and the purchase unit equal to the stock unit. Masters > Products > New: choose *Tablets*, open the **Unit set** list; tick **Show all unit sets**; choose *Strip, box of 10*; save as `US-1`. New: *Tablets*, *Strip, box of 15*, save as `US-2`. New: *Tablets*, *Strip, box of 10*, then change the purchase unit to Carton and the conversion to 120, save as `US-3`. New: *Emulsions*; read the list; through *Show all* choose *Strip, box of 10*; save as `US-4`. New: *Sundries*, no unit set, save as `US-5`. New: no unit set, base unit Piece, purchase unit Box, conversion 12, save as `US-6`. Buy 2 Box of `US-1` on an order dated last year. Save a product `US-7` from *Jar, case of 6*, edit the set to factor 12, save `US-8` from it, delete the set, open `US-7`. Open `US-1` for editing. As the **Sales manager**: open Unit Sets and try to add one. As the second firm's admin: read the Unit Sets list.
- **Expect:** the list shows the eight shared sets marked Shared, with their goods types (*Bottle, carton of 24* under Medicine, Food and Cosmetics; *Piece, loose* as All goods). A shared set cannot be edited or deleted and says so. The firm's own set saves; the repeated name is refused by name; the factor between one and the same unit is refused. On *Tablets* the list offers Medicine's sets and the two tied to no type, and *Show all* adds the rest. Choosing a set fills the unit boxes, Allow decimal and the conversion box, all still editable. `US-1` has Strip/Box/Strip and its own rule 1 Box = 10 Strip; `US-2` 15; `US-3` Carton and 120 with the base unit still Strip. `US-4` saves with no refusal and no warning. `US-5` has no units and no rule; nothing was pre-filled. `US-6` has its own rule 1 Box = 12 Piece. The back-dated order line converts to 20 Strip. `US-7` keeps Case and 6 after the edit and after the delete; `US-8` took 12. Editing `US-1` shows *Units from: Strip, box of 10*, no unit set list and no conversion box. The sales manager reads the list and is refused the add. The second firm sees the shared sets and not *Jar, case of 6*. Opening the product form makes no call to `/uom-framework/unit-sets` and none for a profile's default units.
- **Leaves:** eight products, one deleted unit set.

### TC-MAST-023 — A batch, a serial and their dates are allowed by the product's switches, not the firm's profile

*Added 2026-10-08 from the code (backlog 89, step 4); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89 test group on batch and serial checks
- **Fixture:** `product-master`
- **Also needs:** a **Sales manager** (or any user without `BATCH_CREATE`) on the same firm. The firm's profile does not matter and may have none of the expiry, batch or serial features.
- **Steps:** as the **Firm admin**: create three products. `TR-MED`: batch, expiry and manufacturing date tracking on. `TR-PAINT`: batch tracking on, expiry off. `TR-PHONE`: serial and warranty tracking on, batch off. Then, through Inventory > Batches and Serial Numbers: (a) add a batch with an expiry date for `TR-MED`; (b) add a batch with an expiry date for `TR-PAINT`, then the same batch without the expiry; (c) add a batch for `TR-PHONE`; (d) add a serial with warranty dates for `TR-PHONE`, then a serial for `TR-PAINT`; (e) set the `TR-PAINT` batch from (b) on hold; (f) Masters > Customers: save a customer with a minimum shelf life of 90 days. As the **Sales manager**: (g) repeat (a) with a new batch number.
- **Expect:** (a) accepted. (b) the first is refused with 422 naming `TR-PAINT` and expiry ("does not track expiry dates, so expiry_date cannot be set. Switch it on for the product first."); the second is accepted. (c) refused with 422: `TR-PHONE` is not tracked by batch. (d) the phone's serial is accepted; the paint's is refused with 422, not tracked by serial. (e) accepted, although the product's switch could now be off: an existing batch can always be held. (f) accepted on a firm whose profile has no expiry feature. (g) refused with 403 for the missing permission, and no batch is written.
- **Leaves:** three products, two batches, one serial, one customer.

### TC-MAST-024 — An extra field is shown and required by goods type, customer group and supplier type

*Added 2026-10-08 from the code (backlog 89, step 5); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89 test group 6 (extra fields) and group 8 (who may keep the rules)
- **Fixture:** `product-master`
- **Also needs:** goods types *Medicine* and *Paint* in use, category *Tablets* (Medicine), *Emulsions* (Paint) and *Sundries* (no type); customer groups *Contractors* and *Retailers*; supplier types *Importer* and *Local*; a **Firm manager** on the same firm. The firm's profile does not matter.
- **Steps:** as the **Firm admin**, under Set up > Custom Fields: add the firm's own fields `SHADE_CODE` (product), `CONTRACTOR_REG_NO` (customer) and `IMPORT_EXPORT_CODE` (supplier). Add three rules: `SHADE_CODE` for goods type *Paint*, not compulsory; `CONTRACTOR_REG_NO` for customer group *Contractors*, compulsory; `IMPORT_EXPORT_CODE` for supplier type *Importer*, compulsory. Then: (a) open a new product and pick *Emulsions*, then *Tablets*, then *Sundries*; (b) save a customer in *Contractors* with the registration number empty, then filled; (c) save a customer in *Retailers*, and one in no group; (d) send, over the API, a *Retailers* customer carrying a value for `CONTRACTOR_REG_NO`; (e) move the customer of (b) to *Retailers* and save; (f) save a supplier of type *Importer* without the code, then with it, and one of type *Local* without it; (g) add the *Contractors* rule a second time; (h) add a rule for `SHADE_CODE` naming customer group *Contractors*. As the **Firm manager**: (i) add any rule.
- **Expect:** (a) *Shade Code* is offered for *Emulsions*, optional, and is not offered for *Tablets* or *Sundries*. (b) the first save is refused, "Required attributes are missing"; the second is accepted and the value reads back. (c) both accepted; neither form shows the field. (d) refused with 422, "do not apply". (e) accepted; the registration number the customer already held is still stored and still shown. (f) refused, then accepted; the *Local* supplier is accepted without it. (g) refused with 409, "already exists". (h) refused with 422: a product field cannot name a customer group. (i) refused with 403, and no rule is written.
- **Leaves:** three fields, three rules, one product at most, three customers, two suppliers.

### TC-MAST-025 — A firm switches a shared extra field off, and its values are kept

*Added 2026-10-08 from the code (backlog 89, step 5); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89 test group 6 (a firm switching a catalogue field off) and group 7 (what the profile no longer does)
- **Fixture:** `product-master`
- **Also needs:** one **shared** customer field (added by the platform administrator under Platform > Dynamic Attributes, for example `TRADE_LICENCE_NO`); a second firm in the **same store** -- two firms of the shared store, which the `shared-pair` fixture gives; the `product-master` firm and a second fixture firm are stores of their own, where a shared field of one does not exist in the other, so step (e) cannot be driven on them; a **Firm manager** on the first firm.
- **Steps:** as the **Firm admin** of the first firm: (a) save a customer with a value in the shared field; (b) under Set up > Custom Fields, switch the shared field off for this firm; (c) open that customer, and open a new customer; (d) send, over the API, a new customer carrying a value for the field; (e) open a new customer in the **second** firm; (f) switch the field on again and open the first customer; (g) try the switch on one of the firm's **own** fields. As the **Firm manager**: (h) switch the shared field off.
- **Expect:** (b) accepted; the list shows the field as off for this firm. (c) the existing customer still shows the value it holds; the new customer is not offered the field. (d) refused with 422, "do not apply". (e) the second firm is still offered the field. (f) the value saved in (a) is there, unchanged. (g) refused with 404: a firm's own field is retired by making it inactive. (h) refused with 403. The audit trail of the first firm holds two `firm_custom_field.use_changed` rows, off then on.
- **Leaves:** one shared field, two customers.

### TC-MAST-026 — The Inventory menu shows only the tracking the firm's goods need

*Added 2026-10-08 from the code (backlog 89, step 6); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89 point 6 (menus follow the goods); `docs/BUSINESS_PROFILE_FRAMEWORK.md`, *Menus follow the goods*
- **Fixture:** `product-master`
- **Also needs:** a firm of its own with **no** goods type in use, no category carrying a type, and no product with a tracking switch on; the shared goods types *Paint* (batch only), *Electronics* (serial and warranty) and *Medicine*; a second user on the firm whose role lacks `BATCH_VIEW`; a second firm in the same store holding one product with *Track batch* on and no goods type (the old kind, filed before goods types existed).
- **Steps:** as the **Firm admin** of the first firm: (a) sign in and open the Inventory menu (Stock, and All Stock screens > Tracking). (b) Set up > Goods Types: **Use in this firm** on *Paint*; file a category *Enamels* under it. Without signing out, read the menu; then sign out and in again and read it. (c) Use *Electronics* the same way, sign out and in. (d) Stop using both types after clearing the categories' types; sign out and in. (e) As the user without `BATCH_VIEW`: with Paint in use again, sign in and read the menu. (f) As the **Firm admin** of the second firm: sign in and read the menu. (g) Switch from the first firm to the second and back through the firm switcher. (h) Read `GET /api/v1/business-framework/active-modules` with no `X-Firm-ID` header, then with each firm.
- **Expect:** (a) Batches, Lots, Serial Numbers and Expiry Monitor are all absent; the rest of Stock is there. (b) before signing in again the menu is unchanged (the answer is read at sign-in and at a firm switch); after it Batches and Lots show and Serial Numbers and Expiry Monitor do not. (c) Serial Numbers is added; Expiry Monitor is still absent, Paint and Electronics track no expiry. (d) all four are gone again. (e) the user without `BATCH_VIEW` does not see Batches or Lots although the firm's goods need them. (f) Batches and Lots show, because a live product has *Track batch* on although the firm uses no goods type; Serial Numbers does not. (g) the menu changes with the firm each time, with no further sign-in. (h) the INVENTORY row carries `goods_tracking` as a list (for the first firm `BATCH` while Paint is in use, `BATCH` and `SERIAL` once Electronics is too); every other row carries null; with no `X-Firm-ID` the call answers 200 with an empty list, because the modules are kept in each firm's store and there is no firm to answer for (it answered 503 before D-CFG-26). The client does not ask while no firm is selected, and shows every screen. Opening the menu makes no extra request beyond the `active-modules` call the shell already makes at start.
- **Leaves:** two goods types used then dropped, one category.

### TC-MAST-027 — A product import with no switch columns takes its category's goods type

*Added 2026-10-08 from the code (backlog 89, step 6); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89 import point (a); `docs/FUNCTIONAL_GUIDE.md`, products
- **Fixture:** `product-master`
- **Also needs:** categories *Tablets* (goods type Medicine), *Emulsions* (Paint), *Sundries* (no type) and *Strips* under *Tablets* with no type of its own; a user on the same firm whose role lacks `PRODUCT_IMPORT`.
- **Steps:** as the **Firm admin**: Masters > Products > Import > download the template and read the columns. Build a file from the template that **omits** the TrackBatch, TrackExpiry and TrackSerial columns, with four new products: `IM-MED` in *Tablets*, `IM-SUB` in *Tablets* with sub category *Strips*, `IM-PAINT` in *Emulsions*, `IM-GEN` in *Sundries*. Check, then Import; open the four products. Build a second file with the three columns present: `IM-NO` in *Tablets* with TrackExpiry **No** and the other two blank; `IM-YES` in *Sundries* with TrackBatch **Yes**; `IM-BAD` in *Sundries* with TrackBatch `maybe`. Check; read the problems; remove the bad row; Import; open the products. As the user without `PRODUCT_IMPORT`: open the Products screen and call the import check over the API.
- **Expect:** the template lists the three tracking columns as optional ("Blank takes the goods type of the product's category.") and a UnitSet column. The first check is clean and the import writes four products: `IM-MED` and `IM-SUB` track batch, expiry and manufacturing date (the sub category with no type takes its parent's); `IM-PAINT` tracks batch only; `IM-GEN` tracks nothing. In the second file `IM-NO` tracks batch and manufacturing date but not expiry (a cell saying No wins); `IM-YES` tracks batch only (the file's Yes) and nothing else although the category has no type; `IM-BAD` is named in the check by row and column and the file does not import until it is removed. The user without `PRODUCT_IMPORT` has no Import button, and the same call over the API answers 403.
- **Leaves:** seven products.

### TC-MAST-028 — The UnitSet column fills a new product's units and its pack rule

*Added 2026-10-08 from the code (backlog 89, step 6); driven over HTTP the same day and corrected: a Unit beside a UnitSet is passed over with a warning (D-MST-17).*

- **Covers:** backlog 89 import point (b), unit sets in an import
- **Fixture:** `product-master`
- **Also needs:** the shared unit sets (*Strip, box of 10* is tied to Medicine, *Piece, loose* is tied to no type); categories *Tablets* (Medicine) and *Emulsions* (Paint); one existing product `UX-OLD` in *Tablets* with its own units.
- **Steps:** as the **Firm admin**: download the template and read the Lists sheet. Build a file with a UnitSet column: (1) `UX-1` in *Tablets*, UnitSet `Strip, box of 10`, no Unit; (2) `UX-2` in *Tablets*, UnitSet `Strip, box of 10`, Unit `Box`; (3) `UX-3` in *Tablets*, UnitSet `Blister, box of 99`; (4) `UX-4` in *Emulsions*, UnitSet `Strip, box of 10`; (5) `UX-5` in *Emulsions*, UnitSet `Piece, loose`; (6) `UX-OLD` again, UnitSet `Strip, box of 10`. Check. Remove row 3 and check again, then Import. Open each product. Repeat the file with the column headed `Pack size`.
- **Expect:** the Lists sheet has a Unit set column holding every set offered to the firm. The first check names row 3 as a problem on UnitSet ("'Blister, box of 99' is not an active unit set.") and imports nothing. After row 3 is removed the check is clean in problems but lists three warnings under "3 to look at. These do not stop the import.": row 2 on Unit ("is passed over: the unit set 'Strip, box of 10' fills this product's units and its pack conversion."), row 4 ("is marked for other goods types than this product's. It is imported as written.") and row 6 ("is passed over: a unit set fills a new product only, and this product keeps its units."). Import writes `UX-1` with the set's units and its own pack conversion (1 Box = 10 Strip), `UX-2` exactly as `UX-1` -- the set's units and the same conversion, its own Unit passed over (kept, the Unit made the purchase unit the stock unit and the conversion was dropped without a word: D-MST-17) -- `UX-4` with the Strip set as written, `UX-5` with Piece and no conversion. `UX-OLD` keeps its units and gains no conversion. The `Pack size` heading is read as the UnitSet column.
- **Leaves:** four new products, one unchanged.

### TC-MAST-029 — What a business profile no longer does

*Added 2026-10-08 from the code (backlog 89, step 6); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89 "Business profiles stay, smaller"; `docs/BUSINESS_PROFILE_FRAMEWORK.md`
- **Fixture:** `product-master`, plus a platform administrator
- **Also needs:** a firm on the **Generic** business profile (nothing but `ATTACHMENTS`); a **Firm manager** on it; a second firm on the **Pharmacy** profile; the sales hierarchy levels saved for the Generic firm by the **platform administrator** before step (d) -- a route needs them, and the firm administrator is refused that save (403).
- **Steps:** as the platform administrator: Settings > Business profile > Feature Management; read the list. Open the Generic profile and read its features. As the **Firm admin** of the Generic firm: (a) save a product with a barcode and a QR code; (b) on a product with *Track serial* and *Track warranty* on, add a serial number with warranty dates; (c) on a product with *Track expiry* on, add a batch with an expiry date; (d) Masters > Territory: create a route; (e) Masters > Warehouses: add a second warehouse; (f) record a vehicle number on a delivery note; (g) attach a file to a sales order. As the **Firm manager** of the same firm: repeat (c). As the platform administrator: assign the **Pharmacy** profile to the Generic firm and read the goods types of the firm; then assign the Generic profile again; read the goods types of the pharmacy firm.
- **Expect:** the feature list holds five rows -- Attachments, Vehicle Tracking, Drug License, Commission and Batch PTR / PTS -- and none of Batch Tracking, Expiry Tracking, Serial Number, Warranty, Barcode, QR Code, Territory, Multiple Warehouses or Approval Workflow. The Generic profile lists Attachments only. (a) to (e) are accepted with no refusal naming a profile or a feature. (f) is refused with 403 ("This firm's business profile does not enable VEHICLE_TRACKING, so ... cannot be set."): vehicle details are one of the five firm features and Generic does not map it. (g) is accepted. The firm manager's batch is refused for the missing permission when the role lacks `BATCH_CREATE`, and for no reason to do with the profile otherwise. Assigning Pharmacy to the Generic firm hands it **no** goods type and writes no `goods_type.starting_set` row: a firm takes its profile's goods types with its **first** profile only, as TC-MAST-019 says. Assigning Generic back changes nothing, and the pharmacy firm's goods types are unchanged by the round trip.
- **Leaves:** a product, a route, a warehouse, a batch, a serial, a delivery note, an attachment.

### TC-MAST-030 — Copying a product keeps its pack size

*Added 2026-10-08 from the code (backlog 89, step 6); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Covers:** backlog 89, `ProductService.duplicate_product`
- **Fixture:** `product-master`
- **Also needs:** a product `CP-SET` created from the unit set *Strip, box of 10*, then given its own conversion of 12 (1 Box = 12 Strip); a product `CP-HAND` with units typed by hand and no unit set; a user on the same firm whose role lacks `PRODUCT_CREATE`.
- **Steps:** as the **Firm admin**: Duplicate `CP-SET`, save the copy as `CP-SET-2`. Duplicate `CP-HAND`, save as `CP-HAND-2`. Stop offering the set *Strip, box of 10* (deactivate it if it is the firm's own, or use a firm-made copy of it), then duplicate `CP-SET` again as `CP-SET-3`. As the user without `PRODUCT_CREATE`: try to duplicate `CP-SET`.
- **Expect:** `CP-SET-2` shows *Units from: Strip, box of 10* and has its own pack conversion at the **source's** factor, 12, not the set's 10. `CP-HAND-2` has no unit set and the same units as its source, with a conversion only if the source had one. `CP-SET-3` keeps the units and the conversion but not the set's name, because the set is no longer offered. Over all three the source product is unchanged. The user without `PRODUCT_CREATE` is refused (403) and no product is written.
- **Leaves:** three copies.

### TC-MAST-031 — Goods type in the analyses, the stock reports and the product list

*Added 2026-10-08 from the code (backlog 89, step 8); driven over HTTP the same day (`docs/qa/GOODS_TYPES_REPORTS_CHECK_2026-10-08.md`). Not yet clicked on screen.*

- **Covers:** backlog 89 "The schema is designed for the questions that will be asked of it"; `docs/GOODS_TYPES.md`, *Goods type in reports and lists*
- **Fixture:** `product-master`
- **Also needs:** the goods types and categories of TC-MAST-020 (*Tablets* is Medicine, *Sundries* has no type); a product `GR-MED` under *Tablets* and a product `GR-PLAIN` under *Sundries*, each with opening stock; one approved sales invoice and one approved supplier bill holding a line of each product, dated this month.
- **Steps:** as the **Firm admin**: (a) Sales Analysis, rows *Goods type*, this month; then columns *Month*. (b) Filter *Goods type* = Medicine, rows *Product*. (c) Click the Medicine cell of (a) for its invoices; try the General cell. (d) Purchase Analysis, rows *Goods type*. (e) Reports > Stock valuation, Stock ageing, Dead stock (days 1): read the *Goods type* column. (f) Masters > Products > Filters: *Goods type* = Medicine, Apply; then General; then Any. (g) Ask Sales Analysis for *Goods type* on both rows and columns.
- **Expect:** (a) two rows, *General* and *Medicine*, whose totals add up to the grand total; each holds the value of its own product's line and both count the one invoice. (b) only `GR-MED`. (c) the Medicine cell lists the invoice with the value of the Medicine line; the General cell does not open, as no cell of an unfiled value does. (d) *General* and *Medicine* with the two bill lines. (e) `GR-MED` reads Medicine and `GR-PLAIN` reads General on all three; the valuation's total, books and difference rows show no goods type. (f) Medicine lists `GR-MED` and no product without a type; General lists `GR-PLAIN` and no Medicine product; the count under the list matches; Any lists both. A firm that uses no goods type is not offered the filter. (g) refused: "Choose a different dimension for the columns."
- **Leaves:** two products, an invoice, a bill.

### TC-MAST-032 — A pack's barcode finds its product, and the counter bill adds what the pack holds

*Added 2026-10-08 from the code (backlog 89, market gap 3); the server's half driven over HTTP the same day (`docs/qa/checks/goods_types/tc_mast_032.py`). The scan field and the product boxes are covered by widget tests; not yet clicked on screen.*

- **Covers:** backlog 89, market gap 3 "More than one barcode on a product"; `docs/UOM_FRAMEWORK.md`, *Where a pack's code is read*
- **Fixture:** `product-master`
- **Also needs:** a product `PK-SOAP` with its own barcode `PK-OWN` and stock in the counter's warehouse; a product `PK-TEA` with none. Under Masters > Packaging Levels, on `PK-SOAP`: a level *Carton*, unit BOX, 24 to the base unit, barcode `PK-CTN`, EAN `PK-EAN`. A cash customer.
- **Steps:** as the **Firm admin**: (a) Packaging Levels: scan `PK-CTN`, then `PK-OWN`. (b) Sales > new counter bill: scan `PK-OWN`, then `PK-CTN`, then `PK-CTN` again, then `PK-OWN`. (c) On a new counter bill scan `PK-CTN` first. (d) Scan a code nothing carries. (e) New sales order: click the first line's product box, type `PK-CTN`, press Enter; do the same on a quotation, a sales invoice, a purchase order and a supplier bill. (f) Masters > Products: search `PK-CTN`, then `PK-EAN`. (g) Give `PK-TEA` a level *Box* with barcode `PK-BOTH` and `PK-SOAP` a level *Pallet* with UPC `PK-BOTH`; scan `PK-BOTH` on the counter bill, then search it under Products. (h) Delete the *Carton* level; scan `PK-CTN` on the counter bill. As the **Sales manager**: (i) scan `PK-EAN` on a counter bill; try to add a level under Packaging Levels. As another firm's administrator: (j) scan `PK-CTN`.
- **Expect:** (a) *Carton* of `PK-SOAP`, one scan is 24 base units; then the product itself, one base unit. (b) the one line of `PK-SOAP` reads 1, then 25, then 49, then 50; after each carton the line beside the scan field reads *Carton (BOX) of PK-SOAP: 24 ... added.* and after the single piece it is gone; no second line appears, and the scan field keeps the focus throughout. (c) a new line of `PK-SOAP` with quantity 24. (d) *No product has the barcode ...*, the bill unchanged. (e) on each of the five documents the line takes `PK-SOAP`; its quantity is left for the person to type. (f) each search lists `PK-SOAP` alone. (g) the scan is refused in the server's words -- *2 products or packaging levels carry the code PK-BOTH* -- and nothing is added; the product search lists both products. (h) *No product has the barcode "PK-CTN"*. (i) the scan adds 24; the sales manager is refused a new level (403). (j) not found: another firm's pack answers nothing.
- **Leaves:** two products, their levels, draft counter bills.


---

## Configuration — numbering, profiles, tax and units

Most of these screens are cards on the **Settings** page (the gear at the right
of the menu bar), under **Settings**, **Set up** and **Platform**. **Ctrl+K**
opens any screen by name.

### TC-CONF-001 — Numbering series: who may change one, and a counter nobody types

- **Covers:** plan 6.1, 6.2
- **Fixture:** `firm-admin` and `sales-executive`
- **Steps**
  1. Sign in as the `firm-admin` fixture's **Firm admin** → Settings > Firm > **Numbering Series**.
  2. Select **SALES_INVOICE_DEFAULT** → Edit → scroll below the **Active** switch. Change the Name, save, reopen.
  3. Press **New series** and look at the same spot.
  4. Sign in as the `sales-executive` fixture's **Seller** and open the same screen.
- **Expect**
  - Step 1: **New series**, **Edit** and **Retire** offered.
  - Step 2: a locked row with a padlock, `Next number: N`, and the reason ("The counter belongs to the server, which advances it under a lock..."); no box to type in. After the rename the next number is unchanged.
  - Step 3: a **Start numbering at** box instead, helper "Usually 1...".
  - Step 4: the list loads, and **none** of the three buttons is offered.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.6 in `test_fixtures` — the rename updates `document_numbering_rules.name` and `version` and writes `document_numbering_rule.updated` (`before_data` code, name and next number; nothing after); the counter the next invoice uses is `document_number_sequences.next_sequence`, which the rename does not touch. The editor's "Use this series by default" and "Active" switches are stored and read by nothing (D-CFG-6).
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.6 in `test_fixtures` — step 1 writes nothing; step 2 inserts one `document_numbering_rules` row (`auto_reset` and `include_financial_year` true, `next_sequence` as typed) and `document_numbering_rule.created`, and **no** counter row until a document uses it. With two live SALES_INVOICE series, which one the next bill takes is not decided by the default switch (D-CFG-6) — retire this one when the case is done.
- **Leaves:** a second sales invoice series in TEST01 (not the default).

### TC-CONF-003 — Previewing the next number issues nothing

- **Covers:** plan 6.4
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, select **SALES_INVOICE_DEFAULT** → **Preview next**, twice.
- **Expect:** a number matching the pattern — `SI-2026-2027-00000N` — equal to the locked `Next number` and the **same both times**. A preview issues nothing.
- **Data (HTTP):** `GET /api/v1/document-framework/numbering-rules/{id}/preview`, twice → the same string. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §14.6 in `test_fixtures` — the preview writes nothing: `document_number_sequences.next_sequence` for the rule's current scope reads the same before and after, and there is no audit row.
- **Leaves:** unchanged.

### TC-CONF-004 — A roadmap feature cannot be switched on

- **Covers:** plan 6.5
- **Fixture:** `config-firm` — a store of the run's own, so a profile edit here reaches no other firm.
- **Steps**
  1. Sign in as the fixture's **Platform admin**, switch into the fixture's firm → Settings > Platform > Firms > Business Profiles → **Profiles** → edit **WHOLESALE** → in **Enabled features** tick **IMEI** → Save.
  2. Untick IMEI; tick **BARCODE** (if it is not already) → Save.
- **Expect**
  - Step 1: refused in the summary at the top of the form, which scrolls into view: "These features are not implemented yet and cannot be enabled: IMEI." The dialog stays open and **nothing** is written — not the features, and not the profile's other fields (until 2026-09-12 they were — BACKLOG §31.6). The six roadmap features: `IMEI`, `KITCHEN_MANAGEMENT`, `PRESCRIPTION_REQUIRED`, `PROJECT_MANAGEMENT`, `RECIPE_MANAGEMENT`, `SERVICE_CONTRACTS`.
  - Step 2: saves. The **Feature Flags** leaf beside it is the catalogue, not where a profile's features are chosen.
- **Data (HTTP):** `PUT /api/v1/business-framework/profiles/{WHOLESALE id}/features` with the current ids plus IMEI's → **422**, the same sentence. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §14.1 in `fx_<suffix>_r` — step 1 writes nothing; step 2 sets `profile_features.is_enabled` true on BARCODE's row (or inserts it) and writes `business_profile.features.updated` with `firm_id` null and no data, so it is on no Audit Logs screen and does not say which feature moved (D-CFG-13).
- **Leaves:** the fixture store's WHOLESALE profile, with BARCODE on.

### TC-CONF-005 — The tax simulator: CGST and SGST within a state, IGST across

- **Covers:** plan 6.7
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, Settings > Tax > **Rule Simulator**. Transaction type `SALES_INVOICE`, tax profile `GST_18_LOCAL`, invoice value `1000` → Run Simulation. Then transaction type `SALES_INTERSTATE` → Run.
- **Expect:** local — no rule matched, CGST 9% = 90 and SGST 9% = 90, total **180**. Interstate — matched rule **`INTERSTATE_GST_18`**, one component IGST 18% = 180, total **180**, and the trace shows the rule matched. (TEST01's rules come from the GST template, the same nine the demo firms carry.)
- **Data (HTTP):** `POST /api/v1/tax-framework/simulate` with the same values → `total_tax_amount` 180 both times; `matched_rule_id` null, then INTERSTATE_GST_18's id. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §13.4 in `test_fixtures` — each run writes one `tax_rule_execution_logs` row (`execution_mode` SIMULATION, the trace in `evaluation_trace`: all nine rules tried for the local run, four for the interstate one, which stops at the match) and an audit `tax.rule.simulated`. No document ever sends `SALES_INTERSTATE`, so a real bill to another state is charged CGST and SGST (D-CMP-1), and if INTERSTATE_GST_18 has been edited the match may be an old version (D-CMP-3).
- **Leaves:** unchanged.

### TC-CONF-006 — A product's own conversion outranks the firm-wide one

- **Covers:** plan 6.8
- **Fixture:** `config-firm` — `<SUFFIX>-DET` is bought in PACK and stocked in KG, with its own PACK→KG rule at factor **1**.
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm (or its **Firm admin**), Settings > Set up > Item lists > **Conversion Rules** → **Add**: Product *Firm-wide*, From `PACK`, To `KG`, Factor `2` → Save.
  2. Buy > Purchase Orders → New: vendor `<SUFFIX>-V`, product `<SUFFIX>-DET`, quantity **10**, Purchase UOM `PACK — Pack` → Save; open the order.
- **Expect**
  - Step 1: the firm-wide rule appears beside the product's own.
  - Step 2: the line shows **Base Qty 10**, not 20 — the product's factor of 1 outranks the firm-wide 2. (Ranked explicitly rather than by NULL sort, which PostgreSQL and SQLite order oppositely.)
- **Data (HTTP):** the order's line carries `conversion_factor` 1 and `base_quantity` 10. *(Driven with two firm-wide PACK→KG rules at 2 in place: still 10.)* Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §14.11 in `fx_<suffix>_r` — step 1 inserts a `uom_conversion_rules` row with `product_id` null and writes `uom.conversion.created` with no data; the line stores the factor and the rule's `version_number`. Do not edit either rule while a receipt of this order is in draft: completing it re-reads the rule and moves stock at the new factor (D-CFG-1).
- **Leaves:** a firm-wide rule and a draft order in the fixture's store.

### TC-CONF-007 — GST documents: the firm's own rules for dispatch, e-invoicing and input credit

*Added 2026-10-02 from the code; not yet driven. Drive it and correct the expectation before relying on it.*

- **Covers:** backlog 77 rows 1-3 and 78 row 3, A35, A36
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, Settings > Tax > **GST Documents**. Read the banner. Choose **Block** for *Dispatch of a sale before its invoice*, set *E-invoicing applies from* to a date, and set *30-day reporting limit applies from* to a day **before** it → Save. Correct that, set *Claim input credit* to *Only bills matched to GSTR-2B*, set the matching tolerance → Save, close and reopen. Then open it as a user who holds Tax view but not the manage-tax-settings permission.
- **Expect:** a firm that has never saved sees that it is using the default shown, and saving makes it the firm's own. The 30-day date earlier than the e-invoicing date (or with none) is refused with the server's message and the dialog stays open with what was typed. After the second save the values come back on reopening. The read-only user sees the values, a disabled Save and "Changing the GST document settings needs the manage tax settings permission."
- **Leaves:** the firm's GST documents settings.

### TC-CONF-008 — A feature or module made at runtime reaches every store

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog MST-7, A69
- **Fixture:** `platform-admin`
- **Also needs:** at least two provisioned firms in different stores (TEST01 and TEST02).
- **Steps:** as the fixture's **Platform admin**: Settings > Business profile > **Feature Management** → New feature `QA_RUNTIME_FEAT`, then edit its name; **Module Configuration** → New module and edit it. Read the answer after each save. Delete the feature and the module.
- **Expect:** each create, update and delete answers with the list of **stores** it reached and a warning for any it could not; the new feature and module exist in every firm's store, so a profile can use them. Deleting returns the per-store list rather than an empty answer. The pages are the generic resource pages; nothing new is on screen.
- **Leaves:** nothing, if deleted.

### TC-CONF-009 — "Today" is the firm's own day, at any hour

*Added 2026-10-06 after D-CFG-25 (#1219, #1223, #1226). **Server side driven** over HTTP between 02:30 and 02:50 India time on 2026-10-06; results in `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-CFG-25
- **Fixture:** `ready-firm`
- **Also needs:** to be run **between midnight and 05:30 India time**, the hours in which the server's own (UTC) date is still yesterday's; at any other hour every step passes without showing anything. A supplier with a completed purchase return whose **Outcome** is *Refund*, dated today (TC-BUY-009 shows how); an approved, unpaid sales invoice to the fixture's customer; a goods receipt or an opening stock entry of a product dated today.
- **Steps:** as the fixture's **Firm admin**: (1) Buy > Payments → **Supplier refunds** → the supplier → on the return, **Record refund** dated **today** → Save. (2) Masters > Customers → the fixture's customer → Opening bills → **Add opening bill** dated **today** → Save; then one dated tomorrow. (3) Sell > All Sell screens > Money > Collection Sheet → the bill → **Record promise**, *Promised on* **today** → Save promise. (4) Reports > Operational → **Stock valuation**, with no date and then as on today. (5) Record a customer receipt without typing a date, and open it. (6) Settings > Set up > Pricing > **Promotions** → New, an offer whose first day is **today**; raise an order line it applies to.
- **Expect:** (1) the refund is accepted; one dated tomorrow is refused, "A refund cannot be received on a future date." (2) the opening bill dated today is accepted and the one dated tomorrow refused, "An opening bill is one raised before the books here start, so its date cannot be after <today>." (3) the promise is accepted and reads **Due today**. (4) the valuation includes the stock that arrived today and its total equals account 1200 Inventory on the trial balance. (5) a document the server dates is dated today, the firm's day, not yesterday. (6) an offer that starts today is in force today, and one whose last day was yesterday is not; the same holds for a price list, a rate contract and a supplier scheme (this step, #1226, is unit-tested and was not driven on a running server). Nothing asks the tester to date a document on another day or to wait for the morning. The Counter Shifts list and the printed shift report use the same day (#1228).
- **Leaves:** a refund, an opening bill, a promise, a receipt.

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

Purchase orders are Buy > **Purchase Orders**; Goods Receipts and Purchase Invoices
are on the Buy menu and Purchase Returns under Buy > **Returns & notes**;
payments are Buy > **Payments**;
stock is Stock > All Stock screens > Stock > **Inventory** and Stock > **Stock Ledger**. Every
screen reads once when opened: **Refresh** after acting elsewhere.

### TC-BUY-001 — Raising a purchase order, and the approval that cannot be skipped

- **Covers:** plan 7.1, 7.2, 7.3
- **Fixture:** `buy-ready`
- **Steps**
  1. As the fixture's **Firm admin**, Buy > Purchase Orders → **New**: vendor `<SUFFIX>-V`, branch `HO`, warehouse `MAIN`, today; **Add Line**: product `<SUFFIX>-B`, quantity **10**, unit price **100** (the units fill from the product, PIECE) → **Save**. Open it.
  2. Select the draft: look at the toolbar and inside the view.
  3. **Submit**, then **Approve**.
- **Expect**
  - Step 1: status **DRAFT**, number `PO-TEST01-HO-2026-2027-…`; the Line Items table names the product as `<SUFFIX>-B — Bought Item <suffix>` and the unit `PIECE`; the Approval banner reads "Submit this draft to send it for approval."
  - Step 2: **Approve is not offered** on a draft — only Submit. **(HTTP)** `POST /api/v1/purchases/{id}/approve` on a draft → **422**, "Only submitted purchase orders can be approved. Submit the order first."
  - Step 3: toasts "… submitted for approval." and "… approved."; status **APPROVED**, the grid updating without the dialog closing.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §9.1 (the order and its lines, audit `purchase.created`) and §9.2 (history `purchase.submitted` / `purchase.approved`; no journal, no stock). All in `test_fixtures`.
- **Leaves:** an approved order.

### TC-BUY-002 — Editing an approved order withdraws the approval

- **Covers:** plan 7.4
- **Fixture:** `po-approved`
- **Steps:** as the fixture's **Firm admin**, select the fixture's order → **Edit** → dialog **Editing withdraws the approval** → **Edit anyway**. Type a line remark and change the order remarks → **Save**. Then **Submit** and **Approve** again.
- **Expect:** saved as **DRAFT**; the remark survives reopening; the view's **History** shows the approval withdrawn (audit `purchase.approval_withdrawn`). An edit no longer decides the status — the update body cannot write one. After Submit and Approve: APPROVED again.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §9.3. `purchase.approval_withdrawn` is a **`purchase_order_history`** row (which the History tab reads), not an `audit_logs` row — the trail holds `purchase.updated` with status APPROVED → DRAFT. The two history rows share one timestamp.
- **Leaves:** the order, re-approved.

### TC-BUY-003 — Receiving part of an order, then the rest

- **Covers:** plan 7.5, 7.6
- **Fixture:** `po-approved`
- **Steps**
  1. As the fixture's **Firm admin**, Buy > Goods Receipts → **New** → **Purchase Order** picker (approved orders only) → the fixture's order. Set Accepted to **4**, warehouse `MAIN` → **Save Receipt** → select the draft → **Complete**.
  2. Buy > Purchase Orders → the order. Stock > All Stock screens > Stock > Inventory and Stock Ledger, filtered to `<SUFFIX>-B`.
  3. Buy > Goods Receipts → New against the same order → Accepted defaults to **6** → Save, Complete.
- **Expect**
  - Step 1: the line arrives with Accepted 10 and "Ordered 10 · already received 0"; after save, "Goods receipt GRN-… created as a draft. Complete it to post the stock."; after Complete, status **COMPLETED**.
  - Step 2: the order reads **PARTIALLY_RECEIVED**; `<SUFFIX>-B` in MAIN holds **4**; the Stock Ledger shows `GOODS_RECEIPT` +4 referencing the GRN.
  - Step 3: the line says "already received 4"; after Complete the order reads **RECEIVED**, MAIN holds **10**, and a second `GOODS_RECEIPT` entry appears.
  - A line that did not arrive is left off the document, never kept at 0: a line of 0 with nothing free is refused on an order, a receipt, a bill and a return alike ("Line 1 orders a quantity of 0 and nothing free. Type a quantity, or leave the line off the order." on an order, and in the same pattern on the other three).
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §9.4 (the draft writes no stock) and §9.5 (per completion: a movement, a stock ledger row, the inventory row, a journal Dr 1200 / Cr 2300 of 400.00 then 600.00, five audit rows). The order's move to PARTIALLY_RECEIVED / RECEIVED is audit `purchase.received_status_changed` and has no history row.
- **Leaves:** a fully received order.

### TC-BUY-004 — Cancelling a completed receipt undoes its stock and its journal

- **Covers:** plan 7.7
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, Buy > Goods Receipts → select the **receipt of 4** → **Cancel**. Then the order, the Inventory row and the Stock Ledger for `<SUFFIX>-B`; Accounts > Journal Entries.
- **Expect:** status **CANCELLED**; the ledger shows `GOODS_RECEIPT_REVERSAL` **−4** against that GRN; MAIN holds **6**; the order drops back to **PARTIALLY_RECEIVED**; the journal shows the reversal, crediting inventory with what the movement removed.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §9.6 — six audit rows for the one click; the original journal REVERSED and `GRN-…-REV` (`reversal_of_id` set) Dr 2300 400.00 / Cr 1200 400.00, **dated the first day of the month**, so search Journal Entries for it rather than reading the top of the list; the receipt line's `inventory_transaction_id` is cleared.
- **Leaves:** 6 on hand; one cancelled receipt.

### TC-BUY-005 — A receipt that has been invoiced cannot be cancelled

- **Covers:** plan 7.8
- **Fixture:** `po-invoiced`
- **Steps:** as the fixture's **Firm admin**, Buy > Goods Receipts → select the **receipt of 6** (the one the fixture invoiced) → **Cancel**.
- **Expect:** refused — "Goods receipt GRN-… has been invoiced, so cancelling it would leave the accrual and the payable disagreeing. Cancel the purchase invoice first, or raise a purchase return." Nothing changes.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §9.7 — the refusal writes nothing, not even an audit row, and the receipt's `version` does not move; its query shows the invoice holding the receipt. What the fixture's invoice wrote is §9.8–9.9.
- **Leaves:** unchanged.

### TC-BUY-006 — Returning damaged goods to the supplier

- **Covers:** plan 7.9
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, Buy > Returns & notes > Purchase Returns → **New** → **Goods Receipt** picker (completed receipts only) → the **receipt of 6**. On its line set **Returning** **2**, click the **Damaged** chip → **Save Return** → select the draft → **Approve** → **Complete**. Then Inventory, Stock Ledger, Journal Entries, and Reports > Operational → **Damaged goods returned**.
- **Expect:** after save, "Purchase return PR-2026-2027-… created as a draft. Approving and completing it is what takes the stock off."; after Complete, **COMPLETED**. MAIN holds **8**. The Stock Ledger shows the return of 2 referencing the PR (the API reads `transaction_type: RETURN`). The journal shows the return's entry; the damaged-goods report lists the line. Open the return: product and unit read as code and name, not ids. The goods must still be on hand: a return for more than the location holds is refused at Complete ("This location holds … available, so … cannot be returned to the supplier from it.").
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §9.10. The return reads `grand_total` **236.00** (D-BUY-31) and, because the receipt has not been billed, posts **Dr 2300 Goods Received Not Invoiced 200.00 / Cr 1200 Inventory 200.00** with no tax and no payable (D-BUY-26). The return line reads `free_quantity` (0.0000 where nothing free goes back), and `current_return_quantity` is everything going back, free goods included; on the return reconciliation the received quantity of a line off a goods receipt is bought plus free, the returning quantity includes the free units, and `already_returned_quantity` counts what went back through the other document too. The Damaged chip is `purchase_return_lines.is_damaged` only — the movement's damaged bucket stays 0.
- **Leaves:** 8 on hand; a completed return.

### TC-BUY-007 — The purchasing reports have rows

- **Covers:** plan 7.10
- **Fixture:** `po-approved`
- **Steps:** as the fixture's **Firm admin**, Reports > **Operational**: Purchase order register, Orders not yet received, Overdue purchase orders, Orders by supplier, Orders by buyer, Purchases by product.
- **Expect:** each opens with a row count in the header. The register and "not yet received" include the fixture's order; by supplier names `Fixture Supplier <suffix>`; by product names `Bought Item <suffix>`. Overdue and by buyer may be empty in TEST01 — an empty report reads "Nothing to report", never a blank grid.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §9.13 — which tables each report reads; none writes a row. The fixture's order carries no expected date and no buyer, which is why it never appears in Overdue or By buyer.
- **Leaves:** unchanged.

### TC-BUY-008 — Paying the supplier

- **Covers:** plan 7.11
- **Fixture:** `po-invoiced`
- **Steps:** as the fixture's **Firm admin**, Buy > Payments → **Record Payment**: **Paid to** `<SUFFIX>-V`; **Amount** the bill's Outstanding (708.00); **Method** Bank; **Oldest first** → **Record payment**. Open Record Payment again for the same vendor.
- **Expect:** toast "PY-… recorded and posted to the ledger." *(The plan said `PAY-`; the series prefix is `PY`.)* The second time, the bill is gone from the list. Journal Entries shows the payment: Dr Accounts Payable / Cr Bank.
- **Data (HTTP):** `GET /api/v1/payments/parties?search=<SUFFIX>` lists the vendor by code and name. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §9.11 — the `settlements` row (PAYMENT, POSTED), one `settlement_allocations` row of 708.00, the bill's derived balance at 0.00 while its status stays APPROVED, and journal Dr 2100 / Cr 1010. Reversing a payment is §9.12.
- **Leaves:** a paid supplier invoice.

---

### TC-BUY-009 — A return the supplier pays back (refund)

- **Covers:** backlog 69 row 7, A34
- **Fixture:** `po-invoiced`
- **Also needs:** As *po-invoiced*, with the bill for the receipt of 6 paid in full (TC-BUY-008).
- **Steps:** as the fixture's **Firm admin**, Buy > Returns & notes > Purchase Returns → **New** off the **receipt of 6**, return **2**, **Outcome** *Refund* → Save → Approve → Complete. Buy > Payments → **Supplier refunds** → `<SUFFIX>-V` → on the return, **Record refund**: amount **100**, today, Bank → Save. Then **Record refund** again for more than is left. Then **Refunds** → **Reverse** with a reason. Then try **Cancel** on the return while a refund stands (record one again first).
- **Expect:** the credit shows Outcome *Refund*, Refunded 100, Available reduced by 100; Journal Entries has Dr Bank / Cr Accounts Payable. Over-refund is refused naming what is left. After Reverse the credit is whole again and the mirror journal posts. Cancelling the return while a refund stands is refused: "…Reverse the refund first." A return dated today can be refunded today at any hour. A refund dated tomorrow is refused, "A refund cannot be received on a future date."; one dated before the return, "A refund is received on or after the return, <date>." The goods must still be on hand: a return for more than the location holds is refused at Complete ("This location holds … available, so … cannot be returned to the supplier from it.").
- **Data:** the return line reads `free_quantity` (0.0000 where nothing free goes back), and `current_return_quantity` is everything going back, free goods included. On the return reconciliation (`GET /api/v1/purchase-returns/reports/reconciliation`) the received quantity of a line off a goods receipt is bought plus free, the returning quantity includes the free units, and `already_returned_quantity` counts what went back through the other document too (the bill for a receipt line, the receipt for a bill line).
- **Leaves:** what the steps made.

### TC-BUY-010 — A return to be replaced reopens the order

- **Covers:** backlog 69 row 7
- **Fixture:** `po-received`
- **Also needs:** As *po-received* with the order fully received (receipts of 4 and 6).
- **Steps:** return **2** off the receipt of 6 with **Outcome** *Replacement* → Approve → Complete. Open the purchase order. Then receive 2 more against the order.
- **Expect:** the order reads **Partially received** with 2 pending; the new receipt of 2 is accepted (no over-receipt refusal) and the order reads **Received** again. Change the return's outcome to *Credit* (list → **Change outcome**) before receiving: the order goes back to **Received**. The goods must still be on hand: a return for more than the location holds is refused at Complete ("This location holds … available, so … cannot be returned to the supplier from it.").
- **Data:** the return line reads `free_quantity` (0.0000 where nothing free goes back), and `current_return_quantity` is everything going back, free goods included. On the return reconciliation (`GET /api/v1/purchase-returns/reports/reconciliation`) the received quantity of a line off a goods receipt is bought plus free, the returning quantity includes the free units, and `already_returned_quantity` counts what went back through the other document too (the bill for a receipt line, the receipt for a bill line).
- **Leaves:** what the steps made.

### TC-BUY-011 — A return off a bill already paid leaves a supplier credit

- **Covers:** D-BUY-20
- **Fixture:** `po-invoiced`
- **Also needs:** As TC-BUY-008 (the bill paid in full).
- **Steps:** Buy > Returns & notes > Purchase Returns → **New** off the **paid bill**, return 2 → Approve → Complete. Buy > Payments → **Supplier credits** → `<SUFFIX>-V`. Raise another bill and **Apply** the credit to it.
- **Expect:** the paid bill does not reappear in Record Payment; the return appears as a supplier credit for its value; applying it lowers the new bill's outstanding by that much. Deleting `<SUFFIX>-V` is refused while the credit stands. Delete the supplier before applying the credit to see the refusal for the credit alone; afterwards it is refused for the open bill. The goods must still be on hand: a return for more than the location holds is refused at Complete ("This location holds … available, so … cannot be returned to the supplier from it.").
- **Data:** the return line reads `free_quantity` (0.0000 where nothing free goes back), and `current_return_quantity` is everything going back, free goods included. On the return reconciliation (`GET /api/v1/purchase-returns/reports/reconciliation`) the received quantity of a line off a goods receipt is bought plus free, the returning quantity includes the free units, and `already_returned_quantity` counts what went back through the other document too (the bill for a receipt line, the receipt for a bill line).
- **Leaves:** what the steps made.

### TC-BUY-012 — Input credit blocked on a purchase (a car, catering)

- **Covers:** backlog 78 row 1, D-TAX-1, A36
- **Fixture:** `buy-ready`
- **Also needs:** *buy-ready* with the GST template; a product `QA-CAR`; a firm with a GST number for the GSTR-3B step (TEST01 has none).
- **Steps:** Masters > Products → `QA-CAR` → **Input credit** *Blocked (s.17(5))* → Save. Bill it from a receipt at 18% GST and approve. Open Journal Entries for the bill, and Accounts > GST Returns → GSTR-3B for the month. Then on another bill line set **Input credit** *Eligible* explicitly.
- **Expect:** the bill line shows a **Credit blocked** badge. The journal debits **5450 Input Tax Not Claimable** with the whole tax and **no** input CGST/SGST. GSTR-3B shows the tax in 4(A)(5) and again in **4(B)(1)**, net 4(C) without it. The line set to *Eligible* claims as usual. A user without `PRODUCT_TAX_MANAGE` sees the product's Input credit read-only.
- **Leaves:** what the steps made.

### TC-BUY-013 — A composition supplier charges no GST

- **Covers:** backlog 78 row 2, A37
- **Fixture:** `buy-ready`
- **Also needs:** *buy-ready*; a supplier `QA-COMP` with a GSTIN.
- **Steps:** Masters > Vendors → `QA-COMP` → **GST type** *Composition* → Save. Then set *Unregistered* while the GSTIN is still filled → Save. Order, receive and bill from `QA-COMP` (as Composition).
- **Expect:** *Unregistered with a GSTIN* is refused with the server's message and the form stays open with what was typed. The bill editor shows "This supplier charges no GST; the bill will carry no tax."; the approved bill has tax 0 and claims no credit. A supplier with GST type *Not set* is taxed as before.
- **Leaves:** what the steps made.

### TC-BUY-014 — GSTR-2B reconciliation

- **Covers:** backlog 78 row 3, §42.5
- **Fixture:** `buy-ready`
- **Also needs:** two approved bills in a month from a supplier with a GSTIN; the sample `docs/qa/tools/gstr2b_sample.json`, edited: `rtnprd` to the month as MMYYYY, `ctin` to the supplier's GSTIN, the two bill numbers, dates and amounts to the two bills' (the sample's second bill carries CGST 5 more than the books on purpose), and one invoice not in the books.
- **Steps:** Accounts > All Accounts screens > Tax filing > **GSTR-2B Reconciliation** → month → **Import 2B file**. Then **Match to bill…** on the *Not in books* row, then **Undo match**. Then Settings > Tax > GST Documents → **Claim input credit** *Only bills matched to GSTR-2B* → GSTR-3B for the month.
- **Expect:** rows read **Matched**, **Different** ("CGST … in 2B, … in the books"), **Not in books**; the "In books, not in 2B" section lists any bill 2B lacks. Importing the month again replaces it. Under *matched only*, 3B claims only matched bills and shows the rest as *Held back — not yet in GSTR-2B*.
- **Leaves:** what the steps made.

### TC-BUY-015 — Reorder from what sold (planning formula)

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 69 row 12, A39
- **Fixture:** `buy-ready`
- **Also needs:** a product with **no** reorder or minimum level typed, 100 received in one warehouse long ago and 90 delivered to customers within the last 90 days (10 left); a second product with a reorder level typed.
- **Steps:** as the fixture's **Firm admin**: Settings > Buying > **Purchase Settings** → **Reorder planning** → Open. Note it says the firm plans on typed levels. Reports > Operational → **Below reorder level**. Then choose **From sales**, leave 90 / 7 / 7 / 30 → Save. Open the report again, and Buy > Purchase Orders → "..." → **Below reorder level...**. Try Cover 0 → Save. Open the dialog as a role without *Manage purchase settings*.
- **Expect:** on typed levels the first product is **not** listed. On sales it is listed with **Basis Sales**, **Avg/day 1**, reorder level 14, maximum 44 and **suggested 34** (44 - 10), whole units; the second product keeps **Basis Level** with its typed figures. The dialog names the basis above the grid, and **Raise draft orders** raises a draft for 34. Cover 0 is refused with the range. Without the permission the dialog is read-only. Settings > Platform > System > Audit Logs shows **purchase.reorder_planning_updated**.
- **Leaves:** what the steps made.

### TC-BUY-016 — One quantity picture per order line, and the billing status

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 69 row 5, A33
- **Fixture:** `po-invoiced`
- **Also needs:** as *po-invoiced*: an order for 10, receipts of 4 and 6 completed, a bill for the receipt of 6 **approved**.
- **Steps:** as the fixture's **Firm admin**, Buy > Purchase Orders → open the order and select its line. Then Purchase Invoices → raise a second bill for the receipt of 4 but leave it in **Draft**; reopen the order. Approve that bill; reopen. Then Purchase Returns → return 2 off the receipt of 6 → Approve → Complete; reopen. Open a **Draft** order beside it.
- **Expect:** after the first bill the header reads *Part billed*, and the side panel's *Received and billed* block says Received 10, Billed 6, Pending 0, **To bill 4**. The draft bill changes nothing (only approved bills count). After approving it: *Billed*, **Complete**, To bill 0. After the return of 2: Returned 2, **To bill 0** still (the return is set against what was kept), and Complete stays. A draft order shows none of the block and no billing chip. Nothing in the editor lets the figures be typed, and saving the order does not send them.
- **Data:** the return line reads `free_quantity` (0.0000 where nothing free goes back), and `current_return_quantity` is everything going back, free goods included. On the return reconciliation (`GET /api/v1/purchase-returns/reports/reconciliation`) the received quantity of a line off a goods receipt is bought plus free, the returning quantity includes the free units, and `already_returned_quantity` counts what went back through the other document too (the bill for a receipt line, the receipt for a bill line).
- **Leaves:** what the steps made.

### TC-BUY-017 — A debit note on a bill already paid

*Added 2026-10-02 (decision A4).*

- **Preconditions:** an approved supplier bill of 1,180.00 (1,000 + 18% GST), **paid in full**, and a second approved bill of the same supplier for 500.00.
- **Steps:** Buy > Returns & notes > **Debit Notes** → New against the paid bill: 100 on its line, reason *Price difference* → Save → **Approve**. Pay → New payment for the supplier: look at the supplier credits. Set the debit note's credit against the second bill. Then cancel the debit note. Then raise and approve it again, record a supplier **refund** of 50 against its credit, and try to cancel it.
- **Expect:** approval succeeds (it used to refuse "still owes only 0"). The payment screen lists a credit of **118.00** marked as a debit note; set against the second bill, that bill owes **382.00**. Cancelling the debit note withdraws it -- the second bill owes 500.00 again and the credit is gone. With the refund standing, the cancel is refused ("Reverse that refund…"). A return dated today can be refunded today at any hour. A refund dated tomorrow is refused, "A refund cannot be received on a future date."; one dated before the return, "A refund is received on or after the return, <date>."

### TC-BUY-018 — Reorder orders from the preferred supplier

*Added 2026-10-02 (decision A18).*

- **Preconditions:** two active suppliers, `QA-V1` (who billed the product last, at 100) and `QA-V2` (never billed it); the product below its reorder level; its purchase price 90.
- **Steps:** Masters > Products → open the product → **Preferred supplier** `QA-V2` → Save. Buy > Purchase Orders → "..." → **Below reorder level...**. Then mark `QA-V2` inactive and open the dialog again. Then open the product as a role that cannot see suppliers.
- **Expect:** with `QA-V2` preferred the row names **QA-V2** at **90.00** (the last bill's 100 was QA-V1's, so it does not carry over); **Raise draft orders** raises a draft to QA-V2. With QA-V2 inactive the row falls back to **QA-V1** at 100. Saving the product with QA-V2 inactive and the supplier untouched still works. Choosing an inactive supplier is refused ("Preferred supplier not found, or not active.").
---

### TC-BUY-019 — Supplier rates, catalogue, order multiples and lead times

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog BUY-3 (A97), BUY-4 (A101), BUY-5 (A103), BUY-6 (A105)
- **Fixture:** `po-received`
- **Also needs:** a price list scoped to the vendor `<SUFFIX>-V` with a rate for `<SUFFIX>-B`; one completed receipt of the order of 10 (the fixture has two).
- **Steps:** as the fixture's **Firm admin**: Masters > **Vendors** → `<SUFFIX>-V` → **Standing discount %** 5 → Save. Settings > Set up > Pricing > **Price Lists** → New, scope *Supplier* `<SUFFIX>-V`, rate 90 for `-B`. Masters > Vendors → `<SUFFIX>-V` → **Catalogue** tab → add `-B`: supplier code `SK-1`, price 80, minimum order 20, **order multiple 10**, pack size, lead time 7 days; also import a catalogue file (Import → *supplier catalogue*). Settings > Buying > **Purchase Settings** → order quantity policy **Warn**, then **Refuse**. Buy > **Purchase Orders** → New for `<SUFFIX>-V`: add `-B` with the price and discount boxes blank, quantity 25; use the hint's **Use N**; save. Look at the expected date, then the vendor's lead-time summary. Reports > Operational → Below reorder level (From sales).
- **Expect:** a blank price and discount are filled from the supplier's terms: the catalogue price ranks between the supplier price list and the product's purchase price, and the supplier code is filled; the standing discount fills a blank discount **unless a supplier price list prices the line, whose own discount (0 where none is typed) then applies**. Quantity 25 against minimum 20 and multiple 10 shows a hint "use 30"; under Warn the order saves, under Refuse it is refused naming the multiple. The expected date is the order date plus the catalogue lead time. The vendor shows quoted lead time and what the deliveries actually took (average days, late receipts, on-time share), derived from completed receipts; a cancelled receipt stops counting. The reorder planner rounds its suggestion to the multiple and uses the lead time for the sales-based reorder point. Sales price lists ignore supplier-scoped lists. An explicit price or discount of 0 typed on the line is kept.
- **Leaves:** a catalogue row, a supplier price list, a draft order.

### TC-BUY-020 — A requisition becomes orders, and an approved order is amended

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog BUY-7 (A109), BUY-8 (A102)
- **Fixture:** `po-approved`
- **Also needs:** a second vendor and a second product with a preferred supplier; a role holding PURCHASE_REQUISITION_CREATE but not PURCHASE_APPROVE.
- **Steps:** as the **Purchasing** user: Buy > All Buy screens > Documents > **Requisitions** → New with two lines (one naming a supplier, one with only a product that has a preferred supplier, then one with neither) → Save → Submit. Try Approve. As the **Firm admin**: Approve → **Convert to orders**. Separately Reports > Operational > Below reorder level → **Raise requisition**. Then open the approved purchase order → **Amend**: change a quantity → Save; open **Revisions**; print.
- **Expect:** a requisition is numbered in its own **PRQ** series; a requisition with a line that has neither a supplier nor a preferred supplier saves and can be approved, and **Convert to orders** refuses it by name; only an approver sees Approve. Converting raises **one draft purchase order per supplier** priced from the supplier's terms; the requisition becomes ORDERED and is history. Raise requisition from the reorder screen makes a requisition rather than orders. Amend on the approved order keeps it approved, bumps the **revision number**, and keeps the earlier version listed under Revisions; the print titles it as an amendment.
- **Leaves:** a requisition, two draft orders, a revised order.

### TC-BUY-021 — Goods held for inspection on receipt

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog BUY-9, A100
- **Fixture:** `po-approved`
- **Also needs:** a user holding PURCHASE_INSPECT.
- **Steps:** as the fixture's **Firm admin**: Masters > Products → `<SUFFIX>-B` → switch on **Inspect on receipt** → Save (or the same on its category). Buy > Goods Receipts → receive 10 and complete. Open Stock > All Stock screens > Stock > **Inventory**. Then Buy > All Buy screens > Documents > **Quality Inspection**: pass 6 and reject 4 written off on one receipt; on a second receipt pass 6 and reject 4 left for a return, then return those 4: sellable stays at what passed and quarantine empties. Passed and rejected must add up to everything the line holds. Cancel a second receipt that is still on hold.
- **Expect:** completing the receipt puts the goods in **quarantine** — owned and valued as received but not sellable or issuable. The Quality Inspection screen lists the held lines; passing releases that quantity to stock; rejecting either writes it off at once or leaves it in quarantine for a purchase return (condition Quarantine). Cancelling a receipt whose lines are still held releases the holds with it. Without PURCHASE_INSPECT the decision is refused.
- **Leaves:** a receipt, inspections, a write-off.

### TC-BUY-022 — A supplier bill outside tolerance, and an order over budget

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog BUY-10 (A99), BUY-14 (A106)
- **Fixture:** `po-received`
- **Also needs:** a firm administrator, and a user on a **custom role** that holds PURCHASE_APPROVE without PURCHASE_APPROVE_OVER_TOLERANCE and PURCHASE_APPROVE_OVER_BUDGET; the seeded *Purchase Manager* holds both and approves.
- **Steps:** as the **Firm admin**: Settings > Buying > **Purchase Settings** → **Bill matching**: price tolerance 2% and amount tolerance 50 → Save. Buy > Purchase Invoices → New for the receipt of 6 with the rate 10% above the order → Save → Approve as the **custom-role approver**, then as the administrator. Next Settings > Buying > **Purchase Budgets** → New for this month, category of `-B`, amount 500; set **Past a purchase budget** on Purchase Settings to **Warn**, then **Needs approval**. Raise and approve a purchase order of 10 × 100 as the custom-role approver, then as the administrator; open the order's budget panel.
- **Expect:** the bill is **held** at approval and refused naming the breach (price over tolerance) for a user without the over-tolerance right — single and bulk approve alike; the administrator may approve it. The budget is a month, optionally one branch and one category; what it has used is the value before tax of approved orders in that month, derived on every read. Under Warn the approval proceeds with a warning; under **Needs approval** it is refused for a user without PURCHASE_APPROVE_OVER_BUDGET. The order's budget panel shows budget, used and what the order adds.
- **Leaves:** settings, a bill, a budget.

### TC-BUY-023 — A payment run and its bank file

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog BUY-11, A110
- **Fixture:** `po-invoiced`
- **Also needs:** a second approved supplier bill for another vendor with a bank account saved; a cashier user (CASHIER cannot approve a run); a bank account on `<SUFFIX>-V` too, or untick its bill: a run that pays a supplier with no bank account has no bank file.
- **Steps:** as the fixture's **Firm admin**: Buy > All Buy screens > Money > **Payment Runs** → New → *Propose* bills falling due by today plus 30 days. Untick one bill; lower another amount; try an amount above what the bill owes. Save the draft. As the **cashier** try Approve. As the administrator: Approve. Download the **bank file**. Cancel a second draft run.
- **Expect:** the proposal lists every supplier bill still owing that falls due by the date. A draft holds the chosen bills and amounts, never more than a bill still owes. Approving needs PAYMENT_RUN_APPROVE (the cashier is refused), records **one payment per supplier** by bank transfer allocated to that supplier's bills, all in one commit: a run that cannot pay every supplier pays none. The bank file is a generic NEFT CSV with one row per supplier from its primary bank account (no bank-specific layout yet). A cancelled draft pays nothing.
- **Leaves:** payments and a run.

### TC-BUY-024 — Supplier performance, price trend and ratings

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog BUY-12 (A107), BUY-15 (A74)
- **Fixture:** `po-received`
- **Also needs:** the receipts made on different days from the order's expected date (one late); two users with PURCHASE_VIEW or VENDOR_VIEW.
- **Steps:** as the fixture's **Firm admin**: Reports > Operational → **Supplier performance**, then **Supplier price trend**. Masters > Vendors → `<SUFFIX>-V` → **Ratings** → rate each criterion 1-5 → Save; change it and save again; try 0 and 6. Sign in as a second user and rate; open the tab again; **Delete** your own rating.
- **Expect:** the performance report has a row per supplier with receipts, **On time %**, **Rejected %**, **Returned %** and **Short %**; the trend shows month, quantity and **Average rate**. A rating criterion outside 1-5 is refused. The tab shows the averages per criterion, the overall figure, every rating and the reader's own; one live rating per person per supplier — the earlier ones stay as history and the audit row keeps the earlier scores. Deleting removes only your own.
- **Leaves:** ratings.

### TC-BUY-025 — Supplier volume rebates

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog BUY-13, A124
- **Fixture:** `po-invoiced`
- **Also needs:** an approved bill of `<SUFFIX>-V` for 600 before tax (708.00) **dated inside a period that has already ended**, for example last month. The fixture's own bill is dated today, so raise one of the case's own dated earlier.
- **Steps:** as the fixture's **Firm admin**: Buy > All Buy screens > Money > **Supplier Rebates** → New for `<SUFFIX>-V`: a period **that has already ended** and covers the earlier-dated bill of 708.00 (600 before tax) and two slabs (for example from 0 at 1%, from 500 at 2%). Save. Open it and read the volume, the slab reached and the amount. **Accrue**. Accrue again. **Reverse accrual**. Accrue once more, then Accounts > All Accounts screens > Books > **Party Adjustments** → New of kind *Supplier rebate* naming the agreement. Cancel a second agreement.
- **Expect:** the volume is derived on every read: the supplier's approved bills dated in the period at taxable value, less its completed purchase returns in the period; the **highest slab reached** sets the rate on the **whole** volume (600 at 2% = 12.00). Accrual snapshots the volume, rate and amount with the journal that booked them (Dr *Supplier Rebate Receivable*), and a second accrual of the same period is refused; nothing re-reads the bills afterwards. Reversing the accrual takes the journal off. The rebate is settled by an approved **party adjustment of kind Supplier rebate** that names the agreement (not a debit note, which has to name one bill); what has been settled is the sum of those. The control account exists for new and existing firms.
- **Leaves:** an agreement, journals.

### TC-BUY-026 — Landed cost spread over received goods

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog BUY-16, A129
- **Fixture:** `po-received`
- **Also needs:** a freight bill from a transporter (a second vendor) of 1,000; part of the goods already sold so that on hand is less than received (deliver 4 of the 10).
- **Steps:** as the fixture's **Firm admin**: Buy > All Buy screens > Money > **Landed Costs** → New: pick the two completed receipts, add a charge (freight, the transporter as billing party, its bill number, 1,000), apportion **by value**. Preview and post. Open the voucher and read each product's split. Then try **by quantity**, **by weight**, and cancel a voucher. Check Accounts > Balance Sheet and the stock valuation.
- **Expect:** the charge's own bill is booked to *Expenses Included in Valuation*; the voucher spreads the total over the receipts' lines by taxable value (or quantity, or weight; the rounding residual goes to the largest line) and splits each share by the product's quantity still on hand: that part **revalues the stock** through a zero-quantity *Landed cost* movement (new average cost), and the rest goes to **cost of goods sold**. Journal: Dr Inventory, Dr Cost of Goods Sold, Cr Expenses Included in Valuation. Cancelling reverses the journal and takes the on-hand value back off at today's quantity. Reading needs PURCHASE_VIEW, posting PURCHASE_APPROVE.
- **Leaves:** a landed cost voucher and journals.

### TC-BUY-027 — Supplier credit set against an opening bill

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog BUY-17, A52
- **Fixture:** `buy-ready`
- **Also needs:** an opening supplier bill for `<SUFFIX>-V` (Accounts > All Accounts screens > Books > Opening Balances) of 500, and a supplier credit of 200 (a purchase return refunded as credit, as in TC-BUY-011).
- **Steps:** as the fixture's **Firm admin**: apply the supplier credit — the apply dialog lists bills and opening bills (marked "(opening)") — to the opening bill for 200. Open Buy > **Payments** → Record Payment for the supplier. Open the opening bill list. Try to delete the supplier. Then cancel the opening bill.
- **Expect:** the credit is accepted against the opening bill (it used to refuse it). Record Payment shows the opening bill owing **300**; the opening bill list shows the credit counted; the supplier cannot be deleted while it holds an application. Cancelling the opening bill withdraws the credit set against it and the 200 is available again.
- **Leaves:** a credit application.

### TC-BUY-028 — Free goods to customers, and gifts from a supplier

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog BUY-1 (A111), BUY-2 (A112)
- **Fixture:** `po-approved`
- **Also needs:** a customer; a user holding SUPPLIER_GIFT_MANAGE; the firm's TDS 194R rules are described in the compliance notes.
- **Steps:** as the fixture's **Firm admin**: Masters > Products → `<SUFFIX>-B` → switch **Free issue only** on; try to put it on a quotation or an invoice line with a price. Receive 5 units on a goods receipt with a **Scheme** name on the line. Stock > All Stock screens > Stock > Inventory → Write off 2 with reason *Free to customer* and the customer, and 1 with reason *Sample*. Reports > Operational → **Free goods**. Then Buy > All Buy screens > Money > **Supplier Gifts** → record a gift from the supplier (a fridge, value 20,000, to the firm, then one taken for personal use). Open the **194R summary**. Cancel one.
- **Expect:** a free-issue-only product is refused on a priced sales line by name. The receipt line keeps the scheme; the write-offs post to *Promotional Expense* (not Inventory Adjustment) and carry the customer; the Free goods report shows what came in free, what went out free and what is left. A supplier gift posts Dr the asset or expense account named (or *Drawings* when the owner kept it) and Cr *Supplier Incentives Received*, with no input tax; the gift register links to the receipt line marked "gift, not stock"; the 194R summary totals gifts per supplier; cancelling reverses the journal. Managing gifts needs SUPPLIER_GIFT_MANAGE.
- **Leaves:** write-offs, a register row, journals.

---

**The purchasing features of backlog 86 (PG-1 to PG-14), built 2026-10-05.**
Cases TC-BUY-029 onward were written from the code and its automated tests on
2026-10-05 and have not yet been run by hand. Each stands alone: it names what
it needs and reads nothing another case left. The new screens are under
Buy > All Buy screens > Documents (**Requests for quotation**, **Rate
contracts**, **Supplier schemes**, **Bills of entry**), Buy > All Buy screens >
Money > **Payables by Month**, Accounts > All Accounts screens > **Fixed
assets**, and Settings > Tax > **TDS on purchases (194Q, 194C, 194J)**. The
journals below name the accounts a firm starts with: 1000 Cash, 1010 Bank,
1200 Inventory, 1310 Input IGST, 1320 Input CGST, 1330 Input SGST, 1430 TCS
Receivable, 1500 Fixed Assets, 1590 Accumulated Depreciation, 2100 Trade
Payables, 2300 Goods Received Not Invoiced, 2700 TDS Payable, 2800 Customs
Duty Payable, 4950 Exchange Gain/Loss, 4960 the gain or loss on disposing of
an asset, 5220 Customs Duty and 6950 Depreciation.

**Imports and capital goods run on the full chain.** The import cases
(TC-BUY-070 to 076) and the capital-goods case TC-BUY-077 no longer need the
buying stages switched off: since 2026-10-05 the purchase order carries
**Currency** and **Exchange rate**, and the order line and the receipt line a
**Capital goods** tick. They are written for a firm that orders, receives and
bills. Two cases keep the bill typed alone, TC-BUY-086 (an import) and
TC-BUY-088 (capital goods), and **only those two change a firm-wide
setting**: Settings > Buying > Purchase Settings > **Buying stages** with
**Purchase order** off, which takes **Goods receipt** off with it. Run those
two when nobody else is buying in the firm, or in a firm of its own, and
switch both back on afterwards. TC-BUY-086 to 090 were added after the fixes
of 2026-10-05 and, like the rest, have not been run by hand.

### GST purchase register and HSN summary of purchases (backlog 86 #17)

### TC-BUY-029 — The GST purchase register lists an approved bill by tax head

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #17 (PG-1)
- **Fixture:** `po-invoiced`
- **Steps:** as the fixture's **Firm admin**, Reports > **Financial** → **GST purchase register**, the period covering today. Find the fixture's bill by its number. Then Buy > Purchase Invoices → New for the receipt of 4, save it and leave it a **draft**; open the report again.
- **Expect:** one row for the approved bill: Type **Bill**, the supplier's name and GSTIN (blank where the supplier has none), Taxable **600.00**, CGST **54.00**, SGST **54.00**, IGST 0.00, Total tax **108.00**, Not claimable 0.00, Reverse charge 0.00, Capital goods tax 0.00, Bill total **708.00**. The draft bill is not listed; neither is a cancelled one. Only approved and closed bills count.
- **Leaves:** a draft bill.

### TC-BUY-030 — The HSN summary folds the same bills by HSN code and unit

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #17 (PG-1)
- **Fixture:** `po-invoiced`
- **Also needs:** an HSN code on `<SUFFIX>-B` (the fixture creates it with none), or a product of the case's own with one; a second product with **no** HSN code, bought and billed from the same supplier (order 1 at 100, receive, bill, approve).
- **Steps:** as the fixture's **Firm admin**, Reports > Financial → **HSN summary of purchases**, the period covering today.
- **Expect:** a row for the HSN of `<SUFFIX>-B` with its unit, Quantity **6**, Taxable **600.00**, CGST 54.00, SGST 54.00, Total tax 108.00 and Bills **1** (more where other bills in the period carry the same HSN). The product with no HSN shows under a **blank** HSN, so the gap is visible, not folded into another row.
- **Leaves:** nothing beyond what it needed.

### TC-BUY-031 — Tax that may not be claimed shows in Not claimable

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #17 (PG-1)
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, Buy > Purchase Invoices → New for the receipt of 6; on its line set **Input credit** to *Blocked (s.17(5))* → save → **Approve**. Reports > Financial → **GST purchase register**.
- **Expect:** the bill's row carries CGST 54.00 and SGST 54.00 as charged, Total tax 108.00 and **Not claimable 108.00**. The heads are what the supplier charged; the last column says how much of it the firm may not claim.
- **Leaves:** an approved bill with blocked credit.

### TC-BUY-032 — A debit note and a purchase return are minus rows on their own dates

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #17 (PG-1, debit notes and returns netted in)
- **Fixture:** `po-invoiced`
- **Steps:** as the fixture's **Firm admin**, Buy > Returns & notes > **Debit Notes** → New against the fixture's bill: 100 on its line → Save → **Approve**. Buy > Returns & notes > Purchase Returns → New off the **receipt of 6**: Returning **2** → Save → Approve → Complete. Reports > Financial → **GST purchase register**, then **HSN summary of purchases**.
- **Expect:** besides the bill's row, a row of Type **Debit note** with the bill's number under **Against bill**, Taxable **-100.00**, CGST **-9.00**, SGST **-9.00**; and a row of Type **Purchase return**, Taxable **-200.00**, CGST **-18.00**, SGST **-18.00**. Each is dated the day it was raised, not the bill's day. The HSN summary's row for the product is lower by the same amounts. A return of goods that were never billed is not listed. The goods must still be on hand: a return for more than the location holds is refused at Complete ("This location holds … available, so … cannot be returned to the supplier from it.").
- **Leaves:** a debit note, a return.

### Payables by supplier and month (backlog 85; backlog 86 #20)

### TC-BUY-033 — What each supplier is owed, by month, agrees with the books

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 85, backlog 86 #20 (PG-2)
- **Fixture:** `po-invoiced`
- **Steps:** as the fixture's **Firm admin**, Buy > All Buy screens > Money > **Payables by Month**. Read the row for `<SUFFIX>-V`, the Total row and the line under the grid. Switch **By invoice date** to **By due date**. Narrow to the supplier with the **All suppliers** box.
- **Expect:** the page opens on **Owed**, as of today. The supplier's row shows **708.00** in this month's column and **708.00** under **Outstanding** (more if the supplier has other open bills). The columns are Supplier, **Older**, one per month, **Later**, **Credits**, **Outstanding**. The Total row sums every supplier, and the line under it reads "Agrees with the books: control account 2100 holds …" with the same figure. If it reads "Does not agree with the books: control account 2100 holds …", that is a failure to report with both figures. By due date the 708.00 moves to the month the bill falls due.
- **Leaves:** nothing.

### TC-BUY-034 — A part payment, the Paid view, and the branch filter

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 85 (PG-2)
- **Fixture:** `po-invoiced`
- **Steps:** as the fixture's **Firm admin**, Buy > Payments → **Record Payment**: `<SUFFIX>-V`, amount **200.00**, Bank, against the bill → Record payment. Buy > All Buy screens > Money > **Payables by Month**. Switch **Owed** to **Paid**. Back on Owed, pick a branch in **All branches**. **(HTTP)** `GET /api/v1/purchase-invoices/reports/payables?as_of=<today>&view=paid&branch_id=<a branch id>`.
- **Expect:** Owed shows **508.00** for the supplier and still agrees with 2100. Paid shows **200.00** in this month's column, with the column headed **Paid**. With a branch chosen the line under the grid reads "Narrowed to a branch: advances and refunds name no branch, so there is no books check." The HTTP call is refused: "A payment names no branch, so the Paid view cannot be narrowed to one. Clear the branch filter."
- **Leaves:** a payment of 200.00.

### TC-BUY-035 — Supplier credit sits in Credits, not in a month

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 85 (PG-2), D-BUY-32
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, Buy > Purchase Invoices → bill the **receipt of 6** and approve (708.00); Buy > Payments → pay it in full. Buy > Returns & notes > Purchase Returns → New off the **receipt of 6 after its bill has been approved and paid**: Returning **1** → Save → Approve → Complete. Buy > All Buy screens > Money > **Payables by Month**.
- **Expect:** the paid bill owes nothing in this month, and the return's value shows as a minus figure under **Credits** (-118.00 for the 1 returned), so the supplier's total is the credit alone. A return off a receipt no bill names posts Dr 2300 / Cr 1200 and is no credit. The total still agrees with control account 2100: the page counts every document that posts to it, not bills alone. The goods must still be on hand: a return for more than the location holds is refused at Complete ("This location holds … available, so … cannot be returned to the supplier from it.").
- **Data:** the return line reads `free_quantity` (0.0000 where nothing free goes back), and `current_return_quantity` is everything going back, free goods included. On the return reconciliation (`GET /api/v1/purchase-returns/reports/reconciliation`) the received quantity of a line off a goods receipt is bought plus free, the returning quantity includes the free units, and `already_returned_quantity` counts what went back through the other document too (the bill for a receipt line, the receipt for a bill line).
- **Leaves:** a return, a paid bill.

### Cash purchase in one step (backlog 86 #19)

### TC-BUY-036 — Approve a bill and pay it in the same step

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #19 (PG-3)
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, Buy > Purchase Invoices → New for the receipt of 6 → save. Select the draft → **Approve**. In the dialog **Approve PI-…** tick **Paid now**; leave **Method** *Cash*, **Amount** blank ("Blank pays the full bill.") and **Date paid** blank → **Approve and pay**. Then Buy > Payments, Record Payment for the supplier, and Accounts > Journal Entries.
- **Expect:** the dialog reads "Approving posts the bill to the books." and the button changes from **Approve** to **Approve and pay** when Paid now is ticked. Afterwards the bill is **APPROVED** and a payment `PY-…` of **708.00** dated the bill's date is in Payments, allocated to this bill; Record Payment no longer lists the bill. Two journals: the bill's, Dr 2300 Goods Received Not Invoiced 600.00, Dr 1320 Input CGST 54.00, Dr 1330 Input SGST 54.00 / Cr 2100 Trade Payables 708.00; and the payment's, Dr 2100 Trade Payables 708.00 / Cr 1000 Cash 708.00.
- **Leaves:** an approved bill, paid.

### TC-BUY-037 — Paying part now leaves the rest owing; more than the bill is refused

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #19 (PG-3)
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, bill the receipt of 6 and save the draft. **Approve** → tick **Paid now**, **Method** *Bank*, **Amount** `800` → **Approve and pay**. Then change Amount to `300`, **Reference** `NEFT-QA-0300` → **Approve and pay**.
- **Expect:** 800 is refused inside the dialog, which stays open with what was typed: "Bill PI-… owes 708.00, so 800 cannot be paid against it now. Record an advance through Payments." (the figures may print with more decimals). The bill is **still a draft**: the refusal took the approval back with it. With 300 the bill is approved, a bank payment of 300.00 is recorded, and Record Payment shows the bill owing **408.00**. Payment journal: Dr 2100 Trade Payables 300.00 / Cr 1010 Bank 300.00.
- **Leaves:** an approved bill owing 408.00.

### TC-BUY-038 — Reversing the payment leaves the bill approved and owing

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #19 (PG-3)
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, bill the receipt of 6, **Approve** with **Paid now** ticked and everything else as offered → **Approve and pay**. Buy > Payments → select the payment → **Reverse** with a reason. Open the bill and Record Payment for the supplier.
- **Expect:** the payment made with the approval is an ordinary payment: it reverses like any other. Afterwards the bill is still **APPROVED** and owes **708.00** again; the payment's mirror journal is posted (Dr 1000 Cash 708.00 / Cr 2100 Trade Payables 708.00).
- **Leaves:** an approved bill, unpaid; a reversed payment.

### TC-BUY-039 — Paid now needs the right to record payments

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #19 (PG-3)
- **Fixture:** `po-received`
- **Also needs:** a user hired with the *Purchase Manager* job template, who may approve bills (PURCHASE_APPROVE) but not record payments (no PAYMENT_CREATE).
- **Steps:** as the **Purchase Manager**, bill the receipt of 6, save, **Approve**. Look at the dialog. **Approve**. **(HTTP)** on a second draft bill, as the same user: `POST /api/v1/purchase-invoices/{id}/approve` with body `{"payment": {"method": "CASH"}}`.
- **Expect:** the dialog offers **no Paid now** tick and its button reads **Approve**; the bill approves and owes 708.00. The HTTP call is refused with **403**: "Paying a bill as it is approved records a payment, which needs PAYMENT_CREATE. Approve it without the payment, or ask somebody who may record payments." The second bill stays a draft.
- **Leaves:** an approved bill, unpaid.

### Attach the supplier's bill (backlog 86 #16)

### TC-BUY-040 — Attach, open, save and delete a file on a purchase bill

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #16 (PG-4)
- **Fixture:** `po-invoiced`
- **Also needs:** a PDF and a JPG or PNG photo on this PC, each under 10 MB.
- **Steps:** as the fixture's **Firm admin**, Buy > Purchase Invoices → open the fixture's approved bill → **Attachments**. Type a **Caption (optional)**, **Add file** → the PDF. Add the photo the same way. Use **Open** and **Save as** on one. Close, **Refresh** the list. Open Attachments again → **Delete** on the photo → **Delete**. Settings > Platform > System > Audit Logs.
- **Expect:** the dialog is titled **Attachments · …** and starts with "Nothing is attached yet." Files can be added to an **approved** bill: a paid bill still needs its paper. Each file lists with its name and caption; Open shows it, Save as writes the same file. The list's **Files** column shows a paper clip and **2**, then **1** after the delete. The delete asks "Delete …?" and says the trail keeps the removal; the audit log has `document_file.attached` twice and `document_file.removed` once.
- **Leaves:** one attached file.

### TC-BUY-041 — The wrong kind of file, and a file that is too large, are refused

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #16 (PG-4)
- **Fixture:** `po-invoiced`
- **Also needs:** a `.txt` or `.xlsx` file; a text file renamed to end `.pdf`; a PDF or image larger than 10 MB.
- **Steps:** as the fixture's **Firm admin**, open the bill's **Attachments** and **Add file** with each of the three in turn.
- **Expect:** each is refused and nothing is listed. The wrong extension: "Only PDF, JPG and PNG files may be attached; '…' is not one by its name." The renamed file: "'…' is not a PDF, JPG or PNG file by its contents." The large one: "The file is larger than 10 MB, the most it may be." The dialog stays open.
- **Leaves:** nothing.

### TC-BUY-042 — Attachments on a goods receipt, and who may add them

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #16 (PG-4)
- **Fixture:** `po-received`
- **Also needs:** a user hired with the *Read Only* job template; a photo under 10 MB.
- **Steps:** as the fixture's **Firm admin**, Buy > Goods Receipts → open a completed receipt → **Attachments** → **Add file** → the photo. Start a **new** receipt and press Attachments before saving it. Then sign in as the **Read Only** user and open the first receipt's Attachments.
- **Expect:** the completed receipt takes the file and its row shows the clip and **1** under **Files**. On a receipt not yet saved the dialog says "Save first to attach files". The Read Only user sees the file and can **Open** and **Save as**, but is offered neither **Add file** nor **Delete**: adding and removing follow the right to receive goods (on a bill, the right to create or edit bills).
- **Leaves:** one attached file.

### TDS 194C and 194J worked out (backlog 86 #10)

### TC-BUY-043 — One contractor bill past 30,000 proposes 194C and posts it

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #10 (PG-5)
- **Fixture:** `buy-ready`
- **Also needs:** a supplier of its own with **no other bill or payment this financial year** (April to March): a PAN whose fourth letter is not P or H (a company or firm), **Usual TDS section** *194C*, **Individual / HUF** left unset. Use a new supplier each time the case is run.
- **Steps:** as the fixture's **Firm admin**, order **400** of `<SUFFIX>-B` at **100** from that supplier, approve, receive and complete, bill the receipt and save. Select the draft → **Approve**. Read the dialog and leave **TDS to deduct** blank → **Approve**. Open Record Payment for the supplier, and the bill's journal. **(HTTP)** before approving, `GET /api/v1/purchase-invoices/{invoice_id}/tds-proposal`.
- **Expect:** the bill is 40,000.00 + 7,200.00 GST = **47,200.00**. The dialog shows what the server worked for this bill, on the base approval posts: the bill before GST, which is its lines **plus any additional charges** (a bill of 28,000 of lines with 5,000 of charges is past the 30,000 limit and proposes 660.00). The HTTP call answers the same section, rate and `proposed` 800.00. The dialog names the section and rate -- TDS 194C at 2%, basis OTHER -- then "Threshold crossed.", "Due so far: ₹800.00, already deducted: ₹0.00." and "Proposed on this bill: ₹800.00."; the box's helper reads "Blank takes the proposal (₹800.00); 0 deducts nothing." TDS is worked on the value **before GST**. After approval the supplier is owed **46,400.00**. Journal: Dr 2300 Goods Received Not Invoiced 40,000.00, Dr 1320 Input CGST 3,600.00, Dr 1330 Input SGST 3,600.00 / Cr 2100 Trade Payables 46,400.00, Cr 2700 TDS Payable 800.00.
- **Leaves:** an approved bill with TDS of 800.00.

### TC-BUY-044 — The year's limit crossed mid-year carries the earlier bills' tax

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #10 (PG-5)
- **Fixture:** `buy-ready`
- **Also needs:** a supplier of its own as in TC-BUY-043 (194C, a company PAN, nothing else this financial year).
- **Steps:** as the fixture's **Firm admin**, from that supplier raise, receive, bill and approve three bills in turn, all dated in this financial year, reading the Approve dialog each time and leaving **TDS to deduct** blank: **200** at 100 (20,000 before GST), then **400** at 100 (40,000), then **500** at 100 (50,000).
- **Expect:** bill 1 (20,000): "Threshold not yet crossed." and "Nothing is proposed on this bill." -- it is under 30,000 and the year is under 1,00,000. Bill 2 (40,000): one bill past 30,000, so **800.00** is proposed (2% of 40,000). Bill 3 (50,000): the year is now 1,10,000, past 1,00,000, so the tax is due on the **whole year**: 2% of 1,10,000 = 2,200.00, less the 800.00 already deducted, so **1,400.00** is proposed -- 400.00 more than 2% of this bill, which is bill 1's tax catching up. After the three, 2700 TDS Payable has been credited 2,200.00 for this supplier.
- **Leaves:** three approved bills.

### TC-BUY-045 — No PAN is 20%, and an individual is 1%

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #10 (PG-5)
- **Fixture:** `buy-ready`
- **Also needs:** two suppliers of their own with nothing else this financial year, both **Usual TDS section** *194C*: one with **no PAN**, one with a PAN and **Individual / HUF** set to *Yes*.
- **Steps:** as the fixture's **Firm admin**, from each supplier order **400** of `<SUFFIX>-B` at 100, receive, bill, and open **Approve**.
- **Expect:** the supplier with no PAN: 194C at 20%, basis NO_PAN, and **8,000.00** proposed on the 40,000. The individual: 194C at 1%, basis INDIVIDUAL_HUF, and **400.00** proposed. Where Individual / HUF is left unset, a PAN whose fourth letter is P or H is read as an individual or HUF.
- **Leaves:** two approved bills.

### TC-BUY-046 — 194J applies once the year passes 30,000

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #10 (PG-5)
- **Fixture:** `buy-ready`
- **Also needs:** a supplier of its own with a PAN and nothing else this financial year, **Usual TDS section** *194J*, **Technical services (2%)** not ticked. A second such supplier with **Technical services (2%)** ticked.
- **Steps:** as the fixture's **Firm admin**, from the first supplier raise, receive, bill and approve **250** of `<SUFFIX>-B` at 100 (25,000), then **100** at 100 (10,000), reading the Approve dialog each time. From the second supplier one bill of **400** at 100.
- **Expect:** the first bill proposes nothing: 194J has no single-bill limit and the year is under 30,000. The second takes the year to 35,000: 194J at 10%, basis PROFESSIONAL, and **3,500.00** proposed -- on the whole 35,000, not the 5,000 over the limit. That bill is 11,800.00 with GST and owes the supplier **8,300.00**. The technical-services supplier's bill of 40,000 proposes **800.00** at 2%, basis TECHNICAL.
- **Leaves:** three approved bills.

### TC-BUY-047 — Deducted once: money paid ahead of the bill, then the bill

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #10 (PG-5)
- **Fixture:** `buy-ready`
- **Also needs:** a supplier of its own as in TC-BUY-043 (194C, a company PAN, nothing else this financial year).
- **Steps:** as the fixture's **Firm admin**, Buy > Payments → **Record Payment**: that supplier, **Amount** `50000`, Bank, no bill to apply it to. Wait a moment and read the hint in **TDS deducted**. Then **TDS deducted** `1000`, **TDS section** *194C* → Record payment. Then order **500** of `<SUFFIX>-B` at 100 from the supplier, receive, bill, and open **Approve**. Approve.
- **Expect:** the advance posts Dr 2100 Trade Payables 50,000.00 / Cr 1010 Bank 49,000.00, Cr 2700 TDS Payable 1,000.00. The bill of 50,000 (59,000.00 with GST) then shows "Nothing is proposed on this bill.", because the tax on this money was deducted when it was paid; it approves with no TDS and owes the full 59,000.00, against which the advance can be set. The **TDS deducted** box on a payment is never filled for you; its hint follows the amount being paid. About half a second after `50000` is typed with nothing applied to a bill it reads "194C proposes ₹1000.00" (2% of the money paid ahead). Changing the amount, or applying part of it to a bill, works the hint again for the new figures; before 2026-10-05 it ignored the amount.
- **Leaves:** an advance, an approved bill.

### TC-BUY-048 — Overriding the proposal, and its limits

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #10 (PG-5)
- **Fixture:** `po-received`
- **Also needs:** a supplier of its own as in TC-BUY-043 with three bills of 40,000 before GST ready to approve (for each: order 400 at 100, receive, bill, save).
- **Steps:** as the fixture's **Firm admin**: (1) on the 194C supplier's draft bill, **Approve** → type `0` in **TDS to deduct** → Approve. (2) On a second such bill type `500` → Approve. (3) On a third type an amount equal to the bill's total. (4) On the fixture's own supplier, who has **no** TDS section, bill the receipt of 6 and **(HTTP)** `POST /api/v1/purchase-invoices/{id}/approve` with body `{"tds_amount": 50}`. Then Settings > Platform > System > Audit Logs.
- **Expect:** (1) nothing is deducted; the bill owes its full total. (2) 500.00 is deducted in place of the proposal -- which by now is 1,600.00, the first bill's tax with this one's, since nothing was deducted there -- and the bill owes 46,700.00. (3) refused: "TDS deducted must be less than what the bill owes." (4) refused: "TDS on a bill is worked out under 194C or 194J. Set the supplier's TDS section first, or deduct on the payment." -- and for a supplier with no section the Approve dialog shows no TDS lines at all. The audit row `purchase_invoice.approved` of an overridden bill keeps the proposed amount, the amount deducted and that it was overridden.
- **Leaves:** approved bills.

### TC-BUY-049 — The 194C and 194J settings

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #10 (PG-5)
- **Fixture:** `buy-ready`
- **Steps:** as the fixture's **Firm admin**, Settings > Tax > **TDS on purchases (194Q, 194C, 194J)**. Read the 194C and 194J cards beneath the 194Q settings, and the helper under each rate. On 194C change **Threshold per supplier, per year** to `150000` → **Save 194C**; press Save 194C again without changing anything. Type `35` in **Rate % (companies, firms and others)** → Save 194C; clear the box → Save 194C; type `0` → Save 194C; put `2` back. Type `-1` in **Threshold per supplier, per year** → Save 194C; put it back. Switch **Deduct 194J** off → **Save 194J**, then approve a bill from a 194J supplier past 30,000 in the year. Put everything back.
- **Expect:** a firm that never saved them reads 194C: **Threshold per payment** 30,000, **Threshold per supplier, per year** 1,00,000, **Rate % (companies, firms and others)** 2, **Rate % for an individual or HUF** 1, **Rate % without a PAN** 20; 194J: per year 30,000, **Rate % for professional fees** 10, **Rate % for technical services, call centres and royalty on films** 2, without a PAN 20, and **no** per-payment box. The second rate on 194C says it is used where the supplier is marked an individual or HUF on the supplier form, or, left on Auto, where the fourth letter of the PAN is P or H; on 194J, where the supplier is marked as providing technical services. No box speaks of a lower-deduction certificate. The first save toasts "194C settings saved."; the second says "Nothing has changed." A rate the server would refuse is refused in the card, before anything is sent: 35 and 0 read "Rate % (companies, firms and others) must be a number more than 0 and at most 30."; a blank reads "Enter Rate % (companies, firms and others): a number more than 0 and at most 30."; a threshold of -1 reads "The limit per supplier, per year cannot be below 0." With 194J switched off the bill proposes nothing. Saving needs ACCOUNT_MANAGE; a user without it sees the cards read-only. "Nothing has changed." is the screen's own: **(HTTP)** the server saves the same values again without complaint, and a blank rate sent to it answers "The rate cannot be blank: leave it out to keep what is saved."
- **Leaves:** the settings as they were.

### TCS charged by a supplier (backlog 86 #9)

### TC-BUY-050 — A rate alone is worked on the bill total, and posts to TCS Receivable

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #9 (PG-6)
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, Buy > Purchase Invoices → New for the receipt of 6. Type `0.1` in **TCS charged by supplier %**, leave **TCS amount** blank → save. Read the totals. **Approve**. Open Record Payment for the supplier and the bill's journal.
- **Expect:** the bill's own total stays **708.00** and its GST 108.00: TCS is outside GST's taxable value and moves no line. The totals show **TCS charged 0.71** (0.1% of 708.00, the bill **with** GST) and **Net payable 708.71**. After approval the supplier is owed **708.71**. Journal: Dr 2300 Goods Received Not Invoiced 600.00, Dr 1320 Input CGST 54.00, Dr 1330 Input SGST 54.00, Dr 1430 TCS Receivable 0.71 / Cr 2100 Trade Payables 708.71.
- **Leaves:** an approved bill with TCS.

### TC-BUY-051 — A typed TCS amount wins over the rate

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #9 (PG-6)
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, bill the receipt of 6 with **TCS charged by supplier %** `0.1` and **TCS amount** `1.00` → save. Reopen the draft, clear both boxes → save. Type the rate again and leave the amount blank → save.
- **Expect:** with both typed, TCS is **1.00** and Net payable 709.00: the amount the supplier printed wins over the rate. With both cleared there is no TCS line and Net payable is 708.00. With the rate alone it is 0.71 again.
- **Leaves:** a draft bill.

### TC-BUY-052 — Paying the bill clears its TCS, and cancelling reverses it

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #9 (PG-6)
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, bill the receipt of 6 with **TCS amount** `1.00`, save, **Approve** with **Paid now** ticked and Amount blank → **Approve and pay**. Then bill the receipt of 4 with TCS amount `1.00`, approve without paying, and **Cancel** that bill.
- **Expect:** Paid now pays **709.00**, the bill with its TCS, and the bill owes nothing. The cancelled bill's journal is mirrored, so its 1.00 comes back off 1430 TCS Receivable together with the payable.
- **Leaves:** a paid bill, a cancelled bill.

### TC-BUY-053 — The TCS paid to suppliers report closes each quarter

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #9 (PG-6)
- **Fixture:** `po-received`
- **Steps:** as the fixture's **Firm admin**, bill the receipt of 6 with **TCS charged by supplier %** `0.1`, approve. Reports > Financial → **TCS paid to suppliers**, the period covering today.
- **Expect:** a row for the bill: the quarter (October 2026 reads **Q3 2026-27**; April to June is Q1), Supplier, PAN, Bill, Supplier bill, Date, **Base 708.00**, **Rate % 0.1**, **TCS 0.71**. Under the quarter's bills a row named **Total Q3 2026-27** sums the base and the TCS. A draft or cancelled bill, and a bill with no TCS, is not listed.
- **Leaves:** an approved bill with TCS.

### Send the purchase order by WhatsApp (backlog 86 #3)

### TC-BUY-054 — The Send dialog offers WhatsApp, and refuses until the firm is set up

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #3 (PG-7)
- **Fixture:** `po-approved`
- **Also needs:** a firm whose messaging has never been switched on (the state a new firm is in).
- **Steps:** as the fixture's **Firm admin**, Buy > Purchase Orders → select the approved order → **Send**. Open **Channel**. Choose **WhatsApp** → **Send**. Then Settings > Firm > **Messaging**: switch messaging and the WhatsApp channel on with the firm's account, but name **no** template for *Purchase order sent to the supplier*. Send again.
- **Expect:** the dialog is titled **Send PO-…**. Channel offers **Email** and **WhatsApp** and **not SMS** (SMS is for the sales invoice alone); **Send to** says "Blank sends to the supplier's own address or WhatsApp number". With messaging off: "Messaging is off for this firm. Switch it on under Settings > Messaging first." With it on and no template named: "Name the WhatsApp template for 'Purchase order sent to the supplier' under Settings > Messaging first; WhatsApp sends only registered templates." Each refusal stays in the dialog.
- **Leaves:** messaging switched on, if the last step was taken.

### TC-BUY-055 — A purchase order goes to the supplier's mobile and is marked sent

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #3 (PG-7)
- **Fixture:** `po-approved`
- **Also needs:** messaging and the WhatsApp channel switched on with the firm's own WhatsApp Business account (`docs/MESSAGING_SETUP_GUIDE.md`), and a registered template named for *Purchase order sent to the supplier*; the supplier `<SUFFIX>-V` with a mobile number; a second supplier with **no** mobile, no phone and no contact number, with an approved order. Mark the case Blocked if the firm has no WhatsApp account.
- **Steps:** as the fixture's **Firm admin**, select the fixture's approved order → **Send** → **Channel** *WhatsApp*, **Send to** blank → **Send**. Open the order's **History**. Then Send the second supplier's order the same way; then again with a number typed in **Send to**.
- **Expect:** "Queued to send." The message goes to the supplier's own mobile (else its phone, else its primary contact's number). The order's history gains "Sent to the supplier by whatsapp." WhatsApp carries the registered template only; the order's PDF is not attached, as with the sales invoice. The supplier with no number is refused: "Cannot send: the supplier has no mobile number. Enter a number." With a number typed the message is queued to that number.
- **Leaves:** queued messages.

### Requests for quotation and quote comparison (backlog 86 #1)

### TC-BUY-056 — An RFQ to two suppliers, their quotes, and the comparison

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #1 (PG-8)
- **Fixture:** `buy-ready`
- **Also needs:** a second active supplier.
- **Steps:** as the fixture's **Firm admin**, Buy > All Buy screens > Documents > **Requests for quotation** → New (**New request for quotation**): **Add a supplier** twice (`<SUFFIX>-V` and the second), **Add line**: `<SUFFIX>-B`, **Quantity** `10` → **Save**. Select it → **Send**. **Enter quotes**: for `<SUFFIX>-V` **Rate** `100`, **Discount %** `5`, **Lead time (days)** `7` → **Save quote**; for the second supplier Rate `96`, Discount % blank, Lead time `3` → Save quote. **Compare**.
- **Expect:** the RFQ takes a number from its own `RFQ` series and reads **Draft**, then **Sent**. The comparison (**Compare quotes for RFQ-…**) shows both suppliers on the line by rate after discount and **before tax**: `<SUFFIX>-V` **95.00** marked **Lowest**, the second supplier 96.00. Before any quote is entered Compare reads "No supplier has quoted yet. Enter quotes first."
- **Leaves:** a sent RFQ with two quotes.

### TC-BUY-057 — Choosing a quote that is not the lowest needs a reason; orders are raised per supplier

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #1 (PG-8)
- **Fixture:** `buy-ready`
- **Also needs:** a sent RFQ with two quotes as TC-BUY-056 leaves it (build it first if running this case alone).
- **Steps:** as the fixture's **Firm admin**, select the RFQ → **Compare**. Choose the second supplier's quote (96.00). In the dialog **Not the lowest rate** type a reason → **Choose it**. **Save selections**. **Raise orders** → in **Raise purchase orders** confirm. **Open purchase orders**. Reopen the RFQ and try **Enter quotes**.
- **Expect:** the dialog says one purchase order is raised to each supplier chosen. One **draft** purchase order is raised to the second supplier for 10 of `<SUFFIX>-B` at **96.00**, with the RFQ's number as its reference. The RFQ reads **Closed**. A closed RFQ takes no more quotes: "A closed RFQ takes no quotations; quotes are entered while it is sent." **(HTTP)** choosing the dearer quote with no reason is refused: "Line 1: say why … is chosen over the lowest quote."
- **Leaves:** a closed RFQ, a draft purchase order.

### TC-BUY-058 — An RFQ from an approved requisition; send and cancel refusals

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #1 (PG-8)
- **Fixture:** `buy-ready`
- **Also needs:** an **approved** purchase requisition with one line naming `<SUFFIX>-V` (Buy > All Buy screens > Documents > Requisitions → New, Submit, Approve), and a second requisition still in draft.
- **Steps:** as the fixture's **Firm admin**, on the approved requisition press **Create RFQ**. Press it again. Look for it on the draft requisition. In Requests for quotation → New with a line but **no** supplier → Save → **Send**. Select a draft RFQ → **Cancel** → leave the reason empty, then give one.
- **Expect:** the first press starts a **draft** RFQ with the requisition's lines and, as suppliers, those its lines name plus each product's preferred supplier. The second is refused: "RFQ … was already started from requisition …." Create RFQ cannot be pressed on a draft requisition (the server says "An RFQ is started only from an approved requisition."). Sending with no supplier: "Invite at least one supplier before sending." Cancelling needs a reason (the dialog **Cancel RFQ-…** says "The reason stays on the request."); afterwards the RFQ reads **Cancelled**. When orders are raised from an RFQ that came from a requisition, the requisition becomes ORDERED.
- **Leaves:** a draft RFQ, a cancelled RFQ.

### TC-BUY-059 — Who may raise orders from an RFQ

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #1 (PG-8)
- **Fixture:** `buy-ready`
- **Also needs:** a user hired with the *Read Only* job template and one hired with *Purchasing*; a sent RFQ with a quote chosen.
- **Steps:** as the **Read Only** user open Buy > All Buy screens > Documents > Requests for quotation. As the **Purchasing** user open the RFQ and **Raise orders**. As a user hired with *Warehouse* look for the screen.
- **Expect:** Read Only (RFQ_VIEW) sees the list and the comparison but none of New, Send, Enter quotes, Save selections or Raise orders. Purchasing (RFQ_MANAGE and PURCHASE_CREATE) raises the orders. The Warehouse job holds neither RFQ code and is not offered the screen.
- **Leaves:** a closed RFQ, draft orders.

### Rate contracts and blanket orders (backlog 86 #2)

### TC-BUY-060 — A rate contract prices the order line

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #2 (PG-9)
- **Fixture:** `buy-ready`
- **Also needs:** the product `<SUFFIX>-B` not already on an active rate contract with `<SUFFIX>-V` (close or cancel one left by an earlier run).
- **Steps:** as the fixture's **Firm admin**, Buy > All Buy screens > Documents > **Rate contracts** → New (**New rate contract**): **Supplier** `<SUFFIX>-V`, **Valid from** today, **Valid to** a month on, **Add line**: `<SUFFIX>-B`, **Rate** `90`, **Quantity** `20` → Save. Select it → **Approve**. Buy > Purchase Orders → New for `<SUFFIX>-V`: add `<SUFFIX>-B`, quantity `15`, the price **left blank** → Save. Then a second order line with the price typed `95`.
- **Expect:** the contract takes a number from its own **`RTC`** series (RTC-2026-2027-000001; a customer receipt keeps `RC`), reads **Draft**, then **Active**. The order line is priced **90.00** and carries a mark whose tooltip reads "Rate contract: this rate comes from a supplier contract."; the contract's rate ranks above the supplier's price list and catalogue, and above the product's purchase price of 100. A price typed on the line (95) is kept as typed. Approving a contract needs PURCHASE_APPROVE: a *Purchasing* user can type one but cannot approve it.
- **Leaves:** an active contract, a draft order.

### TC-BUY-061 — Drawn and remaining are derived; over-drawing warns and never refuses

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #2 (PG-9)
- **Fixture:** `buy-ready`
- **Also needs:** an active rate contract for `<SUFFIX>-B` with `<SUFFIX>-V` at 90 for **20** units, as TC-BUY-060 builds, with nothing drawn yet.
- **Steps:** as the fixture's **Firm admin**, raise an order for **15** at the contract rate → Submit → Approve. Open the contract and its **Releases**. Raise a second order for **10**; read the banner on the draft; Submit → Approve. Open the contract again. **Cancel** the first order and open the contract once more.
- **Expect:** after the first approval the contract line shows drawn **15**, remaining **5**; Releases (**Releases against RTC-…**) lists the order line as "PO-… · line 1" with "15 @ 90". A draft order does not count as drawn. The second order shows a banner on the draft and after approval: "Over rate contract: RTC-… …: 25 drawn of 20 contracted." -- and it still approves. The contract then reads drawn 25, remaining **0** (never below zero). Cancelling the first order gives its 15 back: drawn 10, remaining 10, with nothing to reverse.
- **Leaves:** a contract, one approved and one cancelled order.

### TC-BUY-062 — Overlap, expiry, closing and cancelling a contract

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #2 (PG-9)
- **Fixture:** `buy-ready`
- **Also needs:** an active rate contract for `<SUFFIX>-B` with `<SUFFIX>-V` covering today.
- **Steps:** as the fixture's **Firm admin**: (1) type a second contract for the same supplier and product over overlapping dates → Save → **Approve**. (2) Type a contract whose **Valid to** was yesterday → Save → Approve. (3) Try to edit the active contract. (4) **Close** the active contract, then raise an order line with a blank price. (5) On a draft contract press **Delete**; on another press **Cancel** with an empty reason, then with one.
- **Expect:** (1) refused, naming the other contract: "Another active rate contract with this supplier covers the same product for an overlapping period: …". (2) refused: "RTC-… ended on …; change its period before approving it." (a contract raised before 2026-10-05 keeps the `RC-` number it was given) An active contract whose last day has passed reads **Expired** in the list and prices nothing. (3) refused: "Only a draft rate contract can be changed." (4) the contract reads **Closed** and the new line takes the next price in line (the supplier's price list or catalogue, else the product's 100). (5) a draft is removed outright ("A draft contract is removed outright."); Cancel needs a reason ("The reason stays on the contract."), after which the contract reads **Cancelled** and shows "Cancelled: …".
- **Leaves:** a closed contract, a cancelled contract.

### Serial numbers at receipt (backlog 86 #11)

### TC-BUY-063 — Serials typed, pasted or filled from a range on the receipt line

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #11 (PG-10)
- **Fixture:** `electronics-firm`
- **Also needs:** a supplier, and an **approved** purchase order for **3** of the serial-tracked product.
- **Steps:** as the firm's administrator, Buy > Goods Receipts → New against the order, Accepted `3`. Click the line's **Serials** cell. In **Serial numbers · …** open **Fill a range**: **Prefix** `QA-SN`, **Start** `1`, **Count** `2`, **Width** `4` → **Add range** → OK. Save the receipt → **Complete**. Reopen the Serials cell, type a third number on a line of its own → OK → save → **Complete**. Open the completed receipt, click "3 serial numbers" on the line, and click one unit. Stock > All Stock screens > Tracking > **Serial Numbers**.
- **Expect:** the cell reads **2 of 3**, and the dialog "2 of 3 entered". The range fills `QA-SN0001` and `QA-SN0002`. A draft may be short, but completing it is refused: "Line 1 (…) receives 3 serial-tracked units but 2 serial numbers are entered: enter 1 more on the goods receipt." With three it completes; three units exist, available, in the receipt's warehouse. The completed receipt shows each unit's trail (**Trail of …**) with this goods receipt first. Units are counted against accepted **plus free** goods.
- **Leaves:** three serial numbers in stock.

### TC-BUY-064 — A serial is one unit in the whole firm

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #11 (PG-10)
- **Fixture:** `electronics-firm`
- **Also needs:** a supplier; one completed receipt that brought in serial `QA-SN0001` (TC-BUY-063, or receive one unit first); two more approved orders for the serial-tracked product, one of 1 and one with **two lines** of 1 each; an approved order for a product that is **not** serial-tracked.
- **Steps:** as the firm's administrator: (1) receive the order of 1 with serial `qa-sn0001` (lower case) → save. (2) On the two-line order type the same new serial on both lines → save. (3) In the Serials dialog type one number twice. (4) **(HTTP)** send `serial_numbers` on a receipt line of the product that is not serial-tracked.
- **Expect:** (1) refused, case ignored: "Line 1 (…): serial qa-sn0001 already belongs to a unit in this firm (AVAILABLE)." (2) refused: "Serial … is entered on line 1 and on line 2 of GRN-…." (3) the dialog flags it: "Entered twice: …". (4) refused: "…: this product is not serial-tracked, so its lines take no serial numbers." -- and on the screen such a line has no Serials cell to click.
- **Leaves:** draft receipts.

### TC-BUY-065 — Cancelling the receipt, and returning named units to the supplier

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #11 (PG-10)
- **Fixture:** `electronics-firm`
- **Also needs:** a supplier and two completed receipts of the serial-tracked product from it, of 2 units each, with their serials entered; a customer.
- **Steps:** as the firm's administrator: (1) **Cancel** the first receipt. Look for its serials under Serial Numbers and receive them again on a new receipt. (2) From the second receipt sell and dispatch **one** unit to the customer, then try to **Cancel** that receipt. (3) Buy > Returns & notes > Purchase Returns → New off the second receipt: Returning `1`, click the line's **Serials** cell and name the unit still in stock → Save → Approve → Complete. (4) Cancel the completed return.
- **Expect:** (1) the cancelled receipt's units are removed and their numbers are free to be received again. (2) refused: "GRN-… cannot be cancelled: serial … has left stock since it was received (…)." (3) the return must name one unit per unit going back, each in stock and received from this supplier; after Complete the unit reads **Returned**. A serial of another product is refused: "…: serial … is not a unit of this product in this firm." (4) cancelling the completed return puts the unit back **Available**.
- **Leaves:** serial units, a cancelled return.

### Supplier free schemes on the item (backlog 86 #25, #27)

### TC-BUY-066 — A 10+2 scheme fills the free quantity on the order

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #25 (PG-11)
- **Fixture:** `buy-ready`
- **Also needs:** no other active scheme on `<SUFFIX>-B` for `<SUFFIX>-V` (switch off one left by an earlier run).
- **Steps:** as the fixture's **Firm admin**, Buy > All Buy screens > Documents > **Supplier schemes** → New (**New supplier scheme**): **Supplier** `<SUFFIX>-V`, product `<SUFFIX>-B`, **Buy quantity** `10`, **Free quantity** `2`, **Free product** blank ("Blank: the same product is given free."), Valid from today → Save. Buy > Purchase Orders → New for `<SUFFIX>-V`: `<SUFFIX>-B`, quantity `25`, price `100`, the **Free** box left blank → Save. Submit, Approve, receive in full and Complete. Stock > All Stock screens > Stock > Inventory.
- **Expect:** the scheme lists as **10+2**, *In force*. The order line's Free reads **4** (two free for each full ten: 25 buys two tens) and the side panel says "Line 1: Scheme 10+2 applied" under **Supplier schemes**. The line is still charged 25 x 100 = 2,500.00 before tax. The receipt offers 25 accepted and 4 free; after Complete **29** are on hand. The receipt's journal is Dr 1200 Inventory 2,500.00 / Cr 2300 Goods Received Not Invoiced 2,500.00: free goods add units, not value, so each of the 29 costs 86.21. The free units can go back: a purchase return of all 29 off the receipt line is accepted and prices the 25 bought; 30 is refused with "…line 1 can still send back 25 bought and 4 free." (TC-BUY-093 has the whole of it).
- **Leaves:** a scheme, 29 on hand.

### TC-BUY-067 — A typed free quantity is kept, and 0 refuses the scheme

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #25 (PG-11)
- **Fixture:** `buy-ready`
- **Also needs:** an active 10+2 scheme on `<SUFFIX>-B` for `<SUFFIX>-V`, as TC-BUY-066 builds.
- **Steps:** as the fixture's **Firm admin**, raise three draft orders for `<SUFFIX>-B` from `<SUFFIX>-V`: quantity `25` with Free typed `0`; quantity `25` with Free typed `1`; quantity `9` with Free blank. Then an order dated before the scheme's **Valid from**, quantity `25`, Free blank.
- **Expect:** a typed **0** stays 0 and no "Scheme … applied" note shows: zero refuses the scheme, blank takes it. A typed 1 stays 1. Nine units earn nothing (fewer than one full ten). The order dated before the scheme started takes no free goods: a scheme applies only inside its dates.
- **Leaves:** draft orders.

### TC-BUY-068 — A scheme that gives another product adds a gift line

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #25, #27 (PG-11)
- **Fixture:** `buy-ready`
- **Also needs:** a second product to be given free; no other active scheme on `<SUFFIX>-B` for `<SUFFIX>-V`.
- **Steps:** as the fixture's **Firm admin**, Supplier schemes → New: `<SUFFIX>-V`, product `<SUFFIX>-B`, Buy quantity `10`, Free quantity `1`, **Free product** the second product → Save. Purchase Orders → New for `<SUFFIX>-V`: `<SUFFIX>-B`, quantity `25`, price `100`. Wait for the editor to price the order. Save.
- **Expect:** the scheme lists as "10 + 1" followed by the free product's name. The editor adds **one** line for the second product with nothing ordered and **Free 2**, at no charge, and does not add it a second time when the order is priced again. That free-only line is priced live (its amount is 0) and is kept on save. The order total is the 25 x 100 and its tax alone.
- **Leaves:** a scheme, a draft order.

### TC-BUY-069 — Two schemes on one product cannot overlap; who may set them

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #25 (PG-11)
- **Fixture:** `buy-ready`
- **Also needs:** an active scheme on `<SUFFIX>-B` for `<SUFFIX>-V` running from today with no end date; a user hired with the *Read Only* job template.
- **Steps:** as the fixture's **Firm admin**: New scheme for the same supplier and product from next week → Save. New scheme with **Valid to** before **Valid from** → Save. New scheme for the same product with the supplier left as **All suppliers** → Save; raise an order from `<SUFFIX>-V`. Switch the supplier's own scheme off (**Active**) and raise another. As the **Read Only** user open Supplier schemes.
- **Expect:** the overlapping scheme is refused: "An active scheme for … on this product already runs … to …. End or switch it off first." Dates back to front: "A scheme cannot end before it starts." A scheme for all suppliers may stand beside a supplier's own, and the supplier's own wins on that supplier's orders; with it switched off (*Switched off*) the all-suppliers scheme applies. Read Only (SUPPLIER_SCHEME_VIEW) sees the list and no New, Save or Delete.
- **Leaves:** schemes.

### Imports: foreign currency, Bill of Entry, exchange difference (backlog 86 #4, #5)

### TC-BUY-070 — An order, receipt and bill in the supplier's currency post rupees at the rate

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #4, #5 (PG-12 part A; the full chain since D-BUY-39)
- **Fixture:** `buy-ready`
- **Also needs:** a supplier abroad with **Currency** `USD` on its form; a product on the **GST 0%** tax profile with nothing on hand. The buying stages stay **on**.
- **Steps:** as the fixture's **Firm admin**, Masters > Vendors → the supplier: confirm **Currency** reads USD (try `US` → Save first). Buy > Purchase Orders → New: that supplier; read **Currency**. Add the product, quantity `10`, rate `100`. Save with **Exchange rate (₹ per USD)** blank; then type `83` → save → Submit → **Approve**. Buy > Goods Receipts → New against the order, Accepted `10` → **Complete**; read Stock > All Stock screens > Stock > Inventory and Accounts > Journal Entries. Buy > Purchase Invoices → New for the receipt: read **Currency** and the note beside it; type **Exchange rate (₹ per USD)** `83` → save → **Approve**. Open the bill and Journal Entries.
- **Expect:** a two-letter currency is refused on the supplier: "The currency is a three-letter code, such as USD." The order starts in **USD**, the supplier's currency, and shows **Exchange rate (₹ per USD)**. With no rate it is not saved: "Enter the exchange rate: the rupees one USD is worth, above 0." At 83 the total is labelled **Total USD**, 1,000.00, and the note under it gives the rupee equivalent at 83 (83,000). Completing the receipt brings ten units in valued **83,000.00** (8,300 each), at the order's rate: Dr 1200 Inventory 83,000.00 / Cr 2300 Goods Received Not Invoiced 83,000.00. The bill is in **USD** and shows "TCS, TDS and Paid now are rupee matters; pay this bill from Payments in USD." in place of the TCS boxes; it reads **1,000.00 USD** with its rupee equivalent **83,000.00**. The Approve dialog says "This bill is in USD, so TDS and Paid now are not offered. Pay it from Payments, in that currency, at the rate of the day." The bill's journal: Dr 2300 Goods Received Not Invoiced 83,000.00 / Cr 2100 Trade Payables 83,000.00 -- no price variance, because the bill is at the order's rate. **(HTTP)** the server's own words for the two refusals: a currency `US` is "A currency is its three-letter ISO code, such as USD or EUR."; an order with no rate is "A purchase order in USD needs its exchange rate: the rupees one USD was worth on the purchase order's date." The order starts in USD on screen; the server saves an order that names no currency in rupees.
- **Leaves:** an approved USD order, a completed receipt and an approved USD bill owing 1,000.00 USD.

### TC-BUY-071 — Paying in the currency at another rate posts an exchange loss or gain

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #4, #5 (PG-12 part A)
- **Fixture:** `buy-ready`
- **Also needs:** two approved bills of **1,000.00 USD at 83** from a USD supplier, unpaid, each built as in TC-BUY-070.
- **Steps:** as the fixture's **Firm admin**, Buy > Payments → **Record Payment**: the supplier. Read the note under the supplier. Set **Pay in** to *USD*, **Exchange rate (₹ per USD)** `84`, **Amount (USD)** `1000`, apply `1000` to the first bill → Record payment. Then pay the second bill the same way at `82`. Open both payments' journals.
- **Expect:** before a currency is chosen the note lists the bills open in another currency ("Open in another currency: …") and says to choose the currency to pay them. In USD: "The amount and each applied figure are in USD, and the payment is applied in full to the USD bills. No TDS, deductions or advance on these." At 84 the toast adds "Exchange loss ₹1000.00." and the journal is Dr 2100 Trade Payables 83,000.00, Dr 4950 Exchange Gain/Loss 1,000.00 / Cr 1010 Bank 84,000.00. At 82 it adds "Exchange gain ₹1000.00.": Dr 2100 83,000.00 / Cr 1010 Bank 82,000.00, Cr 4950 Exchange Gain/Loss 1,000.00. Both bills owe nothing in either currency.
- **Leaves:** two paid bills.

### TC-BUY-072 — A part payment settles in proportion; reversing brings it all back

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #4, #5 (PG-12 part A)
- **Fixture:** `buy-ready`
- **Also needs:** one approved bill of **1,000.00 USD at 83**, unpaid, as in TC-BUY-070.
- **Steps:** as the fixture's **Firm admin**, Record Payment in USD at `84`: Amount `400`, applied to the bill. Open Record Payment again and read what the bill owes. Buy > Payments → **Reverse** the payment with a reason. Read the bill again.
- **Expect:** 400 USD at 84 costs 33,600.00 and clears 33,200.00 of the bill (400 x 83): Dr 2100 Trade Payables 33,200.00, Dr 4950 Exchange Gain/Loss 400.00 / Cr 1010 Bank 33,600.00. The bill then owes **600.00 USD** and **49,800.00** rupees, both shown. Reversing mirrors all three legs, and the bill owes 1,000.00 USD and 83,000.00 again.
- **Leaves:** an unpaid USD bill, a reversed payment.

### TC-BUY-073 — Rupees, TDS and an advance are refused against a foreign bill

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #4, #5 (PG-12 part A)
- **Fixture:** `buy-ready`
- **Also needs:** one approved bill of 1,000.00 USD at 83, unpaid.
- **Steps:** as the fixture's **Firm admin**: (1) Record Payment with **Pay in** left *Rupees* and look for the USD bill among the bills to apply to. (2) In USD at 84, Amount `1200`, applying 1,000 to the bill. (3) In USD with the rate blank. (4) **(HTTP)** `POST /api/v1/payments` in rupees with an allocation to the USD bill; and a USD payment with `tds_amount` 10. (5) **(HTTP)** save a USD bill with `tcs_amount` 5.
- **Expect:** (1) in rupees the USD bill is not offered: rupees pay the rupee bills. (2) refused before sending: "A payment in USD is applied in full to the supplier's USD bills: … of the … is applied." -- an advance in another currency is not carried. (3) the dialog asks for the exchange rate. (4) "Bill … is in USD. Pay it with a payment in USD at the day's rate."; and "A payment in USD takes no TDS, rounding, bank charges or discount; record it for the amount that was sent." (5) "TCS under 206C(1H) is charged by a seller in India; a bill in another currency carries none."
- **Leaves:** nothing new.

### TC-BUY-074 — A Bill of Entry lands customs duty on the stock and claims the IGST

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #4 (PG-12 part B)
- **Fixture:** `buy-ready`
- **Also needs:** one approved bill of 10 at 100 USD at 83 from a USD supplier, as in TC-BUY-070, with all ten units still on hand (83,000.00, 8,300 each).
- **Steps:** as the fixture's **Firm admin**, Buy > All Buy screens > Documents > **Bills of entry** → New (**New Bill of Entry**): **Bill of Entry number** `1234567`, the BoE date today, **Port code** `INMAA1`, **Supplier** the USD supplier; tick the bill under **Supplier bills the goods came on**; **Add item**: the product, **Quantity** `10`, **Assessable value** `85000`, **BCD %** `10`, **SWS %** blank, **IGST %** `18`, every amount box blank → **Save**. Read the worked figures. Select it → **Post**. Stock > All Stock screens > Stock > Inventory; Journal Entries; Accounts > All Accounts screens > Tax filing > GST Returns → GSTR-3B for the month.
- **Expect:** the draft works out **BCD 8,500.00**, **SWS 850.00** (10% of the BCD when no rate is typed), IGST base 94,350.00 and **IGST 16,983.00**. After Post the document reads **Posted** and shows Customs duty 9,350.00, IGST 16,983.00, **To stock 9,350.00**, To COGS 0.00, To expense 0.00. The ten units are now worth 92,350.00: the average rises from 8,300.00 to **9,235.00**. Journal: Dr 1200 Inventory 9,350.00, Dr 1310 Input IGST 16,983.00 / Cr 2800 Customs Duty Payable 26,333.00. GSTR-3B shows 16,983.00 under 4(A)(1) *Import of goods*. Customs duty has no credit; only the IGST does.
- **Leaves:** a posted Bill of Entry; stock revalued.

### TC-BUY-075 — Typed amounts, goods already sold, cancelling and the duplicate number

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #4 (PG-12 part B)
- **Fixture:** `buy-ready`
- **Also needs:** a posted Bill of Entry as TC-BUY-074 leaves it; a second approved USD bill of 10 units of a **different** product, of which **4 have been sold and dispatched**; a user hired with the *Purchasing* job template.
- **Steps:** as the fixture's **Firm admin**: (1) New Bill of Entry for the second bill: Assessable value `85000`, BCD % `10`, **BCD amount** typed `9000`, IGST % `18` → Save → Post. (2) **Cancel** the Bill of Entry of TC-BUY-074 with a reason; read the stock and GSTR-3B. (3) New Bill of Entry with the same number, port and date as an existing one → Save. (4) Try to save a Bill of Entry with no item. (5) As the **Purchasing** user type a draft and look for Post.
- **Expect:** (1) the typed 9,000.00 wins over 10%; SWS is 900.00 and the duty 9,900.00. Six of the ten units are on hand, so **To stock** is 5,940.00 and **To COGS** 3,960.00: duty on goods already sold goes to cost of goods sold. (2) the dialog (**Cancel Bill of Entry …**) says the journal is reversed and the duty comes off the stock; afterwards it reads **Cancelled**, the average is 8,300.00 again and 4(A)(1) no longer carries its IGST. (3) refused: "Bill of Entry … at … on … is already …." (4) a Bill of Entry with no item cannot be saved at all (the server refuses it as invalid), so there is never an empty one to post. (5) Purchasing (BILL_OF_ENTRY_MANAGE) saves the draft but is not offered **Post** or Cancel, which need PURCHASE_APPROVE. Customs itself is paid by a journal: Dr 2800 Customs Duty Payable / Cr 1010 Bank.
- **Leaves:** a posted and a cancelled Bill of Entry.

### TC-BUY-076 — Revaluing what is still owed in another currency at a period end

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #5 (PG-12 part A)
- **Fixture:** `buy-ready`
- **Also needs:** exactly one unpaid bill in USD in the firm, of 1,000.00 USD at 83; no revaluation yet posted for the date used.
- **Steps:** as the fixture's **Firm admin**, Accounts > Journal Entries → **Revalue foreign payables**. **As of** the last day of last month (the bill must be dated on or before it; use today if it is not), `USD: rupees per unit` `85` → **Post revaluation**. Read the result and the journal list. Post the same date again. Then pay the bill in USD at 84.
- **Expect:** the dialog says it restates what is still owed in each currency. The result reads a net exchange **loss of 2,000.00** (1,000 USD x (85 - 83)). One entry `FXREV-<date>` dated the as-of date: Dr 4950 Exchange Gain/Loss 2,000.00 / Cr 2100 Trade Payables 2,000.00; and its mirror `FXREV-<date>-REV` dated the next day. A second run for the same date is refused: "Payables in other currencies were already revalued on … (FXREV-…)." The revaluation is unrealised: the bill still reads 83,000.00, and paying it at 84 posts the whole 1,000.00 loss against its own rate. Pressing Post with no rate typed: "Type the rate of at least one currency."
- **Leaves:** a revaluation and its reversal; a paid bill.

### Fixed assets (backlog 86 #7)

### TC-BUY-077 — A machine ordered as capital goods is received without stock and billed as a fixed asset

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #7 (PG-13; the full chain since D-BUY-40)
- **Fixture:** `buy-ready`
- **Also needs:** a product for the asset (a desk) on GST 18% with nothing on hand. The buying stages stay **on**.
- **Steps:** as the fixture's **Firm admin**, Accounts > All Accounts screens > Fixed assets > **Asset classes**: confirm the five a firm starts with. Buy > Purchase Orders → New for `<SUFFIX>-V`: the desk, quantity `1`, rate `36500`; on the line tick **Capital goods** → save → Submit → **Approve**. Buy > Goods Receipts → New against the order: read the line's **Capital goods** tick; Accepted `1` → **Complete**. Read Stock > All Stock screens > Stock > Inventory and Accounts > Journal Entries. Buy > Purchase Invoices → New for the receipt: read the line's tick and try to clear it; save without choosing a class; then **Asset class (required)** *FURNITURE · Furniture and Fittings* → save → **Approve**. Accounts > All Accounts screens > Fixed assets > **Asset register**; Inventory; Journal Entries; Reports > Financial → GST purchase register.
- **Expect:** the classes are PLANT, FURNITURE, COMPUTERS, VEHICLES and OFFICE_EQUIPMENT, all *Straight line* with Residual % 5. Under the order line's tick: "A fixed asset, not stock: received without entering stock, and the bill raises the asset." The receipt line starts ticked, as ordered ("Received without entering stock; the bill raises the fixed asset."). Completing the receipt adds **nothing** to stock and posts nothing to Inventory or Goods Received Not Invoiced; the order is received all the same. On the bill the line is ticked **Capital goods (raises a fixed asset when approved)**, cannot be unticked, and says "Received as capital goods." Without a class: "Line 1 is capital goods: choose its asset class." After approval the register has one asset `FA-…`, class FURNITURE, Cost **36,500.00**, Net book value 36,500.00, *In use*, "Raised by bill PI-…". Stock is still nothing. One journal: Dr 1500 Fixed Assets 36,500.00, Dr 1320 Input CGST 3,285.00, Dr 1330 Input SGST 3,285.00 / Cr 2100 Trade Payables 43,070.00 -- no Inventory and no Goods Received Not Invoiced. The GST is claimed in full; the register row shows it again under **Capital goods tax 6,570.00**.
- **Leaves:** a received order, a fixed asset, an approved bill.

### TC-BUY-078 — Capital goods already received into stock are refused; cancelling the bill takes the asset off

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #7 (PG-13)
- **Fixture:** `po-received`
- **Also needs:** for the second part, a capital-goods bill approved as in TC-BUY-077 whose asset has **not** been depreciated.
- **Steps:** as the fixture's **Firm admin**: (1) Buy > Purchase Invoices → New for the completed receipt of 6, whose line was **not** marked capital goods; tick **Capital goods** on its line, choose a class → save → **Approve**. (2) **Cancel** the approved capital-goods bill of the second part and open the Asset register. (3) On an asset raised by a bill press **Delete**, and try to change its Cost.
- **Expect:** (1) refused: "Line 1 is capital goods, but GRN-… already took it into stock. Untick capital goods on this line; or cancel GRN-… and mark the line capital goods on the order or the receipt, so it is received without entering stock." (2) the bill is cancelled, its journal mirrored and its asset gone from the register. (3) "Asset FA-… was raised by a bill; cancelling the bill takes it off the register." and "Asset FA-… costs what its bill charged; change the bill, not the asset."
- **Leaves:** a draft bill, a cancelled bill.

### TC-BUY-079 — A depreciation run: straight line and written down value, by days

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #7 (PG-13)
- **Fixture:** `buy-ready`
- **Also needs:** no depreciation run covering October 2026 or later (cancel the latest first if one does); an asset class of its own typed under **Asset classes** → New (**New asset class**): Code `QA-WDV`, **Method** *Written down value*, **Rate %** `40`, **Residual %** `5`; two assets typed under **Asset register** → New (**New fixed asset**), both acquired and put to use on **2026-10-01** at **Cost** `36500`: one in class FURNITURE (straight line, life 10 years, residual 5%), one in `QA-WDV`.
- **Steps:** as the fixture's **Firm admin**, Accounts > All Accounts screens > Fixed assets > **Depreciation runs** → **Run depreciation**: **From** `2026-10-01`, **To** `2026-10-31` → Run depreciation. Open the run and find the two assets. Open each asset's **Schedule**. Journal Entries. Then run the same period again, and a period ending before `2026-10-31`.
- **Expect:** typing an asset by hand posts nothing. The run lists each asset charged with its days: both **31**. The furniture asset: (36,500 - 1,825) / 10 years = 3,467.50 a year, x 31/365 = **294.50**. The written-down asset: 40% of 36,500 = 14,600.00 a year, x 31/365 = **1,240.00**. One journal for the whole run, reference `DEP-…`, dated 2026-10-31: Dr 6950 Depreciation / Cr 1590 Accumulated Depreciation, 1,534.50 for these two (more where other assets were due). Each asset's Net book value falls by its charge and its schedule shows the charge, then the years projected. The same period again: "Depreciation run … already charged 2026-10-01 to 2026-10-31. Cancel it, or run a period after it." An earlier period: "Runs go forward: … charged up to 2026-10-31. Cancel it to run an earlier period."
- **Leaves:** a posted run, two assets.

### TC-BUY-080 — Disposing of an asset books a loss or a gain

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #7 (PG-13)
- **Fixture:** `buy-ready`
- **Also needs:** the two assets and the October 2026 run of TC-BUY-079 (book values 36,205.50 and 35,260.00).
- **Steps:** as the fixture's **Firm admin**, Asset register → select the furniture asset → **Dispose** (**Dispose of FA-…**): **Disposed on** `2026-10-31`, **Sale amount** `35000`, **Money came by** *Bank*, a **Reason** → Dispose. Then the written-down asset: Disposed on `2026-10-31`, Sale amount `36000`, *Cash*. Journal Entries. Then try to dispose of another depreciated asset on `2026-10-15`, and to cancel the October run.
- **Expect:** the dialog states the net book value the asset stands at. The furniture asset: Dr 1590 Accumulated Depreciation 294.50, Dr 1010 Bank 35,000.00, Dr 4960 (loss on disposal) 1,205.50 / Cr 1500 Fixed Assets 36,500.00; the register shows it **Disposed**, with **Gain / loss -1,205.50**. The written-down asset: Dr 1590 1,240.00, Dr 1000 Cash 36,000.00 / Cr 1500 36,500.00, Cr 4960 (gain) 740.00. Disposing on the last day already charged adds no further depreciation; on a later day the days since are charged first, in a run of type *Disposal*. A day before the last charge is refused: "Depreciation on FA-… is charged to 2026-10-31. Dispose of it on or after that day, or cancel the runs that charged past it." Cancelling the October run is now refused, because assets it charged have since been disposed at the book value it left.
- **Leaves:** two disposed assets.

### TC-BUY-081 — Cancelling a run, the Income-tax block schedule, and who may post

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #7 (PG-13)
- **Fixture:** `buy-ready`
- **Also needs:** a financial year April 2026 to March 2027; an asset class of its own, Code `QA-IT`, straight line, with **Income-tax rate %** `25` (a rate no other class uses); two assets typed by hand in it at Cost `40000` each, one acquired and put to use `2026-06-01`, one `2026-12-01`; a latest depreciation run that charged them and no disposal since; a user hired with the *Read Only* job template.
- **Steps:** as the fixture's **Firm admin**, Depreciation runs → select the latest run → **Cancel** with a reason (**Cancel run …**). Accounts > All Accounts screens > Fixed assets > **Income-tax block schedule**, **Financial year** 2026-27; find the 25% block. Try to **Delete** the class `QA-IT`. As the **Read Only** user open the Asset register and look for New, Dispose and Run depreciation. **(HTTP)** as a user holding FIXED_ASSET_MANAGE but not JOURNAL_POST: `POST /api/v1/fixed-assets/depreciation-runs`.
- **Expect:** the cancelled run reads **Cancelled** with its reason, its journal is reversed (`DEP-…-REV`) and the period can be run again. The 25% block for 2026-27 shows Opening WDV 0.00, **Additions (full) 40,000.00** (used 180 days or more in the year), **Additions (half) 40,000.00** (used less than 180 days), Depreciation **15,000.00** (10,000.00 at 25% plus 5,000.00 at half the rate) and Closing WDV **65,000.00**. The schedule posts nothing. Deleting the class is refused: "Asset class QA-IT has assets on the register. Move them to another class, or mark this one inactive." Read Only (FIXED_ASSET_VIEW) reads the four screens and is offered nothing that changes them. The HTTP call is refused with 403: "This posts a journal, which needs JOURNAL_POST as well."
- **Leaves:** a cancelled run, two assets.

### Batch-wise PTR and PTS (backlog 86 #22)

### TC-BUY-082 — PTR and PTS captured on the receipt line reach the batch

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #22 (PG-14)
- **Fixture:** `pharma-firm`
- **Also needs:** a supplier, and an approved purchase order for **20** of the batch-tracked product at 60.
- **Steps:** as the firm's administrator, Buy > Goods Receipts → New against the order, Accepted `20`. On the line type a new batch number `QA-PTR-1`, its expiry, **MRP** `120`, **PTR per unit (retailer)** `90`, **PTS per unit (stockist)** `80` → save → **Complete**. Stock > Batches: read the batch's row and open it. Then receive a second order into the **same** batch with PTR `92` and PTS blank → Complete. Settings > Platform > System > Audit Logs.
- **Expect:** the batch list shows columns **PTR** and **PTS**; the new batch reads MRP 120, PTR **90**, PTS **80**. After the second receipt PTR reads **92** and PTS is still 80: a rate the receipt states replaces the batch's, a blank never clears it. The change is audited as `batch.rates_updated` with the old pair.
- **Leaves:** a batch with trade rates.

### TC-BUY-083 — A trade rate needs a batch and may not exceed the MRP

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #22 (PG-14)
- **Fixture:** `pharma-firm`
- **Also needs:** a supplier and an approved purchase order for the batch-tracked product.
- **Steps:** as the firm's administrator, on a new goods receipt line type MRP `100` and PTR `120` → save. Correct PTR to `90`. **(HTTP)** send a receipt line with `ptr` 90 and no `batch_number`. Stock > Batches → edit a batch: type PTS above its MRP → Save.
- **Expect:** the screen refuses a rate above the MRP before sending; the server's own words are "PTR 120.00 cannot exceed the MRP 100.00." The line without a batch: "Line 1: PTR and PTS are kept on the batch, so the line needs a batch number." The batch editor's PTR ("Price to retailer, per stock unit.") and PTS ("Price to stockist, per stock unit.") are held to the same cap.
- **Leaves:** a draft receipt.

### TC-BUY-084 — A retailer is charged PTR and a stockist PTS from the batch

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #22 (PG-14)
- **Fixture:** `pharma-firm`
- **Also needs:** a batch in stock with MRP 120, PTR 90 and PTS 80, as TC-BUY-082 builds, of a product whose selling price is **100** and which is on no price list; four customers, their **Trade class** set to *Retailer*, *Stockist*, *Other* and *Not set*.
- **Steps:** as the firm's administrator, Masters > Customers → open one and read **Trade class** ("Picks PTR or PTS when a sales price is left blank"). Sell > Sales Orders → New for the retailer: add the product, choose the batch under **Batch** on the line, leave the price blank → save. The same for the stockist, the *Other* customer and the *Not set* customer. Then for the retailer again with the price typed `95`, and once more with no batch chosen.
- **Expect:** Retailer: **90.00**. Stockist: **80.00**. Other and Not set: **100.00**, the product's own price. A typed 95 stays 95. With no batch chosen the retailer is charged 100.00: the rates live on the batch. An agreed price list for the customer would rank above the batch's rate, and the batch's rate above the customer's price level. The price box is never prefilled on screen; the rate appears when the order is priced. On a delivery note the batch picker shows "PTR 90.00" and "PTS 80.00" beside the MRP.
- **Leaves:** draft sales orders.

### TC-BUY-085 — A firm without the feature is shown none of it

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #22 (PG-14)
- **Fixture:** `electronics-firm`
- **Also needs:** a supplier and an approved purchase order.
- **Steps:** as the firm's administrator, open a new goods receipt line, Stock > Batches, and a customer's form. **(HTTP)** send a goods receipt line with `ptr` 90 in this firm.
- **Expect:** the Electronics profile does not carry *batch-wise PTR / PTS* (Pharmacy, Food and Wholesale do), so the receipt line has no PTR or PTS box, the batch list no PTR or PTS column and the customer form no **Trade class**. The HTTP write is refused by the feature gate and nothing else about the receipt is affected: a line that sends neither field saves as before.
- **Leaves:** nothing.

### After the fixes of 2026-10-05 (D-BUY-35, D-BUY-39, D-BUY-40)

### TC-BUY-086 — A bill typed alone in the supplier's currency

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #4, #5 (PG-12 part A), the bill typed with no order
- **Fixture:** `buy-ready`
- **Also needs:** **Buying stages** with **Purchase order** off (see the note at the head of these cases); a supplier abroad with **Currency** `USD` on its form; a product on the **GST 0%** tax profile with nothing on hand.
- **Steps:** as the fixture's **Firm admin**, Buy > Purchase Invoices → New: that supplier; add the product, quantity `10`, rate `100`. Read **Currency** and the note beside it. Save with **Exchange rate (₹ per USD)** blank; then type `83` → **Save & approve**. Open the bill, Stock > All Stock screens > Stock > Inventory, and Accounts > Journal Entries. Switch the buying stages back on.
- **Expect:** the bill starts in **USD** and shows "TCS, TDS and Paid now are rupee matters; pay this bill from Payments in USD." in place of the TCS boxes. With no rate it is not saved: "Enter the exchange rate: the rupees one USD was worth on the supplier's invoice date." (the server's own words for the same refusal: "A bill in USD needs its exchange rate: the rupees one USD was worth on the bill's date."). At 83 the bill reads **1,000.00 USD** with its rupee equivalent **83,000.00**. The order and the receipt the bill raises are at the bill's rate, so ten units arrive valued 83,000.00 (8,300 each). Journals: Dr 1200 Inventory 83,000.00 / Cr 2300 Goods Received Not Invoiced 83,000.00, then Dr 2300 83,000.00 / Cr 2100 Trade Payables 83,000.00 -- no price variance.
- **Leaves:** an approved USD bill owing 1,000.00 USD; the buying stages as they were.

### TC-BUY-087 — A bill at another rate posts only the difference; another currency, a missing rate and a late change are refused

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #4, #5 (PG-12 part A; D-BUY-39)
- **Fixture:** `buy-ready`
- **Also needs:** a USD supplier and a GST 0% product as in TC-BUY-070; **two** orders of 10 at 100 **USD at 83** from it, approved, received and completed (stock 83,000.00 each), neither billed; one order of 10 at 100 from `<SUFFIX>-V` in **rupees**, approved, received and completed, not billed.
- **Steps:** as the fixture's **Firm admin**: (1) bill the first USD receipt with **Exchange rate (₹ per USD)** `84.50` → save → **Approve**; read its journal. (2) Bill the second USD receipt, change **Currency** to `INR` → save. (3) **(HTTP)** `POST /api/v1/purchase-invoices` billing the **rupee** order's receipt with `currency_code` `USD` and `exchange_rate` `83`. (4) **(HTTP)** `POST /api/v1/purchase-orders` with `currency_code` `USD` and no `exchange_rate`. (5) **(HTTP)** `POST /api/v1/purchase-orders/{order_id}/amend` on the first USD order with `exchange_rate` `85` and a reason. (6) **(HTTP)** `POST /api/v1/purchase-invoices` billing the second USD receipt with **no** `currency_code` and no `exchange_rate`.
- **Expect:** (1) the bill is 1,000.00 USD, 84,500.00 in rupees: Dr 2300 Goods Received Not Invoiced 83,000.00, Dr Purchase Price Variance 1,500.00 / Cr 2100 Trade Payables 84,500.00 -- only the rate difference is variance. (2) refused: "Purchase order PO-… is in USD, and its goods were received at that value, so its bill is in USD too. This bill is in rupees: bill it in USD, or raise the order in the supplier's currency before receiving the goods." (3) refused the other way round: "Purchase order PO-… is in rupees, and its goods were received at that value, so its bill is in rupees too. This bill is in USD: bill it in rupees, or raise the order in the supplier's currency before receiving the goods." (4) refused where the order is typed: "A purchase order in USD needs its exchange rate: the rupees one USD was worth on the purchase order's date." (5) refused: "GRN-… has already valued this order's goods at its currency and rate, so neither can change. A different rate on the supplier's bill is typed on the bill." (6) saved in **USD at 83**: a bill that names no currency takes its order's currency and rate, ahead of the supplier's own.
- **Leaves:** an approved USD bill with a price variance; a draft USD bill.

### TC-BUY-088 — A capital-goods line on a bill typed alone

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #7 (PG-13), the bill typed with no order
- **Fixture:** `buy-ready`
- **Also needs:** **Buying stages** with **Purchase order** off (see the note at the head of these cases); a product for the asset (a desk) on GST 18% with nothing on hand.
- **Steps:** as the fixture's **Firm admin**, Buy > Purchase Invoices → New for `<SUFFIX>-V`, **Entered on** `2026-10-01`: the desk, quantity `1`, rate `36500`. On the line tick **Capital goods (raises a fixed asset when approved)**; save without choosing a class; then **Asset class (required)** *FURNITURE · Furniture and Fittings* → **Save & approve**. Accounts > All Accounts screens > Fixed assets > **Asset register**; Stock > All Stock screens > Stock > Inventory; Journal Entries. Switch the buying stages back on.
- **Expect:** without a class: "Line 1 is capital goods: choose its asset class." After approval the register has one asset `FA-…`, class FURNITURE, Cost **36,500.00**, Net book value 36,500.00, *In use*, "Raised by bill PI-…". **Nothing** is added to stock. One journal: Dr 1500 Fixed Assets 36,500.00, Dr 1320 Input CGST 3,285.00, Dr 1330 Input SGST 3,285.00 / Cr 2100 Trade Payables 43,070.00 -- no Inventory and no Goods Received Not Invoiced.
- **Leaves:** a fixed asset, an approved bill; the buying stages as they were.

### TC-BUY-089 — A bill in another currency is in rupees in the GST purchase register and the HSN summary

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #17 (PG-1; D-BUY-35)
- **Fixture:** `buy-ready`
- **Also needs:** one approved bill of 10 at 100 **USD at 83** dated this month, built as in TC-BUY-070, for a product with an HSN code that no other bill of the period carries.
- **Steps:** as the fixture's **Firm admin**, Reports > Financial → **GST purchase register**, the period covering today; find the bill. Then **HSN summary of purchases** for the same period.
- **Expect:** the bill's row reads Taxable **83,000.00** and Bill total **83,000.00**, in rupees at the bill's own rate -- what its journal posted -- and not 1,000.00. The tax heads are 0.00 for this GST 0% product; on a taxed import each head is likewise its figure multiplied by the bill's rate. The HSN summary's row for the product reads Quantity 10 and Taxable **83,000.00**. The purchase invoice register, purchase analysis and GSTR-3B's input side read the bill the same way. A debit note or a purchase return against such a bill is TC-BUY-091 and 092; GSTR-2B matching, rule 37 and rule 42 read it in rupees too (D-CMP-23).
- **Leaves:** nothing beyond what it needed.

### TC-BUY-090 — The receiver marks capital goods at the dock; the bill cannot bill them as stock

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #7 (PG-13; D-BUY-40)
- **Fixture:** `buy-ready`
- **Also needs:** a product for the asset (a desk) on GST 18% with nothing on hand; **two** approved orders for 1 at 36,500 from `<SUFFIX>-V`, the line **not** ticked Capital goods on either.
- **Steps:** as the fixture's **Firm admin**: (1) Buy > Goods Receipts → New against the first order; tick **Capital goods** on the line; Accepted `1` → **Complete**; read Inventory. (2) Buy > Purchase Invoices → New for that receipt and read the line. **(HTTP)** `POST /api/v1/purchase-invoices` billing the same receipt line with `is_capital_goods` `false`. (3) Receive the second order the same way, ticked, and complete it; then **Cancel** that receipt with a reason; read Inventory and Journal Entries.
- **Expect:** (1) an order typed without the mark is put right on the receipt: the line is received with no stock movement and nothing in Inventory or Goods Received Not Invoiced. (2) the bill line starts ticked and says "Received as capital goods."; it needs an asset class like any capital-goods line. The HTTP bill is refused: "Line 1 was received as capital goods, so nothing entered stock for this bill to clear. Tick capital goods and choose its asset class." (3) the receipt reads Cancelled; nothing came in, so nothing goes out of stock and no journal is reversed.
- **Leaves:** a completed capital-goods receipt with a draft bill; a cancelled receipt.

### TC-BUY-091 — A debit note against a bill in another currency posts rupees at the bill's rate

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #4 (PG-12; D-BUY-41)
- **Fixture:** `buy-ready`
- **Also needs:** one approved, unpaid bill of 10 at 100 **USD at 83** for a GST 0% product, built as in TC-BUY-070 (owed 1,000.00 USD, 83,000.00).
- **Steps:** as the fixture's **Firm admin**, Buy > Returns & notes > Debit Notes → New against the bill; claim `100` on its line → Save → **Approve**. Accounts > Journal Entries. Buy > Record Payment for the supplier in **USD**; read what the bill offers. Then **Cancel** the debit note with a reason and read the bill again.
- **Expect:** the note reads 100.00, in the bill's currency. Its journal is in rupees at the bill's own rate: **Dr 2100 Accounts Payable 8,300.00**, with the goods leg credited 8,300.00 -- not 100.00. The bill owes **900.00 USD** and **74,700.00**; Record Payment offers 900.00 USD and refuses more. Payables by Month and the supplier's statement read 74,700.00, and the payables report's books check reads no difference. Cancelling the note reverses the journal and the bill owes 1,000.00 USD and 83,000.00 again.
- **Leaves:** an approved USD bill owing in full and a cancelled debit note.

### TC-BUY-092 — A purchase return against a bill in another currency; capital goods cannot go back

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 86 #4, #7 (PG-12, PG-13; D-BUY-41)
- **Fixture:** `buy-ready`
- **Also needs:** one approved, unpaid bill of 10 at 100 **USD at 83** for a GST 0% stocked product (as TC-BUY-091); the capital-goods receipt and its approved bill of TC-BUY-090's first order.
- **Steps:** as the fixture's **Firm admin**: (1) Buy > Returns & notes > Purchase Returns → New against the USD bill, `2` of its line → Save → Approve → **Complete**; open the return; Accounts > Journal Entries; Inventory. (2) Buy > Record Payment in USD for `800` at `83`. (3) New purchase return against the capital-goods bill, `1` of its line → Save.
- **Expect:** (1) the return reads Currency **USD** at **83**, taken from its bill whatever was typed, and 200.00. Its journal is **Dr 2100 Accounts Payable 16,600.00 / Cr Inventory 16,600.00**, with nothing in price variance; eight units are on hand. The bill owes **800.00 USD** and **66,400.00**. (2) the payment clears the bill with no exchange gain or loss, and Accounts Payable for the supplier reads 0.00. (3) refused: "Line 1 is capital goods: it was received as a fixed asset and never entered stock, so it cannot go back as a purchase return. Claim its value with a debit note against the supplier's bill and dispose of the asset under Fixed Assets." Nothing is saved and stock is unchanged.
- **Leaves:** a paid USD bill with a completed return against it; the capital-goods bill untouched.

---

**Returns to the supplier after the fixes of 2026-10-05 and 06.** Cases TC-BUY-093 to TC-BUY-098 were added on 2026-10-06. Their expectations were driven over HTTP against a running server; the screens have not been walked. Each stands alone. A purchase return is raised off a **goods receipt** line or off a **supplier bill** line (Buy > Returns & notes > Purchase Returns → New, then the **Goods Receipt** or the bill picker), and the rules below hold whichever it names. The return editor has one quantity box, **Returning**, and no Free box: where a step must say how many of the units are free it is marked **(HTTP)**.

### TC-BUY-093 — Free goods go back off the goods receipt that brought them in

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_3_2026-10-05.md`, `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-BUY-56 (BUYQ-16), D-BUY-63 (BUYQ-23)
- **Fixture:** `buy-ready`
- **Also needs:** two approved orders for `<SUFFIX>-B` from `<SUFFIX>-V`, each **10** at 100 with **Free** `2`, each received in full (10 accepted, 2 free) and completed: 24 on hand. Neither is billed.
- **Steps:** as the fixture's **Firm admin**: (1) Buy > Returns & notes > Purchase Returns → **New** off the **first receipt**: Returning **13** → Save Return. (2) Returning **12** → Save Return → Approve → Complete. Open the return; Inventory; Accounts > Journal Entries; Reports > Operational → **Purchase return reconciliation**. (3) **(HTTP)** `POST /api/v1/purchase-returns` off the **second receipt's** line with `current_return_quantity` 2 and `free_quantity` 2; approve and complete it. (4) Buy > Purchase Invoices → bill the second receipt (10 at 100) and **Approve**. Purchase Returns → New off that **bill**: Returning **11** → Save Return.
- **Expect:** (1) refused: "Return quantity exceeds the available source quantity: line 1 can still send back 10 bought and 2 free." (2) accepted: the gross is **1,000.00**, on the 10 bought only; the 2 free are credited nothing; total **1,180.00**. After Complete **12** are on hand and the journal is Dr 2300 Goods Received Not Invoiced 1,000.00 / Cr 1200 Inventory 1,000.00. The reconciliation counts the free goods: the row reads received **12**, returning **12**, pending 0. (3) a return of only the free units totals **0.00**: the supplier is credited nothing, stock falls by 2 (10 on hand), and the journal is Cr 1200 Inventory / Dr 5400 at the moving average. A receipt line that brought only free goods (a gift line) goes back the same way. (4) refused: off a bill line only what was billed can go back, "…line 1 can still send back 10; free goods go back off the goods receipt that brought them in."
- **Leaves:** two completed returns, an approved bill, 10 on hand.

### TC-BUY-094 — The same goods go back once, whichever document the return names

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_3_2026-10-05.md`, `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-BUY-61 (BUYQ-20)
- **Fixture:** `po-invoiced`
- **Also needs:** as *po-invoiced* (the receipt of 6 billed at 708.00, the receipt of 4 not billed). A second order of the case's own for **10** `<SUFFIX>-B` at 100, approved, received on **one** receipt and billed in full (1,180.00, approved): 20 on hand, so stock is never what refuses.
- **Steps:** as the fixture's **Firm admin**: (1) Purchase Returns → New off the fixture's **bill**: Returning **6** → Save → Approve → Complete. (2) New off the **receipt of 6** that bill billed: Returning **4** → Save. Masters > Vendors → `<SUFFIX>-V` → statement. (3) On the second order: New off its **bill**: Returning **6** → Save → Approve → Complete. (4) New off its **receipt**: Returning **5** → Save. (5) Returning **4** → Save, and leave it a draft; New off the bill: Returning **1** → Save. (6) Approve and Complete the return of 4. (7) **Cancel** the completed return of 4 with a reason; then New off the **bill**: Returning **4** → Save.
- **Expect:** (1) completes: Dr 2100 Trade Payables 708.00 / Cr 1200 Inventory 600.00 / Cr 1320 Input CGST 54.00 / Cr 1330 Input SGST 54.00. (2) refused at Save: "Return quantity exceeds the available source quantity: line 1 can still send back 0 bought and 0 free. 6 of these goods have already gone back against the supplier bill for them." The statement shows the bill of 708.00 and one return of 708.00 against it, never two. (3) completes at 708.00. (4) refused: "…line 1 can still send back 4 bought and 0 free. 6 of these goods have already gone back against the supplier bill for them." (5) 4 is accepted (472.00), and a **draft** already holds its quantity: 1 more off the bill is refused, "…can still send back 0; free goods go back off the goods receipt that brought them in. 4 of these goods have already gone back against the goods receipt that brought them in, or another bill for it." (6) completes; all 10 of the second order have gone back and its bill's 1,180.00 is credited once. (7) cancelling a return frees its quantity: the journal is mirrored, the 4 are on hand again, and 4 off the bill is then accepted (5 would be refused, "…can still send back 4…").
- **Leaves:** completed returns, one cancelled return, a draft return.

### TC-BUY-095 — After the bought units go back off the bill, the free ones go back off the receipt

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_3_2026-10-05.md`, `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-BUY-61, D-BUY-66 (the reconciliation across the two documents)
- **Fixture:** `buy-ready`
- **Also needs:** one approved order for **10** `<SUFFIX>-B` at 100 with **Free** `2` from `<SUFFIX>-V`, received in full (10 accepted, 2 free), completed, and billed (1,180.00, approved): 12 on hand.
- **Steps:** as the fixture's **Firm admin**: (1) Purchase Returns → New off the **bill**: Returning **10** → Save → Approve → Complete. (2) New off the **receipt**: Returning **3** → Save. (3) Returning **2** → Save; open the draft; Approve → Complete. (4) Reports > Operational → **Purchase return reconciliation**; the supplier's statement; Inventory.
- **Expect:** (1) completes at 1,180.00. (2) refused: "…line 1 can still send back 0 bought and 2 free. 10 of these goods have already gone back against the supplier bill for them." (3) nobody has to say the two are free: with every bought unit already returned, the 2 save as **2 free** at total **0.00**, credit the supplier nothing and take 2 out of stock. (4) the receipt-line row reads received **12**, already returned **10**, returning **2**, pending **0**; the bill-line row reads received 10, returning 10, pending 0. The statement closes 0.00 and nothing is on hand.
- **Leaves:** two completed returns, nothing on hand.

### TC-BUY-096 — A return takes its receipt line's batch, and no other

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_3_2026-10-05.md`, `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-BUY-59 (BUYQ-19), D-BUY-64 (BUYQ-24)
- **Fixture:** `pharma-firm`
- **Also needs:** a supplier, and two approved orders for the batch-tracked product `<SUFFIX>-AMX`: one received as **10** into a new batch `QA-X`, one as **5** into a new batch `QA-Y`, both completed.
- **Steps:** as the firm's administrator: (1) Purchase Returns → New off the **receipt of 10**: Returning **2**, the **Batch** box left as it opens → Save Return. Open the draft and read the batch. Approve → Complete; Stock > All Stock screens > Tracking > **Batches**. (2) **(HTTP)** `POST /api/v1/purchase-returns` for 2 off the receipt-of-10 line with `batch_number` `QA-Y`. (3) **(HTTP)** the same with `batch_number` `NO-SUCH-BATCH`. (4) **(HTTP)** `PUT` a draft return off the receipt of 10 naming `QA-Y`.
- **Expect:** (1) a line that names no batch takes its receipt line's batch: the draft reads `QA-X`, and after Complete the batch holds **8**. (2) refused at Save, not at Complete, and nothing is written: "Line 1: the goods receipt brought these goods in as batch QA-X, so batch QA-Y cannot go back against it. Return batch QA-X on this line, or raise the return off the receipt that brought QA-Y." `QA-Y` still holds 5. (3) refused in the same words, naming `NO-SUCH-BATCH`. (4) refused the same way and the draft still reads `QA-X`. The same holds off the **bill** line of that receipt. On a line whose receipt named no batch, a batch nobody received answers "Batch … was never received for this product, so no stock can be taken out of it.", and a product that may only be issued from a batch, with none named, answers "… may only be issued from a batch, so the batch number is required to return it." -- both at Save.
- **Leaves:** a completed return; batch `QA-X` at 8.

### TC-BUY-097 — A refused purchase-return import writes nothing

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_3_2026-10-05.md`, `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-BUY-62 (BUYQ-21)
- **Fixture:** `po-received`
- **Steps:** **(HTTP)** as the fixture's **Firm admin** (the screens offer no import of purchase returns): note how many returns Buy > Returns & notes > Purchase Returns lists. (1) `POST /api/v1/purchase-returns/import` with two records: the first returns **2** off the receipt of 6, the second **50** off the receipt of 4. (2) The same file with the second record returning **0**. (3) The file corrected: **2** off the receipt of 6 and **1** off the receipt of 4.
- **Expect:** (1) **422**, "Record 2 of 2: Return quantity exceeds the available source quantity: line 1 can still send back 4 bought and 0 free. Nothing was imported." The list has the same count as before: the good first record was not left behind as a draft, and no return number was spent. (2) refused the same way, naming record 2. (3) **201**: both are written as **drafts**; each then approves and completes like a return typed on screen.
- **Leaves:** two draft returns.

### TC-BUY-098 — A reverse-charge self-invoice is numbered in its own RSI series

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_3_2026-10-05.md`, `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-BUY-58 (BUYQ-18)
- **Fixture:** `ready-firm`
- **Also needs:** the firm's GST template applied; the four reverse-charge rules switched **on** (Settings > Tax > **Tax Rules**: `RCM_GTA_5_LOCAL`, `RCM_GTA_5_INTERSTATE`, `RCM_LEGAL_18_LOCAL`, `RCM_LEGAL_18_INTERSTATE` are created inactive; make them active, and inactive again afterwards); a supplier (a goods transport agency); a service product on the tax profile `RCM_GTA_5`; a stocked product and the fixture's customer for a sales invoice. Best run in a firm that has raised no self-invoice before 2026-10-05.
- **Steps:** as the fixture's **Firm admin**: (1) raise and approve a sales invoice; note its number. (2) Buy > Purchase Invoices → bill the transport service at 1,000 → Save → **Approve**; read the bill's row and its journal. (3) Raise and approve a second sales invoice. (4) Approve a second reverse-charge bill.
- **Expect:** the sales invoices read `SI-26-27-000001` and `SI-26-27-000002`. The first bill's row carries "· Self-invoice **RSI-26-27-000001**" (16 characters), with reverse charge 50.00 posted to 2270 and 2280 Reverse Charge Payable, 25.00 each; the second reads `RSI-26-27-000002`. The two lists share no number: a self-invoice never takes a number a tax invoice will carry. A supplier rate contract is likewise `RTC-2026-2027-000001`, and a customer receipt stays `RC-`.
- **Leaves:** two sales invoices, two reverse-charge bills.



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
  1. As the fixture's **Firm admin**, Stock > All Stock screens > Stock > **Inventory**, filter Product `<SUFFIX>-B` → Apply. Then **Stock Summary**.
  2. Stock > **Stock Ledger**, filter Product `<SUFFIX>-B` → Apply; open one row's detail (eye icon). Then Transaction type `GOODS_RECEIPT` → Apply.
- **Expect**
  - Step 1: one row, MAIN, Current **10**, Available 10, Reserved 0; the summary's figure for the product agrees.
  - Step 2: two `GOODS_RECEIPT` rows, +4 and +6, each naming its GRN, with the balance after each; the last equals Current. The detail dialog is titled "Ledger details". Filtering by type leaves the two. *(Known: the type list offers values the server never writes and lacks some it does — BACKLOG §31.13.)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §10.0 (the three tables and how the balance is kept) and §10.1 — what each tab reads, none of it writing a row, and a reconciliation query whose three figures must all read 10. All in `test_fixtures`.
- **Leaves:** unchanged.

### TC-STOCK-002 — Moving stock between warehouses posts no journal

- **Covers:** plan 8.3
- **Fixture:** `stock-ready` — 50 of `<SUFFIX>-P` in MAIN; an empty warehouse `<SUFFIX>-W2` under HO.
- **Steps**
  1. As the fixture's **Firm admin**, Stock > All Stock screens > Stock > Inventory → select the `<SUFFIX>-P` / MAIN row → **Transfer**: quantity **3**, **Move it to** `<SUFFIX>-W2 - Overflow <suffix>`, reference `<SUFFIX>-TRF` → **Transfer**.
  2. Refresh; Stock Ledger for the product; Accounts > Journal Entries.
  3. Transfer again with quantity **999**.
- **Expect**
  - Step 1: the dialog "Transfer stock" says how much is available; toast "Stock transferred."
  - Step 2: MAIN **47**, `<SUFFIX>-W2` **3** (a row appears), the product's total unchanged at 50. Ledger: `TRANSFER_OUT` 3 at MAIN and `TRANSFER_IN` 3 at W2, both `<SUFFIX>-TRF`. Journal: **no** entry — the footnote says why.
  - Step 3: refused in the dialog, in a red banner with the error icon: "The source holds 47.0000 available, so 999 cannot be transferred out of it." — before anything is sent.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §10.2 — two movements sharing `<SUFFIX>-TRF`, both costed at the held average, the W2 `inventories` row inserted by the inbound leg, three audit rows in one request, and **no** `journal_entries` row with either movement as `source_id`.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §10.3 (the write-off: `reference_type` is the reason, journal Dr 5500 / Cr 1200 60.00 with the movement as `source_id`, four audit rows) and §10.4 (the hold: `current_quantity_delta` −2 and `quarantine_quantity_delta` +2, so Current **and** Available fall while Quarantine rises; null cost; no journal; only `inventory.transaction.created` in the trail).
- **Leaves:** 49 in MAIN, nothing held.

### TC-STOCK-004 — A physical count posts only what was counted

- **Covers:** plan 8.4
- **Fixture:** `stock-ready`
- **Steps:** as the fixture's **Firm admin**, Stock > **Physical Count** → **+ New count**: branch HO, warehouse MAIN, today → Open. On the sheet find `<SUFFIX>-P - Fixture Product <suffix>` (code and name, never an id); type **49** in Counted (Expected is 50); leave every other line blank. **Save progress**, close, reopen from the list → **Post count** → confirm.
- **Expect:** "PC-… opened over N lines." (N is every product in MAIN — other runs' too). Difference reads `-1` while typing. The list reads "1 of N lines counted", then "N lines · posted". After posting: MAIN **49**; ledger `ADJUSTMENT` −1 referencing the count; Journal Entries shows the adjustment; the uncounted lines moved nothing. The posted sheet is read-only: "Posted. The differences are in the ledger." If stock moved between opening the sheet and posting it, the difference posted is against the stock at posting, not the Expected column (D-STK-45).
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §10.5 — `physical_counts` and one `physical_count_lines` row per stock row in MAIN; Save progress writes `counted_quantity` and no audit row; Post writes `variance_quantity` −1, an `ADJUSTMENT` with `reference_type` `PHYSICAL_COUNT` and the count number as reference, Dr 5500 / Cr 1200 60.00, and leaves every uncounted line null. A first count in a firm also creates the `PHYSICAL_COUNT` document type; there is never a lifecycle event.
- **Leaves:** 49 in MAIN; a posted count.

### TC-STOCK-005 — Dispatch draws the earliest-expiring batch first

- **Covers:** plan 8.5, 8.6
- **Fixture:** `pharma-firm` — `<SUFFIX>-AMX` in three batches of 10: `-B1` **expired 30 days ago**, `-B2` expiring in 20 days, `-B3` in 400; an approved order for **5**.
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Stock > **Batches**, search `<SUFFIX>-B`.
  2. Sell > Delivery Notes → **New** → the fixture's order for 5 → read "Expected to ship from — earliest expiry first, decided at dispatch" (in the phase 2 editor the side panel instead lists the batches, already filled earliest expiry first; see TC-SELL-019) → **Save** → **Approve** → **Dispatch**.
  3. Batches again; Stock Ledger for `<SUFFIX>-AMX`.
  4. Stock > **Expiry Monitor**.
- **Expect**
  - Step 1: three batches, 10 available each, with their expiry dates.
  - Step 2–3: status DISPATCHED; ledger `DISPATCH` −5 referencing the note. **The 5 comes from `-B2`, the earliest batch that has *not* expired**; `-B1` is skipped. Fixed 2026-09-16; see defect **D-8-1**.
  - Step 4: the six cards — Expired Today, Expire in 7 Days, Expire in 30 Days, Total Expired, Quarantine, Recalled — with `-B1` counted as expired and `-B2` inside 30 days; then the **All Batches** grid (Batch #, Product, Status, Qty, Available, Expiry Date, Warehouse).
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §10.6, in schema `fx_<suffix>_p` — the three `batches` rows and their per-batch `inventories` rows; the order's `RESERVE` sitting on `-B2` (expired stock is not reserved, judged on the order's date — D-STK-2; a store built before that fix holds `-B1`); at dispatch an `UNRESERVE` on `-B2`, a `DISPATCH` of 5 on `-B2` costed 300.00, and the note's journal Dr 5200 Cost of Goods Sold / Cr 1200 Inventory 300.00. The Expiry Monitor counts `batches` rows, not stock.
- **Leaves:** a dispatched note.

### TC-STOCK-006 — A delivery short of stock saves but will not dispatch

- **Covers:** plan 8.7
- **Fixture:** `pharma-firm` — `<SUFFIX>-SHT` has **3** on hand and an approved order for **10**.
- **Steps:** as the fixture's **Firm admin**, Sell > Delivery Notes → **New** → the order for 10 → read the preview → Save → Approve → **Dispatch**.
- **Expect:** the preview ends "Short by … — there is not enough available stock to cover this line." Saving is allowed; **Dispatch is refused** with the server's sentence, "Insufficient available stock for dispatch line."; the note stays **APPROVED** and the ledger shows no DISPATCH.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §10.7 — `<SUFFIX>-SHT`'s row reads current 3, reserved 10, **available −7** (two `RESERVE` rows, 3 and 7, from the approval); Save and Approve write no stock row; the refused dispatch writes nothing at all — no movement, no journal, no audit row, `delivery_notes.version` unmoved.
- **Leaves:** an approved, undispatched note.

### TC-STOCK-007 — A remembered filter from another firm is dropped

- **Covers:** plan 8.6a
- **Fixture:** `pharma-firm` — its platform admin can open both TEST01 and the fixture's firm.
- **Steps:** sign in as the fixture's **Platform admin**; switch into **TEST01** → Stock > All Stock screens > Stock > Inventory → filter by any product → Apply. Switch into the fixture's firm → the same tab.
- **Expect:** the tab renders; the remembered TEST01 filter is dropped (the panel reads "Filters" with none active) and choosing the firm's own warehouse works. *(A remembered id from another firm used to take the section down with "This section failed to render".)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §10.8 — not a table row: the filter is `workspace_state.inventory_management` in `%APPDATA%\.agency_platform\desktop_preferences.json` on the machine. The only server row the case writes is the firm switch's `user_preferences.updated` on the platform trail.
- **Leaves:** unchanged.

### TC-STOCK-008 — Serial numbers carry their warranty

- **Covers:** plan 8.8
- **Fixture:** `electronics-firm` — `<SUFFIX>-MIX`, 5 on hand, serials `<SUFFIX>-MIX-0001` to `-0005`.
- **Steps:** as the fixture's **Firm admin**, Stock > All Stock screens > Tracking > **Serial Numbers**; search `<SUFFIX>-MIX-`; open one row's detail; filter Status AVAILABLE.
- **Expect:** five rows, status AVAILABLE, warehouse MAIN; Warranty Start and End are empty until somebody enters them on the serial (a goods receipt carries no warranty dates; the fixture's seeded serials carry a year). The detail is titled "Serial: <SUFFIX>-MIX-0001" with warranty start and end and the warehouse. The Status filter keeps all five.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §10.9, in schema `fx_<suffix>_e` — five `serial_numbers` rows with `warranty_start`/`warranty_end`, `inventory_id` and `batch_id` null, audit action `CREATE`; the screen writes nothing. No movement ever names a serial, so a serial's status never moves on its own (D-STK-4).
- **Leaves:** unchanged.

### TC-STOCK-009 — A stock transfer as a document: dispatch, in transit, receive

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-1, A126
- **Fixture:** `stock-ready`
- **Steps:** as the fixture's **Firm admin**: Stock > **Stock Transfers** → New from MAIN to the second warehouse, 20 of the product → Save. Open Stock > Stock Summary and Accounts > Journal Entries. **Dispatch**. Look at the two warehouses' stock and the valuation. Print the **challan**. **Receive** with 18 arrived, of which 3 damaged (the other 2 never arrived). Create a second transfer and **Cancel** it after dispatch; create a third and cancel it as a draft. Try to cancel the received one. Try to dispatch more than is free.
- **Expect:** the transfer is numbered **TO-…** with a timeline. Dispatch takes the quantity off MAIN at the moving average and puts it **in transit at the destination**, still owned at that figure: no journal is posted and the firm's valuation does not move; the destination's summary shows the goods on their way. The challan is a delivery challan without values. On receipt, each line says what arrived and what of it was damaged: 15 go on the shelf, **3 arrive blocked from sale** (as on a goods receipt), and the 2 that never arrived are written off to the inventory adjustment account at the average. Cancelling a dispatched transfer brings the goods back; a draft cancels freely; a received transfer is final. Dispatching more than is free is refused. The one-step Transfer on the Inventory tab still moves stock within a building. Batches travel as themselves; serial numbers are not carried yet.
- **Leaves:** transfers and one write-off journal.

### TC-STOCK-010 — Why stock is issued: internal use, staff, display, and the firm's own reasons

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-3 (A61), STK-7 (A104)
- **Fixture:** `stock-ready`
- **Also needs:** a user holding INVENTORY_MANAGE_REASONS (the administrator).
- **Steps:** as the fixture's **Firm admin**: Stock > All Stock screens > Stock > Inventory → select the product → **Write off** 2 with reason *Internal use*; again with *Staff* and *Display*; and once with *Damage*. Accounts > Ledgers: read the expense accounts. Settings > Stock > **Adjustment Reasons**: add a reason *Festival gift* with its own expense account; deactivate another. Write off 1 with the new reason. Post an adjustment with a reason code.
- **Expect:** the three new reasons post to their own expense accounts — *Stock Used in Business*, *Staff Welfare*, *Samples and Display* — and damage, expiry and loss stay on *Inventory Adjustment*. The reasons list is the firm's own (seeded on first read); the write-off and adjustment dialogs offer exactly the firm's active reasons and post to the reason's account. Without INVENTORY_MANAGE_REASONS the screen is read-only. A reason's account must be an expense or income account: Inventory, Cash, a party or Sales is refused by name (D-STK-31). Any seeded reason, Damage included, can be switched off, after which a write-off naming it is refused.
- **Leaves:** write-off journals, a reason.

### TC-STOCK-011 — Repacking and bulk breaking

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-4, A114
- **Fixture:** `stock-ready`
- **Also needs:** a second product (the repacked pack) with a purchase price.
- **Steps:** as the fixture's **Firm admin**: Stock > All Stock screens > Movements > **Repacking** → New: consume 10 of the bulk product, produce 40 of the small pack, wastage 1 percent. Post. Read the ledger and journals. Post another with no wastage. **Cancel** one.
- **Expect:** every consume line leaves stock at the product's moving average; the value consumed less the wastage share is spread over the produce lines in proportion to what each is worth at its purchase price (by quantity where none has a price) and the pack arrives **at that cost**; wastage is written off to inventory adjustment. With no wastage the books do not move. Cancelling reverses every movement and the wastage journal.
- **Leaves:** repack documents.

### TC-STOCK-012 — A kit is assembled, sold as itself, and dispatched by assembling

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-15, A134 (D-STK-16)
- **Fixture:** `selling-firm`
- **Also needs:** a product `<SUFFIX>-KIT` of type **Bundle**; DET (100 in MAIN) and a second product as components.
- **Steps:** as the fixture's **Firm admin**: Masters > Products → the kit → **Components**: DET × 2 and the other × 1 → Save. Then **Assemble** 5 kits; check stock of components and of the kit and the kit's cost. **Disassemble** 1. Raise an order for 8 kits, approve, create the delivery note and **Dispatch**. Try a kit inside the kit.
- **Expect:** Assemble is a repack: components leave at their average and the kit arrives carrying their cost (10 DET and 5 of the other for 5 kits). Disassemble returns components. The kit is stocked and sold as itself — reservation, cost of goods sold, invoice cost and returns work as for any product. Dispatching 8 with only 4 assembled **assembles the shortfall from the components inside the dispatch's own transaction**; the dispatch gate counts the line's own reservation (D-STK-16). A kit inside a kit is not supported. Assemble and Disassemble need INVENTORY_ADJUST.
- **Leaves:** repacks, a dispatched order.

### TC-STOCK-013 — Expiry rules, shelf life and the issue rule on the product

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-5 (A113), STK-11 (A63), STK-18 (A59)
- **Fixture:** `pharma-firm`
- **Also needs:** `<SUFFIX>-AMX` in three batches as in TC-STOCK-005; a goods receipt line to type.
- **Steps:** as the fixture's **Firm admin**: Masters > Products → `<SUFFIX>-AMX` → **Stop selling N days before expiry** 20, **alert** 45, **return to supplier** 60; **Shelf life (days)** 365; **Batch issue rule** *FIFO*. Dispatch an order, then set *FEFO*, *PICK* and dispatch again. Receive a new batch giving only a manufacturing date; then one giving an expiry too. Stock > **Expiry Monitor** → *Return to supplier now*. Set the same three counts on the category and clear them on the product.
- **Expect:** a batch within the stop-sale days of expiry is passed over by the earliest-expiry pick while another batch can cover the line, and refused at dispatch where it is the only one (and in a delivery note's chosen-batch check); the picker uses the product's alert window; the monitor lists batches inside the return window (a product with no rule is never listed). A receipt line with a manufacturing date and no expiry is stored with expiry = manufacturing date + 365; a typed expiry stands; nothing is filled where the profile does not enable expiry tracking, and the batch keeps its manufacturing date and shelf life. FIFO ranks batches by when they were received; FEFO by expiry (the default); **PICK** keeps expiry order for holds but dispatch refuses by name until the line names its batches. Product, then category, then firm: the nearest set rule wins.
- **Leaves:** product settings.

### TC-STOCK-014 — Count plans, ABC classes and blind sheets

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-6, A117
- **Fixture:** `stock-ready`
- **Steps:** as the fixture's **Firm admin**: Stock > **Physical Count** → *Count plans* → New: warehouse MAIN, ABC class **A**, every 30 days, **Blind**. Draw the **sheet**. Open it: count a few lines, post. Look at the plan's next-due date. Try a posted variance above the limit if one is set.
- **Expect:** ABC class is worked out from the last year's dispatch value (the products making the first 80% are A, the next 15% B, the rest C; the list names only products that were dispatched, and one it does not name is C). The sheet counts exactly what the plan covers; a **blind** sheet hides the system quantity until it is posted. The plan's next count falls due its interval after the last sheet it drew was posted. The adjustment limits (TC-STOCK-016) apply on posting.
- **Leaves:** a plan, a count sheet.

### TC-STOCK-015 — Evidence attached to adjustments and counts

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-9, A64
- **Fixture:** `stock-ready`
- **Also needs:** a photo or PDF file; the ATTACHMENTS feature enabled for the firm's profile.
- **Steps:** as the fixture's **Firm admin**: Stock > All Stock screens > Stock > Inventory → **Adjust** (and then **Write off** and **Transfer**), pick a file in the dialog and save. Open the movement in Stock > All Stock screens > Stock > **Transactions** → **Evidence**. On a posted count sheet add another file. Delete one file.
- **Expect:** files named in the dialog are saved in the same transaction as the movement; a transfer's files sit on its outbound leg and are readable from either leg. The Evidence viewer lists name, type and caption for a movement or a count sheet; a posted sheet still takes files. Delete is soft and audited. Without the ATTACHMENTS feature the picker is not offered.
- **Leaves:** attachment references.

### TC-STOCK-016 — Large adjustments need approval

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-8, A108
- **Fixture:** `stock-ready`
- **Also needs:** a user with INVENTORY_ADJUST but a low limit (a Warehouse job), and the administrator with INVENTORY_MANAGE_SETTINGS.
- **Steps:** as the **Firm admin**: Settings > Stock > **Adjustment Limits** → Warehouse role limit **500** → Save. As the **Warehouse** user: write off stock worth 2,000 at cost. Press **Submit for approval**. As the administrator: Stock > All Stock screens > Movements > **Adjustment Approvals** → Approve; submit and **Reject** another with a reason; bulk-approve two.
- **Expect:** an adjustment or write-off worth more than the role's limit (quantity at the product's average cost) is refused when posted directly, naming the limit, and offers *Submit for approval*. A person whose own limit covers it approves the request and it posts unchanged through the same service; a rejection keeps its reason. A firm with no limits behaves as before.
- **Leaves:** requests, a posted adjustment.

### TC-STOCK-017 — Incoming and outgoing on availability

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-10, A60
- **Fixture:** `po-approved`
- **Also needs:** a sales order for the product approved for 6 and partly delivered.
- **Steps:** as the fixture's **Firm admin**: Stock > **Stock Summary** → the *Product stock* table and *Warehouse stock*. Receive part of the purchase order and look again. Open the order editor's side panel under Stock.
- **Expect:** **Incoming** is approved purchase orders less completed receipts (stock units); **Outgoing** is the approved or partly delivered sales order lines less what has left less what is still reserved; **Projected** = available + incoming - outgoing. A product with no stock row but open orders is listed in the product table. The order editor shows incoming and outgoing for the warehouse it ships from. Reorder planning uses the same incoming figure.
- **Leaves:** unchanged.

### TC-STOCK-018 — Reservations lapse, and returned goods are held until checked

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-12 (A115), STK-13 (A62)
- **Fixture:** `selling-ordered`
- **Also needs:** the sales order of 12 approved and reserved; a delivered and invoiced sale to return.
- **Steps:** as the fixture's **Firm admin**: Settings > Selling > **Sales Stages** → *Reservation lapses after* 7 days → Save; back-date the order's approval (or wait) and let the server's timer run; open the order. Press **Reserve again**. Then Settings > Stock > **Batch Rules** → *Hold returned goods for checking* on. Complete a sales return with some good, some damaged. Open Inventory. Select the quarantined row → **Release**. Cancel a second return.
- **Expect:** the order is flagged *Reservation lapsed* (not cancelled), its stock goes back to free, and it can still be dispatched from free stock; **Reserve again** holds it once more. Off by default. With the batch rule on, completing the return puts the **sellable** part in quarantine (still owned and valued), the damaged and scrapped parts as before; *Release* puts the checked goods on the shelf; cancelling the return takes it back out of quarantine.
- **Leaves:** a flagged order, quarantined stock.

### TC-STOCK-019 — Stock alerts on Home and turnover in the ageing

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-14, A116
- **Fixture:** `stock-ready`
- **Also needs:** one product below reorder level, one out of stock, one over its maximum.
- **Steps:** as the fixture's **Firm admin**: open Home and read the to-do. Reports > Operational → Stock ageing.
- **Expect:** Home lists stock lines to attend to, each counted with the worst rows: at or below reorder level, out of stock, over the maximum, batches near expiry, goods in transit, open count sheets. The ageing report carries *issued last year* and *turnover* columns. Nothing is stored; the figures change as the stock does.
- **Leaves:** unchanged.

### TC-STOCK-020 — Barcode labels, and the product's selling status

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Covers:** backlog STK-16 (A65), STK-17 (A58)
- **Fixture:** `selling-firm`
- **Also needs:** a printer or the PDF preview; a goods receipt that stocked pieces.
- **Steps:** as the fixture's **Firm admin**: Masters > Products → tick two products → **Print labels**: sheet 65-up, then 24-up, then the 50 × 25 mm roll; copies 2; used positions 1-3; price switch. On a goods receipt selection press **Print labels**. Try a cancelled receipt. Then set `<SUFFIX>-DET` to **Discontinued**; raise a quotation and an order; raise a purchase order. Reorder report. Set **Not for sale** on another product and try a quotation, an order and a purchase order.
- **Expect:** labels are Code 128 with name, barcode, MRP, our price, batch and expiry (the product code stands in for a missing barcode; an unencodable value is refused by product name); `skip` leaves used positions blank; the receipt's labels use the delivery's MRP and price, one per piece stocked, and a cancelled receipt is refused. A **Discontinued** product still sells but is refused on a purchase order by name and is not suggested by reorder planning (only active products are). **Not for sale** refuses the product on every new sales line whatever its status but it can still be bought.
- **Leaves:** product settings.


### Known defects found while writing these cases

- **D-8-1 — Dispatch drew an expired batch. Fixed 2026-09-16.** In a Pharmacy firm with batches expired 30 days ago, expiring in 20 days and in 400 days, dispatching 5 took them from the **expired** batch — its status still AVAILABLE. "Earliest expiry first" read literally does that; for a pharmacy it ships expired medicine. `InventoryService.allocate_for_dispatch` now drops expired stock from the candidates rather than ranking it first, and when that leaves the document short it says so **by name** — "10 of this product's stock is past its expiry date (X expired 2026-08-17) and cannot be dispatched: write it off or quarantine it" — because the screen still shows that stock as on hand and "short by 5" beside it explains nothing. Expiry is judged on the **document's own date**, which the delivery note passes, so rebuilding a year of history posts what it posted at the time. Three tests in `tests/unit/test_inventory_foundation.py`.

---

## Selling — quotation to cash

A firm of the run's own, priced the way WHOLE01 is. Its fixtures build it
from nothing — a minute or two — and then carry one sale to a stage:

| Fixture | Starts you with |
| --- | --- |
| `selling-firm` | customers **`<SUFFIX>-C01` Vijaya** (7.5% standing discount, Retailer segment, **no PAN**) and **`<SUFFIX>-C02` Anand** (Wholesaler, PAN, its own `NEGOTIATED` list at 9.25%); **`<SUFFIX>-DET`** at 84, GST 18 local, 100 in MAIN; the firm-wide **`STANDING`** list on DET with breaks 0 → 2%, 15 → 4.25%, 18 → 6.75%; promotions **BULK5** (7.5% on a line of 25+), **BIGORDER** (200 off a bill of 4,500+, ends the stack), **CLEARANCE** (1% on a line of 40+), **WELCOME** (2.5%, coupon only: `WELCOME10`, `WELCOME10B`); **TCS on** with a threshold of 0 (0.1%, 1% without a PAN) -- which collects nothing on a receipt dated from 1 April 2025, when section 206C(1H) was omitted; loyalty 2 points per 100 |
| `selling-ordered` | … and Vijaya's order for **12** with coupon `WELCOME10`, approved |
| `selling-delivered` | … and notes for **5** and **7**, both dispatched |
| `selling-invoiced` | … and the note for 5 **billed and approved: 483.21** |
| `selling-paid` | … and receipts of **241.60** and **341.61** (241.61 applied), and the note for 7 billed and approved (676.49) |

Sign in as the fixture's **Firm admin** unless a case says otherwise.
Quotations, Sales Orders, Delivery Notes and Sales Invoices are on the Sell
menu; Sales Returns and Credit Notes are under Sell > **Returns & notes**;
Proforma is under Sell > All Sell screens > Documents.
A resolved rate is not printed on a saved document: reopen the editor
(**Revise** on a quotation, **Edit** on a draft order) and read the helper
under the blank Discount % box — "Last priced at N% by the price list" (or a
promotion, or the customer's standing rate).

### TC-SELL-001 — The price list's first break outranks a standing discount

- **Covers:** plan 9.1
- **Fixture:** `selling-firm`
- **Steps:** Sell > Quotations → **New Quotation**: customer `<SUFFIX>-C01`; **Add line** `<SUFFIX>-DET` quantity **12**, Discount % empty (helper: "Blank takes this customer's 7.5%, or a price list where one applies.") → **Create draft** → **Revise**.
- **Expect:** "QT-… drafted, good until … Nothing is reserved by it." Under the blank box: "Last priced at **2**% by the price list." — STANDING's first break beats Vijaya's 7.5% standing rate.
- **Data (HTTP):** the quotation's line carries `discount_percent` 2.0000, `discount_source` `price_list`; grand total 1,165.65. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §11.1 in schema `fx_<suffix>_s` — nothing is written until the quotation saves; `sales_quotation_lines.discount_source` records which tier won; audits `quotation.created` and `tax.rule.simulated`.
- **Leaves:** a draft quotation.

### TC-SELL-002 — A ladder takes the highest break at or below the quantity

- **Covers:** plan 9.2
- **Fixture:** `selling-firm`
- **Steps:** a quotation for `<SUFFIX>-C01`, DET quantity **18**, Discount % empty → Create draft → Revise.
- **Expect:** "Last priced at **6.75**% by the price list" — the break at 18, not the first one above zero. Revising 12 → 18 on one quotation and saving gives the same, because a revision prices resolved lines afresh.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.1 and §11.2 — a revision updates the line in place by `line_number` and re-prices it; audit `quotation.updated`.
- **Leaves:** a draft quotation.

### TC-SELL-003 — A customer's own list replaces the firm-wide ladder

- **Covers:** plan 9.3
- **Fixture:** `selling-firm`
- **Steps:** a quotation for `<SUFFIX>-C02` (Anand), DET quantity **18** → Create draft → Revise.
- **Expect:** "Last priced at **9.25**% by the price list" — Anand's `NEGOTIATED` list replaces STANDING rather than amending it.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.1 — the customer's own list replaces the firm-wide ladder; the line reads `price_list` at 9.25.
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
- **Data (HTTP):** step 1 `discount_source` `promotion`, 7.5; step 2 `discount_source` `percent`, 0, grand total 2,973.60. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §11.1 — `promotion` at 7.5, then `percent` at 0: a typed zero is stored as a refusal, not a silence.
- **Leaves:** a draft quotation.

### TC-SELL-005 — An accepted quotation converts once

- **Covers:** plan 9.6
- **Fixture:** `selling-firm`
- **Steps:** a quotation for `<SUFFIX>-C02`, DET 12 → Create draft → **Mark as sent** → **Customer accepted** (give a reason) → **Convert to order**. Then look for Convert again.
- **Expect:** toasts "QT-… marked as sent…", "QT-… accepted. Converting it is what creates the order.", "QT-… became SO-…. The order reserves the stock when it is approved." Afterwards **no Convert to order**. **(HTTP)** `POST /api/v1/quotations/{id}/convert` with `{"order_date": "<today>"}` → **422**, "Quotation QT-… already became SO-….".
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.2 and §11.3 — lifecycle CREATED, SENT, ACCEPTED, CONVERTED on the quotation; the order arrives DRAFT with `reference_number` = the QT number, its lines carrying the tier the quotation's line was priced at (`discount_source` `price_list`, 9.25, driven 2026-10-05) and no promotion claim staged (D-SELL-9). The refused second convert writes nothing.
- **Leaves:** a converted quotation and a draft order.

### TC-SELL-006 — A coupon reaches its offer; a code nobody recognises gives nothing and refuses nothing

- **Covers:** plan 9.7, 9.8
- **Fixture:** `selling-firm`
- **Steps**
  1. Sell > Sales Orders → **New Order**: `<SUFFIX>-C01`, ships from MAIN, DET **12**, Discount % blank, **Coupon** `WELCOME10` → **Create draft** → **Edit**.
  2. Replace the coupon with `WELCOME10B` → Save order → Edit.
  3. Coupon `NOSUCHCODE` → Save order → Edit.
- **Expect**
  - Step 1: "Order drafted. Approve it to commit the stock and the credit."; "Last priced at **2.5**% by a promotion" — the coupon's offer **replaces** the list's 2%, it does not compound onto it.
  - Step 2: still **2.5** — a second code on the same offer.
  - Step 3: "Order updated."; the helper falls back to "Last priced at **2**% by the price list". The Coupon helper says "Unrecognised codes are ignored".
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.4 in schema `fx_<suffix>_s` — `sales_orders.coupon_code` keeps whatever was typed, NOSUCHCODE included; one PENDING `promotion_redemptions` row per recognised coupon, none for an unknown one; no stock, no journal.
- **Leaves:** a draft order.

### TC-SELL-007 — Approving reserves the stock and claims the offer

- **Covers:** plan 9.9
- **Fixture:** `selling-ordered`
- **Steps:** Stock > All Stock screens > Stock > Inventory, filtered to `<SUFFIX>-DET`. Then Reports > Operational → **Promotion claims**.
- **Expect:** MAIN: Current **100**, Reserved **12**, Available **88**. The claims report lists `WELCOME`, coupon `WELCOME10`, Vijaya, the order, **CLAIMED** (it was PENDING while a draft; only a claim at approval counts against a limit).
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.5 — a `RESERVE` of 12 referenced to the order number, the claim PENDING → CLAIMED under a lock, and two audit rows (`inventory.transaction.created`, `sales_order.approved`); no journal.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.7 — `is_on_hold`, `hold_reason`, `held_at` on `sales_orders` with `status` unmoved; lifecycle HELD then RELEASED; the refused note writes nothing; the reservation stays. A hold does not stop a note that already exists (D-SELL-5).
- **Leaves:** the order released.

### TC-SELL-009 — Part deliveries move the order's status

- **Covers:** plan 9.12, 9.14
- **Fixture:** `selling-ordered`
- **Steps**
  1. Sell > Delivery Notes → **New** → the order; Delivering **5**, warehouse MAIN → Save → **Approve** → **Dispatch** (an approved note moves nothing). Refresh.
  2. New again: Delivering defaults to the remaining **7** → Save, Approve, Dispatch, Refresh.
- **Expect**
  - Step 1: "Delivery note DN-… created as a draft. Dispatching it is what moves the stock."; the note **DISPATCHED**; the order **PARTIALLY_DELIVERED**; MAIN on hand **95**, Reserved **7**; ledger `DISPATCH` −5; Journal Entries has the note's cost-of-goods entry.
  - Step 2: the order **DELIVERED** (only once both notes are dispatched); ledger `DISPATCH` −7; Reserved **0**, on hand **88**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.9 and §11.10 — approving a note moves nothing; each dispatch is six audit rows in one request: `UNRESERVE` and `DISPATCH`, a journal Dr 5200 / Cr 1200 of 300.00 then 420.00, and `sales_order.delivered_status_changed` (PARTIALLY_DELIVERED, then DELIVERED), which has no lifecycle row.
- **Leaves:** a delivered order.

### TC-SELL-010 — A delivery ships the deal the order struck

- **Covers:** plan 9.13
- **Fixture:** `selling-delivered`
- **Steps:** open the note for 5 and read its line's Unit Price and discount; open the order and compare.
- **Expect:** **identical** — 84 less 2.5%, from the coupon on the order. The note does not re-read the customer's current rate or price list.
- **Data (HTTP):** the note's line: `unit_price` 84, `discount_percent` 2.5, `net_amount` 483.21. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §11.9 — the note line inherits the order line's `unit_price` and discount rate; notes carry no `discount_source`.
- **Leaves:** unchanged.

### TC-SELL-011 — Billing a note: the cap, the approval and its journal

- **Covers:** plan 9.15, 9.16
- **Fixture:** `selling-delivered`
- **Steps**
  1. Sell > Sales Invoices → **New Invoice** → **Bill this delivery note** → the note for **5** (it reads "dispatched 5 · at 84 less 2.5%"). Type **6** into Bill.
  2. Set Bill back to **5** → **Create draft** → select it → **Approve**.
  3. Accounts > Journal Entries → the invoice's `SI-…` entry → **View**. Masters > Customers → `<SUFFIX>-C01`.
- **Expect**
  - Step 1: refused before sending: "Only 5.0 left to bill." (an API client gets "Invoice quantity exceeds the available source quantity.").
  - Step 2: "Invoice created as a draft. Approve it to post the journal."; **APPROVED**.
  - Step 3: Dr **1100 Trade Receivables 483.21**, Cr **4000 Sales 409.50**, Cr **2220 Output CGST 36.86**, Cr **2230 Output SGST 36.85**. Vijaya's Outstanding **483.21**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.11 — the invoice's lines, `sales_invoice_line_taxes` (CGST and SGST 36.855 each) and three placeholder accounting events at create; at approval a receivable row `INVOICE` 483.21 and journal Dr 1100 483.21 / Cr 4000 409.50 / Cr 2220 36.86 / Cr 2230 36.85, four audit rows. The refused 6 writes nothing. The bill earns 9.66 loyalty points (`LOY-SI-…`, Dr 5700 / Cr 2600).
- **Leaves:** an approved invoice.

### TC-SELL-012 — Print settings and a printed bill

- **Covers:** plan 9.17
- **Fixture:** `selling-invoiced`
- **Steps:** select the invoice → **Print settings** icon → How many copies **2**, Copy 1 label / Copy 2 label (they prefill ORIGINAL FOR RECIPIENT / DUPLICATE FOR TRANSPORTER) → save → **Print**.
- **Expect:** the PDF carries the CGST/SGST split, an HSN column, the HSN-wise summary, "AMOUNT CHARGEABLE, IN WORDS", and two labelled copies. Saving print settings needs `SETTINGS_UPDATE`, which the firm admin holds. *(Whichever of the firm's GSTIN, the customer's GSTIN and the product's HSN are blank on your firm print empty on the copy; check the ones that are blank on yours rather than assuming all three are. The fixture's product carries no HSN, so that column is always empty here; Vijaya carries no GSTIN either way.)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.13 — one `document_print_templates` row (`document_type` SALES_INVOICE, `copy_labels` a JSON list), audit `document_print_template.created` or `.updated`; printing writes nothing.
- **Leaves:** the firm's print settings for invoices.

### TC-SELL-013 — A receipt collects no TCS from 1 April 2025; an excess with nothing else owed becomes an advance

- **Covers:** plan 9.18, 9.19
- **Fixture:** `selling-invoiced`
- **Steps**
  1. Sell > Receipts → **Record Receipt**: `<SUFFIX>-C01`, Amount **241.60**, Bank; under **Apply to invoices** type 241.60 into the invoice's **Apply** box → Record receipt. Masters > Customers → C01.
  2. Record Receipt again: Amount **341.61**, type **241.61** into Apply → Record receipt. Masters > Customers → C01.
- **Expect**
  - Step 1: no TCS is added, although the firm has TCS switched on; the server's reason is "Section 206C(1H) was omitted by the Finance Act 2025 from 1 April 2025, so nothing is collected under it on a receipt from that date." "RC-… recorded and posted to the ledger."; the row reads "Cleared SI-…". Outstanding **241.61** (483.21 − 241.60).
  - Step 2: the running line says 100.00 left over before saving. The invoice drops out of the outstanding list. Customers: Outstanding **0.00** and Advance **100.00** — the excess over everything owed. *(WHOLE01's Vijaya owed on older bills, so there the excess came off the account instead; this firm has none.)*
  - Accounts > Journal Entries: one entry per receipt, **Dr 1010 Bank / Cr 1100 Trade Receivables**, and no `TCS-RC-…` entry.
- **Data (HTTP):** `GET /api/v1/customers/{id}` → `current_outstanding`, `unapplied_advance_balance`; `GET /api/v1/tcs/preview` → `applicable: false` with the reason. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §11.14 — per receipt: `settlements`, `settlement_allocations`, a receivable row `RECEIPT` that stores the balance/advance split, and the journal `RC-…` (Dr 1010 / Cr 1100); no `tcs_collections` row. Driven 2026-10-05 on `fx_t1005j1us_s`.
- **Leaves:** two receipts.

### TC-SELL-014 — Applying an advance posts nothing; reversing a receipt puts everything back

- **Covers:** plan 9.20, 9.21
- **Fixture:** `selling-paid` — the second receipt has 100.00 unallocated; Vijaya: Outstanding 676.49, Advance 100.00.
- **Steps**
  1. Sell > Receipts → on the **341.61** receipt, **Apply to an invoice** → the invoice for 7 → Amount **95** → Apply. Then try to apply **10** more.
  2. On the **241.60** receipt → **Reverse**, give a reason → Reverse. Then Reverse it again.
- **Expect**
  - Step 1: "RC-… applied to SI-…"; the dialog says "Nothing moves in the ledger. The money arrived when the receipt was recorded." — Journal Entries has **no** new entry. Customers: Outstanding **581.49**, Advance **5.00** (the net owed is unchanged). Applying 10 more is refused: "RC-… has only 5.00 left unapplied."
  - Step 2: "RC-… reversed."; badge **Reversed**; Journal Entries shows `RC-…-REV`. Outstanding rises by **241.60** to **823.09**; Advance stays 5.00. Reversing again: "RC-… has already been reversed."
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.15 — applying writes an allocation and an `ADVANCE_APPLY` receivable row of 95.00 and no journal; reversing writes `RC-…-REV`, a `REVERSAL` receivable row, and keeps the allocations. A receipt whose advance was applied does not reverse cleanly (D-SELL-8). Driven 2026-10-05 on `fx_t1005j1us_s`.
- **Leaves:** one receipt reversed, one applied.

### TC-SELL-015 — A sales return is capped at what was dispatched

- **Covers:** plan 9.22
- **Fixture:** `selling-invoiced`
- **Steps:** Sell > Returns & notes > Sales Returns → **New Return** → Returned against the invoice (entries read "SI-… · date · Vijaya Stores <suffix>") → Line 1 → Taken back into MAIN → Quantity returned **9** → Create draft. Then **2** → Create draft → **Approve** → **Complete**.
- **Expect:** 9 is refused: "Only 5.0 went out on this line." (server: "Return quantity exceeds what was dispatched on the source document (5 sent, 0 already returned)."; where the line names a unit, "(5 PIECE sent, 0 PIECE already returned)"). With 2: "SR-… created as a draft…", "SR-… approved. Nothing has moved yet…", "SR-… completed: 2 back on the shelf and 193.28 credited to the customer." Ledger `SALES_RETURN` +2; Outstanding down **193.28** (2 × 84 less 2.5% plus 18%). A return against a delivery note nobody was billed for moves stock and cost only: no `SR-…` credit journal, no receivable row, `unbilled_quantity` on the line, and the note's left-to-bill reduced. On a part-billed note the unbilled part is taken first (4 delivered, 3 billed, 2 back: 1 credited). TC-SELL-094 walks both.
- **Reports:** Reports > Operational → **Sales return register** values a return at what was credited: it shows the credited amount (`credited_amount`) and the unbilled quantity (`unbilled_quantity`) beside the document total, and by customer, by product and the summary add up the credited figure. The summary's **total return value** counts only completed returns and equals the register's credited total; a draft or approved return adds its stated total to **pending return value** and nothing to the total, and completing it moves what it credited across (nothing, for a return never billed). The summary counts no header charge or rounding of a return that credited nothing. A return raised against a delivery note of a billed supply names that bill under *Against invoice* in the GST sales register and in GSTR-1 CDNR.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.16 — the refused 9 writes nothing; Complete writes a `SALES_RETURN` +2 movement, journals `SR-…` (Dr 4100 163.80 / Dr 2220 14.74 / Dr 2230 14.74 / Cr 1100 193.28) and `SR-…-COST` (Dr 1200 / Cr 5200 120.00), a receivable row `CREDIT_NOTE`, seven audit rows.
- **Loyalty (D-SELL-47, 2026-10-05):** the return takes back the points the bill earned on the value returned — about **3.87** of the bill's 9.66 (193.28 of 483.21) — a `REVERSED` row in `loyalty_entries` naming the return, with a journal Dr 2600 / Cr 5700. Cancelling the return gives them back.
- **Leaves:** a completed return.

### TC-SELL-016 — A credit note reverses the tax the line was charged, and no more than the line

- **Covers:** plan 9.23, 9.24
- **Fixture:** `selling-invoiced`
- **Steps**
  1. Sell > Returns & notes > Credit Notes → **Raise credit note**: the invoice, Line 1, Reason Rate difference, **Credit, before tax** **50** → Raise → row's **Approve**.
  2. Raise again on the same line with **400**.
- **Expect**
  - Step 1: the row reads `59.00 (tax 9.00)` — 18%, the rate that line was charged. "CN-… — approved. The credit and the tax are on the ledger." Outstanding down **59**.
  - Step 2: refused: "A credit note cannot credit more than the line was charged: 409.50 charged, 50.00 already credited."
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.17 — `credit_note_lines.tax_rate_percent` 18.0000; approval posts Dr 4100 50.00 / Dr 2220 4.50 / Dr 2230 4.50 / Cr 1100 59.00 and a receivable row `CREDIT_NOTE` with no reference type, and writes no lifecycle event (D-SELL-23). The refused 400 writes nothing.
- **Loyalty (D-SELL-47, 2026-10-05):** approving takes back about **1.18** of the bill's 9.66 points (59.00 of 483.21); cancelling the note gives them back.
- **Leaves:** an approved credit note.

### TC-SELL-017 — A proforma posts nothing and does not follow the order afterwards

- **Covers:** plan 9.25, 9.26
- **Fixture:** `selling-ordered`
- **Steps**
  1. Sell > All Sell screens > Documents > Proforma → **New**. Press **Raise proforma** with no order chosen. Then choose the fixture's order ("SO-… — Vijaya Stores <suffix> — total") → Raise → **Issue** → **Print**. Journal Entries; Masters > Customers → C01.
  2. Sell > Sales Orders → the order → **Cancel**. Proforma → Refresh → reopen the proforma.
- **Expect**
  - Step 1: the order box opens empty, and Raise without an order says "Choose the sales order this proforma states." and raises nothing. With the order chosen: "PF-… raised. Issue it when the customer needs it." then "PF-… issued."; the print is titled PROFORMA INVOICE, names the order under *Against order* and says "This is not a tax invoice." (a draft's copy says DRAFT); **Send** emails it where the firm has email set up; a `PF` series number (never `PI`, which purchase invoices use); **nothing** posted; Outstanding unchanged; the pane says "Not a tax invoice — no input tax credit is available against this document."
  - Step 2: the proforma's lines and totals are unchanged — snapshotted when it was raised.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.18 and §11.8 — `proforma_invoices` and copied `proforma_invoice_lines`, lifecycle `PROFORMA.CREATED` / `PROFORMA.ISSUED`, no journal or receivable; cancelling the order writes an `UNRESERVE` dated today, claims REVERSED, and nothing on the proforma.
- **Leaves:** an issued proforma and a cancelled order.

---

### TC-SELL-018 — Why the goods go out, and dispatch before the invoice

- **Covers:** backlog 77 rows 1-3, A35
- **Fixture:** `selling-ordered`
- **Also needs:** *sell-ready*: an approved sales order for 10 of `<SUFFIX>-S` with stock.
- **Steps:** as the fixture's **Firm admin**: Settings > Tax > **GST Documents**: leave *Dispatch of a sale before its invoice* at **Warn** → Save. Sell > Delivery Notes → **New** off the order for 2, **Reason** *Sale* → Save → Approve → **Dispatch**. Repeat with **Reason** *Supply on approval*. Then set the policy to **Block** and dispatch a *Sale* note. Then on another approved *Sale* note use **Dispatch and invoice**. Then a note with **Reason** *Other* and no words. Print one challan.
- **Expect:** under Warn, Dispatch on a *Sale* note shows the GST message with **Dispatch and invoice / Dispatch anyway / Cancel**; *Dispatch anyway* dispatches and the audit trail keeps the warning. *Supply on approval* dispatches with no question. Under Block there is no *Dispatch anyway*. **Dispatch and invoice** dispatches the note and creates an **approved** invoice of it in one step ("Dispatched and invoiced as SI-…"); if the invoice is refused (e.g. price below its floor) nothing is dispatched. *Other* without words is refused ("Say why…"). The challan print shows **Reason**. *Van or route sale* dispatches freely unless **Van or route sales need the invoice** is switched on.
- **Leaves:** what the steps made.

### TC-SELL-019 — Choosing batches on a delivery note

*Added 2026-10-02 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (the split, the print and the refusals; not the expiry parts (the fixture firm has no expiry tracking)); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog 79, A38
- **Fixture:** `pharma-firm`
- **Also needs:** the product `<SUFFIX>-AMX` in three batches of 10 as in TC-STOCK-005 (one expired, one within 30 days, one later); an approved sales order for 8 of it, and a second one.
- **Steps:** Sell > Delivery Notes → **New** off the order. Look at the side panel's batch list. (a) Change nothing → Save → Approve → **Dispatch**. On a second order: (b) type 8 against the *later* batch and clear the earlier → Save → Approve → Dispatch. (c) Split 5 + 3 across the two in-date batches → dispatch → **Print** the challan. (d) Type only 6 in total → Save → Approve → Dispatch. (e) Edit a box, then **Use earliest expiry**.
- **Expect:** every batch is listed nearest expiry first with expiry, days left and *can take*; the expired one is greyed and cannot be typed into; the next one is marked near expiry; the boxes start at the earliest-expiry split. (a) ships the nearest in-date batch, as before. (b) ships the later batch, the earlier one's stock is free again, and the audit trail shows **delivery_note.fefo_skipped** with both splits. (c) the challan prints **two rows** for the line, quantities 5 and 3, values adding up to the line. (d) the panel flags that 6 of 8 are chosen, Save works, and Dispatch is refused. (e) the boxes return to the earliest-expiry split. Approving the order reserves by batch: first expiry first, or the batch a customer's minimum shelf life allows. A batch picked by hand that other orders hold in full is refused at dispatch: "Line 1: Batch … holds 0.0000 available here, and 5.0000 is chosen from it. Choose less from it, or another batch." A batch is expired **on** its expiry date, not the day after.
- **Leaves:** a dispatched note.

### TC-SELL-020 — Charging a customer more after the invoice

*Added 2026-10-02 from the code. **Server side driven in full 2026-10-05** on a `compliance-firm`, the GST returns included; results in `docs/qa/SELLING_API_CHECK_ROUND_3_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog 77 row 5, A40
- **Fixture:** `compliance-firm`
- **Also needs:** an approved invoice to a **registered** customer for 10 at 100 + 18% GST (1,180.00), nothing received on it.
- **Steps:** as a **Sales manager** (hire one if the fixture has none): Sell > Returns & notes > **Debit Notes** → **New** → pick the invoice → reason *Price increase* → 100 on its line → watch the tax → **Save**. Try **Approve**. As the **Firm admin**: approve it. Then Sell > Receipts → New for the customer. Then GST Returns → GSTR-1 and GSTR-3B for the month. Then try to cancel the **invoice**. Then record a receipt of 1,250.00 against the invoice and try to cancel the **debit note**.
- **Expect:** the preview shows tax **18.00**, total **118.00** (the invoice line's rate). The sales manager can raise but is not offered **Approve**. After approval the customer's balance is **118.00** higher, and Record Receipt lists the invoice at **1,298.00** owing, one row not two. GSTR-1 CDNR shows the note as type **D** against the invoice, taxable 100, CGST 9 + SGST 9; GSTR-3B 3.1(a) is 100 higher. Cancelling the invoice is refused naming the debit note. With 1,250.00 received, cancelling the debit note is refused ("Money received on invoice SI-… has already met 70.00 of this debit note. Reverse that receipt first, then cancel the note."); after reversing the receipt it cancels and the balance drops back. A customer debit note prints (A4, its own **Print**).
- **Leaves:** what the steps made.

### TC-SELL-021 — Rate includes GST on an order and a quotation

*Added 2026-10-02 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (the quotation and its conversion; the firm setting only prefills on the desktop); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog 64 row 4, A32
- **Fixture:** `selling-firm`
- **Steps:** as the fixture's **Firm admin**, Sell > Quotations → **New** for `<SUFFIX>-C01`. Switch **Rate includes GST** on, type a rate of **118** on a line taxed at 18%, with quantity 10 → Save. Reopen it, then **Print**. Convert it to a sales order and open the order. Then Settings > Selling > **Sales Stages** → *Rates typed on a bill include GST* on → Save, and start another new sales order.
- **Expect:** while the switch is on the Rate column is labelled as the shelf price and the totals show a taxable value of 1,000.00 with 180.00 tax, total 1,180.00. Reopening shows 118 as typed; the print shows both rates. The order opens with the switch **on** and the same typed rate, and the customer is billed what was quoted. A bill raised from the order prints only the pre-tax rate. A new order starts with the switch on only after the setting is saved; an order made by converting a quotation never reads the setting a second time.
- **Leaves:** what the steps made.

### TC-SELL-022 — Batch rules: near expiry, a reason, and the price floor

*Added 2026-10-02 (backlog 79 row 6, A2).*

- **Preconditions:** the shop from TC-SELL-019 (a batch expiring within 30 days and a later one, 10 each). The product's **minimum selling price** 150. Settings > Selling > **Price Floor**: *Block*.
- **Steps:** Settings > Stock > **Batch Rules**: note the defaults, then set *A near-expiry batch leaving* to **Need a reason** → Save. (a) A sales order for 2 at **100** → Approve. (b) A sales order for 15 at 100 → Approve. (c) A delivery note off order (a), batches untouched → Save → Approve → **Dispatch**; cancel the reason prompt; Dispatch again and give *Short-dated stock cleared*. (d) Set *FEFO skip* to **Need a reason**; a note choosing the *later* batch → Dispatch. (e) Untick *may be sold below the price floor* → repeat (a).
- **Expect:** the defaults read 30 days, Warn, Record, ticked. (a) approves although 100 is below 150; its timeline names the near-expiry batch. (b) is refused below the minimum price when the order is **approved**, not when it is saved, and the message quotes the rate after any standing discount -- 15 takes the later batch too, which is fresh stock. (c) the prompt names the line and the near-expiry batch; cancelling dispatches nothing; with the reason it dispatches and Settings > Platform > System > Audit Logs shows **delivery_note.near_expiry_dispatched** with the reason. (d) asks for a reason before dispatching; **delivery_note.fefo_skipped** keeps it. (e) is refused like (b). A batch is expired **on** its expiry date, not the day after.

### TC-SELL-023 — Choosing batches on a counter bill

*Added 2026-10-02 (backlog 79 row 2).*

- **Preconditions:** a firm with the delivery note stage **off** (Settings > Selling > Sales Stages). A batch-tracked product with two in-date batches, an earlier and a later expiry, 10 each, in the default warehouse.
- **Steps:** Sell > Sales Invoices > **+ New by product** (the counter bill): the product, quantity 4. Open the line's batches: note the pre-fill. Put 4 on the **later** batch → Save → reopen the draft and look at the batches → change to 1 earlier + 3 later → Save → **Approve**. Then a second bill of 4 with the batches untouched → Approve.
- **Expect:** the picker lists both batches with expiry and days left, the earlier one pre-filled with 4. The saved draft shows 4 on the later batch, and Stock > Batches shows the 4 reserved on it. After the change to 1 earlier + 3 later, Stock > Batches reads 1 reserved on the earlier batch and 3 on the later: a line split across batches holds each batch for what was chosen from it. Picks that do not add up to the line are held first expiry first and refused at approval ("Line 1: the batches chosen add up to 5.0000, and the line delivers 6.0000."). A counter bill that picks an expired batch is refused when it is saved: "Line 1: the batch the customer asked for, … has expired." **(HTTP)** the picks of a saved counter bill are edited either way, the line sent back by its source fields (no `product_id`) or as a product line; changing the quantity without sending the picks again clears them. After approval, stock of the earlier batch is down by 1 and the later by 3 (Stock > Batches), and Settings > Platform > System > Audit Logs shows **delivery_note.fefo_skipped**. The untouched bill draws 4 from the earlier batch, as before.

### TC-SELL-024 — A customer's minimum shelf life

*Added 2026-10-02 (backlog 79 row 6).*

- **Preconditions:** a firm whose business profile has expiry tracking. A batch-tracked product with a batch expiring in about 4 months and one in about 9 months, 10 each. A customer with **Minimum shelf life** 180 days (Masters > Customers → edit). An approved sales order of 8 for that customer.
- **Steps:** (a) Sell > Delivery Notes → New off the order, batches untouched → Save → Approve → **Dispatch**. (b) A second order and note: open the batch picker. (c) Put 8 on the 4-month batch → Save → Approve → Dispatch. (d) Settings > Stock > **Batch Rules**: *short of the customer's minimum shelf life* → **Warn** → Save, and dispatch (c) again. (e) Raise and approve an order for the same customer (it holds the 9-month batch), then an ordinary order for another customer that holds the 4-month batch; dispatch the first order's note with its batches untouched. (f) Cancel the second order and read Stock > Batches.
- **Expect:** (a) ships the **9-month** batch -- the 4-month one is passed over without anybody choosing; Stock > Batches shows the order's 8 reserved on the 9-month batch from approval. (b) the 4-month batch carries **Too short for customer** and the pre-fill is on the 9-month one. (c) Dispatch is refused with a message naming the batch and the customer's minimum; no reason prompt is offered. (d) it dispatches, and Settings > Platform > System > Audit Logs shows **delivery_note.short_shelf_life_dispatched**. (e) the first order's note still ships the 9-month batch and the other order's reservation on the 4-month batch stays. (f) cancelling or closing an order lets go of that order's own hold and no other: the 4-month batch is free again and nothing else moves.

### TC-SELL-025 — Pinning the batch a customer asked for

*Added 2026-10-02 (backlog 79 row 4).*

- **Preconditions:** a batch-tracked product with an earlier and a later in-date batch, 10 each, and one expired batch with stock.
- **Steps:** Sell > Sales Orders → New: 5 of the product, **Batch** = the later batch → Save → Approve. Stock > Batches. Sell > Delivery Notes → New off the order → look at the batch picker → Approve → Dispatch. Then an order for 12 pinning the later batch → Approve. Then an order pinning the expired batch → Approve.
- **Expect:** approval holds 5 of the **later** batch and nothing of the earlier. The note opens with 5 on the later batch, and dispatch ships it (audit trail: **delivery_note.fefo_skipped**). The order for 12 holds 10 of the later batch and leaves 2 as a back order -- the earlier batch stays free -- and Reports > Back orders lists the order with 2. Cancelling or closing an order, or cancelling a draft counter bill, lets go of that order's own hold: an order on the later batch that is cancelled frees the later batch and leaves another order's hold on the earlier batch alone. Pinning the expired batch is refused at approval naming it. A batch is expired **on** its expiry date, not the day after.

### TC-SELL-026 — A batch's own MRP

*Added 2026-10-02 (backlog 79 row 7, A41).*

- **Preconditions:** a batch-tracked product; the delivery note stage off (counter bills).
- **Steps:** Goods Receipt for the product: batch `B1`, **MRP** 120, **Selling price** 95; a second line batch `B2`, MRP 100. Complete it. Settings > Stock > Batch Rules: tick *Take a line's rate from its batch's selling price*. Counter bill: the product, 4, choose `B1` → look at the rate → Save → Approve → **Print**. Then a counter bill of 4 from `B2` at rate **110** (no tax) → Approve.
- **Expect:** the batch screen shows B1 at MRP 120 / 95 and B2 at 100. The picker lists each batch's MRP. Choosing B1 fills the rate **95** on the screen; the server does not fill a blank rate from the batch. The printed bill has an **MRP** column, 120 on the B1 row. The B2 bill at 110 is refused, quoting the rate **with tax**: on a product taxed at 18%, "charges 129.80 a unit with tax, above the MRP of 100.00 printed on the batch it ships" (110.00 only where the product carries no tax).
---

### TC-SELL-027 — Several delivery notes on one bill: customer first

*Added 2026-10-03 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (the customer's notes billed together and the branch clash; not the supplier half); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog SEL-1, A54 (D-SELL-44)
- **Fixture:** `selling-delivered`
- **Also needs:** a second customer with one dispatched, unbilled delivery note; for the clash, a third dispatched note for Vijaya that names a **different salesman** from the notes of 5 and 7 (set the salesman on the order it came from). For the supplier half, `po-received` (receipts of 4 and 6).
- **Steps:** as the fixture's **Firm admin**: Sell > **Sales Invoices** → New → bill from delivery notes. (a) Look at the first question asked. Pick Vijaya. (b) Tick the notes of 5 and 7 → create the draft. (c) Start again and also try to tick the third note. (d) Start again and pick the second customer. Then Buy > **Purchase Invoices** → New → from receipts: pick the supplier and tick the receipts of 4 and 6.
- **Expect:** (a) the editor asks for the **customer** first and lists only customers that have notes left to bill. Vijaya opens a tick list: number, date, order and the amount left to bill before tax. (b) the two notes can be ticked together and make one draft bill. (c) the third note cannot be ticked beside notes of another salesman, and says which field it clashes on (the server names the field -- "All source documents must belong to the same salesman." -- and not the note; a note that names nobody never clashes); the same holds for branch, territory or route. (d) a customer with a single note has it ticked already, without being asked. The supplier bill asks for the **supplier** first and lists that supplier's receipts; the only field a receipt can clash on is the branch.
- **Leaves:** a draft bill.

### TC-SELL-028 — An enquiry becomes a customer and a quotation

*Added 2026-10-03 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (all of it); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog SEL-10, A133
- **Fixture:** `selling-firm`
- **Also needs:** the product `<SUFFIX>-DET`; a role holding SALES_VIEW, SALES_QUOTATION_CREATE and SALES_UPDATE (the firm administrator does).
- **Steps:** as the fixture's **Firm admin**: Sell > All Sell screens > Documents > **Enquiries** → New. Type a **prospect** (name, company, phone in the form +91…, email, city) instead of picking a customer; source, salesman, expected value, expected close date, next follow-up date; one line for `<SUFFIX>-DET` × 10 and a second line with a description only. Save. (a) Try **Convert to quotation**. (b) Give the second line a product and convert again. (c) Open the new quotation and convert it to a sales order. (d) Raise a second enquiry for a prospect, add a follow-up note with a new next date, then mark it **Lost** with a reason from the list. (e) Open the **Follow-ups due** view; then Reports > Operational → **Enquiries lost**.
- **Expect:** the enquiry is numbered **ENQ-…** and opens as new. (a) conversion is refused while a line has no product. (b) a customer is created from the prospect (code from the customer series, the firm's currency) and a draft quotation with the lines; the enquiry shows the quotation and the customer. (c) once the order is made the enquiry reads **WON**. (d) the follow-up is kept with its date and the enquiry's next follow-up moves; Lost needs a reason chosen from a fixed list. (e) the due view lists enquiries whose next follow-up is today or earlier and not closed; the lost report counts the lost enquiries and totals their expected value by reason. The due view is paged like the enquiry list (**(HTTP)** `GET /api/v1/enquiries/follow-ups-due` with `page_size` above 100 is 422). There is no Home gadget and no reminder yet.
- **Leaves:** a customer, a quotation, an order, two enquiries.

### TC-SELL-029 — Counter billing with a barcode scanner and a split of tenders

*Added 2026-10-03 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (the barcode search, the split of tenders and its receipts; not the scan field or F9); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog SEL-12, A90
- **Fixture:** `selling-firm`
- **Also needs:** `<SUFFIX>-DET` given a barcode (Masters > Products → the product → barcode); a USB scanner in keyboard mode, or type the barcode and press Enter; a thermal printer or the PDF preview.
- **Steps:** as the fixture's **Firm admin**: Sell > **Sales Invoices** → New by product for Vijaya. Click the **scan field**, scan `<SUFFIX>-DET`, scan it again. Add a split of tenders: part **Cash**, the rest **UPI**; then give more cash than the balance. Press **Save & print (F9)**. Then try a tender total above the bill by editing it and saving.
- **Expect:** the first scan adds a line, the second raises its quantity by 1. The tender panel shows the balance and, for cash over the balance, the change to give back. F9 saves, approves, prints the thermal bill and opens the next blank bill. The bill shows as paid: one receipt per tender is recorded, cash into the cash book, UPI through the bank with mode UPI, each allocated to the bill. A tender total above the bill saves as a draft and is refused when the bill is **approved**: "600.00 was received against a bill of 472.00. Enter what the bill is paid with; change is handed back." Receipts appear under Sell > **Receipts**.
- **Leaves:** an approved, paid bill and its receipts.

### TC-SELL-030 — Picking list and loading sheet

*Added 2026-10-03 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (both prints); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog SEL-13, A92
- **Fixture:** `selling-delivered`
- **Steps:** as the fixture's **Firm admin**: Sell > **Delivery Notes**; tick both notes (5 and 7) → **Pick list**. Then with the same ticks → **Loading sheet**. Try the buttons with nothing ticked, and as a role without SALES_VIEW.
- **Expect:** each button gives an A4 PDF. The pick list sums the ticked notes **by product** (12 of `<SUFFIX>-DET`, free goods included, in stock units), by batch where a note chose one and "earliest expiry first" where it left the batch to dispatch. The loading sheet has one drop per note in the order the round visits the customers, with the note's value and what its bills still owe. Nothing is written: the notes are unchanged. With nothing ticked the buttons are disabled or the request is refused by name.
- **Leaves:** unchanged.

### TC-SELL-031 — Cash discount for early payment, and interest on overdue bills

*Added 2026-10-03 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (the discount, the receipt, the firm's terms and the interest on the statement); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog SEL-14, A91
- **Fixture:** `selling-invoiced`
- **Also needs:** the invoice of 483.21 nothing has been received on; an invoice that is already past its due date (back-date one, or use the due date on the bill).
- **Steps:** as the fixture's **Firm admin**: Masters > **Customers** → Vijaya → terms → cash discount **2% within 10 days**. Settings > Selling > **Credit Control** → set an overdue interest rate (say 18% a year) and a grace of 5 days → Save. Sell > **Receipts** → Record Receipt for Vijaya on the day of the invoice. Then open **Customer Statements** for a customer with an overdue bill and press **Raise interest debit note**. Then clear the customer's own discount days and look again.
- **Expect:** Record Receipt prefills the discount allowed (2% of what the bill still owes) while the bill is inside its 10 days, and not after; accepting it posts the discount as *Discount Allowed* and leaves the bill's tax alone. A customer with no days of their own takes the firm's terms; zero days refuses a discount. The statement shows the interest accrued on each overdue bill at the yearly rate (365-day year) for the days past due once the grace days have run. *Raise interest debit note* makes a **draft** customer debit note with the reason *Late payment interest*, taxed at the bill's own rates; interest is only charged when somebody raises it. A receipt, credit note or return changes the figures at once. Raising the note needs CUSTOMER_DEBIT_NOTE_MANAGE.
- **Leaves:** a receipt with a discount, a draft debit note.

### TC-SELL-032 — A new outlet waits for office approval

*Added 2026-10-03 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (the pending customer, the refusal at billing, single and bulk approval; not the field user's own sign-in); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog SEL-15, A93
- **Fixture:** `selling-firm`
- **Also needs:** a **Field Sales** user (SALES_EXECUTIVE) beside the firm administrator.
- **Steps:** as the **Firm admin**: Settings > Selling > **Sales Stages** → switch on *New outlets need approval* → Save. As the **Field Sales** user: Masters > **Customers** → New, save. Try to raise a quotation, an order, and a bill for it; try to change its status. Sign in as the **Firm admin**: filter the list by **Pending approval**, tick the new customer → **Approve**; also tick two more pending ones → **Approve** (bulk). Switch the setting off and create another customer as the field user.
- **Expect:** the field user's new customer is saved with status **Pending approval** (badge in the list; a filter finds it) and a bill for it is refused when it is raised, naming the reason ("… is a new outlet waiting for approval, so it cannot be billed yet. Its orders are kept; approve the customer to bill them."); quotations and orders for it are still accepted and kept; the field user cannot move it on. The administrator's Approve (single and bulk) activates it, after which it can be billed. With the setting off a non-approver's new customer starts active. Approving needs CUSTOMER_APPROVE. The Field Sales user's new customer carries no money terms: on the form the **Credit limit**, **Default discount %**, **Opening balance**, **Payment terms (days)**, **Cash discount (days)** and **Cash discount %** boxes are locked ("Set by somebody with the manage customer settings permission."), and **(HTTP)** a credit limit, an opening balance, credit days, cash-discount terms or a standing discount sent with the new customer is refused (403) naming CUSTOMER_MANAGE_SETTINGS. Zero or blank is not refused. A customer that needs such terms is created, or given them, by the firm administrator or a Firm Manager (TC-CUST-007).
- **Leaves:** customers and a changed sales setting.

### TC-SELL-033 — Named price levels, and a customer's own level

*Added 2026-10-03 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (all of it); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog SEL-9, A89
- **Fixture:** `selling-firm`
- **Steps:** as the fixture's **Firm admin**: Settings > Set up > Pricing > **Price Levels** → New *Dealer* and *Retail*. Masters > Products → `<SUFFIX>-DET` → price levels → Dealer 70, Retail 90. Masters > Customers → Anand → Price level *Dealer* (and, separately, a customer **group** with level *Retail*, Vijaya in it). Sell > **Quotations** → New for Anand: add DET and leave **Unit price** blank. Repeat for Vijaya. Then add a price list that has a **Rate** for DET and repeat for Anand.
- **Expect:** the blank price is filled with the customer's level rate (Dealer 70 for Anand, the group's Retail 90 for Vijaya — the customer's own level wins over the group's) before the GST-inclusive conversion; lines the server filled are not converted again. A price list **Rate** wins over the level, and the level wins over the product's own price. The same holds on a sales order. A typed unit price is kept as typed.
- **Leaves:** two levels, rates on one product.

### TC-SELL-034 — A UPI QR on the invoice, and sharing it on WhatsApp by hand

*Added 2026-10-03 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (the UPI ID, the A4 and thermal prints; not the QR's content or sharing by hand); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog MSG-2 (A55), MSG-1 (A56)
- **Fixture:** `selling-invoiced`
- **Also needs:** the approved invoice of 483.21 for Vijaya, given a phone number for this case; a browser or WhatsApp installed for the wa.me link. No messaging account is needed.
- **Steps:** as the fixture's **Firm admin**: Sell > **Sales Invoices** → Print settings → UPI ID `shop@upi` → Save; try `shop` alone. Print the approved invoice (A4, then the 80 mm roll). Receive part of the bill, print again; receive the rest, print again. Select the approved invoice → **WhatsApp**. Look at Vijaya's timeline.
- **Expect:** the UPI ID must look like `name@handle`. A bill that stands and still owes money prints *Scan to pay by UPI*: a QR with the payee, the amount still owing, INR and the bill number, plus the amount and the UPI ID beside it, in the A4 footer and under the total on the roll. A part-paid bill asks only for the rest; a paid one prints none; a draft or cancelled bill prints none. *WhatsApp* saves the PDF in Downloads, opens the folder with the file selected and opens WhatsApp web (wa.me) with the covering note (and the UPI line); the bill's timeline reads *WhatsApp shared by hand to …* and never "sent".
- **Leaves:** a print template with a UPI ID, a timeline entry.

### TC-SELL-035 — Payment reminders and other documents sent by hand

*Added 2026-10-03 from the code. **Server side driven 2026-10-05** on `fx_t1005j1us_s` (the statement and the prints; reminders and sending were blocked by D-MSG-1 and are still to drive); results in `docs/qa/SELLING_API_CHECK_2026-10-05.md`. **The screens are not yet driven.***

- **Covers:** backlog MSG-3 (A57), MSG-4 (A95)
- **Fixture:** `selling-invoiced`
- **Also needs:** Settings > Firm > **Messaging** switched on with an email account for the firm (see the messaging setup guide) for the email halves; a customer who owes nothing; a customer set to *No reminders*; a quotation, a sales order, a receipt and a purchase order.
- **Steps:** as the fixture's **Firm admin**: Sell > **Customer Statements** → Vijaya → **Remind**; choose email. Then select the approved invoice → **Remind** → WhatsApp. Try Remind for the customer who owes nothing and for the *No reminders* customer. Then use **Send** (email) on a quotation, a sales order, a receipt and a purchase order; print the order and the receipt.
- **Expect:** the reminder sends the customer's **statement of account** as a PDF: the movement from the oldest unpaid bill to today, the closing balance, the unpaid bills with days overdue, and the UPI line where it applies. Email queues an outbox row and the worker sends it; WhatsApp opens WhatsApp web (wa.me) as in TC-SELL-034 and is recorded in the customer's audit trail. A customer who owes nothing and one marked *No reminders* are refused by name on both roads. The five documents send by email with a covering note and the PDF rendered at send time; a cancelled document or a reversed receipt is refused. The order and the receipt each have a Print (the receipt on A5).
- **Leaves:** outbox rows, audit entries.

---

**The nine selling features of backlog 87 (SG-1 to SG-9).** Cases TC-SELL-036 onward were written from the code and its automated tests on 2026-10-05 and have not yet been run by hand; treat a failure as possibly the case's mistake until it is settled. Each case stands alone: it names everything it needs and uses no other case's documents. They share these masters, which no earlier case touches:

| Record | Values |
| --- | --- |
| Product `<SUFFIX>-CTR` *Counter Item* | Selling price 100, GST 18% Local, HSN / SAC `3402`, 500 in MAIN bought at 60 |
| Product `<SUFFIX>-SVC` *Installation* | Product type *SERVICE*, selling price 500, GST 18% Local, HSN / SAC `998739`, no stock |
| Customer `<SUFFIX>-C03` *Registered Buyer* | a GSTIN in the firm's own state, credit limit 0, no standing discount |
| Counter billing | Settings > Selling > **Sales Stages**: *Sales order* and *Delivery note* both **off**. Sell > Sales Invoices → **New Invoice** then opens the counter bill. Switch both back **on** after the counter cases |
| Figures | 10 of `<SUFFIX>-CTR` at 100 is 1,000.00 before tax, 90.00 CGST + 90.00 SGST, 1,180.00 in all. Where a case says *the bill of 1,180.00* it means that bill to the customer the case names |

Counter Shifts and Customer Rebates are under Sell > All Sell screens > Documents; Collection Sheet and Payment Promises under Sell > All Sell screens > Money; Transporters under Settings > Set up > Territories & routes; Party Adjustments under Accounts > All Accounts screens > Books. The journal of any step is read under Accounts > **Journal Entries**.

**GST sales register and HSN summary of sales (SG-1)**

### TC-SELL-036 — The GST sales register reads a bill by tax head

- **Covers:** backlog 87 row 1 (SG-1)
- **Fixture:** `selling-firm`
- **Also needs:** the masters in the table above; the Sales order and Delivery note stages **on**. One sale of 10 `<SUFFIX>-CTR` at 100 to `<SUFFIX>-C03`, Discount % `0`: order approved, delivery note dispatched, invoice approved today (1,180.00). One more invoice left as a **draft**.
- **Steps:** as the fixture's **Firm admin**: Reports > Financial → **GST sales register**, period this month → run. Then **Export**.
- **Expect:** one row for the approved bill: Type **Invoice**, its number, Customer *Registered Buyer*, GSTIN the customer's, Place of supply the firm's state code, Taxable **1,000.00**, IGST 0.00, CGST **90.00**, SGST **90.00**, Cess 0.00, Total tax **180.00**, Total **1,180.00**; *Against invoice* blank. The draft is not listed. The figures equal the bill's journal: Dr 1100 Trade Receivables 1,180.00, Cr 4000 Sales 1,000.00, Cr Output CGST 90.00, Cr Output SGST 90.00. The export matches the grid.
- **Leaves:** an approved bill and a draft.

### TC-SELL-037 — Credit notes and returns are rows in minus, a debit note a row in plus

- **Covers:** backlog 87 row 1 (SG-1)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above, stages **on**; an approved bill of 1,180.00 to `<SUFFIX>-C03` as in TC-SELL-036, nothing received on it.
- **Steps:** as the fixture's **Firm admin**: (a) Sell > Returns & notes > Credit Notes → **Raise credit note**: the bill, Line 1, Reason Rate difference, Credit, before tax **100** → Raise; run the register before approving it. (b) **Approve** it and run the register again. (c) Sell > Returns & notes > Debit Notes → New → the bill → **50** on its line → Save → Approve. (d) Sell > Returns & notes > Sales Returns → New Return against the bill, Quantity returned **2**, taken back into MAIN → Create draft → Approve → Complete. Run Reports > Financial → **GST sales register** for the month.
- **Expect:** (a) a draft credit note is not in the register. (b) a row Type **Credit note**, *Against invoice* the bill's number, Taxable **-100.00**, CGST **-9.00**, SGST **-9.00**, Total **-118.00**, on the note's own date. (c) a row Type **Debit note**, Taxable **50.00**, CGST **4.50**, SGST **4.50**, Total **59.00**. (d) a row Type **Sales return**, Taxable **-200.00**, CGST **-18.00**, SGST **-18.00**, Total **-236.00**; an approved return that is not yet completed is not listed. The four rows' Taxable adds to **750.00**, the same net figure the HSN table (Table 12) of GSTR-1 states for the month under Accounts > All Accounts screens > Tax filing > GST Returns. (GSTR-1 answers only for a firm with a GST number: put one on the fixture firm, or use `compliance-firm`.)
- **Leaves:** a credit note, a debit note and a completed return on one bill.

### TC-SELL-038 — The HSN summary of sales adds up to the register

- **Covers:** backlog 87 row 1 (SG-1)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above, stages **on**; an approved bill of 10 `<SUFFIX>-CTR` at 100 to `<SUFFIX>-C03` dated today, and an approved bill of 5 `<SUFFIX>-DET` at 84, Discount % `0`, to the same customer (`<SUFFIX>-DET` carries no HSN).
- **Steps:** as the fixture's **Firm admin**: Reports > Financial → **HSN summary of sales**, period this month → run. Then set the period to the whole financial year and run again.
- **Expect:** a row HSN **3402**, Rate % **18**, Quantity **10**, Taxable **1,000.00**, CGST **90.00**, SGST **90.00**, Total tax **180.00**. A second row with a **blank** HSN for the detergent: Quantity 5, Taxable 420.00, CGST 37.80, SGST 37.80. The Taxable and Total tax columns add to the GST sales register's for the same days. A year is accepted here, though GSTR-1 itself is refused for more than three months. (GSTR-1 answers only for a firm with a GST number: put one on the fixture firm, or use `compliance-firm`.)
- **Leaves:** two approved bills.

### TC-SELL-039 — Who may open the two GST reports

- **Covers:** backlog 87 row 1 (SG-1)
- **Fixture:** `selling-firm`
- **Also needs:** a **Read Only** user and a **Warehouse** user in the firm.
- **Steps:** as the **Read Only** user: Reports > Financial → GST sales register and HSN summary of sales. As the **Warehouse** user: look for them. **(HTTP)** as the Warehouse user, `GET /api/v1/sales-invoices/reports/gst-register`.
- **Expect:** Read Only (who holds `SALES_VIEW` and `REPORT_VIEW`) opens both. The Warehouse user, who holds neither, is not offered them and the request is refused with **403**, "You do not have permission to perform this action."
- **Leaves:** unchanged.

---

**Walk-in cash sale (SG-2)**

### TC-SELL-040 — A walk-in bill names the Cash sale customer and is paid at the counter

- **Covers:** backlog 87 row 2 (SG-2)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing (both stages **off**).
- **Steps:** as the fixture's **Firm admin**: Sell > Sales Invoices → **New Invoice**. Under *Counter sale* press **Walk-in**. In *Buyer (optional)* type Buyer name `Ramesh` and Buyer phone `+919800000555`. Add `<SUFFIX>-CTR` quantity **10**. Read *Received now*. Press **Save & print (F9)**. Then Masters > Customers; Sell > Receipts; Accounts > Journal Entries. Start another bill and press **Walk-in** again.
- **Expect:** Walk-in selects the customer **Cash sale** (code `CASH`) and shows the two buyer boxes. *Received now* is pre-filled with the bill's amount payable (its total rounded to the paisa, 1,180.00 here), with the note "A walk-in bill is paid in full at the counter." F9 saves, approves and prints; the print names **Ramesh** and his phone in place of *Cash sale*. Masters > Customers lists one *Cash sale*, Outstanding 0.00; the second Walk-in reuses it and makes no second customer. Receipts shows one receipt of 1,180.00, Cash, applied to the bill. Journals: the bill Dr 1100 Trade Receivables 1,180.00 / Cr 4000 Sales 1,000.00 / Cr Output CGST 90.00 / Cr Output SGST 90.00; the receipt **Dr 1000 Cash 1,180.00 / Cr 1100 Trade Receivables 1,180.00**; and the delivery note's cost entry Dr 5200 Cost of Goods Sold 600.00 / Cr 1200 Inventory 600.00. Stock of `<SUFFIX>-CTR` is down 10.
- **Leaves:** the firm's Cash sale customer, a paid bill, a receipt.

### TC-SELL-041 — A walk-in bill that is not paid in full is refused at approval

- **Covers:** backlog 87 row 2 (SG-2)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: New Invoice → **Walk-in** → `<SUFFIX>-CTR` quantity **10** → change *Received now* to **500** → **Save & print (F9)**. Then set *Received now* to **0** and try again. Then set it to **1180** and press F9.
- **Expect:** with 500 the bill is kept as a draft and approval is refused, the screen staying open with the server's message: "A walk-in bill is paid in full at the counter: SI-… comes to 1180.00 and 500.00 was received. Take the rest, or bill a customer with a record to sell on credit." The amount to take is the bill's **amount payable**, its total rounded to the paisa; TC-SELL-093 covers a bill whose total is not a whole paisa. The same with 0. Nothing is posted and no receipt is made: Journal Entries has no entry for the bill. With 1180 it approves as in TC-SELL-040.
- **Leaves:** one paid walk-in bill.

### TC-SELL-042 — A walk-in bill paid with two tenders

- **Covers:** backlog 87 row 2 (SG-2), SEL-12
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: New Invoice → **Walk-in** → `<SUFFIX>-CTR` quantity **10** → **Split payment**: Cash **680**; **Add payment** UPI **500**, Reference `UPI-QA-500` → **Save & print (F9)**. Then repeat with Cash 680 and UPI **400**, and once more with Cash 700 and UPI **500**.
- **Expect:** 680 + 500 equals the bill, so it approves. Sell > Receipts shows **two** receipts, each applied to the bill: 680.00 Cash (**Dr 1000 Cash / Cr 1100 Trade Receivables**) and 500.00 with mode UPI (**Dr 1010 Bank / Cr 1100 Trade Receivables**). With 680 + 400 approval is refused with the paid-in-full message of TC-SELL-041, naming 1080.00 as received. With Cash 700 and UPI 500 it is refused the other way: "1200.00 was received against a bill of 1180.00. Enter what the bill is paid with; change is handed back." Split tenders approve only when they add up to the amount payable.
- **Leaves:** a paid bill and two receipts; a draft.

### TC-SELL-043 — A buyer's name belongs only on a walk-in bill

- **Covers:** backlog 87 row 2 (SG-2)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: New Invoice → choose `<SUFFIX>-C03` and look for the buyer boxes. Press **Walk-in**, then choose `<SUFFIX>-C03` again. **(HTTP)** `POST /api/v1/sales-invoices` for `<SUFFIX>-C03` with `"buyer_name": "Ramesh"`.
- **Expect:** *Buyer (optional)* shows only while the customer is *Cash sale*, and goes when another customer is chosen. The request is refused: "A buyer's name and phone are typed only on a walk-in bill. This bill names a customer with a record; correct the customer instead."
- **Leaves:** unchanged.

### TC-SELL-044 — The Cash sale customer cannot be deleted, given credit, registered or made inactive

- **Covers:** backlog 87 row 2 (SG-2)
- **Fixture:** `selling-firm`
- **Also needs:** the Cash sale customer (press **Walk-in** once on a counter bill, as in TC-SELL-040).
- **Steps:** as the fixture's **Firm admin**: Masters > Customers → *Cash sale*. (a) **Delete**. (b) Edit: Credit limit `5000` → Save. (c) Edit: a GST number → Save. (d) Edit: change the status to anything but Active → Save.
- **Expect:** each is refused and the customer is unchanged: (a) "Cash sale is the walk-in customer every counter bill without a customer record names; it cannot be deleted." (b) "Cash sale is the walk-in customer and takes no credit: its bills are paid in full at the counter." (c) "Cash sale is the walk-in customer and is unregistered. Bill a registered buyer to a customer record of its own." (d) "Cash sale is the walk-in customer and stays active."
- **Leaves:** unchanged.

### TC-SELL-045 — A walk-in bill earns no loyalty points and files as B2C

- **Covers:** backlog 87 row 2 (SG-2)
- **Fixture:** `selling-firm` (its loyalty scheme gives 2 points per 100)
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: a walk-in bill of 10 `<SUFFIX>-CTR`, paid in full, F9. Then a counter bill of the same to `<SUFFIX>-C01` (Vijaya), Discount % `0`, *Received now* 1180, F9. Settings > Set up > Pricing > **Loyalty**. Reports > Financial → **GST sales register** for today.
- **Expect:** Loyalty lists Vijaya with about **23.6** points from her bill (2 per 100 of 1,180.00) and has **no** row for *Cash sale*. In the register both bills show a blank GSTIN; the walk-in bill's Customer is *Cash sale*.
- **Leaves:** two paid bills.

---

**Service invoices (SG-3)**

### TC-SELL-046 — A bill of a service moves no stock and posts no cost

- **Covers:** backlog 87 row 3 (SG-3)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: New Invoice → `<SUFFIX>-C03` → add `<SUFFIX>-SVC` quantity **1** → Save, then **Approve** the draft from the list. Stock > All Stock screens > Stock > Inventory and Stock > Stock Ledger for `<SUFFIX>-SVC`. Sell > Delivery Notes. Accounts > Journal Entries. Then a second bill of quantity **5000**.
- **Expect:** the bill totals **590.00** (500.00 + 45.00 CGST + 45.00 SGST) and approves although the product has no stock. Its own delivery note reads **DISPATCHED**. The stock ledger has **no** row for the service and Inventory shows nothing reserved for it (or no row at all). Journals: only the bill's, Dr 1100 Trade Receivables 590.00 / Cr 4000 Sales 500.00 / Cr Output CGST 45.00 / Cr Output SGST 45.00; there is **no** Cost of Goods Sold entry for the note. 5000 units approve the same way.
- **Leaves:** two approved bills owed by `<SUFFIX>-C03`.

### TC-SELL-047 — Goods and a service on one bill

- **Covers:** backlog 87 row 3 (SG-3)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` quantity **2** and `<SUFFIX>-SVC` quantity **1** → Save → Approve → **Print**. Stock Ledger for both products. Journal Entries. Reports > Financial → HSN summary of sales for today.
- **Expect:** taxable 700.00, tax 126.00 (63.00 + 63.00), total **826.00**. The stock ledger shows `DISPATCH` −2 for the goods and nothing for the service. The note's cost entry is for the goods alone: Dr 5200 Cost of Goods Sold 120.00 / Cr 1200 Inventory 120.00. The print and the HSN summary carry the service under **998739** and the goods under 3402.
- **Leaves:** an approved bill.

### TC-SELL-048 — A service on a typed order and delivery note

- **Covers:** backlog 87 row 3 (SG-3)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; the Sales order and Delivery note stages **on**.
- **Steps:** as the fixture's **Firm admin**: Sell > Sales Orders → New Order: `<SUFFIX>-C03`, MAIN, `<SUFFIX>-SVC` quantity **3** → Create draft → **Approve**. Inventory for the service. Reports → **Back orders**. Sell > Delivery Notes → New off the order → Save → Approve → **Dispatch**. Stock Ledger. Bill the note and approve. Then cancel a second, approved order for the service.
- **Expect:** the order approves with nothing on hand; Inventory shows no reservation and the order is **not** on the back-order report. The note dispatches, the order reads DELIVERED, and the stock ledger has no row and Journal Entries no cost entry. The bill is 1,770.00 (1,500.00 + 135.00 + 135.00). Cancelling an approved service order writes no stock movement either.
- **Leaves:** an order, a note and a bill for a service; a cancelled order.

### TC-SELL-049 — Returning a service credits the customer and puts nothing on a shelf

*The server has no automated test of its own for this path (it rides the return's zero-movement path), so check it with extra care.*

- **Covers:** backlog 87 row 3 (SG-3)
- **Fixture:** `selling-firm`
- **Also needs:** the approved bill of 1 `<SUFFIX>-SVC` (590.00) to `<SUFFIX>-C03` from the steps of TC-SELL-046, built for this case.
- **Steps:** as the fixture's **Firm admin**: Sell > Returns & notes > Sales Returns → New Return against the bill, Quantity returned **1** → Create draft → Approve → **Complete**. Stock Ledger for the service. Masters > Customers → `<SUFFIX>-C03`.
- **Expect:** the return completes and the customer's Outstanding falls by **590.00**. The stock ledger has **no** `SALES_RETURN` row for the service and no stock is added.
- **Leaves:** a completed return.

---

**Charges on the bill with their own GST (SG-4)**

### TC-SELL-050 — A charge is taxed at its own rate and credited to Other Charges Recovered

- **Covers:** backlog 87 row 4 (SG-4)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` quantity **10**. Under **Other charges** press **Add charge**: Name `Packing`, Amount `100`, tax **GST 18% Local**, SAC `998540`. Read the totals. Save → Approve. Accounts > Journal Entries → the bill's entry.
- **Expect:** the charge adds 100.00 and 18.00 of tax (9.00 CGST + 9.00 SGST): taxable 1,100.00, tax 198.00, total **1,298.00**. Journal: Dr 1100 Trade Receivables 1,298.00 / Cr 4000 Sales **1,000.00** / Cr **4050 Other Charges Recovered 100.00** / Cr Output CGST 99.00 / Cr Output SGST 99.00. The customer's Outstanding rises by 1,298.00.
- **Leaves:** an approved bill with one charge.

### TC-SELL-051 — A charge that names no tax carries none

- **Covers:** backlog 87 row 4 (SG-4)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` quantity **10** → **Add charge**: Name `Handling`, Amount `50`, tax left at **(no tax)**, SAC blank. Also type **20** in *Delivery charge*. Save → Approve → the journal.
- **Expect:** *Handling* adds 50.00 and no tax. The delivery charge is still taxed with the goods (20.00 + 3.60). Total 1,180.00 + 50.00 + 23.60 = **1,253.60**. Journal: Cr 4050 Other Charges Recovered **50.00**; Cr 4000 Sales 1,020.00 (goods and delivery charge); Output CGST 91.80, Output SGST 91.80; Dr 1100 Trade Receivables 1,253.60.
- **Leaves:** an approved bill.

### TC-SELL-052 — Charges on a draft are replaced by what the editor holds

- **Covers:** backlog 87 row 4 (SG-4)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` quantity **10** → two charges: `Packing` 100 at GST 18% Local, and `Insurance` 40 at (no tax) → Save. Reopen the draft with **Edit**: both rows are there. Change Packing to **200**, remove Insurance with **Remove charge**, add a third row with an amount and **no name** → Save. Reopen. **(HTTP)** `PUT` the draft with eleven charges; and with a charge whose name is spaces. Then on a draft that carries a **Reference**, a bill discount and a delivery charge: **Edit**, change only the quantity → Save; **Edit** again, empty the Reference box and the bill discount box → Save.
- **Expect:** the first save totals 1,180.00 + 118.00 + 40.00 = **1,338.00**. After the edit only *Packing* 200.00 remains (the unnamed row is not a charge) and the total is 1,180.00 + 236.00 = **1,416.00**. Eleven charges are refused (at most ten), and a blank name is refused: "A charge needs a name." An edit keeps what it does not mention: after the quantity-only save the reference, the bill discount and the delivery charge are as they were; emptying the Reference or the bill discount box on a saved bill and saving clears it. **(HTTP)** a header field a `PUT` does not send is left as it is (freight, the bill discount, the reference, remarks, additional charges, round off, notes and charges). Null clears a reference, remarks, freight, a bill discount or a coupon; 0 clears additional charges and round off; an empty list clears notes and charges. A flat bill discount amount is carried as its rate when the quantity changes, so send the amount again to keep it flat.
- **Leaves:** a draft bill.

### TC-SELL-053 — The charge on the print, in the register and in the HSN summary

- **Covers:** backlog 87 row 4 (SG-4)
- **Fixture:** `selling-firm`
- **Also needs:** the approved bill of TC-SELL-050 (10 `<SUFFIX>-CTR` and *Packing* 100 at 18%, SAC `998540`: 1,298.00), built for this case.
- **Steps:** as the fixture's **Firm admin**: select the bill → **Print**. Reports > Financial → GST sales register, then HSN summary of sales, for today. Accounts > All Accounts screens > Tax filing > GST Returns → GSTR-1 for the month.
- **Expect:** the print lists **Packing** by name between the taxable value and the tax rows, and its HSN summary has a row for 998540. The register's row for the bill reads Taxable **1,100.00**, CGST 99.00, SGST 99.00, Total 1,298.00. The HSN summary has a row **998540**, Rate % 18, Quantity **0**, Taxable 100.00, beside the goods' row. GSTR-1 states the same 1,100.00. (GSTR-1 answers only for a firm with a GST number: put one on the fixture firm, or use `compliance-firm`.)
- **Leaves:** unchanged.

### TC-SELL-054 — What a charge does not do yet

- **Covers:** backlog 87 row 4 (SG-4), known limits
- **Fixture:** `selling-firm`
- **Also needs:** the approved bill of TC-SELL-050, built for this case, nothing received on it; the Sales order and Delivery note stages **on** for the second half.
- **Steps:** as the fixture's **Firm admin**: Sell > Returns & notes > Credit Notes → **Raise credit note** on the bill: look at what can be credited; credit Line 1 by **1000** before tax → Raise → Approve. Then Sell > Sales Orders → New Order and look for charges.
- **Expect:** a credit note offers the bill's **lines** only; the charge cannot be credited. After crediting the whole line (1,180.00) the customer still owes **118.00**, the charge and its tax. A sales order has no *Other charges*: charges are typed on the bill and are not carried from the order.
- **Leaves:** a credit note.

---

**Transporter master and freight terms (SG-5)**

### TC-SELL-055 — A transporter is kept once by name

- **Covers:** backlog 87 row 5 (SG-5)
- **Fixture:** `selling-firm`
- **Steps:** as the fixture's **Firm admin**: Settings > Set up > Territories & routes > **Transporters** → New: Name `Speedy Carriers`, GSTIN `33AAAPL1234C1ZV`, Phone `+919800000777`, Usual mode **Rail**, Active ticked → Save. New again with the same name. New: Name `Hill Cargo`, GSTIN `12345` → Save. New: Name `Hill Cargo`, GSTIN blank, Transporter ID (TRANSIN) `33AABCH5678K1Z2` → Save.
- **Expect:** *Speedy Carriers* is listed with Mode **Rail** and Active **Yes**. The second is refused: "There is already a transporter Speedy Carriers." The same name in other letters (`speedy carriers`) or with a trailing space is refused the same way. A GSTIN that is not the shape of a GSTIN is refused and nothing is saved. *Hill Cargo* saves with only a Transporter ID.
- **Leaves:** two transporters.

### TC-SELL-056 — Choosing a carrier fills the delivery note

- **Covers:** backlog 87 row 5 (SG-5)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; stages **on**; the transporter *Speedy Carriers* of TC-SELL-055 (GSTIN `33AAAPL1234C1ZV`, usual mode Rail); an approved order of 10 `<SUFFIX>-CTR` for `<SUFFIX>-C03`.
- **Steps:** as the fixture's **Firm admin**: Sell > Delivery Notes → **New** → the order. In **Carrier (master)** choose *Speedy Carriers*. In **Freight** choose **To pay**. **Save delivery note** → Approve → Dispatch → **Print** the challan.
- **Expect:** choosing the carrier fills *Transporter* `Speedy Carriers`, *Transporter GSTIN* `33AAAPL1234C1ZV` and *Moving by* **Rail**. The saved note keeps them, and the challan prints the transporter and **Freight: To pay**. Freight terms move no money: no journal names them, and the bill's *Delivery charge* is still what charges the customer.
- **Leaves:** a dispatched note.

### TC-SELL-057 — What is typed on the note wins, and the master never rewrites a note

- **Covers:** backlog 87 row 5 (SG-5)
- **Fixture:** `selling-firm`
- **Also needs:** as TC-SELL-056, with two approved orders.
- **Steps:** as the fixture's **Firm admin**: (a) New delivery note on the first order: choose *Speedy Carriers*, then overtype *Transporter* with `Speedy Carriers (Salem depot)` and set *Moving by* to **Road** → Save delivery note. (b) Settings > Set up > Territories & routes > Transporters → edit *Speedy Carriers*: Usual mode **Air** → Save. Print the note's challan. (c) **Delete** *Speedy Carriers*. Print the challan again.
- **Expect:** (a) the note keeps what was typed: `Speedy Carriers (Salem depot)`, Road. (b) the challan still prints what the note held; the edit rewrote nothing. (c) deleting the transporter is not refused, and the note still prints its carrier. The name is free again for a new transporter.
- **Leaves:** a note; no transporter *Speedy Carriers*.

### TC-SELL-058 — An inactive carrier is not offered and is refused

- **Covers:** backlog 87 row 5 (SG-5)
- **Fixture:** `selling-firm`
- **Also needs:** stages **on**; a transporter `Slow Lines` with **Active** unticked; an approved order.
- **Steps:** as the fixture's **Firm admin**: Sell > Delivery Notes → New → the order → open **Carrier (master)**. **(HTTP)** `POST /api/v1/delivery-notes` for the order with `transporter_id` of *Slow Lines*; and with `"freight_terms": "COLLECT"`.
- **Expect:** the picker lists active carriers only, and `(none)`. The request naming the inactive one is refused: "Slow Lines is marked inactive. Choose another transporter or make it active again." A freight term other than PAID, TO_PAY or TO_BE_BILLED is refused.
- **Leaves:** unchanged.

### TC-SELL-059 — Who keeps transporters, and what the note editor cannot do yet

- **Covers:** backlog 87 row 5 (SG-5), known limit
- **Fixture:** `selling-firm`
- **Also needs:** a **Field Sales** user; one dispatched delivery note with a carrier.
- **Steps:** as the **Field Sales** user: Settings > Set up > Territories & routes > Transporters. As the **Firm admin**: Sell > Delivery Notes → select the note and look for a way to change its carrier.
- **Expect:** Field Sales (who holds `SALES_VIEW` and not `SALES_UPDATE`) sees the list and is offered no New, Edit or Delete. The delivery note editor only **creates** notes: the carrier and freight of a note already raised cannot be changed on screen.
- **Leaves:** unchanged.

---

**Files on the five sales documents (SG-6)**

### TC-SELL-060 — Attaching a file to a sales invoice

- **Covers:** backlog 87 row 6 (SG-6)
- **Fixture:** `selling-firm`
- **Also needs:** any saved sales invoice; a PDF and a JPG or PNG photo under 10 MB.
- **Steps:** as the fixture's **Firm admin**: Sell > Sales Invoices → select the invoice → **Attachments** → **Add file** → the PDF. Add the photo. Close. Read the **Files** column. Open Attachments again → **Open** the PDF, then **Save as**.
- **Expect:** the panel is titled "Attachments · SI-…" and lists both files. The list's Files cell reads a paper clip and **2**; an invoice with nothing attached shows a blank cell. The file opens and saves byte for byte as it was added.
- **Leaves:** two files on the invoice.

### TC-SELL-061 — Only a PDF, JPG or PNG of up to 10 MB

- **Covers:** backlog 87 row 6 (SG-6)
- **Fixture:** `selling-firm`
- **Also needs:** any saved sales invoice; a file over 10 MB; a `notes.docx`; a text file renamed `fake.pdf`.
- **Steps:** as the fixture's **Firm admin**: Sell > Sales Invoices → the invoice → Attachments → Add file, each of the three in turn.
- **Expect:** each is refused and nothing is added (if the file picker does not offer a file, that is the refusal; otherwise the server's message shows): "The file is larger than 10 MB, the most it may be."; "Only PDF, JPG and PNG files may be attached; 'notes.docx' is not one by its name."; "'fake.pdf' is not a PDF, JPG or PNG file by its contents."
- **Leaves:** unchanged.

### TC-SELL-062 — Each of the five documents keeps its own files

- **Covers:** backlog 87 row 6 (SG-6)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above, stages **on**; one sale taken from a quotation to an order, a delivery note, an invoice and a sales return; a PDF.
- **Steps:** as the fixture's **Firm admin**: on each of Sell > Quotations, Sales Orders, Delivery Notes, Sales Invoices and Sell > Returns & notes > Sales Returns, select the document → **Attachments** → Add file. Then open Attachments on the invoice.
- **Expect:** every one of the five lists has **Attachments** and a **Files** column. A file added to the order shows on the order only: the invoice of the same sale lists just its own.
- **Leaves:** one file on each document.

### TC-SELL-063 — Deleting a file, and who may add one

- **Covers:** backlog 87 row 6 (SG-6)
- **Fixture:** `selling-firm`
- **Also needs:** a sales invoice with one file attached; a **Read Only** user.
- **Steps:** as the **Read Only** user: Sell > Sales Invoices → the invoice → Attachments. As the **Firm admin**: Attachments → **Delete** the file → confirm. Settings > Platform > System > Audit Logs.
- **Expect:** Read Only sees the file and can open it, with no **Add file** and no **Delete**. After the administrator deletes it the panel reads "Nothing is attached yet.", the Files cell is blank, and the audit trail keeps that the file was removed.
- **Leaves:** unchanged.

---

**Hold and recall a counter bill; shift closing (SG-7)**

### TC-SELL-064 — Holding a counter bill and recalling it

- **Covers:** backlog 87 row 7 (SG-7)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` quantity **3** → **Hold (F8)** → in *Hold this bill* type the note `blue shirt, back in 5 min` → **Hold**. Read Inventory for the product. Type a line on the fresh bill and press **Recall**. Clear the line, press **Recall (1)**, pick the bill. Change the quantity to **4** → **Save & print (F9)** with *Received now* 472.
- **Expect:** "SI-… is held. Recall it from the Recall button." and a blank bill opens; the button reads **Recall (1)**. The held bill keeps the stock its saved draft reserved (Reserved 3) and ships nothing. Recall with a line typed is refused: "Hold this bill, or finish it, before recalling another." *Recall a held bill* lists the bill with its note, when it was held and its total; picking it reopens the draft and the button reads **Recall**. The bill then approves for 4 (472.00) like any other, and 4 leave the stock. The delivery note and order the first save raised read CANCELLED, "Bill … was changed before approval.", and a new pair carries the 4; their numbers are spent. Any change to a saved or recalled counter bill's lines (a quantity, a price, a discount, another product) withdraws the pair the save raised and raises a new one, so the bill, the note and the order agree after each save; a save that changes nothing on the lines raises nothing. TC-SELL-088 and TC-SELL-089 have the whole of it.
- **Leaves:** an approved bill.

### TC-SELL-065 — A held bill is never approved

- **Covers:** backlog 87 row 7 (SG-7)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing; one bill held as in TC-SELL-064 and one ordinary draft bill.
- **Steps:** as the fixture's **Firm admin**: Sell > Sales Invoices → select the held draft → **Approve**. Tick both drafts → bulk **Approve**. Select the held draft → **Edit**, change the quantity → save. Then **Cancel** the held draft.
- **Expect:** approval is refused: "SI-… is held. Recall it first, then approve it." Bulk approve approves the ordinary draft and reports the held one with the same message. The edit saves and the bill is still held. Cancelling the held draft clears the hold and gives back the stock it reserved (its order is cancelled with it): it no longer counts in **Recall**.
- **Leaves:** an approved bill and a cancelled one.

### TC-SELL-066 — Only a draft can be held

- **Covers:** backlog 87 row 7 (SG-7)
- **Fixture:** `selling-firm`
- **Also needs:** an approved sales invoice and a draft one that is not held.
- **Steps:** **(HTTP)** as the fixture's **Firm admin**: `POST /api/v1/sales-invoices/{id}/hold` with `{"note": "x"}` on the approved bill; `POST /api/v1/sales-invoices/{id}/recall` on the draft that is not held; `GET /api/v1/sales-invoices?is_held=true`.
- **Expect:** "Only a draft bill can be held; SI-… is approved." and "SI-… is not held." The list returns only held bills, each with `is_held`, `held_at` and `held_note`.
- **Leaves:** unchanged.

### TC-SELL-067 — Opening a shift, and one open shift per cashier

- **Covers:** backlog 87 row 7 (SG-7)
- **Fixture:** `selling-firm`
- **Also needs:** counter billing; a **Counter Sales** user and a **Sales Manager** user in the firm; neither has a shift open.
- **Steps:** as the **Counter Sales** user: New Invoice. The strip above the scan field reads **No shift open** → **Open shift** → Opening float `500` → Open shift. **(HTTP)** `POST /api/v1/counter-shifts/open` with `{"opening_float": "100"}` again as the same user. Sign in as the **Sales Manager**: New Invoice → Open shift, float `200`. Sell > All Sell screens > Documents > **Counter Shifts**.
- **Expect:** the strip reads "Shift SHIFT-…" (the firm's next number), when it was opened, **0 bills** and **cash expected 500.00**, with **Close shift**. The second request is refused (409): "You already have SHIFT-… open. Close it before opening another." The Sales Manager opens a shift of their own with the next number. Counter Shifts lists both: Cashier, Opened, Float, Expected, Status **Open**. Opening a shift posts nothing. A Counter Sales user may open a shift: it takes the right to raise sales invoices, not the right to approve them.
- **Leaves:** two open shifts (close them: TC-SELL-069 shows how).

### TC-SELL-068 — Expected cash is the float and the cash tenders, in the shift of the cashier who made the bill

- **Covers:** backlog 87 row 7 (SG-7; D-SELL-51)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing; a **Counter Sales** user and a **Sales Manager** user in the firm; the Sales Manager has a shift of their own open with float `200`; no shift open for the Counter Sales user.
- **Steps:** as the **Counter Sales** user: New Invoice → **Open shift**, float `500`. Bill 1: **Walk-in**, 10 `<SUFFIX>-CTR`, *Received now* 1180 Cash, F9. Bill 2: Walk-in, 10 `<SUFFIX>-CTR`, **Split payment** Cash 680 + UPI 500, F9. Bill 3: `<SUFFIX>-C03`, 10 `<SUFFIX>-CTR`, *Received now* blank, Save. Sign in as the **Sales Manager**: Sell > Sales Invoices → **Approve** the three drafts. Sign in as the Counter Sales user again and read the strip; then Counter Shifts → each of the two shifts → **View**.
- **Expect:** Counter Sales cannot approve, so F9 leaves each bill a **draft** for somebody who may; while they are drafts the strip still reads 0 bills. Once the Sales Manager has approved them the **cashier's** strip reads **2 bills** and **cash expected 2,360.00** (500 + 1,180 + 680): a bill paid at the counter is counted in the open shift of the cashier who **made** it, whoever approves it. View on the cashier's shift shows Bills 2, Total billed 2,360.00, CASH 1,860.00, UPI 500.00, CARD 0.00, BANK_TRANSFER 0.00, Opening float 500.00, Cash expected 2,360.00. The Sales Manager's own shift still reads **0 bills** and cash expected **200.00**. The credit bill took no money at the counter and is in neither shift.
- **Leaves:** two open shifts, the cashier's with two bills; three approved bills.

### TC-SELL-069 — Closing a shift short posts to Cash Short and Over

- **Covers:** backlog 87 row 7 (SG-7)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing; a shift of the Firm admin's own with float `500` and one walk-in bill of 1,180.00 paid in cash (expected 1,680.00).
- **Steps:** as the fixture's **Firm admin**: on the counter bill press **Close shift**. Type *Counted cash* `1670`, Note `End of day` → **Close shift** → **Print report** → Done. Accounts > Journal Entries. Counter Shifts.
- **Expect:** the dialog shows the tenders, Opening float 500.00 and **Cash expected 1,680.00**; typing 1670 reads **Short by 10.00**. After closing: "Shift SHIFT-… is closed.", Cash counted 1,670.00. One journal, reference the shift's number, "Cash short at the close of SHIFT-…": **Dr 6960 Cash Short and Over 10.00 / Cr 1000 Cash 10.00**. The report is a PDF of the takings by mode, the count and the difference. Counter Shifts shows the shift **Closed**, Expected 1,680.00, Counted 1,670.00, Difference −10.00. Closing it again is refused: "SHIFT-… is already closed." The strip reads No shift open. A shift opened after midnight is listed under that day and its report says it was printed on it.
- **Leaves:** a closed shift and its journal.

### TC-SELL-070 — Closing over, and closing exact

- **Covers:** backlog 87 row 7 (SG-7)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing; no shift open for the Firm admin.
- **Steps:** as the fixture's **Firm admin**: (a) Open shift, float `500`; one walk-in bill of 1,180.00 in cash; Close shift with *Counted cash* `1685`. (b) Open shift again, float `500`; no bill; Close shift with `500`.
- **Expect:** (a) reads **Over by 5.00**; the journal is the other way round: **Dr 1000 Cash 5.00 / Cr 6960 Cash Short and Over 5.00**, its reference this shift's own number. (b) reads **Cash is exact** and posts **no** journal. Both shifts read Closed, with Difference 5.00 and 0.00.
- **Leaves:** two closed shifts.

### TC-SELL-071 — Who may close a shift

- **Covers:** backlog 87 row 7 (SG-7)
- **Fixture:** `selling-firm`
- **Also needs:** counter billing; a **Sales Manager** and a **Field Sales** user in the firm; an open shift of the **Sales Manager's**.
- **Steps:** **(HTTP)** as the **Field Sales** user (who holds `SALES_INVOICE_CREATE` and not `SALES_APPROVE`): `POST /api/v1/counter-shifts/{id}/close` with `{"counted_cash": "200"}` on the Sales Manager's shift. Then the same as the **Firm admin**. On screen, as Field Sales: Sell > All Sell screens > Documents > Counter Shifts.
- **Expect:** Field Sales is refused (403): "Only the cashier who opened this shift, or somebody who may approve sales, can close it." The Firm admin, who may approve sales, closes it: "Shift closed." Field Sales can see the Counter Shifts list and print a shift report.
- **Leaves:** a closed shift.

### TC-SELL-072 — Shifts are optional, and a held bill does not stop the close

- **Covers:** backlog 87 row 7 (SG-7), known limits
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing; no shift open for the Firm admin.
- **Steps:** as the fixture's **Firm admin**: (a) with **No shift open**, a walk-in bill of 1,180.00 in cash, F9. (b) Open shift, float `0`; raise a bill and **Hold (F8)** it; press **Close shift**, Counted cash `0`.
- **Expect:** (a) the bill approves and its receipt posts as always; it belongs to no shift. (b) the close dialog warns "1 bill is still held. Recall and finish it, or close the shift and leave it for the next one." and still closes; the held bill stays a held draft. Known limits: a cash receipt is booked to the firm's Cash account whatever account a shift names, and there is no counter refund against a bill, no count by denomination and no handing a shift to another cashier.
- **Leaves:** a paid bill, a closed shift, a held draft.

---

**Collection follow-up (SG-8)**

### TC-SELL-073 — The collection sheet, by collector

- **Covers:** backlog 87 row 8 (SG-8)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; an approved bill of 1,180.00 to `<SUFFIX>-C03` with nothing received; a second member of the firm (a **Counter Sales** user).
- **Steps:** as the fixture's **Firm admin**: Masters > Customers → `<SUFFIX>-C03` → Edit → set **Collector** (its helper reads "Who chases the dues of this customer; the collection sheet groups by them") to the Counter Sales user → Save. Sell > All Sell screens > Money > **Collection Sheet**. Filter **Collector** to that user; tick **Overdue only**; untick it. **Print sheet**.
- **Expect:** the sheet lists every bill still owing: Collector, Customer, Phone, Bill, Bill date, Due, Days overdue, Outstanding **1,180.00**, and the promise columns blank. The bill is under the chosen collector; a customer with no collector is under its account manager, or nobody. *Overdue only* hides a bill not yet due. Print sheet saves a PDF: "The collection sheet was saved."
- **Leaves:** a collector on the customer.

### TC-SELL-074 — Recording a promise posts nothing

- **Covers:** backlog 87 row 8 (SG-8)
- **Fixture:** `selling-firm`
- **Also needs:** an approved bill of 1,180.00 to `<SUFFIX>-C03` with nothing received.
- **Steps:** as the fixture's **Firm admin**: Collection Sheet → select the bill → **Record promise**. *Promised on* three days from today, Amount `1180` (offered), Note `will pay by NEFT` → **Save promise**. Sell > All Sell screens > Money > **Payment Promises**. Accounts > Journal Entries. Masters > Customers → the customer.
- **Expect:** "Promise recorded." The sheet's row now shows Promised on, Promised amount 1,180.00 and Promise status **Pending**. Payment Promises lists it: Customer, Bill, Promised on, Amount 1,180.00, Received 0.00, Status Pending, Recorded on today, Recorded by. **No journal** is written and the customer's Outstanding is still 1,180.00.
- **Leaves:** a pending promise.

### TC-SELL-075 — A promise is kept by the money, and un-kept by a reversal

- **Covers:** backlog 87 row 8 (SG-8)
- **Fixture:** `selling-firm`
- **Also needs:** an approved bill of 1,180.00 to `<SUFFIX>-C03` and a promise for the whole of it, promised for three days from today, both made for this case.
- **Steps:** as the fixture's **Firm admin**: Sell > Receipts → Record Receipt: the customer, Amount `500`, Bank, Apply 500 to the bill. Payment Promises. Record a second receipt of `680`, applied to the bill. Payment Promises. Then **Reverse** the second receipt with a reason. Payment Promises.
- **Expect:** after 500: Received 500.00, Status still **Pending** (part of the money does not keep a promise). After 680: Received 1,180.00, Status **Kept**. After the reversal: Received 500.00 and Status back to **Pending**. The receipts post as ever (Dr 1010 Bank / Cr 1100 Trade Receivables); the promise itself posts nothing at any point.
- **Leaves:** a part-paid bill, a pending promise, a reversed receipt.

### TC-SELL-076 — Due today, the chase list, and broken

- **Covers:** backlog 87 row 8 (SG-8)
- **Fixture:** `selling-firm`
- **Also needs:** an approved bill of 1,180.00 to `<SUFFIX>-C03` with nothing received.
- **Steps:** as the fixture's **Firm admin**: Collection Sheet → the bill → Record promise, *Promised on* **today**, Amount `1180` → Save promise. Payment Promises → tick **To chase today**; set **Status** to *Due today*. The **next day**, with nothing received, open Payment Promises and the chase list again; then record a new promise on the bill and look once more.
- **Expect:** today the promise reads **Due today** and is on the chase list. The next day it reads **Broken** and is still on the chase list. Once a newer promise is taken on the bill, the broken one leaves the chase list but still reads Broken in the full list. **(HTTP)** `GET /api/v1/collections/sheet?as_of=<tomorrow>` shows the promise **Broken** without waiting.
- **Leaves:** a broken promise and a pending one.

### TC-SELL-077 — Promises that are refused

- **Covers:** backlog 87 row 8 (SG-8)
- **Fixture:** `selling-firm`
- **Also needs:** an approved bill of 1,180.00 to `<SUFFIX>-C03` with nothing received; a fully paid bill and a draft bill of the same customer; an approved bill of `<SUFFIX>-C01`.
- **Steps:** as the fixture's **Firm admin**: Collection Sheet → the unpaid bill → Record promise with Amount `2000` → Save promise. **(HTTP)** `POST /api/v1/collections/promises` for `<SUFFIX>-C03`: (a) `promised_on` yesterday; (b) `sales_invoice_id` the paid bill; (c) the draft bill; (d) the bill of `<SUFFIX>-C01`.
- **Expect:** 2000 is refused with the dialog still open: "Bill SI-… owes 1,180.00; a promise cannot be for more than that." (a) "A promise is for today or a later day." (the dialog's date picker offers no earlier day). (b) "Bill SI-… owes nothing." (c) "Bill SI-… is not approved, so nothing is owed on it yet." (d) "Bill SI-… belongs to another customer." Nothing is recorded by any of them. A promise dated today is accepted at any hour: today is the firm's own day. A receipt entered after the promise counts toward it whatever date it carries, up to the promised day: yesterday's cash keyed in today keeps the promise. A receipt dated after the promised day does not.
- **Leaves:** unchanged.

### TC-SELL-078 — A promise is withdrawn, never edited

- **Covers:** backlog 87 row 8 (SG-8)
- **Fixture:** `selling-firm`
- **Also needs:** a pending promise on an unpaid bill, made for this case.
- **Steps:** as the fixture's **Firm admin**: Payment Promises → select the promise → **Withdraw** → leave the reason empty; then give `Customer asked for a week more` → Withdraw. Look for a way to edit or delete a promise. **(HTTP)** withdraw the same promise again.
- **Expect:** an empty reason withdraws nothing. With a reason: "The promise was withdrawn.", Status **Withdrawn**, and the row stays in the list. Withdraw is no longer offered for it, nor for a Kept promise. There is no Edit and no Delete: a changed promise is a withdrawn one and a new one. The repeated request is refused (409): "That promise was already withdrawn." **(HTTP)** withdrawing a Kept promise is refused (422): "That promise was kept: the money promised was received, so there is nothing to withdraw."
- **Leaves:** a withdrawn promise.

### TC-SELL-079 — Who may read the sheet and who may record a promise

- **Covers:** backlog 87 row 8 (SG-8)
- **Fixture:** `selling-firm`
- **Also needs:** an unpaid approved bill; a **Counter Sales**, a **Read Only** and a **Field Sales** user in the firm.
- **Steps:** as each user in turn: Sell > All Sell screens > Money → Collection Sheet and Payment Promises. **(HTTP)** as Read Only, `POST /api/v1/collections/promises`.
- **Expect:** Counter Sales (who holds `RECEIPT_VIEW` and `RECEIPT_CREATE`) reads both and is offered **Record promise** and **Withdraw**. Read Only (`RECEIPT_VIEW` alone) reads both and is offered neither; the request is refused with 403. Field Sales, who holds neither code, is not offered the two screens.
- **Leaves:** unchanged.

---

**Turnover rebate to a customer (SG-9)**

For these cases the agreement covers **last calendar month**, and its bills carry an invoice date in that month, so the accounting period of last month must be open. Slabs: from turnover of 1,000 → 1%, from 5,000 → 2%. The rate of the slab reached applies to the whole turnover, before tax.

### TC-SELL-080 — The slab reached sets the rate on the whole turnover

- **Covers:** backlog 87 row 9 (SG-9)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; a customer `<SUFFIX>-C05` *Rebate Buyer* with no other bills; one approved bill to it of 10 `<SUFFIX>-CTR` at 100 (1,000.00 before tax) dated in last month.
- **Steps:** as the fixture's **Firm admin**: Sell > All Sell screens > Documents > **Customer Rebates** → New: **Customer** `<SUFFIX>-C05`, Code `TR-1`, Name `Turnover rebate`, period the first to the last day of last month, **Add slab** From turnover of `1000` Rebate % `1`, Add slab `5000` and `2` → save. Read the row. Approve a second bill to the customer, 40 `<SUFFIX>-CTR` at 100 dated in last month, and Refresh. Open **Statement**.
- **Expect:** "Rebate TR-1 saved." Status ACTIVE, Turnover **1,000.00**, Rate % **1**, Earned **10.00**, Next slab / To next 5,000 and **4,000.00**. After the second bill: Turnover **5,000.00**, Rate % **2**, Earned **100.00**, no next slab. The statement shows the turnover by kind of document (invoiced, returned, credit notes, debit notes) and "Nothing has been settled yet." A bill dated outside the period, a draft, and another customer's bill do not count. Nothing is posted by the agreement.
- **Leaves:** an agreement and two bills (5,900.00 owed).

### TC-SELL-081 — A rebate is accrued once, after its period ends

- **Covers:** backlog 87 row 9 (SG-9)
- **Fixture:** `selling-firm`
- **Also needs:** the agreement `TR-1` and the two bills of TC-SELL-080, built for this case (turnover 5,000.00, earned 100.00); a second agreement `TR-NOW` for another customer whose period is the **current** month.
- **Steps:** as the fixture's **Firm admin**: Customer Rebates → select `TR-NOW` and look at **Accrue**. **(HTTP)** `POST /api/v1/customer-rebates/{id}/accrue` for it. Select `TR-1` → **Accrue** → leave *Accrual date (optional)* blank → Accrue. Accounts > Journal Entries. Approve one more bill dated in last month and Refresh. Try **Edit** and **Cancel** on `TR-1`.
- **Expect:** **Accrue** is disabled while the period is running; the request is refused: "The period runs to … ; accrue it after that, once every bill of the period is in." For `TR-1`: "Rebate TR-1 accrued.", Status **ACCRUED**, Accrued 100.00, To settle 100.00. Journal dated the **last day of the period**, reference `CREBATE-TR-1`: **Dr 5310 Rebates Allowed 100.00 / Cr 2900 Customer Rebates Payable 100.00**; no tax leg. The late bill does not move what was booked, though the statement's *Turnover today* shows it. **Edit** and **Cancel** are disabled on an accrued agreement; the server's words for the same refusals are "A rebate agreement that is accrued cannot be changed." and "… cannot be cancelled."
- **Leaves:** an accrued agreement and its journal.

### TC-SELL-082 — Settling a rebate against the customer's bills

- **Covers:** backlog 87 row 9 (SG-9)
- **Fixture:** `selling-firm`
- **Also needs:** the accrued agreement `TR-1` of TC-SELL-081, built for this case (100.00 to settle; the customer owes 5,900.00 on two bills).
- **Steps:** as the fixture's **Firm admin**: Customer Rebates → `TR-1` → **Settle against bills**: Amount to settle `60`, Reason `September turnover rebate`, type 60 against the first open bill → save. Accounts > All Accounts screens > Books > **Party Adjustments** → the new draft → **Approve**. Journal Entries; Masters > Customers; Customer Rebates → Statement. Then settle `50` more.
- **Expect:** **Settle against bills** is on the toolbar because the Firm admin may manage party adjustments (`PARTY_ADJUSTMENT_MANAGE`); it is shown on that right alone, and is live only for an accrued agreement with something left to settle. The dialog says "… 100.00 left to settle. This drafts a party adjustment that credits the customer's account; it is approved in Party Adjustments." A draft posts nothing. Approving posts **Dr 2900 Customer Rebates Payable 60.00 / Cr 1100 Trade Receivables 60.00**, no tax; the customer's Outstanding falls by 60.00 and the first bill owes 60.00 less in Record Receipt. The agreement reads Settled 60.00, To settle **40.00**, and its statement lists the adjustment. 50 more is refused: "No more than 40.00 is left to settle." on the screen (the server says "The rebate has 40.00 still to settle, so … cannot be set against the customer's account."). A rebate is settled only this way: no credit note is raised and nothing reaches GSTR-1.
- **Leaves:** an approved party adjustment of 60.00.

### TC-SELL-083 — Reversing an accrual

- **Covers:** backlog 87 row 9 (SG-9)
- **Fixture:** `selling-firm`
- **Also needs:** the agreement `TR-1` accrued (100.00) and settled by an approved adjustment of 60.00, as in TC-SELL-082, built for this case.
- **Steps:** as the fixture's **Firm admin**: Customer Rebates → `TR-1` → **Reverse accrual**. Then Party Adjustments → the adjustment → **Cancel** with a reason. Reverse accrual again. Journal Entries. Then **Accrue** once more.
- **Expect:** the first reversal is refused: "Part of this rebate is already set against the customer's account; cancel those settlements first." Cancelling the adjustment puts the 60.00 back on the customer's account and the agreement reads To settle 100.00. The reversal then works: "Accrual of TR-1 reversed.", Status ACTIVE, and a mirror journal `CREBATE-TR-1-REV`. Accruing again posts a new journal under `CREBATE-TR-1-2`.
- **Leaves:** an agreement accrued a second time; a cancelled adjustment.

### TC-SELL-084 — Two agreements cannot cover the same sales

- **Covers:** backlog 87 row 9 (SG-9)
- **Fixture:** `selling-firm`
- **Also needs:** a customer `<SUFFIX>-C05` in the customer group *Wholesaler*; an ACTIVE agreement `TR-1` for the customer covering last month.
- **Steps:** as the fixture's **Firm admin**: Customer Rebates → New for the same customer, Code `TR-2`, a period overlapping `TR-1` by one day → save. New for **Customer group** *Wholesaler*, Code `TR-G`, the same month → save. New for the same customer, Code `TR-1`, a month that does not overlap → save. New `TR-3` with two slabs both from `1000`. New `TR-4` whose period ends before it starts.
- **Expect:** `TR-2` is refused: "… already has rebate agreement TR-1 from … to …; two cannot cover the same sales." `TR-G` is refused because a member already has an agreement of its own over those dates: "… is in the customer group Wholesaler and already has rebate agreement TR-1 of its own over these dates; cancel that one or leave the customer out of the group." A repeated code is refused: "A rebate agreement TR-1 already exists." Two slabs at one turnover and a backwards period are refused before anything is saved ("Two slabs cannot start at the same turnover."; "The period must not end before it starts.").
- **Leaves:** unchanged.

### TC-SELL-085 — An agreement for a customer group

- **Covers:** backlog 87 row 9 (SG-9)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; a customer group `REBATE-GRP` *Rebate Group* holding two customers, `<SUFFIX>-C06` and `<SUFFIX>-C07`, neither with an agreement; an approved bill of 3,000.00 before tax to the first and 2,000.00 before tax to the second, dated last month; `<SUFFIX>-C03` outside the group.
- **Steps:** as the fixture's **Firm admin**: Customer Rebates → New: **Customer group** *Rebate Group*, Code `TR-GRP`, last month, slabs 1,000 → 1% and 5,000 → 2% → save. Statement. **Accrue**. **Settle against bills**: choose *Customer in the group* `<SUFFIX>-C06`, Amount `70`, a reason → save, and approve it in Party Adjustments. **(HTTP)** create a `CUSTOMER_REBATE` party adjustment naming `TR-GRP` for `<SUFFIX>-C03`.
- **Expect:** Turnover **5,000.00** (the two customers together), Rate % 2, Earned **100.00**; the statement has one row per customer, 3,000.00 and 2,000.00. Accrual posts Dr 5310 Rebates Allowed 100.00 / Cr 2900 Customer Rebates Payable 100.00. The settlement comes off `<SUFFIX>-C06`'s account alone; To settle 30.00. For a customer outside the group it is refused: "That rebate agreement is for a customer group this customer is not in."
- **Leaves:** a group agreement, accrued and part settled.

### TC-SELL-086 — Who agrees a rebate, who settles it, and what it does not do

- **Covers:** backlog 87 row 9 (SG-9), known limits
- **Fixture:** `selling-firm`
- **Also needs:** an accrued agreement with something left to settle whose customer still owes money; an ACTIVE agreement, period over, whose customer sold less than the first slab; a **Sales Manager**, an **Accounts** and a **Read Only** user.
- **Steps:** as **Read Only**: Customer Rebates. As the **Sales Manager**: create an agreement, select the accrued one and look for **Settle against bills**. **(HTTP)** as the Sales Manager, create a `CUSTOMER_REBATE` party adjustment naming the accrued agreement. As **Accounts**: look for Customer Rebates in the menu, then Accounts > All Accounts screens > Books > Party Adjustments. As the **Firm admin**: select the accrued agreement and look for **Settle against bills**; **Accrue** the agreement that reached no slab; Reports > Financial → **Customer rebate statement**.
- **Expect:** Read Only sees the list and the Statement and no New. The Sales Manager (who holds `SALES_APPROVE`) may agree, edit, accrue, reverse and cancel, and is **not offered Settle against bills**: the button is shown on `PARTY_ADJUSTMENT_MANAGE` alone, which is not in that role -- whoever promises a rebate does not move the customer's account. The HTTP request is refused all the same: "You do not have permission to perform this action." The Firm admin is offered the button; of the jobs a firm starts with, Firm Administrator and Firm Manager can settle from the screen. The Accounts job holds the code but cannot open Customer Rebates (it holds no right to view sales), so it settles nothing from that screen; it sees the drafted adjustments under Party Adjustments. Nothing earned is not accrued: "Sales of … reached no slab, so there is nothing to accrue. Cancel the agreement instead." The report lists each agreement with Turnover, Rate %, Earned, Accrued, Settled and Balance. Known limits: a rebate carries no GST and raises no credit note (the *Agreed before the sale* tick is kept for the firm's CA); it accrues once, after the period ends, and is settled only by party adjustment.
- **Leaves:** one more agreement.

---

**Added after the fixes of 2026-10-05 (D-SELL-51)**

### TC-SELL-087 — A bill whose maker has no shift open goes to the approver's shift

- **Covers:** backlog 87 row 7 (SG-7; D-SELL-51, the fallback)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing; a **Counter Sales** user with **no** shift open; a **Sales Manager** with a shift of their own open, float `200`, and no bill in it.
- **Steps:** as the **Counter Sales** user, with **No shift open**: Walk-in, 10 `<SUFFIX>-CTR`, *Received now* 1180 Cash, F9. As the **Sales Manager**: Sell > Sales Invoices → **Approve** the draft; read the strip on New Invoice. Then as the Counter Sales user **Open shift**, float `500`, and raise a second walk-in bill of 1,180.00 in cash; the Sales Manager approves it. Read both strips and Counter Shifts.
- **Expect:** the first bill's maker has no shift, so it lands in the approver's: the Sales Manager's strip reads **1 bill** and **cash expected 1,380.00** (200 + 1,180). The second bill lands in the cashier's shift: **1 bill**, cash expected **1,680.00**; the Sales Manager's shift stays at 1 bill and 1,380.00. Had neither of them a shift open, the bill would approve as always and belong to no shift (TC-SELL-072).
- **Leaves:** two open shifts with one bill each; two approved bills.

---

**Counter bills, coupons, paise and returns after the fixes of 2026-10-05 and 06.** Cases TC-SELL-088 to TC-SELL-095 were added on 2026-10-06. Their expectations were driven over HTTP against a running server; the screens have not been walked. Each stands alone and uses the masters above. A **saved** (draft) or **recalled** (held) counter bill opens with its saved lines and, under them, a table for the products added since, with the same **+ add a product (Ctrl+Enter)** row, scan field and pickers as a new bill. A firm that bills at the counter still has an order and a delivery note behind every bill; they are listed under Sell > Sales Orders and Sell > Delivery Notes.

### TC-SELL-088 — A saved counter bill is cut down, grown and given another product before approval

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-SELL-59, D-SELL-77, SELLQ-12, SELLQ-22
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing (both stages **off**).
- **Steps:** as the fixture's **Firm admin**: (1) New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` quantity **3** → **Save**. Read Inventory for the product, and the newest row of Sell > Sales Orders and Sell > Delivery Notes. (2) **Edit** the draft: quantity **2** → Save; read the same three. (3) Edit: quantity **4** → Save. (4) Edit: on **+ add a product (Ctrl+Enter)** add `<SUFFIX>-DET` quantity **2** → Save. (5) Edit: type a Discount % of **150** on a line → Save. (6) Edit: set the quantity of the `<SUFFIX>-DET` line to **0** → Save. (7) **Approve**. Inventory, Stock Ledger and Journal Entries.
- **Expect:** (1) 354.00, Reserved **3**; an order and a note for 3 stand behind the bill. (2) 236.00, Reserved **2**; the first note and order read **CANCELLED**, "Bill SI-… was changed before approval.", and a new pair carries the 2 (their numbers are spent). (3) 472.00, Reserved 4, a new pair again. (4) the new product is priced as on a new bill (84 less the price list's 2%): total **666.28** (472.00 + 194.28), Reserved 4 of the counter item and 2 of the detergent, and one new note and order hold both lines. (5) refused, and a refused save changes nothing: the bill, its version, the note, the order and the reserved stock are as they were. (6) quantity 0 takes the line off the bill: 472.00 again, the detergent's 2 released. (7) the bill approves for **4**: billed, shipped and out of stock agree. Four leave (`DISPATCH` 4 on the last note); Dr 1100 Trade Receivables 472.00 / Cr 4000 Sales 400.00 / Cr 2220 Output CGST 36.00 / Cr 2230 Output SGST 36.00; cost Dr 5200 Cost of Goods Sold 240.00 / Cr 1200 Inventory 240.00; nothing left reserved. The same edits are taken on a **recalled** held bill, which stays held until it is recalled.
- **Leaves:** an approved bill of 472.00; cancelled orders and notes behind it.

### TC-SELL-089 — A price or a discount changed in a save of its own holds through later edits

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-SELL-77 (SELLQ-28)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: (a) New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` quantity **3**, Discount % **5** → Save. Edit: Discount % **0** → Save. Edit: quantity **4**, nothing else → Save → Approve. (b) New Invoice → the same, quantity **3** at **100** → Save. Edit: rate **90** → Save. Edit: quantity **4**, nothing else → Save → Approve. (c) Edit a draft and press Save without changing anything.
- **Expect:** (a) 336.30, then 354.00, then **472.00**: the 0% typed in its own save holds when the quantity changes (it does not fall back to 5%, which would be 448.40). (b) 354.00, then 318.60, then **424.80**: 4 at the 90 typed earlier, not at 100. After every save the bill line, the note line and the order line agree on quantity, price and discount; each price-only or discount-only save withdraws the pair behind the bill and raises a new one, the old pair reading CANCELLED, "Bill SI-… was changed before approval." (c) a save that changes nothing on the lines raises nothing. The same holds on a bill whose rates include GST (3 at 118 inclusive less 5% is 336.30, at 0% 354.00, then 4 is 472.00, still inclusive).
- **Leaves:** two approved bills.

### TC-SELL-090 — Quantity 0 on a line, and a bill that comes to 0.00

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-SELL-78 (SELLQ-27); the zero-total bill of round 3
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing for (a) to (c); the Sales order and Delivery note stages **on** for (d).
- **Steps:** as the fixture's **Firm admin**: (a) New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` **3** and `<SUFFIX>-SVC` **1** → Save. Edit: quantity of the service line **0** → Save. (b) **(HTTP)** `PUT` a draft counter bill of one line with that line sent back at `current_invoice_quantity` "0"; then with `free_quantity` 1 beside the 0. (c) New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` **3**, Discount % **100** → Save → Approve. Journal Entries; Inventory; Masters > Customers. (d) **(HTTP)** a sales order line, a delivery note line and an invoice line of quantity 0 with nothing free.
- **Expect:** (a) on screen, quantity 0 on a saved line removes it from the bill: 354.00 remains. (b) refused (422) and nothing is written: "Line 1 bills a quantity of 0 and supplies nothing free. Type a quantity, or leave the line off the bill." The bill's version, total, note, order and reserved stock are unchanged. Quantity 0 with 1 free is accepted: nothing billed, one given. (c) a bill that comes to **0.00** approves: it posts no receivable and no journal of its own, the customer's Outstanding does not move, and the goods still leave and are costed (Dr 5200 Cost of Goods Sold 180.00 / Cr 1200 Inventory 180.00). (d) each is refused in the same pattern, naming the line. With the stages on, a delivery note billed at 0.00 leaves the list of notes still to bill.
- **Leaves:** a draft bill and an approved bill of 0.00.

### TC-SELL-091 — Cancelling a draft counter bill withdraws its order and note and frees its stock

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-SELL-54 (SELLQ-17)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` quantity **7** → Save. Inventory. Sell > Sales Invoices → select the draft → **Cancel** with a reason. Inventory, Stock Ledger, Sales Orders, Delivery Notes. Then raise another bill of 7, **Hold (F8)** it, and cancel it while held.
- **Expect:** the draft reserves 7. After the cancel the bill, its delivery note and its order all read **CANCELLED** and nothing is reserved; the Stock Ledger shows `RESERVE` 7 then `UNRESERVE` 7 against the bill's order. A held bill cancelled while held frees its 7 the same way and leaves **Recall**. Cancelling releases only the bill's own reservation: another draft's or another order's stock stays reserved.
- **Leaves:** two cancelled bills.

### TC-SELL-092 — An offer that may be used once, on two draft counter bills

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-SELL-85 (#1224, #1225), D-SELL-86
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing; a promotion of the case's own (Settings > Set up > Pricing > **Promotions** → New): **4%** off, coupon only, code `QAONE`, dated today, **limited to 1 use**. For step (6), the stages **on** and a dispatched delivery note of `<SUFFIX>-C03`.
- **Steps:** as the fixture's **Firm admin**: (1) New Invoice → `<SUFFIX>-C03` → `<SUFFIX>-CTR` **3**, **Coupon** `QAONE` → Save. A second bill the same → Save. **Print** the second draft. (2) **Approve** the first. (3) **Approve** the second. (4) **Edit** the second → Save without changing anything → **Approve**. (5) **Cancel** the first, approved, bill with a reason; raise a third bill with the coupon → Save. (6) With the stages on: New Invoice → *Bill this delivery note* → type the coupon → Create draft.
- **Expect:** (1) both drafts save priced with the offer: **339.84** each (354.00 less 4%). A saved counter bill holds **no** claim on the offer: the claim is made when the bill is approved. The printed draft names the offer under **Offers**. (2) the first approves and claims the one use. (3) the second is refused at approval: "Promotion … has been claimed as often as it allows. Re-save the document to price it without." (where the limit is on the code itself, "Coupon … has been used as often as it allows. …"). (4) saved again it is priced without the offer, **354.00**, and approves. (5) cancelling an **approved** bill does not give the use back, because the goods were delivered: the third draft is priced without the offer, 354.00. (6) refused: "A coupon is applied where the price is set: on the order, or on a bill typed straight in. This bill continues documents already priced, so it cannot take one." A coupon is taken on a counter bill when it is typed and on any later edit, and stays when an edit does not mention it.
- **Data (HTTP):** `GET /api/v1/promotions/reports/redemptions` shows a draft's row **PENDING**, the approved bill's **CLAIMED**, and a cancelled draft's or a withdrawn order's **REVERSED**; `GET /api/v1/promotions/reports/coupons` counts nothing for the code until a bill is approved.
- **Leaves:** approved bills, a cancelled bill, a draft; the offer used up.

### TC-SELL-093 — A walk-in bill whose total is not a whole paisa

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-SELL-83 (#1221, #1225; SELLQ-33)
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; counter billing.
- **Steps:** as the fixture's **Firm admin**: (1) New Invoice → **Walk-in** → `<SUFFIX>-DET` quantity **1** (84 less the price list's 2%, plus 18%: 97.1376). Read *Received now*. (2) Change it to **97.13** → **Save & print (F9)**. (3) Change it to **97.15** → F9. (4) Put **97.14** back → F9. Journal Entries; Sell > Receipts. (5) A second walk-in bill of 1 with **Split payment**: Cash **50.00**, UPI **47.14** → F9. (6) A bill of 1 to `<SUFFIX>-C03` with *Received now* blank → Save → Approve; Sell > Receipts → Record Receipt for 97.15 applied to it, then 97.14.
- **Expect:** (1) *Received now* is pre-filled with the **amount payable**, the total rounded to the paisa: **97.14**. (2) refused, and the bill stays a draft: "A walk-in bill is paid in full at the counter: SI-… comes to 97.14 and 97.13 was received. Take the rest, or bill a customer with a record to sell on credit." (3) refused: "97.15 was received against a bill of 97.14. Enter what the bill is paid with; change is handed back." (4) approves: Dr 1100 Trade Receivables 97.14, and the receipt Dr 1000 Cash 97.14 / Cr 1100 Trade Receivables 97.14; nothing is owed. (5) approves with two receipts; 50.00 + 47.13 and 50.00 + 47.15 are refused in the two wordings above. (6) the customer owes **97.14**; a receipt of 97.15 against the bill is refused, "Invoice … has 97.14 outstanding, so 97.15 cannot be allocated to it."; 97.14 clears it to 0.00.
- **Leaves:** two paid walk-in bills, a paid credit bill, their receipts.

### TC-SELL-094 — A return of goods never billed credits nothing, and the reports say so

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Covers:** D-SELL-80, D-SELL-84 (SELLQ-30, SELLQ-34); the returns-before-billing flavours of round 3
- **Fixture:** `selling-firm`
- **Also needs:** the masters above; the Sales order and Delivery note stages **on**; a GST number on the firm for the GSTR-1 step. For `<SUFFIX>-C03`, all of `<SUFFIX>-CTR` at 100, Discount % `0`: (A) an order of 10, delivered and **billed** (1,180.00, approved); (B) an order of 4, delivered, with **3** billed (354.00, approved); (C) an order of 5, delivered and **never billed**.
- **Steps:** as the fixture's **Firm admin**: Sell > Returns & notes > Sales Returns → New Return: (1) against bill A, quantity **2** → Create draft → Approve → Complete. (2) against **delivery note** B, quantity **2** → Create draft → Approve → Complete. (3) against delivery note C, quantity **5** → Create draft; read Reports > Operational → **Sales return register** and the returns summary; then Approve → Complete and read them again. Then Reports > Financial → **GST sales register**; Masters > Customers; Sell > Sales Invoices → New Invoice → *Bill this delivery note*; GST Returns → GSTR-1.
- **Expect:** (1) credited **236.00**: Dr 4100 Sales Returns 200.00 / Dr 2220 Output CGST 18.00 / Dr 2230 Output SGST 18.00 / Cr 1100 Trade Receivables 236.00, and the cost entry. (2) the unbilled unit is taken first: unbilled quantity **1**, credited **118.00** for the one billed unit, cost entered for both; the return names bill B under *Against invoice*. (3) cost entry only: unbilled quantity **5**, credited **0.00**, no `SR-…` credit journal, and the customer's Outstanding does not move. While return C is a draft it adds its stated total, 590.00, to **pending return value** and nothing to **total return value**; completed, it leaves pending and adds nothing. With all three completed, total return value is **354.00**, equal to the register's credited total. The GST sales register has rows of -200.00 and -100.00 taxable and **no** row for C; GSTR-1 CDNR lists the same two, each against its bill. Delivery note C has nothing left to bill, and note B's left-to-bill is down by the unbilled unit returned. Header charges or rounding on a return that credited nothing add 0 to the summary.
- **Leaves:** three completed returns.

### TC-SELL-095 — Reservations are held batch by batch, and a cancel frees only its own

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** a `pharma-firm`, with the delivery note stage **off** for (a) and (b) and **on** for (c). A batch-tracked product with two in-date batches, an **earlier** and a **later** expiry, 10 each, in the default warehouse, and nothing reserved. A customer.
- **Steps:** (a) Counter bill **A**: the product, quantity **4**, batches untouched → Save. Counter bill **B**: quantity **4**, all 4 on the **later** batch → Save. Stock > Batches. **Cancel** B. Stock > Batches. **Approve** A. (b) Counter bill **C**: quantity **4**, picked **1** earlier + **3** later → Save; Stock > Batches. Raise and approve an ordinary bill or order for the **16** that are left. Approve C. (c) With the delivery note stage on: order **X** for 4 (it holds the earlier batch); order **Y** for 4 with **Batch** = the later batch; approve both. Cancel Y. Stock > Batches. Dispatch X.
- **Expect:** (a) A holds 4 of the earlier batch and B 4 of the later. Cancelling B frees the later batch and leaves A's 4 alone (Stock Ledger: `UNRESERVE` 4 on the later batch against B's order); A approves and ships 4 of the earlier batch. (b) C holds **1** on the earlier batch and **3** on the later, exactly as picked; the other document takes only the rest, and C approves and ships 1 + 3. (c) cancelling Y frees the later batch and nothing else; X dispatches from the earlier batch. An order whose stock is reserved on the batch its customer's minimum shelf life allows dispatches from that batch even while another order holds the earlier one. Cancelling an order while a dispatched note stands against it is refused, as before.



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
  1. As the fixture's **Firm admin**, Settings > Set up > Pricing > **Price Lists** → select `STANDING` (do not open it).
  2. Double-click `STANDING` → **Add product**: `<SUFFIX>-DET`, From qty **25**, Discount % **8** → Save.
  3. Sell > Quotations → New for `<SUFFIX>-C01`, DET qty **30** → Create draft → Revise.
- **Expect**
  - Step 1: the pane reads `STANDING · applies to Everyone`, "In force from 2000-01-01", and three rates for DET: `2%`, `from 15: 4.25%`, `from 18: 6.75%`. Products column 3 (it counts rate rows).
  - Step 2: "Price list saved."; a fourth line `from 25: 8%`.
  - Step 3: "Last priced at **7.5**% by a promotion" — BULK5 outranks the list at 25+.
- **Leaves:** STANDING with a 25 break, in the fixture's store only.

### TC-INCENT-002 — Editing an active promotion makes a new revision

- **Covers:** plan 10.3
- **Fixture:** `selling-firm`
- **Steps:** Settings > Set up > Pricing > **Promotions** → select `BULK5` → Edit → change only the Description → Save. Read the list and the selected row's pane.
- **Expect:** "Promotion BULK5 saved as a new revision; the one you opened is now inactive."; a second BULK5 row appears. The pane reads "BULK5 · revision 2 · applies at 10" and, in the plain English the desktop now words conditions in, "Applies when: Quantity on the line is at least 25". An active offer is superseded, never rewritten — and its claims and limits follow the version group, not the row.
- **Leaves:** BULK5 at revision 2.

### TC-INCENT-003 — Promotion reports count a claim once, at approval

- **Covers:** plan 10.4, 10.5, 10.6
- **Fixture:** `selling-ordered` — one approved order used coupon `WELCOME10`.
- **Steps:** Reports > Operational → **Promotion performance**, **Coupon performance**, **Promotion claims**.
- **Expect**
  - Performance: `WELCOME` with 1 claim; BULK5, BIGORDER and CLEARANCE listed with 0.
  - Coupons: `WELCOME10` with 1 claim; `WELCOME10B` listed at **0** — a code nobody presented is still listed.
  - Claims: one row — WELCOME, coupon WELCOME10, Vijaya Stores <suffix>, SALES_ORDER, the order's number, benefit 25.20, **CLAIMED**.
- **Leaves:** unchanged.

### TC-INCENT-004 — An offer that does not stack ends the stack

- **Covers:** plan 10.7
- **Fixture:** `selling-firm`
- **Steps:** Sell > Sales Orders → New for `<SUFFIX>-C01`: DET **60** at 84 (gross 5,040) → Create draft → Edit. Then Save order unchanged → Edit again.
- **Expect:** under the line's blank box "Last priced at **7.5**% by a promotion" (BULK5); the **Discount on the whole order** box blank with "Last taken off: 200 by a promotion." (BIGORDER). CLEARANCE (1% at 40+, priority 30) did **not** apply: BIGORDER (priority 20) ends the stack. Both survive the unchanged save.
- **Data (HTTP):** the order: `line_discount_total` 378.00, `bill_discount_amount` 200.00 (`bill_discount_source` promotion), grand total 5,265.16.
- **Leaves:** a draft order.

### TC-INCENT-005 — Loyalty: the scheme, a balance, and spending points settles a bill

- **Covers:** plan 10.8, 10.9, 10.10, 10.11
- **Fixture:** `loyalty-points`
- **Steps**
  1. Settings > Set up > Pricing > **Loyalty**. Reports > Financial → **Loyalty balances**.
  2. Sell > Sales Invoices → select Vijaya's approved invoice → **Use points** → 100 → **Use them**.
  3. Accounts > Journal Entries → the top `LOY-RED-SI-…` → View. Masters > Customers → C01.
  4. Use points again, 5000.
  5. Reports > Operational → **Points about to lapse**.
- **Expect**
  - Step 1: the banner "2 points per 100, worth 1 each and expire after 24 months. At least 50 before any can be spent."; the balances report lists Vijaya with **200** points worth 200.00 — **more if your build ran the loyalty scheme setup before approving her invoices**: points are earned at approval, not credited afterward, so an invoice approved while the scheme was already on adds its own 2 per 100 on top of the 200 credited here.
  - Step 2: "100 points used on SI-…".
  - Step 3: Dr **2600 Loyalty Payable 100.00** / Cr **1100 Trade Receivables 100.00**. Outstanding **383.21** — 100 lower; the invoice's total and tax unchanged: the bill is **settled**, not discounted.
  - Step 4: refused outright: "That customer holds 100.0000 points, not 5000.0000." No journal.
  - Step 5: **empty** — nothing in this store is within 90 days of lapsing. *(WHOLE01's aged batches, and the oldest-first spending they showed, need points two years old; a fixture cannot age them.)*
- **Leaves:** 100 points spent.

### TC-INCENT-006 — Commission blends rates per line, and a ladder's floor is a round number

- **Covers:** plan 10.12, 10.13
- **Fixture:** `commission-firm`
- **Steps:** as the fixture's **Firm admin**, Sell > All Sell screens > Incentives > **Commission** → **Collected** view, from `2026-04-01` to the end of this month → **Show**. Then Sell > All Sell screens > Incentives > **Targets** → **Achievement** for this month.
- **Expect**
  - **Asha**: collected **5,900.00**, commission **495.60** — 15% of 2,360 on `-P` plus 4% of 3,540 on everything else: **8.4%**, neither of the two rates that govern her. Target **Met**.
  - **Bala**: collected **4,720.00**, commission **94.40** — exactly **2.00%**, the bottom band; above the 1,000 floor; target **Missed**, so no bonus.
  - Achievement: Asha 1,000 target achieved; Bala 100,000 wanted, 4,720 invoiced (4.72%), 95,280 short.
- **Data (HTTP):** `GET /api/v1/commission/report?from_date=2026-04-01&to_date=<month end>`; `GET /api/v1/sales-targets/achievement?from_date=…&to_date=…`. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §17.10, §17.11 and §17.16 in the fixture's own schema — both reads write nothing and are recomputed every time: the report walks `settlement_allocations` per receipt date and resolves the rule per row, the achievement sums each target over its own dates. A `measure` of MARGIN sent to a rule is dropped (D-TER-1), a credit note takes nothing off either figure (D-TER-3), and two targets over the same days count the same sales twice (D-TER-2).
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §17.12 to §17.14 — accrual inserts one DRAFT `commission_payouts` row per earner with the report's figures snapshotted and **no journal** (audit `commission.payout.accrued`); approval posts `COMM-<yyyymm>-<id8>` dated `accrued_on` — the period's last day, so a date that has not arrived when the month is accrued early (D-TER-6); payment posts `…-PAY` against whatever account and date are sent (D-TER-5); cancelling a draft posts nothing and an approved one posts `…-REV`. The query in §17.12 shows the payout beside both journals.
- **Leaves:** Bala paid, Asha cancelled.

### TC-INCENT-008 — Whoever states a debt must not move the cash

- **Covers:** plan 10.15
- **Fixture:** `commission-firm`
- **Steps:** sign in as the fixture's **Asha** (`SALES_EXECUTIVE`), expand Sales. **(HTTP)** as Asha: `GET /api/v1/commission/payouts`; `POST /api/v1/commission/payouts/{any id}/approve` and `/pay`.
- **Expect:** no Commission, Targets, Price Lists or Promotions under Sales. All three calls **403**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §17.13 and §17.14 — the three refusals write nothing. `COMMISSION_PAY` is its own code and `SALES_MANAGER` holds neither it nor `COMMISSION_MANAGE`; `ACCOUNTANT` and `FIRM_ADMIN` hold both, and nothing compares the actor with the payout's own salesperson (D-TER-4).
- **Leaves:** unchanged.

### TC-INCENT-009 — Buy X get Y at a discount, and a combo price

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog SEL-2 (A94), SEL-3 (A96)
- **Fixture:** `selling-firm`
- **Also needs:** a second product `<SUFFIX>-Q` priced like DET (create one), so a combo has two items.
- **Steps:** as the fixture's **Firm admin**: Settings > Set up > Pricing > **Promotions** → New. (a) Benefit *Buy X get Y at a discount*: buy 2, get 1 at **50%**, optional cap amount. Save and activate. Sell > Quotations → New for Vijaya → `<SUFFIX>-DET` × 3, then × 6, then × 1. (b) New promotion, benefit *Combo price*: pick DET and `-Q` in the product pick, amount **150** for the set. Activate. A quotation with DET × 2 and Q × 2, then DET × 2 and Q × 1.
- **Expect:** (a) the discount is on **whole groups only**: 3 units make one group (the third unit at half price of what that unit has left after other discounts), 6 make two, 1 makes none; a cap limits the total and is shared across the lines in proportion. (b) each **complete set** across the lines sells for the combo amount and the saving (the sets' normal value less 150) is spread across the lines by value; DET × 2 with Q × 2 is two sets, DET × 2 with Q × 1 is one set and the leftover DET is at its normal price. The offer editor shows the benefit and its fields.
- **Leaves:** two promotions, quotations.

### TC-INCENT-010 — Bonus loyalty points, customer history and day-and-time conditions

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog SEL-4 (A73), SEL-6 (A98), SEL-7 (A72)
- **Fixture:** `loyalty-points`
- **Steps:** as the fixture's **Firm admin**: Settings > Set up > Pricing > **Promotions** → New *Bonus loyalty points* with a multiplier of **3** (the benefit stands alone on its offer), dated today. Raise and approve a bill for Vijaya and read her balance (Settings > Set up > Pricing > Loyalty). Try a multiplier of 11 or 0. Next, New promotion with a 5% discount and the condition **Customer order count** = 0 (first order), another with **Days since last order** = 30. Then New promotion 5% with **Days of the week** = Sat and Sun, and another with **Time of day** between 16:00 and 18:00. Try a time window crossing midnight, and a weekday outside 1-7 through the API. Quote a bill on a weekday morning, on a Saturday, and inside the window.
- **Expect:** an approved bill earns points at the scheme's rate **times the largest multiplier** among the live points offers whose conditions hold on the bill's date; the audit row names the offer and the multiplier; the offer is passed over by the discount engine with a trace note. A multiplier outside 1-10 is refused. Order-count and days-since-last-order conditions are tested against the customer's approved and closed bills on or before the date (a customer with none has count 0). Weekend-only and time-window offers apply only inside their day or window (time is India time, taken from the quotation's or order's own creation time); a window that crosses midnight and a weekday outside 1-7 are refused when the condition is written.
- **Leaves:** promotions, points earned.

### TC-INCENT-011 — Bulk coupon codes, and copying an offer with new dates

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog SEL-5 (A70), SEL-8 (A71)
- **Fixture:** `selling-firm`
- **Steps:** as the fixture's **Firm admin**: Settings > Set up > Pricing > **Promotions** → open the coupon-only offer **WELCOME** → coupons → **Generate codes**: count 50, prefix `DIWALI`, a description and a window → Generate; then ask for 6,000. **Export codes**. Use one code on a quotation twice, and for a second customer. Back on the grid select WELCOME → **Copy with new dates...** with a code suffix `-NOV` and a new window.
- **Expect:** 50 random codes `DIWALI-XXXXXXXX` are made from an alphabet without look-alike characters, each usable **once** and once per customer, all or nothing; 6,000 is refused (limit 5,000). The export is a CSV of the offer's codes with their uses. A code already used cannot be redeemed again. The copy is a **DRAFT** at version one with code `…-NOV`, the same conditions and benefits and the new window; its coupons are **not** copied; the audit trail has *promotion.copied* naming the source. The grid selects one offer at a time (the API takes up to 100).
- **Leaves:** 50 coupons, a draft offer.

### TC-INCENT-012 — Claims to the principal

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog SEL-11, A128
- **Fixture:** `selling-invoiced`
- **Also needs:** a principal (Settings > Set up > Item lists > Principals) and a brand under it on `<SUFFIX>-DET`; a promotion the principal funds (principal and **share %** on the promotion editor) that was claimed on an approved bill; an expiry write-off of a DET batch; a sales return of DET completed with damaged goods. A vendor to be the principal's supplier account.
- **Steps:** as the fixture's **Firm admin**: Buy > All Buy screens > Money > **Principal Claims** → New → pick the principal and the period → Preview. Raise the claim. Raise it again for the same period. Then record the principal's **credit note** (Accounts > All Accounts screens > Books > Party Adjustments, kind *Principal claim*) against it, and a payment into the bank for the rest. Reverse one receipt. Cancel the claim in a second run and raise it again. Print.
- **Expect:** the preview gathers each source **once**: scheme redemptions (at the principal's share of the benefit), expiry write-offs of its products (at book value) and damaged or scrapped lines of completed sales returns (at the taxable rate credited). Raising posts Dr *Claims Receivable from Principals* and Cr promotional expense (schemes) or inventory adjustment (stock). A second claim over the same sources is refused or empty (one live claim per source). Settlement by credit note and by bank payment moves the status RAISED → PART_SETTLED → SETTLED; reversing a receipt moves it back. Cancelling frees the sources to be claimed again. Reading needs PURCHASE_VIEW, writing PURCHASE_APPROVE. Free quantity on a bill line is not claimed yet.
- **Leaves:** a claim and its postings.


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
  1. Settings > Set up > Territories & routes > **Territories**; select any row; the right-hand **Territory tree** → **Expand all**. Click the icon beside its title ("Open the tree in a larger window"); try Collapse all / Expand all; Close.
  2. Double-click `<SUFFIX>-R-N1` → **Details**; then **Customers** and **Salespeople**.
- **Expect**
  - Step 1: Chennai Region (Region) → North Zone and South Zone (Territory) → North Sales Beat and North Collections under North, South Sales Beat under South (Route), each node with its code and full path; the grid's Hierarchy column carries the path.
  - Step 2: **Route** section: Route type **Sales Route**, Visit frequency **Weekly**, Working days **Mon, Wed, Fri**, Runs from **Always**, Runs until **No end**. 2 customers, both active; Salespeople 1. Customers: Revise Check, Classic Stores. Salespeople: Asha Sales.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §17.2 and §17.5 in the fixture's own schema (`fx_<suffix>_t`) — reads only. A route is a `sales_territories` row with a live `territory_route_profiles` row and its `territory_working_days`; the query in §17.2 shows all three, and §17.5's the salespeople beside their membership.
- **Leaves:** unchanged.

### TC-TERR-002 — A call list for a Monday, with reasons for every plan that does not run

- **Covers:** plan 11.3
- **Fixture:** `territory-firm`
- **Steps:** Sell > All Sell screens > Field sales > **Call Lists**. Move to **Monday 2026-09-21** (› Next day or the date button), Salesperson Everyone. Then **Back to today**.
- **Expect:** the date button reads "Monday 2026-09-21"; the status bar "1 of 9 plan(s) run on Monday 2026-09-21". `-BP-R1-MON` is badged **Runs on Monday** and calls Revise Check then Classic Stores (the route's round, in order). Every other plan is **Not on Monday** with its reason — e.g. `-BP-R1-FRI` "Runs on Fridays; this is a Monday."
- **Data (HTTP):** `GET /api/v1/sales-territories/call-lists?date=2026-09-21` → nine `entries`, one with `occurs: true`. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §17.6 and §17.7 — a call list is computed from `sales_beat_plans`, the route profile's window and working days and `territory_customer_assignments`, and **writes nothing**.
- **Leaves:** unchanged.

### TC-TERR-003 — Fortnightly and monthly plans, and why they skip a week

- **Covers:** plan 11.4
- **Fixture:** `territory-firm`
- **Steps:** Call Lists: date **2027-01-12**, then **2026-10-13**, then **2026-10-20**.
- **Expect**
  - 2027-01-12 (a second Tuesday and an even fortnight from 2026-04-07): "4 of 9 plan(s) run" — `-R2-TUE` and `-COLL` (both Vijaya), `-R3-TUE` and `-MTH` (both Anand).
  - 2026-10-13 (second Tuesday, off fortnight): `-COLL` **Not on Tuesday**, "Runs every other Tuesday counted from 2026-04-07; this is the week between."; `-MTH` runs.
  - 2026-10-20 (third Tuesday): `-COLL` runs; `-MTH` "Runs on the second Tuesday of the month; this is the third."
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §17.6 and §17.7 — reads only; `weekday`, `week_of_month` and `starts_on` on `sales_beat_plans` are the whole recurrence, and the query in §17.6 shows them.
- **Leaves:** unchanged.

### TC-TERR-004 — Building a round, and saving one unchanged

- **Covers:** plan 11.5, 11.6
- **Fixture:** `territory-firm`
- **Steps**
  1. Settings > Set up > Territories & routes > **Route Builder** → Route being built `<SUFFIX>-R-N1` (right: 1. Revise Check, 2. Classic Stores). Tick **On no route yet** → **Find** → double-click `<SUFFIX>-SN` (stop 3) → drag it by ≡ above the first stop → **Save round and order**. Choose the route again.
  2. **Remove from round** on SN → Save. Then choose N1 again, change nothing → Save.
- **Expect**
  - Step 1: "3 outlet(s) on North Sales Beat, in order."; reopened: 1. SN, 2. Revise Check, 3. Classic Stores — the stops moved without a collision.
  - Step 2: "2 outlet(s) on North Sales Beat, in order." both times; the same two stops in the same order. The status bar says "Saving replaces the whole round with the list on the right." — which is why the screen refuses to save a round it could not read.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §17.4 — each save replaces the node's whole list: a shop left out is soft-deleted, one brought back has its old row un-deleted, and every stop number about to move is set to NULL and flushed before the new ones are written, which is why the swap does not collide. One `sales_territory.customers_set` per save, carrying a count only. A shop that was primary here and has since become primary elsewhere is refused back with a bare 409 (D-TER-10).
- **Leaves:** N1's round as the fixture made it.

### TC-TERR-005 — A salesperson must cover the customer's route

- **Covers:** plan 11.7
- **Fixture:** `territory-firm`
- **Steps:** Sell > Sales Orders → **New Order** for `<SUFFIX>-C4` (Anand, on S1, covered by Asha): ships from MAIN, **Salesman Bala**, one line `<SUFFIX>-P` qty 1 → Create draft. Then Asha → Create draft. Then Salesman blank → Create draft → reopen.
- **Expect:** Bala is refused in the editor's banner: "The selected salesperson is not assigned to this territory." — nothing saved. Asha saves. Blank saves and, reopened, the salesman is **Asha**, supplied by the customer's route.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §17.8 — `resolve_sales_scope` writes `territory_id`, `route_id` and `salesman_id` on the order and nothing else; the refusal writes nothing. A blank route is judged on the order's own date; a route the caller names is kept as sent (D-TER-9), and a derived salesperson is not checked for membership (D-TER-11).
- **Leaves:** two draft orders.

### TC-TERR-006 — Loading places from India Post (B6)

*Added 2026-10-02 (decision B6).*

- **Preconditions:** signed in as the platform administrator with a firm selected. Since migration `20261002_0231` every firm store already holds the seven southern states' places: first open a customer address on a fresh install and type PIN **600001** (Chennai) -- it must fill without any loading. Then delete nothing and continue.
- **Steps:** open the geography screen → **Load places from India Post...**. Look at which states are ticked. Untick all but **Lakshadweep** and **Load**. Then open a customer address and type PIN **682554**. Run the load again for Lakshadweep.
- **Expect:** the seven southern states are ticked by default, each showing its PIN codes and post offices; the source line names India Post and data.gov.in. The Lakshadweep load reports 1 district, 9 towns, 9 PIN codes and 10 localities. PIN 682554 offers town **Chetlat**, district **Lakshadweep District**, state Lakshadweep, and localities Bithra and Chetlat. The second load adds nothing and the counts stay the same.


### Known defects found while writing these cases

- **D-11-1 — A new firm's territory hierarchy was not saved until somebody saved it, and reading it invented ids. Fixed 2026-09-16.** `GET /api/v1/sales-territories/hierarchy-levels` on a fresh store answered REGION / TERRITORY / ROUTE with a **different config id and level ids on every read** — defaults built, flushed and never committed. Creating a territory against one of those ids was refused "Configured hierarchy level is not active.", which reads as a configuration problem and was really a row that was never written; saving the hierarchy unchanged made it work, which is why it survived — anybody who pressed Save once never met it again. `_ensure_hierarchy_config` now commits the defaults it invents, following the create-if-missing shape provisioning already uses. `test_a_new_firms_hierarchy_is_written_by_the_read_that_invents_it` in `tests/unit/test_sales_territory_policies.py`.

---

## Compliance — GST returns, e-invoices and TCS

A GST return is **derived on every read**, never stored: cancel an invoice and
it drops out. E-invoices and e-way bills go to a **sandbox** that marks every
reference it mints `SBX…`. E-Invoice, GST Returns and TCS are under **Sales**.

| Fixture | Starts you with |
| --- | --- |
| `compliance-firm` | a firm with GSTIN `33…` (Tamil Nadu); **`<SUFFIX>-B2B`** Registered Buyer with a GSTIN; **`<SUFFIX>-B2C`** Walk-in Buyer with none; `<SUFFIX>-P` at HSN **340220**, GST 18 local. This month: **Invoice A** — B2B, 10 × 100 (1,180.00), **collected and e-registered**; **Invoice B** — B2B, 5 × 100 (590.00), unpaid, **e-registered, no e-way bill**; **Invoice C** — B2C, 3 × 100 (354.00), unpaid, not registered |
| `selling-paid` | (see *Selling*) two receipts from Vijaya, who has no PAN, dated after 1 April 2025 and so charged no TCS |

### TC-COMP-001 — GSTR-1 for the month

- **Covers:** plan 12.1
- **Fixture:** `compliance-firm`
- **Steps:** as the fixture's **Firm admin**, Accounts > **GST Returns** → this month (the From/To boxes are chosen, not typed) → **GSTR-1**.
- **Expect:** "Filing as <the firm's GSTIN>". **B2B**: Invoice A — taxable 1,000.00, CGST 90.00, SGST 90.00 — and Invoice B — 500.00, 45.00, 45.00 — under the buyer's GSTIN. **B2CS**: one row, Place **33**, 18%, taxable 300.00, CGST 27.00, SGST 27.00 — never a blank place. **CDNR**: nothing. **HSN**: 340220, quantity 18, taxable 1,800.00. **Invoices without a place of supply**: "Nothing in this section." The status bar: "Derived from the documents on every read, never stored."
- **Data (HTTP):** `GET /api/v1/gst-returns/gstr1?from_date=<first>&to_date=<last>`. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §13.6 in `fx_<suffix>_g` — the return is not stored and the read writes nothing, not even an audit row; its query lists the approved bills, their buyers' GSTINs and the CGST/SGST rows it is built from. A sales return would not show here (D-CMP-2).
- **Leaves:** unchanged.

### TC-COMP-002 — What rests on a bill stops it being cancelled; a return follows what is left

- **Covers:** plan 12.2
- **Fixture:** `compliance-firm`
- **Steps**
  1. Sell > Sales Invoices → **Invoice A** → **Cancel**.
  2. **Invoice C** → **Cancel** (give a reason). GST Returns → Refresh.
- **Expect**
  - Step 1: refused, naming what rests on it: "SI-… cannot be cancelled while it has money applied from RC-…; its registration with the tax authority. Reverse or cancel those first."
  - Step 2: C cancels. The **B2CS row is gone** and HSN falls to quantity 15, taxable 1,500.00. *(The plan's second refusal — by a sales return — is TC-SELL-015's return in reverse; this fixture has none.)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §13.8 and §13.6 — the refusal writes nothing and A's `einvoice_registrations` row stays REGISTERED; C's cancel is the §11.12 cancellation (receivable `CREDIT_NOTE`, the journal reversed, `sales_invoice.cancelled`) and the return drops it because it reads `status`, not because anything was written to it. `docs` then counts 2 bills with no cancelled column (D-CMP-10).
- **Leaves:** Invoice C cancelled.

### TC-COMP-003 — GSTR-3B agrees with GSTR-1

- **Covers:** plan 12.3
- **Fixture:** `compliance-firm`
- **Steps:** GST Returns → **GSTR-3B**, same month. Add GSTR-1's B2B, B2CS and CDNR taxable values by hand.
- **Expect:** **3.1(a)** taxable **1,800.00**, CGST 162.00, SGST 162.00 — equal to GSTR-1's sum; credit notes deducted 0; the inward side reads "Not derived: the purchase side files this." 3B is aggregated from the documents, not parsed out of GSTR-1.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §13.7 — nothing stored; its query sums 2200 for the same days, which should read 324.00 (162.00 + 162.00). After a sales return the two part (D-CMP-2), and on bills whose halves end in half a paisa they differ by 0.01 a bill (D-CMP-4).
- **Leaves:** unchanged.

### TC-COMP-004 — The e-invoice screen says it is a rehearsal

- **Covers:** plan 12.4
- **Fixture:** `compliance-firm`
- **Steps:** Accounts > All Accounts screens > Tax filing > **E-Invoice**.
- **Expect:** a banner, "References marked sandbox are a rehearsal: nothing was filed with the tax authority..."; columns Invoice, Customer, Reference, E-way bill; **two** rows (A and B), each Reference an `SBX…` value (hover for `SBX… (sandbox — nothing filed)`), E-way bill —. If anything reads LIVE, stop.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §13.8 — two `einvoice_registrations` rows, `mode` SANDBOX, `status` REGISTERED, `irn` and `acknowledgement_number` beginning `SBX`, `attempts` 1, the payload in `request_payload`, one `einvoice.registered` audit row each; no `eway_bills` row yet.
- **Leaves:** unchanged.

### TC-COMP-005 — An invoice to a buyer with no GSTIN is refused locally

- **Covers:** plan 12.5
- **Fixture:** `compliance-firm`
- **Steps:** E-Invoice → **Register an invoice** → **Invoice C** (items read `SI-… — Walk-in Buyer <suffix> — 354.00`) → Register.
- **Expect:** refused **locally**, in an error toast: "This invoice cannot be registered yet: the customer has no GST number." No row added, no portal code.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §13.8 — the refusal writes nothing: no `einvoice_registrations` row for C and no audit row, not even `einvoice.refused` (that one is written only when the portal itself refuses).
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §13.10 — the refused blank-vehicle attempt writes nothing; the raise inserts one `eway_bills` row (`mode` SANDBOX, `status` GENERATED, `eway_bill_number` `SBX…`, `valid_until` today + 1 day for 120 km, `vehicle_number` TN01AB1234) and audit `eway_bill.generated`; the withdrawal sets CANCELLED, `cancelled_at`, `cancellation_reason`, `version` 2 and writes `eway_bill.cancelled`. Step 3 writes nothing. Withdrawing B's **registration** while its bill is GENERATED is not refused (D-CMP-5).
- **Leaves:** a withdrawn e-way bill on B.

### TC-COMP-007 — TCS: the settings stay, and nothing is collected from 1 April 2025

- **Covers:** plan 12.7, 12.8
- **Fixture:** `selling-paid`
- **Steps:** as the fixture's **Firm admin**, Accounts > All Accounts screens > Tax filing > **TCS**; open **Settings** (close without saving). Accounts > Journal Entries → search `TCS-RC`.
- **Expect**
  - The register is **empty**: both receipts are dated after 1 April 2025, when the Finance Act 2025 omitted section 206C(1H), so neither was charged. *(Checked on 2026-10-05: `tcs_collections` holds no row for the two receipts and the ledger has no 2500 TCS Payable line.)*
  - Settings still read as the firm keyed them: **Collect under section 206C(1H)** on; preceding year turnover 150,000,000; threshold 0; rate 0.1; without a PAN 1.0. Switching it on does not bring the tax back.
  - Journal Entries: no `TCS-RC-…` entry. A receipt dated **before** 1 April 2025 would raise one of its own, **Dr 1100 Trade Receivables / Cr 2500 TCS Payable**; a firm whose books open in 2026-27 cannot date one there, so that half is covered by the unit suite (`tests/unit/test_tcs.py`) rather than by hand.
- **Data (HTTP):** `GET /api/v1/tcs/collections` → no rows. Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §13.11 in `fx_<suffix>_s` — `tcs_collections` empty and no line on 2500; closing Settings without saving writes nothing (a save would write `tcs.settings_changed`). Checked 2026-10-05 on `fx_t1005j1us_s`.
- **Leaves:** unchanged.

---

### TC-COMP-008 — The tax calendar on Home, and marking a return filed

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog 63 row 4
- **Fixture:** `compliance-firm`
- **Also needs:** the fixture's invoices are dated this month, so the calendar's rows are for the month just gone only if the firm traded then; if the list reads "Nothing due.", use a firm with last month's invoices.
- **Steps:** as the fixture's **Firm admin**, Home → **Tax calendar**. On a GSTR-1 row choose to record it as filed, with a date and an acknowledgement number. Then withdraw it (Undo). Record a GST payment for the month and look again.
- **Expect:** one row per return per finished month (GSTR-1 due the 11th, GSTR-3B the 20th; a TCS deposit row only for a month that collected tax at source), each reading due in N days, N days late or Filed on a date. Marking GSTR-1 filed turns its row to Filed and nothing else moves; Undo puts it back. GSTR-3B closes once a GST payment is recorded for the month. A TCS row has no record button. A role that may not open GST Payment does not see the card.
- **Leaves:** a filing record, unless withdrawn.

### TC-COMP-009 — Filing e-invoices offline (no GSP)

*Added 2026-10-02 (decision A42).*

- **Preconditions:** a GST-registered firm with two approved B2B invoices to registered buyers, not yet registered.
- **Steps:** Settings > Tax > **GST Documents** → *E-invoice filing* → **Offline** → Save. Accounts > All Accounts screens > Tax filing > E-Invoice → **Export for portal** → tick both → save the JSON file. Open it. Then **Import portal result** with a JSON file shaped like the portal's answer (for each invoice: `DocDtls.No` the invoice number, `Irn`, `AckNo`, `AckDt`, `SignedQRCode`; give the second invoice no `Irn` and an `ErrorDetails` text). Then try **Register** on a third approved invoice.
- **Expect:** the export holds one object per invoice in the portal's schema (`Version`, `TranDtls`, `DocDtls`, `SellerDtls`, `BuyerDtls`, `ItemList`, `ValDtls`), and both invoices show **PENDING**, mode **LIVE**, route **OFFLINE**. After the import the first is **REGISTERED** with that IRN and acknowledgement, the second **FAILED** with the error text, and the message counts 1 registered, 1 refused. Register on the third comes back refused with directions to export it instead.

### TC-COMP-010 — E-way bills without an IRN, on a challan, and by hand

*Added 2026-10-02 (backlog 77 rows 9-10).*

- **Preconditions:** a firm with no *e-invoicing applies* date; Settings > Tax > GST Documents → *E-way bill needed above* **1,000**. An approved invoice worth more than 1,000 without an e-way bill; an approved **Job work** delivery note that no invoice bills; a second approved invoice.
- **Steps:** Accounts > All Accounts screens > Tax filing > E-Invoice → **E-way bills due**. Raise the first invoice's e-way bill (distance 120, road, a vehicle). Raise the job-work note's. On the second invoice choose **Record e-way bill...**: number `3510 1234 5678`. Then set an *e-invoicing applies* date in the past and try to raise an e-way bill on a new, unregistered B2B invoice. Dispatch a delivery note worth more than 1,000.
- **Expect:** the due list shows the invoices and the note with the limit 1,000. The first invoice's bill is raised without an IRN; the note's bill carries supply type **Job work**; the recorded one shows `351012345678`, marked as entered by hand. Each leaves the due list. With e-invoicing on, the unregistered invoice is refused: "Register the invoice before raising its e-way bill". Dispatching the note prompts to raise its e-way bill.

### TC-COMP-011 — Registering a credit note and a debit note

*Added 2026-10-02 (backlog 77 row 4).*

- **Preconditions:** a GST-registered firm on the **Sandbox** route; an approved, registered B2B invoice of 1,000 + 18% GST; an approved credit note of 200 + 36 against it, and an approved debit note to the customer of 100 + 18.
- **Steps:** Sell > Returns & notes > Credit Notes → the note → **E-invoice** → **Register**. The same on the debit note. Accounts > All Accounts screens > Tax filing > E-Invoice: look at the list. Switch the firm to **Offline**, raise another credit note, and **Export for portal** with an invoice and that note ticked; open the file.
- **Expect:** each note registers with an `SBX` IRN and shows mode **SANDBOX**; the list shows them as *Credit note* and *Debit note* with their own numbers. The exported file holds the invoice (`Typ` INV) and the note (`Typ` CRN) whose `RefDtls` names the invoice it corrects, CGST and SGST each 18.00 on the 200.
---

### TC-COMP-012 — The IRN and QR on the printed documents

*Added 2026-10-02 (backlog 77 row 11).*

- **Preconditions:** TC-COMP-011 done: a registered invoice, a registered credit note and a registered debit note; plus one approved invoice never registered.
- **Steps:** Print each of the four. Withdraw the invoice's registration (inside 24 hours) and print it again.
- **Expect:** the three registered documents carry an **E-INVOICE** box under the title with the IRN, Ack No. and Ack Date and a QR code; scanning the QR returns the signed text. The credit note is titled **CREDIT NOTE**, names "Against invoice" with the invoice number and date and the reason, and splits its tax into CGST and SGST as the invoice did. The unregistered invoice and the withdrawn one print with no box.

### TC-COMP-013 — Rule 37: a bill unpaid 180 days

*Added 2026-10-02 (backlog 78 row 4).*

- **Preconditions:** an approved supplier bill of 400 + 18% local GST (CGST 36, SGST 36) dated more than 180 days ago, nothing paid; Settings > Tax > GST Documents, *180-day unpaid bills* on **Report and post**.
- **Steps:** Accounts > All Accounts screens > Tax filing > Rule 37 (180 days), as of today. **Post reversals and reclaims.** Open the trial balance and GSTR-3B for this month. Pay the bill in full. Back to Rule 37, post again; GSTR-3B for that month.
- **Expect:** the bill is listed to REVERSE CGST 36 and SGST 36. After posting the list is empty, input tax is down 72 and *Input Tax Not Claimable* up 72, and 3B shows 72 in 4(B)(2), "of which rule 37" 72. After payment the bill is listed to RECLAIM 72; once posted the books are back, and that month's 3B shows the 72 in 4(A)(5) and in 4(D)(1). With the setting on **Report only**, the list shows but posting is refused with the reason.

### TC-COMP-014 — The supplier's IRN on a bill

*Added 2026-10-02 (backlog 78 row 5).*

- **Preconditions:** a supplier with a GSTIN; Settings > Tax > GST Documents, *Supplier bill without an IRN* on **Warn** (the default).
- **Steps:** Open the supplier, tick **Supplier e-invoices**, save. Enter a bill from it with no IRN and save. Type `IRN-123` in the IRN box. Then type a 64-character IRN (e.g. 64 `a`s) and save. Approve it; **Record IRN** on the approved bill, clear it, record it again. Enter a second bill from the same supplier carrying the same IRN. Set the setting to **Off** and reopen a bill with no IRN.
- **Expect:** the first save shows the warning that the supplier e-invoices and the bill has no IRN (rule 48(4)); `IRN-123` is refused as not 64 letters and digits; with the IRN the warning goes. On the approved bill the IRN can be recorded and cleared, and the audit trail shows each change. The second bill warns that the first bill already carries this IRN. With the setting Off the missing-IRN warning is not shown (the duplicate warning still is).

### TC-COMP-015 — The e-way bill on a goods receipt

*Added 2026-10-02 (backlog 78 row 6).*

- **Preconditions:** Settings > Tax > GST Documents, e-way bill limit **50,000**; an approved purchase order worth more than 50,000 from a supplier with a GSTIN, and a second from a supplier with none.
- **Steps:** Receive the first order with no e-way bill number and save. Type `EWB-1` in the e-way bill box. Type `3312 3456 7890` and a date, and save. Complete the receipt; **Record e-way bill**, clear it, record it again. Receive the second order with no number.
- **Expect:** the first save warns that goods worth more than 50,000 need an e-way bill and none is recorded (rule 138), asking for the supplier's number; `EWB-1` is refused as not 12 digits; with the number the warning goes and it is stored as `331234567890`. On the completed receipt the number can be recorded and cleared, and the audit trail shows each change. The unregistered supplier's receipt warns that the e-way bill is yours to raise. A receipt under 50,000 shows no warning.

### TC-COMP-016 — No print or email of a B2B invoice without its IRN

*Added 2026-10-02 (backlog 77 row 6, decision A43).*

- **Preconditions:** a GST-registered firm on the **Sandbox** route with *E-invoicing applies from* set to a day in the past (Settings > Tax > GST Documents). An approved invoice dated on or after that day to a buyer **with** a GSTIN, not registered; an approved invoice to a buyer **without** a GSTIN; an approved credit note against the first invoice, not registered. Messaging switched on with an email channel that can send.
- **Steps:** (a) Sell > Sales Invoices → the B2B invoice → **Print**. Read the dialog, choose **Cancel**; Print again and choose **Print reference copy**. (b) **Send** it by email. (c) Print the consumer's invoice. (d) Print the credit note. (e) Accounts > All Accounts screens > Tax filing > E-Invoice → register the B2B invoice, then Print and Send it again.
- **Expect:** (a) a *No IRN yet* dialog: "<number> has no IRN yet. The firm e-invoices from <date> and the buyer is registered for GST, so it is not a valid tax invoice until it is registered on the portal (CGST rule 48(4)). Register it under E-invoice first, or print a reference copy marked not valid." Cancel prints nothing; the reference copy prints with **NO IRN YET - NOT A VALID TAX INVOICE** across its top. (b) the email is refused with the same sentence. (c) the consumer's bill prints as before, with no dialog. (d) the credit note is refused the same way, naming its own number. (e) once registered the invoice prints with its IRN box and no banner, and the email is accepted. A WhatsApp or SMS send is never held.

### TC-COMP-017 — The automatic invoice email waits for the IRN

*Added 2026-10-02 (backlog 77 row 6, decision A43).*

- **Preconditions:** TC-COMP-016's firm; Settings > Firm > Messaging → *Events*: *Invoice approved* on, by email; a B2B customer with an email address.
- **Steps:** Approve a new invoice to that customer. After the next messaging pass, Settings > Firm > Messaging → **Message log**. Then Accounts > All Accounts screens > Tax filing > E-Invoice → register the invoice; wait at least five minutes and look at the log again.
- **Expect:** the row stays **Queued** with the Reason "Waiting for <number>'s IRN: it goes out on the first pass after the invoice is registered on the portal." Nothing is sent and Tries does not climb. After registration the row is sent on the next pass (looked at again every 5 minutes) with the registered invoice attached -- one email, not two. Other queued messages keep going out while it waits.

### TC-COMP-018 — The 30-day limit and the To register list

*Added 2026-10-02 (backlog 77 row 7, decision A44).*

- **Preconditions:** TC-COMP-016's firm, *30-day reporting limit applies from* set to a day in the past (not before the e-invoicing date). Three approved B2B invoices, not registered: one dated 35 days ago, one dated 27 days ago, one dated today.
- **Steps:** Accounts > All Accounts screens > Tax filing > E-Invoice → **To register**. Choose **Register** on the 27-day-old invoice. Try to register the 35-day-old one from **Register an invoice** (and, on the Offline route, by **Export for portal**). Clear the *30-day reporting limit* date, Save, and open **To register** again.
- **Expect:** the list shows every approved B2B document without an IRN, oldest first, with Document, Number, Date, Customer, Amount, **Last day** (date + 30), **Days left** and Status: the 35-day-old one **Late**, with no Register button and the note "A late document cannot be registered: cancel it and raise it again under today's date."; the 27-day-old one "3 days left" (due soon, within 5 days); today's **Open**. Register on the 27-day-old one registers it and it leaves the list. Registering or exporting the late one is refused: "<number> is dated <date>; the last day to register it was <date>. The IRP refuses a document more than 30 days old ... Cancel it and raise it again under today's date." With the date cleared the list still shows the pending documents, says "The 30-day limit does not apply to this firm (Settings > Tax > GST Documents).", and has no Last day or Days left columns.

### TC-COMP-019 — A sales return's credit note on the IRP

*Added 2026-10-02 (D-TAX-2, decision A45).*

- **Preconditions:** TC-COMP-016's firm on the **Sandbox** route. A B2B customer with two approved invoices for the same product; a sales return of goods from **both** invoices, completed; a second completed return of goods that were only delivered, never invoiced.
- **Steps:** Sell > Returns & notes > Sales Returns → the first return → **Print credit note**. Accounts > All Accounts screens > Tax filing > E-Invoice → **To register**: find it and **Register**. Print its credit note again. Switch to **Offline**, raise and complete another return of billed goods, **Export for portal** with it ticked, and open the file. Look for the second return in **To register**.
- **Expect:** before registration the credit note print is refused with the no-IRN sentence and offers a reference copy. The return is listed as **Sales return**; it registers with an `SBX` IRN, and its credit note then prints with the E-INVOICE box. The exported entry is a `CRN` whose `RefDtls` names **each** invoice it returns goods from. The return of goods never invoiced is not listed and is never registered ("... returns goods no invoice billed, so it credits no tax invoice and is not registered.").

### TC-COMP-020 — The 30 November limits and 16-character document numbers

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog GST-1 (A46), GST-2 (A47, D-TAX-3), GST-3 (A48)
- **Fixture:** `compliance-firm`
- **Also needs:** an approved invoice dated in the **previous GST year** (April to March); a supplier bill dated in the previous GST year; a numbering series for the sales invoice with a long prefix.
- **Steps:** as the fixture's **Firm admin**: raise a **credit note** (and a sales return) against the old invoice dated after 30 November that follows that year's end; read the screen after saving. Raise one dated earlier. Open the old **supplier bill** after 30 November following its year. Then Settings > Firm > **Numbering Series** → the sales invoice series: set a prefix that makes the number longer than 16 characters; try a space or an underscore in the prefix. Look at the default series of a new firm for invoice, credit note, sales return, debit note, delivery challan.
- **Expect:** a credit note or sales return dated after 30 November following the supply's GST year carries a **time-limit warning** (a warning, not a refusal: the firm may have filed its annual return earlier); the same warning appears on a supplier bill for input credit claimed after that date (s.16(4)). One dated before it shows none. The GST year is April to March whatever the firm's own year. A series for the six GST documents (invoice, credit note, sales return, customer debit note, delivery challan, reverse-charge self-invoice) is refused when its numbers can exceed **16 characters** or use characters other than letters, digits, hyphen and slash; the default series use a **short financial year** so they fit. Quotations, orders, proformas and vouchers keep any length.
- **Leaves:** documents carrying warnings.

### TC-COMP-021 — GST checks before filing

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog GST-5, A82
- **Fixture:** `compliance-firm`
- **Also needs:** an invoice to a buyer whose GSTIN has a wrong check character; a product with no HSN; an approved invoice to a registered buyer for a firm that e-invoices but with no IRN; a credit note dated late; a credit note on a cancelled invoice; a supplier bill with a bad GSTIN.
- **Steps:** as the fixture's **Firm admin**: Accounts > All Accounts screens > Tax filing > **GST checks** → choose the month → Run. Read each finding. Click a row. Fix one problem and run again. As a role without SALES_VIEW open the screen.
- **Expect:** findings are named by code and each row names its document (type, number, date, party): GSTIN_INVALID (the firm's own, a buyer's on invoices and notes, a supplier's on bills as a **warning**), HSN_MISSING and HSN_SHORT (six digits once the firm e-invoices, four below), PLACE_OF_SUPPLY_MISSING, IRN_MISSING, CREDIT_NOTE_LATE (after 30 November following the supply's year) and CREDIT_NOTE_ON_CANCELLED_INVOICE. The checks read the same invoices GSTR-1 declares. *Open document* is disabled (the desktop cannot open a sales invoice by id yet). After fixing, the finding is gone on the next run. Needs SALES_VIEW.
- **Leaves:** unchanged.

### TC-COMP-022 — A filed return is kept, and a change becomes an amendment

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog GST-6, A130
- **Fixture:** `compliance-firm`
- **Also needs:** invoices in last month and this month (back-date as needed).
- **Steps:** as the fixture's **Firm admin**: Accounts > **GST Returns** → GSTR-1 for last month → **Mark filed**. Then add or edit a document in last month (a new invoice dated last month, a credit note, a changed GSTIN or rate on one) and reopen last month, then open GSTR-1 for **this** month and GSTR-3B for this month. Withdraw the filing (Undo) and look again.
- **Expect:** a filed period shows the figures **as filed** (a banner says filed; recomputing is possible but the snapshot is what is shown). Any other period's GSTR-1 carries an **Amendments** section: every earlier filed period is recomputed and compared with what was declared — B2BA (invoice by number; the GSTIN may change), B2CLA, CDNRA, B2CSA (a row gone to nothing too) and documents added to a filed period after filing. GSTR-3B carries *amendments to earlier returns*, the net change (credit notes negative). Withdrawing the filing drops its snapshot and the period is live again. One snapshot per filing under the firm's GSTIN; per-branch filing is open.
- **Leaves:** a filing record unless withdrawn.

### TC-COMP-023 — A quarterly (QRMP) filer

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog GST-7, A83
- **Fixture:** `compliance-firm`
- **Steps:** as the fixture's **Firm admin**: Settings > Tax > **GST Documents** → **Return filing**: frequency *Quarterly*, from a quarter's start, payment method *fixed sum* (then *self-assessed*). Accounts > All Accounts screens > Tax filing > **PMT-06 deposits** → take the suggested amount → record the deposit; reverse it. Open **GST Returns**: the quarterly GSTR-1 and the **IFF** view for month 1 or 2; Mark filed the IFF. Home → Tax calendar. Then GST Payment for a quarter and for month 1.
- **Expect:** the filing plan says which months are quarterly, the period each month files under and every due date (3B on the 22nd or 24th by the GSTIN's state). The calendar shows IFF (optional) and PMT-06 for months 1-2 and the quarter's GSTR-1 and 3B. A deposit is Dr *GST Electronic Cash Ledger* / Cr bank, reversible while the quarter is unsettled. The quarterly GSTR-1 leaves out what a filed IFF already furnished. GST payment spans the quarter, refuses months 1-2, and pays from the cash-ledger deposits before the bank. A cancellation's "after the return was due" reads the quarterly date too.
- **Leaves:** deposits, filings.

### TC-COMP-024 — Common credit reversal, rule 42

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog GST-4, A84
- **Fixture:** `compliance-firm`
- **Also needs:** taxable and exempt sales and eligible input credit in the month and later months of the year.
- **Steps:** as the fixture's **Firm admin**: Settings > Tax > **GST Documents** → *Rule 42 mode* on. Accounts > All Accounts screens > Tax filing > **Rule 42** → the month → work out; post. Open GSTR-3B. Run the annual true-up and post it; reverse a posting.
- **Expect:** per period the reversal is D1 = C2 × E / F from GSTR-3B's own figures (every eligible credit taken as common), posting Dr *Input Tax Not Claimable* / Cr input tax; the year's true-up is summed month by month against what was posted and a true-up reclaim posts the mirror. GSTR-3B carries *itc reversed rule 42* (4(B)(1)) and *itc reclaimed rule 42* (4(A)(5)) in net ITC. Reversing a posting undoes it. Rule 43 (capital goods) and credit used only for taxable or only for exempt supplies are not done.
- **Leaves:** reversal journals.

### TC-COMP-025 — A branch with its own GSTIN

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog STK-2, A127
- **Fixture:** `compliance-firm`
- **Also needs:** a second branch in another state with a warehouse; a valid GSTIN for that state (and one with a wrong check character).
- **Steps:** as the fixture's **Firm admin**: Masters > **Branches** → the second branch → **Branch GSTIN**: the wrong one, one of another state, then the valid one → Save. Raise and approve an invoice from that branch; print it; e-invoice it. Accounts > **GST Returns**: choose each GSTIN. Try a stock transfer (document or one-step) between the two branches' warehouses.
- **Expect:** the GSTIN is checked for shape and check character and must match the branch's state; a GSTIN makes the branch GST-registered. The branch's own GSTIN (else the firm's) decides the supplier state in place of supply, the seller block on every print, the e-invoice seller details and the e-way bill consignor. GSTR-1 and 3B take a GSTIN and read only that GSTIN's branches (the firm's own GSTIN also takes branches without one); a firm with one GSTIN is not scoped. A transfer between two GSTINs is refused, naming the sales invoice to the other branch as the way.
- **Leaves:** a branch GSTIN, an invoice.

### TC-COMP-026 — The tax rule is kept on each line

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog GST-8, A85
- **Fixture:** `selling-firm`
- **Steps:** as the fixture's **Firm admin**: Sell > **Quotations** → New with a DET line; open the line's tax detail. Save, convert and bill. Open the invoice line's tax detail. Settings > Tax > **Rule Simulator** and simulate the same line. Open an old document made before this change; open a credit note.
- **Expect:** the line's tax detail names the **rule code and version** that taxed it, and the simulator answers with the same matched rule code and version. Lines saved before this change show none; credit and debit notes copy their tax from the invoice and are left out.
- **Leaves:** documents.


## Finance, reports and the rest of the platform

The books are on the **Accounts** menu (with Receipts on Sell and Payments on
Buy); Reports has **Operational** and **Financial**; accounting periods live
under **Settings > Firm > Financial Years**. Trial Balance, Profit & Loss and Balance
Sheet each take an **Accounting period**: pick the same one on all three.

The cases that change a firm's books — a new account, a closed period, a cost
centre, an account that demands one — use `ready-firm`, a store of the run's
own with a fresh chart (1000 Cash, 5000 Purchases, and no 9999).

### TC-FIN-001 — A new ledger account, and what cannot change afterwards

- **Covers:** plan 13.1
- **Fixture:** `ready-firm`
- **Steps:** as the fixture's **Firm admin**, Accounts > All Accounts screens > Books > **Chart of Accounts** → **New**: group chip **REV** first, code `9999`, name `Manual test account`, type EXPENSE → Save. Then group **EXP · Direct Expenses** → Save. Select it → **Edit**.
- **Expect:** with REV: "A ledger account must share its group's account type." With EXP: the row appears (Code, Account, Type, Status). No Delete on the toolbar. On Edit, group, type and code are fixed; only Name, Description, the two "Requires a …" boxes and **Active** change.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §12.3, in schema `fx_<suffix>_r` — one `ledger_accounts` row (9999, EXPENSE, group EXP, `is_profit_loss` true) and audit `finance.ledger_account.created`; the refused REV save writes nothing. An Edit writes `finance.ledger_account.updated` recording only name and active flag (D-FIN-13). The fresh chart is §12.1.
- **Leaves:** account 9999 in the fixture's store.

### TC-FIN-002 — The three statements balance and agree

- **Covers:** plan 13.2, 13.3
- **Fixture:** `selling-paid`
- **Steps:** as the fixture's **Firm admin**, Accounts > **Trial Balance**, this month's period; then **Profit & Loss** and **Balance Sheet**, the same period.
- **Expect:** the trial balance has Code, Account, Type, Opening, Debit, Credit, Closing, a Total row and a **Balanced** chip — 1100 Trade Receivables among the rows. P&L: Income and Expenses with a Net profit or loss row (This period, Year to date). Balance Sheet: Assets, Liabilities, Equity with Retained earnings brought forward and Result for the year, chip **Balanced**. They agree: Total assets = Liabilities and equity; the sheet's Result for the year = the P&L's year-to-date net; total debit = total credit. *(The figures are this fixture's own; the relationships are the test.)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §12.9 in schema `fx_<suffix>_s` — all three read `ledger_balances` and write nothing; its query recomputes assets = liabilities + equity + earnings from the stored rows. The trial balance's Total row is the closing balances by side, not the sum of the Debit and Credit columns above it (D-FIN-18).
- **Leaves:** unchanged.

### TC-FIN-003 — A closed period refuses a posting; its trail says who closed it

- **Covers:** plan 13.5, 13.8
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Firm admin**, Accounts > Journal Entries → **New Entry**: period June 2026, any journal and voucher type, date 2026-06-15, reference `MT-CLOSE-1`, lines `5000 Purchases` Dr 100 and `1000 Cash` Cr 100 → **Save Draft**.
  2. Settings > Firm > **Financial Years** → the year → **June 2026** → **Close**.
  3. Accounts > Journal Entries → the draft → **Post**.
  4. Reopen June (**Open**) → Post again.
  5. Settings > Platform > System > Audit Logs → Action `finance.accounting_period.updated` (in full) → Search. Then sign in as the fixture's **Platform admin**, stay on Platform, and run the same search.
- **Expect**
  - Step 2: "June 2026 is closed. Nothing further can be booked into it."
  - Step 3: refused: "Accounting period P03 is closed and cannot accept postings." (June is P03 in an April year.)
  - Step 4: "Journal entry MT-CLOSE-1 posted." The trial balance for a later month still reads **Balanced**.
  - Step 5: in the firm, the caption "The trail for Ready <suffix>…" and **two** rows (closed, reopened); `finance` alone would find nothing (exact match). On Platform the same search finds **nothing** — finance events stay in the firm's trail.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §12.2 (close and reopen: `accounting_periods.status`, one `finance.accounting_period.updated` each, none on the platform) and §12.4 (the draft: `journal_entries` DRAFT and its lines, no posting; the refused post writes nothing; the post: `gl_postings` and `ledger_balances`, audit `finance.journal_entry.posted`). The June posting moves every later month's stored opening (§12.8). All in `fx_<suffix>_r`.
- **Leaves:** a posted June entry.

### TC-FIN-004 — Journal entries say which module posted them

- **Covers:** plan 13.4
- **Fixture:** `selling-paid`
- **Steps:** Accounts > Journal Entries; search each: `SI-2026-2027-000001`, `DN-`, `RC-2026-2027-000001`; open each with **View**.
- **Expect:** each row's subtitle is the entry's description; the View dialog's first line reads "POSTED · posted by <module> · <description>" — sales_invoice, delivery_note, settlements, tcs. The search matches reference or description; there is no source-module filter (BACKLOG §31.15).
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §12.5 — `journal_entries.source_module` is what the View dialog names (`sales_invoice`, `delivery_note`, `settlements`, `tcs`), every entry `GEN`/`JV`; its query lists the four in `fx_<suffix>_s`.
- **Leaves:** unchanged.

### TC-FIN-005 — Every report opens, and an empty one says so

- **Covers:** plan 13.6
- **Fixture:** `selling-paid`
- **Steps:** Reports > **Operational** and **Financial Reports**: open every entry.
- **Expect:** each renders with `N row(s)` in the header, or — when empty — "Nothing to report / This firm has nothing matching it yet." rather than a blank grid. The sales order register, delivery note register and invoice reports hold the fixture's documents; the purchase reports are empty (this store bought nothing).
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §18 (every catalogued report and what it reads), §12.9 (the financial statements) and §9.13 (the purchasing ones) — each reads its tables and writes nothing, not even an audit row.
- **Leaves:** unchanged.

### TC-FIN-006 — Ctrl+K finds a product and lands on its screen

- **Covers:** plan 13.7
- **Fixture:** `product-master`
- **Steps:** as the fixture's **Firm admin**, type in any search box, move to another screen, press **Ctrl+K**, type `<SUFFIX>-PM` → Search; select the result → **Open Details**.
- **Expect:** the dialog opens wherever focus is; one result, **Slot Check <suffix>** (a product), "1 result found."; Open Details closes the search and lands on **Masters > Products**. **(HTTP)** `GET /api/v1/search?query=<SUFFIX>-PM` → 200 (the parameter is `query`; `q` answers 422).
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §18.7 (and §12.13) — the search reads and writes nothing; landing on a screen can leave only the last-screen `user_preferences.updated` on the platform (§3).
- **Leaves:** unchanged.

### TC-FIN-007 — Cost and profit centres, and an account that demands one

- **Covers:** plan 13.9d, 13.9e
- **Fixture:** `ready-firm`
- **Steps**
  1. Settings > Set up > Account structure > **Cost Centres** → New `SALES`, `Sales` → Save; New `SALES` again. Settings > Set up > Account structure > **Profit Centres** → New `NORTH`, `North` → Save.
  2. Chart of Accounts → Edit `5000 Purchases` → tick **Requires a cost centre** → Save. Accounts > Journal Entries → New Entry → choose 5000 on a line.
  3. **(HTTP)** `POST /api/v1/finance/journal-entries` with a 5000 line and no `cost_center_id`.
  4. Untick the flag.
- **Expect**
  - Step 1: the rows appear; the second SALES: "A cost centre with this code already exists." No Delete on either grid — deactivate with Active.
  - Step 2: a **Cost centre \*** dropdown on that line and no other; with SALES chosen the entry saves.
  - Step 3: **422**, "Ledger account 5000 requires a cost centre."
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §12.6, in schema `fx_<suffix>_r` — `cost_centers` SALES and `profit_centers` NORTH with `finance.cost_center.created` / `finance.profit_center.created`; the duplicate writes nothing; the flag is `ledger_accounts.requires_cost_center`; the refused POST writes nothing; the entry saved with SALES carries it on `journal_lines.cost_center_id`. No report reads a centre.
- **Leaves:** centres SALES and NORTH.

### TC-FIN-008 — A blocking credit policy refuses the approval

- **Covers:** plan 13.9c3 (credit half)
- **Fixture:** `policy-firm` — BLOCK at 100%; Anand's limit 1,000; a draft order for 20 detergent.
- **Steps:** as the fixture's **Firm admin**, Masters > Customers → toolbar **Settings**; Cancel. Sell > Sales Orders → the fixture's draft → **Approve**.
- **Expect:** the policy reads **Warn, then block**, warn 80, block 100. Approve is refused: "Anand Agencies <suffix> would be at 179.9% of a 1000.00 credit limit. Collect payment or raise the limit before continuing." The order stays DRAFT.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.6 — `credit_control_settings` BLOCK at 80/100; the refused approval writes nothing and the order stays DRAFT (§12.13).
- **Leaves:** unchanged.

### TC-FIN-009 — A firm that does not type delivery notes

- **Covers:** plan 13.9c3 (stages half)
- **Fixture:** `policy-firm` — delivery-note stage off; Vijaya's order for 4, approved.
- **Steps:** as the fixture's **Firm admin**, Settings > Selling > **Sales Stages** (the same dialog as the Sales stages icon on Sales Invoices). Look for Delivery Notes on the Sell menu. Then Sales Invoices → New → bill the fixture's **order** (4) → Create draft → Approve. Reports > Operational → **Delivery note register**.
- **Expect:** Sales stages shows **Delivery note** switched off, and **Delivery Notes is not on the Sell menu** — a stage the firm does not type is hidden. The invoice approves straight off the order; the service raises and dispatches the note itself (the order reads **DELIVERED**), and the register lists that note. *(Whether a hidden screen should hide notes that exist is an open product question, not a defect.)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §11.20 — the invoice's create raises, approves and dispatches the note in one request; the journals it leaves are §12.5's `delivery_note` and `sales_invoice` rows.
- **Leaves:** a billed, delivered order.

### TC-FIN-010 — Roles and Permissions are two Settings screens with an address each

- **Covers:** plan 13.9, 13.9b, 13.9c
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, click the gear and look under **Platform > People**; open **Roles**, then **Permissions**. Ctrl+K a permission code (e.g. `CUSTOMER_VIEW`) → open it. Sign out and in.
- **Expect:** Roles and Permissions are two cards under Platform > People, each opening in a tab of its own with its own heading. Ctrl+K lands on **Permissions** directly; after signing in again the last screen restores to the same one (confirm: the 1.3.0 tab strip keeps both open). (Creating and editing roles is TC-ROLE-001 and TC-ROLE-002.)
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §12.13 — reads only; the restored half is the last-screen preference on the platform (§3).
- **Leaves:** a firm admin user.

### TC-FIN-011 — A crash report reaches Diagnostics

- **Covers:** plan 13.10
- **Fixture:** `platform-admin`
- **Steps:** sign in on the desktop, end **agency_desktop** in Task Manager, start it again and sign in as the fixture's **Platform admin** (the queued report is sent then). Settings > Platform > System > **Diagnostics** → Source **Desktop** → Search; open the **UnexpectedTermination** group's first occurrence. Then Source **Server**, any group's first occurrence.
- **Expect:** Desktop: the UnexpectedTermination count one higher than before; occurrences / first seen / last seen / versions chips; the newest occurrence shows Firm, User and "Leading up to it" breadcrumbs ("Previous session started at … ended without a clean exit…") — no Request and no stack trace. Server: **Request <request_id>** and the stack trace.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §18.8 (and §12.13) — one `platform.error_reports` row per report, `source` CLIENT for the desktop (the screen's Desktop) and SERVER for the server, no audit row; its query counts them by source and type.
- **Leaves:** one more crash report.

### TC-FIN-012 — Bank reconciliation against a statement

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog ACC-1, A125
- **Fixture:** `selling-paid`
- **Also needs:** a bank statement file for the bank ledger account in the layout the import expects (date, narration, reference, debit, credit, balance), with lines matching the firm's postings (one by amount and date within 3 days, one by cheque number or UTR, two postings that tie, one that sums two entries) and one line with nothing behind it; a user holding JOURNAL_POST.
- **Steps:** as the fixture's **Firm admin**: Accounts > **Bank Reconciliation** → pick the bank account → **Import statement**; import it again. Press **Auto-match**. Match a tied line by hand; match one line to **two** entries summing to it; **Unmatch** one; remove a statement. Open the *reconciliation statement* as on a date with the statement's printed closing balance. Then Settings > Firm > Financial Years → the month's close checks.
- **Expect:** lines are matched to **postings on the bank ledger** (receipts, payments, contra vouchers, expenses and journals alike). A line already imported on the account is refused. Auto-match pairs on amount, journal date within 3 days and reference; ties are left for a person. A manual match of one line to several entries must sum to the line. The reconciliation statement shows the book balance, unmatched entries and unmatched statement lines, and checks against the printed closing balance. The cleared date is the matched line's date. Reading needs LEDGER_VIEW, importing and matching JOURNAL_POST. The month's close checklist lists the unmatched lines (never refusing).
- **Leaves:** a statement and matches.

### TC-FIN-013 — Post-dated cheques: hold, deposit, clear, bounce

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog ACC-2, A80
- **Fixture:** `selling-invoiced`
- **Also needs:** a bank account; the invoice of 483.21 for Vijaya; a supplier bill for the issued side.
- **Steps:** as the fixture's **Firm admin**: Sell > All Sell screens > Money > **Post-dated Cheques** → New: Vijaya, 483.21, cheque number, cheque date a week ahead → Save (held). Try **Deposit** today. Filter *due today*. On the cheque date **Deposit**; then **Clear**. Take a second cheque, deposit it and **Bounce** it with charges 100. Cancel a third while held. Then Buy > All Buy screens > Money > **Post-dated Cheques** → issue one to a supplier and run through hold and deposit.
- **Expect:** holding posts nothing; deposit records the receipt (payment on the issued side) through the settlement service, mode Cheque, and is **not allowed before the cheque's date**; clearing posts nothing. A bounce reverses the settlement on the day returned and posts the return charges (Dr bank charges / Cr bank, and Dr receivable / Cr cheque-return charges on the customer's account); a cheque can be cancelled while held. The received side needs the receipt grants and the issued side the payment grants.
- **Leaves:** cheques, receipts, a bounce journal.

### TC-FIN-014 — Payment mode and instrument date on receipts and payments

*Added 2026-10-02 from the code; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog ACC-3, A49
- **Fixture:** `selling-invoiced`
- **Steps:** as the fixture's **Firm admin**: Sell > **Receipts** → Record Receipt for Vijaya with mode **Cheque**, an instrument number and instrument date; again with **UPI** and **Cash**. Buy > **Payments** → the same for a supplier. Open the cash book and the bank book. Reports > Financial → collections by mode.
- **Expect:** each receipt and payment stores its mode and instrument date; the cash and bank books gain **Mode** and **Instrument** columns; collections by mode read the mode on each receipt.
- **Leaves:** receipts.

### TC-FIN-015 — Bank details on documents, and printing a cheque

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog ACC-4 (A81), ACC-12 (A66)
- **Fixture:** `selling-invoiced`
- **Also needs:** a bank ledger account; a payment to a supplier by cheque; a cashier user (PAYMENT_CREATE) and an accountant (ACCOUNT_VIEW only); a sheet of paper or the PDF preview.
- **Steps:** as the fixture's **Firm admin**: Accounts > All Accounts screens > Tax filing > **Bank Details** → the bank account → name, number, IFSC, branch, UPI ID; mark **print on documents**; try marking a second account. Print an invoice and a quotation. As the accountant open the screen. Then Buy > **Payments** → the cheque payment → **Cheque layout** → adjust the offsets → **Test print**; **Print cheque** with a payee override. Try a cash payment, a bank-transfer payment and a reversed one.
- **Expect:** one set of details per bank ledger account (asset accounts only) and at most one marked to print: its details fill an empty bank block, and an empty UPI ID, on every print that has one (text typed on a template still wins). The full number is shown to ACCOUNT_MANAGE or PAYMENT_CREATE; everybody else reads the last four; the audit entry masks it. The cheque leaf is a CTS-2010 layout — date boxes, payee, amount in words on two lines, `**12,34,567.00/-`, A/c Payee crossing — moved by the bank account's offsets and dated on the cheque's own date; cash, non-cheque and reversed payments are refused.
- **Leaves:** bank details, a cheque layout.

### TC-FIN-016 — Checks before closing a month, and the ageing bands

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog ACC-5 (A50), ACC-6 (A51)
- **Fixture:** `selling-paid`
- **Also needs:** a draft document dated in the month, an unmatched bank statement line (TC-FIN-012) and an overdue sales and purchase bill.
- **Steps:** as the fixture's **Firm admin**: Settings > Firm > **Financial Years** → open the month → **Close**: read the checklist first. Change the close-check settings and run again. Then in the same screen set the **ageing bands** (for example 0-15, 16-45, 46-90, 90+). Reports > Financial → customer ageing and vendor ageing. Reports > **Due** lists: the sales invoices due today and the purchase invoices due in 7 days.
- **Expect:** closing a month lists what is not finished (per the firm's settings, including unmatched bank lines); the list never refuses by itself. Both ageing reports use the firm's bands (the vendor row carries a `buckets` list instead of four fixed columns). The due reports list sales bills due, and purchase bills due within the days asked (0 today, 7 the week ahead).
- **Leaves:** ageing settings.

### TC-FIN-017 — TDS challans and TDS on purchases (194Q)

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog ACC-7 (A79), ACC-8 (A78)
- **Fixture:** `po-invoiced`
- **Also needs:** payments with TDS deducted (194C or similar) and expense postings with TDS; a supplier whose approved bills this year exceed 50 lakh (or lower the threshold in the settings); the supplier's PAN.
- **Steps:** as the fixture's **Firm admin**: Masters > Vendors → the supplier → *Usual TDS section* 194C. Buy > Payments → Record Payment and look at the section. Accounts > All Accounts screens > Tax filing > **TDS Challans** → *Open deductions* → New: select one section's deductions, enter BSR code, challan serial, date, interest and fees → Save. Create a second challan with the same CIN. Cancel the first. Open the TDS return and *Challans due*. Then Settings > Tax > **TDS on Purchases (194Q)** → switch on, threshold 50 lakh, 0.1%, 5% without PAN → Save. Open Record Payment for the over-threshold supplier. Reports > Financial → 194Q register.
- **Expect:** the payment prefills the supplier's usual section. The challan carries one section; its tax is the sum of the deductions chosen; one live challan per CIN; it posts Dr TDS payable, Dr TDS interest and fees, Cr bank. Cancelling posts a mirror journal and frees the deductions. The TDS return fills each deductee row's challan serial, BSR code and date, and *Challans due* shows deposited and still to deposit. The 194Q figure is the rate on the **excess** over the threshold of the supplier's approved bills without GST in the April-March year, less 194Q already deducted on posted payments; the payment prefills section and amount and never overwrites a figure you typed.
- **Leaves:** challans, settings.

### TC-FIN-018 — Cash flow statement

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog ACC-9, A87
- **Fixture:** `selling-paid`
- **Steps:** as the fixture's **Firm admin**: Accounts > All Accounts screens > Statements > **Cash Flow** → choose the period range; compare with Profit & Loss and Balance Sheet for the same periods. As a role without PROFIT_LOSS_VIEW open it.
- **Expect:** sections are built from the account groups — current assets and liabilities are operating, other assets investing, other liabilities and equity financing; cash is the cash and bank accounts. The statement shows opening and closing cash and says whether it **reconciles** (the movement equals the change in cash). Needs PROFIT_LOSS_VIEW.
- **Leaves:** unchanged.

### TC-FIN-019 — Files attached to journals, receipts and payments

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog ACC-10, A88
- **Fixture:** `selling-paid`
- **Also needs:** a PDF; the ATTACHMENTS feature enabled.
- **Steps:** as the fixture's **Firm admin**: Accounts > **Journal Entries** → open an entry → **Files** → add the PDF; delete it. Do the same on a receipt (Sell > Receipts) and a payment (Buy > Payments).
- **Expect:** each file is a reference (name, type, path, caption) held against exactly one of a journal entry or a settlement; deleting is soft and audited. Without the ATTACHMENTS feature the control is not offered.
- **Leaves:** file references.

### TC-FIN-020 — Export to Tally

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog MSG-5, A135
- **Fixture:** `selling-paid`
- **Also needs:** TallyPrime to import into (the build notes say a CA should import a sample before release).
- **Steps:** as the fixture's **Firm admin**: Accounts > All Accounts screens > Books > **Export to Tally** → the mappings: give two accounts their Tally names and groups → Save. Choose the dates → **Export**. Open the XML; import it into a Tally company.
- **Expect:** every posted journal of the period is one voucher typed by its source (Sales, Purchase, Credit Note, Debit Note, Contra, Receipt or Payment for settlements, otherwise Journal). Lines on the receivable or payable control accounts name the party of the document, so the masters carry a ledger per customer and supplier under Sundry Debtors/Creditors with its GSTIN; other accounts go out under their mapped name and group (or their own name in the group their purpose suggests). GST travels as the tax ledgers. Tally accepts the file and its trial balance agrees with the platform's.
- **Leaves:** ledger mappings.

### TC-FIN-021 — Approvals by level, and bulk reject

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog PLT-1, A131
- **Fixture:** `selling-firm`
- **Also needs:** three users: a **Sales** user, a **Sales manager** and the **Firm admin**.
- **Steps:** as the **Firm admin**: Settings > Firm > **Approval Levels** → New rule: document type *Sales order*, level 1 from 0 role Sales Manager; level 2 from 10,000 role Firm Administrator. Save. As the **Sales** user raise an order of 20,000 and a small one of 500. As the **Sales manager**: Sell > All Sell screens > Documents > **Approvals** → pending → **Sign off** the big order; try **Approve** on the order itself. As the administrator open Approvals and **Sign off** level 2. Raise another and **Reject** with a reason; reject two at once (bulk). Also try an order of 500 and a purchase order. Home bell.
- **Expect:** with no rule for the total nothing changes. Otherwise levels are signed in order, one level per person, and Approve goes through only when the approver can sign the last open level; anyone else is refused naming the level and roles. *Sign off* records the next level and the **last** sign-off approves the document through its own service (if the module refuses, the signature stays). A sign-off counts while the total is no more than it was signed at. *Reject* needs a reason, clears the sign-offs and returns a submitted purchase order to draft; bulk reject is per row. An order the chain raised itself is not gated. Platform administrators are not limited. The bell shows *Documents awaiting the next sign-off*. Applies to sales orders, sales invoices, purchase orders and purchase invoices.
- **Leaves:** rules, sign-offs, approved or rejected orders.

### TC-FIN-022 — The notification bell, and one search box on the audit trail

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog PLT-2 (A123), PLT-8 (A77)
- **Fixture:** `selling-firm`
- **Also needs:** a purchase order awaiting approval, a requisition waiting, a stock adjustment request waiting and a failed email; a user who may approve and a user who may not.
- **Steps:** as the **Firm admin**: look at the bell on Home. Open it and mark it read; make another item wait and look again. As the user who may **not** approve open the bell. Then Settings > Platform > System > **Audit Logs** → type a person's name or email in the search box; then an action name; then a record type.
- **Expect:** the bell is derived from the documents — it counts approvals waiting (purchase orders, the multi-level chain, requisitions, stock adjustment requests), failed messages of the last 7 days and stock alerts — and is offered only to someone who could act on each. Reading marks what has been seen; a change in count makes it new again. The audit search matches action, record type, the actor's name or email, and, for user rows, the subject, on both stores of a firm's merged trail.
- **Leaves:** read marks.

### TC-FIN-023 — Sales and purchase analysis: compare years, basis, margin, saved layouts

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog RPT-1 (A121), RPT-2 (A122)
- **Fixture:** `selling-paid`
- **Also needs:** orders and invoices in the same period of the previous year (back-dated), a user with PRODUCT_VIEW_COST_PRICE and one without.
- **Steps:** as the fixture's **Firm admin**: Sell > All Sell screens > Insight > **Sales Analysis** → basis *Ordered* then *Invoiced*; switch on **Compare with last year**; read cost, margin and margin %; **Save layout**, reopen it. Sign in as the user without cost-price rights. Buy > All Buy screens > Insight > **Purchase Analysis** → basis *Received*/*Ordered*, compare, average rate. Open **Rate Trend**.
- **Expect:** the ordered basis counts approved orders instead of invoices; the previous-year column is the same period shifted one year; cost, margin and margin percent appear only with PRODUCT_VIEW_COST_PRICE. Layouts are saved per user and report. The purchase analysis has the same controls plus average rate on every figure (sales too); the rate trend shows the rate by month.
- **Leaves:** a saved layout.

### TC-FIN-024 — Search at volume, and nightly retention

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog PLT-3 (A75), PLT-4, PLT-6 (A76)
- **Fixture:** `selling-firm`
- **Also needs:** for retention, an installed server with its scheduled backup task; for speed, PERF01 loaded if you want the volume figures (the expected timings are in the performance notes).
- **Steps:** as the fixture's **Firm admin**: press Ctrl+K and type part of an invoice number (for example the middle digits); type part of a customer name. Open GSTR-1 and GSTR-3B for the month and Customer Outstanding. On the server, run the nightly backup task and read its log; set the retention switch off and run again.
- **Expect:** a fragment of a number or name finds the document (on a large firm through the trigram index). The returns and the outstanding report give the same answers as before and are quicker (the month's GSTR-1 about 3.7 s and 3B 2.9 s on the 110,000-invoice test firm; a quarter is still slower). The nightly backup task also runs retention (`purge-retention --yes --scheduled`); with the platform-wide switch off it returns at once; a retention failure is logged and never fails the backup.
- **Leaves:** a backup.

### TC-FIN-025 — Phase 1 leftovers: price list counts, territory picker, return pickers

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog PLT-9
- **Fixture:** `selling-firm`
- **Steps:** as the fixture's **Firm admin**: Settings > Set up > Pricing > **Price Lists** → open the grid, read the count column for a list with 3 breaks of one product; New list with scope **One territory**. Sell > Returns & notes > **Sales Returns** → New and open the picker of returnable lines for a line with no description.
- **Expect:** the price list grid counts **distinct products** ("1 (3 rates)"); the *One territory* scope has a territory picker; a returnable line with no description is labelled by product code and name, and "Line N" only when nothing is known.
- **Leaves:** a price list.


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
- **Steps:** on **A** and **B**: Masters > Customers → double-click `<SUFFIX>-CM`. On A change the phone → **Save**. On B change the phone to something else → **Save**.
- **Expect:** A saves ("Customer updated."). B is refused **inside the editor** with the sentence naming `customer`; the dialog stays open with B's typed phone still in the box. Cancel B; reopen: A's phone.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §16.2 and §16.0 — the customer endpoints publish `version` as an `ETag` and on the body and take `If-Match`; A's save moves it by one and writes one `customer.updated`, B's writes nothing.
- **Leaves:** the customer with A's phone.

### TC-CONC-002 — The same race on an order, a product and a price list

- **Covers:** plan 14.2
- **Fixture:** `selling-firm`
- **Steps:** create a draft Sales Order for `<SUFFIX>-C01` first (any line). Then, on A and B: open that draft → **Edit**, change **Remarks** on both, Save A then B. Repeat on Masters > Products → `<SUFFIX>-DET` (Description) and Settings > Set up > Pricing > Price Lists → `STANDING` (the **Name** — the dialog has no Description).
- **Expect:** B is refused each time with the sentence naming `sales order`, `product`, `price list`; typing kept, dialog open.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §16.12 for the product half — the precondition is the row's `version`, and the winning save rewrites **every** product column from the payload, so B's loss is the whole record rather than the one field.
- **Leaves:** three records with A's edits.

### TC-CONC-003 — Saving unchanged does not move the version

- **Covers:** plan 14.3
- **Fixture:** `customer-master`
- **Steps:** on A alone, double-click `<SUFFIX>-CM`, change nothing → Save; do it again. **(HTTP)** `GET /api/v1/customers/{id}` before and after; compare the `ETag`.
- **Expect:** accepted both times; the `ETag` and the body's `version` are **the same before and after** — so a client re-sending the same `If-Match` is still accepted. *(Driven: `"2"` before and after an unchanged PUT.)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §16.2 — a save that changes no column writes no `UPDATE`, so the mapper's version id does not move; the `customer.updated` audit row is still written, with both sides identical.
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
  1. Settings > Set up > Pricing > Promotions → **Coupons** → `WELCOME10B` → Edit → **Total claims allowed** `1` → Save.
  2. Raise two draft orders for `<SUFFIX>-C01` with **Coupon** `WELCOME10B`, one on each client. Approve both.
- **Expect:** the first approves; the second is refused **by name**: "Coupon WELCOME10B has been used as often as it allows. Re-save the document to price it without." — not silently repriced. A claim counts only at approval, under a lock on the promotion. (`test_the_refusal_is_for_the_race_two_orders_priced_before_either_approved` covers the true race.)
- **Leaves:** one approved order with the coupon, one draft; the coupon exhausted in the fixture's store.

### TC-CONC-006 — Two accruals of one payout period

- **Covers:** plan 14.6
- **Fixture:** `commission-firm`
- **Steps:** on A and B: Sell > All Sell screens > Incentives > Commission → **Payouts** → **Accrue period**, this month on both; **Accrue** on A, then on B.
- **Expect:** A: "2 payout(s) accrued." B: "A commission payout already covers part of that period for this salesman (…)." — a **409** by name, never a 500. The database holds the rule (`UQ_commission_payouts_period_active`); the service supplies the sentence.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §17.12 — A's run inserts two DRAFT rows and two `commission.payout.accrued`; B's is refused by `_assert_period_is_free` and writes nothing. `UQ_commission_payouts_period_active` is what holds when both reads pass at once.
- **Leaves:** two draft payouts.

---

## Permissions — the server refuses, not only the button

`SALES_EXECUTIVE` holds `CUSTOMER_VIEW`, `TERRITORY_VIEW`, `SALES_VIEW` and the
three `SALES_*_CREATE` codes, nothing else. A hidden button is not a control:
each case below checks the screen **and** the route behind it.

### TC-PERM-001 — What a salesperson is not offered

- **Covers:** plan 15.1, 15.3, 15.4, 15.5
- **Fixture:** `sales-executive`
- **Steps:** sign in as the fixture's **Seller**. Click the gear and look for a **Platform** part; open **Sell > All Sell screens** and **Accounts > All Accounts screens** and look for Commission, Credit Notes and TCS.
- **Expect:** **no Platform part** on the Settings page. The territory screens (Settings > Set up > Territories & routes, on `TERRITORY_VIEW`) are offered, and none of **Commission** (Sell > All Sell screens > Incentives), **Credit Notes** (Sell > Returns & notes) or **TCS** (Accounts > All Accounts screens > Tax filing) — nor Price Lists, Promotions, Targets, Proforma, E-Invoice or GST Returns, each hidden on its own view code. That is expected, not a fault.
- **Leaves:** a seller.

### TC-PERM-002 — The credit policy opens read-only

- **Covers:** plan 15.2
- **Fixture:** `sales-executive`
- **Steps:** as the fixture's **Seller**, Masters > Customers → toolbar **Settings**.
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
  2. Click the gear and open, under **Platform**: People > **Users**, **Roles**, **Permissions**, **User Templates**, **User-Firm Assignments**; Firms > **Firms**, **Business Profiles**; System > **Platform Dashboard**, **Audit Logs**, **Diagnostics**.
- **Expect:** every one offered, and each opens. Running the platform is their job.
- **Data**
  ```sql
  select pa.scope from platform.platform_admins pa
  join   platform.users u on u.id = pa.user_id
  where  u.email = '<suffix>.operator@fixtures.local';
  ```
  `PLATFORM`.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — the operator's token carries the 33 operator codes globally and TEST01 and TEST02 in `firm_permissions` with nothing in either.
- **Leaves:** a platform operator.

### TC-TIER-002 — A platform operator is refused the books, even where they are a member

- **Covers:** plan 16.3
- **Fixture:** `platform-operator`
- **Steps**
  1. Sign in as the fixture's **Operator**. Look along the menu bar for Sell, Buy, Stock, Accounts and Masters.
  2. Open the firm switcher.
  3. Switch into **TEST01** and read the menu bar.
- **Expect**
  - Step 1: **none** offered on Platform. Their token carries **33** codes — firm, user, role, permission, platform and system administration (`FIRM_*`, `USER_*`, `ROLE_*`, `PERMISSION_*`, `PLATFORM_VIEW`, `PLATFORM_SETTINGS`, `SETTINGS_VIEW`, `SETTINGS_UPDATE`, `AUDIT_LOG_VIEW`, `DIAGNOSTICS_VIEW`, `LICENSE_MANAGE`, `SYSTEM_BACKUP`, `SYSTEM_RESTORE`, `SYSTEM_CONFIGURATION`) and nothing operational.
  - Step 2: Platform, **TEST01** (primary) and **TEST02** — the two firms they are a member of, and **not** every firm. An `ALL_FIRMS` administrator is widened to every firm (TC-PLAT-003); a `PLATFORM` one is not, but memberships they genuinely hold still show.
  - Step 3: **no business modules**. A designation is a ceiling, not a floor, and they hold no role in TEST01.
- **Data (HTTP):** `GET /api/v1/me/firms` as the operator → exactly TEST01 (`is_primary: true`) and TEST02.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — the two `user_firms` rows are why TEST01 and TEST02 show; the operator can add no other (D-IDN-6), and one global `FIRM_ADMIN` row on their own account would open TEST01's books (D-IDN-1).
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — reads only. The 403 holds while the operator holds no global-tier firm role — nothing stops them giving themselves one (D-IDN-1).
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
  1. Sign in as the fixture's **Firm admin** → Settings > Platform > People > **User Templates**.
  2. Select **Counter Sales**; look at **Edit** and **Delete**; open it.
  3. **(HTTP)** `PATCH /api/v1/user-templates/{Counter Sales id}` with `{"name": "x"}`.
- **Expect**
  - Step 1: the **eleven** above with Origin **Platform**, each naming its roles — Counter Sales shows `BILLING_EXECUTIVE, CASHIER`.
  - Step 2: Edit and Delete **disabled**; the dialog subtitle reads "… · Provided by the platform". It is offered to every firm, so no one firm may change it.
  - Step 3: **422**, "Platform templates cannot be edited."
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — the refused PATCH writes nothing; the eleven seeded templates are `is_system` rows in `platform.user_templates` — not the copies each firm store keeps (§15.0).
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §5 and §15.7 — `user_template.created` / `.updated` carry TEST01's id and no data.
- **Leaves:** a TEST01 template.

### TC-TMPL-003 — Hiring into a job in one step

- **Covers:** plan 17.4a, 17.4b
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → **New**: name `Job Hire <suffix>`, email `<suffix>.jobhire@fixtures.local`, a 12-character password, **Job template** Counter Sales. Save.
  2. New again: `Hand Hire <suffix>`, `<suffix>.handhire@fixtures.local`, Job template **blank**, Roles in this firm `CUSTOMER_SUPPORT` and `VIEWER`. Save.
- **Expect**
  - Step 1: created **and** holding `CASHIER` and `BILLING_EXECUTIVE` — one step, no second visit to the grid.
  - Step 2: exactly those two roles. The template field is optional.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 in `platform` — each Save writes `user.created`, `user.firms_set`, then `user_template.applied` + `user.roles_set` (step 1) or `user.roles_set` alone (step 2); `user.firms_set` carries no firm and is not on TEST01's Audit Logs (D-IDN-5).
- **Leaves:** two users in TEST01.

### TC-TMPL-004 — When a job is named, the job decides

- **Covers:** plan 17.4c, 17.4d
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → **New**. Pick `ACCOUNTANT` under Roles in this firm; then choose the **Read Only** job; then clear the job.
  2. Choose Read Only again and save (name, `<suffix>.readonly@fixtures.local`, password).
  3. Edit that user.
- **Expect**
  - Step 1: the helper text under **Roles in this firm** ends "Ignored when a job template is named above." Choosing the job **clears** ACCOUNTANT and **locks** the chips; clearing it unlocks them, empty.
  - Step 2: the user holds only `VIEWER`.
  - Step 3: **no Job template field** — it is create-only. A template is where somebody starts, and Apply job template on the grid is how to re-apply one.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — the saved person's `user_roles` are Read Only's, TEST01-scoped; the rows as TC-TMPL-003.
- **Leaves:** a TEST01 user holding VIEWER.

### TC-TMPL-005 — Applying a job replaces what somebody holds

- **Covers:** plan 17.5, 17.6
- **Fixture:** `manual-hire`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → select **Manual Hire (<suffix>)** → **Apply job template**.
  2. Type `inventory` in **Search jobs**; clear it.
  3. Choose **Counter Sales** → Apply.
- **Expect**
  - Step 1: dialog "Apply a job template": "Whatever Manual Hire (<suffix>) holds now is replaced by the job's roles. You can edit them afterwards like any other user." One line per active job with its roles beneath; **Apply disabled** until a job is chosen.
  - Step 2: only **Warehouse** remains (the search covers name, code, description and role). A filter that hides the chosen job clears the choice.
  - Step 3: their TEST01 roles become exactly `BILLING_EXECUTIVE` and `CASHIER` — `SALES_EXECUTIVE` and `CUSTOMER_SUPPORT` are gone.
- **Data:** audit `user_template.applied` naming `template_code: counter-sales` and `role_codes`.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — TEST01's `user_roles` rows soft-deleted and inserted, `authorization_version` +1.
- **Leaves:** Manual Hire holding Counter Sales' roles.

### TC-TMPL-006 — A firm administrator's template writes the firm tier only

- **Covers:** plan 17.6a
- **Fixture:** `two-tier-hire`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → **Two Tier Hire (<suffix>)** → Apply job template → **Counter Sales** → Apply.
  2. Sign in as the fixture's **Platform admin**, open the same user.
- **Expect:** **Roles in every firm** still `VIEWER`, `CUSTOMER_SUPPORT`; **Roles in specific firms** now `TEST01: BILLING_EXECUTIVE · CASHIER` (was ACCOUNTANT, INVENTORY_MANAGER). A template overwrites the tier its caller writes and never touches the other.
- **Data (HTTP)**, as the platform admin: `GET /api/v1/users/{id}/roles` → the two global ids; `GET /api/v1/users/{id}/firms/{TEST01 id}/roles` → the two Counter Sales ids.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — only rows with `firm_id` TEST01 move.
- **Leaves:** the user with a changed TEST01 tier.

### TC-TMPL-007 — A platform administrator's template writes the global tier only

- **Covers:** plan 17.6b
- **Fixture:** `two-tier-hire`
- **Steps**
  1. As the fixture's **Platform admin**, Settings > Platform > People > Users → **Two Tier Hire (<suffix>)** → Apply job template → **Warehouse** → Apply.
  2. Reopen the user.
- **Expect:** **Roles in every firm** becomes exactly `INVENTORY_MANAGER` (Warehouse carries that one role) — VIEWER and CUSTOMER_SUPPORT are gone — while **Roles in specific firms** still reads `TEST01: ACCOUNTANT · INVENTORY_MANAGER`, untouched. The desktop never names a firm on this call for a platform administrator. *(The plan said "four roles, a different four"; Warehouse has one role, so it is three.)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 and §15.7 — only rows with `firm_id` null move; `user_template.applied` and `user.roles_set` carry no firm, so neither is on TEST01's trail (D-IDN-5).
- **Leaves:** the user with a changed global tier.

### TC-TMPL-008 — After a template, somebody is an ordinary user

- **Covers:** plan 17.7
- **Fixture:** `two-tier-hire`
- **Steps**
  1. As the fixture's **Firm admin**, edit **Two Tier Hire (<suffix>)**: under **Roles in this firm** remove `ACCOUNTANT`, add `CASHIER` → Save & Close → reopen.
- **Expect:** `INVENTORY_MANAGER` and `CASHIER`. **Also applies here** (read-only, lower in the Security section) shows the global tier, `CUSTOMER_SUPPORT` and `VIEWER`, which a firm administrator cannot change. Nothing on the user records a template.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — the TEST01 tier's rows only; audit `user.roles_set` with TEST01.
- **Leaves:** the user with an edited TEST01 tier.

### TC-TMPL-009 — Somebody without role codes has no templates to see

- **Covers:** plan 17.9
- **Fixture:** `sales-executive`
- **Steps:** sign in as the fixture's **Seller**; click the gear and look for a **Platform** part.
- **Expect:** **No Platform part is offered on the Settings page**. `SALES_EXECUTIVE` holds `CUSTOMER_VIEW`, `SALES_VIEW`, `SALES_QUOTATION_CREATE`, `SALES_ORDER_CREATE`, `SALES_INVOICE_CREATE`, `TERRITORY_VIEW` — no `ROLE_VIEW`. **(HTTP)** `GET /api/v1/user-templates` with `X-Firm-ID` of TEST01 → **403**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — reads only.
- **Leaves:** a seller.

### TC-TMPL-010 — Retiring a template is a decision about future hires

- **Covers:** plan 17.8
- **Fixture:** `firm-template-hire`
- **Steps**
  1. As the fixture's **Firm admin**, User Templates → select the fixture's **Job template** → **Delete** (confirm).
  2. Settings > Platform > People > Users → open **Night Counter Hire (<suffix>)**.
  3. Settings > Platform > People > Users → New → open the Job template list.
- **Expect**
  - Step 1: the row leaves the grid (a soft delete; there is no button called Retire).
  - Step 2: still `BILLING_EXECUTIVE` and `CASHIER`.
  - Step 3: the retired template is **not offered**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — `user_templates.is_deleted` true and `user_template.deleted`; the hire's `user_roles` are untouched.
- **Leaves:** a retired template and the user it hired.

### TC-TMPL-011 — A template cannot bundle a platform role

- **Covers:** plan 17.10
- **Fixture:** `firm-admin`
- **Steps (HTTP)** — as the platform administrator, `GET /api/v1/roles?search=PLATFORM_ADMIN` to find its id (a firm admin's own role list never shows it). Then, as the fixture's firm admin, with `X-Firm-ID` of TEST01: `POST /api/v1/user-templates` `{"code": "<suffix>-bad", "name": "Bad", "role_ids": ["<that id>"]}`.
- **Expect:** **422**, "A template cannot bundle platform or cross-firm roles." Nothing created. That role carries every permission code; a template able to name it would be a second door onto the same room.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — the refusal writes nothing.
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
  1. Sign in as the fixture's **Firm admin** → Settings > Platform > People > Users → select **Source Seller (<suffix>)** → **Hire like this person**.
  2. Press **Create** with the form empty.
  3. Name `Clone Test`, email `not-an-email`, any password → Create.
  4. Email `<suffix>.clone@fixtures.local`, password `short` → Create.
- **Expect**
  - Step 1: "Hire like this person": "The new user gets the same roles and firms as Source Seller (<suffix>), and none of their personal details, password or history. You can edit their roles afterwards like any other user." Boxes **Full name**, **Email**, **Initial password** ("They must change it when they first sign in.").
  - Step 2: under each box — "Give the new person a name.", "An email is required.", "An initial password is required." Nothing created.
  - Step 3: "That is not an email." under Email.
  - Step 4: the **server** refuses, shown **on the dialog** in red: "Password does not meet the configured policy." with its reasons — must contain at least 12 characters, an uppercase letter, a digit, a symbol. Every box keeps what was typed.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — every refusal writes nothing.
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
  - Step 3: a **Set a new password** screen instead of the application — Current password, New password, Confirm new password, **Update password** — and nothing else opens until it is done. Afterwards: the source's access and no Platform part on the Settings page. A password somebody else chose is not a password.
- **Data**
  ```sql
  select email, force_password_change, employee_code, joining_date, created_at
  from   platform.users where email = '<suffix>.clone@fixtures.local';
  ```
  `force_password_change` true until step 3, false after. Audit `user.cloned` carrying the source's id.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — a firm administrator's clone copies the TEST01 tier into the TEST01 tier; a platform administrator's copies every tier into the global one (D-IDN-3), in three commits (D-IDN-8), and its copied memberships write no audit row.
- **Leaves:** a clone in TEST01 with its own password.

### TC-HIRE-003 — A clone is a starting point, not a link

- **Covers:** plan 18.7
- **Fixture:** `clone-source`
- **Steps**
  1. As the fixture's **Firm admin**, Hire like this person on **Source Seller (<suffix>)**: `Clone Test Two <suffix>`, `<suffix>.clone2@fixtures.local`, `Welcome@12345` → Create. A second clone, with its own address: TC-HIRE-002 has already taken `<suffix>.clone@fixtures.local`.
  2. Edit the clone: add `CUSTOMER_SUPPORT` under Roles in this firm → Save & Close.
  3. Open **Source Seller (<suffix>)**; close without saving.
- **Expect:** the clone holds `SALES_EXECUTIVE` and `CUSTOMER_SUPPORT`; the source still holds exactly `SALES_EXECUTIVE`.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — the edit writes the clone's `user_roles` alone; the source's rows and `authorization_version` do not move.
- **Leaves:** a clone with one extra role.

### TC-HIRE-004 — Copying access is granting access

- **Covers:** plan 18.8
- **Fixture:** `clone-source`
- **Steps**
  1. Sign in as the fixture's **Source** (a `SALES_EXECUTIVE`) and click the gear: look for Platform > People > Users.
  2. **(HTTP)** As the source, with `X-Firm-ID` of TEST01: `POST /api/v1/users/{their own id}/clone` with `{"email": "<suffix>.x@fixtures.local", "full_name": "x", "password": "Welcome@12345"}`.
- **Expect**
  - Step 1: **No Platform part is offered** (so no Users screen and no Hire like this person).
  - Step 2: **403**. The action needs `ROLE_ASSIGN` — somebody who may open accounts but not grant access must not be able to copy access instead.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — the 403 writes nothing.
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
- **Steps:** sign in as the fixture's **Platform admin** (on Platform) → Settings > Platform > People > **User Templates** → **New**.
- **Expect:** the tab opens with no firm selected — it carries `requiresFirm: false`, since a platform operator has no firm of their own. The General section has an **Offered to** picker: one chip per firm reading `CODE · Name`, helper "Leave blank to offer this job to every firm." A firm administrator's form has no such field. It is create-only.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — reads only; a template saved with a chip carries that firm's `firm_id`, and one saved blank carries none.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §5 and §15.10 — `user_template.created` carries TEST02's id, so it is on TEST02's trail and not TEST01's.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §5 and §15.7 — the platform's rows have `firm_id` null and audit with no firm; the firm administrator's refused writes leave nothing.
- **Leaves:** nothing, once deleted.

### TC-TMPL-015 — A firm administrator cannot write a template for another firm

- **Covers:** plan 19.5
- **Fixture:** `firm-admin`
- **Steps (HTTP)** — as the fixture's firm admin with `X-Firm-ID` of TEST01: `POST /api/v1/user-templates` `{"code": "<suffix>-x", "name": "X", "firm_id": "11111111-1111-1111-1111-111111111111", "role_ids": ["<CASHIER's id>"]}`.
- **Expect:** **422**, "You can only act within your own firm." Nothing created. Refused, not silently redirected.
  - The `firm_id` need not be a real firm: for a firm caller any firm but their own takes the same branch, and a firm administrator cannot read `/api/v1/firms` to find one anyway.
  - `role_ids` must be non-empty and well formed, or validation refuses the body first and the case tests pydantic rather than the firm check. CASHIER's id: `select id from platform.roles where code = 'CASHIER'`.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.7 — the refusal writes nothing.
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
  1. Sign in as the fixture's **Firm admin** → Settings > Platform > People > **Users**.
  2. Select **Manual Hire (<suffix>)** — in TEST01 only — → **Edit**.
- **Expect:** **New** and **Edit** offered; the edit form opens normally, writable.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.3 — reads only; a save would be `user.updated` with a before and no after.
- **Leaves:** unchanged.

### TC-USER-002 — Somebody who also works elsewhere opens read-only, and says why

- **Covers:** plan 20.1b
- **Fixture:** `shared-member`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → select **Shared Member (<suffix>)** → **Edit**.
  2. Double-click the row; then the context menu's **Edit**.
- **Expect:** all three open the record **read-only**, never silently: the subtitle reads "… also works in another firm, so their profile is managed by a platform administrator. Use Roles by firm to set what they do in yours." The refusal is about writing; the row is still one somebody meant to look at, so it opens.
- **Data (HTTP):** in `GET /api/v1/users?search=<suffix>.shared` as the firm admin, the row carries `belongs_to_other_firms: true`.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.3 — the guard counts only **active** memberships elsewhere (D-IDN-10).
- **Leaves:** unchanged.

### TC-USER-003 — New starts in the firm that is open

- **Covers:** plan 20.2, 20.2a, 20.3
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → **New**. Look at **Firms** before typing anything; open its list.
  2. Name `In Firm <suffix>`, email `<suffix>.infirm@fixtures.local`, a 12-character password → Save.
- **Expect**
  - Step 1: **TEST01 already ticked** — the firm open in the switcher — and the list offers the firms *you* belong to (`/api/v1/me/firms`; `/api/v1/firms` is platform-only and answers a firm admin 403). The form used to open empty and then silently remove the membership the save had just made.
  - Step 2: created, in TEST01, in the grid at once.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.3 and §15.4 in `platform` — `users`, one `user_firms` row for TEST01 (primary) that the form's Firms box then replaces; `user.created` with TEST01, `user.firms_set` with none.
- **Leaves:** a TEST01 user.

### TC-USER-004 — Creating somebody in no firm

- **Covers:** plan 20.2b
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → **New**: name `No Firm <suffix>`, email `<suffix>.nofirm@fixtures.local`, password; **clear** the Firms box; no job, no roles → Save.
  2. Settings > Platform > People > Users → **Add existing user** → type `<suffix>.nofirm`.
  3. New again: `<suffix>.nofirm2@fixtures.local`, Firms cleared, and this time pick a role under Roles in this firm → Save. Then look them up as in step 2.
- **Expect**
  - Step 1: created, in **no** firm — allowed and deliberate — and **not** in the grid.
  - Step 2: found, not marked as already a member.
  - Step 3: the form says "Somebody in no firm cannot be given roles here, because roles are held per firm. Save them without roles, then use Add existing user to bring them into this firm and set what they do." — **and no account was created**: the lookup finds no `<suffix>.nofirm2`. Clear Roles and press Save; it saves. Fixed 2026-09-16; see defect **D-20-1**.
  - *Step 1 failed on 2026-09-15 ("User not found." with the user created anyway) and was fixed in #402. Driven on the API: a firm admin's create lands the user in TEST01, clearing the firms leaves none, and the lookup then finds them with `already_a_member: false`. Step 3's order — create, clear firms, then refuse — is read from `saveAssignments`, not seen on screen.*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 in `platform` — clearing Firms soft-deletes the membership `create_user` wrote (`user.firms_set`, no firm); the lookup reads only.
- **Leaves:** two users in no firm.

### TC-USER-005 — A platform administrator's New form

- **Covers:** plan 20.2c, 20.4
- **Fixture:** `platform-admin`
- **Steps:** sign in as the fixture's **Platform admin** → Settings > Platform > People > Users → **New**; look at Firms and open its list.
- **Expect:** Firms is **empty**, not prefilled — a platform administrator has no firm of their own, and quietly using whichever one the switcher shows would be a surprise. The list offers **every** firm (`/api/v1/firms`). Same field, a different source.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.3 — reads only; a platform administrator's `user.created` carries no firm, whichever firms the form then names.
- **Leaves:** nothing (cancel).

### TC-USER-006 — A firm outside your reach is refused by name

- **Covers:** plan 20.5
- **Fixture:** `shared-member`
- **Steps (HTTP)** — as the fixture's firm admin, `X-Firm-ID` TEST01: `PUT /api/v1/users/{Shared Member's id}/firms` with `{"assignments": [{"firm_id": "11111111-1111-1111-1111-111111111111", "is_primary": false, "is_active": true}]}`.
- **Expect:** **422**, "You can only assign firms you administer." Refused, not silently dropped. Any id that is not TEST01's gives it — the reach check runs before the firm-exists check.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — the refusal writes nothing.
- **Leaves:** unchanged.

### TC-USER-007 — A firm administrator's membership write merges

- **Covers:** plan 20.6
- **Fixture:** `shared-member`
- **Steps**
  1. **(HTTP)** As the fixture's firm admin: `PUT /api/v1/users/{Shared Member's id}/firms` naming **TEST01 only**: `{"assignments": [{"firm_id": "<TEST01 id>", "is_primary": false, "is_active": true}]}`.
  2. Sign in as the fixture's **Platform admin** → Settings > Platform > People > Users → Shared Member (or `GET /api/v1/users/{id}/firms`).
- **Expect**
  - Step 1: **200** — naming only your own firm is legitimate.
  - Step 2: **both** memberships, TEST02 still primary. The endpoint replaces for a platform caller and **merges** for a scoped one: memberships outside the caller's reach are carried through untouched, or a firm administrator correcting their own firm would silently remove that person from every other firm. The screen refuses this edit anyway (TC-USER-002); the merge protects the API from any other client.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 in `platform` — TEST02's `user_firms` row untouched, TEST01's written, `authorization_version` +1; `user.firms_set` with no firm and no data, so TEST01's trail does not show it (D-IDN-5).
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — `is_primary` unmoved; the save still bumps `authorization_version` and writes `user.firms_set`.
- **Leaves:** unchanged.

### TC-USER-009 — A Counter Sales hire gets the till and not the ledger

- **Covers:** plan 20.8
- **Fixture:** `firm-admin`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → New: name, `<suffix>.counter@fixtures.local`, password, **Job template** Counter Sales, Roles left alone → Save. (`docs/USER_ADMINISTRATION_GUIDE.md` §3 end to end.)
  2. Sign in as them and read the menu bar; open Accounts, then the Sell and Buy menus.
- **Expect:** **Sell** and **Stock** offered; the only money screens are **Sell > Receipts** and **Buy > Payments**; no Platform part under Settings. No **Accounts** menu at all, so none of Chart of Accounts, Control Accounts, Cost Centres, Profit Centres, Journal Entries, Ledgers, Trial Balance, Profit & Loss, Balance Sheet or Refunds (confirm).
  - **Two opposite failures:** no Receipts or Payments at all means the module gate was reverted and the empty-menu bug is back; the books (Accounts) *offered* means the tabs lost their own codes and the module gate is doing the work alone.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 and §15.7 — `user_template.applied` naming `counter-sales` with CASHIER and BILLING_EXECUTIVE, both TEST01-scoped `user_roles` rows.
- **Leaves:** a Counter Sales user in TEST01.

### Known defects found while writing these cases

- **D-20-1 — Asking for roles on somebody in no firm refused after the account was made. Fixed 2026-09-16.** `saveAssignments` runs after the create and after the membership write, so the refusal "Save them without roles, then use Add existing user…" arrived when the user already existed in no firm. The message read as if nothing was saved, and pressing Save again answered 409 — the words were right and the moment was wrong. `ResourceDefinition` gained `saveRefusal`, a rule about the **combination** of values that the dialog asks before it writes anything, and the user form's check moved there; the sentence is defined once and the old site keeps it as a backstop for any caller reaching the write without the form. Field-level rules stay on the field; this is for the ones no single box can see. `test/save_refusal_keeps_the_record_test.dart` proves nothing is created behind the refusal, and `test/user_create_role_tier_test.dart` pins which combinations are refused.

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
  1. Sign in as the fixture's **Platform admin** → Settings > Platform > People > Users → edit **Shared Member (<suffix>)**. Read the roles field.
  2. Set it to `VIEWER` → Save & Close.
  3. Select the row → **Roles by firm**.
  4. Give TEST01 `SALES_MANAGER` → that section's **Save**.
  5. Give TEST02 `CASHIER` → its Save.
- **Expect**
  - Step 1: labelled **Roles in every firm**, saying it applies in every firm, including ones added later.
  - Step 3: a section per firm they belong to — TEST01 and TEST02, no others. `VIEWER` once at the top under **Applies in every firm**, greyed and unclickable. Each Save is enabled only once its own firm changed.
  - Step 5: TEST02 saved; TEST01 still shows `SALES_MANAGER` — one Save, one firm.
- **Data (HTTP)** as the platform admin: `GET /api/v1/users/{id}/roles` → VIEWER; `.../firms/{TEST01 id}/roles` → SALES_MANAGER; `.../firms/{TEST02 id}/roles` → CASHIER.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — step 2 writes one `firm_id` null row (`user.roles_set`, no firm); steps 4 and 5 one row each with the firm (`user.firm_roles_set`, with the firm).
- **Leaves:** Shared Member with a role in each tier.

### TC-RTIER-002 — Saving the form unchanged keeps every firm's own roles

- **Covers:** plan 20a.6, 20a.8d
- **Fixture:** `shared-member-roles` — VIEWER everywhere, SALES_MANAGER in TEST01, CASHIER in TEST02.
- **Steps**
  1. As the fixture's **Platform admin**, edit **Shared Member (<suffix>)** → **Save** without changing anything.
  2. **Roles by firm**.
- **Expect:** TEST01 still SALES_MANAGER, TEST02 still CASHIER, VIEWER still under Applies in every firm. **The regression case**: before the fix both firms ended up holding every role, globally. One writer per tier, so neither save can touch the other's rows.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — an unchanged save moves no `user_roles` row but still bumps `authorization_version` and writes `user.roles_set`.
- **Leaves:** unchanged.

### TC-RTIER-003 — Each administrator sees the tier they cannot write

- **Covers:** plan 20a.6b, 20a.6c, 20a.6d
- **Fixture:** `shared-member-roles`
- **Steps**
  1. As the fixture's **Firm admin** (TEST01), Settings > Platform > People > Users → open **Shared Member (<suffix>)** (it opens read-only, TC-USER-002) and look under Security.
  2. As the fixture's **Platform admin**, edit the same person.
  3. As the platform admin, Roles by firm → clear TEST02's CASHIER → Save; reopen the form.
- **Expect**
  - Step 1: **Also applies here** shows `VIEWER`, read-only. A global grant applies in their firm, so hiding it made the form report less than the person could do.
  - Step 2: no Also applies here — the roles field already *is* the global set. Instead **Roles in specific firms**, read-only: `TEST01: SALES_MANAGER · TEST02: CASHIER`.
  - Step 3: only `TEST01: SALES_MANAGER`. A firm holding nothing is left out rather than shown empty.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — steps 1 and 2 read; step 3 soft-deletes one row and writes `user.firm_roles_set` with TEST02.
- **Leaves:** Shared Member without the TEST02 role.

### TC-RTIER-004 — A firm administrator's Roles by firm is their firm only, and cannot clear a global grant

- **Covers:** plan 20a.7, 20a.8, 20a.8j
- **Fixture:** `shared-member-roles`
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → select **Shared Member (<suffix>)** → **Roles by firm**.
  2. Remove `SALES_MANAGER` → Save.
- **Expect**
  - Step 1: **one section, TEST01**, with chips that respond. TEST02 is not listed — its Save would be refused by name. `VIEWER` shown greyed under Applies in every firm, not clearable. This dialog used to read the platform-only firm list, answer 403 and show a firm administrator no firm at all.
  - Step 2: removed in TEST01; VIEWER survives. A firm administrator may not undo a platform grant.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — TEST01's row soft-deleted, the global row untouched; `user.firm_roles_set` with TEST01.
- **Leaves:** Shared Member with no TEST01 role.

### TC-RTIER-005 — A platform administrator's New writes the global tier only

- **Covers:** plan 20a.8b, 20a.8c, 20a.8e
- **Fixture:** `platform-admin`
- **Steps**
  1. As the fixture's **Platform admin**, Settings > Platform > People > Users → **New**; read the Security section.
  2. Create `<suffix>.global1@fixtures.local`: Firms TEST01 and TEST02, Roles in every firm `CUSTOMER_SUPPORT` → Save. Select them → **Roles by firm**.
  3. Create `<suffix>.global2@fixtures.local` in TEST01 with **Job template** Read Only → Save → Roles by firm.
- **Expect**
  - Step 1: **Job template**, **Roles in every firm**, and nothing that names a firm. **Apply roles to** is gone.
  - Step 2: both firm sections **empty**; CUSTOMER_SUPPORT under **Applies in every firm**.
  - Step 3: VIEWER under Applies in every firm — the job's roles land in the same tier the Roles field writes.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 in `platform` — `firm_id` null rows only; `user.created` and `user.roles_set` with no firm.
- **Leaves:** two users.

### TC-RTIER-006 — The firm switcher has no say in where a role lands

- **Covers:** plan 20a.8f, 20a.8g
- **Fixture:** `shared-member-roles`
- **Steps**
  1. As the fixture's **Platform admin**, switch into **TEST01**. Settings > Platform > People > Users → edit **Shared Member (<suffix>)**.
  2. Add `CUSTOMER_SUPPORT` to the roles field → Save → Roles by firm.
- **Expect**
  - Step 1: **one** roles field, **Roles in every firm**, plus the read-only **Roles in specific firms** listing both firms — TEST01 included. No second column. The helper says a role in one firm only is set under Roles by firm.
  - Step 2: CUSTOMER_SUPPORT under **Applies in every firm**; no firm section changed.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — the row lands with `firm_id` null whatever the switcher says.
- **Leaves:** Shared Member with a second global role.

### TC-RTIER-007 — A firm administrator's form

- **Covers:** plan 20a.8h, 20a.8i
- **Fixture:** `two-tier-hire` — global VIEWER and CUSTOMER_SUPPORT; TEST01 ACCOUNTANT and INVENTORY_MANAGER.
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Platform > People > Users → edit **Two Tier Hire (<suffix>)**.
  2. Press **Roles by firm** in the dialog footer; close it. Close the form, open it in **view**, press it again.
- **Expect**
  - Step 1: the roles field labelled **Roles in this firm** (ACCOUNTANT, INVENTORY_MANAGER) and **Also applies here** showing CUSTOMER_SUPPORT and VIEWER read-only. Nothing names a firm.
  - Step 2: the per-firm editor opens without closing the form, from edit and from view.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — reads only.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — every refusal writes nothing; a platform administrator's global-tier save is held to nothing at all (D-IDN-3).
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
  1. Sign in as the fixture's **Firm admin** → Sell > Returns & notes > **Credit Notes** → **Raise credit note**.
  2. Open the **Invoice** picker and look for the fixture's two invoice numbers and its delivery note number.
  3. Pick the approved invoice; open **Line**.
  4. Enter an amount below what the line was charged (it was charged 590.00: 5 × 100 plus 18% GST) → **Raise**.
- **Expect**
  - Step 1: the dialog is titled **Raise a credit note**, its button reads **Raise** — this screen is hand-built, so nothing is called New or Save.
  - Step 2: the **approved** invoice is offered; the **cancelled** one is not, and no `DN-…` number is. Approved sales invoices with lines, and nothing else.
  - Step 3: the line names its product — **Fixture Product <suffix>** — not `Line 1`.
  - Step 4: a draft is listed. **Approve** and **Cancel** are **row actions** on the right, not toolbar buttons; Approve being there *is* the approve gate this case checks. Leave it a draft — approving posts the credit and reverses declared output tax.
- **Data (HTTP):** `GET /api/v1/credit-notes` with `X-Firm-ID` TEST01 lists the draft against the fixture's invoice.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 for the grant, §11.17 for the credit note.
- **Leaves:** a draft credit note in TEST01.

### TC-GRANT-002 — Proforma opens

- **Covers:** plan 21.2
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, Sell > All Sell screens > Documents > **Proforma**.
- **Expect:** offered, and a real screen — a grid or a proper empty state, never a "coming soon" placeholder. A proforma states what an approved order **will** be charged and **posts nothing**; its number comes from its own `PF` series, not the tax invoice's.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — the grant is `FIRM_ADMIN`'s `role_permissions`; the screen reads only (§11.18).
- **Leaves:** a firm admin user.

### TC-GRANT-003 — E-Invoice opens, and never says LIVE

- **Covers:** plan 21.3
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, Accounts > All Accounts screens > Tax filing > **E-Invoice**.
- **Expect:** offered and opens. Wherever a mode is shown it reads **`SANDBOX`**; if it reads LIVE anywhere, stop — that is not cosmetic. `mode` is NOT NULL with no server default on both e-invoice tables, and the sandbox marks every reference it mints `SBX…`. *(TEST01 has registered nothing, so the grid may be empty and show no mode at all; that passes.)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — the grant; what the screen reads is §13.8.
- **Leaves:** a firm admin user.

### TC-GRANT-004 — Loyalty: the banner states the scheme, and a firm can change it

- **Covers:** plan 21.4, 21.4a
- **Fixture:** `firm-admin`
- **TEST01's scheme is shared by every run.** It starts **off**; switch it back off at the end.
- **Steps**
  1. As the fixture's **Firm admin**, Settings > Set up > Pricing > **Loyalty**. Read the banner.
  2. **Scheme settings** → switch **Scheme is running** on; **Minimum to redeem** `50`; **Points expire** off → Save.
  3. Scheme settings → switch **Scheme is running** off → Save.
- **Expect**
  - Step 1: "No scheme is running: nobody is earning anything."
  - Step 2: the dialog saves and the banner re-reads: "1 points per 100, worth 1 each and never expire. At least 50 before any can be spent."
  - Step 3: back to "No scheme is running…".
  - *Until #399 there was no editor at all: the settings route, the code and the grant existed, and the desktop carried only the read.*
- **Data (HTTP):** `GET /api/v1/loyalty/settings` with `X-Firm-ID` TEST01 after each save.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 for the grant, §14.15 for the scheme.
- **Leaves:** TEST01's scheme off, minimum 50.

### TC-GRANT-005 — Loyalty settings are readable by somebody who cannot change them

- **Covers:** plan 21.4b
- **Fixture:** `loyalty-viewer` — `SALES_MANAGER`, which holds `LOYALTY_VIEW` and not `LOYALTY_MANAGE_SETTINGS`.
- **Steps**
  1. Sign in as the fixture's **Loyalty viewer** → Settings > Set up > Pricing > Loyalty → **Scheme settings**.
  2. **(HTTP)** As them, `PUT /api/v1/loyalty/settings` with the body `GET` returned.
- **Expect**
  - Step 1: it **opens**, read-only, saying "Changing the scheme needs the manage loyalty settings permission." Offered rather than hidden on purpose: whoever is asked why a balance is what it is should reach the rule behind it.
  - Step 2: **403**. Whoever a scheme constrains must not rewrite what it is worth.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.15 in `test_fixtures` — the read and the refused PUT write nothing. A permitted save writes `loyalty.settings_changed` with the five figures on both sides; changing `amount_per_point` re-prices points already held (D-CFG-3).
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — the grant: SALES_MANAGER's `role_permissions` carry `LOYALTY_VIEW` and not `LOYALTY_MANAGE_SETTINGS`.
- **Leaves:** a sales manager.

### TC-GRANT-006 — TCS settings open, and TCS is off

- **Covers:** plan 21.5
- **Fixture:** `firm-admin`
- **Steps:** as the fixture's **Firm admin**, Accounts > All Accounts screens > Tax filing > **TCS** → **Settings**; save without changing anything.
- **Expect:** offered, opens and saves. **Collect under section 206C(1H)** is off — it defaults false so shipping the feature charged nobody. Leave it off: on, every receipt in TEST01 collects TCS, and other cases record receipts there.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — the grant; the settings row is §13.11.
- **Leaves:** a firm admin user.

### TC-GRANT-007 — The fix was a grant, not a wider gate

- **Covers:** plan 21.6
- **Fixture:** `sales-executive`
- **Steps:** sign in as the fixture's **Seller**; open **Sales**, then **Masters**.
- **Expect:** Sales is offered — `SALES_VIEW` is one of their six codes — with **no** Credit Notes, Proforma, E-Invoice or TCS; Masters has **no** Loyalty. Any of the five appearing means a tab lost its own code and its module gate is carrying it alone.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — reads only; SALES_EXECUTIVE's `role_permissions` are unchanged.
- **Leaves:** a seller.

### TC-GRANT-008 — The server grants all five

- **Covers:** plan 21.8
- **Fixture:** `firm-admin`
- **Steps (HTTP)** — as the fixture's firm admin with `X-Firm-ID` TEST01: `GET /api/v1/credit-notes`, `/api/v1/proforma-invoices`, `/api/v1/einvoice/registrations`, `/api/v1/loyalty/settings`, `/api/v1/tcs/settings`.
- **Expect:** **200** on all five. They answered 403 before `20260906_0130`. The screens being offered is the desktop honouring the claims; these are the claims being there.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — reads only; the codes come from `firm_permissions[TEST01]` in the firm administrator's token.
- **Leaves:** a firm admin user.

---

## A cashier can see the till

`CASHIER` holds exactly `RECEIPT_CREATE`, `RECEIPT_VIEW`, `PAYMENT_CREATE` and
`PAYMENT_VIEW`, and was offered **no module at all**: Receipts and Payments
were Finance tabs, Finance was gated on `ACCOUNT_VIEW`, and a tab naming no codes
inherits its module's. The module now takes any of `ACCOUNT_VIEW`, `RECEIPT_VIEW`,
`PAYMENT_VIEW`, **and every tab names its own code** — both halves are
load-bearing. In the 1.3.0 menu Receipts is on **Sell** and Payments on **Buy**;
the other ten screens are on **Accounts** and in Settings > Set up > Account structure.

The module's twelve screens: Chart of Accounts (Accounts > All Accounts screens),
Control Accounts, Cost Centres, Profit Centres (Settings > Set up > Account
structure), Journal Entries, Ledgers, Trial Balance, Profit & Loss, Balance
Sheet (Accounts), Receipts (Sell), Payments (Buy), Refunds (Sell > All Sell
screens > Money).

### TC-CASH-001 — A cashier gets the till, holding Receipts and Payments only

- **Covers:** plan 22.0, 22.1, 22.2, 22.3
- **Fixture:** `cashier` — `CASHIER` alone, no job template. That combination is the whole setup: the seeded Counter Sales template pairs CASHIER with BILLING_EXECUTIVE, which is what hid the bug.
- **Steps:** sign in as the fixture's **Cashier**; read the menu bar; open the Sell and Buy menus and look for Accounts.
- **Expect:** The menu bar offers Sell and Buy (before the fix it was empty), with exactly **Sell > Receipts** and **Buy > Payments**. **No Accounts menu**, so **none** of Chart of Accounts, Control Accounts, Cost Centres, Profit Centres, Journal Entries, Ledgers, Trial Balance, Profit & Loss, Balance Sheet, Refunds. Widening the module without gating its tabs would have handed a cashier the ledger.
- **Data (HTTP):** as the cashier with `X-Firm-ID` TEST01, `GET /api/v1/finance/ledger-accounts` → **403**.
- **Leaves:** a cashier.

### TC-CASH-002 — Recording a receipt, with a searchable party picker

- **Covers:** plan 22.4, 22.4a
- **Fixture:** `cashier`
- **Steps**
  1. As the fixture's **Cashier**, Sell > Receipts → **Record Receipt**.
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
- **Steps:** sign in as the fixture's **Accountant** → open Accounts, Sell > Receipts and Buy > Payments.
- **Expect:** **all twelve** tabs. `ACCOUNTANT` carries `ACCOUNT_VIEW`, `JOURNAL_VIEW`, `RECEIPT_VIEW`, `PAYMENT_VIEW`, `LEDGER_VIEW`, `TRIAL_BALANCE_VIEW`, `PROFIT_LOSS_VIEW` and `BALANCE_SHEET_VIEW`; every code now on a tab is one whoever held `ACCOUNT_VIEW` already had, so nobody lost one.
- **Leaves:** an accountant.

### TC-CASH-004 — A firm administrator keeps all twelve

- **Covers:** plan 22.6
- **Fixture:** `firm-admin`
- **Steps:** sign in as the fixture's **Firm admin** → open Accounts, Sell > Receipts, Buy > Payments and Settings > Set up > Account structure.
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
- **Steps:** sign in as the fixture's **Platform admin**, no firm selected → Settings > Platform > System > **Audit Logs**.
- **Expect:** the **platform** trail — user, role and firm administration: `identity.login`, `user.created`, `user.firm_roles_set` and the like, including the fixture's own setup a moment ago. Each row names who did it. *(Answered 403 between 2026-09-05 and 09-06: the designation had moved claims and the check had not.)*
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.10 — reads only; with no firm selected the platform trail holds every firm's platform rows as well as the platform's own.
- **Leaves:** a platform administrator.

### TC-AUDIT-002 — Selecting a firm switches to that firm's trail

- **Covers:** plan 23.2
- **Fixture:** `platform-admin`
- **Steps:** as the fixture's **Platform admin**, switch into **TEST01** (the header changes from Platform, the menu bar grows) → Settings > Platform > System > Audit Logs.
- **Expect:** **TEST01's** trail — firm-owned work such as `customer.created`, `sales_invoice.created`, `settlement.receipt.recorded` from fixtures that sold or took money in TEST01 — with platform rows carrying TEST01's id interleaved. Not the platform trail of TC-AUDIT-001: selecting a firm is what sets `X-Firm-ID`.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.10 — reads only: TEST01's store merged with the platform rows carrying TEST01's id.
- **Leaves:** a platform administrator.

### TC-AUDIT-003 — A firm administrator reads their own firm's history, naming people

- **Covers:** plan 23.3, 23.4, 23.5
- **Fixture:** `firm-admin`
- **Steps:** sign in as the fixture's **Firm admin** → **Settings**; read Audit Logs; look for Diagnostics.
- **Expect**
  - Settings opens with **Audit Logs** in it. It used to open empty — offered on `SETTINGS_VIEW` with both tabs demanding codes the role lacked.
  - TEST01's history and nothing else. **Every row names the person who did it** and, where the subject is a person, who it was done to (#407, #409).
  - **No Diagnostics.** Error reports are telemetry for whoever maintains the product, not something a firm owns.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.10 — reads only; every membership change, and whatever a platform administrator did to TEST01's people and roles, is not among the rows it can show (D-IDN-5).
- **Leaves:** a firm admin user.

### TC-AUDIT-004 — A promotion lands in the firm's trail, in time order, and a filter reaches both stores

- **Covers:** plan 23.4a, 23.4b, 23.4c
- **Fixture:** `manual-hire`
- **Steps**
  1. As the fixture's **Firm admin**: Masters > Customers → New `<SUFFIX>-A`, name `Audit Before <suffix>` → Save.
  2. Settings > Platform > People > Users → **Manual Hire (<suffix>)** → **Apply job template** → Counter Sales → Apply.
  3. Masters > Customers → New `<SUFFIX>-B`, name `Audit After <suffix>` → Save.
  4. Settings > Platform > System > **Audit Logs**. Read the top rows.
  5. Filter by action `user_template.applied` — **typed in full**.
- **Expect**
  - Step 4: from the top, `customer.created` (Audit After), `user_template.applied` and `user.roles_set` (both naming Manual Hire), `customer.created` (Audit Before) — **strictly descending timestamps straight through**. The promotion is written to the *platform* store (user administration is a platform path) and the customers to TEST01's; nothing marks which came from where. A block of user-administration rows at one end and customers in another means the stores were concatenated, not merged. The promotion names the template **and the role codes it granted** — `role_codes` beside `role_ids`, `template_code` beside `template_id`.
  - Step 5: the promotion is found. A filter that reached one store and not the other would answer a half-truth that reads as correct because something came back. *(Exact match: `user` finds nothing — BACKLOG 31.17.)*
- **Data (HTTP)**, as the firm admin with `X-Firm-ID` TEST01: `GET /api/v1/audit-logs?page_size=10` shows the order; `?action=user_template.applied` returns the row with `after_data.role_codes: ["BILLING_EXECUTIVE", "CASHIER"]`.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.10 — `user_template.applied` and `user.roles_set` carry TEST01 because a TEST01 administrator made them; the same promotion by a platform administrator naming no firm would not be on this screen (D-IDN-5).
- **Leaves:** two customers in TEST01 and Manual Hire on Counter Sales.

### TC-AUDIT-005 — The platform trail needs platform authority

- **Covers:** plan 23.6
- **Fixture:** `firm-admin`
- **Steps (HTTP):** `GET /api/v1/audit-logs` as the fixture's firm admin with **no** `X-Firm-ID`.
- **Expect:** **403**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.10 — the refusal writes nothing.
- **Leaves:** a firm admin user.

### TC-AUDIT-006 — Somebody with none of the three codes has no Settings at all

- **Covers:** plan 23.7
- **Fixture:** `sales-executive`
- **Steps:** sign in as the fixture's **Seller**; read the menu bar and open the gear.
- **Expect:** **No Platform part** on the Settings page, so no Audit Logs card — withheld, not an empty screen (confirm: the gear itself stays, because This PC and me is everybody's). A screen that opens and does nothing reads as broken rather than withheld.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.10 — reads only.
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
  1. Sign in as the fixture's **Firm admin** → Settings > Platform > People > Users → **Add existing user**, with no row selected.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — reads only.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 and §15.7 — one `user_firms` row for TEST01, TEST02's untouched; `user.firms_set` with no firm, so the addition is not on TEST01's trail (D-IDN-5); the job's rows as TC-TMPL-003.
- **Leaves:** Outsider in TEST01 as Counter Sales.

### TC-LOOK-003 — Their profile is not yours; their roles here are

- **Covers:** plan 24.9, 24.9a, 24.10
- **Fixture:** `outsider-added` — Outsider is already in TEST01 as Counter Sales.
- **Steps**
  1. As the fixture's **Firm admin**, select **Outsider (<suffix>)** → **Edit**; double-click the row; the context menu's Edit.
  2. Select them → **Apply job template** → Warehouse → Apply. Then **Roles by firm**.
  3. Sign in as the fixture's **Platform admin** → Settings > Platform > People > Users → Outsider → Edit.
- **Expect**
  - Step 1: all three open **read-only**, the subtitle saying they also work in another firm, so their profile is managed by a platform administrator, and Roles by firm is what to use.
  - Step 2: both work. Roles by firm shows **one section, TEST01** — not TEST02, though they work there: the dialog offers only firms you hold `USER_CREATE` in.
  - Step 3: **editable** — correct, not a hole. A platform administrator sees every firm, so nothing is hidden from them, and they are exactly who step 1's message points to.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — the template writes TEST01's tier only; the refused profile edit writes nothing.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — reads only.
- **Leaves:** unchanged.

### TC-LOOK-005 — Reaching across firms is not reading your own people

- **Covers:** plan 24.14, 24.15, 24.16
- **Fixture:** `sales-executive` and `firm-admin` (two runs, or any two)
- **Steps**
  1. Sign in as the `sales-executive` fixture's **Seller**; look for Settings > Platform > People > Users.
  2. **(HTTP)** As the seller with `X-Firm-ID` TEST01: `GET /api/v1/users/lookup?q=fixtures`.
  3. **(HTTP)** As the `firm-admin` fixture's firm admin: `GET /api/v1/users/lookup?q=`, then `?q=fixtures.local&page=2&page_size=2`.
- **Expect**
  1. No Platform part on the Settings page, so no Add existing user.
  2. **403** — the lookup needs `USER_CREATE`, deliberately not `USER_VIEW`.
  3. **422**, "Type at least 3 characters to look somebody up." — an empty term is the shortest of all. Page 2: **empty**, and a plain `?q=fixtures.local` returns **10** however many match: a firm caller gets "is this them?", not "who works here?".
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — reads only.
- **Leaves:** unchanged.

### TC-LOOK-006 — A platform administrator gets the directory

- **Covers:** plan 24.17, 24.18, 24.19, 24.20
- **Fixture:** `outsider`
- **Steps**
  1. Sign in as the fixture's **Platform admin**, switch into **TEST01** → Settings > Platform > People > Users → **Add existing user**.
  2. Type `e`; clear the box.
  3. Type `<suffix>.outs`, pick Outsider, Add, close. Open Add existing user again and type `<suffix>`.
  4. **(HTTP)** As the platform admin with `X-Firm-ID` TEST01: `GET /api/v1/users/lookup?q=&page=1&page_size=2`.
- **Expect**
  - Step 1: the dialog **opens already listing** everyone with an account who is not in TEST01, no typing. Helper: "Leave blank to list everyone not yet in this firm." TEST01's own people are **not** listed, and no platform administrator is — the fixture's firm admin and platform admin are both absent.
  - Step 2: filtered on one character; the three-character rule is a firm caller's. Clearing brings the full list back.
  - Step 3: Outsider is added, and **absent** the second time. A firm caller's lookup *flags* a member; a platform caller's directory *excludes* them.
  - Step 4: two rows and a `pagination` block whose `total_records` is everybody not in TEST01.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 in `platform` — the Add writes one `user_firms` row and `user.firms_set` with no firm.
- **Leaves:** Outsider in TEST01 with no roles there.

### TC-LOOK-007 — User-Firm Assignments is a platform administrator's screen

- **Covers:** plan 24.21, 24.22
- **Fixture:** `template-offering` (a firm admin and a platform admin)
- **Steps:** open Settings > Platform > People as the fixture's **Firm admin**; then as its **Platform admin**, with no firm and then with TEST01 selected.
- **Expect:** the firm admin sees Users, Roles, Permissions and User Templates — **no User-Firm Assignments**; Settings > Platform > People > Users → Edit → Firms and Add existing user are their ways to the same thing. The platform admin sees **User-Firm Assignments**, with the Firm filter, either way. A tab-level `requiresPlatformAdmin`, because a platform administrator passes code checks by designation.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — reads only. For a `PLATFORM` operator User-Firm Assignments is blank and refuses every write (D-IDN-6).
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
  2. Click the gear → Platform > People > **Roles**.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.5 — reads only.
- **Leaves:** a firm admin user.

### TC-ROLE-002 — Creating a custom role; the platform's codes are never offered

- **Covers:** plan 25.2, 25.3, 25.4
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**, TEST01 selected.
  2. Settings > Platform > People > Roles → **New**.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.5 — `role.created` and `role.permissions_set`, TEST01's id, no data — the trail cannot say which codes the role got (D-IDN-5).
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.5 — a refused code writes nothing; a code any other firm or any deleted role holds is refused as well (D-IDN-9).
- **Leaves:** a firm admin user.

### TC-ROLE-004 — A firm admin *holds* `AUDIT_LOG_VIEW` and cannot *grant* it

- **Covers:** plan 25.4a
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**, TEST01 selected.
  2. Click the gear → Platform > System > **Audit Logs**.
  3. Settings > Platform > People > Roles → **New** → Permissions → search `AUDIT_LOG_VIEW`. Cancel.
- **Expect**
  - Step 2: **opens**, on TEST01's trail.
  - Step 3: **not offered**.
  - That is not a contradiction. `PLATFORM_PERMISSION_CODES` answers "what may a firm administrator not *grant*", a different question from what they may hold. `AUDIT_LOG_VIEW` was granted to `FIRM_ADMIN` directly on 2026-09-06. Confusing the two sets is how a permission's reach gets misjudged.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.5 — the refused grant writes nothing.
- **Leaves:** a firm admin user.

### TC-ROLE-005 — A template can bundle the firm's own custom role

- **Covers:** plan 25.6
- **Fixture:** `custom-role`
- **Steps**
  1. Sign in as the fixture's **Firm admin**, TEST01 selected.
  2. Settings > Platform > People > **User Templates** → **New**.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.5 and §15.7.
- **Leaves:** a custom role and a template.

### TC-ROLE-006 — Hiring into a template grants exactly its roles

- **Covers:** plan 25.7
- **Fixture:** `custom-template`
- **Steps**
  1. Sign in as the fixture's **Firm admin**, TEST01 selected.
  2. Settings > Platform > People > **Users** → **New**.
  3. Full name anything; email `<suffix>.hire@fixtures.local`; **Initial password** the fixture's password (twelve or more characters — the form does not say which rule it refused on if shorter).
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.7.
- **Leaves:** a custom role, a template, a user.

### TC-ROLE-007 — A custom role's codes become exactly those screens

- **Covers:** plan 25.8
- **Fixture:** `role-holder`
- **Steps**
  1. Sign in as the fixture's **Role holder** (no password change is asked for). TEST01 is their only firm.
  2. Read the menu bar, and open each menu to see its screens.
- **Expect** — exactly these, taken from the desktop's own visibility and menu logic (confirm: translated from the catalogue; not driven on the 1.3.0 menu):

  | Menu | Screens inside |
  | --- | --- |
  | **Sell** | Quotations, Sales Orders, Delivery Notes, Sales Invoices, Returns & notes (Sales Returns), **Receipts** (with **Record Receipt** offered), Customer Statements |
  | **Accounts** | GST Returns |
  | **Masters** | Customers |

  **No** Buy, Stock or Reports menu, and no Platform part and no Money screen other than Receipts on the Settings page. Four codes — `SALES_VIEW`, `CUSTOMER_VIEW`, `RECEIPT_VIEW`, `RECEIPT_CREATE` — rendered as screens.
- **Why Receipts is offered at all:** the role carries `RECEIPT_VIEW` beside `RECEIPT_CREATE`. With the create code alone there is no Receipts screen to record on — the screen opens on the view code — which is the mistake plan row 25.3 used to make.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.6 — reads only; the codes are the role's live `role_permissions`, in `firm_permissions[TEST01]`.
- **Leaves:** a custom role and a holder.

### TC-ROLE-008 — Editing a role signs out everyone holding it

- **Covers:** plan 25.9
- **Fixture:** `role-holder`
- **Steps** — two windows:
  1. **Window A:** sign in as the fixture's **Role holder**. Open Sell > Receipts. **Record Receipt** is there.
  2. **Window B:** sign in as the fixture's **Firm admin**, TEST01 selected. Roles → the fixture's **Custom role** → **Edit** → untick **`RECEIPT_CREATE`** → **Save**.
  3. **Window A:** click anything.
  4. Sign back in as the holder. Sell > Receipts.
- **Expect**
  - Step 3: **signed out on that click** — nobody asked them to. Editing a role revokes every holder's tokens.
  - Step 4: the **menu is unchanged** (the table in TC-ROLE-007), and on Receipts **Record Receipt is gone**. `RECEIPT_CREATE` gates the button, not the screen.
  - A role is not versioned: editing it changes everybody holding it, immediately.
- **Data**
  ```sql
  select email, authorization_version from platform.users
  where  email = '<suffix>.holder@fixtures.local';
  ```
  Run before and after step 2: **`authorization_version` goes up by one**. That column is the sign-out. Audit `role.permissions_set`.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.5 — confirmed on `t0918nhew`: 1 → 2 at 21:35:23 IST on 2026-09-18.
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
  - Step 3: **signed out** on the click; signed back in, an **empty menu bar** — nothing offered but Home and the gear — and nothing on screen says why.
  - Recorded as the behaviour, **not a defect**. Whether deleting a held role should refuse, or warn with the count, is an open decision for the owner.
- **Data**
  ```sql
  select r.code, r.is_deleted, ur.is_deleted as holder_row_deleted
  from   platform.roles r
  join   platform.user_roles ur on ur.role_id = r.id
  where  r.code = '<suffix>-night-desk';
  ```
  `roles.is_deleted` is **true**; the holder's `user_roles` row is **left in place** — it names a deleted role, and the token simply stops carrying its codes. Audit `role.deleted`.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.5 — confirmed on the 2026-09-16 and 09-17 runs; recorded in `docs/DEFECTS.md` as an open decision, not a defect.
- **Leaves:** a deleted custom role, and a holder with nothing.

---

## Platform mode — the switcher and what a platform administrator starts on

A platform administrator with reach over every firm, and a member of none, used
to get a token carrying every code — so the menu offered Sell and
Stock — and an empty firm switcher, so every one of those screens refused
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 and §14.17.
- **Leaves:** a platform administrator.

### TC-PLAT-002 — Platform mode offers the platform, and nothing that needs a firm

- **Covers:** plan 26.2, 26.3
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. The header reads **Platform**.
  2. Read the menu bar. Click the gear and read its three parts.
- **Expect** — taken from the desktop's own visibility and menu logic:

  | Where | Screens inside |
  | --- | --- |
  | **Menu bar** | Home and the gear only (no firm is chosen) |
  | **Settings > Platform > People** | Users · Roles · Permissions · User Templates · User-Firm Assignments |
  | **Settings > Platform > Firms** | Firms · Business Profiles |
  | **Settings > Platform > Agency** | Branding |
  | **Settings > Platform > System** | Audit Logs · Diagnostics · Licensing · Backups · Platform Dashboard |
  | **Settings > This PC and me** | My Preferences |

  **No** Sell, Buy, Stock, Accounts, Masters or Reports menu, and none of the firm's own Settings (Numbering Series, Tax, Units of Measure, Unit Sets ...) — those live in a firm's own store and need a firm.
- **Why:** `requiresFirm` on a module *and* on a tab hides what needs a firm when none is selected. A platform administrator's token carries every code, so permissions alone would offer everything.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — reads only.
- **Leaves:** a platform administrator.

### TC-PLAT-003 — The switcher lists every firm, and choosing one grows the workspace

- **Covers:** plan 26.4, 26.5, 26.6, 26.7
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**.
  2. Open the firm control.
  3. Pick **TEST01**.
  4. Open **Sell > Sales Orders**.
  5. Open the firm control again and pick **Platform**.
- **Expect**
  - Step 2: a **Platform** entry at the top with a tick beside it, then **every active firm** — TEST01, TEST02, WHOLE01, ELEC01, MEDI01, FOOD01 among them — **although this account is a member of none**.
  - Step 3: a notification names TEST01. The menu bar grows **Sell, Buy, Stock, Accounts, Masters, Reports**, and the Settings page gains the firm's own parts (Firm, Selling, Buying, Stock, Tax, Business profile and SET UP). **Licensing goes away** — it is a platform screen.
  - Step 4: the screen **loads** with no error — whatever orders fixtures have raised in TEST01, or none. Before the fix this module was offered and this screen failed.
  - Step 5: **"Working on the platform. No firm is selected."** The firm-owned modules go away again.
- **Data (HTTP)** — the switcher's source:
  ```
  GET /api/v1/me/firms          (as the fixture's platform admin)
  ```
  Every active firm, each with `is_primary: false` — there is no membership row, so nobody's primary. The same call as a firm user returns only their own firms.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — every live, active firm, primary first by an explicit `case` rather than NULL order.
- **Leaves:** a platform administrator.

### TC-PLAT-004 — Being a member of firms does not change where a platform administrator lands

- **Covers:** plan 26.9
- **Fixture:** `platform-admin-member`
- **Steps**
  1. Sign in as the fixture's **Platform admin** — this one *is* a member of TEST01 (primary) and TEST02.
  2. Read the header; open the firm control.
- **Expect:** still starts on **Platform**. The switcher looks as in TC-PLAT-003, with TEST01 marked **primary**. Membership is not what decides the landing; the designation is.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — reads only; an `ALL_FIRMS` administrator's memberships add nothing to the token — `firm_permissions` is not built for them.
- **Leaves:** a platform administrator with two memberships.

### TC-PLAT-005 — A firm user never sees Platform

- **Covers:** plan 26.10
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**.
  2. Read the header; open the firm control.
- **Expect:** **no Platform entry** anywhere; TEST01 selected and the only firm; lands in it. For an ordinary user a null firm is an empty application rather than a mode, so the switcher refuses to offer it.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — reads only.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — reads only (`GET /me`).
- **Leaves:** a two-firm user.

### TC-ME-002 — Choosing your own primary firm

- **Covers:** plan 26a.3, 26a.4; backlog 73 (since 1.2.0 the choice is *Start in firm* in My preferences)
- **Fixture:** `two-firm-user`
- **Steps**
  1. Sign in as the fixture's **Two-firm user**.
  2. Account menu → **My preferences**.
  3. **Start in firm** → **TEST02** → **Save**.
  4. Open the firm switcher.
- **Expect**
  - Step 2: the dialog opens at once, **Start in firm** reading **TEST01** and listing only TEST01 and TEST02. The account menu has **no separate Primary firm entry** any more.
  - Step 3: the dialog closes. **Nothing on screen switches** — the primary is for next time, not for now.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — `user.primary_firm_set` with the firm; no `authorization_version` move.
- **Leaves:** a two-firm user whose primary is TEST02.

### TC-ME-003 — Signing in lands in the primary firm, not the last one used

- **Covers:** plan 26a.5
- **Fixture:** `two-firm-user`
- **Steps**
  1. Sign in as the fixture's **Two-firm user** (primary: TEST01).
  2. Switch to **TEST02** and open any screen there.
  3. Sign out, sign back in.
- **Expect:** you land in **TEST01**, the primary — not TEST02, where you were last. Switching is for the session; the primary is for next time. Until 2026-09-08 it was the reverse, so the flag meant nothing to anybody who had ever switched.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.1 and §15.4 — sign-in writes §15.1's rows; where it lands is `user_firms.is_primary`.
- **Leaves:** a two-firm user.

### TC-ME-004 — Nobody can make a firm they do not belong to their primary

- **Covers:** plan 26a.7
- **Fixture:** `two-firm-user`
- **Steps (HTTP)** — sign in as the fixture's user and send:
  ```
  PUT /api/v1/me/primary-firm
  { "firm_id": "<the id of a firm this account does not belong to>" }
  ```
  Get that id as a platform administrator, from `GET /api/v1/firms`, choosing one this account is not a member of.
- **Expect:** **422**, "You can only make a firm you belong to your primary firm." Nothing changes.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — the refusal writes nothing.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.4.
- **Leaves:** a two-firm user.

### TC-ME-006 — A platform administrator's menu

- **Covers:** plan 26a.6 (platform half), 26a.9
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**.
  2. Open the account menu; open **My profile**.
- **Expect:** the menu offers **My preferences**, and the dialog has **no Start in firm** box — a platform administrator always starts on Platform, so there is nothing to choose. My profile shows a **Platform administrator** chip under the name.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — reads only.
- **Leaves:** a platform administrator.

### TC-ME-007 — Somebody in one firm has no primary to choose

- **Covers:** plan 26a.6 (one-firm half)
- **Fixture:** `firm-admin`
- **Steps:** sign in as the fixture's **Firm admin**, open the account menu → **My preferences**.
- **Expect:** **no Start in firm** box. It is offered only to somebody with more than one firm who is not a platform administrator.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — reads only.
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
  6. Current password: the fixture's password, new password `Str0ng-Passw0rd!` twice.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.2.
- **Leaves:** a two-firm user whose password is `Str0ng-Passw0rd!`.

### TC-ME-009 — My preferences: theme, text size and date format apply at once

- **Covers:** backlog 73 (My preferences, 1.2.0)
- **Fixture:** `two-firm-user`
- **Steps**
  1. Sign in as the fixture's **Two-firm user**; open any sales invoice and note how its date is written.
  2. Account menu → **My preferences**. Change nothing → **Save**.
  3. Open it again: **Theme** → **Dark**, **Text size** → **Large**, **Date format** → the `yyyy-MM-dd` row → **Save**.
  4. Open the same sales invoice again.
  5. Open My preferences, change the theme, then press **Esc**.
  6. Sign out, sign in on **another PC** (or another Windows account) as the same user.
- **Expect**
  - Step 1: dates read `dd-MM-yyyy` (for example `04-10-2026`) — the default for everybody after the 1.2.0 upgrade.
  - Step 2: the dialog closes; nothing changes.
  - Step 3: the dialog closes and, without restarting, the screen turns dark and the text grows. Each date-format row shows today's date written that way.
  - Step 4: the invoice date now reads `2026-10-04` style.
  - Step 5: the dialog closes and the theme stays as it was.
  - Step 6: the dark theme and the `yyyy-MM-dd` dates follow the user; **text size does not** — it is this PC's setting, and the dialog says *This PC only*.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.4 — this user's `platform.user_preferences` row: `preferred_theme_mode = dark`, `date_format = yyyy-MM-dd`. Opening the dialog reads nothing; Save sends one update carrying only the changed fields; Save with nothing changed sends none.
- **Leaves:** a two-firm user with the dark theme and ISO dates — set them back if the next case needs the defaults.

### TC-ME-010 — My preferences: the first screen

- **Covers:** backlog 73
- **Fixture:** `two-firm-user`
- **Steps**
  1. Sign in as the fixture's **Two-firm user**. Account menu → **My preferences** → open the **First screen** list.
  2. Choose Sell > **Sales Invoices** → **Save**.
  3. Open Customers, then sign out and back in.
  4. Set **First screen** back to **The screen I was last on**; open Customers; sign out and back in.
- **Expect**
  - Step 1: the first entry is **The screen I was last on** (selected); below it only screens this user's roles may open — no Users, Roles or Firms.
  - Step 3: you land on **Sales Invoices**, not Customers.
  - Step 4: you land on **Customers**, where you were last.
- **Data:** `platform.user_preferences.dashboard_layout` holds `first_screen` beside `favourites` (§15.4).
- **Leaves:** a two-firm user starting where they left off.

### TC-ME-011 — Favourites: star a screen, find it on Home and in Ctrl+K

- **Covers:** D-UI-3 (fixed in 1.2.0)
- **Fixture:** `two-firm-user`
- **Steps**
  1. Sign in as the fixture's **Two-firm user**. Open **Sell**; point at **Sales Orders** and click the star that appears. Star one more screen in another drop-down.
  2. Go to **Home**.
  3. On Home, drag the last favourite before the first; point at another box and click its **x**.
  4. Press **Ctrl+K** and type `s`.
  5. Sign out; sign in on another PC (or another Windows account) as the same user.
- **Expect**
  - Step 1: each star turns gold as it is clicked; the drop-down stays open.
  - Step 2: the **FAVOURITES** box shows the starred screens.
  - Step 3: the order changes and the removed box goes; that screen's star in its drop-down is no longer gold.
  - Step 4: starred screens are listed **first** among the matches.
  - Step 5: the same favourites, in the same order.
- **Data:** `platform.user_preferences.dashboard_layout.favourites` lists the screens in order. Several stars in a row are saved by **one** update about a second after the last.
- **Leaves:** a two-firm user with favourites.

### TC-ME-012 — The light menu: daily work first, everything one click away

- **Covers:** backlog 72 (light menu, 1.2.0)
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin**. Open **Sell**.
  2. Click **Returns & notes**.
  3. Click **All Sell screens** at the foot.
  4. Open **Buy**, **Stock**, **Accounts** and **Masters** the same way.
  5. Look along the menu bar for **Admin**.
- **Expect**
  - Step 1: a short list — Quotations, Sales Orders, Delivery Notes, Sales Invoices, Returns & notes, Receipts, Customer Statements — and **All Sell screens (N)** at the foot. Price Lists, Promotions and Territories are **not** here.
  - Step 2: a short list beside it: Sales Returns, Credit Notes, Customer Debit Notes.
  - Step 3: every Sell screen this user may open, under its group (Documents, Money, Incentives, Insight, Field sales); any of them opens in a tab.
  - Step 4: each area works the same way; Masters shows Customers, Vendors, Products, Branches and Warehouses, and its lists (Customer Groups, Product Categories, Units, Places …) are under Settings > Set up.
  - Step 5: **no Admin** on the bar: Users, Roles, Firms, Audit Logs and Backups are under **Settings > Platform**, for those who may open them.
- **Data:** none — the menu is built in the app from the permissions read at sign-in; opening it sends no request.
- **Leaves:** a firm admin user.

### TC-ME-013 — Settings > Set up: cards and a search across every section

- **Covers:** backlog 72 (Settings > Set up, 1.2.0)
- **Fixture:** `firm-admin`, then `two-firm-user`
- **Steps**
  1. Sign in as the fixture's **Firm admin**. Click the **gear**.
  2. Click **This PC and me**, then the **My Preferences** card.
  3. Close it; in the search box type `price`.
  4. Click **Price Lists**.
  5. Sign in as the **Two-firm user** and click the gear.
- **Expect**
  - Step 1: Settings opens as a tab: sections down the left — This PC and me, Firm, Selling, Buying, Stock, Tax, Business profile, then **SET UP** (Pricing, Territories & routes, Account structure, Party lists, Item lists, Locations) and, for a platform administrator only, **PLATFORM**; the chosen section's screens as cards.
  - Step 2: the My preferences dialog opens.
  - Step 3: matches from every section — Price Lists, Price Levels, Price Floor …
  - Step 4: Price Lists opens in its own tab.
  - Step 5: only the sections this user's roles reach; **This PC and me** is always there.
- **Data:** none — built from the permissions already held; no request until a screen opens.
- **Leaves:** unchanged.

### TC-ME-014 — The sign-in screen shows the agency, and the strengths cycle

- **Covers:** backlog 71 (agency branding, 1.3.0)
- **Fixture:** `ready-firm`
- **Steps**
  1. Open the app on a PC whose server has the agency's branding set (give it first under Settings > Platform > Agency > Branding if not). Do not touch the sign-in boxes for 20 seconds.
  2. Click the next and previous arrows and a dot on the left panel.
  3. Type one letter in the email box.
  4. Narrow the window below 900 px wide.
  5. Read the foot of the sign-in card, the window's title bar and the status line.
- **Expect**
  - Step 1: the agency's logo (or the initials of its name), name and tagline sit above the form; a night-blue panel on the left shows one strength with a title and a line, and changes to the next about every 8 seconds.
  - Step 2: the panel moves one strength at a time; the dot shows where you are.
  - Step 3: the panel stops cycling for good, even after the box is cleared, until the app is reopened.
  - Step 4: the left panel goes and the sign-in card stands alone, nothing cut off.
  - Step 5: the product mark (Agency Platform, "by" its company and tagline) is in the card's foot; the title bar reads **Agency Platform - Sign in**; the status line shows the server state, the version and *Powered by Agency Platform*.
- **Data:** `GET /api/v1/branding` once on opening; `GET /api/v1/branding/logo` only when the record has a logo and this PC's cached copy is of another version.
- **Leaves:** an agency with branding set.

### TC-ME-015 — Sign-in: More help, Copy details for support, and a server that does not answer

- **Covers:** backlog 71 (agency branding, 1.3.0)
- **Fixture:** `ready-firm`
- **Steps**
  1. On the sign-in screen open **More help**.
  2. Click **Copy details for support** and paste into Notepad.
  3. Stop the server (or open Application Settings and point the API URL at a port nothing listens on), then close and reopen the app.
  4. Start the server again, reopen the app.
- **Expect**
  - Step 1: support rows (phone, WhatsApp, hours, email, website) each appear only if filled -- they are blank in this release, so none shows; the line *Forgot your password? Your administrator resets it.* does.
  - Step 2: the button says it copied; the text names the product, its version, the server address and this computer's name. No password or token is in it.
  - Step 3: the sign-in screen still opens at once, showing the agency's name, tagline and logo from this PC's last answer (or Agency Platform's own name and logo if this PC never had one); no error box.
  - Step 4: the agency's current branding shows.
- **Data:** none while the server is down; one `GET /api/v1/branding` once it is up.
- **Leaves:** an agency with branding set, once seen by this PC.

### TC-ME-016 — First sign-in: Set up your agency, Skip for now, and the Home card

- **Covers:** backlog 71 (agency branding, 1.3.0)
- **Fixture:** `ready-firm`
- **Steps**
  1. On an installation whose branding has **not** been set (a fresh install with the Branding page left blank), sign in as the platform administrator.
  2. Press **Skip for now**.
  3. Look at Home, then click **Set up your agency** on the card.
  4. Leave the name blank and press **Save**; then type `QA Book Traders Agency`, a tagline `Quality in bulk`, choose a PNG under 1 MB as the logo and press **Save**.
  5. Sign out and sign in again; look at the top of the window and Home.
  6. Sign in as the firm administrator instead.
- **Expect**
  - Step 1: a dialog **Set up your agency** opens over Home with Agency name, Tagline, Logo and a live preview.
  - Step 2: the dialog closes and nothing is saved.
  - Step 3: Home shows a **Finish setting up** card (*Give your agency's name and logo, so every PC shows them.*); the button opens the same form.
  - Step 4: a blank name is refused beside the box; the full save closes the form and the card disappears from Home.
  - Step 5: the dialog no longer opens; the agency's logo, name and tagline lead the menu strip; the window title reads the agency name.
  - Step 6: no dialog and no card appear for a person without platform settings rights.
- **Data:** no request until Save; Save is `PUT /api/v1/branding` and, with a logo, `PUT /api/v1/branding/logo`. The platform audit trail gains `agency_branding.created` and `agency_branding.logo_changed` (the logo's type and size, never the image).
- **Leaves:** a platform administrator on an installation with no branding set.

### TC-ME-017 — Settings > Platform > Agency > Branding: change, logo rules, two people at once

- **Covers:** backlog 71 (agency branding, 1.3.0)
- **Fixture:** `ready-firm`
- **Steps**
  1. Sign in as the platform administrator. Open **Settings > Platform > Agency > Branding**.
  2. Change the tagline and watch the preview; press **Save**.
  3. Press **Choose logo** (or **Change logo**) and pick a file named `fake.png` that is really a text file; then a PNG or JPG larger than 1 MB.
  4. Choose a valid square PNG; Save. Then press **Remove logo**; Save.
  5. On two PCs (or two windows) open the page; on the first change the tagline and Save; on the second change the name and Save.
  6. Sign in as the firm administrator and open Settings.
- **Expect**
  - Step 1: name, tagline, logo, a preview of the sign-in card and of the top of every screen, and our product and company read-only (*set by the installer; changed only by an update*). There is no colour box.
  - Step 2: the preview follows each keystroke; Save shows *Saved.*; the menu strip changes at once with no refresh.
  - Step 3: the text file is refused with *The logo must be a PNG or JPG image.* (the file's contents are judged, not its name); the large one with a message that it is N MB and the limit is 1 MB. The form keeps everything typed.
  - Step 4: the logo appears in the preview and the header; after Remove, the initials of the name show instead.
  - Step 5: the first save succeeds; the second is refused inside the form with the somebody-else-saved message and keeps what was typed.
  - Step 6: **Platform** and its Agency group are not offered.
- **Data:** the platform audit trail (Settings > Platform > System > Audit Logs, no firm) lists `agency_branding.updated` and `agency_branding.logo_changed` for the saves, each naming who. Sign-in on another PC shows the new logo, name and tagline at its next sign-in screen.
- **Leaves:** a platform administrator, and the firm administrator.

### TC-ME-018 — The header: agency and firm, narrow window, Home, status line

- **Covers:** backlog 71 (agency branding, 1.3.0)
- **Fixture:** `ready-firm`
- **Steps**
  1. Sign in as the firm administrator of a firm, with the agency's branding set. Look at the menu strip and the window's title bar.
  2. Switch firm with the firm switcher (if there are two); then sign in as the platform administrator, who has no firm chosen.
  3. Narrow the window to under 820 px, then widen it past 1280 px.
  4. Open Customers, then click the agency's logo or name at the left of the strip.
  5. Read the right end of the status line and point at it.
- **Expect**
  - Step 1: the logo, name and tagline lead the strip before Home, then the firm's name as plain text; the title bar reads **<agency> > <firm>**.
  - Step 2: the firm part of the title follows the switch; with no firm the title is the agency's name alone.
  - Step 3: below 820 px only the logo shows; the tagline appears from 1280 px.
  - Step 4: Home opens.
  - Step 5: the product's mark, *Agency Platform <version> by <company>*, and a tooltip with the same words. Clicking it does nothing (there is no About screen yet).
- **Data:** no request: the header reads the copy the sign-in screen kept.
- **Leaves:** a firm with a finished set-up.

---

## Firms — creating one and finishing it

A firm is created in one place and finished in several: storage, business
profile, books, tax, first branch and people are each a separate act.
Settings > Platform > Firms > **Firms** creates it, and **Set up** on that grid shows each
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

### TC-FIRM-001 — Firms is a Platform screen that needs no firm

- **Covers:** plan 27.1, 27.2
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. The header reads **Platform**.
  2. Open Settings > Platform > Firms > **Firms**.
  3. Select TEST01 and open it with **Open this firm**; look through the **Masters** menu.
- **Expect**
  - Step 2: the list of every firm. This is the one firm screen that works with no firm selected (the Platform part of Settings).
  - Step 3: **no Firms** under Masters. It moved to the platform screens on 2026-09-06 — as a Masters tab it needed a firm, so creating a firm was reachable only from inside another one.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.8 — reads only.
- **Leaves:** a platform administrator.

### TC-FIRM-002 — Creating a shared firm, and reaching it at once

- **Covers:** plan 27.3, 27.4, 27.8, 27.10, 27.15, 27.16
- **Fixture:** `platform-admin`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. Settings > Platform > Firms > **Firms** → **New**.
  2. Type only a name, e.g. `Created <suffix>`, and save.
  3. Fill the rest: code **`<suffix>-s` in lower case** (e.g. `t0916abcd-s`), country `IN`, currency `INR`, financial year start `2026-04-01`, deployment mode **SHARED**. Save.
  4. Select the new row.
  5. Press **Open this firm**, then open the firm switcher.
- **Expect**
  - Step 2: refused. The five required fields are `name`, `code`, `country` (2 letters), `currency_code` (3 letters) and `financial_year_start`; everything else is optional.
  - Step 3: saves. The code is stored **upper case** — `T0916ABCD-S` — as are country and currency. The follow-up message names the next step.
  - Step 4: **Open this firm** enabled — a shared firm is ready at once. **Provision storage** hidden; there is nothing to build.
  - Step 5: "Working in …" names the new firm, the header shows it, the menu bar grows. **The firm is in the switcher.** That is the half that was broken: the switcher was read once at sign-in, so a firm created minutes earlier was refused as "not assigned to this user".
- **Data**
  ```sql
  select code, deployment_mode, schema_name, provisioned_at, created_at
  from   platform.firms where code = '<SUFFIX>-S';
  ```
  `SHARED`, no schema of its own. Audit `firm.created` on the platform trail.
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.8 — `firm.created` carries the firm's own id.
- **Leaves:** a platform administrator, and a firm `<SUFFIX>-S` in the shared store with nothing in it. Delete it from the Firms grid if you like.

### TC-FIRM-003 — What firm creation refuses

- **Covers:** plan 27.5, 27.6, 27.7, 27.9
- **Fixture:** `platform-admin`
- **Steps (HTTP)** — sign in as the fixture's platform admin and send `POST /api/v1/firms`, each time with `name`, `country: "IN"`, `currency_code: "INR"`, `financial_year_start: "2026-04-01"` and `deployment_mode: "SHARED"`, varying one thing:
  1. `code: "TEST01"` (a firm that already exists — on an installed copy, use one of your own)
  2. `code: "BAD CODE"`
  3. `code: "<SUFFIX>-Z"`, `country: "IND"`
  4. `code: "<SUFFIX>-Y"`, `deployment_mode: "DATABASE"`, `database_name: "fx_nope"`, `connection_profile: "NOPE"`
- **Expect**
  1. **409**, "Firm code, GST number, or PAN number already exists." Unique among *live* firms only — a deleted firm releases its code.
  2. **422**, the code "should match pattern `^[A-Z0-9_-]+$`" — no spaces, no dots.
  3. **422**, country "should have at most 2 characters".
  4. **422**, "Connection profile 'NOPE' is not configured. Configured profiles: <this installation's own list, from `config/.env`>." Refused at creation, not at first use — otherwise the firm would provision nothing and fail far from the request that caused it. (This machine's own list is `REMOTE_A`; an installed copy sees whichever profiles its own `.env` names, which may be none.)
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.8 — every refusal writes nothing — but a SCHEMA firm naming `firm_shared` or `platform` is **not** refused (D-IDN-4).
- **Leaves:** nothing; every request was refused.

### TC-FIRM-004 — A dedicated firm cannot be opened until it is provisioned

- **Covers:** plan 27.11, 27.12, 27.13
- **Fixture:** `unprovisioned-firm`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. Settings > Platform > Firms > **Firms**; select the fixture's **New firm**.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §15.9.
- **Leaves:** the firm, now provisioned.

### TC-FIRM-005 — A firm's storage routing is fixed at creation

- **Covers:** plan 27.14
- **Fixture:** `unprovisioned-firm`
- **Steps (HTTP)** — as the fixture's platform admin, `GET /api/v1/firms/{id}` for the fixture's firm, then `PUT` it back with `name`, `code`, `country`, `currency_code`, `financial_year_start` as read and `deployment_mode: "SHARED"`.
- **Expect:** **422**, "Firm storage routing cannot be changed after creation (currently SCHEMA/<the schema the server chose for this firm>). Migrate the firm's data first." — the schema name in the message is whatever the server picked at creation, not a fixed string. Nothing moves a firm's rows between stores.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.8 — the refusal writes nothing; an edit that keeps the routing is a full replacement — an omitted `is_active` is true, omitted GST and PAN are cleared (D-IDN-10).
- **Leaves:** the firm, unchanged.

### TC-FIRM-006 — The setup panel on a firm whose storage is not built

- **Covers:** plan 27.23e
- **Fixture:** `unprovisioned-firm`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. Settings > Platform > Firms > Firms → select the fixture's firm → **Set up**.
  2. **(HTTP)** Before pressing anything, `POST /api/v1/firms/{id}/open-books`, `.../apply-tax-template` and `.../create-default-branch`.
  3. On the panel, press **Provision storage**.
- **Expect**
  - Step 1: **Cannot post documents yet.** Storage is **missing** with a **Provision storage** button. Business profile, Books, Tax, Geography and Branches read "Cannot be checked until the firm's storage is provisioned." with no button and no hint. People reads "Nobody belongs to this firm yet. Only a platform administrator can open it."
  - Step 2: three **422**s — "Provision the firm's storage before opening its books.", "… before applying a tax template.", "… before creating its first branch."
  - Step 3: the list re-reads; Storage is done and Books now offers **Open the books**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.9 — reads only.
- **Leaves:** the firm, provisioned.

### TC-FIRM-007 — The setup panel says what an unfinished firm still needs

- **Covers:** plan 27.23, 27.23a, 27.23b
- **Fixture:** `unfinished-firm`
- **Steps**
  1. Sign in as the fixture's **Platform admin**. Settings > Platform > Firms > Firms → select the fixture's firm → **Set up**.
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
    | Geography | No country in the store. … | a hint: Settings > Set up > Locations > Places; the GST template adds the country |
    | Branches and warehouses | … 0 branches, 0 warehouses so far. | **Create head office and main warehouse** |
    | People | Nobody belongs to this firm yet. … | a hint: Settings > Platform > People > Users → Add existing user, or Settings > Platform > People > User-Firm Assignments |
  - Step 2: **200**, `can_post: false`, `ready: false`, the same seven `steps` with `status` DONE / MISSING and `required`.
  - Step 3: the same seven rows from the same implementation, and that it **cannot post** because the books are not open.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.9 — reads only.
- **Leaves:** the firm, unchanged.

### TC-FIRM-008 — Opening the books, once

- **Covers:** plan 27.23c, 27.23d
- **Fixture:** `unfinished-firm`
- **Steps**
  1. Sign in as the fixture's **Platform admin** → Firms → the fixture's firm → **Set up** → **Open the books**.
  2. Press **Refresh**. Then **(HTTP)** `POST /api/v1/firms/{id}/open-books` again.
  3. Settings > Platform > System > **Audit Logs**, on Platform.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §12.1 — audit `firm.books_opened` on the platform with the firm (§15.10).
- **Leaves:** the firm with its books open.

### TC-FIRM-009 — The GST template, once

- **Covers:** plan 27.23f, 27.23h
- **Fixture:** `unfinished-firm`
- **Steps**
  1. As the fixture's **Platform admin**, open **Set up** on the fixture's firm → Tax row → **Apply GST template**.
  2. **(HTTP)** `POST /api/v1/firms/{id}/apply-tax-template` again; then once more with `{"template": "US"}`.
  3. Open this firm → Settings > Tax > **Tax Configuration**.
- **Expect**
  - Step 1: "GST set up: 10 tax profiles and 13 rules." Tax re-reads as "1 tax system, 10 profiles, 13 rules", and **Geography flips to done** ("1 country in the store") — the template adds India to a store that has no country.
  - Step 2: "The firm already has a tax system; nothing was created.", `already_configured: true`. With `US`: **422**, only `IN_GST` exists. One `firm.tax_template_applied` audit row, not two.
  - Step 3: the system, four components and eight profiles, editable.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §13.2 — audit `firm.tax_template_applied` on the platform with the firm (§15.10); a second press writes nothing.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.2 in `fx_<suffix>_f` — one `firm_business_profiles` row (WHOLESALE, `is_active` true, `effective_from` now) and `firm_business_profile.created` in the **firm's** trail, `after_data` the profile id only; nothing on the platform trail.
- **Leaves:** the firm on the Wholesale profile.

### TC-FIRM-011 — Head office and main warehouse, once

- **Covers:** plan 27.23i
- **Fixture:** `unfinished-firm`
- **Steps**
  1. As the fixture's **Platform admin**, **Set up** on the fixture's firm → Branches and warehouses → **Create head office and main warehouse**.
  2. **(HTTP)** `POST /api/v1/firms/{id}/create-default-branch` again.
  3. Open this firm → Masters > **Branches**, then **Warehouses**.
- **Expect**
  - Step 1: "Created branch HO and warehouse MAIN. Rename them on their own screens." The row reads "1 branch, 1 warehouse". The verdict stays **Cannot post documents yet.** — the books are still shut in this run; that is TC-FIRM-008's step, not this one's.
  - Step 2: "The firm already has a branch and a warehouse; nothing was created.", `already_present: true`.
  - Step 3: `HO` Head Office, default; `MAIN` under it.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.16 — `branches` HO and `warehouses` MAIN in the firm's store with `branch.created` / `warehouse.created` there, and `firm.default_branch_created` on the platform with the firm (§15.10).
- **Leaves:** the firm with a branch and a warehouse.

### TC-FIRM-012 — Profile Assignment, the other way to set a profile

- **Covers:** plan 27.18, 27.19, 27.20
- **Fixture:** `unfinished-firm`
- **Steps**
  1. As the fixture's **Platform admin**, switch into **TEST01** (the screen needs *some* firm open).
  2. Settings > Business profile > **Profile Assignment**.
  3. Select the fixture's firm, open it, choose **Retail**, save. Re-open the row.
- **Expect**
  - Step 2: a grid of **every** firm, not only TEST01 — the screen names the firm in the URL rather than reading `X-Firm-ID`.
  - Step 3: saved against the fixture's firm, not TEST01; re-opening shows Retail. The **Business profile** dropdown is populated — empty, or "The database is temporarily unavailable", means no firm is open.
- **Data** — `docs/DATA_TRAIL_BY_OPERATION.md` §14.2: the row is updated in place (`effective_from` unchanged, `notes` cleared unless sent) and `firm_business_profile.updated` has no before side, so the trail cannot say the firm was WHOLESALE (D-CFG-13).
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
  1. As the fixture's **Platform admin**, open the fixture's firm. Masters > **Customers** → New: code `C1`, name `Before books`, type Business, currency INR. Save.
  2. **(HTTP)** `POST /api/v1/receipts` with `X-Firm-ID` of the fixture's firm: `{"party_id": "<C1's id>", "settlement_date": "<today>", "amount": "100.00", "method": "CASH"}`.
- **Expect**
  - Step 1: saves. Masters do not need the books.
  - Step 2: **422**, "No ledger account is configured for CASH. Set the firm's control accounts before posting this document." The posting service refuses rather than guesses — the design working, not a broken firm.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.16 and §12.1 — the masters write the firm's store with no journal; the refused posting writes nothing.
- **Leaves:** a customer `C1` in the fixture's firm; no receipt.

### TC-FIRM-014 — What "finished" looks like

- **Covers:** plan 27.26
- **Fixture:** `ready-firm`
- **Steps:** sign in as the fixture's **Platform admin** → Settings > Platform > Firms > Firms → the fixture's firm → **Set up**.
- **Expect:** **Finished. Every step is done.** — "24 accounts, 1 financial year, 12 periods, all 24 control accounts mapped, and a period open today"; Assigned: WHOLESALE; 1 tax system, 8 profiles, 9 rules; 1 country; 1 branch, 1 warehouse; **2 members**. No buttons. The contrast with TC-FIRM-007 is the point.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.9 — reads only.
- **Leaves:** the firm, unchanged.

### TC-FIRM-015 — Control accounts: held once something has posted

- **Covers:** plan 27.23j
- **Fixture:** `ready-firm`
- **Steps**
  1. Sign in as the fixture's **Firm admin** → Settings > Set up > Account structure > **Control Accounts**.
  2. Hover the lock on **Accounts receivable**.
  3. On **Rounding**, press **Change**. Open the account picker; look at **Save** before choosing. Choose `4000 Sales`, Save. Then change it back to `4900 Rounding`.
  4. **(HTTP)** `PUT /api/v1/finance/control-accounts/ACCOUNTS_RECEIVABLE` with `{"ledger_account_id": "<any other ASSET account>"}`.
  5. Sign in as the fixture's **Viewer** → Settings > Set up > Account structure > Control Accounts.
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
  Tables: `docs/DATA_TRAIL_BY_OPERATION.md` §12.7.
- **Leaves:** the firm, with Rounding back where it was.

### TC-FIRM-016 — A firm administrator cannot reach firms at all

- **Covers:** plan 27.21, 27.22, 27.23a (the 403 half), 27.26a
- **Fixture:** `firm-admin`
- **Steps**
  1. Sign in as the fixture's **Firm admin** → the gear → look under **Platform**.
  2. **(HTTP)** As that user: `GET /api/v1/firms`, `POST /api/v1/firms` (any body), `GET /api/v1/firms/{TEST01's id}/readiness`, `POST /api/v1/firms/{TEST01's id}/open-books`.
- **Expect**
  - Step 1: **no Firms** and **no Business Profiles** card under Platform, so no setup panel. `FIRM_VIEW` and `PLATFORM_VIEW` are platform codes no firm role can hold.
  - Step 2: **403** for all four. No permission code can grant them. What they would show, a firm administrator reads as their own Accounts > All Accounts screens > Books > Chart of Accounts and Financial Years.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.8 — every refusal writes nothing.
- **Leaves:** a firm admin user.

### TC-FIRM-017 — A firm whose people have been deleted cannot be deleted either

- **Covers:** nothing in the plan — found on 2026-09-16 clearing the per-run fixture firms
- **Fixture:** `ready-firm`
- **Steps (HTTP)** — as the fixture's **Platform admin**
  1. `DELETE /api/v1/users/{the firm admin's id}`, and the same for the `VIEWER`. They are the firm's only two people.
  2. `GET /api/v1/firm-members` and `GET /api/v1/users?page=1&page_size=25`, both with `X-Firm-ID: <the fixture firm's id>`.
  3. `DELETE /api/v1/firms/{the fixture firm's id}`.
  4. Take a second `ready-firm` fixture and, without deleting anybody, `DELETE` that firm.
- **Expect**
  - Step 1: **204** each.
  - Step 2: **nobody**. The firm's own directory is empty and its Users grid has no rows, so every screen agrees the firm has no people.
  - Step 3: **204** — the firm deletes. Until 2026-09-16 this answered **422**, "Assigned firms cannot be deleted.", naming a condition no screen could show; see defect **D-27-5**. The memberships themselves are untouched, because they are what a restore reads to put those people back.
  - Step 4: **422**, "Assigned firms cannot be deleted." A firm with people who still exist is still refused — that half of the guard is the point of it.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §15.8 — the delete writes `firm.deleted` with the firm and leaves the mapping; the guard counts memberships of live users only.
- **Leaves:** nothing live — the first firm is deleted, the second is not. A deleted firm's schema stays behind, because storage routing is never reused, soft-deleted firms included.

### Known defects found while writing these cases

- **D-27-5 — A firm whose people had been deleted could never be deleted. Fixed 2026-09-16.** `FirmService.delete` refused while any `user_firms` row for the firm was live, and `IdentityService.delete_user` leaves those rows alone — so deleting a firm's last person made the firm undeletable for ever. Both halves are defensible on their own: a deleted membership would have to be rebuilt on restore, and the identity router says as much ("a deleted person's memberships still place them in the firm"). Together they refused an action and named a reason nothing could show — `GET /api/v1/firm-members` returned nobody, the Users grid returned nobody, and the refusal still said "Assigned". Met on 2026-09-16 clearing 14 per-run firms: 22 live memberships, **every one of them held by a deleted user**; getting through meant restoring each person, emptying their membership list and deleting them again, which nobody would derive from the message. The guard now joins `users` and ignores a membership whose user is deleted — such a row places nobody in the firm today, it is a note about who to put back, and the rows are left untouched so a restore still reads them. A firm with people who still exist is refused exactly as before. `test_a_firm_whose_people_were_deleted_can_still_be_deleted` in `tests/unit/test_firms_module.py`.

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
  1. Sign in as the fixture's **Platform admin**; switch into the fixture's firm. Settings > Business profile > **Attribute Definitions**.
  2. **New**: code `SHELF_NOTE`, name `Shelf note`, TEXT, entity type `PRODUCT`, business profile **blank**. Save.
  3. **New**: code `PHARMA_NOTE`, name `Pharma note`, TEXT, entity type `PRODUCT`, business profile **Pharmacy**. Save.
  4. **(HTTP)** `GET /api/v1/business-framework/attribute-definitions/applicable?entity_type=PRODUCT` with the fixture firm's `X-Firm-ID`.
  5. Mandatory Attributes → **New**: category `FXAMB`, attribute `Shelf note`, mandatory **off**, profile blank. Save. Then Masters > **Products** → New → category **Fixture Ambient** → **Attributes** tab.
- **Expect**
  - Step 1: the definitions in *this firm's* store — the seeded ones (Batch Number, Expiry Date, IMEI …) — each showing its entity type and the profile it is narrowed to.
  - Steps 2–3: both save.
  - Step 4: `definitions` includes **SHELF_NOTE** and **not** PHARMA_NOTE. Scoping is what stops one industry's field appearing everywhere.
  - Step 5: an **Attributes** tab with a **Shelf note** box. Since 2026-09-16 the rule is not what puts it there — a definition that simply applies is offered on the product form as it is on every other master (D-27-1); the rule decides whether the box is *required*.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.4 in `fx_<suffix>_r` — two `attribute_definitions` rows (`applicable_business_profile_id` null, then PHARMACY's id) and one `category_attribute_rules` row. Their audit rows (`attribute_definition.created` ×2, `category_attribute_rule.created`) carry `firm_id` null and no data, so Settings > Platform > System > Audit Logs does not show them — query by action (D-CFG-13). Step 4 writes nothing.
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
  - On the desktop the form now offers a **Bin code** box, required, so step 3's product can be typed rather than posted: fixed 2026-09-16, see defect **D-27-2**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.4 and §14.5 — the definition carries `mandatory` true; step 2 writes nothing; step 3 writes one `products` row and one `product_attribute_values` row, `value_text` `A-1`. A definition that is itself mandatory also refuses a blank value.
- **Leaves:** a mandatory definition and one product in the fixture firm. Any later product in this firm needs a bin code.

### TC-FIELD-003 — A rule makes a field mandatory for one category only

- **Covers:** plan 27.32
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: `COLD_CHAIN_ID`, `Cold chain id`, TEXT, `PRODUCT`, profile blank, mandatory **off**.
  2. Mandatory Attributes → **New**: profile **Wholesale**, category `FXCHL`, attribute `Cold chain id`, **mandatory on**.
  3. Masters > Products → New, category **Fixture Chilled**, code `CH1`, leave Cold chain id empty, Save. Fill it, Save.
  4. Masters > Products → New, category **Fixture Ambient**, code `AM1`, Save.
- **Expect**
  - Step 3: the Attributes tab shows **Cold chain id** as required; empty is refused on the form ("Required business attributes are missing."); filled, it saves.
  - Step 4: saves — no Attributes tab, nothing asked. Other categories are untouched.
- **Data** — `docs/DATA_TRAIL_BY_OPERATION.md` §14.4: a field a rule makes mandatory is refused when missing but **accepted when sent blank** through the API, stored with every value column null (D-CFG-5).
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
  - Step 4: `required_attribute_definition_ids` does **not** list RX_CLASS, and neither does the optional list — the metadata and the save now answer the same question. Fixed 2026-09-16; see defect **D-27-3**.
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.4 — the rule row is written although it can never apply here; `RX0` saves with no `product_attribute_values` row.
- **Leaves:** a definition, a rule and one product in the fixture firm. Retire the rule to make FXAMB usable on the desktop again.

### TC-FIELD-005 — Changing the firm's profile hides a field and keeps its value

- **Covers:** plan 27.34, 27.35
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm: Dynamic Attributes → New `WS_GRADE`, `Wholesale grade`, TEXT, `PRODUCT`, profile **Wholesale**. Mandatory Attributes → New: profile **Wholesale**, category `FXAMB`, `Wholesale grade`, mandatory **off**.
  2. Masters > Products → New, category Fixture Ambient, code `GR1`, Wholesale grade `A`. Save.
  3. Set Up on the firm (from Platform) or Profile Assignment: change the firm to **Retail**. Open `GR1` again.
  4. Change the firm back to **Wholesale**. Open `GR1` again.
- **Expect**
  - Step 3: the **Attributes tab is gone** and nothing warned you. The value is still stored (below). This is `docs/BACKLOG.md` §16.
  - Step 4: the field and its value `A` are back. Nothing was lost; it stopped being *read*.
- **Data** — `docs/DATA_TRAIL_BY_OPERATION.md` §14.2 and §14.5: each profile change updates the one `firm_business_profiles` row in place and touches no value row.
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
- **Data:** the query from TC-FIELD-005 with `p.code = 'LN1'`, plus `value_number`. `docs/DATA_TRAIL_BY_OPERATION.md` §14.4 — the edit writes `attribute_definition.updated` with `firm_id` null and no data, so nothing records that the type changed.
- **Leaves:** a definition now NUMBER, with a text value stranded.

### TC-FIELD-007 — A customer carries a custom field, and an edit leaves it alone

- **Covers:** plan 27.36a, 27.36b
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: entity type `CUSTOMER`, code `DRUG_LICENCE_NO`, name `Drug licence no`, TEXT, mandatory **off**.
  2. Sign in as the fixture's **Firm admin** → Masters > Customers → New.
  3. Fill the General tab (code `DLC`, name `Licence Holder`), then **Custom fields**: `DL-4471`. Save. Reopen.
  4. Edit the phone on the General tab (`+919800000001`), Save, reopen Custom fields.
- **Expect**
  - Step 2: a **Custom fields** tab with one box, **Drug licence no**.
  - Step 3: the value is there. **(HTTP)** `GET /api/v1/customers/{id}`: `attributes` carries one row with `value_text: "DL-4471"`.
  - Step 4: the licence is still there. A form sends `attributes` only once it has read the definitions, and an update that omits them leaves them alone.
- **Data** — `docs/DATA_TRAIL_BY_OPERATION.md` §14.5: one `customer_attribute_values` row; step 4's save carries no `attributes` and leaves the row's `version` and `updated_at` as they were. Neither save's `customer.*` audit row mentions the licence (D-CFG-13).
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
  2. As the fixture's **Firm admin**: Masters > Customers → New, fill General, leave the licence empty, Save.
  3. **(HTTP)** `POST /api/v1/customers` with `code`, `name`, `customer_type: "BUSINESS"`, `currency_code: "INR"` and no attributes.
- **Expect**
  - Step 2: refused on the form, **"Drug licence no is required."** Nothing sent.
  - Step 3: **422**, "Required attributes are missing."
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.5 — both refusals write nothing, not even an audit row.
- **Leaves:** a mandatory customer definition in the fixture firm. Every later customer there needs a licence.

### TC-FIELD-009 — A vendor field belongs to vendors only

- **Covers:** plan 27.36d
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: entity type `VENDOR`, `SUPPLIER_TIER`, `Supplier tier`, NUMBER.
  2. As the fixture's **Firm admin**: Masters > Vendors → New (or Edit one) → **Custom fields**: `2`. Save, reopen.
  3. Masters > Customers → New: look at Custom fields.
  4. **(HTTP)** `POST /api/v1/customers` carrying `"attributes": [{"attribute_definition_id": "<SUPPLIER_TIER's id>", "value": "2"}]`.
- **Expect**
  - Step 2: one numeric box, Supplier tier; `2` after reopening.
  - Step 3: not offered.
  - Step 4: **422**, "One or more attributes do not apply to this record."
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.5 — one `vendor_attribute_values` row with `value_number` 2; step 4 writes nothing.
- **Leaves:** a vendor definition and a vendor in the fixture firm.

### TC-FIELD-010 — Branches and warehouses carry their own fields

- **Covers:** plan 27.36d2
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: entity type `BRANCH`, `FSSAI_LICENCE`, TEXT. And another: entity type `WAREHOUSE`, `DOCK_COUNT`, NUMBER.
  2. As the fixture's **Firm admin**: Masters > Branches → Edit `HO`; Masters > Warehouses → Edit `MAIN`.
- **Expect:** a **Custom fields** heading at the foot of each dialog with **its own** box only — FSSAI licence on the branch, Dock count on the warehouse. Type a value, Save, reopen: it is there. The branch is **still the default** — saving the dialog does not clear what it does not show.
- **Data:** `fx_<suffix>_r.branch_attribute_values`, `fx_<suffix>_r.warehouse_attribute_values`. `docs/DATA_TRAIL_BY_OPERATION.md` §14.5 — one row each, the value in `value_text` and `value_number`; the owner's `branch.updated` / `warehouse.updated` does not carry it.
- **Leaves:** two definitions and two values in the fixture firm.

### TC-FIELD-011 — A field with fixed choices

- **Covers:** plan 27.36d3
- **Fixture:** `ready-firm`
- **Steps**
  1. As the fixture's **Platform admin** in the fixture's firm, Dynamic Attributes → New: `PRODUCT`, `STORAGE_TEMPERATURE`, `Storage temperature`, TEXT, **Allowed values** `Ambient, Chilled, Frozen`. Then Mandatory Attributes → New: category `FXAMB`, Storage temperature, mandatory **off**.
  2. Masters > Products → New, category Fixture Ambient, code `PEAS`, Attributes → Storage temperature.
  3. Choose **Frozen**, Save, reopen.
  4. **(HTTP)** `PUT /api/v1/products/{PEAS id}` with `code`, `name`, `product_type`, `category_id` and `"attributes": [{"attribute_definition_id": "<id>", "value": "Cold"}]`.
  5. Edit the definition: remove `Frozen`. Reopen `PEAS`; then change its name and Save.
  6. Edit the definition: set the data type to NUMBER with the values still filled. Save.
- **Expect**
  - Step 2: a **dropdown** of the three, not a text box.
  - Step 3: Frozen is selected.
  - Step 4: **422**, "Attribute STORAGE_TEMPERATURE must be one of: Ambient, Chilled, Frozen."
  - Step 5: Frozen still shows, selectable, and **the save goes through with it unchanged**. Choosing something else off the list is still refused with "must be one of: Ambient, Chilled". Fixed 2026-09-16; see defect **D-27-4**.
  - Step 6: **422**, "Only a TEXT attribute can carry allowed values."
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.4 and §14.5 — the list is `attribute_definitions.validation_rule` → `allowed_values`; the product's value is `value_text` `Frozen`; steps 4 and 6 write nothing; step 5's saves leave the value row as it was.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.5 — reads only; the refused POST writes nothing.
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
- **Data** — `docs/DATA_TRAIL_BY_OPERATION.md` §14.5 and §14.10: the `uoms` row is shared and untouched; the value row is TESTSH1's own.
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
- **Data:** `docs/DATA_TRAIL_BY_OPERATION.md` §14.0 and §14.4 — one `firm_shared.attribute_definitions` row with no `firm_id`; its create and delete audit rows carry `firm_id` null, so neither firm's Audit Logs shows them.
- **Leaves:** nothing, once deleted.

### Known defects found while writing these cases

Recorded for the owner, **not fixed** — this pass changes documents only.

- **D-27-1 — The product form never offered a field that merely applies. Fixed 2026-09-16.** `ProductService._category_attribute_ids` built the form's field list from `category_attribute_rules` alone; customers, vendors, branches and warehouses use `/attribute-definitions/applicable`, so an unscoped PRODUCT definition with no rule — the ordinary case, and the one `docs/CUSTOM_FIELDS_FRAMEWORK.md` describes — was offered on no product at all. The product now asks the same question the other four masters ask: `AttributeService.definitions_for` for what applies, `mandatory_ids` for which of those are required, and the rest offered as optional. Rules are still read by the category's name as well as its code. Plan 27.30 expected it to appear. Three tests in `tests/unit/test_product_master.py` cover this and the two below.
- **D-27-2 — A mandatory PRODUCT definition blocked every product on the desktop. Fixed 2026-09-16.** The server refused a product without it ("Required attributes are missing.") while the form, per D-27-1, had no box to fill — so once a firm marked one definition mandatory, no product could be created from the desktop at all. The metadata now offers what the save demands, before a category is chosen as well as after, because the server demands it either way. Plan 27.31.
- **D-27-3 — An "inert" rule was not inert on the desktop. Fixed 2026-09-16.** `mandatory_ids` in `AttributeService` intersects rules with what applies; `_category_attribute_ids` did not, so `/products/metadata` listed a rule naming another profile's field as *required*. The form then refused an empty box, and a filled one was refused by the server as "do not apply" — a category nobody could save. Two implementations of one question, now one: the metadata reads `mandatory_ids`. Plan 27.33 said the rule is not an error, and it is not.
- **D-27-4 — A value removed from a field's allowed list could not be saved back. Fixed 2026-09-16.** `_coerce` validated every value sent, changed or not, so editing anything else on a product still holding a retired choice was refused — and the form deliberately keeps a stored value selectable, so the screen showed it as valid while the save refused it. `replace_values` now passes the record's own stored text into `_coerce`, which accepts it unchanged; a different value off the list is still refused, and so is the retired one on a record that never held it. The same reasoning as the retained definitions. Plan 27.36d3 expected it to save unchanged. `test_a_choice_withdrawn_from_the_list_can_still_be_saved_back` in `tests/unit/test_entity_attributes.py`.

### TC-FIELD-015 — Extra fields on documents, carried down the chain and printed

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog MST-6, A132
- **Fixture:** `selling-firm`
- **Steps:** as the fixture's **Firm admin**: Settings > Firm > **Custom Fields** → New: name *PO reference*, type Text, entity type **Sales order** (also add one for **Quotation** with the same name), **Show on print** on. Sell > **Quotations** → New: fill *Additional details* → Save → convert to a sales order → open the order. Create a delivery note and a bill from it. Print the quotation, order and invoice. Edit the order saving without touching *Additional details*, then clear the field and save. Repeat for a purchase order → supplier bill.
- **Expect:** the six document editors — quotation, sales order, delivery note, sales invoice, purchase order, supplier bill — show *Additional details* from the firm's definitions. Values carry down the chain matched on the field's **name** (quotation → order at conversion, order → delivery note, notes/orders → sales invoice, purchase order → supplier bill) and are printed as references where *Show on print* is on. Saving without sending `attributes` leaves the values alone; sending an empty list clears them. Goods receipts, returns, notes, line-level fields and list filters on a document field are not covered yet.
- **Leaves:** a definition and documents carrying it.

### TC-FIELD-016 — A firm keeps its own custom fields, in the shared store too

*Added 2026-10-03 from the code and the build notes; **not yet driven through a fixture** -- drive it and correct the expectation before relying on it.*

- **Covers:** backlog MST-8, A120
- **Fixture:** `shared-pair`
- **Steps:** as the **Firm admin of TESTSH1**: Settings > Firm > **Custom Fields** → New *Dock number* on Customer; Settings > Firm > **Custom Field Rules** → make it mandatory for a category. Try a code that already exists in the shared catalogue. Edit and delete the field; try to delete it after a customer holds a value. As the **Firm admin of TESTSH2**: open Customer → New and the field list. As the platform administrator open Attribute Definitions.
- **Expect:** the field is **TESTSH1's own**: offered on its forms and on no other firm's. The shared catalogue rows (existing before this change) are listed read-only to the firms. A firm's code is unique among its own and the shared live rows. A held type cannot change and a held field cannot be deleted. The platform's Attribute Definitions list shows the shared rows only.
- **Leaves:** a firm-owned field.


---

## Adding a case

Every section is here now, so what follows is for a **new** case — a new
feature, or a defect worth guarding against by hand.


1. List what each row needs to exist before it starts — that is the fixture.
2. Add the fixture to `backend/scripts/test_fixture.py`, built from the API, composing the existing blocks where it can.
3. **Run the fixture and drive every expectation against the backend** before writing it down; take menu and screen lists from `ModuleVisibility` and `MenuLayout`, not from the permission table.
4. Give each case a stable `TC-AREA-NNN` id and the six parts above. IDs do not change when cases are added, which plan section numbers did.
5. Write it here, at the end of the section it belongs to. Do not add rows to `MANUAL_UI_TEST_PLAN.md` — that file is pointers now, so there is one version and not two.
6. Use `by_code` for a firm's HO and MAIN, never a list's first row, and set a product's fields at creation: a product `PUT` replaces every editable field.
