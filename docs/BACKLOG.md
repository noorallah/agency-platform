# Backlog

Work that is agreed but not started, with the decisions each one is waiting on.
Items move out of here when they are built, not when they are discussed.

**What each open item needs to be built** -- owner input, modules, effort,
who, and a build order in waves -- is `docs/BACKLOG_BUILD_PLAN.md` (2026-10-02).

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

### An `.exe` -- asked 2026-08-22, deferred by the owner

Their words: *"installer will do later"*. Do not build one unprompted; this
section is here so the thinking does not have to be redone.

The batch file already does what an installer is usually wanted for. Proven end
to end on a developer machine on 2026-08-22: prerequisites checked, `.env` left
alone, venv found, database present, all four stores migrated to head, built
client found, backend answering `/health` on 127.0.0.1:8000, and the client
launched -- both processes up from one double-click. What it does when things
are **missing** is the part that has never been exercised (see above).

Three shapes, in increasing order of what they actually buy:

1. **Leave it as scripts.** `install.bat` is already the double-click entry
   point; Windows will not run an unsigned `.ps1` from Explorer, which is the
   only reason the wrapper exists. The honest gap here is not the file
   extension -- it is that the clean-machine paths are unproven. Proving them
   costs a spare Windows box and buys more than any packaging would.

2. **Wrap the script in a self-extracting `.exe`.** An hour or two, and
   cosmetic: it still needs the repository checkout, Python, PostgreSQL, and
   Flutter to build the client. Worth doing only if somebody's process refuses
   to run a `.bat`.

3. **A real distributable.** Inno Setup shipping the built
   `agency_desktop.exe` and a frozen backend (PyInstaller over uvicorn), so the
   target machine needs neither Python nor Flutter. This is the only shape that
   makes "hand it to a customer" true, and it needs four decisions first:

   - **PostgreSQL: bundle or require?** Bundling means shipping a database
     server and owning its upgrades; requiring it means the installer stops on
     a machine that has none, which is what it does today.
   - **Where does data live?** `%ProgramData%` for a service install, or a
     per-user directory. `config\.env` holds the signing key and must survive
     an upgrade -- the same rule the script already follows.
   - **Service or foreground?** A backend that only runs while somebody is
     logged in is not the same product as one that starts with the machine.
   - **Signing.** An unsigned installer gets a SmartScreen warning, and telling
     users to click past that teaches them the wrong habit.

   The migrations are the easy part -- `migrate_all_stores.py` already
   enumerates every store from the registry, and an upgrade is the same call.

## 4. A skill for resetting and regenerating demo data — done

`.claude/skills/reset-demo-data/SKILL.md` carries the sequence and the traps:
migrate every store first and never with a bare `alembic upgrade head`, clear
`AGENCY_DATABASE_*` afterwards, reset before laying opening stock down, and read
the delivery-note count against the sales-order count because a gap between
firms is how a real dispatch defect was found.

**`scripts/verify_sample_data.py` was rewritten on 2026-08-14** and is worth
running after a reseed; what follows is why the old one had to go. It belongs to `generate_sample_data.py`'s single-firm
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

## 8. Reports -- the module that has none

`REPORT_VIEW`, `REPORT_EXPORT` and `REPORT_PRINT` are seeded and granted, the
Reports module renders "Coming Soon", and **34 report endpoints exist across
seven modules that no screen calls**: registers, pending and overdue lists,
reconciliations, outstanding, and breakdowns by customer, salesman, territory,
route, warehouse, vendor and product.

Nothing needs building on the server. What is missing is a workspace that
presents them -- and, because the records are flat rows, a declarative
catalogue of report definitions rendering into one grid, the way
`ResourceDefinition<T>` does for CRUD, rather than 34 hand-written screens.

**Six of them broke the response convention** and were fixed first (2026-08-14):
every report in `sales_invoice` returned a bare list or object while every other
module wrapped in `ApiResponse`, which `CLAUDE.md` says is universal. Nothing
consumed them yet, so it cost nothing to correct; a client written against the
exception would have made it permanent.

**Built on 2026-08-14** as `desktop/lib/ui/reports/` -- a `ReportDefinition`
catalogue rendering into one grid, so a report is an entry rather than a screen.
**Thirty-three of the 34 are catalogued** and every one was driven against the
running backend. The only one left out is `sales-invoices/reports/summary`, which
answers one object rather than rows; it belongs on a dashboard.

**Five purchase-return reports did not do what their names said**, and were
corrected the same day rather than catalogued as they were:

- `damaged` filtered `current_return_quantity > 0` and `expired` filtered
  `pending_quantity >= 0`, so they answered "anything returned" and "nearly
  everything". The line has carried `is_damaged` and `is_expired` since it was
  written; both reports now read them.
- `by-product` answered the per-line reconciliation, which carries no product at
  all. It is now grouped per product, with code, name, quantity, value and count.
- `by-vendor` and `supplier-analysis` were the same call under two paths.
  `supplier-analysis` is gone, and `/reports/reconciliation` -- a report the
  service always computed and nothing exposed -- takes its place, leaving the
  module with six.
- The line-level reports counted **cancelled** returns, which the by-vendor
  totals had always excluded. A cancelled return did not happen; it now counts
  nowhere.

`PurchaseReturnVendorOutstandingRecord` was renamed `PurchaseReturnByVendorRecord`:
purchase returns have no balance still owing, and the record held returned value.

Nine of the 33 answer with **whole documents** rather than report rows
(`goods-receipts/{pending,completed,rejected,damaged}`, `sales-invoices` and
`purchase-invoices` `{pending,overdue}`, `delivery-notes/pending`): forty-odd
fields including `lines` and `attachments`. The client names their columns
explicitly rather than deriving them. Narrowing them server-side to a record
would be the better fix and would let the catalogue drop the override.

## 9. Sales returns -- goods coming back from a customer

**Built on 2026-08-14** as `app/sales_return`, the mirror of `app/purchase_return`
on the sales side.

A customer could always be credit-noted for goods they sent back, which moved
the money. **Nothing put the units back on the shelf**: inventory went on
counting them as sold, so stock understated what the firm held from that moment
on, and the only correction was a manual adjustment nobody knew to make.
`SALES_RETURNS` appeared in exactly one place in the whole backend -- the credit
note posting -- and `SALES_RETURN` had been a seeded permission code, held by
`SALES_MANAGER` and enforced nowhere, since the identity seed was written.

Completing a return moves three books together, and any of them failing fails
the whole document:

- **Stock** comes back through `InventoryService.record_sales_return`, at the
  moving average the product is carried at rather than what it sold for. Only
  the restockable part returns to the sellable bucket; goods that came back
  broken land in the damaged one, still owned and still worth what they cost.
- **The customer's account** falls by the credit, through the same receivable
  path a sales invoice uses.
- **The ledger** takes two entries, because they answer two questions:
  `Dr Sales Returns + Dr Output Tax / Cr Accounts Receivable` at the selling
  price, and `Dr Inventory / Cr Cost of Goods Sold` at cost. One entry at either
  number would leave inventory or receivables wrong by the margin.

Cancelling a completed return undoes all three. A return can be raised from a
**delivery note or a sales invoice** -- a customer who sends goods back before
being billed has only the first.

**Two defects found by driving the running backend**, neither visible to the
unit suite:

- A return worth nothing failed at completion with "A journal entry must carry
  a non-zero amount", stock already counted back in. Free samples and warranty
  replacements go out at no charge, and every delivery note the demo seeder
  writes is priced at zero. The credit posting returns None there now, the way
  the cost posting always did. The line's `unit_price` also became optional
  rather than defaulting to zero, so "take the source document's price" and
  "this one is free" stopped being the same request.
- **`scripts/verify_sample_data.py` caught a valuation leak**: cancelling a
  return of damaged goods left stock worth 203.16 more than the inventory
  control account. `reverse_transaction` mirrors the six bucket deltas and
  nothing else, and this was the first movement whose ownership change differed
  from its sellable one. `inventory_transactions.owned_quantity_delta`
  (`20260814_0085`) persists it so a reversal can undo what was applied; NULL
  keeps its old meaning, so nothing is backfilled. The same hole was latent in
  the quarantine write-off.

`RESET_ORDER` in `scripts/generate_transaction_history.py` gained the five new
tables. Leaving them behind while the numbering counters were cleared made a
freshly regenerated firm answer 409 to the first return raised against it --
the same staleness its header already records for settlements.

**The desktop workspace followed the same day.** A master/detail list whose
right pane says which of the three books have moved, because "COMPLETED" alone
does not tell a reader whether anything reached the shelf or the customer. The
editor is a document picker rather than a form: a return line belongs to a line
of a delivery note or a sales invoice, so there is nothing to type that the
source does not already say except how many came back and how many of those are
still sellable.

**It found a live bug in the sales invoice router**, which declared its list and
create routes at `"/"` while the other fourteen modules use `""`. FastAPI
therefore served them at `/api/v1/sales-invoices/` and answered
`/api/v1/sales-invoices` with a 307 -- and `api_client.dart` sets
`followRedirects = false`, so **every desktop call to list or create a sales
invoice failed** with "Request failed (307)". The Sales Invoices workspace had
been in that state.

**Import and export were built on 2026-08-15**, closing the last gap in this
module. `GET /sales-returns/export` answers CSV; `POST /sales-returns/import`
takes a JSON batch of up to 500. Both take the seeded `SALES_EXPORT` /
`SALES_IMPORT` codes, so no permission or migration was needed.

**JSON only, and that is the decision.** A return line names the delivery-note
or invoice line it came off, so a flat CSV row cannot express one without
inventing a way to identify the source -- and a source picked wrongly puts the
stock back against the wrong document. Purchase returns took the same view.

**The batch lands whole or not at all.** `create_return` commits, so a loop
over it is the shape that made the branch and warehouse imports impossible to
finish: a batch whose later row is refused returns an error with the earlier
rows already written, and the corrected file then fails on those as
duplicates. Creation is split into `_stage_return`, which builds without
committing, and `create_return`, which stages one and commits. The import
stages every record and commits once.

Reverting to the naive loop and re-running `test_a_refused_batch_leaves_nothing_behind`
shows the failure is worse than "half of it went in": the refused record leaves
its **own header flushed on the session** as well, so the caller inherits two
rows where they should see none. That is why the import rolls back rather than
merely declining to commit.

## 10. Quotations -- a price offered before anything is sold

**Built on 2026-08-14** as `app/quotation` plus `desktop/lib/ui/quotations/`.

The Sales module had advertised a Quotations tab since it was written with
nothing behind it: no table, no endpoint, and a `SALES_QUOTATION_CREATE`
permission code seeded, granted to `SALES_MANAGER` and `SALES_EXECUTIVE`, and
enforced nowhere.

**The defining property is what a quotation does not do.** It reserves no
stock, moves no customer balance and writes no journal -- and a test asserts
exactly that, because a document that looks like an order is one somebody will
assume has committed the goods. Everything the firm actually promises happens
at conversion, through `SalesOrderService.create_order`, so credit control, tax
resolution and unit conversion are applied when the order exists rather than
months earlier when somebody quoted a price.

The one thing a quotation owns that an order does not is `valid_until`. Expiry
is **derived from the date rather than stored**: nothing sweeps the table at
midnight, so a stored flag would be stale for as long as nobody had run the
sweep, and a lapsed quote would convert at last year's prices. An expired
quotation cannot be sent, accepted or converted; `is_expired` and `can_convert`
are answered by the server on every response so the client cannot disagree with
it. The desktop badges EXPIRED separately from the status, because `SENT` reads
identically the day before and the day after the prices lapse.

`decline_reason` is kept because "why are we losing quotes" is a question no
total answers, and `/reports/conversion` is the only report that joins what was
offered to what was sold -- a quotation register says one half and an order
register the other.

**Import and export were built on 2026-08-15.** `GET /quotations/export` and
`POST /quotations/import`, JSON batches of up to 500, on the seeded
`SALES_EXPORT` / `SALES_IMPORT` codes. Staged and committed once, for the same
reason sales returns are — see §9.

The export carries **`is_expired` as its own column**. Expiry is derived from
`valid_until` rather than stored, and a quotation reads `SENT` the day before
and the day after its prices lapse, so a pipeline exported on status alone
cannot tell a live offer from a dead one. The test asserts exactly that: two
quotations both `DRAFT`, one expired and one not.

**A duplicate document number is a 409 now, not a 500.** Both modules added
their header row with a bare `session.flush()`, so a clash with an existing
number raised `IntegrityError` straight out of the service, past the
`_flush_or_conflict` translator waiting at the end of the same method. It was
reachable before this change through an explicit `quotation_number`, and a
batch import is the likeliest way anybody hits it.

**The desktop dialog takes as many lines as the offer needs**, as of
2026-08-15. The backend has always accepted up to 1,000 and the form wrote
exactly one, so a quotation for two products could not be raised from the
desktop at all.

Three decisions in it worth keeping:

- **A line owns its own controllers.** `_LineDraft` holds the product and the
  three text fields together, so a row removed from the middle takes its text
  with it. Three parallel lists indexed by position is how deleting a row
  leaves the quantity of the row below it behind, and the test removes the
  middle of three lines specifically to catch that.
- **Every line shows what it contributes**, beside the offer's total. One
  total does not say which of five lines was mistyped.
- **The last line cannot be removed**, and the control says why rather than
  letting the save fail: the server requires at least one, and abandoning a
  quotation is what Cancel is for.

**Revising seeded only the first line before this**, which is a silent deletion
rather than a missing feature -- the update replaces the whole line collection
with what is sent, so revising a two-line offer through the desktop threw the
second line away. `QuotationLine` also parsed only `discount_amount`, never
`discount_percent`, so a discounted line came back into the form at full price
and was re-sent that way; the model carries the rate now.

**Still not built, deliberately:** PDF rendering and emailing a quotation to
the customer. `RESET_ORDER` in
`scripts/generate_transaction_history.py` gained the four new tables, the same
step sales returns needed.

## 11. No tab advertises what the platform cannot open

**Done on 2026-08-14.** Twenty-one tabs and navigation nodes were declared
`available: false` -- rendered, greyed out and disabled. A tab in that state
for a year reads as broken, not as roadmap.

Each was checked against the running server's OpenAPI, and they split three
ways:

- **Fourteen removed** because nothing was behind them. `user-audit`,
  `branches-departments` and the Sales module's `sales-orders`,
  `delivery-notes` and `sales-invoices` duplicated modules with their own place
  in the sidebar; `dashboard`, `gst`, `background-jobs`, `system-settings`,
  `api-monitoring`, `approval-workflows`, `document-templates` and
  `notification-templates` had no endpoints at all, as did the four Licensing
  tabs (§2 is still parked).
- **Two built**, because deleting them would have hidden a working capability
  rather than stopped advertising a missing one:
  - **Financial years** (`/api/v1/finance/financial-years` + `accounting-periods`)
    decides whether a document can be posted at all. The refusal "no open
    accounting period" had nowhere to send anybody. The screen lists years with
    how many of their periods are open -- the fact that decides it, which the
    year's own dates do not say -- and opens or closes a period for whoever
    holds `financial_year`.
  - **Numbering series** (`/api/v1/document-framework/numbering-rules`) is the
    rule behind every document number. Read-only on purpose: `next_sequence` is
    a counter the server advances under a lock, and a form that let somebody
    set it back would mint a number a document already holds.

`test_configuration_screens_test.dart` now fails the build if any catalog tab
is `available: false`, and if a navigation node draws a path its module has no
tab for -- which `numbering-series` did, landing the reader silently on the
first tab instead.

**Building the numbering screen found a defect in the preview.** The endpoint
let `financial_year_label` fall through as None, and the scope signature then
used the plain calendar year: a preview read `QT-2026-000001` for a number that
would be issued as `QT-2026-2027-000001`. Showing the wrong number is the one
thing a preview must not do. The label is now derived once, in `_year_label`,
and used by both `preview_number` and `reserve_number` so the two cannot
disagree -- reading `firms` through `FirmMetadataReader`, because that table
lives only in the platform schema and a direct query from a tenant session
answered 503.

## 12. The lint debt is gone, and what it uncovered

**Done on 2026-08-14.** `ruff check .` and `black --check .` are clean across
the whole tree for the first time -- `app/`, `tests/`, `scripts/` and
`alembic/`. The 181 findings `CLAUDE.md` described as permanent debt were 81
long lines, 41 undocumented functions, 8 undocumented classes, 32 missing
annotations and a handful of unused names.

Nothing about behaviour moved, and that is checked rather than asserted: every
string literal and f-string in the four seed scripts was compared by AST before
and after, and every SQL statement in the six re-wrapped migrations is
byte-identical once whitespace is normalised. The forty-one migration
docstrings are derived from each migration's own module docstring, so they say
what the migration does rather than "Apply the migration" forty-one times.

**`scripts/generate_sample_data.py` was already unrunnable**, which is why
nobody had noticed. It imported `ProductUomConfig`, deleted in `b569479` when
its fourteen columns were folded back onto `products` -- that commit's message
says "nothing outside `app/uom` referenced the model", and this script
referenced it four times. It has raised `ImportError` on every run since
2026-08-12 while `CLAUDE.md` documented it as a primary command. The unit slots
are written onto the product now, and the script starts.

**It finishes now.** The `delete_order` tuple is gone: the order is derived
from `Base.metadata.sorted_tables`, which already knows the dependency graph,
reversed. It cannot go stale -- a table added tomorrow is in it the moment its
model is imported -- and the 61 missing models are no longer a category of
problem. `PRESERVED_TABLES` names the fourteen exceptions and says why each
survives.

**The hand list was not the whole story.** The delete was also unqualified,
while the seed session runs with `search_path = platform, firm_shared, public`.
A table that exists in both schemas -- and `product_valuations` is one --
resolved to the platform copy, which is empty, while the firm_shared rows
survived to break the next foreign key. That is why the list appeared to work
for years: it worked for tables that live in one schema only. Each schema is
now cleared by name, in full, before the next.

Proven by running it twice: a second `--yes` succeeds, which it could only do
if the first run's reset cleared everything. A `reset` leaves nothing behind
except the fourteen preserved tables and the six that
`seed_uom_reference_data` immediately re-seeds.

**One list of model modules**, `app/core/database/all_models.py`. Alembic's
`env.py`, `tests/conftest.py` and the seed script each kept their own copy, and
`CLAUDE.md` carried a standing instruction to keep two of them in step by hand
-- the shape of a rule that gets forgotten, and it was.
`tests/unit/test_schema_registry.py` fails the build if a module under
`app/*/models/` is missing from it.

## Two things this uncovered, both now fixed

**No attribute is mandatory for every firm.** `20260801_0011` seeded four
product attributes with `mandatory = True` and no category or profile scope --
EXPIRY_DATE, BATCH_NUMBER, MANUFACTURER and IMEI. An unscoped mandatory
attribute applies to **every product of every firm**, so a pharmacy could not
save a product without an IMEI and an electronics distributor could not save
one without an expiry date; `AttributeService` refuses the write. It blocked
product creation outright on any database built from migrations, and had gone
unseen because the demo seeder overwrote three of the four flags on the way
past and nobody could get to a freshly-migrated catalogue.

IMEI is one of the seven features `20260810_0059` marks
`is_implemented = false`, so a roadmap attribute was compulsory for every
product in the platform. `20260815_0087` clears the flag; the seed no longer
sets it. Where an attribute really is required, `category_attribute_rules` says
so per business profile and category -- which is what the demo seeder does, and
what the rows in the same migration already did.

**The reset now reaches every firm store.** It cleared `platform` and
`firm_shared` and left the dedicated ones alone, while deleting the `firms`
rows those stores' data belonged to. WHOLE01 ended up with eighteen customers
belonging to firms that no longer existed and a receivable control account
234,000 short of what they said they were owed. The stores are read from the
registry first -- it is the thing that says where they are, and it is about to
be deleted -- then cleared in the same derived order, and their UOM reference
data is re-seeded because a store with no units cannot hold a product.

**`seed_multi_firm_demo.py` seeds a clean database now.** Its UOM codes are
corrected too: it asked for `GRAM` and `TABLET`, and the catalogue has `G` and
had no tablet at all. `TABLET` joins the catalogue below `STRIP`, which is what
a strip is ten of.

Proven end to end: `generate_sample_data.py reset --yes`, then
`seed_multi_firm_demo.py`, then `verify_sample_data.py` -- **all three stores
hold together**, from a full reset, for the first time.

## 13. An opening balance reaches the ledger

**Done on 2026-08-15.** A customer's opening balance moved their account and
wrote no journal, so a firm's customers could owe it 885,000.00 against a
receivable control account of zero. `CustomerService` wrote the balance and a
receivable transaction and stopped there -- the same shape as the credit note
that did not post until 2026-08-14, and the gap `verify_sample_data.py` exists
to find.

**The counterpart was already decided.** `post_opening_stock` put opening
balance equity in the chart for exactly this and said so: "a firm that later
records opening receivables or opening cash has somewhere consistent to put
them." A day-one receivable arrived from nowhere the ledger can see, and what
it represents is what the owners brought into the business, so the receivable
is debited and equity credited. A customer in credit swaps the legs -- the firm
owes them, and nothing about that is a receipt.

**It is refused rather than skipped** when the firm has no chart of accounts or
no open period. A balance nobody can book is one the firm should not be told it
has recorded, and the message says which setup is missing. The customer itself
still opens; it is the balance that cannot.

Three paths make a balance stop being true, and all three mirror the entry:
revising one, and deleting the customer -- found by driving the API, where two
probe customers left 50,000 in the ledger after being deleted.
`customer_receivable_transactions.journal_entry_id` (`20260815_0088`) is what
lets them: searching the ledger by source module would not tell an opening
balance from the credit notes and refunds the same customer raises.

**Two seeders were writing balances nothing backed.**
`generate_sample_data.py` created firms with no chart of accounts at all --
they have one now, for the financial year that contains today, since an opening
balance posts on the day it is recorded. `seed_multi_firm_demo.py` hand-posted
50,000 of invoice and 20,000 of receipt onto its first customer through
`CustomerService.post_receivable_transaction`, the path `CLAUDE.md` names as
the one the two books drift by every rupee of; it left MEDI01 owing 30,000
nobody had journalled, on every seed. Those lines are gone: two financial years
of generated trading give every customer a real balance built from documents
that do post. If the demo ever wants an unapplied advance to show, raise it
through `ReceiptService` so it reaches the ledger like any other money.

`seed_multi_firm_demo.py` also **provisions** the dedicated firms it creates.
`FirmService.create` records the intent and the storage is built by the
explicit provisioning action; reusing already-provisioned firms hid that, and
once the reset began deleting firms every request for WHOLE01 and ELEC01 was
refused.

Verified over HTTP: creating a customer with 25,000 moves Trade Receivables and
opening balance equity by 25,000 each, deleting them moves both back, and the
lifecycle nets to zero. The revise path was covered at service level only,
because the API returned no ETag to send back; that gap is closed below. **All three stores hold together** after a full reset and re-seed.

## 14. Emailing a document to the party it names -- planned in §51

Deferred by the owner on 2026-08-22, after printing was built: *"email sending
we will add to backlog and in future we will build."* Do not start it
unprompted; this section is here so the thinking does not have to be redone.

**Most of it already exists.** `GET /api/v1/sales-invoices/{id}/print` and
`GET /api/v1/purchases/{id}/print` return the finished PDF, and those same
bytes are what an email would attach -- the renderer was put on the backend for
exactly this reason. `document_states.allows_email` and
`document_timeline.email_recipient` are columns waiting for something to write
them, and `DocumentToolbarAction.emailDocument` still exists in the desktop
(removed from the purchase dialog on 2026-08-22 for having nothing behind it).

**What does not exist is everything about actually sending.** There is no SMTP
client, no mail configuration, and no notifications subsystem -- `app/common/notifications`
was one of the eleven docstring-only packages deleted on 2026-08-09 for
advertising a subsystem that was never built. Do not recreate it as an empty
shell.

### Four decisions, none of them technical

1. **Whose mail server?** A per-firm SMTP account means a customer sees the bill
   arrive from their own supplier, which is what a firm wants -- and it means
   this platform stores a mail password per firm. One platform relay is far
   simpler and makes every bill arrive from an address the customer does not
   recognise, which is how invoices end up in spam folders. The tenancy
   connection profiles in `AGENCY_TENANCY_CONNECTION_PROFILES` are the
   precedent for per-firm credentials that live outside the database.
2. **What happens when it bounces?** A send that fails silently is worse than
   no email at all, because the firm believes the customer has been billed. The
   answer needs a place for the failure to surface -- the document timeline is
   the obvious one, since `email_recipient` is already there.
3. **Attach or link?** An attachment is what a customer expects and what their
   accounts department files. A link means the platform is serving documents to
   the public internet, which is a different security problem entirely and
   needs signed, expiring URLs.
4. **Who may send one?** Printing is `*_VIEW`, because a printed bill shows
   nothing the screen does not. Emailing acts on the firm's behalf to somebody
   outside it, which is not the same permission.

### What it would take once those are answered

- SMTP settings per firm, credentials outside the database.
- A send record: what was sent, to whom, when, by whom, and whether it arrived.
  `document_timeline` already has the shape.
- A covering message per document type, which belongs beside the print template
  in `document_print_templates` rather than in a second table.
- The desktop button, which already exists as an enum member.

**Estimated as the same size again as printing was**, and most of that is the
first decision rather than the code.

## 15. A firm cannot be finished without running a script

**Closed 2026-09-08.** The remaining half landed the same day:
`GET /api/v1/finance/control-accounts` lists all 24 purposes with the account
each posts to and how many lines have posted there, `PUT
/api/v1/finance/control-accounts/{purpose}` re-points one, and **Finance ›
Control Accounts** is the screen (`ACCOUNT_VIEW` to read, `ACCOUNT_MANAGE`
to write, like the chart). Decisions 3 and 4 below were taken as: a purpose
with posted lines on its account is **held** -- re-pointing it is refused by
name with the count, since every existing line would stay put and two
accounts would each hold part of one story; a transfer entry and a new
account from the next period is the bookkeeper's way -- and **all 24 are
required**, which is what the readiness panel reports. The paragraph that
follows is the original statement, kept for the reasoning.

**Mostly closed 2026-09-08.** `POST /api/v1/firms/{id}/open-books` and
**Administration › Firms › Set up › Open the books** give a firm the default
chart, the current financial year, the journal and voucher types and all 24
mappings in one press, through the existing `seed_finance_setup`; and
`GET /api/v1/firms/{id}/readiness` behind the same panel says which of
seven steps a firm still lacks, before the first document. Of the four
decisions below, the first two were taken as written -- the screen builds
the chart, from the seed, and the job is the platform administrator's,
beside Provision storage. The third and fourth are still open, and so is the
screen they need: **a mapping cannot be re-pointed except through the
API**, and there is no per-purpose screen. What follows is the original
statement, kept for the two decisions it still carries.

A firm created through the product accepts masters and lets documents be
drafted, and then **refuses every posting action** -- approving an invoice,
completing a goods receipt. `DocumentPostingService` refuses rather than
guesses, and what it needs is a chart of accounts, a financial year, open
periods, journal and voucher types, and a mapped control account for each of
the **24 purposes** in `ControlAccountPurpose`.

**No screen and no endpoint reaches the mapping.** No path in the served
OpenAPI document contains `control`, and no file under `desktop/lib`
references one. The only code that writes `firm_control_accounts` is
`seed_finance_setup` (`app/finance/services/opening_setup.py`), whose only
callers are `scripts/generate_sample_data.py` and
`scripts/generate_transaction_history.py` -- both of which also create demo
trading history, so neither is something to point at a real firm.

The consequence is not a missing convenience. **Creating a firm is a
first-class product action that cannot be completed in the product**, and the
refusal it ends in reads as a broken firm rather than as an unfinished setup.
`scripts/check_firm_readiness.py` reports the gap; it does not close it.

### What already exists

`ControlAccountService` has the whole API surface this needs --
`mapping(firm_id)`, `resolve(firm_id, purpose)`, `assign(...)` and
`missing(firm_id, purposes)` -- and `seed_finance_setup` is idempotent over
groups, accounts and mappings. So this is a router, a screen, and the
decisions below; it is not new domain logic.

### Four decisions, none of them technical

1. **Does the screen only map, or can it also build the chart?** Mapping is
   useless on a firm with no accounts, and a brand-new firm has none -- so a
   screen that only maps leaves the same wall one step further along. Building
   one means shipping `seed_finance_setup`'s chart as a product default, which
   is a claim about how a firm's books should look. The alternative is
   requiring the chart to be entered by hand first, which is real work before
   the first invoice.

2. **Whose job is it?** Today it is nobody's, because it is nobody's *screen*.
   A platform administrator sets the firm up, but a firm's chart of accounts is
   the firm's own business and `FIRM_ADMIN` holds the `accounting` codes. If a
   firm administrator may map them, this needs a new permission code and a
   migration; if only the platform may, it belongs beside Provision storage.

3. **May a mapping be changed after documents have posted?** Re-pointing
   `INVENTORY` leaves every existing journal line on the old account, so the
   trial balance still balances while two accounts each hold part of one
   story. Options are to refuse once anything has posted, to allow it with a
   named warning, or to require a transfer entry.

4. **Is a partially mapped firm allowed to trade?** A firm that never sells on
   credit arguably does not need `LOYALTY_PAYABLE`. Today all 24 are required
   in practice because a document that reaches an unmapped purpose is refused
   at approval -- late, and to the wrong person. Deciding a minimum set, or
   reporting exactly which purposes a firm's own modules can reach, is the
   difference between a checklist somebody can finish and one they cannot.

### Sizing

Small once those are answered: a router in `app/finance` over the existing
service, a `ResourceDefinition` screen with the 24 purposes and an account
picker per row, and the readiness verdict on it so somebody can see when the
firm is done. The first decision is most of the work, as with emailing
documents above.

**Raised 2026-09-06**, after driving firm creation end to end and finding the
setup could not be completed. Documented meanwhile in section 3b of
`docs/platform-administration-guide.md`, so the gap is at least visible to
whoever hits it.

## 16. A firm cannot configure its own custom fields

**Status, 2026-10-02:** the lifecycle guards are built -- a field's type cannot change and it cannot be deleted while it holds values; making it mandatory warns how many records lack it. The per-firm ownership part and the two decisions above are still open (`docs/OWNER_DECISIONS.md` B2).

`FIRM_ADMIN` writes its own tax rules, UOM conversions and numbering series,
and cannot add a single field to its own products. **27 of the 29 routes in
`app/business/api/router.py` take the platform designation**; the two
exceptions are `/active-features` and `/active-modules`, the read-only lists
the desktop draws menus from. So six Administration tabs are hidden from a
firm administrator, and unhiding them would hand over six screens where every
button answers 403 -- the desktop is faithfully reflecting the server.

### Who should get what

Devolve the screens that describe **one firm**; keep the ones that describe
the **shared catalogue**.

| Screen | Firm admin | Why |
| --- | --- | --- |
| Attribute Definitions | **gain** | The extra fields on this firm's own products -- no more structural than the tax rules they already write. |
| Mandatory Attributes | **gain** | Which fields a category insists on; meaningless apart from the definitions. |
| Profile Assignment | **read** | A firm-level fact, but changing it re-scopes every definition at once. |
| Business Profiles | no | One `WHOLESALE` row serves every wholesale firm. |
| Feature Management | no | Shared catalogue, and `is_implemented` is a fact about the codebase. |
| Module Configuration | no | Which modules a firm may operate is closer to commercial than operational. |

### The gate that matters more than the role

Raised by the owner, and the sharper half: **once a firm is trading, changing
its fields loses work** -- and that risk does not depend on who clicks. A
platform administrator breaks it exactly as thoroughly, today, with nothing in
the way.

*Before any value exists* every edit is safe. *Once values exist*: adding a
field and renaming a label stay safe (the code is the identity); **changing a
data type and deleting must be refused**; making a field mandatory must warn
with the count of records that would fail their next save.

**None of that exists.** `update_attribute` is a `setattr` loop over
`model_dump(exclude_unset=True)`, so a type change leaves values stranded in
`value_text` while every read looks in `value_number` -- orphaned rather than
deleted, which is worse because nothing reports it. `delete_attribute` is a
bare soft delete with no check for values, the same trap the geography masters
carry: a RESTRICT constraint is not a guard on a soft-deleted table. And the
mandatory flag has already caused this outage once -- `20260801_0011` seeded
four attributes mandatory with no scope and broke product creation on every
freshly migrated database until `20260815_0087` cleared it.

### Why the permission gate cannot simply be opened

Neither `attribute_definitions` nor `category_attribute_rules` carries a
`firm_id`, and neither is in `_PLATFORM_TABLES` -- so the rows live once per
**store** while being identified per **profile**. Measured across all four
demo firms on 2026-09-06:

```
firm      mode      store             definitions  mandatory rules
ELEC01    DATABASE  electrolink_ops             6                2
FOOD01    SHARED    firm_shared                 6                8
MEDI01    SHARED    firm_shared                 6                8
WHOLE01   SCHEMA    wholesale_hub               6                2
```

FOOD01 and MEDI01 are not showing similar numbers, they are showing **the same
rows**. A pharmacy adding "Drug schedule" would add it to the food
distributor, and `SHARED` is the mode every new firm gets by default. `code`
is unique per store as well, so two shared firms cannot hold one field name
with different meanings.

### The work, in order

1. **`firm_id` on both tables**, nullable, `NULL` meaning platform-wide.
2. **Copy the shared rows per firm** -- decided by the owner. Every firm in a
   shared store gets its own copy, so no firm loses a field and each can
   diverge. A few duplicate rows against firms overwriting one another.
3. **Widen the unique key**: `code` unique per firm, as a partial index over
   live rows, the shape `UQ_firms_code_active` already uses.
4. **Scope the service** on the caller's firm; a `NULL` row stays visible to
   everyone and editable only by the platform.
5. **Add the lifecycle guards** in the service, where no client can bypass
   them.
6. **Seed permission codes** for the two devolved screens, grant to
   `FIRM_ADMIN` with a migration for existing databases, then take the tabs
   off `PLATFORM_VIEW`.

### Two decisions still open

- **May a firm administrator change their own business profile?** Drafted as
  read-only. It is a firm-level fact, which argues for devolving it, but it
  re-scopes every custom field and toggles features, so it behaves like a
  setup-time decision that should need the platform once trading starts.
- **Refuse a type change, or convert the stored values?** Refusing is honest
  and cheap -- add a new field, retire the old, history stays readable.
  Converting is friendlier and fails silently, per row. Recommend refusing
  first.

**Raised 2026-09-06** by the owner asking why a firm administrator cannot set
up their own firm. Not started.

## 17. The duplicated catalogue — low priority, and mostly decided

**Status, 2026-10-02: option 1 built.** A profile written at runtime -- create, update, delete, features, modules -- is written to every store, each reported WRITTEN or FAILED with the reason (`app/business/services/profile_replication.py`). Features and modules created at runtime are still not copied themselves.

**Priority: low. Not mandatory.** Raised as a question about duplication on
2026-09-07 and largely answered in the same conversation; recorded so nobody
re-derives it.

### The observation

`business_profiles`, `business_features`, `business_modules`,
`profile_features` and `profile_modules` are pure reference data that no firm
edits, and every firm store carries its own complete copy -- 12 profiles, 21
features and 75 mappings per store, identical everywhere. `firms` is the only
platform table in the picture, which is why
`firm_business_profiles.firm_id` carries no foreign key.

The obvious tidy-up is to move the catalogue into `platform`, read it through
`platform_reader()` the way `users` and `firms` are already read, and cache it.
That would also let `firm_business_profiles` become a plain platform table with
two real foreign keys, which removes the unenforced cross-store reference
entirely and turns "which profile does each firm use" from a loop over stores
into one query.

### Why it is not being done

**A firm store must keep working when the platform database does not.** That
is the point of `DATABASE` mode -- a firm on its own server, possibly a
different server, serving its own requests. Moving the catalogue would put the
platform database on the request path for rendering a product form, so a firm
that is fully self-sufficient today would stop being so. The owner confirmed
on 2026-09-07 that this isolation is wanted, which settles it: the duplication
is buying something real, and the cost of keeping it is drift and a migration
that has to reach every store, both of which are already handled by
`scripts/migrate_all_stores.py`.

**And the attributes are not catalogue at all.** `attribute_definitions` and
`category_attribute_rules` are the firm's own -- the fields *this* firm records
against *its* products -- so they belong in the firm's store whatever happens
to the profiles above. §16 is where that goes, and it wants a `firm_id` on
both, which is the opposite direction from consolidating.

### The part that is a real defect

One piece survives the decision, and it is small and worth doing on its own.

**A profile created at runtime exists in exactly one store.** The twelve
seeded profiles agree across every store only because the migrations insert
**hardcoded UUIDs** (`10000000-0000-0000-0000-00000000000x`) -- verified
2026-09-07, every store holding the same twelve codes with the same ids.
Nothing maintains that invariant for a profile created through
`POST /business-framework/profiles`, which runs on `get_db` and so lands in
whichever firm store the caller happened to be in, with a random id.

The consequence is reachable from the desktop. The Profile Assignment
dropdown reads `/business-framework/profiles` from the **caller's** current
firm store, while `assign_profile_to_firm` validates with `get_profile()` on
the **target** firm's store. So a platform administrator working inside
WHOLE01 who writes a "Bakery" profile is offered it, and assigning it to
FOOD01 is refused as not found -- a profile visible in the list and
unusable, with a message that describes neither cause nor cure.

Read from the code rather than driven, deliberately: reproducing it writes a
profile row into a real store.

Three ways out, cheapest first, none of them started:

1. **Write a new profile to every store**, the way a migration does. Keeps the
   invariant the design already relies on, and makes the reliance explicit
   rather than accidental.
2. **Refuse to create one outside the platform context**, and say so -- honest,
   and it closes the hole without new machinery, at the cost of a firm never
   getting its own profile.
