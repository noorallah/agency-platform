# What may appear in the sidebar

Three rules, each learned from a menu that had shipped for months doing
something other than what it said. They have now been applied to four modules
— Purchases, Goods Receipts, Delivery Notes and Sales Invoices — and between
them removed **twenty-one** sidebar entries.

> 1. **A status is a view, not a module.** It belongs on the segmented bar over
>    the list, not in the tree.
> 2. **A report is a report.** It belongs in the Reports module, which already
>    renders every one of them from `report_catalog.dart`.
> 3. **A menu entry must do what it says.** If clicking it produces the screen
>    you would have got anyway, it is worse than not being there.

Written 2026-08-22, after the third and fourth applications.

## How each module got here

| Module | Entries | Now | What the surplus was |
| --- | --- | --- | --- |
| Purchases | 11 | 4 | five status presets on one screen, then RFQs and Vendor Quotations, which had no backend at all |
| Goods Receipts | 8 | 1 | four filtered nothing, History duplicated Completed, Settings opened the list |
| Delivery Notes | 7 | 1 | two were status filters, four named reports |
| Sales Invoices | 7 | 1 | five named reports, one duplicated the list |

The Sales Invoices case is the sharpest. `SalesInvoiceManagementPage` never took
a tab id at all, so **all seven** entries built the same widget with the same
query — Overdue Invoices and Sales Invoices returned byte-identical lists. The
five reports those entries are named after exist on the backend at
`/api/v1/sales-invoices/reports/*`, are wired into the desktop's report
catalogue, and work: they were reachable from Reports, and from nowhere the
menu pointed at.

Delivery Notes went further and grouped its five under a node labelled
**Reports**, beside a module of that name that served them properly.

## The shape that replaced them

One workspace entry per module, and a `SegmentedButton` over the list carrying
the lifecycle statuses the server actually stores:

```dart
enum DeliveryNoteView {
  all, draft, approved, dispatched, completed, cancelled;

  String? get status => switch (this) { ... };
  Map<String, String> get query =>
      status == null ? const {} : {'status': status!};
}
```

`PurchaseOrderView`, `GoodsReceiptView`, `DeliveryNoteView` and
`SalesInvoiceView` are the four; copy whichever is closest. Two details are not
decoration:

- **The label is the stored status.** Goods Receipts says *Draft*, not
  *Pending*, because DRAFT is what the row holds and what the grid's status
  column shows. A second vocabulary for the same state is how "Pending
  Deliveries" and "Partial Deliveries" came to mean APPROVED and DISPATCHED.
- **A view that narrows nothing does not get a segment.** Sales Invoices has no
  *History* — the list is already sorted by invoice date — and no *Overdue*,
  because overdue needs the due date *and* what is still unpaid, which the list
  endpoint cannot express. The report can, and does.

## Never strand a stored workspace

The last workspace is persisted through `session.saveLastWorkspace`, so a
removed tab id is still on disk in every installation that used it. Two things
have to happen when the user opens the app on one.

**Which tab.** A module with more than one tab needs a map, or the upgrade
drops the user on its fallback tab with nothing to explain why. Purchases has
four and keeps `purchaseTabAliases`:

```dart
static const Map<String, String> purchaseTabAliases = <String, String>{
  'draft-orders': 'purchase-orders',
  ...
};
```

A module with **one** tab needs no map: the shell falls back to its only tab,
which is the same answer a map would give. Goods Receipts, Delivery Notes and
Sales Invoices are in that position, and a map for them would be code nothing
reads — which is what it briefly was.

**Which view.** Landing on the right screen is the floor, not the goal. Where a
retired entry stood for a status, `fromTabId` carries the choice across, so
somebody who left the app on Pending Deliveries opens on Approved rather than
on All.

```dart
static DeliveryNoteView fromTabId(String? tabId) => switch (tabId) {
      'pending-deliveries' => DeliveryNoteView.approved,
      ...
      _ => DeliveryNoteView.all,
    };
```

The shell reads the router's current tab and passes `initialView`.

## Before adding an entry

Ask what the click does that the entry above it does not. Then check the three
places the answer has to be real:

1. **The endpoint exists.** `grep` the backend router, not the API client — a
   client method can be as absent as the endpoint. RFQs and Vendor Quotations
   were sidebar entries for months against no model, table, service or route.
2. **The page reads the tab id.** `GoodsReceiptManagementPage` took a `tabId`
   parameter and never looked at it, which is why its Settings entry rendered
   the receipts list. A parameter is not wiring.
3. **It is not already in Reports.** `report_catalog.dart` is the list; if the
   thing you are adding is a table with columns and a date range, it belongs
   there.

`test/document_navigation_test.dart` and `test/purchase_navigation_test.dart`
pin all of this — the declared tab ids, that no retired id came back, the view
each one seeds, and that choosing a segment reaches the server with the status
on it. The last
assertion is the one that matters: the defect was invisible from the screen,
because every entry did render a list, and the list did look right.
