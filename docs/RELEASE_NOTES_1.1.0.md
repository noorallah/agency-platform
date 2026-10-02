# Agency Platform 1.1.0: release notes and test hand-over

Release 1.1.0 is the **go-live release**: what the first real firms need to
come over from their old software, run their books through the year, and file
their tax. It upgrades 1.0.x in place and backs up the database first.

Built 2026-10-01 from `main`. Everything below was checked by its own tests
and, where it reads real data, against the demo firms WHOLE01 and PERF01
(two years, 110,000 invoices); the full suites run on `main` before the build.

## How to test it: one pass, in this order

Each row names the screen. Do them on a copy of a firm, or on the demo firm.

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

The other changes of 2026-10-02 have their own cases: TC-BUY-009 to 014,
TC-SELL-018 and TC-SELL-020.

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
- **Batch rules** (Settings > Stock > Batch Rules): how many days count
  as near expiry, whether a near-expiry batch or a later batch chosen ahead of
  an earlier one needs a reason at dispatch, and near-expiry stock may be sold
  below the price floor with the batches kept on the approval (decision A2).
- **Debit note on a paid bill**: the part the bill no longer owes is a
  supplier credit, to set against the next bill or be paid back (decision A4).
- **One company, several customer accounts**: a GSTIN or PAN may repeat
  across customers; saving one already on another account names it and asks
  first (decision A7).
- **Overdue reminders stop after 90 days** past due (a firm setting), so
  switching reminders on does not chase every old bill (decision A12).
- **Reorder from sales**: the planning formula behind *Below reorder level*
  (#913, decision A39).
- **Debit note to a customer**: more charged on an invoice after billing,
  taxed at the invoice line's rate, owed on that invoice, declared in GSTR-1
  as a debit note and added in GSTR-3B (#918, decision A40). Not printable
  yet, like the credit note.
- Four desktop tests that failed only on a loaded machine now wait for what
  they test (#917, D-TEST-2).

## Upgrading

Setup backs up the database, then migrates every firm's store to the new
schema (revisions `20261001_0175` to `20261002_0215`: from TDS columns, GST
payments, user work defaults, the offer mode and received now on the bill to
the 2026-10-02 additions above -- GST settings, input credit, GSTR-2B, return
outcomes, batch picks and reorder planning). Nothing existing changes how
it prices or posts: TDS is blank unless entered, offers still combine unless
a firm chooses Best offer only, and a cap applies only where one is set, and a bill with nothing received
now settles exactly as before.
