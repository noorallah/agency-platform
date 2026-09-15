# Manual UI test plan

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

All as `whole01.admin` in WHOLE01. Price Lists, Promotions, Commission and Targets are tabs of the **Sales** module (a flat list); Loyalty is a tab of **Masters**; the promotion and loyalty reports are entries of **Reports → Operational Reports** or **Financial Reports** (two flat lists, no parameters). Seed facts, verified against the running backend on 2026-09-13: `STANDING` breaks 0 → 2%, 15 → 4.25%, 18 → 6.75% on DETER1K; `BULK5` has two revisions (5% to 2025-03-31, 7.5% from 2025-04-01), 34 claims across both; `BIGORDER` takes 200 off a bill of 4,500 or more and **ends the stack**; `WELCOME` is coupon-only at 2.5% with codes `WELCOME10` (4 claims) and `WELCOME10B` (1 claim -- your section 9 order, saved with that code); the loyalty scheme gives 2 points per 100, worth 1 each, expiring after 24 months, 50 needed before spending; `whole01.sales1` is **Asha** (15% of what is collected on DETER1K, 4% on everything else; the seeded DETER1K rule measures **value**, not margin) and `whole01.sales2` is **Bala** (a ladder: 2% to 50,000 then 4%, nothing below 1,000, 2% bonus when the target is met); two payouts are seeded for April to June 2026, Asha's paid and Bala's approved. On the collected basis Asha came out at **6.07%** (5.8% before section 9's receipts) and Bala at exactly **2.0%**, re-derived on the evening of 2026-09-13. Credit Notes, Proforma, Price Lists, Promotions, Commission and Targets are children of the sidebar entry called just **Sales** (under Masters, above Quotations).

| # | Case | Expected |
| --- | --- | --- |
| 10.1 | Sales → **Price Lists**. Select `STANDING` (do not double-click yet). | The pane on the right reads `STANDING · applies to Everyone`, "In force from 2000-01-01", and under **Rates** three lines for DETER1K: `2%`, `from 15: 4.25%`, `from 18: 6.75%`. The grid's **Products** column reads 3 (it counts rate rows). |
| 10.2 | Double-click `STANDING` (or the row's pencil) → **Add product**: Product `DETER1K`, **From qty** 25, **Discount %** 8, **Save**. Then Quotations → New Quotation for `WHOLE01C01`, `DETER1K` qty 30, Create draft, Revise to read the helper. Afterwards remove the 25 break again. | Toast "Price list saved."; selected, the pane shows a fourth rate line `from 25: 8%`. The quotation still reads "Last priced at **7.5**% by a promotion": `BULK5` outranks the list at 25 and above. *(Seeing the list take effect would mean ending BULK5, and editing an active offer makes a new revision that cannot be taken back, so that half is left to `test_a_promotion_reaches_a_quotation_line` and the pricing unit tests.) Remove the 25 break afterwards: double-click STANDING, the row's ✕ (tooltip "Remove this rate"), Save -- or it prices every later line of 25 or more.* |
| 10.3 | Sales → **Promotions** (Offers). | `BULK5` appears as **two rows**: Gives `5% off the line` In force `2024-04-01 to 2025-03-31`, and `7.5% off the line` `From 2025-04-01`. Select the second: the pane reads "BULK5 · revision 2 · applies at 10" and "Applies when: line_quantity GREATER_OR_EQUAL 25.0000" (the condition prints raw). Edit it, change nothing but the Description, Save: toast "Promotion BULK5 saved as a new revision; the one you opened is now inactive." and a third BULK5 row appears -- an active offer is superseded, never rewritten. This is permanent: 10.4 then counts **3** versions. Press Cancel instead of Save to keep the seeded two. |
| 10.4 | Reports → **Operational Reports** → **Promotion performance**. | One row per offer: `BULK5` with Version count **2** (**3** if you saved the edit in 10.3), Claimed count **34**, Benefit amount 12,126.16, Customer count 4 -- the revisions collapsed to one row. `BIGORDER` 23 claims, `WELCOME` 5 (4 seeded plus your section 9 order), `CLEARANCE` 0 -- it never applies, because BIGORDER ends the stack before it on every large order. |
| 10.5 | Reports → Operational Reports → **Coupon performance**. | Two rows: `WELCOME10` (promotion WELCOME) with Claimed count 4 and 2 customers, and `WELCOME10B` with **1** -- your section 9 order SO-2026-2027-000020, saved with that code. A code nobody has presented is still listed, at 0. |
| 10.6 | Reports → Operational Reports → **Promotion claims**. | One row per claim with Promotion code, Coupon code, Customer name, Document type (always SALES_ORDER -- only orders claim), Document number, Redeemed on, Benefit amount and Status (CLAIMED / PENDING / REVERSED). Your section 9 order is the top row: `WELCOME`, coupon `WELCOME10B` (the code it was last saved with), Vijaya Super Stores, SO-2026-2027-000020, 25.20, CLAIMED. **62 rows** in all on 2026-09-13 -- BULK5 34 + BIGORDER 23 + WELCOME 5, the same counts 10.4 shows. |
| 10.7 | Sales Orders → New Order for `WHOLE01C01`: `DETER1K` qty **60** at 84 (gross 5,040), Create draft, Edit to read. | Under the line's blank box "Last priced at **7.5**% by a promotion" (BULK5, not CLEARANCE's 1% at 40+: promotions apply in priority order and BULK5 is first), and the **Discount on the whole order** box is blank with the helper "Last taken off: 200 by a promotion. Blank prices it afresh." -- `BIGORDER` took the bill. *(Until 2026-09-13 the box was refilled with 200 and the Coupon box opened empty, so saving the order again switched both offers off; press **Save order** unchanged and Edit again to see both survive.)* `CLEARANCE` (priority 30) did **not** apply: BIGORDER (priority 20) ends the stack. Cancel the order afterwards (Cancel works on this screen since 2026-09-13). *(Driven through `POST /api/v1/promotions/simulate` on 2026-09-13: BULK5 and BIGORDER applied, line discount 378.00, bill discount 200.00.)* |
| 10.8 | Masters → **Loyalty**. Then Reports → Financial Reports → **Loyalty balances**. | The Loyalty page shows the scheme banner ("2 points per 100, worth 1 each and expire after 24 months. At least 50 before any can be spent." -- it printed "2.0000 ... 1.0000" until 2026-09-13) and the ledger (On, Customer, Why, Against, Points, Worth, Expires). The balances report lists each customer's Points and Amount: Anand Agencies 1,311.12, Classic Departmental Stores 1,085.27, Revise Check 2 384.79, Vijaya Super Stores 354.64 (2026-09-13). Pick one and add up its EARNED/REDEEMED/EXPIRED rows in Reports → Operational → **Loyalty movements**: the sum is the balance. |
| 10.9 | Sales Invoices → select an APPROVED invoice of `WHOLE01C02` (Anand Agencies, ~1,300 points) with something still owed (e.g. SI-2026-2027-000004, 3,698.95) → **Use points**: in "Use points on SI-..." type 100 → **Use them**. | Toast "100 points used on SI-...". Finance → Journal Entries: the top row is `LOY-RED-SI-...`; select it → **View** (or double-click): Dr **2600 Loyalty Payable** 100.00 / Cr **1100 Trade Receivables** 100.00. Finance → Receipts → **Record Receipt** → Received from `WHOLE01C02` (then Cancel the dialog): that invoice's **Outstanding** is 100 lower (3,598.95 for SI-2026-2027-000004); its Grand Total and tax are unchanged -- the bill is **settled**, not discounted. Customers: Anand's Outstanding is 100 lower too. *(Until 2026-09-13 the receipts list still showed the full amount after points were spent, so a receipt could collect that 100 again.)* |
| 10.10 | **Use points** again on the same invoice, type **5000** (more than the ~1,211 Anand holds after 10.9) → **Use them**. | Refused outright, not trimmed: "That customer holds 1211.1153 points, not 5000.0000." No journal entry, no balance moves. |
| 10.11 | Reports → Operational Reports → **Points about to lapse**. | Rows per unspent batch within 90 days -- Customer name, Points (what is *left* of the batch after spending), Amount, Earned on, Expires on, Days remaining -- ordered by expiry then customer. Rows with a **negative** Days remaining are batches already past their date that no expiry sweep has taken yet -- the balance still counts them until the sweep runs. On 2026-09-13 after 10.9: 6 rows, Anand 60.16 (2026-05-22, −114), Anand 160.59 (−93), Classic 54.12 (−63), Anand 69.39 (29), Classic 160.16 (39), Classic 160.59 (60). Anand's first batch was 160.16: the 100 points spent in 10.9 came out of the **oldest** batch first, even one already past its date. |
| 10.12 | Sales → **Commission** → **Collected** view: Collected from `2024-04-01` to today, **Show**. Divide each salesman's Commission by their Collected. | Asha's rate is **neither** of the two that govern her: a blend of 15% of the money collected on DETER1K and 4% of the money collected on everything else (6.07% on the evening of 2026-09-13, after section 9's receipts; it moves with every receipt, so check the shape rather than the figure). Her Paid on reads "Money collected", Target "Met" -- Sales → **Targets** → **Achievement** (from 2026-04-01 to 2026-09-08) shows why: target 20,145.00 invoiced, achieved 25,181.35 (125%). |
| 10.13 | Same report, Bala. | Exactly **2.00%** -- the bottom band of his ladder; a round number precisely because a ladder's floor is. Target "Missed": Targets → Achievement shows 19,659.00 wanted, 15,122.46 invoiced (76.9%), 4,536.54 short, so his 2% target bonus is not added. |
| 10.14 | Sidebar **Sales** → **Commission** → **Payouts** view (seeded: Asha PAID and Bala APPROVED for 2026-04-01..2026-06-30). **Accrue period** → in "Accrue a period" From `2025-05-01` To `2025-05-31` → **Accrue**. On Bala's new DRAFT row click **Approve**, then **Pay** ("Pay Bala (WHOLE01 Sales)": Paid on today, **Paid from** a cash or bank account, **Record payment**). **Cancel** Asha's draft. Then **Accrue period** for May 2025 again. | Toast "2 payout(s) accrued as drafts." -- Asha 574.19, Bala 27.06. Approve toast "Bala (WHOLE01 Sales) — approved. The cost and the debt are on the ledger."; Pay toast "... — paid." Cancel toast "... — cancelled. The period is free to accrue again." Finance → Journal Entries shows two references for Bala's payout, `COMM-202505-<id>` (approval: Dr Commission Expense / Cr Commission Payable) and `COMM-202505-<id>-PAY` (Dr Commission Payable / Cr the account paid from) -- select one → **View**. A `-REV` entry appears only when an **approved** payout is cancelled; cancelling Asha's draft posts nothing. *(May 2025 is free to accrue: its two earlier accruals are CANCELLED, and a cancelled payout holds no claim.)* Pay on a DRAFT is not offered; **(HTTP)** paying it answers 422 "Only an approved payout can be paid...". Accruing May 2025 again is refused: "A commission payout already covers part of that period for this salesman (2025-05-01 to 2025-05-31)." |
| 10.15 | Sign out; sign in as `whole01.sales1@agency.local` (Asha, SALES_EXECUTIVE) and expand sidebar **Sales**. Sign back in as the administrator afterwards. | **Commission is not listed at all**, nor Targets, Price Lists or Promotions -- a SALES_EXECUTIVE holds none of their view codes. **(HTTP)** with that token, `POST /api/v1/commission/payouts/{id}/approve` and `/pay` answer **403**, and so does `GET /api/v1/commission/payouts` (driven 2026-09-13). Whoever states a debt must not move the cash. |

## 11. Territory, routes and beats

All as `whole01.admin`. Geography, Route Types, Beat Plans, Call Lists, Coverage and Route Builder are children of the sidebar entry called just **Sales** (under Masters, above Quotations). Seed: `WHOLE01-RGN` Chennai Region → `WHOLE01-T-N` North Zone and `WHOLE01-T-S` South Zone → routes, as the store holds them on 2026-09-13: `WHOLE01-R-N1` North Sales Beat (weekly, Mon/Wed/Fri, **Asha**, round: Revise Check 2 then Classic Departmental Stores), `WHOLE01-R-N2` North Collections (fortnightly, Tue/Thu, **Bala**, round: Vijaya Super Stores), `WHOLE01-R-S1` South Sales Beat (weekly, Tue/Thu, **Asha**, round: Anand Agencies). No beat plan has stops of its own, so a call list calls the route's round. Beat plans: one weekly plan per working day per route (`WHOLE01-BP-R1-MON`, `-R1-WED`, `-R1-FRI`, `-R2-TUE`, `-R2-THU`, `-R3-TUE`, `-R3-THU`), `WHOLE01-BP-COLL` fortnightly on Tuesdays from 2026-04-07, and `WHOLE01-BP-MTH` monthly on the 2nd Tuesday.

| # | Case | Expected |
| --- | --- | --- |
| 11.1 | Sales → **Geography**. Select any row: the right-hand **Territory tree** panel. **Expand all**. The panel is narrow, so click the icon beside its title (tooltip "Open the tree in a larger window", added 2026-09-13): the whole tree opens in a window, already expanded, with Expand all / Collapse all and each node's menu (Filter list, Quick create child). Try Collapse all / Expand all, then Close. | Chennai Region (Region) → North Zone and South Zone (Territory) → North Sales Beat and North Collections under North, South Sales Beat under South (Route); each node shows its code and full path. The grid's Hierarchy column carries the full path for every row. |
| 11.2 | Double-click `WHOLE01-R-N1` (North Sales Beat) → **Details** tab; then glance at **Customers** and **Salespeople**. | Section **Route**: Route type **Sales Route**, Visit frequency **Weekly**, Working days **Mon, Wed, Fri**, Runs from **Always**, Runs until **No end**. Counts above: 2 customers, both active, Salespeople 1. Customers tab: Revise Check 2, Classic Departmental Stores. Salespeople tab: Asha (WHOLE01 Sales). |
| 11.3 | Sales → **Call Lists**. It opens on today (Back to today greyed out). Use › (**Next day**) or the date button to land on a **Monday**, Salesperson **Everyone**; then **Back to today**. | The date button reads "Monday 2026-09-14" (the weekday was not shown until 2026-09-13). Status bar "1 of 9 plan(s) run on Monday 2026-09-14". On any day but today the badges read **Runs on Monday** / **Not on Monday** (they said "Runs today" whatever day was chosen until 2026-09-13). `WHOLE01-BP-R1-MON` is badged **Runs on Monday** and calls Revise Check 2 then Classic Departmental Stores (the route's round, in order). Every other plan is badged **Not on Monday** with its reason, e.g. `WHOLE01-BP-R1-FRI` "Runs on Fridays; this is a Monday." |
| 11.4 | With the date button pick **2027-01-12** (a second Tuesday that is also an even fortnight from 2026-04-07), then **2026-10-13**, then **2026-10-20**. | On 2027-01-12, "4 of 9 plan(s) run on Tuesday 2027-01-12": `WHOLE01-BP-R2-TUE` and the fortnightly `WHOLE01-BP-COLL` (both Vijaya), `WHOLE01-BP-R3-TUE` and the monthly `WHOLE01-BP-MTH` (both Anand) read **Runs on Tuesday**. On **2026-10-13** (a second Tuesday in the off fortnight) COLL reads **Not on Tuesday**, "Runs every other Tuesday counted from 2026-04-07; this is the week between."; on **2026-10-20** MTH reads "Runs on the second Tuesday of the month; this is the third." *(Both gave no reason at all until 2026-09-13.)* |
| 11.5 | Sales → **Route Builder**: **Route being built** `WHOLE01-R-N1`. The right shows the round (1. Revise Check 2, 2. Classic Departmental Stores). Tick **On no route yet**, **Find**, double-click `SN` on the left to add it (stop 3), drag it by its ≡ handle above the first stop, **Save round and order**. | Toast "3 outlet(s) on North Sales Beat, in order." Choose the route again: 1. SN, 2. Revise Check 2, 3. Classic Departmental Stores -- the stops moved without a collision. Afterwards ✕ **Remove from round** on SN and Save: "2 outlet(s) on North Sales Beat, in order." |
| 11.6 | Route Builder: choose `WHOLE01-R-N1`, let the round load on the right, change nothing, **Save round and order**. | Toast "2 outlet(s) on North Sales Beat, in order."; choosing the route again shows the same two stops in the same order. The status bar says "Saving replaces the whole round with the list on the right." -- which is why the screen clears the panel before reading and refuses to save a round it could not read ("This round could not be read, so it cannot be saved over."). |
| 11.7 | Sales Orders → **New Order** for `WHOLE01C02` (Anand, on South Sales Beat, covered by **Asha**): **Ships from** `WHL_DC`, **Salesman** `Bala`, one line `DETER1K` qty 1, **Create draft**. | Refused, in the editor's banner: "The selected salesperson is not assigned to this territory." -- nothing is saved (driven over HTTP 2026-09-13: no order created). Choosing Asha saves ("Order drafted..."); leaving Salesman blank saves and, reopened, the order's salesman is Asha, supplied by the customer's route. Cancel the saved drafts afterwards (Cancel works on this screen since 2026-09-13). |

## 12. Compliance

All as `whole01.admin` in WHOLE01. E-Invoice, GST Returns and TCS are children of the sidebar entry called just **Sales** (under Masters, above Quotations). Facts the rows rest on, re-derived from the running backend on the evening of 2026-09-13 (after the owner's sections 9-11): WHOLE01 holds **13** e-invoice registrations and 6 e-way bills, every one SANDBOX; customer `OB-REV2` (Revise Check 2) has **no GST number** and no PAN; `WHOLE01C01` Vijaya has a GSTIN and **no PAN** (so TCS at 1%), `WHOLE01C02` and `WHOLE01C03` have both; the firm's **TCS is switched on** by the seed (threshold 5,000, 0.1%), so the "disabled by default" the model would give a fresh firm is not what you will see; every accounting period is OPEN. Every screen reads once when opened: **Refresh** after acting elsewhere.

| # | Case | Expected |
| --- | --- | --- |
| 12.1 | Sales → **GST Returns**. The **From** and **To** boxes hold the current month and are chosen, not typed: click ‹ (**Previous month**) once to reach August 2026 (**From** `2026-08-01` **To** `2026-08-31`; the history bills on the 12th and 22nd of every month), or click either box for one calendar in which you tap the first day and then the last (**Use this period**). Each change reads the return again. **GSTR-1** segment selected. | Heading "Filing as <the firm's GSTIN>". Four tables: **B2B — registered buyers, invoice by invoice** (Invoice, Buyer GSTIN, Taxable, CGST, SGST, IGST), **B2CS — unregistered, summarised by place and rate** (Place, Rate, ...), **CDNR — credit notes to registered buyers**, **HSN summary**. No B2CS row has a blank Place. A fifth table, **Invoices without a place of supply — named here, not filed**, lists any invoice the return could not place rather than filing it blank; for August it reads "Nothing in this section." The status bar says "Derived from the documents on every read, never stored." August 2026 on the day: **B2B** one invoice, SI-2026-2027-000009 Vijaya Super Stores, taxable 3,887.08, CGST 349.84, SGST 349.84; **B2CS** one row, Place 29, 18%, taxable 2,164.50 (Revise Check 2's SI-2026-2027-000008); **CDNR** nothing; **HSN** 330510 Shampoo Bottle 180ml, 37 units, taxable 6,051.58. *(September carries the section 9 invoices, and the two credit notes appear under CDNR.)* |
| 12.2 | Sales Invoices → select **SI-2026-2027-000009** (Vijaya, August, paid and registered) → **Cancel**. Then select **SI-2026-2027-000008** (Revise Check 2, August, unpaid, not registered) → **Cancel**: refused too, by its seeded sales return. So Sales Returns → **SR-2026-2027-000002** (2026-08-19, against SI-...-000008) → **Cancel** (reason); then SI-...-000008 → **Cancel** again. Back on GST Returns → **Refresh**. | SI-...-000009 is **refused**, naming what rests on it: "SI-2026-2027-000009 cannot be cancelled while it has money applied from RC-2026-2027-000008; its registration with the tax authority. Reverse or cancel those first." *(Until 2026-09-13 nothing was checked: a paid or registered bill cancelled, leaving the receipt clearing a cancelled bill and the customer credited twice.)* SI-...-000008 is refused with "...while it has sales return SR-2026-2027-000002. Reverse or cancel those first."; once the return is cancelled (its stock, credit and journals undone) the invoice cancels. The B2CS row is gone and the HSN taxable falls to 3,887.08 -- the return is derived on every read, never stored. |
| 12.3 | Switch the segment to **GSTR-3B**, same month. | **3.1(a) — outward taxable supplies** with Taxable, IGST, CGST, SGST, Cess; **Credit notes already deducted above**; and a sentence about the inward side the system does not know. Add up GSTR-1's B2B, B2CS and CDNR taxable values by hand: they equal 3.1(a)'s Taxable -- 3,887.08 after 12.2's cancellation (6,051.58 before). The inward side reads "Not derived: the purchase side files this." *(Nothing on screen reconciles the two for you; 3B is aggregated from the documents, not parsed out of GSTR-1.)* |
| 12.4 | Sales → **E-Invoice**. | A banner: "References marked sandbox are a rehearsal: nothing was filed with the tax authority..." The grid has **Invoice**, **Customer**, **Reference**, **E-way bill** columns and an actions column; every Reference is an `SBX...` value, cut short in the cell -- hover it for the whole `SBX... (sandbox — nothing filed)`. 13 rows for WHOLE01; six have an E-way bill reference, seven show —. |
| 12.5 | **Register an invoice** → in the **Sales invoice** picker choose one of `OB-REV2`'s approved invoices (items read `SI-... — <customer> — <total>`; pick one ending in **Revise Check 2**, e.g. SI-2026-2027-000007. The customer was not shown until 2026-09-13) → **Register**. | Refused **locally**, in an error toast, with "This invoice cannot be registered yet: the customer has no GST number." No row is added, no portal code appears. *(If the picker offers no OB-REV2 invoice, approve one of its drafts on Sales Invoices first.)* |
| 12.6 | Select a registered row with an empty E-way bill cell -- e.g. **SI-2026-2027-000003**, Vijaya Super Stores -- and click **Raise bill** on the toolbar (the row's own **Raise e-way bill** button is in the last column, off the right edge on a laptop; scroll right to see it): **Distance (km)** 120, **Moving by** Road, **Vehicle number** `TN01AB1234`, **Raise**. Then, with the row still selected, **Cancel bill** on the toolbar (or the row's **Withdraw bill**), give a reason. | Toast "E-way bill raised."; the row's E-way bill cell fills with an `SBX...` reference (hover it for the whole). Leaving the vehicle blank on a road movement is refused before sending: "Goods moving by road need a vehicle number on the bill." Raising a bill against an **unregistered** invoice is not offered on screen; **(HTTP)** `POST /api/v1/einvoice/invoices/{id}/eway-bill` on one answers 422 "Register the invoice before raising its e-way bill...". Withdraw toast "E-way bill withdrawn." |
| 12.7 | Sales → **TCS**. | The banner reads "Collecting under section 206C(1H) • 5000.00 per buyer per year, then 0.100% (1.000% without a PAN)" and the register lists the receipts already charged (Receipt, Buyer, On, Received, Paid before, Chargeable, Rate, Collected, Status). The register holds 38 rows on the day, the newest being your section 9 receipts from Vijaya -- e.g. RC-2026-2027-000012: Received 341.61, Rate 1.000% (no PAN), Collected 3.42. **Settings** opens "Tax collected at source" with the switch **Collect under section 206C(1H)** on, **Preceding year turnover** 150,000,000, **Threshold per buyer, per financial year** 5,000, **Rate %** 0.1, **Rate % without a PAN** 1.0 -- close it without saving. *(A firm the seeder never touched starts switched off; every demo firm is on.)* |
| 12.8 | Finance → Receipts → **Record Receipt** for `WHOLE01C03` (Classic, has a PAN): **Amount** 6000, **Method** Bank, type 6000 into the **Apply** box of **SI-2024-2025-000012** (8,008.14 owed), **Record receipt**. Back on Sales → TCS → **Refresh**. | The dialog's TCS notice (under Against order) read "Tax collected at source: 6.00 on 6000.00 above the threshold, at 0.100%..." -- Classic had already paid 6,419.17 this financial year, past the 5,000 threshold, so all of it is chargeable. The register's top row: Received 6,000, Paid before 6,419.17, Chargeable 6,000, Rate 0.1%, Collected 6.00, COLLECTED. Finance → Journal Entries shows **two** entries: the receipt `RC-...` and a separate `TCS-RC-...`, whose **View** reads Dr 1100 Trade Receivables 6.00 / Cr 2500 TCS Payable 6.00. Customers → **Refresh** → C03: Outstanding fell by 5,994.00, the receipt less the TCS -- 17,901.78 → **11,907.78** in the owner's run on 2026-09-14. |

## 13. Finance, reports and platform

As `whole01.admin` unless a row says otherwise. Finance is a flat list of tabs; Reports has two tabs, **Operational Reports** (40 entries) and **Financial Reports** (16); accounting periods live under **Masters → Configuration → Financial Years**, not under Finance. Trial Balance, Profit & Loss and Balance Sheet each take an **Accounting period** dropdown: pick the **same** period on all three when comparing them. Facts the rows rest on, re-derived from the running backend on 2026-09-14 after sections 9-12: WHOLE01's financial year FY2026 runs April 2026 to March 2027 in twelve periods P01-P12, all OPEN; the chart holds `1000 Cash`, `1010 Bank` and `5000 Purchases` and no `9999`; cost centres `SALES`, `OPS` (and an inactive `CC14E90`) and profit centres `NORTH`, `SOUTH` are already seeded; every WHOLE01 role is a system role.

| # | Case | Expected |
| --- | --- | --- |
| 13.1 | Finance → **Chart of Accounts** → **New**: Account Group chip **EXP · Direct Expenses**, Code `9999`, Name `Manual test account`, Account Type EXPENSE, Save. Then select it → **Edit**. | The row appears (Code, Account, Type, Status). The group must share the account's type -- any other chip is refused with "A ledger account must share its group's account type." The toolbar offers no Delete. On Edit, Account Group, Account Type and Code are fixed (chips do not respond, the dropdown does not open) and only Name, Description, the two "Requires a …" boxes and **Active** change; deactivating is the Active switch. *(Until 2026-09-14 the chips read only CA, CL, EQ, EXP, REV, and on Edit the group and type looked changeable but were silently not saved -- #369, #370.)* |
| 13.2 | Finance → **Trial Balance**, Accounting period `September 2026`. | Columns Code, Account, Type, Opening, Debit, Credit, Closing, a **Total** row, and a chip reading **Balanced** -- 19 accounts, total debit and credit both **660,640.05** on the day. Every account carrying a balance as at the period is listed, not only ones posted in it. *(Until 2026-09-14 this read "Out of balance by 58,719.61": a posting dated into an earlier month -- a cancelled August bill, an old commission payout -- never moved later months' openings. The engine carries it forward now and migration `20260914_0136` re-chained the stored balances.)* |
| 13.3 | Finance → **Profit & Loss** and **Balance Sheet**, same period. | P&L: Income and Expenses sections with totals and a **Net profit or loss** row (This period, Year to date). Balance Sheet: Assets, Liabilities, Equity with **Retained earnings brought forward** and **Result for the year**, then **Liabilities and equity**, chip **Balanced**. They agree: Total assets = Liabilities and equity; the sheet's Result for the year = P&L's Year to date net; the trial balance's total debit = total credit. On the day: P&L net **-5,200.30** this period and **-4,219.73** year to date; Balance Sheet Total assets **496,470.07**, Retained earnings brought forward 42,223.92, Result for the year -4,219.73, Liabilities and equity **496,470.07**. |
| 13.4 | Finance → **Journal Entries**. Search a document of each kind by its number (e.g. `RC-2026-2027-000013`, `TCS-RC-2026-2027-000013`, `COMM-202505-471a0b0e-PAY`, `LOY-RED-SI-2026-2027-000004`, `CN-2026-2027-000003`, `SR-2026-2027-000005`, `SI-2026-2027-000013`, `DN-WHOLE01-BR_NORTH-2026-2027-000001`, `Stock adjustment`, `PR-2026-2027-000003`, `GRN-WHOLE01-BR_NORTH-2026-2027-000005`, `PI-2026-2027-000006`, `JV-CENTRES-1`) and open it with **View**. | The row's subtitle is the entry's **description**; the module is on the View dialog's first line, "POSTED · posted by <module> · <description>" (a hand-written entry has no "posted by"). | WHOLE01 holds 387 entries on the day from **twelve** posting modules -- delivery_note 62, loyalty 57, settlements 55, sales_invoice 54, tcs 42, goods_receipt 36, purchase_invoice 30, sales_return 26, credit_note 11, purchase_return 7, commission 5, inventory 1 -- and **one** written by hand (the seeded manual expense). WHOLE01 has no customer opening balance, so no `customers` entry; the newest rows are RC-2026-2027-000013 and TCS-RC-2026-2027-000013 from 12.8. *(There is no source-module filter; the search box matches reference or description -- BACKLOG §31.15.)* |
| 13.5 | Journal Entries → **New Entry**: Accounting period `June 2026`, Journal type and Voucher type any, Date `2026-06-15`, Reference `MT-CLOSE-1`, two lines (`5000 Purchases` debit 100, `1000 Cash` credit 100), **Save Draft**. Then Masters → Configuration → **Financial Years**, select the year, on **June 2026** click **Close** (toast "June 2026 is closed. Nothing further can be booked into it."). Back on Journal Entries select the draft → **Post**. Afterwards reopen the period (**Open**). | The post is refused: "Accounting period P03 is closed and cannot accept postings." (the code is the period's; June is P03 in an April year). After **Open**, Post succeeds with "Journal entry MT-CLOSE-1 posted." Trial Balance for **September 2026** still reads **Balanced**: the June entry is carried into every later month. *(No seeded period is closed, so the row closes one itself; the New Entry dialog offers only OPEN periods, which is why the draft is written first.)* |
| 13.6 | Reports → **Operational Reports** and **Financial Reports**: open every entry in both lists (56). | Each renders with `N row(s)` in the header; an empty one reads "Nothing to report / This firm has nothing matching it yet." rather than a blank grid. The two return reports are now **Purchase returns by product** and **Sales returns by product**, and the order-progress report is **Delivery progress by order** (it was "Part-dispatched notes" until 2026-09-14, though it lists every live order -- 65 -- with Completed, Partial or Pending). Exactly **six** are empty in WHOLE01 on the day: Dispatches not yet completed, Damaged on receipt, Rejected on receipt, Invoices not yet approved, Supplier invoices not yet approved, Overdue purchase invoices. The largest are Sales order register 72, Promotion claims 64, Delivery note register 62. |
| 13.7 | Type in any search box, move to another screen, press **Ctrl+K**, type `DETER`, **Search**; select the result → **Open Details** (or double-click it). | The dialog opens wherever keyboard focus is. One result, **Detergent Powder 1kg** (a product), with "1 result found." and no error. Open Details closes the search and lands on **Masters → Products** -- the list, not that product's record. *(Until 2026-09-14 Ctrl+K did nothing once focus had left the shell, and Open Details navigated behind a search dialog that stayed open -- #371, #372.)* **(HTTP)** `GET /api/v1/search?query=DETER` answers 200 (the parameter is `query`; `q` answers 422) -- the dialog would fall back to an inventory-only search if the route failed, so the API check is the one that proves there is no 503. |
| 13.8 | Settings → **Audit Logs** with WHOLE01 selected; type `finance.accounting_period.updated` in **Action** → **Search**. Then sign in as `master.ops` on **Platform** (no firm), open it again and run the same search. | With a firm: the caption "The trail for MarketBridge Wholesale Traders Private Limited. Platform administration and other firms keep their own, in their own stores." and that firm's rows; the search leaves the two rows from 13.5 (June closed and reopened). The only filters are the **Action** and **Entity type** text boxes, matched exactly -- `finance` alone finds nothing. On the platform the same search finds nothing, because finance events stay in the firm's trail. Without a firm, as a platform administrator: "The platform trail: users, roles and firm administration..." As a firm admin without a firm the trail is refused (403 over HTTP). |
| 13.9 | Administration → **Users**, then **Roles & Permissions** (both halves). Select a **system** role (subtitle "System role", e.g. `SALES_MANAGER`) and double-click it. Then **New**: Role code `manual-test-role`, Name `Manual test role`, Permissions tick `CUSTOMER_VIEW`, Save; select it → **Edit** → tick one more permission → Save. | All load; the Roles grid reads Code, Name, Assignments, Status. On the system role the toolbar's Edit is disabled and double-clicking opens the read-only view whose subtitle reads "SALES_MANAGER — Sales Manager · System role · System roles cannot be modified." *(Until 2026-09-15 the double-click opened with no reason given -- #375.)* `CUSTOMER_VIEW` is a chip under CUSTOMER in the **New** form's Permissions section, not something to search the Roles grid for (that finds the VIEWER role). The new role's subtitle reads "Custom role" and its second save keeps both permissions. *(WHOLE01 holds only the twelve system roles, so the custom one is made here; the code must be lowercase.)* |
| 13.9b | Look at the Administration sidebar | **One** entry, **Roles & Permissions**, where Roles and Permissions used to be two. Open it: the Roles grid with a Roles / Permissions strip above it. Switch to Permissions: the sidebar entry stays highlighted and the heading still reads Roles & Permissions. |
| 13.9c | Ctrl+K, type a permission code, open the result | Lands on the **Permissions** tab directly, not on Roles -- each half keeps its own address. Sign out and in: the last screen restores to the same half. |
| 13.9c2 | Sign in as `elec01.admin`, Inventory → **Batch & Serial** → **Serial Numbers** | Twenty serials, `MIX500-2026-0001` to `MIX500-2026-0020`, all AVAILABLE, warranty 2026-09-08 to 2027-09-08. Masters → Products → `MIX500` shows **Track serial** on. |
| 13.9c3 | As `medi01.admin`, Masters → Customers → toolbar **Settings**. Then Sales Orders → select **SO-2026-2027-000010** (CityMed Clinic, DRAFT, 4,353.53) → **Approve**. Then as `food01.admin`, Sales Invoices → the **Sales stages** icon; then Delivery Notes. | "Credit policy" reads **Warn, then block**, Warn at 80, Block at 100; **Cancel**. CityMed Clinic (`MEDI01C03`): credit limit 20,000, outstanding 19,821.33. Sales Orders holds **eight** CityMed drafts. Approve is refused: "CityMed Clinic would be at 120.9% of a 20000.00 credit limit. Collect payment or raise the limit before continuing." and the order stays DRAFT. FOOD01's Sales stages shows **Delivery note** switched off, and so the **Delivery Notes** screen is **not in FOOD01's sidebar** -- a stage the firm does not type is hidden. The notes exist: Reports → Operational → **Delivery note register** reads 49 row(s), one per invoice (Sales Invoices' **Total** card also 49), raised by the service. In WHOLE01, Delivery Notes' status bar reads **62 records** and pages past the first 20. *(Until 2026-09-15 Delivery Notes, Purchase Invoices and Purchase Returns counted only the page on screen, "20 records", with no second page -- #376.)* |
| 13.9d | Finance → **Cost Centres** → New, Code `MT-CC`, Name `Manual test centre`, Save; Finance → **Profit Centres** → New, Code `MT-PC`, Name `Manual test profit centre`, Save. Then New `SALES` on Cost Centres once more. | Both grids list the new row beside the seeded ones (`SALES`, `OPS`, inactive `CC14E90`; `NORTH`, `SOUTH`). The second `SALES` is refused: "A cost centre with this code already exists." Neither grid offers Delete: deactivate with the Active switch on Edit. *(Codes are capitals, digits, `_` and `-`.)* |
| 13.9e | Finance → Chart of Accounts → Edit `5000 Purchases` → tick **Requires a cost centre** → Save. Then Journal Entries → New Entry, choose 5000 on a line | A **Cost centre \*** dropdown appears on that line and on no other; choose `SALES` (seeded). Save with it: posted. **(HTTP)** the same entry without `cost_center_id` on that line: **422**, "Ledger account 5000 requires a cost centre." Untick the flag afterwards. |
| 13.10 | Provoke a desktop report: end **agency_desktop** in Task Manager, start it again and sign in (the queued report is sent then). As `master.ops` open Settings → **Diagnostics**, Source **Desktop**, **Search**; click the group on the left, then the first line under **Occurrences** on the right. Then Source **Server**, open any group's first occurrence. | Desktop: one group, **UnexpectedTermination**, with a count one higher than before the forced close (246× on 2026-09-14 before it); the right pane shows the occurrences / first seen / last seen / versions chips and "showing the newest 50"; the newest occurrence expands to Firm, User and "Leading up to it" breadcrumbs ("Previous session started at … ended without a clean exit. The application was terminated rather than closed.") -- no Request and no stack trace, which a forced close has neither of. Server: the occurrence shows **Request <request_id>** and the stack trace. *(There is no "Help → Report a problem" control; the desktop reports crashes automatically, queued on disk until it can sign in.)* |

---

# Part 3 — Cross-cutting

## 14. Concurrency and two machines

Run these with two clients pointed at one server (or two windows of one client; the second `Start-Process` launch is a second client). Sign both in as `whole01.admin`. An editor that saves from **inside** its dialog -- customer, sales order, sales invoice, product, price list, promotion, coupon, customer group, target, payout adjustment -- shows this sentence on a lost race and keeps the dialog open with the typing in it: `Somebody else saved this <thing> while you were editing it. Your changes are still here and have not been sent. Copy anything you need, then close and reopen to see theirs.` An editor that closes first and saves after -- branch, warehouse, quotation, batch, lot, serial number, beat plan, place, territory, tax component -- cannot keep the typing, so it says so in a red toast instead: `Somebody else saved this <thing> while you were editing it. Your changes were not saved. Open it again to see theirs and redo yours.` Until 2026-09-13 six of them (price list, promotion, customer group, sales invoice, target, packaging level) showed the server's generic "The request conflicts with existing data. Please retry." instead. Server-side facts: driven on 2026-09-13, a second approval of one order and a second accrual of one payout period were both refused rather than answered with a 500, and an unchanged save left the version where it was.

| # | Case | Expected |
| --- | --- | --- |
| 14.1 | On **A** and **B**: Masters → Customers → double-click `WHOLE01C03` (Classic Departmental Stores, phone +919999900001 on 2026-09-14). On A change the phone, **Save**. On B change the phone to something else, **Save**. | A saves ("Customer updated."). B is refused **inside the editor** with the sentence above naming `customer`, the dialog stays open, B's typed phone is still in the box. Cancel B; reopen: A's phone is there. |
| 14.2 | The same on a **sales order** (Sales Orders → `SO-2026-2027-000012`, Anand Agencies, DRAFT → **Edit**, change **Remarks** on both), a **product** (Masters → Products → `TOOTH150`, edit the Description) and a **price list** (Sales → Price Lists, double-click `STANDING`, change the **Name** -- the dialog has no Description). | B refused each time with the sentence naming `sales order`, `product`, `price list`; typing kept, dialog open. |
| 14.3 | On A alone: double-click `WHOLE01C03`, change nothing, **Save**. Then double-click again, **Save** again. **(HTTP)** `GET /api/v1/customers/{id}` twice around it and compare the `ETag`. | Accepted both times. The `ETag` (and `version` in the body) is **the same before and after** -- an unchanged save must not move the version, so a client re-sending the same `If-Match` is still accepted. |
| 14.4 | On A and B: Sales Orders, select `SO-2026-2027-000019` (Anand Agencies, DRAFT, 1,079.42 -- one of the two drafts in WHOLE01 on 2026-09-14) in both grids. **Approve** on A (there is no confirmation). Then **Approve** on B, whose grid still says DRAFT. | A: the grid reloads and the row reads APPROVED (there is no success toast on this page). B: a red toast, either "Only draft sales orders can be approved." (A finished first) or the conflict sentence (both in flight); never a silent no-op and never a 500. Refresh B: APPROVED once. |
| 14.5 | Both clients approve a document that would claim the **last** use of a coupon. | Covered by `test_the_refusal_is_for_the_race_two_orders_priced_before_either_approved` in `backend/tests/unit/test_promotions.py`: the loser is **refused by name**, not silently repriced. The promotion editor has no redemption limit field, so by hand use the coupon's: Sales → Promotions → **Coupons** → `WELCOME10` (offer WELCOME, 2.5% off every line, used 4 times on 2026-09-14) → Edit → **Total claims allowed** `5` → Save. Raise two DRAFT orders for `WHOLE01C01` with **Coupon** `WELCOME10`, one on each client, then approve both: the first approves, the second is refused "Coupon WELCOME10 has been used as often as it allows. Re-save the document to price it without." Clear **Total claims allowed** afterwards and cancel the leftover draft. |
| 14.6 | On A and B: Sales → Commission → **Payouts** → **Accrue period**, From `2025-06-01` To `2025-06-30` on both (no payout covers June 2025 on 2026-09-14; the existing ones are May 2025 and April-June 2026), **Accrue** on A then on B. | A: "2 payout(s) accrued as drafts." B: "A commission payout already covers part of that period for this salesman (2025-06-01 to 2025-06-30)." -- a 409 by name, never a 500. The database holds the rule (`UQ_commission_payouts_period_active`), the service supplies the sentence. **Cancel** A's two drafts afterwards (the row's Cancel action: "... cancelled. The period is free to accrue again."). |

## 15. Permissions

Sign in as `whole01.sales1@agency.local` (Asha, `SALES_EXECUTIVE`: `CUSTOMER_VIEW`, `TERRITORY_VIEW`, `SALES_VIEW` and the three `SALES_*_CREATE` codes -- nothing else). The point is that the **server** refuses, not merely that the button is hidden: every refusal below was driven over HTTP with this user's token on 2026-09-13 and answered `403`. To drive them yourself, sign in with `POST /api/v1/auth/login` (see the appendix) and send `X-Firm-ID: 30c66274-60e9-4789-97d9-138a7a1fdc61`.

| # | Case | Expected |
| --- | --- | --- |
| 15.1 | Look for **Administration** in the sidebar, and Numbering Series under it. | **Administration is not offered at all** -- none of its tabs' codes is Asha's. **(HTTP)** `PUT .../numbering-rules/{id}` → `403`. `GET /api/v1/document-framework/numbering-rules` answers **200**: any member of the firm may read how documents are numbered, and only `SETTINGS_UPDATE` may change it (re-driven 2026-09-14; this row used to claim 403 for the read). |
| 15.2 | Masters → Customers → **Settings** (the credit-policy button on the toolbar). | The dialog **opens read-only**: the fields show the firm's policy but are disabled, **Save** is greyed (only **Close** works) and a notice reads "Changing the policy needs the manage customer settings permission." Somebody the policy warns may read the rule behind the warning. **(HTTP)** `PUT /api/v1/customers/credit-settings` → `403`. |
| 15.3 | Expand **Sales** in the sidebar and look for **Commission**. | **Not in the sidebar** (`COMMISSION_VIEW` missing). Under Sales Asha sees only the territory screens (Geography, Call Lists, Beat Plans, Coverage and the rest, on `TERRITORY_VIEW`); Price Lists, Promotions, Targets, Proforma, E-Invoice and GST Returns are hidden too, each on its own view code -- that is expected, not a fault. **(HTTP)** `POST /api/v1/commission/payouts/{id}/approve` and `.../pay` (any seeded payout id from the admin's Payouts view) → `403`. |
| 15.4 | Look for **Credit Notes** under Sales. | **Not offered** (`CREDIT_NOTE_VIEW` missing). **(HTTP)** `POST /api/v1/credit-notes/{id}/approve` → `403`. Drafting is bookkeeping; approving reverses a declared tax. |
| 15.5 | Look for **TCS** under Sales. | **Not offered** (`TCS_VIEW` missing). **(HTTP)** `PUT /api/v1/tcs/settings` → `403`. |
| 15.6 **(HTTP)** | Call the six writes above with Asha's token: `PUT` numbering rule, `PUT` credit settings, payout `approve`, payout `pay`, credit note `approve`, `PUT` TCS settings. | `403` every time (re-driven 2026-09-14 and again during the owner's run on 2026-09-15; the two reads, numbering rules and credit settings, answer 200), body `{"success": false, "error": {"code": "authorization_denied", ...}}`. A hidden button is not a control. |

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
