// Every telephone box the server validates says what shape it wants.
//
// Firms, customers and vendors all run their numbers through the same E.164
// validator, whose refusal -- "A valid E.164 phone number is required." --
// names a standard without showing an example. `+919876543210` passes,
// `9876543210` does not, and nothing on screen said so.

import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('the hint carries an example, which is the point of it', () {
    expect(phoneHelperText, contains('+91'));
    expect(phoneHelperText, contains('country code'));
  });

  testWidgets('the customer form shows it against the phone boxes',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1600, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CustomerWorkspaceDialog(
          mode: CustomerDialogMode.create,
          customer: null,
          onSave: (_) async => throw UnimplementedError(),
          loadPlaces: (level, {parentId = ''}) async => const [],
        ),
      ),
    ));
    await tester.pumpAndSettle();

    // Phone and Alternate phone: the server checks both.
    expect(find.text(phoneHelperText), findsNWidgets(2));
  });
}
