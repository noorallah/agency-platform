# QA functional walkthrough, version 2: one firm, end to end

For the QA person testing the Agency Platform with data they create
themselves, by hand, the way a customer would. It follows one small trading
firm from creation to its first month's GST return: set it up, buy stock,
sell it, collect the money, take a return, and check that the stock, the books
and the tax all agree.

**Version 2 (2026-09-26)** is written for the **version 2 screens**: the top
menu bar (Home, Sell, Buy, Stock, Accounts, Masters, Reports, Admin and the
gear for Settings), documents entered on one screen and priced as they are
typed, and customers, vendors and products opened as tabs. The firm, the
figures and every expected total are the same as version 1, so a result can
be compared across the two. Version 1, for the left-hand menu and dialogs, is
kept as `QA_FUNCTIONAL_WALKTHROUGH_V1.md`.

**Where to run it.** Version 2 is not in an installer yet. On the test laptop
start the backend (`schtasks /run /tn agency-backend-8000`) and open
`desktop\build\windows\x64\runner\Debug\agency_desktop.exe`, the version 2
build. Sections 1 to 9 do not depend on how it was installed; section 10's
upgrade step waits for the version 2 installer.

Every expected result was taken from the product's own test cases
(`INDEPENDENT_TEST_CASES.md`), which were driven against a running server,
and re-worked for the figures used here. Update the Expected column when the
product changes, and the Result and Notes columns as you test.

## How to use this

**The figures are chosen to be easy to check by hand.** One product, bought
at 100 and sold at 150, GST at 18% within the state. Every total below
follows from those three numbers, so when a screen disagrees you can see by
how much.

**Do the sections in order.** Each step builds on the one before: the sale
needs the stock the purchase brought in. If a step fails, note it and carry
on where you can; mark later steps `Blocked` when they cannot run.

**How the version 2 screens work** -- read once before starting:

- **Menus.** A path such as *Buy → Purchase Orders* means: click **Buy** in
  the top bar, then **Purchase Orders** in the panel that drops down. Alt plus
  the underlined letter opens a menu from the keyboard. **Ctrl+K** (or the
  *Search or jump to* box) finds any screen or record by name.
- **Every screen opens as a tab** under the menu bar, and a customer, vendor,
  product or document you open gets a tab of its own, named after it. Several
  can be open at once; closing one returns to the others.
