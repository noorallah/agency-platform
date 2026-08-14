# Backlog

Work that is agreed but not started, with the decisions each one is waiting on.
Items move out of here when they are built, not when they are discussed.

Open feature-gating decisions live in `docs/MODULE_REVIEW_CHECKLIST.md` under
"three features deliberately left ungated" — they are questions rather than
tasks, so they stay there.

---

## 1. Make the remote UI work over the network — decided

**Decided on 2026-08-14: support both, and let the firm choose.** The client
accepts `https://` anywhere and `http://` to an address on its own network.
Plain HTTP to a public address stays refused.

That is option 3 below, bounded. The product puts a client on one machine and
the backend on another in the same building, and requiring HTTPS everywhere made
that deployment impossible without an installer that first puts a certificate in
every client's trust store. A firm running its own switch can reasonably decide
its LAN traffic does not need TLS; the same traffic crossing the internet is a
different thing, and no deployment of this product needs it.

What "its own network" means is written down and tested, not inferred:
loopback, `10/8`, `172.16-31/12`, `192.168/16`, `169.254/16`, IPv6 `fc00::/7`
and `fe80::/10`, single-label hostnames, and the `.local` / `.lan` /
`.internal` / `.home.arpa` suffixes. Anything it cannot classify is not local.
`desktop/test/server_url_rule_test.dart` is the decision written down —
including the boundary cases, because reading `172.16/12` as "all of 172" would
open the public internet.

**The trade, stated plainly:** on a network where plain HTTP is used, the login
password and every record cross the wire readable by anything else on it. The
firm chooses that by typing an `http://` address; it is not the default and not
silent — the field says which schemes it takes, and the refusal message says why.

The server side supports both as well. `scripts/start_backend.ps1` takes
`-BindHost` (127.0.0.1 by default, so a developer is reachable by nothing) and
`-CertFile` / `-KeyFile` to serve TLS. Giving one of the two without the other
is refused rather than starting on plain HTTP while the operator believes
otherwise, and binding to a network interface without TLS prints a warning.

**What this leaves for the installer (§3).** Nothing is now blocking it. If a
firm wants TLS, the installer has to place the certificate in each client's
Windows trust store; if it wants LAN HTTP, the installer has to open the port
and bind to `0.0.0.0`. It can support both because both work.

The three options this replaced, kept because the reasoning still applies if the
decision is revisited:

1. **HTTPS on the backend with a self-signed certificate**, installed into the
   Windows trust store on every client by the installer. Keeps the guarantee,
   costs installer complexity. Still available, and still the right answer on a
   network the firm does not control.
2. **A reverse proxy** on the server machine terminating TLS. Same guarantee,
   another moving part to install and supervise on a low-specification box.
3. **Relax the rule for private-network addresses.** What was chosen, with the
   tests it was said to need.

Test cases: `docs/MANUAL_UI_TEST_PLAN.md` §3.

---

## 2. Licence feature

Nothing implements licensing. A `LICENSE_MANAGE` permission, a `LICENSE_ADMIN`
role and a `license_error` error code exist and are unused — there is no model,
endpoint or screen.

Five questions decide what gets built, and each changes the tests:

1. What is licensed — the installation, the firm, the user, or a module?
2. What happens at expiry — read-only, blocked writes, or a grace period?
3. Phone home, or an offline key? Offline suits an on-premises Windows box with
   no guaranteed internet.
4. Who may see and enter a key — platform admin only, or a firm admin?
5. How is it stored so a determined user cannot simply edit it?

Whatever we choose, reads should stay possible after expiry so a firm can always
get its own data out.

Draft test cases: `docs/MANUAL_UI_TEST_PLAN.md` §10.

## 3. Single self-installing batch file -- built

`install\install.bat` (a wrapper) and `install\install.ps1` (the work). One
command from a machine with nothing on it to a running backend and a desktop
client at the login screen. No Docker.

It carries the four things this project has been bitten by:

- **Every store is migrated**, through `scripts/migrate_all_stores.py`, which
  enumerates targets from the registry rather than a hardcoded list.
- **Refuses the development secrets**: the generated `.env` writes
  `AGENCY_ENVIRONMENT=production` and a random signing key, so the
  application's own startup checks refuse a development JWT key or a missing
  bootstrap password. The installer does not reimplement those rules; it makes
  them apply.
- **Safe to run twice.** Every step checks first. `config\.env` is never
  overwritten -- it holds the signing key and the database password, and
  replacing it would sign every user out and lock the application out of its
  own database.
