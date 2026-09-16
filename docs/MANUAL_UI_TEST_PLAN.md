# Manual UI test plan

> **Since 2026-09-16 the cases live in `docs/INDEPENDENT_TEST_CASES.md`.**
> Every numbered section below (2 to 27) is now a pointer and an old-row →
> case map; each case there runs on its own from a fixture
> (`backend/scripts/test_fixture.py`), in any order. This file keeps Part 1
> (bringing the environment up), the seed facts the old rows rested on, and
> Part 4 (known gaps).

Scripted manual tests for the Flutter desktop client against a real backend,
**organised by module** so a session can take one module at a time and stop
cleanly at the end of it.

Rewritten on **2026-09-05** against the running application. The previous
version was written on 2026-08-16, before promotions, loyalty, credit notes,
proformas, TCS, GST returns, e-invoicing, customer groups and price-list
ladders existed, and its section numbers had begun to collide.

**Every case names the seeded data it needs** — which login, which firm, which
customer code, which document number. You should never have to hunt for "a
customer with a standing discount"; the case says it is `WHOLE01C01`.

A case that needs a request the desktop cannot make is marked **(HTTP)** and
gives the `curl`. Those are still manual tests: they check a guarantee the
server owes, and marking them keeps the plan honest about what clicking can
and cannot prove.

A case marked **(GAP)** covers something deliberately not built. It is there so
you do not report it as a defect — see §14.

---

# Part 1 — Before you start

## 1.1 Bring the environment up

From `backend/`:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_all_stores.py --dry-run   # what is where
.\.venv\Scripts\python.exe scripts\migrate_all_stores.py --yes       # bring all to head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Never `alembic upgrade head` on its own — it advances one schema and this
demo has four stores.

If the data looks wrong or empty, reseed **one firm at a time** so a run fits
inside a coffee:

```powershell
.\.venv\Scripts\python.exe scripts\seed_multi_firm_demo.py --firm WHOLE01
.\.venv\Scripts\python.exe scripts\verify_sample_data.py
```

`verify_sample_data.py` must end **"Every store holds together"**. If it does
not, stop and read what it says before testing anything else — every number on
every screen below is derived from those books.

From `desktop/`:

```powershell
flutter run -d windows --dart-define=API_BASE_URL=http://localhost:8000
```

## 1.2 The firms, and why there are four

| Firm | Storage mode | Where its data lives | Business profile |
| --- | --- | --- | --- |
| `WHOLE01` | `SCHEMA` | schema `wholesale_hub` in `agency_platform` | WHOLESALE |
| `FOOD01` | `SHARED` | schema `firm_shared` in `agency_platform` | FOOD |
| `MEDI01` | `SHARED` | schema `firm_shared` in `agency_platform` | PHARMACY |
| `ELEC01` | `DATABASE` | schema `electrolink_ops` in a **separate database** | ELECTRONICS |

`FOOD01` and `MEDI01` sharing one schema is the important pair: their rows sit
in the same physical tables, separated only by `firm_id`. Isolation defects
show up there first. `ELEC01` is the other end — a different database
entirely.

**The four firms trade identically on purpose.** Each has 32 purchase orders,
30 goods receipts, 58 sales orders, 58 delivery notes and 49 invoices across
three financial years. A count that differs between firms is a signal worth
chasing. The one known exception is e-invoicing: `WHOLE01` reads `IRN 13` where
its siblings read 17, because it carries a hand-made customer with no GST
number whose invoices are correctly refused.

## 1.3 Accounts

| Login | Password | Firms | Use it for |
| --- | --- | --- | --- |
| `master.ops@agency.local` | `DemoAdmin@12345` | all 4 | firm switching, cross-firm isolation |
| `whole01.admin@agency.local` | `DemoAdmin@12345` | WHOLE01 | single-firm behaviour, SCHEMA mode |
| `whole01.sales1@agency.local` | `DemoAdmin@12345` | WHOLE01 | **an operational role** — use it for every "should be refused" case |
| `whole01.sales2@agency.local` | `DemoAdmin@12345` | WHOLE01 | the second salesman, for commission |
| `food01.admin@agency.local` | `DemoAdmin@12345` | FOOD01 | SHARED mode |
| `medi01.admin@agency.local` | `DemoAdmin@12345` | MEDI01 | SHARED mode, the other half of the pair |
| `elec01.admin@agency.local` | `DemoAdmin@12345` | ELEC01 | DATABASE mode |

`platform-admin@agency.local` is **not** in this list. It must change its
password on first use and every platform-admin route refuses it until then.
Rotating it invalidates the value in `config/.env`. Use `master.ops` instead.

## 1.4 The seeded data every case refers to (WHOLE01)

**Customers**

| Code | Name | Standing discount | Segment | Own price list |
| --- | --- | ---: | --- | --- |
| `WHOLE01C01` | Vijaya Super Stores | 7.5% | Retailer (1.75%) | — |
| `WHOLE01C02` | Anand Agencies | — | Wholesaler (3.25%) | `NEGOTIATED`, 9.25% |
| `WHOLE01C03` | Classic Departmental Stores | — | Retailer (1.75%) | — |
| `OB-REV2` | Revise Check 2 | 7.5% | — | — |

