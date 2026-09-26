# QA functional walkthrough, version 1: one firm, end to end

> **Version 1 -- kept as a backup (2026-09-26).** This is the walkthrough for the
> version 1 screens (`lib/main.dart`: the left-hand menu and dialogs). The current
> walkthrough, for the version 2 screens (top menu bar, one-screen documents,
> records as tabs), is `QA_FUNCTIONAL_WALKTHROUGH.md`. Do not update this copy.

For the QA person testing an **installed** copy of the Agency Platform with
data they create themselves, by hand, the way a customer would. It follows
one small trading firm from creation to its first month's GST return: set it
up, buy stock, sell it, collect the money, take a return, and check that the
stock, the books and the tax all agree.

Run it after the installation checklist (`INSTALLER_QA_CHECKLIST.md`,
sections A and B) has passed on the same PC. Allow most of a day.

Written 2026-09-25. Every expected result was taken from the product's own
test cases (`INDEPENDENT_TEST_CASES.md`), which were driven against a running
server, and re-worked for the figures used here. Update the Expected column
when the product changes, and the Result and Notes columns as you test.

## How to use this

**The figures are chosen to be easy to check by hand.** One product, bought
at 100 and sold at 150, GST at 18% within the state. Every total below
follows from those three numbers, so when a screen disagrees you can see by
how much.

**Do the sections in order.** Unlike the developer test cases, each step here
builds on the one before: the sale needs the stock the purchase brought in.
If a step fails, note it and carry on where you can; mark later steps
`Blocked` when they cannot run.

**Screens read once when opened.** After acting in one screen, press
**Refresh** in the next before judging it.

**A refusal is often the product working.** Several steps ask you to try
something that must be refused. The Expected column says so; the refusal's
wording is part of the result.

**On every failure, capture three things**, as in the installation checklist:
a screenshot, the newest file in
`C:\ProgramData\Agency Platform\logs\server`, and the version on the sign-in
screen.

**Recording results.** Set Result to `Pass`, `Fail` or `Blocked`. Write in
Notes anything that differs from Expected, even when it passed.

### The data you will create

| What | Value |
| --- | --- |
| Firm | **QA Traders**, code `QA01`, GST number `33ABCDE1234F1Z5` (Tamil Nadu) |
| People | a firm administrator, a counter salesperson, a field salesperson |
| Product | `QA-P1` **Test Soap**, unit PIECE, GST 18% local, cost 100, price 150 |
| Supplier | `QA-V1` **QA Supplies** |
| Customer | `QA-C1` **QA Retail**, no GST number, no credit limit |
| Warehouses | `MAIN` from set-up, and `STORE2` you add |

## 1. The firm and its people

Sign in as `platform-admin@agency.local`. The header reads **Platform**.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W1 | Administration → **Firms** → **New**. Type only the name `QA Traders` and save | Refused: code, country, currency and financial year start are also required | Not run | |
| W2 | Fill code `qa01` in lower case, country `IN`, currency `INR`, financial year start `2026-04-01`, GST number `33ABCDE1234F1Z5`, deployment mode **SHARED**. Save | Saves. The code is stored as **QA01**. The first firm on a fresh install takes noticeably longer to save than later ones, because it builds the shared firm store; wait for it | Not run | |
| W3 | Select QA01 → **Set up** | Titled *Set up QA01*, verdict **Cannot post documents yet**. Seven rows: Storage done; Business profile, Books, Tax, Geography, Branches and warehouses, People each open, with a button or a hint | Not run | |
| W4 | Business profile row: choose **Wholesale** → **Assign** | *Business profile set to Wholesale.* Row reads *Assigned: WHOLESALE* | Not run | |
| W5 | Books row → **Open the books** | Notice names the year starting 2026-04-01. Row reads 24 accounts, 1 financial year, 12 periods, all 24 control accounts mapped. Verdict becomes **Can post documents** | Not run | |
| W6 | Press **Open the books** again if still offered, else skip | Nothing is created a second time | Not run | |
| W7 | Tax row → **Apply GST template** | *GST set up: 8 tax profiles and 9 rules.* Geography turns done as well, with 1 country | Not run | |
| W8 | Branches and warehouses → **Create head office and main warehouse** | *Created branch HO and warehouse MAIN.* Row reads 1 branch, 1 warehouse | Not run | |
| W9 | Administration → **Users** → **New**: your name, an email such as `admin@qa01.test`, a password, **Job template** *Firm Administrator*, firm QA01. Save | Created. People on the Set up panel now counts 1 member | Not run | |
| W10 | **Set up** again | **Finished. Every step is done.** No buttons left | Not run | |
| W11 | Sign out. Sign in as the firm administrator | The app opens in QA01 with Masters, Sales, Purchases, Inventory, Finance, Reports and Administration offered. No **Platform** in the header | Not run | |

