# Agency Platform: application features guide

What the application does, screen by screen, in the order of the menu bar of
release 1.3.0. It explains what each screen is for, what has to be set up
before it, and what it changes in stock, the books and GST.

This is a **reference**, not a test script. To test the application step by
step, use the *QA functional walkthrough*; to install it, the *Installation
guide*.

Written 2026-09-27 for release 1.0.2; brought up to 1.1.0 on 2026-10-01;
GST documents, input credit and GSTR-2B added 2026-10-02; choosing batches
on a delivery note and reordering from sales added the same night; the tax
calendar on Home, *Rate includes GST* on orders and quotations, the purchase
order quantity picture, reverse-charge returns and debit notes to customers
brought in the same day; the rest of the batch work, column mapping on
imports, e-invoicing (route, notes, print gate, 30-day limit), e-way bills
without an IRN, rule 37, supplier IRNs and India Post places brought up to
#947 the same night; the backlog build of 2026-10-02/03 (enquiries, approval
levels, the bell, bank reconciliation, landed cost, stock transfer documents,
branch GSTINs, QRMP filing, Tally export and the rest) brought in on
2026-10-03; **brought up to 1.3.0 on 2026-10-04**: the light menu with
*All <Area> screens*, Settings > Set up and Platform, favourites, My
preferences, and the agency's own branding (sign-in screen, header, first-run
and Settings > Platform > Agency > Branding). Release 1.2.0 was never shipped,
so 1.3.0 is the first release after 1.1.0 and carries everything of both. Every
path below is written as the 1.3.0 menu shows it.

**Added on 2026-10-05, still release 1.3.0** (which has not been distributed):
the purchasing build (requests for quotation, rate contracts, supplier
schemes, imports and bills of entry, fixed assets, TDS 194C and 194J, TCS on a
purchase, *Paid now*, attachments, serials at receipt, PTR and PTS, the GST
purchase register and Payables by Month) and the selling build (walk-in cash
sale, service invoices, other charges, transporters, attachments, hold and
recall with counter shifts, the collection sheet and payment promises, customer
rebates, the GST sales register). **These were written here from the code and
its own tests; none has been through a full test suite, a CI run or a hand
test.** Where a label or a figure below is about one of them, read it as
*(confirm)*.

**How paths are written.** *Sell → Sales Invoices* is a screen in Sell's daily
drop-down. *Sell → All Sell screens → Documents → Enquiries* is a screen
behind **All Sell screens** at the foot of that drop-down, under its group
name. *Settings → Set up → Pricing → Price Levels* and *Settings → Platform →
People → Users* are on the Settings page behind the gear (12). **Ctrl+K**
finds any screen by name if you lose one.

## Contents

1. What the application is
2. Finding your way around (signing in, the header, the light menu,
   favourites, My preferences)
3. Setting up a firm
4. Home
5. Sell
6. Buy
7. Stock
8. Accounts
9. Masters
10. Reports
11. Platform: people, firms, the agency and the system
12. Settings (the gear): the Settings page, Set up and Platform
13. How a sale and a purchase reach the books
14. Roles: who can do what
15. Not in 1.3.0

---

# 1. What the application is

Agency Platform runs the day-to-day trade of a **distribution business**: a
wholesaler, a stockist or an agency that buys from suppliers, holds stock in
one or more warehouses, and sells on credit to shops and businesses through
salesmen. It covers:

- **Selling:** quotation, sales order, delivery, invoice, return and receipt,
  with price lists, promotions, credit limits and salesmen's commission.
- **Buying:** purchase order, goods receipt, supplier invoice, return and
  payment.
- **Stock:** what is on hand in each warehouse, what it is worth, and batches,
  serial numbers and expiry dates where the trade needs them.
- **Accounts:** the journal, ledgers, Trial Balance, Profit & Loss and
  Balance Sheet, kept up to date by the documents themselves.
- **GST:** tax worked out on every line, GSTR-1 and GSTR-3B read from the
  documents, TCS, and e-invoice registration.

**One installation serves several firms.** Each firm has its own customers,
stock, documents and books; a person can work in more than one firm and
switches between them. A firm's data can be kept in the shared database, in
a section of its own, or in a separate database.

**It wears the agency's name.** The agency's own name, tagline and logo lead
the sign-in screen and the top of every screen, given at install or under
Settings > Platform > Agency > Branding; the product's own name stays beside
them, quietly (2, 11.3).

**It adapts to the trade.** Each firm is given a *business profile*
(pharmacy, electronics, wholesale, general ...) that decides which features it
uses (expiry dates, serial numbers, drug licence ...), which menus it sees,
and which extra fields its products and customers carry.

**How it is installed.** One PC is the *server*: it holds the database and
runs the server program. Every other PC runs only the app and connects to the
server over the office network. The *Installation guide* explains both.

---

# 2. Finding your way around

## Signing in

The sign-in screen carries the **agency's** identity, not the product's. Above
the form sit the agency's **logo (or its initials), name and tagline**, given
at install or under *Settings → Platform → Agency → Branding* (11.3). Until the
agency has given them, or when the server cannot be reached, the screen shows
Agency Platform's own name; on a PC that has signed in before it shows what
that PC last saw, at once, without waiting for the server, and no error box
appears.

- **The strengths panel.** In a wide window a night-blue panel at the left
  cycles eight short statements of what the product does, about every eight
  seconds, with arrows and dots to move it by hand. It **stops for good once
  you type** in either box. Below 900 px wide it is not drawn and the card
  stands alone.
- **The product, quietly.** Agency Platform, *by* its company and tagline, in
  the foot of the card; the window title reads **Agency Platform - Sign in**;
  the status line shows the server state, the version and *Powered by Agency
  Platform*.
- **More help** opens a short list: the support phone, WhatsApp, hours, email
  and website (each shown only when it has been filled in; **none is filled in
  1.3.0, so none appears**), *Forgot your password? Your administrator resets
  it.*, and **Copy details for support**, which copies the product, version,
  server and this PC's name (never a password) to paste into a message.

## The screen

- **The header.** At the left of the top strip, before Home, the **agency's
  logo, name and tagline**, then the **name of the firm** being worked in as
  plain text (the firm switcher is unchanged). Clicking the agency opens Home.
  The Windows title bar reads **<agency> > <firm>**, or the agency alone when no
  firm is chosen. In a narrow window (below 820 px) only the logo is drawn; the
  tagline appears from 1280 px. The strip is no taller than before.
- **The product's own name.** At the right end of the status line, *Agency
  Platform 1.3.0 by* its company, with the same in a tooltip. Clicking it does
  nothing (*Help > About* is not built, 15).
