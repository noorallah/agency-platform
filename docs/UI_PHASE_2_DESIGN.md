# Desktop UI, phase 2 -- navigation and screen space

**Status:** agreed for building, 2026-09-26. Decisions 1, 10 and 13 were
agreed by the owner on 2026-09-25; the rest of section 8 was decided on
2026-09-26 by industry convention at the owner's request, **to be reviewed by
the owner** -- any of them can still be changed. Phase 1 is frozen as the git
tag `ui-phase-1` (and the installed build as `v1.0.1`); it is not shared with
anyone, and functionality is tested together with phase 2.

**Why:** the owner went through every screen on 2026-09-25 and found that
(1) screen space is not used well, and (2) the left menu takes room, and once
expanded it is so long that finding an item means scrolling every time.

---

## 1. What phase 1 is, measured

Taken from the code on 2026-09-25 (`desktop_shell.dart`, `enterprise_sidebar.dart`,
`module_catalog.dart`, `workspace_components.dart`, `design_tokens.dart`).

### Navigation

| Fact | Value |
| --- | --- |
| Top-level modules in the sidebar | **19** |
| Screens (tabs) under them | **94** |
| Sidebar width | 260 px expanded, 64 px collapsed |
| How a screen is reached | expand a module in a tree, scroll, click |
| Sales documents | **six separate top-level modules** (Quotations, Sales Orders, Delivery Notes, Sales Invoices, Sales Returns, plus Sales); purchasing the same with four |
| Search | global search on Ctrl+K exists, but finds records, not screens or actions |
| Favourites / recent screens | none |

On a 1366 px wide laptop the expanded sidebar takes **19 %** of the width,
all the time, to show a list the user needs for a second.

### A list screen, top to bottom, at 1366 x 768

| Band | Height (approx.) |
| --- | --- |
| Application header (name, collapse, theme, user) | 68 |
| Workspace frame: breadcrumbs, title, a sentence of description | ~100 |
| Search box + toolbar row | ~56 |
| Filters tile (collapsed) | ~48 |
| Grid header | 46 |
| **Grid rows** (42 px each, the default density) | **~330, about 8 rows** |
| Pager | ~52 |
| Status bar | ~28 |
| Windows title bar / taskbar | ~70 |

So **about 8 records** are visible on a laptop, and less than half the
height is data. The description sentence is read once and then costs 40 px on
every visit. Documents (orders, invoices) open in **dialogs**, which are
smaller than the window they sit in.

---

## 2. What comparable products do

| Product | Navigation | Space |
| --- | --- | --- |
| **Tally Prime** (what most Indian distributors know) | No sidebar. A "Gateway" home, **Go To (Alt+G)** to reach any report or voucher by typing, keyboard first | Full-screen vouchers; a thin button bar on the right |
| **Zoho Books / Inventory** | Slim left menu grouped into a handful of areas, each opening a short list; global search; **"+" quick create** in the top bar | Lists fill the page; the record opens beside the list |
| **Odoo** | App switcher (home grid of apps); inside an app, a **horizontal menu bar** of a few dropdowns | List and form use the full width; filters are chips in one search bar |
| **ERPNext / Frappe** | "Awesome bar": one search for screens, records and actions; workspace pages of shortcuts | Full-width lists; sidebar per list is optional |
| **MS Dynamics 365 Business Central / SAP B1** | **Role Center** home; "Tell me" search (Alt+Q) for any page or action | Action bar across the top; FactBox side panel collapsible |
| **Busy / Marg** | Keyboard menus, letters as shortcuts | Full-screen entry grids |

**What they agree on:**
1. The menu is **short**: a handful of areas, each opening a list that fits
   on the screen without scrolling. Nobody shows 94 items in one tree.
2. **Typing beats clicking** for people who use it all day: one box that finds
   a screen, a record, or an action ("new sales order").
3. The menu **does not stay open**; the data does.
4. Lists and documents use the **whole window**; titles are one line.
5. The home screen is **per role**: what this person does today.

---

## 3. Principles for phase 2

1. **Data first.** On a 1366 x 768 laptop a list shows **at least 15 rows**,
   and data takes **at least 70 % of the height**.
2. **Any window size (owner, 2026-09-25).** Nothing is built for a fixed
   screen. Every screen fills whatever window it is given -- a laptop, a
   full-HD or wider monitor, half a screen beside another program -- and uses
   the extra room for more rows and columns. 1366 x 768 is the **smallest
   size tested**, not the size designed for. See 4.11.
3. **Any screen in two actions**, without scrolling a menu: click area →
   click item, or Ctrl+K → type → Enter.
4. **Keyboard complete.** Every list and every document can be driven without
   the mouse, the way Tally users expect.
5. **Nothing permanent that is not data.** Menus fly out and close;
   descriptions become a help icon; side panels open on request.
6. **Same rules, same data.** Permissions, business-profile module gating and
   the module catalogue stay exactly as they are (they are correct and
   tested); phase 2 changes how they are *shown*.

---

## 4. The proposed shell

### 4.1 Layout -- a top menu bar (agreed 2026-09-25)

The owner chose the **top menu bar** over a left rail on 2026-09-25: users
come from Tally, Busy and Marg, which put the menu across the top; the
screens are wide tables that want the whole width; and eight areas fit across
a 1366 px laptop. Xero, NetSuite, Odoo, SAP Fiori and Business Central use
the same arrangement.

