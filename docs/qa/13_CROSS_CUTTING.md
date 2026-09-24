# Cross-cutting: permissions, concurrency and grants

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-09-25 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Permissions — the server refuses, not only the button

`SALES_EXECUTIVE` holds `CUSTOMER_VIEW`, `TERRITORY_VIEW`, `SALES_VIEW` and the
three `SALES_*_CREATE` codes, nothing else. A hidden button is not a control:
each case below checks the screen **and** the route behind it.

### TC-PERM-001 — What a salesperson is not offered

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps:** sign in as the prepared **Seller**. Look for Administration; expand **Sales** and look for Commission, Credit Notes and TCS.
- **Expect:** **no Administration** at all. Under Sales, the territory screens (on `TERRITORY_VIEW`) and none of **Commission**, **Credit Notes**, **TCS** — nor Price Lists, Promotions, Targets, Proforma, E-Invoice or GST Returns, each hidden on its own view code. That is expected, not a fault.
### TC-PERM-002 — The credit policy opens read-only

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps:** as the prepared **Seller**, Masters → Customers → toolbar **Settings**.
- **Expect:** the dialog **opens read-only** — the policy's fields shown but disabled, Save greyed, only Close works — with "Changing the policy needs the manage customer settings permission."
### TC-PERM-003 — Six writes, six refusals; two reads allowed

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps (HTTP)** — sign in as the prepared seller (`POST /api/v1/auth/login`) and send, with `X-Firm-ID` of QA01:
  1. `GET /api/v1/document-framework/numbering-rules`, then `PUT /api/v1/document-framework/numbering-rules/{any listed id}` `{"name": "x"}`.
  2. `GET /api/v1/customers/credit-settings`, then `PUT` it `{"enforcement": "OFF"}`.
  3. `POST /api/v1/commission/payouts/{any id}/approve` and `/pay`.
  4. `POST /api/v1/credit-notes/{any id}/approve`.
  5. `PUT /api/v1/tcs/settings` `{"is_enabled": true}`.
- **Expect:** both **reads answer 200** — any member may read how documents are numbered and the credit rule that warns them. **All six writes answer 403**, body `{"success": false, "error": {"code": "authorization_denied", …}}`. The id need not exist: the permission is checked before the record is looked up.
---

## Concurrency — two people, one record

Run these with **two clients** on one server (or two windows of one client),
**A** and **B**, both signed in as the same preparation's firm admin. An editor that
saves from **inside** its dialog — customer, sales order, sales invoice,
product, price list, promotion, coupon, customer group, target, payout
adjustment — says on a lost race, keeping the dialog open with the typing in
it: *"Somebody else saved this <thing> while you were editing it. Your changes
are still here and have not been sent. Copy anything you need, then close and
reopen to see theirs."* An editor that closes first — branch, warehouse,
quotation, batch, lot, serial number, beat plan, place, territory, tax
component — says in a red toast: *"Somebody else saved this <thing> while you
were editing it. Your changes were not saved. Open it again to see theirs and
redo yours."*

### TC-CONC-001 — Two people editing one customer

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Steps:** on **A** and **B**: Masters → Customers → double-click `QA-CM`. On A change the phone → **Save**. On B change the phone to something else → **Save**.
- **Expect:** A saves ("Customer updated."). B is refused **inside the editor** with the sentence naming `customer`; the dialog stays open with B's typed phone still in the box. Cancel B; reopen: A's phone.
### TC-CONC-002 — The same race on an order, a product and a price list

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** create a draft Sales Order for `QA-C01` first (any line). Then, on A and B: open that draft → **Edit**, change **Remarks** on both, Save A then B. Repeat on Masters → Products → `QA-DET` (Description) and Sales → Price Lists → `STANDING` (the **Name** — the dialog has no Description).
- **Expect:** B is refused each time with the sentence naming `sales order`, `product`, `price list`; typing kept, dialog open.
### TC-CONC-003 — Saving unchanged does not move the version

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Steps:** on A alone, double-click `QA-CM`, change nothing → Save; do it again. **(HTTP)** `GET /api/v1/customers/{id}` before and after; compare the `ETag`.
- **Expect:** accepted both times; the `ETag` and the body's `version` are **the same before and after** — so a client re-sending the same `If-Match` is still accepted. *(Driven: `"2"` before and after an unchanged PUT.)*
### TC-CONC-004 — Two approvals of one order

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** create a draft order for `QA-C01`. On A and B select it in the grid. **Approve** on A; then **Approve** on B, whose grid still says DRAFT.
- **Expect:** A: the row reads APPROVED. B: a red toast — "Only draft sales orders can be approved." (A finished first) or the conflict sentence (both in flight) — never a silent no-op, never a 500. Refresh B: APPROVED once.
### TC-CONC-005 — The last use of a coupon goes to one order

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps**
  1. Sales → Promotions → **Coupons** → `WELCOME10B` → Edit → **Total claims allowed** `1` → Save.
  2. Raise two draft orders for `QA-C01` with **Coupon** `WELCOME10B`, one on each client. Approve both.
- **Expect:** the first approves; the second is refused **by name**: "Coupon WELCOME10B has been used as often as it allows. Re-save the document to price it without." — not silently repriced. A claim counts only at approval, under a lock on the promotion. (`test_the_refusal_is_for_the_race_two_orders_priced_before_either_approved` covers the true race.)
### TC-CONC-006 — Two accruals of one payout period

- **Preconditions:** As *territory-firm*, plus commission rules, targets and three collected sales, as in the preparation table.
- **Steps:** on A and B: Sales → Commission → **Payouts** → **Accrue period**, this month on both; **Accrue** on A, then on B.
- **Expect:** A: "2 payout(s) accrued." B: "A commission payout already covers part of that period for this salesman (…)." — a **409** by name, never a 500. The database holds the rule (`UQ_commission_payouts_period_active`); the service supplies the sentence.
---

