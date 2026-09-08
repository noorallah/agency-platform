import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/sales_invoice.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/module_visibility.dart';
import 'package:agency_desktop/ui/workspace/workspace_templates.dart';
import 'package:flutter_test/flutter_test.dart';

/// What a signed-in user is offered, asked of the rules the shell actually
/// uses.
///
/// Before `ModuleVisibility` existed these rules lived inside `DesktopShell`
/// as closures over private fields, and **no test in this suite instantiates
/// the shell**. So each predicate was spot-checked for one or two modules
/// while the composed answer -- 18 modules and 86 tabs -- was never exercised.
/// That is how a firm administrator came to be offered a Dashboard the server
/// refuses, on the page the app lands on.
PermissionService _service({
  List<String> permissions = const [],
  bool platformAdmin = false,
  String? platformScope,
  String firm = 'firm-1',
}) {
  final String payload = base64Url.encode(
    utf8.encode(
      jsonEncode({
        'permissions': <String>[],
        'roles': const <String>[],
        // Its own claim. It used to be the lowercase string `platform_admin`
        // inside `roles`, which a firm admin could spell as a custom role
        // code and become one -- so a fixture that still derived it from that
        // list would be testing a shape the application no longer issues.
        'platform_admin': platformAdmin,
        'platform_admin_scope': platformScope,
        'firm_permissions': {firm: permissions},
      }),
    ),
  );
  return PermissionService()
    ..applyAccessToken('h.$payload.s', activeFirmId: firm);
}

/// The seeded codes, transcribed from `app/identity/system_seed.py`. Kept
/// short on purpose: these tests are about the *filter*, and a full copy of
/// 189 codes would rot without anybody noticing. `backend/tests/unit/
/// test_desktop_gates_on_real_permissions.py` is what guards the codes
/// themselves against the real catalogue.
/// Every code the catalogue gates on, which is what a platform admin's real
/// token carries: `_issue_tokens` puts **all** active permission codes in the
/// global `permissions` claim for them. `PermissionService` does not
/// short-circuit on the role -- only `Principal.has_permission` does, on the
/// server -- so a fixture that granted the role and no codes would be testing
/// something the application never sees.
Set<String> _everyGatedCode() {
  final Set<String> codes = {};
  for (final ModuleDefinition module in ModuleCatalog.modules) {
    codes.addAll(module.requiredPermissions);
    for (final ModuleTabDefinition tab in module.tabs) {
      codes.addAll(tab.requiredPermissions);
    }
  }
  return codes;
}

const List<String> _salesExecutive = [
  'SALES_VIEW',
  'SALES_CREATE',
  'SALES_UPDATE',
  'SALES_QUOTATION_CREATE',
  'CUSTOMER_VIEW',
  'PRODUCT_VIEW',
];