- **The menu bar** across the top: *Home, Sell, Buy, Stock, Accounts, Masters,
  Reports*, the **bell** and the **gear** for Settings. There is no *Admin*
  area on the bar: administration is under Settings → Platform. A person sees
  only the menus and screens their role (and the firm's business profile)
  allows.
- **The user menu** at the top right, with **My preferences** (see below)
  beside the password and sign-out actions.
- **Tabs.** Every screen and every document opens as a tab under the menu
  bar, so several can stay open at once.
- **Ctrl+K** opens the search box: type part of a screen's name, or a
  customer, product or document number, and go straight to it. Screens you
  have starred (*Favourites*, below) come first.
- **The firm switcher** shows which firm you are working in; a person who
  belongs to several firms changes firm there.

## The light menu

Each of **Sell, Buy, Stock, Accounts** and **Masters** opens a short
drop-down of the screens used every day. At its foot **All <Area> screens (N)**
opens every screen of that area side by side, under its group names; *Back to
daily list* returns. Nothing is lost: the screens not in the daily list are
one click away, and Ctrl+K finds any of them. *Reports* has no short form (its
two screens are always shown).

| Area | The daily drop-down shows | Behind *All screens*, by group |
| --- | --- | --- |
| **Sell** | Quotations, Sales Orders, Delivery Notes, Sales Invoices, **Returns & notes** (opens Sales Returns, Credit Notes, Customer Debit Notes); under Money: Receipts, Customer Statements | Documents (Enquiries, Counter Shifts, Proforma, Approvals, Customer Rebates ...), Money (Collection Sheet, Payment Promises, Post-dated Cheques, Refunds ...), Incentives, Insight, Field sales |
| **Buy** | Purchase Orders, Goods Receipts, Purchase Invoices, **Returns & notes** (Purchase Returns, Debit Notes); under Money: Payments, Supplier Statements | Documents (Requisitions, Requests for quotation, Rate contracts, Supplier schemes, Bills of entry, Approvals, Quality Inspection ...), Money (Payment Runs, Payables by Month, Post-dated Cheques, Supplier Gifts, Supplier Rebates, Principal Claims, Landed Costs), Insight |
| **Stock** | Stock Summary, Stock Ledger, Stock Transfers, Physical Count; under Tracking: Batches, Expiry Monitor | Stock (Inventory, Stock Search, Transactions), Movements (Opening Stock, Adjustment Approvals, Repacking), Tracking (Lots, Serial Numbers), Data (Import, Export) |
| **Accounts** | Books: Journal Entries, Expenses, Ledgers, Bank Reconciliation; Statements: Trial Balance, Profit & Loss, Balance Sheet; Tax: GST Returns | Books (Chart of Accounts, Opening Balances, Party Adjustments, Contra Vouchers, Export to Tally), Fixed assets (Asset register, Asset classes, Depreciation runs, Income-tax block schedule), Statements (Cash Flow), Tax filing |
| **Masters** | Customers, Vendors, Products; under Organisation: Branches, Warehouses | Parties, Items, Organisation, Compliance (Trade Licences) |

The foot of Sell, Accounts and Masters also carries **SET UP IN SETTINGS**:
links to the Settings sections that hold the lists set up once and changed
rarely (Sell: Pricing, Territories & routes; Accounts: Account structure;
Masters: Party lists, Item lists, Locations). Those lists are no longer in the
drop-downs (12.3). The menu is built in the app from what the person may open;
opening it asks the server nothing.

## Favourites

- **Star a screen.** Point at any item in a drop-down and a star appears; click
  it to keep the screen, click the filled star to let it go.
- **Home → FAVOURITES** shows the person's own list as boxes. A cross appears
  on a box when it is pointed at and removes it; **drag** a box to reorder.
  Someone who has never starred a screen sees the common daily screens their
  role may open instead.
- **Ctrl+K** lists starred screens first.
- **The list follows the person**, not the PC: it is kept with their other
  preferences on the server, so signing in on another PC shows the same list.
  Starring five screens is one save (a second after the last click); if the
  save fails the app says so and puts the stars back.

## My preferences

Open it from the **user menu** (top right, *My preferences*) or from
*Settings → This PC and me → My Preferences*. It opens at once and is open to
everybody signed in, with or without a firm. It holds:

- **Start in firm**, the firm that opens first (offered only to a person with
  more than one firm; it replaces the old *Primary firm* menu entry).
- **First screen**: *the screen I was last on*, or any screen the person may
  open.
- **Theme**: Light, Dark or Follow Windows.
- **Text size**: Small, Default or Large. This one is **this PC only**.
- **Date format**: dd-MM-yyyy (the default), dd/MM/yyyy, yyyy-MM-dd or
  MM/dd/yyyy. Dates on the newer screens follow it.

Saving applies theme, text size and date format at once without reloading, and
makes one save of what changed. *Rows per page* is not offered (15). On the
first sign-in after an upgrade the date format becomes dd-MM-yyyy, because
nobody could choose one before.

## Lists

Every list screen has the same shape:

- **One line above the grid**: the title and its **(i)** (what the screen is
  for); counters that filter when clicked (*Draft 3*, *Approved 5*);
  **+ filter** for rarer filters; the search box; the **Period** on dated
  lists (this month, this quarter, the Indian financial year, a custom range;
  ◀ ▶ step to the previous or next period); **Columns**; Refresh; anything
  rarely used under **…**; and **+ New** last.
- **Pick a row** and a bar appears above the grid naming it (number,
  customer or supplier, status, total) with the steps that can be taken now:
  *Open, Edit, Approve, Post, Cancel, Print* ... A step that cannot be taken
  is not offered. The **×** clears the pick.
- **Double-click** a row to open it.
- **Columns** chooses which columns the list shows; the choice is remembered
  on that PC.
- The status bar at the bottom shows how many records there are and which
  page is shown.

**Keys:** Ctrl+N new, F2 edit the picked row, / search, Delete delete,
Ctrl+K find anything.

## Documents

A document (an order, an invoice, a receipt) opens on one full screen: the
header (customer or supplier, date, branch, warehouse), the lines, the
totals, and a side panel with details of the line you are on (stock on hand,
price, tax). **Prices, discounts and tax are worked out by the server as you
type**, so the totals on screen are the totals that will be saved.

## Statuses

Most documents start as **Draft**, which can be edited freely and changes
nothing outside itself. A draft is then **Approved** (or posted, dispatched,
received ... depending on the document), and from that point it has taken
effect: stock has moved, or the books have been written. An approved
document is not edited; it is **cancelled** or **reversed**, which undoes
what it did and keeps a record of both.

Every document keeps a **timeline** of each status it passed through, who
moved it and when.

## Printing

Documents print from the bar or from inside the document: invoices, delivery
notes, orders, receipts and the rest, each with the firm's name, address and
GST number on it.

---

# 3. Setting up a firm

**Before the first firm: the agency.** The first platform administrator to sign
in is asked to *Set up your agency* (11.3) -- its name, tagline and logo -- or
may skip it and do it later under *Settings → Platform → Agency → Branding*.
Nothing in the firm's own work depends on it.

A new firm goes through these steps once. **Settings (gear) → Platform → Firms
→ Firms → pick the firm → Set up** (the firm's *Set up panel*, not the *Set up*
section of the Settings page, 12.3) shows where the firm stands on each and does
several of them with one click.

| # | Step | Where | Why it matters |
| --- | --- | --- | --- |
| 1 | Create the firm: name, code, GST, PAN, address, financial-year start, and where its data is kept | Settings → Platform → Firms → Firms → + New | Where the data is kept cannot be changed later |
| 2 | Prepare its storage (only if it has a section or database of its own) | Set up panel → Provision storage | Nothing can be recorded for the firm until this is done |
| 3 | Give it a business profile | Set up panel → Business profile → Assign | Decides its features, menus and extra fields |
| 4 | **Open the books** | Set up panel → Open the books | Creates the chart of accounts, the current financial year with twelve monthly periods, and the accounts each document posts to. **Without it, no invoice, delivery or receipt can be approved** |
| 5 | Apply the GST template | Set up panel → Apply GST template | The tax rates and rules for Indian GST |
| 6 | Create a head office and a main warehouse | Set up panel → Create head office and main warehouse | Every document names a branch; all stock sits in a warehouse |
| 7 | Give people access | Settings → Platform → People → Users | A user account, a role, and membership of the firm |

Then the masters, in this order, because each needs the one before:

1. Branches and warehouses (beyond the first)
2. Units of measure (check the ones the profile gives)
3. Products
4. Customers and vendors
5. Territories and routes, if the firm sells by beat
6. Price lists and promotions

**Coming over from another tool.** Under the steps, *Opening balances* on
the Set up panel lists what to bring in, in order -- products, customers,
suppliers, the customers' and suppliers' unpaid bills, the opening trial
balance and opening stock -- ticks each as it fills, and names the screen for
the rest. Each comes **from a file**: a template made from the firm's own
records, *Check file* to list every problem by row and column, and an import
that posts all of it or none. A file from another program (Tally, Marg, Busy,
Excel) need not be retyped into the template: the import shows the file's own
headings beside the template column each is read as, guessed by name; change
any of them, leave a column *Not imported*, and *Save mapping as...* to pick
it from *Saved mappings* next time. `docs/GO_LIVE_GUIDE.md` walks it for the
firm's accountant.

**Document numbers need no setup.** Each kind of document starts its own
series on its first save (for example `SI/2026-2027/000001`), and the pattern
can be changed under **Settings → Firm → Numbering Series**.

---

# 4. Home

The first screen after signing in, cut to what the person may see:

- **Figures**: sales today, sales over the last 14 days (with a chart), what
  customers owe and how much of it is overdue, and items below their reorder
  level. Each opens the screen behind it.
- **Recent invoices.**
- **The bell** on the menu bar: everything that is waiting for the person
  signed in, in the firm they are working in, with a count. It lists orders
  and bills waiting to be approved, documents waiting for the next sign-off
  (see *Approval levels* in 5.2), purchase requisitions and stock adjustments
  waiting for approval, messages that failed to send, and stock at or below its
  reorder level. Click a line to open the screen that deals with it; reading
  one marks it read until the count changes. The bell looks again every minute.
- **To do**, each a count that opens the list behind it: orders to approve,
  orders to deliver, invoices overdue, purchase orders to receive, supplier
  bills overdue.
  Stock adds its own lines: below reorder level, out of stock, over the
  maximum level, batches near expiry, goods in transit between warehouses and
  count sheets still open.
- **Tax calendar** (for whoever may open GST Payment): for each of the last
  three finished months the firm traded in, **GSTR-1** (due the 11th),
  **GSTR-3B** (due the 20th, with the cash it works out to) and the **TCS
  deposit** (due the 7th, only for a month that collected any), each shown as
  due, late by so many days, or done. Filing happens on the government portal,
  so a return is closed by **Mark filed** (the date and the acknowledgement
  number); *Undo* withdraws it. GSTR-3B also closes by itself when the
  month's GST payment is recorded. A month that is closed drops off unless it
  is the latest. Rows open GST Returns or GST Payment.
- **Favourites**: the screens a person has starred, as boxes they can
  remove (the cross) and reorder (drag); a person who has starred none sees the
  common daily screens their role may open (see *Favourites* in 2).
- **Finish setting up**: while the agency's name and logo have not been given,
  a calm card under the greeting says so, with a **Set up your agency** button
  that opens the form (11.3). It is shown only to the person who may give them
  (a platform administrator, or someone with the platform-settings right), and
  it goes once they are given.

**Customise** chooses which of these a person sees.

---

# 5. Sell

## 5.1 The sales chain

| Document | What it is | What it changes outside itself |
| --- | --- | --- |
| **Quotation** | An offer to a customer | Nothing. It commits and reserves nothing |
| **Sales order** | What the customer has ordered | Once approved, **reserves the stock** so it is not sold twice |
| **Delivery note** | The goods leaving the warehouse | **Takes the stock out**, and books its cost (cost of goods sold) |
| **Sales invoice** | The bill | **Books the sale, the GST and what the customer owes** |
| **Sales return** | Goods coming back | **Puts the stock back** and credits the customer |
| **Receipt** | Money received | **Books the cash or bank**, and reduces what the customer owes |

Each step is raised **from** the one before, and carries its prices,
discounts and free goods forward unchanged, so an agreed price survives to
the invoice. A document can be continued in parts: an order of 100 can be
delivered as 60 now and 40 later, and the order shows how much is still
outstanding.

**A firm chooses which steps its people type.** A firm that does not use
quotations, or that invoices straight from the order, switches those steps
off (*Settings → Selling → Sales Stages*). The skipped documents are
still created automatically behind the scenes, so stock still leaves at
delivery and every report still adds up.

## 5.2 Documents

*Quotations, Sales Orders, Delivery Notes* and *Sales Invoices* are in the Sell
drop-down; **Returns & notes** opens Sales Returns, Credit Notes and Customer
Debit Notes; Enquiries, Proforma and Approvals are under *Sell → All Sell
screens → Documents*.

**Enquiries** (*Sell → All Sell screens → Documents → Enquiries*). A customer, or somebody who
is not yet a customer, asks about goods. Record who (name, company, phone,
email, city), where the lead came from, the salesman, the lines they asked
about, the value you expect, the date you expect to close and the date to
follow up. *Follow-ups due* lists what to ring today. **Convert** makes the
customer from the prospect's details (if they are not one already) and a
quotation from the lines, in one step; every line must name a product first.
Converting that quotation to an order marks the enquiry *won*. An enquiry that
goes nowhere is marked *lost* with a reason from a fixed list, and the lost
report counts and values them. Enquiries use the quotation's permissions.

**Quotations.** An offer with lines, prices and validity. Convert an
accepted quotation into a sales order in one step. *Reports: quotation
register, quotation conversion.*

**Sales Orders.** The heart of selling. Enter the customer and the lines;
the price, discount, promotion and tax are filled in as you type. Approving
reserves the stock and claims any promotion. An order can be put **on hold**
(the stock stays reserved; nothing more is delivered until the hold is
released) or cancelled (the reservation is released). The credit check runs
here: see 5.5.

**Reservations that lapse.** A firm can say how many days an approved order
keeps its stock reserved (*Settings → Selling → Sales Stages*). An order left
past that is marked *reservation lapsed* and its stock is released; *Reserve
again* takes it back if the stock is still there. Left blank, a reservation
never lapses.

**Approval levels.** A firm can ask for more than one signature on big
documents (*Settings → Firm → Approval Levels*): for sales orders, sales
invoices, purchase orders and purchase bills, up to three levels, each from an
amount upwards and each for a role. With no rule for a document's total,
nothing changes. Otherwise the levels are signed in order, one level per
person; *Approve* goes through only for someone who can sign the last open
level, and anyone else uses *Sign off* to record theirs. The last sign-off
approves the document. *Reject* needs a reason, clears the sign-offs and sends
a purchase order back to draft; several documents can be rejected together. A
sign-off counts while the total is no more than it was when signed. The
**Approvals** screens (*Sell → All Sell screens → Documents* and *Buy → All Buy
screens → Documents*) list what is
waiting. Platform administrators are not limited by the levels.

**Rate includes GST.** The order and the quotation carry the same switch the
counter bill has, starting from the firm's setting (*Settings → Selling →
Sales Stages*). Switched on, the rate and any discount *amount* typed on a
line are the shelf prices; the tax is taken back out to find the rate before
tax, and what was typed is kept so the editor shows it again. A quotation
typed at shelf prices becomes an order typed at them, so the customer pays
what was quoted. The quotation print shows both rates. Orders raised by a
conversion, a counter bill or an import start with it off.

**Delivery Notes.** Picked from an approved order, choosing the warehouse
(and batch or serial, where the product is tracked). Dispatching takes the
stock out. A delivery can be part of an order.

**Choosing batches.** For a batch-tracked product the side panel lists every
batch in the warehouse -- expiry, days left and how much this line can take --
already filled in earliest expiry first, so saving as it stands ships what it
always did. Type other quantities to take a later batch or split the line
across batches; expired batches are shown but cannot be chosen, and those near
expiry are marked. *Use earliest expiry* puts it back. If the chosen quantities
do not add up to the line, the panel says so and dispatch is refused. Passing
over an earlier batch is kept in the audit trail, and the challan prints one
row per batch with its expiry and MRP. A **counter bill** opens the same
picker for a batch-tracked line, and the batches chosen there are the ones the
bill's delivery note takes out.

When a customer asks for a particular batch, the sales order line can **pin**
it (*Pinned batch*): approval reserves that batch, and the delivery note starts
with it picked. A customer can carry a **minimum shelf life** (*Minimum shelf
life (days)* on the customer): earliest-expiry allocation passes over batches
with fewer days left, the picker marks them *Too short for customer*, and one
chosen by hand is refused or warned, as the firm sets. **Batch Rules**
(*Settings → Stock → Batch Rules*) say how many days count as near expiry (30), whether
taking a near-expiry batch or passing over an earlier one needs a reason at
dispatch, and that near-expiry stock may be sold below the price floor.

Each batch keeps the **MRP** printed on it (and a selling price), taken from
the goods receipt. No bill may charge more, tax included, than the lowest MRP
of the batches a line ships; a firm may switch on *Price from batch* so the
chosen batch's selling price fills the rate.

Every delivery note says **why the goods go out**: *Sale* (the default),
*Van or route sale*, *Supply on approval*, *Quantity not known*, *Job work* or
*Other* (with words). The reason prints on the challan. GST wants a sale's tax
invoice to exist **before** the goods leave, so dispatching a *Sale* note that
has no invoice yet follows the firm's choice in *Settings → Tax → GST
Documents*: **Warn** (the default: a message, then *Dispatch anyway* is
allowed and recorded), **Block**, or **Off**. **Dispatch and invoice** does
both in one step: the goods leave and the approved invoice exists at the same
moment. A van or route sale goes on a challan, with each shop invoiced at
delivery, unless the firm switches on *Van or route sales need the invoice
before the van leaves*.

**Sales Invoices.** Raised from an order or its deliveries, or on its own.
Approving books the sale, the GST (CGST and SGST within the state, IGST
outside it) and the amount the customer owes, with a due date from the
customer's payment terms. A document-level discount or freight charge is
spread across the lines so the tax is right.

**Several delivery notes on one bill.** The invoice editor asks for the
**customer** first (only customers with notes still to bill) and opens a tick
list of their delivery notes -- number, date, order and what is left to bill
before tax. A customer with one note has it ticked already. A note of another
branch, salesman, territory or route cannot be ticked beside those already
ticked, and the list says which field and which note it clashes with. The
supplier bill does the same with the **supplier** and their goods receipts
(branch is the only thing a receipt can clash on).

