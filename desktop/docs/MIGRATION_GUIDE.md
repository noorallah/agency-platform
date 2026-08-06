# Migration Guide (Remaining Modules)

## Current status

Only **User Management** has been migrated to the Enterprise Design System in this sprint. Customers, Vendors, Products, Purchases, Inventory, Sales, and all other modules keep their existing bespoke dialogs and must **not** be changed until this framework is reviewed and approved.

## Why User Management was low-risk to migrate

Users (along with Roles, Permissions, Firms, Business Profiles, UOM, Packaging, and other simple masters) already used the **shared generic CRUD framework** (`ResourceManagementPage<T>` / `CrudWorkspaceDialog` in `lib/ui/resource_management_page.dart`). Refactoring that shared dialog's rendering automatically upgraded every resource built on it — no per-screen changes were required beyond reorganizing `_userDefinition`'s `FieldSpec`s into the new section taxonomy.

Customers, Vendors, Products, and Purchases use **bespoke, hand-rolled tabbed dialogs** (e.g. `CustomerWorkspaceDialog`, `VendorWorkspaceDialog`) that do not go through `CrudWorkspaceDialog`. Migrating them is a larger, per-module effort.

## Steps to migrate a bespoke module

1. **Inventory the module's fields** and map them into the section taxonomy in `FORM_STANDARDS.md` (or a module-appropriate variant — not every module needs Address/Documents/Employment sections).
2. **Prefer moving to `ResourceDefinition`/`FieldSpec`** if the module's dialog is a reasonably standard field list. This gets `EnterpriseSection`, validation summary, action bar, and dirty-tracking for free.
3. **If the module has genuinely custom composite widgets** (e.g. a line-item grid for Purchase Orders) that don't fit `FieldSpec`, keep the custom widget but wrap it in an `EnterpriseSection` and use `EnterpriseActionBar`/`EnterpriseValidationSummary` for the surrounding chrome, so the *shell* is consistent even if one section's content is bespoke.
4. **Reuse, don't re-invent, composite fields.** If a module needs addresses, use `EnterpriseAddressEditor`/`AddressRecord` instead of a new address model. If it needs document metadata, use `EnterpriseDocumentSection`/`DocumentRecord`.
5. **Replace tab strips with sections.** Any `SegmentedButton`/`TabBar` switching between "pages" of the same record must become collapsible `EnterpriseSection`s.
6. **Verify with `flutter analyze` and `flutter test`** after each module migration, and add/update widget tests for the new section-based layout (see `test/app_test.dart` for the User Management dialog test pattern).
7. **Do not migrate more than one module per review cycle** unless explicitly asked — this keeps each change reviewable and reversible.

## Backend considerations when migrating

- Prefer additive, nullable schema changes (see `backend/alembic/versions/20260803_0023_user_profile_enrichment.py` for the pattern used for User profile fields).
- Reuse existing partial-update (`PATCH`) semantics where the module's API already supports them; do not restructure working endpoints to migrate the UI.
- Never let a UI migration change authentication, authorization, or core business logic.

## Open follow-ups for a future sprint

- Normalize Customer/Vendor address handling onto the `AddressRecord`/`EnterpriseAddressEditor` shape.
- Decide whether `EnterpriseDocumentSection` should gain real file upload/storage, and whether that becomes a genuinely shared attachment table (today each module still has its own attachment table).
- Migrate Customers, then Vendors, then Products, each as its own reviewed change.