From here on, work as the **firm administrator** unless a step says otherwise.

## 2. Masters

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W12 | Masters → **Branch & Warehouse** → **Warehouses** → New. This creates a **warehouse**; in its **Branch** field choose `HO`. Code `STORE2`, name *Back Store*. Save | Listed beside MAIN | Not run | |
| W13 | Masters → **Product Categories** → New: code `SOAP`, name *Soap*. Save. Then Masters → **Products** → New: code `QA-P1`, name *Test Soap*, Product type **Stock item** (the default), category **Soap**, base, inventory, purchase and sales unit **PIECE**, tax profile **GST 18 local**, HSN code `3401` and selling price 150 if the form offers them. Save | Saved. Reopen it: each unit, the tax profile and the category read as names, not codes or ids | Not run | |
| W14 | Masters → **Vendors** → New: code `QA-V1`, name *QA Supplies*, a phone, one address. Save | Saved and listed | Not run | |
| W15 | Edit QA-V1, change **only** the phone. Save and reopen | The phone changed; the address and everything else are still there | Not run | |
| W16 | Masters → **Customers** → New: code `QA-C1`, name *QA Retail*, type Business, currency INR, no GST number, no credit limit, one billing address in Tamil Nadu. Save | Saved and listed with outstanding 0.00 | Not run | |
| W17 | Edit QA-C1, change **only** the phone. Save and reopen | The phone changed; the address, payment terms and everything else unchanged | Not run | |
| W18 | Press **Ctrl+K** and type `Test Soap` | The product is found; choosing it opens the Products screen on it | Not run | |

## 3. Buying

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W19 | Purchases → **Purchase Orders** → New: vendor QA-V1, branch HO, warehouse MAIN, today; Add Line QA-P1, quantity **10**, unit price **100**. Save | Status **DRAFT**, a number starting `PO-` | Not run | |
| W20 | Select the draft and look at the toolbar | **Approve is not offered**, only Submit: an order cannot be approved before it is submitted | Not run | |
| W21 | **Submit**, then **Approve** | Two notices, submitted and approved. Status **APPROVED** | Not run | |
| W22 | Goods Receipts → New → pick the order. Set Accepted to **4**, warehouse MAIN → Save → select it → **Complete** | Saved as a draft first, with a notice that completing posts the stock. Then **COMPLETED**. The order reads **PARTIALLY_RECEIVED** | Not run | |
| W23 | Inventory → **Stock** → **Inventory**, filter QA-P1 | MAIN holds **4** | Not run | |
| W24 | Goods Receipts → New against the same order | Accepted defaults to the remaining **6**. Save and Complete: the order reads **RECEIVED**, MAIN holds **10** | Not run | |
| W25 | Purchase Invoices → **New** → pick the receipt of **6**. Type **Supplier Invoice Number** `QA-V1-INV-001` and today for both **Supplier Invoice Date** and **Invoice Date** — all three are required. Approve it | Approved. Total **708.00**: 600.00 plus 18% GST | Not run | |
| W26 | Goods Receipts → the receipt of 6 → **Cancel** | Refused: it has been invoiced, and the message says to cancel the purchase invoice first or raise a return | Not run | |
| W27 | Purchase Invoices → New → pick the receipt of **4**. Type **Supplier Invoice Number** `QA-V1-INV-002` and today for both dates. Approve it | Approved. Total **472.00** | Not run | |
| W28 | Finance → **Payments** → **Record Payment**: paid to QA-V1, amount **1,180.00**, method Bank, oldest first → Record | A notice that `PY-…` was recorded and posted. Open Record Payment again for QA-V1: no bills left to pay | Not run | |
| W29 | Finance → **Journal Entries**, search `PY-` → **View** | The payment debits Accounts Payable and credits Bank, 1,180.00 each | Not run | |

