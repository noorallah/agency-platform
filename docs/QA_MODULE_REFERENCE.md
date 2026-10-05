# QA module reference -- release 1.3.0

Written 2026-10-04 for the testers of Agency Platform 1.3.0. One section per
module, in the same order and with the same names as `docs/QA_TEST_BOOK.md`.
It tells you **what to set before you test a module, which screens to open,
what to try, what must change elsewhere, who may and may not reach it, and what
is deliberately not built.** It does **not** repeat the test cases: it points to
them by id (QA-xxx-nn from the test book, TC-xxx-nnn from
`docs/INDEPENDENT_TEST_CASES.md`, also in `docs/qa/`).

**Release 1.3.0 includes everything in 1.2.0.** The 1.2.0 installer was never
built, so no tester has seen it; its light menu, Settings > Set up and
Platform, favourites, My preferences and the whole backlog build (Waves 1 to 3)
are part of this pass (`docs/RELEASE_NOTES_1.3.0.md`,
`docs/RELEASE_NOTES_1.2.0.md`).

**Added 2026-10-05: the purchasing and selling builds** (backlog 86 PG-1 to
PG-14, backlog 87 SG-1 to SG-9), also part of 1.3.0. Sections 5, 7, 11 and 12
below gained their settings, screens and checks. **These features have not
been through a full test suite, a CI run or a hand test**, and everything said
about them here was written from the code: read each such row as (confirm).

Sources: `docs/CONFIGURATION_SETTINGS_GUIDE.md` (settings, defaults, who may
change them), `docs/APPLICATION_FEATURES_GUIDE.md` (screens),
`desktop/lib/phase2/menu_layout.dart` (menu paths), `docs/QA_TEST_BOOK.md`
(sample data and cases), `docs/SALES_CHAIN_RULES.md`,
`docs/PURCHASE_TO_PAYMENT_FLOW.md`, `docs/LEDGER_POSTING_RULES.md`,
`docs/ACCESS_CONTROL_FRAMEWORK.md`. **(confirm)** marks a path, label or
behaviour that the sources do not settle; check it on the screen and write down
what you saw.

---

## How to use this reference

1. **Start with the sanity check**, `docs/qa/SANITY_CHECK.md` (the quick check,
   then the fifteen-step walk). If it fails, report that first; nothing below
   can be trusted until it passes.
2. **Build the sample firm.** Every case in the test book runs in one firm,
   **QA Book Traders (QB01)**, made from the values in the test book's *Sample
   data*. Run **QA-FRM-01 to QA-FRM-12** first; they create the firm, its
   administrator and the warehouse everything else needs.
3. **Go module by module, in the order below.** Later modules use what earlier
   ones created (the sale needs the purchase's stock; the GST return reads the
   sales). Run everything in **one calendar month**.
4. **For each module:** read *Configure first* and set each setting to the value
   shown, open the *Screens*, run the cases listed under *What to test*, and
   after every main action check *Verify elsewhere*. Screens read once when
   opened: press Refresh before judging a figure.
5. **A refusal is often the pass.** Where a case says something must be
   refused, the refusal and its message are the result.
6. Paths use the 1.3.0 light menu: **Sell, Buy, Stock, Accounts, Masters**
   each open a short daily drop-down; everything else is behind **All <Area>
   screens** at its foot, by group. **Settings** is the gear at the right of the
   bar and has three parts: **Settings** (This PC and me, Firm, Selling,
   Buying, Stock, Tax, Business profile), **Set up** (Pricing, Territories &
   routes, Account structure, Party lists, Item lists, Locations) and
   **Platform** (People, Firms, Agency, System). **Ctrl+K** finds any screen by
   name. Passwords in the book are all `QaTest@2026pw`.

### Module index

| # | Module | Test book ids | Cases | Detailed cases (`docs/qa/`) |
| --- | --- | --- | --- | --- |
| 1 | Sign-in & my settings | QA-SIG-01..20 | 20 | `02_SIGN_IN_AND_ACCOUNTS` |
| 2 | Users & roles | QA-USR-01..16 | 16 | `01_ROLES_AND_ACCESS`, `03_USERS_AND_ROLES` |
| 3 | Firm set-up & configuration | QA-FRM-01..20 | 20 | `04_FIRMS_AND_CONFIGURATION` |
| 4 | Masters | QA-MST-01..21 | 21 | `05_MASTERS` |
| 5 | Purchasing | QA-BUY-01..20 | 20 | `06_PURCHASING` |
| 6 | Inventory | QA-INV-01..15 | 15 | `07_INVENTORY` |
| 7 | Selling | QA-SELL-01..36 | 36 | `08_SELLING` |
| 8 | Pricing & incentives | QA-PRC-01..24 | 24 | `09_PRICING_AND_INCENTIVES` |
| 9 | Territory & field sales | QA-TER-01..10 | 10 | `10_TERRITORY` |
| 10 | GST & compliance | QA-GST-01..20 | 20 | `11_COMPLIANCE` |
| 11 | Finance | QA-FIN-01..20 | 20 | `12_FINANCE_AND_REPORTS` |
| 12 | Reports | QA-REP-01..13 | 13 | `12_FINANCE_AND_REPORTS` |
| 13 | Approvals & notifications | QA-APR-01..11 | 11 | `12_FINANCE_AND_REPORTS` |
| 14 | Platform administration | QA-PLT-01..11 | 11 | `04`, `12`, `13_CROSS_CUTTING` |
| 15 | Agency branding | QA-BRD-01..24 | 24 | `02_SIGN_IN_AND_ACCOUNTS` (TC-ME-014..018) |
| 16 | Purchasing & selling build of 2026-10-05 (covered in sections 5 and 7 below) | QA-BUY-21..34, QA-SELL-37..45 | 23 | `06_PURCHASING` (TC-BUY-029..090), `08_SELLING` (TC-SELL-036..087) |
| | **Total** | | **304** | |

---

## 1. Sign-in & my settings

### What it is for
Signing in and out, the lockout, the light menu, favourites, Ctrl+K and each
person's own preferences (theme, text size, date format, first screen).

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Firm and administrator exist | QA-FRM-01..12 | -- | Every case (needs admin@qb01.test) |
| My Preferences: First screen | User menu > My preferences, or Settings > This PC and me | The screen I was last on | SIG-17 |
| My Preferences: Theme | same | Light (Light, Dark, Follow Windows) | SIG-14 |
| My Preferences: Text size | same | Default; **this PC only** | SIG-15 |
| My Preferences: Date format | same | dd-MM-yyyy | SIG-16, SELL-35 |
| My Preferences: Start in firm | same | Only offered with two or more firms | SIG-18 (add a second firm first) |
| Application Settings (server address) | Gear on the sign-in screen, before sign-in | This PC's server | Only if the server address is wrong |
| Failed sign-in lock | Server rule, not a setting | Locks after five wrong passwords for 15 minutes | USR-13 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Sign-in | On opening the app | Version 1.3.0; message on a wrong password does not say whether the account exists |
| Home | First screen after sign-in | Figures, RECENT INVOICES, TO DO, TAX CALENDAR, FAVOURITES; no Admin on the menu bar |
| Sell / Buy / Stock / Accounts / Masters drop-downs | Menu bar | Daily list only; **All <Area> screens (N)** at the foot; **Returns & notes** short list on Sell and Buy |
| Settings page | Gear | Sections, cards, search box (`price` finds Price Lists, Price Levels, Price Floor) |
| Ctrl+K search | Keyboard | Opens screens and records; starred screens first |
| My preferences | User menu (initials, top right) > My preferences | Four boxes (five with two firms); Save with no change just closes; Esc and Cancel keep the old values |
| My profile / Change password | User menu > My profile | Refusals beside the box ("Use at least 12 characters.", "Include a symbol.") |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Sign in, wrong password, sign out; firm switcher reads QB01 | QA-SIG-01, 02, 20; TC-SESS-001, TC-SESS-002, TC-ME-001 |
| Light menu: daily lists, Returns & notes, All screens, Settings page, Ctrl+K | QA-SIG-03..07; TC-ME-012, TC-ME-013 |
| Favourites: star, reorder, remove, starred-first in Ctrl+K, same on another PC | QA-SIG-08..11; TC-ME-011 |
| My preferences: dialog, no-change Save, Esc/Cancel, theme, text size, date format, first screen, start in firm | QA-SIG-12..18; TC-ME-009, TC-ME-010, TC-ME-002..004, TC-ME-007 |
| Password change refusals | QA-SIG-19; TC-ME-008 |
| Lockout and clearing it (Users module) | QA-USR-13, 14; TC-SESS-003, TC-SESS-004 |
| Forced password change at first sign-in (Users module) | QA-USR-03; TC-SESS-006 |
| Inactive or expired accounts told why | TC-SESS-005 (not in the book) |

