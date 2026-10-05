# Purchasing: checked through the API, round 4, 2026-10-06

Rounds 1 to 3 are `PURCHASING_API_CHECK_2026-10-05.md`,
`PURCHASING_API_CHECK_ROUND_2_2026-10-05.md` and
`PURCHASING_API_CHECK_ROUND_3_2026-10-05.md` and are left as they were. This
round re-drives round 3's four return findings (BUYQ-20, 21, 23, 24, logged as
D-BUY-61 to D-BUY-64) after their fixes were merged (#1206, #1207, #1209), and
two customer changes that came out of the selling rounds: the customer edit by
role (#1204) and the opening balance as a bill (D-MST-13, #1205, migration
`20261005_0333`). The backend was the one running at http://127.0.0.1:8000 on
`main` at `a00ac2f0`. Same method: the real server over HTTP, fixture firms
only, books read back through the API, nothing read from the database, no
application code touched. The scripts are in `scratchpad/buying4/` beside the
earlier rounds' folders: `r4a.py` drives D-BUY-61, `r4d.py` D-BUY-62 and
D-BUY-64, `c4.py` (with `c4c.py`, `c4d.py`, `c4p.py`) the two customer items,
`old4.py` reads the two older firms, round 3's own scripts (`r3.py`, `r3b.py`,
`r3c.py`, `r3d.py`, `p3.py` and the case scripts) are the original
reproductions and the regression pass, `books4.py` the books, and `cmp4.py`
diffs a log against its round 3 twin section by section.

