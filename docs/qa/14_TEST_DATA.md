# QA test data: what to type, case by case

The sample data for the whole QA suite and the functional walkthrough, so
nobody has to invent a value in the middle of a case. Every firm, person,
master record and document the cases name is here, with the values to type
and the screen and dropdown labels as the application shows them.

Nothing here goes into a database by itself. You type all of it through the
screens, the way a customer would. It is written by hand, like
`00_README.md`; files `01` to `13` are generated and are not edited to match
this sheet. Where the two disagree, the case's **Expect** is still what
passes, and the disagreement is listed in section H.

Compiled on 2026-09-25 from the cases, the walkthrough, the developer
fixture script that built every case's starting point
(`backend/scripts/test_fixture.py`), and the product's own forms and rules.

## How to use this sheet

1. **Build section A first**: the firms, their set-up and their places. Then
   section B, the people, then section C, the masters. Allow half a day.
2. **Then work module by module.** Before a file, build its preparations
   from section D; then take each case's values from section E.
3. **Names in the cases map to rows here.** A case written for the
   developer's fixtures says `QA-B`, `QA-C01` or **Manual Hire (qa)**; the
   row here with that code or name is the record to use. Where a case's
   code had to change to keep two cases apart, the row says so in words
   such as *(the case says `QA-P`)*.
4. **Today** means the day you run the case. Examples assume **Friday
   2026-09-25**; if you test later, move every date by the same number of
   days, except dates a case gives exactly (such as 2026-04-01 or
   2026-06-15).
5. **Codes are typed in capitals**, phone numbers **without spaces**
   (`+919840011001`, not `+91 98400 11001`: the product refuses spaces), and
   amounts without the thousands comma (`50000`, not `50,000`).
6. **Some set-up has no screen yet.** Four set-up steps can only be done
   with a REST client such as Postman, or by the developer: product
   categories, one coupon-only promotion, a loyalty credit and the
   platform designation. Each is marked **(HTTP)**
   with the exact request, and section H lists them. If you have neither,
   mark the cases that need them `Blocked` and say why.

### Which records are shared, and which are separate

- **The walkthrough and the suite share only the firm, its set-up and its
  people.** The walkthrough's `QA-P1` *Test Soap*, `QA-V1` *QA Supplies*,
  `QA-C1` *QA Retail* and warehouse `STORE2` are the walkthrough's own; no
  suite case uses them. The suite's `QA-B`, `QA-V`, `QA-P`, `QA-C`,
  `QA-CM` and the rest are separate records beside them in QA01. Do the
  walkthrough first; nothing in the suite changes its figures afterwards.
- **`QA-C1` means two different customers.** In the walkthrough it is *QA
  Retail* in QA01. In the territory cases (`10_TERRITORY`) it is *Revise
  Check qa* in **QA04**. Different firms, so they never meet; just do not
  look for one in the other's firm.
- **`QA-B` means two different records in QA01**: the product *Bought Item
  qa* (purchasing) and a customer *Audit After qa* that TC-AUDIT-004
  creates. A product code and a customer code never clash, so both are
  allowed.
- **`QA-V` is one vendor in QA01** for both the purchasing cases (which call
  it *Fixture Supplier qa*) and the vendor-master cases (which call it
  *Supply Check qa*). This sheet names it *Fixture Supplier qa* and gives it
  all six child collections, so it serves both.
- **Each preparation that changes a whole firm gets a firm of its own.**
  The developer ran every case in a fresh firm. By hand that would be
  eleven firms per run, so this sheet groups the cases that can share a
  firm without disturbing each other's figures, and gives a firm of its own
  only where they cannot: a firm with TCS switched on, promotions and a
  price ladder (QA03), a territory and commission firm (QA04), a firm whose
  GST return must hold exactly three invoices (QA05), a Pharmacy and an
  Electronics firm (QA06, QA07), a finished firm whose custom fields and
  books the cases rearrange (QAR1), and four half-built firms for the
  set-up cases.
- **MEDI01, FOOD01, ELEC01, WHOLE01 and TEST01** are the developer's demo
  firms. They do not exist on an installed copy. As `00_README.md` says,
  read them as *any other firm on this installation*; QA06 or QA07 will do.
- **QASH1 and QASH2** in the cases are two firms sharing one store. On this
  sheet QA01 and QA02 are both *With the other firms* (SHARED), so they
  **are** that pair: read QASH1 as QA01 and QASH2 as QA02.

---

## A. The firms

### A1. Every firm, and what it is for

Sign in as `platform-admin@agency.local` for all of section A.
**Administration → Firms → New.**

| Code | Display name | Storage | Business profile | Used by |
| --- | --- | --- | --- | --- |
| QA01 | QA Traders | With the other firms | Wholesale | Walkthrough; files 02, 03, 05, 06; 07 TC-STOCK-001..004; 12 TC-CASH, TC-AUDIT, TC-FIN-006, TC-FIN-010, TC-FIN-011; 13 except the QA03 cases; QASH1 |
| QA02 | QA Traders Two | With the other firms | Wholesale | Second firm for isolation and people in two firms; 05 TC-MAST-004..007; QASH2 |
| QA03 | QA Selling | With the other firms | Wholesale | 08; 09 TC-INCENT-001..005; 11 TC-COMP-007; 12 TC-FIN-002, 004, 005, 008, 009; 13 TC-CONC-002, 004, 005 |
| QA04 | QA Field Sales | With the other firms | Wholesale | 10; 09 TC-INCENT-006..008; 13 TC-CONC-006 |
| QA05 | QA GST Filing | With the other firms | Wholesale | 11 TC-COMP-001..006 |
| QA06 | QA Pharma | With the other firms | Pharmacy | 07 TC-STOCK-005..007 |
| QA07 | QA Electronics | With the other firms | Electronics | 07 TC-STOCK-008; 04 TC-FIRM-017 step 4 |
| QAR1 | QA Ready | Separately, in the same database | Wholesale | 04 TC-FIRM-014, 015, 017, TC-FIELD-001..012, TC-CONF-004, 006; 12 TC-FIN-001, 003, 007 |
| QAU1 | QA Unprovisioned One | Separately, in the same database | none | 04 TC-FIRM-004, 005 |
| QAU2 | QA Unprovisioned Two | Separately, in the same database | none | 04 TC-FIRM-006 |
| QAF1 | QA Unfinished | Separately, in the same database | set by the cases | 04 TC-FIRM-007..013 |

TC-FIRM-002 creates one more firm, `QA-S1` *Created qa*, itself. Build QA01
first: the first firm with *With the other firms* storage builds the shared
store, and takes noticeably longer to save.

### A2. What to type on the firm form

The form requires **Firm code, Display name, Country, Currency code and
Financial year start**; everything else is optional. The GST and PAN
numbers are checked only for being unique among live firms, not for their
format, so type them exactly as below. Contact phone must be in the form
`+91` then the number, with no spaces.

| Field on the form | QA01 | QA02 | QA03 | QA04 |
| --- | --- | --- | --- | --- |
| Firm code | `qa01` (walkthrough W2 types it in lower case; it is stored QA01) | `QA02` | `QA03` | `QA04` |
| Display name | QA Traders | QA Traders Two | QA Selling | QA Field Sales |
| GST number | `33ABCDE1234F1Z5` | `33AAQCT2002K1ZF` | `33AAQCS3003L1ZB` | `33AAQCF4004M1ZJ` |
| PAN number | `ABCDE1234F` | `AAQCT2002K` | `AAQCS3003L` | `AAQCF4004M` |
| Address line 1 | 12 Anna Salai | 25 Avinashi Road | 3 Town Hall Road | 14 Poonamallee High Road |
| Address line 2 | Teynampet | Peelamedu | Simmakkal | Kilpauk |
| City | Chennai | Coimbatore | Madurai | Chennai |
| State / province | Tamil Nadu | Tamil Nadu | Tamil Nadu | Tamil Nadu |
| Postal code | 600018 | 641004 | 625001 | 600010 |
| Country | `IN` | `IN` | `IN` | `IN` |
| Contact name | Priya Raman | Karthik Subramanian | Meena Sundaram | Arun Kumar |
| Contact email | accounts@qatraders.test | accounts@qatraders2.test | accounts@qaselling.test | accounts@qafield.test |
| Contact phone | `+914424330101` | `+914222570202` | `+914522340303` | `+914426410404` |
| Currency code | `INR` | `INR` | `INR` | `INR` |
| Financial year start | `2026-04-01` | `2026-04-01` | `2026-04-01` | `2026-04-01` |
| Where this firm keeps its data | With the other firms (recommended) | same | same | same |

| Field on the form | QA05 | QA06 | QA07 | QAR1 |
| --- | --- | --- | --- | --- |
| Firm code | `QA05` | `QA06` | `QA07` | `QAR1` |
| Display name | QA GST Filing | QA Pharma | QA Electronics | QA Ready |
| GST number | `33AAQCG5005N1ZD` | `33AAQCP6006P1ZX` | `33AAQCE7007Q1Z3` | `33AAQCR8008R1ZL` |
| PAN number | `AAQCG5005N` | `AAQCP6006P` | `AAQCE7007Q` | `AAQCR8008R` |
| Address line 1 | 9 Cathedral Road | 21 Big Bazaar Street | 5 Ritchie Street | 30 Nungambakkam High Road |
| Address line 2 | Gopalapuram | Fort | Mount Road | Nungambakkam |
| City | Chennai | Tiruchirappalli | Chennai | Chennai |
| State / province | Tamil Nadu | Tamil Nadu | Tamil Nadu | Tamil Nadu |
| Postal code | 600086 | 620008 | 600002 | 600034 |
| Country | `IN` | `IN` | `IN` | `IN` |
| Contact name | Lakshmi Narayanan | Dr. S. Balaji | Farhan Ali | Deepa Menon |
| Contact email | accounts@qagst.test | accounts@qapharma.test | accounts@qaelectronics.test | accounts@qaready.test |
| Contact phone | `+914428110505` | `+914312700606` | `+914428520707` | `+914428270808` |
| Currency code | `INR` | `INR` | `INR` | `INR` |
| Financial year start | `2026-04-01` | `2026-04-01` | `2026-04-01` | `2026-04-01` |
| Where this firm keeps its data | With the other firms (recommended) | same | same | Separately, in the same database |
| Schema name | | | | leave blank (the server names it) |

**QAU1, QAU2 and QAF1** take only the required fields, on purpose: code,
display name from A1, country `IN`, currency `INR`, financial year start
`2026-04-01`, **Separately, in the same database**, schema name blank. No
GST number, PAN, address or contact. Do not press Provision storage on QAU1
or QAU2; the cases do. **Press Provision storage on QAF1** (Firms grid,
select it) and nothing else.

All eight trading firms carry a Tamil Nadu GST number (state code 33) with
the firm's PAN at characters 3 to 12. Every number above except QA01's also
has a correct check character; QA01's is the one the walkthrough prints,
kept so that W55's *Filing as 33ABCDE1234F1Z5* stays true.

### A3. The Set up panel

Administration → Firms → select the firm → **Set up**. Do the rows in this
order for QA01 to QA07 and QAR1. **Not** for QAU1, QAU2 or QAF1: their
cases press these buttons themselves.

| Row | Choose or press | QA01 to QA05, QAR1 | QA06 | QA07 |
| --- | --- | --- | --- | --- |
| Business profile | profile dropdown, then **Assign** | Wholesale | Pharmacy | Electronics |
| Books | **Open the books** | yes | yes | yes |
| Tax | **Apply GST template** | yes | yes | yes |
| Geography | turns done with the GST template | | | |
| Branches and warehouses | **Create head office and main warehouse** | yes | yes | yes |
| People | done once the firm administrator in section B exists | | | |

After this every one of them has branch `HO` *Head Office* and warehouse
`MAIN`, a chart of 24 accounts, one financial year starting 2026-04-01 with
12 periods, and the GST tax profiles. The tax profile dropdown on a product
then offers these eight: **GST 0%**, **GST 5% Local**, **GST 5%
Interstate**, **GST 12% Local**, **GST 12% Interstate**, **GST 18% Local**,
**GST 18% Interstate** and **Exempt** (each shown with its code, such as
`GST_18_LOCAL`).

