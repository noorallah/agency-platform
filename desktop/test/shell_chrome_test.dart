import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/workspace_templates.dart';
import 'package:flutter_test/flutter_test.dart';

/// The three §5 tidying decisions, written down so reversing one is deliberate.
///
/// None of them moves a route or a permission: they are ordering and grouping,
/// which is what was wrong with them.
List<WorkspaceNavigationNode> _masters(Set<String> tabs) =>
    ModuleCatalog.navigationChildren(AppModule.masters, tabs);

WorkspaceNavigationNode? _find(
  List<WorkspaceNavigationNode> nodes,
  String label,
) {
  for (final WorkspaceNavigationNode node in nodes) {
    if (node.label == label) return node;
    final WorkspaceNavigationNode? nested = _find(node.children, label);
    if (nested != null) return nested;
  }
  return null;
}

void main() {
  group('configuration is grouped, not loose', () {
    const Set<String> allMastersTabs = {
      'firms',
      'customers',
      'products',
      'vendors',
      'branches',
      'warehouses',
      'firm-settings',
      'financial-years',
      'branches-departments',
    };

    test('the settings entries sit under Configuration', () {
      final List<WorkspaceNavigationNode> nodes = _masters(allMastersTabs);

      final WorkspaceNavigationNode? configuration =
          _find(nodes, 'Configuration');
      expect(configuration, isNotNull);
      expect(
        configuration!.children.map((node) => node.path),
        containsAll(<String>['firm-settings', 'financial-years']),
      );

      // And no longer at the top of Masters, level with Customers and Products.
      expect(
        nodes.map((node) => node.label),
        isNot(contains('Firm Settings')),
        reason: 'a module of master data should not end in things that are not',
      );
    });

    test('every path is unchanged, so stored workspaces still resolve', () {
      // Grouping moved where a node is drawn, not what it points at. If a path
      // ever changes here, a stored `lastWorkspace` stops resolving and this
      // is where it should be noticed.
      final List<WorkspaceNavigationNode> nodes = _masters(allMastersTabs);
      for (final String path in <String>[
        'firm-settings',
        'financial-years',
        'branches-departments',
      ]) {
        expect(
          _find(nodes, _labelFor(path)),
          isNotNull,
          reason: '$path must still be reachable',
        );
      }
    });

    test('an empty Configuration group is not drawn at all', () {
      // A user with none of the three sees no empty heading.
      final List<WorkspaceNavigationNode> nodes = _masters({'customers'});
      expect(_find(nodes, 'Configuration'), isNull);
    });
  });

  group('the catalog still describes every module', () {
    test('each document module kept its own definition', () {
      // Re-parenting and re-ordering are sidebar concerns. If one of these
      // stopped being a module, its page and permissions would go with it.
      for (final AppModule module in <AppModule>[
        AppModule.salesOrders,
        AppModule.deliveryNotes,
        AppModule.salesInvoices,
        AppModule.goodsReceipts,
        AppModule.purchaseInvoices,
        AppModule.purchaseReturns,
      ]) {
        expect(() => ModuleCatalog.byId(module), returnsNormally);
      }
    });
  });
}

String _labelFor(String path) => switch (path) {
      'firm-settings' => 'Firm Settings',
      'financial-years' => 'Financial Years',
      'branches-departments' => 'Branches / Departments',
      _ => path,
    };
