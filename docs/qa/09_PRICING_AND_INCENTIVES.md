# Pricing, promotions, loyalty, commission and targets

Part of the QA test suite in `docs/qa/` for **release 1.3.0**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > Documents > Proforma` is a screen in the
Documents column, and `Settings > Set up > Pricing > Price Lists` is the gear at the
right of the bar. Generated on 2026-10-05 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
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
  1. As the prepared **Firm admin**, Settings > Set up > Pricing > **Price Lists** → select `STANDING` (do not open it).
  2. Double-click `STANDING` → **Add product**: `QA-DET`, From qty **25**, Discount % **8** → Save.
  3. Sell > Quotations → New for `QA-C01`, DET qty **30** → Create draft → Revise.
- **Expect**
  - Step 1: the pane reads `STANDING · applies to Everyone`, "In force from 2000-01-01", and three rates for DET: `2%`, `from 15: 4.25%`, `from 18: 6.75%`. Products column 3 (it counts rate rows).
  - Step 2: "Price list saved."; a fourth line `from 25: 8%`.
  - Step 3: "Last priced at **7.5**% by a promotion" — BULK5 outranks the list at 25+.
### TC-INCENT-002 — Editing an active promotion makes a new revision

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** Settings > Set up > Pricing > **Promotions** → select `BULK5` → Edit → change only the Description → Save. Read the list and the selected row's pane.
- **Expect:** "Promotion BULK5 saved as a new revision; the one you opened is now inactive."; a second BULK5 row appears. The pane reads "BULK5 · revision 2 · applies at 10" and, in the plain English the desktop now words conditions in, "Applies when: Quantity on the line is at least 25". An active offer is superseded, never rewritten — and its claims and limits follow the version group, not the row.
### TC-INCENT-003 — Promotion reports count a claim once, at approval

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved. (one approved order used coupon `WELCOME10`.)
- **Steps:** Reports > Operational → **Promotion performance**, **Coupon performance**, **Promotion claims**.
- **Expect**
  - Performance: `WELCOME` with 1 claim; BULK5, BIGORDER and CLEARANCE listed with 0.
  - Coupons: `WELCOME10` with 1 claim; `WELCOME10B` listed at **0** — a code nobody presented is still listed.
  - Claims: one row — WELCOME, coupon WELCOME10, Vijaya Stores qa, SALES_ORDER, the order's number, benefit 25.20, **CLAIMED**.
### TC-INCENT-004 — An offer that does not stack ends the stack

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** Sell > Sales Orders → New for `QA-C01`: DET **60** at 84 (gross 5,040) → Create draft → Edit. Then Save order unchanged → Edit again.
- **Expect:** under the line's blank box "Last priced at **7.5**% by a promotion" (BULK5); the **Discount on the whole order** box blank with "Last taken off: 200 by a promotion." (BIGORDER). CLEARANCE (1% at 40+, priority 30) did **not** apply: BIGORDER (priority 20) ends the stack. Both survive the unchanged save.
### TC-INCENT-005 — Loyalty: the scheme, a balance, and spending points settles a bill

*Corrected on 2026-10-07 from the pricing pass (ten rounds driven over HTTP: `docs/qa/PRICING_API_CHECK_ROUND_1_2026-10-06.md` to `docs/qa/PRICING_API_CHECK_ROUND_10_2026-10-07.md`). The earlier text named figures the product does not give; this text is what it does give. The steps are not yet re-driven on screen.*

- **Preconditions:** As *selling-invoiced*, plus 200 loyalty points credited to the first customer.
- **Steps**
  1. Settings > Set up > Pricing > **Loyalty**. Reports > Financial → **Loyalty balances**.
  2. Sell > Sales Invoices → select Vijaya's approved invoice → **Use points** → 100 → **Use them**.
  3. Accounts > Journal Entries → the top `LOY-RED-SI-…` → View. Masters > Customers → C01.
  4. Use points again, 5000.
  5. Reports > Operational → **Points about to lapse**.
- **Expect**
  - Step 1: the banner "2 points per 100, worth 1 each and expire after 24 months. At least 50 before any can be spent." The 50 is a **balance to reach** before any can be spent, not the smallest redemption: a customer holding 109.66 can spend 40. The balances report lists Vijaya with **209.6642** points worth 209.66: the 200 credited and **9.6642 earned by approving her invoice of 483.21** (2 per 100). It has a **lapsed** column, 0 here.
  - Step 2: "100 points used on SI-…".
  - Step 3: Dr **2600 Loyalty Payable 100.00** / Cr **1100 Trade Receivables 100.00**. Outstanding **383.21**, 100 lower; the invoice's total and tax unchanged: the bill is **settled**, not discounted.
  - Step 4: refused outright: "That customer holds **109.6642** points, not 5000.0000." No journal.
  - Step 5: **empty**: nothing in this store is within 90 days of lapsing. *(WHOLE01's aged batches, and the oldest-first spending they showed, need points two years old; a preparation cannot age them. Lapsed points are TC-INCENT-017.)*
### TC-INCENT-006 — Commission blends rates per line, and a ladder's floor is a round number

*Corrected on 2026-10-07 from the pricing pass (ten rounds driven over HTTP: `docs/qa/PRICING_API_CHECK_ROUND_1_2026-10-06.md` to `docs/qa/PRICING_API_CHECK_ROUND_10_2026-10-07.md`). The earlier text named figures the product does not give; this text is what it does give. The steps are not yet re-driven on screen.*

- **Preconditions:** As *territory-firm*, plus commission rules, targets and three collected sales, as in the preparation table.
- **Steps:** as the prepared **Firm admin**, Sell > Incentives > **Commission** → **Collected** view, from `2026-04-01` to the end of this month → **Show**. Then Sell > Incentives > **Targets** → **Achievement** for this month.
- **Expect**
  - **Commission is on net sales**: tax and freight earn nothing. Collected and invoiced stay the money itself (5,900.00 and 4,720.00).
  - **Asha**: collected **5,900.00**, commission **420.00**: 15% of her 2,000.00 net on `-P` plus 4% of 3,000.00 on the rest, **8.4% of her net sales of 5,000.00**, neither of the two rates that govern her. Target **Met**.
  - **Bala**: collected **4,720.00**, commission **80.00**: exactly **2.00% of his net sales of 4,000.00**, the bottom band; above the 1,000 floor; target **Missed**, so no bonus.
  - Achievement: Asha 1,000 target achieved; Bala 100,000 wanted, 4,720 invoiced (4.72%), 95,280 short.
- **Needs a clean firm.** The figures are the preparation's own: a `commission-firm` that has had other sales or returns reads other totals (Asha read 8,260.00 collected on a used one). Run it on a fresh preparation.
### TC-INCENT-007 — Payouts: accrue, approve, pay, cancel

*Corrected on 2026-10-07 from the pricing pass (ten rounds driven over HTTP: `docs/qa/PRICING_API_CHECK_ROUND_1_2026-10-06.md` to `docs/qa/PRICING_API_CHECK_ROUND_10_2026-10-07.md`). The earlier text named figures the product does not give; this text is what it does give. The steps are not yet re-driven on screen.*

- **Preconditions:** As *territory-firm*, plus commission rules, targets and collected sales, as in the preparation table, **but the sales must be dated before today**. A period must have ended before it can be accrued, and the preparation dates its three sales today, so on the day it is built the case cannot run: date the sales yesterday, or run the case the day after the preparation.
- **Also needs:** three people: one who accrues (the Firm admin), a **Firm Manager** to approve, an **Accountant** to pay.
- **Steps**
  1. Commission → **Payouts** → **Accrue period** for the 1st of the month to **yesterday** → Accrue. Try this month as well.
  2. On Bala's DRAFT look for Pay. As the Firm admin who accrued, try **Approve**. Sign in as the Firm Manager and **Approve**. As the Firm Manager try **Pay**; sign in as the Accountant and **Pay** (paid on a day from the approval to today, from `1000 Cash`).
  3. **Cancel** Asha's draft.
  4. Accrue the same period again.
- **Expect**
  - Step 1: "2 payout(s) accrued.", both DRAFT; the figures follow the sales you dated (in the check, Asha 190.00 and Bala 40.00). This month is refused: "That period has not ended…" and the date it can be accrued from.
  - Step 2: no Pay on a draft (**(HTTP)** paying it: 422, "Only an approved payout can be paid. Approve it first, which is what recognises the debt."). **The person who accrued cannot approve**: 403 "The person who accrued a payout cannot approve it…". The Firm Manager approves: "… approved. The cost and the debt are on the ledger." **The person who approved cannot pay**: 403. The Accountant pays: "… paid." Journal Entries: `COMM-YYYYMM-<first 8 characters of the id>` (Dr Commission Expense / Cr Commission Payable, dated the accrual day) and the same reference with `-PAY` (Dr Commission Payable / Cr Cash). **(HTTP)** paying a paid payout: 422 "This payout has already been paid on DD-MM-YYYY. It cannot be paid a second time."; a paid-on date before the approval or after today is refused.
  - Step 3: "… cancelled. The period is free to accrue again.", nothing posted, because a draft had no journal.
  - Step 4: refused with a **409**: "A commission payout already covers part of that period for this salesman (…)." Bala's paid payout still holds it; accruing for Asha alone would succeed.
### TC-INCENT-008 — Whoever states a debt must not move the cash

- **Preconditions:** As *territory-firm*, plus commission rules, targets and three collected sales, as in the preparation table.
- **Steps:** sign in as the prepared **Asha** (`SALES_EXECUTIVE`), expand Sales. **(HTTP)** as Asha: `GET /api/v1/commission/payouts`; `POST /api/v1/commission/payouts/{any id}/approve` and `/pay`.
- **Expect:** no Commission, Targets, Price Lists or Promotions under Sales. All three calls **403**.
### TC-INCENT-009 — Buy X get Y at a discount, and a combo price

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a second product `QA-Q` priced like DET (create one), so a combo has two items.
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Pricing > **Promotions** → New. (a) Benefit *Buy X get Y at a discount*: buy 2, get 1 at **50%**, optional cap amount. Save and activate. Sell > Quotations → New for Vijaya → `QA-DET` × 3, then × 6, then × 1. (b) New promotion, benefit *Combo price*: pick DET and `-Q` in the product pick, amount **150** for the set. Activate. A quotation with DET × 2 and Q × 2, then DET × 2 and Q × 1.
- **Expect:** (a) the discount is on **whole groups only**: 3 units make one group (the third unit at half price of what that unit has left after other discounts), 6 make two, 1 makes none; a cap limits the total and is shared across the lines in proportion. (b) each **complete set** across the lines sells for the combo amount and the saving (the sets' normal value less 150) is spread across the lines by value; DET × 2 with Q × 2 is two sets, DET × 2 with Q × 1 is one set and the leftover DET is at its normal price. The offer editor shows the benefit and its fields.
### TC-INCENT-010 — Bonus loyalty points, customer history and day-and-time conditions

*Corrected on 2026-10-07 from the pricing pass (ten rounds driven over HTTP: `docs/qa/PRICING_API_CHECK_ROUND_1_2026-10-06.md` to `docs/qa/PRICING_API_CHECK_ROUND_10_2026-10-07.md`). The earlier text named figures the product does not give; this text is what it does give. The steps are not yet re-driven on screen.*

- **Preconditions:** As *selling-invoiced*, plus 200 loyalty points credited to the first customer.
- **Also needs:** a second customer `QA-C02` (the order-count and days-since conditions are read on a customer with a history).
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Pricing > **Promotions** → New *Bonus loyalty points* with a multiplier of **3** (the benefit stands alone on its offer), dated today. Raise and approve a bill for Vijaya and read her balance (Settings > Set up > Pricing > Loyalty). Try multipliers of 11, 0 and 1. Then make a second points offer with a multiplier of 2 and bill again. Try adding a discount to a points offer. Next, New promotion with a 5% discount and the condition **Customer order count** = 0 (first order), another with **Days since last order** *at least* 30. Then New promotion 5% with **Days of the week** = Sat and Sun, and another with **Time of day** between 16:00 and 18:00. Try a time window crossing midnight, and a weekday outside 1-7 through the API. Quote a bill on a weekday morning, on a Saturday, and inside the window.
- **Expect:** an approved bill earns points at the scheme's rate **times the largest multiplier** among the live points offers whose conditions hold on the bill's date (a bill of 485.688 earns 29.1413, three times 9.7138, with the audit row naming the offer and the multiplier; with both ×3 and ×2 live it earns the larger, not 6); the offer is passed over by the discount engine with a trace note. **A multiplier must be above 1 and at most 10: 0, 1 and 11 are refused**, and a multiplier beside a discount on one offer is refused. **Customer order count counts approved bills**: an approved order with no bill is still a first order, so a customer with no approved bill has count 0 and gets the first-order offer until the first bill is approved. **Days since last order: use *at least* 30**: no at 29, yes at 30 and 35 (*equals* 30 applies on the thirtieth day only). A weekend-only or dated offer is tested with the quotation's date, so a quotation dated Saturday takes it and one dated Tuesday does not; a time window is tested at the moment the quotation is raised, and the trace says yes at 16:00 and 18:00 and no at 15:59 and 18:01 (India time). **The last step depends on the time of day**: inside the offer's window the quotation reads the offer's 5%, outside it the customer's own price list (9.25% for `QA-C02`). A window that crosses midnight, a weekday outside 1-7 and a minute of 1440 are refused when the condition is written.
### TC-INCENT-011 — Bulk coupon codes, and copying an offer with new dates

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Pricing > **Promotions** → open the coupon-only offer **WELCOME** → coupons → **Generate codes**: count 50, prefix `DIWALI`, a description and a window → Generate; then ask for 6,000. **Export codes**. Use one code on a quotation twice, and for a second customer. Back on the grid select WELCOME → **Copy with new dates...** with a code suffix `-NOV` and a new window.
- **Expect:** 50 random codes `DIWALI-XXXXXXXX` are made from an alphabet without look-alike characters, each usable **once** and once per customer, all or nothing; 6,000 is refused (limit 5,000). The export is a CSV of the offer's codes with their uses. A code already used cannot be redeemed again. The copy is a **DRAFT** at version one with code `…-NOV`, the same conditions and benefits and the new window; its coupons are **not** copied; the audit trail has *promotion.copied* naming the source. The grid selects one offer at a time (the API takes up to 100).
### TC-INCENT-012 — Claims to the principal

*Corrected on 2026-10-07 from the pricing pass (ten rounds driven over HTTP: `docs/qa/PRICING_API_CHECK_ROUND_1_2026-10-06.md` to `docs/qa/PRICING_API_CHECK_ROUND_10_2026-10-07.md`). The earlier text named figures the product does not give; this text is what it does give. The steps are not yet re-driven on screen.*

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** a principal (Settings > Set up > Item lists > Principals) and a brand under it on `QA-DET`; a promotion the principal funds (principal and **share %** on the promotion editor) that was claimed on an approved bill; an expiry write-off of a DET batch; a sales return of DET completed with damaged goods. A vendor to be the principal's supplier account, **and an approved supplier bill from that vendor, open for at least the credit note's amount**: a credit note is set against what the firm owes that supplier, and without such a bill it is refused ("… open bills add up to 0 …").
- **Steps:** as the prepared **Firm admin**: Buy > Money > **Principal Claims** → New → pick the principal and the period → Preview. Raise the claim. Raise it again for the same period. Then record the principal's **credit note** (Accounts > Books > Party Adjustments, kind *Principal claim*) against it, and a payment into the bank for the rest. Reverse one receipt. Cancel the credit note, then the claim, in a second run and raise it again. Print. Try to cancel the claim while a part of it is settled.
- **Expect:** the preview gathers each source **once**: scheme redemptions (at the principal's share of the benefit, one line naming the **bill** the offer was given on), free goods given on a bill (TC-INCENT-014), expiry write-offs of its products (at book value) and damaged or scrapped lines of completed sales returns (at the taxable rate credited). In the check: scheme 25.20 (60% of 42.00), expiry 120.00, breakage 81.90, total 227.10; a claim also carries a **Rate difference** figure, 0.00 here (TC-INCENT-015). Raising posts Dr *Claims Receivable from Principals* and Cr promotional expense (schemes) or inventory adjustment (stock). A second claim over the same sources is refused ("Nothing is left to claim from Principal …"). Settlement by credit note and by bank payment moves the status RAISED → PART_SETTLED → SETTLED, a payment beyond what is left is refused, and reversing a receipt moves it back. **Cancelling is refused while any part is settled**: "Part of this claim is settled; reverse its payments and cancel its credit notes first." Cancelling a raised claim frees the sources to be claimed again. **Access**: PURCHASE_MANAGER may raise and receive money; PURCHASE_EXECUTIVE and VIEWER read only; ACCOUNTANT and SALES_MANAGER are refused (403) on everything; receipts are recorded by whoever holds PURCHASE_APPROVE.
### TC-INCENT-013 — An offer's budget, in money and in free units

*Added 2026-10-07 from the pricing pass; driven over HTTP in round 2, and again in every later round (`docs/qa/PRICING_API_CHECK_ROUND_2_2026-10-06.md`); **not yet driven through the screens**, so correct the on-screen steps as you go.*

- **Preconditions:** The selling firm described in this section's preparation table. A product at 100.00 with no price list for the customer.
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Pricing > **Promotions** → New. (a) A discount of **10%** on the line, benefit kind scheme, with the **most benefit** box (money) at **50**. Activate. Raise two orders of 4 for different customers, Approve the first, then Approve the second. Raise an order of 2, then an order of 1. Cancel the first order and quote 4 again. (b) New offer *buy 2 get 1* with the **most free units** box at **3**. Two orders of 4 (2 free each); approve the first, then the second; re-save the second; raise an order of 2. Return the free unit of the first. (c) Edit a live offer and leave both budget boxes as they are, then clear one, then set 0 and -5. **(HTTP)** approve two orders for the last 40.00 at the same moment.
- **Expect:** (a) each order of 4 quotes 40.00 off. Approving the first reads 40.00 claimed and 10.00 left. Approving the second is refused: "Promotion … has 10.00 left of its budget of 50.00, and this document would take 40.00. Re-save the document to price it without." Re-saved, it prices at 472.00 (400.00 and 18% tax) with no discount and approves. While 10.00 is left an order of 4 and an order of 2 are quoted no discount, an order of 1 is quoted 10.00 and claims it, and after that the trace reads "This offer's budget of 50.00 has all been given." Cancelling the first order gives its 40.00 back and a new order of 4 is quoted again. A sale that comes back through a return or a credit note gives the offer's money back too. (b) the second order is refused in the same words for free units ("… has 1 left of its budget of 3 free units, and this document would take 2 …") and re-saves without free goods; an order of 2 (1 free) fits; the next is not quoted ("… budget of 3 free units has all been given."); a free unit that comes back on a return gives the offer its unit back, and the charged units coming back move nothing. (c) editing without the budget boxes keeps them and the count; clearing one lifts that budget; 0 and -5 are refused. **(HTTP)** of several approvals sent at once for the last of a budget, exactly one succeeds and the rest are refused; the losers stay DRAFT. The offer's performance report shows the budgets, what is claimed and what is left, beside the free units.
### TC-INCENT-014 — Free goods are claimed from the principal, at cost

*Added 2026-10-07 from the pricing pass; driven over HTTP in rounds 2 and 3 (`docs/qa/PRICING_API_CHECK_ROUND_2_2026-10-06.md`); **not yet driven through the screens**, so correct the on-screen steps as you go.*

- **Preconditions:** As *selling-delivered*, with the principal and brand of TC-INCENT-012 on `QA-DET`, held at a cost of 60.00. The note stages may be off.
- **Also needs:** an offer *buy 2 get 1* funded by the principal at a **share of 50%**.
- **Steps:** a counter bill of 4 DET with a free quantity of **1 typed on it** (no offer). A second bill of 4 with nothing typed, so the offer gives 2 free. Buy > Money > **Principal Claims** → New → the principal and this month → Preview → raise → raise again → cancel it.
- **Expect:** the typed unit is not an offer's. The preview has a **scheme** figure of 60.00 (the offer's 2 free units at 60.00, at the principal's 50% share) as one line "Free goods under …", 2 units, naming the bill; and a **free goods** figure of 60.00 for the typed unit as one line "Free goods given on the bill", 1 unit; total 120.00. Raising posts Dr *Claims Receivable from Principals* 120.00 / Cr *Cost of Goods Sold* 120.00; raising again is refused ("Nothing is left to claim from Principal …"); cancelling posts the mirror and the lines are proposed again; the print has a "Free goods" row. **Not claimed from the principal:** the free goods of a product branded to another principal, of a product held at a cost of 0, on a draft bill, or under an offer the firm funds itself. **A free unit that comes back after the claim was raised** comes off the next claim as a negative line, and a claim never goes below zero. A scheme line is claimed off what was **billed**, net of returns and credit notes, not off the order: an undelivered or closed order is not claimed. A discount that an offer gives on a line with free units is shared over the charged units only (a claim of 60.00, not 55.38).
### TC-INCENT-015 — A principal's price cut, claimed on the stock in hand

*Added 2026-10-07 from the pricing pass; driven over HTTP in round 3 (`docs/qa/PRICING_API_CHECK_ROUND_3_2026-10-06.md`); **not yet driven through the screens**, so correct the on-screen steps as you go.*

- **Preconditions:** As *selling-delivered*, with a principal and a brand on a product `QA-RD`, and **100 in stock from an opening entry dated before today at a cost of 60.00**.
- **Steps:** on the product, add a price revision with a **purchase price of 55.00 from today**. Buy > Money > **Principal Claims** → New → **Price cut (rate difference)** → the principal, the effective date (today) and the claim date → Preview. Receive 10 more today at 55.00 and sell 5 today, and preview again. Edit the grid: type a new rate of 54, then add a product. Try a new rate of 60 and of 61, the principal's other product, a product with no stock, and a cut dated tomorrow. Raise it. Raise it again. Cancel it, raise it again, and record a bank receipt of 200.00, then 300.00, then 1.00 more. Try to cancel while part is settled.
- **Expect:** the preview is **one line**: 100 at the old rate 60.00 and the new rate 55.00, **500.00**, "Price cut from … on stock at the close of the day before". The stock is the close of the **day before** the cut, from the stock ledger, so a receipt and a sale **today do not move it**. Typing 54 reads 600.00, "rates as typed". The refusals name the product: "the new rate 60 is not lower than the old rate 60.00, so there is nothing to claim."; not the principal's product; no stock at the close of the day before; the product twice; "A claim is raised on or after its period starts."; no effective date. A rate difference claim **stands alone**: ticking it with the period's kinds is refused, and it takes no period. Raising posts **Dr 1420 Claims Receivable from Principals 500.00 / Cr 5400 Purchase Price Variance 500.00**; no tax; **the stock and its valuation are not revalued**. Raising again is refused ("Nothing is left to claim from Principal … for the price cut of …"), as is a typed line for the same stock (it names the claim to cancel). The print has "New rates effective …", "Rate difference 500.00" and the table of item, batch, quantity, old rate, new rate and amount. Cancel posts the mirror and the line is proposed again. 200.00 reads PART_SETTLED with 300.00 outstanding, 300.00 SETTLED, 1.00 more is refused, and cancelling a part-settled claim is refused. **By batch** (a pharmacy preparation): the batches that held stock the day before appear as their own lines, each at its own old rate, and a batch received today does not.
### TC-INCENT-016 — Points spent on a bill are put back, and cancelling the bill puts them back

*Added 2026-10-07 from the pricing pass; driven over HTTP in rounds 1 and 2 (`docs/qa/PRICING_API_CHECK_ROUND_2_2026-10-06.md`); **not yet driven through the screens**, so correct the on-screen steps as you go.*

- **Preconditions:** As *selling-invoiced*, plus 200 loyalty points credited to the first customer, and 100 of them spent on the invoice as in TC-INCENT-005.
- **Steps:** Settings > Set up > Pricing > **Loyalty** → the customer's redemption → **Put points back**, with a reason (try it with none, then as a Sales Executive, then as the Sales Manager). Try again. Spend 10 points again on the same bill, then cancel the bill. Spend points on another bill that also has a receipt recorded against it, and try to cancel that bill.
- **Expect:** no reason is refused (422); a Sales Executive is refused (403); the Sales Manager with a reason: "Points put back." and a journal with the redemption's reference ending `-REV` (Dr 1100 / Cr 2600). A second time: "Those points were already put back, on …." A redemption not found, one that is not a redemption and another firm's: "Redemption not found." The ledger row says which redemption it reverses and whether it has been reversed. Points spent again on the same bill post a second redemption (`…-2`) and **cancelling the bill reverses that one too**. The bill with a receipt: "SI-… cannot be cancelled while it has money applied from RC-…. Reverse or cancel those first.", and the points stay spent.
### TC-INCENT-017 — Points past their date cannot be spent

*Added 2026-10-07 from the pricing pass; driven over HTTP in rounds 1 and 2 (`docs/qa/PRICING_API_CHECK_ROUND_2_2026-10-06.md`); **not yet driven through the screens**, so correct the on-screen steps as you go.*

- **Preconditions:** As *selling-invoiced*. **Needs points that have already lapsed**: a batch of points dated more than the scheme's expiry (24 months) ago. A preparation cannot age points, so build this by crediting a dated adjustment on a firm made for the purpose (the check used 70.8000 points lapsed, 2.3600 earned today and 100 given today).
- **Steps:** Settings > Set up > Pricing > **Loyalty** → the customer's page, then **Use points** on a bill for 103, then for 60. Run the sweep: `agency-server loyalty-expire` on the server, or **(HTTP)** `POST /api/v1/loyalty/expire`. Take points back with a **negative adjustment** larger than what can be spent.
- **Expect:** the customer's page shows the points, a **lapsed** figure (70.8000) and *redeemable* false until live points exist. Spending more than the live points is refused: "That customer holds 2.3600 points, not 70.0000. 70.8000 more ran out of time on … and can no longer be spent." (live points only). Spending 60 within the live points is taken, and the same request posts the redemption (Dr 2600 60.00 / Cr 1100 60.00) **and** the expiry of the lapsed batch (Dr 2600 70.80 / Cr 5700 70.80) with an EXPIRED entry "Earned …, lapsed …." The sweep takes only what other customers still held. Loyalty Payable before anything is spent equals the live points' worth plus the lapsed worth. A negative adjustment or a take-back after a return is **bounded by the points that can be spent**, never taken out of lapsed ones. Two batches credited the same day are spent **oldest first**. Loyalty Payable and the balances report agree to the paisa after redemptions, returns and expiries.
### TC-INCENT-018 — A customer's credit set against another bill

*Added 2026-10-07 from the pricing pass; driven over HTTP in rounds 7 to 10 (`docs/qa/PRICING_API_CHECK_ROUND_9_2026-10-06.md`); **not yet driven through the screens**, so correct the on-screen steps as you go.*

- **Preconditions:** As *selling-invoiced*. A bill of 24 at 100.00 (2,832.00 with tax) **paid in full**; 7 of it returned and the return completed, which leaves **826.00 of credit**; and a second bill of 12 (1,416.00), approved and unpaid.
- **Steps:** Sell > Receipts → **Customer credits** (the toolbar button) → the customer → the 826.00 credit → apply it to the second bill. Open the statement and Receivables. **(HTTP)** reverse the application. Apply 300.00, then try to **refund** 526.01 and 526.00 naming the credit. Cancel the return. Try to cancel the second bill while a credit is applied. Try an amount above the credit, above what the bill owes, and a future date. Sign in as a Viewer.
- **Expect:** the credit is listed as 826.00 available. Applied: the second bill reads 826.00 allocated and **590.00 outstanding**; the customer shows 590.00 and 0.00 held; **no journal is posted and Trade Receivables does not move**; the statement has an `ADVANCE_APPLY` row and closes at 590.00; a receipt of 590.01 is refused and 590.00 clears the bill. Reversing the application puts every figure back; a blank reason or a second reversal is refused; reversing it after the first bill's receipt was reversed still leaves the customer's account equal to the bills and the credits held. Part applied, the refund of 526.01 is refused ("… has only 526.00 of credit left to be paid back") and 526.00 goes out (Dr 1100 / Cr bank); a refund names its source or takes the oldest held credit. Cancelling the source return withdraws the application and the second bill owes 1,416.00 again; cancelling the target bill is refused: "SI-… cannot be cancelled while it has credit applied from SR-…. Reverse that application first." Refusals by name: "SR-… has only 826.00 of credit left to set against a bill.", "SI-… owes only 354.00.", "A credit cannot be applied on a future date." A credit note on a paid bill applies the same way and is withdrawn when the note is cancelled. An applied credit counts as **collected** for commission and targets on the bill it was applied to (once), and a loyalty redemption is capped at what the bill owes after it. A Viewer reads and cannot apply, reverse or refund (403). *On screen the panel applies a credit; reversing an application, a notice in Record Receipt that the customer holds credit, and a refund naming its source are not built yet (`docs/BACKLOG.md`), so do those steps over HTTP.*
### TC-INCENT-019 — A line bought or sold by the box

*Added 2026-10-07 from the pricing pass; driven over HTTP in rounds 2 to 5 (`docs/qa/PRICING_API_CHECK_ROUND_3_2026-10-06.md`); **not yet driven through the screens**, so correct the on-screen steps as you go.*

- **Preconditions:** As *ready-firm* for buying, *selling-invoiced* for selling. A product **kept in PIECE** with a conversion rule **1 BOX = 12 PIECE**, a purchase price of 60.00 a piece, GST 18%, a selling price of 100.00 a piece.
- **Also needs:** a unit with **no rule** (CARTON) to try the refusal.
- **Steps (buying, on screen):** Buy > Purchase Orders → New → the product, **2 BOX**, price blank → approve → receive in full → bill it. Return **1 BOX** off the receipt. Try 2 CARTON. **(HTTP)** the same with the unit named in other ways (no unit; BOX and PIECE both named; a price of 720.00 typed), and a receipt line typed in another unit than its order line. **(HTTP, selling; the sales editors have no unit box yet, D-PRC-53)** an order, a quotation and a counter bill for 2 BOX; a delivery note line naming another unit than its order line; a bill line typed in pieces; an offer *buy 10 get 1* on 2 BOX; a price list break "from 2 boxes".
- **Expect (buying):** the order line reads BOX, factor 12, 24 pieces, **720.00 a box**, gross 1,440.00, total 1,699.20. After the receipt **24 on hand at 60.00 (1,440.00)**: Dr 1200 1,440.00 / Cr 2300 1,440.00. After the bill: Dr 2300 1,440.00, Dr 1320 129.60, Dr 1330 129.60 / Cr 2100 1,699.20, **nothing to Purchase Price Variance**, and the stock valuation, the stock account and goods received not invoiced agree. Every way of naming the unit gives the same figures. The return of 1 BOX sends **12 pieces** out (Dr 2100 849.60 / Cr 1200 720.00 / Cr 1320 64.80 / Cr 1330 64.80). 2 CARTON: "… no active conversion rule converts CARTON to PIECE. Add one under Units -> Conversion Rules, or enter the quantity in PIECE." A receipt line in BOX against an order in PIECE: "Line 1 is received in BOX where PO-… orders it in PIECE. Receive it in the order's unit." **Expect (selling):** the order reads **1,200.00 a box** (a blank price is the piece price times the factor) and **24 pieces reserved**; the discount limit judges the line as a box; a delivery note line in another unit than its order line is refused by name; a bill line typed in pieces is capped, priced and judged in the note's unit; *buy 10 get 1* on 2 BOX gives **2 PIECE free, 26 ship**; a break "from 2 boxes" is taken by 24 pieces and not by 23. Selling 5 pieces costs 300.00 (60.00 a piece). Pieces that are not whole boxes are priced, moved and returned as pieces. A product kept in BOX and sold in PIECE needs its own PIECE-to-BOX rule (BACKLOG).
---

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 09-S01 | **Settings > Set up > Pricing > Price Lists** | Offered to any role holding `PRICE_LIST_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 09-S02 | **Settings > Set up > Pricing > Promotions** | Offered to any role holding `PROMOTION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 09-S03 | **Sell > Incentives > Commission** | Offered to any role holding `COMMISSION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 09-S04 | **Sell > Incentives > Targets** | Offered to any role holding `SALES_TARGET_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 09-S05 | **Settings > Set up > Pricing > Loyalty** | Offered to any role holding `LOYALTY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
