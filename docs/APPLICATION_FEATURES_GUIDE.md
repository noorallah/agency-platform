# Agency Platform: application features guide

What the application does, screen by screen, in the order of the menu bar of
release 1.0.2. It explains what each screen is for, what has to be set up
before it, and what it changes in stock, the books and GST.

This is a **reference**, not a test script. To test the application step by
step, use the *QA functional walkthrough*; to install it, the *Installation
guide*.

Written 2026-09-27 for release 1.0.2.

## Contents

1. What the application is
2. Finding your way around
3. Setting up a firm
4. Home
5. Sell
6. Buy
7. Stock
8. Accounts
9. Masters
10. Reports
11. Admin: people, firms and the system
12. Settings (the gear)
13. How a sale and a purchase reach the books
14. Roles: who can do what
15. Not in 1.0.2

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

**It adapts to the trade.** Each firm is given a *business profile*
(pharmacy, electronics, wholesale, general ...) that decides which features it
uses (expiry dates, serial numbers, drug licence ...), which menus it sees,
and which extra fields its products and customers carry.

**How it is installed.** One PC is the *server*: it holds the database and
runs the server program. Every other PC runs only the app and connects to the
server over the office network. The *Installation guide* explains both.

---

# 2. Finding your way around

## The screen

- **The menu bar** across the top: *Home, Sell, Buy, Stock, Accounts,
  Masters, Reports, Admin*, and the **gear** for Settings. Each opens a panel
  of screens, grouped; screens that are set up once and rarely changed are
  drawn apart under **CONFIGURATION**. A person sees only the menus and
  screens their role allows.
- **Tabs.** Every screen and every document opens as a tab under the menu
  bar, so several can stay open at once.
- **Ctrl+K** opens the search box: type part of a screen's name, or a
  customer, product or document number, and go straight to it.
- **The firm switcher** shows which firm you are working in; a person who
  belongs to several firms changes firm there.

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

A new firm goes through these steps once. **Admin → Firms → pick the firm →
Set up** shows where the firm stands on each and does several of them with
one click.

| # | Step | Where | Why it matters |
| --- | --- | --- | --- |
| 1 | Create the firm: name, code, GST, PAN, address, financial-year start, and where its data is kept | Admin → Firms → + New | Where the data is kept cannot be changed later |
| 2 | Prepare its storage (only if it has a section or database of its own) | Set up → Provision storage | Nothing can be recorded for the firm until this is done |
| 3 | Give it a business profile | Set up → Business profile → Assign | Decides its features, menus and extra fields |
| 4 | **Open the books** | Set up → Open the books | Creates the chart of accounts, the current financial year with twelve monthly periods, and the accounts each document posts to. **Without it, no invoice, delivery or receipt can be approved** |
| 5 | Apply the GST template | Set up → Apply GST template | The tax rates and rules for Indian GST |
| 6 | Create a head office and a main warehouse | Set up → Create head office and main warehouse | Every document names a branch; all stock sits in a warehouse |
| 7 | Give people access | Admin → Users | A user account, a role, and membership of the firm |

Then the masters, in this order, because each needs the one before:

1. Branches and warehouses (beyond the first)
2. Units of measure (check the ones the profile gives)
3. Products
4. Customers and vendors
5. Territories and routes, if the firm sells by beat
6. Price lists and promotions

**Document numbers need no setup.** Each kind of document starts its own
series on its first save (for example `SI/2026-2027/000001`), and the pattern
can be changed under **Settings → Numbering Series**.

---

# 4. Home

The first screen after signing in, cut to what the person may see:

- **Figures**: sales today, sales over the last 14 days (with a chart), what
  customers owe and how much of it is overdue, and items below their reorder
  level. Each opens the screen behind it.
- **Recent invoices.**
- **To do**, each a count that opens the list behind it: orders to approve,
  orders to deliver, invoices overdue, purchase orders to receive, supplier
  bills overdue.
- **Favourites**: the screens a person opens most, pinned.

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
off (*Sell → Sales Invoices → … → Sales stages*). The skipped documents are
still created automatically behind the scenes, so stock still leaves at
delivery and every report still adds up.

## 5.2 Documents

**Quotations.** An offer with lines, prices and validity. Convert an
accepted quotation into a sales order in one step. *Reports: quotation
register, quotation conversion.*

**Sales Orders.** The heart of selling. Enter the customer and the lines;
the price, discount, promotion and tax are filled in as you type. Approving
reserves the stock and claims any promotion. An order can be put **on hold**
(the stock stays reserved; nothing more is delivered until the hold is
released) or cancelled (the reservation is released). The credit check runs
here: see 5.5.

**Delivery Notes.** Picked from an approved order, choosing the warehouse
(and batch or serial, where the product is tracked). Dispatching takes the
stock out. A delivery can be part of an order.