3. **Move only `business_profiles` to `platform`** and have
   `attribute_definitions` reference the profile **code** rather than its id --
   a stable string travels across stores where an id does not. This is the
   narrow version of the refactor rejected above and reintroduces the same
   dependency, so it is listed last.

Until one is chosen, a profile created at runtime is safe to use only within
the store it was created in, and the seeded twelve are safe everywhere.

## 25. The branch and warehouse forms popped on a missing required field -- fixed

Found in manual testing on 2026-09-10. Saving a new warehouse with a required
field empty **closed the form** and surfaced the server's refusal as a toast
against no form, instead of keeping the dialog open and pointing at the field.

**The cause.** Neither the branch nor the warehouse dialog validated its
required fields client-side. The `_field` helper built a plain `TextField`
(no validator), and the Save button popped with `Navigator.pop(context,
_payload())` after only checking the custom fields. So an empty Code or Name
went to the server, which answered 422, by which point the dialog was gone.

**Fixed here (desktop only).** Save now checks Code and Name first; a code that is empty, shorter than
two characters, or not `^[A-Z0-9_-]+$` (the rules the server enforces, and
the code is uppercased on the way out) and an empty name each set an inline
`errorText` under that field and return without popping, so the dialog stays
open and names what is wrong rather than letting the server refuse it after
the form has closed. Both dialogs
share the same `_field` helper and the same flaw, so both were fixed together
(the user hit it on warehouses). `branch_address_test.dart` clears a required
field, saves, and asserts the dialog stays open, the field is highlighted,
and nothing reached the server -- then that typing a value and saving again
goes through.

Note the branch dropdown on the warehouse form was already handled: Save is
disabled until a branch is chosen, so that required choice never reached this
path. This change is about the free-text required fields.

## 26. Vendor Categories and Vendor Types opened on "coming soon" -- fixed

Found in manual testing on 2026-09-11 (test plan case 5.2). Masters →
Vendors → Categories rendered the placeholder "Vendor Categories is coming
soon. The current API does not provide vendor categories operations", and
Types did the same. The server answered a row for every firm; the desktop
never asked it.

**The cause.** A workspace renders its tab by `switch (tabId)` and falls back
to the placeholder for an id it does not name. The two tabs were declared
under the **Masters** module in `module_catalog.dart` on 2026-08-22 (#132),
and their `ResourceManagementPage` bodies were written into the
**Administration** workspace's switch in `desktop_shell.dart` -- a module
they are not tabs of. So the sidebar entry existed, the permission gate
passed, and the screen it opened had no case for it. Unreachable from the day
it was written; `vendor_classification_test.dart` passed throughout because
it builds the `ResourceDefinition` directly and never asks which workspace
would show it. The same PR's own note recorded that the two masters had
"no caller" before it -- they gained one in the API client and still had no
screen anybody could reach.

**Fixed here (desktop only).** The two cases moved into `_MastersWorkspace`,
with their heading, description and breadcrumb entries.
`test/workspace_tab_bodies_test.dart` is the guard: for every module whose
workspace switches on `tabId`, every catalog tab must have a case in **that**
workspace's class body, or-patterns included. A source check, because the
workspaces are private widgets nothing in the suite can build. Reverting the
move fails it naming both tabs.

## 27. The product form never showed the Attributes tab for an existing product -- fixed

Found in manual testing on 2026-09-11 (test plan case 5.5). Opening `DETER1K`
in WHOLE01, in view or in edit, showed General, UOM & Size, Pricing, Tax,
Images, Attachments, Audit and History -- and no Attributes tab, although the
server offers two optional fields for its category.

**The cause.** The product's custom fields hang off `category_attribute_rules`,
so `GET /products/metadata` answers a read that names no `category_id` with
**no** attribute at all (`_category_attribute_ids` returns two empty lists).
The workspace fetches that firm-wide read once at bootstrap and hands it to
the dialog, which hides the tab when the allowed set is empty. Only a category
*changed* in the form asked again with the category named -- the dialog's
`onMetadataForCategory` callback was wired to the dropdown and to nothing
else -- so a product opened with its category already set never asked, and
the tab never appeared. A new product shows the tab only once a category is
chosen, which is right: the fields depend on it.

**Fixed here (desktop only).** `ProductWorkspaceDialog.initState` now asks
`onMetadataForCategory` for the product's own category when it has one, the
same call the dropdown makes, and applies the answer to the tab strip and the
attribute controllers. A failed read leaves the tab hidden rather than
refusing to open the form. `test/product_attributes_tab_test.dart` opens an
existing product in edit and in view and expects the dialog to ask for its
category and show the tab, and a new product with no category to do neither.

Not changed, and worth deciding: a product's fields are resolved from
category rules alone, while customers, vendors, branches and warehouses read
`/attribute-definitions/applicable`, which also offers definitions that are
unscoped or scoped only to the profile. For WHOLE01 the applicable set is six
PRODUCT definitions and the CORE_PRODUCTS rules name two of them (PACK_SIZE
and COUNTRY_OF_ORIGIN), so the product form offers two where the other forms
would offer six -- the rule is doing real narrowing, which is the design; but
a definition added without a rule reaches every other form and never the
product's.

**And a second half, deeper: the fields could not be resolved at all.** The
form read its custom-field catalogue from `GET /attribute-definitions`, which
is `PlatformPrincipal` -- a firm administrator gets 403. The desktop swallowed
the 403 and left the catalogue empty, so even once the tab showed, every field
rendered "Unknown attribute definition: <id>": the metadata named ids the form
had no definition for. The controller now reads
`/attribute-definitions/applicable?entity_type=PRODUCT`, gated on firm
membership, the same door the customer and vendor forms already use. Driven
against the running backend: the raw endpoint 403s for `whole01.admin` while
the applicable one returns all six PRODUCT definitions, including the two the
CORE_PRODUCTS metadata names. `product_controller_definitions_test.dart` pins
that the controller asks the applicable endpoint and not the platform one.

Note this is also why 5.5's profile-gating reads correctly: `/products/metadata`
already returns only the fields the firm's profile enables (WHOLE01/WHOLESALE
gets Pack Size and Country of Origin, not the batch/expiry/warranty fields),
so once the tab shows, the fields in it are the right set.
## 28. A warehouse could not be saved without a capacity -- fixed

Found in manual testing on 2026-09-11 (test plan case 5.7). Renaming a
warehouse and saving answered a validation error, and so did creating one;
the branch form beside it worked.

**The cause.** The warehouse dialog sent `capacity` as the text of its box,
so a blank box sent `""`; the server reads the field as `Decimal | None`, and
`""` is neither, so it answered 422 `Input should be a valid decimal`. Every
warehouse save from the desktop with no capacity stated had been refused this
way since the first desktop commit on 2026-08-06 -- `capacity_unit` had a
normaliser that turned a blank into null, `capacity` did not. The widget test
never saw it because its fixture warehouse carries `capacity: '500'`; the
import dialog was never affected, because it omits a blank cell rather than
sending it.

**Fixed here, both sides.** The dialog sends null for a blank capacity and a
blank unit, the way it already did for the address lines. And the schema
reads a blank string as no capacity, so the import file and any other client
stand on the same footing -- a stated figure still has to parse.
`branch_address_test.dart` clears both boxes and asserts null travels, and
that a stated `500` still travels as typed;
`test_branch_warehouse_partial_update.py` asserts the schema's three answers.
## 29. Screens with a page but no way in -- fixed

Found in manual testing on 2026-09-09: a firm administrator, and a platform
administrator in a firm, could not reach **Customer Statements** from the
Masters sidebar. It was not a permission or a mode -- the screen simply had
no navigation entry.

**The cause.** `ModuleCatalog.navigationChildren` is hand-built for several
modules (`_mastersNavigation`, `_administrationNavigation`,
`_inventoryNavigation`, and the purchase/goods-receipt builders) and
auto-generated from the tab list for the rest. A hand-built builder can
silently omit a tab that is otherwise fully defined -- permission-gated, and
wired to a page in `desktop_shell.dart` -- leaving the screen unreachable
from both the sidebar and Ctrl+K, for every role.

**Three real orphans, all fixed here.**

- Masters **Statements** (`customer-statements`) and **Loyalty** (`loyalty`)
  -- defined, gated on `CUSTOMER_VIEW` / `LOYALTY_VIEW`, wired to
  `CustomerStatementPage` and the loyalty page, listed nowhere. This is what
  blocked plan items 4.7 and 4.8.
- Inventory **Physical Count** (`physical-counts`) -- gated on
  `INVENTORY_VIEW`, wired to `PhysicalCountPage`, listed nowhere.

**The guard.** `desktop/test/module_catalog_navigation_test.dart` walks every
module with all its tabs visible and fails the build when a tab has no
navigation path, unless it is recorded in `_reachedElsewhere` with a reason.
One legitimate exception is recorded: `permissions` shares the Roles &
Permissions tab-group screen and is reached by the in-page tab strip rather
than a leaf of its own. The guard is the durable half -- the same omission
had already happened twice before anybody noticed.
## 30. A customer could not be put in a group from the UI -- fixed

Found in manual testing on 2026-09-09 (plan item 4.9). Customer groups
(Retailer, Wholesaler, Institution) could be created from the **Groups**
button, and `customer_group_id` was accepted by the customer create/update
API from the start -- but the customer form had **no control for it** and
never sent it. So a group could be defined and never assigned, and the
customer-group tier of `resolve_line_discount` could populate for nobody.
Same "wired in the API, no button" class as the settlements and loyalty gaps.

**Fixed here (desktop only).** The customer form's Financial tab gains a
**Customer group** dropdown, loaded from the existing `customerGroups`
client method via a `loadGroups` callback the way routes and places are
loaded. `Customer.customerGroupId` is parsed from the response, the dropdown
shows the current group and the firm's groups plus a "No group" choice, a
stored id not in the loaded list stays selectable (the geography-picker
trap), and the save payload carries `customer_group_id` -- null when "No
group", so it clears any prior one. Driven end to end against a running
backend: assigning WHOLE01C03 to Wholesaler returned 200 and persisted.
`customer_group_assignment_test.dart` pins the dropdown and the payload.

No backend change: the API already accepted the field; only the door was
missing.

## 31. Found in manual testing

**Status, 2026-10-02:** the last two leftovers are fixed -- the territory export carries `CustomerCodes` (quoted) so a round trip keeps the shops (31.5), and the features picker marks what is not built yet (31.6).

Items raised by the owner while driving `docs/MANUAL_UI_TEST_PLAN.md` by
hand. Each records what was seen, what the plan expected, and the decision
the owner has taken, so a fix does not re-open a question already answered.

### 31.1 A locked account should say it is locked (2026-09-09, plan item 2.7) -- fixed the same day

**Done.** `AccountLockedError` (`account_locked`) is raised on *any* attempt
against a locked account, before the password is looked at, saying how many
whole minutes are left; the fifth wrong password, the one that locks, says
so too. Driven against a running server: attempts one to four and an
unknown address still answer "Invalid email or password."
`test_identity_hardening.py` pins both halves. **And the screen counts it
down** (same day, on the owner's next observation that the minutes quoted
were the minutes at the time of the click): the refusal carries
`retry_after_seconds` and `locked_until` in its details, `SessionController`
turns that into `lockedUntil`, and the sign-in banner ticks to zero and
then says the lock has lifted -- `login_screen_test.dart` drives the clock.

**Seen.** Five wrong passwords lock the account for 15 minutes
(`AGENCY_SECURITY_MAX_LOGIN_ATTEMPTS`, `AGENCY_SECURITY_LOCKOUT_MINUTES`).
The sixth attempt with the **correct** password is refused with the same
"Invalid email or password." as the five before it, and nothing on the
screen says the account is locked or when it will open. Driven on
`whole01.admin` and `master.ops`; `login_history` recorded the fifth
attempt as `locked` and the sixth as `account_locked` exactly as the plan
says, so the server is doing what was designed.

**Why it is that way.** `IdentityService.authenticate` raises one message
for every refusal on purpose: a distinct lockout message tells an outsider
that the address has an account and that they have found the threshold.

**Decision.** The owner wants a person who types the right password into
a locked account to be told to try again after the lock lifts -- "try again
after 15 minutes", or the time it opens -- because as it stands a genuine
user has no way to tell a lockout from a typo and keeps trying, which
extends nothing but their confusion. The address-disclosure trade-off is
accepted for the lockout case only: the ordinary wrong-password refusal
stays as it is.

**The work.**

- In `authenticate`, the `locked_until > now` branch raises its own
  message carrying the minutes remaining (computed with `utc_now()`, never
  the server clock), with a distinct error code so the desktop can tell it
  apart. Keep writing `account_locked` to `login_history`.
- Decide whether the message appears on *any* attempt against a locked
  account or only when the password was correct. The second discloses
  less, but the password has to be verified to know, which is the timing
  the equal-cost refusal exists to hide; the first is simpler and is what
  most products do. Recommendation: any attempt.
- `auth_screens.dart` shows the message as the server sent it, and
  `login_screen_test.dart` pins it; `test_identity_hardening.py` covers the
  server branch and that the wrong-password message is unchanged.
- `docs/MANUAL_UI_TEST_PLAN.md` item 2.7 changes its expected result from
  "the same message" to the lockout message.

### 31.2 A deactivated or expired account should say so (2026-09-09, plan item 2.10) -- fixed the same day

**Done.** `AccountInactiveError` (`account_inactive`) and
`AccountExpiredError` (`account_expired`), on login and on token refresh.
`ApiException.code` carries the server's code to the desktop, and a refresh
refused for an account state leaves the message on the sign-in screen as a
notice -- an ordinary token expiry stays silent.
`account_state_notice_test.dart` pins the desktop half.

**Seen.** Untick **Active** on a user and sign in as them: refused with
"Invalid email or password." The history records `account_unavailable`,
as the plan expects, but the person at the login screen is told nothing
they can act on -- their password is right, and the only message says it
is wrong. The same branch covers an account whose **Expires at** has
passed.

**Decision.** The owner wants the refusal to name the state: the account
is inactive, or has expired, and an administrator has to reopen it. This
is the second half of the decision taken in 31.1 -- one message for every
refusal was deliberate, so that an outsider cannot learn which addresses
have accounts, and the owner accepts that disclosure for the *state*
refusals (locked, inactive, expired) while keeping the wrong-password
message as it is.

**The work.** Same shape as 31.1 and best done with it: the `unavailable`
branch in `IdentityService.authenticate` raises its own message and error
code, distinguishing inactive from expired since the administrator's
remedy differs (retick Active, or move the date). The token-refresh copy
of the check at the same place in the service needs the same message, or
a person signed in when the account was closed sees the old one.
`auth_screens.dart` shows the message as sent; `test_identity_hardening.py`
covers both states and that the wrong-password message is unchanged;
plan item 2.10 changes its expected result.
### 31.3 Document views show raw UUIDs, not names (2026-09-09, plan item 3.3)

**Seen.** Opening a sales invoice shows the line's **product** and **tax
profile** as raw UUIDs (`cd6667a7-...`, `6fc6977b-...`) and the header names
no **customer** at all. Found while verifying firm isolation -- the customer
was the field that would have confirmed it on screen.

**Scope -- it is systemic.** All six document views share the generic
`DocumentViewDialog`, and every one feeds `product_id` straight to the
screen: sales invoice, sales order, delivery note, purchase invoice, purchase
return, goods receipt. Two separate gaps behind it:

1. **The party name is missing from the response.** `SalesInvoiceResponse`
   (list and detail) carries `customer_id` only -- no `customer_name`. The
   two `customer_name` fields in that schema module belong to
   `BillableDocument` and the outstanding report, not the main response.
2. **Line names are missing everywhere.** No line response schema carries
   `product_name`, `tax_profile_name`, or a UOM code -- only ids. So even a
   perfect client has nothing but the id to show.

**Done now (the customer half of the sales invoice).** 31.3 tracks the rest;
the customer on the sales-invoice header is fixed separately today:
`SalesInvoiceResponse.customer_name` is populated from the existing
`_customer_name` helper, `DocumentHeaderSnapshot` gained a `party` /
`partyLabel` field that the header renders when set, and the sales-invoice
page wires it. The line names and the other five views are the remaining
work.

**The full fix.** Add denormalized display names to each line response
(`product_name`, `tax_profile_name`, a UOM code) across the ~six document
modules and populate them in each service -- the same denormalization the
customer name now uses -- then wire each of the six desktop views to show the
names instead of the ids. Batch the name lookups: `_customer_name` does a
`session.get` per row, which is an N+1 on a list of 100. This deserves its
own PR, not a bolt-on.

**The four document views resolve their lines as of 2026-09-12** (goods
receipt, purchase return, purchase invoice, delivery note): product as
`CODE — Name`, unit as its code, tax profile as its code, through one
`DocumentLineLabels` in `desktop/lib/ui/document_framework/`, fed by the
products, units and tax profiles each page reads on its own after its
list (a failure there costs a name, never the list; an unknown id shows
as itself, never blank). The owner hit it at 7.8: the goods receipt view
read as a column of UUIDs. The packaging type on a line is still its id,
and the headers of these views (vendor, branch, warehouse) are whatever
`toHeader` puts there -- check them at the next case that opens one.

### 31.4 Import dialogs give no sample file, and their messages cannot be copied (2026-09-11, plan item 5.8) -- fixed the same day

**Seen.** Driving 5.8, the first file was refused with "A valid E.164 phone
number is required." -- the format the importer wants is described in one
sentence of small print and nowhere shown, so the file was built wrong, and
the refusal could not be selected or copied to ask about it.

**Done.** Every file-based importer -- branches, warehouses, territories,
purchase orders and the three inventory imports -- has a **Sample file**
button beside Choose file that saves a CSV with the headings it reads and
one filled-in example row. The sample is built from the importer's own
column list (`ImportSample` in `desktop/lib/ui/workspace/import_sample.dart`)
so it cannot list a heading the parser does not read, and
`test_import_samples_match_the_server.py` on the backend holds the two
server-parsed samples to the `row.get()` names in `TerritoryService.import_csv`
and `PurchaseService.import_orders_csv`. `import_samples_test.dart` feeds
each sample back into its own dialog and asserts it is accepted. Every
message and refusal in those dialogs is a `CopyableMessage`: selectable,
with a copy button.

**Found while building it, fixed the same day.** Feeding the warehouse
dialog its own sample answered "Row 2: branch_id is required" with the
column plainly filled in. `InventoryImportFileParser` normalises every
heading to lower-case letters and digits (`display_name` becomes
`displayname`), and the branch dialog looked each column up by the heading
as written -- so every multi-word column it documents, `display_name`,
`address_line1`, `address_line2`, `currency_code`, `capacity_unit` and the
warehouse's **required** `branch_id`, had been silently dropped from every
file since the dialog was written. A branch imported with a full address
arrived with none, and a warehouse could not be imported at all. The
dialog reads through the same normalised key now, and
`branch_warehouse_import_test.dart` pins a two-word heading. Nothing in
the existing tests had ever used one.

**A warehouse names its branch by code (same evening).** The owner
imported the warehouse sample and got "The request validation failed."
-- the sample could only write `<id of an existing branch>`, since the
importer demanded the branch's id and nothing on a screen shows one.
`WarehouseCreate` takes `branch_id` **or** `branch_code` now (one is
required; an update takes either and keeps the branch when neither is
sent), the service resolves the code within the firm and refuses an
unknown one by name, the export writes `branch_code` in place of
`branch_id` so a file round-trips, and the sample's example row carries
the firm's first real branch code, read when the dialog opens, so it
imports as it is. And a validation refusal now names the row and the
field (`importRefusalMessage`): the server's detail was
`records.0.branch_id` / "Input should be a valid UUID" and the dialog had
shown only the envelope's sentence. The purchase-order importer still
keys on ids; that one is a server-parsed CSV and is left as it is.

### 31.5 Export said success and saved nothing (2026-09-11, plan item 5.9) -- fixed the same day

**Seen.** Branches → Export answered "Export completed." and no file
appeared anywhere. The server log showed `GET /api/v1/branches/export`
answered 200 twice.

**Why.** Four Export actions fetched the CSV through `downloadText` and
did nothing with it: branches and warehouses showed "Export completed.",
territories "Export generated (N bytes)", vendors "Export ready (N rows)".
Each reported a fact about bytes it was about to drop. Nothing in the
tests could see it, because no test tapped Export on any of the four --
the toolbar action existed, the permission gated it, and the handler's
only observable effect was a notification whose text was true of nothing.

**Done.** `saveExportedText` in `desktop/lib/ui/workspace/export_file.dart`
is the one path: it asks where to save, writes the file and returns the
path, and every one of the four reports `Export saved to <path>.` -- or
"Export cancelled. No file was saved." when the dialog is dismissed, since
a cancelled save reported as success is the same lie again. Each page takes
a `saveExportOverride` so `exports_save_a_file_test.dart` can drive the
toolbar and assert the CSV the server answered is the content handed to
the save, byte for byte. Customers and Products were checked and left
alone: they copy the CSV to the clipboard and say so, which is a different
design that works. Inventory and Purchase Orders already saved through a
dialog.

**And the file it saves is now the importer's own shape.** The owner's
next observation, a minute later: the export had six columns and the
import eleven, with the two they shared (`Code`, `Name`) spelled
differently from the importer's `code`, `name` -- so an exported file was
neither a backup nor a template. `BRANCH_EXPORT_COLUMNS` and
`WAREHOUSE_EXPORT_COLUMNS` in `app/branches/api/router.py` are the
importer's lists, `test_import_samples_match_the_server.py` holds them to
the Dart column lists, and `test_branch_export_round_trips.py` reads an
export back through the write schema. The territory export still writes
`Path` and not `CustomerCodes`, so a territory round trip loses the shops
on each round; left as it is, since building that column needs a customer
lookup per row and nobody has asked for it yet.

### 31.6 A refused save reported as saved (2026-09-12, plan item 6.5) -- fixed the same day

**Seen.** Editing the WHOLESALE business profile as `master.ops` and
ticking `IMEI` in Enabled features: the owner reported "it saved". The
server log said otherwise -- `PUT .../profiles/{id}` 200, then
`PUT .../profiles/{id}/features` 422 with "These features are not
implemented yet and cannot be enabled: IMEI." -- and the profile carries
no IMEI.

**Why.** `ResourceManagementPage` writes a record in two requests, the
record's own fields and then its assignments, and on an edit the first
had already gone through when the second was refused. The dialog stayed
open with the refusal in the validation summary at the top of the form,
while the features picker somebody had just used sits at the foot of a
long form, out of view -- so the refusal was easy to miss and the grid,
once the dialog was closed, showed a profile whose details had indeed
been written.

**Done.** On an edit the assignments are written **first**, so a refusal
leaves the record untouched and "not saved" is true; on a create the
record must exist before anything attaches to it, and the create
checkpoint stops a retry creating it twice. The form scrolls back to the
summary when it shows a refusal. `save_refusal_keeps_the_record_test.dart`
pins both: a refused edit makes no update call, a refused create is not
created twice.

**Still open.** The Enabled features picker shows nothing to mark the six
roadmap features as unimplemented, so the only way to learn is to be
refused on save. The catalogue carries `is_implemented`; the picker could
grey those out or label them.

### 31.7 The rule simulator could not match a rule (2026-09-12, plan item 6.7) -- fixed the same day

**Seen.** Reading the screen ahead of driving it: every simulation from
the desktop answered zero tax and "No rule matched -- using default
profile".

**Why, twice over.** The screen never sent `tax_profile_id`, which every
seeded rule is keyed on and without which the engine applies no profile
at all, so the answer was always zero. And its Transaction Type list read
SALE, PURCHASE, SALE_RETURN, PURCHASE_RETURN, TRANSFER, ADJUSTMENT --
names no rule has ever carried and no document module passes; the nine
modules pass SALES_INVOICE, PURCHASE_INVOICE and their siblings, and the
interstate rule names SALES_INTERSTATE. A third fault was waiting behind
those two: the result widgets read every amount with `as num?`, and the
server serialises Decimals as strings, so the first real answer would
have thrown a type error. It never had a real answer to throw on.

**Done.** A required **Tax Profile** dropdown, read from the firm's
profiles; the type list is the engine's own names; amounts are read
through `simulatorNumber`, which takes a number or a string.
`tax_rule_simulator_test.dart` holds the type list to the engine's names
and drives a run end to end against a fake answering the server's shape.

**Worth a decision.** Nothing in the application passes
`SALES_INTERSTATE` to the engine -- `grep -rn SALES_INTERSTATE app` finds
only the template and its tests. `SalesInvoiceService` passes
`SALES_INVOICE` for every sale, so the seeded `INTERSTATE_GST_*` rules,
each conditioned on `transaction_type EQUALS SALES_INTERSTATE`, cannot
fire on a real invoice however the profile condition is spelled; the
2026-09-08 fix to `_normalize_compare` made the second condition
matchable and left the first unmet. What the seeded interstate invoices
actually carry was **not** verified here -- the customer list carries no
state and the check needs a query per invoice -- so the open question is
whether any real sale is taxed IGST through the rule engine at all, or
only re-split after the fact by `gst_returns` and `einvoice`, which
derive the border from the two states. Either the invoice must pass
`SALES_INTERSTATE` when the buyer's state differs from the firm's, or the
rule must be conditioned on something the invoice does send. Not changed
here: it moves the tax on every interstate sale.

### 31.8 No conversion rule could be created from the desktop (2026-09-12, plan item 6.8) -- fixed the same day

**Seen.** Reading the screen ahead of driving it: the Create Conversion
Rule dialog asked for "From UOM ID" and "To UOM ID" -- values nobody can
type -- and sent a `version` key. `UomSchema` forbids unknown fields, so
the server answered 422 "The request validation failed." to every rule
created from the desktop; driven by hand to confirm. The grid showed the
same raw ids, and its Version column showed the optimistic-concurrency
counter rather than the rule's own revision, `version_number`.

**Done.** `ConversionRuleDialog` names the product (or *Firm-wide*) and
both units by code from dropdowns, refuses the same unit on both sides
and a factor at or below zero before sending, and sends exactly the keys
`ConversionRuleCreate` takes. The product is decided at creation and not
sent on an edit, so a rule cannot be moved between firm-wide and a
product from a field nobody touched. The grid shows codes, the product,
and the revision. `conversion_rule_dialog_test.dart` pins the payload key
by key. Precedence itself was verified against the server: with a
firm-wide PACK→KG factor of 2 in place, DETER1K still converts 10 PACK to
10 KG by its own rule, and a product with no rule of its own gets 20.

**And the purchase-order line editor, the same afternoon.** Its line
had text boxes labelled "Purchase UOM ID" and "Inventory UOM ID" -- the
owner asked for dropdowns as soon as 6.8 sent them there. Both are unit
dropdowns by code now, defaulted from the product the moment it is
chosen, with a blank left blank rather than the first unit chosen
silently, and a unit the line names that is not in the list kept
selectable as itself. `purchase_ux_test.dart` drives it. Two more from
the same screen, minutes later: the order **view** printed the unit's id
in its lines table (it shows the code now), and the table -- thirteen
columns, scrolling sideways with no bar -- read as not displaying at all
on a mouse-driven desktop. `DocumentLinesScroller` keeps the bar visible,
for every document view that uses `EnterpriseDocumentLines`. The other
document views (delivery note, goods receipt, purchase invoice, purchase
return) still hand the table a unit **id** -- the same fix per screen,
under §31.3.

### 31.9 A purchase invoice cannot be raised from the desktop (2026-09-12, plan item 7.8)