## The five modules a firm administrator could not open

`FIRM_ADMIN` is built from `_operational_permissions`, a hand-kept list, and
five permission groups had never been added to it: `credit_note`, `proforma`,
`einvoice`, `loyalty` and `tcs`. Each shipped with a module, a screen and a
seeded gate that the role running the firm could not open. Granted in
`20260906_0130`.

**A token carries the claims it was minted with** — a session from before a
grant changes shows the old screens. Fixture accounts are always new, so this
only matters for accounts you already had open.

### TC-GRANT-001 — Credit notes: raise one against an approved invoice

- **Preconditions:** A firm administrator of QA01, and one sale taken to an approved invoice: order, dispatched delivery note, approved invoice. (a sale of yours in QA01: one invoice for 5 **APPROVED**, one **CANCELLED**.)
- **Steps**
  1. Sign in as the prepared **Firm admin** → Sales → **Credit Notes** → **Raise credit note**.
  2. Open the **Invoice** picker and look for the prepared two invoice numbers and its delivery note number.
  3. Pick the approved invoice; open **Line**.
  4. Enter an amount below what the line was charged (it was charged 590.00: 5 × 100 plus 18% GST) → **Raise**.
- **Expect**
  - Step 1: the dialog is titled **Raise a credit note**, its button reads **Raise** — this screen is hand-built, so nothing is called New or Save.
  - Step 2: the **approved** invoice is offered; the **cancelled** one is not, and no `DN-…` number is. Approved sales invoices with lines, and nothing else.
  - Step 3: the line names its product — **Fixture Product qa** — not `Line 1`.
  - Step 4: a draft is listed. **Approve** and **Cancel** are **row actions** on the right, not toolbar buttons; Approve being there *is* the approve gate this case checks. Leave it a draft — approving posts the credit and reverses declared output tax.
### TC-GRANT-002 — Proforma opens

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, Sales → **Proforma**.
- **Expect:** offered, and a real screen — a grid or a proper empty state, never a "coming soon" placeholder. A proforma states what an approved order **will** be charged and **posts nothing**; its number comes from its own `PF` series, not the tax invoice's.
### TC-GRANT-003 — E-Invoice opens, and never says LIVE

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, Sales → **E-Invoice**.
- **Expect:** offered and opens. Wherever a mode is shown it reads **`SANDBOX`**; if it reads LIVE anywhere, stop — that is not cosmetic. `mode` is NOT NULL with no server default on both e-invoice tables, and the sandbox marks every reference it mints `SBX…`. *(QA01 has registered nothing, so the grid may be empty and show no mode at all; that passes.)*
### TC-GRANT-004 — Loyalty: the banner states the scheme, and a firm can change it

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **QA01's scheme is shared by every run.** It starts **off**; switch it back off at the end.
- **Steps**
  1. As the prepared **Firm admin**, Masters → **Loyalty**. Read the banner.
  2. **Scheme settings** → switch **Scheme is running** on; **Minimum to redeem** `50`; **Points expire** off → Save.
  3. Scheme settings → switch **Scheme is running** off → Save.
- **Expect**
  - Step 1: "No scheme is running: nobody is earning anything."
  - Step 2: the dialog saves and the banner re-reads: "1 points per 100, worth 1 each and never expire. At least 50 before any can be spent."
  - Step 3: back to "No scheme is running…".
  - *Until #399 there was no editor at all: the settings route, the code and the grant existed, and the desktop carried only the read.*
### TC-GRANT-005 — Loyalty settings are readable by somebody who cannot change them

- **Preconditions:** A QA01 user hired with the *Sales Manager* job template. (`SALES_MANAGER`, which holds `LOYALTY_VIEW` and not `LOYALTY_MANAGE_SETTINGS`.)
- **Steps**
  1. Sign in as the prepared **Loyalty viewer** → Masters → Loyalty → **Scheme settings**.
  2. **(HTTP)** As them, `PUT /api/v1/loyalty/settings` with the body `GET` returned.
- **Expect**
  - Step 1: it **opens**, read-only, saying "Changing the scheme needs the manage loyalty settings permission." Offered rather than hidden on purpose: whoever is asked why a balance is what it is should reach the rule behind it.
  - Step 2: **403**. Whoever a scheme constrains must not rewrite what it is worth.
### TC-GRANT-006 — TCS settings open, and TCS is off

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, Sales → **TCS** → **Settings**; save without changing anything.
- **Expect:** offered, opens and saves. **Collect under section 206C(1H)** is off — it defaults false so shipping the feature charged nobody. Leave it off: on, every receipt in QA01 collects TCS, and other cases record receipts there.
### TC-GRANT-007 — The fix was a grant, not a wider gate

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps:** sign in as the prepared **Seller**; open **Sales**, then **Masters**.
- **Expect:** Sales is offered — `SALES_VIEW` is one of their six codes — with **no** Credit Notes, Proforma, E-Invoice or TCS; Masters has **no** Loyalty. Any of the five appearing means a tab lost its own code and its module gate is carrying it alone.
### TC-GRANT-008 — The server grants all five

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps (HTTP)** — as the prepared firm admin with `X-Firm-ID` QA01: `GET /api/v1/credit-notes`, `/api/v1/proforma-invoices`, `/api/v1/einvoice/registrations`, `/api/v1/loyalty/settings`, `/api/v1/tcs/settings`.
- **Expect:** **200** on all five. They answered 403 before `20260906_0130`. The screens being offered is the desktop honouring the claims; these are the claims being there.
---

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
