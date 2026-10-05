# Selling: checked through the API, round 3, 2026-10-05

A third pass, after the fixes for round 2's findings were merged (#1180 to
#1194) and the backend at http://127.0.0.1:8000 was restarted on them. First
each SELLQ-1 to SELLQ-21 was driven again by its original reproduction on
fixture firms built fresh for this round; then all 87 cases TC-SELL-001 to
TC-SELL-087; then the generic checks and the books. Everything went over HTTP
as before: no database, no log file except where SELLQ-2 is about the log.
Rounds 1 and 2 (`SELLING_API_CHECK_2026-10-05.md`,
`SELLING_API_CHECK_ROUND_2_2026-10-05.md`) are left as they were.

## Fixture firms used

| Key | Fixture | Suffix / firm | Used for |
| --- | --- | --- | --- |
| I | `selling-firm` | `t1005pcjh` / `T1005PCJH-S` | SELLQ re-check (first run), the access question, returns regression (second run) |
| K | `selling-firm` | `t100571fn` / `T100571FN-S` | SELLQ re-check (second run), the access question again |
| J | `pharma-firm` | `t1005hanf` / `T1005HANF-P` | SELLQ-5, SELLQ-6, counter bills with batches |
| A | `selling-firm` | `t1005tbxw` / `T1005TBXW-S` | 001-006, 021, 028, 032, 033 |
| B | `selling-ordered` | `t10055kmq` / `T10055KMQ-S` | 007-011, 017, 018, 027, 030 |
| C | `selling-invoiced` | `t10056mng` / `T10056MNG-S` | 012, 013, 014, 034 |
| D | `selling-invoiced` | `t10058y97` / `T10058Y97-S` | 015, 016, 031, 035 |
| E | `pharma-firm` | `t1005g9sz` / `T1005G9SZ-P` | 019, 022-026; second run of SELLQ-5 |
| F | `selling-firm` | `t1005qahz` / `T1005QAHZ-S`, stages on | 036-039, 048, 054 (order half), 055-063, 073-086 |
| G | `selling-firm` | `t1005v7tg` / `T1005V7TG-S`, stages off, GSTIN 33FXSEL6257A1Z5 put on it | 029, 040-047, 049-054, 064-072, 087 |
| H | `compliance-firm` | `t10057gah` / `T10057GAH-G` | 020; returns regression (first run) |
| L | `selling-firm` | `t1005y0fv` / `T1005Y0FV-S` | generic checks |

Two fixture builds failed part-way and were built again (the first J and the
first C; see SELLQ-23). F, G, I, K and L were given the shared masters of the
cases from 036 (`-CTR`, `-SVC`, `-C03`) as in round 2. A GSTIN was put on
firms G, I and K through the fixture's platform administrator. For
TC-SELL-035 a local SMTP sink ran for 60 seconds so the email channel's Test
could pass, and stopped by itself; firm D's email channel was disabled and its
messaging switched off again afterwards. The server never had to be
restarted.

## SELLQ-1 to SELLQ-21 driven again

Fixed = the original reproduction now gives what was expected. Each was run on
two fresh firms (I and K, or J for the pharmacy ones) with the same answers.

