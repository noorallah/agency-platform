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
2. **Any screen in two actions**, without scrolling a menu: click area →
   click item, or Ctrl+K → type → Enter.
3. **Keyboard complete.** Every list and every document can be driven without
   the mouse, the way Tally users expect.
4. **Nothing permanent that is not data.** Menus fly out and close;
   descriptions become a help icon; side panels open on request.
5. **Same rules, same data.** Permissions, business-profile module gating and
   the module catalogue stay exactly as they are (they are correct and
   tested); phase 2 changes how they are *shown*.

---

## 4. The proposed shell

### 4.1 Layout

```
+----+------------------------------------------------------------------------------+
|    | [QA01 Traders v]  [ Search or jump to...  Ctrl+K ]      [+ New v]  [?] [SN v] |  top bar 44 px
| A  +------------------------------------------------------------------------------+
| R  | Sales Order SO-QA01-0012 x | Invoices x | Stock Ledger x |                       |  open tabs 32 px
| E  +------------------------------------------------------------------------------+
| A  | Sales Orders  >  Open          [Filters: Status=Open x] [Branch=HO x] [+]  (i)  |  page bar 44 px
|    |                                              [Approve] [Print] [...]  [+ New]  |
| R  +------------------------------------------------------------------------------+
| A  |  #  | Number        | Date       | Customer          | Amount    | Status     |
| I  |  1  | SO-QA01-0012  | 25-09-2026 | QA Retail         |  1,770.00 | Approved   |
| L  |  2  | ...                                                                       |
|    |  ... about 16 rows at 34 px ...                                               |
| 56 |                                                                               |
| px +------------------------------------------------------------------------------+
|    | 128 records  |  3 selected  |  Page 1 of 7  < >  |  Ready                     |  status bar 28 px
+----+------------------------------------------------------------------------------+
```

- **Area rail, 56 px**, icons with a short label under each. It is always
  visible, and too narrow to cost anything.
- **Top bar, 44 px**: firm switcher, the **command box**, **+ New** (quick
  create), help, user menu.
- **Open tabs, 32 px**: every screen or document opened stays as a tab, so a
  sales order and its invoice can be switched between without navigating.
  Closeable, reorderable, remembered per user.
- **Page bar, 44 px, one line**: title, filter chips, actions. The description
  sentence moves behind the (i) icon.
- **Status bar, 28 px**, now also holds the pager.

At 1366 x 768 that leaves **about 16 rows** of grid (compact density),
against 8 today.

### 4.2 Eight areas instead of nineteen modules

| Area (rail) | Contains (today's modules and tabs) |
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

### 4.3 The flyout menu (replaces the long tree)

Clicking **Sell** on the rail opens a panel over the page, **in columns**,
not a tree:

```
+----+--------------------------------------------------------------+
|Sell| DOCUMENTS            PRICING            FIELD SALES           |
| *  |  Quotations           Price Lists        Territories          |
|    |  Sales Orders   *     Promotions         Routes & Beats       |
|    |  Delivery Notes       Loyalty            Call Lists           |
|    |  Sales Invoices                          Coverage             |
|    |  Sales Returns        MONEY                                   |
|    |  Proforma             Receipts                                |
|    |  Credit Notes         Customer Statements                     |
|    |                                                              |
|    |  * = favourite (click the star to pin)     Esc closes         |
+----+--------------------------------------------------------------+
```

- Everything in an area is visible **at once** -- no scrolling, no expanding.
- It closes on choice, on Esc, or on clicking away. A **pin** keeps it open
  as a narrow panel for someone who prefers that.
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

### 4.5 List screens

- **Filter chips** in the page bar replace the collapsible filter tile; "+"
  opens a filter drawer on the right. Saved views ("My open orders") are
  chips too.
- **Density**: compact (34 px) by default below 900 px of height,
  comfortable above; the user can switch. (The three densities already exist
  in `design_tokens.dart`.)
- **Row preview**: selecting a row can open a **side panel** (on request, not
  permanent) with the record's key facts and actions; double-click or Enter
  opens it fully.
- Column chooser, sort, and CSV/XLSX export stay as today.

### 4.6 Documents (orders, invoices, receipts)

- Open **as a tab, full page**, not as a dialog.
- Header fields in a compact **two- or three-column grid**, lines in an
  editable grid entered by keyboard (Enter moves on, a new line appears), a
  **sticky totals footer** (taxable, tax, round-off, total).
- Actions in the page bar follow the status: Save, Approve, Print, Convert
  to...; the document's timeline and attachments in a collapsible right panel.

### 4.7 Home per role

A counter clerk, a storeman, an accountant and an owner get different homes:
today's numbers (sales, receipts due, stock below reorder), their to-do
(orders to approve, deliveries pending), favourites and recent documents.
Built from the same permissions the menu uses.

### 4.8 Keyboard

| Keys | Does |
| --- | --- |
| Ctrl+K or Alt+G | command box |
| Alt+1 ... Alt+8 | open an area's flyout |
| Ctrl+N | new record on the current list |
| Ctrl+S / Ctrl+Enter | save / save and close |
| Ctrl+Tab, Ctrl+W | next tab, close tab |
| F2 | edit the selected row |
| / | focus the list's search |
| Esc | close the flyout, drawer or panel |

---

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
   phase 1 stays the default and testers can compare: rail, top bar,
   flyouts, command box, tabs.
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
- No screen overflows from 1366 x 768 up (as today).

## 8. Decisions for the owner

Recommended answers first; each can be changed.

| # | Question | Recommended | Alternative |
| --- | --- | --- | --- |
| 1 | Menu style | **Icon rail + flyout in columns** (4.1, 4.3) | Top horizontal menu bar per area (Odoo style), no rail at all |
| 2 | Number of areas | **Eight** (4.2) | Keep 19 modules, only make the menu flyout |
| 3 | Open screens as tabs | **Yes**, up to about 10, remembered | Single screen at a time, as today |
| 4 | Documents | **Full-page tab** | Keep dialogs, but full-size |
| 5 | Command box also for actions ("new sales order") | **Yes** | Screens and records only |
| 6 | Tally-style keys (Alt+G, Enter-driven line entry) | **Yes** | Standard Windows keys only |
| 7 | Default density on laptops | **Compact (34 px)** | Comfortable (42 px) |
| 8 | Role homes | **Yes**, one per seeded role family | One dashboard for everyone |
| 9 | Roll-out | **Preview switch, then replace** (section 6) | Replace in one release |

Next: agree or change the nine answers; then appendix A (every screen's
area, group and label) and clickable mock-ups of the shell, a list and a
sales order are prepared for review before any code.
