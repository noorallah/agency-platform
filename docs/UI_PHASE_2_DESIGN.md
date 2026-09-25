# Desktop UI, phase 2 -- navigation and screen space

**Status:** proposal for discussion, 2026-09-25. **No code** until the owner
agrees the decisions in section 8. The current desktop is **phase 1**: it
stays as it is, and keeps working, until phase 2 replaces it screen by screen.

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
  switcher**, help and the user menu on the right. The firm is changed
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
| **Admin** | Firms, Users, Roles, Business Profiles, Settings, Audit, Licensing |

The exact placement of every one of the 94 screens is a table to agree
(appendix A, to be written once section 8 is agreed); a role only ever sees
the areas and items its permissions allow, as today.

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

### 4.8 Documents (orders, invoices, receipts)

- Open **as a tab, full page**, not as a dialog.
- Header fields in a compact **two- or three-column grid**, lines in an
  editable grid entered by keyboard (Enter moves on, a new line appears), a
  **sticky totals footer** (taxable, tax, round-off, total).
- Actions in the page bar follow the status: Save, Approve, Print, Convert
  to...; the document's timeline and attachments in a collapsible right panel.

### 4.9 Home per role

A counter clerk, a storeman, an accountant and an owner get different homes:
today's numbers (sales, receipts due, stock below reorder), their to-do
(orders to approve, deliveries pending), favourites and recent documents.
Built from the same permissions the menu uses.

### 4.10 Keyboard

| Keys | Does |
| --- | --- |
| Ctrl+K or Alt+G | command box |
| Alt+1 ... Alt+8, or Alt then arrows | open an area's drop-down panel |
| Ctrl+N | new record on the current list |
| Ctrl+S / Ctrl+Enter | save / save and close |
| Ctrl+Tab, Ctrl+W | next tab, close tab |
| F2 | edit the selected row |
| / | focus the list's search |
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

Rows and fonts do not grow with the window; the density setting decides
them. Nothing is sized in fixed pixels except the thin bars (menu, tabs, page
bar, status bar).

## 5. What does not change

- The **module catalogue** stays the single source of screens; phase 2 adds
  an `area` and a `group` to each entry instead of hand-building menus.
- **Permissions, firm context and business-profile gating** stay exactly as
  implemented and tested.
- **Design tokens and theme** (`design_tokens.dart`, `ThemeManager`), colours,
  light/dark, fonts.
- The **framework components** (`EnterpriseDataGrid`, `ResourceDefinition`,
  dialogs, form fields) are reused; the shell and the page frame are what
  change.
- The backend: **no API change** is needed for navigation and layout.

## 6. How it would be built (after agreement)

1. **Shell first**, behind a switch in Settings ("New layout, preview"), so
   phase 1 stays the default and testers can compare: menu bar, drop-down
   panels, command box, tabs.
2. **Page frame**: one-line page bar, chips, status-bar pager, density. Every
   list screen gains it at once because they share `ManagementWorkspaceLayout`.
3. **Documents as full-page tabs**, one document type at a time, starting
   with Sales Orders and Sales Invoices.
4. **Role homes.**
5. Remove the switch and phase 1's shell once every screen has moved.

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
| 2 | Number of areas | **Eight** (4.2) -- also what makes the top bar fit | Keep 19 modules (would not fit across the top) |
| 3 | Open screens as tabs | **Yes**, up to about 10, remembered | Single screen at a time, as today |
| 4 | Documents | **Full-page tab** | Keep dialogs, but full-size |
| 5 | Command box also for actions ("new sales order") | **Yes** | Screens and records only |
| 6 | Tally-style keys (Alt+G, Enter-driven line entry) | **Yes** | Standard Windows keys only |
| 7 | Default density on laptops | **Compact (34 px)** | Comfortable (42 px) |
| 8 | Role homes | **Yes**, one per seeded role family | One dashboard for everyone |
| 9 | Roll-out | **Preview switch, then replace** (section 6) | Replace in one release |
| 10 | Summary cards and filters above lists | **Agreed in principle 2026-09-25: moved into the page bar as clickable counters and chips; cards only on Home** (4.5) | Keep a collapsible summary strip |
| 11 | Tally voucher keys (F8, F9, F6, F5, F7) on daily screens | **Yes** (4.6) | Only Ctrl-based shortcuts |
| 12 | Which screens count as "daily" | **The nine listed in 4.6**, confirmed per role | Owner's own list |

Clickable wireframes of the shell, the Customers list (with today's screen
beside it), a billing screen and a role home: `dist\windows\Design\UI phase 2
wireframes.html` -- they fill the browser window and adapt as it is resized.

Next: agree or change the open answers (1 and 10 are agreed); then appendix A (every screen's
area, group and label) and clickable mock-ups of the shell, a list and a
sales order are prepared for review before any code.
