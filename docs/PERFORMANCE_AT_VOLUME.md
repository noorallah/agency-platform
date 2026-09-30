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
   **Step 3:** a slim list row without lines, names batched per page (the
   pattern `customer_names`, `product_names` and
   `ProductService.stock_for_many` already use).
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
| 2 | Chunk every large id list; summaries and outstanding in SQL | Next |
| 3 | Slim list rows and batched names for every document list | |
| 4 | SQL grouping for the report families; set-based back-dated carry | |
| 5 | Measure: a bulk seeder at the target volume and a timing script over every list and report route, run on the minimum hardware | |

`scripts/generate_transaction_history.py` makes about 60 invoices per firm and
has no volume setting, so it cannot show any of this; step 5 is a separate
seeder that inserts rows directly.
