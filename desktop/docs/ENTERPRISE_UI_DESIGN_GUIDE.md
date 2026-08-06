# Enterprise UI Design Guide

## Purpose

This guide defines the visual and interaction language for the agency-platform desktop ERP. It exists so that every module — regardless of which developer builds it — looks and behaves like it belongs to the same product, comparable to SAP Fiori, Oracle Fusion, Dynamics 365, Odoo Enterprise, and ERPNext.

## Guiding principles

1. **Data first.** Navigation and chrome are minimized so grids, forms, and reports get the maximum screen space (target: 15% navigation / 85% workspace).
2. **One way to do each thing.** One navigation system (`EnterpriseSidebar`), one CRUD dialog shell (`CrudWorkspaceDialog`), one section primitive (`EnterpriseSection`), one action bar (`EnterpriseActionBar`). Modules never invent their own layout primitives.
3. **Scroll, don't switch.** Long forms use vertically stacked collapsible sections instead of tabs, so users see the whole record and never "hide" an invalid field behind an unselected tab.
4. **Never lose work.** Validation failures keep the form open, highlight the field, and show a summary. Closing a dirty form always asks for confirmation.
5. **Read/Edit/Create share one layout.** Only field affordances (editable vs read-only) change between modes — never the page structure.
6. **Keyboard first.** Every dialog supports `Ctrl+S` to save and `Esc` to close/cancel.

## Where this applies today

The reference implementation is **User Management** (`_userDefinition` in `lib/ui/desktop_shell.dart`), rendered through the shared `ResourceManagementPage` / `CrudWorkspaceDialog` framework (`lib/ui/resource_management_page.dart`) and the Enterprise component kit (`lib/ui/workspace/enterprise_form_kit.dart`).

Per the current sprint's explicit scope, other modules (Customers, Vendors, Products, Purchases, Inventory, Sales) have **not** been migrated yet and keep their existing bespoke dialogs. See `MIGRATION_GUIDE.md` for how they adopt this system next.

## Related documents

- `COMPONENT_CATALOG.md` — widget-by-widget reference.
- `UX_STANDARDS.md`, `LAYOUT_STANDARDS.md`, `FORM_STANDARDS.md`, `GRID_STANDARDS.md`, `RESPONSIVE_STANDARDS.md` — detailed standards.
- `REUSABLE_WIDGET_DOCUMENTATION.md` — API reference.
- `DESKTOP_UI_FRAMEWORK.md` — navigation architecture (Phase 1) and index of these documents.
