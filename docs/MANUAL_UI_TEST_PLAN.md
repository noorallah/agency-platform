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

| # | Case | Expected |
| --- | --- | --- |
| 2.1 | Log in as `master.ops`, no firm chosen | Only platform screens are reachable. Firm-owned lists say a firm must be chosen, not "no records". |
| 2.2 | Choose WHOLE01, then ELEC01, from the firm switcher | Every open list reloads. No row from the previous firm survives the switch. |
| 2.3 | Log in as `whole01.admin` | The firm switcher offers WHOLE01 only. |
| 2.4 | Leave the app idle past the access-token lifetime, then click anything | It refreshes silently and the action completes. You should not be asked to log in again. |
| 2.5 | Log out, then press Back | No cached screen is reachable. |
| 2.6 | Log in with a wrong password three times | Each refusal takes about as long as a correct one. A wrong address and a wrong password should not feel different. |

## 3. Firm isolation — the core of this application

| # | Case | Expected |
| --- | --- | --- |
| 3.1 | As `master.ops` in FOOD01, note the customer count. Switch to MEDI01 | A different set. **These two share one schema** — if a FOOD01 customer appears here, stop and report it. |
| 3.2 | Create a customer `ISO-TEST` in FOOD01 | It does not appear in MEDI01, WHOLE01 or ELEC01. |
| 3.3 | Open a WHOLE01 sales invoice, copy its number. Switch to ELEC01 and search for it | Not found. Different database entirely. |
| 3.4 | In ELEC01, open Reports → any report | Rows are ELEC01's. Cross-check one figure against the ELEC01 workspace. |
| 3.5 | As `whole01.admin`, try to reach another firm's data by any route the UI offers | There is none. |
| 3.6 **(HTTP)** | Call a firm-owned endpoint with `X-Firm-ID` set to a firm you are not a member of | `403`, not an empty list. An empty list would look like "no data" and hide the hole. |

## 4. Masters — customers

| # | Case | Expected |
| --- | --- | --- |
| 4.1 | Open `WHOLE01C01`, change only the phone number, save | Addresses, contacts, credit limit, payment terms and the 7.5% standing discount are all **unchanged**. This is the defect that shipped twice; check each one. |
| 4.2 | Reopen and confirm the outstanding balance | Unchanged by the edit. |
| 4.3 | On a new customer, use the place picker: choose country, then state, then district, then city | Each rung loads after the one above. Choosing a country must load states immediately, not after a second click. |
| 4.4 | Save, reopen | The place is still there, and the text fields (city, state, country) agree with the chosen ids. |
| 4.5 | Customers → Settings (needs `CUSTOMER_MANAGE_SETTINGS`) | The credit policy dialog opens. As `whole01.sales1` the action is not offered. |
| 4.6 | Set a credit limit of ₹1 on `WHOLE01C03`, then raise and approve a sales order for more | A warning names the exposure. It does **not** block — the demo firms are in warn mode. |
| 4.7 | Customer → Statement | The running balance is in date order and ends at the customer's current balance. |
| 4.8 | Customer → Ageing | The buckets sum to total outstanding, and the reconciliation line explains any gap between the bills and the account. |
| 4.9 | Assign `WHOLE01C03` to the Wholesaler group, save, reopen | The group holds. |
| 4.10 | Try to delete the `RETAILER` group while a customer is in it | Refused, naming the customer. |

## 5. Masters — vendors, products, branches, warehouses

| # | Case | Expected |
| --- | --- | --- |
| 5.1 | Open a vendor, change one field, save | Addresses, contacts, bank accounts, tax details, attachments and notes all survive. |
| 5.2 | Vendors → Categories, and → Types | Both lists load and both can be added to. (These returned nothing at all until the route order was fixed.) |
| 5.3 | Put a category and a type on a vendor, save, reopen | Both held. |
| 5.4 | Products → open `DETER1K` | Its UOM slots, tax profile group and category are populated. |
| 5.5 | Product → custom fields | Fields offered match this firm's business profile. A pharmacy field must not appear in WHOLE01. |
| 5.6 | Branches → rename one, save | Street lines, city, default flag and GST registration all survive. |
| 5.7 | Warehouses → rename one, save | The ten capability flags survive. |
| 5.8 | Branches → Import, with a file whose fifth row duplicates an existing code | **Nothing** is imported. The dialog says so. Correct the file and re-import — all rows go in. |
| 5.9 | Branches → Export, Warehouses → Export | A file downloads. (Both were unreachable until the route order was fixed.) |
| 5.10 | Packaging levels on a product, then scan a carton barcode | The scan resolves to the product and says how many base units it holds. |