**Counter billing.** On a counter bill a barcode scanner (in keyboard mode)
adds the product, and scanning it again adds one more. *Received now* can be
split across tenders -- cash, UPI, card, bank transfer -- with the balance and
the change shown; each tender is recorded as its own receipt against the bill
(cash to the cash book, the rest through the bank). **Save & print (F9)**
saves, approves, prints on the thermal printer and opens the next bill.

**A UPI QR on the bill.** Type the firm's UPI ID (as `name@handle`) under
*Print settings* on the invoice screen, beside the bank details. A bill that
still owes money then prints *Scan to pay by UPI* with a QR carrying the payee,
the amount left and the bill number -- in the A4 footer and under the total on
the 80 mm roll. A part-paid bill asks only for the rest; a paid, draft or
cancelled bill, or a reference copy awaiting its IRN, prints none.

**Sending and sharing by hand.** On an approved invoice, *WhatsApp* saves the
PDF to Downloads, opens the folder with it selected and opens WhatsApp with
the firm's covering note (and the UPI line where it applies); the document's
timeline records *WhatsApp shared by hand*, never *sent*. It needs no account
or switch. *Send* (email) is on the quotation, order, customer statement,
receipt and purchase order screens as well as the invoice, and needs the
firm's messaging and email switched on (see 12). *Remind* on the Customer
Statement screen, or on an overdue invoice, sends the customer a **statement
of account** -- movements since the oldest unpaid bill, the closing balance,
the unpaid bills with days overdue and the UPI line -- by email or by WhatsApp
by hand. A customer who owes nothing, or marked *no reminders*, is refused by
name.

**Picking list and loading sheet.** Tick delivery notes on the list and choose
*Pick list* (what to take from where, for the warehouse) or *Loading sheet*
(what is on the vehicle); each is an A4 PDF.

**Sales Returns.** Goods coming back against an invoice. Approving puts the
stock back into the warehouse (or into a damaged or quarantine bucket) and
reduces what the customer owes, with the tax reversed. For a firm that
e-invoices, a completed return of billed goods is registered on the portal as
a credit note naming each invoice it returns goods from (see 8.3).

**Proforma.** A statement, in advance, of what an approved order will be
billed: for a customer who needs a document to arrange payment or credit
before the goods move. It changes nothing: no stock, no sale, no amount owed,
and it has its own number series, separate from tax invoices.

**Credit Notes.** Money credited to a customer **without goods coming
back**: a rate agreed after invoicing, a quality allowance, a billing error.
It always names the invoice it credits and reverses that invoice's GST in
proportion. (Goods coming back are a *sales return*, not a credit note.)
Credit notes and debit notes print in the invoice's layout, with *Against
invoice* and the reason in the head.

**Debit Notes.** More charged to a customer on a sale already invoiced: a
price raised after billing, a line under-billed, a charge added later. It
names the invoice and its lines and charges GST at the rate each line was
charged. What it adds is owed **on that invoice** -- Record Receipt shows the
invoice at its total plus the note, and the ageing ages it from the invoice's
due date. Drafting and approving are separate permissions; GSTR-1 declares it
as a debit note (type D) and GSTR-3B adds it to outward supplies.

### Added on 2026-10-05 (not yet tested by hand)

**Walk-in cash sale.** A counter sells to people who have no customer record.
On the counter bill choose **Walk-in**: the bill is made out to the firm's one
*Cash sale* customer (created the first time anybody asks for it), and the
buyer's **name** and **phone** can be typed on the bill; they print in place
of the customer's name. Rules: a walk-in bill must be **paid in full** before
it can be approved; it earns no loyalty points; it is an unregistered (B2C)
sale; a buyer's name is refused on a bill to any other customer. The *Cash
sale* customer cannot be deleted, given a credit limit or a GSTIN, or made
inactive.

**Service invoices.** A product whose type is *Service* (installation,
freight, a repair) is put on a quotation, order, delivery note, bill or
return like any other line and is billed with its SAC. It **moves no stock**:
nothing is reserved, nothing is dispatched, no cost of goods sold is booked
and it is never a back order. There is no separate screen; set the product's
type and its HSN / SAC under *Masters → Products*.

**Other charges on the bill.** Under **Other charges** on a sales bill, *Add
charge* takes a name (packing, handling, insurance), an amount before tax, a
tax profile and a SAC; up to ten. Each charge is taxed **at its own rate**,
by the profile it names, for the same buyer; a charge with no tax profile
carries no tax. The charges are in the bill's tax and total, print by name on
the bill, and reach GSTR-1, GSTR-3B, the GST sales register and the
e-invoice. In the books they are credited to *Other Charges Recovered*
(4050), not to sales. Freight and the older untaxed *additional charges* box
work as before. Not built: charges are not carried from the sales order, and
a credit note or a sales return credits lines only, so a charge cannot be
credited.

**Transporters and freight terms.** *Settings → Set up → Territories & routes
→ Transporters* keeps each carrier once: name, GSTIN (or the TRANSIN of an
unregistered carrier), phone and usual mode. On a delivery note, **Carrier
(master)** picks one and fills the note's transporter name, GSTIN and mode;
anything typed on the note wins, and changing the master later never rewrites
a note already raised. An inactive carrier is not offered. **Freight** on the
note says who pays the carrier (*Paid*, *To pay* or *To be billed*); it prints
on the challan and moves no money. The carrier of a note already raised
cannot be changed on screen.

**Attachments on sales documents.** The Quotations, Sales Orders, Delivery
Notes, Sales Invoices and Sales Returns lists each have an **Attachments**
action and a **Files** column. A file is a PDF, JPG or PNG of at most 10 MB
with an optional caption; each document keeps its own files, and removing one
is recorded in the audit trail. A person who may only view the document can
open its files; adding and deleting need the right to edit it.

**Hold and recall at the counter.** On the counter bill, **Hold (F8)** parks
the draft with an optional note and opens a fresh bill; **Recall** lists the
held bills and brings the chosen one back. A held bill can be edited and is
**never approved while held**; only a draft can be held. Holding changes
nothing in stock. The Sales Invoices list marks held bills.

**Counter Shifts** (*Sell → All Sell screens → Documents → Counter Shifts*,
and the strip above the scan field on the counter bill). A shift is one
cashier's till for a sitting:

1. **Open shift** with the opening float. One open shift per cashier.
2. Bill as usual. Expected cash is the float plus the **cash** tenders of the
   shift's bills whose receipts still stand; it is worked out each time it is
   read.
3. **Close shift** with the cash counted. The screen shows the shortage or
   excess as you type, warns of bills still on hold, and offers the shift
   report.

A count that differs from the expected cash posts the difference to *Cash
Short and Over* (6960); an exact count posts nothing. The cashier whose till
it is, or somebody who may approve sales, closes it. **Shifts are optional**:
a firm that opens none bills exactly as before. A bill paid at the counter
is counted in the open shift of the cashier who **made** it, whoever approves
it; the approver's own shift takes it only when the maker has none open. Not
built: a refund at the counter against a bill, a count by denomination, and
handing a shift to another cashier.

**Customer Rebates** (*Sell → All Sell screens → Documents → Customer
Rebates*). "2% back on the year's purchases over 10 lakh", promised to **one
customer or one customer group** for a period, with slabs. The turnover is
counted from the documents GSTR-1 counts (approved bills before tax, less
completed returns and approved credit notes, plus approved debit notes) and
the highest slab reached sets the rate on the whole of it. A group's
agreement adds up its members. Once the period is over the rebate is
**accrued** (booked as owed to the customer); an accrual nothing has settled
can be reversed and accrued again; and it is **settled against the customer's
bills** by a party adjustment of kind *Customer rebate*. One live agreement
covers a customer over any dates: a second whose period overlaps is refused,
its group's included. The statement (also *Reports → Financial → Customer
rebate statement*) shows the turnover, the slab reached, what is accrued,
settled and still to settle. **No GST is computed on a rebate.** The agreement
records whether it was *agreed before the sale*, for the firm's CA. Agreeing
and accruing need the right to approve sales; settling needs the right to
manage party adjustments, and **Settle against bills** is shown only to a
user who holds it. A Sales Manager does not, so a firm administrator or a
firm manager settles. Not built: settling by a GST credit note,
paying a rebate out in money, and accruing part-way through a period.

## 5.3 Money

*Receipts* and *Customer Statements* are in the Sell drop-down; Collection
Sheet, Payment Promises, Post-dated Cheques and Refunds are under *Sell → All
Sell screens → Money*.

**Collection Sheet and Payment Promises** (added 2026-10-05, not yet tested by
hand). The **Collection Sheet** lists every customer's open bills, opening
bills included, with days overdue, the latest promise and the **collector**,
sorted by collector, customer and due date; it can be narrowed to one
collector or route, or to overdue bills only, and printed as a PDF for the
round. The collector is set on the customer (**Collector**); where it is blank
the customer's account manager collects. From a row of the sheet, record a
**promise**: the day promised for, the amount and a note. **Payment Promises**
lists them by status:

- *pending* before its day, *due today* on it;
- *kept* when receipts dated from the day it was taken up to the day promised
  cover the amount;
- *broken* past that day without them;
- *withdrawn* when taken back, with a reason.

The status is worked out from the receipts every time, so reversing a receipt
un-keeps the promise it had kept. A promise **posts nothing** and is never
edited: a changed promise is withdrawn and a new one taken. It is refused on a
draft bill, on a bill that owes nothing and for more than the bill owes.
Reading needs the right to view receipts, recording the right to create them.
Not built: a promise for the account as a whole from the screen, the promise
on the customer statement, and a reminder raised from a broken promise.

**Receipts.** Money received from a customer, by cash, cheque, bank transfer
or UPI. A receipt is applied to one or more invoices; anything left over is
held **on account** (an advance) and applied to a later invoice from the bar
(*Apply to an invoice*). A receipt entered wrongly is **reversed**, never
edited, and the reversal puts everything back as it was. A receipt or a
payment can record **TDS deducted** with its section: the bill is settled in
full and the deduction is booked to TDS Receivable (or TDS Payable on the
buying side).

**Received now, on the bill.** Money taken at the counter is entered on the
sales invoice itself -- the amount, Cash or Bank, and a reference. Approving
the bill records it as a receipt against that bill, in the same step; more
than the bill is refused, because change is handed back rather than kept on
account.

**Approve many at once.** Sales and purchase invoices, delivery notes, credit
notes, sales and purchase returns: tick the rows and *Approve selected* or
*Cancel selected*. Each document is approved on its own; one that is refused
is listed with the reason while the rest go ahead, and *Retry the refused*
tries those again. Journal entries have *Post selected*.

**Payment mode.** Every receipt and payment records its mode (cash, cheque,
bank transfer, UPI) and the instrument date; the cash and bank books show
*Mode* and *Instrument*, and collections by mode read from it.

**Post-dated cheques** (*Sell → All Sell screens → Money → Post-dated Cheques*
for cheques received; *Buy → All Buy screens → Money → Post-dated Cheques* for
cheques issued). A cheque is
**held** (nothing posted), then **deposited** (or presented) on or after its
date -- which records the receipt or payment -- then **cleared**. A cheque that
**bounces** reverses the receipt or payment as of the day it came back, and
the bank's return charge can be posted and charged to the customer's account.
A held cheque can be cancelled. The list can show only those due to deposit
today.

**Early-payment discount and interest on overdue.** A customer can carry
*cash discount days and percent* (the credit policy holds the firm's default
terms); Record Receipt prefills the discount when the money arrives within the
days. The credit policy also carries an **overdue interest rate** and grace
days; the customer's statement shows the interest accrued, and *Raise interest
debit note* drafts a debit note for it (reason: late payment interest) for a
person who may manage customer debit notes.

**Refunds.** Money paid back to a customer, out of an advance or a credit.

**Customer Statements.** Two views:

- **Ageing**: every customer's outstanding split by how old it is (0–30,
  31–60, 61–90, over 90 days).
- **Statement**: double-click a customer for their account over a period:
  opening balance, every invoice, return, credit note and receipt in date
  order with a running balance, and the closing balance. Printable to send to
  the customer.
- **Combined statement**: where one business is both a customer and a supplier
  (see 9.1, *Also a supplier*), the statement merges both accounts in date
  order with a running net, and the set-off preselects the linked party.

The ageing **bands** are the firm's to choose (*Settings → Firm → Financial Years*),
not always 0-30, 31-60, 61-90 and over 90; the supplier ageing follows the same
bands. Invoices **due** today or in the week ahead are listed by the *due*
reports, on the selling side and the buying side.

## 5.4 Incentives

*Sell → All Sell screens → Incentives* (Commission, Targets).

**Commission.** What each salesman earns. *Rates* set the rules: a flat
percentage, or slabs that rise with the amount, on sales or on collections,
by product, category or customer. *Collected* shows what has been earned so
far. *Payouts* turn a period's earnings into a payout; approving it books
the commission owed, and paying it books the payment. The person who
approves a payout and the person who pays it can be kept apart.