### A4. Places (the geography masters)

The GST template adds the country India and nothing under it. The address
pickers need a state, district and city. **Writing places needs the
platform administrator**: sign in as `platform-admin@agency.local`, switch
into the firm, then **Sales → Places**. Open *India*, then **New** at each
level; each asks for a **Code** and a **Name**.

| Firm | State (code, name) | District (code, name) | City (code, name) | Postal code |
| --- | --- | --- | --- | --- |
| QA01 | `TN` Tamil Nadu | `CHN` Chennai | `CHENNAI` Chennai | `600002` |
| QA01 | `KA` Karnataka | `BLR` Bengaluru Urban | `BENGALURU` Bengaluru | `560001` |
| QA02 | `TN` Tamil Nadu | `CBE` Coimbatore | `COIMBATORE` Coimbatore | `641004` |

The cases' **State qa → District qa → City qa** are Tamil Nadu → Chennai →
Chennai in QA01, and Tamil Nadu → Coimbatore → Coimbatore in QA02.
Karnataka is there for an inter-state address; no case in the suite needs
one, since the only IGST case (TC-CONF-005) uses the Rule Simulator.

---

## B. The people

### B1. Passwords

The password rule: **at least 12 characters, with an upper-case letter, a
lower-case letter, a digit and a symbol**. The last 5 passwords of an
account cannot be used again. Five wrong passwords lock an account for 15
minutes.

- Every account prepared below starts with **`QaTest@2026pw`**. Wherever a
  case says *a password you choose*, *a password* or *a 12-character
  password*, type that.
- On **Users → New**, untick **Require password change** for prepared
  accounts, so the password stays usable. The exceptions are marked.
- The platform administrator's password is the one set during
  installation.

### B2. Platform administrators

| Email | Full name | How it comes to exist | Firms | Used by |
| --- | --- | --- | --- | --- |
| `platform-admin@agency.local` | (as installed) | Made by the installer | none | Every *Platform admin* in the cases; all of section A |
| `platform.member@qa.test` | Platform Member (qa) | Users → New in QA01 (primary) and QA02, no roles; then **the developer** gives it the ALL_FIRMS platform designation | QA01 (primary), QA02 | TC-PLAT-004, TC-SESS-010 step 2 |
| `operator@qa.test` | Platform Operator (qa) | Users → New in QA01 (primary) and QA02, no roles; then **the developer** gives it the PLATFORM designation | QA01 (primary), QA02 | TC-TIER-001..003 |

No screen or request grants the platform designation; that is deliberate.
Without the developer, mark TC-PLAT-004, TC-TIER-001..003 and TC-SESS-010
step 2 `Blocked`.

### B3. One person per job template, in QA01

Create these as the **QA01 firm administrator** (after the first row exists)
with **Administration → Users → New**: Full name, Username (Email),
Initial password `QaTest@2026pw`, **Require password change** off unless
marked, **Job template** as listed, **Firms** QA01 (already ticked).

| Email | Full name | Job template | Used by |
| --- | --- | --- | --- |
| `admin@qa01.test` | QA01 Admin (qa) | Firm Administrator | Walkthrough W9 onward (created by the platform admin); every *Firm admin* of QA01; 01 R01 |
| `manager@qa01.test` | Firm Manager (qa) | Firm Manager | 01 R02 |
| `counter@qa01.test` | Counter Sales (qa) | Counter Sales. **Require password change on**: W71 changes it to `Counter-Passw0rd!` | Walkthrough W70-W71; 01 R03 |
| `field@qa01.test` | Field Sales (qa) | Field Sales | Walkthrough W72-W74; 01 R04; the *Seller* of every QA01 case (TC-CUST-003, TC-TMPL-009, TC-LOOK-005, TC-CONF-001, TC-PERM-001..003, TC-GRANT-007, TC-AUDIT-006) |
| `salesmgr@qa01.test` | Sales Manager (qa) | Sales Manager | 01 R05; the *Loyalty viewer* of TC-GRANT-005 |
| `warehouse@qa01.test` | Warehouse (qa) | Warehouse | 01 R06 |
| `purchasing@qa01.test` | Purchasing (qa) | Purchasing | 01 R07 |
| `purchmgr@qa01.test` | Purchase Manager (qa) | Purchase Manager | 01 R08 |
| `accounts@qa01.test` | Accounts (qa) | Accounts | 01 R09; the *Accountant* of TC-CASH-003 |
| `support@qa01.test` | Customer Support (qa) | Customer Support | 01 R10 |
| `readonly@qa01.test` | Read Only (qa) | Read Only | 01 R11 |
| `cashier@qa01.test` | Cashier (qa) | **none**; Roles in this firm: `CASHIER` only | TC-CASH-001, 002 |

### B4. People the cases name

Create each as the account in the *Created by* column. **Roles by firm** is
the button on the Users grid; **Roles in every firm** is the roles field on
the platform administrator's user form.

| Email | Full name | Created by | Firms (primary first) | Roles | Used by |
| --- | --- | --- | --- | --- | --- |
| `admin@qa02.test` | QA02 Admin (qa) | platform admin | QA02 | Job template Firm Administrator | Every *QA02 admin* and *QASH2 admin* |
| `twofirm@qa.test` | Two Firm User (qa) | platform admin | QA01, QA02 | Roles in every firm: `CUSTOMER_SUPPORT`. Then Roles by firm, QA01: `SALES_EXECUTIVE` | TC-ME-001..005, 008 |
| `manual.hire@qa.test` | Manual Hire (qa) | QA01 admin | QA01 | Job template blank; Roles in this firm `SALES_EXECUTIVE`, `CUSTOMER_SUPPORT` | TC-USER-001, TC-TMPL-005, TC-AUDIT-004 |
| `twotier@qa.test` | Two Tier Hire (qa) | platform admin | QA01 | Roles in every firm `VIEWER`, `CUSTOMER_SUPPORT`; Roles by firm, QA01: `ACCOUNTANT`, `INVENTORY_MANAGER` | TC-TMPL-006..008, TC-RTIER-007 |
| `source.seller@qa.test` | Source Seller (qa) | QA01 admin | QA01 | Job template Field Sales | TC-HIRE-001..004 (the *Source*) |
| `shared.member@qa.test` | Shared Member (qa) | platform admin | QA02, QA01 | none (TC-RTIER-001 gives them some) | TC-USER-002, 006..008, TC-RTIER-001..004, 006, 008, TC-SESS-010 |
| `qa02.only@qa.test` | QA02 Only (qa) | platform admin | QA02 | none | TC-RTIER-008 steps 3-4 |
| `outsider@qa.test` | Outsider (qa) | QA02 admin | QA02 | Roles in this firm `CASHIER` | TC-LOOK-001..004 |
| `outsider2@qa.test` | Outsider Two (qa) | QA02 admin | QA02 | Roles in this firm `CASHIER` | TC-LOOK-006 (a second outsider, because TC-LOOK-002 has already brought the first into QA01) |
| `lock.target@qa.test` | Lock Target (qa) | QA01 admin | QA01 | Job template Field Sales | TC-SESS-003..005, 008, 009, 011 (the *Target*) |
| `lock.target2@qa.test` | Lock Target Two (qa) | QA01 admin | QA01 | Job template Field Sales | TC-SESS-007 (its own target, so TC-SESS-008 can still restore the first) |
| `nightdesk@qa.test` | Night Desk Holder (qa) | QA01 admin, after the role *Night Desk qa* exists (the Night Desk row in E, 03) | QA01 | Roles in this firm: `Night Desk qa` only | TC-ROLE-007..009 (the *Role holder*) |
| `nightcounter@qa.test` | Night Counter Hire (qa) | QA01 admin, after TC-TMPL-002 | QA01 | Job template **Night Counter renamed** (`qa-night-counter`) | TC-TMPL-010 |
| `admin@qa03.test` | QA03 Admin (qa) | platform admin | QA03 | Job template Firm Administrator | 08, 09, TC-COMP-007, TC-FIN-002/004/005/008/009, TC-CONC-002/004/005 |
| `admin@qa04.test` | QA04 Admin (qa) | platform admin | QA04 | Firm Administrator | 10, TC-INCENT-006/007, TC-CONC-006 |
| `asha@qa04.test` | Asha Sales | QA04 admin | QA04 | Job template Field Sales | 10, TC-INCENT-006..008 (*Asha*) |
| `bala@qa04.test` | Bala Sales | QA04 admin | QA04 | Job template Field Sales | 10, TC-INCENT-006, 007 (*Bala*) |
| `admin@qa05.test` | QA05 Admin (qa) | platform admin | QA05 | Firm Administrator | 11 TC-COMP-001..006 |
| `admin@qa06.test` | QA06 Admin (qa) | platform admin | QA06 | Firm Administrator | TC-STOCK-005, 006 |
| `admin@qa07.test` | QA07 Admin (qa) | platform admin | QA07 | Firm Administrator | TC-STOCK-008 |
| `admin@qar1.test` | Ready Admin (qa) | platform admin | QAR1 | Firm Administrator | Every *Firm admin* of the ready firm |
| `viewer@qar1.test` | Ready Viewer (qa) | platform admin | QAR1 | Job template Read Only | TC-FIRM-015 step 5 (the *Viewer*) |

The **Platform admin** of every case is `platform-admin@agency.local`.
**Fixture Firm Admin (qa)** in TC-LOOK-001 is QA01 Admin (qa).

### B5. Accounts the cases create themselves

Nothing to prepare; listed so the addresses do not surprise you, and so you
never create them early.

| Email | Created in | Password to type |
| --- | --- | --- |
| `qa.newbie@qa.test` | TC-SESS-006 | `Welcome@123456`, then `Newbie-Passw0rd!` |
| `qa.infirm@qa.test` | TC-USER-003 | `QaTest@2026pw` |
| `qa.nofirm@qa.test`, `qa.nofirm2@qa.test` | TC-USER-004 | `QaTest@2026pw` |
| `qa.counter@qa.test` | TC-USER-009 | `QaTest@2026pw` |
| `qa.clone@qa.test` | TC-HIRE-002 | `Welcome@12345`, then `CloneTest@2026x` |
| `qa.clone2@qa.test` | TC-HIRE-003 (the case reuses `qa.clone@qa.test`, which HIRE-002 already took) | `Welcome@12345` |
| `qa.jobhire@qa.test`, `qa.handhire@qa.test` | TC-TMPL-003 | `QaTest@2026pw` |
| `qa.readonly@qa.test` | TC-TMPL-004 | `QaTest@2026pw` |
| `qa.global1@qa.test`, `qa.global2@qa.test` | TC-RTIER-005 | `QaTest@2026pw` |
| `qa.hire@qa.test` | TC-ROLE-006 | `QaTest@2026pw` |
| `nobody.qa@qa.test` | never: TC-SESS-003 types it as an address that does not exist | `Wrong@Password1` |
| `qa.x@qa.test` | never: TC-HIRE-004's request is refused | `Welcome@12345` |

---

## C. Masters

Type these as the firm's administrator unless the row says otherwise.
Anything not listed is left as the form offers it. **Customer type** is
*Business* and **Currency** `INR` for every customer unless stated.
**Product type** is *STOCK_ITEM* for every product. Units are chosen on the
product's **UOM & Size** tab, the tax profile and HSN on its **Tax** tab,
prices on **Pricing**.

### C1. QA01: the walkthrough's own