```
+----------------------------------------------------------------------------------------+
| Agency | Home  Sell v  Buy v  Stock v  Accounts v  Masters v  Reports v  Admin v         |  menu bar 40 px
|        |       [ Search or jump to...  Ctrl+K ]  [+ New v]  [QA01 Traders v] [?] [SN v]  |  (one row when wide)
+----------------------------------------------------------------------------------------+
| Sales Order SO-QA01-0012 x | Invoices x | Stock Ledger x |                               |  open tabs 32 px
+----------------------------------------------------------------------------------------+
| Sales Orders > Open    [Status=Open x] [Branch=HO x] [+]  (i)  [Approve] [Print] [+ New] |  page bar 44 px
+----------------------------------------------------------------------------------------+
|  #  | Number        | Date       | Customer          | Branch | Amount    | Status     |
|  1  | SO-QA01-0012  | 25-09-2026 | QA Retail         | HO     |  1,770.00 | Approved   |
|  2  | ...                                                                              |
|  ... about 16 rows at 34 px, across the full width of the window ...                 |
+----------------------------------------------------------------------------------------+
| 128 records  |  3 selected  |  Page 1 of 7  < >  |  Ready                               |  status bar 28 px
+----------------------------------------------------------------------------------------+
```

- **Menu bar, 40 px**: the product mark on the left, then the **eight
  areas**, then the **command box**, **+ New** (quick create), the **firm
  switcher**, the **Settings gear**, help and the user menu on the right. The firm is changed
  rarely, so it sits beside the profile rather than first (owner,
  2026-09-25) -- but it stays **visible**, showing the current firm's name,
  because working in the wrong firm is the costly mistake. On a wide screen it is one row; at 1366 px the command box
  may sit on the same row in a shorter form. When the window is too narrow
  for all eight, the ones that do not fit fold into **More v**.
- **No sidebar at all**: the grid gets the full width of the window.
- **Open tabs, 32 px**: every screen or document opened stays as a tab, so a
  sales order and its invoice can be switched between without navigating.
  Closeable, reorderable, remembered per user.
- **Page bar, 44 px, one line**: title, filter chips, actions. The description
  sentence moves behind the (i) icon.
- **Status bar, 28 px**, now also holds the pager.

At 1366 x 768 that leaves **about 16 rows** of grid (compact density),
against 8 today.

### 4.2 Eight areas instead of nineteen modules

