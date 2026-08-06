# Component Library

See also: `DESIGN_SYSTEM.md`, `DESKTOP_FRAMEWORK.md`, `DESKTOP_STYLE_GUIDE.md`.

## Workspace and shell

| Component | Use |
|---|---|
| `WorkspaceLayout` | Generic page composition (header/search/toolbar/filter/content/status) |
| `ModuleWorkspaceFrame` | Module title, breadcrumbs, tabs |
| `ManagementWorkspaceLayout` | CRUD workspace (search+toolbar+grid+details+status) |

## Actions and interactions

| Component | Use |
|---|---|
| `WorkspaceToolbar` | Standard action bar (new/view/edit/delete/refresh/import/export) |
| `WorkspaceShortcuts` | Keyboard action registration |
| `showWorkspaceContextMenu` | Row-level context actions |

## Data presentation

| Component | Use |
|---|---|
| `EnterpriseDataGrid` | Paginated sortable data table |
| `QuickSummaryPanel` / `DetailsPanel` | Selected record details |
| `StatusBadge` | Standard status visualization |
| `SummaryMetricCard` | Dashboard summary cards |

## Dialogs and forms

| Component | Use |
|---|---|
| `WorkspaceDialog` | Large tab-ready detail/editor dialog |
| `CrudWorkspaceDialog` | Metadata-driven CRUD editor |
| `showWorkspaceConfirmDialog` | Standard confirmation dialog |

## State surfaces

| Component | Use |
|---|---|
| `WorkspaceLoadingState` / `LoadingOverlay` | Loading indication |
| `WorkspaceErrorState` | Retryable error state |
| `WorkspaceEmptyState` / `StandardEmptyState` | Empty/no-result/no-permission/fallback states |
| `WorkspaceStatusBar` / `ApplicationStatusBar` | Module and app status |