- **Transport is a choice**, per §1: plain HTTP by default, `-CertFile` /
  `-KeyFile` to serve TLS, and half a TLS configuration is refused rather than
  quietly falling back.

`-DryRun` reports every step and changes nothing. `-InstallPrerequisites` is
what allows it to install Python and PostgreSQL through winget; without it a
missing prerequisite stops the run with the exact command to fix it, because
installing a database server should not be a side effect of running a script
that looked like it would set up an application.

**What building it found**, both fixed here:

- `start_backend.ps1` ran everything through `uv run`, which fails on some
  Windows machines with "uv trampoline failed to canonicalize script path". It
  now prefers the virtual environment's own interpreter.
- Worse, and only visible because the installer waited for `/health`: native
  programs log progress to **stderr**, and in Windows PowerShell 5.1 `2>&1`
  wraps each such line in an ErrorRecord, so with `$ErrorActionPreference =
  'Stop'` the first alembic INFO line aborted the script. It stopped dead after
  "Applying migrations..." with nothing in the log to say why.

**Not yet verified: a machine that has never had the toolchain.** 2.2 and 2.5 in
`docs/MANUAL_UI_TEST_PLAN.md` §2 were checked on a developer box; 2.1, 2.3 and
2.4 cannot be answered there, because a developer machine passes a clean-install
test on the strength of what is already on it. The prerequisite-install path and
the no-internet path are written but unproven.

Also unresolved, and cheap to decide later: the repository has an ignored
`installer/` directory holding a small tenancy-config helper from an earlier
attempt. It is not wired to anything. Either fold it in or delete it.

## 4. A skill for resetting and regenerating demo data — done

`.claude/skills/reset-demo-data/SKILL.md` carries the sequence and the traps:
migrate every store first and never with a bare `alembic upgrade head`, clear
`AGENCY_DATABASE_*` afterwards, reset before laying opening stock down, and read
the delivery-note count against the sales-order count because a gap between
firms is how a real dispatch defect was found.

**`scripts/verify_sample_data.py` does not run**, which the skill says rather
than offering it. It belongs to `generate_sample_data.py`'s single-firm
`NAVK_CPL` dataset and predates multi-tenancy: it fails at import on
`ProductUomConfig`, dropped in `20260812_0068`, and repairing that only moves
the failure to `relation "platform.uoms" does not exist`, because it reads
platform and firm-owned tables from one schema. Making it work means splitting
its queries across the platform store and each firm store — a rewrite, and one
that should decide first whether it is verifying the single-firm sample or the
four-firm demo. The checks that do work are in the skill.

---

## 5. Navigation, header and footer — the 2.0 UX pass

Reviewed on 2026-08-11 and **deliberately deferred**: functionality first, these
changes in 2.0. Written down so the findings are not rediscovered.

### The model is right; the contents are not

`desktop/lib/ui/workspace/module_catalog.dart` declares **16 modules and 107
tabs**, and `EnterpriseSidebar` already renders sections → modules → nested
children. The two-level structure is built and works. What is flat is what was
put into it — the TRANSACTIONS section alone carries eight top-level modules:

```
Purchases · Purchase Invoices · Purchase Returns · Goods Receipts
Sales · Sales Orders · Delivery Notes · Sales Invoices
```

`Sales Invoices` is a sibling of `Sales`. That is the problem in one line: a
document type outranks the process it belongs to, so somebody hunting an invoice
has to know it was promoted to the top level rather than filed under Sales,
where they would look first.

**Done on 2026-08-14.** The six document modules are filed under the process
they belong to -- `goodsReceipts`, `purchaseInvoices`, `purchaseReturns` under
Purchases; `salesOrders`, `deliveryNotes`, `salesInvoices` under Sales. The
TRANSACTIONS section went from eight top-level entries to two.

**The alias map turned out not to be needed, and that was a design choice.**
Nesting was done in the sidebar -- `EnterpriseSidebarSection.childModuleIds`
plus an indent -- so each document is still a whole module with its own page,
permissions and **route name**. `_routeModule()` matches a stored
`lastWorkspace` against `AppModule.values` by name, and no name moved, so a
client last on Sales Invoices still reopens there.

The alternative was to make the documents tabs of Sales and Purchases, which
would have changed those route names and needed the map. It would also have put
document tabs beside the workspaces' own tabs and forced `_page(...)` to
dispatch per tab, for the same visible result. `navigation_reparenting_test.dart`
holds the tripwire: it asserts every re-parented module still resolves to itself
by name, so changing a route id instead of a section fails there rather than in
somebody's next session.