| Id | Ledger id | Result | What it does now (firm I `t1005pcjh` / `T1005PCJH-S` unless said) |
| --- | --- | --- | --- |
| SELLQ-1 | D-SELL-57 | **Fixed** | Setting on: a Field Sales user's `POST /customers` is 201, status PENDING; the same user is 403 on approving it, on setting it ACTIVE, on editing and on deleting it. `SALES_EXECUTIVE` now lists `CUSTOMER_CREATE` and `CUSTOMER_VIEW` (13 codes). See *The access question* below for what else the create accepts |
| SELLQ-2 | D-RPT-21 | **Fixed** | `backend/uvicorn-run.log` shows three `POST /firms/{id}/provision` completed at 21:01:42, 21:03:10 and 21:04:43 and request lines after each (the last read at 21:05:16); `backend/logs/server/server-2026-10-05.log` gains the same lines |
| SELLQ-3 | D-SELL-64 | **Fixed** | A bill with no due date: "Please find attached invoice SI-26-27-000001 dated 05-Oct-2026 for 118.00." with no "due on" clause |
| SELLQ-4 | D-SELL-69 | **Fixed** | A product line on the edit of a saved counter bill: 422 "SI-26-27-000018 is already saved, so it is changed through the lines it has: send each line back with its source_document_type, source_document_id and source_document_line_id, as the bill returns them, and no product_id. A product cannot be added to a saved bill, nor a line raised above the quantity it was saved for; cancel this draft and raise the bill again." |
| SELLQ-5 | D-SELL-58 | **Not fixed** (half) | J and E: approval now reserves the batch the customer can take (8 on M9, none on M4), and with nothing else waiting the note ships M9. The original reproduction still fails: with a second, ordinary order of 10 holding M4, the first order's untouched note is 422 "Insufficient available stock to dispatch: short by 6.0000. Too short-dated for this customer's minimum shelf life…" although its own 8 are reserved on M9; the picker shows M4 "available to line 8" and offers only 2 of M9. It ships once the other order has gone. Dispatch still credits a line's own reservation to the earliest batches (`app/inventory/services/inventory_service.py:3406` `allocate_for_dispatch`, `app/batch_serial/services/batch_serial_service.py:897`). A draft counter bill that chose a batch now reserves that batch (4 on L); editing its picks to 1 + 3 leaves the 4 on L until approval, which ships 1 and 3 |
| SELLQ-6 | D-SELL-60 | **Fixed** | J: 12 ordered pinned to a batch holding 10 is on the report with a back order of 2; an order of 4 of a product whose only stock is expired is on it with 4 (available 0.0000). The 2 still sit as reserved on a batchless stock row with available -2 |
| SELLQ-7 | D-IDN-12 | **Fixed** | `GET /roles/{id}/permissions` answers 200 for FIRM_ADMIN (207 ids) and FIRM_MANAGER (190) |
| SELLQ-8 | D-SELL-61 | **Fixed** | On a firm with a GSTIN every row reads "Tamil Nadu (33)": bills, credit and debit notes, returns, an unregistered buyer's bill and a walk-in bill. On a firm with **no** GSTIN an unregistered buyer's rows are still blank (there is no state to print), a registered buyer's rows read "Tamil Nadu (33)" on all four kinds |
| SELLQ-9 | D-SELL-68 | **Fixed** | "blue dart" and "Blue Dart " after "Blue Dart": 409 "There is already a transporter Blue Dart."; renaming another carrier onto it 409; changing only the case of its own name saves. ("BLUE  DART" with two spaces is taken as a different name.) |
| SELLQ-10 | D-SELL-65 | **Fixed** | Walk-in print: BILLED TO and SHIPPED TO both read the buyer typed and the phone; "Cash sale" is nowhere on the page |
| SELLQ-11 | D-SELL-66 | **Fixed** | Walk-in bill of 118.00 with 200 tendered: 422 "200.00 was received against a bill of 118.00. Enter what the bill is paid with; change is handed back."; with 100 tendered the "Take the rest…" message, as it should |
| SELLQ-12 | D-SELL-59 | **Not fixed, as said** | Unchanged: quantity 3 to 4 on a saved counter bill is 422 "Invoice quantity exceeds the available source quantity."; only the wording for a product line changed (SELLQ-4). **Cutting the bill down is where a new defect sits: SELLQ-22** |
| SELLQ-13 | D-SELL-67 | **Fixed** | Shift opened 21:04:04 +05:30; the report prints "05-10-2026 15:34 UTC" |
| SELLQ-14 | D-SELL-56 | **Fixed** | A promise of 500 taken after a same-day receipt of 500: `received_amount` 0.00, PENDING; a later receipt of 300 shows 300.00 PENDING, 200 more KEPT; reversing the 200 returns it to PENDING. A promise on the account behaves the same. See SELLQ-24 for a receipt dated before the promise |
| SELLQ-15 | D-SELL-62 | **Fixed** | Withdrawing a KEPT promise: 422 "That promise was kept: the money promised was received, so there is nothing to withdraw."; once a reversal makes it PENDING again it withdraws |
| SELLQ-16 | D-SELL-53 | **Fixed** | Quantity 0 with nothing free is 422 on an order line ("Line 1 orders a quantity of 0 and supplies nothing free. Type a quantity, or leave the line off the order."), a note line, a bill line on POST and on PUT, a counter bill and a quotation. A bill at 100% discount (`SI-26-27-000006`, 0.0000) approves: no journal for the bill, no receivable row, the customer's balance unchanged, the note's cost entry Dr 5200 60.00 / Cr 1200 60.00 stands, stock 482 to 481, the note leaves the billable list, the register row is 0.00 / 0.00 / 0.00; cancelling the bill puts the note back on the billable list. An order of 0 + 2 free approves, its note ships the 2 and its bill of 0.0000 approves. Counter: 100% bill approves and ships; a bill of free goods only (0 + 2 free) reserves 2, approves, and ships 2 with cost 120.00 |
| SELLQ-17 | D-SELL-54 | **Fixed** | Draft counter bill of 7 DET: reserved 7; cancel: reserved 0, bill, note and order `SO-2026-2027-000013` all CANCELLED, ledger `RESERVE` 7 then `UNRESERVE` 7. Held then cancelled: reserved 0. A draft for 100,000: refused at approval, cancelled, reserved back to 0 and the next counter bill approves. At the end of the counter run reserved was 0 on both products and no draft was left |
| SELLQ-18 | D-SELL-55 | **Fixed** | (a) 5 back against an unbilled note: line `unbilled_quantity` 5, only `SR-…-COST` (Dr 1200 300.00 / Cr 5200 300.00), no receivable row, no advance, stock 474 to 479, the note off the billable list and a bill of 5 or of 1 off it refused "5.0000 of the 5.0000 delivered came back before being billed, so 0.0000 is left to bill."; cancelling the return reverses the cost entry, clears `unbilled_quantity` and makes the note billable for 5 again. (b) 4 delivered, 3 billed, 2 back: `unbilled_quantity` 1, credited 118.00 (Dr 4100 100.00 / Dr 2220 9.00 / Dr 2230 9.00 / Cr 1100 118.00), cost for both units 120.00, loyalty -2.36 of 7.08. (c) a draft bill of 5 waiting while 2 come back: approval 422 "…line 1: 2.0000 of the 5.0000 delivered came back before being billed, so 3.0000 is left to bill. Change the bill to what the customer kept."; cut to 3 it approves (354.00). (d) fully billed, 2 back against the note: credited 236.00 in full. (e) bill cancelled, 5 back against the note: stock and cost only |
| SELLQ-19 | D-SELL-63 | **Fixed** | `GET /enquiries?page_size=1000` 422; default 25 with `pagination`; page 2 of size 2 returns the third row. `GET /enquiries/follow-ups-due` is still one unpaged list (`page_size=1000` answers 200 with no `pagination`) |
| SELLQ-20 | D-SELL-70 | **Fixed** | `valid_until` before the proforma's date: 422 "valid_until cannot be earlier than the proforma date." on create and on update; the same day is accepted |
| SELLQ-21 | D-SELL-71 | **Fixed** | 422 "Line 1: warehouse 00000000-0000-0000-0000-000000000001 was not found in this branch." |

### The access question: what a Field Sales user's new customer may carry

