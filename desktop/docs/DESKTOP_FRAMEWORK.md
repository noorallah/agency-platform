# Desktop Framework

This document defines how every Agency Platform ERP module composes the shared
Flutter desktop infrastructure. Business modules must not create alternative
workspace shells, CRUD dialogs, notifications, loading states, or table
interaction patterns.

See also:

- `DESIGN_SYSTEM.md`
- `UX_GUIDELINES.md`
- `COMPONENT_LIBRARY.md`
- `DESKTOP_STYLE_GUIDE.md`

## Public component library

Import the framework barrel:

```dart
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
```

The library provides:

| Component | Responsibility |
| --- | --- |
| `WorkspaceLayout` | Breadcrumb, page header, toolbar, search, filters, content, and status |
| `ModuleWorkspaceFrame` | Module title, tabs, and bounded module content |
| `ManagementWorkspaceLayout` | Search/toolbar, grid, details panel, and workspace status |
| `WorkspaceDialog` | Generic 88% window dialog with tabs, body, footer, loading, and shortcuts |
| `CrudWorkspaceDialog` | Metadata-driven Create/View/Edit forms used by current resources |
| `WorkspaceToolbar` | Stable CRUD action ordering and enabled/visible states |
| `SearchFilterPanel` / `FilterPanel` | Search and basic/advanced filter composition |
| `EnterpriseDataGrid` | Pagination, sorting, selection, double-click, and context actions |
| `StatusBadge` | Standardized status visualization for grids and detail views |
| `SummaryMetricCard` | Reusable metric/summary card for dashboard-style surfaces |
| `ApplicationStatusBar` / `WorkspaceStatusBar` | Global health/context and record status |
| `LoadingOverlay` / `TableLoadingSkeleton` | Page, dialog, table, and background loading |
| `StandardEmptyState` | Typed no-data, no-results, permission, network, firm, and license states |
| `WorkspaceShortcuts` | Permission-safe module shortcut registration |
| `showWorkspaceContextMenu` | Extendable View/Edit/Delete/Copy/Refresh/Export menu |
| `showGlobalSearch` | Ctrl+K search UI contract; no API dependency |
| `GeoAreaPicker` | Where something is, chosen from the shared geography masters: country → state → district → city → postal code → locality, each rung loading when its parent is chosen. `levels` selects which rungs to show. **Use this rather than a fourth copy of the cascade** — customers, vendors, branches and warehouses all carry an address, and the point of structured geography is that they land on the same masters instead of four spellings of "Parrys". It keeps a stored id that is not in the loaded list as an item of its own, because `DropdownButtonFormField` asserts when its value matches no item, and without that a record pointing at a retired place would break the whole form and save as blank |
| `fetchAllPages` / `maxApiPageSize` | Reads every page of a list endpoint, 100 at a time. **Never ask a list endpoint for a larger page**: the cap is enforced, not clamped, and on the routers that build their pagination by hand it comes back as a 500 rather than a message naming the limit. Two screens shipped asking for 500 and were broken against every real backend while their tests, whose fakes ignore `pageSize`, stayed green |

Core services and infrastructure remain separately injectable:

- `NotificationPresenter` / `NotificationService`
- `DesktopPreferencesService`
- `ThemeManager`
- `AppDialogs`
- `PermissionService`

## Creating a standard CRUD module

Existing REST resources use `ResourceManagementPage<T>` and a
`ResourceDefinition<T>`. The definition owns metadata and API callbacks while
the shared page owns loading, errors, search, pagination, selection, details,
dialogs, shortcuts, copy, confirmation, and notifications.

```dart
ResourceManagementPage<Vendor>(
  api: api,
  definition: ResourceDefinition<Vendor>(
    title: 'Vendors',
    resource: 'vendors',
    headers: const ['Code', 'Name', 'Status'],
    cells: (vendor) => [vendor.code, vendor.name, vendor.status],
    id: (vendor) => vendor.id,
    load: api.vendors,
    fields: vendorFields,
    initialValues: vendorInitialValues,
    payload: vendorPayload,
    canUseAction: (action, selected) =>
        permissions.canUseAction(vendorPermissions[action] ?? const []),
  ),
)
```

