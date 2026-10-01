# Performance at a real firm's volume

BACKLOG §56 stream C. Targets: **a list opens in under 1 second and a report in
under 3**, on the minimum hardware in `docs/INSTALL_GUIDE.md`, for a mid-size
distributor -- about 5,000 products, 2,000 customers, 300 suppliers and 150
invoices a day for two years.

At that volume the big tables hold roughly:

| Table | Rows |
| --- | --- |
| `sales_invoices` (and orders, delivery notes) | ~100,000 each |
| `sales_invoice_lines` | ~500,000 |
| `sales_invoice_line_taxes` | ~1,000,000 |
| `inventory_transactions`, `stock_ledger_entries` | ~1,500,000 each (every line writes RESERVE, UNRESERVE and DISPATCH) |
| `journal_entries` | ~100,000+ |
| `journal_lines`, `gl_postings` | ~600,000+ |

## What the survey found (2026-09-30, by reading the code; nothing timed yet)

Ranked by expected impact.

1. **The Inventory list and every stock write loaded whole movement
   histories, by table scan.** `InventoryRecord.transactions`,
   `.ledger_entries` and `InventoryTransaction.ledger_entries` were
   `lazy="selectin"`, and neither movement table had an index on
   `inventory_id`. Every read of a stock row -- the list, and every dispatch,
   receipt and adjustment -- loaded its whole history. **Fixed (step 1).**
2. **Reports that pass every invoice id in one `IN (...)` list will fail, not
   just slow down.** psycopg allows 65,535 bind parameters per statement.
   `ReceiptService.outstanding_invoices(party_id=None)` -> `settled_against`,
   which is behind the Sales Invoices page summary (loaded when the page
   opens), customer ageing, the overdue and customer-outstanding reports and
   the purchase twins, sends ~100,000 ids; GSTR-1 sends every line id of the
   period to read line taxes (a quarter is at the cap, a year over it).
   Several page summaries also load every document to count statuses in
   Python. **Step 2.**
3. **Every document list rebuilds each full document per row** --
   `invoice_response` is about ten queries a row (sources, lines, taxes,
   attachments, notes, events, names), so a 50-row page is ~500 queries, and
   ships every line. The same shape in the order, note, purchase, receipt,
   return and quotation lists, settlements, the inventory list (about eleven
   look-ups a row) and the inventory export (one full row build per *column*).
   **Fixed (step 3)** -- not by slimming the row, since the desktop may read
   any field of a list row, but by building the same full rows for the whole
   page at once: see the step table.
4. **Missing indexes** for the default sorts and hot look-ups. **Fixed (step 1)**
   -- see migration `20260930_0173`.
5. **Unpaged reports, and paged ones computed over the whole window in
   Python** (the by-customer / by-salesman / by-product families, GSTR-1/3B,
   reconciliation). **Step 4:** `GROUP BY` in SQL with limit/offset; chunk
   what must be read whole.
6. A back-dated posting updates every later period's balance row by row
   (`_carry_into_later_periods`). One set-based `UPDATE`. **Step 4.**

Already right: trial balance, P&L and balance sheet read the maintained
`ledger_balances`; stock on hand is a maintained balance (`inventories`,
`product_valuations`), never a sum of movements; registers page in SQL.

## The steps

