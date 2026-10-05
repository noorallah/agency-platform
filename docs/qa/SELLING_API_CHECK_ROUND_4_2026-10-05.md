# Selling: checked through the API, round 4, 2026-10-05

A fourth pass, after the fixes for round 3's findings were merged (#1198,
#1200, #1202, #1203) and the backend at http://127.0.0.1:8000 was restarted on
`main` with every store at `20261005_0329`. Eight items were driven by their
original reproductions, each on two fresh fixture firms; then the round 3 case
scripts for counter bills, held bills and shifts, batches, returns and the
books were run again and their logs compared with round 3's. Everything went
over HTTP. The server's own log was read only to find the traceback behind one
500 and to see how it had answered requests whose connection was reset. Nothing
was fixed and no source file was changed. Rounds 1 to 3 are left as they were.

## Fixture firms used

| Key | Fixture | Suffix / firm | Used for |
| --- | --- | --- | --- |
| M | `selling-firm` | `t1005fav4` / `T1005FAV4-S`, GSTIN 33FXSEL3930A1Z5 put on it | items 1, 2, 4, 5, 6, 7, 8 (first run); returns regression |
| N | `selling-firm` | `t10050byk` / `T10050BYK-S`, GSTIN 33FXSEL4430A1Z5 put on it | the same items again (second run) |
| P | `pharma-firm` | `t1005xt4p` / `T1005XT4P-P` | item 3 and the batch corner of item 2 (first run); round 3's pharmacy reproduction script again |
| E | `pharma-firm` | `t1005rp1f` / `T1005RP1F-P` | item 3 and the batch corner again (second run); regression of cases 019, 022 to 026 |
| G | `selling-firm` | `t1005ozk4` / `T1005OZK4-S`, GSTIN 33FXSEL6823A1Z5 put on it | regression of cases 029, 040 to 047, 049 to 054, 064 to 072, 087 and of round 3's SELLQ-16 / 17 / 18 sequences; price terms through an edit |
| D | `selling-invoiced` | `t1005rmij` / `T1005RMIJ-S` | regression of cases 015, 016 |

All six fixture builds succeeded first time. M, N and G were given the shared
masters (`-CTR` at 100 with 500 on hand, `-SVC`, `-C03`) as in round 3. Roles
were hired per firm as before (Field Sales `SALES_EXECUTIVE`, Sales Manager,
Firm Manager, Read Only, Warehouse, Counter Sales). The server was not
restarted. Scripts and logs are in the scratchpad folder `selling4` beside
round 3's `selling`.

## The eight items

Fixed = the original reproduction now gives what was expected, on both firms,
with the same answers. Figures are firm M's unless said.