Customers, Vendors, Products, Sales, Inventory, Accounting, and Reports should
provide only entity models, API adapters, field metadata, permission mapping,
and optional details/export callbacks. They must not duplicate the surrounding
workspace.

## Complex documents and reports

Complex records that do not fit metadata-driven fields still use
`WorkspaceDialog`. Supply module-owned tab bodies and a footer while retaining
shared sizing, scrolling boundaries, loading protection, Ctrl+S, and Escape.

```dart
WorkspaceDialog(
  title: 'Sales order',
  subtitle: 'Create new document',
  icon: Icons.receipt_long_outlined,
  tabs: [
    WorkspaceDialogTab(label: 'General', child: generalForm),
    WorkspaceDialogTab(label: 'Lines', child: lineEditor),
  ],
  body: generalForm,
  footer: documentFooter,
  loading: controller.saving,
  onSave: controller.save,
  onClose: controller.cancel,
)
```

Reports use `WorkspaceLayout` with their own bounded report content. They may
replace the grid with charts or report viewers, but search, filters, status,
loading, empty states, and export actions remain shared.

## Interaction contracts

`WorkspaceShortcuts` registers only callbacks the current user may invoke.
Supported defaults are Ctrl+N, Ctrl+S, Ctrl+F, Ctrl+R, Ctrl+C, Ctrl+K, Escape,
F5, and Delete. Delete callbacks must open confirmation and must never perform
an immediate mutation.

Grid context menus extend `WorkspaceContextAction`; unsupported or unauthorized
actions are omitted. Right-click selects the row before opening its menu.
Ctrl+C and Copy row place tab-delimited visible cell values on the clipboard
without replacing normal row selection. Read-only detail values use
`SelectableText`.

## State and feedback

- Use `NotificationService.instance` through `NotificationPresenter` when
  injecting feedback; use the static convenience method in existing widgets.
- Use `ConfirmationType` presets for delete, logout, discard, password reset,
  lock, and unlock operations.
- Use `LoadingOverlay` when loaded content should remain visible, skeletons for
  initial table loading, and button progress for mutations.
- Use `StandardEmptyState` so no records, no results, permissions, network,
  firm, and licensing failures remain visually distinct.
- Keep backend validation authoritative and map field errors inside the shared
  CRUD dialog.

## Preferences and themes

`DesktopPreferencesService` persists local window state, sidebar collapse,
grid density, theme cache, landing page, server history, and last workspace.
Server preference fields already include theme, default firm, landing page,
and rows per page; synchronize through the authenticated API only when that
backend setting is supported.

Widgets consume `ThemeData`, `ColorScheme`, `AppSemanticColors`, and design
tokens from `core\design\design_tokens.dart`. Feature modules must not define
themes or hardcode presentation colors. `ThemeManager` remains the only runtime
theme coordinator and preserves the five future-compatible theme identities.

## Dependency and ownership rules

1. Widgets receive API adapters, permission checks, controllers, and services
   through constructors.
2. Feature widgets compose shared components; they do not own shell state.
3. Controllers own query, mutation, and validation orchestration. Widgets own
   transient focus, selection, and presentation state only.
4. Backend APIs, authentication, database access, and business rules stay
   outside the desktop framework.
5. Every module must remain bounded and overflow-free at 1366x768, 1600x900,
   1920x1080, restored windows, and maximized windows.

---

# Appendix — shell, catalog and preference rules from `CLAUDE.md`

*Moved out of `CLAUDE.md` on 2026-09-15, when that file passed the 150k-character
limit that keeps it loadable in one context window. Verbatim. Some of it restates
what the parts above cover in more depth; where the two differ, the narrative here
is the one that names the defect and the date, so read it as the record of how a
rule came to be rather than as the reference.*

