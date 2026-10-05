# Selling: checked through the API, round 5, 2026-10-06

A fifth pass, after the fixes for round 4's findings were merged (#1210 to
#1214) and the backend at http://127.0.0.1:8000 was restarted on `main` at
`eb8cc9a7` with every store at `20261005_0333`. Eight items were driven by
their original reproductions, each on two fresh fixture firms; then round 4's
scripts for counter bills, held bills and shifts, batches and pinned batches,
order cancel, returns and the books were run again and their logs compared
with their earlier twins. Everything went over HTTP. Nothing was fixed and no
source file was changed. Rounds 1 to 4 are left as they were.

**All eight items are fixed.** Three things are new: one Medium (SELLQ-33,
money received on a bill whose total is not a whole paisa), and two Low
(SELLQ-34, SELLQ-35). None of them comes from the four PRs.

The round ran between 00:40 and 02:00 IST, which is the evening of 5 October
in UTC. The scripts date their documents with the machine's own date, so every
document of this round is dated one day ahead of the server's day. That is
behind SELLQ-35 and behind two of the log differences below.

## Fixture firms used

| Key | Fixture | Suffix / firm | Used for |
| --- | --- | --- | --- |
| M | `selling-firm` | `t1006sxih` / `T1006SXIH-S`, GSTIN 33FXSEL2322A1Z5 put on it | items 1, 2, 3, 4, 5, 8 (first run); returns regression |
| N | `selling-firm` | `t1006crt0` / `T1006CRT0-S`, GSTIN 33FXSEL2470A1Z5 put on it | the same items again (second run); regression of round 4's counter-bill edit scripts |
| P | `pharma-firm` | `t1006xsvk` / `T1006XSVK-P` | items 6, 7 and the batched corner of item 8 (first run); the pinned-batch regression |
| E | `pharma-firm` | `t1006vkou` / `T1006VKOU-P` | items 6, 7, 8 again (second run); regression of cases 019, 022 to 026 |
| G | `selling-firm` | `t1006ipug` / `T1006IPUG-S`, GSTIN 33FXSEL4186A1Z5 put on it part way | regression of cases 029, 040 to 047, 049 to 054, 064 to 072, 087, round 3's SELLQ-16 / 17 / 18 sequences, price terms through an edit |
| D | `selling-invoiced` | `t1006xrtg` / `T1006XRTG-S` | regression of cases 015, 016 |
| B | `selling-ordered` | `t1006z7sx` / `T1006Z7SX-S` | regression of cases 007 to 011, 017, 030 (order cancel) |

All seven fixture builds succeeded first time, about two minutes each. M, N
and G were given the shared masters (`-CTR` at 100 with 500 on hand, `-SVC`,
`-C03`) as before; roles were hired per firm by the regression scripts. The
server was not restarted. Scripts and logs are in the scratchpad folder
`selling5` beside round 4's `selling4`.

## The eight items

Fixed = the original reproduction now gives what was expected, on both firms,
with the same answers. Figures are the first firm's unless said.

