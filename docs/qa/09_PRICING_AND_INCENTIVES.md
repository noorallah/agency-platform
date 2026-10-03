# Pricing, promotions, loyalty, commission and targets

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-10-03 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
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
### TC-INCENT-009 — Buy X get Y at a discount, and a combo price

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a second product `QA-Q` priced like DET (create one), so a combo has two items.
- **Steps:** as the prepared **Firm admin**: Sell → Pricing → **Promotions** → New. (a) Benefit *Buy X get Y at a discount*: buy 2, get 1 at **50%**, optional cap amount. Save and activate. Quotations → New for Vijaya → `QA-DET` × 3, then × 6, then × 1. (b) New promotion, benefit *Combo price*: pick DET and `-Q` in the product pick, amount **150** for the set. Activate. A quotation with DET × 2 and Q × 2, then DET × 2 and Q × 1.
- **Expect:** (a) the discount is on **whole groups only**: 3 units make one group (the third unit at half price of what that unit has left after other discounts), 6 make two, 1 makes none; a cap limits the total and is shared across the lines in proportion. (b) each **complete set** across the lines sells for the combo amount and the saving (the sets' normal value less 150) is spread across the lines by value; DET × 2 with Q × 2 is two sets, DET × 2 with Q × 1 is one set and the leftover DET is at its normal price. The offer editor shows the benefit and its fields.
### TC-INCENT-010 — Bonus loyalty points, customer history and day-and-time conditions

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-invoiced*, plus 200 loyalty points credited to the first customer.
- **Steps:** as the prepared **Firm admin**: Sell → Pricing → **Promotions** → New *Bonus loyalty points* with a multiplier of **3** (the benefit stands alone on its offer), dated today. Raise and approve a bill for Vijaya and read her balance (Masters → Loyalty). Try a multiplier of 11 or 0. Next, New promotion with a 5% discount and the condition **Customer order count** = 0 (first order), another with **Days since last order** = 30. Then New promotion 5% with **Days of the week** = Sat and Sun, and another with **Time of day** between 16:00 and 18:00. Try a time window crossing midnight, and a weekday outside 1-7 through the API. Quote a bill on a weekday morning, on a Saturday, and inside the window.
- **Expect:** an approved bill earns points at the scheme's rate **times the largest multiplier** among the live points offers whose conditions hold on the bill's date; the audit row names the offer and the multiplier; the offer is passed over by the discount engine with a trace note. A multiplier outside 1-10 is refused. Order-count and days-since-last-order conditions are tested against the customer's approved and closed bills on or before the date (a customer with none has count 0). Weekend-only and time-window offers apply only inside their day or window (time is India time, taken from the quotation's or order's own creation time); a window that crosses midnight and a weekday outside 1-7 are refused when the condition is written.
### TC-INCENT-011 — Bulk coupon codes, and copying an offer with new dates

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Sell → Pricing → **Promotions** → open the coupon-only offer **WELCOME** → coupons → **Generate codes**: count 50, prefix `DIWALI`, a description and a window → Generate; then ask for 6,000. **Export codes**. Use one code on a quotation twice, and for a second customer. Back on the grid select WELCOME → **Copy with new dates...** with a code suffix `-NOV` and a new window.
- **Expect:** 50 random codes `DIWALI-XXXXXXXX` are made from an alphabet without look-alike characters, each usable **once** and once per customer, all or nothing; 6,000 is refused (limit 5,000). The export is a CSV of the offer's codes with their uses. A code already used cannot be redeemed again. The copy is a **DRAFT** at version one with code `…-NOV`, the same conditions and benefits and the new window; its coupons are **not** copied; the audit trail has *promotion.copied* naming the source. The grid selects one offer at a time (the API takes up to 100).
### TC-INCENT-012 — Claims to the principal

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** a principal (Masters → Items → Principals) and a brand under it on `QA-DET`; a promotion the principal funds (principal and **share %** on the promotion editor) that was claimed on an approved bill; an expiry write-off of a DET batch; a sales return of DET completed with damaged goods. A vendor to be the principal's supplier account.
- **Steps:** as the prepared **Firm admin**: Buy → Money → **Principal Claims** → New → pick the principal and the period → Preview. Raise the claim. Raise it again for the same period. Then record the principal's **credit note** (Accounts → Party Adjustments, kind *Principal claim*) against it, and a payment into the bank for the rest. Reverse one receipt. Cancel the claim in a second run and raise it again. Print.
- **Expect:** the preview gathers each source **once**: scheme redemptions (at the principal's share of the benefit), expiry write-offs of its products (at book value) and damaged or scrapped lines of completed sales returns (at the taxable rate credited). Raising posts Dr *Claims Receivable from Principals* and Cr promotional expense (schemes) or inventory adjustment (stock). A second claim over the same sources is refused or empty (one live claim per source). Settlement by credit note and by bank payment moves the status RAISED → PART_SETTLED → SETTLED; reversing a receipt moves it back. Cancelling frees the sources to be claimed again. Reading needs PURCHASE_VIEW, writing PURCHASE_APPROVE. Free quantity on a bill line is not claimed yet.
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
