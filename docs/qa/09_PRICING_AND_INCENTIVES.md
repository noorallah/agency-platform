# Pricing, promotions, loyalty, commission and targets

Part of the QA test suite in `docs/qa/` for **release 1.3.0**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > Documents > Proforma` is a screen in the
Documents column, and `Settings > Set up > Pricing > Price Lists` is the gear at the
right of the bar. Generated on 2026-10-15 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
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

### TC-SELL-109 — Print says which paper the bill needs, and one print can be switched between half and full

*Added 2026-10-14 (backlog 151, row P1). The server was driven over HTTP on a preparation firm; the box on screen is covered by widget tests only and **no screen was clicked**, so those steps are written from the build. Nothing was put through a printer.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** a product **P** with stock; two customers, **A** (Bill paper: Firm's setting) and **B**. Where the firm types orders and delivery notes, each bill below continues a note.
- **Steps**
  1. With the firm's **Paper** at **A4** under *Print settings*, open customer B, set **Bill paper** to **Half page** and save. Raise and approve a one-line bill for B. Choose *Print*.
  2. Set **Paper** to **Half page (half of A4)** under *Print settings*. Raise and approve a one-line bill for A. Choose *Print*.
  3. In the box choose **Full page** and then *Print*.
  4. Choose *Print* on the same bill again and look at the box.
  5. Open customer B, set **Bill paper** to **Full page (A4)** and save. Choose *Print* on B's bill.
  6. In the box choose **Half page** and then *Print*.
  7. Raise and approve a bill for A with sixty lines. Choose *Print*.
  8. Choose *Print* on any bill and then *Cancel* in the box.
  9. Tick A's short bill and B's bill and choose *Print selected*.
  10. Set **Paper** back to **A4**.
- **Expect**
  - Step 1: no box. The bill prints on full A4 pages, though B is set to half a page.
  - Step 2: a box titled *Print* and the bill's number says the bill prints on a **Half page**, and to check the paper in the printer's tray. **Half page** is chosen, **Full page** is offered.
  - Step 3: full A4 pages.
  - Step 4: the box opens on **Half page** again: the choice of step 3 was for that print alone.
  - Step 5: the box says the bill prints on a **Full page** because this customer's bills are set to a full page. **Full page** is chosen, **Half page** is offered.
  - Step 6: half pages.
  - Step 7: the box says the bill prints on a **Full page** because it is too long for half a page. Nothing is offered to choose. It prints on full A4 pages.
  - Step 8: nothing prints and no message is shown.
  - Step 9: no box. One file: A's bill on half pages, B's on full pages.
- **Also true, by the server:** `paper=HALF` asked of a firm on A4 is refused (*The paper is chosen at printing only where the firm prints its bills on half pages.*).
### TC-SELL-110 — A product that needs two licences is checked for both

*Added 2026-10-14 (backlog 152, row P3). The server was driven over HTTP on a preparation firm; the two forms are covered by widget tests only and **no screen was clicked**, so the screen steps are written from the build.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** two active licence types, **L1** and **L2**; the firm holding a valid licence of each; a product **P** with stock; a customer **C** holding neither; *Licence Check* for sales set to **Block**.
- **Steps**
  1. Open product P. Under **Licences needed** choose *Add licence* and pick L1, then again and pick L2. Save.
  2. Raise a one-line sales order for P to customer C and choose *Approve*.
  3. Give customer C a valid licence of type L1. Approve the order again.
  4. Give customer C a licence of type L2 that expired last month. Approve the order again.
  5. Change C's L2 licence to be valid today. Approve the order again.
  6. Open product P, remove L2 from **Licences needed** with the cross on its chip, and save. Take C's L2 licence away. Raise and approve another order for P to C.
  7. Open P's category, tick L1 and L2 under **Licences needed**, and save. Open P, remove L1 so that the list is empty, and save. Raise and approve another order for P to C.
- **Expect**
  - Step 1: P shows two chips, L1 and L2, and the helper reads *The buyer must hold every one of these.*
  - Step 2: refused. The message names both licences: C holds no L1, and C holds no L2.
  - Step 3: refused. The message names L2 only.
  - Step 4: refused. The message says C's L2 licence expired, with its number and date.
  - Step 5: approved, with no licence warning.
  - Step 6: approved: P now needs L1 alone, as a product naming one licence always did.
  - Step 7: refused, naming L2: with no list of its own, P takes its category's two.
- **Also true, by the server:** a licence type on a product's or a category's list cannot be deleted; an edit that does not mention the list leaves it alone; the purchase check asks the supplier for every one the same way and only warns.
### TC-SELL-111 — A list opens on the financial year, and an older bill is one step back

*Added 2026-10-14 (customer task P6, IMP-3, backlog 155). Covered by widget tests; **no screen was clicked**, so the steps are written from the build, not from the screen.*

- **Fixture:** a firm with sales bills in two financial years (a demo firm with two years of trading; `ready-firm` holds one year only)
- **Steps**
  1. Open *Sales > Sales Invoices* and read the Period button.
  2. Look for a bill of last year by scrolling to the end of the list.
  3. Press the arrow to the left of the Period.
  4. Open the Period and choose **All dates**.
  5. Open a bill of last year and raise a sales return against it.
  6. Open *Sales > Sales Orders* from the menu, then go to Home and press **Orders to approve**.
  7. Open *Reports* and read the From and To dates.
  8. Open *Sales > Sales Returns* on a firm that has raised none this year.
- **Expect**
  - Step 1: the button reads **This financial year** and the list holds this year's bills only.
  - Step 2: no bill dated before the first day of the year is listed.
  - Step 3: the list shows last year's bills and the button reads its dates.
  - Step 4: bills of both years are listed, newest first.
  - Step 5: the return is taken; nothing asks which year to work in.
  - Step 6: from the menu the list is on **This financial year**; from Home it shows the drafts over **All dates**.
  - Step 7: From is the first day of the firm's financial year and To is today.
  - Step 8: the list says **Nothing in these dates** and how to see older ones, not *No search results*.
### TC-SELL-112 — The full-page bill carries what the trade's bill carries

*Added 2026-10-14 (customer task P2, PRT-4). Printed over HTTP by the build loop; **no screen was clicked**.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer. (, with a round the customer belongs to, and two batch-tracked products: one received with a manufacture date on its batch, one without)
- **Steps**
  1. Under *Sales > Sales Invoices > Print settings > Payment and terms*, type two lines of **Terms** and save.
  2. Sell and dispatch both products to the customer on his round (say 4 of the first with 1 free, 6 of the second) and raise the bill from the delivery note.
  3. Print the bill on a full page.
  4. Set the paper to **Half page** under *Print settings* and print the same bill.
  5. Print a bill of a product that keeps no batches.
- **Expect**
  - Step 3: the particulars name **Market** with the round's name. The lines have a **Mfg** column between Batch and Expiry: the first line reads the month and year its batch was made (`01/26`), the second is blank. The expiry is a whole date and no figure prints over the one beside it. The free goods print under the quantity. Under the lines **Total quantity** reads 10, and names 1 free beside it. Each line states **GST %** and **GST**; CGST and SGST are named in the totals and in the HSN summary. The terms print line by line under **TERMS**.
  - Step 4: the half page names **Market**, has the **Total quantity** row (10, and 1 under Free), and prints the terms under the amount in words. It has no Mfg column.
  - Step 5: no Mfg column; **Total quantity** is there; each tax component has its own rate and amount columns as before.
### TC-SELL-113 — A firm chooses the trade's layout for its bill, after seeing a sample

*Added 2026-10-14 (backlog 143, PRT-5). Built in the attended session; **no screen was clicked**.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer. (, with a customer on a round and a batch-tracked product with an MRP on its batch)
- **Steps**
  1. Under *Sales > Sales Invoices > Print settings*, keep the paper on **A4** and open **Bill layout**.
  2. Choose **Trade (boxed, with MRP and PTR)**, type a line of **Terms**, and press **Preview** without saving.
  3. Close the sample and the dialog without saving, and print any bill.
  4. Open *Print settings* again, choose **Trade**, save, and print the same bill.
  5. Set the paper to **Half page**, and look for **Bill layout**.
  6. Print a stock transfer or a contra voucher.
- **Expect**
  - Step 1: **Bill layout** reads **Standard**.
  - Step 2: a sample bill opens in the boxed layout, headed *SAMPLE - NOT A TAX INVOICE*, with the firm's own name and address, the line of terms just typed, and the columns M.R.P, D.Price, QTY, Free, P.T.R., Disc., GST%, Net Value, Batch, MfgDt and ExpDt.
  - Step 3: the bill prints in the standard layout: a preview saves nothing.
  - Step 4: the bill prints in the boxed layout. D.Price is the rate with its GST (250.00 at 18% reads 295.000); Gross less the discount is the taxable value; CGST and SGST are named in the totals; **Net Payable** is the bill's total. The customer's licences print under his details, not at the foot.
  - Step 5: no **Bill layout** box: the half page keeps its own layout.
  - Step 6: the transfer or voucher prints as before.
### TC-SELL-114 — A salesman with no sign-in, picked on a bill

*Added 2026-10-14 (P2, the firm's own list of salesmen). **No screen was clicked**; the server half is held by unit tests.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Settings > Selling > **Salesmen** → New: name `Phone order`, Signs in as left empty, Earns commission off → Save. Sell > Sales Invoices → New counter bill for `QA-C01`, one line `QA-DET` × 1; open the Salesman box and choose `Phone order` → Save. Open the saved bill.
- **Expect:** `Phone order` is saved with no user and appears in the list; it is offered in the Salesman box; the saved bill shows `Phone order` as its salesman. No user account was needed.

### TC-SELL-115 — What the Salesman box starts on

*Added 2026-10-14 (P2). **No screen was clicked**; the server half is held by unit tests.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** salesman entries `Asha` (tied to the user you sign in as), `Bala` and `Chitra`; `QA-C01` with account manager Bala and on a round whose primary salesman is Chitra and which Bala also covers (not primary); `QA-C02` with no account manager and the same round; a customer with neither.
- **Steps:** as the user tied to Asha: Sell > Sales Orders → New Order, choose `QA-C01`; read the Salesman box. Change it to Chitra. Repeat as a user tied to no entry with `QA-C01`, then `QA-C02`, then the customer with neither. Finally raise a delivery note and a bill from an order that names Chitra.
- **Expect:** signed in as Asha's user, the box starts on **Asha** for every customer, and Chitra can be picked instead and saves. As the untied user: `QA-C01` starts on **Bala** (account manager), `QA-C02` on **Chitra** (round's primary salesman), the third customer **blank**; a customer whose account manager does not cover the customer's round starts on the round's primary salesman, since the account manager would be refused on save. The note and the bill take **Chitra** from the order and do not ask. An inactive entry is never the starting choice.

### TC-SELL-116 — "Salesman required" refuses a save without one

*Added 2026-10-14 (P2). **No screen was clicked**; the server half is held by unit tests.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Settings > Selling > Sales Stages → switch **Salesman required** on → Save. Sell > Sales Orders → New Order for a customer with no account manager and no round, Salesman left blank → Create draft. Repeat for a delivery note and a sales bill. Switch the setting off and save each again. Last, with the setting on again, save a quotation with no salesman.
- **Expect:** with it on, the order, the delivery note and the bill are each refused with "This firm requires a salesman on every order, delivery note and bill. Choose one in the Salesman box." and nothing is saved. With it off, all three save. The quotation saves either way. Documents already saved are untouched by turning the switch on.

### TC-SELL-117 — Order By on the printed bill

*Added 2026-10-14 (P2). **No screen was clicked**; the server half is held by unit tests.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** save a bill naming salesman `Asha` and a second bill with none. Print each as a full-page bill in the **Standard** layout, then in the **Trade** layout. Delete the entry `Asha` (Settings > Selling > Salesmen) and print the first bill again. Print the first bill on the half-page and on the roll.
- **Expect:** both full-page layouts print an *Order By* row reading **Asha** (the trade layout at the head, the standard one in the particulars); the bill with no salesman prints no *Order By* row at all. After the entry is deleted the first bill still prints *Asha*. The half-page and the roll have no *Order By* row.

### TC-SELL-118 — Two salesmen cannot share a name

*Added 2026-10-14 (P2). **No screen was clicked**; the server half is held by unit tests.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** Settings > Selling > Salesmen: with `Phone order` present, New → name `phone order` → Save. Then New → name `Phone Order 2` → Save; edit it to read `PHONE ORDER` → Save.
- **Expect:** the first save is refused in words (the name is already on the list, whatever the case) and nothing is added; the second is saved, and the edit to `PHONE ORDER` is refused the same way.

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

- **Preconditions:** As *selling-invoiced*, plus 200 loyalty points credited to the first customer.
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
  - Step 5: **empty** — nothing in this store is within 90 days of lapsing. *(WHOLE01's aged batches, and the oldest-first spending they showed, need points two years old; a preparation cannot age them.)*
### TC-INCENT-006 — Commission blends rates per line, and a ladder's floor is a round number

- **Preconditions:** As *territory-firm*, plus commission rules, targets and three collected sales, as in the preparation table.
- **Steps:** as the prepared **Firm admin**, Sell > Incentives > **Commission** → **Collected** view, from `2026-04-01` to the end of this month → **Show**. Then Sell > Incentives > **Targets** → **Achievement** for this month.
- **Expect**
  - **Asha**: collected **5,900.00**, commission **420.00** — earned on the sale net of tax: 15% of 2,000 on `-P` plus 4% of 3,000 on everything else: **8.4%**, neither of the two rates that govern her. Target **Met**.
  - **Bala**: collected **4,720.00**, commission **80.00** — exactly **2.00%** of 4,000 net of tax, the bottom band; above the 1,000 floor; target **Missed**, so no bonus.
  - Achievement: Asha 1,000 target achieved; Bala 100,000 wanted, 4,720 invoiced (4.72%), 95,280 short.
### TC-INCENT-007 — Payouts: accrue, approve, pay, cancel

- **Preconditions:** As *territory-firm*, plus commission rules, targets and three collected sales, as in the preparation table.
- **Steps**
  1. Commission → **Payouts** → **Accrue period** for this month → Accrue.
  2. On Bala's DRAFT look for Pay; **Approve**; then **Pay** (paid on today, from `1000 Cash`).
  3. **Cancel** Asha's draft.
  4. Accrue the same period again.
- **Expect**
  - Step 1: "2 payout(s) accrued." — Asha **420.00**, Bala **80.00**, both DRAFT.
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
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Pricing > **Promotions** → New. (a) Benefit *Buy X get Y at a discount*: buy 2, get 1 at **50%**, optional cap amount. Save and activate. Sell > Quotations → New for Vijaya → `QA-DET` × 3, then × 6, then × 1. (b) New promotion, benefit *Combo price*: pick DET and `-Q` in the product pick, amount **150** for the set. Activate. A quotation with DET × 2 and Q × 2, then DET × 2 and Q × 1.
- **Expect:** (a) the discount is on **whole groups only**: 3 units make one group (the third unit at half price of what that unit has left after other discounts), 6 make two, 1 makes none; a cap limits the total and is shared across the lines in proportion. (b) each **complete set** across the lines sells for the combo amount and the saving (the sets' normal value less 150) is spread across the lines by value; DET × 2 with Q × 2 is two sets, DET × 2 with Q × 1 is one set and the leftover DET is at its normal price. The offer editor shows the benefit and its fields.
### TC-INCENT-010 — Bonus loyalty points, customer history and day-and-time conditions

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-invoiced*, plus 200 loyalty points credited to the first customer.
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Pricing > **Promotions** → New *Bonus loyalty points* with a multiplier of **3** (the benefit stands alone on its offer), dated today. Raise and approve a bill for Vijaya and read her balance (Settings > Set up > Pricing > Loyalty). Try a multiplier of 11 or 0. Next, New promotion with a 5% discount and the condition **Customer order count** = 0 (first order), another with **Days since last order** = 30. Then New promotion 5% with **Days of the week** = Sat and Sun, and another with **Time of day** between 16:00 and 18:00. Try a time window crossing midnight, and a weekday outside 1-7 through the API. Quote a bill on a weekday morning, on a Saturday, and inside the window.
- **Expect:** an approved bill earns points at the scheme's rate **times the largest multiplier** among the live points offers whose conditions hold on the bill's date; the audit row names the offer and the multiplier; the offer is passed over by the discount engine with a trace note. A multiplier outside 1-10 is refused. Order-count and days-since-last-order conditions are tested against the customer's approved and closed bills on or before the date (a customer with none has count 0). Weekend-only and time-window offers apply only inside their day or window (time is India time, taken from the quotation's or order's own creation time); a window that crosses midnight and a weekday outside 1-7 are refused when the condition is written.
### TC-INCENT-011 — Bulk coupon codes, and copying an offer with new dates

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Pricing > **Promotions** → open the coupon-only offer **WELCOME** → coupons → **Generate codes**: count 50, prefix `DIWALI`, a description and a window → Generate; then ask for 6,000. **Export codes**. Use one code on a quotation twice, and for a second customer. Back on the grid select WELCOME → **Copy with new dates...** with a code suffix `-NOV` and a new window.
- **Expect:** 50 random codes `DIWALI-XXXXXXXX` are made from an alphabet without look-alike characters, each usable **once** and once per customer, all or nothing; 6,000 is refused (limit 5,000). The export is a CSV of the offer's codes with their uses. A code already used cannot be redeemed again. The copy is a **DRAFT** at version one with code `…-NOV`, the same conditions and benefits and the new window; its coupons are **not** copied; the audit trail has *promotion.copied* naming the source. The grid selects one offer at a time (the API takes up to 100).
### TC-INCENT-012 — Claims to the principal

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** a principal (Settings > Set up > Item lists > Principals) and a brand under it on `QA-DET`; a promotion the principal funds (principal and **share %** on the promotion editor) that was claimed on an approved bill; an expiry write-off of a DET batch; a sales return of DET completed with damaged goods. A vendor to be the principal's supplier account.
- **Steps:** as the prepared **Firm admin**: Buy > Money > **Principal Claims** → New → pick the principal and the period → Preview. Raise the claim. Raise it again for the same period. Then record the principal's **credit note** (Accounts > Books > Party Adjustments, kind *Principal claim*) against it, and a payment into the bank for the rest. Reverse one receipt. Cancel the claim in a second run and raise it again. Print.
- **Expect:** the preview gathers each source **once**: scheme redemptions (at the principal's share of the benefit), expiry write-offs of its products (at book value) and damaged or scrapped lines of completed sales returns (at the taxable rate credited). Raising posts Dr *Claims Receivable from Principals* and Cr promotional expense (schemes) or inventory adjustment (stock). A second claim over the same sources is refused or empty (one live claim per source). Settlement by credit note and by bank payment moves the status RAISED → PART_SETTLED → SETTLED; reversing a receipt moves it back. Cancelling frees the sources to be claimed again. Reading needs PURCHASE_VIEW, writing PURCHASE_APPROVE. Free quantity on a bill line is not claimed yet.
### TC-INCENT-013 — A commission slab pays a fixed amount or a percentage

*Added 2026-10-13 (backlog 110, customer task S5). Driven over HTTP on a preparation firm; the screen steps were not clicked.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer. ((any firm with one member to be the salesman, a stock item and a customer))
- **Steps:** as the **Firm admin**, Sell > Incentives > **Commission** → **Rates** → **Add rule**: Applies to the salesman, Paid on *Invoiced value*, In force from the first to the last day of **last month**. **Add slab** three times: From `0` To `1000`, Pays **Amount**, Sum `50`; From `1000` To `5000`, Pays **Amount**, Sum `300`; From `5000` To blank, Pays **Percent**, Rate `5`. How the slabs read: the *band reached* choice. Save. Then sell 20 of an item at 100 with 18% GST to a customer, dated the 10th of last month and tagged to the salesman: order, approve; delivery note, approve, dispatch; invoice from the note, approve (2,360.00). Commission → **Collected**, last month → Show. **Payouts** → Accrue last month for the salesman. Repeat in another ended month with the *each band* choice.
- **Expect**
  - Choosing **Amount** turns the slab's Rate box into **Sum**; there is one box, so a slab cannot be typed with both.
  - Band reached: invoiced **2,360.00**, commission **300.00** — the amount of the second slab and nothing of the first. The draft payout earns and owes **300.00**.
  - Each band: the same bill pays **350.00** — 50 for the first slab and 300 for the second.
  - A bill whose total is above 5,000 pays 5% of the whole total on the band-reached rule; on the each-band rule it pays 50 + 300 + 5% of what is above 5,000. (Not driven.)
  - Over HTTP, a slab sent with both `percentage` and `fixed_amount` is refused 422 ("A slab pays a percentage or a fixed amount, not both"), and so is a slab with neither. Reading the rule answers `fixed_amount` on each slab, null on a percentage slab.
  - Editing the first slab back to **Percent** clears its amount.
### TC-INCENT-014 — A commission period is a start date and a number of days

*Added 2026-10-13 (backlog 111, customer task S6). Driven over HTTP on a preparation firm; the screen steps were not clicked.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer. ((any firm with one member to be the salesman, a stock item and a customer))
- **Steps:** as the **Firm admin**, Sell > Incentives > **Commission** → **Rates** → **Add rule**: Applies to the salesman, Paid on *Invoiced value*, Rate `10`, in force for 30 days that have all passed, starting on a day `D`. Bill the customer 2 of an item at 100 with 18% GST (236.00), tagged to the salesman, four times: dated `D+4`, `D+12`, `D+20` and `D+28` (order, approve; delivery note, approve, dispatch; invoice from the note, approve). **Payouts** → **Accrue period**: Starts on `D`, Number of days `10` → Accrue. Accrue period again and read what is offered. Accept it but change the days to `17` → Accrue. Then try Starts on `D+9`, 17 days.
- **Expect**
  - The form has **Starts on** and **Number of days**, and under them "Ends on …": 10 days from `D` end on `D+9`, because the start day is counted. Typing either box moves the end date at once.
  - The first payout runs `D` to `D+9`, measures **236.00** and owes **20.00** (10% of the 200.00 before tax); it is booked on its last day.
  - Opened again, the form offers the day after the last period (`D+10`) and the same number of days (10). After a whole calendar month it offers the next whole month instead, with that month's own number of days.
  - The second payout, 17 days, runs `D+10` to `D+26`, measures **472.00** (two bills) and owes **40.00**: what the *Collected* report says for the same days. Where `D` is past the 14th it crosses a month end.
  - A period starting on `D+9` is refused: "A commission payout already covers part of that period for this salesman (`D` to `D+9`)."
  - A number of days that is blank, 0, above 366 or not a whole number is refused on the form before anything is sent. A period whose last day is today or later is refused by the server, naming the first day it can be accrued.
  - Over HTTP, `period_end` and `period_days` sent together are refused 422 ("Give either period_end or period_days …"), and so is neither. A period said by `period_end` alone still works, as before.
---

## Offers chosen on the bill line

While a sales line is typed, the side panel lists every offer and standing discount that could act on it, with what each gives, why it is or is not applied, a "buy N more" hint and, for an offer that allows it, a part share; the bill maker may tick a different set and the server prices the line again. `docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md` (sections 1, 3 and 6) is the reference; what was built is the L7 row of `docs/CUSTOMER_BUILD_TASKS.md`.

The kept scripts are `docs/qa/checks/offers/` (`setup.py` once, then `python docs/qa/checks/run.py offers`); each makes a fresh scene, so any case runs alone and twice. Results: `docs/qa/OFFERS_ON_THE_LINE_API_CHECK_2026-10-15.md`. The steps are the HTTP calls the screens make (`POST /api/v1/sales-orders/preview` is what the side panel shows); the screens themselves were not clicked.

### TC-OFR-001 — A line's candidates and reasons in the preview

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11; the setting *Combine as each offer allows* (`COMBINE`).
- **Steps:** (1) **(HTTP)** `POST /api/v1/sales-orders/preview` with one line of 9 pieces and no discount typed. Read the line's `candidates` and the order's line. (2) The same with 11 pieces. (3) List the customer's orders.
- **Expect:** (1) TEA-5 applied, worth 45.00, "5% off", its key the offer's `version_group_id`; TEA-11 not applied, "11 + 1 free", combines; CITY (key: the list's id) worth 36.00 and the standing rate (key `CUSTOMER`) worth 18.00, neither applied, each "An offer gives this line its discount."; the coupon offer WELCOME listed, not available, saying no coupon was presented. The line: 45.00 off from a promotion, taxable 855.00, GST 102.60, amount 957.60, nothing free; no choice refused. (2) TEA-5 applied at 55.00 and TEA-11 applied: 55.00 off, 1 free, taxable 1,045.00, GST 125.40, amount 1,170.40. (3) None: a preview saves nothing.
### TC-OFR-002 — The "buy N more" hint

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11, and CITY with a second break: 6% from 10 pieces.
- **Steps:** **(HTTP)** preview a line of (1) 9 pieces, (2) 3 pieces, (3) 9 pieces with a discount of 0% typed.
- **Expect:** (1) TEA-11 `needs_more` 2, `then_gives` "1 free"; CITY `needs_more` 1, "6% off"; TEA-5 (applied) no hint; at most two hints on the line. (2) TEA-5 `needs_more` 2, "5% off", listed but not available; no hint from TEA-11 (8 short, more than the 3 typed) or CITY (7 short). (3) No hint at all, and every candidate says "A discount is typed on this line."
### TC-OFR-003 — A choice on an order line

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11; `COMBINE`; a Sales executive of the firm (holds `SALES_OFFER_CHOOSE`).
- **Steps:** As the Sales executive: (1) **(HTTP)** preview a line of 11 with `offer_choice` `{"discount_from": <CITY's id>, "offers": [<TEA-11's key>]}`. (2) Save the order the same way; read the audit trail for `sales_order.offer_chosen` on it. (3) Save another order whose choice is the start: `{"discount_from": "offers", "offers": [TEA-5, TEA-11]}`; read its audit trail.
- **Expect:** (1) CITY applied and chosen, worth 44.00; TEA-5 neither applied nor chosen. The line: 44.00 off from the price list, 1 free, taxable 1,056.00, GST 126.72, amount 1,182.72. (2) Saved (201). The line's `offers` rows: CITY APPLIED chosen 44.00; TEA-11 APPLIED chosen, 1 free; TEA-5 REFUSED (passed over) at 55.00. The discount box is the server's 44.00. One audit row, by the Sales executive. (3) Saved; stored as the server's: TEA-5 and TEA-11 APPLIED, neither chosen, nothing passed over; no audit row.
### TC-OFR-004 — A choice refused on save, reported in a preview

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11; `COMBINE`.
- **Steps:** **(HTTP)** save an order with (1) a line of 11, 3% typed, and a choice of CITY + TEA-11; (2) a line of 3 choosing TEA-5 (a key chosen at 9, then the quantity lowered); (3) a line of 11 choosing an offer key, and then an arrangement key, that no candidate carries. (4) List the customer's orders. (5) Preview the order of (2) with a second line of 11 choosing CITY + TEA-11.
- **Expect:** (1) 422, "two answers on one line". (2) 422, "Line 1: offer TEA5-... does not apply to this line any more. Choose again." (3) 422 each, "does not apply to this line any more". (4) None saved. (5) The preview answers 200: line 1's `choice_refused` carries the words of (2) and the line is priced from the start (CITY 4% of 300.00 = 12.00); line 2's choice stands: 44.00 off and 1 free.
### TC-OFR-005 — An offer that does not combine

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a scene with SOLO-3 (3% off a line of 5 or more, does **not** combine, priority 5) and TEA-5 (priority 10); `COMBINE`.
- **Steps:** **(HTTP)** (1) preview a line of 9. (2) Save it choosing SOLO-3 and TEA-5. (3) Save it choosing TEA-5 alone.
- **Expect:** (1) SOLO-3, first, applied (27.00), `combines` false; TEA-5 not applied, "Does not combine with SOLO3-..."; the line takes 27.00. An offer that does not combine ends the stack where it applies, so one ranked **before** it still combines with it. (2) 422, "TEA5-... does not combine with SOLO3-...". (3) Saved: 45.00 off by TEA-5, chosen; SOLO-3 REFUSED (passed over) at 27.00.
### TC-OFR-006 — Without SALES_OFFER_CHOOSE

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11; `COMBINE`; a user of a firm role holding the Sales executive's codes less `SALES_OFFER_CHOOSE`, and a Sales executive.
- **Steps:** As the user without the permission, **(HTTP)** (1) preview a line of 11; (2) preview it choosing CITY + TEA-11; (3) save it so; (4) save it sending back the start (TEA-5 + TEA-11). (5) As the Sales executive, save the choice of (3).
- **Expect:** (1) The candidates are listed. (2) `choice_refused` names `SALES_OFFER_CHOOSE`; the line is priced from the start (55.00 off). (3) **403** naming the permission; nothing saved. (4) Saved: the start is not a choice. (5) Saved.
### TC-OFR-007 — One line under the three settings

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11; the Firm admin, to change the setting and put it back.
- **Steps:** **(HTTP)** a line of 11 under each setting: (1) `COMBINE`: preview. (2) `BEST_OFFER`: preview. (3) Save choosing TEA-5 and TEA-11. (4) Save choosing TEA-5. (5) `ASK`: preview. (6) Save choosing TEA-5 and TEA-11. Put the setting back.
- **Expect:** (1) 55.00 off by TEA-5 and 1 free by TEA-11. (2) TEA-11 alone (1 free is worth 100.00 against 55.00) with CITY's 4% beside it: 44.00 off from the price list, 1 free; TEA-5 listed, not applied, with a reason. (3) 422, "the firm gives the best one offer a line". (4) Saved: 55.00 off, nothing free; TEA-11 kept as passed over, 1 free. (5) As under best one only: 44.00 by CITY and 1 free. (6) Saved: 55.00 off and 1 free, both offers applied and chosen.
### TC-OFR-008 — A part share of "11 + 1"

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11; a second scene whose TEA-11 does not allow a part share; `COMBINE`.
- **Steps:** **(HTTP)** (1) preview lines of 6 and of 4 and read TEA-11's `part_share`. (2) Save a line of 5.5 with `offer_choice` `{"part_share": <TEA-11's key>}`. (3) Save the same with 5 pieces; with 0.5 free typed; with TEA-5 as the part share. (4) In the second scene, preview 6 and save 5.5 with its TEA-11 as the part share.
- **Expect:** (1) 6 is 5.5 charged + 0.5 free; 4 is 3.6667 + 0.3333. (2) Saved: 5.5 + 0.5 free, TEA-5 27.50 off, taxable 522.50, GST 62.70, amount 585.20. Rows: TEA-11 APPLIED, chosen, 0.5 free, `part_share` true; TEA-5 APPLIED 27.50, **not chosen** (the server applied it; nobody chose it; **fails, D-SELL-101**). (3) 422 each: "PIECE is counted in whole numbers, so 5.4545 PIECE cannot be entered"; "cannot be billed as a part share" (free typed); the same for a discount offer. (4) No `part_share` on the candidate; the save is refused, "cannot be billed as a part share".
### TC-OFR-009 — A counter bill carries the choice to its order

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11 and 50 pieces in MAIN; `COMBINE`; for (1)-(4) the order and delivery-note stages switched off (put back after).
- **Steps:** **(HTTP)** (1) `POST /api/v1/sales-invoices/preview`: a bare line of 11 choosing CITY + TEA-11. (2) Save the bill. (3) Read the order raised behind it. (4) Read TEA-11's `free_quantity_claimed`; approve the bill; read it again. (5) With the stages on, raise an order of 2, a delivery note, dispatch it, and bill the note with an `offer_choice` on the line.
- **Expect:** (1) The candidates are listed; CITY applied and chosen; nothing refused. (2) Saved: 44.00 off, 1 free; the bill line carries its order line's rows (CITY and TEA-11 chosen, TEA-5 passed over at 55.00). (3) One order, holding the same rows. (4) 0 before approval, 1 after. (5) 422: "what a line takes is chosen where its price is set".
### TC-OFR-010 — A converted quotation hands its choice over

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11; `COMBINE`.
- **Steps:** **(HTTP)** (1) `POST /api/v1/quotations/preview`, a line of 11 choosing CITY + TEA-11. (2) Save the quotation. (3) Send it, accept it, convert it; read the order.
- **Expect:** (1) CITY applied and chosen. (2) 44.00 off and 1 free; rows CITY and TEA-11 chosen, TEA-5 passed over at 55.00. (3) The order line: 44.00 off from the price list, 1 free, the same rows.
### TC-OFR-011 — Saved rows, and an edit that keeps or clears the choice

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11; `COMBINE`.
- **Steps:** **(HTTP)** (1) Save an order of 11 choosing CITY + TEA-11 and read it. (2) `PUT` it with the line sent **without** `offer_choice`. (3) `PUT` it with `"offer_choice": null`.
- **Expect:** (1) Rows: CITY and TEA-11 APPLIED and chosen, TEA-5 REFUSED at 55.00. (2) The choice is kept: the same rows, 44.00 off. (3) The line follows the server again: TEA-5 55.00 and TEA-11 1 free, neither chosen, nothing passed over.
### TC-OFR-012 — The discount reports

*Added 2026-10-15 (L7 step 10). Driven over HTTP 2026-10-15*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the scene with TEA-5 and TEA-11 and 50 pieces in MAIN; `COMBINE`; the order and delivery-note stages off while billing.
- **Steps:** **(HTTP)** (1) Approve two counter bills of 11: one choosing CITY + TEA-11, one with no choice. (2) `GET /api/v1/sales-invoices/reports/discount-by-product` for today; read the item's row. (3) `GET /api/v1/sales-invoices/reports/discount-by-offer-product` for today; read the item's rows.
- **Expect:** (2) 2 lines, gross 2,200.00, arranged 44.00, by offer 55.00; `chosen_lines` 1, `chosen_discount` 44.00, `passed_over` 1, `passed_over_amount` 55.00. (3) TEA-11 on 2 lines, 2 free; TEA-5 on 1 line, 55.00.
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
