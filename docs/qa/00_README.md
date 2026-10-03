# QA test suite: every module, every role

The complete manual test suite for an **installed** copy of the Agency
Platform, one file per module area. Each file stands alone, so QA can take
one module at a time, and each has a PDF beside the installer.

Generated on 2026-10-03 from the product's own sources. The detailed cases
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
| `01_ROLES_AND_ACCESS` | What each of the 11 job templates may reach and do | 11 jobs, 579 screen rows | |
| `02_SIGN_IN_AND_ACCOUNTS` | Sign-in, lockout, sessions, your own account, platform mode | 27 | |
| `03_USERS_AND_ROLES` | Users, hiring, job templates, roles in two tiers | 52 | 5 |
| `04_FIRMS_AND_CONFIGURATION` | Creating and finishing a firm, isolation, numbering, profiles, tax, units, custom fields | 45 | 19 |
| `05_MASTERS` | Customers, vendors, products, branches, warehouses, principals and brands, merging duplicates, codes from a series | 22 | 14 |
| `06_PURCHASING` | Purchase order to supplier payment, returns, GST on purchases, requisitions, supplier terms, payment runs, landed cost | 28 | 16 |
| `07_INVENTORY` | Stock, transfer documents, write-offs, repacking, kits, counts, batches, serials | 20 | 18 |
| `08_SELLING` | Enquiry and quotation to cash, holds, returns, credit notes, debit notes, proforma, counter billing, price levels | 35 | 7 |
| `09_PRICING_AND_INCENTIVES` | Price lists, promotions, coupons, loyalty, commission, targets, principal claims | 12 | 5 |
| `10_TERRITORY` | Territories, routes, beat plans, call lists | 6 | 7 |
| `11_COMPLIANCE` | GSTR-1, GSTR-3B, e-invoice and e-way bill sandbox, TCS, the tax calendar, filing checks, amendments, quarterly filing | 26 | 3 |
| `12_FINANCE_AND_REPORTS` | Ledger, journals, statements, periods, reports, bank reconciliation, cheques, TDS, Tally export, approvals, audit, diagnostics | 35 | 29 |
| `13_CROSS_CUTTING` | Permissions enforced by the server, two people editing one record | 17 | |
| `14_TEST_DATA` | The values to type for every firm, person, master and case (written by hand) | | |

In all: **325 detailed cases, 123 screen checks and 11 role checks**. The
installation itself is tested separately by `docs/INSTALLER_QA_CHECKLIST.md`,
and `docs/QA_FUNCTIONAL_WALKTHROUGH.md` is a one-day end-to-end run that
makes a good first pass before this suite.

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
07, 08, 09, 10, 11, 12), then 13 last.