### Verify elsewhere
- **Favourites:** Home > FAVOURITES and the drop-down star agree (SIG-08, 09); the list follows the person to another PC (SIG-11).
- **Date format:** a document's date and list dates follow it (SIG-16; SELL-35).
- **Text size:** changes on this PC only; another PC unchanged (SIG-15).
- **Start in firm:** takes effect at the next sign-in, not now (SIG-18).
- No ledger, stock or GST effect. Audit trail: sign-ins and failures appear in Settings > Platform > System > Audit Logs (platform administrator, or firm's trail for a firm audit viewer).

### Permissions to check
Everybody signed in may open My preferences (no permission needed, firm or not). The menus offer each person only what their role allows; the server refuses the rest. A firm user never sees **Platform** under Settings (TC-PLAT-005).

### Known limits
- **Rows per page** is not in My preferences. The old *Primary firm* menu entry is gone (replaced by *Start in firm*).
- **Help > About** is not built; clicking the product on the status line does nothing.
- A client-side cache of preferences and reference data was deferred: each screen reads what it needs when it opens.
- On the first sign-in after an upgrade the date format becomes dd-MM-yyyy by design.

---

## 2. Users & roles

### What it is for
Creating people, giving them a job (template) or hand-picked roles, custom roles,
hiring "like this person", lockout clearing, and what each job may reach.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Firm QB01 and admin@qb01.test | QA-FRM-03, 10 | -- | Everything |
| Job templates (platform's, locked) | Settings > Platform > People > User Templates | Eleven jobs seeded (Firm Administrator, Field Sales, Sales Manager, Counter Sales, Accounts, Warehouse ...) | USR-01, 02, 16 |
| Require password change | Users > New form | Off | USR-03 (Meena: on) |
| Roles in this firm / Job template | Users > New form | Naming a job decides the roles | USR-11 (no template, one custom role) |
| Custom role `qb-night-desk` | Settings > Platform > People > Roles > New | None | USR-08..12 |
| Clear login lock | Users > Edit | Off | USR-14 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Users | Settings > Platform > People > Users | New, Edit, **Hire like this person**, Delete, Clear login lock |
| Roles | Settings > Platform > People > Roles | Preset roles locked; custom role marked **Custom role**; platform codes never offered to a firm administrator |
| Permissions | Settings > Platform > People > Permissions | What each code allows and who holds it |
| User Templates | Settings > Platform > People > User Templates | Platform templates listed and locked (no Edit) |
| User-Firm Assignments | Settings > Platform > People > User-Firm Assignments | Which people belong to which firms (platform administrator) |
| Audit Logs | Settings > Platform > System > Audit Logs | User created, lock cleared, merged ... naming you |
| Each role's menus | Sign in as each person; open every menu | Exactly the screens the job should have (see Permissions) |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Create the six people; create by template | QA-USR-01, 02; TC-USER-001, TC-USER-003, TC-TMPL-003, TC-HIRE-001 |
| First sign-in forces a password change | QA-USR-03; TC-SESS-006 |
| Counter Sales sees only Receipts and Payments as money screens | QA-USR-04; TC-USER-009, TC-CASH-001 |
| Field Sales, Sales Manager, Accounts: menus and read-only settings | QA-USR-05..07; TC-PERM-001, TC-PERM-002, TC-PERM-003 |
| Custom role: platform codes not offered, reserved code refused | QA-USR-08..10; TC-ROLE-002, TC-ROLE-003, TC-ROLE-004 |
| A role gives exactly its codes' screens; editing a role signs holders out | QA-USR-11, 12; TC-ROLE-007, TC-ROLE-008 |
| Lockout after five failures, clear the lock | QA-USR-13, 14; TC-SESS-003, TC-SESS-004 |
| Hire like this person (clone gets the access, not the person) | QA-USR-15; TC-HIRE-002, TC-HIRE-003 |
| Platform templates listed and locked | QA-USR-16; TC-TMPL-001 |
| More (not in the book): templates by firm, role tiers, deleting people | TC-TMPL-002..015, TC-RTIER-001..008, TC-SESS-007..011, TC-LOOK-001..007 |

### Verify elsewhere
- **Audit trail:** each create, lock clear and merge-type action is recorded naming the actor (USR-01, 14). A deleted hire is gone from the list but the row stays in the trail (USR-15).
- **Menus:** a changed role takes effect on the holder's next click (signed out) (USR-12).
- No stock, ledger or GST effect.

### Permissions to check
User and role administration is the **firm administrator's** (firm tier) and the platform administrator's (global tier). **Sales Manager** may not change credit policy (Credit Control opens read-only), **Field Sales** has no Commission, Credit Notes, Price Lists, Promotions, GST Returns or TCS, **Counter Sales** has no Journal Entries, Ledgers or Trial Balance, **Warehouse** has Goods Receipts but not Payments or order approval (confirm, QA-BUY-20). A firm administrator holds `AUDIT_LOG_VIEW` but cannot grant it (TC-ROLE-004).

### Known limits
- Per-job screen lists are in `docs/qa/01_ROLES_AND_ACCESS.md` (computed from the role seed on 2026-10-03). A business profile can hide a module for a job; note it rather than failing.
- QA-USR-06 (Sales Manager screens; TCS Settings read-only) is marked (confirm) in the book.

---

## 3. Firm set-up & configuration

### What it is for
Creating and finishing a firm (the Set up panel), numbering series, and the
firm-level settings that change how every other module behaves.

### Configure first
Run in this order as the **platform administrator**, then switch to the firm.

| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Create firm QB01 (code, country, currency, FY start required) | Settings > Platform > Firms > Firms > + New | -- | FRM-02, 03 |
| Business profile **Food Distribution** (batch and expiry tracking) | Firm's **Set up** panel > Business profile > Assign; also Settings > Business profile > Profile Assignment | Platform default profile | FRM-05; MST-05, INV-04, SELL-20..23 |
| Open the books | Set up panel | -- | FRM-06; nothing can be approved without it |
| Apply GST template | Set up panel > Tax | -- | FRM-07; every tax figure |
| Head office and main warehouse | Set up panel | -- | FRM-08 |
| Places (state, district, city) | Settings > Set up > Locations > Places | Southern states preloaded (confirm for TN and KA) | FRM-09; every address |
| Numbering Series | Settings > Firm > Numbering Series | Set up with the firm; counter locked; restarts each financial year; GST numbers at most 16 characters | FRM-13 |
| Sales Stages | Settings > Selling > Sales Stages | Quotation, Sales order, Delivery note **all on** | FRM-14; SELL chain |
| Credit Control | Settings > Selling > Credit Control | **Warn** at 80, block at 100 | FRM-15; SELL-24, 25 |
| GST Documents | Settings > Tax > GST Documents | Dispatch before invoice **Warn**; e-invoicing blank; filing **Sandbox**; claim input credit on all bills | FRM-16; SELL-08; GST-07..13 |
| Batch Rules | Settings > Stock > Batch Rules | Near expiry 30 days; left behind **Warn**; skip earlier batch **Record**; below price floor allowed | FRM-17; SELL-20..23 |
| Rule Simulator | Settings > Tax > Rule Simulator | -- | FRM-18 |
| Feature Management | Settings > Business profile > Feature Management (platform administrator) | IMEI and other unbuilt features cannot be switched on | FRM-19 |
| Control Accounts | Settings > Set up > Account structure > Control Accounts | Mapped when the books open | FRM-20 |
| Financial Years: month-close check, ageing columns | Settings > Firm > Financial Years | **Warn**; 30, 60, 90 days | FIN-17 |
| Messaging | Settings > Firm > Messaging | **Off** | APR-10 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Firms | Settings > Platform > Firms > Firms | + New refusals; Set up panel (seven rows, verdict) |
| Set up panel | Firms > pick firm > **Set up** | Storage, Business profile, Books, Tax, Geography, Branches and warehouses, People; verdict ends **Finished. Every step is done.** |
| Profile Assignment | Settings > Business profile > Profile Assignment | QB01 on Food Distribution |
| Chart of Accounts | Accounts > All Accounts screens > Books | Cash 1000, Bank 1010, Trade Receivables 1100, Inventory 1200, Trade Payables 2100, Sales 4000, Cost of Goods Sold 5200 |
| Numbering Series | Settings > Firm > Numbering Series | Next number per document type, locked counter, Preview |
| Sales Stages / Credit Control / GST Documents / Batch Rules | Settings > Selling, Tax, Stock cards | Defaults as above; close without saving |
| Rule Simulator | Settings > Tax > Rule Simulator | CGST+SGST in state, IGST across |
| Control Accounts | Settings > Set up > Account structure | One row per posting purpose; lock after first posting |
| Branches, Warehouses | Masters daily drop-down | HO, MAIN, then STORE2 |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Platform administrator starts on Platform (no firm) | QA-FRM-01; TC-PLAT-001, TC-PLAT-002 |
| Firm create refusals; code upper-cased; first shared firm slower | QA-FRM-02, 03; TC-FIRM-002, TC-FIRM-003 |
| Set up panel: profile, books (once), GST template (once), head office (once) | QA-FRM-04..08; TC-FIRM-007..011, TC-FIRM-014 |
| Places, administrator, sign-in as administrator | QA-FRM-09..11; TC-FIRM-014 |
| Second warehouse | QA-FRM-12 |
| Numbering series: preview issues nothing; yearly restart needs the year; 16-character limit | QA-FRM-13; TC-CONF-001, TC-CONF-002, TC-CONF-003 |
| Defaults of Sales Stages, Credit Control, GST Documents, Batch Rules | QA-FRM-14..17; TC-FIN-009, TC-CUST-003, TC-CONF-007, TC-SELL-022 |
| Tax simulator; unbuilt feature refused; control accounts lock | QA-FRM-18..20; TC-CONF-004, TC-CONF-005, TC-FIRM-015 |
| More (not in the book): dedicated storage, isolation, custom fields | TC-FIRM-004..006, TC-FIRM-012, 013, 016, 017, TC-ISO-001..004, TC-FIELD-001..016 |

### Verify elsewhere
- **Books opened:** Chart of Accounts lists the accounts; the Set up panel row shows 1 financial year, 12 periods, control accounts mapped (FRM-06). A second press creates nothing.
- **GST template:** a product's tax profile list offers GST 0, 5, 12, 18 (Local and Interstate) and Exempt (FRM-07).
- **Numbering:** Preview twice shows the same number; the first invoice later takes it (FRM-13).
- **Control accounts:** after the first posting a row shows a lock and the count of posted lines (FRM-20).
- **Audit trail:** firm created, profile assigned, settings changed, each naming who (Settings > Platform > System > Audit Logs).
- A setting governs what happens next, not documents already approved.

### Permissions to check
Creating firms and setting them up is the **platform administrator's**; a firm administrator cannot reach Firms or Business Profiles at all (QA-PLT-10; TC-FIRM-016). Numbering Series needs `SETTINGS_UPDATE`; Sales Stages `SALES_MANAGE_SETTINGS` (not Sales Manager); Credit Control `CUSTOMER_MANAGE_SETTINGS` (Accounts, not Sales Manager); Batch Rules `SALES_MANAGE_SETTINGS`; GST Documents `TAX_MANAGE_SETTINGS`.

### Known limits
- **The Quotation stage switch changes nothing in 1.3.0**: it is saved and shown, but quotations stay available whatever it says.
- Tax Settings (labels) changes no calculation; Tax Configuration and Tax Rules do.
- Storage routing is fixed at creation; nothing moves a firm's data between stores.
- QA-FRM-07 counts ("10 tax profiles and 13 rules") are marked (confirm).
- Test-book sequencing: FRM-13..20 belong to the configuration pass and are run alongside or after the later modules named in their rows, not before FRM-12 only.

---

## 4. Masters

### What it is for
Customers, vendors, products, branches and warehouses, the lists behind them
(categories, units, groups), the firm's own custom fields, duplicate warnings,
merge, and import and export.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Places exist | Settings > Set up > Locations > Places | -- | Customer and vendor addresses (FRM-09) |
| Product Categories `CLEAN`, `GROC` | Settings > Set up > Item lists > Product Categories | None | MST-01..05 |
| Tax profiles (GST template) | FRM-07 | -- | Product tax profile |
| Business profile (Food Distribution) | FRM-05 | -- | **Track expiry** allowed (MST-05); Wholesale would refuse it |
| Custom Fields and Custom Field Rules | Settings > Firm > Custom Fields, Custom Field Rules | None | MST-16, 17 (FSSAI licence no) |
| Codes from a series | Numbering Series (CUS, SUP, PRD) | Blank code reads "Blank: issued on save" | MST-20 |
| New outlets wait for approval | Settings > Selling > Sales Stages | **Off** | Pending customers (TC-SELL-032) |
| Customer fields: credit limit, terms, standing discount, minimum shelf life, status | On the customer record | Limit 0 = no limit; Active | MST-09; SELL-24; PRC-11 |
| Supplier fields: status Blocked, GST type, issues e-invoices, payment terms | On the vendor record | Active | BUY-19 |
| Product fields: tracking, issue rule, MRP, minimum selling price, free issue only, not for sale | On the product | Off | MST-02, 05; SELL-34 |
| Customer Groups, Vendor Categories, Licence Types, Licence Check | Settings > Set up > Party lists | Licence check **Warn** | PRC-12 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Customers | Masters > Customers | New/Edit; Money tab; side panel (GSTIN, limit, outstanding); Merge into...; Export; Import opening bills; *Pending approval* filter |
| Vendors | Masters > Vendors | Address, bank account under *Pay to*; Catalogue, Ratings tabs |
| Products | Masters > Products | General, UOM & Size, Pricing, Tax; Margin in the side panel; Components (kit) |
| Branches, Warehouses | Masters daily drop-down (Organisation) | Branch GSTIN; warehouse under a branch |
| Trade Licences | Masters > All Masters screens > Compliance | Licence register with validity dates |
| Product Categories, Principals, Brands, Units | Settings > Set up > Item lists | Category tree, units, conversion rules |
| Customer Groups, Vendor lists | Settings > Set up > Party lists | Default discount; refuses removal while customers are in it (PRC-12) |
| Custom Fields | Settings > Firm > Custom Fields | Section appears on the customer form |
| Places | Settings > Set up > Locations > Places | Each level saves under its parent |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Categories; create and reopen a product; margin and above-MRP warning | QA-MST-01..04; TC-MAST-003 |
| Batch and expiry product | QA-MST-05 |
| Vendor create; edit one field keeps the rest | QA-MST-06..08; TC-MAST-001, TC-MAST-002 |
| Customer create; PAN fills from GSTIN | QA-MST-09, 10 |
| Refusals: GSTIN/PAN clash, duplicate code, blank name | QA-MST-11..13 |
| Same GSTIN on a second customer asks first (one company, two accounts) | QA-MST-14; TC-MAST-009 |
| Edit one field keeps the rest, audit trail | QA-MST-15; TC-CUST-001 |
| Custom field: save, survive an edit, make required | QA-MST-16, 17; TC-FIELD-007, TC-FIELD-008 |
| Duplicate warning and merge | QA-MST-18, 19; TC-MAST-012 |
| Code from a series; delete an unused product | QA-MST-20; TC-MAST-015 |
| Export | QA-MST-21; TC-MAST-007 |
| More (not in the book): import with one bad row, branch/warehouse rename, principals and brands, bank accounts, customer who is a supplier, PAN reports | TC-MAST-004..006, TC-MAST-008, TC-MAST-010, TC-MAST-011, TC-MAST-013, TC-MAST-014, TC-MAST-016, TC-CUST-002, TC-CUST-006 |

### Verify elsewhere
- **Audit trail:** customer updated or merged names you (MST-15, 19).
- **Search:** Ctrl+K finds the new product or customer (MST-03).
- **Merge:** the survivor's statement and balances are unchanged when the duplicate had nothing; with documents they move to the survivor.
- **Series:** a blank code takes the next from CUS, SUP or PRD (five digits).
- **Delete guards:** a customer or product with documents or stock cannot be deleted (SELL-33, 34).

### Permissions to check
Customers and products are viewed and edited by the sales and stock roles; **Customer Support** views and updates customers and views products only (nothing else). Changing a credit limit needs `CUSTOMER_MANAGE_SETTINGS`. Approving a pending outlet needs `CUSTOMER_APPROVE`. Field Sales cannot change masters.

### Known limits
- A kit inside a kit, and kit components priced on the bill, are not built.
- Barcode labels need a real printer to judge alignment.
- Customer and supplier import of opening bills and other imports: detailed cases only in `docs/qa/05_MASTERS` (not in the test book).
- Legal-entity duplicates are warned, never blocked (MST-18 says "does not block").

---

## 5. Purchasing

### What it is for
Requisition, purchase order, approval, goods receipt, supplier bill, payment,
return and debit note: the buying chain and what it books.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Suppliers QB-V1, QB-V2; products | Masters (MST) | -- | Every case |
| Purchase Settings: order stage, receipt stage | Settings > Buying > Purchase Settings | Both on | BUY-01..08 (leave on) |
| Purchase Settings: bill tolerance (rate %, whole bill amount) | same | No check | TC-BUY-022 (not in the book) |
| Purchase Settings: order quantities off supplier terms; past a budget | same | **Warn**; **Warn** | TC-BUY-019, 022 |
| Approval Limits (largest order per role) | Settings > Buying > Approval Limits | None | TC-BUY-001 |
| Purchase Budgets | Settings > Buying > Purchase Budgets | None | TC-BUY-022 |
| Approval Levels (purchase orders and bills) | Settings > Firm > Approval Levels | None: one approval is enough | QA-APR-07 |
| Reorder planning basis | Reports > Operational > Below reorder level | Typed levels | TC-BUY-015, 018 |
| GST Documents: claim input credit; supplier bill without an IRN; rule 37 mode | Settings > Tax > GST Documents | All bills; Warn; Report only | BUY-08, GST-06 |
| Supplier: status Blocked with reason; GST type; issues e-invoices | On the vendor | Active | BUY-19 |
| Licence Check, purchases | Settings > Set up > Party lists > Licence Check | **Warn** (Off or Warn only) | Licensed goods |
| Buying stages: **Purchase order** off (takes **Goods receipt** off) | Settings > Buying > Purchase Settings | Both on | TC-BUY-070..077 only. **Firm-wide: run those last or in a firm of its own, then switch back** |
| TDS 194C and 194J: threshold and rates | Settings > Tax > TDS on purchases (194Q, 194C, 194J) | As seeded (confirm) | TC-BUY-043..049 |
| Supplier: **Usual TDS section**, Individual / HUF, Technical services (2%) | On the vendor | None | TC-BUY-043..048: a supplier of its own with no other bill or payment this financial year |
| Supplier: **Currency** (three letters; blank is rupees) | On the vendor | Blank | TC-BUY-070..076 |
| Messaging on, WhatsApp channel on, template for *Purchase order sent to the supplier* | Settings > Firm > Messaging | Off | TC-BUY-054, 055 |
| Batch PTR / PTS feature (Pharmacy, Food, Wholesale profiles); customer **Trade class** | Business profile; on the customer | By profile | TC-BUY-082..085 |
| A serial-tracked product | Masters > Products | -- | TC-BUY-063..065 |
| Asset classes (five come with the firm) | Accounts > All Accounts screens > Fixed assets > Asset classes | Seeded | TC-BUY-077..081 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Requisitions | Buy > All Buy screens > Documents > Requisitions | Submit, approve, **Convert to orders** (one draft per supplier) |
| Purchase Orders | Buy > Purchase Orders | Totals and Tax box (CGST+SGST or IGST) before saving; status moves by receiving, never by hand |
| Goods Receipts | Buy > Goods Receipts | Remaining quantity pre-fills; Complete; e-way bill field |
| Purchase Invoices | Buy > Purchase Invoices | Supplier's invoice number; duplicate warning; Approve |
| Payments | Buy > Payments | Oldest first; TDS fields; offers only unpaid bills |
| Supplier Statements | Buy > Supplier Statements | Running balance in date order |
| Purchase Returns, Debit Notes | Buy > Returns & notes | Cap at received; credit/replacement/refund outcome |
| Approvals, Quality Inspection | Buy > All Buy screens > Documents | Waiting items |
| Payment Runs, Landed Costs, Supplier Rebates, Principal Claims, Post-dated Cheques, Supplier Gifts | Buy > All Buy screens > Money | Not in the test book; see TC-BUY-023..028 |
| Purchase Dashboard, Purchase Analysis, Rate Trend | Buy > All Buy screens > Insight | Orders, spend, rates |
| Requests for quotation | Buy > All Buy screens > Documents > Requests for quotation | Send, Enter quotes, Compare (lowest marked), Save selections, Raise orders; **Create RFQ** on an approved requisition |
| Rate contracts | Buy > All Buy screens > Documents > Rate contracts | Approve; drawn and remaining per line; Close, Cancel with a reason, Releases; the mark on an order line's rate and the over-draw banner |
| Supplier schemes | Buy > All Buy screens > Documents > Supplier schemes | Buy and free quantity, free product, dates; on the order the Free box and *Scheme 10+2 applied* |
| Bills of entry | Buy > All Buy screens > Documents > Bills of entry | Linked bills and receipts, duty rate and amount pairs, Post, Cancel with a reason |
| Payables by Month | Buy > All Buy screens > Money > Payables by Month | Months, Older, Credits, Outstanding, total row, books check, Owed / Paid, branch |
| Purchase bill window | Buy > Purchase Invoices | **Attachments**; TCS rate and amount; Currency and rate for a foreign supplier; **Capital goods** tick and asset class on a line; the Approve dialog's TDS proposal and **Paid now** |
| Goods receipt window | Buy > Goods Receipts | **Attachments**; the **Serials** cell; PTR and PTS on a batch line |
| Purchase order window | Buy > Purchase Orders | **Send** > WhatsApp |
| Fixed assets | Accounts > All Accounts screens > Fixed assets | Asset register, Asset classes, Depreciation runs, Income-tax block schedule |
| GST purchase register, HSN summary of purchases, TCS paid to suppliers | Reports > Financial | By tax head; by HSN and unit; by quarter |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Requisition becomes a draft order | QA-BUY-01; TC-BUY-020 |
| Order totals; draft cannot be approved without sending for approval; approval changes nothing | QA-BUY-02..04; TC-BUY-001, TC-BUY-002 |
| Part receipt, journal, then the rest | QA-BUY-05..07; TC-BUY-003 |
| Supplier bill, journal, duplicate invoice number warning | QA-BUY-08..10 |
| Invoiced receipt cannot be cancelled | QA-BUY-11; TC-BUY-005 (and TC-BUY-004, cancelling an uninvoiced receipt) |
| Payment applied; paid bill leaves the list | QA-BUY-12; TC-BUY-008 |
| Purchase return capped; credit; stock and journal | QA-BUY-13, 14; TC-BUY-006 |
| Debit note: price difference, tax, no stock | QA-BUY-15; TC-BUY-017 |
| Statement agrees | QA-BUY-16; TC-BUY-007 |
| Inter-state order (IGST), receive and bill | QA-BUY-17, 18 |
| Blocked supplier refused | QA-BUY-19 |
| Warehouse role limits | QA-BUY-20 |
| **Added 2026-10-05, none run by hand yet (confirm):** | |
| GST purchase register and HSN summary; debit notes and returns as minus rows; a foreign-currency bill in rupees | QA-BUY-21; TC-BUY-029..032, 089 |
| Payables by month agree with the books; Paid view; credits | QA-BUY-22; TC-BUY-033..035 |
| Approve and pay in one step; part payment; over the bill refused; needs the right to record payments | QA-BUY-23; TC-BUY-036..039 |
| Attach, open, save, delete; wrong type and over-size refused; who may add | QA-BUY-24; TC-BUY-040..042 |
| TDS 194C and 194J: single bill and yearly limit, no PAN, individual, deducted once, override, settings | QA-BUY-25; TC-BUY-043..049 |
| TCS on a bill: rate or amount, paying it, cancelling, the quarterly report | QA-BUY-26; TC-BUY-050..053 |
| Purchase order by WhatsApp: refused until set up; marked sent | QA-BUY-27; TC-BUY-054, 055 |
| RFQ: quotes, comparison, a reason off the lowest, orders per supplier, from a requisition, who may raise orders | QA-BUY-28; TC-BUY-056..059 |
| Rate contract prices the line; drawn and remaining; over-draw warns; overlap, expiry, close, cancel | QA-BUY-29; TC-BUY-060..062 |
| Serials at receipt: typed, pasted, range; unique in the firm; cancel and return | QA-BUY-31; TC-BUY-063..065 |
| Supplier scheme fills Free; typed figure and 0; another product as a gift line; overlap | QA-BUY-30; TC-BUY-066..069 |
| Imports on the full chain: currency and rate on the order, receipt at the order's rate, the bill in the order's currency, payment at another rate, part payment, refusals, Bill of Entry, revaluation; a bill typed alone (TC-BUY-086, stages off) | QA-BUY-33; TC-BUY-070..076, 086, 087 |
| Fixed assets: capital goods on the order and receipt line, received without stock, the bill raises the asset; refusal for a line already in stock; depreciation run, disposal, cancelling a run, block schedule; a bill typed alone (TC-BUY-088, stages off) | QA-BUY-34; TC-BUY-077..081, 088, 090 |
| PTR and PTS on the batch; never above MRP; retailer and stockist prices; a firm without the feature | QA-BUY-32; TC-BUY-082..085 |
| More (not in the book): return outcomes, input credit blocked, composition supplier, 2B, reorder, rates and catalogue, inspection, tolerance, payment runs, ratings, rebates, landed cost, supplier credit on opening bill, free goods | TC-BUY-009..016, TC-BUY-018, TC-BUY-019, TC-BUY-021..028 |

### Verify elsewhere
| After this action | Check |
| --- | --- |
| Approve order | **Nothing** moves: no stock, no journal (BUY-04) |
| Complete receipt | Stock > Stock Summary and Stock Ledger (GOODS_RECEIPT +n); journal **Dr Inventory / Cr Goods Received Not Invoiced** at cost, no tax (BUY-06) |
| Approve bill | Journal **Dr Goods Received Not Invoiced, Dr Input CGST/SGST (or IGST) / Cr Trade Payables**; Supplier Statements; GSTR-3B table 4 (GST-06) |
| Record payment | **Dr Trade Payables / Cr Bank**; the bill leaves the next payment's list |
| Approve return | Stock down (RETURN); **Dr Trade Payables / Cr Inventory, Cr Input CGST/SGST**; bill owes less |
| Approve debit note | **Dr Trade Payables / Cr Purchase Price Variance, Cr Input tax**; no stock moves |
| TDS on payment | **Cr TDS Payable**; Reports > Financial > TDS deducted (GST-16) |
| Every step | Audit trail; numbering series (PO-, GRN-, own series each) |
| Approve a bill with **Paid now** | A payment `PY-` for the amount on Buy > Payments, allocated to the bill; the bill owes the rest (TC-BUY-036, 037) |
| Approve a bill with TDS proposed | **Cr TDS Payable** for the deduction; the supplier is owed the bill less TDS; Accounts > All Accounts screens > Tax filing > TDS Challans can take the bill (TC-BUY-043) |
| Approve a bill with TCS | **Dr TCS Receivable** (1430); the bill owes total plus TCS; Reports > Financial > TCS paid to suppliers (TC-BUY-050) |
| Raise orders from an RFQ | One **draft** order per chosen supplier on Purchase Orders; the RFQ Closed; a source requisition reads Ordered (TC-BUY-057, 058) |
| Approve an order priced from a rate contract | The contract's drawn goes up and remaining down; cancelling the order gives it back (TC-BUY-061) |
| Complete a receipt with serials | Stock > All Stock screens > Tracking > Serial Numbers: one unit per serial, in the receipt's warehouse, its trail starting at the receipt (TC-BUY-063) |
| Complete the receipt of a foreign-currency order; approve its bill; pay it | Stock in rupees at the order's rate; the bill's journal in rupees at the bill's rate, a rate difference in Purchase Price Variance; on payment **Exchange Gain/Loss** (4950) for the difference; the GST purchase register shows the bill in rupees (TC-BUY-070, 071, 087, 089) |
| Post a Bill of Entry | Duty and surcharge added to the stock value of the linked receipts; **Dr Input IGST / Cr Customs Duty Payable** (2800); GSTR-3B 4(A)(1) (TC-BUY-074) |
| Complete a receipt with a capital-goods line; approve its bill | The receipt moves no stock and posts nothing; then an asset in the Asset register; **Dr Fixed Assets** (1500), no stock; GST purchase register shows the capital goods tax apart (TC-BUY-077) |
| Depreciation run; disposal | **Dr Depreciation (6950) / Cr Accumulated Depreciation (1590)**; on disposal the gain or loss on 4960 (TC-BUY-079, 080) |

### Permissions to check
**Purchase Manager** approves; **Purchasing** (executive) raises but does not approve; **Warehouse** receives goods but not pays or approves orders (confirm); **Accounts** pays; Cashier records payments only. Payment runs: approval is separate from raising (cashier cannot approve). Over-tolerance and over-budget approval need their own permissions. **Added 2026-10-05 (confirm):** *Paid now* shows only to a user who may record payments (TC-BUY-039); RFQs, rate contracts, supplier schemes and bills of entry each have a view and a manage permission of their own, held by Purchasing and Purchase Manager (TC-BUY-059, 069); approving a rate contract and posting a Bill of Entry need the right to approve purchases; fixed assets have their own view and manage permissions, held by Accounts, and a run, cancelling one and a disposal also need the right to post journals (TC-BUY-081). `docs/qa/01_ROLES_AND_ACCESS.md` lists which job is offered each screen.

### Known limits
- Rule 43, a bank's own payment-run file layout and the 26Q file are not built (the generic NEFT file is).
- Direct supplier e-invoice portal checks are warnings only; they never refuse a bill.
- QA-BUY-13 refusal wording and QA-BUY-20 role screens are marked (confirm).
- Cheque and label alignment needs a real printer.
- **From the 2026-10-05 build, not built:** reading a bill into a draft (OCR); emailing an RFQ; a PDF on the WhatsApp order; the Bill of Entry in the GST purchase register and against GSTR-2B; returns and debit notes in another currency; tax withheld on a payment abroad (section 195); turning stock into an asset; GST on the sale of an asset.
- **Fixed on 2026-10-05 (#1175), not yet re-checked by hand:** D-BUY-35 the registers and GSTR-3B's input side show a foreign bill in rupees at the bill's rate; D-BUY-36 the payment dialog's TDS hint follows the amount; D-BUY-37 the Approve dialog's TDS proposal includes additional charges; D-BUY-38 the 194C/194J card names each rate and refuses a blank, zero or above-30 rate; D-BUY-39 an import runs through order, receipt and bill, and a bill in another currency than its order is refused; D-BUY-40 a line marked capital goods on the order or the receipt is received without entering stock.
- **Fixed on 2026-10-05 from reading that code** (`docs/DEFECTS.md`, #1177; unit-tested, not yet driven by hand): **D-BUY-41** a debit note or a purchase return against a foreign-currency bill posts rupees at the bill's rate, and capital goods are refused as a purchase return; **D-CMP-23** GSTR-2B matching, rule 37 and rule 42 read a foreign-currency bill in rupees; **D-BUY-42** the bill editor starts in its order's currency and rate; **D-BUY-43** a supplier rebate counts a foreign bill in rupees. TC-BUY-091 and 092 cover the first.

---

## 6. Inventory

### What it is for
Seeing stock (summary, ledger, batches, expiry) and the movements a firm makes
about its own stock: opening stock, transfers, counts, write-offs, repacking,
kits and approvals.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Business profile with batch and expiry | FRM-05 | Food Distribution | INV-04, 05 |
| Warehouses MAIN and STORE2 | FRM-08, 12 | -- | INV-06, 07 |
| Product tracking: Track batch, Track expiry, issue rule | On the product | Off; *Earliest expiry* | INV-01, 04 (QB-GHEE) |
| Inventory Settings (auto-post opening stock, export format) | Settings > Stock > Inventory Settings | Per person, this PC only | INV-01 |
| Adjustment Reasons | Settings > Stock > Adjustment Reasons | Eight standard reasons | INV-10 |
| Adjustment Limits | Settings > Stock > Adjustment Limits | No limits | INV-13 (set Warehouse 500, then clear) |
| Batch Rules | Settings > Stock > Batch Rules | Near expiry 30; hold returns in quarantine **Off** | INV-05; SELL-20..23 |
| Control Accounts (Inventory, Inventory Adjustment) | Settings > Set up > Account structure | Mapped | INV-09, 10 |
| Sales Stages: release stock held by unshipped orders after n days | Settings > Selling > Sales Stages | Never | TC-STOCK-018 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Stock Summary | Stock > Stock Summary | Quantities and value; no negatives |
| Stock Ledger | Stock > Stock Ledger | Every movement with its document; running balance |
| Stock Transfers | Stock > Stock Transfers | Dispatch, in transit, Receive, challan |
| Physical Count | Stock > Physical Count | Open Count, counted lines, Post count; count plans |
| Batches | Stock > Batches | Quantity and expiry per batch; reserved |
| Expiry Monitor | Stock > Expiry Monitor | Expire in 30 days, expired |
| Inventory | Stock > All Stock screens > Stock > Inventory | On hand, reserved, available, in transit; Write off, Adjust, Transfer, Quarantine |
| Stock Search, Transactions | Stock > All Stock screens > Stock | Where a product is held; every movement |
| Opening Stock | Stock > All Stock screens > Movements > Opening Stock | New, Post |
| Adjustment Approvals | Stock > All Stock screens > Movements | Submitted requests; Reject needs a reason |
| Repacking | Stock > All Stock screens > Movements > Repacking | Cost carries from the input |
| Lots, Serial Numbers | Stock > All Stock screens > Tracking | Where the profile tracks them |
| Import, Export | Stock > All Stock screens > Data | Checked before posting |
| Stock valuation report | Reports > Operational (confirm: the features guide lists it with Statements) | Agrees with Inventory on the trial balance |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Opening stock posted | QA-INV-01; TC-STOCK-001 |
| Summary and ledger agree; batches and expiry monitor | QA-INV-02..05; TC-STOCK-001, TC-STOCK-005 |
| Transfer dispatch and receive; nothing posted; refused when short | QA-INV-06..08; TC-STOCK-002, TC-STOCK-009 |
| Physical count posts only what was counted | QA-INV-09; TC-STOCK-004 |
| Write-off with reason | QA-INV-10; TC-STOCK-003, TC-STOCK-010 |
| Repacking; kit assembly | QA-INV-11, 12; TC-STOCK-011, TC-STOCK-012 |
| Large adjustment needs approval | QA-INV-13; TC-STOCK-016 |
| End-of-module figures; valuation report | QA-INV-14, 15 |
| More (not in the book): short delivery will not dispatch, serial warranty, expiry rules and issue rule, count plans, evidence files, incoming/outgoing/projected, quarantine on returns, stock alerts, labels | TC-STOCK-006..008, TC-STOCK-013..015, TC-STOCK-017..020 |

### Verify elsewhere
| After this action | Check |
| --- | --- |
| Opening stock posted | Stock Summary; journal **Dr Inventory / Cr Opening Balance Equity** (INV-01) |
| Transfer dispatched / received | Source drops, in transit then destination; **no journal** (INV-06, 07) |
| Count posted | Stock Ledger ADJUSTMENT; **Dr Inventory Adjustment / Cr Inventory**; uncounted lines move nothing (INV-09) |
| Write-off | Stock Ledger WRITE_OFF; **Dr Inventory Adjustment / Cr Inventory** (INV-10); reason account for Internal use, Staff, Display |
| Repacking | Output at the cost consumed; no journal without wastage (INV-11) |
| Kit assembled | Components down, kit up at 80 + 40 cost (INV-12) |
| Adjustment refused over limit | Offers Submit for approval; stock unchanged until approved (INV-13) |
| End | Stock value agrees with the Inventory account on the trial balance (QA-FIN-11, REP-04) |

Stock after each module: see the "Where the stock should stand" table in the
test book.

### Permissions to check
**Warehouse** (inventory manager) runs stock and batches and nothing else; **Accounts** and **Read Only** view; large adjustments by anyone above their role limit go to approval. Adjustment Limits need `INVENTORY_MANAGE_SETTINGS`; Adjustment Reasons `INVENTORY_MANAGE_REASONS`.

### Known limits
- A kit inside a kit and kit components priced on the bill are not done.
- Barcode labels need a real printer to judge alignment.
- QA-INV-08 refusal wording, QA-INV-12 button position (Assemble), QA-INV-14 total value 37,040.00 and QA-INV-15 are marked (confirm).
- Inventory Settings is per person on this PC, not a firm setting.

---

## 7. Selling

### What it is for
Enquiry, quotation, order, delivery note, invoice, receipt, returns, credit and
debit notes, proforma, the counter bill, holds, batches, and customer statements.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Sales Stages (quotation, order, delivery note on; offers combine; rate includes GST off; new outlets wait for approval off; release held stock never) | Settings > Selling > Sales Stages | All on | Whole module; SELL-08 (delivery note typed) |
| Credit Control | Settings > Selling > Credit Control | **Warn** at 80, block at 100; limit 0 = no limit | SELL-07, 24, 25 |
| GST Documents: dispatch of a sale before its invoice | Settings > Tax > GST Documents | **Warn** | SELL-08 (offers Dispatch and invoice / Dispatch anyway) |
| Batch Rules | Settings > Stock > Batch Rules | Near expiry 30, Warn, Record | SELL-20..23 |
| Price Floor | Settings > Selling > Price Floor | **Warn**, cost counts | TC-SELL-* price lines |
| Discount Limits | Settings > Selling > Discount Limits | No limits | Hand-typed discounts only |
| Approval Levels | Settings > Firm > Approval Levels | None | QA-APR-01..06 |
| Print settings (title, UPI ID, copies, page size) | **Print** button on an invoice | TAX INVOICE, A4, one copy | SELL-10, 12 |
| Numbering Series (SO, SI, PF ...) | Settings > Firm > Numbering Series | As set up | Each document |
| My Preferences: Date format | User menu | dd-MM-yyyy | SELL-35 |
| Customer record: terms, credit limit, GST registration | Masters > Customers | See MST | Place of supply and tax split |
| Sales Stages: *Sales order* and *Delivery note* **off**, so New Invoice opens the counter bill | Settings > Selling > Sales Stages | On | TC-SELL-040..045, 064..072. Switch both back on afterwards |
| The masters the new cases share (`QA-CTR`, `QA-SVC`, `QA-C03`) | Head of the SG block in `docs/qa/08_SELLING.md` | -- | TC-SELL-036..086 |
| Transporters | Settings > Set up > Territories & routes > Transporters | None | TC-SELL-055..059 |
| Customer: **Collector** | Masters > Customers | Blank: the account manager collects | TC-SELL-073 |
| Control accounts *Other Charges Recovered* (4050) and *Cash Short and Over* (6960) | Settings > Set up > Account structure > Control Accounts | Seeded | TC-SELL-050, 069 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Enquiries | Sell > All Sell screens > Documents > Enquiries | ENQ-, follow-ups due, Convert to quotation, Lost reason |
| Quotations | Sell > Quotations | Totals, place of supply, in words; convert once |
| Sales Orders | Sell > Sales Orders | Approve reserves stock; Hold/Release; credit warning |
| Delivery Notes | Sell > Delivery Notes | Dispatch; Dispatch and invoice; batch picker; pick list, loading sheet |
| Sales Invoices | Sell > Sales Invoices | + New (from delivery notes), + New by product (counter bill), Save & print (F9), draft banner |
| Returns & notes | Sell > Returns & notes | Sales Returns, Credit Notes, Customer Debit Notes (menu label reads "Debit Notes" in `menu_layout.dart`: confirm) |
| Receipts | Sell > Receipts | Apply to invoices; on account; no TCS |
| Customer Statements | Sell > Customer Statements | Ageing and statement; running balance in date order |
| Proforma, Approvals | Sell > All Sell screens > Documents | PF- series, "Not a tax invoice" |
| Post-dated Cheques, Refunds | Sell > All Sell screens > Money | See Finance |
| Sales Analysis | Sell > All Sell screens > Insight | See Reports |
| Counter bill | Sell > Sales Invoices > New (stages off) or + New by product | **Walk-in** and the buyer's name and phone; **Other charges** > Add charge; **Hold (F8)**, **Recall**; the shift strip (Open shift, Close shift) |
| Counter Shifts | Sell > All Sell screens > Documents > Counter Shifts | Status and date filters, View, Print report |
| Customer Rebates | Sell > All Sell screens > Documents > Customer Rebates | Agreement with slabs for a customer or a group; statement; accrue, reverse, cancel, settle against bills |
| Collection Sheet, Payment Promises | Sell > All Sell screens > Money | Open bills by collector with days overdue and the latest promise; the PDF; a promise's status |
| Transporters | Settings > Set up > Territories & routes > Transporters | Name, GSTIN or TRANSIN, phone, mode, active |
| Delivery note window | Sell > Delivery Notes | **Carrier (master)**, **Freight** |
| Attachments | Quotations, Sales Orders, Delivery Notes, Sales Invoices, Sales Returns lists | The **Attachments** action and the **Files** column |
| GST sales register, HSN summary of sales, Customer rebate statement | Reports > Financial | By tax head; by HSN and rate |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Enquiry to quotation to order; lost enquiry | QA-SELL-01..04; TC-SELL-028 |
| Quotation totals; convert once; nothing reserved | QA-SELL-05, 06; TC-SELL-005 |
| Approve order reserves stock | QA-SELL-07; TC-SELL-007 |
| Delivery note; dispatch warning (Dispatch anyway) | QA-SELL-08; TC-SELL-018, TC-SELL-009, TC-SELL-010 |
| Invoice from notes: cap on quantity; draft banner; approve; print | QA-SELL-09..12; TC-SELL-011, TC-SELL-012 |
| Receipt; invoice with money applied cannot be cancelled | QA-SELL-13, 14; TC-SELL-013, TC-SELL-014, TC-COMP-002 |
| Inter-state sale; Dispatch and invoice | QA-SELL-15, 16 |
| Customer debit note | QA-SELL-17; TC-SELL-020 |
| Counter bill and tender | QA-SELL-18, 19; TC-SELL-029 |
| Batches: earliest expiry reserved; hold; release; dispatch and invoice | QA-SELL-20..23; TC-SELL-008, TC-SELL-019, TC-STOCK-005 |
| Credit limit warns; blocks when asked | QA-SELL-24, 25; TC-CUST-004, TC-FIN-008, TC-CUST-003 |
| Dispatch refused when short | QA-SELL-26; TC-STOCK-006 |
| Sales return capped; credit | QA-SELL-27, 28; TC-SELL-015 |
| Credit note capped at the line | QA-SELL-29, 30; TC-SELL-016 |
| Proforma posts nothing | QA-SELL-31; TC-SELL-017 |
| Statement and ageing | QA-SELL-32; TC-CUST-005 |
| Delete guards; date format; end-of-module stock | QA-SELL-33..36 |
| **Added 2026-10-05, none run by hand yet (confirm):** | |
| GST sales register and HSN summary; minus and plus rows; who may open them | QA-SELL-37; TC-SELL-036..039 |
| Walk-in bill: paid in full or refused; two tenders; buyer's name only on a walk-in; the Cash sale customer's guards; no loyalty, B2C | QA-SELL-38; TC-SELL-040..045 |
| A service moves no stock and posts no cost; goods and service together; on a typed order and note; returned | QA-SELL-39; TC-SELL-046..049 |
| A charge taxed at its own rate; with no tax; replaced on a draft; on the print and in the register; what it does not do | QA-SELL-40; TC-SELL-050..054 |
| Transporter kept once by name; fills the note; the note wins; inactive refused; who keeps them | QA-SELL-41; TC-SELL-055..059 |
| Files on the five documents; type and size; delete and who may add | QA-SELL-42; TC-SELL-060..063 |
| Hold and recall; a held bill never approved; only a draft held | QA-SELL-43; TC-SELL-064..066 |
| Shift: open, one per cashier, expected cash, short, over and exact, who may close, optional | QA-SELL-43; TC-SELL-067..072 |
| Collection sheet by collector; promise posts nothing; kept, un-kept, due today, broken; refusals; withdrawn; who may | QA-SELL-44; TC-SELL-073..079 |
| Customer rebate: slab on the whole turnover; accrued once after the period; settle; reverse; overlap; group; who may | QA-SELL-45; TC-SELL-080..086 |
| More (not in the book): rate includes GST, minimum shelf life, pinning a batch, batch MRP, several notes on one bill, picking list, cash discount and interest, new outlet approval, price levels, UPI QR, reminders | TC-SELL-021..027, TC-SELL-030..035 |

### Verify elsewhere
Order of effect (`docs/SALES_CHAIN_RULES.md`, `docs/SALES_TO_RECEIPT_FLOW.md`):

| After this action | Check |
| --- | --- |
| Quotation / proforma | **Nothing**: no stock, balance or journal (SELL-06, 31) |
| Approve order | Inventory: reserved up, available down; **no journal** (SELL-07) |
| Dispatch delivery note | Stock down (DISPATCH), reserved 0; **Dr Cost of Goods Sold / Cr Inventory** at cost; audit trail keeps any warning (SELL-08) |
| Approve invoice | **Dr Trade Receivables / Cr Sales, Cr Output CGST+SGST (or IGST)**; customer outstanding; Home RECENT INVOICES; GSTR-1 B2B/B2CS (SELL-11) |
| Receipt | **Dr Bank (or Cash) / Cr Trade Receivables**; outstanding down (SELL-13) |
| Sales return completed | Stock back (SALES_RETURN); **Dr Sales Returns, Dr Output tax / Cr Trade Receivables** plus **Dr Inventory / Cr Cost of Goods Sold** (SELL-28) |
| Credit note | **Dr Sales Returns, Dr Output tax / Cr Trade Receivables**; no stock (SELL-29) |
| Debit note | **Dr Trade Receivables / Cr Sales, Cr Output tax**; owed on the same invoice (SELL-17) |
| Every document | Numbering series (SO-, DN-, SI-, RC-, PF-); audit trail; GSTR-1 sections B2B, B2CS, CDNR (GST module) |
| Approve a walk-in bill | A receipt for the full amount; no loyalty points; GSTR-1 as B2C (TC-SELL-040, 045) |
| Approve a bill of a service | **No** stock movement and **no** cost of goods sold journal (TC-SELL-046) |
| Approve a bill with a charge | **Cr Other Charges Recovered** (4050) for the charge, apart from Sales; its tax with the output tax; the GST sales register and HSN summary carry it under its SAC (TC-SELL-050, 053) |
| Hold a bill | Nothing: no stock, no journal; the list marks it held (TC-SELL-064) |
| Close a shift short or over | One journal between cash and **Cash Short and Over** (6960) for the difference; an exact count posts nothing (TC-SELL-069, 070) |
| Record or withdraw a promise | **No journal**; Payment Promises shows the status; a receipt in the window turns it *kept*, reversing it un-keeps it (TC-SELL-074, 075) |
| Accrue a customer rebate | **Dr Rebates Allowed (5310) / Cr Customer Rebates Payable (2900)**, dated the period's last day (TC-SELL-081) |
| Settle a rebate | A party adjustment of kind *Customer rebate* under Accounts > All Accounts screens > Books > Party Adjustments; the customer owes less (TC-SELL-082) |

### Permissions to check
**Field Sales** raises quotations, orders and invoices but cannot approve, cancel or change masters; **Counter Sales** bills and takes receipts; **Sales Manager** approves and works the sales desk but may not change Credit Control, Sales Stages or commission payment; **Customer Support** and **Read Only** do not create documents. Price floor override needs `SALES_PRICE_OVERRIDE` (not Sales Manager by default).

### Known limits
- The **Quotation stage** switch changes nothing in 1.3.0.
- Automatic WhatsApp and SMS sends are not built (sharing by hand is); email needs the firm's Messaging switched on, which is off by default.
- Payment links are not built.
- **From the 2026-10-05 build, not built:** charges carried from the sales order, and crediting a charge; changing the carrier of a note already raised; a promise for the account as a whole from the screen, the promise on the customer statement, a reminder from a broken promise; a counter refund against a bill, a count by denomination, handing a shift over; a rebate settled by a GST credit note or paid out in money.
- **Fixed on 2026-10-05 (#1174), not yet re-checked by hand:** **D-SELL-51** a bill paid at the counter is counted in the open shift of the cashier who made it, and in its approver's only when the maker has none open (TC-SELL-068, 087); **D-SELL-52** *Settle against bills* on Customer Rebates is shown only to a user who may manage party adjustments, so a Sales Manager is not offered it (TC-SELL-086).
- Several book cases carry (confirm): SELL-11 per-head output tax legs, SELL-19 cash leg, SELL-26 whether approval warns, SELL-36 value 31,120.00.

---

## 8. Pricing & incentives

### What it is for
How a line's price and discount are decided (price lists, price levels,
promotions, coupons, customer standing and group discounts), loyalty points,
commission and targets.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Sales Stages: when several offers match; most offers may take off one line | Settings > Selling > Sales Stages | **Combine offers**; no cap | PRC-13 (promotion beats the list) |
| Loyalty Scheme | Settings > Selling > Loyalty Scheme | **Off** (running, 1 per 100, worth 1, minimum 50 in the book) | PRC-21..23 |
| Price List `QB-STD` | Settings > Set up > Pricing > Price Lists | None | PRC-08..10 |
| Promotions `QB-BULK`, `QB-WELCOME` and coupon `QBW1` | Settings > Set up > Pricing > Promotions | None | PRC-13..18 |
| Customer Group `RETAIL` | Settings > Set up > Party lists > Customer Groups | None | PRC-12 |
| Standing discount on Ravi Traders | Masters > Customers > Money > Default discount % | 0 | PRC-11 |
| Commission rule (Arun, Money collected, 2%) | Sell > All Sell screens > Incentives > Commission | None | PRC-01..07 |
| Sales target | Sell > All Sell screens > Incentives > Targets | None | PRC-02, 07 |
| Price Levels | Settings > Set up > Pricing > Price Levels | None | TC-SELL-033 |
| Discount Limits | Settings > Selling > Discount Limits | No limits | Limits apply to **hand-typed** discounts only, never to a list, promotion or standing rate |
| Order of the run | Commission first, before any discount exists | -- | PRC-03 sale is at full price |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Commission | Sell > All Sell screens > Incentives > Commission | Rates, Collected, Payouts (Accrue, Approve, Pay) |
| Targets | Sell > All Sell screens > Incentives > Targets | Achievement view |
| Price Lists, Price Levels, Promotions, Loyalty | Settings > Set up > Pricing | Lists; revisions; Coupons view; Adjust points |
| Quotation / order editor | Sell > Quotations, Sales Orders | Side panel says where each discount came from ("2% from the price list"); read the figures before saving, then close without saving |
| Loyalty Scheme | Settings > Selling > Loyalty Scheme | Banner states the scheme |
| Promotion claims report | Reports > Operational > Promotion claims | CLAIMED rows |
| Customer Groups | Settings > Set up > Party lists | Remove refused while a customer is in it |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Commission rule, target, a collected sale, commission earned | QA-PRC-01..04; TC-INCENT-006 |
| Accrue, approve, pay; accruing again refused; achievement | QA-PRC-05..07; TC-INCENT-007, TC-INCENT-008, TC-CONC-006 |
| Price list, break at the quantity | QA-PRC-08..10; TC-SELL-001, TC-SELL-002, TC-INCENT-001 |
| Standing discount; group discount | QA-PRC-11, 12; TC-SELL-003 |
| Promotion beats list; typed 0 refuses; typed 12 overrides | QA-PRC-13..15; TC-SELL-004 |
| Edit makes a new revision | QA-PRC-16; TC-INCENT-002 |
| Coupon: blank, valid, unknown; claims counted at approval; last use | QA-PRC-17, 18; TC-SELL-006, TC-INCENT-003, TC-CONC-005 |
| Whole-order discount and delivery charge reach the tax | QA-PRC-19, 20 |
| Loyalty: earn, spend (settles, not discounts), over-spend refused | QA-PRC-21..23; TC-INCENT-005 |
| Switch offers off; back to full price | QA-PRC-24; TC-INCENT-004 |
| More (not in the book): buy X get Y and combo, bonus points and conditions, bulk coupons, principal claims, price levels | TC-INCENT-009..012, TC-SELL-033 |

### Verify elsewhere
- **Which discount wins**, strongest first: typed amount, typed percentage, promotion, price list, customer standing rate, customer group (`docs/PRICING_AND_PROMOTIONS.md`). A blank box takes the arrangement; a typed **0** refuses it.
- **Commission earned** (2% of the taxable 500.00 = 10.00, tax earns nothing); payout journals **Dr Commission Expense / Cr Commission Payable** at approval, **Dr Commission Payable / Cr Cash** at payment (PRC-05, confirm).
- **Loyalty:** earning posts **Dr Loyalty Expense / Cr Loyalty Payable** (cost when earned); using points posts **Dr Loyalty Payable / Cr Trade Receivables** and the invoice's total and tax are unchanged (PRC-21, 22).
- **Claims:** a coupon is claimed at order approval, not while pricing; Reports > Operational > Promotion claims shows CLAIMED (PRC-18).
- Audit trail records promotions and rule changes in the firm's trail (TC-AUDIT-004).

### Permissions to check
**Sales Manager** may view and work pricing but **cannot pay commission** (`COMMISSION_PAY` is separate from `COMMISSION_MANAGE`) and cannot change the loyalty or credit settings; **Field Sales** has no Commission, Price Lists or Promotions screens (QA-USR-05); the person who approves a payout and the person who pays can be kept apart.

### Known limits
- A promotion's identity is its version group; claims follow the offer, not the row (PRC-16).
- Principal claims, bulk coupons and buy-X-get-Y have detailed cases only in `docs/qa/09_PRICING_AND_INCENTIVES`.
- Whether tax is counted in target achievement (PRC-07), commission figures (PRC-04, 05) and loyalty expense journal (PRC-21) are marked (confirm).

---

## 9. Territory & field sales

### What it is for
The firm's territory map, routes with an ordered round of shops, salespeople on
routes, beat plans, call lists and coverage.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Customers Ravi Traders and Lakshmi Provisions; people Arun and Kiran | Masters; Users | -- | TER-03, 07, 08 |
| Territory records: region, territory, route type, route | Settings > Set up > Territories & routes > Territories, Route Types | None | TER-01, 02 |
| Route Builder: the round and its order | Settings > Set up > Territories & routes > Route Builder | -- | TER-03 |
| Salespeople on the route (Arun primary) | Open the route > Salespeople | None | TER-04, 07, 08 |
| Beat plan | Sell > All Sell screens > Field sales > Beat Plans | None | TER-05, 06 |
| A route's effective window | On the route | Judged on the document's own date | TC-TERR-003 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Territories | Settings > Set up > Territories & routes > Territories | Tree (Expand all): Chennai Region > Chennai North > Anna Nagar Beat |
| Route Types | same section | `SALES` Sales Route |
| Route Builder | same section | Add outlets, **Save round and order** |
| Beat Plans | Sell > All Sell screens > Field sales > Beat Plans | Weekly, Monday |
| Call Lists | Sell > All Sell screens > Field sales > Call Lists | Move to next Monday: *Runs on Monday*; another day: *Not on Tuesday* with the reason |
| Coverage | Sell > All Sell screens > Field sales > Coverage | Outlets visited or missed (confirm columns) |
| Sales order editor | Sell > Sales Orders | Salesman, territory, route fill |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Region, territory, route type, route; tree | QA-TER-01, 02; TC-TERR-001 |
| Round saved in order | QA-TER-03; TC-TERR-004 |
| Salesperson on the route | QA-TER-04; TC-TERR-005 |
| Beat plan and call list for a Monday; other days show reasons | QA-TER-05, 06; TC-TERR-002 |
| Salesman not on the route refused; blank salesman fills from the route | QA-TER-07, 08; TC-TERR-005 |
| Coverage | QA-TER-09 |
| Salesman sees his own plan | QA-TER-10 |
| More (not in the book): fortnightly and monthly plans, loading places from India Post | TC-TERR-003, TC-TERR-006 |

### Verify elsewhere
- **Orders, deliveries and invoices** carry the salesman, route and territory, so Sales Analysis and reports read by any of them (Reports module).
- **Refusal:** "The selected salesperson is not assigned to this territory." saves nothing (TER-07).
- **Commission** is paid to the salesman named on the document (PRC-03).
- Audit trail records territory and route changes. No ledger, stock or GST effect.

### Permissions to check
Territory set-up is a Settings > Set up screen offered to whoever may open it (Sales Manager, firm administrator). **Field Sales (Arun)** sees his own call list but not Territories set-up; Kiran, not on the route, cannot be named on a sale in the route's territory.

### Known limits
- **Coverage** columns are not confirmed in the book (TER-09, confirm).
- Phone layout of the new UI is parked; layouts are desktop layouts.
- The territory export carries customer codes so a round trip keeps the shops.

---

## 10. GST & compliance

### What it is for
GSTR-1 and GSTR-3B (derived from the documents on every read), e-invoice and
e-way bill (sandbox), TCS, TDS 194Q, GST checks, payment, calendar, GSTR-2B.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Firm GSTIN `33AAQCB1201B1ZH`; customer and supplier GSTINs | Firm; Masters | -- | Place of supply, B2B vs B2CS |
| GST template applied | FRM-07 | -- | Tax split |
| GST Documents: e-invoicing applies from | Settings > Tax > GST Documents | Not applicable | GST-09..13 (set to today, then clear) |
| GST Documents: e-invoice filing route | same | **Sandbox** | GST-07..11 |
| GST Documents: e-way bill needed above | same | Rs 50,000 | GST-12 |
| GST Documents: claim input credit; 2B tolerance; supplier bill without IRN; rule 37; rule 42; returns monthly/quarterly | same | All bills; Rs 1.00; Warn; Report only; Report only; Monthly | GST-06, 17, 20 |
| TCS Settings (206C(1H)) | Settings > Selling > TCS Settings | **Off** | GST-15 (switch on, then off) |
| TDS on Purchases (194Q) | Settings > Tax > TDS on Purchases (194Q) | **Off** | GST-16 uses the payment's TDS fields |
| Tax Configuration, Tax Rules | Settings > Tax | From the GST template | Rule choice per line |
| Branch GSTIN | Masters > Branches | None: firm's GSTIN | TC-COMP-025 |
| Every document in the same month | -- | -- | GST-01..06 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| GST Returns (GSTR-1, GSTR-3B) | Accounts > GST Returns | "Filing as 33AAQCB1201B1ZH"; sections B2B, B2CS, CDNR, HSN; 3B tables 3.1(a), 4; Mark filed |
| E-Invoice | Accounts > All Accounts screens > Tax filing > E-Invoice | Sandbox banner; To register list; IRN box on print |
| GST checks | Accounts > All Accounts screens > Tax filing > GST checks | Findings by code |
| Rule 37, Rule 42 | same group | Listed credits (nothing at 180 days in the book) |
| GST Payment, PMT-06 deposits | same group | Liability per head; read, do not record |
| GSTR-2B Reconciliation | same group | Matched, Different, Not in books |
| TCS | same group | Nothing collected |
| TDS Challans, Bank Details | same group | Challans due; masked numbers |
| Tax calendar | Home > TAX CALENDAR | GSTR-1 on the 11th, 3B on the 20th, finished months only |
| Print of an invoice | Sell > Sales Invoices > Print | IRN box or "NO IRN YET" banner; reference copy |
| TDS deducted, Customer/Supplier PAN check | Reports > Financial | 194Q row with PAN and section |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| GSTR-1: B2B, B2CS, CDNR, HSN | QA-GST-01..04; TC-COMP-001 |
| GSTR-3B agrees with GSTR-1; input credit | QA-GST-05, 06; TC-COMP-003 |
| E-invoice is a rehearsal; refused for no GSTIN | QA-GST-07, 08; TC-COMP-004, TC-COMP-005 |
| No IRN: print refused, reference copy; To register list; register; cancel refused after registration | QA-GST-09..11; TC-COMP-012, TC-COMP-016, TC-COMP-018, TC-COMP-011 |
| E-way bill: vehicle needed by road | QA-GST-12; TC-COMP-006, TC-COMP-010 |
| Clearing the date restores printing | QA-GST-13 |
| GST checks | QA-GST-14; TC-COMP-021 |
| TCS omitted from 1 April 2025: nothing charged | QA-GST-15; TC-COMP-007, TC-SELL-013 |
| TDS 194Q on a payment | QA-GST-16; TC-FIN-017 |
| Rule 37; GST payment; calendar; 2B | QA-GST-17..20; TC-COMP-013, TC-COMP-008, TC-BUY-014 |
| More (not in the book): offline e-invoice, supplier IRN, e-way on a receipt, 30-day limit, credit note on the portal, 30 November limits, filed return and amendments, quarterly filing, rule 42, branch GSTIN, rule on the line | TC-COMP-009, 014, 015, 017, 019, 020, 022..026 |

### Verify elsewhere
- **GSTR-1/3B are views:** derived on every read; a late credit note or cancelled invoice always shows; after **Mark filed**, later changes appear as amendments (TC-COMP-022).
- **3B table 3.1(a)** = taxable 7,900.00, IGST 378.00, CGST 242.50, SGST 242.50 in the book's month (GST-05, confirm netting); equals GSTR-1's sections added by hand.
- **Input credit (table 4):** agrees with Input IGST/CGST/SGST on the trial balance (QA-FIN-11).
- **TDS on payment:** **Dr Trade Payables / Cr Bank, Cr TDS Payable**; Reports > Financial > TDS deducted (GST-16).
- **TCS:** no charge on a receipt after 1 April 2025; **Dr Bank / Cr Trade Receivables** only (GST-15).
- **Sandbox references** are marked SBX; anything reading LIVE is a defect (GST-07).
- Audit trail records registration and e-way actions.

### Permissions to check
**Accounts** opens GST Returns, TCS and the filing screens; **Field Sales**, **Counter Sales** do not (GST Returns, TCS absent for Field Sales, QA-USR-05). TCS Settings need `TCS_MANAGE`; GST Documents and Tax Settings `TAX_MANAGE_SETTINGS`; TDS (194Q) `ACCOUNT_MANAGE`.

### Known limits
- **Live e-invoice and e-way bill through NIC or a GSP are not built**: sandbox and offline upload only.
- **The 26Q FVU file, rule 43** (capital goods) are not built.
- In GST checks, **Open document from a finding is not active yet**.
- **Section 206C(1H) was omitted from 1 April 2025**: the application collects nothing on a later receipt.
- Several figures are (confirm): rate-row layout (GST-01), HSN adjustments (GST-04), netting (GST-05), table 4 rows (GST-06), clean checks (GST-14), TCS wording (GST-15), GST payment figures (GST-18).

---

## 11. Finance

### What it is for
Opening balances, journals, expenses, contra vouchers, ledgers, the three
statements, bank reconciliation, post-dated cheques, month close, Tally export.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Books opened; control accounts mapped | FRM-06, 20 | -- | Every posting |
| Financial Years: month-close check; ageing columns | Settings > Firm > Financial Years | **Warn**; 30, 60, 90 | FIN-17 |
| Party Adjustments: second approver above; rounding limit | Accounts > All Accounts screens > Books > Party Adjustments > Adjustment limits | 1,000 / 10 | Receipts/payments rounding |
| Bank Details (print on documents) | Accounts > All Accounts screens > Tax filing > Bank Details | None | Printed bills |
| Tally mappings | Accounts > All Accounts screens > Books > Export to Tally | -- | FIN-19 |
| Control Accounts, Cost Centres, Profit Centres | Settings > Set up > Account structure | Mapped; none | FRM-20; TC-FIN-007 |
| Run order | Opening balances first so ledger figures include them | -- | FIN-11 onwards |
| Month for closing | A completed past month | -- | FIN-17 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Journal Entries | Accounts > Journal Entries | Filter *Posted by*; hand journal Post/Reverse; document journals have no Reverse |
| Expenses | Accounts > Expenses | Posts to the expense account |
| Ledgers | Accounts > Ledgers | Running balance, e.g. Trade Receivables |
| Bank Reconciliation | Accounts > Bank Reconciliation | Import, Auto-match, reconciliation statement |
| Trial Balance, Profit & Loss, Balance Sheet | Accounts daily drop-down | **Balanced** chips; figures per the book |
| Cash Flow | Accounts > All Accounts screens > Statements > Cash Flow | Operating, investing, financing; says it reconciles |
| Opening Balances | Accounts > All Accounts screens > Books | One journal OTB-; sub-ledger accounts refused |
| Contra Vouchers, Party Adjustments, Export to Tally | Accounts > All Accounts screens > Books | Contra series; XML by voucher type |
| Post-dated Cheques | Sell > All Sell screens > Money, Buy > All Buy screens > Money | Held, deposit refused early |
| Financial Years | Settings > Firm > Financial Years | Close, Open, checklist |
| Customer/Supplier statements, opening bills import | Sell > Customer Statements; Masters > Customers/Vendors | OBC- and OB- numbers |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Opening balances; sub-ledger account refused | QA-FIN-01, 02 |
| Import opening bills: check lists problems; import; vendor opening bill | QA-FIN-03..05 |
| Hand journal; unbalanced refused; expense; contra | QA-FIN-06..09; TC-FIN-004 |
| Journal filter by module | QA-FIN-10; TC-FIN-004 |
| Trial balance, P&L, balance sheet, cash flow | QA-FIN-11..14; TC-FIN-002, TC-FIN-018 |
| Ledger and statements agree | QA-FIN-15 |
| Bank reconciliation | QA-FIN-16; TC-FIN-012 |
| Close a month; closed period refuses posting | QA-FIN-17; TC-FIN-003, TC-FIN-016 |
| Post-dated cheques | QA-FIN-18; TC-FIN-013 |
| Tally export | QA-FIN-19; TC-FIN-020 |
| Role limits | QA-FIN-20; TC-CASH-001..004 |
| More (not in the book): new account, cost and profit centres, payment mode, bank details and cheque printing, TDS challans, files on journals | TC-FIN-001, 007, 014, 015, 017, 019 |

### Verify elsewhere
See `docs/LEDGER_POSTING_RULES.md`.

| After this action | Check |
| --- | --- |
| Opening balances | **Dr Bank, Dr Cash / Cr Opening Balance Equity** (FIN-01) |
| Opening bill import | Customer: **Dr Trade Receivables / Cr Opening Balance Equity**; vendor: **Dr Opening Balance Equity / Cr Trade Payables**; outstanding and payment lists show the opening bill (FIN-04, 05) |
| Hand journal | Ledger for each account; Bank falls (FIN-06) |
| Expense / contra | **Dr Electricity / Cr Cash**; **Dr Bank / Cr Cash** |
| Month closed | Posting dated in it refused; Open it again; Audit Logs shows closed and reopened (FIN-17) |
| Statements | Trial balance Balanced; balance sheet result for the year equals P&L year-to-date net (FIN-13) |
| Post-dated cheque held | **Nothing posted** (FIN-18) |
| Every figure | Customer Statements and Vendor outstanding agree with Trade Receivables and Trade Payables on the trial balance (FIN-15; REP-05, 06) |

### Permissions to check
**Accounts** sees Journal Entries, Expenses, Ledgers, Bank Reconciliation, statements, GST Returns (QA-USR-07); **Counter Sales** (Cashier) holds Receipts and Payments only (QA-FIN-20, QA-USR-04). Closing a month needs `FINANCIAL_YEAR_CLOSE`; reopening a year needs `FINANCIAL_YEAR_REOPEN` and a reason. Party adjustments above the limit need a second approver who did not draft.

### Known limits
- No closing entry is posted when a year closes; retained earnings stay derived.
- **26Q FVU**, a bank's own payment file, and live bank feeds are not built; cheque layouts need a real printer.
- Profit & Loss does not show gross profit above net profit.
- Many Trial Balance and Profit & Loss figures in the book (FIN-11, 12, 13) are marked (confirm) and depend on the whole run being completed in one month.

---

## 12. Reports

### What it is for
The operational and financial reports (more than fifty), plus the analysis
screens beside Sell and Buy, filtered, sorted and exported.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| All earlier modules run in the same month | -- | -- | REP-02..09 figures |
| Ageing columns | Settings > Firm > Financial Years | 30, 60, 90 | REP-05, 06, 07 |
| Reorder planning (typed levels / from sales) | Reports > Operational > Below reorder level | Typed levels | Below reorder level |
| Period filter on dated lists | On each report | This month | Every figure |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Operational | Reports > Operational | Sales invoice register, Purchase invoice register, Stock valuation (confirm), Overdue sales invoices, Orders not yet received, Purchase order register, Stock ageing, Promotion claims, Enquiries lost |
| Financial | Reports > Financial | Customer outstanding, Vendor outstanding, Customer PAN check, TDS deducted, purchase price variance |
| Sales Analysis | Sell > All Sell screens > Insight > Sales Analysis | By product/month etc.; returns netted (confirm) |
| Purchase Analysis | Buy > All Buy screens > Insight > Purchase Analysis | Quantity and average rate |
| Export | Any report > Export | File holds the grid's rows |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Every report opens with a row count or "Nothing to report" | QA-REP-01; TC-FIN-005 |
| Sales and purchase registers | QA-REP-02, 03; TC-BUY-007 |
| Stock valuation = Inventory on the trial balance | QA-REP-04; QA-INV-15 |
| Customer and vendor outstanding agree with statements | QA-REP-05, 06 |
| Overdue, orders not received, stock ageing, PAN check | QA-REP-07, 10..12; TC-MAST-016 |
| Sales and purchase analysis | QA-REP-08, 09; TC-FIN-023 |
| Export | QA-REP-13; TC-MAST-007 |
| At volume (nightly retention, search) | TC-FIN-024 |

### Verify elsewhere
- **Register totals** equal the invoices: five sales invoices 8,986.00; three purchase invoices 21,200.00 (REP-02, 03). Opening bills are not purchases.
- **Customer outstanding** (Ravi 2,709.00, Lakshmi 2,000.00) equals Customer Statements and the Trade Receivables ledger (FIN-15).
- **Vendor outstanding** (Deccan 4,360.00) equals Supplier Statements.
- **Stock valuation** (30,720.00) equals Stock Summary and Inventory on the trial balance.
- A slow report (over 3 seconds) is noted, not failed (REP-01).

### Permissions to check
Reports are offered by the role's view codes: **Read Only** (Viewer) sees everything but changes nothing; **Accounts** sees financial reports; what **Customer Support** and **Counter Sales** are offered under Reports is not stated in the sources (confirm). Cost and margin columns in Sales Analysis only for those who may see cost.

### Known limits
- Returns netting in Sales Analysis (REP-08) and the stock valuation's Inventory row (INV-15) are marked (confirm).
- Purchase Analytics under the Buy menu is a placeholder and is not offered.
- Saved layouts and report catalogue entries differ by firm and role; Reports has no short form.

---

## 13. Approvals & notifications

### What it is for
Approval levels by amount, sign-off and rejection, the bell, Home's To do,
bulk approval, and messaging (which is off by default).

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Approval Levels (document, level 1-3, from amount, role) | Settings > Firm > Approval Levels | None: one approval is enough | APR-01 (sales order, level 1 from 5,000, Firm Administrator) |
| Approval Limits (purchase orders) | Settings > Buying > Approval Limits | No limits | TC-BUY-001 |
| Adjustment Limits | Settings > Stock > Adjustment Limits | No limits | INV-13 |
| Messaging | Settings > Firm > Messaging | **Off** (nothing queued or sent) | APR-10 |
| Priya and Arun exist | USR-02 | -- | APR-02..06 |
| Clean-up at the end | Delete the approval rule | -- | APR-11 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Approval Levels | Settings > Firm > Approval Levels | Rule list |
| Approvals (sales) | Sell > All Sell screens > Documents > Approvals | Sign off, Reject (reason) |
| Approvals (purchase) | Buy > All Buy screens > Documents > Approvals | Same |
| The bell | Menu bar | *Documents awaiting the next sign-off*, orders to approve, adjustments waiting, failed messages, stock alerts; counted |
| Home > TO DO | Home | Each to-do opens a list with the number of rows it said |
| Sales Orders list | Sell > Sales Orders | Tick rows > **Approve selected** (each on its own) |
| Messaging | Settings > Firm > Messaging | Four tabs: switch and schedule, channels, events, message log |
| Audit Logs | Settings > Platform > System > Audit Logs | Sign-off, rejection |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Rule set; below the amount approves at once; above is refused naming the level and role | QA-APR-01..03; TC-FIN-021 |
| The bell counts; Priya's bell does not offer it | QA-APR-04; TC-FIN-022 |
| Sign off approves; reject needs a reason | QA-APR-05, 06; TC-FIN-021 |
| Purchase order awaiting approval appears in the bell | QA-APR-07 |
| Bulk approve: per row, with reasons for refusals | QA-APR-08 |
| To do opens the same number of rows | QA-APR-09 |
| Messaging off by default | QA-APR-10; `docs/MESSAGING_SETUP_GUIDE.md` |
| Two approvals of one order | TC-CONC-004 |

### Verify elsewhere
- **Sign-off:** the order becomes Approved (stock reserved, as in SELL-07); the bell count drops; Audit Logs records the sign-off (APR-05).
- **Refusal:** the order stays Draft; no reservation.
- **Rejection:** reason kept, earlier sign-offs cleared; a purchase order returns to draft.
- **Messaging off:** nothing queued or sent; the message log is empty (APR-10). A failed message never stops a document.
- Cleanup returns reservations to zero (APR-11).

### Permissions to check
Platform administrators are not limited by levels. **One person cannot sign two levels** of one document. **Priya (Sales Manager)** cannot sign a level held by Firm Administrator. Changing sales levels needs `SALES_MANAGE_SETTINGS`, purchase levels `PURCHASE_MANAGE_SETTINGS`; Messaging needs `SETTINGS_UPDATE`.

### Known limits
- **Real WhatsApp and SMS sends are not built** (sharing by hand is); email needs the firm's own account and switch.
- The Home gadget for enquiries is not built.
- If the total rises after a signature, that level has to be signed again (by design).
- Messaging sends and rule outcomes beyond the book are in `docs/qa/12_FINANCE_AND_REPORTS` and `docs/MESSAGING_FRAMEWORK.md`.

---

## 14. Platform administration

### What it is for
What only the platform tier does: firms, users across firms, audit trails, backups,
diagnostics, the platform dashboard and firm isolation.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Sign in as the platform administrator (not admin@qb01.test) | -- | -- | Every case unless named |
| A second firm on the server (optional) | Settings > Platform > Firms | -- | PLT-09 (isolation) |
| Backups run nightly 02:00 on the server, newest seven kept | Server, not a setting | -- | PLT-04 |
| Retention clean-up after the nightly backup | Server switch `AGENCY_RETENTION_AUTO_PURGE` | On | No screen |
| Licensing | Settings > Platform > System > Licensing | Placeholder | Not in use |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Settings, PLATFORM part | Gear | People, Firms, Agency (Branding), System |
| Firms | Settings > Platform > Firms > Firms | Set up panel verdict; Delete refused for an assigned firm |
| Business Profiles | Settings > Platform > Firms > Business Profiles | What each profile switches on |
| Audit Logs | Settings > Platform > System > Audit Logs | Platform trail (no firm) vs firm trail (firm chosen); search box |
| Diagnostics | Settings > Platform > System > Diagnostics | Error reports by group |
| Backups | Settings > Platform > System > Backups | **Back up now**; time, size, who |
| Platform Dashboard | Settings > Platform > System > Platform Dashboard | Counts of firms, users, roles |
| Firm switcher | Right of the menu bar | Lists every firm for the platform administrator |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Settings offers the platform sections | QA-PLT-01; TC-PLAT-001..003, TC-PLAT-005 |
| Firm finished; assigned firm cannot be deleted | QA-PLT-02, 03; TC-FIRM-014, TC-FIRM-017 |
| Back up now | QA-PLT-04 |
| Platform trail, firm trail, search | QA-PLT-05, 06; TC-AUDIT-001..005 |
| Diagnostics, dashboard; hidden from a firm administrator | QA-PLT-07, 08; TC-FIN-011 |
| Firm isolation | QA-PLT-09; TC-ISO-001..004 |
| Firm administrator sees no Firms or Business Profiles | QA-PLT-10; TC-FIRM-016 |
| Two windows editing one record: second refused, nothing lost | QA-PLT-11; TC-CONC-001..003 |
| Platform operator vs firm books | TC-TIER-001..003 |

### Verify elsewhere
- **Audit trail** is per store: platform administration writes to the platform trail; a firm's mutations write to that firm's own trail; with a firm chosen you see that firm's, newest first (PLT-05, 06).
- **Backups:** the installation guide names where the files are kept on the server PC (PLT-04).
- **Isolation:** another firm never shows QB01's customers; switching back reloads cleanly (PLT-09).
- **Concurrency:** the second save keeps what was typed and says somebody else saved (PLT-11).

### Permissions to check
The platform tier holds **Firms, Business Profiles, Diagnostics, Backups (`SYSTEM_BACKUP`), Platform Dashboard, Licensing, Branding (`PLATFORM_SETTINGS`)**. admin@qb01.test (firm administrator) sees only People in the PLATFORM part and no Firms, Business Profiles or Diagnostics (PLT-07, 10). A platform operator is refused the firms' books even where a member (TC-TIER-002).

### Known limits
- **Licensing** is a placeholder; licensing is not in use in 1.3.0.
- The installer itself is tested apart: `docs/INSTALLER_QA_CHECKLIST.md`.
- Restoring a backup is described in the installation guide, not driven from a screen.

---

## 15. Agency branding

### What it is for
The agency's own name, tagline and logo on the sign-in screen, the header and the
window title, with Agency Platform's own name shown quietly beside them.

### Configure first
| Setting | Path | Default | Matters for |
| --- | --- | --- | --- |
| Spare PC for a fresh server install | `AgencyPlatform-1.3.0-Setup.exe`, **This PC: server and app** | -- | BRD-01..05 (run first or last) |
| Installer Branding page (name, tagline, logo; all optional) | Setup, page after *This PC* | Blank; a tagline or logo without a name refused | BRD-01..04 |
| Server whose branding is **not set** | A fresh install with no name | Not set | BRD-11, 12, 14 (run before BRD-13) |
| Branding form: Agency name (required, 150), Tagline (200), Logo (PNG or JPG, 1 MB) | Settings > Platform > Agency > Branding | Not set: Agency Platform's own name shows | BRD-13, 15..18 |
| Accent colour | -- | Stored, never asked or applied | No box on the form |
| Permission | `PLATFORM_SETTINGS` | Platform administrator only | BRD-14, 19 |

### Screens to open
| Screen | Menu path | What to look at |
| --- | --- | --- |
| Installer Branding page | Setup, fresh server install only | Three boxes and a read-only product line; absent on repair, upgrade, app-only |
| Sign-in screen | Open the app | Logo or initials, name, tagline; night-blue strengths panel cycling about every 8 seconds, stops once you type; narrow below 900 px |
| More help | Sign-in > More help | No support rows (blank by design); Copy details for support |
| Set up your agency dialog | First sign-in as platform administrator, branding not set | Name, tagline, logo, live preview, Skip for now, Save; Home *Finish setting up* card |
| Branding | Settings > Platform > Agency > Branding | Name starred, preview of sign-in and header, read-only product block, Remove logo |
| Header strip and title bar | Left of the menu bar; Windows title | Agency before Home, then firm; title *agency > firm*; below 820 px logo only; tagline from 1280 px |
| Status line | Foot of the window | Server state, 1.3.0, *Powered by Agency Platform*; product mark at the right (clicking does nothing) |
| Audit Logs (no firm) | Settings > Platform > System > Audit Logs | `agency_branding.created`, `.updated`, `.logo_changed` |

### What to test
| Flow / edge case | Cases |
| --- | --- |
| Installer Branding page; blank install; name only | QA-BRD-01, 02 |
| Refusals on Next; refused logo never fails the install; repair/app-only skip the page | QA-BRD-03..05 |
| Sign-in: cycling, narrow window, product mark and status line, More help, offline fallback | QA-BRD-06..10; TC-ME-014, TC-ME-015 |
| First sign-in dialog, Skip, Home card; firm administrator sees none | QA-BRD-11..14; TC-ME-016 |
| Branding form: change, logo rules, two people at once, no access for firm administrator | QA-BRD-15..19; TC-ME-017 |
| Header: logo, name, tagline, title bar, narrow window, click goes Home, status line | QA-BRD-20..24; TC-ME-018 |
| Installer rows | `docs/INSTALLER_QA_CHECKLIST.md` (A4a, section F) |

### Verify elsewhere
- **Audit trail** (platform trail, no firm): created, updated, logo_changed (type and size, never the image), each naming the platform administrator (BRD-02, 13, 16).
- **Other PCs** see the new branding at their next sign-in screen (BRD-16); the sign-in screen opens at once from the PC's last-seen branding when the server is stopped (BRD-10).
- **Install log:** `C:\ProgramData\Agency Platform\logs\install` holds a warning when a logo was refused (BRD-04).
- **Header:** menu strip height unchanged; title bar *agency alone* when no firm chosen (BRD-20, 21).

### Permissions to check
Only a holder of `PLATFORM_SETTINGS` (the platform administrator) sees the dialog, the card and **Settings > Platform > Agency > Branding**. A firm administrator sees none of them, and Ctrl+K `Branding` does not offer the screen (BRD-14, 19). **Reading** the branding needs no sign-in (the sign-in screen shows it).

### Known limits
- **Help > About is not built**: clicking the product on the status line does nothing.
- **First-run is step 1 only** (Set up your agency); later steps and a header prompt are not built; the Home card stands in.
- **Support details are blank by design**: no phone, WhatsApp, hours, email or website shows on the sign-in screen.
- The accent colour is stored but not asked or applied; the product logo on the status line is a placeholder icon; a logo's shape is not checked (screens fit it into a square).
- The "PRACTICE" mark is not built. The branding is **empty after an upgrade**.

---

## Cross-module checks

Run these after the modules above, in the sample firm. Each points to cases that
already hold the figures; the aim is to see **one document change every place it
should**.

### One sale, end to end (order, dispatch, invoice, receipt)
Cases: QA-SELL-05..13 (and QA-SELL-15, 16 for inter-state; QA-SELL-18, 19 for the counter); `docs/SALES_TO_RECEIPT_FLOW.md`, TC-SELL-007, 009, 011, 013.

| Step | Stock | Ledger | Customer | GST | Other |
| --- | --- | --- | --- | --- | --- |
| Approve order | Reserved up (Inventory screen) | None | None | None | SO- number; credit check |
| Dispatch note | Stock down, reserved 0; Stock Ledger DISPATCH | Dr Cost of Goods Sold / Cr Inventory | None | None | DN- number; warning kept if no invoice |
| Approve invoice | None | Dr Trade Receivables / Cr Sales, Cr Output tax | Outstanding up | GSTR-1 B2B or B2CS row; 3B 3.1(a) | SI- number; Home RECENT INVOICES |
| Receipt | None | Dr Bank / Cr Trade Receivables | Outstanding down; invoice leaves the receipt list | None | RC- number; no TCS |
| Cancel the paid invoice | Refused (QA-SELL-14) | Unchanged | Unchanged | Unchanged | Message names the receipt |

### One purchase, end to end (order, receipt, bill, payment)
Cases: QA-BUY-02..12; `docs/PURCHASE_TO_PAYMENT_FLOW.md`, TC-BUY-001, 003, 005, 008.

| Step | Stock | Ledger | Supplier | GST | Other |
| --- | --- | --- | --- | --- | --- |
| Approve order | None | None | None | None | PO- number |
| Complete receipt | Stock up at cost; Stock Ledger GOODS_RECEIPT | Dr Inventory / Cr Goods Received Not Invoiced | None | None | Order Part/Fully received |
| Approve bill | None | Dr Goods Received Not Invoiced, Dr Input tax / Cr Trade Payables | Owed up | 3B table 4 credit | Duplicate invoice number warns |
| Payment | None | Dr Trade Payables / Cr Bank (TDS to TDS Payable) | Owed down | TDS register | PY- number |
| Cancel the invoiced receipt | Refused (QA-BUY-11) | Unchanged | Unchanged | Unchanged | Names the bill |

### A return each way
- **Sales return** (QA-SELL-27, 28; TC-SELL-015): capped at what went out; stock back into MAIN, Dr Sales Returns, Dr Output tax / Cr Trade Receivables, plus Dr Inventory / Cr Cost of Goods Sold at the dispatch cost; customer owes less; GSTR-1 CDNR row. **Credit note** and **customer debit note** move no stock (QA-SELL-17, 29, 30).
- **Purchase return** (QA-BUY-13, 14; TC-BUY-006): capped at received; stock down (RETURN); Dr Trade Payables / Cr Inventory, Cr Input tax; bill owes less; 3B table 4 reduced. **Debit note** (QA-BUY-15; TC-BUY-017) moves no stock.

### Month-end GST
Cases: QA-GST-01..06, 14, 18, 19; QA-FIN-11..13, QA-REP-02, 03, 05, 06; TC-COMP-001, 003, 008, 021.
1. GST checks for the month (QA-GST-14): no findings.
2. GSTR-1 sections B2B, B2CS, CDNR, HSN against the Sales invoice register total (QA-REP-02).
3. GSTR-3B 3.1(a) equals GSTR-1 added by hand; table 4 equals Input IGST/CGST/SGST on the trial balance (QA-GST-05, 06; QA-FIN-11).
4. Trial balance Balanced; Customer and Vendor outstanding equal their ledgers (QA-FIN-11, 15; QA-REP-05, 06).
5. GST Payment read only (QA-GST-18); tax calendar on Home (QA-GST-19). Mark filed only on a copy of a firm you may spoil.

### Close of the run
Stock Summary agrees with Stock valuation and Inventory on the trial balance (QA-SELL-36, QA-REP-04); every approval rule, order and test record from the Approvals and Pricing modules is cancelled or inactive; the sign-off table at the foot of the test book is filled in.
