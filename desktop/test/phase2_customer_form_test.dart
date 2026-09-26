// The customer record in the phase 2 app (2026-09-26): a full-page tab with
// every section in one scroll and a side panel of what they owe, instead of a
// dialog of seven tabs (design section 9, item 1).

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _customerJson() => <String, dynamic>{
      'id': 'cust-1',
      'version': 4,
      'firm_id': 'firm-1',
      'code': 'CUS-001',
      'customer_type': 'BUSINESS',
      'name': 'Anand Agencies',
      'display_name': 'Anand Agencies',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '50000.00',
      'current_outstanding': '12000.00',
      'payment_terms_days': 30,
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
    };

void main() {
  testWidgets('phase 2 shows the whole record on one page and saves it',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: CustomerWorkspaceDialog(
          mode: CustomerDialogMode.edit,
          customer: Customer.fromJson(_customerJson()),
          onSave: (payload) async {
            sent = payload;
            return Customer.fromJson(_customerJson());
          },
          loadPlaces: (level, {parentId = ''}) async => const [],
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // No tabs: the money fields sit on the same page as the name.
    expect(find.text('Customer name'), findsOneWidget);
    expect(find.text('Credit limit'), findsOneWidget);
    expect(find.text('Contact persons'), findsOneWidget);

    // The side panel says what they owe against their limit.
    expect(find.byKey(const ValueKey('document-side-panel')), findsOneWidget);
    expect(find.text('12,000.00'), findsOneWidget);
    expect(find.text('38,000.00'), findsOneWidget);
    expect(find.text('30 days'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Display name'),
      'Anand Agencies (Main)',
    );
    await tester.tap(find.byKey(const ValueKey('customer-save')));
    await tester.pumpAndSettle();
    expect(sent?['display_name'], 'Anand Agencies (Main)');
    expect(sent?['code'], 'CUS-001');
  });
}
