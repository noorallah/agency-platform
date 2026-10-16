# History documents and their imports: design note

**Status: design note for gaps G7 and G8 of `docs/SWATHI_IMPORT_PLAN.md`,
written 2026-10-17, for the owner's yes. Nothing in it is built.** Section 12
lists what only the owner can settle.

## 1. What it does for the user

The owner decided on 2026-10-12 that old years come across as **history**
(way A in the plan): a bill from before the start date is kept exactly as it
was issued, and nothing in it touches stock, the ledger or GST. This note
designs the two pieces that decision needs.

**G7, a place to keep them.** A firm can open an **Old records** screen and:

- find a bill by number, customer, date, item or amount, for any old year;
- open it and see it as it was issued (header, lines, free quantity, batch,
  discount, GST, round-off, total), and print it again in the firm's bill
  layout;
- open a customer and see the old account, bill by bill and receipt by
  receipt, in a block marked *History*;
- start a return in the new year from an old bill (the return names the
  bill; it posts as a normal return of the new year);
- ask for past sales by item and month, which is what purchase planning
  (backlog 93) averages from.

It cannot edit, cancel, approve or post an old record. It cannot appear in a
stock report, a trial balance, a GST return, an ageing, a commission run, a
credit-limit check or a loyalty balance.

**G8, bringing them in.** One import per kind of record, in the same shape as
the other imports: a template, a **check** that names every problem by row and
column and writes nothing, and an **apply** that is all or nothing. The kinds:
sales bills, purchase bills, receipts, payments, sales returns, credit and
debit notes, and cash vouchers. A second run skips what the first brought in.

Under way B (replay the year as live documents, not chosen) the same files
would feed the live services instead. Section 9 says what that needs and why
the history design does not have to wait for it.

## 2. What is there today

Read on 2026-10-17 at main `3668be9d`.

- Live bills are `sales_invoices`, `sales_invoice_lines` and
  `sales_invoice_line_taxes` (`app/sales_invoice/models/sales_invoice.py`).
  Creating one reserves stock and posts through `DocumentPostingService`.
- Returns are `sales_returns` and lines (`app/sales_return/models/`), credit
  notes `credit_notes` (`app/credit_note/models/credit_note.py`), debit notes
  have their own modules, money is `settlements` and `settlement_allocations`
  (`app/settlements/models/settlement.py`), and a journal is
  `JournalEntry` (`app/finance/models/finance.py`).
- The bill import (`POST /sales-invoices/import`) takes our internal ids,
  recalculates every figure and posts as a live bill. It is not reused here
  (the plan, section 3, reasons 1 to 7).
- `app/common/file_import.py` is the one import framework: `FileImporter` with
  `run`, `_stage`, `_commit`, `RowReader`, `Column`, `ImportIssue`. Products,
  customers, suppliers, opening bills, opening trial balance, opening stock,
  brands, routes, segments, principals, salesmen and the chart of accounts run
  on it. A file in another program's layout is mapped onto the template by
  `app/imports` (kinds in `IMPORT_KINDS`, `remap_headings`, saved heading and
  value mappings).
- **G2 is built.** `import_source_keys`, with `lookup` and `stage_record` in
  `app/imports/services/import_source_keys.py`, keeps the old software's
  number against our record id, per firm, source system and subject. It
  commits nothing and is meant to be called inside the importer's one
  transaction.
- **G10 is built.** A live receipt carries `discount_amount`. An old receipt's
  `cdis` is kept as a figure on the history receipt (section 5); it is not
  posted.
- A proforma is the existing precedent for "a sales document that posts
  nothing": it has its own tables and number series and no journal key
  (`docs/LEDGER_POSTING_RULES.md`, *A proforma posts nothing*). History
  documents follow that precedent, one step further: they are not even in the
  document lifecycle.
- The sales chain's rule that downstream documents record
  `source_document_line_id` as a bare UUID (`docs/SALES_CHAIN_RULES.md`) is
  what lets a new return point at an old bill without a foreign key into the
  live tables.

## 3. Where a history bill is kept

**Decision 1: a table of its own, not a flag on `sales_invoices`.**

