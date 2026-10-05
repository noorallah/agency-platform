# Buying and selling: checked through the API, round 8, 2026-10-06

A short closing re-check of the two things round 7 found (R7-1, now D-STK-17,
#1230; R7-2, now D-SELL-87, #1231) and a last regression pass, driven the same
way as round 7: the real server over HTTP at http://127.0.0.1:8000, on `main`
at `76329d19`, fixture firms only, books read back through the API, nothing
read from the database, no source file changed and nothing fixed. The round 7
file is left as it was.

**Both fixes hold, the regression pass shows no regression, and the round
found no new defect in buying or selling.** Two small things were seen on the
way and are given ids so they are not lost (R8-1, R8-2, both Low, neither
caused by the two fixes, neither on the buying or selling path).

| # | Item | Result |
| --- | --- | --- |
| 1 | D-STK-17 (was R7-1), a batch is out of date on its expiry date everywhere (#1230) | **Fixed.** Reproduced on two firms; every other row of the table unchanged |
| 1a | Shelf life: a batch expiring exactly on the day the goods must last to | **Unchanged, as intended.** Given on the day, refused one day short |
| 1b | A serial in a batch expiring today, refused at dispatch | **Not driven.** No fixture has a serialised batched product, and a pharmacy firm cannot record a serial (see R8-2) |
| 2 | D-SELL-87 (was R7-2), a bill with no due date is due the day it is raised (#1231) | **Fixed.** Seven selling readers and six buying readers agree |
| 3 | Last regression pass | **No regression.** Every differing line is explained below |
| 4 | Books on the four firms | Balanced; 1100, 2100 and 1200 agree, bar one paisa on one pharmacy firm, traced below |

## When, and on which firms

The whole round ran between **03:40 and 03:51 IST on 6 October 2026, which is
22:10 to 22:21 UTC on 5 October**. Every check was made while the server's UTC
day (2026-10-05) was one behind the firm's day (2026-10-06). The server was not
restarted, no request failed with a connection error, and no script printed a
5xx. `/health` answered before and after.

Four fixture firms, all built by `backend/scripts/test_fixture.py` in this
round (03:40:25 to 03:42:03 IST):

| Key | Fixture | Firm | Used for |
| --- | --- | --- | --- |
| P | `pharma-firm` | `T1006H9O8-P` | item 1; one import of the buying regression (`r3b.py`) |
| E | `pharma-firm` | `T1006HEYB-P` | item 1 again; buying regression (`r4d.py`, `r3b.py`) |
| G | `selling-firm` | `T1006AHUM-S` (GSTIN put on it by the regression) | selling regression, then item 2 (selling) |
| C | `ready-firm` | `T1006B98N-R` | buying regression (`r4a.py`), then item 2 (buying) |

No round 7 firm was read or written. Scripts and logs are in the scratchpad
folder `round8` beside `round7`; the round 7 files were copied, not changed,
and round 7's logs sit in `round8/old7` for the comparisons.

## Item 1: D-STK-17, the expiry rule on the expiry date

P at **03:44:53 to 03:45:02 IST** (22:14 UTC on the 5th), E at 03:45:03 to
03:45:11; the add-on checks on P at 03:45:37 to 03:45:45 and on E at 03:46:12
to 03:46:19. Round 7's own scripts, unchanged (`b/r7p.py`, `b/r7c.py`,
`b/r7f.py`), so the logs compare line for line with round 7's; then
`b/r8x.py` for what round 7 did not drive. The two firms' logs are identical
after masking codes.

Same set-up as round 7: 6 of the batched product received as three batches
expiring 2026-10-05, -06 and -07, beside the fixture's own batches (one long
expired, one of 20 days, one of 400). Every document dated 2026-10-06, for 1
unit. Bold marks what changed since round 7.

| Place | Batch expiring **today** (2026-10-06) | Expired **yesterday** (2026-10-05) | Expiring **tomorrow** (2026-10-07) |
| --- | --- | --- | --- |
| (a) Picker, `batches/availability` | `days_to_expiry` 0, `expired` true, `available_to_line` 0 (6 on hand) | -1, `expired` true, 0 | 1, `expired` false, `near_expiry` true, 6 |
| (b) Sales order pinned to the batch | saves (201); approve 422 "Line 1: the batch the customer asked for, R7-T06-7832, has expired." | saves; approve 422, the same words | saves, approves |
| (c) Delivery note, batch pinned on the order | not reached: the order cannot be approved | not reached | note saves, approves, dispatches, ships that batch |
| (c) Delivery note, batch picked on the note | note saves and approves; dispatch 422 "Line 1: batch R7-T06-7832 expired on 2026-10-06." | saves, approves; dispatch 422 "Line 1: batch R7-T05-7832 expired on 2026-10-05." | dispatches |
| (c) Delivery note, **no batch named** | **passed over** (round 7: shipped) | passed over | **dispatch 200, and the batch shipped is this one**, R7-T07 |
| (d) Counter bill, batch picked on the line | save 422 "Line 1: the batch the customer asked for, R7-T06-7832, has expired." | save 422, the same words | saves and approves, ships that batch |
| (d) Counter bill, **no batch named** | **passed over, twice** (round 7: shipped, twice) | passed over | **saves and approves, and the batch shipped is this one**, both times |
| (e) Expiry dashboard | in `expired_today` and `total_expired`; not in `expire_in_7_days` | in `total_expired` | in `expire_in_7_days` and `expire_in_30_days` |
| (e) Batch summary card | in `expired`, not in `near_expiry` | in `expired` | in `near_expiry` |
| (e) Stock alerts, `GET /inventory/alerts` | not listed | not listed | listed while it holds stock: "R8-S07-686A expires 2026-10-07" |
| (e) Batch list, `expiry_before=2026-10-06` | listed | listed | listed only from `expiry_before=2026-10-07` |
| (e) `GET /purchase-returns/reports/expired`, `batches/returns-due` | empty | empty | empty |

The masked comparison of this round's `r7p` and `r7c` logs with round 7's shows
exactly these lines and no other: the batch on the unpinned note and on the two
unpinned counter bills is R7-T07 where it was R7-T06, and at the end the batch
of the 6th still holds **6 of 6** (round 7: 3 of 6) while the batch of the 7th
is used up (its 6 went to the unpinned note, the pinned note, the picked note
and three counter bills). Availability with `as_of` for the 5th, 6th and 7th,
the cards, the three refusals and their words are unchanged.

**Reservation at approval** (`r8x.py reserve`, both firms). An unpinned order
of 1 approved: the only batch whose `reserved` moved is the fixture's 20-day
batch, 5.0000 to 6.0000 (the batch of the 7th was empty by then). The batches
of the 5th and the 6th stayed at `reserved` 0.0000. The note then shipped that
20-day batch. **Not on the today-batch.**

**The today-batch as the only stock** (`r8x.py only`, both firms). A new
batched product with one batch, 6 units, expiring 2026-10-06:

| Step | Result |
| --- | --- |
| Picker | `days_to_expiry` 0, `expired` true, `available_to_line` 0 |
| Sales order of 1, no batch; approve | 201, 200 APPROVED. It is a **back order**: the batch's `reserved` stays 0.0000; the product's unbatched stock row reads on hand 0, reserved 1, available -1; `GET /sales-orders/reports/back-orders` lists the order with `available_stock` 0.0000. The fixture's own back order (10 ordered of 3 on hand) sits the same way (3 / 10 / -7) |
| Delivery note, no batch; approve; dispatch | 201, 200, **422** "Insufficient available stock to dispatch: short by 1.0000. 6.0000 of this product's stock is past its expiry date (R8-ONLY-T06-686A expired 2026-10-06) and cannot be dispatched: write it off or quarantine it." The note line carries no batch |
| Stages off, counter bill of 1, no batch | saves (201 DRAFT); **approve 422**, the same words. Draft cancelled |
| At the end | 6 on hand in the batch, nothing reserved |

**Fixed.** On its expiry date a batch is now refused when named and passed
over when nobody names one.

### 1a. Shelf life, said to be untouched

`r8x.py shelf`, P at 03:45:40 to 03:45:44, E at 03:46:15 to 03:46:19. A fresh
batch of 6 expiring 2026-10-07 received first (R8-S07), since round 7's was
used up.

| Customer | Unpinned order, note, dispatch | Note picking the batch of the 7th |
| --- | --- | --- |
| `minimum_shelf_life_days` 1 (goods must last to 2026-10-07, **exactly** the batch's expiry date) | dispatch 200, ships **the batch of the 7th** | dispatch 200, ships it |
| `minimum_shelf_life_days` 2 (must last to 2026-10-08, the batch is one day short) | dispatch 200, **passes it over** and ships the 20-day batch | dispatch **422** "Line 1: batch R8-S07-686A (expires 2026-10-07, 1 day left) expires before 2026-10-08, the customer's minimum shelf life. Choose a later batch, or change the customer's minimum shelf life." |

Good on the day is long enough; one day short is not. As the fix said.

### 1b. A serial in a batch expiring today

**Not driven, because it cannot be on these fixtures.** No fixture builds a
product tracked by serial and by batch (the pharmacy fixture's two products are
batch-only and plain; the electronics fixture's is serial-only). An attempt on
P to make one (`r8x.py serial`) got as far as the product and its opening stock
and stopped at the serials: `POST /batch-serial/serials` → **403** "This firm's
business profile does not enable: SERIAL_NUMBER." See R8-2. The serial check at
dispatch was read in the fix's diff, not exercised.

## Item 2: D-SELL-87, a bill with no due date

### Selling

G, `b/r8d.py … sell`, **03:47:04 to 03:47:08 IST** (22:17 UTC on the 5th),
after the regression had run on the firm. A customer with
`payment_terms_days` 0; with the order and note stages off, two credit bills
of 118.00 approved, no due date sent: **SI-26-27-000068 dated 2026-10-05** and
**SI-26-27-000069 dated 2026-10-06**. Stages switched back on.

| Reader | Bill of the 5th | Bill of the 6th |
| --- | --- | --- |
| The bill itself, `GET /sales-invoices/{id}` | `due_date` **null** (on save, after approval, on read back) | `due_date` null |
| `GET /customers/ageing` (no `as_of`, and `as_of=2026-10-06`) | due 2026-10-05, `days_overdue` **1** | due 2026-10-06, `days_overdue` 0 |
| `GET /customers/ageing?as_of=2026-10-05` | `days_overdue` 0 | not listed |
| `GET /collections/sheet` (no `as_of`, and `as_of=2026-10-06`) | due 2026-10-05, `days_overdue` **1** (round 7: null, 0) | due 2026-10-06, 0 |
| `GET /collections/sheet?overdue_only=true` | **listed** (round 7: left out) | not listed |
| `GET /sales-invoices/reports/overdue` | **listed**, due 2026-10-05, `days_overdue` 1 (round 7: not listed) | not listed |
| `GET /sales-invoices/reports/due` (no `days`, `days=0`, `days=7`) | not listed | **listed**, due 2026-10-06, `days_until_due` 0 |
| `GET /sales-invoices/reports/summary` | `overdue_invoices` 0 before the two bills, **1** after | not counted |
| `GET /receipts/outstanding` | `due_date` 2026-10-05, 118.00 | `due_date` 2026-10-06, 118.00 |

All agree. **Fixed.**

### Buying

C, `b/r8d.py … buy`, **03:48:26 to 03:48:30 IST**. A supplier with
`payment_terms_days` 0; two supplier bills of 236.00 off their own order and
receipt, approved, no due date and no payment terms sent:
PI-…-000013 dated 2026-10-05 and PI-…-000014 dated 2026-10-06. Both read back
with `due_date` null.

| Reader | Bill of the 5th | Bill of the 6th |
| --- | --- | --- |
| `GET /purchase-invoices/reports/overdue` | listed, due 2026-10-05, `days_overdue` 1 | not listed |
| `GET /purchase-invoices/reports/due` | not listed | listed, due 2026-10-06, `days_until_due` 0 |
| `GET /purchase-invoices/summary` | `overdue_invoices` 0 before, **1** after | not counted |
| `GET /purchase-invoices/reports/vendor-ageing` | `as_of` 2026-10-06, 2 bills, 472.00, `oldest_days` **1** | in the same row |
| `GET /purchase-invoices/reports/payables` | 472.00 for the supplier as of the 6th, 236.00 with `as_of=2026-10-05`; `basis=due` gives the same; the report's own check against 2100 reads difference 0.00 | |
| `GET /payments/outstanding` | `due_date` 2026-10-05 | `due_date` 2026-10-06 |

**No reader disagrees.** The payables report is by month, so both bills sit in
the current month's column on either basis; it has no day count to compare.
`vendor-ageing` takes no `as_of` (the parameter is ignored because it is not
declared), which is how it was.

## Item 3: the regression pass

Round 7's scripts, unchanged, compared with round 7's logs by the same
comparers (`cmp6.py`, `cmpb6.py`). **This round ran the selling scripts on a
selling firm with nothing else on it** (03:42:22 to 03:44:22 IST), where round
7 ran them after its own items 3 and 4 had used the firm. So the differences
from round 7 are round 7's history taken away again, and the same logs were
also compared with **round 6's**, which ran on a clean firm like this one.

| Script and cases | Firm | Against round 7 | Against round 6 (clean firm) | Reading |
| --- | --- | --- | --- | --- |
| `g4.py` 029 | G | none | none | |
| `g1.py` 040 to 047, 049 | G | stock one higher (496 for 495); journals 10 for 35; one loyalty balance for two; no HSN row of 84.00 and the 3402 row one unit lower | none (2 lines moved) | round 7's firm history, absent here |
| `g2.py`, `g3.py` 050 to 054, 064 to 072, 087 | G | the same stock and HSN lines; the shift list one row shorter, "no journal matching SHIFT"; `is_held=false` 20 for 24; journals 55 for 80; "Field Sales lists shifts" 9 for 10 | none (2 lines moved) | round 7's item 3 shift and item 4 bills, absent here |
| `rc1.py` 16, 18 | G | stock figures one higher | none | the same unit |
| `rc1.py` counter | G | stock one and two higher (detergent 100 for 98); the ledger tail reads `RESERVE`, `UNRESERVE` where round 7 read `UNRESERVE`, `DISPATCH` | none | history. This also settles round 7's inferred reading of that ledger line: on a clean firm it reads as round 6 did |
| `i7.py` | G | one line, two tied claims in the other order | none | ordering |
| `s1.py` 3 and 4 | G | three lines, the same | none | ordering |
| `gst6.py` | G | none | none | |
| `reg1.py` (eight returns, every reader) | G | journals of four returns in another order; GSTR-1 rows in another order; `credit_notes_deducted` starts 1,500.00 / 270.00 for 1,584.00 / 285.12 and moves by the same +550.00 / +99.00; the books line | journals of five returns and the GSTR-1 rows in another order, nothing else | ordering of rows that tie; round 7's extra 84.00 return, absent here |
| `r4a.py` S1 to S8 | C | none | | |
| `r4d.py` BATCH, IMPORT | E | one line, a random batch number quoted in a refusal | | a random number |
| `r3b.py` IMPORT | E, P | "returns before 7 … after 8" for 8, 9; second block "before 0 … after 1" for 9, 10 | | counts of returns already on the firm; this round's second slot was P where round 7 used E twice |

**Nothing is unexplained, and nothing in the regression logs comes from #1230
or #1231**: none of these scripts ships a batch on its expiry date or reads a
bill with no due date. What those two changed is in items 1 and 2.

Two slips of mine, the same two as round 7 and none of the product's: the
chain started `reg1.py` with the wrong firm letter and it stopped at sign-in
before sending anything; `r3b.py` first stopped on a missing slot in the state
file. Both were run again and the table shows the second run. `d1.py` (015,
016) needs a `selling-invoiced` fixture and was not run.

### The books at the end

`b/books8.py`, 03:50:53 IST, after everything above.

| Firm | Trial balance | Checks |
| --- | --- | --- |
| G `T1006AHUM-S` | balanced, 2,855,043.09 | 1100 2,740,447.66 = customers; no supplier owed and payables 0; valuation 27,120.00 = 1200; no unbalanced journal |
| C `T1006B98N-R` | balanced, 11,972.00 | 1100 -500.00 = customers 0.00 less the fixture's advance of 500.00; payables 472.00 = 2100, difference 0.00; valuation 11,127.27 = 1200; 63 journals, none unbalanced |
| P `T1006H9O8-P` | balanced, 4,656.00 | 1100 336.00 = customers; no bill owed, payables 0; valuation **3,759.89** against 1200 at 3,759.90, DIFFERENCE -0.01 |
| E `T1006HEYB-P` | balanced, 6,498.35 | 1100 336.00 = customers; payables 604.80 = 2100; valuation 5,537.45 = 1200 |

**The paisa on P, traced** (`b/val6.py P`). It is on the batched product, and
it comes from three dispatches:

- Opening 30 at 60 and three receipts of 6 at 50 give 48 units worth 2,700.00,
  an average of exactly 56.25. Seven dispatches of 1 each credit 1200 with
  56.25: no rounding. 41 units, 2,306.25.
- The shelf-life receipt of 6 at 50 (GRN …-000005) makes 47 units worth
  2,606.25, an average of **55.452127…**.
- **DN-26-27-000012, -000013 and -000014** then each credit 1200 with
  **55.45**, the average rounded to the paisa: 166.35 in all, where three units
  at the unrounded average are 166.356.
- So 1200 holds 2,439.90 for the product, and the report shows 44 units at the
  average, 2,439.8936, as 2,439.89.

It is the **ledger** that carries the extra paisa, not the report: each issue
is posted rounded to the paisa and the 0.0021 dropped each time stays in the
stock account. The report is the quantity times the running average and is the
nearer figure. Nothing is lost or unbalanced; the journal of each dispatch
balances and the report shows the difference on its own DIFFERENCE row.

E went through the same three dispatches at 55.45 (the 1200 lines are
identical to P's up to that point), so it carried the same paisa then; it was
not read at that moment, and by the end later purchase returns on the same
product (three at 56.61 and 56.78, two more of 343.47 and 228.98) had rounded
the other way and the two figures agree. This is the same thing rounds 6 and 7
saw.

## New findings

Provisional ids. Neither is caused by #1230 or #1231, and neither is on the
buying or selling path.

| Id | Severity | What | Where |
| --- | --- | --- | --- |
| R8-1 | Low | The batch summary card counts an emptied batch as near expiry; the expiry dashboard and the stock alerts do not | `app/batch_serial/services/batch_serial_service.py:666` (no stock test) against `:724` and `:749` (`holds_stock`) |
| R8-2 | Low | A serial-tracked product can be made and stocked on a firm whose profile does not enable serials | product create and opening stock accept `track_serial`; `POST /batch-serial/serials` is where the 403 is |

### R8-1 -- the summary card counts an empty batch as near expiry (Low)

P and E, 03:46:19 and 03:47:03 IST (`b/r7f.py`, `b/r8q.py`).

1. On a pharmacy firm, use up a batch that expires tomorrow (here R7-T07-7832,
   2026-10-07: `GET /batch-serial/batches` shows it `AVAILABLE`, quantity 0),
   and hold stock in two other batches expiring within 30 days (R8-S07, 4
   units, 2026-10-07; the fixture's B2, 2026-10-26).
2. `GET /batch-serial/batches/summary` → `near_expiry` **3**.
3. `GET /batch-serial/batches/expiry-dashboard` → `expire_in_7_days` **1**,
   `expire_in_30_days` **2**. `GET /inventory/alerts` → `near_expiry` **2**,
   naming the two batches that hold stock.

**Expected:** the cards agree on how many batches are near expiry. **Actual:**
the summary counts batch records whatever they hold; the dashboard and the
alerts count batches holding stock. The same would hold for `expired` on the
summary once an expired batch is written off; that was not driven. Not new
behaviour: round 7 did not empty a batch, so it did not show.

### R8-2 -- a serial-tracked product on a firm with no serials (Low)

P, 03:45:44 IST (`b/r8x.py serial`). Seen while trying to drive item 1b.

1. On a pharmacy firm, `POST /products` with `track_batch`, `track_expiry` and
   `track_serial` all true → **201**, `track_serial` true.
2. Opening stock of 4 for it in two batches → 201, post 200.
3. `POST /batch-serial/serials` for it → **403** "This firm's business profile
   does not enable: SERIAL_NUMBER."

**Expected:** the product is refused the serial flag where the firm cannot
record a serial, or the serials can be recorded. **Actual:** the firm now
holds 4 units of a serial-tracked product with no serial and no way to record
one. Whether those units can be sold was **not driven**; the product and its
stock were left as they are on P.

### Seen, not filed

- **An order for stock that is all out of date is approved as a back order,
  not refused**, and the refusal comes at dispatch (or at approval of a counter
  bill). The order line's own `available_stock` reads 6.0000 (it counts the
  out-of-date batch) while the back-order report reads 0.0000 for the same
  line. Item 1.
- **The refusal says the stock "is past its expiry date"** on the expiry date
  itself, beside "expired 2026-10-06". The wording, not the rule.
- **Round 7's "seen, not filed" list stands unchanged**: a pinned order to an
  expired batch saves and is refused at approval, a note picking one saves and
  approves and is refused at dispatch, a counter bill is refused at save.
- **One paisa between valuation and the stock account on P**, traced above.

## The scripts

New in `round8`: `b/r8x.py` (reservation, the today-batch as the only stock,
shelf life, the serial attempt), `b/r8d.py` (item 2, selling and buying),
`b/r8q.py` (the fixture's back order and the batch list beside the cards),
`b/r8pay.py` (the payables report's parameters and bases), `b/books8.py` (the
closing books on all four firms), `run8.py` (the regression chain). Item 1's
table is round 7's `r7p.py`, `r7c.py`, `r7f.py` unchanged; the regression is
`reg6.py`, `reg1.py`, `r4a.py`, `r4d.py`, `r3b.py`, `books.py`, `books6.py`,
`val6.py` unchanged. Fixtures by `mk6.py`. Every script and edit went through
the file tool; none through a shell heredoc.

Left on the firms: on P and E the batches of the 5th and the 6th (6 each),
4 of the second batch of the 7th, the only-stock product with its 6, two
shelf-life customers, and cancelled orders and notes from the refused
dispatches; on P also the serial-tracked product with 4 units and no serial,
and one imported purchase return; on G the round-eight customer with two open
bills of 118.00; on C a supplier with two open bills of 236.00.

## Not verified

- **Nothing on screen.** The desktop was not opened.
- **Nothing was read from the database.** That every store is at
  `20261005_0333` and that the server runs `76329d19` were taken from the
  hand-over; `git log` in the checkout shows that commit on top.
- **Everything was driven once, in one window** (03:40 to 03:51 IST), item 1
  on two firms, item 2 on one firm each side. Nothing was re-run after 05:30
  IST, when the two days agree.
- **Item 1:** quantities of 1 only. Not driven: a line split across batches; a
  **serialised product** (1b, could not be); a product with a stop-selling
  window; a batch marked EXPIRED by hand; a sales invoice raised from a note; a
  stock transfer or a purchase return of the today-batch; documents dated other
  than the 6th; the only-stock case for a batch that expired yesterday (so
  "back order at approval, refused at dispatch" was not compared with it).
  Reservation was read off the batch picker's `reserved` figures, once per
  firm, with the batch of the 7th already empty; with stock in it the
  reservation would be expected there and that was not seen. The shelf-life
  check was driven with the default policy only (the route for the sale policy
  was not found; `GET /batch-serial/sale-policy` is 404).
- **Item 2:** one customer and one supplier, terms of 0 days, bills dated the
  5th and the 6th only. Not driven: a customer with no terms set at all, a
  bill partly paid, the collection sheet PDF, overdue interest
  (`GET /customers/{id}/overdue-interest` answered 422 for want of parameters
  and was left), reminders, and MSME dues (0 rows). The summaries' overdue
  counts were read as a before-and-after on the firm, not per bill.
- **Regression:** `d1.py` (015, 016) not run. The comparers mask document
  numbers, dates and clock times, so a difference that was only a number or a
  time would not show. The TC-BUY case scripts (`b01.py` to `b10b.py`) build
  on TEST01 and were not run, as in rounds 6 and 7. The dated reads of round
  7's item 5 (`r7d.py` beyond the receivable and payable readers) were not
  repeated.
- **Books:** 2100 was checked against the payables report and its own check
  against the ledger, not against the supplier masters. The paisa on E was
  inferred from its 1200 lines, not read at the moment it stood.
- **The causes** given for R8-1 and for the paisa are from reading the code
  and the journal lines named; R8-2's cause was not read.
