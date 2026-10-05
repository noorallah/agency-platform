# QA test suite: every module, every role

The complete manual test suite for an **installed** copy of the Agency
Platform, one file per module area. Each file stands alone, so QA can take
one module at a time, and each has a PDF beside the installer.

**This suite is for release 1.3.0 and is the first end-to-end test pass of it.**
Release 1.3.0 includes 1.2.0, which was never shipped, so nothing in it has
been through a tester's hands yet: the light menu, the Settings page, favourites,
My preferences, the whole backlog build of 2026-10-02 and 2026-10-03, and the
agency's branding are all new to this pass. Every menu path in the files is
the 1.3.0 menu: `Sell > Quotations` is the **Sell** drop-down on the menu bar,
`Sell > All Sell screens > Documents > Proforma` is a screen that is not daily
work, `Sell > Returns & notes > Credit Notes` is the short list beside the daily
one, and the gear at the right of the bar opens **Settings**
(`Settings > Firm > Numbering Series`, `Settings > Set up > Pricing > Price
Lists`, `Settings > Platform > People > Users`).

Generated on 2026-10-05 from the product's own sources. The detailed cases
come from `docs/INDEPENDENT_TEST_CASES.md`, whose every expectation was
driven against a running server. The screen checks and the role matrix come
from the application's screen catalogue and role seed. The files are
regenerated from those sources rather than edited by hand, so a fix belongs
in the source.

**Cases added on 2026-10-02** (the return outcome and supplier refunds, a
return off a paid bill, input credit and supplier GST type, GSTR-2B, the
dispatch policy, choosing batches, reorder from sales, the debit note to a
customer, the tax calendar, one quantity picture per order line, the GST
Documents settings and rate-includes-GST on orders and quotations) were
written from the code and have not all been driven against a running server;
those that say so in their own text have not.

**Cases added on 2026-10-03** cover the 95 backlog items built in Waves 1 to
3, so that one manual pass reaches every one of them: enquiries to
quotations, counter billing, picking and loading sheets, early-payment
discount and overdue interest, pending outlets, price levels, the new offer
kinds, bulk coupons, principal claims and sharing documents by hand
(`08_SELLING`, `09_PRICING_AND_INCENTIVES`); supplier rates and catalogue,
requisitions, amended orders, inspection, bill tolerance and budgets, payment
runs, supplier ratings and rebates, landed cost and free goods
(`06_PURCHASING`); stock transfers as documents, repacking, kits, expiry
rules, count plans, adjustment approval, evidence, lapsing reservations and
labels (`07_INVENTORY`); principals and brands, merging duplicates, customer
bank accounts, linked parties and codes from a series (`05_MASTERS`); GST
checks, filed returns and amendments, quarterly filing, rule 42, branch GSTINs
and the rule on each line (`11_COMPLIANCE`); bank reconciliation,
post-dated cheques, cheque printing, TDS challans and 194Q, the cash flow
statement, Tally export, approvals by level and the bell
(`12_FINANCE_AND_REPORTS`); and firm-owned and document custom fields
(`04_FIRMS_AND_CONFIGURATION`). **All of them were written from the code and
the build notes and none has been driven against a running server**; say so in
the result notes, and treat a failure as possibly the case's mistake until it
is settled. Nineteen cases that had been added to these files by hand on
2026-10-02 (TC-MAST-009 and 010, TC-BUY-017 and 018, TC-SELL-022 to 026,
TC-TERR-006, TC-COMP-009 to 019) are now also in
`docs/INDEPENDENT_TEST_CASES.md`, so regenerating no longer drops them.

**Cases added on 2026-10-05** cover the purchasing build (backlog 86, PG-1 to
PG-14) and the selling build (backlog 87, SG-1 to SG-9), both part of release
1.3.0: **TC-BUY-029 to TC-BUY-090** (62 cases, `06_PURCHASING`) and
**TC-SELL-036 to TC-SELL-087** (52 cases, `08_SELLING`). **These features have
not been through a full test suite, a CI run or a hand test, and none of the
114 cases has been run**: they were written from the code and its automated
tests. Say so in the result notes, and treat a failure as possibly the case's
mistake until it is settled. Each stands alone and reads nothing another case
left. Three warnings on the order to run them in:

- **Only TC-BUY-086 and TC-BUY-088 switch a firm-wide setting**: Settings >
  Buying > Purchase Settings > **Buying stages** with **Purchase order** off,
  which takes **Goods receipt** off with it. They type an import bill and a
  capital-goods bill with no order. **Run those two last**, when nobody else
  is buying in the firm, or in a firm of its own, and switch both back on
  afterwards. The other import and capital-goods cases (TC-BUY-070 to 078,
  087, 089, 090) run on the full chain: the purchase order carries the
  currency and rate, and the order and receipt lines a **Capital goods**
  tick.
