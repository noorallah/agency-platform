# Buying and selling: checked through the API, round 7, 2026-10-06

A short re-check of the three things round 6 left open (R6-1, R6-2, R6-3) and
a sanity pass over what the date sweep touched (#1223, #1226, #1228), driven
the same way as round 6: the real server over HTTP at http://127.0.0.1:8000,
on `main` at `79a72cfd`, fixture firms only, books read back through the API,
nothing read from the database, no source file changed and nothing fixed. The
round 6 file is left as it was.

**All three fixes hold, and the sanity pass found no regression. One thing is
new and it is about the expiry rule, not the date (R7-1): the places that
judge a batch on its expiry date do not agree with each other.** A second,
smaller disagreement between two receivable readers was seen on the way
(R7-2).

| # | Item | Result |
| --- | --- | --- |
| 1 | R6-1, the batch picker and expiry cards use the firm's day (#1226) | **Fixed** |
| 2 | The expiry rule on the expiry date | Reported below, not judged. **The places disagree: R7-1** |
| 3 | R6-2, counter shifts use the firm's day (#1228) | **Fixed.** The report's Opened and Closed lines still print UTC, and say so |
| 4 | D-MST-16 (was R6-3), a cancelled invoice does not hold the opening balance (#1227) | **Fixed** |
| 5 | Sanity pass on the date sweep | **No regression.** Every differing line is explained below; every dated read reached reads the 6th |

## When, and on which firms

The whole round ran between **03:13 and 03:22 IST on 6 October 2026, which is
21:43 to 21:52 UTC on 5 October**. Every check below was made while the
server's UTC day (2026-10-05) was one behind the firm's day (2026-10-06). The
server was not restarted, no request failed with a connection error, and no
script printed a 5xx.

Four fixture firms, all built by `backend/scripts/test_fixture.py` in this
round, first time:

| Key | Fixture | Firm | Used for |
| --- | --- | --- | --- |
| P | `pharma-firm` | `T1006MCVJ-P` | items 1, 2; stock reports |
| E | `pharma-firm` | `T1006U2ZF-P` | items 1, 2 again; buying regression (`r4d.py`, `r3b.py`) |
| M | `selling-firm` | `T1006PQ9Q-S` (GSTIN 33FXSEL4360A1Z5 put on it by the regression) | items 3, 4; selling regression; selling-side dated reads |
| C | `ready-firm` | `T1006B3N7-R` | buying regression (`r4a.py`); buying-side dated reads |

C is one more firm than the hand-over suggested: the purchase-return
sequences (`r4a.py`) need a `ready-firm`. No round 6 firm was read or written.
Scripts and logs are in the scratchpad folder `round7` beside `round6`; the
round 6 files were copied, not changed.

## Item 1: the batch picker and the expiry cards (R6-1)

P at **03:13:09 IST / 21:43:09 UTC on the 5th**, E at 03:13:33 IST
(`b/r7p.py`). On each, 6 of the batched product received as three batches
expiring 2026-10-05, -06 and -07 (all three receipts accepted). The two firms'
logs are identical after masking codes.

`GET /batch-serial/batches/availability` for the product and warehouse:

| Batch expires | no `as_of` | `as_of=2026-10-06` | `as_of=2026-10-05` | `as_of=2026-10-07` |
| --- | --- | --- | --- | --- |
| 2026-10-05 | days -1, expired, to line 0 | days -1, expired, to line 0 | days 0, expired, to line 0 | days -2, expired |
| 2026-10-06 | **days 0, expired, to line 0** | **days 0, expired, to line 0** | days 1, not expired, to line 6 | days -1, expired |
| 2026-10-07 | days 1, not expired, near, to line 6 | the same | days 2 | days 0, expired, to line 0 |
| fixture's 20-day batch (2026-10-26) | days 20 | days 20 | days 21 | days 19 |

With no date sent every row equals the row for `as_of=2026-10-06` (round 6
read the answer for the 5th here). **Fixed.**

The cards, same minute, both firms:

- `GET /batch-serial/batches/expiry-dashboard`: `expired_today` **1** (the
  batch of the 6th), `total_expired` **3** (the fixture's expired batch, the
  5th and the 6th), `expire_in_7_days` 1 (the 7th), `expire_in_30_days` 2
  (the 7th and the 20-day batch). Round 6 read `expired_today` as the batch of
  the 5th and `total_expired` 2.
- `GET /batch-serial/batches/summary`: `expired` 3, `near_expiry` 2.
- `GET /inventory/alerts` (03:22 IST): `near_expiry` 2, naming the batch of
  the 7th and the 20-day batch; the batch of the 6th is not "near".

All judged on the 6th. **Fixed.**

## Item 2: what each place does on the batch's expiry date

Recorded, not judged. P and E gave the same answers (`b/r7p.py`, `b/r7c.py`,
`b/r7f.py`; 03:13 to 03:14 IST, and 03:22 for the alerts). Every document was
dated 2026-10-06, for 1 unit, with stock in all three batches. The sales
order and delivery note were driven with the firm's stages on; the counter
bills with the order and note stages switched off for the run and switched
back on after.

| Place | Batch expiring **today** (2026-10-06) | Expired **yesterday** (2026-10-05) | Expiring **tomorrow** (2026-10-07) |
| --- | --- | --- | --- |
| (a) Picker, `batches/availability` | `days_to_expiry` 0, `expired` **true**, `available_to_line` **0** (6 on hand) | -1, `expired` true, 0 | 1, `expired` false, `near_expiry` true, 6 |
| (b) Sales order pinned to the batch (`pinned_batch_id`) | saves (201); **approve 422** "Line 1: the batch the customer asked for, R7-T06-58E7, has expired." | saves; approve 422, the same words | saves, approves |
| (c) Delivery note, batch pinned on the order | not reached: the order cannot be approved | not reached | note saves, approves, **dispatches**, ships that batch |
| (c) Delivery note, batch picked on the note (`batches`) off an unpinned order | note saves (201) and approves (200); **dispatch 422** "Line 1: batch R7-T06-58E7 expired on 2026-10-06." | saves, approves; dispatch 422 "Line 1: batch R7-T05-58E7 expired on 2026-10-05." | dispatches |
| (c) Delivery note, **no batch named** (first expiry first) | **dispatch 200, and the batch shipped is this one**, R7-T06 (expires today) | passed over | not chosen while the batch of the 6th has stock |
| (d) Counter bill, batch picked on the line (`batches`) | **save 422** "Line 1: the batch the customer asked for, R7-T06-58E7, has expired." | save 422, the same words | saves and approves, ships that batch |
| (d) Counter bill, **no batch named** | **saves and approves, and the batch shipped is this one**, R7-T06; done twice, both times this batch | passed over | not chosen |
| (e) Expiry dashboard | counted in `expired_today` and in `total_expired`; not in `expire_in_7_days` | in `total_expired` | in `expire_in_7_days` and `expire_in_30_days` |
| (e) Batch summary card | in `expired`, not in `near_expiry` | in `expired` | in `near_expiry` |
| (e) Stock alerts, `GET /inventory/alerts` | not listed as near expiry (there is no "expired" alert kind) | not listed | listed: "R7-T07-58E7 expires 2026-10-07" |
| (e) Batch list, `expiry_before=2026-10-06` | listed (the filter is "on or before") | listed | listed only from `expiry_before=2026-10-07` |
| (e) `GET /purchase-returns/reports/expired`, `GET /batch-serial/batches/returns-due` | empty (no return was raised; no return rule on the product) | empty | empty |

**Where they disagree.** Every place that is asked about a named batch says a
batch is expired **on** its expiry date: the picker, the cards, the pinned
order at approval, the note that picks it at dispatch, the counter bill that
picks it at save. The one place that chooses the batch itself says a batch is
good **through** its expiry date: a dispatch or counter bill that names no
batch ships the batch expiring today, first, because it is the earliest. So on
the expiry date the same batch is refused when a person asks for it and
handed out when nobody asks. After the run the batch of the 6th on P had
gone from 6 on hand to 3 (one unpinned dispatch, two unpinned counter bills)
while the picker still showed it `expired`, `available_to_line` 0. For
yesterday's and tomorrow's batches every place agrees.

Two smaller points in the same table: a pinned order to an expired batch
**saves** and is only refused at approval, where a counter bill is refused at
save; and a note picking an expired batch saves and **approves** and is only
refused at dispatch.

Places not found: there is no route named near-expiry or expired-stock under
`/inventory/reports` or `/batch-serial` (404 for the four names tried); the
readers above are the ones the API offers.

## Item 3: counter shifts (R6-2)

M, `s/t1s.py shift`, **03:14:17 IST / 21:44:17 UTC on the 5th**. Shift opened
with a float of 100, one walk-in bill of 118.00 cash (dated 2026-10-06),
closed counted 220.

- `GET /counter-shifts?from_date=2026-10-06&to_date=2026-10-06` → **1 row**.
  `…from_date=2026-10-05&to_date=2026-10-05` → **0 rows**. (Round 6: the
  other way round.)
- `GET /counter-shifts/{id}/report` (PDF): "Shift report -- SHIFT-000001 --
  printed **06-10-2026**".
- The closing journal `SHIFT-000001` is dated 2026-10-06 (Dr 1000 2.00 /
  Cr 6960 2.00).

**Fixed.** Two things left as they are, neither wrong: the report's "Opened"
and "Closed" lines read "05-10-2026 21:44 UTC" (UTC, and labelled UTC); and
the shift's `opened_at` comes back as `2026-10-05T21:44:17Z` from the open
call and as `2026-10-06T03:14:17+05:30` from the close call, the same instant
written two ways.

## Item 4: D-MST-16, a cancelled invoice and the opening balance

M, `b/r7ob.py`, 03:15:14 to 03:15:21 IST. Books at the start: trial balance
balanced, 1100 = 0.00.

| Step | Result |
| --- | --- |
| Customer created with `opening_balance` 1500 | bill OBC-00001 1,500.00 POSTED |
| Sales invoice SI-26-27-000002 (99.12) approved; 1500 → 400 | **422** "Opening balance cannot be changed while other entries stand on …'s account: invoice SI-26-27-000002 of 99.12. Reverse or cancel them first. …" |
| The invoice cancelled; 1500 → 400 | **200.** Bills: OBC-00001 1,500.00 **CANCELLED**, OBC-00002 **400.00 POSTED**. Journals +2 (`-OB-REV` Cr 1100 1,500.00 / Dr 3000; `-OB2` Dr 1100 400.00 / Cr 3000), dated 2026-10-06. `receipts/outstanding` one row of 400.00. Customer owes 400.00 |
| Books then | trial balance **balanced** (36,520.00 each side); **1100 = 400.00 = what customers owe** |
| 400 → 0, then 0 → 400 | 200 and 200; at 0 both bills read CANCELLED and the customer owes 0.00 |
| Second customer, invoice SI-26-27-000003 still standing; 1500 → 400 and → 0 | both **422**, naming "invoice SI-26-27-000003 of 99.12" |
| Third customer, invoice SI-26-27-000004 approved, the whole of it returned (SR-26-27-000001, completed, 99.12); 1500 → 400 | **422** "…: invoice SI-26-27-000004 of 99.12; **credit note SR-26-27-000001 of 99.12**. Reverse or cancel them first. …" |
| Books at the end | trial balance balanced (39,705.10); 1100 3,499.12 = what customers owe |

**Fixed.** The refusal for the return names it by the return's own number
(SR-…), as "credit note"; the return carries no separate credit-note number
(`credit_note_number` is empty on `GET /sales-returns/{id}`).

## Item 5: the sanity pass

### Regression scripts against their round 6 logs

Round 6's scripts, unchanged, each log compared with its round 6 twin by
round 6's own comparers (`cmp6.py`, `cmpb6.py`), which mask firm tags, ids,
document numbers, dates and clock times and count a line that only changed
place as moved. The selling scripts ran on M **after** items 3 and 4 had used
it (round 6 ran them on a firm with nothing else on it), which accounts for
most of what differs. No log of this round carries the date 2026-10-05 apart
from one UTC timestamp in a list of old server errors.

| Script and cases | Firm | Differences from the round 6 log | Reading |
| --- | --- | --- | --- |
| `g4.py` 029 (barcode, split tenders, over-tender) | M | none | |
| `g1.py` 040 to 047, 049 | M | stock on hand one lower throughout (495 for 496); journal counts 35 for 10; a second loyalty balance, 1.9824; one more HSN row (quantity 1, taxable 84.00, no HSN code) and the 3402 row one unit higher | M's own history: item 3's walk-in bill took 1 of the counter item, and item 4's invoices and return left a standing invoice of 84.00 for a product with no HSN code, with its loyalty points |
| `g2.py` 050 to 054, `g3.py` 064 to 072, 087 (charges; hold, recall, shifts) | M | the same stock and HSN lines; the shift list has one more row (item 3's closed shift, with its cash-over journal where round 6 read "no journal matching SHIFT"); "Field Sales lists shifts" 10 for 9; `is_held=false` 24 for 20; journals 80 for 55 | M's own history, item 3's shift first of all |
| `rc1.py` 16, 18 (sales returns) | M | stock figures one lower | the same unit |
| `rc1.py` counter | M | stock figures one (counter item) and two (detergent, 98 for 100) lower; one line: the last two stock-ledger rows read `UNRESERVE`, `DISPATCH` where round 6 read `RESERVE`, `UNRESERVE` | item 4 left 2 detergent out. The ledger line prints the tail of the first 100 ledger rows of the counter item, oldest first; this firm had more rows ahead of it, so the page ends in a different place. Inferred from the script (`rc1.py` line 248), not traced row by row |
| `i7.py` (price terms through an edit) | M | one line: two claims of the same order (`BIGORDER`, `BULK5`) listed in the other order | ordering of two rows that tie |
| `s1.py` 3 and 4 | M | three lines, the same two rows in the other order | ordering |
| `reg1.py` (eight returns and every reader) | M | journals of four returns listed in another order; `credit_notes_deducted` starts at 1,584.00 / 285.12 where round 6 started at 1,500.00 / 270.00, and moves by the same +550.00 / +99.00; the first reconciliation row is another return; the books line | ordering; the extra 84.00 / 15.12 is item 4's return on this firm (which also bears out round 6's reading of where its 1,500.00 came from); history |
| `r4a.py` S1 to S8 (purchase-return sequences) | C | none (2 lines moved) | |
| `r4d.py` BATCH, IMPORT | E | one line: the batch number quoted in a refusal | a random number in the batch's name |
| `r3b.py` IMPORT | E | "returns before 8 … after 9" and "before 9 … after 10" where round 6 read 7, 8 and 0, 1 | counts of returns already on the firm |

Nothing is unexplained. Two readings are inferred rather than traced: the
ledger-tail line of `rc1.py`, and that every stock and journal-count
difference on M is items 3 and 4 (the arithmetic agrees: 1 counter item, 2
detergent, 84.00).

Two slips of mine, none of the product's: the first run of `reg1.py` was
started with the wrong firm letter and stopped at sign-in before sending
anything, and `r3b.py` first stopped on a missing slot in the state file;
both were run again and the table shows the second run. `d1.py` (cases 015,
016) needs a `selling-invoiced` fixture and was not run.

### The books at the end

`s/books.py` and `b/books6.py`, 03:21 IST.

| Firm | Trial balance | Checks |
| --- | --- | --- |
| M `T1006PQ9Q-S` | balanced, 2,859,246.19 | 1100 2,744,446.78 = customers; valuation 26,940.00 = 1200; no unbalanced journal |
| C `T1006B3N7-R` | balanced, 12,000.00 | valuation 10,727.27 = 1200; payables as of 2026-10-06 500.00 = 2100, difference 0.00; 61 journals, none unbalanced |
| P `T1006MCVJ-P` | balanced, 3,216.00 | 1100 336.00 = customers; valuation 2,542.50 = 1200; payables 0 |
| E `T1006U2ZF-P` | balanced, 6,491.23 | 1100 336.00 = customers; payables 604.80 = 2100; valuation **5,752.94** against 1200 at 5,752.93, DIFFERENCE 0.01 |

E's paisa is the same shape as the one round 6 recorded on its firm P (a
moving average of batches received at 50 beside stock at 60, dispatched one
unit at a time); it was not traced on E.

### The dated reads, once each

`b/r7d.py`, `b/r7e.py`; M at 03:19 IST (21:49 UTC on the 5th), C at 03:21, P
at 03:18. To make "today" visible each firm was given something due
2026-10-05 and something due 2026-10-06.

| Read | Firm | Status | Reads the 6th? |
| --- | --- | --- | --- |
| Customer ageing, `GET /customers/ageing` | M | 200 | **Yes.** No `as_of`: `as_of` 2026-10-06, the bills of the 5th `days_overdue` 1, of the 6th 0; identical to `as_of=2026-10-06`; `as_of=2026-10-05` reads 0 and leaves the 6th's out |
| Collection sheet, `GET /collections/sheet` | M | 200 | **Yes.** The opening bill due the 5th `days_overdue` 1, due the 6th 0; no `as_of` identical to `as_of=2026-10-06`. See R7-2 for the bills with no due date |
| Sales overdue, `GET /sales-invoices/reports/overdue` | M | 200 | **Yes.** The bill due the 5th, `days_overdue` 1; the bill due the 6th not listed |
| Vendor ageing, `GET /purchase-invoices/reports/vendor-ageing` | C | 200 | **Yes.** `as_of` 2026-10-06, `oldest_days` 1 |
| Payables, `…/reports/payables` | C | 200 | **Yes.** `as_of` 2026-10-06 |
| Purchase bills overdue and due, `…/reports/overdue`, `…/reports/due` | C | 200 | **Yes.** Overdue: the bill due the 5th, `days_overdue` 1. Due: the bill due the 6th, `days_until_due` 0 |
| Purchase orders overdue, `GET /purchases/reports/overdue` | C | 200 | **Yes.** The order expected the 5th, `days_overdue` 1; the order expected the 6th not listed |
| Stock ageing, `GET /inventory/reports/stock-ageing` | P, M | 200 | **Yes.** No date equals `to_date=2026-10-06` and differs from `to_date=2026-10-05`; `last_receipt_date` 2026-10-06. (M's 282 in "31 to 60 days" is the fixture's opening stock, dated 40 days back) |
| Slow-moving, dead stock | P, M | 200 | **Yes.** The same comparison; `last_issue_date` 2026-10-06, `days_since_issue` 0. Dead stock on M has no rows, so the comparison says nothing there; on P it has one |
| Reorder list, `GET /purchases/reports/below-reorder`, `GET /purchases/reorder-planning` | P, M | 200 | Nothing to read: no product is below a reorder level (0 rows), and the planning settings carry no date |
| E-invoice, `GET /einvoice/pending`, `GET /einvoice/eway-bills/due` | M | 200 | `eway-bills/due` items read `on` 2026-10-06. **The reporting-window check was not reached**: `thirty_day_rule_applies` is false on the fixture and nothing was registered |
| Loyalty expiry, `GET /loyalty/reports/expiring` | M | 200 | Nothing to read: 0 rows, with and without `within_days=30`. `POST /loyalty/expire` was not called |
| Supplier rate contract valid from today | C | | **Yes.** Approves (ACTIVE); a purchase order dated 2026-10-06 with no price typed takes **80.00**, `rate_source` RATE_CONTRACT, and is listed under the contract's releases |
| Rate contract that ended yesterday | C | | Approving it today is **422** "RTC-2026-2027-000002 ended on 2026-10-05; change its period before approving it." (judged on the 6th: on the 5th it would still have been in force). The order line for its product takes the product's own 100.00, `rate_source` PRODUCT. An ACTIVE contract that then runs out was not driven, since one cannot be made active after its end |
| Rate contract from tomorrow | C | | Approves; the order dated the 6th takes the product's 100.00 |
| Supplier scheme (buy 10 get 1) from today, ended yesterday, from tomorrow | C | 201 each | An order dated 2026-10-06 of 10 each: **1 free** under the scheme from today; 0 under the one ended yesterday and the one from tomorrow. A scheme has no accrual; it follows the order's date |
| Customer rebate whose period ended yesterday | M | | **Can be accrued today**: `POST …/accrue` with no date 200, ACCRUED, 2.00 on a turnover of 100.00; reversed; with `accrual_date` 2026-10-06 and 2026-10-05 the same. A rebate whose period runs to 31 December: 422 "The period runs to 31 Dec 2026; accrue it after that, once every bill of the period is in." The rule is "after the last day", and it was passed on the 6th for a period ending the 5th, so it is the firm's day |
| Supplier rebate whose period ended yesterday | C | 422 | Got past the date rule and stopped at the next one: "Purchases of 0.00 reached no slab, so there is nothing to accrue. Cancel the agreement instead." The supplier had no bill inside the period, so an accrual itself was not seen |
| A reservation that lapses today | | | **Not reached.** Lapsing is a job with no route (`app/sales_order/services/reservation_lapse.py`); the fixture has `reservation_lapse_days` unset. By reading only: it takes `firm_today` |

## New findings

Provisional ids. R7-1 was reproduced on two firms; R7-2 on one.

| Id | Severity | What | Where |
| --- | --- | --- | --- |
| R7-1 | Medium (a pharmacy ships a batch its own screens call expired), the rule is the owner's call | On its expiry date a batch is expired everywhere a person names it and in date where the system chooses it | `app/inventory/services/inventory_service.py:3474` (`expiry_date < as_of`) against `app/batch_serial/models/batch_serial.py:117` (`expiry_date <= on_date`) |
| R7-2 | Low | A bill with no due date is overdue in the ageing and not overdue in the collection sheet and the overdue report | `app/sales_invoice/services/sales_invoice_service.py:3326`, `4498` |

### R7-1 -- on its expiry date a batch is refused by name and shipped by default (Medium)

P and E, 03:13 to 03:14 IST on 6 October. Not a date defect: every place here
is on the firm's day.

1. Receive 6 of the batched product as a batch expiring **2026-10-06**
   (today); the fixture also holds batches expiring later.
2. `GET /batch-serial/batches/availability?product_id=…&warehouse_id=…`: the
   batch reads `days_to_expiry` 0, `expired` **true**, `available_to_line`
   **0**. The dashboard counts it in `expired_today`.
3. A sales order dated 2026-10-06 of 1, **no batch named**: approve 200. A
   delivery note dated 2026-10-06 for it, no batch named: approve 200,
   **dispatch 200**; `GET /delivery-notes/{id}` shows the line's batch is the
   one expiring today.
4. With the order and note stages off, a counter bill dated 2026-10-06 of 1,
   no batch named: saves and **approves**; its line's batch is the one
   expiring today. A second one the same.
5. The same batch **named**: a pinned order is refused at approval ("Line 1:
   the batch the customer asked for, R7-T06-…, has expired."), a note picking
   it is refused at dispatch ("Line 1: batch R7-T06-… expired on
   2026-10-06."), a counter bill picking it is refused at save.

**Expected:** one rule. Either a batch is good through its expiry date (then
the picker, the cards and the three refusals are a day early), or it is out
of date on its expiry date (then first-expiry-first must pass it over, as it
does yesterday's). **Actual:** `BatchRecord.expired_condition` is
`expiry_date <= the day` and is what the picker, the cards, the pinned order
(`sales_order_service.py:2753`) and the picked note
(`delivery_note_service.py:2258`) use; the allocator's own test,
`_expired_batches`, is `expiry_date < as_of`. The comment above the picked
note's test says "the same test dispatch applies when nobody chooses: a batch
is out of date on its expiry day", which is not what the allocator does. The
serial path (`delivery_note_service.py:2645`) is also `<`. Which rule is
intended was not judged.

### R7-2 -- a bill with no due date: overdue in one reader, not in two (Low)

M, 03:19 to 03:21 IST (`b/r7d.py sell`, `b/r7e.py`). Seen while reading the
reports, on one firm.

1. A customer with `payment_terms_days` 0. With the order and note stages
   off, a credit bill dated **2026-10-05** approved (SI-26-27-000066, 118.00).
   The bill's `due_date` is empty, on save and after approval.
2. `GET /customers/ageing?customer_id=…`: the bill reads `due_date`
   2026-10-05, **`days_overdue` 1**.
3. `GET /collections/sheet`: the same bill reads `due_date` null,
   **`days_overdue` 0**, and is left out with `overdue_only=true`.
4. `GET /sales-invoices/reports/overdue`: the bill is **not listed**. An
   opening bill of the same customer due the same day is listed by all
   three, 1 day overdue.

**Expected:** the three agree on whether a bill with no credit days is
overdue the day after it is raised. **Actual:** `_due_date` leaves the date
blank where there are no days of credit ("as it always has"), the overdue
report skips a bill with no due date, and the ageing falls back to the bill's
own date. Not caused by the date sweep.

### Seen, not filed

- **The shift report's Opened and Closed lines are UTC** and labelled so; the
  heading's "printed" date is the firm's. Item 3.
- **`opened_at` is written two ways** by the open and the close call (Z and
  +05:30). The same instant.
- **A pinned order to an expired batch saves and is refused only at
  approval; a note picking one saves and approves and is refused only at
  dispatch.** A counter bill is refused at save. Item 2.
- **A sales return's refusal calls it "credit note SR-…"**; the return has no
  credit-note number of its own. Item 4.
- **One paisa between valuation and the stock account on E**, as on round 6's
  P.

## The scripts

New in `round7`: `b/r7p.py` (items 1 and 2: receipts, picker, cards, orders
and notes), `b/r7c.py` (item 2: counter bills), `b/r7f.py` (alerts and cards),
`b/r7ob.py` (item 4; it runs the helpers of round 6's `i23.py`), `b/r7d.py`
and `b/r7e.py` (the dated reads), `run7.py` (the regression chain). Item 3 is
round 6's `s/t1s.py shift` unchanged; the regression is round 6's `reg6.py`,
`r4a.py`, `r4d.py`, `r3b.py`, `books.py` unchanged and `books6.py` with its
list of firms cut to this round's. Fixtures by round 6's `mk6.py`. Every
script and edit went through the file tool; none through a shell heredoc.

Left on the firms: on P and E the three batches (3 left of the batch of the
6th, 6 of the 5th, 3 of the 7th); a cancel was sent for the two orders
pinned to the expired batches and for the two unpinned orders and notes
refused at dispatch, and the answers were not read back; on M the
round-seven customers, bills, a customer rebate left ACTIVE and one not
begun; on C a supplier with two opening bills, four approved orders, three
rate contracts (one DRAFT), three schemes and a rebate.

## Not verified

- **Nothing on screen.** The desktop was not opened. Whether it sends `as_of`
  to the batch picker, and how it shows a batch on its expiry date, were not
  seen.
- **Nothing was read from the database.** That every store is at
  `20261005_0333` and that the server runs `79a72cfd` were taken from the
  hand-over; `git log` in the checkout shows that commit.
- **Items 1 to 3 were driven once each, in one window** (03:13 to 03:14 IST),
  items 1 and 2 on two firms, item 3 on one. They were not re-run after
  05:30 IST, when the two days agree.
- **Item 2:** quantities of 1 only; a line split across batches, a serialised
  product (the serial path was read, not driven), a customer with a minimum
  shelf life, a product with a stop-selling window, a batch marked EXPIRED by
  hand, a sales invoice raised from a note (it inherits the note's batch), a
  stock transfer, and a purchase return of the batch were not driven. The
  "pinned on the order" note for today's and yesterday's batch could not be
  reached because the order is refused first. Documents dated other than the
  6th were not driven.
- **Item 3:** one shift, one bill. The shift list was asked for the 5th and
  the 6th only.
- **Item 4:** the three cases asked for, on one firm. A partly returned
  invoice, a return cancelled afterwards, and a customer credit note other
  than a return were not driven.
- **Item 5, not reached:** the e-invoice reporting-window check; loyalty
  expiry (no points to expire; `POST /loyalty/expire` not called); a
  reservation that lapses today (a job, no route); a reorder list with rows;
  an ACTIVE rate contract that has run out; a supplier rebate actually
  accruing (it passed the date rule and had no purchases). The collection
  sheet PDF and the TDS, TCS, bank reconciliation and reminder dates round 6
  listed as "read, not driven" were not driven here either.
- **Regression:** `d1.py` (015, 016) not run. The selling scripts ran on a
  firm already used by items 3 and 4, so their logs differ from round 6 by
  that history; the reading of each difference is in the table, two of them
  inferred. The TC-BUY case scripts (`b01.py` to `b10b.py`) build on TEST01
  and were not run, as in round 6. The comparers mask document numbers and
  clock times, so a difference that was only a number or a time would not
  show.
- **The causes** given for R7-1 and R7-2 are from reading the code at the
  lines named.
