# Agency Platform Desktop Design System

**Document status:** Official  
**Applies to:** Agency Platform Flutter Desktop application  
**Target platform:** Windows 10 and Windows 11  
**Minimum resolution:** 1366×768  
**Minimum hardware:** Dual-core processor, 8 GB RAM, SSD recommended  
**Audience:** Product designers, Flutter developers, QA engineers, architects, and module owners

---

## Companion UX-1 Desktop Documents

The UX-1 phase added implementation-ready desktop design references under
`desktop/docs`. Use these together with this enterprise baseline:

- `desktop/docs/DESIGN_SYSTEM.md`
- `desktop/docs/DESKTOP_FRAMEWORK.md`
- `desktop/docs/UX_GUIDELINES.md`
- `desktop/docs/COMPONENT_LIBRARY.md`
- `desktop/docs/ICON_GUIDELINES.md`
- `desktop/docs/COLOR_GUIDELINES.md`
- `desktop/docs/DESKTOP_STYLE_GUIDE.md`

---

## Document Purpose

This document is the single source of truth for the visual language, interaction
model, reusable components, accessibility expectations, and implementation
rules of the Agency Platform desktop application.

The standards are normative. New screens and modules must follow them unless an
approved architecture decision explicitly documents an exception. The design
system exists to ensure that users can move between Administration, Sales,
Inventory, Accounting, and future ERP modules without relearning navigation,
forms, tables, dialogs, or feedback behavior.

Agency Platform is a presentation layer. Business rules, authorization
decisions, validation authority, calculations, and persistence remain in the
FastAPI backend. The desktop communicates only through REST APIs.

---

## 1. Design Philosophy

Agency Platform should feel calm, dependable, efficient, and familiar to
business users who may spend an entire working day in the application.

The experience draws inspiration from modern enterprise products such as
Microsoft 365, Azure Portal, JetBrains IDEs, SAP Fiori, and Atlassian
Administration without copying their visual identity. The intended character
is:

- **Professional:** suitable for financial and operational work.
- **Information-dense:** able to display business data without feeling crowded.
- **Predictable:** identical actions behave identically across modules.
- **Forgiving:** user input survives recoverable errors.
- **Fast:** common work requires few clicks and minimal waiting.
- **Scalable:** the same patterns support simple masters and complex documents.
- **Accessible:** readable, keyboard-friendly, and theme-aware.

Visual decoration must never compete with business information. Clarity and
task completion take priority over novelty.

---

## 2. Design Principles

1. **Consistency over customization.** Reuse established components before
   inventing module-specific variants.
2. **Backend authority.** The UI may guide users, but backend responses remain
   authoritative for validation, permissions, and business outcomes.
3. **Permission-driven presentation.** Widgets check permissions through the
   centralized permission service and never check role names directly.
4. **Progressive disclosure.** Grids show essential data, summary panels show
   quick context, and workspace dialogs show complete records.
5. **Preserve context.** Navigation, active firm, filters, selections, and form
   input should remain stable whenever safe.
6. **Desktop-first efficiency.** Optimize for keyboard, pointer, large tables,
   multi-step forms, and resizable windows.
7. **Responsive within desktop constraints.** Layouts adapt from 1366×768
   upward without becoming mobile-style interfaces.
8. **State must be visible.** Loading, saving, disabled, selected, warning, and
   error states must never be ambiguous.
9. **Safe destructive actions.** Destructive operations require explicit
   confirmation and clear consequences.
10. **Performance is part of usability.** Avoid unnecessary rebuilds, duplicate
    requests, unbounded widgets, and expensive visual effects.

---

## 3. Visual Identity

The visual identity combines neutral surfaces, a restrained accent color,
legible typography, consistent iconography, and moderate density.

### Identity characteristics

| Characteristic | Standard | Why |
| --- | --- | --- |
| Surface style | Clean, layered, low-noise | Keeps attention on business data |
| Color usage | Neutral-first with semantic accents | Improves scanning and reduces fatigue |
| Shape | Modest rounding, not pill-heavy | Feels professional and space-efficient |
| Typography | Clear Windows-native sans serif | Maximizes readability and familiarity |
| Density | Compact but touch-safe | Supports data-heavy workflows |
| Motion | Brief and functional | Communicates state without slowing work |

Brand expression belongs primarily in the login experience, application name,
logo, title bar, and accent seed. Operational screens remain consistent across
white-label deployments.

---

## 4. Branding Guidelines

Branding must be configuration-driven. White-label deployments must not require
source-code changes.

### Configurable branding fields

- Application name
- Window title
- Product name
- Company name
- Logo path
- Splash image path
- Version
- Support email
- Support website
- Copyright text
- Login background color
- Login accent color

### Usage guidelines

- Use the configured application name in the shell and login experience.
- Use the configured window title for the native desktop window.
- Show the version in the status area or About experience.
- Keep logos aspect-ratio safe with `BoxFit.contain`.
- Provide transparent-background SVG or high-resolution PNG assets.
- Do not place tenant logos inside operational data tables.

### Do

- Validate branding configuration and fall back to safe defaults.
- Maintain sufficient contrast when accepting custom accent colors.
- Provide a neutral fallback when an asset is missing.

### Do not

- Hardcode customer names, logos, support addresses, or colors.
- stretch, crop, or distort logos.
- Allow branding colors to override semantic error or warning meanings.

### Future extensibility

The branding contract may later include favicon-equivalent assets, report
headers, invoice branding, login illustrations, and tenant-specific legal text.
These additions must remain configuration-driven.

---

## 5. Color Palette

All colors must be referenced through semantic design tokens or the active
Flutter `ColorScheme`. Raw color values are permitted only inside the centralized
design-token package.

### Core light palette