| # | Ledger id | Result | Evidence |
| --- | --- | --- | --- |
| 1 | D-SELL-72 / SELLQ-22 | **Fixed** | DET 100 on hand. `POST /sales-invoices` 3 DET for C03: draft `SI-26-27-000002`, 297.36, reserved 3, on `DN-26-27-000002` / `SO-2026-2027-000002`. `PUT` the line back by its source fields at 2 → 200, 198.24, **reserved 2**; the line now names `DN-26-27-000003`; the old note and order read CANCELLED, `cancel_reason` "Bill SI-26-27-000002 was changed before approval."; new order `SO-2026-2027-000003` APPROVED for 2. `POST …/approve` → APPROVED 198.24, **on hand 98**, reserved 0. Stock ledger: `RESERVE` 3 / `UNRESERVE` 3 on the old order, `RESERVE` 2 / `UNRESERVE` 2 on the new, `DISPATCH` 2 on `DN-26-27-000003`. Cost Dr 5200 120.00 / Cr 1200 120.00; bill Dr 1100 198.24 / Cr 4000 168.00 / Cr 2220 15.12 / Cr 2230 15.12. Nothing is left to bill on either note (`GET /sales-invoices/billable` has no row for them); the customer owes 198.24 more. With several lines (CTR 3 + DET 5): one line cut, then one left off, then the draft cancelled, reserved follows each step and ends at 0 |
| 2 | D-SELL-59 server half / SELLQ-12 | **Fixed**, with new findings SELLQ-27, 28, 29, 31 in the corners | **Grow by source fields**: draft of 3 CTR (354.00), `PUT` quantity 4 with 472 cash → 200, 472.00, reserved 4, new note and order for 4; approve → on hand 497 to 493, note delivers 4, order DELIVERED 4, receipt `RC-2026-2027-000001` 472.00 CASH (Dr 1000 / Cr 1100), bill Dr 1100 472.00 / Cr 4000 400.00 / Cr 2220 36.00 / Cr 2230 36.00, cost 240.00, customer balance unchanged. **Held**: a held draft takes the same edit while held (stays held, reserved 4) and after recall. **Product lines on the PUT** (CTR 4 and DET 1, Cash 300 + UPI 271.12) → 200, 571.12, one note with both lines; approve ships 4 and 1, two receipts (Dr 1000 300.00, Dr 1010 271.12), bill Cr 4000 484.00 / tax 43.56 + 43.56, cost 300.00. Its own line at 4 plus one product line in one PUT is accepted too; leaving a line off drops its reservation. **Ships the same**: a reference only, money received only, and a price only each answer 200 on the same note with the order and note counts unchanged (12 / 12). **Refused edits** (unknown warehouse on an added line 422, unknown product 422, stale `If-Match` 409, a line that is not its own 422, discount 150% 422, an expired batch 422 on the pharmacy firms, and the 500 of SELLQ-27): after each the bill, its version, the note, the order, the reserved quantity and the document counts read exactly as before. **A bill of a person's own delivery note** still refuses a product line: 422 "SI-26-27-000001 bills documents already raised, so it is changed through the lines it has: send each line back with its source_document_type, source_document_id and source_document_line_id, as the bill returns them, and no product_id."; 4 against 3 delivered is 422 "Invoice quantity exceeds the available source quantity."; 2 is accepted with 1 left to bill. Corners are in the section below |
| 3 | D-SELL-58 remainder / SELLQ-5 | **Fixed** | P: batches M4 (120 days, 10) and M9 (270 days, 10). Order A, 8 for a customer needing 180 days: reserved M9 8. Order B, 8 for an ordinary customer: reserved M4 8. Picker for A's line: M9 "available to line" 10, pre-fill 8; M4 short for the customer, to line 2, pre-fill 0. Picker for B's line: M4 pre-fill 8. **A's untouched note dispatches**: 200, M9 on hand 2 reserved 0, **M4 still 10 on hand, 8 reserved**; ledger `UNRESERVE` 8 on A's order and `DISPATCH` 8; order B still APPROVED with 8 reserved; cost 480.00. B's note then ships M4. On E with B ordering 10 (round 3's figures): the same, M4 10 reserved throughout, A's picker shows M4 to line 0. **Behaviour change**: order X holds all 10 of batch N, order Y holds 5 on L; Y's note hand-picking N 5 saves and approves, and dispatch is 422 **"Line 1: Batch T1005XT4P-HA-N holds 0.0000 available here, and 5.0000 is chosen from it. Choose less from it, or another batch."**; a reason does not help; Y's picker shows N to line 0. With X holding 3 of N and Y holding 7: Y hand-picking N 10 is 422 "…holds 7.0000 available here, and 10.0000 is chosen from it…"; once X is cancelled (3 free) the same pick dispatches. A later batch that is all free, picked in place of the one held, dispatches |
| 4 | D-SELL-76 | **Fixed** | `POST /customers` as Field Sales and as Sales Manager, each field alone: `credit_limit` 50000 → 403 "T1005FAV4-QFS002: giving a customer a credit limit needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS). Leave it at zero, or ask somebody who holds it."; `opening_balance` 1500 → 403 "…an opening balance…"; `payment_terms_days` 30 → 403 "…credit days…"; `cash_discount_percent` 2, `cash_discount_days` 10, and both → 403 "…cash-discount terms…"; `default_discount_percent` 12.5 → 403 "…a standing discount…". Nothing extra → 201 ACTIVE; every term sent as zero → 201; cash discount sent as null → 201; a GSTIN and a phone → 201. With *New outlets need approval* on: a limit is still 403, nothing extra is 201 PENDING. Firm Manager and firm administrator: all 201, stored as typed, the opening balance posting its one journal. **`POST /customers/import`**: Field Sales 403 on the route (no `CUSTOMER_IMPORT`); Sales Manager two plain records 201, one plain plus one with any of the seven → 403 in the same words and **0 customers written**; all-zero 201. **File import** (the template carries `CreditLimit`, `CreditDays`, `DiscountPercent`, `OpeningBalance`; no cash-discount column): Sales Manager check and apply both report the issue on row 3 in the same words and apply writes 0; zeros import; Firm Manager and administrator import all. Books after it: 1100 = what customers owe. What an **edit** accepts is reported below, as an observation |
| 5 | D-SELL-73 / SELLQ-24 | **Fixed** | Bill of 118.00; promise of 118 for three days on; `POST /receipts` dated **yesterday** → the promise reads `received_amount` 118.00, **KEPT**. 60 dated five days back then 58 today: PENDING 60.00, then KEPT. A receipt recorded **before** the promise (dated today, and dated yesterday): `received_amount` 0.00, PENDING. A receipt dated the day **after** the promised day (promise for tomorrow, receipt dated two days on, which the server accepts): 0.00, PENDING; dated **on** the promised day: KEPT. A promise on the account: a receipt dated yesterday keeps it, reversing the receipt returns it to PENDING |
| 6 | D-SELL-74 / SELLQ-25 | **Fixed** for the reproduction; one corner is new, SELLQ-30 | Round 3's eight returns built again (A to F, U1, U2). Register: every row carries `credited_amount` and `unbilled_quantity`: A 236.00 / 0, B 118.00 / 1, C 0.00 / 5, D 0.00 / 5, cancelled E 0.00 / 0, F 118.00 / 0, U1 0.00 / 1, U2 118.00 / 0. By-customer: registered **472.00** over 5 returns with `unbilled_quantity` 11 (was 1,770.00); unregistered 118.00 over 2, unbilled 1. By-product: quantity 17, `return_amount` **590.00**, unbilled 12 (was 2,006.00). Summary `total_return_value` **590.00** |
| 7 | D-SELL-75 / SELLQ-26 | **Fixed** | Flavour B, `SR-26-27-000002` raised against `DN-26-27-000043`: GST sales register row `against_invoice_number` **`SI-26-27-000021`**, -100.00 / -18.00; GSTR-1 CDNR `against_invoice` **`SI-26-27-000021`**, taxable 100.00, 9.00 + 9.00. Returns raised against a bill name it as before; the unbilled returns C, D and U1 have no row in either. A part-billed return with a header charge (below) names its bill too |
| 8 | D-SELL-63 rest | **Fixed** | `GET /enquiries/follow-ups-due` → 200 with `pagination` {page 1, page_size 25, total_records 4, total_pages 1}, soonest first; `page_size=1000` and `101` → 422 ("query.page_size … less than or equal to 100"); `page_size=0` and `page=0` → 422; `page_size=2`: page 1 has two rows, **page 2 the other two**, page 3 is empty with the same totals; `on=` two days back counts 2. Read Only 200, Warehouse 403 |

