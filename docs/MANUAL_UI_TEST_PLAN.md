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

## 16. Who a user is — the four tiers

New on 2026-09-05 (#235–#237). There are four kinds of user and they are not
interchangeable:

| Tier | Who | Reaches |
| --- | --- | --- |
| 1 | Platform operator (`PLATFORM` scope) | Creates firms and their people, provisions storage, sets a firm up until it works. **Refused a firm's books.** |
| 2 | All-firms super user (`ALL_FIRMS` scope) | Everything, in every firm, without needing a membership. |
| 3 | Firm administrator (`FIRM_ADMIN`) | Everything inside their own firm, including its users and their access. |
| 4 | Firm staff | The modules their job needs. |

`platform-admin@agency.local`, `master.ops@agency.local` and
`superadmin@agency.local` are all **tier 2** — the migration left every existing
designation exactly as it was. There is no seeded tier-1 account; 16.1 makes
one, because the tier cannot be tested without one.

| # | Case | Expected |
| --- | --- | --- |
| 16.1 **(SQL)** | `UPDATE platform.platform_admins SET scope = 'PLATFORM' WHERE user_id = (SELECT id FROM platform.users WHERE email = 'superadmin@agency.local');` then sign out and back in | Necessary setup. Put it back to `ALL_FIRMS` when you are done, or that account loses every firm. |
| 16.2 | As that user: Dashboard, Administration → Users, Roles, Firms | All offered. Running the platform is their job. |
| 16.3 | As that user: Sales, Purchases, Finance, Inventory in the sidebar | **Not offered.** Their token carries 33 permission codes, none operational. |
| 16.4 **(HTTP)** | `GET /api/v1/customers` with their token and `X-Firm-ID` | `403`. Not by a rule of its own — they are simply not exempt from the membership check. |
| 16.5 | Sign in as `master.ops@agency.local` (tier 2) and switch between firms | Unchanged from before. Every firm, no membership needed. |
| 16.6 | Put 16.1 back to `ALL_FIRMS` | Housekeeping. Do not skip it. |

## 17. User templates — hiring by naming the job

Eleven platform templates are seeded. A firm may add its own; it may not edit
the platform's. Sign in as `whole01.admin`.

| # | Case | Expected |
| --- | --- | --- |
| 17.1 | Administration → User Templates | 11 rows. Each names its roles — Counter Sales shows `BILLING_EXECUTIVE, CASHIER`. Origin reads **Platform**. |
| 17.2 | Select a platform template → Edit / Retire | Both disabled. It is offered to every firm, so no one firm may change it. |
| 17.3 | New → code `night-counter`, name `Night Counter`, pick one or two roles → Save | Created. Origin reads **This firm**. |
| 17.4 | Edit it, change only the **name**, save | The roles are unchanged. An edit that says nothing about the bundle must not empty it. |
| 17.4a | Administration → Users → **New**, fill in the details, set **Job template** to Counter Sales, save | The user is created **and** holds `CASHIER` and `BILLING_EXECUTIVE`. One step, no second visit to the grid. |
| 17.4b | New again, leave **Job template** blank and pick two roles by hand | Those two roles, as before. The template field is optional. |
| 17.4c | New again, name a job **and** pick a different role | The job wins. The helper text under Roles says so; check it does. |
| 17.4d | Edit an existing user | **No** Job template field — it is create-only. Use Apply job template on the grid instead. |
| 17.5 | Administration → Users → select a user → **Apply job template** | A picker listing each job with the roles beside it, and a line saying the person's roles are **replaced** and editable afterwards. |
| 17.6 | Choose Counter Sales → Apply | Their roles become exactly `BILLING_EXECUTIVE` and `CASHIER`. |
| 17.7 | Edit that user's roles by hand afterwards | Works normally. A template is where you start, not where you stay — nothing on the user records which template they came from. |
| 17.8 | Retire `night-counter`, then re-open the user from 17.6 | The user is untouched. Retiring is a decision about future hires. |
| 17.9 | Sign in as `whole01.sales1` → Administration | No User Templates tab. It needs `ROLE_VIEW`. |
| 17.10 **(HTTP)** | `POST /api/v1/user-templates` with `role_ids` naming the `PLATFORM_ADMIN` role, using `whole01.admin`'s token | `422`, "A template cannot bundle platform or cross-firm roles." That role carries every permission code. |
| 17.11 | Administration → **Roles** as `whole01.admin` | Lists the twelve firm roles and any of this firm's own. **Not** `PLATFORM_ADMIN`, `SUPPORT_ADMIN` or `LICENSE_ADMIN`. This list was platform-admin-only until #237. |

---

## 18. Hiring like an existing person

The other half of section 17, and the more common one: an administrator
usually has a person in mind rather than a written-down job. Sign in as
`whole01.admin`.

| # | Case | Expected |
| --- | --- | --- |
| 18.1 | Administration → Users → pick somebody with roles → **Hire like this person** | A dialog naming them, saying the new user gets the same roles and firms and **none** of their personal details, password or history. |
| 18.2 | Press Create with the form empty | Refused, field by field. Nothing is created. |
| 18.3 | Type a name, an email with no `@`, a password → Create | "That is not an email." |
| 18.4 | Fill it in properly → Create | Created. The message names both people. |
| 18.5 | Open the new user | Same roles as the source. **Blank** mobile, employee code, department, joining date. |
| 18.6 | Sign in as the new user with the password you typed | Forced to change it. A password somebody else chose is not a password. |
| 18.7 | Change the new user's roles, then re-open the source | The source is unchanged. A clone is a starting point, not a link. |
| 18.8 | As `whole01.sales1`, open the users grid | No **Hire like this person**. It needs `ROLE_ASSIGN`, `ROLE_VIEW` and `USER_CREATE` — copying access is granting access. |

## 19. Setting a firm up from the platform side

Sign in as `superadmin@agency.local` (tier 2). This is the flow a platform
operator uses when a new firm is created.

| # | Case | Expected |
| --- | --- | --- |
| 19.1 | Administration → User Templates → New | An **Offered to** picker appears, which a firm administrator does not see. |
| 19.2 | Create a template with **Offered to** set to one firm | Created. Origin shows that firm. |
| 19.3 | Sign in as `whole01.admin` and open User Templates | The template from 19.2 is **not** listed, unless you chose WHOLE01. Before this, a template written for one firm was offered to every firm. |
| 19.4 | As the platform user, create one with **Offered to** left blank | Offered to every firm — which is right for a job every firm has, and is why the field says so. |
| 19.5 **(HTTP)** | As `whole01.admin`, `POST /api/v1/user-templates` with `firm_id` naming a different firm | `422`, "You can only act within your own firm." Refused, not silently redirected. |

---

## 20. A firm administrator creating users

The button that was not there. `FIRM_ADMIN` holds `USER_CREATE`, `USER_UPDATE`,
`ROLE_ASSIGN` and `ROLE_VIEW` — everything running a firm's people needs — and
the New-user gate also demanded `FIRM_VIEW`, which is a platform code the role
can never be given. Sign in as `whole01.admin`.

| # | Case | Expected |
| --- | --- | --- |
| 20.1 | Administration → Users | **New** and **Edit** are offered. Before this they were not, for any firm administrator. |
| 20.2 | New → look at **Firms** before typing anything | **WHOLE01 is already ticked.** The form used to open empty and then silently remove the membership the save had just created, leaving a user in no firm and invisible in the grid. |
| 20.2a | Fill in name, email, password → Save | Created and in WHOLE01, visible in the grid straight away. |
| 20.2b | New again, **clear** the Firms box, save | Created in **no** firm — allowed, and deliberate. They will not appear in the grid; find them with **Add existing user**. |
| 20.2c | As `superadmin`, open New | Firms is **empty**, not prefilled. A platform administrator has no own firm, and quietly using whichever one their switcher shows would be a surprise. |
| 20.3 | Open the form again and look at **Firms** | Lists the firms *you* belong to. It read `/api/v1/firms`, which is platform-only, so it used to come back empty with a failed load. |
| 20.4 | Sign in as `superadmin@agency.local` and open the same form | **Firms** lists every firm. Same field, different source. |
| 20.5 **(HTTP)** | As `whole01.admin`, `PUT /api/v1/users/{id}/firms` naming ELEC01 | `422`, "You can only assign firms you administer." Refused by name, not silently dropped. |
| 20.6 **(HTTP)** | As `superadmin`, put a user in **both** WHOLE01 and ELEC01. Then as `whole01.admin`, save that user with WHOLE01 only. Re-read as `superadmin` | **Both** memberships survive. The endpoint replaces for a platform caller and merges for a scoped one — otherwise a firm administrator correcting their own firm would remove the person from every other firm on the platform. |
| 20.7 | As `whole01.admin`, set a user's primary firm to something else | The primary does not move. It is one flag across every firm somebody belongs to, so a caller who can see only some of them must not set it. |
| 20.8 | Follow `docs/USER_ADMINISTRATION_GUIDE.md` §3 end to end | Create a user, apply **Counter Sales**, sign in as them: Sales and Inventory offered, Finance and Administration not. |

---

## 20a. Roles: global and firm-level

Two tiers. A **platform** administrator writes the global set on the user
form (**Roles in every firm**); either administrator writes one firm's set
under **Roles by firm** on the Users grid. They are additive, and a firm
administrator cannot remove a global grant.

The defect behind the screen: the single Roles box wrote through a path that
replaced every row regardless of firm, so a platform administrator pressing
Save without changing anything collapsed each firm's separate roles into one
global grant.

Use a user who belongs to **two** firms — create one and add both memberships
first.

| # | Case | Expect |
| --- | --- | --- |
| 20a.1 | As `master.ops`, Administration → Users → edit that user | The roles field is labelled **Roles in every firm**, and says it applies in every firm including ones added later. |
| 20a.2 | Set it to `VIEWER` and save | Saved as the global set. |
| 20a.3 | Select the row → **Roles by firm** | A section per firm the person belongs to — and **not** firms they do not belong to. `VIEWER` appears once at the top under **Applies in every firm**, greyed and unclickable. |
| 20a.4 | Give WHOLE01 `SALES_MANAGER`, press its **Save** | Saved for WHOLE01. Each firm has its own Save, enabled only once that firm changed. |
| 20a.5 | Give ELEC01 `CASHIER`, save | Saved for ELEC01. WHOLE01 still shows `SALES_MANAGER` — one Save affects one firm. |
| 20a.6 | Re-open the user form and press **Save** without changing anything | **Both firms keep their own roles.** This is the regression case: before the fix, WHOLE01 and ELEC01 both ended up holding every role, globally. |
| 20a.6b | Sign in as `whole01.admin` → Users → **edit** that person | Under Security, **Also applies here** shows the global roles as read-only text, or `None`. A firm administrator could not see them at all before: a global grant applies in their firm, so the form reported less than the person could do. |
| 20a.6c | As `master.ops`, edit the same person | **Also applies here** is absent — the Roles field above already *is* their global set. In its place, **Roles in specific firms** shows what each firm holds, read-only: `WHOLE01: SALES_MANAGER · ELEC01: CASHIER`, or `None`. Each caller sees the tier they cannot write. |
| 20a.6d | Give someone roles in one firm and none in another, then re-open | Only the firm holding roles is listed. A firm with none is left out rather than shown empty, so the line stays readable as firms are added. |
| 20a.7 | Sign in as `whole01.admin` → Users → that person → **Roles by firm** | One section, WHOLE01. `VIEWER` is shown greyed under **Applies in every firm** and cannot be cleared. |
| 20a.8 | Remove `SALES_MANAGER` in WHOLE01 and save | Removed in WHOLE01. `VIEWER` survives — a firm administrator may not undo a platform grant. |
| 20a.8b | As `master.ops`, Users → **New** | Under Security: **Job template**, **Roles in every firm**, and nothing that names a firm. **Apply roles to** is gone — the form writes the global tier only, and Roles by firm is the only place a firm-tier role is written. |
| 20a.8c | Create a user: two firms, a role | Granted globally. Check with **Roles by firm**: both firm sections are empty; the role sits under **Applies in every firm**. |
| 20a.8d | Give one firm a role from **Roles by firm**, then re-open the form and Save it unchanged | The firm keeps its role and the global set is unchanged — one writer per tier, so neither save can touch the other's rows. |
| 20a.8e | Create another naming a **job template** | The job's roles land globally, the same tier the Roles field would have written. |
| 20a.8f | As `master.ops` **with a firm selected**, edit a user | **One** roles field under Security, **Roles in every firm**, plus the read-only **Roles in specific firms** listing every firm the person holds roles in — the selected one included. No second column. The helper says a role in one firm only is set under Roles by firm. |
| 20a.8g | Add a role there and save, then check **Roles by firm** | It is under **Applies in every firm**; no firm section changed. The switcher has no say in where a role lands. |
| 20a.8h | Sign in as `whole01.admin` → Users → edit somebody in WHOLE01 | The roles field is labelled **Roles in this firm** and **Also applies here** shows the global grants read-only. Nothing names a firm. |
| 20a.8i | Press **Roles by firm** in the dialog footer (edit **or** view) | The per-firm editor opens without closing the form. Offered to anyone holding `ROLE_ASSIGN` and `ROLE_VIEW`. |
| 20a.8j | As `whole01.admin`, select a person who is in WHOLE01 **and** ELEC01 → **Roles by firm** | **One section, WHOLE01**, with chips that respond and a Save that lands. This was the broken case: the dialog read the platform-only firm list, answered 403, and showed a firm administrator an error and no firm at all. ELEC01 is not listed — its Save would be refused by name. |
| 20a.8k | As `whole01.admin`, open Roles by firm on somebody who is in ELEC01 only | "This person belongs to no firm you administer." — not "belongs to no firm yet", which would be false. |
| 20a.9 **(HTTP)** | As `whole01.admin`, `PUT /api/v1/users/{id}/firms/{ELEC01 id}/roles` | Refused: "You can only set roles in firms you administer." |
| 20a.9b **(HTTP)** | As `whole01.admin`, `GET /api/v1/users/{id}/firms/{ELEC01 id}/roles` | Refused the same way: "You can only read roles in firms you administer." The read used to answer for any firm. `.../firms/{WHOLE01 id}/roles` still answers 200. |
| 20a.10 **(HTTP)** | As `master.ops`, `PUT /api/v1/users/{id}/firms/{firm}/roles` for a firm the user is **not** a member of | Refused: "Add the user to this firm before giving them a role in it." A role there would sit in the table and stay out of the token. |

---

## 21. The five modules a firm administrator could not open

`_operational_permissions` is the list `FIRM_ADMIN` and `FIRM_MANAGER` are
built from, and five groups had never been added to it. Sign in as
`whole01.admin`. **If you were already signed in when this shipped, sign out
and back in** — a token carries the claims it was minted with.

| # | Case | Expected |
| --- | --- | --- |
| 21.1 | Sales → Credit Notes | Offered, and opens. Draft, approve and the approve gate are all reachable. |
| 21.2 | Sales → Proforma | Offered, and opens. |
| 21.3 | Sales → E-Invoice | Offered, and opens. Check the mode badge reads SANDBOX. |
| 21.4 | Masters → Loyalty | Offered, and opens. Settings included — `LOYALTY_MANAGE_SETTINGS` is granted. |
| 21.5 | Sales → TCS | Offered, and opens, settings included. |
| 21.6 | As `whole01.sales1`, try all five | Still refused, all five. The grant widened one role, not everybody. |
| 21.7 | Masters → Firms | **Still not offered**, deliberately. Deciding which firms exist is not a firm's own business. |
| 21.8 **(HTTP)** | `GET /api/v1/credit-notes`, `/proforma-invoices`, `/einvoice/registrations`, `/loyalty/settings`, `/tcs/settings` with a `whole01.admin` token | `200` on all five. They answered `403` before. |

---

## 22. A cashier can see the till

`CASHIER` held exactly the right codes and was offered **no module at all** —
Receipts and Payments are Finance tabs, Finance was gated on `ACCOUNT_VIEW`,
and a tab naming no codes inherits its module's.

Make a cashier first: **Users → New**, set **Job template** to nothing and pick
the `CASHIER` role alone. (The seeded `counter-sales` template pairs it with
`BILLING_EXECUTIVE`, which hides the whole problem.)

| # | Case | Expected |
| --- | --- | --- |
| 22.1 | Sign in as that user | **Finance** is in the sidebar. Before this the sidebar was empty. |
| 22.2 | Open Finance | Exactly two tabs: **Receipts** and **Payments**. |
| 22.3 | Look for Chart of Accounts, Journal Entries, Ledgers, Trial Balance, P&L, Balance Sheet, Refunds | **None of them.** Widening the module without gating its tabs would have handed a cashier the ledger. |
| 22.4 | Record a receipt | Works. `RECEIPT_CREATE`. |
| 22.5 | Sign in as `whole01.accounts` (or any `ACCOUNTANT`) → Finance | **All nine** tabs, exactly as before. Nobody lost one. |
| 22.6 | As `whole01.admin` → Finance | All nine. |

---

## 23. The audit trail

Two things here, and the first is a regression that shipped on 2026-09-05 and
was found on 2026-09-06: moving the platform designation into its own claim
left two checks looking for it in the old place, so **no platform administrator
could read any audit trail at all**.

| # | Case | Expected |
| --- | --- | --- |
| 23.1 | Sign in as `superadmin@agency.local`, no firm selected → Settings → Audit Logs | The **platform** trail: user, role and firm administration. Answered 403 between 2026-09-05 and 2026-09-06. |
| 23.2 | Same user, select WHOLE01 → Settings → Audit Logs | **That firm's** trail, not the platform's. Also 403 in that window. |
| 23.3 | As `whole01.admin` → Settings | The module opens with **Audit Logs** in it. It used to open empty — offered on `SETTINGS_VIEW`, with both tabs demanding codes the role did not hold. |
| 23.4 | Read it | WHOLE01's history and nothing else. |
| 23.4a | Promote somebody (Users → Apply job template), then re-open Settings → Audit Logs **as `whole01.admin`** | The promotion is listed, naming the template. It is written to the *platform* store — user administration is a platform path — and the firm's trail now merges the platform rows carrying this firm's id. |
| 23.4b | Check the order around it | Newest first across both stores, not the firm's rows followed by the platform's. |
| 23.4c | Filter by action `user_template.applied` | The filter reaches both stores. Filtering one and not the other would answer a half-truth. |
| 23.5 | Look for **Diagnostics** | **Not there.** `DIAGNOSTICS_VIEW` is deliberately withheld — error reports are telemetry for whoever maintains the product, not something a firm owns. |
| 23.6 **(HTTP)** | `GET /api/v1/audit-logs` with a `whole01.admin` token and **no** `X-Firm-ID` | `403`. Reading the platform trail needs platform authority. |
| 23.7 | As `whole01.sales1` → Settings | Not offered at all. |

---

## 24. Hiring somebody who already has an account

`list_users` is scoped to the caller's own members, so a firm administrator
could not find — or even learn the existence of — a person who already works
elsewhere. Sign in as `whole01.admin`.

| # | Case | Expected |
| --- | --- | --- |
| 24.1 | Administration → Users → **Add existing user** | A search box. It is offered with no row selected — the person is not in the grid, which is the point. |
| 24.2 | Type `el` | Nothing searched: "at least 3 characters". |
| 24.3 | Type `elec` | ELEC01's people, found by **email**. |
| 24.4 | Type `Electro` | The same person found by **name**. |
| 24.5 | Look at a result | Name, email, and nothing else. **No firm is named** — you must not learn which firms they work in. |
| 24.6 | Type part of one of your own people's names | Listed, marked **Already in this firm**, and Add is disabled. |
| 24.7 | Type something matching nobody | "They may not have an account yet — use New." |
| 24.8 | Pick an ELEC01 person, set job **Counter Sales**, Add | Added. They appear in WHOLE01's user list. |
| 24.9 | Open their row | **Edit is disabled**, and it says they also work in another firm and their profile is managed by a platform administrator. |
| 24.10 | Apply job template / set roles on them | Both work. Those are yours. |
| 24.11 **(HTTP)** | `GET /api/v1/users/{id}/firms` as `whole01.admin` | **Only WHOLE01.** It returned every membership until 2026-09-06. |
| 24.12 **(HTTP)** | Same as `superadmin` | Both firms — a platform caller still sees them all. |
| 24.13 **(SQL)** | Check their ELEC01 roles | Unchanged. Adding them to WHOLE01 touches nothing in ELEC01. |
| 24.14 | As `whole01.sales1`, look for Add existing user | Not offered. It needs `USER_CREATE`. |
| 24.15 **(HTTP)** | `GET /api/v1/users/lookup?q=elec` with a `whole01.sales1` token | `403`. `USER_VIEW` deliberately does not reach it. |
| 24.16 **(HTTP)** | `GET /api/v1/users/lookup?q=` as `whole01.admin` | `422`: "Type at least 3 characters". An empty term is the shortest of all, and a firm caller gets a lookup, not the directory. |
| 24.17 | Sign in as `master.ops`, select **WHOLE01**, Users → **Add existing user** | The dialog **opens already listing** everyone with an account who is not in WHOLE01, with no typing. The helper reads "Leave blank to list everyone not yet in this firm." WHOLE01's own people are **not** listed — they are in the grid beside the button — and neither is any platform administrator. |
| 24.18 | Type `e` | Filtered on one character; the three-character rule is a firm caller's. Clear the box and the full list returns. |
| 24.19 | Pick somebody, Add | Added to WHOLE01, and gone from the dialog's list next time it opens. |
| 24.20 **(HTTP)** | `GET /api/v1/users/lookup?q=&page=1&page_size=2` as `master.ops` with `X-Firm-ID: WHOLE01` | Two rows and a `pagination` block whose `total_records` is everybody not in WHOLE01. The route pages for a platform caller and caps at ten for a firm one, whatever `page` says. |
| 24.21 | As `whole01.admin`, open Administration | Users, Roles, Permissions, User Templates — and **no User-Firm Assignments**. That tab is a platform administrator's; Users → Edit → Firms and Add existing user are the firm administrator's ways to the same thing. |
| 24.22 | As `master.ops`, with or without a firm selected, open Administration | **User-Firm Assignments** is there, with the Firm filter. |

> **Tidy up:** 24.8 leaves a real ELEC01 person in WHOLE01. Remove the
> membership and the WHOLE01 roles afterwards, or reseed.

---

## 25. A firm's own roles and its own templates

The point of this one: **you are not limited to what the platform shipped.**
A role is a bundle of permissions, a template is a bundle of roles, and a firm
administrator may write both. Sign in as `whole01.admin`.

| # | Case | Expected |
| --- | --- | --- |
| 25.1 | Administration → **Roles** | The twelve firm roles. **Not** `PLATFORM_ADMIN`, `SUPPORT_ADMIN` or `LICENSE_ADMIN`. |
| 25.2 | New → code `night-desk`, name `Night Desk` → Save | Created, and it belongs to WHOLE01. |
| 25.3 | Open it → **Permissions** | **167** to choose from. Tick `SALES_VIEW`, `RECEIPT_CREATE`, `CUSTOMER_VIEW`. |
| 25.4 | Look for `FIRM_CREATE`, `PLATFORM_SETTINGS`, `VOID_INVOICE`, `AUDIT_LOG_VIEW` | **Not in the list at all.** The 22 platform codes are not offered, so there is nothing to get wrong. |
| 25.5 | New role with code `platform_admin` | Refused — the designation and the twelve seeded codes are reserved, case-insensitively. |
| 25.6 | User Templates → New → name it, pick **Night Desk** as its role | Created, Origin **This firm**. A template may bundle any role you may assign. |
| 25.7 | Users → New → set **Job template** to it → Save | The new user holds `night-desk` and nothing else. |
| 25.8 | Sign in as that user | They can do exactly what you ticked in 25.3, and nothing more. |
| 25.9 | Edit the role, remove `RECEIPT_CREATE`, and have them sign out and in | Gone for them too. A role is not versioned — editing it changes everybody holding it. |
| 25.10 | Delete `night-desk` while somebody holds it | **It is deleted.** No refusal, no warning. |
| 25.10a | Have that person sign in again | They no longer have the role's permissions, and nothing on screen says why. Know who is on a role before deleting it. |

> **Tidy up:** 25.2–25.7 leave a role, a template and a user in WHOLE01.
> Remove them or reseed.

---

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

## 26. Platform mode, and the switcher that was empty

Sign in as **`platform-admin@agency.local`**. This account is `ALL_FIRMS` and
holds **no** firm memberships, which is what made the defect visible: its token
carries all 189 permission codes, so the sidebar offered Sales, Purchases and
Inventory, while `/me/firms` answered an empty list so no firm could be
selected and every one of those screens refused its first request.

| # | Step | Expect |
| --- | --- | --- |
| 26.1 | Sign in | The header firm control reads **Platform**, and so does the status bar. |
| 26.2 | Look at the sidebar | Dashboard, Administration, Settings (and Licensing if seeded). **No** Sales, Purchases, Inventory, Masters, Finance or Reports. |
| 26.3 | Open Administration | **Firms**, Users, Roles, Permissions, User Templates, User-Firm Assignments. **No** Tax, UOM, Business Profiles or Numbering Series — those live in a firm's own store. |
| 26.4 | Open the firm control | A **Platform** entry at the top with a tick beside it, then all four firms — even though this account is a member of none. |
| 26.5 | Pick `WHOLE01` | Notification names the firm; the sidebar grows Sales, Purchases, Inventory, Masters, Finance, Reports; Administration gains its configuration tabs. |
| 26.6 | Open Sales → Sales Orders | Real rows. Before this change the module was offered and this screen failed. |
| 26.7 | Open the firm control and pick **Platform** | "Working on the platform. No firm is selected." The firm-owned modules go away again. |
| 26.8 | Sign out and back in | Lands on **Platform**, not on `WHOLE01`. Deliberate: a reach over every firm's books must not restore itself silently. |
| 26.9 | Sign in as `superadmin@agency.local` | Also `ALL_FIRMS`, but a member of all four. Still starts on **Platform**; the switcher looks the same as before. |
| 26.10 | Sign in as `whole01.admin@agency.local` | **No** Platform entry anywhere, one firm, lands in it as always. Nothing about a firm user's experience changed. |

**(HTTP)** `GET /api/v1/me/firms` as `platform-admin` returns four firms, each
with `is_primary: false` — no membership row, so nobody's primary. The same
call as `whole01.admin` still returns one.

## 27. Creating a firm and setting it up

**Sign in as `master.ops@agency.local`.** Not `platform-admin@agency.local`,
which this section used to name: that account is created at startup from
`AGENCY_BOOTSTRAP_ADMIN_PASSWORD` and its password is changed on first use, so
on a database anybody has signed into it no longer takes the value in
`config/.env`. Both hold the same designation and `ALL_FIRMS` scope, so nothing
about the cases changes -- only which account can reach them. On a *fresh*
database the bootstrap account is the only one that exists, and `master.ops`
comes from the demo seeder.

Only a platform administrator can do any of 27.1--27.20. `require_platform_admin()`
guards every `/api/v1/firms` route and never reads a permission, so `FIRM_CREATE`
gates the desktop's **New** button and nothing else.

### 27a. Creating the record

| # | Case | Expect |
| --- | --- | --- |
| 27.1 | Administration → **Firms**, on **Platform** | The list of all firms. This is the one Administration tab that needs no firm selected. |
| 27.2 | Masters → look for Firms | Not there. It moved on 2026-09-06; a firm's own master data needs a firm, so creating a firm was reachable only from inside another one. |
| 27.3 | **New** → save with only a name | Refused. `name`, `code`, `country` (2 letters), `currency_code` (3 letters) and `financial_year_start` are the five required fields; everything else is optional. |
| 27.4 | Enter code `sntest02` in lower case | Stored as `SNTEST02`. Code, country and currency are upper-cased on the way in. |
| 27.5 **(HTTP)** | `POST /api/v1/firms` with code `WHOLE01` | **409**, "Firm code, GST number, or PAN number already exists." The three are unique among *live* firms only, so a soft-deleted firm releases its code. |
| 27.6 **(HTTP)** | Same with code `BAD CODE` | **422**. The pattern is `^[A-Z0-9_-]+$` -- no spaces, no dots. |
| 27.7 **(HTTP)** | Same with `country: "IND"` | **422**. Two letters, ISO-style. |
| 27.8 | Create with deployment mode `SHARED` | Saves. The follow-up message names the next step. |
| 27.9 **(HTTP)** | Create with mode `DATABASE` and `connection_profile: "NOPE"` | **422**, "Connection profile 'NOPE' is not configured. Configured profiles: REMOTE_A." Refused at creation rather than at first use -- otherwise the firm provisions nothing and fails far from the request that caused it. |

### 27b. What creation does and does not do

| # | Case | Expect |
| --- | --- | --- |
| 27.10 | Select the new `SHARED` row | **Open this firm** enabled -- a shared firm is ready at once. **Provision storage** hidden; there is nothing to provision. |
| 27.11 | Create a second firm with mode `SCHEMA` | **Open this firm** **disabled** -- its schema has no tables, so switching in would answer errors on every screen. **Provision storage** enabled. |
| 27.12 | Press **Provision storage**, refresh, select it again | **Open this firm** now enabled. The response carries `provisioned_at`. |
| 27.13 | Press **Provision storage** again | Succeeds, reporting it was already provisioned. Every step is create-if-missing, so this is also the repair action after a target server was unreachable. |
| 27.14 **(HTTP)** | `PUT /api/v1/firms/{id}` changing `deployment_mode` | **422**, "Firm storage routing cannot be changed after creation (currently SCHEMA/…). Migrate the firm's data first." Nothing moves a firm's rows between stores, so the routing is fixed at creation. Verified 2026-09-06. |

### 27c. Reaching the new firm

| # | Case | Expect |
| --- | --- | --- |
| 27.15 | Press **Open this firm** | "Working in …". The header shows it and the sidebar grows the whole application. |
| 27.16 | Open the firm switcher | The new firm is listed. **This is the half that was broken**: the switcher is read once at sign-in, so without the refresh a firm created minutes earlier was not in it and `switchFirm` refused it as "not assigned to this user". |
| 27.17 | Go back to **Platform** and look at Administration | There is **no Configuration heading**. Every one of its eighteen descendants lives in a firm's store, so with no firm it had nothing under it -- and until 2026-09-06 it was offered anyway and opened nothing. |

### 27d. Setting the business profile

**Not** *Masters → Firm Settings*, which this section said until 2026-09-06 and
which does not exist. It is **Administration → Configuration → Business
Profiles → Profile Assignment**, and it needs a firm selected.

| # | Case | Expect |
| --- | --- | --- |
| 27.18 | With any firm open: Administration → Configuration → Business Profiles → **Profile Assignment** | A grid of **every** firm, not just the one you are in. The screen names the firm in the URL rather than reading `X-Firm-ID`. |
| 27.19 | Select the new firm, open it, choose a profile, save | Saved against that firm. The **Business profile** dropdown must be populated -- if it is empty or the dialog says "The database is temporarily unavailable", you are in platform mode with no firm selected, and the catalogue it reads lives in each firm's store. |
| 27.20 | Re-open the row | The profile you chose is shown. Until it is set the firm trades as GENERIC, with the features and modules of no particular industry. |
| 27.21 | Sign in as `whole01.admin@agency.local` → Administration | **No** Firms tab and **no** Business Profiles group. `FIRM_VIEW` and `PLATFORM_VIEW` are platform codes no firm role can hold. |
| 27.22 **(HTTP)** | As `whole01.admin`, `GET` and `POST /api/v1/firms` | **403** for both. Measured 2026-09-06. No permission code can grant this. |

### 27e. The firm is not finished — check before reporting a bug

A provisioned firm with a profile still cannot trade. It needs a chart of
accounts, a financial year, open periods, journal and voucher types, and a
mapped control account for each of the 24 posting purposes -- and **no screen
or endpoint reaches the mapping**. See `docs/BACKLOG.md` §15.

| # | Case | Expect |
| --- | --- | --- |
| 27.23 | From `backend`, run `.\.venv\Scripts\python.exe scripts\check_firm_readiness.py SNTEST02` | Reports the mode, whether storage is provisioned, the profile, the counts of accounts, years and periods, how many control purposes are unmapped, and a verdict. For a new firm: **`CANNOT post -- books not open`**. |
| 27.24 | In the new firm, create a customer and a product | Both save. Masters do not need the books. |
| 27.25 | Raise a sales invoice in the new firm and try to **approve** it | **Refused.** `DocumentPostingService` refuses rather than guesses. This is the design working, not a fault in the new firm -- do not report it as one. |
| 27.26 | Run the same readiness check against `WHOLE01` | **`can post documents`** -- 24 accounts, 3 years, 36 periods, all 24 control purposes mapped. The contrast is the point: it shows what "finished" looks like. |

### 27f. Custom fields and mandatory fields

How a profile reaches a product. `docs/BUSINESS_PROFILE_FRAMEWORK.md`,
"How a firm resolves its attributes", is the reference. Stay signed in as
`master.ops` **with a firm selected** -- both screens live in that firm's
store, so platform mode does not offer them.

A definition applies when it targets the entity type **and** is either
unscoped or scoped to the firm's profile. **NULL means every profile, not
none** -- that is the whole grammar of the table, and reading it backwards is
what put an IMEI on a pharmacy's products in `20260801_0011`.

| # | Case | Expect |
| --- | --- | --- |
| 27.27 | Administration → Configuration → Business Profiles → **Dynamic Attributes** | The definitions in *this firm's* store. Each row shows its entity type and which profile it is narrowed to. |
| 27.28 | New → entity type `PRODUCT`, leave **business profile** blank | Applies to every profile. This is what a field every firm needs looks like. |
| 27.29 | New → entity type `PRODUCT`, business profile = **something other than this firm's** | Saved, and **not** offered on this firm's products. Scoping is what stops one industry's field appearing everywhere. |
| 27.30 | Masters → Products → New | The field from 27.28 appears; the one from 27.29 does not. |
| 27.31 | Set 27.28's definition **mandatory**, then create a product without it | Refused. The flag on the definition applies to **every** category it reaches -- blunt, and the one with a history. |
| 27.32 | Clear that flag. Administration → Configuration → Business Profiles → **Mandatory Attributes** → New, naming one category | Required for that category only. Products in other categories still save without it. |
| 27.33 | Add a mandatory rule naming a definition scoped to **another** profile | Accepted and **inert** -- `mandatory_ids` intersects the rules against what applies, so a rule this firm cannot see enforces nothing. Not an error. |
| 27.34 | Create a product carrying a value, then change the firm's business profile in Profile Assignment | The field **stops appearing** and its value is still in `product_attribute_values`. Nothing warns you; this is `docs/BACKLOG.md` §16. |
| 27.35 | Change the profile back | The field and its value reappear. Nothing was lost -- it stopped being *read*. |
| 27.36 | Change a definition's **data type** after a product carries a value | Accepted with no warning, and the value stops being read -- it sits in the old typed column. Record this as expected-but-wrong; it is §16's first lifecycle guard. |

**If the firm is `SHARED`**, one more case, and it is the reason §16 exists:

| # | Case | Expect |
| --- | --- | --- |
| 27.37 | Add a definition in your new `SHARED` firm, then open Dynamic Attributes as `medi01.admin@agency.local` | **It is there.** `attribute_definitions` carries no `firm_id`, so every firm in `firm_shared` edits one set. A firm in its own schema or database does not have this. |

Delete the test firms afterwards, or leave them; a firm with no data costs
nothing. A `SCHEMA` firm leaves its schema behind either way.

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