- **The TDS cases (TC-BUY-043 to 048) each need a supplier of their own with no
  other bill or payment in the financial year.** Use a new supplier each time
  one is run.
- **The counter cases** (walk-in, hold and recall, shifts: TC-SELL-040 to 045
  and 064 to 072) need Settings > Selling > **Sales Stages** with *Sales
  order* and *Delivery note* both off; switch both back on afterwards.

The new screens also have screen checks: Requests for quotation, Rate
contracts, Supplier schemes and Bills of entry (`06_PURCHASING`), Counter
Shifts and Customer Rebates (`08_SELLING`), Transporters (`10_TERRITORY`),
and Collection Sheet, Payment Promises and the four Fixed assets screens
(`12_FINANCE_AND_REPORTS`). The eight defects found while the cases were
written (D-SELL-51, D-SELL-52 and D-BUY-35 to D-BUY-40) were fixed on
2026-10-05, and the cases were corrected to what the application does now:
the shift cases sign in as a Counter Sales user whose bills a manager
approves (TC-SELL-067, 068, 087), and TC-BUY-086 to 090 were added. Two
defects found on the way are open and not yet driven, D-BUY-41 and D-CMP-23
in `docs/DEFECTS.md`: do not raise a debit note or a purchase return against
a foreign-currency bill, and do not expect GSTR-2B matching, rule 37 or rule
42 to convert one.

**What 1.2.0 changed (carried into 1.3.0): the menu.** Each drop-down now shows daily work only; every other screen is behind **All <area> screens** at its foot, under the same group name, so a path such as *Sell > Insight > Sales Analysis* is now *Sell > All Sell screens > Insight > Sales Analysis*. **Returns & notes** opens the returns and notes. The **Admin** area has left the bar: Users, Roles, Firms, Audit Logs and Backups are under **Settings > Platform** (People, Firms, Agency, System); the set-up lists (price lists, promotions, territories, customer groups, product categories, units, places) are under **Settings > Set up**. Ctrl+K finds any screen by name. Cases TC-ME-009 to TC-ME-013 (`02_SIGN_IN_AND_ACCOUNTS`) cover the new menu, Settings > Set up, favourites and My preferences, which replaces the *Primary firm* menu entry. For one tester's book across every module, with sample data and what to check after each action, see `docs/QA_TEST_BOOK.md`. For a module-by-module reference (what to configure, which screens to open, what to verify elsewhere, known limits) see `docs/QA_MODULE_REFERENCE.md`.

**What 1.3.0 adds: the agency's branding.** The sign-in screen, the header and the first sign-in now show the agency's own name, tagline and logo, set on a Branding page of a fresh server install or under **Settings > Platform > Agency > Branding**. Cases TC-ME-014 to TC-ME-018 (`02_SIGN_IN_AND_ACCOUNTS`) cover the sign-in screen, More help and the offline fallback, the first-run *Set up your agency* dialog, the Branding settings page and the header; the installer page is in `docs/INSTALLER_QA_CHECKLIST.md` (A4a and section F). **Written from the code and not yet driven against a running server.** They are in `docs/INDEPENDENT_TEST_CASES.md` too, so regenerating keeps them.

## Start with the sanity check

**`SANITY_CHECK.md`** comes before every file below. It has two parts, about
20 minutes in all:

- the quick check, `agency-server quick-check`, which signs in to the
  running server and opens every list and report of every firm, read only;
- a fifteen-step walk through the screens.

If it fails, the cases below cannot be trusted until the failure is fixed.

## The files

