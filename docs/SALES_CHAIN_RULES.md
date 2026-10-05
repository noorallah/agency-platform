# The sales chain — documents, stages and what may be skipped

These rules were in `CLAUDE.md` until 2026-09-15, when that file passed the
150k-character limit that keeps it loadable in one context window. Nothing
was cut -- the prose is verbatim and the imperative half of each rule stays
in `CLAUDE.md` with a pointer here. Every one was written from a defect that
actually happened, so the story beside the rule is the part that says why it
is the rule.

`docs/SALES_TO_RECEIPT_FLOW.md` is the walkthrough; these are the rules the
chain enforces.

## An enquiry comes before the chain, and a prospect is not a customer

SEL-10 (A133). An enquiry records who asked and what for; it raises nothing. A prospect becomes a customer only when the enquiry is converted to a quotation, and the customer and the quotation are staged together and committed once -- a refused quotation leaves no stray customer. The quotation becoming an order marks the enquiry won.

## Document lines are reconciled on their line number

**Document lines are reconciled on their line number, not deleted and re-inserted**, in `sales_order`, `purchase`, `goods_receipt` and `delivery_note`. Downstream documents record `source_document_line_id` as a bare UUID with **no foreign key**, so re-inserting lines silently left those references dangling. The three invoice modules still re-insert; their lines are terminal.

## A hold on a sales order is a flag, not a status

**A hold on a sales order is a flag, not a status.** An order that is
PARTIALLY_DELIVERED can be held, and releasing it has to put it back to
PARTIALLY_DELIVERED -- writing HOLD into `status` would destroy the only
record of how far the order had got and the release would have to guess.
Nothing is overwritten, so nothing has to be restored; it is the same
reasoning `update_order` was repaired on. **The stock stays reserved** --
holding says "not yet", not "never", and releasing the goods would let
another order take them while this one waits; cancelling is what gives stock
back. The refusal lives in `DeliveryNoteService.stage_note` rather than
`create_note`, so `SalesChainService` is covered by the same line, and it
**names the reason** because whoever hits it is the one who has to get the
hold lifted. A hold is an operational stop, **not a credit control** -- that
is `credit_control_settings`, which acts at approval.

## A line whose whole content is a gift is not a line that has been billed

**A line whose whole content is a gift is not a line that has been billed.**
Nothing charged, goods supplied free -- the shape a "buy ten of this, get
two of that" offer needs. Such a line has a remaining quantity of zero from
the moment it is written, and three separate places read that as *fully
billed*: the note-level filter in `billable_documents` hid the whole note,
`_billable_line` dropped the line, and `_invoice_free_quantity` pro-rated
the gift by a charged share of zero and returned nothing. So the goods left
the warehouse and the document the customer reads was silent about them --
the same fault the ordinary case had until 2026-08-23, in the one shape
nobody had tried. Fixed 2026-09-03. **A gift line is owed until an invoice
line references it, counted in rows and never in quantity**: zero minus zero
is zero however many times it has been stated, so the quantity test that
stops an ordinary line being billed twice can never stop this one. Found by
driving a nil-charge line through the chain by hand, which is also the only
way to see it -- every fixture in the suite billed a line that charged for
something.

## A line of nothing is refused; a bill that comes to nothing approves

**A line of quantity 0 with nothing free is refused with 422** on a sales
order, a delivery note, a bill and a counter bill (D-SELL-53). The order and
note schemas judge it on the request; a note line may also stand on damaged
goods alone. A bill line that names a document is judged in the service,
because only its source says whether it inherits a gift. A gift line --
quantity 0, goods free -- stands on all of them, and a counter bill of free
goods alone raises its order and note like any other.

**A bill whose total is 0 approves** -- every line at a 100% discount, or
goods given free. It puts **no row on the customer's account** and
`post_sales_invoice` writes **no zero journal lines** (a bill whose every leg
is nothing posts no journal at all); the stock and its cost still move with
the dispatch, a tax leg that is not zero still posts, and the note reads
billed. Cancelling such a bill takes nothing off the account. It used to
answer 500 at approval with the goods already gone.