`main.dart` → `app.dart` → `ui/desktop_shell.dart` (the single shell). Modules are declared as data in `ui/workspace/module_catalog.dart` (`ModuleDefinition` with id, icon, workspace template, tabs, and `requiredPermissions`); the shell filters them by permission **and** by business-profile active modules. Adding a module means adding a catalog entry plus a workspace page — not new navigation code. **A tab's body goes in the workspace of the module that declares it.** Each multi-tab workspace renders by `switch (tabId)` and falls back to a "coming soon" placeholder for an id it does not name; Vendor Categories and Vendor Types were declared under Masters and dispatched inside the Administration workspace, so the sidebar entry opened the placeholder from 2026-08-22 until manual testing reached it on 2026-09-11, while the screen's own widget test passed because it built the definition directly. `desktop/test/workspace_tab_bodies_test.dart` fails the build on the next one.

**A field the desktop sends must be one the server declares, and a suite on either side cannot see when it is not.** `ApiSchema` forbids unknown fields, so one stray key fails the whole request. The desktop split appearance into palette, mode and contrast on 2026-08-10 and sent all three to `PATCH /api/v1/me/preferences`; the server declared two. Every appearance save answered 422 and stored **nothing** -- the two declared fields rode in the same refused request -- and the next sign-in handed the client the row's untouched defaults, which `applyServerAppearance` wrote over the correct local copy. A theme chosen on Monday was gone on Tuesday, and the only trace was an unhandled exception in the crash log, because `ThemeSelector` fired the save and forgot it. It survived a month of green suites for the reason a claim-shape change does: the desktop's fake API accepts whatever it is given and the backend's tests build their own requests, so neither asks whether the real client's payload would be accepted. `preferred_palette` is a column since `20260908_0132`, `ThemeSelector` says so when a save is refused, and `tests/unit/test_desktop_preference_payloads_are_accepted.py` reads the keys `session_controller.dart` sends and the keys `user_preferences.dart` reads and asks the two schemas -- the question that closes the gap between the suites. **Two more preferences went missing at sign-in for neighbouring reasons**, both fixed the same day. Saved searches and the inventory views kept their state *inside* the cached server document (`server_preferences`), which `_applyServerPreferences` replaces wholesale, so they came back empty every morning; they live in `DesktopPreferences.workspaceState` now, through `saveWorkspaceState`/`workspaceState(key)`, which no sign-in touches, and the first load after the split lifts the three old keys across once. And the last screen was one machine-wide file (`%APPDATA%\.agency_platform\desktop_preferences.json` is per Windows account, not per user), so on a shared PC user B landed on user A's screen; `saveLastWorkspace` now also writes the user's own `default_landing_page` and `lastWorkspace` reads it first, with the local file as the offline fallback. The server pattern for that field had to admit uppercase, because the desktop's module names are Dart enum members like `goodsReceipts`. `desktop/test/workspace_state_persistence_test.dart` pins both. The last used **firm** was never lost: `switchFirm` writes `default_firm_id`, and sign-in reads it for a person with no primary firm.

