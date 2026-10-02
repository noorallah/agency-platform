# Sanity check -- is this installation working?

Run it after installing or upgrading and before anything else, or whenever
something looks wrong. It has two parts:

1. **The quick check** (5-10 minutes, automatic). One command signs in to
   the running server and opens every list and report of every firm. It
   reports PASS, SLOW, SKIP or FAIL for each.
2. **Module by module** (about 45 minutes, by hand). Eleven short groups
   of cases -- sign-in, masters, pricing, selling, buying, stock, accounts,
   GST, reports, field sales, administration -- on the demo firm WHOLE01,
   each with the exact customer, product and figures to expect. It covers
   what a script cannot judge: that the screens work, price right, post
   right and print.

If either part fails, stop. Send the quick-check page (part 1) or a
screenshot and the case id (part 2) before testing anything further. A
failure here makes the detailed test cases in this folder meaningless.

---

## Part 1 -- the quick check

The quick check only reads: it sends nothing but sign-in and GETs. It is
safe on a firm's live books and can be run as often as wanted.

### Run it

Open **PowerShell** on the machine where the server is installed. The check
also works from another PC on the network: add `--no-stores` and point
`--base-url` at the server.

**An installed copy:**

```powershell
& "C:\Program Files\Agency Platform\backend\agency-server.exe" quick-check --email <your sign-in email>
```