| Token | Recommended HEX | Use |
| --- | --- | --- |
| `primary` | `#155EEF` | Primary actions, selected navigation, focus accents |
| `primaryHover` | `#0F4FD1` | Pointer hover on primary actions |
| `primaryPressed` | `#0B3FA8` | Pressed primary actions |
| `primaryContainer` | `#E8F0FF` | Selected or emphasized containers |
| `surface` | `#FFFFFF` | Cards, dialogs, grids |
| `surfaceCanvas` | `#F6F8FC` | Application workspace background |
| `surfaceMuted` | `#EEF2F7` | Status bars, headers, subtle grouping |
| `border` | `#D7DEE8` | Standard borders and dividers |
| `borderStrong` | `#AAB4C3` | Focused or emphasized boundaries |
| `textPrimary` | `#172033` | Primary body and heading text |
| `textSecondary` | `#526079` | Labels, descriptions, metadata |
| `textDisabled` | `#8B96A8` | Disabled controls |

### Semantic palette

| Meaning | Foreground | Container | Use |
| --- | --- | --- | --- |
| Success | `#147D45` | `#E6F6ED` | Saved, active, completed |
| Warning | `#B54708` | `#FFF3E0` | Attention, expiring, partial risk |
| Error | `#B42318` | `#FDECEC` | Validation, failed actions, destructive states |
| Information | `#175CD3` | `#EAF2FF` | Neutral system information |
| Pending | `#6941C6` | `#F2ECFF` | Queued, awaiting review |

### Dark palette

| Token | Recommended HEX |
| --- | --- |
| `primary` | `#6EA8FE` |
| `surfaceCanvas` | `#111827` |
| `surface` | `#1B2433` |
| `surfaceMuted` | `#263244` |
| `border` | `#3C495C` |
| `textPrimary` | `#F4F7FB` |
| `textSecondary` | `#B8C2D1` |

### Rules

- Never use color as the only indicator of meaning; pair it with text or icons.
- Error red is reserved for errors and destructive actions.
- Success green is reserved for successful or healthy states.
- Verify text contrast against WCAG AA targets.
- Grid row selection must remain visible in every theme.

---

## 6. Typography Standards

### Font family

Use the platform-appropriate sans-serif stack:

```text
Segoe UI, Inter, Roboto, Arial, sans-serif
```

Segoe UI is preferred on Windows because it is familiar, optimized for the
platform, and legible at compact desktop sizes.

### Type scale

| Token | Size | Weight | Typical use |
| --- | ---: | ---: | --- |
| `displaySmall` | 32 | 600 | Rare landing or major summary title |
| `headlineLarge` | 28 | 600 | Top-level workspace title |
| `headlineMedium` | 24 | 600 | Module title |
| `titleLarge` | 20 | 600 | Dialog and card title |
| `titleMedium` | 16 | 600 | Section title |
| `bodyLarge` | 16 | 400 | Prominent body content |
| `bodyMedium` | 14 | 400 | Default UI text |
| `bodySmall` | 12 | 400 | Metadata and supporting text |
| `labelLarge` | 14 | 600 | Buttons and strong labels |
| `labelMedium` | 12 | 600 | Field labels and compact headers |

### Guidelines

- Use sentence case, not title case, for labels and buttons.
- Use tabular numerals for financial and quantity columns where available.
- Right-align numeric values in data grids and reports.
- Avoid all-caps except stable technical identifiers.
- Do not use font size alone to establish hierarchy; combine size, weight, and
  spacing.

---

## 7. Iconography Standards

Use one icon family consistently. Flutter Material Symbols or Material Icons
are the default.

### Rules

- Standard action icons: 20–24 px.
- Navigation icons: 22–24 px.
- Empty-state icons: 40–56 px.
- Pair unfamiliar icons with text.
- Every icon-only button requires a tooltip and semantic label.
- Use outlined icons for neutral actions and filled emphasis sparingly.
- Preserve established meanings: plus for create, pencil for edit, eye for
  view, trash for delete, refresh for reload, filter for filters.

### Do not

- Mix unrelated icon families in one surface.
- Use decorative icons in dense grids.
- reuse an icon for conflicting actions.
- rely on color alone to distinguish icon meaning.

### Future extensibility

`app_icons.dart` should expose semantic aliases such as `AppIcons.salesOrder`
rather than requiring modules to choose raw icon names independently.

---

## 8. Application Shell Layout

The application shell is permanent after authentication and must not be
recreated during normal module navigation.

```text
+-----------------------------------------------------------------------+
| Application Header: route history | module | firm | notices | theme  |
+----------------------+------------------------------------------------+
|                      |                                                |
| Sidebar Navigation   | Workspace                                      |
|                      |                                                |
|                      |                                                |
|                      |                                                |
+----------------------+------------------------------------------------+
| Application Status: active firm | server | company | version          |
+-----------------------------------------------------------------------+
```

### Purpose

Provide stable navigation, firm context, application identity, global status,
and workspace hosting.

### Usage guidelines

- Keep the sidebar and header mounted while switching modules.
- Render feature content only inside the workspace area.
- Preserve current route, selected tab, and active firm.
- Avoid placing feature-specific buttons in the global shell.

### Do not

- Recreate the shell for every route.
- place business forms directly in the shell.
- allow a feature to bypass the shared navigation or status areas.

---

## 9. Header Design

The header contains global context, not feature-specific toolbars.

### Required content

- Back and forward navigation
- Current module name
- Active firm or firm switcher
- Notification indicator
- Theme selector
- Optional user/account menu

### Dimensions

- Recommended height: 56–64 px.
- Horizontal padding: 16–24 px.
- Use a subtle bottom divider rather than a heavy shadow.

### Best practices