### Item 2: the corners asked about

Driven on M and N (and P and E for batches), same answers on each pair.

| Corner | What happens |
| --- | --- |
| A GST-inclusive rate | Draft of 3 at 118 with `rate_includes_tax` true: stored `unit_price` 100, `entered_rate` 118, 354.00. `PUT` 2 by source line with no price → 236.00, still 100 / 118 and still inclusive. `PUT` 4 with `unit_price` 118 → 472.00. `PUT` 5 echoing the stored pre-tax 100 (what a client that sends the row back does) → 590.00, read as unchanged, still 118 entered. A product line of 5 at 118 without the switch → 590.00, the bill keeps its switch. A new inclusive price of 236 → `unit_price` 200. Approved at 590.00: Cr 4000 500.00 / Cr 2220 45.00 / Cr 2230 45.00, cost 300.00, the print carries 118.00 and 590.00. **Works** |
| Typed free goods, then the quantity changes | Draft of 3 + 1 free (reserved 4). Same quantity, `free_quantity` not sent: the free unit is kept. **Quantity 3 → 4 with `free_quantity` not sent: the free unit is dropped** (4 + 0, reserved 4), and again on 4 → 2. Sent with the edit it is kept (2 + 1, reserved 3); approved, 3 leave and cost 180.00, 2 are billed. `docs/SALES_CHAIN_RULES.md` says an offer's gift is judged afresh; it does not say a typed free quantity goes with a quantity change. The desktop editor sends no `free_quantity` on either path, so this is an API matter today |
| A line split across two batches | P, E: draft of 4 picked 1 N + 3 L. Same quantity, no batches sent: picks kept, nothing raised. **Quantity 4 → 5 with no batches sent: the picks are dropped** (the line names none, reserved N 5) as the rules doc says. `PUT` 5 as 2 N + 3 L, and 3 as 1 N + 2 L: the picks are stored; approval ships 1 N and 2 L (N 10 → 9, L 10 → 8), cost 180.00. Picks adding to 5 of 6 save and approval is 422 "Line 1: the batches chosen add up to 5.0000, and the line delivers 6.0000." An expired batch on the edit is 422 "…has expired." and the chain is as it was. **What is reserved is not what was picked: SELLQ-31** |
| The same lines sent as products, nothing changed | Read as a change: the note and order are withdrawn and raised again (counts 12 → 13), though quantity, price and total are the same. Harmless, but each such save spends a note number and an order number |
| The same source line twice (2 and 1) | Accepted: the bill becomes two lines of 2 and 1 on a new note. The bill's `version` did not move (2 → 2) because its header figures did not, so an `If-Match` taken before that edit still passes after it |

