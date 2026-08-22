// A dialog always offers a way out.
//
// `WorkspaceDialog` passed `onClose` straight through to three controls — the
// Cancel button, the header cross and the Escape shortcut — so a caller that
// forgot it got all three disabled at once. Three editors shipped that way:
// quotations, products and sales returns. Opening a new quotation and changing
// your mind left the dialog on screen with no way out but saving it.
//
// Closing is now what happens when nothing else is asked for, and these pin
// that: the default, the override, and the fact that a busy dialog still holds
// the door shut while it saves.

import 'package:agency_desktop/ui/workspace/workspace_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> _open(
  WidgetTester tester, {
  VoidCallback? onClose,
  bool loading = false,
}) async {
  tester.view.physicalSize = const Size(1400, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => showDialog<void>(
            context: context,
            builder: (_) => WorkspaceDialog(
              title: 'New quotation',
              onSave: () {},
              onClose: onClose,
              loading: loading,
              body: const Text('body'),
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  if (loading) {
    // A loading dialog shows a progress indicator, which never stops
    // animating -- `pumpAndSettle` would wait for it forever.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
  } else {
    await tester.pumpAndSettle();
  }
  expect(find.text('New quotation'), findsOneWidget);
}

void main() {
  testWidgets('Cancel closes a dialog that asked for nothing special',
      (tester) async {
    await _open(tester);

    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(find.text('New quotation'), findsNothing);
  });

  testWidgets('the header cross closes it too', (tester) async {
    await _open(tester);

    await tester.tap(find.byTooltip('Close'));
    await tester.pumpAndSettle();

    expect(find.text('New quotation'), findsNothing);
  });

  testWidgets('a caller that wants something else still gets it',
      (tester) async {
    // Asking about unsaved work before closing is the reason this callback
    // exists at all.
    int asked = 0;
    await _open(tester, onClose: () => asked++);

    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(asked, 1);
    expect(find.text('New quotation'), findsOneWidget,
        reason: 'the caller decides whether it closes');
  });

  testWidgets('a dialog that is saving cannot be closed underneath itself',
      (tester) async {
    await _open(tester, loading: true);

    final TextButton cancel = tester.widget<TextButton>(
      find.widgetWithText(TextButton, 'Cancel'),
    );
    expect(cancel.onPressed, isNull);
    // `IconButton` builds the tooltip *inside* itself, so the button is the
    // ancestor of what `byTooltip` matches, not its descendant.
    final IconButton close = tester.widget<IconButton>(
      find.ancestor(
        of: find.byTooltip('Close'),
        matching: find.byType(IconButton),
      ),
    );
    expect(close.onPressed, isNull);
  });
}