## 6. Configuration

| # | Case | Expected |
| --- | --- | --- |
| 6.1 | Settings → Numbering series, as `whole01.admin` | New series, Edit and Retire are offered. As `whole01.sales1`, none are. |
| 6.2 | Edit a series | **Next number is read-only**, with the reason. Only a new series may say where its counter starts. |
| 6.3 | On a new series, switch off "include the financial year" while "restart each financial year" is on | The form says it would repeat a number in April. Saving anyway is refused by the server with the same sentence. |
| 6.4 | Preview next on the sales invoice series | Matches the pattern, e.g. `SI-2026-2027-000010`. |
| 6.5 | Administration → Business profiles → features | Toggling a feature the firm does not implement is refused. The six roadmap features cannot be switched on at all. |
| 6.6 | Administration → Category attribute rules | A rule can be added; a product missing that attribute is then refused, naming it. |
| 6.7 | Tax → rules, simulate | The simulator answers with the components and the matched rule. |
| 6.8 | UOM → conversion rules | A product's own rule outranks the firm-wide one. |

## 7. Buying — order to payment

| # | Case | Expected |
| --- | --- | --- |
| 7.1 | Purchase orders → New, one line, save as draft | Draft. |
| 7.2 | Try Approve straight from draft | Refused: "Submit the order first." |
| 7.3 | Submit, then Approve | Approved. |
| 7.4 | Edit the approved order | The approval is withdrawn and it returns to draft, recorded on the timeline. |
| 7.5 | Receive part of it (Goods receipt → New from the order), complete the receipt | The order reads **PARTIALLY_RECEIVED**. Stock rises. |
| 7.6 | Receive the rest | The order reads **RECEIVED**. |
| 7.7 | Cancel a completed receipt | Stock falls and the journal reverses. Run `verify_sample_data.py` — all five checks still pass. This is the case that put a store 2,287.42 out. |
| 7.8 | Raise a purchase invoice against a receipt and approve it, then try to cancel the receipt | Refused: the invoice already cleared the accrual. A purchase return is the way. |
| 7.9 | Purchase return → mark a line damaged, complete it | Stock falls, the journal reverses, and the line appears in Reports → Purchase returns → Damaged. |
| 7.10 | Reports → Purchase → all six | Register 32 rows, Pending 2, Overdue 2, and by-vendor / by-buyer / by-product all populated. |
| 7.11 | Payments → record a payment against a purchase invoice | The vendor balance falls and a journal entry exists. |

## 8. Stock

| # | Case | Expected |
| --- | --- | --- |
| 8.1 | Inventory → Stock summary, by warehouse and by product | Figures agree with the stock ledger. |
| 8.2 | Inventory → Ledger for `DETER1K` | Every movement has a document behind it. |
| 8.3 | Transfer stock between warehouses | Both sides move; the total is unchanged. |
| 8.4 | Physical count → post a count with a difference | The adjustment posts to the ledger. |
| 8.5 | In MEDI01 or FOOD01, dispatch a batch-tracked product | The batch nearest expiry is taken first. |
| 8.6 | Batches → expiry dashboard | Expiring batches are listed with days remaining. |
| 8.7 | Try to dispatch more than is available | Refused, naming the shortfall. |
| 8.8 **(GAP)** | Serial numbers | No demo firm serialises. The screens work; there is no seeded data behind them. |

## 9. Selling — quotation to cash

Do this whole section in order; each step feeds the next.