## A draft counter bill's edit raises its order and note again

**After any edit of a draft counter bill, the bill, its note, its order and
the reservation agree** (D-SELL-72, D-SELL-59; `_raise_counter_chain_again`
in `app/sales_invoice/services/sales_invoice_service.py`). A counter bill is
one that raised its own sales order and delivery note; both carry its stamp.
Its edit used to change the bill alone, so a draft cut from 3 to 2 billed 2
and shipped 3, and one could not grow at all.

- **An edit that changes what the bill ships is raised again**: a quantity
  up or down, a line added or left off, free goods, the batches or the
  units. The note and the order are withdrawn -- which gives the reservation
  back, exactly as cancelling the draft does -- and raised again from the
  bill's lines through `SalesChainService`, in the edit's own transaction. A
  refused edit therefore leaves all four as they were.
- **The withdrawn pair's numbers are spent**, and they stay as CANCELLED
  documents saying which bill changed. That was decided, not overlooked:
  amending an approved order and note in place would need both services to
  edit approved documents.
- **An edit that changes what a line charges is raised again too**
  (D-SELL-77, `_charges_as_raised`): a price that is not the note's, or a
  discount stated that is not one the order has typed. It used to change the
  bill alone, and the order and the note kept the old terms -- so the next
  quantity edit, which reads the terms back to raise them again, undid it:
  3 at 5% saved again at 0%, then grown to 4, billed 4 at 5%; 3 at 100 saved
  at 90, then 4 sent with the bill's own 90, billed 4 at 100. The order is
  where a counter bill is priced, so a price belongs there or nowhere.
- **An edit that ships and charges the same raises nothing**: a reference, a
  charge, the money received, the price sent back as the bill returned it.
  The bill is re-priced as any draft is.
- **Lines may be sent either way.** As products, the way a new counter bill
  is; or back by the source fields the bill returns, which are read as the
  same products at the terms **the bill's own line holds**. A price left
  out, or sent back unchanged, is the bill's. A discount stated is typed. A
  discount left out is the bill's where the bill typed it -- a typed zero is
  still a refusal -- then the order's where the order's was typed, and one
  that was the customer's own arrangement is resolved again. A gift an offer
  added is judged afresh on the new quantities. Batches and units are kept
  on a line whose quantity did not move and that names none anew.
- **A draft already out of step is put right by its next edit.** What the
  request leaves out is compared from the bill's line, so a bill saved
  before D-SELL-77 at terms its order does not hold raises the pair again
  whatever the edit says.
- **Only a draft counter bill.** A bill of documents somebody raised is
  still changed through its own lines and refuses a product line by name
  (D-SELL-69); an approved bill is not edited at all.
- **The desktop adds a product beside the saved lines, never in place of
  them** (D-SELL-59; `sales_invoice_editor_phase2.dart`). A saved or recalled
  counter bill is opened as a bill of its lines, and a second table takes the
  products added. The save sends each saved line back by its source fields,
  so the server keeps the terms struck at the first save, and each new
  product as a product line. The saved bill's response does not say whether a
  line's discount was typed or inherited (`discount_source` is stored but not
  returned), so the desktop never rebuilds a saved line as a product line to
  save it: that would turn an inherited discount into a typed one. The live
  preview refuses a mixture of the two shapes, so it alone restates every
  line as a product, through `POST /sales-invoices/preview`, which stages
  and rolls back.

## Goods back before billing credit nothing

**A sales return against a delivery note nobody was billed for moves stock
and cost only** (D-SELL-55, the selling twin of D-BUY-26; `app/sales_return/billing.py`).
No row goes on the customer's account, no output tax is reversed and nothing
is debited to sales returns: the firm charged nothing, so it owes nothing
back. It used to credit the full price -- the customer came out in advance
for goods never billed -- and left the note billable in full.

- **Returned goods are taken first from the unbilled part.** On a note line
  part billed, the return is set against what no bill has charged for --
  delivered, less charged, less earlier returns before billing -- and only
  the rest is a credit note. Four delivered, three billed, two back: one is
  credited. The choice is the buying one (D-BUY-26), and it is the one that
  never credits a customer for goods they were not charged for.
