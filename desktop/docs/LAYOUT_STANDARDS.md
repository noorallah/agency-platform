# Layout Standards

## Page structure

Every enterprise form dialog uses the same structure, top to bottom:

1. `CrudWorkspaceHeader` — icon, title, mode subtitle, close button.
2. `EnterpriseValidationSummary` — only rendered when there is something to show.
3. A single scrollable column of `EnterpriseSection`s, one per logical group of fields, each independently collapsible.
4. `EnterpriseActionBar` — Cancel / Save & New / Save & Close, pinned at the bottom.

No module may introduce tab bars, `SegmentedButton` section switchers, or a second full-height panel inside a form dialog — sections replace tabs everywhere.

## Section rules

- One `EnterpriseSection` per conceptual group (General Information, Organization, Security, Contact Information, Address, Employment, Documents, Audit Information, ...).
- Sections default to expanded; a section is force-expanded whenever one of its fields has a validation error.
- Read-only/audit sections are marked with the "Read only" badge and never contain editable controls, regardless of dialog mode.
- Keep section field counts reasonable (roughly 3–10 fields); if a section grows much larger, split it into two logically-named sections rather than making one giant one.

## Spacing

- Section cards: 12px bottom margin between sections, 16px horizontal / vertical internal padding.
- Fields inside a section: 12px bottom padding between fields (`EdgeInsets.only(bottom: 12)`), consistent with the existing `_field()` builder.
- Dialog surface: 88% of window width/height, with a `1100px` max content width (`CrudFormPage`) so text fields don't stretch unreadably wide on ultra-wide monitors.

## Ratio target (unchanged from Phase 1)

- Navigation: 15–18% of window width.
- Workspace (including any open dialog): 82–85%.
- No layout may permanently reserve a second navigation-style panel outside the `EnterpriseSidebar`.