**A sign-in lands on the primary firm, and the primary firm is the person's own to choose.** `GET /api/v1/me` and `PUT /api/v1/me/primary-firm` exist as of 2026-09-08, gated on being signed in and nothing else. Before them the desktop could show a signed-in person nothing but the address typed at the login form -- the login response carries tokens only, the token's claims carry roles and never a name, and `GET /users/{id}` needs `USER_VIEW` -- and after a restored session not even that, since `attemptedUsername` is set only by `login`; the menu read "User". `SessionController.currentUser` and `userLabel` are what the menu and the status bar show now. The primary firm could be set only by an administrator through `PUT /users/{id}/firms`, which replaces the whole membership list and is held to the caller's reach; where a person lands is their own decision, so the self-service route touches that one flag, for the caller alone, among the firms they actively belong to, clearing the old primary and **flushing** before setting the new one because `UQ_user_firms_active_primary` is checked per statement. **`resolveLandingFirm` reads the primary before `default_firm_id` now**, which is the change that makes the flag mean anything: read the other way round, the last firm always came back and a chosen primary was never seen by anybody who had ever switched. Switching is for the session; the primary is for next time, and the switcher labels the primary so the difference is visible where switching happens. The **Primary firm** entry in the user menu is offered only to somebody with a choice to make -- more than one firm, and not a platform administrator, who always starts on Platform. **My profile** in the same menu is the self-service read: `GET /me` carries `profile` (`UserProfileFields`, validated straight off the row) and `roles` (`list_my_roles`, the global tier with no firm and each firm's own with its code), so a person sees what is held about them and what they may do without holding `USER_VIEW`; it is read-only by design and says so, since changing those details stays an administrator's job -- except the password, which is the person's own: **Change password** on My profile is the ordinary way to `POST /auth/change-password`, which for a year was reachable only from the screen a *forced* change lands on. The policy is named beside the box (`ChangePasswordPolicy.check` mirrors `validate_password_policy`), the server still refuses the last five, and a successful change ends the session through `SessionController.signOutAfterPasswordChange` because the server has already revoked every token. **A refusal about the account's state names it; a refusal about the credential does not.** One message for every refusal was deliberate, so that an outsider cannot learn which addresses exist -- and it left somebody holding the *right* password with no way to tell a lockout from a typo, which the owner found on the first manual pass and decided against (2026-09-09, `docs/BACKLOG.md` 18.1 and 18.2). `AccountLockedError`, `AccountInactiveError` and `AccountExpiredError` in `app/core/exceptions/base.py` are subclasses of `AuthenticationError`, so every handler catching the broad class still does and 401 stays 401; their codes are `account_locked`, `account_inactive`, `account_expired`. Two properties are load-bearing. The locked refusal is raised **before the password is looked at**, so nothing about it depends on verifying the password -- which is the timing the equal-cost refusal exists to hide -- and the attempt that locks the account is told so as well. And a wrong password or an unknown address still says only "Invalid email or password.", pinned beside the three states in `test_identity_hardening.py`, because that half of the decision did not move. `refresh` raises the same two for a closed account, and the desktop's `ApiException.code` plus `namesAccountState` is how the message survives onto the sign-in screen as a notice; an ordinary token expiry says nothing. The lockout also carries `retry_after_seconds` in its details, and the sign-in banner **counts it down** rather than repeating the minutes quoted at the click -- decremented per tick rather than re-read from the clock, so a widget test can drive it with `pump(Duration)`. **A platform administrator sets anybody else's password** through `POST /api/v1/users/{id}/password` (platform-only list), for the forgotten, the locked-out and the account handed over after somebody left: no current password, the lock cleared, every session revoked, the old hash kept in the history so the reset cannot be undone by changing back, `force_password_change` on by default so a password an administrator chose is a way in and not a password kept, and the caller's own account refused because My profile asks for the current password for a reason. On the desktop it sits in the user dialog's footer beside Roles by firm -- the toolbar is full -- and the footer builder now returns a `Row` when more than one action applies. **A deleted user can be restored, by a platform administrator, as they were** -- `POST /api/v1/users/{id}/restore`, on the platform-only list. Deletion marks the row and revokes the sessions and leaves the memberships, roles and preferences in place, so a restore is one flag; the grid's half is finding the row, which `GET /users?deleted_only=true` answers for a platform administrator only -- the deleted rows *instead of* the live ones, since the first cut mixed them in and "Deleted" showed every active user beside the one being looked for -- since a deleted person's memberships still place them in a firm and a firm's grid must not list them. The grid carries a **Status** filter beside Firm as of 2026-09-09 -- Active, Inactive, Deleted -- a firm and a status being two axes rather than sentinel values overloaded onto one dropdown (they were, until the filter bar was found to be a `Wrap` that wraps a second control rather than the `Row` a stale comment claimed). Deleted (`deleted_only`) is a *separate population* and platform-admin-only, so it overrides any firm chosen; Active (`active_only`) and Inactive (`inactive_only`) are *narrowings* of the live rows, honoured for any caller and meaningless beside `deleted_only`, and they **compose with the firm scope** -- inactive-members-of-one-firm is the query the overloaded filter could not ask. Refused by name when a live account has since taken the address -- the email is unique among live accounts -- so **restore before re-onboarding**, and deciding which of two accounts survives is a person's call rather than a merge.

