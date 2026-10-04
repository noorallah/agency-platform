# QA Test Book -- Agency Platform

Release 1.3.0 -- written 2026-10-04 from the product documentation; cases marked (confirm) need the figure checked on the first run.

## How to use this book

**Who it is for.** A tester at a Windows PC with the installed desktop app
(release 1.3.0), connected to a working server. You need to know the trade
(wholesale distribution, GST) but nothing about databases or code.

**One firm, built by you.** Every case runs in one test firm, **QA Book
Traders (QB01)**, which you create from the values in *Sample data*. Run
cases QA-FRM-01 to QA-FRM-12 (module *Firm set-up & configuration*) before
anything else, because every other case, sign-in included, needs that firm
and its administrator. Nothing else on the server is touched, except the
platform cases at the end.

**The first sign-in as platform administrator may open a *Set up your
agency* dialog** (the agency's branding is not yet given). Press **Skip for
now** and carry on with QA-FRM-01; the branding cases (module *Agency
branding*, QA-BRD) come back to it.

**Who to sign in as.** The firm and its people are created by the
**platform administrator** (the account set up when the server was
installed). From then on, work as the firm administrator
**admin@qb01.test** unless a case names another person. Every password in
this book is **QaTest@2026pw**.

**Run the modules in order.** Later modules use what earlier ones created:
the sale needs the stock the purchase brought in, and the GST return reads
the sales. If a case fails, write it up and carry on where you can; mark a
case **Blocked** if it cannot run because an earlier one failed.

**Run everything in one calendar month.** The GST returns and the monthly
figures assume every document is dated in the same month. If the month
changes during the run, the GST cases show the documents split across two
months; note it rather than failing the case.

**Recording results.** In the **Result** column write **Pass**, **Fail** or
**Blocked**. On a Fail, write in a few words what you saw instead, and fill
in a defect report (template at the end). A refusal is often the product
working: when a case says something must be refused, the refusal and its
message are the pass.

**Reading a case.**

- **Action** names the menu path and what to type. `Sell > Sales Invoices`
  means click **Sell** on the menu bar, then **Sales Invoices**. Screens that
  are not daily work are under **All <area> screens** at the foot of each
  drop-down, by group: `Sell > All Sell screens > Insight > Sales Analysis`.
  **Settings** is the gear at the right of the menu bar.
- **Verify on this screen** is what the screen you are on must show.
- **Verify elsewhere** is the knock-on effect: stock, the customer's or
  supplier's balance, the ledger, the GST return, the audit trail. Open the
  screen named and check the figure. **Screens read once when opened**:
  press Refresh (the circular arrow) before judging one.
- Ledger lines are written *Dr account amount / Cr account amount*, using
  the account names as the chart of accounts shows them.
- **(confirm)** means the figure or wording comes from the design notes and
  has not been driven on a real screen yet. Check it, and if the screen
  differs but looks reasonable, write down what it showed.

**Useful keys.** Ctrl+K searches every screen and record. Ctrl+N new, F2 edit
the picked row, Ctrl+S save, / search box, Esc close.

---

## Sample data

Create these records in the modules named. The figures are chosen so every
total can be checked by hand: cost and price in round numbers, GST at 18% or
5%. **The GST rates and HSN codes are test data, not tax advice.**

### The firm

| Field | Value |
| --- | --- |
| Firm code | `QB01` |
| Display name | QA Book Traders |
| GST number | `33AAQCB1201B1ZH` (Tamil Nadu, state 33) |
| PAN | `AAQCB1201B` |
| Address | 12 Anna Salai, Teynampet, Chennai, Tamil Nadu 600018 |
| Country / currency | `IN` / `INR` |
| Financial year start | `2026-04-01` |
| Contact phone | `+914424331201` (no spaces) |
| Where data is kept | With the other firms (recommended) |
| Business profile | **Food Distribution** -- chosen because it switches on batch *and* expiry tracking; Wholesale tracks batches but not expiry dates |

After *Set up* the firm has branch **HO** (Head Office) and warehouse
**MAIN**. You add a second warehouse **STORE2** *Back Store* under HO.

### Places (needed by every address)

| State (code, name) | District (code, name) | City (code, name) | Postal code |
| --- | --- | --- | --- |
| `TN` Tamil Nadu | `CHN` Chennai | `CHENNAI` Chennai | 600001 |
| `KA` Karnataka | `BLR` Bengaluru Urban | `BENGALURU` Bengaluru | 560001 |

### People (all in QB01, password QaTest@2026pw)

| Email | Name | Job template | Used for |
| --- | --- | --- | --- |
| admin@qb01.test | Firm Admin QB | Firm Administrator | Almost every case |
| arun@qb01.test | Arun Kumar | Field Sales | Salesman on the route; commission |
| kiran@qb01.test | Kiran Raj | Field Sales | A salesman *not* on the route |
| priya@qb01.test | Priya Menon | Sales Manager | Approvals; what a manager may not do |
| meena@qb01.test | Meena Devi | Counter Sales (tick **Require password change**) | The counter |
| anita@qb01.test | Anita Rao | Accounts | The books |
| suresh@qb01.test | Suresh Babu | Warehouse | Stock work |

### Customers

| Code | Name | GSTIN (PAN fills itself) | Billing address | Phone | Credit limit | Payment terms |
| --- | --- | --- | --- | --- | --- | --- |
| `QB-C1` | Ravi Traders | `33AAFCR1111R1ZE` | 14 Mint Street, Chennai, TN 600001 | `+919840011101` | `10000` | 30 days |
| `QB-C2` | Bharat Stores | `29AAGCB2222B1Z9` | 8 MG Road, Bengaluru, KA 560001 | `+919845022202` | `0` (no limit) | 30 days |
| `QB-C3` | Lakshmi Provisions | none (unregistered) | 22 Second Avenue, Anna Nagar, Chennai, TN 600040 | `+919840033303` | `0` | 0 days |

C1 is **intra-state** (CGST + SGST, B2B), C2 is **inter-state** (IGST,
B2B), C3 is **unregistered** (CGST + SGST, B2C small). Customer type
*Business*, currency INR for all three.

### Suppliers

| Code | Name | GSTIN | Address | Phone | Bank |
| --- | --- | --- | --- | --- | --- |
| `QB-V1` | Sunrise Distributors | `33AAKCS3333S1ZU` | 5 SIDCO Estate, Chennai, TN | `+914424440001` | State Bank of India, a/c `30012345678`, IFSC `SBIN0001234` |
| `QB-V2` | Deccan Foods | `29AALCD4444D1ZM` | 40 Peenya Industrial Area, Bengaluru, KA | `+918022550002` | none |

### Products (unit PIECE for base, inventory, purchase and sales unit)

| Code | Name | Category | HSN | Tax profile | Buy | Sell | MRP | Tracking |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `QB-DET` | Detergent Powder 1 kg | Cleaning | 340220 | GST 18% Local | 80 | 100 | 110 | none |
| `QB-FLR` | Floor Cleaner 1 L | Cleaning | 340290 | GST 18% Local | 40 | 50 | 60 | none |
| `QB-TEA` | Tea 250 g | Grocery | 090230 | GST 5% Local | 160 | 200 | 220 | none |
| `QB-TEA100` | Tea 100 g | Grocery | 090230 | GST 5% Local | 70 | 90 | 100 | none |
| `QB-GHEE` | Ghee 500 ml | Grocery | 040590 | GST 5% Local | 240 | 300 | 320 | **Track batch** and **Track expiry** |

The *Local* tax profile is right for inter-state customers too: the tax
rules switch it to IGST when the buyer is in another state.

### Opening stock (warehouse MAIN, reference `QB-OPEN`, posting date today)

| Product | Batch | Expiry | Quantity | Unit cost | Value |
| --- | --- | --- | --- | --- | --- |
| QB-FLR | -- | -- | 100 | 40 | 4,000.00 |
| QB-GHEE | `G-101` | today + 20 days | 20 | 240 | 4,800.00 |
| QB-GHEE | `G-102` | today + 180 days | 40 | 240 | 9,600.00 |
| **Total** | | | | | **18,400.00** |

Write the two actual expiry dates here before you start: G-101 ______ G-102 ______

### Pricing and incentives (created in the Pricing module)

| Record | Values |
| --- | --- |
| Price list `QB-STD` *Standard trade* | Applies to Everyone, from today; QB-DET from qty 1: **2%**; QB-DET from qty 20: **5%** |
| Promotion `QB-BULK` | Applies at 10; *Other promotions may still apply* ticked; condition *Quantity on the line* is at least **50**; benefit *Percent off each line* **10** |
| Promotion `QB-WELCOME` | *Only with a coupon*; benefit *Percent off each line* **4**; coupon `QBW1`, total claims allowed **1** |
| Customer group `RETAIL` *Retailer* | Default discount **1%**; Lakshmi Provisions in it |
| Standing discount | Ravi Traders, Default discount % **3** |
| Loyalty scheme | Running; 1 point per 100; each point worth 1; minimum 50 to redeem |
| Commission rule | Arun Kumar, paid on *Money collected*, **2%** |
| Sales target | Arun Kumar, this month, **10,000** |

### Territory (created in the Territory module)

| Record | Values |
| --- | --- |
| Region | `QB-RGN` Chennai Region |
| Territory | `QB-NTH` Chennai North, parent Chennai Region |
| Route type | `SALES` Sales Route |
| Route | `QB-R1` Anna Nagar Beat, parent Chennai North, Weekly, Mon and Thu; round: 1 Ravi Traders, 2 Lakshmi Provisions; salesperson Arun Kumar (primary) |
| Beat plan | `QB-BP-MON` Monday Anna Nagar, route Anna Nagar Beat, Weekly, Monday |

### Where the stock should stand

A running check. After each module, Stock Summary should agree.

| Product | After Buying | After Stock | After Selling | After Pricing (end) |
| --- | --- | --- | --- | --- |
| QB-DET | 95 | 89 | 61 | 61 |
| QB-TEA | 70 | 68 | 61 | 61 |
| QB-TEA100 | 0 | 5 | 5 | 5 |
| QB-FLR (MAIN + STORE2) | 0 | 93 (83 + 10) | 89 (79 + 10) | 79 (69 + 10) |
| QB-GHEE (G-101 + G-102) | 0 | 60 (20 + 40) | 50 (10 + 40) | 50 |
| QB-COMBO (kit) | 0 | 5 | 5 | 5 |
| **Stock value** | 18,800.00 | 37,040.00 | 31,120.00 | 30,720.00 |

Every product keeps one cost all the way through (DET 80, TEA 160, TEA100
64, FLR 40, GHEE 240, COMBO 120), so a value is always quantity times cost.

---

## Sign-in & my settings

**Before you start:** module *Firm set-up & configuration* cases FRM-01 to
FRM-12 must have passed (the firm and its administrator exist). Sign in as
admin@qb01.test.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-SIG-01 | Open the app; read the sign-in screen; sign in as admin@qb01.test | The version on the sign-in screen reads 1.3.0. Home opens on QA Book Traders; menu bar: Home, Sell, Buy, Stock, Accounts, Masters, Reports, gear. **No Admin** on the bar | Firm switcher (right) reads QA Book Traders | |
| QA-SIG-02 | Sign out; sign in with password `Wrong@Password1` | Refused: "Invalid email or password." Nothing says whether the account exists | -- | |
| QA-SIG-03 | Open **Sell** | Short list: Quotations, Sales Orders, Delivery Notes, Sales Invoices, Returns & notes, Receipts, Customer Statements; **All Sell screens (N)** at the foot. No Price Lists, Promotions or Territories here | -- | |
| QA-SIG-04 | In Sell, click **Returns & notes** | A short list opens beside it: Sales Returns, Credit Notes, Customer Debit Notes | Buy > Returns & notes offers Purchase Returns and Debit Notes | |
| QA-SIG-05 | Click **All Sell screens** | Every Sell screen you may open, under Documents, Money, Incentives, Insight, Field sales; each opens in a tab | Buy, Stock, Accounts, Masters behave the same; Masters daily list is Customers, Vendors, Products, Branches, Warehouses | |
| QA-SIG-06 | Click the **gear** (Settings) | A Settings tab: sections This PC and me, Firm, Selling, Buying, Stock, Tax, Business profile, then SET UP (Pricing, Territories & routes, Account structure, Party lists, Item lists, Locations) and PLATFORM (People) | Type `price` in its search box: Price Lists, Price Levels, Price Floor are found across sections | |
| QA-SIG-07 | Press **Ctrl+K**, type `sales order`, Enter | The Sales Orders screen opens | Ctrl+K `Ravi` (after Masters) finds the customer | |
| QA-SIG-08 | Open **Sell**; point at **Sales Orders** and click the star. Open **Stock**; star **Stock Summary** | Each star turns gold as clicked; the drop-down stays open | **Home > FAVOURITES** shows both boxes | |
| QA-SIG-09 | On Home, drag Stock Summary before Sales Orders; then point at Sales Orders and click its **x** | Order changes; Sales Orders box disappears | Sell drop-down: the Sales Orders star is no longer gold | |
| QA-SIG-10 | Star Sales Orders again. Press **Ctrl+K**, type `s` | Starred screens are listed **first** among the matches | -- | |
| QA-SIG-11 | Sign out; sign in as the same user on **another PC** (or another Windows account) | Same favourites, same order | -- | |
| QA-SIG-12 | User menu (initials, top right) > **My preferences** | Dialog: First screen, Theme, Text size, Date format. **No Start in firm** box (this user has one firm) | Same dialog from Settings > This PC and me > My Preferences | |
| QA-SIG-13 | My preferences: change nothing, press **Save**. Open again, change Theme, press **Esc**. Open again, change Theme, press **Cancel** | Save with nothing changed simply closes. Esc and Cancel close and the theme stays as it was | -- | |
| QA-SIG-14 | My preferences > **Theme** Dark > Save. Then Follow Windows > Save. Then Light > Save | Each applies at once, without restarting. Follow Windows follows the Windows light/dark setting | -- | |
| QA-SIG-15 | My preferences > **Text size** Large > Save; then Default | Text grows at once; the box says *This PC only* | On another PC the text size is unchanged | |
| QA-SIG-16 | My preferences > open **Date format** | Four rows, each showing today written that way: dd-MM-yyyy (default, e.g. 04-10-2026), dd/MM/yyyy, yyyy-MM-dd, MM/dd/yyyy | After Selling: choose yyyy-MM-dd and a sales invoice's date reads 2026-10-04 style (QA-SELL-27) | |
| QA-SIG-17 | My preferences > **First screen** > Sell > Sales Invoices > Save. Open Customers; sign out and in | Lands on Sales Invoices. The list offers only screens your role may open | Set back to *The screen I was last on*; sign out and in: lands where you were | |
| QA-SIG-18 | Sign in as a user in **two** firms (the platform administrator can add admin@qb01.test to a second firm under Settings > Platform > User-Firm Assignments) and open My preferences | **Start in firm** offered, listing only that user's firms. Choosing one changes nothing now | Next sign-in starts in the chosen firm | |
| QA-SIG-19 | User menu > **My profile** > Change password: new `Short@1` | Refused beside the box: "Use at least 12 characters." | New `LongEnoughPassw0rd`: "Include a symbol." Wrong current password: "Current password is incorrect." Do not finish the change | |
| QA-SIG-20 | User menu > **Sign out** | Back on the sign-in screen | Signing in again restores the favourites and preferences | |

---

## Users & roles

**Before you start:** the firm exists (FRM cases). Sign in as admin@qb01.test.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-USR-01 | Settings > Platform > **Users** > + New: Arun Kumar, arun@qb01.test, password, **Require password change** off, Job template **Field Sales**, firm QB01. Save | Created and listed | Settings > Platform > **Audit Logs**: user created, naming you | |
| QA-USR-02 | Create the other five people from *Sample data* the same way (Meena with **Require password change** on) | All listed with their job | -- | |
| QA-USR-03 | Sign in as meena@qb01.test | Only the change-password screen is reachable. `Short@1` refused ("Use at least 12 characters."); `Counter-Passw0rd!` accepted and the app opens | -- | |
| QA-USR-04 | As Meena, open each menu | Sell and Stock offered. The only money screens are **Receipts** (Sell) and **Payments** (Buy). No Journal Entries, Ledgers, Trial Balance anywhere; no Platform under Settings | -- | |
| QA-USR-05 | Sign in as arun@qb01.test; open every menu | No Commission, Credit Notes, Price Lists, Promotions, GST Returns or TCS; no Platform section | Settings > Selling > **Credit Control** opens read-only: "Changing the policy needs the manage customer settings permission." | |
| QA-USR-06 | Sign in as priya@qb01.test (Sales Manager) | Sell screens, Commission and Targets offered (confirm) | Credit Control opens **read-only** (a manager may not switch the limit off); TCS Settings read-only (confirm) | |
| QA-USR-07 | Sign in as anita@qb01.test (Accounts) | Accounts drop-down: Journal Entries, Expenses, Ledgers, Bank Reconciliation, Trial Balance, Profit & Loss, Balance Sheet, GST Returns all open | -- | |
| QA-USR-08 | As admin: Settings > Platform > **Roles** > New. Code `qb-night-desk`, name Night Desk. In Permissions search `FIRM_CREATE`, then `AUDIT_LOG_VIEW` | Neither code is offered (platform codes are never offered to a firm administrator) | -- | |
| QA-USR-09 | Same form: tick SALES_VIEW, CUSTOMER_VIEW, RECEIPT_VIEW, RECEIPT_CREATE. Save | Created, marked **Custom role**, offers Edit | -- | |
| QA-USR-10 | Roles > New with code `platform_admin` | Refused: "'platform_admin' is reserved. Choose a different role code." Nothing created | -- | |
| QA-USR-11 | Users > + New: Nikhil Night, nightdesk@qb01.test, no job template, Roles in this firm: **Night Desk** only. Sign in as him | Sell > Receipts offered with **+ New** (Record receipt) | -- | |
| QA-USR-12 | Two windows: Nikhil signed in (A); admin (B) edits Night Desk, unticks RECEIPT_CREATE, Save. In A click anything | A is **signed out on that click** | Signed back in, Receipts still opens but + New (record receipt) is gone | |
| QA-USR-13 | Sign-in screen: kiran@qb01.test with `Wrong@Password1` five times, then the right password | Times 1-4: "Invalid email or password." Time 5 and the right password: "This account is locked after too many failed sign-in attempts. You can try again in 15:00.", counting down | -- | |
| QA-USR-14 | As admin: Users > Kiran > Edit > tick **Clear login lock** > Save. Sign in as Kiran | Signs in at once | Audit Logs records the change | |
| QA-USR-15 | Users > pick Arun > **Hire like this person**: Arjun Test, arjun@qb01.test | New user with the same roles as Arun (Field Sales), none of Arun's personal details | Delete Arjun afterwards: gone from the list; the audit trail keeps the row | |
| QA-USR-16 | Settings > Platform > **User Templates** | The platform's templates (Firm Administrator, Field Sales ...) listed and locked (no Edit) | -- | |

---

## Firm set-up & configuration

**Before you start:** nothing. Sign in as the **platform administrator**.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-FRM-01 | Sign in as the platform administrator | Starts on **Platform** (no firm); switcher reads Platform | -- | |
| QA-FRM-02 | Settings > Platform > **Firms** > + New: type only the name `QA Book Traders`, Save | Refused: code, country, currency and financial year start are also required | Nothing listed | |
| QA-FRM-03 | Fill the firm table from *Sample data*, code typed as `qb01`. Save | Saved; code stored as **QB01**. The first shared firm on a new install takes noticeably longer | Firms list shows it; firm switcher now offers it | |
| QA-FRM-04 | Pick QB01 > **Set up** | Titled *Set up QB01*; verdict **Cannot post documents yet**; rows Storage (done), Business profile, Books, Tax, Geography, Branches and warehouses, People | -- | |
| QA-FRM-05 | Business profile row: **Food Distribution** > Assign | Row reads Assigned: FOOD | Settings > Business profile > Profile Assignment shows QB01 on Food Distribution | |
| QA-FRM-06 | Books row > **Open the books**. Then press it again if still offered | Notice names the year starting 2026-04-01; row shows the accounts, 1 financial year, 12 periods, control accounts mapped; verdict **Can post documents**. A second press creates nothing | Switch into QB01: Accounts > All Accounts screens > Books > **Chart of Accounts** lists Cash 1000, Bank 1010, Trade Receivables 1100, Inventory 1200, Trade Payables 2100, Sales 4000, Cost of Goods Sold 5200 among others | |
| QA-FRM-07 | Tax row > **Apply GST template** | "GST set up: 10 tax profiles and 13 rules." (confirm counts). Geography turns done (1 country) | A product's tax profile list offers GST 0%, 5%, 12%, 18% Local and Interstate, Exempt | |
| QA-FRM-08 | Branches and warehouses > **Create head office and main warehouse** | "Created branch HO and warehouse MAIN." | Masters > Branches and Warehouses list them | |
| QA-FRM-09 | Switch into QB01; Settings > Set up > Locations > **Places**: open India, add the two states, districts and cities from *Sample data* | Each level saves and lists under its parent | A customer address picker offers India > Tamil Nadu > Chennai > Chennai | |
| QA-FRM-10 | Settings > Platform > Users > + New: Firm Admin QB, admin@qb01.test, password, Require password change off, Job template **Firm Administrator**, firm QB01 | Created | Set up panel: People 1 member; verdict **Finished. Every step is done.** No buttons left | |
| QA-FRM-11 | Sign out; sign in as admin@qb01.test | Opens in QB01 on Home | -- | |
| QA-FRM-12 | Masters > **Warehouses** > + New: branch HO, code `STORE2`, name Back Store. Save | Listed beside MAIN | -- | |
| QA-FRM-13 | Settings > Firm > **Numbering Series**; open the sales invoice series; press Preview twice | Each document type with its next number, the counter locked (padlock, no box to type). Preview shows the same next number both times | Preview issues nothing: the first invoice later still takes that number | |
| QA-FRM-14 | Settings > Selling > **Sales Stages** | Quotation, Sales order and Delivery note stages all **on** (defaults). Close without saving | -- | |
| QA-FRM-15 | Settings > Selling > **Credit Control** | When a customer reaches their limit: **Warn**; warn at 80; block at 100 | Used in QA-SELL-18 | |
| QA-FRM-16 | Settings > Tax > **GST Documents** | Dispatch of a sale before its invoice: **Warn**; e-invoicing date blank; E-invoice filing **Sandbox**; claim input credit on all bills | -- | |
| QA-FRM-17 | Settings > Stock > **Batch Rules** | Near expiry 30 days; near-expiry batch leaving: Warn; FEFO skip: Record; may be sold below price floor ticked | -- | |
| QA-FRM-18 | Settings > Tax > **Rule Simulator**: 1,000 at GST 18% Local, buyer in Tamil Nadu; then buyer in Karnataka | Local: CGST 9% 90.00 + SGST 9% 90.00, tax 180.00. Inter-state: matched rule INTERSTATE_GST_18, IGST 18% 180.00 | -- | |
| QA-FRM-19 | Settings > Business profile > **Feature Management** (as platform administrator): open Food Distribution, try to switch on **IMEI**, Save | Refused: "These features are not implemented yet and cannot be enabled: IMEI." Nothing saved | Food Distribution lists BATCH_TRACKING and EXPIRY_TRACKING | |
| QA-FRM-20 | Settings > Set up > Account structure > **Control Accounts** | One row per posting purpose, each naming its account (Accounts receivable > 1100 Trade Receivables, Cash > 1000 Cash ...) with Change offered while nothing has posted | After the first posting, that row shows a lock and the count of posted lines | |

---

## Masters (customers, vendors, products, custom fields, merge duplicates)

**Before you start:** the firm is finished and Places exist. Sign in as
admin@qb01.test.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-MST-01 | Settings > Set up > Item lists > **Product Categories** > New: `CLEAN` Cleaning; `GROC` Grocery | Both listed | -- | |
| QA-MST-02 | Masters > **Products** > + New: QB-DET from the products table (category Cleaning, PIECE x4, GST 18% Local, HSN 340220, buy 80, sell 100, MRP 110) | Opens as a tab with General, UOM & Size, Pricing, Tax. Side panel **Margin 20.00 · 20.0%** while typing | Type selling 120 for a moment: warned it is above MRP 110; put 100 back | |
| QA-MST-03 | **Save product**; reopen it (pick, F2) | Tab titled Detergent Powder 1 kg; units, category and tax profile read as names, not codes | Ctrl+K `Detergent` finds it | |
| QA-MST-04 | Create QB-FLR, QB-TEA and QB-TEA100 from the table | Saved | -- | |
| QA-MST-05 | Create QB-GHEE; in **UOM & Size** tick **Track batch** and **Track expiry**; Batch issue rule *Earliest expiry first* | Saved; reopened, both ticks hold | On a Wholesale firm Track expiry would be refused; here it is allowed by Food Distribution | |
| QA-MST-06 | Masters > **Vendors** > + New: QB-V1 Sunrise Distributors with address and bank account. **Save vendor** | Saved; reopened, side panel shows the account under *Pay to* | -- | |
| QA-MST-07 | Edit QB-V1, change **only** the phone to `+914424440009`; save and reopen | Phone changed; address, bank account and everything else unchanged | -- | |
| QA-MST-08 | Create QB-V2 Deccan Foods (Karnataka) | Saved | -- | |
| QA-MST-09 | Masters > **Customers** > + New: QB-C1 Ravi Traders; type the GSTIN and leave PAN blank; Money: credit limit 10000, payment terms 30. **Save customer** | Saved; PAN reads AAFCR1111R (filled from the GSTIN); outstanding 0.00 | Side panel shows GSTIN and credit limit 10,000.00 | |
| QA-MST-10 | Create QB-C2 Bharat Stores and QB-C3 Lakshmi Provisions | Saved; QB-C3's side panel reads *unregistered* | -- | |
| QA-MST-11 | New customer: code QB-C4, name Test PAN, GSTIN `33AAFCR1111R1ZE`, PAN `AAAPZ1234Z` | Refused, naming both the GSTIN's PAN and the typed PAN | Cancel; nothing saved | |
| QA-MST-12 | New customer: code `QB-C1` again, name anything | Refused: "Customer code QB-C1 already exists in this firm." | -- | |
| QA-MST-13 | New customer: save with the name empty | Refused, naming the field | -- | |
| QA-MST-14 | New customer QB-C5 *Ravi Traders Branch* with Ravi's GSTIN `33AAFCR1111R1ZE`; Save | Asked "Same GSTIN or PAN on another customer", naming QB-C1. **Cancel** keeps everything typed and saves nothing | Then close without saving | |
| QA-MST-15 | Edit QB-C1, change **only** the phone to `+919840011109`; save, reopen | Phone changed; address, GSTIN, credit limit 10,000, terms 30 and outstanding 0.00 unchanged | Audit Logs: customer updated, naming you | |
| QA-MST-16 | Settings > Firm > **Custom Fields** > New: label *FSSAI licence no*, applies to Customer, type Text. Open QB-C3 | A Custom fields section with **FSSAI licence no**. Type `FSSAI-33-1001`, save, reopen: kept | Edit only the phone again: the licence is still there | |
| QA-MST-17 | Edit the field to **Required**. New customer QB-C6 without it | Refused on the form: "FSSAI licence no is required." | Set the field back to not required | |
| QA-MST-18 | New customer QB-C9 *Ravi Traders Chennai* with phone `+919840011109` (Ravi's) | Before saving, a duplicate warning names QB-C1; it does not block. Save anyway | -- | |
| QA-MST-19 | Masters > Customers: pick QB-C9 > **Merge into...** > QB-C1 > confirm | QB-C9 leaves the list | QB-C1's statement and balances unchanged (QB-C9 had nothing); Audit Logs records the merge | |
| QA-MST-20 | Masters > Products > + New with the **code left blank**: *Test Item*, any unit and tax profile. Save. Then pick it > Delete | Editor says *Blank: issued on save*; saved with a code from the PRD series (e.g. PRD-00001). Delete succeeds (no stock, no documents) | -- | |
| QA-MST-21 | Masters > Customers > ... > **Export** | A save dialog suggesting a .csv; the file holds the three customers | -- | |

---

## Purchasing

**Before you start:** suppliers QB-V1 and QB-V2 and the products exist.
Sign in as admin@qb01.test. Requisition -> order -> approval -> goods
receipt -> purchase invoice -> payment -> return and debit note.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-BUY-01 | Buy > All Buy screens > Documents > **Requisitions** > + New: QB-FLR x 50, supplier QB-V1 > Submit > Approve > **Convert to orders** | Numbered from its own series; reads **Ordered** | Buy > Purchase Orders: a **draft** order to Sunrise for 50 x 40: taxable 2,000.00, CGST 180.00, SGST 180.00, total 2,360.00. **Cancel** that draft; nothing else moves | |
| QA-BUY-02 | Buy > **Purchase Orders** > + New: QB-V1; Branch HO, receives into MAIN; QB-DET x 100 (rate fills at 80); QB-TEA x 50 (rate 160) | Before saving: taxable **16,000.00**, CGST **920.00**, SGST **920.00**, total **17,840.00**; Tax box reads CGST + SGST | Side panel shows the line's rate, tax split and stock | |
| QA-BUY-03 | **Save draft**; reopen it | Draft, number starting PO-. **Approve is not offered**, only Send for approval | No stock movement; no journal (Accounts > Journal Entries unchanged) | |
| QA-BUY-04 | **Send for approval**, then **Approve** | Status **Approved** | Still no stock and no journal: an order is a promise only | |
| QA-BUY-05 | Buy > **Goods Receipts** > + New > the order. Accept QB-DET **60**, QB-TEA **50**; warehouse MAIN. Save receipt, then **Complete** | Draft, then **Completed** | Order reads **Partially received**. Stock > Stock Summary: DET 60, TEA 50 | |
| QA-BUY-06 | Accounts > **Journal Entries** > the receipt's GRN- entry | Dr Inventory 12,800.00 / Cr Goods Received Not Invoiced 12,800.00 (at cost, no tax) | Stock > **Stock Ledger**, QB-DET: GOODS_RECEIPT +60 naming the receipt | |
| QA-BUY-07 | Goods Receipts > + New against the same order | DET starts at the remaining **40** (received before 60). Save and Complete | Order reads **Received**; Stock Summary DET 100. Journal Dr Inventory 3,200.00 / Cr Goods Received Not Invoiced 3,200.00 | |
| QA-BUY-08 | Buy > **Purchase Invoices** > + New > the first receipt (60 + 50). Supplier's invoice number `SD-1001`, date today | Before saving: taxable **12,800.00**, CGST **632.00**, SGST **632.00**, total **14,064.00**. Save bill, then **Approve** | Journal: Dr Goods Received Not Invoiced 12,800.00, Dr Input CGST 632.00, Dr Input SGST 632.00 / Cr Trade Payables 14,064.00. Inventory untouched | |
| QA-BUY-09 | Start a bill for the second receipt and type `SD-1001` again | Warning: a purchase invoice with this supplier invoice number already exists | Cancel without saving | |
| QA-BUY-10 | Purchase Invoices > + New > the second receipt (DET 40), number `SD-1002` > Save > Approve | Total **3,776.00** (3,200.00 + CGST 288.00 + SGST 288.00) | Buy > **Supplier Statements**, QB-V1: two bills, owed 17,840.00 | |
| QA-BUY-11 | Goods Receipts > the second receipt > **Cancel** | Refused: it has been invoiced, "...Cancel the purchase invoice first, or raise a purchase return." Nothing changes | -- | |
| QA-BUY-12 | Buy > **Payments** > + New: paid to QB-V1, amount **14,064.00**, method Bank, oldest first > Record | Notice that PY-... was recorded and posted | Journal: Dr Trade Payables 14,064.00 / Cr Bank 14,064.00. A new payment for QB-V1 offers only SD-1002 | |
| QA-BUY-13 | Buy > Returns & notes > **Purchase Returns** > + New off bill SD-1002: try Returning **50** on the DET line | Refused: more than was received on that line (confirm wording) | -- | |
| QA-BUY-14 | Same return: Returning **5** > Save > Approve > **Complete** | Credit **472.00** (400.00 + CGST 36.00 + SGST 36.00); Completed | Stock Summary DET **95**; Stock Ledger RETURN -5. Journal: Dr Trade Payables 472.00 / Cr Inventory 400.00 / Cr Input CGST 36.00 / Cr Input SGST 36.00. SD-1002 now owes 3,304.00 | |
| QA-BUY-15 | Buy > Returns & notes > **Debit Notes** > + New against SD-1002: **100** on the DET line, reason Price difference > Save > Approve | Tax 18.00 (CGST 9.00 + SGST 9.00), total **118.00** | Journal: Dr Trade Payables 118.00 / Cr Purchase Price Variance 100.00 / Cr Input CGST 9.00 / Cr Input SGST 9.00. SD-1002 owes **3,186.00**; no stock moves | |
| QA-BUY-16 | Buy > **Supplier Statements**, QB-V1 | Bills 14,064.00 and 3,776.00; payment 14,064.00; return 472.00; debit note 118.00; closing **3,186.00** owed | Running balance in date order | |
| QA-BUY-17 | Purchase Orders > + New: QB-V2 (Karnataka), QB-TEA x 20 at 160 | Tax box reads **IGST**: taxable 3,200.00, IGST 160.00, total 3,360.00. Send for approval, Approve | -- | |
| QA-BUY-18 | Receive all 20 (Complete); bill it as `DF-0055`, approve | Bill total **3,360.00** | Stock Summary TEA **70**. Journal: Dr Goods Received Not Invoiced 3,200.00, Dr Input IGST 160.00 / Cr Trade Payables 3,360.00 | |
| QA-BUY-19 | Masters > Vendors > + New QB-V9 *Blocked Test*, status **Blocked**, reason *Quality issues*. Then a purchase order to it | Order refused, repeating "Quality issues" | Delete QB-V9 afterwards | |
| QA-BUY-20 | Sign in as suresh@qb01.test (Warehouse); open Buy | Goods Receipts offered; Payments and Approve on orders not offered (confirm) | -- | |

---

## Inventory

**Before you start:** Purchasing done (DET 95, TEA 70 in MAIN). Sign in as
admin@qb01.test.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-INV-01 | Stock > All Stock screens > Movements > **Opening Stock** > New opening stock: HO, MAIN, reference `QB-OPEN`, posting date today; the three lines of the opening stock table (with batch and expiry for Ghee). Save, then **Post** | Posted | Stock Summary: FLR 100, GHEE 60. Journal QB-OPEN: Dr Inventory 18,400.00 / Cr Opening Balance Equity 18,400.00 | |
| QA-INV-02 | Stock > **Stock Summary** | DET 95 (7,600.00), TEA 70 (11,200.00), FLR 100 (4,000.00), GHEE 60 (14,400.00); no negative quantity | Total 37,200.00 | |
| QA-INV-03 | Stock > **Stock Ledger**, QB-DET | GOODS_RECEIPT +60, +40; RETURN -5; each naming its document; running balance ends at **95** | Agrees with Stock Summary | |
| QA-INV-04 | Stock > **Batches**, search QB-GHEE | G-101: 20, expiry today + 20; G-102: 40, expiry today + 180 | -- | |
| QA-INV-05 | Stock > **Expiry Monitor** | G-101 counted under *Expire in 30 days*; G-102 not near expiry | -- | |
| QA-INV-06 | Stock > **Stock Transfers** > + New: MAIN to STORE2, QB-FLR x 10 > Save > **Dispatch** | Numbered TO-...; dispatched | MAIN FLR **90**; the 10 shown in transit to STORE2. Accounts > Journal Entries: **nothing new** (moving stock posts nothing) | |
| QA-INV-07 | **Receive** the transfer, all 10 arrived; print the **challan** | Received; final | STORE2 FLR **10**. Challan carries no values | |
| QA-INV-08 | Stock Transfers > + New: MAIN to STORE2, QB-FLR x **999** > Dispatch | Refused: not that much free in MAIN (confirm wording) | Nothing moves | |
| QA-INV-09 | Stock > **Physical Count** > Open Count: HO, MAIN, today. Find QB-FLR (expected 90), type Counted **88**; leave other lines blank. Save progress, reopen, **Post count** | Difference reads -2 while typing; list shows "1 of N lines counted", then posted; the sheet is read-only | MAIN FLR **88**; Stock Ledger ADJUSTMENT -2 naming the count. Journal: Dr Inventory Adjustment 80.00 / Cr Inventory 80.00. Uncounted lines moved nothing | |
| QA-INV-10 | Stock > All Stock screens > Stock > **Inventory**: pick QB-DET / MAIN > **Write off** 1, reason Damage, reference `QB-WO1` | "Stock written off." | DET **94**; Stock Ledger WRITE_OFF -1. Journal: Dr Inventory Adjustment 80.00 / Cr Inventory 80.00 | |
| QA-INV-11 | Stock > All Stock screens > Movements > **Repacking** > New: consume QB-TEA x 2, produce QB-TEA100 x 5, wastage 0 > Post | Posted | TEA **68**; TEA100 **5** at cost 64.00 each (the 320.00 consumed). No journal (no wastage) | |
| QA-INV-12 | Masters > Products > + New `QB-COMBO` *Cleaning Combo*, type **Bundle**, GST 18% Local, HSN 340220, sell 170; **Components**: QB-DET x 1, QB-FLR x 1. Save; then **Assemble** 5 (confirm where the button sits) | Kit saved; 5 assembled | DET **89**, FLR MAIN **83**, COMBO **5** carrying cost 120.00 each (80 + 40) | |
| QA-INV-13 | Settings > Stock > **Adjustment Limits**: Warehouse role **500** > Save. Sign in as suresh@qb01.test; write off QB-TEA x 5 (worth 800.00) | Refused, naming the limit; offers **Submit for approval**. Submit it | As admin: Stock > All Stock screens > Movements > **Adjustment Approvals**: **Reject** with reason *test only*. TEA stays 68. Clear the limit afterwards | |
| QA-INV-14 | Stock > Stock Summary (end of module) | DET 89, TEA 68, TEA100 5, FLR 93 (MAIN 83 + STORE2 10), GHEE 60, COMBO 5 | Total value **37,040.00** (confirm) | |
| QA-INV-15 | Reports > Operational > **Stock valuation** for today | Same quantities and value as Stock Summary | Its last rows show the Inventory account beside it, agreeing (confirm) | |

---

## Selling

**Before you start:** stock as at the end of Inventory. Sign in as
admin@qb01.test. Enquiry -> quotation -> order -> delivery note -> invoice
-> receipt, then credit limit, returns, notes and the counter.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-SELL-01 | Sell > All Sell screens > Documents > **Enquiries** > + New: prospect *Kumar Stores*, phone `+919840055501`, city Chennai, source Walk-in, expected value 1,000, next follow-up tomorrow; line QB-DET x 10. Save | Numbered ENQ-..., open | Listed under *Follow-ups due* tomorrow | |
| QA-SELL-02 | On it: **Convert to quotation** | A customer *Kumar Stores* is created (code from the CUS series) and a draft quotation: 10 x 100, taxable 1,000.00, CGST 90.00, SGST 90.00, total 1,180.00 | Masters > Customers lists Kumar Stores. Nothing reserved, nothing posted | |
| QA-SELL-03 | Open that quotation > Mark as sent > Customer accepted > **Convert to order**. Leave the order as a draft | Order SO-... drafted | The enquiry now reads **WON** | |
| QA-SELL-04 | Enquiries > + New: prospect *Test Lost*, any line > Save > **Lost**, reason from the list | Reads Lost; a reason is required | Reports > Operational > **Enquiries lost** counts it with its expected value | |
| QA-SELL-05 | Sell > **Quotations** > + New: Ravi Traders; QB-DET x 10, QB-TEA x 5 | Rates fill at 100 and 200. Taxable **2,000.00**, CGST **115.00** (90.00 + 25.00), SGST **115.00**, total **2,230.00**, in words. Place of supply Tamil Nadu, CGST + SGST | Save draft: QT-... | |
| QA-SELL-06 | Mark as sent > Customer accepted (reason) > **Convert to order** | Last notice names the SO-... and says approving reserves the stock. Convert is no longer offered | Quotation moved nothing: stock, balance and journals unchanged | |
| QA-SELL-07 | Sell > **Sales Orders** > the new order > **Approve** | Approved; no credit warning (22% of the limit) | Stock > All Stock screens > Stock > Inventory: DET on hand 89, reserved 10, available 79; TEA reserved 5. No journal | |
| QA-SELL-08 | Sell > **Delivery Notes** > + New > the order: DET 10, TEA 5 from MAIN. Save > Approve > **Dispatch** | Asked: no approved invoice, policy Warn; offers Dispatch and invoice / Dispatch anyway / Cancel. Choose **Dispatch anyway**: Dispatched; order **Delivered** | Stock: DET **79**, TEA **63**, reserved 0. Stock Ledger DISPATCH -10 / -5. Journal DN-...: Dr Cost of Goods Sold 1,600.00 / Cr Inventory 1,600.00 (800 + 800). Audit trail keeps the warning | |
| QA-SELL-09 | Sell > **Sales Invoices** > + New, bill from delivery notes: Ravi Traders (its note is ticked). Type **11** in DET's quantity | Red; cannot save: only 10 left to bill | -- | |
| QA-SELL-10 | Set DET back to 10. Read totals. **Save & print** | Taxable 2,000.00, CGST 115.00, SGST 115.00, total **2,230.00**. Every copy's banner: *DRAFT - NOT A TAX INVOICE - NOT YET APPROVED*. Cancel the print | -- | |
| QA-SELL-11 | On the list pick the invoice > **Approve** | Approved; number from the invoice series | Journal SI-...: Dr Trade Receivables 2,230.00 / Cr Sales 2,000.00 / Cr Output CGST 115.00 / Cr Output SGST 115.00 (confirm the per-head legs; older builds showed one Output Tax line). Customer side panel: outstanding **2,230.00**. Home > RECENT INVOICES lists it | |
| QA-SELL-12 | **Print** the approved invoice | TAX INVOICE, no draft banner; both GSTINs; place of supply Tamil Nadu (33); HSN 340220 and 090230; CGST/SGST at 9% and 2.5%; HSN summary; total in words | -- | |
| QA-SELL-13 | Sell > **Receipts** > + New: Ravi Traders, **2,230.00**, Bank; apply 2,230.00 to the invoice > Record | RC-... recorded and posted | Journal: Dr Bank 2,230.00 / Cr Trade Receivables 2,230.00. Ravi outstanding **0.00**. A new receipt no longer offers the invoice. No TCS charged | |
| QA-SELL-14 | Sales Invoices > the paid invoice > **Cancel** | Refused: cannot be cancelled while it has money applied from RC-...; "Reverse or cancel those first." | -- | |
| QA-SELL-15 | Sell > Sales Orders > + New: Bharat Stores, QB-DET x 20 | Place of supply Karnataka · **IGST**: taxable 2,000.00, IGST **360.00**, total **2,360.00**. Save, Approve | -- | |
| QA-SELL-16 | Delivery Notes > + New > that order > Save > Approve > **Dispatch and invoice** | "Dispatched and invoiced as SI-..."; the invoice is approved, total 2,360.00 | DET **59**. Journals: Dr Cost of Goods Sold 1,600.00 / Cr Inventory 1,600.00; Dr Trade Receivables 2,360.00 / Cr Sales 2,000.00 / Cr Output IGST 360.00 | |
| QA-SELL-17 | Sell > Returns & notes > **Customer Debit Notes** > + New: Bharat's invoice, reason Price increase, **100** on the DET line > Save > Approve | Tax **18.00** (IGST, the line's rate), total **118.00** | Journal: Dr Trade Receivables 118.00 / Cr Sales 100.00 / Cr Output IGST 18.00. Bharat outstanding **2,478.00**; a new receipt lists the invoice at 2,478.00 on one row. Cancelling the invoice is refused naming the debit note | |
| QA-SELL-18 | Sales Invoices > **+ New by product** (counter bill): Lakshmi Provisions; QB-TEA x 2, QB-FLR x 4. Tender **Cash 700** | Taxable 600.00, CGST **28.00** (10.00 + 18.00), SGST 28.00, total **656.00**; the tender panel shows change **44.00** | -- | |
| QA-SELL-19 | Change the tender to Cash **656.00**; press **Save & print (F9)** | Bill approved and printed; a new blank bill opens | Bill shows paid; Sell > Receipts lists a cash receipt of 656.00 applied to it. Journals: the bill, and Dr Cash 656.00 / Cr Trade Receivables 656.00; cost 480.00 to Cost of Goods Sold (confirm). TEA **61**, FLR MAIN **79** | |
| QA-SELL-20 | Sales Orders > + New: Ravi Traders, QB-GHEE x 10 at 300 > Save > Approve | Taxable 3,000.00, CGST 75.00, SGST 75.00, total **3,150.00**. Approved | Stock > Batches: G-101 has 10 reserved (earliest expiry first) | |
| QA-SELL-21 | Pick that order > **Hold**, reason `awaiting cheque`. Then Delivery Notes > + New > the order > Save | Order reads *Approved (on hold)*. The note is refused: "SO-... is on hold and cannot be dispatched ("awaiting cheque"). Release it first." | Reserved stays 10 | |
| QA-SELL-22 | Sales Orders > the order > **Release**. Delivery Notes > + New > the order | Order back to Approved. Side panel lists G-101 (near expiry, about 20 days left) pre-filled with 10, and G-102 with 0 | -- | |
| QA-SELL-23 | Save > Approve > **Dispatch and invoice** | Dispatched and invoiced; invoice 3,150.00 approved | Batches: G-101 **10**, G-102 40. Journal: Dr Cost of Goods Sold 2,400.00 / Cr Inventory 2,400.00. Ravi outstanding **3,150.00** | |
| QA-SELL-24 | Sales Orders > + New: Ravi Traders, QB-DET x 50 and QB-TEA x 10 (total 8,000.00) > Save > **Approve** | Warning: "Ravi Traders would be at 111.5% of a 10000.00 credit limit, ..." and the order **is approved** (policy Warn) | Then **Cancel** the order (reason *test*): DET and TEA reservations released | |
| QA-SELL-25 | Settings > Selling > Credit Control: **Block** (warn 80, block 100) > Save. Raise the same order again > Approve | Refused: "Ravi Traders would be at 111.5% of a 10000.00 credit limit. Collect payment or raise the limit before continuing." Order stays Draft | Set Credit Control back to **Warn**; delete the draft | |
| QA-SELL-26 | Sales Orders > + New: Lakshmi Provisions, QB-FLR x **100** (MAIN holds 79) > Approve; Delivery Notes > + New for 100 > Save > Approve > Dispatch | Dispatch is refused: not enough available stock (confirm whether approval already warns or back-orders 21) | No DISPATCH in the Stock Ledger. Cancel the note and the order | |
| QA-SELL-27 | Sell > Returns & notes > **Sales Returns** > + New, returned against the first Ravi invoice, taken back into MAIN; DET Returning **12** | Red; saving refused: only 10 went out on this line | -- | |
| QA-SELL-28 | Returning **2** > Save draft > Approve > **Complete** | Before saving: credit to customer **236.00** (200.00 + 18.00 + 18.00). After Complete: 2 back on the shelf, 236.00 credited | DET **61**; Stock Ledger SALES_RETURN +2. Journals: Dr Sales Returns 200.00 / Dr Output CGST 18.00 / Dr Output SGST 18.00 / Cr Trade Receivables 236.00; and Dr Inventory 160.00 / Cr Cost of Goods Sold 160.00. Ravi outstanding **2,914.00** | |
| QA-SELL-29 | Sell > Returns & notes > **Credit Notes** > + New: the Ghee invoice, reason Rate difference, **100** on the line > Raise > Approve | Tax back **5.00**, total **105.00**; row reads 105.00 (tax 5.00) | Journal: Dr Sales Returns 100.00 / Dr Output CGST 2.50 / Dr Output SGST 2.50 / Cr Trade Receivables 105.00. Ravi outstanding **2,809.00**. No stock moves | |
| QA-SELL-30 | Credit Notes > + New on the same line, **4,000** | Refused: "A credit note cannot credit more than the line was charged: 3000.0000 charged, 100.0000 already credited." | Cancel | |
| QA-SELL-31 | Approve Kumar Stores' draft order from QA-SELL-03. Sell > All Sell screens > Documents > **Proforma** > New > that order > Raise > **Issue** | PF-... number (its own series); "Not a tax invoice" | No journal; Kumar's outstanding unchanged. Then **Cancel** the order: the proforma's lines and total stay as raised. DET available back to 61 | |
| QA-SELL-32 | Sell > **Customer Statements** > Ravi Traders, this month | Invoice 2,230.00, receipt 2,230.00, invoice 3,150.00, return 236.00, credit note 105.00; closing **2,809.00**, in date order | Ageing: everything in the first band; the buckets add up to the total and the reconciliation line explains any gap to the balance | |
| QA-SELL-33 | Masters > Customers > Ravi Traders > **Delete** | Refused: "QB-C1 cannot be deleted: it ... Settle, refund or cancel what is open first, or set the customer inactive to stop trading with them." | -- | |
| QA-SELL-34 | Masters > Products > QB-DET > **Delete** | Refused: "QB-DET cannot be deleted: it holds ... Move or write off the stock ... or set the product inactive to stop trading it." | -- | |
| QA-SELL-35 | My preferences > Date format **yyyy-MM-dd** > Save; open the first Ravi invoice. Then set dd-MM-yyyy back | Its date reads 2026-10-04 style; then 04-10-2026 style | Lists show the same format | |
| QA-SELL-36 | Stock > Stock Summary (end of module) | DET 61, TEA 61, TEA100 5, FLR 89 (MAIN 79 + STORE2 10), GHEE 50, COMBO 5 | Value **31,120.00** (confirm) | |

---

## Pricing & incentives

**Before you start:** Selling done. Sign in as admin@qb01.test. Read each
quotation's figures **before saving** and then close it without saving,
unless the case says to save. Commission comes first, before any discount
exists, so its sale is at full price.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-PRC-01 | Sell > All Sell screens > Incentives > **Commission** > Add rule: applies to Arun Kumar, paid on **Money collected**, percentage of the value **2**, Active | Rule listed | -- | |
| QA-PRC-02 | Sell > All Sell screens > Incentives > **Targets** > New: Arun Kumar, this month, **10,000** | Listed | -- | |
| QA-PRC-03 | Sales Orders > + New: Lakshmi Provisions, salesman **Arun Kumar**, QB-FLR x 10 > Approve > delivery note > **Dispatch and invoice**. Then Receipts > + New: 590.00 Cash against it | Order taxable 500.00, CGST 45.00, SGST 45.00, total **590.00**; invoice approved; receipt recorded | FLR MAIN **69**. Journal: Dr Cost of Goods Sold 400.00 / Cr Inventory 400.00; Dr Trade Receivables 590.00 / Cr Sales 500.00 / Cr Output CGST 45.00 / Cr Output SGST 45.00; Dr Cash 590.00 / Cr Trade Receivables 590.00 | |
| QA-PRC-04 | Commission > **Collected** view, this month > Show | Arun: collected 590.00, commission **10.00** (2% of 500.00; tax earns nothing) (confirm) | -- | |
| QA-PRC-05 | Commission > **Accrue period** this month; on Arun's draft **Approve**, then **Pay** from 1000 Cash | Payout 10.00, Draft > Approved > Paid | Journals: Dr Commission Expense 10.00 / Cr Commission Payable 10.00 at approval; Dr Commission Payable 10.00 / Cr Cash 10.00 at payment (confirm) | |
| QA-PRC-06 | Accrue the same period again | Refused: "A commission payout already covers part of that period for this salesman (...)." | -- | |
| QA-PRC-07 | Targets > **Achievement**, this month | Arun: target 10,000, achieved (the 590.00 bill; confirm whether tax is counted), **Missed**, short by the rest | -- | |
| QA-PRC-08 | Settings > Set up > Pricing > **Price Lists** > New: QB-STD from *Sample data* > Save | Listed: applies to Everyone, DET 2% and from 20: 5% | -- | |
| QA-PRC-09 | Sell > Quotations > + New: Ravi Traders, QB-DET x 10, discount blank | Side panel: **2% from the price list**. Taxable **980.00**, CGST 88.20, SGST 88.20, total **1,156.40** | Close without saving | |
| QA-PRC-10 | Same, quantity **20** | **5%** from the price list (highest break at or below the quantity): taxable 1,900.00, tax 342.00, total **2,242.00** | -- | |
| QA-PRC-11 | Masters > Customers > Ravi Traders > Money > Default discount % **3** > Save. Quote QB-TEA x 5 and QB-DET x 10 | TEA: **3% from the customer's standing rate**: taxable 970.00, CGST 24.25, SGST 24.25. DET: still **2% from the price list** (a list beats the standing rate) | -- | |
| QA-PRC-12 | Settings > Set up > Party lists > **Customer Groups** > New `RETAIL` Retailer, default discount 1; put Lakshmi Provisions in it. Quote Lakshmi QB-TEA x 10 | **1% from the customer group**: taxable 1,980.00, CGST 49.50, SGST 49.50, total **2,079.00** | Customer Groups > Remove RETAIL: refused, 1 customer still in it | |
| QA-PRC-13 | Settings > Set up > Pricing > **Promotions** > + New: QB-BULK from *Sample data*, Active. Quote Ravi QB-DET x **50** | **10% from a promotion** (beats the list): taxable 4,500.00, tax 810.00, total **5,310.00** | -- | |
| QA-PRC-14 | Same line: type **0** in Disc % | 0% typed (refuses every arrangement): taxable 5,000.00, tax 900.00, total **5,900.00** | -- | |
| QA-PRC-15 | Type **12** instead | 12% typed: taxable 4,400.00, tax 792.00, total **5,192.00** | -- | |
| QA-PRC-16 | Promotions > open QB-BULK > Edit, change only the description > Save | "Promotion QB-BULK saved as a new revision; the one you opened is now inactive." | Its claims and limits follow the offer, not the row | |
| QA-PRC-17 | New promotion QB-WELCOME (*Only with a coupon*, 4%). In its **Coupons** view: + New `QBW1`, total claims allowed 1. Quote Ravi QB-DET x 10: coupon blank, then `QBW1`, then `NOSUCHCODE` | Blank: 2% list. With QBW1: **4% from a promotion** (replaces the 2%): taxable 960.00, tax 172.80, total **1,132.80**. NOSUCHCODE: nothing refused, back to 2% | -- | |
| QA-PRC-18 | Sales Orders > + New: Ravi, QB-DET x 10, coupon QBW1 > Save > Approve. Then another order, same coupon | First approved at 4%. Second is priced at the 2% list (1,156.40): the coupon is used up | Reports > Operational > **Promotion claims**: QB-WELCOME, QBW1, Ravi Traders, CLAIMED. Cancel both orders | |
| QA-PRC-19 | Quote Ravi QB-DET x 10, Disc % **0**, *Discount on the whole order %* **10** | Taxable **900.00**, tax 162.00, total **1,062.00** (taken off before tax) | -- | |
| QA-PRC-20 | Same quote, whole-order discount cleared, **Delivery charge 100** | Charge joins the taxable value: taxable **1,100.00**, CGST 99.00, SGST 99.00, total **1,298.00** | -- | |
| QA-PRC-21 | Settings > Selling > **Loyalty Scheme**: running on, 1 point per 100, worth 1, minimum 50 > Save. Settings > Set up > Pricing > **Loyalty** > **Adjust points**: Ravi Traders +200, reason *opening credit* | Ravi holds 200 points worth 200.00 | Journal: Dr Loyalty Expense 200.00 / Cr Loyalty Payable 200.00 (confirm) | |
| QA-PRC-22 | Sales Invoices > the Ghee invoice > **Use points** 100 | "100 points used on SI-..." | Journal: Dr Loyalty Payable 100.00 / Cr Trade Receivables 100.00. Ravi outstanding **2,709.00**; the invoice's total and tax unchanged (settled, not discounted) | |
| QA-PRC-23 | Use points again: **5000** | Refused: "That customer holds 100.0000 points, not 5000.0000." No journal | -- | |
| QA-PRC-24 | Set QB-BULK, QB-WELCOME and QB-STD **Inactive**; set Ravi's default discount back to **0** | Saved | A Ravi quote for DET x 10 is back to full price, 1,180.00 | |

---

## Territory & field sales

**Before you start:** Arun and Kiran exist. Sign in as admin@qb01.test.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-TER-01 | Settings > Set up > Territories & routes > **Territories** > New: `QB-RGN` Chennai Region (Region); `QB-NTH` Chennai North (Territory, parent Chennai Region) | Both listed with their path | -- | |
| QA-TER-02 | **Route Types** > New `SALES` Sales Route. Territories > New `QB-R1` Anna Nagar Beat: level Route, parent Chennai North, Sales Route, Weekly, Mon and Thu | Saved | Territory tree (Expand all): Chennai Region > Chennai North > Anna Nagar Beat | |
| QA-TER-03 | **Route Builder** > QB-R1: add Ravi Traders, then Lakshmi Provisions > **Save round and order** | "2 outlet(s) on Anna Nagar Beat, in order." | Reopen: 1 Ravi Traders, 2 Lakshmi Provisions | |
| QA-TER-04 | Open QB-R1 > **Salespeople**: Arun Kumar, primary | Listed | Route details: Weekly, Mon, Thu; 2 customers; 1 salesperson | |
| QA-TER-05 | Sell > All Sell screens > Field sales > **Beat Plans** > New: `QB-BP-MON` Monday Anna Nagar, route Anna Nagar Beat, Weekly, Monday | Saved | -- | |
| QA-TER-06 | Field sales > **Call Lists**: move to next Monday | QB-BP-MON badged *Runs on Monday*; calls Ravi Traders then Lakshmi Provisions | Move to Tuesday: *Not on Tuesday*, with the reason | |
| QA-TER-07 | Sales Orders > + New: Lakshmi Provisions, salesman **Kiran Raj**, QB-FLR x 1 > Save | Refused: "The selected salesperson is not assigned to this territory." Nothing saved | -- | |
| QA-TER-08 | Same with salesman Arun > Save; then a new order with salesman **blank** > Save, reopen | Arun saves. Blank saves and reopens with salesman **Arun Kumar** (from the route) | Delete both drafts | |
| QA-TER-09 | Field sales > **Coverage** | Opens; Chennai North / Anna Nagar Beat with its outlets (confirm columns) | -- | |
| QA-TER-10 | Sign in as arun@qb01.test; open Call Lists for next Monday | His plan and outlets in round order | -- | |

---

## GST & compliance

**Before you start:** Selling and Pricing done, all in this month. Sign in
as admin@qb01.test. The documents this month are: Ravi invoices 2,230.00 and
3,150.00; Bharat invoice 2,360.00 and its debit note 118.00; Lakshmi bills
656.00 and 590.00; Ravi's sales return 236.00 and credit note 105.00; bills
SD-1001, SD-1002 (with a return and a debit note) and DF-0055.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-GST-01 | Accounts > **GST Returns** > this month > **GSTR-1** | "Filing as 33AAQCB1201B1ZH". **B2B**: Ravi 2,000.00 (CGST 115.00, SGST 115.00) and 3,000.00 (75.00, 75.00) under 33AAFCR1111R1ZE; Bharat 2,000.00 IGST 360.00, place 29, under 29AAGCB2222B1Z9 (confirm rate-row layout) | Footer: derived from the documents on every read | |
| QA-GST-02 | Same, **B2CS** section | Place **33**, 18%: taxable 700.00, CGST 63.00, SGST 63.00. Place 33, 5%: taxable 400.00, CGST 10.00, SGST 10.00 | Kumar Stores is not there (never invoiced) | |
| QA-GST-03 | Same, **CDNR** section | Ravi sales return 200.00 (CGST 18.00, SGST 18.00) and credit note 100.00 (2.50, 2.50); Bharat debit note, note type **D**, 100.00, IGST 18.00 | -- | |
| QA-GST-04 | Same, **HSN** summary | 340220 qty 30 taxable 3,000.00; 090230 qty 7, 1,400.00; 340290 qty 14, 700.00; 040590 qty 10, 3,000.00 on the invoices; the return and notes adjust it (confirm) | -- | |
| QA-GST-05 | **GSTR-3B**, same month, table 3.1(a) | Taxable **7,900.00** (8,100.00 billed less 300.00 credited plus 100.00 debited), IGST **378.00**, CGST **242.50**, SGST **242.50** (confirm netting) | Equals GSTR-1's sections added by hand | |
| QA-GST-06 | GSTR-3B, table 4 (input credit) | 4(A)(5): IGST 160.00, CGST 920.00, SGST 920.00. Taken off for the purchase return (36.00 + 36.00) and the debit note (9.00 + 9.00); net CGST 875.00, SGST 875.00 (confirm rows) | Agrees with Input IGST / CGST / SGST on the trial balance (QA-FIN-11) | |
| QA-GST-07 | Accounts > All Accounts screens > Tax filing > **E-Invoice** | Banner says sandbox references are a rehearsal; nothing reads LIVE | If anything reads LIVE, stop and report | |
| QA-GST-08 | E-Invoice > Register an invoice > Lakshmi's counter bill (656.00) | Refused locally: "This invoice cannot be registered yet: the customer has no GST number." | -- | |
| QA-GST-09 | Settings > Tax > **GST Documents**: *E-invoicing applies from* today, filing Sandbox > Save. Sales Invoices > Bharat's invoice > **Print** | Dialog *No IRN yet*: not a valid tax invoice until registered. Cancel prints nothing; **Print reference copy** prints under "NO IRN YET - NOT A VALID TAX INVOICE" | Lakshmi's bill (no GSTIN) prints as before | |
| QA-GST-10 | E-Invoice > **To register** | Every B2B document dated today without an IRN, with Last day and Days left (30 days) | -- | |
| QA-GST-11 | Register Bharat's invoice; print it again | It leaves the list; print carries an E-INVOICE box with IRN (SBX...), Ack No., Ack Date and QR, marked SANDBOX | Sales Invoices > Bharat's invoice > Cancel: refused, naming its registration and the debit note | |
| QA-GST-12 | On Bharat's row, **Raise bill** (e-way): distance 350, by Road, vehicle blank; then vehicle `KA05AB1234` | Blank vehicle refused: "Goods moving by road need a vehicle number on the bill." Then "E-way bill raised." with an SBX... number | -- | |
| QA-GST-13 | GST Documents: clear *E-invoicing applies from* > Save. Print Ravi's first invoice | Prints without asking for an IRN | -- | |
| QA-GST-14 | Accounts > All Accounts screens > Tax filing > **GST checks**, this month > Run | No findings: the GSTINs are well formed and every HSN has 6 digits (confirm) | -- | |
| QA-GST-15 | Settings > Selling > **TCS Settings**: collect under 206C(1H) on, preceding year turnover 150000000, threshold 0, rate 0.1, without PAN 1 > Save. Sell > Receipts > + New: Bharat Stores, **2,478.00**, Bank, against the invoice | Receipt recorded; **no TCS** charged: section 206C(1H) was omitted from 1 April 2025, and the screen says why (confirm wording) | Tax filing > **TCS**: nothing collected. Bharat outstanding **0.00**. Journal: Dr Bank 2,478.00 / Cr Trade Receivables 2,478.00. Switch TCS off again | |
| QA-GST-16 | Buy > Payments > + New: QB-V1, amount **3,186.00**, TDS deducted **6.00**, section **194Q**, method Bank > Record | Paid from bank **3,180.00**; SD-1002 settled in full | Journal: Dr Trade Payables 3,186.00 / Cr Bank 3,180.00 / Cr TDS Payable 6.00. Supplier Statements QB-V1 closes at 0.00. Reports > Financial > **TDS deducted**: Sunrise, its PAN, 194Q, 6.00, the return quarter | |
| QA-GST-17 | Tax filing > **Rule 37 (180 days)** | Nothing listed: no bill is 180 days old | -- | |
| QA-GST-18 | Tax filing > **GST Payment**, this month. Read, **do not record** | Liability per head from 3B (IGST 378.00, CGST 242.50, SGST 242.50) and the credit available, with the set-off worked out (confirm figures) | -- | |
| QA-GST-19 | Home > **TAX CALENDAR** | Due dates for finished months only (GSTR-1 the 11th, GSTR-3B the 20th); a new firm may read nothing due yet | -- | |
| QA-GST-20 | Tax filing > **GSTR-2B Reconciliation** > Import the month's 2B file from the portal (if you have one from the CA) | Rows read Matched, Different (with the difference in words) or Not in books; *In books, not in 2B* lists our bills it lacks | Optional: skip if no file | |

---

## Finance

**Before you start:** GST & compliance done. Sign in as admin@qb01.test.
Opening balances come first so the ledger figures below include them.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-FIN-01 | Accounts > All Accounts screens > Books > **Opening Balances**, date today: 1010 Bank debit **50,000**; 1000 Cash debit **5,000** > Save | Saved as one journal OTB-... | Journal: Dr Bank 50,000.00, Dr Cash 5,000.00 / Cr Opening Balance Equity 55,000.00 | |
| QA-FIN-02 | Opening Balances: add a line for 1100 Trade Receivables | Refused: a sub-ledger account takes its own opening path (customer bills) | Nothing changes | |
| QA-FIN-03 | Masters > Customers > ... > **Import opening bills**: download the template; fill two rows: Lakshmi Provisions bill `OLD-501`, date 60 days ago, due 30 days ago, **2,000**; and a row with customer code `QB-C99`. Check file | The check lists QB-C99 by row and column; nothing is written | -- | |
| QA-FIN-04 | Delete the bad row; Check file again; posting date today; **Import** | Imported; numbered OBC-00001 | Journal: Dr Trade Receivables 2,000.00 / Cr Opening Balance Equity 2,000.00. Lakshmi outstanding **2,000.00**; Receipts > + New for Lakshmi lists OLD-501 as an opening bill | |
| QA-FIN-05 | Masters > Vendors > ... > Import opening bills (or the form): Deccan Foods bill `OLD-77`, 1,000 | Numbered OB-00001 | Journal: Dr Opening Balance Equity 1,000.00 / Cr Trade Payables 1,000.00. Buy > Payments > + New for Deccan lists it marked opening, beside DF-0055 | |
| QA-FIN-06 | Accounts > **Journal Entries** > New: Dr 6000 Rent 5,000; Cr 1010 Bank 5,000; reference `QB-RENT-1` > Save > **Post** | Posted with a number | Accounts > **Ledgers**: Rent 5,000.00 Dr; Bank falls by 5,000.00 | |
| QA-FIN-07 | New journal: Dr Rent 5,000, Cr Bank 4,000 > Post | Refused: debits and credits differ | Nothing posted | |
| QA-FIN-08 | Accounts > **Expenses** > New: Electricity 1,200, paid from Cash, no TDS > Save | Recorded | Journal: Dr Electricity 1,200.00 / Cr Cash 1,200.00 | |
| QA-FIN-09 | Accounts > All Accounts screens > Books > **Contra Vouchers** > New: Cash to Bank 1,000 | Posted | Journal: Dr Bank 1,000.00 / Cr Cash 1,000.00 | |
| QA-FIN-10 | Journal Entries: filter *Posted by: Sales invoices*, this month | Only the five sales invoices' journals | A document's journal offers no Reverse; a hand journal does | |
| QA-FIN-11 | Accounts > **Trial Balance**, this month | **Balanced** chip. Among the rows (confirm): Inventory 30,720.00 Dr; Trade Receivables 4,709.00 Dr; Bank 33,464.00 Dr; Cash 4,036.00 Dr; Trade Payables 4,360.00 Cr; Goods Received Not Invoiced 0.00; TDS Payable 6.00 Cr; Opening Balance Equity 74,400.00 Cr; Output IGST 378.00, Output CGST 242.50, Output SGST 242.50 Cr; Input IGST 160.00, Input CGST 875.00, Input SGST 875.00 Dr | Total debits = total credits (88,029.00 if every figure above holds) | |
| QA-FIN-12 | Accounts > **Profit & Loss**, same period | Sales 8,200.00; Sales Returns 300.00; Cost of Goods Sold 6,320.00; Inventory Adjustment 160.00; Purchase Price Variance 100.00 credit; Rent 5,000.00; Electricity 1,200.00; Commission Expense 10.00; Loyalty Expense 200.00; net **loss 4,890.00** (confirm) | -- | |
| QA-FIN-13 | Accounts > **Balance Sheet**, same period | **Balanced** chip; total assets = liabilities and equity (74,839.00 if the trial balance figures hold); *Result for the year* equals the P&L's year-to-date net | -- | |
| QA-FIN-14 | Accounts > All Accounts screens > Statements > **Cash Flow**, same period | Operating, investing, financing; opening and closing cash; says it **reconciles** | -- | |
| QA-FIN-15 | Accounts > **Ledgers**: Trade Receivables, this month | Every invoice, receipt, return, note, loyalty use and opening bill above, with a running balance ending 4,709.00 Dr | Sell > Customer Statements: Ravi 2,709.00 + Lakshmi 2,000.00 = 4,709.00 | |
| QA-FIN-16 | Accounts > **Bank Reconciliation** > Bank > Import statement: the bank's file with a line for the 14,064.00 payment (date within 3 days) and one line the books do not have > **Auto-match** | The 14,064.00 line matches the payment's posting; the other stays unmatched | Reconciliation statement lists only unmatched items against the statement's closing balance. Nothing posts | |
| QA-FIN-17 | Settings > Firm > **Financial Years** > last month > **Close**. Then a journal dated in last month > Post | The close checklist shows first (never refuses). Posting refused: the period is closed and cannot accept postings | **Open** the month again; Audit Logs shows closed and reopened, naming you | |
| QA-FIN-18 | Sell > All Sell screens > Money > **Post-dated Cheques** > New: Ravi Traders, 500.00, cheque dated next week > Save; try **Deposit** today | Held; deposit refused before the cheque's date | Holding posts nothing (Journal Entries unchanged). Cancel the cheque | |
| QA-FIN-19 | Accounts > All Accounts screens > Books > **Export to Tally**, this month > Export | An XML file is saved | Every posted journal is a voucher typed by its source (Sales, Purchase, Receipt, Payment, Journal...), with a ledger per customer and supplier | |
| QA-FIN-20 | Sign in as meena@qb01.test (Counter Sales) | No Journal Entries, Ledgers or Trial Balance anywhere | anita@qb01.test sees them all | |

---

## Reports

**Before you start:** everything above. Sign in as admin@qb01.test. Reports
are under **Reports > Operational** and **Reports > Financial**.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-REP-01 | Open every entry under Reports > Operational, then Financial | Each opens with a row count, or "Nothing to report"; never a blank grid or an error | Note any slow one (over 3 seconds) | |
| QA-REP-02 | Operational > **Sales invoice register**, this month | Five invoices: 2,230.00, 3,150.00, 2,360.00, 656.00, 590.00; total **8,986.00** | -- | |
| QA-REP-03 | **Purchase invoice register**, this month | SD-1001 14,064.00, SD-1002 3,776.00, DF-0055 3,360.00; total **21,200.00** | Opening bills are not purchases and are not listed | |
| QA-REP-04 | **Stock valuation**, today | DET 61 / 4,880.00; TEA 61 / 9,760.00; TEA100 5 / 320.00; FLR 79 / 3,160.00; GHEE 50 / 12,000.00; COMBO 5 / 600.00; total **30,720.00** (confirm) | Equals Inventory on the trial balance | |
| QA-REP-05 | Financial > **Customer outstanding** | Ravi Traders 2,709.00; Lakshmi Provisions 2,000.00; Bharat Stores and Kumar Stores 0 | Agrees with Customer Statements | |
| QA-REP-06 | Financial > **Vendor outstanding** | Deccan Foods 4,360.00 (DF-0055 3,360.00 + OLD-77 1,000.00); Sunrise 0 | Agrees with Supplier Statements | |
| QA-REP-07 | **Overdue sales invoices** | Lakshmi's opening bill OLD-501, about 30 days overdue; no current invoice (Ravi's terms are 30 days) | -- | |
| QA-REP-08 | Sell > All Sell screens > Insight > **Sales Analysis**, this month by product | DET, TEA, FLR and GHEE with the quantities and values sold above (confirm how returns are netted) | -- | |
| QA-REP-09 | Buy > All Buy screens > Insight > **Purchase Analysis**, this month | DET 100 and TEA 70 bought, with average rates 80 and 160 | -- | |
| QA-REP-10 | **Orders not yet received** and **Purchase order register** | The register lists both orders; *not yet received* lists none (both fully received) | -- | |
| QA-REP-11 | **Stock ageing** | Every product with quantity by age band and turnover columns | -- | |
| QA-REP-12 | Financial > **Customer PAN check** | Lakshmi Provisions and Kumar Stores listed (no PAN); Ravi and Bharat not listed | -- | |
| QA-REP-13 | Any report > Export | A file is saved with the grid's rows | -- | |