**Targets.** What each salesman is expected to sell in a period, and how it
went. Targets over several months are judged together. Commission can pay a
bonus when a target is met.

## 5.5 Credit control

Each customer can carry a **credit limit** and **payment terms**. When an
order would take a customer over their limit the application warns, by
default from 80% of the limit. A firm can choose to **block** such orders
instead (*Settings → Selling → Credit Control*). Changing that policy is
kept to people who hold the customer-settings permission, not the sales
manager whose orders it limits.

**New outlets pending approval.** A firm can switch on *New outlets need
approval* (Sales Stages). A person without the customer-approve permission then
saves a new customer as **Pending approval**, and nothing can be billed to it
until the office approves it (one by one or in bulk, from the Customers list,
which filters on *Pending approval*).

## 5.6 Field sales

For a firm whose salesmen visit shops on fixed rounds:

- **Territories** (*Settings → Set up → Territories & routes*): the firm's own map of areas, for example
  Region → Zone → Area, each with a manager.
- **Route Types** and **Route Builder** (same section): a route is a round
  of shops in visiting order, valid for a period, assigned to a salesman.
- **Beat Plans**: which route a salesman walks on which day.
- **Call Lists**: today's calls for a salesman, drawn from the beat plan.
- **Coverage**: which shops were visited or ordered from, and which were
  missed.

Beat Plans, Call Lists and Coverage are under *Sell → All Sell screens → Field
sales*.

Orders, deliveries and invoices carry the salesman, route and territory, so
the reports can be read by any of them.

## 5.7 Pricing (Settings → Set up → Pricing)

*Price Lists, Price Levels, Promotions* and *Loyalty* are in the **Pricing**
section of *Settings → Set up*, reached from the **SET UP IN SETTINGS** link
at the foot of the Sell drop-down.

**Price Lists.** What a customer pays for a product before any offer. A price
list can apply to **one customer, one territory or the whole firm**, is valid
between dates, and can have **quantity breaks** (a lower price from 10, and
lower again from 50).

**Which discount applies** on a line, from strongest to weakest: an amount
typed on the line; a percentage typed on the line; a running promotion; the
price list; the customer's own standing discount; their customer group's
discount. A blank discount box takes the arrangement; a **0** typed in the
box refuses it.

**Price Levels** (*Settings → Set up → Pricing → Price Levels*). Named levels (for example
*Retail*, *Wholesale*, *Dealer*): the product's rate at each level is typed on
the product, and a level is given to a customer or to a customer group. A blank
unit price on an order or quotation is filled from the price list rate if there
is one, else the customer's level, else the product's own price; the price
list's quantity breaks apply.

**Promotions.** Offers the firm is running: a percentage or amount off, a
special price, **buy X get Y free**, for chosen products, categories,
customers or territories, between dates, optionally with a coupon code and a
limit on how many times it can be used. Several promotions can apply to one
line unless a promotion is marked as not combining with others. Beyond those:
**buy X get Y at a discount** (a percentage off the Y goods, with an optional
cap), a **combo price** (a fixed price for a set of products bought together,
counted in complete sets) and **bonus loyalty points** for a festival (the
largest multiplier that applies). An offer can also be limited by who is buying
-- the customer's number of orders, days since their last order -- and by
when: days of the week (weekends only, say) and a time-of-day window. Each offer
records what it has cost. *Reports: promotion performance, promotion claims,
coupon performance.*

**Coupon codes in bulk.** On the coupon screen, *Generate codes* mints up to
5,000 single-use codes at once (with a prefix, a description and a window), all
or none; *Export codes* writes the offer's codes and their uses to a CSV file.
**Copy with new dates...** on Promotions copies the picked offer as a draft
with a new window and code suffix (conditions and benefits kept, coupons not).
An offer can name the **principal** who funds it and its share, which feeds
*Principal Claims* (6.3).

When several offers match, the firm chooses (*Settings → Selling → Sales
Stages → When several offers match*): **combine** them, or give **the best
offer only** -- the single one worth most to the customer. A percentage offer
can have a limit (**20% off, up to 500**). *Try offers* (under "..." on
Promotions) shows what the offers do to any order on any date, before
launch, and why each one applied or did not. The printed bill names the
offers given and what the customer **saved**.

**Sales Analysis** (*Sell → All Sell screens → Insight → Sales Analysis*). Billed sales by any one or two of
day, week, month, quarter, year, product, category, customer, customer
group, salesman, territory, route and branch -- product by month, customer by
quarter -- with totals both ways, net of returns, and a click on any cell
for the invoices behind it.

**Loyalty.** Points or cashback: customers earn on what they buy and spend
the balance against a later bill. Points can expire. The scheme (earn rate,
value of a point, expiry) is set per firm.

---

# 6. Buy

## 6.1 The buying chain

| Document | What it is | What it changes outside itself |
| --- | --- | --- |
| **Purchase order** | What the firm has ordered from a supplier | Nothing. It records an intention |
| **Goods receipt** | The goods arriving | **Puts the stock in**, and books it |
| **Purchase invoice** | The supplier's bill | **Books what the firm owes the supplier, and the input GST** |
| **Purchase return** | Goods sent back | **Takes the stock back out**, and reduces what is owed |
| **Payment** | Money paid to the supplier | **Books the cash or bank**, and reduces what is owed |

## 6.2 Documents

*Purchase Orders, Goods Receipts* and *Purchase Invoices* are in the Buy
drop-down; **Returns & notes** opens Purchase Returns and Debit Notes;
Requisitions, Requests for quotation, Rate contracts, Supplier schemes, Bills
of entry, Approvals and Quality Inspection are under *Buy → All Buy screens →
Documents*.

**Requisitions** (*Buy → All Buy screens → Documents → Requisitions*). An indent: someone asks
for goods, a manager approves, and an approved requisition is converted into a
purchase order. *Raise requisition* on *Below reorder level* (see 6.3) makes
them from the shortages.

**Purchase Orders.** Enter the supplier and the lines. An order is
**approved** before anything can be received against it, and approval can be
kept to a purchase manager. Receiving moves the order to *part received* and
then *received* on its own; nobody sets that by hand. Once an order has left
draft, the side panel of the selected line shows what was **received,
rejected, returned and billed**, what is still **pending** and what is still
**to bill** (the figures behind it also carry accepted and damaged), worked out
afresh from the live receipts, bills and returns; only approved bills count as
billed. The order carries a **billing status** (*Not billed*, *Part billed*,
*Billed*) and a **Complete** flag beside its status, so billing never
overwrites how far receiving got.

**Amending an order.** *Amend* on an approved purchase order changes it and
keeps the earlier version; *Revisions* lists every version, and the print
carries the amendment.

**Supplier rates.** A supplier can carry a **standing discount** and its own
price lists (a price list can be scoped to a supplier). On the order, a blank
price and discount are filled from the supplier's price list, then the
supplier's **catalogue** (the *Catalogue* tab on the supplier: their code for
each product, price, pack size, minimum order, order multiple and lead time,
also loadable from a file), then the product's purchase price; a product price
with an effective date (9.2) is used from its date. Under *Settings → Buying →
Purchase Settings* the firm chooses what happens to a quantity that is not a
multiple of the supplier's order multiple; the editor shows the hint with *Use
N*. The expected delivery date starts from the supplier's average **lead time**,
which the supplier screen summarises, and the sales-based reorder point uses
it too.

**Budgets.** *Settings → Buying → Purchase Budgets* sets an amount for a
period; the order shows how much of the budget it would use, and approving an
order over budget follows the firm's policy (warn or block) unless the approver
holds the over-budget permission.

**Goods Receipts.** Record what actually arrived against an order: the
quantity accepted, damaged and rejected, into which warehouse, with the batch
number and expiry date or serial numbers where the product is tracked.
Completing the receipt puts the accepted stock in and values it. The receipt
records the **e-way bill** the goods came on (*E-way bill no.* and date, or
*Record e-way bill* once it is completed); a receipt worth more than the
firm's e-way bill limit without one is warned about -- for an unregistered
supplier, as the buyer's to raise.

**Quality inspection.** A product or category marked *Inspect on receipt* is
received into **quarantine**: owned and valued, but not for sale. *Buy → All Buy screens →
Documents → Quality Inspection* lists the lines waiting; recording the result
releases what passes to stock, and what is rejected is written off at once or
left in quarantine for a purchase return. Cancelling the receipt releases the
hold.

**Free goods and gifts.** A product can be marked *free issue only*; a receipt
line can name the **scheme** the free goods came under, and a write-off can name
the customer they were given to (reasons *Free to customer* and *Sample*).
*Free goods* in the operational reports adds it up. Gifts from a supplier are
recorded in the **Supplier Gifts** register (*Buy → All Buy screens → Money*): each is booked as
income (or as drawings, if the owner kept it), and the **194R summary** shows
the value by supplier.

**Purchase Invoices.** The supplier's bill, matched to the receipt. Approving
books the amount owed with a due date, and the input GST the firm can claim.

Not all GST paid can be claimed. Each bill line has **Input credit**:
*Eligible*, *Blocked* (cars, food and catering, personal use, gifts --
section 17(5)) or *Ineligible*. It comes from the line, else from the
product's own setting, else from a tax rule. Tax that cannot be claimed is
booked to **Input Tax Not Claimable** (account 5450) as a cost, never as
input credit, and GSTR-3B shows it as the law asks.

A supplier marked **Supplier e-invoices** must put an IRN on its bills. The
bill records the **supplier's IRN** from the QR code (*Record IRN* works on an
approved bill too), and warns when that supplier's bill has none (a firm may
switch the warning off) or when another bill already carries the same IRN.
It warns and never refuses: the firm still owes the money.

**Bill matching tolerances.** Under *Settings → Buying → Purchase Settings →
Bill matching* a firm sets how far a bill's price may differ from the order (a
percentage and an amount). A bill outside the tolerance is held: only a person
who holds the over-tolerance approval permission can approve it, singly or in
bulk.

What a **supplier** is under GST is set on the supplier: *Regular*,
*Composition*, *Unregistered*, *Overseas* or *SEZ*. A supplier marked
Composition, Unregistered or Overseas charges no GST, so their bills carry
none and claim none (reverse charge aside). A supplier with no type set is
taxed by the firm's tax rules, as before.

**Purchase Returns.** Goods sent back to the supplier (damaged, expired,
wrong). Approving takes the stock out and reduces what is owed. A return says
what the supplier gives back: **Credit** (set against the next bill, the
default), **Replacement** (the order is owed the goods again and the next
receipt takes them in) or **Refund** (the supplier pays the money back:
*Payments → Supplier refunds → Record refund*). A return off a bill already
paid becomes a supplier credit for what the bill can no longer absorb. A
return or debit note off a bill charged under **reverse charge** takes the
matching share of that reverse charge (and the input credit it raised) off
too, so the firm does not go on paying tax on goods it no longer holds.

**Debit Notes** to a supplier claim money back on a bill. A claim larger than
what the bill still owes -- the bill is already paid -- is not refused: the
excess becomes a **supplier credit**, set against the next bill or refunded,
as a return off a paid bill does.

### Added on 2026-10-05 (not yet tested by hand)

**Requests for quotation** (*Buy → All Buy screens → Documents → Requests for
quotation*). Ask several suppliers for their prices and order from the best.

1. New: the products and quantities, and the suppliers invited. An approved
   requisition has a **Create RFQ** action that starts one from its lines.
2. **Send**, then **Enter quotes**, one supplier at a time: a rate, a discount,
   a lead time per line.
3. **Compare**: every supplier's rate after discount and before tax, cheapest
   first, the lowest marked. Choose one quote per line; a choice that is not
   the lowest needs a reason.
4. **Raise orders**: one draft purchase order per chosen supplier, at the
   quoted rates, and the RFQ closes.

A supplier who was not invited cannot quote. Raising orders needs the right to
create purchase orders as well as to manage RFQs. Emailing the RFQ to the
suppliers is not built.

**Rate contracts** (*Buy → All Buy screens → Documents → Rate contracts*). A
rate, a discount and optionally a quantity agreed with one supplier for a
period. **Approve** makes it active. From then on a purchase order line for
that supplier with the price left blank takes the contract's rate, ahead of
the supplier's price list, and shows a mark on its rate. The contract window
shows what has been **drawn** (ordered on approved orders) and what
**remains** per line; an order that takes a contract past its quantity shows
a warning and is **never refused**. An active contract past its last day reads
*Expired* and prices nothing. Two active contracts with one supplier for the
same product may not overlap. **Close**, **Cancel** (with a reason) and
**Releases** (the orders priced from it) are on the same window.

