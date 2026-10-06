# Selling, buying and pricing screens: checked through the real desktop app, round 1, 2026-10-07

First pass of the screen layer: the real phase 2 Flutter Windows app
(`lib/main_phase2.dart`, debug build) driven by Flutter `integration_test`
against the real server at http://127.0.0.1:8000. Backend `main` at `3e2cec5c`
(branch `test/desktop-flows-buy-sell-price`), nothing under `desktop/lib` or
`backend/` changed, nothing fixed, no restart, no migration. Driven between
about 23:20 IST on 6 October and 00:40 IST on 7 October 2026.

Each step reads its result back two ways: from the screen (document number,
total and status as the list shows them) and from the server over HTTP as the
same user, and checks the document's own arithmetic (grand total = taxable
value + tax, line quantity = the quantity typed). Ids start at **SCRQ-1**.

## Firm and user

| Fixture firm | `T10069CWY-S` ("Selling t10069cwy", a `selling-firm` Wholesale fixture) |
| --- | --- |
| User | `t10069cwy.tradeadmin@fixtures.local`, password `Fixture@2026pw` (the firm administrator the fixture builds) |
| Data used | customer Vijaya Stores (`T10069CWY-C01`, standing 7.5 percent), product Detergent 1kg (84.00, GST 18), supplier Principal supplier |
| Firm data left behind | quotations, orders, notes, bills and a 5 percent offer raised by the runs; stock fell by each run's dispatch |

## How to re-run

From `desktop/` in Git Bash, with free memory over 2.5 GB and the backend up:

```bash
export IT_EMAIL=t10069cwy.tradeadmin@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=900
bash integration_test/run.sh selling_flow_test.dart
bash integration_test/run.sh buying_flow_test.dart
bash integration_test/run.sh pricing_flow_test.dart
```

Each prints `FLOW: PASS|FAIL|DEFECT|SKIP` lines and a `FLOW: SUMMARY`. One
run at a time. A run raises documents in the fixture firm and each selling run
dispatches 12 units, so top the stock up or cancel old approved notes before
the fifth or sixth run. The first build takes about two minutes.

## Selling (`selling_flow_test.dart`): 15 of 15 steps pass on the final run

| Step | Result | What the screen showed |
| --- | --- | --- |
| quotation: new, line, save | PASS | Vijaya, Detergent, quantity 10 saved; taxable and total equal the server's |
| quotation: list shows its number and total | PASS | number and grand total are on the list |
| quotation: revise, change quantity, save | PASS | "Revise" opens the editor; quantity 12 saved, total 1,129.97 |
| quotation: Mark as sent / Customer accepted / Convert to order | PASS (3 steps) | status read back SENT, ACCEPTED, CONVERTED from the server after each |
| order: converted order exists with sound figures | PASS | order total equals the quote's 1,129.97 |
| order: list shows it, approve | PASS | list total shown; status Approved on screen and APPROVED on the server |
| delivery note: new off the order, save | PASS | note for 12, same order |
| delivery note: approve | PASS | status moves off DRAFT |
| delivery note: dispatch | PASS | DISPATCHED (see SCRQ-2 for the dialog that appears) |
| invoice: new, bill the note, save | PASS | note ticked in the tick list; bill total equals the order's |
| invoice: approve | PASS | status moves off DRAFT, total on the list |
| receipt: record against the bill | PASS | "Oldest first" allocates; receipt equals the bill, bill owes nothing |
| return: new off the bill, save, approve | PASS | one unit returned, approved |

## Buying (`buying_flow_test.dart`): 10 of 10 steps pass on the final run

| Step | Result | What the screen showed |
| --- | --- | --- |
| order: new, line, save | PASS | quantity 10, total as the server |
| order: list shows number and total | PASS | |
| order: reopen (Edit), change quantity, save | PASS | quantity 12 |
| order: submit for approval | PASS | a draft needs Submit before Approve |
| order: approve | PASS | Approved on the screen and on the server |
| receipt: new off the order, complete | PASS | status COMPLETED, quantity 12 |
| bill: new off the receipt, save | PASS | receipt ticked, supplier's invoice number typed, bill equals the order total |
| bill: approve | PASS | |
| payment: record against the bill | PASS | payment equals the bill, bill owes nothing |
| return: new off the receipt, save, approve | PASS | |

