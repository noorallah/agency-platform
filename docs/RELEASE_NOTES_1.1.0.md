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

## Upgrading

Setup backs up the database, then migrates every firm's store to the new
schema (revisions `20261001_0175` to `20261001_0179`: TDS columns, GST
payments, user work defaults, the offer mode, received now on the bill). Nothing existing changes how
it prices or posts: TDS is blank unless entered, offers still combine unless
a firm chooses Best offer only, and a cap applies only where one is set, and a bill with nothing received
now settles exactly as before.