| Record | Values | Used by |
| --- | --- | --- |
| Warehouse `STORE2` | Warehouse Name *Back Store*, Branch *HO - Head Office*, nothing else | W12, W32-W34 |
| Product `QA-P1` | Product name *Test Soap*; Base, Inventory, Purchase and Sales UOM **PIECE**; Tax profile **GST 18% Local**; HSN / SAC `3401`; Purchase price `100`; Selling price `150`; Category blank (see H) | W13-W67 |
| Vendor `QA-V1` | Vendor Name *QA Supplies*; Phone `+919840011001`; GSTIN `33AABCQ1101E1ZC`; one address: type Office, line 1 *18 SIDCO Industrial Estate*, place India, Tamil Nadu, Chennai, Chennai | W14, W15 (new phone `+919840011002`), W19-W29 |
| Customer `QA-C1` | Customer name *QA Retail*; Business; INR; Phone `+919841022001`; no GST number; Credit limit `0` (0 means no limit); one address: Billing, line 1 *45 Anna Salai*, City Chennai, State Tamil Nadu, Postal code `600002`, Country `IN` | W16, W17 (new phone `+919841022002`), W35-W63 |

### C2. QA01: masters the suite needs

| Record | Values | Used by |
| --- | --- | --- |
| Warehouse `QA-W2` | Warehouse Name *Overflow qa*, Branch HO | TC-STOCK-002 |
| Customer groups (Customers toolbar → **Groups**) | `QA-RET` *Retailer qa*, default discount `1.75`; `QA-WHL` *Wholesaler qa*, default discount `3.25` | TC-CUST-001, 006 |
| Vendor category `QA-CAT` (Masters → Vendor Categories) | *Category qa* | TC-MAST-002 |
| Vendor type `QA-TYP` (Masters → Vendor Types) | *Type qa* | TC-MAST-002 |
| Vendor `QA-V` | Vendor Name *Fixture Supplier qa*; Phone `+919800000200`; category and type **left blank** (TC-MAST-002 sets them). **Contacts**: *Vendor Contact*, mobile `+919800000201`, Primary. **Addresses**: Office, *7 Supplier Lane*, place Tamil Nadu, Chennai, Chennai, Primary. **Banking**: bank *Fixture Bank*, account name *Fixture Supplier qa*, account number `000111222333`, IFSC `FXBK0000001`, Primary. **Tax**: PAN `AAHFS2222C`, Primary. **Attachments**: file name `agreement.pdf`, URL `https://example.invalid/agreement.pdf`. **Notes**: *Supply terms agreed for QA.* | TC-BUY-001..008 (as *Fixture Supplier qa*), TC-MAST-001, 002 (as *Supply Check*) |
| Vendor `QA-VS` | Vendor Name *Stock Supplier qa*; Phone `+919800000300` | stock-in, D2 |
| Product `QA-B` | *Bought Item qa*; PIECE for all four units; GST 18% Local; HSN `3402`; Purchase price `100`; Selling price `150` | TC-BUY-001..005, 007, 008, TC-STOCK-001 |
| Product `QA-B2` | *Bought Item Two qa*; as `QA-B` | TC-BUY-006 (the case says `QA-B`) |
| Product `QA-P` | *Fixture Product qa*; PIECE; GST 18% Local; Purchase `60`; Selling `100` | TC-STOCK-002 |
| Product `QA-P3` | *Write Off Item qa*; as `QA-P` | TC-STOCK-003 (the case says `QA-P`) |
| Product `QA-P4` | *Count Item qa*; as `QA-P` | TC-STOCK-004 (the case says `QA-P - Fixture Product qa`) |
| Product `QA-PS` | *Sold Item qa*; as `QA-P` | the *invoiced* sale (D2): TC-GRANT-001, TC-ISO-003, TC-CUST-005; TC-CUST-004's order (the case says `QA-P`) |
| Product category `QA-PC` | *Shelf qa*. **(HTTP) only**: `POST /api/v1/products/categories` with `X-Firm-ID` of QA01 and `{"code": "QA-PC", "name": "Shelf qa"}` | `QA-PM` |
| Product `QA-PM` | *Slot Check qa*; Category *Shelf qa*; Base, Inventory and Sales UOM **PIECE**, Purchase UOM **BOX**; GST 18% Local; Selling `100` | TC-MAST-003, 008, TC-FIN-006 |
| Packaging level on `QA-PM` (Administration → Configuration → UOM & Packaging → **Packaging Levels**) | Level name *Case*; UOM **CASE**; factor to base `12`; barcode `8906012345678` | TC-MAST-008 (type this barcode) |
| Customer `QA-CM` | *Master Check qa*; Phone `+919800000100`; **Financial** tab: Customer group *Retailer qa*, Credit limit `50000`, Default discount % `7.5`, Payment terms (days) `30`; **Address**: Billing, line 1 *12 Fixture Street*, place India, Tamil Nadu, Chennai, Chennai, Postal code `600001`, default billing; **Contacts**: *Fixture Contact*, mobile `+919800000101`, Primary | TC-CUST-001..004, 006, TC-CONC-001, 003 |
| Customer `QA-C` | *Fixture Buyer qa*; nothing else | the *invoiced* sale (D2): TC-CUST-005, TC-GRANT-001, TC-ISO-003 |
| Customer `QA-TILL` | *Till Customer qa*; nothing else | TC-CASH-002 |
| Customer `QA-ONE` | *Isolation One qa* | TC-SESS-001, TC-ISO-002 |
| Customer `QA-SHONE` | *Isolation Shone qa* | TC-ISO-001 |

### C3. QA02

| Record | Values | Used by |
| --- | --- | --- |
| Customer `QA-TWO` | *Isolation Two qa* | TC-SESS-001, TC-ISO-002 |
| Customer `QA-SHTWO` | *Isolation Shtwo qa* | TC-ISO-001 |
| Branch `QA-BR` | Branch Name *Keep Branch qa*; **Default branch** ticked; **GST registered** ticked; Address line 1 *1 Keep Street*; Address line 2 *Keep Nagar*; place India, Tamil Nadu, Coimbatore, Coimbatore. The PAN is not on the desktop form; see H | TC-MAST-004 |
| Warehouse `QA-WH` | Branch *QA-BR - Keep Branch qa*; Warehouse Name *Keep Warehouse qa*; Capacity `1000`; Capacity Unit `SQFT`. Capabilities **ticked**: Default warehouse, Temperature controlled, Cold storage, Receiving area, Dispatch area, Inspection area, Loading dock. **Not ticked**: Hazardous storage, Returns area, Packing area | TC-MAST-005 |
| Import file *clash* | See E, 05 TC-MAST-006 | TC-MAST-006 |
| Import file *clean* | See E, 05 TC-MAST-006 | TC-MAST-006 |

Making `QA-BR` the default branch moves the default away from `HO` in QA02.
That is expected; nothing else in QA02 relies on HO being the default.

### C4. QA03: the selling firm