- **Lists.** Filters are the chips beside the title (*All*, *Draft*,
  *Approved* ...), search is the box below, and the buttons for the selected
  row sit on the same line; rarely used ones are under **…**. **+ New** is
  always last. The status bar at the bottom shows the record count and the
  pages (*1–20 of 36*). Keys: **Ctrl+N** new, **F2** edit the selected row,
  **/** search, **Delete** delete.
- **Documents** (quotation, order, invoice, receipt and so on) are one screen:
  the header across the top, the lines as a table, terms and totals at the
  bottom with the amount in words, and a **side panel** on the right for the
  line you are on. Most documents are **priced by the server as you type**, so
  the tax and total you see before saving are the ones that will be stored.
  **Ctrl+S** saves; **Ctrl+Enter** adds a line where lines are typed.
- **Screens read once when opened.** After acting in one screen, refresh the
  next (the circular-arrow button) before judging it.

**A refusal is often the product working.** Several steps ask you to try
something that must be refused. The Expected column says so; the refusal's
wording is part of the result.

**On every failure, capture three things**: a screenshot, the newest file in
the backend's `logs\server` folder, and the version on the sign-in screen.

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

Sign in as `platform-admin@agency.local`.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W1 | Admin → **Firms** → **+ New**. Type only the name `QA Traders` and save | Refused: code, country, currency and financial year start are also required | Not run | |
| W2 | Fill code `qa01` in lower case, country `IN`, currency `INR`, financial year start `2026-04-01`, GST number `33ABCDE1234F1Z5`, deployment mode **SHARED**. Save | Saves. The code is stored as **QA01**. The first firm on a fresh install takes noticeably longer to save than later ones, because it builds the shared firm store; wait for it | Not run | |
| W3 | Select QA01 → **Set up** (on the list's button line, or under **…**) | Titled *Set up QA01*, verdict **Cannot post documents yet**. Seven rows: Storage done; Business profile, Books, Tax, Geography, Branches and warehouses, People each open, with a button or a hint | Not run | |
| W4 | Business profile row: choose **Wholesale** → **Assign** | *Business profile set to Wholesale.* Row reads *Assigned: WHOLESALE* | Not run | |
| W5 | Books row → **Open the books** | Notice names the year starting 2026-04-01. Row reads 24 accounts, 1 financial year, 12 periods, all 24 control accounts mapped. Verdict becomes **Can post documents** | Not run | |
| W6 | Press **Open the books** again if still offered, else skip | Nothing is created a second time | Not run | |
| W7 | Tax row → **Apply GST template** | *GST set up: 8 tax profiles and 9 rules.* Geography turns done as well, with 1 country | Not run | |
| W8 | Branches and warehouses → **Create head office and main warehouse** | *Created branch HO and warehouse MAIN.* Row reads 1 branch, 1 warehouse | Not run | |
| W9 | Admin → **Users** → **+ New**: your name, an email such as `admin@qa01.test`, a password, **Job template** *Firm Administrator*, firm QA01. Save | Created. People on the Set up panel now counts 1 member | Not run | |
| W10 | **Set up** again | **Finished. Every step is done.** No buttons left | Not run | |
| W11 | Sign out. Sign in as the firm administrator | The app opens in QA01 on **Home**. The top bar offers Sell, Buy, Stock, Accounts, Masters, Reports and Admin; the firm switcher at the right reads QA Traders | Not run | |

From here on, work as the **firm administrator** unless a step says otherwise.

## 2. Masters

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W12 | Masters → **Warehouses** → **+ New**. In its **Branch** field choose `HO`. Code `STORE2`, name *Back Store*. Save | Listed beside MAIN | Not run | |
| W13 | Masters → (under *Configuration*) **Product Categories** → **+ New**: code `SOAP`, name *Soap*. Save. Then Masters → **Products** → **+ New** | The product opens as a **tab** titled *New product*: every section on one page (General, UOM & size, Pricing, Tax ...) with links along the top, and a side panel of prices on the right | Not run | |
| W13a | Fill code `QA-P1`, name *Test Soap*, Product type **Stock item**, category **Soap**, base, inventory, purchase and sales unit **PIECE**, tax profile **GST 18 local**, HSN `3401`, purchase price **100**, selling price **150**, MRP 160 | While typing, the side panel's **Margin** reads **50.00 · 33.3%**. Type a selling price of 170 for a moment: the panel warns it is above MRP. Put 150 back | Not run | |
| W13b | **Save product**, then reopen it (select → **F2**) | The tab is titled **Test Soap**, not its code. Each unit, the tax profile and the category read as names, not codes or ids | Not run | |
| W14 | Masters → **Vendors** → **+ New**: code `QA-V1`, name *QA Supplies*, a phone, one address, and under *Banking* one account (any bank, IFSC). **Save vendor** | Saved and listed. Reopen: the tab reads **QA Supplies**; the side panel shows the account under *Pay to* | Not run | |
| W15 | Edit QA-V1, change **only** the phone. Save and reopen | The phone changed; the address, bank account and everything else are still there | Not run | |
| W16 | Masters → **Customers** → **+ New**: code `QA-C1`, name *QA Retail*, type Business, currency INR, no GST number, no credit limit, one billing address in Tamil Nadu. **Save customer** | Saved and listed with outstanding 0.00 | Not run | |
| W17 | Edit QA-C1 (**F2**), change **only** the phone. Save and reopen | The tab reads **QA Retail**. The phone changed; the address, payment terms and everything else unchanged. Side panel: outstanding 0.00 | Not run | |
| W18 | Press **Ctrl+K** and type `Test Soap` | The product is found; choosing it opens the Products screen on it | Not run | |

## 3. Buying

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W19 | Buy → **Purchase Orders** → **+ New**: vendor QA-V1; **Branch · receives into** HO and MAIN; the first line QA-P1 (it starts at the purchase price, **100**), quantity **10** | Before saving, the totals bar reads Taxable **1,000.00**, CGST **90.00**, SGST **90.00**, Total **1,180.00**, and the *Tax* box reads *CGST + SGST*. The side panel shows the line's rate, its tax split and stock | Not run | |
| W19a | **Save draft** | Saved as **Draft**, a number starting `PO-` | Not run | |
| W20 | Open the draft again (select → **F2**) and look at the buttons on its top line | **Approve is not offered**, only **Send for approval**: an order cannot be approved before it is submitted | Not run | |
| W21 | **Send for approval**, then **Approve** | Two notices, submitted and approved. Status **Approved** | Not run | |
| W22 | Buy → **Goods Receipts** → **+ New** → choose the order. The line shows Ordered 10, Due 10; type Accepted **4**; the side panel's warehouse is MAIN. **Save receipt**, then on the list select it → **Complete** | Saved as a draft first. After Complete: **Completed**, and the order reads **Partially received** | Not run | |
| W23 | Stock → **Inventory**, search QA-P1 | MAIN holds **4** | Not run | |
| W24 | Buy → Goods Receipts → **+ New** against the same order | Accepted starts at the remaining **6** (Received before 4, Due 6). Save and Complete: the order reads **Received**, MAIN holds **10** | Not run | |
| W25 | Buy → **Purchase Invoices** → **+ New** → choose the receipt of **6**. Type **Supplier's invoice number** `QA-V1-INV-001`; supplier's invoice date today | Before saving, the bill is priced: **708.00** (600.00 plus 18% GST); the rate box shows the receipt price 100 as its hint. **Save bill**, then on the list **Approve**: approved at **708.00** | Not run | |
| W25a | Start another bill for the receipt of 4 and type `QA-V1-INV-001` again as the supplier's number | While typing, a warning says a purchase invoice with this supplier invoice number already exists. **Cancel** without saving | Not run | |
| W26 | Goods Receipts → the receipt of 6 → **Cancel** | Refused: it has been invoiced, and the message says to cancel the purchase invoice first or raise a return | Not run | |
| W27 | Purchase Invoices → **+ New** → the receipt of **4**, supplier's number `QA-V1-INV-002`. Save and Approve | Approved. Total **472.00** | Not run | |
| W28 | Buy → **Payments** → **+ New**: paid to QA-V1, amount **1,180.00**, method Bank, oldest first → Record | A notice that `PY-…` was recorded and posted. Start another payment for QA-V1: no bills left to pay | Not run | |
| W29 | Accounts → **Journal Entries**, search `PY-` → view it | The payment debits Accounts Payable and credits Bank, 1,180.00 each | Not run | |

## 4. Stock

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W30 | Stock → **Stock Ledger**, search QA-P1 | Two `GOODS_RECEIPT` rows, +4 and +6, each naming its receipt, the balance ending at **10** | Not run | |
| W31 | Stock → **Stock Summary** | QA-P1 **10**, agreeing with the Inventory screen | Not run | |
| W32 | Stock → **Inventory**, select the MAIN row for QA-P1 → **Transfer** 2 to STORE2. **Reference** is optional; leave it blank | MAIN **8**, STORE2 **2**, total still 10. Blank reference: numbered from its own series (`ST-…`) | Not run | |
| W33 | Accounts → Journal Entries, newest first | **No** entry for the transfer: moving stock between warehouses posts nothing to the books | Not run | |
| W34 | Transfer the 2 back from STORE2 to MAIN, reference left blank again | MAIN **10**, STORE2 0. A second `ST-…` number, not the first reused | Not run | |

## 5. Selling

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W35 | Sell → **Quotations** → **+ New**: customer QA-C1 (type part of the code or name). First line QA-P1, quantity **4** | The rate fills in at **150**. Before saving: Taxable **600.00**, CGST **54.00**, SGST **54.00**, Total **708.00**, and *Seven hundred eight only* in words. The side panel shows the rate's source, the tax split and stock | Not run | |
| W35a | **Save draft** | A number starting `QT-`, status draft | Not run | |
| W36 | On the list: **Mark as sent** → **Customer accepted** (give a reason) → **Convert to order** (look under **…** if a button is not on the line) | Three notices; the last says the quotation became `SO-…` and that approving the order reserves the stock | Not run | |
| W37 | Look at the quotation's buttons again | **Convert to order** is gone: a quotation converts once | Not run | |
| W38 | Sell → **Sales Orders** → the new order → **Approve** | **Approved**. No credit warning, since QA-C1 has no limit | Not run | |
| W39 | Stock → **Inventory**, QA-P1 | MAIN: current **10**, reserved **4**, available **6** | Not run | |
| W40 | Sales Orders → the order → **Hold**, reason *awaiting cheque* | Status reads *Approved (on hold)* | Not run | |
| W41 | Sell → **Delivery Notes** → **+ New** → choose the order → **Save delivery note** | Refused: the order is on hold, naming the reason. Reserved stays 4 | Not run | |
| W42 | Sales Orders → the order → **Release** | Status back to plain **Approved** | Not run | |
| W43 | Delivery Notes → **+ New** → the order. The line shows Reserved 4 and Delivering **4**; the side panel shows warehouse MAIN and the stock it is expected to ship from. Save → on the list **Approve** → **Dispatch** | Created as a draft. After Dispatch: **Dispatched**, the order **Delivered** | Not run | |
| W44 | Stock → **Inventory**, QA-P1 | MAIN current **6**, reserved **0** | Not run | |
| W45 | Stock Ledger, QA-P1 | A `DISPATCH` row of **−4** naming the delivery note | Not run | |
| W46 | Sell → **Sales Invoices** → **+ New**. In **Bill this delivery note** choose the note. Type **5** in the quantity to bill | The line shows red and the bill cannot be saved: only 4 left to bill | Not run | |
| W47 | Set it to **4**. Before saving, read the totals | Taxable **600.00**, CGST **54.00**, SGST **54.00**, total **708.00**, in words. The *Place of supply* box reads CGST + SGST | Not run | |
| W47a | Press **Save & print** (or Ctrl+P) | The bill is saved and the Windows print dialog opens on it. **Every copy's banner reads *DRAFT - NOT A TAX INVOICE - NOT YET APPROVED***: it has not been approved yet. Cancel the print | Not run | |
| W47b | On the list, select the invoice → **Approve** | **Approved** | Not run | |
| W48 | Accounts → Journal Entries → the invoice's `SI-…` entry | Debit Trade Receivables **708.00**; credit Sales **600.00** and Output Tax **108.00**. The first line says it was posted by sales_invoice | Not run | |
| W49 | Journal Entries → the delivery note's `DN-…` entry | The cost of the goods sold, **400.00** (4 × 100), debited to cost of goods and credited to inventory | Not run | |
| W50 | Masters → Customers → QA-C1 (**F2**) | Side panel: outstanding **708.00** | Not run | |
| W51 | Sell → Sales Invoices → the invoice → **Print** | A PDF with **TAX INVOICE** and no draft line (it is approved now), the CGST/SGST split, an HSN column and summary, and the amount in words | Not run | |
| W51a | Sales Invoices → **…** → **Print settings** → Paper **Thermal roll (80 mm)** → Save. Print the invoice again. Then set Paper back to **A4** | The bill comes out as one narrow 80 mm column, only as long as the bill: firm and GSTIN, number and date, customer, the line, CGST 9% and SGST 9%, total **708.00** and in words | Not run | |

## 6. Money and GST

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W52 | Sell → **Receipts** → **+ New**: QA-C1, amount **708.00**, Bank; under *Apply to invoices* put 708.00 against the invoice → Record | *RC-… recorded and posted to the ledger.* No TCS is charged: it is off for a new firm | Not run | |
| W53 | Masters → Customers → QA-C1 | Outstanding **0.00** | Not run | |
| W54 | Start another receipt for QA-C1 | The invoice is no longer in the list to apply against | Not run | |
| W55 | Accounts → **GST Returns** → this month → **GSTR-1** | *Filing as 33ABCDE1234F1Z5.* **B2CS**: one row, place **33**, 18%, taxable **600.00**, CGST **54.00**, SGST **54.00**. B2B empty, since QA-C1 has no GST number. HSN summary: quantity 4, taxable 600.00, under 3401 | Not run | |
| W56 | Same month → **GSTR-3B** | 3.1(a) taxable **600.00**, CGST 54.00, SGST 54.00: equal to GSTR-1 | Not run | |
| W57 | Accounts → **E-Invoice** | The screen says plainly that it is a sandbox rehearsal, never *LIVE* | Not run | |

## 7. A return and a credit

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W58 | Sell → **Sales Returns** → **+ New** → *Returned against* the invoice. **Taken back into** MAIN. Every line of the invoice is listed, each starting at 0. Type Returning **5** on line 1 → **Save draft** | The figure shows red, and saving is refused: only 4 went out | Not run | |
| W59 | Returning **1**. Before saving read the totals: then **Save draft**, and on the list **Approve** → **Complete** | Before saving: *To shelf* 1, and **Credit to customer 177.00** (150 plus 18%). After Complete: a notice of 1 back on the shelf and 177.00 credited | Not run | |
| W60 | Stock → **Inventory**, QA-P1 | MAIN **7**. The Stock Ledger shows a `SALES_RETURN` of +1 | Not run | |
| W61 | Masters → Customers → QA-C1 | **177.00** in the customer's favour, shown as an advance or a credit balance. Note which | Not run | |
| W62 | Sell → **Credit Notes** → **+ New**: the invoice; reason *Rate difference*; on line 1 type **50** in *Credit* | Before raising: GST 18%, tax back **9.00**, total **59.00**, *Credit to customer 59.00*. **Raise credit note**, then on the list **Approve**: the row reads **59.00 (tax 9.00)** | Not run | |
| W63 | **+ New** again on the same line and type **1,000** in *Credit* | Refused while typing -- a banner says a credit note cannot credit more than the line was charged, naming what it was charged and what is already credited. **Cancel** | Not run | |

## 8. The books agree

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W64 | Accounts → **Trial Balance**. It opens on this month's period | A **Balanced** chip. Trade Receivables, Sales, Output Tax, Bank, Accounts Payable and Inventory are among the rows | Not run | |
| W65 | Accounts → **Profit & Loss**, same period | Income and Expenses with a net profit row. Sales less the return and the credit note, less the cost of goods, is the gross result | Not run | |
| W66 | Accounts → **Balance Sheet**, same period | A **Balanced** chip. Total assets equal liabilities and equity. Its *Result for the year* equals the P&L's year-to-date net | Not run | |
| W67 | Inventory value | The stock of 7 is carried at cost, 700.00: the Inventory account on the trial balance agrees | Not run | |
| W68 | Reports → **Operational**, then **Financial**: open every entry | Each opens with a row count, or says *Nothing to report* when empty. Never a blank grid or an error | Not run | |
| W69 | Admin → **Audit Logs** | The firm's history: the product, the documents and the approvals from today, each naming you | Not run | |

## 9. Who can see what

Sign in as the firm administrator for W70 and W72.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W70 | Admin → Users → **+ New**: `counter@qa01.test`, a password, **Job template** *Counter Sales*. Save | Created in QA01 | Not run | |
| W71 | Sign in as `counter@qa01.test`. Change the password when asked. Open each menu in the top bar | Sell and Stock offered. The only money screens are **Receipts** (Sell → Money) and **Payments** (Buy → Money). No ledger screens anywhere: no Chart of Accounts, Journal Entries, Trial Balance. No Admin | Not run | |
| W72 | As the firm administrator, create `field@qa01.test` with *Field Sales* | Created | Not run | |
| W73 | Sign in as `field@qa01.test` | No Admin. Under Sell no Commission, Credit Notes, Price Lists or Promotions; no GST Returns or TCS anywhere | Not run | |
| W74 | As `field@qa01.test`, Masters → Customers → **…** → **Settings** | The credit policy opens read-only, saying that changing it needs the manage customer settings permission | Not run | |

## 10. The data survives

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W75 | Restart the PC. Wait a minute, start the backend if it does not start by itself, and open the version 2 app | Sign-in appears. Everything from sections 1 to 9 is still there | Not run | |
| W76 | Run the version 2 Setup.exe again (an upgrade to the same version) | **Waits for the version 2 installer** -- mark `Blocked` until it exists. When it does: a backup is taken first, and afterwards every record is still there | Not run | |

## 11. The version 2 screens themselves

Checks of the new frame, apart from the business steps above. Any firm will do;
WHOLE01 (`whole01.admin@agency.local`) has two years of data and makes the
paging checks meaningful.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| V1 | Open Sell → Sales Orders, then a customer from Masters, then a product | Three tabs under the menu bar, the records named by their names. Type something in the product, switch to another tab and back: it is still there | Not run | |
| V2 | Close the product tab with unsaved changes | Asked before the changes are thrown away | Not run | |
| V3 | **Alt+S** | The Sell menu opens; arrow keys move through it and Enter opens a screen | Not run | |
| V4 | **Ctrl+K**, type `sales order` | The Sales Orders screen is offered; Enter opens it | Not run | |
| V5 | On any list: **Ctrl+N**, then Esc; select a row and **F2**; press **/** | New opens; F2 opens the selected row; / puts the cursor in the search box | Not run | |
| V6 | Paging: Sell → Sales Orders in WHOLE01 | The status bar reads the count and the page, e.g. *1–50 of 72*. The next-page arrow shows the rest; the count does not change | Not run | |
| V7 | Paging on a filtered list: choose the *Approved* chip, then page | The pages cover only approved orders; the count matches the chip | Not run | |
| V8 | Home | Today's figures and to-dos. Click a to-do: the list it opens holds the same number of rows the to-do said | Not run | |
| V9 | Resize the window down to 1366 × 768 and open a document, a record and a report | Nothing is cut off; the side panel hides on a narrow window and the table keeps its columns | Not run | |
| V10 | A document's side panel: on a sales order, click each line in turn | The panel follows the line: its rate and where it came from, the last price to this customer, tax split, stock | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| App version (sign-in screen) | |
| Steps passed / failed / blocked | |
| Server log files sent | |
| Worst problem found | |