---

## Approvals & notifications

**Before you start:** Priya (Sales Manager) and Arun exist. Sign in as
admin@qb01.test.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-APR-01 | Settings > Firm > **Approval Levels** > New: document Sales order, level 1 from **5,000**, role Firm Administrator > Save | Rule listed | -- | |
| QA-APR-02 | Sign in as priya@qb01.test. Sales Orders > + New: Lakshmi Provisions, QB-TEA x 30 (total 6,300.00) > Save > **Approve** | Refused, naming level 1 and the role that may sign it (Firm Administrator) | -- | |
| QA-APR-03 | Priya: Sales Orders > + New: Lakshmi, QB-TEA x 10 (2,100.00) > Approve | Approved at once (below 5,000) | -- | |
| QA-APR-04 | As admin: open the **bell** on the menu bar | *Documents awaiting the next sign-off* counts 1 | Priya's bell does not offer it (she cannot sign) | |
| QA-APR-05 | Sell > All Sell screens > Documents > **Approvals** > the 6,300.00 order > **Sign off** | The order is **Approved** | Bell count drops; Audit Logs records the sign-off | |
| QA-APR-06 | Priya raises another 6,300.00 order and submits it; admin > Approvals > **Reject**, reason *test* | Rejected with the reason | -- | |
| QA-APR-07 | Buy > Purchase Orders > + New: QB-V1, QB-FLR x 10 > Save > Send for approval (do not approve) | Submitted | Admin's bell lists a purchase order awaiting approval | |
| QA-APR-08 | Sell > Sales Orders: tick two draft orders > **Approve selected** | Each row approved or refused on its own, with the reason for any refusal | -- | |
| QA-APR-09 | Home > **TO DO**: click one to-do | The list it opens holds the number of rows the to-do said | -- | |
| QA-APR-10 | Settings > Firm > **Messaging** | Off (the default): nothing is queued or sent | Message log empty | |
| QA-APR-11 | Clean up: cancel every order and the purchase order raised in this module; delete the approval rule | All cancelled | Stock reservations back to zero | |