`OB-REV2` was created by hand during testing. It has **no GST number**, which
is why four of this firm's invoices cannot be e-registered. Leave it alone; it
is useful precisely because it is the odd one.

**Products** — `DETER1K` Detergent Powder 1kg · `SHAMP180` Shampoo Bottle
180ml · `TOOTH150` Toothpaste 150g.

**Promotions** — `BULK5` (two revisions, line quantity ≥ 25, 5% then 7.5%) ·
`BIGORDER` (document ≥ 4,500, ₹200 off the bill, **does not stack**) ·
`CLEARANCE` (line quantity ≥ 40, 1%) · `WELCOME` (2.5%, **needs a coupon**).
Coupons `WELCOME10` (used) and `WELCOME10B` (never presented).

**Price list `STANDING`** — firm-wide, on `DETER1K` only, with breaks at 0 →
2%, 15 → 4.25%, 18 → 6.75%.

**Territories** — `WHOLE01-RGN` Chennai Region → `WHOLE01-T-N` / `WHOLE01-T-S`
zones → routes `WHOLE01-R-N1`, `WHOLE01-R-N2`, `WHOLE01-R-S1`.

**Beat plans** — `WHOLE01-BP-R1-MON`, `-R1-WED`, `-R1-FRI` (weekly),
`WHOLE01-BP-COLL` (alternate Tuesdays), `WHOLE01-BP-MTH` (second Tuesday).

## 1.5 Recording a result

For each case write **pass**, **fail** or **blocked**, and for a failure the
smallest thing that reproduces it. A screenshot taken from inside the app
(Help → Report a problem) carries the request id, which joins it to the
server-side traceback — that is worth far more than a photograph of the
screen.

---

# Part 2 — Module by module

Work down. Each module is self-contained; the order follows how a distribution
firm actually operates, so later modules can use what earlier ones produced.

## 2. Login, session and firm context

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-SESS-001 to
011. The person locked out, switched off, deleted and restored is the
`lock-target` fixture's own user rather than `rr@rr.com` or a spare account,
and WHOLE01/ELEC01 are TEST01/TEST02.

Driving the rows found one disagreement, recorded as **D-2-1** rather than
decided: 2.10 says a wrong password on an inactive or expired account still
answers "Invalid email or password.", and the server names the state instead.