- **The split is decided at completion and stored** on the return line
  (`unbilled_quantity`), cleared when a completed return is cancelled. The
  document keeps its own totals, tax included, as a purchase return before
  billing does (D-BUY-31); `return_billed_amounts` is what the journal and
  the customer's account read.
- **"Billed" is a bill that charged**: approved or closed. A draft has charged
  nothing, so goods returned while one waits are returned before billing,
  and the draft is refused at approval for what came back. A cancelled bill
  leaves its note unbilled again.
- **What came back before billing is not left to bill.** The save and the
  approval of a bill both cap a note line at delivered less billed less
  returned before billing, and `billable_documents` offers the same figure.
- **Every reader of "what did returns credit" reads the billed part**: GSTR-1
  and 3B and the GST sales register leave out a return wholly before billing
  (`credits_a_bill`) and scale a part-billed line; the sales analysis and the
  rebate turnover net off only the billed part; loyalty takes back only what
  a bill earned. The sales-return reports do too (D-SELL-74): the register
  states `credited_amount` beside the document's total, by-customer and
  by-product value a return at what was credited, the summary's
  `total_return_value` is what the live returns credit, and each carries
  `unbilled_quantity` -- the goods back before billing, as a quantity with
  no value.
- **A return on a note names the bill it credits** (D-SELL-75). Where a bill
  charged the note's line, the GST sales register and GSTR-1's CDNR read
  that bill as the return's "against invoice" -- the earliest that stands,
  the one its tax is reversed from.

## A firm chooses which stages of a sale its people type

**A firm chooses which stages of a sale its people type**, per stage, in
`sales_workflow_settings` -- `quotation_stage`, `sales_order_stage`,
`delivery_note_stage`, the invoice always typed. A firm with no row types all
four, so nothing changed for any existing firm. `SalesChainService`
(`app/sales_invoice/services/sales_chain_service.py`) raises whatever is
switched off by driving the same services a person would, so **the documents
are real**: stock still leaves at dispatch and cost of goods sold still
belongs to the delivery note. Making the invoice move stock itself was
rejected deliberately -- it needs a second inventory path in a module that has
never touched stock, and strands `_already_invoiced_quantity` and
`sales_return`'s cap on `current_delivery_quantity`, both keyed off the chain.
A column per stage rather than a mode, because a firm grows: an enum needs a
new value for every combination on that path. The switch governs **new**
documents only, so turning a stage on never strands work in flight.

**A draft bill ships nothing** (D-SELL-13, 2026-09-19). The note the chain
raises for a bill is approved and left waiting; the bill's **approval**
dispatches it, in the approval's own transaction, and costs the bill's lines
from that dispatch. Saving the draft used to dispatch it there and then, so a
draft cancelled a minute later left the stock out, cost of goods sold posted
and the order DELIVERED with nothing billed. Cancelling a draft now cancels
the waiting note it raised, which the invoice records by
`allow_direct_sales_order` -- a record of how the bill was raised, not a
permission. The order a bare bill raised is left APPROVED and is offered again
to bill.

**A bill ships only the note it raised itself** (D-CFG-16, 2026-09-19). The
chain stamps each note it raises with the bill's id
(`delivery_notes.raised_by_sales_invoice_id`), and that stamp -- never the
firm's stage as it stands today -- is what lets a bill name the note before it
is dispatched, dispatch it on approval, and withdraw it when the draft is
cancelled. Reading "the stage is off now" as "this bill raised the note" let a
draft adopt a note a person had raised before the stage was switched off,
skip the dispatched-note check, and cancel that person's note with the draft.
A note a person raised is billed like any other: once dispatched.

**A bill that ships a serial-tracked product names its units** (D-STK-4,
2026-09-19). Dispatch refuses a serial-tracked line that does not name one
serial per unit leaving, and the document that issues the stock is where they
are named -- so a bill that dispatches its own goods carries `serial_ids` on
the line and the chain hands them to the note it raises. A bill naming none is
refused by name in `SalesChainService._refuse_serialised` before anything is
staged. `docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md` has the rest.

