# Grid Standards

Every module's list/grid screen (via `ResourceManagementPage<T>` or a bespoke equivalent) must expose the same building blocks, in the same order:

1. **Toolbar** — module title, primary "New" action, contextual actions.
2. **Search** — free-text search bound to the list query.
3. **Advanced Filters** — optional filter panel (`FilterPanel` in `workspace_components.dart`) for modules with rich filter needs.
4. **Grid** — sortable columns (`sortFields`), paginated (`PagedResult<T>`), row selection.
5. **Summary Panel** — aggregate counts/totals where relevant (module-specific).
6. **Details Panel** — optional read-only preview of the selected row without opening the full dialog.
7. **Bulk Actions** — multi-select operations where the module supports them.
8. **Column Chooser / Export / Import** — provided by existing `ExportWizard`/`ImportWizard` where wired.
9. **Keyboard Navigation** — arrow-key row movement, `Enter` to open, `Ctrl+N` to create (already standard in `ResourceManagementPage`).
10. **Context Menu** — right-click row actions where supported.

This document describes the target contract; it does not change any existing grid implementation as part of this sprint (no business modules were migrated). New/updated modules should conform to this list, and any gaps found while migrating a module later should be fixed in the shared framework, not worked around locally.
