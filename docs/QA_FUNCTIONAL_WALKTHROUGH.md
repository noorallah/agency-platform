# QA functional walkthrough, version 2: one firm, end to end

**Brought up to date 2026-10-04 for release 1.3.0.** This is the **first end-to-end
test pass of 1.3.0**, and 1.3.0 includes everything in 1.2.0 (no 1.2.0 installer
was ever built), so the whole firm below, from the first sign-in to the GST
return, is being driven by hand for the first time on this build. Every menu
path in this book is the **1.3.0 path**: the light menu (since 2026-10-09 each
drop-down shows every screen of its area, the daily ones first) and the gear's
**Settings page** (Settings, Set up, Platform). The Admin area is gone from the
bar. Where a path could not be confirmed it is marked *(confirm)*.

For the QA person testing the Agency Platform with data they create
themselves, by hand, the way a customer would. It follows one small trading
firm from creation to its first month's GST return: set it up, buy stock,
sell it, collect the money, take a return, and check that the stock, the books
and the tax all agree.

**Version 2 (2026-09-26)** is written for the **version 2 screens**: the top
menu bar (Home, Sell, Buy, Stock, Accounts, Masters, Reports and the
gear for Settings; the Admin area moved under the gear in 1.2.0), documents entered on one screen and priced as they are
typed, and customers, vendors and products opened as tabs. The firm, the
figures and every expected total are the same as version 1, so a result can
be compared across the two. Version 1, for the left-hand menu and dialogs, is
kept as `QA_FUNCTIONAL_WALKTHROUGH_V1.md`.

**Updated 2026-09-27 for release 1.0.2**, the first installer with these
screens: the list screens now keep everything on one line and show a bar for
the picked row (below), and section 15 checks what is new in 1.0.2. The
figures and expected totals of sections 1 to 14 are unchanged.

**Updated 2026-10-03 for the features built in backlog Waves 1 to 3**: section
16 walks the important new flows on the same firm. Its steps are written from
the code and have not yet been driven; sections 1 to 15 are unchanged. The
detailed cases for each feature are in `INDEPENDENT_TEST_CASES.md` and `qa/`.

**Where to run it.** Install or upgrade with `AgencyPlatform-1.3.0-Setup.exe`
(the *Installer QA checklist*, sections A, B, E and F), then open *Agency
Platform* from the Start menu. Sections 1 to 9 do not depend on how it was
installed.

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
  the top bar, then **Purchase Orders** in the panel that drops down. Each
  drop-down shows every screen of its area in group columns, the daily ones
  first in heavier type, so *Buy → Money → Landed Costs* means: open Buy, then
  find Landed Costs in the Money column. Returns, credit notes and debit notes
  are ordinary items in the Documents column. **Settings** is the gear at the right of the bar: *Settings → Selling →
  Credit Control* means: click the gear, then the **Selling** group, then the
  **Credit Control** card. Alt plus the underlined letter opens a menu from
  the keyboard. **Ctrl+K** (or the *Search or jump to* box) finds any screen
  or record by name; use it whenever a path here does not match what you see.
- **Every screen opens as a tab** under the menu bar, and a customer, vendor,
  product or document you open gets a tab of its own, named after it. Several
  can be open at once; closing one returns to the others.
- **Lists keep everything on one line** above the grid: the title, its
  **(i)** (what the screen is for), counters that filter when clicked
  (*Draft 3*, *Approved 5* ...), **+ filter** for the rarer filters, the
  search box, the **Period** on dated lists (a named period, the Indian
  financial year, or a custom range; ◀ ▶ step it), **Columns** (choose the
  columns; remembered on this PC), Refresh, anything rarely used under **…**,
  and **+ New** last. The status bar at the bottom shows the record count and
  the pages (*1–20 of 36*).