| Old row | Case |
| --- | --- |
| 2.1 | TC-PLAT-002 |
| 2.2 | TC-SESS-001 |
| 2.3 | TC-PLAT-005 |
| 2.4, 2.5 | TC-SESS-002 |
| 2.6, 2.7 | TC-SESS-003 |
| 2.8, 2.9 | TC-SESS-004 |
| 2.10 | TC-SESS-005 |
| 2.11 | TC-SESS-006 |
| 2.12 | TC-ROLE-008 (an edit that changes somebody's access signs them out) |
| 2.13 | TC-SESS-007 |
| 2.13b, 2.13c | TC-SESS-008 |
| 2.13d (both rows) | TC-SESS-009 |
| 2.14 | TC-SESS-010 |
| 2.15, 2.16, 2.17 | TC-SESS-011 |

## 3. Firm isolation — the core of this application

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-ISO-001 to
004. FOOD01 and MEDI01, the demo pair sharing a schema, are replaced by the
fixture firms **TESTSH1** and **TESTSH2** in the same schema, so no case writes
an `ISO-TEST` customer into a demo firm; TEST01 and TEST02 stand in for WHOLE01
and ELEC01.

| Old row | Case |
| --- | --- |
| 3.1, 3.2 (shared) | TC-ISO-001 |
| 3.2 (dedicated), 3.3, 3.3b | TC-ISO-002 |
| 3.4 | TC-ISO-003 |
| 3.5, 3.6 | TC-ISO-004 |

## 4. Masters — customers

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-CUST-001 to
006. `WHOLE01C01` and `WHOLE01C03` are replaced by the `customer-master`
fixture's own customer, which carries every field the partial-update defect
used to reset, plus places and segments of its own; the statement and ageing
use `invoiced-part-paid`.

One correction: **4.5** said the credit Settings action is not offered to
`whole01.sales1`. It is — read-only, on `CUSTOMER_VIEW`, by design ("someone
the policy warns should see the rule behind the warning") — and the server
refuses that user's save with 403.

| Old row | Case |
| --- | --- |
| 4.1, 4.2 | TC-CUST-001 |
| 4.3, 4.4 | TC-CUST-002 |
| 4.5 | TC-CUST-003 |
| 4.6 | TC-CUST-004 |
| 4.7, 4.8 | TC-CUST-005 |
| 4.9, 4.10 | TC-CUST-006 |

## 5. Masters — vendors, products, branches, warehouses

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-MAST-001 to
008. The vendor, product, branch and warehouse each come from a fixture of
their own rather than WHOLE01's seeded ones; the branch and warehouse live in
**TEST02**, because making a branch default demotes the firm's previous one,
and the `branch-master` fixture also writes the two import files 5.8 needs.

**5.5** (the product Attributes tab offering this firm's fields) is covered by
TC-FIELD-001 and TC-FIELD-003 in a firm of the run's own — and by defect
**D-27-1**: the product form offers only fields a category rule names.

| Old row | Case |
| --- | --- |
| 5.1 | TC-MAST-001 |
| 5.2, 5.3 | TC-MAST-002 |
| 5.4 | TC-MAST-003 |
| 5.5 | TC-FIELD-001, TC-FIELD-003 |
| 5.6 | TC-MAST-004 |
| 5.7 | TC-MAST-005 |
| 5.8, 5.8b | TC-MAST-006 |
| 5.8a, 5.9 | TC-MAST-007 |
| 5.10 | TC-MAST-008 |

## 6. Configuration

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-CONF-001 to
006. The cases that change a whole store — a business profile's features, a
firm-wide conversion rule — run in the `config-firm` fixture's own store, so
nothing is left behind in a firm another case reads, and "delete the firm-wide
rule afterwards" is no longer a step anybody can forget. The numbering and
simulator cases run in TEST01.

| Old row | Case |
| --- | --- |
| 6.1, 6.2 | TC-CONF-001 |
| 6.3 | TC-CONF-002 |
| 6.4 | TC-CONF-003 |
| 6.5 | TC-CONF-004 |
| 6.6 | TC-FIELD-003 |
| 6.7 | TC-CONF-005 |
| 6.8 | TC-CONF-006 |

## 7. Buying — order to payment

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-BUY-001 to
008. The rows were one chain in WHOLE01 — each receipt, cancellation and
return building on the last, with stock "relative to where you started". Four
fixtures now start at each stage (`buy-ready`, `po-approved`, `po-received`,
`po-invoiced`) with a product of the run's own that begins at zero, so every
figure is absolute and there is nothing to clean up before a fresh run.

Two corrections: the payment series prefix is **`PY-`**, not `PAY-`; and 7.8
no longer needs a seeded WHOLE01 invoice, because the fixture raises one.

| Old row | Case |
| --- | --- |
| 7.1, 7.2, 7.3 | TC-BUY-001 |
| 7.4 | TC-BUY-002 |
| 7.5, 7.6 | TC-BUY-003 |
| 7.7 | TC-BUY-004 |
| 7.8 | TC-BUY-005 |
| 7.9 | TC-BUY-006 |
| 7.10 | TC-BUY-007 |
| 7.11 | TC-BUY-008 |

## 8. Stock

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-STOCK-001 to
008. The rows ran on WHOLE01 after section 7 ("Current in WH_NORTH is what
section 7 left"), MEDI01's seeded batches and ELEC01's seeded serials. Now
`stock-ready` gives a TEST01 product 50 on hand beside an empty second
warehouse, and `pharma-firm` / `electronics-firm` build firms of the run's own
on the Pharmacy and Electronics profiles — TEST01's Wholesale profile enables
neither expiry dates nor serial numbers, and refuses both.

Driving the batch case found **D-8-1**: dispatch took its 5 from a batch that
had expired a month earlier, ahead of one still in date. Recorded, not fixed.

| Old row | Case |
| --- | --- |
| 8.1, 8.2 | TC-STOCK-001 |
| 8.3 | TC-STOCK-002 |
| 8.3a, 8.3b | TC-STOCK-003 |
| 8.4 | TC-STOCK-004 |
| 8.5, 8.6 | TC-STOCK-005 |
| 8.6a | TC-STOCK-007 |
| 8.7 | TC-STOCK-006 |
| 8.8 | TC-STOCK-008 |

## 9. Selling — quotation to cash

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-SELL-001 to
017. The rows were one chain in WHOLE01 ("in order: each step feeds the
next"), resting on two years of seeded history — Vijaya's older debts, the
seeded TCS settings, the promotions' claim counts. The `selling-firm` fixture
builds a store of the run's own priced the same way (the STANDING ladder,
Anand's negotiated list, BULK5, BIGORDER, CLEARANCE, WELCOME and its two
coupons, TCS, loyalty), and four stage fixtures carry one sale to where each
step begins.

Every pricing figure and document total below was re-driven in a fixture firm
and matches WHOLE01's: 2%, 6.75%, 9.25%, 7.5%, 2.5%, an invoice of 483.21
(409.50 + 73.71), a return crediting 193.28, a credit note of 59.00 and its
cap at 409.50. Two figures differ **because the firm is new**, and the cases
say so: Vijaya owes nothing older, so the excess on the second receipt becomes
an **advance** (97.58) rather than coming off the account; and TCS applies
from the first rupee (threshold 0) so every receipt shows it.

| Old row | Case |
| --- | --- |
| 9.1 | TC-SELL-001 |
| 9.2 | TC-SELL-002 |
| 9.3 | TC-SELL-003 |
| 9.4, 9.5 | TC-SELL-004 |
| 9.6 | TC-SELL-005 |
| 9.7, 9.8 | TC-SELL-006 |
| 9.9 | TC-SELL-007 |
| 9.10, 9.11 | TC-SELL-008 |
| 9.12, 9.14 | TC-SELL-009 |
| 9.13 | TC-SELL-010 |
| 9.15, 9.16 | TC-SELL-011 |
| 9.17 | TC-SELL-012 |
| 9.18, 9.19 | TC-SELL-013 |
| 9.20, 9.21 | TC-SELL-014 |
| 9.22 | TC-SELL-015 |
| 9.23, 9.24 | TC-SELL-016 |
| 9.25, 9.26 | TC-SELL-017 |

## 10. Pricing, promotions and incentives

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-INCENT-001 to
008. Pricing and promotions run on the `selling-*` fixtures; loyalty on
`loyalty-points` (a goodwill adjustment of 200 points, since one fixture invoice
earns too few to spend); commission and targets on `commission-firm` — a
territory store with a firm-wide 4%, Asha's 15% on one product, Bala's ladder
with a floor and a bonus, three sales collected in full, and this month's
targets one met and one missed. Driven: Asha 495.60 on 5,900 (a blended 8.4%),
Bala exactly 2.00%.

Not carried over: **10.11**'s aged batches and oldest-first spending need
points two years old, which no fixture can make; the case checks the report
opens empty. **10.4–10.6**'s seeded claim counts are the fixture's own now.

| Old row | Case |
| --- | --- |
| 10.1, 10.2 | TC-INCENT-001 |
| 10.3 | TC-INCENT-002 |
| 10.4, 10.5, 10.6 | TC-INCENT-003 |
| 10.7 | TC-INCENT-004 |
| 10.8 – 10.11 | TC-INCENT-005 |
| 10.12, 10.13 | TC-INCENT-006 |
| 10.14 | TC-INCENT-007 |
| 10.15 | TC-INCENT-008 |

## 11. Territory, routes and beats

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-TERR-001 to
005. The `territory-firm` fixture builds WHOLE01's shape in a store of the
run's own — region, two zones, three routes with the same frequencies, days,
salespeople and rounds, the nine beat plans — so the call lists answer the same
days the same way (driven: 1 of 9 on a Monday; 4 of 9 on 2027-01-12; the
fortnight and second-Tuesday reasons word for word), and 11.5's temporary
reordering and 11.7's drafts land in that store, not WHOLE01's.

Building it found **D-11-1**: a new store's hierarchy levels are invented
afresh on every read and refused when a territory names one, until somebody
saves the hierarchy. Recorded, not fixed.

| Old row | Case |
| --- | --- |
| 11.1, 11.2 | TC-TERR-001 |
| 11.3 | TC-TERR-002 |
| 11.4 | TC-TERR-003 |
| 11.5, 11.6 | TC-TERR-004 |
| 11.7 | TC-TERR-005 |

## 12. Compliance

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-COMP-001 to
007. WHOLE01's August figures and its thirteen seeded registrations are
replaced by the `compliance-firm` fixture — a GST-registered store of the run's
own with a registered and an unregistered buyer, an HSN'd product and three
bills this month — and the TCS register by `selling-paid`'s two receipts.
Driven: B2B 1,000 and 500, B2CS 300 at place 33, HSN 1,800; the paid,
registered bill refused cancellation naming its receipt and its registration;
the B2C bill cancelled and left GSTR-1 and 3B at 1,500 / 1,800 → 1,500; local
refusal for no GSTIN; vehicle required; e-way bill before registration refused.

| Old row | Case |
| --- | --- |
| 12.1 | TC-COMP-001 |
| 12.2 | TC-COMP-002 |
| 12.3 | TC-COMP-003 |
| 12.4 | TC-COMP-004 |
| 12.5 | TC-COMP-005 |
| 12.6 | TC-COMP-006 |
| 12.7, 12.8 | TC-COMP-007 (and TC-SELL-013 for the receipt that charges it) |

## 13. Finance, reports and platform

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-FIN-001 to
011. The books cases (a new account, a closed period, centres, an account that
demands a centre) run in `ready-firm`'s own store, so closing June touches no
firm another case reads; the statements, journals and reports read
`selling-paid`; MEDI01's credit block and FOOD01's missing delivery-note stage
are `policy-firm`. WHOLE01's day-specific figures (660,640.05, 387 entries, 56
reports with six empty) are replaced by the relationships they illustrate.
Driven: "Accounting period P03 is closed and cannot accept postings.", the
cost-centre refusal, the 179.9% block, and an invoice off an order that
raised and dispatched its own note.

| Old row | Case |
| --- | --- |
| 13.1 | TC-FIN-001 |
| 13.2, 13.3 | TC-FIN-002 |
| 13.4 | TC-FIN-004 |
| 13.5, 13.8 | TC-FIN-003 |
| 13.6 | TC-FIN-005 |
| 13.7 | TC-FIN-006 |
| 13.9, 13.9b, 13.9c | TC-FIN-010, TC-ROLE-001, TC-ROLE-002 |
| 13.9c2 | TC-STOCK-008 |
| 13.9c3 | TC-FIN-008, TC-FIN-009 |
| 13.9d, 13.9e | TC-FIN-007 |
| 13.10 | TC-FIN-011 |

## 14. Concurrency and two machines

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-CONC-001 to
006, on fixture records rather than `WHOLE01C03`, `SO-2026-2027-000012`,
`TOOTH150`, `STANDING` and May/June 2025 payouts — so the coupon limit a case
sets, and the payouts it accrues, stay in a store of the run's own and need no
clearing afterwards. Re-driven: an unchanged save kept `ETag "2"`; a second
approval answered "Only draft sales orders can be approved."; the second order
on a one-use coupon was refused by name; a second accrual of a period answered
409 with the sentence.

| Old row | Case |
| --- | --- |
| 14.1 | TC-CONC-001 |
| 14.2 | TC-CONC-002 |
| 14.3 | TC-CONC-003 |
| 14.4 | TC-CONC-004 |
| 14.5 | TC-CONC-005 |
| 14.6 | TC-CONC-006 |

## 15. Permissions

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-PERM-001 to
003, on the `sales-executive` fixture's own seller in TEST01 rather than Asha.
Re-driven with that token: the two reads answer 200 and all six writes 403,
before any record is looked up, so no seeded payout or credit note id is
needed.

| Old row | Case |
| --- | --- |
| 15.1, 15.3, 15.4, 15.5 | TC-PERM-001 (the screens) and TC-PERM-003 (the routes) |
| 15.2 | TC-PERM-002 and TC-PERM-003 |
| 15.6 | TC-PERM-003 |

## 16. Who a user is — the four tiers

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-TIER-001 to
003. The section no longer changes `superadmin`'s scope by SQL and back: the
`platform-operator` fixture makes a `PLATFORM`-scope administrator of its own,
a member of TEST01 and TEST02 with no roles, which is the shape 16.3 needs.

| Old row | Case |
| --- | --- |
| 16.1, 16.6 | not needed — the fixture builds the operator |
| 16.2 | TC-TIER-001 |
| 16.3 | TC-TIER-002 |
| 16.4 | TC-TIER-003 |
| 16.5 | TC-PLAT-003 (an `ALL_FIRMS` administrator switching into a firm they are not a member of) |

## 17. User templates — hiring by naming the job

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-TMPL-001 to
011, in TEST01 with fixture users rather than Asha, Bala and `whole01.admin`.
17.6a and 17.6b share nothing now: each is its own run of `two-tier-hire`.

One correction: **17.6b** said applying Warehouse leaves "four roles, a
different four". Warehouse carries one role, `INVENTORY_MANAGER`, so the global
tier becomes that one and the person holds three.

| Old row | Case |
| --- | --- |
| 17.1, 17.2 | TC-TMPL-001 |
| 17.3, 17.4 | TC-TMPL-002 |
| 17.4a, 17.4b | TC-TMPL-003 |
| 17.4c, 17.4d | TC-TMPL-004 |
| 17.5, 17.6 | TC-TMPL-005 |
| 17.6a | TC-TMPL-006 |
| 17.6b | TC-TMPL-007 |
| 17.7 | TC-TMPL-008 |
| 17.8 | TC-TMPL-010 |
| 17.9 | TC-TMPL-009 |
| 17.10 | TC-TMPL-011 |
| 17.11 | TC-ROLE-001 |

---

## 18. Hiring like an existing person

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-HIRE-001 to
004. The source is the `clone-source` fixture's own seller in TEST01 rather
than Asha, and each case that needs a clone makes it, so 18.7 no longer waits
for 18.4.

| Old row | Case |
| --- | --- |
| 18.1, 18.2, 18.3 | TC-HIRE-001 |
| 18.4, 18.5, 18.6 | TC-HIRE-002 |
| 18.7 | TC-HIRE-003 |
| 18.8 | TC-HIRE-004 |

## 19. Setting a firm up from the platform side

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-TMPL-012 to
015. TEST02 plays FOOD01's part and TEST01 WHOLE01's, and each case deletes the
template it wrote.

**Left over from the 2026-09-15 run:** an `every-night` template offered to
every firm (CASHIER) is still live — 19.4a's clean-up did not happen. It shows
in every firm's User Templates as **Every firm**; delete it as a platform
administrator.

| Old row | Case |
| --- | --- |
| 19.1 | TC-TMPL-012 |
| 19.2, 19.3 | TC-TMPL-013 |
| 19.4, 19.4a | TC-TMPL-014 |
| 19.5 | TC-TMPL-015 |

---

## 20. A firm administrator creating users

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-USER-001 to
009. The rows no longer build on each other: `plan20a`, `plan20b` and
`plan20c` are gone, and the two-firm person 20.1b, 20.6 and 20.7 need comes
from the `shared-member` fixture (TEST02 primary, TEST01).

Two changes from the row text:

- **20.2b is no longer a known failure** — #402 fixed it. Driving the fix found
  a smaller defect in its place, written up as **D-20-1**: asking for roles on
  somebody in no firm refuses *after* the account has been made.
- **20.6 step 1 and 20.7's setup** are not needed; the fixture's memberships
  and primary are the starting point.

| Old row | Case |
| --- | --- |
| 20.1, 20.1a | TC-USER-001 |
| 20.1b | TC-USER-002 |
| 20.2, 20.2a, 20.3 | TC-USER-003 |
| 20.2b | TC-USER-004 |
| 20.2c, 20.4 | TC-USER-005 |
| 20.5 | TC-USER-006 |
| 20.6 | TC-USER-007 |
| 20.7 | TC-USER-008 |
| 20.8 | TC-USER-009 |

---

## 20a. Roles: global and firm-level

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-RTIER-001
to 008. "A user who belongs to two firms — create one first" is the
`shared-member` fixture; the roles 20a.6 onwards start from are
`shared-member-roles`.

**20a.8k** ("This person belongs to no firm you administer.") is not a case of
its own: the dialog has to be opened on somebody outside the firm
administrator's firm, and such a person is not in their grid. TC-RTIER-008
covers the server's half of the same rule.

| Old row | Case |
| --- | --- |
| 20a.1 – 20a.5 | TC-RTIER-001 |
| 20a.6, 20a.8d | TC-RTIER-002 |
| 20a.6b, 20a.6c, 20a.6d | TC-RTIER-003 |
| 20a.7, 20a.8, 20a.8j | TC-RTIER-004 |
| 20a.8b, 20a.8c, 20a.8e | TC-RTIER-005 |
| 20a.8f, 20a.8g | TC-RTIER-006 |
| 20a.8h, 20a.8i | TC-RTIER-007 |
| 20a.8k, 20a.9, 20a.9b, 20a.10 | TC-RTIER-008 |

---

## 21. The five modules a firm administrator could not open

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-GRANT-001 to
008, in TEST01. The credit note case no longer needs an approved invoice from
WHOLE01's history: the `invoiced` fixture sells this run's own product through
order, delivery note and invoice, and leaves one invoice approved and one
cancelled so the picker has something to exclude. 21.4b's "somebody holding
`LOYALTY_VIEW` but not the settings code" is the `loyalty-viewer` fixture
(`SALES_MANAGER`).

TEST01's loyalty scheme is **off**, not WHOLE01's running one, so TC-GRANT-004
switches it on to read the banner and back off at the end.

| Old row | Case |
| --- | --- |
| 21.1, 21.1a | TC-GRANT-001 |
| 21.2 | TC-GRANT-002 |
| 21.3 | TC-GRANT-003 |
| 21.4, 21.4a | TC-GRANT-004 |
| 21.4b | TC-GRANT-005 |
| 21.5 | TC-GRANT-006 |
| 21.6 | TC-GRANT-007 |
| 21.7 | TC-FIRM-016 |
| 21.8 | TC-GRANT-008 |

---

## 22. A cashier can see the till

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-CASH-001 to
004. 22.0's "make the cashier" is the `cashier` fixture, which also makes a
customer of its own for the party picker; 22.5's accountant, whom no demo firm
seeds, is the `accountant` fixture.

| Old row | Case |
| --- | --- |
| 22.0, 22.1, 22.2, 22.3 | TC-CASH-001 |
| 22.4, 22.4a | TC-CASH-002 |
| 22.5 | TC-CASH-003 |
| 22.6 | TC-CASH-004 |

---

## 23. The audit trail

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-AUDIT-001 to
006. 23.4a's "throwaway account" is the `manual-hire` fixture's user, and
23.4b's check of the merge no longer depends on two years of seeded history:
the case writes a customer, applies a template and writes another customer, so
the platform row must land between the two firm rows.

| Old row | Case |
| --- | --- |
| 23.1 | TC-AUDIT-001 |
| 23.2 | TC-AUDIT-002 |
| 23.3, 23.4, 23.5 | TC-AUDIT-003 |
| 23.4a, 23.4b, 23.4c | TC-AUDIT-004 |
| 23.6 | TC-AUDIT-005 |
| 23.7 | TC-AUDIT-006 |

---

## 24. Hiring somebody who already has an account

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-LOOK-001 to
007. ELEC01's people are replaced by the `outsider` fixture's own person, who
works in TEST02 alone, so nothing here adds a demo-firm employee to another
demo firm and there is nothing to tidy up before section 25. The cases that
start with that person already added use `outsider-added`.

| Old row | Case |
| --- | --- |
| 24.1 – 24.7 | TC-LOOK-001 |
| 24.8 | TC-LOOK-002 |
| 24.9, 24.9a, 24.10 | TC-LOOK-003 |
| 24.11, 24.12, 24.13 | TC-LOOK-004 |
| 24.14, 24.15, 24.16 | TC-LOOK-005 |
| 24.17 – 24.20 | TC-LOOK-006 |
| 24.21, 24.22 | TC-LOOK-007 |

---

## 25. A firm's own roles and its own templates

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16** — the pilot for
cases that run on their own, in any order, from a fixture
(`backend/scripts/test_fixture.py`) instead of from whatever an earlier row
left behind. This section was chosen first because it was the worst chain:
25.7 needed 25.2's role and 25.10 deleted it, so 25.9 could never be run twice.

Converting it also corrected 25.8, which had said a role holder sees Sales,
Masters and Finance. The desktop's own visibility logic says eight modules —
Quotations, Sales Orders, Delivery Notes, Sales Invoices and Sales Returns are
modules of their own, not tabs of Sales — and that list is in TC-ROLE-007.

| Old row | Case |
| --- | --- |
| 25.1 | TC-ROLE-001 |
| 25.2, 25.3, 25.4 | TC-ROLE-002 |
| 25.4a | TC-ROLE-004 |
| 25.5 | TC-ROLE-003 |
| 25.6 | TC-ROLE-005 |
| 25.7 | TC-ROLE-006 |
| 25.8 | TC-ROLE-007 |
| 25.9 | TC-ROLE-008 |
| 25.10, 25.10a | TC-ROLE-009 |

---

# Part 4 — Known gaps

Do **not** raise these as defects. They are deliberate, and each is recorded in
`docs/MODULE_STATUS.md` with what is blocking it.

**Five entries came off this table on 2026-09-15**, and it is worth knowing why
before you read the rest of it. They all said "built, but nothing exercises it",
which was true when written and stopped being true on 2026-09-08 when the demo
seeder was extended to reach exactly those five paths. A stale row here is worse
than a stale row anywhere else in this plan: this table tells you **not to
raise** what it lists, so each of those five was quietly excluded from testing
for a week after it became testable. They are now in the table below the gaps,
with the firm that carries each.

| Area | State |
| --- | --- |
| Emailing a document | Not built. The PDF exists; there is no SMTP client or mail configuration. Deferred by the owner. |
| Licensing | Not built. A permission and a role exist and are unused. Deferred by the owner. |
| `lots` | The one table still holding no live row in any store. |
| `IMEI`, `PRESCRIPTION_REQUIRED`, `RECIPE_MANAGEMENT`, `KITCHEN_MANAGEMENT`, `SERVICE_CONTRACTS`, `PROJECT_MANAGEMENT` | Declared as roadmap features and refused if switched on. Six, not seven: `COMMISSION` came off on 2026-09-03, because `app/commission` shipped on 08-23 and the flag outlived the fact — an administrator was being refused a feature the platform had. |

### No longer gaps — these are testable, and on which firm

Each is one deliberate choice on one demo firm, so the ordinary case sits beside
the exceptional one. **Do** raise a defect against any of these.

| Area | Where it lives now |
| --- | --- |
| Serial numbers | **ELEC01**'s mixer grinder has `track_serial` set, with up to twenty serials carrying warranty dates. Tracking only — receipts and issues do not demand the numbers, so the trading history is unaffected. Needed `SERIAL_NUMBER` and `WARRANTY` on the ELECTRONICS profile, which the feature seed backfills. |
| Packaging levels | Each firm's **first product** carries a `Case` level with a barcode. |
| Cost and profit centres | **Two of each per firm**, plus one posted manual journal naming them. Manual deliberately: the automatic postings name no centre, so a seeded account that required one would refuse them. |
| Shortened sales chains | **FOOD01** has `delivery_note_stage` off, so every one of its invoices is billed off the order and `SalesChainService` dispatches the goods — the one path that moves stock from an invoice. Note the consequence, which is an open product question rather than a defect: FOOD01's Delivery Notes screen is hidden when the stage is off, so its service-raised notes can only be read through the Delivery note register report. |
| Credit **blocking** | **MEDI01** is in `BLOCK` mode (warn 80, block 100) and CityMed Clinic sits on a 20,000 limit the history crosses, so refused approvals appear in the seeder's notes and the refused orders stay unapproved on the grid. The other three firms are in `WARN`, so both paths are seeded. |

---

## 26. Platform mode, and the switcher that was empty

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-PLAT-001 to
005. Converting it corrected two things: the switcher lists **every active
firm** — seven on this database when converted, not "all four" — and
**Licensing** is shown in platform mode and disappears once a firm is selected.

| Old row | Case |
| --- | --- |
| 26.1, 26.8 | TC-PLAT-001 |
| 26.2, 26.3 | TC-PLAT-002 |
| 26.4, 26.5, 26.6, 26.7 | TC-PLAT-003 |
| 26.9 | TC-PLAT-004 |
| 26.10 | TC-PLAT-005 |

## 26a. The user menu: who you are, and where you start

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-ME-001 to
008. 26a.11 said "a new password of 8 characters"; the rule and the message are
**twelve** — "Use at least 12 characters." — and the case uses that.

| Old row | Case |
| --- | --- |
| 26a.1, 26a.2 | TC-ME-001 |
| 26a.3, 26a.4 | TC-ME-002 |
| 26a.5 | TC-ME-003 |
| 26a.6 | TC-ME-006 (platform) and TC-ME-007 (one firm) |
| 26a.7 | TC-ME-004 |
| 26a.8, 26a.10 | TC-ME-005 |
| 26a.9 | TC-ME-006 |
| 26a.11, 26a.12, 26a.13 | TC-ME-008 |

## 27. Creating a firm and setting it up

**Moved to `docs/INDEPENDENT_TEST_CASES.md` on 2026-09-16**, as TC-FIRM-001 to
016 and TC-FIELD-001 to 014. The cases no longer share `SNTEST02`: each run of
a fixture builds a firm of its own, so the first press of **Open the books** is
always a first press.

Driving them corrected the section in these places:

- **27.23i** "with People already done, the verdict reads Finished" -- a firm a
  platform administrator creates has **no members**, so People stays missing
  and the verdict does not reach Finished until somebody is added.
- **27.26** now runs against `ready-firm` rather than WHOLE01: one financial
  year and twelve periods, not three and thirty-six.
- **27.23j**'s locked half needs something posted. `ready-firm` posts a
  receipt, which holds **Accounts receivable** and **Cash** at one line each,
  and adds a `VIEWER` for the read-only half.
- **27.36d4** named WHOLE01 and MEDI01 as firms sharing a store; they do not.
  Only `firm_shared` holds more than one firm, so the case uses the fixture's
  own **TESTSH1** and **TESTSH2** there.
- **27f**: only a platform administrator writes definitions and rules (a firm
  administrator gets 403), and the **product** form offers only fields a
  Mandatory Attributes rule names. Four plan rows met product defects, written
  up as D-27-1 to D-27-4 at the end of the Custom fields cases and not fixed.

| Old row | Case |
| --- | --- |
| 27.1, 27.2 | TC-FIRM-001 |
| 27.3, 27.4, 27.8, 27.10, 27.15, 27.16 | TC-FIRM-002 |
| 27.5, 27.6, 27.7, 27.9 | TC-FIRM-003 |
| 27.11, 27.12, 27.13 | TC-FIRM-004 |
| 27.14 | TC-FIRM-005 |
| 27.17 | TC-PLAT-002 |
| 27.18, 27.19, 27.20 | TC-FIRM-012 |
| 27.21, 27.22, 27.26a | TC-FIRM-016 |
| 27.23, 27.23a, 27.23b | TC-FIRM-007 (the 403 half of 27.23a: TC-FIRM-016) |
| 27.23c, 27.23d | TC-FIRM-008 |
| 27.23e | TC-FIRM-006 |
| 27.23f, 27.23h | TC-FIRM-009 |
| 27.23g | TC-FIRM-010 |
| 27.23i | TC-FIRM-011 |
| 27.23j | TC-FIRM-015 |
| 27.24, 27.25 | TC-FIRM-013 |
| 27.26 | TC-FIRM-014 |
| 27.27, 27.28, 27.29, 27.30 | TC-FIELD-001 |
| 27.31 | TC-FIELD-002 |
| 27.32 | TC-FIELD-003 |
| 27.33 | TC-FIELD-004 |
| 27.34, 27.35 | TC-FIELD-005 |
| 27.36 | TC-FIELD-006 |
| 27.36a, 27.36b | TC-FIELD-007 |
| 27.36c | TC-FIELD-008 |
| 27.36d | TC-FIELD-009 |
| 27.36d2 | TC-FIELD-010 |
| 27.36d3 | TC-FIELD-011 |
| 27.36d4 | TC-FIELD-013 (the `TAX_PROFILE` half is not a case: its `PUT` needs the whole profile, components included) |
| 27.36e | TC-FIELD-012 |
| 27.37 | TC-FIELD-014 |

## Appendix — driving the API by hand

For the **(HTTP)** cases. See `.claude/skills/run-app` for the full recipe.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"whole01.sales1@agency.local","password":"DemoAdmin@12345"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

# /me/firms, **not** /firms. `GET /api/v1/firms` is platform-only and answers
# 403 for every firm user, including the token above -- so a recipe built on it
# fails on the step before the one you are testing. `/me/firms` returns
# {id, code, name, is_primary}; the firm id is `id`.
FIRM=$(curl -s http://localhost:8000/api/v1/me/firms \
  -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])")

curl -s -w "\nHTTP %{http_code}\n" -X POST \
  http://localhost:8000/api/v1/document-framework/numbering-rules \
  -H "Authorization: Bearer $TOKEN" -H "X-Firm-ID: $FIRM" \
  -H "Content-Type: application/json" -d '{...}'
```

*Corrected 2026-09-15: this read `FIRM=<the WHOLE01 id from GET /api/v1/firms>`,
which no firm token can call.*

A platform caller is the other way round — `/api/v1/firms` lists every firm and
`/me/firms` returns only the ones they are a member of, which for
`platform-admin` is none. Pick the route that matches the token in your hand.

**Never write a token to a file inside the repo.** A previous run committed one;
`.tok` and `uvicorn-*.log` are in `backend/.gitignore` because of it.

Every response carries a `requestId`. Quote it when reporting anything — it
joins the screen to the server log.
