# QA test suite: every module, every role

The complete manual test suite for an **installed** copy of the Agency
Platform, one file per module area. Each file stands alone, so QA can take
one module at a time, and each has a PDF beside the installer.

Generated on 2026-09-25 from the product's own sources. The detailed cases
come from `docs/INDEPENDENT_TEST_CASES.md`, whose every expectation was
driven against a running server. The screen checks and the role matrix come
from the application's screen catalogue and role seed. The files are
regenerated from those sources rather than edited by hand, so a fix belongs
in the source.

## The files

| File | Area | Detailed cases | Screen checks |
| --- | --- | --- | --- |
| `01_ROLES_AND_ACCESS` | What each of the 11 job templates may reach and do | 11 jobs, 353 screen rows | |
| `02_SIGN_IN_AND_ACCOUNTS` | Sign-in, lockout, sessions, your own account, platform mode | 27 | |
| `03_USERS_AND_ROLES` | Users, hiring, job templates, roles in two tiers | 52 | 5 |
| `04_FIRMS_AND_CONFIGURATION` | Creating and finishing a firm, isolation, numbering, profiles, tax, units, custom fields | 41 | 19 |
| `05_MASTERS` | Customers, vendors, products, branches, warehouses | 14 | 14 |
| `06_PURCHASING` | Purchase order to supplier payment, returns | 8 | 7 |
| `07_INVENTORY` | Stock, transfers, write-offs, counts, batches, serials | 8 | 14 |
| `08_SELLING` | Quotation to cash, holds, returns, credit notes, proforma | 17 | 7 |
| `09_PRICING_AND_INCENTIVES` | Price lists, promotions, loyalty, commission, targets | 8 | 5 |
| `10_TERRITORY` | Territories, routes, beat plans, call lists | 5 | 7 |
| `11_COMPLIANCE` | GSTR-1, GSTR-3B, e-invoice and e-way bill sandbox, TCS | 7 | 3 |
| `12_FINANCE_AND_REPORTS` | Ledger, journals, statements, periods, reports, audit, diagnostics | 21 | 17 |
| `13_CROSS_CUTTING` | Permissions enforced by the server, two people editing one record | 17 | |

In all: **225 detailed cases, 98 screen checks and 11 role checks**. The
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