| Record | Values | Used by |
| --- | --- | --- |
| Customer groups | `RETAILER` *Retailer*, default discount `1.75`; `WHOLESALER` *Wholesaler*, default discount `3.25` | the two customers |
| Customer `QA-C01` | *Vijaya Stores qa*; Customer group *Retailer*; Default discount % `7.5`; **no PAN, no GST number**; Credit limit `0` | 08, 09, TC-FIN-009, TC-CONC-002/004/005 |
| Customer `QA-C02` | *Anand Agencies qa*; Customer group *Wholesaler*; PAN number `AAFCA3131H`; Default discount blank (0); Credit limit `0` (TC-FIN-008's preparation sets 1000) | 08, 09, TC-FIN-008 |
| Vendor `QA-VS` | *Stock Supplier qa*; Phone `+919800000300` | stock-in only |
| Product `QA-DET` | *Detergent 1kg qa*; PIECE for all four units; GST 18% Local; Purchase `60`; Selling `84`; no HSN | 08, 09 |
| Stock | 100 of `QA-DET` into MAIN at 60, by purchase: D5 | |
| Price list `STANDING` (Sales → Price Lists → New) | Code `STANDING`; Name *Standing*; In force from `2000-01-01`; Until blank; Customer blank (everyone). Add product three times: `QA-DET` From qty `0` Discount % `2`; `QA-DET` From qty `15` Discount % `4.25`; `QA-DET` From qty `18` Discount % `6.75` | TC-SELL-001, 002, TC-INCENT-001, TC-CONC-002 |
| Price list `NEGOTIATED` | Code `NEGOTIATED`; Name *Negotiated*; In force from `2000-01-01`; Customer *QA-C02 Anand Agencies qa*; `QA-DET` From qty `0` Discount % `9.25` | TC-SELL-003, TC-FIN-008 |
| Promotion `BULK5` (Sales → Promotions → New) | Name *Bulk5*; Applies at `10`; Status Active; From `2020-01-01`; Other promotions may still apply **on**. Gives: Percent off each line, Percent `7.5`. Applies when (**Add condition**): When *Quantity on the line*, Test *is at least*, Value `25` | TC-SELL-004, TC-INCENT-001, 002, 004 |
| Promotion `BIGORDER` | Name *Bigorder*; Applies at `20`; Active; From `2020-01-01`; Other promotions may still apply **off** (the dialog then says *This offer ends the stack*). Gives: Amount off the whole bill, Amount `200`. Applies when: *Order value* *is at least* `4500` | TC-INCENT-004 |
| Promotion `CLEARANCE` | Name *Clearance*; Applies at `30`; Active; From `2020-01-01`; stacking on. Gives: Percent off each line, `1`. Applies when: *Quantity on the line* *is at least* `40` | TC-INCENT-004 |
| Promotion `WELCOME` | **(HTTP) only**, because the desktop has no *coupon only* switch: `POST /api/v1/promotions` with `X-Firm-ID` of QA03 and `{"code": "WELCOME", "name": "Welcome", "priority": 40, "status": "ACTIVE", "effective_from": "2020-01-01", "requires_coupon": true, "conditions": [], "actions": [{"action_type": "LINE_DISCOUNT_PERCENT", "percent": "2.5"}]}`. Made on screen instead, it applies to every line and every pricing case fails | TC-SELL-006, 007, 010, TC-INCENT-003, TC-CONC-005 |
| Coupons (Sales → Promotions → **Coupons** → New) | Offer *WELCOME*; Code `WELCOME10`; Total claims allowed blank. Then Offer *WELCOME*; Code `WELCOME10B`; Total claims allowed blank | as WELCOME |
| TCS (Sales → TCS → **Settings**) | Collect under section 206C(1H) **on**; Preceding year turnover `150000000`; Threshold `0`; Rate `0.1`; Rate without a PAN `1` | TC-SELL-013, 014, TC-COMP-007 |
| Loyalty (Masters → Loyalty → **Scheme settings**) | Scheme is running **on**; points per 100 `2`; worth `1` each; Minimum to redeem `50`; Points expire **on**, after `24` months | TC-INCENT-005 |

### C5. QA04: the territory and commission firm

| Record | Values | Used by |
| --- | --- | --- |
| Route type (Sales → Route Types → New) | Code `SALES`; Name *Sales Route* | the three routes |
| Territory `QA-RGN` (Sales → **Geography** → New) | Name *Chennai Region*; Hierarchy level Region; Parent none | TC-TERR-001 |
| Territory `QA-T-N` | *North Zone*; level Territory; Parent Chennai Region | |
| Territory `QA-T-S` | *South Zone*; level Territory; Parent Chennai Region | |
| Route `QA-R-N1` | *North Sales Beat*; level Route; Parent North Zone; Route type Sales Route; Visit frequency Weekly; working days Mon, Wed, Fri; effective dates blank | TC-TERR-001..004 |
| Route `QA-R-N2` | *North Collections*; level Route; Parent North Zone; Sales Route; Fortnightly; Tue, Thu | TC-TERR-002, 003, 005 |
| Route `QA-R-S1` | *South Sales Beat*; level Route; Parent South Zone; Sales Route; Weekly; Tue, Thu | TC-TERR-003, 005 |
| Customers | `QA-C1` *Revise Check qa*; `QA-C2` *Classic Stores qa*; `QA-C3` *Vijaya Stores qa*; `QA-C4` *Anand Agencies qa*; `QA-SN` *Not Yet Routed qa*. Nothing else on any of them | 10, commission |
| Rounds (Sales → **Route Builder**) | `QA-R-N1`: 1 Revise Check qa, 2 Classic Stores qa. `QA-R-N2`: 1 Vijaya Stores qa. `QA-R-S1`: 1 Anand Agencies qa. `QA-SN` on no route. **Save round and order** after each | TC-TERR-001, 004 |
| Salespeople (open the route → **Salespeople**) | N1: Asha Sales, primary. N2: Bala Sales, primary. S1: Asha Sales, primary | TC-TERR-001, 005, commission |
| Beat plans (Sales → **Beat Plans** → New), weekly | Repeats Weekly, one per working day: `QA-BP-R1-MON` *Mon round R1*, Route North Sales Beat, On Monday; `QA-BP-R1-WED` Wednesday; `QA-BP-R1-FRI` Friday; `QA-BP-R2-TUE` *Tue round R2*, Route North Collections, Tuesday; `QA-BP-R2-THU` Thursday; `QA-BP-R3-TUE` *Tue round R3*, Route South Sales Beat, Tuesday; `QA-BP-R3-THU` Thursday | TC-TERR-002, 003 |
| Beat plan `QA-BP-COLL` | *Collections, alternate Tuesdays*; Route North Collections; Repeats Fortnightly; On Tuesday; starts on `2026-04-07` | TC-TERR-003 |
| Beat plan `QA-BP-MTH` | *Second Tuesday review*; Route South Sales Beat; Repeats Monthly; On Tuesday; Week of the month `2` | TC-TERR-003 |
| Vendor `QA-VS` | *Stock Supplier qa*; Phone `+919800000300` | stock-in |
| Product `QA-P` | *Fixture Product qa*; PIECE; GST 18% Local; Purchase `60`; Selling `100` | TC-TERR-005, commission |
| Product `QA-Q` | *Other Product qa*; as `QA-P` | commission |
| Stock | 50 of `QA-P` and 200 of `QA-Q` into MAIN at 60, by purchase: D5 | |

That is nine beat plans, which TC-TERR-002 counts. If a new territory is
refused as *not active*, open the hierarchy levels on the Geography screen
and **Save** them unchanged first (defect D-11-1: a new firm's levels are
not real until saved once).

### C6. QA05: the GST filing firm

| Record | Values | Used by |
| --- | --- | --- |
| Customer `QA-B2B` | *Registered Buyer qa*; Business; GST number `33AABCR5005B1Z6`; PAN number `AABCR5005B`; address: Billing, *40 Mount Road*, Chennai, Tamil Nadu, `600002`, `IN` | TC-COMP-001..003, 006 |
| Customer `QA-B2C` | *Walk-in Buyer qa*; Customer type **Individual**; no GST number, no PAN | TC-COMP-001, 002, 005 |
| Vendor `QA-VS` | *Stock Supplier qa*; Phone `+919800000300` | stock-in |
| Product `QA-P` | *Fixture Product qa*; PIECE; GST 18% Local; **HSN / SAC `340220`**; Purchase `60`; Selling `100` | 11 |
| Stock | 50 of `QA-P` into MAIN at 60, by purchase: D5 | |

### C7. QA06 and QA07

| Firm | Record | Values | Used by |
| --- | --- | --- | --- |
| QA06 | Vendor `QA-VP` | *Pharma Distributor qa*; Phone `+919800000600`; Drug licence in its Tax tab: `TN-RX-20B-0606` | stock-in |
| QA06 | Product `QA-AMX` | *Amoxicillin qa*; PIECE; **GST 12% Local**; Purchase `60`; Selling `100`; on UOM & Size: **Track batch** and **Track expiry** on | TC-STOCK-005 |
| QA06 | Product `QA-SHT` | *Scarce Syrup qa*; PIECE; GST 12% Local; Purchase `60`; Selling `100`; no tracking | TC-STOCK-006 |
| QA06 | Customer `QA-RX` | *Clinic qa*; Business | the two orders |
| QA07 | Vendor `QA-VE` | *Electronics Distributor qa*; Phone `+919800000700` | stock-in |
| QA07 | Product `QA-MIX` | *Mixer Grinder qa*; PIECE; GST 18% Local; Purchase `2000`; Selling `2500`; **Track serial** on | TC-STOCK-008 |

### C8. QAR1: the ready firm

| Record | Values | Used by |
| --- | --- | --- |
| Product categories | **(HTTP) only**, twice, with `X-Firm-ID` of QAR1: `POST /api/v1/products/categories` `{"code": "FXAMB", "name": "Fixture Ambient"}` and `{"code": "FXCHL", "name": "Fixture Chilled"}` | TC-FIELD-001..006, 011 |
| Customer `FXCUST` | *Fixture Customer qa*; nothing else | the 500.00 receipt |
| Receipt | Finance → Receipts → Record Receipt: `FXCUST`, amount `500.00`, method **Cash**, narration *Opening receipt to lock two accounts* | TC-FIRM-015 |
| Vendor `QA-V` | *Pack Supplier qa* | TC-CONF-006, TC-FIELD-009 |
| Product `QA-DET` | *Detergent 1kg qa*; Base UOM **KG**, Inventory UOM **KG**, Sales UOM **PACK**, Purchase UOM **PACK**; GST 18% Local; Purchase `100` | TC-CONF-006 |
| Conversion rule (Administration → Configuration → UOM & Packaging → Conversion Rules → Add) | Product `QA-DET`; From `PACK`; To `KG`; Factor `1`; effective from `2020-01-01` | TC-CONF-006 |

---

## D. The preparations, as documents

Each *Preparation* table in the suite names a starting state. Here is what
to create for each, in order. **Approve** and **Complete** are toolbar
buttons on the selected row; every screen reads once when opened, so press
**Refresh** after acting elsewhere.

### D1. Purchasing in QA01 (`06_PURCHASING`, `TC-STOCK-001`)

The four purchasing preparations are stages of **one** order. Run the cases
in the order below and each finds the state it expects, with the figures in
its Expect unchanged. The case itself does most of the building.

| Order | Case or step | What it creates or needs | State afterwards |
| --- | --- | --- | --- |
| 1 | TC-BUY-001 | Purchase order **PO-1**: vendor `QA-V`, branch HO, warehouse MAIN, today; line `QA-B` quantity `10`, unit price `100`. Save, Submit, Approve | `po-approved` |
| 2 | TC-BUY-002 | Edits PO-1 (remark *Deliver to back gate*, order remark *Confirmed by phone with Fixture Supplier qa*), then Submit and Approve again | `po-approved` |
| 3 | TC-BUY-007 | The reports, reading PO-1 | |
| 4 | TC-BUY-003 | Goods receipt **GRN-A** on PO-1, Accepted `4`, warehouse MAIN, Complete; then **GRN-B**, Accepted `6`, Complete | `po-received`: 10 on hand |
| 5 | TC-STOCK-001 | Reads the 10 | |
| 6 | TC-BUY-004 | Cancels GRN-A | 6 on hand |
| 7 | *Prep: invoice GRN-B* | Purchase Invoices → New: Goods Receipt *GRN-B*; Supplier Invoice Number `QA-SUP-001`; Supplier Invoice Date today; Invoice Date today; Remarks blank. Save Invoice, then **Approve**. Total **708.00** | `po-invoiced` |
| 8 | TC-BUY-005 | Tries to cancel GRN-B; refused | |
| 9 | TC-BUY-008 | Pays the 708.00 | |

**TC-BUY-006 needs its own order**, because a return from GRN-B would
change the figures above. Before it: purchase order **PO-2** from `QA-V`,
HO, MAIN, today, line `QA-B2` quantity `10` at `100`; Submit, Approve;
goods receipt Accepted `4`, Complete; goods receipt Accepted `6`, Complete.
Then TC-BUY-006 returns 2 from the receipt of 6, and MAIN holds 8 of
`QA-B2`.

### D2. Stock and a sale in QA01 (`07`, `05`, `12`, `13`)

| Preparation | Create |
| --- | --- |
| **Stock-in** (`stock-ready`) | Purchase order from `QA-VS`, HO, MAIN, today, four lines at unit price `60`: `QA-P` 50, `QA-P3` 50, `QA-P4` 50, `QA-PS` 50. Submit, Approve. Goods receipt on it, every line Accepted `50`, warehouse MAIN, Complete. Warehouse `QA-W2` from C2 stays empty |
| **invoiced** | Sales order: customer `QA-C` *Fixture Buyer qa*, ships from MAIN, branch HO, today; line `QA-PS` quantity `10`, unit price `100`, Discount % blank. Create draft, **Approve**. Delivery note on it: Delivering `10`, MAIN, Save, Approve, **Dispatch**. Sales Invoices → New Invoice → **Bill this delivery note** → that note, Bill `5`, Create draft, **Approve**: total **590.00**. New Invoice again on the same note, Bill `5`, Create draft, then **Cancel** it with the reason *Raised in error* |
| **invoiced-part-paid** | Finance → Receipts → Record Receipt: `QA-C`, amount `200.00`, method Bank, instrument reference `NEFT-QA-0200`; under Apply to invoices put `200.00` against the approved invoice. Record receipt. `QA-C` then owes 390.00 |
| **customer-master** | Customer `QA-CM` and the groups from C2; the Seller is `field@qa01.test` |

### D3. The firm-setting preparations (`04_FIRMS_AND_CONFIGURATION`)

| Preparation | Is | Notes |
| --- | --- | --- |
| `unprovisioned-firm` | **QAU1** for TC-FIRM-004 and 005; **QAU2** for TC-FIRM-006 | Two, because TC-FIRM-004 provisions its firm and TC-FIRM-006 needs one that is still unprovisioned |
| `unfinished-firm` | **QAF1**, provisioned and nothing else | Run its cases in the order given in E, 04 |
| `ready-firm` | **QAR1**: A2, A3, `admin@qar1.test`, `viewer@qar1.test`, C8 | The finished firm with two members, two categories, a customer and a 500.00 cash receipt |
| `config-firm` | QAR1 again, with the vendor, product and conversion rule of C8 | |
| `shared-pair` | QA01 and QA02 with their administrators | See *QASH1 and QASH2* at the top |
| `isolation-pair`, `shared-isolation-pair` | `QA-ONE` / `QA-TWO` and `QA-SHONE` / `QA-SHTWO` from C2 and C3 | |

### D4. Selling in QA03 (`08_SELLING`, `09`, `11`, `12`, `13`)

The selling preparations are stages of **one** sale to Vijaya. Build each
stage when the run order in E, 08 reaches it; the cases between them depend
on it not having happened yet.

| Preparation | Create | Check |
| --- | --- | --- |
| `selling-firm` | C4 in full, and D5's stock-in of 100 `QA-DET` | Inventory: MAIN 100 |
| `selling-ordered` | Sales Orders → New Order: `QA-C01`, ships from MAIN, today; line `QA-DET` quantity `12`, unit price `84`, Discount % blank; **Coupon** `WELCOME10`. Create draft, **Approve**. Call it **S-ORD** | Reserved 12. Its line reads 84 less 2.5% |
| `selling-delivered` | Delivery note on S-ORD, Delivering `5`, MAIN, Save, Approve, Dispatch. Then another, Delivering `7`, Save, Approve, Dispatch. (TC-SELL-009 does exactly this) | S-ORD DELIVERED |
| `selling-invoiced` | Bill the note for 5: Sales Invoices → New Invoice → Bill this delivery note → the note for 5, Bill `5`, Create draft, Approve. (TC-SELL-011 does this) | Total **483.21** |
| `selling-paid` | Receipt `241.60` Bank, apply `241.60` to that invoice; receipt `341.61` Bank, apply `241.61` (TC-SELL-013 does both). Then bill the note for 7 the same way: Bill `7`, Create draft, Approve | Second invoice **676.49**; Vijaya owes 679.91 with an advance of 97.58 |
| `loyalty-points` | **(HTTP)** `POST /api/v1/loyalty/adjust` with `X-Firm-ID` of QA03 and `{"customer_id": "<QA-C01's id>", "points": "200", "reason": "Goodwill credit for QA"}`. No screen credits points by hand | Masters → Loyalty lists Vijaya |
| `policy-firm` | Customers → **Settings**: When a customer reaches their limit **Warn, then block**; warn at `80`; block at `100`. Edit `QA-C02`: Credit limit `1000`. Sales Orders → New Order: `QA-C02`, MAIN, `QA-DET` `20` at `84`, Create draft, **do not approve** (**S-BLK**). Sales Invoices → **Sales stages** icon: Delivery note **off**. Sales Orders → New Order: `QA-C01`, MAIN, `QA-DET` `4` at `84`, Create draft, Approve (**S-FOUR**) | Run last in QA03, and switch both back afterwards (E, 08, step 10) |

### D5. Stock-in for QA03 to QA07

Opening Stock on the desktop has no unit cost, batch or expiry field, so
stock typed there is carried at nothing and the cost-of-goods journals the
cases look for would be zero. Bring stock in by a purchase instead:
purchase order from the firm's stock vendor, HO, MAIN, today; Submit,
Approve; one goods receipt accepting everything into MAIN; Complete.

| Firm | Vendor | Lines on the order (unit price) | On the goods receipt |
| --- | --- | --- | --- |
| QA03 | `QA-VS` | `QA-DET` 100 at 60 | Accepted 100 |
| QA04 | `QA-VS` | `QA-P` 50 at 60; `QA-Q` 200 at 60 | Accepted 50 and 200 |
| QA05 | `QA-VS` | `QA-P` 50 at 60 | Accepted 50 |
| QA06 | `QA-VP` | `QA-AMX` 10 at 60; `QA-AMX` 10 at 60; `QA-AMX` 10 at 60 (three lines); `QA-SHT` 3 at 60 | Line 1 Batch Number `QA-B1`, Expiry Date **today minus 30 days** (2026-08-26); line 2 `QA-B2`, **today plus 20 days** (2026-10-15); line 3 `QA-B3`, **today plus 400 days** (2027-10-30); line 4 accepted 3, no batch |
| QA07 | `QA-VE` | `QA-MIX` 5 at 2000 | Accepted 5 |

### D6. The rest of QA04, QA05, QA06 and QA07

| Preparation | Create |
| --- | --- |
| `territory-firm` (QA04) | C5 and its stock-in |
| `commission-firm` (QA04) | **Rules** (Sales → Commission → **Add rule**), all Paid on *Money collected*, Rate shape *Percentage of the value*, In force from `2026-04-01`, Status Active: (1) Applies to *Everyone (default)*, On *Everything sold*, rate `4`. (2) Applies to *Asha Sales*, On product `QA-P`, rate `15`. (3) Applies to *Bala Sales*, On *Everything sold*, **Slabs**: From `0` To `50000` Rate `2`; From `50000` To blank Rate `4`; How the slabs read *Each band at its own rate*; Earns nothing below `1000`; Extra when the target is met `2`. **Sales**, each: new order (Salesman blank; the route supplies it), Discount % `0`, Approve; delivery note for all, Approve, Dispatch; invoice from the note, Approve; Finance → Receipts → Record Receipt for the invoice's full total, Bank, applied to it: `QA-C4` 20 `QA-P` at 100 (2,360.00, Asha); `QA-C1` 30 `QA-Q` at 100 (3,540.00, Asha); `QA-C3` 40 `QA-Q` at 100 (4,720.00, Bala). **Targets** (Sales → Targets → New): Salesperson Asha Sales, From `2026-09-01` To `2026-09-30`, Target amount `1000`; Salesperson Bala Sales, same period, `100000`. Runs Monthly, Counts Invoiced |
| `compliance-firm` (QA05) | Three sales of `QA-P` at `100`, Discount % `0`, each order approved, noted, dispatched and billed as above. **Invoice A**: `QA-B2B`, quantity `10` (1,180.00), then a receipt of `1180.00` Bank applied to it. **Invoice B**: `QA-B2B`, quantity `5` (590.00), no receipt. **Invoice C**: `QA-B2C`, quantity `3` (354.00), no receipt. Then Sales → E-Invoice → **Register an invoice** → Invoice A → Register; again for Invoice B. Not C |
| `pharma-firm` (QA06) | D5's receipt, then two sales orders for `QA-RX`, both Approved: `QA-AMX` quantity `5` at `100`; `QA-SHT` quantity `10` at `100` |
| `electronics-firm` (QA07) | D5's receipt, then Inventory → Batch & Serial → **Serial Numbers** → New, five times: product `QA-MIX`, warehouse MAIN, branch HO, serial `QA-MIX-0001` to `QA-MIX-0005`, warranty start today (2026-09-25), warranty end today plus one year (2027-09-25) |

---

## E. Case by case

Where a case already gives a value, it is repeated so the table stands
alone. *Firm admin* is the administrator of the firm the section names.

### 02 Signing in and accounts (all in QA01 unless stated)

| Case | Sign in as | Values to type |
| --- | --- | --- |
| *Run order* | | Lock Target (qa): TC-SESS-003, 004, 005, 009, then 011, then 008. From TC-SESS-011 on, its password is `Handover-Passw0rd!`. TC-SESS-007 uses Lock Target Two (qa) and can run any time |
| TC-SESS-001 | platform admin | Search `QA`; expect `QA-ONE` in QA01 and `QA-TWO` in QA02 (among the other QA records; the point is that no QA01 row survives the switch) |
| TC-SESS-002 | `admin@qa01.test` | Idle more than 15 minutes; nothing to type |
| TC-SESS-003 | nobody, then the Target | `nobody.qa@qa.test` / `Wrong@Password1`; `lock.target@qa.test` / `Wrong@Password1` four times, then a fifth; then `QaTest@2026pw` |
| TC-SESS-004 | the Target, then `admin@qa01.test` | Lock as above; Users → Edit **Lock Target (qa)** → tick Clear login lock → Save; sign in `lock.target@qa.test` / `QaTest@2026pw` |
| TC-SESS-005 | `admin@qa01.test`, the Target | Untick Active; right password `QaTest@2026pw`, wrong `Wrong@Password1`. Expires at: **yesterday** (2026-09-24). Then clear Expires at |
| TC-SESS-006 | `admin@qa01.test` | New: Full name *Newbie qa*, `qa.newbie@qa.test`, `Welcome@123456`, Require password change **on**, QA01. New passwords `Short@1`, `LongEnoughPassw0rd`, `Newbie-Passw0rd!` |
| TC-SESS-007 | platform admin | Target is **Lock Target Two (qa)** (`lock.target2@qa.test`). New with the same email: Full name *Lock Target Reborn (qa)*, `QaTest@2026pw`, no firms, no roles |
| TC-SESS-008 | platform admin, the Target | Delete **Lock Target (qa)**; Status → Deleted → Restore; sign in `QaTest@2026pw` (or the password TC-SESS-011 left: `Handover-Passw0rd!`). Step 3: delete; New with `lock.target@qa.test`, Full name *Replacement (qa)*, `QaTest@2026pw`, no firms; then Restore the old one: refused |
| TC-SESS-009 | `admin@qa01.test`, platform admin | Search `qa`; untick Active on Lock Target (qa); tick it back afterwards |
| TC-SESS-010 | the QA01 admin, platform admin | Delete **Shared Member (qa)**: refused. HTTP step aims at `platform.member@qa.test` (needs B2) |
| TC-SESS-011 | platform admin | Reset password `Temp-Passw0rd!!` with Require a new password on; then `Handover-Passw0rd!` with it off |
| TC-PLAT-001..003 | platform admin | Nothing to type. TC-PLAT-003's firm list will show QA01 to QA07, QAR1, QAU1, QAU2 (once provisioned), QAF1 and QA-S1 |
| TC-PLAT-004 | `platform.member@qa.test` | Needs the developer's designation (B2) |
| TC-PLAT-005 | `admin@qa01.test` | Nothing |
| TC-ME-001 | `twofirm@qa.test`, Remember me ticked | Expect name *Two Firm User (qa)* |
| TC-ME-002, 003 | `twofirm@qa.test` | Choose QA02 → Save. **Run TC-ME-003 before TC-ME-002**, or set QA01 back as primary first: TC-ME-003 expects QA01 to be the primary |
| TC-ME-004 | `twofirm@qa.test` | **(HTTP)** The case lists no request; send `PUT /api/v1/me/primary-firm` with `{"firm_id": "<QA03's id>"}` (a firm they do not belong to) |
| TC-ME-005 | `twofirm@qa.test` | Nothing |
| TC-ME-006 | platform admin | Nothing |
| TC-ME-007 | `admin@qa01.test` | Nothing |
| TC-ME-008 | `twofirm@qa.test` | `Short@1`; `LongEnoughPassw0rd`; current `Wrong@Password1` with new `Str0ng-Passw0rd!` twice; current `QaTest@2026pw` with new `Str0ng-Passw0rd!` twice. **Run last** of the TC-ME cases: from here their password is `Str0ng-Passw0rd!` |
| TC-TIER-001..003 | `operator@qa.test` | Needs the developer's designation (B2) |

### 03 Users, roles, templates and hiring

**Run order for the people who change:** Manual Hire: TC-USER-001, then
TC-TMPL-005, then TC-AUDIT-004. Two Tier Hire: reset it before each of
TC-TMPL-006, TC-TMPL-007, TC-TMPL-008 and TC-RTIER-007 (as the platform
admin: Roles in every firm `VIEWER`, `CUSTOMER_SUPPORT`; Roles by firm,
QA01, `ACCOUNTANT`, `INVENTORY_MANAGER`). Shared Member: TC-USER-002,
006, 007, 008 first, then TC-RTIER-001, 002, 003, 004, 006, 008 in that
order. Outsider: TC-LOOK-001 to 004; Outsider Two: TC-LOOK-006. Night Desk:
TC-ROLE-005, 006, 007, 008, then 009 last.

| Case | Sign in as | Values to type |
| --- | --- | --- |
| TC-USER-001 | `admin@qa01.test` | Nothing |
| TC-USER-002 | `admin@qa01.test` | Nothing |
| TC-USER-003 | `admin@qa01.test` | Full name *In Firm qa*, `qa.infirm@qa.test`, `QaTest@2026pw` |
| TC-USER-004 | `admin@qa01.test` | *No Firm qa*, `qa.nofirm@qa.test`, `QaTest@2026pw`, Firms cleared; lookup `qa.nofirm`; then *No Firm Two qa*, `qa.nofirm2@qa.test`, Firms cleared, Roles in this firm `VIEWER` |
| TC-USER-005 | platform admin | Nothing |
| TC-USER-006..008 | `admin@qa01.test` (HTTP) | Shared Member's id, QA01's id, as the cases show |
| TC-USER-009 | `admin@qa01.test` | *Counter Hire qa*, `qa.counter@qa.test`, `QaTest@2026pw`, Job template Counter Sales |
| TC-LOOK-001 | `admin@qa01.test` | `t0`; `qa.outs`; `Outsider (qa)`; `qa`; `zzqq-nobody` |
| TC-LOOK-002 | `admin@qa01.test` | `qa.outs` → Outsider (qa) → Job template Counter Sales |
| TC-LOOK-003, 004 | `admin@qa01.test`, platform admin | Apply job template **Warehouse** |
| TC-LOOK-005 | `field@qa01.test`, then `admin@qa01.test` | HTTP `?q=fixtures`, `?q=`, `?q=qa.test&page=2&page_size=2` |
| TC-LOOK-006 | platform admin | `e`; then `qa.outs`: pick **Outsider Two (qa)** (the case says Outsider) → Add |
| TC-LOOK-007 | `admin@qa01.test`, platform admin | Nothing |
| TC-HIRE-001 | `admin@qa01.test` | On Source Seller (qa): empty; *Clone Test*, `not-an-email`, `Welcome@12345`; `qa.clone@qa.test`, `short` |
| TC-HIRE-002 | `admin@qa01.test` | *Clone Test qa*, `qa.clone@qa.test`, `Welcome@12345`; then sign in and set `CloneTest@2026x` |
| TC-HIRE-003 | `admin@qa01.test` | *Clone Test Two qa*, **`qa.clone2@qa.test`**, `Welcome@12345`; add `CUSTOMER_SUPPORT` |
| TC-HIRE-004 | `source.seller@qa.test` | HTTP body as the case gives |
| TC-TMPL-001 | `admin@qa01.test` | HTTP `{"name": "x"}` |
| TC-TMPL-002 | `admin@qa01.test` | Template code `qa-night-counter`, Job name *Night Counter*, Roles `CASHIER`, `BILLING_EXECUTIVE`; rename to *Night Counter renamed*. Then create `nightcounter@qa.test` (B4) for TC-TMPL-010 |
| TC-TMPL-003 | `admin@qa01.test` | *Job Hire qa*, `qa.jobhire@qa.test`, `QaTest@2026pw`, Counter Sales; *Hand Hire qa*, `qa.handhire@qa.test`, `QaTest@2026pw`, Roles `CUSTOMER_SUPPORT`, `VIEWER` |
| TC-TMPL-004 | `admin@qa01.test` | Pick `ACCOUNTANT`, then Read Only; save as *Read Only Hire qa*, `qa.readonly@qa.test`, `QaTest@2026pw` |
| TC-TMPL-005 | `admin@qa01.test` | On Manual Hire (qa): search `inventory`, then Counter Sales |
| TC-TMPL-006 | `admin@qa01.test`, platform admin | Reset Two Tier Hire first; Counter Sales |
| TC-TMPL-007 | platform admin | Reset first; Warehouse |
| TC-TMPL-008 | `admin@qa01.test` | Reset first; remove `ACCOUNTANT`, add `CASHIER` |
| TC-TMPL-009 | `field@qa01.test` | Nothing |
| TC-TMPL-010 | `admin@qa01.test` | Delete *Night Counter renamed*; open Night Counter Hire (qa) |
| TC-TMPL-011 | `admin@qa01.test` | **(HTTP)** The case lists no request; send `POST /api/v1/user-templates` with `{"code": "qa-bad", "name": "Bad", "role_ids": ["<PLATFORM_ADMIN role's id>"]}` |
| TC-TMPL-012 | platform admin | Nothing |
| TC-TMPL-013 | platform admin | `qa-t2-night`, *T2 Night*, Offered to QA02, Roles `CASHIER` |
| TC-TMPL-014 | platform admin | `qa-every-night`, *Every Night*, Roles `CASHIER`, Offered to blank; rename to *Every Night renamed*. HTTP `{"name": "y"}` |
| TC-TMPL-015 | `admin@qa01.test` | HTTP body as the case gives |
| TC-RTIER-001 | platform admin | Roles in every firm `VIEWER`; Roles by firm QA01 `SALES_MANAGER`, QA02 `CASHIER` |
| TC-RTIER-002..004, 006 | as each case says | Values in the case |
| TC-RTIER-005 | platform admin | *Global One qa*, `qa.global1@qa.test`, `QaTest@2026pw`, Firms QA01 and QA02, Roles in every firm `CUSTOMER_SUPPORT`; *Global Two qa*, `qa.global2@qa.test`, `QaTest@2026pw`, QA01, Job template Read Only |
| TC-RTIER-007 | `admin@qa01.test` | Reset Two Tier Hire first |
| TC-RTIER-008 | `admin@qa01.test`, platform admin (HTTP) | QA02 Only (qa)'s id |
| TC-ROLE-001 | `admin@qa01.test` | Nothing |
| TC-ROLE-002 | `admin@qa01.test` | Role code `qa-my-role`, Name *My Role qa*; search `FIRM_CREATE`, `PLATFORM_SETTINGS`, `VOID_INVOICE`, `AUDIT_LOG_VIEW`; tick `SALES_VIEW`, `CUSTOMER_VIEW` |
| TC-ROLE-003 | `admin@qa01.test` | `platform_admin`, Name *Reserved qa*; also `firm_admin`, `cashier`, `system_auditor` |
| TC-ROLE-004 | `admin@qa01.test` | Search `AUDIT_LOG_VIEW` |
| **Night Desk**, before TC-ROLE-005 | `admin@qa01.test` | Roles → New: Role code `qa-night-desk`, Name *Night Desk qa*, Permissions `SALES_VIEW`, `CUSTOMER_VIEW`, `RECEIPT_VIEW`, `RECEIPT_CREATE`. Then create `nightdesk@qa.test` (B4) holding it |
| TC-ROLE-005 | `admin@qa01.test` | Template code `qa-my-job`, Job name *Night Desk job*, Roles *Night Desk qa* |
| TC-ROLE-006 | `admin@qa01.test` | *Night Hire qa*, `qa.hire@qa.test`, `QaTest@2026pw`, Job template *Night Desk job* (`qa-my-job`) |
| TC-ROLE-007..009 | `nightdesk@qa.test` and `admin@qa01.test` | Untick `RECEIPT_CREATE` in 008; Delete in 009 |

### 04 Firms and configuration

**Run order in QAF1:** TC-FIRM-007, 013, 011, 010, 012, 009, 008. Each case
then finds the firm as its Expect assumes: 013 needs the books still shut,
011 expects the verdict still *Cannot post documents yet*, and 008 is last
because opening the books is what lets it post.

| Case | Firm | Values to type |
| --- | --- | --- |
| TC-FIRM-001 | QA01 | Nothing |
| TC-FIRM-002 | new | Name only *Created qa*; then Firm code `qa-s1`, Country `IN`, Currency code `INR`, Financial year start `2026-04-01`, With the other firms. Stored as `QA-S1` |
| TC-FIRM-003 | (HTTP) | Name *Refused qa*, and codes `QA01`, `BAD CODE`, `QA-Z` with country `IND`, `QA-Y` with `DATABASE`, `fx_nope`, `NOPE`. On an installed copy with no extra servers the last message ends *Configured profiles:* followed by none, not `REMOTE_A` |
| TC-FIRM-004 | QAU1 | Provision storage, twice |
| TC-FIRM-005 | QAU1 (HTTP) | Read it, PUT it back with `deployment_mode` `SHARED`. The message names QAU1's schema, which the server chose, not `fx_qa_u` |
| TC-FIRM-006 | QAU2 | Set up; HTTP the three posts; then Provision storage |
| TC-FIRM-007 | QAF1 | Nothing. The panel is titled *Set up QAF1* |
| TC-FIRM-008 | QAF1 | Open the books; HTTP it again |
| TC-FIRM-009 | QAF1 | Apply GST template; HTTP again, and with `{"template": "US"}` |
| TC-FIRM-010 | QAF1 | Wholesale |
| TC-FIRM-011 | QAF1 | Create head office and main warehouse; HTTP again |
| TC-FIRM-012 | QAF1 (opened from QA01) | Retail |
| TC-FIRM-013 | QAF1 | Customer code `C1`, name *Before books*, Business, INR. HTTP receipt `{"party_id": "<C1's id>", "settlement_date": "2026-09-25", "amount": "100.00", "method": "CASH"}` |
| TC-FIRM-014, 015 | QAR1 | TC-FIRM-015 step 3: change Rounding to `4000 Sales`, then back to `4900 Rounding`. Step 4 HTTP: any other ASSET account's id, for example `1200 Inventory`'s |
| TC-FIRM-016 | QA01 | Nothing |
| TC-FIRM-017 | QAR1, then QA07 | **Run last of all**: it deletes QAR1's two people and QAR1 itself. Step 4: aim the DELETE at **QA07**, whose administrator still exists; it is refused |
| TC-ISO-001 | QA01, QA02 | Search **`QA-SH`** rather than `QA` (QA01 and QA02 hold many QA records); expect only `QA-SHONE` in QA01 and only `QA-SHTWO` in QA02 |
| TC-ISO-002 | QA01, QA02 | Search *Isolation One qa*, then `QA` |
| TC-ISO-003 | QA01, QA02 | Register lists the *invoiced* sale's order for Fixture Buyer qa |
| TC-ISO-004 | QA01 | HTTP with QA02's id |
| TC-CONF-001 | QA01 | Rename SALES_INVOICE_DEFAULT to *Sales invoice default (QA)*; the Seller is `field@qa01.test` |
| TC-CONF-002 | QA01 | Document type Sales Invoice, code `QA-SI`, name *Check qa* |
| TC-CONF-003 | QA01 | Nothing |
| TC-CONF-004 | QAR1 | IMEI; then BARCODE |
| TC-CONF-005 | QA01 | `SALES_INVOICE`, `GST_18_LOCAL`, `1000`; then `SALES_INTERSTATE` |
| TC-CONF-006 | QAR1 | Firm-wide PACK to KG factor `2`; then a purchase order from `QA-V` (*Pack Supplier qa*), `QA-DET` quantity `10`, Purchase UOM *PACK — Pack*, unit price `100` |
| TC-FIELD-001 | QAR1 | `SHELF_NOTE` *Shelf note* TEXT PRODUCT; `PHARMA_NOTE` *Pharma note* TEXT PRODUCT Pharmacy; rule on `FXAMB` |
| TC-FIELD-002 | QAR1 | `BIN_CODE` *Bin code* mandatory; HTTP products `NOBIN` *No bin* and `BIN1` *Bin one* with value `A-1`. **Afterwards untick mandatory on BIN_CODE**: while it is on, every product saved in QAR1 needs a bin code, and TC-FIELD-003 to 011 save products |
| TC-FIELD-003 | QAR1 | `COLD_CHAIN_ID` *Cold chain id*; product `CH1` *Chilled One qa* in Fixture Chilled, value `CC-0001`; product `AM1` *Ambient One qa* in Fixture Ambient |
| TC-FIELD-004 | QAR1 | `RX_CLASS` *Rx class* Pharmacy; HTTP product `RX0` *Rx zero* |
| TC-FIELD-005 | QAR1 | `WS_GRADE` *Wholesale grade*; product `GR1` *Graded One qa* value `A`; profile to Retail, then back to Wholesale |
| TC-FIELD-006 | QAR1 | `LOT_NOTE` *Lot note*; product `LN1` *Lot Note One qa* value `abc`; change type to NUMBER |
| TC-FIELD-007 | QAR1 | `DRUG_LICENCE_NO` *Drug licence no* CUSTOMER; customer `DLC` *Licence Holder*, licence `DL-4471`; phone `+919800000001` |
| TC-FIELD-008 | QAR1 | Make `DRUG_LICENCE_NO` mandatory (edit the one from TC-FIELD-007); customer `QA-DL2` *Licence Missing qa*, licence left empty; HTTP customer `QA-DL3` *Licence Missing Two qa*, BUSINESS, INR. **Afterwards make it optional again**, or every later customer in QAR1 is refused |
| TC-FIELD-009 | QAR1 | `SUPPLIER_TIER` *Supplier tier* NUMBER VENDOR; on vendor `QA-V`: `2` |
| TC-FIELD-010 | QAR1 | `FSSAI_LICENCE` BRANCH: `12426001000123` on HO; `DOCK_COUNT` WAREHOUSE: `4` on MAIN |
| TC-FIELD-011 | QAR1 | `STORAGE_TEMPERATURE` *Storage temperature*, allowed values `Ambient, Chilled, Frozen`; product `PEAS` *Frozen Peas qa*; HTTP value `Cold` |
| TC-FIELD-012 | QAR1 (HTTP) | Nothing more |
| TC-FIELD-013 | QA01 as QASH1, QA02 as QASH2 | `QA_PACK_NOTE`, TEXT, UOM; unit `BAG`; value `QASH1 note`. Delete the definition at the end |
| TC-FIELD-014 | QA01, QA02 | `QA_SHARED_CHECK`, TEXT, CUSTOMER. Delete it at the end |

### 05 Masters

| Case | Firm | Values to type |
| --- | --- | --- |
| TC-CUST-001 | QA01 | Phone `+919800000199` |
| TC-CUST-002 | QA01 | Code `QA-GEO`, name *Place Check qa*, Business, INR; address country India, state Tamil Nadu, district Chennai, city Chennai; line 1 *3 Place Check Road*; PIN `600001`. Expect the text to read Chennai, Tamil Nadu, IN |
| TC-CUST-003 | QA01 | HTTP body as the case gives; the Seller is `field@qa01.test` |
| TC-CUST-004 | QA01 | Credit limit `1`; order for `QA-CM`, line **`QA-PS`** quantity `2` at `100`. Afterwards put the credit limit back to `50000` for the cases that follow |
| TC-CUST-005 | QA01 | Statement for 2026-04-01 to 2027-03-31 on **`QA-C`** |
| TC-CUST-006 | QA01 | Segment *Wholesaler qa*; then Remove `QA-WHL` |
| TC-MAST-001 | QA01 | On `QA-V`: phone `+919800000299` |
| TC-MAST-002 | QA01 | New `QA-CAT2` *Category Two qa*, `QA-TYP2` *Type Two qa*; on `QA-V`: category *Category qa*, type *Type qa* |
| TC-MAST-003 | QA01 | Nothing |
| TC-MAST-004 | QA02 | Rename `QA-BR` to *Kept Branch renamed* |
| TC-MAST-005 | QA02 | Rename `QA-WH` to *Kept Warehouse renamed* |
| TC-MAST-006 | QA02 | Save the two files below with Notepad, as **UTF-8**, named `branches-clash.csv` and `branches-clean.csv`. Import the clash one, then the clean one |
| TC-MAST-007 | QA02 | In the sample file change `BR_NORTH` to `QA-NORTH` |
| TC-MAST-008 | QA01 | Barcode `8906012345678` |

`branches-clash.csv`:

```
code,name,address_line1,currency_code,status
QA-I1,Import 1 qa,1 Import Road,INR,ACTIVE
QA-I2,Import 2 qa,2 Import Road,INR,ACTIVE
QA-I3,Import 3 qa,3 Import Road,INR,ACTIVE
QA-I4,Import 4 qa,4 Import Road,INR,ACTIVE
QA-BR,Clash qa,x,INR,ACTIVE
```

`branches-clean.csv` is the same without the last line.

Screen checks (05-S01 to 05-S14): where a screen offers **New**, type code
`QA-SC01`, `QA-SC02` and so on and the name *Screen check 01*, and so on,
plus any field the form marks required, taking values from the nearest row
in C. Delete them afterwards where the screen allows it.

### 06 Purchasing (QA01; run in the order of D1)

| Case | Values to type |
| --- | --- |
| TC-BUY-001 | Vendor `QA-V`, branch HO, warehouse MAIN, today; `QA-B` quantity `10`, unit price `100` |
| TC-BUY-002 | Line remark *Deliver to back gate*; order remarks *Confirmed by phone with Fixture Supplier qa* |
| TC-BUY-003 | Accepted `4`, MAIN; then `6` |
| TC-BUY-004 | Cancel the receipt of 4 |
| TC-BUY-005 | Needs D1 step 7 first (supplier invoice `QA-SUP-001`, 708.00) |
| TC-BUY-006 | On **PO-2**'s receipt of 6 (`QA-B2`): Returning `2`, Damaged |
| TC-BUY-007 | Nothing |
| TC-BUY-008 | Paid to `QA-V`; Amount `708.00`; Method Bank; instrument reference `NEFT-QA-0708`; Oldest first |

The walkthrough's own buying (W19 to W29): supplier invoice numbers
`QA-V1-INV-001` for the receipt of 6 and `QA-V1-INV-002` for the receipt
of 4; the payment of `1180.00`, Bank, instrument reference `NEFT-QA-1180`.

### 07 Inventory

| Case | Firm | Values to type |
| --- | --- | --- |
| TC-STOCK-001 | QA01 | Filter Product `QA-B`; type `GOODS_RECEIPT` |
| TC-STOCK-002 | QA01 | Row `QA-P` / MAIN → Transfer: quantity `3`, Move it to *QA-W2 - Overflow qa*, reference `QA-TRF`; then quantity `999` |
| TC-STOCK-003 | QA01 | Row **`QA-P3`** / MAIN → Write off: `1`, reason Damage, reference `QA-WO`; Quarantine Hold back `2` ref `QA-QH`; Release `2` ref `QA-QR`; Hold back `999` |
| TC-STOCK-004 | QA01 | Open Count: HO, MAIN, today; on **`QA-P4 - Count Item qa`** type Counted `49`; every other line blank |
| TC-STOCK-005 | QA06 | Search Batches `QA-B` (finds `QA-B1` to `QA-B3`); deliver the order for 5 `QA-AMX` |
| TC-STOCK-006 | QA06 | Deliver the order for 10 `QA-SHT` |
| TC-STOCK-007 | platform admin: QA01, then QA06 | Filter any product in QA01, for example `QA-P` |
| TC-STOCK-008 | QA07 | Search `QA-MIX-` |

Walkthrough W32 and W34: Transfer `2` from MAIN to *STORE2 - Back Store*,
reference `QA-W32`, and back with reference `QA-W34`.

### 08 Selling (QA03)

**Run order in QA03.** The cases share one sale, so take them in this
order and every Expect figure holds:

1. TC-SELL-001, 002, 003, 004, 005, 006; TC-INCENT-001, 002, 004.
2. Build **S-ORD** (D4, `selling-ordered`). TC-SELL-007, TC-INCENT-003,
   TC-SELL-008.
3. TC-SELL-009 (builds `selling-delivered`), TC-SELL-010.
4. TC-SELL-011 (builds `selling-invoiced`), TC-SELL-012.
5. TC-SELL-013; then bill the note for 7 (D4, `selling-paid`);
   TC-COMP-007; TC-FIN-002, 004, 005; TC-SELL-014.
6. TC-SELL-015 and TC-SELL-016, against the **invoice for 7**.
7. TC-INCENT-005 (loyalty), also on the **invoice for 7**.
8. Build **S-PF** and run TC-SELL-017.
9. TC-CONC-002, 004, 005.
10. Build `policy-firm` (D4); TC-FIN-008, TC-FIN-009; then set the credit
    policy back to **Warn** and switch the Delivery note stage back **on**.

Each case was written against a fresh firm, so a return, a credit note and
a loyalty redemption were each made on the invoice for 5 while it still
owed 483.21. By hand they share one firm, and the invoice for 5 is paid off
by TC-SELL-013. Running them on the **invoice for 7**, which still owes
money after TC-SELL-014, keeps what they check: the per-unit credit
(193.28 for 2), the tax on a credit note (59.00 for 50), and the outstanding
falling by the amount credited. The refusal texts then name 7 and 573.30
where the cases say 5 and 409.50; the table says so row by row.

| Case | Values to type |
| --- | --- |
| TC-SELL-001 | Customer `QA-C01`; `QA-DET` quantity `12`; Discount % blank |
| TC-SELL-002 | `QA-C01`; `QA-DET` `18`; blank |
| TC-SELL-003 | `QA-C02`; `QA-DET` `18` |
| TC-SELL-004 | `QA-C02`; `QA-DET` `30`; then Discount % `0` |
| TC-SELL-005 | `QA-C02`; `QA-DET` `12`; accept reason *Customer confirmed by phone*; order date today |
| TC-SELL-006 | New Order `QA-C01`, MAIN, `QA-DET` `12`, Discount % blank, Coupon `WELCOME10`; then `WELCOME10B`; then `NOSUCHCODE`. Leave this draft alone afterwards |
| TC-SELL-007 | Filter `QA-DET` (reads S-ORD) |
| TC-SELL-008 | Hold S-ORD, reason `awaiting cheque`; delivery note on it; Release |
| TC-SELL-009 | Delivering `5`, MAIN; then the remaining `7` |
| TC-SELL-010 | Nothing |
| TC-SELL-011 | Bill `6`, then `5` |
| TC-SELL-012 | How many copies `2`; labels as prefilled |
| TC-SELL-013 | Receipt `241.60`, Bank, reference `NEFT-QA-2416`, Apply `241.60`; receipt `341.61`, Bank, reference `NEFT-QA-3416`, Apply `241.61` |
| TC-SELL-014 | Apply to an invoice: the invoice for 7, Amount `97.58`; then `5`. Reverse the 241.60 receipt, reason *Cheque returned unpaid* |
| TC-SELL-015 | Against the **invoice for 7**; Line 1; Taken back into MAIN; Quantity `9` (refused: *Only 7.0 went out on this line.*), then `2` (193.28 credited, as the case says) |
| TC-SELL-016 | The **invoice for 7**; Line 1; Reason Rate difference; Credit, before tax `50` (reads `59.00 (tax 9.00)`); then **`600`** instead of 400, because this line was charged 573.30: refused, naming 573.30 charged and what is already credited |
| TC-SELL-017 | First build **S-PF**: New Order `QA-C01`, MAIN, `QA-DET` `4` at `84`, Create draft, Approve. Proforma → New → S-PF → Raise → Issue. Then Cancel S-PF, reason *Customer postponed* |

### 09 Pricing and incentives

| Case | Firm | Values to type |
| --- | --- | --- |
| TC-INCENT-001 | QA03 | On `STANDING`: Add product `QA-DET`, From qty `25`, Discount % `8`; quotation `QA-C01`, `QA-DET` `30` |
| TC-INCENT-002 | QA03 | On `BULK5`: Description *Bulk discount for 25 and over* |
| TC-INCENT-003 | QA03 | Nothing (reads S-ORD's claim) |
| TC-INCENT-004 | QA03 | New Order `QA-C01`, MAIN, `QA-DET` `60` at `84` |
| TC-INCENT-005 | QA03 | Needs the HTTP adjustment (D4). Use points `100` on the **invoice for 7**; then `5000`. The balance reads 200 plus what the two invoices earned (about 23, at 2 per 100 of 483.21 and 676.49), and the refusal names what is left; the outstanding falls by exactly 100.00 rather than to 383.21, because this invoice is not the one the case was written against |
| TC-INCENT-006 | QA04 | Collected from `2026-04-01` to `2026-09-30`; Targets → Achievement for September 2026 |
| TC-INCENT-007 | QA04 | Accrue period September 2026 (2026-09-01 to 2026-09-30); Pay on today from `1000 Cash`; Cancel Asha's |
| TC-INCENT-008 | QA04 | Sign in as `asha@qa04.test` |

### 10 Territory (QA04)

| Case | Values to type |
| --- | --- |
| TC-TERR-001 | Nothing |
| TC-TERR-002 | Date Monday `2026-09-21` |
| TC-TERR-003 | Dates `2027-01-12`, `2026-10-13`, `2026-10-20` |
| TC-TERR-004 | Route `QA-R-N1`; tick On no route yet; add `QA-SN` |
| TC-TERR-005 | New Order for `QA-C4`, MAIN, Salesman Bala Sales, `QA-P` `1` at `100`; then Asha Sales; then blank. Leave the three drafts; they are never approved |

Nothing in TC-TERR-001 to 005 posts, so they may run before or after the
commission sales. TC-TERR-004 edits `QA-R-N1`'s round and puts it back;
make sure it reads Revise Check qa, then Classic Stores qa, before the
commission sales take their salesman from it.

### 11 Compliance

| Case | Firm | Values to type |
| --- | --- | --- |
| TC-COMP-001 | QA05 | This month (September 2026) |
| TC-COMP-002 | QA05 | Cancel Invoice A; cancel Invoice C, reason *Billed to the wrong buyer* |
| TC-COMP-003 | QA05 | Nothing |
| TC-COMP-004 | QA05 | Nothing |
| TC-COMP-005 | QA05 | Invoice C |
| TC-COMP-006 | QA05 | Invoice B: Distance `120`, Moving by Road, vehicle blank; then `TN01AB1234`. Cancel bill reason *Vehicle changed* |
| TC-COMP-007 | QA03 | Nothing; run at step 5 of the QA03 order, before TC-SELL-014 reverses a receipt |

TC-COMP-002 cancels Invoice C, which TC-COMP-001, 003 and 005 need; run it
after them.

### 12 Finance and reports

| Case | Firm | Values to type |
| --- | --- | --- |
| TC-FIN-001 | QAR1 | Group REV, code `9999`, name *Manual test account*, type EXPENSE; then group EXP · Direct Expenses |
| TC-FIN-002 | QA03 | Period September 2026 (P06) on all three |
| TC-FIN-003 | QAR1 | Period June 2026; date `2026-06-15`; reference `MT-CLOSE-1`; `5000 Purchases` Dr `100`; `1000 Cash` Cr `100`; any journal and voucher type |
| TC-FIN-004 | QA03 | Search `SI-2026-2027-000001`, `DN-`, `RC-2026-2027-000001`, `TCS-RC-2026-2027-000001` |
| TC-FIN-005 | QA03 | Nothing. The purchase reports are **not** empty here: they hold the stock-in order of D5 |
| TC-FIN-006 | QA01 | Search `QA-PM` |
| TC-FIN-007 | QAR1 | Cost centre `SALES` *Sales* (twice); profit centre `NORTH` *North*; journal line on `5000` with cost centre SALES, `5000 Purchases` Dr `250`, `1000 Cash` Cr `250`, reference `MT-CC-1`, today |
| TC-FIN-008 | QA03 | Approve **S-BLK** |
| TC-FIN-009 | QA03 | Bill **S-FOUR**: Sales Invoices → New → bill the order, `4` |
| TC-FIN-010 | QA01 | Ctrl+K `CUSTOMER_VIEW` |
| TC-FIN-011 | platform admin | Nothing |
| TC-CASH-001 | QA01 | Sign in as `cashier@qa01.test` |
| TC-CASH-002 | QA01 | `QA-TI`; `Till Customer`; `zzzz-nobody`; then `QA-TILL`, amount `100`, method Cash. `QA-TILL` owes nothing, so the 100 is taken as an advance |
| TC-CASH-003 | QA01 | Sign in as `accounts@qa01.test` |
| TC-CASH-004 | QA01 | Nothing |
| TC-AUDIT-001..003 | | Nothing |
| TC-AUDIT-004 | QA01 | Customers `QA-A` *Audit Before qa* and `QA-B` *Audit After qa* (customers, unrelated to the product `QA-B`); Apply Counter Sales on Manual Hire (qa); filter `user_template.applied` |
| TC-AUDIT-005, 006 | QA01 | Nothing |

### 13 Cross-cutting

| Case | Firm | Values to type |
| --- | --- | --- |
| TC-PERM-001..003 | QA01 | Sign in as `field@qa01.test`; HTTP bodies as the cases give |
| TC-CONC-001 | QA01 | On `QA-CM`: A `+919800000111`, B `+919800000122` |
| TC-CONC-002 | QA03 | Draft order `QA-C01`, MAIN, `QA-DET` `1` at `84`. Remarks A *Edited on A*, B *Edited on B*; product `QA-DET` Description A *Edited on A*, B *Edited on B*; price list `STANDING` Name A *Standing A*, B *Standing B*. Set the name back to *Standing* afterwards |
| TC-CONC-003 | QA01 | `QA-CM`, no change |
| TC-CONC-004 | QA03 | Draft order `QA-C01`, `QA-DET` `1` at `84`; Approve on A and B |
| TC-CONC-005 | QA03 | `WELCOME10B` Total claims allowed `1`; two drafts `QA-C01`, `QA-DET` `1`, Coupon `WELCOME10B` |
| TC-CONC-006 | QA04 | Accrue September 2026 on A and B. Run it **before** TC-INCENT-007, then **Cancel** both DRAFT payouts it made, so TC-INCENT-007 starts from an empty period |
| TC-GRANT-001 | QA01 | The approved invoice of the *invoiced* sale; line **Sold Item qa** (the case says Fixture Product qa); Credit before tax `100`; leave it a draft |
| TC-GRANT-002, 003 | QA01 | Nothing |
| TC-GRANT-004 | QA01 | Scheme is running on, Minimum to redeem `50`, Points expire off; then off |
| TC-GRANT-005 | QA01 | Sign in as `salesmgr@qa01.test` |
| TC-GRANT-006..008 | QA01 | Nothing |

---

## F. The walkthrough, step by step

The walkthrough gives most of its own values; these fill the rest.

| Step | Values |
| --- | --- |
| W1 | Display name `QA Traders` only |
| W2 | As A2, column QA01 |
| W4 | Wholesale |
| W9 | Full name *QA01 Admin (qa)*, `admin@qa01.test`, `QaTest@2026pw`, Require password change off, Job template Firm Administrator, Firms QA01 |
| W12 | C1, `STORE2` |
| W13 | C1, `QA-P1`. There is no category to choose unless one was made by HTTP; leave it blank |
| W14, W15 | C1, `QA-V1`; new phone `+919840011002` |
| W16, W17 | C1, `QA-C1`; new phone `+919841022002` |
| W19 | Today; `QA-P1` `10` at `100` |
| W22, W24 | Accepted `4`; then `6` |
| W25, W27 | Supplier invoice numbers `QA-V1-INV-001` (the receipt of 6), `QA-V1-INV-002` (the receipt of 4), dated today |
| W28 | `1180.00`, Bank, reference `NEFT-QA-1180`, Oldest first |
| W32, W34 | `2`, references `QA-W32`, `QA-W34` |
| W35 | `QA-C1`, `QA-P1` `4`, `150` |
| W36 | Accept reason *Customer confirmed by phone* |
| W40 | Reason `awaiting cheque` |
| W43 | Delivering `4`, MAIN |
| W46, W47 | Bill `5`, then `4` |
| W52 | `708.00`, Bank, reference `NEFT-QA-0708W`, apply `708.00` |
| W58, W59 | Quantity `5`, then `1` |
| W62, W63 | Rate difference, `50`; then `1000` |
| W70 | *Counter Sales (qa)*, `counter@qa01.test`, `QaTest@2026pw`, Require password change **on**, Counter Sales. W71's new password `Counter-Passw0rd!` |
| W72 | *Field Sales (qa)*, `field@qa01.test`, `QaTest@2026pw`, Require password change off, Field Sales |

---

## G. Counts

- **Firms:** 11 prepared (QA01 to QA07, QAR1, QAU1, QAU2, QAF1), plus
  `QA-S1` which TC-FIRM-002 makes.
- **People:** 37 prepared accounts (the platform administrator and the two
  that need the developer, 12 in QA01 by job, and 22 named people), plus
  13 that the cases create themselves.
- **Masters:** 83 master records in C1 to C8: 4 warehouses and branches
  beyond the set-up panel's, 3 product categories, 4 customer groups,
  2 vendor categories and types, 9 vendors, 16 products, 19 customers,
  2 price lists, 4 promotions and 2 coupons, 1 route type, 6 territories
  and routes, 9 beat plans, 1 packaging level and 1 conversion rule; plus
  9 places, and the TCS and loyalty settings of QA03.
- **Cases:** all 225 detailed cases and the 76 walkthrough steps have a
  row or are covered by a preparation.

---

## H. Noticed while compiling

Written down, not fixed: the generated files are regenerated from their
sources rather than edited.

**Things with no screen yet.** These can only be done by HTTP or by the
developer, which is why the cases that need them may be `Blocked`:

1. **Product categories cannot be created on the desktop.** The product
   form offers a Category dropdown but nothing adds to it. Needed for
   `QA-PM` (TC-MAST-003) and QAR1's `FXAMB` and `FXCHL` (the TC-FIELD
   cases). Walkthrough W13's *Create a category when the form asks for one*
   cannot happen; the category is optional, so leave it blank.
2. **A promotion cannot be made coupon-only on the desktop.** The
   Promotions dialog has no such switch, so `WELCOME` needs HTTP (C4).
3. **Loyalty points cannot be credited by hand on the desktop.** The
   adjustment route exists but no screen calls it (TC-INCENT-005).
4. **The platform designation has no route**, by design (B2).
5. **Opening Stock on the desktop takes no unit cost, batch or expiry.**
   Stock typed there is valued at nothing, so this sheet brings stock in by
   purchase (D5). The same gap means an installed copy's first stock count
   carries no value.

**Generator and wording glitches in the generated files.**

6. `02_SIGN_IN_AND_ACCOUNTS.md`, TC-PLAT-003, line 179: *QA01, QA02, QA01,
   ELEC01, MEDI01, FOOD01*. QA01 appears twice; the source said TEST01,
   TEST02 and a third firm.
7. `02`, TC-ME-004: the **Steps (HTTP)** line has no request under it. The
   request is in E, 02.
8. `03`, TC-TMPL-011: no Steps at all, only an Expect. The request is in
   E, 03.
9. *a password you choose* appears where the developer's fixture printed a
   fixed password (TC-SESS-003, 004, 008, TC-ME-008, TC-ROLE-006). It
   means the prepared account's password: `QaTest@2026pw` here.
10. Several preconditions describe the wrong preparation for the case, a
    side effect of one sentence per preparation: TC-CUST-002 and 003 carry
    TC-CUST-001's full description of `QA-CM`; TC-MAST-004 to 007 all say
    *two import files*, TC-STOCK-005 to 007 all say *two orders* and
    *batches*; TC-STOCK-007's precondition describes a Pharmacy firm when
    the case only needs the platform admin to switch firms.
11. `07`, TC-STOCK-005 step 1 says search Batches for `QA-B`: correct only
    because the fixture named the batches `QA-B1` to `QA-B3`, which reads
    like the purchasing product `QA-B`. This sheet keeps those batch
    numbers so the case reads as written.
12. `03`, TC-HIRE-003 reuses the email `qa.clone@qa.test` that TC-HIRE-002
    just used. Use `qa.clone2@qa.test`.
13. `06`, TC-BUY-005 says a purchase invoice cannot be raised from the
    desktop (BACKLOG 31.9). The desktop now has **Purchase Invoices → New**
    with a Goods Receipt picker (the walkthrough's W25 uses it); the note is
    out of date.
14. `04`, TC-FIRM-003 expects *Configured profiles: REMOTE_A*: that is the
    developer's machine. An installed copy has no extra server profiles.
15. `04`, TC-FIRM-005 expects the message to name `fx_qa_u`, the fixture's
    schema name; an installed copy names the schema the server chose.
16. `09`, TC-INCENT-005 step 1 expects Vijaya to hold exactly **200**
    points, but the invoice of 483.21 also earns 9.66 at 2 per 100
    (points are earned when an invoice is approved). Expect about 209.66
    in a fresh run.
17. `04`, TC-ISO-002 is titled *Two firms in their own schemas*. With QA01
    and QA02 both sharing the store, it checks the same thing as
    TC-ISO-001; the separate-schema case is covered by QAR1.
18. **The GST template now makes nine rules, not six.** Walkthrough W7 and
    TC-FIRM-009 and 014 expect *8 tax profiles and 6 rules*; the template
    in the code creates the six sales rules plus three for inter-state
    purchases. Record the message the screen shows.
19. `04`, TC-MAST-004 expects the branch's **PAN** to survive a rename, but
    the desktop branch form has no PAN field; only a branch made by HTTP
    carries one. Check the other fields.
20. `12`, TC-CASH-002's precondition asks for *a customer with an
    outstanding invoice*; the developer's preparation made the customer
    only, and nothing in the case uses an invoice.
21. `12`, TC-FIN-005 says the purchase reports are empty (*this store bought
    nothing*). On this sheet QA03 buys its opening stock (D5), so they each
    list that one order.
22. The walkthrough's GST number `33ABCDE1234F1Z5` does not have a valid
    check character (a valid one ends `Z7`). The product accepts it
    because it checks GST numbers for uniqueness only; kept so W55 reads as
    written.
23. The suite's Expect for TC-SELL-012 says *the prepared firm and customer
    carry no GSTIN*. On this sheet QA03 has a GST number, so it prints on
    the bill; Vijaya still has none.
24. `09`, TC-INCENT-002 expects the pane to read *Applies when:
    line_quantity GREATER_OR_EQUAL 25.0000*. The desktop now words
    conditions in plain English, so expect *Quantity on the line is at
    least 25*.