## 4. Stock

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W30 | Inventory → **Stock** → **Stock Ledger**, filter QA-P1 | Two `GOODS_RECEIPT` rows, +4 and +6, each naming its receipt, the balance ending at **10** | Not run | |
| W31 | Inventory → **Stock** → **Stock Summary** | QA-P1 **10**, agreeing with the Inventory tab | Not run | |
| W32 | Inventory → **Stock** → **Inventory**, select the MAIN row for QA-P1 → **Transfer** 2 to STORE2. **Reference** is optional; leave it blank | MAIN **8**, STORE2 **2**, total still 10. Blank reference: numbered from its own series (`ST-…`) | Not run | |
| W33 | Finance → Journal Entries, newest first | **No** entry for the transfer: moving stock between warehouses posts nothing to the books | Not run | |
| W34 | Transfer the 2 back from STORE2 to MAIN, reference left blank again | MAIN **10**, STORE2 0. A second `ST-…` number, not the first reused | Not run | |

## 5. Selling

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W35 | **Quotations** → New: customer QA-C1, QA-P1 quantity **4**, unit price **150** if not filled in. Create draft | A number starting `QT-`, status draft | Not run | |
| W36 | **Mark as sent** → **Customer accepted** (give a reason) → **Convert to order** | Three notices; the last says the quotation became `SO-…` and that approving the order reserves the stock | Not run | |
| W37 | Look at the quotation's toolbar again | **Convert to order** is gone: a quotation converts once | Not run | |
| W38 | **Sales Orders** → the new order → **Approve** | **APPROVED**. No credit warning, since QA-C1 has no limit | Not run | |
| W39 | Inventory → **Stock** → **Inventory**, QA-P1 | MAIN: current **10**, reserved **4**, available **6** | Not run | |
| W40 | Sales Orders → the order → **Hold**, reason *awaiting cheque* | Status *APPROVED (on hold)* | Not run | |
| W41 | **Delivery Notes** → New → the order → Save | Refused: the order is on hold, naming the reason. Reserved stays 4 | Not run | |
| W42 | Sales Orders → the order → **Release** | Status back to plain **APPROVED** | Not run | |
| W43 | Delivery Notes → New → the order: delivering **4**, warehouse MAIN → Save → **Approve** → **Dispatch** | Created as a draft, with a notice that dispatching moves the stock. After Dispatch: **DISPATCHED**, the order **DELIVERED** | Not run | |
| W44 | Inventory → **Stock** → **Inventory**, QA-P1 | MAIN current **6**, reserved **0** | Not run | |
| W45 | Stock Ledger, QA-P1 | A `DISPATCH` row of **−4** naming the delivery note | Not run | |
| W46 | **Sales Invoices** → New Invoice → **Bill this delivery note** → the note. Type **5** into Bill | Refused before sending: only 4 left to bill | Not run | |
| W47 | Set Bill to **4** → Create draft → **Approve** | **APPROVED**. Taxable **600.00**, CGST **54.00**, SGST **54.00**, total **708.00** | Not run | |
| W48 | Finance → Journal Entries → the invoice's `SI-…` entry → **View** | Debit Trade Receivables **708.00**; credit Sales **600.00** and Output Tax **108.00**. The first line says it was posted by sales_invoice | Not run | |
| W49 | Journal Entries → the delivery note's `DN-…` entry | The cost of the goods sold, **400.00** (4 × 100), debited to cost of goods and credited to inventory | Not run | |
| W50 | Masters → Customers → QA-C1 | Outstanding **708.00** | Not run | |
| W51 | Sales Invoices → the invoice → **Print** | A PDF with the CGST/SGST split, an HSN column and summary, and the amount in words | Not run | |