---

## Platform administration

**Before you start:** sign in as the **platform administrator** unless the
case says otherwise.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-PLT-01 | Sign in as the platform administrator; open Settings | Starts on Platform. PLATFORM section: People (Users, Roles, Permissions, User Templates, User-Firm Assignments), Firms (Firms, Business Profiles), System (Audit Logs, Diagnostics, Licensing, Backups, Platform Dashboard), Agency (Branding) | -- | |
| QA-PLT-02 | Settings > Platform > **Firms** > QB01 > Set up | **Finished. Every step is done.** | -- | |
| QA-PLT-03 | Firms > QB01 > **Delete** | Refused: "Assigned firms cannot be deleted." | QB01 still works | |
| QA-PLT-04 | Settings > Platform > **Backups** > **Back up now** | Completes; listed with time, size and who took it | The installation guide names where backups are kept on the server PC | |
| QA-PLT-05 | Settings > Platform > **Audit Logs** (no firm chosen) | The platform trail: user and firm administration (user created, firm created ...), each naming who | -- | |
| QA-PLT-06 | Switch into QB01; Audit Logs | QB01's trail: customers, documents, approvals, each naming the person; newest first | Search box: type `Arun` -- rows about or by Arun only | |
| QA-PLT-07 | Settings > Platform > **Diagnostics** | Opens (error reports by group) | Signed in as admin@qb01.test, Diagnostics is **not** offered | |
| QA-PLT-08 | Settings > Platform > **Platform Dashboard** | Counts of firms, users and roles | -- | |
| QA-PLT-09 | Switch into any other firm on this server; Masters > Customers; search `Ravi` | QB01's customers never appear | Switch back: QB01's list reloads without the other firm's rows | |
| QA-PLT-10 | Sign in as admin@qb01.test; open Settings | No **Firms** and no **Business Profiles**; PLATFORM shows only People | -- | |
| QA-PLT-11 | Two windows as admin@qb01.test: both open Ravi Traders for edit; A changes the phone and saves; B changes the phone and saves | A saves. B is refused inside the editor: "Somebody else saved this customer while you were editing it. Your changes are still here and have not been sent..." | Reopen: A's phone | |

