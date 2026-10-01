// Backlog 51, customer half: how messages reach this customer.
//
// The form sends `no_reminders`, `preferred_channel` (null for "no
// preference") and `whatsapp_opt_in`, shows the date they agreed as read-only
// text, and never sends `whatsapp_opt_in_at` -- the server declares no such
// input.

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _customerJson({bool optedIn = false}) => <String, dynamic>{
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
      'payment_terms_days': 30,
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
      'no_reminders': false,
      'preferred_channel': null,
      'whatsapp_opt_in': optedIn,
      'whatsapp_opt_in_at': optedIn ? '2026-09-30T08:00:00Z' : null,
    };

Future<Json?> _saveWith(
  WidgetTester tester,
  Future<void> Function() change, {
  Json? json,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  Json? sent;
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: CustomerWorkspaceDialog(
        mode: CustomerDialogMode.edit,
        customer: Customer.fromJson(json ?? _customerJson()),
        onSave: (payload) async {
          sent = payload;
          return Customer.fromJson(_customerJson());
        },
        loadPlaces: (level, {parentId = ''}) async => const [],
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await change();
  await tester.tap(find.byKey(const ValueKey('customer-save')));
  await tester.pumpAndSettle();
  return sent;
}

void main() {
  testWidgets('the form sends the three messaging fields', (tester) async {
    final Json? sent = await _saveWith(tester, () async {
      await tester.ensureVisible(
          find.byKey(const ValueKey('customer-messaging-group')));
      await tester.tap(find.byKey(const ValueKey('customer-no-reminders')));
      await tester.tap(find.byKey(const ValueKey('customer-whatsapp-opt-in')));
      await tester.pumpAndSettle();
      await tester
          .tap(find.byKey(const ValueKey('customer-preferred-channel')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('WhatsApp').last);
      await tester.pumpAndSettle();
    });
    expect(sent?['no_reminders'], isTrue);
    expect(sent?['preferred_channel'], 'WHATSAPP');
    expect(sent?['whatsapp_opt_in'], isTrue);
    expect(sent?.containsKey('whatsapp_opt_in_at'), isFalse);
  });

  testWidgets('no preference is sent as null and the agreed date is shown',
      (tester) async {
    final Json? sent = await _saveWith(
      tester,
      () async {
        await tester.ensureVisible(
            find.byKey(const ValueKey('customer-messaging-group')));
        await tester.pumpAndSettle();
        expect(find.text('Agreed on 2026-09-30'), findsOneWidget);
      },
      json: _customerJson(optedIn: true),
    );
    expect(sent?['preferred_channel'], isNull);
    expect(sent?['no_reminders'], isFalse);
    expect(sent?['whatsapp_opt_in'], isTrue);
  });
}