Not covered: the **collapsed** rail is a flat strip of icons, so the six still
appear at its top level. Nesting is not expressible in a one-icon-wide rail, and
the flyout it opens shows a module's own tabs.

**Sales is listed before Purchases** as of 2026-08-14. The section is ordered by
how often it is opened rather than by the order goods move in: a distribution
firm raises sales orders every day and purchase orders every few weeks, so
putting the weekly job above the daily one cost the daily one a glance every
time.

**Configuration is grouped** in Masters, the way Administration already grouped
its own. `Firm Settings`, `Financial Years` and `Branches / Departments` sat
loose at the bottom, level with Customers and Products, so a module of master
data ended in three entries that are not master data. Grouping only -- every
path is unchanged.

What that does **not** do is unify configuration across Masters and the Settings
module. Settings is still a separate module, and all four of its tabs
(`audit-logs`, `background-jobs`, `system-settings`, `api-monitoring`) are
`available: false` -- unbuilt placeholders. Moving working screens into a module
that does nothing yet would bury them; that unification is worth doing when the
placeholders become real, and not before.

### Not to do

**A Windows-style File/Edit menu bar.** ERP actions belong to the record on
screen, and the workspace toolbar already owns New / Edit / Delete / Export. A
global menu bar would either duplicate it or go stale against the selection. The
left rail plus the per-screen toolbar is the right pairing; this was considered
and rejected, not overlooked.

### Header and footer — reviewed, left as they are

Both were examined and the decision was to **change nothing for now**. Recorded
so the next reader knows these are known, not missed:

- The header was **trimmed on 2026-08-14**. It carried the application name, a
  sidebar collapse toggle and `ThemeSelector`, all three of which the sidebar
  owns -- its header has the name and the toggle, its footer the theme. Two
  copies of a control are two things to keep in step, and one of them is always
  the wrong one to reach for. Back and forward stayed.

  **The module title stayed too**, deliberately. It is the third place the title
  appears, after the selected sidebar item and the page's own header — but only
  seven files render a header of their own, so removing it here would leave the
  rest of the screens with no title at all. Worth revisiting once
  `ModuleWorkspaceFrame` is used everywhere.
- The footer's health lights were **decided and fixed on 2026-08-14**: they
  probe for real. `/health` and `/health/database` both already existed and
  neither was ever called, so the bar reported "checking" for the life of the
  application. The shell asks both every thirty seconds now, and `stateText`
  follows the answer instead of reading `Online` always.

  Two things worth keeping if it is touched again. The database is asked about
  only when the server answered, because a database that has gone does not
  return 503 — it stops answering, and `/health/database` hangs until the
  30-second request timeout, so asking both of a dead server doubles how long a
  client takes to notice. And an unreachable server leaves the database
  **unknown** rather than offline: this client cannot tell a database that has
  gone from one it cannot see past, and claiming otherwise would be the same
  kind of wrong as the literal it replaced. `resolveHealth` in
  `ui/workspace/health_probe.dart` holds that decision, tested without a server.

  Still open in the footer, and cosmetic: it repeats the user's email address,
  which the profile menu already shows.

## 6. Batch-grained stock — the rest of it

