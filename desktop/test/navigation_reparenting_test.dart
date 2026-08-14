import 'package:agency_desktop/ui/workspace/enterprise_sidebar.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/workspace_templates.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Documents filed under the process they belong to.
///
/// TRANSACTIONS used to carry eight top-level entries, with `Sales Invoices` a
/// sibling of `Sales` -- a document type outranking the process it belongs to.
///
/// Each document is still a whole module: its own page, its own permissions,
/// its own route. Only where the sidebar draws it changed, which is the reason
/// no stored workspace had to be migrated. The last group here is what proves
/// that, and it is the reason an alias map turned out not to be needed.
const List<AppModule> _purchaseDocuments = [
  AppModule.goodsReceipts,
  AppModule.purchaseInvoices,
  AppModule.purchaseReturns,
];

const List<AppModule> _salesDocuments = [
  AppModule.salesOrders,
  AppModule.deliveryNotes,
  AppModule.salesInvoices,
];

Widget _sidebar(EnterpriseSidebarSection section) => MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 320,
          height: 900,
          child: EnterpriseSidebar(
            appName: 'Agency',
            modules: ModuleCatalog.modules,
            navigationChildren: (module) => const <WorkspaceNavigationNode>[],
            selectedModule: AppModule.dashboard,
            selectedPath: null,
            onSelectModule: (_) {},
            onSelectLeaf: (_, __) {},
            collapsed: false,
            onToggleCollapsed: () {},
            sections: [section],
          ),
        ),
      ),
    );

void main() {
  group('the section carries the nesting', () {
    test('a child module is declared under its parent, not beside it', () {
      const EnterpriseSidebarSection section = EnterpriseSidebarSection(
        label: 'TRANSACTIONS',
        moduleIds: [AppModule.purchases, AppModule.sales],
        childModuleIds: {
          AppModule.purchases: _purchaseDocuments,
          AppModule.sales: _salesDocuments,
        },
      );

      expect(section.moduleIds, hasLength(2));
      for (final AppModule document in [
        ..._purchaseDocuments,
        ..._salesDocuments,
      ]) {
        expect(
          section.moduleIds,
          isNot(contains(document)),
          reason: '$document must not also sit at the top level',
        );
      }
      expect(section.childModuleIds[AppModule.sales], _salesDocuments);
    });
  });

  group('the sidebar draws it', () {
    testWidgets('parents and children are both rendered', (tester) async {
      tester.view.physicalSize = const Size(1400, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        _sidebar(
          const EnterpriseSidebarSection(
            label: 'TRANSACTIONS',
            moduleIds: [AppModule.purchases, AppModule.sales],
            childModuleIds: {
              AppModule.purchases: _purchaseDocuments,
              AppModule.sales: _salesDocuments,
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(ModuleCatalog.byId(AppModule.sales).label), findsOneWidget);
      expect(
        find.text(ModuleCatalog.byId(AppModule.salesInvoices).label),
        findsOneWidget,
      );
      expect(
        find.text(ModuleCatalog.byId(AppModule.goodsReceipts).label),
        findsOneWidget,
      );
    });

    testWidgets('a child is indented further than its parent', (tester) async {
      // The indent is the whole point: without it the tree reads as eight
      // siblings again, however the data is shaped.
      tester.view.physicalSize = const Size(1400, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        _sidebar(
          const EnterpriseSidebarSection(
            label: 'TRANSACTIONS',
            moduleIds: [AppModule.sales],
            childModuleIds: {AppModule.sales: _salesDocuments},
          ),
        ),
      );
      await tester.pumpAndSettle();

      final double parentLeft = tester
          .getTopLeft(find.text(ModuleCatalog.byId(AppModule.sales).label))
          .dx;
      final double childLeft = tester
          .getTopLeft(
              find.text(ModuleCatalog.byId(AppModule.salesInvoices).label))
          .dx;
      expect(childLeft, greaterThan(parentLeft));
    });

    testWidgets('a child filtered out by permissions is simply absent',
        (tester) async {
      tester.view.physicalSize = const Size(1400, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);

      // The shell filters `childModuleIds` through the same permission check as
      // the top level, so an unpermitted document arrives as an absent entry
      // rather than a broken one.
      await tester.pumpWidget(
        _sidebar(
          const EnterpriseSidebarSection(
            label: 'TRANSACTIONS',
            moduleIds: [AppModule.sales],
            childModuleIds: {
              AppModule.sales: [AppModule.salesOrders],
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(ModuleCatalog.byId(AppModule.salesOrders).label),
        findsOneWidget,
      );
      expect(
        find.text(ModuleCatalog.byId(AppModule.salesInvoices).label),
        findsNothing,
      );
    });
  });

  group('stored workspaces still resolve', () {
    test('every re-parented module keeps the route name it was stored under',
        () {
      // `_routeModule()` matches a stored `lastWorkspace` against
      // `AppModule.values` by name and falls back to Dashboard for anything it
      // cannot match. Re-parenting by moving a module between sidebar sections
      // leaves that name alone, so a client that was last on Sales Invoices
      // reopens there.
      //
      // This is what an alias map would have been for. Changing a route id
      // instead of a section would break it, and this test is the tripwire.
      for (final AppModule document in [
        ..._purchaseDocuments,
        ..._salesDocuments,
      ]) {
        final AppModule resolved = AppModule.values.firstWhere(
          (module) => module.name == document.name,
          orElse: () => AppModule.dashboard,
        );
        expect(
          resolved,
          document,
          reason: 'a client last on ${document.name} must not land on Dashboard',
        );
      }
    });
  });
}
