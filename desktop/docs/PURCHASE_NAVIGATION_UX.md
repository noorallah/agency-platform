# Purchases navigation and workspace UX

How the Purchases module is laid out, and the one rule that shapes it:

> **Purchase order statuses are views and filters, not modules.**

Written 2026-08-16, when the module went from eleven sidebar entries to five;
four since 2026-08-22, when the two that had no backend were removed rather
than reserved.

The rules this module established are now general, and have been applied
to Goods Receipts, Delivery Notes and Sales Invoices as well:
**`WORKSPACE_NAVIGATION_RULES.md`**.

## What it looked like, and why it changed

Purchases declared **eleven** tabs for **six** destinations:

```
Purchases
├── Dashboard
├── Orders ▾                ← says nothing about whose orders
│   ├── Purchase Orders
│   ├── RFQs
│   ├── Vendor Quotations
│   ├── Draft Orders        ┐
│   ├── Open Orders         │  all four: the same workspace,
│   ├── Cancelled Orders    │  one `status` preset each
│   └── Closed Orders       ┘
├── History                 ← the same workspace, a different sort
├── Analytics
└── Settings
```

Five menu items led to one screen. The group was labelled **Orders** in an
application that also has Sales Orders, Sales Invoices and Sales Returns, so the
word did not narrow anything. And a status is not a thing you navigate *to* — it
is a way of looking at what you are already on.

## The navigation now

```
Purchases
├── Dashboard              purchase-dashboard
├── Purchase Orders        purchase-orders
├── Analytics              purchase-analytics   → not built
└── Settings               purchase-settings
```

Declared in two places, both in `lib/ui/workspace/module_catalog.dart`:

- the module's `tabs:` list — the routing and permission source of truth, one
  entry per tab id;
- `_purchasesNavigation()` — how those flat ids are drawn as a tree.

**Goods Receipts, Purchase Invoices and Purchase Returns are not tabs.** They
are separate modules, drawn indented beneath Purchases by
`EnterpriseSidebarSection.childModuleIds` in `desktop_shell.dart`. They have
their own permissions, pages and routes; only where the sidebar draws them is
shared.

## The status bar

Inside Purchase Orders, above the grid:

```
[ All ] [ Draft ] [ Open ] [ Cancelled ] [ Closed ] [ History ]
```

`PurchaseOrderView` (`lib/ui/purchases/purchase_management_page.dart`) is the
enum behind it. Each segment sets the query the list already supported:

| Segment | `status` | `sort_by` |
|---|---|---|
| All | — | `created_at` |
| Draft | `DRAFT` | `created_at` |
| Open | `SUBMITTED` | `created_at` |
| Cancelled | `CANCELLED` | `created_at` |
| Closed | `CLOSED` | `created_at` |
| History | — | `purchase_date` |

**History is a sort, not a status.** It narrows nothing; it reorders every order
by its document date. That is what makes it worth a segment beside All rather
than a duplicate of it, and it is why the label is the one thing in this bar
that does not name a status.

Switching a segment keeps the search term and the advanced filters — the user is
looking at one screen and narrowing it. It clears the **selection**, because
that drives the bulk actions and a bulk close carried over from All could act on
orders no longer on screen.

The advanced filter panel still has its own Status dropdown, offering all nine
backend statuses, and it still **overrides** the segment
(`status: _status ?? _statusForView()`). That was the behaviour of the old tab
presets and it is unchanged.

### Two known gaps

- **"Open" means different things in two places.** This bar filters
  `status = SUBMITTED`. The Dashboard's *Open Orders* card counts `SUBMITTED`,
  `APPROVED`, `ORDERED`, `PARTIALLY_ORDERED` and `PARTIALLY_RECEIVED`. The list
  endpoint takes **one** status per request, so the two cannot be made to agree
  from the client. Closing this needs `GET /api/v1/purchases` to accept a set of
  statuses; until then the workspace status bar says *"Showing orders awaiting
  approval (SUBMITTED)"* rather than pretending otherwise.
