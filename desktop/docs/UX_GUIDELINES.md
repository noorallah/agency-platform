# UX Guidelines

See also: `DESIGN_SYSTEM.md`, `DESKTOP_FRAMEWORK.md`, `COMPONENT_LIBRARY.md`.

## Layout

- Standard shell: left navigation, page header, workspace, status bar.
- Use `ModuleWorkspaceFrame` for module pages.
- Use `ManagementWorkspaceLayout` for CRUD/list-detail workspaces.
- Keep layout usable at 1366x768, 1600x900, 1920x1080, 2560x1440.

## Forms

- Use `CrudWorkspaceDialog` with tabbed sections.
- Show inline field validation and top-level submission errors.
- Support save/cancel keyboard flow (`Ctrl+S`, `Esc`).
- Keep key actions visible in footer.

## Tables

- Use `EnterpriseDataGrid`.
- Preserve sorting, paging, selection, context-menu actions, row open (double-click), and copy.
- Display status fields with `StatusBadge`.

## Search and filters

- Use `SearchFilterPanel` for quick search.
- Use `FilterPanel` for expandable advanced filters.
- Keep search interactions keyboard-friendly.

## Feedback states

- Loading: `WorkspaceLoadingState` or `LoadingOverlay`.
- Errors: `WorkspaceErrorState`.
- Empty/no-result/no-permission/no-firm/license states: `StandardEmptyState`.
- Notifications: `NotificationService`.

## Accessibility

- Maintain focus traversal order.
- Ensure keyboard alternatives for toolbar/grid/dialog actions.
- Use high-contrast-compatible color tokens.

## Login screen

- Keep the login card centered, wider than the default form card, and visually calm.
- Use generic enterprise copy: welcome header, sign-in options, footer metadata, and dismissible errors.
- Keep loading, error, and quick-login states in the screen; never swap to a separate login flow.
- Support Enter to submit, Escape to dismiss errors, and standard text-field shortcuts.
