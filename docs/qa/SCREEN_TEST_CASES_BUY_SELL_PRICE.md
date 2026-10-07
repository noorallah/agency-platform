# Screen test cases: selling, buying and pricing (phase 2 desktop)

Written 2026-10-07. Part of the QA material in `docs/qa/`, but **not generated**:
`docs/qa/tools/generate_qa_suite.py` writes only the numbered files `00` to `14`
and `docs/qa/` carries no other generated name, so this file is edited by hand.

## Purpose

The cases in `06_PURCHASING.md`, `08_SELLING.md` and `09_PRICING_AND_INCENTIVES.md`
(TC-BUY, TC-SELL, TC-INCENT) were driven over HTTP and carry the figures. This
book is about what a **person sees and can do on each screen** of the phase 2
desktop app: what opens, which buttons are offered, what a refusal looks like,
and what the next user sees. The owner asked for the cases to be written down
first, feature by feature; the click tests under `desktop/integration_test/` are
then written and reported against these ids.

Each case links to the existing case that holds the figures (the **Book case**
column) rather than restating them. Where no figure is needed, none is given.

## How to read a case

| Column | Meaning |
| --- | --- |
| Id | `SC-<FEATURE>-<nnn>`. Stable: never renumber; add new cases at the end of a feature. |
| Kind | Positive, Negative, Role or Multi-user (defined below). |
| User (role) | The user id from the table below. "and" means two sessions at once; "then" or a comma list means hand-over in that order. |
| Before | The data the case needs. "Fixture firm" is the firm described below. |
| Steps on screen | Menu path, button names and field labels as the screen spells them. Quoted text is on the screen. |
| Expected on screen | What the person sees. Wording given in quotes is taken from the code; "wording on first run" means the refusal exists but its exact text has not been read from the screen yet (see Open questions). |
| Book case | The TC id (or `0N-Sxx` screen check, or `01-ROLES Rxx` role-matrix section) that holds the figures or the same rule. |
| Automated in | The flow file and step name in `desktop/integration_test/` that already covers it, or "not yet". The flows are on branch `test/desktop-flows-buy-sell-price` (`selling_flow_test.dart`, `buying_flow_test.dart`, `pricing_flow_test.dart`, `harness.dart`). |
| Result | Blank means not run. Use Pass, Fail, Blocked, with a note. |

### The four kinds

- **Positive.** The list opens; new, fill, save; reopen, change, save; each
  lifecycle button; the next document raised from it; print or send; search,
  filter and counters.
- **Negative.** Missing fields; zero, negative or over-limit quantities;
  over-delivery, over-billing, over-return, over-payment; wrong dates;
  duplicates; acting in the wrong status; expired or exhausted offers; more
  points than held; closing a typed-in editor without saving.
- **Role.** Whether the screen is in the menu for the role, which buttons it
  offers, and what happens when the role acts outside its rights.
- **Multi-user.** A hand-over along the chain (each user sees the last user's
  document and status), two users editing one record, and a list refreshed after
  another user's change.

### The three checks every Negative case makes

Every Negative case, where its Expected cell says "Checks N1 to N3 hold" or names
a refusal, passes only if all three are true:

- **N1.** The refusal is shown in words a person can act on (it names the field,
  the limit or the document), not a code, not a blank, not a stack trace.
- **N2.** The editor or dialog **stays open with everything typed kept**; the
  person can correct one thing and press Save again.
- **N3.** **Nothing was saved**: the list, the stock and the books (Accounts >
  Journal Entries, Stock > Stock Summary) are as they were before the attempt.

Two refusals are common to all editors and are not repeated per case:

- Closing an editor with typing in it asks **"Discard unsaved changes?"** with
  **Keep editing** and **Discard changes**. Keep returns with everything typed.
  Discard closes with nothing saved.
- A save made from an old copy of a record is told **"This record changed since
  you loaded it. Reload and try again."** (HTTP 409). The typed values stay on
  screen and the other user's change is not lost.

## How a case is run

- **By hand.** Sign in as the user named, follow the steps, compare with
  Expected, write the result. Menu paths are the 1.3.0 light menu: **Sell** and
  **Buy** show the daily list; **All Sell screens** and **All Buy screens** are one
  click further; the gear opens **Settings** (price lists, promotions and
  loyalty are under **Settings > Set up > Pricing**). Each case stands alone: it
  says what it needs under Before.
- **By flow.** A case with a name in Automated in is run by
  `bash integration_test/run.sh <file>` from `desktop/` with `IT_EMAIL` and
  `IT_PASSWORD` set for the fixture firm's administrator, one run at a time, with
  the backend up (see `docs/qa/SCREEN_FLOW_CHECK_ROUND_1_2026-10-07.md` on the same
  branch). A flow reports `FLOW: PASS|FAIL|DEFECT|SKIP` per step; report those
  against the ids here. A Result of Pass for a flow-covered case means the step
  passed **and** nothing in the case's Expected cell was contradicted by the
  screen.
- **Never** run a full suite to do this; run one flow or one case at a time.

## The fixture firm

One firm, set up as the `selling-firm` fixture of `08_SELLING.md` (customers
**Vijaya Stores** with a 7.5 percent standing rate and **Anand**; product
**Detergent 1kg** at 84 with GST 18 and 100 in stock; the firm-wide price list
STANDING; offers BULK5, BIGORDER, CLEARANCE and the coupon-only WELCOME with
`WELCOME10`), plus a supplier **Principal supplier**, a customer group, a price
level, loyalty switched on at 2 points per 100, a salesman with a commission
rule, and a principal-funded offer. Counter billing is on for the counter cases.
Credit control is left at its default (warn at 80 percent, never block) unless a
case says it is switched on. `docs/qa/14_TEST_DATA.md` has the values to type.
Figures in a case are small round numbers; take the exact ones from the Book case.

## The users

Hire one user per job with **Settings > Platform > People > Users > + New**,
naming the job in **Job template**, all in the fixture firm. The seeded roles and
their codes are in `backend/app/identity/system_seed.py` and the matrix in
`01_ROLES_AND_ACCESS.md` (the section for each user is shown in the last column).

| User id | Job template | Role codes | What it can and cannot do on these screens | Matrix |
| --- | --- | --- | --- | --- |
| FA | Firm Administrator | FIRM_ADMIN | Everything in the firm, including approving over budget and over tolerance, price lists, offers, loyalty settings. | R01 |
| FM | Firm Manager | FIRM_MANAGER | Everything operational; not firm administration. Used only where a case says FM. | R02 |
| CS | Counter Sales | CASHIER, BILLING_EXECUTIVE | Cashier role: records receipts and payments. Billing Executive role: raises sales bills and sends them; cannot approve or cancel. Neither sees quotations, orders or delivery notes beyond the list (SALES_VIEW). | R03 |
| FS | Field Sales | SALES_EXECUTIVE | Raises quotations, orders and bills; adds customers. Cannot approve, hold, cancel, close, override a price, or see receipts, credit notes, price lists, offers, commission. | R04 |
| SM | Sales Manager | SALES_MANAGER | All sales documents including approve, hold, cancel, close and returns; drafts credit notes and debit notes but cannot approve them; reads offers and commission; spends and adjusts loyalty points. Cannot change the credit policy, the sales stages, a customer's price level or bank details, or override the price floor; cannot pay commission. | R05 |
| WH | Warehouse | INVENTORY_MANAGER | Receives, stores, picks and dispatches stock; raises and completes goods receipts; inspects goods. Cannot order, bill or return to a supplier. | R06 |
| PU | Purchasing | PURCHASE_EXECUTIVE | Raises requisitions, orders, receipts, bills, returns; manages supplier schemes. Cannot approve, inspect, approve over budget or tolerance, or change purchase settings. | R07 |
| PM | Purchase Manager | PURCHASE_MANAGER | All purchasing including approve; drafts supplier debit notes but cannot approve them. Cannot change purchase settings or a supplier's bank details; holds no payment code. | R08 |
| AC | Accounts | ACCOUNTANT | Records and reverses receipts and payments, runs payment runs, clears small party balances, manages and pays commission, manages credit control. Holds no purchase or sales document codes. | R09 |
| SUP | Customer Support | CUSTOMER_SUPPORT | Customers and products only. Expected to see none of the screens in this book. | R10 |
| RO | Read Only | VIEWER | Reads every screen it is offered; every write button is absent or disabled. | R11 |
| Clerk | A hired job: clone of Firm Manager, with COMMISSION_MANAGE and without COMMISSION_PAY | custom | Used only for the commission separation case (no seeded role holds the one without the other). | none |

A second session of the same job is written FA2, SM2, PM2 and so on: a different
user with the same job template, or the same user signed in on a second PC.

## Abbreviations

PO purchase order; GRN goods receipt; STANDING the firm-wide price list;
Draft, Approved, Dispatched, Completed, Closed, Cancelled are the statuses the
list's Status column shows. "Chips" are the view buttons above a grid. "Cards"
are the counters above a grid.


# Part 1. Selling


## QT. Quotations

**Where and who.** Sell > Quotations (daily list). Offered to FA, FM, SM, FS, RO (read only). Not offered to CS, WH, PU, PM, AC, SUP.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-QT-001 | Positive | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | Open Sell > Quotations. Look at the grid, press Refresh. | Grid shows Quotation Number, Customer, Quotation Date, Valid Until, Status, Grand Total. No error. An empty firm shows an empty-state message, not a blank grid. | 08-S01 | not yet |  |
| SC-QT-002 | Positive | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New. Customer: Vijaya Stores. Add Detergent, quantity 10. Save. | Editor closes or shows the saved draft. Notice says the quotation is drafted and good until the valid date, and that nothing is reserved. List shows the new number, status Draft, correct Grand Total. | SELL-001 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-QT-003 | Positive | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | Select the saved row. Look at its number and total in the list. | The number and the grand total on the screen are the same as in the editor (taxable value plus tax). | SELL-001 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-QT-004 | Positive | FS | Vijaya has a 7.5 percent standing rate; firm price list STANDING on Detergent | New quotation, add Detergent qty 10, leave the discount box blank. | Helper text under the blank discount box names the rate taken and where it came from (the price list, not the standing rate). The box itself is not prefilled. | SELL-001, INCENT-001 | not yet |  |
| SC-QT-005 | Positive | FS | A saved Draft quotation | Select it, press Revise, change quantity 10 to 12, Save. | Editor opens with the existing lines. After Save the list shows the new total. Version of the record moves once. | 08-S01 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-QT-006 | Positive | FS | A saved Draft quotation | Select it, press Mark as sent. | Status becomes Sent. Status badge on the list says so. Mark as sent is no longer offered. | 08-S01 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-QT-007 | Positive | FS | A Sent quotation | Press Customer accepted. | Status becomes Accepted. Convert to order is now offered. | SELL-005 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-QT-008 | Positive | FS | An Accepted quotation | Press Convert to order. | Status becomes Converted. A sales order exists for the same customer and lines. Open Sell > Sales Orders: it is there as Draft. | SELL-005 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-QT-009 | Positive | FS | A Sent quotation | Press Customer declined. | Status becomes Declined (Outcome column says so). Convert to order is not offered. | 08-S01 | not yet |  |
| SC-QT-010 | Positive | FS | A Draft quotation | Press Withdraw, confirm. | Status becomes Withdrawn. It cannot be revised or converted afterwards. | 08-S01 | not yet |  |
| SC-QT-011 | Positive | FS | A saved quotation | Press Print. Press Send. Press Attachments. | Print opens a preview with the firm header and the lines. Send offers the channels the firm has set up and refuses by name if none is. Attachments opens the files window. | SELL-034, SELL-035 | not yet |  |
| SC-QT-012 | Positive | FS | Firm has the Rate includes GST option | New quotation. Tick Rate includes GST. Add Detergent at 118. Save. | Taxable value is 100 and tax 18; grand total stays 118. | SELL-021 | not yet |  |
| SC-QT-013 | Positive | FS | Coupon WELCOME10 exists (WELCOME offer) | New quotation, type WELCOME10 in Coupon, add a line over the offer minimum, Save. | The offer's discount shows on the line. Saving with a code nobody recognises gives no discount and no refusal. | SELL-006 | not yet |  |
| SC-QT-014 | Positive | FS | Several quotations of different status | Type part of a number in Search. Pick a status filter. Sort by Valid Until. | Grid narrows to matching rows; counters agree with the rows; clearing the filter brings all rows back. | 08-S01 | not yet |  |
| SC-QT-015 | Positive | FS | An enquiry exists | Open the enquiry, use its action to raise a quotation. | A quotation editor opens with the customer and products filled from the enquiry. | SELL-028 | not yet |  |
| SC-QT-016 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New. Leave Customer empty. Add a line. Save. | Checks N1 to N3 hold. Message names the customer as missing. | 08-S01 | not yet |  |
| SC-QT-017 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New. Pick the customer, add no line. Save. | Checks N1 to N3 hold. Message says a line is needed. | 08-S01 | not yet |  |
| SC-QT-018 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New. Add Detergent with quantity 0. Save. | Checks N1 to N3 hold. Message says the quantity must be more than zero. | SELL-090 | not yet |  |
| SC-QT-019 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New. Add Detergent with quantity -5. Save. | Checks N1 to N3 hold. The quantity box refuses it or the save is refused in words. | SELL-090 | not yet |  |
| SC-QT-020 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New. Set Valid until a day before Quotation date. Save. | Checks N1 to N3 hold. Message names the dates. Exact wording to be established on the first run. | 08-S01 | not yet |  |
| SC-QT-021 | Negative | FS | A Draft quotation | Select it. Look for Convert to order. | Convert to order is not offered, or is disabled with a reason, until it is Accepted. If forced through a stale list, the server refusal is shown. | SELL-005 | not yet |  |
| SC-QT-022 | Negative | FS | A Converted quotation | Select it. Try Convert to order again. | Not offered. No second order appears in Sales Orders. | SELL-005 | not yet |  |
| SC-QT-023 | Negative | FS | A Converted quotation | Try Revise, Withdraw, Customer declined. | Each is not offered, or refused in words. Nothing changes. | SELL-005 | not yet |  |
| SC-QT-024 | Negative | FS | A quotation past its Valid Until | Look at the list row. Try Convert to order. | Row carries the EXPIRED badge. Whether conversion is refused or allowed is to be established on the first run. | 08-S01 | not yet |  |
| SC-QT-025 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New, type a customer and two lines, press the close button of the editor. | A question 'Discard unsaved changes?' with Keep editing and Discard changes. Keep editing returns with everything typed. Discard closes with nothing saved. | 08-S01 | not yet |  |
| SC-QT-026 | Negative | FS | Customer Vijaya on a firm that blocks sales to inactive customers, or an inactive customer | New quotation for that customer. Save. | Refusal in words naming the customer. Editor open, typed values kept. Exact rule to be established on the first run. | 08-S01 | not yet |  |
| SC-QT-027 | Role | FS | Field Sales hired by template | Sign in. Open the Sell menu. | Quotations is offered. New, Revise, Mark as sent, Customer accepted, Convert to order are offered (SALES_QUOTATION_CREATE). | 01-ROLES R04 | not yet |  |
| SC-QT-028 | Role | RO | Read Only user | Open Sell > Quotations. | List opens with rows. New, Revise and every lifecycle button are absent or disabled with a reason. | 01-ROLES R11 | not yet |  |
| SC-QT-029 | Role | CS | Counter Sales user (Cashier role and Billing Executive role) | Look in the Sell menu. | Cashier role: no Quotations. Billing Executive role: list is readable (SALES_VIEW) but New is not offered (no SALES_QUOTATION_CREATE). | 01-ROLES R03 | not yet |  |
| SC-QT-030 | Role | FS | Field Sales has no SALES_PRICE_OVERRIDE | On a line, type a rate lower than the price floor, or a discount past the limit set in Settings > Selling > Discount Limits. Save. | Refused in words, or flagged for approval; editor stays open. Exact behaviour to be established on the first run. | SELL-022 | not yet |  |
| SC-QT-031 | Multi-user | FS then SM | FS has saved a Draft quotation | FS saves and signs out. SM opens Sell > Quotations and refreshes. | SM sees the quotation with the same number, total and status FS left. | 08-S01 | not yet |  |
| SC-QT-032 | Multi-user | FS and FA | Same Draft quotation open in two sessions | FA changes quantity and saves. Then FS, still on the old copy, changes the note and saves. | FS is told 'This record changed since you loaded it. Reload and try again.' FS's typed values stay on screen. FA's save is not lost. | 08-S01 | not yet |  |

## SO. Sales orders