**Seen.** Writing the steps for 7.8 ("raise a purchase invoice against a
receipt"): the Purchase Invoices screen offers View, Approve, Cancel and
Close, and nothing else. It lists, approves and closes invoices that
already exist -- the seeder raises them -- and never calls
`POST /api/v1/purchase-invoices`.

**Why the guard did not say so.** `test_routes_have_a_caller.py` asks
whether a served path is named anywhere in `api_client.dart`, and the
screen reaches its routes through the generic `documentPage` /
`documentAction` helpers with the literal `'purchase-invoices'`, so the
create route reads as called. It is the hole `reachable_features_test.dart`
was written for on the sales side; nothing pins the purchase side.

**What is needed.** A **New** on Purchase Invoices that picks a completed
goods receipt (the twin of the Purchase Returns dialog, which picks the
same thing), seeds the lines from it, takes the supplier's invoice number
and date, and posts through the existing create route. Until then the
plan's 7.8 uses a seeded invoice, and 7.11 pays a seeded bill.

### 31.10 Every edit of a saved purchase order was refused (2026-09-12, plan item 7.4) -- fixed the same day

**Seen.** "I added line item remarks but its not saving, no error,
nothing." The server log showed `PUT /api/v1/purchases/{id}` answering
422 -- seven times that morning.

**Why.** `PurchaseOrder.toUpdateJson` was `toCreateJson` minus `status`,
and `toCreateJson` carries `po_number` whenever the order has one, which
a saved order always does. `PurchaseOrderCreate` takes `po_number` (so an
old system's numbering can be carried in); `PurchaseOrderUpdate` does
not, and `PurchaseSchema` forbids unknown fields. So the desktop could
create an order and never edit one -- and the editor showed only "The
request validation failed.", in a banner at the top of a long dialog,
which read as nothing happening. Neither suite could see it: the desktop
fake accepts what it is given and the backend tests build their own
requests -- the preferences gap of 2026-09-08 again, on another payload.

**Done.** `toUpdateJson` drops `po_number`. The editor shows the refusal
with the fields it names (`refusalMessage`, shared, in
`desktop/lib/ui/workspace/api_refusal.dart`). And
`test_desktop_purchase_payloads_are_accepted.py` reads the desktop's
create, update and line keys out of the Dart source and holds each to the
matching server schema, so the next key that create takes and update does
not fails the build instead of every edit.

### 31.11 Every purchase return raised from the desktop was refused (2026-09-12, plan item 7.9) -- fixed the same day

**Seen.** "Error while submitting return." The server log: `POST
/api/v1/purchase-returns` answered 422, twice.

**Why.** The return editor sent a `description` on every line, seeded
from the receipt line so never empty, and `PurchaseReturnLineWrite` has
no such field -- the server derives the description from the source line
it is told about -- while `PurchaseReturnSchema` forbids unknown fields.
So no return could be raised from the desktop, which is the second
payload of the day the two suites could not see (§31.10 was the first).

**Done.** The line no longer sends it; the return and receipt editors
show a refusal with the fields it names; and
`test_desktop_document_payloads_are_accepted.py` reads both editors'
payload keys out of the Dart source and holds them to
`PurchaseReturnCreate`/`PurchaseReturnLineWrite` and
`GoodsReceiptCreate`/`GoodsReceiptLineWrite`. Three document editors are
now guarded this way (purchase order, goods receipt, purchase return);
the sales side -- quotation, sales order, delivery note, sales invoice,
sales return, credit note -- is not, and the same afternoon's evidence
says it should be.

### 31.12 A second branch's first return was numbered like the first branch's (2026-09-12, plan item 7.9) -- fixed the same day

**Seen.** "The request conflicts with existing data." on saving the
return, once the payload defect (§31.11) was out of the way. The server
log: `UQ_purchase_returns_firm_return_number` refused
`PR-2026-2027-000001`, a number the seeded returns already held.

**Why.** `DocumentFrameworkService._scope_signature` keyed the counter on
the branch and the company **always**, while `_build_document_number`
prints them only when the rule says to. The purchase-return rule prints
neither, so the first return raised under `BR_NORTH` opened a fresh
counter at one and issued the number `WHL_HO` had issued months before.
The model's own docstring said the scope is "whatever the rule includes
in the number"; the code had drifted from it. The seeded stores never
showed it because the seeder raises everything under one branch.

**Done.** The signature carries the branch and the company only when the
number prints them -- by flag, or by a `{branch_code}` /
`{company_code}` placeholder in an explicit format pattern.
`test_a_counter_is_keyed_on_what_the_number_prints` pins both shapes: a
firm-wide series continues across branches, a per-branch series restarts
per branch. The orphaned counter row the failed attempt created is
harmless; nothing reads a signature that is no longer produced.

**And then the fix orphaned every existing series (same day, the retest
of 7.9).** The sentence above was true of the *failed attempt's* row and
exactly wrong about every other one: the seeded returns' counter sat
under the old key `2026-2027|WHL_HO|WHOLE01` at 3, the retest looked
under the new key `2026-2027||`, found nothing, started at one and was
refused as a duplicate of `PR-2026-2027-000001` -- the same 409 as
before, for the opposite reason. Every document type whose number prints
neither branch nor company had the same shape waiting in every seeded
firm: sales invoices, sales orders, quotations, purchase invoices,
credit notes, proformas and sales returns. Orders and receipts were
spared only because their numbers print the branch, which is why the
fresh run of 7.1--7.8 passed. **A change to what a counter is keyed on
has to move the rows that are already keyed.** Done twice over:
`20260912_0133` re-keys every live counter in every store the way
`_scope_signature` keys it today, merging any that collapse onto one key
at the highest `next_sequence`; and `_sequence_for` / `preview_number`
adopt a counter kept under an old key on first use, so a store the
migration has not reached still continues its series.
`test_a_series_survives_its_counter_key_changing_shape` pins it.


### 31.13 The Stock Ledger's type filter names movements the server never writes (2026-09-12, mapping section 8)

**Seen while writing the section 8 steps**, not yet on screen by the tester.
The **Transaction type** dropdown on the Stock Ledger and Transactions tabs
(`inventory_management_page.dart`) offers `GOODS_ISSUE`, `PHYSICAL_COUNT`,
`RESERVATION`, `RESERVATION_RELEASE`, `DAMAGE`, `EXPIRY`, `QUARANTINE`
and `CORRECTION`, none of which the server ever writes -- the ledger's
types are `OPENING_STOCK`, `GOODS_RECEIPT`, `ADJUSTMENT`, `RETURN`,
`SALES_RETURN`, `RESERVE`, `UNRESERVE`, `DISPATCH`, `TRANSFER_OUT`,
`TRANSFER_IN`, `WRITE_OFF`, `QUARANTINE_HOLD`, `QUARANTINE_RELEASE` and
their `_REVERSAL` twins (`app/inventory/schemas/inventory.py`). Choosing
one of the phantom values matches nothing, and the real ones a warehouse
asks for most -- a dispatch, a write-off, a quarantine hold -- are not
offered at all. A physical count posts as `ADJUSTMENT` referenced by the
count number, so there is no `PHYSICAL_COUNT` to filter on either. The
list should be read from the same enum the server writes, the way the
document pickers read their statuses, rather than typed a second time.

Two smaller ones from the same pass. The **Expiry Monitor** shows six
counts per window plus each batch's absolute expiry date; there is no
"days remaining" and the old test-plan row expected one -- a column on
the All Batches grid is the obvious shape, and the API already sorts by
`expiry_date`. And the **physical count sheet's Product column prints the
product id** (`physical_count_sheet_dialog.dart`), the same class as
§31.3.


### 31.14 What a saved sales document does not show (2026-09-13, mapping section 9)

**Status, 2026-10-03** (PLT-9): the credit and debit note pickers now name a line by product code and name rather than `Line 1`.

**Seen while writing the section 9 steps**, not yet on screen by the tester.

- *(Closed 2026-09-24, #626: the Discount cell reads "100.00 (10.00%)" and
  the quotation card "less 10.00%" where a rate applied.)*
  **No resolved discount percentage on any saved document.** The
  quotation's detail card prints `qty × price` and the totals; the order
  and invoice view dialogs' Discount column is the *amount*. The only way
  to read the rate the server resolved is to reopen the editor (Revise on
  a quotation, Edit on a draft order), where the box is refilled from the
  stored `discount_percent`. A tester checking 9.1--9.5 has no other
  route, and a salesman asking "what did this line get" has none at all
  once the order is approved.
- *(Closed 2026-09-24, #626: a Coupon header field, where one was presented.)*
  **The coupon is invisible after save**: no grid column, no header field
  in `EnterpriseDocumentHeader`; only the draft order's editor shows it.
- *(Closed 2026-09-24, #625: the row buttons read "Apply" and "Reverse".)*
  **Allocate and Reverse on a receipt are unlabelled icons** (tooltips
  "Apply to an invoice" and "Reverse") on the Receipts list row.
- *(Closed 2026-09-24, #625: a firm that has saved no Print settings gets
  the three copies CGST rule 48 names for goods -- recipient, transporter,
  supplier -- which is also the desktop's own default list; the owner may
  prefer the two-copy services set.)*
  **Invoice print copies are not defaulted**: `copy_labels` is empty until
  the firm saves Print settings, so a first print carries one unlabelled
  copy. The delivery challan defaults three labels; the invoice should
  default two (ORIGINAL FOR RECIPIENT, DUPLICATE FOR SUPPLIER).
- **The sales return and credit note Line pickers read `Line 1`** when
  the source line has no description -- no product code, so two lines of
  one document cannot be told apart by product.
- *(Closed: both dialogs resolve them through `DocumentLineLabels`; noted
  2026-09-24.)* **Sales order and sales invoice view dialogs print product and tax
  profile ids** (already §31.3; the delivery note resolves them).
- *(Decided 2026-09-24, #636: a typed rate is the deal and stands; an
  inherited one is resolved afresh, so the coupon reaches it -- which is
  what the conversion has done since D-SELL-9.)*
  **A coupon cannot reach an order that began as a quotation.** The
  conversion forwards each quoted rate as a typed rate -- the deal carries
  over as the deal -- and a typed rate outranks every promotion, so a code
  presented at order time changes nothing on a converted line (found at
  9.7, 2026-09-13). Defensible either way; a decision for the owner. If
  coupons should apply, the conversion could forward only rates that were
  typed on the quotation (`discount_source` now says which) and let the
  order re-resolve the rest.


### 31.15 Left open from mapping sections 10-13 (2026-09-13)

**Status, 2026-10-03** (PLT-9): the price list grid counts distinct products, territory-scoped lists are created on screen, and the payload guard reads the phase 2 editors and the sales side.

Found by mapping the screens and driving the flows for the plan rewrite;
each is a decision or a small feature rather than a broken behaviour.

- *(Closed 2026-09-24, #629: a "Posted by" dropdown beside the search box,
  over the modules that post plus "All", sends `source_module`, which the
  list route now takes as an exact match.)*
  **Journal Entries has no source-module filter.** The plan wanted one;
  the page's only filter is the reference/description search, and the
  module is visible only as "Posted by <module>" in each row's subtitle.
  The API takes `accounting_period_id` and `status` and nothing about the
  source. A dropdown over the thirteen posting modules is the obvious
  shape; it needs a query parameter first.
- *(Closed 2026-09-24, #630: the fallback says the search service could not
  be reached and only stock is shown.)*
  **Ctrl+K masks a failing search route.** If `GET /api/v1/search`
  throws, the shell silently falls back to an inventory-only search, so a
  503 there reads as "inventory results". A visible notice would be
  honest.
- *(Closed 2026-09-13: GST Returns' period is chosen with a calendar on
  each box and Previous/Next month arrows; it was two free-text dates.)*
- **The e-way bill action is offered only on registered rows**, so "an
  e-way bill against an unregistered invoice is refused" can only be shown
  over HTTP. Fine as a design; the plan says so.
- *(Closed 2026-09-24, #630: a customer picker narrows the ledger and states
  the balance, its worth and whether it is below the floor.)*
  **The Loyalty page cannot answer "this customer's balance"**: no
  customer filter and no balance column, though the API has both
  (`loyaltyEntries(customerId:)`, `GET /loyalty/{customer_id}`). The
  balances report is the route today.
- **The price-list grid's Products column counts rate rows, not
  products**, and territory-scoped lists cannot be created from the desktop
  (the third segment prints a sentence). *(The pane now says where each
  break starts, and double-click edits -- 2026-09-13.)*
- *(Closed 2026-09-24, #630 and #637: conditions read as sentences, and a
  condition on a product, category, customer, territory or route is picked
  by name in the dialog and shown by name on the page.)*
  **Promotions: the details pane prints conditions raw**
  (`line_quantity GREATER_OR_EQUAL 25`), and a condition on a product,
  customer, territory or route is typed as a bare id. *(The missing save
  toast -- "saved as a new revision; the one you opened is now inactive"
  -- and double-click to edit landed 2026-09-13.)*
- *(Closed 2026-09-24, #629: the target dialog has a Salesperson picker
  over the firm's members, "Whole firm" as the empty choice, and sends
  `salesman_id` on create and edit -- null for the firm.)*
  **Targets cannot be set for a person from the desktop** -- the dialog
  sends no `salesman_id`, so every desktop-made target is "Whole firm".
- *(Closed 2026-09-13: a call list's "Not today" now says "Runs on
  Fridays; this is a Monday.", and the seeder looks for `<FIRM>-BP-R1-MON`
  so the Monday plan gets its explicit stops -- visible after a reseed.)*
- *(Closed 2026-09-24, #629: both are in the report catalogue; the
  workspace asks a period of a report that needs one, and lists them only
  to holders of COMMISSION_VIEW / SALES_TARGET_VIEW, which is what their
  routes check.)*
  **The commission collections report and the targets achievement report
  are not in the report catalogue**; they exist only as their own
  screens, and the catalogue guard polices `/reports/` paths only.


## 32. Seed a standard India geography master into every firm store -- done 2026-09-17

Raised while verifying the customer place picker (plan item 4.3, 2026-09-09).

**The observation.** Geography -- `geo_countries` -> `geo_states` ->
`geo_districts` -> `geo_cities` -> `geo_postal_codes` -> `geo_localities` --
is a per-firm master owned by the territory module (`app/sales`), and it
ships with **nothing preloaded**. Each firm starts empty and the data is
entered by hand or by a seed script, so the place picker on customers,
vendors, branches and warehouses is only as complete as whatever that firm
has added. In the seeded demo, WHOLE01 holds India plus one state and one
city (and two "UITest" leftovers), and ELEC01 holds only India with nothing
beneath it. A new or dedicated firm has to build its own country and state
list before the picker is useful, and every firm rebuilds it independently.

**The ask.** Seed the standard India state master -- the 28 states and 8
union territories, with their GST state codes -- into every firm store, so
the State rung of the picker is populated out of the box. Country India is
already created by the finance/tax setup where it is missing, so this builds
on that.

**Shape of the work.**

- A blueprint of the 28 states + 8 UTs with GST state codes (the same list
  `app/gst_returns` and the tax framework already reason about), created
  through `SalesTerritoryService` so the ids and audit rows are consistent
  with hand-entered ones.
- Run it per firm store, the way `migrate_all_stores.py` and the retention
  purge enumerate targets from the registry -- platform-owned geography does
  not exist; each firm store gets its own copy.
- Idempotent on "this state already exists in this store", so it can be run
  against firms that have already entered some places, and re-run safely.
- Districts, cities, postal codes and localities stay user-entered -- the
  full India dataset is large and volatile, and the state list is the rung
  that is both small, stable, and needed for GST place-of-supply.
- Decide whether it runs as a one-off script (like the other seeders), a
  step in firm provisioning / open-books, or both. Provisioning is the
  natural home, so a new firm gets it without a manual step.

Not a bug -- the picker works, it is just empty. Deferred by the owner on
2026-09-09 to do later.

**Done on 2026-09-17**, as migration `20260917_0137`, delivered the way every
store already receives reference data: a data migration, so `migrate-all`
reaches existing stores and `upgrade_store` reaches each newly provisioned one
without a second mechanism to remember.

Two things in the ask above turned out to be wrong, and are recorded here
rather than quietly dropped:

* **GST state codes were not seeded, because there is nowhere to put them and
  nothing that would read them.** `geo_states` carries only `country_id`,
  `code`, `name` and `is_active`. Every place-of-supply decision in this
  codebase reads the numeric code off the **GSTIN** -- `einvoice`'s
  `_state_code` takes the first two digits, `gst_returns` does the same -- for
  the stated reason that reading it off the number rather than off an address
  means the two can never disagree. Geography is not in that path. Adding a
  `gst_state_code` column would have been a new column and a second source for
  a fact already derived. `code` holds the two-letter abbreviation this
  repository was already using.
* **`SalesTerritoryService` was not used**, despite the ask. A migration that
  reads today's models replays a different change next year, and `_commit()`
  would commit inside Alembic's transaction. Module-level `sa.table` stubs, as
  every other seeding migration here uses.

It **skips rather than merges**: a state whose code *or* name a store already
holds is left alone, soft-deleted ones included. Both unique indexes are scoped
to `is_deleted = false`, so re-inserting a deleted state would succeed and
quietly undo a deliberate deletion. Verified against all seven live stores --
the three with no states went to 36, the ones with their own kept them (38 and
37), a replay stayed at 36, and a deliberately deleted Mizoram stayed deleted.

Districts, cities, postal codes and localities stay user-entered, as above.
A screen for filling those in is the open half, and the owner asked for it on
2026-09-17: somewhere a tenant can add a district, city, town or pin code
without it being a chore.
## 33. Customer group management belongs beside the other master lists

Raised by the owner on 2026-09-09 while reviewing the customers screen.

**The observation.** Managing the *set* of customer groups -- creating,
editing, deleting Retailer / Wholesaler / Institution -- is done from a
**Groups** button on the customers grid toolbar (`CustomerGroupDialog`). That
is master-data setup, not something done while working the customer list, and
it is the odd one out: **Vendor Categories** and **Vendor Types**, the same
shape of thing (a small master another record points at), are their own tabs
under Masters. A firm setting up its segments looks for them beside the vendor
masters or under Configuration, not behind a toolbar button on the customers
grid.

Distinct from **assigning** a customer to a group, which is the dropdown on
the customer form (§30) and is correctly placed -- this is only about where
the groups themselves are created and edited.

**The ask.** Make **Customer Groups** a tab under Masters, the way Vendor
Categories is, reusing the existing management screen, and drop the toolbar
button. It sits naturally beside the vendor masters, or under the
Configuration section; deciding which is part of the work. The assign
dropdown on the customer form stays.

**Shape of the work.**

- A `customer-groups` tab on the `masters` module with `CUSTOMER_VIEW` to
  read and `CUSTOMER_MANAGE_SETTINGS` (or `CUSTOMER_UPDATE`) to write, wired
  to a management page built from the current `CustomerGroupDialog` body.
- A navigation node for it in `_mastersNavigation`, which
  `module_catalog_navigation_test.dart` (§29) now requires anyway.
- Remove the **Groups** button from the customers toolbar.
- The client methods already exist (`customerGroups`, `createCustomerGroup`,
  `updateCustomerGroup`, `deleteCustomerGroup`), so this is placement, not new
  API.

Not a bug -- the feature works where it is. A consistency and discoverability
improvement, deferred by the owner to do later.

## Also open

- **Cancelling a goods receipt valued the two books differently — fixed
  2026-08-22.** Found by cancelling one on freshly seeded data and asking the verifier.
  `_reverse_receipt_journal` mirrors the original entry (the receipt price)
  while `_reverse_inventory` removes stock at today's moving average. Measured
  on ELEC01: 8,040.00 mirrored against 5,752.60 of stock removed, leaving the
  inventory control account 2,287.42 above the warehouse from one request.

  **The decision is which book leads, and where the difference lands.**

  1. *The ledger follows the movement*, which is what `sales_return` and
     `purchase_return` already do — post the reversal at the stock value the
     movement actually removed. Then 2,287.42 is a valuation difference that
     needs a named account: an inventory adjustment or cost-of-goods line. This
     is the smaller change and the consistent one.
  2. *The movement follows the ledger* — take the goods out at the cost they
     came in at and unwind the moving average. A truer reversal, and a change
     to the valuation engine rather than to one method, with its own question
     about what happens when the stock has since been sold.

  **Option 1 was taken**, and the account it needed already existed:
  `PURCHASE_PRICE_VARIANCE`, which `post_purchase_return` uses when goods leave
  at an average that disagrees with the document. A cancelled receipt now
  debits goods received not invoiced in full, credits inventory with what the
  movement removed, and books the gap to the variance account. Driven on
  ELEC01: the sequence that put it 2,287.42 out now leaves all five checks
  passing.

  The pre-2026-08-18 defect in the same method is what put both shared stores
  out before the re-seed. This was its sibling, and it is closed.

- **A soft-deleted profile assignment no longer reserves its firm**
  (`20260815_0089`). `firm_business_profiles` carried a table-wide
  `UNIQUE (firm_id)`, so a removed assignment would have locked that firm out
  of ever having another: every query in `app/business` filters `is_deleted`,
  making the row invisible to all of them while it still held the key, and the
  re-assignment would fail on the constraint with nothing on screen to explain
  it.

  **Nothing sets `is_deleted` on that table today** -- all four references only
  filter on it -- so this was a trap rather than a defect, closed before the
  first "unassign" action opens it rather than after. The index is partial now,
  matching `UQ_firms_code_active` and `UQ_users_email_active`; PostgreSQL only,
  so on MySQL the service check stays authoritative, and it updates the firm's
  row in place rather than inserting a second.

  Proven on the deployed schema in a rolled-back transaction, before and after:
  with a soft-deleted row present a new live assignment was refused, and is now
  accepted, while **two live assignments are still refused**.


- **A platform screen administering firm-owned data must open that firm's
  store**, decided 2026-08-15 after the business-profile assignment endpoints
  were found doing the opposite.

  They took their session from `get_db`, which routes on the caller's
  `X-Firm-ID`. So an administrator on a platform screen read and wrote
  assignments in **whichever firm they happened to have selected**, not the
  firm named in the URL. Reading answered `none` for any firm in a different
  store; writing **returned success** while the firm kept its old profile and
  a row claiming otherwise landed in the caller's store. Proven on the seeded
  demo: assigning a profile to ELEC01 with WHOLE01 selected left ELEC01
  untouched and put the row in `wholesale_hub`. MEDI01 and FOOD01 appeared to
  work only because they share `firm_shared`.

  `firm_store_session(request, firm_id)` in
  `app/core/database/dependencies.py` is the fix, built on a new
  `FirmRegistryTenantResolver.resolve_firm` split out of the header parsing.
  Use it for **any** platform endpoint touching firm-owned data.

  `GET /business-framework/firm-profile-assignments` returns every firm with
  its profile by iterating the stores, the way `migrate_all_stores.py` does. A
  firm whose store cannot be read carries `unavailable_reason` rather than
  being blanked or dropped: an unprovisioned firm and an unassigned one are
  different facts, and a grid that renders them identically invites the
  administrator to fix the wrong one.


- **`PUT /customers/{id}` works again**, as of 2026-08-15. It answered 409
  "This record changed since you loaded it" for **any customer whose opening
  balance had posted**, with nobody else touching the record -- so on a seeded
  firm, every customer edit failed.

  `_reverse_opening_balance_postings` sets `journal_entry_id = None` on the
  opening-balance rows, and `_reset_opening_balance_transaction` then removed
  those same rows with a bulk `delete(synchronize_session=False)`. The dirty
  objects stayed in the session, so their `UPDATE` fired against rows that were
  already gone and SQLAlchemy raised `StaleDataError`, which the handler maps
  to 409. They are deleted through the ORM now, so the unit of work knows.

  **The unit suite could not have caught it**, and that is the reusable part.
  Every fixture here builds a session with SQLAlchemy's default autoflush,
  while `app/core/database/engine.py` passes `autoflush=False` -- and autoflush
  writes the pending UPDATE while the row still exists, repairing the ordering
  by accident. `_request_like_session_factory` in
  `tests/unit/test_customer_management.py` builds a session shaped like a
  request's; reach for it whenever a service mixes ORM mutation with bulk
  statements. It is the same difference that hid the adjustment that returned
  201 and wrote no journal.

  Found by driving the endpoint over HTTP after the ETag work made it possible
  to send a precondition, and reproduced against `main` on a second server to
  be sure it was not introduced by that change.

- **An edit no longer discards what a customer owes**, as of 2026-08-15, and
  this is the larger of the two. `CustomerService.update` recomputed
  `current_outstanding` and `unapplied_advance_balance` from `opening_balance`
  on **every** call, so changing a phone number threw away every invoice,
  receipt and credit note the customer had accumulated since -- and the
  receivable control account was then out by the difference, silently and
  permanently.

  The balance work now runs only when the opening balance actually moved, which
  the existing guard already restricts to customers with no receivable
  activity. There, recomputing from the opening figure is the whole truth about
  the balances; everywhere else it is a lie.

  **Found by `scripts/verify_sample_data.py` catching damage this session
  caused.** Three probe edits to one WHOLE01 customer -- notes only, opening
  balance untouched -- moved them from 84,901.23 outstanding to 25,000.00 and
  put the store 59,901.23 out. The verifier named it as "a balance moved
  without a journal", which is exactly what had happened. It is the second time
  that script has paid for itself within minutes.

- **A record now tells you which version to send back**, as of 2026-08-15.
  `If-Match` had been accepted by five routers since it was written, and **no
  response carried the version anywhere** -- not as a header, not as a body
  field. The only value a client could honestly send was `*`, which means "no
  precondition", so the whole optimistic-concurrency contract was documented
  and unusable. `set_etag` in `app/core/concurrency.py` publishes the version as
  a quoted `ETag`, which is exactly what `parse_if_match` reads back, so a
  client echoes the header it was given without having to know what is inside
  it.

  It is on the twelve endpoints that answer with one versioned record -- the
  `GET` and `PUT` pair for firms, purchase orders, sales orders, delivery
  notes, goods receipts and customers.

  **`PUT /customers/{id}` gained the precondition itself**, which it never had.
  It is the endpoint the gap was first noticed on and the one where losing it
  costs most: the update replaces the whole address and contact collection, so
  the loser of a concurrent edit does not merge badly -- they lose every row
  they entered.

  **The desktop uses it for customers** as of 2026-08-15. Two people editing
  one customer is the case that costs most — the update replaces the whole
  address and contact collection, so the loser does not merge badly, they lose
  every row they entered.

  **The version rides in the response body as well as the ETag header**, which
  looks like duplication and is not. A header carries one value and a list
  carries many records, and this client opens its editor from a list row rather
  than re-reading the record — so an ETag alone could never have reached the
  screen that needed it. `CustomerResponse` and the five other versioned
  responses now carry `version`; the header remains correct for single reads.

  A record whose `version` is absent reads as zero and saves with **no**
  precondition, so an older backend stays usable rather than having every save
  refused.

  **Extended to five more screens on 2026-08-15**: vendors, products, branches,
  warehouses and quotations. Vendors is the one that mattered most — its update
  replaces **six** child collections (contacts, addresses, banking, tax
  registrations, attachments, notes), the worst case of that shape in the
  codebase.

  **The refusal message depends on where the editor saves from**, and getting
  that wrong tells the user a lie about their own work. Customers and products
  save from *inside* the dialog, so a refusal leaves the form holding every
  keystroke and the message says so. Vendors, branches, warehouses and
  quotations return their payload and close first, so by the time the refusal
  arrives the typing is gone — those say the changes were **not saved**.
  `concurrencyMessage(noun, changesKept:)` in
  `desktop/lib/core/api/concurrency.dart` is that distinction, in one place.

  **`QuotationResponse` already carried `version`** and had since the module was
  written, so that screen needed no schema change at all — only the client had
  to start reading it.

  **Still last-one-wins:** UOM, tax, batch/serial, territories, inventory,
  opening stock, physical counts, document types and business profiles.
  **UOM and tax are deliberate**, not an oversight: `uom` already uses `version`
  in its schemas for a conversion rule's own business version, so the
  concurrency counter cannot take that name there without a rename, and `tax`
  carries `version_number` on versioned rules for the same reason. Those two
  need a field-naming decision before they can join, which is why they are not
  in this change.

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

  **Swept on 2026-08-14.** The delivery note's vehicle field is gated too --
  it was the only remaining *write* field of the three. The other hits are
  read-only displays (batch grid columns, detail lines, a product attribute
  label), and gating those would hide history rather than prevent a refusal:
  the server refuses writes, not reads.

  **The product form deliberately keeps its own path.** It reads the same
  feature set out of `ProductMetadataRecord`, which it already fetches for
  categories and attributes in one call. Both come from `resolve_capabilities`
  firm-wide -- the category affects which attributes apply, not which features
  are on -- so the two cannot disagree, and moving the product form onto
  `BusinessFeatures` would add an HTTP call to reach the same answer. The
  relationship is written down in `business_features.dart` so neither side gets
  "fixed" into the other.
- **A dialog that can be saved shows a way to save it**, as of 2026-08-14.
  `WorkspaceDialog.onSave` was wired to a keyboard shortcut and nothing else,
  so a dialog passing it without building its own footer offered no visible
  button. Two had shipped that way -- recording a receipt and moving stock --
  and both were reachable only by a shortcut nobody had been told about. The
  dialog now renders a default Cancel/Save footer when it is given `onSave` and
  no footer of its own, with `saveLabel` naming the action, so the gap cannot
  recur silently.

- **A credit note reaches the ledger** as of 2026-08-14, and so does cancelling
  an invoice. The verifier found the first within minutes of existing, and
  chasing it found the second, which is much larger.

  `POST /customers/{id}/receivables/transactions` refuses RECEIPT and
  ADVANCE_RECEIPT, and the reasoning for leaving CREDIT_NOTE was that it "moves
  no money" -- the wrong test. What matters is whether the **receivable balance**
  moves, and a credit note reduces it: WHOLE01 drifted by exactly the 10.00
  credit note posted while verifying that change. A standalone credit note now
  posts `Dr Sales Returns / Cr Accounts Receivable`.

  **Cancelling an approved sales invoice was worse.** It posted a credit note to
  the customer's balance and left the invoice's journal untouched, so revenue,
  tax and the receivable all stayed in the ledger while the customer stopped
  owing them -- the control account overstated by the whole invoice, every time.
  It reverses the invoice's own entry now, which mirrors what the invoice
  raised; booking it as a sales return instead would have put the revenue in the
  wrong place.

  `ADVANCE_APPLY` is genuinely fine by contrast: the advance was credited to
  receivables when the receipt posted, so applying it to an invoice moves
  nothing the ledger has not already recorded.

- **`scripts/verify_sample_data.py` works again** (2026-08-14), rewritten
  rather than repaired. The old one counted rows in one schema for one firm and
  predated multi-tenancy. It now enumerates every firm store from the registry
  the way `migrate_all_stores.py` does, and checks the five things that were
  actually found broken this week: stock value against the inventory control
  account, every period balancing, customer outstanding against the receivable
  control account, every settlement carrying its journal, and every approved
  invoice having posted.

- **`tests/` is clean under ruff and black** as of 2026-08-14, and `mypy app`
  passes across all 320 files. The 24 missing docstrings were the useful part:
  a test that does not say what it protects is a test nobody dares delete and
  nobody trusts. What remains repo-wide is 181 findings in `scripts/` (130) and
  `alembic/` (51), mostly long lines and missing docstrings in older
  migrations.

## 34. Stock movements should be numbered by the system, not typed

**Status, 2026-10-02: built** (found while compiling `docs/BACKLOG_BUILD_PLAN.md`) as D-QA-16 -- transfers, write-offs, quarantine and adjustments draw `ST`, `WO`, `QR` and `ADJ` numbers from their own series (`backend/app/inventory/services/movement_numbering.py`); a typed reference is still taken as it is.

Proposed 2026-09-12 during section 8 of the manual pass; **a decision for the
owner, not yet scheduled.**

**Today.** A transfer, write-off or quarantine hold/release asks the storeman
for a **Reference** (free text, two characters or more, uppercased) and that
text becomes the movement's identity in the stock ledger -- on both legs of a
transfer, and on the write-off's journal entry. Nothing checks it is unique,
so two people can both type `TRF-0001`; and because journal references *are*
unique, a repeated reference on a write-off would refuse the second one with
an error about the journal rather than the stock. Physical counts already do
this the right way: `PhysicalCountService` draws `PC-...` from the document
framework's numbering rules.

**Proposal.**

- Three numbering series per firm, seeded the way the `PC` series is:
  `STOCK_TRANSFER` (`TRF-{FY}-000001`), `STOCK_WRITE_OFF` (`WO-...`),
  `STOCK_QUARANTINE` (`QH-...`; hold and release share one series, since the
  ledger type already says which). Administered on Settings -> Numbering
  series like every other series.
- The server issues the number through `reserve_number` inside the same
  transaction as the movement and stamps it on both transfer legs and on the
  write-off's journal. `reference_number` stays **optional** on the three
  request schemas for imports and older clients: absent means "issue one",
  a typed one is still accepted.
- The dialog drops the Reference box and says "Reference: issued on save"
  (the framework's `preview_number` can show it up front). **Remarks** is
  where the gate pass, the damage report or who authorised it goes --
  mirroring goods receipts, which keep the system number and the supplier's
  invoice reference apart.
- The toast names the number ("Stock transferred as TRF-2026-2027-000004")
  so it can be found in the ledger straight away.

**To decide alongside it.** Whether a movement should carry an optional
*external reference* column for the counterpart's document number rather
than burying it in remarks -- worth adding only when someone needs to filter
by it. And retries: a typed reference was the only natural duplicate check
on a double-click, so the dialog's save must stay disabled while the request
is in flight, as the document editors already do.

**Cost.** A migration seeding three document types and rules into every
store, a few lines in the three service methods, the dialog, and tests.

---

### 31.16 A refused password does not say which rule it broke (2026-09-15, plan section 22)

Setting an initial password of 11 characters is refused with **"Password does
not meet the configured policy."** and nothing else. The server already sends
the answer: `validate_password_policy` (`app/core/validation/common.py`)
raises with `details` holding the specific violations -- `["must contain at
least 12 characters"]` -- one per rule broken. The form drops them and shows
the summary line alone.

Met while making a test user during section 22. The cost is a guessing game
at exactly the moment somebody is being careful: the minimum is 12, and
nothing on screen says 12, or uppercase, or a symbol, or which of them was
missing.

**What to do.** `ApiException` already carries structured detail elsewhere --
`refusalMessage` in the user dialog lists plain-string details, added in #392
-- so this is a matter of using it where a password is set rather than new
machinery. Three places set one: Users → New, the administrator's password
reset, and My profile → Change password. The third already states the policy
beside the box (`ChangePasswordPolicy.check` mirrors the server's rules), so
the shape to copy is there.

**Worth deciding at the same time.** Whether the New-user form should state
the policy up front, as Change password does, rather than only on refusal.
Stating it costs a helper line under a field somebody fills in once; not
stating it costs a round trip every time somebody types a short password.

---

### 31.17 The audit trail cannot be searched, only matched exactly (2026-09-15, plan section 23; first raised at 13.8)

**Status, 2026-10-03: built** (PLT-8, A77). Partial matching on action and record type came first (#622); one search box now spans action, record type and the name or email of who did it or was acted on.

**Action** and **Entity type** on Settings → Audit Logs are exact-match:
`AuditLog.action == filters.action` in `AuditLogReader._apply`. Typing `user`
finds nothing; only `user_template.applied`, in full, does. The boxes are
therefore usable by somebody who already knows the vocabulary and by nobody
else, which is the opposite of who needs them.

Raised at 13.8 during section 13 as "owner may want real filters", left open,
and met again at 23.4c -- the owner asked for "search text on screen like
browser". That phrasing is worth keeping, because it names the expectation:
somebody looking at a screen full of rows expects to narrow it by typing part
of what they can see.

**What to build.**

- **Partial and case-insensitive matching** on both existing boxes (`ilike`),
  so `user` matches `user.created`, `user.roles_set` and
  `user_template.applied`.
- **One free-text box** spanning action, entity type and the actor's name and
  email. `actor_name` / `actor_email` arrived in #407, so the join that makes
  a name searchable is already there.

**Why not a literal Ctrl+F.** Flutter paints text rather than structuring it,
so a browser-style find over the rendered screen would mean building a text
index per screen. Searching the data is the honest equivalent and is what
every other grid here already does -- the audit screen is the odd one out,
having been given exact filters instead of the whitelisted `search` parameter
the list endpoints share.

**Worth checking at the same time.** Whether any other screen was given
exact-match filters where the rest of the application offers `search`. The
audit screen was found by using it; there is no guard that would report a
second one.

**Cost.** Three lines in `_apply`, a field on `AuditLogFilters`, a query
parameter, one box on the screen, and tests for each -- including one that a
partial term matches, which is the thing that is wrong today.

---

## 35. Daily and manual backups -- built 2026-10-01

**Status, 2026-10-01: built.** The nightly backup is §45 (#812). The manual
trigger and the restore drill are here:

- `app/core/tenancy/backup.py` takes a backup of every store into
  `<AGENCY_BACKUP_DIRECTORY>/manual/<stamp>/`: the stores are
  `migration_targets(..., include_deleted=True)`, so deleted firms are
  included and the list cannot drift from `migrate-all`'s; a store never
  built is skipped, not failed; each store is one `pg_dump -Fc -n "<schema>"`
  read back with `pg_restore --list`, and a `manifest.json` records the
  tables, size and revision of each. A folder missing a store gets no
  `.complete` and is never offered as a backup. One run at a time; the
  newest `AGENCY_BACKUP_KEEP_MANUAL` (10) are kept.
- `POST /api/v1/backups` (*Back up now*, 202, runs in the background, 409
  while one runs, audited as `system.backup_started` in the platform trail)
  and `GET /api/v1/backups` (every backup on disk -- manual, daily and
  pre-upgrade -- plus the current run), both on `SYSTEM_BACKUP`, a platform
  path. `agency-server backup` runs the same function. The phase 2 desktop
  has a **Backups** screen.
- Setup gives the server `AGENCY_BACKUP_DIRECTORY` and `AGENCY_BACKUP_PG_BIN`
  through the service definition, write on `backups\manual` and read on the
  rest.
- **Restore drill:** `tests/integration/test_backup_restore_drill.py` takes a
  backup through that code, restores it into a database created for the
  purpose and compares every table's row count; CI installs the PostgreSQL 17
  client tools for it and fails, rather than skips, without them.
- Found on the way (D-BACKUP-1): `pg_dump -n SNTEST01` folds the pattern to
  lower case, matched nothing and wrote an empty file, so the nightly and
  pre-upgrade backups failed for any upper-case firm schema. Both quote it now.

**Decided:** restore stays the procedure in `docs/INSTALL_GUIDE.md` section 6
rather than a button -- it means stopping the server that would run it, and
every comparable product keeps it an administrator's act on the server.
`SYSTEM_RESTORE` still guards nothing. A backup is not opt-in: it deletes
nothing. Encryption at rest and an off-box copy remain the administrator's
(the guide says to copy the folder off the PC). Per-firm restore is still the
constraint below.

Raised 2026-09-16 while walking the platform end to end.

**The observation.** Nothing backs anything up. There is no backup script,
endpoint, screen, test or scheduler anywhere in the repo. Four permission codes
-- `SYSTEM_BACKUP`, `SYSTEM_RESTORE` (`app/identity/system_seed.py`) and
`RESTORE_BACKUP`, `DATABASE_MAINTENANCE` -- are seeded and enforced by a CHECK
constraint in `20260801_0010`, and **nothing reads them**: the same shape as the
unused licensing codes. `app/platform/backup/` is an empty untracked directory
left behind by the 2026-08-09 deletion, not a package.

**The ask.** A daily automated backup and a manual trigger, covering the whole
installation and restorable as a whole. Per-firm restore is a later item; see
the constraint below.

**Shape of the work.**

- One script, `backend/scripts/backup_all_stores.py`, enumerating targets from
  the registry the way `scripts/migrate_all_stores.py` and
  `scripts/purge_retention.py` already do, so it cannot miss a store when one is
  added. Take the **profile-keyed** dedup `(connection_profile, database_name,
  schema_name)` from the purge -- two firms on different hosts may share a
  database and schema name -- and the **subprocess-with-env** execution and the
  report-every-store, exit-non-zero-if-any-failed policy from the migrator.
- Resolve every credential through `app/core/tenancy/connections.py`
  (`resolve_connection_profile` + `build_tenant_database_config`). A backup job
  is that module's **third consumer, not a fourth implementation**. `pg_dump`
  needs host, port, database, user and schema as separate values, and the
  password via `PGPASSWORD` in the subprocess env, never on the command line.
- **The platform schema is a mandatory target.** `firms`, `user_firms`,
  `platform_admins` and `firm_storage_mappings` live only there; a firm store
  restored without its mapping row is unreachable data.
- **Back up soft-deleted firms too.** Both existing scripts filter
  `Firm.is_deleted == False`, which is right for migrating and pruning and wrong
  here -- `docs/TENANCY_AND_STORES.md` says their data is still there. A
  dedicated firm with `provisioned_at` NULL has no tables and must be a skip,
  not a failure.
- Rotation, retention and a stated location for the artefacts. Sizing is
  favourable: `docs/HARDWARE_SIZING.md` measures 294 MB of tables for four firms
  over two years, 85% of it prunable logs, against a 128-256 GB SSD. Add a
  backup-storage line to that doc; it sizes live data only today.
- **A restore drill.** A backup nobody has restored is not a backup. The CI
  `integration` job already stands up `postgres:17` and migrates two schemas, so
  a dump-and-restore round trip has a natural home there.
- **Two schedulers are needed, not one.** The `retention` compose service in
  `backend/docker-compose.yml` is the template -- opt-in, `while true; do ...;
  sleep; done`, needing `AGENCY_TENANCY_CONNECTION_PROFILES` or a firm on
  another server fails. But that loop exists **only inside compose**, and the
  native Windows installer (`install/install.ps1`) registers no scheduled task
  at all. The actual product deployment has no mechanism to run any recurring
  job; that gap has to be closed for a daily backup to mean anything.

**Decisions still open.**

- Script only, or a platform-admin endpoint and a button? An endpoint needs a
  job runner, progress and a guard against ten concurrent dumps. The four seeded
  permission codes are the natural gate -- check which group is the platform set
  before wiring one.
- **Opt-in or opt-out?** Retention is opt-in *because it deletes*. A backup does
  not delete, so the same default is arguably wrong -- but inverting it
  contradicts the only precedent, so decide it deliberately.
- Which database principal dumps? `SECURITY_ARCHITECTURE.md` already separates
  runtime from migration credentials; a dump needs read on everything.
- **The artefact is a credential store.** A platform dump contains
  `users.password_hash`, `refresh_tokens` and `platform_admins`. Encryption at
  rest, file permissions and an off-box location are part of the item.

**The constraint that shapes per-firm restore later.** A `SHARED`-mode firm's
rows are interleaved with every other shared firm's in `firm_shared`, separated
only by a `firm_id` predicate, so restoring that schema restores all of them to
one point in time. `SCHEMA` and `DATABASE` firms restore independently. Any
per-firm promise must be qualified by deployment mode or implemented as a
row-filtered logical restore. A restore that rebuilds a store by running
migrations must also re-apply `prune_platform_objects`, or it recreates the
defect pruning exists to prevent.

Not a bug -- a missing capability the platform has always implied, four
permission codes' worth, and never had.

---

## 36. Onboarding a firm from its previous tool -- opening position built 2026-10-01

**Status, 2026-10-01: the opening position can be loaded from files.** The four gaps below are closed by the shared import framework (`app/common/file_import.py`: template, check with every problem by row and column, all-or-nothing apply, update by code) and these imports: products (#843), customers (#851), suppliers (#861), supplier opening bills (#841) and customer opening bills (#855) bill by bill, the opening trial balance on a cutover date (#842), and opening stock with batches (#862). **Column mapping on every one of these imports** (decision B3, 2026-10-02): a file from any software is previewed, its headings mapped onto the template (suggested by the names already accepted), and the mapping saved per firm and import for the next export -- `app/imports`, `import_mappings` (migration 0226). This replaces a reader per product, such as a Tally XML import. An item's opening stock is posted once, on the form and from the file alike (decided 2026-10-01); a second document for a warehouse is allowed for what was missed. The *Opening balances* step on the firm's Set up panel lists them in that order and ticks each as its store fills (2026-10-01, go-live plan tier 1 item 4). The opening bills come from a file too since D-GOLIVE-1 (2026-10-01). Left: Tally XML import.

Raised 2026-09-16. **Everything here is a provisional recommendation, not a
decision** -- how much data comes across, and who converts it, are still open.

**The observation.** Replacing a customer's existing tool (Tally, Busy, Marg, or
spreadsheets) means getting their masters and their current position into a new
firm. **Nineteen import endpoints already exist**, each taking a batch of the
same create payloads as its single-record route (`CustomerImportRequest` is
`records: list[CustomerCreate]`, 1-1000), staged and committed once in the nine
modules that were repaired. So the loading half is largely built. Four things
make today's imports unfit for a real cutover:

- **No import framework.** CSV/XLSX parsing is copy-pasted across five modules,
  each with its own `csv.DictReader`, its own hardcoded header names and its own
  "Install openpyxl" message. Unknown columns and short rows are dropped
  **silently**.
- **No per-row error report and no dry run.** A batch lands whole or returns one
  error naming neither the row nor the field. The only row index a caller sees
  is FastAPI's `body.records.236.phone`, which the desktop re-derives by regex.
- **No external identifier on any master**, so no import can be re-run: every
  `import_*` calls `create`, never an upsert. `TaxMigrationMapping`
  (`legacy_tax_code`, `source_system`) is the one genuine migration artefact and
  covers tax codes only.
- **Eleven of the nineteen endpoints have no client**, including customers,
  vendors and every sales and purchase document.

**The ask.** A repeatable way to stand up a firm from its old system's data,
good enough that onboarding is a day's work rather than a project.

**The recommended shape, to be reviewed.**

- **Migrate balances, not history.** Masters plus a starting position: stock on
  hand with costs, customer and vendor outstanding, opening trial balance. The
  old system stays readable for history. This is what the platform is built for
  -- `opening_balance` posts a journal, opening stock is a draft-then-post
  document. Re-creating years of past invoices would post journals for trading
  that happened in another set of books.
- **Generate the workbook template from the create schemas**, one sheet per
  entity, with a script -- the discipline `scripts/dump_route_permissions.py`
  and `scripts/dump_table_catalogue.py` already use. A hand-written template
  drifts from the schema the first time a field is added.
- **Reference by code, never by id.** Category, UOM, `tax_profile_group_code`,
  state, customer group, resolved by the importer, with an unknown code reported
  as a row error. This is where most of the work is, and what makes the file
  fillable by a human.
- **Follow the masters order** in `docs/FUNCTIONAL_GUIDE.md`'s runbook (units
  and tax before products, groups before customers) and refuse to run out of
  order rather than half-load.
- **Dry run, then commit once.** Validate every row, return a per-row error
  report, write nothing; then stage and commit once.
- **Keep the source system's identifier.** A `LEGACY_CODE` custom attribute
  needs no schema change and is indexed on `(firm_id, value_text)`, but
  `AttributeDefinition.code` is globally unique with no `firm_id`, nothing
  enforces uniqueness of the value, and only products expose an attribute filter
  today. A real `external_id` column may be the honest answer.
- **Masters and balances are separate passes**, so a failed balance load does
  not take the masters with it.
- **Copy the Inventory Import Wizard**
  (`desktop/lib/ui/inventory/inventory_import_wizard.dart`). It is already the
  right shape: file picker plus drag-and-drop, client-side parse, validation
  against loaded masters before sending, a per-row error table, a downloadable
  error CSV, retry, and a sample CSV guarded against drift by
  `tests/unit/test_import_samples_match_the_server.py`.
- **Duplicates on a re-run:** import under a suffixed code and reconcile by
  hand. Safe only **before the firm starts trading** -- once any document
  references a master record, two records for one party is expensive: the
  receivable ledger, every document and the credit exposure hang off the id, and
  soft-deleting the loser does not move its balance. There is no merge tool.

**Two cutover gaps that block a real migration.**

- **No vendor opening balance and no vendor payable ledger.** A customer's
  `opening_balance` posts `Dr Trade Receivables / Cr Opening Balance Equity` and
  writes a typed receivable transaction; `Vendor` has no equivalent column, no
  `VendorPayableTransaction`, and `post_opening_balance` is hardcoded to
  `customer_id` and `ACCOUNTS_RECEIVABLE`. A firm cannot load what it owes its
  suppliers on day one.
  **Built 2026-09-30 as supplier opening bills** (`vendor_opening_bills`,
  migration `20260930_0169`; the rules are in `docs/LEDGER_POSTING_RULES.md`,
  "A supplier's opening balance is bills, not a balance"). Decided by
  convention -- Tally's bill-wise opening balances: one row per unpaid bill
  with its own date and due date, posted Dr Opening Balance Equity / Cr
  Payables on a chosen cutover date, and paid through Record Payment like any
  bill. Not a lump sum per supplier (every payment would become an advance
  with nothing to clear) and not a purchase invoice (the GST returns would
  read it as trading). Entered on the vendor form's *Opening bills* section;
  `POST /vendors/opening-bills/import` takes a batch by supplier code, all or
  nothing; the file import (template, check, post) is
  `POST /vendors/opening-bills/import-file` (D-GOLIVE-1, 2026-10-01). Supplier credit from a return or a
  debit note is set against an opening bill like any bill -- **built
  2026-10-03** (BUY-17, A52, migration 0239).
- **Customers had only a single-figure opening balance.** Every receipt
  against it was money on account with nothing to clear, and the ageing could
  not say how old any of it was. **Built 2026-09-30 as customer opening bills**
  (`customer_opening_bills`, migration `20260930_0172`; rules in
  `docs/LEDGER_POSTING_RULES.md`, "A customer's opening balance is one figure
  or bills, never both"). The mirror of the supplier's: one row per unpaid
  bill, `OBC-00001`, posted Dr Receivables / Cr Opening Balance Equity on the
  cutover date, with an `OPENING_BILL` receivable transaction so the
  customer's balance, statement, credit control and delete guard see it;
  offered by Record Receipt ("Opening"), aged from its due date (given, or the
  bill date plus the customer's terms), listed by the outstanding and overdue
  reports; cancel mirrors the journal and the balance and is refused while a
  receipt is applied. **One figure or bill-wise, never both** (Tally's
  bill-wise breakup): a bill is refused while the master's opening balance is
  non-zero, and a non-zero opening balance while live bills stand. Entered on
  the phase 2 customer form's *Opening bills* section;
  `POST /customers/opening-bills/import` takes a batch by customer code, all
  or nothing; the file import is `POST /customers/opening-bills/import-file`
  (D-GOLIVE-1, 2026-10-01). Not a sales invoice, so GST returns, sales registers,
  e-invoicing and TCS turnover never see it, and neither does
  collection-based commission (it joins sales invoices).
- **No opening trial balance loader.** `LedgerBalance.opening_balance` is
  derived and carried forward, never written as an input, and `app/finance` has
  no import route. Cash, bank, fixed assets, loans, retained earnings and tax
  balances can only be entered as hand-typed journal entries, one at a time. The
  `OPENING_BALANCE_EQUITY` control account exists precisely as their
  counterpart, and nothing but stock and customer balances posts to it.
  **Built 2026-09-30 as the opening trial balance** (Accounts > Opening
  Balances, `GET`/`PUT /api/v1/finance/opening-trial-balance`; the rules are in
  `docs/LEDGER_POSTING_RULES.md`, "The opening trial balance is one journal,
  replaced whole"). One statement on a cutover date, by account code, the
  difference to opening balance equity, replaced whole by reversing the one
  standing; sub-ledger accounts refused. The same `PUT` is what §46's file
  import will send.
- **Stock on hand at cutover from one file: built 2026-10-01.**
  `GET /api/v1/inventory/opening-stock/import-template` (Opening stock, Notes
  and Lists sheets -- the firm's warehouses and up to 2,000 products, each
  marked where it needs a batch or an expiry; the example row names the
  firm's own product and warehouse, so the template imports as it comes) and
  `POST /api/v1/inventory/opening-stock/import-file` (`posting_date`,
  `apply`; `INVENTORY_IMPORT`, as the old import). Columns ProductCode,
  Warehouse (blank means the only one), Quantity, UnitCost, Batch, Expiry
  (dd-mm-yyyy, dd/mm/yyyy, yyyy-mm-dd or an Excel date), Unit, Remarks. Rows
  are grouped into one document per warehouse, `OS-IMPORT-<yyyymmdd>-<code>`,
  each **created and posted** through the form's own `stage_*` methods and
  committed once -- all warehouses or none. A check stages and posts too
  before rolling back, so a firm without its books is told on the check.
  Refused by row and column: an unknown product or warehouse, a quantity not
  above 0, a batch missing on a batch- or expiry-tracked product or present on
  a plain one, a missing or unreadable expiry, the same product, warehouse
  and batch twice (naming the first row), a unit with no conversion, a
  serial-numbered product (an opening-stock line carries no serials; entered
  on screen), and an item (product, warehouse, batch) that **already has
  posted opening stock**, naming that document. One rule with the form
  (decided 2026-10-01, as ERPs do it): the form's post refuses the same item
  too, while a second document for a warehouse -- the items forgotten the
  first time -- is allowed either way. A correction belongs in an adjustment. The importer is
  `app/inventory/services/opening_stock_import.py`; the desktop Opening
  Stock screen has **Import from file** (the shared wizard with a posting
  date). The old `POST /inventory/opening-stock/import` (one warehouse,
  product ids, stops at the first problem) is kept and has no desktop caller.
- Smaller: the customer opening balance posts dated **today**, not a chosen
  cutover date, and firm readiness has no "opening balances" or "masters loaded"
  step, so nothing tells a firm its cutover is incomplete.

**Open questions for the review.**

- Which tools are customers actually coming from, and in what formats? Build
  nothing per-tool until real export files have been seen.
- Does the customer's team prepare the data, or is it part of onboarding? That
  decides whether a fixed template suffices or a column-mapping screen earns its
  cost. Start with the template; a mapping screen and per-tool converters are
  later items.
- Is "look it up in the old system for a year" acceptable, or do they expect
  history in one place from day one? This is the question that would overturn
  "balances, not history".
- Are vendor payables and the opening trial balance part of this item or their
  own? Without them a migrated firm's books are wrong on day one.

Not a bug -- nineteen import endpoints exist and are staged correctly where they
were repaired; what is missing is the onboarding layer around them, two cutover
gaps, and clients for eleven of the endpoints. No customer has been migrated yet.

---

## 37. Scope the screens to a financial year -- low priority

Raised 2026-09-16.

**The observation.** Every document list and report reads across all history. A
firm three years in scrolls past two years of invoices to find this month's. The
pieces to fix it exist: `financial_years` carries `starts_on`/`ends_on` per firm,
list endpoints already take inclusive `created_from`/`created_to` filters, the
P&L already stops at the financial year, and the balance sheet already splits
this year from what came before.

**The ask.** A financial-year scope in the shell, beside the firm switcher:
default to the firm's current year, offer older years and an "all years" option,
and bound document lists and reports to the selection. It is a **filter**, not a
data split -- nothing is archived, unloaded or moved.

**Shape of the work.**

- A year selector in the shell header, sourced from the firm's own
  `financial_years` rows, defaulting to the year containing today.
- Scope **documents and reports**, passing the range as the existing date
  filters rather than inventing a parameter.
- **Make the selection visible.** A silent filter that hides data is the most
  reliable way to generate "the system lost my invoice" reports.

**Two things that must NOT be year-scoped, or the feature does harm.**

- **Open items.** An unpaid invoice from last year must still appear while
  working in this year, or the receivables list, the credit check and collection
  all silently omit it. The rule is "dated in this year **plus** anything still
  open".
- **Masters and positions.** Customers, vendors and products do not belong to a
  year. Neither does stock on hand -- it is a position built from movements going
  back years.

**What to keep true in the meantime** -- these keep the door open at no cost:

- Every new list endpoint takes a document-date range from the start, following
  the inclusive `created_from`/`created_to` convention.
- Transactional tables keep an index on `(firm_id, <document date>)`.
- `financial_years` stays the authority on year boundaries -- nothing hardcodes
  April, which is already the rule behind `financial_year_label`.
- No report is written that can only aggregate all history when a year-bounded
  form would serve; the balance sheet's retained-earnings derivation is the
  legitimate exception.

**Performance note, so it is not oversold.** Bounding queries on an indexed range
is a real gain for lists and reports. It is not the lever for storage: business
data is ~11 MB per firm per year, while 85% of what is on disk is `audit_logs`
and `tax_rule_execution_logs`, which the already-built, opt-in retention service
prunes. Turn that on first. If volume ever genuinely bites, partitioning those
big append-only tables by date is the next lever and needs no accounting change.

**Explicitly out of scope.** This does not require year-end closing entries and
must not be confused with them. Two facts established while discussing it, worth
recording because they constrain any future year-end design:
`FinancialYear.is_locked` refuses modifying or deleting the year row and does
**not** block postings -- closing a period is what refuses a posting; and there
is **no year-end closing entry**, because the balance sheet computes
`retained_earnings_brought_forward` by subtracting this year's result from
cumulative earnings on every read. Prior-year data therefore cannot be unloaded:
removing it silently makes retained earnings wrong.

Not a bug -- the data is all reachable, the screens are simply unbounded.

---

## 38. The same stage switches for purchasing

Raised 2026-09-16. **Built 2026-09-30** -- backend (migrations `0163`, `0164`,
`PurchaseChainService`) and the phase 2 desktop (Purchases > Purchase Settings >
Buying stages; the bill editor names an order or products when receipts are
off). `docs/PURCHASE_FRAMEWORK.md`, "Stage switches", is the reference. The
decisions below were taken by industry standard and are recorded there:
approval of an order the bill raised is **not** a separate step (the person
typing the bill is the approver there is); receipts on with orders off is
refused; the bill's approval completes its own draft receipt first, so *Goods
Received Not Invoiced* nets to zero.

**The observation.** Selling already bends to a small firm and buying does not.
`SalesWorkflowSettings` (`app/sales_order/models/sales_order.py`) gives a firm
one row with three switches -- `quotation_stage`, `sales_order_stage`,
`delivery_note_stage` -- and `SalesChainService` raises whatever is switched off
by driving the same services a person would. Its docstring states the case
plainly: *"a firm run by one person has no use for the first three: they are four
screens for one counter sale."* The invoice has no switch, because it is what the
customer receives and what the user actually wants.

Buying has no equivalent. There is no `PurchaseWorkflowSettings` and no purchase
chain service -- `app/purchase/services/` holds only the service and a print
service. A one-person firm with the supplier's bill in hand must still type a
purchase order, receive it, and then record the invoice, and **approval cannot be
skipped**. The asymmetry looks like an oversight rather than a decision: the same
argument applies exactly.

**The ask.** Stage switches for the buying chain, so a firm can record the
purchase invoice and have the order and the goods receipt raised behind it.

**Shape of the work.**

- A `purchase_workflow_settings` row per firm, mirroring the sales table: a
  **column per stage, not a `mode`**, for the reason the sales docstring gives --
  a firm changes shape, and each step should be a switch rather than a migration.
  Every stage defaults **on**, so an existing firm is unchanged until somebody
  switches one off.
- A purchase chain service that raises the skipped documents **through the real
  services**, as `SalesChainService` does. The documents must be real: stock
  still arrives at the goods receipt, and the reversal rules still hold.
- A default branch and warehouse on the settings row, the same way the sales
  table carries one -- receiving refuses a line with no warehouse, and a firm on
  automatic never sees a field to type one into.

**The part that is not a copy of the sales side.** The buying chain moves stock
**inwards** at the goods receipt and posts the accrual to *Goods Received Not
Invoiced* (`2300`) between the receipt and the bill. Synthesising backwards from
the invoice means posting both sides in the right order so that accrual nets to
zero, rather than leaving a balance nobody will clear. `2300` is one of the two
accounts people already ask about; leaving it dangling on every automatic
purchase would be worse than the typing it saves.

**To decide alongside it.** Whether approval is a stage that can be switched off
at all. On the sales side the switches remove *documents*; on the buying side
approval is a *control*, and a firm of one approving its own orders is either
sensible (there is nobody else) or the point at which the control stops meaning
anything. Answer it deliberately rather than by copying the sales flags.

Not a bug -- selling bends to a one-person firm and buying does not, and only one
of the two was ever asked to.

---

## 39. Field collections: record offline, sync on return

Raised 2026-09-17.

**The observation.** A collections person walks a route, takes cash against
outstanding bills, and has no connectivity while doing it. The platform has the
route half -- territories, routes, beats, customers in `visit_sequence`, and a
call list that already says who is due today -- and none of the offline half.
Nothing in the codebase queues work, detects a replayed write, or reconciles a
device with the server; grepping for idempotency, offline or sync finds nothing.
The Android build (`desktop/build_android.ps1`) is the **desktop layout in an
APK**, built to look at screens on a phone, not a field application.

**The ask.** Let a collector record receipts on a phone with no network, and
sync them when back at the office, with the system remaining the authority on
what was actually applied.

**Design, 2026-09-30:** `docs/FIELD_COLLECTIONS.md` -- the online and offline
options (office Wi-Fi, file exchange with a small offline app, QR), the daily
route-pack / collect / sync cycle, and the integrity checks that stop a receipt
or a file going missing.

**Shape of the work.**

- **A route pack before he leaves.** One download: his route's customers in
  visit order, each with outstanding and open invoices. It is a snapshot and
  will be stale by afternoon; that is acceptable because of the re-resolve
  below.
- **A queue of intents, not a local ledger.** The device stores the same
  `SettlementCreate` payloads it would have posted -- party, date, amount,
  method, instrument reference, allocations. Nothing is computed or authoritative
  on the phone. This is deliberately **not** an offline replica of the books.
- **The device assigns the number, from a block issued to it.** This is the part
  that matters most. `UQ_settlements_firm_number` already makes
  `settlement_number` unique per firm, and the field is optional on the create
  payload, so a device-assigned number **is** the idempotency key: a replayed
  sync collides on the unique key instead of taking the money twice. Best of all
  is the physical receipt-book number handed to the customer, so the paper, the
  device and the system carry one identifier. `manual_allowed` on the numbering
  rule already exists for this case.
- **The server re-decides at sync.** Allocations are resolved against *current*
  outstanding, not the morning's snapshot -- the office may have banked a cheque
  against the same invoice while he was out. Each receipt is its **own**
  transaction, so one refused row does not roll back the good ones, and the
  response is a **per-receipt report** rather than one error for the batch.
- **Sync through `ReceiptService`.** Not a parallel write path. Bulk and import
  endpoints are already documented here as a second implementation that drifts;
  a field-sync endpoint would be a third, and it moves money.

**Three things that will bite.**

- **A closed period.** Collected on the 31st, synced on the 2nd, and the period
  has closed in between: the posting is refused. Decide the rule -- periods stay
  open until field sync is confirmed, or a late receipt posts into the open
  period while carrying its true collection date.
- **Cash in hand is invisible.** Between collection and sync the money is in
  somebody's pocket and in no system. A **cash-handover step** -- sync, total
  what was collected, confirm the cash received matches -- is what makes this
  auditable, and is arguably a larger feature than the sync itself.
- **It needs a real mobile surface.** Today's APK is a desktop layout. A
  collections app is small-screen and one-handed, used in a shop doorway:
  today's calls, tap a customer, enter an amount, capture a signature or photo.
  That is the cost of this item; the queue is the straightforward part.

Authentication is already survivable: the refresh token lasts 7 days and is held
in the OS credential vault, so signing in at the office covers a day's route.

**Decisions to make.**

- **Allocate on the device, or collect on account?** Letting the collector
  allocate to specific invoices is what a customer expects on the receipt, but
  it is the part that goes stale. Collecting **on account** -- an unallocated
  receipt the office applies afterwards -- removes the staleness problem
  entirely and is markedly simpler. The platform already splits a receipt into
  balance and advance, so an unallocated receipt is an ordinary thing here.
- Device-issued number blocks, or the physical receipt book? The book is better
  evidence; blocks are better if receipts are printed from the phone.
- What happens to a receipt the server refuses -- who is told, and how is the
  cash already taken accounted for?
- Signature or photo capture, and where those files live. `backend/storage/`
  holds nothing today and there is no file-storage module.

Not a bug -- the route machinery exists and the offline half was never built.

## 40. If the logic ever needs real protection, host it

Compiling the backend with Nuitka (2026-09-17, `docs/RELEASE_BUILD.md`) means a
customer receives machine code rather than a readable copy of how this works.
That was the right answer to the question actually asked -- *"someone should not
read the code easily while we install the app on a customer machine"* -- and it
clears that bar.

It is worth writing down what it does **not** do, so that nobody later reads the
compile step as more than it is:

- Nuitka raises the cost of casual reading and copying substantially. It does
  not prevent reverse engineering by somebody who has decided to.
- The database sits on the customer's machine. Schema and data are readable by
  any administrator there whatever happens to the Python, and the migrations
  ship as source because Alembic loads them by path.
- The `.env` on that machine holds the JWT signing key. A machine's owner can
  read it.

**The durable answer is architectural rather than a compiler.** This product
already has a client--server split; the backend merely *happens* to run on the
customer's machine. Moving it to a server the vendor controls protects the
logic completely, and no compiler comes close.

**Why it is not being done now.** The product is deliberately on-premises and
LAN-first: a distributor in a town with intermittent internet has to keep
invoicing. Hosting turns every outage into a stoppage, and that is a worse
product for the customer this was built for.

**What would change the calculation.** Any of:

- a customer base with reliable connectivity, where the trade-off reverses;
- a competitor shipping something recognisably derived from this;
- pricing that depends on usage the vendor has to be able to count;
- a feature that is genuinely the commercial secret rather than the sum of
  ordinary business rules.

**If it were done**, the shape is already mostly there: `api_client.dart` is the
only place endpoint paths live, the backend is already multi-tenant with a store
per firm, and `connection_profile` already allows a firm's data to live on
another server. What is missing is everything operational -- backups somebody
else is responsible for, an uptime commitment, per-tenant isolation that holds
up to being sold as a promise, and a support arrangement for the hours a firm
actually trades.

Not a bug, and not scheduled. Recorded so the decision is a decision.

## 41. Filling in districts, cities and pin codes without typing them

**Status, 2026-10-02:** built as decision B6 -- an India Post places pack inside
the installer, loaded by state from a screen, southern states ticked by
default; skip-not-merge. See `docs/GEOGRAPHY_MASTERS.md`. Owner, the same
day: the southern states are loaded into every firm store by migration
`20261002_0231` -- at install, upgrade and provisioning -- without the button.

Asked by the owner on 2026-09-17, straight after the state master landed
(§32): *"can user has option to refresh one time other territory information
based on net"*.

**Where this starts.** `20260917_0137` seeds India and the 36 states into every
store. The four rungs below -- districts, cities, postal codes, localities --
are still typed by hand, and they are the ones with real volume: roughly 780
districts, thousands of towns, and about 155,000 post offices in the Indian
Post dataset. A firm that wants its customer addresses keyed rather than free
text has to enter every place it trades in.

**The ask as put** was a one-time refresh from the internet. Three things argue
against that being the *only* path, and they are worth settling before anything
is built.

- **This product is deliberately offline.** On-premises, LAN-first, no
  guaranteed internet -- that is the reason hosting was rejected in §40. A
  feature reachable only over the internet is one a firm in a town with patchy
  connectivity cannot use, and geography is what they need on day one.
- **A third-party endpoint is a dependency nobody here controls.** A free
  places API today is a 404, a rate limit or a changed shape in two years, and
  the failure lands on a customer's machine while they are setting up.
- **Geography is per store.** Every dedicated-database firm gets its own copy,
  so pulling the whole country into every store to serve a firm trading in two
  states is a great many rows nobody reads.

**The shape worth considering instead -- a vendor data pack.**

- A **versioned places file**, curated and published by whoever ships this,
  carried *inside the installer*, so a customer with no internet is complete on
  the day they install.
- A screen offering **"Update places"**, which reads a newer pack -- from a
  file the firm was sent, or fetched from **a URL the vendor controls**, which
  cannot rot the way a public API does.
- **Scoped by state.** The firm ticks the states it trades in and expands only
  those. A Tamil Nadu distributor does not need Manipur's villages.
- The same **skip-rather-than-merge** rule the state seed uses: never overwrite
  a place a firm typed, never resurrect one it deleted.
- Built on the import machinery that already exists -- `import_territories` in
  `app/sales/api/router.py` and the CSV/Excel convention eight other modules
  already follow -- rather than a new network layer.

**Decisions to make.**

- **Does this application ever reach the internet from a customer's machine?**
  It never has. If the answer is yes, it must be opt-in, on a button, never
  automatic, and must send nothing out. That is a product decision rather than
  a technical one, and it should be made deliberately rather than arrived at.
- **Which rungs ship in the pack?** Districts and towns are small enough to
  bundle whole. The full post-office set is not, and most of it is villages no
  distributor will ever bill. Postal codes may be better as an opt-in tier.
- **Where does the data come from, and under what licence?** India Post and
  `data.gov.in` publish this; the terms need reading before anything is
  redistributed inside an installer.
- **Who owns keeping it current?** A pack shipped once and never updated is a
  pack that is wrong in three years. If there is no intention to republish it,
  say so, and let firms import their own file instead.
- **What happens to a firm that already typed 40 towns?** The skip rule keeps
  them, but they will then hold their own spelling beside the pack's. Worth
  deciding whether the screen offers to reconcile, or leaves it alone.

Not a bug -- the pickers work and the states are seeded; this is the volume
below them. Raised and deferred by the owner on 2026-09-17 for review later.

## 42. What the market offers that this product does not

**Status, 2026-10-02:** 42.9 built -- Reports > *Below reorder level* (available, on order, last-billed supplier, suggested quantity) and Purchase Orders > "..." > *Below reorder level...* raises one draft order per supplier and warehouse.

Asked by the owner on 2026-09-18, after the product-overview deck: compare the
system with the products on the market and list the useful features it is
missing. **Nothing here is decided or scoped.** It is a list to choose from,
each entry saying who has the feature, what exists here today, and why a
distributor would ask for it.

**How it was compiled.** Four products were read from their own websites and
public reviews on 2026-09-18: **TallyPrime**, **BUSY**, **Marg ERP 9+** and
**Zoho Books + Zoho Inventory**, plus the feature lists of Indian distributor
management (DMS) apps. Every "what exists here" line was checked by searching
`backend/app` for the tables and columns such a feature would need, not taken
from the docs. Competitors change between releases, so re-check a claim about
them before quoting it to a customer.

**Already covered, so not gaps:** credit limits, trade schemes and free goods,
beats and routes, earliest-expiry-first batches, multi-branch, e-way bills,
TCS, an audit trail, currency and exchange-rate fields, and a low-stock view.

### 42.1 Sending documents and reminders on WhatsApp, SMS or email

- **Who has it:** BUSY (invoices, statements, payment reminders, scheme
  offers), Marg, TallyPrime (payment advice), Zoho Books (reminders before and
  after the due date, escalating, by email or WhatsApp).
- **Here:** nothing. The invoice PDF already exists
  (`GET /api/v1/sales-invoices/{id}/print` and its purchase twin); no code
  sends anything.
- **Why it matters:** every competitor has it, and it is the first thing a
  customer notices is missing. **§14 (email) holds the four open questions**
  -- which address, whose outbox, what a bounce does, whether a failed send
  blocks the document -- and WhatsApp adds a fifth: which provider, since
  WhatsApp Business messages go through a paid API. Deferred by the owner
  (§14); this entry adds WhatsApp and reminders to the same decision.

### 42.2 Bank reconciliation, and bank feeds

- **Who has it:** TallyPrime (one-click auto reconciliation, and connected
  banking with four banks), BUSY (statement import, cleared and uncleared
  views, a reconciliation statement), Marg (auto reconciliation with 140+
  banks), Zoho Books (bank feeds from its Standard plan).
- **Here:** nothing -- no statement import, no cleared date on a settlement or
  a journal line, no reconciliation report.
- **Why it matters:** it is where a firm's accountant spends each week. A first
  version needs no bank connection: import a statement file, match lines to
  receipts and payments, record the cleared date. Connected banking can come
  later.

### 42.3 A post-dated cheque register

**Status, 2026-10-03: built** (ACC-2, A80): *Post-dated Cheques* under Sell > Money and Buy > Money. A cheque is held until it is banked, banking records the receipt or payment, and a returned cheque reverses it with the bank's fee and an optional charge to the customer.

- **Who has it:** BUSY (PDC management on receipts and payments).
- **Here:** a settlement carries `method` and a free-text
  `instrument_reference`; there is no cheque date, no "held until" state, no
  clearing or bounce.
- **Why it matters:** Indian distribution still runs on cheques dated ahead.
  A cheque received today for the 30th should not count as money until then,
  and a bounced one has to reverse and often carry a charge. Best designed with
  42.2, since clearing is what both are about.

### 42.4 TDS, and 194Q in particular

**Status, 2026-10-03: built** (ACC-8, A78): 194Q is worked out per supplier per Income-tax year once the firm switches it on; the payment suggests the deduction and a register shows each supplier's position. The CA confirms the rate and threshold at hand-over.

- **Who has it:** BUSY, TallyPrime, Zoho Books (calculation, Form 16A, return
  preparation).
- **Here:** TCS under 206C(1H) (`app/tcs`); **no TDS at all**.
- **Why it matters:** section 194Q obliges a buyer whose purchases from one
  seller pass Rs 50 lakh in a year to deduct TDS on the excess -- most
  distributors cross that with their principal. It is the mirror image of the
  TCS module, which already has the threshold, the per-financial-year running
  total and charging on the excess only, so much of the shape exists.

### 42.5 GSTR-2A / 2B matching

**Built 2026-10-02 as §78 row 3.**

- **Who has it:** TallyPrime (download and auto-reconcile), Zoho Books.
- **Here:** GSTR-1 and 3B are derived from the documents (`app/gst_returns`);
  3B carries the input credit from purchase bills (table 4, since D-CMP-20)
  but nothing checks it against what suppliers filed.
- **Why it matters:** input tax credit is claimable only on what the supplier
  actually filed. Matching purchase invoices against 2B shows the credit at
  risk before the return is filed. A first version can import the 2B JSON the
  portal gives out; no portal connection is needed.

### 42.6 A mobile app for salesmen

- **Who has it:** Marg (eOrder, eDelivery), most DMS apps (order booking at the
  outlet, GPS attendance, visit check-in, live stock and scheme checks).
- **Here:** beats, routes and call lists on the desktop. The Android build is a
  preview of desktop layouts, not a field app. No GPS, attendance or visit
  records (`grep` finds none).
- **Why it matters:** it is the feature distributors compare products on. It is
  also a separate product -- phone layouts, working offline, syncing later --
  so it deserves its own decision. **§39 (field collections offline)** already
  records the thinking on the offline half.

### 42.7 Scheme claims to the principal

- **Who has it:** Marg (claims and statements, with reminders), DMS apps
  (claims raised by the distributor, settled by the company).
- **Here:** promotions work end to end, but nothing records what the
  manufacturer owes back for a scheme the distributor passed on.
- **Why it matters:** for an **agency** this is part of how it earns. A claim
  is the promotion cost, summed per principal per period, raised as a document
  and settled -- the promotion and loyalty ledgers already hold the figures.

### 42.8 Backup and restore inside the product

- **Who has it:** TallyPrime, BUSY, Marg.
- **Here:** nothing. **§35 (daily and manual backups)** holds the design.
- Listed here only so this comparison is complete.

### 42.9 Reorder alerts and a suggested purchase order

- **Who has it:** Marg (reorder points, alerts).
- **Here:** `reorder_level` and `maximum_level` on inventory, and a
  `low_stock_only` filter on the stock list. No alert and no suggested order.
- **Why it matters:** a "raise a purchase order for everything below its
  reorder level, up to its maximum" action turns an existing column into a
  saved afternoon each week.

### 42.10 UPI QR codes and payment links on an invoice

- **Who has it:** TallyPrime (payment links, UPI QR), Zoho (payment links, and
  card or UPI terminals).
- **Here:** a `upi_id` field on vendors only.
- **Status, 2026-10-03:** the static UPI QR is **built** (MSG-2, A55): the firm's UPI ID on the invoice's Print settings, a QR for what the bill still owes on the A4 and 80 mm prints. Payment links stay open (§51 B4).
- **Why it matters:** a static UPI QR printed on the invoice needs no gateway
  and no internet -- only the firm's UPI ID and the amount. Payment links need a
  gateway and are a bigger decision.

### 42.11 Importing from Tally or BUSY

- **Who has it:** not a competitor feature -- it is what lowers the cost of
  leaving one.
- **Here:** spreadsheet imports for masters. **§36 (onboarding from the
  previous tool)** covers the design, including what today's imports lack.

### 42.12 Landed cost

- **Who has it:** Zoho Inventory (spread a freight, duty or clearing bill over
  the goods it relates to, by quantity, value, dimensions or weight).
- **Here:** no code names landed cost, and no way was found to add a separate
  transporter's or clearing agent's bill to the cost of goods already
  received.
- **Why it matters:** without it, freight paid to a third party lands in an
  expense account and the stock's cost -- and so the margin on it -- is
  understated.

### 42.13 Kits and composite items

- **Who has it:** Zoho Inventory (composite items, assembled or bundled).
- **Here:** nothing; the "bundle" hits in the code are role templates.
- **Why it matters:** gift packs and combo packs are common in FMCG. Promotions
  already give free goods, which covers some of it; a kit that is stocked and
  sold as one item is a different thing.

### 42.14 A customer and vendor portal

- **Who has it:** Zoho (customer and vendor portals, with approvals and
  permissions).
- **Here:** nothing.
- **Why it matters:** a retailer who can see their own statement and place an
  order without phoning is a lighter version of 42.6. It needs the server
  reachable from outside the office, which this product has deliberately never
  required (§40, §41), so it is a hosting decision before it is a feature.

### 42.15 Less likely to matter for a distributor

- **Bill of materials and job work** (BUSY) -- only for the MANUFACTURING
  profile.
- **Recurring invoices** (Zoho) -- suits rent and subscriptions more than
  trading.
- **Courier and marketplace integrations** (Zoho: Delhivery and others;
  Shopify, Amazon) -- for firms that ship parcels or sell online.

### A suggested order, if any of this is built

1. **42.1** sending on WhatsApp and email -- the most visible gap, and the PDFs
   exist.
2. **42.2 with 42.3** bank reconciliation and post-dated cheques -- one screen,
   the accountant's weekly work.
3. **42.4 with 42.5** TDS 194Q and GSTR-2B -- what an auditor asks about, and
   both build on engines already here.
4. **42.7** scheme claims -- how an agency earns.

42.6 is a separate product and wants its own decision.

**Sources (read 2026-09-18):** tallysolutions.com/features/banking;
spectracompunet.com (TallyPrime GSTR-2A/2B reconciliation, TallyPrime 7.0
connected payments); busy.in FAQs (bank reconciliation; sending invoices on
SMS and WhatsApp); softwaresuggest.com/busy-accounting;
techjockey.com/detail/margerp-9; cliqus.in/marg;
margcompusoft.com (distribution software, eOrder app);
zoho.com/us/inventory/kb/general-overview/zom-feature-list.html;
zoho.com/in/books; patronaccounting.com (Zoho Books India guide);
massistcrm.com (DMS); deltasalesapp.com (DMS features).

## 43. Telling people an update is out, and applying it within the licence -- later

Asked for by the owner on 2026-09-24, to be built **after** the installer and
licensing (see the "Windows installer, logs and licensing design" doc, rule
L-E3 and phase 2). Nothing here exists yet.

**What it is.** The server learns that a newer Sutra ERP version has been
released, tells the firm's administrators inside the app, and -- when the
licence still covers updates -- downloads and applies it by itself at a quiet
hour. When the licence does not cover it, the notice says so and offers
renewal instead; the installed version keeps working either way.

**Rules, to be agreed when it is picked up:**

1. **One release feed**, a small signed file listing each version, its build
   date, its download address, its size and its SHA-256 hash. The server
   reads it once a day when the PC has internet, and never waits on it.
2. **Covered or not is decided by the licence**: a version whose build date is
   on or before the licence's *updates until* date is covered (L-E3). A
   licence past its end date gets no automatic update at all.
3. **Covered updates apply automatically**, by default overnight outside
   business hours and never while anyone is signed in, using the installer's
   upgrade path: backup every store first, migrate, check health, and put the
   old version back if anything fails (the design doc's upgrade section).
4. **The administrator decides the mode**: automatic (default), notify only,
   or off; plus the hour it may run. Choosing "notify only" is the right
   setting for a firm that wants to install updates itself.
5. **Nothing unverified is installed**: the downloaded Setup.exe must match the
   feed's hash and carry the Sutra Softworks code signature, or it is deleted
   and the failure logged.
6. **Client PCs update from their own server**, not from the internet: the
   server keeps the matching desktop installer, and a desktop app older than
   its server offers the update at sign-in. A LAN with one internet-connected
   server is enough.
7. **Offline customers lose nothing**: with no internet nothing is checked, and
   an update is the same Setup.exe sent by hand.
8. **The notice** shows version, date, what changed in a few lines, whether the
   licence covers it, and when it will be applied; administrators only, once
   per version, dismissible.
9. **What leaves the PC** is only what licensing phase 2 already sends
   (licence id, machine code, version); no business data.
10. **Everything is logged** in the platform audit trail and the install log:
    checked, found, downloaded, verified, applied, rolled back, skipped because
    not covered.

**Depends on:** the installer's upgrade and rollback path, licensing (the
*updates until* date), code signing, and somewhere to host the release feed
and installers (the same place as the phase 2 licence service).

## 44. A user's own default branch and warehouse

**Status, 2026-10-02:** an administrator sets another member's default branch and warehouse (`GET/PUT /api/v1/branches/work-defaults/{user_id}`, Users grid > *Branch and warehouse*).

**Status, 2026-10-01: built.** Settings > Firm > **My Branch and Warehouse** (any firm member) sets where a person usually works; `GET/PUT /api/v1/branches/my-work-defaults`, kept in the firm's own store (`user_work_defaults`, migration `20261001_0177`), validated on save (live, the warehouse the branch's) and on use (one retired since is dropped with a notice). The desktop loads it on firm switch and sign-in, clears it on sign-out and before another firm's, and `preferredBranchId` / `preferredWarehouseId` take it ahead of the firm's default, so every document form that opens with a default follows. It only fills; it restricts nothing. Left: an administrator setting it on someone else's record.

Asked for by the owner on 2026-09-25, during the laptop QA round (W39-W43),
after a sales order was approved with no warehouse and its stock was reserved
in an empty one (D-QA-17).

**What exists.** One default per **firm**: `sales_workflow_settings`
`default_branch_id` / `default_warehouse_id`, plus an `is_default` flag on
branches and warehouses. Nothing per **user**.

**What is asked.** Each person can set the branch and warehouse they usually
work from -- a counter clerk at STORE2, a salesman at the head office -- and
every new document (quotation, sales order, delivery note, invoice, purchase
order, goods receipt, return, stock action) opens with them filled in.

**Rules, by the usual convention:**

1. **Order of precedence** when a form opens: the source document's own
   value (a delivery note continues its order's warehouse) -> the user's
   default -> the firm's default -> blank. A default only **fills** a field; the
   user can always change it, and nothing is ever chosen silently at save or
   approval (that is D-QA-17).
2. **Stored per user per firm** -- a person in two firms has a default in
   each -- on the server with the other user preferences, so it follows them
   to another PC. Set from the user's own preferences screen; an administrator
   may also set it on the user's record.
3. **Validated on save and on use**: it must be a live branch/warehouse of that
   firm, and the warehouse must belong to the branch. One that has since been
   retired is ignored with a notice, not used.
4. **Not a restriction.** It says where someone usually works, not where they
   may work. Limiting a user to certain branches or warehouses is a separate
   access-control feature and should not be smuggled in through this.

**Depends on:** D-QA-17's fix (an order must name a warehouse before
approval), which this makes painless rather than replaces.

## 45. A scheduled daily backup (D-QA-4) -- built 2026-09-27

**2026-09-27:** finished. A successful run against a live database (three
runs with `-KeepDaily 2`: each wrote an 83 MB dump and `.complete`, the third
removed the oldest), and a restore of that dump into a fresh database gave
back the same counts of firms, users, sales invoices and journal entries.
The restore procedure is in `docs/INSTALL_GUIDE.md` section 6. Still to see
on the next laptop install: the task registering (`Get-ScheduledTask 'Agency
Platform daily backup'`) and a manual `Start-ScheduledTask` run as SYSTEM.
The notes below are the history.

Nothing backs up the database on a schedule: `backups\` fills only when Setup
runs an upgrade, so a firm that never upgrades has no backup, and a disk
failure loses everything (D-QA-4, found in the laptop QA round 2026-09-25).

**Built, on branch `fix/d-qa-4-daily-backup` (pushed, not merged):**
`packaging/server_setup.ps1` shares the pre-upgrade backup's store list and
dump loop (`Get-BackupPlan`, `Write-StoreDumps`), adds `-Action DailyBackup`
(an online `pg_dump -Fc` of every store into `backups\daily\<stamp>\`, a
`.complete` marker, keeps the newest 7, Administrators and SYSTEM only, log in
`logs\backup\daily-<date>.log`), registers a SYSTEM scheduled task "Agency
Platform daily backup" at 02:00 with catch-up on every install, upgrade and
repair, and removes it on uninstall.

**Checked:** the script parses; the failure path (database unreachable) exits
1 with a clear message, keeps the earlier backups and clears the unfinished
folder on the next run; the folder ACL is admin-only.

**Still to do before merging:**
1. A successful run against a live database (the throwaway-cluster test was
   not finished), including retention with more than `-KeepDaily` runs.
2. The task registering on a real install: run Setup on the laptop, then
   `Get-ScheduledTask 'Agency Platform daily backup'` and a manual
   `Start-ScheduledTask`.
3. A restore procedure in `docs/INSTALL_GUIDE.md` (stop the server service,
   `pg_restore --clean --if-exists -d <database> <file>` per store, start it).
4. Move D-QA-4 to Fixed in `docs/DEFECTS.md`.

## 46. Import products, customers and vendors from a file, with templates -- built 2026-09-30

**Status, 2026-10-01:** products #843, customers #851, suppliers #861, opening stock #862 -- all merged, on `app/common/file_import.py`.

**Products: built 2026-09-30.** `GET /api/v1/products/import-template`
(XLSX with Products, Notes and Lists sheets -- the Lists sheet carries the
firm's own categories, units and tax groups -- or CSV) and
`POST /api/v1/products/import-file` (`apply=false` checks, `apply=true`
commits the whole file or nothing, `existing=update` updates by code with a
blank cell leaving its field alone; needs `PRODUCT_UPDATE` as well as
`PRODUCT_IMPORT`). Every problem comes back with its row and column in one
pass. The importer is `app/products/services/product_import.py`; each row
goes through `stage_product` / `stage_update_product`, so the guards and the
audit writes are the form's. The desktop Products **Import** opens a file
wizard: template download, choose file, check, save the problems as CSV,
import. The old CSV/XLSX branch of `POST /products/import` goes through the
same importer, so a row with a name and no code is now reported rather than
skipped.

**Customers: built 2026-09-30.** The file rules above moved to
`app/common/file_import.py` (`FileImporter`, `RowReader`, the template
builder), so a master states only its columns and how to stage one row.
`GET /api/v1/customers/import-template` (Customers, Notes and Lists sheets --
the firm's segments, the types and statuses) and
`POST /api/v1/customers/import-file`, same parameters; updating needs
`CUSTOMER_UPDATE` as well as `CUSTOMER_IMPORT`. The importer is
`app/customers/services/customer_import.py`. One row is one customer with
one address (default billing and shipping) and one primary contact; on an
update those two change in place and every other address and contact is
kept. The opening balance is booked exactly as the form books it, and
`1,200 Dr` / `500 Cr` are read as Tally writes them; a firm without its
books is told per row. A standing discount or a credit limit needs
`CUSTOMER_MANAGE_SETTINGS`, as on the form. A 10-digit phone is taken as
Indian (+91). A blank currency is the firm's own. The desktop Customers
**Import** opens the same wizard as Products.

**Suppliers: built 2026-09-30.** `GET /api/v1/vendors/import-template?format=xlsx|csv`
(`VENDOR_IMPORT`) and `POST /api/v1/vendors/import-file` (multipart `file`,
`existing` = `refuse|update`, `apply` = `true|false`, the same report as
customers); updating needs `VENDOR_UPDATE` as well. The importer is
`app/vendors/services/vendor_import.py`. One row is one supplier with one
address, one contact and one bank account, each updated in place on an
update. Addresses are placed in the geography masters by PIN, then city, then
state, and a place that matches none is reported rather than guessed. A bank
account needs `VENDOR_MANAGE_BANK_DETAILS`, as on the form. A GSTIN marks the
supplier registered. Opening balances stay bill-wise, through supplier opening
bills. The desktop Suppliers **Import** opens the same wizard.

**Opening stock: built 2026-10-01** (point 7 above: "opening stock stays with
its own import" -- it now has one in the same shape). The template and the
check-then-import file route are described under §36. The shared desktop
wizard gained two generic options for it: `offersUpdate: false` hides "update
existing" (opening stock is posted once), and `extraFields` shows fields the
import needs besides the file -- here the posting date -- whose change
discards the last check.


Owner's note, 2026-09-25: a firm moving from other software (Tally, Excel,
another ERP) needs to bring its masters in from a file, and a template to
fill in. **Important for onboarding; build when scheduled.**

**What exists today:**

| Master | Server import | Desktop | Template |
| --- | --- | --- | --- |
| Products | `POST /api/v1/products/import` -- JSON, CSV or XLSX | Import wizard takes **pasted JSON only**, no file picker | none |
| Customers | `POST /api/v1/customers/import` -- JSON only | toolbar **Import** does nothing (`customer_management_page.dart`, `ToolbarAction.import` falls through) | none |
| Vendors | `POST /api/v1/vendors/import` -- JSON only | no import | none |

The pattern to copy is the inventory import (`inventory_import_wizard.dart`,
`InventoryImportFileParser`, which already reads XLSX, and
`inventory_import_samples.dart`): file pick, preview, validation before
anything is written, cancel and retry.

**To build, the same shape for all three (one PR per master, products first):**
1. **Download template**: XLSX (CSV too) whose headings are exactly the
   fields the write schema accepts, one example row, and a notes sheet --
   required columns, allowed codes, date and number formats.
2. **Import**: pick a CSV/XLSX file; one shared desktop wizard for the three.
3. **Preview and check** every row before saving -- missing or duplicate
   code, unknown category / unit / tax profile / customer group, bad
   GSTIN, PAN or phone -- each with its row number, and the errors
   downloadable so the file can be fixed and re-run.
4. **All or nothing**: stage then commit once (CLAUDE.md, "bulk and import
   endpoints are a second implementation": same audit writes and guards as
   the single-row path).
5. **Update existing by code** as an option, so a migration can be re-run and
   corrected.
6. References (category, unit, tax profile, group, geography) matched by code
   or name and **reported, never guessed** when missing; headings matched
   ignoring case and spacing, so an export from other software needs little
   editing.
7. Opening balances for customers and vendors in the same file where the
   write schema already takes them; opening stock stays with its own import.

## 47. The window's title bar buttons barely show on hover (D-QA-1) -- done 2026-09-27 (option 1, #771)

Owner, 2026-09-26, on the laptop after the 1.0.1 upgrade: minimize, maximize
and close are now all present (the original D-QA-1 symptom, no minimize or
resize button, is gone). What remains: hovering **close** turns it red, but
**minimize** and **maximize** get only Windows 11's very light grey, which on
the white title bar is nearly invisible, so they feel absent. The title bar is
the standard Windows one (`windows/runner/win32_window.cpp`, `window_manager`
0.5); Windows draws these buttons, the same as in Notepad.

**Options (owner to choose when scheduled):**
1. **Phase 1, small:** colour the title bar (`DwmSetWindowAttribute` with
   `DWMWA_CAPTION_COLOR` and `DWMWA_TEXT_COLOR`, Windows 11), e.g. the phase 2
   menu bar's dark grey with white text, so Windows draws a visible hover on
   all three. One runner change, next Setup.
2. **Phase 2:** no separate Windows title bar -- our own minimize, maximize
   and close at the right end of the top menu bar (as VS Code, Teams and Edge
   do), with a clear hover, gaining about 30 px of height for the grid.

Also still open: the window and taskbar icon is the default Flutter logo
until the owner supplies the product `.ico`.

## 48. The phone layout of phase 2 -- parked

Owner, 2026-09-26: the phone layout is not needed now; keep it in mind and
build it later. It is designed in `docs/UI_PHASE_2_DESIGN.md` section 4.15:
one app, one set of screens and rules, a phone layout chosen by width below
600 px -- bottom bar (Home, Sell, Stock, Money, More), lists as cards showing
the fields their column priority ranks first, documents entered a section at
a time, the field-sales day first (orders, receipts, customer ledger, stock
enquiry, route calls).

**Keep in mind while building phase 2, so it stays cheap to add:**
1. Every list declares a **priority per column** (4.11); the phone card is
   the top two or three of them, so no screen is designed twice.
2. No screen assumes a minimum width: a phase 2 page must reflow down to one
   column rather than scroll sideways.
3. Actions sit in the page bar and its **...** menu, never only on hover or
   right-click, which a touch screen does not have.
4. Nothing new goes into phase 1's drawer; below 600 px the phase 2 app
   still falls back to it (`DesktopShell._menuLayout`) until this is built.

Related: the Android build (`desktop/build_android.ps1`) is for looking at
screens on a phone, not for field use. It still builds phase 1
(`lib/main.dart`); pointing it at `lib/main_phase2.dart` is a one-line change,
as `packaging/build_installer.ps1` does for Windows.

### 48.1 Every screen size, not only the phone -- to review 2026-10-04

Owner, 2026-09-27: the app should adapt to any screen resolution, phone
included; a future plan, reviewed next week.

**Why it is mostly framework work.** Phase 2 screens are built from a handful
of shared pieces -- the menu bar, `ManagementWorkspaceLayout` (page bar,
selection bar, grid), `WorkspaceToolbar`, the document page and the dialogs --
so making those adapt changes every screen at once.

| Size | Width | What changes | Effort |
| --- | --- | --- | --- |
| Large | above 1366 | Works today; use the room (more default columns, the side panel always open) | Small |
| Medium | about 600 to 1366 (small laptops, tablets) | Page bar folds to two lines or a menu, side panel becomes a pop-up, fewer default columns, menu areas open as a list | Moderate |
| Phone | below 600 | Section 48 above: bottom bar, lists as cards, selection bar as a bottom sheet, documents a section at a time, touch-sized targets | Major |

**Suggested order:**
1. One breakpoint rule (phone / tablet / desktop) decided in one place, which
   every shared piece asks rather than assuming a desktop.
2. Adapt the list layout and the menu bar first; they cover the most screens.
3. Widget tests at each size, so a screen that breaks narrow fails the build
   (today's widget tests run in an 800x600 window).
4. Phone by who uses it: the salesman's day first (call list, customer,
   order, receipt), then the owner's (Home, outstanding, approvals). Setup and
   accounting screens may stay desktop-only, as is normal for this class of
   product.
5. Reach the server safely from outside the office (HTTPS; the client already
   accepts it -- section 1), so phones work on mobile data.

**Decided by the owner, 2026-09-27:**
1. **Tablet: every screen.** Some firm owners run the business from a
   tablet, so the medium size must support all pages, not a subset.
2. **Phone: a chosen set of modules**, with **orders and collections working
   offline** and syncing when back in signal (section 39 holds the offline
   thinking for collections; orders join it).

**Proposed phone modules, to settle at the review:**

| Fit | Modules | Why |
| --- | --- | --- |
| **Yes, offline** | Sales orders, Receipts (collections) | The salesman's day at the outlet, often with poor signal |
| **Yes, online** | Call list and beat plan, Customers (details, outstanding, statement), Stock search, Home (key figures, to do), Approvals (orders, payouts) | Reading and one-tap decisions; small screens handle them well |
| **Maybe** | Delivery notes (confirm delivery at the door), Sales returns (record at the outlet), Quotations, Expiry monitor | Useful for van sales or pharma; decide by how firms work |
| **No, tablet or desktop** | Purchasing, Accounts, GST, Stock movements and counts, Masters setup, Admin, Settings, Reports | Wide grids, long forms, done at a desk |

**Still to decide at the review:**
1. **Android only, or iPhone too** -- the same code builds both; iPhone needs
   an Apple developer account and a Mac to build on.
2. **Tablet first or phone first** -- the tablet is cheaper and helps small
   laptops too; the phone is what salesmen ask for.
3. **Outside access** -- how the server is reached from outside the office
   (a fixed IP and certificate, or a hosted relay), which decides whether
   phones and tablets work beyond the office Wi-Fi at all.
4. **Offline conflicts** -- what happens when an order synced late meets
   stock that has since gone, or a price that has changed (reprice, warn, or
   hold for approval), and whether a collection synced late may clear an
   invoice somebody has since credited.

## 49. Home gadgets -- parked

**Status, 2026-10-02:** item 4 built -- *Receipts today* on Home, from the receipts list's date filter.

Owner, 2026-09-26: Home as built (#695-#705, the approved wireframe) is fine
for now; different gadgets come later. What exists: key figures, sales over
14 days, recent invoices, to do, favourites, Customise to hide any of them,
every part cut to the user's role (`desktop/lib/phase2/home_page.dart`).

**To build when scheduled:**
1. **Gadgets as a catalogue**: Home made of gadgets a user adds, removes and
   orders (not only hides), each declaring the permission it needs so a role
   is offered only what it may see -- the same rule the menu follows (4.12).
2. **Gadgets by role**: owner, accountant, storeman, counter clerk and field
   salesman each start from their own default set (design 4.9).
3. **Favourites by star**: the star on menu items (4.3) fills FAVOURITES with
   the user's own screens; today it shows the daily screens of 4.6.
4. **Receipts today**: the wireframe's fourth key figure. Needs a date filter
   on `GET /api/v1/receipts` (it has none), so the figure is exact rather than
   counted from one page.
5. **Recent across documents**: the wireframe's RECENT mixes invoices, orders
   and goods receipts; today it lists invoices.
6. Candidates owners have asked of similar products: collections due this
   week, top customers, stock value, cash and bank balances, GST due.

## 50. Profit and loss for a financial year or chosen months

**Status, 2026-10-02:** item 5 built -- the trial balance and the ledger statement take a run of months within one financial year (`to_period_id`), sharing the P&L range rule.

**Status, 2026-10-01: items 1-4 built.** `GET /api/v1/finance/profit-loss/range?from_period_id=&to_period_id=&compare=previous_year` sums any run of months inside one financial year (a span across two is refused), returns each month's amount per account beside the total and the month-by-month net profit, and with `compare=previous_year` the previous year's same months by period number. The screen's *Show* picker adds **Months or year**: presets (This financial year, Year to date, This quarter, Last financial year, Custom), *Month by month* columns and *Compare with last year*. Checked on WHOLE01: every year's total equals the one-month report's year to date. Left: item 5, the same range on the trial balance and the ledger statement.

Owner, 2026-09-26: Profit & Loss shows one month at a time; it should also
show a whole financial year, or the months a user picks.

**What exists:** `GET /api/v1/finance/profit-loss?accounting_period_id=`
takes exactly one accounting period (a month) and returns that month with a
year-to-date column beside it (`GeneralLedgerService.profit_and_loss`). The
desktop page (`desktop/lib/ui/finance/profit_loss_page.dart`) offers one
period picker. So a full year is only readable as the last month's
year-to-date column, and a quarter or any other span not at all.

**To build when scheduled** (the Tally / Zoho / Busy convention):
1. **Server:** accept a range -- `from_period_id` and `to_period_id` (or a
   `financial_year_id` for the whole year) -- and sum income and expense over
   every period in it. Periods stay the unit, so a range can never cut a
   month in half or cross into another financial year's closing.
2. **Screen:** a period chooser with presets -- This month, Last month, This
   quarter, This financial year, Last financial year -- and "Custom" for a
   from-month and a to-month.
3. **Columns:** the chosen span, and optionally month by month across the
   span (one column per month with a total), which is how owners compare
   months side by side.
4. **Comparison:** the same span last year beside it, as a second column.
5. The same range choice suits the Trial Balance and the ledger statement,
   which are also one-period today; decide together when this is scheduled.


## 51. Email, WhatsApp, SMS and payments -- basic version, planned 2026-09-27

**Status, 2026-10-02: A1, A5 and B1-B3 built** to the owner's decisions of 2026-10-01: the firm switches messaging on itself (no platform gate), configures its own SMTP / Meta WhatsApp Cloud API / MSG91 account on its own Settings > Messaging page (encrypted, Test before enabling), and picks which events send by which channel; outbox with retry and fallback, reminders, customer opt-outs, every send on the timeline, `DOCUMENT_SEND`. See `docs/MESSAGING_FRAMEWORK.md` and `docs/MESSAGING_SETUP_GUIDE.md`. Proven against fake providers only. Open: A2-A4, B4, sending documents other than the invoice by hand.

Owner, 2026-09-27: plan email, WhatsApp, SMS and a payment gateway now, as a
basic version; build after review. This takes up **§14** (emailing a
document), **§42.1** (WhatsApp, SMS, reminders) and **§42.10** (UPI QR and
payment links), and answers their open questions by the convention of Tally,
BUSY, Vyapar and Zoho Books, for the owner to confirm at the review.

**Detail for Phase B, and the rule that it ships off and each firm switches
it on with its own provider account:** `docs/MESSAGING_FRAMEWORK.md`
(2026-09-30).

### What exists to build on

- **The PDFs.** Every document already prints on the server (for example
  `GET /api/v1/sales-invoices/{id}/print`); those bytes are what an email
  attaches and what WhatsApp shares.
- **Where to send.** A customer has `email` and `phone`, and each contact
  person a `mobile` and an `email` (`app/customers/models/customer.py`);
  vendors have the same shape. Vendors have a `upi_id`; the firm has none yet.
- **Where to record it.** `document_timeline.email_recipient` and
  `document_states.allows_email` exist with nothing writing them.
- **What does not exist:** any sending, any provider account, any outbox.

### The one constraint that shapes all of it

**The server sits inside the office.** It can call out to a provider, but a
provider cannot call in (no public address), so nothing may rely on a
*webhook*. Every status -- delivered, bounced, paid -- is **fetched by the
server**, on a timer, from the provider's API. This keeps the product working
for an installed firm with no IT, and is what decides the payment design
below.

### Phase A -- basic, no paid provider needed

| # | Feature | How it works | Needs from the firm |
| --- | --- | --- | --- |
| A1 | **Email a document** (invoice, order, statement, receipt, purchase order) -- **all five built 2026-10-03** (MSG-4, A95) | From the document's bar: *Email*. Pre-filled to the party's email, a covering message per document type, the PDF attached. Sent through the **firm's own mail account** (SMTP: Gmail or Outlook with an app password, or the firm's domain mail) | Its mail account details, once, in Settings |
| A2 | **Share on WhatsApp** | *WhatsApp* on the bar opens WhatsApp (desktop app or web) to the party's number with the message typed in (invoice number, amount, due date); the PDF is saved and its folder opened, for the user to attach. No API, no cost -- what Vyapar and most small-business products do. **Built 2026-10-03 for the invoice (MSG-1, A56)** | WhatsApp installed on the PC |
| A3 | **UPI QR on the invoice** | The printed invoice carries a UPI QR for the amount due (`upi://pay?pa=<firm UPI ID>&am=<amount>&tn=<invoice no>`). The customer scans and pays from any UPI app. No gateway, no internet. **Built 2026-10-03 (MSG-2, A55)**: the UPI ID is set in the invoice's Print settings | The firm's UPI ID, once, in Firm Settings |
| A4 | **Payment reminders, by hand** | On the overdue invoices list and customer statements: *Remind* sends the statement or the overdue list by email (A1) or WhatsApp (A2). **Built 2026-10-03 (MSG-3, A57)** | -- |
| A5 | **A record of every send** | Each send is a line on the document's timeline: channel, to whom, by whom, when, and *sent* or *failed* with the reason. A failure shows on the document; it never blocks or undoes the document | -- |

### Phase B -- automatic, through a provider (the firm pays the provider)

| # | Feature | How it works | Needs from the firm |
| --- | --- | --- | --- |
| B1 | **SMS** | Receipt confirmations and payment reminders by SMS through an Indian provider (MSG91, Textlocal and the like) | **DLT registration** with a telecom operator (TRAI rule): its sender ID and each message template registered -- the firm's paperwork, a few days, not ours to do |
| B2 | **WhatsApp Business API** | The PDF sent directly, no user step, through Meta's Cloud API or a partner (Interakt, AiSensy, Gupshup) | A WhatsApp Business account; each message template approved by Meta; about ₹0.1 to ₹0.9 per message, billed by the provider |
| B3 | **Automatic reminders** | A schedule per firm: before the due date, on it, and every N days after, by the channels the firm chose; stops when the invoice is paid | -- |
| B4 | **Payment links** | *Payment link* on an invoice creates a link through Razorpay or Cashfree (card, UPI, net banking), sent by A1, A2, B1 or B2. The server **fetches** the link's status (no webhook, above); when paid it creates a **draft receipt** against the invoice for a person to approve, with the gateway's fee recorded as a bank charge | A merchant account (KYC by the gateway, a few days) |

### Decided by convention (to confirm at the review)

1. **Whose account:** the **firm's own** mail, SMS, WhatsApp and gateway
   accounts, never one shared by the platform -- the customer sees mail from
   their own supplier, costs land on the firm that sends, and one firm's
   spam complaint cannot stop another's messages.
2. **Credentials** are entered in **Settings → Messaging** and **Settings →
   Payments** by the firm administrator, stored **encrypted** with a key held
   in the server's config (not in the database), and never shown again after
   saving -- only *replace* or *test*.
3. **Attach, not link**, for email: the customer's accounts department files
   the attachment, and nothing is served to the internet.
4. **A failed send never blocks a document** and is never silent: it is on
   the timeline and shown on the document (A5).
5. **Sending is its own permission** (`DOCUMENT_SEND`), not `*_VIEW`:
   printing shows what the screen shows, sending acts for the firm towards
   somebody outside it. Settings need `SETTINGS_UPDATE`.
6. **A gateway payment is never posted unseen:** it becomes a draft receipt
   (B4), because a receipt posts to the books and must be reversible by the
   same rules as any other.
7. **Opt-out:** a customer can be marked *no reminders*; B3 skips them.

### Open for the owner at the review

1. **Which providers** to support first -- one each is the basic version: an
   SMS provider, a WhatsApp partner or Meta direct, and Razorpay or Cashfree.
2. **Phase B in 1.x at all**, or Phase A first and B after firms ask.
3. **Message wording** -- the covering message and reminder text per
   document type, in English only or also in Hindi and regional languages.
4. **Reminder schedule defaults** for B3 (for example 3 days before, on the
   due date, then every 7 days).

### Size

Phase A is about the size printing was: a settings page, one sending service
with an outbox and retry (the server may be offline when a send is asked
for), the timeline record, and a button on each document's bar. Phase B adds
one adapter per provider plus the status fetcher, and the draft-receipt step
for payments.

## 52. Extra fields on documents, not only on masters

Owner, 2026-09-27: the system must stay open to change -- tax, prices, and
collecting extra information -- without a new release. Tax (versioned rules
with effective dates) and prices (dated price lists and promotions) already
are. **Extra information is open on masters only:** `AttributeEntityType`
(`app/business/models/framework.py`) lists products, customers, vendors,
branches, warehouses, tax profiles and units. A firm cannot add a field to a
**document** -- a vehicle number or transporter on a delivery note, the
buyer's PO reference or a site name on an invoice, a salesman's remark on an
order -- without a code change.

**To build when scheduled:** add the document types (header first: sales
order, delivery note, sales invoice, purchase order, goods receipt, purchase
invoice, returns; lines later if asked) to `AttributeEntityType` and call
`AttributeService` from each document's service, as customers and vendors do
(`docs/CUSTOM_FIELDS_FRAMEWORK.md`). Then:
1. The document screen shows them in an *Additional details* section.
2. **They carry forward** down the chain (order → delivery → invoice) where
   the same definition exists on both, as prices do.
3. A field can be chosen to **print** on the document.
4. Lists can show and filter by them, through **Columns** and **+ filter**.

**What stays a code change, by nature:** a new *kind* of tax calculation
(TDS under 194Q, tax on MRP less abatement), and a change in a government
format (GSTR-1 JSON, the e-invoice schema). Rates, thresholds, and which rate
applies to what are configuration.

## 53. PAN and TAN: record both, check them, and use them

**Status, 2026-10-02:** item 2 built -- PAN and TAN format checks on customers, vendors and the firm, PAN filled from and checked against the GSTIN (checked only when set). 53.1: the 26Q export is built as a workbook for the CA / RPU (Reports > Financial > *TDS return (26Q)*); the FVU text file waits on the challan screen. See `docs/OWNER_DECISIONS.md` A7-A8.

**Status, 2026-10-03:** the PAN reports are **built** (PLT-11, A53) -- Reports > Financial > *Customer PAN check* and *Supplier PAN check* (`GET /customers/reports/pan`, `GET /vendors/reports/pan`): every live party with no PAN, a blank PAN its GSTIN carries, a PAN not in the PAN format, or one that is not characters 3 to 12 of the GSTIN, the problem named per row.

Owner, 2026-09-27: customers in the market carry both a PAN and a TAN; the
product should tell them apart and put each to work.

**Status, 2026-10-01.** Items 1, 3 and 4 are built (see §53.1): TAN on the
firm and customers, *TDS deducted* on payments, receipts and expenses, and both
TDS registers. Of item 2 only the TAN format check (firm, customer) and the
PAN format check on an expense's payee exist (`app/core/validation/common.py`);
customer and vendor PANs, the vendor's TAN and the PAN-against-GSTIN match are
not checked yet. Item 5 (194Q) is §42.4.

**The difference.** **PAN** identifies a taxpayer (every business and person
has one). **TAN** identifies somebody who **deducts or collects tax at
source**; only a party that deducts TDS or collects TCS has one, and it is what
their deduction is filed under -- and what the other side sees in Form 26AS.

**What exists (2026-09-27):**

| Record | PAN | TAN | Used by anything |
| --- | --- | --- | --- |
| Firm | `pan_number` | **none** | PAN unique among live firms |
| Customer | `pan_number` | **none** | TCS: no PAN meant the higher rate (`app/tcs`) |
| Vendor | `pan` | `tan` | Stored only; nothing reads them |

Nothing checks either format, or that a PAN matches its GSTIN.

**Why it matters now.** The Finance Act 2025 omitted TCS under 206C(1H) from
1 April 2025 (`app/tcs` already stops charging it on receipts from that day).
What remains is **TDS under 194Q**, the buyer's side, and that is where PAN
and TAN do their work -- in both directions for a distributor:

- **As a buyer** (the firm buying from its principal, over Rs 50 lakh a
  year): the firm deducts TDS from the supplier's payments. It needs **its
  own TAN** and the **supplier's PAN** (no PAN means the higher rate). This is
  §42.4.
- **As a seller** (a large customer buying from the firm): the **customer**
  deducts TDS and pays the firm short. The firm must record the shortfall as
  **TDS receivable** -- an asset, claimed against its own income tax -- not as
  a discount or a bad debt, and match it against 26AS **by the customer's
  TAN**. Today a short receipt simply leaves the invoice part-open.

**To build when scheduled:**
1. **Fields.** TAN on the firm (Firm Settings) and on customers; keep the
   vendor's. Labelled plainly: *PAN (income tax)*, *TAN (deducts tax at
   source)*, beside *GSTIN*.
2. **Checks on save.** PAN is `AAAAA9999A`, TAN is `AAAA99999A`; a GSTIN's
   characters 3 to 12 must equal the party's PAN, so the PAN can be **filled
   from the GSTIN** and a mismatch refused. The PAN's fourth letter gives the
   holder type (C company, F partnership, P individual, H HUF ...), which can
   pre-fill the party's type.
3. **A customer that deducts TDS.** A flag *deducts TDS on payments to us*
   (set automatically when a TAN is entered, editable), with the section and
   rate. The **receipt** then offers *TDS deducted* beside the amount: the
   invoice is settled in full, the cash posts to the bank, and the TDS part
   posts to a **TDS receivable** account (a new control purpose).
4. **Reports.** TDS deducted by customers, by TAN and quarter, to tick
   against 26AS; parties with no PAN (they cost the higher rate); PAN and
   GSTIN mismatches.
5. **194Q as a buyer** is §42.4, and uses the same fields.

**Confirm with the firm's CA at the review:** the rates and the threshold as
they stand in the current Finance Act, and whether any other section (194C,
194J) matters to these firms. Rates and thresholds go into settings, never
into code, as TCS already does.

### 53.1 Firms that already hold a TAN -- owner, 2026-09-27 -- HIGH PRIORITY

**Priority (owner, 2026-09-27): high.** **Items 1 and 2 built 2026-09-30**
(migration `20260930_0166`). **Items 3 and 4 built 2026-10-01**, before
go-live rather than in 1.1 (migration `20261001_0175`): *TDS deducted* and its
section on payments, receipts and expenses, and the *TDS deducted* and *TDS
deducted by customers* registers; rules in `docs/LEDGER_POSTING_RULES.md`,
"Tax deducted at source posts with the money". Left: a challan screen (today a
journal), party defaults (a supplier's usual section), and a 26Q export file.
**Built 2026-10-03 (ACC-7, A79):** the challan screen (Accounts > Tax filing >
*TDS Challans*, `tds_challans`) and a supplier's usual section; the 26Q
workbook names each deduction's challan. Left: the FVU text file.

| When | What | Size |
| --- | --- | --- |
| **Before go-live** | Items 1 and 2 below: TAN on the firm and customers; TDS Payable and TDS Receivable in every firm's chart | About a day |
| **Before go-live** | The interim steps at the end of this section, in the go-live guide | Docs only |
| **First update after go-live (1.1)** | Items 3 and 4: *TDS deducted* on payments, expenses and receipts, and the quarterly TDS list for the CA | About a week |

**Move 1.1 before go-live** if a first go-live firm is a mid-size
distributor (turnover over Rs 10 crore, buying over Rs 50 lakh a year from a
principal): every payment to the principal carries 194Q TDS, and a journal
per payment is not a fair ask. Ask each go-live firm: do they hold a TAN, and
does their CA file their TDS returns?


Some firms using the product hold a TAN today, which means they deduct TDS --
on supplier purchases (194Q), and commonly on **rent (194-I), professional
fees (194J) and contractors such as transporters (194C)**. None of that can be
recorded properly yet:

- The firm has **nowhere to enter its TAN**.
- The default chart has **TCS Payable but no TDS Payable or TDS Receivable**
  (`app/finance/services/opening_setup.py`).
- A payment to a supplier, and the coming Expenses screen (#814), can pay
  only the full amount: there is no *TDS deducted* part.

**Order to build, smallest first:**
1. TAN on Firm Settings and on customers (a field and a check).
2. *TDS Payable* (liability) and *TDS Receivable* (asset) in the default
   chart, backfilled for firms with open books as `20260927_0162` did for
   Indirect Expenses, each with its control purpose.
3. *TDS deducted* on **payments** and **expenses**: the section and rate
   from the vendor (or expense account), the supplier settled in full, the
   deduction posted to TDS Payable. A quarterly report of deductions by
   section and deductee PAN, for the 26Q return and the challans.
4. *TDS deducted* on **receipts** (53 item 3), to TDS Receivable.

**Until then (tell a firm that asks):** add *TDS Payable* and *TDS
Receivable* under Chart of Accounts, record the payment or receipt for the
net amount, and a journal entry for the TDS part -- debit the supplier, credit
TDS Payable; or debit TDS Receivable, credit the customer.

## 54. Trade licences: the firm's, the customer's, and the goods that need them -- built 2026-09-30

**Status, 2026-10-01: all five steps built.** Licence types, the register for firm/branch, customers and suppliers, printing, the Home expiry alert and the desktop screens (#839); the required licence on category and product, the sale check (warn by default, block by policy, override permission with a reason) and the purchase check (#840).

**Priority (owner, 2026-09-27): high, depending on the trade of the first
go-live firms.**

| Trade | Importance |
| --- | --- |
| Pharma distribution | **Essential, a go-live blocker**: a wholesaler may sell only to licensed buyers, and pharma invoices carry both sides' drug licence numbers |
| Food / FMCG | Needed, small: the firm's FSSAI number on every food invoice |
| Agri (pesticide, fertiliser, seed) | Important: dealers must be licensed; inspections check |
| Electronics, hardware, general | Not needed |

| When | What | Size |
| --- | --- | --- |
| **Before go-live** | Build order steps 1 and 4 (below): the register with validity dates; firm, branch and customer licence numbers printed on invoices; Home alert for licences expiring in 30 days | About 3 days |
| **After go-live** | Steps 2, 3 and 5: licence required per product or category; the sale check (warn, or block by policy); the purchase check | About 5 days |

**If a first go-live firm is a pharma distributor, build all of it before
go-live**: the sale check is what that trade compares products on.

**Order against TDS (53.1):** for a pharma target, licences first; for any
other, TDS first -- every mid-size distributor meets TDS, only some trades
need licences. **To settle at the review: which trades the first go-live
firms are in.**

Owner, 2026-09-27: some goods may only be bought and sold under a licence --
the firm needs one to trade them, and the customer needs one to buy them. The
product should hold both and act on them.

### What exists (2026-09-27)

| Where | What | Acted on |
| --- | --- | --- |
| Branch | `license_number` (one free-text number) | No |
| Vendor | `license_number`; per tax detail `fssai` and `drug_license` | Only gated: a drug licence may be recorded only by a firm whose profile has the `DRUG_LICENSE` feature |
| Customer | Nothing (a firm can add a custom field, which nothing reads) | No |
| Firm | Nothing | No |
| Product | Nothing says a product needs a licence | No |

No licence has a **type**, a **validity date** or a **scan**, and nothing
refuses or warns about a sale.

### The trades this covers (India)

| Licence | Who needs it | Goods |
| --- | --- | --- |
| **Drug licence**, wholesale (Forms 20B/21B) or retail (20/21); 20C/21C for Schedule X | Seller and buyer | Medicines; Schedule H/H1/X need the matching form |
| **FSSAI** registration or licence | Seller; printed on every food invoice | Packaged food, beverages |
| **Insecticide** licence | Seller and dealer buyer | Pesticides |
| **Fertiliser** authorisation | Seller and dealer buyer | Fertilisers |
| **Seed** licence | Seller and dealer buyer | Seeds |
| Others where a firm needs them | Poisons, explosives, arms, excise (liquor), narcotics | Configured, not built in |

### The design (decided by convention -- Marg, BUSY pharma, Tally add-ons)

1. **Licence types are a master**, not code: code, name, which form numbers
   it covers, whether it expires. The business profile seeds the usual ones
   (a pharmacy profile gets the drug forms, a food profile FSSAI, an agri
   profile insecticide, fertiliser and seed); a firm adds its own.
2. **One licence register for every holder**: the **firm** (per branch,
   since a drug licence is issued per premises), **customers** and
   **vendors**. Each licence: type, number, issued by, valid from, **valid
   to**, the premises it covers, and a scan (PDF or image) when file storage
   is built. A party may hold several.
3. **Products name the licence they need**, set on the **category** (all
   Schedule H medicines) and overridable on the product. A product with none
   needs none.
4. **The sale check.** On a sales order, delivery and invoice, each line's
   required licence type must be held by the **customer** with a valid-to on
   or after the **document's date**, and by the **selling branch**. Otherwise:
   - **Warn** by default, naming the line, the licence and why (missing,
     expired on ..., wrong type);
   - **Block** if the firm chooses (a firm policy, like credit control), with
     an override kept to a permission and recorded on the timeline.
   The server decides; the screen only shows it.
5. **The purchase check** is the mirror, on purchase orders and goods
   receipts: the vendor holds the licence for what it supplies. Warn only.
6. **Printing.** The seller's licence numbers print on documents that carry
   licensed goods (FSSAI on food invoices is mandatory); the buyer's drug
   licence prints on pharma invoices, as the trade expects.
7. **Expiry.** Home shows licences expiring in 30 days -- the firm's own
   first -- and a report lists every licence by expiry. An expired licence
   is kept, never deleted: it is the record of what was valid when a past
   sale was made.
8. **What stays as it is:** the existing vendor `fssai` / `drug_license` and
   branch `license_number` values are copied into the register by a
   migration (only where missing), then read from there.

### Build order

| Step | What | Size |
| --- | --- | --- |
| 1 | Licence types and the register (firm/branch, customer, vendor), screens in Masters and on each party | 2-3 days |
| 2 | Required licence on category and product | 1 day |
| 3 | The sale check (warn, then block by policy, override permission) | 2-3 days |
| 4 | Printing, Home expiry alert, expiry report | 1-2 days |
| 5 | The purchase check | 1 day |
| Later | Scans, when file storage exists | -- |

### Built so far (2026-09-30): steps 1 and 4

The owner settled question 1 on 2026-09-30: **all four trades go live**, so
pharma makes the whole of §54 a go-live item, steps 2, 3 and 5 included.

| Piece | Where |
| --- | --- |
| Licence types master, every type seeded for every firm (DRUG_WHOLESALE, DRUG_RETAIL, DRUG_SCHEDULE_X, FSSAI, INSECTICIDE, FERTILISER, SEED, OTHER) -- not per profile, since all four trades go live and a type a firm does not use costs nothing | `app/trade_licences`, `GET/POST/PUT/DELETE /api/v1/trade-licences/types` |
| One register for the firm (per branch), customers and vendors; standing (valid, expiring, expired, no valid-to) is derived on every read, never stored | `/api/v1/trade-licences`, `/expiring` (the firm's own first) |
| `TRADE_LICENCE_VIEW` / `_MANAGE`, group `trade_licences` -- not `LICENSE_*`, which is product licensing. Sales and purchase managers manage, executives view | `app/identity/system_seed.py`, migration `20260930_0167` |
| The old vendor `fssai` / `drug_license` and branch and vendor `license_number` copied into the register, only where missing | `20260930_0167` |
| Licences valid on the bill date printed for the seller (firm and branch) and the buyer on the sales invoice | `PartyBlock.licences` |
| Desktop: Trade Licences register in Masters, Licence Types under configuration, Home tile for licences expiring, licences listed on the customer and vendor forms | phase 2 |

Decisions taken by convention: **valid-to is required when the type
expires**, refused by the server and the dialog alike; an expired licence is
never deleted, only superseded by a new row. The **expiry report** is the
register itself sorted by valid-to -- a separate report adds nothing a
filtered list does not.

### Built: steps 2, 3 and 5 (2026-09-30)

| Piece | Where |
| --- | --- |
| `required_licence_type_id` on product categories and products. A product's own outranks its sub-category's, then its category's, then any category above -- the nearest wins. Null on a product takes the category's; a category edit that omits the field leaves it alone | `app/products`, migration `20260930_0168` |
| One judgement, `LicenceCheckService`: each line's required type must be held by the **customer** and by the **firm as seller** (a whole-firm licence or one for the selling branch) -- for a purchase, by the **vendor** -- valid on the **document's own date**. Findings name the lines, products, party and why: missing, expired on ..., valid only from ... A licence of another type does not count | `app/trade_licences/services/licence_check.py` |
| Firm policy `trade_licence_settings`: sale OFF / WARN / BLOCK, purchase OFF / WARN (BLOCK refused -- the goods on the dock have arrived). No row warns on both | `GET/PUT /api/v1/trade-licences/settings`, `TRADE_LICENCE_MANAGE_SETTINGS` |
| The sale check at the approval of the sales order, delivery note and sales invoice; the purchase check at purchase-order approval and goods-receipt completion. A warning is recorded on the APPROVED / COMPLETED timeline event and the audit row; BLOCK refuses before stock is reserved or shipped | the five services |
| Override: `?licence_override_reason=` on the three sales approve endpoints, refused 403 without `TRADE_LICENCE_OVERRIDE`; recorded on the timeline with what it overrode | `app/trade_licences/api/override.py` |
| A preview for the screen: `GET /api/v1/trade-licences/check/{document}/{id}` answers exactly what approval would | same service |
| A counter bill's chain (the order and note it raises) is not checked; the bill is, once, at its own approval -- two refusals for one sale would be one too many | `SalesChainService` passes `check_licences=False` |
| Deleting a licence type products or categories need is refused by name | `TradeLicenceService.delete_type` |

Decided by convention (owner questions 2 and 3 below): the sale check
**defaults to warn**; the check is **per line**, so a customer without any
licence still buys goods that need none. `TRADE_LICENCE_MANAGE_SETTINGS` and
`TRADE_LICENCE_OVERRIDE` go to the firm administrator and firm manager only --
both are controls over the people who sell, the split credit control makes.
A product can only add or change a requirement, not waive its category's;
a product that needs none belongs in a category that needs none.

### For the owner at the review

1. Which trades the first go-live firms are in -- pharma, food, agri --
   decides which licence types ship seeded first.
2. Whether the sale check defaults to **warn** (proposed) or **block**.
3. Whether a customer **without** any licence may still buy the goods that
   need none (proposed: yes, the check is per line, not per customer).

## 55. Market gaps with no backlog entry of their own -- validate before building

**Status, 2026-10-02:** G6 (last rate while billing, with its discount and *Use the last price*) and G8 (debit note to a supplier, `app/debit_note`) built. M9 (day book, cash book, bank book, drilling to the journal) and S7 (stock ageing, slow-moving and dead stock, vendor ageing) built.

Owner, 2026-09-27: every gap found against the market goes into the plan so
none is missed; **whether each is really needed is validated when it comes
up for implementation**, with the firms going live, not decided here. The
detail -- who has it, why it matters, effort -- is in
`docs/MARKET_COMPARISON.md`, by its id. Items that already have a section
here (§14, §35-§54) are not repeated.

**Status for every row: to validate.** When one is taken up: confirm with
the go-live firms that they need it, then give it its own section here (or
strike it with the reason).

| Id | Item | Priority as proposed | Note |
| --- | --- | --- | --- |
| G4 | Export to Tally (vouchers and masters, XML) | **High** | The firm's CA keeps the books in Tally |
| G5 | Batch-wise MRP and rates (PTR, PTS) | **High** for pharma and FMCG | `products.mrp` is one value per product |
| M9 | Day book, cash book, bank book; drill-down to the voucher | **High** | Goes with §50 (period ranges) |
| M10 | Fast counter billing with barcode -- **built 2026-10-03** (SEL-12, A90): scan to add, F9 save-print-next, tender split | High for counters | UI_PHASE_2_DESIGN 4.6 |
| M2 | Live e-invoice and e-way bill through a GSP | High above the threshold | A GSP contract first |
| G6 | Last rate while billing (sale and purchase) | Medium, small | |
| G7 | Picking list and loading sheet, by van or route -- **built 2026-10-03** (SEL-13, A92): pick list and loading sheet PDFs | Medium, small | |
| G8 | Debit note to a supplier | Medium, small | Mirror of credit notes |
| G9 | Cash discount for early payment; interest on overdue -- **built 2026-10-03** (SEL-14, A91): cash discount window, overdue interest on the statement, interest debit note | Medium | |
| G10 | Expiry and breakage claims to the principal | Medium | Extends §42.7 scheme claims |
| S7 | Stock ageing, slow-moving and dead stock; vendor ageing | Medium, small | Not in the report catalogue |
| S8 | Barcode label printing -- **built 2026-10-03** (STK-16, A65): A4 65/24-up sheets and 50 x 25 mm roll, from the product list and a goods receipt | Medium, small | After M10 |
| S11 | Cheque printing -- **built 2026-10-03** (ACC-12, A66): CTS-2010 leaf, per-bank offsets with a test print | Low-Medium, small | |
| S12 | Approvals and notifications (the bell) | Medium | UI_PHASE_2_DESIGN §9 item 15 |
| G11 | GSTR-9; composition-scheme firms and parties | Low-Medium | |
| G12 | Returnable containers (crates, cans, cylinders) | Low, by trade | Beverage, dairy, gas |
| G13 | Printing in Hindi or a regional language | Low | |
| N1 | Payroll | Low | Export to the payroll tool or CA rather than build |
| N2 | Multi-currency with revaluation | Low | Importers only |
| N7 | Recurring invoices | Low | §42.15 |
| N8 | Budgets and variance | Low | |
| N9 | Custom report builder | Low | Excel export covers most |

Already planned elsewhere, for completeness: M1 §45 (built), M3 §51, M4
PR #814, M5 §42.2-42.3, M6 §46 and §36, M7 §42.4 and §53.1, M8 §42.5, M11 §2,
S1 §48.1 and §39, S2 §42.7, S3 §42.9, S4 §51, S5 §38, S6 §42.12, S9 audit
entry, S10 §44 and §37, S13 §43, G1 §54, G2 §53, G3 §52, N3 §42.14, N4
§42.13, N5 §42.2, N6 §51, N10 §41, N11 §48-49, N12-N13 §42.15.

## 56. Bulk approval, migration from other tools, and data over the years -- HIGH PRIORITY

**Status, 2026-10-01.** *A -- bulk approval:* sales and purchase orders built (#864); **sales and purchase invoices, delivery notes, credit notes (approve only), sales and purchase returns and draft journals (post) built 2026-10-01** -- the same `run_each`, each row through its single action's service, ticked on the phase 2 lists. Sales and purchase orders: `POST .../bulk-approve` and `.../bulk-cancel` (a reason), up to 100 rows, each row through the single action's service and committed on its own, refusals reported per row with *Retry the refused*; `run_each` in `app/document_framework/services/bulk_actions.py` is the pattern for invoices, credit notes, returns and journals next. Neither order has a *reject* transition, so the second action is Cancel with a reason. *B -- migration:* see §36 and §46. *C -- performance:* steps 1-3 and 5 merged (#854, #856, #857, #859), step 4 in #860 and a second part after it; results in `docs/PERFORMANCE_AT_VOLUME.md`. *Year-end close:* built (#865) -- close refuses while a period is open or a draft journal is dated in the year, then locks; reopen needs `FINANCIAL_YEAR_REOPEN` and a reason. **No closing entry is posted** (decided 2026-10-01, as Tally does): the balance sheet already derives retained earnings and the trial balance brings profit forward (D-FIN-22).

Owner, 2026-09-27: three streams to run in parallel, designed from how
Tally, BUSY, Marg, Vyapar, Zoho, Odoo and ERPNext do it. **The design is
`docs/BULK_APPROVAL_MIGRATION_AND_YEAR_DATA.md`**; this entry is the plan.

**Decided by convention (to confirm at the review):**
1. **One continuous database, no year split** -- as Zoho, Odoo and ERPNext,
   and as Tally recommends until audit. The Indian desktop tools split years
   because their data files must load whole; PostgreSQL reads by index.
   Year-end is a **closing entry plus a lock**, and balances simply continue.
2. **Bulk approval is per row, not all-or-nothing** -- one order over its
   credit limit must not hold back the rest -- through the same service as a
   single approval; reject needs a reason. (Only Zoho does bulk approval
   well; the desktop tools approve one at a time.)
3. **Migration targets the opening position** -- masters, bill-wise
   customer and vendor outstanding, opening trial balance, opening stock with
   batches -- **not full history**; the old tool stays read-only for that.
   Every import: template, dry run with per-row errors, commit once. Tally's
   XML exports after the Excel path works.

| Stream | First | Then | Later |
| --- | --- | --- | --- |
| A. Bulk approval | Framework + sales and purchase orders | Invoices, credit notes, returns, journals | Approval rules, multi-level, notifications |
| B. Import and migration | Framework + products, customers, vendors (§46) | Opening bills, opening trial balance, *Opening balances* on Set up (§36) | Tally XML |
| C. Performance | Large test firm and timings; the Inventory list's history loading, stock sums, `journal_entries` date index, unpaged reports | Current-year default on lists (§37); set-based balance update; retention on by default | Year-end close; partition `audit_logs` if needed |

Targets for C: a list opens in under 1 second, a report in under 3, on the
minimum hardware.

## 57. Settings gear: the Selling section -- built 2026-10-01

**Status, 2026-10-01: built (#863).** Sales Stages, Credit Control, Loyalty Scheme and TCS Settings behind the gear and in Ctrl+K, each opening the dialog its screen's ... menu opens, which still offers it.

Noticed on 2026-09-28, discussing the sales chain with the owner.

**What exists.** `docs/UI_PHASE_2_DESIGN.md` §4.13 gathers every setting
behind the **Settings gear**, and appendix A places four under
**Settings > Selling**. The gear today has Firm, Buying, Stock, Tax and
Business profile (`MenuLayout.settings` in
`desktop/lib/phase2/menu_layout.dart`) and **no Selling section**. The four
are still reachable only from the **...** menu of their own screens:

| Setting | Where it is today |
| --- | --- |
| Sales stages (`sales_workflow_settings`) -- which of quotation, sales order and delivery note a firm types; a one-person firm switches all three off and bills straight from the invoice | Sales Invoices > ... > Sales stages |
| Credit control (`credit_control_settings`) | Customers > ... |
| Loyalty scheme | Loyalty > ... |
| TCS | TCS > ... |

It was recorded only in the design and in a code comment
(`menu_layout.dart`: they "join [settings] when the Settings page of 4.13 is
built"), never here, so nothing on the work list carried it.

**The ask.**

1. A **Selling** group behind the gear holding the four, each gated by the
   permission its screen already uses (sales stages: read `SALES_VIEW`,
   change `SALES_MANAGE_SETTINGS`; credit control: `CUSTOMER_MANAGE_SETTINGS`).
2. **Each stays in its screen's ... menu as well** -- findable both ways, as
   §4.13 says.
3. The Ctrl+K box finds each by name ("sales stages", "credit limit",
   "loyalty", "TCS").

No backend work: the endpoints exist. `test/menu_layout_test.dart` and the
phase 2 menu tests are what to extend.

## 58. One invoice for several delivery notes (D-SELL-39) -- built 2026-09-30

**Status, 2026-10-01:** items 1-3, 5 and 6 built (#844), for supplier bills against several goods receipts too (D-BUY-18). **Item 7 built 2026-10-01:** the printed bill's head lists each delivery note and the sales order behind it, each with its date, and the buyer's own order number where the order carries one (Tally's "Delivery Note No." and "Buyer's Order No."); past three it says "Several - see lines", and whenever a bill has more than one note every line names its note. **Items 2 and 4 built 2026-10-03 (SEL-1, A54):** the customer (supplier) is chosen first and their notes (receipts) are ticked from a list showing number, date, order and amount left; a note that clashes in branch, salesman, territory or route cannot be ticked and names the field and the note. §58 is complete.

Noticed on 2026-09-28, discussing the sales chain with the owner.

**What exists.** The server bills several delivery notes on one invoice
(`source_documents` on the create body, one `sales_invoice_sources` row each).
It refuses a mix unless every note has the same customer and branch, the same
salesman, territory and route where set, and has been dispatched. The screens
offer one note only: "Bill this delivery note" is a single dropdown in both
invoice editors.

**The ask** -- consolidated billing, as Tally, Zoho, Odoo and ERPNext offer it:

1. Choose the **customer** first.
2. A tick list of that customer's dispatched notes with something left to
   bill: number, date, order number, amount left.
3. The ticked notes' lines are gathered into the one bill, each line keeping
   the note it came from; quantities stay editable within what is left.
4. Notes that differ in branch, salesman, territory or route are refused on
   the screen, naming the note and the field, before the server is asked.
5. Editing a draft keeps its notes fixed, as today for the one note.

**Not changed:** a firm with the delivery-note stage off still bills one sales
order per invoice -- that bill dispatches the goods itself.

**The preview and the printed bill follow the invoice** (owner, 2026-09-28:
the preview and the invoice are one feature and must behave the same).

6. **Preview.** `/sales-invoices/preview` already stages the bill through
   `stage_invoice`, the same code as saving, so it takes several notes with no
   change; the editor must send every ticked note to it, and the preview pane
   shows which note each line came from.
7. **Printed bill.** The PDF names only the invoice's own `reference_number`
   (`invoice_print_service.py`), no delivery note or order numbers. The GST
   convention (Tally's "Delivery Note No." and "Buyer's Order No.") prints
   them, so the bill lists **every** note and order it covers -- one line each,
   or "several, see lines" with the note number on each line when there are
   more than fit. A bill of one note prints its one note and order.

Backend work is only item 7. Tests: the phase 2 invoice editor's widget test;
backend tests that preview and then save one bill of two notes from two orders
and get the same totals, and that its PDF names both notes.

**Built 2026-09-30 (D-SELL-39, D-BUY-18; desktop only, phase 2 screens).** The
invoice editor and the supplier bill editor keep their first picker as the
primary document and add an **Also bill** control beside it: it lists the other
billable delivery notes (goods receipts) of the same customer (supplier) and
branch, and hides when there are none. Adding one puts its lines on the bill at
what is left, each row naming the note or receipt it came from; the chip's x
takes them off again. The preview and the save send every line with its own
source, numbered 1..n. A sales draft of several notes reopens with all of them;
the buying screen only creates. Choosing a different primary document clears
the added ones. It is a menu rather than the tick list of item 2, so the
"choose the customer first" step and the salesman/territory/route refusal on
screen (item 4) are not built -- the server still refuses those. Item 7 (the
printed bill naming every note) was built later the same day (status above).

## 59. Promotions: a "best offer only" mode

**Status, 2026-10-02:** item 3 built -- an optional maximum combined offer discount per line in Combine mode (Settings > Selling > Sales Stages); the latest-applied offer gives back first and campaign costs are reduced to match.

**Status, 2026-10-01: items 1 and 2 built.** Settings > Selling > Sales Stages carries **When several offers match**: *Combine offers* (the default; every firm keeps today's pricing) or *Best offer only* (`sales_workflow_settings.promotion_mode`, migration `20261001_0178`). In best-offer mode every matching offer is valued on its own -- discounts, bill discount, free units at the line's own rate, a free product at its selling price, waived delivery at its charge -- the most valuable is applied, a tie goes to the earlier *Applies at*, and each loser's decision says what it was worth against the winner. Left: item 3, a maximum combined discount per line in Combine mode (60 item 1's cap covers the per-offer case).

Noticed on 2026-09-28, explaining promotions to the owner
(`docs/PROMOTIONS_AND_DISCOUNTS_GUIDE.md` section 4).

**What exists.** Matching promotions always **combine**, in "Applies at"
order, compounding, until one with stacking switched off ends the stack. The
only way to make one offer exclude another is priority plus that switch.
There is no "give the customer whichever single offer is worth most", and no
cap on the combined discount.

**The ask**, as most retail and distribution tools offer it:

1. A firm-wide choice under Settings > Selling: **Combine offers** (today's
   behaviour, the default so no firm changes) or **Best offer only**.
2. Best offer only: evaluate each matching promotion on its own and apply the
   one that takes the most off the document; ties go to the lower "Applies
   at". The execution log records every candidate and why it lost.
3. Optionally a **maximum combined discount %** per line, for Combine mode.

Free goods and free shipping have no rupee value to compare until costed;
decide at design time whether they are valued at selling price or excluded
from the comparison.

## 60. Offers to market standard: festival offers, schemes, coupons, free items

Owner, 2026-09-28: promotions must be flexible enough to run any festival
offer -- coupons, discounts, free items, anything -- as the market does.
Designed against Tally/BUSY/Marg schemes, Vyapar, Zoho, Odoo and Shopify-style
retail offers. `docs/PROMOTIONS_AND_DISCOUNTS_GUIDE.md` is what exists.

**Already possible** (a festival offer is an ordinary promotion with From/Until
dates): % or amount off a line; % or amount off the bill; buy X get Y of the
same item; conditions on product, category, customer, territory, route,
quantity, line value, order value; coupon-only offers with total and
per-customer limits; priority and stacking; order-value slabs (one promotion
per slab, highest slab first with stacking off).

**Built on the server, missing on the screen** -- D-SELL-42: free product
(buy X get a different item), free shipping, conditions on customer group,
branch, salesman, document type and date, and the tests "is one of", "between",
"is set". Fixing D-SELL-42 is the first step and needs no backend work.

**Missing, by market convention** (in the order most asked for):

| # | Offer | Example | Note |
| --- | --- | --- | --- |
| 1 | Percent off **with a cap** | 20% off, up to 500 | **Built 2026-10-01**: an *Up to* on both percent benefits, the cap on the whole document; on line percentages it is spread over the lines in proportion, summing exactly to the cap |
| 2 | **Best offer only** | give whichever single offer is worth most | backlog 59 |
| 3 | **Product and customer sets** | "any of these 12 products" | server has `IN`; needs a multi-pick on the screen (D-SELL-42) |
| 4 | **Buy X get Y at a discount** -- **built 2026-10-03** (SEL-2, A94): buy X get Y at a discount | buy 2, second at 50% off | new benefit; today only fully free |
| 5 | **Combo / bundle price** -- **built 2026-10-03** (SEL-3, A96): combo price apportioned by value | shampoo + soap for 150 | new benefit: a set price for a set of lines |
| 6 | **Festival bonus points** | double loyalty points during Diwali | **Built 2026-10-03** (SEL-4, A73): a *Bonus loyalty points* benefit multiplies what a bill earns at approval while the offer runs |
| 7 | **Bulk coupon codes** | 500 single-use codes for a campaign, exported to CSV | **Built 2026-10-03** (SEL-5, A70): *Generate codes* mints up to 5,000 single-use codes; *Export codes* gives the CSV |
| 8 | **Customer eligibility** -- **built 2026-10-03** (SEL-6, A98): first order, not billed in N days | first order only; customers not billed in 90 days | new conditions |
| 9 | **Day and time** | weekends only; 4-6 pm | **Built 2026-10-03** (SEL-7, A72): weekday from the document date, time of day in India time from when it was raised |
| 10 | **Offer templates** | "copy last Diwali's offers, new dates" | **Built 2026-10-03** (SEL-8, A71): *Copy with new dates...* copies the ticked offers as drafts with a code suffix |
| 11 | **Manufacturer scheme claims** | free goods given on the company's scheme, claimed back | track the value per scheme to claim from the supplier |
| 12 | **Offer shown on the print** | "Diwali offer: 250 saved" on the bill | **Built 2026-10-01**: the bill head names the offers claimed on the orders it bills (*Offers*) and *You saved* -- line discounts plus the bill discount |
| 13 | **Try an offer before launch** | see today what next week's Diwali offer does to an order | **Built.** *Try offers* on the Promotions screen (behind "...") over `POST /api/v1/promotions/simulate`: a date, document, optional customer, coupon and delivery charge, and lines; it shows each line's discount and free goods, the bill discount, delivery waived, gifts, the total saved, and every offer tried with why it applied or not |

**Rules that stay** (from `docs/PRICING_AND_PROMOTIONS.md`): one engine for
every document; a typed discount beats every offer; offers are counted at
approval; editing an active offer makes a new revision; free goods are never
discounted; a bill discount reaches the GST.

**Suggested order:** D-SELL-42 (screen only) -> 13 -> 1, 2, 3 -> 12 -> 4, 5 -> 6, 7
-> the rest. Each benefit is a new `PromotionActionType` and each eligibility a
new `PromotionField`, so none changes how existing offers price.

## 61. Free goods and gifts from suppliers: for customers, and for the firm

Owner, 2026-09-28: suppliers send free items with a purchase delivery. Some
are meant to be passed on free to customers; some are not for customers at
all -- they are for the firm or its owner. How is each tracked?

**What exists.**

- **Free quantity of the same item** (a 10+1 scheme) is a field on the
  purchase order line and the goods receipt line. Receiving puts
  **accepted + free** into stock as ordinary saleable stock of that product,
  and spreads the line's value over all of it, so the average cost falls
  (`GoodsReceiptService._receipt_unit_cost`). The bill charges only what was
  bought. This works.
- **A different free item** (50 bowls to give away with detergent) can only be
  received as an extra receipt line at price 0. It becomes saleable stock at
  zero cost, and nothing says it was meant to be given away.
- **Giving it to customers**: a sales line's free quantity of the same item, or
  a Free product promotion (server only -- D-SELL-42). Stock can also leave by
  write-off, but its reasons are DAMAGE, EXPIRY and LOSS only.
- **Gifts for the firm or owner** (a TV, a trip, a gold coin for meeting a
  target): **nothing**. The only way in is a zero-price receipt, which puts a
  television into saleable stock.
- **What the supplier owes back** for a scheme passed on to customers is §42.7.

**The ask**, by the usual convention (Tally and BUSY free-quantity schemes,
Marg scheme stock, standard accounting for supplier incentives):

1. **Free goods for customers.**
   - A product flag **For free issue only** ("promotional stock"): it can be
     received, given away and counted, but never sold at a price. The sales
     screens refuse a price on it; stock reports show it separately.
   - On the goods receipt, a free line names the **scheme** it came under
     (free text, or a link to the supplier's offer when §42.7 lands).
   - A stock issue reason **Given free to customer** (and **Sample**), naming
     the customer, costed to a **Promotional expense** account, beside the
     existing DAMAGE / EXPIRY / LOSS.
   - A report: free goods received per supplier and scheme, given away per
     customer, and what is left -- received = given + in stock.
   - Same-item free goods (10+1) stay as today: ordinary stock at a lower
     average cost. That is how every Indian trade tool treats them, and it is
     right, because the item is sold like any other unit.
2. **Gifts for the firm or owner.** Not stock and not for sale.
   - A **Supplier gifts and incentives** register: date, supplier, item,
     value (the supplier's declared value, or fair market value), who received
     it (firm or owner), and the purchase or scheme it came with.
   - Saving it posts one journal, chosen by who keeps it:
     - kept by the business as an asset: Dr **Fixed asset** / Cr **Other income -
       supplier incentives**;
     - used up by the business: Dr the expense / Cr the same income;
     - taken by the owner: Dr **Drawings** / Cr the same income.
   - No GST input credit is taken on a gift received free.
   - **TDS 194R:** a supplier giving benefits worth more than 20,000 in a year
     deducts TDS on them. The register totals value per supplier per financial
     year, and shows the 194R TDS deducted so it can be matched with Form 26AS
     (ties in with §53, PAN/TAN and TDS).
3. **Arriving with the delivery.** The goods receipt screen gets a third kind
   of line beside ordered and free: **Gift, not stock**. It records the gift in
   the register (2) instead of stock, so the person unloading the truck
   records everything that arrived in one place.

**Tests:** a 10+1 receipt lowers the average cost and the bill charges 10; a
free-issue product cannot be sold at a price; giving it away posts promotional
expense at its cost; a gift line on a receipt adds no stock and posts one
journal by who keeps it; the 194R total per supplier crosses 20,000 when it
should.

## 62. Sales analysis: any combination of period, product, customer and more

**Status, 2026-10-01: the core built.** Sell > Insight > **Sales Analysis**: rows and optional columns, each any of day, week, month, financial-year quarter, financial year, product, category, customer, customer group, salesman, territory, route, branch; figures quantity, taxable, tax, net sales, invoices (distinct, never summed across cells) and average bill; totals both ways; net of credit notes and completed returns by default, gross on a switch; presets for this month, last month and this financial year; click a cell or row total to list the invoices behind it (`/sales-invoices/reports/analysis` and `.../analysis/invoices`, grouped in SQL). Checked on PERF01: 5,000 products by 12 months over a year in 3.5 s, rows summing to the grand total. Left: filter pickers on the screen (the server takes them), orders-booked mode, margin, compare with last year, chart, export, saved layouts, the Home gadgets, and §66 for purchases.

Owner, 2026-09-28: sales needs a section, and Home gadgets, showing how much
was sold per day, per month, per product, per customer -- every combination.

**What exists.** Fixed reports only: orders by customer, by salesman and by
territory (`/sales-orders/reports/*`, orders booked rather than sales
billed); the invoice register, summary, pending and overdue lists
(`/sales-invoices/reports/*`); notes by route, salesman and warehouse; and
Home's "sales over 14 days" chart. There is **no** sales-by-product report, no
day / month trend over billed sales, and no way to cross two of them
(product by month, customer by product).

**The ask** -- a pivot over billed sales, as Tally (sales register and item
analysis), BUSY, Zoho (sales by item / customer / salesperson) and every BI
tool offer it:

1. **Sell → Sales Analysis**, one screen:
   - **Rows** and optional **Columns**, each any one of: day, week, month,
     quarter, financial year; product, product category; customer, customer
     group; salesman, territory, route; branch, warehouse. Examples: product
     by month; customer by product; salesman by month; category by territory.
   - **Figures**: quantity (in the sales unit), taxable value, tax, net sales,
     invoice count, average bill; and **gross margin** (value less cost of
     goods sold from the delivery notes) for users who may see cost.
   - **Filters** on every dimension above, plus a period (defaults to this
     month).
   - **Net of returns**: approved invoices less credit notes and sales
     returns in the same period, with a switch to show gross.
   - A switch to analyse **orders booked** instead of sales billed.
   - Totals per row and column; **click any figure** to see the invoices
     behind it; **compare** with the previous period or the same period last
     year (value and % change); chart view (line for periods, bars for
     products and customers); export to Excel, CSV and PDF; save a layout by
     name ("Monthly product sales").
2. **Home gadgets** (joins §49's gadget catalogue): today's sales; this month
   against last month; sales by day for the month; top 5 products; top 5
   customers; top salesmen. Each opens Sales Analysis already set to it.
3. **Who sees what**: `SALES_VIEW` for the analysis; margin only with a cost
   permission; a salesman sees only his own customers when his role says so.
4. **Speed** (§56 stream C targets: a report in under 3 seconds): one grouped
   query over invoice lines with an index on the invoice date; a daily summary
   table only if large firms need it.

**Tests:** each dimension alone and crossed with a period; totals equal the
invoice register for the same period; a credit note in the period reduces net
sales; drill-down lists exactly the invoices summed; a salesman limited to his
customers sees only theirs; margin hidden without the cost permission.

The same analysis for purchases (by vendor, product, month) follows the same
design once this lands; the existing Purchase Analytics screen is not offered
in phase 2.

## 63. Paying the tax: GST payable, set-off and payment; TCS deposit

**Status, 2026-10-01: items 1, 2 and 6 built.** Accounts > GST Payment works out a month from its GSTR-3B -- output tax per head after credit notes, net input credit per head, plus the credit the month before carried -- and sets the credit off by section 49(5) and rule 88A (IGST credit first and wholly, split across CGST and SGST to leave the least cash; CGST never against SGST nor SGST against CGST; cess only against cess), showing cash payable and credit carried per head, with interest at 18% a year suggested for days after the 20th. Recording the challan (CPIN, CIN, bank, interest and late fee to expense accounts the user picks) posts one journal and keeps the month in `gst_payments` (migration `20261001_0176`); one standing settlement per month, and only the latest month can be reversed. A firm's first month takes its opening credit from the portal's electronic credit ledger. Recording needs `JOURNAL_POST`. Item 5 **dropped** by the owner on 2026-10-02 (decision B8): 206C(1H) ended on 1 April 2025, so there is no TCS to deposit or file under it; the tax calendar already shows a TCS deposit only for a month that collected any.

**Item 4 built 2026-10-02:** a **Tax calendar** card on the phase 2 Home (shown to whoever may open GST Payment) lists, for the last three finished months the firm traded in, GSTR-1 (due the 11th; amount the month's output tax), GSTR-3B (due the 20th; the cash its payment works out to, reverse charge included) and the TCS deposit (due the 7th; only for a month that collected any) -- each due, late by N days, or done. Filing happens on the portal, so a return is closed by saying so: **Mark filed** records the date and ARN in `gst_return_filings` (migration `20261002_0208`, `JOURNAL_POST`, withdrawable); GSTR-3B also closes when the month's GST payment is recorded. A closed month drops off unless it is the latest. `GET /api/v1/gst-returns/calendar`, `POST /filings`, `DELETE /filings/{id}`; `app/gst_returns/services/tax_calendar.py`. Monthly filers then; quarterly filers since GST-7 (§74.1 row 11, A83). A TCS deposit never shows as done until item 5 records deposits.

**Item 3 built 2026-10-01:** output tax posts per head -- `OUTPUT_TAX_IGST / _CGST / _SGST` (2210 / 2220 / 2230), UTGST with SGST, cess and component-less documents on `OUTPUT_TAX` (2200) -- from the components each sales invoice and sales return recorded; a credit note splits its single tax figure the way its invoice was taxed (IGST, or CGST and SGST halves). Reversals mirror the split. Existing firms gain the accounts through `20261001_0201` and new ones through the chart seed (readiness's control-accounts step). History stays in 2200 as posted; the GST payment debits each head by what the month's documents credited to it, capped at the head's liability, and the rest to 2200 (`docs/OWNER_DECISIONS.md` A28). Reverse charge on purchases (§68 row 8) joins the payment as cash only.

Owner, 2026-09-28: sales collect tax -- is anything to be paid, and does the
product show it?

**What exists.**

- Every approved sales document credits **Output tax** (one account,
  `OUTPUT_TAX`, not split by CGST / SGST / IGST); every approved purchase bill
  debits **Input tax** split by IGST / CGST / SGST.
- **GSTR-3B** (`/api/v1/gst-returns/gstr3b`) shows the month's outward tax
  (3.1) and eligible, reversed and net input credit (table 4), per head.
- **TCS** collected on receipts is credited to `TCS_PAYABLE`; the TCS screen
  lists collections and charged-versus-due.

**What is missing -- the step from "collected" to "paid":**

1. **Net GST payable per month.** Output tax less input credit, per head, by
   the statutory **set-off order**: IGST credit against IGST, then CGST, then
   SGST; CGST credit against CGST then IGST; SGST credit against SGST then
   IGST; never CGST against SGST or back. Show credit carried forward, and
   **cash to pay** per head, with interest at 18% a year for days late after the
   due date (20th of the next month for monthly filers; 22nd/24th under QRMP).
   Reverse-charge tax is always paid in cash.
2. **Recording the payment.** A **GST payment** entry (the PMT-06 challan:
   CPIN, CIN, bank, date, amount per head, interest, late fee) that posts
   Dr output tax per head / Cr bank, and a **set-off** entry that posts
   Dr output tax / Cr input tax for the credit used. After both, output and
   input tax for the month are zero except credit carried forward -- the check
   that the books and the return agree.
3. **Output tax split by head** (`OUTPUT_TAX_IGST / _CGST / _SGST`), mirroring
   input, so the ledger answers "how much CGST do we owe" without a report.
4. **A tax calendar on Home** (§49 gadget): GSTR-1 due (11th), 3B due (20th),
   TCS deposit due (7th), with amounts and a warning when late.
5. ~~**TCS deposit and returns.**~~ **Dropped 2026-10-02 (B8).** Deposit the month's TCS by the 7th of the next
   month (challan 281: Dr `TCS_PAYABLE` / Cr bank, with the challan number);
   the quarterly **27EQ** return listing each collection by customer PAN;
   **Form 27D** certificates for customers. Ties in with §53 (TAN).
6. **Late fee and interest** posted to their own expense accounts, not mixed
   into tax.

**Not in scope:** filing on the portal (the sandbox rule in
`docs/LEDGER_POSTING_RULES.md` stands); GSTR-2B matching is §42.5.

**Tests:** a month with 18,000 output IGST and 10,000 input IGST shows 8,000
cash payable; CGST credit never pays SGST; credit beyond liability carries
forward; after payment and set-off the month's output and input tax accounts
are zero; a TCS deposit clears `TCS_PAYABLE` for its month; 27EQ lists every
collection with the customer's PAN.

## 64. Sales: five gaps no other entry covers

**Status, 2026-10-02: rows 2, 3, 4 and 5 built.** Row 2: a product's minimum selling price and its cost are floors judged on the net rate per stock unit when an order or a bill is approved; `price_floor_settings` warns (default), blocks or is off, and a block is lifted only with `SALES_PRICE_OVERRIDE` and a recorded reason (`docs/PRICING_AND_PROMOTIONS.md`). Row 3: `role_discount_limits` gives each role a maximum discount per firm; only a **typed** discount counts (line source `percent`/`amount`, a typed bill discount), judged per line at approval against the approver's limit -- the largest among their roles that have one, none for a platform administrator or a person whose roles have none. Above it the document stays a draft and the refusal names the limit it needs; the approval that clears it records both figures. Bill lines now store `discount_source`, so an inherited discount is not judged twice; a counter bill reads it from the order it raised. Settings > Selling > Price Floor and Discount Limits on the phase 2 desktop. Still open from the floor: costing is one weighted average per product, so an old near-expiry batch is judged against today's average; batch-wise cost is §70 row 9.

**Parked for discussion (owner, 2026-10-01):** near-expiry clearance and the cost floor. A sales line may pick an old batch to send first, but cost is one weighted average per product, so a near-expiry batch bought cheaper is judged against today's average and can read "below cost" when it is not. Proposed: a setting so the cost floor skips batches expiring within N days, the minimum price still applying (about a day). The alternative is batch-wise cost (§70 row 9), which changes stock valuation, cost of goods sold and every stock posting. **Not to be built until the owner decides.**

**Row 4 (2026-10-01):** A counter bill carries **Rate includes GST** (`sales_invoices.rate_includes_tax`), defaulting from `sales_workflow_settings.rate_includes_tax` (Settings > Selling > Sales Stages on the phase 2 desktop). A rate typed on a bare line -- and a discount amount typed with it -- is read back to its pre-tax rate before the order behind the bill is raised, dividing by the tax the buyer is billed (`TaxRuleService.simulate`, CGST + SGST or IGST, reverse-charge and price-inclusive components excluded; a value slab is asked again at the taxable value, once). `unit_price` stays the pre-tax rate, so the journal, returns, GSTR-1/3B and e-invoice are untouched, and `sales_invoice_lines.entered_rate` keeps the rate as typed for the print (A4 and roll show both) and the editor. A line continuing an order or a note, and a price the bill leaves to the product master, stay before tax. Bill discount and freight are still before tax. `app/tax/services/inclusive_rate.py`; `docs/PRICING_AND_PROMOTIONS.md`. **2026-10-02:** the same switch on the sales order and the quotation (`20261002_0207`, decision A32), on their phase 2 editors; absent on a new one is off, the typed rate and discount amount are kept and sent back on an edit, a quotation typed at shelf prices converts into an order typed at them, and the quotation print shows both rates.

**Row 5:** The phase 2 sales bill carries **Received now** -- amount, Cash or Bank, and a reference for Bank. Approving the bill records a receipt against it inside the approval's own transaction (the bill, its stock and its money land together or not at all), through the receipt service, so the journal, the balance and the reversal are a receipt's. More than the bill is refused rather than kept as an advance: change is handed back, and the editor warns before the save. UPI and card are Bank, as on a receipt; a separate tender list is §55 M10's.

Found 2026-09-28 reviewing sales end to end with the owner, after §57-§63.
Checked against §42, §55 and `docs/MARKET_COMPARISON.md` so nothing here is
listed twice. Each is **to validate** with the go-live firms, as §55 says.

| # | Gap | What exists | The ask, by convention |
| --- | --- | --- | --- |
| 1 | **Fixed special rates and price levels** -- "Anand pays 80 for detergent"; retail / wholesale / dealer rates -- **built 2026-10-03** (SEL-9, A89): price levels, fixed list rates, blank prices filled | Price lists hold **discount % ladders only** (`price_list_items.discount_percent`); a product has **one** `selling_price` | A price list line may give a **rate** instead of a %; products carry named **price levels** (Retail, Wholesale, Dealer), a customer or group is assigned one, and a rate from a list outranks the level. Ranked in `app/core/utils/pricing.py` like every other tier. |
| 2 | **Selling below cost or below a minimum price** | Nothing warns; only commission refuses to pay on a sale below cost | The line warns when the net rate is below the product's cost or its **minimum selling price** (a new product field); a firm setting chooses warn or block; a block can be lifted by a role holding a new permission. |
| 3 | **Discount limit per role** | Anybody who may edit an order may type any discount | Each role has a **maximum discount %**; above it the order is saved but needs approval by a role with a higher limit, and the approval records who allowed it. |
| 4 | **Typing a rate that includes GST** | Tax-inclusive treatment exists only as a tax-rule property; a line's rate is always before tax | A **Rate includes GST** switch per document (default from firm settings) so a counter can type the shelf price; the line derives the taxable value; the print shows both. |
| 5 | **Taking payment on the bill** | A receipt is a separate document on another screen | On the invoice: **Received now** (cash / UPI / card, amount, reference); approving the bill records the receipt against it in the same transaction; shows change due. Pairs with §55 M10 fast counter billing. |

**Already recorded, for completeness** -- the sales list as of today: §57
Selling settings; §58 / D-SELL-39 several notes on one bill; §59 best offer;
§60 offer types; §62 sales analysis; §63 paying the tax; D-SELL-40 to 43;
§42.1 WhatsApp and email; §42.6 salesman app; §42.7 scheme claims; §42.10 UPI
QR on the invoice; §44 user default branch; §52 document fields; §53 PAN/TAN;
§54 trade licences; §55 G5 batch-wise MRP / PTR, G6 last rate, G7 picking and
loading sheet, G9 cash discount and overdue interest, G12 returnable
containers, M2 live e-invoice and e-way bill, M10 counter billing.

## 65. Purchases: what the review with the owner found

**Status, 2026-10-02:** row 5's last part (the variance on the bill's own screen) and row 6 (debit note, §55 G8) built. A debit note on a bill already paid leaves its excess as supplier credit (decision A4, migration 0218).

Owner, 2026-09-28, the purchases half of the review that produced §57-§64.
`docs/PURCHASE_FRAMEWORK.md` and `docs/PURCHASE_TO_PAYMENT_FLOW.md` describe
what is built.

**How the documents link today.** Purchase order -> goods receipt ->
supplier bill -> payment, with returns off the receipt or the bill.

- One order, **many receipts** (part deliveries; receiving more than ordered is
  refused). A receipt always names **one** order -- there is no receipt
  without an order.
- One receipt can be billed in **parts**; one bill can cover **several
  receipts** of one supplier and branch on the server, but not on the screen
  (D-BUY-18).
- A bill never skips the receipt (D-BUY-14). A bill with no source is for
  services and expenses only (and Expenses, PR #814).
- A payment needs no bill (an advance); a return off the receipt becomes a
  supplier credit.

**Gaps, each to validate as §55 says:**

| # | Gap | What exists | The ask, by convention |
| --- | --- | --- | --- |
| 1 | **Stage switches** for a one-person firm: type the bill and let the order and receipt follow | Three screens for every purchase | **Built** -- §38, merged #836 2026-09-30 |
| 2 | **Several receipts on one bill** on the screen | One receipt per bill | **Fixed** -- D-BUY-18, with §58 (#844) |
| 3 | **Purchase order discount on the whole order** reaching tax, receipt and bill | Subtracted after tax, not carried on | **Fixed** -- D-BUY-19 |
| 4 | **Supplier rates**: a vendor's standing discount, a supplier price list with quantity breaks, and the **last purchase rate** while typing -- **built 2026-10-03** (BUY-3, A97): supplier standing discount and supplier price lists fill the order line | Only a typed discount; the product's one `purchase_price` | Mirror sales: vendor standing % and supplier price lists ranked in `app/core/utils/pricing.py`; last rate is §55 G6 |
| 5 | **Purchase price variance** explained per bill | Posted to its account, seen only as a P&L line | **Report built 2026-10-01**: Reports > Financial > *Purchase price variance* lists every approved bill line charged at a rate other than its receipt's -- supplier, product, both rates, quantity, variance; a bill in another unit is flagged. Left: the same on the bill's own screen |
| 6 | **Debit note** to a supplier for a price difference or a short-supply claim with no goods going back | Purchase return (goods back) only | §55 G8 |
| 7 | **Supplier free goods and gifts** | Same-item free quantity only | §61 |
| 8 | **Scheme claims** from the principal | Nothing | §42.7 |
| 9 | **Input credit at risk**: bills matched to GSTR-2B | 3B table 4 from the bills | §42.5 |
| 10 | **TDS on purchases (194Q)** above 50 lakh a year per supplier | Nothing | §42.4, §53 |
| 11 | **Landed cost**: freight, loading and duty added to stock cost | Nothing | §42.12 |
| 12 | **Reorder**: what to buy, from stock levels and sales | Nothing | §42.9 |
| 13 | **Purchase analysis by any combination** | Fixed reports by vendor, buyer, product | **Built** -- §66, #886 |
| 14 | **RFQ and supplier quotations** | Nothing (removed from the screens 2026-08-22) | Low for a distributor; validate |

**Suggested order:** 2 and 3 (defects, small) -> 1 (§38) -> 4 -> 5 -> 6 ->
the rest as the go-live firms confirm them.

## 66. Purchase analysis: any combination of period, product, supplier and more

**Status, 2026-10-01: built.** Buy > Insight > **Purchase Analysis**, the §62 screen reused as one widget (`AnalysisPage`, configured per side): rows and optional columns, each any of day, week, month, financial-year quarter, year, product, category, supplier, supplier category, branch; figures quantity, taxable, tax, total billed, bills (distinct) and average bill; totals both ways; net of purchase returns by default, gross on a switch; click a cell to list the bills behind it (`/purchase-invoices/reports/analysis` and `.../analysis/bills`, grouped in SQL, open to `PURCHASE_VIEW` or `REPORT_VIEW`). Left: filter pickers on the screen (the server takes them), the goods-received and orders-placed basis, average rate and price-difference figures, compare, chart, export, rate trend, saved layouts and the Home gadgets.

Owner, 2026-09-28: purchase reports like the sales ones (§62) -- by product,
by month, by year, by supplier, over any date range -- and as Home gadgets.

**What exists.** Fixed purchase-order reports: register, pending, overdue, by
vendor, by buyer, by product (`/api/v1/purchases/reports/*`), plus the goods
receipt and purchase return reports. They count **orders placed**; nothing
analyses what was actually **received and billed**, over time, or crosses two
dimensions (product by month, supplier by product).

**The ask** -- the §62 screen, built once and used for both, with purchase
dimensions and figures:

1. **Buy → Purchase Analysis**:
   - **Rows** and optional **Columns**, each any one of: day, week, month,
     quarter, financial year, calendar year; product, product category;
     supplier, supplier category; buyer; branch, warehouse.
   - **Period**: any date range, with quick picks (this month, last month,
     this quarter, this financial year, last financial year).
   - **Figures**: quantity (purchase unit), free quantity, taxable value,
     input tax, total billed, bill count, **average rate** per unit, and the
     **price difference** between receipt and bill (§65 row 5).
   - **Basis** switch: bills approved (the default, net of purchase returns
     and debit notes), goods received, or orders placed.
   - Totals, click-through to the bills behind a figure, compare with the
     previous period or the same period last year, chart view, export to
     Excel / CSV / PDF, saved layouts ("Monthly purchases by supplier").
2. **Rate trend**: for one product, the rate paid per supplier over time --
   who is cheapest, and whether prices are rising.
3. **Home gadgets** (§49 catalogue): purchases this month against last month;
   purchases by month for the year; top 5 suppliers; top 5 products bought;
   bills due to pay this week; goods received not yet billed. Each opens the
   analysis already set to it.
4. **Buy and sell side by side** (once §62 lands): per product per period,
   quantity bought vs sold and average buy rate vs average sell rate.
5. **Who sees what**: `PURCHASE_VIEW` for the analysis; a buyer may be limited
   to his own purchases when his role says so.

**Tests:** each dimension alone and crossed with a period; totals equal the
bill register for the same range; a purchase return in the range reduces the
net; the three bases give different, explainable totals for a part-received,
part-billed order; drill-down lists exactly the bills summed.

## 67. Sales against a full ERP checklist: what is built, and nine gaps

**Status, 2026-10-02:** rows 2-6 built -- account manager on the customer; ship-to per order carried down the chain and printed; payment terms on the order inherited by the bill; transport details on the delivery note feeding the e-way bill; proof of delivery with a *Not yet delivered* filter. See `docs/SALES_CHAIN_RULES.md` and `docs/OWNER_DECISIONS.md` A20-A21. Rows 8-9 built too: discount given by customer, salesman, product and offer (typed / arranged / promotion / bill share), and collections by day, salesman and mode.

Owner, 2026-09-28, supplied a 14-part checklist of a complete ERP sales module
(customers, CRM, quotation, order, delivery, invoice, collection, return,
credit note, debit note, pricing, tax, receivables, reports). Each part was
checked against the code the same day.

**Built** (no action): customer master with groups, several billing and
shipping addresses, contacts, GSTIN and PAN, credit limit and policy, payment
terms in days, standing discount, opening balance and live outstanding;
quotations with payment and delivery terms, validity, sent / accepted /
declined / converted, and "expired" derived from the validity date; orders
with part delivery, back orders, hold, close; delivery notes with batch and
serial, vehicle, driver, attachments, part delivery; invoices with due date,
payment terms, place of supply, bill-to and ship-to on the print, references
to the order and note; receipts with part payment, advances, one receipt over
many invoices, reversal; sales returns with reason, condition, restock and
damaged quantities; credit notes against an invoice's lines; the central tax
engine (CGST / SGST / IGST, HSN, exemptions, inclusive and reverse charge);
customer statement and ageing; the flow sales -> inventory -> accounting ->
tax -> payments, posted automatically. Terms and conditions print from the
print settings.

**Already recorded elsewhere:** customer-specific rates, maximum discount and
approval limits (§64); stacking and best offer (§59, §60); daily / monthly /
by customer / by product / margin reports (§62); payment reconciliation with
the bank (§42.2); one bill for several notes (§58).

**The nine gaps** -- each to validate with the go-live firms (§55):

| # | Gap | Today | The ask |
| --- | --- | --- | --- |
| 1 | **Enquiries and leads (CRM)**: enquiry -> opportunity -> quotation, products and quantity asked, expected value, follow-up dates, status, lost reason | Nothing before the quotation | A light pipeline: an **Enquiry** document (customer or prospect, lines, expected value, salesman, next follow-up, status Open / Quoted / Won / Lost with reason) that converts to a quotation; a follow-ups due list and a Home gadget. A prospect becomes a customer on conversion. |
| 2 | **Account manager on the customer** | A salesman reaches a customer only through territory, route or the document | `customers.salesman_id`, defaulting onto every new document for that customer; lists and §62 can filter by it. |
| 3 | **Ship-to chosen per order** | Every document ships to the customer's **default** shipping address | Order, note and invoice carry a `shipping_address_id` picked from the customer's addresses (default preselected), inherited down the chain and printed; place of supply follows it where the law says so. |
| 4 | **Payment terms on the order** | Only the invoice carries payment terms and due date | The order carries them (from the customer), and the invoice inherits rather than re-reading the customer. |
| 5 | **Transport details** on the delivery note | Vehicle and driver only | Transporter name and GSTIN, mode, LR / docket number and date, distance -- what the e-way bill needs (§55 M2) -- printed on the challan. |
| 6 | **Proof of delivery** | Attachments only; a note ends at dispatched / completed | Delivered on (date, time), received by (name), remarks, photo or signature attachment; a note is **Delivered** only with a proof; a list of notes dispatched but not yet proven delivered. |
| 7 | **Debit note to a customer**: extra charges or a price increase after billing -- **built 2026-10-02** (§77 row 5) | Nothing (only credit notes) | A debit note against an invoice, mirror of the credit note: raises the receivable, posts revenue and output tax, reported in GSTR-1 as a debit note. |
| 8 | **Discount report** | Nothing summarises what was given away | Discount given by customer, product, salesman and source (typed, price list, promotion, customer, group, bill), per period -- the discount_source already stored on each line makes it a report, not a data change. |
| 9 | **Collection report** | The receipts list, and commission on collections | Collections by day, by salesman, by mode (cash / bank / UPI), and against what was due in the period. |

**Suggested order:** 3, 4 (small, correctness of the documents) -> 5, 6
(delivery, and needed for e-way bill) -> 7 -> 8, 9 -> 2 -> 1.

## 68. Purchases against a full ERP checklist: what else to consider

**Status, 2026-10-02:** rows 1-2 built -- supplier payment terms default a bill's due date; Udyam number and MSME category on the supplier, `msme_pay_by` (45 days with a written agreement, 15 without) stamped on each micro/small supplier's bill, warned at approval, and Reports > Financial > *MSME payments due*. Row 4 built 2026-10-01: `role_purchase_approval_limits` gives each role a largest order (grand total incl. tax) it may approve per firm, with the discount limit's rules (largest among a person's roles, none for a platform administrator, nobody limited until set); above it the order stays submitted and the refusal names the amount needed, the APPROVED event records both figures, bulk approval judges each row; Settings > Buying > Approval Limits (OWNER_DECISIONS A30). Row 10 built 2026-10-01: the supplier's own credit note is recorded on the debit note (§65 row 6) -- `supplier_credit_note_number` / `_date` (both or neither, not before the supplier's bill, once per supplier among live notes) and the reason *Discount after billing*; the debit note's posting, the bill's derived outstanding, the supplier statement (which now names the supplier's note) and GSTR-3B 4(B)(2) cover it, and cancelling reverses all of it; the list searches the number and `GET /debit-notes?supplier_credit_note=` filters on it; the phase 2 editor has the two fields (OWNER_DECISIONS A31).

**Row 8 built 2026-10-01 (reverse charge).** Verified first: the tax engine had a *Reverse charge* rule action that zeroed what the supplier is billed, but the bill threw the tax away -- no liability, no credit, no self-invoice, and 3B counted the components in 4(A)(5) as though the supplier had charged them. Now a bill line whose tax resolves as reverse charge marks its components (`purchase_invoice_line_taxes.reverse_charge`) and sums them in `purchase_invoices.reverse_charge_tax_total`, outside `tax_total` and the payable. Approval issues a **self-invoice number** from its own series (`RCM_SELF_INVOICE`, prefix SI; kept on cancel), credits `RCM_PAYABLE_IGST / _CGST / _SGST` (2260-2280; cess to 2250) and debits the input-tax heads; cancelling mirrors all of it. GSTR-3B reports 3.1(d) (`inward_reverse_charge`) and 4(A)(3) (`itc_reverse_charge`), net ITC includes it, and 4(A)(5) no longer does. The §63 GST payment pays it **in cash only** (`gst_payments.reverse_charge_*`, migration `20261001_0202`), never by credit. Which supplies are reverse charge is a tax rule's decision (`docs/OWNER_DECISIONS.md` A29). **2026-10-02:** a purchase return or a debit note off a reverse-charge bill takes its share of the liability and the credit off -- the share its value is of the bill line's -- in the journal and in 3B's 3.1(d) and 4(A)(3) for its own period, and cancelling it puts them back (`docs/LEDGER_POSTING_RULES.md`).

Owner, 2026-09-28: purchasing is well built; compare it anyway with a full ERP
purchase module (the same shape as the sales checklist in §67): suppliers,
requisition, RFQ, order, receipt, inspection, bill and matching, payment,
return, debit note, pricing, tax, payables, reports. Checked against the code
the same day. §65 already holds fourteen purchase gaps; these are the ones it
does not.

**Built** (no action): supplier master with categories and types, several
addresses and contacts, bank accounts (with UPI), GSTIN / PAN / TAN / FSSAI /
drug licence / IEC; orders with approval, part receipts, over-receipt refusal;
receipts with accepted / free / rejected / damaged quantities, batches and
expiry; bills from receipts with due date, part billing, input credit split by
head; payments with advances, supplier credits from returns, reversal;
purchase returns off the receipt or the bill; vendor outstanding and overdue
bills; automatic posting (stock, GRNI, payable, price variance).

**To consider** -- each to validate with the go-live firms (§55):

| # | Item | Today | The ask |
| --- | --- | --- | --- |
| 1 | **Supplier payment terms** | No payment terms on the supplier; the bill's due date is typed | `vendors.payment_terms_days`; the bill's due date defaults from it, as customers already do |
| 2 | **MSME suppliers: pay within 45 days** (Income Tax s.43B(h)) | No MSME / Udyam field | Udyam number and category on the supplier; bills to an MSME supplier due in at most 45 days (15 without an agreement); a list of MSME bills near or past the limit, since an unpaid one is disallowed as an expense at year end |
| 3 | **Purchase requisition (indent)** | Nothing before the order | A request from a storeman or branch (items, quantity, needed by), approved, then converted into one or more orders -- the reorder suggestion (§42.9) can raise it |
| 4 | **Approval limits by amount** | Anyone with the permission approves any order | Each role approves orders up to an amount; above it the order waits for a higher role. Shares its rules with §64 row 3 (discount limits) |
| 5 | **Changing an approved order** | To verify: what an edit to an approved order does | A formal **amendment**: revision number, what changed, re-approval above a threshold, and the supplier's copy reprinted as "Amendment 1" |
| 6 | **Quality inspection before stock is usable** | Rejected / damaged quantities typed at the receipt | Optional per product or category (pharma, food): received stock lands **on hold** until an inspection passes or rejects it, using the quarantine inventory already has |
| 7 | **Matching the bill to order and receipt, with tolerances** -- **built 2026-10-03** (BUY-10, A99): rate and total tolerances hold the bill | Quantity is capped; a price difference posts silently to price variance | A firm tolerance (for example 2% or 100) beyond which a bill's price or quantity difference **holds** the bill for approval, naming the lines |
| 8 | **Reverse charge on purchases** (GTA freight, legal fees, supplies from unregistered persons where notified) | To verify: the tax engine knows reverse charge; nothing found posting the liability on a bill or reporting 3B 3.1(d) | On such a bill: post output tax payable **and** the input credit, raise the self-invoice number, and report it in 3B; paid in cash (§63) |
| 9 | **Payment run** | One payment at a time | Pick the bills due by a date across suppliers, approve the run, record every payment at once, and export the bank's bulk-payment file using the supplier bank accounts already stored |
| 10 | **Supplier's own credit note** (rate difference, discount after billing) with no goods returned | Purchase return only; our debit note is §55 G8 | Record the supplier's credit note against a bill: reduces the payable and the input credit, reported in 3B |
| 11 | **Supplier performance** | Nothing | On time %, short and rejected %, price trend per supplier (with §66's rate trend) |
| 12 | **Rate contracts / blanket orders** | Nothing | An agreed rate and total quantity for a period, drawn down by orders -- low for a distributor |
| 13 | **Imports** | Nothing | Bill of entry, IGST paid at customs as input credit, customs duty into landed cost (§42.12) -- only for importers |

**Suggested order:** 1, 2 (small, and 2 is a legal deadline) -> 8 (verify
first; tax) -> 7 -> 10 -> 4 -> 9 -> 3, 5, 6 -> the rest.

## 69. The full procurement specification: what it adds to §61, §65, §66, §68

**Status, 2026-10-02:** row 4 (BLOCKED supplier with a reason: no new orders or bills, existing ones still received, paid and returned) and row 6 (a purchase order marked sent, with when and how; "approved but never sent" is a list filter) built. Row 5 built 2026-10-02: every order line carries its quantity picture -- received, accepted, rejected, damaged, returned (traced through a receipt or a bill), invoiced (approved bills), pending receipt and to invoice -- derived per read for a page in a fixed number of statements (`app/purchase/services/line_quantities.py`), and the order a `billing_status` (NOT / PARTIALLY / INVOICED) and `is_complete` beside its lifecycle status rather than as new statuses (OWNER_DECISIONS A33); shown on the phase 2 purchase order. Row 7 built 2026-10-02: a purchase return records its **outcome** -- credit, replacement or refund (OWNER_DECISIONS A34). A supplier refund is received against the return's credit (`/payments/supplier-credits/{return_id}/refunds`, posting Dr cash or bank / Cr payables, reversible); a replacement reopens the order line for what went back, so the next receipt against the order takes it in.

Owner, 2026-09-28, supplied a 53-section "complete Purchase module"
specification (requisition -> RFQ -> supplier quotations -> comparison -> PO ->
GRN -> inspection -> invoice -> payment, plus returns, notes, pricing,
planning, budgets, contracts, landed cost, reports, RBAC, audit, testing) --
**for review, not for building**. Checked against the code and this backlog.

**Already built:** firm isolation at the service layer, RBAC, audit, document
numbering, attachments, pagination, the PO -> GRN -> bill -> payment chain
with partial receipts and billing, over-receipt refusal, accepted / rejected /
damaged / free quantities, batches, expiry, serials, inventory posting through
the inventory service, returns off receipt or bill with reason codes, supplier
credits from returns, advances, allocation, reversal, centralised pricing and
tax, reorder level and safety stock fields in inventory, `purchase_type` on
the order (the spec's "purchase channel"), transport details and the supplier's
invoice reference on the receipt, and the never-lose-typed-data form rule.

**Already recorded:** requisition, approval limits, amendments, inspection,
three-way match with tolerances, reverse charge, payment run, supplier credit
notes, performance, contracts, imports (§68); supplier rates, price variance,
debit notes, RFQ and supplier quotations (§65); free goods and gifts (§61);
purchase analysis, rate trend, dashboard gadgets (§66); landed cost (§42.12);
reorder suggestions (§42.9); notifications (§55 S12); sending the PO by email
(§51).

**What the specification adds** -- each to validate (§55):

| # | Item | Today | The ask |
| --- | --- | --- | --- |
| 1 | **Supplier product catalogue** | A supplier code is typed per order line (`vendor_product_code`); nothing per supplier per product | Per supplier and product: supplier's name and SKU, price with effective dates (history kept, never overwritten), MOQ, order multiple, pack size, minimum order value, lead time, and a **preferred supplier** per product. The order line fills from it. **The preferred supplier is built** (decision A18, 2026-10-02: `products.preferred_vendor_id`, used by reorder); the rest of the catalogue is open. |
| 2 | **MOQ and order-multiple checks** | None | Ordering 115 against MOQ 100, multiple 20 **warns** (or refuses, by firm setting) and suggests 120 -- never changes the quantity silently. |
| 3 | **Lead time used and measured** | None | Expected delivery defaults from the supplier-product lead time; actual lead time and delay per receipt feed §68 performance and §42.9 planning. |
| 4 | **Blocked supplier** | Statuses DRAFT / ACTIVE / INACTIVE / ARCHIVED | **BLOCKED** with a reason: no new orders or bills, existing ones can still be received, paid and returned. |
| 5 | **One quantity picture per order line** | Receipt and bill services each derive their own figures | One service answers ordered / received / accepted / rejected / returned / invoiced / pending per PO line, and the order API and screen show it; PO statuses gain **partially invoiced** and **completed** from the same figures. To verify first what the order screen shows today. |
| 6 | **Sent to supplier** | Approval is the last step before receiving | A **Sent** state with date and how (email, print, WhatsApp), so "approved but never sent" is findable. |
| 7 | **What a return comes back as** | A return gives a credit; a refund service exists for customers | The return records the outcome -- **credit**, **replacement** (a receipt against the return, no new order) or **refund** -- and a supplier **refund** is received as money in against the supplier's credit. To verify whether settlements already take a supplier refund. |
| 8 | **Supplier rebates and offers** | Only free quantity on a line | Target and volume rebates ("2% back on the year's purchases over 10 lakh"): the agreement, purchases counted against it, the rebate accrued as a receivable from the supplier, and claimed -- with §42.7 on the sales side. |
| 9 | **Purchase budget** | None (§55 N8 is a general finance budget) | Budget by firm, branch, category and period; used and available shown on the order; warn, or require approval, when exceeded -- never block by default. |
| 10 | **Supplier rating by people** -- **built 2026-10-03** (BUY-15, A74): five 1-5 scores and a remark per person, averages on the supplier screen | None | Price, quality, delivery, support, communication scores given by users, kept **apart** from the computed §68 metrics and labelled as opinion. |
| 11 | **Quotation comparison** | §65 row 14, rated low | If validated, the spec's side-by-side: effective landed cost per unit, delivery days, payment terms, rating; the chosen supplier and the **reason** recorded; never auto-picks the cheapest. |
| 12 | **Planning formula** | §42.9 reorder suggestions | Required = demand over lead time + safety stock - on hand + reserved - open orders, rounded up to MOQ / multiple; the formula's parts configurable; suggestions first, automatic POs only with a permission. |

**Row 12 status, 2026-10-02:** built (A39) -- Settings > Buying > Purchase Settings > *Reorder
planning*: typed levels, or from sales (window, lead time, safety and cover
days); the *Below reorder level* report and its draft orders follow it
(`docs/PURCHASE_FRAMEWORK.md`). MOQ / multiple rounding waits for rows 1-2,
supplier lead time for row 3.

**The spec's phasing, mapped to this product:** its Phase 2 (core) is built;
Phase 3 is §68 rows 3-4 + rows 1, 11 here; Phase 4 is §68 rows 6, 10 + §55 G8
+ row 7 here; Phase 5 is rows 1-3, 9, 12 here + §42.9; Phase 6 is §68 rows
11-13 + §42.12 + row 8 here; Phase 7 is §66.

## 70. Inventory against a full ERP checklist: what else to consider

**Status, 2026-10-02:** row 5 was already built as Reports > *Stock valuation* (as on any date); row 6 built -- Reports > Financial > *Stock statement for the bank* (opening, in, out, closing, each with value).

Owner, 2026-09-28: the same review as sales (§67) and purchases (§68, §69),
for inventory -- **review only, nothing to build yet**. Checked against the
code the same day.

**Built** (no action): warehouses with storage nodes (bins); several units per
product with conversion rules; batches, lots and serials with expiry, forward
and backward trace, an expiry monitor; stock split into current, reserved,
available, blocked, damaged, quarantine; opening stock (with import);
adjustments; write-offs by reason (damage, expiry, loss); quarantine hold and
release; transfers between warehouses and across branches that keep the batch
and the value; physical counts with posting; reservations from sales orders;
batches allocated automatically at dispatch, expired ones refused on the
note's own date; a stock ledger recording before and after for every
quantity; weighted-average costing with every movement posted to the ledger;
minimum, maximum, reorder level and safety stock per item; summaries by firm,
branch, warehouse and product; export.

**Already recorded:** system-numbered movements (§34); reorder suggestions
(§42.9); landed cost (§42.12); kits and combo packs (§42.13); stock ageing,
slow and dead stock (§55 S7); barcode counter billing and labels (§55 M10,
S8); batch-wise MRP / PTR / PTS (§55 G5); picking list and loading sheet (§55
G7); returnable containers (§55 G12); free-issue products and "given free" /
"sample" issues (§61); inspection hold on receipt (§68 row 6).

**To consider** -- each to validate with the go-live firms (§55):

| # | Item | Today | The ask |
| --- | --- | --- | --- |
| 1 | **A stock transfer as a document** | One product per transfer, applied at once; `in_transit_quantity` exists but a transfer never uses it | A numbered, multi-line **Stock Transfer** with a printed transfer challan; two steps -- **dispatch** (stock goes in transit) and **receive** at the other end, recording any shortage or damage in transit |
| 2 | **Branches with their own GSTIN** | A branch has a "GST registered" flag but no GSTIN; every document uses the firm's | A GSTIN per branch (a firm registered in two states has two); documents print the branch's GSTIN; a transfer **between two GSTINs** is a taxable supply -- raised as a tax invoice with e-way bill, credited as input tax at the receiving branch -- while one within a GSTIN goes on a delivery challan |
| 3 | **Issue for internal use** | Stock leaves only by sale, transfer, write-off (damage, expiry, loss), return | **Built 2026-10-03 (STK-3, A61).** Reasons **Internal use / consumption**, **Staff**, **Display / demo**, each with its expense account (sits beside §61's given-free and sample) |
| 4 | **Repacking and bulk breaking** | Nothing | Convert one product into another -- a 25 kg bag into 25 x 1 kg packs, loose into packed, cartons into pieces as separate items -- with the cost carried across and any wastage recorded |
| 5 | **Stock value on any date** | The summary shows value now | Closing stock quantity and value **as of a date**, by warehouse and category, from the ledger's `average_cost_after` -- what the accountant needs at 31 March and for bank stock statements |
| 6 | **Monthly stock statement for the bank** | Nothing | Opening, receipts, issues, closing, value -- the drawing-power statement banks ask of distributors with a cash credit limit |
| 7 | **Expiry rules per product** | Near-expiry is fixed at 30 days in the expiry monitor | Per product or category: days before expiry to stop selling (sell-by), to alert, and to return to the supplier; near-expiry stock offered last or flagged on the order |
| 8 | **Count planning** | A physical count is started by hand | **Cycle counts** by ABC class or bin on a schedule; blind count (quantity hidden from the counter); variance above a limit needs approval before posting |
| 9 | **Costing method choice** | Weighted average only (the model already allows FIFO later) | FIFO as a firm setting, if a go-live firm's accountant requires it; most Indian distributors use weighted average, so validate before building |
| 10 | **Negative stock policy** | Every movement refuses to go below zero | Keep refusing by default; a firm setting to **warn** instead for counter billing where stock is entered late -- validate before building |

**Added the same day from a 60-section "complete inventory module" prompt**
(review only). Confirmed built besides the above: earliest-expiry-first batch
allocation that skips expired batches (`allocate_for_dispatch`); serial
statuses AVAILABLE / RESERVED / SOLD / INSTALLED / RETURNED / REPAIRED /
SCRAPPED / LOST; reversal by a compensating movement rather than an edit;
return restock versus damaged / scrap quantities. What it adds:

| # | Item | Today | The ask |
| --- | --- | --- | --- |
| 11 | **Adjustment reasons as a list the firm keeps** | Write-off reasons are fixed (damage, expiry, loss) and an adjustment takes free text | A reason master (count variance, found, theft, data correction, internal use, sample, other...) that administrators extend, each mapped to an account; every adjustment and write-off names one |
| 12 | **Approval for large adjustments and write-offs** | Anyone with the permission posts any size | Above a quantity or value limit per role the movement waits for approval -- the same approval rules as §64 row 3 and §68 row 4, not a third mechanism |
| 13 | **Evidence on adjustments** | Movements carry no attachments | **Built 2026-10-03 (STK-9, A64).** Photos and documents on adjustments, write-offs, counts and transfers, through the existing attachment storage |
| 14 | **Incoming and outgoing on the availability figure** | Physical, reserved, available, blocked, damaged, quarantine, in transit | **Built 2026-10-03 (STK-10, A60).** **Incoming** (open purchase orders not yet received) and **outgoing** (open orders not yet reserved) beside available, on the stock screen and the order line, so a salesman can promise a date |
| 15 | **Issue rule per product** | Earliest expiry first for every batch-tracked product | **Built 2026-10-03 (STK-11, A63), per product.** A setting per product or category: FEFO (today), FIFO by receipt, or **the person picks the batch** -- and when picking is required the note refuses to allocate silently |
| 16 | **Reservations that lapse** | A reservation lasts until the order ships, is cancelled or closed | Optional expiry per firm (for example 7 days): a reservation not dispatched in time is released and the order flagged, so stock is not held for dead orders |
| 17 | **Returned goods held until checked** | The return decides restock versus damaged at entry | **Built 2026-10-03 (STK-13, A62).** Optional: returned stock lands in **quarantine** and is released to available only after a check -- the same hold as §68 row 6 for receipts |
| 18 | **Stock alerts and the inventory dashboard** | Expiry monitor; §42.9 reorder; §55 S12 notifications | Configurable alerts (low, out, over maximum, negative, near expiry, expired, transfer awaiting receipt, count pending) and Home gadgets: stock value by warehouse and category, low and out of stock, near expiry, fast and slow movers, pending transfers and counts -- with §55 S7 ageing and an **inventory turnover** figure per product |

**Suggested order:** 5, 6 (small; accountant and bank) -> 3 -> 1 -> 2 (needed
before any firm with branches in two states) -> 7 -> 4 -> 8 -> 9, 10;
then 11 -> 13 -> 12 -> 14 -> 18 -> 15 -> 16, 17.

## 71. Sign-in screen for phase 2, with the agency's own logo and name

Owner, 2026-09-28: a wireframe for the sign-in screen, and **the logo and
agency name must be configurable** -- keep it in the backlog. The wireframe is
view 8 of `dist\windows\Design\UI phase 2 wireframes.html`, in **three
layouts** (A, B, C) that follow Home's frame and colours; switch "not yet set"
/ "configured" to see both branding states. **Layout: owner to choose.**

**Today:** the phase 1 sign-in screen reads `config\branding.json` beside the
executable -- `app_name`, `company_name`, `logo_path`, two colours. That file
is per PC and edited by hand, so ten PCs mean ten edits, Setup overwrites it
on every upgrade, and nobody can change it from inside the app. The logo path
must point at a file that exists on that PC.

**The ask:**

| # | Item | Detail |
| --- | --- | --- |
| 1 | **Branding held by the server** | Agency name, tagline, logo (PNG/JPG, stored by the backend, size-capped) and accent colour, in one platform-level record -- one agency per installation, above the firms, because sign-in happens before a firm is chosen |
| 2 | **Read before sign-in** | A public, unauthenticated `GET` for the branding and the logo image (nothing secret in it), cached on the PC so the screen still shows the logo when the server is down, with the "server does not answer" strip beside it |
| 3 | **Edited in the app** | **Settings > Platform > Branding**, platform administrators only: upload/replace/remove the logo with a preview, name, tagline, accent colour; audited like any other platform change |
| 4 | **Used everywhere the name shows** | Sign-in panel, the menu bar's logo spot, the window title, About, and the footer's copyright; the product name stays as "Powered by Agency Platform" |
| 5 | **`branding.json` becomes the fallback** | Kept for the server address and the version; its name/logo apply only until the server's record is set, so an install that set them by hand keeps them |
| 6 | **Phase 2 sign-in screen** | In the layout the owner picks (**A** brand panel left, form right; **B** Home's frame -- the dark bar carries logo and name and becomes the menu bar after sign-in -- with one card in the middle; **C** as B plus tiles of the people who signed in on this PC, so a counter clerk types only a password). In each: username or email, password with show/hide, remember username, keep me signed in, Sign in on Enter, Forgot password), server status and version at the foot, Application Settings behind the gear; below 820 px the brand panel folds into a small logo above the form; a wrong password is one line that does not say which half was wrong |

Per-firm logos on printed documents are a separate thing (the firm's own
letterhead) and are not changed by this.

**After sign-in, when it is given, and our own name (owner, same day).** The
owner asked that the logo and name carry into the main app, that we decide
when they are provided, and that the maker's name be visible somewhere, as
market tools do. Wireframe: view 9 "Logo and names" (tabs: installer,
first-run setup, main app, Settings > Branding, Help > About).

How the market does it (checked 2026-09-28): **Odoo** takes the login page
logo from the company record (Settings > Companies), editable any time, with
"Powered by Odoo" under the form; **Zoho Books** uploads the organisation logo
under Settings > Organization Profile, used in the app and on PDFs and emails;
**Business Central** always shows the company name top left (click = Role
Centre), a company badge top right, and the logo from Company Information on
printed documents; **TallyPrime** asks the company name when the company is
created -- not at install -- and prints a logo only if configured. None asks
for the customer's name in the installer, and every one keeps its own name on
the product (title, About, login footer) while leaving it off the customer's
documents.

**Decided by that convention** -- three names, three owners:

| Name | Who sets it, when | Where it shows |
| --- | --- | --- |
| **The agency** (the customer) | Its first administrator, in a **first-run setup** after the first sign-in (step 1 of: agency, first firm, users, done; name required, logo and tagline optional, skippable with a "Finish setting up" card on Home); changed any time in Settings > Platform > Branding | Sign-in; **left of the menu bar on every screen** (logo + name, click = Home, name hides below 820 px); window and taskbar title "Firm - Agency"; About's "Licensed to" |
| **The firm** | As today, when the firm is created | Firm switcher, Home greeting, the firm's letterhead on printed documents -- unchanged |
| **Our company** (the maker) | Fixed at build time (`AppPublisher` in `packaging/AgencyPlatform.iss`, `CompanyName` in `Runner.rc`, the product constants); **never editable by a customer** | Installer and Windows Apps list as publisher; exe properties; sign-in footer "Powered by Agency Platform"; the status line's right end "Agency Platform 1.0.2 - <maker>"; Help > About (version, build, maker, support email, phone, website, copyright, "Copy details for support"). **Not** on the customer's printed invoices |

**The installer asks nothing about branding** -- a name typed there would sit
on one PC, and the server record is what every PC reads.

**Owner owes:** the company's legal name, support email, phone and website
(the wireframe shows "Your Company Pvt Ltd"), and the product `.ico` (§47).

## 72. Configuration apart from the daily menu, shown by permission

Owner, 2026-09-29: separate configuration from the menu items people use
every day -- configuration is rarely used, and mostly by administrators --
with wireframes, and **only shown to those whose permissions allow it**.
Wireframe: view 10 "Menu and Setup" of `dist\windows\Design\UI phase 2
wireframes.html` (switch Option A / B and the role: administrator, sales
manager, accountant, billing clerk); screenshots in `dist\windows\Design\Menu
and Setup screenshots\`.

**Today** (`desktop/lib/phase2/menu_layout.dart`): configuration groups sit
inside the daily drop-downs, drawn apart under a CONFIGURATION heading
(Sell: Pricing, Territories & routes; Accounts: Structure; Masters: the lookup
lists, units, packing, locations). Admin is an area on the bar. The gear
opens Settings (Firm, Buying, Stock, Tax, Business profile). Every item is
already offered only when `ModuleVisibility` allows it.

**How the market does it** (checked 2026-09-29): **Odoo** ends each app's
menu with a Configuration menu, and its Settings menu can be limited to
managers by group; **Zoho Books** puts every setting behind the gear on one
Settings page (organisation, users and roles, taxes, preferences,
customisation...); **Business Central** lists setup pages by area on one
Manual Setup page, with an administrator role centre.

**Two options:**

| | Option | What changes |
| --- | --- | --- |
| A | **Configure row per area** (Odoo) | Each drop-down lists daily work; a Configure row at its foot holds that area's setup screens, drawn only for roles that may open them; Admin stays on the bar |
| B | **Setup behind the gear** (Zoho, Business Central) -- *recommended* | Drop-downs hold only daily work; **Admin leaves the bar** (seven areas: Home, Sell, Buy, Stock, Accounts, Masters, Reports); the gear opens **Setup**: one page, topics on the left, cards on the right, a search across every topic the person may open |

**Split proposed** (every screen of today's menu placed; none dropped):

- **Daily menu:** Sell (the seven documents; Receipts, Refunds, Customer
  Statements; Commission, Targets; Beat Plans, Call Lists, Coverage); Buy
  (four documents, Payments, Purchase Dashboard); Stock (all of it); Accounts
  (Journal Entries, Ledgers, the three statements, GST Returns, E-Invoice,
  TCS); Masters (Customers, Vendors, Products); Reports.
- **Setup:** *For everyone* -- This PC and me (appearance, server address,
  landing page, password). *The firm* -- Firm (Firm Settings, Financial
  Years, Numbering Series, Branches, Warehouses, Storage Areas, Branch and
  Warehouse Types); Selling (Price Lists, Promotions, Loyalty, Customer
  Groups, Territories, Route Types, Route Builder); Buying (Purchase
  Settings, Vendor Categories, Vendor Types); Items and stock (Product
  Categories, Units, UOM Groups, Packaging Types and Levels, Conversion
  Rules, Inventory Settings); Accounts and tax (Chart of Accounts, Control
  Accounts, Cost and Profit Centres, Tax Configuration, Tax Rules, Rule
  Simulator, Execution Log, Tax Settings); Places. *Administration* -- People
  and access (Users, Roles, Permissions, User Templates, User-Firm
  Assignments); Business profile (six screens); Firms and system (Platform
  Dashboard, Firms, Business Profiles, Branding §71, Audit Logs, Diagnostics,
  Licensing).

**Permissions (both options):** a screen is drawn only if `ModuleVisibility`
lets the person open it -- the same rule as today, and the server still
refuses the request whatever the menu shows; a topic with nothing left
disappears; the gear always shows *This PC and me*, so a billing clerk sees
only that; an area with no daily item left leaves the bar; Ctrl+K finds any
setup screen the person may open. `menu_layout_test.dart` keeps guarding
that every catalogue screen has exactly one place.

**Owner to decide:** A or B; whether Chart of Accounts (looked up often by
accountants) stays under Accounts in the daily menu as well as Setup's
list; whether Price Lists and Promotions (changed weekly by some sales
managers) stay in Sell.

## 73. One standard for dialogs, and the review of every dialog against it

Owner, 2026-09-29: review, for the new UI, every form that opens on a click,
like Change password; and a user sets his own preferences -- theme, and the
firm he starts in when he has several.

**The standard** (drawn in view 11 "Dialogs" of `dist\windows\Design\UI
phase 2 wireframes.html`; screenshots in `dist\windows\Design\Dialogs
screenshots\`): documents and master records open as full-page tabs (4.8); a
**dialog** is a short task (a few fields, one decision); a **confirm** is a
yes/no. Every dialog: a title that names the action; the main button named
by its verb, on the right, Cancel beside it, a destructive one in red naming
what it destroys; first box focused, **Enter** does the main action, **Esc**
cancels; mistakes under the box, a server refusal inside the dialog, which
**stays open and keeps what was typed**; the button shows it is saving and
cannot be pressed twice; widths small 420 / medium 580 / large 820, the body
scrolls, the buttons never do; closing with unsaved edits asks first. This is
Windows' and Business Central's convention, and what `CrudWorkspaceDialog`,
`askForReason` and `AppDialogs.confirm` already do.

**The review** (`docs/UI_PHASE_2_DIALOG_REVIEW.md`): about 150 dialogs read
in code; about 69 with a finding; defects `D-DLG-1`..`D-DLG-10` in
`docs/DEFECTS.md`. Fix order, one PR each, each with a test that fails when
reverted:

1. **Keep the save inside the dialog** (D-DLG-1, D-DLG-4): the dialog calls
   the server, stays open while it runs and closes only on success --
   copying `CrudWorkspaceDialog`. The largest item; do it by area.
2. **Confirm every delete** (D-DLG-2) and **make `AppDialogs.confirm` the one
   confirm**, replacing about 100 hand-built yes/no dialogs as each file is
   touched.
3. **Small, one-line fixes:** D-DLG-5, D-DLG-6, D-DLG-7, D-DLG-10.
4. **One `PasswordField`** with show/hide, used by all seven (D-DLG-9).
5. **Unsaved-changes guard** in `WorkspaceDialog` (opt-in), and phase 2's
   document guard noticing drop-downs, switches and dates (D-DLG-8).
6. **Enter submits** a short `WorkspaceDialog` task, as Ctrl+S does today.
7. **Rebuild the five tax masters' dialog** as proper forms (D-DLG-4, after 1).
8. Product import staged and committed once, reporting the failed row
   (D-DLG-3), as the backend's other imports are.

**My preferences in one place.** Already built: each user's theme is saved
on the server; the firm opened at sign-in is the **primary firm**, set from
the user menu (offered only to somebody with more than one firm, listing only
the firms they are a member of, the server refusing any other); failing that
the last firm, then the first; a platform administrator starts in none. What
is missing is one place: a **My preferences** dialog (view 11) -- start-in
firm, first screen, theme, text size, date format, rows per page -- opened
from the user menu and from Setup's *This PC and me* (§72), with "switching
firm on the bar is for this session; Start in firm is for next time" said on
it.

## 74. Money against a full ERP checklist: what else to consider

**Status, 2026-10-02:** row 2 built -- deductions (rounding, bank charges, discount allowed/received) on receipts and payments; a party adjustment document (customer write-off, supplier write-back, set-off) with approval above a per-firm threshold (`app/party_adjustments`). Defaults in `docs/OWNER_DECISIONS.md` A14-A16. Rows 3-4 built: a contra voucher (deposit, withdrawal, bank and cash transfers, own CV series, printable; `app/contra`), a supplier statement of account (Purchases > Money > Supplier Statements) and balance confirmation letters for any customer or supplier, one PDF or a zip for everyone with a balance (`docs/OWNER_DECISIONS.md` A22-A24).

Owner, 2026-09-28: after sales (§67), purchases (§68) and inventory (§70),
review the money side the same way -- books, years, receipts and payments,
party balances, tax filings, statements. Checked against the code the same
day. Most of the usual gaps already have an entry, so this section first maps
the checklist to them and then lists only what nothing else covers.

**Built** (no action): chart of accounts with groups, 24 control-account
purposes per firm, cost and profit centres; financial years and monthly
periods that close oldest first and a year lock that is final; hand journals
with draft, edit, reject, post and reverse, refused on the accounts a
sub-ledger keeps (D-FIN-11); automatic posting from eleven modules; trial
balance (opening, movement, closing), general ledger per account, P&L for a
period with the year to date, balance sheet; receipts, payments and refunds
by cash or bank with allocation to bills, advances, supplier credits and
reversal (never edit); customer statement and ageing; customer credit notes
that reverse tax (`app/credit_note`); opening stock and customer opening
balances posted against opening balance equity; TCS 206C(1H) with its
settings, collections and charged-versus-due; GSTR-1 and GSTR-3B (outward
and input credit) derived from the documents; e-invoice and e-way bill in
sandbox; an append-only audit trail in every store.

**Already planned elsewhere:**

| Checklist item | Where |
| --- | --- |
| Expenses (bills without stock: rent, power, travel) | PR #814, draft |
| Bank reconciliation, statement import | §42.2 |
| Post-dated cheques, clearing and bounce | §42.3 |
| TDS payable (194Q, 194C, 194J) and TDS deducted by customers | §42.4, §53, §53.1 |
| GSTR-2B matching | §42.5 |
| GST set-off and payment, output tax by head, TCS deposit, 27EQ | §63 |
| Reverse charge on purchases | §68 row 8 |
| MSME 45-day payments; payment run | §68 rows 2, 9 |
| Supplier debit note; supplier's credit note | §55 G8; §68 row 10 |
| Day book, cash book, bank book | §55 M9 |
| P&L for any months | §50 |
| Cash discount for early payment; interest on overdue | §55 G9 |
| Vendor ageing | §55 S7 |
| Cheque printing | §55 S11 |
| GSTR-9, composition | §55 G11 |
| Export to Tally | §55 G4 |
| Multi-currency, budgets, recurring entries, payroll | §55 N2, N8, N7, N1 |
| Live e-invoice through a GSP | §55 M2 |
| Branch GSTINs; stock value as of a date | §70 |
| Opening balances from a previous tool | §36, §56 |
| Screens scoped to a financial year | §37 |

**To consider** -- each to validate with the go-live firms (§55):

| # | Item | Today | The ask |
| --- | --- | --- | --- |
| 1 | **The new year's opening** (D-FIN-22) | No closing entry is ever posted. The balance sheet computes earnings from every income and expense account since the start, so it balances, but the trial balance of a second year opens Sales, Purchases and every expense at last year's closing (`JournalEngine._opening_balance` carries every account alike) | In the first period of a year, income and expense accounts open at zero and one line, **Profit and loss brought forward**, carries last year's net. Keep it derived, with no posted closing entry, as the balance sheet already is. The balance sheet splits equity into **surplus brought forward** and **profit for the year** (Schedule III, Reserves and Surplus) |
| 2 | **Adjusting a party's balance without tax** | Only documents move a customer's or supplier's balance; hand journals are refused on receivables and payables (rightly). A receipt 3.00 short, a bank charge the customer's bank took, a bad debt: none can be cleared, so the bill stays unpaid forever. The only credit note either reverses tax (`/credit-notes`) or is the old route in D-FIN-23 | (a) On a receipt or payment: **deductions** -- rounding / short paid, bank charges, discount allowed or received -- each to its own account, closing the bill. (b) A **party adjustment** document: write-off or bad debt against a customer, balance written back for a supplier, with a reason, approval above an amount, and its journal. (c) **Set-off** between a customer and a supplier who are the same business (Dr payable / Cr receivable, both balances moved) |
| 3 | **Contra: cash to bank and back** | Possible as a hand journal (cash and bank are open to them), with no document or number of its own | A **contra** voucher: deposit, withdrawal, bank-to-bank transfer, with its own series and print. Warn when cash in hand would go below zero on the day, which the ledger today shows without comment |
| 4 | **Supplier statement and balance confirmation** | Customer statement and ageing exist; nothing for suppliers | A supplier statement of account (as the customer's) and, at year end, a **balance confirmation** letter for any party -- "our books show you owe / we owe X as of 31 March, please confirm" -- which auditors ask for |
| 5 | **Cash flow statement** -- **built 2026-10-03** (ACC-9, A87): indirect method, reconciled to cash and bank | Trial balance, P&L, balance sheet only | Cash flow for a period by the indirect method (profit, change in receivables, payables, stock, then investing and financing), derived from the same balances. Banks ask for it with a loan application |
| 6 | **Fixed assets and depreciation** | Nothing; an asset is a ledger account at cost | An asset register (item, date put to use, cost, block), depreciation by written-down value at the income-tax block rates, and the half rate for assets used under 180 days in the year, posted once a year. Low for a trading firm, since the CA often does it; validate before building |
| 7 | **A document behind every hand journal** -- **built 2026-10-03** (ACC-10, A88): files on journals, receipts and payments | Journals carry a narration only | Attach the scanned bill or letter to a journal, receipt or payment, as auditors expect. Share the store with Expenses (#814) if it has one |

**Suggested order:** 1 (the books a CA reads first; small) -> 2 (every firm
has short receipts in the first week) -> 3, 4 (small) -> 7 -> 5 -> 6.

### 74.1 What the finance master prompt adds (rows 8-16)

Owner, 2026-09-28: a full "Money / Finance & Tax module" master prompt (81
sections) reviewed against the code the same day. Most of it is built or
already has an entry, as the table below shows. Nine points are new.

**Already built** (the prompt asks, the code has it): double entry enforced on
post; posted journals immutable, corrected by reversal; maker and checker
(`JOURNAL_CREATE` / `JOURNAL_POST`); every automatic journal names its source
document; firm isolation in the query layer (per-store sessions, `X-Firm-ID`
membership); years and periods with close, lock and a separate
`FINANCIAL_YEAR_REOPEN`; several cash and bank accounts (a receipt names its
ledger account); receipts and payments with part allocation, advances,
unallocated balance and reversal, never allocated silently; control accounts
for rounding, discount allowed and received; decimal money throughout
(`quantize_ledger`); tax rules versioned and matched by date; a tax
execution log per evaluation; e-invoice behind a portal interface, refusal
kept for retry, cancellation refused after 24 hours; e-way bill fields;
`currency_code` on the documents; audit rows on every mutation.

**Already planned:** bank reconciliation §42.2; cheques §42.3; TDS rules,
payable, receivable, returns and certificates §42.4 / §53 / §53.1; GSTR-2B
§42.5; GST payable, set-off, challan, TCS deposit and 27EQ §63; approval by
amount §68 row 4 and §55 S12; expenses #814; supplier debit note §55 G8;
customer debit note §67; supplier opening balances §36; day, cash and bank
book §55 M9; cash flow, supplier statement §74 rows 5, 4; finance dashboard
§49; live IRP through a GSP, with duplicate-IRN handling, §55 M2;
multi-currency §55 N2.

| # | Item | Today | The ask |
| --- | --- | --- | --- |
| 8 | **HSN kept on the invoice line** (D-CMP-22) | Lines keep the tax components and rates, but not the HSN/SAC: GSTR-1's HSN table, the e-invoice payload and a reprint read the product's **current** code | Copy `hsn_sac` onto every sales, purchase, return and credit note line when it is written (backfill existing lines from the product, once); the returns, payload and print read the line |
| 9 | **GST checks before filing** | GSTR-1 folds a line with no HSN under a blank code; nothing lists what is wrong | An exception list per return period: B2B bill whose GSTIN fails the checksum or state code, missing HSN, HSN shorter than the firm's turnover requires (4 / 6 digits), missing place of supply, e-invoice required but not registered, credit note with no original invoice. Each row opens the document -- **built 2026-10-03** (GST-5, A82) |
| 10 | **Recording a filed return** | Returns are derived on every read, and nothing records that one was filed | A return register per GSTIN, return type and period: prepared, filed (typed by the person who filed on the portal: date, ARN), by whom. After filing, the period's figures are **kept as filed**, and a later change to a document in that period is shown as an amendment for the next return rather than silently changing the filed one. Never marked FILED by the app itself (the sandbox rule stands) |
| 11 | **Quarterly filers (QRMP)** -- **built 2026-10-03** (GST-7, A83): filing frequency in the GST settings, quarterly GSTR-1 with the IFF, PMT-06 deposits, quarterly 3B due the 22nd / 24th | Due dates and periods assume monthly | Filing frequency on the firm's GST registration; GSTR-1 by quarter (with the optional IFF in months 1-2), 3B quarterly, due dates 22nd / 24th by state; §63's payment by PMT-06 in months 1-2 |
| 12 | **How the money moved** | `method` is CASH or BANK; the instrument is free text | A mode on receipts and payments -- UPI, cheque, NEFT / RTGS / IMPS, card, cash -- with instrument number and date, so the cash and bank books (M9) and bank matching (§42.2) can use it; cheque status stays §42.3 -- **built 2026-10-02** (ACC-3, A49) |
| 13 | **The firm's bank accounts, and masking** | A bank is only a ledger account; supplier and customer bank numbers come back in full from the API | Bank name, account number, IFSC, branch on the firm's bank ledger accounts, printed on invoices ("pay to"); **show only the last four digits** of any account number except to a role that pays (the payment run in §68 row 9 needs the full one) -- **built 2026-10-03** (ACC-4, A81) |
| 14 | **Checks before closing a month** | A period closes if the one before is closed; nothing else is asked | Before close, list and warn (or refuse, by firm setting): draft journals and documents dated in the month, approved documents with no journal, receipts left unallocated, unreconciled bank lines (after §42.2), GST return not recorded as filed (row 10) -- **built 2026-10-02** (ACC-5, A50; bank lines wait for §42.2) |
| 15 | **Why tax was charged, kept on the document** -- **built 2026-10-03** (GST-8, A85): rule code and version on every taxed line | The line keeps component and rate; the rule that chose them is only in `tax_rule_execution_logs`, which retention may purge | Store the rule code and version on each line tax row, so the reason survives the log's retention and a reprint years later can say which rule applied |
| 16 | **Ageing buckets and due lists** | Buckets fixed at 0-30-60-90-90+; overdue lists exist | Buckets set per firm; "due today" and "due this week" for receivables and payables, and a collection summary by salesman and route (with §62) -- **built 2026-10-03** (ACC-6, A51: bands per firm, due today / this week; the collection summary stays with §62) |

**Suggested order, whole section:** 8 (small; a filed return must not
change) -> 1 -> 2 -> 9 -> 12 -> 13 -> 3, 4 -> 10, 11 -> 14 -> 15, 16 -> 7 ->
5 -> 6.

## 75. Masters and configuration against a full ERP checklist

**Status, 2026-10-02:** row 3 decided and built (A7/B5): a GSTIN or PAN may repeat across customers, warned by name before and after the save; the code stays unique (migration 0219). Row 2 built -- a customer's GST registration type (Regular, Composition, Unregistered, SEZ with/without payment, Deemed export, Overseas), stamped on each bill: SEZ is IGST wherever it is, GSTR-1 marks SEWP/SEWOP/DE and files exports in EXP, 3B reports zero-rated supplies in 3.1(b), the e-invoice supply type follows.

Owner, 2026-09-28: after Money (§74), review the masters -- customers,
suppliers, products, branches and warehouses -- and the configuration they
lean on: price lists, units, tax, business profiles, numbering. Checked against
the code the same day.

**Built** (no action): customers with groups, type, credit limit and terms,
standing discount, ON_HOLD, several addresses and contacts on the geography
masters, credit-control policy; suppliers with categories and types, contacts,
addresses, bank accounts with UPI, tax details (GSTIN, PAN, TAN, FSSAI, drug
licence, IEC), attachments and notes; products with a category tree, barcode
and QR, HSN/SAC, tax profile group, seven unit roles and packaging levels,
dimensions, batch / serial / expiry / warranty flags, media, MRP; branches and
warehouses with storage bins; price lists by customer or territory with
quantity breaks and dates; promotions; units and conversions; tax rules;
business profiles and features; custom fields on every master; document
numbering with prefix, financial year, branch code, reset and a manual switch;
unique codes among live rows (D-MST-11); import from files (§46).

**Already planned:** price levels and fixed rates §64 row 1; supplier rates
§65 row 4; PAN / TAN / GSTIN format checks §53; licences §54; supplier payment
terms and MSME §68 rows 1-2; supplier catalogue, MOQ, blocked supplier §69;
branch GSTINs §70; batch-wise MRP §55 G5; ship-to per order §67; supplier
opening balances §36; firm bank details §74.1 row 13; HSN kept on the line
§74.1 row 8; extra fields on documents §52.

**To consider** -- each to validate with the go-live firms (§55):

| # | Item | Today | The ask |
| --- | --- | --- | --- |
| 1 | **Principal and brand** | `products.brand` is free text; nothing ties a product to the company whose agency the firm holds, or that company to its supplier record | A **principal** master (the company: HUL, Nestle) linked to its supplier, and a **brand** master under it; products name a brand. Principal-wise sales, stock and claims (§42.7), targets and reports all key on it |
| 2 | **Customer's GST registration type** | Customers carry only a GSTIN and INDIVIDUAL / BUSINESS; suppliers have `gst_registration`. The e-invoice builder says "SEZ and deemed exports need a marker no customer carries yet" (`einvoice/services/payload.py`) | Regular, Composition, Unregistered, SEZ (with or without payment), Deemed export, Overseas on the customer, driving the GSTR-1 table (B2B, SEZWP / SEZWOP, DE, EXP), the e-invoice supply type, and a warning when an SEZ bill charges tax the LUT says it should not |
| 3 | **One GSTIN or PAN on several customer accounts** | `UQ_customers_firm_gst_number_active` and `..._pan_number_active` refuse a second customer with the same GSTIN or PAN | Decide: outlets of one business, or one proprietor with two shops, are routinely kept as separate accounts on separate routes. Either allow the same GSTIN / PAN with a warning (as Tally does), or model outlets as delivery addresses of one customer (§67). Validate with the go-live firms before changing the keys D-MST-11 made |
| 4 | **Customer and supplier as one party** -- **built 2026-10-03** (ACC-11, A86): linked on the customer, combined statement, set-off preselects | Two unrelated records | Link a customer to a supplier record; one combined statement, and the set-off of §74 row 2 |
| 5 | **Discontinued, and not for sale** | Product status is ACTIVE or INACTIVE only | DISCONTINUED: refused on purchase orders, still sold until stock runs out, then flagged. Not-for-sale (samples, consumables, packing material): stock kept, never on a sales document. **Built 2026-10-03 (STK-17, A58)** |
| 6 | **Shelf life** | Expiry is typed per batch | **Built 2026-10-03 (STK-18, A59).** Shelf life (days) on the product fills expiry from the manufacturing date at receipt; a customer's **minimum remaining life** (modern trade refuses stock under a set share of its life) is warned at order and refused at dispatch |
| 7 | **Price revision with an effective date** | `selling_price` and `purchase_price` are overwritten on edit, with no history and no future date | Schedule "new rates from the 1st" (from a principal's circular, often by file); the old rate holds until then, and the product keeps its rate history. Combines with §64 row 1 price levels |
| 8 | **Duplicate check and merge** | Codes are unique; nothing warns of a second "Sri Balaji Stores" with the same phone; §36 notes there is no merge tool | Warn on create when name, phone or GSTIN resembles a live record; a **merge** that moves documents, balances and route membership to the survivor and records it, refused across a locked year |
| 9 | **Customer attachments and bank account** -- **built 2026-10-03** (MST-4, A68): files and bank accounts on the customer, numbers masked to the last four without CUSTOMER_MANAGE_BANK_DETAILS | Suppliers have both; customers neither | Attachments (licence copies, KYC, agreements) and a bank account (for refunds by NEFT, masked per §74.1 row 13) on the customer |
| 10 | **Codes from a series** -- **built 2026-10-03** (MST-5, A67): blank code takes CUS-/SUP-/PRD-00001 from the series | Customer, supplier and product codes are typed (`code` is required and pattern-checked) | Optional automatic codes from the numbering framework (CUS-0001, per firm or per category), as §34 does for stock movements; typing stays allowed. To verify what the phase 2 forms do |
| 11 | **New outlet approval** -- **built 2026-10-03** (SEL-15, A93): PENDING status, firm switch, approve single and bulk | A new customer is ACTIVE at once | Optionally, a customer added by a salesman (in the field, §39) starts PENDING: orders taken, but no credit sale or invoice until the office approves it. Goes with §39 and §56 bulk approval |

**Suggested order:** 2 (tax: SEZ and composition buyers are billed wrong
without it) -> 5, 7 (small, and weekly work) -> 1 -> 3 (decide first) -> 4
-> 6 -> 9, 10 -> 8 -> 11.

## 76. Routes with no screen, found tightening the orphan-route guard (D-GOLIVE-2)

Found 2026-10-01. `tests/unit/test_routes_have_a_caller.py` used to count a
route as reached whenever a generic helper (`'/api/v1/$resource/$id'`) could
in principle build it, which reached everything; it now expands those helpers
with the resource names the desktop actually hands them. 53 routes turned out
to have no caller. Most are deliberate surface (JSON batch imports for scripted
migration, machine exports) and are pinned with that reason. These are screen
gaps, pinned with a pointer here, each to build when a firm asks:

| Gap | Routes |
| --- | --- |
| Bulk status, category and profile on the Vendors, Branches and Warehouses lists | `POST /vendors/bulk-status`, `/vendors/bulk-category`, `/vendors/bulk-profile`, `/branches/bulk-status`, `/warehouses/bulk-status` |
| Bulk delete / restore / status on tax systems, components and profiles | `POST /tax-framework/{systems,components,profiles}/bulk-*` |
| Managing document lifecycle states and editing or retiring a document type | `GET/POST/PUT/DELETE /document-framework/document-states`, `PUT/DELETE /document-framework/document-types/{id}` |
| Editing or deleting a financial year (only create, close and reopen are offered) | `PATCH/DELETE /finance/financial-years/{id}` |
| The branch-warehouse settings read | `GET /branch-warehouse/settings` |
| Stock summary by product | `GET /inventory/summary/by-product` |
| The sales returns list's summary cards | `GET /sales-returns/summary` |

## 77. GST documents for the sales chain -- HIGH PRIORITY

**Status, 2026-10-02 (night, later):** row 7 built (A44). From the firm's *30-day rule from* date, registering an invoice, credit note, debit note or sales return through the portal or the offline export refuses one more than 30 days old, naming its last day and the remedy (cancel and raise again under today's date). `GET /einvoice/pending` and **E-invoice > To register** list every approved B2B document without an IRN, oldest first, with last day, days left and *Open* / *N days left* (within 5) / *Late*, a refused attempt's reason, and a Register button per row. Also D-TAX-2 fixed (A45): a completed sales return of billed goods registers as a CRN (migration 0234).

**Status, 2026-10-02 (night):** row 6 built (A43). Once the firm's *e-invoicing applies from* date has passed, an approved invoice to a buyer with a GSTIN -- and a credit or debit note against one -- is refused at print (`/print` on all three) and at a person's email send until it has a live IRN, by name and with `details.reason = irn_required`; *Print reference copy* (`?reference_copy=true`) prints it under "NO IRN YET - NOT A VALID TAX INVOICE". The automatic *Invoice approved* email waits in the outbox, saying why, and goes on the first pass after registration (rechecked every 5 minutes; waiting rows no longer crowd the worker's page). WhatsApp and SMS are not held: they name the invoice and issue nothing. A sales return's credit note cannot be e-invoiced yet and is left out (D-TAX-2).

**Status, 2026-10-02 (evening):** row 11 built -- a registered invoice, credit note or debit note prints its IRN, acknowledgement number and date and the signed QR in a box under the banner (the thermal roll prints the IRN and acknowledgement without the QR); a refused or withdrawn registration prints nothing. Credit notes and debit notes to customers are printable for the first time (`GET /credit-notes/{id}/print`, `GET /customer-debit-notes/{id}/print`), in the invoice's layout with "Against invoice" and the reason in the head and each line's tax split into the invoice line's heads.

**Status, 2026-10-02 (later still):** row 4 built -- credit notes and customer debit notes are registered on the portal as CRN and DBN, each carrying the invoice's parties and place of supply, its own lines and values, tax split into heads as the invoice line was charged, and `RefDtls` naming the invoice; through the sandbox or exported offline with the invoices (migration 0229).

**Status, 2026-10-02 (later):** rows 9 and 10 built -- an e-way bill without an IRN from the invoice where the firm need not e-invoice it, or from a delivery note no invoice bills (supply type from the challan reason), one recorded by hand after raising it on the portal (A42), and the firm's limit (`gst_compliance_settings.eway_bill_limit`, ₹50,000) with a due list and a prompt after dispatch or approval (migration 0228). E-invoicing itself may go through the portal by hand (A42, #936).

**Status, 2026-10-02:** rows 1-3 built. Every delivery note carries a reason (Sale, Van or route sale, Supply on approval, Quantity not known, Job work, Other with words), printed on the challan. A sale dispatched or completed by hand before its invoice is judged by the firm's policy in `gst_compliance_settings` -- Off, Warn (default; kept on the dispatch event and audit row) or Block -- and **Dispatch and invoice** dispatches, bills and approves in one transaction. A van or route sale goes on a challan unless the firm switches on "route sales need the invoice first", so either answer from the firm's CA is a setting. The same table holds the dates e-invoicing and the 30-day limit apply from (used by rows 6-7). Settings > Tax > GST documents.
Row 5 built 2026-10-02 (also §67 row 7): **Sales > Debit Notes** raises a debit note to a customer against an approved invoice -- price increase, short billed, charges added later, or other -- taxed at each invoice line's rate, no cap, approval separate from drafting (`CUSTOMER_DEBIT_NOTE_APPROVE`). It posts Dr receivable, Cr sales and output tax per head, and the extra is owed **on the invoice** (TallyPrime's against-reference, A40): Record Receipt, the ageing and the overdue list show the invoice at its total plus the note. GSTR-1 CDNR/CDNUR note type D; 3B adds it to 3.1(a). The printed debit note and its e-invoicing, open when this row was built, came with rows 11 and 4 the same day.

Owner, 2026-10-02: follow the GST rules and redesign the sales flow to market
standard. The rules, today's state, the redesigned flow and the work are in
`docs/GST_DOCUMENT_COMPLIANCE.md` (sections 1-4a); the decisions are
OWNER_DECISIONS A35. Summary of the rows (numbered as in that doc's section 4):

| # | Item | Pri |
| --- | --- | --- |
| 1 | Firm GST settings: e-invoicing applies, 30-day rule applies, each dated -- **built 2026-10-02** (#903) | P1 |
| 2 | Dispatch of a Sale delivery note with no invoice: firm policy warn (default) / block; **Dispatch and invoice** in one action -- **built 2026-10-02** (#903) | P1 |
| 3 | Challan reason on the delivery note, printed -- **built 2026-10-02** (#903) | P1 |
| 4 | E-invoice credit notes and debit notes -- **built 2026-10-02** (#938; sales returns #946) | P1 |
| 5 | Debit note to a customer (§67 row 7) -- **built 2026-10-02** (A40) | P1 |
| 6 | No print or send of a B2B invoice without an IRN where e-invoicing applies -- **built 2026-10-02** (A43) | P1 |
| 7 | 30-day list and check -- **built 2026-10-02** (A44) | P1 |
| 8 | Live e-invoice and e-way bill through a GSP (§55 M2) -- a per-firm route (A42); offline upload built (#936), Direct NIC and a GSP adapter not | P1 |
| 9 | E-way bill without an IRN, from the invoice or (only when there is none) the delivery note -- **built 2026-10-02** (#937) | P2 |
| 10 | E-way bill prompt above the firm's limit (default ₹50,000) -- **built 2026-10-02** (#937) | P2 |
| 11 | IRN, acknowledgement and QR on the invoice, credit and debit note prints -- **built 2026-10-02** (#939) | P2 |
| 12 | Credit note after 30 November warns -- **built 2026-10-02** (GST-1, A46) | P3 |
| 13 | 16-character check on GST document numbering -- **built 2026-10-02** (GST-2, A47) | P3 |
| 14 | Bill of supply | P3 |

**Order:** 3 + 2 + 1 → 5 → 4 → 9, 10, 11 → 6, 7 → 8 once a GSP is chosen → 12-14.

## 78. Purchases under GST: blocked credit, supplier type, GSTR-2B -- HIGH PRIORITY

**Status, 2026-10-02:** row 1 built (fixes D-TAX-1). Each bill line has an input-credit eligibility -- Eligible, Blocked (s.17(5)) or Ineligible -- taken from the line, else the product (a `PRODUCT_TAX_MANAGE` field), else a tax rule's *Input credit blocked*. Blocked or ineligible tax is booked to *Input Tax Not Claimable* (5450), never to input tax, and returns and debit notes take their share back off it. GSTR-3B: blocked in 4(A)(5) and reversed in 4(B)(1) (CBIC circular 170/02/2022); ineligible in 4(D)(2).
Row 2 built 2026-10-02: a supplier's GST type (Regular, Composition, Unregistered, Overseas, SEZ; blank read off the GSTIN), checked against the GSTIN on the form and the import (`GstType`). A supplier **declared** Composition, Unregistered or Overseas is billed no GST and gives no credit on every purchase document, reverse charge aside; one never declared is taxed by the rules as before (A37). The type reaches the tax rules as `vendor_type`.
Row 4 built 2026-10-02: rule 37. Accounts > Tax filing > Rule 37 (180 days) lists every bill dated (supplier's date, else ours) more than 180 days ago with credit claimed and money unpaid -- what it owes read from the payments service, so payments, returns and debit notes all count -- and the credit to reverse in proportion to the unpaid share, less what already stands reversed; a bill paid since shows its reclaim. The firm chooses Off, Report (default) or Report and post (Settings > Tax > GST Documents); posting moves the credit to *Input Tax Not Claimable* (5450) and a reclaim moves it back, one journal per bill (`R37-<bill>-<n>`), recorded in `itc_reversals` (migration 0230). GSTR-3B: reversals in 4(B)(2) (`itc_reversed_rule37` shows the part), reclaims in 4(A)(5) and 4(D)(1) (`itc_reclaimed`). Interest under s.50 is not computed.
Row 5 built 2026-10-02: a supplier can be marked *Supplier e-invoices* (form and import column `EInvoicing`), and a bill records the supplier's IRN (64 hexadecimal characters, read off the QR code; stored lower case). The IRN may be recorded on an approved bill too (`PUT /purchase-invoices/{id}/supplier-irn`, audited), since the QR code is often read after the bill is booked. The bill warns when the supplier e-invoices and the bill has no IRN (CGST rule 48(4)) -- Settings > Tax > GST Documents, *Supplier bill without an IRN*: Off or Warn (default) -- and, whatever the setting, when another bill already carries the same IRN. Migration 0232. Warned, never refused: Zoho Books and TallyPrime record the IRN without demanding it, and refusing the bill would stop the firm booking a payable it owes.
Row 6 built 2026-10-02: a goods receipt records the e-way bill the goods came on -- its 12-digit number and date -- typed on the receipt or, once it is completed, with *Record e-way bill* (`PUT /goods-receipts/{id}/eway-bill`, audited). A receipt worth more than the firm's e-way bill limit (the same setting as sales, ₹50,000 unless the firm sets its state's) with no number is warned about; for an unregistered supplier the warning says the e-way bill is the buyer's to raise (rule 138). Warned, never refused: the goods are already on the dock. Migration 0233. The value judged is the receipt's total; a bill that raises its own receipt (stages switched off) carries the number on that receipt.
Row 3 built 2026-10-02 (also §42.5): GST > GSTR-2B Reconciliation imports the month's 2B JSON from the portal (invoices and supplier credit/debit notes; other sections named as not read), matches each supplier invoice to the bill by GSTIN and the supplier's number read loosely (case, punctuation, leading zeros ignored), and the date and each head of tax within the firm's tolerance (₹1): Matched, Different (what differs), Not in books, or matched by hand; plus the bills 2B lacks. A supplier's credit note matches the debit note that recorded it. Settings > Tax > GST Documents: claim all bills (default) or only matched ones; under matched-only, unmatched credit is held out of 4(A)(5) and shown as awaiting 2B.

Owner, 2026-10-02: the purchase side of §77, against industry standard, with
what each firm configures. The rules, the comparison with Zoho Books, ERPNext
and TallyPrime, and the work are `docs/GST_DOCUMENT_COMPLIANCE.md` section 6;
decisions OWNER_DECISIONS A36. Rows, numbered as there:

| # | Item | Pri |
| --- | --- | --- |
| 1 | Credit eligibility per bill line (eligible / blocked 17(5) / ineligible), defaulting from product, expense account and tax rule; blocked tax goes to cost (fixes D-TAX-1) -- **built 2026-10-02** (#905) | P1 |
| 2 | Supplier GST treatment: regular, composition, unregistered, overseas, SEZ -- **built 2026-10-02** (#906) | P1 |
| 3 | GSTR-2B import and matching (§42.5); 3B claims all bills or only matched, per firm -- **built 2026-10-02** (#909) | P1 |
| 4 | 180-day unpaid-bill reversal and reclaim (rule 37) -- **built 2026-10-02** (#941) | P2 |
| 5 | Supplier's IRN on the bill; warn when an e-invoicing supplier's bill has none -- **built 2026-10-02** (#943) | P2 |
| 6 | E-way bill number on the goods receipt above the firm's limit -- **built 2026-10-02** (#944) | P2 |
| 7 | Warn on a bill entered after its credit's last date (30 November) -- **built 2026-10-02** (GST-3, A48) | P3 |
| 8 | Import bill of entry (§68) | P3 |
| 9 | Common credit reversal for a firm with exempt sales (rules 42/43) -- **rule 42 built 2026-10-03** (GST-4, A84); rule 43 (capital goods) open | P3 |

**Order:** 1 → 2 → 3 → 4, 5, 6 → 7-9, interleaved with §77 by priority.

## 79. Choosing batches on a sale -- HIGH PRIORITY

Owner, 2026-10-02: "when we select a sales item we need to show all batches,
or based on expiry and stock, for the same product, then select -- validate
with industry standards". Decision A38.

**Today:** approving a sales order reserves batches earliest-expiry-first
(expired ones skipped, judged on the order's date); the phase 2 delivery note
shows which batches dispatch will draw, read-only; a counter bill draws FEFO
silently. `delivery_note_lines.batch_number` exists but no screen sets it.

**What other products do:** Marg opens a batch window on the sale line (batch,
expiry, MRP, rate, stock; FEFO highlighted; expired blocked; split allowed);
Tally has a batch allocation sub-screen; ERPNext auto-picks by expiry with a
*Select Batch* override; Zoho Inventory picks batches by hand.

| # | Item | Pri |
| --- | --- | --- |
| 1 | Batch availability per product and warehouse, net of other orders' reservations, with expiry and days left (API) | P1 |
| 2 | Batch picker on the delivery note line (pre-filled with the reserved FEFO split; change, split, scan) and on the counter bill | P1 |
| 3 | Server checks: product, warehouse, not expired on the document date, enough available; moving the reservation to the chosen batch; FEFO skip recorded in the audit trail | P1 |
| 4 | Optional *pin batch* on the sales order line | P2 |
| 5 | One printed row per batch on the challan and invoice (batch, expiry, MRP) | P1 |
| 6 | Firm settings (Settings > Stock): near-expiry days (30), near-expiry warn / need a reason, FEFO skip allowed / need a reason, minimum shelf life per customer | P2 |
| 7 | Price from the batch where the batch carries its own MRP or rate | P2 |

**Status, 2026-10-02:** rows 1, 3 and 5 built, row 2 on the delivery note
(availability API, checked picks, FEFO skip audited, challan one row per
batch; `docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md`). Row 6 built the same day
except minimum shelf life per customer: `batch_sale_settings` -- near-expiry
window, near-expiry and FEFO-skip reasons judged at dispatch, and decision A2,
near-expiry stock exempt from the price floor. Row 2 on the counter bill built
the same day (picks handed to the note the bill raises), and row 6's minimum
shelf life per customer (allocation passes over a short batch; a hand-picked
one is blocked or warned, migration 0223). Row 4, pinning a batch on the order,
built the same day (migration 0224), and row 7, the batch's own MRP and
selling price (decision A41, migration 0225). §79 is complete.