| # | Case | Expected |
| --- | --- | --- |
| 9.1 | Quotations → New for `WHOLE01C01`, one line of `DETER1K` qty 12, **leave the discount box empty** | Saves. The line resolves 2% from the `STANDING` price list. |
| 9.2 | Change the quantity to 18 | The rate becomes **6.75%** — the ladder took the highest break at or below 18, not the first one above zero. |
| 9.3 | Same line for `WHOLE01C02` | **9.25%** — that shop's own list replaces the firm-wide ladder rather than amending it. |
| 9.4 | Set the quantity to 30 | **5% or 7.5%** — `BULK5` applies, and a promotion outranks the price list. |
| 9.5 | Type `0` into the discount box | The line takes **nothing**. Zero is a refusal of every arrangement, not a silence. |
| 9.6 | Send the quotation, then Accept, then Convert | A sales order is created, numbered in its own series. Converting twice is refused, naming the order. |
| 9.7 | On the order, add coupon `WELCOME10` | An extra 2.5% compounds onto what is left. `WELCOME10B` gives nothing until presented. |
| 9.8 | Type a nonsense coupon code | The order still saves and simply gives nothing. A typo must not refuse a sale. |
| 9.9 | Approve the order | Stock is reserved. The promotion claim moves from pending to claimed. |
| 9.10 | Put the order on hold, then try to dispatch | Refused, naming the hold. The stock **stays reserved**. |
| 9.11 | Release the hold | The order returns to the status it had, not to "approved". |
| 9.12 | Delivery note → New from the order, dispatch part of it | Order reads **PARTIALLY_DELIVERED**. Stock leaves. Cost of goods sold posts. |
| 9.13 | Check the note's line rate against the order's | **Identical.** The note ships the deal the order struck; it must not re-read the customer's current rate. |
| 9.14 | Dispatch the rest | Order reads **DELIVERED**. |
| 9.15 | Sales invoice → New, bill the delivery note | The billable quantity is what was **charged**, not what left the warehouse. If the note gave a unit free, you cannot bill for it. |
| 9.16 | Approve the invoice | Revenue, receivable and output tax post. The customer balance rises. |
| 9.17 | Print the invoice | Both parties' GSTINs, HSN codes, the CGST/SGST split, the HSN-wise summary, the amount in words, and two labelled copies. |
| 9.18 | Receipts → collect part of it | Balance falls by what was collected. The rest stays outstanding. |
| 9.19 | Collect more than is owed | The excess becomes an unapplied advance, not a negative balance. |
| 9.20 | Receipts → Allocate the advance to another invoice | **No journal is posted** — the money already moved. Only the part that became an advance moves the balance. |
| 9.21 | Reverse the receipt | Balance and advance both go back to exactly where they were. |
| 9.22 | Sales return against the invoice, complete it | Stock returns, the credit note posts, the customer balance falls. |
| 9.23 | Credit note → New naming an invoice **line**, approve | Tax is reversed at the rate that line was charged, not at a profile rate. |
| 9.24 | Try to credit more than the line was worth | Refused, naming the cap. |
| 9.25 | Proforma → raise one from an approved order, issue it | **Nothing posts.** No journal, no receivable. Its number is a `PI-` series, not the invoice series. |
| 9.26 | Edit the order the proforma came from | The proforma is unchanged — its lines are a snapshot. |

## 10. Pricing, promotions and incentives

