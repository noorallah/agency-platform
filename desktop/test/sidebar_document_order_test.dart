// A document sits beside the step it follows, not after the Settings entry.
//
// Child modules used to be drawn below the parent's *whole* group, and the
// parent's own entries end with Analytics and Settings. So the Purchases menu
// read:
//
//   Dashboard, Purchase Orders, Sourcing, Analytics, Settings,
//   Goods Receipts, Purchase Invoices, Purchase Returns
//
// Receiving — the next thing you do after approving an order — was filed below
// the workspace's configuration, which reads as an afterthought rather than as
// the next step of the process.
//
// `EnterpriseSidebarSection.childModulesAfter` names the entry they follow.

import 'package:agency_desktop/ui/workspace/enterprise_sidebar.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const List<AppModule> _purchaseDocuments = [
  AppModule.goodsReceipts,
  AppModule.purchaseInvoices,
  AppModule.purchaseReturns,
];

Widget _sidebar(EnterpriseSidebarSection section) => MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 340,
          height: 1000,
          child: EnterpriseSidebar(
            appName: 'Agency',
            modules: ModuleCatalog.modules,
            navigationChildren: (module) => ModuleCatalog.navigationChildren(
              module.id,
              module.tabs.map((tab) => tab.id).toSet(),
            ),
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

/// Labels in the order they are painted down the sidebar.
List<String> _order(WidgetTester tester, List<String> wanted) {
  final List<({double top, String label})> found = [];
  for (final String label in wanted) {
    final Finder finder = find.text(label);
    if (finder.evaluate().isEmpty) continue;
    found.add((top: tester.getTopLeft(finder.first).dy, label: label));
  }
  found.sort((a, b) => a.top.compareTo(b.top));
  return [for (final entry in found) entry.label];
}

void main() {
  testWidgets('receiving follows ordering, and configuration comes last',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      _sidebar(
        const EnterpriseSidebarSection(
          label: 'TRANSACTIONS',
          moduleIds: [AppModule.purchases],
          childModuleIds: {AppModule.purchases: _purchaseDocuments},
          childModulesAfter: {AppModule.purchases: 'purchase-orders'},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      _order(tester, const [
        'Purchase Orders',
        'Goods Receipts',
        'Purchase Invoices',
        'Purchase Returns',
        'Analytics',
        'Settings',
      ]),
      const [
        'Purchase Orders',
        'Goods Receipts',
        'Purchase Invoices',
        'Purchase Returns',
        'Analytics',
        'Settings',
      ],
    );
  });

  testWidgets('naming no entry leaves them last, as they always were',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      _sidebar(
        const EnterpriseSidebarSection(
          label: 'TRANSACTIONS',
          moduleIds: [AppModule.purchases],
          childModuleIds: {AppModule.purchases: _purchaseDocuments},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      _order(tester, const ['Settings', 'Goods Receipts']),
      const ['Settings', 'Goods Receipts'],
    );
  });

  testWidgets('an empty entry puts them first', (tester) async {
    // What Sales wants: the documents are the work, and the territory and
    // geography screens beneath them are the setup behind it.
    tester.view.physicalSize = const Size(1400, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      _sidebar(
        const EnterpriseSidebarSection(
          label: 'TRANSACTIONS',
          moduleIds: [AppModule.purchases],
          childModuleIds: {AppModule.purchases: _purchaseDocuments},
          childModulesAfter: {AppModule.purchases: ''},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      _order(tester, const ['Goods Receipts', 'Dashboard', 'Purchase Orders']),
      const ['Goods Receipts', 'Dashboard', 'Purchase Orders'],
    );
  });

  testWidgets('a document is still visible without expanding anything',
      (tester) async {
    // The property this must not cost. Moving these inside the group to fix
    // the order would otherwise hide them behind a disclosure triangle --
    // which is the opposite of the complaint that started it.
    tester.view.physicalSize = const Size(1400, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      _sidebar(
        const EnterpriseSidebarSection(
          label: 'TRANSACTIONS',
          moduleIds: [AppModule.purchases],
          childModuleIds: {AppModule.purchases: _purchaseDocuments},
          childModulesAfter: {AppModule.purchases: 'purchase-orders'},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Goods Receipts'), findsOneWidget);
  });
}
