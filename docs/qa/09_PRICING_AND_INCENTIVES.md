# Pricing, promotions, loyalty, commission and targets

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-09-25 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Pricing, promotions and incentives

Price Lists, Promotions, Commission and Targets are under **Sales**; Loyalty
under **Masters**; the promotion and loyalty reports under **Reports**.
Pricing and loyalty cases use the selling preparations (see *Selling*, above);
commission uses `commission-firm`:

| Preparation | Starts you with |
| --- | --- |
| `loyalty-points` | `selling-invoiced` — Vijaya's invoice for 483.21 — plus **200 points** credited to Vijaya by adjustment |
| `commission-firm` | `territory-firm` plus: firm-wide **4%** of money collected; **Asha 15%** on `QA-P` only; **Bala** a ladder (2% to 50,000 then 4%, nothing below 1,000, 2% bonus when his target is met). Asha sold 20 `-P` (2,360.00) and 30 `-Q` (3,540.00); Bala 40 `-Q` (4,720.00); **all collected** today. This month's targets: Asha 1,000 (met), Bala 100,000 (missed) |

### TC-INCENT-001 — A price list is a ladder, and a promotion still outranks it

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps**
  1. As the prepared **Firm admin**, Sales → **Price Lists** → select `STANDING` (do not open it).
  2. Double-click `STANDING` → **Add product**: `QA-DET`, From qty **25**, Discount % **8** → Save.
  3. Quotations → New for `QA-C01`, DET qty **30** → Create draft → Revise.
- **Expect**
  - Step 1: the pane reads `STANDING · applies to Everyone`, "In force from 2000-01-01", and three rates for DET: `2%`, `from 15: 4.25%`, `from 18: 6.75%`. Products column 3 (it counts rate rows).
  - Step 2: "Price list saved."; a fourth line `from 25: 8%`.
  - Step 3: "Last priced at **7.5**% by a promotion" — BULK5 outranks the list at 25+.
### TC-INCENT-002 — Editing an active promotion makes a new revision

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** Sales → **Promotions** → select `BULK5` → Edit → change only the Description → Save. Read the list and the selected row's pane.
- **Expect:** "Promotion BULK5 saved as a new revision; the one you opened is now inactive."; a second BULK5 row appears. The pane reads "BULK5 · revision 2 · applies at 10" and, in the plain English the desktop now words conditions in, "Applies when: Quantity on the line is at least 25". An active offer is superseded, never rewritten — and its claims and limits follow the version group, not the row.
### TC-INCENT-003 — Promotion reports count a claim once, at approval

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved. (one approved order used coupon `WELCOME10`.)
- **Steps:** Reports → Operational Reports → **Promotion performance**, **Coupon performance**, **Promotion claims**.
- **Expect**
  - Performance: `WELCOME` with 1 claim; BULK5, BIGORDER and CLEARANCE listed with 0.
  - Coupons: `WELCOME10` with 1 claim; `WELCOME10B` listed at **0** — a code nobody presented is still listed.
  - Claims: one row — WELCOME, coupon WELCOME10, Vijaya Stores qa, SALES_ORDER, the order's number, benefit 25.20, **CLAIMED**.
### TC-INCENT-004 — An offer that does not stack ends the stack

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** Sales Orders → New for `QA-C01`: DET **60** at 84 (gross 5,040) → Create draft → Edit. Then Save order unchanged → Edit again.
- **Expect:** under the line's blank box "Last priced at **7.5**% by a promotion" (BULK5); the **Discount on the whole order** box blank with "Last taken off: 200 by a promotion." (BIGORDER). CLEARANCE (1% at 40+, priority 30) did **not** apply: BIGORDER (priority 20) ends the stack. Both survive the unchanged save.
### TC-INCENT-005 — Loyalty: the scheme, a balance, and spending points settles a bill

- **Preconditions:** As *selling-invoiced*, plus 200 loyalty points credited to the first customer.
- **Steps**
  1. Masters → **Loyalty**. Reports → Financial Reports → **Loyalty balances**.
  2. Sales Invoices → select Vijaya's approved invoice → **Use points** → 100 → **Use them**.
  3. Journal Entries → the top `LOY-RED-SI-…` → View. Customers → C01.
  4. Use points again, 5000.
  5. Reports → Operational Reports → **Points about to lapse**.
- **Expect**
  - Step 1: the banner "2 points per 100, worth 1 each and expire after 24 months. At least 50 before any can be spent."; the balances report lists Vijaya with **200** points worth 200.00 — **more if your build ran the loyalty scheme setup before approving her invoices**: points are earned at approval, not credited afterward, so an invoice approved while the scheme was already on adds its own 2 per 100 on top of the 200 credited here.
  - Step 2: "100 points used on SI-…".
  - Step 3: Dr **2600 Loyalty Payable 100.00** / Cr **1100 Trade Receivables 100.00**. Outstanding **383.21** — 100 lower; the invoice's total and tax unchanged: the bill is **settled**, not discounted.
  - Step 4: refused outright: "That customer holds 100.0000 points, not 5000.0000." No journal.
  - Step 5: **empty** — nothing in this store is within 90 days of lapsing. *(WHOLE01's aged batches, and the oldest-first spending they showed, need points two years old; a preparation cannot age them.)*
### TC-INCENT-006 — Commission blends rates per line, and a ladder's floor is a round number

- **Preconditions:** As *territory-firm*, plus commission rules, targets and three collected sales, as in the preparation table.
- **Steps:** as the prepared **Firm admin**, Sales → **Commission** → **Collected** view, from `2026-04-01` to the end of this month → **Show**. Then Sales → **Targets** → **Achievement** for this month.
- **Expect**
  - **Asha**: collected **5,900.00**, commission **495.60** — 15% of 2,360 on `-P` plus 4% of 3,540 on everything else: **8.4%**, neither of the two rates that govern her. Target **Met**.
  - **Bala**: collected **4,720.00**, commission **94.40** — exactly **2.00%**, the bottom band; above the 1,000 floor; target **Missed**, so no bonus.
  - Achievement: Asha 1,000 target achieved; Bala 100,000 wanted, 4,720 invoiced (4.72%), 95,280 short.
### TC-INCENT-007 — Payouts: accrue, approve, pay, cancel

- **Preconditions:** As *territory-firm*, plus commission rules, targets and three collected sales, as in the preparation table.
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
### TC-INCENT-008 — Whoever states a debt must not move the cash

- **Preconditions:** As *territory-firm*, plus commission rules, targets and three collected sales, as in the preparation table.
- **Steps:** sign in as the prepared **Asha** (`SALES_EXECUTIVE`), expand Sales. **(HTTP)** as Asha: `GET /api/v1/commission/payouts`; `POST /api/v1/commission/payouts/{any id}/approve` and `/pay`.
- **Expect:** no Commission, Targets, Price Lists or Promotions under Sales. All three calls **403**.
---

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 09-S01 | **Sales → Price Lists** | Offered to any role holding `PRICE_LIST_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 09-S02 | **Sales → Promotions** | Offered to any role holding `PROMOTION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 09-S03 | **Sales → Commission** | Offered to any role holding `COMMISSION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 09-S04 | **Sales → Targets** | Offered to any role holding `SALES_TARGET_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 09-S05 | **Masters → Loyalty** | Offered to any role holding `LOYALTY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
