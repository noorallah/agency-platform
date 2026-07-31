# Desktop Framework

This document defines how every Agency Platform ERP module composes the shared
Flutter desktop infrastructure. Business modules must not create alternative
workspace shells, CRUD dialogs, notifications, loading states, or table
interaction patterns.

## Public component library

Import the framework barrel:

```dart
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
```

The library provides:

| Component | Responsibility |
| --- | --- |
| `WorkspaceLayout` | Breadcrumb, page header, toolbar, search, filters, content, and status |
| `ModuleWorkspaceFrame` | Module title, tabs, and bounded module content |
| `ManagementWorkspaceLayout` | Search/toolbar, grid, details panel, and workspace status |
| `WorkspaceDialog` | Generic 88% window dialog with tabs, body, footer, loading, and shortcuts |
| `CrudWorkspaceDialog` | Metadata-driven Create/View/Edit forms used by current resources |
| `WorkspaceToolbar` | Stable CRUD action ordering and enabled/visible states |
| `SearchFilterPanel` / `FilterPanel` | Search and basic/advanced filter composition |
| `EnterpriseDataGrid` | Pagination, sorting, selection, double-click, and context actions |
| `ApplicationStatusBar` / `WorkspaceStatusBar` | Global health/context and record status |
| `LoadingOverlay` / `TableLoadingSkeleton` | Page, dialog, table, and background loading |
| `StandardEmptyState` | Typed no-data, no-results, permission, network, firm, and license states |
| `WorkspaceShortcuts` | Permission-safe module shortcut registration |
| `showWorkspaceContextMenu` | Extendable View/Edit/Delete/Copy/Refresh/Export menu |
| `showGlobalSearch` | Ctrl+K search UI contract; no API dependency |

Core services and infrastructure remain separately injectable:

- `NotificationPresenter` / `NotificationService`
- `DesktopPreferencesService`
- `ThemeManager`
- `AppDialogs`
- `PermissionService`

## Creating a standard CRUD module

Existing REST resources use `ResourceManagementPage<T>` and a
`ResourceDefinition<T>`. The definition owns metadata and API callbacks while
the shared page owns loading, errors, search, pagination, selection, details,
dialogs, shortcuts, copy, confirmation, and notifications.

```dart
ResourceManagementPage<Vendor>(
  api: api,
  definition: ResourceDefinition<Vendor>(
    title: 'Vendors',
    resource: 'vendors',
    headers: const ['Code', 'Name', 'Status'],
    cells: (vendor) => [vendor.code, vendor.name, vendor.status],
    id: (vendor) => vendor.id,
    load: api.vendors,
    fields: vendorFields,
    initialValues: vendorInitialValues,
    payload: vendorPayload,
    canUseAction: (action, selected) =>
        permissions.canUseAction(vendorPermissions[action] ?? const []),
  ),
)
```

Customers, Vendors, Products, Sales, Inventory, Accounting, and Reports should
provide only entity models, API adapters, field metadata, permission mapping,
and optional details/export callbacks. They must not duplicate the surrounding
workspace.

## Complex documents and reports

Complex records that do not fit metadata-driven fields still use
`WorkspaceDialog`. Supply module-owned tab bodies and a footer while retaining
shared sizing, scrolling boundaries, loading protection, Ctrl+S, and Escape.

```dart
WorkspaceDialog(
  title: 'Sales order',
  subtitle: 'Create new document',
  icon: Icons.receipt_long_outlined,
  tabs: [
    WorkspaceDialogTab(label: 'General', child: generalForm),
    WorkspaceDialogTab(label: 'Lines', child: lineEditor),
  ],
  body: generalForm,
  footer: documentFooter,
  loading: controller.saving,
  onSave: controller.save,
  onClose: controller.cancel,
)
```

Reports use `WorkspaceLayout` with their own bounded report content. They may
replace the grid with charts or report viewers, but search, filters, status,
loading, empty states, and export actions remain shared.

## Interaction contracts

`WorkspaceShortcuts` registers only callbacks the current user may invoke.
Supported defaults are Ctrl+N, Ctrl+S, Ctrl+F, Ctrl+R, Ctrl+C, Ctrl+K, Escape,
F5, and Delete. Delete callbacks must open confirmation and must never perform
an immediate mutation.

Grid context menus extend `WorkspaceContextAction`; unsupported or unauthorized
actions are omitted. Right-click selects the row before opening its menu.
Ctrl+C and Copy row place tab-delimited visible cell values on the clipboard
without replacing normal row selection. Read-only detail values use
`SelectableText`.

## State and feedback

- Use `NotificationService.instance` through `NotificationPresenter` when
  injecting feedback; use the static convenience method in existing widgets.
- Use `ConfirmationType` presets for delete, logout, discard, password reset,
  lock, and unlock operations.
- Use `LoadingOverlay` when loaded content should remain visible, skeletons for
  initial table loading, and button progress for mutations.
- Use `StandardEmptyState` so no records, no results, permissions, network,
  firm, and licensing failures remain visually distinct.
- Keep backend validation authoritative and map field errors inside the shared
  CRUD dialog.

## Preferences and themes

`DesktopPreferencesService` persists local window state, sidebar collapse,
grid density, theme cache, landing page, server history, and last workspace.
Server preference fields already include theme, default firm, landing page,
and rows per page; synchronize through the authenticated API only when that
backend setting is supported.

Widgets consume `ThemeData`, `ColorScheme`, `AppSemanticColors`, and design
tokens from `core\design\design_tokens.dart`. Feature modules must not define
themes or hardcode presentation colors. `ThemeManager` remains the only runtime
theme coordinator and preserves the five future-compatible theme identities.

## Dependency and ownership rules

1. Widgets receive API adapters, permission checks, controllers, and services
   through constructors.
2. Feature widgets compose shared components; they do not own shell state.
3. Controllers own query, mutation, and validation orchestration. Widgets own
   transient focus, selection, and presentation state only.
4. Backend APIs, authentication, database access, and business rules stay
   outside the desktop framework.
5. Every module must remain bounded and overflow-free at 1366x768, 1600x900,
   1920x1080, restored windows, and maximized windows.
