# Enterprise CRUD Workspace Guide

The standard for every list-and-edit screen in the Agency Platform. Adding a
module means writing a `ResourceDefinition<T>` — metadata and API callbacks —
not another table, toolbar, pager, empty state and error state.

Reference implementation: **Administration → Permissions**
(`permissionDefinition` in `lib/ui/desktop_shell.dart`).

## 1. Component architecture

There is no `EnterpriseCrudWorkspace` class. The workspace already existed as
`ResourceManagementPage<T>` + `ResourceDefinition<T>`, and a second framework
beside it would have meant two of everything. These are the parts:

| Concern | Component | Where |
|---|---|---|
| Page shell, title, description, breadcrumbs | `ModuleWorkspaceFrame` | `workspace_components.dart` |
| Layout (toolbar / search / grid / details / status) | `ManagementWorkspaceLayout` | `workspace_components.dart` |
| Toolbar | `WorkspaceToolbar` (+ `trailing`) | `workspace_components.dart` |
| Search and filter bar | `SearchFilterPanel`, `FilterPanel` | `workspace_components.dart` |
| Grid, paging, selection, row actions | `EnterpriseDataGrid<T>` | `workspace_components.dart` |
| Row overflow menu | `_RowActions` (internal to the grid) | `workspace_components.dart` |
| Bulk bar | `WorkspaceBulkActionBar`, `WorkspaceBulkAction` | `workspace_components.dart` |
| Status pill | `StatusBadge.fromStatus` | `workspace_components.dart` |
| Empty / loading / error | `WorkspaceEmptyState`, `TableLoadingSkeleton`, `WorkspaceErrorState` | `workspace_components.dart` |
| Form dialog | `CrudWorkspaceDialog` | `workspace_dialog.dart` |
| Form sections | `EnterpriseSection` | `enterprise_form_kit.dart` |
| Confirmation | `showWorkspaceConfirmDialog`, `AppDialogs.confirm` | framework / `core/dialogs` |
| Orchestration | `ResourceManagementPage<T>` | `resource_management_page.dart` |

Import everything through the barrel:

```dart
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
```

## 2. Standard screen layout

```
Workspace › Administration › Permissions        ← ModuleWorkspaceFrame
Permissions
Manage platform permissions and access capabilities.

[ Search permissions by name or code  ✕ ]  [ Module ▾ ]   ← SearchFilterPanel
[ + New ] [ View ] [ Edit ] [ Delete ] [ Refresh ] [ Export ]  ← WorkspaceToolbar

┌──┬──────────────────┬───────────────┬────────┬──────────┐
│□ │ Permission       │ Code          │ Status │ Actions  │
├──┼──────────────────┼───────────────┼────────┼──────────┤
│□ │ Journal Posting  │ JOURNAL_POST  │ Active │ 👁 ✎ ⋮   │
└──┴──────────────────┴───────────────┴────────┴──────────┘
Showing 1–25 of 164                       Rows per page: 25 ▾

3 records                                        ← WorkspaceStatusBar
```

## 3. Search

Set `searchHint` in the user's words — what the records can be found *by*, not
the word "Search":

```dart
searchHint: 'Search permissions by name or code',
```

Typing is debounced 350 ms into a single request; the clear (✕) appears only
once there is text. Search always resets to page 1. `Ctrl+F` focuses the field
via `WorkspaceShortcuts`.

## 4. Filters

Declare them; the bar appears only for modules that do.

```dart
filters: const [
  ResourceFilter(key: 'status', label: 'Status', options: [
    ResourceFilterOption(value: 'ACTIVE', label: 'Active'),
    ResourceFilterOption(value: 'INACTIVE', label: 'Inactive'),
  ]),
],
```

**Filters require `loadPage`.** The value is handed to the server; nothing
filters an already-fetched page, because that would disagree with the record
count and the paging.

> Today no list endpoint accepts filter parameters — `page`, `page_size`,
> `search`, `sort_by`, `sort_direction` are the whitelist. So no module declares
> filters yet. This is the client half, ready for the first endpoint that grows
> one. Do not add a filter that the API ignores.

## 5. Pagination

Server-side, always. `load` is enough for paging at the server's default size
(20). A page-size selector requires `loadPage`, because the size has to reach
the request:

```dart
loadPage: ({
  int page = 1,
  int pageSize = 25,
  String search = '',
  String sortBy = 'created_at',
  bool descending = true,
  Map<String, String> filters = const {},
}) => api.permissions(
      page: page, pageSize: pageSize, search: search,
      sortBy: sortBy, descending: descending,
    ),
pageSize: 25,
pageSizeOptions: const [25, 50, 100],
```

Without `loadPage` the selector is hidden and the size shows 20. Offering a
control that changes a number the server ignores is worse than offering none.

Add an optional `pageSize` named parameter to the `ApiClient` method — extra
optional named parameters still satisfy the narrower `load` signature, so
existing definitions keep compiling.

## 6. Row actions

`View` and `Edit` are inline; everything else is behind `⋮`. This is enforced by
the grid, not by each module: pass `contextActions` and the grid decides
placement. Never add per-row `IconButton`s in a module.

Actions come from `WorkspaceContextAction` (`view`, `edit`, `delete`, `restore`,
`copy`, `refresh`, `export`). `refresh` and `export` are grid-scoped and never
appear in a row. Visibility is filtered by `canUseAction` before it reaches the
grid, so an action the user cannot perform is absent rather than disabled.