**Sales Invoices.** Raised from an order or its deliveries, or on its own.
Approving books the sale, the GST (CGST and SGST within the state, IGST
outside it) and the amount the customer owes, with a due date from the
customer's payment terms. A document-level discount or freight charge is
spread across the lines so the tax is right.

**Sales Returns.** Goods coming back against an invoice. Approving puts the
stock back into the warehouse (or into a damaged or quarantine bucket) and
reduces what the customer owes, with the tax reversed.

**Proforma.** A statement, in advance, of what an approved order will be
billed: for a customer who needs a document to arrange payment or credit
before the goods move. It changes nothing: no stock, no sale, no amount owed,
and it has its own number series, separate from tax invoices.

**Credit Notes.** Money credited to a customer **without goods coming
back**: a rate agreed after invoicing, a quality allowance, a billing error.
It always names the invoice it credits and reverses that invoice's GST in
proportion. (Goods coming back are a *sales return*, not a credit note.)

## 5.3 Money

**Receipts.** Money received from a customer, by cash, cheque, bank transfer
or UPI. A receipt is applied to one or more invoices; anything left over is
held **on account** (an advance) and applied to a later invoice from the bar
(*Apply to an invoice*). A receipt entered wrongly is **reversed**, never
edited, and the reversal puts everything back as it was.

**Refunds.** Money paid back to a customer, out of an advance or a credit.

**Customer Statements.** Two views:

- **Ageing**: every customer's outstanding split by how old it is (0–30,
  31–60, 61–90, over 90 days).
- **Statement**: double-click a customer for their account over a period:
  opening balance, every invoice, return, credit note and receipt in date
  order with a running balance, and the closing balance. Printable to send to
  the customer.

## 5.4 Incentives

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
instead (the credit settings on the *Masters → Customers* screen). Changing that policy is
kept to people who hold the customer-settings permission, not the sales
manager whose orders it limits.

## 5.6 Field sales

For a firm whose salesmen visit shops on fixed rounds:

- **Territories** (configuration): the firm's own map of areas, for example
  Region → Zone → Area, each with a manager.
- **Route Types** and **Route Builder** (configuration): a route is a round
  of shops in visiting order, valid for a period, assigned to a salesman.
- **Beat Plans**: which route a salesman walks on which day.
- **Call Lists**: today's calls for a salesman, drawn from the beat plan.
- **Coverage**: which shops were visited or ordered from, and which were
  missed.

Orders, deliveries and invoices carry the salesman, route and territory, so
the reports can be read by any of them.

## 5.7 Pricing (configuration)

**Price Lists.** What a customer pays for a product before any offer. A price
list can apply to **one customer, one territory or the whole firm**, is valid
between dates, and can have **quantity breaks** (a lower price from 10, and
lower again from 50).

**Which discount applies** on a line, from strongest to weakest: an amount
typed on the line; a percentage typed on the line; a running promotion; the
price list; the customer's own standing discount; their customer group's
discount. A blank discount box takes the arrangement; a **0** typed in the
box refuses it.

**Promotions.** Offers the firm is running: a percentage or amount off, a
special price, **buy X get Y free**, for chosen products, categories,
customers or territories, between dates, optionally with a coupon code and a
limit on how many times it can be used. Several promotions can apply to one
line unless a promotion is marked as not combining with others. Each offer
records what it has cost. *Reports: promotion performance, promotion claims,
coupon performance.*

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

**Purchase Orders.** Enter the supplier and the lines. An order is
**approved** before anything can be received against it, and approval can be
kept to a purchase manager. Receiving moves the order to *part received* and
then *received* on its own; nobody sets that by hand.

**Goods Receipts.** Record what actually arrived against an order: the
quantity accepted, damaged and rejected, into which warehouse, with the batch
number and expiry date or serial numbers where the product is tracked.
Completing the receipt puts the accepted stock in and values it.

**Purchase Invoices.** The supplier's bill, matched to the receipt. Approving
books the amount owed with a due date, and the input GST the firm can claim.

**Purchase Returns.** Goods sent back to the supplier (damaged, expired,
wrong). Approving takes the stock out and reduces what is owed.

## 6.3 Money and insight

**Payments.** Money paid to a supplier, applied to one or more of their
invoices; any excess is held as an advance. Reversed, never edited, like a
receipt.

**Purchase Dashboard.** What is on order, what is waiting to be received,
what is overdue, and spend by supplier.

Every buying list names the **supplier** in a column and on the bar, and is
searched by supplier name.

---

# 7. Stock

Most stock moves because of a document: a goods receipt brings it in, a
delivery note takes it out, a return brings it back. The Stock menu shows
what is there, and handles the movements a firm makes about its stock rather
than about a trade.

