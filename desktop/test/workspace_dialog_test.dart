import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The dialog chrome.
///
/// `onSave` was wired to a keyboard shortcut and nothing else, so a dialog
/// passing it without building its own footer offered no way to save that
/// anybody could see. Two shipped that way -- recording a receipt and moving
/// stock -- before it was noticed.
Future<void> _pump(
  WidgetTester tester,
  Widget dialog, {
  bool settle = true,
}) async {
  tester.view.physicalSize = const Size(1200, 800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: dialog)));
  // A loading dialog spins forever, so there is nothing to settle to.
  if (settle) {
    await tester.pumpAndSettle();
  } else {
    await tester.pump();
  }
}

void main() {
  testWidgets('a dialog that can be saved shows a way to save it',
      (tester) async {
    bool saved = false;
    await _pump(
      tester,
      WorkspaceDialog(
        title: 'Something',
        body: const Text('body'),
        onSave: () => saved = true,
      ),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    expect(saved, isTrue);
  });

  testWidgets('the button can be named after what it does', (tester) async {
    // "Record receipt" reads better than "Save" on a dialog that records
    // something rather than editing it.
    await _pump(
      tester,
      WorkspaceDialog(
        title: 'Something',
        body: const Text('body'),
        onSave: () {},
        saveLabel: 'Record receipt',
      ),
    );

    expect(find.widgetWithText(FilledButton, 'Record receipt'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Save'), findsNothing);
  });

  testWidgets('a dialog with its own footer keeps it', (tester) async {
    await _pump(
      tester,
      WorkspaceDialog(
        title: 'Something',
        body: const Text('body'),
        onSave: () {},
        footer: const Text('my own footer'),
      ),
    );

    expect(find.text('my own footer'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Save'), findsNothing);
  });

  testWidgets('a read-only dialog gets no save button', (tester) async {
    await _pump(
      tester,
      const WorkspaceDialog(title: 'Something', body: Text('body')),
    );

    expect(find.widgetWithText(FilledButton, 'Save'), findsNothing);
    expect(find.byTooltip('Close'), findsOneWidget);
  });

  testWidgets('while it is saving, both actions are held', (tester) async {
    await _pump(
      tester,
      WorkspaceDialog(
        title: 'Something',
        body: const Text('body'),
        loading: true,
        onSave: () {},
        onClose: () {},
      ),
      settle: false,
    );

    final FilledButton save = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Save'),
    );
    final TextButton cancel = tester.widget<TextButton>(
      find.widgetWithText(TextButton, 'Cancel'),
    );
    expect(save.onPressed, isNull);
    expect(cancel.onPressed, isNull);
  });
}
