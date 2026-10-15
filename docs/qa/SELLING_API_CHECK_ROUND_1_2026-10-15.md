# Selling, API check round 1 (2026-10-15)

Driven over HTTP against the running backend with the kept scripts in `docs/qa/checks/selling/` (`setup.py`, then `python docs/qa/checks/run.py selling`). Two `ready-firm` fixtures (firm one with its Firm admin, a Viewer and a Sales executive; firm two for the cross-firm probes). Every script makes its own product, customer and documents under a fresh tag and puts any firm setting it changes back (GET, change, PUT back: `workflow-settings`, `credit-settings`, `gst-compliance-settings`). 26 scripts: 20 cases and 6 probes. Two full runs gave the same result.

| Case | Result | Notes |
| --- | --- | --- |
| TC-SELL-005 | PASS | Draft, sent, accepted, converted; a second convert is 422 "already became". |
| TC-SELL-007 | PASS | Draft reserves nothing; approval: on hand 100, reserved 12, ledger RESERVE 12. The promotion-claims report is not driven (needs the coupon and offer set-up). |
| TC-SELL-008 | PASS | Hold quotes the reason on a new note, reserved stays 12, release returns plain APPROVED. |
| TC-SELL-009 | PASS | Draft and approved notes move nothing; 5 then 7 take the order PARTIALLY_DELIVERED then DELIVERED, stock 95/7 then 88/0, ledger DISPATCH -5 and -7. |
| TC-SELL-010 | PASS | The note carries 84 less 2.5% after the customer's standing rate changed; the bill is 483.21. |
| TC-SELL-011 | PASS | 6 against 5 refused; 483.21 journal Dr receivable, Cr 409.50, 36.86, 36.85; customer owes 483.21. |
| TC-SELL-015 | PASS | 9 refused ("5 sent"); 2 credits 193.28, ledger SALES_RETURN +2, outstanding down 193.28; a return of a never-billed note credits 0, unbilled quantity 3, only the `-COST` journal. |
| TC-SELL-016 | PASS | 50 gives 59.00 (tax 9.00), outstanding down 59; 400 refused naming 409.50 and 50.00. |
| TC-SELL-017 | PASS | No order is 422; PF number, PROFORMA INVOICE, "not a tax invoice", nothing posted; the proforma is unchanged after the order is cancelled. |
| TC-SELL-018 | PASS | WARN dispatches Sale and On approval notes; BLOCK refuses the Sale note, `dispatch-and-invoice` dispatches and approves the bill, On approval and Route sale go free; Other without words is 422. The screen's three buttons are not driven. |
| TC-SELL-027 | PASS | Two notes of one salesman make one two-line bill; a note of another salesman is refused ("same salesman"). The customer-first tick list is a screen step. |
| TC-SELL-091 | PASS | Cancelling a draft counter bill and a held one frees 7; the bill's order and note read CANCELLED; the other order's 3 stays reserved; RESERVE then UNRESERVE. |
| TC-SELL-094 | PASS | A, B and C as written: 236.00, 118.00 (unbilled 1, names bill B in the GST register), 0.00 (unbilled 5); summary total +354, pending +590 while draft; GST register rows -200 and -100, none for C. |
| TC-SELL-095 | NOT DRIVEN | Needs a `pharma-firm` with batch tracking. |
| TC-SELL-100 | PASS | See "Case text" for how Save works at the API; refusals and the three approvals as written. |
| TC-SELL-101 | PASS | Wholesale 80/150/40, Retail 95/190/38, a typed 91 holds, no level 100/200/40, a foreign or switched-off level refused, a bill typed directly 80 then 95, a bill of notes naming a level refused. |
| TC-SELL-102 | PASS | Default, chosen, note-wins and bill-wins addresses; B, C (default billing) and the print text; another customer's address refused. Step 8 (removing the Gammabad address) is not driven. |
| TC-SELL-104 | PASS | Totals to the paisa (see "Observed, not a defect" for the stored figure). |
| TC-SELL-105 | PASS | 117.99, then 118.00 with Round off 0.01 on preview, bill, journal, print and a full return; customer back to the start. |
| TC-SELL-107 | PASS | Edit keeps number, date, reason; 3 re-prices; Approved return refused; a Viewer is 403. The box-unit quotation and offer steps are not driven. |
| TC-SELL-108 | PASS | Bulk approve 3 of 3; back-order report names only the two short orders (10 and 7), the id-scoped rows equal the whole report's, 201 ids is 422. |
| p_sell_stage_off | **FAIL** | S2 below. Both stages off and "order on, note off" behave. |
| p_sell_salesman_required | PASS | A bill and an order without a salesman are refused by name; with one they are accepted; the return and the delivery note inherit it. |
| p_sell_return_approval | PASS | The settings hold three approval switches and none for a sales return; a return is always draft, approve, complete. |
| p_sell_credit_block | PASS | BLOCK refuses an over-limit bill at save and at approval and an order at approval; WARN passes the same draft; a bill inside the limit passes. |
| p_sell_round_returns | **FAIL** | S1 below. A credit note is not rounded (11.80), and a full return is exact. |
| p_sell_other_firm_and_viewer | PASS | Another firm's order, note, bill and return are 404 (403 with its id in the header), cancel/approve/credit note/proforma refused; a Viewer reads but cannot raise an order, bill, return or note, hold, or approve. |