**Supplier schemes** (*Buy → All Buy screens → Documents → Supplier schemes*).
"Buy 10, get 2", for one supplier or for every supplier of the product, for a
period. On a purchase order a scheme of the **same product** fills the line's
**Free** box where it was left blank, and the side panel reads *Scheme 10+2
applied*; a figure you type is kept, and a typed 0 refuses the scheme. A
scheme that gives **another product** adds that product as a line of its own
with nothing charged, once. The receipt and the bill inherit the free goods.
A supplier's own scheme beats one for every supplier; two schemes of the same
reach on one product may not overlap in dates.

**Serial numbers at receipt.** On a goods receipt line for a serial-tracked
product, the **Serials** cell opens a box to type, paste or scan the numbers,
or **Fill a range** (prefix, start, count, width). A draft may be short; to
complete the receipt there must be one serial per unit received, free units
included. A serial already in the firm is refused. Completing creates the
units in the receipt's warehouse and starts each unit's trail; cancelling the
receipt removes them unless one has moved. A purchase return names the units
going back.

**PTR and PTS per batch** (firms on the Pharmacy, Food or Wholesale profile
with the feature on). A goods receipt line for a batch takes the *price to
retailer* and *price to stockist* beside the MRP; a batch number is required
and neither may be above the MRP. The customer carries a **Trade class**
(Retailer, Stockist, Other). On a sale from that batch a blank price takes
PTR for a retailer and PTS for a stockist, after a typed price and the price
list. The price box is never filled in for you. A firm without the feature
sees none of this.

**Attachments on bills and receipts.** The purchase bill and goods receipt
windows have an **Attachments** button (add, open, save, delete) and their
lists a **Files** column: the supplier's bill as a PDF, JPG or PNG of at most
10 MB. Reading the bill into a draft (OCR) is not built.

**Paid now: a cash purchase in one step.** A person who may record payments
sees a **Paid now** tick in the bill's Approve dialog: method, amount
(blank pays the full bill), reference and date. **Approve and pay** approves
the bill and records an ordinary payment against it together. More than the
bill owes is refused; reversing the payment later leaves the bill approved
and owing.

**TDS under 194C and 194J.** The supplier carries its **Usual TDS section**
(with *Individual / HUF* for 194C and *Technical services (2%)* for 194J), and
the thresholds and rates are under *Settings → Tax → TDS on purchases (194Q,
194C, 194J)*. When a bill is approved the dialog shows the deduction worked
out for it, with a box to override it; approval posts it to *TDS Payable* and
the supplier is owed the bill less the TDS. Money paid ahead of any bill
proposes the deduction on the payment instead, and it is deducted once.
Challans and the TDS registers carry these bills.

**TCS charged by a supplier.** A purchase bill has a **TCS rate** and a **TCS
amount**: a rate alone is worked on the bill's total including GST, and a
typed amount wins. It is outside GST. Approval books it to *TCS Receivable*
(1430), a tax asset to claim, and the supplier is owed the bill plus the TCS.
*Reports → Financial → TCS paid to suppliers* totals it by quarter.

**Send the order by WhatsApp.** **Send** on a purchase order offers WhatsApp
beside Email once the firm has switched messaging and the WhatsApp channel on
and named the template for *Purchase order sent to the supplier* (*Settings →
Firm → Messaging*). It goes to the supplier's mobile unless a number is typed,
and the order is marked sent. The message is the template only; the PDF is not
attached.

**Imports: a supplier in another currency.** Give the supplier a **Currency**
(three letters; blank is rupees). The bill window then starts in that
currency and asks for the **rate**; lines and totals are typed in the
currency and shown with their rupee equivalent, and the books are posted in
rupees at that rate. Such a bill offers no TCS, TDS or *Paid now*. Pay it
from *Payments* in its own currency at the day's rate: the difference from
the bill's rate posts to *Exchange Gain/Loss*. *Revalue foreign payables* on
*Journal Entries* books the unrealised difference on what is still owed at a
period end and reverses it the next day. **An import goes through the whole
chain.** The purchase order has **Currency** and, for any currency but
rupees, a required **Exchange rate**; a new order starts in the supplier's
currency. The receipt values the stock in rupees at the order's rate. The
bill is in the order's currency: a bill in any other is refused, naming the
order, and a bill at another rate posts only the rate difference to price
variance. Neither the currency nor the rate of an order can change once a
receipt has been completed against it. A bill typed alone (the order and
receipt stages off) works as before. Not yet converted: a debit note or a
purchase return against a foreign-currency bill (D-BUY-41), and GSTR-2B
matching, rule 37 and rule 42 for such a bill (D-CMP-23).

**Bills of entry** (*Buy → All Buy screens → Documents → Bills of entry*).
The customs document for an import. Link the bills and receipts it covers;
per line give the assessable value and the rates or amounts of basic customs
duty, social welfare surcharge (10% of the duty unless typed), IGST and cess;
a typed amount beats its rate. **Post** adds the duty and surcharge to the
cost of the goods received (to *Customs Duty* expense for a line no receipt
carries), claims the IGST as input credit, and books what is owed to *Customs
Duty Payable*. The receipts must be completed first. **Cancel** (with a
reason) reverses it. GSTR-3B shows the IGST in 4(A)(1) *Import of goods*. Not
built: the Bill of Entry in the GST purchase register and against GSTR-2B.

**Capital goods.** A bill line has a **Capital goods** tick and, with it, a
required **asset class**. At approval the line raises a fixed asset (8.1)
instead of stock, and its GST is claimed in full. A firm that orders and
receives first ticks **Capital goods** on the purchase order line (or on the
receipt line): the receipt then brings the line in without entering stock,
and the bill line for it is capital goods and cannot be unticked. Only a
line a receipt has already taken **into stock** is refused at the bill: untick
it, or cancel the receipt and mark the line on the order or the receipt.

## 6.3 Money and insight

*Payments* and *Supplier Statements* are in the Buy drop-down; the rest of
Money (Payment Runs, Payables by Month, Post-dated Cheques, Supplier Gifts, Supplier Rebates,
Principal Claims, Landed Costs) and Insight (Purchase Dashboard, Purchase
Analysis, Rate Trend) are under *Buy → All Buy screens*.

**Payments.** Money paid to a supplier, applied to one or more of their
invoices; any excess is held as an advance. Reversed, never edited, like a
receipt.

A supplier's **credit** (from a return or a debit note on a paid bill) can be
set against a supplier's **opening bill** as well as a purchase bill.

**Payment Runs** (*Buy → All Buy screens → Money → Payment Runs*). Proposes the supplier bills
falling due by a date; a draft run holds the bills and amounts chosen (never
more than a bill still owes). Approving -- a separate permission the cashier
does not hold -- records one payment per supplier by bank transfer, all or
none, and *Bank file* writes a generic NEFT upload (one row per supplier, from
its primary bank account). A layout for the firm's own bank is not built.

**Printing a cheque.** *Print cheque* on a payment made by cheque prints on the
leaf (CTS-2010 style: date boxes, payee, amount in words, A/c payee crossing);
*Cheque layout* moves the print to suit the bank's leaf, kept per bank account.
A cash or non-cheque payment, or a reversed one, is refused.

**Supplier Rebates** (*Buy → All Buy screens → Money → Supplier Rebates*). A volume rebate agreed
with a supplier: set up the agreement, *accrue* what is earned (booked as a
receivable from the supplier), reverse an accrual that was wrong, and settle it
with a supplier adjustment of kind *Supplier rebate* rather than a debit note
(which must name one bill).

Customer rebates, the same thing the other way round, are under Sell (5.2).

**Payables by Month** (*Buy → All Buy screens → Money → Payables by Month*;
added 2026-10-05, not yet tested by hand). What each supplier is owed, month
by month, with *Older*, *Credits* (advances and supplier credit) and
*Outstanding*, a total row, a chart and a check that the total agrees with the
payables account in the books. A switch shows what was **paid** instead of
what is **owed**, and a filter narrows to a branch.

**Principal Claims** (*Buy → All Buy screens → Money → Principal Claims*). What a principal (the
brand owner) owes the firm: for each principal and period it gathers, once
each, the redemptions of the schemes the principal funds (at its share), expiry
write-offs of its products, and damaged goods on completed sales returns.
*Preview* shows it, *Raise* books it as a claim receivable, *Print* gives the
claim, and it is settled by the principal's credit note or by its payment into
a cash or bank account; its status (raised, part settled, settled) follows.
Cancelling a claim frees its sources to be claimed again.

**Landed Costs** (*Buy → All Buy screens → Money → Landed Costs*). Freight, duty and handling
that belong to goods already received. Name the completed receipts and the
charges (each with its own bill), choose to spread them by value, quantity or
weight, and post. The share for goods still on hand adds to their value (so the
stock is worth what it really cost); the share for goods already sold goes to
cost of goods sold. Cancelling reverses it.

**Purchase Dashboard.** What is on order, what is waiting to be received,
what is overdue, and spend by supplier.

**Purchase Analysis** (*Buy → All Buy screens → Insight*). The same as Sales Analysis, for the
suppliers' bills: by supplier, supplier category, product, category, branch
and period.

**Purchase price variance** (*Reports → Financial*). A bill line charged at a
different rate from its receipt, with both rates and the difference.

**Below reorder level** (*Reports → Operational*, and *Purchase Orders → "..."
→ Below reorder level...* to raise draft orders, one per supplier). What is
short in each warehouse, what is already on order, who supplies it and
how much to order -- the product's **preferred supplier** where one is set,
else the supplier last billed. Under *Settings → Buying → Purchase Settings → Reorder
planning* a firm chooses **typed levels** (order up to the reorder and maximum
levels on each product) or **from sales**: each product's average daily sales
over the last 90 days sets its level -- reorder when stock falls to 14 days'
worth (7 days' lead time plus 7 safety), order up to 30 days more, in whole
units. A level typed on a product still wins. The report shows which basis each
row used and the daily average.

Every buying list names the **supplier** in a column and on the bar, and is
searched by supplier name.

**Supplier performance** (*Reports*): by supplier, the share of receipts on
time, the quantity rejected, returned and left short, and a **supplier price
trend**. People can also **rate** a supplier (the *Ratings* tab on the
supplier): scores from 1 to 5 on several criteria, one live rating per person,
earlier ones kept as history.

---

# 7. Stock

Most stock moves because of a document: a goods receipt brings it in, a
delivery note takes it out, a return brings it back. The Stock menu shows
what is there, and handles the movements a firm makes about its stock rather
than about a trade.

## 7.1 Seeing the stock

*Stock Summary* and *Stock Ledger* are in the Stock drop-down; *Inventory,
Stock Search* and *Transactions* are under *Stock → All Stock screens →
Stock*.

- **Inventory**: what is on hand, by product and warehouse: available,
  reserved for orders, damaged, quarantined, with the quantity **incoming**
  (approved purchase orders not yet received) and **outgoing** (approved sales
  orders not yet shipped) and the projected quantity. The movements below start
  here.
- **Stock Summary**: the totals at a glance: items, value, items below
  reorder level, out of stock.
- **Stock Search**: find a product and see where it is held.
- **Stock Ledger**: every movement of a product, in date order, with the
  running quantity and value: how the stock got to what it is.
- **Transactions**: every stock movement of every kind, with the document
  behind it.

Stock is valued at **average cost**, and every movement also writes to the
books, so the stock account in the Balance Sheet matches the stock screens.

## 7.2 Movements

*Stock Transfers* and *Physical Count* are in the Stock drop-down; Opening
Stock, Adjustment Approvals and Repacking are under *Stock → All Stock screens
→ Movements*.

From the Inventory screen, each its own action:

- **Adjust**: correct a quantity up or down, with a reason.
- **Transfer**: move stock between warehouses or branches.
- **Write off**: remove stock that is lost, broken or expired.
- **Quarantine**: set stock aside so it cannot be sold, and release it later.

An adjustment or write-off names a reason from the firm's own list (*Settings →
Stock → Adjustment Reasons*); *internal use*, *staff* and *display or samples*
are posted to their own expense accounts, while damage, expiry and loss stay on
Inventory Adjustment. **Large adjustments need approval:** under *Settings →
Stock → Adjustment Limits* each role has a limit; above it the post is refused
and *Submit for approval* sends it to **Adjustment Approvals** (*Stock → All Stock
screens → Movements*), where someone with a higher limit approves or rejects it, singly
or in bulk. Files (a photo, a note) can be attached to an adjustment, a
write-off, a transfer or a count sheet as evidence.

And two documents:

- **Opening Stock**: the stock a firm holds on its first day in the
  application, entered by hand or imported from Excel, then posted once.
  Posting values it against the opening balance in the books.
