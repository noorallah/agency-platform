# Purchasing: checked through the API, round 3, 2026-10-05

Rounds 1 and 2 are `PURCHASING_API_CHECK_2026-10-05.md` and
`PURCHASING_API_CHECK_ROUND_2_2026-10-05.md` and are left as they were. This
round re-drives the four findings of round 2 (BUYQ-16 to BUYQ-19, logged as
D-BUY-56 to D-BUY-59) after their fixes were merged (#1197, #1199, #1201), on
the backend as it was running on the evening of 2026-10-05. Same method: the
real server over HTTP, fixture firms only, books read back through the API,
nothing read from the database, no application code touched. The scripts are
in `scratchpad/buying3/` beside the earlier rounds' folders: `r3.py` drives the
four fixes, `r3b.py`, `r3c.py` and `r3d.py` the extras that came out of them,
`q2.py` the two older refusals, the round 2 case scripts (`b01.py`, `b02.py`,
`b04.py`, `b04c.py`, `b05.py`, `b08.py`, `b08b.py`, `b09.py`, `b10b.py`) the
regression pass, `books3.py` the books, and `cmp3.py` diffs a log against its
round 2 twin section by section.

| Fix | Result |
| --- | --- |
| D-BUY-58 / BUYQ-18, self-invoice `RSI-` | **Fixed** for every number issued from now on. A firm that issued `SI-` self-invoices before the fix still has its sales invoices walk onto those old numbers: BUYQ-22 |
| D-BUY-57 / BUYQ-17, rate contract `RTC-` | **Fixed**, with the same leftover for old `RC-` contracts: BUYQ-22 |
| D-BUY-56 / BUYQ-16, free goods on a return | **Fixed.** Driving it found that the same goods can go back twice, off the bill line and off the receipt line: BUYQ-20 |
| D-BUY-59 / BUYQ-19, batch on a return line | **Fixed** |

D-BUY-44 (return from quarantine) and D-BUY-45 (return below zero) still hold.
The regression pass over the return, debit note and return-report cases found
**no regression**: every differing line is explained below. Five new findings,
BUYQ-20 to BUYQ-24; none is caused by the three fixes.

The backend did not stop answering and was never restarted. Free memory went
from 2.5 GB to 1.2 GB over the round.

**Where the data went.** Firms of this round's own: `T1005H0OH-R` and
`T10056RSE-R` (`ready-firm`, called A and B below), `T1005XWA9-P` and
`T1005PCAQ-P` (`pharma-firm`), `T1005TEC7-G` (`compliance-firm`),
`T1005TIXK-E` and `T1005C0UN-E` (`electronics-firm`). `TEST01` for the cases on
the buying fixtures, each under its own suffix. Two round 2 firms,
`T1005498P-R` and `T100517LD-G`, were read and given two reverse-charge bills
and three sales invoices each (and, on the first, three rate contracts and two
receipts) to see what a firm that already issued `SI-` and `RC-` numbers
issues next. The RCM rules of every firm were switched to ACTIVE for that and
are INACTIVE again.

## The four fixes, driven again

Each on a fresh fixture by its round 2 reproduction, and again on a second
firm (`r3.py`; logs `r3_rsi.log`, `r3_num.log`, `r3_free.log`, `r3_batch.log`).

| Id | Result | What it does now, with the data used |
| --- | --- | --- |
| D-BUY-58 / BUYQ-18 | Fixed | **Fresh firms** T1005H0OH-R and T10056RSE-R, the same on both. Numbering rules: `RCM_SELF_INVOICE_DEFAULT` prefix `RSI`, `SALES_INVOICE_DEFAULT` prefix `SI`. Issued in this order: sales invoice **SI-26-27-000001**, RCM bill PI-…-000001 (reverse charge 50.00, Cr 2270 and 2280 25.00 each) with `self_invoice_number` **RSI-26-27-000001**, sales invoice SI-26-27-000002, self-invoice RSI-26-27-000002, sales invoice SI-26-27-000003. No number is on both lists. The self-invoice number is **16 characters**. **Round 2 firms:** T1005498P-R held self-invoices SI-26-27-000002, 000003 and its rule had been moved to `RSI` with the counter kept: the next two are **RSI-26-27-000004, 000005**. T100517LD-G held SI-26-27-000004, 000005: next **RSI-26-27-000006, 000007**. The old `SI-` self-invoices stay as issued, and the sales invoices raised this round took numbers two of them hold (BUYQ-22) |
| D-BUY-57 / BUYQ-17 | Fixed | **Fresh firms** A and B, the same on both: each holds the fixture's receipt RC-2026-2027-000001. `POST /rate-contracts` twice: **RTC-2026-2027-000001, 000002**. `POST /receipts` twice: **RC-2026-2027-000002, 000003**. A third contract after the receipts: RTC-2026-2027-000003. No shared number. **Round 2 firm** T1005498P-R (rule `RATE_CONTRACT_DEFAULT` moved to `RTC`, counter at 7): contracts **RTC-2026-2027-000007, 000008, 000009**; receipts RC-2026-2027-000006, 000007, the first of which an old contract already holds (BUYQ-22) |
| D-BUY-56 / BUYQ-16 | Fixed | `buy-ready` t1005mnn4 on TEST01 and a supplier and product of its own on T1005H0OH-R; every figure below is the same on both. **(1)** 10 at 100 with 2 free received: 12 on hand, receipt journal Dr 1200 1,000.00 / Cr 2300 1,000.00. Return of **13**: 422 "Return quantity exceeds the available source quantity: line 1 can still send back 10 bought and 2 free." Return of **12**: 201, the line reads `current_return_quantity` 12, `free_quantity` 2, `gross_amount` 1,000.00, tax 180.00, total 1,180.00. Approve and Complete 200: **0 on hand**, one RETURN movement of 12, journal Dr 2300 1,000.00 / Cr 1200 1,000.00, supplier balance 0.00 before and after (the receipt was never billed). One more: refused, "0 bought and 0 free". Cancel puts 12 back and mirrors the journal. **(2)** Free units alone, `current_return_quantity` 2 with `free_quantity` 2: 201 at **total 0.00**, approves, completes; stock 24 to 22; journal **Cr 1200 Inventory 166.67 / Dr 5400 Purchase Price Variance 166.67** (the two units at the moving average of 83.33); no supplier credit, statement and payables unchanged at 0.00, `GET /payments/supplier-credits` empty. `free_quantity` 3 on a return of 2: 422 "Line 1: the free quantity is part of the return quantity and cannot exceed it." Then 11 more, or 3 of which 1 free: refused, "10 bought and 0 free". The 10 bought: Dr 2300 1,000.00 / Cr 1200 833.33 / Cr 5400 166.67. **(3)** A free-only receipt line (ordered 0, free 2): a return of 1 with no `free_quantity` typed saves as free 1 at 0.00 and completes (gift stock 2 to 1, no journal: the units carry no value); 2 more refused "0 bought and 1 free"; the last 1 completes (0 on hand). **(4)** Billed (PI-2026-2027-000146, 1,180.00): 12 off the **bill** line refused "…can still send back 10; free goods go back off the goods receipt that brought them in."; 12 off the **receipt** line completes: Dr 2100 1,180.00 / Cr 1200 1,055.56 / Cr 1320 90.00 / Cr 1330 90.00 / Dr 5400 55.56, supplier statement closes 0.00, books check difference 0.00. **(5)** A draft of 12 edited by PUT: the same 12 saves; 13 is refused; 5 of which 2 free prices 3 (354.00); 5 with free not typed prices 5 (590.00); 11 prices 10 and 1 free (`r3c.py`, both ready firms). Every journal balances |
| D-BUY-59 / BUYQ-19 | Fixed | T1005XWA9-P and T1005PCAQ-P, the same on both. Receipt of 10 into a new batch (QA-RET-3841, QA-RET-8577). **(a)** `POST /purchase-returns` for 2 off the receipt line with no `batch_number`: 201 and the line reads `batch_number` **QA-RET-3841**; approve 200, complete 200; the batch goes 10 to 8, the movement names the batch, Dr 2300 120.00 / Cr 1200 120.00; cancel puts it back. **(b)** Batch `NO-SUCH-BATCH`: **422 at create**, "Batch NO-SUCH-BATCH was never received for this product, so no stock can be taken out of it."; no return row is left. **(e)** A draft edited by PUT with `batch_number` null keeps QA-RET-3841; PUT naming `NO-SUCH-BATCH` is refused in the same words and the draft is unchanged; it then approves and completes. **(f)** A return off the **bill** line of a receipt line takes that receipt line's batch (QA-RET-8A2F) and completes. **(g)** A batch-only product (`require_batch_on_issue`) received with no batch, returned with none: **422 at create**, "BO-374A may only be issued from a batch, so the batch number is required to return it." **(h)** A product with no batch tracking returns as before, `batch_number` null. The import (`POST /purchase-returns/import`) fills the batch and refuses an unknown one the same way (but see BUYQ-21) |

### The two older refusals

`q2.py`, cases BUYQ-1 and BUYQ-2, on fresh `po-approved` and `po-received`
fixtures on TEST01 (`q2.log`). Line for line as round 2.

| Id | Result | Data |
| --- | --- | --- |
| D-BUY-44 (BUYQ-1) | Holds | t1005y942 and t1005vvff. Pass 6, reject 4 for return. Return of the 4 naming QUARANTINE (PR-2026-2027-000066) and naming no condition (PR-2026-2027-000069): sellable 6, quarantine 0, movement `current_quantity_delta` 0, `quarantine_quantity_delta` -4. Two more named QUARANTINE with none held: refused at completion "This location holds 0.0000 in quarantine, so 2.0000 cannot be returned from it." Cancel puts each bucket back |
| D-BUY-45 (BUYQ-2) | Holds | t1005l9sv and t1005j96j: 10 received, 9 sold. Return of 3: refused at completion "This location holds 1.0000 available, so 3.0000 cannot be returned to the supplier from it." Return of 1 completes. t1005on1j with `allow_negative_stock`: a return of 2 with 0 on hand completes at -2 |

## Regression pass

The round 2 case scripts that raise returns, debit notes and the return
reports, re-run and diffed against their round 2 logs with `cmp3.py`. Cases
covered: 002 to 006, 009 to 013, 016, 017, 020, 021, 023 to 028 (and 021b,
`neg`, 026b), 029 to 033, 035 to 037, 039, 040, 042, 063 to 065, 077, 078,
091, 092. Sections with no differing line: 002, 003, 005, 009, 010, 011, 012,
016, 017, 028, `neg`, 031, 032, 036, 037, 039, 040, 042, E2 (065 on a second
firm).

| Log, case | What differs | Why |
| --- | --- | --- |
| `b01.log`, 004 (with 006) | The return line now carries `"free_quantity": "0.0000"` | Expected from #1199: the field is new on the response |
| `b02.log`, 013 | Round 2's log stops at a 409 "Vendor code or GSTIN already exists"; this round runs through | The script makes a random GSTIN and round 2 drew one already used (it was re-run then as `b02_013.log`). Not the application |
| `b04.log`, 020 | Print size 3007 to 3008 bytes | One more digit in a document number |
| `b04.log`, 021 | Round 2's log is a traceback (connection reset on the journal list); this round runs through | The same request was reset twice this round and answered on the third try (`resets.log`); see "Not verified". This script is the round 1 form of the case, superseded by `b04c.py` 021b, which matches round 2 |
| `b04.log`, 023 | Proposal rows 57 to 100; two ids | TEST01 holds more open bills; the ids were not normalised |
| `b04.log`, 024 | `supplier-performance` "mine" is now empty | The list is paged at 100 and TEST01 now has 196 suppliers on it; the fixture's row is there (`books3.py` walks both pages) |
| `b04.log`, 025 | `posted_lines` 3 to 6 on the rebate control account | TEST01 has had the case run on it once more |
| `b04.log`, 026 and `b04c.log`, 026b | The landed-cost voucher lists the two receipts in the other order, and the per-receipt split reads receipt of 4: 400.00 to stock, receipt of 6: 200.00 to stock and 400.00 to cost of goods sold (round 2: receipt of 6 all to stock, receipt of 4 all to cost of goods sold). The journal is the same: Dr 1200 600.00, Dr 5200 400.00 / Cr 5210 1,000.00 | Not a regression. The receipt lines are read `ORDER BY goods_receipt_id` (`app/landed_costs/services/__init__.py:177-179`) and what is on hand is given to them in that order, so which receipt keeps the stock share follows a random id. The module has not changed since round 2 |
| `b04c.log`, 021b and 026b | The stock valuation row for the fixture's product is empty | `GET /inventory/reports/stock-valuation` ignores `search` and `product_id`; it returned page 1 of 195 rows and the product is on page 2 (`p4.py`: quantity 10, rate 100, value 1,000.00). In round 2 it happened to be on page 1 |
| `b04.log`, 027 | Opening bill OB-00002 to OB-00003 | The next number |
| `b05.log`, 029, 030 | Register rows 99 to 158; HSN rows 3 to 4; a different random HSN; the blank-HSN row totals | TEST01 has grown; the fixture's own HSN row is identical apart from the code |
| `b05.log`, 033, 035 | Payables totals for the whole firm | TEST01 has grown. The difference of -708.00 is the same PI-2026-2027-000003 as in rounds 1 and 2 |
| `b08.log`, E (064) | "…is entered on line 1 and on line 2…" now reads "line 2 and on line 1" | Goods receipt code, not touched by the three fixes; the order of the two lines in the message is not fixed. Both logs end in the same script error at `b08.py:90`, which `b08b.py` (E2) replaced; E2 matches line for line |
| `b10b.log`, 077 / 078 | FA-00003 to FA-00004 | The next asset number |
| `b09_091.log`, 091 | Supplier payables 408,200.00 to 74,700.00 | A fresh firm: only this case's bill (83,000.00 less the 8,300.00 debit note). The debit note, the return in another currency and the payments match |

Nothing in the table is unexplained.

### The books at the end

`books3.py`, `books3.log`.

| Firm | Trial balance | Payables report against 2100 |
| --- | --- | --- |
| T1005H0OH-R | balanced, 5,295.11 | 1,764.00, agrees: the two reverse-charge bills (2,000.00) less the 236.00 of BUYQ-20 |
| T10056RSE-R | balanced, 3,120.00 | 584.00, agrees: 2,000.00 less the 236.00 and the 1,180.00 of BUYQ-20 |
| T1005XWA9-P, T1005PCAQ-P | balanced, 4,288.80 each | 268.80, agrees |
| T1005TEC7-G | balanced, 70,344.00 | nothing owed, agrees |
| T1005TIXK-E, T1005C0UN-E | balanced | nothing owed, agrees |
| T1005498P-R, T100517LD-G (round 2) | balanced | difference 0.00 with 2,000.00 of unrealised revaluation named, as round 2 |
| TEST01 | balanced, 1,813,526.53 | differs by 708.00, the same PI-2026-2027-000003 of 2026-09-18 |

## New findings

None is in `docs/DEFECTS.md`. Each was reproduced twice, on two firms. None is
caused by #1197, #1199 or #1201; BUYQ-20, 21 and 24 are older than them by
reading the code, not by driving the old build.

| Id | Severity | What | Where |
| --- | --- | --- | --- |
| BUYQ-20 | High | The same goods can be returned twice, once off the bill line and once off the receipt line the bill billed; the supplier is debited twice and input tax reversed twice | `app/purchase_return/services/purchase_return_service.py:2586-2614` (`_already_returned`), `:2576-2584` |
| BUYQ-21 | Medium | `POST /purchase-returns/import` answers 422 for a file whose second record is refused, and leaves the first record written as a draft | `app/purchase_return/services/purchase_return_service.py:1966-1973` |
| BUYQ-22 | Low | In a firm that issued `SI-` self-invoices or `RC-` rate contracts before the fix, the next sales invoices and receipts still take the numbers those old documents hold | `alembic/versions/20261005_0328…` (numbers stay as issued), `app/document_framework/services/transactional_document_service.py:506-531` (`_number_taken`) |
| BUYQ-23 | Low | The return reconciliation report and the line's `received_quantity` leave free goods out, so a free-only return reads as nothing returned | `app/purchase_return/services/purchase_return_service.py:1898-1901, 1919, 2157` |
| BUYQ-24 | Low | A return off a receipt line may name any other batch of the product and takes the stock out of that batch | `app/purchase_return/services/purchase_return_service.py:1053-1055` |

### BUYQ-20 -- the same goods go back twice (High)

`po-invoiced` t1005qxmj on TEST01 (`r3d.py`, `r3d.log`): receipt of 6 billed
(PI-2026-2027-000180, 708.00), receipt of 4 not billed, 10 on hand.

1. `POST /purchase-returns` for 6 off the **bill** line, approve, complete:
   PR-2026-2027-000091, 708.00, Dr 2100 708.00 / Cr 1200 600.00 / Cr 1320
   54.00 / Cr 1330 54.00. 4 on hand. The bill is now returned in full.
2. `POST /purchase-returns` for 4 off the **receipt line that bill billed**
   -> 201, approve 200, complete 200: PR-2026-2027-000092, 472.00, Dr 2100
   472.00 / Cr 1200 400.00 / Cr 1320 36.00 / Cr 1330 36.00. 0 on hand.
3. The supplier statement: BILL 708.00, PURCHASE_RETURN 708.00,
   PURCHASE_RETURN 472.00, closing **-472.00**; payables -472.00.

On T10056RSE-R: 10 received and billed (PI-…-000004, 1,180.00), 10 more of
the product on hand from another receipt. 10 off the bill line, then 10 off
the receipt line: both complete, the supplier closes at **-1,180.00**. In the
other order (receipt line first, then the bill line) the second return saves
and approves too, and was stopped at Complete only because nothing was left
on hand.

**Expected:** a return off either line counts what has already gone back off
the other, as the sales side does since D-SELL-7. **Actual:** each line counts
only the returns that name it, so 6 received and billed can be returned as 6 +
6. The stock check (D-BUY-45) is the only limit, and it is satisfied by any
other stock of the product. Ten units went back against six received on that
line's bill here, and 72.00 of input tax was reversed that was never claimed
on those four.

It is what makes the natural free-goods flow go wrong (`r3c.py`, both ready
firms): 10 + 2 free received and billed, the 10 returned off the bill line,
then "the 2 free" returned off the receipt line with `free_quantity` not
typed: the line is priced as **2 bought**, 236.00, and completes; the supplier
is debited 236.00 for goods that were free. With `free_quantity` 2 typed it is
0.00 as it should be.

**Cause:** `_already_returned` sums `purchase_return_lines` where
`source_document_line_id` is the line named; a bill line and its receipt line
are different ids.

### BUYQ-21 -- a refused import leaves rows behind (Medium)

T1005XWA9-P and T1005PCAQ-P (`r3b.py`, `r3b.log`). The endpoint takes a form
field `payload` holding `{"records": [...]}`.

1. Import two records off one receipt line: the first good, the second naming
   `NO-SUCH-BATCH` -> **422** "Batch NO-SUCH-BATCH was never received for this
   product…".
2. `GET /purchase-returns`: one more return than before, **PR-…-000008 DRAFT**,
   the first record.
3. Again with the second record for 50 of 10 -> 422 "Return quantity exceeds
   the available source quantity…"; PR-…-000009 DRAFT is left.

**Expected:** all or nothing, as the method's own docstring says ("Import a
validated batch of purchase returns atomically"). **Actual:** `import_returns`
loops over `create_return`, which commits each record. A person told the file
was refused imports it again and has the first rows twice.

### BUYQ-22 -- old `SI-` and `RC-` numbers are still walked onto (Low)

Only in a store that issued a self-invoice or a rate contract before
`20261005_0328`. Read after this round's documents (`p2.py`, `p2.log`):

| Firm | Old document | New document with the same number |
| --- | --- | --- |
| T1005498P-R | self-invoice SI-26-27-000003 (round 2) | sales invoice **SI-26-27-000003**, approved this round |
| T100517LD-G | self-invoice SI-26-27-000005 (round 2) | sales invoice **SI-26-27-000005**, approved this round |
| T1005498P-R | rate contract RC-2026-2027-000006 (round 2) | receipt **RC-2026-2027-000006**, posted this round |

**Expected:** D-BUY-58's own words, "two tax documents with one serial
number", no longer happen. **Actual:** they stop happening only once the
sales-invoice counter has passed the last old self-invoice number. The
migration says numbers already issued stay as issued, and the step-over still
looks only at documents of the same type and at journal references, so it
cannot see an old self-invoice. A fresh firm is not affected. No customer
store can hold such numbers unless it used reverse charge or rate contracts on
a build before today's; the demo and test firms do.

### BUYQ-23 -- free goods are missing from the reconciliation (Low)

T1005H0OH-R, after the free-goods run (`p3.py`, `p3.log`); the same rows on
TEST01.

- `GET /purchase-returns/reports/reconciliation`: the free-only returns
  PR-…-000004 and 000005 read `current_return_quantity` **0.0000**; the return
  of 12 (PR-…-000006) reads **10.0000**.
- `GET /purchase-returns/{id}`: the line of the return of 12 reads
  `received_quantity` 10.0000 beside `current_return_quantity` 12.0000; a
  free-only line reads received 0.0000, returning 1.0000.
- `GET /purchase-returns/reports/by-product` counts both: 22.0000 for the
  product (10 + 12), 2.0000 for the gift.

**Expected:** one meaning of "returned" across the reports, or a free column.
**Cause:** the by-product report adds `free_quantity`; the reconciliation
report and `received_quantity` were not changed with it.

### BUYQ-24 -- a return can drain a batch its receipt never brought (Low)

T1005XWA9-P and T1005PCAQ-P, step (c) of the batch run: a return of 2 off the
receipt line that brought batch QA-RET-3841, naming `batch_number`
QA-RET-8A2F (another receipt's) -> 201, approves, completes; **QA-RET-8A2F
goes 5 to 3** and QA-RET-3841 stays at 10. **Expected:** a typed batch is the
receipt line's own, or the refusal says the line brought another. **Actual:**
any batch the product was ever received into is accepted. A typing slip sends
the wrong batch's stock back on paper, and the two batches may be different
suppliers' goods. `_line_batch_number` returns whatever was typed.

### Seen, not filed

- `POST /purchase-returns/preview` answers 200 for a line naming a batch
  nobody received; the refusal comes at Save. The code says so on purpose
  ("Asked where the return is saved, not where it is previewed").
- A free-only return of units that carry value debits **5400 Purchase Price
  Variance** with their moving-average cost, and a later return of the bought
  units credits it back; when the whole delivery has gone the account nets to
  0.00. Where some stock stays, 5400 keeps a balance (T1005H0OH-R: Cr 111.11
  with 24 on hand at 2,111.11). That follows the posting rule (stock leg at
  the movement's value, counterparty leg at the document's); whether 5400 is
  the account a firm expects for returned free goods is a question for the
  accountant, not a defect found here.
- `GET /purchase-returns/summary` counts cancelled returns in `total_value`
  (T1005H0OH-R: 3,540.00 with two of six cancelled). Not compared with an
  earlier build.
- `GET /inventory/reports/stock-valuation` ignores `search` and `product_id`
  without saying so (see the regression table).

## Case text to correct

On top of round 2's table, which still stands. `docs/INDEPENDENT_TEST_CASES.md`
was not edited.

| Case | Change |
| --- | --- |
| TC-BUY-060 | Replace "the contract takes a number from its own `RC` series" with "the contract takes a number from its own **`RTC`** series (RTC-2026-2027-…); a customer receipt keeps `RC`". |
| TC-BUY-061 | Replace "Releases (**Releases against RC-…**)" with "Releases (**Releases against RTC-…**)". |
| TC-BUY-062 | Replace "RC-… ended on …" with "RTC-… ended on …". A contract raised before the fix keeps its `RC-` number. |
| TC-BUY-006, 009 to 011, 016, 035 | **Data:** the return line now reads `free_quantity` (0.0000 where nothing free goes back), and `current_return_quantity` is everything going back, free goods included. |
| TC-BUY-066 | Add to **Leaves** or as a new step: "The free units can go back: a return of all 29 off the receipt line is accepted and prices the 25 bought; 30 is refused with '…can still send back 25 bought and 4 free'." |
| New, after D-BUY-56 | A case for free goods on a return, `buy-ready`: receive 10 + 2 free. (1) Return 13 off the receipt line: refused, "Return quantity exceeds the available source quantity: line 1 can still send back 10 bought and 2 free." (2) Return 12: accepted, gross 1,000.00 on the 10 bought, total 1,180.00; after Complete 0 on hand and Dr 2300 1,000.00 / Cr 1200 1,000.00. (3) On a second receipt, return 2 with **Free** 2: total 0.00, the supplier is credited nothing, stock falls by 2, journal Cr 1200 / Dr 5400 at the moving average. (4) A free-only receipt line can be returned. (5) Off a **bill** line: "…free goods go back off the goods receipt that brought them in." Until BUYQ-20 is fixed, do not return the bought units off the bill and the free units off the receipt in one case without typing the free quantity. |
| New, after D-BUY-58 | A case for the self-invoice number, in a firm with the RCM rules switched on: approve a bill for a product on `RCM_GTA_5`; its self-invoice reads **RSI-26-27-000001** (16 characters); the next sales invoice reads SI-26-27-…, and the two lists share no number. |
| New, after D-BUY-59 | A case for the batch on a return, `pharma-firm`: receive 10 of `<SUFFIX>-AMX` into a new batch. A return off that line with the batch left blank saves with the receipt line's batch filled in, approves and completes, and the batch falls by the quantity. A batch nobody received is refused at Save: "Batch … was never received for this product, so no stock can be taken out of it." A batch-only product with no batch: "… may only be issued from a batch, so the batch number is required to return it." |

## Still to walk on screen

- The return editor's **Free** box (if it has one), what it shows for a line
  of 10 + 2 free, and the two new refusals as the screen words them.
- That a return saved from the desktop with the batch box cleared comes back
  with the receipt line's batch.
- A rate contract's `RTC-` number on its print and in *Releases against …*;
  the self-invoice print under `RSI-`.

## Not verified

- **Nothing was read from the database.** Which revision each store is at was
  not checked; the write-up takes the hand-over's word for it. The fresh firms
  were provisioned by the running server without error.
- **The old build was not driven.** That BUYQ-20, 21 and 24 predate the three
  fixes rests on reading the code and on the cap having been per source line
  in round 2's description of BUYQ-16.
- **D-BUY-58 on a rule a firm had changed.** `20261005_0328` moves only a rule
  still at the default prefix. A firm with a prefix of its own was not made;
  both round 2 firms were at the default and both were moved.
- **GSTR-1's document summary** was not read for the `RSI` series or for the
  clash of BUYQ-22.
- **"In the words Complete used"** for the batch-only product was checked by
  reading: save and Complete call the same `_resolve_return_batch`. Complete
  was not reached with such a line, because Save now refuses it.
- **Connection resets.** `GET /finance/journal-entries?journal_from=…&page_size=100`
  on TEST01 was reset twice and answered on the third try, in the place round
  2's `b04.py` crashed. `GET /purchase-invoices` at `page_size` 100 and 50 on
  T100517LD-G was reset once each, which ended the first read-back there; the
  read was repeated and completed. This round's copy of the helper retries a
  reset GET and never a write. Not explained, as in round 2.
- **Not re-run:** the cases that raise no return or debit note (`b03.py`,
  `b06.py`, `b07.py`, the rest of `b09.py` and `b10.py`), the generic checks
  (`g01.py`), and round 2's `x2.py` to `x5.py` as such; their return, free
  goods, batch and prefix parts are what `r3.py` drives. `r01.py` was not run
  whole: its books check is `books3.py`, on this round's firms.
- **A return in another unit** than the receipt line's, with free goods, was
  not driven; nor a serial-tracked product with free units; nor free goods on
  a replacement or refund outcome.
- The desktop was not opened.
- TEST01's 708.00 (PI-2026-2027-000003) was again left alone.