- **Five statuses have no segment** — `APPROVED`, `ORDERED`,
  `PARTIALLY_ORDERED`, `PARTIALLY_RECEIVED`, `RECEIVED`. They appear under All
  and are selectable in the advanced filter. Six segments is already the width
  of a narrow window; eleven would be a second navigation. Two of these stopped
  being hypothetical on 2026-08-18, when completing a goods receipt began
  writing `PARTIALLY_RECEIVED` and `RECEIVED`, so a firm that receives against
  its orders now has rows only All will show.

## Routing, and the tab ids that retired

A tab id is a route. `_PurchaseWorkspaceState` in `desktop_shell.dart` maps one
to a page, and every case builds the same `PurchaseManagementPage` with a
different `section:`.

`draft-orders`, `open-orders`, `cancelled-orders`, `closed-orders` and
`purchase-history` no longer exist. **They still resolve**, through
`ModuleCatalog.purchaseTabAliases`: each maps to `purchase-orders`, and the
shell also derives the matching `initialView` so the workspace opens on that
segment. This is not politeness — the last workspace is persisted
(`session.saveLastWorkspace`), so without it anybody who left the app on Draft
Orders would be dropped on the Dashboard after an upgrade with nothing to
explain why.

Do **not** add a route for a status. That is the shape this document exists to
prevent.

## RBAC

Two filters, both already generic:

- `_visibleModules` hides a module the user has no permission for, and one the
  firm's business profile has not enabled.
- `_visibleTabIds` hides a tab whose `requiredPermissions` the user lacks,
  falling back to the module's own when a tab declares none.

Every Purchases tab requires `PURCHASE_VIEW`. A group disappears when the user
can see none of its children — guard any group you add with a `hasAny([...])`
over its child ids, so an empty expander never appears. Purchases has no group
left to guard since Sourcing went; `_salesNavigation` and its siblings show the
pattern.

## Acting on an order from inside it

Submit and Approve sit in the toolbar of the open purchase order as well as on
the workspace toolbar, as of 2026-08-18. The grid buttons are the only ones
that work without opening a document; these are the only ones that work while
reading one, which is when the decision is actually taken.

**Permission decides whether the button is rendered; status decides whether it
is enabled.**

| Order | Submit | Approve |
| --- | --- | --- |
| DRAFT | enabled | shown, disabled |
| SUBMITTED | disabled | enabled |
| APPROVED and beyond, or deleted | disabled | disabled |
| never saved (New / Duplicate) | not shown | not shown |

Someone holding `PURCHASE_APPROVE` sees Approve on a draft, greyed — the step
exists and it is theirs, it is just not their turn yet. Someone without it
never sees the button. The `EnterpriseApprovalPanel` above the header says
which of those it is in words, replacing the placeholder sentence that used to
describe the plumbing.

**The dialog does not close.** It holds the order the server returned, so the
status chip, the approval note, both buttons and the History tab all update in
place. That is also what makes two routes to one action safe: Submit stops
being pressable the moment the order stops being a draft, without waiting for a
reload. A refusal appears in the dialog's own banner rather than a toast, which
is easy to miss behind a modal.

Closing after an action reloads the grid — otherwise the row behind still reads
DRAFT — but does **not** claim the document was edited. `PurchaseEditorOutcome`
carries `saved` for exactly that: a save says "created"/"updated", a lifecycle
action says nothing more, having already reported itself.

Gating reuses the `isDraft` / `isSubmitted` getters the workspace toolbar
gates on, so the two routes cannot disagree about one order. Note the two
toolbars differ in one respect on purpose: the workspace **hides** Submit and
Approve when they do not apply, the dialog **disables** them, because in the
dialog the row of buttons is the document's own lifecycle and a gap in it reads
as a missing step.

The other six document screens still act only from their workspace toolbar —
see the comment on `DocumentViewDialog` for the three things to settle before
they follow.

## Printing