- **Physical Count**: a stock-take. Open a count for a warehouse, record what
  was found line by line (over hours, by several people if needed; the list
  shows how many lines are counted), then post it: every difference becomes
  an adjustment. **Count plans** choose what to count and how often -- a
  warehouse, a bin or an ABC class (fast sellers more often) -- draw the sheet,
  can hide the system quantity on a **blind sheet**, and limit what a counter
  may post.
- **Stock Transfers** (*Stock → Stock Transfers*). A move between branches or
  warehouses as a document: *Dispatch* takes the goods off the source at their
  cost and holds them **in transit** (still the firm's, so the books do not
  move); *Receive* names, line by line, what arrived and what of it was damaged
  (damaged goods arrive blocked from sale; what never arrived is written off).
  A challan prints without values. A draft or dispatched transfer can be
  cancelled; a received one is final. A transfer between two branches with
  different GSTINs is refused: bill it as a sale to the other branch (9.3). The
  quick *Transfer* action above stays for a shift within a building.
- **Repacking** (*Stock → All Stock screens → Movements → Repacking*). Break a bulk product into smaller packs
  (or the reverse); the output carries the cost of what went in.
- **Kits and combo packs.** A product of type bundle is a *kit* with
  components. *Assemble* and *Disassemble* turn components into kits and back;
  a kit is stocked and sold as itself, and a delivery that is short of
  assembled kits assembles the shortfall from the components.

## 7.3 Tracking

*Batches* and *Expiry Monitor* are in the Stock drop-down; *Lots* and *Serial
Numbers* are under *Stock → All Stock screens → Tracking*.

Used when the firm's business profile switches them on:

- **Batches** and **Lots**: stock held by batch, with manufacturing and
  expiry dates; deliveries pick the batch earliest expiry first, or the
  batches chosen on the delivery note.
- **Serial Numbers**: each unit held by its serial number, from receipt to
  sale, with warranty where it applies.
- **Expiry Monitor**: batches that have expired or expire soon, and their
  value.

Each product can set its own **expiry rules** (days before expiry that it may
no longer be sold, the alert window, and the days to return it to the
supplier) and a **batch issue rule** (earliest expiry first, first in first
out, or picked by hand); the Expiry Monitor offers *Return to supplier now* for
what is due back. A product with a **shelf life** in days has its expiry worked
out from the manufacturing date typed on a receipt line. A product can be
**discontinued** (it still sells until the stock is gone, but is not bought or
suggested for reorder) or **not for sale** (refused on every new sales line).

**Returned goods held until checked.** *Settings → Stock → Batch Rules* can
send the sellable part of a sales return into quarantine; *Release* on the
stock row puts checked goods on the shelf.

**Barcode labels.** *Print labels* on the product and goods receipt lists
prints Code 128 labels (name, barcode, MRP, price, batch and expiry) on A4
sheets of 65 or 24, or a 50 x 25 mm roll, skipping the positions already used
on a part sheet.

## 7.4 Data

*Stock → All Stock screens → Data*.

- **Import**: load stock (opening balances, adjustments) from an Excel file,
  checked before anything is posted.
- **Export**: the stock to Excel.

---

# 8. Accounts

The books are kept **by the documents themselves**: every invoice, delivery,
receipt, payment, return and stock movement writes its own journal entry when
it is approved. Nobody has to post sales or purchases by hand; the
accountant's work is the entries no document makes (rent, salaries,
adjustments) and reading the statements.

## 8.1 Books

*Journal Entries, Expenses, Ledgers* and *Bank Reconciliation* are in the
Accounts drop-down; Chart of Accounts, Opening Balances, Party Adjustments,
Contra Vouchers and Export to Tally are under *Accounts → All Accounts screens
→ Books*.

**Chart of Accounts.** The accounts, in groups: assets, liabilities, equity,
income and expenses. Opening the books gives a firm a standard chart for a
distribution business, including an **Indirect Expenses** group with Rent,
Salaries and Wages, Electricity, Telephone and Internet, Travel and
Conveyance, Office and General Expenses, Repairs and Maintenance, and Bank
Charges. Accounts can be added.

**Journal Entries.** Every entry, whoever or whatever made it. Filter by
*Posted by* (sales invoices, receipts, deliveries ... or by hand) and by
period. A hand-written entry is a draft until it is **posted**; debits must
equal credits. An entry a document made is reversed by reversing the
document, not the entry. Several drafts can be posted at once with *Post
selected*.

**Expenses.** Rent, fuel, salaries and other running costs: the expense
account, the amount, the cash or bank account it was paid from, and TDS where it was deducted. Saving
posts it to the journal; an expense dated in a locked year is refused.

**Ledgers.** One account's movements over a period, with the opening and
closing balance.

**Bank Reconciliation** (*Accounts → Bank Reconciliation*). Import the bank's statement from
a file (with the same column mapping as other imports; a line already imported
on the account is refused). *Auto-match* pairs each line with the book entry of
the same amount within three days and the same reference (cheque number or
UTR); anything doubtful is left for a person to match by hand, a line can match
several entries that add up to it, and a match can be undone. The
*reconciliation statement* as on a date shows the books, the unmatched items
and the statement balance, checked against the balance printed on the
statement. Unmatched lines of a month are listed when the month is closed (8.4).

**Party Adjustments.** A customer's or supplier's balance cleared without money
and without a tax effect: a *customer write-off* (to bad debts), a *supplier
write-back* or a *set-off* between what a business owes and is owed. A draft
changes nothing; approving posts the journal and moves the balance; it is
cancelled, never edited, and always carries a reason.

**Contra Vouchers.** Money moved between the firm's own cash and bank accounts
(cash paid into the bank, a transfer between banks), numbered in its own
series, instead of a hand journal.

**Files on entries.** *Files* on a journal entry, a receipt or a payment keeps
the bill or letter behind it.

**Export to Tally** (*Accounts → All Accounts screens → Books → Export to Tally*). Writes the period's posted vouchers
as a TallyPrime import file: each is typed by what made it (Sales, Purchase,
Credit Note, Debit Note, Contra, Receipt, Payment, else Journal), with a ledger
per customer and supplier under Sundry Debtors or Creditors. The *mappings* give
each account the name and group it has in the firm's Tally. Try a sample in
Tally before relying on it.

**Bank Details** (*Accounts → All Accounts screens → Tax filing → Bank Details*). The firm's bank
accounts for its bills, one marked *print on documents*: its details print in
the bank block of every document that has one. Only people who may manage
accounts or record payments see the full number; others see the last four.

**Fixed assets** (*Accounts → All Accounts screens → Fixed assets*; added
2026-10-05, not yet tested by hand). Four screens:

- **Asset classes**: how each kind of asset is depreciated. Straight line or
  written down value, by a rate or a useful life, a residual percentage, and
  the Income-tax block rate. Five classes come with the firm: plant,
  furniture, computers, vehicles and office equipment.
- **Asset register**: each asset with its cost, accumulated depreciation and
  net book value. An asset arrives from a purchase bill line ticked *Capital
  goods* (6.2), or is typed by hand for an opening asset (which posts
  nothing). Each asset has a **schedule** (charged and projected by year) and
  **Dispose**.
- **Depreciation runs**: charge a period. A run works each asset pro rata by
  days and posts one journal (*Depreciation* against *Accumulated
  Depreciation*). Runs go forward only and may not overlap; the latest can be
  cancelled with a reason.
- **Income-tax block schedule**: by financial year, the opening value,
  additions, depreciation at the block rate (half for an asset used under 180
  days) and closing value per block. It is a statement only and posts nothing.

Disposing of an asset charges depreciation to the day, takes its cost and
accumulated depreciation off the books, brings in the cash or bank received
and books the difference as a gain or a loss. Viewing and managing are two
permissions of their own; a run, cancelling one and a disposal also need the
right to post journals. Not built: turning goods already in stock into an
asset, GST on the sale of an asset (raise a sales invoice for it), and an
Income-tax book posting.

## 8.2 Statements

*Trial Balance, Profit & Loss* and *Balance Sheet* are in the Accounts
drop-down; *Cash Flow* is under *Accounts → All Accounts screens →
Statements*.

- **Trial Balance**: every account's balance at a date; debits equal credits.
- **Profit & Loss**: income less expenses for a period -- a month, a quarter,
  a year or any run of months, **month by month** in columns, and **compared
  with last year**.
- **Stock valuation**: every item's quantity, rate and value as on a date, with
  the Inventory account's balance on the same day and the difference.
- **Balance Sheet**: what the firm owns and owes at a date.
- **Cash Flow**: where the cash came from and went, by operating, investing
  and financing, from the books, checked against the cash and bank balances.

Each chooses its period on the page line and opens a line to its ledger.

## 8.3 Tax filing

*GST Returns* is in the Accounts drop-down. Everything else of tax filing --
GSTR-2B Reconciliation, Rule 37, Rule 42, GST checks, GST Payment, PMT-06
deposits, E-Invoice, TCS, TDS Challans and Bank Details -- is under *Accounts →
All Accounts screens → Tax filing*. The tax *settings* are under *Settings →
Tax*.

**GST Returns.** **GSTR-1** (outward supplies: B2B invoice by invoice, B2C
large and small, credit notes, HSN summary, documents issued) and
**GSTR-3B** (the summary), for a chosen month. They are read from the
invoices and credit notes **as they stand**, every time, so a late credit note
or a cancelled invoice is always reflected. The place of supply is decided by
the tax charged on each document.

Once a month is **marked filed**, its GSTR-1 is kept as it was filed. Later
changes do not rewrite it: they appear as **amendments** (B2BA, B2CLA, CDNRA,
B2CSA and documents added after filing) in the period that makes them, and
GSTR-3B carries the net change. A firm whose branches have their own **GSTIN**
chooses the GSTIN at the top of the page and sees only those branches' documents
(see 9.3).

**Quarterly filers (QRMP).** Under *Settings → Tax → GST Documents → Return
filing* a firm chooses monthly or quarterly filing and how it pays in months 1
and 2. The tax calendar then shows the optional IFF and the PMT-06 deposit for
months 1 and 2 and the quarter's GSTR-1 and GSTR-3B on their due dates;
*PMT-06 deposits* (beside GST Payment) records the deposit, and the quarterly
GST payment uses it before the bank.

**GST checks** (*Accounts → All Accounts screens → Tax filing → GST checks*). Before filing, lists what
a return would trip over: an invalid GSTIN (the firm's, a buyer's, a supplier's),
a missing or short HSN code, a missing place of supply, an invoice with no IRN,
a credit note raised after the last date allowed (30 November after the year),
or one on a cancelled invoice. Each row names its document. Separately, a
credit note after that date, a supplier bill after its credit's last date and a
document number longer than the 16 characters GST allows (the default series
are now shortened to fit) each raise a warning when saved. Each line also keeps
the tax rule that taxed it, shown in the line's tax detail.

**Rule 42** (*Accounts → All Accounts screens → Tax filing → Rule 42*). Credit on goods and services
used for both taxable and exempt supplies is reversed in proportion: the
monthly reversal, the year's true-up and the reclaim post against Input Tax Not
Claimable, and GSTR-3B carries them. Rule 43 (capital goods) is not built.

**GSTR-2B Reconciliation.** The portal's monthly statement of what
suppliers filed, imported as the JSON file the portal gives and matched to the
purchase bills by the supplier's GSTIN and bill number: *Matched*,
*Different* (it says what differs), *Not in books*, or matched by hand; and a
list of bills the suppliers have not filed. The firm chooses in *GST
Documents* whether GSTR-3B claims every bill (the default, listing what 2B
lacks) or only matched ones.

**Rule 37 (180 days).** Bills dated more than 180 days ago with input
credit claimed and money still unpaid, with the credit to reverse in
proportion to the unpaid share; a bill paid since shows the credit to reclaim.
Under *GST Documents* the firm chooses *Off*, *Report* (the default) or
*Report and post*, which posts each reversal and reclaim against Input Tax Not
Claimable; GSTR-3B reports both.

**E-Invoice.** Registers an invoice, a credit note, a debit note to a
customer or a sales return with the government portal and records the IRN,
acknowledgement and signed QR it returns, which then print on the document.
Each firm chooses its **route** in *GST Documents*: the portal's **sandbox**
(a rehearsal: every reference it returns is marked as a sandbox one and can
never be mistaken for a real filing) or **offline** -- *Export for portal*
writes the portal's bulk-upload file, the firm uploads it on the e-invoice
portal, and *Import portal result* records each IRN. A direct or GSP
connection is not in 1.3.0.

Once the firm's *e-invoicing applies from* date has passed, an approved B2B
invoice, credit note or debit note **cannot be printed or emailed until it has
its IRN** -- without one it is not a valid invoice. The refusal offers *Print
reference copy*, which prints the figures under "NO IRN YET - NOT A VALID TAX
INVOICE"; the automatic *Invoice approved* email waits until the IRN arrives.
A consumer's bill is never held. From the firm's *30-day rule from* date, a
document more than 30 days old is refused at registration, naming its last
day. *... → To register* lists every B2B document still without an IRN, with
its last day, days left, *due soon* within 5 days or *Late*, and a *Register*
button.

**E-way bills** come from the invoice (with or without an IRN), from a
delivery note that no invoice bills (job work, supply on approval, van sales),
or are recorded by hand after raising them on the portal. *... → E-way bills
due* lists consignments worth more than the firm's limit (₹50,000 unless it
sets its state's) that have none, and a prompt offers one after dispatch or
approval.

**TCS.** Tax collected at source under section 206C(1H), charged on the
**money received** from a buyer beyond the yearly threshold, not on the bill.
The Finance Act 2025 **omitted this section from 1 April 2025**, so receipts
from that date are charged nothing; the screen keeps the record of what was
collected before it, by customer.

**GST Payment.** The month's GST settled the way the law sets it off (section
49(5) and rule 88A): what is owed head by head, what input credit pays, the
cash payable, and the credit carried to next month. Recording the challan
(CPIN, bank, interest) posts it in one journal; only the latest month can be
reversed.