Driven on firm I and again on firm K as a Field Sales user (`SALES_EXECUTIVE`),
*New outlets need approval* **off**. Every customer below was saved **ACTIVE**
at once.

| Typed on the create | Answer | What was stored and posted |
| --- | --- | --- |
| nothing extra | 201 | ACTIVE, credit limit 0, no balance |
| `credit_limit` 50000 | 201 | `credit_limit` 50000; `credit-status` then reads limit 50,000.00, available 48,500.00 |
| `opening_balance` 1500 | 201 | `current_outstanding` 1,500.00 at once. **A journal is posted**: `<code>-OB` "Opening balance", Dr 1100 Trade Receivables 1,500.00 / Cr 3000 Opening Balance Equity 1,500.00, and a receivable row OPENING_BALANCE 1,500.00 (reference type CUSTOMER_MASTER). No opening **bill** is made, so the 1,500.00 is on no list a receipt or a collector works from: `receipts/outstanding`, the collection sheet and `customers/ageing` have no row for it |
| a GSTIN | 201 | stored |
| `payment_terms_days` 90 | 201 | stored |
| cash discount 5% in 30 days | 201 | stored |
| a customer group (*Wholesaler*, which carries a 3.25% group discount) | 201 | stored |
| `default_discount_percent` 12.5 | **403** | "…giving a customer a standing discount needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS). Leave it at zero, or ask somebody who holds it." |
| credit limit 50000 **and** opening balance 1500 | 201 | both, with the journal above |

Afterwards the same user is 403 on raising the limit (no `CUSTOMER_UPDATE`)
and on adding an opening bill, and may raise an order for the customer. With
the setting **on** the same create is accepted the same way (limit 50,000,
opening balance 1,500 and its journal) and the customer starts PENDING. The
books stay balanced (1100 equals what customers owe). For the owner to decide:
whether a salesman's new outlet may carry a credit limit, an opening balance
that posts to the ledger, credit days and cash-discount terms, when the one
thing held back from him is the standing discount.

## Cases 001 to 035

Results are of the server half; where round 2 said *screen, not driven* that
still holds and is listed at the end. "As round 2" means the same answers and
figures, read again on this round's firm.

