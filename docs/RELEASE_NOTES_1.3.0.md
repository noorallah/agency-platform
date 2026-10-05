# Agency Platform 1.3.0: release notes and test hand-over

Release 1.3.0 is the **agency's branding release**: the agency's own name,
tagline and logo on the sign-in screen and at the top of every screen, given
at install or after the first sign-in, and the product's own name shown
quietly beside them. It upgrades 1.1.x and 1.0.x in place and backs up the
database first.

**Read this first: the 1.2.0 installer was never built.** Its build was
stopped before it finished, so no tester received it. 1.3.0 is therefore the
first installer since 1.0.2, and it carries **everything in the 1.2.0 notes**
(`docs/RELEASE_NOTES_1.2.0.md`: the light menu, Settings > Set up and
Platform, favourites, My preferences and the whole Wave 1 to 3 backlog build)
as well as the branding below. Treat the 1.2.0 rows as part of this pass.

Built 2026-10-04 from `main`: the 1.2.0 content up to #1062 (and the 1.2.0
test book, #1063), plus the branding work #1066 to #1070 and the version
bump #1071. Each item was checked by its own tests; many of the cases were
written from the code and have not yet been driven by hand, which is what
this pass is for.

**Added on 2026-10-05, still in 1.3.0** (1.3.0 has not been distributed): the
**purchasing build** (fourteen features, PG-1 to PG-14, `docs/BACKLOG.md` §86,
#1116 to #1141) and the **selling build** (nine features, SG-1 to SG-9, §87,
#1153 to #1168), with three defects fixed on the way (#1163, #1172). An
installer built before 2026-10-05 does not hold them: test them on a build
made from `main` at #1172 or later. **None of these features has been through
a full test suite, a CI run or a hand test.** Each was checked by its own
tests only, and every row and case about them below was written from the
code, so read each as *(confirm)*: a failure may be the case's mistake until
it is settled.

## How to test it: one pass, in this order

Each row names the screen. Do them on a copy of a firm, or on the demo firm.
**Menu paths use the new menu** described in the 1.2.0 notes: each top
drop-down shows daily work only and every other screen is behind **All <Area>
screens** at its foot. **Ctrl+K** finds any screen by name if you lose one.

**Start with the sanity check** (`docs/qa/SANITY_CHECK.md`, PDF *Sanity check* in the hand-over folder). If it fails, report that before anything below.

**Then the branding rows below**, in order: rows 1 to 3 need a **fresh server
install** on a spare PC (the Branding page appears only there), so do them
first or last, not in the middle. Rows 4 onwards use the installation you
already have. The cases are TC-ME-014 to TC-ME-018 in
`docs/qa/02_SIGN_IN_AND_ACCOUNTS.md`, and QA-BRD-01 to QA-BRD-24 in
`docs/QA_TEST_BOOK.md`; the installer rows are also in
`docs/INSTALLER_QA_CHECKLIST.md` (section F). **After that, the 1.2.0 rows**
(next section), **and last the purchasing and selling rows of 2026-10-05**,
which are below the branding table.

### The agency's branding

| # | What | Where | What to look for |
| --- | --- | --- | --- |
| 1 | **Branding page of the installer** | Setup, a fresh **server** install: the page after *This PC* | Agency name, Tagline and a Logo file with Browse, all optional; below them, read-only, *This product: Agency Platform, by* its company. A tagline or logo without a name is refused on Next; a logo path that does not exist is refused. Leave all blank and the install is unchanged. **The page does not appear** for an app-only PC, an upgrade or a repair |
| 2 | **A refused logo never fails the install** | The same page, a text file renamed `fake.png`, or a picture over 1 MB | The install completes, the name is saved, no logo is saved (initials show), and the install log (`C:\ProgramData\Agency Platform\logs\install`) holds a warning; the logo can be added later (row 9) |
| 3 | **Branding saved after the server starts** | After such an install: sign in as the platform administrator; Settings > Platform > Audit Logs (no firm) | No *Set up your agency* dialog if a name was given; the name shows on the sign-in screen and at the top; the audit trail holds `agency_branding.created` |
| 4 | **Sign-in screen with the agency** | The sign-in screen | The agency's logo (or initials), name and tagline above the form; a night-blue panel at the left cycling eight strengths about every 8 seconds, **stopping for good once you type** in either box; arrows and dots; below 900 px wide the panel goes and the card stands alone; the title bar reads **Agency Platform - Sign in** |
| 5 | **Product mark and status line** | Foot of the sign-in card; status line | *Agency Platform*, by its company and tagline in the card's foot; the status line shows the server state, version 1.3.0 and *Powered by Agency Platform* |
| 6 | **More help, Copy details for support** | Sign-in screen > More help | Support phone, WhatsApp, hours, email and website show only when filled; **they are blank in this release by design**, so none appears; *Forgot your password? Your administrator resets it.*; **Copy details for support** copies product, version, server and this PC's name (no password) |
| 7 | **Server not answering** | Stop the server, reopen the app | The sign-in screen still opens at once with the agency's name, tagline and logo from this PC's last visit (or Agency Platform's own on a PC that never had one); no error box |
| 8 | **First sign-in: Set up your agency** | Sign in as the platform administrator while branding is not set | A dialog with name, tagline, logo and a live preview; **Skip for now** closes it and Home shows a **Finish setting up** card until it is set; Save with a name closes it and the card goes; it is not shown to a firm administrator or anyone without platform settings rights, and does not reopen for a user who skipped |
| 9 | **Settings > Platform > Agency > Branding** | Settings (gear) > Platform > Agency > Branding | One form: name (required), tagline, logo (PNG or JPG, at most 1 MB), a preview of the sign-in card and the top of every screen, and our product, company and logo read-only; **no accent colour box**; Save shows *Saved.* and the header changes at once; **Remove logo** shows the initials; a text file renamed `.png` is refused (*The logo must be a PNG or JPG image.*), an over-size picture is refused naming its size; two PCs editing at once: the second save is refused with the somebody-else-saved message and keeps what was typed |
| 10 | **Branding in the audit trail** | Settings > Platform > Audit Logs, no firm chosen | `agency_branding.created`, `agency_branding.updated`, `agency_branding.logo_changed` (the type and size, never the image), each naming who; another PC sees the new branding at its next sign-in screen |
| 11 | **The header** | Left of the menu strip; the window's title bar | The agency's logo, name and tagline lead the strip before Home, then the firm's name as plain text (firm switcher unchanged); the title bar reads **<agency> > <firm>**, the agency alone when no firm is chosen; below 820 px only the logo shows, the tagline from 1280 px; clicking it opens Home; no extra height |
| 12 | **Product on the status line** | Right end of the status line | *Agency Platform 1.3.0 by* its company and a tooltip with the same; clicking does nothing |

### Buying: the purchasing build of 2026-10-05 *(confirm: not yet run by hand)*

Do these **after the 1.2.0 rows**, in the order below. The cases are
TC-BUY-029 to TC-BUY-090 in `docs/qa/06_PURCHASING.md` (values in
`docs/qa/14_TEST_DATA.md`); QA-BUY-21 to QA-BUY-34 in `docs/QA_TEST_BOOK.md`
are the short form. Two warnings on order:

- **The TDS cases (TC-BUY-043 to 048) each need a supplier of their own with no
  other bill or payment in the financial year.** Use a new supplier each time.
- **Only TC-BUY-086 and TC-BUY-088 change a firm-wide setting.** Imports and
  capital goods (rows 13 and 14) now run on the full chain: the purchase order
  has **Currency** and **Exchange rate**, and the order and receipt lines a
  **Capital goods** tick. The two cases that type the bill alone need
  Settings > Buying > Purchase Settings > **Buying stages** with **Purchase
  order** off (which takes **Goods receipt** off with it): run those two when
  nobody else is buying in the firm, or in a firm of its own, and switch both
  back on after.

| # | What | Where | What to look for | Cases |
| --- | --- | --- | --- | --- |
| 1 | **GST purchase register, HSN summary of purchases** | Reports > Financial | Approved and closed bills by tax head, with tax that may not be claimed and reverse charge apart; a debit note and a purchase return after billing are minus rows on their own dates; the HSN summary folds the same bills by HSN code and unit; a bill in another currency is shown in rupees at the bill's rate | TC-BUY-029 to 032, 089 |
| 2 | **Payables by Month** | Buy > All Buy screens > Money > Payables by Month | What each supplier is owed by month, with Older, Credits and Outstanding, a total row and a check against the books (account 2100); an Owed / Paid switch and a branch filter | TC-BUY-033 to 035 |
| 3 | **Cash purchase in one step** | Buy > Purchase Invoices > Approve | The Approve dialog has a **Paid now** tick (method, amount, reference, date) for a user who may record payments; the button reads **Approve and pay**; more than the bill is refused; reversing the payment leaves the bill approved and owing | TC-BUY-036 to 039 |
| 4 | **Attach the supplier's bill** | The bill and goods receipt windows: **Attachments**; a **Files** column on both lists | PDF, JPG or PNG up to 10 MB; add, open, save, delete; the wrong kind or an over-size file is refused. Reading a bill into a draft (OCR) is not built | TC-BUY-040 to 042 |
| 5 | **TDS 194C and 194J worked out** | The supplier's **Usual TDS section**; Settings > Tax > TDS on purchases (194Q, 194C, 194J); the bill's Approve dialog | The bill proposes the deduction and posts it at approval, with an override box; the proposal is worked on the lines plus additional charges; a payment ahead of any bill proposes it too, in a hint that follows the amount typed, and it is deducted once; the settings card names each rate (companies and firms, an individual or HUF, professional fees, technical services) and refuses a blank, zero or above-30 rate | TC-BUY-043 to 049 |
| 6 | **TCS charged by a supplier** | The purchase bill: TCS rate and TCS amount; Reports > Financial > TCS paid to suppliers | A rate alone is worked on the bill total including GST, a typed amount wins; approval posts it to *TCS Receivable* (1430); the bill owes its total plus the TCS | TC-BUY-050 to 053 |
| 7 | **Send the purchase order by WhatsApp** | Buy > Purchase Orders > Send | WhatsApp beside Email; refused until messaging, the channel and the template for *Purchase order sent to the supplier* are set; the order is then marked sent. The PDF is not attached | TC-BUY-054, 055 |
| 8 | **Requests for quotation** | Buy > All Buy screens > Documents > Requests for quotation; **Create RFQ** on an approved requisition | Send, **Enter quotes** one supplier at a time, **Compare** with the lowest landed rate marked, a reason for any other choice, **Raise orders**: one draft order per chosen supplier. Emailing the RFQ is not built | TC-BUY-056 to 059 |
| 9 | **Rate contracts** | Buy > All Buy screens > Documents > Rate contracts | Approve makes it active; a blank price on an order line takes the contract's rate (a mark on the rate); drawn and remaining per line; over-drawing warns in a banner and never refuses; overlap refused at approval; Close, Cancel with a reason, Releases | TC-BUY-060 to 062 |
| 10 | **Serial numbers at receipt** | A serial-tracked goods receipt or purchase return line: the **Serials** cell | Type, paste or **Fill a range**; one serial per unit before the receipt completes; a serial already in the firm is refused; cancelling the receipt removes the units; a return names the units going back | TC-BUY-063 to 065 |
| 11 | **Supplier schemes** | Buy > All Buy screens > Documents > Supplier schemes; the purchase order | "Buy 10, get 2" fills a blank **Free** box and the side panel says *Scheme 10+2 applied*; a typed figure is kept and 0 refuses the scheme; a scheme giving another product adds a gift line once | TC-BUY-066 to 069 |
| 12 | **Batch-wise PTR and PTS** | A batch receipt line, the batch list and picker; **Trade class** on the customer | Only on a firm with the feature (Pharmacy, Food and Wholesale profiles): PTR and PTS beside the MRP, never above it, and a batch number required; a retailer's blank price takes PTR and a stockist's PTS. A firm without the feature is shown none of it | TC-BUY-082 to 085 |
| 13 | **Imports** | A **Currency** on the supplier; **Currency** and **Exchange rate** on the purchase order; the purchase bill and payment windows; Buy > All Buy screens > Documents > Bills of entry; Accounts > Journal Entries > *Revalue foreign payables* | An order in the supplier's currency with a rate; the receipt values stock in rupees at the order's rate; the bill is in the order's currency (another is refused) and posts rupees at its own rate, with only a rate difference in price variance; no TCS, TDS or Paid now on it; a payment in the currency at another rate posts the exchange gain or loss; a Bill of Entry lands customs duty on the stock and claims the IGST (GSTR-3B 4(A)(1)) | TC-BUY-070 to 076, 086, 087 |
| 14 | **Fixed assets** | **Capital goods** on the purchase order line and the goods receipt line; the bill line's tick and asset class; Accounts > All Accounts screens > Fixed assets (Asset register, Asset classes, Depreciation runs, Income-tax block schedule) | A line marked on the order or the receipt is received without entering stock, and its bill line raises an asset; a line a receipt already took into stock is refused at the bill; a depreciation run posts one journal, by days; disposal books a gain or a loss; the latest run can be cancelled | TC-BUY-077 to 081, 088, 090 |

### Selling: the selling build of 2026-10-05 *(confirm: not yet run by hand)*

Then these, in order. The cases are TC-SELL-036 to TC-SELL-087 in
`docs/qa/08_SELLING.md`, which opens with the masters they share; QA-SELL-37
to QA-SELL-45 in `docs/QA_TEST_BOOK.md` are the short form. The counter cases
(rows 2 and 7) need Settings > Selling > **Sales Stages** with *Sales order*
and *Delivery note* both off, so that **New Invoice** opens the counter bill;
switch both back on afterwards.

| # | What | Where | What to look for | Cases |
| --- | --- | --- | --- | --- |
| 1 | **GST sales register, HSN summary of sales** | Reports > Financial | Every declared document of a period by tax head; credit notes and returns in minus, a customer debit note in plus; the HSN summary adds up to the register and both agree with GSTR-1 | TC-SELL-036 to 039 |
| 2 | **Walk-in cash sale** | The counter bill: **Walk-in** | One *Cash sale* customer per firm, made on first use; the buyer's name and phone typed on the bill and printed; refused at approval unless paid in full; no loyalty points; the customer cannot be deleted, given credit or a GSTIN, or made inactive | TC-SELL-040 to 045 |
| 3 | **Service invoices** | Any sales document with a product of type *SERVICE* | Billed with its SAC; no reservation, no stock movement, no cost of goods sold, never a back order. No new screen | TC-SELL-046 to 049 |
| 4 | **Other charges with their own GST** | The sales bill: **Other charges** > **Add charge** | Up to ten charges (packing, handling), each taxed by the tax profile it names, or untaxed with none; in the bill's tax and total, on the print, in the register and in GSTR-1; credited to *Other Charges Recovered* (4050) | TC-SELL-050 to 054 |
| 5 | **Transporters and freight terms** | Settings > Set up > Territories & routes > Transporters; the delivery note's **Carrier (master)** and **Freight** | Choosing a carrier fills the note's transporter, GSTIN and mode; what is typed on the note wins; an inactive carrier is not offered | TC-SELL-055 to 059 |
| 6 | **Attachments on sales documents** | Quotation, sales order, delivery note, sales invoice and sales return lists: **Attachments**; a **Files** column | PDF, JPG or PNG up to 10 MB; each document keeps its own files | TC-SELL-060 to 063 |
| 7 | **Hold and recall; counter shifts** | The counter bill: **Hold (F8)**, **Recall**, the shift strip; Sell > All Sell screens > Documents > Counter Shifts | A held bill is parked with a note and never approved while held; a shift opens with a float, expected cash is the float plus the cash tenders, and closing on a count posts a shortage or excess to *Cash Short and Over* (6960). A bill a Counter Sales user makes and a manager approves is counted in the **cashier's** shift | TC-SELL-064 to 072, 087 |
| 8 | **Collection Sheet and Payment Promises** | Sell > All Sell screens > Money; **Collector** on the customer | The sheet lists open bills by collector with days overdue and the latest promise, with a PDF; a promise posts nothing and reads pending, due today, kept, broken or withdrawn; it is withdrawn, never edited | TC-SELL-073 to 079 |
| 9 | **Customer Rebates** | Sell > All Sell screens > Documents > Customer Rebates; Reports > Financial > Customer rebate statement | An agreement for a customer or a customer group with slabs; accrued once after the period ends; settled by a party adjustment of kind *Customer rebate*; **Settle against bills** is shown only to a user who may manage party adjustments, so not to a Sales Manager; no GST on a rebate | TC-SELL-080 to 086 |

## Carried from the 1.2.0 notes

Everything in `docs/RELEASE_NOTES_1.2.0.md` is part of this build, and **no
tester has yet seen it on an installer**: its 75 rows (the light menu,
Settings > Set up and Platform, favourites, My preferences, the bell, and the
selling, buying, stock, accounts and tax, masters and reports rows) are to be
tested in full from those notes, with their menu paths. Behind them are the
1.1.0 notes (`docs/RELEASE_NOTES_1.1.0.md`) and everything since the 1.0.2
installer, which is the last build testers received.

## Fixed since 1.2.0

- The sign-in screen, the header and the status line had no place for the
  agency's own name and logo; they have (backlog 71).
- A fresh install had no way to name the agency; the Branding page and
  Settings > Platform > Agency > Branding give it.

Fixed on 2026-10-05, during the purchasing and selling builds (each fix has
its own test; none was re-checked by hand):

- **TDS deducted on a purchase bill could not be put on a challan in an
  upgraded store** (D-FIN-25, #1163). An old database check stayed behind
  after an upgrade; migration `20261005_0323` removes it.
- **Regenerating a firm's demo history refused to start** (D-CFG-24, #1172).
  Seventeen tables that arrived with later features were missing from the
  reset's list, and three were cleared in the wrong order. Developer and demo
  data only; an installed firm is not affected.
- **A supplier rebate accrued, reversed and accrued again was refused**
  (D-BUY-34, #1172). The second and later accruals are now numbered.
- **A cashier's shift took no bills** (D-SELL-51, #1174). A bill paid at the
  counter was counted in the shift of whoever approved it, and the counter
  roles cannot approve. It is now counted in the open shift of the cashier
  who **made** it; the approver's own shift takes it only when the maker has
  none open.
- **Settle against bills was offered to a user whose save was refused**
  (D-SELL-52, #1174). Customer Rebates and Supplier Rebates now show it only
  to a user who may manage party adjustments: a firm administrator or a firm
  manager, not a Sales Manager. The Accounts job holds that right but cannot
  open either screen.
- **The GST purchase register listed a foreign-currency bill in currency
  units** (D-BUY-35, #1175). The register, the HSN summary of purchases, the
  purchase invoice register, purchase analysis and GSTR-3B's input side now
  show it in rupees at the bill's rate.
- **The payment dialog's 194C/194J hint ignored the amount being paid**
  (D-BUY-36, #1175). It follows the amount and what is applied to bills.
- **The bill's Approve dialog worked its TDS proposal on the lines alone**
  (D-BUY-37, #1175). It now shows the figure the server posts: the lines plus
  additional charges.
- **The 194C/194J settings card mislabelled its second rate** (D-BUY-38,
  #1175). The boxes read *Rate % (companies, firms and others)* and *Rate %
  for an individual or HUF* (194C), *Rate % for professional fees* and *Rate %
  for technical services, call centres and royalty on films* (194J); a blank,
  zero or above-30 rate is refused in the form.
- **An import could not be typed on a purchase order, and nothing held a
  bill to its order's currency** (D-BUY-39, #1175). The purchase order has
  **Currency** and **Exchange rate**; a bill takes its order's currency and
  rate; a bill in another currency than its order is refused, and so is a
  foreign-currency order with no rate.
- **Capital goods could not be bought with the goods receipt stage on**
  (D-BUY-40, #1175). The order line and the receipt line have a **Capital
  goods** tick: such a line is received without entering stock and the bill
  capitalises it. Migration `20261005_0326`.

## Known limits and what is not in it

- **Help > About is not built** (clicking the product on the status line does
  nothing).
- **First-run is step 1 only** ("Set up your agency"); the later steps, and a
  prompt in the header strip, are not built. Home's *Finish setting up* card
  stands in for them.
- **The "PRACTICE" mark** is not built (there is no practice-firm feature).
- **Support details are blank by design**: no phone, WhatsApp, hours, email
  or website is shown on the sign-in screen until they are packaged.
- The accent colour is stored but not asked or applied; the product logo on
  the status line is a placeholder icon until one is packaged.
- The logo's shape is not checked by the server; the screens fit it into a
  square.
- Everything under *Known limits* in the 1.2.0 notes still holds: the 26Q FVU
  file, live e-invoice and e-way bill, real WhatsApp and SMS sends, payment
  links, rule 43 and licensing are not built; *Rows per page* is not offered.

### Known gaps in the purchasing and selling builds

Not built (from `docs/BACKLOG.md` §86 and §87):

- **Buying:** reading a supplier's bill into a draft (OCR); emailing an RFQ; a
  Bill of Entry in the GST purchase register and against GSTR-2B's import
  rows; purchase returns and debit notes in another currency; withholding on a
  payment abroad (section 195); capitalising goods already in stock; GST on
  the sale of an asset (raise a sales invoice); recurring purchase bills; job
  work; drop-ship; consignment; a supplier credit limit; "10+2" printed on the
  order. The purchase order sent by WhatsApp carries no PDF.
- **Selling:** charges are not carried from the sales order and cannot be
  credited by a credit note or a return; the carrier of a delivery note
  already raised cannot be changed on screen; a promise for the account as a
  whole (from the screen), the promise on the customer statement and a
  reminder from a broken promise; a counter refund against a bill, a count by
  denomination and handing a shift over; a rebate settled by a GST credit
  note or paid out in money. Van sales, export and SEZ sales, warranty claims,
  packing slips, bill of supply and the rest of §87 rows 10 to 31 are for
  later.

Open defects found by reading the code on 2026-10-05, **not yet driven**
(`docs/DEFECTS.md`). The eight found while the cases were written (D-SELL-51,
D-SELL-52, D-BUY-35 to D-BUY-40) were fixed the same day and are under *Fixed
since 1.2.0* above; these two were found while fixing them:

- **D-BUY-41 (medium):** a debit note or a purchase return against a
  foreign-currency bill is not converted to rupees in the ledger or in
  GSTR-3B's reversal. Do not raise one against a foreign bill in this build.
- **D-CMP-23 (low):** GSTR-2B matching, rule 37 and rule 42 read a
  foreign-currency bill in currency units. A supplier abroad is never in
  GSTR-2B, so this reaches a foreign bill under reverse charge.

**On every failure**: a screenshot, the newest file in
`C:\ProgramData\Agency Platform\logs\server`, and the version on the sign-in
screen (1.3.0).

## Upgrading

Setup backs up the database, then migrates every firm's store to the new
schema (revisions up to `20261004_0300`: everything in the 1.2.0 notes, then
the one new platform table, `agency_branding`). Nothing existing changes how
it prices or posts. The branding is **empty after an upgrade**: no Branding
page is shown on an upgrade, so the first platform administrator to sign in is
asked *Set up your agency* (or skips it, and Home keeps the *Finish setting
up* card until it is given). Until then the sign-in screen and header show
Agency Platform's own name.

**Database, with the purchasing and selling builds.** A build from 2026-10-05
migrates every store on to **`20261005_0326`**, 26 revisions past
`20261004_0300`: the purchasing tables and columns (`20261005_0306` to
`20261005_0316`), the selling ones (`20261005_0318` to `20261005_0325`),
among them `20261005_0323`, which repairs the TDS challan check in stores
already upgraded, and `20261005_0326`, the capital-goods mark on purchase
order lines and goods receipt lines. They add tables, columns and control accounts (for a firm
whose books are open, only where missing); no existing document is repriced
or reposted. *(confirm: this upgrade has not been rehearsed on an installed
copy.)*

The two changes from 1.2.0 apply to anyone coming from an earlier build:

- **Date format becomes dd-MM-yyyy**, because nobody could choose one before.
  Anyone can change it under My preferences.
- **Admin screens are under Settings > Platform.** The Admin area is gone from
  the bar, and the *Primary firm* menu entry is replaced by *Start in firm* in
  My preferences.

Set-up lists (Pricing, Territories & routes, Account structure, Party lists,
Item lists, Locations) have moved out of the drop-downs to Settings > Set up.
