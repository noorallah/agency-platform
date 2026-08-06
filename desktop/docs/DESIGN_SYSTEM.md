# Enterprise Design System (UX-1)

## Purpose

This design system standardizes desktop UX across ERP modules using reusable Flutter workspace components. It is the baseline for all current and future modules.

## Document set

- `DESKTOP_FRAMEWORK.md`
- `UX_GUIDELINES.md`
- `COMPONENT_LIBRARY.md`
- `ICON_GUIDELINES.md`
- `COLOR_GUIDELINES.md`
- `LOGIN_SCREEN_GUIDELINES.md`
- `DESKTOP_STYLE_GUIDE.md`

## Design principles

1. Professional, minimal, high-density enterprise UI.
2. Reusable components over module-specific UI patterns.
3. Predictable keyboard-first workflows.
4. Clear status, error, loading, and empty-state feedback.
5. Accessibility and high-contrast support.

## Tokens

- **Spacing**: `AppSpacing` (`xs/sm/md/lg/xl/xxl`)
- **Dimensions**: `AppDimensions` (shell breakpoints, dialog scale, panel widths)
- **Radius**: `AppRadius` (small/medium/large)
- **Semantic colors**: `AppSemanticColors` (`success`, `warning`, `information`)

## Core framework components

- `WorkspaceLayout`
- `ModuleWorkspaceFrame`
- `ManagementWorkspaceLayout`
- `WorkspaceToolbar`
- `EnterpriseDataGrid`
- `WorkspaceDialog` / `CrudWorkspaceDialog`
- `SearchFilterPanel` / `FilterPanel`
- `StatusBadge`
- `SummaryMetricCard`
- `WorkspaceStatusBar` / `ApplicationStatusBar`
- `WorkspaceLoadingState` / `WorkspaceErrorState` / `StandardEmptyState`

## Reference implementation screens

UX-1 reference implementation is applied to:

1. Login
2. Dashboard
3. Product Management
4. Inventory Management
5. Customer Management
6. Vendor Management

## Compatibility rules

- No backend, API, or business-rule changes.
- Existing functionality must remain intact.
- New modules must compose this framework instead of introducing new shell patterns.