## Defects

### S1 (Medium): with "Round every bill to the nearest rupee" on, each partial return rounds on its own, so parts do not add up to the bill

- **Request:** switch `round_bills_to_rupee` on; bill 7 pieces at 12.34 (GST 18%): the bill is 102.00. Return the pieces one at a time (`POST /api/v1/sales-returns`, approve, complete, seven times). Same with 3 at 33.35: bill 118.00.
- **Expected:** the returns, taken together, credit what was billed, 102.00 and 118.00, and the customer owes nothing.
- **Got:** 7 x 12.34: each return is 14.56 rounded to 15.00, so 105.00 is credited against a bill of 102.00; the ledger receivable nets to -3.00 while the customer's outstanding reads 0. 3 x 33.35: each return is 39.35 rounded to 39.00, 117.00 credited against 118.00; the customer is left owing 1.00 and the ledger agrees. A return of everything at once, and a credit note, are exact.
- **Cause:** `backend/app/sales_return/services/sales_return_service.py:1665-1667` sets `row.round_off = rupee_round_off(worked_out)` on every return; the comment says "so a bill returned in full is cancelled to the rupee" but nothing limits it to a full return. The credit note does not round, which is why it is exact.
- **Reproduce:** `python docs/qa/checks/run.py selling p_sell_round_returns` (repeated in both runs).

### S2 (Medium): Sales Stages accepts "order off, delivery note on", and then nothing can be typed or billed

- **Request:** `PUT /api/v1/sales-orders/workflow-settings` with `sales_order_stage: false, delivery_note_stage: true` (accepted, 200). Then a bare bill (`POST /api/v1/sales-invoices` with product lines) and a delivery note without an order.
- **Expected:** either the combination is refused when saved, or a bill/note can still be raised (the order being the stage that is switched off).
- **Got:** the bill is 422 "This firm raises a sales order and a delivery note before it bills, so an invoice line must name the document it bills."; the delivery note requires `sales_order_id` and its line `sales_order_line_id`, so it is 422 too. Only an order can be raised, and the firm has switched order typing off. The other mixed case, order on and note off, works (a bill of an approved order raises the note behind it and stock leaves at approval).
- **Cause:** `backend/app/sales_invoice/services/sales_chain_service.py:205` synthesises order and note only when both stages are off; `backend/app/sales_order/services/workflow_settings_service.py:177-178` stores the two stage flags with no check on the pair.
- **Reproduce:** `python docs/qa/checks/run.py selling p_sell_stage_off`.

## Observed, not a defect

- Documents store money to four decimals: 1,000 pieces at 100.00 incl. GST read `grand_total` 99999.9999 and the part bill of 200 reads 19999.9999; a round-off of 0.0118 where the case says 0.01. The journals post 100,000.00, 20,000.00 and 118.00 / 0.01, and the customer's balance is exact, so only a client that shows four decimals would see it. Every comparison in the scripts rounds to the paisa.
- A draft bill reserves its quantity even beyond the stock: a refused bill of 500 against 50 left a draft holding 500 (reserved 502 on a stock of 50), and it blocked the next approval ("Insufficient available stock") until it was cancelled. Case 100 step 5 says the draft stays; it does not say it keeps the reservation.
- `credited_amount` on a return reads 193.2840, with four decimals; the journal and the customer's balance use 193.28.

## Case text (08_SELLING.md), not edited

- **TC-SELL-100 steps 3, 5:** at the API, create gives a Draft and the second call (`/approve`) completes it; "Save" is the screen doing both. Step 4's "Only whoever raised this sales invoice..." is the answer for a draft raised while the switch was off; a draft raised while it was on answers "waits for approval, which needs SALES_APPROVE". Step 5 should add that the refused bill stays a draft *and keeps its reservation* (see above).
- **TC-SELL-100 and the settings screen:** the case lists three approval switches; `workflow-settings` also has `new_outlets_need_approval` (a different switch). There is no switch for a sales return.
- **TC-SELL-094 step (1):** the cost entry is 120.00 (2 x 60), not part of the 200.00 sales-returns debit; the credit entry is the one totalling 236.00.
- **TC-SELL-105 step 3:** the document carries Round off 0.0118 (four decimals); it prints and posts 0.01.
- **TC-SELL-104 step 1:** "total 50,000.00" holds; the stored figures are 42372.8814 and 7627.1186, which round to 42,372.88 and 7,627.12.

## Not driven

TC-SELL-095 (needs a batch-tracked pharma firm); the promotion-claims report in 007; the on-screen buttons and confirmation dialogs in 018; the customer-first tick list in 027; step 8 of 102; the box-unit quotation and offer steps of 107; every screen step (nothing was clicked).