- Show a firm dropdown only when the user has more than one assigned firm.
- For a single-firm user, show the firm name without a switch affordance.
- Keep notification indicators understandable with tooltips.
- Truncate long firm names safely.

---

## 10. Sidebar Navigation

Navigation is generated from backend permission claims through the centralized
permission service.

### Standard module order

1. Dashboard
2. Administration
3. Masters
4. Sales
5. Purchases
6. Inventory
7. Accounting
8. Reports
9. Licensing
10. Settings

### Guidelines

- Width: approximately 232–256 px on wide layouts.
- Use icon + label.
- Highlight exactly one selected module.
- Hide unauthorized modules rather than displaying unusable destinations.
- Keep unavailable future features visibly marked only when product strategy
  requires discovery; otherwise hide them.
- Place sign-out and secondary global controls at the bottom.

### Do not

- Check roles in navigation widgets.
- reorder modules between sessions without a product requirement.
- place record-level actions in navigation.

---

## 11. Workspace Layout

Every feature workspace uses the same vertical hierarchy:

```text
Workspace
└── Column
    ├── Breadcrumbs
    ├── Module title and description
    ├── Tabs
    ├── Toolbar and search/filter controls
    ├── 8 px gap
    ├── Expanded
    │   └── Row
    │       ├── Expanded data grid/content
    │       ├── 16 px gap
    │       └── Quick summary panel
    └── Status bar
```

### Purpose

Guarantee predictable placement and bounded layout behavior across every
management module.

### Rules

- Header, tabs, toolbar, search, and status remain fixed.
- Only grids, details, long forms, and reports scroll.
- Never wrap an entire management page in `SingleChildScrollView`.
- The main content row must occupy remaining height with `Expanded`.
- Summary panels must scroll internally and must not determine page height.

---

## 12. Breadcrumb Standards

Breadcrumbs communicate workspace hierarchy, not browser history.

### Format

```text
Workspace > Administration > Users
```

### Guidelines

- Use concise nouns.
- Include no more than four visible levels.
- The final item is current and non-interactive.
- Prior items may become interactive when stable routes exist.
- Use chevrons as separators.

### Do not

- repeat the application name.
- include record identifiers unless the user is inside a record workspace.
- use breadcrumbs as the only navigation method.

---

## 13. Toolbar Standards

### Standard order

```text
New | View | Edit | Delete | Refresh | Import | Export | Print | Settings
```

Only relevant and authorized actions are visible.

### Purpose

Provide consistent record-level actions across all management screens.

### Guidelines

- **New** is the primary filled action.
- Neutral actions use icon buttons or outlined buttons.
- Destructive actions use clear labels and confirmation.
- Disabled actions must explain requirements through tooltips where useful.
- Toolbar permissions must be checked through the permission service.

### Do

- Keep ordering stable.
- disable actions requiring a selection until a row is selected.
- prevent duplicate action execution while an operation is pending.

### Do not

- create module-specific toolbar arrangements without justification.
- hide Refresh when data can become stale.
- use icon-only actions without tooltips.

---

## 14. Search & Filter Standards

### Search

- Place search before filters.
- Recommended maximum width: 320–360 px.
- Include a search icon and descriptive hint.
- Execute on Enter and explicit search action.
- Preserve the term when paging or opening a dialog.
- Reset pagination to the first page when search criteria change.

### Filters

- Place common filters inline with search.
- Use a collapsible filter panel for advanced criteria.
- Show an active-filter count.
- Provide **Clear filters** when any filter is active.
- Distinguish applied values from unsaved filter edits.

### Do not

- issue a request for every keystroke without appropriate debounce.
- silently discard filters during refresh.
- put dozens of controls in the fixed toolbar row.

---

## 15. Data Grid Standards

### Purpose

Display searchable, sortable, paginated operational data while preserving the
workspace height.

### Required behavior

- Occupy all remaining vertical space.
- Scroll vertically and horizontally inside the grid.
- Never determine the page height.
- Keep headers understandable and stable.
- Support row selection.
- Preserve selection when the record remains in the result set.
- Reset internal pagination when query or page offset resets.

### Column guidelines

- Place primary identifier and name columns first.
- Right-align numbers, currency, and quantities.
- Use consistent date and time formatting from user preferences.
- Truncate long text with tooltips.
- Keep actions out of cells when toolbar actions are sufficient.
- Avoid more than 8–10 default visible columns; support future column settings.

### Do

- Use server-side pagination for large data sets.
- show total record count.
- make selected rows visually distinct in every theme.
- use semantic status labels.

### Do not

- nest the entire page inside grid scrolling.
- render thousands of records without pagination or virtualization.
- place full forms inside table rows.
- allow a table to create vertical `RenderFlex` overflow.

### Future extensibility

The grid contract should support saved views, column visibility, column order,
multi-sort, export, grouping, totals, inline status chips, and keyboard row
navigation without changing the surrounding workspace.

---

## 16. Dashboard Card Standards

Dashboard cards summarize information; they do not replace management screens.

### Card anatomy

- Title
- Primary value
- Optional trend or status
- Supporting label
- Optional navigation action

### Dimensions and layout

- Use responsive grid/wrap layouts.
- Minimum practical width: 220 px.
- Keep heights consistent within a row.
- Use modest elevation and a clear border in high-contrast mode.

### Do

- show values the user has permission to access.
- use concise, meaningful labels.
- provide a clear destination when a card is clickable.

### Do not

- overload cards with complete tables.
- expose unauthorized counts.
- use unexplained red/green trends.

---

## 17. Form Design Standards

### Purpose

Enable accurate, efficient data entry while reducing errors and cognitive load.

### Layout