**TDS challans** (*Accounts → All Accounts screens → Tax filing → TDS Challans*). The tax deducted
and not yet deposited is listed by section; make a challan from it (one
section, the tax equals the deductions' sum, with the bank's counterfoil
details), and the challan's serial, BSR code and date flow into the TDS return;
*Challans due* shows what is deposited and what is not. A supplier can carry a
*Usual TDS section* that the payment screen prefills.

**TDS on purchases (194Q).** Switch it on under *Settings → Tax → TDS on
Purchases (194Q)* (threshold 50 lakh, 0.1%, 5% without PAN, all editable). The
payment screen then prefills the section and the amount for a supplier whose
bills in the year exceed the threshold, never over a figure typed; a register
in Reports lists each supplier's bills and the 194Q deducted.

**PAN check.** *Reports → Financial → Customer PAN check* and *Supplier PAN
check* list parties with a missing or wrongly shaped PAN.

**TDS.** Two registers: *TDS deducted* (by the firm, with PAN and section by
quarter, for 26Q) and *TDS deducted by customers* (with their TAN, to check
against 26AS).

## 8.4 Structure (Settings → Set up → Account structure)

- **Control Accounts**: which account each kind of posting uses (stock,
  customers, suppliers, sales, purchases, output and input GST ...), filled in
  when the books are opened. Once an account has entries
  against it, it cannot be switched, so the books never split one story
  across two accounts.
- **Cost Centres** and **Profit Centres**: optional tags on entries for
  reporting by department or line of business.

**Financial years and periods** are under *Settings → Firm → Financial Years*. A
document can only be posted into an open period; closing a period stops late
changes to it. Before a month is closed the screen lists what is still undone
(draft documents, unreconciled bank lines and the like) -- it lists and never
refuses. The same screen sets the **ageing bands** (5.3).

---

# 9. Masters

## 9.1 Parties

*Customers* and *Vendors* are in the Masters drop-down.

**Customers.** Name, code, GSTIN, PAN, contacts, billing and shipping
addresses, payment terms, credit limit, standing discount, price list,
salesman and territory, opening balance, minimum shelf life, and any extra
fields the business
profile adds (a pharmacy's drug licence number, for example). Customers can be
exported, duplicated, edited in bulk, and restored after deletion. A customer with documents against them cannot be
deleted. One company may be several customers (a branch per state, say), so a
GSTIN or PAN may repeat; saving one another customer already holds names that
customer and asks first.

**One business as customer and supplier.** Tick *Also a supplier* on the
customer (or *Also a customer* on the supplier) to link the two records (same
PAN, each linked once); the *Combined statement* then nets what each owes the
other.

**Duplicates.** Saving a new customer or supplier warns when the same GSTIN,
the same phone (last ten digits) or the same name (ignoring *stores*, *traders*,
*Pvt*, *Ltd* and the like) is already held. *Merge into...* on the lists joins
a duplicate into the one to keep: every document, balance and record of the
duplicate moves to the survivor in one step, and the duplicate is retired. It is
refused if the duplicate has a document dated in a locked financial year.

**Customer bank accounts and files.** The *Bank accounts* and *Files* tabs on
the customer keep the customer's accounts (numbers masked to the last four for
people who may not change them) and scanned papers.

**Codes from a series.** Leave a new customer's, supplier's or product's code
blank and one is issued on save (CUS, SUP, PRD followed by five digits); a code
typed is kept.

**Vendors.** The supplier's side of the same: name, code, GSTIN, PAN,
contacts, addresses, bank account for payments, category and type, payment
terms, GST type, and whether the supplier e-invoices. Same export, bulk and
restore actions.

**Configuration** (*Settings → Set up → Party lists*): *Customer Groups*
(segments with a group discount and a price level), *Vendor Categories*,
*Vendor Types*, *Licence Types* and *Licence Check*.

## 9.2 Items

*Products* is in the Masters drop-down.

**Products.** Code, name, category, HSN code and tax group, units (buying,
stock and selling), prices, preferred supplier, reorder level, barcode, and,
where the profile
switches them on, batch, expiry, serial number and warranty tracking, plus
any extra fields the profile adds. Products can be imported from a file
(checked before anything is saved) and exported. A product also carries its
**brand** (and through it the **principal**), its **price levels**, a **price
history** (a new price with an effective date, also loadable from a file), the
expiry, shelf-life and issue rules (7.3), *Inspect on receipt* and *Not for
sale*.

**Configuration** (*Settings → Set up → Item lists*):

- *Product Categories*: a tree of categories.
- *Principals* and *Brands*: the brand owners the firm
  distributes for and their brands; brand and principal are also ways to slice
  Sales Analysis.
- *Units of Measure*, *UOM Groups*, *Conversion Rules*: a product can be
  bought by the carton, held in boxes and sold in pieces; the conversion is
  applied on every document line.
- *Packaging Types* and *Packaging Levels*: the packing hierarchy (piece,
  box, carton) with a barcode at each level.

## 9.3 Organisation and locations

*Branches* and *Warehouses* are in the Masters drop-down. **Trade Licences**
(*Masters → All Masters screens → Compliance*) is the register of licences --
the firm's, a branch's, a customer's or a supplier's, with their validity
dates -- whose numbers print on invoices and whose expiry is raised on Home; a
product or category can require one, and the sale (and purchase) then warns or
blocks as the firm sets. *Licence Types* and *Licence Check* are set up under
*Settings → Set up → Party lists*.

- **Branches**: places that trade, each with its address, GST registration
  and manager. Every document belongs to a branch. A branch with its **own
  GSTIN** (checked, and for the branch's own state) prints it on that branch's
  documents, e-invoices and e-way bills, and files its GSTR-1 and 3B
  separately; a branch without one uses the firm's.
- **Warehouses**: places that hold stock, each under a branch.
- **Configuration** (*Settings → Set up → Locations*): *Storage Areas* (zones, racks and bins inside a
  warehouse), *Branch Types*, *Warehouse Types*, and **Places** (countries,
  states, districts, cities, PIN codes and localities, shared by every
  address in the firm). Every firm starts with the southern states' places
  already loaded from India Post's PIN directory; the platform administrator
  loads other states with *Load places from India Post...*.

---

# 10. Reports

*Reports* on the menu bar has no daily list: its two screens are always shown.
Two screens, **Operational** and **Financial**, holding more than fifty
reports. Each can be filtered, sorted and exported.

| Area | Reports |
| --- | --- |
| Quotations and orders | Enquiries lost, quotation register, quotation conversion, sales order register, orders not yet delivered, back orders, orders by customer, salesman or territory, targets achieved |
| Deliveries | Delivery note register, dispatches not yet completed, delivery progress by order, dispatches by route, salesman or warehouse |
| Invoices and money | Sales invoice register, customer outstanding, invoices not yet approved, overdue sales invoices, sales invoice reconciliation |
| Returns and credits | Sales return register, returns by customer or product, sales return reconciliation, credit note register, credits by customer or by reason |
| Proforma and loyalty | Proforma register, proformas awaiting payment, loyalty balances, loyalty movements, points about to lapse |
| Promotions | Promotion performance, promotion claims, coupon performance |
| Buying | Purchase order register, orders not yet received, overdue purchase orders, orders by supplier or buyer, purchases by product, receipts awaiting completion, orders part received, receipts completed, damaged and rejected on receipt |
| Supplier bills and returns | Purchase invoice register, supplier invoices not yet approved, purchase invoice reconciliation, overdue purchase invoices, vendor outstanding, purchase return register and reconciliation, damaged and expired goods returned, returns by product or vendor |
| Commission and tax | Commission on collections, TCS charged against due, customer and supplier PAN check, TDS 194Q |
| Supplier and stock | Supplier performance, supplier price trend, free goods given, invoices due (selling and buying) |
| GST registers and others added 2026-10-05 (Financial) | GST sales register, HSN summary of sales, GST purchase register, HSN summary of purchases, TCS paid to suppliers, customer rebate statement |

The accounting statements (Trial Balance, Profit & Loss, Balance Sheet,
Ledgers), GST returns, customer statements and ageing are under
**Accounts**, **Sell** and **Buy**, beside the work they report on.

The **GST sales register** lists every declared document of a period by tax
head: an approved bill is a row, a credit note, a completed sales return and a
late cancellation rows in minus on their own dates, a customer debit note a
row in plus. The **HSN summary of sales** folds the same supplies by HSN code
and rate. Both read what GSTR-1 reads, so they agree with the return. The
**GST purchase register** does the same for approved and closed supplier
bills, with tax that may not be claimed and reverse charge shown apart, and
debit notes and returns after billing as minus rows; the **HSN summary of
purchases** folds them by HSN code and unit. A bill in another currency is
shown in rupees at the bill's own rate, here and in the purchase invoice
register, purchase analysis and GSTR-3B's input side. All were added on
2026-10-05 and have not been tested by hand.

---

# 11. Platform: people, firms, the agency and the system

What used to be the **Admin** area of the menu bar. It lives behind the gear:
*Settings → Platform*, with the sections *People, Firms, Agency* and *System*.
Each card is shown only to those whose role holds the matching right, and the
server refuses the request whatever a menu shows.

## 11.1 People (*Settings → Platform → People*)

- **Users**: create an account, reset a password, lock or unlock, and see
  the firms and roles a person has.
- **Roles**: the preset roles (section 14) and any the firm adds. A new role
  is usually made by copying a preset one and adjusting it.
- **Permissions**: what each permission allows, and which roles hold it.
- **User Templates**: a named job (for example *Counter billing*) that sets
  up a new person's roles and firms in one step. A new person can also be
  set up **like an existing one**.
- **User-Firm Assignments**: which people belong to which firms, and which
  firm opens first for each.

Passwords are never stored in readable form. Signing in again after a set
time is required, and a person whose access is removed is signed out at once.

## 11.2 Firms (*Settings → Platform → Firms*)

- **Firms**: create a firm, edit its details, and **Set up** (section 3).
- **Business Profiles**: the industries on offer and what each switches on.
  Which profile a firm has is set under *Settings → Business profile →
  Profile Assignment* or on the firm's Set up panel.

## 11.3 The agency: branding (*Settings → Platform → Agency → Branding*)

The agency that bought the product has a **name, a tagline and a logo**. They
lead the sign-in screen and the header of every screen, so every PC shows the
same; the product's own name (Agency Platform, by its company) stays beside
them, quietly. The record belongs to the installation, not to any firm, so
there is one and it needs no firm to be chosen.

**Giving it.** In any of three ways:

1. **At install.** A fresh *server* install shows a **Branding** page after
   *This PC*: agency name, tagline and a logo file (Browse), all optional.
   A tagline or logo without a name is refused, and so is a logo path that does
   not exist. Leave them blank and the install is unchanged. The page is not
   shown for an app-only PC, an upgrade or a repair. A logo the server refuses
   (a text file renamed `.png`, a picture over 1 MB) **never fails the install**:
   the name is saved, no logo is, a warning goes to the install log, and the
   logo can be added later.
2. **First sign-in: *Set up your agency*.** While the branding has not been
   given, the first platform administrator (or anyone with the
   platform-settings right) to sign in sees a dialog with name, tagline, logo
   and a live preview. **Skip for now** closes it, and Home keeps a *Finish
   setting up* card (4) until it is given; it does not reopen for somebody who
   skipped. A firm administrator, or anyone without the right, never sees it.
   After an upgrade the branding is empty, so this is how an upgraded
   installation gives it.
3. **Settings → Platform → Agency → Branding**, any time. One form: *Agency
   name* (required), tagline, logo (PNG or JPG, at most 1 MB), a preview of
   the sign-in card and the top of every screen, and the product, company and
   product logo shown read-only (they change only with an update). There is no
   accent-colour box. **Save** shows *Saved.* and the header changes at once;
   **Remove logo** brings back the agency's initials. A file that is not
   really a PNG or JPG is refused (*The logo must be a PNG or JPG image.*) and
   so is one over the size, naming it. If two people edit at once, the second
   save is refused with a message that somebody else saved, and keeps what was
   typed.

**Who may.** Reading the name, tagline and logo needs no sign-in at all (the
sign-in screen shows them). Changing them needs the platform-settings right
(`PLATFORM_SETTINGS`), which only the platform tier holds. Every change is in
the audit trail (*Settings → Platform → System → Audit Logs*, no firm chosen):
`agency_branding.created`, `agency_branding.updated` and
`agency_branding.logo_changed` (the type and size, never the picture), each
naming who. Another PC sees the new branding at its next sign-in screen.

## 11.4 System (*Settings → Platform → System*)

- **Audit Logs**: who changed what, and when: every create, edit, approval,
  cancellation and sign-in, with the old and new values. The trail cannot be
  edited or deleted, by anybody. The firm administrator may give *Firm Audit
  Log View* to any role of the firm (an accountant, say): it reads that firm's
  trail and nothing else.
  One search box finds text in the action, the record type or the person.
  With no firm chosen it reads the platform's own trail (people, firms,
  branding).