void main() {
  _navigationLeadsSomewhereTests();

  group('the composed module filter', () {
    test('a platform admin is offered every module', () {
      final ModuleVisibility view = ModuleVisibility(
        permissions: _service(
          permissions: _everyGatedCode().toList(),
          platformAdmin: true,
          platformScope: 'ALL_FIRMS',
        ),
      );

      expect(view.modules.length, ModuleCatalog.modules.length);
      for (final ModuleDefinition module in ModuleCatalog.modules) {
        expect(view.denial(module), isNull, reason: module.label);
      }
    });

    test('a sales executive is refused the modules they have no codes for', () {
      final ModuleVisibility view = ModuleVisibility(
        permissions: _service(permissions: _salesExecutive),
      );

      final Set<String> shown =
          view.modules.map((module) => module.label).toSet();

      expect(shown, contains('Sales'));
      expect(shown, isNot(contains('Purchases')));
      expect(shown, isNot(contains('Finance')));
      expect(shown, isNot(contains('Dashboard')));
    });

    test('a denial says which gate refused, not just that one did', () {
      // "Finance is missing" and "Finance needs ACCOUNT_VIEW, which this role
      // does not hold" are very different pieces of information to whoever is
      // asking why a screen has gone.
      final ModuleVisibility view = ModuleVisibility(
        permissions: _service(permissions: _salesExecutive),
      );
      final ModuleDefinition dashboard =
          ModuleCatalog.byId(AppModule.dashboard);
      final ModuleDefinition finance = ModuleCatalog.byId(AppModule.accounting);

      expect(view.denial(dashboard), 'platform administrators only');
      expect(view.denial(finance), contains('ACCOUNT_VIEW'));
    });

    test('the Dashboard is refused even though its permission list passes', () {
      // The heart of the defect this file exists for. A FIRM_ADMIN holds three
      // of the Dashboard's four codes and the list is `requiresAny`, so the
      // permission gate says yes. Only the platform-admin gate says no.
      final PermissionService firmAdmin = _service(
        permissions: ['USER_VIEW', 'ROLE_VIEW', 'PERMISSION_VIEW'],
      );
      final ModuleDefinition dashboard =
          ModuleCatalog.byId(AppModule.dashboard);

      expect(
        firmAdmin.canUseModule(
          dashboard.requiredPermissions,
          requiresAny: dashboard.requiresAnyPermission,
        ),
        isTrue,
        reason: 'the permission list cannot be what hides it',
      );
      expect(
        ModuleVisibility(permissions: firmAdmin).denial(dashboard),
        'platform administrators only',
      );
    });
  });

  group('the two reaches of a platform designation', () {
    // The backend has two: one who runs the platform, and one who may also act
    // inside every firm's books. The first is refused firm-owned routes
    // outright, so a screen offering them an operational module would be
    // offering one that answers 403 on its first request.
    //
    // Nothing in `ModuleVisibility` asks about the reach, and that is the
    // point: a `PLATFORM` token carries only the 33 platform permission codes,
    // so the operational modules fall out through the ordinary permission
    // gate. This group pins that it really does fall out, because the
    // alternative -- a fourth gate -- is a rule that has to be remembered.
    const List<String> platformOperator = [
      'FIRM_CREATE',
      'FIRM_VIEW',
      'USER_VIEW',
      'USER_CREATE',
      'ROLE_VIEW',
      'ROLE_ASSIGN',
      'PERMISSION_VIEW',
      'SETTINGS_VIEW',
      'AUDIT_LOG_VIEW',
    ];

    test('a platform operator is offered the platform, not the books', () {
      final ModuleVisibility view = ModuleVisibility(
        permissions: _service(
          permissions: platformOperator,
          platformAdmin: true,
          platformScope: 'PLATFORM',
        ),
      );
      final Set<String> shown =
          view.modules.map((module) => module.label).toSet();

      // Theirs: the platform surface, including the dashboard that only a
      // designation opens.
      expect(shown, contains('Dashboard'));
      expect(shown, contains('Administration'));
      // Not theirs: a firm's own books.
      expect(shown, isNot(contains('Sales')));
      expect(shown, isNot(contains('Purchases')));
      expect(shown, isNot(contains('Finance')));
      expect(shown, isNot(contains('Inventory')));
    });

    test('the two reaches are told apart, and an old token keeps its own', () {
      expect(
        _service(
                permissions: const [],
                platformAdmin: true,
                platformScope: 'PLATFORM')
            .mayActInAnyFirm,
        isFalse,
      );
      expect(
        _service(
                permissions: const [],
                platformAdmin: true,
                platformScope: 'ALL_FIRMS')
            .mayActInAnyFirm,
        isTrue,
      );
      // Minted before the scope existed, for somebody who by definition had
      // every firm. Reading its absence as the narrow value would strip a live
      // session of screens it legitimately had.
      expect(
        _service(permissions: const [], platformAdmin: true).mayActInAnyFirm,
        isTrue,
      );
      // And an unrecognised value grants the narrow one, as on the server.
      expect(
        _service(
                permissions: const [],
                platformAdmin: true,
                platformScope: 'EVERYTHING')
            .mayActInAnyFirm,
        isFalse,
      );
      expect(_service(permissions: const []).platformAdminScope, isNull);
    });
  });

  group('the business profile and the workflow stages', () {
    PermissionService everything() => _service(
          permissions: _everyGatedCode().toList(),
          platformAdmin: true,
          platformScope: 'ALL_FIRMS',
        );

    test('null active modules shows everything', () {
      // A failed fetch must not empty the sidebar. Hiding a firm's whole
      // application because one request timed out is worse than briefly
      // offering a module it has switched off.
      final ModuleVisibility view = ModuleVisibility(permissions: everything());
      expect(view.modules.length, ModuleCatalog.modules.length);
    });

    test('a module its firm switched off is hidden, and says so', () {
      final ModuleVisibility view = ModuleVisibility(
        permissions: everything(),
        activeBusinessModules: const {'SALES', 'REPORTS'},
      );
      final ModuleDefinition purchases =
          ModuleCatalog.byId(AppModule.purchases);

      expect(view.denial(purchases), 'this firm has switched the module off');
      expect(view.modules.map((m) => m.id), contains(AppModule.sales));
    });

    test('a stage this firm does not type is hidden', () {
      final ModuleVisibility view = ModuleVisibility(
        permissions: everything(),
        salesStages: const SalesWorkflowSettings(
          quotationStage: false,
          salesOrderStage: true,
          deliveryNoteStage: true,
          isConfigured: true,
        ),
      );

      expect(
        view.denial(ModuleCatalog.byId(AppModule.quotations)),
        'this firm does not type this stage of a sale',
      );
      expect(view.denial(ModuleCatalog.byId(AppModule.salesOrders)), isNull);
      // Sales returns are never hidden: a counter sale still comes back.
      expect(view.denial(ModuleCatalog.byId(AppModule.salesReturns)), isNull);
    });
  });

  group('tabs', () {
    test('a tab naming no permissions inherits its module list', () {
      final ModuleVisibility admin = ModuleVisibility(
        permissions: _service(
          permissions: _everyGatedCode().toList(),
          platformAdmin: true,
          platformScope: 'ALL_FIRMS',
        ),
      );
      final ModuleDefinition administration =
          ModuleCatalog.byId(AppModule.administration);

      expect(admin.tabIds(administration).length, administration.tabs.length);
    });

    test('a hidden module offers no tabs at all', () {
      // The gate this used to miss. The tab filter applied `available` and
      // permissions but neither the platform-admin gate nor the profile nor
      // the stages -- so a module refused at the module level could still
      // hand out its tabs. Harmless only because the one platform-admin
      // module has no tabs; the next one with tabs would have leaked them.
      final ModuleVisibility view = ModuleVisibility(
        permissions: _service(permissions: _salesExecutive),
        activeBusinessModules: const {'SALES'},
      );
      final ModuleDefinition purchases =
          ModuleCatalog.byId(AppModule.purchases);

      expect(view.allows(purchases), isFalse);
      expect(view.tabIds(purchases), isEmpty);
    });

    test('every module the catalogue declares can be asked about', () {
      // A cheap sweep over all 18, so a new module with a malformed gate
      // fails here rather than on somebody's screen.
      final ModuleVisibility view = ModuleVisibility(
        permissions: _service(permissions: _salesExecutive),
      );
      for (final ModuleDefinition module in ModuleCatalog.modules) {
        expect(() => view.denial(module), returnsNormally,
            reason: module.label);
        expect(() => view.tabIds(module), returnsNormally,
            reason: module.label);
      }
    });
  });

  // ----------------------------------------------------------------------
  // Platform mode: a platform administrator with no firm selected
  // ----------------------------------------------------------------------
  //
  // `platform-admin@agency.local` holds `ALL_FIRMS` and **zero** firm
  // memberships, so its switcher was empty -- and its token carries every
  // permission code, so the sidebar offered Sales, Purchases, Inventory and
  // the rest on a context that could not send `X-Firm-ID`. Every one of them
  // opened onto a request the server refuses.
  //
  // The firm switcher is the mode now: no firm is platform work.
  group('with no firm selected', () {
    ModuleVisibility platformMode() => ModuleVisibility(
          permissions: _service(
            permissions: _everyGatedCode().toList(),
            platformAdmin: true,
            platformScope: 'ALL_FIRMS',
          ),
          hasActiveFirm: false,
        );

    test('a firm-owned module is not offered', () {
      final ModuleVisibility view = platformMode();
      for (final AppModule id in [
        AppModule.sales,
        AppModule.purchases,
        AppModule.inventory,
        AppModule.masters,
        AppModule.accounting,
        AppModule.reports,
      ]) {
        final ModuleDefinition module = ModuleCatalog.byId(id);
        expect(view.allows(module), isFalse, reason: module.label);
        expect(view.denial(module), 'no firm is selected',
            reason: module.label);
      }
    });

    test('platform administration still is', () {
      final ModuleVisibility view = platformMode();
      expect(view.allows(ModuleCatalog.byId(AppModule.administration)), isTrue);
      expect(view.allows(ModuleCatalog.byId(AppModule.dashboard)), isTrue);
      expect(view.allows(ModuleCatalog.byId(AppModule.settings)), isTrue);
    });

    test('a platform-only tab is hidden from a firm administrator who '
        'satisfies its permission list', () {
      // User-Firm Assignments is a strict subset of the Users form, so for a
      // firm administrator it was a third door onto one room. It is flagged
      // `requiresPlatformAdmin` on the tab, and the flag has to be read where
      // every tab strip is built or it is the #249 shape again: a gate in the
      // catalogue nobody consults.
      final ModuleDefinition administration =
          ModuleCatalog.byId(AppModule.administration);
      final ModuleTabDefinition tab =
          administration.tabs.firstWhere((t) => t.id == 'user-firms');
      expect(tab.requiresPlatformAdmin, isTrue);

      final PermissionService firmAdmin =
          _service(permissions: const ['USER_VIEW', 'USER_UPDATE']);
      // The property the flag exists for: the code list alone would let
      // them through.
      expect(firmAdmin.canUseTab(tab.requiredPermissions), isTrue);
      expect(firmAdmin.isPlatformAdmin, isFalse);

      final Set<String> firmTabs = ModuleVisibility(
        permissions: firmAdmin,
        hasActiveFirm: true,
      ).tabIds(administration);
      expect(firmTabs, contains('users'),
          reason: 'the same codes still open the Users tab');
      expect(firmTabs, isNot(contains('user-firms')));

      // And the caller it is for still has it, with or without a firm.
      expect(platformMode().tabIds(administration), contains('user-firms'));
      final Set<String> platformInFirm = ModuleVisibility(
        permissions: _service(
          permissions: _everyGatedCode().toList(),
          platformAdmin: true,
          platformScope: 'ALL_FIRMS',
        ),
        hasActiveFirm: true,
      ).tabIds(administration);
      expect(platformInFirm, contains('user-firms'));
    });

    test("Administration offers its platform tabs and hides the firm's", () {
      // The module that makes a tab-level answer necessary: users and roles
      // are platform tables, the tax and UOM configuration is each firm's
      // own, and they sit side by side under one heading.
      final Set<String> tabs =
          platformMode().tabIds(ModuleCatalog.byId(AppModule.administration));

      expect(tabs, contains('users'));
      expect(tabs, contains('roles'));
      expect(tabs, contains('user-firms'));
      // The screen that creates a firm. It was the first tab of Masters --
      // a firm's own master data, which needs a firm selected -- so creating
      // a firm was reachable only from inside another firm.
      expect(tabs, contains('firms'));
      expect(tabs, isNot(contains('tax-configuration')));
      expect(tabs, isNot(contains('uoms')));
      // Every tab under Business Profiles stays hidden with no firm, and
      // `profile-assignment` is the one that looks like an exception and is
      // not. Its own two calls answer 200 with no `X-Firm-ID`, so it was
      // made visible here on 2026-09-06 -- and the edit dialog's profile
      // dropdown reads `/business-framework/profiles`, which answers 503,
      // because the catalogue lives in each firm's store. The grid rendered
      // and could not be used. Reverted the same day: a tab one click away
      // beats a screen that opens and cannot be filled in.
      //
      // Driven against a running server: `/firm-profile-assignments` and
      // `/firms/{id}/profile-assignment` answered 200 with no firm, while
      // `/profiles`, `/features`, `/modules`, `/attribute-definitions` and
      // `/category-attribute-rules` all answered 503.
      expect(tabs, isNot(contains('profile-assignment')));
      expect(tabs, isNot(contains('business-profiles')));
      expect(tabs, isNot(contains('feature-management')));
      expect(tabs, isNot(contains('module-configuration')));
      expect(tabs, isNot(contains('attribute-definitions')));
      expect(tabs, isNot(contains('category-attribute-rules')));
    });

    test('nobody is left with an empty sidebar', () {
      // The failure this is really about: a mode that hides everything is
      // worse than the menu of refusals it replaced.
      expect(platformMode().modules, isNotEmpty);
    });

    test('selecting a firm brings the firm-owned modules back', () {
      final ModuleVisibility view = ModuleVisibility(
        permissions: _service(
          permissions: _everyGatedCode().toList(),
          platformAdmin: true,
          platformScope: 'ALL_FIRMS',
        ),
      );
      expect(view.allows(ModuleCatalog.byId(AppModule.sales)), isTrue);
      expect(
        view.tabIds(ModuleCatalog.byId(AppModule.administration)),
        contains('tax-configuration'),
      );
    });

    test("Firms is no longer filed under a firm's own master data", () {
      expect(
        ModuleCatalog.byId(AppModule.masters).tabs.map((tab) => tab.id),
        isNot(contains('firms')),
      );
    });

    test('an ordinary user is never put in platform mode', () {
      // `hasActiveFirm` defaults to true for exactly this reason: everybody
      // without the designation always has a firm, and a null one would empty
      // their application rather than change its mode.
      final ModuleVisibility view = ModuleVisibility(
        permissions: _service(permissions: _salesExecutive),
      );
      expect(view.allows(ModuleCatalog.byId(AppModule.sales)), isTrue);
    });
  });

  test('there is one tab filter, and the shell does not keep its own', () {
    // There were eight: `ModuleVisibility.tabIds` and seven byte-identical
    // copies inside `desktop_shell.dart`, one per workspace. They drifted the
    // day `requiresFirm` was added -- the navigation tree hid the firm-owned
    // tabs and every workspace's own tab strip went on offering them, so the
    // sidebar and the screen it opened disagreed.
    //
    // A source check rather than a behavioural one because the workspaces are
    // private widgets: nothing can build one to ask it what it shows.
    final String shell = File('lib/ui/desktop_shell.dart').readAsStringSync();

    expect(
      shell.contains('canUseTab('),
      isFalse,
      reason: 'desktop_shell.dart is filtering tabs itself again. Call '
          'ModuleVisibility.tabsFor -- a second copy is a second answer, and '
          'the tab strip and the sidebar then disagree.',
    );
    expect(shell.contains('ModuleVisibility.tabsFor('), isTrue);
  });
}