| # | Ledger id | Result | Evidence |
| --- | --- | --- | --- |
| 1 | D-SELL-77 / SELLQ-28 (#1210) | **Fixed** | **Discount**: draft 3 CTR at 5% (`SI-26-27-000003`, 336.30). `PUT` the same 3 with `discount_percent` "0" → 200, 354.00. `PUT` 4 by source line, nothing else → 200, **472.00 at 0%** (was 448.40); approves at 472.00: Dr 1100 472.00 / Cr 4000 400.00 / Cr 2220 36.00 / Cr 2230 36.00, cost 240.00, on hand 492 to 488, reserved 0. **Price**: draft 3 CTR at 100 (354.00). `PUT` the same 3 with `unit_price` "90" → 318.60. `PUT` 4 echoing `unit_price` 90 → **424.80 at 90** (was 472.00); `PUT` 5 with no price → 531.00 at 90; `PUT` 6 at 80 → 566.40; the same 6 at 80 with 10% → 509.76; `PUT` 7 with nothing else → 594.72 (7 x 80 less 10%); approves at 594.72: Cr 4000 504.00, tax 45.36 + 45.36, cost 420.00, on hand 488 to 481, ledger `DISPATCH` 7. **New behaviour, confirmed**: a price-only or discount-only edit withdraws the hidden pair and raises a new one. After the discount edit `DN-26-27-000007` / `SO-2026-2027-000007` read CANCELLED, "Bill SI-26-27-000003 was changed before approval.", and the bill names `DN-26-27-000008`; orders and notes go 7 → 8. After **every** edit above the bill line, the note line and the order line were read and agree on quantity, price and discount. An edit that changes nothing (the same 4 at 90 again) raises nothing (12 → 12). **Inherited terms**: see the section below. **GST-inclusive**: draft 3 at 118 inclusive, 5% (336.30) → discount 0 → 354.00 → 4 by source line → 472.00, still inclusive, `entered_rate` 118, print carries 118.00 and 472.00, approved Cr 4000 400.00. Draft 3 at 118 inclusive → the same 3 at 106.20 → 318.60 (`unit_price` 90, entered 106.20) → 4 echoing the stored 90 → 424.80 → 5 with no price → 531.00; approved Cr 4000 450.00, cost 300.00 |
| 2 | D-SELL-78 / SELLQ-27 (#1212) | **Fixed** | Draft 3 CTR for C03. `PUT` the line by its source fields with `current_invoice_quantity` "0" → **422 "Line 1 bills a quantity of 0 and supplies nothing free. Type a quantity, or leave the line off the bill."** Bill version 2 → 2, total 354.00 → 354.00, orders / notes 35 → 35, reserved 3 → 3, the same note. With two lines and the second at 0: 422 "Line 2 bills a quantity of 0…", bill still 552.24 with 3 and 2. Quantity 0 with `free_quantity` 1 is accepted (0 billed, 1 free, reserved 1), as the message implies. `/diagnostics/errors` holds no server error dated after the restart |
| 3 | D-SELL-79 / SELLQ-29 (#1212) | **Fixed** | Draft 3 CTR, `freight_amount` 50, `bill_discount_percent` 10 → 377.60. `PUT` the same 3 naming only its lines → **377.60**, both kept. `PUT` 4 naming only its lines → **483.80** (was 472.00); the order raised again carries freight 50 and 10% too. Freight "0" → 424.80 with the bill discount kept; `bill_discount_percent` null → 472.00; both sent again with 5 → 590.00; `freight_amount` null → 531.00; bill discount "0" → 590.00. **Other header fields** (a walk-in draft with `reference_number` REF-9, `remarks`, `additional_charges` 20, `round_off` 0.40, one note, a Packing charge of 100, a buyer; 474.40): all survive the same 3, a change to 4 (592.40) and 5 sent as a product line (710.40), each naming only lines. Then one at a time: `reference_number` null → cleared; `remarks` null → cleared; `additional_charges` "0" → 690.40; `round_off` "0" → 690.00; `notes` [] → no notes; `charges` [] → 590.00; `buyer_name` null → cleared. `additional_charges` null and `round_off` null are 422 (the schema takes a number there), so 0 is how those two are cleared. **A bill of a person's own delivery note**: order of 4 with freight 50, note of 4, draft bill of 2 with a reference, remarks, bill discount 10%, charges 20, round off 0.40 → 262.30 with freight 25.00 (its share). Naming only its lines: the same 2 → 262.30; 3 → 383.25, freight 37.50; 4 → 504.20, freight 50.00; 2 again → 262.30. Every header field kept each time. Null or 0 clears each (reference, remarks, bill discount, charges, round off, notes). **Its freight rule**: nothing sent, or null, takes the order's share (25.00 for 2 of 4; a fresh bill of 2 of 4 with nothing on its header also reads 25.00); a typed 80 is taken as 80. **A flat bill discount amount**: draft 3 CTR with `bill_discount_amount` 30 → 318.60, stored as 10% / 30.00. The same 3 → 318.60. `PUT` 4 naming only its lines → **424.80: 10% / 40.00, carried as a rate** (a flat 30 would be 436.60). Sent again as 30 with the 4 → 436.60, stored 7.5% / 30.00. Null or "0" → 472.00 |
| 4 | Coupon (#1212) | **Fixed** | Draft 3 DET for C03, no coupon: 291.4128 at the price list's 2%. `PUT` the same 3 with `coupon_code` WELCOME10 → **200**, 289.9260 at 2.5% (was 422); the pair is raised again and the order line reads `promotion`. `PUT` 4 with the coupon → 386.5680. `PUT` 5 with no coupon sent → 483.2100, **still 2.5%**. The same 5 again, not sent → unchanged. `coupon_code` null → 485.6880 at 2%, order line `price_list`. Coupon back with 6 → 579.8520; the same again → unchanged; approved at 579.8520. **Claims**: `GET /promotions/reports/redemptions` after approval shows one CLAIMED row (the last order, 12.60) and three REVERSED (the withdrawn orders, 6.30, 8.40, 10.50); `GET /promotions/reports/coupons` WELCOME10 `claimed_count` 0 → **1**, benefit 12.60. The claim is made when the hidden order is approved, which is at the save, so a draft already holds one live claim; each edit reverses it and claims again on the new order. **A bill of somebody's documents**: create with a coupon → 422 "A coupon is applied where the price is set: on the order, or on a bill typed straight in. This bill continues documents already priced, so it cannot take one."; edit with a coupon, same lines and with the quantity cut → the same 422, bill unchanged |
| 5 | D-SELL-80 / SELLQ-30 (#1213) | **Fixed** | Five wholly unbilled returns, each 5 delivered, never billed, 5 back against the note, COMPLETED. `GET /sales-returns/summary` `total_return_value` before and after each: plain (590.00) **+0**; `additional_charges` 50 (640.00) **+0** (was +50); `round_off` 0.40 (590.40) **+0** (was +0.40); 50 and -0.25 (639.75) **+0**; a line charge of 10 (601.80) +0. Each has only its cost journal, the customer's balance does not move, register `credited_amount` 0.00. A billed return of 2 with `additional_charges` 20 (256.00) moves the summary by 256.00; a part-billed one (4 delivered, 3 billed, 2 back, charges 20) credits 138.00 and moves it by 138.00. **Summary against register**: after round 4's eight returns and these, the register's COMPLETED rows add up to 984.00 credited over 14 returns; the summary says `total_return_value` 984.0000, `completed_returns` 14. Equal on both firms. What a draft or approved return adds is SELLQ-34 below |
| 6 | D-SELL-81 / SELLQ-31 (#1214) | **Fixed** | P, stages off, batch N (60 days, 10) and L (400 days, 10). Draft of 4 picked 1 N + 3 L → reserved **N 1, L 3** (was N 4, L 0); stock ledger `RESERVE` 1 on N and 3 on L against the bill's order. Approved: N 9, L 7, nothing reserved, note ships 1 + 3, cost 240.00, bill 448.00. A draft that chose L alone holds L 4; edited at the same quantity to 1 N + 3 L → N 1, L 3; to 6 as 2 N + 4 L → N 2, L 4; all on L → L 6; to 5 with no batches sent → picks dropped, N 5; cancelled → 0 / 0. **Picks that do not add up**: 6 with 2 N + 3 L saves and reserves N 6, L 0 (first expiry first); approval 422 "Line 1: the batches chosen add up to 5.0000, and the line delivers 6.0000."; corrected to 2 N + 4 L → N 2, L 4, approves, N 8, L 6. **The hold protects the bill**: with a draft holding 1 N + 3 L, an ordinary order of 16 takes the rest (N 10, L 10 reserved); the bill approves and ships 1 + 3. Two split lines of two products on one bill each hold their own picks |
| 7 | "D-SELL-82" (#1214) | **Fixed** | P, N and L as above. **Two drafts**: A of 4 with no picks holds N 4; B of 4 chose L, holds L 4. Cancel B → **N 4, L 0**; A's order still shows 4 reserved, B's 0; ledger `UNRESERVE` 4 on L against B's order. A approves and ships 4 of N. B edited instead (5 on L: its order withdrawn and raised again) → N 4, L 5; A cut to 3 → N 3, L 5; A cancelled → N 0, L 5; B ships 5 of L. A held bill on L cancelled while held → N 4, L 0. **Ordinary orders**: X 10 holds all of N, Y 5 falls to L; cancel Y → N 10, L 0, X's note ships N. X 4 on N, Y 4 pinned to L; cancel Y → N 4, L 0; a new pinned Y2, cancel X → N 0, L 4, Y2 ships L. X 4, Y 8 (N 6 + L 2); cancel Y → N 4, L 0; Y again, cancel X → N 6, L 2 and Y ships. X on N, Y 3 and Z 4 on L; cancel the middle one → N 10, L 4, both others dispatch. **Close**, the other way an order lets go: W 8 on N, X 6 (N 2 + L 4), X ships 2 and is closed → L 0, N 8 still W's, W dispatches. Cancelling an order with a dispatched note standing is refused as before (422 "…cannot be cancelled while delivery note … stands against it…") |
| 8 | D-SELL-59 desktop half (#1211) | **Fixed** | Bodies built as `_payload` / `_productLine` in `sales_invoice_editor_dialog.dart` build them: saved lines by source fields with the bill's own `unit_price`, new products with no warehouse and no `source_documents`, `shipping_address_id` null, `If-Match` with the version. **Typed terms kept**: saved draft 3 CTR at a typed 5% (336.30); mixed `PUT` adding DET 2 at 84 → **200, 530.5752**; CTR still 5% (order line `percent`), DET at the price list's 2% (`price_list`); one new note and order with both lines, the old pair CANCELLED; reserved CTR 3, DET 2. Approved: CTR 460 → 457, DET 91 → 89, Dr 1100 530.58 / Cr 4000 449.64 / Cr 2220 40.47 / Cr 2230 40.47, cost 300.00. **Inherited terms resolved**: saved draft 3 CTR for C01 (standing 7.5%, 327.45); mixed `PUT` adding DET 16 at a typed 3% → 1,865.7924, CTR 7.5% `customer`, DET 3% `percent`; again with CTR to 5 and the service added → 2,629.8424; approved, 5 and 16 leave, Cr 4000 2,228.68, cost 1,260.00. **Quantity changed in the same save**: CTR 3 → 4 by source plus DET 1 → 569.1376, lines agree (its approval with two tenders is SELLQ-33). **Held**: mixed `PUT` while held → 200, stays held, 433.4376; after recall, adding the service → 1,023.4376; approved, Cr 4000 867.32. **Batched**: on P, a saved draft of product V gains product W picked 1 N + 3 L → W reserved N 1, L 3; approved, ships 2 and 1 + 3. **Refused**: stale `If-Match` 409, unknown product 422, discount 150% 422, each leaving bill, version, note, order and reserved stock as they were. **Preview**: `POST /sales-invoices/preview` with every line as a product line and `rate_includes_tax` false → 200, 530.5752, the figure the save then stores; orders 69, notes 69, invoices 24, the bill's version and reserved stock all unchanged; the mixed shape on the preview is 422 "An invoice bills either documents already raised or bare product lines, never a mixture of the two.", which is why the screen restates. On a GST-inclusive bill (CTR entered 118 less 5%, DET 2 at 99.12 inclusive, `rate_includes_tax` true) → 530.5752, nothing written; the save, which sends no `rate_includes_tax`, stores 530.5752, still inclusive, entered 118.00 and 99.12. **An emptied box**: draft with reference REF-R5, bill discount 10%, freight 50 (377.60); the desktop's save with those three keys omitted → all three **kept**, 377.60; with a product added → kept, 465.0240. Sent as null → all cleared, 451.1376. Bill discount "0" and freight "0" clear those two. So a reference, a bill discount or freight on a saved bill **cannot be cleared from the desktop** until it sends null (or 0) for an emptied box |

Every item gave the same answers on its second firm; the logs were compared
line by line with document numbers masked and differ only in the order two
journals of one document are listed.

### Item 1: an arrangement nobody typed

Driven on M and N, same answers.

| Sequence | What happens |
| --- | --- |
| C01's standing 7.5% on CTR, nothing typed | Draft 3 → 327.45, order line `customer`. A **price-only** edit to 90 → 294.7050, still 7.5% `customer` on bill, note and order. 4 echoing 90 → 392.94, still 7.5% |
| The price list on DET for C03 (0 → 2%, 15 → 4.25%, 18 → 6.75%; BULK5 7.5% at 25+) | Draft 16 → 4.25% `price_list`. Price-only to 80 → still 4.25%. 20 echoing 80 → **6.75%**. 26 → **7.5% `promotion`**. 2 → **2%**. The price of 80 is kept throughout and the tier follows the quantity: resolved again each time |
| An inherited 7.5%, then a 0 typed at the same quantity, then the bill grows | 327.45 → typed 0 → 354.00 → 4 with nothing else → **472.00**: the typed 0 is kept as typed and the standing rate does not come back |
| A typed 5%, 4 with no discount, then 0 typed, then 6 with no discount (round 4's script) | 5% kept at 4; after the typed 0, 6 reads 0% and 594.72 (round 4: 5% and 564.98) |

## Regression pass

Round 4's scripts were run unchanged on fresh firms (only the shared helper's
ledger-account reader was repaired in the copy, see "The scripts" below) and
each log compared with its twin after replacing firm tags, ids, dates and
times. Every difference is listed.

| Script and cases | Firm | Differences from the earlier log | Reading |
| --- | --- | --- | --- |
| `g1.py` 040 to 047, 049 (walk-in and counter bills, services, a service return) | G | document numbers two higher throughout; case 045's register rows read `place_of_supply` '' and GSTR-1 answered 422 "This firm has no GST number…"; the order two journals are listed in | my setup: `g4.py` ran first this time (two documents), and G had no GSTIN yet when 045 ran. With the GSTIN on, the register reads "Tamil Nadu (33)" on every row and GSTR-1 answers 200 with B2CS 13,500.00 / 1,215.00 + 1,215.00. No change in the product |
| `g2.py` 050 to 054 (charges on the bill) | G | numbers two higher; GSTR-1 b2b and hsn empty in 053 | the same two causes |
| `g3.py` 064 to 072, 087 (hold, recall, shifts) | G | numbers two higher and stock four lower; a clock time in the shift report | no change. 064 still approves for 4 at 472.00, and the script's next step is still refused "…names a document that is not … own" for holding ids from before the edit |
| `g4.py` 029 (barcode, split tenders, over-tender) | G | receipt and order numbers (it ran first) | no change |
| `rc1.py` 16, 18 (zero-total bills, returns before billing) | G | journal order only | no change |
| `rc1.py` counter (SELLQ-17, 16, 21, 4, 12, 10, 11, 13) | G | a clock time; two connection resets retried | no change |
| `i7.py` (price terms through an edit) | G | (b) after a typed 0, 6 with no discount: 594.72 at 0%, was 564.98 at 5%. (d) the coupon sent again on a same-ship edit: 200, was 422. (f) 4 with nothing sent: 583.80 with freight 50 and 10% kept, was 572.00 with both gone. (g) the reference TOKEN-7 kept through the edits, was cleared | all four expected: #1210, #1212, #1212, #1212 |
| `i1.py`, `i2.py` (round 4's items 1 and 2) | N | 2c: a price-only edit now raises the pair again (a CANCELLED note and order in the chain listing), so the script's next step, which sends ids from before it, is refused "not its own"; "PUT quantity 0" 422, was 500; reserved figures 8 and 2 higher throughout | the first is #1210 and the refusal is right; the second is #1212; the third is two drafts item 8c left on N on purpose (cancelled before the books check). Free goods, GST-inclusive, several lines, refusals and held bills read as round 4 |
| `i8.py`, `i9.py` (round 4's SELLQ-28 and 29 reproductions) | N | 448.40 → 472.00; 472.00 at 100 → 424.80 at 90; 590.00 → 531.00; note and order lines now carry the edited terms; freight and bill discount kept (413.00 → 377.60, 472.00 → 483.80); reference and remarks kept | the fixes |
| `reg1.py` (eight returns and every reader) | M, N | journal order; bill numbers; GSTR-3B's 247.49999999999994 reads 247.5 this time; B2B rows listed in another order | no change. The float depends on the order the rows are summed in |
| `d1.py` 015, 016 (return and credit note against a bill, and their cancels) | D | the order loyalty rows and journals are listed in | no change |
| `b1.py` 007 to 011, 017, 030 (delivery, back order, order cancel) against round 3's log | B | audit rows and journals in another order; the pick list and loading sheet PDFs 7 and 2 bytes longer. Round 3's log also holds 018 and 027, which `b2.py` makes and was not run | no change. 017: cancelling the order takes reserved 24 back to 12 |
| `e1.py`, `e2.py`, `e3.py` 019, 022 to 026 | E | `days_to_expiry` one higher on every batch (21 for 20, 121 for 120) and expiry dates one day later; the newest `fefo_skipped` audit row is a different one; two stock rows in the other order | the first is the hour: the script dated the batches from the machine's 6 October and the server counts from the UTC 5 October. The audit row is item 8's batched save, run on the same firm first. 023 and 025 read as round 4 |
| `rp_pharma.py` (round 3's SELLQ-5 / 6 reproduction, pinned batches) | P | "edit to 1 N + 3 L" reads L 3, N 1 where round 4 read N 4; stock rows in another order | #1214 |

**Books, all seven firms.** The trial balance balances (M 56,985.72; N
59,455.50; P 34,772.00; E 39,621.60; G 2,844,351.02; D 6,459.53; B 6,492.87);
1100 Trade Receivables equals customers' outstanding less advances in each (M
13,409.66; N 14,433.90; G 2,736,386.81; D 289.93; B 483.21); no journal is
unbalanced (read 25 a page). Reserved stock came back to 0 on M and N. **The
stock valuation could not be set against 1200 this round**: the report read
0.00 against 5,400.00 on D, and likewise on the others, because of SELLQ-35.
Each bill's cost journal was read instead and matches what left (60.00 a
unit).

No difference was left unexplained.

## New findings

Ids continue from round 4. Each was reproduced on two fresh firms.

| Id | Severity | What | Reproduction | Expected / actual | Suspected cause |
| --- | --- | --- | --- | --- | --- |
| SELLQ-33 | **Medium** | Money received at the counter cannot settle a bill whose total is not a whole paisa | M, N (stages off). `POST /sales-invoices` 1 DET at 84 for the walk-in customer, nothing typed (the price list's 2%, total **97.1376**), `received_now_amount` "97.14" CASH → saved; `POST …/approve` → **422 "97.14 was received against a bill of 97.1376. Enter what the bill is paid with; change is handed back."** With "97.13": 422 "A walk-in bill is paid in full at the counter: … comes to 97.14 and 97.13 was received. Take the rest…". One cash tender of 97.14: the same first refusal. "97.1376", the bill's own total: 422 at save, "Decimal input should have no more than 2 decimal places". For C03, a named customer: 97.14 is the same 422; 97.13 approves and leaves the customer owing 0.01 (the journal debits 1100 97.14). Also met in item 8c: 569.14 in two tenders against 569.1376 | Expected: 97.14, the amount the bill posts to the receivable, is accepted. Actual: the walk-in rule compares with the rounded 97.14 and the over-tender rule beside it with the unrounded total, so no amount passes both. A walk-in bill priced by any percentage that leaves a fraction of a paisa cannot be approved with its money; the way through is a typed `round_off` (0.0024 with 97.14 received approves and posts Dr 1000 97.14). Not from this round's PRs: every earlier counter case used a product with no price list, so the totals were whole | `app/sales_invoice/services/sales_invoice_service.py:1276` (`amount > Decimal(str(row.grand_total))`, where the walk-in check at `:1570` uses `_receivable_amount(row.grand_total)`). The desktop pre-fills the box with the preview's `grand_total` (`sales_invoice_editor_phase2.dart:330`), which would be the four-decimal figure the save refuses; read in the code, not seen on screen |
| SELLQ-34 | Low | The sales-return summary values a draft or approved return at its document total; the register and by-customer value it at nothing until it completes | M, N: 5 delivered and billed; `POST /sales-returns` 1 back against the bill (118.00), left DRAFT → summary `total_return_value` **+118.00**; register row `credited_amount` 0.00; by-customer unmoved. Approved: the same. Completed: summary unmoved, register 118.00, by-customer +118.00. A return of 5 never billed with `additional_charges` 50 (640.00), DRAFT → summary **+640.00**, register 0.00, `unbilled_quantity` 0.0000; approved the same; completed → summary **-640.00** (back to where it was), register 0.00, unbilled 5 | Expected: one rule. Either the summary counts only what has credited (as the register does), or it counts drafts at what they will credit. Actual: a never-billed return is counted at 640.00 for as long as it is a draft or approved and at 0 once complete, because the unbilled quantity is stamped on the lines only at completion and the summary reads it from there. The completed total is right (item 5) | `app/sales_return/services/sales_return_service.py:350` (every status but CANCELLED is summed; `before_billing` reads `unbilled_quantity`, set at `:969`) |
| SELLQ-35 | Low, outside selling | Between midnight and 05:30 IST the stock valuation leaves out everything dated today, and cannot be asked for it | 01:42 IST on 6 October (20:12 UTC on the 5th). Firm D (and M, N, P, E, G, B): 90 DET on hand, trial balance 1200 Inventory 5,400.00. `GET /inventory/reports/stock-valuation` → three rows, TOTAL 0.00, BOOKS 0.00, DIFFERENCE 0.00 and no item. With `to_date=2026-10-06` and with `2026-10-07`: the same. On M: TOTAL 30,000.00 (the one opening dated 40 days back) against 1200 at 33,900.00. Round 4 read 5,400.00 / 5,400.00 on the same fixture, before midnight. Batch availability shows the same day shift: a batch dated 20 days on reads `days_to_expiry` 21 | Expected: a document dated today by the person who made it is in "as on today". Actual: documents carry the date the client sends (the machine's own, and the desktop sends `widget.today`), the report's day is the server's UTC day, and a later `to_date` is clamped back to it. For a firm in India that is the first five and a half hours of every day. Whether dates should follow the firm's zone is the owner's call; the clamp makes the gap impossible to work around | `app/inventory/api/router.py:337` (`on = min(to_date or utc_now().date(), utc_now().date())`) |

**D-PERF-3 (a large answer reset in transit) was seen again**, on one route
only: `GET /inventory/ledger?product_id=…&page_size=100` (about 175 KB) was
reset with WinError 10054 **14 times** in four script runs on M, N and G.
Eleven were followed by a retry that arrived; once all three tries failed in a
row and the script stopped. Asked for directly three times afterwards at 100
it answered three times. Every read at `page_size=25` in the round arrived, as
did the journal and customer lists that failed in round 4 at 100, now read at
25. `/diagnostics/errors` holds no server error dated after the restart.

Smaller things seen and not given an id: an unknown coupon code is accepted
without a word on a counter bill, on its edit and on a sales order (201 / 200,
no discount, the code stored on the order; `promotion_service.py:358` says this
is on purpose, so a typo does not stop a save); a saved counter bill does not
return its `coupon_code` (the order holds it), so a client cannot show which
coupon a saved bill carries; clearing `notes` on a bill does not move its
`version` (13 → 13), nor does sending the same source line twice (round 4);
a typed discount of 0% is stored on the raised order as a discount *amount*
of 0 (`discount_source` "amount") after the next quantity edit, which changes
no figure; a `reference_number` sent as an empty string is stored as "" where
null clears it; a negative `round_off` of 0.1376 is posted against Sales (Cr
4000 82.18 for a line of 82.32), not to a rounding account; a draft of 100,000
units against 72 on hand still saves and reserves 100,001, and is refused only
at approval (as round 4).

## The scripts

One fault of the driver, not of the product, cost about twenty minutes: the
copy of round 4's helper read `GET /finance/ledger-accounts` page after page at
25 a page, and that list is not paged (it returns every account whatever
`page` says), so the loop never ended. The helper had been changed that way
late in round 4 and not run since. It was repaired in the `selling5` copy only;
round 4's folder is untouched. Three of my own scripts were also run a second
time after a mistake of mine (a clash of argument names, case tags left off
`g1.py`, `g2.py` and `d1.py`); the first tries are kept in the folder under
`*_first_try.out` / `*_second_try.out` and wrote real documents on M and N,
which is why the document numbers quoted above do not start at 1.

## Case-text corrections needed

Changes to `docs/INDEPENDENT_TEST_CASES.md` on top of round 4's table.

| Case | What the text must now say |
| --- | --- |
| TC-SELL-064 | Drop round 4's last sentence ("Until SELLQ-28 is settled, do not change a price or discount in a save of its own…"). Replace with: "Any change to a saved counter bill's lines, a quantity, a price or a discount, withdraws the note and order the save raised and raises a new pair; the old pair reads CANCELLED, 'Bill … was changed before approval.' After each save the bill, the note and the order agree on quantity, price and discount. A save that changes nothing on the lines raises nothing." |
| TC-SELL-064, and any case that sends quantity 0 on a saved counter bill | "Quantity 0 on a line is refused: 'Line 1 bills a quantity of 0 and supplies nothing free. Type a quantity, or leave the line off the bill.' Nothing is written." (was a 500 in round 4) |
| TC-SELL-023 | Replace round 4's "a line split across batches is reserved first expiry first until approval (SELLQ-31)" with: "a line split across batches holds each batch for what was chosen from it (1 of the early batch and 3 of the late read reserved 1 and 3); picks that do not add up to the line are held first expiry first and refused at approval." Keep "changing the quantity without sending the picks again clears them" |
| TC-SELL-024 / 025 | Add: "Cancelling or closing an order, or cancelling a draft counter bill, lets go of that order's own hold: an order on the late batch that is cancelled frees the late batch and leaves another order's hold on the early batch alone." |
| TC-SELL-050 to 054 (charges, freight and discount on the bill) | Add: "On a saved bill, a header field an edit does not send is left as it is: freight, the bill discount, the reference, remarks, additional charges, round off, notes and charges. Null clears a reference, remarks, freight, a bill discount or a coupon; 0 clears additional charges and round off; an empty list clears notes and charges. A flat bill discount amount is carried as its rate when the quantity changes, so send the amount again to keep it flat." |
| The counter-bill coupon wording round 4 left under "smaller things", wherever a case quotes it | "A coupon is taken on any edit of a saved counter bill, stays when the edit does not send it, and null removes it. A bill of somebody's delivery note or order refuses one on create and on edit. The coupon report counts one claim for the bill however many times it was edited; the withdrawn orders' claims read REVERSED." |
| TC-SELL-015 | Add to round 4's wording: "The summary counts no header charge or rounding of a return that credited nothing, and for completed returns equals the register's credited total." Until SELLQ-34 is settled: "read the summary with no return left in draft or approved." |
| TC-SELL-041, 042 (walk-in paid in full) | Until SELLQ-33 is settled: "use a product whose bill comes to whole paise (CTR at 100), or type a round off that makes it so." |
| The desktop cases for a saved counter bill (D-SELL-59) | "Add a product to a saved or recalled counter bill and save: the saved line keeps a discount somebody typed and takes again one the customer's arrangement gave; the new product is priced as on a new bill. Emptying the reference, bill discount or freight box on a saved bill and saving does **not** clear it (the desktop omits the field); note this as a known limit until the desktop sends null." |
| New cases wanted | (1) price-only and discount-only edits of a saved counter bill, exclusive and GST-inclusive, then a quantity edit, with bill, note and order read after each. (2) two drafts or two orders on different batches, one cancelled, by batch. (3) the stock valuation and "as on today" reports run after midnight IST (SELLQ-35) |

## Not verified

- Nothing on screen. What the desktop sends for a saved counter bill, and
  what it pre-fills as money received, was read from
  `sales_invoice_editor_dialog.dart` and `sales_invoice_editor_phase2.dart`
  and sent by hand; the screen itself, its second table, the scan field and
  the live preview were not opened.
- Item 8 with serial-tracked products (`serial_ids`), a second unit of
  measure or packaging, a gift added by an offer, and two people saving the
  same draft at once was not driven. The batched corner was driven with one
  added product only.
- Item 4 with a coupon that has a redemption limit: that a draft's live claim
  counts against the limit, and what a second draft is told, was not driven.
  The fixture's coupons have none.
- Item 7: only cancel, close and the withdrawal an edit makes were driven. A
  reservation that lapses by age, and an order put on hold (which keeps its
  stock by design), were not.
- Item 5: the by-product report was not read again after the header-charge
  returns; the register, by-customer and the summary were.
- The stock valuation against 1200 on every firm (SELLQ-35 stood in the way),
  and SELLQ-35 itself after 05:30 IST, when the two dates agree again.
- SELLQ-33 on a credit bill paid later through `/receipts`: only money
  received on the bill itself was driven.
- D-PERF-3's cause. It was counted, not investigated.
- The causes given for every finding are from reading the code.
- Of the earlier regression set, 018, 027 (`b2.py`), 031, 035 (cash discount,
  messaging), 036 to 039, 048, 055 to 063, 073 to 086 and the generic checks
  script were not run again: #1210 to #1214 do not touch them.
