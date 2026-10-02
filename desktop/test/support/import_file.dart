import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Tap "Choose file…" in a file-import dialog and wait until the file is read.
///
/// The dialog awaits `XFile.readAsBytes()`, which is real file I/O and runs
/// outside the fake clock. A fixed 200ms sleep was enough on an idle machine
/// and not on a loaded one, so the bytes were still null, "Check file" stayed
/// disabled and the test failed for no product reason (D-TEST-2). This waits
/// for the condition itself -- "Check file" enabled -- with a generous cap.
Future<void> chooseImportFile(
  WidgetTester tester, {
  Duration limit = const Duration(seconds: 20),
}) async {
  await tester.runAsync(() async {
    await tester.tap(find.text('Choose file…'));
  });
  final Stopwatch elapsed = Stopwatch()..start();
  while (!_checkEnabled(tester) && elapsed.elapsed < limit) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await tester.pump();
  }
  await tester.pumpAndSettle();
}

bool _checkEnabled(WidgetTester tester) {
  final Finder button = find.ancestor(
    of: find.text('Check file'),
    matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
  );
  if (button.evaluate().isEmpty) return false;
  return tester.widget<ButtonStyleButton>(button.first).enabled;
}
