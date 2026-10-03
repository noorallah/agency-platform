# Agency Platform 1.2.0: release notes and test hand-over

Release 1.2.0 is the **menu and breadth release**: a lighter menu with your
own settings, and the whole of the 96-item backlog build (selling, buying,
stock, accounts, GST, masters, reports and platform). It upgrades 1.1.x and
1.0.x in place and backs up the database first.

Built 2026-10-04 from `main`. It carries everything merged since the 1.1.0
build of 2026-10-01 (commit 4fc41dd0, #889) up to #1062: the 2026-10-02
additions already listed in the 1.1.0 notes, and everything built on
2026-10-03 and 2026-10-04. Each item was checked by its own tests; many of
the cases below were written from the code and have not yet been driven by
hand, which is what this pass is for.

## How to test it: one pass, in this order

Each row names the screen. Do them on a copy of a firm, or on the demo firm.
**Menu paths use the new menu.** Each top drop-down (Sell, Buy, Stock,
Accounts, Masters) shows only daily work; every other screen of the area is
behind **All <Area> screens** at the foot of the drop-down, under its group
name, so `Sell > All Sell screens > Insight > Sales Analysis` means: open
Sell, choose *All Sell screens*, then the Insight group. **Ctrl+K** finds any
screen by name if you lose one.

**Start with the sanity check** (`docs/qa/SANITY_CHECK.md`, PDF *Sanity check* in the hand-over folder). The quick check proves the server answers, every store is migrated and every list and report of every firm opens, module by module; the cases after it walk each module on the demo firm WHOLE01 with the figures to expect. If it fails, report that before anything below.

Section 16 of `docs/QA_FUNCTIONAL_WALKTHROUGH.md` (steps X1 to X19) walks the main new flows on one small firm with the figures to expect; use it beside the tables below. The cases named in the rows are in `docs/qa/`.

### The new menu and your own settings

| # | What | Where | What to look for |
| --- | --- | --- | --- |
| 1 | **Light menu** | Sell, Buy, Stock, Accounts, Masters drop-downs | Only daily lists (Sell: Quotations, Sales Orders, Delivery Notes, Sales Invoices, Returns & notes, Receipts, Customer Statements); *All Sell screens (N)* at the foot opens every other screen under its old group name; *Returns & notes* opens a short list (Sell: Sales Returns, Credit Notes, Customer Debit Notes; Buy: Purchase Returns, Debit Notes); the **Admin** area is gone from the bar |
| 2 | **Settings > Set up and Platform** | Settings (gear) | Cards with a search box: SET UP (Pricing, Territories & routes, Account structure, Party lists, Item lists, Locations) and PLATFORM (People, Firms, System: Audit Logs, Diagnostics, Licensing, Backups, Platform Dashboard); Firm, Selling, Buying, Stock, Tax and Business profile sections are still there |
| 3 | **Favourites** | Hover any drop-down item and click its star; Home > FAVOURITES | The box shows your list; the cross removes one, drag reorders; starred screens come first in Ctrl+K; sign in on another PC and the same list is there (D-UI-3) |
| 4 | **My preferences** | User menu (top right) > My preferences, or Settings > This PC and me > My Preferences | *Start in firm* (only with more than one firm), *First screen* (the screen I was last on, or any screen you may open), *Theme* (Light, Dark, Follow Windows), *Text size* (Small, Default, Large; this PC only), *Date format* (dd-MM-yyyy, dd/MM/yyyy, yyyy-MM-dd, MM/dd/yyyy); dates on the new screens follow it; there is no *Rows per page*; the old *Primary firm* menu entry is gone |
| 5 | **The bell** | Top bar | Lists what waits for you (approvals, refused sends, stock alerts), each counted; opening one goes to it (TC-FIN-022) |

### Selling

| # | What | Where | What to look for |
| --- | --- | --- | --- |
| 6 | **Enquiries and leads** | Sell > All Sell screens > Documents > Enquiries | New enquiry numbered ENQ with lines and next follow-up; *Follow-ups due*; *Convert to quotation* makes the customer from the prospect and a draft quotation; WON when the quotation becomes an order; *Lost* needs a reason (TC-SELL-028) |
| 7 | **Approval levels** | Settings > Firm > Approval Levels; Sell (or Buy) > All ... screens > Documents > Approvals | A rule by document type, level, from amount and role; an order above it is refused at Approve naming the level and role; *Sign off* signs the next level, the last approves; *Reject* needs a reason, also in bulk (TC-FIN-021) |
| 8 | **Customer first, then tick the notes** | Sell > Sales Invoices > New from delivery notes | Pick the customer, then a tick list of that customer's dispatched notes with something left to bill; a clash of branch, salesman, territory or route is refused by name |
| 9 | **Fast counter billing** | Sell > Sales Invoices > New by product | Scan field adds a line or adds 1; *Save & print (F9)* saves, approves, prints and opens the next bill; tender split Cash / UPI / card with balance and change (TC-SELL-029) |
| 10 | **Pick list and loading sheet** | Sell > Delivery Notes, tick notes | *Pick list* sums products and batches; *Loading sheet* lists drops in route order per vehicle (TC-SELL-030) |
| 11 | **Cash discount and overdue interest** | Masters > Customers (terms); Settings > Selling > Credit Control; Sell > Receipts > Record receipt; Sell > Customer Statements | Discount days and percent on the customer prefill the receipt; interest at the firm's rate shows on the statement; *Raise interest debit note* makes a draft (TC-SELL-031) |
| 12 | **New outlet waits for approval** | Settings > Firm (switch on); Masters > Customers > New by a person without the approve right | *Pending approval* badge and filter; cannot be billed until approved, singly or in bulk (TC-SELL-032) |
| 13 | **Price levels and special rates** | Settings > Set up > Pricing > Price Levels; a customer or group; Masters > Products | A level (Retail, Wholesale, Dealer) on the customer or group; a price-list rate beats the level, which beats the product price; orders and quotations open prefilled (TC-SELL-033) |
| 14 | **Buy X get Y, and combo price** | Settings > Set up > Pricing > Promotions > New | *Buy X get Y at N% off* discounts the cheapest units, repeating per set; *Combo price* spreads over the lines so each keeps its own GST; *Try offers* shows why each applied |
| 15 | **Offer conditions** | Promotions > New, conditions | First order, or not billed in N days; days of the week and time of day; the offer applies only then |
| 16 | **Festival points, coupons, copy, principal share** | Promotions; Settings > Set up > Pricing > Loyalty | *Bonus loyalty points* multiplier for the dates; *Generate codes* (single-use, up to 5,000) and *Export codes*; *Copy with new dates...* makes drafts; a funding principal and its share feed Principal Claims (row 30) |
| 17 | **UPI QR on the bill** | Sell > Sales Invoices > Print settings (UPI ID); print an unpaid invoice | *Scan to pay by UPI* with the amount still owed; a paid bill prints none (TC-SELL-034) |
| 18 | **WhatsApp by hand, reminders, other documents** | Sell > Sales Invoices (approved) > WhatsApp; Sell > Customer Statements > Remind; Send on quotation, order, receipt, statement and purchase order | PDF saved to Downloads and WhatsApp opens with the message; Remind sends the statement of account; email and print as the firm's messaging switches allow (TC-SELL-034, 035) |
| 19 | **Stock held for an order lapses** | Sell > Sales Orders; the lapse days in the firm's sales stages | An unshipped order's reservation is released after N days and badged; *Reserve again* takes it back |
| 20 | **Extra fields on documents** | Settings > Firm > Custom Fields; quotation, order, delivery note, invoice, purchase order, goods receipt | *Additional details* on the editor; carried down the chain by field name; printed when *Show on print* |

### Buying

| # | What | Where | What to look for |
| --- | --- | --- | --- |
| 21 | **Requisitions** | Buy > All Buy screens > Documents > Requisitions; Reports > Operational > Below reorder level > Raise requisition | Submit, approve, *Convert to orders* makes one draft order per supplier priced from the supplier's terms (TC-BUY-020) |
| 22 | **Supplier catalogue and terms** | Masters > Vendors > a supplier: Catalogue, standing discount, lead time, usual TDS section | Their code, price, pack, minimum order, multiple, lead time; a new order fills blank price and discount, the expected date and a hint *Use N* for the multiple |
| 23 | **Amend an order** | Buy > Purchase Orders > an approved order > Amend, Revisions | Revision n kept, earlier ones listed; re-approval when the total rises past the approver's limit |
| 24 | **Quality inspection** | Product or category *Inspect on receipt*; Buy > All Buy screens > Documents > Quality Inspection | Received goods wait in quarantine until released or rejected |
| 25 | **Bill matching tolerance** | Settings > Buying > Purchase Settings > Bill matching | A bill past the percent or amount over its order or receipt is held, naming the lines; approving needs the right |
| 26 | **Purchase budgets** | Settings > Buying > Purchase Budgets; Purchase Settings policy | Budget by month, branch, category; a panel on the order; a warning when exceeded |
| 27 | **Payment runs** | Buy > All Buy screens > Money > Payment Runs | Pick bills due by a date, approve once, one payment per supplier, bank file exported; the cashier cannot approve |
| 28 | **Post-dated cheques** | Sell > All Sell screens > Money and Buy > All Buy screens > Money > Post-dated Cheques | Held, not posted, until the date; Deposit refused early; Bounce reverses and posts the charge (TC-FIN-013) |
| 29 | **Landed costs** | Buy > All Buy screens > Money > Landed Costs | Freight spread over receipts by value, quantity or weight; stock on hand revalued, sold share to cost of goods sold (TC-BUY-026) |
| 30 | **Principal claims** | Buy > All Buy screens > Money > Principal Claims | Scheme, expiry and breakage claimed per principal and period, each source once; settled by credit note or receipt |
| 31 | **Supplier rebates and gifts** | Buy > All Buy screens > Money > Supplier Rebates, Supplier Gifts | Slabs accrued and settled by a party adjustment; gifts journal by who keeps them; 194R total per supplier against 20,000 |
| 32 | **Supplier ratings, performance, price trend** | Masters > Vendors > a supplier > Ratings; Buy > All Buy screens > Insight > Rate Trend; the supplier performance report | 1 to 5 per criterion kept apart from the figures; on time, short, rejected; price trend by supplier |
| 33 | **Free goods for customers** | Masters > Products (free issue only); a goods receipt line; stock write-off | Scheme or free quantity on the receipt; a *given free / sample* issue posts promotional expense at cost |
| 34 | **A credit against an opening bill** | Buy > Payments, a supplier with a return credit | The supplier's credit can be set against an opening bill |
| 35 | **Purchase Analysis, the rest** | Buy > All Buy screens > Insight > Purchase Analysis | Ordered and received bases, average rate, last year, saved layouts |

### Stock

| # | What | Where | What to look for |
| --- | --- | --- | --- |
| 36 | **Stock transfer as a document** | Stock > Stock Transfers > New | Dispatch moves stock in transit to the destination, no journal; Receive names damaged and missing; challan has no values (TC-STOCK-009) |
| 37 | **Branch GSTIN** | Masters > Branches > a branch | GSTIN checked against the state; prints, GSTR-1, 3B and e-invoice read the branch's; a transfer between two GSTINs is refused as a transfer |
| 38 | **Repacking and kits** | Stock > All Stock screens > Movements > Repacking; Masters > Products > Components, Assemble | A 25 kg bag into packs carries cost, wastage to loss; a Bundle product assembles from components and is made at dispatch if short (TC-STOCK-012) |
| 39 | **Internal use and adjustment reasons** | Stock write-off; Settings > Stock > Adjustment Reasons | Internal use, Staff, Display each to its own expense; the firm's own reasons list, each tied to an account |
| 40 | **Large adjustments need approval** | Settings > Stock > Adjustment Limits; Stock > All Stock screens > Movements > Adjustment Approvals | Above a role's limit the post is refused, *Submit for approval*, approve or reject singly or in bulk |
| 41 | **Evidence files** | Adjustment, write-off, transfer and count dialogs; *Evidence* | Photos and documents attached and viewable, also after a count is posted |
| 42 | **Incoming, outgoing, projected** | Stock > Stock Summary > Product stock | Incoming (open purchase orders), outgoing (open orders not reserved) and projected beside available |
| 43 | **Count planning** | Stock > Physical Count > Count plans | ABC classes, cycle plans, blind sheet hides system quantity; a difference over the limit needs approval |
| 44 | **Expiry rules, shelf life, issue rule** | Masters > Products; Settings > Set up > Item lists > Product Categories; Stock > Expiry Monitor | Stop-selling, alert and return days; shelf life fills a batch's expiry from its manufacture date; FEFO, FIFO or pick-by-hand refuses silent allocation; *Return to supplier now* on the monitor |
| 45 | **Returns held until checked** | Settings > Stock > Batch Rules; Sell > Returns & notes > Sales Returns | With it on, a completed return lands in quarantine; *Release* puts it on the shelf |
| 46 | **Stock alerts** | Home to-do; the stock ageing report | Low, out, over maximum, near expiry, pending transfers and counts; turnover columns on the ageing |
| 47 | **Labels** | Masters > Products; Buy > Goods Receipts > select > Print labels | Code 128 labels on A4 65-up or 24-up sheets or a 50 x 25 mm roll, with used positions skipped |
| 48 | **Discontinued and not for sale** | Masters > Products | Discontinued still sells but a purchase order refuses it; *Not for sale* is refused on every sales line |

### Accounts and tax

| # | What | Where | What to look for |
| --- | --- | --- | --- |
| 49 | **Bank reconciliation** | Accounts > Bank Reconciliation | Import a statement file, *Auto-match* by amount, date within 3 days and reference; the statement shows what is left and checks the closing balance (TC-FIN-012) |
| 50 | **Payment mode on money** | Sell > Receipts and Buy > Payments > Record | Cash, UPI, cheque, NEFT, card with number and date; the cash and bank books show *Mode* and *Instrument* |
| 51 | **Cheque printing** | Buy > Payments > Print cheque, Cheque layout | CTS-2010 leaf with a per-bank offset |
| 52 | **Cash flow statement** | Accounts > All Accounts screens > Statements > Cash Flow | Operating, investing, financing; opening and closing cash; a line saying whether it reconciles (TC-FIN-018) |
| 53 | **Export to Tally** | Accounts > All Accounts screens > Books > Export to Tally | XML of a month's vouchers by source and a ledger per party (TC-FIN-020) |
| 54 | **Files on journals, receipts, payments** | Accounts > Journal Entries; Sell > Receipts; Buy > Payments | *Files* attaches a scanned bill and opens it again |
| 55 | **Customer and supplier as one party** | Masters > Customers > *Also a supplier*; Vendors > *Also a customer* | *Combined statement* with a running net; the set-off preselects the linked party |
| 56 | **Checks before closing, ageing bands** | Settings > Firm > Financial Years | Open items listed before a month closes, never refusing; ageing bands set per firm; *due today / this week* lists |
| 57 | **Bank details on bills** | Accounts > All Accounts screens > Tax filing > Bank Details | Printed on bills; account numbers masked to the last four except for those who pay |
| 58 | **TDS challans and 194Q** | Accounts > All Accounts screens > Tax filing > TDS Challans; Settings > Tax > TDS on Purchases (194Q) | A challan gathers the month's deductions and posts to the bank; the payment prefills a supplier's usual section and, past 50 lakh a year, 194Q at 0.1% on the excess |
| 59 | **GST checks before filing** | Accounts > All Accounts screens > Tax filing > GST checks | Findings by code with the document; a made-up GSTIN flagged for its check character is the check working (TC-COMP-021) |
| 60 | **Filed return kept, amendments** | Accounts > GST Returns | Marking filed freezes GSTR-1; later changes show as amendments (B2BA, CDNRA and so on); 3B carries the net |
| 61 | **Quarterly filers (QRMP)** | Settings > Tax > GST Documents > Return filing; Accounts > All Accounts screens > Tax filing > PMT-06 deposits | Quarterly GSTR-1 with IFF, deposits, the quarter's payment |
| 62 | **Rule 42** | Accounts > All Accounts screens > Tax filing > Rule 42 | Common credit reversal for a firm with exempt sales, monthly with year-end true-up |
| 63 | **GST warnings** | A credit note after 30 November; a bill after its credit's last date; a long document number | Each warns by name; document numbers stay within 16 characters |
| 64 | **Tax rule on the line** | An approved document line, tax detail | Names the rule that decided it |
| 65 | **Parties with no PAN** | Reports > Financial > Customer PAN check, Supplier PAN check | Missing or malformed PANs and PANs that do not match the GSTIN |

### Masters and configuration

| # | What | Where | What to look for |
| --- | --- | --- | --- |
| 66 | **Principals and brands** | Settings > Set up > Item lists > Principals, Brands | A principal linked to its supplier, brands under it; the brand picker on the product; analysis by them |
| 67 | **Price revisions** | Masters > Products > Price history | A new rate from a future date, history kept, read from its date |
| 68 | **Duplicate check and merge** | Masters > Customers or Vendors > New; select > Merge into... | A warning names the existing party by GSTIN, phone or name and does not block; merge moves every document and is refused if a locked year holds one (TC-MAST-012) |
| 69 | **Bank accounts and files on a customer** | Masters > Customers > a customer | Bank accounts masked to the last four; files kept |
| 70 | **Codes from a series** | Masters > Customers, Vendors, Products > New | A blank code reads *Blank: issued on save*; typing one still works |
| 71 | **The firm's own custom fields** | Settings > Firm > Custom Fields, Custom Field Rules | A firm administrator adds fields and mandatory rules without the platform |

### Reports, search and platform

| # | What | Where | What to look for |
| --- | --- | --- | --- |
| 72 | **Sales Analysis, the rest** | Sell > All Sell screens > Insight > Sales Analysis | Ordered basis, against last year, cost and margin for those who may see cost, saved layouts |
| 73 | **Audit trail search** | Settings > Platform > System > Audit Logs | One search box across who and what |
| 74 | **Faster search and reports** | Ctrl+K; Accounts > GST Returns; Sell > Customer Statements | Search answers at once on a large firm; GSTR-1, 3B and outstanding read faster |
| 75 | **Nightly clean-up** | On the server PC | Old login and log records are pruned after the nightly backup; no screen |

## Carried from the 1.1.0 notes

Everything in `docs/RELEASE_NOTES_1.1.0.md` (its rows 1 to 28 and the
2026-10-02 additions: e-invoice and e-way bills, batches and MRP, rule 37,
GSTR-2B, the quick check and the rest) is part of this build too. Test those
rows from the 1.1.0 notes if they were not tested on a 1.1.0 build. Their
menu paths there use the old menu: find a screen with **Ctrl+K**, or by the
rules above (Admin screens are now under Settings > Platform; Tax filing is
under Accounts > All Accounts screens).

## Fixed since 1.1.0

- A delivery note refused to ship stock its own order held (D-STK-16).
- The app loaded slowly and Quotations spun for about 40 seconds on a busy
  start; requests now queue before they hold a connection (D-PERF-2, #1058).
- A form closed before its custom fields arrived raised an error
  (D-DSK-CF-1, #1056).
- A bill of several delivery notes let a second and third note onto one bill
  with different salesmen (D-SELL-44).
- Places by PIN code and locality were slow on a large state (D-PERF-1).
- Favourites had no home in the new menu (D-UI-3, #1061).

## Known limits and what is not in it

- **Not built:** the 26Q FVU file, live e-invoice and e-way bill through NIC
  or a GSP, real WhatsApp and SMS sends, payment links, a bank's own
  payment-run layout, rule 43, licensing and the installer items
  (`docs/BACKLOG_BUILD_PLAN.md` section 5.1 says what unblocks each).
- In GST checks, *Open document* from a finding is not active yet.
- A kit inside a kit, and components priced on the bill, are not done.
- Barcode labels and cheque layouts need a real printer to judge alignment.
- *Rows per page* is not offered in My preferences.

**On every failure**: a screenshot, the newest file in
`C:\ProgramData\Agency Platform\logs\server`, and the version on the sign-in
screen (1.2.0).

## Upgrading

Setup backs up the database, then migrates every firm's store to the new
schema (revisions `20261002_0235` to `20261004_0299`: the backlog build's
tables for enquiries, approvals, transfers, repacking, kits, claims, landed
costs, rebates, reconciliation, cheques, custom fields and branch GSTINs, and
the date format default). Nothing existing changes how it prices or posts:
every new rule, limit, hold and approval is off until a firm switches it on or
sets a figure.

Two things change for everyone on the first sign-in:

- **Date format becomes dd-MM-yyyy**, because nobody could choose one before.
  Anyone can change it under My preferences (row 4).
- **Admin screens are under Settings > Platform.** The Admin area is gone from
  the bar, and the *Primary firm* menu entry is replaced by *Start in firm* in
  My preferences.

Set-up lists (Pricing, Territories & routes, Account structure, Party lists,
Item lists, Locations) have moved out of the drop-downs to Settings > Set up.
