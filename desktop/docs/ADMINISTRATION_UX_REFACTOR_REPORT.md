# Administration UX Refactor Report

Refactoring Administration → Permissions into the reusable enterprise CRUD
workspace, and establishing that workspace as the standard for every module.

Standard: `ENTERPRISE_CRUD_WORKSPACE_GUIDE.md`.

## Headline finding

**The reusable workspace already existed.** `ResourceManagementPage<T>` +
`ResourceDefinition<T>` were already driving Users, Roles, Permissions, Firms
and Business Profiles, and `workspace_components.dart` already provided the page
frame, toolbar, grid, status badge, empty/loading/error states, pager and
confirm dialog.

So no `EnterpriseCrudWorkspace` class was created. Building one beside the
existing framework would have produced two toolbars, two grids and two empty
states, and left every module to choose. The work was instead: audit the
existing framework against the 24-point specification, close the gaps in it, and
migrate Permissions onto the result.

Of the specification, roughly two thirds was already satisfied. Six gaps were
real.

## Components reused (not rebuilt)

`ModuleWorkspaceFrame`, `ManagementWorkspaceLayout`, `WorkspaceToolbar`,
`SearchFilterPanel`, `FilterPanel`, `EnterpriseDataGrid`, `WorkspacePager`,
`StatusBadge`, `WorkspaceEmptyState`, `WorkspaceErrorState`,
`WorkspaceLoadingState`, `TableLoadingSkeleton`, `QuickSummaryPanel`,
`WorkspaceStatusBar`, `CrudWorkspaceDialog`, `EnterpriseSection`,
`WorkspaceShortcuts`, `showWorkspaceConfirmDialog`, `NotificationService`,
`PermissionService`.

## Components created

| Component | Why nothing existed |
|---|---|
| `_RowActions` (in `EnterpriseDataGrid`) | Row actions were one `IconButton` per action |
| `WorkspaceBulkActionBar` + `WorkspaceBulkAction` | No multi-selection affordance existed |
| `ResourceFilter` / `ResourceFilterOption` | `FilterPanel` existed but nothing configured it |
| `ResourceAction<T>` | Added earlier for the Firms provision action |

## Framework changes

1. **Row actions (§8).** Every applicable action rendered as its own icon, so a
   row carried view + edit + delete + copy and a 25-row grid carried a hundred
   icons. Now View and Edit inline, the rest behind `⋮`. Enforced in the grid so
   no module can regress it individually.

2. **Search (§4).** `searchHint` is configurable per module; typing is debounced
   350 ms into one request instead of firing per keystroke; the trailing icon
   is a working **Clear** that appears only when there is text — it was
   previously a second Search button sitting beside the search icon.

3. **Page size (§3).** `pageSize` / `pageSizeOptions` (25/50/100), wired through
   a new `loadPage` callback that carries the size into the request. **The
   selector is hidden unless a module supplies `loadPage`**, because
   `ApiClient._list` hardcodes `page_size: 20` — a selector without it would
   change the label and not the query. `ApiClient.permissions` gained an
   optional `pageSize`; extra optional named parameters still satisfy the
   narrower `load` signature, so no existing definition broke.

4. **Filters (§5).** Declarative `filters`, rendered into the existing
   `SearchFilterPanel` and passed to `loadPage`. Server-side only.

5. **Bulk selection (§6).** Multi-select wired to the grid's existing
   `selectedIds`; the toolbar is replaced by `WorkspaceBulkActionBar` while a
   selection exists. Selections are pruned to the visible page on reload.

6. **Empty and loading states (§9, §10).** "No results for your search" (offering
   **Clear filters**) is now distinct from "nothing created yet" (offering
   **Create X**, only with the create permission). First load shows a table
   skeleton instead of a blank page.

## Permissions screen changes

| Before | After |
|---|---|
| Columns: Code, Name, Status | **Permission**, Code, Status |
| Sort: code, name | name, code |
| "Search permissions" | "Search permissions by name or code" |
| 20 per page, fixed | 25/50/100, reaching the server |
| view+edit+delete+copy icons per row | 👁 ✎ ⋮ |
| "Manage platform permission definitions." | "Manage platform permissions and access capabilities." |

`permissionDefinition` was made public (it was `_permissionDefinition`) to match
`firmDefinition` and to be testable.

**No Module or Action columns.** The permissions API returns neither. Splitting
`JOURNAL_POST` into Module=JOURNAL, Action=POST would be a guess rendered as
fact, and would be wrong for codes like `CUSTOMER_MANAGE_SETTINGS`. The header
list takes them the day the API provides them.

**No filters and no bulk actions on Permissions.** `/api/v1/permissions` accepts
only `page`, `page_size`, `search`, `sort_by`, `sort_direction`, and there is no
bulk endpoint. The mechanisms exist and are unused here, which is the honest
result.

## Navigation changes

**None.** The specification's §13 grouping (Configuration → Business / Tax /
Inventory / Documents / Workflow / Notifications) is a larger change to
`module_catalog.dart` affecting every module's navigation, and the brief says not
to migrate broadly where it introduces risk. The catalog already supports
permission-filtered, collapsible groups that hide when empty, so the hierarchy
is a data change that can be made on its own. Flagged as outstanding.

## Backend

Unchanged. No business logic, schema, API contract, permission semantics or
route was touched. The only backend-adjacent change is the desktop
`ApiClient.permissions` sending `page_size`, a parameter the endpoint already
accepted.

## Tests

`test/enterprise_crud_workspace_test.dart` — 13 new tests:

- readable name leads, code retained
- search hint is the module's
- no filters/bulk actions declared where the API has none
- typing debounces to a single request
- clear button appears only with text, and resets the query
- page-size change reaches the server
- empty-after-search offers Clear filters, and clearing restores the list
- genuinely-empty offers Create
- empty offers no Create without the permission
- failed load shows the message and a retry
- row shows view + edit with the rest in `⋮`
- row actions respect the permission model
- selecting rows swaps in the selection bar, with no bulk action offered

`flutter analyze` clean. `flutter test` **195 passed**, including all 182 that
existed before.

Two of these tests initially passed for the wrong reason and were tightened: a
tooltip assertion matched the toolbar as well as the rows (now scoped to the
table), and the search assertions passed without the debounce having fired (now
pumped past it explicitly).

## Known limitations

1. **`dart format` was reverted outside this task's files.** Running it
   reformatted 47 files and introduced `curly_braces_in_flow_control_structures`
   lints in modules untouched here, by splitting single-line `if` returns. The
   repo is not uniformly `dart format` clean; making it so is its own change.
   Only files edited here are formatted.
2. **Filters have no consumer.** No list endpoint accepts filter parameters yet.
3. **Bulk actions have no consumer.** No module declares one, deliberately.
4. **Page-size selector only on Permissions**, the only `ApiClient` list method
   currently exposing `pageSize`. Extending it is one optional parameter per
   method plus a `loadPage`.
5. **Users and Roles are not migrated** beyond what they inherit automatically
   (row actions, search clear, states — every definition gets these). Their
   columns, search hints and page sizes are untouched.
6. **Navigation regrouping not done** — see above.
7. **Verified by widget test, not visually.** Screenshots are not capturable in
   this environment (the Flutter surface is GPU-composited), so the rendering
   was not inspected by eye.
