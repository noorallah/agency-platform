// A credit limit is a credit control, not a contact detail (D-CFG-17).
//
// `SALES_MANAGER` is denied `CUSTOMER_MANAGE_SETTINGS` so it cannot switch the
// credit block off, and the limit is the other half of that control: raising
// it, or setting it to zero ("no limit"), lifts a block just as surely. The
// server refuses a moved limit without the code; the form says so before a
// save is refused, and still sends the stored figure, which is not a change.

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _field = 'Credit limit';
const String _helper = 'manage customer settings permission';

Json _customerJson() => <String, dynamic>{
      'id': 'cust-1',
      'code': 'C001',
      'name': 'Shop One',
      'display_name': 'Shop One',
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '25000.00',
      'default_discount_percent': '0',
      'addresses': const <Json>[],
      'contacts': const <Json>[],
    };

/// Open the editor; [onSaved] receives the payload of a save.
Future<void> _open(
  WidgetTester tester, {
  required CustomerDialogMode mode,
  required bool mayChange,
  void Function(Json payload)? onSaved,
}) async {
  tester.view.physicalSize = const Size(1700, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CustomerWorkspaceDialog(
        mode: mode,
        customer: mode == CustomerDialogMode.edit
            ? Customer.fromJson(_customerJson())
            : null,
        loadPlaces: (level, {parentId = ''}) async => const [],
        mayChangeCreditLimit: mayChange,
        onSave: (payload) async {
          onSaved?.call(payload);
          return Customer.fromJson(_customerJson());
        },
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _financialTab(WidgetTester tester) async {
  await tester.tap(find.text('Financial'));
  await tester.pumpAndSettle();
}

TextField _limitBox(WidgetTester tester) => tester.widget<TextField>(
      find.descendant(
        of: find.widgetWithText(TextFormField, _field),
        matching: find.byType(TextField),
      ),
    );

void main() {
  testWidgets('without the credit-settings code the limit cannot be edited',
      (tester) async {
    await _open(tester, mode: CustomerDialogMode.edit, mayChange: false);
    await _financialTab(tester);

    expect(_limitBox(tester).readOnly, isTrue);
    expect(find.textContaining(_helper), findsOneWidget);
  });

  testWidgets('an unrelated edit still sends the stored limit unchanged',
      (tester) async {
    // The server does not count resending the stored figure as a change, so
    // somebody without the code can still correct a name.
    Json? saved;
    await _open(
      tester,
      mode: CustomerDialogMode.edit,
      mayChange: false,
      onSaved: (payload) => saved = payload,
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Display name'),
      'Shop One Renamed',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(saved, isNotNull);
    expect(saved!['credit_limit'], '25000.00');
  });

  testWidgets('with the code the limit is an ordinary field', (tester) async {
    await _open(tester, mode: CustomerDialogMode.edit, mayChange: true);
    await _financialTab(tester);

    expect(_limitBox(tester).readOnly, isFalse);
    expect(find.textContaining(_helper), findsNothing);
  });

  testWidgets('a new customer can be given a limit by whoever creates it',
      (tester) async {
    // Every new customer otherwise starts with none, so a limit typed here
    // can only tighten what they would have had.
    await _open(tester, mode: CustomerDialogMode.create, mayChange: false);
    await _financialTab(tester);

    expect(_limitBox(tester).readOnly, isFalse);
  });
}