**A developer machine** (from `backend\`):

```powershell
uv run python -m app.cli quick-check --email <your sign-in email>
```

It asks for the password. It then checks every firm that person can open, so
sign in as someone who belongs to the firms you care about. A firm
administrator checks their firm; an `ALL_FIRMS` platform member checks all
of them.

| Option | What it does |
| --- | --- |
| `--firm WHOLE01` | Only this firm. Repeat it for several. |
| `--no-stores` | Skip the migration check. Use it when running away from the server, which cannot see the database. |
| `--base-url http://192.168.1.20:8000` | Check a server on another machine. The default is this machine, port 8000. |
| `--report C:\temp\check.html` | Where the result page goes. The default is `quick-check-<date>-<time>.html` in the current folder. |
| `--timeout 120` | Seconds to wait for one answer. The default is 60. |

### What it checks

| Section | Checks |
| --- | --- |
| Server | The server answers (and which version and environment it is); the database answers |
| Sign-in | The person can sign in |
| Stores | Every store -- the platform, the shared store, every dedicated firm store -- is at the newest database migration |
| Platform | *Who am I*, *My firms*, Firms, Users, Roles |
| One section per firm | Every list and every report the firm's screens open: about 280 routes, read from the application itself, so a new screen is checked from the day it ships. Reports are asked about last month. Each firm's result is counted **module by module** -- Masters, Pricing and promotions, Selling, Buying, Stock, Accounts, GST and compliance, Field sales and incentives, Configuration and audit -- the same groups as Part 2, so a failure points at the cases to run by hand. |

### Reading the result

At the end it prints the totals, a table per firm with one row per module,
and every failure, then the path of an **HTML page** with the full result:
the same module table, then every check, failures first.

```
WHOLE01 MarketBridge Wholesale Traders Private Limited
  module                        pass  slow  skip  fail
  Masters                         40     0     1     0
  Pricing and promotions          11     0     0     0
  Selling                         59     1     1     0
  Buying                          45     0     1     0
  Stock                           22     0     0     0
  Accounts                        29     0     3     0
  GST and compliance              26     0     3     0
  Field sales and incentives      19     3     0     0
  Configuration and audit         11     3     0     0
```

| Status | Meaning | What to do |
| --- | --- | --- |
| **PASS** | Answered, in time | Nothing |
| **SLOW** | Answered, but slower than a person should wait: 1 second for a list, 3 for a report | Note it. It is not a failure, but a list of them is worth sending. |
| **SKIP** | This person may not open it, or the firm has no data the route needs (no customer to show a statement for) | Nothing. Sign in as an administrator to see more of it. |
| **FAIL** | An error; the server's own message is beside it | Stop and send the page |

The command ends with **exit code 1** when anything failed, so it can also
be scheduled and alerted on.

If the server stops answering part-way, the check stops with one failure,
*The server kept answering*, rather than hundreds. Look at the server's log
(`C:\ProgramData\Agency Platform\logs`) and at the machine's free memory.

---

## Part 2 -- module by module, on the demo data

About 45 minutes for all of it. Each module stands alone: run the ones a
change touched, or all of them after an install or upgrade. The cases use
the demo firm **WHOLE01**, whose masters are the same on every machine
because the demo seeder builds them. Every figure below was priced by the
application's own pricing and tax engine on 2026-10-02, so a different
figure is a finding, not a typo.

### The sample data

Sign in as **`whole01.admin@agency.local`**; the demo password is printed at
the end of `seed_multi_firm_demo.py`. On a developer machine, if WHOLE01 is
missing or has been changed by hand, rebuild it first:

```powershell
cd backend
uv run python scripts/seed_multi_firm_demo.py
uv run python scripts/generate_transaction_history.py --firm WHOLE01 --years 2 --reset --yes
```

| What | In WHOLE01 |
| --- | --- |
| Firm | MarketBridge Wholesale Traders Private Limited, GSTIN `29WHOLE010102Z5`, a `WHOLESALE` profile |
| Branch / warehouse | **WHL_HO** Chennai Wholesale Branch / **WHL_DC** Bulk Goods Warehouse |
| Products (18% GST, `GST_18_LOCAL`) | **DETER1K** Detergent Powder 1kg: sell 84, buy 68, MRP 89 -- **SHAMP180** Shampoo Bottle 180ml: sell 116, buy 92, MRP 120 -- **TOOTH150** Toothpaste 150g: sell 58, buy 46, MRP 60 |
| Customers (all registered, GSTIN `29WHOLE01C0..`) | **WHOLE01C01** Vijaya Super Stores: a standing discount of **7.5%**, group Retailer -- **WHOLE01C02** Anand Agencies: its own price list *NEGOTIATED* (**9.25%** on DETER1K), group **Wholesaler 3.25%**, credit limit 2,50,000 -- **WHOLE01C03** Classic Departmental Stores: group **Retailer 1.75%** |
| Price list | *STANDING*, every customer: DETER1K **2%**, **4.25%** from 15, **6.75%** from 18 |
| Promotions | *BULK5* **7.5%** on a line of 25 or more -- *BIGORDER* **₹200 off** a document of ₹4,500 or more (does not stack) -- *CLEARANCE* 1% on a line of 40 or more (stopped by BIGORDER) -- *WELCOME* 2.5% with the coupon `WELCOME10` |
| Suppliers | **WHOLE01V01** BrightHome Consumer Goods; also CleanWave Home Care and DailyNeed Distributors |
| Territory | Chennai Region, North Zone, South Zone; beats such as *South Sales Beat* |

Which discount wins, highest first: a discount typed on the line, then a
promotion, then a price list, then the customer's standing discount, then
their group's. Each line says which one it took (*Discount from*). All
three customers are in Karnataka (29), as the firm's GSTIN is, so every sale
is **CGST + SGST**, never IGST.

Write the case id and **Pass** or **Fail** in the run log at the end. On a
Fail, write what you saw.

### A. Sign-in and firms

| Id | Do | Expect |
| --- | --- | --- |
| SAN-A1 | Sign in as `whole01.admin@agency.local` | Home opens on *MarketBridge Wholesale Traders*; no error banner; the menus Sell, Buy, Stock, Accounts, Masters, Reports, Admin, Settings |
| SAN-A2 | Sign in as `master.ops@agency.local`; use the firm switcher to go to **WHOLE01**, then **MEDI01**, then back | Each firm shows its own Home. WHOLE01's customer list never shows MEDI01's customers, and the reverse |
| SAN-A3 | Sign in with a wrong password | Refused with a plain message; the account is not shown as existing or not |

### B. Masters

| Id | Do | Expect |
| --- | --- | --- |
| SAN-B1 | **Masters > Customers**, open **WHOLE01C02** Anand Agencies | GSTIN `29WHOLE01C023Z5`, credit limit 2,50,000, group Wholesaler |
| SAN-B2 | Change its phone number to `9876500001`, Save; open it again | Saved; the new number shows. *Admin > Audit Logs* has the change with your name |
| SAN-B3 | **Masters > Products**, search `SHAMP` | Only **SHAMP180** Shampoo Bottle 180ml; selling price 116, MRP 120, HSN 330510 |
| SAN-B4 | **Masters > Vendors**, open **WHOLE01V01** | BrightHome Consumer Goods opens with its details |
| SAN-B5 | **Masters > Customers > New**: save with the name empty | Refused, naming the field; nothing is created |

### C. Pricing -- one quotation, every discount tier

**Sell > Quotations > New**, customer and lines as in each row, branch
WHL_HO, warehouse WHL_DC, leave every discount box **blank**. Read the
figures before saving; save only SAN-C1 (it is used in D1).

| Id | Customer | Line | Expect on the line | Expect in total |
| --- | --- | --- | --- | --- |
| SAN-C1 | WHOLE01C01 | TOOTH150 × 10 | 7.5%, from **customer**; discount 43.50 | taxable 536.50, tax 96.57, **total 633.07** |
| SAN-C2 | WHOLE01C01 | DETER1K × 10 | 2%, from **price list** (the list outranks the customer's 7.5%) | taxable 823.20, tax 148.18, **total 971.38** |
| SAN-C3 | WHOLE01C01 | DETER1K × 18 | 6.75%, from **price list** (the break at 18) | taxable 1,409.94, tax 253.79, **total 1,663.73** |
| SAN-C4 | WHOLE01C02 | DETER1K × 10 | 9.25%, from **price list** (its own *NEGOTIATED* list) | taxable 762.30, tax 137.21, **total 899.51** |
| SAN-C5 | WHOLE01C02 | SHAMP180 × 5 | 3.25%, from **customer group** | taxable 561.15, tax 101.01, **total 662.16** |
| SAN-C6 | WHOLE01C03 | SHAMP180 × 5 | 1.75%, from **customer group** | taxable 569.85, tax 102.57, **total 672.42** |
| SAN-C7 | WHOLE01C03 | TOOTH150 × 30 | 7.5%, from **promotion** BULK5 | taxable 1,609.50, tax 289.71, **total 1,899.21** |
| SAN-C8 | WHOLE01C03 | SHAMP180 × 40 | 7.5%, from **promotion** BULK5 (not CLEARANCE) | bill discount **200** (BIGORDER), taxable 4,092.00, tax 736.56, **total 4,828.56** |
| SAN-C9 | WHOLE01C01 | TOOTH150 × 10, type **0** in the discount box | 0%, typed | taxable 580.00, tax 104.40, total 684.40 -- a typed 0 refuses every arrangement |

Tax on every row is half CGST 9%, half SGST 9%.

### D. Selling -- quotation to cash

| Id | Do | Expect |
| --- | --- | --- |
| SAN-D1 | Open the quotation from SAN-C1, **Send**, then **Convert to order**; approve the order | An approved sales order for WHOLE01C01, TOOTH150 × 10, total 633.07. **Stock > Inventory**: TOOTH150 in WHL_DC shows 10 more reserved, 10 fewer available |
| SAN-D2 | **Sell > Delivery Notes**: raise the note from the order (reason *Sale*), then **Dispatch and invoice** | The note is dispatched and an approved invoice exists for 633.07. TOOTH150 on hand in WHL_DC is 10 lower than before D1 |
| SAN-D3 | Open the invoice, **Print** | The PDF shows the firm and customer GSTINs, place of supply Karnataka (29), HSN 330610, CGST 9% and SGST 9% (96.57 together), total 633.07 in figures and words |
| SAN-D4 | **Record Receipt** on the invoice: 633.07, Bank | The invoice shows paid, nothing outstanding. **Sell > Customer Statements**, WHOLE01C01: the invoice and the receipt, closing where it opened |
| SAN-D5 | **Sell > Sales Returns**: return 2 of the 10 from that invoice; complete it | A credit of 126.61 (2 × 58 less 7.5%, plus 18%); TOOTH150 on hand back up by 2; the customer's balance shows the credit |
| SAN-D6 | **Sell > Sales Orders**: a new order for WHOLE01C02, SHAMP180 × 5; **Hold** it, then try to raise a delivery note | Held orders cannot be delivered; the message says it is on hold. Release the hold and the note is allowed |

### E. Buying -- order to payment

| Id | Do | Expect |
| --- | --- | --- |
| SAN-E1 | **Buy > Purchase Orders > New**: WHOLE01V01, WHL_HO / WHL_DC, DETER1K × 20 at 68; approve | Subtotal 1,360.00, tax 244.80, **total 1,604.80** |
| SAN-E2 | **Buy > Goods Receipts**: receive all 20 against it; complete | DETER1K on hand in WHL_DC is 20 higher; the order shows received in full |
| SAN-E3 | **Buy > Purchase Invoices**: the supplier's bill for that receipt, supplier's number `BH-001`; approve | Bill total 1,604.80; *Supplier Statements*, WHOLE01V01, shows it owed |
| SAN-E4 | **Buy > Payments**: pay the bill in full from Bank | The bill shows paid; the supplier's statement closes where it opened |
| SAN-E5 | **Buy > Purchase Returns**: return 2 of the 20 | DETER1K on hand 2 lower; a debit of 160.48 (2 × 68 plus 18%) against the supplier |

### F. Stock

| Id | Do | Expect |
| --- | --- | --- |
| SAN-F1 | **Stock > Inventory**, DETER1K | One row per warehouse; WHL_DC's on-hand and available make sense after D and E |
| SAN-F2 | **Stock > Stock Ledger**, DETER1K, this month | The receipt (+20) and the return (-2) from E, each with its document number, and a running balance |
| SAN-F3 | **Stock > Stock Summary** | Every product with quantity and value; no negative quantity |
| SAN-F4 | **Stock > Physical Count**: count TOOTH150 in WHL_DC at its book quantity, post it | No difference posted; the count is recorded |

### G. Accounts

| Id | Do | Expect |
| --- | --- | --- |
| SAN-G1 | **Accounts > Ledgers**, Trade Receivables (or the customer WHOLE01C01) | The invoice from D2 (debit 633.07) and the receipt from D4 (credit 633.07) |
| SAN-G2 | **Accounts > Statements > Trial Balance**, this financial year | Opens; total debits equal total credits |
| SAN-G3 | **Accounts > Statements > Profit & Loss** and **Balance Sheet**, this year | Both open; the balance sheet balances |
| SAN-G4 | **Accounts > Journal Entries > New**: debit any expense account 500, credit Cash 500; post | Posted with a number; it appears in both ledgers. A journal whose debits and credits differ is refused |

### H. GST and compliance

| Id | Do | Expect |
| --- | --- | --- |
| SAN-H1 | **Accounts > Tax filing > GST Returns**, GSTR-1 for this month | The invoice from D2 under **B2B** with GSTIN `29WHOLE01C012Z5`, taxable 536.50, CGST + SGST 96.57; the return from D5 under credit notes (CDNR) |
| SAN-H2 | GSTR-3B for this month | 3.1(a) includes the sale less the return; 4(A)(5) includes the purchase from E3 |
| SAN-H3 | **Settings > Tax > GST Documents**: set *E-invoicing applies from* to today, E-invoice filing **Sandbox**; Save. Raise and approve a new invoice to WHOLE01C03 (SHAMP180 × 5) and **Print** it | Print is refused: *no IRN yet*; **Print reference copy** prints it under "NO IRN YET - NOT A VALID TAX INVOICE" |
| SAN-H4 | **Accounts > Tax filing > E-Invoice > To register**: the invoice from H3 is listed; **Register** it, then print it again | It leaves the list; the print carries the IRN, acknowledgement and QR in a box marked SANDBOX |
| SAN-H5 | Back in **GST Documents**, clear *E-invoicing applies from*; Save | Printing a new invoice works without an IRN again. **Leave WHOLE01 like this** so the other cases print |

### I. Reports

| Id | Do | Expect |
| --- | --- | --- |
| SAN-I1 | **Reports > Operational**: *Sales invoice register*, *Purchase invoice register* and *Stock valuation*, for this month | Each opens with rows; the sales register includes the invoices from D and H, the purchase register the bill from E3 |
| SAN-I2 | **Reports**: *Overdue sales invoices* | WHOLE01C01's invoice from D2 is not in it (paid); unpaid invoices past their due date are, with the days overdue |
| SAN-I3 | **Sell > Sales Analysis**, this month by product | TOOTH150 and SHAMP180 with the quantities sold above |

### J. Field sales and incentives

| Id | Do | Expect |
| --- | --- | --- |
| SAN-J1 | **Sell > Territories** | Chennai Region with North Zone and South Zone under it |
| SAN-J2 | **Sell > Beat Plans**, *South Sales Beat* | Its customers in visit order and the weekday it runs |
| SAN-J3 | **Sell > Commission** and **Sell > Targets** | Both open with the seeded rules and targets; nothing errors |

### K. Administration and settings

| Id | Do | Expect |
| --- | --- | --- |
| SAN-K1 | **Admin > Users**, open `whole01.sales1@agency.local` | Its firm (WHOLE01) and its roles show |
| SAN-K2 | Sign in as `whole01.sales1@agency.local` (role *Sales Executive*) | Quotations, Sales Orders, Sales Invoices and Customers are offered; Buy, Accounts and Admin are not |
| SAN-K3 | **Admin > Audit Logs**, today | The changes made in B2 and G4, with who and when |
| SAN-K4 | **Settings > Firm > Numbering Series** | Each document type with its next number; the invoice series is past the invoices made above |
| SAN-K5 | As the platform administrator: **Admin > System > Backups**, take a backup | It completes and is listed with its size and time |

When every case passes, the installation is working and the detailed cases
in sections 01-14 of this folder can be run.

---

## When it was last run

| Date | Machine | Version | Quick check | Cases failed (ids) | By |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
