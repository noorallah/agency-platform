# Bulk approval, migration from other tools, and data over the years

Owner, 2026-09-27: three pieces of work to run in parallel -- **bulk
approvals**, **import and migration from other tools**, and **performance as
years of data build up** -- designed from how the established tools do it.

How this was compiled: the other tools' help pages and official sites, read
2026-09-27 (sources at the end), and a survey of this codebase the same day.
Where a claim about another tool could not be confirmed from its own
documentation it says so. Competitors change between releases; re-check
before quoting one to a customer.

---

## 1. How the market handles a financial year

### What each tool does

| Tool | Model | What the new year gets | Old year afterwards | A back-dated change in the old year |
| --- | --- | --- | --- | --- |
| **TallyPrime** | **Both.** *Change Current Period*: one continuous data file, the period just moves on -- Tally recommends this until the books are audited. *Split Company Data*: new company files from a split date, as a performance step | Masters; closing balances of balance-sheet ledgers as openings; **bill-wise outstanding**; unreconciled GST and bank items. **Not** pending sales or purchase orders, **not** cost-centre balances | Kept, still editable | Continuous: nothing to do. Split: re-export closing balances as openings by hand |
| **BUSY** | A company per year: back up, create the new year, restore into it | Masters and balances, carried automatically | Kept as its own data | No re-sync found in its documentation |
| **Marg ERP 9+** | A company per year, through *Carry Balances* (run with every other user out) | Ledger balances, outstanding, sales challans (once only); stock and pending orders when chosen | Kept | **Marg notices** an edit to the old year and offers *Carry Balances* again |
| **Vyapar** | *Close Books*: a backup, then *Carry forward* (parties, stock, open cheques as openings) or *Fresh start* | As chosen | Only in the backup file | -- |
| **Zoho Books** | **One continuous database**; the financial year is a setting | Nothing to carry: balances continue | Same database | Nothing to do |
| **Odoo** | One continuous database; year-end is a **lock date** | Nothing to carry | Same database, locked | Unlock, change, relock |
| **ERPNext** | One continuous database; year-end is a **Period Closing Voucher** moving profit and loss into retained earnings | Balance-sheet accounts continue | Same database | Post another closing voucher for the difference |

### Why the Indian desktop tools split years

It is a **file-format limit, not an accounting rule.** Tally, BUSY and Marg
keep a company's data in local files that the program loads to work with; as
the files grow, opening them slows down (Tally partners cite about 500 MB as
the point to split). Splitting by year shrinks what has to be loaded. Even
Tally tells users to stay continuous until the books are audited, and treats
splitting as an optimisation to delay.

Splitting has a real cost that every one of them works around: a change to
last year does not reach this year's opening balances until somebody re-runs
the carry-forward (Marg prompts for it; Tally and BUSY leave it to the user),
reports cannot span years without opening two companies, and pending orders
and post-dated cheques fall through the gap.

### What this product should do

**Stay one continuous database, as Zoho, Odoo and ERPNext do, and as Tally
itself recommends until audit.** The server is PostgreSQL, which reads by
index rather than loading a file, so the reason the desktop tools split does
not apply -- and none of the splitting costs are paid: a back-dated change is
simply correct everywhere, reports span years, open items never fall through.

Performance comes from four things instead of splitting (section 4), and
closing a year is a **lock plus a closing entry** (section 4.3).

---

## 2. Bulk approvals

### The market

| Tool | Approval | Bulk |
| --- | --- | --- |
| **Zoho Books** | Transaction approval on bills, vendor credits, purchase and sales orders, invoices, quotes, credit notes; single or multi-level | **Yes**: the pending list, tick rows, *More → Approve*; a *My approvals* filter for multi-level chains; the submitter is notified |
| **BUSY** (Enterprise) | Voucher and master approval per user, with **conditional rules** (approval needed only above, for example, a discount) | Not found: approve and reject one voucher at a time (F4), with remarks |
| **TallyPrime** | *Edit Log* is an audit trail, not an approval | Not found |
| **Marg** | Approval routing in the Control Room | Not found |
| **Vyapar** | None | Bulk print and reminders only |

Bulk approval is **fully done only by Zoho**; the desktop tools stopped at
approving one voucher at a time. Doing it well is a place to be ahead.

### Where this product stands

- Approval exists on every document that needs it, **one at a time**, each
  under its own `*_APPROVE` permission.
- Bulk endpoints exist only for masters (vendors, products, branches,
  warehouses, tax, territories: delete, restore, status).
- The grid already supports ticking rows and select-all
  (`workspace_components.dart`); the phase 2 selection bar is built around
  one record.

### The design

1. **Where:** every list whose documents are approved -- sales orders,
   purchase orders, sales invoices, purchase invoices, credit notes, sales and
   purchase returns, and journal entries (*post*). Filter to *Draft* (the
   counter already there), tick rows or select all.