A flag (`is_history`) on the live tables means every query that reads
`sales_invoices` today (about every report, the GST returns, the ageing, the
statement, the commission run, the loyalty earn, the search, the dashboard
and the volume reports) must remember to exclude it. This repository has
shipped that class of defect repeatedly: a filter somebody forgets is a
silent wrong figure in a closed return. A separate pair of tables cannot
leak, because nothing reads them unless it names them.

New tables, firm-owned, in every firm store (BaseEntity as usual, so
`version`, soft delete and actors come with them):

**`history_documents`** (one row per old record of any kind)

| Column | Meaning |
| --- | --- |
| `firm_id` | the firm |
| `kind` | `SALES_BILL`, `PURCHASE_BILL`, `RECEIPT`, `PAYMENT`, `SALES_RETURN`, `CREDIT_NOTE`, `DEBIT_NOTE`, `VOUCHER` |
| `document_number` | the number as issued, text, kept exactly (letters, slashes, spaces) |
| `document_date` | date as issued |
| `financial_year_label` | text such as `2025-26`, as the old program had it |
| `source_system` | text, `SWATHI` for now (same value G2 uses) |
| `customer_id` / `vendor_id` | nullable keys to our master, set when the party was matched by its old code (section 6) |
| `party_code`, `party_name` | the old code and the name as printed on the document, kept even when matched |
| `party_gstin`, `place_of_supply` | as issued |
| `salesman_id`, `route_id` | nullable, matched when known |
| `gross_amount`, `discount_amount`, `taxable_amount`, `tax_amount`, `round_off`, `total_amount` | **header figures as issued**, never derived |
| `payment_mode`, `cash_discount_amount`, `narration` | receipts and vouchers use these; bills leave them empty |
| `original_document_id` | nullable, the history document this one reverses or settles (a return's bill, a receipt's bill) |
| `import_batch_id` | the import run that wrote it, so a run can be listed and (before anyone relies on it) withdrawn |
| `extra` | none. No JSON column (CLAUDE.md: typed columns) |

Unique key: `firm_id, kind, source_system, document_number,
financial_year_label` among live rows (a Swathi bill number restarts each
year, so the year is part of the key; section 7).

**`history_document_lines`** (bills and returns only)

`history_document_id`, `line_number`, `product_id` (nullable, matched by old
item code), `item_code`, `item_name` (as printed), `hsn_code`, `batch_number`,
`expiry_date`, `mrp`, `quantity`, `free_quantity`, `unit_text` (the unit as
the old program printed it; our unit master is not consulted), `rate`,
`discount_percent`, `discount_amount`, `taxable_amount`, `tax_rate`,
`cgst_amount`, `sgst_amount`, `igst_amount`, `cess_amount`, `line_total`.

Every money column is a stored figure. **No row is recalculated on save, on
read or on print.** A line whose figures do not add up to its header (plan
D7) is stored as issued and listed in the check report; it is not refused and
not corrected.

**`history_document_links`** (a receipt names the bills it settled)

`receipt_id`, `bill_id` (both history documents), `amount_settled`,
`discount_amount`. A receipt that names no bill has no rows here and is shown
as on account. This is what lets the customer's old account be shown "bill by
bill and receipt by receipt" without computing anything.

Why one header table for every kind and not one table per kind: the fields in
common (number, date, party, totals, narration) are most of the columns, the
search screen is one screen, and a new kind later (a delivery challan, a
quotation) is a value in `kind`. Why separate lines and links: a bill has
many lines, a receipt has many bills, and those are the only repeating
groups.

## 4. How a history record stays out of the books

The guarantee is structural and then tested.

- **No posting key.** Neither table has `journal_entry_id`,
  `receivable_transaction_id` or a stock movement id, the way a proforma has
  none. There is nowhere to record that anything was posted, so nothing can
  have been.
- **No lifecycle.** The documents are not in `app/document_framework`; no
  state, no number reservation, no timeline, no approval, no bulk action. The
  number is text typed by the old program, not issued by ours, so it can never
  collide with a number our series issues (the new year's series start at 1
  and carry their own prefix; section 7 of the bill-series note covers it).
