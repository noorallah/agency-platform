// A customer's GSTIN and PAN may repeat (decision A7): one company has many
// accounts, a branch per state sharing its PAN. The form asks before saving a
// value another customer already holds, and the check is only advice.

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _customerJson({String pan = ''}) => <String, dynamic>{
      'id': 'cust-1',
      'version': 1,
      'firm_id': 'firm-1',
      'code': 'CUS-001',
      'customer_type': 'BUSINESS',
      'name': 'Anand Agencies',
      'display_name': 'Anand Agencies',
      'pan_number': pan,
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
    };

const String _warning = 'PAN AAACP1234C is also on HO Customer HO.';

Future<void> _pump(
  WidgetTester tester, {
  required Future<String?> Function(String, String) check,
  required List<Json> saved,
  Customer? customer,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: CustomerWorkspaceDialog(
          mode: customer == null
              ? CustomerDialogMode.create
              : CustomerDialogMode.edit,
          customer: customer,
          onSave: (payload) async {
            saved.add(payload);
            return Customer.fromJson(_customerJson());
          },
          checkIdentity: check,
          loadPlaces: (level, {parentId = ''}) async => const [],
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _fillAndSave(WidgetTester tester) async {
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Customer code'),
    'CUS-009',
  );
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Customer name'),
    'Branch Customer',
  );
  await tester.enterText(
    find.widgetWithText(TextFormField, 'PAN number'),
    'AAACP1234C',
  );
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  // Not pumpAndSettle: the form shows a spinner while it waits on the dialog.
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

void main() {
  testWidgets('a repeated PAN asks first, and Cancel saves nothing',
      (tester) async {
    final List<Json> saved = <Json>[];
    await _pump(tester, check: (_, __) async => _warning, saved: saved);

    await _fillAndSave(tester);

    expect(find.text('Same GSTIN or PAN on another customer'), findsOneWidget);
    expect(find.textContaining(_warning), findsOneWidget);
    await tester.tap(find.descendant(
      of: find.byType(AlertDialog),
      matching: find.text('Cancel'),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(saved, isEmpty);
    expect(find.byType(CustomerWorkspaceDialog), findsOneWidget);
    expect(find.text('Branch Customer'), findsOneWidget);
  });

  testWidgets('Save anyway saves the customer', (tester) async {
    final List<Json> saved = <Json>[];
    await _pump(tester, check: (_, __) async => _warning, saved: saved);

    await _fillAndSave(tester);
    await tester.tap(find.text('Save anyway'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(saved, hasLength(1));
    expect(saved.single['pan_number'], 'AAACP1234C');
  });

  testWidgets('no other holder saves straight away', (tester) async {
    final List<Json> saved = <Json>[];
    await _pump(tester, check: (_, __) async => null, saved: saved);

    await _fillAndSave(tester);

    expect(find.byType(AlertDialog), findsNothing);
    expect(saved, hasLength(1));
  });

  testWidgets('a failed check still saves', (tester) async {
    final List<Json> saved = <Json>[];
    await _pump(
      tester,
      check: (_, __) async => throw Exception('offline'),
      saved: saved,
    );

    await _fillAndSave(tester);

    expect(find.byType(AlertDialog), findsNothing);
    expect(saved, hasLength(1));
  });

  testWidgets('an unchanged PAN on an edit is not asked about', (tester) async {
    final List<Json> saved = <Json>[];
    int asked = 0;
    await _pump(
      tester,
      check: (_, __) async {
        asked++;
        return _warning;
      },
      saved: saved,
      customer: Customer.fromJson(_customerJson(pan: 'AAACP1234C')),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(asked, 0);
    expect(saved, hasLength(1));
  });
}
