# The sales chain — documents, stages and what may be skipped

These rules were in `CLAUDE.md` until 2026-09-15, when that file passed the
150k-character limit that keeps it loadable in one context window. Nothing
was cut -- the prose is verbatim and the imperative half of each rule stays
in `CLAUDE.md` with a pointer here. Every one was written from a defect that
actually happened, so the story beside the rule is the part that says why it
is the rule.

`docs/SALES_TO_RECEIPT_FLOW.md` is the walkthrough; these are the rules the
chain enforces.

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

## Credit limits warn, and block only if a firm asks

**Credit limits warn, and block only if a firm asks.** `customers.credit_limit` constrained nothing until `20260810_0057`. `CreditControlService` compares it against exposure — `current_outstanding - unapplied_advance + the document being saved` — at sales order and sales invoice approval, the two points where credit is committed. Policy is per firm in `credit_control_settings` (`OFF` / `WARN` / `BLOCK`, with warn and block percentages); a firm with no row warns at 80% and never blocks, and a `credit_limit` of zero means unset rather than no credit, so shipping this stopped nobody trading. `GET /api/v1/customers/{id}/credit-status?amount=` answers the question before a document is saved rather than reporting the breach after, and `GET`/`PUT /api/v1/customers/credit-settings` carries the policy. Writing the policy needs `CUSTOMER_MANAGE_SETTINGS`, deliberately **not** granted to `SALES_MANAGER`: the role the limit constrains must not be able to switch it off. **Moving a customer's `credit_limit` needs the same code** (D-CFG-17): raising it, or setting it to zero, lifts a BLOCK as surely as switching the policy off, so `PUT /customers/{id}` refuses a changed limit by name without it and the desktop shows the field read-only; resending the stored figure is not a change, and a new customer's limit is anyone's to set because every customer otherwise starts with none. The desktop **warns and never blocks**: `warnOnCreditExposure` (`desktop/lib/ui/sales/credit_notice.dart`) runs on Approve for sales orders and sales invoices, before the action so the document is not counted twice, and stays silent when `would_block` is true because the server's refusal already carries the same sentence. A client that blocked on its own would enforce a rule the firm may not have chosen and could be bypassed by any other client. The policy itself is edited from the Settings action on the customers workspace (`credit_settings_dialog.dart`), which is readable with `CUSTOMER_VIEW` — someone the policy warns should see the rule behind the warning — and writable only with `CUSTOMER_MANAGE_SETTINGS`.