## A chain of committing services is not a transaction

**A chain of committing services is not a transaction, and `begin_nested` does
not make it one.** In SQLAlchemy 2.0 `Session.commit()` commits the outermost
transaction and closes the savepoint, so wrapping does nothing -- verified
against this repo's own version rather than assumed. Every step of the sales
chain used to commit, so a failure at invoice approval left an approved order
and a **DISPATCHED** delivery note written: goods gone from the warehouse with
nothing owed for them. The seven methods are now split into `stage_*`
internals that flush and public wrappers that commit -- the shape
`CustomerService.import_customers` has always had. **Compose the `stage_*`
methods and commit once**; the public ones are for a caller that owns nothing
else. That split also made `import_orders`, `import_notes` and
`import_invoices` genuinely atomic: all three said "atomically" in their
docstrings while looping over a committing create.

## A flag the caller sets to permit itself is not a control

**A flag the caller sets to permit itself is not a control.**
`allow_direct_sales_order` was a boolean on the invoice body that let a bill
be raised against a sales order with no delivery note -- and since the invoice
posts no stock and no cost, that reachable state produced revenue with no cost
of goods sold, stock that never left, and a reservation open for ever. It is
now the firm's `delivery_note_stage`, and the column records how a bill was
raised rather than authorising it. Of 147 invoices in the seeded stores, none
carried the flag and all were billed off delivery notes, so nothing needed
migrating.

## A sales order's status follows its deliveries

**A sales order's status follows its deliveries as of 2026-08-23**, the way a
purchase order has followed its receipts since 2026-08-18.
`DeliveryNoteService._resync_order_status` writes `PARTIALLY_DELIVERED` and
`DELIVERED` on dispatch, **derived by summing the notes that have left the
warehouse** rather than incremented -- an incrementing counter and a reversal
are two chances to disagree. Only an order already in the delivering part of
its life is moved. Two traps came with it. The gate on raising a delivery
note compared a **sales order's** status against `DeliveryNoteStatus`
members, which agreed only because both enums spell APPROVED and CLOSED the
same; writing the new status would have made it refuse every second delivery,
so a part-shipped order could never be completed. And the service still lets
a DELIVERED order be cancelled -- true before and invisible, because such an
order read APPROVED -- so the desktop gate lists the new statuses rather than
disabling a button the API accepts. Orders predating the change are not
backfilled, as on the purchase side.

## An invoice is corrected upward by a debit note, not by a second invoice

`app/customer_debit_note` (prefix `SDN`). It names the invoice and its lines,
moves no stock and charges tax at the rate **each line was charged**, because a
tax profile edited in September must not retax a March supply. It has **no
cap** -- a price can rise by whatever is agreed -- so the control is approval,
`CUSTOMER_DEBIT_NOTE_APPROVE`, deliberately not given to the sales manager who
drafts one. What it adds is owed **on the invoice**: receipts allocate to the
invoice, which ages from its own due date. A live debit note stops the invoice
being cancelled, and the note cannot be cancelled once money received on the
invoice has met it.

## Credit limits warn, and block only if a firm asks

**Credit limits warn, and block only if a firm asks.** `customers.credit_limit` constrained nothing until `20260810_0057`. `CreditControlService` compares it against exposure — `current_outstanding - unapplied_advance + the document being saved` — at sales order and sales invoice approval, the two points where credit is committed. Policy is per firm in `credit_control_settings` (`OFF` / `WARN` / `BLOCK`, with warn and block percentages); a firm with no row warns at 80% and never blocks, and a `credit_limit` of zero means unset rather than no credit, so shipping this stopped nobody trading. `GET /api/v1/customers/{id}/credit-status?amount=` answers the question before a document is saved rather than reporting the breach after, and `GET`/`PUT /api/v1/customers/credit-settings` carries the policy. Writing the policy needs `CUSTOMER_MANAGE_SETTINGS`, deliberately **not** granted to `SALES_MANAGER`: the role the limit constrains must not be able to switch it off. **Moving a customer's `credit_limit` needs the same code** (D-CFG-17): raising it, or setting it to zero, lifts a BLOCK as surely as switching the policy off, so `PUT /customers/{id}` refuses a changed limit by name without it and the desktop shows the field read-only; resending the stored figure is not a change, and a new customer's limit is anyone's to set because every customer otherwise starts with none. The desktop **warns and never blocks**: `warnOnCreditExposure` (`desktop/lib/ui/sales/credit_notice.dart`) runs on Approve for sales orders and sales invoices, before the action so the document is not counted twice, and stays silent when `would_block` is true because the server's refusal already carries the same sentence. A client that blocked on its own would enforce a rule the firm may not have chosen and could be bypassed by any other client. The policy itself is edited from the Settings action on the customers workspace (`credit_settings_dialog.dart`), which is readable with `CUSTOMER_VIEW` — someone the policy warns should see the rule behind the warning — and writable only with `CUSTOMER_MANAGE_SETTINGS`.