---

## Agency branding

**Before you start:** the platform administrator and QB01 exist (FRM cases).
QA-BRD-01 to 05 need a **spare PC** for a fresh server install and are best
run last; QA-BRD-11 to 14 need a server whose branding is **not yet set**,
which is how a fresh install without a name leaves it (run them before
QA-BRD-13 sets it, or on the spare PC). The rest need the branding set.
The agency's name and logo are the agency's own; the product stays **Agency
Platform**.

| ID | Action (with the exact sample values) | Verify on this screen | Verify elsewhere | Result |
| --- | --- | --- | --- | --- |
| QA-BRD-01 | **Fresh server install on a spare PC** (not the PC the other cases run on): run `AgencyPlatform-1.3.0-Setup.exe`, choose **This PC: server and app**, Next | A **Branding** page follows *This PC* with *Your agency's name and logo*: Agency name, Tagline, a Logo box with Browse, and a read-only line *This product: Agency Platform, by* its company. Every box is optional | Leave all blank, Next, finish the install: no error; first sign-in opens the *Set up your agency* dialog (QA-BRD-11) | |
| QA-BRD-02 | Repeat the fresh install; type only Agency name `QA Book Traders Agency`, Next, finish, sign in as the platform administrator | No *Set up your agency* dialog; the sign-in screen and the top of the app show *QA Book Traders Agency* with its initials in place of a logo | Settings > Platform > Audit Logs (no firm): `agency_branding.created` by the installer's run | |
| QA-BRD-03 | On the Branding page type a Tagline `Quality in bulk` and no name; press Next. Then clear it, give a Logo path `C:\nowhere\x.png` and a name, press Next | First: *Type the agency's name too; the tagline and logo are saved with it.* Second: *The logo file was not found. Choose it again or leave it blank.* Next does not move on either time | -- | |
| QA-BRD-04 | Give a name and, as the logo, a text file renamed `fake.png`; then (another run) a PNG larger than 1 MB. Finish each install | **The install still completes.** The name is saved and shows after sign-in; no logo is saved (initials show) | The newest file in `C:\ProgramData\Agency Platform\logs\install` holds a warning that the logo was not saved or could not be read; the administrator can add a logo later (QA-BRD-16) | |
| QA-BRD-05 | Run the setup again on the same PC (repair or upgrade), and run it on a second PC choosing **App only** | **No Branding page** in either (it is shown on a fresh server install only) | The agency's branding is unchanged after the repair or upgrade | |
| QA-BRD-06 | Open the app with the agency's branding set; do not touch the boxes for 20 seconds | The agency's logo (or initials), name and tagline sit above the form; a night-blue panel at the left shows one strength (title and a line) and moves to the next about every 8 seconds | Click the arrows and a dot: one strength at a time. Type one letter in the email box: cycling **stops for good**, even after clearing the box | |
| QA-BRD-07 | Narrow the window below 900 px wide, then widen it again | The left panel goes and the sign-in card stands alone with nothing cut off; wide again, the panel returns | -- | |
| QA-BRD-08 | At the foot of the sign-in card read the product mark; read the window's title bar and the status line | Mark: Agency Platform, *by* its company, and its tagline. Title bar: **Agency Platform - Sign in**. Status line: server state, version (1.3.0) and *Powered by Agency Platform* | After signing in the title bar changes to the agency's name (QA-BRD-20) | |
| QA-BRD-09 | Open **More help**; click **Copy details for support**; paste into Notepad | Support rows (phone, WhatsApp, hours, email, website) show only when filled: **all blank in this release, so none appears** (this is by design). *Forgot your password? Your administrator resets it.* does appear. The button reports it copied | The pasted text names the product, version 1.3.0, the server address and this PC's name; no password | |
| QA-BRD-10 | Stop the server (Services > Agency Platform Server > Stop), close and reopen the app | The sign-in screen still opens at once with the agency's name, tagline and logo from this PC's last visit; no error box. On a PC that never connected, it shows Agency Platform's own name and logo | Start the server, reopen: the current branding shows | |
| QA-BRD-11 | On a server whose branding is **not** set, sign in as the platform administrator | A dialog **Set up your agency** opens over Home: Agency name, Tagline, Logo, a live preview, **Skip for now** and **Save** | Press Save with the name blank: refused beside the box, nothing saved | |
| QA-BRD-12 | Press **Skip for now**; look at Home; sign out and in | The dialog closes and saves nothing. Home shows a **Finish setting up** card, *Give your agency's name and logo, so every PC shows them.*, with a **Set up your agency** button. After signing in again the dialog does not reopen for this user | Sign in as another platform administrator (if you have one): the dialog opens for them once | |
| QA-BRD-13 | Click **Set up your agency** on the card; type `QA Book Traders Agency`, tagline `Quality in bulk`, choose a valid PNG under 1 MB; **Save** | *Saved.*, the form closes, the Home card disappears, and the logo, name and tagline lead the menu strip at once | Settings > Platform > Audit Logs (no firm): `agency_branding.created` and `agency_branding.logo_changed` naming the platform administrator; the logo entry gives type and size, not the image | |
| QA-BRD-14 | Sign in as admin@qb01.test (firm administrator) while branding is still not set | No dialog and no **Finish setting up** card; Settings offers no Platform section | -- | |
| QA-BRD-15 | Sign in as the platform administrator; Settings > **Platform > Agency > Branding** | Agency name (starred), Tagline, Logo, a **Preview** of the *Sign-in screen* and *Top of every screen*, and our product, company and logo read-only (*Set by the installer; changed only by an update*). **No colour box** | Type in the name box: the preview follows each keystroke | |
| QA-BRD-16 | Change the tagline to `Quality, in bulk`; **Save**. Then **Change logo**, pick a different valid PNG or JPG; Save. Then **Remove logo**; Save | Each save shows *Saved.* and the menu strip changes with no refresh. After Remove the initials of the name show in the preview and the header | Audit Logs (no firm): `agency_branding.updated`, `agency_branding.logo_changed` (twice: set, removed). On another PC the new tagline and logo show at its next sign-in screen | |
| QA-BRD-17 | Choose as the logo a text file named `fake.png`; then a PNG or JPG larger than 1 MB | Text file: *The logo must be a PNG or JPG image.* (the contents are judged, not the name). Large file: a message giving its size in MB and the 1 MB limit. The form keeps everything typed and nothing is saved | Audit Logs: no new entry | |
| QA-BRD-18 | Two PCs (or two windows) open the page. On the first change the tagline and Save; on the second change the name and Save | The first saves. The second is refused inside the form with the somebody-else-saved message, keeping what was typed | Reopen: the first person's tagline | |
| QA-BRD-19 | Sign in as admin@qb01.test; open Settings | No **Platform** section and no Agency or Branding card | Ctrl+K `Branding` does not offer the screen | |
| QA-BRD-20 | Sign in as admin@qb01.test with the agency's branding set; look at the left of the menu strip and the window's title bar | The agency's logo, name and tagline lead the strip before Home, then **QA Book Traders** as plain text; the firm switcher is still at the right. Title bar: **QA Book Traders Agency > QA Book Traders** | Menu strip height is unchanged from before (nothing pushed down) | |
| QA-BRD-21 | Sign in as the platform administrator (no firm chosen) | Title bar reads the agency's name alone, with no *>*; no firm name beside the agency in the strip | Switch into QB01: the title becomes *agency > QB01* | |
| QA-BRD-22 | Narrow the window below 820 px; then widen it past 1280 px | Below 820 px only the logo shows (no name); the tagline appears only from 1280 px; nothing overflows | -- | |
| QA-BRD-23 | Open Masters > Customers; click the agency's logo or name at the left of the strip | Home opens | -- | |
| QA-BRD-24 | Read the right end of the status line; point at it; click it | Our product's mark, *Agency Platform 1.3.0 by* its company; a tooltip repeats it. **Clicking does nothing** (Help > About is not built yet) | -- | |