| Case | What was driven, with the data | Result |
| --- | --- | --- |
| TC-SELL-001 to 004 | A: `QT-2026-2027-000001` to `…000004` | **Pass**, as round 2: 2% (1,165.6512), 6.75% both ways (1,663.7292), 9.25% (1,619.1252), 7.5% by a promotion (2,750.58) then a typed 0 (2,973.60) |
| TC-SELL-005 | A: `QT-…000005` to `SO-2026-2027-000001` | **Pass**: DRAFT order, `price_list` 9.25; second convert 422 "…already became SO-2026-2027-000001." |
| TC-SELL-006 | A: `SO-…000002` with `WELCOME10`, `WELCOME10B`, `NOSUCHCODE` | **Pass**: 2.5, 2.5, 2.0; the code typed is kept |
| TC-SELL-007 | B: the fixture's `SO-2026-2027-000001` | **Pass**: 100 / 12 / 88; claim WELCOME / WELCOME10 CLAIMED 25.20; no journal |
| TC-SELL-008 | B: hold, a note, release | **Pass**: refusal word for word; reserved stays 12; history CREATED, APPROVED, HELD, RELEASED |
| TC-SELL-009 | B: `DN-26-27-000001` (5), `DN-26-27-000002` (7) | **Pass**: PARTIALLY_DELIVERED 95 / 7, cost 300.00; DELIVERED 88 / 0, cost 420.00 |
| TC-SELL-010 | B | **Pass**: note line 84, 2.5%, 483.21 |
| TC-SELL-011 | B: `SI-26-27-000001` | **Pass against the corrected text**: 6 refused; Dr 1100 483.21 / Cr 4000 409.50 / Cr 2220 36.86 / Cr 2230 36.85; loyalty 9.66 earned |
| TC-SELL-012 | C: `SI-26-27-000001` | **Pass**: two labelled copies, CGST / SGST, HSN, amount in words; Read Only 403 on the template |
| TC-SELL-013 | C: `RC-2026-2027-000001` 241.60, `…000002` 341.61 | **Pass**: no TCS and the reason; 241.61 then 0.00 with advance 100.00; Dr 1010 / Cr 1100 |
| TC-SELL-014 | C: `SI-26-27-000003` (676.494) | **Pass**: 581.49 / 5.00 with no journal; "…has only 5.00 left unapplied."; reversal to 823.09; second reverse refused |
| TC-SELL-015 | D: `SR-26-27-000001` (2 of the bill of 5), cancelled, a second return completed | **Pass**: 9 refused; 193.28 credited (Dr 4100 163.80 / Dr 2220 14.74 / Dr 2230 14.74 / Cr 1100 193.28), cost 120.00, loyalty -3.8657; the cancel puts stock, receivable, three journals and the points back. A return against a **bill** is unchanged by the fix (`unbilled_quantity` 0) |
| TC-SELL-016 | D: `CN-26-27-000001` | **Pass**: 59.00 (tax 9.00); 400 refused; cancel reverses it and the 1.18 points |
| TC-SELL-017 | B: `PF-2026-2027-000001`; `SO-…000002` with `PF-…000002`, cancelled | **Pass**: nothing posted; the proforma unchanged; `UNRESERVE` 12; claim REVERSED |
| TC-SELL-018 | B: notes `DN-26-27-000003` to `…000007` under Block | **Partly**: Block refuses a Sale; "Dispatched and invoiced as SI-26-27-000002." (198.24); below the floor nothing is dispatched; *Other* needs words; route sale refused once the switch is on. The Warn half and its audit row were not driven again this round |
| TC-SELL-019 | E: `T1005G9SZ-P19`, batches X / N / L | **Pass**, as round 2: FEFO ships N; 8 on L ships L with `delivery_note.fefo_skipped`; 5 + 3 ships both; 4 + 2 refused at dispatch; an expired batch saves on a **delivery note** draft and is refused at dispatch. An ordinary customer's reservation is FEFO as before (J: 12 ordered reserves N 10 + L 2 and ships them) |
| TC-SELL-020 | H: `SI-26-27-000004`, `SDN-26-27-000001` | **Pass, in full**, as round 2: 18.00 / 118.00; Sales Manager 403 on approve; 1,298.00 as one row; CDNR type D; both cancel refusals; print |
| TC-SELL-021 | A: `QT-…000006` to `SO-…000003` | **Pass**: 118 typed, 100 stored, 1,180.00; the order keeps the switch; the firm setting does not default an order on the server |
| TC-SELL-022 | E: `T1005G9SZ-P22` | **Pass**, as round 2, (a) to (e) |
| TC-SELL-023 | E: `T1005G9SZ-P23`, counter bills `SI-26-27-000001`, `…000002`; J: `T1005HANF-R23` | **Pass, changed by the fixes**: a draft bill that chose L now shows the 4 reserved **on L**; approving ships L (`delivery_note.fefo_skipped`); an untouched bill ships N. Editing the picks (J: 1 N + 3 L, sent by source line) saves and approval ships 1 and 3. A product line on the edit gets the new wording (SELLQ-4). On J a counter bill choosing an **expired** batch is now refused at save: 422 "Line 1: the batch the customer asked for, T1005HANF-R23-X, has expired."; picks adding to 1 of 2 save and are refused at approval |
| TC-SELL-024 | E: `T1005G9SZ-P24`, customer with 180 days | **Pass**: approval now reserves M9 (8), not M4; (a) ships M9; (b) picker marks M4 short; (c) refused, a reason does not help; (d) under Warn it dispatches with `delivery_note.short_shelf_life_dispatched` |
| TC-SELL-025 | E: `T1005G9SZ-P25` | **Pass**: 5 pinned to L held on L and shipped; 12 pinned with 5 left approves, and (J) the shortfall is now on the back-order report; pinning X refused by name |
| TC-SELL-026 | E: `T1005G9SZ-P26`, B1 120 / 95, B2 100 | **Differs**, as before: the server does not fill a blank rate from the batch (100, not 95); MRP column printed; B2 at 110 refused "charges 123.20 a unit with tax, above the MRP of 100.00…" |
| TC-SELL-027 | B: `SI-26-27-000003`, `…000004` | **Partly**, as round 2: two notes on one draft (594.72); another salesman's note 422; a note naming nobody accepted; branch clash and supplier half not driven |
| TC-SELL-028 | A: `ENQ-2026-2027-000001` to `…000003` | **Pass**: as round 2; the list is now paged |
| TC-SELL-029 | G: barcode 8901234567890; `SI-26-27-000029` (472.00), Cash 100 + UPI 372; `…000030` with 600 | **Pass**: two receipts, cash and bank; 600 refused at approval "…change is handed back."; cancelling that draft now cancels its order too (`SO-2026-2027-000030` CANCELLED) |
| TC-SELL-030 | B | **Pass**: both PDFs; an empty list 422; Accounts 403 |
| TC-SELL-031 | D: `SI-26-27-000002`, `…000005`, `SDN-26-27-000001` | **Pass**, as round 2: 9.66 until day 10; Dr 1010 473.55 / Dr 5300 9.66 / Cr 1100 483.21; firm terms for a customer with none; 12.46 of interest; draft interest debit note; Field Sales 403 |
| TC-SELL-032 | A: Field Sales user; `T1005TBXW-M01` to `-M03` | **Pass** (was Fail): the Field Sales user's customer is saved PENDING; the filter finds it; quotation and order accepted; the user is 403 on setting it ACTIVE and on approving; billing 422 with the case's words; single and bulk approve; then it bills (`SI-26-27-000001`); with the setting off the next one starts ACTIVE |
| TC-SELL-033 | A: levels DEALER / RETAIL, `RATE65` | **Pass**, as round 2 |
| TC-SELL-034 | C | **Pass**: UPI ID rule; unpaid prints ask 483.21, part paid 241.61, paid / draft / cancelled none; shared-by-hand timeline row; the covering note has no "due on ." now |
| TC-SELL-035 | D: Anand, 945.36 owed | **Partly**, as round 2: Remind and the five Sends queue (QUEUED); refusals for a customer who owes nothing, *No reminders*, a reversed receipt, a cancelled quotation; the worker sending and a purchase order not driven |

## Cases 036 to 087