- **Diagnostics**: the server's health, versions and recent errors, for
  support.
- **The quick check** (on the server PC, not a screen): `agency-server
  quick-check --email <user>` proves an installation works -- the server
  and database answer, every store is migrated, every list and report of
  every firm the user can open comes back -- counted module by module,
  with an HTML page of the result. It only reads, so it is safe on live
  books. `docs/qa/SANITY_CHECK.md` adds the hand checks, module by module.
- **Platform Dashboard**: counts of firms, users and roles across the
  installation, for the platform administrator.
- **Backups**: the backups the server has taken, and **Back up now** to take
  one. A backup runs on the server and takes a while, so the button returns at
  once and the page checks until the run is done. Platform tier only
  (`SYSTEM_BACKUP`).
- **Licensing**: a placeholder; licensing is not in use in 1.3.0.

## 11.5 Backup

The server backs up every database **every night at 02:00** into
`C:\ProgramData\Agency Platform\backups\daily`, keeping the newest seven, and
also before every upgrade. After the nightly backup the server also prunes
old sign-in and token records on its own (switched off by the platform-wide
setting `AGENCY_RETENTION_AUTO_PURGE`). The *Installation guide* (section 6) explains how
to restore one.

---

# 12. Settings (the gear): the Settings page, Set up and Platform

## 12.1 The Settings page

The **gear** at the right of the menu bar opens the Settings page in a tab of
its own: a list of sections at the left, each section's screens as **cards** at
the right, and a **search box** across every card. It is built in the app from
the person's permissions, so it asks the server nothing, and a section with
nothing the person may open is not shown. It has three parts:

| Part | What it holds |
| --- | --- |
| **Settings** | *This PC and me* (My Preferences, 2), then the firm's own settings: Firm, Selling, Buying, Stock, Tax and Business profile (12.2) |
| **Set up** | The lists set up once and changed rarely, moved here from the drop-downs: Pricing, Territories & routes, Account structure, Party lists, Item lists and Locations (12.3) |
| **Platform** | What the Admin area held: People, Firms, Agency and System (11) |

Settings that are dialogs rather than screens (Sales Stages, Credit Control,
Price Floor, Discount Limits, Loyalty Scheme, TCS Settings, Approval Levels,
Approval Limits, Purchase Budgets, Adjustment Limits, Batch Rules, GST
Documents, TDS on Purchases, Messaging, My Branch and Warehouse) open from a
card the same way, and from the "..." menu of the screen they belong to.
Opening a card that is a screen opens it as a tab.

## 12.2 The firm's settings

| Group | Screens | What they set |
| --- | --- | --- |
| This PC and me | My Preferences | Start in firm, first screen, theme, text size, date format (2) |
| Firm | Firm Settings, Financial Years, Numbering Series, Custom Fields, Custom Field Rules, My Branch and Warehouse, Messaging, Approval Levels | The firm's details; its years and accounting periods (open and close); the number pattern of each kind of document; the branch and warehouse **each person's** new orders, quotations and purchase orders open with; the firm's own **custom fields**, and **extra fields on documents** (quotation, order, delivery note, invoice, purchase order, goods receipt) carried from one document to the next and printed when marked *Show on print*; **approval levels** (5.2); **Messaging** (email, WhatsApp, SMS: off until the firm switches it on with its own accounts; overdue reminders stop 90 days past due unless the firm sets another window) |
| Selling | Sales Stages, Credit Control, Price Floor, Discount Limits, Loyalty Scheme, TCS Settings | Which stages of a sale the firm's people type, and whether *Rate includes GST* starts on; the credit warning and whether it blocks; the lowest price and each role's discount limit; points; tax collected at source |
| Buying | Purchase Settings, Approval Limits, Purchase Budgets | Purchasing defaults and approval, the **reorder planning** choice (typed levels or from sales), the order-multiple, bill-matching and budget policies, and the budgets |
| Stock | Inventory Settings, Adjustment Reasons, Adjustment Limits, Batch Rules | The firm's stock defaults; **Batch Rules**: the near-expiry window (30 days), whether a near-expiry batch or one passing over an earlier batch needs a reason, the minimum-shelf-life policy (block or warn), near-expiry stock below the price floor, and *Price from batch*; the firm's adjustment reasons; each role's adjustment limit; whether returns are held for checking |
| Tax | Tax Configuration, Tax Rules, Rule Simulator, Execution Log, Tax Settings, GST Documents, TDS on Purchases (194Q) | Tax systems, components and rates; the rules that choose the tax for a line (by product tax group, category, place of supply, customer type); trying a rule before relying on it; what each calculation decided; **GST Documents**: the dispatch-before-invoice policy, whether route sales need the invoice first, the dates e-invoicing and the 30-day limit start, the e-invoice route (sandbox or offline) and the e-way bill limit, whether GSTR-3B claims every bill or only those matched to GSTR-2B, the 2B tolerance, the rule 37 mode, whether a bill from an e-invoicing supplier with no IRN is warned about, the Rule 42 mode, and monthly or quarterly return filing (read with *Tax view*, changed with the tax-settings permission) |
| Business profile | Feature Management, Module Configuration, Attribute Definitions, Mandatory Attributes, Profile Assignment, Industry Templates | What each industry switches on, which extra fields exist and which are mandatory for which product category, and which profile each firm has |

**How tax is chosen.** Tax is not a rate stored on a product. The product
brings its tax group, category and type; the document brings the branch, the
customer and the place of supply; and the **tax rules** decide, in priority
order, which rates apply. The first rule that matches wins. So a change in
law is a new rule, not an edit to every product.

## 12.3 Set up: the lists set up once

*Settings → Set up* holds what the drop-downs used to carry under a
CONFIGURATION heading. Each section is exactly one of those old groups, and
each area's drop-down ends with a **SET UP IN SETTINGS** link to its own
sections. Every screen is offered only to a person who may open it.

| Section | Screens | See |
| --- | --- | --- |
| Pricing | Price Lists, Price Levels, Promotions, Loyalty | 5.7 |
| Territories & routes | Territories, Route Types, Route Builder | 5.6 |
| Account structure | Control Accounts, Cost Centres, Profit Centres | 8.4 |
| Party lists | Customer Groups, Vendor Categories, Vendor Types, Licence Types, Licence Check | 9.1, 9.3 |
| Item lists | Product Categories, Principals, Brands, Units of Measure, UOM Groups, Packaging Types, Packaging Levels, Conversion Rules | 9.2 |
| Locations | Storage Areas, Branch Types, Warehouse Types, Places | 9.3 |

The **Platform** part (People, Firms, Agency, System) is section 11.

---

# 13. How a sale and a purchase reach the books

What each approved document writes, in plain terms.

**A sale:**

| Step | Books |
| --- | --- |
| Delivery dispatched | Cost of goods sold up, stock down, at the stock's average cost |
| Invoice approved | Customer owes the total; sales and output GST recorded |
| Receipt recorded | Cash or bank up; customer owes less |
| Return approved | Stock back at its cost; customer owes less; sales and GST reversed |
| Credit note approved | Customer owes less; sales and GST reversed (no stock moves) |
| Debit note approved | Customer owes more on the invoice; sales and GST added (no stock moves) |

**A purchase:**

| Step | Books |
| --- | --- |
| Goods received | Stock up, at the receipt's cost |
| Supplier invoice approved | The firm owes the supplier; input GST recorded |
| Payment recorded | Cash or bank down; the firm owes less |
| Return approved | Stock down; the firm owes less |

**Running costs** -- rent, salaries, electricity -- are recorded under
*Accounts → Expenses*, which posts each against its Indirect Expenses account.
Anything else is a journal entry by hand.

Because each step writes its own entry, the customer and supplier balances,
the stock screens and the accounts agree with each other without any
month-end posting.

---

# 14. Roles: who can do what

A person's **role** decides what they may do; their **firm membership**
decides whose data they may do it to. The preset roles:

| Role | For | Cannot |
| --- | --- | --- |
| Firm administrator | Runs the firm: every module, plus the firm's users and roles | Platform-wide administration |
| Firm manager | Everything the administrator operates | Manage people, roles and settings |
| Accountant | The books, commission, reports, credit policy | Raise or approve sales and purchases |
| Sales manager | The sales desk: customers, the sales chain, territories, credit notes, proforma, loyalty | Change the credit policy, pay commission, and a few other controls kept apart |
| Sales executive | Works a beat: views customers, raises quotations, orders and invoices | Approve, cancel, or change masters |
| Purchase manager | All of purchasing, including approval | Anything outside purchasing |
| Purchase executive | Purchasing without approval | Approve |
| Inventory manager | Stock, batches and serial numbers | Anything else |
| Cashier | Receipts and payments | Anything else |
| Billing executive | Raise sales invoices | Anything else |
| Customer support | View and update customers, view products | Anything else |
| Viewer | Look at everything in the firm | Change anything |

Above them sit the **platform administrator** (the whole installation: firms,
users, profiles) and two platform roles for **auditing** and **licensing**.
A firm can add its own roles; the preset ones cannot be changed.

---

# 15. Not in 1.3.0

Known and planned:

- **Help > About.** Not built; clicking the product on the status line does
  nothing.
- **First-run is step 1 only** (*Set up your agency*). The later steps, and a
  prompt in the header strip, are not built; Home's *Finish setting up* card
  stands in for them.
- **The "PRACTICE" mark** for a practice firm: not built (there is no
  practice-firm feature).
- **Support details are blank by design.** No support phone, WhatsApp, hours,
  email or website is shown under *More help* on the sign-in screen until they
  are packaged.
- **The accent colour** is stored with the branding but neither asked nor
  applied; the product logo on the status line is a placeholder icon until one
  is packaged; the server does not check a logo's shape (the screens fit it into
  a square).
- **A client-side cache** of preferences and reference data to cut server calls
  was deferred by the owner; today every screen reads what it needs when it
  opens.
- **Licensing.** The screen is a placeholder and licensing is not in use.
- **Rows per page** is not offered in My preferences.
- Gross profit shown above net profit on the Profit & Loss.
- Sending documents automatically by WhatsApp or SMS: only sharing by hand is
  built (5.2); automatic messages wait for the firm's own accounts (Settings
  → Firm → Messaging). Payment links are not built.
- The 26Q return file for TDS (the registers and challans exist).
- Rule 43 (capital goods) of the common-credit reversal.
- A bank-specific layout for the payment run file.
- Opening a document straight from a GST check row.
- A live connection to the e-invoice portal or e-way bill through NIC or a GSP
  (the sandbox and the offline upload exist).
- A kit inside a kit, and kit components priced on the bill.
- A signed installer (Windows warns when it is run).
- From the purchasing and selling builds of 2026-10-05: reading a supplier's
  bill into a draft (OCR); emailing a request for quotation; the Bill of Entry
  in the GST purchase register and against GSTR-2B; purchase returns and debit
  notes in another currency; tax withheld on a payment abroad (section 195);
  recurring bills, job work, drop-ship and consignment; charges carried from
  the sales order or credited by a credit note; a counter refund against a
  bill and a count by denomination; a rebate settled by a GST credit note; van
  sales, export and SEZ sales, packing slips and a bill of supply.