For an action the enum cannot express — "Provision storage" on Firms — use
`customActions`:

```dart
customActions: [
  ResourceAction<Firm>(
    label: 'Provision storage',
    icon: Icons.dns_outlined,
    isVisible: (firm) => firm == null || firm.deploymentMode != 'SHARED',
    isEnabled: (firm) => !firm.isStorageReady,
    onInvoke: (firm) => api.provisionFirmStorage(firm.id),
  ),
],
```

## 7. Bulk actions

Ticking rows replaces the toolbar with `WorkspaceBulkActionBar`. A module with
no bulk endpoint declares none and the bar shows only the count and
**Clear selection** — the selection still works, it just offers nothing that
cannot be done.

```dart
bulkActions: [
  WorkspaceBulkAction(
    label: 'Deactivate',
    icon: Icons.block,
    isDestructive: true,
    onInvoke: (ids) async { /* call the real bulk endpoint */ return '...'; },
  ),
],
```

**Do not fake this.** CLAUDE.md records that the existing bulk endpoints were a
second implementation that skipped audit rows and delete guards; a bulk button
must call an endpoint built for it.

Selections are pruned to the visible page on every reload, so a bulk action can
never operate on rows the user can no longer see.

## 8. Empty, loading and error states

- **Loading (first load)** — `TableLoadingSkeleton` shaped like the table. A
  refresh with rows already on screen keeps them and shows "Refreshing…" in the
  status bar; the page never goes blank.
- **Empty after search/filter** — "No X found", plus **Clear filters**.
- **Empty with nothing narrowed** — "No X yet", plus **Create X** when the user
  holds the create permission.
- **Error** — `WorkspaceErrorState` with **Try again**.

The distinction matters: "nothing matched" and "nothing exists" need different
words and different offers.

## 9. Forms

`CrudWorkspaceDialog` renders one scrollable form of `EnterpriseSection`s — no
tabs. Group with `FieldSpec.section`:

```dart
FieldSpec(key: 'email', label: 'Email', section: 'General'),
FieldSpec(key: 'password', label: 'Password', section: 'Security'),
```

**The form never discards what the user typed.** On a validation or API failure
it stays open with the values intact and the error shown inside it; it closes
only on success or explicit Cancel. `CrudCreateCheckpoint` makes a retry after a
partial failure reuse the record already created rather than making a second one.

Use `createFollowUp` when a create leaves something outstanding that the form
cannot do:

```dart
createFollowUp: (_) => 'Set this firm\'s business profile in Firm Settings.',
```

## 10. Configuration grouping

Modules and tabs are data in `ui/workspace/module_catalog.dart`. A tab is hidden
unless the user holds its `requiredPermissions`, and a group with no visible
tabs disappears. Add a catalog entry plus a page — never new navigation code.

## 11. Permission behaviour

Compose `canUseAction` from the module's codes:

```dart
canUseAction: (action, _) => _canUseResourceAction(
  permissions, action,
  view: const ['PERMISSION_VIEW'],
  create: const ['PERMISSION_CREATE'],
  update: const ['PERMISSION_UPDATE'],
  delete: const ['PERMISSION_DELETE'],
),
```

This gates the toolbar, the row actions, the context menu and the empty-state
Create button from one declaration. It is a UX affordance, not a security
boundary — the server enforces the same codes.

## 12. Adding a module

1. Add a `ModuleTabDefinition` to the catalog with its permissions.
2. Write `xxxDefinition(api, permissions)` returning a `ResourceDefinition<T>`.
3. Render `ResourceManagementPage<T>` for the tab id in `desktop_shell.dart`.
4. Add a widget test modelled on `test/enterprise_crud_workspace_test.dart`.

## 13. Example — Permissions (reference)

```dart
ResourceDefinition<Permission>(
  title: 'Permissions',
  resource: 'permissions',
  description: 'Manage platform permissions and access capabilities.',
  headers: const ['Permission', 'Code', 'Status'],
  sortFields: const ['name', 'code', null],
  cells: (p) => [p.name, p.code, p.isActive ? 'Active' : 'Inactive'],
  id: (p) => p.id,
  load: api.permissions,
  loadPage: /* see §5 */,
  searchHint: 'Search permissions by name or code',
  canUseAction: /* see §11 */,
  fields: const [ /* code, name, description, is_active */ ],
  initialValues: ..., payload: ..., partialUpdate: true,
)
```

Readable name first, technical code second: an administrator scans for
"Journal Posting", not `JOURNAL_POST`. The code stays — it is what the API and
the role screens speak — but it does not lead.

Module and Action columns are **not** present. The permissions API returns
neither, and deriving them by splitting the code would be a guess displayed as
fact. The header list takes them the day the API does.

## 14. Example — a simple master

UOM, Tax Component, Role: the same shape with fewer fields. Omit `loadPage`
unless the endpoint accepts `page_size`; omit `filters` and `bulkActions`.

## 15. Example — a complex transaction

Purchase Orders, GRN, Sales Orders, Sales Invoices keep this workspace as the
list shell — same toolbar, search, grid, paging, states — and open a
module-owned document dialog instead of the generic form, because a document
has lines, totals, a timeline and approvals. Use `customActions` for
document-specific verbs (Approve, Post, Cancel) and let `canUseAction` gate them.
The surrounding shell must not vary.

## Status badges

`StatusBadge.fromStatus(value)` renders any column whose header contains
"Status". Colour is never the only signal — the text is always present.