| Case | What was driven, with the data | Result |
| --- | --- | --- |
| TC-SELL-036 to 039 | F: `SI-26-27-000001` (1,180.00), draft `…000002`, `CN-26-27-000001`, `SDN-26-27-000001`, `SR-26-27-000001`, `SI-26-27-000003` (DET) | **Pass**, as round 2: the register rows and their sum 750.00; HSN 3402 8 / 750 and the blank-HSN row 5 / 420; Read Only 200, Warehouse 403. Every row of a registered buyer now prints "Tamil Nadu (33)". GSTR-1 still needs a GSTIN on the firm (422 without) |
| TC-SELL-040 | G: walk-in `SI-26-27-000001`, Ramesh | **Pass** (the print is right now): BILLED TO and SHIPPED TO name Ramesh, "Cash sale" is not on the page; receipt `RC-2026-2027-000001` Dr 1000 Cash 1,180.00 / Cr 1100; note cost 600.00; stock 500 to 490 |
| TC-SELL-041 | G: `SI-26-27-000002` | **Pass**: 500 and 0 refused at approval, 1,180 approves |
| TC-SELL-042 | G: `SI-26-27-000003` | **Pass**: Cash 680 + UPI 500, two receipts; 680 + 400 refused naming 1080.00; 700 + 500 now "1200.00 was received against a bill of 1180.00. Enter what the bill is paid with; change is handed back." |
| TC-SELL-043, 044 | G | **Pass**: refusals word for word |
| TC-SELL-045 | G: `SI-26-27-000006`, `…000007` | **Pass**: Vijaya 23.6 points, none for *Cash sale*; both register rows have a blank GSTIN and place of supply "Tamil Nadu (33)" |
| TC-SELL-046, 047, 049 | G: `SI-26-27-000008` to `…000011`, `SR-26-27-000001` | **Pass**, as round 2: 590.00 with no stock and no cost; 826.00 with cost 120.00 for the goods; the service return credits 590.00 and moves nothing |
| TC-SELL-048 | F: `DN-26-27-000004`, `SI-26-27-000004` | **Pass**: 1,770.00; no reservation, no ledger row, no cost entry |
| TC-SELL-050 to 054 | G: `SI-26-27-000012` to `…000015`, `CN-26-27-000001`; F: an order sent `charges` | **Pass**, as round 2: 1,298.00 with Cr 4050 100.00; 1,253.60; draft 1,338.00 then 1,416.00; register 1,100.00; the bill owes 118.00 after the line is credited; an order takes no charges |
| TC-SELL-055 | F | **Pass**: "speedy carriers " is now 409 "There is already a transporter Speedy Carriers." |
| TC-SELL-056 to 059 | F: `DN-26-27-000005` and a second note | **Pass**, as round 2 |
| TC-SELL-060, 062, 063 | F | **Pass**, as round 2 |
| TC-SELL-061 | F | **Differs** on one message, as round 2: "The file is larger than 10 MB, the most it may be." |
| TC-SELL-064 | G: `SI-26-27-000016` | **Differs / SELLQ-12**, unchanged: hold, recall, 4 refused, 3 approves (354.00) |
| TC-SELL-065 | G: `SI-26-27-000017`, `…000018` | **Pass**: and cancelling the held draft now gives its stock back (reserved 32 to 30) |
| TC-SELL-066 | G | **Pass** |
| TC-SELL-067 | G: `SHIFT-000001`, `SHIFT-000002` | **Differs** (path only, `POST /counter-shifts/open`), otherwise as the case says |
| TC-SELL-068, 087 | G: `SI-26-27-000020` to `…000022`; `SHIFT-000003`, `SHIFT-000004` | **Pass**: cashier 2 bills / 2,360.00, manager 0 / 200.00; then 1 bill / 1,380.00 and 1 bill / 1,680.00 |
| TC-SELL-069 to 072 | G: `SHIFT-000005` to `SHIFT-000011` | **Pass**: short 10.00 Dr 6960 / Cr 1000; over 5.00 the other way; exact posts nothing; Field Sales 403 on the manager's shift; a held bill does not stop the close. The report prints real UTC |
| TC-SELL-073 to 075 | F: `SI-26-27-000006`, `…000007` | **Pass**, as round 2 |
| TC-SELL-076 | F: `SI-26-27-000008` | **Partly**, as round 2: the next day only through `as_of` |
| TC-SELL-077 | F | **Pass**: the five refusals; a promise on the account taken after the day's receipts is PENDING now |
| TC-SELL-078 | F: `SI-26-27-000012`, `…000013` | **Pass**: and a KEPT promise is now refused over HTTP too (422 "That promise was kept: the money promised was received, so there is nothing to withdraw.") |
| TC-SELL-079 | F | **Pass** |
| TC-SELL-080 to 086 | F: `TR-1`, `TR-NOW`, `TW-1`, `TR-GRP`, `TR-LOW`; bills `SI-26-27-000014`, `…000015`, `…000019`; `PA-2026-2027-000001` | **Pass**, as round 2: 1,000 / 10.00 then 5,000 / 100.00; `CREBATE-TR-1` 100.00 dated 2026-09-30; 60 settled, 40 left, 50 refused; reverse blocked until the adjustment is cancelled, then `-REV` and `CREBATE-TR-1-2` (110.00); the overlap, group and code refusals; group 5,000 / 100.00 with 70 off C06; the three roles |

**Counts:** 87 cases, none left undriven. **Pass 79**, **Differs 4** (026,
061, 064, 067), **Partly 4** (018, 027, 035, 076), **Fail 0**. 032 and 040
pass now; 011, 015 and 016 pass against the corrected journals.

## Regression checks asked for

**Sales returns in every flavour, and the readers afterwards.** Driven on H
(a new product at 100, HSN 330511, one registered and one unregistered
customer made for it) and again on I. Same figures on both.

| Flavour | Documents on H | What posted |
| --- | --- | --- |
| A: billed, 2 of 10 back against the bill | `SI-26-27-000005`, `SR-26-27-000001` | credited 236.00: Dr 4100 200.00 / Dr 2220 18.00 / Dr 2230 18.00 / Cr 1100 236.00; cost entry |
| B: 4 delivered, 3 billed, 2 back against the note | `SI-26-27-000006`, `SR-26-27-000002` | `unbilled_quantity` 1; credited 118.00 for the one billed unit; cost for both |
| C: 5 delivered, never billed, 5 back | `SR-26-27-000003` | cost entry only; `unbilled_quantity` 5 |
| D: bill of 5 cancelled, 5 back against the note | `SR-26-27-000004` | cost entry only |
| E: bill of 6, 3 back, the return then cancelled | `SI-26-27-000008`, `SR-26-27-000005` | credit and cost journals and both `-REV` |
| F: bill of 10 with a credit note of 50 and a return of 1 | `SI-26-27-000009`, `CN-26-27-000001`, `SR-26-27-000006` | 59.00 and 118.00 credited |
| Unregistered: 3 delivered unbilled, 1 back; bill of 4, 1 back | `SR-26-27-000007`, `SI-26-27-000010`, `SR-26-27-000008` | nothing; then 118.00 credited |