| # | Case | Expected |
| --- | --- | --- |
| 10.1 | Price lists → open `STANDING` | Three breaks on `DETER1K`: 0 / 15 / 18. |
| 10.2 | Add a break at 25 and re-price a line of 30 | `BULK5` still wins — a promotion outranks a price list. Remove the promotion's window to see the list take effect. |
| 10.3 | Promotions → open `BULK5` | **Two revisions.** Editing an active promotion supersedes it rather than changing it. |
| 10.4 | Reports → Promotions → Performance | `BULK5` shows **one row** with 34 claims, not two rows of 14 and 20. |
| 10.5 | Reports → Promotions → Coupons | `WELCOME10` has claims; `WELCOME10B` has none. Both are listed. |
| 10.6 | Reports → Promotions → Claims | Each claim names its document and customer. |
| 10.7 | Raise an order large enough for `BIGORDER` | `BIGORDER` applies and `CLEARANCE` does **not** — a non-stacking offer ends evaluation. |
| 10.8 | Loyalty → a customer's balance and movements | The balance is the sum of the ledger. |
| 10.9 | Redeem points against an invoice | The bill is **settled**, not discounted — the full GST is still charged. |
| 10.10 | Try to redeem more than the balance | Refused outright, not trimmed. |
| 10.11 | Loyalty → Expiring report | Points shown are what is left of each batch after spending, oldest first. |
| 10.12 | Commission → report over the whole history, and divide commission by the collected amount | The first salesman comes out at a rate that is **neither** of the two that govern them — a blend of 15% of the **margin** on their scoped product and 4% of the *value* of everything else. It read **6.07%** on 2026-09-05; the figure moves whenever the data is reseeded, so check the shape rather than the number. |
| 10.13 | The second salesman | Exactly **2.00%** — the bottom band of their ladder, and a round number precisely because a ladder's floor is. |
| 10.14 | Accrue a payout, approve it, pay it | Three distinct journal references. An approved payout can be paid; the accrual cannot be paid twice. |
| 10.15 | As `whole01.sales1`, try to approve or pay a payout | Refused. Whoever states a debt must not move the cash. |

## 11. Territory, routes and beats

| # | Case | Expected |
| --- | --- | --- |
| 11.1 | Territories → the hierarchy | Region → zone → route, three routes under two zones. |
| 11.2 | Open route `WHOLE01-R-N1` → working days | Monday, Wednesday, Friday. |
| 11.3 | Call lists → pick a Monday | `WHOLE01-BP-R1-MON` is due with its stops. The Friday plan is listed and **not** due, with a reason. |
| 11.4 | Pick the second Tuesday of a month | The weekly, the fortnightly and the monthly plan are all due. |
| 11.5 | Route → customers, drag one shop above another, save | Both stop numbers change. No collision. |
| 11.6 | Open a route, let the shop list load, then save without changing anything | The list is unchanged. (This screen **replaces** the whole list, so it must prove it read it first.) |
| 11.7 | Assign a salesman who does not cover a customer's territory | Refused, naming the reason. |

## 12. Compliance

| # | Case | Expected |
| --- | --- | --- |
| 12.1 | GST returns → GSTR-1 for a month with invoices | B2B, B2CS and CDNR sections populate. No row has a blank place of supply. |
| 12.2 | Cancel an invoice, re-read GSTR-1 | It drops out. The return is derived on every read, never stored. |
| 12.3 | GST returns → GSTR-3B | Aggregated from the documents, and it reconciles with GSTR-1. |
| 12.4 | E-invoicing → registrations | 13 for WHOLE01, every one **SANDBOX** with an `SBX…` reference. |
| 12.5 | Register an invoice for `OB-REV2` | Refused **locally**, naming the missing GST number — not a numeric code from a portal. |
| 12.6 | Raise an e-way bill against a registered invoice | Succeeds. Against an unregistered one, refused. |
| 12.7 | TCS → settings | Disabled by default. |
| 12.8 | Enable TCS, then collect a receipt | Tax is charged on the **receipt**, on the excess over the threshold only, and posts to `TCS_PAYABLE`. |

## 13. Finance, reports and platform

