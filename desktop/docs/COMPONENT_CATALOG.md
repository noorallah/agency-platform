# Component Catalog

All Enterprise components live in `desktop/lib/ui/workspace/enterprise_form_kit.dart` unless noted. They are generic — no component knows about Users, Customers, or any specific module.

| Component | Purpose | Notes |
|---|---|---|
| `EnterpriseSection` | Collapsible group of related fields (replaces tab pages). | `ExpansionTile`-based; forces open when `errorCount > 0`; shows a "Read only" badge for audit-style sections. |
| `EnterpriseValidationSummary` | Top-of-form banner listing every current validation failure. | Shown once, above all sections, inside `CrudFormPage`. |
| `EnterpriseActionBar` | Standard footer: Cancel, Save & New (create only), Save & Close. | Replaces the old `CrudWorkspaceFooter`. |
| `EnterpriseAuditSection` | Read-only key/value grid (Created On, Last Login, etc.). | Used for stand-alone audit displays outside the field-driven dialog. |
| `EnterpriseConfirmationDialog` | `confirmDiscard(context)` — unsaved-changes prompt. | Thin wrapper over the existing `ConfirmationDialog` (`workspace_components.dart`). |
| `AddressRecord` / `EnterpriseAddressEditor` | The Enterprise Address Framework: reusable multi-address list editor (Permanent/Current/Office/Temporary/Other, primary flag). | Canonical shape going forward; Customers/Vendors keep their own address drafts until migrated. |
| `DocumentRecord` / `EnterpriseDocumentSection` | The Enterprise Document Framework: reusable document-metadata list editor (type, reference, notes). | Metadata only — no file upload/storage exists yet. |
| `kEnterpriseAddressTypes` / `kEnterpriseDocumentTypes` | Canonical option lists for the two editors above. | |

## Extended in `resource_management_page.dart`

| Type | Change |
|---|---|
| `FieldKind` (enum) | `text` (default), `date`, `addressList`, `documentList` — selects which Enterprise widget renders a field. |
| `FieldSpec` | New properties: `sectionIcon` (icon shown next to a section title), `kind` (`FieldKind`), `alwaysReadOnly` (renders a static label/value pair regardless of dialog mode — used for audit fields). |
| `CrudWorkspaceDialog` | Renders fields grouped into `EnterpriseSection`s inside one scroll (no more `SegmentedButton`/`IndexedStack` tab switching); tracks a `_dirty` flag and confirms discard on close; supports Save & New for create-mode dialogs. |

## Existing components reused (not duplicated)

| Component | File | Reused for |
|---|---|---|
| `StatusBadge` | `workspace_components.dart` | Section "Read only" tag; entity status badges. |
| `ConfirmationDialog` | `workspace_components.dart` | Backing widget for `EnterpriseConfirmationDialog`. |
| `AttachmentPanel` | `workspace_components.dart` | Read-only display precedent that `EnterpriseDocumentSection` follows visually. |
| `CrudWorkspaceHeader`, `CrudFormPage` | `resource_management_page.dart` | Unchanged dialog chrome (title/close icon, scrollable centered page). |

## Naming convention

New shared, cross-module widgets are prefixed `Enterprise*`. Module-specific widgets (e.g. `CustomerWorkspaceDialog`) are **not** renamed or touched by this sprint.
