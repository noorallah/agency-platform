# Purchasing: order to payment

Part of the QA test suite in `docs/qa/` for **release 1.3.0**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > All Sell screens > Documents > Proforma` is a screen that is not
daily work, and `Settings > Set up > Pricing > Price Lists` is the gear at the
right of the bar. Generated on 2026-10-05 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Buying — order to payment

Four documents: a purchase order, goods receipts against it, a supplier
invoice against a receipt, and a purchase return. **Completing a receipt
posts stock; cancelling a completed one reverses the stock and the journal;
approving an invoice posts the payable; completing a return takes stock back
off.** Everything else is paperwork.

| Preparation | Starts you with |
| --- | --- |
| `buy-ready` | a vendor `QA-V` and a product `QA-B`, 0 on hand |
| `po-approved` | … and an **approved** purchase order for 10 at 100 |
| `po-received` | … and receipts of **4** and **6**, both completed — 10 on hand |
| `po-invoiced` | … and an **approved** supplier invoice for the receipt of 6 (708.00 with GST) |

Purchase orders are Buy > **Purchase Orders**; Goods Receipts and Purchase Invoices
are on the Buy menu and Purchase Returns under Buy > **Returns & notes**;
payments are Buy > **Payments**;
stock is Stock > All Stock screens > Stock > **Inventory** and Stock > **Stock Ledger**. Every
screen reads once when opened: **Refresh** after acting elsewhere.

### TC-BUY-001 — Raising a purchase order, and the approval that cannot be skipped

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Steps**
  1. As the prepared **Firm admin**, Buy > Purchase Orders → **New**: vendor `QA-V`, branch `HO`, warehouse `MAIN`, today; **Add Line**: product `QA-B`, quantity **10**, unit price **100** (the units fill from the product, PIECE) → **Save**. Open it.
  2. Select the draft: look at the toolbar and inside the view.
  3. **Submit**, then **Approve**.
- **Expect**
  - Step 1: status **DRAFT**, number `PO-QA01-HO-2026-2027-…`; the Line Items table names the product as `QA-B — Bought Item qa` and the unit `PIECE`; the Approval banner reads "Submit this draft to send it for approval."
  - Step 2: **Approve is not offered** on a draft — only Submit. **(HTTP)** `POST /api/v1/purchases/{id}/approve` on a draft → **422**, "Only submitted purchase orders can be approved. Submit the order first."
  - Step 3: toasts "… submitted for approval." and "… approved."; status **APPROVED**, the grid updating without the dialog closing.
### TC-BUY-002 — Editing an approved order withdraws the approval

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Steps:** as the prepared **Firm admin**, select the prepared order → **Edit** → dialog **Editing withdraws the approval** → **Edit anyway**. Type a line remark and change the order remarks → **Save**. Then **Submit** and **Approve** again.
- **Expect:** saved as **DRAFT**; the remark survives reopening; the view's **History** shows the approval withdrawn (audit `purchase.approval_withdrawn`). An edit no longer decides the status — the update body cannot write one. After Submit and Approve: APPROVED again.
### TC-BUY-003 — Receiving part of an order, then the rest

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Steps**
  1. As the prepared **Firm admin**, Buy > Goods Receipts → **New** → **Purchase Order** picker (approved orders only) → the prepared order. Set Accepted to **4**, warehouse `MAIN` → **Save Receipt** → select the draft → **Complete**.
  2. Buy > Purchase Orders → the order. Stock > All Stock screens > Stock > Inventory and Stock Ledger, filtered to `QA-B`.
  3. Buy > Goods Receipts → New against the same order → Accepted defaults to **6** → Save, Complete.
- **Expect**
  - Step 1: the line arrives with Accepted 10 and "Ordered 10 · already received 0"; after save, "Goods receipt GRN-… created as a draft. Complete it to post the stock."; after Complete, status **COMPLETED**.
  - Step 2: the order reads **PARTIALLY_RECEIVED**; `QA-B` in MAIN holds **4**; the Stock Ledger shows `GOODS_RECEIPT` +4 referencing the GRN.
  - Step 3: the line says "already received 4"; after Complete the order reads **RECEIVED**, MAIN holds **10**, and a second `GOODS_RECEIPT` entry appears.
### TC-BUY-004 — Cancelling a completed receipt undoes its stock and its journal

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, Buy > Goods Receipts → select the **receipt of 4** → **Cancel**. Then the order, the Inventory row and the Stock Ledger for `QA-B`; Accounts > Journal Entries.
- **Expect:** status **CANCELLED**; the ledger shows `GOODS_RECEIPT_REVERSAL` **−4** against that GRN; MAIN holds **6**; the order drops back to **PARTIALLY_RECEIVED**; the journal shows the reversal, crediting inventory with what the movement removed.
### TC-BUY-005 — A receipt that has been invoiced cannot be cancelled

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**, Buy > Goods Receipts → select the **receipt of 6** (the one the preparation invoiced) → **Cancel**.
- **Expect:** refused — "Goods receipt GRN-… has been invoiced, so cancelling it would leave the accrual and the payable disagreeing. Cancel the purchase invoice first, or raise a purchase return." Nothing changes.
### TC-BUY-006 — Returning damaged goods to the supplier

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, Buy > Returns & notes > Purchase Returns → **New** → **Goods Receipt** picker (completed receipts only) → the **receipt of 6**. On its line set **Returning** **2**, click the **Damaged** chip → **Save Return** → select the draft → **Approve** → **Complete**. Then Inventory, Stock Ledger, Journal Entries, and Reports > Operational → **Damaged goods returned**.
- **Expect:** after save, "Purchase return PR-2026-2027-… created as a draft. Approving and completing it is what takes the stock off."; after Complete, **COMPLETED**. MAIN holds **8**. The Stock Ledger shows the return of 2 referencing the PR (the API reads `transaction_type: RETURN`). The journal shows the return's entry; the damaged-goods report lists the line. Open the return: product and unit read as code and name, not ids.
### TC-BUY-007 — The purchasing reports have rows

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Steps:** as the prepared **Firm admin**, Reports > **Operational**: Purchase order register, Orders not yet received, Overdue purchase orders, Orders by supplier, Orders by buyer, Purchases by product.
- **Expect:** each opens with a row count in the header. The register and "not yet received" include the prepared order; by supplier names `Fixture Supplier qa`; by product names `Bought Item qa`. Overdue and by buyer may be empty in QA01 — an empty report reads "Nothing to report", never a blank grid.
### TC-BUY-008 — Paying the supplier

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**, Buy > Payments → **Record Payment**: **Paid to** `QA-V`; **Amount** the bill's Outstanding (708.00); **Method** Bank; **Oldest first** → **Record payment**. Open Record Payment again for the same vendor.
- **Expect:** toast "PY-… recorded and posted to the ledger." *(The plan said `PAY-`; the series prefix is `PY`.)* The second time, the bill is gone from the list. Journal Entries shows the payment: Dr Accounts Payable / Cr Bank.
---

### TC-BUY-009 — A return the supplier pays back (refund)

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** As *po-received*: a completed receipt of 6 from `QA-V`.
- **Steps:** as the prepared **Firm admin**, Buy > Returns & notes > Purchase Returns → **New** off the **receipt of 6**, return **2**, **Outcome** *Refund* → Save → Approve → Complete. Buy > Payments → **Supplier refunds** → `QA-V` → on the return, **Record refund**: amount **100**, today, Bank → Save. Then **Record refund** again for more than is left. Then **Refunds** → **Reverse** with a reason. Then try **Cancel** on the return while a refund stands (record one again first).
- **Expect:** the credit shows Outcome *Refund*, Refunded 100, Available reduced by 100; Journal Entries has Dr Bank / Cr Accounts Payable. Over-refund is refused naming what is left. After Reverse the credit is whole again and the mirror journal posts. Cancelling the return while a refund stands is refused: "…Reverse the refund first."
### TC-BUY-010 — A return to be replaced reopens the order

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** As *po-received* with the order fully received (receipts of 4 and 6).
- **Steps:** return **2** off the receipt of 6 with **Outcome** *Replacement* → Approve → Complete. Open the purchase order. Then receive 2 more against the order.
- **Expect:** the order reads **Partially received** with 2 pending; the new receipt of 2 is accepted (no over-receipt refusal) and the order reads **Received** again. Change the return's outcome to *Credit* (list → **Change outcome**) before receiving: the order goes back to **Received**.
### TC-BUY-011 — A return off a bill already paid leaves a supplier credit

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Also needs:** As TC-BUY-008 (the bill paid in full).
- **Steps:** Buy > Returns & notes > Purchase Returns → **New** off the **paid bill**, return 2 → Approve → Complete. Buy > Payments → **Supplier credits** → `QA-V`. Raise another bill and **Apply** the credit to it.
- **Expect:** the paid bill does not reappear in Record Payment; the return appears as a supplier credit for its value; applying it lowers the new bill's outstanding by that much. Deleting `QA-V` is refused while the credit stands.
### TC-BUY-012 — Input credit blocked on a purchase (a car, catering)

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** *buy-ready* with the GST template; a product `QA-CAR`.
- **Steps:** Masters > Products → `QA-CAR` → **Input credit** *Blocked (s.17(5))* → Save. Bill it from a receipt at 18% GST and approve. Open Journal Entries for the bill, and Accounts > GST Returns → GSTR-3B for the month. Then on another bill line set **Input credit** *Eligible* explicitly.
- **Expect:** the bill line shows a **Credit blocked** badge. The journal debits **5450 Input Tax Not Claimable** with the whole tax and **no** input CGST/SGST. GSTR-3B shows the tax in 4(A)(5) and again in **4(B)(1)**, net 4(C) without it. The line set to *Eligible* claims as usual. A user without `PRODUCT_TAX_MANAGE` sees the product's Input credit read-only.
### TC-BUY-013 — A composition supplier charges no GST

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** *buy-ready*; a supplier `QA-COMP` with a GSTIN.
- **Steps:** Masters > Vendors → `QA-COMP` → **GST type** *Composition* → Save. Then set *Unregistered* while the GSTIN is still filled → Save. Order, receive and bill from `QA-COMP` (as Composition).
- **Expect:** *Unregistered with a GSTIN* is refused with the server's message and the form stays open with what was typed. The bill editor shows "This supplier charges no GST; the bill will carry no tax."; the approved bill has tax 0 and claims no credit. A supplier with GST type *Not set* is taxed as before.
### TC-BUY-014 — GSTR-2B reconciliation

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** two approved bills in a month from a supplier with a GSTIN; the sample `docs/qa/tools/gstr2b_sample.json`, edited: `rtnprd` to the month as MMYYYY, `ctin` to the supplier's GSTIN, the two bill numbers, dates and amounts to the two bills' (the sample's second bill carries CGST 5 more than the books on purpose), and one invoice not in the books.
- **Steps:** Accounts > All Accounts screens > Tax filing > **GSTR-2B Reconciliation** → month → **Import 2B file**. Then **Match to bill…** on the *Not in books* row, then **Undo match**. Then Settings > Tax > GST Documents → **Claim input credit** *Only bills matched to GSTR-2B* → GSTR-3B for the month.
- **Expect:** rows read **Matched**, **Different** ("CGST … in 2B, … in the books"), **Not in books**; the "In books, not in 2B" section lists any bill 2B lacks. Importing the month again replaces it. Under *matched only*, 3B claims only matched bills and shows the rest as *Held back — not yet in GSTR-2B*.
### TC-BUY-015 — Reorder from what sold (planning formula)

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a product with **no** reorder or minimum level typed, 100 received in one warehouse long ago and 90 delivered to customers within the last 90 days (10 left); a second product with a reorder level typed.
- **Steps:** as the prepared **Firm admin**: Settings > Buying > **Purchase Settings** → **Reorder planning** → Open. Note it says the firm plans on typed levels. Reports > Operational → **Below reorder level**. Then choose **From sales**, leave 90 / 7 / 7 / 30 → Save. Open the report again, and Buy > Purchase Orders → "..." → **Below reorder level...**. Try Cover 0 → Save. Open the dialog as a role without *Manage purchase settings*.
- **Expect:** on typed levels the first product is **not** listed. On sales it is listed with **Basis Sales**, **Avg/day 1**, reorder level 14, maximum 44 and **suggested 34** (44 - 10), whole units; the second product keeps **Basis Level** with its typed figures. The dialog names the basis above the grid, and **Raise draft orders** raises a draft for 34. Cover 0 is refused with the range. Without the permission the dialog is read-only. Settings > Platform > System > Audit Logs shows **purchase.reorder_planning_updated**.
### TC-BUY-016 — One quantity picture per order line, and the billing status

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Also needs:** as *po-invoiced*: an order for 10, receipts of 4 and 6 completed, a bill for the receipt of 6 **approved**.
- **Steps:** as the prepared **Firm admin**, Buy > Purchase Orders → open the order and select its line. Then Purchase Invoices → raise a second bill for the receipt of 4 but leave it in **Draft**; reopen the order. Approve that bill; reopen. Then Purchase Returns → return 2 off the receipt of 6 → Approve → Complete; reopen. Open a **Draft** order beside it.
- **Expect:** after the first bill the header reads *Part billed*, and the side panel's *Received and billed* block says Received 10, Billed 6, Pending 0, **To bill 4**. The draft bill changes nothing (only approved bills count). After approving it: *Billed*, **Complete**, To bill 0. After the return of 2: Returned 2, **To bill 0** still (the return is set against what was kept), and Complete stays. A draft order shows none of the block and no billing chip. Nothing in the editor lets the figures be typed, and saving the order does not send them.
### TC-BUY-017 — A debit note on a bill already paid

*Added 2026-10-02 (decision A4).*

- **Preconditions:** an approved supplier bill of 1,180.00 (1,000 + 18% GST), **paid in full**, and a second approved bill of the same supplier for 500.00.
- **Steps:** Buy > Returns & notes > **Debit Notes** → New against the paid bill: 100 on its line, reason *Price difference* → Save → **Approve**. Pay → New payment for the supplier: look at the supplier credits. Set the debit note's credit against the second bill. Then cancel the debit note. Then raise and approve it again, record a supplier **refund** of 50 against its credit, and try to cancel it.
- **Expect:** approval succeeds (it used to refuse "still owes only 0"). The payment screen lists a credit of **118.00** marked as a debit note; set against the second bill, that bill owes **382.00**. Cancelling the debit note withdraws it -- the second bill owes 500.00 again and the credit is gone. With the refund standing, the cancel is refused ("Reverse that refund…").

### TC-BUY-018 — Reorder orders from the preferred supplier

*Added 2026-10-02 (decision A18).*

- **Preconditions:** two active suppliers, `QA-V1` (who billed the product last, at 100) and `QA-V2` (never billed it); the product below its reorder level; its purchase price 90.
- **Steps:** Masters > Products → open the product → **Preferred supplier** `QA-V2` → Save. Buy > Purchase Orders → "..." → **Below reorder level...**. Then mark `QA-V2` inactive and open the dialog again. Then open the product as a role that cannot see suppliers.
- **Expect:** with `QA-V2` preferred the row names **QA-V2** at **90.00** (the last bill's 100 was QA-V1's, so it does not carry over); **Raise draft orders** raises a draft to QA-V2. With QA-V2 inactive the row falls back to **QA-V1** at 100. Saving the product with QA-V2 inactive and the supplier untouched still works. Choosing an inactive supplier is refused ("Preferred supplier not found, or not active.").
---

### TC-BUY-019 — Supplier rates, catalogue, order multiples and lead times

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** a price list scoped to the vendor `QA-V` with a rate for `QA-B`; one completed receipt of the order of 10 (the preparation has two).
- **Steps:** as the prepared **Firm admin**: Masters > **Vendors** → `QA-V` → **Standing discount %** 5 → Save. Settings > Set up > Pricing > **Price Lists** → New, scope *Supplier* `QA-V`, rate 90 for `-B`. Masters > Vendors → `QA-V` → **Catalogue** tab → add `-B`: supplier code `SK-1`, price 80, minimum order 20, **order multiple 10**, pack size, lead time 7 days; also import a catalogue file (Import → *supplier catalogue*). Settings > Buying > **Purchase Settings** → order quantity policy **Warn**, then **Refuse**. Buy > **Purchase Orders** → New for `QA-V`: add `-B` with the price and discount boxes blank, quantity 25; use the hint's **Use N**; save. Look at the expected date, then the vendor's lead-time summary. Reports > Operational → Below reorder level (From sales).
- **Expect:** a blank price and discount are filled from the supplier's terms: the catalogue price ranks between the supplier price list and the product's purchase price, and the supplier code is filled; the standing discount fills a blank discount. Quantity 25 against minimum 20 and multiple 10 shows a hint "use 30"; under Warn the order saves, under Refuse it is refused naming the multiple. The expected date is the order date plus the catalogue lead time. The vendor shows quoted lead time and what the deliveries actually took (average days, late receipts, on-time share), derived from completed receipts; a cancelled receipt stops counting. The reorder planner rounds its suggestion to the multiple and uses the lead time for the sales-based reorder point. Sales price lists ignore supplier-scoped lists. An explicit price or discount of 0 typed on the line is kept.
### TC-BUY-020 — A requisition becomes orders, and an approved order is amended

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Also needs:** a second vendor and a second product with a preferred supplier; a role holding PURCHASE_REQUISITION_CREATE but not PURCHASE_APPROVE.
- **Steps:** as the **Purchasing** user: Buy > All Buy screens > Documents > **Requisitions** → New with two lines (one naming a supplier, one with only a product that has a preferred supplier, then one with neither) → Save → Submit. Try Approve. As the **Firm admin**: Approve → **Convert to orders**. Separately Reports > Operational > Below reorder level → **Raise requisition**. Then open the approved purchase order → **Amend**: change a quantity → Save; open **Revisions**; print.
- **Expect:** a requisition is numbered in its own **PR** series; a line with neither a supplier nor a preferred supplier is refused by name; only an approver sees Approve. Converting raises **one draft purchase order per supplier** priced from the supplier's terms; the requisition becomes ORDERED and is history. Raise requisition from the reorder screen makes a requisition rather than orders. Amend on the approved order keeps it approved, bumps the **revision number**, and keeps the earlier version listed under Revisions; the print titles it as an amendment.
### TC-BUY-021 — Goods held for inspection on receipt

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Also needs:** a user holding PURCHASE_INSPECT.
- **Steps:** as the prepared **Firm admin**: Masters > Products → `QA-B` → switch on **Inspect on receipt** → Save (or the same on its category). Buy > Goods Receipts → receive 10 and complete. Open Stock > All Stock screens > Stock > **Inventory**. Then Buy > All Buy screens > Documents > **Quality Inspection**: pass 6, reject 4 (once written off, once left in quarantine for a return). Cancel a second receipt that is still on hold.
- **Expect:** completing the receipt puts the goods in **quarantine** — owned and valued as received but not sellable or issuable. The Quality Inspection screen lists the held lines; passing releases that quantity to stock; rejecting either writes it off at once or leaves it in quarantine for a purchase return (condition Quarantine). Cancelling a receipt whose lines are still held releases the holds with it. Without PURCHASE_INSPECT the decision is refused.
### TC-BUY-022 — A supplier bill outside tolerance, and an order over budget

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** a user with the approval right on purchases and a firm administrator; PURCHASE_APPROVE_OVER_TOLERANCE and PURCHASE_APPROVE_OVER_BUDGET held by the administrator only.
- **Steps:** as the **Firm admin**: Settings > Buying > **Purchase Settings** → **Bill matching**: price tolerance 2% and amount tolerance 50 → Save. Buy > Purchase Invoices → New for the receipt of 6 with the rate 10% above the order → Save → Approve as the **Purchasing manager**, then as the administrator. Next Settings > Buying > **Purchase Budgets** → New for this month, category of `-B`, amount 500; set the policy on Purchase Settings to **Warn**, then **Block**. Raise and approve a purchase order of 10 × 100 as the manager, then as the administrator; open the order's budget panel.
- **Expect:** the bill is **held** at approval and refused naming the breach (price over tolerance) for a user without the over-tolerance right — single and bulk approve alike; the administrator may approve it. The budget is a month, optionally one branch and one category; what it has used is the value before tax of approved orders in that month, derived on every read. Under Warn the approval proceeds with a warning; under Block it is refused for a user without PURCHASE_APPROVE_OVER_BUDGET. The order's budget panel shows budget, used and what the order adds.
### TC-BUY-023 — A payment run and its bank file

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Also needs:** a second approved supplier bill for another vendor with a bank account saved; a cashier user (CASHIER cannot approve a run).
- **Steps:** as the prepared **Firm admin**: Buy > All Buy screens > Money > **Payment Runs** → New → *Propose* bills falling due by today plus 30 days. Untick one bill; lower another amount; try an amount above what the bill owes. Save the draft. As the **cashier** try Approve. As the administrator: Approve. Download the **bank file**. Cancel a second draft run.
- **Expect:** the proposal lists every supplier bill still owing that falls due by the date. A draft holds the chosen bills and amounts, never more than a bill still owes. Approving needs PAYMENT_RUN_APPROVE (the cashier is refused), records **one payment per supplier** by bank transfer allocated to that supplier's bills, all in one commit: a run that cannot pay every supplier pays none. The bank file is a generic NEFT CSV with one row per supplier from its primary bank account (no bank-specific layout yet). A cancelled draft pays nothing.
### TC-BUY-024 — Supplier performance, price trend and ratings

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** the receipts made on different days from the order's expected date (one late); two users with PURCHASE_VIEW or VENDOR_VIEW.
- **Steps:** as the prepared **Firm admin**: Reports > Operational → **Supplier performance**, then **Supplier price trend**. Masters > Vendors → `QA-V` → **Ratings** → rate each criterion 1-5 → Save; change it and save again; try 0 and 6. Sign in as a second user and rate; open the tab again; **Delete** your own rating.
- **Expect:** the performance report has a row per supplier with receipts, **On time %**, **Rejected %**, **Returned %** and **Short %**; the trend shows month, quantity and **Average rate**. A rating criterion outside 1-5 is refused. The tab shows the averages per criterion, the overall figure, every rating and the reader's own; one live rating per person per supplier — the earlier ones stay as history and the audit row keeps the earlier scores. Deleting removes only your own.
### TC-BUY-025 — Supplier volume rebates

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**: Buy > All Buy screens > Money > **Supplier Rebates** → New for `QA-V`: a period covering the bill of 708.00 (600 before tax) and two slabs (for example from 0 at 1%, from 500 at 2%). Save. Open it and read the volume, the slab reached and the amount. **Accrue**. Accrue again. **Reverse accrual**. Accrue once more, then Accounts > All Accounts screens > Books > **Party Adjustments** → New of kind *Supplier rebate* naming the agreement. Cancel a second agreement.
- **Expect:** the volume is derived on every read: the supplier's approved bills dated in the period at taxable value, less its completed purchase returns in the period; the **highest slab reached** sets the rate on the **whole** volume (600 at 2% = 12.00). Accrual snapshots the volume, rate and amount with the journal that booked them (Dr *Supplier Rebate Receivable*), and a second accrual of the same period is refused; nothing re-reads the bills afterwards. Reversing the accrual takes the journal off. The rebate is settled by an approved **party adjustment of kind Supplier rebate** that names the agreement (not a debit note, which has to name one bill); what has been settled is the sum of those. The control account exists for new and existing firms.
### TC-BUY-026 — Landed cost spread over received goods

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** a freight bill from a transporter (a second vendor) of 1,000; part of the goods already sold so that on hand is less than received (deliver 4 of the 10).
- **Steps:** as the prepared **Firm admin**: Buy > All Buy screens > Money > **Landed Costs** → New: pick the two completed receipts, add a charge (freight, the transporter as billing party, its bill number, 1,000), apportion **by value**. Preview and post. Open the voucher and read each product's split. Then try **by quantity**, **by weight**, and cancel a voucher. Check Accounts > Balance Sheet and the stock valuation.
- **Expect:** the charge's own bill is booked to *Expenses Included in Valuation*; the voucher spreads the total over the receipts' lines by taxable value (or quantity, or weight; the rounding residual goes to the largest line) and splits each share by the product's quantity still on hand: that part **revalues the stock** through a zero-quantity *Landed cost* movement (new average cost), and the rest goes to **cost of goods sold**. Journal: Dr Inventory, Dr Cost of Goods Sold, Cr Expenses Included in Valuation. Cancelling reverses the journal and takes the on-hand value back off at today's quantity. Reading needs PURCHASE_VIEW, posting PURCHASE_APPROVE.
### TC-BUY-027 — Supplier credit set against an opening bill

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** an opening supplier bill for `QA-V` (Accounts > All Accounts screens > Books > Opening Balances) of 500, and a supplier credit of 200 (a purchase return refunded as credit, as in TC-BUY-011).
- **Steps:** as the prepared **Firm admin**: apply the supplier credit — the apply dialog lists bills and opening bills (marked "(opening)") — to the opening bill for 200. Open Buy > **Payments** → Record Payment for the supplier. Open the opening bill list. Try to delete the supplier. Then cancel the opening bill.
- **Expect:** the credit is accepted against the opening bill (it used to refuse it). Record Payment shows the opening bill owing **300**; the opening bill list shows the credit counted; the supplier cannot be deleted while it holds an application. Cancelling the opening bill withdraws the credit set against it and the 200 is available again.
### TC-BUY-028 — Free goods to customers, and gifts from a supplier

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Also needs:** a customer; a user holding SUPPLIER_GIFT_MANAGE; the firm's TDS 194R rules are described in the compliance notes.
- **Steps:** as the prepared **Firm admin**: Masters > Products → `QA-B` → switch **Free issue only** on; try to put it on a quotation or an invoice line with a price. Receive 5 units on a goods receipt with a **Scheme** name on the line. Stock > All Stock screens > Stock > Inventory → Write off 2 with reason *Free to customer* and the customer, and 1 with reason *Sample*. Reports > Operational → **Free goods**. Then Buy > All Buy screens > Money > **Supplier Gifts** → record a gift from the supplier (a fridge, value 20,000, to the firm, then one taken for personal use). Open the **194R summary**. Cancel one.
- **Expect:** a free-issue-only product is refused on a priced sales line by name. The receipt line keeps the scheme; the write-offs post to *Promotional Expense* (not Inventory Adjustment) and carry the customer; the Free goods report shows what came in free, what went out free and what is left. A supplier gift posts Dr the asset or expense account named (or *Drawings* when the owner kept it) and Cr *Supplier Incentives Received*, with no input tax; the gift register links to the receipt line marked "gift, not stock"; the 194R summary totals gifts per supplier; cancelling reverses the journal. Managing gifts needs SUPPLIER_GIFT_MANAGE.
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

**Two groups change a firm-wide setting.** The import cases (TC-BUY-070 to
076) and the capital-goods case TC-BUY-077 need a firm that types
only the bill: Settings > Buying > Purchase Settings > **Buying stages** with
**Purchase order** off, which takes **Goods receipt** off with it. Run them
when nobody else is buying in the firm, or in a firm of its own, and switch
both back on afterwards.

### GST purchase register and HSN summary of purchases (backlog 86 #17)

### TC-BUY-029 — The GST purchase register lists an approved bill by tax head

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**, Reports > **Financial** → **GST purchase register**, the period covering today. Find the prepared bill by its number. Then Buy > Purchase Invoices → New for the receipt of 4, save it and leave it a **draft**; open the report again.
- **Expect:** one row for the approved bill: Type **Bill**, the supplier's name and GSTIN (blank where the supplier has none), Taxable **600.00**, CGST **54.00**, SGST **54.00**, IGST 0.00, Total tax **108.00**, Not claimable 0.00, Reverse charge 0.00, Capital goods tax 0.00, Bill total **708.00**. The draft bill is not listed; neither is a cancelled one. Only approved and closed bills count.
### TC-BUY-030 — The HSN summary folds the same bills by HSN code and unit

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Also needs:** a second product with **no** HSN code, bought and billed from the same supplier (order 1 at 100, receive, bill, approve).
- **Steps:** as the prepared **Firm admin**, Reports > Financial → **HSN summary of purchases**, the period covering today.
- **Expect:** a row for the HSN of `QA-B` with its unit, Quantity **6**, Taxable **600.00**, CGST 54.00, SGST 54.00, Total tax 108.00 and Bills **1** (more where other bills in the period carry the same HSN). The product with no HSN shows under a **blank** HSN, so the gap is visible, not folded into another row.
### TC-BUY-031 — Tax that may not be claimed shows in Not claimable

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, Buy > Purchase Invoices → New for the receipt of 6; on its line set **Input credit** to *Blocked (s.17(5))* → save → **Approve**. Reports > Financial → **GST purchase register**.
- **Expect:** the bill's row carries CGST 54.00 and SGST 54.00 as charged, Total tax 108.00 and **Not claimable 108.00**. The heads are what the supplier charged; the last column says how much of it the firm may not claim.
### TC-BUY-032 — A debit note and a purchase return are minus rows on their own dates

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**, Buy > Returns & notes > **Debit Notes** → New against the prepared bill: 100 on its line → Save → **Approve**. Buy > Returns & notes > Purchase Returns → New off the **receipt of 6**: Returning **2** → Save → Approve → Complete. Reports > Financial → **GST purchase register**, then **HSN summary of purchases**.
- **Expect:** besides the bill's row, a row of Type **Debit note** with the bill's number under **Against bill**, Taxable **-100.00**, CGST **-9.00**, SGST **-9.00**; and a row of Type **Purchase return**, Taxable **-200.00**, CGST **-18.00**, SGST **-18.00**. Each is dated the day it was raised, not the bill's day. The HSN summary's row for the product is lower by the same amounts. A return of goods that were never billed is not listed.
### Payables by supplier and month (backlog 85; backlog 86 #20)

### TC-BUY-033 — What each supplier is owed, by month, agrees with the books

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**, Buy > All Buy screens > Money > **Payables by Month**. Read the row for `QA-V`, the Total row and the line under the grid. Switch **By invoice date** to **By due date**. Narrow to the supplier with the **All suppliers** box.
- **Expect:** the page opens on **Owed**, as of today. The supplier's row shows **708.00** in this month's column and **708.00** under **Outstanding** (more if the supplier has other open bills). The columns are Supplier, **Older**, one per month, **Later**, **Credits**, **Outstanding**. The Total row sums every supplier, and the line under it reads "Agrees with the books: control account 2100 holds …" with the same figure. If it reads "Does not agree with the books: control account 2100 holds …", that is a failure to report with both figures. By due date the 708.00 moves to the month the bill falls due.
### TC-BUY-034 — A part payment, the Paid view, and the branch filter

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**, Buy > Payments → **Record Payment**: `QA-V`, amount **200.00**, Bank, against the bill → Record payment. Buy > All Buy screens > Money > **Payables by Month**. Switch **Owed** to **Paid**. Back on Owed, pick a branch in **All branches**. **(HTTP)** `GET /api/v1/purchase-invoices/reports/payables?as_of=<today>&view=paid&branch_id=<a branch id>`.
- **Expect:** Owed shows **508.00** for the supplier and still agrees with 2100. Paid shows **200.00** in this month's column, with the column headed **Paid**. With a branch chosen the line under the grid reads "Narrowed to a branch: advances and refunds name no branch, so there is no books check." The HTTP call is refused: "A payment names no branch, so the Paid view cannot be narrowed to one. Clear the branch filter."
### TC-BUY-035 — Supplier credit sits in Credits, not in a month

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, Buy > Returns & notes > Purchase Returns → New off the **receipt of 4** (which no bill names): Returning **1** → Save → Approve → Complete. Buy > Purchase Invoices → bill the **receipt of 6** and approve (708.00). Buy > All Buy screens > Money > **Payables by Month**.
- **Expect:** the supplier's row shows 708.00 in this month and the return's value as a minus figure under **Credits**, so **Outstanding** is the bill less the credit. The total still agrees with control account 2100: the page counts every document that posts to it, not bills alone.
### Cash purchase in one step (backlog 86 #19)

### TC-BUY-036 — Approve a bill and pay it in the same step

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, Buy > Purchase Invoices → New for the receipt of 6 → save. Select the draft → **Approve**. In the dialog **Approve PI-…** tick **Paid now**; leave **Method** *Cash*, **Amount** blank ("Blank pays the full bill.") and **Date paid** blank → **Approve and pay**. Then Buy > Payments, Record Payment for the supplier, and Accounts > Journal Entries.
- **Expect:** the dialog reads "Approving posts the bill to the books." and the button changes from **Approve** to **Approve and pay** when Paid now is ticked. Afterwards the bill is **APPROVED** and a payment `PY-…` of **708.00** dated the bill's date is in Payments, allocated to this bill; Record Payment no longer lists the bill. Two journals: the bill's, Dr 2300 Goods Received Not Invoiced 600.00, Dr 1320 Input CGST 54.00, Dr 1330 Input SGST 54.00 / Cr 2100 Trade Payables 708.00; and the payment's, Dr 2100 Trade Payables 708.00 / Cr 1000 Cash 708.00.
### TC-BUY-037 — Paying part now leaves the rest owing; more than the bill is refused

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, bill the receipt of 6 and save the draft. **Approve** → tick **Paid now**, **Method** *Bank*, **Amount** `800` → **Approve and pay**. Then change Amount to `300`, **Reference** `NEFT-QA-0300` → **Approve and pay**.
- **Expect:** 800 is refused inside the dialog, which stays open with what was typed: "Bill PI-… owes 708.00, so 800 cannot be paid against it now. Record an advance through Payments." (the figures may print with more decimals). The bill is **still a draft**: the refusal took the approval back with it. With 300 the bill is approved, a bank payment of 300.00 is recorded, and Record Payment shows the bill owing **408.00**. Payment journal: Dr 2100 Trade Payables 300.00 / Cr 1010 Bank 300.00.
### TC-BUY-038 — Reversing the payment leaves the bill approved and owing

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, bill the receipt of 6, **Approve** with **Paid now** ticked and everything else as offered → **Approve and pay**. Buy > Payments → select the payment → **Reverse** with a reason. Open the bill and Record Payment for the supplier.
- **Expect:** the payment made with the approval is an ordinary payment: it reverses like any other. Afterwards the bill is still **APPROVED** and owes **708.00** again; the payment's mirror journal is posted (Dr 1000 Cash 708.00 / Cr 2100 Trade Payables 708.00).
### TC-BUY-039 — Paid now needs the right to record payments

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** a user hired with the *Purchase Manager* job template, who may approve bills (PURCHASE_APPROVE) but not record payments (no PAYMENT_CREATE).
- **Steps:** as the **Purchase Manager**, bill the receipt of 6, save, **Approve**. Look at the dialog. **Approve**. **(HTTP)** on a second draft bill, as the same user: `POST /api/v1/purchase-invoices/{id}/approve` with body `{"payment": {"method": "CASH"}}`.
- **Expect:** the dialog offers **no Paid now** tick and its button reads **Approve**; the bill approves and owes 708.00. The HTTP call is refused with **403**: "Paying a bill as it is approved records a payment, which needs PAYMENT_CREATE. Approve it without the payment, or ask somebody who may record payments." The second bill stays a draft.
### Attach the supplier's bill (backlog 86 #16)

### TC-BUY-040 — Attach, open, save and delete a file on a purchase bill

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Also needs:** a PDF and a JPG or PNG photo on this PC, each under 10 MB.
- **Steps:** as the prepared **Firm admin**, Buy > Purchase Invoices → open the prepared approved bill → **Attachments**. Type a **Caption (optional)**, **Add file** → the PDF. Add the photo the same way. Use **Open** and **Save as** on one. Close, **Refresh** the list. Open Attachments again → **Delete** on the photo → **Delete**. Settings > Platform > System > Audit Logs.
- **Expect:** the dialog is titled **Attachments · …** and starts with "Nothing is attached yet." Files can be added to an **approved** bill: a paid bill still needs its paper. Each file lists with its name and caption; Open shows it, Save as writes the same file. The list's **Files** column shows a paper clip and **2**, then **1** after the delete. The delete asks "Delete …?" and says the trail keeps the removal; the audit log has `document_file.attached` twice and `document_file.removed` once.
### TC-BUY-041 — The wrong kind of file, and a file that is too large, are refused

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Also needs:** a `.txt` or `.xlsx` file; a text file renamed to end `.pdf`; a PDF or image larger than 10 MB.
- **Steps:** as the prepared **Firm admin**, open the bill's **Attachments** and **Add file** with each of the three in turn.
- **Expect:** each is refused and nothing is listed. The wrong extension: "Only PDF, JPG and PNG files may be attached; '…' is not one by its name." The renamed file: "'…' is not a PDF, JPG or PNG file by its contents." The large one: "The file is … MB; the most a file may be is 10 MB." The dialog stays open.
### TC-BUY-042 — Attachments on a goods receipt, and who may add them

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** a user hired with the *Read Only* job template; a photo under 10 MB.
- **Steps:** as the prepared **Firm admin**, Buy > Goods Receipts → open a completed receipt → **Attachments** → **Add file** → the photo. Start a **new** receipt and press Attachments before saving it. Then sign in as the **Read Only** user and open the first receipt's Attachments.
- **Expect:** the completed receipt takes the file and its row shows the clip and **1** under **Files**. On a receipt not yet saved the dialog says "Save first to attach files". The Read Only user sees the file and can **Open** and **Save as**, but is offered neither **Add file** nor **Delete**: adding and removing follow the right to receive goods (on a bill, the right to create or edit bills).
### TDS 194C and 194J worked out (backlog 86 #10)

### TC-BUY-043 — One contractor bill past 30,000 proposes 194C and posts it

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a supplier of its own with **no other bill or payment this financial year** (April to March): a PAN whose fourth letter is not P or H (a company or firm), **Usual TDS section** *194C*, **Individual / HUF** left unset. Use a new supplier each time the case is run.
- **Steps:** as the prepared **Firm admin**, order **400** of `QA-B` at **100** from that supplier, approve, receive and complete, bill the receipt and save. Select the draft → **Approve**. Read the dialog and leave **TDS to deduct** blank → **Approve**. Open Record Payment for the supplier, and the bill's journal.
- **Expect:** the bill is 40,000.00 + 7,200.00 GST = **47,200.00**. The dialog names the section and rate -- TDS 194C at 2%, basis OTHER -- then "Threshold crossed.", "Due so far: ₹800.00, already deducted: ₹0.00." and "Proposed on this bill: ₹800.00."; the box's helper reads "Blank takes the proposal (₹800.00); 0 deducts nothing." TDS is worked on the value **before GST**. After approval the supplier is owed **46,400.00**. Journal: Dr 2300 Goods Received Not Invoiced 40,000.00, Dr 1320 Input CGST 3,600.00, Dr 1330 Input SGST 3,600.00 / Cr 2100 Trade Payables 46,400.00, Cr 2700 TDS Payable 800.00.
### TC-BUY-044 — The year's limit crossed mid-year carries the earlier bills' tax

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a supplier of its own as in TC-BUY-043 (194C, a company PAN, nothing else this financial year).
- **Steps:** as the prepared **Firm admin**, from that supplier raise, receive, bill and approve three bills in turn, all dated in this financial year, reading the Approve dialog each time and leaving **TDS to deduct** blank: **200** at 100 (20,000 before GST), then **400** at 100 (40,000), then **500** at 100 (50,000).
- **Expect:** bill 1 (20,000): "Threshold not yet crossed." and "Nothing is proposed on this bill." -- it is under 30,000 and the year is under 1,00,000. Bill 2 (40,000): one bill past 30,000, so **800.00** is proposed (2% of 40,000). Bill 3 (50,000): the year is now 1,10,000, past 1,00,000, so the tax is due on the **whole year**: 2% of 1,10,000 = 2,200.00, less the 800.00 already deducted, so **1,400.00** is proposed -- 400.00 more than 2% of this bill, which is bill 1's tax catching up. After the three, 2700 TDS Payable has been credited 2,200.00 for this supplier.
### TC-BUY-045 — No PAN is 20%, and an individual is 1%

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** two suppliers of their own with nothing else this financial year, both **Usual TDS section** *194C*: one with **no PAN**, one with a PAN and **Individual / HUF** set to *Yes*.
- **Steps:** as the prepared **Firm admin**, from each supplier order **400** of `QA-B` at 100, receive, bill, and open **Approve**.
- **Expect:** the supplier with no PAN: 194C at 20%, basis NO_PAN, and **8,000.00** proposed on the 40,000. The individual: 194C at 1%, basis INDIVIDUAL_HUF, and **400.00** proposed. Where Individual / HUF is left unset, a PAN whose fourth letter is P or H is read as an individual or HUF.
### TC-BUY-046 — 194J applies once the year passes 30,000

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a supplier of its own with a PAN and nothing else this financial year, **Usual TDS section** *194J*, **Technical services (2%)** not ticked. A second such supplier with **Technical services (2%)** ticked.
- **Steps:** as the prepared **Firm admin**, from the first supplier raise, receive, bill and approve **250** of `QA-B` at 100 (25,000), then **100** at 100 (10,000), reading the Approve dialog each time. From the second supplier one bill of **400** at 100.
- **Expect:** the first bill proposes nothing: 194J has no single-bill limit and the year is under 30,000. The second takes the year to 35,000: 194J at 10%, basis PROFESSIONAL, and **3,500.00** proposed -- on the whole 35,000, not the 5,000 over the limit. That bill is 11,800.00 with GST and owes the supplier **8,300.00**. The technical-services supplier's bill of 40,000 proposes **800.00** at 2%, basis TECHNICAL.
### TC-BUY-047 — Deducted once: money paid ahead of the bill, then the bill

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a supplier of its own as in TC-BUY-043 (194C, a company PAN, nothing else this financial year).
- **Steps:** as the prepared **Firm admin**, Buy > Payments → **Record Payment**: that supplier, **Amount** `50000`, Bank, no bill to apply it to; **TDS deducted** `1000`, **TDS section** *194C* → Record payment. Then order **500** of `QA-B` at 100 from the supplier, receive, bill, and open **Approve**. Approve.
- **Expect:** the advance posts Dr 2100 Trade Payables 50,000.00 / Cr 1010 Bank 49,000.00, Cr 2700 TDS Payable 1,000.00. The bill of 50,000 (59,000.00 with GST) then shows "Nothing is proposed on this bill.", because the tax on this money was deducted when it was paid; it approves with no TDS and owes the full 59,000.00, against which the advance can be set. The **TDS deducted** box on a payment is never filled for you: a hint such as "194C proposes ₹…" shows in it only when the supplier's bills already leave tax due.
### TC-BUY-048 — Overriding the proposal, and its limits

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** a supplier of its own as in TC-BUY-043 with three bills of 40,000 before GST ready to approve (for each: order 400 at 100, receive, bill, save).
- **Steps:** as the prepared **Firm admin**: (1) on the 194C supplier's draft bill, **Approve** → type `0` in **TDS to deduct** → Approve. (2) On a second such bill type `500` → Approve. (3) On a third type an amount equal to the bill's total. (4) On the prepared own supplier, who has **no** TDS section, bill the receipt of 6 and **(HTTP)** `POST /api/v1/purchase-invoices/{id}/approve` with body `{"tds_amount": 50}`. Then Settings > Platform > System > Audit Logs.
- **Expect:** (1) nothing is deducted; the bill owes its full total. (2) 500.00 is deducted in place of the proposal -- which by now is 1,600.00, the first bill's tax with this one's, since nothing was deducted there -- and the bill owes 46,700.00. (3) refused: "TDS deducted must be less than what the bill owes." (4) refused: "TDS on a bill is worked out under 194C or 194J. Set the supplier's TDS section first, or deduct on the payment." -- and for a supplier with no section the Approve dialog shows no TDS lines at all. The audit row `purchase_invoice.approved` of an overridden bill keeps the proposed amount, the amount deducted and that it was overridden.
### TC-BUY-049 — The 194C and 194J settings

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Steps:** as the prepared **Firm admin**, Settings > Tax > **TDS on purchases (194Q, 194C, 194J)**. Read the 194C and 194J cards beneath the 194Q settings. On 194C change **Threshold per supplier, per year** to `150000` → **Save 194C**; press Save 194C again without changing anything. Type `35` in **Rate %** → Save 194C. Switch **Deduct 194J** off → **Save 194J**, then approve a bill from a 194J supplier past 30,000 in the year. Put everything back.
- **Expect:** a firm that never saved them reads 194C: threshold per payment 30,000, per year 1,00,000, rate 2, without a PAN 20; 194J: per year 30,000, rate 10, without a PAN 20, and **no** per-payment box. The first save toasts "194C settings saved."; the second says "Nothing has changed." A rate of 35 is refused: "A rate is more than 0 and at most 30 percent." With 194J switched off the bill proposes nothing. Saving needs ACCOUNT_MANAGE; a user without it sees the cards read-only.
### TCS charged by a supplier (backlog 86 #9)

### TC-BUY-050 — A rate alone is worked on the bill total, and posts to TCS Receivable

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, Buy > Purchase Invoices → New for the receipt of 6. Type `0.1` in **TCS charged by supplier %**, leave **TCS amount** blank → save. Read the totals. **Approve**. Open Record Payment for the supplier and the bill's journal.
- **Expect:** the bill's own total stays **708.00** and its GST 108.00: TCS is outside GST's taxable value and moves no line. The totals show **TCS charged 0.71** (0.1% of 708.00, the bill **with** GST) and **Net payable 708.71**. After approval the supplier is owed **708.71**. Journal: Dr 2300 Goods Received Not Invoiced 600.00, Dr 1320 Input CGST 54.00, Dr 1330 Input SGST 54.00, Dr 1430 TCS Receivable 0.71 / Cr 2100 Trade Payables 708.71.
### TC-BUY-051 — A typed TCS amount wins over the rate

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, bill the receipt of 6 with **TCS charged by supplier %** `0.1` and **TCS amount** `1.00` → save. Reopen the draft, clear both boxes → save. Type the rate again and leave the amount blank → save.
- **Expect:** with both typed, TCS is **1.00** and Net payable 709.00: the amount the supplier printed wins over the rate. With both cleared there is no TCS line and Net payable is 708.00. With the rate alone it is 0.71 again.
### TC-BUY-052 — Paying the bill clears its TCS, and cancelling reverses it

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, bill the receipt of 6 with **TCS amount** `1.00`, save, **Approve** with **Paid now** ticked and Amount blank → **Approve and pay**. Then bill the receipt of 4 with TCS amount `1.00`, approve without paying, and **Cancel** that bill.
- **Expect:** Paid now pays **709.00**, the bill with its TCS, and the bill owes nothing. The cancelled bill's journal is mirrored, so its 1.00 comes back off 1430 TCS Receivable together with the payable.
### TC-BUY-053 — The TCS paid to suppliers report closes each quarter

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, bill the receipt of 6 with **TCS charged by supplier %** `0.1`, approve. Reports > Financial → **TCS paid to suppliers**, the period covering today.
- **Expect:** a row for the bill: the quarter (October 2026 reads **Q3 2026-27**; April to June is Q1), Supplier, PAN, Bill, Supplier bill, Date, **Base 708.00**, **Rate % 0.1**, **TCS 0.71**. Under the quarter's bills a row named **Total Q3 2026-27** sums the base and the TCS. A draft or cancelled bill, and a bill with no TCS, is not listed.
### Send the purchase order by WhatsApp (backlog 86 #3)

### TC-BUY-054 — The Send dialog offers WhatsApp, and refuses until the firm is set up

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Also needs:** a firm whose messaging has never been switched on (the state a new firm is in).
- **Steps:** as the prepared **Firm admin**, Buy > Purchase Orders → select the approved order → **Send**. Open **Channel**. Choose **WhatsApp** → **Send**. Then Settings > Firm > **Messaging**: switch messaging and the WhatsApp channel on with the firm's account, but name **no** template for *Purchase order sent to the supplier*. Send again.
- **Expect:** the dialog is titled **Send PO-…**. Channel offers **Email** and **WhatsApp** and **not SMS** (SMS is for the sales invoice alone); **Send to** says "Blank sends to the supplier's own address or WhatsApp number". With messaging off: "Messaging is off for this firm. Switch it on under Settings > Messaging first." With it on and no template named: "Name the WhatsApp template for 'Purchase order sent to the supplier' under Settings > Messaging first; WhatsApp sends only registered templates." Each refusal stays in the dialog.
### TC-BUY-055 — A purchase order goes to the supplier's mobile and is marked sent

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Also needs:** messaging and the WhatsApp channel switched on with the firm's own WhatsApp Business account (`docs/MESSAGING_SETUP_GUIDE.md`), and a registered template named for *Purchase order sent to the supplier*; the supplier `QA-V` with a mobile number; a second supplier with **no** mobile, no phone and no contact number, with an approved order. Mark the case Blocked if the firm has no WhatsApp account.
- **Steps:** as the prepared **Firm admin**, select the prepared approved order → **Send** → **Channel** *WhatsApp*, **Send to** blank → **Send**. Open the order's **History**. Then Send the second supplier's order the same way; then again with a number typed in **Send to**.
- **Expect:** "Queued to send." The message goes to the supplier's own mobile (else its phone, else its primary contact's number). The order's history gains "Sent to the supplier by whatsapp." WhatsApp carries the registered template only; the order's PDF is not attached, as with the sales invoice. The supplier with no number is refused: "Cannot send: the supplier has no mobile number. Enter a number." With a number typed the message is queued to that number.
### Requests for quotation and quote comparison (backlog 86 #1)

### TC-BUY-056 — An RFQ to two suppliers, their quotes, and the comparison

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a second active supplier.
- **Steps:** as the prepared **Firm admin**, Buy > All Buy screens > Documents > **Requests for quotation** → New (**New request for quotation**): **Add a supplier** twice (`QA-V` and the second), **Add line**: `QA-B`, **Quantity** `10` → **Save**. Select it → **Send**. **Enter quotes**: for `QA-V` **Rate** `100`, **Discount %** `5`, **Lead time (days)** `7` → **Save quote**; for the second supplier Rate `96`, Discount % blank, Lead time `3` → Save quote. **Compare**.
- **Expect:** the RFQ takes a number from its own `RFQ` series and reads **Draft**, then **Sent**. The comparison (**Compare quotes for RFQ-…**) shows both suppliers on the line by rate after discount and **before tax**: `QA-V` **95.00** marked **Lowest**, the second supplier 96.00. Before any quote is entered Compare reads "No supplier has quoted yet. Enter quotes first."
### TC-BUY-057 — Choosing a quote that is not the lowest needs a reason; orders are raised per supplier

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a sent RFQ with two quotes as TC-BUY-056 leaves it (build it first if running this case alone).
- **Steps:** as the prepared **Firm admin**, select the RFQ → **Compare**. Choose the second supplier's quote (96.00). In the dialog **Not the lowest rate** type a reason → **Choose it**. **Save selections**. **Raise orders** → in **Raise purchase orders** confirm. **Open purchase orders**. Reopen the RFQ and try **Enter quotes**.
- **Expect:** the dialog says one purchase order is raised to each supplier chosen. One **draft** purchase order is raised to the second supplier for 10 of `QA-B` at **96.00**, with the RFQ's number as its reference. The RFQ reads **Closed**. A closed RFQ takes no more quotes: "A closed RFQ takes no quotations; quotes are entered while it is sent." **(HTTP)** choosing the dearer quote with no reason is refused: "Line 1: say why … is chosen over the lowest quote."
### TC-BUY-058 — An RFQ from an approved requisition; send and cancel refusals

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** an **approved** purchase requisition with one line naming `QA-V` (Buy > All Buy screens > Documents > Requisitions → New, Submit, Approve), and a second requisition still in draft.
- **Steps:** as the prepared **Firm admin**, on the approved requisition press **Create RFQ**. Press it again. Look for it on the draft requisition. In Requests for quotation → New with a line but **no** supplier → Save → **Send**. Select a draft RFQ → **Cancel** → leave the reason empty, then give one.
- **Expect:** the first press starts a **draft** RFQ with the requisition's lines and, as suppliers, those its lines name plus each product's preferred supplier. The second is refused: "RFQ … was already started from requisition …." Create RFQ cannot be pressed on a draft requisition (the server says "An RFQ is started only from an approved requisition."). Sending with no supplier: "Invite at least one supplier before sending." Cancelling needs a reason (the dialog **Cancel RFQ-…** says "The reason stays on the request."); afterwards the RFQ reads **Cancelled**. When orders are raised from an RFQ that came from a requisition, the requisition becomes ORDERED.
### TC-BUY-059 — Who may raise orders from an RFQ

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a user hired with the *Read Only* job template and one hired with *Purchasing*; a sent RFQ with a quote chosen.
- **Steps:** as the **Read Only** user open Buy > All Buy screens > Documents > Requests for quotation. As the **Purchasing** user open the RFQ and **Raise orders**. As a user hired with *Warehouse* look for the screen.
- **Expect:** Read Only (RFQ_VIEW) sees the list and the comparison but none of New, Send, Enter quotes, Save selections or Raise orders. Purchasing (RFQ_MANAGE and PURCHASE_CREATE) raises the orders. The Warehouse job holds neither RFQ code and is not offered the screen.
### Rate contracts and blanket orders (backlog 86 #2)

### TC-BUY-060 — A rate contract prices the order line

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** the product `QA-B` not already on an active rate contract with `QA-V` (close or cancel one left by an earlier run).
- **Steps:** as the prepared **Firm admin**, Buy > All Buy screens > Documents > **Rate contracts** → New (**New rate contract**): **Supplier** `QA-V`, **Valid from** today, **Valid to** a month on, **Add line**: `QA-B`, **Rate** `90`, **Quantity** `20` → Save. Select it → **Approve**. Buy > Purchase Orders → New for `QA-V`: add `QA-B`, quantity `15`, the price **left blank** → Save. Then a second order line with the price typed `95`.
- **Expect:** the contract takes a number from its own `RC` series, reads **Draft**, then **Active**. The order line is priced **90.00** and carries a mark whose tooltip reads "Rate contract: this rate comes from a supplier contract."; the contract's rate ranks above the supplier's price list and catalogue, and above the product's purchase price of 100. A price typed on the line (95) is kept as typed. Approving a contract needs PURCHASE_APPROVE: a *Purchasing* user can type one but cannot approve it.
### TC-BUY-061 — Drawn and remaining are derived; over-drawing warns and never refuses

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** an active rate contract for `QA-B` with `QA-V` at 90 for **20** units, as TC-BUY-060 builds, with nothing drawn yet.
- **Steps:** as the prepared **Firm admin**, raise an order for **15** at the contract rate → Submit → Approve. Open the contract and its **Releases**. Raise a second order for **10**; read the banner on the draft; Submit → Approve. Open the contract again. **Cancel** the first order and open the contract once more.
- **Expect:** after the first approval the contract line shows drawn **15**, remaining **5**; Releases (**Releases against RC-…**) lists the order line as "PO-… · line 1" with "15 @ 90". A draft order does not count as drawn. The second order shows a banner on the draft and after approval: "Over rate contract: RC-… …: 25 drawn of 20 contracted." -- and it still approves. The contract then reads drawn 25, remaining **0** (never below zero). Cancelling the first order gives its 15 back: drawn 10, remaining 10, with nothing to reverse.
### TC-BUY-062 — Overlap, expiry, closing and cancelling a contract

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** an active rate contract for `QA-B` with `QA-V` covering today.
- **Steps:** as the prepared **Firm admin**: (1) type a second contract for the same supplier and product over overlapping dates → Save → **Approve**. (2) Type a contract whose **Valid to** was yesterday → Save → Approve. (3) Try to edit the active contract. (4) **Close** the active contract, then raise an order line with a blank price. (5) On a draft contract press **Delete**; on another press **Cancel** with an empty reason, then with one.
- **Expect:** (1) refused, naming the other contract: "Another active rate contract with this supplier covers the same product for an overlapping period: …". (2) refused: "RC-… ended on …; change its period before approving it." An active contract whose last day has passed reads **Expired** in the list and prices nothing. (3) refused: "Only a draft rate contract can be changed." (4) the contract reads **Closed** and the new line takes the next price in line (the supplier's price list or catalogue, else the product's 100). (5) a draft is removed outright ("A draft contract is removed outright."); Cancel needs a reason ("The reason stays on the contract."), after which the contract reads **Cancelled** and shows "Cancelled: …".
### Serial numbers at receipt (backlog 86 #11)

### TC-BUY-063 — Serials typed, pasted or filled from a range on the receipt line

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm on the **Electronics** profile, with a serial-tracked product that carries a warranty.
- **Also needs:** a supplier, and an **approved** purchase order for **3** of the serial-tracked product.
- **Steps:** as the firm's administrator, Buy > Goods Receipts → New against the order, Accepted `3`. Click the line's **Serials** cell. In **Serial numbers · …** open **Fill a range**: **Prefix** `QA-SN`, **Start** `1`, **Count** `2`, **Width** `4` → **Add range** → OK. Save the receipt → **Complete**. Reopen the Serials cell, type a third number on a line of its own → OK → save → **Complete**. Open the completed receipt, click "3 serial numbers" on the line, and click one unit. Stock > All Stock screens > Tracking > **Serial Numbers**.
- **Expect:** the cell reads **2 of 3**, and the dialog "2 of 3 entered". The range fills `QA-SN0001` and `QA-SN0002`. A draft may be short, but completing it is refused: "Line 1 (…) receives 3 serial-tracked units but 2 are entered: enter 1 more on the goods receipt." With three it completes; three units exist, available, in the receipt's warehouse. The completed receipt shows each unit's trail (**Trail of …**) with this goods receipt first. Units are counted against accepted **plus free** goods.
### TC-BUY-064 — A serial is one unit in the whole firm

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm on the **Electronics** profile, with a serial-tracked product that carries a warranty.
- **Also needs:** a supplier; one completed receipt that brought in serial `QA-SN0001` (TC-BUY-063, or receive one unit first); two more approved orders for the serial-tracked product, one of 1 and one with **two lines** of 1 each; an approved order for a product that is **not** serial-tracked.
- **Steps:** as the firm's administrator: (1) receive the order of 1 with serial `qa-sn0001` (lower case) → save. (2) On the two-line order type the same new serial on both lines → save. (3) In the Serials dialog type one number twice. (4) **(HTTP)** send `serial_numbers` on a receipt line of the product that is not serial-tracked.
- **Expect:** (1) refused, case ignored: "Line 1 (…): serial qa-sn0001 already belongs to a unit in this firm (AVAILABLE)." (2) refused: "Serial … is entered on line 1 and on line 2 of GRN-…." (3) the dialog flags it: "Entered twice: …". (4) refused: "…: this product is not serial-tracked, so its lines take no serial numbers." -- and on the screen such a line has no Serials cell to click.
### TC-BUY-065 — Cancelling the receipt, and returning named units to the supplier

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm on the **Electronics** profile, with a serial-tracked product that carries a warranty.
- **Also needs:** a supplier and two completed receipts of the serial-tracked product from it, of 2 units each, with their serials entered; a customer.
- **Steps:** as the firm's administrator: (1) **Cancel** the first receipt. Look for its serials under Serial Numbers and receive them again on a new receipt. (2) From the second receipt sell and dispatch **one** unit to the customer, then try to **Cancel** that receipt. (3) Buy > Returns & notes > Purchase Returns → New off the second receipt: Returning `1`, click the line's **Serials** cell and name the unit still in stock → Save → Approve → Complete. (4) Cancel the completed return.
- **Expect:** (1) the cancelled receipt's units are removed and their numbers are free to be received again. (2) refused: "GRN-… cannot be cancelled: serial … has left stock since it was received (…)." (3) the return must name one unit per unit going back, each in stock and received from this supplier; after Complete the unit reads **Returned**. A serial of another product is refused: "…: serial … is not a unit of this product in this firm." (4) cancelling the completed return puts the unit back **Available**.
### Supplier free schemes on the item (backlog 86 #25, #27)

### TC-BUY-066 — A 10+2 scheme fills the free quantity on the order

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** no other active scheme on `QA-B` for `QA-V` (switch off one left by an earlier run).
- **Steps:** as the prepared **Firm admin**, Buy > All Buy screens > Documents > **Supplier schemes** → New (**New supplier scheme**): **Supplier** `QA-V`, product `QA-B`, **Buy quantity** `10`, **Free quantity** `2`, **Free product** blank ("Blank: the same product is given free."), Valid from today → Save. Buy > Purchase Orders → New for `QA-V`: `QA-B`, quantity `25`, price `100`, the **Free** box left blank → Save. Submit, Approve, receive in full and Complete. Stock > All Stock screens > Stock > Inventory.
- **Expect:** the scheme lists as **10+2**, *In force*. The order line's Free reads **4** (two free for each full ten: 25 buys two tens) and the side panel says "Line 1: Scheme 10+2 applied" under **Supplier schemes**. The line is still charged 25 x 100 = 2,500.00 before tax. The receipt offers 25 accepted and 4 free; after Complete **29** are on hand. The receipt's journal is Dr 1200 Inventory 2,500.00 / Cr 2300 Goods Received Not Invoiced 2,500.00: free goods add units, not value, so each of the 29 costs 86.21.
### TC-BUY-067 — A typed free quantity is kept, and 0 refuses the scheme

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** an active 10+2 scheme on `QA-B` for `QA-V`, as TC-BUY-066 builds.
- **Steps:** as the prepared **Firm admin**, raise three draft orders for `QA-B` from `QA-V`: quantity `25` with Free typed `0`; quantity `25` with Free typed `1`; quantity `9` with Free blank. Then an order dated before the scheme's **Valid from**, quantity `25`, Free blank.
- **Expect:** a typed **0** stays 0 and no "Scheme … applied" note shows: zero refuses the scheme, blank takes it. A typed 1 stays 1. Nine units earn nothing (fewer than one full ten). The order dated before the scheme started takes no free goods: a scheme applies only inside its dates.
### TC-BUY-068 — A scheme that gives another product adds a gift line

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a second product to be given free; no other active scheme on `QA-B` for `QA-V`.
- **Steps:** as the prepared **Firm admin**, Supplier schemes → New: `QA-V`, product `QA-B`, Buy quantity `10`, Free quantity `1`, **Free product** the second product → Save. Purchase Orders → New for `QA-V`: `QA-B`, quantity `25`, price `100`. Wait for the editor to price the order. Save.
- **Expect:** the scheme lists as "10 + 1" followed by the free product's name. The editor adds **one** line for the second product with nothing ordered and **Free 2**, at no charge, and does not add it a second time when the order is priced again. That free-only line is priced live (its amount is 0) and is kept on save. The order total is the 25 x 100 and its tax alone.
### TC-BUY-069 — Two schemes on one product cannot overlap; who may set them

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** an active scheme on `QA-B` for `QA-V` running from today with no end date; a user hired with the *Read Only* job template.
- **Steps:** as the prepared **Firm admin**: New scheme for the same supplier and product from next week → Save. New scheme with **Valid to** before **Valid from** → Save. New scheme for the same product with the supplier left as **All suppliers** → Save; raise an order from `QA-V`. Switch the supplier's own scheme off (**Active**) and raise another. As the **Read Only** user open Supplier schemes.
- **Expect:** the overlapping scheme is refused: "An active scheme for … on this product already runs … to …. End or switch it off first." Dates back to front: "A scheme cannot end before it starts." A scheme for all suppliers may stand beside a supplier's own, and the supplier's own wins on that supplier's orders; with it switched off (*Switched off*) the all-suppliers scheme applies. Read Only (SUPPLIER_SCHEME_VIEW) sees the list and no New, Save or Delete.
### Imports: foreign currency, Bill of Entry, exchange difference (backlog 86 #4, #5)

### TC-BUY-070 — A bill in the supplier's currency posts rupees at its rate

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** **Buying stages** with **Purchase order** off (see the note at the head of these cases); a supplier abroad with **Currency** `USD` on its form; a product on the **GST 0%** tax profile with nothing on hand.
- **Steps:** as the prepared **Firm admin**, Masters > Vendors → the supplier: confirm **Currency** reads USD (try `US` → Save first). Buy > Purchase Invoices → New: that supplier; add the product, quantity `10`, rate `100`. Read **Currency** and the note beside it. Save with **Exchange rate (₹ per USD)** blank; then type `83` → **Save & approve**. Open the bill, Stock > All Stock screens > Stock > Inventory, and Accounts > Journal Entries.
- **Expect:** a two-letter currency is refused on the supplier: "The currency is a three-letter code, such as USD." The bill starts in **USD** and shows "TCS, TDS and Paid now are rupee matters; pay this bill from Payments in USD." in place of the TCS boxes. With no rate: "A bill in USD needs its exchange rate: the rupees one USD was worth on the bill's date." At 83 the bill reads **1,000.00 USD** with its rupee equivalent **83,000.00**. The Approve dialog says "This bill is in USD, so TDS and Paid now are not offered. Pay it from Payments, in that currency, at the rate of the day." Ten units arrive valued 83,000.00 (8,300 each). Journals: Dr 1200 Inventory 83,000.00 / Cr 2300 Goods Received Not Invoiced 83,000.00, then Dr 2300 83,000.00 / Cr 2100 Trade Payables 83,000.00 -- no price variance.
### TC-BUY-071 — Paying in the currency at another rate posts an exchange loss or gain

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** two approved bills of **1,000.00 USD at 83** from a USD supplier, unpaid, each built as in TC-BUY-070.
- **Steps:** as the prepared **Firm admin**, Buy > Payments → **Record Payment**: the supplier. Read the note under the supplier. Set **Pay in** to *USD*, **Exchange rate (₹ per USD)** `84`, **Amount (USD)** `1000`, apply `1000` to the first bill → Record payment. Then pay the second bill the same way at `82`. Open both payments' journals.
- **Expect:** before a currency is chosen the note lists the bills open in another currency ("Open in another currency: …") and says to choose the currency to pay them. In USD: "The amount and each applied figure are in USD, and the payment is applied in full to the USD bills. No TDS, deductions or advance on these." At 84 the toast adds "Exchange loss ₹1000.00." and the journal is Dr 2100 Trade Payables 83,000.00, Dr 4950 Exchange Gain/Loss 1,000.00 / Cr 1010 Bank 84,000.00. At 82 it adds "Exchange gain ₹1000.00.": Dr 2100 83,000.00 / Cr 1010 Bank 82,000.00, Cr 4950 Exchange Gain/Loss 1,000.00. Both bills owe nothing in either currency.
### TC-BUY-072 — A part payment settles in proportion; reversing brings it all back

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** one approved bill of **1,000.00 USD at 83**, unpaid, as in TC-BUY-070.
- **Steps:** as the prepared **Firm admin**, Record Payment in USD at `84`: Amount `400`, applied to the bill. Open Record Payment again and read what the bill owes. Buy > Payments → **Reverse** the payment with a reason. Read the bill again.
- **Expect:** 400 USD at 84 costs 33,600.00 and clears 33,200.00 of the bill (400 x 83): Dr 2100 Trade Payables 33,200.00, Dr 4950 Exchange Gain/Loss 400.00 / Cr 1010 Bank 33,600.00. The bill then owes **600.00 USD** and **49,800.00** rupees, both shown. Reversing mirrors all three legs, and the bill owes 1,000.00 USD and 83,000.00 again.
### TC-BUY-073 — Rupees, TDS and an advance are refused against a foreign bill

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** one approved bill of 1,000.00 USD at 83, unpaid.
- **Steps:** as the prepared **Firm admin**: (1) Record Payment with **Pay in** left *Rupees* and look for the USD bill among the bills to apply to. (2) In USD at 84, Amount `1200`, applying 1,000 to the bill. (3) In USD with the rate blank. (4) **(HTTP)** `POST /api/v1/payments` in rupees with an allocation to the USD bill; and a USD payment with `tds_amount` 10. (5) **(HTTP)** save a USD bill with `tcs_amount` 5.
- **Expect:** (1) in rupees the USD bill is not offered: rupees pay the rupee bills. (2) refused before sending: "A payment in USD is applied in full to the supplier's USD bills: … of the … is applied." -- an advance in another currency is not carried. (3) the dialog asks for the exchange rate. (4) "Bill … is in USD. Pay it with a payment in USD at the day's rate."; and "A payment in USD takes no TDS, rounding, bank charges or discount; record it for the amount that was sent." (5) "TCS under 206C(1H) is charged by a seller in India; a bill in another currency carries none."
### TC-BUY-074 — A Bill of Entry lands customs duty on the stock and claims the IGST

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** one approved bill of 10 at 100 USD at 83 from a USD supplier, as in TC-BUY-070, with all ten units still on hand (83,000.00, 8,300 each).
- **Steps:** as the prepared **Firm admin**, Buy > All Buy screens > Documents > **Bills of entry** → New (**New Bill of Entry**): **Bill of Entry number** `1234567`, the BoE date today, **Port code** `INMAA1`, **Supplier** the USD supplier; tick the bill under **Supplier bills the goods came on**; **Add item**: the product, **Quantity** `10`, **Assessable value** `85000`, **BCD %** `10`, **SWS %** blank, **IGST %** `18`, every amount box blank → **Save**. Read the worked figures. Select it → **Post**. Stock > All Stock screens > Stock > Inventory; Journal Entries; Accounts > All Accounts screens > Tax filing > GST Returns → GSTR-3B for the month.
- **Expect:** the draft works out **BCD 8,500.00**, **SWS 850.00** (10% of the BCD when no rate is typed), IGST base 94,350.00 and **IGST 16,983.00**. After Post the document reads **Posted** and shows Customs duty 9,350.00, IGST 16,983.00, **To stock 9,350.00**, To COGS 0.00, To expense 0.00. The ten units are now worth 92,350.00: the average rises from 8,300.00 to **9,235.00**. Journal: Dr 1200 Inventory 9,350.00, Dr 1310 Input IGST 16,983.00 / Cr 2800 Customs Duty Payable 26,333.00. GSTR-3B shows 16,983.00 under 4(A)(1) *Import of goods*. Customs duty has no credit; only the IGST does.
### TC-BUY-075 — Typed amounts, goods already sold, cancelling and the duplicate number

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a posted Bill of Entry as TC-BUY-074 leaves it; a second approved USD bill of 10 units of a **different** product, of which **4 have been sold and dispatched**; a user hired with the *Purchasing* job template.
- **Steps:** as the prepared **Firm admin**: (1) New Bill of Entry for the second bill: Assessable value `85000`, BCD % `10`, **BCD amount** typed `9000`, IGST % `18` → Save → Post. (2) **Cancel** the Bill of Entry of TC-BUY-074 with a reason; read the stock and GSTR-3B. (3) New Bill of Entry with the same number, port and date as an existing one → Save. (4) A Bill of Entry with no item → Post. (5) As the **Purchasing** user type a draft and look for Post.
- **Expect:** (1) the typed 9,000.00 wins over 10%; SWS is 900.00 and the duty 9,900.00. Six of the ten units are on hand, so **To stock** is 5,940.00 and **To COGS** 3,960.00: duty on goods already sold goes to cost of goods sold. (2) the dialog (**Cancel Bill of Entry …**) says the journal is reversed and the duty comes off the stock; afterwards it reads **Cancelled**, the average is 8,300.00 again and 4(A)(1) no longer carries its IGST. (3) refused: "Bill of Entry … at … on … is already …." (4) refused: "Add at least one line before posting." (5) Purchasing (BILL_OF_ENTRY_MANAGE) saves the draft but is not offered **Post** or Cancel, which need PURCHASE_APPROVE. Customs itself is paid by a journal: Dr 2800 Customs Duty Payable / Cr 1010 Bank.
### TC-BUY-076 — Revaluing what is still owed in another currency at a period end

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** exactly one unpaid bill in USD in the firm, of 1,000.00 USD at 83; no revaluation yet posted for the date used.
- **Steps:** as the prepared **Firm admin**, Accounts > Journal Entries → **Revalue foreign payables**. **As of** the last day of last month (the bill must be dated on or before it; use today if it is not), `USD: rupees per unit` `85` → **Post revaluation**. Read the result and the journal list. Post the same date again. Then pay the bill in USD at 84.
- **Expect:** the dialog says it restates what is still owed in each currency. The result reads a net exchange **loss of 2,000.00** (1,000 USD x (85 - 83)). One entry `FXREV-<date>` dated the as-of date: Dr 4950 Exchange Gain/Loss 2,000.00 / Cr 2100 Trade Payables 2,000.00; and its mirror `FXREV-<date>-REV` dated the next day. A second run for the same date is refused: "Payables in other currencies were already revalued on … (FXREV-…)." The revaluation is unrealised: the bill still reads 83,000.00, and paying it at 84 posts the whole 1,000.00 loss against its own rate. Pressing Post with no rate typed: "Type the rate of at least one currency."
### Fixed assets (backlog 86 #7)

### TC-BUY-077 — A capital-goods bill line becomes a fixed asset, not stock

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** **Buying stages** with **Purchase order** off (see the note at the head of these cases); a product for the asset (a desk) on GST 18% with nothing on hand.
- **Steps:** as the prepared **Firm admin**, Accounts > All Accounts screens > Fixed assets > **Asset classes**: confirm the five a firm starts with. Buy > Purchase Invoices → New for `QA-V`, **Entered on** `2026-10-01`: the desk, quantity `1`, rate `36500`. On the line tick **Capital goods (raises a fixed asset when approved)**; save without choosing a class; then **Asset class (required)** *FURNITURE · Furniture and Fittings* → **Save & approve**. Accounts > All Accounts screens > Fixed assets > **Asset register**; Stock > All Stock screens > Stock > Inventory; Journal Entries; Reports > Financial → GST purchase register.
- **Expect:** the classes are PLANT, FURNITURE, COMPUTERS, VEHICLES and OFFICE_EQUIPMENT, all *Straight line* with Residual % 5. Without a class: "Line 1 is capital goods: choose its asset class." After approval the register has one asset `FA-…`, class FURNITURE, Cost **36,500.00**, Net book value 36,500.00, *In use*, "Raised by bill PI-…". **Nothing** is added to stock. One journal: Dr 1500 Fixed Assets 36,500.00, Dr 1320 Input CGST 3,285.00, Dr 1330 Input SGST 3,285.00 / Cr 2100 Trade Payables 43,070.00 -- no Inventory and no Goods Received Not Invoiced. The GST is claimed in full; the register row shows it again under **Capital goods tax 6,570.00**.
### TC-BUY-078 — Capital goods already received into stock are refused; cancelling the bill takes the asset off

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** for the second part, a capital-goods bill approved as in TC-BUY-077 whose asset has **not** been depreciated.
- **Steps:** as the prepared **Firm admin**: (1) with the full chain on, Buy > Purchase Invoices → New for the completed receipt of 6; tick **Capital goods** on its line, choose a class → save → **Approve**. (2) **Cancel** the approved capital-goods bill of the second part and open the Asset register. (3) On an asset raised by a bill press **Delete**, and try to change its Cost.
- **Expect:** (1) refused: "Line 1 is capital goods, but GRN-… already took it into stock. Capital goods are received on the bill itself: untick capital goods, or bill it without a completed receipt." (2) the bill is cancelled, its journal mirrored and its asset gone from the register. (3) "Asset FA-… was raised by a bill; cancelling the bill takes it off the register." and "Asset FA-… costs what its bill charged; change the bill, not the asset."
### TC-BUY-079 — A depreciation run: straight line and written down value, by days

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** no depreciation run covering October 2026 or later (cancel the latest first if one does); an asset class of its own typed under **Asset classes** → New (**New asset class**): Code `QA-WDV`, **Method** *Written down value*, **Rate %** `40`, **Residual %** `5`; two assets typed under **Asset register** → New (**New fixed asset**), both acquired and put to use on **2026-10-01** at **Cost** `36500`: one in class FURNITURE (straight line, life 10 years, residual 5%), one in `QA-WDV`.
- **Steps:** as the prepared **Firm admin**, Accounts > All Accounts screens > Fixed assets > **Depreciation runs** → **Run depreciation**: **From** `2026-10-01`, **To** `2026-10-31` → Run depreciation. Open the run and find the two assets. Open each asset's **Schedule**. Journal Entries. Then run the same period again, and a period ending before `2026-10-31`.
- **Expect:** typing an asset by hand posts nothing. The run lists each asset charged with its days: both **31**. The furniture asset: (36,500 - 1,825) / 10 years = 3,467.50 a year, x 31/365 = **294.50**. The written-down asset: 40% of 36,500 = 14,600.00 a year, x 31/365 = **1,240.00**. One journal for the whole run, reference `DEP-…`, dated 2026-10-31: Dr 6950 Depreciation / Cr 1590 Accumulated Depreciation, 1,534.50 for these two (more where other assets were due). Each asset's Net book value falls by its charge and its schedule shows the charge, then the years projected. The same period again: "Depreciation run … already charged 2026-10-01 to 2026-10-31. Cancel it, or run a period after it." An earlier period: "Runs go forward: … charged up to 2026-10-31. Cancel it to run an earlier period."
### TC-BUY-080 — Disposing of an asset books a loss or a gain

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** the two assets and the October 2026 run of TC-BUY-079 (book values 36,205.50 and 35,260.00).
- **Steps:** as the prepared **Firm admin**, Asset register → select the furniture asset → **Dispose** (**Dispose of FA-…**): **Disposed on** `2026-10-31`, **Sale amount** `35000`, **Money came by** *Bank*, a **Reason** → Dispose. Then the written-down asset: Disposed on `2026-10-31`, Sale amount `36000`, *Cash*. Journal Entries. Then try to dispose of another depreciated asset on `2026-10-15`, and to cancel the October run.
- **Expect:** the dialog states the net book value the asset stands at. The furniture asset: Dr 1590 Accumulated Depreciation 294.50, Dr 1010 Bank 35,000.00, Dr 4960 (loss on disposal) 1,205.50 / Cr 1500 Fixed Assets 36,500.00; the register shows it **Disposed**, with **Gain / loss -1,205.50**. The written-down asset: Dr 1590 1,240.00, Dr 1000 Cash 36,000.00 / Cr 1500 36,500.00, Cr 4960 (gain) 740.00. Disposing on the last day already charged adds no further depreciation; on a later day the days since are charged first, in a run of type *Disposal*. A day before the last charge is refused: "Depreciation on FA-… is charged to 2026-10-31. Dispose of it on or after that day, or cancel the runs that charged past it." Cancelling the October run is now refused, because assets it charged have since been disposed at the book value it left.
### TC-BUY-081 — Cancelling a run, the Income-tax block schedule, and who may post

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a financial year April 2026 to March 2027; an asset class of its own, Code `QA-IT`, straight line, with **Income-tax rate %** `25` (a rate no other class uses); two assets typed by hand in it at Cost `40000` each, one acquired and put to use `2026-06-01`, one `2026-12-01`; a latest depreciation run that charged them and no disposal since; a user hired with the *Read Only* job template.
- **Steps:** as the prepared **Firm admin**, Depreciation runs → select the latest run → **Cancel** with a reason (**Cancel run …**). Accounts > All Accounts screens > Fixed assets > **Income-tax block schedule**, **Financial year** 2026-27; find the 25% block. Try to **Delete** the class `QA-IT`. As the **Read Only** user open the Asset register and look for New, Dispose and Run depreciation. **(HTTP)** as a user holding FIXED_ASSET_MANAGE but not JOURNAL_POST: `POST /api/v1/fixed-assets/depreciation-runs`.
- **Expect:** the cancelled run reads **Cancelled** with its reason, its journal is reversed (`DEP-…-REV`) and the period can be run again. The 25% block for 2026-27 shows Opening WDV 0.00, **Additions (full) 40,000.00** (used 180 days or more in the year), **Additions (half) 40,000.00** (used less than 180 days), Depreciation **15,000.00** (10,000.00 at 25% plus 5,000.00 at half the rate) and Closing WDV **65,000.00**. The schedule posts nothing. Deleting the class is refused: "Asset class QA-IT has assets on the register. Move them to another class, or mark this one inactive." Read Only (FIXED_ASSET_VIEW) reads the four screens and is offered nothing that changes them. The HTTP call is refused with 403: "This posts a journal, which needs JOURNAL_POST as well."
### Batch-wise PTR and PTS (backlog 86 #22)

### TC-BUY-082 — PTR and PTS captured on the receipt line reach the batch

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it.
- **Also needs:** a supplier, and an approved purchase order for **20** of the batch-tracked product at 60.
- **Steps:** as the firm's administrator, Buy > Goods Receipts → New against the order, Accepted `20`. On the line type a new batch number `QA-PTR-1`, its expiry, **MRP** `120`, **PTR per unit (retailer)** `90`, **PTS per unit (stockist)** `80` → save → **Complete**. Stock > Batches: read the batch's row and open it. Then receive a second order into the **same** batch with PTR `92` and PTS blank → Complete. Settings > Platform > System > Audit Logs.
- **Expect:** the batch list shows columns **PTR** and **PTS**; the new batch reads MRP 120, PTR **90**, PTS **80**. After the second receipt PTR reads **92** and PTS is still 80: a rate the receipt states replaces the batch's, a blank never clears it. The change is audited as `batch.rates_updated` with the old pair.
### TC-BUY-083 — A trade rate needs a batch and may not exceed the MRP

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it.
- **Also needs:** a supplier and an approved purchase order for the batch-tracked product.
- **Steps:** as the firm's administrator, on a new goods receipt line type MRP `100` and PTR `120` → save. Correct PTR to `90`. **(HTTP)** send a receipt line with `ptr` 90 and no `batch_number`. Stock > Batches → edit a batch: type PTS above its MRP → Save.
- **Expect:** the screen refuses a rate above the MRP before sending; the server's own words are "PTR 120.00 cannot exceed the MRP 100.00." The line without a batch: "Line 1: PTR and PTS are kept on the batch, so the line needs a batch number." The batch editor's PTR ("Price to retailer, per stock unit.") and PTS ("Price to stockist, per stock unit.") are held to the same cap.
### TC-BUY-084 — A retailer is charged PTR and a stockist PTS from the batch

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it.
- **Also needs:** a batch in stock with MRP 120, PTR 90 and PTS 80, as TC-BUY-082 builds, of a product whose selling price is **100** and which is on no price list; four customers, their **Trade class** set to *Retailer*, *Stockist*, *Other* and *Not set*.
- **Steps:** as the firm's administrator, Masters > Customers → open one and read **Trade class** ("Picks PTR or PTS when a sales price is left blank"). Sell > Sales Orders → New for the retailer: add the product, choose the batch under **Batch** on the line, leave the price blank → save. The same for the stockist, the *Other* customer and the *Not set* customer. Then for the retailer again with the price typed `95`, and once more with no batch chosen.
- **Expect:** Retailer: **90.00**. Stockist: **80.00**. Other and Not set: **100.00**, the product's own price. A typed 95 stays 95. With no batch chosen the retailer is charged 100.00: the rates live on the batch. An agreed price list for the customer would rank above the batch's rate, and the batch's rate above the customer's price level. The price box is never prefilled on screen; the rate appears when the order is priced. On a delivery note the batch picker shows "PTR 90.00" and "PTS 80.00" beside the MRP.
### TC-BUY-085 — A firm without the feature is shown none of it

*Added 2026-10-05 from the code and its automated tests; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm on the **Electronics** profile, with a serial-tracked product that carries a warranty.
- **Also needs:** a supplier and an approved purchase order.
- **Steps:** as the firm's administrator, open a new goods receipt line, Stock > Batches, and a customer's form. **(HTTP)** send a goods receipt line with `ptr` 90 in this firm.
- **Expect:** the Electronics profile does not carry *batch-wise PTR / PTS* (Pharmacy, Food and Wholesale do), so the receipt line has no PTR or PTS box, the batch list no PTR or PTS column and the customer form no **Trade class**. The HTTP write is refused by the feature gate and nothing else about the receipt is affected: a line that sends neither field saves as before.

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 06-S01 | **Buy > All Buy screens > Insight > Purchase Dashboard** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S02 | **Buy > All Buy screens > Insight > Purchase Analysis** | Offered to any role holding `PURCHASE_VIEW` or `REPORT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S03 | **Buy > All Buy screens > Insight > Rate Trend** | Offered to any role holding `PURCHASE_VIEW` or `REPORT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S04 | **Buy > Purchase Orders** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S05 | **Buy > Returns & notes > Debit Notes** | Offered to any role holding `DEBIT_NOTE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S06 | **Buy > All Buy screens > Documents > Requisitions** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_REQUISITION_CREATE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S07 | **Buy > All Buy screens > Documents > Requests for quotation** | Offered to any role holding `RFQ_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S08 | **Buy > All Buy screens > Documents > Rate contracts** | Offered to any role holding `RATE_CONTRACT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S09 | **Buy > All Buy screens > Documents > Supplier schemes** | Offered to any role holding `SUPPLIER_SCHEME_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S10 | **Buy > All Buy screens > Documents > Bills of entry** | Offered to any role holding `BILL_OF_ENTRY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S11 | **Buy > All Buy screens > Documents > Quality Inspection** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_INSPECT`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S12 | **Buy > All Buy screens > Money > Supplier Rebates** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S13 | **Buy > All Buy screens > Money > Principal Claims** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S14 | **Buy > All Buy screens > Documents > Approvals** | Offered to any role holding `SALES_APPROVE` or `PURCHASE_APPROVE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S15 | **Buy > All Buy screens > Money > Landed Costs** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S16 | **Settings > Buying > Purchase Settings** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S17 | **Buy > Purchase Invoices** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_CREATE` or `PURCHASE_UPDATE` or `PURCHASE_IMPORT` or `PURCHASE_EXPORT` or `PURCHASE_APPROVE` or `PURCHASE_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S18 | **Buy > Returns & notes > Purchase Returns** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_CREATE` or `PURCHASE_UPDATE` or `PURCHASE_IMPORT` or `PURCHASE_EXPORT` or `PURCHASE_APPROVE` or `PURCHASE_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S19 | **Buy > Goods Receipts** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_RECEIVE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