- **No service that mutates after import.** The service exposes `search`,
  `get`, `list_for_party`, `print`, `sales_by_item`. The only write is the
  import. There is no update or delete route: a wrong import is corrected by
  withdrawing its batch (Decision 7) and running it again.
- **A guard test, in the shape of the existing ones.**
  `tests/unit/test_history_documents_stay_out_of_reports.py` walks the
  `app/` tree with `ast` and fails the build if any module other than
  `app/history_documents` and the two named readers (customer statement
  block, past-sales-by-item) imports the history models. It also asserts the
  tables carry no key to a posting table. Like `test_time_conventions.py` it
  uses an AST, not a grep, and pins the allowed readers with the reason for
  each, so an added reader is a decision in a diff.
- **A reader that mixes them says so.** The two readers that show history
  beside live data (the customer's account and past sales for planning)
  return history rows in a separate, labelled block or series, never summed
  into a live balance. The customer's outstanding, ageing and credit check
  keep reading live data only; the opening bills of step 8 are what carry
  the unpaid figure across.
- **Reports that must not see them.** `docs/MODULE_STATUS.md` lists the
  report routes; the guard test above is what makes "must not" true. The
  GST returns, trial balance, stock valuation, commission, loyalty, rebates,
  targets, messaging and e-invoice never import the models.
- **Searching it.** The global search (`app/search`) gets one entry, *Old
  records*, behind its own permission, so a bill number typed in the top box
  finds the old bill too, labelled History. It is not mixed into the
  search entries for live bills.

## 5. Searching and printing

**Search.** `GET /api/v1/history-documents` with the whitelisted `page`,
`page_size`, `search`, `sort_by`, `sort_direction` plus `kind`,
`financial_year_label`, `party_id`, `date_from`, `date_to`, `item_code`,
`amount_min`, `amount_max`. `search` matches number and party name. Indexed
on `(firm_id, kind, document_date)`, `(firm_id, customer_id, document_date)`,
`(firm_id, document_number)` and on the lines' `(product_id)` and
`(item_code)`. A list page is built in bulk (`children_by_parent`), like every
other list. `item_code` filters through the lines. The list is checked at the
PERF01 volume (110,000 bills and several lines each) before anyone calls it
fast.

**Open.** `GET /api/v1/history-documents/{id}` returns header, lines and
links. Published with an `ETag` and `version` like every record, although
nothing writes it.

**Print.** The printed old bill uses the firm's bill print layout
(`app/report_layouts`), fed from the stored figures. It reuses the layout, not
the live bill's calculation: the print path takes the stored GST split and
round-off as they are. It carries a visible line, *Copy of a bill issued in
the previous system*, so a reprint can never pass for a new tax invoice (a
reprint of a GST invoice for a filed month is something an inspector would
ask about). Receipts, returns and vouchers print on a plain statement layout.

**Customer account.** The customer screen gains a *History* tab: old bills,
receipts, returns and credit notes in date order, with a running figure
computed from the stored amounts in date order (never a stored
`outstanding_after`, as the ledger rules say). It is labelled *Not part of
the current balance*.

**Past sales by item.** `GET /api/v1/history-documents/sales-by-item` groups
in SQL by product and month, over `SALES_BILL` and `SALES_RETURN` lines, and
nothing else. Purchase planning (backlog 93) may read it; it states in its
response that the figures are history.

**Desktop.** Features go only into the phase 2 UI. An *Old records* module in
`module_catalog.dart` (and a `report_catalog.dart` entry for the by-item
view, because a sibling's entry makes an unlisted report look reachable),
gated on the business profile's module code and a new permission pair
`HISTORY_DOCUMENT_VIEW` and `HISTORY_DOCUMENT_IMPORT`, both seeded in
`PERMISSION_GROUPS` with a migration to insert them. The import permission is
not granted to roles that hold day-to-day billing.

## 6. Linking to the customer and the product

Matching uses the old codes already brought in, through G2: the customer's
`acode` and the item's `icode` are what steps 3 to 5 stored in
`import_source_keys`. The import looks every party and item code up once for
the file (one query, in chunks via `over_chunks`), never per row.

- **Matched:** `customer_id` / `vendor_id` / `product_id` is set. The name and
  code as printed are kept anyway, because a customer renamed since 2021 must
  still print as it was.
- **Not matched:** the check lists the row and column (`CustomerCode 1234 is
  not a customer brought in`). The row is refused by default. Decision 2
  covers an alternative.
- **A sales bill to a customer who was later deleted or merged** still prints
  from the stored name; the key is nullable for that reason, and a soft-deleted
  customer's old bills stay visible on the Old records screen.
- **A return in the new year pointing at an old bill:** the sales return's
  source is a bare UUID with no foreign key by the chain's existing
  convention; the new `source_kind` value `HISTORY_BILL` (a text value, not a
  schema change) names the history document. A live return from a history bill
  does not check the bill's quantities against stock; it checks them against
  the history lines' quantities less earlier returns of that bill (live and
  history), with the batch from the old line, and posts as an ordinary return
  of the new year. Whether the first release builds that link or only the
  search is Decision 6.

## 7. Keys and running it twice (G2)

The key for every kind is the old software's own number, qualified by what
makes it unique there:

| Kind | Subject in `import_source_keys` | Key |
| --- | --- | --- |
| Sales bill | `HISTORY_SALES_BILL` | financial year + company/series + bill number as the old program stores it |
| Purchase bill | `HISTORY_PURCHASE_BILL` | financial year + the program's own purchase entry number (not the supplier's bill number, which two suppliers may repeat) |
| Receipt / payment | `HISTORY_RECEIPT`, `HISTORY_PAYMENT` | financial year + receipt number |
| Return | `HISTORY_SALES_RETURN` | financial year + return number |
| Credit / debit note | `HISTORY_CREDIT_NOTE`, `HISTORY_DEBIT_NOTE` | financial year + note number |
| Voucher | `HISTORY_VOUCHER` | financial year + voucher type + voucher number |