## 7.1 Seeing the stock

- **Inventory**: what is on hand, by product and warehouse: available,
  reserved for orders, damaged, quarantined. The movements below start here.
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

From the Inventory screen, each its own action:

- **Adjust**: correct a quantity up or down, with a reason.
- **Transfer**: move stock between warehouses or branches.
- **Write off**: remove stock that is lost, broken or expired.
- **Quarantine**: set stock aside so it cannot be sold, and release it later.

And two documents:

- **Opening Stock**: the stock a firm holds on its first day in the
  application, entered by hand or imported from Excel, then posted once.
  Posting values it against the opening balance in the books.
- **Physical Count**: a stock-take. Open a count for a warehouse, record what
  was found line by line (over hours, by several people if needed; the list
  shows how many lines are counted), then post it: every difference becomes
  an adjustment.

## 7.3 Tracking

Used when the firm's business profile switches them on:

- **Batches** and **Lots**: stock held by batch, with manufacturing and
  expiry dates; deliveries pick the batch (earliest expiry first).
- **Serial Numbers**: each unit held by its serial number, from receipt to
  sale, with warranty where it applies.
- **Expiry Monitor**: batches that have expired or expire soon, and their
  value.

## 7.4 Data

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
document, not the entry. This is where expenses such as rent are recorded
today (see the *Profit and loss guide*).

**Ledgers.** One account's movements over a period, with the opening and
closing balance.

## 8.2 Statements

- **Trial Balance**: every account's balance at a date; debits equal credits.
- **Profit & Loss**: income less expenses for a period.
- **Balance Sheet**: what the firm owns and owes at a date.

Each chooses its period on the page line and opens a line to its ledger.

## 8.3 Tax filing

**GST Returns.** **GSTR-1** (outward supplies: B2B invoice by invoice, B2C
large and small, credit notes, HSN summary, documents issued) and
**GSTR-3B** (the summary), for a chosen month. They are read from the
invoices and credit notes **as they stand**, every time, so a late credit note
or a cancelled invoice is always reflected. The place of supply is decided by
the tax charged on each document.

**E-Invoice.** Registers an invoice with the government portal and records
the IRN it returns, and raises the e-way bill for the goods. *In 1.0.2 only
the portal's sandbox (test) connection exists*; every reference it returns is
marked as a sandbox one and can never be mistaken for a real filing.

**TCS.** Tax collected at source under section 206C(1H): charged on the
**money received** from a buyer beyond the yearly threshold, not on the bill.
The screen shows what has been charged against what was due, by customer.

## 8.4 Structure (configuration)

- **Control Accounts**: which account each kind of posting uses (stock,
  customers, suppliers, sales, purchases, output and input GST ...), 24 in
  all, filled in when the books are opened. Once an account has entries
  against it, it cannot be switched, so the books never split one story
  across two accounts.
- **Cost Centres** and **Profit Centres**: optional tags on entries for
  reporting by department or line of business.

**Financial years and periods** are under *Settings → Financial Years*. A
document can only be posted into an open period; closing a period stops late
changes to it.

---

# 9. Masters

## 9.1 Parties

