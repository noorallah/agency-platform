# Desktop Style Guide

See also: `DESIGN_SYSTEM.md`, `UX_GUIDELINES.md`, `COMPONENT_LIBRARY.md`.

## Typography usage

- Window title: `headlineMedium`
- Page title: `headlineMedium`
- Section header: `titleMedium`
- Card header: `titleMedium`
- Body text: `bodyMedium`
- Caption/help/status text: `bodySmall`
- Table header: `DataColumn` label with theme defaults
- Form labels: `InputDecoration.labelText`

## Spacing and sizing

- Horizontal workspace padding: `24`
- Header spacing: `12-24`
- Control spacing: use `AppSpacing` tokens only
- Dialog size: ~88% viewport via `WorkspaceDialog` / `CrudWorkspaceDialog`

## Form style

- Outlined inputs (`InputDecorationTheme`).
- Sectioned/tabbed layout for medium/large entities.
- Use explicit helper text for non-obvious inputs.

## Grid style

- `EnterpriseDataGrid` is the standard data table.
- Keep row actions in context menu and toolbar.
- Use status badges for status columns.

## Empty, loading, and error visuals

- Empty: `StandardEmptyState`
- Loading: `WorkspaceLoadingState`/`LoadingOverlay`
- Error: `WorkspaceErrorState`

## Do/Don't

- **Do** compose existing framework widgets.
- **Do** keep keyboard shortcuts functional.
- **Don't** create module-specific shell frameworks.
- **Don't** hardcode custom colors outside token/theme system.