- **Pick a row and a bar appears above the grid**, naming it (number,
  customer or supplier, status, total) with the steps that can run now at the
  right: *Open*, *Edit*, *Approve*, *Post*, *Cancel*, *Print* ... A step that
  cannot run is not offered; the **×** clears the pick. Nothing is picked when
  a list opens. **Double-click** a row to open it. Keys: **Ctrl+N** new,
  **F2** edit the picked row, **/** search, **Delete** delete.
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

## 0. First sign-in: Set up your agency (new in 1.3.0)

Sign in as `platform-admin@agency.local`. On a server whose agency branding has
not been given, a dialog **Set up your agency** opens over Home: Agency name,
Tagline, Logo, a live preview, **Skip for now** and **Save**. It is shown only
to a platform administrator, once per user.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W0 | In the dialog type the agency name `QA Agency`, leave the tagline and logo blank, press **Save**. (Or press **Skip for now** to carry on without a name) | *Saved.* The dialog closes. The name **QA Agency**, with its initials in place of a logo, leads the menu strip at the top of every screen. Sign out: the sign-in screen shows **QA Agency** above the form. With **Skip for now** instead: nothing is saved, Home shows a **Finish setting up** card with a **Set up your agency** button, the header and sign-in screen show Agency Platform's own name, and the dialog does not open again for this user | Not run | |
| W0a | Sign in again. Settings (gear) → **Platform** → **Agency** → **Branding** | One form with the saved name; it can be changed later (the branding cases are QA-BRD-01 to QA-BRD-24 in `QA_TEST_BOOK.md`) | Not run | |

## 1. The firm and its people

Still signed in as `platform-admin@agency.local`. The platform administrator
works from **Settings (gear) → Platform**.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W1 | Settings (gear) → **Platform** → **Firms** → **Firms** → **+ New**. Type only the name `QA Traders` and save | Refused: code, country, currency and financial year start are also required | Not run | |
| W2 | Fill code `qa01` in lower case, country `IN`, currency `INR`, financial year start `2026-04-01`, GST number `33ABCDE1234F1Z5`, deployment mode **SHARED**. Save | Saves. The code is stored as **QA01**. The first firm on a fresh install takes noticeably longer to save than later ones, because it builds the shared firm store; wait for it | Not run | |
| W3 | Select QA01 → **Set up** (on the list's button line, or under **…**) | Titled *Set up QA01*, verdict **Cannot post documents yet**. Seven rows: Storage done; Business profile, Books, Tax, Geography, Branches and warehouses, People each open, with a button or a hint | Not run | |
| W4 | Business profile row: choose **Wholesale** → **Assign** | *Business profile set to Wholesale.* Row reads *Assigned: WHOLESALE* | Not run | |
| W5 | Books row → **Open the books** | Notice names the year starting 2026-04-01. Row reads 24 accounts, 1 financial year, 12 periods, all 24 control accounts mapped. Verdict becomes **Can post documents** | Not run | |
| W6 | Press **Open the books** again if still offered, else skip | Nothing is created a second time | Not run | |
| W7 | Tax row → **Apply GST template** | *GST set up: 10 tax profiles and 13 rules.* Geography turns done as well, with 1 country | Not run | |
| W8 | Branches and warehouses → **Create head office and main warehouse** | *Created branch HO and warehouse MAIN.* Row reads 1 branch, 1 warehouse | Not run | |
| W9 | Settings (gear) → **Platform** → **People** → **Users** → **+ New**: your name, an email such as `admin@qa01.test`, a password, **Job template** *Firm Administrator*, firm QA01. Save | Created. People on the Set up panel now counts 1 member | Not run | |
| W10 | **Set up** again | **Finished. Every step is done.** No buttons left | Not run | |
| W11 | Sign out. Sign in as the firm administrator | The app opens in QA01 on **Home**. The top bar offers Sell, Buy, Stock, Accounts, Masters and Reports (no Admin: it is not a menu any more); the agency's name and the firm, QA Traders, show at the left of the strip | Not run | |

From here on, work as the **firm administrator** unless a step says otherwise.

## 2. Masters

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W12 | Masters → **Warehouses** → **+ New**. In its **Branch** field choose `HO`. Code `STORE2`, name *Back Store*. Save | Listed beside MAIN | Not run | |
| W13 | Settings (gear) → **Set up** → **Item lists** → **Product Categories** → **+ New**: code `SOAP`, name *Soap*. Save. Then Masters → **Products** → **+ New** | The product opens as a **tab** titled *New product*: every section on one page (General, UOM & size, Pricing, Tax ...) with links along the top, and a side panel of prices on the right | Not run | |
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
| W23 | Stock → Stock → **Inventory**, search QA-P1 | MAIN holds **4** | Not run | |
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
| W32 | Stock → Stock → **Inventory**, select the MAIN row for QA-P1 → **Transfer** 2 to STORE2. **Reference** is optional; leave it blank | MAIN **8**, STORE2 **2**, total still 10. Blank reference: numbered from its own series (`ST-…`) | Not run | |
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
| W39 | Stock → Stock → **Inventory**, QA-P1 | MAIN: current **10**, reserved **4**, available **6** | Not run | |
| W40 | Sales Orders → the order → **Hold**, reason *awaiting cheque* | Status reads *Approved (on hold)* | Not run | |
| W41 | Sell → **Delivery Notes** → **+ New** → choose the order → **Save delivery note** | Refused: the order is on hold, naming the reason. Reserved stays 4 | Not run | |
| W42 | Sales Orders → the order → **Release** | Status back to plain **Approved** | Not run | |
| W43 | Delivery Notes → **+ New** → the order. The line shows Reserved 4 and Delivering **4**; the side panel shows warehouse MAIN and the stock it is expected to ship from. Save → on the list **Approve** → **Dispatch** | Created as a draft, reason **Sale**. Dispatch finds no approved invoice and asks (the firm's policy defaults to **Warn**): choose **Dispatch anyway**. Then **Dispatched**, the order **Delivered** | Not run | |
| W44 | Stock → Stock → **Inventory**, QA-P1 | MAIN current **6**, reserved **0** | Not run | |
| W45 | Stock Ledger, QA-P1 | A `DISPATCH` row of **−4** naming the delivery note | Not run | |
| W46 | Sell → **Sales Invoices** → **+ New** (bill from delivery notes). Pick the customer QA-C1 first, then tick its dispatched delivery note in the list. Type **5** in the quantity to bill | The line shows red and the bill cannot be saved: only 4 left to bill | Not run | |
| W47 | Set it to **4**. Before saving, read the totals | Taxable **600.00**, CGST **54.00**, SGST **54.00**, total **708.00**, in words. The *Place of supply* box reads CGST + SGST | Not run | |
| W47a | Press **Save & print** (or Ctrl+P) | The bill is saved and the Windows print dialog opens on it. **Every copy's banner reads *DRAFT - NOT A TAX INVOICE - NOT YET APPROVED***: it has not been approved yet. Cancel the print | Not run | |
| W47b | On the list, select the invoice → **Approve** | **Approved** | Not run | |
| W48 | Accounts → Journal Entries → the invoice's `SI-…` entry | Debit Trade Receivables **708.00**; credit Sales **600.00** and Output Tax **108.00** *(confirm: 1.3.0 may show the tax as separate Output CGST 54.00 and Output SGST 54.00 legs rather than one Output Tax line)*. The first line says it was posted by sales_invoice | Not run | |
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
| W57 | Accounts → Tax filing → **E-Invoice** | The screen says plainly that it is a sandbox rehearsal, never *LIVE* | Not run | |

## 7. A return and a credit

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W58 | Sell → **Sales Returns** → **+ New** → *Returned against* the invoice. **Taken back into** MAIN. Every line of the invoice is listed, each starting at 0. Type Returning **5** on line 1 → **Save draft** | The figure shows red, and saving is refused: only 4 went out | Not run | |
| W59 | Returning **1**. Before saving read the totals: then **Save draft**, and on the list **Approve** → **Complete** | Before saving: *To shelf* 1, and **Credit to customer 177.00** (150 plus 18%). After Complete: a notice of 1 back on the shelf and 177.00 credited | Not run | |
| W60 | Stock → Stock → **Inventory**, QA-P1 | MAIN **7**. The Stock Ledger shows a `SALES_RETURN` of +1 | Not run | |
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
| W69 | Settings (gear) → **Platform** → **System** → **Audit Logs** *(confirm: offered to the firm administrator as well as the platform administrator)* | The firm's history: the product, the documents and the approvals from today, each naming you | Not run | |

## 9. Who can see what

Sign in as the firm administrator for W70 and W72.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W70 | Settings (gear) → Platform → People → Users → **+ New**: `counter@qa01.test`, a password, **Job template** *Counter Sales*. Save | Created in QA01 | Not run | |
| W71 | Sign in as `counter@qa01.test`. Change the password when asked. Open each menu in the top bar | Sell and Stock offered. The only money screens are **Receipts** (Sell) and **Payments** (Buy). No ledger screens anywhere: no Chart of Accounts, Journal Entries, Trial Balance. The gear offers no *Platform* part | Not run | |
| W72 | As the firm administrator, create `field@qa01.test` with *Field Sales* | Created | Not run | |
| W73 | Sign in as `field@qa01.test` | The gear offers no *Platform* part. Under Sell no Incentives (Commission, Targets); under Sell → Documents no Credit Notes; no Settings → Set up → Pricing (Price Lists, Promotions); no GST Returns or TCS anywhere | Not run | |
| W74 | As `field@qa01.test`, Settings (gear) → **Selling** → **Credit Control** (or Masters → Customers → **…** → **Settings**) | The credit policy opens read-only, saying that changing it needs the manage customer settings permission | Not run | |

## 10. The data survives

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| W75 | Restart the PC. Wait a minute, start the backend if it does not start by itself, and open the app | Sign-in appears. Everything from sections 1 to 9 is still there | Not run | |
| W76 | Run `AgencyPlatform-1.3.0-Setup.exe` again (an upgrade to the same version) | A *Backing up the database* step first; afterwards every record from sections 0 to 9 is still there, the agency's name from W0 still shows, and the old sign-in works | Not run | |

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

## 12. Tax by customer: where they are, and whether they are registered

GST follows the **buyer's state**: the state in their GSTIN if they have one,
else the state of their billing address. The same state as the firm (Tamil
Nadu, 33) is charged **CGST + SGST**; another state, **IGST**. Whether the
customer is a business or an individual does **not** change the rate; a
GSTIN decides whether the sale is **B2B** (registered) or **B2C** on GSTR-1.
Every figure below is QA-P1 at 150 with 18% GST.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| G1 | Masters → Customers → **+ New**, three customers (type, GSTIN, billing address): `QA-C3` *QA Karnataka Traders* -- Business, GSTIN `29ABCDE9999F1Z5`, address in Karnataka. `QA-C4` *QA Bengaluru Walk-in* -- **Individual**, no GSTIN, address in Karnataka. `QA-C5` *QA Chennai Wholesale* -- Business, GSTIN `33PQRSX5678K1Z2`, PAN `PQRSX5678K`, address in Tamil Nadu | All three saved. The side panel of each shows its GSTIN or *unregistered* | Not run | |
| G2 | Sell → Quotations → **+ New** for **QA-C5**, QA-P1 quantity **2**. Read, then **Cancel** | *Place of supply* reads Tamil Nadu · **CGST + SGST**. Taxable 300.00, CGST **27.00**, SGST **27.00**, total **354.00** | Not run | |
| G3 | The same for **QA-C3** | Karnataka · **IGST**. Taxable 300.00, IGST **54.00**, total **354.00** -- the same total, split differently | Not run | |
| G4 | The same for **QA-C4** (no GSTIN, an individual) | Karnataka · **IGST**, 54.00: with no GSTIN the billing address decides, and being an individual changes nothing | Not run | |
| G5 | Edit QA-C3: change only its billing address to Tamil Nadu. Quote it again | Still **IGST**: a GSTIN's state outranks the address. Put the address back to Karnataka | Not run | |
| G6 | Bill one piece to each of QA-C3, QA-C4 and QA-C5, the way section 5 did (order → approve → delivery note → dispatch → invoice of 1 → approve) | Each invoice is taxable **150.00**, total **177.00**: QA-C3 and QA-C4 IGST 27.00; QA-C5 CGST 13.50 + SGST 13.50 | Not run | |
| G7 | Accounts → **GST Returns** → this month → **GSTR-1** | **B2B** now lists QA-C3's invoice (IGST 27.00, place 29) and QA-C5's (CGST 13.50, SGST 13.50). **B2CS** gains a row for place **29** at 18%, taxable 150.00, IGST 27.00 (QA-C4). QA-C1's sales stay in the place-33 row | Not run | |
| G8 | Accounts → Tax filing → **E-Invoice**: raise the e-invoice for QA-C4's bill, then for QA-C3's | QA-C4's is **refused** before anything is sent: an e-invoice needs the buyer's GSTIN. QA-C3's gets a sandbox reference, marked *sandbox* | Not run | |
| G9 | Settings (gear) → **Selling** → **TCS Settings** (also Accounts → Tax filing → **TCS** → **Settings**): *Collect under section 206C(1H)* on, preceding-year turnover **150000000**, threshold **0**, rate **0.1**, without a PAN **1.0**. Save | The banner reads the threshold 0 and *0.1% (1.0% without a PAN)* | Not run | |
| G10 | Sell → Receipts → **+ New**: **QA-C5** (has a PAN) pays **177.00** against its invoice. Then **QA-C4** (no PAN) pays **177.00** | Accounts → Tax filing → TCS lists both: QA-C5 at **0.1%**, TCS **0.18**; QA-C4 at **1.0% (no PAN)**, TCS **1.77**. Each has its own `TCS-RC-…` journal to 2500 TCS Payable | Not run | |
| G11 | Settings → Selling → TCS Settings: turn collection **off** again | Later receipts carry no TCS | Not run | |

## 13. Units: buying in boxes, stocking in pieces

QA-P1 is kept in **PIECE**. A box holds 12.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| U1 | Settings (gear) → **Set up** → **Item lists** → **Conversion Rules** → **+ New**: Product **QA-P1**, From **BOX**, To **PIECE**, Factor **12**. Save | Listed: QA-P1, BOX → PIECE, 12 | Not run | |
| U2 | Note MAIN's QA-P1 figure on Stock → Stock → **Inventory**. Then Buy → Purchase Orders → **+ New**: QA-V1, QA-P1, **Unit BOX**, quantity **2**, rate **1,200** (a box) | Before saving: taxable **2,400.00**, CGST **216.00**, SGST **216.00**, total **2,832.00**. Save, Send for approval, Approve | Not run | |
| U3 | Buy → Goods Receipts → **+ New** against it: Ordered 2, accept **2**. Save and Complete | Stock → Stock → Inventory: MAIN is up by **24** pieces -- 2 boxes of 12 | Not run | |
| U4 | Add a **firm-wide** rule: Product *Firm-wide*, BOX → PIECE, Factor **10**. Order and receive **1 BOX** of QA-P1 again | MAIN is up by **12**, not 10: the product's own rule outranks the firm-wide one | Not run | |
| U5 | A purchase order for QA-P1 with **Unit KG**, quantity 1. Save | Refused, naming the product and both units: *QA-P1: no active conversion rule converts KG to PIECE …*, and saying where to add one | Not run | |
| U6 | Sell 30 pieces of QA-P1 on a sales order | Priced per piece: 30 × 150; nothing about boxes on the order | Not run | |

## 14. Pricing: standing rates, price lists, promotions and coupons

The **side panel** of a sales order says, for the line you are on, what
discount was taken and **where it came from**. The order of precedence: a
discount **typed** on the line beats a **promotion**, which beats the
**price list**, which beats the customer's **standing rate**. A typed **0**
refuses them all. Work on a new customer so the earlier sections are not
touched; read each order before saving, then **Cancel** unless a step says to
save.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| P1 | Masters → Customers → **+ New**: `QA-C6` *QA Pricing Mart*, Business, no GSTIN, address in Tamil Nadu; under **Money**, *Default discount %* **5**. Save | Saved; the side panel reads its terms | Not run | |
| P2 | Sell → Sales Orders → **+ New**: QA-C6, QA-P1 quantity **10**, discount boxes left **blank** | Side panel: Discount **5%** *from the customer's standing rate*. Taxable **1,425.00**, CGST **128.25**, SGST **128.25**, total **1,681.50** | Not run | |
| P3 | Settings (gear) → **Set up** → **Pricing** → **Price Lists** → **New price list**: code `QA-STD`, name *Standard trade*, applies to **Everyone**, in force from today. **Add product** QA-P1 from qty **1** discount **3**; again QA-P1 from qty **20** discount **6**. Save | Listed, applies to Everyone, 2 rates | Not run | |
| P4 | Sales order for QA-C6, QA-P1 quantity **10** | **3%** *from the price list* -- the list beats the 5% standing rate even though it is lower. Taxable **1,455.00**, CGST 130.95, SGST 130.95, total **1,716.90** | Not run | |
| P5 | Change the quantity to **20** | **6%** from the price list: the highest break at or below the quantity. Taxable **2,820.00**, tax 507.60, total **3,327.60** | Not run | |
| P6 | New price list `QA-C6-OWN`, applies to **One customer** QA-C6: QA-P1 from qty 1 discount **10**. Save. Order for QA-C6, quantity **10** | **10%** from the price list: the customer's own list **replaces** the firm-wide one. Taxable **1,350.00**, tax 243.00, total **1,593.00** | Not run | |
| P7 | Settings → Set up → Pricing → **Promotions** → **+ New**: code `QA-BULK`, name *Five percent on 25 or more*, Applies at **10**, *Other promotions may still apply* ticked. **Add condition**: *Quantity on the line* *is at least* **25**. **Add benefit**: *Percent off each line*, **5**. Status Active. Save | Listed; its description reads "Quantity on the line is at least 25" | Not run | |
| P8 | Order for QA-C6, quantity **30** | **5%** *from a promotion*: it outranks the customer's 10% list. Gross 4,500.00, taxable **4,275.00**, tax 769.50, total **5,044.50** | Not run | |
| P9 | On the same line type **0** in *Disc %* | 0%, *typed on this order*: a typed zero refuses every arrangement. Taxable **4,500.00**, tax 810.00, total **5,310.00** | Not run | |
| P10 | Type **12** instead | 12% typed. Taxable **3,960.00**, tax 712.80, total **4,672.80** | Not run | |
| P11 | Promotions → **+ New**: code `QA-WELCOME`, name *Two percent with a coupon*, **Only with a coupon** on, benefit *Percent off each line* **2**. Save. Then the **Coupons** view → **+ New**: code `QAWELCOME`, offer QA-WELCOME, **Total claims allowed 1**. Save | Both listed; the coupon names its offer | Not run | |
| P12 | Order for QA-C6, quantity **10**, **Coupon** left blank | Still **10%** from the price list: a coupon-only offer reaches nobody without its code | Not run | |
| P13 | Type `QAWELCOME` in **Coupon** | **2%** *from a promotion* -- it replaces the 10%, it does not add to it. Taxable **1,470.00**, CGST 132.30, SGST 132.30, total **1,734.60** | Not run | |
| P14 | Type `NOSUCHCODE` instead | Nothing is refused; the line falls back to **10%** from the price list, 1,593.00 | Not run | |
| P15 | Put `QAWELCOME` back, **Save draft**, then on the list **Approve** the order | Approved. Reports → Operational → *Promotion claims* lists QA-WELCOME, coupon QAWELCOME, QA-C6, **CLAIMED** | Not run | |
| P16 | A new order for QA-C6, quantity 10, Coupon `QAWELCOME` | The coupon is used up (1 claim allowed): the line is priced at **10%** from the price list, 1,593.00, not 2% | Not run | |
| P17 | Order for QA-C6, quantity 10, *Disc %* **0** on the line; at the bottom *Discount on the whole order %* **10** | The 150.00 comes off the line before tax: taxable **1,350.00**, tax 243.00, total **1,593.00** | Not run | |
| P18 | Add a **Delivery charge** of **100** | The charge joins the taxable value and is taxed with it: taxable **1,450.00**, CGST 130.50, SGST 130.50, total **1,711.00** | Not run | |
| P19 | Set the promotions QA-BULK and QA-WELCOME, and both price lists, to **Inactive** when finished | Later orders for QA-C6 go back to its 5% standing rate | Not run | |

## 15. What is new in 1.0.2 (carried into 1.3.0)

Checks of the 1.0.2 changes, which 1.3.0 still carries, apart from the business steps above. Use QA01
from sections 1 to 9, or WHOLE01 (`whole01.admin@agency.local`) where a
longer history helps.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| N1 | Open any list, e.g. Sell → Sales Orders | One line above the grid: title, (i), counters, + filter, search, Period, Columns, Refresh, + New last. Nothing else above the grid; no row is picked | Not run | |
| N2 | Click a row once | A bar above the grid names it (number · customer · status · total) with its steps at the right. Click × on the bar: the pick clears | Not run | |
| N3 | On a draft sales order, compare the bar with an approved one | The draft offers Edit and Approve; the approved one offers what an approved order can do and **not** Approve | Not run | |
| N4 | Period: choose *This month*, then ◀ | The list narrows to this month, then to last month; *All dates* brings everything back | Not run | |
| N5 | Columns: add *Remarks*, remove *Status*, close the screen and open it again | The choice is kept | Not run | |
| N6 | Buy → Goods Receipts, Purchase Invoices, Purchase Returns | Each has a **Supplier** column; typing `QA Supplies` in the search finds that supplier's documents; the bar names the supplier | Not run | |
| N7 | Sell → Quotations and Sell → Sales Returns | Both are grids like Sales Orders (no list-and-pane); double-click opens the document in a window | Not run | |
| N8 | Sell → Receipts: search `QA Retail`, then pick the receipt from section 6 | Found by customer name. If it still has money on account, the bar offers *Apply to an invoice*; it offers *Reverse* | Not run | |
| N9 | Accounts → Journal Entries: choose "Posted by: Sales invoices" and a Period | Only entries the sales invoices posted, in that period. A hand-written draft offers Post on the bar; a document's entry offers no Reverse | Not run | |
| N10 | Accounts → Trial Balance, Profit & Loss, Balance Sheet | The period is chosen on the page line, not in a band above the table. Totals as in section 8 | Not run | |
| N11 | Sell → Customer Statements | Ageing is a grid with a column per age band; double-click a customer: their statement opens as a grid with Opening and Closing as figures on the line | Not run | |
| N12 | Stock → Physical Count, Stock Summary, Expiry Monitor | Physical Count names each count's warehouse and shows "n of m lines counted"; Stock Summary and Expiry Monitor show figures on the line, not rows of cards | Not run | |
| N13 | Masters → Customers: pick a customer | The bar names them (name · code · city · status) with Open, Edit and Delete | Not run | |
| N14 | Accounts → Books → Chart of Accounts in QA01 | An *Indirect Expenses* group with Rent, Salaries and Wages, Electricity, Telephone and Internet, Travel and Conveyance, Office and General Expenses, Repairs and Maintenance, Bank Charges (6000 to 6700) | Not run | |
| N15 | Record rent as a journal (P&L guide, section 3): debit 6000 Rent 5,000, credit 1010 Bank 5,000, and post it | Profit & Loss shows Rent 5,000 among the expenses; the bank balance falls by 5,000 | Not run | |
| N16 | Settings (gear) → Platform → System → Audit Logs: pick an entry, then Open | A grid; the entry's field changes open in a window, not in a side pane | Not run | |
| N17 | Resize the window to 1366 × 768 and repeat N1 and N2 on Purchase Invoices | Everything fits on the line (steps fold under … when short); the bar's steps stay reachable | Not run | |

## 16. What was added in Waves 1 to 3 (2026-10-03)

Run after sections 1 to 14, on QA01, as the firm administrator unless a step
names another login. Each step is the shortest walk through one new feature;
the case named in the last column of the step has the full set of checks. The
expected figures follow from the same numbers as before (cost 100, price 150,
GST 18% within the state). **Written from the code, not yet driven:** where a
figure depends on stock left over from earlier sections, the step says what to
read rather than a number.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| X1 | Sell → Documents → **Enquiries** → **+ New**: a prospect *QA Walk-in* with phone `+919800000201` and city, source *Walk-in*, expected value 1,500, next follow-up tomorrow; one line `QA-P1` × 10. Save | Numbered `ENQ-…`, status open, listed under *Follow-ups due* tomorrow (TC-SELL-028) | Not run | |
| X2 | On it choose **Convert to quotation** | A customer *QA Walk-in* is created from the prospect (code from the customer series) and a **draft quotation** for 10 × 150 = taxable **1,500.00** plus 18% GST is made; the enquiry names both | Not run | |
| X3 | Open the quotation, **Convert to sales order**; look at the enquiry again | The enquiry now reads **WON**. A second enquiry marked **Lost** with a reason appears in Reports → Operational → *Enquiries lost* | Not run | |
| X4 | Settings (gear) → **Firm** → **Approval Levels** → New: *Sales order*, level 1, from **5,000**, role *Firm Administrator*. As the **field salesperson** raise an order for QA-C1 of 40 × 150 (total 7,080.00) and try **Approve** | Refused, naming the level and the role that may sign it (TC-FIN-021) | Not run | |
| X5 | As the administrator, Sell → Documents → **Approvals**, find the order and **Sign off** (or Approve it on the order) | The last open level is signed, so the order is **Approved**. An order of 10 × 150 (1,770.00) approves with no sign-off | Not run | |
| X6 | Buy → Documents → **Requisitions** → **+ New**: `QA-P1` × 20, supplier QA-V1 → Submit → Approve → **Convert to orders** | A draft purchase order for QA-V1 is made (taxable 2,000.00, tax 360.00, total 2,360.00), priced from the supplier's terms; the requisition reads Ordered (TC-BUY-020) | Not run | |
| X7 | Stock → **Stock Transfers** → **+ New**: MAIN to STORE2, QA-P1 × 4. Note MAIN's quantity, then **Dispatch** | MAIN falls by 4; the 4 are **in transit** at STORE2 (Stock Summary shows them as incoming there). No journal is posted: Accounts → Journal Entries has nothing new (TC-STOCK-009) | Not run | |
| X8 | **Receive** the transfer with all 4 arrived, then print the **challan** | STORE2 holds 4 more, none damaged; the challan has no values; the transfer is final | Not run | |
| X9 | Masters → Products → **+ New** `QA-KIT` *QA Gift Pack*, type **Bundle**; **Components**: `QA-P1` × 2. Then **Assemble** 2 kits | `QA-P1` falls by **4**, `QA-KIT` holds **2**, carrying a cost of 200 each (the components' cost) (TC-STOCK-012) | Not run | |
| X10 | Buy → Money → **Landed Costs** → **+ New**: the two goods receipts of section 3, a freight charge of **1,000** from QA-V1 with its bill number, spread **by value**. Post | The 600 and 400 shares go to the receipts' lines; the part that belongs to goods still on hand **raises the stock's average cost**, and the part belonging to goods already sold goes to cost of goods sold. Journal: Dr Inventory and Cost of Goods Sold, Cr *Expenses Included in Valuation* (TC-BUY-026) | Not run | |
| X11 | Sell → **Sales Invoices** → **+ New** by product for QA-C1 (counter bill): give `QA-P1` a barcode first, type it into the **scan field** twice, split the tender **Cash 100 / UPI** for the rest, press **Save & print (F9)** | Quantity 2 on one line; the bill is approved, printed and a new blank bill opens; two receipts exist (cash and UPI), both allocated to the bill, which shows paid (TC-SELL-029) | Not run | |
| X12 | Sell → Money → **Post-dated Cheques** → **+ New**: QA-C1, 500.00, a cheque dated tomorrow. Try **Deposit** today; then **Bounce** it after depositing on the date (or back-date) with charges 50 | Deposit is refused before the cheque's date; a bounce reverses the receipt and posts the charges to QA-C1's account (TC-FIN-013) | Not run | |
| X13 | Accounts → **Bank Reconciliation**: import a statement file for the bank account with a line for the 1,180.00 payment of W28, then **Auto-match** | The line is matched to the payment's posting (amount, date within 3 days, reference); the reconciliation statement shows only the lines left unmatched and checks against the statement's closing balance (TC-FIN-012) | Not run | |
| X14 | Masters → Customers → **+ New** `QA-C7` *QA Retail Stores* with the same phone number as QA-C1 | Before saving, a **duplicate warning** names QA-C1 (it does not block). Save anyway, then select `QA-C7` → **Merge into...** → QA-C1 (TC-MAST-012) | Not run | |
| X15 | Open QA-C1's statement, then the customer list | `QA-C7` is gone from the list; anything raised for it now sits on QA-C1, and QA-C1's balances are the sum of both | Not run | |
| X16 | Accounts → Tax filing → **GST checks** for this month | The findings are listed by code with the document they are about. A made-up GSTIN such as `33ABCDE1234F1Z5` may be flagged for its check character; that is the check working, not a fault (TC-COMP-021) | Not run | |
| X17 | Accounts → Books → **Export to Tally**: today's month, **Export** | An XML file is saved; every posted journal of the period is a voucher typed by its source, with a ledger per customer and supplier (TC-FIN-020) | Not run | |
| X18 | Accounts → Statements → **Cash Flow** for the same periods as Profit & Loss | Operating, investing and financing sections, opening and closing cash, and a line saying whether it reconciles (TC-FIN-018) | Not run | |
| X19 | Home: open the bell | Lists what waits for you (for example the purchase order awaiting approval from X6, stock alerts), each counted (TC-FIN-022) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| App version (sign-in screen) | |
| Steps passed / failed / blocked | |
| Server log files sent | |
| Worst problem found | |
