# Finance, reports, audit and diagnostics

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-09-25 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Finance, reports and the rest of the platform

Finance is a flat list of tabs; Reports has **Operational Reports** and
**Financial Reports**; accounting periods live under **Masters →
Configuration → Financial Years**. Trial Balance, Profit & Loss and Balance
Sheet each take an **Accounting period**: pick the same one on all three.

The cases that change a firm's books — a new account, a closed period, a cost
centre, an account that demands one — use `ready-firm`, a store of the run's
own with a fresh chart (1000 Cash, 5000 Purchases, and no 9999).

### TC-FIN-001 — A new ledger account, and what cannot change afterwards

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps:** as the prepared **Firm admin**, Finance → **Chart of Accounts** → **New**: group chip **REV** first, code `9999`, name `Manual test account`, type EXPENSE → Save. Then group **EXP · Direct Expenses** → Save. Select it → **Edit**.
- **Expect:** with REV: "A ledger account must share its group's account type." With EXP: the row appears (Code, Account, Type, Status). No Delete on the toolbar. On Edit, group, type and code are fixed; only Name, Description, the two "Requires a …" boxes and **Active** change.
### TC-FIN-002 — The three statements balance and agree

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Steps:** as the prepared **Firm admin**, Finance → **Trial Balance**, this month's period; then **Profit & Loss** and **Balance Sheet**, the same period.
- **Expect:** the trial balance has Code, Account, Type, Opening, Debit, Credit, Closing, a Total row and a **Balanced** chip — 1100 Trade Receivables among the rows. P&L: Income and Expenses with a Net profit or loss row (This period, Year to date). Balance Sheet: Assets, Liabilities, Equity with Retained earnings brought forward and Result for the year, chip **Balanced**. They agree: Total assets = Liabilities and equity; the sheet's Result for the year = the P&L's year-to-date net; total debit = total credit. *(The figures are this preparation's own; the relationships are the test.)*
### TC-FIN-003 — A closed period refuses a posting; its trail says who closed it

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. As the prepared **Firm admin**, Journal Entries → **New Entry**: period June 2026, any journal and voucher type, date 2026-06-15, reference `MT-CLOSE-1`, lines `5000 Purchases` Dr 100 and `1000 Cash` Cr 100 → **Save Draft**.
  2. Masters → Configuration → **Financial Years** → the year → **June 2026** → **Close**.
  3. Journal Entries → the draft → **Post**.
  4. Reopen June (**Open**) → Post again.
  5. Settings → Audit Logs → Action `finance.accounting_period.updated` (in full) → Search. Then sign in as the prepared **Platform admin**, stay on Platform, and run the same search.
- **Expect**
  - Step 2: "June 2026 is closed. Nothing further can be booked into it."
  - Step 3: refused: "Accounting period P03 is closed and cannot accept postings." (June is P03 in an April year.)
  - Step 4: "Journal entry MT-CLOSE-1 posted." The trial balance for a later month still reads **Balanced**.
  - Step 5: in the firm, the caption "The trail for Ready qa…" and **two** rows (closed, reopened); `finance` alone would find nothing (exact match). On Platform the same search finds **nothing** — finance events stay in the firm's trail.
### TC-FIN-004 — Journal entries say which module posted them

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Steps:** Finance → Journal Entries; search each: `SI-2026-2027-000001`, `DN-`, `RC-2026-2027-000001`, `TCS-RC-2026-2027-000001`; open each with **View**.
- **Expect:** each row's subtitle is the entry's description; the View dialog's first line reads "POSTED · posted by <module> · <description>" — sales_invoice, delivery_note, settlements, tcs. The search matches reference or description; there is no source-module filter (BACKLOG §31.15).
### TC-FIN-005 — Every report opens, and an empty one says so

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.
- **Steps:** Reports → **Operational Reports** and **Financial Reports**: open every entry.
- **Expect:** each renders with `N row(s)` in the header, or — when empty — "Nothing to report / This firm has nothing matching it yet." rather than a blank grid. The sales order register, delivery note register and invoice reports hold the prepared documents; the purchase reports are empty (this store bought nothing).
### TC-FIN-006 — Ctrl+K finds a product and lands on its screen

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Steps:** as the prepared **Firm admin**, type in any search box, move to another screen, press **Ctrl+K**, type `QA-PM` → Search; select the result → **Open Details**.
- **Expect:** the dialog opens wherever focus is; one result, **Slot Check qa** (a product), "1 result found."; Open Details closes the search and lands on **Masters → Products**. **(HTTP)** `GET /api/v1/search?query=QA-PM` → 200 (the parameter is `query`; `q` answers 422).
### TC-FIN-007 — Cost and profit centres, and an account that demands one

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Steps**
  1. Finance → **Cost Centres** → New `SALES`, `Sales` → Save; New `SALES` again. Finance → **Profit Centres** → New `NORTH`, `North` → Save.
  2. Chart of Accounts → Edit `5000 Purchases` → tick **Requires a cost centre** → Save. Journal Entries → New Entry → choose 5000 on a line.
  3. **(HTTP)** `POST /api/v1/finance/journal-entries` with a 5000 line and no `cost_center_id`.
  4. Untick the flag.
- **Expect**
  - Step 1: the rows appear; the second SALES: "A cost centre with this code already exists." No Delete on either grid — deactivate with Active.
  - Step 2: a **Cost centre \*** dropdown on that line and no other; with SALES chosen the entry saves.
  - Step 3: **422**, "Ledger account 5000 requires a cost centre."
### TC-FIN-008 — A blocking credit policy refuses the approval

- **Preconditions:** As *selling-firm*, plus a **blocking** credit policy and the delivery-note stage switched off in the sales workflow settings. (BLOCK at 100%; Anand's limit 1,000; a draft order for 20 detergent.)
- **Steps:** as the prepared **Firm admin**, Customers → toolbar **Settings**; Cancel. Sales Orders → the prepared draft → **Approve**.
- **Expect:** the policy reads **Warn, then block**, warn 80, block 100. Approve is refused: "Anand Agencies qa would be at 179.9% of a 1000.00 credit limit. Collect payment or raise the limit before continuing." The order stays DRAFT.
### TC-FIN-009 — A firm that does not type delivery notes

- **Preconditions:** As *selling-firm*, plus a **blocking** credit policy and the delivery-note stage switched off in the sales workflow settings. (delivery-note stage off; Vijaya's order for 4, approved.)
- **Steps:** as the prepared **Firm admin**, Sales Invoices → **Sales stages** icon. Look for Delivery Notes in the sidebar. Then Sales Invoices → New → bill the prepared **order** (4) → Create draft → Approve. Reports → Operational → **Delivery note register**.
- **Expect:** Sales stages shows **Delivery note** switched off, and **Delivery Notes is not in the sidebar** — a stage the firm does not type is hidden. The invoice approves straight off the order; the service raises and dispatches the note itself (the order reads **DELIVERED**), and the register lists that note. *(Whether a hidden screen should hide notes that exist is an open product question, not a defect.)*
### TC-FIN-010 — Roles and Permissions are one sidebar entry with two addresses

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, look at the Administration sidebar; open **Roles & Permissions**; switch the strip to Permissions. Ctrl+K a permission code (e.g. `CUSTOMER_VIEW`) → open it. Sign out and in.
- **Expect:** **one** entry, Roles & Permissions, with a Roles / Permissions strip; switching keeps the entry highlighted and the heading. Ctrl+K lands on **Permissions** directly; after signing in again the last screen restores to the same half. (Creating and editing roles is TC-ROLE-001 and TC-ROLE-002.)
### TC-FIN-011 — A crash report reaches Diagnostics

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps:** sign in on the desktop, end **agency_desktop** in Task Manager, start it again and sign in as the prepared **Platform admin** (the queued report is sent then). Settings → **Diagnostics** → Source **Desktop** → Search; open the **UnexpectedTermination** group's first occurrence. Then Source **Server**, any group's first occurrence.
- **Expect:** Desktop: the UnexpectedTermination count one higher than before; occurrences / first seen / last seen / versions chips; the newest occurrence shows Firm, User and "Leading up to it" breadcrumbs ("Previous session started at … ended without a clean exit…") — no Request and no stack trace. Server: **Request <request_id>** and the stack trace.
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

- **Preconditions:** A QA01 user holding the CASHIER role only, and a customer with an outstanding invoice. (`CASHIER` alone, no job template. That combination is the whole setup: the seeded Counter Sales template pairs CASHIER with BILLING_EXECUTIVE, which is what hid the bug.)
- **Steps:** sign in as the prepared **Cashier**; read the sidebar; open Finance.
- **Expect:** **Finance** is in the sidebar (before the fix the sidebar was empty), with exactly **Receipts** and **Payments**. **None** of Chart of Accounts, Control Accounts, Cost Centres, Profit Centres, Journal Entries, Ledgers, Trial Balance, Profit & Loss, Balance Sheet, Refunds. Widening the module without gating its tabs would have handed a cashier the ledger.
### TC-CASH-002 — Recording a receipt, with a searchable party picker

- **Preconditions:** A QA01 user holding the CASHIER role only, and a customer with an outstanding invoice.
- **Steps**
  1. As the prepared **Cashier**, Finance → Receipts → **Record Receipt**.
  2. In the party picker, type part of the prepared customer code (`QA-TI`); clear it; type part of its name (`Till Customer`); then type `zzzz-nobody`.
  3. Choose **QA-TILL**, amount `100`, method Cash → save.
- **Expect**
  - Step 1: the dialog opens with the picker filled. **This failed until 2026-09-15** with "You do not have permission to perform this action." — the picker read `GET /api/v1/customers`, which needs `CUSTOMER_VIEW`, so the role was blocked one step short of the only thing it exists to do. The money screens read `GET /api/v1/receipts/parties` now (#403).
  - Step 2: both narrow the list, each option reading `CODE  Name` on one line; a search matching nobody says so under the field rather than showing an empty sheet.
  - Step 3: the receipt is recorded and listed.
### TC-CASH-003 — An accountant keeps all twelve

- **Preconditions:** A QA01 user hired with the *Accounts* job template (role ACCOUNTANT only). (`ACCOUNTANT` alone. No accountant is seeded in any demo firm.)
- **Steps:** sign in as the prepared **Accountant** → Finance.
- **Expect:** **all twelve** tabs. `ACCOUNTANT` carries `ACCOUNT_VIEW`, `JOURNAL_VIEW`, `RECEIPT_VIEW`, `PAYMENT_VIEW`, `LEDGER_VIEW`, `TRIAL_BALANCE_VIEW`, `PROFIT_LOSS_VIEW` and `BALANCE_SHEET_VIEW`; every code now on a tab is one whoever held `ACCOUNT_VIEW` already had, so nobody lost one.
### TC-CASH-004 — A firm administrator keeps all twelve

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** sign in as the prepared **Firm admin** → Finance.
- **Expect:** all twelve tabs.
---

## The audit trail

Settings is offered on any of `SETTINGS_VIEW`, `AUDIT_LOG_VIEW`,
`DIAGNOSTICS_VIEW`; Audit Logs needs `AUDIT_LOG_VIEW` and no firm; Diagnostics
needs `DIAGNOSTICS_VIEW`, which `FIRM_ADMIN` does not hold.

### TC-AUDIT-001 — A platform administrator reads the platform trail

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps:** sign in as the prepared **Platform admin**, no firm selected → Settings → **Audit Logs**.
- **Expect:** the **platform** trail — user, role and firm administration: `identity.login`, `user.created`, `user.firm_roles_set` and the like, including the prepared own setup a moment ago. Each row names who did it. *(Answered 403 between 2026-09-05 and 09-06: the designation had moved claims and the check had not.)*
### TC-AUDIT-002 — Selecting a firm switches to that firm's trail

- **Preconditions:** The platform administrator (`platform-admin@agency.local`), who belongs to no firm.
- **Steps:** as the prepared **Platform admin**, switch into **QA01** (the header changes from Platform, the sidebar grows) → Settings → Audit Logs.
- **Expect:** **QA01's** trail — firm-owned work such as `customer.created`, `sales_invoice.created`, `settlement.receipt.recorded` from preparations that sold or took money in QA01 — with platform rows carrying QA01's id interleaved. Not the platform trail of TC-AUDIT-001: selecting a firm is what sets `X-Firm-ID`.
### TC-AUDIT-003 — A firm administrator reads their own firm's history, naming people

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** sign in as the prepared **Firm admin** → **Settings**; read Audit Logs; look for Diagnostics.
- **Expect**
  - Settings opens with **Audit Logs** in it. It used to open empty — offered on `SETTINGS_VIEW` with both tabs demanding codes the role lacked.
  - QA01's history and nothing else. **Every row names the person who did it** and, where the subject is a person, who it was done to (#407, #409).
  - **No Diagnostics.** Error reports are telemetry for whoever maintains the product, not something a firm owns.
### TC-AUDIT-004 — A promotion lands in the firm's trail, in time order, and a filter reaches both stores

- **Preconditions:** A firm administrator of QA01, and a QA01 user given two roles picked by hand.
- **Steps**
  1. As the prepared **Firm admin**: Masters → Customers → New `QA-A`, name `Audit Before qa` → Save.
  2. Administration → Users → **Manual Hire (qa)** → **Apply job template** → Counter Sales → Apply.
  3. Customers → New `QA-B`, name `Audit After qa` → Save.
  4. Settings → **Audit Logs**. Read the top rows.
  5. Filter by action `user_template.applied` — **typed in full**.
- **Expect**
  - Step 4: from the top, `customer.created` (Audit After), `user_template.applied` and `user.roles_set` (both naming Manual Hire), `customer.created` (Audit Before) — **strictly descending timestamps straight through**. The promotion is written to the *platform* store (user administration is a platform path) and the customers to QA01's; nothing marks which came from where. A block of user-administration rows at one end and customers in another means the stores were concatenated, not merged. The promotion names the template **and the role codes it granted** — `role_codes` beside `role_ids`, `template_code` beside `template_id`.
  - Step 5: the promotion is found. A filter that reached one store and not the other would answer a half-truth that reads as correct because something came back. *(Exact match: `user` finds nothing — BACKLOG 31.17.)*
### TC-AUDIT-005 — The platform trail needs platform authority

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps (HTTP):** `GET /api/v1/audit-logs` as the prepared firm admin with **no** `X-Firm-ID`.
- **Expect:** **403**.
### TC-AUDIT-006 — Somebody with none of the three codes has no Settings at all

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps:** sign in as the prepared **Seller**; read the sidebar.
- **Expect:** **no Settings** — the module absent, not an empty Settings. A module that opens and does nothing reads as broken rather than withheld.
---

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 12-S01 | **Finance → Chart of Accounts** | Offered to any role holding `ACCOUNT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S02 | **Finance → Control Accounts** | Offered to any role holding `ACCOUNT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S03 | **Finance → Cost Centres** | Offered to any role holding `ACCOUNT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S04 | **Finance → Profit Centres** | Offered to any role holding `ACCOUNT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S05 | **Finance → Journal Entries** | Offered to any role holding `JOURNAL_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S06 | **Finance → Receipts** | Offered to any role holding `RECEIPT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S07 | **Finance → Payments** | Offered to any role holding `PAYMENT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S08 | **Finance → Refunds** | Offered to any role holding `ACCOUNT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S09 | **Finance → Ledgers** | Offered to any role holding `LEDGER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S10 | **Finance → Trial Balance** | Offered to any role holding `TRIAL_BALANCE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S11 | **Finance → Profit & Loss** | Offered to any role holding `PROFIT_LOSS_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S12 | **Finance → Balance Sheet** | Offered to any role holding `BALANCE_SHEET_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S13 | **Reports → Operational Reports** | Offered to any role holding `REPORT_VIEW` or `SALES_VIEW` or `PURCHASE_VIEW` or `CREDIT_NOTE_VIEW` or `PROFORMA_VIEW` or `LOYALTY_VIEW` or `PROMOTION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S14 | **Reports → Financial Reports** | Offered to any role holding `REPORT_VIEW` or `SALES_VIEW` or `PURCHASE_VIEW` or `CREDIT_NOTE_VIEW` or `PROFORMA_VIEW` or `LOYALTY_VIEW` or `PROMOTION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S15 | **Settings → Audit Logs** | Offered to any role holding `AUDIT_LOG_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S16 | **Settings → Diagnostics** | Offered to any role holding `DIAGNOSTICS_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 12-S17 | **Dashboard** | Offered to the platform administrator only. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