## A walk-in bill names the cash customer and is paid in full

Backlog §87 #2 (SG-2, 2026-10-05), decided by what Tally, Busy and Marg do: a
counter sells to people who have no customer record, and every such bill is
made out to one built-in party. Each firm has exactly one customer marked
`is_cash_sale` (*Cash sale*), held to one by `UQ_customers_cash_sale_active`.
It is **made the first time a counter asks for it** --
`POST /api/v1/sales-invoices/walk-in-customer`, under the permission that
raises a bill, `app/customers/services/cash_customer.py` -- rather than seeded
with the firm or by a migration: a firm that existed before needs no backfill,
and a migration in a firm store cannot name the firms in it.

- The bill carries `buyer_name` and `buyer_phone`, typed at the counter and
  printed in place of the cash customer's own name. They are refused on a
  bill to any other customer, which has a name of its own.
- **Approval refuses a walk-in bill that is not paid in full**
  (`received_now_amount` or its tenders equal to the total). The cash
  customer is nobody in particular, so nothing may be left owing on it; a
  sale on credit needs a customer record.
- It earns no loyalty points -- they would pool on an account that belongs to
  nobody -- and it is unregistered, which is what places its bills in B2C.
- The customer cannot be deleted, given a credit limit or a GSTIN, or made
  inactive. `is_cash_sale` is not writable through the API.

`tests/unit/test_walk_in_cash_sale.py` holds each rule.

## A counter bill can be held, and a shift is counted against its tenders

Backlog §87 #7 (SG-7, 2026-10-05; server #1165, and the counter screen's Hold,
Recall and shift strip in #1167). Decided by what Tally's POS register, Marg and Busy's
shift closing and ERPNext's POS opening and closing entries do.

**A hold is a flag, not a status** -- the same reasoning as a hold on a sales
order. `sales_invoices.is_held`, with `held_at` and `held_note` (what the
cashier typed to know the bill again), is set by
`POST /api/v1/sales-invoices/{id}/hold` `{note?}` and cleared by
`POST /api/v1/sales-invoices/{id}/recall`. Both are audited, both write a
timeline event, and both run under the scope that edits a draft: whoever
raised the bill, or a holder of `SALES_UPDATE`.

- **Only a draft can be held**, and any draft bill can be -- the flag is not
  limited to bills raised with the stages off.
- **A held bill never posts.** `stage_approval` refuses it ("recall it first"),
  so the single approval, bulk approve and anything composing approval all
  refuse it, each row with that message.
- **A held bill can still be edited.** Recall is not needed to change it; an
  edit leaves the flag and the note alone. Cancelling a held draft clears the
  flag.
- `GET /api/v1/sales-invoices?is_held=true` is the counter's list of parked
  bills (`false` is everything else), and every bill's response carries
  `is_held`, `held_at` and `held_note` -- columns of the row, so the list adds
  no statement per bill.
- **Holding changes nothing about stock.** A counter bill raises and approves
  its own sales order when the draft is saved, and that approval reserves the
  stock; a held bill keeps exactly that reservation, as any saved draft
  counter bill does, and ships nothing until it is approved. The reservation
  is the order's and is released the way it always was. Holding neither adds
  to it nor releases it. **Cancelling the draft releases it**: the order
  carries `raised_by_sales_invoice_id`, as the note does, and the bill's
  cancel withdraws the note and the order it stamped in one transaction
  (D-SELL-54). An order a person raised is left approved.