Stages one and two are merged (PRs #14–#17). A stock row is now identified by
its batch, goods receipts create the batch from the number typed off the
carton, dispatch allocates across batches by earliest expiry, purchase returns
post against the batch they name, the ledger records which batch moved, `GET
/inventory/summary/by-product` totals a product across its batches, and a
product's `require_batch_on_receipt` / `require_batch_on_issue` finally decide
something.

A batch no longer stores its own quantities either: the six columns are gone
and the API reports what the stock rows hold.

`docs/INVENTORY_FRAMEWORK.md` describes the module as it stands, including
which document does what with a batch.

**This item is done.** It is kept here rather than deleted because the three
editors below took three different shapes for reasons that are not obvious from
the code, and the next person to touch document entry needs them.

**Goods receipt entry is built** (`goods_receipt_editor_dialog.dart`): the
workspace has a New Receipt action, lines are seeded from the purchase order
being received, each defaults to what is still outstanding on it, and the batch
number typed off the carton reaches the server. That is the first document the
desktop can create, and it makes the batch work reachable by a user.

**Delivery note entry is built** (`delivery_note_editor_dialog.dart`): lines are
seeded from the sales order, each defaults to what is **reserved** rather than
what was ordered — dispatching more than is reserved is refused, so the ordered
quantity would look right and fail — and each line shows which batches it is
expected to ship from, earliest expiry first. Nobody types a batch: the server
allocates at dispatch, and the preview says so rather than implying a decision
has been made.

**Purchase return entry is built** (`purchase_return_editor_dialog.dart`): lines
are seeded from the completed goods receipt being sent back, default to what is
still returnable, and the batch is **chosen from the register** rather than
typed — the batch the goods arrived in is the default. The server refuses a
number nobody received, and it refuses it at completion, after the whole
document has been typed and approved; a picker means that refusal cannot be
reached by hand.

**All three document types can now be created from the desktop**, which was the
last thing standing between the batch work and a user.

`BatchResponse` names the product, warehouse and branch a batch belongs to.
Those six fields had been declared since the response was written and filled by
nothing, so the batch grid rendered a product column reading " - " for every
row. They are filled in `batch_responses` in bulk -- one query per kind of name
for the whole page, guarded by a test that counts the statements, because a
lookup per row is what turns a twenty-row page into eighty queries.

**The demo data carries batches.** PHARMACY and FOOD enable BATCH_TRACKING, the
medicines and the packaged food require a batch on receipt, and
`generate_transaction_history.py` names one per product per month, with an
expiry where the firm has EXPIRY_TRACKING. A seed produces batch-grained stock
rows, dispatches that name the batch they came off, lines that span two batches,
and untracked stock beside all of it -- the vitamin box and the biscuits are
deliberately left untraced, so both paths are exercised.

Both flags are seeded, because **opening stock arrives in a batch** too
(`20260814_0074`). It was the last way stock could enter untraced, and until it
carried one, a product requiring a batch on issue could never ship what it
started with -- there was no batch for the allocator to draw from. Day-one stock
behaves like a receipt: an unknown number registers the batch, and a product
requiring one on receipt is refused without it.

**A reservation names the batch it holds.** Approving a sales order used to
commit the *product*: the movement went to the untracked row whatever the goods
were in, driving its available negative while the batch rows sat apparently free
and promisable to somebody else. Reservations are now held by earliest expiry,
released the same way, and what no batch can cover is held with no batch --
which is what a back order is.

What that was worth, on the same seeding command: **MEDI01 and FOOD01 went from
44 and 23 delivery notes to 57 of 57**, the same as the firms that trace
nothing.

**The batch field is a different control in each editor, and that is the point.**
A receipt takes free text, because the goods are on the dock and the number is
on the carton — refusing an unknown one would stop a warehouse. A delivery note
takes nothing, because the server allocates at dispatch by earliest expiry. A
return offers a picker over the register, because the number must be one that
was actually received and the server's refusal lands at completion, after the
document has been typed and approved. Copying any one of them onto another
document would be wrong in a way that only shows up in use.

Decisions in the editors worth knowing before copying them:

- **They offer only APPROVED or COMPLETED source documents.** The backend accepts
  a receipt against a purchase order in any state, so this is a client-side
  policy: goods should not be booked in against an order nobody approved. If that
  turns out to be wrong for a warehouse that receives before the paperwork
  catches up, the fix is to widen the filter, not to loosen the server.
- **The delivery editor's allocation is a preview, not a decision.** It mirrors
  `allocate_for_dispatch` client-side over the stock rows it can see, and the
  server allocates for real at dispatch — stock can move in between, so the
  wording on screen says "expected to ship from" and never claims more.
- **`reserved_quantity` of zero has two meanings** and the editor separates
  them: an order nobody approved has reserved nothing yet, while a fully
  delivered one released its reservation on the way out. Every seeded order in
  the demo store is in the second state, so a single message would have been
  wrong for all of them.
- **The expiry and vehicle fields are shown to every firm**, so a firm without
  EXPIRY_TRACKING or VEHICLE_TRACKING can type one and be refused on save --
  proven while verifying this, where completing a receipt carrying an expiry
  date returned a 403 naming the feature. That is the "desktop does not pre-hide
  feature-gated fields" item under **Also open**, now with a concrete case.

**Warehouse transfers were built on 2026-08-14.** `POST /inventory/transfers`
writes a `TRANSFER_OUT` and a `TRANSFER_IN` against one reference, carrying the
batch across so it stays traceable through the move, and **writes no journal**:
the firm owns the same goods at the same value afterwards, and there is one
inventory control account, so debiting and crediting it for the same amount
would be noise rather than information. Stock by warehouse in the accounts
would need an account per warehouse, which is a different and much larger
feature.

The value is held still deliberately -- stock leaves at the moving average and
arrives at the same figure, so a transfer cannot quietly revalue a product,
which it would if the inbound leg valued itself at nothing. Unlike a dispatch,
which may run stock negative because the goods have physically gone, a transfer
of stock the source does not hold is refused: nothing left the building.

**Reason-coded write-offs and quarantine were built on 2026-08-14.**
`POST /inventory/write-offs` takes a reason (`DAMAGE`, `EXPIRY`, `LOSS`), which
rides on the movement and into the journal narration: a firm could already
answer how much stock it lost and not to what. The value leaves through the
same `5500 Inventory Adjustment` account, because splitting damage from expiry
into separate accounts is a chart decision a firm can make by remapping the
purpose -- seeding three accounts would be deciding it for them.

`POST /inventory/quarantine` holds stock back from sale and releases it again,
and **posts nothing**: quarantined stock is still owned and still worth what it
was. Condemning it is a separate decision taken once somebody has looked at the
goods.

Two defects found building it, both about value rather than quantity. A
quarantine hold rolled the moving average as though the stock had left, writing
120.00 off a firm that had lost nothing -- `_Movement.revalues` marks a
movement that changes buckets and not ownership. And a write-off of quarantined
stock posted nothing at all, because the valuation follows the sellable bucket
which the hold had already emptied: the goods went in the skip and the value
stayed on the balance sheet. `_Movement.owned_delta` says how much the firm
stopped owning, separately from which bucket it left.

**The three stock actions have screens** as of 2026-08-14: transfer, write off
and quarantine are buttons on a selected inventory row, opening one dialog that
asks the same three questions -- how much, when, under what reference -- and
differs in one field each. Three dialogs would be three places for the same
quantity check to drift. Each says on screen what it does to the books, since
"this posts nothing" is exactly the thing a storeman cannot infer.

**The receivable endpoint no longer takes money.**
`POST /customers/{id}/receivables/transactions` refuses `RECEIPT` and
`ADVANCE_RECEIPT` and names `/api/v1/receipts` instead: it moves the customer
balance and writes no journal, so every use of it for money in put the
subsidiary ledger and the general ledger further apart. The service method
stays general -- the sales invoice and settlement services call it inside a
larger unit of work that does post. Credit notes and advance applications still
go through it, because they move no money.

**`REFUND` was the hole this left, and it is closed** (2026-08-14).
`POST /api/v1/refunds` is a third settlement direction: money out, like a
payment, and about a customer, like a receipt -- which is why it is neither.
It debits receivables because the customer is no longer owed the advance they
paid, credits the account the money left, and reduces the advance through the
receivable service, which already held the rule that a refund cannot exceed
what the customer is actually holding.

It is not applied to an invoice: a refund returns money held on account, which
is the opposite of settling a document. `20260814_0082` widens the party check
constraint so a refund carries a customer, and it takes the money-out grants
rather than the receipt ones -- the person trusted to collect is not
automatically the person trusted to hand money back.

**The Refunds tab followed the same day.** Adding it turned the client's
money-in boolean into a `SettlementDirection`: a refund is money out like a
payment and about a customer like a receipt, so no single flag described it,
and the three places that had been asking `isReceipt ? ... : ...` were each
about to grow a third arm. The direction now owns its path, its party
parameter, its permissions and its nouns, so a fourth direction would touch one
file. The dialog shows no invoice table for a refund and says why.

**Physical count reconciliation was built on 2026-08-14**, which closes the
inventory gaps. It is a document rather than an action: the sheet is drawn up
from what the warehouse currently holds, walked over hours by people with a
clipboard, and posted once at the end -- an endpoint taking counted quantities
would lose everything the moment somebody closed a laptop.

Two rules carry the weight, and both are about the gap between drawing the
sheet up and posting it:

- **The variance is measured against what the system holds when the sheet is
  posted**, not against the snapshot it was drawn up from. Stock moves while a
  warehouse is being counted, and posting a stale figure would put back every
  dispatch made in between. The snapshot is kept on the line as
  `expected_quantity`, for the person reading it afterwards.
- **A line nobody walked is not a line that found nothing.** `counted_quantity`
  is null until somebody counts it, and posting skips those: treating them as
  zero would write off the stock that was simply not reached.

Each difference becomes a stock adjustment, and adjustments have reached the
general ledger since `20260814_0079`, so a count that finds twelve missing
cartons puts their value in the profit and loss without anybody keying a
journal.

**The screen followed the same day**, under Inventory. Saving and posting are
separate buttons because the sheet is walked over hours: what has been found so
far goes to the server rather than sitting in a form somebody might close.
Building it found that `WorkspaceDialog.onSave` is bound to a keyboard shortcut
and nothing else, so a sheet relying on it would have had no visible Save at
all -- losing an afternoon of counting to an unknown shortcut is exactly the
failure the screen exists to avoid. Both actions are buttons now.

The difference is shown as it is typed, so a fat-fingered digit is visible
before posting rather than after; a blank line is sent as no count rather than
as zero, matching the server's rule that an uncounted line is not a line that
found nothing; and posting says how many lines nobody walked before it goes
ahead.

**"Stock movements post nothing to the general ledger" was wrong**, and the
correction matters because it changes what needs building. Measured on
2026-08-14 against both stores:

    wholesale_hub   stock 210,338.7956   ledger 210,338.79   drift 0.0056
    firm_shared     stock 420,677.5916   ledger 420,677.58   drift 0.0116

The two agree. The drift is the valuation holding four decimals and the ledger
two, not a missing posting. Goods receipts post `Dr Inventory / Cr GRNI` and
dispatches post `Dr COGS / Cr Inventory`, and between them they keep the
control account honest for everything the demo exercises.

**Three movement types do change stock value and post nothing**, and each one
silently breaks that reconciliation the first time it is used:

1. **`ADJUSTMENT` -- built on 2026-08-14.** Stock going up debits inventory and
   credits `5500 Inventory Adjustment`; going down does the reverse, which is a
   write-off and a cost. The same account takes both sides so a firm reads its
   net adjustment in one place, and `20260814_0079` creates and maps it for
   every firm that already has a chart -- without that, posting would have
   refused every adjustment a firm made, a working endpoint breaking on
   upgrade. An adjustment worth nothing writes no journal at all: an empty one
   claims something happened in the ledger when nothing did.
2. **Purchase returns -- built on 2026-08-14.** Completing one now posts
   `Dr Accounts Payable` with the whole credit note, `Cr Input Tax` reversing
   what was claimed on the way in, and `Cr Inventory` at **what the stock
   actually cost** rather than what the return is priced at. The gap between
   those two is a purchase price variance, the same account an invoice uses
   when it disagrees with the receipt it clears -- crediting inventory at the
   return price would leave stock valued at something no movement ever paid.
   Verified on the seeded firm: a return of 316.24 moved payables -316.24,
   input tax -48.24, inventory -203.16 and variance -64.84, and stock still
   reconciles to the control account.
3. **Opening stock -- built on 2026-08-14.** Day-one stock arrived from nowhere
   the ledger can see, so it debits inventory and credits `3000 Opening Balance
   Equity` under a new `EQ` group (`20260814_0080`). It is the first equity
   account the chart has ever had, and the balance sheet now shows a real one
   rather than computing the whole equity side.

   Building it found the reason posting was pointless: **`opening_stock_lines`
   had no cost column at all**, so day-one stock entered the valuation at zero
   -- a firm's entire starting inventory worth nothing in the stock valuation
   and nothing in the ledger, agreeing with each other and with nothing real.
   `20260814_0081` adds `unit_cost`, nullable, because a firm that does not
   know is better served recording the quantity than nothing; such stock still
   posts no journal.

All four movement types that change stock value now post, and the seeded firm
reconciles after each of them.

## 7. Finance has a screen -- and now the full set of reports

`app/finance` is thirty live endpoints and has been since `20260809_0042`.
Every goods receipt, dispatch, sales invoice and purchase invoice posts to the
general ledger through `DocumentPostingService`, and the desktop rendered
**"Coming Soon"** -- so a firm could trade for a year with the ledger filling up
and no way to look at it.

Built on 2026-08-14:

- **Chart of Accounts**, as a `ResourceDefinition` over `/finance/ledger-accounts`.
  No delete: an account with postings against it cannot go without taking its
  history, so deactivating is the way and the form says so.
- **Trial Balance** over `/finance/trial-balance`, per accounting period,
  opening on the most recent one. Whether it balances is the server's answer
  carried through, not recomputed here -- two places deciding that is two places
  that can disagree.

Verified against the seeded WHOLE01 firm: August 2026 reports six lines with
debit and credit both 604,976.70.

**Journal entries** followed on 2026-08-14: a list, a hand-written entry that
has to balance before it is sent, and post and reverse. The backend had no way
to *find* an entry -- create, read-one-by-id, post and reverse, and no list --
so everything the documents posted was unfindable unless somebody already knew
its id. `GET /finance/journal-entries` was added with it.

**Ledgers** followed on 2026-08-14: pick an account and a period, and read what
it opened at, every movement with the entry that wrote it, and what it closed
at. The running balance comes down from the server with the lines rather than
being added up in the client -- it starts from the opening balance and moves in
whichever direction the account type increases in, and a client totalling it
itself is a second opinion about the ledger.

**Profit and loss** followed on 2026-08-14, backend and screen: `GET
/finance/profit-loss` had to be written, since the module served a trial
balance and a statement but nothing that said whether the firm made money.

Two columns, the period and the year to date, because one on its own is the
wrong answer half the time -- June 2026 in the seeded firm is a loss of 2,657.46
inside a year that is 5,086.46 ahead. It is built from movement rather than
balances, which makes it the one report where an account that saw nothing
contributes nothing and the carried-balance fix above would be *wrong*. The year
is the boundary, because profit resets there.

Sections come from `account_type`, deliberately not from the `is_profit_loss`
flag: the type is structural, while the flag was a plain default nothing set, so
every account in every firm carried "balance sheet, not profit and loss" --
Sales and Purchases included, and the account detail panel showed it as fact. A
report reading it would have come back empty everywhere. The flag now follows
the type on create unless the caller overrules it, and `20260814_0075` brings
existing rows into line, touching only rows still at both defaults so a
deliberate choice is never overwritten.

**Balance sheet** followed on 2026-08-14, and closes the module's reporting:
`GET /finance/balance-sheet`, as at a period end rather than for a period, so
it uses the same carried-balance pair as the trial balance.

The decision it needed was retained earnings, and the data answered it.
**Nothing in this ledger posts a year-end closing entry**, so income and
expense accounts accumulate indefinitely and their net *is* the firm's
earnings; carrying it into equity balances the sheet to the rupee on every one
of the 36 seeded periods. Without it the sheet is short by everything the firm
has ever made, and no chart of accounts fixes that, because the entry that
would is never written. It is split into what was built up before this year and
this year's result, which are the two questions people actually ask.

Only `ASSET`, `LIABILITY` and `EQUITY` accounts appear. `MEMO` is off the
statement by definition and `CONTROL` is not a section of a balance sheet; if
either ever holds a balance the sheet stops balancing and the screen names that
as the likely cause rather than absorbing it silently.

**Receipts and payments** were built on 2026-08-14 as `app/settlements`, the
last real gap in the module. Nothing in the product could record money
arriving: two years of seeded trading left Cash at 0.00 while Trade Receivables
grew to 249,236.70, because invoices were the only document that reached the
ledger.

The one path that existed was worse than none.
`POST /customers/{id}/receivables/transactions` accepts a RECEIPT, moves the
customer's outstanding balance and **writes no journal**, so every use of it put
the subsidiary ledger and the general ledger further apart, silently and
permanently. A settlement is therefore a document that posts, and the posting is
what makes it real -- no control account or no open period refuses the whole
thing rather than recording it half-way. `settlements.journal_entry_id` is NOT
NULL to keep that true in the schema and not only in the service.

One table for both directions: a receipt and a payment are the same document
with the signs reversed. Allocations record which invoices it cleared, and what
an invoice still owes is **derived** from them rather than stored, because a
paid-to-date column is a second copy of the same facts and is wrong the first
time anything writes one outside the service. Money not tied to an invoice is
held on account, which is a normal thing for a customer to send.

Two things it deliberately does not do, and the reasons:

- **A settlement can be reversed** since 2026-08-14 (`20260814_0077`). Nothing
  is edited or deleted: a mirror journal cancels the original, the allocations
  stop clearing their invoices while still recording what they had cleared, and
  the customer's outstanding and advance balances are put back by the exact
  amounts the receipt moved them -- read from the transaction row it wrote, not
  recomputed. A receipt of 500 against an outstanding 300 becomes 300 off the
  balance and 200 of advance, and only that row remembers the split.
  A reversal that would drive a balance below zero is **refused** rather than
  clamped: if the overpayment has since been refunded, the correction that fits
  is a credit note, and inventing a balance nobody can explain is worse.
- **No vendor payable balance was introduced.** Customers carry a denormalised
  `current_outstanding` that credit control depends on, so receipts keep it in
  step. Vendors carry nothing, and what they are owed is derived from their
  invoices less allocations rather than adding a second balance to drift.

**The seeder now raises purchase invoices** (2026-08-14). It had 29 goods
receipts and zero invoices, so the payables side of the ledger stayed at zero,
nothing was ever owed to a vendor, and a payment had nothing to be applied to.
Each receipt is now billed and approved, which is what clears the
goods-received accrual into Trade Payables: the seeded wholesale firm went from
`2300 Goods Received Not Invoiced 355,740.00` to
`2100 Trade Payables 419,773.20` with 29 unpaid bills, and paying one clears it
against the ledger.

Fixing that exposed a second gap: **`RESET_ORDER` did not know about the
settlement tables**, so `--reset` failed on the foreign key from
`settlement_allocations` to `sales_invoices` as soon as any receipt existed.
They are cleared first now.

**The trial balance lists every account with a balance** as of 2026-08-14, not
only the accounts that moved. A `ledger_balances` row is written when an account
is posted to, so the stored rows for a period are its movers -- and totting
those up reported a firm out of balance whenever a quiet period touched one side
and not the other. March 2027 in the seeded firm read `dr 0.00 cr 211217.50`
with the ledger perfectly sound. Accounts holding a balance that saw no movement
are now carried in with a zero-movement line, built in memory and never written:
a stored balance for a period nothing happened in would be invented history. All
36 seeded periods balance, including the earliest, which has nothing to carry.

**An account statement opens at the balance it carries**, from the same day and
for the same reason. `general_ledger` read its opening from the stored row for
the period, so an account that saw no movement opened at zero and closed at
zero -- which tells the reader the account is empty rather than that it was
quiet. Trade Receivables read `opening 0, closing 0` for March 2027 while the
firm was owed 249,236.70; it now reads 249,236.70 both sides with no lines
between them. `ZERO` in the same service became `Decimal("0.00")` with it, so a
carried figure is not written `0` in a column of `0.00`s.

---

## Also open

- **The audit trail has a screen** as of 2026-08-14, under Settings. Every
  mutation has written a row since the platform started and a trigger makes the
  table append-only in every store, with nothing in the client able to read one.
  The screen shows **only the fields that changed** -- an audit row carries whole
  snapshots on both sides and showing all of them buries the one that moved --
  and it names which trail is on screen, because the trail is per store and a
  reader who takes it for everything will conclude that something they cannot
  see never happened.

  **Open question it surfaced, deliberately not decided here:**
  `AUDIT_LOG_VIEW` is granted only to `PLATFORM_ADMIN`, `SUPPORT_ADMIN` and
  `SYSTEM_AUDITOR`, so a firm administrator cannot read their own firm's
  history while the platform operator can. On a product that runs on the
  customer's own machine that looks backwards -- but it is a **stated
  boundary**, not an oversight:
  `test_firm_admin_has_no_platform_permissions_or_platform_access` names
  `AUDIT_LOG_VIEW` in the set a firm role must never hold, and the endpoint
  already gates the *platform* trail separately on the `platform_admin` role,
  so the code is doing two jobs.

  Granting it to `FIRM_ADMIN` was tried and reverted rather than editing the
  test to match: a test that names the exact code is a decision. Deciding it
  properly means either splitting the code (a firm-scoped
  `FIRM_AUDIT_LOG_VIEW` alongside the platform one) or agreeing the boundary
  should move. Until then the screen is reachable by `SYSTEM_AUDITOR`,
  `SUPPORT_ADMIN` and platform administrators, which is who the seed intends.

- **Desktop pre-hides feature-gated fields** as of 2026-08-14, decided the way
  the module menu already worked: read `/active-features` and do not offer what
  cannot be saved. `BusinessFeatures` holds the answer, and **unknown means
  offered** -- the set is null before the call returns and after it fails, and
  hiding fields because a request failed would take working screens away from
  firms entitled to them. It is cosmetic; the server is still the boundary.

  Applied to the goods receipt editor, which is where the concrete case was:
  WHOLE01 has neither EXPIRY_TRACKING, MANUFACTURING_DATE nor VEHICLE_TRACKING,
  so all three fields were offered and none could be saved. MEDI01 keeps expiry
  and manufacturing date, which is the check that the gate is reading the
  profile rather than hiding everything.

  **Still to sweep:** the same fields appear in the delivery note editor,
  purchase and batch screens, and DRUG_LICENSE / SHELF_LIFE / WARRANTY are
  ungated in the client everywhere. The product form has its own gating already
  (it reads product metadata rather than `/active-features`), which is a second
  mechanism worth collapsing into this one.
- **`tests/` still has about 40 ruff findings** — missing docstrings and long
  lines in older test files. `app/` is clean.