| File | Area | Detailed cases | Screen checks |
| --- | --- | --- | --- |
| `01_ROLES_AND_ACCESS` | What each of the 11 job templates may reach and do | 11 jobs, 723 screen rows | |
| `02_SIGN_IN_AND_ACCOUNTS` | Sign-in, lockout, sessions, your own account, platform mode, the 1.3.0 menu, branding | 37 | |
| `03_USERS_AND_ROLES` | Users, hiring, job templates, roles in two tiers | 52 | 5 |
| `04_FIRMS_AND_CONFIGURATION` | Creating and finishing a firm, isolation, numbering, profiles, tax, units, custom fields | 45 | 19 |
| `05_MASTERS` | Customers, vendors, products, branches, warehouses, principals and brands, merging duplicates, codes from a series | 22 | 13 |
| `06_PURCHASING` | Purchase order to supplier payment, returns, GST on purchases, requisitions, supplier terms, payment runs, landed cost; from 2026-10-05 the GST purchase register, payables by month, Paid now, attachments, TDS 194C and 194J, TCS, RFQ, rate contracts, serials at receipt, supplier schemes, imports and bills of entry, fixed assets, PTR and PTS | 90 | 19 |
| `07_INVENTORY` | Stock, transfer documents, write-offs, repacking, kits, counts, batches, serials | 20 | 18 |
| `08_SELLING` | Enquiry and quotation to cash, holds, returns, credit notes, debit notes, proforma, counter billing, price levels; from 2026-10-05 the GST sales register, walk-in cash sale, service invoices, other charges, transporters, attachments, hold and recall, counter shifts, collection follow-up, customer rebates | 87 | 9 |
| `09_PRICING_AND_INCENTIVES` | Price lists, promotions, coupons, loyalty, commission, targets, principal claims | 12 | 5 |
| `10_TERRITORY` | Territories, routes, beat plans, call lists, transporters | 6 | 8 |
| `11_COMPLIANCE` | GSTR-1, GSTR-3B, e-invoice and e-way bill sandbox, TCS, the tax calendar, filing checks, amendments, quarterly filing | 26 | 3 |
| `12_FINANCE_AND_REPORTS` | Ledger, journals, statements, periods, reports, bank reconciliation, cheques, TDS, Tally export, approvals, audit, diagnostics | 35 | 35 |
| `13_CROSS_CUTTING` | Permissions enforced by the server, two people editing one record | 17 | |
| `14_TEST_DATA` | The values to type for every firm, person, master and case (written by hand) | | |

In all: **449 detailed cases, 134 screen checks and 11 role checks** (counted
from the files on 2026-10-05). The
installation itself is tested separately by `docs/INSTALLER_QA_CHECKLIST.md`,
and `docs/QA_FUNCTIONAL_WALKTHROUGH.md` is a one-day end-to-end run that
makes a good first pass before this suite. For one tester's book across every
module, see `docs/QA_TEST_BOOK.md`.

## Before you start

1. **Install** with the installation guide and pass the installation
   checklist, sections A and B.
2. **Build the base firm QA01** with sections 1 and 2 of the functional
   walkthrough: the firm, its set-up, a firm administrator, a product, a
   vendor and a customer. Most cases run in QA01.
3. **Build a second firm QA02** the same way, with its own firm administrator.
   Cases about keeping firms apart, and about people in two firms, need it.
4. **Hire one user per job template** in QA01, as `01_ROLES_AND_ACCESS`
   describes. Most cases name the job they sign in as.
5. **Take every value from `14_TEST_DATA`**: the firms (it adds a few
   beyond QA01 and QA02), the people and their passwords, the masters, the
   documents each *Preparation* stands for, and the values for each case.

## Reading a case

Every case has the same parts:

| Part | Meaning |
| --- | --- |
| **Preconditions** | What must exist first. Build it by hand, following the other cases or the walkthrough. Where a section opens with a *Preparation* table, the precondition names a row of it, and the table gives the exact data |
| **Steps** | Click by click, naming the account to use |
| **Expect** | What passes. Messages are quoted exactly; a refusal is often the product working |

A few more conventions:

- **Names in bold**, such as **Manual Hire (qa)** or `QA-B`, are the people
  and records the preconditions ask for. Use whatever names you gave them.
- **Steps marked (HTTP)** are optional checks of the server behind a screen,
  for a tester with a REST client such as Postman. Skip them otherwise; the
  screen steps around them still stand.
- **Other firms.** A few cases mention further firms, such as MEDI01 or
  FOOD01. Those are the developer's demo firms. On an installed copy, read
  them as *any other firm on this installation*, and skip that part if there
  is none.
- **Screen checks** (ids ending `-Snn`) are one standard row per screen:
  it opens, lists or shows an empty state, searches, and handles New, Edit,
  Delete, Export and Import where offered. Run them as the firm administrator.

## Recording results

- Set each case's **Result** to `Pass`, `Fail` or `Blocked`. Write in
  **Notes** anything that differs from Expect, even when it passed.
- Each file ends with a results summary to fill in.
- On a failure, capture a screenshot, the newest file in
  `C:\ProgramData\Agency Platform\logs\server`, and the version shown on the
  sign-in screen.
- Keep each case's id (TC-…) in the report. It traces the failure back to the
  developer case, which carries the database checks behind it.

## Suggested order

Roles first, because every later file assumes the jobs work. Then
02, 03 and 04, then the trading areas in the order money flows (05, 06,
07, 08, 09, 10, 11, 12), then 13 last. Within 06, leave TC-BUY-086 and
TC-BUY-088 (the two that switch the buying stages off) to the very end of
the pass, as above.
