# Desktop UI Framework

## Architecture

The desktop app uses reusable workspace templates instead of screen-specific layouts. Each module renders through a shared shell, **one unified navigation system**, standard toolbars, and consistent status surfaces. Business data (grids, forms, reports) always gets the maximum available width.

## Navigation architecture (single-panel standard)

Enterprise ERPs like SAP Fiori, Oracle Fusion, Dynamics 365, Azure Portal, and IDEs like Visual Studio / JetBrains / Outlook use **one** collapsible hierarchical navigation surface, not a fixed module rail plus a second permanently-visible sub-navigation panel. This app follows the same model:

- `EnterpriseSidebar` (`lib/ui/workspace/enterprise_sidebar.dart`) is the **only** navigation surface in the shell. It renders every module (Dashboard, Administration, Masters, Purchases, Sales, Inventory, Accounting, Reports, Licensing, Settings) as a top-level entry that expands in place to reveal its sub-navigation — there is no second, always-visible panel next to it.
- Sub-navigation for each module comes from `ModuleCatalog.navigationChildren(module, visibleTabIds)` (`lib/ui/workspace/module_catalog.dart`) — the single source of truth for module trees. Complex areas are grouped (e.g. Administration's `Configuration` node groups Business Profiles, Tax Configuration, and UOM & Packaging instead of listing 20+ flat tabs).
- `EnterpriseWorkspace` / `ConfigurationWorkspace` accept an **optional** `navigation` widget. The standard for every module going forward is to leave it `null`, because sub-navigation already lives in the sidebar tree. Only legacy/experimental workspaces should pass a second panel, and only temporarily during migration.

### Sizing and ratio

- Target ratio: navigation **15–18%** of the window width, workspace **82–85%**.
- Expanded sidebar: 260px. Collapsed (icon) rail: 64px.
- Removing the second permanent panel recovers roughly 20–30% of working width compared to the legacy two-panel layout.

### Collapse behavior

- `CollapsibleGroupTile` / `_ModuleGroup` (in `enterprise_sidebar.dart`) implement in-place expand/collapse — expanding a group does not open another panel, it grows within the same column.
- When the sidebar is collapsed to icons, tapping a module opens a `FlyoutMenu` (`showFlyoutMenu`) anchored to that icon, showing the same navigation nodes as the expanded tree (Visual Studio / Outlook / Azure Portal pattern). Selecting a leaf navigates and closes the flyout.
- The sidebar collapse state is a user preference (`DesktopPreferencesService.sidebarCollapsed`) and persists across sessions.

### Responsive guidelines

- **Wide monitor** (≥ ~1400px content width): expanded sidebar (260px) is the default.
- **Laptop** (~1000–1400px): users may collapse to the icon rail (64px) to reclaim width; flyouts keep sub-navigation reachable.
- **Narrow window** (< 1000px, the existing `wide` breakpoint in `desktop_shell.dart`): navigation moves into an overlay `Drawer`, matching the current small-window behavior.
- Never render two simultaneous permanent navigation columns at any breakpoint.

## Workspace templates

- **Master Management Workspace**: header, toolbar, search, filters, enterprise grid, details panel, status bar.
- **Configuration Workspace**: hierarchical navigation for unlimited depth, sourced from the unified sidebar tree (no in-workspace second panel by default).
- **Transaction Workspace**: summary cards, filters, grid, preview, history, workflow timeline.
- **Report Workspace**: filters, charts, pivot, export, print, drill-down.
- **Dashboard Workspace**: KPIs, widgets, recent activity, notifications.
- **Settings Workspace**: application, company, security, license, database, theme, localization.

## Reusable components

- `EnterpriseSidebar` — the single unified navigation surface (replaces the legacy module rail + second panel pattern).
- `CollapsibleGroupTile` — non-scrolling collapsible tree tile, reused by both the expanded sidebar tree and the collapsed-sidebar flyout.
- `FlyoutMenu` (`showFlyoutMenu`) — popover navigation shown when the sidebar is collapsed to icons.
- `WorkspaceNavigationTree` / `WorkspaceNavigationNode` — data-driven navigation tree primitives (`ModuleCatalog.navigationChildren` builds these per module).
- `EnterpriseWorkspace`
- `WorkspaceToolbar`
- `EnterpriseDataGrid`
- `FilterPanel`
- `SummaryCards`
- `DetailsPanel`
- `AuditPanel`
- `HistoryPanel`
- `AttachmentPanel`
- `ImportWizard`
- `ExportWizard`
- `EditorDialog`
- `ConfirmationDialog`
- `GlobalSearch`
- `NotificationCenter`
- `StatusBar`
- `Breadcrumb`
- `QuickActions`

## Navigation standards

- Use exactly one hierarchical navigation tree per shell; do not add a second permanent panel for module sub-navigation.
- Support unlimited depth via nested `WorkspaceNavigationNode`s and group related configuration screens instead of listing them flat.
- Preserve route compatibility by encoding nested paths in the workspace tab segment (`WorkspaceRouter`/`WorkspaceLocation`).
- Every module must expose its sub-navigation through `ModuleCatalog.navigationChildren` so `EnterpriseSidebar` can render it — do not hand-roll per-workspace navigation trees.
- Prioritize business data visibility: navigation should occupy the minimum practical space, and the workspace should occupy the rest.

## Visual standards

- Use consistent spacing, typography, icon sizes, and neutral surfaces.
- Keep primary actions visible in the workspace toolbar.
- Avoid crowded horizontal tab rows for large configuration areas — use the sidebar tree instead.

## Accessibility and keyboard

- All interactive controls must expose focus indicators.
- Tree navigation must remain keyboard accessible.
- Support standard desktop shortcuts across modules.

## Migration guide

1. Implement the shared workspace template and navigation primitives.
2. Migrate Administration first as the reference configuration workspace (done — its previous in-workspace navigation tree now lives in `ModuleCatalog.navigationChildren` and renders inside `EnterpriseSidebar`; `navigation` is `null` on its `ConfigurationWorkspace`).
3. Move high-volume master modules to the master-management template and remove their horizontal tab strips once their sidebar tree is defined in `ModuleCatalog.navigationChildren` (done for Masters, Purchases, Inventory, Sales).
4. Migrate transactions, reporting, and settings incrementally, always adding their sub-navigation to `ModuleCatalog.navigationChildren` rather than a new panel or tab strip.
5. Require future modules to use the shared framework and the unified sidebar — no module may introduce its own second navigation panel.

## Enterprise Design System (Phase 2)

Beyond navigation, every data-entry and grid screen must build on the shared **Enterprise component kit** rather than a bespoke layout. See the companion documents for full detail:

- [`ENTERPRISE_UI_DESIGN_GUIDE.md`](ENTERPRISE_UI_DESIGN_GUIDE.md) — overall design language and principles.
- [`COMPONENT_CATALOG.md`](COMPONENT_CATALOG.md) — every Enterprise* widget, its file, props, and usage.
- [`UX_STANDARDS.md`](UX_STANDARDS.md) — interaction, keyboard, and validation standards.
- [`LAYOUT_STANDARDS.md`](LAYOUT_STANDARDS.md) — spacing, section, and page layout rules.
- [`FORM_STANDARDS.md`](FORM_STANDARDS.md) — collapsible sections, Save/Save & New/Save & Close, unsaved-changes handling.
- [`GRID_STANDARDS.md`](GRID_STANDARDS.md) — toolbar/search/filter/grid/summary/details contract.
- [`RESPONSIVE_STANDARDS.md`](RESPONSIVE_STANDARDS.md) — breakpoints for navigation and workspace.
- [`REUSABLE_WIDGET_DOCUMENTATION.md`](REUSABLE_WIDGET_DOCUMENTATION.md) — API reference for `enterprise_form_kit.dart`.
- [`MIGRATION_GUIDE.md`](MIGRATION_GUIDE.md) — how remaining modules adopt this framework.

**Reference implementation**: `CrudWorkspaceDialog` (`lib/ui/resource_management_page.dart`) — the shared generic CRUD dialog used by Users, Roles, Permissions, Firms, Business Profiles, UOM, Packaging, etc. It was refactored from a `SegmentedButton` tab switcher to a single scrollable column of collapsible `EnterpriseSection`s, gaining `EnterpriseValidationSummary`, `EnterpriseActionBar` (Save & Close / Save & New / Cancel), and unsaved-changes confirmation automatically for every resource that already uses it — including the redesigned **User Management** screen (`_userDefinition` in `lib/ui/desktop_shell.dart`), which is the reference for the new General Information / Organization / Security / Contact Information / Address / Employment / Documents / Audit Information section taxonomy.

Per this sprint's explicit scope, **only User Management has been migrated**. Customers, Vendors, Products, Purchases, Inventory, and Sales keep their existing bespoke dialogs until reviewed and approved for migration (see `MIGRATION_GUIDE.md`).

