# Agency Platform 1.1.0: release notes and test hand-over

Release 1.1.0 is the **go-live release**: what the first real firms need to
come over from their old software, run their books through the year, and file
their tax. It upgrades 1.0.x in place and backs up the database first.

Built 2026-10-01 from `main`. Everything below was checked by its own tests
and, where it reads real data, against the demo firms WHOLE01 and PERF01
(two years, 110,000 invoices); the full suites run on `main` before the build.

## How to test it: one pass, in this order

Each row names the screen. Do them on a copy of a firm, or on the demo firm.

**Start with the sanity check** (`docs/qa/SANITY_CHECK.md`, PDF *Sanity check* in the hand-over folder). The quick check proves the server answers, every store is migrated and every list and report of every firm opens, module by module; the 49 cases after it walk each module on the demo firm WHOLE01 with the figures to expect. If it fails, report that before anything below.

| # | What | Where | What to look for |
| --- | --- | --- | --- |
| 1 | **Opening balances checklist** | Admin > Firms > Set up | Under the steps, *Opening balances* lists products, customers, suppliers, opening bills both sides, the trial balance and opening stock, ticked as each fills, with the screen to use for the rest |
| 2 | **Opening bills from a file** | Masters > Customers > ... > Import opening bills (and Vendors) | Template names your parties; Check file lists every problem by row and column; Import posts all or nothing on the posting date |
| 3 | **Stock valuation** | Reports > Financial > Stock valuation | One *As on* date; quantity, rate, value per item; Grand total, the Inventory account and the Difference at the bottom (should be 0.00 or a paisa) |
| 4 | **The printed bill** | Any invoice billing two or more delivery notes > Print | Head lists every delivery note and order with dates, the buyer's order no., *Offers* and *You saved*; each line names its note |
| 5 | **TDS** | Buy > Payments > Record payment; Sell > Receipts > Record receipt; Accounts > Expenses > New | *TDS deducted* and *TDS section*; the screen shows what the bank moves; the bill or invoice is settled in full |
| 6 | **TDS registers** | Reports > Financial > TDS deducted; TDS deducted by customers | Each deduction with PAN (or "PAN not given"), section, quarter; customers' list shows their TAN |
| 7 | **Profit and loss for a year or months** | Accounts > Profit & Loss > Show: Months or year | Presets; *Month by month* adds a column per month; *Compare with last year* adds Last year |
| 8 | **Paying the month's GST** | Accounts > Tax filing > GST Payment | Owed, credit, paid by credit, cash and carried, head by head; record the challan (CPIN, bank, interest); next month brings the credit forward; Reverse works on the latest month only |
| 9 | **Approve many at once** | Sales Invoices, Purchase Invoices, Delivery Notes, Credit Notes, Sales Returns, Purchase Returns; Journal Entries (Post selected) | Tick two or more rows; Approve selected / Cancel selected; the result lists refusals with reasons; *Retry the refused* |
| 10 | **My Branch and Warehouse** | Settings (gear) > Firm > My Branch and Warehouse | Set yours; a new order, quotation or purchase order opens with them filled in; another user is unaffected |
| 11 | **Sales Analysis** | Sell > Insight > Sales Analysis | Rows and columns (product by month, customer by quarter ...); totals both ways; click a cell for the invoices behind it; Net of returns switch |
| 12 | **Purchase Analysis** | Buy > Insight > Purchase Analysis | The same for bills, by supplier and product |
| 13 | **Purchase price variance** | Reports > Financial > Purchase price variance | A bill at a different rate from its receipt shows both rates and the difference |
| 14 | **Offers** | Masters > Promotions | *Up to* on a percentage ("20% off, up to 500"); *... > Try offers* shows what an offer does on any date and why each offer did or did not apply; Settings > Selling > Sales Stages > *When several offers match*: Best offer only |
| 15 | **Received now on the bill** | Sell > Sales Invoices > New | *Received now*, Cash or Bank and a reference; more than the bill warns and is refused; on Approve a receipt appears under Sell > Receipts and the bill shows as paid (or part paid) |
| 16 | **Go-live guide** | `GO_LIVE_GUIDE.pdf` beside Setup.exe | Read it as the firm's accountant would |
| 17 | **Choosing batches** | Sell > Delivery Notes > New, a batch-tracked product | Every batch with expiry and days left, earliest expiry filled in; take a later one or split; expired cannot be chosen; the challan prints a row per batch (`docs/qa/08_SELLING.md` TC-SELL-019) |
| 18 | **Reorder from sales** | Settings > Buying > Purchase Settings > Reorder planning; Reports > Operational > Below reorder level | *From sales*: products with no typed level are listed from their average daily sales, with Basis and Avg/day; a typed level still wins (`docs/qa/06_PURCHASING.md` TC-BUY-015) |
| 19 | **Debit note to a customer** | Sell > Debit Notes > New, an approved invoice | Charge more on a line: tax at that line's rate; on Approve the customer owes more and Record Receipt shows the invoice at its total plus the note; GSTR-1 lists it as type D (`docs/qa/08_SELLING.md` TC-SELL-020) |
| 20 | **No print without the IRN** | Settings > Tax > GST Documents: *E-invoicing applies from* in the past; then Sell > Sales Invoices, an approved invoice to a customer with a GSTIN > Print | Refused, naming the invoice; *Print reference copy* prints under "NO IRN YET - NOT A VALID TAX INVOICE"; once registered it prints with the IRN and QR; a consumer's bill prints as before (`docs/qa/11_COMPLIANCE.md` TC-COMP-016, 017) |
| 21 | **To register and the 30-day limit** | Accounts > Tax filing > E-Invoice > ... > To register | Every B2B document without an IRN, with last day and days left, *N days left* within 5, *Late* after; registering a late one is refused naming its last day (TC-COMP-018) |
| 22 | **E-invoice route and notes** | GST Documents > route *Offline*; E-Invoice > Export for portal / Import portal result; a credit note, debit note and completed sales return | The file holds invoices and notes; importing the portal's result records each IRN; a sales return registers as a credit note naming its invoices (TC-COMP-009, 011, 012, 019) |
| 23 | **E-way bills** | E-Invoice > ... > E-way bills due; a delivery note with reason Job work above ₹50,000; a goods receipt above the limit | Consignments above the limit are listed and prompted; the note raises one without an IRN; the receipt warns until *Record e-way bill* (TC-COMP-010, 015) |
| 24 | **Purchases under GST** | Accounts > Tax filing > Rule 37 (180 days); a bill from a supplier marked *Supplier e-invoices* | Old unpaid bills with the credit to reverse, posted and reclaimed; a bill with no IRN warns, *Record IRN* clears it (TC-COMP-013, 014) |
| 25 | **Batches, the rest** | Settings > Stock > Batch Rules; a counter bill; a sales order line *Pinned batch*; a customer's *Minimum shelf life (days)*; a goods receipt with MRP | Reasons asked at dispatch; the counter bill's picks are what leaves; the pinned batch is reserved and picked; short batches passed over; no bill above the batch MRP (`docs/qa/08_SELLING.md` TC-SELL-022 to 026) |
| 26 | **Mapping an import's columns** | Masters > Products (or Customers, Vendors, opening bills, opening stock) > Import, a file with its own headings | Each heading beside the template column it is read as; change one, *Save mapping as...*, pick it again from *Saved mappings* (`docs/qa/05_MASTERS.md` TC-MAST-010) |
| 27 | **Places from India Post** | Masters > Places, a new firm | Southern states' districts, towns and PIN codes are already there; *Load places from India Post...* adds another state (`docs/qa/10_TERRITORY.md` TC-TERR-006) |
| 28 | **Quick check** | On the server PC, PowerShell: `agency-server.exe quick-check --email <you>` (see the sanity check) | Asks for the password; a table per firm, one row per module, and *RESULT: everything answered*; an HTML page with every check. Exit code 1 if anything failed |

