# Go-live plan

The plan for the first real firms, written 2026-10-01 from what is merged on
`main` that day. The owner's decisions behind it (2026-09-29): the first firms
come from **all four trades** -- pharma distribution, FMCG and grocery,
electronics and durables, agri inputs -- and the **first firm goes live within
a month**, by about **2026-10-29**.

Three tiers: what must be done before that firm starts, what follows in the
first update, and what waits for the go-live firms to say they need it. Every
item names the backlog section or defect that holds its detail.

## Where things stand, 2026-10-01

- **Defects: none open.** Every defect in `docs/DEFECTS.md` is fixed and
  names its PR; D-GOLIVE-2, the last, was fixed by #884.
- **Built for go-live since 2026-09-29:**
  - Trade licences, all five steps (§54): register, printing, Home alert,
    required licence per product, sale and purchase checks.
  - TAN and the TDS accounts (§53.1) and the buying stage switches (§38).
  - Bringing a firm over from its old tool (§36, §46), all from files with
    a template and a check before anything is written: products,
    customers, suppliers, opening bills both sides, the opening trial
    balance, opening stock with batches.
  - Bulk approval of orders (§56 A), year-end close and reopen (§56), the
    Selling settings (§57), one bill for several delivery notes or
    receipts (§58).
  - Reports at volume: a firm with two years and 110,000 invoices was
    built and every report timed; the minute-long ones were fixed
    (`docs/PERFORMANCE_AT_VOLUME.md`).
  - Accounts > Expenses (#814): rent, fuel and salaries recorded and posted to
    the journal, refused in a locked year.
- **Built on 2026-10-01 for release 1.1.0** (#869-#887; the owner's single
  test list is `docs/RELEASE_NOTES_1.1.0.md`): the Opening balances
  checklist and opening bills from a file, TDS on payments, receipts and
  expenses with both registers, GST Payment, Profit and loss by months and
  against last year, stock valuation, purchase price variance, bulk approve
  and cancel on six lists and bulk post on journals, each person's branch and
  warehouse, Sales and Purchase Analysis, offers on the printed bill, Try
  offers, percent off up to a limit, best offer only, money received on the
  bill, and the go-live guide.

## Tier 1 -- before the first firm starts (weeks 1-4)

| # | What | Why it blocks | Size | Who |
| --- | --- | --- | --- | --- |
| 1 | **Install on a clean PC from `Setup.exe`** and run `docs/INSTALLER_QA_CHECKLIST.md`, including the new port rows A15a and A15b (D-SETUP-9 was driven by its script, never by a full install) | A firm's first day is the installer | Half a day | Owner |
| 2 | **Time the reports on the minimum hardware** in `docs/INSTALL_GUIDE.md` with `scripts/time_routes.py` against PERF01 | Every timing so far is on the development machine | Half a day | Owner + Claude |
| 3 | **Walk the onboarding on a copy of a real firm's data**: products, customers, suppliers, opening bills, trial balance and stock from their own files, in that order, then check that the trial balance, the stock valuation and the outstanding lists agree with the old tool | Proves §36 end to end on real data, not seeded data | 1-2 days | Owner with the firm |
| 4 | **An *Opening balances* step on the firm's Set up panel** that lists the imports above in order and ticks each one done | Today the imports live on five screens; a firm's first day should not depend on knowing where. **Built 2026-10-01** (#869); it found that the opening bills had no file import, fixed the same day (D-GOLIVE-1) | 1-2 days | Claude |
| 5 | **Expenses (#814, merged)**: the owner's laptop test of the merged screen | Expenses are a daily entry for every trade | Owner's test | Owner |
| 6 | **The go-live guide**: the TDS interim steps (§53, "docs only"), how to close a month and a year, how to bulk-approve, what to do when a licence check refuses | The firm's accountant reads it before the CA does. **Built 2026-10-01**: `docs/GO_LIVE_GUIDE.md` (PDF from `packaging/render_guide.py` + Edge); TDS is described as built rather than as interim steps | 1 day | Claude |
| 7 | **The printed bill names every delivery note it bills** (§58 item 7) | A bill made of three dispatches must say so on paper. **Built 2026-10-01** | 1 day | Claude |
| 8 | **Backup and restore drill** on the installed copy: scheduled backup (#812) runs, and a restore into a fresh install brings the firm back | A firm must not be able to lose its books | Half a day | Owner + Claude |
| 9 | **A full test run on the release commit**, the release build (`docs/RELEASE_BUILD.md`), and the version number | The release gate | 1 day | Claude |

Items 1, 2, 3, 5 and 8 need the owner or a firm; Claude builds 4, 6, 7 and 9
in parallel. Whatever item 3 finds goes to the top of the list.

## Tier 2 -- the first update after go-live (version 1.1)

| What | Backlog | Size |
| --- | --- | --- |
| ~~*TDS deducted* on payments, expenses and receipts, and the quarterly TDS list for the CA~~ **Built 2026-10-01**, ahead of go-live | §53 items 3-4 | Done |
| ~~Bulk approval for invoices, credit notes, returns and journals~~ **Built 2026-10-01** (#876) | §56 A | Done |
| Global search under a second: trigram indexes, one migration | §56 C | 1-2 days |
| GSTR-1 and 3B for a month under 3 s, and the outstanding reports | §56 C | 2-3 days |
| Set-based back-dated balance carry | §56 C | 2-3 days |
| Tally XML import, after the Excel path has been used by a real firm | §36 | About a week |
| Reject (send back to draft) as a bulk action, with approval rules | §56 A | 3-4 days |
| Sign-in screen and branding: the Jugnix name and logo, once the trademark is filed | §71 | 2 days |

## Tier 3 -- later, or when a go-live firm asks

The market reviews in the backlog list what a full ERP has and this one does
not. **None is built until a go-live firm says it needs it** (§55): a
feature nobody uses is a feature nobody tests.

- Sales: the rest of §60 (offer types still missing), §64 special rates and
  discount limits, §67 the nine sales gaps. **Built ahead of a firm asking,
  2026-10-01:** §59 best offer only, §60 items 1, 12 and 13, §62 sales
  analysis, §64 row 5 money received on the bill.
- Buying: §61 supplier free goods, §65 the rest of the purchase gaps, §68-69
  the procurement checklist. **Built 2026-10-01:** §65.5 price variance, §66
  purchase analysis.
- Stock: §70 the inventory checklist, FIFO costing if an accountant requires
  it.
- Messaging (email, WhatsApp, SMS) and field collections, designed in #848.
- Year-data archiving and log partitioning: not before a firm has years of
  data (`docs/BULK_APPROVAL_MIGRATION_AND_YEAR_DATA.md` section 4.5).

## Decisions taken by convention on 2026-10-01

The owner asked for decisions to be made the way other tools make them and
recorded rather than parked. These were:

1. **GSTR-1 and 3B cover at most a quarter.** They are filed monthly, or
   quarterly under QRMP; an annual figure is GSTR-9.
2. **The sales- and purchase-invoice reconciliations take a period** and page,
   like the sales-return reconciliation.
3. **An item's opening stock is posted once**, on the form and from a file
   alike; a second document for a warehouse is allowed for what was missed.
4. **Bulk actions are per row, not all-or-nothing**, and the second action is
   *Cancel with a reason* because neither order has a reject step yet.
5. **A year is closed by locking it, with no closing entry** (as Tally does);
   reopening needs its own permission and a reason.
6. **The business-framework screens stay platform-only**: setting a firm up is
   the platform's work, using what it was set up with is the firm's.
