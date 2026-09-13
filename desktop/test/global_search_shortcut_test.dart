import 'package:agency_desktop/ui/workspace/workspace_interactions.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Ctrl+K opens global search wherever keyboard focus happens to be.
///
/// The shell bound it through `WorkspaceShortcuts`, which hears a key only
/// while focus sits inside it. Focus falls back above the shell whenever the
/// focused control goes away, and Ctrl+K then did nothing (manual plan item
/// 13.7, 2026-09-14).

Future<void> _pressCtrlK(WidgetTester tester) async {
  await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
  await tester.sendKeyEvent(LogicalKeyboardKey.keyK);
  await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
  await tester.pump();
}

void main() {
  testWidgets('Ctrl+K reaches search with focus outside the shell',
      (tester) async {
    int opened = 0;
    await tester.pumpWidget(MaterialApp(
      home: GlobalSearchShortcut(
        onSearch: () => opened++,
        child: const Scaffold(body: Text('shell')),
      ),
    ));
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pump();

    await _pressCtrlK(tester);
    expect(opened, 1);

    await tester.sendKeyEvent(LogicalKeyboardKey.keyK);
    await tester.pump();
    expect(opened, 1, reason: 'K on its own is typing, not a shortcut');
  });

  testWidgets('the old focus-bound shortcut is deaf once focus leaves it',
      (tester) async {
    // The shape the shell had: this is the defect the new widget closes.
    int opened = 0;
    await tester.pumpWidget(MaterialApp(
      home: WorkspaceShortcuts(
        bindings: WorkspaceShortcutBindings(globalSearch: () => opened++),
        child: const Scaffold(body: Text('shell')),
      ),
    ));
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pump();

    await _pressCtrlK(tester);
    expect(opened, 0);
  });

  testWidgets('a dialog on top keeps Ctrl+K for itself', (tester) async {
    int opened = 0;
    await tester.pumpWidget(MaterialApp(
      home: GlobalSearchShortcut(
        onSearch: () => opened++,
        child: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => showDialog<void>(
                context: context,
                builder: (_) => const AlertDialog(content: Text('on top')),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await _pressCtrlK(tester);
    expect(opened, 0);
  });

  testWidgets('the listener goes away with the widget', (tester) async {
    int opened = 0;
    await tester.pumpWidget(MaterialApp(
      home: GlobalSearchShortcut(
        onSearch: () => opened++,
        child: const SizedBox(),
      ),
    ));
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));

    await _pressCtrlK(tester);
    expect(opened, 0);
  });
}