- Use the Workspace Dialog for create, view, and edit.
- Group related fields into named sections or tabs.
- Use one logical reading direction, top-to-bottom and left-to-right.
- Recommended content width: up to 1100 px.
- Prefer one column for complex fields and two columns only for short,
  naturally paired values.
- Long forms scroll internally.

### Behavior

- Preserve all entered values after API or validation failures.
- Disable duplicate submission while saving.
- Keep the dialog open when save fails.
- Close only after successful save or explicit cancellation.
- Mark required fields consistently.
- Provide sensible defaults without hiding important consequences.

### Do not

- place business logic in widgets.
- reset the form after a failed request.
- use placeholder text as the only label.
- make users re-enter unchanged information.

---

## 18. Field Validation Standards

Validation occurs at two levels:

1. **Client guidance:** required fields, basic format, obvious constraints.
2. **Backend authority:** business rules, uniqueness, permissions, and
   cross-entity validation.

### Error presentation

- Show field errors beside the relevant field.
- Show a concise form-level banner for non-field or general failures.
- Move focus to the first invalid field when practical.
- Keep invalid values visible for correction.
- Use direct language: “Email address is required,” not “Invalid input.”

### Do

- map structured API validation details to field keys.
- clear stale field errors when the user edits the affected value.
- distinguish warnings from blocking errors.

### Do not

- close the dialog after validation failure.
- show only a generic toast when field-level information exists.
- duplicate complex backend business rules in Flutter.

---

## 19. Workspace Dialog Standards (Create/View/Edit)

All management dialogs use the shared CRUD Workspace Dialog framework.
Module-specific dialog implementations are prohibited.

### Size and placement

- Centered in the application window.
- Approximately 85–90% of available width and height.
- Current recommended target: 88%.
- Minimum outer inset: 24 px.
- Resize proportionally with the application window.
- Content scrolls internally; the dialog itself must not overflow.

### Shared modes

| Mode | Fields | Footer | Save behavior |
| --- | --- | --- | --- |
| Create | Empty/default values, editable | Cancel, Save | Creates record |
| View | Populated, read-only | Close | No mutation |
| Edit | Populated, editable as permitted | Cancel, Save | Updates record |

### Required anatomy

```text
+------------------------------------------------------------------+
| Icon | Entity title | mode description                       [X] |
+------------------------------------------------------------------+
| General | Address | Security | Documents | Audit                 |
+------------------------------------------------------------------+
|                                                                  |
| Internally scrolling form page                                   |
|                                                                  |
+------------------------------------------------------------------+
|                                              Cancel       Save   |
+------------------------------------------------------------------+
```

### Interaction rules

- `Esc` closes unless saving.
- `Ctrl+S` saves in Create/Edit and does nothing in View.
- Closing is disabled while saving.
- Save button shows progress and prevents duplicate submission.
- Tabs preserve field values and validation state.
- API errors preserve all user input.
- If entity creation succeeds but assignment saving fails, retry assignments
  against the created record instead of creating a duplicate.

### Future extensibility

Future dialogs may add tabs such as General, Address, Contacts, Security,
Documents, Audit, Payments, Delivery, Tax, or Workflow while retaining the
same header, footer, shortcuts, validation, and sizing.

---

## 20. Button Standards

| Type | Use | Example |
| --- | --- | --- |
| Primary filled | Main positive action | Save, Sign in, Create |
| Tonal | Secondary emphasized action | Edit, Apply filters |
| Outlined | Neutral alternative | Cancel, Close, View details |
| Text | Low-emphasis action | Reset, Learn more |
| Icon | Compact familiar action | Refresh, Back, Forward |
| Destructive | Irreversible or high-risk action | Delete, Revoke |

### Rules

- Use verb-first labels.
- One primary action per focused surface.
- Minimum practical target: 36–40 px high.
- Show progress inside the action that initiated work.
- Disabled buttons must remain visually recognizable.
- Do not use red for ordinary Cancel.

---

## 21. Status Indicators

Status indicators communicate business or system state using text, icon, and
color.

### Recommended states

- Active
- Inactive
- Draft
- Pending
- Approved
- Rejected
- Completed
- Cancelled
- Locked
- Expired
- Failed

### Guidelines

- Use consistent wording across modules.
- Use compact chips for grids and summaries.
- Include accessible text.
- Reserve flashing or animated indicators for exceptional live conditions.

---

## 22. Notification Standards

Supported notification types:

- Success
- Information
- Warning
- Error

### Usage

| Type | Use |
| --- | --- |
| Success | Completed user-initiated action |
| Information | Neutral state or helpful context |
| Warning | Recoverable risk or attention required |
| Error | Failed action requiring awareness |

### Rules

- Use consistent banners or snackbars through the notification service.
- Keep messages concise and actionable.
- Do not expose stack traces or internal exception details.
- Persistent issues belong in the workspace, not only transient notifications.
- Avoid success notifications for passive data loading.

---

## 23. Dialog Standards

Use the Workspace Dialog for CRUD forms. Use smaller standard dialogs only for:

- Confirmation
- Short choices
- Error details
- Loading that must block interaction
- Simple acknowledgements

### Confirmation dialogs

- State the action in the title.
- Explain the consequence.
- Use explicit labels such as **Delete user**, not **Yes**.
- Place Cancel before the confirming action.
- Use destructive styling only when appropriate.

### Do not

- use a small alert dialog for complex forms.
- stack dialogs more than one level deep.
- dismiss a saving dialog through barrier clicks.

---

## 24. Empty State Standards

An empty state must explain:

1. What is empty.
2. Why it may be empty.
3. What the user can do next, if authorized.

### Examples

- “No users found. Try a different search or create a new user.”
- “No firm is assigned to this account. Contact an administrator.”
- “No transactions match the selected date range.”

### Do

