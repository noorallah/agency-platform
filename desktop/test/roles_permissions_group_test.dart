import 'package:agency_desktop/ui/administration/tab_group_page.dart';
import 'package:agency_desktop/ui/workspace/enterprise_sidebar.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/workspace_templates.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Roles and Permissions are one sidebar entry with a tab strip inside.
///
/// Both are reference screens somebody opens a few times a year, and each
/// was a row in a menu scanned every day. The shape that shortens the menu
/// is one leaf and an inner strip -- a parent with children only expands, so
/// that would be two clicks and more rows. What must not change is the
/// address: each half keeps its own tab id, because that is what Ctrl+K
/// opens, what the router carries and what the remembered screen restores.
void main() {
  final ModuleDefinition administration =
      ModuleCatalog.byId(AppModule.administration);

  List<WorkspaceNavigationNode> nav(Set<String> visible) =>
      ModuleCatalog.navigationChildren(AppModule.administration, visible);

  group('the sidebar entry', () {
    test('two tabs are one entry, whose path is the first of them', () {
      final List<WorkspaceNavigationNode> nodes =
          nav({'users', 'roles', 'permissions'});
      final Iterable<WorkspaceNavigationNode> entries = nodes
          .where((node) => node.label == ModuleCatalog.rolesAndPermissions);

      expect(entries, hasLength(1));
      expect(entries.single.path, 'roles');
      expect(entries.single.alsoSelectedBy, ['permissions']);
      expect(nodes.map((node) => node.label), isNot(contains('Roles')));
      expect(nodes.map((node) => node.label), isNot(contains('Permissions')));
    });

    test('a caller who may open only one half gets an entry that opens it',
        () {
      // An entry whose path is a tab the caller cannot open would open
      // nothing -- the family of defect a menu entry that leads nowhere is.
      final WorkspaceNavigationNode onlyPermissions = nav({'permissions'})
          .singleWhere(
              (node) => node.label == ModuleCatalog.rolesAndPermissions);
      expect(onlyPermissions.path, 'permissions');
      expect(onlyPermissions.alsoSelectedBy, isEmpty);

      final WorkspaceNavigationNode onlyRoles = nav({'roles'}).singleWhere(
          (node) => node.label == ModuleCatalog.rolesAndPermissions);
      expect(onlyRoles.path, 'roles');
    });

    test('neither half visible, no entry', () {
      expect(
        nav({'users'}).map((node) => node.label),
        isNot(contains(ModuleCatalog.rolesAndPermissions)),
      );
    });

    test('the group is declared on the catalogue, in order', () {
      expect(
        administration
            .groupMembers(ModuleCatalog.rolesAndPermissions)
            .map((tab) => tab.id),
        ['roles', 'permissions'],
      );
    });
  });

  group('the entry stays highlighted on either half', () {
    // A leaf that opens a page holding two addressable tabs must be drawn
    // selected whichever is current, or it goes dark the moment somebody
    // switches the inner tab or arrives by Ctrl+K on a permission.
    const WorkspaceNavigationNode leaf = WorkspaceNavigationNode(
      label: 'Roles & Permissions',
      path: 'roles',
      alsoSelectedBy: ['permissions'],
    );

    test('the node answers for both paths', () {
      expect(leaf.isSelectedBy('roles'), isTrue);
      expect(leaf.isSelectedBy('permissions'), isTrue);
      expect(leaf.isSelectedBy('users'), isFalse);
      expect(leaf.isSelectedBy(null), isFalse);
    });

    testWidgets('the sidebar tile is selected on the other half',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: CollapsibleGroupTile(
            node: leaf,
            selectedPath: 'permissions',
            onSelected: (_) {},
            depth: 0,
          ),
        ),
      ));

      expect(tester.widget<ListTile>(find.byType(ListTile)).selected, isTrue);
    });

    testWidgets('and so is the navigation tree tile', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: WorkspaceNavigationTree(
            nodes: [leaf],
            selectedPath: 'permissions',
            onSelected: _ignore,
          ),
        ),
      ));

      expect(tester.widget<ListTile>(find.byType(ListTile)).selected, isTrue);
    });

    testWidgets('tapping the entry still opens its own path', (tester) async {
      String? opened;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: CollapsibleGroupTile(
            node: leaf,
            selectedPath: 'permissions',
            onSelected: (path) => opened = path,
            depth: 0,
          ),
        ),
      ));
      await tester.tap(find.text('Roles & Permissions'));

      expect(opened, 'roles');
    });
  });

  group('the page', () {
    final List<ModuleTabDefinition> members =
        administration.groupMembers(ModuleCatalog.rolesAndPermissions);

    Future<List<String>> pump(
      WidgetTester tester, {
      required List<ModuleTabDefinition> members,
      required String current,
    }) async {
      final List<String> selected = [];
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: TabGroupPage(
            members: members,
            current: current,
            onSelect: selected.add,
            builder: (id) => Text('body:$id'),
          ),
        ),
      ));
      return selected;
    }

    testWidgets('shows a strip of the members over the current one',
        (tester) async {
      await pump(tester, members: members, current: 'roles');

      expect(find.text('Roles'), findsOneWidget);
      expect(find.text('Permissions'), findsOneWidget);
      expect(find.text('body:roles'), findsOneWidget);
      expect(find.text('body:permissions'), findsNothing);
    });

    testWidgets('choosing the other half hands its id to the router',
        (tester) async {
      // Not local state: the id goes out through `onSelect`, the workspace
      // rebuilds with it, and the heading, the sidebar and the remembered
      // screen all follow the same value.
      final List<String> selected =
          await pump(tester, members: members, current: 'roles');

      await tester.tap(find.text('Permissions'));
      await tester.pumpAndSettle();

      expect(selected, ['permissions']);
    });

    testWidgets('one visible member means no strip', (tester) async {
      await pump(tester, members: [members.last], current: 'permissions');

      expect(find.byType(SegmentedButton<String>), findsNothing);
      expect(find.text('body:permissions'), findsOneWidget);
    });
  });
}

void _ignore(String _) {}