2. **The bar for several rows:** *"12 selected · ₹4,82,300"* and the steps
   **every** ticked row can take: *Approve*, *Reject*, *Print*, *Export*. A
   step some rows cannot take shows how many it will skip.
3. **Reject needs a reason**, recorded on each document's timeline.
4. **Each row is approved on its own, through the same service as a single
   approval** -- the credit check, stock reservation, promotion claim and
   posting all run. Unlike an import, a bulk approval is **not
   all-or-nothing**: one order over its credit limit must not hold back
   eleven good ones. The result lists every row: approved, or refused and
   why, with *Retry the refused*.
5. **Server:** `POST /{documents}/bulk-approve` with `[{id, version}]`, up
   to 100 per request, same permission as a single approval; each row in its
   own transaction; each audited. The version guards against approving a
   document somebody changed after the list was read.
6. **Home:** the *To do* counts (orders to approve, and so on) open the list
   filtered to what is waiting.
7. **Later, from BUSY and Zoho:** approval only when a rule says so (above an
   amount, a discount, a credit limit), multi-level approval, and telling
   the submitter.

Size: the framework (bar, server pattern, result dialog) about a week, then
about a day per document type.

---

## 3. Import and migration from other tools

### The market

Every tool converges on **three tiers**, and on loading them **in order, in
batches**:

| Tier | What | Who offers it |
| --- | --- | --- |
| 1. Masters | Customers, vendors, products, ledgers | Everyone (Excel templates) |
| 2. **Opening position** | Ledger opening balances (trial balance), **bill-wise** customer and vendor outstanding, opening stock with batches | Everyone; this is what migration guides actually aim for |
| 3. Full history | Every past voucher | Zoho (module by module, small batches), BUSY (Tally add-on), Marg (Tally both ways) -- always optional |

Tally is the source to read: BUSY and Marg import Tally's XML exports
(masters and day book), and Zoho documents a Tally path through its own
templates. BUSY and Marg also sell migration as a service.

### Where this product stands

- 19 import routes (JSON; nine also CSV and Excel), all-or-nothing, but
  **no preview**, and a failure names neither the row nor the field. Only
  opening stock has a desktop wizard with checks; 11 routes have no screen.
- **Opening stock with batches:** yes (draft, then post).
- **Customer opening balance:** one figure per customer, dated today -- not
  bill by bill, so ageing and applying a receipt to an old bill cannot work.
- **Vendor opening balance:** none.
- **Opening trial balance:** no way to load one.
- The plans: §36 (onboarding from a previous tool) and §46 (import with
  templates) in `docs/BACKLOG.md`.

### The design

**Target tier 2 for go-live; tier 3 is not offered** -- the old tool is kept,
read-only, for history, as most migrations do in practice.

1. **One import framework** for every entity:
   - a **template** (Excel) generated from the create schema, with a notes
     sheet;
   - **dry run first**: the server checks every row and returns *row, column,
     problem* for all of them; nothing is saved;
   - **commit once**, all-or-nothing, only after a clean dry run;
   - references by **code** (customer code, product code, account code),
     never by internal id; an unknown code is a row error, never a guess;
   - the old tool's identifier kept on the record (`legacy_code`), so a
     re-import updates rather than duplicates;
   - one desktop wizard for all of it (upload → check → fix and re-upload →
     commit), grown from the opening-stock wizard.
2. **The missing opening pieces:**
   - **Opening bills**, customer and vendor: invoice number, date, due date,
     amount outstanding, per bill -- held as opening documents, so ageing is
     right from day one and a receipt or payment applies to them like any
     bill;
   - **Opening trial balance**: account code and debit or credit, as at the
     cut-over date, checked to balance, posted as one opening entry; the
     customer and vendor totals must agree with their opening bills;
   - **Opening stock** exists; it joins the same wizard.
3. **The cut-over**: the start of a financial year is best (nothing to
   split), a month start otherwise. Everything opening is dated the day
   before.
4. **The order**, as the masters runbook sets it: branches and warehouses →
   units → tax → products → customers → vendors → opening stock → opening
   bills → opening trial balance. The firm's **Set up** panel gains an
   *Opening balances* step that shows what is loaded and whether it
   reconciles.
5. **From Tally, after the Excel path works:** read Tally's XML exports
   (masters, trial balance, bill-wise outstanding, stock summary) straight
   into the same dry run -- the most common source by far.

Size: framework and wizard 1-2 weeks; opening bills and trial balance about
a week; each master's template a day or two; Tally XML reading 1-2 weeks.

---

## 4. Performance as the years build up

### How big the data gets

Business data is about **11 MB per firm per year**; about **85% of the disk
is logs** (`audit_logs`, `tax_rule_execution_logs`) (BACKLOG §37). Ten years
of a firm's trading is well within what PostgreSQL reads by index in
milliseconds -- **if the queries use indexes and read only what they show.**
The risks are in how some queries are written, not in the volume.