- use a restrained icon.
- distinguish “no data” from “no search results.”
- show a create action only when permitted.

### Do not

- show a blank white area.
- imply an error when the state is valid.

---

## 25. Loading State Standards

### Initial loading

Use a centered progress indicator or skeleton inside the content region.

### Refreshing existing data

Keep existing data visible where safe and show a lightweight refreshing status.

### Saving

- Disable duplicate submission.
- Show progress in the Save button.
- Prevent close while the mutation is pending.

### Long-running operations

Show progress, current stage when available, and a safe cancellation path only
when backend semantics support cancellation.

### Do not

- block the entire application for a local workspace refresh.
- replace loaded content with a blank screen unnecessarily.

---

## 26. Footer / Status Bar Design

### Workspace status bar

Shows:

- Total records
- Selected record count
- Refreshing or contextual status

### Application status bar

May show:

- Active firm
- Server address or environment
- Company
- Application version
- Connectivity state

### Guidelines

- Keep height compact, approximately 28–36 px.
- Use muted surfaces.
- Do not place primary actions in status bars.
- Avoid exposing sensitive server details in production builds unless required.

---

## 27. Theme Architecture

Agency Platform supports:

1. Light
2. Dark
3. Blue
4. Green
5. High Contrast

### Architecture rules

- Themes are centralized and selected at runtime.
- Every module inherits the active theme automatically.
- Theme choice is cached locally and synchronized with backend preferences.
- Components consume semantic colors from `ThemeData` and design tokens.
- No feature module defines an independent theme.

### Theme intent

| Theme | Intent |
| --- | --- |
| Light | Default general office environment |
| Dark | Low-light or user-preference environment |
| Blue | Branded professional alternative |
| Green | Branded operational alternative |
| High Contrast | Maximum differentiation and accessibility |

### High-contrast requirements

- Strong visible borders.
- Clear focus indicators.
- No low-opacity text.
- Selected and disabled states remain distinguishable.
- Do not rely on elevation alone.

---

## 28. Accessibility Guidelines

- Target WCAG 2.1 AA contrast.
- Support keyboard-only operation.
- Provide visible focus indicators.
- Give icon buttons tooltips and semantic labels.
- Preserve logical focus order.
- Do not use color as the sole status cue.
- Ensure text remains usable with Windows text scaling.
- Use meaningful control labels for screen readers.
- Avoid time-limited actions unless users can extend them.
- Respect reduced-motion preferences when available.
- Ensure disabled controls remain understandable.

Accessibility is a release requirement, not a later enhancement.

---

## 29. Responsive Desktop Behaviour

### Required reference sizes

- 1366×768
- 1600×900
- 1920×1080
- Maximized window
- Restored and resized window

### Layout behavior

- Wide shell: persistent sidebar.
- Narrow desktop shell: drawer may replace persistent sidebar.
- Toolbar/search controls may wrap vertically below approximately 900 px
  workspace width.
- Data grid remains primary and scrolls internally.
- Quick summary panel remains bounded and may use a smaller width.
- Workspace dialogs stay proportional with fixed outer insets.

### Rules

- No yellow/black overflow indicators.
- No clipped controls.
- No full-page scrolling on management screens.
- Avoid fixed content heights except stable shell dimensions.
- Use `Expanded`, `Flexible`, `LayoutBuilder`, and bounded scrolling
  deliberately.

---

## 30. Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+S` | Save current Create/Edit workspace dialog |
| `Esc` | Close current dialog when not saving |
| `Enter` | Submit search or activate focused default action where safe |
| `Tab` / `Shift+Tab` | Move focus forward/backward |
| `Alt+Left` | Navigate back when supported |
| `Alt+Right` | Navigate forward when supported |
| `Ctrl+F` | Focus workspace search in future implementations |
| `F5` | Refresh current workspace in future implementations |
| `Delete` | Never delete immediately; may open confirmation when explicitly enabled |

Shortcuts must never bypass permissions, confirmation, or backend validation.

---

## 31. User Experience Guidelines

- Prefer recognition over recall.
- Keep labels aligned with business terminology.
- Preserve the user’s active firm and workspace.
- Make destructive consequences explicit.
- Provide immediate feedback after user actions.
- Avoid surprise navigation after saving.
- Do not clear search or filters without user intent.
- Use progressive disclosure for advanced settings.
- Make defaults safe and reversible.
- Explain unavailable actions rather than failing silently.

---

## 32. Animation Guidelines

Animations must communicate state, not decorate routine work.

### Recommended durations

| Motion | Duration |
| --- | ---: |
| Hover/focus transition | 80–120 ms |
| Small visibility change | 120–180 ms |
| Panel/dialog transition | 180–240 ms |
| Theme transition | 200–300 ms |

### Rules

- Use standard easing.
- Avoid large parallax, bounce, or continuous animation.
- Keep data-grid updates stable; do not animate every row.
- Progress indicators are permitted for indeterminate work.
- Respect reduced-motion settings when available.

---

## 33. Design Tokens

Design tokens are named, centralized values representing visual decisions.

### Token categories

- Colors
- Typography
- Spacing
- Radius
- Dimensions
- Shadows/elevation
- Icons
- Motion
- Breakpoints
- Density

### Naming examples

```text
color.surface.canvas
color.status.error
space.3
radius.card
dimension.sidebar.width
motion.duration.short
```

Widgets consume semantic tokens. They must not depend directly on raw values.

---

## 34. Spacing System

Use a 4 px base unit.

| Token | Value | Typical use |
| --- | ---: | --- |
| `space0` | 0 | No spacing |
| `space1` | 4 | Tight icon/text gap |
| `space2` | 8 | Standard compact gap |
| `space3` | 12 | Field or toolbar gap |
| `space4` | 16 | Standard component padding |
| `space5` | 20 | Medium section spacing |
| `space6` | 24 | Workspace/dialog padding |
| `space8` | 32 | Major section separation |
| `space10` | 40 | Large empty-state spacing |
| `space12` | 48 | Major page separation |