| # | Case | Expected |
| --- | --- | --- |
| 13.1 | Finance → Chart of accounts | Loads and can be added to. |
| 13.2 | Finance → Trial balance | Balances. |
| 13.3 | Finance → P&L and Balance sheet | Both render and agree with the trial balance. |
| 13.4 | Finance → Journal entries, filter by source module | Eleven modules post: delivery note, sales invoice, sales return, credit note, goods receipt, purchase invoice, purchase return, settlements, loyalty, TCS, commission. |
| 13.5 | Finance → Accounting periods → close one, then try to post into it | Refused. |
| 13.6 | Reports workspace → open **every** report in the list | Each renders. A report that errors is a defect; a report that is legitimately empty should say so rather than showing a blank grid. There are 56 as of 2026-09-05; `report_catalog.dart` is the list. |
| 13.7 | Ctrl+K from inside a firm, search anything | Results across modules. **No 503.** |
| 13.8 | Audit logs, with a firm chosen | That firm's trail. Without a firm and with platform authority, the platform trail. |
| 13.9 | Administration → Users, Roles, Permissions | All load. A role's permissions can be changed; a system role cannot. |
| 13.10 | Help → Report a problem, from a screen that has errored | The report carries the request id and joins to the server-side traceback under Diagnostics. |

---

# Part 3 — Cross-cutting

## 14. Concurrency and two machines

Run these with two clients pointed at one server, or two windows.

| # | Case | Expected |
| --- | --- | --- |
| 14.1 | Open the same customer on both, save on A, then save on B | B is refused with a conflict message, and **keeps what was typed**. |
| 14.2 | The same for a sales order, a product and a price list | Same behaviour. |
| 14.3 | Save a record twice with no change in between | Accepted both times. An unchanged save must not move the version. |
| 14.4 | Approve the same sales order on both clients at once | One succeeds; the other is refused by name. |
| 14.5 | Both approve documents claiming the last redemption of an offer | The loser is **refused**, not silently repriced. |
| 14.6 | Two clients accrue a commission payout for one salesman and period | One succeeds; the other is refused by name, not with a 500. |

## 15. Permissions

Use `whole01.sales1` for every refusal case. The point is that the **server**
refuses, not merely that the button is hidden.

| # | Case | Expected |
| --- | --- | --- |
| 15.1 | Numbering series | Read-only. No New / Edit / Retire. |
| 15.2 | Customer credit settings | Not offered. The role the limit constrains must not be able to switch it off. |
| 15.3 | Commission → approve or pay a payout | Not offered, and refused if forced. |
| 15.4 | Credit note → approve | Not offered. Drafting is bookkeeping; approving reverses a declared tax. |
| 15.5 | TCS settings | Not offered. |
| 15.6 **(HTTP)** | Call each of the above endpoints directly with this user's token | `403` every time. A hidden button is not a control. |

---

# Part 4 — Known gaps

Do **not** raise these as defects. They are deliberate, and each is recorded in
`docs/MODULE_STATUS.md` with what is blocking it.

| Area | State |
| --- | --- |
| Emailing a document | Not built. The PDF exists; there is no SMTP client or mail configuration. Deferred by the owner. |
| Licensing | Not built. A permission and a role exist and are unused. Deferred by the owner. |
| Serial numbers | Built, but no demo firm serialises — screens work, no seeded data. |
| Packaging levels | Built, no seeded rows. |
| Cost and profit centres | Present in finance, used by nothing. |
| Shortened sales chains | A firm can be configured to type fewer than four documents; no demo firm is. |
| Credit **blocking** | Built. Every demo firm is in **warn** mode, so blocking is not exercised. |
| `IMEI`, `PRESCRIPTION_REQUIRED`, `RECIPE_MANAGEMENT`, `KITCHEN_MANAGEMENT`, `SERVICE_CONTRACTS`, `PROJECT_MANAGEMENT` | Declared as roadmap features and refused if switched on. |

---

## Appendix — driving the API by hand

For the **(HTTP)** cases. See `.claude/skills/run-app` for the full recipe.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"whole01.sales1@agency.local","password":"DemoAdmin@12345"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

FIRM=<the WHOLE01 id from GET /api/v1/firms>

curl -s -w "\nHTTP %{http_code}\n" -X POST \
  http://localhost:8000/api/v1/document-framework/numbering-rules \
  -H "Authorization: Bearer $TOKEN" -H "X-Firm-ID: $FIRM" \
  -H "Content-Type: application/json" -d '{...}'
```

Every response carries a `requestId`. Quote it when reporting anything — it
joins the screen to the server log.