### Item 4: what an edit accepts, by role (an observation, not a defect)

One customer per try, made by the firm administrator, then `PUT /customers/{id}`
with the one change. Same on M and N.

| Changed on the edit | Field Sales | Sales Manager | Firm Manager | Firm administrator |
| --- | --- | --- | --- | --- |
| `credit_limit` 70000 | 403 (no `CUSTOMER_UPDATE`) | 403 "Changing a customer's credit limit needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)." | 200 | 200 |
| `opening_balance` 900 | 403 | **200**, outstanding 900.00, one journal posted | 200, journal | 200, journal |
| `payment_terms_days` 45 | 403 | **200** | 200 | 200 |
| cash discount 3% in 7 days | 403 | **200** | 200 | 200 |
| `default_discount_percent` 6 | 403 | 403 "Changing a customer's standing discount needs…" | 200 | 200 |
| name only | 403 | 200 | 200 | 200 |

So a Sales Manager who is refused an opening balance, credit days or
cash-discount terms on a **new** customer can save the customer plain and add
all three by editing it. Whether the edit should answer to the same code is the
owner's call.

## Regression pass

The round 3 scripts were run unchanged on fresh firms and each log compared
with its round 3 twin after replacing firm tags, ids and times. Every
difference is listed.

| Script and cases | Firm | Differences from round 3 | Reading |
| --- | --- | --- | --- |
| `g1.py` 040 to 047, 049 (walk-in and counter bills, services, a service return) | G | none but the order two journals of one document are listed in, and the random suffix of a loyalty reference | no change |
| `g2.py` 050 to 054 (charges on the bill) | G | none but journal order | no change |
| `g3.py` 064 to 072, 087 (hold, recall, shifts) | G | **064**: "change the quantity to 4" was 422, now 200; the bill approves for 472.00 where it approved for 354.00; stock 413 where 414. The script's next step still sends the first note's line ids and is refused 422 "Line 1 names a document that is not SI-26-27-000016's own…" | expected from #1198: the case passes as first written. The 422 is the script holding ids from before the edit, and the refusal is right |
| `g4.py` 029 (barcode, split tenders, over-tender) | G | none | no change |
| `rc1.py` 16, 18 (zero-total bills, returns before billing, five flavours) | G | none but journal order and the customer's running balance (G has more history than round 3's firm) | no change |
| `rc1.py` counter (SELLQ-17, 16, 21, 4, 12, 10, 11, 13) | G | SELLQ-12 and SELLQ-4 edits were 422, now 200; the two steps after them are refused "not its own" for the same stale-id reason; "drafts left" lists four where round 3's firm had none; the last two rows of the stock ledger differ | the first is the fix. The four drafts are the ones `g1` to `g3` leave on purpose (three of 10 and a held bill of 1, reserved 31, as on round 3's firm G). The ledger line prints rows 99 and 100 of a ledger that is longer on this firm: the script's limit, not the product; the stock figures beside it match |
| `d1.py` 015, 016 (return and credit note against a bill, and their cancels) | D | none but the order journals and loyalty rows are listed in | no change |
| `reg1.py` (eight returns and every reader) | M, N | CDNR row for return B: `against_invoice` was "", now the bill; GST register row for B the same; the return register's last column was empty, now `credited_amount` | expected from #1203. Balances 2,891.00 and 354.00, B2B, B2CS +300, HSN 28 / 2,750, 3B +2,750 / +550 / +99, analysis, rebate 2,900 / 400 / 50 / 2,450 and stock 70 are as round 3 |
| `e1.py`, `e2.py`, `e3.py` 019, 022 to 026 | E | **023**: editing a draft's picks to 1 + 3 by a product line was 422, now 200; approval then ships 1 N + 3 L (N 9, L 7) where it shipped 4 L, and the audit row names both batches; the untouched bill after it leaves N 5 where 6. An extra `fefo_skipped` audit row in 019's listing; two stock rows listed in the other order | 023 is the fix. The extra audit row is from item 2's batch corner, run on the same firm first; the listing shows the newest rows of the firm |
| `rp_pharma.py` (round 3's SELLQ-5 / 6 reproduction) | P | "dispatch the first order's note" was 422 short by 6, now 200 with M9 down to 2 and M4 10 / 10; a draft that chose L, its picks edited to 1 N + 3 L, showed L 4 reserved, now **N 4** | the first is #1200. The second is the edit now raising the order again, and a line split across batches reserving first-expiry-first: SELLQ-31 |

**Books, all six firms.** Trial balance balances (M and N Dr 62,272.09 / Cr
62,272.09; P 17,388.00; E 25,837.60; G 2,844,351.02; D 6,459.53); 1100 Trade
Receivables equals customers' outstanding less advances in each (M 17,408.64,
G 2,736,386.81, D 289.93); the stock valuation difference against 1200 is 0.00
in each; no journal is unbalanced (read 25 a page). Reserved stock came back to
0 on M and N; G holds the 31 of its deliberate drafts. One new 500 was recorded
by `/diagnostics/errors` in this round (SELLQ-27, four occurrences, all mine);
the other entries of today predate the restart.

