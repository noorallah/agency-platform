import 'package:agency_desktop/phase2/phase2_scope.dart';
import 'package:agency_desktop/ui/workspace/workspace_components.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// D-UI-26: a list kept built reads itself again when its screen is put on
/// show again.
///
/// The shell fires a [ShownAgainSignal] for a screen that was not rebuilt --
/// the one under a document tab, or the one picked again while it is there
/// -- and the phase 2 list layout answers it, once for every list, by
/// running the screen's own Refresh. What the shell fires on is pinned in
/// `desktop_shell_menu_layout_test.dart`.
Widget _list({
  required ShownAgainSignal? signal,
  required List<ToolbarAction> run,
  bool refreshOffered = true,
  bool refreshEnabled = true,
}) {
  final Widget list = ManagementWorkspaceLayout(
    searchPanel: SearchFilterPanel(
      controller: TextEditingController(),
      onSearch: (_) {},
    ),
    toolbar: WorkspaceToolbar(
      onAction: run.add,
      isEnabled: (action) =>
          action != ToolbarAction.refresh || refreshEnabled,
      actions: [
        ToolbarAction.edit,
        if (refreshOffered) ToolbarAction.refresh,
        ToolbarAction.newItem,
      ],
    ),
    primaryContent: const Text('rows'),
    statusBar: const WorkspaceStatusBar(total: 0, selected: false),
  );
  return MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: signal == null
            ? list
            : ScreenShownAgain(signal: signal, child: list),
      ),
    ),
  );
}

void main() {
  testWidgets('a list reads itself again when its screen is shown again',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final ShownAgainSignal signal = ShownAgainSignal();
    final List<ToolbarAction> run = [];
    await tester.pumpWidget(_list(signal: signal, run: run));
    await tester.pump();
    // Opening the list is the screen's own read, not this one.
    expect(run, isEmpty);

    signal.fire();
    expect(run, [ToolbarAction.refresh]);
    signal.fire();
    expect(run, [ToolbarAction.refresh, ToolbarAction.refresh]);
    expect(signal.serial, 2);
  });

  testWidgets('a list with no Refresh, or a disabled one, is left alone',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final ShownAgainSignal signal = ShownAgainSignal();
    final List<ToolbarAction> run = [];
    await tester
        .pumpWidget(_list(signal: signal, run: run, refreshOffered: false));
    await tester.pump();
    signal.fire();
    expect(run, isEmpty);

    // Disabled while the list is busy reading, say.
    await tester
        .pumpWidget(_list(signal: signal, run: run, refreshEnabled: false));
    await tester.pump();
    signal.fire();
    expect(run, isEmpty);
  });

  testWidgets('a list that has gone no longer answers', (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final ShownAgainSignal signal = ShownAgainSignal();
    final List<ToolbarAction> run = [];
    await tester.pumpWidget(_list(signal: signal, run: run));
    await tester.pump();
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    await tester.pump();

    signal.fire();
    expect(run, isEmpty);
    // Nothing is left listening, so the shell can dispose it.
    signal.dispose();
  });

  testWidgets('outside the shell a list has nothing to answer',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<ToolbarAction> run = [];
    await tester.pumpWidget(_list(signal: null, run: run));
    await tester.pump();
    expect(run, isEmpty);
    expect(tester.takeException(), isNull);
  });
}