**A tab may name a `group`, and grouped tabs are one sidebar entry with a tab strip inside.** Roles and Permissions are the first (`ModuleCatalog.rolesAndPermissions`, 2026-09-08): two reference screens opened a few times a year, each a row in a menu scanned every day. Each tab keeps its own id, because the id is its **address** -- what Ctrl+K opens, what `WorkspaceRouter` carries (module and tab, nothing else), what the remembered last screen restores -- and `test_search_navigation_targets.py` fails the build if one vanishes; only how it is reached changes. `_administrationNavigation` emits one leaf per group whose path is the first *visible* member, so a caller who may open only Permissions gets an entry that opens Permissions rather than one that opens nothing, and `WorkspaceNavigationNode.alsoSelectedBy` keeps the entry highlighted on the other half -- a leaf over several addressable tabs goes dark the moment somebody switches the strip or arrives by Ctrl+K otherwise. `TabGroupPage` owns no selection: choosing a tab calls `router.selectTab`, the workspace rebuilds with the new id, and the heading (`administrationHeaderFor` takes the group as its title, the description stays per tab), the sidebar and the remembered screen all follow one value. Not a parent node with children: clicking a parent only expands it, so that shape is two clicks and *more* rows.

All UI composes the shared framework barrel:

```dart
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
```

which provides `WorkspaceLayout`, `ModuleWorkspaceFrame`, `ManagementWorkspaceLayout`, `WorkspaceDialog`/`CrudWorkspaceDialog`, `WorkspaceToolbar`, `SearchFilterPanel`, `EnterpriseDataGrid`, `StatusBadge`, `LoadingOverlay`, `StandardEmptyState`, `WorkspaceShortcuts`, and the context-menu/global-search helpers. Simple REST resources should be expressed as a `ResourceDefinition<T>` passed to `ResourceManagementPage<T>` — metadata and API callbacks only, no bespoke shell. Complex documents still use `WorkspaceDialog` with module-owned tab bodies. Feature modules must not define themes or hardcode colors; use `core/design/design_tokens.dart` and `ThemeManager`. Every screen must stay overflow-free from 1366x768 up.

`lib/core/api/api_client.dart` is the **only** place endpoint paths live; it also owns the `X-Firm-ID` header, the single automatic refresh-retry after a `401`, and the HTTPS-except-loopback rule. Only the refresh token is persisted, in the OS credential vault via `flutter_secure_storage`; passwords are never stored. Runtime branding comes from the external `config/branding.json` beside the executable.

Detailed contracts live in `desktop/docs/DESKTOP_FRAMEWORK.md`, `DESIGN_SYSTEM.md`, `UX_GUIDELINES.md`, and `COMPONENT_LIBRARY.md`.

## A dialog owns its own `TextEditingController`

**A dialog owns its own `TextEditingController`.** A caller that creates
one, awaits `showDialog` and then disposes it, disposes it *mid-animation*,
and the field rebuilding during the exit throws "A TextEditingController was
used after being disposed". An `AlertDialog` also gives its content
unbounded height, so a stretched `Column` with no width overflows by tens of
thousands of pixels instead of laying out. Both were written twice in one
afternoon before `askForReason` in
`desktop/lib/ui/workspace/reason_prompt.dart` existed; use it rather than a
third copy. It returns null for a dismissal **and** for an empty box, so a
caller has one answer to check.