No difference was left unexplained.

## New findings

Ids continue from round 3. Each was reproduced on two fresh firms unless said.

| Id | Severity | What | Reproduction | Expected / actual | Suspected cause |
| --- | --- | --- | --- | --- | --- |
| SELLQ-27 | Low | Quantity 0 sent back by its source line on a draft counter bill answers 500 | M, N (stages off): `POST /sales-invoices` 3 CTR for C03 (draft). `PUT` the line by its source fields with `current_invoice_quantity` "0" → **500** "An unexpected error occurred." Sent as a product line the same 0 is 422. Nothing is written: bill, note, order and reserved read as before | Expected 422 "Line 1 bills a quantity of 0 and supplies nothing free…", as a bill of somebody's delivery note still gives on the same edit (round 3 drove the zero on that kind of bill only). Actual: the schema's own refusal is raised inside the service and not caught. The code path is new in #1198 | `app/sales_invoice/services/sales_invoice_service.py:2220` (`_as_product_lines` builds `SalesInvoiceLineWrite`; its validator raises a pydantic `ValidationError`), called from `:1996` |
| SELLQ-28 | **Medium** | A price or discount changed on a draft counter bill without changing what ships is undone by the next quantity edit | M, N (stages off). **Discount**: draft 3 CTR at `discount_percent` 5 (336.30). `PUT` the same 3 with `discount_percent` "0" → 354.00 at 0%. `PUT` 4 by source line, nothing else → **448.40 at 5%**; approves at 448.40 (Cr 4000 380.00). **Price**: draft 3 CTR at 100 (354.00). `PUT` the same 3 with `unit_price` "90" → 318.60. `PUT` 4 echoing the bill's own `unit_price` 90 → **472.00 at 100**; `PUT` 5 with no price → 590.00 at 100. A new price sent in the same request as the quantity (6 at 80) is kept | Expected: 472.00 at 0%, and 424.80 at 90. Actual: the first, same-ship edit re-prices the bill only; its order and note keep the old terms (order line still 5% `percent`; note line still 100), and the re-raise reads the terms from them. A price equal to the bill's current one is taken for "unchanged" and replaced by the note's. The desktop sends each line's own `unit_price` back, which is that case | `sales_invoice_service.py:2171-2184` (`unit_price` unchanged → `note_line.unit_price`) and `:2186-2204` (discount read from the order line); `_ships_as_raised` at `:2081` lets a price-only edit through without touching the order or note |
| SELLQ-29 | Low | Freight and a bill discount on a draft counter bill are dropped by an edit that does not send them again | M, N: draft 3 CTR, `freight_amount` 50, `bill_discount_percent` 10 (377.60). `PUT` the same 3 with neither → 413.00: freight kept, **bill discount gone**. `PUT` 4 with neither → **472.00: freight gone too**. Sent with the edit, both hold (5: 590.00). The charges list and the buyer's name are kept when left out; `reference_number` and `remarks` are cleared by any edit that leaves them out | Expected: 483.80 for 4, or one rule for all of them. Actual: freight is inherited from the bill's order, and the order raised again has none | `sales_invoice_service.py:2000` (`restated` is built from the request alone, with no fall back to the bill's own freight and bill discount); `:3688` (`_inherited_freight`) |
| SELLQ-30 | Low | The sales-return summary counts header charges and rounding of a return that credited nothing | M, N: 5 delivered, never billed, 5 back against the note with `additional_charges` 50 (document 640.00): nothing credited, no journal but the cost entry, register `credited_amount` 0.00, by-customer 0.00, and `GET /sales-returns/summary` `total_return_value` **+50.00**. With `round_off` 0.40: +0.40. With 50 and -0.25: +49.75. A line charge of 10 (document 601.80) moves it by 0. On a part-billed return (4 delivered, 3 billed, 2 back, `additional_charges` 20) the customer is credited 138.00 (the whole 20 with the one billed unit) and summary and register agree | Expected: 0, as the register and by-customer say. Actual: the summary takes the document total less the unbilled share of the **lines**, so whatever sits on the header stays in | `app/sales_return/services/sales_return_service.py:338` (`grand_total - unbilled_value()`), `app/sales_return/billing.py:115` |
| SELLQ-31 | Low | A draft counter bill whose line is split across batches reserves first-expiry-first, not the batches picked | P, E (stages off): N (60 days, 10) and L (400 days, 10). Draft of 4 picked **1 N + 3 L** → reserved **N 4, L 0**. A draft that chose L alone reserves L 4 (as round 3); edited at the same quantity to 1 N + 3 L it now reads N 4, L 0. Approval ships what was picked (1 and 3) because L is free | Expected: 1 held on N and 3 on L. Actual: 3 of N are held that will not ship and the 3 of L that will are open to any other order; if one takes them the bill's approval is refused for stock. The code says so on purpose ("Several batches name no one to hold"), so this is a known limit now easier to reach, since every pick edit raises the order again | `app/sales_invoice/services/sales_chain_service.py:199` and `:535` (`_one_batch`) |
| SELLQ-32 | Not rated, outside selling | A large answer is cut off: the connection is reset though the server logged 200 | On M at 23:40: `GET /finance/journal-entries?page_size=100` failed **8 of 8** tries with WinError 10054 after about 19 seconds each, through two HTTP clients; `GET /customers?page_size=100` (122,673 bytes) failed 4 of 8; the same routes with `page_size=25` (35,656 bytes) answered 8 of 8. The server log shows each request completed 200 in under 100 ms. Seen earlier in the round on the same two lists, where two scripts gave up after three resets | Expected: the page arrives. Not established whether this is the server or the machine (1.8 GB of memory free at the time, another agent provisioning firms); round 2 and round 3 recorded the same resets and put them down to provisioning. It did not go away when asked again, which a passing lock would | not found |

Smaller things seen and not given an id: a coupon sent again on an edit that
ships the same is 422 "…This bill continues documents already priced, so it
cannot take one." though the same coupon on an edit that changes the quantity
is taken (the coupon is kept either way when left out, and the claims of the
withdrawn orders read REVERSED); a hand-picked batch that other orders hold is
refused only at dispatch, the note saving and approving first; the picker's
pre-fill for a line that holds two batches offers the first batch for all of
it once that batch has free stock, which is also what an untouched note ships;
GSTR-3B still returns floats (247.49999999999994).

## Case-text corrections needed

Changes to `docs/INDEPENDENT_TEST_CASES.md` on top of round 3's table.

| Case | What the text must now say |
| --- | --- |
| TC-SELL-064 | Drop round 3's interim wording. The case stands as first written: change the quantity to **4**, *Received now* 472, and the bill approves for 4 (472.00). Add: "The note and order the first save raised read CANCELLED, 'Bill … was changed before approval.', and a new pair carries the 4; their numbers are spent." Until SELLQ-28 is settled, do not change a price or discount in a save of its own before changing the quantity |
| TC-SELL-023 | "**(HTTP)** the picks of a saved counter bill are edited either way: the line sent back by its source fields, or as a product line." Replace round 3's "shows the 4 reserved on the later batch" with: "a bill that chose one batch shows the 4 reserved on it; a line split across batches is reserved first expiry first until approval (SELLQ-31)." Add: "changing the quantity without sending the picks again clears them" |
| TC-SELL-024 | Remove round 3's "with no other order waiting on the product". Add a step: "with a second, ordinary order holding the 4-month batch, the first order's untouched note still ships the 9-month batch and the other order's reservation stays" |
| TC-SELL-019 | Add: "A batch picked by hand that other orders hold in full is refused at dispatch: 'Line 1: Batch … holds 0.0000 available here, and 5.0000 is chosen from it. Choose less from it, or another batch.'" |
| TC-SELL-032 | Add: "The Field Sales user's new customer carries no money terms: a credit limit, an opening balance, credit days, cash-discount terms or a standing discount is refused (403) naming CUSTOMER_MANAGE_SETTINGS. Zero or blank is not refused." |
| TC-SELL-028 | Add: "`GET /api/v1/enquiries/follow-ups-due` is paged like the list: `page_size` above 100 is 422." |
| TC-SELL-015 | Add to round 3's wording: "Reports > Sales returns value a return at what was credited: the register shows `credited_amount` and `unbilled_quantity` beside the document total, and by customer, by product and the summary add up the credited figure." And: "a return raised against a delivery note names the bill it credits in the GST sales register and in GSTR-1 CDNR." |
| TC-SELL-077 | Add: "A receipt entered after the promise counts toward it whatever date it carries, up to the promised day: yesterday's cash keyed in today keeps the promise. A receipt dated after the promised day does not." |
| Round 3's SELLQ-4 wording, wherever a case quotes it | The message for a bill of somebody's documents no longer ends "A product cannot be added to a saved bill, nor a line raised above the quantity it was saved for; cancel this draft and raise the bill again." A saved **counter** bill now takes product lines |
| New cases wanted | (1) a saved counter bill cut down, grown, and given another product before approval: bill, note, order, reserved stock and what leaves agree after each save, and a refused save changes nothing. (2) the customer money terms by role, on the form, the batch import and the file import |

## Not verified

- Nothing on screen: the desktop's uncapped quantity box on a saved counter
  bill, the locked money-term boxes on a new customer, the batch picker's
  pre-fill and the paged follow-up list were not opened. What the desktop
  sends was read from `sales_invoice_editor_dialog.dart` only.
- Item 2 with serial-tracked products, with a second unit of measure or
  packaging, with a gift added by an offer, and with two people editing the
  same draft at once was not driven.
- Item 3's pinned-batch orders were covered only by the unchanged round 3
  cases (025); a pinned order competing with the new release order was not
  driven.
- Item 5: the promise was read as PENDING after a receipt dated past its day;
  that it then reads Broken on the collection sheet was not seen, because the
  bill it names is paid and leaves the sheet.
- Item 6's corner was driven for a return against a delivery note only; the
  cash-discount column does not exist in the customer file template, so that
  term could not be tried through the file.
- SELLQ-32's cause. It was measured on one firm in one ten-minute window.
- The causes given for every finding are from reading the code.
- Of round 3's regression set, 031 and 035 (cash discount, messaging) and the
  generic checks script were not run again: #1198 to #1203 do not touch them.