| Step | What | Status |
| --- | --- | --- |
| 1 | Stop loading movement histories; indexes for the hot look-ups and sorts | Done |
| 2 | Chunk every large id list; summaries and outstanding in SQL | Done (#856) |
| 3 | Build each list page in bulk, same response | Done: every document list, settlements, the inventory list/movements/ledger and the journal list read each child table and each name once per page (`children_by_parent` in `app/core/database/batch.py`, a `*_responses(rows)` per module that the single-row builder calls with `[row]`); the inventory export builds each row once, not once per column. At 12 rows a sales-invoice page went from 148 statements to 13, a purchase-invoice page from 170 to 10, and no page grows with its length -- `tests/unit/test_list_pages_are_batched.py` pins that and that every row equals the document built alone. Left: opening-stock batches (lines and names per line, rarely listed) |
| 4 | SQL grouping for the report families; set-based back-dated carry | Reports done (#860 and its second part); set-based back-dated carry and global search left -- see "Step 4" below |
| 5 | Measure: a bulk seeder at the target volume and a timing script over every list and report route, run on the minimum hardware | Tools done; first run below (dev machine, not yet the minimum hardware) |

`scripts/generate_transaction_history.py` makes about 60 invoices per firm and
has no volume setting, so it cannot show any of this; step 5 is a separate
seeder that inserts rows directly.

## Step 4: the slow reports (2026-10-01)

Targets came from the first PERF01 run below. What each fix was:

- **Firm-wide sums ask once.** `settled_against` and `credited_against`
  (what has come off a sales invoice) accept `None` for "every invoice", and
  `whole_past_a_chunk` (`app/core/utils/chunks.py`) answers any call naming
  more ids than one chunk by grouping over the firm once and keeping the ids
  asked. Twenty statements of 5,000 binds spent most of their time having the
  ids parsed. Record Receipt's list, overdue, customer outstanding, the
  invoice summary, the ageing, net sales for commission and loyalty all gain.
- **Read the columns shown, not the rows.** The outstanding list, the
  overdue reports, GSTR's lines and taxes, customer and supplier names.
  Products and customers read for a report skip their eager collections
  (`lazyload("*")`): loading addresses and media cost as much as the rows.
- **Group in SQL**: delivery notes and sales orders by route, salesman,
  warehouse, customer and territory; purchases by product.
- **Paged and windowed reconciliations.** The sales- and purchase-invoice
  reconciliations take a period (on the bill date) and page in SQL, as the
  sales-return one already did; the desktop asks for the period. The window
  picks the source lines billed in it, the sums run over every bill of them.
- **Counting, not building.** The invoice and bill summaries counted their
  overdue tile by building the whole overdue report.
- **Only where a rule can pay.** The commission report priced every line of
  the period although money with no salesman earns nothing and a firm with
  no rule pays nothing.
- **The year read once.** TCS charged-versus-due read each buyer's receipts
  twice over; it reads the year once and replays each buyer.
- **GSTR-1 and 3B cover at most three months** (decided 2026-10-01): they are
  filed monthly or quarterly under QRMP, and a year -- GSTR-9's job -- was
  still 45 s of arithmetic over 280,000 lines after the reads were fixed.

Re-timed through `scripts/time_routes.py` on the same machine (median of
three, ms):

| Route | Before | After |
| --- | ---: | ---: |
| `/sales-invoices/reports/reconciliation` | 95,531 | 2,246 |
| `/gst-returns/gstr1` (year) | 63,527 | refused: a quarter at most |
| `/gst-returns/gstr1` (month) | 6,514 | 4,356 |
| `/gst-returns/gstr3b` (month) | 5,435 | 3,757 |
| `/inventory/opening-stock` | 53,519 | 2,003 |
| `/sales-invoices/reports/summary` | 46,298 | 3,966 |
| `/sales-invoices/reports/overdue` | 16,129 | 4,766 |
| `/sales-invoices/reports/customer-outstanding` | 15,690 | 4,518 |
| `/commission/report` (year) | 12,573 | 3,015 |
| `/tcs/reports/charged-versus-due` | 8,273 | 1,048 |
| `/customers/ageing` | 7,232 | 3,821 |

The second part was timed by calling the service directly under `cProfile`
(slower than the route, so these are upper bounds):

| Report | Before | After |
| --- | ---: | ---: |
| Delivery notes by warehouse / salesman / route (year) | 4,345 / 4,223 / 4,153 | 330 |
| Sales orders by customer (year) | 4,644 | 640 |
| Purchase-invoice reconciliation (first page) | 5,270 | 350 |
| Purchases by product (year) | 3,620 | 310 |
| Purchase-invoice summary | 3,010 | 1,830 |

**Still over target:** GSTR-1 and 3B for a month (about 4 s: Python
arithmetic over 23,000 lines), the reports that read what every open bill
owes (about 4 s -- `outstanding_invoices` derives it rather than storing it,
deliberately), global search (3.5 s: `ILIKE '%term%'` over every module needs
trigram indexes, a migration of its own), billable (1.4 s) and control
accounts (1.1 s). The six `/business-framework` 403s in the first run are not
a finding: those routes are platform-only by design (`test_platform_only_routes.py`)
and a firm administrator reads `/active-features` and `/active-modules`.

## Step 5: measuring

Two scripts, both run from `backend/`.

### `scripts/seed_volume_firm.py` -- the volume firm

Builds **PERF01**, "Performance test firm", in its own dedicated schema
(`perf01`, SCHEMA mode), so it never shares a store with another firm and can
be dropped whole. The set-up goes through the real services -- the firm and
its provisioning, a `perf01.admin@agency.local` FIRM_ADMIN (password
`PerfAdmin@12345` unless `--password` or `PERF01_PASSWORD` says otherwise),
the WHOLESALE profile, the GST template, the books for every year traded, a
head-office branch with three warehouses, and each document module's own
numbering series. Only the trading is inserted directly, through `COPY`, in
batches of 5,000 rows with one transaction per batch.

```powershell
uv run python scripts/seed_volume_firm.py                # scale 1.0
uv run python scripts/seed_volume_firm.py --scale 0.1    # a quick run
uv run python scripts/seed_volume_firm.py --reset        # drop perf01 and rebuild
```

At `--scale 1.0`: 5,000 products (one in ten batch and expiry tracked), 2,000
customers, 300 suppliers, and 730 days of trading ending yesterday at about
150 invoices a day. Every sale is a sales order, a delivery note and an
invoice, with the RESERVE / UNRESERVE / DISPATCH movements, CGST and SGST line
taxes, the receivable transaction, and the goods-issue and invoice journals.
Each supplier is ordered from once a week for whatever of theirs is below the
reorder level: order, goods receipt and bill, with their movements and
journals. About 80% of invoices and bills are settled in full, with the
allocation and the journal; about 3% of invoices get a sales return and 2% a
credit note.

What it keeps consistent: every journal balances, and `ledger_balances` is the
sum of the journals period by period, with openings carried as the journal
engine carries them; every `inventories` row is the sum of its movements, and
the inventory account equals `product_valuations` (a product costs the same at
every receipt, so the average never moves); every customer's balance is the
sum of their receivable transactions, and the receivable account equals the
customers' outstanding. Every series counter is moved past the last number
used. What it simplifies: no salesman, territory or route on any document;
one batch per tracked product; returns and credit notes only on invoices that
are never paid; no purchase returns; purchase orders are mostly one line (the
weekly reorder rarely finds more than one of a supplier's products low at
once); one lifecycle-event pair and one audit row per document. It ends with
`ANALYZE` on every table it wrote. `tests/unit/test_seed_volume_firm.py` runs
the same row builders at a tiny scale against SQLite and checks the balances.

To remove PERF01 for good: delete it on the Firms screen, then
`DROP SCHEMA perf01 CASCADE`.

### `scripts/time_routes.py` -- the timings

Signs in through `/api/v1/auth/login` as the desktop does, picks the firm from
`/api/v1/me/firms`, and times every firm-owned GET in the application's own
OpenAPI document: no path parameter (plus the per-customer and per-supplier
reports in `PER_PARTY_REPORTS`), no file exports unless `--include-exports`,
nothing under the platform paths. A list is called with default paging; a
report is called for the last complete month and the last complete financial
year where it takes a date range. Three calls each, median kept, over one
kept-alive connection. OK / SLOW against 1 s for a list and 3 s for a report;
FAIL with the status and message on an error; SKIP with the reason where a
required parameter cannot be filled from the firm's own data.

```powershell
$env:PYTHONPATH = (Get-Location).Path   # in a worktree: its app, not the venv's
uv run uvicorn app.main:app --port 8010
uv run python scripts/time_routes.py --base-url http://127.0.0.1:8010 --csv timings.csv
uv run python scripts/time_routes.py --only sales-invoices   # one family
```

### First run, 2026-10-01

Dev machine: Intel Core i9-13900H, 16 GB (2.6 GB free during the run),
Windows 11, PostgreSQL 17 in a local container; backend from this branch on
port 8010, one uvicorn worker. **Not** the minimum hardware in
`docs/INSTALL_GUIDE.md` -- expect it to be slower there.

Seed at `--scale 1.0`: **16.9 minutes**, 11.26 million rows -- 109,566 sales
invoices (and as many orders and notes), 549,057 invoice lines, 1,098,114
line taxes, 1,689,388 movements (and as many stock-ledger rows), 369,201
journals with 894,246 lines, 100,506 settlements, 20,434 purchase orders,
receipts and bills, 3,282 sales returns, 2,128 credit notes.

Timings: **258 timings of 216 routes -- 225 OK, 23 SLOW (5 lists, 18
reports), 7 FAIL, 3 SKIP.** Every document list opens in under a second: the
sales invoice list (109,566 rows) in 724 ms, movements (1.69 million) in 745
ms, journals in 114 ms, the audit log (496,127) in 149 ms.

The 25 slowest that answered:

| Route | Kind | Window | Median ms | Rows | Status |
| --- | --- | --- | ---: | ---: | --- |
| `/sales-invoices/reports/reconciliation` | report | - | 95,531 | 549,057 | SLOW |
| `/gst-returns/gstr1` | report | year | 63,527 | - | SLOW |
| `/inventory/opening-stock` | list | - | 53,519 | 3 | SLOW |
| `/gst-returns/gstr3b` | report | year | 49,414 | - | SLOW |
| `/sales-invoices/reports/summary` | report | - | 46,298 | - | SLOW |
| `/sales-invoices/reports/overdue` | report | - | 16,129 | 20,972 | SLOW |
| `/sales-invoices/reports/customer-outstanding` | report | - | 15,690 | 2,000 | SLOW |
| `/commission/report` | report | year | 12,573 | 1 | SLOW |
| `/tcs/reports/charged-versus-due` | report | - | 8,273 | 1,999 | SLOW |
| `/customers/ageing` | report | - | 7,232 | 2,000 | SLOW |
| `/gst-returns/gstr1` | report | month | 6,514 | - | SLOW |
| `/gst-returns/gstr3b` | report | month | 5,435 | - | SLOW |
| `/purchase-invoices/reports/reconciliation` | report | - | 5,016 | 23,935 | SLOW |
| `/delivery-notes/reports/by-warehouse` | report | year | 4,345 | 3 | SLOW |
| `/delivery-notes/reports/by-salesman` | report | year | 4,223 | 1 | SLOW |
| `/delivery-notes/reports/by-route` | report | year | 4,153 | 1 | SLOW |
| `/purchase-invoices/reports/overdue` | report | - | 3,708 | 3,858 | SLOW |
| `/search` | list | - | 3,532 | - | SLOW |
| `/purchases/reports/by-product` | report | year | 3,459 | 4,997 | SLOW |
| `/sales-orders/reports/by-customer` | report | year | 3,355 | 2,000 | SLOW |
| `/purchase-invoices/summary` | list | - | 3,094 | - | SLOW |
| `/sales-orders/reports/by-territory` | report | year | 2,503 | 1 | OK |
| `/sales-orders/reports/by-salesman` | report | year | 2,295 | 1 | OK |
| `/purchase-invoices/reports/outstanding` | report | - | 2,243 | 300 | OK |
| `/commission/report` | report | month | 2,150 | 1 | OK |

The two SLOW lists outside the table: `/sales-invoices/billable` (1,784 ms)
and `/finance/control-accounts` (1,081 ms, 29 rows).

Every FAIL:

| Route | Status | What |
| --- | --- | --- |
| `/delivery-notes/summary` | 503 after 7.5 s | `DeliveryNoteService.partially_delivered_orders` sends every order id in one `IN (...)` -- 109,566 ids against psycopg's 65,535-parameter limit. The Delivery Notes page summary; step 2 missed it. **Fixed in the same PR**: the order lines and `delivered_by_order_line` are read in chunks (`test_chunked_id_lists.py`). |
| `/business-framework/attribute-definitions` | 403 | FIRM_ADMIN does not hold the code; not a volume finding |
| `/business-framework/category-attribute-rules` | 403 | as above |
| `/business-framework/features` | 403 | as above |
| `/business-framework/firm-profile-assignments` | 403 | as above |
| `/business-framework/modules` | 403 | as above |
| `/business-framework/profiles` | 403 | as above |

Skipped, for want of a parameter the firm's data cannot supply:
`/sales-returns/returnable-serials`, `/tcs/preview`,
`/uom-framework/barcode-lookup`.

What this says for steps 3 and 4: the document lists already meet the target
at this volume. The misses are the report families that read every invoice or
line of the window into Python (reconciliation, GSTR-1 and 3B, the invoice
summary, overdue and customer outstanding, ageing, the by-X families over a
year), the opening-stock list (three batches, fifteen thousand lines), global
search, and two page summaries.