### Rules

- Use token values only.
- Prefer 8, 12, 16, and 24 px for common layouts.
- Avoid arbitrary values such as 13 or 19 px.
- Reduce spacing before reducing typography at constrained sizes.

---

## 35. Border Radius Standards

| Token | Value | Use |
| --- | ---: | --- |
| `radiusSmall` | 4 | Compact chips, small fields |
| `radiusMedium` | 8 | Inputs, buttons, banners |
| `radiusLarge` | 12 | Cards, panels, dialogs |
| `radiusXLarge` | 16 | Special large surfaces only |
| `radiusFull` | 999 | Status chips and avatars only |

Enterprise surfaces should not appear excessively rounded. Use the same radius
for equivalent component types.

---

## 36. Shadow & Elevation Standards

| Level | Use |
| --- | --- |
| 0 | Canvas, embedded areas |
| 1 | Cards and grid surfaces |
| 2 | Menus and floating controls |
| 3 | Standard dialogs |
| 4 | Workspace dialogs or critical overlays |

### Rules

- Prefer borders and surface contrast over heavy shadows.
- Dark and high-contrast themes require border reinforcement.
- Never use elevation to communicate semantic status.
- Avoid multiple nested shadows.

---

## 37. Component Naming Standards

Use names that communicate role, not appearance.

### Preferred

- `ManagementWorkspaceLayout`
- `WorkspaceToolbar`
- `EnterpriseDataGrid`
- `QuickSummaryPanel`
- `CrudWorkspaceDialog`
- `CrudWorkspaceHeader`
- `CrudFormPage`
- `CrudWorkspaceFooter`
- `NotificationService`

### Avoid

- `BlueButton`
- `BigPopup`
- `Screen2`
- `CustomWidget`
- `TempPanel`

### Rules

- Prefix globally reusable components with `App`, `Workspace`, or a clear
  domain-neutral capability name.
- Feature widgets may use feature names but must compose shared primitives.
- Enums describe behavior, such as `CrudDialogMode`, not visual implementation.

---

## 38. Reusable Widget Library

The shared library should include:

| Component | Responsibility |
| --- | --- |
| Application shell | Permanent navigation and global context |
| Module workspace frame | Header, breadcrumbs, tabs, bounded content |
| Management workspace layout | Fixed controls, grid/summary row, status |
| Workspace toolbar | Standard authorized actions |
| Search/filter panel | Query controls |
| Enterprise data grid | Bounded scrolling, selection, paging, sorting |
| Quick summary panel | Concise selected-record context and actions |
| CRUD workspace dialog | Create/View/Edit container |
| CRUD header/form/footer | Consistent dialog composition |
| Confirmation dialog | Safe confirmation |
| Loading dialog | Blocking operation feedback |
| Error dialog | Detailed actionable errors |
| Notification service | Success/warning/error/information feedback |
| Empty/loading/error states | Consistent content states |
| Pagination control | Standard paging |
| Status indicators | Semantic business states |

### Rule

Before adding a new widget, search the reusable library. Extend an existing
component when the interaction is the same. Do not fork shared components into
feature folders.

---

## 39. Folder Structure Recommendation

```text
lib/
├── core/
│   ├── design/
│   │   ├── app_theme.dart
│   │   ├── app_colors.dart
│   │   ├── app_typography.dart
│   │   ├── app_spacing.dart
│   │   ├── app_radius.dart
│   │   ├── app_icons.dart
│   │   ├── app_shadows.dart
│   │   ├── app_dimensions.dart
│   │   └── design_tokens.dart
│   ├── api/
│   ├── auth/
│   ├── branding/
│   ├── dialogs/
│   ├── navigation/
│   ├── notifications/
│   ├── permissions/
│   ├── preferences/
│   ├── routing/
│   ├── services/
│   ├── theme/
│   ├── utilities/
│   └── workspace/
├── features/
│   ├── dashboard/
│   ├── administration/
│   ├── masters/
│   ├── sales/
│   ├── purchase/
│   ├── inventory/
│   ├── accounting/
│   ├── reports/
│   ├── licensing/
│   └── settings/
└── shared/
```

### Design package responsibilities

| File | Responsibility |
| --- | --- |
| `app_theme.dart` | Builds complete `ThemeData` variants |
| `app_colors.dart` | Semantic palette definitions and theme mappings |
| `app_typography.dart` | Font families, weights, sizes, and text themes |
| `app_spacing.dart` | 4 px spacing scale |
| `app_radius.dart` | Standard radius values |
| `app_icons.dart` | Semantic icon aliases |
| `app_shadows.dart` | Elevation and shadow definitions |
| `app_dimensions.dart` | Shell, panel, grid, dialog, and breakpoint dimensions |
| `design_tokens.dart` | Stable public export/aggregation of design tokens |

Feature packages contain feature-specific composition and models, not copies of
shared visual foundations.

---

## 40. UI Consistency Rules

The following rules are mandatory:

- Never hardcode colors outside the design package.
- Never hardcode spacing outside token definitions.
- Never hardcode font sizes in feature widgets.
- Never duplicate an existing reusable widget.
- All dialogs use the appropriate shared dialog framework.
- All management forms use the CRUD Workspace Dialog.
- All forms preserve input after validation or API errors.
- All tables use the shared management layout and data-grid standards.
- All modules inherit the active theme.
- Widgets never check roles directly.
- Permission decisions go through the permission service.
- UI and business logic remain separate.
- Desktop remains presentation-only and never accesses PostgreSQL directly.
- API errors are surfaced explicitly; failures are not silently ignored.
- Every asynchronous mutation prevents duplicate submission.