/// Every navigation node must lead to a tab that is actually there.
///
/// A leaf whose `path` is not in the visible set does not disappear -- the
/// workspace falls back to `visibleTabs.first`, so selecting it **silently
/// renders an unrelated screen**. It has happened twice. First `Audit`, which
/// was unconditional with path `'audit'`, a tab id that does not exist, and
/// rendered Users. Then `Numbering Series`, unconditional and pointing at a
/// tab that lives in a firm's own store -- so it survived every firm-context
/// test and only appeared once platform mode existed, where it again rendered
/// whatever tab came first.
///
/// Both were found by somebody clicking. This asks it mechanically, in both
/// firm contexts, for every module.
void _navigationLeadsSomewhereTests() {
  List<String> pathsOf(List<WorkspaceNavigationNode> nodes) => [
        for (final WorkspaceNavigationNode node in nodes) ...[
          if ((node.path ?? '').isNotEmpty) node.path!,
          ...pathsOf(node.children),
        ],
      ];

  group('navigation leads somewhere', () {
    for (final bool hasActiveFirm in [true, false]) {
      test('with hasActiveFirm=$hasActiveFirm, no node points at a hidden tab',
          () {
        final PermissionService permissions = _service(
          permissions: _everyGatedCode().toList(),
          platformAdmin: true,
          platformScope: 'ALL_FIRMS',
        );
        final ModuleVisibility view = ModuleVisibility(
          permissions: permissions,
          hasActiveFirm: hasActiveFirm,
        );

        final Map<AppModule, List<String>> orphans = {};
        for (final ModuleDefinition module in ModuleCatalog.modules) {
          final Set<String> visible = view.tabIds(module);
          final List<String> dead = pathsOf(
            ModuleCatalog.navigationChildren(module.id, visible),
          ).where((path) => !visible.contains(path)).toList();
          if (dead.isNotEmpty) orphans[module.id] = dead;
        }

        expect(
          orphans,
          isEmpty,
          reason: 'these navigation nodes point at tabs that are not shown, '
              'so selecting one renders whatever tab happens to be first:\n'
              '$orphans\n'
              'Guard the node on visibleTabIds.contains(<tab id>).',
        );
      });

      test('with hasActiveFirm=$hasActiveFirm, no heading is empty', () {
        // The test above walks *leaves*, and a heading carries no path, so an
        // empty one slips straight through it. Administration's
        // `Configuration` node was built unconditionally while every one of
        // its descendants needs a firm -- so with none selected it rendered
        // as a heading that opened nothing, and it was the only parent in the
        // catalogue without a guard. Reported from the running client on
        // 2026-09-06, after the leaf guard above had been green for months.
        final ModuleVisibility view = ModuleVisibility(
          permissions: _service(
            permissions: _everyGatedCode().toList(),
            platformAdmin: true,
            platformScope: 'ALL_FIRMS',
          ),
          hasActiveFirm: hasActiveFirm,
        );

        List<String> emptyHeadings(List<WorkspaceNavigationNode> nodes) => [
              for (final WorkspaceNavigationNode node in nodes) ...[
                // No path of its own and nothing reachable underneath. Both
                // halves matter: with its guard removed the node is built with
                // an *empty* children list, so a check for
                // `children.isNotEmpty` never fires -- which is how the first
                // version of this test passed against the very bug it was
                // written for.
                if ((node.path ?? '').isEmpty && pathsOf(node.children).isEmpty)
                  node.label,
                ...emptyHeadings(node.children),
              ],
            ];

        final Map<AppModule, List<String>> dead = {};
        for (final ModuleDefinition module in ModuleCatalog.modules) {
          final List<String> empty = emptyHeadings(
            ModuleCatalog.navigationChildren(module.id, view.tabIds(module)),
          );
          if (empty.isNotEmpty) dead[module.id] = empty;
        }

        expect(
          dead,
          isEmpty,
          reason: 'these navigation headings have no reachable child, so each '
              'renders as an entry that does nothing when selected: $dead. '
              'Guard the parent on hasAny([...its tab ids]).',
        );
      });
    }
  });
}