---

## Defect report template

Copy this block for each failure.

| Field | Fill in |
| --- | --- |
| Defect title | One line: what is wrong, on which screen |
| Case ID | e.g. QA-SELL-11 |
| Date and time | |
| Tester | |
| App version | As shown on the sign-in screen (1.3.0) |
| Firm and user | e.g. QB01, admin@qb01.test |
| Steps | The case's action, plus anything you did differently |
| Expected | Copy from the case |
| Seen instead | Exact figures and the exact message text |
| Severity | High (wrong money, tax or stock; data lost) / Medium (feature does not work, workaround exists) / Low (wording, layout) |
| Repeatable? | Yes / No / Sometimes |
| Screenshot | Attach |
| Server log | The newest file in `C:\ProgramData\Agency Platform\logs\server` |
| Diagnostics report | User menu > Diagnostics report, saved and attached |
| Notes | Anything else, including "possibly the case's mistake" for a (confirm) item |

## Sign-off

| Module | Cases | Passed | Failed | Blocked | Tester | Date | Signature |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Sign-in & my settings | 20 | | | | | | |
| Users & roles | 16 | | | | | | |
| Firm set-up & configuration | 20 | | | | | | |
| Masters | 21 | | | | | | |
| Purchasing | 20 | | | | | | |
| Inventory | 15 | | | | | | |
| Selling | 36 | | | | | | |
| Pricing & incentives | 24 | | | | | | |
| Territory & field sales | 10 | | | | | | |
| GST & compliance | 20 | | | | | | |
| Finance | 20 | | | | | | |
| Reports | 13 | | | | | | |
| Approvals & notifications | 11 | | | | | | |
| Platform administration | 11 | | | | | | |
| Agency branding | 24 | | | | | | |
| **Total** | **281** | | | | | | |

**Not covered in this book** (each has detailed cases in `docs/qa/`): landed
costs, payment runs, supplier rebates and ratings, principal claims, quality
inspection, purchase budgets and bill tolerance, serial numbers, count plans,
quarterly (QRMP) filing, rule 42, filed-return amendments, branch GSTINs,
cheque printing, TDS challans, price levels, bulk coupons, messaging sends,
and the installer itself apart from its Branding page (`docs/INSTALLER_QA_CHECKLIST.md`).
