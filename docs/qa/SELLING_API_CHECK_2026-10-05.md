# Selling: checked through the API, 2026-10-05

Kept apart from `08_SELLING.md`, which is regenerated from
`docs/INDEPENDENT_TEST_CASES.md` and would drop a hand-written table.

After the purchasing build (PG-1..14) the chain was driven through the real
API on a firm of its own (`selling-paid`, schema `fx_t1005j1us_s`) and its
books read back from the database. This covers the server; the screens are
still to be walked by hand.

| Case | What was driven | Result |
| --- | --- | --- |
| TC-SELL-007, 009, 010 | Order for 12 with `WELCOME10`, approved; notes for 5 and 7 dispatched | Pass: stock 100 to 88, cost of goods sold 720.00 |
| TC-SELL-011 | Both notes billed and approved (483.21 and 676.49) | Pass: sales 982.80, output tax 176.90, receivable 1,159.70 |
| TC-SELL-013 | Receipts of 241.60 and 341.61 | Pass on the corrected figures: no TCS, advance 100.00 |
| TC-SELL-014 | Advance of 95 applied, 10 more refused; receipt reversed twice | Pass: no journal for the apply, one `-REV` for the reversal |
| TC-SELL-015 | Return of 9 refused, 2 completed | Pass: 193.28 credited, stock back to 90, inventory 5,400.00 |
| TC-SELL-016 | Credit note of 50 approved, 400 refused | Pass: 59.00 (tax 9.00) credited |
| Books | Every journal balanced; bank 341.61; receivable 565.81 against the customer's 570.81 owed less 5.00 advance | Pass |
| TC-SELL-001 | Vijaya, 12, blank discount | Pass: 2% by the price list, 1,165.65 |
| TC-SELL-002 | 18, and 12 revised to 18 | Pass: 6.75% both ways |
| TC-SELL-003 | Anand, 18 | Pass: 9.25% by his own list |
| TC-SELL-004 | Anand, 30, then a typed 0 | Pass: 7.5% by a promotion, then 0% and 2,973.60 |
| TC-SELL-005 | Send, accept, convert, convert again | Pass; the order's line reads `price_list` at 9.25, not `amount` (document corrected) |
| TC-SELL-006 | `WELCOME10`, `WELCOME10B`, `NOSUCHCODE` | Pass: 2.5%, 2.5%, back to 2% |
| TC-SELL-008 | Hold, a note refused, release | Pass: reserved stays 12, status back to Approved |
| TC-SELL-017 | Proforma raised and issued; the order then cancelled | Pass: nothing posted, the proforma unchanged |

## Cases 018 to 035

Most of these were written from the code and had never been driven. Screen
behaviour (labels, prompts, the scanner, F9) cannot be seen over HTTP and is
still to walk.

| Case | Result | What the server does |
| --- | --- | --- |
| TC-SELL-018 | Pass | Under Warn the server dispatches and records the warning; the three-button prompt is the desktop's, from `dispatch-check`. Under Block a sale with no invoice is refused, and *Dispatch and invoice* ships and bills together. Reason *Other* with no words is refused at save. |
| TC-SELL-019 | Partly | A split across two batches dispatches and prints one row per batch that add up; 6 chosen of 8 is refused at dispatch. Expiry parts not driven. Found D-SELL-50. |
| TC-SELL-020 | Differs | Preview 18.00 / 118.00; the balance rises 118.00; the invoice is offered at 1,298.00 as one row; cancelling the invoice names the debit note. **A customer debit note does print.** GST returns not driven. |
| TC-SELL-021 | Partly | 10 at 118 including GST is 1,000.00 + 180.00; the order made from it keeps the switch and the typed rate. The firm setting does not default an order on the server: the desktop reads it and sends the flag. |
| TC-SELL-022 | Partly | Defaults 30 days, Warn, Record, ticked. Below the floor is refused **at approval**, quoting the rate after the standing discount. Near-expiry parts not driven. |
| TC-SELL-023 | Partly | A counter bill needs the sales order **and** delivery note stages off. Approving draws the batches chosen. Changing the batches on a saved bill needs the line's source-document fields sent back. |
| TC-SELL-024 | Not driven | Needs batches with expiry dates. |
| TC-SELL-025 | Partly | A pinned batch is held at approval and ships; an expired one is refused at approval. An order pinned for more than the batch has left still shows the whole quantity reserved on its line -- not yet judged. |
| TC-SELL-026 | Differs | The server stores a batch's MRP and selling price and refuses a rate above the MRP, quoting the rate with tax; it does **not** fill the rate from the batch -- the desktop does. The print carries Batch, Expiry and MRP. |
| TC-SELL-027 | Partly | Two notes of one customer and branch bill together; another branch is refused, naming the field and not the note; a note naming no salesman never clashes. Supplier half not driven. |
| TC-SELL-028 | Pass | A line with no product blocks the quotation; converting creates the customer and a draft quotation; an order from it reads the enquiry WON; follow-ups and the lost report answer. |
| TC-SELL-029 | Differs | The barcode is found by `search`. Cash 100 + UPI 372 on a 472.00 bill makes two receipts, cash to the cash book and UPI through the bank. A tender total above the bill is refused **at approval**, not at save. |
| TC-SELL-030 | Pass | Both PDFs: one pick row of 12 for two notes; a loading sheet of two drops, 1,079.42, nothing to collect. |
| TC-SELL-031 | Partly | 2% inside ten days is 11.80 on 590.00 and gone on day 11; the receipt's amount includes the discount; a customer with no terms takes the firm's; 51 days overdue at 18% is 14.84. Found D-SELL-49. |
| TC-SELL-032 | Differs | A pending customer can be quoted and ordered and is refused only when billed. Single and bulk approval work; a stale row is refused by name. |
| TC-SELL-033 | Pass | Own level 70, group level 90, own beats group, no level takes the product's 84, a typed 75 stays, a price list's 65 beats the level. |
| TC-SELL-034 | Partly | A UPI ID without an @ is refused. The A4 and roll prints carry the amount still owed and drop the block once paid or on a draft. Sharing by hand not driven. |
| TC-SELL-035 | Partly | The statement PDF carries the balances, the unpaid bills with days overdue and the UPI line. Reminders and sending were blocked by D-MSG-1 and are still to drive. |

## Defects found by this check

| Id | Severity | What | State |
| --- | --- | --- | --- |
| D-SELL-47 | Medium | Loyalty points not taken back on a return or credit note | Fixed, #1146 |
| D-SELL-48 | Low | The ledger put a bill's odd paisa on the other head from the returns | Fixed, #1147 |
| D-MSG-1 | High | Every messaging route answered 503 on PostgreSQL | Fixed, #1149 |
| D-SELL-49 | Medium | *Raise interest debit note* answered with a number and wrote nothing | Fixed, #1149 |
| D-SELL-50 | High | A hand-picked batch could be dispatched below zero | Fixed, #1150 |

## Still to do

- Walk the selling screens by hand.
- Drive the expiry cases (019, 022, 023, 024, 025) on a firm with expiry
  tracking, such as the `pharma-firm` fixture.
- Re-drive the messaging halves of 034 and 035 now that D-MSG-1 is fixed.
- Decide TC-SELL-032: whether a customer waiting for approval may be quoted
  and ordered, as the server allows today.
- Judge the reservation shown on a line pinned to a short batch (025).
- GST returns for the customer debit note (020) on a GST-registered firm.
