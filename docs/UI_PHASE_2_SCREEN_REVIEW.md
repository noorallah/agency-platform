# Phase 2 screen review against the UI guidelines

Owner, 2026-09-27: "review all modules' UI as per the new UI guidelines".
Every screen reachable from the phase 2 menu was read in its phase 2 code
path and checked against `docs/UI_PHASE_2_DESIGN.md` 4.5 (one line above the
grid), 4.7 (list screens, as built), 4.11 (window sizes), 4.14 (readability)
and 7 (measures of done), plus option C (the selection bar, owner
2026-09-27). This is the code review; a screenshot pass against the running
backend at 1366 x 768 and 1920 x 1080 follows when the machine has the
memory for it.

**Checks.** 1 band above the grid; 2 toolbar (the shared line order, "+ New"
last, no per-row action column); 3 selection bar where rows can be picked;
4 side pane; 5 Period and Columns on dated lists; 6 fixed widths, auto-picked
first row; 7 status and amounts in words and Indian digits.

**Severity.** High = breaks the one-line / no-band rule, or leaves an action
out of reach. Medium = missing selection bar, Period, Columns, or a side
pane. Low = cosmetic.

**Result.** 30 High, 7 Medium, 19 Low. All sales and purchase document
lists, the masters (customers, vendors, products), receipts, payments,
journal, counts and every screen built on `ResourceManagementPage` pass.

## High

| Area | Screen | What is wrong |
| --- | --- | --- |
| Sell | Credit Notes | Notice box above the grid; errors as red text; full-screen spinner |
| Sell | Customer Statements | Ageing/Statement switch is a band; free-text From/To in the search slot; raw table, amounts not in Indian digits, types in capitals |
| Sell | Commission | Rates/Collected/Payouts switch is a band; a notice on every view; total cards; payout steps only in a per-row column, rows cannot be picked |
| Sell | Targets | Raw button row with its own From/To; rows cannot be picked, Edit/Delete right-click only; "Runs" in capitals |
| Sell | Loyalty | Scheme sentence, customer picker and balance crammed into the search slot; raw buttons; amounts not Indian |
| Sell | Territories | Tree card as a side pane; the bulk bar sits in the hidden "+ filter" slot |
| Stock | Stock Summary | Eleven counters in a band, not on the line; raw toolbar |
| Stock | Expiry Monitor | Six coloured cards with hard-coded colours above a fixed-height grid |
| Accounts | Ledgers | Own row of account/period pickers and a figures band above the table |
| Accounts | Trial Balance, Profit & Loss, Balance Sheet | Own period-picker band (and Balanced chip) above the table |
| Accounts | GST Returns | GSTR-1/3B switch is a band; period panel crammed into the search slot; raw tables |
| Accounts | E-Invoice | Sandbox notice box; per-row action column still drawn; Withdraw / Try again reachable only there |
| Accounts | TCS | Policy sentence as the search; Settings takes "+ New"'s place; no Period, rows cannot be picked |
| Accounts | Control Accounts | Sentence band; raw table with a button on every row |
| Masters | Units, UOM Groups, Packaging Types, Conversion Rules, Industry Templates | Edit/Delete only by right-click, double-click does nothing; the bar appears with nothing on it |
| Masters | Packaging Levels | Product picker with helper text and an error line above the grid; scan card in the search slot |
| Masters | Storage Areas | Always the first warehouse; no way to reach another warehouse's storage |
| Masters | Places | The level trail (the only way back up) is hidden under "+ filter" |
| Admin | Roles, Permissions | A Roles/Permissions strip above the grid (the menu already lists both) |
| Admin | Audit Logs, Diagnostics | Filter-row band and sentence; list plus a permanent detail pane; first entry auto-picked |
| Settings | Tax Configuration, Tax Rules | Still the phase 1 master/detail: own search, status chips in capitals, card list, New at the bottom of a panel |

## Medium

| Area | Screen | What is wrong |
| --- | --- | --- |
| Sell | Route Builder | Fixed 280 px route picker on the line; the screen's own Find is hidden under "+ filter" |
| Stock | Stock Ledger, Transactions, Opening Stock | Dated lists with no Period and no Columns |
| Settings | Financial Years, Numbering Series | List tiles with buttons on every row; status in capitals |
| Settings | Execution Log | No Period, no Columns; raw ids, capitals and timestamps |

## Low

Beat Plans ("Today's calls" stays on the line disabled rather than on the
bar); Call Lists (cards, acceptable for a day sheet); Purchase Invoices and
Purchase Returns (counters do not filter); Purchase Dashboard (a dashboard on
a list page; amounts not Indian); Inventory and Stock Search (no Columns);
Batches (no Columns); Import / Export (wizard pages); Branches and Warehouses
(status filter options in capitals); Reports (own From/To rather than the
Period control, permanent report list); Licensing (a "coming soon"
placeholder in the menu); Platform Dashboard (raw statuses); Firm Settings
(raw "FIRM_UPDATE is required"); Purchase and Inventory Settings (repeated
title); Rule Simulator (a tool page); Tax Settings (a search box that
searches nothing).

## Shared fixes, each covering several screens

1. `ManagementWorkspaceLayout`: in phase 2 put `viewBar` on the page line,
   not above the grid (Commission, Customer Statements, GST Returns).
2. A notice slot: explanatory text behind the title's (i), not a box above
   the grid; a search panel that is not a search stays out of the 260 px
   slot (Credit Notes, E-Invoice, Commission, TCS, Loyalty, Control
   Accounts, Audit Logs, Diagnostics).
3. One accounting-period picker on the line (Trial Balance, P&L, Balance
   Sheet, Ledgers); `DateRangeFilter` for GST Returns, TCS, Statements,
   Targets and Reports.
4. Proper layout slots for a bulk bar and a level trail rather than
   `filterPanel` (Territories, Places).
5. A grid's right-click actions offered on the selection bar (the five UOM
   screens, Targets, E-Invoice, Commission payouts).
6. `StatusBadge` in words in phase 2; `Phase2WideTable` infers numeric
   columns from the heading as the grid does.
7. One phase 2 master/detail pattern -- grid, selection bar, detail in a
   window, nothing auto-picked -- for Audit Logs, Diagnostics, Financial
   Years, Numbering Series, Tax Configuration and Tax Rules.
8. Period and Columns on the inventory movement grid (Stock Ledger,
   Transactions, Opening Stock); Stock Summary hands its counters to the
   line.
9. `TabGroupPage`'s strip on the line (Roles / Permissions).
10. `WorkspaceToolbar.forList()` moves trailing widgets that need a picked
    row to the selection bar (Beat Plans).

## Fix log

Fixes land one PR per group; each row above is struck through here with its
PR number when merged.