---

## 41. Future Module Design Guidelines

### Login

- Focus on identity, server selection, branding, and recovery guidance.
- Keep the form narrow and centered.
- Never store passwords.
- Clearly show connection and authentication failures.

### Dashboard

- Use permission-aware summary cards.
- Prioritize actionable operational information.
- Allow future configurable layouts without module-specific styling.

### Administration

- Use shared management workspaces for users, roles, permissions, and
  assignments.
- Clearly distinguish system-managed records from editable records.

### Firms

- Use tabs such as General, Address, Contacts, Financial, and Audit.
- Keep active/inactive state prominent.

### Customers and Vendors

- Reuse identical master-data patterns.
- Typical tabs: General, Addresses, Contacts, Tax, Credit, Documents, Audit.

### Products, Categories, and Units

- Prioritize code, name, status, pricing, tax, inventory settings, and units.
- Product images are secondary to operational information.

### Inventory

- Use grids for stock views and workspace dialogs for adjustments/transfers.
- Clearly distinguish available, reserved, damaged, and in-transit quantities.

### Sales and Purchase

- Use document workspaces with header, line-item grid, totals, status, and
  workflow actions.
- Avoid forcing complex documents into a generic narrow form.
- Support draft preservation and explicit posting/approval states.

### Accounting

- Favor precision, auditability, and keyboard efficiency.
- Align amounts consistently and display debit/credit semantics clearly.
- Destructive changes to posted records require strong warnings.

### Reports

- Use a fixed parameter region and internally scrolling report canvas.
- Support export and print consistently.
- Clearly display generated-at time, firm, period, and filters.

### Licensing

- Present machine, activation, expiry, and status information clearly.
- Do not expose sensitive license secrets.

### Settings

- Group settings by stable categories.
- Distinguish user preferences, firm settings, and platform settings.
- Warn when changes affect all users or require restart.

---

## 42. White-label / Branding Support

White-label deployments may change branding but not interaction semantics.

### Configurable

- Names
- Logo and splash assets
- Company and support information
- Login colors
- Primary theme seed within accessibility limits

### Fixed

- Error/warning/success meanings
- Workspace architecture
- Dialog behavior
- Permission behavior
- Accessibility requirements
- Core spacing and interaction patterns

Brand customization must not fragment the product into incompatible user
experiences.

---

## 43. Performance Considerations

- Avoid unnecessary widget rebuilds; listen only to relevant state.
- Keep the application shell mounted.
- Deduplicate simultaneous token refreshes and API calls.
- Use server-side pagination and filtering.
- Do not render unbounded tables.
- Cache stable lookup data where appropriate and invalidate deliberately.
- Keep animations short and lightweight.
- Avoid large images in operational screens.
- Dispose controllers, focus nodes, and subscriptions.
- Use lazy loading for expensive tabs when it does not lose form state.
- Preserve loaded data during refresh when safe.
- Test on Windows systems with 8 GB RAM.

---

## 44. Developer Guidelines

### Before implementation

1. Identify the existing workspace and reusable components.
2. Define required permissions.
3. Confirm REST contracts and backend validation.
4. Choose the standard screen pattern.
5. Define loading, empty, error, and unauthorized states.

### During implementation

- Compose design-system components.
- Use centralized tokens.
- Keep API/state logic outside visual primitives.
- Preserve values after failures.
- Add keyboard and accessibility behavior.
- Use stable keys when stateful controls must reset.

### Review requirements

- Verify all supported themes.
- Verify 1366×768, 1600×900, and 1920×1080.
- Verify keyboard-only operation.
- Verify permission visibility.
- Verify long text, empty data, large data, and API errors.
- Verify no `RenderFlex` overflow.

---

## 45. Example Screen Wireframes

### Management workspace

```text
+----------------------------------------------------------------------------+
| Workspace > Administration > Users                                         |
| Users                                                                      |
| Manage platform user accounts and assignments.                             |
| [Users] [Roles] [Permissions] [User-Firm Assignments]                      |
+----------------------------------------------------------------------------+
| [Search users________________]        [New] [View] [Edit] [Delete] [Refresh]|
|                                                                            |
| +-----------------------------------------------+  +----------------------+ |
| | Email        Name        Status       ...     |  | Selected User        | |
| |-----------------------------------------------|  |----------------------| |
| | a@x.com      Asha Rao    Active               |  | Name                 | |
| | b@x.com      Ben Shah    Locked               |  | Email                | |
| | ...                                           |  | Status               | |
| |                                               |  | Roles                | |
| |                                               |  | Firms                | |
| |                                               |  |                      | |
| |                                               |  | [View Details][Edit] | |
| +-----------------------------------------------+  +----------------------+ |
| 245 records | 1 selected                                      Refreshing... |
+----------------------------------------------------------------------------+
```

### CRUD Workspace Dialog

```text
      +------------------------------------------------------------------+
      | [icon] User Management                                      [X] |
      |        Edit existing record                                      |
      +------------------------------------------------------------------+
      | [General] [Security] [Organization] [Audit]                       |
      +------------------------------------------------------------------+
      |                                                                  |
      |  Full name             [_______________________________]          |
      |  Email                 [_______________________________]          |
      |                                                                  |
      |  Internally scrolling content                                    |
      |                                                                  |
      +------------------------------------------------------------------+
      |                                              [Cancel]    [Save]   |
      +------------------------------------------------------------------+
```

### Transaction document workspace