**A shift is a cashier's till** (`counter_shifts`, `app/counter_shifts`,
`/api/v1/counter-shifts`): a branch, a cashier, a cash account, an opening
float, and at the close a counted amount.

- **One open shift per cashier per firm**, held by the partial unique index
  `UQ_counter_shifts_open_cashier` rather than by a read; the service checks
  first so the refusal (409) names the shift already open. Numbers run
  `SHIFT-000001` per firm, counted from the firm's shifts rather than issued
  by the document framework -- a shift has no lifecycle configuration, and
  `UQ_counter_shifts_number` settles two opened at once.
- **A bill paid at the counter is stamped with the open shift of the cashier
  who made it** (`sales_invoices.counter_shift_id`, set in `stage_approval`,
  in the approval's own transaction) when `received_now_amount` is more than
  zero -- which its tenders make it. The till that took the money is the
  maker's: the counter roles raise bills and hold no approve code, so a
  manager approves them, and stamping the approver's shift left the cashier's
  drawer at its float (D-SELL-51). The approver's own shift takes the bill
  only when its maker has none open. The shift row is locked while it is stamped and
  while it is closed, so no bill lands in a shift after its drawer was counted.
- **Shifts are optional.** Somebody with no open shift is not refused: the
  bill posts as it always did and is stamped with none. A one-person firm that
  counts no drawer is asked for nothing, and one that hires a cashier later
  starts opening shifts the day it wants to.
- **Expected cash is derived, never incremented**: the opening float plus the
  CASH tenders of the shift's bills that are approved or closed and whose
  receipts still stand (a bill with no tenders counts its
  `received_now_amount` by its method -- CASH as cash, BANK as a bank
  transfer). Summed in SQL in four statements however many bills the shift
  took, and a page of shifts costs what one does. Cancelling a bill needs its
  receipts reversed first, and a reversed receipt drops out by itself, so the
  drawer owes less the moment the money is handed back. **There is no counter
  refund tied to a bill in the codebase** (a customer refund returns an
  advance and names no bill), so nothing else is taken off.
- **The close snapshots it.** `POST /api/v1/counter-shifts/{id}/close`
  `{counted_cash, note?}` stores `expected_cash`, `counted_cash` and
  `difference` (counted less expected) and posts the difference to *Cash short
  and over* (`docs/LEDGER_POSTING_RULES.md`). Only the cashier whose till it
  is, or a holder of `SALES_APPROVE`, may close it. Bills the cashier parked
  during the shift and never recalled are reported as `summary.held_bills` --
  a warning, never a refusal: a held bill took no money.
- **Permissions.** Opening, reading and closing one's own till take
  `SALES_INVOICE_CREATE` -- the code a bill is actually raised under
  (D-ROLE-2), not `SALES_CREATE`. The list, one shift and the report
  (`GET /api/v1/counter-shifts/{id}/report`, a PDF) open to `SALES_VIEW`,
  `REPORT_VIEW` or that same create code, so a cashier can print their own.
  No new permission code.

**On the desktop** (#1167): the counter bill has **Hold (F8)**, **Recall** and a
shift strip with **Open shift** and **Close shift**, and Sell > All Sell
screens > Documents > *Counter Shifts* lists the shifts and prints the report.

**Not built:** routing a
shift's cash receipts to a cash account other than the firm's `CASH` control
account -- a receipt books cash there whatever the shift names, so a shift
that names another account posts only its difference against it; a counter
refund against a bill; denominations at the count; handing a shift over to
another cashier; and stamping a bill that took no money at the counter.

`tests/unit/test_counter_hold_and_shifts.py` holds each rule.

## A service rides the chain and moves no stock

Backlog §87 #3 (SG-3, 2026-10-05). A product of type `SERVICE` -- freight,
repair, installation -- is billed with its SAC like any line, but there is
nothing to reserve, ship or take back. `stockless_products`
(`app/products/services/stockless.py`) names the services among a document's
products, once per document, and three places skip the stock half of their
step for those lines:

- **the order** (`_reserve_inventory` / `_release_inventory`) writes no
  reservation movement. The line's `reserved_quantity` is still set to the
  whole quantity, and cleared on cancel, so everything derived from the hold
  reads the line as ready to deliver; the back-order report leaves it out.
- **the delivery note** (`_dispatch_inventory`) writes no movement, picks no
  batch and adds nothing to the cost of goods sold; it lets go of the order's
  nominal hold. A bill of services alone posts no goods-issue journal at all.
- **the sales return** (`complete_return`) credits the customer and puts
  nothing back on a shelf.

**Decided against the plan's first wording**, which refused a service line on
a delivery note and billed it straight from the order. That needs the bill to
take an order line as its source, which `_prepare_invoice_sources` refuses for
the reason recorded above it (revenue with no movement behind it), and a
second way of deriving what is billed. ERPNext carries a non-stock item on a
delivery note with no stock ledger entry, and that is what this does: one
chain, and the stock left out where there is none. A firm that types its
delivery notes sees the service on the note as work delivered; a counter bill
raises the note for itself.

`tests/unit/test_service_invoices.py` drives a service bill, a mixed bill and
a typed order through the real services. The return of a service is covered
only by the zero-movement path the return already had, not by a test of its
own.

## Where the goods go: the ship-to is chosen on the order and inherited

Backlog 67 row 3, 2026-10-01. A customer keeps several addresses, and until
then every order, note and bill printed the customer's one default shipping
address whatever the buyer asked for. Now `shipping_address_id` sits on the
order, the delivery note and the invoice:

- **The order names it**, the customer's default shipping address preselected
  (then any SHIPPING address). None means "the default", never "nowhere".
- **The note inherits the order's**, and the bill inherits the ship-to of the
  notes it bills when they agree. Either may name another of the customer's
  addresses; notes that went to different places leave the bill to the
  customer's default unless a person names one, since a bill prints one
  ship-to. A counter bill hands its ship-to to the order and note the chain
  raises for it, so all three agree.
- **It must be the customer's own live address**
  (`app/customers/services/ship_to.py`); on an update, leaving it out keeps the
  document's own. The challan and the tax invoice print it.
- **Place of supply.** Goods are supplied where their movement ends (IGST Act
  s.10(1)(a)), so for an **unregistered** buyer the ship-to's state is the
  place of supply and decides CGST + SGST against IGST. A **registered** buyer
  keeps its GSTIN's state: shipping to an address the buyer names is
  bill-to-ship-to, s.10(1)(b), supplied at the bill-to person's principal
  place of business -- which is also the only state the buyer's input credit
  can follow. SEZ and OVERSEAS buyers are unchanged. The invoice stamps
  `place_of_supply` as before, now from the same answer
  (`app/tax/services/place_of_supply.py`).

## Payment terms are agreed on the order and the bill inherits them

Backlog 67 row 4, 2026-10-01. `sales_orders.payment_terms` (the words) and
`payment_terms_days` (the days of credit). A new order takes the customer's
days unless it names its own -- 0 is an answer, payment on the bill -- and a
converted quotation brings its words. On an update, leaving either out keeps
the order's own.

The invoice inherits rather than re-reading the customer, which is the same
rule as prices and discounts: a deal struck at 7 days stays 7 days when the
bill is raised, however the customer master has moved since. A bill that
leaves `due_date` blank falls due on the orders' days (several orders: the
earliest -- the stricter promise is the one made), and one that leaves
`payment_terms` blank takes the first order's words. A typed date always
wins. A counter bill is unchanged: the order the chain raises for it takes the
customer's days, so it falls due exactly as it did before.

## The delivery note records how the goods travel

Backlog 67 row 5, 2026-10-01. Beside the vehicle and driver, a note carries
`transporter_name`, `transporter_gstin` (format-checked by `normalize_gstin`
in `app/core/validation/common.py`; a TRANSIN has the same shape),
`transport_mode` (ROAD / RAIL / AIR / SHIP), `lr_number` / `lr_date` (the
lorry receipt or docket) and `distance_km` -- what Part B of an e-way bill
asks for. On an update, leaving any out keeps the note's own. They are not
gated on VEHICLE_TRACKING the way vehicle and driver are: every firm that
moves goods over the e-way bill threshold needs them.

The challan prints them, and an e-way bill raised for an invoice takes
whatever the person leaves blank -- distance, mode, transporter, vehicle --
from the latest delivery note the invoice billed, and sends its LR as
`TransDocNo` / `TransDocDt`. A distance is still required from one or the
other.

### The carrier is chosen from a master, and the note still owns it

Backlog §87 #5 (SG-5, 2026-10-05). `transporters` keeps each carrier once --
name, GSTIN, the TRANSIN an unregistered carrier enrols for, phone, usual mode
-- under `/api/v1/delivery-notes/transporters`
(`app/delivery_note/services/transporters.py`; read with `SALES_VIEW`, kept
with `SALES_UPDATE`). A note names one with `transporter_id`, and
`_apply_transporter` **copies** the name, the GSTIN or TRANSIN and the mode
into the note's own columns wherever the request left them blank. The challan
and the e-way bill go on reading the note, so:

- what is typed on the note wins over the master, for a one-off;
- editing or removing a carrier rewrites no note already raised, which is why
  removing one is never refused;
- an edit that does not mention the carrier keeps it; naming another takes
  that one's details; an inactive carrier is refused by name.

`freight_terms` on the note is PAID, TO_PAY or TO_BE_BILLED -- who pays the
carrier -- and prints on the challan as *Freight*. It records the term and
moves no money: freight charged to the customer is still the bill's
`freight_amount`. Migration `20261005_0320`;
`tests/unit/test_transporter_master.py`.

## Goods leave with an invoice, or on a challan that says why

Every delivery note carries a **reason** (`challan_reason`: Sale by default;
van or route sale, on approval, quantity not known, job work, other with the
firm's own words). It prints on the challan and decides whether dispatch is
judged. A tax invoice is issued at or before removal of goods (CGST s.31), so
a `SALE` note dispatched with no approved invoice is judged by the firm's
`dispatch_without_invoice` policy: `OFF`, `WARN` (the default; the warning is
kept on the dispatch event and the audit row) or `BLOCK`. A van or route sale
is judged only if the firm switches on *route sales need the invoice first*;
the other reasons leave on a challan and are billed later, one invoice for
several notes if need be. The firm chooses because CAs differ.

**A bill that dispatches the note it raised is never judged** -- the invoice is
what ships it. **Dispatch and invoice** is the compliant one-click path: it
dispatches, raises the bill of the whole note and approves it in one
transaction, so the invoice exists when the goods leave, and if the bill's own
approval refuses nothing is dispatched either. Both live in the delivery
note's service, not the client, so no other client can skip them.

## A note is delivered only with a proof -- and delivered is a flag

Backlog 67 row 6, 2026-10-01. `POST /api/v1/delivery-notes/{id}/proof-of-delivery`
records when the goods were received (`delivered_at`), who received them,
remarks and optionally a photo or signature (kept with the note's attachments
as `PROOF_OF_DELIVERY`). It needs `SALES_UPDATE`: it records what the signed
paper shows, and the clerk filing it is not the person who approves sales.

**Delivered is a flag beside the status, not a status**, for the reason a
hold is: DISPATCHED and COMPLETED both mean "the goods left" to billing,
returns, the order's progress and every report, and a DELIVERED status
between them would have to be taught to each of those readers without
changing anything they decide. A note is delivered when `delivered_at` is
set, and only a proof sets it. Recording a proof on a DISPATCHED note also
completes it -- the confirmation of receipt that completing always meant; a
note completed earlier without one is still "not yet delivered". The proof
cannot predate the note or lie in the future, and may be recorded again to
correct it (audited as `delivery_note.delivery_corrected`).

The list's `awaiting_delivery_proof=true` filter, and the summary count of
the same name, are the notes dispatched or completed with no proof yet. A
list filter rather than a report, so it has no report-catalogue entry.
