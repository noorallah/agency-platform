// Every module tab must have a way in.
//
// `ModuleCatalog.navigationChildren` is hand-built for several modules
// (masters, administration, purchases, goods receipts, inventory) and
// auto-generated for the rest. A hand-built builder can silently omit a tab,
// and one did: Statements and Loyalty were defined, permission-gated and
// wired to their pages, yet listed nowhere in the Masters sidebar, so both
// screens were unreachable from the UI for every role (docs/BACKLOG.md 20).
//
// This walks every module with *all* its tabs visible and asserts each tab id
// is reachable through the navigation tree. An intentional exception -- a tab
// reached only from inside another screen -- goes in `_reachedElsewhere` with
// a reason, so leaving one out stays a deliberate act rather than an accident.

import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/workspace_templates.dart';
import 'package:flutter_test/flutter_test.dart';

/// Tab ids deliberately not in the navigation, each with why.
const Map<String, String> _reachedElsewhere = <String, String>{
  // Roles and Permissions share one screen (a TabGroupPage): the sidebar
  // shows one leaf pointing at 'roles', and 'permissions' is reached by the
  // tab strip inside it, not by a navigation path of its own.
  'permissions': 'shares the Roles & Permissions tab-group screen',
};

Set<String> _paths(List<WorkspaceNavigationNode> nodes) {
  final Set<String> found = <String>{};
  void walk(WorkspaceNavigationNode node) {
    final String? path = node.path;
    if (path != null && path.isNotEmpty) found.add(path);
    node.children.forEach(walk);
  }

  nodes.forEach(walk);
  return found;
}

void main() {
  group('every module tab is reachable from its navigation', () {
    for (final ModuleDefinition module in ModuleCatalog.modules) {
      test('${module.id.name} lists all of its tabs', () {
        final Set<String> allTabIds =
            module.tabs.map((tab) => tab.id).toSet();
        final Set<String> reachable =
            _paths(ModuleCatalog.navigationChildren(module.id, allTabIds));

        final List<String> orphaned = allTabIds
            .where((id) =>
                !reachable.contains(id) && !_reachedElsewhere.containsKey(id))
            .toList();

        expect(
          orphaned,
          isEmpty,
          reason: 'these ${module.id.name} tabs have no way in -- add a '
              'navigation node, or record the reason in _reachedElsewhere: '
              '$orphaned',
        );
      });
    }

    test('Statements and Loyalty are reachable in Masters', () {
      // The specific pair this test was written for.
      final ModuleDefinition masters = ModuleCatalog.byId(AppModule.masters);
      final Set<String> reachable = _paths(ModuleCatalog.navigationChildren(
        AppModule.masters,
        masters.tabs.map((tab) => tab.id).toSet(),
      ));
      expect(reachable, containsAll(<String>['customer-statements', 'loyalty']));
    });
  });
}