The exact composition of each key is settled when the converter is written
against the real tables (`shead`, `phead`, `receipt`, `returns`, `crdr`); the
rule is that it is the shortest string that is unique in the dump, written in
one place in the converter and never rebuilt elsewhere.

Run flow, for every kind:

1. `lookup` all keys in the file once.
2. A key already answered is **skipped** and reported as *already brought in*,
   not as an error; the report counts new, skipped and refused separately.
3. For every new record, the importer creates the history rows and calls
   `stage_record` in the same transaction. A crash leaves neither.
4. If the same key appears twice **inside one file** the second is refused by
   row, naming the first.

`financial_year_label` is part of the unique key on the table as well, so
even if a key table row were lost, a re-run would be refused at the database
rather than duplicate.

**A changed record on a second run is not updated.** History is a record of
what was issued; if the old program's bill was edited after the first import
(the owner took a fresh backup, plan D8), the check lists it as *differs from
what was brought in* with the changed figures, and the person chooses to
withdraw the batch and re-run (Decision 7). Silent overwrite would be the
failure the import exists to prevent.

## 8. The imports (G8), kind by kind

All on `FileImporter` (`app/common/file_import.py`): a `Column` list per kind,
`RowReader` for typed reads, `ImportIssue` by row and column, `run` with
`apply=False` as the check and `apply=True` as the write, one commit. Each has
`GET .../import-template`, which carries the firm's own party and item codes
as sample rows, and `POST .../import-file`, mappable by `app/imports` (a new
`IMPORT_KINDS` entry per kind, so the Swathi headings are remapped, and
value mappings, such as the old payment-mode letters, ride the existing
`value_mapping`). The routes are under `/api/v1/history-documents/` and are
declared before `/{id}`, since the route-declaration guard fails the other
order. The permission is `HISTORY_DOCUMENT_IMPORT`. A file arrives as bytes;
a JSON import is not offered (the current one's flaw, reason 7).

A bill has a header row and line rows. One file for a bill kind has one row
per line, repeating the header columns, grouped on the bill key; a row whose
header columns disagree with the first row of its group is refused by row and
column. (This is how the existing opening-bill imports read repeating groups.)

**Sales bill / purchase bill** (header; line)

- Header: *BillNumber, BillDate, FinancialYear, Series, CustomerCode (or
  SupplierCode), PartyName, PartyGSTIN, PlaceOfSupply, Salesman, Route, Gross,
  Discount, Taxable, CGST, SGST, IGST, Cess, RoundOff, Total, PaymentMode,
  Narration*.
- Line: *ItemCode, ItemName, HSN, Batch, Expiry, MRP, Quantity, FreeQuantity,
  Unit, Rate, DiscountPercent, DiscountAmount, TaxableValue, TaxRate, CGST,
  SGST, IGST, LineTotal*.
- Checks: date parses and falls inside the stated financial year; party and
  item codes are known (Decision 2); no figure negative except a return
  line; header total equals taxable plus tax plus round-off **to the paisa, or
  the bill is listed (D7) and still stored as issued**. The check never
  changes a figure.

**Receipt / payment** (header; settled bills)

- *ReceiptNumber, ReceiptDate, FinancialYear, CustomerCode, Amount, Mode,
  Reference, CashDiscount, Narration, BillNumber, BillYear, AmountSettled*
  (repeating per settled bill).
- A settled bill must be found, as a history bill, in this file or among
  those already brought in (by its G2 key). A bill not found is a row error
  (the plan's "most tied to a bill" leaves some on account; those simply have
  no bill columns).
- `CashDiscount` (Swathi `cdis`, 810 of 2,844 in the larger firm) is stored
  on the history receipt and on its link row as `discount_amount`. It is not
  posted. The check confirms the sum of the settled amounts plus discount
  equals the receipt amount, or lists the receipt.
- Ordering: bills before receipts, which the converter guarantees by running
  the kinds in that order inside a run; an import of a receipt file alone
  against bills of a previous run works for the same reason.

**Sales return / credit note / debit note**

- *Number, Date, FinancialYear, CustomerCode, OriginalBillNumber,
  OriginalBillYear, Reason, Taxable, Tax, Total, Narration* and the same line
  columns as a bill (a return carries goods; a credit or debit note may carry
  only an amount, in which case it has no lines).
- `OriginalBillNumber`, when given, must resolve to a history bill (G2 key);
  `original_document_id` is set. Absent is allowed: a note against no bill.

**Voucher** (cash and journal vouchers)

- *VoucherNumber, VoucherDate, FinancialYear, VoucherType, AccountCode,
  AccountName, Debit, Credit, Narration*, one row per leg, grouped on the
  voucher key. Total debit must equal total credit per voucher, or the
  voucher is listed.
- Its legs are stored as lines carrying the account code and name as printed
  (text, no key to the live chart), because nothing is posted. This is the
  only kind whose lines are not goods; it uses `history_document_lines` with
  `item_code` carrying the account code, `item_name` the account name and
  `taxable_amount` empty, with a debit/credit pair as two extra nullable
  columns `debit_amount` and `credit_amount` on the line table.

**What the check lists, whatever the kind.** Unknown party code; unknown item
code; date outside the year; duplicate key within the file; key already
brought in (as skipped, not an error); a header total that differs from its
lines by more than a rupee (D7); a receipt whose settled bills do not add up;
a note whose original bill is not found; a voucher that does not balance.
Warnings (stored anyway) and refusals (not stored) are separate lists, and the
apply is **all or nothing on the refusals**: one refused row stops the file
and nothing is written, as with every other import. A person fixes the file
or maps the code and runs it again, which is safe because of the keys.

**Volume and chunking.** A year of the larger firm is on the order of 110,000
bills (the PERF01 figure). A single transaction of that size is not wanted;
the converter feeds the importer one **year and kind at a time**, in chunks of
500 bills, each chunk one transaction with the keys inside it, and the
all-or-nothing rule is per chunk with the run reporting how many chunks
passed. A chunk that fails stops the run, and a re-run skips the chunks
already done by key. (Decision 5.)

## 9. Under way B: the same kinds as live documents

Not decided and not built: the owner chose way A on 2026-10-12. If it is ever
chosen, G8's per-kind columns above are the **same file layouts**; only the
sink changes.

- The importer's `_stage` calls the module's `stage_*` services (as the
  sales invoice, receipts, return and credit-note modules expose them)
  instead of writing history rows, so the document is live: stock moves,
  the journal posts, GST is calculated.
- It needs what the plan lists as missing: an *as issued* mode that stores
  the printed figures and refuses to recalculate (plan reason 2); cost by lot
  (G1, backlog 101/103); a switch that silences messaging, e-invoice,
  loyalty, offers, commission, credit-limit warnings and approval steps
  (reason 6); and the receipt, return and voucher importers writing through
  `stage_*` with the discount mapped onto `discount_amount` (G10).
- The key table (G2) works unchanged: the subject names change from
  `HISTORY_*` to the live subjects.
- The file layouts, the converter and the check are shared, so building way A
  first loses nothing that way B would reuse except the sink. The history
  tables are then the archive of the years before the start date, as they are
  under A.

So G8 is designed as **one importer per kind with a pluggable sink**: the
history sink now, a live sink only if way B is ever chosen. The history sink is
the only one built.

## 10. Migrating what exists

- One migration creates the three tables in every firm store, written
  idempotent (check before create) and guarded for cross-schema foreign keys:
  `customer_id`, `vendor_id`, `product_id`, `salesman_id`, `route_id` are
  declared only when `sa.inspect` finds the target, none to `firms`. Timestamps
  spell out `server_default=sa.text("CURRENT_TIMESTAMP")`
  (`test_every_deployed_table_can_be_inserted_into` is the guard).
- Foreign-key names key on the referring column (`FK_<table>_<column>`).
- Two permission codes inserted by the same migration and added to
  `PERMISSION_GROUPS`.
- `app/core/database/all_models.py` gains the new model module; `alembic/env.py`
  and the schema registry test follow.
- `RESET_ORDER` in the seeders: the new tables RESTRICT customers and products,
  so they join the list, as the demo-data rule requires.
- Existing firms have no rows. Nothing is backfilled.
- Run `migrate-all` afterwards (the migration is per schema).

## 11. Tables, files and tests

New package `app/history_documents/{api/router.py, schemas/, services/,
repositories/, models/}`, registered in `app/main.py`. Importers live in
`app/history_documents/services/` beside one converter per kind, copying
`app/vendors/services/vendor_import.py`. Kinds are added to `IMPORT_KINDS` in
`app/imports`.

Tests (targeted, per the project's testing rule; no full sweep):

1. **Stays out of the books.** The AST guard of section 4; plus an
   integration-style unit test that imports a bill, then asserts stock
   movements, journal entries, receivables, GST return and trial balance are
   unchanged (counts and sums).
2. **As issued.** A bill with a header total one rupee off its lines is
   stored with the header figure and appears in the check's warning list.
3. **Round trip.** Import, open, print: every printed figure equals the file.
4. **Twice.** A second run of the same file writes nothing and reports all as
   skipped; a changed record is listed as differing and not written.
5. **All or nothing.** A file whose fifth bill has an unknown customer writes
   none of the first four.
6. **Per kind.** Receipt that settles a bill brought in earlier; receipt on
   account; credit note with and without an original bill; voucher that does
   not balance; return from a history bill in the new year (if Decision 6
   says yes).
7. **Search.** Number, party, date range, item code and amount range; page
   built in bulk (`test_list_pages_are_batched` extended); the list never
   returns another firm's rows.
8. **Permissions.** Neither permission is granted to the billing roles;
   `test_every_enforced_permission_code_is_seeded` passes.
9. **Route order.** The literal routes are declared before `/{id}`.
10. **Time.** No `date.today()`; the year label and bill date are plain dates
    as issued, not converted.
11. **Reachability.** The routes have a screen (`test_routes_have_a_caller`,
    `test_reports_have_a_screen`) and the desktop screens a widget test with a
    refusing case and a mixed-role case.
12. **Docs.** `docs/DEFECTS.md`, `docs/TABLE_CATALOGUE.md` and the
    import list in `docs/DEMO_DATA.md` are updated in the same PR as the
    build, not this one.

## 12. Questions for the owner

Each has a proposal; a plain yes is enough.

1. **Separate tables or a flag on the live bill tables (Decision 1).**
   Proposed: separate tables (`history_documents`, lines, links). A flag
   puts the burden on every report to exclude, and one forgotten filter
   changes a filed return. Confirm.
2. **A history record whose customer or item is not in our masters.**
   Proposed: refuse the row in the check, so the firm first completes steps
   3 to 5 (which they have to do anyway). The alternative is to store the
   name and code as text with the key empty and accept it; that is faster for
   a customer deleted years ago, but it hides a mapping error as readily as a
   deleted party. Proposed middle path: refuse by default and offer a
   *Keep the name as printed* tick on the import for the rows whose party is
   absent, listed in the report. Confirm.
3. **Which kinds to bring in.** Proposed: sales bills, receipts, sales
   returns and credit notes first (what the customer will look up); purchase
   bills and payments second; vouchers third and only if the firm asks for
   them, since the ledger itself starts from the opening balances. Confirm,
   or say vouchers are not wanted at all.
4. **How many years.** Proposed: no limit in the design; each year is a
   separate import so the firm can start with the last two and add earlier
   ones. Which years the customer wants is plan question 7.
5. **Chunking.** Proposed: one financial year and kind at a time, in chunks
   of 500 bills, each chunk its own transaction, a re-run skipping done
   chunks by key. The alternative is one transaction per year, which fails
   whole on the last bill and holds a long lock. Confirm.
6. **Return from an old bill in the new year.** Proposed: build the search
   and print first, and the return-from-history link as the second release,
   because it touches the live return service (a new `source_kind`). Or build
   both together. Which?
7. **Correcting a wrong import.** Proposed: no edit and no delete of a single
   history record; a whole import batch can be withdrawn (soft-deleted, with
   its keys) by a user holding `HISTORY_DOCUMENT_IMPORT` and a reason the
   trail keeps, and the file run again. Confirm that a single-record fix is
   not wanted.
8. **Print wording.** Proposed: the reprint says *Copy of a bill issued in
   the previous system* in the footer, in the firm's language list, and
   cannot be switched off. Confirm.
9. **Who may see old records.** Proposed: one view permission, granted to the
   owner, the accountant and sales managers, not to a salesman or a
   counter user, since the old years hold every customer's rates. Confirm.
10. **Past sales feed to planning.** Proposed: purchase planning (backlog 93)
    may read `sales-by-item` from history; it is the only live module that
    does. Confirm that this is wanted and that history bills are not counted
    into the live demand history (they are a separate series, merged only in
    that one planning view).
11. **Way B.** Proposed: stays not built. Section 9 keeps the file layouts
    sink-neutral, so nothing needs redoing if the answer ever changes.
12. **The year label.** Proposed: stored as the old program's text, as
    issued, and a financial-year selector (G14) filters on it; it is not
    mapped onto our financial year records, since the old years do not exist
    as years in our books. Confirm.

## 13. What other programs do

Stated from general knowledge, not checked against any current manual.

- **Tally.** Moving to a new financial year carries forward closing balances
  and bill-wise outstanding; the old year's vouchers stay in the company's
  data under the old period and are read through the period selector.
  Splitting a company into a new year and keeping the old one attached is
  the usual way to hold history. Old vouchers stay editable by default unless
  locked. Here they cannot be edited at all.
- **Busy.** Data for each year is kept in its own company file; opening a
  previous year's file shows its bills as they were, and the new year starts
  from the transferred balances. Old years are reached by switching the
  company file.
- **ERPNext.** Importing past documents is commonly done with the data
  import tool as submitted documents with a *posting date* in the past, so
  they post to the ledger; or by opening entries. The system has no
  "outside the books" state, which is why imported history there still moves
  the books.

All three keep old years inside the accounts. This design keeps them beside
the accounts, which is what the owner asked for: a record that can be found
and printed and cannot change a closed figure.
