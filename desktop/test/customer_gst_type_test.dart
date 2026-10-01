// A customer's GST registration type (backlog 75 row 2).
//
// It decides whether a bill is IGST whatever the states (SEZ), which GSTR-1
// table it is filed in and the e-invoice supply type, so the form must show
// what the server holds and send what is picked -- and blank as null, which
// the server reads off the GSTIN.

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _customerJson(String gstType) => <String, dynamic>{
      'id': 'cust-1',
      'code': 'C001',
      'name': 'Zone Unit',
      'display_name': 'Zone Unit',
      'customer_type': 'BUSINESS',
      'gst_number': '33AAAPL1234C1Z5',
      'gst_registration_type': gstType,
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '0',
      'default_discount_percent': '0',
      'addresses': const <Json>[],
      'contacts': const <Json>[],
    };

Future<Json?> _openAndSave(
  WidgetTester tester, {
  required String stored,
  String? pick,
  String? shown,
}) async {
  tester.view.physicalSize = const Size(1700, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  Json? saved;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CustomerWorkspaceDialog(
        mode: CustomerDialogMode.edit,
        customer: Customer.fromJson(_customerJson(stored)),
        loadPlaces: (level, {parentId = ''}) async => const [],
        onSave: (payload) async {
          saved = payload;
          return Customer.fromJson(_customerJson(stored));
        },
      ),
    ),
  ));
  await tester.pumpAndSettle();
  if (shown != null) expect(find.text(shown), findsOneWidget);
  if (pick != null) {
    await tester.tap(find.byType(DropdownButtonFormField<String>).at(
          _pickerIndex(tester),
        ));
    await tester.pumpAndSettle();
    await tester.tap(find.text(pick).last);
    await tester.pumpAndSettle();
  }
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
  return saved;
}

/// The index of the GST registration picker among the form's dropdowns.
int _pickerIndex(WidgetTester tester) {
  final List<Element> pickers =
      find.byType(DropdownButtonFormField<String>).evaluate().toList();
  for (int index = 0; index < pickers.length; index++) {
    final Finder label = find.descendant(
      of: find.byWidget(pickers[index].widget),
      matching: find.text('GST registration'),
    );
    if (label.evaluate().isNotEmpty) return index;
  }
  fail('no GST registration picker on the form');
}

void main() {
  testWidgets('the stored type is shown and kept on save', (tester) async {
    final Json? saved = await _openAndSave(
      tester,
      stored: 'SEZ_WITHOUT_PAYMENT',
      shown: 'SEZ, under LUT (no tax)',
    );

    expect(saved!['gst_registration_type'], 'SEZ_WITHOUT_PAYMENT');
  });

  testWidgets('a picked type reaches the payload', (tester) async {
    final Json? saved = await _openAndSave(
      tester,
      stored: '',
      pick: 'SEZ, tax paid',
    );

    expect(saved!['gst_registration_type'], 'SEZ_WITH_PAYMENT');
  });

  testWidgets('blank is sent as null, left to the GSTIN', (tester) async {
    final Json? saved =
        await _openAndSave(tester, stored: '', shown: 'From the GSTIN');

    expect(saved!.containsKey('gst_registration_type'), isTrue);
    expect(saved['gst_registration_type'], isNull);
  });
}