```text
+----------------------------------------------------------------------------+
| Sales > Sales Orders > SO-2026-00418                                       |
| [Save Draft] [Submit] [Approve] [Print] [Cancel]                           |
+----------------------------------------------------------------------------+
| Customer [____________]  Date [________]  Status [Draft]                    |
| Ship To  [______________________________________________________________]   |
+----------------------------------------------------------------------------+
| Item              Qty        Rate        Tax        Amount                  |
|----------------------------------------------------------------------------|
| Product A          10      125.00      18%       1,475.00                  |
| Product B           2      500.00      18%       1,180.00                  |
+----------------------------------------------------------------------------+
| Notes [________________________________]     Subtotal        2,250.00        |
|                                             Tax               405.00        |
|                                             Total           2,655.00        |
+----------------------------------------------------------------------------+
```

---

## 46. Recommended UI Patterns

| Scenario | Pattern |
| --- | --- |
| Master-data list | Management workspace + grid + quick summary |
| Create/View/Edit master | CRUD Workspace Dialog |
| Complex transaction | Dedicated document workspace |
| Destructive action | Confirmation dialog |
| Short choice | Standard small dialog |
| Global feedback | Notification service |
| Field validation | Inline error + form banner |
| Long report | Fixed parameters + scrollable report canvas |
| Multiple entity aspects | Workspace-dialog tabs |
| Permission restriction | Hide unauthorized navigation/actions |
| No records | Actionable empty state |
| Temporary loading | In-region progress |

---

## 47. Best Practices

- Design the empty, loading, error, and unauthorized states with the main state.
- Keep common actions in predictable locations.
- Prefer explicit labels over clever icons.
- Make status and firm context continuously visible.
- Format values using user preferences.
- Maintain stable selection and navigation state.
- Treat validation messages as part of the form layout.
- Use responsive constraints instead of fixed page heights.
- Test realistic long names, large counts, and translated text.
- Keep every feature visually compatible with all five themes.

---

## 48. Common Mistakes to Avoid

- Hardcoded colors, spacing, font sizes, or radii.
- Role checks inside widgets.
- Full-page `SingleChildScrollView` around management screens.
- Unbounded `DataTable` or `PaginatedDataTable`.
- Narrow popup forms for complex records.
- Separate Create, View, and Edit implementations.
- Clearing form values after API errors.
- Closing dialogs after failed saves.
- Multiple simultaneous Save requests.
- Using snackbars as the only field-validation feedback.
- Inconsistent action order.
- Missing tooltips on icon buttons.
- Unauthorized modules visible through hardcoded menus.
- Silent API failures.
- Direct database access from Flutter.
- Feature-specific theme overrides.
- Excessive shadows, gradients, animation, or decorative color.

---

## 49. Checklist for New Screens

### Architecture

- [ ] Uses REST APIs only.
- [ ] Keeps business logic outside widgets.
- [ ] Uses centralized permission checks.
- [ ] Uses reusable workspace/dialog components.

### Visual system

- [ ] Uses design tokens for color, spacing, typography, radius, and elevation.
- [ ] Works in Light, Dark, Blue, Green, and High Contrast.
- [ ] Uses standard icons and labels.

### Layout

- [ ] Works at 1366×768, 1600×900, and 1920×1080.
- [ ] Has no overflow or clipped controls.
- [ ] Scrolls only approved content areas.
- [ ] Keeps toolbar, search, tabs, and status fixed.

### Interaction

- [ ] Keyboard focus order is logical.
- [ ] Tooltips and semantics exist for icon-only controls.
- [ ] New/View/Edit use the CRUD Workspace Dialog when applicable.
- [ ] Save prevents duplicate submission.
- [ ] Esc and Ctrl+S behave correctly.

### Data and feedback

- [ ] Loading, empty, error, and unauthorized states are defined.
- [ ] API validation maps to fields.
- [ ] User input survives failed saves.
- [ ] Search/filter changes reset paging appropriately.
- [ ] Destructive actions require confirmation.

### Quality

- [ ] No duplicated shared widget.
- [ ] No hardcoded design values.
- [ ] Widget tests cover critical sizing and state behavior.
- [ ] Static analysis passes.
- [ ] Existing navigation and authentication remain intact.

---

## 50. Appendix

### A. Normative language

- **Must / must not:** mandatory requirement.
- **Should / should not:** expected standard; deviations require justification.
- **May:** optional capability that must remain compatible with the system.

### B. Standard dimensions

| Element | Recommended value |
| --- | ---: |
| Application header | 56–64 px |
| Sidebar width | 232–256 px |
| Application status bar | 28–36 px |
| Workspace horizontal padding | 24 px |
| Grid/summary gap | 16 px |
| Quick summary width | 240–320 px |
| Search maximum width | 360 px |
| CRUD workspace dialog | 85–90%, target 88% |
| Dialog outer inset | 24 px |
| Standard row/control height | 36–48 px |

### C. Standard terminology

| Preferred | Avoid |
| --- | --- |
| Firm | Tenant, company account, organization interchangeably |
| User | Operator, login, member interchangeably |
| Role | Profile, group when meaning authorization role |
| Permission | Right, privilege when referring to permission code |
| Workspace Dialog | Big popup, modal screen |
| Quick Summary | Details form |
| Active firm | Current tenant when shown to business users |

### D. Design governance

Changes to shared interaction patterns, token scales, workspace architecture, or
dialog behavior require:

1. A documented user or product need.
2. Review by UI/UX and Flutter architecture owners.
3. Accessibility and theme review.
4. Migration guidance for existing modules.
5. Updates to this document and reusable components.

Feature teams must not introduce a local exception first and document it later.

### E. Final implementation rule

When uncertain, choose the existing shared pattern. Consistency across the ERP
is more valuable than local visual optimization. A user who learns one Agency
Platform module should be able to operate every other module with minimal
additional instruction.