## 6. Money and GST

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W52 | Finance → **Receipts** → **Record Receipt**: QA-C1, amount **708.00**, Bank; under Apply to invoices put 708.00 against the invoice → Record | *RC-… recorded and posted to the ledger.* No TCS is charged: it is off for a new firm | Not run | |
| W53 | Masters → Customers → QA-C1 | Outstanding **0.00** | Not run | |
| W54 | Record Receipt again for QA-C1 | The invoice is no longer in the list to apply against | Not run | |
| W55 | Sales → **GST Returns** → this month → **GSTR-1** | *Filing as 33ABCDE1234F1Z5.* **B2CS**: one row, place **33**, 18%, taxable **600.00**, CGST **54.00**, SGST **54.00**. B2B empty, since QA-C1 has no GST number. HSN summary: quantity 4, taxable 600.00, under 3401 if you gave the product that code | Not run | |
| W56 | Same month → **GSTR-3B** | 3.1(a) taxable **600.00**, CGST 54.00, SGST 54.00: equal to GSTR-1 | Not run | |
| W57 | Sales → **E-Invoice** | The screen says plainly that it is a sandbox rehearsal, never *LIVE* | Not run | |

## 7. A return and a credit

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W58 | **Sales Returns** → New Return → against the invoice, line 1, back into MAIN, quantity **5** → Create draft | Refused: only 4 went out on this line | Not run | |
| W59 | Quantity **1** → Create draft → **Approve** → **Complete** | Completed with a notice of 1 back on the shelf and **177.00** credited to the customer (150 plus 18%) | Not run | |
| W60 | Inventory → **Stock** → **Inventory**, QA-P1 | MAIN **7**. The Stock Ledger shows a `SALES_RETURN` of +1 | Not run | |
| W61 | Masters → Customers → QA-C1 | **177.00** in the customer's favour, shown as an advance or a credit balance. Note which | Not run | |
| W62 | Sales → **Credit Notes** → Raise credit note: the invoice, line 1, reason *Rate difference*, credit before tax **50** → Raise → **Approve** | The row reads **59.00 (tax 9.00)**: 18%, the rate that line was charged | Not run | |
| W63 | Raise another on the same line for **1,000** | Refused: a credit note cannot credit more than the line was charged, naming what the line was charged and what is already credited | Not run | |

## 8. The books agree

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W64 | Finance → **Trial Balance**, this month's period | A **Balanced** chip. Trade Receivables, Sales, Output Tax, Bank, Accounts Payable and Inventory are among the rows | Not run | |
| W65 | **Profit & Loss**, same period | Income and Expenses with a net profit row. Sales less the return and the credit note, less the cost of goods, is the gross result | Not run | |
| W66 | **Balance Sheet**, same period | A **Balanced** chip. Total assets equal liabilities and equity. Its *Result for the year* equals the P&L's year-to-date net | Not run | |
| W67 | Inventory value | The stock of 7 is carried at cost, 700.00: the Inventory account on the trial balance agrees | Not run | |
| W68 | Reports → **Operational Reports**, then **Financial Reports**: open every entry | Each opens with a row count, or says *Nothing to report* when empty. Never a blank grid or an error | Not run | |
| W69 | Settings → **Audit Logs** | The firm's history: the product, the documents and the approvals from today, each naming you | Not run | |

## 9. Who can see what

Sign in as the firm administrator for W70 and W72.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W70 | Administration → Users → New: `counter@qa01.test`, a password, **Job template** *Counter Sales*. Save | Created in QA01 | Not run | |
| W71 | Sign in as `counter@qa01.test`. Change the password when asked. Read the sidebar and open Finance | Sales and Inventory offered. Finance holds **only Receipts and Payments**. No Chart of Accounts, Journal Entries, Trial Balance or other ledger screens. No Administration | Not run | |
| W72 | As the firm administrator, create `field@qa01.test` with *Field Sales* | Created | Not run | |
| W73 | Sign in as `field@qa01.test` | No Administration. Under Sales no Commission, Credit Notes, TCS, Price Lists, Promotions or GST Returns | Not run | |
| W74 | As `field@qa01.test`, Masters → Customers → **Settings** | The credit policy opens read-only, saying that changing it needs the manage customer settings permission | Not run | |

## 10. The data survives

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W75 | Restart the PC. Wait a minute and open the app | Sign-in appears without starting anything by hand. Everything from sections 1 to 9 is still there | Not run | |
| W76 | Run the same Setup.exe again (an upgrade to the same version) | A backup is taken first. Afterwards sign in as before; every record is still there | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Steps passed / failed / blocked | |
| Server log files sent | |
| Worst problem found | |
