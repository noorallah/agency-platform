# Backlog

Work that is agreed but not started, with the decisions each one is waiting on.
Items move out of here when they are built, not when they are discussed.

Open feature-gating decisions live in `docs/MODULE_REVIEW_CHECKLIST.md` under
"three features deliberately left ungated" — they are questions rather than
tasks, so they stay there.

---

## 1. Make the remote UI work over the network

**Blocks: the installer.** Decide this first; whatever we choose, the installer
is what has to carry it.

The desktop client refuses plain HTTP to anything but `localhost` — see
`normalizeServerUrl` in
`desktop/lib/core/preferences/desktop_preferences_service.dart`. A client on
another machine therefore cannot reach `http://<lan-ip>:8000`, which is exactly
the deployment the product calls for.

Three ways out, in the order I would consider them:

1. **HTTPS on the backend with a self-signed certificate**, installed into the
   Windows trust store on every client by the installer. Keeps the guarantee,
   costs installer complexity.
2. **A reverse proxy** on the server machine terminating TLS. Same guarantee,
   another moving part to install and supervise on a low-specification box.
3. **Relax the rule for private-network addresses.** Cheapest, and it weakens
   the protection that stops credentials crossing the LAN in clear text. If we
   do this it should be a deliberate decision with its own tests, not a quiet
   edit.

Test cases are already written: `docs/MANUAL_UI_TEST_PLAN.md` §3.

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

## 3. Single self-installing batch file

One Windows script that installs the prerequisites, migrates **every** schema,
starts the backend, and opens the UI. No Docker; target is a low-configuration
Windows machine.

Waiting on item 1 — the installer has to set up whatever transport we settle on,
including placing a certificate in the trust store if it comes to that.

Things it must get right, each of which has bitten this project already:

- **Migrate every store, not just `platform`.** `alembic upgrade head` advances
  one schema, chosen by `AGENCY_DATABASE_SCHEMA`. A firm store left behind is
  invisible until a query hits a missing column.
- **Enumerate the real targets** from `firms` and `firm_storage_mappings` rather
  than a hardcoded list.
- Refuse to start with the development JWT key or without a bootstrap admin
  password, the way the app already does.
- Be safe to run twice.

Draft test cases: `docs/MANUAL_UI_TEST_PLAN.md` §2.

---

## 4. A skill for resetting and regenerating demo data

`seed_multi_firm_demo.py` now seeds masters and two years of trading in one
command, and `generate_transaction_history.py` regenerates one firm's history
on its own. Wrapping the sequence in a skill would make it one instruction
rather than a command plus the four `alembic upgrade head` runs that have to
precede it, and would carry the traps with it -- migrate every store, enumerate
the targets from the registry, clear `AGENCY_DATABASE_*` afterwards.

Worth doing when the reset sequence stops changing.

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

**The change**, when it happens: re-parent the six document modules —
`salesOrders`, `deliveryNotes`, `salesInvoices` under Sales;
`purchaseInvoices`, `purchaseReturns`, `goodsReceipts` under Purchases. That
takes the top level from 16 entries to 10 and the TRANSACTIONS section to 2. It
is catalog data plus the `_page(...)` switch and `_moduleCode` in
`desktop_shell.dart`; the sidebar needs nothing new.

Two things to carry into it:

- `_routeModule()` falls back to Dashboard for an unknown route (`orElse`), so a
  stored `lastWorkspace` cannot crash — but **without an alias map, anyone whose
  last screen was `salesInvoices` silently lands on Dashboard.**
- `desktop/test/navigation_tree_test.dart` and `workspace_overflow_test.dart`
  both assert on the current tree and will need updating with it.

Also open in the same pass: **Purchases is listed before Sales** (fine, but be
deliberate), and **Configuration is scattered** across Masters and Settings —
the §13 grouping from the enterprise CRUD brief, still outstanding.

### Not to do

**A Windows-style File/Edit menu bar.** ERP actions belong to the record on
screen, and the workspace toolbar already owns New / Edit / Delete / Export. A
global menu bar would either duplicate it or go stale against the selection. The
left rail plus the per-screen toolbar is the right pairing; this was considered
and rejected, not overlooked.

### Header and footer — reviewed, left as they are

Both were examined and the decision was to **change nothing for now**. Recorded
so the next reader knows these are known, not missed:

- The header (68px, `_applicationHeader`) shows the application name a second
  time (the sidebar has it), `ThemeSelector` a second time (the sidebar footer
  has it), and the module title up to three times — header label, selected
  sidebar item, and the page's own `PageHeader`. Back and forward are genuinely
  useful and unusual in an ERP; keep them whatever else changes.
- The footer (`_applicationStatusBar`) passes `backend: checking` and
  `database: unknown` as literals, and nothing ever probes them — so the bar
  reports "checking" permanently. A health light that never changes is worse
  than none, because it will be believed once. `stateText: 'Online'` is likewise
  constant, and the bar repeats the user's email address, which the profile menu
  already shows. Either probe `/health` for real or drop the indicators; do not
  leave a third state where they look live and are not.

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

Two things the batch work leaves behind:

- **`BatchResponse` still returns `product_code`, `product_name`,
  `warehouse_code`, `warehouse_name`, `branch_code` and `branch_name` as null.**
  Nothing populates them -- the model has no such attributes and the response is
  validated straight off the record -- so the desktop's batch grid renders blank
  columns. Now that responses are built through
  `BatchSerialService.batch_responses`, that is where the join would go.
- **The demo data has no batches**, so nothing in the seeded stores exercises
  batch-grained stock. `scripts/generate_sample_data.py` writes `batch_number`
  onto document lines but never registers a batch, which is why the receipt path
  that creates them never runs during a seed.

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

Not part of this, but adjacent and unbuilt: warehouse-to-warehouse transfers,
physical count reconciliation, and dedicated damage/expiry/quarantine
write-offs (only a generic `ADJUSTMENT` reaches those buckets). Stock movements
also post nothing to the general ledger, so stock value and the inventory
control account never reconcile.

## Also open

- **Desktop does not pre-hide feature-gated fields.** The backend refuses them
  (a 403 naming the feature), but the UI lets a user type a barcode into a firm
  that has no barcode feature and only fails on save. Decide whether that is
  acceptable or whether the desktop should read `/active-features` and hide
  them. `docs/MANUAL_UI_TEST_PLAN.md` §6.8.
- **`tests/` still has about 40 ruff findings** — missing docstrings and long
  lines in older test files. `app/` is clean.