The other changes of 2026-10-02 have their own cases: TC-BUY-009 to 018,
TC-SELL-018, TC-SELL-020 to 026, TC-MAST-009 and 010, and TC-COMP-009 to
019.

**On every failure**: a screenshot, the newest file in
`C:\ProgramData\Agency Platform\logs\server`, and the version on the sign-in
screen (1.1.0).

## What is new in 1.1.0

### Bringing a firm over
- The Set up panel's **Opening balances** checklist (#869).
- **Opening bills from a file**, both sides, with a template and a check
  (#870, D-GOLIVE-1).

### Accounts and tax
- **TDS** on payments, receipts and expenses, posted to TDS Payable and TDS
  Receivable, with the two registers for 26Q and 26AS (#872).
- **GST Payment**: the month's set-off by section 49(5) and rule 88A, cash
  payable, interest suggestion, the challan posted in one journal (#875).
- **Profit and loss** for any run of months, month by month and against last
  year (#874).
- **Stock valuation** as on any day, beside the books (#873, D-GOLIVE-3).
- **Purchase price variance**, bill line by bill line (#880).

### Everyday work
- **Bulk approve / cancel** on six document lists and **bulk post** on
  journals (#876).
- **My Branch and Warehouse**: each person's documents open where they work
  (#881).
- **Received now on the bill**: money taken at the counter is entered on the
  invoice and recorded as a receipt when it is approved (#887).
- **The printed bill** names every delivery note and order it bills (#871),
  the offers given and what the customer saved (#883).

### Analysis
- **Sales Analysis** and **Purchase Analysis**: any one or two dimensions,
  totals, drill-down (#878, #886).

### Offers
- **Try offers** before launch (#879), **percent off up to a limit** (#882),
  **best offer only** (#885).

### For the firm's accountant
- **The go-live guide** (`docs/GO_LIVE_GUIDE.md`, #877): bringing the firm
  over, TDS, approving many, closing a month and the year, licence checks,
  the monthly calendar.

### Added after the first 1.1.0 build (2026-10-02)
- **GST on the sales chain**: why each delivery note goes out (challan
  reason), dispatch before the invoice warned or blocked, *Dispatch and
  invoice* in one step, the firm's GST document settings (#903, decision A35).
- **GST on purchases**: input credit per bill line, blocked credit posted as
  an expense (#905, D-TAX-1); a supplier's GST type (#906); **GSTR-2B**
  import and matching (#909); a return off a reverse-charge bill takes its tax
  off (#897).
- **Returns to suppliers**: what a return comes back as -- credit,
  replacement or refund -- and supplier refunds (#900); a return off a paid
  bill leaves a supplier credit (#901, D-BUY-20).
- **Purchase orders**: one quantity picture per line -- received, accepted,
  returned, invoiced, pending (#899).
- **Rate includes GST** on the sales order and the quotation (#896); the
  **tax calendar** on Home (#898).
- **Choosing batches** on a delivery note, printed one row per batch (#911,
  decision A38).
- **Choosing batches on a counter bill**: a batch-tracked line opens the same
  picker as the delivery note, and the batch chosen is the one that leaves
  (#931).
- **Rule 37, the 180-day rule.** Bills unpaid 180 days after their date
  are listed with the credit to reverse, and reclaimed when paid; a firm can
  post both from the list, and GSTR-3B reports them (#941, §78 row 4).
- **The supplier's IRN on a bill.** A supplier can be marked as
  e-invoicing; its bill records the IRN from the QR code (on an approved bill
  too), and a bill from it without one is warned about, as is a second bill
  carrying the same IRN (#943, §78 row 5).
- **The e-way bill on a goods receipt.** A receipt records the e-way bill
  number and date the goods came on, completed receipts too, and one worth
  more than the firm's e-way bill limit without it is warned about (#944,
  §78 row 6).
- **Places from India Post.** Districts, towns, PIN codes and localities
  load by state from India Post's directory, shipped with the installer; the
  southern states are already loaded in every firm, with no setup step
  (#940, #942, B6).
- **The IRN and signed QR print** on a registered invoice, credit note
  and debit note; credit and debit notes to customers can now be printed
  (#939, §77 row 11).
- **Credit and debit notes are e-invoiced** like invoices, through the
  sandbox or the offline portal upload (#938, §77 row 4).
- **E-way bills for every consignment**: from the invoice without an IRN
  where the firm need not e-invoice, from a delivery note no invoice bills
  (job work, approval, van sales), or recorded by hand after raising it on
  the portal; a list of consignments above the firm's limit (₹50,000 by
  default) that still need one, and a prompt after dispatch (#937, §77 rows
  9-10).
- **E-invoice without a GSP**: a firm may file offline -- export its invoices
  as the e-invoice portal's bulk-upload JSON, upload it there, and import the
  result to record each IRN, acknowledgement and QR (#936, decision A42;
  Settings > Tax > GST Documents).
- **Map any file's columns on import**: products, customers, suppliers,
  opening bills and opening stock show the file's headings with the template
  column each is read as; change them, and save the mapping for the next
  export from Tally, Marg, Busy or Excel (#935, decision B3).
- **Batch MRP**: each batch keeps the MRP printed on it (and a selling
  price), taken from the goods receipt; no bill may charge more, and the
  challan and the invoice print each batch with its MRP. A firm may take a
  line's rate from its batch (#934, decision A41).
- **Pin a batch on a sales order** when the customer asks for one: approval
  holds that batch, and the delivery note starts with it picked (#933).
- **Minimum shelf life per customer**: a customer may ask for goods with so
  many days left; earliest-expiry dispatch passes over shorter batches, and
  one chosen by hand is refused (or warned, as the firm sets) (#932).
- **Batch rules** (Settings > Stock > Batch Rules): how many days count
  as near expiry, whether a near-expiry batch or a later batch chosen ahead of
  an earlier one needs a reason at dispatch, and near-expiry stock may be sold
  below the price floor with the batches kept on the approval (#922,
  decision A2).
- **Debit note on a paid bill**: the part the bill no longer owes is a
  supplier credit, to set against the next bill or be paid back (#923,
  decision A4).
- **One company, several customer accounts**: a GSTIN or PAN may repeat
  across customers; saving one already on another account names it and asks
  first (#924, decision A7).
- **Overdue reminders stop after 90 days** past due (a firm setting), so
  switching reminders on does not chase every old bill (#925, decision A12).
- **Preferred supplier** on a product: *Below reorder level* orders from it,
  else from the supplier last billed (#926, decision A18).
- **Cash-in-Hand and Bank Accounts groups** for a new firm's chart, so a
  contra voucher offers only money accounts (#927, decision A22; existing
  firms unchanged).
- **Reverse charge, ready-made**: the GST template carries GTA (5%) and legal
  services (18%) under reverse charge, switched off until a firm turns them
  on; applying the template again gives an existing firm the same (#928,
  A29).
- **A firm's audit trail can be given to its own people**: the firm
  administrator may grant *Firm Audit Log View* to any role, which reads that
  firm's trail and nothing else (#929, decision B1).
- **No B2B invoice leaves without its IRN.** Once the firm's *e-invoicing
  applies from* date has passed, an approved invoice to a buyer with a GSTIN
  -- and a credit or debit note against one -- is refused at print and at
  email until it has its IRN; *Print reference copy* prints it marked "NO IRN
  YET - NOT A VALID TAX INVOICE". The automatic *Invoice approved* email waits
  for the IRN and then goes (#945, §77 row 6, decision A43).
- **The 30-day limit and the To register list.** From the firm's *30-day rule
  from* date a document more than 30 days old is refused at registration,
  naming its last day; Accounts > Tax filing > E-Invoice > ... > *To register*
  lists every B2B document without an IRN with its last day, days left, *due
  soon* (5 days) or *Late*, and a Register button (#946, §77 row 7, A44).
- **A sales return's credit note is e-invoiced** as a CRN naming each invoice
  it returns goods from, prints with its IRN, and falls under the print gate
  (#946, D-TAX-2, A45).
- **GSTR-3B screen** no longer prints an inward-supplies line the server
  stopped sending, and the GST documents dialog starts at *Warn*, as the
  server does (#921, D-UI-2).
- **Reorder from sales**: the planning formula behind *Below reorder level*
  (#913, decision A39).
- **Debit note to a customer**: more charged on an invoice after billing,
  taxed at the invoice line's rate, owed on that invoice, declared in GSTR-1
  as a debit note and added in GSTR-3B (#918, decision A40). Printable, with
  the credit note, since #939.
- Four desktop tests that failed only on a loaded machine now wait for what
  they test (#917, D-TEST-2).
- **The quick check**: `agency-server quick-check` signs in to the running
  server and, reading only, checks every store is migrated and every list
  and report of every firm opens, counted module by module, with an HTML
  page of the result (#949, #950). With it, `docs/qa/SANITY_CHECK.md`: 49
  cases module by module on the demo firm WHOLE01.
- **Below reorder level** answered an error on every installed copy
  (PostgreSQL has no `max` of an id, which the report used) -- found by the
  quick check's first run and fixed (#949, D-BUY-21). Row 18 above depends
  on it.

## Upgrading

Setup backs up the database, then migrates every firm's store to the new
schema (revisions `20261001_0175` to `20261002_0234`: from TDS columns, GST
payments, user work defaults, the offer mode and received now on the bill to
the 2026-10-02 additions above -- GST settings, input credit, GSTR-2B, return
outcomes, batch picks and reorder planning, then batch rules, MRP and
pins, import mappings, the e-invoice route, e-way bills on notes and receipts,
rule 37, supplier IRNs and the India Post places). Nothing existing changes how
it prices or posts: TDS is blank unless entered, offers still combine unless
a firm chooses Best offer only, and a cap applies only where one is set, and a bill with nothing received
now settles exactly as before.