| Area (menu bar) | Contains (today's modules and tabs) |
| --- | --- |
| **Home** | role dashboard, to-do, favourites, recent |
| **Sell** | Quotations, Sales Orders, Delivery Notes, Sales Invoices, Sales Returns, Proforma, Credit Notes, Receipts; Price Lists, Promotions, Loyalty; Territory, Routes, Beats, Call lists |
| **Buy** | Purchase Orders, Goods Receipts, Purchase Invoices, Purchase Returns, Payments |
| **Stock** | Inventory, Stock Ledger, Transfers, Adjustments, Opening Stock, Physical Count, Batches and Serials, Expiry |
| **Accounts** | Ledger, Journals, Financial Years, GST Returns, E-Invoice, TCS, Commission |
| **Masters** | Customers, Vendors, Products, Product Categories, Units, Tax, Branches and Warehouses, Places |
| **Reports** | the report catalogue, searchable, with favourites |
| **Admin** | Users, Roles, Permissions, Firms, Business Profiles, Audit, Diagnostics, Licensing |
| **Settings** (the gear in the menu bar, not an area) | every setting, gathered in one place by topic -- see 4.13 |

**No phase 1 screen is dropped.** Appendix A places every one of them
(all 94 catalogue screens, the single-screen modules, and the settings that
today open as dialogs inside other screens). A role only ever sees the areas
and items its permissions allow, as today (4.12).

### 4.3 The drop-down panel (replaces the long tree)

Clicking **Sell v** in the menu bar drops a panel down over the page, **in
columns**, not a tree (a "mega menu"):

```
| Agency | Home  [Sell v]  Buy v  Stock v  Accounts v  Masters v ...
+--------+-----------------------------------------------------------------+
                 | DOCUMENTS            PRICING            FIELD SALES     |
                 |  Quotations           Price Lists        Territories    |
                 |  Sales Orders   *     Promotions         Routes & Beats |
                 |  Delivery Notes       Loyalty            Call Lists     |
                 |  Sales Invoices                          Coverage       |
                 |  Sales Returns        MONEY                             |
                 |  Proforma             Receipts                          |
                 |  Credit Notes         Customer Statements               |
                 |                                                         |
                 |  * = favourite (click the star)          Esc closes     |
                 +---------------------------------------------------------+
```

- Everything in an area is visible **at once** -- no scrolling, no expanding.
- It closes on choice, on Esc, or on clicking away. Moving the mouse along the
  menu bar while a panel is open switches to the next area's panel, as a
  Windows menu bar does; the keyboard's arrow keys do the same.
- Favourites (star) appear on **Home** and at the top of the command box.

### 4.4 The command box (Ctrl+K, also Alt+G for Tally users)

One box for three things:

```
[ so 12                                                        ]
  SCREENS   Sales Orders                                   Sell
  RECORDS   SO-QA01-0012   QA Retail   1,770.00   Approved
  ACTIONS   New sales order                                Ctrl+Shift+O
            New sales order for QA Retail
```

Screens (all 94, by name and by synonyms: "bill" finds Sales Invoices),
records (today's global search), and actions (create, approve, print).
Recent entries first.

### 4.5 Nothing above the grid but one line (owner, 2026-09-25)

The owner's note after going through every screen: filters and summaries take
a lot of each page, and that space should go to the work. Today, above the
grid, a list can stack a breadcrumb, a title and a description, a row of
summary cards (`SummaryMetricCard`, 230 px wide with 20 px padding, about
100 px tall -- on Inventory, Purchases and the Dashboard) or a summary strip
(orders, invoices, receipts, delivery notes), the search and toolbar row and
the filter tile. Phase 2 folds **all of it into the page bar**:

```
| Sales Invoices   Open 12 | Overdue 3 | Rs 4.2 L this month   [Status=Open x] [+]  / search   [Print] [+ New] |
```

- **Summary figures become counters in the page bar** -- small, one line,
  and **clickable**: clicking "Overdue 3" filters the list to those three. A
  figure that is not a filter ("Rs 4.2 L this month") is plain text. The
  full set of cards and charts lives on **Home**, where somebody goes to look
  at numbers, not on the list where they go to work.
- **Filters are chips** in the same line; **+** opens a filter drawer from
  the right, which closes again. Saved views are chips too.
- **Search** is the `/` key or the small box in the line, not a full-width
  band.
- **Actions** sit at the right end of the same line; the rarely used ones
  under **...**.
- A screen may not add a band above its grid. Anything that wants one is a
  counter, a chip, or belongs on Home.

At 1366 x 768 this is what gives the ~16 rows in 4.1; today's cards and
filter tile alone take the height of about five rows.

#### Worked example: Customers, from the owner's screenshot

The owner circled everything above the Customers grid (2026-09-25). On that
screen, about **480 px of a ~1,100 px window** sit above the first row, and
the page says where you are **three times**:

| Band today | What it holds | Phase 2 |
| --- | --- | --- |
| Header bar | back / forward, "Masters", firm, user | the **menu bar** (firm, areas, search, user) |
| Breadcrumb | Workspace > Masters > Customer Management | gone -- the open menu area and the tab say it |
| Title + description | "Customer Management", "Manage firm-scoped customer masters..." | title in the page bar; description behind (i) |
| Search + toolbar | a wide search box, New, view, edit, delete, refresh, export, settings, Groups | one page-bar line: counters, chips, `/` search, New, **...** for the rest |
| Filters tile | a collapsed "Filters" row | a **+** chip opening a drawer |
| Status bar **and** a second system bar | "1 record / Ready", then Online, user, firm, API, DB, configured, version | **one** status bar: records, selection, pager; connection shown as one dot, details on hover |
| Row actions column | view, edit, more on every row | kept only as **...** on hover; double-click / Enter opens, the toolbar acts on the selection |

The same page in phase 2:

```
| Agency | Home  Sell v  Buy v  Stock v  Accounts v  [Masters v]  Reports v  Admin v  [Search Ctrl+K] [QA01 Traders v] [SN] |
| Customers x | Products x |                                                                                     |
| Customers   Active 1 | On hold 0 | Over limit 0   [+ filter]   / search          [Groups] [...]  [+ New] |
|  Code   | Name        | GST             | Phone         | City    | Status  | Credit limit | Balance     |
|  QA-C1  | QA Retail   |                 | +911111111111 | Madras  | Active  |         0.00 |        0.00 |
|  ... the rest of the window is rows ...                                                              |
| 1 record  |  0 selected  |  Page 1 of 1                                                    (o) online |
```

From the menu bar to the first row: **about 120 px instead of 480**, the
difference being roughly twenty more customers on screen.

### 4.6 Daily screens: fast, and familiar

Most of a customer's day is spent on a few screens. They get extra care, and
they should feel like the software the customer used before (Tally, Busy,
Marg), so the work is done quickly without training.

**The daily screens** (to confirm per role in appendix A): Sales Invoice
(billing), Receipt, Sales Order, Quotation, Delivery Note, Purchase entry
(receipt and invoice), Payment, Stock enquiry, Customer ledger / statement.

For each of them:

1. **Opens ready to type.** The menu item or its key opens a new entry with
   the cursor in the first field -- the list is one key away, not in the way.
2. **Pick by typing.** Customer by code, name or phone; product by code, name
   or barcode; the first few letters narrow the list, Enter takes it. A
   master that is missing can be created **inline** (Alt+C, as in Tally)
   without leaving the document.
3. **What the user needs at the line, on the line.** Available stock, last
   price charged to this customer, and the applicable discount shown beside
   the product as it is picked -- no second screen.
4. **Enter moves forward**, a new line appears after the last, and the
   totals footer (taxable, GST, round-off, total, amount in words) is always
   visible.
5. **Save, print and start the next in one key** (for billing counters),
   plus Save and Save-and-close.
6. **Recent documents** of the same kind in a narrow panel that can be
   hidden, to repeat or check the last bill.
7. **Voucher keys** a Tally user knows, as an option to agree: F8 sales,
   F9 purchase, F6 receipt, F5 payment, F7 journal.

The measure is time: a counter clerk should bill a known customer for three
known products **in under 30 seconds without the mouse**.

### 4.7 List screens

- Filters, counters and search as in 4.5.
- **Density**: compact (34 px) by default below 900 px of height,
  comfortable above; the user can switch. (The three densities already exist
  in `design_tokens.dart`.)
- **Row preview**: selecting a row can open a **side panel** (on request, not
  permanent) with the record's key facts and actions; double-click or Enter
  opens it fully.
- Column chooser, sort, and CSV/XLSX export stay as today.

**As built for every screen (2026-09-26, "implement for all pages").** One
set of rules, carried by the shared framework so each screen follows them
without its own code:

| Rule | How |
| --- | --- |
| The line's order: title, counters, "+ filter", Views, search, View/Edit/Delete/Refresh icons, the screen's own steps, "...", **+ New** last | `WorkspaceToolbar` |
| A screen's own steps (Approve, Hold, Print challan...) are buttons that **fold into "..."** when the line is short; set-up actions (print settings, sales stages, columns) are always behind "..." | `ToolbarCommand`, `menuOnly` |
| A screen that builds its own header (quotations, returns, receipts, payments, counts, journal) puts its search and New on the same one line | `Phase2LineTools` |
| Filters that came with a search box (area, status, include deleted) move into the "+ filter" panel, so the line stays one line | `ManagementWorkspaceLayout` |
| A screen's own Refresh button is the line's refresh icon | `Phase2Refresh` |
| A frame inside another frame shows one title, not two | `phase2Frame` |
| Amounts right-aligned in Indian digits, quantities without trailing zeros -- read from the heading and the values, so no screen has to say so | `EnterpriseDataGrid` |
| Status in words ("On hold"), columns by priority (4.11) | `EnterpriseDataGrid` |
| Loading is a thin bar at the top, not a grey sheet over the screen | `LoadingOverlay` |
| Rarely used set-up is under CONFIGURATION in Masters, Sell (pricing, territories and routes) and Accounts (structure) | `MenuLayout` |

Products carries its wireframe (view 6): Unit, HSN, GST, MRP, Selling and
Stock with low stock in red, and Active / Low stock / No price counters; the
server now sends each product's stock and counts low stock and no price.

### 4.8 Documents (orders, invoices, receipts)

- Open **as a tab, full page**, not as a dialog.
- Header fields in a compact **two- or three-column grid**, lines in an
  editable grid entered by keyboard (Enter moves on, a new line appears), a
  **sticky totals footer** (taxable, tax, round-off, total).
- Actions in the page bar follow the status: Save, Approve, Print, Convert
  to...; the document's timeline and attachments in a collapsible right panel.


**As built (2026-09-26).** The owner approved the quotation wireframe (view 7) and
asked for the same on orders and invoices. All three are one screen drawn from the
same pieces (`desktop/lib/phase2/document_page.dart`): the top line with the number
and the buttons, a header that fills itself from the customer (marked "auto"), the
lines as a table, the terms, the totals with the amount in words, and a side panel
for the line being typed (rate and discount and where they came from, last price to
this customer, the CGST/SGST or IGST split, stock, the customer's balance, and on a
bill the serial numbers going out). Every change is priced by the server exactly as
saving would -- `POST /quotations/preview`, `/sales-orders/preview`,
`/sales-invoices/preview` stage the document and roll it back -- so what is shown
is what is stored. Each editor keeps its own state, payload and rules.

**Purchase orders (2026-09-26)** use the same pieces with the vendor in place of
the customer. The side panel shows the last price this vendor billed (with a "Use
the last price" button), the stock where the order is received, the vendor's GSTIN
and phone, and what approval needs. A new line starts at the product's purchase
price. Delivery schedule, notes and files, and history sit on a strip under the
header, so nothing the phase 1 dialog offered is lost. Send for approval, Approve
and Print are on the top line when the status allows them. Priced by
`POST /purchases/preview`.

**Goods receipts (2026-09-26)** are the same screen for what arrived. The lines
are the order's lines: ordered, received before, still due, then accepted, free,
rejected, damaged and batch, typed in the table (an accepted figure over what is
due turns red). The side panel holds the rest of the current line: the warehouse
it went to, expiry and manufacturing dates where the firm uses them, and remarks,
plus the receipt's totals. The receipt is not priced by the server: it is valued
at the order's rates, and the supplier's bill is a purchase invoice.

### 4.9 Home per role

A counter clerk, a storeman, an accountant and an owner get different homes:
today's numbers (sales, receipts due, stock below reorder), their to-do
(orders to approve, deliveries pending), favourites and recent documents.
Built from the same permissions the menu uses.

### 4.10 Keyboard

| Keys | Does |
| --- | --- |
| Ctrl+K or Alt+G | command box |
| Alt + the area's letter (underlined while Alt is held): Alt+H Home, Alt+S Sell, Alt+B Buy, Alt+T Stock, Alt+A Accounts, Alt+M Masters, Alt+R Reports, Alt+D Admin, Alt+O More; then arrows, Enter, Esc | open an area's drop-down panel and move in it (built 2026-09-26, Windows menu-bar convention; replaces Alt+1...8) |
| Ctrl+N | new record on the current list |
| Ctrl+S / Ctrl+Enter | save / save and close |
| Ctrl+Tab, Ctrl+W | next tab, close tab |
| F2 | edit the selected row |
| / or Ctrl+F | focus the list's search (a / typed inside a box stays a /) |
| F5, Delete | refresh the list; delete the selected row (as the toolbar's own icons, only when enabled) |
| Esc | close the drop-down, drawer or panel |

---

### 4.11 Adapting to the window

Every rule here is relative, so the same screen works from a small laptop
window to a wide monitor:

| As the window narrows | What gives way, in this order |
| --- | --- |
| Menu bar | areas that do not fit fold into **More v** (right to left); the command box shortens to an icon last |
| Page bar | the search box shrinks, then becomes the `/` key only; counters and chips that do not fit fold into **+**; actions fold into **...**, New stays |
| Lists | each column has a priority; low-priority columns (GST, credit limit, HSN, discount...) drop first; the grid scrolls sideways only after that; the user's own column choice always wins |
| Documents | header fields reflow from four columns to one; the recent-documents panel hides behind a button; the totals footer wraps but stays visible |
| Home | cards reflow into fewer columns, then one |

| As the window grows | What it gets |
| --- | --- |
| Height | more rows -- never bigger gaps |
| Width | more columns (the hidden ones come back), then the optional side panel (row preview, recent documents) opens by default |

**Column priority as built (2026-09-26).** `GridColumn.priority` is 1 (always
stays), 2 (goes next) or 3 (goes first). A screen may set it; otherwise it is
read from the heading -- GST, HSN, MRP, PAN, e-mail, credit limit, created and
notes are 3; phone, brand, type, group, territory, branch and warehouse are 2;
the leading column and everything else is 1. Among equals the rightmost goes
first. A status column reads as words ("On hold", not ON_HOLD), as the
wireframe; a long value ends in "..." at 260 px rather than holding its column
open.

Rows and fonts do not grow with the window; the density setting decides
them. Nothing is sized in fixed pixels except the thin bars (menu, tabs, page
bar, status bar).

### 4.12 Every menu follows permissions (owner, 2026-09-25)

Phase 2 adds more ways to reach a screen than phase 1 had. **Every one of them
shows only what the signed-in user may use in the current firm** -- the same
three checks the sidebar applies today, from the one module catalogue:
the user's **permission codes**, the firm's **business profile** (a module or
feature the profile does not run is not offered), and **firm context**
(firm-only screens need a firm chosen; platform-only screens need the platform
designation).

| Place | What is filtered |
| --- | --- |
| Menu bar | an area appears only if at least one of its items is allowed; an empty area is not shown at all |
| Drop-down panels and **More** | only allowed items; a column (group) with none left disappears |
| Open tabs | a tab restored from last time is dropped if its screen is no longer allowed (role changed, other firm) |
| Command box | screens, records and actions alike -- a record is found only if its list may be viewed, an action only if it may be done |
| **+ New** (both) | only record types the user may create |
| Favourites and recent | hidden while not allowed, kept for when they are again |
| Home | cards, figures and to-do items only from modules the role may view (a storeman sees no receivables) |
| Page bar | counters, chips and actions (Approve, Delete, Export...) follow their own permission, as buttons do today |
| Keyboard shortcuts | F8, F6, Alt+C... do nothing, with a short "not allowed" note, when the target is not allowed |
| Links inside screens | a link to a screen the user cannot open is plain text |

When the user switches firm or their roles change, every one of these
recalculates at once; nothing stays on screen from the previous firm.

**The server stays the authority.** Hiding is for a clean screen, not for
security -- every endpoint keeps checking its own permission as it does today,
so a hidden item reached any other way is still refused.

### 4.13 Settings: one place, by topic (owner, 2026-09-25)

Phase 1 has settings in **six different modules** (Tax Settings under
Administration; Branch & Warehouse Settings, Firm Settings and Financial Years
under Masters; Purchase Settings; Inventory Settings) and **five more as
dialogs** inside other screens (sales workflow on Sales Invoices, credit
control on Customers, the loyalty scheme on Loyalty, TCS on the TCS page, print
settings on three document lists), plus Application Settings on the sign-in
screen. Nobody can find them all.

Phase 2 gathers them behind the **Settings gear** in the menu bar -- the
convention of Zoho, Odoo, QuickBooks and Xero. Settings is the one page that
keeps a list of sections down its left side, because it is a page somebody
visits to look through, not a place they work:

| Section | What it holds (phase 1 home in brackets) |
| --- | --- |
| **Firm** | Firm Settings (Masters), Financial Years (Masters), Numbering Series (Administration) |
| **Selling** | Sales workflow stages (dialog on Sales Invoices), Credit control (dialog on Customers), Loyalty scheme (dialog on Loyalty), TCS (dialog on TCS) |
| **Buying** | Purchase Settings (Purchases) |
| **Stock** | Inventory Settings (Inventory), Branch & Warehouse Settings (Masters) |
| **Tax** | Tax Configuration, Tax Rules, Rule Simulator, Execution Log, Tax Settings (all Administration) |
| **Business profile** | Feature Management, Module Configuration, Attribute Definitions, Mandatory Attributes, Profile Assignment, Industry Templates (Administration) |
| **Printing** | print settings for invoices, delivery notes and purchase orders (dialogs on three lists) |
| **This PC and me** | server address (Application Settings), theme, density, landing page, export format, printer -- per user and per PC |

- Each section and each setting follows permissions (4.12): a sales manager
  sees Selling but not Tax; a user with no settings permission sees only
  **This PC and me**.
- A screen that has settings of its own keeps a **Settings** item under its
  page bar's **...**, which opens the gear page at that section -- so the
  setting is findable both ways.
- The Ctrl+K box finds every setting by name ("credit limit", "numbering").

### 4.14 Clear to read, easy on the eyes all day (owner, 2026-09-26)

The owner's rule: every screen must be **clearly visible**, and its colours and
contrast must **not tire the eyes** of somebody who works on it all day. Both
halves matter -- too faint and it cannot be read (D-QA-1's hover), too harsh
and it tires. Phase 2 follows the accessibility standard (WCAG 2.2, level AA)
and the conventions of tools built for long sessions:

| Rule | Measure |
| --- | --- |
| Text is readable | body text at least **4.5 : 1** against its background; large text and headings at least 3 : 1 |
| Controls can be seen | borders, focus rings, checkboxes, icons and the hover/selected state of a row or button at least **3 : 1** -- nothing that says "you can click here" is faint |
| No glare | the page is a soft off-white, not pure `#FFFFFF`, and text is a dark grey-black, not pure `#000000`; the contrast stays well above AA without the harshness of black on white |
| Calm colour | colour is kept for meaning -- status, warnings, the one primary button -- never for large areas or backgrounds; no saturated bands across the screen |
| Colour is never the only signal | a status has a word or an icon as well (Overdue, Approved), so it reads for anybody and on any monitor |
| Dark theme | a proper dark theme (dark grey, not black), meeting the same measures, for users who prefer it; the choice is per user in **This PC and me** |
| Size | the default text is never below 13 px; the density setting changes spacing, not text size; Windows display scaling (125 %, 150 %) is honoured (section 9, item 9) |

All colours come from `design_tokens.dart`, so the measures are checked once,
there: phase 2 adds a test that computes each foreground / background token
pair's contrast ratio and fails the build below these figures, in light and
dark. The high-detail look-and-feel mock-up (section 9, item 7) is judged
against this table.


**Phase 2 matches the wireframe's colours (owner, 2026-09-26).** Comparing the app
with the wireframe, the owner found the text a little light and the backgrounds not
the same. The phase 2 light theme now takes the wireframe's own colours: white
(#ffffff) where work is done, neutral greys for headings, bars and tabs (#f3f4f6,
#e5e7eb) instead of the earlier bluish greys, row lines #eaeef2, and text a shade
darker (#16191d) because Flutter draws Segoe UI thinner than a browser. This
replaces this section's "off-white, not pure white" for phase 2 only; phase 1 and
the dark theme are unchanged, and every text pair still passes the 4.5 : 1 test.

### 4.15 The same app on a phone (owner, 2026-09-26)

The owner will use the same UI in the mobile app. The desktop layout cannot
simply shrink to a phone: a phone is 360-430 px wide, and the menu bar, the
drop-down columns and a nine-column grid need 1,000 or more. The convention
of Zoho, Odoo and Business Central is **one app, one set of screens and
rules, and a phone layout** chosen by width -- not a second app:

| Width | Layout |
| --- | --- |
| 1,000 px and more | the desktop layout of this document |
| 600-1,000 px (tablet, half a screen) | the same, folded as 4.11 says: areas into **More**, columns by priority |
| below 600 px (phone) | **bottom bar** with Home, Sell, Stock, Money and More; each area opens as a full-screen list of its items; the command box is the search icon at the top |

On a phone:

- **Lists become cards**: each row shows its two or three key fields (number,
  customer, amount, status) and the rest open on tap. The column priority of
  4.11 decides which fields a card shows, so nothing is designed twice.
- **Documents are entered a section at a time**: header, then lines (one card
  per line, add with a button), then totals and save -- the same fields and
  the same rules as the desktop screen.
- **Open-screen tabs** are replaced by the phone's own back gesture; filters
  and counters stay chips, scrolling sideways.
- **Permissions, colours (4.14) and every server rule are the same**, because
  it is the same code.

What the phone offers first is the field-sales day -- orders, receipts,
customer ledger, stock enquiry and route calls; administration, settings and
reports stay desktop screens, reachable on a phone but not reworked for it.
The shell is built with the phone breakpoint from its first version, because
adding it afterwards means reworking every screen twice.

## 5. What does not change

- The **module catalogue** stays the single source of screens; phase 2 adds
  an `area` and a `group` to each entry instead of hand-building menus.
- **Permissions, firm context and business-profile gating** stay exactly as
  implemented and tested.
- **Design tokens and theme** (`design_tokens.dart`, `ThemeManager`) stay the
  one place colours and fonts are defined; their values are re-checked against
  4.14.
- The **framework components** (`EnterpriseDataGrid`, `ResourceDefinition`,
  dialogs, form fields) are reused; the shell and the page frame are what
  change.
- The backend: **no API change** is needed for navigation and layout.

## 6. How it would be built (after agreement)

1. **Shell first**: menu bar, drop-down panels, command box, tabs. Phase 2 is
   **its own app** (owner, 2026-09-26): `lib/main_phase2.dart` starts it,
   its frame lives in `lib/phase2/`, and phase 1 (`lib/main.dart`) is left
   exactly as it is, with no switch inside it. Both share the screens, the
   server connection and the permission rules; only the frame differs. Run it
   with `flutter run -d windows -t lib/main_phase2.dart`.
2. **Page frame**: one-line page bar, chips, status-bar pager, density. Every
   list screen gains it at once because they share `ManagementWorkspaceLayout`.
3. **Documents as full-page tabs**, one document type at a time, starting
   with Sales Orders and Sales Invoices.
4. **Role homes.**
5. Once every screen has moved, phase 2 becomes `main.dart` and phase 1's
   frame is deleted.

Each step is its own set of PRs with the existing guards (catalogue parsing,
permission gating, 1366 x 768 overflow tests) extended to the new shell.

## 7. Measures of done

- A list shows **>= 15 rows** at 1366 x 768 and **>= 25** at 1920 x 1080.
- Any screen reachable in **<= 2 clicks or one Ctrl+K search**, never a
  scroll through a menu.
- A sales order can be entered start to finish **without the mouse**.
- A counter clerk bills a known customer for three known products in
  **under 30 seconds**.
- No band above any grid except the page bar.
- No screen overflows at any window size from 1366 x 768 up, and the
  grid always takes the rest of the window (tested at 1366 x 768,
  1920 x 1080, 2560 x 1440 and a half-width window).

## 8. Decisions for the owner

Recommended answers first; each can be changed.

| # | Question | Recommended | Alternative |
| --- | --- | --- | --- |
| 1 | Menu style | **Agreed 2026-09-25: top menu bar with drop-down panels in columns** (4.1, 4.3) | (Not chosen) a 56 px icon rail on the left with fly-out panels |
| 2 | Number of areas | **Decided 2026-09-26: eight** (4.2). Odoo, Zoho and Business Central all group by business area in a handful of top-level menus, and eight is what fits across the top bar | Keep 19 modules (would not fit across the top) |
| 3 | Open screens as tabs | **Decided 2026-09-26: yes**, up to 10, remembered per user. Desktop ERPs (SAP Business One, Busy, Business Central's multiple windows) let a clerk keep an order open while checking stock; the oldest unpinned, unchanged tab closes at the limit, and a tab with unsaved work is never closed silently | Single screen at a time, as today |
| 4 | Documents | **Decided 2026-09-26: full-page tab** (4.8), as Zoho, Odoo and Business Central do; a dialog cannot hold a long line grid and a totals footer at a small window | Keep dialogs, but full-size |
| 5 | Command box also for actions ("new sales order") | **Decided 2026-09-26: yes** -- the convention of Business Central's "Tell me", Odoo's command palette and Tally's Go To; actions follow permissions (4.12) | Screens and records only |
| 6 | Tally-style keys (Alt+G, Enter-driven line entry) | **Decided 2026-09-26: yes, in addition to** the standard Windows keys (4.10) -- nothing standard is taken away. Tally, Busy and Marg users are the market | Standard Windows keys only |
| 7 | Default density on laptops | **Decided 2026-09-26: compact (34 px)** below 900 px of window height, comfortable above (4.7); the user's own choice always wins. Data-heavy ERPs (Business Central, SAP) default dense | Comfortable (42 px) |
| 8 | Role homes | **Decided 2026-09-26: yes**, one per seeded role family (Business Central's Role Centres; Odoo and Zoho show per-app dashboards). Built from the same permissions as the menu; a role with no home of its own gets the general one | One dashboard for everyone |
| 9 | Roll-out | **Owner, 2026-09-26: phase 2 is built as its own app** beside phase 1 (`lib/main_phase2.dart`, `lib/phase2/`), with no switch inside phase 1, so the two are never confused. It replaces phase 1 once the last screen has moved (section 6, step 5); phase 1 also lives on in the `ui-phase-1` tag | Replace in one release |
| 10 | Summary cards and filters above lists | **Agreed in principle 2026-09-25: moved into the page bar as clickable counters and chips; cards only on Home** (4.5) | Keep a collapsible summary strip |
| 11 | Tally voucher keys (F8, F9, F6, F5, F7) on daily screens | **Decided 2026-09-26: yes** (4.6), active on Home and the daily screens. F5 therefore does not mean refresh anywhere; refresh is Ctrl+R. F2 stays "edit the selected row" on lists; inside a voucher it changes the date, as in Tally | Only Ctrl-based shortcuts |
| 12 | Which screens count as "daily" | **Decided 2026-09-26: the nine listed in 4.6**; each role's home and its favourites start from the ones that role may open | Owner's own list |
| 13 | Settings | **Agreed 2026-09-25: one Settings page behind a gear, by topic** (4.13), every phase 1 screen kept (appendix A) | Leave each setting in its module |

Clickable wireframes of the shell, the Customers list (with today's screen
beside it), a billing screen and a role home: `dist\windows\Design\UI phase 2
wireframes.html` -- they fill the browser window and adapt as it is resized.

All thirteen are now answered. Next: build, in the order of section 6,
showing the owner the first screen of each kind before it is repeated
(section 9). The owner reviews the 2026-09-26 answers as they appear on
screen; changing one is a change to this table first.

## 9. Open topics, decided screen by screen

Agreed with the owner on 2026-09-25: the shell, navigation, page bar, Settings
and permissions above are the frame; the topics below are **decided screen by
screen during implementation**, each shown to the owner on its first screen
before it is repeated on the rest. Where one needs a decision, it is added to
section 8 at that point.

**Before or with the first screens**

1. **Master forms** (customer, product, vendor) -- full-page tab or side
   panel; their inner tabs (addresses, contacts, bank, attributes); where
   validation errors show.
2. **Printing and sharing** -- preview, A4 and thermal, copies, send as PDF
   by email or WhatsApp. Billing depends on it.
3. **Reports screen** -- filters, totals, drill-down from a figure to the
   documents behind it, export and print.
4. **Messages** -- saved, errors, "unsaved changes -- leave anyway?",
   connection lost, credit-limit warnings, approval prompts: one look
   everywhere.
5. **Record history** -- a timeline on each document (created, approved,
   printed, who changed what) and its attachments.
6. **Owner review** of the section 8 answers decided on 2026-09-26.

**With the screens they touch**

7. **Look and feel** -- colours, fonts, logo, light and dark; one
   high-detail mock-up to approve before the shell is coded.
8. **Indian formats as rules** -- lakh/crore grouping (1,12,050.00),
   dd-mm-yyyy, the rupee sign, amount in words on bills.
9. **Windows display scaling** -- 125 % and 150 % scaling and larger text
   (see D-QA-1).
10. **Branch and warehouse context** -- a user's own default (BACKLOG section
    44) and where it shows beside the firm switcher.
11. **First run** -- a new firm's set-up checklist and the empty screens a
    new customer meets first.
12. **Help** -- F1 on any screen, a shortcut sheet, a short "what is new"
    tour when phase 2 is switched on.
13. **Import screens** (BACKLOG section 46) in the same design.

**Later**

14. Very large lists (paging or endless scroll, loading placeholders).
15. Approvals and notifications (a bell: "3 orders waiting for you").
16. Phone and tablet -- decided in 4.15 (2026-09-26): one app with a phone layout below 600 px, field-sales screens first.

---

## Appendix A. Every phase 1 screen, and where it goes

Compiled from `module_catalog.dart` on 2026-09-25: 19 modules, every tab, and
the settings dialogs. **Nothing is removed**; a screen only moves. A test in
phase 2 will read the catalogue and fail if any phase 1 screen has no place.

| Phase 1 (module > screen) | Phase 2 (area > group > item) |
| --- | --- |
| Dashboard | Home |
| Quotations | Sell > Documents > Quotations |
| Sales Orders | Sell > Documents > Sales Orders |
| Delivery Notes > Delivery Notes | Sell > Documents > Delivery Notes |
| Sales Invoices > Sales Invoices | Sell > Documents > Sales Invoices |
| Sales Returns | Sell > Documents > Sales Returns |
| Sales > Proforma | Sell > Documents > Proforma |
| Sales > Credit Notes | Sell > Documents > Credit Notes |
| Finance > Receipts | Sell > Money > Receipts |
| Finance > Refunds | Sell > Money > Refunds |
| Masters > Statements | Sell > Money > Customer Statements |
| Sales > Price Lists | Sell > Pricing > Price Lists |
| Sales > Promotions | Sell > Pricing > Promotions |
| Masters > Loyalty | Sell > Pricing > Loyalty |
| Sales > Commission | Sell > Incentives > Commission |
| Sales > Targets | Sell > Incentives > Targets |
| Sales > Geography (territories) | Sell > Field sales > Territories |
| Sales > Route Types | Sell > Field sales > Route Types |
| Sales > Beat Plans | Sell > Field sales > Beat Plans |
| Sales > Call Lists | Sell > Field sales > Call Lists |
| Sales > Coverage | Sell > Field sales > Coverage |
| Sales > Route Builder | Sell > Field sales > Route Builder |
| Purchases > Purchase Orders | Buy > Documents > Purchase Orders |
| Goods Receipts > Receipts | Buy > Documents > Goods Receipts |
| Purchase Invoices | Buy > Documents > Purchase Invoices |
| Purchase Returns | Buy > Documents > Purchase Returns |
| Finance > Payments | Buy > Money > Payments |
| Purchases > Dashboard | Buy > Insight > Purchase Dashboard |
| Purchases > Analytics | Buy > Insight > Purchase Analytics |
| Inventory > Inventory | Stock > Stock > Inventory |
| Inventory > Stock Summary | Stock > Stock > Stock Summary |
| Inventory > Stock Search | Stock > Stock > Stock Search |
| Inventory > Stock Ledger | Stock > Stock > Stock Ledger |
| Inventory > Transactions | Stock > Stock > Transactions |
| Inventory > Opening Stock | Stock > Movements > Opening Stock |
| Inventory > Physical Count | Stock > Movements > Physical Count |
| Inventory > Batches | Stock > Tracking > Batches |
| Inventory > Lots | Stock > Tracking > Lots |
| Inventory > Serial Numbers | Stock > Tracking > Serial Numbers |
| Inventory > Expiry Monitor | Stock > Tracking > Expiry Monitor |
| Inventory > Import | Stock > Data > Import |
| Inventory > Export | Stock > Data > Export |
| Finance > Chart of Accounts | Accounts > Books > Chart of Accounts |
| Finance > Journal Entries | Accounts > Books > Journal Entries |
| Finance > Ledgers | Accounts > Books > Ledgers |
| Finance > Trial Balance | Accounts > Statements > Trial Balance |
| Finance > Profit & Loss | Accounts > Statements > Profit & Loss |
| Finance > Balance Sheet | Accounts > Statements > Balance Sheet |
| Finance > Control Accounts | Accounts > Structure > Control Accounts |
| Finance > Cost Centres | Accounts > Structure > Cost Centres |
| Finance > Profit Centres | Accounts > Structure > Profit Centres |
| Sales > GST Returns | Accounts > Tax filing > GST Returns |
| Sales > E-Invoice | Accounts > Tax filing > E-Invoice |
| Sales > TCS | Accounts > Tax filing > TCS |
| Masters > Customers | Masters > Parties > Customers |
| Customers: customer groups dialog | Masters > Configuration > Parties > Customer Groups (owner, 2026-09-26: lookup lists apart from the everyday masters) |
| Masters > Vendors | Masters > Parties > Vendors |
| Masters > Vendor Categories | Masters > Configuration > Parties > Vendor Categories |
| Masters > Vendor Types | Masters > Configuration > Parties > Vendor Types |
| Masters > Products | Masters > Items > Products |
| Masters > Product Categories | Masters > Configuration > Items > Product Categories |
| Administration > Units of Measure | Masters > Configuration > Items > Units of Measure |
| Administration > UOM Groups | Masters > Configuration > Items > UOM Groups |
| Administration > Packaging Types | Masters > Configuration > Items > Packaging Types |
| Administration > Packaging Levels | Masters > Configuration > Items > Packaging Levels |
| Administration > Conversion Rules | Masters > Configuration > Items > Conversion Rules |
| Masters > Branches | Masters > Organisation > Branches |
| Masters > Warehouses | Masters > Organisation > Warehouses |
| Masters > Storage Areas | Masters > Configuration > Locations > Storage Areas |
| Masters > Branch Types | Masters > Configuration > Locations > Branch Types |
| Masters > Warehouse Types | Masters > Configuration > Locations > Warehouse Types |
| Masters > Places | Masters > Configuration > Locations > Places |
| Reports > Operational Reports | Reports > Operational |
| Reports > Financial Reports | Reports > Financial |
| Administration > Users | Admin > People > Users |
| Administration > Roles | Admin > People > Roles |
| Administration > Permissions | Admin > People > Permissions |
| Administration > User Templates | Admin > People > User Templates |
| Administration > User-Firm Assignments | Admin > People > User-Firm Assignments |
| Administration > Firms | Admin > Firms > Firms |
| Administration > Business Profiles | Admin > Firms > Business Profiles |
| Settings > Audit Logs | Admin > System > Audit Logs |
| Settings > Diagnostics | Admin > System > Diagnostics |
| Licensing | Admin > System > Licensing |
| Masters > Firm Settings | Settings > Firm |
| Masters > Financial Years | Settings > Firm |
| Administration > Numbering Series | Settings > Firm |
| Sales Invoices: sales workflow dialog | Settings > Selling |
| Customers: credit control dialog | Settings > Selling |
| Loyalty: scheme settings dialog | Settings > Selling |
| TCS: settings dialog | Settings > Selling |
| Purchases > Settings | Settings > Buying |
| Inventory > Settings | Settings > Stock |
| Masters > Branch & Warehouse Settings | Settings > Stock |
| Administration > Tax Configuration | Settings > Tax |
| Administration > Tax Rules | Settings > Tax |
| Administration > Rule Simulator | Settings > Tax |
| Administration > Execution Log | Settings > Tax |
| Administration > Tax Settings | Settings > Tax |
| Administration > Feature Management | Settings > Business profile |
| Administration > Module Configuration | Settings > Business profile |
| Administration > Attribute Definitions | Settings > Business profile |
| Administration > Mandatory Attributes | Settings > Business profile |
| Administration > Profile Assignment | Settings > Business profile |
| Administration > Industry Templates | Settings > Business profile |
| Print settings dialogs (invoices, delivery notes, purchase orders) | Settings > Printing |
| Sign-in screen: Application Settings | Settings > This PC and me (and still on the sign-in screen) |