**Customers.** Name, code, GSTIN, PAN, contacts, billing and shipping
addresses, payment terms, credit limit, standing discount, price list,
salesman and territory, opening balance, and any extra fields the business
profile adds (a pharmacy's drug licence number, for example). Customers can be
exported, duplicated, edited in bulk, and restored after deletion. A customer with documents against them cannot be
deleted.

**Vendors.** The supplier's side of the same: name, code, GSTIN, PAN,
contacts, addresses, bank account for payments, category and type, payment
terms. Same export, bulk and restore actions.

**Configuration:** *Customer Groups* (segments with a group discount),
*Vendor Categories*, *Vendor Types*.

## 9.2 Items

**Products.** Code, name, category, HSN code and tax group, units (buying,
stock and selling), prices, reorder level, barcode, and, where the profile
switches them on, batch, expiry, serial number and warranty tracking, plus
any extra fields the profile adds. Products can be imported from a file
(checked before anything is saved) and exported.

**Configuration:**

- *Product Categories*: a tree of categories.
- *Units of Measure*, *UOM Groups*, *Conversion Rules*: a product can be
  bought by the carton, held in boxes and sold in pieces; the conversion is
  applied on every document line.
- *Packaging Types* and *Packaging Levels*: the packing hierarchy (piece,
  box, carton) with a barcode at each level.

## 9.3 Organisation and locations

- **Branches**: places that trade, each with its address, GST registration
  and manager. Every document belongs to a branch.
- **Warehouses**: places that hold stock, each under a branch.
- **Configuration:** *Storage Areas* (zones, racks and bins inside a
  warehouse), *Branch Types*, *Warehouse Types*, and **Places** (countries,
  states, districts, cities, PIN codes and localities, shared by every
  address in the firm).

---

# 10. Reports

Two screens, **Operational** and **Financial**, holding more than fifty
reports. Each can be filtered, sorted and exported.

| Area | Reports |
| --- | --- |
| Quotations and orders | Quotation register, quotation conversion, sales order register, orders not yet delivered, back orders, orders by customer, salesman or territory, targets achieved |
| Deliveries | Delivery note register, dispatches not yet completed, delivery progress by order, dispatches by route, salesman or warehouse |
| Invoices and money | Sales invoice register, customer outstanding, invoices not yet approved, overdue sales invoices, sales invoice reconciliation |
| Returns and credits | Sales return register, returns by customer or product, sales return reconciliation, credit note register, credits by customer or by reason |
| Proforma and loyalty | Proforma register, proformas awaiting payment, loyalty balances, loyalty movements, points about to lapse |
| Promotions | Promotion performance, promotion claims, coupon performance |
| Buying | Purchase order register, orders not yet received, overdue purchase orders, orders by supplier or buyer, purchases by product, receipts awaiting completion, orders part received, receipts completed, damaged and rejected on receipt |
| Supplier bills and returns | Purchase invoice register, supplier invoices not yet approved, purchase invoice reconciliation, overdue purchase invoices, vendor outstanding, purchase return register and reconciliation, damaged and expired goods returned, returns by product or vendor |
| Commission and tax | Commission on collections, TCS charged against due |

The accounting statements (Trial Balance, Profit & Loss, Balance Sheet,
Ledgers), GST returns, customer statements and ageing are under
**Accounts** and **Sell**, beside the work they report on.

---

# 11. Admin: people, firms and the system

## 11.1 People

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

## 11.2 Firms

- **Firms**: create a firm, edit its details, and **Set up** (section 3).
- **Business Profiles**: the industries on offer and what each switches on.

## 11.3 System

- **Audit Logs**: who changed what, and when: every create, edit, approval,
  cancellation and sign-in, with the old and new values. The trail cannot be
  edited or deleted, by anybody.
- **Diagnostics**: the server's health, versions and recent errors, for
  support.
- **Platform Dashboard**: counts of firms, users and roles across the
  installation, for the platform administrator.
- **Licensing**: a placeholder; licensing is not in use in 1.0.2.

## 11.4 Backup

The server backs up every database **every night at 02:00** into
`C:\ProgramData\Agency Platform\backups\daily`, keeping the newest seven, and
also before every upgrade. The *Installation guide* (section 6) explains how
to restore one.

---

# 12. Settings (the gear)

| Group | Screens | What they set |
| --- | --- | --- |
| Firm | Firm Settings, Financial Years, Numbering Series | The firm's details; its years and accounting periods (open and close); the number pattern of each kind of document |
| Buying | Purchase Settings | Purchasing defaults and approval |
| Stock | Inventory Settings | The firm's stock defaults |
| Tax | Tax Configuration, Tax Rules, Rule Simulator, Execution Log, Tax Settings | Tax systems, components and rates; the rules that choose the tax for a line (by product tax group, category, place of supply, customer type); trying a rule before relying on it; what each calculation decided |
| Business profile | Feature Management, Module Configuration, Attribute Definitions, Mandatory Attributes, Profile Assignment, Industry Templates | What each industry switches on, which extra fields exist and which are mandatory for which product category, and which profile each firm has |

**How tax is chosen.** Tax is not a rate stored on a product. The product
brings its tax group, category and type; the document brings the branch, the
customer and the place of supply; and the **tax rules** decide, in priority
order, which rates apply. The first rule that matches wins. So a change in
law is a new rule, not an edit to every product.

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

**A purchase:**

| Step | Books |
| --- | --- |
| Goods received | Stock up, at the receipt's cost |
| Supplier invoice approved | The firm owes the supplier; input GST recorded |
| Payment recorded | Cash or bank down; the firm owes less |
| Return approved | Stock down; the firm owes less |

**Everything else by hand**: rent, salaries, electricity and other running
costs are recorded as journal entries against the Indirect Expenses accounts
(the *Profit and loss guide* shows how).

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

# 15. Not in 1.0.2

Known and planned:

- **An Expenses screen** (Accounts → Expenses) to record rent, fuel and
  other running costs without writing a journal. Until then, use a journal
  entry.
- Gross profit shown above net profit on the Profit & Loss.
- Sending documents by WhatsApp or email.
- Bank reconciliation.
- Importing customers and vendors from Excel (products, stock, branches,
  warehouses, territories and purchase orders can be imported today).
- A live connection to the e-invoice portal (the sandbox exists).
- A signed installer (Windows warns when it is run).
- Licensing.