### 4.1 Fix what reads too much (do first)

Found in the survey, in order of harm:

1. **The Inventory list loads every product's whole movement history** on
   every page (`selectinload(InventoryRecord.transactions)`,
   `inventory_service.py:195`; `lazy="selectin"` on the model). It grows
   with every sale ever made. **The biggest one.**
2. **Stock reports sum all movements** (45 `func.sum` in
   `inventory_service.py`) where the quantity is already stored on the
   stock row.
3. **`journal_entries` has no `(firm_id, journal_date)` index**; every other
   document table has one.
4. **Unpaged reports load the whole window into memory** and cut it in
   Python (`core/pagination/reports.py`).
5. **A back-dated posting rewrites every later period's balance row**, one
   by one in Python (`journal_engine.py:886-900`) -- slower each year.
6. **Every list runs a `COUNT(*)`** over all history.

### 4.2 Read less by default

- **Lists open on the current financial year** (§37's year selector, with
  *All years*), through the date filters every list already has. **Open
  items are never cut by year**: last year's unpaid invoice is still in
  *Receivables*.
- The **Period** control on every list (built in phase 2) is the same
  mechanism, so this is a default, not a new screen.

### 4.3 Close a year without splitting it

**Year-end close** (Accounts, by the accountant, ERPNext's pattern):
1. Check: every period of the year is closed, nothing is left in draft.
2. Post a **closing entry**: income and expense accounts to *Retained
   earnings* (or the partners' capital accounts, by the firm's type).
3. **Lock the year**: nothing can be posted into it.
4. Balances **continue on their own** -- one database, nothing to carry --
   so bill-wise outstanding, stock with batches, pending orders and
   post-dated cheques are simply there in the new year: none of the gaps
   the splitting tools leave.
5. **Reopening** is a permission, recorded; closing again posts a second
   closing entry for the difference only.

Then reports read from the **closing balance of the last closed year**
instead of adding up from the first day, and the balance sheet no longer
has to derive retained earnings from all history on every read.

### 4.4 Keep the logs small

- **Turn retention on by default** in the installer (it exists, opt-in:
  `purge-retention`), so the logs that are 85% of the disk stop growing
  without limit.
- If a firm's audit trail still grows large, **partition `audit_logs` by
  year** -- the one table where that is worth it.

### 4.5 Archiving -- not now

Moving whole old years out of the working database (to an archive schema
or file) is what the splitting tools do by nature. It is not needed at this
volume; revisit only if a firm passes about ten years or a measured target
is missed.

### 4.6 Measure, don't guess

Build a **large test firm** with `backend/scripts/generate_transaction_history.py`
(five years, heavy volume), record the time of every list and report, fix,
and record again. Targets: **a list opens in under 1 second, a report in
under 3**, on the minimum hardware in `docs/HARDWARE_SIZING.md`.

---

## 5. Order of work, three streams in parallel

| Stream | First | Then | Later |
| --- | --- | --- | --- |
| **A. Bulk approval** | Framework: the bar for several rows, the server pattern, the result list; sales orders and purchase orders | Invoices, credit notes, returns, journal entries | Approval rules, multi-level, notify the submitter |
| **B. Import and migration** | Framework: templates, dry run, per-row errors, the wizard; products, customers, vendors (§46) | Opening bills (customer and vendor), opening trial balance, *Opening balances* on Set up | Reading Tally's XML exports |
| **C. Performance** | The large test firm and timings; fix 4.1 items 1-4 | Current-year default on lists; set-based balance update (item 5); retention on by default | Year-end close (4.3); partition `audit_logs` if needed |

Streams A and B share nothing and can run side by side; C's first step
(the test firm) also gives A and B realistic data to test against.

---

## Sources (read 2026-09-27)

- Tally: help.tallysolutions.com -- moving to the next financial year
  (change current period; split or create new company), split company data
  FAQ, Edit Log FAQ, tracking modifications; tallyplanet.com (slowness and
  splitting).
- BUSY: busy.in FAQs -- Tally to BUSY data conversion, master and voucher
  import, voucher approval, selective approval; busyaccountingsoftware.in
  change-financial-year FAQ; busywinsoftware.com data migration service.
- Marg: care.margcompusoft.com -- carry balances, financial year queries,
  export to and import from Tally.
- Vyapar: vyaparapp.in -- change or close the financial year; close books.
- Zoho Books: zoho.com -- organization profile and fiscal year; Tally to
  Zoho Books migration; approve multiple transactions; approval workflow;
  manage approvals.
- Odoo: odoo.com documentation, year-end closing.
- ERPNext: docs.frappe.io / docs.erpnext.com -- period closing voucher,
  fiscal year.
