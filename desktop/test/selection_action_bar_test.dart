// Option C (owner, 2026-09-27): a list's page line keeps what is about the
// list; the selected row's actions move to a bar that names the row, and the
// bar offers only what can run.

import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

WorkspaceToolbar _toolbar(List<String> ran) => WorkspaceToolbar(
      actions: const [
        ToolbarAction.view,
        ToolbarAction.edit,
        ToolbarAction.refresh,
        ToolbarAction.newItem,
      ],
      isEnabled: (action) => action != ToolbarAction.edit,
      onAction: (action) => ran.add(action.name),
      commands: [
        ToolbarCommand(
          id: 'approve',
          label: 'Approve',
          icon: Icons.check,
          onPressed: () => ran.add('approve'),
        ),
        const ToolbarCommand(id: 'close', label: 'Close', icon: Icons.stop),
        ToolbarCommand(
          id: 'print-settings',
          label: 'Print settings',
          icon: Icons.tune,
          menuOnly: true,
          onPressed: () => ran.add('settings'),
        ),
      ],
    );

Widget _page(WorkspaceToolbar toolbar, SelectionSummary? selection) =>
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ManagementWorkspaceLayout(
            toolbar: toolbar,
            searchPanel: SearchFilterPanel(
              controller: TextEditingController(),
              onSearch: (_) {},
            ),
            primaryContent: const SizedBox.expand(),
            statusBar: const SizedBox.shrink(),
            selectionBar: true,
            selection: selection,
          ),
        ),
      ),
    );

void main() {
  test('the line keeps the list; the bar gets what the row can do now', () {
    final WorkspaceToolbar toolbar = _toolbar([]);

    expect(toolbar.forList().actions,
        [ToolbarAction.refresh, ToolbarAction.newItem]);
    expect(
        [for (final c in toolbar.forList().commands) c.id], ['print-settings']);
    // Edit is disabled and Close has nothing to run: neither is offered.
    expect([for (final c in toolbar.forSelection()) c.id], ['view', 'approve']);
    expect(toolbar.forSelection().first.label, 'Open');
  });

  test('a document is named as the grid writes it', () {
    final SelectionSummary summary = SelectionSummary.document(
      number: 'SO-2026-2027-000025',
      party: 'Anand Agencies',
      status: 'PARTIALLY_DELIVERED',
      total: '112050.9514',
      onClear: () {},
    );
    expect(
        summary.detail, 'Anand Agencies · Partially Delivered · 1,12,050.95');
  });

  test('a record summarised as lines is named, coded, labelled and statused',
      () {
    final SelectionSummary summary = SelectionSummary.lines(
      title: 'Head Office',
      lines: const [
        DetailLine('Code', 'WHL_HO'),
        DetailLine('Status', 'ACTIVE'),
        DetailLine('Warehouses', '3'),
        DetailLine('Phone', ''),
      ],
      onClear: () {},
    );
    expect(summary.title, 'Head Office');
    // A bare "3" says nothing, so a fact other than the code keeps its label;
    // an empty one is left out.
    expect(summary.detail, 'WHL_HO · Warehouses: 3 · Active');
  });

  testWidgets('the bar appears with a selection, names it, and runs actions',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<String> ran = [];
    bool cleared = false;

    await tester.pumpWidget(_page(_toolbar(ran), null));
    expect(find.byKey(const ValueKey('selection-bar')), findsNothing);
    expect(find.byKey(const ValueKey('toolbar-command-approve')), findsNothing);

    await tester.pumpWidget(_page(
      _toolbar(ran),
      SelectionSummary(
        title: 'SO-2026-2027-000025',
        detail: 'Anand Agencies · DRAFT · 89.95',
        onClear: () => cleared = true,
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    expect(find.textContaining('SO-2026-2027-000025'), findsOneWidget);
    expect(find.byKey(const ValueKey('selection-close')), findsNothing);

    // The actions stand at the right of the bar, not after the name.
    expect(
      tester.getTopRight(find.byKey(const ValueKey('selection-approve'))).dx,
      greaterThan(1366 - 200),
    );

    await tester.tap(find.byKey(const ValueKey('selection-approve')));
    await tester.tap(find.byKey(const ValueKey('selection-view')));
    await tester.tap(find.byKey(const ValueKey('selection-clear')));
    expect(ran, ['approve', 'view']);
    expect(cleared, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phase 2 keeps a view switch and a notice on the page line',
      (tester) async {
    // 4.5: no band above the grid (owner, 2026-09-27 review). A view switch
    // sits on the line; a screen's notice is behind an (i) there.
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ManagementWorkspaceLayout(
            toolbar: WorkspaceToolbar(
              actions: const [ToolbarAction.refresh],
              isEnabled: (_) => true,
              onAction: (_) {},
            ),
            searchPanel: SearchFilterPanel(
              controller: TextEditingController(),
              onSearch: (_) {},
            ),
            viewBar: const Text('Rates | Payouts', key: ValueKey('views')),
            notice: 'What this screen is for.',
            primaryContent: const SizedBox.expand(key: ValueKey('grid')),
            statusBar: const SizedBox.shrink(),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final double views =
        tester.getCenter(find.byKey(const ValueKey('views'))).dy;
    final double search = tester.getCenter(find.byType(SearchFilterPanel)).dy;
    expect((views - search).abs(), lessThan(12), reason: 'on the one line');
    expect(
      tester.getTopLeft(find.byKey(const ValueKey('grid'))).dy,
      greaterThan(views),
    );
    expect(find.byKey(const ValueKey('page-notice')), findsOneWidget);
    expect(find.text('What this screen is for.'), findsNothing,
        reason: 'behind the (i), not a box');
  });

  testWidgets('a status badge reads in words in phase 2', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: Phase2Scope(child: StatusBadge(label: 'ON_HOLD')),
      ),
    ));
    expect(find.text('On hold'), findsOneWidget);
    expect(statusInWords('APPROVED (on hold)'), 'Approved (on hold)');
    expect(statusInWords('Kumar Stores'), 'Kumar Stores');
  });
}
