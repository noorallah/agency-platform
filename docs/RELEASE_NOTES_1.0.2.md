# Agency Platform 1.0.2: release notes and QA hand-over

Release 1.0.2 is the first installer that carries the **version 2 screens**:
the top menu bar, lists with everything on one line, and documents entered on
one screen. It upgrades an existing 1.0.0 or 1.0.1 installation in place, and
backs up the database before it changes anything.

Built 2026-09-27 from `main` at #813.

## What to send the QA person, and in what order

| # | Document | What it is for | When |
| --- | --- | --- | --- |
| 1 | **Release notes 1.0.2** (this document) | What changed and what to look at first | Read first |
| 2 | **Installation guide** | Installing, upgrading, the nightly backup and how to restore it | Beside `Setup.exe`; read before installing |
| 3 | **Installer QA checklist** | Install and upgrade on a real laptop, sections A to E. Section **E** is the upgrade to 1.0.2 and the backup | First, on the laptop |
| 4 | **QA functional walkthrough** (version 2) | One firm end to end: set up, buy, stock, sell, collect, return, GST. Section 11 covers the version 2 screens; section 15 covers what is new in 1.0.2 | After sections A and B of the checklist, before section D |
| 5 | **Profit and loss guide** | How rent, fuel and salaries reach the P&L, and the new Indirect Expenses accounts | When testing section 8 of the walkthrough |
| 6 | **QA test suite** (`QA test suite` folder, 00 to 14) | Detailed cases by module, for a deeper second round | Optional, after the walkthrough |

Plus the installer itself: `AgencyPlatform-1.0.2-Setup.exe`.

**On every failure**, the QA person captures a screenshot, the newest file in
`C:\ProgramData\Agency Platform\logs\server` (or `logs\install` for an install
problem), and the version on the sign-in screen.

## What is new in 1.0.2

### The version 2 screens

- **A top menu bar** replaces the left-hand menu: Home, Sell, Buy, Stock,
  Accounts, Masters, Reports, Admin, and the gear for Settings. **Ctrl+K**
  finds any screen or record.
- **Every screen and record opens as a tab** under the menu bar.
- **Documents are one full screen** -- header, lines, totals, a side panel for
  the line you are on -- and most are priced by the server as you type.

### Lists: one line, and a bar for the picked row

- **Nothing above the grid but one line**: the title, counters that filter
  when clicked, "+ filter", the search, the **Period** (named periods, the
  Indian financial year, a custom range, ◀ ▶ to step), **Columns**, Refresh,
  and **+ New** last. A screen's explanation is behind the **(i)** beside the
  title.
- **Picking a row shows a bar above the grid** that names it -- number,
  customer or supplier, status, total -- with only the steps that can run now
  at the right (Open, Edit, Approve, Post, Cancel, Print ...). Nothing is
  picked when a list opens.
- **Columns** lets each user choose which columns a list shows; the choice is
  remembered on that PC.
- **Double-click** a row to open it; a list no longer has a pane on the side.

### Screens reworked

- **Sell:** Quotations and Sales Returns are grids like the other sales lists;
  every sales list searches by customer and has the Period; Credit Notes,
  Proforma, Customer Statements (ageing and statement), Commission (rates,
  collected, payouts), Targets and Loyalty follow the one-line rule.
- **Buy:** Goods Receipts, Purchase Invoices and Purchase Returns name the
  **supplier** in a column and on the bar, and are searched by supplier;
  Purchase Orders too. All four have the Period and Columns.
- **Money:** Receipts, Payments and Refunds are grids with the Period, a
  search that finds the customer or supplier, and Apply / Reverse on the bar.
  (A refund list filtered by customer used to match nothing; fixed.)
- **Accounts:** Journal Entries is a grid with the Period and "Posted by";
  Trial Balance, Profit & Loss, Balance Sheet and Ledgers carry the period on
  the line; GST Returns, E-Invoice, TCS and Control Accounts follow the rules.
- **Stock:** Physical Count names each warehouse and shows progress; Stock
  Summary and Expiry Monitor show counters instead of cards; Stock Ledger,
  Transactions and Opening Stock have the Period.
- **Masters and settings:** Customers, Products and Vendors, and every setup
  list (users, roles, units, branches, tax, territories, price lists ...), have
  the selection bar; Audit Logs and Diagnostics are grids.

### Behind the screens

- **A nightly backup.** The server backs up every database at 02:00 into
  `C:\ProgramData\Agency Platform\backups\daily`, keeping the newest 7. The
  installation guide explains how to restore one. (Proven on 2026-09-27 by
  restoring a backup into a fresh database: every firm, user, invoice and
  journal entry came back.)
- **Indirect Expenses.** The books open with an *Indirect Expenses* group:
  Rent, Salaries and Wages, Electricity, Telephone and Internet, Travel and
  Conveyance, Office and General Expenses, Repairs and Maintenance, Bank
  Charges. An upgraded firm gets them too.

## Not in 1.0.2 (known, planned)

- **The Expenses screen** (Accounts → Expenses: record rent or fuel without
  writing a journal) is built and waiting for review; it comes in the next
  build. Until then an expense is recorded as a journal entry (P&L guide,
  section 3).
- The Profit & Loss does not yet show gross profit above net profit.
- Share by WhatsApp or email, bank reconciliation, Excel import of masters.
- The Execution Log (Settings → Tax) still shows ids rather than rule names.
- The installer is not signed yet: Windows SmartScreen warns and names the
  publisher *Agency*.
