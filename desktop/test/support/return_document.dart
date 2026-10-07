import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Choose the document a new sales return is raised against.
///
/// The editor used to open with the first source document already chosen. It
/// starts with nothing chosen now (D-UI-22), so a test that is about
/// something else asks for the document it used to be given. [label] is any
/// text of the entry, such as the document number.
Future<void> chooseReturnDocument(
  WidgetTester tester,
  String label,
) async {
  final Finder phase2 = find.byKey(const ValueKey<String>('sales-return-document'));
  if (phase2.evaluate().isNotEmpty) {
    await tester.tap(phase2);
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining(label).last);
  } else {
    await tester.tap(find.widgetWithText(DropdownButtonFormField<String>, 'Returned against'));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining(label).last);
  }
  await tester.pumpAndSettle();
}