The Print control on the workspace toolbar and the one in the order dialog both
render `GET /api/v1/purchases/{id}/print` -- the same renderer the sales invoice
uses, given an order's shape: placed with a supplier, delivered to a warehouse,
and stating no place of supply and no HSN summary, because an order charges
nobody. The firm's `document_print_templates` row for `PURCHASE_ORDER` decides
the letterhead, terms and columns around that.

Until 2026-08-22 the toolbar button showed a toast reading *"Print is reserved
for the next transactional phase"* and the dialog's Print did nothing at all.
**Export and Email were beside it and have been removed** -- neither had a
handler, an endpoint, or any SMTP anywhere in the platform. Email comes back
when there is something behind it.

## Not built

Analytics renders `WorkspaceEmptyState` through `_buildPlaceholderSection()`.
There is no model, table, service, endpoint or API client method behind it.

**RFQs and Vendor Quotations were removed on 2026-08-22**, along with the
Sourcing group that held them. They had been kept as an extension point on the
argument that the navigation would then not have to change again when the
backend arrived. That trade was the wrong way round: the cost of adding a menu
entry later is one catalog line, while the cost of shipping one now is a user
who clicks it, reads that the API "does not yet expose" the screen, and learns
that this application's menu is not to be trusted. A navigation entry is a
promise the product keeps.

Both ids stay resolvable in `purchaseTabAliases`, pointing at Purchase Orders —
the last workspace is persisted, so somebody who closed the app on RFQs must
land somewhere real rather than on the fallback tab.

**Sales quotations are a different thing.** `sales_quotations` is customer-side
and lives under Sales. A vendor quotation is a supplier's response to an RFQ.
Keep them distinct in naming and in search, if the latter is ever built.

## Global search

Registered on the **backend**, in
`app/search/services/search_service.py`. Each `SearchDefinition` names the
module and tab the desktop should open. The purchase-order definition pointed at
a tab called `"purchases"` — the module id, not a tab, and no such tab has ever
existed — so opening a purchase order from Ctrl+K landed on the shell's fallback
tab instead of the order. It now names `purchase-orders`.

Six other definitions had the same defect and are fixed with it;
`tests/unit/test_search_navigation_targets.py` reads the tab ids out of this
catalog and fails the build if any definition names one that is not there.

RFQs and Vendor Quotations are not registered for search — there is nothing to
find, which is also why their screens no longer exist.

## What the screens are for

`docs/PURCHASE_FRAMEWORK.md` covers the workflow behind this navigation: the
four documents, their lifecycles, which transitions post stock or a journal,
and what purchasing depends on in other modules. Read it before changing what
an action on one of these screens does.

## The future lifecycle

The navigation is shaped for the whole procurement chain:

```
RFQ → Vendor Quotation → Purchase Order → Goods Receipt
    → Purchase Invoice → Purchase Return → Supplier Payment
```

Purchase Order is where it is, and the last four are already separate modules
drawn beneath Purchases. The first two exist nowhere: build the backend first,
then add a Sourcing group with `hasAny(['purchase-rfqs', 'vendor-quotations'])`
and drop the two ids out of `purchaseTabAliases`. Adding them requires moving
nothing that exists, which is the whole reason they did not need to be
pre-announced in the menu.

## Components reused

Nothing here is Purchase-specific machinery:

| Concern | Component |
|---|---|
| Page shell, title, breadcrumbs | `ModuleWorkspaceFrame` |
| Toolbar / search / filters / grid / status | `ManagementWorkspaceLayout` |
| The status bar's slot | `ManagementWorkspaceLayout.viewBar` |
| Nav tree and groups | `WorkspaceNavigationNode`, `CollapsibleGroupTile` |
| "Not built yet" | `WorkspaceEmptyState` |
| Grid, paging, row actions | `EnterpriseDataGrid` |
| Editor | `WorkspaceDialog` |

`viewBar` was added to the shared layout rather than to this page. A list whose
records fall into a few states somebody switches between all day is not unique
to purchasing — sales orders, invoices and returns are the obvious next users,
and the alternative was every module inventing its own spacing above the grid.
See `ENTERPRISE_CRUD_WORKSPACE_GUIDE.md`.