| Item | Result |
| --- | --- |
| 1. D-BUY-61 / BUYQ-20, the same goods returned twice | **Fixed** |
| 2. D-BUY-62 / BUYQ-21, a refused return import leaves rows | **Fixed** |
| 3. D-BUY-63 / BUYQ-23, free goods in the return reconciliation | **Fixed**; what is *pending* on a line still ignores the other document: BUYQ-25 |
| 4. D-BUY-64 / BUYQ-24, a return naming another batch | **Fixed** |
| 5. Customer edit by role (#1204) | **Fixed** on the edit and on the file import; the same debt can still be entered, and taken off, as an opening **bill**: CUSTQ-2 |
| 6. Opening balance is a bill (D-MST-13, #1205) | **Fixed**, with one thing not driven (the overdue report, see below) and one dead end: CUSTQ-1 |

The regression pass found **no regression**: every differing line is explained
below. Four new findings: BUYQ-25 (Low), BUYQ-26 (Low to Medium, the server's
day against the firm's), CUSTQ-1 (Low) and CUSTQ-2 (Medium). None is caused by
this round's fixes.

**The hour mattered.** The round ran from 00:09 to about 00:50 IST on
2026-10-06, when this machine's day is one ahead of the server's UTC day
(2026-10-05). The fixture tool and the scripts date their documents by the
machine. That is what BUYQ-26 is, and it is behind several lines of the
regression table.

**The backend was restarted once**, from 00:38:48 to 00:39:02, while
`b04.py` was building the `po-invoiced` fixture of case 023. Cases 023 to 028
and `b04c.py` ran against a server that was down or just up; both scripts were
run again whole afterwards and those are the logs compared (`b04_restart.log`
and `b04c_restart.log` are the interrupted ones). The cut fixture build may
have left an order or a receipt of its own on TEST01 under a suffix it never
printed. No write of the round's own scripts was in flight.

**One mistake of mine.** The first run of `c4.py` paged
`GET /finance/ledger-accounts`, which is not paged and answers the whole list
whatever page is asked, and so asked it about 14,000 times over ten minutes
before I stopped the script. They were reads only, and the server went on
answering. It left one more customer with an opening balance of 1,500 on
T1006YLNL-S.

**Where the data went.** Firms of this round's own: `T1006SUZA-R` and
`T1006D5GD-R` (`ready-firm`, A and B below), `T1006VQ0M-P` and `T1006DW3P-P`
(`pharma-firm`), `T1006YLNL-S` and `T1006O4W8-S` (`selling-firm`, M and N),
`T10069A1W-G` (`compliance-firm`), `T1006ANJQ-E` and `T10063O3I-E`
(`electronics-firm`, made by `b08.py` and `b08b.py`). `TEST01` for the cases
on the buying fixtures, each under its own suffix. Two round 3 selling firms,
`T1005PCJH-S` and `T100571FN-S`, were **read only**.

## The six items

Each by its original reproduction on a fresh fixture, and again on a second
firm. Where two firms are named the answers were the same on both, checked by
diffing the two logs.

| # | Id | Result | What it does now, with the data used |
| --- | --- | --- | --- |
| 1 | D-BUY-61 / BUYQ-20 | **Fixed** | **Round 3's own script** (`r3d.py`): TEST01 `po-invoiced` t1006hqyi, receipt of 6 billed (PI-2026-2027-000181, 708.00) and receipt of 4 not billed, 10 on hand. 6 off the bill line completes (PR-2026-2027-000093, Dr 2100 708.00 / Cr 1200 600.00 / Cr 1320 54.00 / Cr 1330 54.00), 4 on hand. 4 off the receipt line that bill billed: **422** "Return quantity exceeds the available source quantity: line 1 can still send back 0 bought and 0 free. 6 of these goods have already gone back against the supplier bill for them." Supplier statement BILL 708.00, PURCHASE_RETURN 708.00, closing **0.00** (round 3: -472.00). On T1006D5GD-R: 10 off the bill line, then 10 off the receipt line refused, closing 0.00 (round 3: -1,180.00); the other order, 10 off the receipt line then 10 off the bill line, is refused **at save** "…can still send back 0; free goods go back off the goods receipt that brought them in. 10 of these goods have already gone back against the goods receipt that brought them in, or another bill for it." **The sequences asked for** (`r4a.py`, A and B, a supplier and product of its own each time, 10 received and billed at 1,180.00, 10 more of the product on hand from another receipt so the stock check cannot be what refuses): **S1** 6 off the bill completes; 5 off the receipt 422 "…can still send back 4 bought and 0 free. 6 of these goods have already gone back against the supplier bill for them."; 4 saves (472.00). While that 4 is a **draft**, 1 more off the bill and 1 more off the receipt are both refused (0 left), so a draft holds the quantity. Approved and completed: 10 on hand, statement closes 0.00. 1 more off either line refused. **Cancel** the return of 4: 14 on hand, journal mirrored, then 5 off the bill refused ("can still send back 4"), 4 accepted and completed, 1 off the receipt refused "…10 of these goods have already gone back against the supplier bill for them." End: 10 on hand, statement BILL 1,180.00 / returns 708.00, 472.00, reversal 472.00, 472.00, closing 0.00, payables 0.00. **S2** the other order: 6 off the receipt, 5 off the bill refused, 4 accepted, 1 more off either refused; closing 0.00. **S3** one return, two lines: receipt 6 + bill 6 refused at line 2 ("line 2 can still send back 4…"); receipt 10 + bill 1 refused; bill 6 + receipt 5 refused; receipt 6 + bill 4 saves at 1,180.00; PUT to 6 + 5 refused, PUT to 5 + 5 saves; completes, Dr 2100 1,180.00 / Cr 1200 1,000.00 / Cr 1320 90.00 / Cr 1330 90.00. **S4** free goods, 10 + 2 free received and billed: 10 off the bill completes (1,180.00); then off the receipt, 3 with free blank, 2 with `free_quantity` 0 and 2 with `free_quantity` 1 are each refused "…can still send back 0 bought and 2 free…"; **2 with `free_quantity` blank saves as `current_return_quantity` 2, `free_quantity` 2, gross 0.00, total 0.00** and completes: stock 12 to 10, journal Cr 1200 181.82 / Dr 5400 181.82, no supplier credit (`GET /payments/supplier-credits` empty), statement closing 0.00 before and after. The other order (2 off the receipt first, nothing back yet) prices 2 bought, 236.00, as before; the bill line then gives 8, not 10, and the 2 free go back at 0.00: closing 0.00. Typed-free first, then all 10 off the bill: closing 0.00. **S5** two drafts, neither approved: 6 off the bill saves, 5 off the receipt is refused, 4 saves; PUT of the receipt draft to 5 refused, PUT of the bill draft to 7 refused; moving a draft onto the other line obeys the same total; 5 + 5 completes. **S6** `POST /purchase-returns/import`: bill 6 + receipt 6 in one file 422 "Record 2 of 2: … can still send back 4 bought and 0 free. 6 of these goods have already gone back against the supplier bill for them. Nothing was imported." (returns 15 before and after); bill 6 + receipt 4 imports both; one more record off either line is refused. **S7** a receipt of 10 of which the bill bills 6: 7 off the bill refused, 6 accepted; 5 off the receipt refused, the 4 never billed go back as Dr 2300 400.00 / Cr 1200 400.00, the supplier not debited; all 10 off the receipt first posts Dr 2100 708.00 / Dr 2300 400.00 and the bill line then gives 0. **S8** one receipt line on two bills (6 and 4): the three routes share the 10. After every sequence: stock on hand as expected, statement closing 0.00, payables report difference 0.00, every journal balanced |
| 2 | D-BUY-62 / BUYQ-21 | **Fixed** | **Round 3's own script** (`r3b.py`, both pharmacy firms): two records, the second naming `NO-SUCH-BATCH`: 422, and the return list is unchanged (8 before the file, 8 after; round 3 was left one DRAFT more). The second asking 50 of 10: 422 "Record 2 of 2: Return quantity exceeds the available source quantity: line 1 can still send back 8 bought and 0 free. Nothing was imported.", nothing written. **`r4d.py`**, T1006VQ0M-P and T1006DW3P-P, a receipt of 10 into a new batch, return count read before and after each file: second record `NO-SUCH-BATCH` 422 "Record 2 of 2: Line 1: the goods receipt brought these goods in as batch QA4-I…, so batch NO-SUCH-BATCH cannot go back against it. … Nothing was imported." (5 to 5); second record 50 of 10 (5 to 5); **6 and 6 off 10** 422 "Record 2 of 2: … can still send back 4 bought and 0 free. Nothing was imported." (5 to 5); second record returning 0; a third record bad of three ("Record 3 of 3"); second record naming a line that does not exist: all 422, all 5 to 5. **A good file of 6 and 4 writes both** (201, PR-…-000006 and 000007, DRAFT, the batch filled in; 5 to 7), a further record of 1 is refused (0 left), both approve and complete and the batch goes 10 to 4 to 0. No number is skipped by the refused files |
| 3 | D-BUY-63 / BUYQ-23 | **Fixed** | T1006SUZA-R after round 3's free-goods run and `r3c.py` (`p3.py`, `p3.log`); the 10 + 2 rows read the same on T1006D5GD-R (`r4a.py` S4) and on TEST01 (`r3_free.log`), the gift-line rows were read on T1006SUZA-R only. `GET /purchase-returns/reports/reconciliation`: the return of 12 off 10 + 2 (PR-…-000033) reads `received_quantity` **12.0000**, `current_return_quantity` **12.0000**, pending 0 (round 3: 10 and 10); the free-only returns of a gift line read 1.0000 each (round 3: 0.0000), received 2.0000; a free-only return off a 10 + 2 line reads 2.0000. `GET /purchase-returns/{id}`: the line's `received_quantity` is bought plus free (12.0000; 2.0000 on the free-only gift line). Against `reports/by-product`: FRP-CB02 22.0000 = the two live reconciliation rows of 12 and 10 (the two cancelled returns are in neither); the gift 2.0000 = 1 + 1. What the report calls **pending** is BUYQ-25 |
| 4 | D-BUY-64 / BUYQ-24 | **Fixed** | T1006VQ0M-P and T1006DW3P-P (`r4d.py`, and round 3's step (c) in `r3.py`). Receipt of 10 as batch X, receipt of 5 as batch Y. **POST** 2 off the X receipt line naming Y: **422** "Line 1: the goods receipt brought these goods in as batch QA4-X06B6, so batch QA4-Y2427 cannot go back against it. Return batch QA4-X06B6 on this line, or raise the return off the receipt that brought QA4-Y2427."; Y stays 5, X stays 10, no return row is left (0 to 0). **PUT**: a draft of 1 with no batch typed (reads X), PUT naming Y is refused in the same words and the draft still reads X; moved onto the Y receipt line naming Y it saves, and there naming X is refused the other way round. **Import**: one record naming Y, and two records the second naming Y, 422 "Record n of n: Line 1: … Nothing was imported.", nothing written. **Off the bill line** of the X receipt naming Y: 422 in the same words; naming X saves, a PUT of it naming Y is refused, it completes and X goes 10 to 9. A second receipt of batch X may send X back off its own line. `POST /purchase-returns/preview` still answers 200 for the refused line (as round 3 noted, on purpose) |
| 5 | Customer edit, #1204 | **Fixed** | T1006YLNL-S and T1006O4W8-S (`c4.py EDIT`). A Sales Manager (`SALES_MANAGER`), and a Customer Support user (`CUSTOMER_SUPPORT`, the other seeded role with `CUSTOMER_UPDATE` and no `CUSTOMER_MANAGE_SETTINGS`), on a customer the administrator made with credit days 30, cash discount 2% in 10 days, opening balance 1,500, credit limit 50,000, standing discount 5%. `PUT /customers/{id}` with the whole record and one figure changed: credit days 30 to 45 **403** "Changing a customer's credit days needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)."; cash-discount days 10 to 7 and percent 2 to 3 **403** "…cash-discount terms…"; opening balance 1,500 to 900 **403** "…opening balance…"; credit limit and standing discount 403 as before. Each of the six set to zero or null: 403 the same way. After every refusal the stored row, its `version`, the journal count and the opening-bill count are unchanged. The stored figures resent with the name changed: **200**; only the required fields and a new name: 200, the terms untouched; the figures sent as numbers (30, 10, 2.0, 1500.0): 200, no journal and no new bill. Round 4's reproduction, a plain customer given the terms by an edit: 403 on each of credit days, cash-discount days, percent, both, opening balance, limit and discount; zeros sent with a new name 200. **File import with `existing=update`** as Sales Manager: `CreditDays` 45, `OpeningBalance` 900, `CreditLimit` 70000, `DiscountPercent` 6 each report the issue on row 2 in the same words and update 0; the name alone updates. (Customer Support is 403 on the file import route itself: no `CUSTOMER_IMPORT`.) **Firm administrator**: every one of the changes 200 and stored; opening balance 1,500 to 900 posts two journals and gives one new bill. Books after it: trial balance balanced, 1100 = what customers owe (12,300.00) |
| 6 | D-MST-13, #1205 | **Fixed** | T1006YLNL-S and T1006O4W8-S (`c4.py OB OB2`), as firm administrator. **Create** with `opening_balance` 1500, `payment_terms_days` 30: journals +1, `<code>-OB` Dr 1100 Trade Receivables 1,500.00 / Cr 3000 Opening Balance Equity 1,500.00; `current_outstanding` 1,500.00. `GET /customers/{id}/opening-bills`: one row, OBC-…, 1,500.00, POSTED, **`covers_master_balance` true**, `bill_date` 2026-10-05, **`due_date` 2026-11-04** (the server's day plus 30). `GET /receipts/outstanding?customer_id=`: one row "Opening balance", 1,500.00, due 2026-11-04, `is_opening_bill` true. `GET /collections/sheet`: the same row. `GET /customers/ageing`: 1,500.00 in the 0 to 29 bucket, invoice "Opening balance" due 2026-11-04; asked `as_of` 2026-11-20 it reads 16 days overdue (and a customer with no credit days, due 2026-10-05, moves to the 30 to 59 bucket at 46 days). **Receipt of 600 allocated to it**: 201, Dr 1000 600.00 / Cr 1100 600.00; the bill reads received 600.00, outstanding **900.00** on all three lists; customer `current_outstanding` 900.00; trial balance balanced; 1100 = what customers owe (firm M 14,700.00, firm N 13,200.00). 2,000 allocated to it: 422 "Invoice Opening balance has 1500.00 outstanding, so 2000.00 cannot be allocated to it." **Cancel the bill** (`POST /customers/opening-bills/{id}/cancel`): **422** "OBC-00012 is the opening balance entered on the customer, not a bill of its own. Set the customer's opening balance to 0 to take it back." **Change the opening balance after the receipt** (to 900, 0, 2000): **422** "Opening balance cannot be changed after receivable activity exists.", stored unchanged. An ordinary opening bill beside it: 422 "… carries an opening balance of 1500.00. Enter the opening balance either as one figure on the customer or bill by bill, not both…". Reversing the receipt puts the bill back to 1,500.00; a receipt on account then `POST /receipts/{id}/allocate` to the bill works; paid in full the bill leaves all three lists. **Second customer, no receipt**: 1,500 to 400: journals +2 (`-OB-REV` mirrors the old, `-OB2` Dr 1100 400.00 / Cr 3000 400.00), the 1,500 bill CANCELLED "The customer's opening balance was revised.", **one standing bill of 400.00**, the lists read 400.00. 400 to 0: journals +1, no bill standing, the lists empty. An ordinary opening bill of 250 then saves (`covers_master_balance` false, on the three lists as "OLD-7 (opening)"), and an opening balance of 300 typed on the customer is then refused "… has 1 opening bill. Enter the opening balance either as one figure on the customer or bill by bill, not both…". **Negative** opening balance (-300): one journal Dr 3000 / Cr 1100 300.00, advance 300.00, **no bill**, nothing on the lists; revised to 700 a bill appears, revised to -50 it is cancelled. **Statement** (`GET /customers/{id}/statement`, and the printed PDF read for one customer on firm M): one OPENING_BALANCE line of 1,500.00, then the receipts (the PDF also carries the period's own brought-forward row, "Opening balance 0.00", above it); a later period opens at the balance and has no line. **`POST /customers/import`** with `opening_balance` 700 and 15 days: journal, bill of 700.00 due 2026-10-20, on the three lists. **File import** (`OpeningBalance` 800, `CreditDays` 20): bill of 800.00 due 2026-10-25, on the three lists; `OpeningBalance` -120: no bill; the file with `existing=update` taking 800 to 650 cancels the 800 bill and leaves one of 650.00. `POST /customers/opening-bills/import` for a customer carrying a figure: refused the same either/or way. Books at the end: balanced, 1100 = customers less advances, no unbalanced journal. **The two older firms, read only** (`old4.py`): T1005PCJH-S and T100571FN-S each have 3 customers carrying an opening balance on the master (FS2, Q2, Q8, 1,500.00 each, made in round 3); **each has exactly one POSTED `covers_master_balance` bill for 1,500.00** (OBC-00001 to 00003, dated and due 2026-10-05), no other opening bill, and a row "Opening balance" on `receipts/outstanding`; the collection sheet and the ageing were read for one of the three in each firm (Q8) and carry it. Trial balance balanced (54,147.84 and 44,287.94); 1100 = what customers owe (9,603.54 and 6,358.54); 133 and 87 journals read, none unbalanced |

### Item 6: what was not driven, and three things seen

- **The overdue report.** `GET /sales-invoices/reports/overdue` takes no date,
  and the bill for an opening balance is dated the day it is entered, so none
  could be past due today: the report had no row for it, on the fresh firms or
  the older ones. An ordinary opening bill dated 70 days back **is** on that
  report ("OLD-7 (opening)", 39 days overdue), and the code reads one list for
  both, so the row should appear from tomorrow for a customer with no credit
  days. Not seen.
- The bill's due date is fixed when the figure is entered. Changing the
  customer's credit days from 30 to 60 afterwards leaves it at 2026-11-04 (an
  ordinary opening bill entered after the change, with no due date typed,
  takes the 60).
- A receipt taken on account lowers `current_outstanding` at once and leaves
  the bill reading its full amount until the receipt is allocated, as for a
  sales invoice.
- A Sales Manager's edit that sends the cash-discount fields as zero on a
  customer that had none stores 0 where there was nothing (blank and zero are
  the same answer). Harmless.

## Regression pass

Round 3's scripts, unchanged, re-run and diffed against their round 3 logs
with `cmp4.py` (dates are compared as their distance from each run's own day).
The reproductions: `r3d.py` (TWICE), `r3c.py` (EDIT), `r3b.py` (IMPORT),
`r3.py FREE`, `r3.py BATCH`. The cases: 002 to 006, 009 to 013, 016, 017, 020,
021, 023 to 028 (and 021b, `neg`, 026b), 029 to 033, 035 to 037, 039, 040,
042, 064, 065, 077, 078, 091, and the two older refusals BUYQ-1 and BUYQ-2
(D-BUY-44, D-BUY-45). Sections with no differing line: 002, 003, 004, 005,
010, 011, 012, 013, 016, 025, 028, `neg`, 031, 032, 036, 037, 039, 040, 042,
E2 (065), 091, BUYQ-1, BUYQ-2.

| Log, case | What differs | Why |
| --- | --- | --- |
| `r3d.log`, TWICE | The second return of each pair is refused at save; the supplier closes 0.00 instead of -472.00 and -1,180.00 | Expected from #1206. This is item 1 |
| `r3c.log`, EDIT | "2 off the receipt line, free not typed" after the 10 went back off the bill saves as 2 free at 0.00 (round 3: 2 bought, 236.00); the next return typed as 2 free is refused, 0 left (round 3: saved, and failed at Complete for want of stock); payables 0 (round 3: -236.00) | Expected from #1206 |
| `r3b.log`, IMPORT | The two refused files write nothing (round 3: one DRAFT each); the refusals carry "Record 2 of 2: … Nothing was imported."; "can still send back 8" where round 3 said 7 | Expected from #1207. The 8 is because the first refused file no longer leaves a draft of 1 behind |
| `r3b.log`, `r3_batch.log` (b), (e) | `NO-SUCH-BATCH` on a line whose receipt named a batch is refused "Line 1: the goods receipt brought these goods in as batch …, so batch NO-SUCH-BATCH cannot go back against it. …" (round 3: "Batch NO-SUCH-BATCH was never received for this product…") | Expected from #1209: the new check runs first. The old words still answer where the receipt line named no batch (step (g)) |
| `r3_batch.log`, (c) | Naming the other batch is refused (round 3: saved, completed, the other batch 5 to 3); the batch quantities of the later steps follow | Expected from #1209. This is item 4 |
| `r3_batch.log`, every "rows" line | More batch rows on the product | `r4d.py` and `r3b.py` had already received batches of the same product on these firms |
| `r3_free.log`, (5) reconciliation | `received_quantity` 12.0000 where round 3 read 10.0000; the first row shown is a different return | Expected from #1209. The line is cut at 900 characters and the report orders one day's rows by a random id |
| `b02.log`, 009 and 017 | The supplier refund is refused: "A refund cannot be received on a future date."; what follows it differs | The hour, not the application as it was: BUYQ-26. Re-run with every document dated the server's day (`b02_srv.log`): 017 matches line for line; 009 differs by one line, the refund's journal is not among the first 100 journals from that day on TEST01 (it is printed three lines later as REVERSED with its mirror) |
| `b04.log`, 020 | Print size 3008 to 3007 bytes | One digit fewer in a document number |
| `b04.log`, 021 | 6 inspection rows where round 3 had 4; the "recent" journals are other documents | TEST01 has grown; the list is the firm's latest journals. This is the round 1 form of the case; 021b matches |
| `b04.log`, 023 | Proposal rows 100 to 131; two ids | TEST01 holds more open bills; the ids were not normalised |
| `b04.log`, 024 | `rated_on` is the day before the run's | The server stamps its own (UTC) day |
| `b04.log`, 026 and `b04c.log`, 026b | Which receipt keeps the stock share of a landed cost is the other way round; one more LANDED_COST ledger row | The same cause as round 3: the receipt lines are read in the order of a random id. The journal is the same |
| `b04.log`, 027 | OB-00003 to OB-00004; `posting_date` the day before | The next number; the server's day |
| `b04c.log`, 021b | Two identical journal lines in the other order | Ordering only |
| `b05.log`, 029, 030, 033, 035 | Register rows 158 to 193; HSN rows 4 to 5; another random HSN; firm totals | TEST01 has grown. The difference of -708.00 is the same PI-2026-2027-000003 |
| `b08.log`, E (064) | Two traceback paths | The folder name. Both logs end in the same script error at `b08.py:90`; E2 matches |
| `b10b.log`, 077 / 078 | FA-00004 to FA-00005 | The next asset number |

Nothing in the table is unexplained.

### The books at the end

`books4.py`, `books4.log`; the selling firms from `c4.py`.

| Firm | Trial balance | Check |
| --- | --- | --- |
| T1006SUZA-R | balanced, 13,500.00 | payables 0.00 against 2100 0.00, agrees (round 3's firm A was out by the 236.00 of BUYQ-20); 77 journals, none unbalanced |
| T1006D5GD-R | balanced, 12,500.00 | payables 0.00, agrees (round 3's firm B: 236.00 and 1,180.00 over-returned); 73 journals, none unbalanced |
| T1006VQ0M-P, T1006DW3P-P | balanced, 5,253.60 each | payables 873.60, agrees; 26 journals each, none unbalanced |
| T10069A1W-G | balanced, 70,344.00 | nothing owed, agrees |
| T1006YLNL-S | balanced, 29,190.00 | 1100 21,690.00 = 30 customers owing 21,860.00 less advances 170.00; no unbalanced journal |
| T1006O4W8-S | balanced, 27,390.00 | 1100 19,890.00 = 29 customers owing 20,060.00 less advances 170.00; no unbalanced journal |
| TEST01 | balanced, 1,889,657.64 | payables differ by 708.00, the same PI-2026-2027-000003 of 2026-09-18 |

The stock valuation report read 0.00 on every fresh buying firm at the time.
That is BUYQ-26, not the stock.

## New findings

None is in `docs/DEFECTS.md`. Each was reproduced on two firms. None is caused
by #1204 to #1209.

| Id | Severity | What | Where |
| --- | --- | --- | --- |
| BUYQ-25 | Low | The return reconciliation and the return line count what went back per document, so a receipt line whose goods went back off the bill still reads them as pending | `app/purchase_return/services/purchase_return_service.py:2245-2246, 1941-1944` |
| BUYQ-26 | Low to Medium | "Today" is the server's UTC day. From midnight to 05:30 IST a document dated today is a day ahead of it: a supplier refund is refused as future-dated, an opening bill cannot be dated today, and the stock valuation leaves out everything entered since midnight | `app/settlements/services/supplier_credits.py:851`, `app/inventory/api/router.py:337, 392, 461`, `app/customers/services/opening_bill_service.py:542`, `app/vendors/services/opening_bill_service.py:378` |
| CUSTQ-1 | Low | An opening balance that has ever had a receipt, even one since reversed, cannot be taken back: the two refusals point at each other | `app/customers/services/opening_bill_service.py:343-351`, `app/customers/services/customer_service.py:396` |
| CUSTQ-2 | Medium | A role refused an opening balance on the customer can enter the same debt as an opening bill, and can cancel an opening bill somebody else entered | `app/customers/api/router.py:528-545, 566-575` (both on `CUSTOMER_UPDATE`), `:432-440` (`CUSTOMER_IMPORT`) |

### BUYQ-25 -- pending on the reconciliation ignores the other document (Low)

T1006SUZA-R and T1006D5GD-R, sequence S4 of `r4a.py`: 10 + 2 free received
(GRN-…-000007) and billed (PI-…-000004).

1. 10 off the **bill** line, completed (PR-…-000007).
2. The 2 free off the **receipt** line, completed (PR-…-000008).
3. `GET /purchase-returns/reports/reconciliation`: PR-…-000008, source
   GRN-…-000007, `received_quantity` 12.0000, `already_returned_quantity`
   **0.0000**, returning 2.0000, `pending_quantity` **10.0000**.
4. A return of 1 off that receipt line: 422 "…can still send back 0 bought
   and 0 free. 10 of these goods have already gone back against the supplier
   bill for them."

**Expected:** pending 0, or the 10 shown as returned by the other route.
**Actual:** the report and `GET /purchase-returns/{id}` (the line's
`already_returned_quantity`) still count only the returns naming the same
source line, which is what the save did before #1206. The cap is right; the
report disagrees with it. Seen the same way in round 3's free-goods rows
(`p3.log`: PR-…-000027, pending 10.0000 on a receipt whose 10 went back off
its bill).

### BUYQ-26 -- "today" is the server's UTC day, not the firm's (Low to Medium)

Found because the round ran just after midnight. The machine's day was
2026-10-06; the server's was 2026-10-05 until 05:30 IST.

1. TEST01, case 009's fixture (`b02.log`, `b02r.log`): a return dated today (2026-10-06, as the fixture's
   receipt and bill are) completed with a credit of 236.00.
   `POST /payments/supplier-credits/{id}/refunds` with `refunded_on`
   2026-10-06: **422** "A refund cannot be received on a future date." With
   `refunded_on` 2026-10-05: **422** "A refund is received on or after the
   return, 2026-10-06." So that return cannot be refunded at all until 05:30.
   The same for a debit note's refund (case 017).
2. `POST /customers/{id}/opening-bills` with `bill_date` 2026-10-06: 422 "An
   opening bill is one raised before the books here start, so its date cannot
   be after 2026-10-05."
3. T1006SUZA-R, where every document is dated 2026-10-06:
   `GET /inventory/reports/stock-valuation`, with no date and with
   `to_date=2026-10-06`: Grand total **0.00**, "Inventory account in the
   books" **0.00**, no product row, while the trial balance holds Dr 1200
   12,838.38 and the products are on hand. The router takes
   `min(to_date, utc_now().date())`.
4. A customer's opening balance typed at 00:25 on the 6th is given a bill
   dated the 5th, due the 5th plus the terms. `rated_on` of a supplier rating
   and `posting_date` of an opening bill are the 5th too.

Receipts, payments, orders, receipts of goods, bills and returns dated
2026-10-06 were all accepted, so the rule is not applied everywhere.

**Expected:** a firm in India sees its own day. **Actual:** five and a half
hours of every day belong to yesterday for these checks and reports. A
wholesaler closed at night will not meet it; a counter open past midnight, or
anybody finishing the day's entries late, will. It follows from the house rule
that the server never reads a local clock (`utc_now().date()`), so it is a
design question as much as a defect, and it may be known. The severity is the
owner's call.

### CUSTQ-1 -- an opening balance that ever had a receipt cannot be corrected (Low)

T1006YLNL-S and T1006O4W8-S (`c4.py OB2`, step H).

1. Customer created with `opening_balance` 1500.
2. Receipt of 600 allocated to its bill, then the receipt reversed. The
   customer owes 1,500.00 again and the bill reads received 0.00.
3. `PUT /customers/{id}` with `opening_balance` 0: **422** "Opening balance
   cannot be changed after receivable activity exists."
4. `POST /customers/opening-bills/{id}/cancel`: **422** "OBC-00024 is the
   opening balance entered on the customer, not a bill of its own. Set the
   customer's opening balance to 0 to take it back."
5. `DELETE /customers/{id}`: 422 "… cannot be deleted: it owes 1,500.00, has
   1 open invoice (Opening balance). Settle, refund or cancel what is open
   first…".

**Expected:** one of the refusals names a way out. **Actual:** each sends the
person to a step the other refuses. The rule in step 3 is older than #1205;
the message in step 4 is new and is what makes it a circle. A figure typed
wrongly and noticed after the first receipt can only be written off by an
adjustment.

### CUSTQ-2 -- the opening bill is a second door to the opening balance (Medium)

T1006YLNL-S and T1006O4W8-S (`c4c.py`, `c4d.py`), as Sales Manager and as
Customer Support (both hold `CUSTOMER_UPDATE`, neither holds
`CUSTOMER_MANAGE_SETTINGS`).

1. `PUT /customers/{id}` with `opening_balance` 900 on a plain customer:
   **403** "Changing a customer's opening balance needs the manage customer
   settings permission (CUSTOMER_MANAGE_SETTINGS)."
2. `POST /customers/{id}/opening-bills` `{bill_date, amount: 900}`: **201**,
   OBC-…, POSTED; journals +1 ("Opening bill OBC-…", 900.00);
   `current_outstanding` 900.00; the bill is on `receipts/outstanding` with a
   due date.
3. The same user cancels it: 200.
4. Sales Manager only (holds `CUSTOMER_IMPORT`):
   `POST /customers/opening-bills/import`, one bill of 450: 201,
   `current_outstanding` 450.00, journals +1. Customer Support: 403.
5. `c4d.py`: the administrator enters an opening bill of 5,000.00 for a
   customer; the **Sales Manager cancels it**: 200, the customer owes 0.00,
   journal `OBC-…-REV` posted.

**Expected:** by the reasoning of #1204 ("whoever is refused the figure on the
new outlet must not be able to add it by another save"), entering or removing
a customer's opening debt answers to the same code as the opening balance.
**Actual:** the opening-bill endpoints ask for `CUSTOMER_UPDATE` (the import
for `CUSTOMER_IMPORT`). Step 5 is the heavier half: the role the credit limit
constrains can take 5,000.00 off what a customer owes, with a journal. The
bill for a master balance itself cannot be cancelled by anybody (item 6).
Whether these routes should ask for `CUSTOMER_MANAGE_SETTINGS` is the owner's
call, as the edit was in selling round 4.

### Seen, not filed

- **A draft counts as gone back.** A draft return off the bill line makes the
  refusal on the receipt line read "6 of these goods have already gone back
  against the supplier bill for them", though nothing has left. The quantity
  is rightly held; only the wording runs ahead. A forgotten draft holds the
  quantity until somebody cancels it.
- **A batch typed in another case is refused in confusing words.** Naming
  the line's own batch in lower case: 422 "…brought these goods in as batch
  QA4-X06B6, so batch qa4-x06b6 cannot go back against it. … raise the return
  off the receipt that brought qa4-x06b6." Batch numbers were matched exactly
  before #1209 as well (it used to read "was never received"); spaces around
  the number are trimmed.
- **A receipt line that named no batch may still send back any batch.** A
  batch-optional product, 5 received as batch Z and 5 received with no batch:
  a return off the no-batch line naming Z saves and completes, and Z goes 5 to
  3 while the unbatched 5 stay. The code says so on purpose ("a receipt line
  that named no batch says nothing about which may go back"). It is what is
  left of BUYQ-24 for such products.
- **Free units returned first are priced.** With nothing back yet, 2 off a
  10 + 2 receipt line with `free_quantity` blank are 2 bought (236.00), as in
  round 3: bought units go first unless the free quantity is typed. After
  #1206 the bill line then gives 8 and the supplier still closes at 0.00.
- `GET /finance/ledger-accounts` ignores `page` and `page_size` and answers
  every account with no `pagination`.
- Round 3's "seen" items (preview answers 200 for a batch Save refuses; 5400
  for returned free goods; `summary` counting cancelled returns; the stock
  valuation ignoring `search`) stand as they were.

## Case text to correct

On top of the round 2 and round 3 tables, which still stand.
`docs/INDEPENDENT_TEST_CASES.md` was not edited.

| Case | Change |
| --- | --- |
| New, after D-BUY-56 (round 3's proposed free-goods case) | Remove "Until BUYQ-20 is fixed, do not return the bought units off the bill and the free units off the receipt in one case without typing the free quantity." Add: "(6) Billed, the 10 bought returned off the **bill** line: a return of 2 off the receipt line with **Free** left blank saves as 2 free at total 0.00, credits the supplier nothing and takes 2 out of stock; 3 is refused, '…can still send back 0 bought and 2 free. 10 of these goods have already gone back against the supplier bill for them.'" |
| New, after D-BUY-59 (round 3's proposed batch case) | Replace the refusal for a batch nobody received with: "On a line whose receipt named a batch, any other batch number is refused at Save: 'Line 1: the goods receipt brought these goods in as batch …, so batch … cannot go back against it. Return batch … on this line, or raise the return off the receipt that brought ….' 'Batch … was never received for this product…' is what a line whose receipt named no batch answers." |
| New, after D-BUY-61 | A case on `po-invoiced` (receipt of 6 billed, receipt of 4 not): return 6 off the bill and complete; a return of 4 off the receipt line the bill billed is refused at Save, "Return quantity exceeds the available source quantity: line 1 can still send back 0 bought and 0 free. 6 of these goods have already gone back against the supplier bill for them."; the supplier's statement closes 0.00. Then on a receipt of 10 billed in full: 6 off the bill, 5 off the receipt refused ("…can still send back 4 bought and 0 free…"), 4 accepted; cancelling the return of 4 lets 4 go back off the bill instead. |
| New, after D-BUY-62 | A case for the return import: a file of two records whose second is refused answers 422 "Record 2 of 2: … Nothing was imported." and the return list has the same count before and after; the corrected file writes both as drafts. |
| TC-BUY-006, 009 to 011, 016, 035 | **Data** (on top of round 3's note): on the return reconciliation the received quantity of a line off a goods receipt is bought plus free, and the returning quantity includes the free units. |
| TC-BUY-009, TC-BUY-017 | **Note:** run with the return and the refund dated the same day as the server's (UTC) day. Between 00:00 and 05:30 IST a return dated today cannot be refunded today (BUYQ-26). |
| New, after #1204 | A case for the customer edit, as a Sales Manager: open a customer with credit days, cash-discount terms and an opening balance; changing any of them is refused, "Changing a customer's credit days / cash-discount terms / opening balance needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)."; changing only the name saves and leaves them as they were. As the firm administrator each change saves. |
| New, after D-MST-13 | A case for the opening balance: as the administrator create a customer with opening balance 1,500 and 30 credit days. Record Receipt lists one row **Opening balance**, 1,500.00, due 30 days on; so do the collection sheet and the customer ageing. A receipt of 600 against it leaves 900.00 on all three and on the customer. Cancelling that bill is refused, "… is the opening balance entered on the customer, not a bill of its own. Set the customer's opening balance to 0 to take it back."; changing the opening balance is refused, "Opening balance cannot be changed after receivable activity exists." On a customer with no receipt: 1,500 to 400 leaves one bill of 400.00 and the first cancelled; to 0 leaves none. The statement shows the opening balance once. A negative opening balance makes no bill. |

## Still to walk on screen

- Round 3's list, unchanged.
- Record Receipt, the collection sheet and the ageing screen showing the
  row **Opening balance**, and a receipt allocated to it from the screen.
- The customer form as a Sales Manager: what it shows for the four refused
  fields, and that saving a name change with the form's own payload is not
  refused (the API accepts the stored figures resent, as numbers or strings).
- The opening-bills screen for a customer whose only bill is the one for the
  master balance: what Cancel says.

## Not verified

- **Nothing was read from the database.** That every store is at
  `20261005_0333` was taken from the hand-over; the older firms' bills and the
  fresh firms' behaviour are consistent with it.
- **The overdue report for an opening balance** (see item 6): no such bill
  could be past due on the day it is entered, and the demo firms, which hold
  older ones, were not touched.
- **The backfill for a customer who had paid part of an opening balance before
  the migration.** Neither older firm has one: all six customers owed their
  full 1,500.00 with no receipt. The migration's own note says such a receipt
  stays on account and the bill reads its full amount; not seen.
- **Round 4's selling firms** (T1005FAV4-S, T10050BYK-S), which also held
  opening balances, were not read: two older firms were asked for.
- **Roles.** That the Sales Manager and Customer Support hold `CUSTOMER_UPDATE`
  and not `CUSTOMER_MANAGE_SETTINGS` was read in `app/identity/system_seed.py`
  and shown by what they were answered, not read from an endpoint (the path
  the script tried, `/me/permissions`, does not exist). Firm Manager was not
  driven this round; the firm administrator was.
- **The old build was not driven.** That BUYQ-25, CUSTQ-1 and CUSTQ-2 are not
  caused by this round's fixes rests on reading the code: the per-line count
  on the report is what the save used before #1206, and the opening-bill
  routes have asked for `CUSTOMER_UPDATE` since they were written.
- **BUYQ-26 was only met, not mapped.** Three refusals and one report were
  seen; which other screens and reports take the server's day was not walked.
  It cannot be reproduced between 05:30 and midnight IST.
- **Dates.** Everything this round entered is dated 2026-10-06 by the machine
  while the server stamped 2026-10-05 on what it dates itself. The fixes were
  judged on quantities, money and refusals, which do not depend on it; the
  two refund cases were re-run on the server's day.
- **Not re-run:** the cases that raise no return or debit note (`b03.py`,
  `b06.py`, `b07.py`, the rest of `b09.py` and `b10.py`), the generic checks
  (`g01.py`), and round 3's numbering runs (RSI, RTC). BUYQ-22 was not looked
  at again.
- **A return in another unit** than the receipt line's, across the bill and
  the receipt; a serial-tracked product; a bill raised straight off an order
  line (the path #1206's code handles for old bills, which can no longer be
  made); a goods receipt with rejected or quarantined units: none driven.
- **Two people saving at once** against the same goods was not driven. Drafts
  are counted at save, one after another here.
- **Connection resets.** None this round apart from the restart. The helper
  now reads lists 25 rows at a time.
- The desktop was not opened.
- TEST01's 708.00 (PI-2026-2027-000003) was again left alone.