| Reader | Expected | Read |
| --- | --- | --- |
| Customer balances | 2,891.00 (2,450 + 18%) and 354.00 | 2,891.00 and 354.00, no advance |
| GSTR-1 B2B | 1,000 / 300 / 600 / 1,000 | the same four bills |
| GSTR-1 CDNR | 50, 200, 100, 100; nothing for C and D | the same; C, D and the cancelled E absent |
| GSTR-1 B2CS (change) | +300 | +300 |
| GSTR-1 HSN (change) | quantity 28, taxable 2,750 | 28 and 2,750 |
| GSTR-3B 3.1(a) (change), credit notes deducted | +2,750 / tax 247.50 a head; +550 / +99 | the same (the second firm's JSON reads 247.49999999999997) |
| GST sales register | sum 2,750.00; no row for C, D, the unbilled unregistered return or the cancelled E | the same; B's row is -100.00 |
| Sales analysis by customer | net of returns 2,450.00 / 25 and 300.00 / 3; gross 2,900.00 / 29 and 400.00 / 4 | the same |
| Customer rebate turnover | invoiced 2,900, returned 400, credit notes 50, turnover 2,450 | the same |
| Stock | 100 less 30 | 70, reserved 0 |
| Loyalty (firm I) | taken back only where a bill was credited | A, B, E, F and the billed unregistered return; none for C, D or the unbilled one |
| Books | 1100 equals what customers owe | 5,369.00 both (H); 9,603.54 both (I) |

Two readers were **not** changed and disagree with the rest: SELLQ-25 and
SELLQ-26 below.

**Counter bills.** Draft, hold, recall, cancel a draft, cancel a held draft,
cancel an approved bill, a draft for more than the stock, 100% discount, free
goods only (ships its 2 with cost 120.00), batches chosen, an expired batch
(refused at save), picks short of the line (refused at approval): driven on
I, K, G and J. Reserved stock came back to 0 at the end of each run, except
where a draft or an approved order was deliberately left (G: three drafts of
10; L: two over-tendered drafts of 1 and one approved order of 1), and each of
those was accounted for. The one exception is new: **SELLQ-22**, a draft cut
down before approval.

**Ordinary orders.** With no shelf-life customer the reservation is first
expiry first as before (J: 12 reserves N 10 and L 2; E: cases 019 and 025
unchanged).

**Zero-total bills and the note's billing status.** A bill of 0.0000 approves;
its note leaves `GET /sales-invoices/billable`; cancelling the bill puts the
note back; the note's own `status` stays DISPATCHED throughout (it carries no
billing status of its own; the billable list is what says).

**Promises.** 073 to 079 and the SELLQ-14 / 15 sequences on I and K; one new
low finding, SELLQ-24.

## Generic checks

Run in full on firm L (fresh, stages on; the counter bill with stages off).
The table of round 2 stands with these changes; every other cell read the same.

| Check | Round 2 | Now |
| --- | --- | --- |
| Quantity 0: sales order | 201, and approved | 422 "Line 1 orders a quantity of 0 and supplies nothing free…" |
| Quantity 0: delivery note | 201, and dispatched | 422 "…delivers a quantity of 0 and supplies nothing free…" |
| Quantity 0: sales invoice | 200 on edit, 500 at approval | 422 on create and on edit |
| Quantity 0: counter bill | 500 on save | 422 |
| A bill at 100% discount (counter and off a note) | 500 at approval | approves; no receivable row, no journal for the bill |
| Unknown warehouse on a counter bill | 409 | 422 naming the line and the warehouse |
| `page_size=1000` on enquiries | 200, no pages | 422 |
| Proforma `valid_until` before its date | 201 | 422 |
| Cancel a draft counter bill for more than the stock | reservation left for ever | reserved back to what it was (469 / 3 before and after) |
| Cancel an approved counter bill | receivable and journals back, stock stays out | the same: 1,376.20 to 1,612.20 and back; the 2 units stay out and the note stays DISPATCHED and billable (a return against it now moves stock and cost only) |

Unchanged and read again: 403 for the Warehouse, Read Only, Field Sales,
Counter Sales and Sales Manager checks; 409 on a stale `If-Match` for every
document with an update route; `status` in the update body 422 (ignored on a
proforma); 6 off a note of 5, 600 dispatched with 500 on hand, returns and
credit notes above their source, receipts above the money or the bill: 422;
cancel of an approved bill, a completed return, an approved credit or debit
note and a receipt put the receivable back to the paisa.

**Books, firms A to L.** The trial balance balances in every one (for example
F Dr 60,113.63 / Cr 60,113.63; G 2,841,444.19 both sides; I 54,147.84; K
44,287.94; L 38,162.08); 1100 Trade Receivables equals customers' outstanding
less advances in every one (C: 818.09 = 823.09 - 5.00); the stock valuation
report's difference against 1200 Inventory is 0.00 in every one; no journal is
unbalanced. Round 2's negative receivable (advances made by SELLQ-18) does not
recur. No new 500 was recorded by `/diagnostics/errors` for a selling route in
this round.

## New defects

Ids continue from round 2. Each was reproduced on two fresh firms unless the
row says otherwise.