**Where and who.** Sell > Sales Orders (daily list). Offered to FA, FM, SM, FS, RO. Hold, Release, Approve and Close need SALES_APPROVE.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-SO-001 | Positive | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | Open Sell > Sales Orders. | Grid shows Order Number, Customer, Order Date, Delivery Date, Status, Taxable Value, Tax, Freight, Grand Total. Cards show Approved, Cancelled and Closed counts. | 08-S02 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: columns present; cards: Draft, Approved, Cancelled, Closed, Draft, Draft |
| SC-SO-002 | Positive | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New. Customer Vijaya Stores, line Detergent qty 10, Save. | Draft order saved. Number, total and Draft status on the list. Customer, Branch (ships from), Salesman and Wanted by are fields in the editor. | SELL-007 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-SO-003 | Positive | SM | A Draft order | Select it, press Approve. | Status Approved. Stock for the lines is reserved (Stock > Stock Summary shows reserved). The offer claimed, if any, is counted once. | SELL-007 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-SO-004 | Positive | FS | Customer with a standing 7.5 percent; price list STANDING | New order, add Detergent qty 20, leave the discount blank, Save. | The line shows the rate taken from the price list break; a typed 0 would refuse every arrangement. Helper text says what blank takes. | SELL-001, SELL-004 | not yet |  |
| SC-SO-005 | Positive | FS | An offer BULK5 active | New order, Detergent qty 30. | Offer discount shows on the line; the reason names the offer. | SELL-004 | `pricing_flow_test.dart` | Pass 2026-10-07 |
| SC-SO-006 | Positive | FS | Draft order | Select, press Edit (or reopen), change quantity, Save. | Only a Draft is editable; the new quantity and total show in the list. | 08-S02 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: quantity 5 saved, total 472.0 |
| SC-SO-007 | Positive | SM | An Approved order | Press Hold. Type a reason. Confirm. | Order shows on hold; status stays Approved; stock stays reserved. A note says it cannot be dispatched until released. | SELL-008 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, on hold true, notice "SO-2026-2027-000070 is on hold." |
| SC-SO-008 | Positive | SM | An order on hold | Press Release. | Hold flag goes. The order is back at the status it had. | SELL-008 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, on hold false, notice "SO-2026-2027-000070 released." |
| SC-SO-009 | Positive | SM | Order whose reservation lapsed | Open it. Press Reserve again. | Stock held again; the banner 'Stock hold lapsed' goes. | SELL-095 | not yet |  |
| SC-SO-010 | Positive | SM | Order partly delivered and billed | Look at the status after each part delivery. | Status moves with what was delivered (derived, never counted up). | SELL-009 | not yet |  |
| SC-SO-011 | Positive | SM | An Approved order with nothing delivered | Press Cancel, give the reason, confirm. | Status Cancelled. Message says stock is released. Stock Summary shows it free again. | SELL-007 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: status CANCELLED, screen says "SO-2026-2027-000075 cancelled. Its stock is released." |
| SC-SO-012 | Positive | SM | A fully delivered and billed order | Press Close. | Status Closed. | SELL-009 | not yet |  |
| SC-SO-013 | Positive | SM | Several Draft orders | Tick three rows. Press Approve selected. Then tick two and press Cancel selected. | A result per row: each approved or refused with its own message. A refusal does not stop the others. | 08-S02 | `sc_so_test.dart` (tradeadmin) | Skipped 2026-10-07: bulk selection checkboxes not reached in two attempts |
| SC-SO-014 | Positive | FS | Order | Press Print, Send, Attachments. | Print preview opens; Send and Attachments behave as on the quotation. | SELL-034 | not yet |  |
| SC-SO-015 | Positive | SM | Approved order | Raise a Proforma from it (Sell > All Sell screens > Documents > Proforma > New). | The proforma names the order. See Proforma section. | SELL-017 | not yet |  |
| SC-SO-016 | Positive | SM | Order with one line and a delivery charge | Open the order. Add a delivery charge and a document discount. | Both reach the line and the tax; grand total agrees with the lines. | SELL-050 | not yet |  |
| SC-SO-017 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New order without a customer. Save. | Checks N1 to N3 hold. Customer named as missing. | 08-S02 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Check the fields marked below." |
| SC-SO-018 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New order, no lines. Save. | Checks N1 to N3 hold. A line is required. | 08-S02 | `sc_so_test.dart` (tradeadmin) | Fail 2026-10-07: note: :: editor after the customer is chosen: S( / Sales Orders / New sales order / New sales order / Draft / Enter next field  ·  Ctrl+Enter new line  ·  Ct... |
| SC-SO-019 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | Line quantity 0, then -3. Save. | Checks N1 to N3 hold. Quantity must be more than zero. | SELL-090 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Check the fields marked below. / Enter the quantity."; note: :: quantity box now reads "Detergent 1kg t10069cwy  T10069CWY-DET / 0 ... |
| SC-SO-020 | Negative | FS | Detergent stock 100 | Order 500 units. Save, then Approve (as SM). | Whether Approve refuses for short stock or reserves what exists is to be established on the first run; whichever it is, the message is in words and the status is unchanged on refusal. | SELL-007 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: status after Approve: APPROVED, screen says ""; Approve of a success is silent by design, and 500 units against the stock on hand were accepted without a word |
| SC-SO-021 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | Set Wanted by to a date before Order date. Save. | Checks N1 to N3 hold. Message names the dates. | 08-S02 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: date picker opened; the screen cannot be given a date before the order date (first selectable day is the order date) |
| SC-SO-022 | Negative | SM | Customer whose credit limit would be passed | Approve an order that takes the customer past 80 percent, then past 100 percent of the limit. | Warns only (a notice with the figures); approval still goes through unless the firm has switched blocking on in Credit Control. With blocking on, approval is refused in words and the order stays Draft. | 08-S02, CLAUDE sales chain | `sc_so_test.dart` (tradeadmin) | Skipped 2026-10-07: no customer with a credit limit in the fixture firm; needs a customer made for it (CC section) |
| SC-SO-023 | Negative | SM | An Approved order | Try Edit. | Edit is not offered, or a message says only a Draft can be edited. Nothing changes. | SELL-007 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: Edit is absent on an Approved order |
| SC-SO-024 | Negative | SM | An Approved order | Press Approve again (stale list). | Message that only a Draft can be approved; no second reservation. | SELL-007 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: screen says "Only draft sales orders can be approved."; status APPROVED |
| SC-SO-025 | Negative | SM | An order with a delivery note resting on it | Press Cancel. | Refused in words naming the delivery note, or the note is dealt with first. Exact wording to be established on the first run. | SELL-009 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, screen says "SO-2026-2027-000074 cannot be cancelled while delivery note DN-26-27-000019 stands against it. Cancel those first, or close the... |
| SC-SO-026 | Negative | SM | An order on hold | Open Delivery Notes, New, pick this order. | Dispatch is refused while on hold; the message says the order is on hold. | SELL-008 | `sc_so_test.dart` (tradeadmin) | Skipped 2026-10-07: needs a delivery note editor session on a held order; done in the DN file |
| SC-SO-027 | Negative | SM | An Approved order | Press Hold and leave the reason empty. | Hold is not recorded; the reason box asks for a reason. | SELL-008 | `sc_so_test.dart` (tradeadmin) | Fail 2026-10-07: Bad state: N1: the dialog closed and nothing said a reason is needed |
| SC-SO-028 | Negative | SM | Offer with a total-uses cap of 1 and two Draft orders using it | Approve the first, then the second. | The loser is refused by name at approval; it is not silently repriced. | SELL-092 | `sc_so_test.dart` (tradeadmin) | Skipped 2026-10-07: needs an offer with a total-uses cap of 1; built in the OF section |
| SC-SO-029 | Negative | FS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New order, type a customer and a line, press the editor's close button. | Question 'Discard unsaved changes?'. Keep editing keeps everything. Discard closes, nothing saved. | 08-S02 | `sc_so_test.dart` (tradeadmin) | Fail 2026-10-07: Esc did nothing: the editor stayed open and asked nothing (the Cancel button is judged in the next step); Bad state: the Cancel button closed an editor holdi... |
| SC-SO-030 | Role | FS | Field Sales (no SALES_APPROVE) | Open a Draft order. | New and Edit are offered. Approve, Hold, Release, Close are absent or disabled with a reason. | 01-ROLES R04 | `sc_so_test.dart` (qsexe) | Pass 2026-10-07: {New Order: absent, + New: enabled, Edit: enabled, Approve: absent, Hold: absent, Release: absent, Close: absent} |
| SC-SO-031 | Role | FS | Field Sales | Try to Cancel an order. | Cancel is absent (no SALES_CANCEL) or refused: 'You do not have permission to perform this action.' | 01-ROLES R04 | `sc_so_test.dart` (qsexe) | Pass 2026-10-07: Cancel is absent |
| SC-SO-032 | Role | SM | Sales Manager | Open Settings > Selling > Credit Control and Sales Stages. | The credit policy cannot be changed by this role (no CUSTOMER_MANAGE_SETTINGS); Sales Stages likewise (no SALES_MANAGE_SETTINGS). Saving is refused or the control is read only. | 08-S02 | `sc_so_test.dart` (qsmgr) | Pass 2026-10-07: credit settings PUT 403, sales stages PUT 403 (HTTP level; the settings screens not opened) |
| SC-SO-033 | Role | RO | Read Only | Open Sell > Sales Orders. | Rows are readable; no New, Edit, Approve, Cancel. | 01-ROLES R11 | `sc_so_test.dart` (qro) | Pass 2026-10-07: {+ New: absent, New Order: absent, Edit: absent, Approve: absent, Hold: absent, Cancel: absent, Close: absent} |
| SC-SO-034 | Multi-user | FS, SM, WH | FS raises a Draft order | FS saves. SM approves. WH opens Sell > Delivery Notes. | SM sees FS's Draft; after approval FS's refreshed list shows Approved; the order is offered to the delivery note editor ('approved orders only'). | SELL-007 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: note: :: the storekeeper (INVENTORY_MANAGER) is refused the order list with 403 and is not offered Delivery Notes; 01_ROLES R06 lists no Sell screen for it, ... |
| SC-SO-035 | Multi-user | SM and FA | Same Approved order open on two sessions | FA places it on hold. SM, not refreshed, presses Cancel. | SM's action is refused or told the record changed; no stock is released twice. | SELL-008 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: status CANCELLED, on hold true, screen says "SO-2026-2027-000076 cancelled. Its stock is released." |
| SC-SO-036 | Multi-user | SM | Two sessions showing the Sales Orders list | Session A approves an order. Session B presses Refresh. | Session B shows the new status and updated counters. | 08-S02 | `sc_so_test.dart` (tradeadmin) | Pass 2026-10-07: row reads: SO-2026-2027-000078 / Vijaya Stores t10069cwy / 2026-10-07 02:03 / Approved / 94.40 |

## DN. Delivery notes

**Where and who.** Sell > Delivery Notes (daily list). Offered to FA, FM, SM, WH (needs the sales codes: WH sees it only if its role grants SALES_VIEW; to be confirmed), RO.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-DN-001 | Positive | SM | An Approved sales order for Detergent 10 | Open Sell > Delivery Notes. | Grid shows Note Number, Customer, Sales Order, Delivery Date, Vehicle, Driver, Freight, Quantity Delivered, Status, Delivered. Cards show Approved, Dispatched, Completed, Cancelled. | 08-S03 | `sc_dn_test.dart` (tradeadmin) | Pass 2026-10-07: columns present |
| SC-DN-002 | Positive | SM | Approved order | New. Choose the order under 'Sales order (approved orders only)'. Save. | Lines come from the order with quantities still owed. Draft note saved. | SELL-010 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-DN-003 | Positive | SM | Draft note | Press Approve. | Status Approved. Stock does not leave yet unless the firm's stage setting says so. | SELL-018 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-DN-004 | Positive | SM | Approved note | Press Dispatch. | Status Dispatched. Stock Ledger shows the issue. The order status moves with the part delivery. | SELL-009 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-DN-005 | Positive | SM | Approved note | Press Dispatch and invoice. | A dialog confirms; on Dispatch and invoice, the note is dispatched and a bill is raised. The notice says 'Dispatched and invoiced.' | SELL-018 | not yet |  |
| SC-DN-006 | Positive | SM | Part delivery: note for 4 of 10 | Dispatch. Raise a second note for the rest. | Order shows partly delivered, then fully delivered. Second note offers 6. | SELL-009 | not yet |  |
| SC-DN-007 | Positive | WH | Product with batches | On the note line choose the batch. Save. | Only batches with stock are offered, nearest expiry first; the customer's minimum shelf life is respected. | SELL-019, SELL-024 | not yet |  |
| SC-DN-008 | Positive | SM | Dispatched note | Press Print challan, Pick list, Loading sheet, Print settings. | Each opens a preview or a print; the pick list and loading sheet list the products and quantities. | SELL-030 | not yet |  |
| SC-DN-009 | Positive | SM | Carrier master has a transporter | In the editor choose Carrier (master). | Transporter, GSTIN, mode are filled; what is typed on the note afterwards wins. | SELL-056, SELL-057 | not yet |  |
| SC-DN-010 | Positive | SM | Dispatched note | Press Proof of delivery, record it. Press E-way bill. | Delivered column shows the date; the E-way bill dialog opens (or says the firm is not set up). | 08-S03 | not yet |  |
| SC-DN-011 | Positive | SM | Dispatched notes for the same customer | Use the view chip 'Not yet delivered'. | Only notes without proof of delivery show. | 08-S03 | not yet |  |
| SC-DN-012 | Positive | SM | Dispatched notes for one customer | Open Sales Invoices, New, bill several notes. | Customer-first choice; see Sales bills section. | SELL-027 | not yet |  |
| SC-DN-013 | Negative | SM | Order for 10 | New note. Enter quantity 11 on the line. Save. | Checks N1 to N3 hold. Message says the quantity is more than is still owed on the order. | SELL-009 | `sc_dn_test.dart` (tradeadmin) | Pass 2026-10-07: note: :: quantity-related text on screen after Save: Stock / Delivery Notes / New delivery note / New delivery note / Save delivery note / Line 1 delivers 99... |
| SC-DN-014 | Negative | SM | Detergent stock 5 | Note for 10. Approve and Dispatch. | Refused in words naming the product and what is in stock. Note stays Approved; stock unchanged. | SELL-007 | `sc_dn_test.dart` (tradeadmin) | Skipped 2026-10-07: stock cannot be set to 5 without moving the firm; on hand is 82 and approved orders reserve more than that (see SCRQ findings on over-reservation) |
| SC-DN-015 | Negative | SM | Order not approved (Draft) | Open the note editor and look for that order. | A Draft order is not offered in the order box. | SELL-007 | `sc_dn_test.dart` (tradeadmin) | Fail 2026-10-07: note: :: server approved list has SO-2026-2027-000112; the box offers SO-2026-2027-000107  07-10-2026  Vijaya Stores t10069cwy / SO-2026-2027-000106  07-10-2... |
| SC-DN-016 | Negative | SM | Draft note | Delivery date set in the future. Save, Dispatch. | Dispatch of a future date is refused or flagged; exact rule to be established on the first run. | 08-S03 | `sc_dn_test.dart` (tradeadmin) | Skipped 2026-10-07: the date box offers no future date in two attempts |
| SC-DN-017 | Negative | SM | Draft note, quantity 0 on all lines | Save. | Checks N1 to N3 hold. At least one line with a quantity is needed. | SELL-090 | `sc_dn_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Enter a delivery quantity on at least one line. A line with nothing reserved cannot be dispatched until the order is approved. / Ze... |
| SC-DN-018 | Negative | SM | An Approved note | Try Edit. | Edit not offered, or 'Only draft delivery notes can be updated.' shown. | SELL-018 | `sc_dn_test.dart` (tradeadmin) | Pass 2026-10-07: Edit is absent on an Approved note (the editor only creates; no Edit exists for a note in any status) |
| SC-DN-019 | Negative | SM | A Draft note | Press Dispatch. | 'Only approved delivery notes can be dispatched.' (or the button is not offered). | SELL-018 | `sc_dn_test.dart` (tradeadmin) | Pass 2026-10-07: Dispatch is absent on a Draft note |
| SC-DN-020 | Negative | SM | A Dispatched note that is already billed | Press Cancel. | Refused in words naming the bill resting on it. Note stays Dispatched. | SELL-011 | `sc_dn_test.dart` (tradeadmin) | Skipped 2026-10-07: needs a billed dispatched note; chain done in the SB file |
| SC-DN-021 | Negative | SM | Order on hold | Dispatch a note off that order. | Refused: the order is on hold. | SELL-008 | `sc_dn_test.dart` (tradeadmin) | Pass 2026-10-07: note status APPROVED; said "SO-2026-2027-000113 is on hold and cannot be dispatched ("dispatch test"). Release it first." |
| SC-DN-022 | Negative | SM | Carrier marked inactive | Open the Carrier (master) box. | An inactive carrier is not offered. | SELL-058 | `sc_dn_test.dart` (tradeadmin) | Skipped 2026-10-07: no carrier master record in the fixture firm |
| SC-DN-023 | Negative | SM | New note editor with typing | Close the editor. | 'Discard unsaved changes?' question; Keep editing keeps all. | 08-S03 | `sc_dn_test.dart` (tradeadmin) | Fail 2026-10-07: Bad state: Cancel closed an editor holding a typed quantity without asking |
| SC-DN-024 | Role | FS | Field Sales | Look in Sell menu for Delivery Notes. | Whether offered is to be established (no delivery code held beyond SALES_VIEW); if offered, no Approve or Dispatch button. | 01-ROLES R04 | `sc_dn_test.dart` (qro) | Pass 2026-10-07: buttons {+ New: absent, Approve: absent, Dispatch: absent, Cancel: absent} |
| SC-DN-025 | Role | WH | Warehouse | Sign in, open the menu. | Warehouse role holds inventory and PURCHASE_RECEIVE; Delivery Notes visible only if SALES_VIEW is held. Result recorded either way and matched to docs/qa/01_ROLES_AND_ACCESS.md R06. | 01-ROLES R06 | `sc_dn_test.dart` (qstore) | Pass 2026-10-07: Delivery Notes offered: false; menu areas sell, buy, stock, masters; list answers 403 |
| SC-DN-026 | Role | SM | Sales Manager with Sales Stages set to type delivery notes | Look at Settings > Selling > Sales Stages. | Cannot switch the delivery-note stage off (no SALES_MANAGE_SETTINGS). | 08-S03 | `sc_dn_test.dart` (qsmgr) | Pass 2026-10-07: stages PUT answered 403 (HTTP level) |
| SC-DN-027 | Role | FS | A note the user cannot approve | On Dispatch and invoice, if SALES_APPROVE is missing. | The dialog says dispatching and invoicing needs the permission to approve and offers only Cancel. | SELL-018 | not yet |  |
| SC-DN-028 | Multi-user | FS, SM, WH, SM | FS order approved by SM | WH raises the note and dispatches; SM opens the order. | Each sees the previous user's document and status; the order shows part or full delivery. | SELL-009 | not yet |  |
| SC-DN-029 | Multi-user | SM and SM2 | Two sessions on one Draft note | Session A saves a new vehicle; session B saves a new driver from the old copy. | B is told the record changed; B's typing stays; A's change is intact. | 08-S03 | `sc_dn_test.dart` (tradeadmin) | Skipped 2026-10-07: the delivery note editor only creates; a saved note cannot be opened for change on screen, so there is no second session to race |
| SC-DN-030 | Multi-user | SM | Two sessions, one Approved note | A dispatches. B presses Dispatch from a stale list. | B refused: 'Only approved delivery notes can be dispatched.' No second stock issue. | SELL-018 | `sc_dn_test.dart` (tradeadmin) | Fail 2026-10-07: Bad state: N1: Dispatch of a note another user had already dispatched said nothing after the dialog was confirmed |

## SB. Sales bills (sales invoices, including the counter bill)

**Where and who.** Sell > Sales Invoices (daily list). The counter bill is the same editor with Counter sale ticked; shifts are at Sell > All Sell screens > Documents > Counter Shifts. Offered to FA, FM, SM, FS, CS (Billing Executive role), RO.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-SB-001 | Positive | CS | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | Open Sell > Sales Invoices. | Grid shows Invoice Number, Customer, Date, Status, Payment Terms, Taxable Value, Tax, Grand Total; cards show Approved, Cancelled, Closed. | 08-S04 | `sc_sb_test.dart` (tradeadmin) | Fail 2026-10-07: note: :: headers on screen: QA Agency / > / Selling t10069cwy / Home / Sell / Buy / Stock / Accounts / Masters / Reports / Search or jump to… / Ctrl+K / Sell... |
| SC-SB-002 | Positive | SM | A Dispatched note not yet billed | New. Customer (only those with notes to bill): Vijaya Stores. Press Choose notes, tick the note. Save. | Lines come from the note at the note's price and discount (not re-priced from the master). Draft bill saved. | SELL-011 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-SB-003 | Positive | SM | Draft bill | Press Approve. | Status Approved. Journal posted (Accounts > Journal Entries shows sales, tax and receivable). List total equals editor total. | SELL-011 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-SB-004 | Positive | SM | Draft bill | Press Save and approve in the editor. | Saved and approved in one step; same result as above. | SELL-011 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: saved 1, newest status APPROVED |
| SC-SB-005 | Positive | SM | Dispatched notes of one customer | Choose two notes on one bill. | Customer is chosen first; both notes appear on one bill; each note shows billed afterwards. | SELL-027 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: chips 2, saved 1, lines 2 |
| SC-SB-006 | Positive | CS | Counter-sale firm; Cash sale customer; shift open | New. Tick Counter sale. Scan or type a product code in the scan field. Take Received now: Cash. Save and print. | Customer is Cash sale. Scan message confirms the product. Tender balance reads 0 and change is shown. Bill is approved and printed. | SELL-029, SELL-040 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: counter bill: the fixture firm bills notes; no Counter sale tick or scan field in this firm's stages |
| SC-SB-007 | Positive | CS | Counter-sale firm | Counter bill with two tenders: Split, cash and UPI. | Tender lines sum to the bill; balance 0. | SELL-042 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: counter-sale case; the firm is not set to bill products directly and has no Cash sale customer or shift |
| SC-SB-008 | Positive | CS | Counter-sale firm | Fill Buyer (optional) name and phone on a walk-in bill. | Buyer name is kept on the walk-in bill only; a registered customer's bill does not offer it. | SELL-043 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: counter-sale case; the firm is not set to bill products directly and has no Cash sale customer or shift |
| SC-SB-009 | Positive | CS | Counter bill not finished | Hold it, open another, recall the first. | The held bill returns with lines intact; a held bill is never approved. | SELL-064, SELL-065 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: counter-sale case; the firm is not set to bill products directly and has no Cash sale customer or shift |
| SC-SB-010 | Positive | SM | Bill of goods and a service | Add a service line and a delivery charge. Save. | Service moves no stock; charge taxed at its own rate. | SELL-047, SELL-050 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: service line and delivery charge need a direct bill; notes carry only goods |
| SC-SB-011 | Positive | SM | Approved bill | Press Print, Send, Attachments. Attach a PDF. | Print opens with the UPI QR if set; Send offers channels; the PDF is listed. | SELL-012, SELL-034, SELL-060 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: Send opened=true; Attachments opened=true |
| SC-SB-012 | Positive | SM | Bill with a coupon | Type the coupon in Coupon, Save. | Offer applied once; the discount shows on the line. | SELL-006 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: coupon applies only on a direct bill of products |
| SC-SB-013 | Positive | SM | Approved bill | Press Close. | Status Closed. | SELL-011 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: status CLOSED, screen says "SI-26-27-000039 closed." |
| SC-SB-014 | Positive | SM | Draft bills | Tick several. Approve selected. | Per row result; one refusal does not stop the rest. | 08-S04 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: row tick boxes of the grid not reached in two attempts (same as SC-SO-013) |
| SC-SB-015 | Positive | CS | Open shift as cashier | Close the shift with cash counted equal, short, over. | Equal posts nothing; short and over post to Cash Short and Over; message states the difference. | SELL-067, SELL-069, SELL-070 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: counter-sale case; the firm is not set to bill products directly and has no Cash sale customer or shift |
| SC-SB-016 | Negative | SM | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | New bill, no customer. Save. | Checks N1 to N3 hold. Customer named as missing. | 08-S04 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Bill at least one line." |
| SC-SB-017 | Negative | SM | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | Bill with no lines. Save. | Checks N1 to N3 hold. A line is needed. | 08-S04 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Delivery notes to bill — Vijaya Stores t10069cwy / Delivery note / Date / Order / Left to bill (before tax) / DN-26-27-000080 / 07-... |
| SC-SB-018 | Negative | SM | Fixture firm; Vijaya Stores; Detergent (84, GST 18, 100 in stock) | Line quantity 0 or negative. Save. | Checks N1 to N3 hold. Quantity must be more than zero. A bill that comes to 0.00 is refused. | SELL-090 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Bill at least one line." |
| SC-SB-019 | Negative | SM | Note for 10, bill for 12 | Bill more than the note delivered. | Checks N1 to N3 hold. Message says no more than was dispatched can be billed. | SELL-011 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Bill at least one line. / Only 2.0 left to bill." |
| SC-SB-020 | Negative | SM | Note already billed | Look for the note under Choose notes. | A billed note is not offered. | SELL-011 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: billed note DN-26-27-000081 offered=false; unbilled DN-26-27-000078 offered=true |
| SC-SB-021 | Negative | SM | Order stage that requires a delivery note | Try to bill an order with no dispatched note. | Refused in words (dispatch before the invoice). | SELL-018 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: HTTP 422: {"success":false,"error":{"code":"validation_error","message":"This firm raises a sales order and a delivery note before it bills, so an invoice li... |
| SC-SB-022 | Negative | CS | Counter bill, nothing tendered | Approve a walk-in bill not paid in full. | Refused at approval. Bill stays Draft with everything typed. | SELL-041 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: counter-sale case; the firm is not set to bill products directly and has no Cash sale customer or shift |
| SC-SB-023 | Negative | CS | Walk-in customer | Try to give the Cash sale customer a credit limit or make it inactive (Masters > Customers). | Refused in words. | SELL-044 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: no Cash sale customer in the fixture firm |
| SC-SB-024 | Negative | SM | Invoice date in the future | Set Invoice date after today. Save. | Checks N1 to N3 hold. 'Cannot be future-dated' style message; exact wording on first run. | 08-S04 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: Invoice date is read-only (set to today by the screen); no input to type a future date into |
| SC-SB-025 | Negative | SM | Invoice date in a closed period | Set a date inside a closed financial year or period. Approve. | Refused in words naming the period. Bill stays Draft. | 08-S04 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: no closed financial period in the fixture firm |
| SC-SB-026 | Negative | SM | Approved bill | Try Edit. | Edit not offered, or 'Only draft sales invoices can be updated.' | SELL-011 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: Edit is absent on an Approved bill |
| SC-SB-027 | Negative | SM | Approved bill | Press Approve again from a stale list. | 'Only draft sales invoices can be approved.' No second journal. | SELL-011 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, screen says "Only draft sales invoices can be approved." |
| SC-SB-028 | Negative | SM | Approved bill with a receipt resting on it | Press Cancel. | Refused in words naming the receipt, or the receipt must be reversed first. Wording on first run. | SELL-014 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, screen says "SI-26-27-000044 cannot be cancelled while it has money applied from RC-2026-2027-000010. Reverse or cancel those first." |
| SC-SB-029 | Negative | SM | Approved bill with a return resting on it | Press Cancel. | Refused in words naming the return. | SELL-015 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, screen says "SI-26-27-000045 cannot be cancelled while it has sales return SR-26-27-000010. Reverse or cancel those first." |
| SC-SB-030 | Negative | SM | Line rate under the price floor, Price Floor setting on | Save and approve. | Refused or sent for approval per the firm's setting; the message names the product and the floor. | SELL-022 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: Price Floor setting is off and a bill of notes carries the notes' prices; no rate can be typed |
| SC-SB-031 | Negative | SM | Customer past credit limit, firm blocks | Approve a bill. | With blocking on: refused in words, stays Draft. With the default policy: a warning only and approval goes through. | 08-S04 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: no customer with a credit limit in the fixture firm (see SC-SO-022) |
| SC-SB-032 | Negative | SM | Typed editor | Close the editor. | 'Discard unsaved changes?'; Keep editing keeps all. | 08-S04 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: editor closed=false, asked=true |
| SC-SB-033 | Role | CS | Counter Sales (Billing Executive role) | Open Sell > Sales Invoices. | List opens, New offered (SALES_INVOICE_CREATE). Approve, Cancel, Close are not offered (no SALES_APPROVE or SALES_CANCEL). | 01-ROLES R03 | not yet |  |
| SC-SB-034 | Role | FS | Field Sales | Raise a bill and try to approve it. | Approve is absent or refused with the permission message. | 01-ROLES R04 | `sc_sb_test.dart` (qsexe) | Pass 2026-10-07: offered; buttons {+ New: enabled, New Invoice: absent, Approve: absent, Cancel: absent, Close: absent} |
| SC-SB-035 | Role | CS | Cashier role only | Look in the Sell menu. | No Sales Invoices (no SALES_VIEW); Receipts is offered. | 01-ROLES R03 | not yet |  |
| SC-SB-036 | Role | SM | Sales Manager | Open the bill. Look for a price override on a line. | No override of the floor (no SALES_PRICE_OVERRIDE); a below-floor rate is refused or goes for approval. | SELL-022 | `sc_sb_test.dart` (qsmgr) | Pass 2026-10-07: buttons {Approve: enabled, Edit: enabled, Cancel: enabled} (the bill's rate cell is read-only text; override tested at HTTP level elsewhere) |
| SC-SB-037 | Role | RO | Read Only | Open Sales Invoices. | Rows readable; no write buttons. | 01-ROLES R11 | `sc_sb_test.dart` (qro) | Pass 2026-10-07: buttons {New Invoice: absent, + New: absent, Edit: absent, Approve: absent, Cancel: absent, Close: absent} |
| SC-SB-038 | Multi-user | FS, SM, WH, CS, AC | FS orders; SM approves; WH dispatches; CS bills; AC sees the bill | Each user opens the list after the one before. | Each sees the previous user's document with the same number and status; AC can read the posted journal. | SELL-007 to SELL-011 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: qacct reads the journals 200 (the bill itself is not in the Accounts role) |
| SC-SB-039 | Multi-user | SM and FA | Same Draft bill open twice | A saves a changed payment term; B saves from the old copy. | B is told 'This record changed since you loaded it. Reload and try again.' B's typing stays. | 08-S04 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: note: :: the refusal does not say the record changed or to reload: Somebody else saved this invoice while you were editing it. Your changes are still here an... |
| SC-SB-040 | Multi-user | CS and CS2 | Two cashiers | Both press Approve on the same held counter bill. | One succeeds; the other sees the status moved and nothing is posted twice. | SELL-065 | `sc_sb_test.dart` (tradeadmin) | Skipped 2026-10-07: counter-sale case; the firm is not set to bill products directly and has no Cash sale customer or shift |
| SC-SB-041 | Multi-user | SM | Two sessions with the list open | A approves a bill; B refreshes. | B shows Approved and the updated card counts. | 08-S04 | `sc_sb_test.dart` (tradeadmin) | Pass 2026-10-07: row reads: SI-26-27-000043 / Vijaya Stores t10069cwy / 2026-10-07 03:35 / Approved / 188.80 |

## PF. Proforma

**Where and who.** Sell > All Sell screens > Documents > Proforma. Offered to FA, FM, SM (PROFORMA_VIEW and PROFORMA_MANAGE), RO.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-PF-001 | Positive | SM | An Approved sales order | Open Proforma. Press New. Choose the sales order. Type Payment terms, Delivery terms, Valid until. Raise. | A proforma is raised with its own number series (not the tax invoice's). It posts nothing: Accounts > Journal Entries shows no new entry. | SELL-017 | not yet |  |
| SC-PF-002 | Positive | SM | A proforma | Look at the grid. | Columns Number, Customer, Date, Valid Until, Sales Order, Status, Taxable Value, Tax, Grand Total. | SELL-017 | not yet |  |
| SC-PF-003 | Positive | SM | A proforma in Draft | Press Issue. | Status Issued; still no journal and no receivable. | SELL-017 | not yet |  |
| SC-PF-004 | Positive | SM | An Issued proforma | Press Withdraw, confirm. | Status Withdrawn; the order is untouched. | SELL-017 | not yet |  |
| SC-PF-005 | Positive | SM | A proforma, then the order is changed | Edit the order quantity then reopen the proforma. | The proforma keeps its own figures; it does not follow the order afterwards. | SELL-017 | not yet |  |
| SC-PF-006 | Positive | SM | Issued proforma | Print or Send. | Preview shows 'Proforma', not 'Tax invoice'. | SELL-017 | not yet |  |
| SC-PF-007 | Positive | SM | Several proformas | Search by customer; refresh. | Grid narrows; counters agree. | SELL-017 | not yet |  |
| SC-PF-008 | Negative | SM | Order Draft (not approved) | New proforma and look for that order. | A Draft order is not offered, or the raise is refused in words. | SELL-017 | not yet |  |
| SC-PF-009 | Negative | SM | Order cancelled | Try to raise a proforma from it. | Refused in words. | SELL-017 | not yet |  |
| SC-PF-010 | Negative | SM | Raise dialog | Press Raise with no order chosen. | Dialog stays open, names the order as missing; nothing saved. | SELL-017 | not yet |  |
| SC-PF-011 | Negative | SM | Valid until before today | Raise with a past Valid until. | Refused in words or flagged; wording to be established on the first run. | SELL-017 | not yet |  |
| SC-PF-012 | Negative | SM | Withdrawn proforma | Try Issue. | Not offered or refused: only the right status can be issued. | SELL-017 | not yet |  |
| SC-PF-013 | Negative | SM | A proforma | Look for any receipt or journal link on it. | None exists; by design a proforma cannot be paid or posted. | SELL-017 | not yet |  |
| SC-PF-014 | Role | SM | Sales Manager | Open Proforma. | Offered; New, Issue, Withdraw offered (PROFORMA_MANAGE). | 01-ROLES R05 | not yet |  |
| SC-PF-015 | Role | FS | Field Sales | Look in the All Sell screens list. | Proforma not offered (no PROFORMA_VIEW). | 01-ROLES R04 | not yet |  |
| SC-PF-016 | Role | RO | Read Only | Open Proforma. | Readable; no New, Issue, Withdraw. | 01-ROLES R11 | not yet |  |
| SC-PF-017 | Multi-user | FS, SM | FS's order approved by SM | SM raises a proforma and issues it; FS asks for it. | FS cannot raise it but the customer-facing print is shared by SM; the order list still shows the order unchanged. | SELL-017 | not yet |  |
| SC-PF-018 | Multi-user | SM and FA | Same Draft proforma open twice | FA issues it; SM presses Withdraw from the old copy. | SM is told the status moved; nothing is lost. | SELL-017 | not yet |  |

## RC. Receipts

**Where and who.** Sell > Receipts (daily Money list). Offered to FA, FM, CS (Cashier role), AC (RECEIPT_CREATE and RECEIPT_VIEW), RO. Related: Collection Sheet, Payment Promises, Post-dated Cheques, Refunds under Sell > All Sell screens > Money.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-RC-001 | Positive | CS | Approved bill for Vijaya Stores, 1,000 outstanding | Open Sell > Receipts. | Grid shows receipts with Cash or Bank, On Account, Other Deductions; chips switch Customer credits and Supplier views. Search by number or reference works. | 08 Screen checks | `sc_rc_test.dart` (tradeadmin) | Fail 2026-10-07: note: :: short texts: QA Agency / > / Selling t10069cwy / Home / Sell / Buy / Stock / Accounts / Masters / Reports / Search or jump to… / Ctrl+K / 1 / Sellin... |
| SC-RC-002 | Positive | CS | Approved bill outstanding | New. Pick Vijaya Stores. Press Oldest first. Press Record. | The bill's outstanding falls by the amount; receipt number appears in the list; a journal is posted (Dr bank or cash, Cr receivable). | SELL-013 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-RC-003 | Positive | CS | Two bills outstanding | Type an amount that clears the first bill and part of the second. | Allocation grid shows the split; each bill's outstanding is right. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: saved 1, 6 allocations summing 900.0, unallocated 0.00 |
| SC-RC-004 | Positive | CS | Bill 300 outstanding | Record 500 (more than owed) with nothing else outstanding. | Bill is cleared; the excess shows under On Account and becomes a customer credit. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: advance notice shown=true, saved 1, newest unallocated 137.00 |
| SC-RC-005 | Positive | CS | Receipt with Mode cheque | Choose Mode cheque; fill instrument date; Record. | Instrument date is kept; Print cheque is not offered for a receipt. | 08 Screen checks | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: instrument date box shown=true, saved 1, mode CHEQUE, instrument date null |
| SC-RC-006 | Positive | AC | Customer with TDS deducted | Fill TDS deducted and TDS section. Record. | TDS posts to its receivable account; the bill is cleared by cash plus TDS. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Skipped 2026-10-07: TDS section list not driven; the section dropdown holds no entries without a TDS master in the fixture |
| SC-RC-007 | Positive | AC | Early-payment discount offered on the bill | Pick the bill; look for the cash discount offer. | An offer line shows with an Apply button; applying it fills the discount amount. | SELL-031 | `sc_rc_test.dart` (tradeadmin) | Skipped 2026-10-07: no early-payment discount offered on any bill |
| SC-RC-008 | Positive | CS | A recorded receipt | Press Print, Send, Files. | Print preview opens; Send names channels; Files lists attachments. | 08 Screen checks | `sc_rc_test.dart` (tradeadmin) | Fail 2026-10-07: Bad state: Send absent; Files opened=true |
| SC-RC-009 | Positive | AC | A recorded receipt | Select it, press Reverse, type the reason, press Reverse. | Receipt shows Reversed; the bill's outstanding is back; the deltas come off the original row. | SELL-014 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: receipt REVERSED; bill outstanding null of 188.8000; screen says "RC-2026-2027-000050 reversed." |
| SC-RC-010 | Positive | AC | A promise to pay recorded | Record a receipt for that customer. | The promise moves to kept. | SELL-075 | `sc_rc_test.dart` (tradeadmin) | Skipped 2026-10-07: no payment promise recorded in the fixture firm |
| SC-RC-011 | Positive | CS | Collection Sheet | Open Sell > All Sell screens > Money > Collection Sheet. | Rows by collector with what is due; a receipt can be started from a row. | SELL-073 | `sc_rc_test.dart` (tradeadmin) | Skipped 2026-10-07: Collection Sheet is under All Sell screens; not reached |
| SC-RC-012 | Negative | CS | Receipt dialog | Press Record with amount 0 or empty. | Dialog stays open; 'must be for more than nothing' style message; nothing saved. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Record a receipt / Money already received. Recording it posts to the ledger. / Enter how much money moved. / Dismiss / Received fro... |
| SC-RC-013 | Negative | CS | Receipt dialog | Type a negative amount. | Refused in words; typed values kept. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Record a receipt / Money already received. Recording it posts to the ledger. / Enter how much money moved. / Dismiss / Received fro... |
| SC-RC-014 | Negative | CS | Receipt dialog | Set 'Date the money moved' to a future date. | Refused in words (not future-dated). | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Fail 2026-10-07: note: :: date picker open=true; note: :: date now reads 2026-11-15, 2026-10-07, 2026-10-07, 2026-10-07, 2026-10-07, 2026-10-07, 2026-10-07, 2026-10-07, 2026-... |
| SC-RC-015 | Negative | CS | Receipt dialog | Set the date inside a closed financial year or period. | Refused in words naming the period. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Skipped 2026-10-07: no closed financial period in the fixture firm |
| SC-RC-016 | Negative | CS | Receipt dialog | Leave Mode or the bank/cash account empty. Record. | Refused; the field is named. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Skipped 2026-10-07: Mode and account default to Cash; the dialog has no empty state for them |
| SC-RC-017 | Negative | CS | Receipt dialog, no customer chosen | Press Record. | Customer named as missing. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: note: :: newest receipt after press: null customer null amount 10.00 created null; open=true, saved=0, said="Record a receipt / Money already received. Recor... |
| SC-RC-018 | Negative | AC | TDS typed without a section | Record. | Refused or section required; wording on first run. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Record a receipt / Money already received. Recording it posts to the ledger. / Choose the TDS section the deduction is filed under.... |
| SC-RC-019 | Negative | AC | A receipt already applied to a bill that has a return resting on it | Try Reverse. | Reverse works or is refused in words; the books must agree either way. To be established. | SELL-014 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: receipt REVERSED; bill outstanding null of 377.6000; screen says "RC-2026-2027-000052 reversed." |
| SC-RC-020 | Negative | AC | A Reversed receipt | Press Reverse again. | Not offered or refused: already reversed. | SELL-014 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: Reverse is absent on a reversed receipt |
| SC-RC-021 | Negative | CS | Receipt dialog typed | Close it. | Asks to discard unsaved changes. | 08 Screen checks | `sc_rc_test.dart` (tradeadmin) | Fail 2026-10-07: Bad state: the dialog closed holding typing without asking (same family as known SCRQ-21/29) |
| SC-RC-022 | Negative | CS | Receipt can only be edited by reversal | Look for Edit and Delete on a recorded receipt. | Neither is offered; a settlement is reversed, never edited or deleted. | SELL-014 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: Edit absent, Delete absent |
| SC-RC-023 | Role | CS | Cashier role | Open Sell > Receipts. | List and Record offered (RECEIPT_CREATE and RECEIPT_VIEW); Reverse offered if the role holds the code, else refused. | 01-ROLES R03 | not yet |  |
| SC-RC-024 | Role | FS | Field Sales | Look for Receipts. | Not offered (no RECEIPT_VIEW). | 01-ROLES R04 | `sc_rc_test.dart` (qsexe) | Pass 2026-10-07: Receipts offered: false; list answers 403 |
| SC-RC-025 | Role | SM | Sales Manager | Look for Receipts. | Not offered (Sales Manager holds no receipt code). | 01-ROLES R05 | `sc_rc_test.dart` (qsmgr) | Pass 2026-10-07: Receipts offered: false; list answers 403 |
| SC-RC-026 | Role | RO | Read Only | Open Receipts. | Rows readable; Record and Reverse absent. | 01-ROLES R11 | `sc_rc_test.dart` (qro) | Pass 2026-10-07: Receipts offered: true; list answers 200; {+ New: absent, Reverse: absent} |
| SC-RC-027 | Role | AC | Accounts | Open Receipts and Refunds. | Both offered; Refunds needs ACCOUNT_VIEW. | 01-ROLES R09 | `sc_rc_test.dart` (qacct) | Pass 2026-10-07: Receipts offered: true; list answers 200; New enabled, Reverse enabled |
| SC-RC-028 | Multi-user | SM, CS, AC | SM approves a bill; CS records a receipt; AC opens Customer Statements | Each opens its screen after the other. | CS sees the bill with its outstanding; AC sees the statement balance equal to the bills less receipts. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Skipped 2026-10-07: needs the cashier user and the statement screen |
| SC-RC-029 | Multi-user | CS and AC | Same receipt open on two sessions | AC reverses; CS presses Reverse from the old list. | CS is told it is already reversed or the list moved; no double reversal. | SELL-014 | `sc_rc_test.dart` (tradeadmin) | Fail 2026-10-07: Bad state: N1: the stale Reverse said nothing |
| SC-RC-030 | Multi-user | CS and CS2 | Two cashiers | Both record a receipt against the same bill for the full outstanding. | The second is told only the remainder is owed or the excess becomes On Account; the bill is never negative. | SELL-013 | `sc_rc_test.dart` (tradeadmin) | Pass 2026-10-07: second receipt answered 422: {"success":false,"error":{"code":"validation_error","message":"An allocated invoice does not belong to this party, is not approv... |

## CC. Customer credits (advances and credit set against a bill)

**Where and who.** Sell > Receipts, chip Customer credits. Offered with Receipts: FA, FM, CS (Cashier role), AC, RO.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-CC-001 | Positive | AC | An On Account receipt of 200 for Vijaya | Open Receipts, press the Customer credits chip. | The credit is listed with its amount and the customer; credits applied show Applied, the rest On account. | SELL-013 | not yet |  |
| SC-CC-002 | Positive | AC | Credit 200 and an approved bill of 500 | Select the credit, press Apply. Pick the customer, the credit, the bill, confirm the amount. | Bill outstanding falls by the amount; the credit shows Applied (or the rest On account). No journal is posted by applying. | SELL-014, INCENT-018 | not yet |  |
| SC-CC-003 | Positive | AC | Credit 200 | Apply only 50 of it. | Only 50 moves; 150 stays on account. | INCENT-018 | not yet |  |
| SC-CC-004 | Positive | AC | A credit applied | Press Reverse on the application (or the receipt). | The bill's outstanding and the credit go back to what they were. | SELL-014 | not yet |  |
| SC-CC-005 | Positive | AC | Customer Statements | Open Sell > Customer Statements for the customer. | Credits show as minus rows; the running balance is in date order. | SELL-037 | not yet |  |
| SC-CC-006 | Negative | AC | Credit 200 | Apply 300. | Refused in words; the amount cannot be more than the credit. Dialog open, values kept. | INCENT-018 | not yet |  |
| SC-CC-007 | Negative | AC | Bill of 100 | Apply 150 to it. | Refused: more than the bill owes. | INCENT-018 | not yet |  |
| SC-CC-008 | Negative | AC | Credit dialog | Apply on a date in the future. | 'A credit cannot be applied on a future date.' | INCENT-018 | not yet |  |
| SC-CC-009 | Negative | AC | Credit already taken off the bill | Apply it again. | 'This credit has already been taken off the bill.' | INCENT-018 | not yet |  |
| SC-CC-010 | Negative | AC | Credit dialog | Apply an amount of 0. | 'An application must be for more than nothing.' | INCENT-018 | not yet |  |
| SC-CC-011 | Negative | AC | Customer with no open bill | Press Apply. | Dialog says there is no open bill; nothing saved. | INCENT-018 | not yet |  |
| SC-CC-012 | Role | AC | Accounts | Open Customer credits. | Offered, Apply offered (RECEIPT_CREATE). | 01-ROLES R09 | not yet |  |
| SC-CC-013 | Role | SM | Sales Manager | Look for the screen. | Not offered. | 01-ROLES R05 | not yet |  |
| SC-CC-014 | Role | RO | Read Only | Open Customer credits. | Readable; Apply absent. | 01-ROLES R11 | not yet |  |
| SC-CC-015 | Multi-user | CS, AC | CS records an excess receipt | AC opens Customer credits and applies it. | AC sees the credit CS created; afterwards CS's list shows the bill reduced. | SELL-013 | not yet |  |
| SC-CC-016 | Multi-user | AC and AC2 | Same credit open twice | Both apply the full credit to different bills. | The second is refused: credit already used (or only the remainder applies). | INCENT-018 | not yet |  |

## SR. Sales returns

**Where and who.** Sell > Returns & notes > Sales Returns (short list). Offered to FA, FM, SM; RO reads. FS and CS do not hold SALES_RETURN.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-SR-001 | Positive | SM | A Dispatched note or an Approved bill with 10 units | Open Sales Returns. | Grid shows Return Number, Customer, Return Date, Status; cards per status. | 08-S05 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: note: :: short texts: QA Agency / > / Selling t10069cwy / Home / Sell / Buy / Stock / Accounts / Masters / Reports / Search or jump to… / Ctrl+K / 1 / Sellin... |
| SC-SR-002 | Positive | SM | Approved bill, Detergent 10 | New. Under 'Returned against (delivery note or invoice)' pick the bill. Set the returning quantity to 1. 'Taken back into' a warehouse. Save. | Draft return saved with the line; Tax column shows the tax the line was charged. | SELL-015 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-SR-003 | Positive | SM | Draft return | Press Approve. | Status Approved. Stock back into the chosen warehouse only on Complete (check Stock Summary at each step). | SELL-015 | `selling_flow_test.dart` | Pass 2026-10-07 |
| SC-SR-004 | Positive | SM | Approved return | Press Complete. | Status Completed; stock returns; the journal reverses revenue and tax. | SELL-015 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: status COMPLETED, screen says "SR-26-27-000040 completed: 1.0000 back on the shelf and 94.4000 credited to the customer." |
| SC-SR-005 | Positive | SM | Completed return | Press Close. | Status Closed. | SELL-015 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: status CLOSED, screen says "SR-26-27-000040 closed." |
| SC-SR-006 | Positive | SM | Draft or Approved return | Press Cancel, type a reason, confirm. | Status Cancelled; reason shown on the row. | SELL-015 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: status CANCELLED, screen says "SR-26-27-000037 cancelled. The stock, the customer’s balance and both journals have been put back." |
| SC-SR-007 | Positive | SM | Return of a service line | Return a service. | Credits the customer and puts nothing on a shelf. | SELL-049 | `sc_sr_test.dart` (tradeadmin) | Skipped 2026-10-07: no service line on any bill in the fixture firm |
| SC-SR-008 | Positive | SM | Several drafts | Tick rows, Approve selected. | Per row results. | 08-S05 | `sc_sr_test.dart` (tradeadmin) | Skipped 2026-10-07: row tick boxes of the grid not reached in two attempts (same as SC-SO-013) |
| SC-SR-009 | Negative | SM | Bill of 10, 2 already returned | Enter returning 9. | Checks N1 to N3 hold. Message says no more than was dispatched (less already returned) can come back. | SELL-015 | `sc_sr_test.dart` (tradeadmin) | Fail 2026-10-07: Bad state: N2: the editor closed [open=false, saved=0, said="Return quantity exceeds what left on DN-26-27-000136 (9 sent, 7 already returned against it or t... |
| SC-SR-010 | Negative | SM | Return editor | Returning 0 on every line. Save. | Checks N1 to N3 hold. At least one line with a quantity. | SELL-090 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Enter how many came back on at least one line." |
| SC-SR-011 | Negative | SM | Return editor | Returning -1. | Checks N1 to N3 hold. Quantity must be more than zero. | SELL-090 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Enter how many came back on at least one line." |
| SC-SR-012 | Negative | SM | Return editor | Save with 'Returned against' empty. | Checks N1 to N3 hold. The source document is named as missing. | 08-S05 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Enter how many came back on at least one line." |
| SC-SR-013 | Negative | SM | Return editor | Return date in the future. | Checks N1 to N3 hold. Message about the date. | 08-S05 | `sc_sr_test.dart` (tradeadmin) | Skipped 2026-10-07: Return date is read-only (set to today); no input to type a future date into |
| SC-SR-014 | Negative | SM | Return of goods never billed | Return goods never billed. | Credits nothing; the reports say so. | SELL-094 | `sc_sr_test.dart` (tradeadmin) | Skipped 2026-10-07: a return off a never-billed note: the credit is a report matter; not driven |
| SC-SR-015 | Negative | SM | Approved return | Try Edit. | 'Only draft sales returns can be edited.' | SELL-015 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: Edit is absent on an Approved return; Approve absent, Complete enabled |
| SC-SR-016 | Negative | SM | Draft return | Press Complete. | 'Only approved sales returns can be completed.' | SELL-015 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: Complete is absent on a Draft return |
| SC-SR-017 | Negative | SM | Closed return | Press Cancel. | 'Closed sales returns cannot be cancelled.' | SELL-015 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: Cancel is absent on a Closed return |
| SC-SR-018 | Negative | SM | Return with a credit note raised on it | Press Cancel. | Refused in words naming the credit note. Wording on first run. | SELL-016 | `sc_sr_test.dart` (tradeadmin) | Skipped 2026-10-07: no credit note raised on a return in the fixture |
| SC-SR-019 | Negative | SM | Editor typed | Close the editor. | Discard question; Keep editing keeps typing. | 08-S05 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: editor closed=false, asked=true |
| SC-SR-020 | Role | SM | Sales Manager | Open Sales Returns. | Offered, with New, Approve, Complete, Close, Cancel (SALES_RETURN, SALES_APPROVE, SALES_CANCEL). | 01-ROLES R05 | `sc_sr_test.dart` (qsmgr) | Pass 2026-10-07: offered; {+ New: enabled, New Return: absent, Approve: enabled, Cancel: enabled} |
| SC-SR-021 | Role | FS | Field Sales | Look in the short list. | Not offered, or readable only; no New. | 01-ROLES R04 | `sc_sr_test.dart` (qsexe) | Fail 2026-10-07: not offered, or readable with no New: Bad state: menu (false) and server (200) disagree |
| SC-SR-022 | Role | RO | Read Only | Open Sales Returns. | Rows readable; no write buttons. | 01-ROLES R11 | `sc_sr_test.dart` (qro) | Pass 2026-10-07: buttons {New Return: absent, + New: absent, Approve: absent, Cancel: absent} |
| SC-SR-023 | Multi-user | SM, WH, AC | SM raises and approves; WH completes (stock back); AC reads the credit | Each opens after the last. | Each sees the status the last user left; AC's statement shows the credit in minus. | SELL-015 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: note: :: the storekeeper is refused Complete (403); the return is completed by the Sales Manager instead; qstore Complete answered 403; qacct journals 200 |
| SC-SR-024 | Multi-user | SM and SM2 | Same return open twice | A approves; B approves from the old copy. | B is refused: only a draft can be approved. | SELL-015 | `sc_sr_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, screen says "SR-26-27-000038 approved. Nothing has moved yet — completing it takes the goods back." |
| SC-SR-025 | Multi-user | SM and FA | Same Draft return open twice | A changes quantity and saves; B saves from the old copy. | B told 'This record changed since you loaded it.'; typing kept. | 08-S05 | `sc_sr_test.dart` (tradeadmin) | Skipped 2026-10-07: a Draft return has no Edit on screen, so there is no second session to race |

## CN. Credit notes (and customer debit notes)

**Where and who.** Sell > Returns & notes > Credit Notes and Debit Notes. Offered to FA, FM, SM (draft only), AC, RO. Approve needs CREDIT_NOTE_APPROVE or CUSTOMER_DEBIT_NOTE_APPROVE, which Sales Manager does not hold.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-CN-001 | Positive | SM | An Approved bill of 1,000 taxable | Open Credit Notes. | Grid: Number, Customer, Invoice, Date, Reason, Status, Taxable Value, Tax, Credited, E-invoice. | SELL-016 | not yet |  |
| SC-CN-002 | Positive | SM | Approved bill | Press Raise credit note. Pick Invoice, Line, Credit before tax 100, Reason, Remarks. Save. | Draft credit note saved. Tax shown is the tax the line was charged on 100. | SELL-016 | not yet |  |
| SC-CN-003 | Positive | AC | Draft credit note | Press Approve. | Status Approved; journal reverses the sale and the tax; the bill's outstanding falls. | SELL-016 | not yet |  |
| SC-CN-004 | Positive | AC | Several drafts | Tick rows, Approve selected. | Per row results. | SELL-016 | not yet |  |
| SC-CN-005 | Positive | AC | Approved note | Press Print. Press E-invoice if the firm is set up. | Print opens; E-invoice dialog opens or says the firm is not set up. Sandbox reference marked as sandbox. | SELL-016 | not yet |  |
| SC-CN-006 | Positive | SM | Approved bill | Raise a customer Debit Note (Charge, before tax 50). | Draft saved; approved by AC it adds declared tax and a receivable. | SELL-020 | not yet |  |
| SC-CN-007 | Positive | AC | Credit and debit notes | Open Sell > Customer Statements. | Credit note shows minus, debit note plus. | SELL-037 | not yet |  |
| SC-CN-008 | Positive | AC | Approved credit note | Press Cancel. | Status Cancelled; the journal is reversed. | SELL-016 | not yet |  |
| SC-CN-009 | Negative | SM | Raise dialog | Press Raise with Invoice empty. | Dialog stays open; Invoice named as missing. | SELL-016 | not yet |  |
| SC-CN-010 | Negative | SM | Raise dialog | Credit 0 or negative. | Refused in words. | SELL-016 | not yet |  |
| SC-CN-011 | Negative | SM | Bill line of 1,000 | Credit 1,200 on that line. | Refused: no more than the line (less credits already raised). | SELL-016 | not yet |  |
| SC-CN-012 | Negative | SM | Two credit notes of 600 on a 1,000 line | Raise the second. | Refused: the total passes the line. | SELL-016 | not yet |  |
| SC-CN-013 | Negative | SM | Draft bill | Look for it in the Invoice box. | Only approved bills are offered. | SELL-016 | not yet |  |
| SC-CN-014 | Negative | SM | Raise dialog | Leave Reason empty. | Reason named as missing, or accepted as Other; wording on first run. | SELL-016 | not yet |  |
| SC-CN-015 | Negative | AC | Approved note | Press Approve again. | Not offered or refused: already approved. | SELL-016 | not yet |  |
| SC-CN-016 | Negative | AC | Credit note on a bill in a closed period | Approve. | Refused in words naming the period. | SELL-016 | not yet |  |
| SC-CN-017 | Negative | SM | Dialog typed | Close it. | Asks to discard. | SELL-016 | not yet |  |
| SC-CN-018 | Role | SM | Sales Manager | Open Credit Notes. | New (Raise) offered; Approve absent or refused (no CREDIT_NOTE_APPROVE). | 01-ROLES R05 | not yet |  |
| SC-CN-019 | Role | AC | Accounts | Open Credit Notes. | Approve offered if the role holds CREDIT_NOTE_APPROVE, else absent; result matched to the role matrix. | 01-ROLES R09 | not yet |  |
| SC-CN-020 | Role | FS | Field Sales | Look for Credit Notes. | Not offered (no CREDIT_NOTE_VIEW). | 01-ROLES R04 | not yet |  |
| SC-CN-021 | Role | RO | Read Only | Open Credit Notes. | Readable; no write buttons. | 01-ROLES R11 | not yet |  |
| SC-CN-022 | Multi-user | SM, FA | SM drafts a credit note; FA approves | FA opens the list. | FA sees SM's Draft with its figures; after approval SM sees Approved. | SELL-016 | not yet |  |
| SC-CN-023 | Multi-user | FA and FA2 | Same Draft note open twice | Both approve. | Only one journal is posted; the second is told it is already approved. | SELL-016 | not yet |  |

# Part 2. Buying


## PO. Purchase orders

**Where and who.** Buy > Purchase Orders (daily list). Offered to FA, FM, PM, PU, RO. Approve needs PURCHASE_APPROVE (not PU).

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-PO-001 | Positive | PU | Fixture firm; supplier Principal supplier; Detergent | Open Buy > Purchase Orders. | Grid with PO number, supplier, date, status, value; cards Draft Orders, Open Orders, Orders Today, Pending Delivery, Cancelled, Closed, Purchase Value. Search placeholder reads 'Search PO number, supplier, remarks or reference'. | 06-S04 | `sc_po_test.dart` (tradeadmin) | Fail 2026-10-07: note: :: short texts: QA Agency / > / Selling t10069cwy / Home / Sell / Buy / Stock / Accounts / Masters / Reports / Search or jump to… / Ctrl+K / 1 / Sellin... |
| SC-PO-002 | Positive | PU | Fixture firm; supplier Principal supplier; Detergent | New. Vendor: Principal supplier. Add Detergent, quantity 10. Save. | Draft order saved with a PO number; list shows number and total. | BUY-001 | `buying_flow_test.dart` | Pass 2026-10-07 |
| SC-PO-003 | Positive | PU | Saved Draft order | Select, press Edit, change quantity 10 to 12. Save. | List shows the new total; the quantity is 12. | BUY-001 | `buying_flow_test.dart` | Pass 2026-10-07 |
| SC-PO-004 | Positive | PU | Draft order | Press Submit. | Status moves to the submitted state waiting approval. | BUY-001 | `buying_flow_test.dart` | Pass 2026-10-07 |
| SC-PO-005 | Positive | PM | Submitted order | Press Approve. | Status Approved. Approval cannot be skipped: a Draft is not receivable. | BUY-001 | `buying_flow_test.dart` | Pass 2026-10-07 |
| SC-PO-006 | Positive | PU | Rate contract exists for the product | New order, add the product. | The line takes the contract rate; the contract notice shows. Over-drawing warns and never refuses. | BUY-060, BUY-061 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: no rate contract in the fixture firm |
| SC-PO-007 | Positive | PU | Supplier scheme 10+2 on the product | Add a line of 10. | Free quantity 2 is filled; a typed free quantity is kept; 0 refuses the scheme. | BUY-066, BUY-067 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: no supplier scheme in the fixture firm |
| SC-PO-008 | Positive | PU | Foreign supplier | Choose a Currency and Exchange rate. | Rupee equivalents are shown; document in the supplier's currency. | BUY-070 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: no foreign currency supplier |
| SC-PO-009 | Positive | PM | Approved order | Press Amend. | Order returns to editable; the approval is withdrawn and a notice says so ('Editing withdraws the approval'). | BUY-002, BUY-020 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, amend editor open=true, screen says "" |
| SC-PO-010 | Positive | PU | Approved order | Press Mark as sent. Press Print. Press Send. | Marked sent with the date. Print opens preview; Send offers WhatsApp and says the firm must be set up first if not. | BUY-054, BUY-055 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: asked ""; sent_at 2026-10-07T15:19:32.725787+05:30, status APPROVED, screen says "PO-T10069CWY-S-HO-2026-2027-000127 marked as sent." |
| SC-PO-011 | Positive | PU | Any order | Press Duplicate. | A new Draft with the same lines opens. | BUY-001 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: editor open=true, records 0 more |
| SC-PO-012 | Positive | PM | Approved, part-received order | Press Close. | Order Closed; confirm dialog 'Close purchase order'. | BUY-003 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: status CLOSED, screen says "Close purchase order... / Purchase order closed. // Purchase order closed." |
| SC-PO-013 | Positive | PM | Draft or Approved order, nothing received | Press Cancel, confirm. | Order Cancelled. | BUY-001 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: Cancel: status CANCELLED, says "Cancel purchase order... / Purchase order cancelled. // Purchase order cancelled."; Restore on the Cancelled row is absent (i... |
| SC-PO-014 | Positive | PM | A cancelled order | Press Restore. | Order returns. | BUY-001 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: Restore brings back a deleted order, not a Cancelled one; there is no way back from Cancelled on screen |
| SC-PO-015 | Positive | PM | Draft orders | Tick rows, Approve selected, then Cancel selected. | Per row results. | 06-S04 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: grid tick boxes not reached (same as SC-SO-013) |
| SC-PO-016 | Positive | PU | Stock below reorder level | Press 'Below reorder level...'. | A dialog proposes orders from the preferred supplier. | BUY-015, BUY-018 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: dialog open=true: Below reorder level / Suggested is up to the maximum level, less what is available and what is already on order; without a maximum, the sho... |
| SC-PO-017 | Positive | PU | Saved views | Save current search, apply it later; Columns changes the grid. | Saved view returns the same filter and layout. | 06-S04 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: saved searches not driven |
| SC-PO-018 | Negative | PU | Fixture firm; supplier Principal supplier; Detergent | New order, no vendor. Save. | Checks N1 to N3 hold. Vendor named as missing. | 06-S04 | `sc_po_test.dart` (tradeadmin) | Fail 2026-10-07: note: :: newest order: PO-T10069CWY-S-HO-2026-2027-000133 vendor 4a737e55-f062-4871-b02a-089c7797c3a5 lines 1 status DRAFT; Save is refused: Bad state: N2: t... |
| SC-PO-019 | Negative | PU | Fixture firm; supplier Principal supplier; Detergent | No lines. Save. | Checks N1 to N3 hold. A line is needed. | 06-S04 | `sc_po_test.dart` (tradeadmin) | Fail 2026-10-07: Save is refused: Bad state: N2: the editor closed; N3: 1 record(s) saved [open=false, saved=1, said="Purchase order created. / 1 selected"] |
| SC-PO-020 | Negative | PU | Fixture firm; supplier Principal supplier; Detergent | Quantity 0, then -4. Save. | Checks N1 to N3 hold. Quantity must be more than zero. | 06-S04 | `sc_po_test.dart` (tradeadmin) | Fail 2026-10-07: Bad state: N1: nothing on screen says why [open=true, saved=0, said=""]; open=true, saved=0, said="The request validation failed. / lines 1, ordered_quantity... |
| SC-PO-021 | Negative | PU | Fixture firm; supplier Principal supplier; Detergent | Expected by earlier than Order date. Save. | Checks N1 to N3 hold. Date named. Short delivery window shows a helper note. | 06-S04 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: Expected by is a date picker limited to future days; not driven |
| SC-PO-022 | Negative | PU | Supplier is inactive or blocked | Look in the Vendor box. | An inactive supplier is not offered. | 06-S04 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: no inactive supplier in the fixture firm |
| SC-PO-023 | Negative | PU | Draft order | Look for Approve. | Not offered (no PURCHASE_APPROVE). | BUY-001 | not yet |  |
| SC-PO-024 | Negative | PM | Draft order not submitted | Press Approve if the firm's stage requires Submit first. | Refused in words or Approve not offered; approval cannot be skipped. | BUY-001 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: Approve is absent on a Draft |
| SC-PO-025 | Negative | PM | Order past a budget set in Settings > Buying > Purchase Budgets | Approve. | Refused: needs PURCHASE_APPROVE_OVER_BUDGET; message names the budget. FA holds that code and succeeds. | BUY-022 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: no budget set in the fixture firm |
| SC-PO-026 | Negative | PM | Order above the Approval Limits | Approve. | Goes to the next level or is refused naming the limit. | BUY-022 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: no approval limits set in the fixture firm |
| SC-PO-027 | Negative | PM | Order with goods received | Press Cancel. | Refused in words: goods have been received against it. | BUY-003 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: status RECEIVED, screen says "Cancel purchase order / Reason / Optional remarks for the lifecycle action / Cancel / Confirm" |
| SC-PO-028 | Negative | PM | Order with a bill resting on it | Press Cancel or Amend. | Refused in words naming the bill. | BUY-005 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: status RECEIVED, screen says "Cancel purchase order / Reason / Optional remarks for the lifecycle action / Cancel / Confirm / Cancel purchase order..." |
| SC-PO-029 | Negative | PM | Approved order | Edit and Save a changed quantity. | Shows the warning 'Editing withdraws the approval'; after saving the order is no longer Approved. | BUY-002 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: note: :: after Edit: dialogs 1, save box 0, text "Editing withdraws the approval / Cancel / Edit anyway"; fresh: Editing withdraws the approval; warning show... |
| SC-PO-030 | Negative | PU | Two rate contracts overlapping or an expired contract | Pick the product. | Expired contract is not applied; notice says so. | BUY-062 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: no rate contract in the fixture firm |
| SC-PO-031 | Negative | PU | Typed editor | Close the editor. | 'Discard unsaved changes?'; Keep editing keeps all. | 06-S04 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: editor closed=false, asked=true |
| SC-PO-032 | Role | PU | Purchasing | Open the Buy menu. | Purchase Orders offered with New and Submit; Approve, Cancel-after-approval absent as the role lacks PURCHASE_APPROVE. | 01-ROLES R07 | `sc_po_test.dart` (qpexe) | Pass 2026-10-07: offered: true; list 200; {+ New: enabled, New: absent, Submit: absent, Approve: absent, Cancel: enabled} |
| SC-PO-033 | Role | PM | Purchase Manager | Open Purchase Orders. | Approve, Amend, Close offered; settings dialogs under Settings > Buying (PURCHASE_MANAGE_SETTINGS) are not. | 01-ROLES R08 | `sc_po_test.dart` (qpmgr) | Pass 2026-10-07: offered: true; {Approve: enabled, Amend: absent, Close: enabled, Cancel: enabled} |
| SC-PO-034 | Role | WH | Warehouse | Look in the Buy menu. | Purchase Orders is offered only if PURCHASE_VIEW is held; the role receives against orders, so check the order box in a goods receipt works. | 01-ROLES R06 | `sc_po_test.dart` (qstore) | Fail 2026-10-07: Purchase Orders offered or not: Bad state: menu (false) and server (200) disagree |
| SC-PO-035 | Role | FS | Field Sales | Look in the Buy menu. | Nothing offered. | 01-ROLES R04 | `sc_po_test.dart` (qsexe) | Pass 2026-10-07: Purchase Orders offered: false; buy menu null; list answers 403 |
| SC-PO-036 | Role | RO | Read Only | Open Purchase Orders. | Rows readable; no write buttons. | 01-ROLES R11 | `sc_po_test.dart` (qro) | Pass 2026-10-07: offered: true; {+ New: disabled, New: absent, Submit: absent, Approve: absent, Edit: absent, Cancel: absent, Close: absent} |
| SC-PO-037 | Multi-user | PU, PM, WH | PU raises and submits; PM approves; WH opens Goods Receipts | Each opens the list after the last. | PM sees PU's submitted order; WH can choose the approved order in the receipt editor. | BUY-001 | `sc_po_test.dart` (tradeadmin) | Skipped 2026-10-07: covered by SC-PO-039/040 and the GR file |
| SC-PO-038 | Multi-user | PU and PM | Same Draft order open twice | PM approves; PU, on the old copy, saves a change. | PU is told 'This record changed since you loaded it. Reload and try again.'; typing kept. | BUY-002 | `sc_po_test.dart` (tradeadmin) | Fail 2026-10-07: Bad state: HIGH: a save from a stale copy went through over the other user's submit (status SUBMITTED) |
| SC-PO-039 | Multi-user | PM and PM2 | Two approvers | Both press Approve. | One succeeds; the other sees the status already moved. | BUY-001 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, screen says "PO-T10069CWY-S-HO-2026-2027-000128 approved." |
| SC-PO-040 | Multi-user | PU | Two sessions with the list open | Session A approves; session B Refresh. | B shows Approved and updated cards. | 06-S04 | `sc_po_test.dart` (tradeadmin) | Pass 2026-10-07: row reads: PO-T10069CWY-S-HO-2026-2027-000130 / Principal supplier t10069cwy / Head Office / Main Warehouse / Q acct (t10069cwy) / 2026-10-07 / STANDARD PURC... |

## GR. Goods receipts

**Where and who.** Buy > Goods Receipts (daily list). Offered to FA, FM, WH (PURCHASE_RECEIVE), PM, PU, RO. A warehouse user sees receipts, not bills or returns.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-GR-001 | Positive | WH | Approved PO of 10 | Open Buy > Goods Receipts. | Grid shows receipts with status; opens without error. | 06-S19 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: columns present |
| SC-GR-002 | Positive | WH | Approved PO of 10 | New. Under 'Purchase order (approved orders only)' choose the PO. Fill 'Went to warehouse'. Save and complete. | Receipt Completed; stock rises by the quantity; journal posted. The order's status moves with the receipt. | BUY-003 | `buying_flow_test.dart` | Pass 2026-10-07 |
| SC-GR-003 | Positive | WH | PO of 10 | Receive 4, save and complete. Then a second receipt for 6. | Order Part received, then Received; each receipt offers only what is still owed. | BUY-003 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: after 4: order PARTIALLY_RECEIVED; second receipt boxes PO-T10069CWY-S-HO-2026-2027-000136  07-10-2026 / 6 / 0 / 0 / 0; after the rest: order RECEIVED |
| SC-GR-004 | Positive | WH | Product with batches | Fill batch, 'Manufactured on' and expiry on the line. | Batch is created with its expiry. | BUY-082 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: the product is not batch-tracked in the fixture |
| SC-GR-005 | Positive | WH | Product with serials | Type, paste or fill serials from a range. | Serial count equals the quantity; each is unique in the firm. | BUY-063, BUY-064 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: the product is not serial-tracked in the fixture |
| SC-GR-006 | Positive | WH | PTR/PTS feature on | Fill MRP per unit, PTR per unit, PTS per unit. | They reach the batch; PTR not above MRP. | BUY-082, BUY-083 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: MRP/PTR/PTS boxes need a batch-tracked product |
| SC-GR-007 | Positive | WH | Inspection on | Complete a receipt. | Goods wait in quarantine until passed at Buy > Quality Inspection. | BUY-021 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: quarantine needs Quality Inspection set on |
| SC-GR-008 | Positive | WH | Completed receipt | Press Close. | Status Closed. | BUY-003 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: status CLOSED, screen says "Goods receipt GRN-T10069CWY-S-HO-2026-2027-000061 closed." |
| SC-GR-009 | Positive | WH | A receipt with transport details | Fill Transport, Vehicle number, E-way bill no., E-way bill date. | Kept on reopen. | BUY-003 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: transport boxes not driven |
| SC-GR-010 | Positive | WH | Completed, not billed | Press Cancel. | Cancelled; stock and journal undone together. | BUY-004 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: status CANCELLED, screen says "Goods receipt GRN-T10069CWY-S-HO-2026-2027-000060 cancelled." |
| SC-GR-011 | Positive | WH | Receipt | Open Attachments, add a file. | File listed; only PDF, JPG or PNG up to 10 MB. | BUY-042 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: file picker not drivable |
| SC-GR-012 | Negative | WH | Receipt editor | Save with no purchase order. | Checks N1 to N3 hold. Order named as missing. | 06-S19 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Choose the purchase order being received." |
| SC-GR-013 | Negative | WH | PO of 10 | Receive 11. | Checks N1 to N3 hold. Message says more than is still owed on the order. Wording on first run (some firms allow a tolerance). | BUY-003 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Goods receipt exceeds allowed quantity for PO line 1: 10 PIECE ordered, 0 PIECE already received, and this line receives 11 PIECE. ... |
| SC-GR-014 | Negative | WH | Receipt editor | Quantity 0 on all lines, then -1. | Checks N1 to N3 hold. Quantity more than zero. | 06-S19 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Enter a received quantity on at least one line. / Zero only / Value at the order's rates, before tax  0.00"; open=true, saved=0, sa... |
| SC-GR-015 | Negative | WH | Receipt editor | Receipt date in the future. | 'The goods cannot have been received in the future.' | 06-S19 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: Receipt date is a picker limited to today |
| SC-GR-016 | Negative | WH | Product with serials | Quantity 3 and only 2 serials; also a serial already in the firm. | Refused in words; the duplicate serial is named. | BUY-063, BUY-064 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: needs a serial-tracked product |
| SC-GR-017 | Negative | WH | Draft or unapproved order | Look in the order box. | Only approved orders are offered. | BUY-001 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: approved order offered=true, draft order offered=false |
| SC-GR-018 | Negative | WH | A receipt already billed | Press Cancel. | Refused: the receipt has been invoiced. | BUY-005 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: status COMPLETED, screen says "Goods receipt GRN-T10069CWY-S-HO-2026-2027-000057 has been invoiced, so cancelling it would leave the accrual and the payable ... |
| SC-GR-019 | Negative | WH | Completed receipt | Try Edit. | 'Only draft goods receipts can be updated.' | BUY-003 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: Edit is absent on a Completed receipt |
| SC-GR-020 | Negative | WH | Draft receipt | Press Close. | 'Only completed goods receipts can be closed.' | BUY-003 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: Close is enabled on a Draft receipt; pressed: status DRAFT, says "Only completed goods receipts can be closed." |
| SC-GR-021 | Negative | WH | Receipt with goods already sold | Press Cancel. | Refused or stock goes negative-protected; message names the product. Wording on first run. | BUY-004 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: needs stock consumed after the receipt |
| SC-GR-022 | Negative | WH | Typed editor | Close the editor. | Discard question; Keep editing keeps all. | 06-S19 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: editor closed=false, asked=true |
| SC-GR-023 | Role | WH | Warehouse | Open Goods Receipts. | Offered with New and Complete (PURCHASE_RECEIVE). Bills and returns screens are not offered. | 01-ROLES R06 | `sc_gr_test.dart` (qstore) | Pass 2026-10-07: offered: true; list 200; bills offered: false; returns offered: false; {+ New: enabled, New: absent, Approve: absent, Complete: enabled, Cancel: absent} |
| SC-GR-024 | Role | PU | Purchasing | Open Goods Receipts. | Offered; Complete offered; Quality Inspection not offered (no PURCHASE_INSPECT). | 01-ROLES R07 | `sc_gr_test.dart` (qpexe) | Pass 2026-10-07: offered: true; list 200; bills offered: true; returns offered: true; {+ New: enabled, New: absent, Approve: absent, Complete: enabled, Cancel: enabled} |
| SC-GR-025 | Role | PM | Purchase Manager | Open Goods Receipts and Quality Inspection. | Both offered. | 01-ROLES R08 | `sc_gr_test.dart` (qpmgr) | Pass 2026-10-07: offered: true; list 200; bills offered: true; returns offered: true; {+ New: enabled, New: absent, Approve: absent, Complete: enabled, Cancel: enabled} |
| SC-GR-026 | Role | FS | Field Sales | Look in the Buy menu. | Not offered. | 01-ROLES R04 | `sc_gr_test.dart` (qsexe) | Pass 2026-10-07: offered: false; list 403 |
| SC-GR-027 | Role | RO | Read Only | Open Goods Receipts. | Rows readable; no write buttons. | 01-ROLES R11 | `sc_gr_test.dart` (qro) | Pass 2026-10-07: offered: true; {+ New: absent, New: absent, Complete: absent, Approve: absent, Cancel: absent, Close: absent} |
| SC-GR-028 | Multi-user | PU, PM, WH, PU | Order approved by PM; WH receives; PU bills | Each opens after the last. | WH sees PM's approved order; PU sees WH's completed receipt under 'only those with receipts to bill'. | BUY-003 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: covered by SC-GR-029 and the PO file |
| SC-GR-029 | Multi-user | WH and WH2 | Two storemen receive the full quantity of one order | Both Save and complete. | The second is told the order is already received or only the remainder is offered. | BUY-003 | `sc_gr_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Goods receipt exceeds allowed quantity for PO line 1: 10 PIECE ordered, 10 PIECE already received, and this line receives 10 PIECE." |
| SC-GR-030 | Multi-user | WH and PM | Same Draft receipt open twice | WH completes it; PM saves a change from the old copy. | PM is told the record changed; typing kept. | 06-S19 | `sc_gr_test.dart` (tradeadmin) | Skipped 2026-10-07: a Completed receipt cannot be edited on screen |

## PB. Supplier bills (purchase invoices)

**Where and who.** Buy > Purchase Invoices (daily list). Offered to FA, FM, PM, PU, AC (reads), RO. Approve needs PURCHASE_APPROVE; Pay now needs PAYMENT_CREATE.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-PB-001 | Positive | PU | A completed receipt for Principal supplier | Open Buy > Purchase Invoices. | Grid with bill number, supplier, dates, status, total, outstanding. | 06-S17 | `sc_pb_test.dart` (tradeadmin) | Fail 2026-10-07: note: :: short texts: QA Agency / > / Selling t10069cwy / Home / Sell / Buy / Stock / Accounts / Masters / Reports / Search or jump to… / Ctrl+K / 1 / Sellin... |
| SC-PB-002 | Positive | PU | Completed receipt | New. Supplier (only those with receipts to bill): Principal supplier. Press Choose receipts, tick the receipt. Fill 'Supplier bill date'. Save. | Draft bill with lines from the receipt at the receipt's rates. | BUY-003 | `buying_flow_test.dart` | Pass 2026-10-07 |
| SC-PB-003 | Positive | PM | Draft bill | Press Approve. In the approve dialog press Approve. | Status Approved; the dialog says it is approved and posted to the books. Input tax is posted to the claim account. | BUY-003 | `buying_flow_test.dart` | Pass 2026-10-07 |
| SC-PB-004 | Positive | PM | Draft bill and a role with PAYMENT_CREATE | In the approve dialog tick Pay now for part of the bill. | Bill approved; the part is paid; the rest stays owing. | BUY-036, BUY-037 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED; payments +1; screen says "PI-T10069CWY-S-HO-2026-2027-000037 approved and posted to the books." |
| SC-PB-005 | Positive | PU | A bill typed alone, with no receipt | New, choose Supplier, add a line. | Allowed where the firm's stage permits it; goods then come in on approval or the screen says a receipt is needed. | BUY-086 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: the firm bills receipts only; a bill with no receipt cannot be started on screen |
| SC-PB-006 | Positive | PU | Foreign supplier | Choose Currency and Exchange rate. | Foreign note shown; rupee values shown; not offered where noted. | BUY-086, BUY-087 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: no foreign-currency supplier in the fixture |
| SC-PB-007 | Positive | PM | Bill for a contractor above the TDS limit | Open the approve dialog. | A TDS proposal (194C or 194J) is shown and can be overridden within limits. | BUY-043, BUY-048 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: no TDS section set up in the fixture |
| SC-PB-008 | Positive | PU | Bill from a TCS-charging supplier | Fill 'TCS charged by supplier %' or 'TCS amount'. | A typed amount wins over the rate; the bill total includes TCS. | BUY-050, BUY-051 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: TCS boxes not driven |
| SC-PB-009 | Positive | PU | Bill | Open Attachments, add a file. | File listed; wrong type or oversize is refused. | BUY-040, BUY-041 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: file picker not drivable |
| SC-PB-010 | Positive | PM | Approved bill | Press Close. | Status Closed. | BUY-003 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: status CLOSED, screen says "PI-T10069CWY-S-HO-2026-2027-000044 closed." |
| SC-PB-011 | Positive | PM | Approved bill, no payment | Press Cancel. | Cancelled; journal and TCS reversed. | BUY-052 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: status CANCELLED, screen says "PI-T10069CWY-S-HO-2026-2027-000045 cancelled." |
| SC-PB-012 | Positive | AC | Buy > Payables by Month | Open it. | What each supplier is owed, by month, agrees with the books; a part payment shows in the Paid view. | BUY-033, BUY-034 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: Payables by Month report not reached |
| SC-PB-013 | Positive | PU | Supplier's e-invoice reference | Fill the supplier IRN. | Kept on reopen. | BUY-003 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: IRN dialog not driven |
| SC-PB-014 | Negative | PU | Bill editor | Save with no supplier. | Checks N1 to N3 hold. Supplier named as missing. | 06-S17 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Choose the goods receipt being billed." |
| SC-PB-015 | Negative | PU | Bill editor | Save with no receipt chosen and no lines. | Checks N1 to N3 hold. A line or receipt is needed. | 06-S17 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Goods receipts to bill — Principal supplier t10069cwy / Goods receipt / Date / Order / Left to bill / GRN-T10069CWY-S-HO-2026-2027-... |
| SC-PB-016 | Negative | PU | Receipt of 10 | Bill 12 units. | Checks N1 to N3 hold. Message says no more than was received can be billed. | BUY-016 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Line 1: quantity exceeds what the receipt still has to be billed for (10). / More than received by" |
| SC-PB-017 | Negative | PU | Receipt already billed | Look under Choose receipts. | A billed receipt is not offered. | BUY-005 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: billed receipt GRN-T10069CWY-S-HO-2026-2027-000075 offered=false; unbilled GRN-T10069CWY-S-HO-2026-2027-000080 offered=true |
| SC-PB-018 | Negative | PU | Bill editor | Bill date in the future. | Checks N1 to N3 hold. Message about the date. | 06-S17 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: Bill date is not a typed box |
| SC-PB-019 | Negative | PM | Bill dated in a closed period | Approve. | Refused naming the period; bill stays Draft. | 06-S17 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: no closed period in the fixture firm |
| SC-PB-020 | Negative | PM | Bill outside tolerance against the order | Approve. | Refused, naming the tolerance; PURCHASE_APPROVE_OVER_TOLERANCE is needed (FA holds it). | BUY-022 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: no tolerance set in the fixture firm |
| SC-PB-021 | Negative | PM | Same supplier bill number twice | Save the second. | Refused as a duplicate. Wording on first run. | BUY-075 | `sc_pb_test.dart` (tradeadmin) | Fail 2026-10-07: Bad state: a duplicate number was accepted |
| SC-PB-022 | Negative | PM | Approve dialog, Pay now | Pay more than the bill. | Refused: more than the bill. Dialog stays open. | BUY-037 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: open=true, saved=0, said="Approve PI-T10069CWY-S-HO-2026-2027-000038 / Bill PI-T10069CWY-S-HO-2026-2027-000038 owes 708.00, so 99999 cannot be paid against i... |
| SC-PB-023 | Negative | PM | Pay now, role without PAYMENT_CREATE | Look at the Pay now control. | Not offered; saying Pay now is refused without the right. | BUY-039 | not yet |  |
| SC-PB-024 | Negative | PM | Approved bill | Try Edit. | 'Only draft ... can be updated' style message or Edit absent. | BUY-003 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: Edit is absent on an Approved bill |
| SC-PB-025 | Negative | PM | Approved bill with a payment | Press Cancel. | Refused in words naming the payment; reverse the payment first. | BUY-038 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, screen says "PI-T10069CWY-S-HO-2026-2027-000042 cannot be cancelled while it has payment PY-2026-2027-000014. Reverse or cancel those first." |
| SC-PB-026 | Negative | PM | Approved bill with a return or debit note resting on it | Press Cancel. | Refused naming it. | BUY-017 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, screen says "PI-T10069CWY-S-HO-2026-2027-000043 cannot be cancelled while it has purchase return PR-T10069CWY-S-HO-2026-2027-000015. Reverse... |
| SC-PB-027 | Negative | PU | Capital goods line | Leave Asset class empty. | Refused: 'Asset class (required)'. | BUY-088 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: no capital goods line in the fixture |
| SC-PB-028 | Negative | PU | Typed editor | Close the editor. | Discard question; Keep editing keeps all. | 06-S17 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: editor closed=false, asked=true |
| SC-PB-029 | Role | PU | Purchasing | Open Purchase Invoices. | New offered; Approve absent (no PURCHASE_APPROVE). | 01-ROLES R07 | `sc_pb_test.dart` (qpexe) | Pass 2026-10-07: offered: true; list 200; {+ New: enabled, New: absent, Approve: absent, Edit: absent} |
| SC-PB-030 | Role | PM | Purchase Manager | Open Purchase Invoices. | Approve offered; Pay now absent (no PAYMENT_CREATE). | 01-ROLES R08 | `sc_pb_test.dart` (qpmgr) | Pass 2026-10-07: offered: true; Approve enabled; Pay now control shown=false |
| SC-PB-031 | Role | AC | Accounts | Open Purchase Invoices and Payables by Month. | Payables offered; PURCHASE_VIEW decides whether the list itself is offered (to be matched to the matrix). | 01-ROLES R09 | `sc_pb_test.dart` (qacct) | Pass 2026-10-07: offered: false; list 403; payables offered: false |
| SC-PB-032 | Role | WH | Warehouse | Look for bills. | Not offered. | 01-ROLES R06 | `sc_pb_test.dart` (qstore) | Pass 2026-10-07: offered: false; list 403 |
| SC-PB-033 | Role | RO | Read Only | Open the list. | Rows readable; no write buttons. | 01-ROLES R11 | `sc_pb_test.dart` (qro) | Pass 2026-10-07: offered: true; {+ New: absent, New: absent, Edit: absent, Approve: absent, Cancel: absent, Close: absent} |
| SC-PB-034 | Multi-user | PU, PM, AC | PU bills a receipt; PM approves; AC pays | Each opens after the last. | PM sees PU's Draft; AC's Payments screen offers the approved bill as outstanding. | BUY-003, BUY-008 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: covered by the PO and PY files |
| SC-PB-035 | Multi-user | PM and PM2 | Same Draft bill open twice | A approves; B approves from the old list. | B is refused: only a draft can be approved. One journal only. | BUY-003 | `sc_pb_test.dart` (tradeadmin) | Pass 2026-10-07: status APPROVED, screen says "Approve PI-T10069CWY-S-HO-2026-2027-000039 / Approving posts the bill to the books. / Paid now / A cash purchase: record the pa... |
| SC-PB-036 | Multi-user | PU and PM | Same Draft bill open twice | PM saves; PU, on the old copy, saves. | PU told the record changed; typing kept. | 06-S17 | `sc_pb_test.dart` (tradeadmin) | Skipped 2026-10-07: a Draft bill has no Edit on screen (Open, Approve, Cancel, Close, Record IRN only), so there is no second session to race |

## PY. Payments

**Where and who.** Buy > Payments (daily Money list). Offered to FA, FM, AC (PAYMENT_CREATE, PAYMENT_VIEW), CS (Cashier role), RO. Related: Payment Runs, Post-dated Cheques, Supplier Statements.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-PY-001 | Positive | AC | Approved bill for Principal supplier, 1,000 outstanding | Open Buy > Payments. | Grid of payments; chips Supplier credits and Supplier refunds; Search by number or reference. | 06 Screen checks | not yet |  |
| SC-PY-002 | Positive | AC | Approved bill outstanding | New. Pick Principal supplier. Press Oldest first. Press Record. | Bill's outstanding falls; payment number listed; journal posted (Dr payable, Cr bank). | BUY-008 | `buying_flow_test.dart` | Pass 2026-10-07 |
| SC-PY-003 | Positive | AC | Bill of 1,000 | Pay 400 only. | 400 settles; 600 remains; Paid view shows the part payment. | BUY-034, BUY-072 | not yet |  |
| SC-PY-004 | Positive | AC | Bill with TDS proposed | Fill TDS deducted and section. | TDS is posted; the supplier receives the net. | BUY-043, BUY-047 | not yet |  |
| SC-PY-005 | Positive | AC | Bank mode cheque | Choose Mode cheque; fill instrument date. Record. Press Print cheque. | Cheque prints in the firm's layout; Cheque layout opens. | BUY-008 | not yet |  |
| SC-PY-006 | Positive | AC | Foreign bill | Pay in the supplier's currency at another rate. | Exchange loss or gain is posted; rupees refused against a foreign bill. | BUY-071, BUY-073 | not yet |  |
| SC-PY-007 | Positive | AC | Several approved bills | Open Payment Runs, create a run, approve it. | A run lists due bills; bank file is produced. | BUY-023 | not yet |  |
| SC-PY-008 | Positive | AC | Recorded payment | Press Reverse, give the reason, confirm. | Payment Reversed; the bill is Approved and owing again. | BUY-038 | not yet |  |
| SC-PY-009 | Positive | AC | Recorded payment | Press Print, Send, Files. | Preview and channel behave as in Receipts. | BUY-008 | not yet |  |
| SC-PY-010 | Positive | AC | Cheque issued but not yet cleared | Open Post-dated Cheques under Buy. | The cheque shows with its date; it clears on the date. | BUY-008 | not yet |  |
| SC-PY-011 | Negative | AC | Payment dialog | Amount 0 or empty, then negative. | Refused in words; dialog open; values kept. | BUY-037 | not yet |  |
| SC-PY-012 | Negative | AC | Bill of 1,000 | Pay 1,500 against it. | Refused: more than the bill, as in Pay now (BUY-037). Payments screen may allow an advance; to be established on the first run. | BUY-037 | not yet |  |
| SC-PY-013 | Negative | AC | Payment dialog | Date in the future. | Refused in words. | BUY-008 | not yet |  |
| SC-PY-014 | Negative | AC | Payment dialog | Date in a closed period. | Refused naming the period. | BUY-008 | not yet |  |
| SC-PY-015 | Negative | AC | Payment dialog | No supplier, or no bank account chosen. | Field named as missing. | BUY-008 | not yet |  |
| SC-PY-016 | Negative | AC | Payment dialog | Pick a foreign bill and pay rupees, or use TDS and an advance. | Refused in words. | BUY-073 | not yet |  |
| SC-PY-017 | Negative | AC | Reversed payment | Press Reverse again. | Not offered or refused: already reversed. | BUY-038 | not yet |  |
| SC-PY-018 | Negative | AC | Recorded payment | Look for Edit and Delete. | Neither is offered; a payment is reversed, never edited. | BUY-038 | not yet |  |
| SC-PY-019 | Negative | AC | Typed dialog | Close it. | Discard question. | BUY-008 | not yet |  |
| SC-PY-020 | Role | AC | Accounts | Open Payments. | Offered with Record, Reverse, Payment Runs (PAYMENT_RUN_APPROVE). | 01-ROLES R09 | not yet |  |
| SC-PY-021 | Role | PU | Purchasing | Look for Payments. | Not offered (no PAYMENT_VIEW). | 01-ROLES R07 | not yet |  |
| SC-PY-022 | Role | PM | Purchase Manager | Look for Payments. | Not offered; whoever approves the bill does not move the cash. | 01-ROLES R08 | not yet |  |
| SC-PY-023 | Role | CS | Cashier role | Open Payments. | Offered with Record (PAYMENT_CREATE). | 01-ROLES R03 | not yet |  |
| SC-PY-024 | Role | RO | Read Only | Open Payments. | Readable; no write buttons. | 01-ROLES R11 | not yet |  |
| SC-PY-025 | Multi-user | PM, AC | PM approves a bill; AC pays it | AC refreshes Payments. | AC sees the approved bill; PM later sees it as paid. | BUY-008 | not yet |  |
| SC-PY-026 | Multi-user | AC and AC2 | Both pay the same bill in full | Record in two sessions. | The second is refused or only the remainder is allowed; the bill never goes below zero. | BUY-037 | not yet |  |
| SC-PY-027 | Multi-user | AC and FA | Same payment open twice | FA reverses; AC presses Reverse from the old list. | AC told already reversed; no double reversal. | BUY-038 | not yet |  |

## SCR. Supplier credits (credit set against a bill, and supplier refunds)

**Where and who.** Buy > Payments, chips Supplier credits and Supplier refunds. Offered with Payments: FA, FM, AC, RO.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-SCR-001 | Positive | AC | A return off a paid bill leaving a credit | Open Payments, press Supplier credits. | The credit is listed with supplier and amount. | BUY-011 | not yet |  |
| SC-SCR-002 | Positive | AC | Credit and an approved bill | Select the credit, press Apply. Pick the bill, confirm the amount. | Bill's outstanding falls; credit shows Applied; no journal posted by applying. | BUY-011, BUY-027 | not yet |  |
| SC-SCR-003 | Positive | AC | Credit | Apply part. | Only that part moves. | BUY-011 | not yet |  |
| SC-SCR-004 | Positive | AC | Supplier pays the credit back in cash | Press Supplier refunds; record the refund. | Refund reduces the credit and posts to the bank. | BUY-009 | not yet |  |
| SC-SCR-005 | Positive | AC | Credit set against an opening bill | Apply the credit to an opening bill. | Allowed; opening bill outstanding falls. | BUY-027 | not yet |  |
| SC-SCR-006 | Positive | AC | Buy > Payables by Month | Look for the Credits section. | Supplier credit sits in Credits, not in a month. | BUY-035 | not yet |  |
| SC-SCR-007 | Negative | AC | Credit 200 | Apply 300. | Refused: more than the credit; dialog open. | BUY-011 | not yet |  |
| SC-SCR-008 | Negative | AC | Bill of 100 | Apply 150. | Refused: more than the bill owes. | BUY-011 | not yet |  |
| SC-SCR-009 | Negative | AC | Credit dialog | Apply a future-dated credit. | 'A credit cannot be applied on a future date.' | BUY-011 | not yet |  |
| SC-SCR-010 | Negative | AC | Credit already applied | Apply again. | 'This credit has already been taken off the bill.' | BUY-011 | not yet |  |
| SC-SCR-011 | Negative | AC | Supplier with no open bill | Press Apply. | Dialog says 'This supplier has no open bills.' | BUY-011 | not yet |  |
| SC-SCR-012 | Negative | AC | Refund dialog | Refund more than the credit. | Refused in words. | BUY-009 | not yet |  |
| SC-SCR-013 | Role | AC | Accounts | Open Supplier credits. | Offered; Apply offered. | 01-ROLES R09 | not yet |  |
| SC-SCR-014 | Role | PU | Purchasing | Look for it. | Not offered. | 01-ROLES R07 | not yet |  |
| SC-SCR-015 | Role | RO | Read Only | Open it. | Readable; no Apply. | 01-ROLES R11 | not yet |  |
| SC-SCR-016 | Multi-user | PM, AC | PM approves a purchase return; AC sees the credit | AC opens Supplier credits. | The credit created by PM's return appears. | BUY-011 | not yet |  |
| SC-SCR-017 | Multi-user | AC and AC2 | Same credit open twice | Both apply it to different bills. | The second is refused or only the rest is applied. | BUY-011 | not yet |  |

## PR. Purchase returns

**Where and who.** Buy > Returns & notes > Purchase Returns (short list). Offered to FA, FM, PM, PU, RO. Warehouse does not hold the bills and returns codes.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-PR-001 | Positive | PU | A completed goods receipt for 10 | Open Purchase Returns. | Grid with return number, supplier, date, status; cards by status. | 06-S18 | not yet |  |
| SC-PR-002 | Positive | PU | Completed receipt | New. Choose 'Goods receipt going back (completed only)'. Returning 1. Reason code and 'Why it is going back'. Outcome: Refund. Save. | Draft return with the line and tax. | BUY-006 | `buying_flow_test.dart` | Pass 2026-10-07 |
| SC-PR-003 | Positive | PM | Draft return | Press Approve. | Status Approved; stock leaves; journal posted with the stock. | BUY-006 | `buying_flow_test.dart` | Pass 2026-10-07 |
| SC-PR-004 | Positive | PM | Approved return | Press Complete, then Close. | Completed then Closed. | BUY-006 | not yet |  |
| SC-PR-005 | Positive | PU | Outcome Replace | Raise, approve and complete a return with Outcome: Replace. | The order reopens for the replacement. | BUY-010 | not yet |  |
| SC-PR-006 | Positive | PU | Outcome Credit on a paid bill | Return off a bill already paid. | A supplier credit remains. | BUY-011 | not yet |  |
| SC-PR-007 | Positive | PU | Receipt with free goods | Return the bought units first, then the free ones off the receipt. | Free goods go back off the receipt that brought them. | BUY-093, BUY-095 | not yet |  |
| SC-PR-008 | Positive | PU | Batch tracked line | Open the return line. | The line takes its receipt line's batch only. | BUY-096 | not yet |  |
| SC-PR-009 | Positive | PM | Draft or Approved return | Press Cancel. | Cancelled. | BUY-006 | not yet |  |
| SC-PR-010 | Negative | PU | Receipt of 10 | Returning 11. | Checks N1 to N3 hold. Message: no more than was received. | BUY-094 | not yet |  |
| SC-PR-011 | Negative | PU | Receipt of 10, 4 already returned | Return 7. | Checks N1 to N3 hold. Only 6 can go back. | BUY-094 | not yet |  |
| SC-PR-012 | Negative | PU | Return editor | Quantity 0 on every line; then -1. | Checks N1 to N3 hold. Quantity more than zero. | 06-S18 | not yet |  |
| SC-PR-013 | Negative | PU | Return editor | No receipt chosen. Save. | Checks N1 to N3 hold. Receipt named. | 06-S18 | not yet |  |
| SC-PR-014 | Negative | PU | Draft (not completed) receipt | Look for it in the receipt box. | Only completed receipts are offered. | BUY-006 | not yet |  |
| SC-PR-015 | Negative | PU | Return editor | Return date in the future. | Checks N1 to N3 hold. Date named. | 06-S18 | not yet |  |
| SC-PR-016 | Negative | PU | Goods already sold | Return more than is in stock. | Refused naming the product and stock. | BUY-006 | not yet |  |
| SC-PR-017 | Negative | PU | Capital goods | Return a capital-goods line. | Refused: capital goods cannot go back. | BUY-092 | not yet |  |
| SC-PR-018 | Negative | PM | Approved return | Try Edit. | 'Only draft purchase returns can be updated.' | BUY-006 | not yet |  |
| SC-PR-019 | Negative | PM | Draft return | Press Complete. | 'Only approved purchase returns can be completed.' | BUY-006 | not yet |  |
| SC-PR-020 | Negative | PM | Closed return | Press Close or Cancel. | 'This purchase return is already closed.' | BUY-006 | not yet |  |
| SC-PR-021 | Negative | PU | Typed editor | Close it. | Discard question. | 06-S18 | not yet |  |
| SC-PR-022 | Role | PU | Purchasing | Open Purchase Returns. | New offered; Approve absent (no PURCHASE_APPROVE). | 01-ROLES R07 | not yet |  |
| SC-PR-023 | Role | PM | Purchase Manager | Open Purchase Returns. | Approve, Complete, Close, Cancel offered. | 01-ROLES R08 | not yet |  |
| SC-PR-024 | Role | WH | Warehouse | Look for it. | Not offered. | 01-ROLES R06 | not yet |  |
| SC-PR-025 | Role | RO | Read Only | Open it. | Readable; no write buttons. | 01-ROLES R11 | not yet |  |
| SC-PR-026 | Multi-user | PU, PM, AC | PU raises; PM approves; AC sees the credit or refund | Each opens after the last. | PM sees PU's Draft; AC's Payments screen shows the supplier credit or refund. | BUY-009, BUY-011 | not yet |  |
| SC-PR-027 | Multi-user | PM and PM2 | Same return open twice | Both approve. | One succeeds; the other sees the status moved. | BUY-006 | not yet |  |
| SC-PR-028 | Multi-user | PU and PM | Same Draft return open twice | PM saves; PU saves from the old copy. | PU told the record changed; typing kept. | 06-S18 | not yet |  |

## DB. Debit notes (to a supplier)

**Where and who.** Buy > Returns & notes > Debit Notes. Offered to FA, FM, PM (draft only), AC, RO. Approve needs DEBIT_NOTE_APPROVE, which Purchase Manager does not hold.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-DB-001 | Positive | PM | An approved bill of 1,000 taxable | Open Debit Notes. | Grid: Number, Supplier, Bill, Date, Reason, Status, Taxable Value, Tax, Total. | BUY-017 | not yet |  |
| SC-DB-002 | Positive | PM | Approved bill | New. Supplier: Principal supplier. 'Bill being corrected (approved)'. Reason. Save. | Draft debit note saved with the corrected amounts. | BUY-017 | not yet |  |
| SC-DB-003 | Positive | FA | Draft debit note | Press Approve. | Approved; claimed input tax reverses; the supplier's balance falls. | BUY-017 | not yet |  |
| SC-DB-004 | Positive | PM | Draft | Edit and save. | A Draft is editable; Edit titled with the note number. | BUY-017 | not yet |  |
| SC-DB-005 | Positive | FA | Bill already paid | Raise and approve a debit note. | A supplier credit remains. | BUY-017 | not yet |  |
| SC-DB-006 | Positive | PM | Debit note against a foreign bill | Raise and approve. | Posts rupees at the bill's rate. | BUY-091 | not yet |  |
| SC-DB-007 | Positive | PM | Supplier's own credit note | Fill 'Supplier credit note' and 'Its date'. | Kept on reopen. | BUY-017 | not yet |  |
| SC-DB-008 | Positive | AC | Purchase register | Open the GST purchase register for the month. | A debit note is a minus row on its own date. | BUY-032 | not yet |  |
| SC-DB-009 | Negative | PM | Editor | Save with no supplier or no bill. | Checks N1 to N3 hold. Missing field named. | BUY-017 | not yet |  |
| SC-DB-010 | Negative | PM | Bill of 1,000 | Debit more than the bill. | Checks N1 to N3 hold. Message names the limit. | BUY-017 | not yet |  |
| SC-DB-011 | Negative | PM | Editor | Reason empty. | Reason named as missing (or accepted); wording on first run. | BUY-017 | not yet |  |
| SC-DB-012 | Negative | PM | Draft bill | Look in the Bill box. | Only approved bills are offered. | BUY-017 | not yet |  |
| SC-DB-013 | Negative | PM | Approved note | Try Edit. | Not offered or refused. | BUY-017 | not yet |  |
| SC-DB-014 | Negative | FA | Debit note in a closed period | Approve. | Refused naming the period. | BUY-017 | not yet |  |
| SC-DB-015 | Negative | FA | Approved note | Press Approve again. | Not offered or refused. | BUY-017 | not yet |  |
| SC-DB-016 | Negative | PM | Typed editor | Close it. | Discard question. | BUY-017 | not yet |  |
| SC-DB-017 | Role | PM | Purchase Manager | Open Debit Notes. | New and Edit offered; Approve absent (no DEBIT_NOTE_APPROVE). | 01-ROLES R08 | not yet |  |
| SC-DB-018 | Role | PU | Purchasing | Look for Debit Notes. | Not offered. | 01-ROLES R07 | not yet |  |
| SC-DB-019 | Role | AC | Accounts | Open Debit Notes. | Offered or not per the matrix; result recorded. | 01-ROLES R09 | not yet |  |
| SC-DB-020 | Role | RO | Read Only | Open it. | Readable; no write buttons. | 01-ROLES R11 | not yet |  |
| SC-DB-021 | Multi-user | PM, FA | PM drafts; FA approves | FA opens the list. | FA sees PM's Draft; PM later sees Approved. | BUY-017 | not yet |  |
| SC-DB-022 | Multi-user | FA and FA2 | Same Draft note open twice | Both approve. | One journal only; second told it is approved. | BUY-017 | not yet |  |

# Part 3. Pricing


## PL. Price lists

**Where and who.** Settings (gear) > Set up > Pricing > Price Lists. Offered to FA, FM, RO (PRICE_LIST_VIEW); edited with PRICE_LIST_MANAGE. Not held by SM, FS, CS, PU, PM, AC.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-PL-001 | Positive | FA | Fixture firm; Vijaya Stores (standing 7.5 percent); Detergent 84 | Open Settings > Set up > Pricing > Price Lists. | Grid with Code, Name, Applies to, In force, Products, Status; buttons New price list and Refresh; chip All lists. Opens without error. | 09 Screen checks | not yet |  |
| SC-PL-002 | Positive | FA | Fixture firm; Vijaya Stores (standing 7.5 percent); Detergent 84 | New price list. Code, Name. Add product: Detergent, Rate 80. Save. | List saved; appears in the grid with Products 1 and status in force. | INCENT-001 | `pricing_flow_test.dart` | Pass 2026-10-07 |
| SC-PL-003 | Positive | FA | Price list saved | Reopen it; look at the line. | Product, Rate and any ladder rows are kept. | INCENT-001 | `pricing_flow_test.dart` | Pass 2026-10-07 |
| SC-PL-004 | Positive | FA | A list with breaks | Add rows: From qty 0 at Discount 2 percent, From qty 15 at 4.25 percent. | The ladder is saved; a quantity takes the highest break at or below it. | SELL-002 | not yet |  |
| SC-PL-005 | Positive | FA | List applies to Everyone | New order for Vijaya for 20 Detergent. | The line is priced from the list (first break beats the standing 7.5 percent). | SELL-001 | not yet |  |
| SC-PL-006 | Positive | FA | List for One customer | New list, Applies to: One customer, pick Anand. | The customer's own list replaces the firm-wide ladder for him only. | SELL-003 | not yet |  |
| SC-PL-007 | Positive | FA | List for One supplier, One territory | Choose each. | The supplier box and territory box appear; the list applies to that party only. | SELL-003 | not yet |  |
| SC-PL-008 | Positive | FA | List with In force from and Until dates | Set both. Check an order dated inside and outside. | Inside: the list prices. Outside: it does not. | SELL-003 | not yet |  |
| SC-PL-009 | Positive | FA | Active list | Press Withdraw on the row (title 'Withdraw <code>?'), confirm. | List no longer applies; row shows withdrawn. | INCENT-001 | not yet |  |
| SC-PL-010 | Positive | FA | Several lists | Filter by All lists chip, by Supplier. | Grid narrows; counts agree. | 09 Screen checks | not yet |  |
| SC-PL-011 | Positive | FA | Price list on a promotion | New order with both a list and an offer on the product. | The promotion outranks the list; the order of precedence is amount, percent, promotion, price list, standing rate, group rate. | SELL-004, INCENT-001 | not yet |  |
| SC-PL-012 | Negative | FA | New price list | Save with no Code. | Checks N1 to N3 hold. Code named. | 09 Screen checks | not yet |  |
| SC-PL-013 | Negative | FA | New price list | Save with no Name. | Checks N1 to N3 hold. Name named. | 09 Screen checks | not yet |  |
| SC-PL-014 | Negative | FA | Code already used | Save a second list with the same code. | Checks N1 to N3 hold. Message says the code is taken. | 09 Screen checks | not yet |  |
| SC-PL-015 | Negative | FA | List row | Rate 0 or negative. | Checks N1 to N3 hold. Rate must be more than zero (or accepted as free: to be established on the first run). | 09 Screen checks | not yet |  |
| SC-PL-016 | Negative | FA | List row | Same product twice with the same From qty. | Checks N1 to N3 hold. Message names the duplicate. | 09 Screen checks | not yet |  |
| SC-PL-017 | Negative | FA | List row | Discount percent over 100 or negative. | Checks N1 to N3 hold. Message names the limit. | 09 Screen checks | not yet |  |
| SC-PL-018 | Negative | FA | List row | Until before In force from. | Checks N1 to N3 hold. Message names the dates. | 09 Screen checks | not yet |  |
| SC-PL-019 | Negative | FA | Applies to One customer | Save without choosing the customer. | Checks N1 to N3 hold. Customer named. | 09 Screen checks | not yet |  |
| SC-PL-020 | Negative | FA | Price floor set in Settings > Selling > Price Floor | Make a list rate below the floor and use it in an order. | The order line is refused or flagged against the floor; the message names the product. To be established on the first run. | SELL-022 | not yet |  |
| SC-PL-021 | Negative | FA | Typed editor | Close it. | Discard question; Keep editing keeps all. | 09 Screen checks | not yet |  |
| SC-PL-022 | Role | FA | Firm Administrator | Open Price Lists. | All buttons offered. | 01-ROLES R01 | not yet |  |
| SC-PL-023 | Role | SM | Sales Manager | Look for Price Lists under Settings > Set up > Pricing. | Not offered (no PRICE_LIST_VIEW). The manager can still read the effect on an order line. | 01-ROLES R05 | not yet |  |
| SC-PL-024 | Role | RO | Read Only | Open Price Lists. | Readable; New price list, Withdraw absent. | 01-ROLES R11 | not yet |  |
| SC-PL-025 | Role | FS | Field Sales | Look for it. | Not offered. | 01-ROLES R04 | not yet |  |
| SC-PL-026 | Multi-user | FA, FS | FA saves a list; FS raises an order | FS opens a new order after FA saves. | FS's line prices from the new list with no restart. | SELL-001 | not yet |  |
| SC-PL-027 | Multi-user | FA and FM | Same price list open twice | FM saves a new rate; FA saves from the old copy. | FA told the record changed; typing kept. | 09 Screen checks | not yet |  |
| SC-PL-028 | Multi-user | FA, SM | FA withdraws a list while SM has a Draft order using it | SM approves the order. | The order keeps the price it was struck at or is re-priced per the rule; to be established on the first run. | SELL-010 | not yet |  |

## LV. Price levels and customer groups

**Where and who.** Settings > Set up > Pricing > Price Levels, and Settings > Set up > Party lists > Customer Groups; a customer's own level is on its Customers editor. Price Levels needs PRICE_LIST_VIEW; Customer Groups needs the customer view.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-LV-001 | Positive | FA | Fixture firm; Vijaya Stores (standing 7.5 percent); Detergent 84 | Open Price Levels. | Grid with Code, Name, Order, Active; title Price Levels. | SELL-033 | not yet |  |
| SC-LV-002 | Positive | FA | Fixture firm; Vijaya Stores (standing 7.5 percent); Detergent 84 | New level: Code, Name, Order, Active ticked. Save. | Level appears in the grid. | SELL-033 | not yet |  |
| SC-LV-003 | Positive | FA | Level exists and a price list for it | Open Masters > Customers > Vijaya > editor; set Price level. | The customer's price level is saved and shown on reopen. | SELL-033 | not yet |  |
| SC-LV-004 | Positive | FA | Level attached | New order for that customer. | The line takes the level's rate. | SELL-033 | not yet |  |
| SC-LV-005 | Positive | FA | Customer Groups | Open Settings > Set up > Party lists > Customer Groups. | Dialog or page 'Customer groups' lists groups with Code, Name, Rate. | SELL-033 | not yet |  |
| SC-LV-006 | Positive | FA | Customer Groups | New group: Code, Name, Rate 5, Price level: a level. Save. | Group appears; a customer in the group takes the group rate when no other arrangement applies. | SELL-033 | not yet |  |
| SC-LV-007 | Positive | FA | A group | Edit it (Cancel edit offered), change Rate. | Saved; list updates. | SELL-033 | not yet |  |
| SC-LV-008 | Positive | FA | A group with no customers | Remove it; confirm 'Remove <name>?'. | Group gone from the list. | SELL-033 | not yet |  |
| SC-LV-009 | Positive | FA | Customer in a group and with a standing rate | Order a product. | Standing rate wins over the group rate. | INCENT-001 | not yet |  |
| SC-LV-010 | Negative | FA | New level | Save without Code, or without Name. | Checks N1 to N3 hold. Field named. | SELL-033 | not yet |  |
| SC-LV-011 | Negative | FA | Code already used | Save a level with a used code. | Checks N1 to N3 hold. Message says so. | SELL-033 | not yet |  |
| SC-LV-012 | Negative | FA | New group | Rate negative or over 100. | Checks N1 to N3 hold. Message names the limit. | SELL-033 | not yet |  |
| SC-LV-013 | Negative | FA | A group with customers in it | Press Remove. | Refused in words naming that customers use it, or they are released first; wording on first run. | SELL-033 | not yet |  |
| SC-LV-014 | Negative | FA | A level in use by a customer | Make it inactive or remove it. | Refused in words, or the customer falls back to no level; to be established. | SELL-033 | not yet |  |
| SC-LV-015 | Negative | FA | Typed dialog | Close it. | Discard question. | SELL-033 | not yet |  |
| SC-LV-016 | Role | SM | Sales Manager | Open the customer editor; try to change the Price level. | Refused or read only: the role that is constrained by the price does not set it (no CUSTOMER_MANAGE_SETTINGS). Result recorded. | SELL-033 | not yet |  |
| SC-LV-017 | Role | SM | Sales Manager | Look for Price Levels. | Not offered (no PRICE_LIST_VIEW). | 01-ROLES R05 | not yet |  |
| SC-LV-018 | Role | AC | Accounts | Open Customer Groups. | Offered if CUSTOMER_VIEW is held; edit buttons only with the manage code. | 01-ROLES R09 | not yet |  |
| SC-LV-019 | Role | RO | Read Only | Open Price Levels. | Readable; no write buttons. | 01-ROLES R11 | not yet |  |
| SC-LV-020 | Multi-user | FA, FS | FA changes a customer's level | FS opens a new order for him. | FS's order uses the new level's rate. | SELL-033 | not yet |  |
| SC-LV-021 | Multi-user | FA and FM | Same group open twice | Both save a different rate. | Second told the record changed; typing kept. | SELL-033 | not yet |  |

## RV. Product price revisions (new rates from a date)

**Where and who.** Masters > Products > a product's editor, section Price revisions ('New rates from...'). Needs PRODUCT_VIEW to read; changing needs the product update code (FA, FM).

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-RV-001 | Positive | FA | Product Detergent with a first rate set | Open Masters > Products, open Detergent. Look at Price revisions. | A dated list of rates, newest first, with Selling, MRP, Purchase and Remarks columns. | MAST-011, 05-S03 | not yet |  |
| SC-RV-002 | Positive | FA | Detergent | Press New rates from... Fill Effective from (a future date), Selling 90, MRP 100, Purchase 70, Remarks. Save. | A row is added with the date; the current rate does not change until that date. | MAST-011, 05-S03 | not yet |  |
| SC-RV-003 | Positive | FA | Revision dated today | Save a revision effective today. | The product's current selling rate becomes the new one; new documents use it. | MAST-011, 05-S03 | not yet |  |
| SC-RV-004 | Positive | FA | Two revisions | Open an order dated between them and one after. | Each document is priced from the revision in force on its own date. | MAST-011, 05-S03 | not yet |  |
| SC-RV-005 | Positive | FA | A future revision | Press Delete row, confirm 'Delete these rates?'. | The row is gone; rates fall back to the one before. | MAST-011, 05-S03 | not yet |  |
| SC-RV-006 | Positive | FA | Old documents | Open a bill raised before the revision. | It keeps its own price; history is not rewritten. | SELL-010 | not yet |  |
| SC-RV-007 | Negative | FA | Revision dialog | Save with Effective from empty. | Checks N1 to N3 hold. Date named. | MAST-011, 05-S03 | not yet |  |
| SC-RV-008 | Negative | FA | A revision already on that date | Save a second revision with the same date. | Refused (409) in words; the first stays. | MAST-011, 05-S03 | not yet |  |
| SC-RV-009 | Negative | FA | Revision dialog | Selling negative, or MRP below selling where the firm forbids it. | Checks N1 to N3 hold. Message names the rule; wording on first run. | MAST-011, 05-S03 | not yet |  |
| SC-RV-010 | Negative | FA | Revision dialog | Effective date far in the past inside a closed period. | Refused or accepted with a warning; to be established. | MAST-011, 05-S03 | not yet |  |
| SC-RV-011 | Negative | FA | Typed dialog | Close it. | Discard question. | MAST-011, 05-S03 | not yet |  |
| SC-RV-012 | Role | SM | Sales Manager | Open the product editor. | Rates readable; New rates from... absent (no product update code). | 01-ROLES R05 | not yet |  |
| SC-RV-013 | Role | PU | Purchasing | Open the product. | Purchase rate visible only with PRODUCT_VIEW_COST_PRICE; to be matched to the matrix. | 01-ROLES R07 | not yet |  |
| SC-RV-014 | Role | RO | Read Only | Open the product. | Rates readable; no New rates from... | 01-ROLES R11 | not yet |  |
| SC-RV-015 | Multi-user | FA, FS | FA adds a revision dated today | FS opens a new quotation. | The quotation uses the new selling rate. | MAST-011, 05-S03 | not yet |  |
| SC-RV-016 | Multi-user | FA and FM | Same product open twice | Both add revisions on the same date. | The second is refused (same date twice is a 409). | MAST-011, 05-S03 | not yet |  |

## OF. Offers (promotions) with budgets

**Where and who.** Settings > Set up > Pricing > Promotions. Offered to FA, FM, SM (read only, PROMOTION_VIEW), RO. Setting offers needs PROMOTION_MANAGE (not Sales Manager).

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-OF-001 | Positive | FA | Fixture firm; Vijaya Stores (standing 7.5 percent); Detergent 84 | Open Promotions. | Grid with Code, Name, Offer, Gives, In force, Per customer, Claimed, Stacks, Status, Order; buttons New promotion, New coupon, Try offers, Refresh. | 09 Screen checks | not yet |  |
| SC-OF-002 | Positive | FA | Fixture firm; Vijaya Stores (standing 7.5 percent); Detergent 84 | New promotion. Code, Name, % off 5, Budget (value) 5000. Save. Reopen. | Offer saved with its budget; Claimed starts at 0. | INCENT-013 | `pricing_flow_test.dart` | Pass 2026-10-07 |
| SC-OF-003 | Positive | FA | Offer BULK5 (7.5 percent, line of 25+) | Press Try offers; choose customer, product, quantity 30. | The panel names BULK5 and the discount; at quantity 10 it names no offer. | SELL-004 | not yet |  |
| SC-OF-004 | Positive | FA | Offer | Add condition (Min), Add benefit; Applies at Line. | Conditions and benefits saved; reopening shows them. | INCENT-009 | not yet |  |
| SC-OF-005 | Positive | FA | Buy X get Y | Benefit Buy 10 Get free 2 (Product given away). | Free goods appear as a gift line on the document; the budget (free units) is counted. | INCENT-009, INCENT-013 | not yet |  |
| SC-OF-006 | Positive | FA | Combo | Benefit Set price for a set of products. | The combo price applies when all products are on the document. | INCENT-009 | not yet |  |
| SC-OF-007 | Positive | FA | Day and time conditions | Tick weekdays, set From and Until time. | The offer applies only inside those days and times. | INCENT-010 | not yet |  |
| SC-OF-008 | Positive | FA | Offer funded by a principal | Set Funded by principal and the principal's share. | The share appears in Principal Claims. | INCENT-012 | not yet |  |
| SC-OF-009 | Positive | FA | Active offer | Edit and save a changed percent. | A new revision is made; the grid shows one live row for the group (identity is the version group, not the row). | INCENT-002 | not yet |  |
| SC-OF-010 | Positive | FA | Offer | Press Copy with new dates... Choose new From and Until. | A copy is made with the new dates. | INCENT-011 | not yet |  |
| SC-OF-011 | Positive | FA | Offer | Press Retire (title 'Retire <code>?'), confirm. | Offer no longer applies to new documents; old ones keep it. | INCENT-002 | not yet |  |
| SC-OF-012 | Positive | FS | New order with the offer's conditions met | Raise an order. | The offer shows on the line; one claim is counted only at approval. | INCENT-003 | `pricing_flow_test.dart` | Pass 2026-10-07 |
| SC-OF-013 | Positive | FA | Offers that stack and offers that end the stack | Raise an order meeting BULK5 and BIGORDER. | BIGORDER ends the stack; the figure agrees with the case. | INCENT-004 | not yet |  |
| SC-OF-014 | Positive | FA | Offers with Uses per customer and Total uses | Set Max per customer 1. | A second use by the same customer is refused. | INCENT-013 | not yet |  |
| SC-OF-015 | Negative | FA | New promotion | Save with no Code or no Name. | Checks N1 to N3 hold. Field named. | 09 Screen checks | not yet |  |
| SC-OF-016 | Negative | FA | Code already used | Save a second offer with the same code. | Checks N1 to N3 hold. Message says so. | 09 Screen checks | not yet |  |
| SC-OF-017 | Negative | FA | New promotion | Until before From. | Checks N1 to N3 hold. Dates named. | 09 Screen checks | not yet |  |
| SC-OF-018 | Negative | FA | New promotion | % off over 100, negative, or Buy 0 Get 0. | Checks N1 to N3 hold. Message names the limit. | INCENT-009 | not yet |  |
| SC-OF-019 | Negative | FA | New promotion | No benefit added. | Checks N1 to N3 hold. A benefit is required. | 09 Screen checks | not yet |  |
| SC-OF-020 | Negative | FA | Budget (value) 100 already used up | Raise and approve an order that would claim more. | An exhausted offer is not quoted at all; the order line shows no discount; nothing is refused silently. | INCENT-013 | not yet |  |
| SC-OF-021 | Negative | FA | Offer past its Until date | Raise an order. | The offer is not applied. | SELL-004 | not yet |  |
| SC-OF-022 | Negative | FA | Offer needing a coupon | Raise an order without the code. | No offer is applied. | SELL-006 | not yet |  |
| SC-OF-023 | Negative | SM | Two Draft orders racing for the last unit of an offer | Approve both. | The loser is refused by name at approval. | SELL-092 | not yet |  |
| SC-OF-024 | Negative | FA | A typed discount 0 on a line | Save the order. | Every arrangement is refused for that line (zero means refuse; blank takes the offer). | SELL-004 | not yet |  |
| SC-OF-025 | Negative | FA | Typed dialog | Close it. | Discard question. | 09 Screen checks | not yet |  |
| SC-OF-026 | Role | SM | Sales Manager | Open Promotions. | Readable; New promotion, Retire, Copy are absent (no PROMOTION_MANAGE). | 01-ROLES R05 | not yet |  |
| SC-OF-027 | Role | FS | Field Sales | Look for Promotions. | Not offered; the offer still shows on the order line. | 01-ROLES R04 | not yet |  |
| SC-OF-028 | Role | FA | Firm Administrator | Open Promotions. | All buttons offered. | 01-ROLES R01 | not yet |  |
| SC-OF-029 | Role | RO | Read Only | Open Promotions. | Readable; no write buttons. | 01-ROLES R11 | not yet |  |
| SC-OF-030 | Multi-user | FA, FS, SM | FA saves an offer; FS raises an order; SM approves it | Each opens in turn. | FS sees the discount; SM's approval counts the claim; FA's grid shows Claimed go up. | INCENT-003 | not yet |  |
| SC-OF-031 | Multi-user | FA and FM | Same offer open twice | Both save. | Second told the record changed; typing kept. | INCENT-002 | not yet |  |
| SC-OF-032 | Multi-user | FA | Two sessions with the list open | A retires an offer; B refreshes. | B no longer shows it live. | INCENT-002 | not yet |  |

## CP. Coupons

**Where and who.** Settings > Set up > Pricing > Promotions, tab or button Coupons (New coupon, Generate codes, Export codes). Offered with Promotions: FA, FM, RO.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-CP-001 | Positive | FA | An offer exists (coupon-only WELCOME) | On Promotions press New coupon. Code, Offer, Live from, Live until, Per customer, Total claims allowed, Status Active. Save. | Coupon saved and listed with its offer. | INCENT-011 | `pricing_flow_test.dart` | Pass 2026-10-07 |
| SC-CP-002 | Positive | FA | Offer | Press Generate codes. Prefix, How many 20, Offer, dates. Generate. Save as CSV. | Twenty unique codes are listed and a CSV file is saved. | INCENT-011 | not yet |  |
| SC-CP-003 | Positive | FA | Coupons | Press Export codes and choose the offer ('Export the codes of which offer?'). | A file of the offer's codes is produced. | INCENT-011 | not yet |  |
| SC-CP-004 | Positive | FS | Coupon WELCOME10 | Type it in Coupon on a new quotation, order or bill. | The offer's benefit shows on the lines; the code reaches the offer. | SELL-006 | not yet |  |
| SC-CP-005 | Positive | FA | A coupon | Make it Inactive or Draft; try it on an order. | Not applied. | SELL-006 | not yet |  |
| SC-CP-006 | Positive | FA | Coupon with Total claims 1 | Use it on an approved order, then on another. | The second use is refused or gives nothing. | INCENT-013 | not yet |  |
| SC-CP-007 | Positive | FA | Offer funded by coupon only | Look at Promotions row. | The offer shows 'Only with a coupon'. | SELL-004 | not yet |  |
| SC-CP-008 | Negative | FA | New coupon | Save with no Code or no Offer. | Checks N1 to N3 hold. Field named. | 09 Screen checks | not yet |  |
| SC-CP-009 | Negative | FA | Code already used | Save a second coupon with the same code. | Checks N1 to N3 hold. Message says so. | 09 Screen checks | not yet |  |
| SC-CP-010 | Negative | FA | New coupon | Live until before Live from. | Checks N1 to N3 hold. Dates named. | 09 Screen checks | not yet |  |
| SC-CP-011 | Negative | FA | Generate dialog | How many 0, or an enormous number. | Checks N1 to N3 hold. Message names the limit. | INCENT-011 | not yet |  |
| SC-CP-012 | Negative | FS | Unknown code | Type NOSUCH on an order. | Gives nothing and refuses nothing. | SELL-006 | not yet |  |
| SC-CP-013 | Negative | FS | Expired coupon | Type it on an order. | Gives nothing; the notice says it has expired or nothing is shown (to be established). | SELL-006 | not yet |  |
| SC-CP-014 | Negative | FS | Coupon with Per customer 1 already used by Vijaya | Use it again for Vijaya. | Not applied. | INCENT-013 | not yet |  |
| SC-CP-015 | Negative | FS | Exhausted coupon | Use it. | Not applied; no silent repricing. | INCENT-013 | not yet |  |
| SC-CP-016 | Negative | FA | Typed dialog | Close it. | Discard question. | 09 Screen checks | not yet |  |
| SC-CP-017 | Role | FA | Firm Administrator | Open Coupons. | All buttons offered. | 01-ROLES R01 | not yet |  |
| SC-CP-018 | Role | SM | Sales Manager | Look for Coupons. | Readable at most; New coupon and Generate absent. | 01-ROLES R05 | not yet |  |
| SC-CP-019 | Role | FS | Field Sales | Type a coupon on an order. | Allowed; creating coupons is not offered. | 01-ROLES R04 | not yet |  |
| SC-CP-020 | Role | RO | Read Only | Open Coupons. | Readable; no write buttons. | 01-ROLES R11 | not yet |  |
| SC-CP-021 | Multi-user | FA, FS | FA creates a coupon; FS uses it | FS types the code on a new order. | The offer applies; FA's grid shows the claim after approval. | SELL-006 | not yet |  |
| SC-CP-022 | Multi-user | FS and FS2 | Both use the last claim of a coupon | Both approve. | The loser is refused by name. | SELL-092 | not yet |  |

## LY. Loyalty

**Where and who.** Settings > Set up > Pricing > Loyalty (Masters area). Offered to FA, FM, SM (LOYALTY_VIEW and LOYALTY_MANAGE), RO. Scheme settings need LOYALTY_MANAGE_SETTINGS (SM does not hold it).

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-LY-001 | Positive | FA | Loyalty scheme on: 2 points per 100; Vijaya has earned points | Open Loyalty. Choose the customer (loyalty-customer box). | The customer's points and a ledger with Points, On, Against, Expires, Why, Worth. | INCENT-005 | `pricing_flow_test`: loyalty: opens and shows a customer's points |  |
| SC-LY-002 | Positive | FA | Loyalty screen | Press Scheme settings. | Dialog 'Loyalty scheme': Scheme is running, A point is worth, Minimum to redeem, Points earned, Points expire, Expire after. | INCENT-005 | not yet |  |
| SC-LY-003 | Positive | FA | Customer with points | Raise a bill and set points to be used (spend points on a bill). | The bill is settled by points: the supply is worth its full value and tax stands. | INCENT-005 | not yet |  |
| SC-LY-004 | Positive | SM | Customer with points | Press Adjust points. Customer, Points 50, Reason. Record adjustment. | The ledger shows the adjustment; balance rises. | INCENT-005 | not yet |  |
| SC-LY-005 | Positive | SM | A bill paid partly by points, then cancelled | Cancel the bill; or use Put points back. | Points are put back in the ledger. | INCENT-016 | not yet |  |
| SC-LY-006 | Positive | FA | Batch of points past its date | Press Expire lapsed. | Lapsed points leave what is left of their batch, shown in the Lapsed column. | INCENT-017 | not yet |  |
| SC-LY-007 | Positive | FA | An offer with Times the usual points 2 | Bill under that offer. | Bonus points are earned. | INCENT-010 | not yet |  |
| SC-LY-008 | Positive | CS | Walk-in bill | Bill the Cash sale customer. | No points earned; the bill files as B2C. | SELL-045 | not yet |  |
| SC-LY-009 | Negative | SM | Customer with 100 points | Spend 150 points on a bill. | Refused in words: more than held; editor stays open; nothing saved. | INCENT-005 | not yet |  |
| SC-LY-010 | Negative | SM | Minimum to redeem 100 | Spend 40. | Refused: below the minimum. | INCENT-005 | not yet |  |
| SC-LY-011 | Negative | SM | Points expired yesterday | Try to spend them. | Refused: points past their date cannot be spent. | INCENT-017 | not yet |  |
| SC-LY-012 | Negative | SM | Adjust dialog | Points 0 or empty, no Reason. | Dialog open; field named; nothing saved. | INCENT-005 | not yet |  |
| SC-LY-013 | Negative | SM | Adjust dialog | Take away more than the balance. | Refused in words. | INCENT-005 | not yet |  |
| SC-LY-014 | Negative | FA | Scheme settings | A point worth 0 or negative; Expire after negative. | Refused in words. | INCENT-005 | not yet |  |
| SC-LY-015 | Negative | SM | Loyalty off for the firm | Open Loyalty. | A message says the scheme is off, or nothing earned yet is shown. | INCENT-005 | not yet |  |
| SC-LY-016 | Negative | SM | Typed dialog | Close it. | Discard question. | INCENT-005 | not yet |  |
| SC-LY-017 | Role | SM | Sales Manager | Open Scheme settings. | Not offered or refused (no LOYALTY_MANAGE_SETTINGS: deciding what a point is worth is not theirs). Adjust points offered. | 01-ROLES R05 | not yet |  |
| SC-LY-018 | Role | FS | Field Sales | Look for Loyalty. | Not offered; the screen says 'You cannot see this' if reached. | 01-ROLES R04 | not yet |  |
| SC-LY-019 | Role | RO | Read Only | Open Loyalty. | Readable; Adjust points and Scheme settings absent. | 01-ROLES R11 | not yet |  |
| SC-LY-020 | Multi-user | SM, CS | CS bills; SM opens Loyalty | SM looks at the customer. | SM sees the points CS's bill earned. | INCENT-005 | not yet |  |
| SC-LY-021 | Multi-user | SM and SM2 | Both spend the last 100 points on different bills | Approve both. | The loser is refused: more points than held. | INCENT-005 | not yet |  |

## CM. Commission rules and payouts

**Where and who.** Sell > All Sell screens > Incentives > Commission, tabs Rates and Payouts. Offered to FA, FM, AC (COMMISSION_MANAGE and COMMISSION_PAY), SM (view only), RO. A role holding MANAGE without PAY is a hired job template: no seeded role is one.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-CM-001 | Positive | FA | Fixture firm with a salesman | Open Commission, tab Rates. | Grid with Applies to, On, Rate, In force from, Until, Status; buttons Add rule, Add slab, Refresh. | INCENT-006 | not yet |  |
| SC-CM-002 | Positive | FA | Commission page | Add rule. Applies to the salesman; Rate 3; In force from today. Save. | Rule appears in the grid as Active. | INCENT-006 | `pricing_flow_test.dart` | Pass 2026-10-07 |
| SC-CM-003 | Positive | FA | Rule | Add slab: From, To, Rate; set Rate shape and 'How the slabs read'. | A rule with slabs ignores its flat percentage; the screen shows slabs only, never both. | INCENT-006 | not yet |  |
| SC-CM-004 | Positive | FA | Rule | Set 'Earns nothing below', 'Extra when the target is met', 'Most this pays per period'. | Saved; a ladder's floor is a round number. | INCENT-006 | not yet |  |
| SC-CM-005 | Positive | AC | Collected invoices in the period | Open Payouts, press Accrue period; choose From and To. | A payout per salesman appears with Earned, Collected, Payable; amounts agree with the report 'Collected <from> to <to>'. | INCENT-007 | not yet |  |
| SC-CM-006 | Positive | AC | Payout in Draft | Press Adjust. Adjustment, Reason. Save. | The adjustment is recorded; payable changes. | INCENT-007 | not yet |  |
| SC-CM-007 | Positive | FA | Payout in Draft | Press Approve. | Payout approved; journal accrues the expense; the figure is snapshotted and never re-read. | INCENT-007 | not yet |  |
| SC-CM-008 | Positive | AC | Approved payout | Press Pay. Paid on, Paid from (Cash or Bank), Notes. Record payment. | Payout Paid; payment journal posted with a distinct reference. | INCENT-007 | not yet |  |
| SC-CM-009 | Positive | FA | Draft or Approved payout | Press Cancel. | Payout Cancelled; the accrual reverses. | INCENT-007 | not yet |  |
| SC-CM-010 | Positive | AC | Collected period, margin rule | Look at a line with no dispatch behind it. | It contributes nothing (NULL cost is not zero cost). | INCENT-006 | not yet |  |
| SC-CM-011 | Positive | AC | Everything sold versus Collected | Switch the view and press Show. | Both views list their invoices and agree with the earned total. | INCENT-006 | not yet |  |
| SC-CM-012 | Negative | FA | Add rule | Rate empty, 0 or negative. | Checks N1 to N3 hold. Message names the rate. | INCENT-006 | not yet |  |
| SC-CM-013 | Negative | FA | Add rule | Until before In force from. | Checks N1 to N3 hold. Dates named. | INCENT-006 | not yet |  |
| SC-CM-014 | Negative | FA | Slabs | Slabs that overlap or leave a gap. | Checks N1 to N3 hold. Message names the slab. | INCENT-006 | not yet |  |
| SC-CM-015 | Negative | AC | Payout exists for the period | Accrue the same or an overlapping period for the same person. | Refused naming the existing payout (one live payout per person per overlapping period). | INCENT-007 | not yet |  |
| SC-CM-016 | Negative | AC | Accrue dialog | To before From; no period chosen. | Checks N1 to N3 hold. 'Choose a period' shown. | INCENT-007 | not yet |  |
| SC-CM-017 | Negative | AC | Period with no collections | Accrue. | Nothing is accrued; the empty state says 'Nothing was collected in this period'. | INCENT-007 | not yet |  |
| SC-CM-018 | Negative | AC | Draft payout | Press Pay before it is approved. | Refused or Pay not offered; only an approved payout can be paid. | INCENT-007 | not yet |  |
| SC-CM-019 | Negative | AC | Paid payout | Press Pay again, or Cancel. | Refused: already paid. | INCENT-007 | not yet |  |
| SC-CM-020 | Negative | AC | Pay dialog | Paid on in the future; no account chosen. | Refused in words. | INCENT-007 | not yet |  |
| SC-CM-021 | Negative | AC | Adjust dialog | Adjustment with no Reason. | Dialog open; Reason named. | INCENT-007 | not yet |  |
| SC-CM-022 | Negative | FA | Typed dialog | Close it. | Discard question. | INCENT-006 | not yet |  |
| SC-CM-023 | Role | Clerk (hired from a Firm Manager clone with COMMISSION_MANAGE and no COMMISSION_PAY) | A user whose role states payouts and cannot pay | Open Commission, state and approve a payout, look for Pay. | Pay is absent, or refused with the permission message: whoever states a debt must not move the cash. | INCENT-008 | not yet |  |
| SC-CM-024 | Role | SM | Sales Manager (COMMISSION_VIEW only) | Open Commission. | Rates and payouts readable; Add rule, Accrue, Approve, Pay absent. | 01-ROLES R05 | not yet |  |
| SC-CM-025 | Role | FS | Field Sales | Look for Commission. | Not offered. 'You cannot see commission' if reached. | 01-ROLES R04 | not yet |  |
| SC-CM-026 | Role | AC | Accounts | Open Commission. | Rates, Accrue, Approve, Pay offered (the role holds both codes); result recorded against the matrix. | 01-ROLES R09 | not yet |  |
| SC-CM-027 | Role | RO | Read Only | Open Commission. | Readable; no write buttons. | 01-ROLES R11 | not yet |  |
| SC-CM-028 | Multi-user | FA, AC | FA sets a rule; AC accrues | AC opens Payouts after FA saves. | AC's accrual uses FA's rule. | INCENT-006 | not yet |  |
| SC-CM-029 | Multi-user | Clerk, AC | Clerk approves; AC pays | AC opens Payouts after the Clerk approves. | AC sees the approved payout and pays it. | INCENT-008 | not yet |  |
| SC-CM-030 | Multi-user | AC and AC2 | Both press Pay on one payout | Record in two sessions. | One succeeds; the other is told it is paid; one journal. | INCENT-007 | not yet |  |

## PC. Principal claims (scheme, free goods, expired stock, breakage, price cut)

**Where and who.** Buy > All Buy screens > Money > Principal Claims. Offered to FA, FM, PM, PU, RO (PURCHASE_VIEW). The claim kinds are Schemes, Free goods, Expired stock, Breakage; a price cut is its own claim.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-PC-001 | Positive | PM | Offers funded by a principal were used on approved bills | Open Principal Claims. | Grid with Number, Principal, Period, Status, Total; button New claim on a principal and Claim a price cut on stock in hand. | INCENT-012 | not yet |  |
| SC-PC-002 | Positive | PM | Principal-funded offer used | New claim on a principal. Choose Principal, Period, tick kind Schemes. Preview, then Raise. | Preview lists the lines per kind with totals; Raise saves a claim with a number. | INCENT-012 | not yet |  |
| SC-PC-003 | Positive | PM | Free goods given under a principal's offer | New claim, kind Free goods. | Free goods are claimed from the principal at cost. | INCENT-014 | not yet |  |
| SC-PC-004 | Positive | PM | Expired and broken stock written off | New claim, kinds Expired stock and Breakage. | Lines grouped by kind; totals add up. | INCENT-012 | not yet |  |
| SC-PC-005 | Positive | PM | Stock in hand of a product whose rate fell | Press Claim a price cut on stock in hand. Principal, Add product, Old rate, New rate. Preview. | Preview shows stock, rate difference and total; Raise saves the claim. | INCENT-015 | `pricing_flow_test.dart` | Pass 2026-10-07 |
| SC-PC-006 | Positive | PM | A price cut claim | Change the Old or New rate after the preview. | A 'recalculate' notice appears; the preview must be run again before Raise. | INCENT-015 | not yet |  |
| SC-PC-007 | Positive | PM | A raised claim | Open it. Look at details; carried-forward amounts. | Details, remarks and carried-forward are shown; Print statement is offered. | INCENT-012 | not yet |  |
| SC-PC-008 | Positive | AC | A raised claim | Press Record payment. Amount, Date, Paid into, reference. | The claim shows paid in part or whole; a journal posts. | INCENT-012 | not yet |  |
| SC-PC-009 | Positive | AC | A recorded payment | Press Reverse payment, confirm. | The payment comes off; the claim returns to unpaid. | INCENT-012 | not yet |  |
| SC-PC-010 | Positive | PM | Claim and an open bill from the principal | Press Settle by credit note. Tick the bills, set the date, Save. | The claim is set against the bills; a credit note is raised. | INCENT-012 | not yet |  |
| SC-PC-011 | Negative | PM | New claim | Raise with no principal. | Checks N1 to N3 hold. Principal named ('claim-problem' message). | INCENT-012 | not yet |  |
| SC-PC-012 | Negative | PM | New claim | Raise with no kind ticked, or a period with nothing in it. | Refused or an empty preview saying nothing to claim. | INCENT-012 | not yet |  |
| SC-PC-013 | Negative | PM | Period already claimed | Raise the same principal and period again. | Refused or the lines already claimed are not claimed twice; to be established. | INCENT-012 | not yet |  |
| SC-PC-014 | Negative | PM | Price cut claim | Old rate lower than New rate; negative rates. | Refused in words; nothing saved. | INCENT-015 | not yet |  |
| SC-PC-015 | Negative | PM | Price cut claim | Product with no stock in hand. | Preview says nothing is in stock; Raise is refused. | INCENT-015 | not yet |  |
| SC-PC-016 | Negative | PM | Price cut claim | Press Raise with no product added. | Refused: a product is needed ('pc-empty'). | INCENT-015 | not yet |  |
| SC-PC-017 | Negative | AC | Payment dialog | Amount 0; more than the claim; date in the future. | Refused in words; dialog open. | INCENT-012 | not yet |  |
| SC-PC-018 | Negative | PM | Settle dialog | Total more than the claim; no bill ticked. | Refused in words; 'settle-problem' message. | INCENT-012 | not yet |  |
| SC-PC-019 | Negative | PM | Principal has no open bills | Press Settle by credit note. | 'This supplier has no open bills.' | INCENT-012 | not yet |  |
| SC-PC-020 | Negative | PM | Typed dialog | Close it. | Discard question. | INCENT-012 | not yet |  |
| SC-PC-021 | Role | PU | Purchasing | Open Principal Claims. | Offered (PURCHASE_VIEW); which buttons it holds is to be established from the endpoint codes. | 01-ROLES R07 | not yet |  |
| SC-PC-022 | Role | PM | Purchase Manager | Open Principal Claims. | Offered with raise and settle. | 01-ROLES R08 | not yet |  |
| SC-PC-023 | Role | AC | Accounts | Look for the screen. | Offered only if PURCHASE_VIEW is held; recording payment needs a payment code. | 01-ROLES R09 | not yet |  |
| SC-PC-024 | Role | RO | Read Only | Open Principal Claims. | Readable; no write buttons. | 01-ROLES R11 | not yet |  |
| SC-PC-025 | Multi-user | SM, PM, AC | SM sells under a principal-funded offer; PM claims; AC records the payment | Each opens in turn. | PM's preview includes SM's sales; AC sees PM's claim and pays it. | INCENT-012 | not yet |  |
| SC-PC-026 | Multi-user | PM and PM2 | Both raise a claim for the same principal and period | Raise in two sessions. | The second is refused or the figures do not double count. | INCENT-012 | not yet |  |

## SS. Supplier schemes (buy so many, get so many free)

**Where and who.** Buy > All Buy screens > Documents > Supplier schemes. Offered to FA, FM, PM, PU (SUPPLIER_SCHEME_VIEW and SUPPLIER_SCHEME_MANAGE), RO.

| Id | Kind | User (role) | Before (data needed) | Steps on screen | Expected on screen | Book case | Automated in | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SC-SS-001 | Positive | PU | Supplier and product exist | Open Supplier schemes. | Grid with Scheme, Supplier, Product, Free product, Valid from, Valid to, Status; filters All suppliers and Active/All/Switched off. | BUY-066 | not yet |  |
| SC-SS-002 | Positive | PU | Supplier and product | New scheme. Supplier, Product, Buy quantity 10, Free quantity 2, Valid from, Valid to. Save. | Scheme appears as Active. | BUY-066 | not yet |  |
| SC-SS-003 | Positive | PU | Scheme 10+2 | New purchase order for that product, quantity 10. | Free quantity 2 fills on the line. | BUY-066 | not yet |  |
| SC-SS-004 | Positive | PU | Scheme giving another product | Set Free product to a different product. | A gift line is added to the order. | BUY-068 | not yet |  |
| SC-SS-005 | Positive | PU | Scheme | Switch Active off, Save. | It shows Switched off and no longer fills orders. | BUY-066 | not yet |  |
| SC-SS-006 | Positive | PU | Scheme with Valid to | Press the clear-date control. | Valid to is emptied and the scheme runs open ended. | BUY-066 | not yet |  |
| SC-SS-007 | Positive | PU | Scheme | Delete: confirm 'Delete scheme <label>' with Delete. | The scheme is removed; Keep leaves it. | BUY-069 | not yet |  |
| SC-SS-008 | Positive | PU | Order with a typed free quantity | Type a free quantity different from the scheme's. | The typed value is kept. | BUY-067 | not yet |  |
| SC-SS-009 | Negative | PU | New scheme | Save with no Supplier or no Product. | Checks N1 to N3 hold. Field named ('ss-problem'). | BUY-069 | not yet |  |
| SC-SS-010 | Negative | PU | New scheme | Buy quantity 0 or Free quantity 0. | Checks N1 to N3 hold. Quantity more than zero. | BUY-067 | not yet |  |
| SC-SS-011 | Negative | PU | Scheme on the same product | Save a second scheme for the same supplier and product with overlapping dates. | Checks N1 to N3 hold. 'Two schemes on one product cannot overlap.' | BUY-069 | not yet |  |
| SC-SS-012 | Negative | PU | New scheme | Valid to before Valid from. | Checks N1 to N3 hold. Dates named. | BUY-069 | not yet |  |
| SC-SS-013 | Negative | PU | Order line | Type a free quantity of 0 on a scheme line. | The scheme is refused for that line. | BUY-067 | not yet |  |
| SC-SS-014 | Negative | PU | Expired scheme | New order after Valid to. | The scheme does not apply. | BUY-066 | not yet |  |
| SC-SS-015 | Negative | PU | Typed dialog | Close it. | Discard question. | BUY-069 | not yet |  |
| SC-SS-016 | Role | PU | Purchasing | Open Supplier schemes. | Offered with New, edit, Delete (SUPPLIER_SCHEME_MANAGE). | 01-ROLES R07 | not yet |  |
| SC-SS-017 | Role | PM | Purchase Manager | Open it. | Offered with the same buttons. | 01-ROLES R08 | not yet |  |
| SC-SS-018 | Role | WH | Warehouse | Look for it. | Not offered. | 01-ROLES R06 | not yet |  |
| SC-SS-019 | Role | RO | Read Only | Open it. | Readable; no write buttons. | 01-ROLES R11 | not yet |  |
| SC-SS-020 | Multi-user | PU, PM | PU saves a scheme; PM raises an order | PM starts a new order. | PM's line shows the free quantity PU's scheme gives. | BUY-066 | not yet |  |
| SC-SS-021 | Multi-user | PU and PM | Same scheme open twice | Both save. | Second told the record changed; typing kept. | BUY-069 | not yet |  |

# Coverage

| Feature | Prefix | Positive | Negative | Role | Multi-user | Total | Automated now |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Selling: Quotations | SC-QT | 15 | 11 | 4 | 2 | 32 | 6 |
| Selling: Sales orders | SC-SO | 16 | 13 | 4 | 3 | 36 | 3 |
| Selling: Delivery notes | SC-DN | 12 | 11 | 4 | 3 | 30 | 3 |
| Selling: Sales bills (sales invoices, including the counter bill) | SC-SB | 15 | 17 | 5 | 4 | 41 | 2 |
| Selling: Proforma | SC-PF | 7 | 6 | 3 | 2 | 18 | 0 |
| Selling: Receipts | SC-RC | 11 | 11 | 5 | 3 | 30 | 1 |
| Selling: Customer credits (advances and credit set against a bill) | SC-CC | 5 | 6 | 3 | 2 | 16 | 0 |
| Selling: Sales returns | SC-SR | 8 | 11 | 3 | 3 | 25 | 2 |
| Selling: Credit notes (and customer debit notes) | SC-CN | 8 | 9 | 4 | 2 | 23 | 0 |
| Buying: Purchase orders | SC-PO | 17 | 14 | 5 | 4 | 40 | 4 |
| Buying: Goods receipts | SC-GR | 11 | 11 | 5 | 3 | 30 | 1 |
| Buying: Supplier bills (purchase invoices) | SC-PB | 13 | 15 | 5 | 3 | 36 | 2 |
| Buying: Payments | SC-PY | 10 | 9 | 5 | 3 | 27 | 1 |
| Buying: Supplier credits (credit set against a bill, and supplier refunds) | SC-SCR | 6 | 6 | 3 | 2 | 17 | 0 |
| Buying: Purchase returns | SC-PR | 9 | 12 | 4 | 3 | 28 | 2 |
| Buying: Debit notes (to a supplier) | SC-DB | 8 | 8 | 4 | 2 | 22 | 0 |
| Pricing: Price lists | SC-PL | 11 | 10 | 4 | 3 | 28 | 2 |
| Pricing: Price levels and customer groups | SC-LV | 9 | 6 | 4 | 2 | 21 | 0 |
| Pricing: Product price revisions (new rates from a date) | SC-RV | 6 | 5 | 3 | 2 | 16 | 0 |
| Pricing: Offers (promotions) with budgets | SC-OF | 14 | 11 | 4 | 3 | 32 | 2 |
| Pricing: Coupons | SC-CP | 7 | 9 | 4 | 2 | 22 | 1 |
| Pricing: Loyalty | SC-LY | 8 | 8 | 3 | 2 | 21 | 1 |
| Pricing: Commission rules and payouts | SC-CM | 11 | 11 | 5 | 3 | 30 | 1 |
| Pricing: Principal claims (scheme, free goods, expired stock, breakage, price cut) | SC-PC | 10 | 10 | 4 | 2 | 26 | 1 |
| Pricing: Supplier schemes (buy so many, get so many free) | SC-SS | 8 | 7 | 4 | 2 | 21 | 0 |
| **All features (25)** | | **255** | **247** | **101** | **65** | **668** | **35** |

"Automated now" counts cases whose Automated in column names a flow step. Those
flows are positive paths only; every Negative, Role and Multi-user case is "not
yet" and is the next work for the click tests.

# No screen

No feature in the requested list was dropped: each has a phase 2 screen. Four
have no screen **of their own**, which matters for where a click test starts:

- **Counter bill.** It is the Sales Invoices editor with **Counter sale** ticked
  (scan field, Received now, tenders); shifts are on **Counter Shifts**. Cases are
  under Sales bills (SC-SB).
- **Customer credits.** The **Customer credits** chip on Receipts (SC-CC).
- **Supplier credits and supplier refunds.** The chips on Payments (SC-SCR).
- **Product price revisions.** The **New rates from...** section of the product
  editor under Masters > Products (SC-RV).
- **Coupons.** Buttons **New coupon**, **Generate codes**, **Export codes** on the
  Promotions screen (SC-CP).

Screens found in `menu_layout.dart` that this book does not cover because they are
outside buying, selling and pricing: Enquiries, Approvals, Collection Sheet,
Payment Promises, Customer Rebates, Targets, Beat Plans, Requisitions, RFQs, Rate
contracts, Bills of entry, Quality Inspection, Landed Costs, Supplier Rebates,
and the stock and accounts areas. Several of them are touched inside a case
(for example Collection Sheet in SC-RC-011) but have no section of their own yet.
Purchase Analytics and Branch and Warehouse Settings are deliberately not offered
in the menu (`MenuLayout.notOffered`).

# Open questions

Expected results that could not be established from the code and are marked
"to be established on the first run" or "wording on first run" in the cases:

1. **Wording of refusals.** The exact text of most refusals (missing customer,
   quantity zero, over-delivery, over-billing, over-return, future date, closed
   period) was not read from the services. The cases say what must be named; the
   first run records the real text and this book is then updated.
2. **Over-delivery and over-receipt.** Whether a delivery note or goods receipt
   above what is still owed is refused outright or allowed inside a tolerance
   (SC-DN-013, SC-GR-013).
3. **Over-payment of a supplier bill from the Payments screen.** BUY-037 says
   Pay now at approval refuses more than the bill. Whether the Payments screen
   refuses, or books the excess as a supplier advance the way an over-receipt
   becomes a customer advance, was not established (SC-PY-012).
4. **Short stock at approval.** Whether approving a sales order for more than the
   stock refuses, or reserves what exists (SC-SO-020).
5. **Credit control.** The default warns (80 percent) and never blocks, per the
   chain rules. The cases assume the warning is a notice with figures; the exact
   desktop notice was not read (SC-SO-022, SC-SB-031).
6. **Price floor and discount limits.** Whether a below-floor rate is refused or
   sent for approval, and what a Field Sales user (no SALES_PRICE_OVERRIDE) sees
   (SC-QT-030, SC-SB-030, SC-PL-020).
7. **Sales Manager and a customer's price level.** The brief says a Sales Manager
   cannot change it. The role seed withholds CUSTOMER_MANAGE_SETTINGS and
   SALES_PRICE_OVERRIDE from SALES_MANAGER, but which code guards the customer
   editor's Price level field was not found. SC-LV-016 records what happens.
8. **Which screens each role is offered.** Field Sales and Warehouse and Delivery
   Notes; Accounts and Debit Notes, Principal Claims and Payables; Cashier and the
   customer picker (the Cashier role holds no CUSTOMER_VIEW, so the receipt
   dialog's customer box may be empty). Each is to be matched to
   `01_ROLES_AND_ACCESS.md`.
9. **Edit rights of Field Sales.** FS holds SALES_QUOTATION_CREATE, SALES_ORDER_CREATE
   and SALES_INVOICE_CREATE but not SALES_UPDATE; whether FS may reopen and edit
   its own Draft was not established.
10. **Principal claims codes.** The screen needs PURCHASE_VIEW. Which code guards
    Raise, Record payment and Settle was not read; so PU, AC and RO button
    expectations are loose (SC-PC-021 to SC-PC-024).
11. **Commission separation.** AC holds both COMMISSION_MANAGE and COMMISSION_PAY,
    so the "whoever states cannot pay" case needs a hired Clerk role (SC-CM-023).
    Whether the firm wants a seeded role that holds MANAGE without PAY is a
    decision for the owner.
12. **Expired quotation and expired coupon.** Whether converting an expired
    quotation is refused, and whether an expired coupon shows a notice or nothing
    (SC-QT-024, SC-CP-013).
13. **Withdrawing a price list or retiring an offer while a Draft uses it.**
    Whether the Draft keeps its price or is re-priced at approval (SC-PL-028).
14. **Cancel with something resting on it.** The wording and whether the screen
    blocks the button or the server refuses after the click (orders with notes,
    notes with bills, bills with receipts or returns, receipts with bills, bills
    with payments).
15. **Flows not yet pushed.** The click flows were read from
    `origin/test/desktop-flows-buy-sell-price`. Automated-in step names are those
    in that branch at the time of writing and must be rechecked after it merges.
