// A standing discount is a price decision, not a contact detail (D-MST-2).
//
// A segment's rate already takes `CUSTOMER_MANAGE_SETTINGS`; the customer's
// own rate rode on `CUSTOMER_UPDATE`, so the sales manager refused the credit
// limit (D-CFG-17) could set 100% instead. The server now refuses a moved
// rate -- and a new customer that starts with one -- without the code; the
// form says so before a save is refused, and still sends the stored figure,
// which is not a change.

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _field = 'Default discount %';
const String _helper = 'Setting a standing discount needs';

Json _customerJson() => <String, dynamic>{
      'id': 'cust-1',
      'code': 'C001',
      'name': 'Shop One',
      'display_name': 'Shop One',
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '25000.00',
      'default_discount_percent': '7.5000',
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
        mayChangeStandingDiscount: mayChange,
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

TextField _discountBox(WidgetTester tester) => tester.widget<TextField>(
      find.descendant(
        of: find.widgetWithText(TextFormField, _field),
        matching: find.byType(TextField),
      ),
    );

void main() {
  testWidgets('without the settings code the discount cannot be edited',
      (tester) async {
    await _open(tester, mode: CustomerDialogMode.edit, mayChange: false);
    await _financialTab(tester);

    expect(_discountBox(tester).readOnly, isTrue);
    expect(find.textContaining(_helper), findsOneWidget);
  });

  testWidgets('an unrelated edit still sends the stored discount unchanged',
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
    expect(saved!['default_discount_percent'], '7.5000');
  });

  testWidgets('with the code the discount is an ordinary field',
      (tester) async {
    await _open(tester, mode: CustomerDialogMode.edit, mayChange: true);
    await _financialTab(tester);

    expect(_discountBox(tester).readOnly, isFalse);
    expect(find.textContaining(_helper), findsNothing);
  });

  testWidgets('a new customer starts at none for whoever lacks the code',
      (tester) async {
    // Unlike a credit limit, a discount typed at creation loosens rather
    // than tightens, so the server refuses it and the form does not offer it.
    Json? saved;
    await _open(
      tester,
      mode: CustomerDialogMode.create,
      mayChange: false,
      onSaved: (payload) => saved = payload,
    );
    await _financialTab(tester);

    expect(_discountBox(tester).readOnly, isTrue);
    expect(_discountBox(tester).controller!.text, '0');
    expect(saved, isNull);
  });
}