| Id | Severity | What | Reproduction (trimmed) | Expected / actual | Suspected cause |
| --- | --- | --- | --- | --- | --- |
| SELLQ-22 | **High** | A saved counter bill cut down before approval ships the quantity it was first saved for | I, K (stages off): DET 100 on hand. `POST /sales-invoices` 3 DET for C03 (draft `SI-26-27-000022`, 297.36; reserved 3). `PUT` the line back by its source fields with `current_invoice_quantity` "2" → 200, total 198.24, reserved still 3. `POST …/approve` → APPROVED 198.24; **on hand 97**; ledger `DISPATCH` 3 on `DN-26-27-000023`; cost journal Dr 5200 180.00 / Cr 1200 180.00; the bill's journal Dr 1100 198.24. The hidden note delivers 3, its order reads DELIVERED for 3, and the note sits on the billable list with 1 left | Expected: two units leave, or the edit is refused. Actual: three leave and two are charged; the third is out of stock at cost with nobody billed, on a note no screen of a counter firm offers. Cutting down is the only change a saved counter bill takes (SELLQ-12), and the new SELLQ-4 message points the user to it | `app/sales_invoice/services/sales_invoice_service.py:770-808` `update_invoice` restates serials and batches on the bill's own note (`_restate_own_serials`, `_restate_own_batches`) but not the quantity; `_ship_on_approval` (`:1988`) dispatches the note as first raised |
| SELLQ-23 | **High**, outside selling | Provisioning one firm runs DDL on every other firm's tables, so requests in other firms deadlock while it runs | Seen twice in this round, both while another agent was provisioning fixture firms at the same moment. (1) `POST /firms/{id}/provision` for `fx_t100520lt_p` → 422 "Migrating tenant storage … failed: deadlock detected … [SQL: ALTER TABLE "fx_t100517ld_g".products DROP CONSTRAINT IF EXISTS "FK_products_tax_profile"]": the migration of one schema was altering another firm's table. (2) An ordinary `POST /sales-invoices` in `fx_t1005rwyh_s` → **503** "The database is temporarily unavailable."; the log shows `DeadlockDetected` on `SELECT fx_t1005rwyh_s.products.code`, blocked by a process waiting for an AccessExclusiveLock. Connection resets (WinError 10054) on plain GETs came at the same times, as in round 2 | Expected: provisioning a firm touches that firm's store only. Actual: every provision re-runs schema changes across all firms' stores, takes exclusive locks on their tables, and can fail itself or fail other firms' requests. Not reproducible on demand (a race); the cause is in the code | `backend/alembic/versions/20260807_0038_tax_profile_group_code.py:30-47` (`_firm_schemas` lists every schema holding `tax_systems`) and `:112-118` (the `ALTER TABLE` run on each) |
| SELLQ-5 (still open) | Medium | The reservation is on the right batch; dispatch still refuses the first order while another order holds the earlier batch | E, J: see the re-check table | as there | `app/inventory/services/inventory_service.py:3406`; `app/batch_serial/services/batch_serial_service.py:897` |
| SELLQ-24 | Low | A receipt entered after the promise but dated before the day it was recorded does not count toward it | I, K: bill of 118.00; promise of 118 for three days on; then `POST /receipts` dated **yesterday**, 118 applied to the bill → the bill owes nothing and the promise reads `received_amount` 0.00, PENDING (it will read Broken on its day) | Expected: money recorded after the promise for the bill it names keeps it. Actual: the date window still excludes it | `app/collections/services/promises.py:79` (`settlement_date >= recorded_on`, kept beside the new `created_at` test) |
| SELLQ-25 | Low | The sales return reports value a return before billing at full price | H, I: `GET /sales-returns/reports/by-customer` gives the registered customer `return_amount` 1,770.00 over 5 returns where 472.00 was credited; `…/by-product` 2,006.00; `/sales-returns/summary` `total_return_value` 2,006.00; the register lists C and D at 590.0000 each with no column for what was credited | Expected: the reports say what was credited, or carry both figures, as the GST register, the analysis and the rebate now do | `app/sales_return/services/sales_return_service.py:321` (`summary`), `:2490`, `:2535-2605` |
| SELLQ-26 | Low | A return raised against a delivery note names no bill in the GST register or in GSTR-1 CDNR, though it credits one | H, I: flavour B (`SR-26-27-000002`): register `against_invoice_number` blank, CDNR `against_invoice` "" with taxable 100.00; returns raised against a bill carry the number | Expected: the bill whose unit was credited (`SI-26-27-000006`) | `app/sales_invoice/services/gst_sales_register.py:513`, `app/gst_returns/services/gstr_service.py:1923` |

Smaller things seen and not given an id: `GET /enquiries/follow-ups-due` is
still unpaged; GSTR-3B returns floats (247.49999999999997); the sales analysis
prints a netted quantity as "25.00000000000000000000"; editing the batch picks
of a draft counter bill leaves the reservation on the batches first chosen
until approval; an opening balance typed on a customer makes no opening bill,
so it is on no outstanding list (see the access question).

## Case-text corrections needed (as they stand after the fixes)

Changes to `docs/INDEPENDENT_TEST_CASES.md`. Dropped from round 2's list
because the fixes made the text right again: TC-SELL-032 (Field Sales adds the
customer) and TC-SELL-040 (the print names the buyer).