## Pricing (`pricing_flow_test.dart`): 8 of 8 steps pass, one oddity recorded

| Step | Result | What the screen showed |
| --- | --- | --- |
| price list: new with a product price, save | PASS | code and name typed, Detergent at 80 saved, row on the grid |
| offer: new with a budget, save, reopen | PASS, with SCRQ-3 | percent 5, budget 5000 saved; the view reads "Value: 0 used, 5000.0000 left of 5000.0000" |
| coupon: new for the offer, save | PASS | on the Coupons grid (the save button is "Create") |
| loyalty: opens, shows a customer's points | PASS | Vijaya: Points 64.53, Worth 64.53, earned on SI-26-27-000005 |
| commission: new rule, save | PASS | a 3 percent firm-wide rule on the server |
| principal claim: open, price cut claim preview | PASS | the dialog opens and answers |
| order: picks up the offer, shows its discount | PASS | line discount 5 percent from a promotion; taxable equals 10 x rate less 5 percent |

The last step cannot tell the new offer from the fixture's own 5 percent
PSCHEME, so it proves an offer is picked up, not that the new one was.

## Findings

| Id | Severity | Screen | Symptom | Expected | File:line |
| --- | --- | --- | --- | --- | --- |
| SCRQ-1 | Low | Sales invoice editor | With the customer chosen, the screen text still includes the picker hint "Choose the customer first" (seen in the on-screen text dump; not confirmed visually) | the hint hides once a customer is chosen | `lib/ui/sales/sales_invoice_editor_phase2.dart:609` (hint text on the bill-from-notes picker) |
| SCRQ-2 | Oddity, not a defect | Delivery notes, Dispatch | Dispatch on an approved note with no bill opens "No invoice yet" and its filled button is "Dispatch and invoice": a flow that confirms the dialog by its filled button raises and approves a bill as a side effect. The first runs did exactly that and found the note "not billable" because it was already billed. This was the flow, not the app; the flow now taps "Dispatch anyway" | none | `lib/ui/delivery_notes/delivery_note_management_page.dart:1355-1370` |
| SCRQ-3 | Low | Promotions, offer view | Budget line prints raw server decimals: "0 used, 5000.0000 left of 5000.0000" | amounts in the grouped two-decimal form the rest of the app uses | `lib/ui/pricing/promotion_page.dart:749-753` |
| SCRQ-4 | Low | Purchase invoice list | When the connection to the server drops while the list reloads after a save, an `HttpException` reaches the framework unhandled (only `ApiException` is caught) instead of showing "cannot reach the server". Met once when the backend dropped a request mid-run | a message on the page | `lib/ui/purchase_invoices/purchase_invoice_management_page.dart:333` |

What was the flow and not the app, so no row: "delivery note: dispatch"
failing on the 23:44 run was insufficient stock (the earlier runs' approved
notes, 7 x 12 units, had reserved it; the server answered "Insufficient
available stock for dispatch line") and was cleared by cancelling those notes;
"invoice: bill the note, save" failing was the note not being billable because
the dialog above had already billed it (and, before that, the flow ticking the
oldest note's box instead of the newest); the quotation "not converted" reading
was a stale read in the flow; "Approve" not found on a purchase order was the
missing Submit step; buttons "New Quotation", "New Order" and so on are all
"+ New" in phase 2.

**The desktop app exited on its own in 4 of the 12 runs** (exit 79, no crash
event in the Windows log, always 40 to 60 seconds in, at different steps).
Cause not found; another process on this PC may be stopping
`agency_desktop.exe`. Recorded as unexplained, not as an SCRQ row.

## Not driven

Everything under "Main paths only": no edge cases, no refusals (see the
negative section), no printing, attachments, e-way bills, e-invoicing, no
counter (walk-in) bill, no stock hold, no batch or serial lines, no price level
screens, no coupon redemption on an order, loyalty redemption or adjustment,
commission accrual and payouts, principal claim raise and payment, quotation
print and send, credit notes and debit notes, and no second warehouse or
branch. The price list and offer were only checked as saved; their effect on a
document was checked only for the 5 percent line discount.
