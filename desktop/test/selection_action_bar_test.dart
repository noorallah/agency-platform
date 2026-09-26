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
    expect([for (final c in toolbar.forList().commands) c.id],
        ['print-settings']);
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
    expect(summary.detail, 'Anand Agencies · Partially Delivered · 1,12,050.95');
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
}