| Case | Now reads | Should read |
| --- | --- | --- |
| TC-SELL-011 | "Cr **Sales 409.50**, Cr **Output Tax 73.71** — one tax line…"; Data "Cr 4000 409.50 / Cr 2200 73.71"; "No loyalty points arrive (D-SELL-1)." | "Cr **4000 Sales 409.50**, Cr **2220 Output CGST 36.86**, Cr **2230 Output SGST 36.85**"; and "The bill earns 9.66 loyalty points (`LOY-SI-…`, Dr 5700 / Cr 2600)." |
| TC-SELL-015 | "(Dr 4100 163.80 / Dr 2200 29.48 / Cr 1100 193.28)" | "(Dr 4100 163.80 / Dr 2220 14.74 / Dr 2230 14.74 / Cr 1100 193.28)". Add: "A return against a delivery note nobody was billed for moves stock and cost only: no `SR-…` credit journal, no receivable row, `unbilled_quantity` on the line, and the note's left-to-bill reduced. On a part-billed note the unbilled part is taken first (4 delivered, 3 billed, 2 back: 1 credited)." |
| TC-SELL-016 | "Dr 4100 50.00 / Dr 2200 9.00 / Cr 1100 59.00" | "Dr 4100 50.00 / Dr 2220 4.50 / Dr 2230 4.50 / Cr 1100 59.00" |
| TC-SELL-019 | "(b) type 8 against the *later* batch and 0 against the earlier"; last sentence "The near-expiry window is a fixed 30 days and no setting yet asks for a reason on a skip." | "(b) type 8 against the *later* batch and clear the earlier". Delete the last sentence. Add: "Approving the order reserves by batch: first expiry first, or the batch a customer's minimum shelf life allows." |
| TC-SELL-020 | fixture `selling-invoiced`; the header says the GST returns are not driven | fixture `compliance-firm`; driven in full |
| TC-SELL-023 | "The saved draft shows 4 on the later batch." | add "and Stock > Batches shows the 4 reserved on the later batch. A counter bill that picks an expired batch is refused when it is saved: 'Line 1: the batch the customer asked for, … has expired.'"; and say how an API client edits the picks (source fields, no `product_id`) |
| TC-SELL-024 | (a) "ships the **9-month** batch -- the 4-month one is passed over without anybody choosing" | add "Stock > Batches shows the order's 8 reserved on the 9-month batch from approval." Until SELLQ-5 is closed, also: "with no other order waiting on the product". |
| TC-SELL-025 | "The order for 12 holds 10 of the later batch and leaves 2 as a back order" | add "and Reports > Back orders lists the order with 2." |
| TC-SELL-026 | "Choosing B1 fills the rate **95**." | "Choosing B1 fills the rate **95** on the screen; the server does not fill a blank rate from the batch." |
| TC-SELL-034 | "Vijaya, who has a phone number" | "Vijaya, given a phone number for this case" |
| TC-SELL-037, 038, 053 | the GSTR-1 comparisons | add "(GSTR-1 answers only for a firm with a GST number: put one on the fixture firm, or use `compliance-firm`)" |
| TC-SELL-042 | "Then repeat with Cash 680 and UPI **400**." | add "With Cash 700 and UPI 500 it is refused the other way: '1200.00 was received against a bill of 1180.00. Enter what the bill is paid with; change is handed back.'" |
| TC-SELL-055 | "New again with the same name." | add "The same name in other letters (`speedy carriers`) or with a trailing space is refused the same way." |
| TC-SELL-061 | "The file is … MB; the most a file may be is 10 MB." | "The file is larger than 10 MB, the most it may be." |
| TC-SELL-064 | "Change the quantity to **4** → **Save & print (F9)** with *Received now* 472." … "approves for 4 (472.00)" | interim, until SELLQ-12 is settled: "Leave the quantity at 3 → **Save & print (F9)** with *Received now* 354. The bill approves for 3 (354.00). A saved counter bill cannot be added to." And until SELLQ-22 is fixed the case must not cut the quantity down either |
| TC-SELL-065 | "Cancelling the held draft clears the hold" | add "and gives back the stock it reserved (its order is cancelled with it)." |
| TC-SELL-067 | "`POST /api/v1/counter-shifts`" | "`POST /api/v1/counter-shifts/open`" |
| TC-SELL-076 | the next-day half | add "`GET /api/v1/collections/sheet?as_of=<tomorrow>` shows the promise **Broken** without waiting." |
| TC-SELL-078 | "Withdraw is no longer offered for it, nor for a Kept promise." | add "**(HTTP)** withdrawing a Kept promise is refused (422): 'That promise was kept: the money promised was received, so there is nothing to withdraw.'" |
| TC-SELL-084 | "The period cannot end before it starts." | the server's words are "The period must not end before it starts." |
| New cases wanted | none exist | (1) a line of quantity 0 with nothing free is refused on an order, a note, a bill and a counter bill; a bill that comes to 0.00 (100% discount, free goods alone) approves, posts no receivable and no journal of its own, ships and costs its goods, and its note leaves the list of notes to bill. (2) cancelling a draft counter bill cancels the order and note it raised and writes `UNRESERVE`. (3) the returns-before-billing flavours of the table above, with what GSTR-1, 3B, the register, the analysis and the rebate read |

## Still to walk on screen

As listed in round 2, unchanged: the helper texts and toasts of 001-017 and
021; the dispatch prompt of 018; the batch picker of 019 and 023-026; the tick
list of 027; the scan field and F9 of 029; the QR, Downloads and wa.me of 034
and 035; Export of 036; the *Walk-in* button and buyer boxes of 040-045; the
*Other charges* rows of 050-054; the carrier picker of 055-059; the
Attachments panel of 060-063; Hold, Recall, the shift strip and close dialog
of 064-072 and 087; the Collection Sheet and Payment Promises screens of
073-079; the Customer Rebates screen of 080-086. New for this round: how the
return editor shows a return before billing (the document still totals 590.00
while nothing is credited), and what the customer editor offers a Field Sales
user (credit limit, opening balance).

## Not verified

- TC-SELL-018's Warn half, TC-SELL-027's branch clash and supplier half,
  TC-SELL-076's real next day, TC-SELL-006's PENDING claim rows, the email
  worker, Send on a purchase order.
- SELLQ-23 could not be reproduced at will; it was seen twice with other
  provisions running. The causes given for every defect are from reading the
  code.
- SELLQ-2 was checked by reading the log after three provisions on the one
  server.
- Whether a counter bill cut down (SELLQ-22) behaves the same with several
  lines or with batches was not driven.
